"""FFL UL surrender charge after a specified-amount decrease is on the ORIGINAL units.

Robert's 10/5/2026 ruling: "switch FFL to the original. That makes sense since FFL doesn't charge a
partial surrender charge on a decrease." Company-26 FFL UL per-unit (rule 6) plans keep
``SA_Basis = CurrentSA`` (it also drives the COI band, EPU, targets and withdrawals); only the
surrender charge basis changes, and a face decrease takes no partial surrender charge.

The CyberLife cases are live CKPR ``FH_FIXED`` TRANS 'SF' full surrenders (no loan) on reduced-face
policies, with the plan's loaded per-unit ``SCR`` schedule; the charge is truncated to cents.
"""
from datetime import date
from decimal import ROUND_DOWN, Decimal
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.withdrawal_handler import compute_withdrawal
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

FFL = PlancodeConfig(company_sub="FFL")
ANICO = PlancodeConfig(company_sub="ANICO")


def _segment(units, original_units, issue=date(2010, 1, 1), phase=1, vpu=1000.0):
    return CoverageSegment(coverage_phase=phase, issue_date=issue, units=units, face_amount=units * vpu,
                           original_face_amount=original_units * vpu, vpu=vpu)


def test_ffl_per_unit_plans_charge_original_units_and_keep_current_sa():
    segment = _segment(50.0, 100.0)
    assert FFL.sa_basis == "CurrentSA" and FFL.partial_surrender_charge
    assert FFL.surrender_charge_on_original_units and not FFL.face_decrease_surrender_charge
    assert calc_engine.surrender_charge_units(segment, FFL) == 100.0
    assert calc_engine.surrender_charge_units(_segment(50.0, 100.0, vpu=500.0), FFL) == 100.0
    assert calc_engine.surrender_charge_units(segment, ANICO) == 50.0
    assert ANICO.face_decrease_surrender_charge


@pytest.mark.parametrize("config", [
    PlancodeConfig(company_sub="FFL", product_family="ISWL"),
    PlancodeConfig(company_sub="FFL", scr_pct_of_surrender_target=(0.5, 0.4)),
    PlancodeConfig(company_sub="ANICO"),
    None,
])
def test_other_plans_keep_current_units(config):
    assert calc_engine.surrender_charge_units(_segment(50.0, 100.0), config) == 50.0


def test_missing_original_amount_falls_back_to_current_units():
    segment = CoverageSegment(coverage_phase=1, units=50.0, face_amount=50_000.0)
    assert calc_engine.surrender_charge_units(segment, FFL) == 50.0


def _charge(policy, rates, on, config=FFL) -> Decimal:
    _, _, rate_by, _ = calc_engine._calculate_surrender_charge(
        policy, rates, 1, on, config, account_value=0.0)
    total = sum((Decimal(repr(rate_by[f"cov{i}"])) * Decimal(repr(calc_engine.surrender_charge_units(s, config)))
                 for i, s in enumerate(policy.segments, start=1)), Decimal(0))
    return total.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


@pytest.mark.parametrize("policy_id, issue, on, units, original_units, schedule, charge", [
    # NU1F3P00: year 10, m 0 = rate(9) 12.17 x 100 original units (50 current).
    ("000306376", date(2007, 9, 5), date(2016, 9, 8), 50.0, 100.0, {9: 12.17, 10: 11.06}, "1217.00"),
    # NU1F3P00: year 11, m 11: 4.6 + 0.51 x 0.08333 = 4.642 x 1,000 original units (600 current).
    ("000306892", date(2007, 12, 27), date(2018, 12, 26), 600.0, 1000.0, {10: 5.11, 11: 4.6}, "4642.00"),
    # 1U1F4N00: year 5, m 5: 12.75 + 0.85 x 0.58333 = 13.246 x 1,500 original units (500 current).
    ("000326197", date(2012, 2, 28), date(2016, 8, 23), 500.0, 1500.0, {4: 13.6, 5: 12.75}, "19869.00"),
    # 1U14I200: year 7, m 9: 13.47 + 1.04 x 0.25 = 13.73 x 397.164 original units (206.165 current).
    ("000338977", date(2014, 7, 15), date(2021, 5, 14), 206.165, 397.164, {6: 14.51, 7: 13.47}, "5453.06"),
])
def test_reduced_face_ffl_surrender_matches_cyberlife_on_original_units(
        policy_id, issue, on, units, original_units, schedule, charge):
    policy = IllustrationPolicyData(company_code="26", issue_date=issue,
                                    segments=[_segment(units, original_units, issue)])
    values = [None] + [0.0] * 30
    for year, rate in schedule.items():
        values[year] = rate
    rates = IllustrationRates(segment_scr={1: values})
    assert _charge(policy, rates, on) == Decimal(charge), policy_id


