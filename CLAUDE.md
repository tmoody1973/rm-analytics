# Radio Milwaukee Analytics Pipeline

> Context file for Claude Code. Read this first every session.

## What this project is

A unified analytics warehouse for Radio Milwaukee's four streaming brands,
plus social, web, donations, finance, and email data. The streaming side is
the first build; the architecture is designed to absorb other sources
without restructuring.

**Brands:**
- **88Nine Radio Milwaukee** (FM, AAA / Discovery)
- **HYFIN** (HD2 subchannel, Urban Alternative)
- **414 Music** (Local Music, streaming-only)
- **Rhythm Lab Radio** (Genre-Fluid Specialty, streaming-only)

**Audience for the dashboards:**
- **Program Director** — content, dayparts, tune-out analysis
- **Development Director** — cume, YoY trends, geo, loyalty, donor data, grant
  narratives
- **Underwriting Director** — AAS by daypart, device split, inventory capacity,
  underwriting revenue
- **Finance/Executive** — revenue vs budget, multi-source revenue mix,
  campaign ROI

## Stack

| Layer | Tech | Notes |
|---|---|---|
| Streaming source | Triton WMS | XLSX via scheduled email |
| Donations source | Funraise | REST API + transaction webhook |
| Social source | Meta Graph + Marketing API | Via Coupler.io (organic + paid) |
| Web source | Google Analytics 4 | Via Coupler.io |
| Email source | (ESP TBD — Mailchimp/etc) | Via Coupler.io |
| Finance source | Spreadsheets / QuickBooks export | Manual upload + later API |
| Inbox | AgentMail | `triton-ingest@yourdomain.com` for emails |
| Ingestion service | FastAPI on Fly.io | App: `rm-data-loader`, region `ord` (Chicago) |
| Warehouse | Neon Postgres | Project `radio-milwaukee-analytics`, db `neondb` |
| Backfill | Python scripts run locally | One-time historical loads |
| Daily updates | Webhook + Coupler.io | Coupler ingests Meta/GA/ESP; webhooks for Triton/Funraise |
| Presentation | Hex notebooks + apps | Reads from `marts.*` views; connects directly to Neon |
| Alerting | Slack webhook | Per-source success/failure messages |

---

## Database structure

Single Neon database (`neondb`), organized by **schema-per-source**. Critical
principle: **source schemas are sacred and untouched** — they mirror exactly
what the vendor sends. The `marts` schema is where joins happen for dashboards.

```
neondb
│
├── ────── STREAMING ───────
├── wms                     ← Triton streaming facts (Q1, Q2a, Q2b, Q2c, Q3, Q4)
│
├── ────── AUDIENCE / WEB / SOCIAL ──────
├── ga                      ← Google Analytics 4
├── meta_organic            ← Facebook + Instagram organic posts/pages
├── meta_ads                ← Facebook + Instagram paid campaigns (separate API!)
├── linkedin                ← LinkedIn page analytics (future)
├── youtube                 ← YouTube channel + video analytics (future)
├── tiktok                  ← TikTok organic (future, if relevant)
│
├── ────── DONATIONS / CRM ──────
├── funraise                ← Funraise transactions, supporters, subscriptions
│
├── ────── EMAIL ──────
├── email_esp               ← Mailchimp/etc — campaign sends, opens, clicks
│
├── ────── REVENUE & FINANCE ──────
├── finance                 ← Revenue actuals, budgets, expenses, by category
├── underwriting            ← Underwriting contracts + delivery (sold inventory)
├── grants                  ← Grant pipeline, awards, restricted vs unrestricted
│
├── ────── EVENTS / EARNED ──────
├── events                  ← Event ticketing, attendance, revenue (AXS, etc.)
│
├── ────── SHARED + DERIVED ──────
├── dim                     ← Shared dimensions (stations, dates, channels)
└── marts                   ← Cross-source views for dashboards
```

