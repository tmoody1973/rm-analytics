-- ============================================================================
-- 001_initial.sql
-- Radio Milwaukee Analytics Pipeline — foundational migration.
--
-- Creates every schema-per-source namespace plus the shared `dim` dimensions.
-- Idempotent: safe to re-run. All DDL uses IF NOT EXISTS; all seed data uses
-- ON CONFLICT so reapplying never errors and corrections propagate.
--
-- Apply with:  psql "$DATABASE_URL" -f schema/001_initial.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Schemas (schema-per-source). Source schemas mirror exactly what each vendor
-- sends and are read-only after load; `marts` is where cross-source joins live.
-- ----------------------------------------------------------------------------

-- Streaming
CREATE SCHEMA IF NOT EXISTS wms;            -- Triton streaming facts

-- Audience / web / social
CREATE SCHEMA IF NOT EXISTS ga;             -- Google Analytics 4
CREATE SCHEMA IF NOT EXISTS meta_organic;   -- Facebook + Instagram organic
CREATE SCHEMA IF NOT EXISTS meta_ads;       -- Facebook + Instagram paid (separate API)
CREATE SCHEMA IF NOT EXISTS linkedin;       -- LinkedIn page analytics (future)
CREATE SCHEMA IF NOT EXISTS youtube;        -- YouTube channel + video (future)
CREATE SCHEMA IF NOT EXISTS tiktok;         -- TikTok organic (future)

-- Donations / CRM
CREATE SCHEMA IF NOT EXISTS funraise;       -- Funraise transactions, supporters

-- Email
CREATE SCHEMA IF NOT EXISTS email_esp;      -- ESP campaign sends, opens, clicks

-- Revenue & finance
CREATE SCHEMA IF NOT EXISTS finance;        -- Revenue actuals, budgets, expenses
CREATE SCHEMA IF NOT EXISTS underwriting;   -- Underwriting contracts + delivery
CREATE SCHEMA IF NOT EXISTS grants;         -- Grant pipeline, awards

-- Events / earned
CREATE SCHEMA IF NOT EXISTS events;         -- Event ticketing, attendance, revenue

-- Shared + derived
CREATE SCHEMA IF NOT EXISTS dim;            -- Shared dimensions
CREATE SCHEMA IF NOT EXISTS marts;          -- Cross-source views for dashboards


-- ----------------------------------------------------------------------------
-- dim.stations — the four streaming brands.
-- `code` is the internal station_code used as a join key everywhere.
-- `mount_point` holds the raw Triton "Station" string each brand maps from.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim.stations (
    station_id   SERIAL PRIMARY KEY,
    code         TEXT NOT NULL UNIQUE,
    brand_name   TEXT NOT NULL,
    format       TEXT,
    mount_point  TEXT
);

INSERT INTO dim.stations (code, brand_name, format, mount_point) VALUES
    ('RM88',  '88Nine Radio Milwaukee', 'AAA / Discovery',       'WYMSFM'),
    ('HYFIN', 'HYFIN',                   'Urban Alternative',     'WYMSHD2'),
    ('RM414', '414 Music',               'Local Music',           '414 Music'),
    ('RLR',   'Rhythm Lab Radio',        'Genre-Fluid Specialty', 'Rhythm Lab Radio 24/7')
ON CONFLICT (code) DO UPDATE SET
    brand_name  = EXCLUDED.brand_name,
    format      = EXCLUDED.format,
    mount_point = EXCLUDED.mount_point;


-- ----------------------------------------------------------------------------
-- dim.dayparts — five standard dayparts.
-- Hour ranges are [start_hour, end_hour): start inclusive, end exclusive.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim.dayparts (
    daypart_id  SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    start_hour  INT  NOT NULL,
    end_hour    INT  NOT NULL
);

INSERT INTO dim.dayparts (name, start_hour, end_hour) VALUES
    ('Overnight',  0,  5),
    ('Morning',    5,  10),
    ('Midday',     10, 15),
    ('Afternoon',  15, 19),
    ('Evening',    19, 24)
ON CONFLICT (name) DO NOTHING;


-- ----------------------------------------------------------------------------
-- dim.dates — calendar table, 2020-01-01 through 2030-12-31.
-- day_of_week uses ISODOW (1 = Monday … 7 = Sunday).
-- fiscal_year = calendar year for now (verify Radio Milwaukee's real FY later).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim.dates (
    date         DATE PRIMARY KEY,
    year         INT NOT NULL,
    quarter      INT NOT NULL,
    month        INT NOT NULL,
    week         INT NOT NULL,
    day_of_week  INT NOT NULL,
    fiscal_year  INT NOT NULL
);

INSERT INTO dim.dates (date, year, quarter, month, week, day_of_week, fiscal_year)
SELECT
    d::date                       AS date,
    EXTRACT(YEAR    FROM d)::int  AS year,
    EXTRACT(QUARTER FROM d)::int  AS quarter,
    EXTRACT(MONTH   FROM d)::int  AS month,
    EXTRACT(WEEK    FROM d)::int  AS week,
    EXTRACT(ISODOW  FROM d)::int  AS day_of_week,
    EXTRACT(YEAR    FROM d)::int  AS fiscal_year
FROM generate_series('2020-01-01'::date, '2030-12-31'::date, INTERVAL '1 day') AS g(d)
ON CONFLICT (date) DO NOTHING;


-- ----------------------------------------------------------------------------
-- dim.brand_channels — maps each social handle, GA property, email list, and
-- ad account to a station_code. CRITICAL for cross-source joins. Seeded later
-- (left empty here on purpose).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim.brand_channels (
    channel_id    SERIAL PRIMARY KEY,
    station_code  TEXT NOT NULL REFERENCES dim.stations (code),
    platform      TEXT NOT NULL,   -- e.g. fb_page, ig_profile, meta_ad_acct, ga_property, email_list
    handle_or_id  TEXT NOT NULL,
    display_name  TEXT,
    UNIQUE (platform, handle_or_id)
);
