# Phase 1 Slice 1 — Role tabs + editorial layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-06-25-phase1-slice1-role-tabs-design.md`.

**Goal:** Convert the `dashboard/` app to role-based tabs, build the Program Director + Underwriting tabs (incl. a daypart heatmap and hour×day programming grid), and add a plain-English editorial layer (deck/info props + RM-voice glossary), with assistant-citable KPIs sourced from the metric registry.

**Architecture:** Vite + React frontend (single `/api/dashboard` fetch, client-side brand/date filter — already built). FastAPI `dashboard_api.py` returns one bulk payload; headline KPIs come from `metrics.registry.run_metric`, long-tail widgets from bespoke SQL. New streaming queries read `wms.fact_hourly_listening`; web content from `ga.stg_pages_daily`.

**Tech Stack:** Python 3.12, psycopg3, FastAPI, pytest; React 18, Recharts, Vite. No new dependencies.

## Global Constraints

- **stg_ vs fact_:** GA/Meta/Email read `stg_*`; streaming/nielsen/finance read `fact_*`. Never the empty GA/Meta `fact_*`.
- **Brand keys:** `ALL, RM, HYFIN, RM414, RLR, GWML`. `RM` covers station_codes `RM88`+`RMORG`. Use the existing `from*` mappers in `dashboard/src/brands.js` — do not invent new ones.
- **Dayparts** (`dim.dayparts`, half-open `[start_hour, end_hour)`): Overnight 0–5, Morning 5–10, Midday 10–15, Afternoon 15–19, Evening 19–24.
- **RM editorial voice:** sentence case, contractions, Oxford comma, no hype words, no jargon, no emoji.
- **No new frontend data path:** keep the single `fetchDashboard()` + client-side filtering. No router, no new npm dep.
- **Visible tabs this slice (in order):** Overview, Program Director, Underwriting, Digital, Social, Finance / Exec. Board + Development are NOT added. Standalone Nielsen + Triton + Mailchimp tabs are removed (folded in).
- All new SQL parameterized where it takes input; brand-attributable rows must carry `station_code` or `property`.

---

### Task 1: Editorial foundation — glossary + deck/info props

**Files:**
- Create: `dashboard/src/glossary.js`
- Modify: `dashboard/src/components.jsx` (`Kpi`, `ChartCard`)
- Modify: `dashboard/src/app.css` (info tooltip + deck styles)

**Interfaces:**
- Produces: `GLOSSARY`, `SECTION_INTRO`, `DECK` objects; `Kpi` gains `info?`, `ChartCard` gains `deck?` + `info?`.

- [ ] **Step 1: Create `dashboard/src/glossary.js`** (RM-voice text verbatim from `docs/dashboard-roadmap.md`):

```js
// Single source of truth for plain-English definitions (RM voice). The same
// strings feed the ⓘ tooltips now and the Phase-2 assistant prompt later.
export const GLOSSARY = {
  aqh_share: "Of all the radio listening happening in metro Milwaukee in an average quarter-hour, the slice tuned to us. Higher is better; we're ranked against every station in the market.",
  aqh_persons: "The average number of people listening in any given 15-minute window.",
  cume: "How many different people tuned in at least once during the week — our reach, not our depth.",
  tsl: "Time spent listening — how long the average listener stays with us. Rising TSL means the programming is holding people.",
  tlh: "Total listening hours — every hour of streaming, added up across all listeners. Our total streaming volume.",
  aas: "Average active sessions — how many streams are playing at once, on average. A live read on stream audience.",
  sustainer_mrr: "Monthly recurring revenue from sustaining members — the income we can count on every month. Target $50K.",
  donor_retention: "Of the supporters who gave before this year, the share who gave again. Are we keeping the people we earn?",
  active_donor: "Someone who's given at least once in the last 12 months.",
  reach: "The number of unique people who saw our posts.",
  impressions: "Total times our content was shown — one person can count several times.",
  open_click_rate: "The share of email recipients who opened it, or clicked a link inside.",
  organic_traffic: "Visitors who found us through search or unpaid links, not ads.",
};

export const SECTION_INTRO = {
  program_director: "Who's listening, when, and whether they're staying — across the broadcast signal and the streams.",
  underwriting: "The audience we can offer sponsors — by daypart, device, and demo.",
  digital: "How people find and move through our sites, and the content that brings them in.",
  social: "How each brand's audience is growing and engaging, page by page.",
  finance: "The money: what we've raised against budget, where it comes from, and what's left over.",
};

export const DECK = {
  revenue_vs_budget: "Where we stand against the fiscal-year plan, month by month.",
  donor_retention: "We aim to keep 45–50% of last year's donors. Here's how we're tracking.",
  aqh_share_trend: "Our share of Milwaukee's radio listening over the last 14 surveys.",
  sustainer_mrr: "Predictable monthly giving from sustaining members, against the $50K goal.",
  daypart_aas: "When our streams are busiest — average concurrent listeners through the day.",
  hourly_grid: "The week at a glance: where listening peaks by hour and day.",
  tsl_trend: "How long the average streaming listener stays with us, month over month.",
  top_web_content: "The stories pulling people to our sites.",
  device_split: "What our streaming audience listens on — useful for ad targeting.",
};
```

