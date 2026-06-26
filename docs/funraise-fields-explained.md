# Funraise donations — what we capture in Neon (plain English)

> Last updated 2026-06-25. This explains every field we store from Funraise, in
> everyday language. Technical shape lives in `schema/006_funraise.sql`; this
> doc is the "what does it mean and why do we keep it" companion.

## The big picture

Funraise is our donation platform. We pull its data into the warehouse so the
Development and Finance dashboards can answer questions like *"How much did we
raise this month?"*, *"How many recurring donors do we have?"*, *"Which campaign
drove the most gifts?"*, and *"Where do our donors live?"* — **without** storing
the kind of personal information we don't need.

Data arrives two ways:
- **Real-time:** every time a gift is made (or edited), Funraise instantly sends
  it to us (a "webhook"). That gift lands in **`fact_transactions`**.
- **Nightly catch-up (still being built):** once a night we'll ask Funraise's API
  for the slower-changing lists — donors, recurring plans, campaigns — to fill in
  anything the real-time feed missed.

## Privacy: what we deliberately DO NOT keep

We made a conscious choice (2026-06-25) to **minimize personal data**. We do
**not** store donor **names, email addresses, or phone numbers**.

Instead, for matching purposes we keep a **scrambled fingerprint of the email**
(`email_sha256`). Think of it as a one-way code: the same email always produces
the same code, so we *can* tell whether a donor is also on our email list — but
the code **cannot be turned back into the actual email address**. We get the
analytics value (overlap, loyalty) without holding contact info we don't need.

We still keep **city, state, and ZIP**, because geography matters for grant
narratives and underwriting — and on its own it doesn't identify anyone.

---

## Table 1 — `fact_transactions` (every single gift)

One row per donation. This is the money table.

| Field | Plain-English meaning |
|---|---|
| `transaction_id` | Funraise's unique ID for the gift. How we avoid duplicates. |
| `supporter_id` | An anonymous code for the donor (no name attached). Lets us count gifts per donor without knowing who they are. |
| `campaign_id` | Which Funraise campaign the gift came in under. |
| `transaction_at` | The **exact moment** of the gift (date + time). Lets us line up donation spikes against on-air pledge breaks and specific asks. |
| `transaction_date` | Just the day, kept for fast daily/monthly totals (derived from `transaction_at`). |
| `amount` | The full gift amount (what the donor gave). |
| `fee` | Processing fee taken out (credit-card/platform fees). |
| `net` | What we actually keep after fees (`amount` − `fee`). |
| `currency` | Currency of the gift (almost always USD). |
| `payment_method` | How they paid — card, bank transfer, etc. |
| `recurring` | **TRUE = part of a monthly/recurring plan; FALSE = one-time gift.** This is how we split recurring vs one-time. |
| `status` | State of the gift — completed, pending, failed, refunded, etc. |
| `utm_source` / `utm_medium` / `utm_campaign` | Marketing tags showing where the donor came from (e.g. a Facebook ad, an email). Lets us tie gifts back to campaigns. |
| `designation` | Which fund/program the gift supports (e.g. General Fund, a specific initiative). |
| `restricted` | TRUE if the money is restricted to a specific purpose, FALSE if it's unrestricted. Important for finance and grant reporting. |
| `fee_covered` | TRUE if the donor chose to cover the processing fee themselves. |
| `fee_covered_amount` | How much fee the donor covered. |
| `refunded` | TRUE if the gift was refunded/reversed. |
| `refunded_amount` | How much was refunded. |
| `refunded_at` | When it was refunded. |
| `channel` | Where the gift came through — website, event, text-to-give, etc. |
| `recurring_plan_id` | If it's a recurring gift, links to the plan in `fact_subscriptions`. |
| `loaded_at` | Bookkeeping: when we recorded the row (not donor data). |

---

## Table 2 — `dim_supporters` (the donors — anonymized)

One row per donor. **No names, no email, no phone.**

| Field | Plain-English meaning |
|---|---|
| `supporter_id` | The anonymous donor code (matches `fact_transactions`). |
| `email_sha256` | Scrambled, non-reversible fingerprint of the email — used only to check overlap with our email list. **Not a readable address.** |
| `city` / `state` / `postal_code` / `country` | Where the donor is located (geography only). |
| `first_donation_at` | The date of their very first gift — useful for "new vs returning donor." |
| `lifetime_total` | Total they've given across all time — for major-donor and loyalty analysis. |
| `loaded_at` | Bookkeeping timestamp. |

---

## Table 3 — `fact_subscriptions` (recurring giving plans)

One row per recurring plan (the *plan itself*, separate from the individual
monthly charges, which live in `fact_transactions`).

| Field | Plain-English meaning |
|---|---|
| `subscription_id` | Unique ID for the recurring plan. |
| `supporter_id` | The anonymous donor who owns the plan. |
| `campaign_id` | Campaign the plan is tied to. |
| `amount` | How much is charged each cycle. |
| `frequency` | How often — monthly, annual, etc. |
| `status` | active, paused, or churned (cancelled). |
| `started_at` | When the recurring plan began. |
| `canceled_at` | When it was cancelled, if it was. |
| `loaded_at` | Bookkeeping timestamp. |

---

## Table 4 — `dim_campaigns` (campaign details)

One row per Funraise campaign — the lookup that gives campaign IDs a name.

| Field | Plain-English meaning |
|---|---|
| `campaign_id` | Unique ID (matches the gifts and plans above). |
| `name` | The campaign's name (e.g. "Fall Pledge Drive"). |
| `goal_amount` | The fundraising goal, if one was set. |
| `start_date` / `end_date` | The campaign window. |
| `loaded_at` | Bookkeeping timestamp. |

---

## A note on the field names

The exact field names from Funraise are still being confirmed against a real
gift payload. The *meanings* above won't change, but a few internal mappings may
be adjusted once we see Funraise's actual data format. This doc will be updated
when that's locked in.
