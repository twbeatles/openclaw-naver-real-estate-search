"""Site contract ported from scrapper ``src/core/services/site_contract.py``."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

HOST_NEW = "https://new.land.naver.com"
HOST_FIN = "https://fin.land.naver.com"
HOST_M = "https://m.land.naver.com"

ARTICLE_API_PREFIX = f"{HOST_NEW}/api/articles"
COMPLEX_OVERVIEW_API = f"{HOST_NEW}/api/complexes/overview"
SINGLE_MARKERS_COMPLEX = f"{HOST_NEW}/api/complexes/single-markers/2.0"
SINGLE_MARKERS_HOUSE = f"{HOST_NEW}/api/houses/single-markers/2.0"

FRONT_API_AGENT = f"{HOST_FIN}/front-api/v1/article/agent"
FRONT_API_BASIC_INFO = f"{HOST_FIN}/front-api/v1/article/basicInfo"
FRONT_API_MAINTENANCE = f"{HOST_FIN}/front-api/v1/article/maintenanceFee"

GEO_QUERY_ASSET = "a"
GEO_QUERY_TRADE = "b"
GEO_QUERY_PRICE_TYPE = "e"
GEO_QUERY_MS = "ms"

_TRADE_NAME_TO_CODE: dict[str, str] = {"매매": "A1", "전세": "B1", "월세": "B2"}


def normalize_asset_type(asset_type: Any) -> str:
    token = str(asset_type or "APT").strip().upper()
    return token if token in {"APT", "VL"} else "APT"


def trade_type_to_code(trade_type: Any) -> str:
    return _TRADE_NAME_TO_CODE.get(str(trade_type or "").strip(), "A1")


def article_api_real_estate_type(path_asset: Any, *, include_pre: bool = False) -> str:
    asset = str(path_asset or "APT").strip().upper()
    if asset == "VL":
        return "VL:DDDGG:JWJT:SGJT"
    base = "APT:ABYG:JGC"
    if include_pre:
        return f"{base}:PRE"
    return base


def build_complex_page_url(
    cid: Any,
    *,
    base_kind: str = "complexes",
    path_asset: str = "APT",
    trade_type: str = "매매",
    lat: float | None = None,
    lon: float | None = None,
    zoom: int | None = None,
    include_pre: bool = False,
) -> str:
    complex_id = str(cid or "").strip()
    if not complex_id:
        return ""
    kind = "houses" if str(base_kind or "") in {"houses", "house"} or str(path_asset or "").upper() == "VL" else "complexes"
    params: dict[str, Any] = {
        GEO_QUERY_MS: f"{lat or 37.5},{lon or 127},{zoom or 16}",
        GEO_QUERY_ASSET: article_api_real_estate_type(path_asset, include_pre=include_pre),
        GEO_QUERY_TRADE: trade_type_to_code(trade_type),
        GEO_QUERY_PRICE_TYPE: "RETAIL",
    }
    return f"{HOST_NEW}/{kind}/{complex_id}?" + urlencode(params)


def build_complex_url(complex_id: Any, *, asset_type: str = "APT", preferred_family: str = "new") -> str:
    cid = str(complex_id or "").strip()
    if not cid:
        return ""
    family = str(preferred_family or "new").strip().lower()
    path = "houses" if normalize_asset_type(asset_type) == "VL" else "complexes"
    if family == "m":
        return f"{HOST_M}/{path}/{cid}"
    return f"{HOST_NEW}/{path}/{cid}"


def build_article_url(
    article_id: Any,
    *,
    complex_id: Any = None,
    asset_type: str = "APT",
    preferred_family: str = "fin",
) -> str:
    aid = str(article_id or "").strip()
    if not aid:
        return ""
    family = str(preferred_family or "fin").strip().lower()
    if family == "m":
        return f"{HOST_M}/article/info/{aid}"
    if family == "new":
        cid = str(complex_id or "").strip()
        if not cid:
            return ""
        path = "houses" if normalize_asset_type(asset_type) == "VL" else "complexes"
        return f"{HOST_NEW}/{path}/{cid}?articleId={aid}"
    return f"{HOST_FIN}/articles/{aid}"


def get_article_url(complex_id: Any, article_id: Any, asset_type: str = "APT") -> str:
    return build_article_url(article_id, complex_id=complex_id, asset_type=asset_type, preferred_family="fin")


def build_complex_overview_url(complex_id: Any, *, asset_type: str = "APT") -> str:
    cid = str(complex_id or "").strip()
    if str(asset_type or "").strip().upper() == "VL":
        return f"{HOST_NEW}/api/houses/{cid}?sameAddressGroup=false"
    return f"{COMPLEX_OVERVIEW_API}/{cid}"


def is_fin_html_dead_url(final_url: str, body_text: str = "") -> bool:
    url = str(final_url or "").lower()
    body = str(body_text or "")
    if "financial.pstatic.net/404" in url:
        return True
    if "페이지를 찾을 수 없습니다" in body and "fin.land" in url:
        return True
    return "요청하신 페이지를 찾을 수 없어요" in body
