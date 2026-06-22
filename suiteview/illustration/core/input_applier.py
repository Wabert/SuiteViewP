from __future__ import annotations

from dataclasses import dataclass, field

from suiteview.illustration.core.input_compiler import CompiledMonthInputs
from suiteview.illustration.core.loan_handler import LoanState, loan_payoff, repay_loan
from suiteview.illustration.models.plancode_config import PlancodeConfig


@dataclass
class CashFlowApplication:
    av: float
    loan_state: LoanState
    applied_loan_repayment: float = 0.0
    applied_variable_loan: float = 0.0
    # Premium dollars diverted to the loan by sInput_ApplyPremToLoan — the
    # lumpsum portion (RERUN MH), the scheduled-premium portion (MI), and the
    # over-repayment that returns to the premium pool (vLNRepayLeftOver / MY).
    loan_repay_from_lumpsum: float = 0.0
    loan_repay_from_scheduled: float = 0.0
    ln_repay_left_over: float = 0.0
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
    apply_prem_to_loan: bool = False,
    requested_lumpsum: float = 0.0,
    requested_scheduled: float = 0.0,
) -> CashFlowApplication:
    """Apply early-month loan inputs (variable loans, repayments).

    Withdrawals are processed earlier by the dedicated withdrawal stage
    (calc_engine._process_withdrawal — CalcEngine AX..BU). Fixed loan requests
    are handled later in the policy-values slice after monthly deduction, once
    preferred-vs-regular allocation can be determined.

    Loan repayment honors the plancode's loan type: advance loans reduce the loan
    by the grossed-up amount (RERUN MR), arrears reduce the buckets by the cash.
    ``loan_state`` is the post-capitalization loan (RERUN cols LX..MC).

    When ``apply_prem_to_loan`` is on (sInput_ApplyPremToLoan), the requested
    premium repays the loan FIRST: the lumpsum (``requested_lumpsum``) then the
    scheduled premium (``requested_scheduled``), each capped at the remaining loan
    payoff (RERUN MH = MIN(MF, lumpsum), MI = MIN(MF − MH, scheduled)). The
    amounts diverted are returned so the premium-acceptance chain only loads what
    is left (NL/NY) onto the account value.
    """
    variable_loan = max(month_inputs.variable_loan, 0.0) if month_inputs is not None else 0.0
    requested_repayment = month_inputs.loan_repayment if month_inputs is not None else 0.0

    # New variable loan is added before the repayment (RERUN adds it to the
    # variable principal bucket; repayment then sees the larger balance).
    cap_loan = LoanState(
        rg_loan_princ=loan_state.rg_loan_princ,
        rg_loan_accrued=loan_state.rg_loan_accrued,
        pf_loan_princ=loan_state.pf_loan_princ,
        pf_loan_accrued=loan_state.pf_loan_accrued,
        vbl_loan_princ=loan_state.vbl_loan_princ + variable_loan,
        vbl_loan_accrued=loan_state.vbl_loan_accrued,
    )

    # MH/MI — premium diverted to the loan, capped at the payoff. The lumpsum
    # repays first, then the scheduled premium against what payoff remains.
    prem_to_loan_from_lumpsum = 0.0
    prem_to_loan_from_scheduled = 0.0
    if apply_prem_to_loan:
        payoff = loan_payoff(cap_loan, config, adv_reg_factor, adv_pref_factor)   # MF
        prem_to_loan_from_lumpsum = min(payoff, max(requested_lumpsum, 0.0))      # MH
        prem_to_loan_from_scheduled = min(
            max(payoff - prem_to_loan_from_lumpsum, 0.0), max(requested_scheduled, 0.0)
        )                                                                         # MI

    result = repay_loan(
        cap_loan, requested_repayment, config, adv_reg_factor, adv_pref_factor,
        prem_to_loan_from_lumpsum=prem_to_loan_from_lumpsum,
        prem_to_loan_from_scheduled=prem_to_loan_from_scheduled,
    )
    leftover = float((result.detail or {}).get("LNRepayLeftOver", 0.0))           # MY

    return CashFlowApplication(
        av=av,
        loan_state=result.loan_state,
        applied_loan_repayment=result.applied_repayment,
        applied_variable_loan=variable_loan,
        loan_repay_from_lumpsum=prem_to_loan_from_lumpsum,
        loan_repay_from_scheduled=prem_to_loan_from_scheduled,
        ln_repay_left_over=leftover,
        loan_cap_repay=result.detail or {},
    )