**Why split Meta into two schemas:** The Graph API (organic) and Marketing API
(paid ads) return fundamentally different shapes — organic doesn't have spend,
paid doesn't have "organic reach" the same way. They use different OAuth
permissions and different rate limits. Keeping them separate means a Meta API
change to one side never breaks the other.

**Why a finance schema separate from underwriting/grants:** Finance is the
*output* (revenue by month, by category, vs budget). Underwriting and grants
are *operational pipelines* (which client/grant, at what stage, when expected).
They feed into `finance.fact_revenue_monthly` via the `marts` layer.

---

## Schemas: what goes in each

### `wms` (Triton streaming)
Already documented below in "Query catalog." Six fact tables. Note that
Triton a2x ad-delivery data is OUT OF SCOPE for this build.

**Grain decision:** CUME is non-additive, so we query it natively at the four
grains we report at: hourly (Q1 embed), daily (Q2a), weekly (Q2b), monthly
(Q2c). Geo and device data is captured monthly only, since 95% of audience and
underwriting questions are inherently monthly.

### `funraise`
Mirrors Funraise's API shape:
- `funraise.fact_transactions` — every donation (one-time + recurring),
  amount, fee, net, supporter_id, campaign_id, date, payment method,
  UTM source/medium/campaign
- `funraise.dim_supporters` — donors (name, email, first donation, lifetime
  total, supporter_id is PK)
- `funraise.fact_subscriptions` — recurring giving plans (active, churned,
  amount, frequency)
- `funraise.dim_campaigns` — Funraise campaign metadata
Populated via the Funraise webhook (transactions) + nightly API pull
(supporters, subscriptions for the slow-changing data).

### `meta_organic`
- `meta_organic.fact_page_daily` — daily page-level metrics per
  (date, page_id): impressions, reach, engaged_users, follows, unfollows
- `meta_organic.fact_post_lifetime` — per-post lifetime stats:
  impressions, reach, reactions, comments, shares, video_views,
  saves (IG), profile_visits
- `meta_organic.dim_posts` — post metadata (caption, media_url,
  post_type, published_at)
Populated via Coupler.io (Meta Graph API → Coupler → Neon).

### `meta_ads`
- `meta_ads.fact_ad_insights_daily` — per (date, ad_id):
  impressions, reach, clicks, spend, CPM, CPC, conversions
- `meta_ads.dim_campaigns` — campaign hierarchy: campaign → ad_set → ad
- `meta_ads.dim_ads` — ad creative metadata
Populated via Coupler.io (Meta Marketing API → Coupler → Neon).

### `ga`
- `ga.fact_sessions_daily` — sessions, users, page_views per
  (date, property_id, source_medium, country)
- `ga.fact_events_daily` — custom events (stream_start_click, donate_click, etc.)
- `ga.dim_pages` — page paths + titles
Populated via Coupler.io.

### `email_esp`
- `email_esp.fact_campaign_sends` — campaign_id, sent, opens, clicks,
  unsubscribes, bounces
- `email_esp.dim_lists` — list_id → station mapping (via `dim.brand_channels`)
- `email_esp.fact_subscriber_events` — opt-ins, opt-outs by day
Populated via Coupler.io once ESP is selected.

### `finance`
**This is the financial truth table for the org.**
- `finance.fact_revenue_monthly` — revenue by (month, category, brand,
  restricted_yn). Categories include: underwriting, individual_giving,
  major_gifts, grants, events, royalties, other.
- `finance.fact_budget_monthly` — same grain as revenue, but budget values
  by fiscal year
- `finance.fact_expense_monthly` — expenses by (month, category, brand)
- `finance.dim_categories` — revenue/expense category lookup with rollups
- `finance.dim_fiscal_periods` — your FY calendar (Radio Milwaukee likely
  uses calendar year or 7/1 FY — verify and document)
- `finance.fact_membership_summary_monthly` — derived from `funraise.*`:
  active members, new acquired, churned, net change, MRR
