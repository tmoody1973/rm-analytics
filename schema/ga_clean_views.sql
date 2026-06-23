-- ga_clean_views.sql — curated views over Coupler's raw GA4 staging tables.
--
-- ARCHITECTURE (decided 2026-06-23):
--   Coupler.io writes each GA4 report into a raw staging table it owns
--   (ga.stg_*), with verbose snake_case column names (account__property_id,
--   report__date, engagement__sessions, …) and "Replace" mode (full reload
--   each run). The clean layer below is a set of VIEWS that rename/cast those
--   columns into the project's tidy shape — always live, no ETL job, never out
--   of sync. These replace the placeholder TABLEs from 008_ga.sql.
--
--   Join key to dim.brand_channels: property_id (platform='ga4').
--   GROUP BY collapses the rare NULL-vs-'(not set)' source/medium duplicate;
--   rate metrics are session-weighted so the merge stays correct.
--
-- Add one view per report-type as its Coupler dataflow lands a stg_* table.

-- Sessions / acquisition (stg_sessions_daily) — first one wired + verified.
DROP TABLE IF EXISTS ga.fact_sessions_daily;
CREATE OR REPLACE VIEW ga.fact_sessions_daily AS
SELECT
    report__date                                                        AS date,
    account__property_id                                                AS property_id,
    COALESCE(NULLIF(session__session_source___medium, ''), '(not set)') AS source_medium,
    SUM(engagement__sessions)::bigint                                   AS sessions,
    SUM(acquisition__total_users)::bigint                               AS users,
    SUM(acquisition__new_users)::bigint                                 AS new_users,
    SUM(engagement__engaged_sessions)::bigint                           AS engaged_sessions,
    SUM(engagement__views)::bigint                                      AS page_views,
    CASE WHEN SUM(engagement__sessions) > 0
         THEN SUM(session__average_session_duration * engagement__sessions)
              / SUM(engagement__sessions)
         ELSE 0 END                                                     AS avg_session_duration,
    CASE WHEN SUM(engagement__sessions) > 0
         THEN SUM(performance__bounce_rate * engagement__sessions)
              / SUM(engagement__sessions)
         ELSE 0 END                                                     AS bounce_rate
FROM ga.stg_sessions_daily
GROUP BY report__date, account__property_id,
         COALESCE(NULLIF(session__session_source___medium, ''), '(not set)');
