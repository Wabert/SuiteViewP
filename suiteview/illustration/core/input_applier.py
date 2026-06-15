from __future__ import annotations

from dataclasses import dataclass

from suiteview.illustration.core.input_compiler import CompiledMonthInputs
from suiteview.illustration.core.loan_handler import LoanState


@dataclass
class CashFlowApplication:
    av: float
    loan_state: LoanState
    applied_loan_repayment: float = 0.0
    applied_variable_loan: float = 0.0


def apply_cash_flow_inputs(
    av: float,
    loan_state: LoanState,
    month_inputs: CompiledMonthInputs | None,
) -> CashFlowApplication:
    """Apply early-month loan inputs (variable loans, repayments).

    Withdrawals are processed earlier by the dedicated withdrawal stage
    (calc_engine._process_withdrawal — CalcEngine AX..BU). Fixed loan requests
    are handled later in the policy-values slice after monthly deduction, once
    preferred-vs-regular allocation can be determined.
    """
    if month_inputs is None:
        return CashFlowApplication(av=av, loan_state=loan_state)

    new_loan_state = LoanState(
        rg_loan_princ=loan_state.rg_loan_princ,
        rg_loan_accrued=loan_state.rg_loan_accrued,
        pf_loan_princ=loan_state.pf_loan_princ,
        pf_loan_accrued=loan_state.pf_loan_accrued,
        vbl_loan_princ=loan_state.vbl_loan_princ + month_inputs.variable_loan,
        vbl_loan_accrued=loan_state.vbl_loan_accrued,
    )

    requested_repayment = max(month_inputs.loan_repayment, 0.0)
    repayment_remaining = requested_repayment
    if repayment_remaining > 0:
        new_loan_state.rg_loan_accrued, repayment_remaining = _reduce_bucket(new_loan_state.rg_loan_accrued, repayment_remaining)
        new_loan_state.rg_loan_princ, repayment_remaining = _reduce_bucket(new_loan_state.rg_loan_princ, repayment_remaining)
        new_loan_state.pf_loan_accrued, repayment_remaining = _reduce_bucket(new_loan_state.pf_loan_accrued, repayment_remaining)
        new_loan_state.pf_loan_princ, repayment_remaining = _reduce_bucket(new_loan_state.pf_loan_princ, repayment_remaining)
        new_loan_state.vbl_loan_accrued, repayment_remaining = _reduce_bucket(new_loan_state.vbl_loan_accrued, repayment_remaining)
        new_loan_state.vbl_loan_princ, repayment_remaining = _reduce_bucket(new_loan_state.vbl_loan_princ, repayment_remaining)

    return CashFlowApplication(
        av=av,
        loan_state=new_loan_state,
        applied_loan_repayment=requested_repayment - repayment_remaining,
        applied_variable_loan=max(month_inputs.variable_loan, 0.0),
    )


def _reduce_bucket(balance: float, amount: float) -> tuple[float, float]:
    applied = min(balance, amount)
    return balance - applied, amount - applied