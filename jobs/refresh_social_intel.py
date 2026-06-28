"""Weekly sweep: fetch every active watchlist account, upsert snapshot + posts,
Haiku-tag new posts. One bad handle never aborts the run; a socialfetch credit
exhaustion (402) DOES abort + alerts so we notice immediately.

Fly scheduled machine `social-intel-weekly`. CLI:
  python jobs/refresh_social_intel.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "loaders"))
sys.path.insert(0, ROOT)
from _common import get_db_connection  # noqa: E402
from _socialfetch import SocialfetchCreditError  # noqa: E402
from load_socialfetch import load  # noqa: E402
from service.slack import post_success, post_failure  # noqa: E402

TAG = "[SOCIAL-INTEL]"


def active_accounts(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT account_id, platform, handle FROM social_intel.dim_accounts "
            "WHERE active ORDER BY account_id"
        )
        return [{"account_id": r[0], "platform": r[1], "handle": r[2]}
                for r in cur.fetchall()]


def run() -> dict:
    conn = get_db_connection()
    summary = {"accounts": 0, "fetched": 0, "skipped": 0, "posts_upserted": 0,
               "enriched": 0, "failures": 0, "tag": TAG}
    try:
        accounts = active_accounts(conn)
        summary["accounts"] = len(accounts)
        for account in accounts:
            try:
                stats = load(account, conn=conn)
                if stats["skipped"]:
                    summary["skipped"] += 1
                else:
                    summary["fetched"] += 1
                    summary["posts_upserted"] += stats["posts_upserted"]
                    summary["enriched"] += stats["enriched"]
            except SocialfetchCreditError:
                # Out of credits — every later account would fail too. Abort loudly.
                post_failure(TAG, "socialfetch credits exhausted (402) — run aborted")
                raise
            except Exception as exc:            # noqa: BLE001 — isolate one bad handle
                summary["failures"] += 1
                print(f"{TAG} skipped {account['account_id']}: {exc}")
        # Shape the success message for service.slack.post_success.
        post_success(TAG, {"table": "social_intel.fact_posts",
                           "rows_upserted": summary["posts_upserted"],
                           "rows_read": summary["accounts"],
                           "elapsed_sec": "—"})
        return summary
    finally:
        conn.close()


if __name__ == "__main__":
    print(run())
