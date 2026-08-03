"""Unit tests for the base-banding rider rule (core.band_rules)."""

from suiteview.core.band_rules import rider_bands_as_base


def test_known_rider_bands_as_base():
    assert rider_bands_as_base("1U144A00") is True


def test_case_insensitive_and_trimmed():
    assert rider_bands_as_base(" 1u144a00 ") is True


def test_other_riders_do_not_band_as_base():
    assert rider_bands_as_base("1U135D00") is False
    assert rider_bands_as_base("") is False
    assert rider_bands_as_base(None) is False
