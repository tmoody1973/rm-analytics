"""One broken query must never blank the whole dashboard.

On 2026-07-10 the dashboard showed "Couldn't load data: Failed to fetch". Coupler
had re-created its staging tables (DROP TABLE ... CASCADE), which took the two
clean views down with them. Three of the 41 queries referenced those views, threw,
and the endpoint 500'd — so all 41 returned nothing and the browser got no CORS
headers on the error response.

The data was fine the whole time. The dashboard should have rendered 38 of 41
cards and said so.
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


def test_a_broken_query_does_not_take_down_the_others(monkeypatch):
    from service import dashboard_api

    broken = dict(dashboard_api.QUERIES)
    broken["__deliberately_broken__"] = "SELECT * FROM meta_organic.table_that_does_not_exist"
    monkeypatch.setattr(dashboard_api, "QUERIES", broken)

    out = dashboard_api.dashboard_data()

    # the good queries all still came back
    assert out["tlh_by_station"], "a healthy query returned nothing"
    assert out["social_ig_monthly"], "a healthy query returned nothing"
    # the broken one is empty, not missing — the frontend maps over it
    assert out["__deliberately_broken__"] == []


def test_the_failure_is_reported_not_swallowed(monkeypatch):
    """A silent empty list is how a wrong number reaches leadership. Say what broke."""
    from service import dashboard_api

    broken = dict(dashboard_api.QUERIES)
    broken["__deliberately_broken__"] = "SELECT * FROM meta_organic.table_that_does_not_exist"
    monkeypatch.setattr(dashboard_api, "QUERIES", broken)

    out = dashboard_api.dashboard_data()
    errors = out["_errors"]
    assert len(errors) == 1
    assert errors[0]["query"] == "__deliberately_broken__"
    assert errors[0]["error"], "the error is unnamed"


def test_a_healthy_payload_reports_no_errors():
    from service import dashboard_api

    out = dashboard_api.dashboard_data()
    assert out["_errors"] == [], f"live queries are failing: {out['_errors']}"


def test_the_error_does_not_leak_sql_or_row_data():
    """/api/dashboard is UNAUTHENTICATED. The error surface must name the query and
    the failure class, never the statement text or a row."""
    from service import dashboard_api

    broken = dict(dashboard_api.QUERIES)
    secret = "SELECT 'super-secret-column-name' FROM meta_organic.nope"
    broken["__deliberately_broken__"] = secret
    import unittest.mock as mock
    with mock.patch.object(dashboard_api, "QUERIES", broken):
        out = dashboard_api.dashboard_data()
    blob = repr(out["_errors"])
    assert "super-secret-column-name" not in blob
    assert "SELECT" not in blob
