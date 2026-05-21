-- ============================================================================
-- 004_wms_facts_revision_geo_device.sql
-- Re-shapes the monthly geo and device fact tables to match what Triton ACTUALLY
-- exports for Q3 and Q4 (verified against the real export, not the planned spec).
--
-- WHAT THIS DOES
--   1. Rebuilds wms.fact_monthly_geo    with geography = City + DMA (no Country/Region)
--   2. Rebuilds wms.fact_monthly_device with device = family + device + player (no OS)
--
-- WHY
--   * Q3 geo: Triton's monthly geo tier delivers (Station, Month, City, DMA) plus
--     the 5 metrics. It does NOT break out Country or Region, so those columns in
--     migration 003 were never going to be populated. DMA (Nielsen market) is the
--     dimension that actually matters for underwriting/audience reporting anyway.
--   * Q4 device: Triton delivers (Station, Month, Device family, Device, Player)
--     plus the 5 metrics. There is no separate OS column. `device_category`→
--     `device_family`, and `os`→`device` (a SEMANTIC change: this column now holds
--     concrete device names like "Amazon Echo", "iPhone", "Chromecast" — not OS names).
--
-- SAFE TO RUN: both tables are empty (no backfill has run yet), so no data is lost.
-- Idempotent via DROP TABLE IF EXISTS / CREATE TABLE IF NOT EXISTS. Dropping a
-- table also drops its index; it is recreated below.
--
-- Apply with:  psql "$DATABASE_URL" -f schema/004_wms_facts_revision_geo_device.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Monthly geography — City + DMA (replaces the Country/Region version).
--    Grain: one row per (station, month, city, dma).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS wms.fact_monthly_geo;

CREATE TABLE IF NOT EXISTS wms.fact_monthly_geo (
    station_code  TEXT    NOT NULL,
    month_start   DATE    NOT NULL,            -- first day of the reporting month
    city          TEXT    NOT NULL DEFAULT '',
    dma           TEXT    NOT NULL DEFAULT '',  -- Nielsen Designated Market Area
    aas           NUMERIC,                     -- Average Active Sessions
    tlh           NUMERIC,                     -- Total Listening Hours
    cume          NUMERIC,                     -- Cume (non-additive)
    ss            INTEGER,                     -- Sessions Started
    tsl_minutes   NUMERIC,                     -- Time Spent Listening, parsed from "HH:MM"
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, month_start, city, dma)
);

CREATE INDEX IF NOT EXISTS idx_fact_monthly_geo_month_start
    ON wms.fact_monthly_geo (month_start);


-- ----------------------------------------------------------------------------
-- 2. Monthly device / platform — family + device + player (replaces the OS version).
--    Grain: one row per (station, month, device_family, device, player).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS wms.fact_monthly_device;

CREATE TABLE IF NOT EXISTS wms.fact_monthly_device (
    station_code   TEXT    NOT NULL,
    month_start    DATE    NOT NULL,           -- first day of the reporting month
    device_family  TEXT    NOT NULL DEFAULT '',-- e.g. "Mobile", "Smart Speaker", "Desktop"
    device         TEXT    NOT NULL DEFAULT '',-- concrete device, e.g. "Amazon Echo", "iPhone", "Chromecast"
    player         TEXT    NOT NULL DEFAULT '',
    aas            NUMERIC,                     -- Average Active Sessions
    tlh            NUMERIC,                     -- Total Listening Hours
    cume           NUMERIC,                     -- Cume (non-additive)
    ss             INTEGER,                     -- Sessions Started
    tsl_minutes    NUMERIC,                     -- Time Spent Listening, parsed from "HH:MM"
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, month_start, device_family, device, player)
);

CREATE INDEX IF NOT EXISTS idx_fact_monthly_device_month_start
    ON wms.fact_monthly_device (month_start);
