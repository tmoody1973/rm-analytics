-- 009_email_esp.sql — Mailchimp (email service provider) source tables.
--
-- Newsletters for Radio Milwaukee (88Nine), GWML, and HYFIN. Populated by
-- Coupler.io (Mailchimp -> Coupler -> Neon).
--
-- Join key back to dim.brand_channels: list_id -> platform='mailchimp_list'.
-- Source schema mirrors Mailchimp/Coupler output. loaded_at is audit only.

CREATE SCHEMA IF NOT EXISTS email_esp;

-- ---------------------------------------------------------------------------
-- email_esp.dim_lists
-- Audience/list metadata. Grain: (list_id). Each list maps to a station via
-- dim.brand_channels (a list ~ a brand's newsletter).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_esp.dim_lists (
    list_id        TEXT        NOT NULL,
    list_name      TEXT,
    member_count   BIGINT      NOT NULL DEFAULT 0,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (list_id)
);

-- ---------------------------------------------------------------------------
-- email_esp.fact_campaign_sends
-- One row per sent campaign. Grain: (campaign_id).
-- Mailchimp reports both total and unique opens/clicks — keep both.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_esp.fact_campaign_sends (
    campaign_id     TEXT        NOT NULL,
    list_id         TEXT,
    send_time       TIMESTAMPTZ,
    campaign_title  TEXT,
    subject_line    TEXT,
    emails_sent     BIGINT      NOT NULL DEFAULT 0,
    unique_opens    BIGINT      NOT NULL DEFAULT 0,
    opens_total     BIGINT      NOT NULL DEFAULT 0,
    unique_clicks   BIGINT      NOT NULL DEFAULT 0,
    clicks_total    BIGINT      NOT NULL DEFAULT 0,
    unsubscribes    BIGINT      NOT NULL DEFAULT 0,
    hard_bounces    BIGINT      NOT NULL DEFAULT 0,
    soft_bounces    BIGINT      NOT NULL DEFAULT 0,
    open_rate       NUMERIC     NOT NULL DEFAULT 0,
    click_rate      NUMERIC     NOT NULL DEFAULT 0,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (campaign_id)
);

-- ---------------------------------------------------------------------------
-- email_esp.fact_subscriber_events
-- List growth by day. Grain: (date, list_id).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_esp.fact_subscriber_events (
    date          DATE        NOT NULL,
    list_id       TEXT        NOT NULL,
    opt_ins       BIGINT      NOT NULL DEFAULT 0,
    opt_outs      BIGINT      NOT NULL DEFAULT 0,
    cleaned       BIGINT      NOT NULL DEFAULT 0,
    net_change    BIGINT      NOT NULL DEFAULT 0,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, list_id)
);

CREATE INDEX IF NOT EXISTS ix_email_campaign_list_send
    ON email_esp.fact_campaign_sends (list_id, send_time);
CREATE INDEX IF NOT EXISTS ix_email_subevents_list_date
    ON email_esp.fact_subscriber_events (list_id, date);
