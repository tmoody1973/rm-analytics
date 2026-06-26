"""
Read-only dashboard data API. One GET returns all data the RM Executive Dashboard
web app needs, as JSON. Aggregate, non-PII data. SQL mirrors the validated Hex
dashboard cells; GA/Meta/Email read the populated stg_ tables (clean fact_ are empty).
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row

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
          (SELECT value FROM finance.fact_kpi_monthly WHERE indicator='Revenue YTD - Cash' ORDER BY month DESC LIMIT 1) AS revenue_ytd,
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
               max(value) FILTER (WHERE indicator='Revenue YTD - Cash') AS revenue_ytd,
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
    "social_ig_monthly": """
        SELECT account__account_name AS account, report__end_date::text AS month,
               performance__reach AS reach, performance__engagements AS engagements,
               engagement__accounts_engaged AS accounts_engaged
        FROM meta_organic.stg_ig_profile_monthly
        ORDER BY report__end_date, account__account_name
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
            + (SELECT coalesce(sum(performance__reach),0) FROM meta_organic.stg_ig_profile_monthly WHERE report__end_date >= current_date - interval '40 days') AS social_reach_30d,
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
}


def _jsonable(v: object):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


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


def dashboard_data() -> dict:
    conn = get_db_connection()
    out: dict[str, list[dict]] = {}
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            for name, sql in QUERIES.items():
                cur.execute(sql)
                out[name] = [{k: _jsonable(v) for k, v in row.items()} for row in cur.fetchall()]
    finally:
        conn.close()
    # Headline KPIs via registry (one definition — no duplicate SQL).
    out["exec_kpis"] = _exec_kpis_from_registry()
    return out
