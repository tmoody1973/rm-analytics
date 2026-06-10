"""
Q1 — Hourly listening backfill loader.

Target: wms.fact_hourly_listening   PK (station_code, date, hour)
Triton export cols: Station, Date Hour, AAS, TLH, CUME, SS, TSL
"Date Hour" ("YYYY-MM-DD HH:MM:SS") is split into date + hour.

This is the reference loader — the other five follow the same shape.

CLI:   python loaders/load_q1_hourly.py exports/Q1_hourly_2024-01-01_2026-05-16.xlsx
"""
from __future__ import annotations

import sys
import time

import pandas as pd

from _common import (
    assert_columns,
    bulk_upsert,
    coerce_float,
    coerce_int,
    get_db_connection,
    parse_tsl,
    read_export,
    resolve_station,
)

QUERY_NAME = "Q1 Hourly"
TABLE = "wms.fact_hourly_listening"
EXPECTED_COLS = ["Station", "Date Hour", "AAS", "TLH", "CUME", "SS", "TSL"]

# DB column order used for the upsert.
COLUMNS = ["station_code", "date", "hour", "aas", "tlh", "cume", "ss", "tsl_minutes"]
CONFLICT_COLUMNS = ["station_code", "date", "hour"]
# Everything except the PK gets refreshed on conflict (re-running a fixed export wins).
UPDATE_COLUMNS = ["aas", "tlh", "cume", "ss", "tsl_minutes"]


def load(file_path: str) -> dict:
    """Load a Q1 hourly export into wms.fact_hourly_listening. Returns stats."""
    start = time.time()

    df = read_export(file_path)
    assert_columns(df, EXPECTED_COLS, QUERY_NAME)

    rows: list[tuple] = []
    for rec in df.to_dict(orient="records"):
        dt = pd.to_datetime(rec["Date Hour"])
        rows.append(
            (
                resolve_station(rec["Station"]),
                dt.date(),
                int(dt.hour),
                coerce_float(rec["AAS"]),
                coerce_float(rec["TLH"]),
                coerce_float(rec["CUME"]),
                coerce_int(rec["SS"]),
                parse_tsl(rec["TSL"]),
            )
        )

    conn = get_db_connection()
    try:
        upserted = bulk_upsert(
            conn, TABLE, COLUMNS, rows, CONFLICT_COLUMNS, UPDATE_COLUMNS
        )
    finally:
        conn.close()

    elapsed = round(time.time() - start, 1)
    return {
        "query": QUERY_NAME,
        "table": TABLE,
        "rows_read": len(df),
        "rows_upserted": upserted,
        "elapsed_sec": elapsed,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: python {sys.argv[0]} <export.xlsx>")
        sys.exit(1)
    stats = load(sys.argv[1])
    print(
        f"[{stats['query']}] upserted {stats['rows_upserted']} rows into "
        f"{stats['table']} in {stats['elapsed_sec']}s (read {stats['rows_read']})"
    )
