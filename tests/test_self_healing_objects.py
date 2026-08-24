"""schema/025 — the database must repair itself when Coupler rebuilds a table.

Coupler DROPs and re-CREATEs its staging tables on every import. `DROP TABLE ...
CASCADE` took both clean views with it on 2026-07-10 and blanked the dashboard, and
the CREATE re-granted the dirty table to rm_readonly via schema/016's blanket
ALTER DEFAULT PRIVILEGES.

These tests reproduce that exact sequence against a scratch table.
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


def _exec(sql: str) -> None:
    import psycopg
    with psycopg.connect(_dsn(), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql)


def _view_exists(schema: str, name: str) -> bool:
    return _one(
        "SELECT count(*) FROM information_schema.views WHERE table_schema=%s AND table_name=%s",
        (schema, name),
    )[0] == 1


def test_both_clean_views_are_registered():
    names = _one("SELECT coalesce(array_agg(view_name), '{}') FROM admin.managed_view")[0]
    assert "meta_organic.v_ig_profile_monthly" in names
    assert "ga.v_app_daily" in names


def test_the_blanket_auto_grant_is_gone_from_couplers_schemas():
    """This is what silently re-exposed the dirty Instagram table."""
    rows = _one(
        "SELECT coalesce(array_agg(defaclnamespace::regnamespace::text), '{}') FROM pg_default_acl "
        "WHERE array_to_string(defaclacl, ',') LIKE '%%rm_readonly%%'"
    )[0]
    for coupler_schema in ("meta_organic", "ga", "meta_ads", "email_esp"):
        assert coupler_schema not in rows, f"{coupler_schema} still auto-grants future tables"


def test_our_own_schemas_keep_their_default_privileges():
    """wms/nielsen/dim are not Coupler's; nothing drops and recreates them."""
    rows = _one(
        "SELECT coalesce(array_agg(defaclnamespace::regnamespace::text), '{}') FROM pg_default_acl "
        "WHERE array_to_string(defaclacl, ',') LIKE '%%rm_readonly%%'"
    )[0]
    assert "wms" in rows and "nielsen" in rows


def test_rebuild_all_is_idempotent():
    _exec("SELECT admin.rebuild_all()")
    _exec("SELECT admin.rebuild_all()")
    assert _view_exists("meta_organic", "v_ig_profile_monthly")
    assert _view_exists("ga", "v_app_daily")


def test_a_dropped_and_recreated_table_heals_the_views(tmp_path):
    """THE REGRESSION. Reproduce Coupler: DROP TABLE ... CASCADE, then CREATE.

    Uses a scratch table in meta_organic with a view on it, so the real staging data
    is never touched. The event trigger must fire on the CREATE and rebuild everything.
    """
    _exec("DROP VIEW IF EXISTS meta_organic._probe_view")
    _exec("DROP TABLE IF EXISTS meta_organic._probe_tbl CASCADE")
    _exec("CREATE TABLE meta_organic._probe_tbl (id int)")
    try:
        # sanity: the real views exist before we start
        _exec("SELECT admin.rebuild_all()")
        assert _view_exists("meta_organic", "v_ig_profile_monthly")

        # Simulate the import: CASCADE kills the dependent view of the REAL table too,
        # so first prove the drop is destructive, then that CREATE heals it.
        _exec("DROP VIEW meta_organic.v_ig_profile_monthly")
        assert not _view_exists("meta_organic", "v_ig_profile_monthly"), "setup failed"

        # Coupler's CREATE TABLE — this alone must bring the view back.
        _exec("DROP TABLE meta_organic._probe_tbl CASCADE")
        _exec("CREATE TABLE meta_organic._probe_tbl (id int)")

        assert _view_exists("meta_organic", "v_ig_profile_monthly"), \
            "the event trigger did not rebuild the view"
        assert _view_exists("ga", "v_app_daily"), "the app view was not rebuilt"
    finally:
        _exec("DROP TABLE IF EXISTS meta_organic._probe_tbl CASCADE")
        _exec("SELECT admin.rebuild_all()")


