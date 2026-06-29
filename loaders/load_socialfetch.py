"""Fetch one social account from socialfetch, upsert its snapshot + posts, and
Haiku-tag any post that has no enrichment row yet.

Pure + idempotent: ON CONFLICT (account_id, snapshot_date) and (account_id, post_id)
DO UPDATE. Only NEW posts (no enrichment row) hit the LLM, so weekly cost stays flat.

CLI:
  python loaders/load_socialfetch.py ig:hyfinmke instagram hyfinmke
  python loaders/load_socialfetch.py ig:hyfinmke instagram hyfinmke --no-enrich
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db_connection, bulk_upsert  # noqa: E402
from _socialfetch import (  # noqa: E402
    fetch_account, normalize, _SNAPSHOT_COLUMNS, _POST_COLUMNS,
)
from _social_enrich import enrich_post, validate_enrichment  # noqa: E402

SNAPSHOT_TABLE = "social_intel.fact_account_snapshots"
POSTS_TABLE = "social_intel.fact_posts"
ENRICH_TABLE = "social_intel.fact_post_enrichment"
DEFAULT_MODEL = os.environ.get("ENRICH_MODEL", "claude-haiku-4-5-20251001")

_ENRICH_COLUMNS = ["post_id", "content_theme", "format", "primary_topic",
                   "hook_style", "has_cta", "featured_artists", "model"]


def _anthropic_client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def _already_enriched(conn, post_ids: list[str]) -> set[str]:
    """Return the subset of post_ids that already have an enrichment row."""
    if not post_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT post_id FROM {ENRICH_TABLE} WHERE post_id = ANY(%s)",
            (list(post_ids),),
        )
        return {r[0] for r in cur.fetchall()}


def load(account: dict, *, api_key=None, enrich=True, client=None,
         model=None, conn=None) -> dict:
    start = time.time()
    api_key = api_key or os.environ["SOCIALFETCH_API_KEY"]
    model = model or DEFAULT_MODEL
    owns_conn = conn is None
    conn = conn or get_db_connection()
    try:
        raw = fetch_account(account, api_key=api_key)
        if raw is None:                        # not_found / private — skip cleanly
            return {"account_id": account["account_id"], "skipped": True,
                    "posts_total": 0, "posts_upserted": 0, "snapshots_upserted": 0,
                    "enriched": 0, "elapsed_sec": round(time.time() - start, 1)}

        norm = normalize(account, raw)
        snap_upserted = bulk_upsert(
            conn, SNAPSHOT_TABLE, _SNAPSHOT_COLUMNS, [norm["snapshot"]],
            ["account_id", "snapshot_date"],
            [c for c in _SNAPSHOT_COLUMNS if c not in ("account_id", "snapshot_date")],
        )
        posts_upserted = bulk_upsert(
            conn, POSTS_TABLE, _POST_COLUMNS, norm["posts"],
            ["account_id", "post_id"],
            [c for c in _POST_COLUMNS if c not in ("account_id", "post_id")],
        )

        enrich_rows = []
        if enrich:
            all_post_ids = [row[1] for row in norm["posts"]]
            already = _already_enriched(conn, all_post_ids)
            new_post_ids = [pid for pid in all_post_ids if pid and pid not in already]
            # Only construct the anthropic client when there are captioned new posts.
            new_captioned = [pid for pid in new_post_ids if pid in norm["captions"]]
            if new_captioned and client is None:
                client = _anthropic_client()
            for post_id in sorted(new_post_ids):
                if post_id in norm["captions"]:
                    tags = enrich_post(client, norm["captions"][post_id], model=model)
                    tags = validate_enrichment(tags)   # defensive: stub may return raw
                    row_model = model
                else:
                    # Captionless post: write honest-null tags (mirrors newsletter loader's
                    # empty-body handling) so INNER JOINs don't silently drop these posts.
                    tags = validate_enrichment({})
                    row_model = "skipped-empty-caption"
                enrich_rows.append((
                    post_id, tags["content_theme"], tags["format"],
                    tags["primary_topic"], tags["hook_style"], tags["has_cta"],
                    json.dumps(tags["featured_artists"]), row_model,
                ))
            if enrich_rows:
                bulk_upsert(
                    conn, ENRICH_TABLE, _ENRICH_COLUMNS, enrich_rows, ["post_id"],
                    [c for c in _ENRICH_COLUMNS if c != "post_id"],
                )
        return {"account_id": account["account_id"], "skipped": False,
                "posts_total": len(norm["posts"]), "posts_upserted": posts_upserted,
                "snapshots_upserted": snap_upserted, "enriched": len(enrich_rows),
                "elapsed_sec": round(time.time() - start, 1)}
    finally:
        if owns_conn:
            conn.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    enrich = "--no-enrich" not in args
    pos = [a for a in args if not a.startswith("--")]
    if len(pos) < 3:
        raise SystemExit("usage: load_socialfetch.py <account_id> <platform> <handle> [--no-enrich]")
    acct = {"account_id": pos[0], "platform": pos[1], "handle": pos[2]}
    print(load(acct, enrich=enrich))
