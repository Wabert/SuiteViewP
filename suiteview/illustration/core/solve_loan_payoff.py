"""Solve the "Pay-off" loan repayment — the level modal repayment that clears
the loan by the end of its window.

A Pay-off row in the Loan Repayments section carries a start year, a mode, and
a span (For Years / To Age) but no amount: this solver finds the level
repayment, paid on each modal date in the window, such that the loan balance
is zero at the end of the window. Because the engine applies loan repayments
BEFORE new loans within a month (RERUN "Loan Capitalize and Repay" runs at row
16, new loans after the monthly deduction), the balance is zero *just before*
any new loan that follows the window — a payoff can be chained straight into a
fresh borrowing plan.

The balance is read off the month FOLLOWING the window (``check_date``, the
anniversary that ends it): that state's post-capitalize/repay beginning
buckets are exactly the loan the next new loan would stack onto. When the
window runs to maturity there is no following month, so the last projected
month's ending policy debt is used instead.

The repayment amount is found the same way the other solvers work
(``solve_lumpsum_to_next_premium``): bracket an amount that pays the loan off,
then bisect "paid off" down to the cent and round UP so the result lands on
the paid-off side. Overshoot on the final payment is harmless — ``repay_loan``
caps every repayment at the loan payoff.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

# Subtype stamped on the injected repayments so the values/report can label them.
PAYOFF_SUBTYPE = "loan_payoff"

# A paid-off loan may strand IEEE dust below a cent; treat under a half-cent as zero.
_PAID_OFF_TOLERANCE = 0.005

# Backstop so a pathological projection can never loop the upper-bracket search.
_MAX_BRACKET_DOUBLINGS = 24


class LoanPayoffError(Exception):
    """The bracket search could not find a repayment that pays the loan off."""


@dataclass
class LoanPayoffResult:
    repayment: float                # level modal repayment (0.0 — nothing owed)
    residual_balance: float         # loan balance left at the check with the solved amount
    check_date: Optional[date]      # where the balance was measured (None → last month)
    iterations: int                 # engine projections spent solving


def _months_from_issue(issue: date, when: date) -> int:
    """Whole engine months from issue to ``when`` (monthliversary-aligned).

    Month-end clamping (issue on the 29th–31st) makes the naive year/month
    delta ambiguous, so verify against relativedelta and bump if short.
    """
    months = (when.year - issue.year) * 12 + (when.month - issue.month)
    if issue + relativedelta(months=months) < when:
        months += 1
    return months


def solve_loan_payoff(
    policy: IllustrationPolicyData,
    *,
    repayment_dates: List[date],
    check_date: Optional[date],
    base_future_inputs: Optional[IllustrationInputSet] = None,
    base_options: Optional[IllustrationOptions] = None,
    engine: Optional[IllustrationEngine] = None,
    resolution: float = 0.01,
) -> LoanPayoffResult:
    """Level repayment on ``repayment_dates`` that zeroes the loan at ``check_date``.

    Args:
        repayment_dates: the modal monthliversaries the repayment lands on
            (already expanded by the inputs UI — forecast-clamped like any
            other repayment row).
        check_date: the monthliversary ending the window (the anniversary
            after its last year). The post-capitalize/repay beginning loan of
            that month is the solve target — the balance just before any new
            loan that month. ``None`` (or a date past the projection) falls
            back to the last projected month's ending policy debt.
        base_future_inputs: the run's future inputs; trial repayments layer on
            top so premiums, new loans, and withdrawals all feed the balance.
        base_options: the run's toggles, honored as-is.

    Returns a :class:`LoanPayoffResult`; ``repayment`` is 0.0 when the loan is
    already gone by the check (nothing to solve).
    """
    engine = engine or IllustrationEngine()
    options = base_options if base_options is not None else IllustrationOptions()
    base = base_future_inputs
    if not repayment_dates or policy.issue_date is None:
        return LoanPayoffResult(repayment=0.0, residual_balance=0.0,
                                check_date=check_date, iterations=0)

    horizon = check_date or (max(repayment_dates) + relativedelta(months=1))
    project_months = max(1, _months_from_issue(policy.issue_date, horizon)
                         - policy.duration + 1)

    def project(amount: float) -> List[MonthlyState]:
        dated = list(base.dated_transactions) if base is not None else []
        if amount > 0:
            dated.extend(DatedTransaction(
                kind=TransactionKind.LOAN_REPAYMENT, effective_date=when,
                amount=float(amount), subtype=PAYOFF_SUBTYPE)
                for when in repayment_dates)
        future = IllustrationInputSet(
            scheduled_transactions=list(base.scheduled_transactions) if base is not None else [],
            dated_transactions=dated,
            policy_changes=list(base.policy_changes) if base is not None else [])
        # stop_on_lapse off so the check month is populated even past a lapse.
        return engine.project(policy, months=project_months, future_inputs=future,
                              options=options, stop_on_lapse=False)

    def balance(states: List[MonthlyState]) -> float:
        # The check month's beginning loan, after capitalize/repay but before
        # its new loan — the buckets the next borrowing would stack onto.
        if check_date is not None:
            for state in states:
                if state.date == check_date:
                    return (state.rg_loan_princ + state.rg_loan_accrued
                            + state.pf_loan_princ + state.pf_loan_accrued
                            + state.vbl_loan_princ + state.vbl_loan_accrued)
        # Window ends at maturity (or the projection stops short): the last
        # month's ending debt is the same "nothing left owing" test.
        return float(states[-1].policy_debt) if states else 0.0

    def paid_off(amount: float) -> tuple[bool, float]:
        remaining = balance(project(amount))
        return remaining <= _PAID_OFF_TOLERANCE, remaining

    iterations = 1
    done, base_balance = paid_off(0.0)
    if done:
        return LoanPayoffResult(repayment=0.0, residual_balance=round(base_balance, 2),
                                check_date=check_date, iterations=iterations)

    # Bracket: seed at the check-date balance spread level across the payments
    # (it already carries the interest growth the repayments must outrun).
    lo = 0.0
    hi = max(base_balance / len(repayment_dates) * 1.25, 1.0)
    doublings = 0
    while True:
        done, _ = paid_off(hi)
        iterations += 1
        if done:
            break
        hi *= 2.0
        doublings += 1
        if doublings > _MAX_BRACKET_DOUBLINGS:
            raise LoanPayoffError(
                "Could not find a loan repayment that pays the loan off by the "
                "end of the Pay-off period — the loan balance keeps outrunning "
                "the repayments. Check the Pay-off years against any new loans "
                "requested in the same period.")

    # Bisect to HALF the resolution, then test the rounded candidate directly
    # — ceiling the raw ``hi`` can overshoot a full step when the boundary
    # sits just under a grid point.
    while hi - lo > resolution / 2.0:
        mid = (lo + hi) / 2.0
        done, _ = paid_off(mid)
        iterations += 1
        if done:
            hi = mid
        else:
            lo = mid

    repayment = round(math.ceil(lo / resolution - 1e-9) * resolution, 2)
    done, residual = paid_off(repayment)
    iterations += 1
    if not done:
        repayment = round(repayment + resolution, 2)
        _, residual = paid_off(repayment)
        iterations += 1
    return LoanPayoffResult(repayment=repayment,
                            residual_balance=round(residual, 2),
                            check_date=check_date, iterations=iterations)
