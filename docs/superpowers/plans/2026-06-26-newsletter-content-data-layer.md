# Newsletter Content Data Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull Mailchimp newsletter body content into the warehouse, LLM-tag each newsletter with structured topics, so the CopilotKit assistant can correlate content with performance and retrieve/summarize individual newsletters.

**Architecture:** Two new `email_esp` tables — `fact_campaign_content` (raw vendor body, links, word count) and `fact_campaign_enrichment` (Haiku-derived `content_type`/`topics`/`featured_artists`). A loader fetches content from Mailchimp's `GET /campaigns/{id}/content`, parses it, upserts, then runs one Haiku pass per newsletter for tags. A daily Fly sweep job backfills any sent campaign missing a content row. The agent reaches correlation via existing `query_sql` and retrieval via a new tool (deferred — see Phase B).

**Tech Stack:** Python 3.12, psycopg3 (`psycopg`), `requests` (Mailchimp), `anthropic` SDK (enrichment, Haiku 4.5), pytest. Design doc: `docs/plans/2026-06-26-newsletter-content-analysis-design.md`.

## Global Constraints

- psycopg3 — import is `import psycopg`, NOT psycopg2. Reuse `loaders/_common.py` `get_db_connection()` and `bulk_upsert(...)`. No row-by-row inserts.
- Every fact table upserts: `ON CONFLICT (campaign_id) DO UPDATE`. Idempotent by default.
- Loaders are pure functions `def load(...) -> dict` (stats) with an `if __name__ == "__main__"` CLI block.
- Source schemas mirror the vendor; derived tags live in the separate `fact_campaign_enrichment` table (per the `funraise.dim_supporters` rollup precedent).
- Closed vocabs are the single source of truth in `loaders/_enrich.py`: `CONTENT_TYPES` and `TOPICS`. Out-of-vocab values are dropped at the validation boundary, never stored.
- Enrichment model id: `claude-haiku-4-5-20251001` (override via env `ENRICH_MODEL`). The `anthropic` client reads `ANTHROPIC_API_KEY` from env. **Before writing the Anthropic `messages.create` call, consult the `claude-api` skill to confirm the current SDK/tool-use shape.**
- Mailchimp: API key form `xxxxxxxx-usNN`; the `usNN` suffix is the data-center → base URL `https://usNN.api.mailchimp.com/3.0`. HTTP Basic auth, username any non-empty string, password = full API key. Key from env `MAILCHIMP_API_KEY` (laptop `.env` for backfill, Fly secret for the sweep).
- Tests must not make real network calls (mock `requests` + the Anthropic client). DB-touching smoke tests are gated on `DATABASE_URL` being set and must clean up after themselves.

---

### Task 1: Schema migration — two `email_esp` tables

**Files:**
- Create: `schema/017_email_content.sql`
- Test: applied + verified via Neon MCP (`run_sql`)

**Interfaces:**
- Produces: tables `email_esp.fact_campaign_content (campaign_id PK, plain_text, html, links jsonb, word_count int, fetched_at timestamptz)` and `email_esp.fact_campaign_enrichment (campaign_id PK, primary_theme, topics jsonb, content_type, featured_artists jsonb, enriched_at timestamptz, model text)`.

- [ ] **Step 1: Write the migration**

```sql
-- schema/017_email_content.sql
-- Newsletter body content + LLM-derived topic tags for the assistant.
-- Raw Mailchimp content (fact_campaign_content) is vendor data; the derived
-- tags (fact_campaign_enrichment) are kept in a SEPARATE table so derived data
-- is never confused with what Mailchimp sent. Both key on campaign_id, aligned
-- with email_esp.fact_campaign_sends.

CREATE TABLE IF NOT EXISTS email_esp.fact_campaign_content (
    campaign_id  text PRIMARY KEY,
    plain_text   text,
    html         text,
    links        jsonb NOT NULL DEFAULT '[]'::jsonb,
    word_count   integer NOT NULL DEFAULT 0,
    fetched_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_esp.fact_campaign_enrichment (
    campaign_id      text PRIMARY KEY,
    primary_theme    text,
    topics           jsonb NOT NULL DEFAULT '[]'::jsonb,
    content_type     text,
    featured_artists jsonb NOT NULL DEFAULT '[]'::jsonb,
    enriched_at      timestamptz NOT NULL DEFAULT now(),
    model            text
);

-- rm_readonly already holds SELECT on the email_esp schema (schema/016), but
-- default privileges only cover pre-existing tables. Grant explicitly so the
-- assistant can read the new tables immediately.
GRANT SELECT ON email_esp.fact_campaign_content    TO rm_readonly;
GRANT SELECT ON email_esp.fact_campaign_enrichment TO rm_readonly;
```

