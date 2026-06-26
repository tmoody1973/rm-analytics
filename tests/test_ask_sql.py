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
    "SELECT * FROM funraise.dim_supporters",       # donor table
    "SELECT funraise.x FROM dim.stations",         # funraise token anywhere
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
    assert "99999" not in out
    assert "1000" in out


def test_keeps_small_limit():
    out = validate_sql("SELECT * FROM dim.stations LIMIT 5")
    assert out.strip().lower().endswith("limit 5")


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


def test_live_donor_table_rejected():
    from fastapi.testclient import TestClient

    from service.main import app

    client = TestClient(app)
    r = client.post("/api/ask-sql",
                    json={"sql": "SELECT count(*) FROM funraise.dim_supporters"})
    assert r.status_code == 400
    assert "funraise" in r.json()["detail"].lower()
