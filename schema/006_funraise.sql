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
CREATE TABLE IF NOT EXISTS funraise.dim_supporters (
    supporter_id      TEXT PRIMARY KEY,
    first_name        TEXT,
    last_name         TEXT,
    email             TEXT,
    city              TEXT,
    state             TEXT,
    postal_code       TEXT,
    country           TEXT,
    first_donation_at DATE,
    lifetime_total    NUMERIC(12, 2),
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
    transaction_id   TEXT PRIMARY KEY,
    supporter_id     TEXT,
    campaign_id      TEXT,
    transaction_date DATE,
    amount           NUMERIC(12, 2),
    fee              NUMERIC(12, 2),
    net              NUMERIC(12, 2),
    currency         TEXT,
    payment_method   TEXT,
    recurring        BOOLEAN,
    status           TEXT,
    utm_source       TEXT,
    utm_medium       TEXT,
    utm_campaign     TEXT,
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