- [ ] **Step 2: Apply via Neon MCP**

Use `mcp__Neon__run_sql` with `projectId=morning-frost-30675590`, running the file's contents.

- [ ] **Step 3: Verify tables + grants exist**

Run via `mcp__Neon__run_sql`:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema='email_esp'
  AND table_name IN ('fact_campaign_content','fact_campaign_enrichment')
ORDER BY table_name;
SELECT table_name FROM information_schema.role_table_grants
WHERE grantee='rm_readonly' AND table_schema='email_esp'
  AND table_name IN ('fact_campaign_content','fact_campaign_enrichment');
```
Expected: both tables listed; both grants present.

- [ ] **Step 4: Commit**

```bash
git add schema/017_email_content.sql
git commit -m "feat(email): schema for newsletter content + enrichment tables"
```

---

### Task 2: Mailchimp client + content parsing (`loaders/_mailchimp.py`)

**Files:**
- Create: `loaders/_mailchimp.py`
- Test: `tests/test_mailchimp_content.py`

**Interfaces:**
- Produces:
  - `mailchimp_base_url(api_key: str) -> str`
  - `parse_content(html: str | None, plain_text: str | None) -> dict` → `{"plain_text": str, "html": str | None, "links": list[dict], "word_count": int}` where each link is `{"url": str, "label": str}`.
  - `fetch_campaign_content(api_key: str, campaign_id: str, *, session=None) -> dict` → raw Mailchimp JSON (`plain_text`, `html`).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_mailchimp_content.py
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "loaders"))

import pytest
import _mailchimp as mc


def test_base_url_uses_datacenter_suffix():
    assert mc.mailchimp_base_url("abc123def456-us21") == "https://us21.api.mailchimp.com/3.0"


def test_base_url_rejects_keys_without_suffix():
    with pytest.raises(ValueError):
        mc.mailchimp_base_url("no-datacenter-here-")


def test_parse_content_extracts_links_and_word_count():
    html = '<p>Hear <a href="https://radiomilwaukee.org/show">the show</a> now</p>'
    plain = "Hear the show now"
    out = mc.parse_content(html, plain)
    assert out["word_count"] == 4
    assert out["links"] == [{"url": "https://radiomilwaukee.org/show", "label": "the show"}]
    assert out["plain_text"] == "Hear the show now"
    assert out["html"] == html


def test_parse_content_handles_missing_body():
    out = mc.parse_content(None, None)
    assert out == {"plain_text": "", "html": None, "links": [], "word_count": 0}
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_mailchimp_content.py -q`
Expected: FAIL (`No module named '_mailchimp'`).

- [ ] **Step 3: Implement `loaders/_mailchimp.py`**

```python
"""Mailchimp Marketing API client + content parsing for newsletter analysis.

Only the campaign CONTENT endpoint is used here; performance metrics already
arrive via Coupler into email_esp.fact_campaign_sends. Auth is HTTP Basic with
any username and the API key as the password; the key's `-usNN` suffix selects
the data-center host.
"""
from __future__ import annotations

import re
import requests

_TIMEOUT_SEC = 30
_LINK_RE = re.compile(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def mailchimp_base_url(api_key: str) -> str:
    """Derive the data-center base URL from the API key's `-usNN` suffix."""
    if "-" not in api_key or not api_key.rsplit("-", 1)[-1]:
        raise ValueError("Mailchimp API key missing the `-usNN` data-center suffix")
    dc = api_key.rsplit("-", 1)[-1]
    return f"https://{dc}.api.mailchimp.com/3.0"


def parse_content(html: str | None, plain_text: str | None) -> dict:
    """Normalize a Mailchimp content payload into our storage shape."""
    text = (plain_text or "").strip()
    links: list[dict] = []
    if html:
        for url, raw_label in _LINK_RE.findall(html):
            label = _TAG_RE.sub("", raw_label).strip()
            links.append({"url": url, "label": label})
    return {
        "plain_text": text,
        "html": html if html else None,
        "links": links,
        "word_count": len(text.split()),
    }


def fetch_campaign_content(api_key: str, campaign_id: str, *, session=None) -> dict:
    """GET /campaigns/{id}/content -> raw JSON ({'plain_text','html', ...})."""
    http = session or requests
    url = f"{mailchimp_base_url(api_key)}/campaigns/{campaign_id}/content"
    resp = http.get(url, auth=("rm-analytics", api_key), timeout=_TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_mailchimp_content.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add loaders/_mailchimp.py tests/test_mailchimp_content.py
git commit -m "feat(email): Mailchimp content client + parser"
```

