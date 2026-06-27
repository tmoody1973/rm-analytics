# Chat History Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every assistant conversation to Neon and give any signed-in user a read-only, full-text-searchable History tab.

**Architecture:** Client-side capture (CopilotKit v2 `useAgent` messages) → dashboard Vercel function `/api/chats` (verifies Clerk, stamps identity) → Fly FastAPI `chat_api` (gated by `INTERNAL_API_TOKEN`, owner `DATABASE_URL`) → Neon `chat` schema (threads + messages, `tsvector` + `pg_trgm` search). The `chat` schema is never granted to `rm_readonly`, so the assistant cannot read past sessions.

**Tech Stack:** Python 3.12 / FastAPI / psycopg3 (`import psycopg`); React + Vite + vitest; `@clerk/react` (client `getToken`) + `@clerk/backend` (`verifyToken`); Neon Postgres.

**Design doc:** `docs/plans/2026-06-27-chat-history-archive-design.md`.

## Global Constraints

- psycopg3 import is `import psycopg` (NOT psycopg2); use `cursor.executemany`/parameterized SQL, never string interpolation of values.
- Writes use the owner `DATABASE_URL` (resolved from env or `~/.radio-milwaukee/.env`); `rm_readonly` is read-only and must NOT be used here.
- All `chat_api` routes are gated by `INTERNAL_API_TOKEN` (wired in `service/main.py` via `Depends(require_internal_token)` — same mechanism as the other tool endpoints).
- The browser NEVER calls Fly directly and NEVER holds `INTERNAL_API_TOKEN`. Browser → Vercel `/api/chats` (Clerk token) → Fly (internal token).
- Identity (`clerk_user_id`, `user_email`) is taken ONLY from the verified Clerk token in the Vercel function — never from a client-supplied body field.
- Store transcript + `tool_calls` (the SQL); do NOT store raw tool result rows.
- Backend tests: `source .venv/bin/activate && python -m pytest -q`. Frontend: `cd dashboard && npm test`.
- Neon project `morning-frost-30675590`, db `neondb`. DB-dependent tests skip when `DATABASE_URL` is absent (mirror `tests/test_catalog_endpoints.py::_db_available`).

---

### Task 1: `chat` schema migration

**Files:**
- Create: `schema/019_chat.sql`
- Apply: via Neon MCP `run_sql_transaction` (project `morning-frost-30675590`, db `neondb`)

**Interfaces:**
- Produces: schema `chat` with tables `chat.threads` and `chat.messages` and their indexes (consumed by every later backend task).

- [ ] **Step 1: Write the migration**

```sql
-- 019_chat.sql — shared, searchable assistant chat archive.
-- App data (NOT a source schema). NEVER granted to rm_readonly: the assistant
-- must not be able to read past sessions. Served only by owner-role Fly endpoints.
CREATE SCHEMA IF NOT EXISTS chat;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS chat.threads (
    thread_id     UUID PRIMARY KEY,
    clerk_user_id TEXT NOT NULL,
    user_email    TEXT,
    title         TEXT,
    message_count INT  NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat.messages (
    message_id  UUID PRIMARY KEY,
    thread_id   UUID NOT NULL REFERENCES chat.threads(thread_id) ON DELETE CASCADE,
    seq         INT  NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content     TEXT NOT NULL DEFAULT '',
    tool_calls  JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_tsv  TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    UNIQUE (thread_id, seq)
);

CREATE INDEX IF NOT EXISTS ix_chat_messages_tsv    ON chat.messages USING GIN (search_tsv);
CREATE INDEX IF NOT EXISTS ix_chat_messages_trgm   ON chat.messages USING GIN (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_chat_threads_updated ON chat.threads (updated_at DESC);
```

- [ ] **Step 2: Apply via Neon MCP**

Use `mcp__Neon__run_sql_transaction` with `projectId: "morning-frost-30675590"`, `databaseName: "neondb"`, and each statement above as an array element.
Expected: an array of empty results (no error).

- [ ] **Step 3: Verify the tables exist**

