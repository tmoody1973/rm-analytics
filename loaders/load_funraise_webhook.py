"""
Funraise transaction webhook loader.

The Funraise transaction webhook fires on transaction create OR edit. This loader
upserts each transaction into funraise.fact_transactions ON CONFLICT (transaction_id)
DO UPDATE, so re-fires (edits, retries) are idempotent.

`load(payload: dict) -> dict` where payload is the parsed Funraise webhook body.

TODO: confirm the real Funraise payload field names against a sample event and
finalize `_extract`. The current mapping is a best-guess from CLAUDE.md.
"""
from __future__ import annotations

import time
from datetime import date, datetime

from _common import bulk_upsert, get_db_connection

TABLE = "funraise.fact_transactions"
COLUMNS = [
    "transaction_id",
    "supporter_id",
    "campaign_id",
    "transaction_date",
    "amount",
    "fee",
    "net",
    "currency",
    "payment_method",
    "recurring",
    "status",
    "utm_source",
    "utm_medium",
    "utm_campaign",
]
CONFLICT_COLUMNS = ["transaction_id"]
UPDATE_COLUMNS = [c for c in COLUMNS if c not in CONFLICT_COLUMNS]


def _maybe_str(value: object) -> str | None:
    return None if value is None else str(value)


def _parse_date(value: object) -> date | None:
    """Best-effort ISO date/datetime -> date. TODO: confirm Funraise's date format."""
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _extract(txn: dict) -> tuple:
    """Map one Funraise transaction object to a fact_transactions row tuple."""
    utm = txn.get("utm") or {}
    return (
        str(txn.get("id")),
        _maybe_str(txn.get("supporterId") or txn.get("supporter_id")),
        _maybe_str(txn.get("campaignId") or txn.get("campaign_id")),
        _parse_date(txn.get("date") or txn.get("createdAt")),
        txn.get("amount"),
        txn.get("fee"),
        txn.get("net"),
        txn.get("currency"),
        txn.get("paymentMethod") or txn.get("payment_method"),
        bool(txn.get("recurring")),
        txn.get("status"),
        utm.get("source"),
        utm.get("medium"),
        utm.get("campaign"),
    )


def load(payload: dict) -> dict:
    """Upsert one or more Funraise transactions from a webhook body. Returns stats."""
    start = time.time()

    # A webhook may deliver a single transaction object or a list under "transactions".
    if isinstance(payload.get("transactions"), list):
        txns = payload["transactions"]
    elif payload.get("id"):
        txns = [payload]
    else:
        txns = []

    rows = [_extract(t) for t in txns]

    conn = get_db_connection()
    try:
        upserted = bulk_upsert(
            conn, TABLE, COLUMNS, rows, CONFLICT_COLUMNS, UPDATE_COLUMNS
        )
    finally:
        conn.close()

    return {
        "query": "funraise webhook",
        "table": TABLE,
        "rows_read": len(rows),
        "rows_upserted": upserted,
        "elapsed_sec": round(time.time() - start, 1),
    }
