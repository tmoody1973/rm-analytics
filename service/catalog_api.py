"""Catalog endpoints for the AI assistant's tool discovery (MOO-176 / Phase 2).

GET /api/metrics  — return the metric registry as a list of {id, name, description,
                    unit, source}. No params. Lets the assistant discover curated
                    metrics before falling back to raw SQL.

GET /api/schema   — return tables/columns the assistant may query. Derived from
                    the rm_readonly allowlist (schema/016_readonly_role.sql) via
                    information_schema.columns. funraise is excluded entirely — it
                    is not on the allowlist and donor PII must not be revealed even
                    as schema metadata.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from typing import Any

import psycopg
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pathlib import Path
from psycopg import sql
from psycopg.rows import dict_row

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from metrics.registry import REGISTRY  # noqa: E402

router = APIRouter()

# Keep in sync with schema/016 + schema/018_funraise_readonly_grant.sql
# + schema/021_social_intel_grant.sql.
# funraise (de-identified donor data) is included so the assistant can query it;
# the endpoint is gated behind INTERNAL_API_TOKEN and PII column VALUES are never
# enumerated (see _SENSITIVE_NAME_BITS / _DIMENSION_COLUMNS below).
_ALLOWED_SCHEMAS: frozenset[str] = frozenset({
    "wms", "nielsen", "ga", "meta_organic", "meta_ads",
    "email_esp", "finance", "dim", "marts", "funraise", "social_intel",
})

_ENV_PATH = Path.home() / ".radio-milwaukee" / ".env"

# Columns of these (text-like) types get their distinct values enumerated when
# low-cardinality, so the assistant can SEE the categories it can filter on
# (e.g. nielsen section='Gender Composition (AQH Persons)') instead of guessing.
_TEXT_TYPES: frozenset[str] = frozenset({"varchar", "text", "bpchar", "char", "name"})
# Only enumerate when distinct count <= this; above it the column is marked
# high-cardinality (avoids dumping every city/date/free-text value).
_MAX_DISTINCT = 40
# Per-column guard so enumerating values on a big fact table can't hang the call.
_ENRICH_TIMEOUT_MS = 4000

# DENY-BY-DEFAULT value enumeration. Only these categorical *dimension* column
# names get their distinct values listed. Arbitrary text columns are NEVER
# enumerated — they can hold PII (email_esp contact/address, list names, social
# captions). The structural schema still lists every column; the assistant can
# SELECT DISTINCT for any value not pre-listed.
_DIMENSION_COLUMNS: frozenset[str] = frozenset({
    # nielsen
    "section", "demo", "daypart", "metric", "period_label", "unit",
    # station / brand / channel
    "station", "station_code", "brand", "brand_code", "channel", "platform",
    # wms device + geo rollups
    "device_family", "device", "player", "dma", "country", "region",
    # ga traffic
    "source_medium", "source", "medium",
    # finance / generic dimensions
    "category", "subcategory", "restricted_yn", "frequency", "designation", "fund",
    "type", "status", "content_type", "post_type", "media_type",
    # newsletter enrichment — closed-vocab tags, safe to enumerate
    "primary_theme",
    # social_intel enrichment — closed-vocab tags, safe to enumerate
    "content_theme", "format", "hook_style", "primary_topic",
})
# Defense-in-depth: never enumerate a column whose name hints at PII/free text,
# even if it somehow appears above.
_SENSITIVE_NAME_BITS: tuple[str, ...] = (
    "email", "phone", "address", "contact", "name", "zip", "postal", "city",
    "first", "last", "ip", "secret", "token", "password", "caption", "subject",
    "url", "company", "note", "message", "body", "text", "handle",
)

# Short, human-written notes per table (grain + coverage + how to query the
# tricky ones). Tables without an entry simply omit `note`.
_TABLE_NOTES: dict[tuple[str, str], str] = {
    ("nielsen", "fact_vital_signs"): (
        "Nielsen PPM 'Vital Signs' for the FM BROADCAST signal (NOT streaming — that's wms.*). "
        "Long/unpivoted: one row per (station_code, demo, daypart, period_label, section, metric) "
        "with value_numeric (+value_raw, rank, unit). DEMOGRAPHICS LIVE HERE: filter `section` to "
        "'Gender Composition (AQH Persons)' (metric Male/Female), 'Age Cell Composition (AQH Persons)', "
        "or 'Ethnic Composition (AQH Persons)'. Other sections: Estimates, P1 Information, In-Tab, "
        "Detailed Daypart Trend (AQH Share). station_code RM88=88Nine, HYFIN. period_label like "
        "MAY26 / HOL25 (holiday). Small-sample caution on single-period swings."
    ),
    ("wms", "fact_hourly_listening"): "Triton streaming, hourly grain, per (station, date, hour). AAS/TLH/CUME/SS/TSL. Jan 2024-.",
    ("wms", "fact_daily_cume"): "Triton streaming, daily grain. CUME is non-additive — query at this grain, don't sum.",
    ("wms", "fact_weekly_cume"): "Triton streaming, weekly grain. CUME non-additive.",
    ("wms", "fact_monthly_cume"): "Triton streaming, monthly grain. CUME non-additive.",
    ("wms", "fact_monthly_geo"): "Triton streaming geography by (station, month, city, DMA). ~monthly.",
    ("wms", "fact_monthly_device"): "Triton streaming by device family/device/player, monthly.",
    ("dim", "stations"): "The 4 station codes: RM88 (88Nine), HYFIN, RM414 (414 Music), RLR (Rhythm Lab Radio).",
    ("dim", "brand_channels"): "Maps each social handle / GA property / email list / ad account to a station_code.",
    ("meta_organic", "fact_ig_followers_daily"): "Daily Instagram follower counts per brand page.",
    ("meta_organic", "v_ig_profile_monthly"): (
        "Monthly Instagram profile metrics per (account, month) — THE CLEAN SOURCE. "
        "Use this; the raw stg_ig_profile_monthly is not readable (bad data). Engagement "
        "columns are deliberately NULL where the source can't be trusted: before Aug 2025 "
        "(collection gap — reach IS populated back to Jan 2025), where a `-1` sentinel "
        "appeared, and where engagements exceeded reach (impossible; hits hyfin.mke Feb + "
        "Jul 2026). NULL means 'not measured', not zero — never report it as zero, and "
        "exclude those months from trends. `accounts_engaged` only starts Dec 2025. "
        "`engagement_rate` = engagements/reach. Accounts: radiomilwaukee AND 88nine.mke "
        "(both are 88Nine), hyfin.mke, gwmusiclab. `follows_and_unfollows` is never populated."
    ),
    ("email_esp", "stg_campaigns_report"): (
        "Mailchimp campaign report — ONE ROW PER NEWSLETTER (`id` = campaign_id), Jan 2024-. "
        "This is the authoritative campaign list AND where the PERFORMANCE metrics live: "
        "`opens_open_rate`, `opens_unique_opens`, `clicks_click_rate`, `clicks_unique_clicks`, "
        "`emails_sent`, `send_time`, `subject_line`. To correlate newsletter CONTENT with "
        "performance, JOIN this table on `id = fact_campaign_enrichment.campaign_id` (the modeled "
        "email_esp.fact_campaign_sends table is NOT populated — use this staging table)."
    ),
    ("email_esp", "fact_campaign_content"): (
        "Newsletter BODY text per campaign (PK campaign_id = stg_campaigns_report.id). "
        "`plain_text` (body), `word_count`, `links` (jsonb). Empty-body campaigns (RSS/archived/"
        "variants) have word_count 0. For the full body of one newsletter prefer the dedicated "
        "retrieval path over dumping plain_text via SQL."
    ),
    ("email_esp", "fact_campaign_enrichment"): (
        "LLM-derived TAGS per newsletter (PK campaign_id). `content_type` (newsletter/event_promo/"
        "fundraising_appeal/announcement/contest), `topics` (jsonb array), `primary_theme`, "
        "`featured_artists` (jsonb). Use to ask 'what topics/themes drive opens?' by joining "
        "stg_campaigns_report on campaign_id for the open/click rates. model='skipped-empty-body' "
        "means there was no body to tag (tags are null)."
    ),
    ("funraise", "dim_supporters"): (
        "DE-IDENTIFIED donor records — NO names, NO raw email, NO phone. `supporter_id` is an opaque "
        "key. Has city/state/postal (geo), `email_sha256` (one-way hash, NOT an address), "
        "lifetime_total/recurring_total/onetime_total, first/last_donation_at, active_12mo. Aggregate "
        "for analysis; never present an individual donor's identity (you cannot — there is none here)."
    ),
    ("funraise", "fact_transactions"): (
        "Every gift (one-time + recurring; `recurring` bool). amount/net/fee, transaction_at, "
        "`designation`/`fund` (+restricted flag), `status`, `channel`, utm_*, campaign_id, refund cols. "
        "No donor name. The Jan 2026 spike is a single $1M foundation grant (designation 'Foundations'); "
        "the warehouse cannot name the funder."
    ),
    ("funraise", "dim_campaigns"): "Funraise campaign metadata (`name` = campaign name, not a donor name).",
    ("funraise", "fact_subscriptions"): "Recurring giving plans: active/churned, amount, frequency. ~$47.5K MRR.",
    ("social_intel", "dim_accounts"): (
        "Watchlist of social accounts we track. `is_owned`=true is Radio Milwaukee, "
        "false is a COMPETITOR/peer. `category` (peer_station/local_media/music_brand/"
        "aspirational), `platform`, `station_code` when owned. Join to fact_posts / "
        "fact_account_snapshots on account_id."
    ),
    ("social_intel", "fact_account_snapshots"): (
        "Profile metrics over time per (account_id, snapshot_date) — follower_count, "
        "post_count. Weekly. follower_count is a VANITY number; compare with engagement_rate "
        "on fact_posts, not raw followers. Non-additive — query at the snapshot grain."
    ),
    ("social_intel", "fact_posts"): (
        "One row per public post per (account_id, post_id). USE `engagement_rate` "
        "(=(likes+comments+shares+saves)/followers-at-fetch) — it is comparable across "
        "account sizes; do NOT rank by raw likes/followers. Aggregate comment COUNTS only "
        "(no commenter data). Join dim_accounts on account_id to split us (is_owned) vs them; "
        "join fact_post_enrichment on post_id for content tags. Recent posts only (no deep history). "
        "IG caveat: the Instagram API reports reels with post_type='video' (not 'reel'/'short'), "
        "so filtering reels by post_type is unreliable for Instagram."
    ),
    ("social_intel", "fact_post_enrichment"): (
        "Haiku-derived TAGS per post (PK post_id). `content_theme` (local_artist_feature/"
        "event_promo/behind_the_scenes/community/music_discovery/...), `format`, `hook_style`, "
        "`has_cta`, `featured_artists` (jsonb). Join fact_posts on post_id to ask 'what "
        "themes/formats drive engagement_rate?'. model='skipped-empty-caption' => no caption to tag."
    ),
}


# ----------------------------------------------------------------- /api/metrics ---

@router.get("/api/metrics")
def list_metrics() -> list[dict[str, Any]]:
    """Return the full metric registry catalog.

    Each entry has: id, name, description, unit, source.
    The assistant uses this to discover which curated metrics are available
    before deciding to fall back to raw SQL via /api/ask-sql.
    """
    return [
        {
            "id": m.id,
            "name": m.name,
            "description": m.description,
            "unit": m.unit,
            "source": m.source,
        }
        for m in REGISTRY.values()
    ]


# ----------------------------------------------------------------- /api/schema ---

def _get_dsn() -> str:
    """Resolve DATABASE_URL from env or ~/.radio-milwaukee/.env."""
    if not os.environ.get("DATABASE_URL") and _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL not set")
    return dsn


def _enrich_distinct_values(cur, schema: str, table: str, col: dict[str, Any]) -> None:
    """For a low-cardinality text column, attach the distinct values (most
    frequent first) so the assistant can see the categories it can filter on.
    Above _MAX_DISTINCT, mark it high-cardinality instead of dumping the values.
    Mutates `col` in place; failures degrade to cardinality 'unknown'."""
    name = col["name"]
    low = name.lower()
    # Deny-by-default: only curated dimension names, never PII/free-text columns.
    if col["type"] not in _TEXT_TYPES:
        return
    if name not in _DIMENSION_COLUMNS:
        return
    if any(bit in low for bit in _SENSITIVE_NAME_BITS):
        return
    query = sql.SQL(
        "SELECT {c}::text AS v, count(*) AS n FROM {s}.{t} "
        "WHERE {c} IS NOT NULL GROUP BY 1 ORDER BY n DESC, 1 LIMIT %s"
    ).format(c=sql.Identifier(col["name"]), s=sql.Identifier(schema), t=sql.Identifier(table))
    try:
        cur.execute(query, (_MAX_DISTINCT + 1,))
        rows = cur.fetchall()
        if len(rows) <= _MAX_DISTINCT:
            col["values"] = [r["v"] for r in rows]
        else:
            col["cardinality"] = "high"
    except psycopg.Error:
        col["cardinality"] = "unknown"


def _fetch_schema_from_db() -> list[dict[str, Any]]:
    """Build the assistant's view of the warehouse: every allowlisted table's
    columns, the distinct values of low-cardinality text columns, and a per-table
    note. funraise is never returned (not in _ALLOWED_SCHEMAS).

    Shape: [{schema, table, note?, columns:[{name, type, values?|cardinality?}]}]
    """
    schema_placeholders = ", ".join(["%s"] * len(_ALLOWED_SCHEMAS))
    cols_sql = f"""
        SELECT
            table_schema  AS schema,
            table_name    AS "table",
            column_name   AS name,
            udt_name      AS type
        FROM information_schema.columns
        WHERE table_schema IN ({schema_placeholders})
          AND table_catalog = current_database()
        ORDER BY table_schema, table_name, ordinal_position
    """
    tables: dict[tuple[str, str], list[dict[str, Any]]] = {}
    try:
        with psycopg.connect(_get_dsn(), autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(cols_sql, list(_ALLOWED_SCHEMAS))
                for row in cur.fetchall():
                    key = (row["schema"], row["table"])
                    tables.setdefault(key, []).append(
                        {"name": row["name"], "type": row["type"]}
                    )
                # Cap per-query time so value enumeration can't hang the endpoint.
                cur.execute(f"SET statement_timeout = {_ENRICH_TIMEOUT_MS}")
                for (schema, table), cols in tables.items():
                    for col in cols:
                        _enrich_distinct_values(cur, schema, table, col)
    except (psycopg.OperationalError, RuntimeError) as exc:
        raise RuntimeError(f"schema query failed: {exc}") from exc

    result: list[dict[str, Any]] = []
    for (schema, table), cols in sorted(tables.items()):
        entry: dict[str, Any] = {"schema": schema, "table": table, "columns": cols}
        note = _TABLE_NOTES.get((schema, table))
        if note:
            entry["note"] = note
        result.append(entry)
    return result


# Cache the result so repeated assistant calls don't hammer information_schema.
# The schema only changes when migrations run; a process restart clears the cache.
@lru_cache(maxsize=1)
def _cached_schema() -> list[dict[str, Any]]:
    return _fetch_schema_from_db()


@router.get("/api/schema")
def get_schema() -> list[dict[str, Any]]:
    """Return table/column metadata for schemas the assistant may query.

    Excludes funraise (donor PII) and any schema not in the rm_readonly
    allowlist. Cached in-process after the first call.

    Shape: [{schema, table, columns:[{name, type}]}]
    """
    try:
        return _cached_schema()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
