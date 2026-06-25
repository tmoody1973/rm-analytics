# Phase 0 — Metric Registry + Metric Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the canonical metric layer — a Python metric registry (the executable form of `semantic/rm_metrics.yml`) and a FastAPI `/api/metric/{id}` endpoint — so the dashboard tabs and the future AI assistant resolve every number through one definition.

**Architecture:** A `metrics/` package holds pure brand/period→SQL filter helpers and a registry of `Metric` objects, each with plain-English metadata and a SQL builder. `run_metric()` executes a metric against Neon and returns `{data, meta}`. A thin FastAPI route exposes it. Brand and period vocabularies exactly match the front-end (`RM/HYFIN/RM414/RLR/GWML/ALL`, `30d/90d/12m/ytd/all`).

**Tech Stack:** Python 3.12, FastAPI, psycopg3, pytest (new dev dep), PyYAML (new dev dep, for the drift test). Reuses `loaders/_common.get_db_connection`.

## Global Constraints

- Python import is `import psycopg`, NOT psycopg2.
- Brand keys (verbatim): `RM`, `HYFIN`, `RM414`, `RLR`, `GWML`, `ALL`. `RM` maps to station codes `RM88` + `RMORG`.
- Period keys (verbatim): `30d`, `90d`, `12m`, `ytd`, `all`.
- Revenue = completed gifts only (`status='Complete'`); never count Failed/Refunded.
- Source schemas are read-only; no writes from this layer.
- DB connection via `loaders/_common.get_db_connection()` (reads `DATABASE_URL`).
- No row-by-row inserts; this layer only SELECTs.

---

### Task 1: metrics package + brand/period filter helpers

**Files:**
- Create: `metrics/__init__.py`
- Create: `metrics/filters.py`
- Create: `tests/test_metric_filters.py`
- Modify: `requirements-dev.txt` (create)

**Interfaces:**
- Produces: `metrics.filters.station_codes_for(brand: str | None) -> list[str] | None`
  (returns `None` for `ALL`/`None`, raises `ValueError` for unknown brand).
- Produces: `metrics.filters.period_cutoff(period: str | None, today: date | None = None) -> date | None`
  (returns `None` for `all`/`None`, raises `ValueError` for unknown period).

- [ ] **Step 1: Add dev requirements**

Create `requirements-dev.txt`:

```
pytest==8.3.3
PyYAML==6.0.2
```

Install:

```bash
source .venv/bin/activate && pip install -r requirements-dev.txt
```

- [ ] **Step 2: Create the empty package marker**

Create `metrics/__init__.py`:

```python
"""Canonical metric layer — executable form of semantic/rm_metrics.yml."""
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_metric_filters.py`:

```python
from datetime import date

import pytest

from metrics.filters import station_codes_for, period_cutoff


def test_station_codes_rm_maps_to_two_codes():
    assert station_codes_for("RM") == ["RM88", "RMORG"]


def test_station_codes_all_is_none():
    assert station_codes_for("ALL") is None
    assert station_codes_for(None) is None


def test_station_codes_unknown_raises():
    with pytest.raises(ValueError):
        station_codes_for("NOPE")


def test_period_cutoff_30d():
    assert period_cutoff("30d", today=date(2026, 6, 25)) == date(2026, 5, 26)


def test_period_cutoff_ytd():
    assert period_cutoff("ytd", today=date(2026, 6, 25)) == date(2026, 1, 1)


def test_period_cutoff_all_is_none():
    assert period_cutoff("all", today=date(2026, 6, 25)) is None


def test_period_cutoff_unknown_raises():
    with pytest.raises(ValueError):
        period_cutoff("forever", today=date(2026, 6, 25))
```

