"""Geo-assisted resolution tests (offline, no network).

Covers scripts/naver_collect/geo_markers.py pure helpers and the
search_geo_candidates pipeline in scripts/search_real_estate.py with
injected fakes (upstream geo-mode approach: geocode locality ->
single-markers viewport -> name match -> detail verify).
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import search_real_estate as sre
from naver_collect import geo_markers as gm

FIN_MAP_URL = (
    "https://fin.land.naver.com/map?center=3zkIqm-2AM2FA&zoom=14.43756398345512"
    "&tradeTypes=A1-B1&realEstateTypes=A01-A04-B01&layer=NobwRAlgJmBcYGMD2"
)


def test_viewport_bounds_contain_center() -> None:
    bounds = gm.viewport_bounds(37.57, 127.05, 14)
    assert bounds["leftLon"] < 127.05 < bounds["rightLon"]
    assert bounds["bottomLat"] < 37.57 < bounds["topLat"]
    assert bounds["leftLon"] < bounds["rightLon"]
    assert bounds["bottomLat"] < bounds["topLat"]


def test_single_markers_url_contract() -> None:
    url = gm.build_single_markers_url(
        asset_type="APT", trade_type="매매", zoom=14,
        left_lon=126.9, right_lon=127.1, top_lat=37.6, bottom_lat=37.5,
    )
    assert "single-markers/2.0" in url
    assert "tradeType=A1" in url
    assert "leftLon=126.9" in url and "bottomLat=37.5" in url
    assert "realEstateType=APT" in url
    vl_url = gm.build_single_markers_url(
        asset_type="VL", trade_type="월세", zoom=14,
        left_lon=126.9, right_lon=127.1, top_lat=37.6, bottom_lat=37.5,
    )
    assert "/api/houses/single-markers/2.0" in vl_url
    assert "tradeType=B2" in vl_url


def test_normalize_marker_row() -> None:
    row = gm.normalize_marker_row(
        {"complexNo": "12345", "complexName": "테스트위브",
         "latitude": 37.57, "longitude": 127.05, "articleCount": 7}
    )
    assert row["complex_id"] == "12345"
    assert row["name"] == "테스트위브"
    assert row["lat"] == 37.57 and row["count"] == 7
    house = gm.normalize_marker_row({"houseNo": "77", "houseName": "테스트빌라"})
    assert house["complex_id"] == "77"


def test_parse_fin_map_url() -> None:
    parsed = gm.parse_fin_map_url(FIN_MAP_URL)
    assert parsed["is_fin_map_url"] is True
    assert parsed["zoom"] == 14.43756398345512
    assert parsed["trade_codes"] == ["A1", "B1"]
    assert parsed["trade_types"] == ["매매", "전세"]
    assert gm.parse_fin_map_url("https://new.land.naver.com/complexes/1147")["is_fin_map_url"] is False


def test_geocode_place_uses_fetcher_and_caches() -> None:
    gm.clear_geocode_cache()
    calls: list[str] = []

    def fake(place: str) -> tuple[float, float] | None:
        calls.append(place)
        return (37.1, 127.1)

    assert gm.geocode_place("어딘가", fetcher=fake) == (37.1, 127.1)
    assert gm.geocode_place("어딘가", fetcher=fake) == (37.1, 127.1)
    assert len(calls) == 1
    assert gm.geocode_place("", fetcher=fake) is None

    def boom(place: str) -> tuple[float, float] | None:
        raise RuntimeError("offline")

    assert gm.geocode_place("다른곳", fetcher=boom) is None


def test_build_geo_anchor_prefers_seed_locality() -> None:
    anchor = sre.build_geo_anchor(sre.parse_natural_query("답십리두산위브 매매"))
    assert anchor == ("답십리두산위브", "서울특별시 동대문구 답십리동, 대한민국")


def test_build_geo_anchor_falls_back_to_location_hints() -> None:
    anchor = sre.build_geo_anchor(sre.parse_natural_query("서울 동대문구 답십리동 없는단지xyz 매매"))
    assert anchor is not None
    assert "답십리동" in anchor[1]
    assert sre.build_geo_anchor(sre.parse_natural_query("zzz없는단지qqq")) is None
    assert sre.build_geo_anchor(None) is None


def test_marker_name_ok() -> None:
    assert sre._marker_name_ok("답십리두산위브", "답십리두산위브아파트") is True
    assert sre._marker_name_ok("답십리두산위브아파트", "답십리두산위브") is True
    assert sre._marker_name_ok("답십리두산위브", "리센츠") is False
    assert sre._marker_name_ok("", "리센츠") is False


def _patch_geo_success(monkeypatch, detail_name="답십리두산위브아파트") -> None:
    sre.RATE_LIMIT_STATE["active"] = False
    gm.clear_geocode_cache()
    monkeypatch.setattr(gm, "geocode_place", lambda place: (37.57002, 127.05467))

    def fake_markers(url: str, backoffs=None):  # noqa: ANN001, ANN202
        assert "single-markers/2.0" in url
        return [
            {"complexNo": "99991", "complexName": "답십리두산위브아파트",
             "latitude": 37.57, "longitude": 127.05, "articleCount": 5},
            {"complexNo": "99992", "complexName": "전농삼성아파트",
             "latitude": 37.57, "longitude": 127.06, "articleCount": 3},
        ]

    monkeypatch.setattr(sre, "_request_json", fake_markers)

    def fake_detail(cid: str, asset_type: str = "APT"):  # noqa: ANN001, ANN202
        assert cid == "99991"
        return {"complex_id": "99991", "name": detail_name,
                "address": "서울특별시 동대문구 답십리동",
                "household_count": 1000,
                "complex_url": "https://new.land.naver.com/complexes/99991"}

    monkeypatch.setattr(sre, "fetch_complex_info", fake_detail)


def test_search_geo_candidates_resolves_verified_id(monkeypatch) -> None:
    _patch_geo_success(monkeypatch)
    rows = sre.search_geo_candidates("답십리두산위브 매매", candidate_limit=3)
    assert rows and rows[0]["complex_id"] == "99991"
    assert rows[0]["source"] == "geo-markers"
    assert rows[0]["complex_url"].endswith("/99991")


def test_search_geo_candidates_drops_name_mismatch(monkeypatch) -> None:
    _patch_geo_success(monkeypatch, detail_name="리센츠")
    assert sre.search_geo_candidates("답십리두산위브 매매", candidate_limit=3) == []


def test_search_geo_candidates_rate_limited_returns_empty(monkeypatch) -> None:
    sre.RATE_LIMIT_STATE["active"] = False
    gm.clear_geocode_cache()
    monkeypatch.setattr(gm, "geocode_place", lambda place: (37.57002, 127.05467))

    def limited(url: str, backoffs=None):  # noqa: ANN001, ANN202
        raise sre.SearchError("429")

    monkeypatch.setattr(sre, "_request_json", limited)
    try:
        assert sre.search_geo_candidates("답십리두산위브 매매", candidate_limit=3) == []
    finally:
        sre.RATE_LIMIT_STATE["active"] = False

