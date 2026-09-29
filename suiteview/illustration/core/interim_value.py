"""Interim account value: roll the valuation-date AV forward to a quote date.

CyberLife stores the account value as of the last monthliversary, after that
month's deduction. Premiums received since then are credited to the account
value on their effective dates and earn interest from those dates. This module
rolls that monthliversary value forward to a quote date strictly before the
next monthliversary:

* the monthliversary AV accrues interest from the valuation date;
* each later premium adds its **net** amount (after premium load) on its
  effective date and accrues interest from there;
* interest is credited with :func:`credit_interest` over the exact interest
  days between events (365-day year, Feb 29 excluded), so declared/bonus rates,
  loaned-AV credit rates and "no interest on a negative AV" match the engine.

Interest on indexed (IUL) segments is only credited at segment maturity; the
roll-forward uses the declared rate the engine applies to the account value.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.interest_calc import credit_interest, interest_days
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData


class InterimValueUnavailable(ValueError):
    """The account value cannot be rolled forward to the requested date."""


@dataclass(frozen=True)
class InterimPremium:
    """A premium received after the valuation monthliversary."""

    received: date
    gross: float
    net: float


@dataclass(frozen=True)
class InterimAccountValue:
    """Valuation-date AV rolled forward to ``quote_date``."""

    valuation_date: date
    quote_date: date
    next_monthliversary: date
    valuation_account_value: float
    premiums: tuple[InterimPremium, ...]
    interest: float
    account_value: float

    @property
    def gross_premium(self) -> float:
        return sum(premium.gross for premium in self.premiums)

    @property
    def net_premium(self) -> float:
        return sum(premium.net for premium in self.premiums)

    @property
    def is_rolled_forward(self) -> bool:
        return self.quote_date > self.valuation_date


def next_monthliversary(policy: IllustrationPolicyData) -> date:
    """The engine's first projected month date after the valuation month."""
    if policy.issue_date is None:
        raise InterimValueUnavailable("Issue date is required to find the next monthliversary.")
    return policy.issue_date + relativedelta(months=policy.duration)


def roll_forward_account_value(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    bonus: BonusConfig,
    premiums: Iterable[InterimPremium],
    quote_date: date,
) -> InterimAccountValue:
    """Roll ``policy.account_value`` from its valuation date to ``quote_date``.

    ``premiums`` must be the premiums received after the valuation date; those
    effective after ``quote_date`` are ignored. Raises
    :class:`InterimValueUnavailable` when the valuation date is missing or the
    next monthliversary has not been processed yet (its deduction would be
    missing from the roll-forward).
    """
    valuation = policy.valuation_date
    if valuation is None:
        raise InterimValueUnavailable("Valuation date was not found.")
    next_mv = next_monthliversary(policy)
    if quote_date >= next_mv:
        raise InterimValueUnavailable(
            f"The {next_mv:%m/%d/%Y} monthliversary has not been processed yet "
            f"(values are as of {valuation:%m/%d/%Y}); an interim value cannot "
            "skip a monthly deduction.")
    quote = max(quote_date, valuation)
    received = tuple(sorted(
        (premium for premium in premiums if valuation < premium.received <= quote),
        key=lambda premium: premium.received,
    ))
    balance = float(policy.account_value)
    interest = 0.0
    as_of = valuation
    for when, amount in [*((p.received, p.net) for p in received), (quote, 0.0)]:
        credited = _interest(policy, config, rates, bonus, balance, as_of, when)
        interest += credited
        balance += credited + amount
        as_of = when
    interest = round(interest, 2)
    net = sum(premium.net for premium in received)
    return InterimAccountValue(
        valuation_date=valuation,
        quote_date=quote,
        next_monthliversary=next_mv,
        valuation_account_value=float(policy.account_value),
        premiums=received,
        interest=interest,
        account_value=round(float(policy.account_value) + net + interest, 2),
    )


def apply_interim_value(
    policy: IllustrationPolicyData, interim: InterimAccountValue,
) -> IllustrationPolicyData:
    """Copy ``policy`` with the interim AV and the received premiums' accumulators.

    CyberLife's premium totals are as of the valuation monthliversary, so the
    gross premiums received since then are added to premiums-to-date, the
    policy-year total, cost basis and the current TAMRA year's contributions.
    """
    rolled = copy.deepcopy(policy)
    gross = interim.gross_premium
    rolled.account_value = interim.account_value
    rolled.premiums_paid_to_date += gross
    rolled.premiums_ytd += gross
    rolled.cost_basis += gross
    contributions = list(rolled.tamra_7year_contributions or [])
    start = rolled.tamra_7pay_start_date
    if start is not None and len(contributions) == 7:
        for premium in interim.premiums:
            elapsed = relativedelta(premium.received, start)
            year = elapsed.years + 1
            if 1 <= year <= 7:
                contributions[year - 1] += premium.gross
        rolled.tamra_7year_contributions = contributions
    return rolled


def _interest(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    bonus: BonusConfig,
    balance: float,
    start: date,
    end: date,
) -> float:
    days = interest_days(start, end)
    if days <= 0:
        return 0.0
    return credit_interest(
        balance, policy, config, rates, bonus,
        int(policy.policy_year or 1), int(policy.attained_age or 0), start,
        reg_loan_balance=policy.regular_loan_principal,
        pref_loan_balance=policy.preferred_loan_principal,
        period_days=days,
    ).interest_credited
