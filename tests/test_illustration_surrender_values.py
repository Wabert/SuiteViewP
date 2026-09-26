from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import (
    IllustrationEngine,
    ILLUSTRATION_TIMING,
    MonthContext,
    run_month,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    CoverageSegment,
    IllustrationPolicyData,
)


@pytest.mark.parametrize("company,subsidiary,cola,exempt", [
    ("26", "FFL", True, True),
    ("26", "FFL", False, False),
    ("01", "FFL", True, False),
    ("26", "ANICO", True, False),
])
@pytest.mark.parametrize("basis", ["CurrentSA", "OriginalSA"])
def test_cola_surrender_exemption_is_company_and_plan_specific(
    company, subsidiary, cola, exempt, basis,
):
    policy = IllustrationPolicyData(
        company_code=company,
        segments=[CoverageSegment(
            coverage_phase=4, is_cola=cola, units=25.0,
            original_face_amount=50_000.0, issue_date=date(2026, 1, 1),
        )],
    )
    config = PlancodeConfig(company_sub=subsidiary, sa_basis=basis)
    rates = IllustrationRates(scr=[0.0, 99.0], segment_scr={4: [0.0, 2.0]})
    _, total, rate_detail, charge_detail = calc_engine._calculate_surrender_charge(
        policy, rates, 1, date(2026, 1, 1), config)

    units = 50.0 if basis == "OriginalSA" else 25.0
    expected = 0.0 if exempt else units * 2.0
    assert total == expected
    assert charge_detail == {"cov1": expected}
    assert rate_detail == {"cov1": 0.0 if exempt else 2.0}


def test_seven_coverage_projection_keeps_exempt_cola_columns(monkeypatch):
    config = PlancodeConfig(
        company_sub="FFL", gint=0.0, dbd=0.0, premium_load="0",
        prem_flat_load=0.0, epu_code="0", mfee="0", poav_code="0",
        bonus="0", corridor_code=None, snet_period=0,
    )
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda *_: BonusConfig())
    policy = IllustrationPolicyData(
        company_code="26", plancode="TEST", issue_date=date(2026, 1, 1),
        valuation_date=date(2026, 1, 1), issue_age=45, attained_age=45,
        maturity_age=46, face_amount=700_000.0, units=700.0,
        account_value=10_000.0,
        segments=[CoverageSegment(
            coverage_phase=index * 2, is_cola=index > 1,
            issue_date=date(2026, 1, 1), face_amount=100_000.0, units=100.0,
        ) for index in range(1, 8)],
    )
    results = IllustrationEngine().project(
        policy, months=1, stop_on_lapse=False,
        rates_override=IllustrationRates(scr=[0.0, 2.0]),
        bonus_override=BonusConfig(),
    )
    assert len(results) == 2
    for state in results:
        assert state.surrender_charges_by_coverage == {
            f"cov{index}": 200.0 if index == 1 else 0.0
            for index in range(1, 8)
        }
        assert state.surrender_charge == 200.0
        assert state.ending_sv == state.av_end_of_month - 200.0 - state.policy_debt


def test_cola_face_reduction_does_not_charge_partial_surrender(monkeypatch):
    monkeypatch.setattr(calc_engine, "_reband_segment", lambda *a, **k: None)
    monkeypatch.setattr(calc_engine, "_reband_benefits", lambda *a: None)
    policy = IllustrationPolicyData(company_code="26", segments=[
        CoverageSegment(coverage_phase=1, face_amount=100_000.0, units=100.0),
        CoverageSegment(coverage_phase=4, face_amount=25_000.0, units=25.0, is_cola=True),
    ])
    result = calc_engine._reduce_base_face(
        policy, 30_000.0, IllustrationRates(scr=[0.0, 2.0]),
        date(2026, 1, 1), 1, charge_scr=True,
        config=PlancodeConfig(company_sub="FFL"),
    )
    assert result.cuts_by_phase == {4: 25_000.0, 1: 5_000.0}
    assert result.psc_by_phase == {4: 0.0, 1: 10.0}
    assert result.av_adjustment == -10.0


def test_withdrawal_receives_effective_cola_surrender_rates(monkeypatch):
    from suiteview.illustration.core.withdrawal_handler import WithdrawalResult

    seen = []

    def compute(av, policy, config, scr_rates, request, **kwargs):
        seen.append(scr_rates)
        return WithdrawalResult()

    monkeypatch.setattr(calc_engine, "compute_withdrawal", compute)
    monkeypatch.setattr(calc_engine, "get_corridor_factor", lambda *a: 1.0)
    policy = IllustrationPolicyData(company_code="26", segments=[
        CoverageSegment(coverage_phase=1),
        CoverageSegment(coverage_phase=4, is_cola=True),
    ])
    loan = SimpleNamespace(
        rg_loan_princ=0.0, rg_loan_accrued=0.0, pf_loan_princ=0.0,
        pf_loan_accrued=0.0, vbl_loan_princ=0.0, vbl_loan_accrued=0.0,
    )
    calc_engine._process_withdrawal(calc_engine.WithdrawalInput(
        state=MonthlyState(),
        policy=policy,
        config=PlancodeConfig(company_sub="FFL"),
        rates=IllustrationRates(scr=[0.0, 2.0]),
        rate_year=1,
        attained_age=45,
        month_date=date(2026, 1, 1),
        av=100_000.0,
        cost_basis=0.0,
        month_inputs=None,
        cap_loan=loan,
        is_anniversary=True,
        options=calc_engine.IllustrationOptions(),
    ))
    assert seen == [{1: 2.0, 4: 0.0}]


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

    result = run_month(
        MonthContext(
            state=state,
            policy=policy,
            config=config,
            rates=IllustrationRates(),
            bonus=BonusConfig(),
            month_inputs=None,
            options=calc_engine.IllustrationOptions(),
        ),
        ILLUSTRATION_TIMING,
    )

    assert result.av_after_exception == 100.0
    assert result.av_end_of_month > result.policy_debt
    assert result.av_less_loans == -10.0
    assert result.surrender_value == -10.0
    assert result.lapsed is True
    # Ending SV (RERUN vESV) derives from the END-of-month AV — EAV − FullSC −
    # ending loan balance — unlike the pre-interest lapse-check surrender_value.
    assert result.ending_sv == (
        result.av_end_of_month - result.surrender_charge - result.policy_debt
    )
    assert result.ending_sv > result.surrender_value


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