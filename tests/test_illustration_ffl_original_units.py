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
    # Pre-decrease (original) units of what remains; the increase decreased out no longer charges.
    assert full == pytest.approx(5.0 * 100.0)


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


# -- follow-up (10/5/2026 review): zero-face coverages and projected FFL withdrawals --------

def test_ffl_coverage_decreased_to_zero_has_no_original_units_basis():
    zero = CoverageSegment(coverage_phase=4, units=0.0, face_amount=0.0, original_face_amount=150_000.0)
    assert calc_engine.surrender_charge_units(zero, FFL) == 0.0
    issue = date(2015, 3, 1)
    policy = IllustrationPolicyData(company_code="26", issue_date=issue, segments=[
        _segment(100.0, 100.0, issue), _segment(30.0, 30.0, date(2018, 3, 1), phase=2)])
    flat = [None] + [5.0] * 30
    rates = IllustrationRates(segment_scr={1: flat, 2: flat})
    calc_engine._reduce_base_face(policy, 30_000.0, rates, date(2020, 6, 15), 1, False, FFL)
    assert [s.units for s in policy.segments] == [100.0, 0.0]
    full = calc_engine._calculate_surrender_charge(policy, rates, 1, date(2020, 6, 15), FFL, account_value=0.0)[1]
    assert full == pytest.approx(5.0 * 100.0)          # the removed increase no longer charges


def test_ffl_increase_then_decrease_keeps_the_original_units_of_what_remains():
    issue = date(2015, 3, 1)
    policy = IllustrationPolicyData(company_code="26", issue_date=issue, segments=[
        _segment(100.0, 100.0, issue), _segment(50.0, 50.0, date(2018, 3, 1), phase=2)])
    flat = [None] + [4.0] * 30
    rates = IllustrationRates(segment_scr={1: flat, 2: flat})
    on = date(2020, 6, 15)
    charge_scr = calc_engine._charge_face_decrease_surrender(policy, FFL, {})
    cut = calc_engine._reduce_base_face(policy, 20_000.0, rates, on, 1, charge_scr, FFL)
    assert cut.av_adjustment == 0.0 and [s.units for s in policy.segments] == [100.0, 30.0]
    full = calc_engine._calculate_surrender_charge(policy, rates, 1, on, FFL, account_value=0.0)[1]
    assert full == pytest.approx(4.0 * 150.0)


def test_original_units_below_current_units_are_used():
    """000200993 shape: CyberLife's original units (75.0, 98.01) are below current (75.05, 109.351)."""
    policy = IllustrationPolicyData(company_code="26", issue_date=date(1989, 9, 14), segments=[
        _segment(75.05, 75.0, date(1989, 9, 14)), _segment(109.351, 98.01, date(2013, 10, 14), phase=16)])
    assert [calc_engine.surrender_charge_units(s, FFL) for s in policy.segments] == [75.0, pytest.approx(98.01)]


@pytest.mark.parametrize("face, original, expected", [
    (80_000.0, 0.0, 80_000.0),          # missing original amount: current face
    (0.0, 50_000.0, 0.0),               # decreased out: no original basis
    (80_000.0, 100_000.0, 100_000.0),
])
def test_withdrawal_full_charge_face_with_zero_or_missing_original(face, original, expected):
    from suiteview.illustration.core.withdrawal_handler import _full_surrender_charge_face

    segment = CoverageSegment(coverage_phase=1, units=face / 1000.0, face_amount=face, original_face_amount=original)
    assert _full_surrender_charge_face(segment, FFL) == expected


def _withdrawal_policy(company="26"):
    issue = date(2015, 3, 1)
    policy = IllustrationPolicyData(company_code=company, issue_date=issue, db_option="A",
                                    segments=[_segment(100.0, 100.0, issue)])
    policy.face_amount = 100_000.0
    return policy


def _withdraw(policy, config, amount, monkeypatch):
    from suiteview.illustration.core.loan_handler import LoanState
    from suiteview.illustration.models.calc_state import MonthlyState
    from suiteview.illustration.models.input_set import IllustrationOptions

    monkeypatch.setattr(calc_engine, "_apply_withdrawal_face_decrease", lambda inputs, wd: calc_engine._reduce_base_face(
        inputs.policy, wd.face_decrease, inputs.rates, inputs.month_date, inputs.rate_year, False, inputs.config))
    rates = IllustrationRates(segment_scr={1: [None] + [20.0] * 30})
    wd = calc_engine._process_withdrawal(calc_engine.WithdrawalInput(
        state=MonthlyState(), policy=policy, config=config, rates=rates, rate_year=1, attained_age=50,
        month_date=date(2020, 6, 15), av=50_000.0, cost_basis=0.0,
        month_inputs=SimpleNamespace(withdrawal=amount, withdrawal_gross=0.0), cap_loan=LoanState(),
        is_anniversary=False, options=IllustrationOptions(), corridor_rate=1.0))
    full = calc_engine._calculate_surrender_charge(
        policy, rates, 1, date(2020, 7, 15), config, account_value=50_000.0)[1]
    return wd, full


