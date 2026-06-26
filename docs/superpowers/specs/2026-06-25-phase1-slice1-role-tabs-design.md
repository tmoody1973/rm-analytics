# Phase 1 (MOO-176) — Slice 1: Role tabs + editorial layer

> Design spec. Slice 1 of a decomposed MOO-176. Scope agreed with Tarik 2026-06-25.

## Goal

Convert the `dashboard/` app from **source-based** tabs to **role-based** tabs, build the two
richest role tabs (**Program Director**, **Underwriting**), and add a **plain-English editorial
layer** (deck sentences + ⓘ definitions + a shared glossary in Radio Milwaukee voice). Ship a
coherent, non-regressing dashboard that the board and leadership can read without an analyst.

## Locked decisions (2026-06-25)

1. **Phased** — MOO-176 is decomposed; this is **slice 1**. Slices 2+ cover Board narrative,
   Development depth, and the Nielsen/Web/Social deep-dives.
2. **Hybrid data architecture, server-side** — `service/dashboard_api.py` computes headline KPIs by
   calling the metric registry's `run_metric()`, so the dashboard and the (Phase-2) assistant share
   one definition. Long-tail widgets stay bespoke SQL in the same bulk `/api/dashboard` payload. The
   frontend keeps its single fetch + client-side brand/date filtering — no new frontend data plumbing.
3. **Board + Development hidden** until their slice — not shown as placeholders.
4. **Daypart depth = full hour × day grid** (AAS/CUME by hour-of-day × day-of-week) plus the
   5-daypart roll-up, both from `wms.fact_hourly_listening`.

## What already exists (leverage, do not rebuild)

The brand-filter stack is **fully built and in production**: `FilterBar` (filters.jsx), `brand`+`range`
state in `App.jsx`, `filterByBrand`/`filterByDate`/`rangeCutoff` and all five `from*` mappers
(`fromStation`, `fromGaProperty`, `fromFbAccount`, `fromIgAccount`, `fromEmailList`),
`brandHasChannel`, and the `NoBrandData`/`BrandBadge`/`OrgWideBadge` components. Slice 1 reuses these
verbatim. `Kpi`/`ChartCard` (components.jsx) have **no** `deck`/`info` props yet — clean addition points.

## Tab restructure

`TABS` (an ordered object in `tabs.jsx`, keys drive the nav in `App.jsx`) is reorganized. Slice 1 ships
**6 visible tabs**; the standalone Nielsen + Triton tabs are **folded into** PD/Underwriting and removed.

| Slice-1 tab (in order) | Source | Notes |
|---|---|---|
| **Overview** | existing `Overview` | landing; org-wide; no filter bar (unchanged) |
| **Program Director** | NEW — existing Triton + Nielsen widgets + new daypart/grid/TSL/top-content | brand filter essential |
| **Underwriting** | NEW — new AAS-by-daypart + existing `platform_breakdown` + Nielsen + underwriting revenue | brand filter essential; pipeline = "coming soon" note |
| **Digital** | existing `DigitalReach` (relabeled) | + decks/glossary |
| **Social** | existing `Social` (relabeled) | + decks/glossary |
| **Finance / Exec** | existing `Financial` (relabeled) | org-wide badge; + decks/glossary |

Removed from nav: standalone `Nielsen`, `Triton Streaming`, `Mailchimp`. Nielsen→PD/Underwriting;
Triton→PD; **Mailchimp email content moves under Social** (roadmap allows Digital or Social — choose
Social to keep Digital focused on web). Board + Development: not in nav this slice.

## Editorial layer

- **`components.jsx`** — add optional `deck?: string` and `info?: string` to both `Kpi` and `ChartCard`.
  - `ChartCard({ title, children, className, deck, info })` — render `deck` as a one-line sentence under
    the title; render `info` as a hoverable/tappable `ⓘ` next to the title showing the definition.
  - `Kpi({ label, value, note, accent, info })` — `ⓘ` next to the label with the definition (+ target).
  - Tooltip is CSS-only (no new dependency): a `<span class="info" title={info}>ⓘ</span>` plus a styled
    `:hover` popover in `app.css`. Accessible: `tabindex=0` + `aria-label`.
