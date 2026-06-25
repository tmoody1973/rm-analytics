# Phase 0c — Metric Coverage (donations + streaming) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four clean metrics to the registry — `revenue`, `active_sustainers`, `total_donors`, `avg_active_sessions` — each proven against the live warehouse, including cross-checks that reproduce the deployed dashboard's numbers.

**Architecture:** Extend the existing `metrics/registry.py` (built in MOO-172): add one builder function + one `REGISTRY` entry per metric, following the established `_streaming_tlh` pattern. New tests live in `tests/test_metric_coverage.py` and compute the legacy comparison value in-test via `get_db_connection` (no hardcoded numbers). No `dashboard_api.py` or front-end changes (deferred to MOO-176).

**Tech Stack:** Python 3.12, psycopg3, pytest. Reuses `metrics.filters` and `loaders/_common.get_db_connection`.

## Global Constraints

- Python import is `import psycopg`, NOT psycopg2.
- Revenue/giving = completed gifts only (`status='Complete'`); never count Failed/Refunded.
- Brand keys: `RM`, `HYFIN`, `RM414`, `RLR`, `GWML`, `ALL` (`RM`→`RM88`+`RMORG`). Period keys: `30d`, `90d`, `12m`, `ytd`, `all`.
- All SQL parameterized — no string-interpolated user values. `group_by` is validated by `run_metric` before the builder runs.
- Existing `run_metric(id, brand=None, period=None, group_by=None) -> {data, meta}` and the `Metric` dataclass (`id,name,description,unit,source,build`) are already in `metrics/registry.py`; ADD to them, do not rewrite.
- Donations are org-wide (not brand-split): `revenue`, `active_sustainers`, `total_donors` ignore `brand`.
- Do NOT modify `service/dashboard_api.py` or any front-end file in this plan.

---

### Task 1: `revenue` metric (period-aware, group_by month)

**Files:**
- Modify: `metrics/registry.py` (add `_revenue` builder above `REGISTRY`; add `"revenue"` entry inside `REGISTRY`)
- Create: `tests/test_metric_coverage.py`

**Interfaces:**
- Consumes: `metrics.registry.run_metric`, `metrics.filters.period_cutoff`, `loaders/_common.get_db_connection`.
- Produces: registry id `revenue` (unit `usd`, source `funraise.fact_transactions`); ungrouped → one row `{value}`; `group_by="month"` → rows `{bucket, value}` ordered by month.
- Produces: test helper `_scalar(sql, params=None)` in `tests/test_metric_coverage.py` (runs a scalar query on Neon, returns the single value) — later tasks reuse it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_metric_coverage.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_coverage.py -v`
Expected: FAIL — `KeyError: 'revenue'` (metric not registered yet).

- [ ] **Step 3: Write the builder and register it**

In `metrics/registry.py`, add this builder just above the `REGISTRY` definition:

```python
def _revenue(brand, period, group_by):
    where = ["status='Complete'"]
    params: list = []
    cutoff = period_cutoff(period)
    if cutoff:
        where.append("transaction_date >= %s")
        params.append(cutoff)
    clause = " WHERE " + " AND ".join(where)
    if group_by == "month":
        sql = (f"SELECT date_trunc('month', transaction_date)::date::text AS bucket, "
               f"round(sum(amount)) AS value FROM funraise.fact_transactions{clause} "
               f"GROUP BY 1 ORDER BY 1")
    else:
        sql = f"SELECT round(sum(amount)) AS value FROM funraise.fact_transactions{clause}"
    return sql, params