FFL_WD = PlancodeConfig(company_sub="FFL", withdrawal_fee=25.0, md_holdback=0.0, min_face_after_wd=0.0)


def test_ffl_withdrawal_then_surrender_nets_the_partial_charge_already_taken(monkeypatch):
    """100 units at 20/unit: a 10,000 withdrawal cuts 10 units and charges 200 (plus the 25 fee);
    the full charge stays on the 100 original units (2,000) less the 200 already taken = 1,800."""
    policy = _withdrawal_policy()
    wd, full = _withdraw(policy, FFL_WD, 10_000.0, monkeypatch)
    assert wd.partial_sc == pytest.approx(200.0) and wd.reduces_sa
    assert full == pytest.approx(2_000.0 - 200.0)       # fee (25) is not part of the credit
    # A second withdrawal adds its charge; the credit never takes the charge below 0.
    wd2, full2 = _withdraw(policy, FFL_WD, 10_000.0, monkeypatch)
    assert full2 == pytest.approx(2_000.0 - 200.0 - wd2.partial_sc)
    from suiteview.illustration.core.withdrawal_handler import record_ffl_withdrawal_surrender_charge
    record_ffl_withdrawal_surrender_charge(policy, FFL_WD, 5_000.0)
    rates = IllustrationRates(segment_scr={1: [None] + [20.0] * 30})
    assert calc_engine._calculate_surrender_charge(
        policy, rates, 1, date(2020, 8, 15), FFL_WD, account_value=0.0)[1] == 0.0


def test_ffl_withdrawal_limit_nets_the_credit(monkeypatch):
    policy = _withdrawal_policy()
    _withdraw(policy, FFL_WD, 10_000.0, monkeypatch)
    from suiteview.illustration.core.withdrawal_handler import compute_withdrawal
    result = compute_withdrawal(50_000.0, policy, FFL_WD, {1: 20.0}, 0.0, corridor_rate=1.0, prior_total_md=0.0,
                                policy_debt=0.0, cost_basis=0.0, withdrawals_to_date=0.0, withdrawals_ytd=0.0,
                                is_anniversary=False)
    assert result.max_net_withdrawal == pytest.approx(50_000.0 - (2_000.0 - 200.0) - 25.0)


@pytest.mark.parametrize("company, config", [
    ("01", FFL_WD),
    ("26", PlancodeConfig(company_sub="ANICO", withdrawal_fee=25.0, md_holdback=0.0, min_face_after_wd=0.0)),
])
def test_withdrawal_credit_is_company_26_ffl_only(company, config, monkeypatch):
    policy = _withdrawal_policy(company)
    wd, full = _withdraw(policy, config, 10_000.0, monkeypatch)
    units = 100.0 if config.is_ffl else policy.segments[0].units
    assert wd.partial_sc == pytest.approx(200.0)
    assert full == pytest.approx(20.0 * units)

# -- second review (10/5/2026): withdrawal-zeroed coverages, history credit, lapse/loan use ----

def test_two_segment_withdrawal_keeps_the_zeroed_increase_and_nets_the_charge(monkeypatch):
    """Base 100 + increase 30 units at 20/unit (2,600). A 40,000 withdrawal charges 800 and
    takes the increase to zero; the full charge is 2,600 - 800 = 1,800, not 1,200."""
    issue = date(2015, 3, 1)
    policy = IllustrationPolicyData(company_code="26", issue_date=issue, db_option="A", segments=[
        _segment(100.0, 100.0, issue), _segment(30.0, 30.0, date(2018, 3, 1), phase=2)])
    policy.face_amount = 130_000.0
    wd, full = _withdraw_2(policy, 40_000.0, monkeypatch)
    assert wd.partial_sc == pytest.approx(800.0)
    assert policy.segments[1].units == 0.0
    assert full == pytest.approx(2_600.0 - 800.0)


