# Radio Milwaukee Analytics — Master Setup Guide (v2)

**For:** Tarik / Radio Milwaukee
**Stack:** Triton WMS · Funraise · Meta · GA4 · Email · Finance · Neon Postgres · AgentMail · Fly.io · Coupler.io · Hex
**Companion files:** `CLAUDE.md` (operations reference), `phase-8-revised-agentmail-flyio.md` (webhook service deep dive)

This guide takes you from zero to a fully working analytics warehouse with
Hex notebooks as the presentation layer. Built for a beginner — every command
copyable, every concept explained the first time it appears.

## What you're building

A single Neon Postgres database that ingests:
- **Streaming data** from Triton WMS (via scheduled emails to AgentMail)
- **Donations & supporters** from Funraise (via webhook + API)
- **Social** organic + paid from Meta (via Coupler.io)
- **Web** from Google Analytics 4 (via Coupler.io)
- **Email** campaigns from your ESP (via Coupler.io)
- **Finance** revenue, budget, expenses (via XLSX upload, later QuickBooks)
- **Underwriting** contracts & delivery (operational pipeline)
- **Grants** pipeline (operational)
- **Events** ticketing & attendance

All data lands in source-specific schemas. A `marts` schema joins them into
the dashboard-ready views. **Hex notebooks** consume `marts.*` to produce
the actual reports for the Program Director, Development Director,
Underwriting Director, and finance/executive team.

## Time budget

| Phase | Goal | Time | Section |
|---|---|---|---|
| 1 | Install all tools | 30 min | below |
| 2 | Create Neon project | 15 min | below |
| 3 | Project structure + CLAUDE.md | 20 min | below |
| 4 | Full schema migration | 45 min | below |
| 5 | Triton bulk exports | 1–2 hr (mostly waiting) | below |
| 6 | Backfill loaders (streaming) | 1–2 hr | below |
| 7 | Validate streaming data | 30 min | below |
| 8 | Daily pipeline (Fly.io + AgentMail) | 2–3 hr | see `phase-8-revised-agentmail-flyio.md` |
| 9 | Funraise integration | 1–2 hr | below |
| 10 | Coupler imports (Meta, GA, ESP) | 2 hr | below |
| 11 | Finance ingestion | 1 hr | below |
| 12 | Hex dashboards | 2–3 hr | below |

**Total ~14 hours active work**, spread across multiple sessions.

---

# Phase 1 — Install tools

## 1.1 — Neon CLI (Postgres warehouse)

```bash
brew install neonctl
neon auth
```

## 1.2 — Hex CLI (analytics + dashboards)

You said you already installed this — verify and authenticate:

```bash
hex --version
hex auth login
```

The auth flow opens a browser, lets you pick your Hex workspace. Credentials
get stored in your system keyring (Mac Keychain).

## 1.3 — Hex Claude skill (lets Claude Code use Hex CLI)

```bash
hex install skill --claude
```

This adds a Hex skill to your Claude Code installation so Claude understands
how to create projects, push SQL cells, and run analyses via the CLI. Same
idea as the Neon MCP wiring — Claude now has hands in both Neon and Hex.

## 1.4 — Fly.io CLI (webhook service hosting)

```bash
brew install flyctl
flyctl auth login
```

## 1.5 — Claude Code

Make sure Claude Code itself is current. From any terminal:

```bash
claude --version
```

## 1.6 — Wire Neon into Claude Code

```bash
cd ~/code   # or wherever you want this project to live
npx neonctl@latest init
```

When prompted, select **Claude CLI** (spacebar toggle, Enter confirm).
This installs the Neon MCP server so Claude can run migrations directly.

Restart Claude Code after this completes.

## 1.7 — Postgres client (psql)

For ad-hoc database checks:

```bash
brew install libpq
brew link --force libpq
```

## 1.8 — Verify everything

```bash
neon --version
hex --version
flyctl version
claude --version
psql --version
```

