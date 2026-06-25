import os
import sys

import pytest

from metrics.registry import run_metric

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "loaders"))
from _common import get_db_connection  # noqa: E402


def _scalar(sql, params=None):
    """Run a scalar query against the live warehouse and return the one value."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])
            return cur.fetchone()[0]
    finally:
        conn.close()


def test_revenue_total_is_positive():
    out = run_metric("revenue")
    assert out["meta"]["unit"] == "usd"
    assert out["meta"]["source"] == "funraise.fact_transactions"
    assert out["data"][0]["value"] > 0


def test_revenue_group_by_month_returns_buckets():
    out = run_metric("revenue", group_by="month")
    assert {"bucket", "value"} <= set(out["data"][0].keys())
    assert len(out["data"]) >= 2


def test_revenue_period_narrows():
    all_time = run_metric("revenue")["data"][0]["value"]
    last_30 = run_metric("revenue", period="30d")["data"][0]["value"]
    assert 0 < last_30 <= all_time


def test_revenue_latest_month_matches_legacy_revenue_trend():
    legacy = _scalar(
        """SELECT round(sum(amount)) FROM funraise.fact_transactions
           WHERE status='Complete'
             AND date_trunc('month', transaction_date) = (
               SELECT max(date_trunc('month', transaction_date))
               FROM funraise.fact_transactions WHERE status='Complete')"""
    )
    out = run_metric("revenue", group_by="month")
    assert out["data"][-1]["value"] == legacy
