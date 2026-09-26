"""Vendored naverland-scrapper collection algorithm.

stdlib-only port so this skill works without the optional upstream checkout.
Upstream sources (2026-08 live probes):

- ``src/core/services/site_contract.py``
- ``src/core/services/article_api.py``
- ``src/core/services/response_capture.py``
- ``src/core/services/gap_analysis.py``
- ``src/utils/helpers.py`` (converters)
- ``src/utils/error_handler.py`` + ``src/utils/retry_handler.py``
- ``src/core/parser_parts/article_lookup.py``
"""

from naver_collect.article_api import (
    DEFAULT_ARTICLE_API_PAGE_SIZE,
    MAX_ARTICLE_API_PAGES,
)
from naver_collect.article_lookup import resolve_article_complex
from naver_collect.response_capture import (
    detect_asset_type,
    detect_trade_type,
    normalize_article_payload,
    normalize_marker_payload,
    normalize_price_fields,
)
from naver_collect.retry import RetryCancelledError, RetryHandler
from naver_collect.site_contract import (
    HOST_FIN,
    HOST_M,
    HOST_NEW,
    article_api_real_estate_type,
    build_complex_overview_url,
    build_complex_page_url,
    is_fin_html_dead_url,
    trade_type_to_code,
)

__all__ = [
    "DEFAULT_ARTICLE_API_PAGE_SIZE",
    "HOST_FIN",
    "HOST_M",
    "HOST_NEW",
    "MAX_ARTICLE_API_PAGES",
    "RetryCancelledError",
    "RetryHandler",
    "article_api_real_estate_type",
    "build_complex_overview_url",
    "build_complex_page_url",
    "detect_asset_type",
    "detect_trade_type",
    "is_fin_html_dead_url",
    "normalize_article_payload",
    "normalize_marker_payload",
    "normalize_price_fields",
    "resolve_article_complex",
    "trade_type_to_code",
]
