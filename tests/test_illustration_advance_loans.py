"""Interest-in-advance loan handling (RERUN CalcEngine "Loan Capitalize and Repay").

Advance loans carry a year of prepaid interest in the loan total, so:
  - at each anniversary the next year's interest is grossed onto the principal
    (cols AA/AC), and
  - a cash repayment reduces the loan total by the *grossed-up* amount
    repay/(1-factor) (col MR) — paying $X mid-year clears $X plus the interest
    on $X for the rest of the policy year.
"""
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import (
    IllustrationEngine,
    _advance_loan_factors,
    _days_to_next_anniversary,
)
from suiteview.illustration.core.loan_handler import (
    LoanState,
    capitalize_loans,
    empty_loan_cap_repay_detail,
    repay_loan,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


ADVANCE = PlancodeConfig(loan_type="Advance", loan_charge_rate_guar=0.074,
                         pref_loan_charge_rate_guar=0.0566)
ARREARS = PlancodeConfig(loan_type="Arrears", loan_charge_rate_guar=0.06,
                         pref_loan_charge_rate_guar=0.05)


def _round2(x):
    from decimal import ROUND_HALF_UP, Decimal
    return float(Decimal(f"{x:.12f}").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ── date / factor helpers ────────────────────────────────────────────────────

def test_days_to_next_anniversary_resets_to_full_year_at_anniversary():
    issue = date(1985, 7, 23)
    # An anniversary monthliversary → a full year ahead.
    assert _days_to_next_anniversary(issue, date(2026, 7, 23)) == 365
    # Mid-year shrinks toward zero.
    assert _days_to_next_anniversary(issue, date(2026, 8, 23)) == 334


def test_advance_loan_factors_scale_rate_by_days_remaining():
    x, y = _advance_loan_factors(ADVANCE, 365)
    assert x == pytest.approx(0.074)
    assert y == pytest.approx(0.0566)
    x_half, _ = _advance_loan_factors(ADVANCE, 183)
    assert x_half == pytest.approx(0.074 * 183 / 365)


# ── capitalization ───────────────────────────────────────────────────────────

def test_advance_capitalization_grosses_prepaid_interest_at_anniversary():
    x, y = _advance_loan_factors(ADVANCE, 365)  # ≈ full annual rate
    cap = capitalize_loans(
        10_000.0, 0.0, 0.0, 0.0, 0.0, 0.0, is_anniversary=True,
        config=ADVANCE, adv_reg_factor=x, adv_pref_factor=y,
    )
    # AA = Z * X/(1-X); the total grosses up to Z/(1-X).
    assert cap.rg_loan_princ == pytest.approx(10_000.0 / (1 - 0.074))
    assert cap.rg_loan_accrued == 0.0


def test_arrears_capitalization_rolls_accrued_into_principal():
    cap = capitalize_loans(
        1_000.0, 50.0, 0.0, 0.0, 0.0, 0.0, is_anniversary=True, config=ARREARS,
    )
    assert cap.rg_loan_princ == 1_050.0
    assert cap.rg_loan_accrued == 0.0


def test_no_capitalization_off_anniversary():
    cap = capitalize_loans(
        1_000.0, 50.0, 0.0, 0.0, 0.0, 0.0, is_anniversary=False, config=ADVANCE,
        adv_reg_factor=0.05, adv_pref_factor=0.04,
    )
    assert cap.rg_loan_princ == 1_000.0
    assert cap.rg_loan_accrued == 50.0


# ── repayment ────────────────────────────────────────────────────────────────

def test_advance_repayment_reduces_principal_by_grossed_up_amount():
    cap = LoanState(rg_loan_princ=10_000.0)
    x, y = _advance_loan_factors(ADVANCE, 183)  # mid-year
    result = repay_loan(cap, 100.0, ADVANCE, x, y)

    # Payoff = principal * (1 - X); a $100 repayment clears 100/(1-X) of the total.
    expected_reduction = _round2(100.0 / (1 - x))
    assert expected_reduction > 100.0  # grossed up beyond the cash
    assert result.detail["Advance - Adv Total Loan Repayment"] == expected_reduction
    assert result.detail["TotalLoanReduction"] == expected_reduction
    assert result.loan_state.rg_loan_princ == pytest.approx(10_000.0 - expected_reduction)
    assert result.applied_repayment == 100.0
    assert result.detail["Advance - Adv Reg LN Payoff"] == _round2(10_000.0 * (1 - x))
    assert result.detail["Advance - Adv Reg LN Repay"] == 100.0


def test_advance_repayment_prefers_preferred_then_regular():
    cap = LoanState(rg_loan_princ=5_000.0, pf_loan_princ=300.0)
    x, y = _advance_loan_factors(ADVANCE, 365)
    pref_payoff = _round2(300.0 * (1 - y))
    # Repay more than the preferred payoff: preferred clears first, rest to regular.
    result = repay_loan(cap, pref_payoff + 100.0, ADVANCE, x, y)

    assert result.detail["Advance - Adv Pref LN Repay"] == pref_payoff
    assert result.detail["Advance - Adv Reg LN Repay"] == 100.0
    assert result.loan_state.pf_loan_princ == pytest.approx(0.0, abs=0.01)


def test_advance_full_payoff_clears_loan():
    cap = LoanState(rg_loan_princ=10_000.0)
    x, y = _advance_loan_factors(ADVANCE, 200)
    payoff = _round2(10_000.0 * (1 - x))
    result = repay_loan(cap, payoff + 50.0, ADVANCE, x, y)  # over-pay

    assert result.loan_state.rg_loan_princ == pytest.approx(0.0, abs=0.01)
    assert result.applied_repayment == payoff  # capped at the payoff
    assert result.detail["LNRepayLeftOver"] == pytest.approx(50.0)


def test_arrears_repayment_reduces_buckets_by_cash_no_gross_up():
    cap = LoanState(rg_loan_princ=1_000.0, rg_loan_accrued=20.0)
    result = repay_loan(cap, 100.0, ARREARS, 0.03, 0.02)

    # Arrears: cash reduces accrued first, then principal — no gross-up.
    assert result.detail["TotalLoanReduction"] == 100.0
    assert result.detail["Advance - Adv Total Loan Repayment"] == 0.0
    assert result.loan_state.rg_loan_accrued == 0.0
    assert result.loan_state.rg_loan_princ == 920.0
    assert result.applied_repayment == 100.0


def test_empty_detail_has_all_display_keys():
    detail = empty_loan_cap_repay_detail()
    for key in (
        "Advance - Rg Ln Princ/Total", "Advance - Adv Reg LN Payoff",
        "Advance - LoanPayoff", "Arrears - Requested Loan Repayment",
        "Advance - Adv Total Loan Repayment", "LNRepayLeftOver", "TotalLoanReduction",
    ):
        assert key in detail
        assert detail[key] == 0.0


# ── engine integration ───────────────────────────────────────────────────────

def _advance_policy():
    return IllustrationPolicyData(
        plancode="ADV",
        issue_date=date(2020, 6, 15),
        valuation_date=date(2026, 6, 15),  # start of policy year 7 (an anniversary)
        issue_age=45,
        attained_age=51,
        maturity_age=121,
        policy_year=7,
        policy_month=1,
        duration=73,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=100_000.0,
        regular_loan_principal=10_000.0,
        current_interest_rate=0.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2020, 6, 15),
                                  face_amount=100_000.0, units=100.0)],
    )