Run `mcp__Neon__run_sql` with:
```sql
SELECT table_name FROM information_schema.tables WHERE table_schema='chat' ORDER BY 1;
```
Expected: `threads`, `messages`.

- [ ] **Step 4: Commit**

```bash
git add schema/019_chat.sql
git commit -m "feat(chat): schema for shared searchable chat archive"
```

---

### Task 2: `chat_api.save_thread` — idempotent upsert

**Files:**
- Create: `service/chat_api.py`
- Test: `tests/test_chat_api.py`

**Interfaces:**
- Consumes: `service/internal_auth.require_internal_token` (wired in Task 6), owner DSN resolver.
- Produces:
  - `router = APIRouter()` with `POST /api/chats`.
  - `save_thread(payload: dict) -> dict` returning `{"thread_id": str, "message_count": int}`.
  - Pydantic models `ChatMessageIn(seq:int, role:str, content:str, tool_calls:list|None)` and `ChatThreadIn(thread_id:str, clerk_user_id:str, user_email:str|None, title:str|None, messages:list[ChatMessageIn])`.
  - `_owner_dsn() -> str` (resolves `DATABASE_URL` from env or `~/.radio-milwaukee/.env`).

- [ ] **Step 1: Write the failing test (validation, no DB)**

```python
# tests/test_chat_api.py
from __future__ import annotations
import os
from pathlib import Path
import pytest
from service.chat_api import ChatThreadIn, _title_from

_ENV = Path.home() / ".radio-milwaukee" / ".env"

def _db() -> bool:
    if os.environ.get("DATABASE_URL"):
        return True
    if _ENV.exists():
        from dotenv import dotenv_values
        return bool(dotenv_values(_ENV).get("DATABASE_URL"))
    return False

def test_title_falls_back_to_first_user_message():
    t = ChatThreadIn(
        thread_id="11111111-1111-1111-1111-111111111111",
        clerk_user_id="user_1", user_email="a@b.org", title=None,
        messages=[{"seq": 0, "role": "user", "content": "How many donors?"}],
    )
    assert _title_from(t) == "How many donors?"

def test_title_truncates_long_first_message():
    long = "x" * 200
    t = ChatThreadIn(
        thread_id="11111111-1111-1111-1111-111111111111",
        clerk_user_id="u", user_email=None, title=None,
        messages=[{"seq": 0, "role": "user", "content": long}],
    )
    assert len(_title_from(t)) <= 120
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_chat_api.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'service.chat_api'`.

- [ ] **Step 3: Write minimal implementation**

```python
# service/chat_api.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_chat_api.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Add the DB-gated idempotency test**

```python
# append to tests/test_chat_api.py
_TID = "22222222-2222-2222-2222-222222222222"

def _sample(n_msgs: int) -> dict:
    return {
        "thread_id": _TID, "clerk_user_id": "user_test", "user_email": "t@rm.org",
        "title": None,
        "messages": [
            {"seq": i, "role": "user" if i % 2 == 0 else "assistant",
             "content": f"msg {i} donors", "tool_calls": None}
            for i in range(n_msgs)
        ],
    }

@pytest.mark.skipif(not _db(), reason="DATABASE_URL not set")
def test_resave_is_idempotent():
    from service.chat_api import save_thread, _owner_dsn
    import psycopg
    save_thread(_sample(3))
    save_thread(_sample(3))  # re-save same thread
    with psycopg.connect(_owner_dsn()) as c, c.cursor() as cur:
        cur.execute("SELECT count(*) FROM chat.messages WHERE thread_id=%s", (_TID,))
        assert cur.fetchone()[0] == 3   # not 6
        cur.execute("DELETE FROM chat.threads WHERE thread_id=%s", (_TID,))
        c.commit()
