"""Natural-language resolution regression tests (offline, no network).

Covers the unresolved-hint path in scripts/search_real_estate.py:
a reference seed without a verified complex_id must still be recognized
and surfaced with actionable guidance instead of a bare SearchError.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from search_real_estate import (
    build_unresolved_error,
    describe_unresolved_hints,
    search_reference_candidates,
)


def test_reference_hint_recognized_without_complex_id() -> None:
    rows = search_reference_candidates("답십리두산위브아파트 매매", candidate_limit=3)
    assert rows, "expected the 답십리두산위브 reference hint"
    top = rows[0]
    assert "답십리두산위브" in str(top.get("name") or "")
    assert top.get("complex_id") in ("", None)
    assert "답십리" in str(top.get("address") or "")


def test_describe_unresolved_hints_is_offline_and_actionable() -> None:
    hints = describe_unresolved_hints("답십리두산위브 매매")
    assert hints, "expected at least one unresolved hint"
    assert all(not str(item.get("complex_id") or "").strip() for item in hints)
    assert "답십리두산위브" in str(hints[0].get("name") or "")
    names = [str(item.get("name") or "") for item in hints]
    assert len(set(names)) == len(names), "duplicate hint rows must be collapsed"


def test_describe_unresolved_hints_empty_query() -> None:
    assert describe_unresolved_hints("") == []
    assert describe_unresolved_hints(None) == []


def test_unresolved_error_names_recognized_candidate() -> None:
    message = build_unresolved_error("답십리두산위브 매매")
    assert "단지 ID를 찾지 못했습니다." in message
    assert "답십리두산위브" in message
    assert "다음 행동:" in message


def test_unresolved_error_without_hint_keeps_base_message() -> None:
    message = build_unresolved_error("zzz없는단지qqq")
    assert message == "단지 ID를 찾지 못했습니다. 더 구체적인 단지명/지역명을 주거나 단지 URL/ID를 직접 넣어 주세요."
