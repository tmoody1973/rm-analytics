"""
Read-only dashboard data API. One GET returns all data the RM Executive Dashboard
web app needs, as JSON. Aggregate, non-PII data. SQL mirrors the validated Hex
dashboard cells; GA/Meta/Email read the populated stg_ tables (clean fact_ are empty).
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger(__name__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "loaders"))
from _common import get_db_connection  # noqa: E402

# Headline KPIs are defined once in the metric registry. Dashboard pulls them
# from there so there is ONE definition per metric (no duplicate SQL).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from metrics.registry import run_metric  # noqa: E402

# name -> SQL. Each returns rows the frontend renders directly.
QUERIES: dict[str, str] = {
    "header": """
        SELECT
          (SELECT value FROM finance.fact_kpi_monthly WHERE indicator='Revenue Actual YTD - Cash' ORDER BY month DESC LIMIT 1) AS revenue_ytd,
          (SELECT value FROM finance.fact_kpi_monthly WHERE indicator='Cash balance' ORDER BY month DESC LIMIT 1) AS cash_balance,
          (SELECT value FROM finance.fact_kpi_monthly WHERE indicator='Total donors YTD' ORDER BY month DESC LIMIT 1) AS total_donors,
          (SELECT value FROM finance.fact_kpi_monthly WHERE indicator='Surplus/deficit YTD' ORDER BY month DESC LIMIT 1) AS surplus_ytd,
          (SELECT value FROM finance.fact_kpi_monthly WHERE indicator='% to Revenue Annual Budget' ORDER BY month DESC LIMIT 1) AS pct_to_budget,
          (SELECT max(engagement__lifetime_followers) FROM meta_organic.stg_fb_page_daily) AS fb_followers,
          (SELECT coalesce(sum(stats_member_count),0) FROM email_esp.stg_lists) AS email_subscribers
    """,
    # exec_kpis is intentionally absent from QUERIES. The four headline KPIs
    # (active_donors, active_sustainers, sustainer_mrr, revenue_12mo) are now
    # fetched from the metric registry in dashboard_data() below. One definition.
    "revenue_trend": """
        SELECT date_trunc('month', transaction_date)::date::text AS month, round(sum(amount)) AS revenue
        FROM funraise.fact_transactions WHERE status='Complete' GROUP BY 1 ORDER BY 1
    """,
    "revenue_vs_budget": """
        SELECT month::text AS month,
               max(value) FILTER (WHERE indicator='Revenue Actual YTD - Cash') AS revenue_ytd,
               max(value) FILTER (WHERE indicator='Revenue Budget YTD') AS budget_ytd
        FROM finance.fact_kpi_monthly GROUP BY month ORDER BY month
    """,
    "revenue_mix": """
        SELECT month::text AS month,
               max(value) FILTER (WHERE indicator='Underwriting Revenue YTD') AS underwriting,
               max(value) FILTER (WHERE indicator='Individual Revenue YTD') AS individual,
               max(value) FILTER (WHERE indicator='Foundation Revenue YTD') AS foundation
        FROM finance.fact_kpi_monthly GROUP BY month ORDER BY month
    """,
    "sustainer_tracker": """
        SELECT round(sum(amount)) AS mrr, count(*) AS active_plans, 50000 AS target
        FROM funraise.fact_subscriptions WHERE status='Active' AND frequency='Monthly'
    """,
    "donor_retention": """
        WITH d AS (SELECT supporter_id, max(transaction_date) AS last_gift, min(transaction_date) AS first_gift
                   FROM funraise.fact_transactions WHERE status='Complete' GROUP BY 1)
        SELECT round(100.0 * count(*) FILTER (WHERE last_gift >= current_date - interval '12 months' AND first_gift < current_date - interval '12 months')
                     / nullif(count(*) FILTER (WHERE first_gift < current_date - interval '12 months'),0),1) AS retention_pct FROM d
    """,
    "nielsen_share": """
        SELECT station_code, value_numeric AS aqh_share, rank
        FROM nielsen.fact_vital_signs
        WHERE section='Estimates' AND metric='AQH Share'
          AND period_date=(SELECT max(period_date) FROM nielsen.fact_vital_signs WHERE metric='AQH Share')
        ORDER BY aqh_share DESC
    """,
    "nielsen_aqh_trend": """
        SELECT station_code, period_label, period_date::text AS period_date, value_numeric AS aqh_persons
        FROM nielsen.fact_vital_signs
        WHERE section='Estimates' AND metric='AQH Persons' AND period_date IS NOT NULL
        ORDER BY period_date, station_code
    """,
    "nielsen_cume": """
        SELECT station_code, value_numeric AS cume
        FROM nielsen.fact_vital_signs
        WHERE section='Estimates' AND metric='Avg Weekly Cume Persons'
          AND period_date=(SELECT max(period_date) FROM nielsen.fact_vital_signs WHERE metric='Avg Weekly Cume Persons')
        ORDER BY cume DESC
    """,
    "nielsen_cume_trend": """
        SELECT station_code, period_label, period_date::text AS period_date, value_numeric AS cume
        FROM nielsen.fact_vital_signs
        WHERE section='Estimates' AND metric='Avg Weekly Cume Persons' AND period_date IS NOT NULL
        ORDER BY period_date, station_code
    """,
    "tlh_by_station": """
        SELECT station_code, month_start::text AS month, round(tlh) AS tlh, round(aas,1) AS aas, round(cume) AS cume
        FROM wms.fact_monthly_cume ORDER BY month_start, station_code
    """,
    "platform_breakdown": """
        SELECT station_code, device_family, round(sum(tlh)) AS tlh
        FROM wms.fact_monthly_device
        WHERE month_start=(SELECT max(month_start) FROM wms.fact_monthly_device)
        GROUP BY station_code, device_family ORDER BY tlh DESC
    """,
    "station_comparison": """
        SELECT station_code, round(tlh) AS tlh, round(aas,1) AS aas, cume
        FROM wms.fact_monthly_cume
        WHERE month_start=(SELECT max(month_start) FROM wms.fact_monthly_cume)
        ORDER BY tlh DESC
    """,
    "web_sessions_weekly": """
        SELECT account__property_name AS property, date_trunc('week', report__date)::date::text AS week,
               sum(engagement__sessions) AS sessions
        FROM ga.stg_sessions_daily WHERE report__date >= current_date - interval '365 days'
        GROUP BY 1,2 ORDER BY 2,1
    """,
    "email_lists": """
        SELECT name AS list_name, stats_member_count AS members
        FROM email_esp.stg_lists WHERE name <> 'Funraise' ORDER BY members DESC
    """,
    "social_followers": """
        SELECT report__date::text AS date, account__account_name AS account,
               max(engagement__lifetime_followers) AS followers
        FROM meta_organic.stg_fb_page_daily WHERE engagement__lifetime_followers IS NOT NULL
        GROUP BY report__date, account__account_name ORDER BY report__date
    """,
    "ig_followers": """
        SELECT account_name, followers_count
        FROM meta_organic.fact_ig_followers_daily
        WHERE snapshot_date=(SELECT max(snapshot_date) FROM meta_organic.fact_ig_followers_daily)
        ORDER BY followers_count DESC
    """,
    # Reads the CLEAN view (schema/022): engagement metrics are NULL where the
    # source is untrustworthy (pre-Aug-2025 collection gap, -1 sentinels, and the
    # months where engagements exceeded reach). `month` is the month START.
    # is_complete = false for the month still accumulating; the frontend drops those
    # rather than compare 9 days against 30. NULL means not measured, never zero.
    "social_ig_monthly": """
        SELECT account, month::text AS month, reach, engagements, accounts_engaged, is_complete
        FROM meta_organic.v_ig_profile_monthly
        ORDER BY month, account
    """,
    "email_campaigns": """
        SELECT campaign_title, list_name, send_time::date::text AS sent,
               round(opens_open_rate::numeric,3) AS open_rate, round(clicks_click_rate::numeric,3) AS click_rate, emails_sent
        FROM email_esp.stg_campaigns_report ORDER BY send_time DESC LIMIT 40
    """,
    "combined_digital_reach": """
        SELECT
          (SELECT sum(engagement__sessions) FROM ga.stg_sessions_daily WHERE report__date >= current_date - interval '30 days') AS web_sessions_30d,
          (SELECT coalesce(sum(performance__content_views___total),0) FROM meta_organic.stg_fb_page_daily WHERE report__date >= current_date - interval '30 days')
            -- Read the CLEAN view, not staging: the raw table still carries the
            -- impossible reach values the view nulls out (hyfin.mke 2026-07 = 2,213
            -- against 6,135 accounts engaged). Summing staging quietly re-imports the bug.
            + (SELECT coalesce(sum(reach),0) FROM meta_organic.v_ig_profile_monthly WHERE period_end >= current_date - interval '40 days') AS social_reach_30d,
          (SELECT sum(emails_sent) FROM email_esp.stg_campaigns_report WHERE send_time >= current_date - interval '30 days') AS emails_sent_30d
    """,
    "daypart_aas": """
        SELECT h.station_code,
               d.daypart_id,
               d.name AS daypart,
               round(avg(h.aas), 1) AS aas
        FROM wms.fact_hourly_listening h
        JOIN dim.dayparts d ON h.hour >= d.start_hour AND h.hour < d.end_hour
        WHERE h.date >= (current_date - interval '365 days')
        GROUP BY h.station_code, d.daypart_id, d.name
        ORDER BY h.station_code, d.daypart_id
    """,
    "hourly_grid": """
        SELECT station_code,
               extract(dow from date)::int AS dow,
               hour,
               round(avg(aas), 1) AS aas,
               round(avg(cume))  AS cume
        FROM wms.fact_hourly_listening
        WHERE date >= (current_date - interval '365 days')
        GROUP BY station_code, dow, hour
        ORDER BY station_code, dow, hour
    """,
    "tsl_trend": """
        SELECT station_code,
               date_trunc('month', date)::date AS month,
               round(avg(tsl_minutes), 1) AS tsl_minutes
        FROM wms.fact_hourly_listening
        GROUP BY station_code, month
        ORDER BY station_code, month
    """,
    "top_web_content": """
        SELECT account__property_name AS property,
               page__page_path AS page_path,
               sum(engagement__views) AS views,
               round((sum(engagement__user_engagement) / NULLIF(sum(acquisition__total_users), 0))::numeric, 1) AS avg_engagement_s
        FROM ga.stg_pages_daily
        WHERE report__date >= (current_date - interval '90 days')
        GROUP BY property, page_path
        ORDER BY views DESC
        LIMIT 50
    """,
    # Top pages for the Digital tab — two windows (weekly = trailing 7d,
    # monthly = trailing 30d). Page TITLES are derived from the slug in the
    # frontend (ga.dim_pages is empty); SQL returns path + volume + quality.
    # Top-N is PER PROPERTY (window function), not global: the dashboard filters
    # these rows by brand client-side, and a global LIMIT would starve a smaller
    # property (e.g. HYFIN, ~21x less traffic than radiomilwaukee.org) down to the
    # one page that cracks the combined top list. Per-property gives each brand
    # its own top 15.
    "top_pages_weekly": """
        WITH ranked AS (
            SELECT account__property_name AS property,
                   page__page_path AS page_path,
                   sum(engagement__views) AS views,
                   sum(acquisition__total_users) AS users,
                   round((sum(engagement__user_engagement) / NULLIF(sum(acquisition__total_users), 0))::numeric, 1) AS avg_engagement_s,
                   row_number() OVER (PARTITION BY account__property_name ORDER BY sum(engagement__views) DESC) AS rn
            FROM ga.stg_pages_daily
            WHERE report__date >= (current_date - interval '7 days')
            GROUP BY property, page_path
        )
        SELECT property, page_path, views, users, avg_engagement_s
        FROM ranked WHERE rn <= 15
        ORDER BY property, views DESC
    """,
    "top_pages_monthly": """
        WITH ranked AS (
            SELECT account__property_name AS property,
                   page__page_path AS page_path,
                   sum(engagement__views) AS views,
                   sum(acquisition__total_users) AS users,
                   round((sum(engagement__user_engagement) / NULLIF(sum(acquisition__total_users), 0))::numeric, 1) AS avg_engagement_s,
                   row_number() OVER (PARTITION BY account__property_name ORDER BY sum(engagement__views) DESC) AS rn
            FROM ga.stg_pages_daily
            WHERE report__date >= (current_date - interval '30 days')
            GROUP BY property, page_path
        )
        SELECT property, page_path, views, users, avg_engagement_s
        FROM ranked WHERE rn <= 15
        ORDER BY property, views DESC
    """,
    # ── Digital tab — web overview (GA4 staging) ───────────────────────────
    # Daily web series (last 365d) powers the KPI row, period-over-period
    # deltas, and the growth/engagement trends — all derived client-side so the
    # global date filter applies. Per (property, date).
    # Mobile app, monthly. Reads ga.v_app_daily (schema/024), which merges Radio
    # Milwaukee's TWO GA properties — one app, migrated Sep 2025 — and carries the
    # only iOS rows. `active_users_daily` is a DAILY value: averaged here, never
    # summed, or the month reports person-days instead of people.
    # is_complete: the month's last calendar day is present in the data. The current
    # month is always partial (GA is daily and today is mid-month), and the frontend
    # drops it — the same rule the Instagram tiles learned the hard way.
    "app_monthly": """
        SELECT station_code,
               date_trunc('month', date)::date::text AS month,
               platform,
               sum(sessions)                          AS sessions,
               sum(views)                             AS views,
               sum(new_users)                         AS new_users,
               round(avg(active_users_daily))::bigint AS avg_daily_active_users,
               (max(date) >= (date_trunc('month', min(date)) + interval '1 month - 1 day')::date)
                                                      AS is_complete
        FROM ga.v_app_daily
        GROUP BY 1, 2, 3
        ORDER BY 2, 1, 3
    """,
    "web_daily": """
        SELECT account__property_name AS property,
               report__date AS date,
               sum(acquisition__total_users) AS users,
               sum(acquisition__new_users) AS new_users,
               sum(engagement__sessions) AS sessions,
               sum(engagement__engaged_sessions) AS engaged_sessions,
               sum(engagement__views) AS views,
               round(avg(NULLIF(session__average_session_duration, 0))::numeric, 1) AS avg_session_sec
        FROM ga.stg_sessions_daily
        WHERE report__date >= (current_date - interval '365 days')
        GROUP BY property, report__date
        ORDER BY property, report__date
    """,
    # Traffic channels — GA4-style grouping of source/medium. Trailing 30d
    # (dimensional; the date filter does not apply — note it in the UI).
    "web_channels": """
        SELECT account__property_name AS property,
               CASE
                 WHEN session__session_source___medium ILIKE '%email%' THEN 'Email'
                 WHEN session__session_source___medium ILIKE '%cpc%'
                      OR session__session_source___medium ILIKE '%/ paid%'
                      OR session__session_source___medium ILIKE '%ppc%' THEN 'Paid'
                 WHEN session__session_source___medium ILIKE '%organic%' THEN 'Organic Search'
                 WHEN session__session_source___medium ILIKE '(direct)%' THEN 'Direct'
                 WHEN session__session_source___medium ILIKE 'fb %'
                      OR session__session_source___medium ILIKE 'facebook%'
                      OR session__session_source___medium ILIKE '%instagram%'
                      OR session__session_source___medium ILIKE '%t.co%'
                      OR session__session_source___medium ILIKE '%/twitter%'
                      OR session__session_source___medium ILIKE '%linkedin%'
                      OR session__session_source___medium ILIKE '%youtube%'
                      OR session__session_source___medium ILIKE '%reddit%' THEN 'Social'
                 WHEN session__session_source___medium ILIKE '%referral%' THEN 'Referral'
                 ELSE 'Other'
               END AS channel,
               sum(engagement__sessions) AS sessions,
               sum(acquisition__total_users) AS users,
               sum(engagement__views) AS views
        FROM ga.stg_sessions_daily
        WHERE report__date >= (current_date - interval '30 days')
        GROUP BY property, channel
        ORDER BY property, sessions DESC
    """,
    # Geography — top 10 regions + top 10 cities per property, trailing 30d.
    "web_geo": """
        WITH agg AS (
            SELECT account__property_name AS property, 'region' AS level,
                   audience__region AS place,
                   sum(engagement__sessions) AS sessions,
                   sum(acquisition__total_users) AS users,
                   sum(engagement__views) AS views
            FROM ga.stg_geo_daily
            WHERE report__date >= (current_date - interval '30 days')
              AND audience__region IS NOT NULL AND audience__region <> '' AND audience__region <> '(not set)'
            GROUP BY account__property_name, audience__region
            UNION ALL
            SELECT account__property_name, 'city', audience__city,
                   sum(engagement__sessions), sum(acquisition__total_users), sum(engagement__views)
            FROM ga.stg_geo_daily
            WHERE report__date >= (current_date - interval '30 days')
              AND audience__city IS NOT NULL AND audience__city <> '' AND audience__city <> '(not set)'
            GROUP BY account__property_name, audience__city
        ),
        ranked AS (
            SELECT property, level, place, sessions, users, views,
                   row_number() OVER (PARTITION BY property, level ORDER BY sessions DESC) AS rn
            FROM agg
        )
        SELECT property, level, place, sessions, users, views
        FROM ranked WHERE rn <= 10
        ORDER BY property, level, sessions DESC
    """,
    # Device split — trailing 30d.
    "web_devices": """
        SELECT account__property_name AS property,
               audience__device_category AS device,
               sum(engagement__sessions) AS sessions,
               sum(acquisition__total_users) AS users
        FROM ga.stg_device_daily
        WHERE report__date >= (current_date - interval '30 days')
          AND audience__device_category IS NOT NULL AND audience__device_category <> ''
        GROUP BY property, device
        ORDER BY property, sessions DESC
    """,
    # Key on-site actions — trailing 30d. Excludes GA4's automatic events so the
    # list shows meaningful actions (audio plays, outbound clicks, player use).
    "web_key_events": """
        SELECT account__property_name AS property,
               engagement__event_name AS event,
               sum(engagement__event_count) AS count
        FROM ga.stg_events_daily
        WHERE report__date >= (current_date - interval '30 days')
          AND engagement__event_name NOT IN
              ('page_view','session_start','first_visit','user_engagement','scroll','ad_impression')
        GROUP BY property, event
        ORDER BY property, count DESC
    """,
    # ── Program Director tab — streaming overview (Triton, daily grain) ─────
    # Daily streaming series (last 365d) powers the NPR-style overview: KPI row
    # (Listeners=CUME, Sessions=SS, Sessions/User=SS/CUME, Minutes/Session=
    # TLH*60/SS), period-over-period deltas, and the trends — all client-side so
    # the brand + date filter applies. CUME is non-additive: averaged per day,
    # never summed across days. fact_daily_cume is one row per (station, date).
    "streaming_daily": """
        SELECT station_code, date, cume, ss, tlh, aas, tsl_minutes
        FROM wms.fact_daily_cume
        WHERE date >= (current_date - interval '365 days')
        ORDER BY station_code, date
    """,
    # Device-family split for the latest available month (share by session starts,
    # matching NPR's "% of sessions"). Per station.
    "streaming_devices": """
        SELECT station_code, device_family,
               sum(ss) AS ss, sum(tlh) AS tlh, sum(cume) AS cume
        FROM wms.fact_monthly_device
        WHERE month_start = (SELECT max(month_start) FROM wms.fact_monthly_device)
        GROUP BY station_code, device_family
        ORDER BY station_code, ss DESC
    """,
    # ── Development Director tab — Funraise donor queries ──────────────────
    "donor_retention_trend": """
        WITH gifts AS (
          SELECT supporter_id, extract(year FROM transaction_date)::int AS yr
          FROM funraise.fact_transactions WHERE status='Complete' GROUP BY 1,2),
        first_yr AS (SELECT supporter_id, min(yr) AS fy FROM gifts GROUP BY 1)
        SELECT g.yr AS prior_year,
               CASE WHEN g.yr = f.fy THEN 'first_year' ELSE 'repeat' END AS cohort,
               count(DISTINCT g.supporter_id) AS donors,
               round(100.0*count(DISTINCT g2.supporter_id)/NULLIF(count(DISTINCT g.supporter_id),0),1) AS retention_pct
        FROM gifts g JOIN first_yr f USING (supporter_id)
        LEFT JOIN gifts g2 ON g2.supporter_id=g.supporter_id AND g2.yr=g.yr+1
        GROUP BY g.yr, cohort ORDER BY g.yr, cohort
    """,
    "donor_status_trend": """
        WITH first_gift AS (
          SELECT supporter_id, min(transaction_date) AS fg
          FROM funraise.fact_transactions WHERE status='Complete' GROUP BY 1),
        monthly AS (
          SELECT DISTINCT supporter_id, date_trunc('month',transaction_date)::date AS m
          FROM funraise.fact_transactions WHERE status='Complete')
        SELECT m.m AS month,
               count(*) FILTER (WHERE date_trunc('month',f.fg)=m.m) AS new_donors,
               count(*) FILTER (WHERE date_trunc('month',f.fg)<m.m) AS returning_donors
        FROM monthly m JOIN first_gift f USING (supporter_id)
        GROUP BY m.m ORDER BY m.m
    """,
    "sustainer_flow": """
        WITH adds AS (
          SELECT date_trunc('month',started_at)::date AS m, count(*) AS added
          FROM funraise.fact_subscriptions WHERE started_at IS NOT NULL GROUP BY 1),
        churn AS (
          SELECT date_trunc('month',canceled_at)::date AS m, count(*) AS churned
          FROM funraise.fact_subscriptions WHERE canceled_at IS NOT NULL AND status='Cancelled' GROUP BY 1)
        SELECT coalesce(a.m,c.m) AS month, coalesce(a.added,0) AS added, coalesce(c.churned,0) AS churned
        FROM adds a FULL OUTER JOIN churn c ON a.m=c.m ORDER BY month
    """,
    "ltv_tiers": """
        SELECT CASE WHEN lifetime_total<100 THEN '<$100'
                    WHEN lifetime_total<500 THEN '$100-499'
                    WHEN lifetime_total<1000 THEN '$500-999'
                    WHEN lifetime_total<5000 THEN '$1K-4,999'
                    ELSE '$5K+' END AS tier,
               count(*) AS donors, round(sum(lifetime_total)) AS total
        FROM funraise.dim_supporters WHERE lifetime_total>0
        GROUP BY tier ORDER BY min(lifetime_total)
    """,
    "payment_method_mix": """
        SELECT
            CASE lower(replace(coalesce(nullif(payment_method,''),'other'),'_',' '))
                WHEN 'credit card' THEN 'Credit Card'
                WHEN 'ach'         THEN 'ACH'
                WHEN 'physical check' THEN 'Physical Check'
                WHEN 'personal check' THEN 'Physical Check'
                WHEN 'check'       THEN 'Physical Check'
                WHEN 'apple pay'   THEN 'Apple Pay'
                WHEN 'paypal'      THEN 'PayPal'
                WHEN 'cash'        THEN 'Cash'
                WHEN 'stock'       THEN 'Stock'
                WHEN 'donor advised fund' THEN 'Donor Advised Fund'
                WHEN 'external capture' THEN 'Other'
                WHEN 'other'       THEN 'Other'
                ELSE 'Other'
            END AS method,
            count(*) AS gifts,
            round(sum(amount)) AS total
        FROM funraise.fact_transactions
        WHERE status='Complete' AND coalesce(refunded,false)=false
        GROUP BY method ORDER BY total DESC
    """,
    "donor_geo_state": """
        SELECT state, count(*) AS donors, round(sum(lifetime)) AS lifetime
        FROM (
            SELECT
                CASE upper(trim(coalesce(nullif(state,''),'Unknown')))
                    WHEN 'WISCONSIN'     THEN 'WI'
                    WHEN 'ILLINOIS'      THEN 'IL'
                    WHEN 'CALIFORNIA'    THEN 'CA'
                    WHEN 'MINNESOTA'     THEN 'MN'
                    WHEN 'COLORADO'      THEN 'CO'
                    WHEN 'NEW YORK'      THEN 'NY'
                    WHEN 'FLORIDA'       THEN 'FL'
                    WHEN 'VIRGINIA'      THEN 'VA'
                    WHEN 'MICHIGAN'      THEN 'MI'
                    WHEN 'WASHINGTON'    THEN 'WA'
                    WHEN 'OREGON'        THEN 'OR'
                    WHEN 'PENNSYLVANIA'  THEN 'PA'
                    WHEN 'ARIZONA'       THEN 'AZ'
                    WHEN 'NEW JERSEY'    THEN 'NJ'
                    ELSE upper(trim(coalesce(nullif(state,''),'Unknown')))
                END AS state,
                lifetime_total AS lifetime
            FROM funraise.dim_supporters WHERE lifetime_total>0
        ) sub
        GROUP BY state ORDER BY donors DESC LIMIT 15
    """,
    "donor_geo_zip": """
        SELECT coalesce(nullif(postal_code,''),'Unknown') AS zip,
               count(*) AS donors, round(sum(lifetime_total)) AS lifetime
        FROM funraise.dim_supporters WHERE lifetime_total>0
        GROUP BY zip ORDER BY donors DESC LIMIT 15
    """,
}


def _jsonable(v: object):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _dev_kpis_from_registry() -> dict:
    """Fetch Development Director KPIs from the metric registry.

    Returns a single dict with five donor metrics:
    - sustainer_share      (percent of active donors who are sustainers)
    - donor_retention_pct  (share of prior-year donors who gave again)
    - avg_gift             (median; also carries mean)
    - new_donors           (first gift in last 365 days)
    - lapsed_donors        (last gift > 12 months ago)
    """
    avg_gift_row = run_metric("avg_gift")["data"][0]
    return {
        "sustainer_share": run_metric("sustainer_share")["data"][0]["value"],
        "donor_retention_pct": run_metric("donor_retention_pct")["data"][0]["value"],
        "avg_gift": avg_gift_row.get("value"),
        "avg_gift_mean": avg_gift_row.get("mean"),
        "new_donors": run_metric("new_donors")["data"][0]["value"],
        "lapsed_donors": run_metric("lapsed_donors")["data"][0]["value"],
    }


def _exec_kpis_from_registry() -> list[dict]:
    """Fetch the four headline KPIs from the metric registry (single source of truth).

    Period note: revenue_12mo uses the registry's 12m period (365-day rolling
    window from Python, i.e. today - 365 days). The previous bespoke SQL used
    PostgreSQL's `interval '12 months'` (calendar-month subtraction). These
    differ by at most one day in leap years; registry semantics are preferred per
    the architecture decision to avoid duplicate SQL.
    """
    return [
        {
            "active_donors": run_metric("active_donors")["data"][0]["value"],
            "active_sustainers": run_metric("active_sustainers")["data"][0]["value"],
            "sustainer_mrr": run_metric("sustainer_mrr")["data"][0]["value"],
            # registry period="12m" = today - 365 days (see metrics/filters.py)
            "revenue_12mo": run_metric("revenue", period="12m")["data"][0]["value"],
        }
    ]


def _error_summary(exc: Exception) -> str:
    """Name the failure class, never the statement or a row.

    /api/dashboard is UNAUTHENTICATED — only the assistant's tool endpoints are gated —
    so the response must not echo SQL back to the internet. The full message and stack
    go to the server log.
    """
    sqlstate = getattr(exc, "sqlstate", None)
    return type(exc).__name__ + (f" ({sqlstate})" if sqlstate else "")


def dashboard_data() -> dict:
    """Run every dashboard query and return the ones that worked.

    A single failing query used to raise straight out of here, 500 the endpoint, and
    blank the whole dashboard — exactly what happened on 2026-07-10, when Coupler's
    DROP TABLE ... CASCADE took the clean views down with it and 3 of 41 queries threw.
    The other 38 were fine.

    Now each query fails alone: its key comes back `[]`, the failure is named in
    `_errors`, and every other card still renders.
    """
    conn = get_db_connection()
    out: dict[str, list[dict]] = {}
    errors: list[dict[str, str]] = []
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            for name, sql in QUERIES.items():
                try:
                    cur.execute(sql)
                    out[name] = [{k: _jsonable(v) for k, v in row.items()} for row in cur.fetchall()]
                except psycopg.Error as exc:
                    # A failed statement poisons the transaction — without this rollback
                    # every later query dies with InFailedSqlTransaction.
                    conn.rollback()
                    out[name] = []
                    errors.append({"query": name, "error": _error_summary(exc)})
                    log.exception("dashboard query %r failed", name)
    finally:
        conn.close()

    # Headline KPIs via registry (one definition — no duplicate SQL).
    for key, fn in (("exec_kpis", _exec_kpis_from_registry), ("dev_kpis", _dev_kpis_from_registry)):
        try:
            out[key] = fn()
        except Exception as exc:          # registry metrics open their own connections
            out[key] = []
            errors.append({"query": key, "error": _error_summary(exc)})
            log.exception("dashboard registry block %r failed", key)

    # Surfaced, never swallowed. A silently empty card is how a wrong number reaches
    # leadership; the frontend renders a banner when this is non-empty.
    out["_errors"] = errors
    return out
