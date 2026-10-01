"""Geo-assisted complex lookup (single-markers API).

Approach ported from upstream ``naverland-scrapper`` geo mode
(``map_geometry`` viewport math + ``single-markers/2.0`` contract):
a place name is geocoded to coordinates, the surrounding viewport is
queried for complex markers, and marker names are matched against the
natural-language query. All network access is best-effort and isolated
behind injectable fetchers so unit tests stay offline.
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from typing import Any, Callable

from .site_contract import article_api_real_estate_type, trade_type_to_code

KOR_BOUNDS = (33.0, 39.5, 124.0, 132.1)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search?format=json&limit=1&q={query}"
NOMINATIM_USER_AGENT = "naver-real-estate-search-skill/1.0 (contact: local-diagnostic)"
FIN_TRADE_CODE_TO_NAME = {"A1": "매매", "B1": "전세", "B2": "월세"}

_geo_cache: dict[str, tuple[float, float] | None] = {}


def clamp_korea(lat: float, lon: float) -> tuple[float, float]:
    mn_lat, mx_lat, mn_lon, mx_lon = KOR_BOUNDS
    return max(mn_lat, min(float(lat), mx_lat)), max(mn_lon, min(float(lon), mx_lon))


def viewport_bounds(
    lat: float,
    lon: float,
    zoom: int,
    *,
    width_px: int = 1600,
    height_px: int = 900,
) -> dict[str, float]:
    """Approximate map viewport WGS84 bounds for the single-markers API."""
    scale = 256 * (2 ** int(zoom or 14))
    x = (float(lon) + 180.0) / 360.0 * scale
    siny = math.sin(math.radians(float(lat)))
    siny = min(0.9999, max(-0.9999, siny))
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * scale
    half_w = max(100, int(width_px or 1600)) / 2.0
    half_h = max(100, int(height_px or 900)) / 2.0

    def _px(pxx: float, pyy: float) -> tuple[float, float]:
        lo = pxx / scale * 360.0 - 180.0
        n = math.pi - 2.0 * math.pi * pyy / scale
        la = math.degrees(math.atan(math.sinh(n)))
        return la, lo

    top_lat, left_lon = _px(x - half_w, y - half_h)
    bottom_lat, right_lon = _px(x + half_w, y + half_h)
    north = max(top_lat, bottom_lat)
    south = min(top_lat, bottom_lat)
    west = min(left_lon, right_lon)
    east = max(left_lon, right_lon)
    mid_lon = (west + east) / 2.0
    mid_lat = (north + south) / 2.0
    north, _ = clamp_korea(north, mid_lon)
    south, _ = clamp_korea(south, mid_lon)
    _, west = clamp_korea(mid_lat, west)
    _, east = clamp_korea(mid_lat, east)
    return {
        "leftLon": float(west),
        "rightLon": float(east),
        "topLat": float(north),
        "bottomLat": float(south),
    }


def build_single_markers_url(
    *,
    asset_type: str = "APT",
    trade_type: str = "매매",
    zoom: int = 14,
    left_lon: float,
    right_lon: float,
    top_lat: float,
    bottom_lat: float,
) -> str:
    """Build complexes/houses single-markers/2.0 URL (upstream contract)."""
    is_vl = str(asset_type or "").strip().upper() == "VL"
    base = (
        "https://new.land.naver.com/api/houses/single-markers/2.0"
        if is_vl
        else "https://new.land.naver.com/api/complexes/single-markers/2.0"
    )
    params = {
        "zoom": str(int(zoom or 14)),
        "priceType": "RETAIL",
        "markerId": "",
        "markerType": "",
        "selectedComplexNo": "",
        "selectedComplexBuildingNo": "",
        "fakeComplexMarker": "",
        "realEstateType": article_api_real_estate_type(asset_type),
        "tradeType": trade_type_to_code(trade_type),
        "tag": "::::::::",
        "rentPriceMin": "0",
        "rentPriceMax": "900000000",
        "priceMin": "0",
        "priceMax": "900000000",
        "areaMin": "0",
        "areaMax": "900000000",
        "showArticle": "false",
        "sameAddressGroup": "false",
        "directions": "",
        "leftLon": str(left_lon),
        "rightLon": str(right_lon),
        "topLat": str(top_lat),
        "bottomLat": str(bottom_lat),
    }
    return f"{base}?" + urllib.parse.urlencode(params)


def normalize_marker_row(marker: dict[str, Any], asset_type: str = "APT") -> dict[str, Any]:
    """Normalize one single-markers payload row (upstream marker contract)."""
    cid = str(marker.get("complexNo") or marker.get("houseNo") or "").strip()
    marker_id = str(marker.get("markerId") or "").strip()
    if not cid:
        cid = marker_id
    if not marker_id:
        marker_id = cid
    name = str(marker.get("complexName") or marker.get("houseName") or "").strip()
    try:
        lat = float(marker.get("latitude") or marker.get("lat") or 0.0)
    except (TypeError, ValueError):
        lat = 0.0
    try:
        lon = float(marker.get("longitude") or marker.get("lon") or marker.get("lng") or 0.0)
    except (TypeError, ValueError):
        lon = 0.0
    try:
        count = int(marker.get("articleCount") or marker.get("dealCount") or marker.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    return {
        "complex_id": cid,
        "name": name or f"단지_{cid}",
        "asset_type": str(asset_type or "APT").strip().upper() or "APT",
        "marker_id": marker_id,
        "count": count,
        "lat": lat,
        "lon": lon,
    }


def parse_fin_map_url(url: str) -> dict[str, Any]:
    """Extract usable hints from a fin.land map share URL.

    ``center=`` is an opaque Naver encoding (not decoded); ``zoom`` and
    ``tradeTypes`` (A1/B1/B2) are returned for filter/viewport reuse.
    """
    result: dict[str, Any] = {
        "is_fin_map_url": False,
        "zoom": None,
        "trade_codes": [],
        "trade_types": [],
        "real_estate_types": [],
        "center": None,
    }
    text = str(url or "")
    if "fin.land.naver.com/map" not in text:
        return result
    result["is_fin_map_url"] = True
    try:
        query = urllib.parse.urlparse(text).query
    except ValueError:
        return result
    params = urllib.parse.parse_qs(query)
    zoom_raw = (params.get("zoom") or [""])[0]
    try:
        result["zoom"] = float(zoom_raw)
    except (TypeError, ValueError):
        result["zoom"] = None
    center_raw = (params.get("center") or [""])[0]
    result["center"] = center_raw.strip() or None
    codes = [token.strip().upper() for token in (params.get("tradeTypes") or [""])[0].split("-") if token.strip()]
    result["trade_codes"] = codes
    result["trade_types"] = [FIN_TRADE_CODE_TO_NAME[c] for c in codes if c in FIN_TRADE_CODE_TO_NAME]
    estate_raw = (params.get("realEstateTypes") or [""])[0]
    result["real_estate_types"] = [token.strip() for token in estate_raw.split("-") if token.strip()]
    return result


def _nominatim_fetch(place: str) -> tuple[float, float] | None:
    req = urllib.request.Request(
        NOMINATIM_URL.format(query=urllib.parse.quote(place)),
        headers={"User-Agent": NOMINATIM_USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        rows = json.loads(response.read().decode("utf-8"))
    if not rows:
        return None
    return float(rows[0]["lat"]), float(rows[0]["lon"])


def geocode_place(
    place: str,
    *,
    fetcher: Callable[[str], tuple[float, float] | None] | None = None,
    pace_seconds: float = 0.0,
) -> tuple[float, float] | None:
    """Best-effort place -> (lat, lon). Never raises; caches per process."""
    key = str(place or "").strip()
    if not key:
        return None
    if key in _geo_cache:
        return _geo_cache[key]
    try:
        coords = (fetcher or _nominatim_fetch)(key)
        if coords is not None:
            coords = (float(coords[0]), float(coords[1]))
    except Exception:
        coords = None
    _geo_cache[key] = coords
    if pace_seconds > 0:
        time.sleep(pace_seconds)
    return coords


def clear_geocode_cache() -> None:
    _geo_cache.clear()