- [ ] **Step 2: Add `info`/`deck` props to `Kpi` and `ChartCard`** in `dashboard/src/components.jsx`.

Read the current `Kpi` and `ChartCard` first. Change their signatures and render to:

```jsx
export function Kpi({ label, value, note, accent, info }) {
  return (
    <div className="kpi">
      <div className="kpi-label">
        {label}
        {info ? <InfoDot text={info} /> : null}
      </div>
      <div className={accent ? 'kpi-value accent' : 'kpi-value'}>{value}</div>
      {note ? <div className="kpi-note">{note}</div> : null}
    </div>
  );
}

export function ChartCard({ title, children, className = '', deck, info }) {
  return (
    <div className={`card ${className}`}>
      <div className="card-head">
        <h3>{title}{info ? <InfoDot text={info} /> : null}</h3>
        {deck ? <p className="deck">{deck}</p> : null}
      </div>
      {children}
    </div>
  );
}

// Small accessible info tooltip — CSS-only popover, no dependency.
function InfoDot({ text }) {
  return (
    <span className="info-dot" tabIndex={0} role="img" aria-label={text}>
      ⓘ<span className="info-pop">{text}</span>
    </span>
  );
}
```

Keep the existing class names the current markup already uses (verify against the file — if the current `Kpi` uses different class names like `value`/`label`, preserve them; only ADD the `info`/`deck` rendering). Do not change `HeaderKpi`.

- [ ] **Step 3: Add styles** to `dashboard/src/app.css`:

```css
.deck { margin: 2px 0 10px; font-size: 0.85rem; color: var(--muted, #6b6b6b); line-height: 1.4; }
.info-dot { position: relative; cursor: help; margin-left: 6px; font-size: 0.8em; color: var(--muted, #888); }
.info-dot:hover .info-pop, .info-dot:focus .info-pop { display: block; }
.info-pop { display: none; position: absolute; left: 0; top: 1.4em; z-index: 20; width: 260px;
  background: #1a1a1a; color: #f5f5f0; padding: 8px 10px; border-radius: 8px; font-size: 0.8rem;
  line-height: 1.45; box-shadow: 0 4px 14px rgba(0,0,0,.25); font-weight: 400; }
```

- [ ] **Step 4: Verify build** — `cd dashboard && npm run build` exits 0; no unused-import or syntax errors.

- [ ] **Step 5: Commit** — `git add dashboard/src/glossary.js dashboard/src/components.jsx dashboard/src/app.css && git commit -m "feat(dashboard): editorial layer — glossary + deck/info props"`

---

### Task 2: New streaming + web queries in the API

**Files:**
- Modify: `service/dashboard_api.py` (add to the `QUERIES` dict)
- Test: `tests/test_dashboard_api_queries.py` (create)

**Interfaces:**
- Produces payload keys `daypart_aas`, `hourly_grid`, `tsl_trend`, `top_web_content`.

- [ ] **Step 1: Read `service/dashboard_api.py`** to learn the exact `QUERIES` structure (key → SQL string, and how rows are serialized). Follow that pattern exactly for the four additions below.

- [ ] **Step 2: Add the four queries.** SQL (verified against live schema):

```sql
-- daypart_aas: avg concurrent sessions by daypart × station (last 365d profile; not date-filtered)
SELECT h.station_code,
       d.daypart_id,
       d.name AS daypart,
       round(avg(h.aas), 1) AS aas
FROM wms.fact_hourly_listening h
JOIN dim.dayparts d ON h.hour >= d.start_hour AND h.hour < d.end_hour
WHERE h.date >= (current_date - interval '365 days')
GROUP BY h.station_code, d.daypart_id, d.name
ORDER BY h.station_code, d.daypart_id;
```

