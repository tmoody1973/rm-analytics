"""Guards ga.v_app_daily (schema/024).

Radio Milwaukee's app spans TWO GA properties because its Android traffic migrated
between them in Sep 2025. Summing is correct; dropping either loses real traffic.
And active_users is not additive across days. If these assertions fail, a consumer
is about to report a wrong number to leadership.
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


def _all(sql: str, params: tuple = ()):
    import psycopg
    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_every_row_carries_a_brand():
    """The join to dim.brand_channels must not drop or orphan a property. If a new
    app property appears in GA, this fails until someone maps it."""
    view_rows = _one("SELECT count(*) FROM ga.v_app_daily")[0]
    src_groups = _one(
        "SELECT count(*) FROM (SELECT 1 FROM ga.stg_app_engagement_daily "
        "GROUP BY account__property_id, report__date, audience__platform) x"
    )[0]
    unmapped = _one(
        "SELECT count(DISTINCT e.account__property_id) FROM ga.stg_app_engagement_daily e "
        "LEFT JOIN dim.brand_channels bc ON bc.platform='ga4_app' AND bc.handle_or_id=e.account__property_id "
        "WHERE bc.station_code IS NULL"
    )[0]
    assert unmapped == 0, "a GA app property is not mapped in dim.brand_channels"
    # RM's two properties collapse into one station_code, so the view has FEWER rows.
    assert view_rows < src_groups, "the two RM properties did not merge"


def test_the_two_rm_properties_are_summed_not_dropped():
    """Sep 2025 handoff: neither property alone tells the truth about Android."""
    old, new = _one(
        "SELECT "
        " (SELECT sum(engagement__sessions) FROM ga.stg_app_engagement_daily "
        "   WHERE account__property_id='183736836' AND audience__platform='Android' "
        "     AND report__date >= '2026-06-01' AND report__date < '2026-07-01'), "
        " (SELECT sum(engagement__sessions) FROM ga.stg_app_engagement_daily "
        "   WHERE account__property_id='447654700' AND audience__platform='Android' "
        "     AND report__date >= '2026-06-01' AND report__date < '2026-07-01')"
    )
    merged = _one(
        "SELECT sum(sessions) FROM ga.v_app_daily WHERE station_code='RMORG' "
        "AND platform='Android' AND date >= '2026-06-01' AND date < '2026-07-01'"
    )[0]
    assert merged == old + new, f"expected {old} + {new}, view gave {merged}"
    assert new > old * 10, "sanity: the 2024 property should now carry most Android traffic"


def test_summing_android_across_the_handoff_stays_continuous():
    """If the properties double-counted, Sep 2025 would spike vs Aug. It doesn't."""
    aug, sep = _one(
        "SELECT "
        " (SELECT sum(sessions) FROM ga.v_app_daily WHERE station_code='RMORG' AND platform='Android'"
        "   AND date >= '2025-08-01' AND date < '2025-09-01'), "
        " (SELECT sum(sessions) FROM ga.v_app_daily WHERE station_code='RMORG' AND platform='Android'"
        "   AND date >= '2025-09-01' AND date < '2025-10-01')"
    )
    assert 0.8 < sep / aug < 1.2, f"handoff month is discontinuous: Aug {aug} -> Sep {sep}"


def test_ios_survives_the_merge():
    """iOS exists on only one property; a naive 'use the newest property' rule loses it."""
    ios = _one(
        "SELECT sum(sessions) FROM ga.v_app_daily "
        "WHERE station_code='RMORG' AND platform='iOS' AND date >= '2026-06-01' AND date < '2026-07-01'"
    )[0]
    assert ios and ios > 10000, f"iOS traffic vanished from the view: {ios}"


def test_a_new_user_is_always_an_active_user():
    """new_users <= active_users on every day. (The reverse — active <= sessions —
    is NOT an invariant: GA4 reports 6 days where a user is active with fewer
    sessions, e.g. HYFIN 2025-01-13 active=1 sessions=0. That quirk is in the raw
    staging table too, so it isn't ours to fix.)"""
    bad = _all(
        "SELECT station_code, date, platform, new_users, active_users_daily "
        "FROM ga.v_app_daily WHERE new_users > active_users_daily LIMIT 5"
    )
    assert bad == [], f"more new users than active users: {bad}"


def test_the_non_additive_column_keeps_its_warning_name():
    """`active_users_daily`, never `active_users`. Summing it across days yields
    person-days, not people — the CUME trap. The suffix is the guard rail; a rename
    would let a consumer sum it without noticing."""
    cols = [r[0] for r in _all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='ga' AND table_name='v_app_daily'"
    )]
    assert "active_users_daily" in cols
    assert "active_users" not in cols, "a summable-looking name reappeared"


def test_the_assistant_can_read_the_clean_view():
    granted = _one(
        "SELECT count(*) FROM information_schema.role_table_grants "
        "WHERE grantee='rm_readonly' AND table_schema='ga' AND table_name='v_app_daily'"
    )[0]
    assert granted >= 1, "rm_readonly cannot read ga.v_app_daily"
