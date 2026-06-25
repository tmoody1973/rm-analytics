# RM Executive Dashboard — build roadmap (next phase)

> Handoff for continuing the `dashboard/` app. Goal of this phase: **deepen each
> tab around what each leader actually needs**, and add a **global brand filter**
> that widgets honor where the data is brand-attributable.

## Where we are (current state)

- **App:** `dashboard/` — Vite + React, 6 **source-based** tabs (Overview, Financial,
  Digital Reach, Nielsen, Triton Streaming, Mailchimp). Pixel-faithful to the RM brand
  (design-system tokens in `src/theme.css`, Aktiv Grotesk + Sidewalk Block fonts in
  `public/fonts/`, crescendo logo, charcoal/cream/orange, Recharts charts charcoal+blue+
  orange — no cyan). Builds clean; QA'd in browser (data loads, brand correct, 0 errors).
- **Data:** one read-only call `GET https://rm-data-loader.fly.dev/api/dashboard`
  (`service/dashboard_api.py`, CORS on). Returns 16 aggregate datasets from Neon. Reads
  the POPULATED tables (`stg_*` for GA/Meta/Email; `fact_*` for streaming/funraise/nielsen/
  finance — the clean GA/Meta/Email `fact_*` are EMPTY, always use `stg_*`).
- **Run:** `cd dashboard && npm run dev` (or `npm run preview` on :4173). Deploy target: Vercel
  (static) pointing at the Fly API via `VITE_API_URL`.
- **Files:** `src/App.jsx` (shell + header KPI strip + tab switch), `src/tabs.jsx` (the 6
  tab render fns), `src/components.jsx` (RM palette, formatters, Kpi/ChartCard, pivot/distinct),
  `src/api.js`, `src/app.css` + `src/theme.css`.

## The shift this phase: source-based → role-based + brand filter

Leaders consume by **role**, and a metric often serves several roles (streaming TLH matters
to the Program Director AND Underwriting). Recommendation: **keep "Executive Overview" as the
landing tab, then organize the rest by role** (below). Build cross-source role tabs on top of
the existing datasets + new queries. Each role tab respects the global brand filter.

---

## Global BRAND FILTER (design)

A header control: **All Brands · 88Nine (RM88) · HYFIN · 414 Music (RM414) · Rhythm Lab (RLR) ·
Radio Milwaukee (RMORG)**. Selecting a brand filters every widget that is brand-attributable;
widgets that are org-wide show an **"Org-wide" badge and ignore the filter** (don't hide them —
label them). Implement as **client-side filtering**: the API returns brand-tagged rows
(`station_code` / a `brand` column where derivable), the frontend filters by the selection.

**Brand → data availability matrix** (VERIFIED 2026-06-25 from live distinct values — the
filter must surface only the channels a brand actually has; coverage is lopsided):

| Brand | Streaming | Nielsen | Web (GA4) | FB | IG | Email | Donations |
|---|---|---|---|---|---|---|---|
| **HYFIN** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| **Radio Milwaukee (RMORG)** | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **88Nine (RM88)** | ✅ | ✅ | ❌ | ❌ retired | ✅ | ❌ | ⚠️ |
| **414 Music (RM414)** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Rhythm Lab (RLR)** | ✅ (since 2025-11) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Grace Weber's Music Lab (GWML)** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ |

> Lopsided by design: **HYFIN** is the only brand in every channel. **RMORG** is the digital
> hub (web/social/email/donations) with no broadcast. **88Nine** = streaming + Nielsen + IG only.
> **414/RLR** stream only. **GWML** is a show with only social + email. The filter shows only the
> channels present for the selected brand; everything else hides or badges "not measured for this brand".

**Exact string → brand mapping (use these literal values in the API queries):**

| Channel | Source column | Literal value | → brand |
|---|---|---|---|
| Streaming | `wms.*.station_code` | `RM88` / `HYFIN` / `RM414` / `RLR` | direct |
| Nielsen | `nielsen.*.station_code` | `RM88` / `HYFIN` | direct (P6+, M-Su only) |
| Web | `ga.stg_sessions_daily.account__property_name` | `https://www.radiomilwaukee.org - GA4` → RMORG; `HYFIN` → HYFIN | |
| FB | `meta_organic.stg_fb_page_daily.account__account_name` | `Radio Milwaukee`→RMORG; `HYFIN`→HYFIN; `Grace Weber's Music Lab`→GWML | |
| IG | `meta_organic.stg_ig_profile_monthly.account__account_name` | `radiomilwaukee`→RMORG; `hyfin.mke`→HYFIN; `88nine.mke`→RM88; `gwmusiclab`→GWML | |
| Email | `email_esp.stg_lists.name` (+ `stg_campaigns_report.list_id`) | `Radio Milwaukee List`→RMORG; `HYFIN List`→HYFIN; `Grace Weber's Music Lab`→GWML; `Funraise`→exclude | |
| Donations | `funraise.*.designation` / `Form` | best-effort or leave org-wide | |

