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


@router.post("/api/chats")
def post_chat(payload: ChatThreadIn) -> dict:
    try:
        return save_thread(payload.model_dump())
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except psycopg.Error as e:
        raise HTTPException(status_code=400, detail=f"chat save failed: {e.sqlstate or str(e)}")