```sql
-- hourly_grid: avg aas + cume by hour-of-day × day-of-week × station (last 365d profile)
SELECT station_code,
       extract(dow from date)::int AS dow,   -- 0=Sun … 6=Sat
       hour,
       round(avg(aas), 1) AS aas,
       round(avg(cume))  AS cume
FROM wms.fact_hourly_listening
WHERE date >= (current_date - interval '365 days')
GROUP BY station_code, dow, hour
ORDER BY station_code, dow, hour;
```

```sql
-- tsl_trend: avg minutes per listener by month × station (date-filterable via `month`)
SELECT station_code,
       date_trunc('month', date)::date AS month,
       round(avg(tsl_minutes), 1) AS tsl_minutes
FROM wms.fact_hourly_listening
GROUP BY station_code, month
ORDER BY station_code, month;
```

```sql
-- top_web_content: top pages by views + approx engagement seconds/user (last 90d), tagged by GA property
SELECT account__property_name AS property,
       page__page_path AS page_path,
       sum(engagement__views) AS views,
       round((sum(engagement__user_engagement) / NULLIF(sum(acquisition__total_users), 0))::numeric, 1) AS avg_engagement_s
FROM ga.stg_pages_daily
WHERE report__date >= (current_date - interval '90 days')
GROUP BY property, page_path
ORDER BY views DESC
LIMIT 50;
```

- [ ] **Step 3: Write `tests/test_dashboard_api_queries.py`** — runs each query against live Neon, asserts shape + discriminator:

```python
"""Shape/discriminator checks for the slice-1 dashboard_api queries (MOO-176)."""
from __future__ import annotations
import importlib

dashboard_api = importlib.import_module("service.dashboard_api")

def _payload():
    return dashboard_api.dashboard_data()

def test_new_keys_present():
    p = _payload()
    for k in ("daypart_aas", "hourly_grid", "tsl_trend", "top_web_content"):
        assert k in p, f"missing payload key {k}"

def test_daypart_aas_shape():
    rows = _payload()["daypart_aas"]
    assert rows, "daypart_aas empty"
    r = rows[0]
    assert {"station_code", "daypart", "aas"} <= set(r)

def test_hourly_grid_shape():
    rows = _payload()["hourly_grid"]
    assert rows
    r = rows[0]
    assert {"station_code", "dow", "hour", "aas"} <= set(r)
    assert 0 <= r["dow"] <= 6 and 0 <= r["hour"] <= 23

def test_tsl_trend_brandable():
    rows = _payload()["tsl_trend"]
    assert rows and "station_code" in rows[0] and "month" in rows[0]

def test_top_web_content_brandable():
    rows = _payload()["top_web_content"]
    assert rows and "property" in rows[0] and "views" in rows[0]
```

- [ ] **Step 4: Run** — `source .venv/bin/activate && python -m pytest tests/test_dashboard_api_queries.py -v`. All pass.

- [ ] **Step 5: Commit** — `git add service/dashboard_api.py tests/test_dashboard_api_queries.py && git commit -m "feat(api): daypart/hourly-grid/tsl/top-web-content queries"`

---

### Task 3: Route headline KPIs through the metric registry

**Files:**
- Modify: `service/dashboard_api.py`
- Test: `tests/test_dashboard_registry_parity.py` (create)

**Interfaces:**
- The payload's headline KPI values (streaming TLH, AAS, sustainer MRR, active/total donors, active sustainers, revenue) are produced by `metrics.registry.run_metric`, not duplicate SQL.

- [ ] **Step 1: Identify the overlap.** In `dashboard_api.py`, find the KPI values that duplicate a registry metric (`exec_kpis` / `header` fields for MRR, active donors, total donors, active sustainers, revenue; streaming TLH/AAS where used). For each, replace the bespoke computation with `run_metric(id, brand=None, period="all"|"12m", group_by=None)["data"][0]["value"]`. Import `from metrics.registry import run_metric` (the Dockerfile already ships `metrics/`). Where the bespoke query and the registry disagree on window, prefer the registry's period semantics and note it.

