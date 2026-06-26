"""
Recompute the funraise.dim_supporters rollup from fact_transactions.

The webhook appends raw gifts to fact_transactions in real time, but the donor
rollup fields (lifetime_*, first/last_donation_at, active_12mo) are batch-derived
and don't update themselves. Run this nightly (Fly cron) so the supporter
dimension stays current.

Counts only Complete gifts (excludes Failed / Refunded). Splits recurring vs
one-time. active_12mo is a snapshot as of the run date — that's why it must be
re-run regularly. NOTE: first/last_donation_at are bounded by our data start
(2023-01-01); pre-2023 first gifts read as Jan 2023.

CLI:  python jobs/refresh_funraise_rollup.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "loaders"))
from _common import get_db_connection  # noqa: E402

ROLLUP_SQL = """
UPDATE funraise.dim_supporters s
SET first_donation_at = r.first_at,
    last_donation_at   = r.last_at,
    lifetime_total     = r.total,
    lifetime_recurring = r.recur,
    lifetime_onetime   = r.onetime,
    active_12mo        = COALESCE(r.last_at >= CURRENT_DATE - INTERVAL '12 months', false)
FROM (
  SELECT supporter_id,
    min(transaction_date) FILTER (WHERE status='Complete') AS first_at,
    max(transaction_date) FILTER (WHERE status='Complete') AS last_at,
    COALESCE(sum(amount) FILTER (WHERE status='Complete'), 0)                   AS total,
    COALESCE(sum(amount) FILTER (WHERE status='Complete' AND recurring), 0)      AS recur,
    COALESCE(sum(amount) FILTER (WHERE status='Complete' AND NOT recurring), 0)  AS onetime
  FROM funraise.fact_transactions
  WHERE supporter_id IS NOT NULL
  GROUP BY supporter_id
) r
WHERE s.supporter_id = r.supporter_id;
"""


def run() -> dict:
    start = time.time()
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(ROLLUP_SQL)
            updated = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return {"job": "funraise_rollup", "supporters_updated": updated,
            "elapsed_sec": round(time.time() - start, 1)}


if __name__ == "__main__":
    print(run())