---

### Task 3: Enrichment taxonomy + validation (`loaders/_enrich.py`)

**Files:**
- Create: `loaders/_enrich.py`
- Modify: `tests/test_mailchimp_content.py` (append enrichment tests)
- Modify: `requirements.txt` (add `anthropic`)

**Interfaces:**
- Produces:
  - Constants `CONTENT_TYPES: set[str]`, `TOPICS: set[str]`.
  - `validate_enrichment(raw: dict) -> dict` → `{"primary_theme": str|None, "topics": list[str], "content_type": str|None, "featured_artists": list[str]}` with out-of-vocab values dropped.
  - `ENRICH_TOOL` (Anthropic tool definition dict) and `enrich_text(client, plain_text: str, *, model: str) -> dict` returning a validated enrichment dict.

- [ ] **Step 1: Add `anthropic` to requirements.txt**

Append line: `anthropic==0.69.0`

- [ ] **Step 2: Write failing validation tests**

```python
# append to tests/test_mailchimp_content.py
import _enrich as en


def test_validate_drops_out_of_vocab_topics_and_dedups():
    raw = {"primary_theme": "events", "topics": ["events", "events", "made_up", "podcasts"],
           "content_type": "event_promo", "featured_artists": ["GGOOLD", "  Klassik  "]}
    out = en.validate_enrichment(raw)
    assert out["topics"] == ["events", "podcasts"]
    assert out["primary_theme"] == "events"
    assert out["content_type"] == "event_promo"
    assert out["featured_artists"] == ["GGOOLD", "Klassik"]


def test_validate_nulls_invalid_scalars():
    out = en.validate_enrichment({"primary_theme": "nope", "topics": "notalist",
                                  "content_type": "bogus", "featured_artists": None})
    assert out == {"primary_theme": None, "topics": [], "content_type": None, "featured_artists": []}


def test_enrich_text_uses_injected_client_and_validates():
    class FakeBlock:
        type = "tool_use"
        input = {"primary_theme": "local_music", "topics": ["local_music", "junk"],
                 "content_type": "newsletter", "featured_artists": ["Foo"]}
    class FakeResp:
        content = [FakeBlock()]
    class FakeClient:
        def __init__(self): self.messages = self
        def create(self, **kw):
            assert kw["tool_choice"]["name"] == "record_enrichment"
            return FakeResp()
    out = en.enrich_text(FakeClient(), "some newsletter body", model="claude-haiku-4-5-20251001")
    assert out["content_type"] == "newsletter"
    assert out["topics"] == ["local_music"]   # 'junk' dropped
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `python -m pytest tests/test_mailchimp_content.py -q`
Expected: FAIL (`No module named '_enrich'`).

- [ ] **Step 4: Implement `loaders/_enrich.py`**

> When writing `enrich_text`, consult the `claude-api` skill to confirm the current `messages.create` + tool-use shape before finalizing.

```python
"""LLM enrichment of newsletter body text into structured, closed-vocab tags.

One Haiku pass per newsletter. The taxonomy here is the single source of truth;
validate_enrichment drops anything the model invents so GROUP BY stays clean.
"""
from __future__ import annotations

CONTENT_TYPES = {"newsletter", "event_promo", "fundraising_appeal", "announcement", "contest"}
TOPICS = {"local_music", "artist_spotlight", "music_discovery", "events",
          "membership_giving", "station_news", "community", "partnerships",
          "podcasts", "contests"}

_MAX_ARTISTS = 20

