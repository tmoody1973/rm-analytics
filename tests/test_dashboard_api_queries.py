"""Shape/discriminator checks for the slice-1 dashboard_api queries (MOO-176)."""
from __future__ import annotations
import importlib

dashboard_api = importlib.import_module("service.dashboard_api")

def _payload():
    return dashboard_api.dashboard_data()

def test_new_keys_present():
    p = _payload()
    for k in ("daypart_aas", "hourly_grid", "tsl_trend", "top_web_content"):
        assert k in p, f"missing payload key {k}"

def test_daypart_aas_shape():
    rows = _payload()["daypart_aas"]
    assert rows, "daypart_aas empty"
    r = rows[0]
    assert {"station_code", "daypart", "aas"} <= set(r)

def test_hourly_grid_shape():
    rows = _payload()["hourly_grid"]
    assert rows
    r = rows[0]
    assert {"station_code", "dow", "hour", "aas"} <= set(r)
    assert 0 <= r["dow"] <= 6 and 0 <= r["hour"] <= 23

def test_tsl_trend_brandable():
    rows = _payload()["tsl_trend"]
    assert rows and "station_code" in rows[0] and "month" in rows[0]

def test_top_web_content_brandable():
    rows = _payload()["top_web_content"]
    assert rows and "property" in rows[0] and "views" in rows[0]

def test_top_pages_weekly_and_monthly_shape():
    p = _payload()
    for k in ("top_pages_weekly", "top_pages_monthly"):
        rows = p[k]
        assert rows, f"{k} empty"
        r = rows[0]
        # property for brand filtering + the four displayed metrics/keys.
        assert {"property", "page_path", "views", "users", "avg_engagement_s"} <= set(r), (
            f"{k} missing columns: got {sorted(r)}"
        )
