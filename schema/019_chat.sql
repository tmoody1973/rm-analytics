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
