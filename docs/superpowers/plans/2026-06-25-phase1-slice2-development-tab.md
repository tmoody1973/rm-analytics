# Phase 1 Slice 2 — Development Director tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-06-25-phase1-slice2-development-tab-design.md`.

**Goal:** Build the org-wide **Development Director** tab on Funraise data — donor health (retention, acquisition/attrition, lifetime value) led by the public-radio sustainer story (MRR vs goal, sustainer share, conversion) — with assistant-citable KPIs from the metric registry and the slice-1 editorial layer.

**Architecture:** Vite + React frontend (single `/api/dashboard` fetch, client-side filter — already built; this tab ignores the brand filter and is org-wide). FastAPI `dashboard_api.py` returns one bulk payload; headline KPIs from `metrics.registry.run_metric`, long-tail widgets from bespoke SQL on `funraise.*`.

**Tech Stack:** Python 3.12, psycopg3, FastAPI, pytest; React 18, Recharts, Vite. No new dependencies.

## Global Constraints

- **Org-wide only.** Funraise has no `station_code`; every card uses `OrgWideBadge`; brand filter is a no-op on this tab.
- **Gift validity:** all giving SQL filters `status='Complete'` and excludes refunded (`coalesce(refunded,false)=false`) where it affects $ totals.
- **Data floor 2023-01-01;** "new donor" = first Complete gift in our window. First gift is derived from `min(transaction_date)` per supporter (the `first_donation_at` rollup is only ~54% populated — do NOT rely on it).
- **Editorial voice:** sentence case, contractions, Oxford comma, no hype, no jargon, no emoji. Extend `dashboard/src/glossary.js`; reuse slice-1 `Kpi`/`ChartCard` `info`/`deck`, `SectionTitle`, `OrgWideBadge`.
- **No new frontend data path, no router, no new npm dependency.** Charts via existing Recharts helpers; geography + LTV tiers + payment mix as tables/bars.
- **Metric-definition decisions (verified against live data 2026-06-25):**
  - `sustainer_share` = **donor-count based** (% of active-12mo donors who are sustainers). Dollar-share is outlier-distorted (a $1M one-time gift drops it to ~19% vs ~88% by count) — show dollar-share only as a secondary note, not the headline.
  - `avg_gift` = **median + mean** (median ~$10.80 reflects monthly sustainer charges; mean ~$83 is outlier-pulled — show both, deck explains).
  - `donor_retention_trend` = drop the incomplete current year (year+1 has no data → 0%) and flag that the earliest year (2023) is inflated by the data floor.

---

### Task 1: Editorial foundation — development glossary + section intro + decks

**Files:** Modify `dashboard/src/glossary.js`.

- [ ] **Step 1:** Add `SECTION_INTRO.development` (RM voice): "The health of our supporter base: how many give, whether they come back, and what they're worth over time. Org-wide — the brand filter doesn't apply here."
- [ ] **Step 2:** Add `GLOSSARY` entries: `sustainer_share` ("The share of our active donors who give every month as sustaining members. Public radio runs on these."), `sustainer_conversion` ("Of donors who started with a one-time gift, the share who became monthly sustainers."), `avg_gift` ("The typical gift — we show the median, since a few large gifts pull the average up."), `ltv` ("Lifetime giving — every completed gift from a supporter, added up."), `lapsed_donor` ("Someone who gave before but hasn't given in the last 12 months."), `new_donor` ("Someone whose first gift to us landed in this period."), `payment_method` ("How gifts come in — credit card, ACH bank transfer, check, and so on. ACH costs us less and tends to stick.")  — reuse existing `donor_retention`, `active_donor` from slice 1.
- [ ] **Step 3:** Add `DECK` entries: `retention_cohort` ("First-year donors are the leaky bucket; repeat donors stick. Here's the gap."), `donor_status` ("New donors coming in versus our returning base, month by month."), `sustainer_flow` ("Sustaining members gained and lost each month."), `ltv_tiers` ("Where our lifetime giving concentrates — and how few donors hold most of it."), `payment_mix` ("How gifts reach us, by method and dollars."), `donor_geo` ("Where our supporters are."). Reuse `donor_retention`, `sustainer_mrr` decks from slice 1.
- [ ] **Step 4:** `cd dashboard && npm run build` exits 0. **Commit:** `feat(dashboard): development tab editorial (glossary/intro/decks)`.