Populated initially via XLSX upload (one-time historical), then via
QuickBooks export pipeline (or QB Online API later).

### `underwriting`
**Operational pipeline for the Underwriting Director.**
- `underwriting.fact_contracts` — every signed contract: client, flight
  window, dayparts, spots, contracted_impressions, contracted_revenue,
  station(s)
- `underwriting.fact_delivery` — actual impressions/spots delivered per
  (contract_id, date), pulled from Triton a2x when wired
- `underwriting.dim_clients` — advertiser names + categories (auto, CPG,
  healthcare, etc.)
- `underwriting.fact_pipeline` — opportunities by stage (prospect → pitched
  → contract → flight → renewed/lost) with expected close date
Initially: XLSX upload from sales tracker. Later: CRM integration.

### `grants`
- `grants.fact_grants` — every grant tracked: funder, amount, fiscal year,
  restricted purpose, status (applied/awarded/declined), reporting deadlines
- `grants.dim_funders` — foundation/corporate/government metadata
Maintained manually for now.

### `events`
- `events.fact_events` — event_id, date, venue, attendance, gross_revenue,
  net_revenue, station(s) promoted
- `events.fact_ticket_sales` — per-event ticket transactions if available
Populated from AXS Group API (when license is wired) or manual XLSX uploads.

### `dim` (shared)
- `dim.stations` — the 4 station codes (RM88, HYFIN, RM414, RLR)
- `dim.dates` — every date 2020–2030 with year/month/quarter/week/FY
- `dim.dayparts` — 5 standard dayparts
- `dim.geographies` — city → region → DMA → MSA → country roll-ups
- `dim.campaigns` — marketing/programming campaign windows (pledge drives,
  product launches, festival promos)
- `dim.shows` — show name × station × schedule grid
- `dim.brand_channels` — **CRITICAL** — maps each social handle, GA property,
  email list, ad account to a station_code. Without this, every cross-source
  query has hardcoded `WHERE handle = '@hyfinmke'` filters.

### `marts` (derived, cross-source)
Materialized views and tables that answer real business questions:
- `marts.daily_brand_health` — for each (date, brand): streaming TLH + cume,
  web sessions, social impressions (org+paid), email opens, donations.
  The "what happened yesterday" snapshot.
- `marts.monthly_revenue_dashboard` — joins finance + funraise + underwriting
  + grants + events for the full revenue picture per month vs budget.
- `marts.audience_funnel` — for each (date, brand): paid social impressions
  → organic reach → web sessions → stream starts → email signups → donations.
- `marts.campaign_impact` — lift in streaming/social/web/donations during
  campaign windows vs prior comparable windows.
- `marts.donor_streaming_overlap` — joins Funraise supporters to inferred
  streaming behavior where possible (email match against ESP list, etc.).
  High-value insight for development.
- `marts.underwriting_inventory_capacity` — AAS by daypart × station with
  current contracted spots overlaid. Sold-out analysis.

---

## Triton WMS export conventions

### Station code mapping

| Triton "Station" string | Internal `station_code` | Brand |
|---|---|---|
| `WYMSFM` | `RM88` | 88Nine Radio Milwaukee |
| `WYMSHD2` | `HYFIN` | HYFIN (88.9 HD2) |
| `414 Music` | `RM414` | 414 Music |
| `Rhythm Lab Radio 24/7` | `RLR` | Rhythm Lab Radio |

### TSL parsing
Triton exports TSL as `"HH:MM"` string (e.g. `"00:46"` = 46 min). Parse to
`tsl_minutes` (NUMERIC).

### Date/Hour parsing
Triton exports "Date Hour" as `"YYYY-MM-DD HH:MM:SS"`. Split to `date` (DATE)
+ `hour` (INT 0–23).

### Numeric coercion
Empty strings → 0 on parse.

### Data caveats
- **Rhythm Lab Radio 24/7** mount went live 2025-11-16. No history before that.
- **414 Music** has minor gaps in early 2024.
- Hourly TSL above ~3 hours is real (long-haul listeners) — don't filter.

