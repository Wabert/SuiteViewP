from decimal import Decimal
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.input_applier import apply_cash_flow_inputs
from suiteview.illustration.core.input_compiler import CompiledMonthInputs
from suiteview.illustration.core.loan_handler import (
    LoanState,
    accrue_loan_interest,
    apply_new_fixed_loan,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData
from suiteview.polview.models.cl_polrec.CL_POLREC_20_77 import LoanRecords


class _FakeLoanPolicy:
    is_advanced_product = True

    def __init__(self, loan_type="7"):
        self.loan_type = loan_type

    def data_item(self, table_name, field_name, index=0):
        if table_name == "LH_BAS_POL" and field_name == "LN_TYP_CD":
            return self.loan_type
        return None

    def fetch_table(self, table_name):
        if table_name != "LH_FND_VAL_LOAN":
            return []
        return [
            {"MVRY_DT": "2025-01-01", "FND_ID_CD": "LZ", "LN_CRG_ITS_RT": "0.061"},
            {"MVRY_DT": "2025-07-01", "FND_ID_CD": "AA", "LN_CRG_ITS_RT": "0.065"},
            {"MVRY_DT": "2025-07-01", "FND_ID_CD": "LZ", "LN_CRG_ITS_RT": "0.067"},
        ]


def test_fixed_loan_prefers_preferred_capacity_first():
    loan = LoanState(rg_loan_princ=50.0, pf_loan_princ=25.0)

    updated = apply_new_fixed_loan(
        loan=loan,
        requested_amount=120.0,
        account_value=500.0,
        premiums_to_date=300.0,
        withdrawals_to_date=50.0,
    )

    # Preferred capacity = 500 - 75 - (300 - 50) = 175
    assert updated.pf_loan_princ == 145.0
    assert updated.rg_loan_princ == 50.0


def test_fixed_loan_spills_excess_to_regular():
    loan = LoanState(rg_loan_princ=50.0, pf_loan_princ=25.0)

    updated = apply_new_fixed_loan(
        loan=loan,
        requested_amount=250.0,
        account_value=500.0,
        premiums_to_date=300.0,
        withdrawals_to_date=50.0,
    )

    # Preferred capacity = 175, remaining 75 goes to regular.
    assert updated.pf_loan_princ == 200.0
    assert updated.rg_loan_princ == 125.0


def test_fixed_loan_uses_preferred_capacity_without_availability_gate():
    loan = LoanState(rg_loan_princ=10.0, pf_loan_princ=5.0)

    updated = apply_new_fixed_loan(
        loan=loan,
        requested_amount=80.0,
        account_value=500.0,
        premiums_to_date=0.0,
        withdrawals_to_date=0.0,
    )

    assert updated.rg_loan_princ == 10.0
    assert updated.pf_loan_princ == 85.0


def test_variable_loan_accrues_with_policy_rate_without_collateral_split():
    config = PlancodeConfig(
        loan_type="Arrears",
        loan_charge_rate_guar=0.06,
        pref_loan_charge_rate_guar=0.05,
    )
    loan = LoanState(
        rg_loan_princ=100.0,
        pf_loan_princ=200.0,
        vbl_loan_princ=1_000.0,
        vbl_loan_accrued=10.0,
    )

    updated = accrue_loan_interest(
        loan,
        config,
        days_in_month=31,
        variable_loan_charge_rate=0.08,
    )

    expected_variable_charge = 1_000.0 * 0.08 * 31 / 365.0
    assert updated.vbl_loan_charge == pytest.approx(expected_variable_charge)
    assert updated.vbl_loan_accrued == pytest.approx(10.0 + expected_variable_charge)
    assert updated.reg_loan_charge == pytest.approx(100.0 * 0.06 * 31 / 365.0)
    assert updated.pref_loan_charge == pytest.approx(200.0 * 0.05 * 31 / 365.0)


def test_engine_loan_accrual_honors_exact_days_option(monkeypatch):
    monkeypatch.setattr(
        calc_engine,
        "load_plancode",
        lambda _plancode: PlancodeConfig(
            plancode="TEST",
            interest_method="ExactDays",
            loan_type="Arrears",
            loan_charge_rate_guar=0.12,
            pref_loan_charge_rate_guar=0.12,
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
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _plancode, _date: BonusConfig())
    policy = IllustrationPolicyData(
        plancode="TEST",
        issue_date=date(2026, 1, 15),
        valuation_date=date(2026, 1, 15),
        issue_age=45,
        attained_age=45,
        maturity_age=46,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=10_000.0,
        regular_loan_principal=1_000.0,
        current_interest_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2026, 1, 15), face_amount=100_000.0, units=100.0)],
    )
    engine = IllustrationEngine()

    monthly = engine.project(
        policy,
        months=0,
        options=IllustrationOptions(exact_days_interest=False),
        rates_override=IllustrationRates(),
        bonus_override=BonusConfig(),
    )[0]
    exact = engine.project(
        policy,
        months=0,
        options=IllustrationOptions(exact_days_interest=True),
        rates_override=IllustrationRates(),
        bonus_override=BonusConfig(),
    )[0]

    assert monthly.days_in_month == pytest.approx(365.0 / 12.0)
    assert monthly.reg_loan_charge == pytest.approx(1_000.0 * 0.12 / 12.0)
    assert exact.days_in_month == 31.0
    assert exact.reg_loan_charge == pytest.approx(1_000.0 * 0.12 * 31.0 / 365.0)


def test_cash_flow_inputs_report_applied_variable_loan_and_repayment():
    loan = LoanState(
        rg_loan_princ=10.0,
        rg_loan_accrued=1.0,
        pf_loan_princ=20.0,
        pf_loan_accrued=2.0,
        vbl_loan_princ=30.0,
        vbl_loan_accrued=3.0,
    )
    month_inputs = CompiledMonthInputs(variable_loan=7.0, loan_repayment=40.0)

    applied = apply_cash_flow_inputs(1000.0, loan, month_inputs)

    assert applied.applied_variable_loan == 7.0
    assert applied.applied_loan_repayment == 40.0
    assert applied.loan_state.rg_loan_accrued == 0.0
    assert applied.loan_state.rg_loan_princ == 0.0
    assert applied.loan_state.pf_loan_accrued == 0.0
    assert applied.loan_state.pf_loan_princ == 0.0
    assert applied.loan_state.vbl_loan_accrued == 0.0
    assert applied.loan_state.vbl_loan_princ == 33.0


def test_variable_loan_rate_comes_from_latest_fund_loan_monthiversary():
    records = LoanRecords(_FakeLoanPolicy(loan_type="7"))

    assert records.variable_loan_charge_rate == Decimal("0.067")


def test_variable_loan_rate_is_none_for_non_variable_loan_type():
    records = LoanRecords(_FakeLoanPolicy(loan_type="1"))

    assert records.variable_loan_charge_rate is None