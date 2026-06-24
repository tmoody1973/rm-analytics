"""
Generic Google Sheets -> Neon loader (finance, Nielsen, any manual sheet).

A "Sync to Neon" Apps Script button in each sheet POSTs a JSON payload

    {"dataset": "<name>", "rows": [{header: value, ...}, ...]}

to the rm-data-loader `/webhook/sheet` endpoint, which calls load(payload).
This keeps manually-maintained sheets out of Coupler (no paid account slot) while
reusing the same idempotent-upsert + Slack-alert plumbing as the Triton loaders.

`load()` is a pure function: load(payload: dict) -> dict (stats).

Each dataset maps to a target table + key columns in SHEET_DATASETS. The finance
and Nielsen specs are stubbed until the real sheet layouts (tabs/headers) are
confirmed — an unconfigured dataset raises a clear NotImplementedError rather than
guessing a column map.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from _common import bulk_upsert, get_db_connection


@dataclass(frozen=True)
class DatasetSpec:
    """Maps a sheet dataset to a Neon table and its upsert keys.

    `columns` is the target column order. `source_keys` is the matching sheet
    header for each column (defaults to the column names when they already match
    the headers). `conflict_columns` is the table's PK / unique key.
    """

    table: str
    columns: list[str]
    conflict_columns: list[str]
    source_keys: list[str] | None = None

    @property
    def keys(self) -> list[str]:
        return self.source_keys or self.columns

    @property
    def update_columns(self) -> list[str]:
        return [c for c in self.columns if c not in self.conflict_columns]


# Registry of supported sheet datasets.
# TODO: fill these in once the finance + Nielsen sheet layouts are confirmed.
#   "finance_revenue": DatasetSpec(
#       table="finance.fact_revenue_monthly",
#       columns=["month", "category", "station_code", "restricted_yn", "amount"],
#       conflict_columns=["month", "category", "station_code", "restricted_yn"],
#       source_keys=["Month", "Category", "Station", "Restricted", "Amount"],
#   ),
#   "nielsen_ratings": DatasetSpec(
#       table="nielsen.fact_ratings_monthly",
#       columns=["month", "station_code", "daypart", "cume", "aqh"],
#       conflict_columns=["month", "station_code", "daypart"],
#       source_keys=["Month", "Station", "Daypart", "Cume", "AQH"],
#   ),
SHEET_DATASETS: dict[str, DatasetSpec] = {}


def load(payload: dict) -> dict:
    """Upsert a sheet-sync payload into its mapped Neon table. Returns stats."""
    start = time.time()
    dataset = payload.get("dataset") or ""
    spec = SHEET_DATASETS.get(dataset)
    if spec is None:
        raise NotImplementedError(
            f"sheet dataset {dataset!r} is not configured yet; "
            f"known={sorted(SHEET_DATASETS)} — add a DatasetSpec once the layout is set"
        )

    rows_in = payload.get("rows") or []
    tuples = [tuple(r.get(k) for k in spec.keys) for r in rows_in]

    conn = get_db_connection()
    try:
        upserted = bulk_upsert(
            conn,
            spec.table,
            spec.columns,
            tuples,
            spec.conflict_columns,
            spec.update_columns,
        )
    finally:
        conn.close()

    return {
        "query": f"sheet:{dataset}",
        "table": spec.table,
        "rows_read": len(rows_in),
        "rows_upserted": upserted,
        "elapsed_sec": round(time.time() - start, 1),
    }