All five should print versions. If any error out, fix that one before
moving on.

---

# Phase 2 — Create the Neon project

## 2.1 — Create the project

```bash
neon projects create --name radio-milwaukee-analytics
```

The output includes a connection string. **Copy it to your password manager
right now**, before doing anything else. Looks like:

```
postgresql://neondb_owner:npg_xxxxxxxxxxxxx@ep-xxxxx.us-east-1.aws.neon.tech/neondb?sslmode=require
```

## 2.2 — Save the connection string

```bash
mkdir -p ~/.radio-milwaukee
nano ~/.radio-milwaukee/.env
```

Paste:
```
DATABASE_URL=postgresql://...your-connection-string...
```

Save (Ctrl+O, Enter, Ctrl+X). Then:

```bash
chmod 600 ~/.radio-milwaukee/.env
```

## 2.3 — Verify connection

```bash
source ~/.radio-milwaukee/.env
psql "$DATABASE_URL" -c "SELECT current_database(), version();"
```

You should see `neondb | PostgreSQL 17.x...`. **Important:** we use the
default `neondb` database for everything — schemas inside it are how we
separate sources. Do NOT create a separate `wms` database.

---

# Phase 3 — Project structure

## 3.1 — Create the directory

```bash
mkdir -p ~/code/rm-analytics
cd ~/code/rm-analytics
git init
```

## 3.2 — Create folders

```bash
mkdir -p {schema,loaders,service,jobs,exports,queries/validation,queries/dashboards,hex_projects}
```

Folder layout:
```
rm-analytics/
├── CLAUDE.md           # context for Claude Code (copy from companion file)
├── README.md
├── .gitignore
├── requirements.txt
├── Dockerfile          # for Fly.io
├── fly.toml            # Fly.io config
│
├── schema/             # SQL migrations
├── loaders/            # Python ingestion scripts
├── service/            # FastAPI webhook service
├── jobs/               # scheduled tasks (Funraise nightly pull, mart refresh)
├── exports/            # Triton xlsx files land here (gitignored)
├── queries/
│   ├── validation/     # spot-check SQL after each load
│   └── dashboards/     # SQL backing each Hex dashboard
└── hex_projects/       # Local copies of Hex notebooks (synced via hex CLI)
```

## 3.3 — .gitignore

```bash
cat > .gitignore << 'EOF'
exports/*.xlsx
exports/*.csv
.env
.venv/
__pycache__/
*.pyc
.DS_Store
hex_projects/.cache/
EOF
```

## 3.4 — Drop in CLAUDE.md

Copy the comprehensive CLAUDE.md from the companion file `CLAUDE.md`
into your project root. This is what Claude Code reads automatically every
session — it contains the full database structure, station mapping, query
catalog, and operational rules.

## 3.5 — Python virtual env

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3.6 — Requirements

```bash
cat > requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn[standard]==0.32.0
psycopg2-binary==2.9.10
pandas==2.2.3
openpyxl==3.1.5
python-dotenv==1.0.1
requests==2.32.3
python-multipart==0.0.12
EOF

pip install -r requirements.txt
```

## 3.7 — Open in Claude Code

```bash
claude .
```

Claude reads your `CLAUDE.md` automatically. It now knows the full context.

---

# Phase 4 — Full schema migration

## 4.1 — Generate the migration via Claude Code

In Claude Code:

> *Read CLAUDE.md and create schema/001_initial.sql that creates all the
> Postgres schemas and dimension tables described there. The schemas are:
> wms, ga, meta_organic, meta_ads, linkedin, youtube, tiktok, funraise,
> email_esp, finance, underwriting, grants, events, dim, marts.*
>
> *Also create schema/002_wms_facts.sql with the five Triton fact tables
> from the query catalog. All five need (composite_key) DO UPDATE ON
> CONFLICT for upserts, plus a loaded_at timestamp column. Use the exact
> column types from the CLAUDE.md TSL parsing and Date/Hour conventions.*
>
> *Seed dim.stations with the four station codes (RM88, HYFIN, RM414, RLR)
> mapping to the Triton station strings. Create dim.dayparts with the 5
> standard dayparts. Create dim.dates as a calendar table populated for
> 2020-01-01 through 2030-12-31. Create dim.brand_channels as the channel
> mapping table per CLAUDE.md.*