- [ ] **Step 2: Parity test** — `tests/test_dashboard_registry_parity.py` asserts the payload KPI equals the registry value (no drift):

```python
"""The dashboard's headline KPIs must equal the registry (one definition)."""
from __future__ import annotations
import importlib
dashboard_api = importlib.import_module("service.dashboard_api")
from metrics.registry import run_metric

def test_mrr_matches_registry():
    p = dashboard_api.dashboard_data()
    reg = run_metric("sustainer_mrr")["data"][0]["value"]
    # locate MRR in the payload (exec_kpis or header) — adjust key to match impl
    got = p["exec_kpis"][0].get("sustainer_mrr") or p["header"][0].get("sustainer_mrr")
    assert got == reg
```

(Expand with the same pattern for `active_donors`, `total_donors`, `active_sustainers`, `revenue` once Step 1 fixes the exact payload keys.)

- [ ] **Step 3: Run** — `python -m pytest tests/test_dashboard_registry_parity.py -v` → pass; then full suite `python -m pytest -q` stays green.

- [ ] **Step 4: Commit** — `git add service/dashboard_api.py tests/test_dashboard_registry_parity.py && git commit -m "refactor(api): headline KPIs via metric registry (one definition)"`

---

### Task 4: Tab restructure (source → role)

**Files:**
- Modify: `dashboard/src/tabs.jsx` (rewrite `TABS`)
- Modify: `dashboard/src/App.jsx` (default tab + any tab-name string literals)

**Interfaces:**
- `TABS` exports keys in order: `Overview, Program Director, Underwriting, Digital, Social, Finance / Exec`. (PD + Underwriting fns are stubs here; Task 5/6 fill them.)

- [ ] **Step 1: Read `tabs.jsx` + `App.jsx`.** Rename `DigitalReach`→keep fn but key it `Digital`; `Financial`→`Finance / Exec`; keep `Social`. Remove the `Nielsen` and `Triton` and `Mailchimp` standalone tab entries from `TABS` (keep their render code available — PD/Underwriting/Social will reuse the widget logic). Add `Program Director` and `Underwriting` keys pointing at new stub fns `ProgramDirector(d,f)` / `Underwriting(d,f)` that render just a `SectionTitle` + `SECTION_INTRO` for now.

- [ ] **Step 2:** In `App.jsx`, ensure default `tab` is `'Overview'` and the `tab !== 'Overview'` filter-bar guard still holds. No other change.

- [ ] **Step 3: Verify build + smoke** — `cd dashboard && npm run build` exits 0; `npm run preview` and confirm the 6 tabs render and switch (PD/Underwriting show their intro only).

- [ ] **Step 4: Commit** — `git add dashboard/src/tabs.jsx dashboard/src/App.jsx && git commit -m "feat(dashboard): role-based tab structure (6 tabs)"`

---

### Task 5: Program Director tab

**Files:** Modify `dashboard/src/tabs.jsx` (fill `ProgramDirector`); maybe add a `HourGrid`/`Heatmap` helper to `components.jsx`.

**Widget spec** (reuse `filterByBrand(rows, f.brand, field, mapper)`, `filterByDate`, `Lines`, `pivot`, `sumBy`, `Kpi`, `ChartCard`, `NoBrandData`; decks from `DECK`, definitions from `GLOSSARY`):

