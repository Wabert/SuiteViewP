"""Reinstatement start basis: lapse values restored on the reinstatement date (no database)."""
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.reinstatement_start import (
    PREMIUMS_AFTER_VALUATION_NOT_APPLICABLE,
    REINSTATED_PREMIUM_PAY_STATUS,
    ReinstatementStartError,
    build_reinstated_policy,
)
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    DatedTransaction,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
)
from suiteview.polview.services import reinstatement as rein

YEARS = 40
ISSUE = date(2015, 3, 15)
VALUES = date(2026, 4, 15)       # policy year 12, month 2
LAPSE = date(2026, 5, 15)
SAME_YEAR = date(2026, 10, 15)   # policy year 12, month 8
NEXT_YEAR = date(2027, 4, 15)    # policy year 13, month 2
CONFIG = PlancodeConfig(plancode="SYNTHETIC")


def make_policy(**changes) -> IllustrationPolicyData:
    values = dict(
        policy_number="SYNTHETIC", plancode="SYNTHETIC", product_type="UL",
        premium_pay_status_code="99",
        issue_date=ISSUE, valuation_date=VALUES, issue_age=40, attained_age=51,
        policy_year=12, policy_month=2, duration=134, maturity_age=121,
        face_amount=100000.0, units=100.0, account_value=850.0,
        premiums_paid_to_date=12000.0, premiums_ytd=300.0, ctp=1200.0,
        glp=1200.0, accumulated_glp=14000.0,
        map_cease_date=date(2030, 3, 15),
        regular_loan_principal=400.0, regular_loan_accrued=12.34,
        preferred_loan_principal=100.0, preferred_loan_accrued=1.66,
        segments=[CoverageSegment(
            issue_date=ISSUE, issue_age=40, face_amount=100000.0,
            original_face_amount=100000.0, units=100.0, rate_sex="M", rate_class="N")],
    )
    values.update(changes)
    return IllustrationPolicyData(**values)


def make_rates(**changes) -> IllustrationRates:
    values = dict(
        segment_coi={1: [None] + [0.12] * YEARS},
        segment_epu={1: [None] + [0.05] * YEARS},
        segment_scr={1: [None] + [10.0 - 0.5 * year for year in range(YEARS)]},
        mfee=[None] + [7.5] * YEARS,
        tpp=[None] + [0.05] * YEARS,
        epp=[None] + [0.05] * YEARS,
    )
    values.update(changes)
    return IllustrationRates(**values)


def start(policy=None, when=SAME_YEAR, rates=None):
    return build_reinstated_policy(
        policy or make_policy(), CONFIG, rates or make_rates(),
        lapse_date=LAPSE, reinstatement_date=when)


def ccv(**changes) -> BenefitInfo:
    values = dict(
        coverage_phase=1, benefit_type="A", benefit_subtype="1", units=100.0,
        vpu=1000.0, issue_date=ISSUE, issue_age=40, pay_up_date=date(2096, 3, 15),
        cease_date=date(2096, 3, 15), coi_rate=0.25, is_active=True)
    values.update(changes)
    return BenefitInfo(**values)


def test_lapse_av_is_injected_before_the_reinstatement_date_deduction():
    source = make_policy()
    result = start(source)
    policy = result.policy
    expected = calculate_deduction(
        850.0, policy, CONFIG, make_rates(), 12, 51, 12000.0,
        projection_date=SAME_YEAR, bln_round_charge=True).total_deduction
    assert result.monthly_deduction == pytest.approx(expected, abs=0.005)
    assert result.monthly_deduction > 0
    assert result.account_value_before_deduction == 850.0
    assert policy.account_value == pytest.approx(850.0 - result.monthly_deduction)
    assert policy.system_monthly_deduction == result.monthly_deduction
    assert (policy.system_coi_charge + policy.system_expense_charge
            + policy.system_other_charge) == pytest.approx(result.monthly_deduction)
    assert source.account_value == 850.0 and source.valuation_date == VALUES


def test_illustration_starts_on_the_reinstatement_date_and_forecasts_the_next_monthliversary():
    result = start()
    policy = result.policy
    assert policy.valuation_date == SAME_YEAR
    assert result.forecast_date == date(2026, 11, 15)
    assert (policy.policy_year, policy.policy_month, policy.duration) == (12, 8, 140)
    assert policy.attained_age == 51
    assert policy.premium_pay_status_code == REINSTATED_PREMIUM_PAY_STATUS
    assert policy.rollback_snapshots == []
    assert policy.premiums_after_valuation == []
    assert policy.premiums_after_valuation_error == PREMIUMS_AFTER_VALUATION_NOT_APPLICABLE
    assert policy.starting_basis_assumptions[0].startswith("REINSTATEMENT: lapsed 05/15/2026")
    assert policy.reinstatement_date == SAME_YEAR


def test_reinstatement_date_deduction_matches_the_polview_quote():
    basis = rein.build_reinstatement_basis(
        make_policy(), CONFIG, make_rates(),
        eligibility=rein.ReinstatementEligibility("Q", "Termination - Lapse", True, ""),
        lapse_date=LAPSE, today=SAME_YEAR)
    quote = basis.quote(SAME_YEAR)
    assert start(basis.policy).monthly_deduction == pytest.approx(float(quote.deduction.total))