- `dim.brand_channels` is the intended canonical mapping table — **verify it's populated**; if not,
  hardcode the map above (it's now verified against live data). Email campaigns join to a list via
  `stg_campaigns_report.list_id` → `stg_lists.id` → name → brand.
- Finance (revenue/budget/cash/surplus) is **org-wide** — not brand-split. Badge it "Org-wide".

---

## Per-leader tab specs (the detail)

### 1. Executive Overview (landing — all leaders)
Keep current header KPI strip + at-a-glance cards. Add: revenue-vs-budget gauge, MRR vs target,
Nielsen share by station, combined digital reach, donor retention. Org-wide by default; brand
filter narrows the brand-attributable cards.

### 2. Program Director (content, dayparts, tune-out) — brand filter ESSENTIAL
What they want: *who's listening, when, to what, and are they staying.*
- **Daypart performance** — AAS by daypart × station (heatmap) [`wms.fact_hourly_listening`].
- **Hourly listening grid** — AAS/CUME by hour-of-day × day-of-week (programming grid) [hourly].
- **TSL / session duration** trend — engagement & tune-out signal [`tsl_minutes`].
- **TLH + AAS + CUME trends** by station [`wms.fact_monthly_cume` / daily].
- **Nielsen AQH/cume/share + TSL** trend, **daypart AQH**, **demo composition** [`nielsen`].
- **Top web content** (what stories resonate) [`ga.stg_pages_daily`].
- Streaming vs broadcast for the same station (two audiences, one brand).

### 3. Development Director (giving, loyalty, donors) — brand filter PARTIAL
What they want: *donor health, retention, growth, and where donors are.*
- **Active donors, new vs returning, lapsed** [`funraise`].
- **Donor retention / churn** trend; **sustainer MRR + net adds/churn** [`fact_subscriptions`].
- **Lifetime-value tiers** + top-donor distribution [`dim_supporters.lifetime_total`].
- **Gift size distribution**, recurring vs one-time mix, **acquisition channel/UTM**.
- **Donor geography** — city/state/ZIP map (pairs with the geo story) [`dim_supporters`].
- **Donor ↔ email overlap** (via `email_sha256`), audience→giving funnel.
- Individual giving vs budget [`finance`].

### 4. Digital Director (web/app) — brand filter ESSENTIAL
- **Sessions/users by site** (RM, 88Nine, HYFIN, 414, RLR) [`ga.stg_sessions_daily`].
- **Traffic sources** (organic/social/direct/referral) + **organic growth YoY**
  [`session__session_source___medium`].
- **Top content / pages / articles** [`ga.stg_pages_daily`].
- **Device split**, **geo**, **engagement time**.
- **Conversion events** — stream-start clicks, donate clicks [`ga.stg_events_daily`].
- **App** — engagement/downloads (GA app props + AppFigures `app_store.*`).

### 5. Social Media Director — brand filter ESSENTIAL (per page/handle)
- **Follower growth** by platform × brand (FB + IG per station) [`meta_organic.stg_fb_page_daily`,
  `stg_ig_profile_monthly`; map via `dim.brand_channels`].
- **Reach / impressions / engagement rate** trends.
- **Top posts** [`stg_fb_post_lifetime`, `stg_ig_post_lifetime`].
- Posting cadence vs engagement. (Paid = `meta_ads` — future.)
- Email could live here or under Digital (Mailchimp opens/clicks/growth by list→brand).

### 6. Underwriting Director (sellable audience, inventory) — brand filter ESSENTIAL
- **AAS by daypart × station** = sellable inventory [`wms.fact_hourly_listening`].
- **Device/platform split** (ad targeting) [`wms.fact_monthly_device`].
- **Nielsen AQH/cume + demos** (what advertisers buy) [`nielsen`].
- Underwriting revenue vs budget [`finance` — aggregate]. Pipeline/per-sponsor: **blocked**
  (no underwriting/CRM data loaded — flag as "coming soon").

### 7. Finance / Executive — brand filter mostly N/A (org-wide)
- Revenue vs budget by month, revenue mix (Foundation/Individual/Underwriting), surplus,
  cash, expenses, % to annual budget, MRR [`finance.fact_kpi_monthly` — Feb–Apr 2026 loaded].

---

## Editorial layer (plain-English — explain the data, don't just show it)

The audience is the **board + leadership**, not analysts. Every metric carries an explanation
of *what it is and why it matters*, in the **Radio Milwaukee voice** (warm, civic, plain,
**sentence case**, contractions, Oxford comma, no hype words, no jargon, no emoji — see the
brand README's Content Fundamentals).

**How to deliver it (3 levels):**
1. **Chart deck** — one sentence under each chart/section title saying what it shows + why it matters.
2. **Metric tooltip** — a small `ⓘ` on each KPI/metric with the plain-English definition + the target if there is one.
3. **Caveat notes** — the existing italic footnotes for coverage limits ("P6+ only", "Feb–Apr finance").

Implement as a `deck` + `info` prop on `<ChartCard>`/`<Kpi>` and a shared `glossary.js`. Keep a
single source of truth so the same definition feeds tooltips AND (later) the AI chat.

**Plain-English glossary (RM voice — reuse verbatim):**

| Term | What it means |
|---|---|
| **AQH Share** | Of all the radio listening happening in metro Milwaukee in an average quarter-hour, the slice tuned to us. Higher is better; we're ranked against every station in the market. |
| **AQH Persons** | The average number of people listening in any given 15-minute window. |
| **Cume / Weekly Cume** | How many *different* people tuned in at least once during the week — our reach, not our depth. |
| **TSL** | Time spent listening — how long the average listener stays with us. Rising TSL means the programming is holding people. |
| **TLH** | Total listening hours — every hour of streaming, added up across all listeners. Our total streaming volume. |
| **AAS** | Average active sessions — how many streams are playing at once, on average. A live read on stream audience. |
| **Sustainer MRR** | Monthly recurring revenue from sustaining members — the income we can count on every month. Target $50K. |
| **Donor retention** | Of the supporters who gave before this year, the share who gave again. Are we keeping the people we earn? |
| **Active donor** | Someone who's given at least once in the last 12 months. |
| **Reach** | The number of *unique* people who saw our posts. |
| **Impressions** | Total times our content was shown — one person can count several times. |
| **Open / click rate** | The share of email recipients who opened it / clicked a link inside. |
| **Organic traffic** | Visitors who found us through search or unpaid links, not ads. |

**Section intros (one sentence each, RM voice):**
- **Program Director** — "Who's listening, when, and whether they're staying — across the broadcast signal and the streams."
- **Development** — "The health of our supporter base: how many give, whether they come back, and what they're worth over time."
- **Digital** — "How people find and move through our sites, and the content that brings them in."
- **Social** — "How each brand's audience is growing and engaging, page by page."
- **Underwriting** — "The audience we can offer sponsors — by daypart, device, and demo."
- **Finance / Executive** — "The money: what we've raised against budget, where it comes from, and what's left over."

**Example chart decks (RM voice):**
- Revenue vs. Budget — "Where we stand against the fiscal-year plan, month by month."
- Donor retention — "We aim to keep 45–50% of last year's donors. Here's how we're tracking."
- AQH Share trend — "Our share of Milwaukee's radio listening over the last 14 surveys."
- Sustainer MRR — "Predictable monthly giving from sustaining members, against the $50K goal."

## Architecture changes to make

1. **API (`service/dashboard_api.py`):** add `station_code`/`brand` to every brand-attributable
   query so the frontend can filter client-side. Add the new role queries (daypart heatmap,
   traffic sources, top posts, donor geo/LTV tiers, conversion events, app engagement). Keep one
   `/api/dashboard` payload, or split into `/api/dashboard/<role>` if it gets large.
2. **Frontend:** add a `<BrandFilter>` in the header (global state, default "All"); pass to each
   tab; each widget filters its data by brand or renders an "Org-wide" badge. Reorganize
   `tabs.jsx` into role tabs (Executive, Program Director, Development, Digital, Social,
   Underwriting, Finance). Add a reusable `<BrandBadge>` and a "no data for this brand" empty state.
3. **`dim.brand_channels`:** verify populated; it's the source of truth for handle/property/list →
   station_code. If empty, seed it (see `CLAUDE.md` Meta/GA channel-mapping notes).

## Known polish items (from browser QA)

- **Revenue Trend line is compressed by one spike** (~early 2024) — verify it's a real large gift
  (not a double-count), then cap/annotate the axis or switch to YoY bars.
- **Overview Nielsen bar rendered empty in one capture** — verify the vertical `<BarChart>` renders
  (it works on the Nielsen tab); may be a ResponsiveContainer timing thing.
- Mailchimp campaign labels truncate at ~12 chars; FB-followers chart is near-flat (show net-new
  instead). Recharts bundle >500kB — consider code-splitting per tab.

## Build sequence (suggested)

1. Add the **brand filter** infra (API brand-tagging + frontend selector + badges) — unlocks everything.
2. Build the **Program Director** + **Underwriting** tabs first (richest streaming/Nielsen data, brand
   filter shines). Then **Digital** + **Social** (GA/Meta stg). Then **Development** (Funraise depth).
3. Fix the polish items. Then **deploy to Vercel**.
4. (Separately) the **AI chat** feature + the **semantic model** (`semantic/rm_metrics.yml`) — the
   semantic layer makes both the role metrics and the chat consistent.

## Key facts for whoever continues
- Project (Neon): `morning-frost-30675590` / `neondb`. API + app both committed (`4ab7c86`).
- stg_ vs fact_ rule: GA/Meta/Email data is in `stg_*`; their clean `fact_*` are EMPTY.
- Brands: RM88=88Nine, HYFIN, RM414=414 Music, RLR=Rhythm Lab, RMORG=Radio Milwaukee flagship.
  Nielsen only measures RM88 + HYFIN. RLR streaming starts 2025-11-16.
- The Hex `RM Executive Dashboard` project (019efffc-…) is a parallel build with the same data
  + a branded Plotly theme — either continue there OR (recommended) focus the standalone app.
