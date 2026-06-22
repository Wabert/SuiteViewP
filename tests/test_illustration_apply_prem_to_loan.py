"""Apply Premium to Loan First (RERUN sInput_ApplyPremToLoan).

When the option is on, the requested premium repays the policy loan before any
of it loads onto the account value: the lumpsum (vLumpsum) repays first, then
the scheduled premium (LS), each capped at the loan payoff (RERUN MH/MI). Only
what is left feeds the premium-acceptance chain (NL = lumpsum − MH + leftover,
NY = scheduled − MI).

Pure-function tests — no rates database or full projection needed. The
checkbox → IllustrationOptions wiring lives in ``test_illustration_run_controls``
(the Qt-headless options-wiring suite).
"""
import pytest

from suiteview.illustration.core.input_applier import apply_cash_flow_inputs
from suiteview.illustration.core.loan_handler import LoanState, loan_payoff, repay_loan
from suiteview.illustration.core.premium_allowance import compute_premium_allowances
from suiteview.illustration.models.plancode_config import PlancodeConfig


ARREARS = PlancodeConfig(loan_type="Arrears", loan_charge_rate_guar=0.06,
                         pref_loan_charge_rate_guar=0.05)
ADVANCE = PlancodeConfig(loan_type="Advance", loan_charge_rate_guar=0.074,
                         pref_loan_charge_rate_guar=0.0566)