ENRICH_TOOL = {
    "name": "record_enrichment",
    "description": "Record structured tags for one newsletter.",
    "input_schema": {
        "type": "object",
        "properties": {
            "primary_theme": {"type": "string", "enum": sorted(TOPICS),
                              "description": "The single most-central topic."},
            "topics": {"type": "array", "items": {"type": "string", "enum": sorted(TOPICS)},
                       "description": "All topics the newsletter covers."},
            "content_type": {"type": "string", "enum": sorted(CONTENT_TYPES)},
            "featured_artists": {"type": "array", "items": {"type": "string"},
                                 "description": "Musicians/artists named in the body."},
        },
        "required": ["primary_theme", "topics", "content_type", "featured_artists"],
    },
}

_PROMPT = (
    "You tag Radio Milwaukee email newsletters. Read the body and call "
    "record_enrichment with the closed-vocabulary tags. Use only the allowed "
    "enum values; if unsure of a topic, omit it. featured_artists are proper "
    "names of musicians/bands actually mentioned.\n\nNewsletter body:\n"
)


def validate_enrichment(raw: dict) -> dict:
    raw = raw or {}
    pt = raw.get("primary_theme")
    ct = raw.get("content_type")
    topics_in = raw.get("topics") if isinstance(raw.get("topics"), list) else []
    artists_in = raw.get("featured_artists") if isinstance(raw.get("featured_artists"), list) else []

    topics = sorted({t for t in topics_in if t in TOPICS})
    artists, seen = [], set()
    for a in artists_in:
        if not isinstance(a, str):
            continue
        name = a.strip()
        if name and name not in seen:
            seen.add(name)
            artists.append(name)
    return {
        "primary_theme": pt if pt in TOPICS else None,
        "topics": topics,
        "content_type": ct if ct in CONTENT_TYPES else None,
        "featured_artists": artists[:_MAX_ARTISTS],
    }