---

## Query catalog (streaming)

All six queries land in `wms.fact_*`. Each has both a backfill loader
(historical, local) and a webhook route (daily, Fly.io). Same function,
two entry points.

| ID | Description | Target table | Loader | Webhook tag |
|---|---|---|---|---|
| Q1 | Hourly listening | `wms.fact_hourly_listening` | `load_q1_hourly.py` | `[WMS-Q1-HOURLY]` |
| Q2a | Daily cume | `wms.fact_daily_cume` | `load_q2a_daily_cume.py` | `[WMS-Q2A-CUME-DAILY]` |
| Q2b | Weekly cume | `wms.fact_weekly_cume` | `load_q2b_weekly_cume.py` | `[WMS-Q2B-CUME-WEEKLY]` |
| Q2c | Monthly cume | `wms.fact_monthly_cume` | `load_q2c_monthly_cume.py` | `[WMS-Q2C-CUME-MONTHLY]` |
| Q3 | Monthly geography | `wms.fact_monthly_geo` | `load_q3_monthly_geo.py` | `[WMS-Q3-GEO]` |
| Q4 | Monthly device/platform | `wms.fact_monthly_device` | `load_q4_monthly_device.py` | `[WMS-Q4-DEVICE]` |

Q7 (session duration buckets) deferred — derive in SQL from Q1.

### Saved-query inventory & schedule

Each of the 6 queries exists twice in Triton: a **Bulk** saved query (one-time
historical export, run locally for backfill) and a **Scheduled** saved query
(recurring email → AgentMail → Fly.io webhook). That's **6 Bulk + 6 Scheduled =
12 saved queries** total.

| Query | Cadence | Trigger (CT) | Webhook tag |
|---|---|---|---|
| Q1 Hourly | Daily | 6:00am | `[WMS-Q1-HOURLY]` |
| Q2a Daily cume | Daily | 6:15am | `[WMS-Q2A-CUME-DAILY]` |
| Q2b Weekly cume | Weekly (Mon) | 6:30am | `[WMS-Q2B-CUME-WEEKLY]` |
| Q2c Monthly cume | Monthly (1st) | 8:00am | `[WMS-Q2C-CUME-MONTHLY]` |
| Q3 Monthly geography | Monthly (1st) | 8:15am | `[WMS-Q3-GEO]` |
| Q4 Monthly device | Monthly (1st) | 8:30am | `[WMS-Q4-DEVICE]` |

### Per-query metadata

**Q1 Hourly** — Cols: Station, Date Hour, AAS, TLH, CUME, SS, TSL. Daily 6:00am CT.
~96 rows/day. Backfill ~60K rows (2024-01-01 onward).

**Q2a Daily cume** — Cols: Station, Day, AAS, TLH, CUME, SS, TSL.
Daily 6:15am CT. ~4 rows/day. Cume is non-additive.

**Q2b Weekly cume** — Cols: Station, Week, AAS, TLH, CUME, SS, TSL. Weekly,
Mon 6:30am CT. ~4 rows/week. Backfill ~520 rows (2024-01-01 onward). Cume is
non-additive.

**Q2c Monthly cume** — Cols: Station, Month, AAS, TLH, CUME, SS, TSL.
1st of month 8am CT. ~4 rows/month.

**Q3 Monthly geography** — Cols: Station, Month, Country, Region, City, AAS,
TLH, CUME, SS, TSL. Triton dimension = Month (not Day). 1st of month 8:15am CT.
~800 rows/month.

**Q4 Monthly device** — Cols: Station, Month, Device Category, OS, Player, AAS,
TLH, CUME, SS, TSL. Triton dimension = Month (not Day). 1st of month 8:30am CT.
~50-200 rows/month.

---

## Funraise integration

### Authentication
- API key generated in Funraise Dashboard → Settings → API Keys
- Webhook signing: Funraise sends `x-hook-secret` in request header on first
  call; our endpoint must echo it back to confirm subscription
