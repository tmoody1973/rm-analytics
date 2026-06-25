"""Read-only metric endpoint. Resolves a metric_id through the registry so the
dashboard and the assistant share one definition of every number.
"""
from __future__ import annotations

import os
import sys

from fastapi import APIRouter, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from metrics.registry import run_metric  # noqa: E402

router = APIRouter()


@router.get("/api/metric/{metric_id}")
def metric(metric_id: str, brand: str | None = None,
           period: str | None = None, group_by: str | None = None) -> dict:
    try:
        return run_metric(metric_id, brand=brand, period=period, group_by=group_by)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown metric {metric_id!r}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
