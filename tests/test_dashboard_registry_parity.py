"""The dashboard's headline KPIs must equal the registry (one definition).

These tests guard against drift: if the registry SQL changes, the dashboard
automatically reflects it (no separate bespoke SQL to keep in sync).
"""
from __future__ import annotations

import importlib

dashboard_api = importlib.import_module("service.dashboard_api")
from metrics.registry import run_metric  # noqa: E402


def _payload() -> dict:
    return dashboard_api.dashboard_data()


def test_exec_kpis_present():
    """exec_kpis key must exist and contain exactly one row."""
    p = _payload()
    assert "exec_kpis" in p, "exec_kpis missing from dashboard payload"
    assert len(p["exec_kpis"]) == 1


def test_sustainer_mrr_matches_registry():
    p = _payload()
    reg = run_metric("sustainer_mrr")["data"][0]["value"]
    got = p["exec_kpis"][0]["sustainer_mrr"]
    assert got == reg, f"sustainer_mrr mismatch: payload={got}, registry={reg}"


def test_active_donors_matches_registry():
    p = _payload()
    reg = run_metric("active_donors")["data"][0]["value"]
    got = p["exec_kpis"][0]["active_donors"]
    assert got == reg, f"active_donors mismatch: payload={got}, registry={reg}"


def test_active_sustainers_matches_registry():
    p = _payload()
    reg = run_metric("active_sustainers")["data"][0]["value"]
    got = p["exec_kpis"][0]["active_sustainers"]
    assert got == reg, f"active_sustainers mismatch: payload={got}, registry={reg}"


def test_revenue_12mo_matches_registry():
    p = _payload()
    # Registry uses period="12m" = today - 365 days (see metrics/filters.py).
    reg = run_metric("revenue", period="12m")["data"][0]["value"]
    got = p["exec_kpis"][0]["revenue_12mo"]
    assert got == reg, f"revenue_12mo mismatch: payload={got}, registry={reg}"