- [ ] **Step 1:** Section intro = `SECTION_INTRO.program_director`. Gate the whole tab on streaming channel: if `!brandHasChannel(f.brand,'streaming')` show `<NoBrandData brand channel="streaming"/>`.
- [ ] **Step 2: Headline KPIs** (filter `tlh_by_station`/registry-backed values by brand via `fromStation`): TLH (info `GLOSSARY.tlh`), AAS (info `GLOSSARY.aas`), CUME (info `GLOSSARY.cume`), TSL latest (info `GLOSSARY.tsl`).
- [ ] **Step 3: Daypart heatmap** — `ChartCard` deck `DECK.daypart_aas`; from `daypart_aas` filtered by brand (`fromStation`), render AAS per daypart (bar per station, or a colored 5-cell row). Order dayparts by `daypart_id`.
- [ ] **Step 4: Hour × day grid** — `ChartCard` deck `DECK.hourly_grid`; from `hourly_grid` filtered by brand; render a 7×24 grid coloring cells by `aas` (build a small `HourGrid` component; rows = dow 0–6 labeled Sun–Sat, cols = hour 0–23).
- [ ] **Step 5: TSL trend** — `ChartCard` deck `DECK.tsl_trend`; from `tsl_trend` filtered by brand + `filterByDate(_, 'month', f.range)`; `Lines` per station.
- [ ] **Step 6: TLH/AAS/CUME trend** — reuse the existing Triton `tlh_by_station` line(s) filtered by brand+date.
- [ ] **Step 7: Nielsen block** — reuse existing `nielsen_aqh_trend` + `nielsen_share` widgets (filtered via `fromStation`); deck `DECK.aqh_share_trend`, info `GLOSSARY.aqh_share`. Only render if `brandHasChannel(f.brand,'nielsen')`.
- [ ] **Step 8: Top web content** — `ChartCard` deck `DECK.top_web_content`; from `top_web_content` filtered via `fromGaProperty`; table of page_path/views/avg_engagement_s. Render only if `brandHasChannel(f.brand,'web')`, else omit (not a hard error).
- [ ] **Step 9: Build + browser smoke** (`npm run build`; preview: switch brands RM/HYFIN/RM414, confirm gating + data). **Commit** `feat(dashboard): Program Director tab`.

---

### Task 6: Underwriting tab

**Files:** Modify `dashboard/src/tabs.jsx` (fill `Underwriting`).

- [ ] **Step 1:** Intro = `SECTION_INTRO.underwriting`. Gate on streaming; `NoBrandData` if absent.
- [ ] **Step 2: Sellable-inventory KPIs** — AAS overall + per top daypart from `daypart_aas` (brand-filtered); info `GLOSSARY.aas`.
- [ ] **Step 3: AAS by daypart × station** — the marquee widget: reuse the daypart heatmap from Task 5 (extract the shared component); deck "The audience we can sell, by time of day."
- [ ] **Step 4: Device / platform split** — from existing `platform_breakdown` (brand-filtered via `fromStation`); pie/bar; deck `DECK.device_split`.
- [ ] **Step 5: Nielsen for advertisers** — AQH/cume + (if present) demo composition from the nielsen datasets; render only if `brandHasChannel(f.brand,'nielsen')`; info `GLOSSARY.aqh_persons`.
- [ ] **Step 6: Underwriting revenue** — from `revenue_vs_budget`/`revenue_mix` (org-wide → `OrgWideBadge`); add an italic note: "Per-sponsor pipeline is coming once underwriting/CRM data is loaded."
- [ ] **Step 7: Build + browser smoke. Commit** `feat(dashboard): Underwriting tab`.

---

### Task 7: Decks on carried-over tabs + deploy + QA

**Files:** Modify `dashboard/src/tabs.jsx` (Digital, Social, Finance decks); deploy.

- [ ] **Step 1:** Add `SECTION_INTRO` + relevant `DECK`/`GLOSSARY` info to the Digital, Social, and Finance/Exec tabs (e.g. Finance revenue-vs-budget deck + org-wide badge; Social reach/impressions info; Digital organic-traffic info). Move the Mailchimp email widgets into the Social tab.
- [ ] **Step 2: Full test suite** — `python -m pytest -q` green. **Frontend build** — `cd dashboard && npm run build` exits 0.
- [ ] **Step 3: Deploy API** — `flyctl deploy --app rm-data-loader`; verify `/health` 200 and `/api/dashboard` returns the new keys (`curl … | python -m json.tool | grep daypart_aas`).
- [ ] **Step 4: Browser QA** (issue checklist) — each of the 6 tabs renders real data; PD daypart heatmap + hour×day grid populate; decks + ⓘ tooltips show glossary text; brand filter narrows; "not measured" states where a brand lacks a channel; no console errors. Capture notes.
- [ ] **Step 5: Commit** any QA fixes; deploy the dashboard (Vercel or the existing static host) if that's in scope.

---

## Notes for the controller
- `daypart_aas` and `hourly_grid` are period-agnostic profiles (last 365d) and intentionally ignore the date filter — say so in their decks; brand filter still applies.
- Frontend tab tasks (5/6/7) are best verified in-browser; expect small iteration. Keep the existing `tabs.jsx` widget patterns — read neighbours before writing.
- After merge, update `docs/dashboard-roadmap.md`'s "build sequence" + CLAUDE.md, and create the slice-2 / slice-3 Linear child issues.
