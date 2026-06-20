from __future__ import annotations

from dataclasses import dataclass, field

from suiteview.illustration.core.input_compiler import CompiledMonthInputs
from suiteview.illustration.core.loan_handler import LoanState, repay_loan
from suiteview.illustration.models.plancode_config import PlancodeConfig


@dataclass
class CashFlowApplication:
    av: float
    loan_state: LoanState
    applied_loan_repayment: float = 0.0
    applied_variable_loan: float = 0.0
    # RERUN "Loan Capitalize and Repay" display detail (cols LX..MZ).
    loan_cap_repay: dict = field(default_factory=dict)


def apply_cash_flow_inputs(
    av: float,
    loan_state: LoanState,
    month_inputs: CompiledMonthInputs | None,
    *,
    config: PlancodeConfig | None = None,
    adv_reg_factor: float = 0.0,
    adv_pref_factor: float = 0.0,
) -> CashFlowApplication:
    """Apply early-month loan inputs (variable loans, repayments).

    Withdrawals are processed earlier by the dedicated withdrawal stage
    (calc_engine._process_withdrawal — CalcEngine AX..BU). Fixed loan requests
    are handled later in the policy-values slice after monthly deduction, once
    preferred-vs-regular allocation can be determined.

    Loan repayment honors the plancode's loan type: advance loans reduce the loan
    by the grossed-up amount (RERUN MR), arrears reduce the buckets by the cash.
    ``loan_state`` is the post-capitalization loan (RERUN cols LX..MC).
    """
    if month_inputs is None:
        result = repay_loan(loan_state, 0.0, config, adv_reg_factor, adv_pref_factor)
        return CashFlowApplication(
            av=av, loan_state=result.loan_state, loan_cap_repay=result.detail or {})

    # New variable loan is added before the repayment (RERUN adds it to the
    # variable principal bucket; repayment then sees the larger balance).
    variable_loan = max(month_inputs.variable_loan, 0.0)
    cap_loan = LoanState(
        rg_loan_princ=loan_state.rg_loan_princ,
        rg_loan_accrued=loan_state.rg_loan_accrued,
        pf_loan_princ=loan_state.pf_loan_princ,
        pf_loan_accrued=loan_state.pf_loan_accrued,
        vbl_loan_princ=loan_state.vbl_loan_princ + variable_loan,
        vbl_loan_accrued=loan_state.vbl_loan_accrued,
    )

    result = repay_loan(
        cap_loan, month_inputs.loan_repayment, config, adv_reg_factor, adv_pref_factor)

    return CashFlowApplication(
        av=av,
        loan_state=result.loan_state,
        applied_loan_repayment=result.applied_repayment,
        applied_variable_loan=variable_loan,
        loan_cap_repay=result.detail or {},
    )
