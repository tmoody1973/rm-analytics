"""
Q4 — Monthly device / platform backfill loader.

Target: wms.fact_monthly_device   PK (station_code, month_start, device_family, device, player)
Triton export cols: Station, Month, Device family, Device, Player, AAS, TLH, CUME, SS, TSL
('Device' holds concrete device names like "Amazon Echo", "iPhone", "Chromecast".)

CLI:   python loaders/load_q4_monthly_device.py exports/Q4_monthly_device_2024-01-01_to_2026-05-20.xlsx
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
    coerce_str,
    get_db_connection,
    parse_tsl,
    read_export,
    resolve_station,
)

QUERY_NAME = "Q4 Monthly device"
TABLE = "wms.fact_monthly_device"
EXPECTED_COLS = [
    "Station", "Month", "Device family", "Device", "Player",
    "AAS", "TLH", "CUME", "SS", "TSL",
]

COLUMNS = [
    "station_code", "month_start", "device_family", "device", "player",
    "aas", "tlh", "cume", "ss", "tsl_minutes",
]
CONFLICT_COLUMNS = ["station_code", "month_start", "device_family", "device", "player"]
UPDATE_COLUMNS = ["aas", "tlh", "cume", "ss", "tsl_minutes"]


def load(file_path: str) -> dict:
    """Load a Q4 monthly-device export into wms.fact_monthly_device. Returns stats."""
    start = time.time()

    df = read_export(file_path)
    assert_columns(df, EXPECTED_COLS, QUERY_NAME)

    rows: list[tuple] = []
    for rec in df.to_dict(orient="records"):
        rows.append(
            (
                resolve_station(rec["Station"]),
                pd.to_datetime(rec["Month"]).date(),
                coerce_str(rec["Device family"]),
                coerce_str(rec["Device"]),
                coerce_str(rec["Player"]),
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
