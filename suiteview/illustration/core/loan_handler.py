"""Loan processing — Capitalization, Interest Accrual.

Pipeline positions (RERUN CalcEngine):
  - Loan Capitalize: Row 16 (before Apply Premium)
  - Loan Interest Accrual: Accumulation section cols 587-592 (after Interest Credit)

In-Arrears formula:
    monthly_accrual = principal * charge_rate * days_in_month / 365

Capitalization (at policy anniversary):
    principal += accrued_interest
    accrued_interest = 0
"""
from __future__ import annotations

from dataclasses import dataclass

from suiteview.illustration.models.plancode_config import PlancodeConfig


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
) -> LoanState:
    """Capitalize accrued loan interest into principal at anniversary.

    At each policy anniversary, accrued interest rolls into principal
    and accrued resets to zero.  Outside anniversary months, balances
    pass through unchanged.

    Args:
        rg_princ: Regular loan principal (from previous month or policy data).
        rg_accrued: Regular loan accrued interest.
        pf_princ: Preferred loan principal.
        pf_accrued: Preferred loan accrued interest.
        vbl_princ: Variable loan principal.
        vbl_accrued: Variable loan accrued interest.
        is_anniversary: True if this is the first month of a new policy year.

    Returns:
        LoanState with capitalized balances (no accrual yet).
    """
    if is_anniversary:
        return LoanState(
            rg_loan_princ=rg_princ + rg_accrued,
            rg_loan_accrued=0.0,
            pf_loan_princ=pf_princ + pf_accrued,
            pf_loan_accrued=0.0,
            vbl_loan_princ=vbl_princ + vbl_accrued,
            vbl_loan_accrued=0.0,
        )
    return LoanState(
        rg_loan_princ=rg_princ,
        rg_loan_accrued=rg_accrued,
        pf_loan_princ=pf_princ,
        pf_loan_accrued=pf_accrued,
        vbl_loan_princ=vbl_princ,
        vbl_loan_accrued=vbl_accrued,
    )


def accrue_loan_interest(
    loan: LoanState,
    config: PlancodeConfig,
    days_in_month: int,
) -> LoanState:
    """Accrue monthly loan interest charge (in-arrears).

    Formula per CalcEngine col 588:
        new_accrued = old_accrued + principal * charge_rate * days / 365

    Args:
        loan: Current loan balances (after capitalization).
        config: Plancode config with loan charge rates.
        days_in_month: Calendar days in the current month.

    Returns:
        Updated LoanState with accrued interest added.
    """
    if config.loan_type != "Arrears":
        # Advance loans: no monthly accrual (interest prepaid)
        return loan

    rg_interest = loan.rg_loan_princ * config.loan_charge_rate_guar * days_in_month / 365.0
    pf_interest = loan.pf_loan_princ * config.pref_loan_charge_rate_guar * days_in_month / 365.0
    vbl_interest = 0.0  # Variable loan rate handled separately if enabled

    return LoanState(
        rg_loan_princ=loan.rg_loan_princ,
        rg_loan_accrued=loan.rg_loan_accrued + rg_interest,
        pf_loan_princ=loan.pf_loan_princ,
        pf_loan_accrued=loan.pf_loan_accrued + pf_interest,
        vbl_loan_princ=loan.vbl_loan_princ,
        vbl_loan_accrued=loan.vbl_loan_accrued + vbl_interest,
        reg_loan_charge=rg_interest,
        pref_loan_charge=pf_interest,
    )
