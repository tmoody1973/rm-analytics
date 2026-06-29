# Radio Milwaukee Analytics Pipeline

> A unified analytics warehouse for Radio Milwaukee's four brands — streaming,
> broadcast, donations, web, social, email, and finance — with a live executive
> dashboard and an AI data analyst on top.

## Overview

This project consolidates Radio Milwaukee's data into a single Neon Postgres
warehouse, organized **schema-per-source** so each vendor's data is mirrored
exactly as delivered and joined only in a derived layer for dashboards.

On top of the warehouse sits a **FastAPI ingestion + metrics service** (on Fly.io)
and a **React executive dashboard** (on Vercel) with a built-in **AI data analyst**
(CopilotKit + Claude) that answers questions in plain language and cites every
live figure.

**Brands:** 88Nine Radio Milwaukee (`RM88`), HYFIN (`HYFIN`), 414 Music (`RM414`),
Rhythm Lab Radio (`RLR`).

**Dashboard audiences:** Program Director, Development Director, Underwriting
Director, Digital/Marketing, and Finance/Executive (plus the Board).

> For full architecture, conventions, and source-by-source detail, see
> [`CLAUDE.md`](./CLAUDE.md) — the canonical project reference.

## What's live

- **Warehouse** — Neon Postgres, schema-per-source. Streaming (Triton), donations
  (Funraise), broadcast ratings (Nielsen), email + newsletter content (Mailchimp),
  and competitive social (socialfetch) are loaded; web (GA4) staging is loaded;
  Meta and full finance ingestion are in progress.
- **Ingestion service** — `rm-data-loader` on Fly.io. Webhooks for Triton (via
  AgentMail) and Funraise, a Nielsen upload page, scheduled jobs (newsletter +
  social enrichment, Funraise rollup, IG followers), and the dashboard/metric/SQL
  API the assistant uses.