```

- [ ] **Step 6: Run it**

Run: `python -m pytest tests/test_chat_api.py -q`
Expected: PASS (3 passed, or 2 passed + 1 skipped if no DB).

- [ ] **Step 7: Commit**

```bash
git add service/chat_api.py tests/test_chat_api.py
git commit -m "feat(chat): idempotent thread+messages upsert endpoint"
```

---

### Task 3: `GET /api/chats` — recent thread list

**Files:**
- Modify: `service/chat_api.py`
- Test: `tests/test_chat_api.py`

**Interfaces:**
- Produces: `list_threads(limit:int) -> list[dict]` and route `GET /api/chats` returning `[{thread_id, title, user_email, message_count, updated_at}]` newest first. (When `q` is present the route delegates to search — Task 4.)

- [ ] **Step 1: Write the failing DB-gated test**

```python
# append to tests/test_chat_api.py
@pytest.mark.skipif(not _db(), reason="DATABASE_URL not set")
def test_list_threads_returns_saved_thread_newest_first():
    from service.chat_api import save_thread, list_threads, _owner_dsn
    import psycopg
    save_thread(_sample(2))
    rows = list_threads(limit=50)
    assert any(r["thread_id"] == _TID for r in rows)
    r = next(r for r in rows if r["thread_id"] == _TID)
    assert r["message_count"] == 2 and "updated_at" in r
    with psycopg.connect(_owner_dsn()) as c, c.cursor() as cur:
        cur.execute("DELETE FROM chat.threads WHERE thread_id=%s", (_TID,)); c.commit()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_chat_api.py::test_list_threads_returns_saved_thread_newest_first -q`
Expected: FAIL — `ImportError: cannot import name 'list_threads'` (or skip if no DB; if skipped, proceed — the route test in Task 6 also covers it).

- [ ] **Step 3: Implement**

```python
# add to service/chat_api.py
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


@router.get("/api/chats")
def get_chats(q: str | None = None, limit: int = LIST_LIMIT) -> list[dict]:
    try:
        if q and q.strip():
            return search_chats(q.strip(), limit=SEARCH_LIMIT)   # Task 4
        return list_threads(limit=limit)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
