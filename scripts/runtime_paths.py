"""Resolve the skill root and optional naverland-scrapper dependency.

The skill runs both from an OpenClaw workspace (``workspace/skills/...``)
and directly from a checked-out repository.  Do not rely on a fixed number of
parent directories: that made the repository checkout look for ``D:\\tmp``.
"""

from __future__ import annotations

import os
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def workspace_root() -> Path:
    """Return the OpenClaw workspace when installed, otherwise the skill root."""
    if SKILL_ROOT.parent.name == "skills":
        return SKILL_ROOT.parent.parent
    return SKILL_ROOT


WORKSPACE = workspace_root()


def resolve_upstream() -> Path:
    """Find a usable local naverland-scrapper checkout without hard-coding a drive."""
    configured = os.environ.get("NAVERLAND_SCRAPPER_PATH", "").strip()
    candidates = [
        Path(configured) if configured else None,
        WORKSPACE / "tmp" / "naverland-scrapper",
        SKILL_ROOT.parent / "naverland-scrapper",
        SKILL_ROOT.parent.parent / "naverland-scrapper",
    ]
    for candidate in candidates:
        if candidate and (candidate / "src" / "core" / "parser.py").is_file():
            return candidate
    # Keep a deterministic diagnostic path even when the optional checkout is absent.
    return WORKSPACE / "tmp" / "naverland-scrapper"


UPSTREAM = resolve_upstream()

