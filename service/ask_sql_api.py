"""Guarded read-only SQL endpoint for the assistant's fallback path (MOO-173).

The assistant prefers registered metrics; for the long tail it may emit a single
read-only SELECT. validate_sql() enforces: one statement, SELECT/WITH only, no
DDL/DML keywords, and a best-effort FROM/JOIN allowlist check on non-PII schemas.
The rm_readonly Neon role (DATABASE_URL_RO) is the AUTHORITATIVE allowlist and
funraise enforcer — exotic join forms and comma-joins not caught by the regex are
blocked by the role's permission denial, surfaced as 403.
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
_CTE_NAME = re.compile(r"(?:\bwith\b|,)\s+([a-z_]\w*)(?:\s*\([^)]*\))?\s+as\s*\(", re.IGNORECASE)
_REL = re.compile(r"\b(?:from|join)\s+([a-z_]\w*)(?:\.([a-z_]\w*))?", re.IGNORECASE)


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


def _cap_rows(cleaned: str) -> str:
    """Bound the OUTER result to MAX_ROWS by wrapping the query in a subquery.

    Wrapping (vs. editing an inner LIMIT) guarantees the cap holds no matter
    what LIMIT/FETCH a CTE or subquery contains, and never rewrites the
    user's own SQL/literals. The read-only role's statement_timeout is the
    time backstop; this is the row backstop.

    PostgreSQL does not allow a WITH clause inside a subquery's FROM, so for
    WITH queries the CTE block is promoted to the outer SELECT:
      WITH <ctes> SELECT * FROM (<select-body>) AS _ask_sql_capped LIMIT n
    For plain SELECT queries the whole query becomes the subquery.
    """
    first = cleaned.split(None, 1)[0].lower()
    if first == "with":
        # Split "WITH <ctes> SELECT ..." into the CTE prefix and the SELECT body.
        # Find the SELECT that follows the last closing parenthesis of the CTE list.
        # Strategy: scan for the outermost-level SELECT keyword after all CTE parens.
        depth = 0
        i = 0
        # Skip past "WITH"
        while i < len(cleaned) and cleaned[i:i+4].lower() != "with":
            i += 1
        i += 4  # past WITH
        # Walk through CTE definitions (balanced parens) to find where SELECT starts
        in_cte_header = True
        while i < len(cleaned) and in_cte_header:
            ch = cleaned[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    # End of a CTE body — check what follows (comma = more CTEs, else SELECT)
                    j = i + 1
                    while j < len(cleaned) and cleaned[j].isspace():
                        j += 1
                    if j < len(cleaned) and cleaned[j] == ",":
                        i = j + 1  # skip comma, continue to next CTE
                        continue
                    else:
                        # No more CTEs — everything from j onward is the SELECT body
                        cte_prefix = cleaned[:i + 1]  # "WITH ... )"
                        select_body = cleaned[j:].strip()
                        return (
                            f"{cte_prefix}\n"
                            f"SELECT * FROM (\n{select_body}\n) AS _ask_sql_capped LIMIT {MAX_ROWS}"
                        )
            i += 1
    # Plain SELECT (or fallback)
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