- Keep API key in Fly.io secret `FUNRAISE_API_KEY`, signing secret in
  `FUNRAISE_WEBHOOK_SECRET`

### Real-time path (webhook)
- Transaction webhook fires on transaction create OR edit
- Endpoint: `https://rm-data-loader.fly.dev/webhook/funraise`
- Retries for ~24 hours on failure (good — no need to build our own retry)
- Payload includes full transaction: amount, fee, net, supporter info,
  campaign, UTM, payment method, timestamp
- Upserts to `funraise.fact_transactions` with `ON CONFLICT (transaction_id)
  DO UPDATE` (handles the "edit" case)

### Daily reconciliation path (API pull)
- Even with the webhook, run a nightly API pull for the last 7 days to catch
  anything the webhook missed (network blips, retried transactions, etc.)
- Endpoint pulls supporters + subscriptions which don't have webhooks
- Scheduled via Fly.io cron (or external cron triggering an HTTP endpoint)

### Caveats
- "Fundraise Up" (fundraiseup.com) is a DIFFERENT product. Don't confuse.
- Coupler.io does NOT have a native Funraise connector — that's why we go
  webhook + API. Don't waste time looking for one.
- Funraise has a Salesforce integration — if Radio Milwaukee uses Salesforce
  as the donor CRM downstream of Funraise, consider whether Salesforce is
  the source of truth instead. For now, treat Funraise as authoritative.

---

## Meta integration (organic + paid)

### Two APIs, two schemas

| API | Use for | Goes to schema | Coupler.io connector |
|---|---|---|---|
| Graph API / Page Insights | Organic posts/pages/reels | `meta_organic` | "Facebook Pages" + "Instagram" |
| Marketing API / Ads Insights | Paid campaigns, spend, ROAS | `meta_ads` | "Facebook Ads" + "Instagram Ads" |

### Important Meta API behavior
- For Facebook posts that are **boosted**, the Graph API's organic impression
  metric INCLUDES paid impressions. To get clean "organic-only," subtract
  boosted impressions from the same post via the Ads side. Document this in
  the `marts` views.
- For Instagram, Graph API returns organic-only — paid IG data lives in the
  Marketing API exclusively. Cleaner than FB on this front.
- Demographic breakdowns require ≥100 people in the audience or Meta returns
  nulls.

### Channel mapping for cross-source joins
Every Meta page, ad account, and IG profile gets a row in
`dim.brand_channels`:
```sql
INSERT INTO dim.brand_channels (station_code, platform, handle_or_id, display_name)
VALUES
  ('RM88',  'fb_page',     '123456789',     '88Nine Facebook'),
  ('HYFIN', 'fb_page',     '987654321',     'HYFIN Facebook'),
  ('RM88',  'ig_profile',  '17841400001',   '88Nine Instagram'),
  ('HYFIN', 'ig_profile',  '17841400002',   'HYFIN Instagram'),
  ('RM88',  'meta_ad_acct','act_111111',    '88Nine Ad Account'),
  ('HYFIN', 'meta_ad_acct','act_222222',    'HYFIN Ad Account');
```

---

## Operational pattern

### Backfill (one-time, per source)
Run locally with virtualenv active:
```bash
cd ~/code/rm-analytics
source .venv/bin/activate
python loaders/load_q1_hourly.py exports/Q1_hourly_2024-01-01_2026-05-16.xlsx
```
Idempotent — `ON CONFLICT DO UPDATE` everywhere. Safe to re-run.

### Daily incremental (automated)
- **Streaming (Triton):** AgentMail email → Fly.io webhook → loader → Neon
- **Donations (Funraise):** Funraise webhook → Fly.io webhook → loader → Neon
  + nightly API pull for supporters/subscriptions
- **Social/Web/Email (GA, Meta, ESP):** Coupler.io → Neon directly, daily
- **Finance:** Monthly manual upload (XLSX) → loader script → Neon, until
  QuickBooks API wired
