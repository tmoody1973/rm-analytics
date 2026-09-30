"""Daily freshness check: Slack-alert when any source's newest data goes stale.

Catches the silent-freeze failure mode — a feed stops (Coupler over quota, a
Triton email missed, a token expired) and nobody notices for weeks. Reads Neon,
compares each source's newest data date to a per-source max age, and posts ONE
Slack message listing anything stale. Quiet when everything is fresh.

Thresholds are deliberately loose to avoid alert fatigue — they catch a feed
that has *stopped*, not one that is a day behind. Streaming monthly oscillates
~62–92 days stale by design (it arrives ~2 months after month-end), so its
threshold only fires on a fully missed month.

Fly scheduled machine `freshness-check-daily`. CLI:
  python jobs/check_freshness.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

import psycopg  # noqa: E402
from service.slack import post_stale  # noqa: E402

TAG = "[FRESHNESS]"

# (label, SQL returning ONE latest date/timestamp, max_age_days before "stale")
CHECKS: list[tuple[str, str, int]] = [
    ("streaming daily (Triton)",   "SELECT max(date) FROM wms.fact_daily_cume", 6),
    ("streaming monthly (Triton)", "SELECT max(month_start) FROM wms.fact_monthly_cume", 95),
    ("web GA pages (Coupler)",     "SELECT max(report__date) FROM ga.stg_pages_daily", 4),
    ("web GA sessions (Coupler)",  "SELECT max(report__date) FROM ga.stg_sessions_daily", 4),
    ("social Meta FB (Coupler)",   "SELECT max(report__date) FROM meta_organic.stg_fb_page_daily", 4),
    ("IG followers (Meta API)",    "SELECT max(snapshot_date) FROM meta_organic.fact_ig_followers_daily", 4),
]


def _as_date(v: object) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def run() -> dict:
    today = date.today()
    stale: list[tuple[str, str, int | None]] = []
    fresh: list[tuple[str, str, int]] = []
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        for label, sql, max_age in CHECKS:
            cur.execute(sql)
            latest = _as_date(cur.fetchone()[0])
            if latest is None:
                stale.append((label, "no data", None))
                continue
            age = (today - latest).days
            (stale if age > max_age else fresh).append((label, latest.isoformat(), age))
    if stale:
        post_stale(TAG, stale)
    return {"stale": stale, "fresh": fresh, "checked": len(CHECKS)}


if __name__ == "__main__":
    print(json.dumps(run(), default=str, indent=2))