def enrich_text(client, plain_text: str, *, model: str) -> dict:
    """Run one enrichment pass; returns a validated enrichment dict."""
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[ENRICH_TOOL],
        tool_choice={"type": "tool", "name": "record_enrichment"},
        messages=[{"role": "user", "content": _PROMPT + (plain_text or "")[:20000]}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return validate_enrichment(block.input)
    return validate_enrichment({})
```

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest tests/test_mailchimp_content.py -q`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add loaders/_enrich.py tests/test_mailchimp_content.py requirements.txt
git commit -m "feat(email): newsletter enrichment taxonomy + Haiku tagging"
```

---

### Task 4: Loader orchestration + upsert (`loaders/load_mailchimp_content.py`)

**Files:**
- Create: `loaders/load_mailchimp_content.py`
- Modify: `tests/test_mailchimp_content.py` (append loader tests)

**Interfaces:**
- Consumes: `_common.get_db_connection`, `_common.bulk_upsert`, `_mailchimp.fetch_campaign_content`, `_mailchimp.parse_content`, `_enrich.enrich_text`.
- Produces:
  - `campaigns_missing_content(conn) -> list[str]` — sent campaign_ids with no content row.
  - `load(campaign_ids: list[str] | None = None, *, api_key: str | None = None, enrich: bool = True, client=None, model: str | None = None, conn=None) -> dict` → stats `{"table","rows_read","rows_upserted","enriched","elapsed_sec"}`.
  - CLI: `python loaders/load_mailchimp_content.py [--all] [--no-enrich] [CAMPAIGN_ID ...]`.

- [ ] **Step 1: Write failing loader test (no network/DB)**

```python
# append to tests/test_mailchimp_content.py
import load_mailchimp_content as loader


def test_load_builds_rows_and_enriches(monkeypatch):
    calls = {"content": [], "enrich": 0, "upserts": []}

    def fake_fetch(api_key, cid, session=None):
        calls["content"].append(cid)
        return {"html": f'<a href="https://x/{cid}">go</a>', "plain_text": f"body {cid}"}

    class FakeEnrichClient: pass
    def fake_enrich(client, text, *, model):
        calls["enrich"] += 1
        return {"primary_theme": "events", "topics": ["events"],
                "content_type": "newsletter", "featured_artists": []}

    def fake_bulk_upsert(conn, table, columns, rows, conflict_columns, update_columns, batch_size=5000):
        calls["upserts"].append((table, len(rows)))
        return len(rows)

    monkeypatch.setattr(loader, "fetch_campaign_content", fake_fetch)
    monkeypatch.setattr(loader, "enrich_text", fake_enrich)
    monkeypatch.setattr(loader, "bulk_upsert", fake_bulk_upsert)

    stats = loader.load(["c1", "c2"], api_key="k-us1", client=FakeEnrichClient(),
                        model="m", conn=object())
    assert stats["rows_read"] == 2
    assert stats["rows_upserted"] == 2
    assert stats["enriched"] == 2
    assert ("email_esp.fact_campaign_content", 2) in calls["upserts"]
    assert ("email_esp.fact_campaign_enrichment", 2) in calls["upserts"]
```

- [ ] **Step 2: Run test, verify fail**

Run: `python -m pytest tests/test_mailchimp_content.py::test_load_builds_rows_and_enriches -q`
Expected: FAIL (`No module named 'load_mailchimp_content'`).

- [ ] **Step 3: Implement `loaders/load_mailchimp_content.py`**

```python
"""Fetch Mailchimp newsletter content, upsert it, and LLM-tag each newsletter.

Two entry modes (same function): explicit campaign ids, or --all to sweep every
sent campaign in email_esp.fact_campaign_sends that has no content row yet.
Idempotent: ON CONFLICT (campaign_id) DO UPDATE on both tables.

CLI:
  python loaders/load_mailchimp_content.py --all          # backfill / sweep
  python loaders/load_mailchimp_content.py CID1 CID2       # specific campaigns
  python loaders/load_mailchimp_content.py --all --no-enrich
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _common import get_db_connection, bulk_upsert  # noqa: E402
from _mailchimp import fetch_campaign_content, parse_content  # noqa: E402
from _enrich import enrich_text  # noqa: E402

CONTENT_TABLE = "email_esp.fact_campaign_content"
ENRICH_TABLE = "email_esp.fact_campaign_enrichment"
DEFAULT_MODEL = os.environ.get("ENRICH_MODEL", "claude-haiku-4-5-20251001")


def campaigns_missing_content(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s.campaign_id FROM email_esp.fact_campaign_sends s "
            "LEFT JOIN email_esp.fact_campaign_content c USING (campaign_id) "
            "WHERE c.campaign_id IS NULL ORDER BY s.send_time"
        )
        return [r[0] for r in cur.fetchall()]


def _anthropic_client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def load(campaign_ids=None, *, api_key=None, enrich=True, client=None,
         model=None, conn=None) -> dict:
    start = time.time()
    api_key = api_key or os.environ["MAILCHIMP_API_KEY"]
    model = model or DEFAULT_MODEL
    owns_conn = conn is None
    conn = conn or get_db_connection()
    try:
        ids = list(campaign_ids) if campaign_ids is not None else campaigns_missing_content(conn)

        content_rows, enrich_rows = [], []
        if enrich and ids and client is None:
            client = _anthropic_client()

        for cid in ids:
            raw = fetch_campaign_content(api_key, cid)
            parsed = parse_content(raw.get("html"), raw.get("plain_text"))
            content_rows.append((cid, parsed["plain_text"], parsed["html"],
                                 json.dumps(parsed["links"]), parsed["word_count"]))
            if enrich:
                tags = enrich_text(client, parsed["plain_text"], model=model)
                enrich_rows.append((cid, tags["primary_theme"], json.dumps(tags["topics"]),
                                    tags["content_type"], json.dumps(tags["featured_artists"]),
                                    model))

        upserted = bulk_upsert(
            conn, CONTENT_TABLE,
            ["campaign_id", "plain_text", "html", "links", "word_count"],
            content_rows, ["campaign_id"],
            ["plain_text", "html", "links", "word_count"],
        )
        if enrich_rows:
            bulk_upsert(
                conn, ENRICH_TABLE,
                ["campaign_id", "primary_theme", "topics", "content_type",
                 "featured_artists", "model"],
                enrich_rows, ["campaign_id"],
                ["primary_theme", "topics", "content_type", "featured_artists", "model"],
            )
        return {"table": CONTENT_TABLE, "rows_read": len(ids),
                "rows_upserted": upserted, "enriched": len(enrich_rows),
                "elapsed_sec": round(time.time() - start, 1)}
    finally:
        if owns_conn:
            conn.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    enrich = "--no-enrich" not in args
    sweep = "--all" in args
    ids = [a for a in args if not a.startswith("--")]
    print(load(ids if (ids and not sweep) else None, enrich=enrich))
```

Note on the `links`/`topics` jsonb columns: psycopg3 sends `json.dumps(...)` strings, which Postgres casts to `jsonb` on insert into a jsonb column.

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/test_mailchimp_content.py -q`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add loaders/load_mailchimp_content.py tests/test_mailchimp_content.py
git commit -m "feat(email): Mailchimp content loader (fetch + parse + enrich + upsert)"
```

---

### Task 5: Daily sweep job + Dockerfile + Slack (`jobs/refresh_mailchimp_content.py`)

**Files:**
- Create: `jobs/refresh_mailchimp_content.py`
- Modify: `tests/test_mailchimp_content.py` (append job test)
- (Dockerfile already `COPY jobs/` — no change needed; `anthropic` arrives via requirements.txt.)

**Interfaces:**
- Consumes: `load_mailchimp_content.load`, `service.slack.post_success`/`post_failure`.
- Produces: `run() -> dict` (the load stats + `"tag": "[ESP-CONTENT]"`), posts Slack success/failure.

- [ ] **Step 1: Write failing job test**

```python
# append to tests/test_mailchimp_content.py
import importlib


def test_job_run_posts_success(monkeypatch):
    job = importlib.import_module("jobs.refresh_mailchimp_content") \
        if False else __import__("refresh_mailchimp_content")
    posted = {}
    monkeypatch.setattr(job, "load", lambda *a, **k: {"table": "t", "rows_read": 3,
                        "rows_upserted": 3, "enriched": 3, "elapsed_sec": 1.0})
    monkeypatch.setattr(job, "post_success", lambda tag, stats: posted.setdefault("ok", (tag, stats)))
    monkeypatch.setattr(job, "post_failure", lambda tag, err: posted.setdefault("fail", (tag, err)))
    out = job.run()
    assert out["tag"] == "[ESP-CONTENT]"
    assert posted["ok"][0] == "[ESP-CONTENT]"
    assert "fail" not in posted
```

(The job dir must be importable; the job inserts `loaders/` and the repo root on `sys.path`, mirroring `refresh_funraise_rollup.py`. Add `jobs/` to `sys.path` in the test via `sys.path.insert(0, os.path.join(ROOT, "jobs"))` at the top of the test file.)

- [ ] **Step 2: Run test, verify fail**

Run: `python -m pytest tests/test_mailchimp_content.py -q`
Expected: FAIL (`No module named 'refresh_mailchimp_content'`).

- [ ] **Step 3: Implement `jobs/refresh_mailchimp_content.py`**

```python
"""Daily sweep: fetch + enrich any sent campaign missing a content row.

Piggybacks the Coupler cadence — newsletter content's real-time-ness buys
nothing because the open/click metrics it correlates against accrue over days.
This sweep is also the reconciliation safety net if a webhook is added later.

Fly scheduled machine `mailchimp-content-nightly`. CLI:
  python jobs/refresh_mailchimp_content.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "loaders"))
