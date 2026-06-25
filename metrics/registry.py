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
