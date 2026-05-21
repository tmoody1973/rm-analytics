-- ============================================================================
-- 003_wms_facts_revision.sql
-- Revises the wms streaming fact tables to the grains we actually report on.
--
-- WHAT THIS DOES
--   1. Replaces wms.fact_daily_geo    -> wms.fact_monthly_geo
--   2. Replaces wms.fact_daily_device -> wms.fact_monthly_device
--   3. Adds      wms.fact_weekly_cume (new)
--
-- WHY
--   * CUME is non-additive: you cannot sum daily cume to get a month, because the
--     same listener counted on two days is one unique person for the month. So a
--     "daily geo/device" table can't be rolled up correctly anyway — the only
--     honest figures come straight from Triton at the grain you want to report.
--   * Geo and device breakdowns are consumed monthly (development geo views,
--     underwriting device-split decks), not daily. Pulling them at monthly grain
--     keeps the cume/unique numbers correct and cuts row volume dramatically.
--   * Weekly cume is added for underwriting reporting — flight windows and spot
--     pacing are discussed week-over-week, a grain we didn't have between daily
--     (Q2a) and monthly (Q2c) cume.
--
-- SAFE TO RUN: both dropped tables are empty (no backfill has run yet), so no
-- data is lost. Idempotent via DROP TABLE IF EXISTS / CREATE TABLE IF NOT EXISTS.
-- Dropping a table also drops its indexes; they are recreated below.
--
-- Apply with:  psql "$DATABASE_URL" -f schema/003_wms_facts_revision.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Monthly geography (replaces daily geography).
--    Grain: one row per (station, month, country, region, city).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS wms.fact_daily_geo;

CREATE TABLE IF NOT EXISTS wms.fact_monthly_geo (
    station_code  TEXT    NOT NULL,
    month_start   DATE    NOT NULL,            -- first day of the reporting month
    country       TEXT    NOT NULL DEFAULT '',
    region        TEXT    NOT NULL DEFAULT '',
    city          TEXT    NOT NULL DEFAULT '',
    aas           NUMERIC,                     -- Average Active Sessions
    tlh           NUMERIC,                     -- Total Listening Hours
    cume          NUMERIC,                     -- Cume (non-additive)
    ss            INTEGER,                     -- Sessions Started
    tsl_minutes   NUMERIC,                     -- Time Spent Listening, parsed from "HH:MM"
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, month_start, country, region, city)
);

CREATE INDEX IF NOT EXISTS idx_fact_monthly_geo_month_start
    ON wms.fact_monthly_geo (month_start);


-- ----------------------------------------------------------------------------
-- 2. Monthly device / platform (replaces daily device).
--    Grain: one row per (station, month, device_category, os, player).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS wms.fact_daily_device;

CREATE TABLE IF NOT EXISTS wms.fact_monthly_device (
    station_code     TEXT    NOT NULL,
    month_start      DATE    NOT NULL,         -- first day of the reporting month
    device_category  TEXT    NOT NULL DEFAULT '',
    os               TEXT    NOT NULL DEFAULT '',
    player           TEXT    NOT NULL DEFAULT '',
    aas              NUMERIC,                  -- Average Active Sessions
    tlh              NUMERIC,                  -- Total Listening Hours
    cume             NUMERIC,                  -- Cume (non-additive)
    ss               INTEGER,                  -- Sessions Started
    tsl_minutes      NUMERIC,                  -- Time Spent Listening, parsed from "HH:MM"
    loaded_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, month_start, device_category, os, player)
);

CREATE INDEX IF NOT EXISTS idx_fact_monthly_device_month_start
    ON wms.fact_monthly_device (month_start);


-- ----------------------------------------------------------------------------
-- 3. Weekly cume (new) — for underwriting flight/pacing reporting.
--    Grain: one row per (station, week). Cume is non-additive across weeks.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.fact_weekly_cume (
    station_code  TEXT    NOT NULL,
    week_start    DATE    NOT NULL,            -- Monday of the reporting week
    aas           NUMERIC,                     -- Average Active Sessions
    tlh           NUMERIC,                     -- Total Listening Hours
    cume          NUMERIC,                     -- Cume (non-additive)
    ss            INTEGER,                     -- Sessions Started
    tsl_minutes   NUMERIC,                     -- Time Spent Listening, parsed from "HH:MM"
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, week_start)
);

CREATE INDEX IF NOT EXISTS idx_fact_weekly_cume_week_start
    ON wms.fact_weekly_cume (week_start);