sys.path.insert(0, ROOT)
from load_mailchimp_content import load  # noqa: E402
from service.slack import post_success, post_failure  # noqa: E402

TAG = "[ESP-CONTENT]"


def run() -> dict:
    try:
        stats = load(None)            # sweep mode: campaigns missing content
        stats["tag"] = TAG
        post_success(TAG, stats)
        return stats
    except Exception as exc:          # noqa: BLE001 — report then re-raise
        post_failure(TAG, str(exc))
        raise


if __name__ == "__main__":
    print(run())
```

- [ ] **Step 4: Run test, verify pass**

Run: `python -m pytest tests/test_mailchimp_content.py -q`
Expected: PASS.

- [ ] **Step 5: Full suite regression**

Run: `python -m pytest -q`
Expected: prior baseline (93 passed, 1 skipped) + the new tests, all green.

- [ ] **Step 6: Commit**

```bash
git add jobs/refresh_mailchimp_content.py tests/test_mailchimp_content.py
git commit -m "feat(email): nightly newsletter-content sweep job + Slack"
```

---

### Task 6: Backfill run + validation (manual, local)

**Files:** none (operational).

- [ ] **Step 1: Set secrets locally** — ensure `MAILCHIMP_API_KEY` and `ANTHROPIC_API_KEY` are in `~/.radio-milwaukee/.env` (or exported). `DATABASE_URL` already there.

- [ ] **Step 2: Dry sweep size** — run, observe the count it would process:
```bash
source .venv/bin/activate
python -c "import sys; sys.path.insert(0,'loaders'); from _common import get_db_connection; \
from load_mailchimp_content import campaigns_missing_content as m; \
c=get_db_connection(); print('missing content:', len(m(c)))"
```

- [ ] **Step 3: Backfill** (laptop, idempotent):
```bash
python loaders/load_mailchimp_content.py --all
```

- [ ] **Step 4: Validate tags against reality** via `mcp__Neon__run_sql`:
```sql
SELECT e.content_type, e.topics, c.word_count, s.subject_line, s.open_rate
FROM email_esp.fact_campaign_enrichment e
JOIN email_esp.fact_campaign_content c USING (campaign_id)
JOIN email_esp.fact_campaign_sends s USING (campaign_id)
ORDER BY s.send_time DESC LIMIT 15;
```
Eyeball: do `content_type`/`topics` match what the `subject_line` implies? Spot-check one `plain_text`. Record findings in the PR.

- [ ] **Step 5: Deploy the sweep** (separate from this plan's code commits):
```bash
flyctl secrets set MAILCHIMP_API_KEY=... ANTHROPIC_API_KEY=... --app rm-data-loader
flyctl deploy --app rm-data-loader
flyctl machine run . --schedule daily --app rm-data-loader \
  --entrypoint "python jobs/refresh_mailchimp_content.py"   # confirm flag syntax vs funraise-rollup-nightly
