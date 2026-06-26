# Phase 0b — Read-only Neon role + guarded ask-sql Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the AI assistant a safe SQL fallback — a dedicated read-only Neon role plus a guarded `POST /api/ask-sql` endpoint — that can never write or read donor PII.

**Architecture:** Two independent safety layers. (1) A `rm_readonly` Postgres role with `SELECT` only on an allowlist of non-PII schemas (`funraise` excluded) — the authoritative boundary. (2) A FastAPI validator that fail-fast rejects non-`SELECT`/multi-statement/off-allowlist SQL and injects a row `LIMIT`, then runs on that role via `DATABASE_URL_RO`.

**Tech Stack:** Python 3.12, FastAPI, psycopg3, pytest. Mirrors `service/metric_api.py` and `loaders/_common.py`.

## Global Constraints

- Python 3.12; `import psycopg` (psycopg3), never psycopg2. Type hints on signatures.
- Allowlist schemas (verbatim, keep role grants and validator in sync): `wms, nielsen, ga, meta_organic, meta_ads, email_esp, finance, dim, marts`.
- `funraise` is **never** granted and **always** rejected by the validator.
- `MAX_ROWS = 1000`; `STATEMENT_TIMEOUT_MS = 15000`.
- No secret (password, full conn string) committed to git. `DATABASE_URL_RO` lives only in `~/.radio-milwaukee/.env` (local) and the Fly secret.
- Do not touch `service/dashboard_api.py` or `dashboard/**`.
- RO connection helper loads `~/.radio-milwaukee/.env` if `DATABASE_URL_RO` not already set (mirror `_common.get_db_connection`).

---

### Task 1: Read-only role migration

**Files:**
- Create: `schema/016_readonly_role.sql`

**Interfaces:**
- Produces: a `rm_readonly` LOGIN role with SELECT on the 9 allowlist schemas, role-level `default_transaction_read_only=on` and `statement_timeout='15s'`. (Password + apply-to-Neon + Fly secret are done by the controller out-of-band, NOT in this task.)

- [ ] **Step 1: Write the migration file**

Create `schema/016_readonly_role.sql`:

```sql
-- 016_readonly_role.sql — MOO-173 Phase 0b
-- Dedicated read-only role for the AI assistant's guarded SQL fallback.
-- SELECT only, on an allowlist of NON-PII schemas. The funraise (donor) schema
-- is deliberately omitted — donor data reaches the assistant only as metric
-- aggregates. This role is the AUTHORITATIVE safety boundary; the app-layer
-- validator in service/ask_sql_api.py is a second, fail-fast layer.
--
-- Password is set out-of-band (Neon MCP / console) and stored ONLY in the Fly
-- secret DATABASE_URL_RO and ~/.radio-milwaukee/.env — never in this file.

-- 1. Role (idempotent).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rm_readonly') THEN
    CREATE ROLE rm_readonly LOGIN;
  END IF;
END
$$;

-- 2. Hard read-only + finite timeout at the role level.
ALTER ROLE rm_readonly SET default_transaction_read_only = on;
ALTER ROLE rm_readonly SET statement_timeout = '15s';

-- 3. SELECT on each allowlisted schema (existing + future tables).
GRANT USAGE ON SCHEMA wms          TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA wms          TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA wms          GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA nielsen      TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA nielsen      TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA nielsen      GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA ga           TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA ga           TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA ga           GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA meta_organic TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA meta_organic TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA meta_organic GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA meta_ads     TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA meta_ads     TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA meta_ads     GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA email_esp    TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA email_esp    TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA email_esp    GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA finance      TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA finance      TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA finance      GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA dim          TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA dim          TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA dim          GRANT SELECT ON TABLES TO rm_readonly;

GRANT USAGE ON SCHEMA marts        TO rm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA marts        TO rm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA marts        GRANT SELECT ON TABLES TO rm_readonly;

-- 4. Defensive: ensure no funraise (donor) access, even if ever granted.
REVOKE ALL ON ALL TABLES IN SCHEMA funraise FROM rm_readonly;
REVOKE ALL ON SCHEMA funraise FROM rm_readonly;
```

- [ ] **Step 2: Verify the file is valid SQL (syntax sanity)**

Run: `python -c "open('schema/016_readonly_role.sql').read(); print('ok')"`
Expected: `ok` (the migration is applied to live Neon by the controller, not here).

