"""Article -> complex reverse lookup ported from scrapper article_lookup."""

from __future__ import annotations

import re
import urllib.request
from html import unescape

from naver_collect.site_contract import HOST_FIN, HOST_M, normalize_asset_type

COMPLEX_URL_RE = re.compile(r"new\.land\.naver\.com/(?:complexes|houses)/(\d+)", re.IGNORECASE)
COMPLEX_NO_RE = re.compile(r"complexNo[\"'=: ]+(\d{3,10})", re.IGNORECASE)
COMPLEX_JSON_RE = re.compile(r"\"complex(?:No|Id)\"?\s*[:=]\s*\"?(\d{3,10})\"?", re.IGNORECASE)
ARTICLE_TYPE_CODE_RE = re.compile(r"\b(APT|VL|ABYG|JGC|DDDGG|JWJT|SGJT|HOJT|JT|OR)\b")
VL_HINTS = ("빌라", "연립", "다세대", "주택")
APT_HINTS = ("아파트", "APT")


def article_lookup_urls(article_id: str) -> tuple[tuple[str, str], ...]:
    aid = str(article_id or "").strip()
    if not aid:
        return ()
    return (
        ("fin_article", f"{HOST_FIN}/articles/{aid}"),
        ("m_info", f"{HOST_M}/article/info/{aid}"),
        ("m_view", f"{HOST_M}/article/view/{aid}"),
    )


def _fetch_url(url: str, timeout: float = 10.0) -> str:
    req = urllib.request.Request(str(url or ""))
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    req.add_header("Accept", "text/html,application/json;q=0.9,*/*;q=0.8")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def _normalize_asset_token(token: str) -> str:
    value = str(token or "").strip().upper()
    if value in {"APT", "ABYG", "JGC"}:
        return "APT"
    if value in {"VL", "DDDGG", "JWJT", "SGJT", "HOJT", "JT", "OR"}:
        return "VL"
    return ""


def detect_article_asset_type(text: str, fallback: str = "APT") -> str:
    corpus = str(text or "")
    for match in ARTICLE_TYPE_CODE_RE.finditer(corpus):
        detected = _normalize_asset_token(match.group(1))
        if detected:
            return detected
    if "/houses/" in corpus.lower():
        return "VL"
    if any(token in corpus for token in VL_HINTS):
        return "VL"
    if any(token in corpus for token in APT_HINTS):
        return "APT"
    return normalize_asset_type(fallback)


def extract_article_complex_info(body_text: str, fallback_asset_type: str = "APT") -> tuple[str, str]:
    corpus = unescape(str(body_text or "")).replace("\\/", "/")
    detected_asset = detect_article_asset_type(corpus, fallback=fallback_asset_type)
    for pattern in (COMPLEX_URL_RE, COMPLEX_NO_RE, COMPLEX_JSON_RE):
        match = pattern.search(corpus)
        if match:
            cid = str(match.group(1) or "").strip()
            if cid:
                asset = detected_asset or normalize_asset_type(fallback_asset_type)
                if "/houses/" in match.group(0).lower() and asset == "APT" and "빌라" in corpus:
                    asset = "VL"
                return cid, asset
    return "", normalize_asset_type(detected_asset or fallback_asset_type)


def resolve_article_complex(
    article_id: str,
    *,
    fallback_asset_type: str = "APT",
    fetcher: object = None,
) -> dict[str, str]:
    """매물 ID/URL에서 단지 ID와 자산유형을 역조회한다."""
    aid_match = re.search(r"(\d{5,12})", str(article_id or ""))
    aid = aid_match.group(1) if aid_match else str(article_id or "").strip()
    if not aid:
        return {}
    fetch = fetcher if callable(fetcher) else _fetch_url
    for source, url in article_lookup_urls(aid):
        try:
            body = fetch(url)  # type: ignore[operator]
        except Exception:  # noqa: BLE001, S112 - lookup probes next mirror on any fetch failure
            continue
        cid, asset_type = extract_article_complex_info(str(body or ""), fallback_asset_type=fallback_asset_type)
        if cid:
            return {"source": source, "complex_id": cid, "asset_type": asset_type, "article_id": aid, "url": url}
    return {}
