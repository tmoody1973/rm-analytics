# Radio Milwaukee Analytics Pipeline

> A unified analytics warehouse for Radio Milwaukee's four streaming brands — plus
> social, web, donations, finance, and email data — built on Neon Postgres.

## Overview

This project consolidates Radio Milwaukee's data into a single Neon Postgres
warehouse, organized **schema-per-source** so each vendor's data is mirrored
exactly as delivered and joined only in a derived `marts` layer for dashboards.

The **streaming side (Triton WMS) is the first build and is fully backfilled.**
Other sources (donations, social, web, email, finance) are designed into the
schema and will be added without restructuring.

**Brands:** 88Nine Radio Milwaukee (`RM88`), HYFIN (`HYFIN`), 414 Music (`RM414`),
Rhythm Lab Radio (`RLR`).

**Dashboard audiences:** Program Director, Development Director, Underwriting
Director, and Finance/Executive.

> For full architecture, conventions, and source-by-source detail, see
> [`CLAUDE.md`](./CLAUDE.md) — the canonical project reference.

## Tech Stack

| Layer | Technology |
|---|---|
| Warehouse | Neon Postgres (project `radio-milwaukee-analytics`, db `neondb`) |
| Streaming source | Triton WMS (XLSX exports) |
| Loaders | Python 3.12, pandas, psycopg3 (`psycopg[binary]`) |
| Ingestion service (planned) | FastAPI on Fly.io (`rm-data-loader`) |
| Daily updates (planned) | Webhooks + Coupler.io |
| Presentation (planned) | Hex notebooks reading from `marts.*` |
| Alerting (planned) | Slack webhook |

## Quick Start

### Prerequisites

- Python 3.12+
- `psql` (PostgreSQL client)
- Access to the Neon database (a `DATABASE_URL` connection string)

### Installation

```bash
git clone https://github.com/tmoody1973/rm-analytics.git
cd rm-analytics

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Credentials

Create `~/.radio-milwaukee/.env` (chmod 600, never committed):

```bash
DATABASE_URL=postgresql://<user>:<password>@<host>.neon.tech/neondb?sslmode=require
```

### Apply the schema

Migrations are plain SQL, idempotent, and applied in order:

```bash
psql "$DATABASE_URL" -f schema/001_initial.sql
psql "$DATABASE_URL" -f schema/002_wms_facts.sql
psql "$DATABASE_URL" -f schema/003_wms_facts_revision.sql
psql "$DATABASE_URL" -f schema/004_wms_facts_revision_geo_device.sql
psql "$DATABASE_URL" -f schema/005_wms_cume_revision.sql
```

### Run a backfill

Loaders are importable functions and CLI scripts. Place the Triton XLSX exports
in `exports/` (gitignored), then run:

```bash
python loaders/load_q1_hourly.py          exports/Q1_hourly_2024-01-01_2026-05-16.xlsx
python loaders/load_q2a_daily_cume.py     exports/Q2a_daily_2024-01-01_to_2026-05-20.xlsx
python loaders/load_q2b_weekly_cume.py    exports/Q2b_weekly_2024-01-01_to_2026-05-20.xlsx
python loaders/load_q2c_monthly_cume.py   exports/Q2c_monthly_2024-01-01_to_2026-05-20.xlsx
python loaders/load_q3_monthly_geo.py     exports/Q3_monthly_geo_2024-01-01_to_2026-05-20.xlsx
python loaders/load_q4_monthly_device.py  exports/Q4_monthly_device_2024-01-01_to_2026-05-20.xlsx
```

Every loader is idempotent (`ON CONFLICT DO UPDATE`) and prints rows upserted and
elapsed time. Run the smoke test first to confirm the foundation end-to-end:

```bash
python tests/test_smoke_q1.py     # loads 50 rows, verifies the count, cleans up
```

## Project Structure

```
rm-analytics/
├── CLAUDE.md              # Canonical project reference (read first)
├── master-setup-guide.md  # Step-by-step setup walkthrough (Phases 1–12)
├── requirements.txt
├── schema/                # SQL migrations (001–005 applied)
│   ├── 001_initial.sql               # all schemas + dim tables (stations, dates, dayparts, brand_channels)
│   ├── 002_wms_facts.sql             # Triton fact tables
│   ├── 003_wms_facts_revision.sql    # monthly geo/device + weekly cume
│   ├── 004_wms_facts_revision_geo_device.sql  # geo City/DMA + device family/device
│   └── 005_wms_cume_revision.sql     # daily/monthly cume → 5-metric shape
├── loaders/               # Importable + CLI-runnable backfill loaders
│   ├── _common.py         # STATION_MAP, parse_tsl, coercion, get_db_connection, bulk_upsert
│   └── load_q*.py         # one loader per Triton query (Q1–Q4)
├── tests/                 # test_smoke_q1.py — end-to-end smoke test
├── exports/               # Triton XLSX exports (gitignored)
├── service/               # FastAPI webhook service (planned)
├── jobs/                  # Scheduled tasks (planned)
└── queries/               # Dashboard / validation SQL
```

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `DATABASE_URL` | Neon Postgres connection string (in `~/.radio-milwaukee/.env`) | Yes |

## Backfill Status

| Source | Status |
|---|---|
| Streaming (Triton WMS, Q1–Q4) | ✅ Backfilled — 117,940 rows across 6 fact tables (validation against Triton UI pending) |
| Funraise, Meta, GA, Email, Finance | ⏳ Planned |

## Conventions

- Source schemas are read-only after load; transformations live in `marts`.
- Every fact table upserts via `ON CONFLICT (composite_key) DO UPDATE` (idempotent).
- Bulk inserts use psycopg3 `executemany` in batches of 5000 — no row-by-row inserts.
- `import psycopg` (psycopg3), never `psycopg2`.

See [`CLAUDE.md`](./CLAUDE.md) for the full coding conventions and "what NOT to do".

## License

Proprietary — internal to Radio Milwaukee. Not licensed for redistribution.
