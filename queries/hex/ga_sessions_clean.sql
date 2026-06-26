-- Hex query: clean GA4 sessions (both brands), with station labels.
--
-- Reads Coupler's raw staging table DIRECTLY. This is deliberate: Coupler's
-- "Replace" import mode drops + recreates ga.stg_sessions_daily on every run,
-- which cascade-drops any DB view built on top of it. The table itself always
-- exists with the same name, so querying it from Hex is the robust pattern.
-- The column renaming / station join lives here in Hex, not in the database.
--
-- property_id -> station via dim.brand_channels (platform='ga4').

select
    s.report__date                                                       as date,
    bc.station_code,
    s.account__property_id                                               as property_id,
    coalesce(nullif(s.session__session_source___medium, ''), '(not set)') as source_medium,
    s.engagement__sessions::bigint                                       as sessions,
    s.acquisition__total_users::bigint                                   as users,
    s.acquisition__new_users::bigint                                     as new_users,
    s.engagement__engaged_sessions::bigint                               as engaged_sessions,
    s.engagement__views::bigint                                          as page_views,
    s.session__average_session_duration                                  as avg_session_duration,
    s.performance__bounce_rate                                           as bounce_rate
from ga.stg_sessions_daily s
left join dim.brand_channels bc
  on bc.platform = 'ga4'
 and bc.handle_or_id = s.account__property_id
order by date desc, sessions desc;
