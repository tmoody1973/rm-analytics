"""Map a Triton subject tag to the loader that handles it.

All 6 Triton WMS queries are wired: Q1, Q2a, Q2b, Q2c, Q3, Q4.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Loaders import sibling helpers as `from _common import ...`, which only resolves
# if the loaders directory itself is on sys.path. We add it once at import time.
_LOADERS_DIR = Path(__file__).resolve().parent.parent / "loaders"
if str(_LOADERS_DIR) not in sys.path:
    sys.path.insert(0, str(_LOADERS_DIR))

import load_q1_hourly  # noqa: E402
import load_q2a_daily_cume  # noqa: E402
import load_q2b_weekly_cume  # noqa: E402
import load_q2c_monthly_cume  # noqa: E402
import load_q3_monthly_geo  # noqa: E402
import load_q4_monthly_device  # noqa: E402


@dataclass(frozen=True)
class Route:
    tag: str
    loader: Callable[[str], dict]
    query_name: str


_ROUTES: dict[str, Route] = {
    "[WMS-Q1-HOURLY]": Route(
        tag="[WMS-Q1-HOURLY]",
        loader=load_q1_hourly.load,
        query_name="Q1 Hourly",
    ),
    "[WMS-Q2A-CUME-DAILY]": Route(
        tag="[WMS-Q2A-CUME-DAILY]",
        loader=load_q2a_daily_cume.load,
        query_name="Q2a Daily cume",
    ),
    "[WMS-Q2B-CUME-WEEKLY]": Route(
        tag="[WMS-Q2B-CUME-WEEKLY]",
        loader=load_q2b_weekly_cume.load,
        query_name="Q2b Weekly cume",
    ),
    "[WMS-Q2C-CUME-MONTHLY]": Route(
        tag="[WMS-Q2C-CUME-MONTHLY]",
        loader=load_q2c_monthly_cume.load,
        query_name="Q2c Monthly cume",
    ),
    "[WMS-Q3-GEO]": Route(
        tag="[WMS-Q3-GEO]",
        loader=load_q3_monthly_geo.load,
        query_name="Q3 Monthly geography",
    ),
    "[WMS-Q4-DEVICE]": Route(
        tag="[WMS-Q4-DEVICE]",
        loader=load_q4_monthly_device.load,
        query_name="Q4 Monthly device",
    ),
}

_TAG_RE = re.compile(r"WMS-[A-Z0-9-]+")


def find_tag(subject: str) -> str | None:
    """Return the canonical [WMS-...] tag from a subject line, or None.

    Lenient about brackets and prefixes — Gmail forwarding strips the
    brackets and prepends "Fwd: " when a Triton report is auto-forwarded,
    so we match the raw tag string anywhere in the subject and rebuild the
    bracketed form ourselves before looking it up in _ROUTES.
    """
    if not subject:
        return None
    match = _TAG_RE.search(subject)
    if match is None:
        return None
    return f"[{match.group(0).rstrip('-')}]"


def resolve(subject: str) -> Route | None:
    tag = find_tag(subject)
    if tag is None:
        return None
    return _ROUTES.get(tag)


def known_tags() -> list[str]:
    return sorted(_ROUTES)