```

> NOTE: `get_chats` references `search_chats` — add Task 4 before running the route. If implementing strictly in order, temporarily stub `def search_chats(q, limit=SEARCH_LIMIT): return []` and replace it in Task 4.

- [ ] **Step 4: Add the stub so the module imports**

```python
# temporary, replaced in Task 4
def search_chats(q: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    return []
```

- [ ] **Step 5: Run the test**

Run: `python -m pytest tests/test_chat_api.py -q`
Expected: PASS (or list test skipped without DB).

- [ ] **Step 6: Commit**

```bash
git add service/chat_api.py tests/test_chat_api.py
git commit -m "feat(chat): list recent threads endpoint"
```

---

### Task 4: `GET /api/chats?q=` — full-text search

**Files:**
- Modify: `service/chat_api.py` (replace the `search_chats` stub)
- Test: `tests/test_chat_api.py`

**Interfaces:**
- Produces: `search_chats(q:str, limit:int) -> list[dict]` returning `[{thread_id, title, user_email, updated_at, snippet}]` ranked by relevance then recency. Uses `websearch_to_tsquery` + `ts_headline`; falls back to `pg_trgm` similarity when the tsquery matches nothing.

- [ ] **Step 1: Write the failing DB-gated test**

```python
# append to tests/test_chat_api.py
@pytest.mark.skipif(not _db(), reason="DATABASE_URL not set")
def test_search_finds_thread_by_message_word():
    from service.chat_api import save_thread, search_chats, _owner_dsn
    import psycopg
    save_thread({
        "thread_id": _TID, "clerk_user_id": "u", "user_email": "t@rm.org", "title": None,
        "messages": [{"seq": 0, "role": "user", "content": "underwriting revenue by daypart"}],
    })
    hits = search_chats("underwriting", limit=30)
    assert any(h["thread_id"] == _TID for h in hits)
    assert "snippet" in next(h for h in hits if h["thread_id"] == _TID)
    with psycopg.connect(_owner_dsn()) as c, c.cursor() as cur:
        cur.execute("DELETE FROM chat.threads WHERE thread_id=%s", (_TID,)); c.commit()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_chat_api.py::test_search_finds_thread_by_message_word -q`
Expected: FAIL — stub returns `[]`, so no hit (or skip without DB).

- [ ] **Step 3: Implement (replace the stub)**

```python
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
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest tests/test_chat_api.py -q`
Expected: PASS (or skipped without DB).

- [ ] **Step 5: Commit**

```bash
git add service/chat_api.py tests/test_chat_api.py
git commit -m "feat(chat): full-text search with trigram fallback"
```

---

### Task 5: `GET /api/chats/{thread_id}` — transcript

**Files:**
- Modify: `service/chat_api.py`
- Test: `tests/test_chat_api.py`

**Interfaces:**
- Produces: `get_thread(thread_id:str) -> dict|None` and route `GET /api/chats/{thread_id}` returning `{thread:{...}, messages:[{seq, role, content, tool_calls}]}` ordered by seq; 404 when absent.

- [ ] **Step 1: Failing DB-gated test**

```python
# append to tests/test_chat_api.py
@pytest.mark.skipif(not _db(), reason="DATABASE_URL not set")
def test_get_thread_returns_messages_in_order():
    from service.chat_api import save_thread, get_thread, _owner_dsn
    import psycopg
    save_thread(_sample(3))
    out = get_thread(_TID)
    assert out is not None
    assert [m["seq"] for m in out["messages"]] == [0, 1, 2]
    with psycopg.connect(_owner_dsn()) as c, c.cursor() as cur:
        cur.execute("DELETE FROM chat.threads WHERE thread_id=%s", (_TID,)); c.commit()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_chat_api.py::test_get_thread_returns_messages_in_order -q`
Expected: FAIL — `cannot import name 'get_thread'` (or skip).

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_chat_api.py -q`
Expected: PASS (or skipped without DB).

- [ ] **Step 5: Commit**

```bash
git add service/chat_api.py tests/test_chat_api.py
git commit -m "feat(chat): thread transcript endpoint"
```

---

### Task 6: Wire `chat_api` into the gated service

**Files:**
- Modify: `service/main.py`
- Test: `tests/test_endpoint_gating.py`

**Interfaces:**
- Consumes: `service.chat_api.router`, `require_internal_token`.
- Produces: `/api/chats` reachable only with `X-Internal-Token`.

- [ ] **Step 1: Add the failing gating assertion**

```python
# in tests/test_endpoint_gating.py, extend the parametrized list:
@pytest.mark.parametrize("path", [
    "/api/metrics",
    "/api/metric/streaming_tlh",
    "/api/newsletter-content/abc123",
    "/api/chats",                 # NEW
])
def test_gated_get_returns_401_without_token(real_auth, path):
    assert client.get(path).status_code == 401
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_endpoint_gating.py -q`
Expected: FAIL on `/api/chats` (200 — not yet wired).

- [ ] **Step 3: Wire the router**

```python
# service/main.py — add to the import line and the gated includes:
from . import ask_sql_api, catalog_api, chat_api, metric_api, newsletter_api
# ...
app.include_router(chat_api.router, dependencies=_internal)
```

- [ ] **Step 4: Run**

Run: `python -m pytest tests/test_endpoint_gating.py tests/test_chat_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add service/main.py tests/test_endpoint_gating.py
git commit -m "feat(chat): gate /api/chats behind INTERNAL_API_TOKEN"
```

---

### Task 7: Vercel `/api/chats` proxy (Clerk verify + identity stamp)

**Files:**
- Create: `dashboard/api/chats.ts`
- Test: `dashboard/test/chats-api.test.ts`

**Interfaces:**
- Consumes: `@clerk/backend` `verifyToken`, `process.env.API_BASE`, `process.env.INTERNAL_API_TOKEN`, `process.env.CLERK_SECRET_KEY`.
- Produces: a Vercel handler that (a) 401s unauthenticated requests; (b) on POST, overwrites `clerk_user_id`/`user_email` from the verified token before forwarding to Fly `POST /api/chats`; (c) on GET forwards to Fly `GET /api/chats` (passing `q`/`limit`) or `GET /api/chats/{id}` when `?id=` is present. Exports a pure helper `buildFlyTarget(method, query)` for unit testing URL routing.

- [ ] **Step 1: Write the failing test**

```typescript
// dashboard/test/chats-api.test.ts
import { describe, it, expect } from "vitest";
import { buildFlyTarget } from "../api/chats.js";

describe("buildFlyTarget", () => {
  it("GET with no params → /api/chats", () => {
    expect(buildFlyTarget("GET", {})).toBe("/api/chats");
  });
  it("GET with q → /api/chats?q=...", () => {
    expect(buildFlyTarget("GET", { q: "donors" })).toBe("/api/chats?q=donors");
  });
  it("GET with id → /api/chats/{id} (id wins over q)", () => {
    expect(buildFlyTarget("GET", { id: "abc", q: "x" })).toBe("/api/chats/abc");
  });
  it("POST → /api/chats", () => {
    expect(buildFlyTarget("POST", {})).toBe("/api/chats");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd dashboard && npx vitest run test/chats-api.test.ts`
Expected: FAIL — cannot resolve `../api/chats.js`.

- [ ] **Step 3: Implement**

```typescript
// dashboard/api/chats.ts
/**
 * Vercel proxy for the chat archive. Verifies the Clerk session (any signed-in
 * user — the archive is shared), stamps identity from the token on writes, and
 * forwards to the gated Fly chat endpoints with X-Internal-Token. The browser
 * never holds the internal token and cannot set its own identity.
 */
import type { IncomingMessage, ServerResponse } from "node:http";
import { verifyToken } from "@clerk/backend";

const API_BASE = () =>
  (process.env.API_BASE ?? "https://rm-data-loader.fly.dev").replace(/\/$/, "");
const internalHeaders = (): Record<string, string> => ({
  "X-Internal-Token": process.env.INTERNAL_API_TOKEN ?? "",
});

export function buildFlyTarget(method: string, query: Record<string, string>): string {
  if (method === "GET" && query.id) return `/api/chats/${encodeURIComponent(query.id)}`;
  if (method === "GET" && query.q)
    return `/api/chats?q=${encodeURIComponent(query.q)}${
      query.limit ? `&limit=${encodeURIComponent(query.limit)}` : ""}`;
  return "/api/chats";
}

async function verifiedClaims(req: IncomingMessage): Promise<{ sub: string; email?: string } | null> {
  const secretKey = process.env.CLERK_SECRET_KEY;
  if (!secretKey) return null;
  const header = req.headers["authorization"];
  const token = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : null;
  if (!token) return null;
  try {
    const c = await verifyToken(token, { secretKey }) as Record<string, unknown>;
    return { sub: String(c.sub), email: (c.email as string) ?? undefined };
  } catch {
    return null;
  }
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => resolve(data));
  });
}

export default async function handler(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const claims = await verifiedClaims(req);
  if (!claims) {
    res.statusCode = 401;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ error: "Unauthorized" }));
    return;
  }
  const url = new URL(req.url ?? "", "http://x");
  const query = Object.fromEntries(url.searchParams.entries());
  const target = `${API_BASE()}${buildFlyTarget(req.method ?? "GET", query)}`;

  let init: RequestInit;
  if (req.method === "POST") {
    const raw = await readBody(req);
    const body = raw ? JSON.parse(raw) : {};
    body.clerk_user_id = claims.sub;          // stamp identity from the token
    body.user_email = claims.email ?? null;
    init = { method: "POST",
      headers: { "Content-Type": "application/json", ...internalHeaders() },
      body: JSON.stringify(body) };
  } else {
    init = { method: "GET", headers: internalHeaders() };
  }
  const r = await fetch(target, init);
  const text = await r.text();
  res.statusCode = r.status;
  res.setHeader("Content-Type", "application/json");
  res.end(text);
}

export const config = { api: { bodyParser: false } };
```

- [ ] **Step 4: Run the test**

Run: `cd dashboard && npx vitest run test/chats-api.test.ts`
Expected: PASS (4 passed).

- [ ] **Step 5: Add the Vercel rewrite (if subpaths are used)**

Confirm `dashboard/vercel.json` routes `/api/chats` and `/api/chats/*` to the function (Vercel maps `api/chats.ts` to `/api/chats` automatically; only add a rewrite if `?id=` style is replaced by path segments — this plan uses `?id=`, so no rewrite needed). Verify by reading `dashboard/vercel.json`.

- [ ] **Step 6: Commit**

```bash
git add dashboard/api/chats.ts dashboard/test/chats-api.test.ts
git commit -m "feat(chat): vercel proxy verifies clerk, stamps identity, forwards to fly"
```

---

### Task 8: `<ChatPersistence/>` — capture on turn-complete

**Files:**
- Create: `dashboard/src/chat-persistence.jsx`
- Modify: `dashboard/src/App.jsx` (mount the component + own a stable `threadId`)
- Test: `dashboard/test/chat-persistence.test.ts`

**Interfaces:**
- Consumes: `useAgent({agentId:'default'})` (`agent.messages`, `agent.isRunning`), `@clerk/react` `useAuth().getToken`.
- Produces: pure helper `toSavePayload(threadId, messages) -> {thread_id, messages:[{seq, role, content, tool_calls}]}` and a `<ChatPersistence threadId=.../>` component that POSTs to `/api/chats` once each time `isRunning` transitions true→false.

- [ ] **Step 1: Write the failing test for the payload mapper**

```typescript
// dashboard/test/chat-persistence.test.ts
import { describe, it, expect } from "vitest";
import { toSavePayload } from "../src/chat-persistence.jsx";

describe("toSavePayload", () => {
  it("maps messages to {seq, role, content, tool_calls} and keeps order", () => {
    const msgs = [
      { role: "user", content: "How many donors?" },
      { role: "assistant", content: "14,087.", toolCalls: [{ name: "query_sql", args: { sql: "SELECT ..." } }] },
    ];
    const p = toSavePayload("t-1", msgs);
    expect(p.thread_id).toBe("t-1");
    expect(p.messages.map((m) => m.seq)).toEqual([0, 1]);
    expect(p.messages[0].role).toBe("user");
    expect(p.messages[1].tool_calls).toEqual([{ name: "query_sql", args: { sql: "SELECT ..." } }]);
  });

  it("drops empty trailing assistant placeholders (no content, no tool calls)", () => {
    const msgs = [
      { role: "user", content: "hi" },
      { role: "assistant", content: "" },
    ];
    const p = toSavePayload("t-2", msgs);
    expect(p.messages).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd dashboard && npx vitest run test/chat-persistence.test.ts`
Expected: FAIL — cannot resolve `../src/chat-persistence.jsx`.

- [ ] **Step 3: Implement**

```jsx
// dashboard/src/chat-persistence.jsx
import { useEffect, useRef } from 'react'
import { useAgent } from '@copilotkit/react-core/v2'
import { useAuth } from '@clerk/react'

// Map CopilotKit messages to the save payload. Drops empty trailing assistant
// placeholders (a streamed slot that never filled). tool_calls comes from
// `toolCalls` on the message if present.
export function toSavePayload(threadId, messages) {
  const cleaned = (messages || []).filter((m, i) => {
    const empty = !(m.content && m.content.trim()) && !(m.toolCalls && m.toolCalls.length)
    return !(empty && m.role === 'assistant')
  })
  return {
    thread_id: threadId,
    messages: cleaned.map((m, seq) => ({
      seq,
      role: m.role === 'assistant' ? 'assistant' : 'user',
      content: m.content ?? '',
      tool_calls: m.toolCalls && m.toolCalls.length ? m.toolCalls : null,
    })),
  }
}

// Saves the whole thread once each time a run finishes (isRunning true→false).
export function ChatPersistence({ threadId }) {
  const { agent } = useAgent({ agentId: 'default' })
  const { getToken } = useAuth()
  const wasRunning = useRef(false)

  useEffect(() => {
    const running = !!agent?.isRunning
    if (wasRunning.current && !running) {
      const payload = toSavePayload(threadId, agent?.messages || [])
      if (payload.messages.length > 0) {
        getToken().then((token) =>
          fetch('/api/chats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify(payload),
          }).catch(() => {})   // archive write is best-effort; never block the UI
        )
      }
    }
    wasRunning.current = running
  }, [agent?.isRunning, agent?.messages, threadId, getToken])

  return null
}
```

- [ ] **Step 4: Run the test**

Run: `cd dashboard && npx vitest run test/chat-persistence.test.ts`
Expected: PASS (2 passed).

- [ ] **Step 5: Mount it in App.jsx with a stable threadId**

```jsx
// dashboard/src/App.jsx — near the top of the component body:
import { ChatPersistence } from './chat-persistence.jsx'
// inside App(), with the other useState hooks:
const [threadId] = useState(() => crypto.randomUUID())
// inside the returned JSX, alongside <CopilotSidebar/>:
<ChatPersistence threadId={threadId} />
```

- [ ] **Step 6: Build + typecheck**

Run: `cd dashboard && npx tsc --noEmit && npm run build`
Expected: tsc clean, build succeeds.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/chat-persistence.jsx dashboard/src/App.jsx dashboard/test/chat-persistence.test.ts
git commit -m "feat(chat): persist each completed turn from the client"
```

---

### Task 9: History tab (browse + search + transcript)

**Files:**
- Create: `dashboard/src/history.jsx`
- Modify: `dashboard/src/tabs.jsx` (register a "History" tab)
- Test: `dashboard/test/history.test.ts`

**Interfaces:**
- Consumes: `@clerk/react` `useAuth().getToken`, the `/api/chats` proxy.
- Produces: pure helper `chatsUrl({q, id}) -> string` and a `<HistoryView/>` component (search box → thread list → click → transcript with expandable SQL). Registered in `TABS` as `History: () => <HistoryView/>`.

- [ ] **Step 1: Write the failing test for the URL helper**

```typescript
// dashboard/test/history.test.ts
import { describe, it, expect } from "vitest";
import { chatsUrl } from "../src/history.jsx";

describe("chatsUrl", () => {
  it("no args → /api/chats", () => expect(chatsUrl({})).toBe("/api/chats"));
  it("search → /api/chats?q=", () => expect(chatsUrl({ q: "donors" })).toBe("/api/chats?q=donors"));
  it("detail → /api/chats?id=", () => expect(chatsUrl({ id: "abc" })).toBe("/api/chats?id=abc"));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd dashboard && npx vitest run test/history.test.ts`
Expected: FAIL — cannot resolve `../src/history.jsx`.

- [ ] **Step 3: Implement**

```jsx
// dashboard/src/history.jsx
import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '@clerk/react'

export function chatsUrl({ q, id } = {}) {
  if (id) return `/api/chats?id=${encodeURIComponent(id)}`
  if (q) return `/api/chats?q=${encodeURIComponent(q)}`
  return '/api/chats'
}

export function HistoryView() {
  const { getToken } = useAuth()
  const [q, setQ] = useState('')
  const [threads, setThreads] = useState([])
  const [active, setActive] = useState(null)   // {thread, messages}
  const [err, setErr] = useState(null)

  const authedFetch = useCallback(async (url) => {
    const token = await getToken()
    const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    return r.json()
  }, [getToken])

  useEffect(() => {
    authedFetch(chatsUrl({ q: q.trim() || undefined })).then(setThreads).catch((e) => setErr(e.message))
  }, [q, authedFetch])

  const open = (id) => authedFetch(chatsUrl({ id })).then(setActive).catch((e) => setErr(e.message))

  if (active) {
    return (
      <div className="history-detail">
        <button className="tab" onClick={() => setActive(null)}>← Back to history</button>
        <h3>{active.thread.title}</h3>
        <div className="history-meta">{active.thread.user_email} · {active.thread.updated_at}</div>
        {active.messages.map((m) => (
          <div key={m.seq} className={`chat-msg chat-${m.role}`}>
            <div className="chat-role">{m.role}</div>
            <div className="chat-content">{m.content}</div>
            {m.tool_calls ? (
              <details className="chat-sql"><summary>SQL it ran</summary>
                <pre>{JSON.stringify(m.tool_calls, null, 2)}</pre></details>
            ) : null}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="history">
      <input className="history-search" placeholder="Search past chats…"
             value={q} onChange={(e) => setQ(e.target.value)} />
      {err ? <div className="loading">Couldn't load history: {err}</div> : null}
      <ul className="history-list">
        {threads.map((t) => (
          <li key={t.thread_id} className="history-item" onClick={() => open(t.thread_id)}>
            <div className="history-title">{t.title}</div>
            <div className="history-sub">{t.user_email} · {t.updated_at} · {t.message_count ?? ''} msgs</div>
            {t.snippet ? <div className="history-snippet">…{t.snippet}…</div> : null}
          </li>
        ))}
        {threads.length === 0 && !err ? <li className="loading">No chats yet.</li> : null}
      </ul>
    </div>
  )
}
```

- [ ] **Step 4: Register the tab**

```jsx
// dashboard/src/tabs.jsx — import then add to the TABS object:
import { HistoryView } from './history.jsx'
// add as the last entry of TABS:
//   History: () => <HistoryView />,
```

- [ ] **Step 5: Run tests + build**

Run: `cd dashboard && npx vitest run test/history.test.ts && npx tsc --noEmit && npm run build`
Expected: PASS, tsc clean, build OK.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/history.jsx dashboard/src/tabs.jsx dashboard/test/history.test.ts
git commit -m "feat(chat): read-only History tab with search + transcript"
```

---

### Task 10: Deploy + end-to-end verification

**Files:** none (deploy only).

**Interfaces:** consumes everything above.

- [ ] **Step 1: Full local test gate**

Run: `source .venv/bin/activate && python -m pytest -q && cd dashboard && npm test && npx tsc --noEmit && npm run build`
Expected: all green.

- [ ] **Step 2: Deploy backend, then frontend**

```bash
flyctl deploy --app rm-data-loader
cd dashboard && vercel --prod --yes
```
(`INTERNAL_API_TOKEN` already set on both; `schema/019` already applied in Task 1.)

- [ ] **Step 3: Verify the gate (chat endpoint)**

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://rm-data-loader.fly.dev/api/chats   # expect 401
```

- [ ] **Step 4: Verify end-to-end in the browser**

Sign in at the dashboard, ask the assistant one question, then open the **History** tab: the chat appears; searching a word from it returns it; opening it shows the transcript and the "SQL it ran" expander.

- [ ] **Step 5: Open the PR**

```bash
git push -u origin tarikjmoody/chat-history-archive
gh pr create --base main --title "Shared searchable chat history archive" --body "Implements docs/plans/2026-06-27-chat-history-archive-design.md. Read-only archive; client capture; Clerk-stamped identity; chat schema not granted to rm_readonly."
```

---

## Self-Review

- **Spec coverage:** schema (T1) ✓; capture client-side on complete (T8) ✓; identity server-stamped (T7) ✓; owner-role writes / not granted to rm_readonly (T1 note + T2) ✓; gated endpoints (T6) ✓; list/search/detail (T3/T4/T5) ✓; History UI read-only with SQL expander (T9) ✓; tsvector + pg_trgm (T1/T4) ✓; tests (every task) ✓; deploy (T10) ✓. No gaps.
- **Placeholder scan:** Task 3 intentionally introduces a `search_chats` stub, explicitly replaced in Task 4 — flagged inline, not a hidden TODO. No other placeholders.
- **Type consistency:** `save_thread`/`list_threads`/`search_chats`/`get_thread` names match across tasks; `buildFlyTarget`/`toSavePayload`/`chatsUrl` signatures match their tests; `tool_calls` (snake, DB/payload) vs `toolCalls` (camel, CopilotKit message) mapping is explicit in `toSavePayload`.
