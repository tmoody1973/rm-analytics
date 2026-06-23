-- 008_ga.sql — Google Analytics 4 source tables.
--
-- Populated by Coupler.io (GA4 -> Coupler -> Neon). One GA4 property per
-- website: Radio Milwaukee (88Nine) and HYFIN. property_id is the join key
-- back to dim.brand_channels (platform='ga4').
--
-- Source schema: mirrors what GA4/Coupler delivers. No cross-source joins
-- here — those live in marts. loaded_at is audit only, never part of a PK.

-- ---------------------------------------------------------------------------
-- ga.fact_sessions_daily
-- Grain: one row per (date, property, source/medium, country).
-- The acquisition + geo breakdown most dashboards start from.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ga.fact_sessions_daily (
    date                  DATE        NOT NULL,
    property_id           TEXT        NOT NULL,
    source_medium         TEXT        NOT NULL DEFAULT '(not set)',
    country               TEXT        NOT NULL DEFAULT '(not set)',
    sessions              BIGINT      NOT NULL DEFAULT 0,
    users                 BIGINT      NOT NULL DEFAULT 0,
    new_users             BIGINT      NOT NULL DEFAULT 0,
    engaged_sessions      BIGINT      NOT NULL DEFAULT 0,
    page_views            BIGINT      NOT NULL DEFAULT 0,
    avg_session_duration  NUMERIC     NOT NULL DEFAULT 0,
    bounce_rate           NUMERIC     NOT NULL DEFAULT 0,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, property_id, source_medium, country)
);

-- ---------------------------------------------------------------------------
-- ga.fact_events_daily
-- Grain: one row per (date, property, event_name).
-- Custom events: stream_start_click, donate_click, newsletter_signup, etc.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ga.fact_events_daily (
    date          DATE        NOT NULL,
    property_id   TEXT        NOT NULL,
    event_name    TEXT        NOT NULL,
    event_count   BIGINT      NOT NULL DEFAULT 0,
    total_users   BIGINT      NOT NULL DEFAULT 0,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, property_id, event_name)
);

-- ---------------------------------------------------------------------------
-- ga.dim_pages
-- Slowly-changing page metadata. Grain: (property, page_path).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ga.dim_pages (
    property_id   TEXT        NOT NULL,
    page_path     TEXT        NOT NULL,
    page_title    TEXT,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (property_id, page_path)
);

-- Helpful secondary indexes for the dashboard query patterns.
CREATE INDEX IF NOT EXISTS ix_ga_sessions_property_date
    ON ga.fact_sessions_daily (property_id, date);
CREATE INDEX IF NOT EXISTS ix_ga_events_property_date
    ON ga.fact_events_daily (property_id, date);
