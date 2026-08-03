"""Unit tests for the per-(plancode, benefit) charge rules registry."""

from suiteview.core.benefit_rate_rules import benefit_charge_factor

_ANNUAL_UNIT_TO_MONTHLY_PER_1000 = 1000.0 / 12.0


def test_known_quirk_returns_annual_unit_to_monthly_per_1000_factor():
    assert benefit_charge_factor("MLUL", "10") == _ANNUAL_UNIT_TO_MONTHLY_PER_1000
    assert benefit_charge_factor("MLUL502", "10") == _ANNUAL_UNIT_TO_MONTHLY_PER_1000


def test_factor_is_case_insensitive_and_trims_plancode():
    assert benefit_charge_factor(" mlul ", "10") == _ANNUAL_UNIT_TO_MONTHLY_PER_1000


def test_unlisted_plancode_or_benefit_has_no_adjustment():
    assert benefit_charge_factor("MLUL", "12") == 1.0
    assert benefit_charge_factor("OTHER", "10") == 1.0
    assert benefit_charge_factor("", "") == 1.0
