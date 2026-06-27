# Newsletter Content Analysis — Design

> Make Mailchimp newsletter **content** a first-class, queryable thing the
> CopilotKit assistant can reason over, alongside the performance metrics it
> already sees. Status: design approved 2026-06-26. Ships as its own phase,
> purely additive to the MOO-177 assistant (no rework).

## Goal

Let the agent do **both** at scale:
1. **Correlate content with performance** — "what topics/themes drive opens and
   clicks?", across the whole newsletter archive.
2. **Retrieve / summarize specific newsletters** — "summarize the last HYFIN
   newsletter", "what stories did we feature in June?"

## What already exists (no work)

`email_esp.fact_campaign_sends` already stores, per campaign: `subject_line`,
`campaign_title`, `preview_text`, and the full performance set (`emails_sent`,
`unique_opens`, `open_rate`, `unique_clicks`, `click_rate`, unsubs, bounces).
The `email_esp` schema is **already in the agent's `rm_readonly` allowlist**, so
`query_sql` can reach new tables there the moment they exist.

**The gap:** the newsletter **body content** (article text, featured stories,
links) is not stored anywhere — Coupler pulls the *report*, not the *content*.
That requires Mailchimp's `GET /campaigns/{id}/content` endpoint.

## Section 1 — Data model

Two new tables in `email_esp`. Raw content (vendor data) and LLM-derived tags
are kept **separate** so derived data is never confused with what the vendor
sent. Placement in `email_esp` (not `marts`) mirrors the precedent of
`funraise.dim_supporters` carrying derived rollup columns inside a source schema.

### `email_esp.fact_campaign_content` (raw Mailchimp content)
| column | type | notes |
|---|---|---|
| `campaign_id` | text **PK** | aligns with `fact_campaign_sends.campaign_id` |
| `plain_text` | text | body, stripped — what the LLM reads |
| `html` | text | fidelity/links; nullable to save space |
| `links` | jsonb | extracted `[{url, label}]` |
| `word_count` | int | structural signal |
| `fetched_at` | timestamptz | audit (not in PK) |

### `email_esp.fact_campaign_enrichment` (LLM-derived tags)
| column | type | notes |
|---|---|---|
| `campaign_id` | text **PK** | joins to content + sends |
| `primary_theme` | text | single dominant theme |
| `topics` | jsonb | multi-select array |
| `content_type` | text | closed vocab (below) |
| `featured_artists` | jsonb | extracted names (open) |
| `enriched_at` | timestamptz | audit |
| `model` | text | tagging model/version, for reproducibility |

## Section 2 — Ingestion & enrichment

All follow existing loader conventions: pure `load() -> dict`, psycopg3,
`ON CONFLICT DO UPDATE`, CLI `__main__` block. Laptop-for-backfill,
Fly-for-daily.

1. **`loaders/load_mailchimp_content.py`** — fetch + enrich one or many.
   - Auth: key is `key-usXX`; the `usXX` server prefix → base URL
     `https://usXX.api.mailchimp.com/3.0/`, basic auth `anystring:key`.
     Fly secret `MAILCHIMP_API_KEY` (+ laptop `.env` for backfill).
   - Per campaign: `GET /campaigns/{id}/content` → `plain_text` + `html` →
     strip, extract links, count words → upsert `fact_campaign_content`.
   - **Enrichment pass:** one Anthropic call per newsletter, **Haiku 4.5**
     (cheap, sufficient for tagging), forced structured JSON (tool-use schema)
     → upsert `fact_campaign_enrichment`, stamping `model`. Idempotent;
     re-enrich only when `model` changes or the row is missing.
2. **`loaders/load_mailchimp_content_backfill.py`** (or `--all`) — one-time:
   every `campaign_id` in `fact_campaign_sends` lacking a content row → loop →
   fetch → enrich. Run locally.
