-- ============================================================================
-- 002_wms_facts.sql
-- Triton WMS streaming fact tables (queries Q1, Q2a, Q2c, Q3, Q4).
--
-- Column names follow the Triton export conventions in CLAUDE.md:
--   * "Date Hour" is split into `date` (DATE) + `hour` (INT 0-23).
--   * TSL ("HH:MM") is parsed to `tsl_minutes` (NUMERIC).
--   * `station_code` holds the resolved internal code (RM88, HYFIN, RM414, RLR),
--     stored as plain TEXT with NO hard FK to dim.stations — source schemas are
--     sacred and a daily load must never fail on a not-yet-mapped station.
--
-- Each fact table has a composite primary key at its natural grain (so loader
-- ON CONFLICT upserts line up), a `loaded_at` audit column (never in the PK),
-- and an index on its time column. Idempotent: safe to re-run.
--
-- Text columns that participate in a composite PK are NOT NULL DEFAULT '' so
-- Triton's empty-string coercion can't produce a NULL PK component.
--
-- Apply with:  psql "$DATABASE_URL" -f schema/002_wms_facts.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Q1 — Hourly listening.
-- Triton cols: Station, Date Hour, AAS, TLH, CUME, SS, TSL.
-- Grain: one row per (station, date, hour).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.fact_hourly_listening (
    station_code  TEXT    NOT NULL,
    date          DATE    NOT NULL,
    hour          INT     NOT NULL,         -- 0-23, parsed from "Date Hour"
    aas           NUMERIC,                  -- Average Active Sessions
    tlh           NUMERIC,                  -- Total Listening Hours
    cume          NUMERIC,                  -- Cume (non-additive)
    ss            INTEGER,                  -- Sessions Started
    tsl_minutes   NUMERIC,                  -- Time Spent Listening, parsed from "HH:MM"
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, date, hour)
);

CREATE INDEX IF NOT EXISTS idx_fact_hourly_listening_date
    ON wms.fact_hourly_listening (date);


-- ----------------------------------------------------------------------------
-- Q2a — Daily cume.
-- Triton cols: Station, Date, Unique Listeners, TLH, ATL, CUME.
-- Grain: one row per (station, date). Cume is non-additive.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.fact_daily_cume (
    station_code      TEXT    NOT NULL,
    date              DATE    NOT NULL,
    unique_listeners  INTEGER,
    tlh               NUMERIC,              -- Total Listening Hours
    atl               NUMERIC,              -- Average Time Listening
    cume              NUMERIC,              -- Cume (non-additive)
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, date)
);

CREATE INDEX IF NOT EXISTS idx_fact_daily_cume_date
    ON wms.fact_daily_cume (date);


-- ----------------------------------------------------------------------------
-- Q2c — Monthly cume.
-- Triton cols: Station, Month, Unique Listeners, TLH, CUME.
-- `month` is stored as `month_start` (DATE = first day of the month).
-- Grain: one row per (station, month_start).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.fact_monthly_cume (
    station_code      TEXT    NOT NULL,
    month_start       DATE    NOT NULL,     -- first day of the reporting month
    unique_listeners  INTEGER,
    tlh               NUMERIC,              -- Total Listening Hours
    cume              NUMERIC,              -- Cume (non-additive)
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, month_start)
);

CREATE INDEX IF NOT EXISTS idx_fact_monthly_cume_month_start
    ON wms.fact_monthly_cume (month_start);


-- ----------------------------------------------------------------------------
-- Q3 — Daily geography.
-- Triton cols: Station, Date, Country, Region, City, Sessions Started, TLH,
--              Unique Listeners.
-- Grain: one row per (station, date, country, region, city).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.fact_daily_geo (
    station_code      TEXT    NOT NULL,
    date              DATE    NOT NULL,
    country           TEXT    NOT NULL DEFAULT '',
    region            TEXT    NOT NULL DEFAULT '',
    city              TEXT    NOT NULL DEFAULT '',
    sessions_started  INTEGER,
    tlh               NUMERIC,              -- Total Listening Hours
    unique_listeners  INTEGER,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, date, country, region, city)
);

CREATE INDEX IF NOT EXISTS idx_fact_daily_geo_date
    ON wms.fact_daily_geo (date);


-- ----------------------------------------------------------------------------
-- Q4 — Daily device / platform.
-- Triton cols: Station, Date, Device Category, OS, Player, Sessions Started,
--              TLH, Unique Listeners.
-- Grain: one row per (station, date, device_category, os, player).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.fact_daily_device (
    station_code      TEXT    NOT NULL,
    date              DATE    NOT NULL,
    device_category   TEXT    NOT NULL DEFAULT '',
    os                TEXT    NOT NULL DEFAULT '',
    player            TEXT    NOT NULL DEFAULT '',
    sessions_started  INTEGER,
    tlh               NUMERIC,              -- Total Listening Hours
    unique_listeners  INTEGER,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_code, date, device_category, os, player)
);

CREATE INDEX IF NOT EXISTS idx_fact_daily_device_date
    ON wms.fact_daily_device (date);
