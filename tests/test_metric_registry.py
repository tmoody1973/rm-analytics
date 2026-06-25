import pytest

from metrics.registry import REGISTRY, run_metric


def test_sustainer_mrr_matches_known_floor():
    out = run_metric("sustainer_mrr")
    assert out["meta"]["unit"] == "usd"
    assert out["meta"]["source"] == "funraise.fact_subscriptions"
    value = out["data"][0]["value"]
    # ~$47.5K active monthly MRR loaded (handoff 2026-06-25); guard a sane floor.
    assert value is not None and value > 40000


def test_active_donors_is_positive_count():
    out = run_metric("active_donors")
    assert out["meta"]["unit"] == "count"
    assert out["data"][0]["value"] > 0


def test_unknown_metric_raises_keyerror():
    with pytest.raises(KeyError):
        run_metric("does_not_exist")
