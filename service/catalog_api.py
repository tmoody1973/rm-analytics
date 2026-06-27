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

# Keep in sync with schema/016_readonly_role.sql.
# funraise is intentionally absent — donor data is blocked at the role level
# and must not leak even as table/column metadata.
_ALLOWED_SCHEMAS: frozenset[str] = frozenset({
    "wms", "nielsen", "ga", "meta_organic", "meta_ads",
    "email_esp", "finance", "dim", "marts",
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
