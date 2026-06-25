"""Pure brand/period -> SQL-filter helpers. No DB access, fully unit-testable.

Brand and period vocabularies match the dashboard front-end exactly so the
tabs, filters, and assistant share one language.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# Brand key -> station codes (streaming / Nielsen). ALL / None = no filter.
# RM is the merged flagship: RM88 (broadcast/streaming) + RMORG (digital).
BRAND_STATIONS: dict[str, list[str]] = {
    "RM": ["RM88", "RMORG"],
    "HYFIN": ["HYFIN"],
    "RM414": ["RM414"],
    "RLR": ["RLR"],
    "GWML": ["GWML"],
}

PERIOD_DAYS: dict[str, int] = {"30d": 30, "90d": 90, "12m": 365}


def station_codes_for(brand: str | None) -> list[str] | None:
    """Station codes for a brand key, or None for ALL/None. Raises on unknown."""
    if not brand or brand == "ALL":
        return None
    if brand not in BRAND_STATIONS:
        raise ValueError(f"unknown brand {brand!r}")
    return BRAND_STATIONS[brand]


def period_cutoff(period: str | None, today: date | None = None) -> date | None:
    """Inclusive lower-bound date for a period key, or None for all/None."""
    today = today or datetime.now(timezone.utc).date()
    if not period or period == "all":
        return None
    if period == "ytd":
        return date(today.year, 1, 1)
    if period in PERIOD_DAYS:
        return today - timedelta(days=PERIOD_DAYS[period])
    raise ValueError(f"unknown period {period!r}")
