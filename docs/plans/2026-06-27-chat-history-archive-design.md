# Chat history archive — design

> Status: validated design, not yet implemented. 2026-06-27.

## Goal

Persist the in-dashboard AI assistant's conversations so **any signed-in (Clerk-allowlisted)
user can browse and full-text search past chats**. Read-only archive — no resuming old threads.

## Decisions (locked in brainstorming)

- **Scope:** searchable archive (read-only), not resumable shared threads. (YAGNI on resume.)
- **Store depth:** transcript + the `tool_calls` (the SQL the assistant ran) — NOT the raw tool
  result rows. The assistant's replies already contain the aggregates it states; we add the SQL
  for "show your work" without duplicating donor rows into a shared searchable store.
- **Capture:** client-side. The self-hosted CopilotKit v2 `BuiltInAgent` has no server-side
  persistence (that's a CopilotKit Enterprise feature); the client already exposes the full
  `messages` array incl. tool calls. Save on turn-complete.
- **Identity:** stamped server-side from the verified Clerk token — never trusted from the client.
- **Isolation:** the `chat` schema is served only by owner-role Fly endpoints; it is **NOT** granted
  to `rm_readonly`, so the assistant itself can never query the chat log (can't be prompted into
  surfacing someone else's session).

## Governance note

Transcripts contain de-identified donor and financial analysis. "Shared + searchable to everyone
with a login" means any allowlisted staff/board member can read all of it. Accepted because every
login is vetted staff/board. Raw donor rows are not stored (store-depth choice above).

## Data model — new `chat` schema in Neon

```sql
CREATE SCHEMA IF NOT EXISTS chat;

CREATE TABLE chat.threads (
  thread_id     UUID PRIMARY KEY,
  clerk_user_id TEXT NOT NULL,
  user_email    TEXT,                 -- denormalized for the History list
  title         TEXT,                 -- first user message, truncated
  message_count INT  NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat.messages (
  message_id  UUID PRIMARY KEY,
  thread_id   UUID NOT NULL REFERENCES chat.threads(thread_id) ON DELETE CASCADE,
  seq         INT  NOT NULL,          -- order within the thread
  role        TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content     TEXT NOT NULL DEFAULT '',
  tool_calls  JSONB,                  -- [{tool, args}] — captures the SQL
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  search_tsv  TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
  UNIQUE (thread_id, seq)
);

CREATE INDEX ix_chat_messages_tsv   ON chat.messages USING GIN (search_tsv);
CREATE INDEX ix_chat_messages_trgm  ON chat.messages USING GIN (content gin_trgm_ops);
CREATE INDEX ix_chat_threads_updated ON chat.threads (updated_at DESC);
```

`pg_trgm` extension required (likely already present; `CREATE EXTENSION IF NOT EXISTS pg_trgm`).

## Capture flow

1. `<ChatPersistence/>` hook in the dashboard watches the assistant `messages` array.
2. On turn-complete (`agent.isRunning` → false), upsert the whole thread:
   `POST /api/chats {thread_id, messages:[{seq, role, content, tool_calls}]}`.
   Upsert-by-`thread_id` is idempotent — a 3-turn chat ends as 1 thread row + N message rows.
3. It posts to the dashboard's Vercel function `/api/chats`, which `verifyToken`s the Clerk
   session, extracts `clerk_user_id` + email, and forwards to Fly `POST /api/chats` with
   `X-Internal-Token`.
4. Fly writes to Neon on the **owner** `DATABASE_URL` (writes need INSERT; `rm_readonly` can't).

## Endpoints (Fly, gated by `INTERNAL_API_TOKEN`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chats` | Upsert thread + messages (owner role). Identity from the trusted forward. |
| GET  | `/api/chats?limit=&cursor=` | Recent threads for the History list. |
| GET  | `/api/chats/search?q=` | Full-text search; `websearch_to_tsquery`, `ts_rank` (recency tiebreak), `ts_headline` snippet; `pg_trgm` fallback. Returns matching threads + snippet + hit message. |
| GET  | `/api/chats/{thread_id}` | Full transcript for the detail view. |

The dashboard reaches all of these through its Clerk-verified Vercel function, mirroring the
existing tool-endpoint pattern.

## History UI (new dashboard tab, Clerk-gated)

- Search box over a most-recent-first thread list (title, who asked, when, message count).
- Click a thread → read-only transcript; assistant messages expand to show the "SQL it ran"
  from `tool_calls`.
- No resume. "New chat" returns to the assistant tab.

## Testing

- **pytest:** save idempotency (re-upsert → no dupes), search ranking + snippet, internal-token
  gate (reuse `tests/conftest.py` bypass pattern), identity-required on write.
- **vitest:** the `<ChatPersistence/>` hook (saves once on complete, not per delta) + History
  components (list, search, transcript render, tool_calls expansion).

## Out of scope (YAGNI)

- Resuming/continuing an archived thread.
- Per-user private history / ACLs (everything is shared to logged-in users).
- Editing or deleting chats from the UI.
- Storing raw tool result rows.

## New schema migration

`schema/019_chat.sql` — the DDL above. Applied via Neon MCP, owner role.