def test_cascade_drop_then_create_heals_a_managed_view():
    """The faithful reproduction of 2026-07-10, on a scratch table so real data is safe.

    Coupler: DROP TABLE ... CASCADE (which silently takes the dependent view), then
    CREATE TABLE. The event trigger must fire on the CREATE and rebuild the view.
    """
    _exec("DROP TABLE IF EXISTS meta_organic._probe_src CASCADE")
    _exec("DELETE FROM admin.managed_view WHERE view_name = 'meta_organic._probe_v'")
    _exec("CREATE TABLE meta_organic._probe_src (id int)")
    _exec("SELECT admin.register_view('meta_organic._probe_v', "
          "'CREATE OR REPLACE VIEW meta_organic._probe_v AS SELECT id FROM meta_organic._probe_src')")
    try:
        assert _view_exists("meta_organic", "_probe_v")

        # exactly what Coupler does — and CASCADE eats the view without a word
        _exec("DROP TABLE meta_organic._probe_src CASCADE")
        assert not _view_exists("meta_organic", "_probe_v"), \
            "CASCADE did not drop the view; this test no longer reproduces the bug"

        _exec("CREATE TABLE meta_organic._probe_src (id int)")
        assert _view_exists("meta_organic", "_probe_v"), \
            "the event trigger did not heal the view after CREATE TABLE"
    finally:
        _exec("DROP TABLE IF EXISTS meta_organic._probe_src CASCADE")
        _exec("DELETE FROM admin.managed_view WHERE view_name = 'meta_organic._probe_v'")
        _exec("SELECT admin.rebuild_all()")


def test_a_broken_managed_view_cannot_block_couplers_import():
    """If a rebuild throws, the CREATE TABLE must still succeed — a bad view must never
    stop the data pipeline. The hardened /api/dashboard absorbs the missing view."""
    _exec("DELETE FROM admin.managed_view WHERE view_name = 'meta_organic._probe_bad'")
    _exec("INSERT INTO admin.managed_view (view_name, definition) VALUES "
          "('meta_organic._probe_bad', 'CREATE OR REPLACE VIEW meta_organic._probe_bad AS "
          "SELECT nope FROM meta_organic.no_such_table')")
    _exec("DROP TABLE IF EXISTS meta_organic._probe_ok CASCADE")
    try:
        _exec("CREATE TABLE meta_organic._probe_ok (id int)")   # must not raise
        assert _one("SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='meta_organic' AND table_name='_probe_ok'")[0] == 1
        # and the healthy views still got rebuilt despite the broken sibling
        assert _view_exists("meta_organic", "v_ig_profile_monthly")
    finally:
        _exec("DROP TABLE IF EXISTS meta_organic._probe_ok CASCADE")
        _exec("DELETE FROM admin.managed_view WHERE view_name = 'meta_organic._probe_bad'")


def test_the_rebuild_restores_the_revoke_on_the_dirty_table():
    """schema/016's default privilege would re-grant it; rebuild_all must revoke."""
    _exec("GRANT SELECT ON meta_organic.stg_ig_profile_monthly TO rm_readonly")   # simulate the regrant
    _exec("SELECT admin.rebuild_all()")
    granted = _one(
        "SELECT count(*) FROM information_schema.role_table_grants "
        "WHERE grantee='rm_readonly' AND table_schema='meta_organic' "
        "AND table_name='stg_ig_profile_monthly'"
    )[0]
    assert granted == 0, "the assistant can read the dirty staging table again"


def test_the_assistant_keeps_every_table_it_had():
    """Removing the blanket grant must not quietly strip the 56 objects it uses."""
    missing = _one(
        "SELECT coalesce(array_agg(r.schema_name || '.' || r.table_name), '{}') "
        "FROM admin.readonly_table r "
        "JOIN information_schema.tables i ON i.table_schema=r.schema_name AND i.table_name=r.table_name "
        "LEFT JOIN information_schema.role_table_grants g "
        "  ON g.grantee='rm_readonly' AND g.table_schema=r.schema_name AND g.table_name=r.table_name "
        "WHERE g.table_name IS NULL"
    )[0]
    assert missing == [], f"allowlisted tables the assistant lost: {missing}"


def test_a_new_coupler_table_is_NOT_readable_by_default():
    """Deny by default. A table Coupler invents tomorrow must not be auto-granted."""
    _exec("DROP TABLE IF EXISTS meta_organic._probe_new CASCADE")
    _exec("CREATE TABLE meta_organic._probe_new (id int)")
    try:
        granted = _one(
            "SELECT count(*) FROM information_schema.role_table_grants "
            "WHERE grantee='rm_readonly' AND table_schema='meta_organic' AND table_name='_probe_new'"
        )[0]
        assert granted == 0, "a brand-new Coupler table was auto-granted to the assistant"
    finally:
        _exec("DROP TABLE IF EXISTS meta_organic._probe_new CASCADE")