---

### Task 2: New Funraise queries in the API

**Files:** Modify `service/dashboard_api.py` (add to `QUERIES` / payload); Test `tests/test_dashboard_dev_queries.py` (create).

**Interfaces:** Produces payload keys `donor_retention_trend`, `donor_status_trend`, `sustainer_flow`, `ltv_tiers`, `payment_method_mix`, `donor_geo_state`, `donor_geo_zip`.

- [ ] **Step 1: Read `service/dashboard_api.py`** to learn the exact `QUERIES` structure and row serialization; follow it exactly. All queries below are **verified against live Neon (2026-06-25)**.

- [ ] **Step 2: Add the queries.**

```sql
-- donor_retention_trend: first-year vs repeat cohort retention, prior_year -> prior_year+1.
-- App must DROP the latest prior_year (year+1 incomplete) and flag the earliest year (data floor).
WITH gifts AS (
  SELECT supporter_id, extract(year FROM transaction_date)::int AS yr
  FROM funraise.fact_transactions WHERE status='Complete' GROUP BY 1,2),
first_yr AS (SELECT supporter_id, min(yr) AS fy FROM gifts GROUP BY 1)
SELECT g.yr AS prior_year,
       CASE WHEN g.yr = f.fy THEN 'first_year' ELSE 'repeat' END AS cohort,
       count(DISTINCT g.supporter_id) AS donors,
       round(100.0*count(DISTINCT g2.supporter_id)/NULLIF(count(DISTINCT g.supporter_id),0),1) AS retention_pct
FROM gifts g JOIN first_yr f USING (supporter_id)
LEFT JOIN gifts g2 ON g2.supporter_id=g.supporter_id AND g2.yr=g.yr+1
GROUP BY g.yr, cohort ORDER BY g.yr, cohort;
```

```sql
-- donor_status_trend: monthly new vs returning donor counts.
-- (Lapsed is a headline KPI, not in this monthly series — per-month lapsed is an expensive
--  trailing-window calc deferred; note this in the deck.)
WITH first_gift AS (
  SELECT supporter_id, min(transaction_date) AS fg
  FROM funraise.fact_transactions WHERE status='Complete' GROUP BY 1),
monthly AS (
  SELECT DISTINCT supporter_id, date_trunc('month',transaction_date)::date AS m
  FROM funraise.fact_transactions WHERE status='Complete')
SELECT m.m AS month,
       count(*) FILTER (WHERE date_trunc('month',f.fg)=m.m) AS new_donors,
       count(*) FILTER (WHERE date_trunc('month',f.fg)<m.m) AS returning_donors
FROM monthly m JOIN first_gift f USING (supporter_id)
GROUP BY m.m ORDER BY m.m;
```

```sql
-- sustainer_flow: monthly sustainers added vs churned. NOTE: churned depends on canceled_at,
-- which is sparsely populated — churned may read 0 for many months. Show what exists; do not fabricate.
WITH adds AS (
  SELECT date_trunc('month',started_at)::date AS m, count(*) AS added
  FROM funraise.fact_subscriptions WHERE started_at IS NOT NULL GROUP BY 1),
churn AS (
  SELECT date_trunc('month',canceled_at)::date AS m, count(*) AS churned
  FROM funraise.fact_subscriptions WHERE canceled_at IS NOT NULL AND status='Cancelled' GROUP BY 1)
SELECT coalesce(a.m,c.m) AS month, coalesce(a.added,0) AS added, coalesce(c.churned,0) AS churned
FROM adds a FULL OUTER JOIN churn c ON a.m=c.m ORDER BY month;
```

