-- 014_nielsen.sql — Nielsen PPM "Vital Signs Trend" reports (broadcast audience).
-- Source: Nielsen PDA Web export (manual, monthly, licensed/confidential data).
--
-- The export is a pivoted wide grid (metrics down rows, ~14 survey periods across
-- columns, grouped into sections: Estimates, P1, In-Tab, Detailed Daypart Trend,
-- Age/Gender/Ethnic composition). The loader UNPIVOTS it to this long fact table —
-- every (section, row-label, period) cell becomes one row. This generic long shape
-- holds all sections uniformly.
--
-- NOTE: Nielsen audience = BROADCAST (PPM panel estimate for the FM signal,
-- WYMS = RM88). Keep separate from streaming (wms.*); join only in marts.

CREATE SCHEMA IF NOT EXISTS nielsen;

CREATE TABLE IF NOT EXISTS nielsen.fact_vital_signs (
    station_code   TEXT NOT NULL,        -- mapped from report title (Radio Milwaukee -> RM88)
    market         TEXT,                  -- e.g. MILWAUKEE-RACINE
    demo           TEXT NOT NULL,         -- e.g. Persons 6+
    daypart        TEXT NOT NULL,         -- report-level daypart, e.g. M-Su 6a-12m
    period_label   TEXT NOT NULL,         -- Nielsen survey label: MAY25, HOL25, JAN26 ...
    period_date    DATE,                  -- first of month where parseable (NULL for HOL survey)
    section        TEXT NOT NULL,         -- Estimates / P1 Information / In-Tab / Detailed Daypart Trend / Age|Gender|Ethnic Composition
    metric         TEXT NOT NULL,         -- the row label (e.g. "AQH Share", "25-34", "M-F 6a-10a")
    value_numeric  NUMERIC,               -- normalized: HH:MM->minutes, 71%->71, "2.2 (18)"->2.2
    value_raw      TEXT,                  -- original cell, kept for fidelity
    rank           INT,                   -- market rank for AQH Share rows ("2.2 (18)" -> 18)
    unit           TEXT,                  -- share|persons|minutes|percent|rating|occasions|panelists
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (station_code, demo, daypart, period_label, section, metric)
);

CREATE INDEX IF NOT EXISTS ix_nielsen_vs_period  ON nielsen.fact_vital_signs (period_date);
CREATE INDEX IF NOT EXISTS ix_nielsen_vs_section ON nielsen.fact_vital_signs (section);
CREATE INDEX IF NOT EXISTS ix_nielsen_vs_metric  ON nielsen.fact_vital_signs (metric);
