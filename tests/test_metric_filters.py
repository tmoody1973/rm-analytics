from datetime import date

import pytest

from metrics.filters import station_codes_for, period_cutoff


def test_station_codes_rm_maps_to_two_codes():
    assert station_codes_for("RM") == ["RM88", "RMORG"]


def test_station_codes_all_is_none():
    assert station_codes_for("ALL") is None
    assert station_codes_for(None) is None


def test_station_codes_unknown_raises():
    with pytest.raises(ValueError):
        station_codes_for("NOPE")


def test_period_cutoff_30d():
    assert period_cutoff("30d", today=date(2026, 6, 25)) == date(2026, 5, 26)


def test_period_cutoff_ytd():
    assert period_cutoff("ytd", today=date(2026, 6, 25)) == date(2026, 1, 1)


def test_period_cutoff_all_is_none():
    assert period_cutoff("all", today=date(2026, 6, 25)) is None


def test_period_cutoff_unknown_raises():
    with pytest.raises(ValueError):
        period_cutoff("forever", today=date(2026, 6, 25))
