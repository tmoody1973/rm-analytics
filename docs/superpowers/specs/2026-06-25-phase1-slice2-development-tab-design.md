# Phase 1 Slice 2 — Development Director tab (Funraise) — Design

> Companion to the Phase-1 epic (MOO-176). Builds the **Development Director** role tab
> on the already-loaded Funraise data. Plan: `docs/superpowers/plans/2026-06-25-phase1-slice2-development-tab.md`.

## Goal

Give the Development Director a single tab that answers *"How healthy is our supporter
base — how many give, do they come back, what are they worth, and how is our membership
(sustainer) engine doing?"* — sourced from `funraise.*`, org-wide, in the slice-1
editorial voice, with assistant-citable KPIs from the metric registry.

## Persona framing (public radio)

Radio Milwaukee is sustainer-driven: **88% of completed gifts are recurring**. A public-radio
DD lives on the membership/sustainer model, so the tab leads with the sustainer story
(MRR vs goal, sustainer share, conversion) alongside the universal donor-health fundamentals
(retention, acquisition/attrition, lifetime value).

## Global decisions

- **Org-wide only.** Funraise transactions carry no `station_code`; donation brand attribution
  would be fragile (designations are campaign/fund names, not brands). Every card uses the
  existing `OrgWideBadge`; the brand filter is a **no-op** on this tab (documented in the intro).
- **Data layer = slice-1 split.** Headline KPIs come from `metrics.registry.run_metric`
  (one definition, assistant-citable via `/api/metric`); long-tail widgets come from bespoke
  parameterized SQL added to `service/dashboard_api.py`. Pre-aggregated donor metrics are safe
  to expose; this does **not** touch the `rm_readonly` funraise block (that gates only the
  assistant's raw SQL).
- **No new frontend data path / no new npm dependency.** Single `fetchDashboard()` +
  client-side filtering; charts via existing Recharts (`Lines`, bars), geography + tiers as tables.
- **Editorial reuse.** Extend `glossary.js` (`SECTION_INTRO.development`, new `GLOSSARY`/`DECK`
  entries); reuse slice-1 `Kpi`/`ChartCard` `info`/`deck` props, `SectionTitle`, `NoBrandData`,
  `OrgWideBadge`.
- **Tab placement.** 7 tabs: `Overview · Program Director · Underwriting · Development · Digital · Social · Finance / Exec` — Development sits with the audience→revenue roles, before the channel tabs.

## Data caveats (verified against live data, 2026-06-25)

- **`status='Complete'` is the only valid gift status** (122,479 Complete; also Failed/Refunded/Pending). All giving SQL filters to Complete and excludes refunded.
- **`channel` is 100% NULL** → the "channel mix" idea is replaced by **payment-method mix** (`payment_method` is fully populated: Credit Card / ACH / Physical Check / Apple Pay / PayPal).
- **`utm_*` ~99% NULL** → not usable as a source dimension.
- **Average gift is skewed** (mean ~$68 but a $1,000,000 gift exists) → KPI shows **median + average**.
- **`first_donation_at` only ~54% populated** → derive a supporter's first gift from
  `min(transaction_date)` per supporter, not the rollup column.
- **Data floor is 2023-01-01** → "new donor" means *first gift in our window*; retention
  trend starts where two full comparison years exist.
- **Subscription churn = `status='Cancelled'`** (Active 2,726; also Failed/Redacted/Cancelled).

## Widget set

**Headline KPI row** (registry-backed; ⓘ glossary; OrgWideBadge):
Active donors (12mo) · Sustainer MRR vs $50K · Sustainer share of giving % · Donor retention % ·
Median gift (avg shown as note) · Total raised (12mo). Secondary: active sustainers, new, lapsed.

1. **Retention trend — first-year vs repeat** (`donor_retention_trend`): of supporters who gave
   in year N−1, the share who gave again in year N, split into first-year cohort vs repeat.
2. **New / returning / lapsed** (`donor_status_trend`): monthly stacked counts. New = first-ever
   gift (min txn date) in month; returning = gave this month and earlier; lapsed = no Complete
   gift in trailing 12mo as of month end.
3. **Sustainer flow + conversion** (`sustainer_flow`): MRR trend with net adds vs churned plans
   per month (from `fact_subscriptions`); conversion = share of donors who are recurring.
4. **Lifetime-value tiers** (`ltv_tiers`): `<$100 / $100–499 / $500–999 / $1K–4,999 / $5K+`,
   donor count + total $ per tier (top-donor concentration).
5. **Payment-method mix** (`payment_method_mix`): gift count + $ by method (CC/ACH/Check/…).
6. **Donor geography** (`donor_geo`): top states + top ZIPs by donor count + lifetime total (table).
7. **Audience → giving funnel** — **deferred** (quiet note): blocked until the email/ESP source is loaded.

## Backend additions

**Registry metrics** (`metrics/registry.py`): `donor_retention_pct`, `lapsed_donors`,
`new_donors`, `total_raised`, `avg_gift` (returns median + mean), `sustainer_share`.

**Bespoke payload keys** (`service/dashboard_api.py`): `donor_retention_trend`,
`donor_status_trend`, `sustainer_flow`, `ltv_tiers`, `payment_method_mix`, `donor_geo`.

## Testing

- Shape/discriminator tests per new payload key (mirror `tests/test_dashboard_api_queries.py`).
- Registry parity tests for the new metrics (mirror `tests/test_dashboard_registry_parity.py`).
- Full suite green; frontend `npm run build` clean.

## Out of scope (slice 2)

- Audience→giving funnel / donor↔email overlap (ESP source not loaded).
- Per-brand donation attribution.
- Geographic *map* visualization (would need a map lib — table only).
- Giving-by-designation/fund breakdown (designations are noisy "Historic Sustainer Import" bulk rows).
- Campaign/pledge-drive impact (belongs to a later `marts.campaign_impact` slice).

## Branch / tracking

Stacked on the slice-1 branch (`tarikjmoody/moo-176-slice1-role-tabs`) because the Development
tab extends slice-1's `TABS`/glossary/components; rebase onto `main` after slice-1 merges.
Tracked as a new MOO child issue under the Phase-1 epic.
