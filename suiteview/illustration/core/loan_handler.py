"""Loan processing — Capitalization, Interest Accrual, Repayment.

Pipeline positions (RERUN CalcEngine):
  - Loan Capitalize: Row 16 (before Apply Premium)
  - Loan Interest Accrual: Accumulation section cols 587-592 (after Interest Credit)

In-Arrears formula:
    monthly_accrual = principal * charge_rate * days_in_month / 365

Capitalization at policy anniversary:
    Arrears:  principal += accrued_interest;  accrued_interest = 0
    Advance:  principal += principal * X/(1-X);  accrued stays 0
              where X = charge_rate * days_to_next_anniversary / 365 (≈ rate at
              the anniversary). The advance loan total already carries a year of
              prepaid interest, so each anniversary grosses the next year on.

Interest-in-advance repayment (RERUN CalcEngine "Loan Capitalize and Repay",
cols MD..MR): the loan total includes prepaid interest, so the *payoff* value of
a loan is principal*(1-X) (cols MD/ME) — less than the total, because unearned
interest is refunded. A cash repayment of R therefore extinguishes R/(1-X) of
the loan total (col MR): paying $100 mid-year reduces the balance by 100 plus the
interest on 100 for the remainder of the year.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from suiteview.illustration.models.plancode_config import PlancodeConfig


def _round2(value: float) -> float:
    """Round half-up to cents (Excel ROUND semantics, not banker's)."""
    return float(Decimal(f"{value:.12f}").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _reduce_bucket(balance: float, amount: float) -> tuple[float, float]:
    """Take as much of ``amount`` as ``balance`` allows; return (new_balance, leftover)."""
    applied = min(balance, amount)
    return balance - applied, amount - applied


@dataclass
class LoanState:
    """Loan balances after capitalization and accrual."""

    rg_loan_princ: float = 0.0
    rg_loan_accrued: float = 0.0
    pf_loan_princ: float = 0.0
    pf_loan_accrued: float = 0.0
    vbl_loan_princ: float = 0.0
    vbl_loan_accrued: float = 0.0
    reg_loan_charge: float = 0.0     # Regular loan interest accrued this month
    pref_loan_charge: float = 0.0    # Preferred loan interest accrued this month
    vbl_loan_charge: float = 0.0     # Variable loan interest accrued this month

    @property
    def policy_debt(self) -> float:
        return (
            self.rg_loan_princ + self.rg_loan_accrued
            + self.pf_loan_princ + self.pf_loan_accrued
            + self.vbl_loan_princ + self.vbl_loan_accrued
        )


def capitalize_loans(
    rg_princ: float,
    rg_accrued: float,
    pf_princ: float,
    pf_accrued: float,
    vbl_princ: float,
    vbl_accrued: float,
    is_anniversary: bool,
    *,
    config: PlancodeConfig | None = None,
    adv_reg_factor: float = 0.0,
    adv_pref_factor: float = 0.0,
) -> LoanState:
    """Capitalize loan interest into principal at anniversary.

    Outside anniversary months, balances pass through unchanged.

    At each policy anniversary:
      - Arrears: accrued interest rolls into principal; accrued resets to zero.
      - Advance: the next year's prepaid interest is grossed onto the principal
        (RERUN CalcEngine AA/AC): ``princ += princ * X/(1-X)`` where ``X`` is the
        advance interest factor (``charge_rate * days_to_next_anniversary/365``,
        ≈ the annual rate at the anniversary). Accrued stays zero — advance loans
        carry no accrued bucket.

    Args:
        rg_princ..vbl_accrued: Beginning loan buckets (prior month-end / policy).
        is_anniversary: True if this is the first month of a new policy year.
        config: Plancode config; advance behavior applies when loan_type=="Advance".
        adv_reg_factor: Regular advance interest factor X (anniversary value).
        adv_pref_factor: Preferred advance interest factor Y (anniversary value).

    Returns:
        LoanState with capitalized balances (no monthly accrual yet).
    """
    if not is_anniversary:
        return LoanState(
            rg_loan_princ=rg_princ,
            rg_loan_accrued=rg_accrued,
            pf_loan_princ=pf_princ,
            pf_loan_accrued=pf_accrued,
            vbl_loan_princ=vbl_princ,
            vbl_loan_accrued=vbl_accrued,
        )

    if config is not None and config.loan_type == "Advance":
        # Round the interest-in-advance capitalization to whole cents — CyberLife
        # carries the loan balance in cents, so an unrounded gross-up leaves a
        # sub-penny residual that the payoff (ROUND(LX*(1-X),2)) can no longer
        # reach, stranding a fraction of a cent of debt and a negative surrender
        # value once the loan is otherwise repaid. RERUN cols AA/AC do NOT round
        # (Z*X/(1-X)); this is a deliberate, CyberLife-correct divergence.
        rg_adv = _round2(rg_princ * adv_reg_factor / (1.0 - adv_reg_factor)) if adv_reg_factor < 1.0 else 0.0
        pf_adv = _round2(pf_princ * adv_pref_factor / (1.0 - adv_pref_factor)) if adv_pref_factor < 1.0 else 0.0
        return LoanState(
            rg_loan_princ=rg_princ + rg_adv,
            rg_loan_accrued=0.0,
            pf_loan_princ=pf_princ + pf_adv,
            pf_loan_accrued=0.0,
            # Variable loans accrue in arrears even on advance plancodes.
            vbl_loan_princ=vbl_princ + vbl_accrued,
            vbl_loan_accrued=0.0,
        )

    return LoanState(
        rg_loan_princ=rg_princ + rg_accrued,
        rg_loan_accrued=0.0,
        pf_loan_princ=pf_princ + pf_accrued,
        pf_loan_accrued=0.0,
        vbl_loan_princ=vbl_princ + vbl_accrued,
        vbl_loan_accrued=0.0,
    )


def accrue_loan_interest(
    loan: LoanState,
    config: PlancodeConfig,
    days_in_month: float,
    variable_loan_charge_rate: float | None = None,
) -> LoanState:
    """Accrue monthly loan interest charge (in-arrears).

    Formula per CalcEngine col 588:
        new_accrued = old_accrued + principal * charge_rate * days / 365

    Args:
        loan: Current loan balances (after capitalization).
        config: Plancode config with loan charge rates.
        days_in_month: Option-aware day count for the current month.

    Returns:
        Updated LoanState with accrued interest added.
    """
    if config.loan_type != "Arrears":
        # Advance loans: no monthly accrual (interest prepaid)
        return loan

    rg_interest = loan.rg_loan_princ * config.loan_charge_rate_guar * days_in_month / 365.0
    pf_interest = loan.pf_loan_princ * config.pref_loan_charge_rate_guar * days_in_month / 365.0
    vbl_rate = variable_loan_charge_rate if variable_loan_charge_rate is not None else 0.0
    vbl_interest = loan.vbl_loan_princ * vbl_rate * days_in_month / 365.0

    return LoanState(
        rg_loan_princ=loan.rg_loan_princ,
        rg_loan_accrued=loan.rg_loan_accrued + rg_interest,
        pf_loan_princ=loan.pf_loan_princ,
        pf_loan_accrued=loan.pf_loan_accrued + pf_interest,
        vbl_loan_princ=loan.vbl_loan_princ,
        vbl_loan_accrued=loan.vbl_loan_accrued + vbl_interest,
        reg_loan_charge=rg_interest,
        pref_loan_charge=pf_interest,
        vbl_loan_charge=vbl_interest,
    )


def apply_new_fixed_loan(
    loan: LoanState,
    requested_amount: float,
    account_value: float,
    premiums_to_date: float,
    withdrawals_to_date: float,
    max_loan: float | None = None,
) -> LoanState:
    """Allocate a new fixed-loan request between preferred and regular loans.

    Mirrors CalcEngine TR/TW/TX: the "gain" portion of the policy is taken as
    preferred loan, the remainder as regular loan. Gain (preferred capacity) is
    determined after monthly deduction as:

        max(0, AV - current policy debt - (PremTD - AccumWDs))

    ``max_loan`` caps the applied amount (TQ vAppliedLoan with
    sInput_RestrictLoansToSV: MIN(requested, MAX(0, lapseSV − holdback·MD)) —
    you cannot borrow past the surrender value).

    The split always applies to a fixed loan; when there is no gain the whole
    request becomes regular loan (preferred_amount = 0). Capitalized loan
    interest is not re-split here — it stays in its own bucket, matching the
    workbook (capitalization happens within-bucket before this step).
    """
    loan_amount = max(requested_amount, 0.0)
    if max_loan is not None:
        loan_amount = min(loan_amount, max(0.0, max_loan))
    if loan_amount == 0.0:
        return loan

    preferred_capacity = max(
        account_value - loan.policy_debt - (premiums_to_date - withdrawals_to_date),
        0.0,
    )

    preferred_amount = min(loan_amount, preferred_capacity)
    regular_amount = loan_amount - preferred_amount

    return LoanState(
        rg_loan_princ=loan.rg_loan_princ + regular_amount,
        rg_loan_accrued=loan.rg_loan_accrued,
        pf_loan_princ=loan.pf_loan_princ + preferred_amount,
        pf_loan_accrued=loan.pf_loan_accrued,
        vbl_loan_princ=loan.vbl_loan_princ,
        vbl_loan_accrued=loan.vbl_loan_accrued,
    )


@dataclass
class LoanRepayResult:
    """Outcome of the Loan Capitalize and Repay step.

    ``loan_state`` is the post-repayment beginning-of-month loan (RERUN cols
    MS..MX). ``applied_repayment`` is the cash actually applied to the loan.
    ``detail`` is keyed by the RERUN "Loan Capitalize and Repay" display column
    names (LX..MR, MY, MZ) for the Values tab.
    """

    loan_state: LoanState
    applied_repayment: float = 0.0
    detail: dict = None


def loan_payoff(
    cap_loan: LoanState,
    config: PlancodeConfig | None,
    adv_reg_factor: float,
    adv_pref_factor: float,
) -> float:
    """Loan payoff value (RERUN MF = vLoanPayoff).

    Advance loans refund unearned prepaid interest, so each bucket pays off at
    ``principal*(1-factor)`` (cols MD/ME); arrears loans pay off at the full
    bucket total (SUM(LX:MC)). This is the cash needed to clear the loan, and
    the ceiling on premium that can be diverted to repay it (MH/MI).
    """
    is_advance = config is not None and config.loan_type == "Advance"
    if is_advance:
        reg_payoff = _round2(cap_loan.rg_loan_princ * (1.0 - adv_reg_factor))
        pref_payoff = _round2(cap_loan.pf_loan_princ * (1.0 - adv_pref_factor))
        return reg_payoff + pref_payoff
    return (
        cap_loan.rg_loan_princ + cap_loan.rg_loan_accrued
        + cap_loan.pf_loan_princ + cap_loan.pf_loan_accrued
        + cap_loan.vbl_loan_princ + cap_loan.vbl_loan_accrued
    )


def repay_loan(
    cap_loan: LoanState,
    requested_repayment: float,
    config: PlancodeConfig | None,
    adv_reg_factor: float,
    adv_pref_factor: float,
    *,
    prem_to_loan_from_lumpsum: float = 0.0,
    prem_to_loan_from_scheduled: float = 0.0,
) -> LoanRepayResult:
    """Apply a loan repayment to the post-capitalization buckets.

    The total attempted repayment is the scheduled repayment input
    ``requested_repayment`` (RERUN MN) plus any premium diverted to the loan by
    ``sInput_ApplyPremToLoan`` — the lumpsum portion ``prem_to_loan_from_lumpsum``
    (MH) and the scheduled-premium portion ``prem_to_loan_from_scheduled`` (MI).
    Together these form MO = MK + MN (the PremToPayLoanInterest MG and force-out
    MJ sources are not modeled). The caller computes MH/MI against
    :func:`loan_payoff`; this routine reduces the buckets by the total.

    Advance loans (RERUN cols MD/ME/MP/MQ/MR): the loan total carries prepaid
    interest, so its payoff value is ``principal*(1-factor)`` (MD/ME). A cash
    repayment is taken preferred-first (MQ) then regular (MP), each capped at its
    payoff, and the loan *principal* is reduced by the grossed-up amount
    ``repay/(1-factor)`` (MR) — i.e. the cash plus the unearned interest on it.

    Arrears loans: the cash reduces the buckets directly (interest already lives
    in the accrued buckets), preferred-first then regular then variable.

    Returns a :class:`LoanRepayResult` (does not add new/variable loans — that
    happens separately). ``applied_repayment`` is the total cash applied to the
    loan, capped at the payoff.
    """
    is_advance = config is not None and config.loan_type == "Advance"
    requested = max(requested_repayment, 0.0)                  # MN
    prem_lump = max(prem_to_loan_from_lumpsum, 0.0)            # MH
    prem_sched = max(prem_to_loan_from_scheduled, 0.0)         # MI
    attempted = requested + prem_lump + prem_sched            # MO = MK + MN

    if is_advance:
        reg_payoff = _round2(cap_loan.rg_loan_princ * (1.0 - adv_reg_factor))   # MD
        pref_payoff = _round2(cap_loan.pf_loan_princ * (1.0 - adv_pref_factor))  # ME
        payoff = reg_payoff + pref_payoff                                        # MF
        pref_repay = min(pref_payoff, attempted)                                 # MQ
        reg_repay = min(reg_payoff, max(0.0, attempted - pref_repay))            # MP
        reg_reduction = _round2(reg_repay / (1.0 - adv_reg_factor)) if adv_reg_factor < 1.0 else reg_repay
        pref_reduction = _round2(pref_repay / (1.0 - adv_pref_factor)) if adv_pref_factor < 1.0 else pref_repay
        total_reduction = reg_reduction + pref_reduction                         # MR / MZ
        # Round the post-repay principal to whole cents — the gross-up subtraction
        # otherwise leaves IEEE float dust (~1e-12) that the payoff (ROUND(...,2))
        # can no longer reach, so a paid-off loan strands a sub-penny of debt and
        # a negative surrender value.
        new_loan = LoanState(
            rg_loan_princ=max(0.0, _round2(cap_loan.rg_loan_princ - reg_reduction)),
            rg_loan_accrued=0.0,
            pf_loan_princ=max(0.0, _round2(cap_loan.pf_loan_princ - pref_reduction)),
            pf_loan_accrued=0.0,
            vbl_loan_princ=cap_loan.vbl_loan_princ,
            vbl_loan_accrued=cap_loan.vbl_loan_accrued,
        )
        leftover = max(0.0, attempted - payoff)                                  # MY
        applied = reg_repay + pref_repay
        detail = _loan_cap_repay_detail(
            cap_loan, advance=True,
            reg_payoff=reg_payoff, pref_payoff=pref_payoff, payoff=payoff,
            requested=requested, attempted=attempted,
            prem_from_lumpsum=prem_lump, prem_from_scheduled=prem_sched,
            reg_repay=reg_repay, pref_repay=pref_repay,
            total_reduction=total_reduction, leftover=leftover,
        )
        return LoanRepayResult(loan_state=new_loan, applied_repayment=applied, detail=detail)

    # Arrears: cash reduces the buckets directly (interest is in the accrued buckets).
    payoff = (
        cap_loan.rg_loan_princ + cap_loan.rg_loan_accrued
        + cap_loan.pf_loan_princ + cap_loan.pf_loan_accrued
        + cap_loan.vbl_loan_princ + cap_loan.vbl_loan_accrued
    )                                                                            # MF = SUM(LX:MC)
    remaining = attempted
    rg_accrued, remaining = _reduce_bucket(cap_loan.rg_loan_accrued, remaining)
    rg_princ, remaining = _reduce_bucket(cap_loan.rg_loan_princ, remaining)
    pf_accrued, remaining = _reduce_bucket(cap_loan.pf_loan_accrued, remaining)
    pf_princ, remaining = _reduce_bucket(cap_loan.pf_loan_princ, remaining)
    vbl_accrued, remaining = _reduce_bucket(cap_loan.vbl_loan_accrued, remaining)
    vbl_princ, remaining = _reduce_bucket(cap_loan.vbl_loan_princ, remaining)
    applied = attempted - remaining
    new_loan = LoanState(
        rg_loan_princ=rg_princ, rg_loan_accrued=rg_accrued,
        pf_loan_princ=pf_princ, pf_loan_accrued=pf_accrued,
        vbl_loan_princ=vbl_princ, vbl_loan_accrued=vbl_accrued,
    )
    detail = _loan_cap_repay_detail(
        cap_loan, advance=False,
        reg_payoff=0.0, pref_payoff=0.0, payoff=payoff,
        requested=requested, attempted=attempted,
        prem_from_lumpsum=prem_lump, prem_from_scheduled=prem_sched,
        reg_repay=0.0, pref_repay=0.0,
        total_reduction=applied, leftover=max(0.0, attempted - payoff),
    )
    return LoanRepayResult(loan_state=new_loan, applied_repayment=applied, detail=detail)


def empty_loan_cap_repay_detail() -> dict:
    """Zero-valued Loan Capitalize and Repay detail (all display keys present)."""
    return _loan_cap_repay_detail(
        LoanState(), advance=False, reg_payoff=0.0, pref_payoff=0.0, payoff=0.0,
        requested=0.0, attempted=0.0, prem_from_lumpsum=0.0, prem_from_scheduled=0.0,
        reg_repay=0.0, pref_repay=0.0, total_reduction=0.0, leftover=0.0,
    )


def _loan_cap_repay_detail(
    cap_loan: LoanState,
    *,
    advance: bool,
    reg_payoff: float,
    pref_payoff: float,
    payoff: float,
    requested: float,
    attempted: float,
    prem_from_lumpsum: float = 0.0,
    prem_from_scheduled: float = 0.0,
    reg_repay: float,
    pref_repay: float,
    total_reduction: float,
    leftover: float,
) -> dict:
    """Build the RERUN "Loan Capitalize and Repay" display dict (cols LX..MZ).

    Keys match :data:`suiteview.illustration.ui.values_tab` exactly. The
    post-repay buckets (MS..MX) and policy debt (NA) come from the engine's
    post-repay loan state, not from here.
    """
    return {
        # Capitalized (pre-repay) buckets — LX..MC
        "Advance - Rg Ln Princ/Total": cap_loan.rg_loan_princ,
        "Advance - Rg Ln Int Accrued": cap_loan.rg_loan_accrued,
        "Advance - Pf Ln Princ/Total": cap_loan.pf_loan_princ,
        "Advance - Pf Ln Int Accrued": cap_loan.pf_loan_accrued,
        "Advance - Var Ln Princ/Total": cap_loan.vbl_loan_princ,
        "Advance - Var Ln Int Accrued": cap_loan.vbl_loan_accrued,
        # Payoffs — MD, ME, MF (advance-only payoffs; MF = sum of buckets for arrears)
        "Advance - Adv Reg LN Payoff": reg_payoff,
        "Advance - Adv Pref LN Payoff": pref_payoff,
        "Advance - LoanPayoff": payoff,
        # Premium/force-out repayment sources — MG..MK. MG (PremToPayLoanInterest)
        # and MJ (LoanRepayFromForceout) are not modeled; MH/MI carry the
        # sInput_ApplyPremToLoan diversion and MK their sum.
        "Arrears - PremToPayLoanInterest": 0.0,
        "Arrears - From Lumpsum": prem_from_lumpsum,
        "Arrears - From Scheduled Prem": prem_from_scheduled,
        "Arrears - LoanRepayFromForceout": 0.0,
        "Arrears - LoanRepayFromPremAndForceout": prem_from_lumpsum + prem_from_scheduled,
        # Requested / attempted — MN, MO
        "Arrears - Requested Loan Repayment": requested,
        "Arrears - Total Loan Repayment Attempted": attempted,
        # Advance split + gross-up — MP, MQ, MR
        "Advance - Adv Reg LN Repay": reg_repay,
        "Advance - Adv Pref LN Repay": pref_repay,
        "Advance - Adv Total Loan Repayment": (total_reduction if advance else 0.0),
        # Leftover + total reduction — MY, MZ
        "LNRepayLeftOver": leftover,
        "TotalLoanReduction": total_reduction,
    }
