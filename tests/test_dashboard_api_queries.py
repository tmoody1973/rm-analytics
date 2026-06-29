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
        assert {"property", "page_path", "users", "avg_engagement_s"} <= set(r) and "views" in r, (
            f"{k} missing columns: got {sorted(r)}"
        )

def test_top_pages_ranked_per_property_not_global():
    # Regression guard: top-N must be PER PROPERTY (window function), not a global
    # LIMIT. The dashboard filters these rows by brand client-side, so a global cap
    # starves the smaller property (HYFIN) down to ~1 page. With per-property
    # ranking both GA properties appear, and the smaller one gets several pages.
    p = _payload()
    for k in ("top_pages_weekly", "top_pages_monthly"):
        rows = p[k]
        by_prop = {}
        for r in rows:
            by_prop.setdefault(r["property"], 0)
            by_prop[r["property"]] += 1
        assert len(by_prop) >= 2, (
            f"{k}: expected >=2 GA properties, got {by_prop} — global LIMIT regression?"
        )
        # The smaller property should get more than the single page the old global
        # query left it with.
        assert min(by_prop.values()) >= 2, (
            f"{k}: smallest property has {min(by_prop.values())} page(s) — {by_prop}"
        )

def test_web_overview_queries_present_and_shaped():
    p = _payload()
    # Daily web series for KPI row + trends (client-side date-filtered).
    daily = p["web_daily"]
    assert daily and {"property", "date", "users", "sessions", "views"} <= set(daily[0])
    # Traffic channels — grouped source/medium; expect the common buckets.
    chans = p["web_channels"]
    assert chans and {"property", "channel", "sessions", "users", "views"} <= set(chans[0])
    names = {r["channel"] for r in chans}
    assert {"Organic Search", "Direct"} <= names, f"channel grouping off: {names}"
    # Geography — regions AND cities per property.
    geo = p["web_geo"]
    assert geo and {"property", "level", "place", "sessions"} <= set(geo[0])
    assert {"region", "city"} <= {r["level"] for r in geo}
    # Device split + key on-site actions.
    dev = p["web_devices"]
    assert dev and {"property", "device", "sessions"} <= set(dev[0])
    ev = p["web_key_events"]
    assert ev and {"property", "event", "count"} <= set(ev[0])
    # Automatic GA4 events are excluded so the list is meaningful actions.
    assert "page_view" not in {r["event"] for r in ev}