- (9:00am CT) Hex projects refresh from `marts.*` views via scheduled runs

### Morning checks
- Slack channel for ✅ from each source. Triton (2 messages most days, 3 on Mondays incl. Q2b weekly, 6 on the 1st of the month incl. all monthly queries), Funraise
  (variable, only on transactions), Coupler (per importer).
- If anything ❌: `flyctl logs --app rm-data-loader` for stack trace.

---

## File system layout

```
~/code/rm-analytics/
├── CLAUDE.md                  ← this file
├── README.md
├── .gitignore
├── requirements.txt
├── Dockerfile
├── fly.toml
│
├── schema/
│   ├── 001_initial.sql        ← APPLIED — all source schemas + dim + marts skeleton
│   ├── 002_wms_facts.sql      ← APPLIED — Triton fact tables
│   ├── 003_wms_facts_revision.sql  ← APPLIED — monthly geo/device + weekly cume
│   ├── 004_funraise.sql       ← PLANNED (Phase 9) — Funraise tables
│   ├── 005_meta.sql           ← PLANNED (Phase 10) — Both Meta schemas
│   ├── 006_ga.sql             ← PLANNED (Phase 10)
│   ├── 007_finance.sql        ← PLANNED (Phase 11) — Finance + budget tables
│   ├── 008_underwriting.sql   ← PLANNED (Phase 11+)
│   ├── 009_grants.sql         ← PLANNED (Phase 11+)
│   ├── 010_events.sql         ← PLANNED (Phase 11+)
│   └── 100_marts.sql          ← PLANNED (Phase 12) — Cross-source views (rebuild often)
│
├── loaders/                   ← Importable AND CLI-runnable
│   ├── _common.py             ← Station map, TSL parse, DB conn, station_code resolver
│   ├── load_q1_hourly.py
│   ├── load_q2a_daily_cume.py
│   ├── load_q2b_weekly_cume.py
│   ├── load_q2c_monthly_cume.py
│   ├── load_q3_monthly_geo.py
│   ├── load_q4_monthly_device.py
│   ├── load_funraise_webhook.py
│   ├── load_funraise_api_pull.py     ← nightly reconciliation
│   └── load_finance_monthly.py       ← XLSX upload for revenue/budget
│
├── service/                   ← FastAPI on Fly.io
│   ├── __init__.py
│   ├── main.py                ← multi-route webhook + health
│   ├── router.py              ← maps inbound to loaders
│   ├── auth.py                ← shared secret + signing verification
│   └── slack.py
│
├── jobs/                      ← Scheduled tasks (Fly.io cron or similar)
│   ├── nightly_funraise_pull.py
│   └── refresh_marts.py       ← rebuild materialized views
│
├── exports/                   ← Triton xlsx, gitignored
│
├── hex_projects/              ← Local copies of Hex notebooks, synced via Hex CLI
│
└── queries/
    ├── validation/
    ├── dashboard_program_director.sql
    ├── dashboard_development.sql
    ├── dashboard_underwriting.sql
    └── dashboard_finance_exec.sql
```

---

## Credentials

`~/.radio-milwaukee/.env` (chmod 600, gitignored):
- `DATABASE_URL` — Neon

Fly.io secrets (via `flyctl secrets set`):
- `DATABASE_URL`
- `AGENTMAIL_WEBHOOK_SECRET`
- `FUNRAISE_API_KEY`
- `FUNRAISE_WEBHOOK_SECRET`
- `SLACK_WEBHOOK_URL`
- `META_ACCESS_TOKEN` (long-lived, only if doing direct Meta calls outside Coupler)

Never commit secrets. Never paste them in chat without rotating after.

---

## Coding conventions

- Python 3.12. Type hints where they help.
- psycopg3 (the `psycopg` package, currently 3.3.4) with `cursor.executemany()` or `COPY` for bulk inserts, batches of 5000. Import is `import psycopg`, not `import psycopg2`.
- Every fact table has `ON CONFLICT (composite_key) DO UPDATE`. Idempotency
  by default.
