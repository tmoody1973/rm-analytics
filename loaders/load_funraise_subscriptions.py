"""
Funraise subscriptions (recurring plans) loader — one-time / periodic.

Loads the Funraise Subscriptions export into funraise.fact_subscriptions, keyed on
Subscription Id (idempotent upsert). Re-run anytime to true up statuses (Active /
Cancelled / Failed / Redacted) — there's no cancel-date column in the export, so
churn is read from Status, and `canceled_at` is left NULL.

PRIVACY / SECURITY: we map an explicit allowlist of columns only. Supporter name,
email, soft-credit name, card last-four, and the payment/third-party TOKENS in the
export are never read or stored (PCI + PII).

CLI:  python loaders/load_funraise_subscriptions.py exports/.../subscriptions.csv
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from _common import bulk_upsert, get_db_connection

CENTRAL = ZoneInfo("America/Chicago")

TABLE = "funraise.fact_subscriptions"
COLUMNS = [
    "subscription_id", "supporter_id", "campaign_id", "amount",
    "frequency", "status", "started_at", "canceled_at",
]
CONFLICT = ["subscription_id"]
UPDATE = [c for c in COLUMNS if c not in CONFLICT]


def _read_str(path: str) -> "pd.DataFrame":
    if path.lower().endswith(".csv"):
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return pd.read_excel(path, dtype=str).fillna("")


def _s(v: object) -> str | None:
    if v is None:
        return None
    t = str(v).strip()
    return t or None


def _num(v: object) -> float | None:
    t = _s(v)
    if t is None:
        return None
    t = t.replace("$", "").replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _date(v: object):
    """ISO timestamp (with optional '[US/Central]' suffix) -> Central calendar date."""
    t = _s(v)
    if t is None:
        return None
    if "[" in t:
        t = t.split("[", 1)[0]
    t = t.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(t).astimezone(CENTRAL).date()
    except ValueError:
        return None


def _extract(r: dict) -> tuple:
    return (
        _s(r.get("Subscription Id")),
        _s(r.get("Supporter ID")),
        _s(r.get("Giving Form ID")),       # campaign_id (matches transaction mapping)
        _num(r.get("Recurring Amount")),
        _s(r.get("Frequency")),
        _s(r.get("Status")),
        _date(r.get("Created Date")),       # started_at
        None,                               # canceled_at — no cancel-date column in export
    )


def load(file_path: str) -> dict:
    start = time.time()
    df = _read_str(file_path)
    rows = [_extract(r) for r in df.to_dict("records")]
    rows = [t for t in rows if t[0]]  # require subscription_id

    conn = get_db_connection()
    try:
        n = bulk_upsert(conn, TABLE, COLUMNS, rows, CONFLICT, UPDATE)
    finally:
        conn.close()

    return {
        "file": file_path.split("/")[-1],
        "rows_read": len(df),
        "subscriptions_upserted": n,
        "elapsed_sec": round(time.time() - start, 1),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python loaders/load_funraise_subscriptions.py FILE [FILE ...]")
    for path in sys.argv[1:]:
        print(load(path))
