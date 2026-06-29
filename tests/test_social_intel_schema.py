"""Verifies schema/020_social_intel.sql created the expected tables/columns.
Skips when no DATABASE_URL is available (CI without Neon)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_ENV_PATH = Path.home() / ".radio-milwaukee" / ".env"


def _dsn() -> str | None:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if _ENV_PATH.exists():
        from dotenv import dotenv_values
        return dotenv_values(_ENV_PATH).get("DATABASE_URL")
    return None


pytestmark = pytest.mark.skipif(_dsn() is None, reason="DATABASE_URL not set")


def _columns(table: str) -> set[str]:
    import psycopg
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'social_intel' AND table_name = %s",
            (table,),
        )
        return {r[0] for r in cur.fetchall()}


def test_dim_accounts_columns():
    cols = _columns("dim_accounts")
    assert {"account_id", "platform", "handle", "is_owned", "station_code", "active"} <= cols


def test_fact_posts_has_engagement_rate():
    cols = _columns("fact_posts")
    assert {"account_id", "post_id", "engagement_rate", "comments_count", "caption"} <= cols


def test_fact_post_enrichment_columns():
    cols = _columns("fact_post_enrichment")
    assert {"post_id", "content_theme", "format", "hook_style", "has_cta", "featured_artists"} <= cols
