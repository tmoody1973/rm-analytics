# Phase 1 Slice 3 — Board / Executive landing view Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-06-26-phase1-slice3-board-landing-design.md`.

**Goal:** Rebuild the existing `Overview` tab into the Board/Executive landing — a plain-English health scorecard (Reach · Revenue vs budget · Donor health · Market position) for non-analyst directors — reusing the existing payload + editorial layer, plus a new Nielsen weekly-cume reach number.

**Architecture:** Vite + React frontend (single `/api/dashboard` fetch, client-side filter). FastAPI `dashboard_api.py` bulk payload. This slice is mostly frontend; the only backend is two Nielsen cume queries.

**Tech Stack:** Python 3.12, psycopg3, FastAPI, pytest; React 18, Recharts, Vite. No new dependencies.

## Global Constraints

- **Upgrade Overview in place** — rebuild the existing `Overview(d, f)` tab fn in `dashboard/src/tabs.jsx`; keep it the default first tab and its `TABS` key `Overview`. Do not add a 7th tab; do not rename the key (the design's "Board" is the audience name for this landing).
- **Form = scorecard** — grouped big-number cards with a direction arrow + one-line deck. No auto-generated prose.
- **Reuse existing payload keys** (verified shapes below). Only NEW backend = `nielsen_cume` + `nielsen_cume_trend`.
- **Brand filter:** per-station cards (reach, market position) honor `f.brand` via `fromStation`; revenue/donor cards are org-wide with `OrgWideBadge`. Default brand ALL.
- **Reach is cume-led and NOT summed across sources** — show separate cards with a caveat (sources can't be de-duplicated).
- **Editorial voice:** sentence case, contractions, no hype/jargon/emoji. Extend `glossary.js`.
- No new npm dependency, no router, no new data-fetch path.

## Verified payload field shapes (2026-06-26)

```
station_comparison[4]   : station_code, tlh, aas, cume          # streaming cume per station
nielsen_share[2]        : station_code, aqh_share, rank
nielsen_aqh_trend[28]   : station_code, period_label, period_date, aqh_persons
combined_digital_reach  : web_sessions_30d, social_reach_30d, emails_sent_30d
social_followers[2721]  : date, account, followers              # need LATEST per account
web_sessions_weekly[106]: property, week, sessions
revenue_vs_budget[3]    : month, revenue_ytd, budget_ytd        # latest row = current YTD
revenue_mix[3]          : month, underwriting, individual, foundation
header[1]               : revenue_ytd, cash_balance, total_donors, surplus_ytd, pct_to_budget, fb_followers, email_subscribers
exec_kpis[1]            : active_donors, active_sustainers, sustainer_mrr, revenue_12mo
dev_kpis{}              : sustainer_share, donor_retention_pct, avg_gift, avg_gift_mean, new_donors, lapsed_donors
sustainer_tracker[1]    : mrr, active_plans, target
tlh_by_station[94]      : station_code, month, tlh, aas, cume    # monthly history for deltas
```

---

### Task 1: Editorial — board glossary, intro, decks

**Files:** Modify `dashboard/src/glossary.js`.

- [ ] **Step 1:** Add `SECTION_INTRO.board` (RM voice): "How the whole organization is doing — the people we reach, the money against plan, the health of our giving, and where we stand in the market. Org-wide; some cards narrow by brand."
- [ ] **Step 2:** Add `GLOSSARY` entries (reuse existing `aqh_share`, `cume`, `tsl`, `sustainer_mrr`, `donor_retention`):
  - `weekly_cume` — "How many different people tune in to our broadcast signal at least once in a week — our on-air reach, not how long they stay."
  - `aqh_vs_cume` — "Cume counts different people reached; AQH is how many are listening in an average quarter-hour. Reach versus intensity."
  - `market_rank` — "Where our AQH share ranks against every station Nielsen measures in metro Milwaukee."
  - `pct_to_budget` — "How our revenue so far this year compares to the plan — over 100% is ahead of budget."
- [ ] **Step 3:** Add `DECK` entries: `board_reach` ("The people we touch across broadcast, streaming, social, and web. Each source is counted separately — we can't de-duplicate a person across them."), `board_revenue` ("Where revenue stands against the fiscal-year plan."), `board_donors` ("The health of our supporter base at a glance."), `board_market` ("Our standing in metro Milwaukee's radio market.").
- [ ] **Step 4:** `cd dashboard && npm run build` exits 0. **Commit:** `feat(dashboard): board landing editorial (glossary/intro/decks)`.

---

### Task 2: Backend — Nielsen cume queries

**Files:** Modify `service/dashboard_api.py` (`QUERIES`); Test `tests/test_dashboard_board_queries.py` (create).

**Interfaces:** Produces payload keys `nielsen_cume`, `nielsen_cume_trend`.

- [ ] **Step 1: Read** the existing `nielsen_share` and `nielsen_aqh_trend` entries in `QUERIES` and mirror them exactly (same `section='Estimates'` filter, same latest-period subquery pattern, same serialization).

- [ ] **Step 2: Add the two queries** (verified against live Neon — metric label is exactly `Avg Weekly Cume Persons`, which lives in `section='Estimates'`, one row per station per period):

```sql
-- nielsen_cume: latest weekly broadcast cume (unique weekly listeners) per station.
SELECT station_code, value_numeric AS cume
FROM nielsen.fact_vital_signs
WHERE section='Estimates' AND metric='Avg Weekly Cume Persons'
  AND period_date=(SELECT max(period_date) FROM nielsen.fact_vital_signs WHERE metric='Avg Weekly Cume Persons')
ORDER BY cume DESC;
```

```sql
-- nielsen_cume_trend: weekly cume over time per station (for the reach sparkline + direction arrow).
SELECT station_code, period_label, period_date::text AS period_date, value_numeric AS cume
FROM nielsen.fact_vital_signs
WHERE section='Estimates' AND metric='Avg Weekly Cume Persons' AND period_date IS NOT NULL
ORDER BY period_date, station_code;
```

Verified latest values (MAY26): RM88 = 75,600, HYFIN = 18,900.

- [ ] **Step 3: Write `tests/test_dashboard_board_queries.py`** — real assertions: both keys present; `nielsen_cume` non-empty with fields `{station_code, cume}` and numeric cume; `nielsen_cume_trend` rows have `{station_code, period_label, period_date, cume}`.

- [ ] **Step 4: Run** `source .venv/bin/activate && python -m pytest tests/test_dashboard_board_queries.py -v` pass; full suite `python -m pytest -q` green.
- [ ] **Step 5: Commit** `feat(api): nielsen weekly-cume queries for board reach`.

---

### Task 3: Rebuild the Overview tab into the Board scorecard

**Files:** Modify `dashboard/src/tabs.jsx` (`Overview` fn); optionally add a small `ScoreCard`/`Stat` + `Delta` helper to `components.jsx` if no existing one fits.

Reuse `Kpi`, `ChartCard` (deck/info), `Lines`, `sumBy`, `filterByBrand`, `fromStation`, `money`/`num` formatters, `OrgWideBadge`, `SectionTitle`. **READ the current `Overview` fn and a finished role tab first** to match patterns and reuse helpers; invent nothing new.

- [ ] **Step 1: Section intro** = `SECTION_INTRO.board`. Keep `Overview` as the default first tab.
- [ ] **Step 2: Build a direction-arrow helper** — given a monthly trend array + a value key, return `{delta, dir}` comparing the latest point to the same period prior year (fallback: prior available point); return null when history is too thin. Render as ▲/▼ + the change; OMIT when null. (Pure client-side from existing trend arrays — no backend.)
- [ ] **Step 3: Reach group** (`ChartCard`/section deck `DECK.board_reach`; per-station cards honor `f.brand` via `fromStation`):
  - Broadcast weekly cume from `nielsen_cume` (info `GLOSSARY.weekly_cume`), direction from `nielsen_cume_trend`. Only where `brandHasChannel(f.brand,'nielsen')`.
  - Streaming cume from `station_comparison` (info `GLOSSARY.cume`), direction from `tlh_by_station` (cume).
  - Social following: latest `followers` per `social_followers.account` (sum for the brand/all).
  - Web sessions: latest from `web_sessions_weekly`.
  - Caveat line: sources are counted separately and can't be de-duplicated.
- [ ] **Step 4: Revenue vs budget group** (deck `DECK.board_revenue`; `OrgWideBadge`): from `revenue_vs_budget` latest row — revenue YTD, budget YTD, variance % (or reuse `header.pct_to_budget`, info `GLOSSARY.pct_to_budget`); `revenue_mix` donut. Use `header.surplus_ytd`/`cash_balance` as supporting board numbers.
- [ ] **Step 5: Donor health group** (deck `DECK.board_donors`; `OrgWideBadge`): active donors (`exec_kpis`), sustainer MRR vs `sustainer_tracker.target` ($50K), retention % (`dev_kpis.donor_retention_pct`, info `GLOSSARY.donor_retention`). Direction arrows from donor trends where available.
- [ ] **Step 6: Market position group** (deck `DECK.board_market`; per-station, honor brand): Nielsen AQH share + rank from `nielsen_share` (info `GLOSSARY.aqh_share`; `market_rank`), and an AQH-persons sparkline from `nielsen_aqh_trend`. Make the cume-vs-AQH distinction explicit (info `GLOSSARY.aqh_vs_cume`).
- [ ] **Step 7: Build + browser smoke** — `npm run build` exits 0; preview the Overview/Board tab; switch brand (per-station reach/market cards narrow; revenue/donor stay org-wide badged); confirm decks + ⓘ tooltips; no console errors. **Commit** `feat(dashboard): rebuild Overview into Board/Executive scorecard`.

---

### Task 4: QA + deploy (gated)

- [ ] **Step 1: Full suite** `python -m pytest -q` green; **frontend build** clean.
- [ ] **Step 2: Browser QA** — all four groups render real numbers; broadcast weekly cume shows (RM88 ~75.6K) and is clearly distinct from AQH share; direction arrows appear where history exists and are omitted where thin; brand filter narrows per-station cards only; revenue/donor org-wide badged; no console errors. Capture notes.
- [ ] **Step 3: DEPLOY — GATED ON USER** (do not run without explicit go-ahead): `flyctl deploy --app rm-data-loader`; verify `/health` 200 and `/api/dashboard` returns `nielsen_cume`.
- [ ] **Step 4: Commit** any QA fixes.

---

## Notes for the controller
- Branched off `main` (slices 1+2 merged) — not stacked. Standard PR to `main`.
- All new SQL is static (no user input) and mirrors the existing Nielsen query filters.
- Existing Nielsen queries (and these new ones) filter only `section='Estimates'` + metric; current data is P6+ / M-Su so one row per station/period. If more demos/dayparts load later, add a demo/daypart filter — note for a hardening pass, out of scope here.
- Run the final whole-branch review on the most capable model — prior slices' final reviews caught payload-key/field mismatches the per-task reviews missed; scrutinize the Task-3 frontend reads against the verified field shapes above.
- After merge: update `docs/dashboard-roadmap.md` (Board done) + `CLAUDE.md`; this likely completes the MOO-176 epic's tab set (Board, PD, Underwriting, Development, Digital, Social, Finance/Exec) — verify and close MOO-176.
