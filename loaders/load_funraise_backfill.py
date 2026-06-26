"""
Funraise historical backfill loader (one-time, local).

Loads Funraise transaction CSV/XLSX exports into funraise.fact_transactions and
upserts donor geography into funraise.dim_supporters. Keyed on the Funraise `Id`
(transaction_id) / `Supporter Id`, so re-running or loading overlapping/duplicate
export windows is safe — every row upserts ON CONFLICT.

Column mapping confirmed against real exports 2026-06-25 (see
docs/funraise-export-checklist.md). PII: names/phone are never read; raw email is
not present in the export (so email_sha256 stays NULL). Donor geo (city/state/zip)
lives only in these files, so we capture it into dim_supporters here.

Not in the export (left NULL): fee, net, restricted, channel, refund amount/date,
gateway id. `Status == 'Refunded'` sets the `refunded` flag; `Form` is the
designation proxy; `Form Id` is the campaign_id.

CLI:
    python loaders/load_funraise_backfill.py exports/Funraise_exports/export-1.csv
    python loaders/load_funraise_backfill.py exports/Funraise_exports/*.csv
"""
from __future__ import annotations

import sys
import time
from datetime import datetime

import pandas as pd

from _common import bulk_upsert, get_db_connection


def _read_str(file_path: str) -> "pd.DataFrame":
    """Read a Funraise export with EVERYTHING as strings, blanks as ''.

    Critical: reading without dtype=str lets pandas coerce numeric-looking ID
    columns (Form Id, Recurring Id, Postal Code) to floats, producing '9577.0'
    and breaking downstream joins. Strings preserve the exact codes.
    """
    p = file_path.lower()
    if p.endswith(".csv"):
        return pd.read_csv(file_path, dtype=str, keep_default_na=False)
    return pd.read_excel(file_path, dtype=str).fillna("")

# --- fact_transactions -------------------------------------------------------
TXN_TABLE = "funraise.fact_transactions"
TXN_COLUMNS = [
    "transaction_id", "supporter_id", "campaign_id", "transaction_at",
    "transaction_date", "amount", "fee", "net", "currency", "payment_method",
    "recurring", "status", "utm_source", "utm_medium", "utm_campaign",
    "designation", "restricted", "fee_covered", "fee_covered_amount",
    "refunded", "refunded_amount", "refunded_at", "channel", "recurring_plan_id",
]
TXN_CONFLICT = ["transaction_id"]
TXN_UPDATE = [c for c in TXN_COLUMNS if c not in TXN_CONFLICT]

# --- dim_supporters (geo only; email/first_donation/lifetime filled elsewhere) ---
SUP_TABLE = "funraise.dim_supporters"
SUP_COLUMNS = ["supporter_id", "city", "state", "postal_code", "country"]
SUP_CONFLICT = ["supporter_id"]
SUP_UPDATE = [c for c in SUP_COLUMNS if c not in SUP_CONFLICT]


def _s(v: object) -> str | None:
    """Stripped string, or None if blank/NaN."""
    if v is None:
        return None
    t = str(v).strip()
    if t == "" or t.lower() == "nan":
        return None
    return t


def _num(v: object) -> float | None:
    """Money string -> float. Strips $ and commas. Blank -> None."""
    t = _s(v)
    if t is None:
        return None
    t = t.replace("$", "").replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _bool(v: object) -> bool | None:
    """'true'/'false' (or blank) -> bool/None."""
    t = _s(v)
    if t is None:
        return None
    return t.lower() in {"true", "1", "yes", "t"}


def _dt(v: object) -> datetime | None:
    """Funraise 'Transaction Date' -> aware datetime. Strips the trailing
    '[US/Central]' zone-name suffix that Python's ISO parser can't handle."""
    t = _s(v)
    if t is None:
        return None
    if "[" in t:
        t = t.split("[", 1)[0]
    t = t.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def _extract_txn(r: dict) -> tuple:
    when = _dt(r.get("Transaction Date"))
    status = _s(r.get("Status"))
    return (
        _s(r.get("Id")),
        _s(r.get("Supporter Id")),
        _s(r.get("Form Id")),
        when,
        when.date() if when else None,
        _num(r.get("Amount")),
        None,  # fee — not in export
        None,  # net — not in export
        _s(r.get("Currency")),
        _s(r.get("Payment Method")),
        _bool(r.get("Recurring")),
        status,
        _s(r.get("UTM Source")),
        _s(r.get("UTM Medium")),
        _s(r.get("UTM Campaign")),
        _s(r.get("Form")),                       # designation proxy
        None,                                    # restricted — not in export
        _bool(r.get("Donor Covered Fees")),
        _num(r.get("Donor Covered Fee Amount")),
        (status.lower() == "refunded") if status else None,
        None,  # refunded_amount — not in export
        None,  # refunded_at — not in export
        None,  # channel — not in export
        _s(r.get("Recurring Id")),
    )


def _extract_supporter(r: dict) -> tuple | None:
    sid = _s(r.get("Supporter Id"))
    if sid is None:
        return None
    return (sid, _s(r.get("City")), _s(r.get("State/Province")),
            _s(r.get("Postal Code")), _s(r.get("Country")))


def load(file_path: str) -> dict:
    """Load one Funraise export file. Upserts transactions + supporter geo."""
    start = time.time()
    df = _read_str(file_path)
    records = df.to_dict("records")

    txn_rows = [_extract_txn(r) for r in records]
    txn_rows = [t for t in txn_rows if t[0]]  # require a transaction_id

    # de-dupe supporters within the file (last row per supporter wins for geo)
    sup_map: dict[str, tuple] = {}
    for r in records:
        s = _extract_supporter(r)
        if s:
            sup_map[s[0]] = s
    sup_rows = list(sup_map.values())

    conn = get_db_connection()
    try:
        txn_n = bulk_upsert(conn, TXN_TABLE, TXN_COLUMNS, txn_rows, TXN_CONFLICT, TXN_UPDATE)
        sup_n = bulk_upsert(conn, SUP_TABLE, SUP_COLUMNS, sup_rows, SUP_CONFLICT, SUP_UPDATE)
    finally:
        conn.close()

    return {
        "file": file_path.split("/")[-1],
        "rows_read": len(records),
        "transactions_upserted": txn_n,
        "supporters_upserted": sup_n,
        "elapsed_sec": round(time.time() - start, 1),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python loaders/load_funraise_backfill.py FILE [FILE ...]")
    for path in sys.argv[1:]:
        print(load(path))