3. **`jobs/refresh_mailchimp_content.py`** — daily sweep, Fly scheduled machine
   (shape of `funraise-rollup-nightly`): find sent campaigns with no content
   row → fetch + enrich + upsert. Slack ✅/❌.

### Trigger decision: daily sweep, webhook deferred
Mailchimp's webhook fires on `campaign` (sent) and hands back **id + subject,
not the body** — the handler would still call the content API. And content's
real-time-ness buys nothing analytically because the performance data it
correlates against accrues over the following **days** via the daily Coupler
pull. The daily sweep piggybacks on that cadence with no per-list webhook
config or signing. The sweep is also the mandatory reconciliation safety net
**even if** a webhook is added later (the Funraise lesson). So: **daily sweep
now, clean seam for a webhook later.**

### Starter tag taxonomy (closed vocabs; tune from real data)
- **`content_type`** (exactly one): `newsletter`, `event_promo`,
  `fundraising_appeal`, `announcement`, `contest`.
- **`topics`** (multi): `local_music`, `artist_spotlight`, `music_discovery`,
  `events`, `membership_giving`, `station_news`, `community`, `partnerships`,
  `podcasts`, `contests`.
- **`featured_artists`** — open free-form array (can't pre-enumerate).
- **`primary_theme`** — the model's single most-central topic.
- Sentiment intentionally omitted (YAGNI).

Closed vocabs keep `GROUP BY` correlation clean; the open artist list stays
flexible.

## Section 3 — How the agent reaches it

- **Correlation → existing `query_sql`, no new code.** All enrichment columns
  are small/structured:
  ```sql
  SELECT e.primary_theme, AVG(s.open_rate), AVG(s.click_rate), COUNT(*)
  FROM email_esp.fact_campaign_enrichment e
  JOIN email_esp.fact_campaign_sends s USING (campaign_id)
  GROUP BY e.primary_theme ORDER BY 2 DESC;
  ```
- **Retrieval/summary → new tool `get_newsletter_content(campaign_id)`** in
  `dashboard/api/_tools.ts`, returning one newsletter's cleaned `plain_text`
  (capped length) + tags. Dedicated tool (not raw `query_sql`) so body size is
  controlled and the affordance is explicit. Backs onto a small new route
  `GET /api/newsletter-content/{id}` on the `rm_readonly` connection.
- **Discovery wiring:** add both tables to `/api/schema` (the agent's
  `get_schema`); add a short "newsletter content" section to
  `system-prompt.md`. No PII rules — newsletter content is published marketing,
  not donor data, so no Funraise-style blocks apply.

## Section 4 — Testing & rollout

**Testing** (pytest loaders, vitest agent tool):
- Loader units — mock Mailchimp `/content` + Anthropic; assert link extraction,
  word count, enrichment→column mapping, idempotency.
- Enrichment contract — known body → valid `content_type` from closed vocab,
  well-formed `topics`; reject out-of-vocab tags at the validation boundary.
- Agent tool — vitest for `get_newsletter_content`: mocked fetch,
  resolves-not-throws on 404/400 (parity with the existing 4 tools).
- Validation — eyeball first batch: do tags match what the newsletters say?

**Rollout, in order:**
1. `schema/017_email_content.sql` → apply via Neon MCP.
2. Build + unit-test loader locally.
3. Backfill historical campaigns from laptop; spot-check tags.
4. Deploy daily sweep (Fly machine `mailchimp-content-nightly`) +
   `MAILCHIMP_API_KEY` secret + Slack wiring.
5. Add `get_newsletter_content` tool + `/api/newsletter-content/{id}` route +
   `/api/schema` + `system-prompt.md` updates; deploy.
6. Real prod probes: "which themes drive opens?", "summarize the last HYFIN
   newsletter".

## Open items / future
- Webhook trigger (near-real-time) — deferred; only if ever needed.
- Full RAG (pgvector embeddings + semantic search tool) — deferred; layer on
  later for fuzzy "find newsletters about X" without rework.
- Taxonomy tuning once real tag distributions are visible.