- [ ] **Step 4: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_filters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'metrics.filters'`

- [ ] **Step 5: Write minimal implementation**

Create `metrics/filters.py`:

```python
"""Pure brand/period -> SQL-filter helpers. No DB access, fully unit-testable.

Brand and period vocabularies match the dashboard front-end exactly so the
tabs, filters, and assistant share one language.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

# Brand key -> station codes (streaming / Nielsen). ALL / None = no filter.
# RM is the merged flagship: RM88 (broadcast/streaming) + RMORG (digital).
BRAND_STATIONS: dict[str, list[str]] = {
    "RM": ["RM88", "RMORG"],
    "HYFIN": ["HYFIN"],
    "RM414": ["RM414"],
    "RLR": ["RLR"],
    "GWML": ["GWML"],
}

PERIOD_DAYS: dict[str, int] = {"30d": 30, "90d": 90, "12m": 365}


def station_codes_for(brand: str | None) -> list[str] | None:
    """Station codes for a brand key, or None for ALL/None. Raises on unknown."""
    if not brand or brand == "ALL":
        return None
    if brand not in BRAND_STATIONS:
        raise ValueError(f"unknown brand {brand!r}")
    return BRAND_STATIONS[brand]


def period_cutoff(period: str | None, today: date | None = None) -> date | None:
    """Inclusive lower-bound date for a period key, or None for all/None."""
    today = today or datetime.now(timezone.utc).date()
    if not period or period == "all":
        return None
    if period == "ytd":
        return date(today.year, 1, 1)
    if period in PERIOD_DAYS:
        return today - timedelta(days=PERIOD_DAYS[period])
    raise ValueError(f"unknown period {period!r}")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_filters.py -v`
Expected: PASS (7 passed)

- [ ] **Step 7: Commit**

```bash
git add metrics/__init__.py metrics/filters.py tests/test_metric_filters.py requirements-dev.txt
git commit -m "feat: metric-layer brand/period filter helpers + pytest dev deps"
```

---

### Task 2: Metric registry + run_metric (org-wide metrics)

**Files:**
- Create: `metrics/registry.py`
- Create: `tests/test_metric_registry.py`

**Interfaces:**
- Consumes: `metrics.filters.station_codes_for`, `metrics.filters.period_cutoff`.
- Produces: `metrics.registry.REGISTRY: dict[str, Metric]`.
- Produces: `metrics.registry.run_metric(metric_id: str, brand: str | None = None, period: str | None = None, group_by: str | None = None) -> dict`
  returning `{"data": list[dict], "meta": {"id","name","description","unit","source"}}`. Raises `KeyError` on unknown metric_id, `ValueError` on bad group_by.
- Produces: `Metric` dataclass with fields `id, name, description, unit, source, build`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_metric_registry.py` (integration — needs `DATABASE_URL`):

```python
import pytest

from metrics.registry import REGISTRY, run_metric


def test_sustainer_mrr_matches_known_floor():
    out = run_metric("sustainer_mrr")
    assert out["meta"]["unit"] == "usd"
    assert out["meta"]["source"] == "funraise.fact_subscriptions"
    value = out["data"][0]["value"]
    # ~$47.5K active monthly MRR loaded (handoff 2026-06-25); guard a sane floor.
    assert value is not None and value > 40000


def test_active_donors_is_positive_count():
    out = run_metric("active_donors")
    assert out["meta"]["unit"] == "count"
    assert out["data"][0]["value"] > 0


def test_unknown_metric_raises_keyerror():
    with pytest.raises(KeyError):
        run_metric("does_not_exist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'metrics.registry'`

- [ ] **Step 3: Write minimal implementation**

Create `metrics/registry.py`:

```python
"""The metric registry — one place that defines each leadership number.

Each Metric carries plain-English metadata (for tooltips + the assistant's
citations) and a SQL builder. run_metric() executes against Neon and returns
{data, meta}. The same logic backs the dashboard tabs and the assistant tools.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "loaders"))
from _common import get_db_connection  # noqa: E402

from .filters import period_cutoff, station_codes_for  # noqa: E402

Builder = Callable[[str | None, str | None, str | None], tuple[str, list]]
VALID_GROUP_BYS: set[str | None] = {None, "month", "station"}


@dataclass(frozen=True)
class Metric:
    id: str
    name: str
    description: str
    unit: str       # 'usd' | 'count' | 'percent' | 'hours'
    source: str     # origin table, used for citations
    build: Builder


def _jsonable(v: object):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


# ---------------------------------------------------------------- builders ---
def _sustainer_mrr(brand, period, group_by):
    return (
        "SELECT round(sum(amount)) AS value FROM funraise.fact_subscriptions "
        "WHERE status='Active' AND frequency='Monthly'",
        [],
    )


def _active_donors(brand, period, group_by):
    return (
        "SELECT count(*) AS value FROM funraise.dim_supporters WHERE active_12mo",
        [],
    )


REGISTRY: dict[str, Metric] = {
    "sustainer_mrr": Metric(
        "sustainer_mrr", "Sustainer MRR",
        "Monthly recurring revenue from active monthly sustainer plans. Target $50,000.",
        "usd", "funraise.fact_subscriptions", _sustainer_mrr,
    ),
    "active_donors": Metric(
        "active_donors", "Active donors",
        "Distinct donors with a completed gift in the last 12 months.",
        "count", "funraise.dim_supporters", _active_donors,
    ),
}


