"""
Finance KPI sheet loader.

The finance Google Sheet ("financial" tab) is a wide KPI dashboard: one row per
indicator (Revenue YTD - Cash, Expenses Actual YTD, Total donors YTD, ...) and one
column per month ("February 2026", "March 2026", ...). The Apps Script "Sync to
Neon" button POSTs it as

    {"dataset": "finance_kpi", "rows": [{<header>: <displayed value>, ...}, ...]}

using the sheet's *display* values (strings like "1,489,865.75", "36.67%",
"-37,701.35"). This loader **unpivots** that into long rows and upserts them into
finance.fact_kpi_monthly ON CONFLICT (month, indicator) DO UPDATE, so re-syncing
the same months is idempotent.

`load(payload: dict) -> dict` (stats), matching the other loaders.
"""
from __future__ import annotations

import time
from datetime import date, datetime

from _common import get_db_connection, bulk_upsert

TABLE = "finance.fact_kpi_monthly"
COLUMNS = ["month", "indicator", "value"]
CONFLICT_COLUMNS = ["month", "indicator"]
UPDATE_COLUMNS = ["value"]


def _parse_month(header: object) -> date | None:
    """Parse a column header like 'February 2026' to its first-of-month date.

    Returns None for headers that aren't a month (e.g. the indicator column),
    which is how we tell month columns apart from everything else.
    """
    text = str(header).strip()
    for fmt in ("%B %Y", "%b %Y", "%m/%Y", "%Y-%m"):
        try:
            return datetime.strptime(text, fmt).date().replace(day=1)
        except ValueError:
            continue
    return None


def _clean_number(raw: object) -> float | None:
    """Turn a displayed sheet value into a float, or None if blank/non-numeric.

    Strips thousands separators, currency, percent signs, and stray markdown
    escapes; '(123)' accounting-negatives become -123.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "":
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = s.replace(",", "").replace("$", "").replace("%", "").replace("\\", "").strip()
    if s in ("", "-", "—", "N/A", "n/a"):
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def _unpivot(rows: list[dict]) -> list[tuple]:
    """Wide indicator×month rows -> long (month, indicator, value) tuples."""
    out: list[tuple] = []
    for row in rows:
        month_cols = {k: _parse_month(k) for k in row}
        month_cols = {k: m for k, m in month_cols.items() if m is not None}
        # The indicator is the value under the first non-month column that has text.
        indicator = None
        for key in row:
            if key in month_cols:
                continue
            candidate = str(row.get(key) or "").strip()
            if candidate:
                indicator = candidate
                break
        if not indicator:
            continue
        for key, month in month_cols.items():
            value = _clean_number(row.get(key))
            if value is None:
                continue
            out.append((month, indicator, value))
    return out


def load(payload: dict) -> dict:
    """Unpivot a finance KPI sheet payload and upsert into Neon. Returns stats."""
    start = time.time()
    rows_in = payload.get("rows") or []
    tuples = _unpivot(rows_in)

    conn = get_db_connection()
    try:
        upserted = bulk_upsert(
            conn, TABLE, COLUMNS, tuples, CONFLICT_COLUMNS, UPDATE_COLUMNS
        )
    finally:
        conn.close()

    return {
        "query": "finance KPI sheet",
        "table": TABLE,
        "rows_read": len(rows_in),
        "rows_upserted": upserted,
        "elapsed_sec": round(time.time() - start, 1),
    }