```

In the same file, add this entry inside the `REGISTRY` dict:

```python
    "revenue": Metric(
        "revenue", "Revenue (completed gifts)",
        "Total dollars from completed Funraise gifts (excludes failed/refunded). Period-aware; group by month.",
        "usd", "funraise.fact_transactions", _revenue,
    ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_coverage.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add metrics/registry.py tests/test_metric_coverage.py
git commit -m "feat: revenue metric (completed gifts, period/group_by-aware) + cross-check"
```

---

### Task 2: `active_sustainers` + `total_donors` metrics

**Files:**
- Modify: `metrics/registry.py` (add `_active_sustainers`, `_total_donors` builders + entries)
- Modify: `tests/test_metric_coverage.py` (append tests)

**Interfaces:**
- Produces: registry id `active_sustainers` (unit `count`, source `funraise.fact_subscriptions`) — count of `status='Active'` plans (any frequency).
- Produces: registry id `total_donors` (unit `count`, source `funraise.dim_supporters`) — count of all supporters.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_metric_coverage.py`:

```python
def test_active_sustainers_matches_legacy_count():
    legacy = _scalar("SELECT count(*) FROM funraise.fact_subscriptions WHERE status='Active'")
    out = run_metric("active_sustainers")
    assert out["meta"]["unit"] == "count"
    assert out["data"][0]["value"] == legacy


def test_total_donors_at_least_active_donors():
    total = run_metric("total_donors")["data"][0]["value"]
    active = run_metric("active_donors")["data"][0]["value"]
    assert total >= active > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_coverage.py -v -k "active_sustainers or total_donors"`
Expected: FAIL — `KeyError: 'active_sustainers'`.

- [ ] **Step 3: Write the builders and register them**

In `metrics/registry.py`, add above `REGISTRY`:

```python
def _active_sustainers(brand, period, group_by):
    return "SELECT count(*) AS value FROM funraise.fact_subscriptions WHERE status='Active'", []


def _total_donors(brand, period, group_by):
    return "SELECT count(*) AS value FROM funraise.dim_supporters", []
```

Add inside `REGISTRY`:

```python
    "active_sustainers": Metric(
        "active_sustainers", "Active sustainers",
        "Count of active recurring giving plans (any frequency).",
        "count", "funraise.fact_subscriptions", _active_sustainers,
    ),
    "total_donors": Metric(
        "total_donors", "Total donors (all time)",
        "Count of all supporters on record.",
        "count", "funraise.dim_supporters", _total_donors,
    ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_coverage.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add metrics/registry.py tests/test_metric_coverage.py
git commit -m "feat: active_sustainers + total_donors metrics with legacy cross-check"
```

---

### Task 3: `avg_active_sessions` metric (brand/period/group_by-aware)

**Files:**
- Modify: `metrics/registry.py` (add `_avg_active_sessions` builder + entry)
- Modify: `tests/test_metric_coverage.py` (append tests)

**Interfaces:**
- Produces: registry id `avg_active_sessions` (unit `count`, source `wms.fact_monthly_cume`) — `round(avg(aas),1)`; honors `brand` (station filter via `station_codes_for`), `period` (`month_start` cutoff), and `group_by in {None,"month","station"}` (grouped rows key `bucket`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_metric_coverage.py`:

```python
def test_avg_active_sessions_total_positive():
    out = run_metric("avg_active_sessions")
    assert out["meta"]["unit"] == "count"
    assert out["meta"]["source"] == "wms.fact_monthly_cume"
    assert out["data"][0]["value"] > 0


def test_avg_active_sessions_group_by_station_returns_buckets():
    out = run_metric("avg_active_sessions", group_by="station")
    assert {"bucket", "value"} <= set(out["data"][0].keys())
    assert len(out["data"]) >= 2


def test_avg_active_sessions_brand_filter_changes_value():
    all_aas = run_metric("avg_active_sessions")["data"][0]["value"]
    hyfin = run_metric("avg_active_sessions", brand="HYFIN")["data"][0]["value"]
    assert hyfin > 0
    assert hyfin != all_aas


def test_avg_active_sessions_bad_group_by_raises():
    with pytest.raises(ValueError):
        run_metric("avg_active_sessions", group_by="weekday")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_coverage.py -v -k avg_active_sessions`
Expected: FAIL — `KeyError: 'avg_active_sessions'`.

- [ ] **Step 3: Write the builder and register it**

In `metrics/registry.py`, add above `REGISTRY`:

```python
def _avg_active_sessions(brand, period, group_by):
    where: list[str] = []
    params: list = []
    codes = station_codes_for(brand)
    if codes:
        where.append("station_code = ANY(%s)")
        params.append(codes)
    cutoff = period_cutoff(period)
    if cutoff:
        where.append("month_start >= %s")
        params.append(cutoff)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    if group_by == "station":
        sql = (f"SELECT station_code AS bucket, round(avg(aas),1) AS value "
               f"FROM wms.fact_monthly_cume{clause} GROUP BY 1 ORDER BY 2 DESC")
    elif group_by == "month":
        sql = (f"SELECT month_start::text AS bucket, round(avg(aas),1) AS value "
               f"FROM wms.fact_monthly_cume{clause} GROUP BY 1 ORDER BY 1")
    else:
        sql = f"SELECT round(avg(aas),1) AS value FROM wms.fact_monthly_cume{clause}"
    return sql, params
```

Add inside `REGISTRY`:

```python
    "avg_active_sessions": Metric(
        "avg_active_sessions", "Avg active sessions (AAS)",
        "Average concurrent Triton streams. Brand- and period-aware; group by month or station.",
        "count", "wms.fact_monthly_cume", _avg_active_sessions,
    ),
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_coverage.py -v`
Expected: PASS (10 passed)

Run the whole suite (the drift guard must still pass — all four new ids already exist as measure ids in `semantic/rm_metrics.yml`):
Run: `source .venv/bin/activate && python -m pytest tests/ -q`
Expected: PASS (all green, 29 tests)

- [ ] **Step 5: Commit**

```bash
git add metrics/registry.py tests/test_metric_coverage.py
git commit -m "feat: avg_active_sessions metric (brand/period/group_by-aware); full suite green"
```

---

## Self-Review

- **Spec coverage:** `revenue` (Task 1), `active_sustainers` + `total_donors` (Task 2), `avg_active_sessions` (Task 3) — all four acceptance metrics covered. Cross-checks: `revenue` latest month == legacy revenue_trend SQL (Task 1), `active_sustainers` == legacy exec_kpis count (Task 2). Drift guard re-run in Task 3 Step 4 (ids pre-exist in `rm_metrics.yml`, so it stays green with no YAML edit). Full suite green in Task 3.
- **Placeholder scan:** none — every code step has complete code; every run step has the command + expected result.
- **Type consistency:** all builders match the established `(brand, period, group_by) -> (sql, params)` signature and register via the existing `Metric(id,name,description,unit,source,build)` dataclass; grouped rows use key `bucket` consistently (Tasks 1 & 3) with their tests; the `_scalar` helper defined in Task 1 is reused in Task 2.
- **Scope:** strictly additive to `metrics/registry.py` + `tests/test_metric_coverage.py`. No `dashboard_api.py` or front-end edits (deferred to MOO-176), matching the refined issue.