- Loaders are pure functions: `def load(file_path_or_payload) -> dict` with
  stats. `if __name__ == "__main__"` block for CLI.
- No row-by-row inserts. Ever.
- Source schemas are read-only after load. Transformation in `marts`.

---

## When extending

### Adding a new Triton query
1. Create loader in `loaders/`
2. Add table to new `schema/00N_*.sql`, apply via Neon MCP
3. Run backfill locally
4. Validate against Triton UI
5. Add to `service/router.py` with new tag
6. Add Triton scheduled query with matching tag
7. End-to-end test

### Adding a new data source via Coupler
1. Create schema: `CREATE SCHEMA new_source;`
2. Set up Coupler importer → Neon → target schema
3. Add channel mappings to `dim.brand_channels`
4. Extend `marts.daily_brand_health` to include new fields
5. Update dashboard SQL

### Adding a new data source via webhook (like Funraise)
1. Create schema + tables
2. Write loader function with idempotent upsert
3. Add new route in `service/main.py` (e.g. `/webhook/source-name`)
4. Configure signing/auth pattern (each vendor differs)
5. Test with a sample payload locally before deploying
6. Set up the webhook in the source platform pointing at Fly.io URL

---

## What NOT to do

- Don't put dashboard SQL in source schemas. Use `marts`.
- Don't manually edit fact tables. Re-run the loader.
- Don't merge Triton queries — webhook routing depends on subject tags.
- Don't skip `ON CONFLICT`. Every loader upserts.
- Don't run backfill through the webhook. Laptop for backfill, Fly.io for daily.
- Don't put `loaded_at` in primary keys. It's audit.
- Don't trust Triton column headers — re-verify after every Triton UI update.
- Don't conflate Funraise (funraise.org) with Fundraise Up (fundraiseup.com).
- Don't try to mix Meta organic and paid metrics in the same table. Two
  schemas, two truths, join in `marts`.
- Don't put financial data in any schema other than `finance` (and
  `underwriting`/`grants` for operational pipelines that *feed* finance).

---

## Backfill status (update as you go)

### Streaming
| Query | Loaded | Window | Rows | Validated |
|---|---|---|---|---|
| Q1 Hourly | [x] | 2024-01-01 to 2026-05-16 | ~60130 | [x] |
| Q2a Daily cume | [ ] | | | [ ] |
| Q2b Weekly cume | [ ] | | | [ ] |
| Q2c Monthly cume | [ ] | | | [ ] |
| Q3 Monthly Geography | [ ] | | | [ ] |
| Q4 Monthly Device | [ ] | | | [ ] |

### Other sources
| Source | Loaded | Method | Notes |
|---|---|---|---|
| Funraise transactions | [ ] | API pull → backfill | |
| Funraise supporters | [ ] | API pull | |
| Meta organic (FB+IG) | [ ] | Coupler | |
| Meta ads | [ ] | Coupler | |
| Google Analytics 4 | [ ] | Coupler | |
| Email ESP | [ ] | Coupler | |
| Finance — revenue history | [ ] | XLSX upload | |
| Finance — budget history | [ ] | XLSX upload | |
| Underwriting contracts | [ ] | XLSX upload | |
| Grants pipeline | [ ] | Manual entry | |
| Events history | [ ] | XLSX upload | |

## Service status

- [ ] Fly.io app `rm-data-loader` deployed
- [ ] AgentMail inbox + webhook (Triton) configured
- [ ] Funraise webhook configured + verified
- [ ] Coupler.io importers running (Meta, GA, ESP)
- [ ] Slack alerting wired for all sources
- [ ] All Triton scheduled queries enabled
- [ ] First full daily cycle completed successfully across all sources
- [ ] `marts.daily_brand_health` populating correctly
- [ ] `marts.monthly_revenue_dashboard` populating correctly
