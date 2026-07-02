"""Apply excess loan repayment as premium (apply_excess_repayment_as_premium).

A loan repayment larger than the loan payoff leaves an excess (RERUN
vLNRepayLeftOver / MY). RERUN always returns that excess to the premium pool;
SuiteView gates it behind the "Apply excess as premium" toggle in the Loan
Repayments group. Off (the default), repayments stop at the payoff and the
excess is discarded; on, the excess feeds the lumpsum side of the premium-
acceptance chain (NL), where it loads onto the account value with the premium
load.

Pure-function tests — no rates database or full projection needed. The
checkbox → IllustrationOptions wiring lives in ``test_illustration_run_controls``.
"""
from suiteview.illustration.core.input_applier import apply_cash_flow_inputs
from suiteview.illustration.core.input_compiler import CompiledMonthInputs
from suiteview.illustration.core.loan_handler import LoanState
from suiteview.illustration.core.premium_allowance import compute_premium_allowances
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig


ARREARS = PlancodeConfig(loan_type="Arrears", loan_charge_rate_guar=0.06,
                         pref_loan_charge_rate_guar=0.05)


def test_option_defaults_off():
    assert IllustrationOptions().apply_excess_repayment_as_premium is False


def test_excess_discarded_by_default():
    # An $800 repayment against a $500 loan clears the loan; the $300 excess
    # does NOT return to the premium pool, but the display detail still shows it.
    loan = LoanState(rg_loan_princ=500.0)
    out = apply_cash_flow_inputs(
        1_000.0, loan, CompiledMonthInputs(loan_repayment=800.0), config=ARREARS,
    )
    assert out.loan_state.rg_loan_princ == 0.0
    assert out.applied_loan_repayment == 500.0
    assert out.ln_repay_left_over == 0.0
    assert out.loan_cap_repay["LNRepayLeftOver"] == 300.0   # MY, display only


def test_excess_returns_to_premium_when_enabled():
    loan = LoanState(rg_loan_princ=500.0)
    out = apply_cash_flow_inputs(
        1_000.0, loan, CompiledMonthInputs(loan_repayment=800.0), config=ARREARS,
        excess_repayment_to_premium=True,
    )
    assert out.loan_state.rg_loan_princ == 0.0
    assert out.applied_loan_repayment == 500.0
    assert out.ln_repay_left_over == 300.0


def test_leftover_loads_as_lumpsum_premium():
    # The leftover enters the acceptance chain on the lumpsum side (NL), so it
    # is applied as gross premium — the AV pipeline then takes the premium load.
    a = compute_premium_allowances(
        is_cvat=False, is_gpt=True, tefra_force=False, tamra_force=False,
        mec_bypass=False, guideline_limit=0.0, prem_less_wd=0.0, force_out=0.0,
        loan_repay_from_forceout=0.0, seven_pay_level=0.0, tamra_year=1,
        tamra_month_of_year=1, policy_month=1, amount_in_7pay=0.0, npt_premium=0.0,
        tamra_reset=False, requested_scheduled=0.0, requested_lumpsum=0.0,
        payment_count_policy_year=12, payment_count_tamra_year=12,
        loan_repay_from_lumpsum=0.0, loan_repay_from_scheduled=0.0,
        ln_repay_left_over=300.0, has_loan_balance=False, levelizing_premium=False,
        beginning_of_year=True, prior_scheduled_prem_cap=0.0,
    )
    assert a.lumpsum_remaining == 300.0
    assert a.applied_lumpsum == 300.0
    assert a.applied_total_premium == 300.0
