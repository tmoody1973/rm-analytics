"""Newsletter content retrieval for the assistant (Phase B / MOO-177).

GET /api/newsletter-content/{campaign_id}
    Return one newsletter's body text (length-capped) plus its LLM-derived tags
    and the subject/send_time from staging. A dedicated tool — instead of raw
    query_sql — so a long body can't blow the agent's context: plain_text is
    capped here and a `truncated` flag tells the agent when it was clipped.

Runs on the rm_readonly role (DATABASE_URL_RO), same as ask-sql. email_esp is on
the read-only allowlist; funraise is not, so there is no donor-data path here.
Newsletter content is published marketing — no PII concern.
"""
from __future__ import annotations

from datetime import date, datetime

import psycopg
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row

from .ask_sql_api import _ro_dsn

router = APIRouter()

# Cap the body so a multi-thousand-word newsletter can't flood the agent context.
MAX_PLAIN_TEXT_CHARS = 8000
STATEMENT_TIMEOUT_MS = 15000

_QUERY = """
    SELECT c.campaign_id, c.plain_text, c.word_count,
           e.content_type, e.primary_theme, e.topics, e.featured_artists,
           s.subject_line, s.send_time
    FROM email_esp.fact_campaign_content c
    LEFT JOIN email_esp.fact_campaign_enrichment e ON e.campaign_id = c.campaign_id
    LEFT JOIN email_esp.stg_campaigns_report    s ON s.id          = c.campaign_id
    WHERE c.campaign_id = %s
"""


def _iso(v: object) -> object:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def shape_row(row: dict) -> dict:
    """Project a DB row into the assistant-facing response, capping the body.

    Pure — no I/O — so the capping/null logic is unit-testable without a DB.
    """
    body = row.get("plain_text") or ""
    return {
        "campaign_id": row["campaign_id"],
        "subject_line": row.get("subject_line"),
        "send_time": _iso(row.get("send_time")),
        "word_count": row.get("word_count"),
        "content_type": row.get("content_type"),
        "primary_theme": row.get("primary_theme"),
        "topics": row.get("topics") or [],
        "featured_artists": row.get("featured_artists") or [],
        "plain_text": body[:MAX_PLAIN_TEXT_CHARS],
        "truncated": len(body) > MAX_PLAIN_TEXT_CHARS,
    }


def fetch_newsletter_content(campaign_id: str) -> dict | None:
    """Look up one campaign's content + tags on the read-only role.

    Returns the shaped response, or None when no content row exists.
    """
    with psycopg.connect(_ro_dsn()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
            cur.execute(_QUERY, (campaign_id,))
            row = cur.fetchone()
    return shape_row(row) if row else None


@router.get("/api/newsletter-content/{campaign_id}")
def get_newsletter_content(campaign_id: str) -> dict:
    """Return one newsletter's body + tags, or 404 if we have no content for it."""
    try:
        result = fetch_newsletter_content(campaign_id)
    except psycopg.OperationalError:
        raise HTTPException(status_code=503, detail="database unavailable")
    except RuntimeError as exc:  # _ro_dsn: DATABASE_URL_RO not configured
        raise HTTPException(status_code=503, detail=str(exc))
    except psycopg.Error as exc:
        raise HTTPException(status_code=400, detail=f"query error: {exc.sqlstate or str(exc)}")
    if result is None:
        raise HTTPException(status_code=404, detail="no newsletter content for that campaign_id")
    return result