- **`dashboard/src/glossary.js`** (new) — `export const GLOSSARY = { aqh_share: "...", cume: "...", tsl:
  "...", tlh: "...", aas: "...", sustainer_mrr: "...", donor_retention: "...", active_donor: "...",
  reach: "...", impressions: "...", open_click_rate: "...", organic_traffic: "..." }` using the
  roadmap's RM-voice text **verbatim**, plus `SECTION_INTRO = { program_director: "...", underwriting:
  "...", digital: "...", social: "...", finance: "..." }` and a `DECK = { revenue_vs_budget: "...",
  donor_retention: "...", aqh_share_trend: "...", sustainer_mrr: "..." }` map. Single source of truth —
  the same strings seed the Phase-2 assistant prompt.
- RM voice rules: sentence case, contractions, Oxford comma, no hype words, no jargon, no emoji.

## Data architecture (server-side hybrid)

`service/dashboard_api.py`:
- **Headline KPIs via the registry.** For the KPI strip and the role-tab headline numbers that the
  assistant will also cite, call `metrics.registry.run_metric(id, brand=None, period=..., group_by=...)`
  server-side and place the result in the payload, instead of a bespoke duplicate query. Concretely the
  registry already backs: `streaming_tlh`, `avg_active_sessions` (brand/period/station-aware),
  `sustainer_mrr`, `active_donors`, `active_sustainers`, `total_donors`, `revenue`. Replace the existing
  hand-written equivalents in `dashboard_api` with `run_metric` calls where they overlap, so there is one
  definition. (Net: `dashboard_api` imports from `metrics`, mirroring how `service/metric_api.py` already
  does — and the Dockerfile now ships `metrics/`.)
- **New long-tail queries** (bespoke SQL, brand-tagged with `station_code` so the frontend filters
  client-side):
  1. `daypart_aas` — AAS by **daypart × station** from `wms.fact_hourly_listening`, bucketing `hour`
     into the 5 standard dayparts (per `dim.dayparts`). Rows: `{station_code, daypart, aas}`.
  2. `hourly_grid` — AAS (and CUME) by **hour-of-day × day-of-week × station** from
     `wms.fact_hourly_listening`. Rows: `{station_code, dow, hour, aas, cume}`.
  3. `tsl_trend` — average `tsl_minutes` by month × station from the hourly/daily facts. Rows:
     `{station_code, month, tsl_minutes}`.
  4. `top_web_content` — top pages by views + engagement time from `ga.stg_pages_daily`, tagged with the
     GA property (→ brand via `fromGaProperty`). Rows: `{property, page_path, views, avg_engagement_s}`.
  - Underwriting revenue: reuse `revenue_vs_budget`/`revenue_mix` (org-wide, `finance.fact_kpi_monthly`);
    if a clean "underwriting" category split isn't present, show org revenue-vs-budget with an
    "Org-wide" badge and an underwriting-pipeline "coming soon" note (no CRM data loaded).
- All new SQL parameterized; respects the project rule **stg_ for GA/Meta/Email, fact_ for
  streaming/nielsen/finance**.

## Frontend changes

- `tabs.jsx` — rewrite `TABS` to the 6-tab role set above. Add `ProgramDirector(d, f)` and
  `Underwriting(d, f)` render fns. Reuse `Lines`, `pivot`, `sumBy`, `filterByBrand`, `NoBrandData`.
  New widgets: a daypart heatmap/bar and an hour×day grid (Recharts; no new dep) — extract a small
  `Heatmap`/`Grid` helper in `components.jsx` if it clarifies.
- `App.jsx` — nav iterates the new `TABS` keys; the `tab !== 'Overview'` filter-bar guard stays.
- `glossary.js` — new; imported by `tabs.jsx`/`components.jsx`.
- No router, no new fetch path, no new dependency.

## Non-goals (deferred)

Board landing narrative; Development donor-depth (geo/LTV/retention); the Nielsen/Web/Social deep-dives;
paid social (`meta_ads`); app analytics; underwriting pipeline/CRM; any Phase-2 assistant work; server-
side brand filtering. These are slice 2+ / other issues.

## Testing & verification

- **Python** (`tests/`): each new `dashboard_api` query returns the documented shape and carries its
  `station_code`/`property` discriminator; registry-backed KPIs equal a direct `run_metric` call (no
  drift between the bulk payload and the registry). Full suite stays green.
- **Browser QA** (the issue's checklist): each of the 6 tabs renders real data; PD daypart grid + heatmap
  populate; decks + ⓘ tooltips show the glossary text; brand filter narrows correctly and org-wide
  widgets badge; "not measured for this brand" empty states where a brand lacks a channel; no console errors.
- Deploy: API to Fly (`rm-data-loader`), dashboard build verified (Vercel/`npm run preview`).

## Linear decomposition

- **MOO-176** becomes the parent/epic for Phase 1. Slice 1 (this spec) is the first child issue; create
  follow-up child issues for Slice 2 (Board + Development) and Slice 3 (Nielsen/Web/Social deep-dives).
  Done via the linear-build step after the plan.
