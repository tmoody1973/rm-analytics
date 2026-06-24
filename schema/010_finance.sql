-- 010_finance.sql — Finance KPIs, sourced from the manually-maintained Google
-- Sheet ("financial" tab) via the Apps Script "Sync to Neon" button ->
-- rm-data-loader /webhook/sheet -> load_finance_sheet.
--
-- The sheet is a wide KPI dashboard: one row per indicator, one column per month.
-- We unpivot it into long form so it is queryable — one row per (month, indicator).
-- Values are YTD / cumulative where the indicator name says so. Percents are stored
-- as the percent number (e.g. 36.67), counts as the count (e.g. 2756 donors).
--
-- This intentionally models what the sheet actually contains. A finer-grained
-- revenue-by-category/brand model (see CLAUDE.md) can be added later if/when a
-- more detailed source exists.

CREATE SCHEMA IF NOT EXISTS finance;

CREATE TABLE IF NOT EXISTS finance.fact_kpi_monthly (
    month      DATE        NOT NULL,
    indicator  TEXT        NOT NULL,
    value      NUMERIC(16, 4),
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (month, indicator)
);

CREATE INDEX IF NOT EXISTS ix_finance_kpi_month ON finance.fact_kpi_monthly (month);
