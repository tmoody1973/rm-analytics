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


def _all(sql: str, params: tuple = ()):
    import psycopg
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# ── schema/023: the guard must blame the metric that is actually wrong ────────


def test_reach_is_nulled_when_accounts_engaged_exceeds_it():
    """hyfin.mke 2026-07: acctEng 6,135 > reach 2,213. You cannot engage with a post
    you were never shown, so REACH is the broken column — not engagements. 022 had
    this backwards: it kept the bad reach and discarded a real engagement number."""
    reach, eng, acct = _one(
        "SELECT reach, engagements, accounts_engaged FROM meta_organic.v_ig_profile_monthly "
        "WHERE account='hyfin.mke' AND month=DATE '2026-07-01'"
    )
    assert reach is None, f"impossible reach leaked through: {reach}"
    assert eng == 7327, "the real engagement number was discarded"
    assert acct == 6135, "accounts_engaged is the witness, not the accused — keep it"


def test_no_surviving_row_reports_more_engagement_than_reach():
    """Whichever column was at fault, the output must never be self-contradictory."""
    bad = _all(
        "SELECT account, month, reach, engagements, accounts_engaged "
        "FROM meta_organic.v_ig_profile_monthly "
        "WHERE reach IS NOT NULL "
        "  AND (engagements > reach OR accounts_engaged > reach)"
    )
    assert bad == [], f"contradictory rows survived the guard: {bad}"


# ── schema/023: the in-progress month must announce itself ────────────────────


def test_only_the_in_progress_month_is_incomplete():
    """Coupler re-pulls the current month nightly, so its window covers only the days
    elapsed (9, when written). Every closed month must read complete."""
    total = _one("SELECT count(DISTINCT month) FROM meta_organic.v_ig_profile_monthly")[0]
    open_months = _all(
        "SELECT DISTINCT month, period_end FROM meta_organic.v_ig_profile_monthly "
        "WHERE NOT is_complete"
    )
    assert len(open_months) == 1, f"expected exactly one in-progress month, got {open_months}"
    assert total > 1, "sanity: there should be closed months to compare against"


def test_a_31_day_month_ending_on_the_30th_still_counts_as_complete():
    """Coupler caps its window at 30 days, so a 31-day month legitimately ends on the
    30th. A naive `period_end = month end` rule would call every one of them truncated
    and hide half the history."""
    period_end, is_complete = _one(
        "SELECT DISTINCT period_end, is_complete FROM meta_organic.v_ig_profile_monthly "
        "WHERE month = DATE '2026-01-01'"          # January: 31 days, window ends the 30th
    )
    assert str(period_end) == "2026-01-30", "source window changed; revisit the rule"
    assert is_complete is True, "a 30-day window on a 31-day month must count as complete"


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
