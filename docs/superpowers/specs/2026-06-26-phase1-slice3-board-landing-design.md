# Phase 1 Slice 3 — Board / Executive landing view — Design

> Companion to the Phase-1 epic (MOO-176). Upgrades the existing **Overview** tab into the
> Board/Executive landing — an org-wide, plain-English health scorecard for non-analyst directors.
> Plan: `docs/superpowers/plans/2026-06-26-phase1-slice3-board-landing.md`.

## Goal

Give board members and leadership a single landing tab that answers *"How is the organization
doing?"* at a glance — reach, revenue vs budget, donor health, and market position — in plain
English, reusing the existing payload and the slice-1/2 editorial layer. No analyst skills required.

## Decisions (settled in brainstorming)

- **Upgrade Overview, don't add a tab.** The roadmap keeps a single "Executive Overview" as the
  landing; MOO-176 calls it the Board view. We rebuild the existing `Overview` tab fn into the
  Board scorecard and keep it as the default first tab. (This also closes the QA gap that Overview
  was the one tab lacking the ⓘ/deck editorial treatment.)
- **Form = plain-English scorecard**, not auto-written prose. Grouped big-number cards, each with a
  direction arrow vs prior period and a one-line plain-English deck. True generated narrative is
  deferred to the Phase-2 AI assistant.
- **Mostly frontend.** Almost everything is already in the `/api/dashboard` payload. The only new
  backend is a Nielsen **CUME** query (broadcast weekly reach), which the payload doesn't expose yet.
- **Brand filter still works** where cards are per-station (reach, market position); revenue/donor
  cards are org-wide and carry `OrgWideBadge` (the filter is a no-op on them). Default brand = ALL.

## Card groups

**1. Reach — "the people we touch" (cume-led).** Separate cards under one header, with an explicit
caveat that the sources can't be de-duplicated (no dishonest single "total reach" number):
- **Broadcast weekly cume** (Nielsen `Avg Weekly Cume Persons`, per station) — NEW `nielsen_cume`.
  The most intuitive board reach number (e.g. RM88 ≈ 75,600/week, HYFIN ≈ 18,900).
- **Streaming cume** (`station_comparison` / latest `tlh_by_station`).
- **Social following** (`social_followers` count).
- **Web sessions** (`web_sessions_weekly`, latest).
- Existing `combined_digital_reach` as the digital roll-up.

**2. Revenue vs budget.** `revenue_vs_budget` (YTD actual vs budget + variance %), `revenue_mix`
donut. Direction = actual-vs-budget (finance history is only ~3 months, so no time trend).
Org-wide badge.

**3. Donor health.** Active donors, sustainer MRR vs $50K goal, donor retention % (from
`exec_kpis` / `dev_kpis` / `sustainer_tracker`), each with a YoY/prior-period direction arrow
derived from the donor trend arrays. Org-wide badge.

**4. Market position.** Nielsen **AQH share** + market **rank** per station (`nielsen_share`) and an
AQH-persons trend sparkline (`nielsen_aqh_trend`). The competitive/intensity story — distinct from
the reach (cume) story above.

## Direction arrows

Computed **client-side** from monthly trend arrays already in the payload (`tlh_by_station`,
`revenue_trend`, `nielsen_aqh_trend`, `nielsen_cume_trend`, donor trends): latest vs same period
prior year, or vs prior period where a year of history isn't available. A card **omits** the arrow
when history is too thin rather than faking a delta.

## Backend additions (small)

Two new `dashboard_api.py` payload keys, mirroring the existing Nielsen queries
(`section='Estimates'`, latest-period pattern):
- `nielsen_cume` — latest `Avg Weekly Cume Persons` per station (mirrors `nielsen_share`).
- `nielsen_cume_trend` — `Avg Weekly Cume Persons` over time per station (mirrors `nielsen_aqh_trend`),
  for the reach sparkline + direction arrow.

No registry change. No new dependency.

## Editorial

Extend `glossary.js`: `SECTION_INTRO.board`; `GLOSSARY` entries distinguishing **cume** (reach —
different people) from **AQH** (intensity — average quarter-hour) and `market_rank`; `DECK` entries
for the four group headers.

## Testing

- Shape tests for `nielsen_cume` / `nielsen_cume_trend` (present, per-station, numeric).
- Full backend suite green; frontend `npm run build` clean.
- Browser QA: scorecard renders all four groups with real numbers; direction arrows where history
  exists and omitted where thin; brand filter narrows per-station reach/market cards; revenue/donor
  cards badged org-wide; cume vs AQH clearly distinct; no console errors.

## Out of scope (slice 3)

- Auto-generated prose narrative (Phase-2 assistant).
- A single de-duplicated "total reach" number (methodologically impossible across sources).
- Production deploy (gated on user).

## Data notes (verified 2026-06-26)

- `Avg Weekly Cume Persons` is in `section='Estimates'`, one row per station per period; latest MAY26:
  RM88 75,600, HYFIN 18,900.
- Existing Nielsen queries filter only `section='Estimates'` + metric (current data is P6+ / M-Su,
  so one row per station/period). As more demos/dayparts load, those queries — and the new cume
  ones — may need a demo/daypart filter; note for a later hardening pass (not this slice).
- Finance history is ~3 months (Feb–Apr 2026), so revenue is shown vs budget, not as a time trend.

## Tracking

Branched off `main` (slices 1+2 merged). New MOO child issue under the Phase-1 epic (MOO-176).
