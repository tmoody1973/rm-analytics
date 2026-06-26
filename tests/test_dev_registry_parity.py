"""Parity tests for the five new Development-tab donor metrics.

Each metric must return a numeric `value` via run_metric().
Additional contracts per metric are documented inline.
"""
from __future__ import annotations

from metrics.registry import run_metric


def test_avg_gift_returns_numeric_value():
    out = run_metric("avg_gift")
    row = out["data"][0]
    assert isinstance(row["value"], (int, float)), f"expected numeric, got {row['value']!r}"
    assert row["value"] > 0


def test_avg_gift_row_also_carries_mean():
    out = run_metric("avg_gift")
    row = out["data"][0]
    assert "mean" in row, "avg_gift row must include a 'mean' field"
    assert isinstance(row["mean"], (int, float)), f"mean should be numeric, got {row['mean']!r}"
    assert row["mean"] > 0


def test_sustainer_share_is_between_0_and_100():
    out = run_metric("sustainer_share")
    value = out["data"][0]["value"]
    assert isinstance(value, (int, float)), f"expected numeric, got {value!r}"
    assert 0 <= value <= 100, f"sustainer_share out of range: {value}"


def test_donor_retention_pct_is_between_0_and_100():
    out = run_metric("donor_retention_pct")
    value = out["data"][0]["value"]
    assert isinstance(value, (int, float)), f"expected numeric, got {value!r}"
    assert 0 <= value <= 100, f"donor_retention_pct out of range: {value}"


def test_new_donors_returns_positive_count():
    out = run_metric("new_donors")
    value = out["data"][0]["value"]
    assert isinstance(value, (int, float)), f"expected numeric, got {value!r}"
    assert value > 0


def test_lapsed_donors_returns_positive_count():
    out = run_metric("lapsed_donors")
    value = out["data"][0]["value"]
    assert isinstance(value, (int, float)), f"expected numeric, got {value!r}"
    assert value > 0


def test_avg_gift_period_12m():
    """Period filter must narrow the result — 12m avg gift should still be positive."""
    out = run_metric("avg_gift", period="12m")
    assert out["data"][0]["value"] > 0


def test_new_donors_period_12m():
    out = run_metric("new_donors", period="12m")
    assert out["data"][0]["value"] >= 0  # could be 0 in test env but must not error


def test_registry_meta_units():
    """Smoke-check unit metadata for all five new metrics."""
    expected = {
        "avg_gift": "usd",
        "sustainer_share": "percent",
        "donor_retention_pct": "percent",
        "new_donors": "count",
        "lapsed_donors": "count",
    }
    for metric_id, unit in expected.items():
        out = run_metric(metric_id)
        assert out["meta"]["unit"] == unit, (
            f"{metric_id}: expected unit={unit!r}, got {out['meta']['unit']!r}"
        )
