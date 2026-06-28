"""Guardrail tests for the read-only ask-sql surface (MOO-173)."""
from __future__ import annotations

import os

import pytest

from service.ask_sql_api import ENV_PATH, SqlValidationError, validate_sql


def _ro_available() -> bool:
    if os.environ.get("DATABASE_URL_RO"):
        return True
    if ENV_PATH.exists():
        from dotenv import dotenv_values
        return bool(dotenv_values(ENV_PATH).get("DATABASE_URL_RO"))
    return False


@pytest.mark.parametrize("bad", [
    "",
    "   ",
    "INSERT INTO dim.stations VALUES (1)",
    "UPDATE dim.stations SET a = 1",
    "DELETE FROM dim.stations",
    "DROP TABLE dim.stations",
    "CREATE TABLE dim.y (a int)",
    "ALTER TABLE dim.stations ADD COLUMN z int",
    "TRUNCATE dim.stations",
    "GRANT SELECT ON dim.stations TO public",
    "SELECT 1; DROP TABLE dim.stations",          # multi-statement
    "SELECT * FROM secret.tbl",                    # off-allowlist schema
    "SELECT * FROM stations",                      # unqualified table
    "WITH x AS (DELETE FROM dim.s RETURNING 1) SELECT * FROM x",  # smuggled write
    "SELECT * FROM dim.stations; SELECT 1",        # trailing extra statement
])
def test_rejected(bad):
    with pytest.raises(SqlValidationError):
        validate_sql(bad)


def test_allows_simple_aggregate_and_injects_limit():
    out = validate_sql("SELECT count(*) FROM dim.stations")
    assert out.lower().endswith("limit 1000")


def test_allows_trailing_semicolon():
    out = validate_sql("SELECT count(*) FROM dim.stations;")
    assert "limit 1000" in out.lower()


def test_caps_oversized_limit():
    out = validate_sql("SELECT * FROM dim.stations LIMIT 99999")
    assert "_ask_sql_capped" in out
    assert out.strip().lower().endswith("limit 1000")


def test_keeps_small_limit():
    out = validate_sql("SELECT * FROM dim.stations LIMIT 5")
    assert "limit 5" in out.lower()          # inner bound preserved
    assert out.strip().lower().endswith("limit 1000")  # outer cap added


def test_allows_cte():
    out = validate_sql(
        "WITH t AS (SELECT station_code FROM dim.stations) SELECT count(*) FROM t"
    )
    assert out  # no raise; CTE name 't' is allowed as a bare relation


def test_strips_comments_before_validation():
    # the comment hides a DROP; after stripping, it's a clean SELECT
    out = validate_sql("SELECT count(*) FROM dim.stations -- DROP TABLE x")
    assert "limit 1000" in out.lower()


def test_case_insensitive_keywords():
    with pytest.raises(SqlValidationError):
        validate_sql("insert INTO dim.stations values (1)")


@pytest.mark.skipif(not _ro_available(), reason="DATABASE_URL_RO not set")
def test_live_aggregate_returns_rows_via_ro_role():
    from fastapi.testclient import TestClient

    from service.main import app

    client = TestClient(app)
    r = client.post("/api/ask-sql",
                    json={"sql": "SELECT count(*) AS n FROM wms.fact_monthly_cume"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["via"] == "read-only SQL"
    assert body["data"][0]["n"] >= 0


def test_funraise_aggregate_now_validates():
    # De-identified donor data is unblocked: a funraise SELECT must pass
    # validation (and get the outer LIMIT cap) rather than raising.
    out = validate_sql("SELECT count(*) FROM funraise.dim_supporters")
    assert out.strip().lower().endswith("limit 1000")


def test_funraise_join_validates():
    out = validate_sql(
        "SELECT s.state, sum(t.amount) AS total "
        "FROM funraise.fact_transactions t "
        "JOIN funraise.dim_supporters s ON s.supporter_id = t.supporter_id "
        "GROUP BY s.state"
    )
    assert out.strip().lower().endswith("limit 1000")


def test_cte_only_limit_still_capped():
    # the only LIMIT is inside the CTE; outer result must still be capped
    out = validate_sql(
        "WITH t AS (SELECT station_code FROM dim.stations LIMIT 3) "
        "SELECT * FROM t"
    )
    assert out.strip().lower().endswith("limit 1000")
    assert "_ask_sql_capped" in out


def test_subquery_limit_still_capped():
    out = validate_sql(
        "SELECT * FROM dim.stations a "
        "JOIN (SELECT station_code FROM dim.stations LIMIT 5) b "
        "ON a.station_code = b.station_code"
    )
    assert out.strip().lower().endswith("limit 1000")


def test_string_literal_with_limit_not_rewritten():
    # a 'limit 99999' literal must be preserved, not edited by the capper
    out = validate_sql("SELECT 'limit 99999' AS label FROM dim.stations")
    assert "limit 99999" in out          # literal intact
    assert out.strip().lower().endswith("limit 1000")


def test_social_intel_schema_is_allowed():
    from service.ask_sql_api import validate_sql
    # Should not raise — social_intel is on the allowlist.
    out = validate_sql(
        "SELECT account_id, engagement_rate FROM social_intel.fact_posts"
    )
    assert "social_intel.fact_posts" in out
