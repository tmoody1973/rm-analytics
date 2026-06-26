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


def test_streaming_tlh_total_is_positive():
    out = run_metric("streaming_tlh")
    assert out["meta"]["unit"] == "hours"
    assert out["data"][0]["value"] > 0


def test_streaming_tlh_hyfin_less_than_all():
    all_tlh = run_metric("streaming_tlh")["data"][0]["value"]
    hyfin = run_metric("streaming_tlh", brand="HYFIN")["data"][0]["value"]
    assert 0 < hyfin < all_tlh


def test_streaming_tlh_group_by_station_returns_buckets():
    out = run_metric("streaming_tlh", group_by="station")
    assert {"bucket", "value"} <= set(out["data"][0].keys())
    assert len(out["data"]) >= 2  # at least RM88 + HYFIN


def test_streaming_tlh_bad_group_by_raises():
    with pytest.raises(ValueError):
        run_metric("streaming_tlh", group_by="weekday")
