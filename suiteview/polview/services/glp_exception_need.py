"""Quick screen: does this guideline-premium policy likely need a GLP Exception?

A GLP Exception is worth suggesting only when the account value cannot carry
the monthly deductions to the end of the current policy year **and** the
premium needed to make up the difference does not fit in the remaining
guideline (GPT) room. Guideline room refreshes at the anniversary, when the
GLP is added to AccumGLP, so the test horizon is the next policy anniversary.

This is a deliberately cheap, conservative estimate built from the facts
PolView already holds (no projection, no rate lookups). Each simplification
leans toward suggesting the exception:

* monthly deductions are the last processed deduction grossed up by
  ``DEDUCTION_CUSHION`` and charged on every monthliversary through and
  including the anniversary;
* the loan grows at ``ASSUMED_LOAN_RATE`` simple interest to the anniversary;
* no interest is credited to the account value;
* premiums fit the GPT room only after an assumed ``ASSUMED_PREMIUM_LOAD``.

The Policy Support GLP Exception quote does the real projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta

DEDUCTION_CUSHION = 0.10
ASSUMED_LOAN_RATE = 0.08
ASSUMED_PREMIUM_LOAD = 0.10


def gpt_premium_room(gsp: float, accumulated_glp: float, premium_td: float,
                     withdrawals: float) -> float:
    """Premium still allowed by the guideline premium test ("Prem Allowed by GPT")."""
    return max(0.0, max(gsp, accumulated_glp) - premium_td + withdrawals)


def next_policy_anniversary(issue_date: date, valuation_date: date) -> date:
    """First issue-date anniversary strictly after ``valuation_date``."""
    years = max(0, valuation_date.year - issue_date.year)
    anniversary = issue_date + relativedelta(years=years)
    while anniversary <= valuation_date:
        years += 1
        anniversary = issue_date + relativedelta(years=years)
    return anniversary


def monthliversaries_through(valuation_date: date, anniversary: date) -> int:
    """Monthliversaries after ``valuation_date`` up to and including ``anniversary``."""
    delta = relativedelta(anniversary, valuation_date)
    return max(1, delta.years * 12 + delta.months + (1 if delta.days else 0))


@dataclass(frozen=True)
class GlpExceptionNeed:
    """Inputs and outcome of the conservative year-end funding screen."""

    account_value: float
    policy_debt: float
    monthly_deduction: float
    months_to_anniversary: int
    anniversary: date
    gpt_room: float

    @property
    def deductions_to_anniversary(self) -> float:
        return self.monthly_deduction * (1 + DEDUCTION_CUSHION) * self.months_to_anniversary

    @property
    def loan_interest_to_anniversary(self) -> float:
        return max(0.0, self.policy_debt) * ASSUMED_LOAN_RATE * self.months_to_anniversary / 12

    @property
    def shortfall(self) -> float:
        """Net premium needed to carry the policy to the anniversary."""
        available = self.account_value - self.policy_debt
        return max(0.0, self.deductions_to_anniversary + self.loan_interest_to_anniversary - available)

    @property
    def net_room(self) -> float:
        """GPT room after the assumed premium load."""
        return self.gpt_room * (1 - ASSUMED_PREMIUM_LOAD)

    @property
    def needed(self) -> bool:
        return self.shortfall > 0 and self.shortfall > self.net_room

    def explanation(self) -> str:
        return (
            f"Estimated shortfall to the {self.anniversary.month}/{self.anniversary.day:02d}/"
            f"{self.anniversary.year} anniversary exceeds the guideline premium room.\n"
            f"  AV ${self.account_value:,.2f} less loan ${self.policy_debt:,.2f}\n"
            f"  {self.months_to_anniversary} deductions of ${self.monthly_deduction:,.2f} "
            f"+{DEDUCTION_CUSHION:.0%} = ${self.deductions_to_anniversary:,.2f}\n"
            f"  Loan interest at {ASSUMED_LOAN_RATE:.0%} = ${self.loan_interest_to_anniversary:,.2f}\n"
            f"  Shortfall ${self.shortfall:,.2f} vs GPT room ${self.gpt_room:,.2f} "
            f"(${self.net_room:,.2f} after {ASSUMED_PREMIUM_LOAD:.0%} load)\n"
            "Conservative estimate; open GLP Exception to project it properly."
        )


def estimate_glp_exception_need(
    *,
    account_value: Optional[float],
    policy_debt: Optional[float],
    monthly_deduction: Optional[float],
    issue_date: Optional[date],
    valuation_date: Optional[date],
    gpt_room: Optional[float],
) -> Optional[GlpExceptionNeed]:
    """The screen's result, or ``None`` when a required fact is unknown."""
    if None in (account_value, monthly_deduction, issue_date, valuation_date, gpt_room):
        return None
    anniversary = next_policy_anniversary(issue_date, valuation_date)
    return GlpExceptionNeed(
        account_value=float(account_value),
        policy_debt=float(policy_debt or 0),
        monthly_deduction=float(monthly_deduction),
        months_to_anniversary=monthliversaries_through(valuation_date, anniversary),
        anniversary=anniversary,
        gpt_room=float(gpt_room),
    )