- **Dashboard** — [data.radiomilwaukee.org](https://data.radiomilwaukee.org),
  Clerk sign-in gated to staff + board. Role tabs, brand/date filters, and a
  searchable history of every assistant conversation.
- **AI data analyst** — in-dashboard assistant (CopilotKit runtime + Claude) with
  curated metrics, a guarded read-only SQL fallback, schema discovery, and
  newsletter-content retrieval. Donor data is de-identified; the prompt is
  server-authoritative.
- **Competitive social intelligence** — RM's own + competitor public accounts
  ingested weekly via socialfetch, Haiku-tagged, and queryable by the assistant
  (engagement rate, not follower count).

## Tech Stack

| Layer | Technology |
|---|---|
| Warehouse | Neon Postgres (db `neondb`) |
| Loaders / jobs | Python 3.12, pandas, psycopg3 (`psycopg[binary]`), `requests` |
| Service | FastAPI + Uvicorn on Fly.io (`rm-data-loader`, region `ord`) |
| Dashboard | Vite + React, Recharts, deployed on Vercel |
| Assistant | CopilotKit v2 runtime + Anthropic Claude (Haiku for enrichment) |
| Auth | Clerk (production) + app-layer email allowlist |
| Sources | Triton WMS, Funraise, Nielsen, Mailchimp, GA4/Meta (Coupler.io), socialfetch.dev |
| Inbox / alerting | AgentMail (Triton email → webhook), Slack webhook |

## Quick Start

### Backend (loaders, jobs, service)

**Prerequisites:** Python 3.12+, `psql`, and a Neon `DATABASE_URL`.

```bash
git clone https://github.com/tmoody1973/rm-analytics.git
cd rm-analytics
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt          # add -r requirements-dev.txt for tests
```

Credentials live in `~/.radio-milwaukee/.env` (chmod 600, never committed):

```bash
DATABASE_URL=postgresql://<user>:<password>@<host>.neon.tech/neondb?sslmode=require
# Optional, per pipeline:
DATABASE_URL_RO=...          # read-only role, used by the guarded SQL endpoint
MAILCHIMP_API_KEY=...        # newsletter content sweep (includes -usNN suffix)
ANTHROPIC_API_KEY=...        # LLM enrichment (newsletter + social tags)
SOCIALFETCH_API_KEY=sfk_...  # competitive social ingestion
```

Apply the schema (plain SQL, idempotent, in order — `001` through `021`):

```bash
for f in schema/0*.sql; do psql "$DATABASE_URL" -f "$f"; done
psql "$DATABASE_URL" -f schema/seed_brand_channels.sql
```

Run a loader (idempotent; place Triton XLSX exports in `exports/`, gitignored):

```bash
python loaders/load_q1_hourly.py exports/Q1_hourly_2024-01-01_2026-05-16.xlsx
```

Run the tests:

```bash
python -m pytest -q
```

### Dashboard (frontend)

**Prerequisites:** Node.js 20+, a Clerk publishable key, and the service running
(or the deployed API).

```bash
cd dashboard
npm install
# .env: VITE_CLERK_PUBLISHABLE_KEY=pk_...
npm run dev        # local dev server
npm test           # vitest
npm run build      # production build
```

## Project Structure

```
rm-analytics/
├── CLAUDE.md              # Canonical project reference (read first)
├── schema/               # SQL migrations 001–021 (+ seeds) — applied to Neon
├── loaders/              # Importable + CLI backfill/ingest loaders
│   ├── _common.py        # station map, parsing, get_db_connection, bulk_upsert
│   ├── load_q*.py        # Triton WMS (Q1–Q4)
│   ├── load_funraise_*.py, load_nielsen.py, load_mailchimp_content.py
│   └── load_socialfetch.py + _socialfetch.py, _social_enrich.py
├── jobs/                 # Scheduled Fly machines (newsletter, social-intel, rollups)
├── service/              # FastAPI app — webhooks + dashboard/metric/SQL/catalog APIs
├── metrics/              # Registry-backed curated metric definitions
├── dashboard/            # Vite + React executive dashboard + AI assistant
│   ├── src/              # App.jsx, tabs.jsx, start-here.jsx, brands.js, …
│   └── api/              # CopilotKit runtime + system prompt + auth proxies
├── tests/                # pytest suites (loaders, APIs, dashboard queries)
├── queries/              # Validation + dashboard SQL
├── exports/              # Triton XLSX exports (gitignored)
├── Dockerfile, fly.toml  # Fly deployment for rm-data-loader
└── docs/                 # Specs, plans, setup walkthroughs
```

## The assistant

The dashboard's AI analyst retrieves data only through five server-side tools and
cites every figure:

- **`get_metric` / `list_metrics`** — curated, registry-backed metrics (same source
  the dashboard renders).
- **`get_schema`** — allowlisted tables/columns (+ low-cardinality value enumeration).
- **`query_sql`** — guarded read-only `SELECT`/`WITH` fallback, run as a restricted
  Neon role (single statement, allowlisted schemas, row + time caps).
- **`get_newsletter_content`** — full body + topic tags for one Mailchimp newsletter.

Tool endpoints are gated behind `INTERNAL_API_TOKEN`; `/api/dashboard`, `/health`,
and `/webhook/*` stay open. Donor data is **de-identified** — no names, raw emails,
or phone numbers.

## Data sources

| Source | Status |
|---|---|
| Streaming (Triton WMS, Q1–Q4) | ✅ Loaded — ~118K rows across 6 fact tables |
| Donations (Funraise) | ✅ Loaded — 134K transactions, 14K supporters, ~$47.5K MRR (de-identified) |
| Broadcast ratings (Nielsen) | ✅ Loaded — RM88 + HYFIN Vital Signs (upload page) |
| Email + newsletter (Mailchimp) | ✅ Loaded — 576 campaigns + body content + Haiku tags |
| Competitive social (socialfetch) | ✅ Live — 26-account watchlist, weekly job, engagement-rate benchmark |
| Web (GA4) | ◐ Staging loaded (`ga.stg_*`); marts in progress |
| Social (Meta organic/ads) | ⏳ In progress (Coupler.io) |
| Finance — revenue/budget | ◐ Partial (recent months); full history in progress |

## Conventions

- Source schemas are read-only after load; cross-source joins live in the dashboard
  query layer and (in progress) the `marts` layer.
- Every fact table upserts via `ON CONFLICT (composite_key) DO UPDATE` (idempotent).
- Bulk inserts use psycopg3 `executemany` in batches of 5000 — no row-by-row inserts.
- `import psycopg` (psycopg3), never `psycopg2`. Loaders are pure functions with a
  CLI block.
- Deploy: `flyctl deploy --app rm-data-loader` (backend); `cd dashboard && vercel --prod`
  (frontend). Small PRs off `main`.

See [`CLAUDE.md`](./CLAUDE.md) for the full conventions and "what NOT to do".

## License

Proprietary — internal to Radio Milwaukee. Not licensed for redistribution.
