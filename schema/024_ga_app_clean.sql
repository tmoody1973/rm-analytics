-- schema/024_ga_app_clean.sql
-- One clean view over the GA4 app tables, because three things about the raw
-- staging shape will produce wrong numbers if a consumer reads it directly.
--
-- 1. RADIO MILWAUKEE'S APP SPANS TWO GA PROPERTIES.
--    It is ONE app. In Sep 2025 its Android traffic migrated from property
--    183736836 ("radiomke App") to 447654700 ("radio-milwaukee-app-2024"):
--
--      month     183736836/And   447654700/And
--      2025-08           5,385               0
--      2025-09             909           4,370   <- handoff month
--      2025-10             201           5,313
--      2026-06              72           6,319
--
--    SUMMING them is correct, not double-counting: a session is recorded by
--    exactly one property (whichever app build the user is running), and the
--    summed series is continuous across the handoff (Aug 5,385 -> Sep 5,279).
--    Dropping either property loses real traffic — 447654700 carries ~all of
--    today's Android, and 183736836 carries 100% of iOS and all pre-Sep history.
--    So the view groups by station_code and lets both properties add up.
--
-- 2. iOS EXISTS ON ONLY ONE PROPERTY.
--    447654700 has zero iOS rows, ever. HYFIN (347788143) has zero iOS rows too.
--    Any "iOS vs Android" split must come from this view, not from a property.
--
-- 3. active_users IS NOT ADDITIVE.
--    Summing daily active users over June for radiomke App gives 6,629 — that is
--    the same people counted once per day, not 6,629 humans. Same trap as CUME
--    (see CLAUDE.md). `sessions`, `views` and `new_users` ARE additive; treat
--    `active_users` as a DAILY value only — average it, never sum it across days.
--
-- Brand comes from dim.brand_channels (platform='ga4_app'), so a new app property
-- is onboarded by inserting one row there, not by editing this view.
--
-- Reads ga.stg_app_engagement_daily, which is the only table carrying iOS.
-- ga.stg_app_acquisition_daily is deliberately NOT used: it holds no rows for
-- property 183736836 and no iOS rows at all, so its new_users would silently be
-- "Android, post-Sep-2025 only". Fix that Coupler flow before trusting it.

CREATE OR REPLACE VIEW ga.v_app_daily AS
SELECT
    bc.station_code,
    e.report__date                              AS date,
    e.audience__platform                        AS platform,
    -- additive: safe to sum across days, platforms and properties
    sum(e.engagement__sessions)::bigint         AS sessions,
    sum(e.engagement__views)::bigint            AS views,
    sum(e.engagement__user_engagement)::bigint  AS engagement_seconds,
    sum(e.acquisition__new_users)::bigint       AS new_users,
    -- NOT additive across DAYS. Summing across the two RM properties on one day is
    -- safe (a user runs one app build), but rolling this up to a month means
    -- "person-days", not people. Average it per day, or count nothing.
    sum(e.acquisition__active_users)::bigint    AS active_users_daily
FROM ga.stg_app_engagement_daily e
JOIN dim.brand_channels bc
  ON bc.platform = 'ga4_app'
 AND bc.handle_or_id = e.account__property_id
GROUP BY 1, 2, 3;

COMMENT ON VIEW ga.v_app_daily IS
  'Daily GA4 mobile-app metrics per (station_code, date, platform). Radio Milwaukee''s '
  'two GA properties are summed — one app, migrated Sep 2025, no double-count. '
  'sessions/views/new_users are additive; active_users_daily is a DAILY value and must '
  'NEVER be summed across days (that yields person-days, not people) — average it.';

GRANT SELECT ON ga.v_app_daily TO rm_readonly;
