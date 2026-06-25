# Funraise export — column checklist

> Which columns to include in each Funraise transaction export, mapped to the
> warehouse fields in `funraise.fact_transactions` / `dim_supporters`. Match by
> meaning — Funraise's exact column labels may differ slightly.

## ✅ CONFIRMED against a real export (2026-06-25)

Use the **same columns for all 21 windows**. The primary key is **`Id`** (verified
unique + 100% populated). Confirmed real column labels and mappings:

| Funraise column | → warehouse field | Notes |
|---|---|---|
| **`Id`** | `transaction_id` (**PRIMARY KEY**) | Required. Unique per gift. |
| `Transaction Date` | `transaction_at` + `transaction_date` | Full timestamp; has a `[US/Central]` suffix the loader strips. |
| `Supporter Id` | `supporter_id` | |
| `Amount` (= `Source Amount`) | `amount` | Gross. |
| `Currency` | `currency` | |
| `Payment Method` (+ `Card Type`) | `payment_method` | |
| `Recurring` / `Frequency` | `recurring` | |
| `Recurring Id` | `recurring_plan_id` | |
| `Status` | `status` | Complete / Failed / **Refunded** (covers refunds). |
| `Donor Covered Fees` / `Donor Covered Fee Amount` | `fee_covered` / `fee_covered_amount` | |
| `Form` | `designation` | Best designation/fund proxy. |
| `Form Id` | `campaign_id` | (`Campaign Page Id` is ~always empty.) |
| `City` / `State/Province` / `Postal Code` / `Country` | geo | |
| `Match` | (matching-gift flag — bonus) | |

**NOT available as export columns** (so these stay NULL for the backfill):
`fee`, `net`, `restricted`, `channel`, and a true gateway transaction id
(`Order ID` exists but is ~99.6% empty — skip it). Email/names are not included
(fine — no PII).

---

### Original conceptual checklist (kept for reference)

## ✅ Must-have (core gift record)
- [ ] **Transaction ID** → `transaction_id`
- [ ] **Donor/Supporter ID** → `supporter_id` *(the ID, not the name)*
- [ ] **Campaign** (ID and/or name) → `campaign_id`
- [ ] **Donation Date _and time_** → `transaction_at` (exact moment) + `transaction_date` (day, derived)
- [ ] **Amount** (gross) → `amount`
- [ ] **Fee** → `fee`
- [ ] **Net** → `net` *(if not offered, we compute amount − fee)*
- [ ] **Currency** → `currency`
- [ ] **Payment method** → `payment_method`
- [ ] **Frequency / Recurring?** (one-time vs recurring) → `recurring`
- [ ] **Status** → `status`
- [ ] **UTM Source / Medium / Campaign** → `utm_source` / `utm_medium` / `utm_campaign`

## ✅ The 4 extras
- [ ] **Designation / Fund** → `designation`
- [ ] **Restricted?** → `restricted`
- [ ] **Fee covered by donor?** + **amount covered** → `fee_covered`, `fee_covered_amount`
- [ ] **Refunded?** + **refund amount** + **refund date** → `refunded`, `refunded_amount`, `refunded_at`
- [ ] **Channel / Source** (web, event, text-to-give) → `channel`
- [ ] **Recurring plan / Subscription ID** → `recurring_plan_id`

## ✅ Donor geography
- [ ] **City**, **State**, **ZIP/Postal code**, **Country** → `city`/`state`/`postal_code`/`country`
- [ ] **First donation date** → `first_donation_at`
- [ ] **Lifetime total** → `lifetime_total`

## ⚠️ Email — optional
- [ ] **Email** — include **only if** you want donor↔email-list matching. The loader
  **hashes it and discards the readable address** on import (nothing readable is
  stored). Leave it out entirely if you'd rather it never enter the pipeline.

## 🚫 Not needed (dropped even if present in the file)
- First name, Last name, Phone — we do not store these (see `funraise-fields-explained.md`).

## Format
- **CSV or XLSX**, one file per export window (see `funraise-backfill-export-plan.md`).
