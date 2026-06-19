from datetime import date

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


def test_engine_allows_negative_ending_surrender_value(monkeypatch):
    monkeypatch.setattr(
        calc_engine,
        "load_plancode",
        lambda _plancode: PlancodeConfig(
            plancode="TEST",
            gint=0.0,
            dbd=0.0,
            premium_load="0",
            prem_flat_load=0.0,
            epu_code="0",
            mfee="0",
            poav_code="0",
            bonus="0",
            corridor_code=None,
            snet_period=0,
            lapse_value="SV",
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _plancode, _date: BonusConfig())

    policy = IllustrationPolicyData(
        plancode="TEST",
        issue_date=date(2026, 1, 1),
        valuation_date=date(2026, 1, 1),
        issue_age=45,
        attained_age=45,
        maturity_age=46,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=10.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2026, 1, 1), face_amount=100_000.0, units=100.0)],
    )
    rates = IllustrationRates(scr=[0.0, 1.0])

    results = IllustrationEngine().project(
        policy,
        months=1,
        stop_on_lapse=False,
        rates_override=rates,
        bonus_override=BonusConfig(),
    )

    assert results[0].surrender_value == -90.0
    assert results[1].surrender_value == -90.0


def test_lapse_check_uses_policy_values_av_and_loan_cap_debt():
    policy = IllustrationPolicyData(
        plancode="TEST",
        issue_date=date(2026, 1, 1),
        valuation_date=date(2026, 1, 1),
        issue_age=45,
        attained_age=45,
        maturity_age=121,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=100.0,
        current_interest_rate=100.0,
        variable_loan_charge_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2026, 1, 1), face_amount=100_000.0, units=100.0)],
    )
    config = PlancodeConfig(
        plancode="TEST",
        gint=0.0,
        dbd=0.0,
        premium_load="0",
        prem_flat_load=0.0,
        epu_code="0",
        mfee="0",
        poav_code="0",
        bonus="0",
        corridor_code=None,
        snet_period=0,
        lapse_value="AV",
    )
    state = MonthlyState(
        date=date(2026, 1, 1),
        policy_year=1,
        policy_month=1,
        duration=1,
        attained_age=45,
        av_end_of_month=100.0,
        end_vbl_loan_princ=110.0,
    )

    result = IllustrationEngine().process_month(
        state,
        policy,
        config,
        IllustrationRates(),
        BonusConfig(),
    )

    assert result.av_after_exception == 100.0
    assert result.av_end_of_month > result.policy_debt
    assert result.av_less_loans == -10.0
    assert result.surrender_value == -10.0
    assert result.lapsed is True


def test_engine_does_not_take_monthly_deduction_on_maturity_date(monkeypatch):
    monkeypatch.setattr(
        calc_engine,
        "load_plancode",
        lambda _plancode: PlancodeConfig(
            plancode="TEST",
            maturity_age=46,
            gint=0.0,
            dbd=0.0,
            premium_load="0",
            prem_flat_load=0.0,
            epu_code="0",
            mfee="10",
            poav_code="0",
            bonus="0",
            corridor_code=None,
            snet_period=0,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _plancode, _date: BonusConfig())

    policy = IllustrationPolicyData(
        plancode="TEST",
        issue_date=date(2026, 1, 1),
        valuation_date=date(2026, 1, 1),
        issue_age=45,
        attained_age=45,
        maturity_age=46,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=1_000.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2026, 1, 1), face_amount=100_000.0, units=100.0)],
    )

    results = IllustrationEngine().project(
        policy,
        months=12,
        stop_on_lapse=False,
        rates_override=IllustrationRates(),
        bonus_override=BonusConfig(),
    )

    maturity = results[-1]
    assert maturity.date == date(2027, 1, 1)
    assert maturity.attained_age == 46
    assert maturity.total_deduction == 0.0
    assert maturity.mfee_charge == 0.0
    assert maturity.av_after_deduction == maturity.av_after_premium