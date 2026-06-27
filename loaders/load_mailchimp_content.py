"""Fetch Mailchimp newsletter content, upsert it, and LLM-tag each newsletter.

Two entry modes (same function): explicit campaign ids, or --all to sweep every
sent campaign in email_esp.fact_campaign_sends that has no content row yet.
Idempotent: ON CONFLICT (campaign_id) DO UPDATE on both tables.

CLI:
  python loaders/load_mailchimp_content.py --all          # backfill / sweep
  python loaders/load_mailchimp_content.py CID1 CID2       # specific campaigns
  python loaders/load_mailchimp_content.py --all --no-enrich
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db_connection, bulk_upsert  # noqa: E402
from _mailchimp import fetch_campaign_content, parse_content  # noqa: E402
from _enrich import enrich_text, validate_enrichment  # noqa: E402

CONTENT_TABLE = "email_esp.fact_campaign_content"
ENRICH_TABLE = "email_esp.fact_campaign_enrichment"
DEFAULT_MODEL = os.environ.get("ENRICH_MODEL", "claude-haiku-4-5-20251001")


def campaigns_to_process(conn, *, include_unenriched: bool = True) -> list[str]:
    # Source of campaign IDs is email_esp.stg_campaigns_report (`id`), the
    # authoritative list Coupler maintains. The "clean" fact_campaign_sends is
    # not populated in this warehouse (the staging->fact promotion was never
    # built), so we read straight from staging. A campaign needs processing when
    # it has no content row, or (when enriching) no enrichment row.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.id "
            "FROM email_esp.stg_campaigns_report s "
            "LEFT JOIN email_esp.fact_campaign_content    c ON c.campaign_id = s.id "
            "LEFT JOIN email_esp.fact_campaign_enrichment e ON e.campaign_id = s.id "
            "WHERE s.id IS NOT NULL AND s.id <> '' "
            "  AND (c.campaign_id IS NULL "
            "       OR (%s AND e.campaign_id IS NULL)) "
            "ORDER BY s.send_time",
            (include_unenriched,),
        )
        return [r[0] for r in cur.fetchall()]


def _anthropic_client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def load(campaign_ids=None, *, api_key=None, enrich=True, client=None,
         model=None, conn=None) -> dict:
    start = time.time()
    api_key = api_key or os.environ["MAILCHIMP_API_KEY"]
    model = model or DEFAULT_MODEL
    owns_conn = conn is None
    conn = conn or get_db_connection()
    try:
        ids = list(campaign_ids) if campaign_ids is not None else campaigns_to_process(conn, include_unenriched=enrich)

        content_rows, enrich_rows = [], []
        failed: list[str] = []
        if enrich and ids and client is None:
            client = _anthropic_client()

        for cid in ids:
            try:
                raw = fetch_campaign_content(api_key, cid)
                parsed = parse_content(raw.get("html"), raw.get("plain_text"))
                content_rows.append((cid, parsed["plain_text"], parsed["html"],
                                     json.dumps(parsed["links"]), parsed["word_count"]))
                if enrich:
                    # Some campaigns (RSS, archived, A/B variants) return an empty
                    # body. Don't ask the LLM to tag nothing — it hallucinates a
                    # theme. Store honest empty tags so the row is marked processed
                    # (not re-fetched) without fabricated content.
                    if parsed["word_count"] > 0:
                        tags = enrich_text(client, parsed["plain_text"], model=model)
                        tag_model = model
                    else:
                        tags = validate_enrichment({})
                        tag_model = "skipped-empty-body"
                    enrich_rows.append((cid, tags["primary_theme"], json.dumps(tags["topics"]),
                                        tags["content_type"], json.dumps(tags["featured_artists"]),
                                        tag_model))
            except Exception as exc:
                print(f"[ESP-CONTENT] skipped {cid}: {exc}")
                failed.append(cid)

        upserted = bulk_upsert(
            conn, CONTENT_TABLE,
            ["campaign_id", "plain_text", "html", "links", "word_count"],
            content_rows, ["campaign_id"],
            ["plain_text", "html", "links", "word_count"],
        )
        if enrich_rows:
            bulk_upsert(
                conn, ENRICH_TABLE,
                ["campaign_id", "primary_theme", "topics", "content_type",
                 "featured_artists", "model"],
                enrich_rows, ["campaign_id"],
                ["primary_theme", "topics", "content_type", "featured_artists", "model"],
            )
        return {"table": CONTENT_TABLE, "rows_read": len(ids),
                "rows_upserted": upserted, "enriched": len(enrich_rows),
                "failed": len(failed),
                "elapsed_sec": round(time.time() - start, 1)}
    finally:
        if owns_conn:
            conn.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    enrich = "--no-enrich" not in args
    sweep = "--all" in args
    ids = [a for a in args if not a.startswith("--")]
    print(load(ids if (ids and not sweep) else None, enrich=enrich))