```sql
-- ltv_tiers: lifetime-value buckets with donor count + total $.
SELECT CASE WHEN lifetime_total<100 THEN '<$100'
            WHEN lifetime_total<500 THEN '$100-499'
            WHEN lifetime_total<1000 THEN '$500-999'
            WHEN lifetime_total<5000 THEN '$1K-4,999'
            ELSE '$5K+' END AS tier,
       count(*) AS donors, round(sum(lifetime_total)) AS total
FROM funraise.dim_supporters WHERE lifetime_total>0
GROUP BY tier ORDER BY min(lifetime_total);   -- min() keeps tiers in ascending order
```

```sql
-- payment_method_mix: gift count + $ by method (replaces the all-NULL channel field).
SELECT coalesce(nullif(payment_method,''),'Unknown') AS method,
       count(*) AS gifts, round(sum(amount)) AS total
FROM funraise.fact_transactions
WHERE status='Complete' AND coalesce(refunded,false)=false
GROUP BY method ORDER BY total DESC;
```

```sql
-- donor_geo_state: top states by donor count + lifetime total.
SELECT coalesce(nullif(state,''),'Unknown') AS state,
       count(*) AS donors, round(sum(lifetime_total)) AS lifetime
FROM funraise.dim_supporters WHERE lifetime_total>0
GROUP BY state ORDER BY donors DESC LIMIT 15;
```

```sql
-- donor_geo_zip: top ZIPs by donor count + lifetime total.
SELECT coalesce(nullif(postal_code,''),'Unknown') AS zip,
       count(*) AS donors, round(sum(lifetime_total)) AS lifetime
FROM funraise.dim_supporters WHERE lifetime_total>0
GROUP BY zip ORDER BY donors DESC LIMIT 15;
```

- [ ] **Step 3: Write `tests/test_dashboard_dev_queries.py`** — shape/discriminator checks per key (mirror `tests/test_dashboard_api_queries.py`): each key present and non-empty; `donor_retention_trend` rows have `prior_year`/`cohort`/`retention_pct` and `cohort` ∈ {first_year, repeat}; `donor_status_trend` rows have `month`/`new_donors`/`returning_donors`; `ltv_tiers` returns the 5 expected tier labels; `payment_method_mix` row has `method`/`gifts`/`total`; `donor_geo_state` row has `state`/`donors`.

- [ ] **Step 4: Run** `source .venv/bin/activate && python -m pytest tests/test_dashboard_dev_queries.py -v` → all pass.
- [ ] **Step 5: Commit** `feat(api): development tab funraise queries (retention/status/sustainer/ltv/payment/geo)`.

---

### Task 3: New donor registry metrics

**Files:** Modify `metrics/registry.py` (+ any metric module it uses); Test `tests/test_dev_registry_parity.py` (create).

**Interfaces:** Adds registry ids `total_raised`, `avg_gift`, `sustainer_share`, `donor_retention_pct`, `new_donors`, `lapsed_donors`.

- [ ] **Step 1: Read `metrics/registry.py`** — copy the existing donor metric pattern (`_active_donors`, `_sustainer_mrr`) exactly: function signature `(brand, period, group_by)`, return shape `{"data":[{"value":...}], ...}`, period handling. All metrics here are org-wide (ignore `brand`).

- [ ] **Step 2: Add metrics** (verified SQL, period `12m` = last 365 days, `all` = no date filter):

