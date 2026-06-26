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


def _fetch_schema_from_db() -> list[dict[str, Any]]:
    """Query information_schema.columns for the allowlisted schemas.

    Returns a list of {schema, table, columns:[{name, type}]} objects,
    grouped by (table_schema, table_name).  funraise is never returned
    because it is not in _ALLOWED_SCHEMAS.
    """
    schema_placeholders = ", ".join(["%s"] * len(_ALLOWED_SCHEMAS))
    sql = f"""
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
    params = list(_ALLOWED_SCHEMAS)

    tables: dict[tuple[str, str], list[dict[str, str]]] = {}
    try:
        with psycopg.connect(_get_dsn()) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                for row in cur.fetchall():
                    key = (row["schema"], row["table"])
                    tables.setdefault(key, []).append(
                        {"name": row["name"], "type": row["type"]}
                    )
    except (psycopg.OperationalError, RuntimeError) as exc:
        raise RuntimeError(f"schema query failed: {exc}") from exc

    return [
        {"schema": schema, "table": table, "columns": cols}
        for (schema, table), cols in sorted(tables.items())
    ]


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