def _withdraw_2(policy, amount, monkeypatch):
    from suiteview.illustration.core.loan_handler import LoanState
    from suiteview.illustration.models.calc_state import MonthlyState
    from suiteview.illustration.models.input_set import IllustrationOptions

    monkeypatch.setattr(calc_engine, "_apply_withdrawal_face_decrease", lambda inputs, wd: calc_engine._reduce_base_face(
        inputs.policy, wd.face_decrease, inputs.rates, inputs.month_date, inputs.rate_year, False, inputs.config))
    rates = IllustrationRates(segment_scr={1: [None] + [20.0] * 30, 2: [None] + [20.0] * 30})
    wd = calc_engine._process_withdrawal(calc_engine.WithdrawalInput(
        state=MonthlyState(), policy=policy, config=FFL_WD, rates=rates, rate_year=1, attained_age=50,
        month_date=date(2020, 6, 15), av=60_000.0, cost_basis=0.0,
        month_inputs=SimpleNamespace(withdrawal=amount, withdrawal_gross=0.0), cap_loan=LoanState(),
        is_anniversary=False, options=IllustrationOptions(), corridor_rate=1.0))
    full = calc_engine._calculate_surrender_charge(
        policy, rates, 1, date(2020, 7, 15), FFL_WD, account_value=60_000.0)[1]
    return wd, full


def _decrease_increase_out(policy):
    rates = IllustrationRates(segment_scr={1: [None] + [20.0] * 30, 2: [None] + [20.0] * 30})
    calc_engine._reduce_base_face(policy, policy.segments[1].face_amount, rates, date(2020, 6, 15), 1,
                                  calc_engine._charge_face_decrease_surrender(policy, FFL_WD, {}), FFL_WD)


@pytest.mark.parametrize("order", ["withdrawal first", "decrease first"])
def test_withdrawal_before_or_after_a_decrease(order, monkeypatch):
    """Base 100 + increase 30 at 20/unit. A 10,000 withdrawal (charge 200) and an elective
    decrease that removes what is left of the increase: the increase removed by the decrease
    drops out and the withdrawal charge is netted, in either order: 100 x 20 - 200 = 1,800."""
    issue = date(2015, 3, 1)
    policy = IllustrationPolicyData(company_code="26", issue_date=issue, db_option="A", segments=[
        _segment(100.0, 100.0, issue), _segment(30.0, 30.0, date(2018, 3, 1), phase=2)])
    policy.face_amount = 130_000.0
    if order == "decrease first":
        _decrease_increase_out(policy)
        wd, _ = _withdraw_2(policy, 10_000.0, monkeypatch)
    else:
        wd, _ = _withdraw_2(policy, 10_000.0, monkeypatch)
        _decrease_increase_out(policy)
    assert wd.partial_sc == pytest.approx(200.0)
    rates = IllustrationRates(segment_scr={1: [None] + [20.0] * 30, 2: [None] + [20.0] * 30})
    full = calc_engine._calculate_surrender_charge(policy, rates, 1, date(2020, 7, 15), FFL_WD, account_value=0.0)[1]
    assert policy.segments[1].units == 0.0
    assert full == pytest.approx(100.0 * 20.0 - 200.0)


def _credited_policy(credit):
    from suiteview.illustration.core.withdrawal_handler import record_ffl_withdrawal_surrender_charge

    policy = IllustrationPolicyData(
        company_code="26", plancode="TEST", issue_date=date(2016, 1, 1), valuation_date=date(2026, 1, 1),
        issue_age=45, attained_age=55, maturity_age=56, face_amount=100_000.0, units=100.0,
        account_value=10_000.0, segments=[_segment(100.0, 100.0, date(2016, 1, 1))])
    record_ffl_withdrawal_surrender_charge(policy, FFL_WD, credit)
    return policy


def test_lapse_test_and_surrender_value_use_the_netted_charge(monkeypatch):
    from suiteview.illustration.core.bonus_rates import BonusConfig

    config = PlancodeConfig(company_sub="FFL", gint=0.0, dbd=0.0, prem_flat_load=0.0)
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())

    def run(credit):
        return calc_engine.IllustrationEngine().project(
            _credited_policy(credit), months=1, stop_on_lapse=False,
            rates_override=IllustrationRates(scr=[None] + [20.0] * 30), bonus_override=BonusConfig())[-1]

    plain, netted = run(0.0), run(300.0)
    assert plain.surrender_charge == pytest.approx(2_000.0)
    assert netted.surrender_charge == pytest.approx(1_700.0)
    assert netted.ending_sv - plain.ending_sv == pytest.approx(300.0)
    assert netted.surrender_value - plain.surrender_value == pytest.approx(300.0)   # lapse-test value


