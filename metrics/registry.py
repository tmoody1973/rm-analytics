"""The metric registry — one place that defines each leadership number.

Each Metric carries plain-English metadata (for tooltips + the assistant's
citations) and a SQL builder. run_metric() executes against Neon and returns
{data, meta}. The same logic backs the dashboard tabs and the assistant tools.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "loaders"))
from _common import get_db_connection  # noqa: E402

from .filters import period_cutoff, station_codes_for  # noqa: E402

Builder = Callable[[str | None, str | None, str | None], tuple[str, list]]
VALID_GROUP_BYS: set[str | None] = {None, "month", "station"}


@dataclass(frozen=True)
class Metric:
    id: str
    name: str
    description: str
    unit: str       # 'usd' | 'count' | 'percent' | 'hours'
    source: str     # origin table, used for citations
    build: Builder


def _jsonable(v: object):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


# ---------------------------------------------------------------- builders ---
def _sustainer_mrr(brand, period, group_by):
    return (
        "SELECT round(sum(amount)) AS value FROM funraise.fact_subscriptions "
        "WHERE status='Active' AND frequency='Monthly'",
        [],
    )


def _active_donors(brand, period, group_by):
    return (
        "SELECT count(*) AS value FROM funraise.dim_supporters WHERE active_12mo",
        [],
    )


def _streaming_tlh(brand, period, group_by):
    where: list[str] = []
    params: list = []
    codes = station_codes_for(brand)
    if codes:
        where.append("station_code = ANY(%s)")
        params.append(codes)
    cutoff = period_cutoff(period)
    if cutoff:
        where.append("month_start >= %s")
        params.append(cutoff)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    if group_by == "month":
        sql = (f"SELECT month_start::text AS bucket, round(sum(tlh)) AS value "
               f"FROM wms.fact_monthly_cume{clause} GROUP BY 1 ORDER BY 1")
    elif group_by == "station":
        sql = (f"SELECT station_code AS bucket, round(sum(tlh)) AS value "
               f"FROM wms.fact_monthly_cume{clause} GROUP BY 1 ORDER BY 2 DESC")
    else:
        sql = f"SELECT round(sum(tlh)) AS value FROM wms.fact_monthly_cume{clause}"
    return sql, params


def _revenue(brand, period, group_by):
    where = ["status='Complete'"]
    params: list = []
    cutoff = period_cutoff(period)
    if cutoff:
        where.append("transaction_date >= %s")
        params.append(cutoff)
    clause = " WHERE " + " AND ".join(where)
    if group_by == "month":
        sql = (f"SELECT date_trunc('month', transaction_date)::date::text AS bucket, "
               f"round(sum(amount)) AS value FROM funraise.fact_transactions{clause} "
               f"GROUP BY 1 ORDER BY 1")
    else:
        sql = f"SELECT round(sum(amount)) AS value FROM funraise.fact_transactions{clause}"
    return sql, params


def _active_sustainers(brand, period, group_by):
    return "SELECT count(*) AS value FROM funraise.fact_subscriptions WHERE status='Active'", []


def _total_donors(brand, period, group_by):
    return "SELECT count(*) AS value FROM funraise.dim_supporters", []


def _avg_gift(brand, period, group_by):
    where = ["status='Complete'", "amount > 0", "coalesce(refunded, false) = false"]
    params: list = []
    cutoff = period_cutoff(period)
    if cutoff:
        where.append("transaction_date >= %s")
        params.append(cutoff)
    clause = " WHERE " + " AND ".join(where)
    sql = (
        f"SELECT round(percentile_cont(0.5) WITHIN GROUP (ORDER BY amount)::numeric, 2) AS value, "
        f"round(avg(amount), 2) AS mean "
        f"FROM funraise.fact_transactions{clause}"
    )
    return sql, params


def _sustainer_share(brand, period, group_by):
    sql = (
        "WITH active AS ("
        "  SELECT DISTINCT supporter_id FROM funraise.fact_transactions"
        "  WHERE status='Complete' AND transaction_date >= current_date - interval '365 days'"
        "), sustainers AS ("
        "  SELECT DISTINCT supporter_id FROM funraise.fact_transactions"
        "  WHERE status='Complete' AND recurring"
        "  AND transaction_date >= current_date - interval '365 days'"
        ") "
        "SELECT round("
        "  100.0 * (SELECT count(*) FROM sustainers) / NULLIF((SELECT count(*) FROM active), 0), 1"
        ") AS value"
    )
    return sql, []


def _donor_retention_pct(brand, period, group_by):
    sql = (
        "WITH prior AS ("
        "  SELECT DISTINCT supporter_id FROM funraise.fact_transactions"
        "  WHERE status='Complete'"
        "  AND transaction_date >= current_date - interval '730 days'"
        "  AND transaction_date < current_date - interval '365 days'"
        "), recent AS ("
        "  SELECT DISTINCT supporter_id FROM funraise.fact_transactions"
        "  WHERE status='Complete' AND transaction_date >= current_date - interval '365 days'"
        ") "
        "SELECT round("
        "  100.0 * count(*) FILTER (WHERE supporter_id IN (SELECT supporter_id FROM recent))"
        "  / NULLIF(count(*), 0), 1"
        ") AS value FROM prior"
    )
    return sql, []


def _new_donors(brand, period, group_by):
    cutoff = period_cutoff(period)
    if cutoff:
        since_expr = "%s"
        params: list = [cutoff]
    else:
        since_expr = "current_date - interval '365 days'"
        params = []
    sql = (
        f"SELECT count(*) AS value FROM ("
        f"  SELECT supporter_id, min(transaction_date) AS fg"
        f"  FROM funraise.fact_transactions WHERE status='Complete' GROUP BY 1"
        f") s WHERE s.fg >= {since_expr}"
    )
    return sql, params


def _lapsed_donors(brand, period, group_by):
    sql = (
        "SELECT count(*) AS value FROM ("
        "  SELECT supporter_id, max(transaction_date) AS lg"
        "  FROM funraise.fact_transactions WHERE status='Complete' GROUP BY 1"
        ") s WHERE s.lg < current_date - interval '365 days'"
    )
    return sql, []


def _avg_active_sessions(brand, period, group_by):
    where: list[str] = []
    params: list = []
    codes = station_codes_for(brand)
    if codes:
        where.append("station_code = ANY(%s)")
        params.append(codes)
    cutoff = period_cutoff(period)
    if cutoff:
        where.append("month_start >= %s")
        params.append(cutoff)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    if group_by == "station":
        sql = (f"SELECT station_code AS bucket, round(avg(aas),1) AS value "
               f"FROM wms.fact_monthly_cume{clause} GROUP BY 1 ORDER BY 2 DESC")
    elif group_by == "month":
        sql = (f"SELECT month_start::text AS bucket, round(avg(aas),1) AS value "
               f"FROM wms.fact_monthly_cume{clause} GROUP BY 1 ORDER BY 1")
    else:
        sql = f"SELECT round(avg(aas),1) AS value FROM wms.fact_monthly_cume{clause}"
    return sql, params


REGISTRY: dict[str, Metric] = {
    "sustainer_mrr": Metric(
        "sustainer_mrr", "Sustainer MRR",
        "Monthly recurring revenue from active monthly sustainer plans. Target $50,000.",
        "usd", "funraise.fact_subscriptions", _sustainer_mrr,
    ),
    "active_donors": Metric(
        "active_donors", "Active donors",
        "Distinct donors with a completed gift in the last 12 months.",
        "count", "funraise.dim_supporters", _active_donors,
    ),
    "streaming_tlh": Metric(
        "streaming_tlh", "Streaming total listening hours",
        "Triton streaming hours, summed. Brand- and period-aware; group by month or station.",
        "hours", "wms.fact_monthly_cume", _streaming_tlh,
    ),
    "revenue": Metric(
        "revenue", "Revenue (completed gifts)",
        "Total dollars from completed Funraise gifts (excludes failed/refunded). Period-aware; group by month.",
        "usd", "funraise.fact_transactions", _revenue,
    ),
    "active_sustainers": Metric(
        "active_sustainers", "Active sustainers",
        "Count of active recurring giving plans (any frequency).",
        "count", "funraise.fact_subscriptions", _active_sustainers,
    ),
    "total_donors": Metric(
        "total_donors", "Total donors (all time)",
        "Count of all supporters on record.",
        "count", "funraise.dim_supporters", _total_donors,
    ),
    "avg_active_sessions": Metric(
        "avg_active_sessions", "Avg active sessions (AAS)",
        "Average concurrent Triton streams. Brand- and period-aware; group by month or station.",
        "count", "wms.fact_monthly_cume", _avg_active_sessions,
    ),
    "avg_gift": Metric(
        "avg_gift", "Avg gift (median)",
        "Median completed gift amount. Returns median as value and mean as an extra field. Period-aware.",
        "usd", "funraise.fact_transactions", _avg_gift,
    ),
    "sustainer_share": Metric(
        "sustainer_share", "Sustainer share",
        "Percentage of active-12-month donors who are recurring sustainers.",
        "percent", "funraise.fact_transactions", _sustainer_share,
    ),
    "donor_retention_pct": Metric(
        "donor_retention_pct", "Donor retention",
        "Share of donors active in the prior 12 months who also gave in the most recent 12 months.",
        "percent", "funraise.fact_transactions", _donor_retention_pct,
    ),
    "new_donors": Metric(
        "new_donors", "New donors",
        "Donors whose first-ever completed gift falls within the period. Period-aware; defaults to last 365 days.",
        "count", "funraise.fact_transactions", _new_donors,
    ),
    "lapsed_donors": Metric(
        "lapsed_donors", "Lapsed donors",
        "Donors who gave at least once but whose last completed gift was more than 12 months ago.",
        "count", "funraise.fact_transactions", _lapsed_donors,
    ),
}


def run_metric(metric_id: str, brand: str | None = None,
               period: str | None = None, group_by: str | None = None) -> dict:
    if metric_id not in REGISTRY:
        raise KeyError(metric_id)
    if group_by not in VALID_GROUP_BYS:
        raise ValueError(f"unknown group_by {group_by!r}")
    m = REGISTRY[metric_id]
    sql, params = m.build(brand, period, group_by)
    conn = get_db_connection()
    try:
        from psycopg.rows import dict_row
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()
    data = [{k: _jsonable(v) for k, v in r.items()} for r in rows]
    return {
        "data": data,
        "meta": {"id": m.id, "name": m.name, "description": m.description,
                 "unit": m.unit, "source": m.source},
    }
