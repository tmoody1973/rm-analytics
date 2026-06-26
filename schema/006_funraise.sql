-- 006_funraise.sql — Funraise donations / CRM tables.
-- Source of truth for the funraise schema shape: CLAUDE.md ("funraise" section).
-- Populated by: the transaction webhook (real-time, fact_transactions) + a nightly
-- API pull (supporters, subscriptions, campaigns). Every loader upserts on the PK,
-- so loads are idempotent and order-independent (a transaction webhook may arrive
-- before its supporter is pulled — that's why there are no hard FKs here; joins
-- happen in the marts layer).
--
-- NOTE: column set is a best-guess from CLAUDE.md. Reconcile against a real Funraise
-- webhook payload + API response before the loaders go live, then revise as 006b.

CREATE SCHEMA IF NOT EXISTS funraise;

-- Donors. supporter_id is the Funraise PK.
-- PRIVACY / DATA MINIMIZATION (decided 2026-06-25): we intentionally do NOT store
-- names, raw email, or phone. supporter_id is an opaque Funraise key (not PII) and
-- is enough for per-donor analytics. email_sha256 is a one-way hash (lowercased +
-- trimmed email -> SHA-256 hex) so donors can be matched to the email/ESP list
-- (hash both sides identically) without ever storing a readable address. The loader
-- discards the raw email at ingest — only the hash is persisted.
-- See loaders/_common.py:hash_email for the canonical normalization.
CREATE TABLE IF NOT EXISTS funraise.dim_supporters (
    supporter_id      TEXT PRIMARY KEY,
    email_sha256      TEXT,        -- one-way hash, NOT a readable address (see hash_email)
    city              TEXT,
    state             TEXT,
    postal_code       TEXT,
    country           TEXT,
    -- Derived by the supporter rollup (sums of Complete gifts from
    -- fact_transactions; recompute after new gifts load). NOTE: *_at dates are
    -- bounded by our data start (2023-01-01) — pre-2023 first gifts read as Jan 2023.
    first_donation_at  DATE,
    last_donation_at   DATE,
    lifetime_total     NUMERIC(12, 2),   -- all completed gifts (recurring + one-time)
    lifetime_recurring NUMERIC(12, 2),   -- completed gifts where recurring = true
    lifetime_onetime   NUMERIC(12, 2),   -- completed gifts where recurring = false
    active_12mo        BOOLEAN,          -- gave (Complete) within the last 12 months
    loaded_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Hash index supports the donor <-> ESP-subscriber join in the marts layer.
CREATE INDEX IF NOT EXISTS ix_funraise_supporter_email_hash ON funraise.dim_supporters (email_sha256);

-- Funraise campaign metadata.
CREATE TABLE IF NOT EXISTS funraise.dim_campaigns (
    campaign_id   TEXT PRIMARY KEY,
    name          TEXT,
    goal_amount   NUMERIC(12, 2),
    start_date    DATE,
    end_date      DATE,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every donation (one-time + recurring). transaction_id is the Funraise PK.
-- The transaction webhook fires on create OR edit -> ON CONFLICT DO UPDATE.
CREATE TABLE IF NOT EXISTS funraise.fact_transactions (
    transaction_id     TEXT PRIMARY KEY,
    supporter_id       TEXT,
    campaign_id        TEXT,
    -- transaction_at is the exact gift moment (for correlating to on-air pledge
    -- breaks); transaction_date is the day, kept for fast daily rollups.
    transaction_at     TIMESTAMPTZ,
    transaction_date   DATE,
    amount             NUMERIC(12, 2),
    fee                NUMERIC(12, 2),
    net                NUMERIC(12, 2),
    currency           TEXT,
    payment_method     TEXT,
    recurring          BOOLEAN,
    status             TEXT,
    utm_source         TEXT,
    utm_medium         TEXT,
    utm_campaign       TEXT,
    -- Designation / fund: which program the gift supports + restricted flag.
    -- Feeds finance restricted-vs-unrestricted split and grant narratives.
    designation        TEXT,
    restricted         BOOLEAN,
    -- Donor-covered processing fee, for true-net revenue analysis.
    fee_covered        BOOLEAN,
    fee_covered_amount NUMERIC(12, 2),
    -- Refund tracking, so reversed gifts don't overstate revenue.
    refunded           BOOLEAN,
    refunded_amount    NUMERIC(12, 2),
    refunded_at        DATE,
    -- Gift channel (web, event, text-to-give) + link to the recurring plan.
    channel            TEXT,
    recurring_plan_id  TEXT,
    loaded_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_funraise_txn_at        ON funraise.fact_transactions (transaction_at);
CREATE INDEX IF NOT EXISTS ix_funraise_txn_date      ON funraise.fact_transactions (transaction_date);
CREATE INDEX IF NOT EXISTS ix_funraise_txn_supporter ON funraise.fact_transactions (supporter_id);
CREATE INDEX IF NOT EXISTS ix_funraise_txn_campaign  ON funraise.fact_transactions (campaign_id);

-- Recurring giving plans. subscription_id is the Funraise PK.
CREATE TABLE IF NOT EXISTS funraise.fact_subscriptions (
    subscription_id  TEXT PRIMARY KEY,
    supporter_id     TEXT,
    campaign_id      TEXT,
    amount           NUMERIC(12, 2),
    frequency        TEXT,   -- monthly, annual, ...
    status           TEXT,   -- active, churned, paused
    started_at       DATE,
    canceled_at      DATE,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
