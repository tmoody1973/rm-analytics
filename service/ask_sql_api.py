"""Guarded read-only SQL endpoint for the assistant's fallback path (MOO-173).

The assistant prefers registered metrics; for the long tail it may emit a single
read-only SELECT. validate_sql() enforces: one statement, SELECT/WITH only, no
DDL/DML keywords, and a best-effort FROM/JOIN allowlist check. funraise
(de-identified donor data) is on the allowlist; the endpoint itself is gated
behind INTERNAL_API_TOKEN. The rm_readonly Neon role (DATABASE_URL_RO) is the
AUTHORITATIVE allowlist enforcer — exotic join forms and comma-joins not caught
by the regex are blocked by the role's permission denial, surfaced as 403.
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

# Keep in sync with the grants in schema/016 + schema/018_funraise_readonly_grant.sql
# + schema/021_social_intel_grant.sql.
# funraise (de-identified donor data) is included; the endpoint is gated behind
# INTERNAL_API_TOKEN and the system prompt forbids surfacing individual PII.
ALLOWED_SCHEMAS: frozenset[str] = frozenset({
    "wms", "nielsen", "ga", "meta_organic", "meta_ads",
    "email_esp", "finance", "dim", "marts", "funraise", "social_intel",
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
_CTE_NAME = re.compile(r"(?:\bwith\b|,)\s+([a-z_]\w*)(?:\s*\([^)]*\))?\s+as\s*\(", re.IGNORECASE)
_REL = re.compile(r"\b(?:from|join)\s+([a-z_]\w*)(?:\.([a-z_]\w*))?", re.IGNORECASE)


class SqlValidationError(ValueError):
    """Raised when a candidate SQL string fails a guardrail check."""


class AskSqlRequest(BaseModel):
    sql: str


def _strip_comments(sql: str) -> str:
    return _LINE_COMMENT.sub(" ", _BLOCK_COMMENT.sub(" ", sql))


def _check_relations(cleaned: str) -> bool:
    """Reject off-allowlist schemas and bare (non-CTE) tables.

    funraise is now on the allowlist (de-identified donor data); the rm_readonly
    role and the INTERNAL_API_TOKEN gate are the authoritative enforcers.
    Returns True if at least one FROM/JOIN relation was seen.
    """
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


def _cap_rows(cleaned: str) -> str:
    """Bound the OUTER result to MAX_ROWS by wrapping the query in a subquery.

    Wrapping (vs. editing an inner LIMIT) guarantees the cap holds no matter
    what LIMIT/FETCH a CTE or subquery contains, and never rewrites the user's
    own SQL or string literals. PostgreSQL permits a WITH clause inside the
    wrapped subquery, so plain SELECT and WITH queries wrap identically (verified
    on Neon). The read-only role's statement_timeout is the time backstop; this
    is the row backstop.
    """
    return f"SELECT * FROM (\n{cleaned}\n) AS _ask_sql_capped LIMIT {MAX_ROWS}"


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
    return _cap_rows(cleaned)


def _jsonable(v: object) -> object:
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
    except psycopg.OperationalError:
        raise HTTPException(status_code=503, detail="database unavailable")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except psycopg.Error as e:
        raise HTTPException(status_code=400, detail=f"query error: {e.sqlstate or str(e)}")
