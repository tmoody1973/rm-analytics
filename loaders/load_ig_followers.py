"""
Pull absolute Instagram follower counts from the Meta Graph API and snapshot
them daily into meta_organic.fact_ig_followers_daily.

WHY THIS EXISTS
---------------
The Coupler "Instagram Insights" monthly feed (meta_organic.stg_ig_profile_monthly)
carries reach/engagement but NO absolute follower total — its net follows column
is 100% null. The Graph API exposes the real number as the `followers_count`
field on the IG Business Account node. This loader reads it with zero Coupler
usage (so it doesn't touch the Coupler connected-account limit) using the
META_ACCESS_TOKEN we already keep as a Fly secret.

HOW IT DISCOVERS ACCOUNTS
-------------------------
GET /me/accounts?fields=instagram_business_account{id,username,followers_count}
returns every Facebook Page the token's user manages, with the linked IG
Business Account inline. We snapshot each linked account. An IG account is only
visible here if it is linked to a Page the token manages — accounts not linked
to a managed Page won't appear (document/add explicitly if one is missing).

REQUIRED TOKEN SCOPES
---------------------
A long-lived USER access token with: pages_show_list, instagram_basic,
pages_read_engagement (business_management also works). Set as env/Fly secret
META_ACCESS_TOKEN.

CLI:  python loaders/load_ig_followers.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, timezone, datetime

import requests

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db_connection  # noqa: E402

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
TIMEOUT = 30

UPSERT_SQL = """
INSERT INTO meta_organic.fact_ig_followers_daily
    (snapshot_date, ig_user_id, account_name, followers_count)
VALUES (%s, %s, %s, %s)
ON CONFLICT (snapshot_date, ig_user_id) DO UPDATE
SET account_name    = EXCLUDED.account_name,
    followers_count = EXCLUDED.followers_count,
    loaded_at       = now();
"""


def _token() -> str:
    token = os.environ.get("META_ACCESS_TOKEN")
    if not token:
        # Local runs keep the token in ~/.radio-milwaukee/.env; on Fly it's a real
        # env secret. Load the dotenv file before giving up (mirrors _common's DB path).
        from pathlib import Path

        from dotenv import load_dotenv

        env_path = Path.home() / ".radio-milwaukee" / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            token = os.environ.get("META_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN not set (env or Fly secret)")
    return token


def fetch_ig_accounts(token: str) -> list[dict]:
    """Return [{ig_user_id, account_name, followers_count}] for every linked IG
    Business Account the token can see. Follows pagination."""
    accounts: list[dict] = []
    url = f"{GRAPH_BASE}/me/accounts"
    params = {
        "fields": "instagram_business_account{id,username,followers_count}",
        "limit": 100,
        "access_token": token,
    }
    while url:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        body = resp.json()
        if "error" in body:
            raise RuntimeError(f"Graph API error: {body['error']}")
        for page in body.get("data", []):
            ig = page.get("instagram_business_account")
            if not ig or "id" not in ig:
                continue
            accounts.append({
                "ig_user_id": str(ig["id"]),
                "account_name": ig.get("username"),
                "followers_count": ig.get("followers_count"),
            })
        # Pagination: subsequent pages come back as a full `next` URL.
        url = body.get("paging", {}).get("next")
        params = None
    # De-dupe in case two Pages link the same IG account.
    seen: dict[str, dict] = {}
    for a in accounts:
        seen[a["ig_user_id"]] = a
    return list(seen.values())


def load(token: str | None = None, snapshot: date | None = None) -> dict:
    """Snapshot today's IG follower counts. Idempotent on (date, ig_user_id)."""
    token = token or _token()
    snapshot = snapshot or datetime.now(timezone.utc).date()
    accounts = fetch_ig_accounts(token)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for a in accounts:
                cur.execute(UPSERT_SQL, (
                    snapshot, a["ig_user_id"], a["account_name"], a["followers_count"],
                ))
        conn.commit()
    finally:
        conn.close()

    return {
        "snapshot_date": snapshot.isoformat(),
        "accounts": len(accounts),
        "detail": [
            {"account": a["account_name"], "followers": a["followers_count"]}
            for a in accounts
        ],
    }


if __name__ == "__main__":
    stats = load()
    print(f"[IG-FOLLOWERS] {stats['snapshot_date']} — {stats['accounts']} accounts")
    for d in stats["detail"]:
        print(f"  {d['account']}: {d['followers']:,}" if d["followers"] is not None
              else f"  {d['account']}: (null)")
