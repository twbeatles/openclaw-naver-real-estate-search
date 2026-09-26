"""Vendored collection algorithm regression tests (offline, no network)."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from naver_collect.article_api import (
    MAX_ARTICLE_API_PAGES,
    article_api_has_more_pages,
    article_api_list_count,
    article_api_path_kind,
    build_article_api_url,
)
from naver_collect.article_lookup import (
    detect_article_asset_type,
    extract_article_complex_info,
    resolve_article_complex,
)
from naver_collect.converters import (
    AreaConverter,
    PriceConverter,
    enrich_gap_fields,
)
from naver_collect.response_capture import (
    detect_trade_type,
    normalize_article_payload,
    normalize_price_fields,
)
from naver_collect.retry import (
    NetworkErrorHandler,
    RetryCancelledError,
    RetryHandler,
)
from naver_collect.site_contract import (
    article_api_real_estate_type,
    build_complex_overview_url,
    build_complex_url,
    get_article_url,
    trade_type_to_code,
)


def test_price_converter_decimal_eok() -> None:
    assert PriceConverter.to_int("1.5억") == 15000
    assert PriceConverter.to_int("12억 5,000") == 125000
    assert PriceConverter.to_int("5000만") == 5000
    assert PriceConverter.to_string(15000) == "1억 5,000만"


def test_area_converter_matches_upstream_ratio() -> None:
    assert AreaConverter.sqm_to_pyeong(84) == round(84 * 0.3025, 1)
    assert AreaConverter.pyeong_to_sqm(25) == round(25 / 0.3025, 2)


def test_article_api_url_contract() -> None:
    apt_url = build_article_api_url("complexes", "1147", "전세", "APT", page=2)
    assert "realEstateType=APT%3AABYG%3AJGC" in apt_url
    assert "tradeType=B1" in apt_url and "page=2" in apt_url
    assert "/api/articles/complex/1147?" in apt_url
    vl_url = build_article_api_url("houses", "9999", "매매", "VL", page=1)
    assert "realEstateType=VL%3ADDDGG%3AJWJT%3ASGJT" in vl_url
    assert "/api/articles/house/9999?" in vl_url
    assert article_api_path_kind("houses") == "house"
    assert article_api_path_kind("complexes") == "complex"
    assert article_api_real_estate_type("APT", include_pre=True).endswith(":PRE")
    assert trade_type_to_code("월세") == "B2"
    assert MAX_ARTICLE_API_PAGES == 50


def test_article_api_pagination_uses_pre_filter_count() -> None:
    assert article_api_has_more_pages({"isMoreData": True}, 0) is True
    assert article_api_has_more_pages({"isMoreData": False}, 20) is False
    assert article_api_has_more_pages({"moreData": True}, 1) is True
    assert article_api_has_more_pages({"articleList": [1] * 20}, 20) is True
    assert article_api_has_more_pages({"articleList": [1, 2]}, 2) is False
    assert article_api_list_count({"articleList": [1, 2, 3]}) == 3
    assert article_api_list_count({}) == 0


def test_trade_detection_code_fallback() -> None:
    # upstream contract: requested_trade_type seeds the name default, so an
    # explicit code is only consulted when no name/requested value exists.
    assert detect_trade_type({"tradeType": "B1"}) == "전세"
    assert detect_trade_type({"tradeTypeName": "월세"}) == "월세"
    assert detect_trade_type({}, requested_trade_type="전세") == "전세"


def test_monthly_price_split() -> None:
    sale, deposit, monthly = normalize_price_fields(
        {"dealOrWarrantPrc": "월세 5억/200", "rentPrc": "200"}, "월세"
    )
    assert (sale, deposit, monthly) == ("", "5억", "200")


def test_normalize_article_payload_full_schema() -> None:
    row = normalize_article_payload(
        {
            "articleNo": "123",
            "tradeTypeName": "전세",
            "dealOrWarrantPrc": "10억",
            "area1": 84,
            "floorInfo": "12/25",
            "direction": "남향",
            "realtorName": "테스트공인",
            "realEstateTypeCode": "APT",
        },
        "테스트아파트",
        "99999",
        requested_trade_type="전세",
    )
    assert row["매물ID"] == "123"
    assert row["보증금"] == "10억"
    assert row["면적(평)"] == AreaConverter.sqm_to_pyeong(84)
    assert row["평당가"] > 0 and row["평당가_표시"].endswith("/평")
    assert row["부동산상호"] == "테스트공인"
    assert row["갭금액(원)"] == 0


def test_gap_enrichment_only_for_sale_with_prev_jeonse() -> None:
    sale = enrich_gap_fields({"거래유형": "매매", "매매가": "10억", "기전세금(원)": 800_000_000})
    assert sale["갭금액(원)"] == 200_000_000
    jeonse = enrich_gap_fields({"거래유형": "전세", "보증금": "10억"})
    assert jeonse["갭금액(원)"] == 0 and jeonse["갭비율"] == 0.0


def test_retry_handler_recovers_and_cancels() -> None:
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise ConnectionError("connection reset")
        return "ok"

    assert RetryHandler(max_retries=2, base_delay=0.1).execute_with_retry(flaky) == "ok"
    assert NetworkErrorHandler.is_recoverable(ConnectionError("x")) is True

    def cancelled() -> bool:
        return True

    try:
        RetryHandler(max_retries=2, base_delay=0.1).execute_with_retry(flaky, cancel_checker=cancelled)
    except RetryCancelledError:
        pass
    else:
        raise AssertionError("expected RetryCancelledError")


def test_article_lookup_extract_and_resolve_with_fake_fetcher() -> None:
    cid, asset = extract_article_complex_info(
        '<a href="https://new.land.naver.com/complexes/1147">리센츠</a> 아파트', fallback_asset_type="APT"
    )
    assert cid == "1147" and asset == "APT"
    assert detect_article_asset_type("빌라 매물입니다") == "VL"

    def fake_fetch(url: str) -> str:
        assert "m.land.naver.com" in url or "fin.land.naver.com" in url
        if url.startswith("https://fin.land.naver.com"):
            return "not found"
        return "complexNo=1147 아파트"

    resolved = resolve_article_complex("https://fin.land.naver.com/articles/27654321", fetcher=fake_fetch)
    assert resolved["complex_id"] == "1147"
    assert resolved["article_id"] == "27654321"


def test_site_contract_urls() -> None:
    assert build_complex_url("1147") == "https://new.land.naver.com/complexes/1147"
    assert build_complex_url("9999", asset_type="VL") == "https://new.land.naver.com/houses/9999"
    assert get_article_url("1147", "27654321") == "https://fin.land.naver.com/articles/27654321"
    assert build_complex_overview_url("9999", asset_type="VL").startswith("https://new.land.naver.com/api/houses/9999")
    assert build_complex_overview_url("1147").endswith("/1147")
