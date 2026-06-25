"""
Funraise transaction webhook loader.

Real payload shape confirmed 2026-06-25 via diagnostic logging:

    { "sentAt": int, "event": str,
      "data": {
        "id": int,                      # -> transaction_id
        "donationDate": int,            # epoch (the gift moment)
        "transaction": { "amount", "sourceAmount", "currency", "status",
                         "paymentMethod", "transactionId" (gateway), "billingZip" },
        "supporter": { "id", "firstName"/"lastName"/"name"/"phone" (PII, dropped),
                       "email", "primaryAddress" },
        "allocation": { "id", "name" }, # name -> designation/fund
        "form": { "id", "name" },       # id -> campaign_id
        "subscription": { "id", ... },  # present => recurring; id -> recurring_plan_id
        "utm": { "source", "medium", "campaign", ... },
        "tip": { "amount", "percent" }, # donor-covered fee (best-effort)
        "fees": ... } }

Upserts the gift into funraise.fact_transactions AND the donor identity/geo into
funraise.dim_supporters (idempotent on transaction_id / supporter_id). The donor
upsert touches ONLY identity/geo columns — the lifetime/first/last/active rollup
fields are owned by the nightly rollup (jobs/refresh_funraise_rollup.py).

PII: names/phone are never stored; email is one-way hashed (hash_email). Mirrors
the backfill's privacy model (schema/006_funraise.sql).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from _common import bulk_upsert, get_db_connection, hash_email

CENTRAL = ZoneInfo("America/Chicago")

TXN_TABLE = "funraise.fact_transactions"
TXN_COLUMNS = [
    "transaction_id", "supporter_id", "campaign_id", "transaction_at",
    "transaction_date", "amount", "fee", "net", "currency", "payment_method",
    "recurring", "status", "utm_source", "utm_medium", "utm_campaign",
    "designation", "restricted", "fee_covered", "fee_covered_amount",
    "refunded", "refunded_amount", "refunded_at", "channel", "recurring_plan_id",
]
TXN_UPDATE = [c for c in TXN_COLUMNS if c != "transaction_id"]

SUP_TABLE = "funraise.dim_supporters"
# Only identity/geo here — rollup columns (lifetime_*, *_donation_at, active_12mo)
# are owned by the nightly rollup and must NOT be clobbered by the webhook.
SUP_COLUMNS = ["supporter_id", "email_sha256", "city", "state", "postal_code", "country"]
SUP_UPDATE = [c for c in SUP_COLUMNS if c != "supporter_id"]


def _s(v: object) -> str | None:
    if v is None:
        return None
    t = str(v).strip()
    return t or None


def _num(v: object) -> float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _epoch_dt(v: object) -> datetime | None:
    """Funraise epoch (seconds or millis) -> aware UTC datetime."""
    try:
        n = int(v)
    except (ValueError, TypeError):
        return None
    if n > 1_000_000_000_000:  # milliseconds
        n /= 1000
    return datetime.fromtimestamp(n, tz=timezone.utc)


def _extract_txn(data: dict) -> tuple:
    txn = data.get("transaction") or {}
    sub = data.get("subscription") or {}
    alloc = data.get("allocation") or {}
    form = data.get("form") or {}
    utm = data.get("utm") or {}
    fees = data.get("fees") or {}          # rich object: platformFeeAmount, funraiseNetAmount, donorCovered*
    status = _s(txn.get("status"))
    when = _epoch_dt(data.get("donationDate"))
    dcf = fees.get("donorCoveredFees")
    return (
        _s(data.get("id")),
        _s((data.get("supporter") or {}).get("id")),
        _s(form.get("id")),
        when,
        when.astimezone(CENTRAL).date() if when else None,
        _num(txn.get("amount")),
        _num(fees.get("platformFeeAmount")),     # fee
        _num(fees.get("funraiseNetAmount")),     # net (after fees)
        _s(txn.get("currency")),
        _s(txn.get("paymentMethod")),
        bool(sub.get("id")),                     # recurring if a subscription is attached
        status,
        _s(utm.get("source")), _s(utm.get("medium")), _s(utm.get("campaign")),
        _s(alloc.get("name")) or _s(form.get("name")),  # designation / fund
        None,  # restricted — not in payload
        bool(dcf) if dcf is not None else None,  # fee_covered (donorCoveredFees)
        _num(fees.get("donorCoveredFeeAmount")),
        (status.lower() == "refunded") if status else None,
        None, None,  # refunded_amount / refunded_at — not in payload
        None,        # channel — not in payload
        _s(sub.get("id")),
    )


def _extract_supporter(data: dict) -> tuple | None:
    sup = data.get("supporter") or {}
    sid = _s(sup.get("id"))
    if sid is None:
        return None
    addr = sup.get("primaryAddress") or {}
    txn = data.get("transaction") or {}
    return (
        sid,
        hash_email(sup.get("email")),
        _s(addr.get("city")),
        _s(addr.get("state") or addr.get("region")),
        _s(addr.get("postalCode") or addr.get("zip") or txn.get("billingZip")),
        _s(addr.get("country")),
    )


def load(payload: dict) -> dict:
    """Upsert one Funraise transaction (+ its donor) from a webhook body."""
    start = time.time()
    data = payload.get("data") or {}

    if not _s(data.get("id")):
        return {"query": "funraise webhook", "table": TXN_TABLE,
                "rows_read": 0, "rows_upserted": 0, "note": "no data.id",
                "elapsed_sec": round(time.time() - start, 1)}

    txn_rows = [_extract_txn(data)]
    sup = _extract_supporter(data)
    sup_rows = [sup] if sup else []

    conn = get_db_connection()
    try:
        txn_n = bulk_upsert(conn, TXN_TABLE, TXN_COLUMNS, txn_rows, ["transaction_id"], TXN_UPDATE)
        sup_n = bulk_upsert(conn, SUP_TABLE, SUP_COLUMNS, sup_rows, ["supporter_id"], SUP_UPDATE)
    finally:
        conn.close()

    return {
        "query": "funraise webhook",
        "table": TXN_TABLE,
        "event": payload.get("event"),
        "rows_read": len(txn_rows),
        "rows_upserted": txn_n,
        "supporters_upserted": sup_n,
        "elapsed_sec": round(time.time() - start, 1),
    }