```sql
-- total_raised
SELECT round(sum(amount)) AS value FROM funraise.fact_transactions
WHERE status='Complete' AND coalesce(refunded,false)=false [AND transaction_date >= :since];

-- avg_gift  (return median as value; include mean as an extra field)
SELECT round(percentile_cont(0.5) WITHIN GROUP (ORDER BY amount)::numeric,2) AS value,
       round(avg(amount),2) AS mean
FROM funraise.fact_transactions
WHERE status='Complete' AND amount>0 AND coalesce(refunded,false)=false [AND transaction_date >= :since];

-- sustainer_share  (DONOR-COUNT based: % of active-12mo donors who are sustainers)
WITH active AS (SELECT DISTINCT supporter_id FROM funraise.fact_transactions
                WHERE status='Complete' AND transaction_date >= current_date-interval '365 days'),
sustainers AS (SELECT DISTINCT supporter_id FROM funraise.fact_transactions
               WHERE status='Complete' AND recurring AND transaction_date >= current_date-interval '365 days')
SELECT round(100.0*(SELECT count(*) FROM sustainers)/NULLIF((SELECT count(*) FROM active),0),1) AS value;

-- donor_retention_pct  (of donors active in months -24..-12, share active in last 12mo)
WITH prior AS (SELECT DISTINCT supporter_id FROM funraise.fact_transactions
  WHERE status='Complete' AND transaction_date>=current_date-interval '730 days'
    AND transaction_date<current_date-interval '365 days'),
recent AS (SELECT DISTINCT supporter_id FROM funraise.fact_transactions
  WHERE status='Complete' AND transaction_date>=current_date-interval '365 days')
SELECT round(100.0*count(*) FILTER (WHERE supporter_id IN (SELECT supporter_id FROM recent))
  /NULLIF(count(*),0),1) AS value FROM prior;

-- new_donors  (first-ever Complete gift within period)
SELECT count(*) AS value FROM (
  SELECT supporter_id, min(transaction_date) AS fg
  FROM funraise.fact_transactions WHERE status='Complete' GROUP BY 1) s
WHERE s.fg >= [:since | current_date-interval '365 days'];

-- lapsed_donors  (gave at some point, last Complete gift > 12mo ago)
SELECT count(*) AS value FROM (
  SELECT supporter_id, max(transaction_date) AS lg
  FROM funraise.fact_transactions WHERE status='Complete' GROUP BY 1) s
WHERE s.lg < current_date-interval '365 days';
```

Verified values today: retention ≈ 70.7%, sustainer_share (count) high, avg_gift median ≈ $10.80 / mean ≈ $83.13.

