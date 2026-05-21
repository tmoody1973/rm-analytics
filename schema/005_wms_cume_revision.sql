-- ============================================================================
-- 005_wms_cume_revision.sql
-- Aligns the daily (Q2a) and monthly (Q2c) cume tables to Triton's real export.
--
-- WHY
--   Verified against the actual exports: Triton's daily and monthly cume tiers
--   deliver the SAME 5-metric set as every other query — (AAS, TLH, CUME, SS, TSL).
--   Migration 002 built fact_daily_cume / fact_monthly_cume with a speculative
--   (unique_listeners, atl) shape that Triton does NOT export, so those columns
--   would never populate and the loaders couldn't map cleanly. This re-shapes both
--   tables to the 5-metric form already used by fact_weekly_cume / geo / device.
--
-- SAFE TO RUN: both tables are empty (0 rows — no backfill yet), so no data is lost.
-- Idempotent via DROP TABLE IF EXISTS / CREATE TABLE IF NOT EXISTS. Dropping a
-- table also drops its index; it is recreated below.
--
-- Apply with:  psql "$DATABASE_URL" -f schema/005_wms_cume_revision.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q2a — Daily cume. Grain: one row per (station, date).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS wms.fact_daily_cume;

CREATE TABLE IF NOT EXISTS wms.fact_daily_cume (
    station_code  TEXT    NOT NULL,
    date          DATE    NOT NULL,
    aas           NUMERIC,                     -- Average Active Sessions
    tlh           NUMERIC,                     -- Total Listening Hours
    cume          NUMERIC,                     -- Cume (non-additive)
    ss            INTEGER,                     -- Sessions Started
    tsl_minutes   NUMERIC,                     -- Time Spent Listening, parsed from "HH:MM"
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, date)
);

CREATE INDEX IF NOT EXISTS idx_fact_daily_cume_date
    ON wms.fact_daily_cume (date);


-- ----------------------------------------------------------------------------
-- Q2c — Monthly cume. Grain: one row per (station, month_start).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS wms.fact_monthly_cume;

CREATE TABLE IF NOT EXISTS wms.fact_monthly_cume (
    station_code  TEXT    NOT NULL,
    month_start   DATE    NOT NULL,            -- first day of the reporting month
    aas           NUMERIC,                     -- Average Active Sessions
    tlh           NUMERIC,                     -- Total Listening Hours
    cume          NUMERIC,                     -- Cume (non-additive)
    ss            INTEGER,                     -- Sessions Started
    tsl_minutes   NUMERIC,                     -- Time Spent Listening, parsed from "HH:MM"
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, month_start)
);

CREATE INDEX IF NOT EXISTS idx_fact_monthly_cume_month_start
    ON wms.fact_monthly_cume (month_start);
