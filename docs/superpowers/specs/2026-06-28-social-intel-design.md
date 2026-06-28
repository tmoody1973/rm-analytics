# Social intelligence: competitive social learning for the assistant — design

> Status: validated design, approved 2026-06-28. Ready for an implementation plan
> (run `/superpowers:writing-plans` on this file next). Not yet built.

## Goal

Let the in-dashboard AI assistant **learn from other social accounts and competitors**
(and Radio Milwaukee's own public accounts) to help the social team improve. Powered by
**socialfetch.dev** (a unified public-social scraping API) ingested into the warehouse, with
Haiku content-tagging so the assistant can reason about *what kind of content works*, not just
raw metrics.

## Approved decisions (from brainstorming)

- **Mode:** tracked **watchlist / benchmark first**; ad-hoc "research any account live" is a
  separate fast-follow phase.
- **Platforms (v1):** Instagram, TikTok, YouTube, Facebook, Threads, LinkedIn (socialfetch
  returns one normalized shape across all, so this is field-mapping, not 6× the work).
- **Us + them, one pipeline:** RM's own public handles AND competitors flow through the identical
  path, distinguished by `is_owned`. This also sidesteps our unfinished Meta/Coupler ingestion —
  one integration gives apples-to-apples comparison.
- **Approach A (assistant access):** ingest → warehouse → the assistant's **existing `query_sql`
  tool** reaches it (same as funraise + email). No new endpoints in v1. The intelligence lives in
  the data, the Haiku tags, and the system prompt — not in bespoke tools.
- **Engagement RATE is the headline metric**, never raw follower count.

## Architecture & data flow

```
dim_accounts (watchlist; you add a row)      socialfetch.dev (live public data, REST)
        │                                            ▲  weekly, per account
        ▼                                            │
  social_intel.dim_accounts ──► jobs/refresh_social_intel.py (Fly scheduled machine)
                                          │ fetch profile + recent posts
                                          ▼
              social_intel.fact_account_snapshots   (followers/posts over time)
              social_intel.fact_posts               (each post: type, caption, metrics, eng. rate)
                                          │ Haiku-tag NEW posts (reuse newsletter enrichment)
                                          ▼
              social_intel.fact_post_enrichment      (theme, format, hook, topic)
                                          │ rm_readonly SELECT + /api/schema notes + system prompt
                                          ▼
              Assistant's existing query_sql tool ──► "how do we compare / what's working"
```

Watchlist is the only human-touched config: add a `dim_accounts` row, the weekly job tracks it.
Cost is bounded: weekly × N accounts socialfetch calls + a Haiku tag per *new* post.

## Schema — new `social_intel` schema (`schema/020_social_intel.sql`)

Conventions: snapshots are non-additive (query at grain); every loader upserts `ON CONFLICT`;
enrichment table mirrors `email_esp.fact_campaign_enrichment`.

**`social_intel.dim_accounts`** — the watchlist / config
- `account_id` TEXT PK (our slug, e.g. `ig:hyfinmke`)
- `platform` TEXT (instagram|tiktok|youtube|facebook|threads|linkedin)
- `handle` TEXT, `display_name` TEXT
- `category` TEXT (peer_station|local_media|music_brand|aspirational|other)
- `is_owned` BOOLEAN, `station_code` TEXT NULL (RM88/HYFIN/RM414/RLR when owned)
- `active` BOOLEAN DEFAULT true, `added_at` TIMESTAMPTZ DEFAULT now()

**`social_intel.fact_account_snapshots`** — profile metrics over time, PK `(account_id, snapshot_date)`
- `follower_count`, `following_count`, `post_count` INT; `verified` BOOLEAN; `loaded_at`

**`social_intel.fact_posts`** — one row per post, PK `(account_id, post_id)`
- `platform`, `published_at` TIMESTAMPTZ, `post_type` TEXT (reel|carousel|image|video|short|text)
- `caption` TEXT, `transcript` TEXT NULL
- `likes`, `comments_count`, `shares`, `views`, `saves` INT (aggregate counts only — NO commenter rows)
- `engagement_rate` NUMERIC (engagement ÷ followers-at-fetch — comparable across account sizes)
- `permalink` TEXT, `fetched_at` TIMESTAMPTZ

**`social_intel.fact_post_enrichment`** — Haiku tags, PK `(post_id)`
- `content_theme` TEXT (local_artist_feature|event_promo|behind_the_scenes|community|music_discovery|…)
- `format` TEXT, `primary_topic` TEXT, `hook_style` TEXT, `has_cta` BOOLEAN
- `featured_artists` JSONB, `model` TEXT (honest null tags when no body/failed, like the newsletter table)

PII stance: **no commenter data stored** — aggregate comment counts only.

## socialfetch API reference (canonical — do not invent endpoints/fields)

Source: https://www.socialfetch.dev/docs/sdk + /openapi.json + /llms.json (read these at build time).
- **REST base:** `https://api.socialfetch.dev`. **Auth header:** `x-api-key: sfk_...` on every `/v1/**`
  route (unless an op is explicitly anonymous). Our env var is `SOCIALFETCH_API_KEY`.
- **Our ingest loader is PYTHON → call REST directly** (httpx/requests + the `x-api-key` header). The
  official `@socialfetch/sdk` is **TypeScript** and is only relevant if/when we build the Phase-2 live
  tool in the Vercel/TS layer — NOT for the Python job.
- **Response envelope gotchas (bake into the loader):** a route can return **HTTP 200 and still be
  `lookupStatus: "not_found" | "private"`** (not an error — skip the account, don't crash). `402` =
  insufficient credits (stop the run, Slack-alert). Normal data lives under `data.*`.
- **Exact per-platform routes + field names:** read `/openapi.json` (full contract) and `/llms.json`
  (structured operation inventory with params/credits) while writing the normalizer. Do NOT guess field
  names. There's also a hosted MCP at `/mcp` with `docs_search`/`docs_read` for implementation help.

## Ingest pipeline (Python on Fly, existing patterns)

**`loaders/load_socialfetch.py`** (pure, idempotent, importable + CLI):
- `fetch_account(account) -> dict` — socialfetch REST call(s) for profile + recent posts, sending
  `x-api-key: $SOCIALFETCH_API_KEY` to `https://api.socialfetch.dev/v1/...`. Handle the 200+`lookupStatus`
  envelope (skip not_found/private) and `402` (abort + alert).
- `load(account) -> stats` — normalize JSON → upsert 1 snapshot row + N `fact_posts`
  `ON CONFLICT (account_id, post_id) DO UPDATE`. Returns `{accounts, posts_new, posts_updated}`.
- Per-platform-in, one-shape-out; small `post_type` translator. Field mapping comes from /openapi.json.

**`jobs/refresh_social_intel.py`** (weekly Fly scheduled machine, like `mailchimp-content-nightly`):
1. `SELECT * FROM social_intel.dim_accounts WHERE active`.
2. Per account: `load_socialfetch.load()`, wrapped in try/except (one bad handle never aborts the run).
3. Posts with no enrichment row → Haiku-tag (reuse `jobs/refresh_mailchimp_content.py` enrichment
   helper; swap taxonomy to social themes/formats). Only NEW posts → flat weekly cost.
4. Slack summary: accounts fetched, new posts, tags, failures.

**Backfill:** none — socialfetch returns recent posts only; the time-series accumulates from day one.
Seed `dim_accounts` with RM's own handles + an initial competitor set (user provides).

**Secret:** `SOCIALFETCH_API_KEY` — Fly secret (prod) + `~/.radio-milwaukee/.env` (local). User has
added it to a local `.env`; confirm path the loader reads.

## Assistant access (Approach A — no new endpoints)

1. **Grant** (`schema/021_social_intel_grant.sql`): `GRANT USAGE ON SCHEMA social_intel` +
   `SELECT ON ALL TABLES` to `rm_readonly`. No PII → plain table-level grants (simpler than funraise).
2. **Catalog** (`service/catalog_api.py`): add `social_intel` to `_ALLOWED_SCHEMAS`; add it to
   `ask_sql_api.py` `ALLOWED_SCHEMAS`. Write per-table NOTES: "engagement_rate is the comparable
   metric, NOT follower_count; `is_owned=true` is Radio Milwaukee, false is a competitor; join
   `fact_posts`↔`fact_post_enrichment` on post_id to ask what themes/formats drive engagement." Add
   `content_theme`, `format`, `category`, `platform`, `hook_style` to `_DIMENSION_COLUMNS` so values
   enumerate.
3. **System prompt** (`dashboard/api/system-prompt.md`): a "Competitive social intelligence" section —
   reason in engagement rate not vanity followers; separate us/them via `is_owned`; use content tags
   for the *learning* ("their top posts skew local-artist features + BTS; ours skew event promos —
   consider shifting mix"); frame as actionable recommendations; stay honest that it's recent public
   data, not full history.

## Cadence / cost / compliance

- **Cadence:** weekly (per-account override later). Profile snapshot + posts both weekly.
- **Cost:** ~20 accounts × ~2 calls weekly ≈ 160 socialfetch calls/month ≈ <$1 (Starter $2/1k); free
  100 credits cover dev. Haiku tags pennies, new-posts-only. Bounding to a watchlist is the cost control.
- **Compliance:** public data only; no commenter PII; standard competitive analysis; kept internal
  (staff-gated). socialfetch puts platform-ToS responsibility on us — note, not a blocker.

## Scope

- **v1 (this spec):** schema + loader + weekly job + Haiku enrichment + grant/catalog/system-prompt,
  seeded watchlist. Assistant answers via `query_sql`.
- **Fast-follow (separate specs):** (B) curated tools `get_social_benchmark` /
  `get_social_content_insights`; (C) ad-hoc live "research any account" tool — **socialfetch has an
  MCP server** (https://www.socialfetch.dev/docs/integrations/mcp) that fits this phase, or use REST;
  Social dashboard-tab cards surfacing the competitive data.
- **Fast-follow — Reddit story radar (separate spec, sibling capability):** a DIFFERENT use case from
  benchmarking — search r/milwaukee (+ r/wisconsin) via socialfetch's Reddit endpoints for **story/content
  ideas** (trending topics, questions, local conversations). Consumer is the **content/programming** team,
  not social/marketing. Inherently **live + exploratory** ("what's blowing up this week we could cover?"),
  so it belongs with the ad-hoc live phase (C), NOT the benchmark watchlist — a subreddit isn't an
  "account" with an engagement rate; the value is the topic as a lead. Likely a live search tool + maybe a
  lightweight weekly "top local posts" digest. Keep its own schema/shape; do not force it into
  `social_intel.fact_posts`.

## Testing

- pytest: loader normalization (mock socialfetch JSON → assert row shapes + idempotency on re-run),
  enrichment taxonomy, grant + catalog (a `social_intel`-present assertion mirroring the funraise/email
  catalog tests). Follows existing loader/catalog test patterns.

## Open items to confirm at build time

- Exact initial competitor watchlist (handles per platform) — user provides.
- Confirm which local `.env` path holds `SOCIALFETCH_API_KEY` so the loader reads it; set the Fly secret.
- socialfetch's exact JSON field names per platform (read their REST docs while writing the normalizer).
