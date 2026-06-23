-- 008_ga.sql — Google Analytics 4 source tables.
--
-- Populated by Coupler.io (GA4 -> Coupler -> Neon). One GA4 property per
-- website: Radio Milwaukee (88Nine) and HYFIN. property_id is the join key
-- back to dim.brand_channels (platform='ga4').
--
-- DESIGN: GA4 reports are split into focused fact tables — one dimension set
-- each — instead of one wide table. Combining acquisition × geo × device in a
-- single report explodes cardinality and trips GA4 sampling; it also maps
-- cleanly to Coupler (one importer = one report = one table here).
--
-- Source schema mirrors GA4/Coupler. No cross-source joins — those live in
-- marts. loaded_at is audit only, never part of a PK.

-- ---------------------------------------------------------------------------
-- ga.fact_sessions_daily — ACQUISITION
-- Grain: (date, property, source/medium). The traffic-by-channel base.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ga.fact_sessions_daily (
    date                  DATE        NOT NULL,
    property_id           TEXT        NOT NULL,
    source_medium         TEXT        NOT NULL DEFAULT '(not set)',
    sessions              BIGINT      NOT NULL DEFAULT 0,
    users                 BIGINT      NOT NULL DEFAULT 0,
    new_users             BIGINT      NOT NULL DEFAULT 0,
    engaged_sessions      BIGINT      NOT NULL DEFAULT 0,
    page_views            BIGINT      NOT NULL DEFAULT 0,
    avg_session_duration  NUMERIC     NOT NULL DEFAULT 0,
    bounce_rate           NUMERIC     NOT NULL DEFAULT 0,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, property_id, source_medium)
);

-- ---------------------------------------------------------------------------
-- ga.fact_geo_daily — GEOGRAPHY (region = US state, city)
-- Grain: (date, property, region, city). Replaces coarse country grain —
-- a Milwaukee station's web audience is ~all US, so state/city is what matters.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ga.fact_geo_daily (
    date          DATE        NOT NULL,
    property_id   TEXT        NOT NULL,
    region        TEXT        NOT NULL DEFAULT '(not set)',  -- US state
    city          TEXT        NOT NULL DEFAULT '(not set)',
    sessions      BIGINT      NOT NULL DEFAULT 0,
    users         BIGINT      NOT NULL DEFAULT 0,
    new_users     BIGINT      NOT NULL DEFAULT 0,
    page_views    BIGINT      NOT NULL DEFAULT 0,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, property_id, region, city)
);

-- ---------------------------------------------------------------------------
-- ga.fact_device_daily — DEVICE CATEGORY
-- Grain: (date, property, device_category). Feeds the Underwriting device-split
-- story and PD. device_category = desktop | mobile | tablet | smart tv.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ga.fact_device_daily (
    date            DATE        NOT NULL,
    property_id     TEXT        NOT NULL,
    device_category TEXT        NOT NULL DEFAULT '(not set)',
    sessions        BIGINT      NOT NULL DEFAULT 0,
    users           BIGINT      NOT NULL DEFAULT 0,
    new_users       BIGINT      NOT NULL DEFAULT 0,
    page_views      BIGINT      NOT NULL DEFAULT 0,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, property_id, device_category)
);

-- ---------------------------------------------------------------------------
-- ga.fact_pages_daily — CONTENT (top pages)
-- Grain: (date, property, page_path). Answers "what content performed" for PD.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ga.fact_pages_daily (
    date                  DATE        NOT NULL,
    property_id           TEXT        NOT NULL,
    page_path             TEXT        NOT NULL,
    page_views            BIGINT      NOT NULL DEFAULT 0,
    users                 BIGINT      NOT NULL DEFAULT 0,
    avg_engagement_time   NUMERIC     NOT NULL DEFAULT 0,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (date, property_id, page_path)
);

-- ---------------------------------------------------------------------------
-- ga.fact_events_daily — CUSTOM EVENTS
-- Grain: (date, property, event_name).
-- stream_start_click, donate_click, newsletter_signup, etc.
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
-- ga.dim_pages — page metadata (title lookup for page_path).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ga.dim_pages (
    property_id   TEXT        NOT NULL,
    page_path     TEXT        NOT NULL,
    page_title    TEXT,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (property_id, page_path)
);

-- Secondary indexes for dashboard query patterns.
CREATE INDEX IF NOT EXISTS ix_ga_sessions_property_date
    ON ga.fact_sessions_daily (property_id, date);
CREATE INDEX IF NOT EXISTS ix_ga_geo_property_date
    ON ga.fact_geo_daily (property_id, date);
CREATE INDEX IF NOT EXISTS ix_ga_device_property_date
    ON ga.fact_device_daily (property_id, date);
CREATE INDEX IF NOT EXISTS ix_ga_pages_property_date
    ON ga.fact_pages_daily (property_id, date);
CREATE INDEX IF NOT EXISTS ix_ga_events_property_date
    ON ga.fact_events_daily (property_id, date);
