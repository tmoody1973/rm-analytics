"""Guards the hygiene in meta_organic.v_ig_profile_monthly (schema/022).

The raw staging table reports impossible engagement values that were being shown
to leadership. If any of these assertions fail, the clean view stopped protecting
its consumers (the dashboard's social_ig_monthly query and the assistant).
"""
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


def _one(sql: str, params: tuple = ()):
    import psycopg
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def test_impossible_month_is_nulled():
    """hyfin.mke 2026-02: 37,624 engagements on 9,399 reach (400%) — must be NULL."""
    reach, eng = _one(
        "SELECT reach, engagements FROM meta_organic.v_ig_profile_monthly "
        "WHERE account='hyfin.mke' AND month=DATE '2026-02-01'"
    )
    assert reach == 9399, "source reach changed; revisit this guard"
    assert eng is None, f"impossible engagements leaked through: {eng}"


def test_real_spike_survives():
    """radiomilwaukee 2026-02 is a genuine viral month (11% rate) — must be kept."""
    reach, eng = _one(
        "SELECT reach, engagements FROM meta_organic.v_ig_profile_monthly "
        "WHERE account='radiomilwaukee' AND month=DATE '2026-02-01'"
    )
    assert (reach, eng) == (292282, 33107)


def test_collection_gap_is_null_not_zero():
    """Pre-Aug-2025 engagement wasn't collected; reach was. NULL, never 0."""
    reach, eng = _one(
        "SELECT reach, engagements FROM meta_organic.v_ig_profile_monthly "
        "WHERE account='radiomilwaukee' AND month=DATE '2025-07-01'"
    )
    assert reach == 78328 and eng is None


def test_assistant_cannot_read_the_dirty_table():
    """rm_readonly must hold the view and NOT the raw staging table."""
    granted = _one(
        "SELECT count(*) FROM information_schema.role_table_grants "
        "WHERE grantee='rm_readonly' AND table_schema='meta_organic' "
        "AND table_name='stg_ig_profile_monthly'"
    )[0]
    assert granted == 0, "rm_readonly can still read the dirty staging table"
    on_view = _one(
        "SELECT count(*) FROM information_schema.role_table_grants "
        "WHERE grantee='rm_readonly' AND table_schema='meta_organic' "
        "AND table_name='v_ig_profile_monthly'"
    )[0]
    assert on_view >= 1, "rm_readonly lost access to the clean view"