def test_loan_cap_uses_the_netted_charge():
    from suiteview.illustration.core.loan_handler import LoanState

    def loan(credit):
        work = SimpleNamespace(rate_year=1, month_date=date(2026, 2, 1), av=10_000.0, cap_loan=LoanState(),
                               ded=SimpleNamespace(total_deduction=0.0),
                               prem=SimpleNamespace(premiums_to_date=0.0), withdrawals_to_date=0.0)
        ctx = SimpleNamespace(options=SimpleNamespace(restrict_loans_to_sv=True), policy=_credited_policy(credit),
                              rates=IllustrationRates(segment_scr={1: [None] + [20.0] * 30}), config=FFL_WD,
                              month_inputs=SimpleNamespace(regular_loan=1_000_000.0))
        calc_engine.apply_new_loans(ctx, work)
        return work.applied_regular_loan + work.applied_preferred_loan

    assert loan(0.0) == pytest.approx(10_000.0 - 2_000.0)
    assert loan(300.0) == pytest.approx(10_000.0 - 1_700.0)


def _history(*events):
    return [SimpleNamespace(trans_date=day, trans_code=code, raw_data={"CHARGE_AMT": charge})
            for day, code, charge in events]


def test_inforce_history_seeds_the_credit_net_of_the_fee():
    from suiteview.illustration.core.withdrawal_handler import (
        ffl_current_units_fallback, ffl_withdrawal_surrender_credit, seed_ffl_withdrawal_history)

    policy = _withdrawal_policy()
    # 000330798 shape: SN 2018-08-09 CHARGE_AMT 1,219.41 (fee 25 inside); two fund rows of one event.
    seed_ffl_withdrawal_history(policy, FFL_WD, _history(
        (date(2018, 8, 9), "SN", 1_000.00), (date(2018, 8, 9), "SN", 219.41), (date(2017, 1, 3), "SG", 0.0)),
        withdrawal_count=2, fee=25.0)
    assert ffl_withdrawal_surrender_credit(policy, FFL_WD) == pytest.approx(1_194.41)
    assert not ffl_current_units_fallback(policy)


@pytest.mark.parametrize("transactions, count", [
    (None, 1),                                                     # FH_FIXED unreadable
    (_history((date(2018, 8, 9), "SN", 500.0)), 2),                # purged: fewer events than TOT_WTD_QTY
])
def test_incomplete_history_falls_back_to_current_units(transactions, count):
    from suiteview.illustration.core.withdrawal_handler import (
        ffl_current_units_fallback, ffl_withdrawal_surrender_credit, seed_ffl_withdrawal_history)

    policy = _withdrawal_policy()
    policy.segments[0].units, policy.segments[0].face_amount = 80.0, 80_000.0
    seed_ffl_withdrawal_history(policy, FFL_WD, transactions, withdrawal_count=count, fee=25.0)
    assert ffl_current_units_fallback(policy)
    assert ffl_withdrawal_surrender_credit(policy, FFL_WD) == 0.0
    assert calc_engine.surrender_charge_units(policy.segments[0], FFL_WD, policy) == 80.0
    rates = IllustrationRates(segment_scr={1: [None] + [20.0] * 30})
    assert calc_engine._calculate_surrender_charge(
        policy, rates, 1, date(2020, 7, 15), FFL_WD, account_value=0.0)[1] == pytest.approx(1_600.0)

def test_polview_reports_the_history_credit_in_the_surrender_tip():
    from suiteview.polview.services.policy_prefetch import _surrender_values
    from suiteview.polview.ui.tabs import adv_prod_tooltips

    basis = _credited_policy(1_194.41)
    state = SimpleNamespace(scr_rates_by_coverage={"cov1": 20.0}, surrender_charges_by_coverage={"cov1": 2_000.0},
                            surrender_charge=805.59, surrender_value=9_194.41, policy_debt=0.0)
    values = _surrender_values(basis, FFL_WD, IllustrationRates(), state)
    assert values.withdrawal_credit == pytest.approx(1_194.41) and values.original_units_basis
    tip = adv_prod_tooltips.surrender_charge_tip(values)
    assert "- Partial surrender charges already taken on withdrawals: 1,194.41" in tip
    assert tip.endswith("= 805.59")