from __future__ import annotations

from dataclasses import dataclass

from suiteview.illustration.core.input_compiler import CompiledMonthInputs
from suiteview.illustration.core.loan_handler import LoanState


@dataclass
class CashFlowApplication:
    av: float
    loan_state: LoanState
    withdrawals_to_date: float


def apply_cash_flow_inputs(
    av: float,
    loan_state: LoanState,
    withdrawals_to_date: float,
    month_inputs: CompiledMonthInputs | None,
) -> CashFlowApplication:
    """Apply early-month cash-flow inputs before monthly deduction.

    Fixed loan requests are handled later in the policy-values slice after
    monthly deduction, once preferred-vs-regular allocation can be determined.
    """
    if month_inputs is None:
        return CashFlowApplication(av=av, loan_state=loan_state, withdrawals_to_date=withdrawals_to_date)

    new_loan_state = LoanState(
        rg_loan_princ=loan_state.rg_loan_princ,
        rg_loan_accrued=loan_state.rg_loan_accrued,
        pf_loan_princ=loan_state.pf_loan_princ,
        pf_loan_accrued=loan_state.pf_loan_accrued,
        vbl_loan_princ=loan_state.vbl_loan_princ + month_inputs.variable_loan,
        vbl_loan_accrued=loan_state.vbl_loan_accrued,
    )

    repayment_remaining = month_inputs.loan_repayment
    if repayment_remaining > 0:
        new_loan_state.rg_loan_accrued, repayment_remaining = _reduce_bucket(new_loan_state.rg_loan_accrued, repayment_remaining)
        new_loan_state.rg_loan_princ, repayment_remaining = _reduce_bucket(new_loan_state.rg_loan_princ, repayment_remaining)
        new_loan_state.pf_loan_accrued, repayment_remaining = _reduce_bucket(new_loan_state.pf_loan_accrued, repayment_remaining)
        new_loan_state.pf_loan_princ, repayment_remaining = _reduce_bucket(new_loan_state.pf_loan_princ, repayment_remaining)
        new_loan_state.vbl_loan_accrued, repayment_remaining = _reduce_bucket(new_loan_state.vbl_loan_accrued, repayment_remaining)
        new_loan_state.vbl_loan_princ, repayment_remaining = _reduce_bucket(new_loan_state.vbl_loan_princ, repayment_remaining)

    applied_withdrawal = min(max(month_inputs.withdrawal, 0.0), max(av, 0.0))
    return CashFlowApplication(
        av=av - applied_withdrawal,
        loan_state=new_loan_state,
        withdrawals_to_date=withdrawals_to_date + applied_withdrawal,
    )


def _reduce_bucket(balance: float, amount: float) -> tuple[float, float]:
    applied = min(balance, amount)
    return balance - applied, amount - applied