```
(Mirror the exact machine/schedule pattern already used for `funraise-rollup-nightly`.)

---

## Phase B — Agent wiring (GATED on PR #4 merging to main)

These files live only on the unmerged MOO-177 branch (`dashboard/api/_tools.ts`,
`dashboard/api/system-prompt.md`, the backend `/api/schema` catalog). **Do not
start Phase B until #4 is merged** and this branch is rebased on the new main.
Sketch (full TDD tasks to be written once the files exist):

1. Backend route `GET /api/newsletter-content/{id}` (FastAPI in `service/`) — runs on the `rm_readonly` connection, returns `{campaign_id, plain_text (capped ~8k chars), word_count, content_type, topics, featured_artists}`; 404 when absent. Add pytest like `tests/test_ask_sql.py`.
2. Agent tool `get_newsletter_content(campaign_id)` in `dashboard/api/_tools.ts` calling that route; vitest mirroring the existing 4 tools (resolves-not-throws on 404/400).
3. `/api/schema` (the agent's `get_schema`) must include `fact_campaign_content` + `fact_campaign_enrichment` so the agent can discover columns for correlation `query_sql`.
4. `system-prompt.md` — add a short "Newsletter content" capability note (correlate topics/themes with performance via SQL; fetch full text via the tool). No PII rules — newsletter content is published marketing.
5. Prod probes: "which themes drive the highest open rates?", "summarize the most recent HYFIN newsletter".

---

## Self-Review

- **Spec coverage:** Design §1 (two tables) → Task 1. §2 loader/enrichment/taxonomy → Tasks 2–4. §2 daily sweep + secrets/Docker → Task 5. §2 backfill → Task 6. §3 agent access → Phase B (gated). §4 testing folded into each task's TDD steps; §4 rollout → Tasks 1,5,6 + Phase B. Webhook explicitly deferred (design "Open items"). ✓
- **Placeholder scan:** none — every code step is complete; the one `flyctl machine run` flag is marked "confirm against the existing funraise-rollup-nightly machine," not a code placeholder. ✓
- **Type consistency:** `parse_content` returns keys consumed verbatim in `load`; `validate_enrichment`/`enrich_text` keys match the `enrich_rows` tuple and `ENRICH_TABLE` columns; `campaigns_missing_content` returns `list[str]` consumed by `load`. Table/column names identical across schema + loader + job. ✓