def _decrease(config, decrease_charge_allowed=None):
    """A projected elective decrease of 40 units, newest coverage first, then the full charge."""
    issue = date(2015, 3, 1)
    policy = IllustrationPolicyData(
        company_code="26", issue_date=issue, decrease_charge_allowed=decrease_charge_allowed,
        segments=[_segment(100.0, 100.0, issue), _segment(30.0, 30.0, date(2018, 3, 1), phase=2)])
    policy.face_amount = 130_000.0
    flat = [None] + [5.0] * 30
    rates = IllustrationRates(segment_scr={1: flat, 2: flat})
    on = date(2020, 6, 15)
    charge_scr = calc_engine._charge_face_decrease_surrender(policy, config, {})
    cut = calc_engine._reduce_base_face(policy, 40_000.0, rates, on, 1, charge_scr, config)
    full = calc_engine._calculate_surrender_charge(policy, rates, 1, on, config, account_value=0.0)[1]
    return charge_scr, cut, full, policy


def test_ffl_face_decrease_takes_no_partial_charge_and_keeps_the_full_charge():
    charge_scr, cut, full, policy = _decrease(FFL)
    assert not charge_scr and cut.av_adjustment == 0.0 and cut.psc_by_phase == {}
    assert cut.cuts_by_phase == {2: 30_000.0, 1: 10_000.0}
    assert [s.units for s in policy.segments] == [90.0, 0.0]
    assert full == pytest.approx(5.0 * 130.0)          # pre-decrease (original) units


def test_current_sa_plan_still_charges_the_decrease_and_reduces_the_full_charge():
    charge_scr, cut, full, _ = _decrease(ANICO)
    assert charge_scr and cut.av_adjustment == pytest.approx(-5.0 * 40.0)
    assert full == pytest.approx(5.0 * 90.0)
    assert not _decrease(ANICO, decrease_charge_allowed=False)[0]


def test_ffl_withdrawal_keeps_its_partial_charge_and_limit_uses_original_units():
    """Withdrawals are unchanged: CyberLife books a partial surrender charge on FFL withdrawals
    (FH_FIXED 'SN' rows). The maximum withdrawal nets the full charge on original units."""
    issue = date(2015, 3, 1)
    policy = IllustrationPolicyData(company_code="26", issue_date=issue, db_option="A",
                                    segments=[_segment(80.0, 100.0, issue)])
    policy.face_amount = 80_000.0
    config = PlancodeConfig(company_sub="FFL", withdrawal_fee=0.0, md_holdback=0.0, min_face_after_wd=0.0)
    result = compute_withdrawal(20_000.0, policy, config, {1: 5.0}, 1_000.0,
                                corridor_rate=1.0, prior_total_md=0.0, policy_debt=0.0, cost_basis=0.0,
                                withdrawals_to_date=0.0, withdrawals_ytd=0.0, is_anniversary=False)
    assert result.max_net_withdrawal == pytest.approx(20_000.0 - 5.0 * 100.0)
    assert result.partial_sc == pytest.approx(5.0 * 1.0)


def test_policy_prefetch_reports_the_original_units_basis_for_ffl():
    from suiteview.polview.services.policy_prefetch import _surrender_values

    basis = SimpleNamespace(segments=[_segment(50.0, 100.0)], base_segment=None, account_value=1000.0,
                            valuation_date=date(2026, 9, 1))
    state = SimpleNamespace(scr_rates_by_coverage={"cov1": 2.0}, surrender_charges_by_coverage={"cov1": 200.0},
                            surrender_charge=200.0, surrender_value=800.0, policy_debt=0.0)
    values = _surrender_values(basis, FFL, IllustrationRates(), state)
    assert values.original_units_basis and values.coverages[0].units == 100.0