def _round2(x):
    from decimal import ROUND_HALF_UP, Decimal
    return float(Decimal(f"{x:.12f}").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ── loan_payoff (RERUN MF) ───────────────────────────────────────────────────

def test_loan_payoff_arrears_sums_every_bucket():
    loan = LoanState(rg_loan_princ=500.0, rg_loan_accrued=20.0, pf_loan_princ=100.0)
    assert loan_payoff(loan, ARREARS, 0.0, 0.0) == 620.0


def test_loan_payoff_advance_refunds_unearned_interest():
    loan = LoanState(rg_loan_princ=10_000.0)
    # Payoff is the principal less the prepaid (unearned) interest factor.
    assert loan_payoff(loan, ADVANCE, 0.05, 0.04) == _round2(10_000.0 * (1 - 0.05))


# ── repay_loan with premium diverted (MH/MI) ─────────────────────────────────

def test_repay_loan_records_diverted_premium_and_reduces_the_loan():
    # repay_loan takes MH/MI as already capped (the caller bounds them at the
    # payoff) and folds them into the total repayment (MK, then MO = MK + MN).
    cap = LoanState(rg_loan_princ=500.0)
    result = repay_loan(
        cap, 0.0, ARREARS, 0.0, 0.0,
        prem_to_loan_from_lumpsum=300.0, prem_to_loan_from_scheduled=100.0,
    )
    detail = result.detail
    assert detail["Arrears - From Lumpsum"] == 300.0           # MH
    assert detail["Arrears - From Scheduled Prem"] == 100.0    # MI
    assert detail["Arrears - LoanRepayFromPremAndForceout"] == 400.0  # MK
    assert detail["Arrears - Requested Loan Repayment"] == 0.0        # MN
    assert detail["Arrears - Total Loan Repayment Attempted"] == 400.0  # MO
    assert detail["TotalLoanReduction"] == 400.0
    assert detail["LNRepayLeftOver"] == 0.0
    assert result.loan_state.rg_loan_princ == 100.0
    assert result.applied_repayment == 400.0


def test_repay_loan_combines_scheduled_repayment_with_premium_diversion():
    # MN (scheduled repayment input) and MH stack into MO and reduce the loan.
    cap = LoanState(rg_loan_princ=1_000.0)
    result = repay_loan(
        cap, 200.0, ARREARS, 0.0, 0.0, prem_to_loan_from_lumpsum=300.0,
    )
    assert result.detail["Arrears - Requested Loan Repayment"] == 200.0   # MN
    assert result.detail["Arrears - From Lumpsum"] == 300.0               # MH
    assert result.detail["Arrears - Total Loan Repayment Attempted"] == 500.0  # MO
    assert result.loan_state.rg_loan_princ == 500.0


def test_repay_loan_premium_diversion_works_on_advance_loans():
    cap = LoanState(rg_loan_princ=10_000.0)
    x, y = 0.05, 0.04
    payoff = _round2(10_000.0 * (1 - x))
    result = repay_loan(
        cap, 0.0, ADVANCE, x, y, prem_to_loan_from_lumpsum=100.0,
    )
    assert result.detail["Arrears - From Lumpsum"] == 100.0
    # Advance loans reduce principal by the grossed-up amount, not the cash.
    assert result.loan_state.rg_loan_princ == pytest.approx(10_000.0 - _round2(100.0 / (1 - x)))
    assert result.applied_repayment == 100.0
    assert result.detail["Advance - LoanPayoff"] == payoff


# ── apply_cash_flow_inputs orchestration ─────────────────────────────────────

def test_apply_cash_flow_off_does_not_divert_premium():
    loan = LoanState(rg_loan_princ=500.0)
    out = apply_cash_flow_inputs(
        1_000.0, loan, None, config=ARREARS,
        apply_prem_to_loan=False, requested_lumpsum=400.0, requested_scheduled=300.0,
    )
    assert out.loan_repay_from_lumpsum == 0.0
    assert out.loan_repay_from_scheduled == 0.0
    assert out.loan_state.rg_loan_princ == 500.0   # untouched


def test_apply_cash_flow_diverts_lumpsum_then_scheduled():
    loan = LoanState(rg_loan_princ=500.0)
    out = apply_cash_flow_inputs(
        1_000.0, loan, None, config=ARREARS,
        apply_prem_to_loan=True, requested_lumpsum=400.0, requested_scheduled=300.0,
    )
    assert out.loan_repay_from_lumpsum == 400.0    # MH
    assert out.loan_repay_from_scheduled == 100.0  # MI — the split point
    assert out.ln_repay_left_over == 0.0
    assert out.loan_state.rg_loan_princ == 0.0     # loan cleared
    assert out.av == 1_000.0                        # AV is loaded later, not here


def test_apply_cash_flow_lumpsum_exceeding_payoff_caps_at_payoff():
    loan = LoanState(rg_loan_princ=500.0)
    out = apply_cash_flow_inputs(
        1_000.0, loan, None, config=ARREARS,
        apply_prem_to_loan=True, requested_lumpsum=800.0, requested_scheduled=300.0,
    )
    assert out.loan_repay_from_lumpsum == 500.0    # capped at the payoff
    assert out.loan_repay_from_scheduled == 0.0    # no payoff left for the scheduled
    assert out.loan_state.rg_loan_princ == 0.0


# ── premium-acceptance chain consumes the diversion (NL / NY) ─────────────────

def _alw(**overrides):
    kwargs = dict(
        is_cvat=False, is_gpt=True, tefra_force=False, tamra_force=False,
        mec_bypass=False, guideline_limit=0.0, prem_less_wd=0.0, force_out=0.0,
        loan_repay_from_forceout=0.0, seven_pay_level=0.0, tamra_year=1,
        tamra_month_of_year=1, policy_month=1, amount_in_7pay=0.0, npt_premium=0.0,
        tamra_reset=False, requested_scheduled=0.0, requested_lumpsum=0.0,
        payment_count_policy_year=12, payment_count_tamra_year=12,
        loan_repay_from_lumpsum=0.0, loan_repay_from_scheduled=0.0,
        ln_repay_left_over=0.0, has_loan_balance=False, levelizing_premium=False,
        beginning_of_year=True, prior_scheduled_prem_cap=0.0,
    )
    kwargs.update(overrides)
    return compute_premium_allowances(**kwargs)


def test_diverted_premium_only_loads_the_remainder_onto_av():
    # $400 lumpsum + $300 scheduled requested; $400+$100 went to the loan, so
    # only the $200 scheduled remainder loads onto the account value.
    a = _alw(
        requested_lumpsum=400.0, requested_scheduled=300.0,
        loan_repay_from_lumpsum=400.0, loan_repay_from_scheduled=100.0,
    )
    assert a.lumpsum_remaining == 0.0                 # NL = (400 − 400) + 0
    assert a.applied_lumpsum == 0.0
    assert a.scheduled_less_loan_repay == 200.0       # NY = 300 − 100
    assert a.applied_scheduled_premium == 200.0
    assert a.applied_total_premium == 200.0


def test_lumpsum_over_payoff_returns_excess_to_premium():
    # An $800 lumpsum clears a $500 loan; the $300 excess loads as premium.
    a = _alw(
        requested_lumpsum=800.0, requested_scheduled=0.0,
        loan_repay_from_lumpsum=500.0, loan_repay_from_scheduled=0.0,
    )
    assert a.lumpsum_remaining == 300.0
    assert a.applied_lumpsum == 300.0
    assert a.applied_total_premium == 300.0