- [ ] **Step 3: Commit**

```bash
git add schema/016_readonly_role.sql
git commit -m "feat: read-only rm_readonly Neon role (SELECT allowlist; funraise excluded)"
```

---

### Task 2: SQL validator + ask-sql endpoint

**Files:**
- Create: `service/ask_sql_api.py`
- Modify: `service/main.py` (register the router)
- Test: `tests/test_ask_sql.py` (Task 3 adds cases; create the file here only if needed for import)

**Interfaces:**
- Consumes: `DATABASE_URL_RO` env (set by controller after Task 1).
- Produces: `validate_sql(raw: str) -> str` (raises `SqlValidationError`), `SqlValidationError(ValueError)`, `ALLOWED_SCHEMAS: frozenset[str]`, `MAX_ROWS: int`, and FastAPI `router` with `POST /api/ask-sql` taking `{"sql": str}` returning `{"data": [...], "meta": {...}}`.

- [ ] **Step 1: Write `service/ask_sql_api.py`**

```python
"""Guarded read-only SQL endpoint for the assistant's fallback path (MOO-173).

The assistant prefers registered metrics; for the long tail it may emit a single
read-only SELECT. validate_sql() enforces: one statement, SELECT/WITH only, no
DDL/DML keywords, every relation schema-qualified into an allowlist of non-PII
schemas, a row LIMIT injected/capped. The query runs on the dedicated
rm_readonly Neon role (DATABASE_URL_RO), which physically cannot write or read
donor (funraise) data — so the role, not this validator, is the hard boundary.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel

router = APIRouter()

# Keep in sync with the grants in schema/016_readonly_role.sql. funraise is
# intentionally absent — donor data is exposed only as metric aggregates.
ALLOWED_SCHEMAS: frozenset[str] = frozenset({
    "wms", "nielsen", "ga", "meta_organic", "meta_ads",
    "email_esp", "finance", "dim", "marts",
})

MAX_ROWS = 1000
STATEMENT_TIMEOUT_MS = 15000
ENV_PATH = Path.home() / ".radio-milwaukee" / ".env"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|create|drop|alter|truncate|grant|revoke|"
    r"comment|copy|call|do|vacuum|analyze|reindex|cluster|refresh|set|reset)\b",
    re.IGNORECASE,
)
_CTE_NAME = re.compile(r"(?:\bwith\b|,)\s+([a-z_]\w*)\s+as\s*\(", re.IGNORECASE)
_REL = re.compile(r"\b(?:from|join)\s+([a-z_]\w*)(?:\.([a-z_]\w*))?", re.IGNORECASE)
_LIMIT = re.compile(r"\blimit\b\s+(\d+)", re.IGNORECASE)


class SqlValidationError(ValueError):
    """Raised when a candidate SQL string fails a guardrail check."""


class AskSqlRequest(BaseModel):
    sql: str


def _strip_comments(sql: str) -> str:
    return _LINE_COMMENT.sub(" ", _BLOCK_COMMENT.sub(" ", sql))


def _check_relations(cleaned: str) -> bool:
    """Reject funraise, off-allowlist schemas, and bare (non-CTE) tables.

    Returns True if at least one FROM/JOIN relation was seen.
    """
    if "funraise" in cleaned.lower():
        raise SqlValidationError("funraise (donor) data is not queryable via SQL")
    cte_names = {m.group(1).lower() for m in _CTE_NAME.finditer(cleaned)}
    saw_relation = False
    for m in _REL.finditer(cleaned):
        saw_relation = True
        schema, table = m.group(1).lower(), (m.group(2) or "").lower()
        if table:  # schema.table
            if schema not in ALLOWED_SCHEMAS:
                raise SqlValidationError(f"schema not allowed: {schema}")
        elif schema not in cte_names:  # bare identifier, not a CTE
            raise SqlValidationError(f"tables must be schema-qualified: {schema}")
    return saw_relation


def _apply_limit(cleaned: str) -> str:
    m = _LIMIT.search(cleaned)
    if m:
        n = int(m.group(1))
        if n > MAX_ROWS:
            return cleaned[: m.start(1)] + str(MAX_ROWS) + cleaned[m.end(1):]
        return cleaned
    return f"{cleaned} LIMIT {MAX_ROWS}"


def validate_sql(raw: str) -> str:
    """Return a safe, LIMIT-capped SQL string, or raise SqlValidationError."""
    if not raw or not raw.strip():
        raise SqlValidationError("empty SQL")

    cleaned = _strip_comments(raw).strip()
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if ";" in cleaned:
        raise SqlValidationError("multiple statements are not allowed")
    if not cleaned:
        raise SqlValidationError("empty SQL")

    first = cleaned.split(None, 1)[0].lower()
    if first not in ("select", "with"):
        raise SqlValidationError("only SELECT / WITH queries are allowed")

    bad = _FORBIDDEN.search(cleaned)
    if bad:
        raise SqlValidationError(f"forbidden keyword: {bad.group(0).lower()}")

    _check_relations(cleaned)
    return _apply_limit(cleaned)


def _jsonable(v: object):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _ro_dsn() -> str:
    if not os.environ.get("DATABASE_URL_RO") and ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    dsn = os.environ.get("DATABASE_URL_RO")
    if not dsn:
        raise RuntimeError("DATABASE_URL_RO not set (read-only role connection)")
    return dsn


def run_safe_sql(raw: str) -> dict:
    """Validate then execute on the read-only role. Returns {data, meta}."""
    safe = validate_sql(raw)
    with psycopg.connect(_ro_dsn()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
            cur.execute(safe)
            rows = cur.fetchall()
    data = [{k: _jsonable(v) for k, v in r.items()} for r in rows]
    return {"data": data, "meta": {"rows": len(data), "sql": safe,
                                    "via": "read-only SQL"}}


@router.post("/api/ask-sql")
def ask_sql(req: AskSqlRequest) -> dict:
    try:
        return run_safe_sql(req.sql)
    except SqlValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except psycopg.errors.InsufficientPrivilege:
        raise HTTPException(status_code=403, detail="permission denied for relation")
    except psycopg.Error as e:
        raise HTTPException(status_code=400, detail=f"query error: {e.sqlstate}")
```