- [ ] **Step 3: Parity test** `tests/test_dev_registry_parity.py` — each new metric returns a numeric `value`; `donor_retention_pct` and `sustainer_share` are 0–100; `avg_gift` row also carries `mean`. (No dashboard-payload parity needed unless a payload KPI duplicates a metric — if Task 5 sources a headline KPI from the registry, assert equality like slice-1's parity test.)
- [ ] **Step 4: Run** `python -m pytest tests/test_dev_registry_parity.py -v` → pass; then full suite `python -m pytest -q` green.
- [ ] **Step 5: Commit** `feat(metrics): donor registry metrics (raised/avg-gift/sustainer-share/retention/new/lapsed)`.

---

### Task 4: Add the Development tab (structure)

**Files:** Modify `dashboard/src/tabs.jsx` (add `Development` to `TABS`), `dashboard/src/App.jsx` only if a tab-name literal needs it.

- [ ] **Step 1: Read `tabs.jsx`.** Add a `Development(d, f)` stub fn rendering `SectionTitle` + `SECTION_INTRO.development` + `OrgWideBadge`. Insert into `TABS` in position 4: `Overview, Program Director, Underwriting, Development, Digital, Social, Finance / Exec` (exact strings/order).
- [ ] **Step 2:** Confirm default tab still `'Overview'` and the `tab !== 'Overview'` filter-bar guard still holds (the brand filter bar will show but is a no-op on this tab — acceptable; the intro says so).
- [ ] **Step 3:** `cd dashboard && npm run build` exits 0; preview shows 7 tabs, Development shows intro only. **Commit** `feat(dashboard): add Development tab (7-tab structure)`.

---

### Task 5: Build the Development tab

**Files:** Modify `dashboard/src/tabs.jsx` (fill `Development`); maybe a small `TierBars`/table helper in `components.jsx` if no existing one fits.

Reuse `Kpi`, `ChartCard` (deck/info), `Lines`, `pivot`, `sumBy`, `OrgWideBadge`, `SectionTitle`, `money`/`num` formatters. Decks from `DECK`, definitions from `GLOSSARY`. Everything org-wide — do NOT brand-filter.

- [ ] **Step 1: Section intro** = `SECTION_INTRO.development` + `OrgWideBadge`.
- [ ] **Step 2: Headline KPI row** (registry-backed via the new metrics; read how slice-1 surfaces `exec_kpis`): Active donors, Sustainer MRR vs $50K, Sustainer share % (`info` `GLOSSARY.sustainer_share`), Donor retention % (`info` `GLOSSARY.donor_retention`), Median gift (note: mean alongside; `info` `GLOSSARY.avg_gift`), Total raised (12mo). Secondary KPIs: active sustainers, new donors, lapsed donors.
- [ ] **Step 3: Retention cohort chart** — `ChartCard` deck `DECK.retention_cohort`; from `donor_retention_trend`. Two lines (first_year vs repeat) over `prior_year`. **Drop the latest prior_year** (incomplete year+1) and add a small note that the earliest year is inflated by the 2023 data floor.
- [ ] **Step 4: New vs returning chart** — `ChartCard` deck `DECK.donor_status`; from `donor_status_trend`, `filterByDate(_, 'month', f.range)`; stacked/!grouped lines or bars of `new_donors` + `returning_donors`.
- [ ] **Step 5: Sustainer flow** — `ChartCard` deck `DECK.sustainer_flow`; from `sustainer_flow`; bars of `added` vs `churned` per month (+ current MRR from the sustainer KPI). If churned is all 0, render added only with a note "cancellations aren't dated in the source yet."
- [ ] **Step 6: LTV tiers** — `ChartCard` deck `DECK.ltv_tiers`; from `ltv_tiers`; table or bar with tier, donors, total $ (tiers already ordered ascending). Highlight the top-tier concentration.
- [ ] **Step 7: Payment-method mix** — `ChartCard` deck `DECK.payment_mix`; from `payment_method_mix`; bar/pie of gifts + $ by method; `info` `GLOSSARY.payment_method`.
- [ ] **Step 8: Donor geography** — `ChartCard` deck `DECK.donor_geo`; two tables side by side from `donor_geo_state` + `donor_geo_zip` (state/ZIP, donors, lifetime).
- [ ] **Step 9: Audience → giving funnel** — quiet italic note: "Coming once the email source is connected — we'll show how audience turns into giving." (No data.)
- [ ] **Step 10: Build + browser smoke** (`npm run build`; preview Development tab; confirm org-wide badges, decks, ⓘ tooltips, no console errors; brand filter changes nothing on this tab). **Commit** `feat(dashboard): Development Director tab`.

---

### Task 6: QA + deploy (gated)

- [ ] **Step 1: Full suite** `python -m pytest -q` green. **Frontend build** `cd dashboard && npm run build` exits 0.
- [ ] **Step 2: Browser QA** — Development tab renders all widgets with real data; retention cohort shows the first-year-vs-repeat gap; LTV tiers + payment mix + geo populate; deferred funnel shows its note; switching the brand filter does not change the tab; no console errors. Capture notes.
- [ ] **Step 3: DEPLOY — GATED ON USER** (do not run without explicit go-ahead): `flyctl deploy --app rm-data-loader`; verify `/health` 200 and `/api/dashboard` returns the new keys.
- [ ] **Step 4: Commit** any QA fixes.

---

## Notes for the controller
- This branch is **stacked on the slice-1 branch**; if slice 1 merges/squashes first, rebase this onto `main` before its PR.
- All giving SQL is org-wide and parameterized only where it takes a period; no user input is interpolated.
- Run the final whole-branch review on the most capable model — slice 1's final review caught two broken widgets the per-task reviews missed; expect the same diligence here (esp. payload-key/valKey agreement between Task 2/3 and Task 5).
- After merge: update `docs/dashboard-roadmap.md` build sequence + `CLAUDE.md`, and create the slice-3 Linear child issue.