def test_accrued_loan_interest_is_reinstated_as_is_within_the_policy_year():
    result = start()
    policy = result.policy
    assert result.anniversaries_crossed == 0
    assert result.loan_interest_capitalized == 0.0
    assert (policy.regular_loan_principal, policy.regular_loan_accrued) == (400.0, 12.34)
    assert (policy.preferred_loan_principal, policy.preferred_loan_accrued) == (100.0, 1.66)
    assert policy.premiums_ytd == 300.0
    assert policy.accumulated_glp == 14000.0


def test_crossing_an_anniversary_capitalizes_loan_interest():
    result = start(make_policy(impaired_fund_values={"FX": 500.0}), when=NEXT_YEAR)
    policy = result.policy
    assert result.anniversaries_crossed == 1
    assert result.loan_interest_capitalized == pytest.approx(14.0)
    assert (policy.regular_loan_principal, policy.regular_loan_accrued) == (412.34, 0.0)
    assert (policy.preferred_loan_principal, policy.preferred_loan_accrued) == (101.66, 0.0)
    assert policy.impaired_fund_values == {"FX": 514.0}
    assert (policy.policy_year, policy.policy_month, policy.attained_age) == (13, 2, 52)
    assert policy.premiums_ytd == 0.0
    assert policy.accumulated_glp == 15200.0
    assert any("accrued interest added" in note for note in policy.starting_basis_assumptions)


def test_ccv_is_terminated_and_not_charged():
    result = start(make_policy(benefits=[ccv()], ccv_active=True, ccv_units=100.0,
                               shadow_account_value=2500.0))
    policy = result.policy
    plain = start().monthly_deduction
    assert result.ccv_terminated
    assert policy.ccv_active is False and policy.ccv_ceased is True
    assert policy.has_shadow_account is False
    assert policy.shadow_account_value == 0.0
    assert policy.benefits[0].is_active is False
    assert policy.benefits[0].cease_date == LAPSE
    assert result.monthly_deduction == pytest.approx(plain)


@pytest.mark.parametrize("map_cease,expected", [
    (date(2030, 3, 15), LAPSE),
    (None, LAPSE),
    (date(2025, 3, 15), date(2025, 3, 15)),
])
def test_map_period_remains_terminated(map_cease, expected):
    assert start(make_policy(map_cease_date=map_cease)).policy.map_cease_date == expected


def test_fund_values_keep_their_split_of_the_starting_account_value():
    result = start(make_policy(fund_values={"FX": 600.0, "SW": 250.0}))
    funds = result.policy.fund_values
    assert sum(funds.values()) == pytest.approx(result.policy.account_value, abs=0.02)
    assert funds["FX"] / funds["SW"] == pytest.approx(600.0 / 250.0, rel=1e-3)


@pytest.mark.parametrize("when,message", [
    (date(2026, 4, 15), "before the lapse date"),
    (date(2026, 10, 20), "not a monthliversary"),
    (date(2096, 3, 15), "at or after maturity"),
])
def test_invalid_reinstatement_dates_are_refused(when, message):
    with pytest.raises(ReinstatementStartError, match=message):
        start(when=when)


def _offline_engine(monkeypatch):
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plancode: CONFIG)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_args: BonusConfig())
    monkeypatch.setattr(calc_engine, "compute_target_premiums", lambda *_a, **_k: TargetPremiumResult())
    monkeypatch.setattr(calc_engine, "build_target_detail_snapshots", lambda *_a, **_k: ({}, {}))
    monkeypatch.setattr(calc_engine, "_coverage_after_change_snapshot", lambda *_a, **_k: {})


def _project(result, lumpsum: float, months: int = 2):
    inputs = IllustrationInputSet(dated_transactions=[DatedTransaction(
        kind=TransactionKind.PREMIUM, effective_date=result.forecast_date,
        amount=lumpsum, subtype="manual_lumpsum")])
    return IllustrationEngine().project(
        result.policy, months=months, future_inputs=inputs, rates_override=make_rates(),
        stop_on_lapse=False,
        options=IllustrationOptions(conform_to_tefra=False, conform_to_tamra=False),
        bonus_override=BonusConfig())


def test_engine_starts_from_the_reinstated_basis_and_pays_the_forecast_lumpsum(monkeypatch):
    _offline_engine(monkeypatch)
    result = start()
    states = _project(result, 2000.0)
    opening, first = states[0], states[1]
    assert opening.date == SAME_YEAR
    assert opening.md_check_av_before_deduction == pytest.approx(850.0)
    assert opening.md_check_calculated_deduction == pytest.approx(result.monthly_deduction)
    assert opening.md_check_deduction_variance == pytest.approx(0.0, abs=0.005)
    assert first.date == result.forecast_date
    assert first.policy_year == 12 and first.policy_month == 9
    assert not first.lapsed


def test_quoted_reinstatement_premium_keeps_a_negative_lapse_av_in_force(monkeypatch):
    _offline_engine(monkeypatch)
    lapsed = make_policy(account_value=-25.0, regular_loan_principal=0.0,
                         regular_loan_accrued=0.0, preferred_loan_principal=0.0,
                         preferred_loan_accrued=0.0)
    basis = rein.build_reinstatement_basis(
        lapsed, CONFIG, make_rates(),
        eligibility=rein.ReinstatementEligibility("Q", "Termination - Lapse", True, ""),
        lapse_date=LAPSE, today=SAME_YEAR)
    premium = float(basis.quote(SAME_YEAR).premium.premium)
    result = start(basis.policy)
    assert result.policy.account_value < 0
    first = _project(result, premium, months=1)[1]
    assert not first.lapsed
    assert first.av_end_of_month > 0
