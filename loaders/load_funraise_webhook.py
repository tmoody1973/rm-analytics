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
    "transaction_at",
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
    "designation",
    "restricted",
    "fee_covered",
    "fee_covered_amount",
    "refunded",
    "refunded_amount",
    "refunded_at",
    "channel",
    "recurring_plan_id",
]
CONFLICT_COLUMNS = ["transaction_id"]
UPDATE_COLUMNS = [c for c in COLUMNS if c not in CONFLICT_COLUMNS]


def _maybe_str(value: object) -> str | None:
    return None if value is None else str(value)


def _opt_bool(value: object) -> bool | None:
    """Optional bool: missing key -> None (unknown), not False. Accepts JSON
    bools or string flags ('true'/'1'/'yes')."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "t"}
    return bool(value)


def _parse_datetime(value: object) -> datetime | None:
    """Best-effort ISO datetime -> aware datetime. TODO: confirm Funraise's format."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


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
    status = txn.get("status")
    when = txn.get("date") or txn.get("createdAt")
    return (
        str(txn.get("id")),
        _maybe_str(txn.get("supporterId") or txn.get("supporter_id")),
        _maybe_str(txn.get("campaignId") or txn.get("campaign_id")),
        _parse_datetime(when),
        _parse_date(when),
        txn.get("amount"),
        txn.get("fee"),
        txn.get("net"),
        txn.get("currency"),
        txn.get("paymentMethod") or txn.get("payment_method"),
        bool(txn.get("recurring")),
        status,
        utm.get("source"),
        utm.get("medium"),
        utm.get("campaign"),
        # --- extras (best-guess field names; confirm against a real payload) ---
        txn.get("designation") or txn.get("fund") or txn.get("fundName"),
        _opt_bool(txn.get("restricted")),
        _opt_bool(txn.get("feeCovered") or txn.get("fee_covered") or txn.get("coveredFee")),
        txn.get("feeCoveredAmount") or txn.get("coveredFeeAmount"),
        _opt_bool(txn.get("refunded")) if txn.get("refunded") is not None
        else (str(status).lower() == "refunded" if status else None),
        txn.get("refundedAmount") or txn.get("refundAmount"),
        _parse_date(txn.get("refundedAt") or txn.get("refunded_at")),
        txn.get("channel") or txn.get("giftChannel") or txn.get("source"),
        _maybe_str(
            txn.get("recurringPlanId")
            or txn.get("subscriptionId")
            or txn.get("recurring_plan_id")
        ),
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
