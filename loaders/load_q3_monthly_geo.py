"""
Q3 — Monthly geography backfill loader.

Target: wms.fact_monthly_geo   PK (station_code, month_start, city, dma)
Triton export cols: Station, Month, City, DMA, AAS, TLH, CUME, SS, TSL

CLI:   python loaders/load_q3_monthly_geo.py exports/Q3_monthly_geo_2024-01-01_to_2026-05-20.xlsx
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
    resolve_station,
)

QUERY_NAME = "Q3 Monthly geography"
TABLE = "wms.fact_monthly_geo"
EXPECTED_COLS = ["Station", "Month", "City", "DMA", "AAS", "TLH", "CUME", "SS", "TSL"]

COLUMNS = [
    "station_code", "month_start", "city", "dma",
    "aas", "tlh", "cume", "ss", "tsl_minutes",
]
CONFLICT_COLUMNS = ["station_code", "month_start", "city", "dma"]
UPDATE_COLUMNS = ["aas", "tlh", "cume", "ss", "tsl_minutes"]


def load(file_path: str) -> dict:
    """Load a Q3 monthly-geo export into wms.fact_monthly_geo. Returns stats."""
    start = time.time()

    df = pd.read_excel(file_path)
    assert_columns(df, EXPECTED_COLS, QUERY_NAME)

    rows: list[tuple] = []
    for rec in df.to_dict(orient="records"):
        rows.append(
            (
                resolve_station(rec["Station"]),
                pd.to_datetime(rec["Month"]).date(),
                coerce_str(rec["City"]),
                coerce_str(rec["DMA"]),
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