def test_engine_advance_loan_repayment_grosses_up_balance(monkeypatch):
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _p: PlancodeConfig(
            plancode="ADV", interest_method="ExactDays", loan_type="Advance",
            loan_charge_rate_guar=0.074, pref_loan_charge_rate_guar=0.0566,
            gint=0.0, dbd=0.0, premium_load="0", prem_flat_load=0.0, epu_code="0",
            mfee="0", poav_code="0", bonus="0", corridor_code=None, snet_period=0,
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _p, _d: BonusConfig())

    policy = _advance_policy()
    repay_date = date(2026, 9, 15)  # 3 months after valuation, same policy year
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(kind=TransactionKind.LOAN_REPAYMENT, effective_date=repay_date, amount=600.0),
    ])

    engine = IllustrationEngine()
    states = engine.project(
        policy, months=6, future_inputs=inputs,
        options=IllustrationOptions(), rates_override=IllustrationRates(),
        bonus_override=BonusConfig(),
    )

    repay_state = next(s for s in states if s.applied_loan_repayment > 0)
    assert repay_state.date == repay_date

    detail = repay_state.loan_cap_repay
    x = _advance_loan_factors(ADVANCE, _days_to_next_anniversary(policy.issue_date, repay_date))[0]
    cap_principal = detail["Advance - Rg Ln Princ/Total"]

    assert detail["Arrears - Requested Loan Repayment"] == 600.0
    # Payoff = capitalized principal × (1 − X).
    assert detail["Advance - Adv Reg LN Payoff"] == _round2(cap_principal * (1 - x))
    # The loan reduces by the grossed-up amount, not the $600 cash.
    expected_reduction = _round2(600.0 / (1 - x))
    assert expected_reduction > 600.0
    assert detail["TotalLoanReduction"] == pytest.approx(expected_reduction)
    assert repay_state.rg_loan_princ == pytest.approx(cap_principal - expected_reduction)