Review the SQL Claude drafts. When it looks right:

> *Apply schema/001_initial.sql and schema/002_wms_facts.sql to the Neon
> database via the Neon MCP.*

## 4.2 — Verify

```bash
psql "$DATABASE_URL" -c "\dn"     # list schemas
psql "$DATABASE_URL" -c "\dt wms.*"
psql "$DATABASE_URL" -c "\dt dim.*"
psql "$DATABASE_URL" -c "SELECT code, brand_name FROM dim.stations;"
```

You should see 15 source schemas, 5 fact tables in `wms`, and 4 rows in
`dim.stations`.

## 4.3 — Hold on other tables for now

We're NOT creating fact tables in `funraise`, `meta_organic`, `meta_ads`,
`finance`, etc. yet. Those happen in their respective integration phases.
The empty schemas just establish the namespace.

---

# Phase 5 — Triton bulk exports

## 5.1 — Reminder

You already have Q1 done. Copy your file into `exports/`:

```bash
cp ~/Downloads/WCM_2026-05-20_88Nine-Rad_2024-01-01_2026-05-16.xlsx \
   ~/code/rm-analytics/exports/Q1_hourly_2024-01-01_2026-05-16.xlsx
```

## 5.2 — Run the other four

For each query, in Triton WMS:
1. Build a Query (or duplicate Q1's structure)
2. Set date range: `2024-01-01` to today
3. Select all 4 stations: WYMSFM, WYMSHD2, 414 Music, Rhythm Lab Radio 24/7
4. Configure metrics + dimensions per the table below
5. Output: XLSX
6. Save to `exports/`

| Query | Metrics | Dimensions | Save as |
|---|---|---|---|
| Q2a Daily cume | Unique Listeners, TLH, ATL, CUME | Date, Station | `Q2a_daily_cume_2024-01-01_to_today.xlsx` |
| Q2c Monthly cume | Unique Listeners, TLH, CUME | Month, Station | `Q2c_monthly_cume_2024-01-01_to_today.xlsx` |
| Q3 Geo | Sessions Started, TLH, Unique Listeners | Date, Station, Country, Region, City | `Q3_geo_<chunk>.xlsx` (chunked into 6-month windows) |
| Q4 Device | Sessions Started, TLH, Unique Listeners | Date, Station, Device Category, OS, Player | `Q4_device_2024-01-01_to_today.xlsx` |

**Q3 Geo chunks (5 files):**
- `Q3_geo_2024-01-01_to_2024-06-30.xlsx`
- `Q3_geo_2024-07-01_to_2024-12-31.xlsx`
- `Q3_geo_2025-01-01_to_2025-06-30.xlsx`
- `Q3_geo_2025-07-01_to_2025-12-31.xlsx`
- `Q3_geo_2026-01-01_to_today.xlsx`

---

# Phase 6 — Backfill loaders

## 6.1 — Build the common helpers first

In Claude Code:

> *Create loaders/_common.py with:*
> *1. A STATION_MAP dict for Triton string → station_code per CLAUDE.md*
> *2. A parse_tsl(s) function that converts "HH:MM" to total minutes (float)*
> *3. A get_db_connection() function that reads DATABASE_URL from
> ~/.radio-milwaukee/.env and returns a psycopg2 connection*
> *4. A bulk_upsert(conn, table, columns, rows, conflict_columns,
> update_columns) function that uses psycopg2.extras.execute_values in
> batches of 5000 with ON CONFLICT DO UPDATE*

## 6.2 — Build the Q1 loader

> *Create loaders/load_q1_hourly.py that uses _common.py. It should:*
> *1. Accept an xlsx file path as a CLI arg*
> *2. Read the file with pandas*
> *3. Parse Station, Date Hour, AAS, TLH, CUME, SS, TSL columns*
> *4. Split Date Hour into date + hour*
> *5. Parse TSL via _common.parse_tsl*
> *6. Map Station via _common.STATION_MAP*
> *7. Bulk upsert into wms.fact_hourly_listening on
> (station_code, date, hour) primary key*
> *8. Expose a load(file_path) function for webhook reuse, with
> if __name__ == "__main__" calling it from sys.argv[1]*
> *9. Print row count and timing*

Run it:

```bash
python loaders/load_q1_hourly.py exports/Q1_hourly_2024-01-01_2026-05-16.xlsx
```

Expect:
```
Loaded 60,130 rows into wms.fact_hourly_listening in 14.2s
```

## 6.3 — Build the rest

Same pattern, in Claude Code:

> *Create loaders/load_q2a_daily_cume.py, loaders/load_q2c_monthly_cume.py,
> loaders/load_q3_geo.py (accepts a glob pattern for multiple files), and
> loaders/load_q4_device.py. All follow the same skeleton as
> load_q1_hourly.py — common imports, load() function, CLI shim. Use the
> column mappings in CLAUDE.md.*

Then run each:

```bash
python loaders/load_q2a_daily_cume.py exports/Q2a_daily_cume_*.xlsx
python loaders/load_q2c_monthly_cume.py exports/Q2c_monthly_cume_*.xlsx
python loaders/load_q3_geo.py 'exports/Q3_geo_*.xlsx'
python loaders/load_q4_device.py exports/Q4_device_*.xlsx
```

---

# Phase 7 — Validate

## 7.1 — Row counts

In Claude Code:

> *Use the Neon MCP to run this query and show me the output:*
> ```sql
> SELECT 'hourly' AS source, COUNT(*) FROM wms.fact_hourly_listening
> UNION ALL SELECT 'daily_cume', COUNT(*) FROM wms.fact_daily_cume
> UNION ALL SELECT 'monthly_cume', COUNT(*) FROM wms.fact_monthly_cume
> UNION ALL SELECT 'geo', COUNT(*) FROM wms.fact_daily_geo
> UNION ALL SELECT 'device', COUNT(*) FROM wms.fact_daily_device;
> ```

## 7.2 — Spot check against Triton UI

Pick one specific hour/day in Triton UI. Find that exact (station_code,
date, hour) in Neon. Numbers must match exactly.

## 7.3 — Commit

```bash
git add . && git commit -m "Phase 1-7 complete: schema + streaming backfill loaded"
```

---

# Phase 8 — Daily pipeline (Fly.io + AgentMail)

**See companion file:** `phase-8-revised-agentmail-flyio.md`

That doc covers the full deployment of `rm-data-loader` on Fly.io, the
AgentMail webhook config, Triton scheduled query setup, and end-to-end test.

**One change from that doc:** the service is now `rm-data-loader` (not
`rm-wms-loader`) because it'll also handle the Funraise route. Adjust app
names in `fly.toml` and `flyctl` commands accordingly.

---

# Phase 9 — Funraise integration

Funraise feeds donations into the `funraise` schema. Two ingestion paths:
real-time webhook (transactions) and nightly API pull (supporters,
subscriptions, reconciliation).

## 9.1 — Get Funraise API access

In your Funraise dashboard:
1. **Settings → API Keys → Generate new key**
2. Copy the key immediately — you can't view it again
3. Save to your password manager labeled `FUNRAISE_API_KEY`

## 9.2 — Create the funraise schema tables

In Claude Code:

> *Create schema/003_funraise.sql with these tables:*
> *- funraise.fact_transactions — every donation: transaction_id (PK),
> supporter_id, amount, fee, net, currency, payment_method, status,
> created_at, modified_at, campaign_id, designation, recurring (bool),
> utm_source, utm_medium, utm_campaign, raw_payload (JSONB for whatever
> we don't model yet)*
> *- funraise.dim_supporters — supporter_id (PK), email, first_name,
> last_name, address fields, first_donation_date, lifetime_total,
> created_at, updated_at*
> *- funraise.fact_subscriptions — subscription_id (PK), supporter_id,
> amount, frequency, status (active/canceled/failed), started_at,
> canceled_at, next_charge_at*
> *- funraise.dim_campaigns — campaign_id (PK), name, type, started_at,
> ended_at, goal*
> *All fact tables get loaded_at TIMESTAMPTZ. ON CONFLICT DO UPDATE
> on all primary keys.*

Apply via the Neon MCP.

## 9.3 — Build the webhook receiver

> *Add a new route to service/main.py: POST /webhook/funraise. It should:*
> *1. On first call from Funraise, echo back the x-hook-secret header to
> confirm webhook subscription*
> *2. On subsequent calls, validate the signing secret against
> FUNRAISE_WEBHOOK_SECRET env var*
> *3. Parse the transaction payload*
> *4. Call loaders/load_funraise_webhook.py's load_transaction(payload) function*
> *5. Post a Slack message: "💰 Funraise: $50 from anonymous, RID:abc123"*
> *6. Return 200*

> *Create loaders/load_funraise_webhook.py with load_transaction(payload)
> that upserts into funraise.fact_transactions. Save the entire raw payload
> to the raw_payload JSONB column so we can backfill any new fields later
> without re-asking Funraise.*

## 9.4 — Build the nightly API pull

> *Create jobs/nightly_funraise_pull.py that:*
> *1. Uses FUNRAISE_API_KEY from env*
> *2. Pulls transactions from the last 7 days (catches anything the webhook missed)*
> *3. Pulls all active subscriptions*
> *4. Pulls supporters modified in the last 30 days*
> *5. Upserts to the respective tables*
> *6. Posts a Slack summary*

## 9.5 — Backfill historical donations

In Funraise dashboard:
1. **Reports → Transactions → Export CSV**
2. Set range to all time
3. Save as `exports/Funraise_transactions_all_time.csv`

> *Create loaders/load_funraise_csv_backfill.py that reads the CSV export
> and upserts to funraise.fact_transactions. Same idempotency pattern.*

Run it:
```bash
python loaders/load_funraise_csv_backfill.py exports/Funraise_transactions_all_time.csv
```

## 9.6 — Deploy + configure webhook

```bash
flyctl secrets set \
  FUNRAISE_API_KEY="<your-api-key>" \
  FUNRAISE_WEBHOOK_SECRET="$(openssl rand -hex 32)" \
  --app rm-data-loader
flyctl deploy --app rm-data-loader
```

In Funraise dashboard:
1. **Settings → Webhooks → Add webhook**
2. URL: `https://rm-data-loader.fly.dev/webhook/funraise`
3. Pass the FUNRAISE_WEBHOOK_SECRET as the signing secret
4. Trigger: Transaction created OR edited
5. Save → Funraise will ping your endpoint to verify the secret echo

## 9.7 — Schedule the nightly pull

In Fly.io, you can either:
- Use Fly's cron via `flyctl machines update` with `[processes.cron]` —
  see Fly docs for the exact syntax current at deploy time, or
- Use an external cron-as-a-service (cron-job.org, EasyCron) that hits a
  `/cron/funraise-nightly` HTTP endpoint at 3am CT daily

Either works. The HTTP endpoint pattern is simpler if you don't want to
mess with Fly's machine processes.

---

# Phase 10 — Coupler.io imports (Meta, GA, ESP)

## 10.1 — Connect Coupler to Neon

In Coupler.io:
1. **+ New importer** → Source: PostgreSQL → that's actually for *reading* —
   we want Coupler as *destination*. So:
2. **+ New importer** → Source: whichever data source → Destination: PostgreSQL
3. Paste your Neon DATABASE_URL
4. Coupler auto-discovers schemas

## 10.2 — Meta organic (Facebook + Instagram)

Two separate Coupler importers:

**Importer 1: Facebook Pages**
- Source: Facebook Pages
- Auth via Meta OAuth
- Select all Radio Milwaukee FB pages (88Nine, HYFIN, etc.)
- Destination schema: `meta_organic`
- Tables: `fact_page_daily`, `dim_posts`, `fact_post_lifetime`
- Schedule: Daily 7:00am CT

**Importer 2: Instagram Business**
- Source: Instagram Business
- Auth via the same Meta OAuth (must be Business or Creator accounts)
- Destination schema: `meta_organic`
- Same tables (Coupler will figure out the IG-specific shape)
- Schedule: Daily 7:15am CT

## 10.3 — Meta ads

- Source: Facebook Ads (covers both FB and IG paid)
- Destination schema: `meta_ads`
- Tables: `fact_ad_insights_daily`, `dim_campaigns`, `dim_ads`
- Schedule: Daily 7:30am CT

## 10.4 — Google Analytics 4

- Source: Google Analytics 4
- Auth via Google OAuth
- Select all RM web properties (88nine.org, hyfinmke.com, etc.)
- Destination schema: `ga`
- Schedule: Daily 7:45am CT

## 10.5 — Email ESP

When you finalize which ESP Radio Milwaukee uses (Mailchimp, etc.):
- Source: <your ESP>
- Destination schema: `email_esp`
- Schedule: Daily 8:00am CT

## 10.6 — Populate dim.brand_channels

After Coupler creates the source tables, you need to map each handle/account
to a station_code. In Claude Code:

> *Help me populate dim.brand_channels. Query meta_organic and meta_ads to
> see what page_ids, instagram_user_ids, and ad_account_ids we now have.
> Then generate the INSERT statements for dim.brand_channels mapping each
> to the right station_code (88Nine→RM88, HYFIN→HYFIN, etc.).*

---

# Phase 11 — Finance ingestion

The finance schema starts as monthly XLSX uploads from your accounting
system. Later you can wire up QuickBooks/Sage Intacct API if/when it's
worth the effort.

## 11.1 — Create finance tables

> *Create schema/006_finance.sql with:*
> *- finance.dim_categories — category_id, name, parent_category, type
> (revenue/expense), is_restricted*
> *- finance.dim_fiscal_periods — fiscal_year, fiscal_month, calendar_month,
> period_label*
> *- finance.fact_revenue_monthly — (month, category_id, station_code,
> is_restricted, amount) — PK on (month, category_id, station_code,
> is_restricted)*
> *- finance.fact_budget_monthly — same grain as revenue, with budget_amount*
> *- finance.fact_expense_monthly — (month, category_id, station_code,
> amount) — PK*
> *- finance.fact_membership_summary_monthly — (month, station_code,
> active_members, new_members, churned_members, mrr) — populated by view
> derived from funraise.\**
>
> *Also confirm Radio Milwaukee's fiscal year — verify this with their
> finance team before populating dim_fiscal_periods.*

Apply via Neon MCP.

## 11.2 — Seed the categories

> *Help me draft INSERT statements for finance.dim_categories. Standard
> public radio revenue categories include: underwriting, individual_giving,
> major_gifts, grants_unrestricted, grants_restricted, events, royalties,
> sponsorships, in-kind, other. Expense categories should mirror IRS Form
> 990 functional expense categories: program_services, management_general,
> fundraising.*

## 11.3 — Historical revenue upload

Get a multi-year revenue export from your finance team in this format:
| month | category | brand | restricted | amount |

> *Create loaders/load_finance_monthly.py that reads an XLSX with the above
> schema and upserts to finance.fact_revenue_monthly. Map the category
> string column to category_id via a lookup against dim.dim_categories.*

Run it for revenue, budget, and expenses (one XLSX each).

## 11.4 — Build the membership summary view

> *Create schema/100_marts.sql with finance.fact_membership_summary_monthly
> as a MATERIALIZED VIEW computed from funraise.fact_transactions and
> funraise.fact_subscriptions. New members = first donation in that month.
> Churned = subscription canceled in that month. Active = had any
> transaction in trailing 12 months. MRR = sum of active monthly
> subscription amounts.*

Refresh nightly:
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY finance.fact_membership_summary_monthly;
```

---

# Phase 12 — Hex dashboards

This is where Hex earns its keep. Notebooks with SQL + Python +
visualizations, plus AI-assisted exploration that Looker Studio can't do.

## 12.1 — Apply for nonprofit pricing

**Do this before building anything in Hex.** Hex is free for qualified
nonprofits.

1. Email `nonprofits@hex.tech` from your radiomilwaukee.org address
2. Mention 501(c)(3) status and EIN
3. They'll typically respond within a few business days
4. Once approved you get full Team-tier features at no cost

Don't skip this — it's a significant savings ($149-199/seat/month list price).

## 12.2 — Connect Hex to Neon

In Hex (web UI):
1. **Settings → Data sources → + Connection**
2. Select **Postgres**
3. Fill in connection details:
   - Host: from your Neon connection string (`ep-xxxxx.us-east-1.aws.neon.tech`)
   - Port: 5432
   - Database: `neondb`
   - User: `neondb_owner`
   - Password: from your `.env`
   - Require SSL: yes
4. Test connection → Save
5. Name it `RM Analytics Warehouse`

## 12.3 — Create dashboard projects via CLI

This is where Claude Code + Hex CLI shines. In Claude Code:

> *Use the Hex CLI to create a new project called "Program Director Dashboard".
> The project should have:*
> *1. A SQL cell querying wms.fact_hourly_listening joined to dim.stations
> for the last 30 days of TLH by station by hour*
> *2. A chart cell visualizing that as a heatmap (hour x day)*
> *3. A SQL cell computing daypart performance from the hourly data*
> *4. A chart cell with that as a grouped bar chart*
> *5. A SQL cell computing tune-out — sessions_started - sessions_ended
> by hour, last 7 days*
> *6. Use the data connection named "RM Analytics Warehouse"*

Repeat for:
- **Development Director Dashboard:** cume YoY, monthly trend, geo
  breakdown (Milwaukee MSA vs rest), TSL loyalty trend, donor count from
  funraise, new vs returning donor mix
- **Underwriting Director Dashboard:** AAS by daypart × station (rate card
  view), device split for advertiser pitches, inventory capacity from
  underwriting.fact_contracts, post-flight reconciliation
- **Finance/Executive Dashboard:** monthly revenue actual vs budget by
  category, multi-source revenue mix donut, YoY comparison, MRR trend
  from finance.fact_membership_summary_monthly, grants pipeline by stage
- **Daily Brand Health:** the cross-source `marts.daily_brand_health` view
  visualized — streaming + social + web + donations per brand per day

## 12.4 — Schedule the projects

For each Hex project that should run on a schedule:
1. In the Hex app: **Project settings → Schedule**
2. Set daily 9:00am CT (after all ingestion has completed)
3. Optionally: email/Slack notification when run completes with key numbers

## 12.5 — Share with stakeholders

For each dashboard:
1. Publish as a Hex **App** (this is the read-only consumer view)
2. Share link with the right director
3. They view in browser — no Hex login required for app viewers

Give each director only their own dashboard. Don't dump all four on
everyone — they care about different things.

---

# Operational reference

## Daily morning check

1. Slack channel should have ~6 ✅ messages by 8:30am CT:
   - 5 from Triton (Q1, Q2a, Q3, Q4 daily; Q2c on 1st)
   - 1 nightly Funraise reconciliation summary
2. Coupler.io importers should all show green in their dashboard
3. Hex app refreshes should show timestamp within last hour

If anything's red:

```bash
# Webhook service logs
flyctl logs --app rm-data-loader

# Database connection test
psql "$DATABASE_URL" -c "SELECT MAX(loaded_at) FROM wms.fact_hourly_listening;"

# Hex project run status
hex project list
hex run list --project <project-id>
```

## When adding a new query/source/dashboard

The pattern repeats:
1. Schema first (SQL migration via Neon MCP)
2. Loader / Coupler importer
3. Backfill (if applicable)
4. Validate against source
5. Add to `service/router.py` (if webhook) or schedule Coupler (if API)
6. Add Hex notebook + chart cells via Hex CLI
7. Update `CLAUDE.md` backfill status table

## Common commands

```bash
# Connect to project (from scratch)
cd ~/code/rm-analytics && source .venv/bin/activate && claude .

# Health checks
psql "$DATABASE_URL" -c "
SELECT schemaname, COUNT(*) AS n_tables
FROM pg_tables
WHERE schemaname IN ('wms','funraise','meta_organic','meta_ads','ga','email_esp','finance','underwriting','grants','events','dim','marts')
GROUP BY schemaname ORDER BY schemaname;"

# Backup
pg_dump "$DATABASE_URL" > backup_$(date +%Y%m%d).sql

# Update Hex notebooks in bulk via CLI
hex project list --json | jq '.[] | select(.name | contains("Director"))'

# Refresh marts views
psql "$DATABASE_URL" -c "REFRESH MATERIALIZED VIEW CONCURRENTLY marts.daily_brand_health;"
```

---

# Troubleshooting

**"Numbers in Neon don't match Triton UI"**
99% of the time: timezone mismatch, aggregation method confusion, or a
column you assumed was numeric being delivered as a formatted string.
Fix the parser, re-run the loader. Upsert handles the cleanup.

**"Hex notebook can't see new table I just created"**
Hex caches schema. In the project: SQL cell → … menu → Refresh schema.

**"Funraise webhook keeps failing the signing secret check"**
On first webhook from Funraise they send a different header pattern than
subsequent calls (x-hook-secret echo). Make sure the route handles both.
Check `flyctl logs` for the actual headers received.

**"Coupler importer is at row limit"**
Check your Coupler plan. The Squad/Business tiers have higher row caps.
For high-volume sources (GA can produce 100K+ rows/month), you may need
to upgrade. Alternative: write your own Python loader instead of using
Coupler for that specific source.

**"My Neon free tier database is paused"**
Auto-pause after inactivity. First query takes ~3s to wake. For
production-facing dashboards, consider upgrading Neon to the Launch plan
(~$19/mo) which removes auto-pause.

**"Hex CLI auth keeps expiring"**
Run `hex auth login` again. OAuth tokens refresh automatically in normal
use; expirations usually mean you've been away from the CLI for weeks.

---

# What we're NOT building (deliberately)

- **Triton a2x ad delivery schema** — not in scope, we removed it
- **LinkedIn, YouTube, TikTok schemas** — empty for now, fill if/when needed
- **Salesforce integration** — only if Funraise → Salesforce sync is the
  source of truth for donor data
- **Custom dashboards in Looker Studio** — Hex replaces this entirely
- **dbt** — overkill for this volume; the `marts` views handle our
  transformations directly in Postgres
- **Airflow / Prefect** — Fly.io cron + AgentMail webhooks + Coupler
  schedules cover all our scheduling needs

If any of these ever DO become in scope, the architecture absorbs them —
just add another schema, another loader, another Hex notebook. The
pattern doesn't change.
