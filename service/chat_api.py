"""Shared, searchable chat archive endpoints (owner role, gated by INTERNAL_API_TOKEN).

The chat schema is NEVER granted to rm_readonly — the assistant must not read past
sessions. These endpoints run on the owner DATABASE_URL. Identity is supplied by the
trusted Vercel forward (it verified the Clerk token); we never read identity from an
untrusted client.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel

router = APIRouter()

_ENV_PATH = Path.home() / ".radio-milwaukee" / ".env"
_TITLE_MAX = 120
LIST_LIMIT = 50
SEARCH_LIMIT = 30


class ChatMessageIn(BaseModel):
    seq: int
    role: str
    content: str = ""
    tool_calls: list[Any] | None = None


class ChatThreadIn(BaseModel):
    thread_id: str
    clerk_user_id: str
    user_email: str | None = None
    title: str | None = None
    messages: list[ChatMessageIn]


def _title_from(t: ChatThreadIn) -> str:
    if t.title:
        return t.title[:_TITLE_MAX]
    first_user = next((m for m in t.messages if m.role == "user"), None)
    text = (first_user.content if first_user else "").strip() or "(untitled)"
    return text[:_TITLE_MAX]


def _owner_dsn() -> str:
    if not os.environ.get("DATABASE_URL") and _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL not set (owner role)")
    return dsn


def save_thread(payload: dict) -> dict:
    """Idempotent upsert of a thread + its messages. Re-saving replaces the
    thread's messages (delete-then-insert) so re-posting the same thread never
    duplicates rows."""
    t = ChatThreadIn(**payload)
    title = _title_from(t)
    with psycopg.connect(_owner_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat.threads
                    (thread_id, clerk_user_id, user_email, title, message_count, updated_at)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (thread_id) DO UPDATE SET
                    user_email = EXCLUDED.user_email,
                    title = EXCLUDED.title,
                    message_count = EXCLUDED.message_count,
                    updated_at = now()
                """,
                (t.thread_id, t.clerk_user_id, t.user_email, title, len(t.messages)),
            )
            cur.execute("DELETE FROM chat.messages WHERE thread_id = %s", (t.thread_id,))
            for m in t.messages:
                cur.execute(
                    """
                    INSERT INTO chat.messages
                        (message_id, thread_id, seq, role, content, tool_calls)
                    VALUES (gen_random_uuid(), %s, %s, %s, %s, %s)
                    """,
                    (t.thread_id, m.seq, m.role, m.content,
                     Jsonb(m.tool_calls) if m.tool_calls is not None else None),
                )
        conn.commit()
    return {"thread_id": t.thread_id, "message_count": len(t.messages)}


def _jsonable(v: object) -> object:
    from datetime import date, datetime
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def list_threads(limit: int = LIST_LIMIT) -> list[dict]:
    with psycopg.connect(_owner_dsn()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT thread_id::text, title, user_email, message_count, updated_at
                FROM chat.threads ORDER BY updated_at DESC LIMIT %s
                """,
                (min(limit, 200),),
            )
            return [{k: _jsonable(v) for k, v in r.items()} for r in cur.fetchall()]


def search_chats(q: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """Full-text search over messages; returns distinct threads with a snippet.
    websearch_to_tsquery supports quotes / OR / -term. Falls back to trigram
    similarity on content when the tsquery yields nothing."""
    fts = """
        SELECT DISTINCT ON (t.thread_id)
               t.thread_id::text, t.title, t.user_email, t.updated_at,
               ts_headline('english', m.content, websearch_to_tsquery('english', %(q)s),
                           'MaxFragments=1,MaxWords=18,MinWords=5') AS snippet,
               ts_rank(m.search_tsv, websearch_to_tsquery('english', %(q)s)) AS rank
        FROM chat.messages m JOIN chat.threads t ON t.thread_id = m.thread_id
        WHERE m.search_tsv @@ websearch_to_tsquery('english', %(q)s)
        ORDER BY t.thread_id, rank DESC
    """
    trgm = """
        SELECT DISTINCT ON (t.thread_id)
               t.thread_id::text, t.title, t.user_email, t.updated_at,
               left(m.content, 160) AS snippet,
               similarity(m.content, %(q)s) AS rank
        FROM chat.messages m JOIN chat.threads t ON t.thread_id = m.thread_id
        WHERE m.content %% %(q)s
        ORDER BY t.thread_id, rank DESC
    """
    with psycopg.connect(_owner_dsn()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT * FROM ({fts}) s ORDER BY s.rank DESC, s.updated_at DESC LIMIT %(lim)s",
                        {"q": q, "lim": min(limit, 100)})
            rows = cur.fetchall()
            if not rows:
                cur.execute(f"SELECT * FROM ({trgm}) s ORDER BY s.rank DESC, s.updated_at DESC LIMIT %(lim)s",
                            {"q": q, "lim": min(limit, 100)})
                rows = cur.fetchall()
    return [{k: _jsonable(v) for k, v in r.items() if k != "rank"} for r in rows]


def get_thread(thread_id: str) -> dict | None:
    with psycopg.connect(_owner_dsn()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT thread_id::text, title, user_email, message_count, created_at, updated_at "
                "FROM chat.threads WHERE thread_id = %s", (thread_id,))
            thread = cur.fetchone()
            if not thread:
                return None
            cur.execute(
                "SELECT seq, role, content, tool_calls FROM chat.messages "
                "WHERE thread_id = %s ORDER BY seq", (thread_id,))
            msgs = cur.fetchall()
    return {
        "thread": {k: _jsonable(v) for k, v in thread.items()},
        "messages": [{k: _jsonable(v) for k, v in m.items()} for m in msgs],
    }


@router.get("/api/chats/{thread_id}")
def get_chat_detail(thread_id: str) -> dict:
    try:
        out = get_thread(thread_id)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if out is None:
        raise HTTPException(status_code=404, detail="thread not found")
    return out


@router.get("/api/chats")
def get_chats(q: str | None = None, limit: int = LIST_LIMIT) -> list[dict]:
    try:
        if q and q.strip():
            return search_chats(q.strip(), limit=SEARCH_LIMIT)   # Task 4
        return list_threads(limit=limit)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/api/chats")
def post_chat(payload: ChatThreadIn) -> dict:
    try:
        return save_thread(payload.model_dump())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except psycopg.Error as e:
        raise HTTPException(status_code=400, detail=f"chat save failed: {e.sqlstate or str(e)}")
