"""Shape/discriminator checks for the Development Director tab Funraise queries (MOO-176)."""
from __future__ import annotations

import importlib

dashboard_api = importlib.import_module("service.dashboard_api")

EXPECTED_KEYS = (
    "donor_retention_trend",
    "donor_status_trend",
    "sustainer_flow",
    "ltv_tiers",
    "payment_method_mix",
    "donor_geo_state",
    "donor_geo_zip",
)

LTV_TIER_LABELS = {"<$100", "$100-499", "$500-999", "$1K-4,999", "$5K+"}


def _payload():
    return dashboard_api.dashboard_data()


def test_dev_keys_present():
    p = _payload()
    for k in EXPECTED_KEYS:
        assert k in p, f"missing payload key: {k}"


def test_all_dev_keys_non_empty():
    p = _payload()
    for k in EXPECTED_KEYS:
        assert p[k], f"payload key {k!r} is empty"


def test_donor_retention_trend_shape():
    rows = _payload()["donor_retention_trend"]
    assert rows, "donor_retention_trend empty"
    r = rows[0]
    assert "prior_year" in r, "missing prior_year"
    assert "cohort" in r, "missing cohort"
    assert "retention_pct" in r, "missing retention_pct"
    cohorts = {row["cohort"] for row in rows}
    assert cohorts <= {"first_year", "repeat"}, f"unexpected cohort values: {cohorts}"


def test_donor_status_trend_shape():
    rows = _payload()["donor_status_trend"]
    assert rows, "donor_status_trend empty"
    r = rows[0]
    assert "month" in r, "missing month"
    assert "new_donors" in r, "missing new_donors"
    assert "returning_donors" in r, "missing returning_donors"


def test_sustainer_flow_shape():
    rows = _payload()["sustainer_flow"]
    assert rows, "sustainer_flow empty"
    r = rows[0]
    assert "month" in r, "missing month"
    assert "added" in r, "missing added"
    assert "churned" in r, "missing churned"


def test_ltv_tiers_labels():
    rows = _payload()["ltv_tiers"]
    assert rows, "ltv_tiers empty"
    returned_tiers = {row["tier"] for row in rows}
    assert returned_tiers == LTV_TIER_LABELS, (
        f"ltv_tiers mismatch — got {returned_tiers}, expected {LTV_TIER_LABELS}"
    )


def test_payment_method_mix_shape():
    rows = _payload()["payment_method_mix"]
    assert rows, "payment_method_mix empty"
    r = rows[0]
    assert "method" in r, "missing method"
    assert "gifts" in r, "missing gifts"
    assert "total" in r, "missing total"


def test_donor_geo_state_shape():
    rows = _payload()["donor_geo_state"]
    assert rows, "donor_geo_state empty"
    r = rows[0]
    assert "state" in r, "missing state"
    assert "donors" in r, "missing donors"


def test_donor_geo_zip_shape():
    rows = _payload()["donor_geo_zip"]
    assert rows, "donor_geo_zip empty"
    r = rows[0]
    assert "zip" in r, "missing zip"
    assert "donors" in r, "missing donors"


# ── dev_kpis registry-backed shape tests ───────────────────────────────────

DEV_KPI_FIELDS = {"sustainer_share", "donor_retention_pct", "avg_gift", "avg_gift_mean", "new_donors", "lapsed_donors"}


def test_dev_kpis_key_present():
    p = _payload()
    assert "dev_kpis" in p, "payload missing dev_kpis key"


def test_dev_kpis_has_all_fields():
    kpis = _payload()["dev_kpis"]
    for field in DEV_KPI_FIELDS:
        assert field in kpis, f"dev_kpis missing field: {field}"


def test_dev_kpis_avg_gift_has_value_and_mean():
    kpis = _payload()["dev_kpis"]
    assert kpis["avg_gift"] is not None, "dev_kpis.avg_gift (median) is None"
    assert kpis["avg_gift_mean"] is not None, "dev_kpis.avg_gift_mean is None"