def run_metric(metric_id: str, brand: str | None = None,
               period: str | None = None, group_by: str | None = None) -> dict:
    if metric_id not in REGISTRY:
        raise KeyError(metric_id)
    if group_by not in VALID_GROUP_BYS:
        raise ValueError(f"unknown group_by {group_by!r}")
    m = REGISTRY[metric_id]
    sql, params = m.build(brand, period, group_by)
    conn = get_db_connection()
    try:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()
    data = [{k: _jsonable(v) for k, v in r.items()} for r in rows]
    return {
        "data": data,
        "meta": {"id": m.id, "name": m.name, "description": m.description,
                 "unit": m.unit, "source": m.source},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_registry.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add metrics/registry.py tests/test_metric_registry.py
git commit -m "feat: metric registry + run_metric with sustainer_mrr, active_donors"
```

---

### Task 3: Brand- and period-aware metric (streaming TLH)

**Files:**
- Modify: `metrics/registry.py` (add `_streaming_tlh` builder + registry entry)
- Modify: `tests/test_metric_registry.py` (add brand/period/group_by tests)

**Interfaces:**
- Produces: registry id `streaming_tlh` (unit `hours`, source `wms.fact_monthly_cume`),
  honoring `brand` (station filter), `period` (month_start cutoff), and
  `group_by in {None, "month", "station"}` (grouped rows use key `bucket`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_metric_registry.py`:

```python
def test_streaming_tlh_total_is_positive():
    out = run_metric("streaming_tlh")
    assert out["meta"]["unit"] == "hours"
    assert out["data"][0]["value"] > 0


def test_streaming_tlh_hyfin_less_than_all():
    all_tlh = run_metric("streaming_tlh")["data"][0]["value"]
    hyfin = run_metric("streaming_tlh", brand="HYFIN")["data"][0]["value"]
    assert 0 < hyfin < all_tlh


def test_streaming_tlh_group_by_station_returns_buckets():
    out = run_metric("streaming_tlh", group_by="station")
    assert {"bucket", "value"} <= set(out["data"][0].keys())
    assert len(out["data"]) >= 2  # at least RM88 + HYFIN


def test_streaming_tlh_bad_group_by_raises():
    with pytest.raises(ValueError):
        run_metric("streaming_tlh", group_by="weekday")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_registry.py -v -k streaming`
Expected: FAIL — `KeyError: 'streaming_tlh'`

- [ ] **Step 3: Write minimal implementation**

In `metrics/registry.py`, add this builder above `REGISTRY`:

```python
def _streaming_tlh(brand, period, group_by):
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
    if group_by == "month":
        sql = (f"SELECT month_start::text AS bucket, round(sum(tlh)) AS value "
               f"FROM wms.fact_monthly_cume{clause} GROUP BY 1 ORDER BY 1")
    elif group_by == "station":
        sql = (f"SELECT station_code AS bucket, round(sum(tlh)) AS value "
               f"FROM wms.fact_monthly_cume{clause} GROUP BY 1 ORDER BY 2 DESC")
    else:
        sql = f"SELECT round(sum(tlh)) AS value FROM wms.fact_monthly_cume{clause}"
    return sql, params
```

In the same file, add to `REGISTRY`:

```python
    "streaming_tlh": Metric(
        "streaming_tlh", "Streaming total listening hours",
        "Triton streaming hours, summed. Brand- and period-aware; group by month or station.",
        "hours", "wms.fact_monthly_cume", _streaming_tlh,
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_registry.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add metrics/registry.py tests/test_metric_registry.py
git commit -m "feat: brand/period/group_by-aware streaming_tlh metric"
```

---

### Task 4: FastAPI metric endpoint

**Files:**
- Create: `service/metric_api.py`
- Modify: `service/main.py` (add the route)
- Create: `tests/test_metric_api.py`

**Interfaces:**
- Consumes: `metrics.registry.run_metric`.
- Produces: `GET /api/metric/{metric_id}?brand=&period=&group_by=` → JSON `{data, meta}`;
  404 on unknown metric; 400 on bad brand/period/group_by.

- [ ] **Step 1: Write the failing test**

Create `tests/test_metric_api.py`:

```python
from fastapi.testclient import TestClient

from service.main import app

client = TestClient(app)


def test_metric_endpoint_returns_data_and_meta():
    r = client.get("/api/metric/sustainer_mrr")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["id"] == "sustainer_mrr"
    assert "data" in body


def test_metric_endpoint_unknown_is_404():
    r = client.get("/api/metric/nope")
    assert r.status_code == 404


def test_metric_endpoint_bad_brand_is_400():
    r = client.get("/api/metric/streaming_tlh", params={"brand": "NOPE"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_api.py -v`
Expected: FAIL — `404` for the first test (route not defined) or import error.

- [ ] **Step 3: Write minimal implementation**

Create `service/metric_api.py`:

```python
"""Read-only metric endpoint. Resolves a metric_id through the registry so the
dashboard and the assistant share one definition of every number.
"""
from __future__ import annotations

import os
import sys

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from metrics.registry import run_metric  # noqa: E402

router = APIRouter()


@router.get("/api/metric/{metric_id}")
def metric(metric_id: str, brand: str | None = None,
           period: str | None = None, group_by: str | None = None) -> dict:
    try:
        return run_metric(metric_id, brand=brand, period=period, group_by=group_by)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown metric {metric_id!r}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

In `service/main.py`, after `app.add_middleware(...)` (CORS block), add:

```python
from . import metric_api

app.include_router(metric_api.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add service/metric_api.py service/main.py tests/test_metric_api.py
git commit -m "feat: GET /api/metric/{id} endpoint over the registry"
```

---

### Task 5: Registry ↔ YAML drift guard

**Files:**
- Create: `tests/test_registry_yaml_sync.py`

**Interfaces:**
- Consumes: `metrics.registry.REGISTRY`, `semantic/rm_metrics.yml`.
- Produces: a test asserting every registry metric id appears as a measure id in the
  semantic YAML (no orphan registry metrics; the reverse is allowed while metrics are
  still being ported).

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry_yaml_sync.py`:

```python
from pathlib import Path

import yaml

from metrics.registry import REGISTRY

YAML_PATH = Path(__file__).resolve().parents[1] / "semantic" / "rm_metrics.yml"


def _measure_ids() -> set[str]:
    docs = yaml.safe_load_all(YAML_PATH.read_text())
    ids: set[str] = set()
    for doc in docs:
        if not doc:
            continue
        for measure in doc.get("measures", []) or []:
            ids.add(measure["id"])
    return ids


def test_every_registry_metric_exists_in_yaml():
    yaml_ids = _measure_ids()
    orphans = [mid for mid in REGISTRY if mid not in yaml_ids]
    assert not orphans, f"registry metrics missing from rm_metrics.yml: {orphans}"
```

- [ ] **Step 2: Run test to verify it fails (or reveals a real mismatch)**

Run: `source .venv/bin/activate && python -m pytest tests/test_registry_yaml_sync.py -v`
Expected: The test imports cleanly. If it FAILS, the failure names registry ids absent
from the YAML — that is a real drift to fix in Step 3, not a test bug.

- [ ] **Step 3: Reconcile ids so the test passes**

The starter registry uses ids `sustainer_mrr`, `active_donors`, `streaming_tlh`.
`semantic/rm_metrics.yml` already defines `sustainer_mrr` and `active_donors`. The
streaming measure in the YAML is `tlh` (model `streaming_monthly`). Make the names
match by renaming the YAML measure id `tlh` → `streaming_tlh` in
`semantic/rm_metrics.yml` (the `streaming_monthly` model's measures):

```yaml
  - id: streaming_tlh
    func: sum
    of: tlh
    type: number
    name: Total Listening Hours
    visibility: public
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_registry_yaml_sync.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the whole suite**

Run: `source .venv/bin/activate && python -m pytest tests/test_metric_filters.py tests/test_metric_registry.py tests/test_metric_api.py tests/test_registry_yaml_sync.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add tests/test_registry_yaml_sync.py semantic/rm_metrics.yml
git commit -m "test: registry<->YAML drift guard; align streaming_tlh id"
```

---

## What this plan deliberately leaves for follow-on plans

- **Read-only Neon role + guarded `/api/ask-sql`** (the assistant's SQL fallback) — its own plan; it is the assistant's dependency, not the dashboard's.
- **Porting the remaining ~10 metrics** from `rm_metrics.yml` (Nielsen, web, email, social, finance) — incremental, same pattern as Tasks 2–3.
- **Refactoring `dashboard_api.py`** queries onto the registry — a follow-on once enough metrics exist to back the current tabs.
- **Phase 1 role tabs** and **Phase 2 CopilotKit assistant** — separate plans per the spec's phasing.

## Self-Review

- **Spec coverage (Phase 0 metric layer):** metric registry ✓ (Tasks 2–3), metric service ✓ (Task 4), brand/period vocab match ✓ (Task 1), YAML-as-spec + drift test ✓ (Task 5). Read-only role / guarded SQL / query refactor explicitly deferred above (still Phase 0 in the spec, split into the next plan for independent testability).
- **Placeholder scan:** none — every code step shows complete code; every run step shows the command + expected result.
- **Type consistency:** `run_metric(metric_id, brand, period, group_by)` signature and the `{data, meta}` return shape are used identically in Tasks 2, 3, and 4; `Metric` fields (`id,name,description,unit,source,build`) are consistent; grouped rows use key `bucket` in both the builder (Task 3) and its test.
