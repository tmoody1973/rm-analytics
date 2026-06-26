"""Shape/discriminator checks for the Board view Nielsen cume queries (MOO-176)."""
from __future__ import annotations

import importlib

dashboard_api = importlib.import_module("service.dashboard_api")


def _payload():
    return dashboard_api.dashboard_data()


def test_board_keys_present():
    p = _payload()
    assert "nielsen_cume" in p, "missing payload key: nielsen_cume"
    assert "nielsen_cume_trend" in p, "missing payload key: nielsen_cume_trend"


def test_nielsen_cume_non_empty():
    rows = _payload()["nielsen_cume"]
    assert rows, "nielsen_cume is empty"


def test_nielsen_cume_shape():
    rows = _payload()["nielsen_cume"]
    assert rows, "nielsen_cume is empty"
    r = rows[0]
    assert "station_code" in r, "nielsen_cume row missing station_code"
    assert "cume" in r, "nielsen_cume row missing cume"
    assert isinstance(r["cume"], (int, float)), (
        f"nielsen_cume.cume is not numeric: {type(r['cume'])}"
    )


def test_nielsen_cume_trend_shape():
    rows = _payload()["nielsen_cume_trend"]
    assert rows, "nielsen_cume_trend is empty"
    r = rows[0]
    assert "station_code" in r, "nielsen_cume_trend row missing station_code"
    assert "period_label" in r, "nielsen_cume_trend row missing period_label"
    assert "period_date" in r, "nielsen_cume_trend row missing period_date"
    assert "cume" in r, "nielsen_cume_trend row missing cume"