- [ ] **Step 2: Register the router in `service/main.py`**

Find the existing block (around line 58):

```python
from . import metric_api

app.include_router(metric_api.router)
```

Replace it with:

```python
from . import ask_sql_api, metric_api

app.include_router(metric_api.router)
app.include_router(ask_sql_api.router)
```

- [ ] **Step 3: Verify import works**

Run: `python -c "from service.ask_sql_api import validate_sql; print(validate_sql('SELECT 1'))"`
Expected: prints `SELECT 1 LIMIT 1000`

- [ ] **Step 4: Commit**

```bash
git add service/ask_sql_api.py service/main.py
git commit -m "feat: guarded /api/ask-sql endpoint + SQL validator (RO role)"
```

---

### Task 3: Guardrail tests

**Files:**
- Create: `tests/test_ask_sql.py`

**Interfaces:**
- Consumes: `validate_sql`, `SqlValidationError` from `service.ask_sql_api`; `TestClient(app)` from `service.main`; live `DATABASE_URL_RO` for the two integration tests (skipped if unset).

- [ ] **Step 1: Write `tests/test_ask_sql.py`**

```python
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
```

- [ ] **Step 2: Run the new tests**

Run: `python -m pytest tests/test_ask_sql.py -v`
Expected: all pass (the live aggregate test is skipped only if `DATABASE_URL_RO` is unset).

- [ ] **Step 3: Run the full suite (no regressions)**

Run: `python -m pytest -q`
Expected: prior 29 + new tests all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_ask_sql.py
git commit -m "test: ask-sql guardrails (write/DDL/multi/off-allowlist/funraise) + live RO"
```

---

## Controller-only steps (NOT subagent tasks — involve secrets/infra)

1. Apply `schema/016_readonly_role.sql` to live Neon via Neon MCP (project `morning-frost-30675590`).
2. `ALTER ROLE rm_readonly PASSWORD '<generated>'` via MCP (password never committed).
3. Build `DATABASE_URL_RO` from the existing host + `rm_readonly` creds; write to `~/.radio-milwaukee/.env`; `flyctl secrets set DATABASE_URL_RO=… --app rm-data-loader`.
4. Prove the role boundary directly: connect as `rm_readonly`, confirm `SELECT … FROM funraise.dim_supporters` → permission denied, and `INSERT`/`UPDATE` denied, and an allowlisted aggregate returns rows.
