"""Interim AV Quote: the monthliversary AV rolled forward to a quote date.

Reads the premiums received after the valuation monthliversary from policy
history and rolls the account value forward with
:func:`suiteview.illustration.core.interim_value.roll_forward_account_value`.
Used by the Account Values tab and the Policy Support GLP Exception quote.
"""
from __future__ import annotations

from datetime import date

from suiteview.illustration.core.calc_engine import resolve_bonus_config
from suiteview.illustration.core.interim_value import (
    InterimAccountValue,
    InterimPremium,
    InterimValueUnavailable,
    roll_forward_account_value,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.polview.models.policy_sections.lookup import policy_attr


def premiums_after_valuation(policy, valuation_date: date) -> tuple[InterimPremium, ...]:
    """Unreversed premiums effective after ``valuation_date``.

    The net amount (after premium load) is what reaches the account value; a
    premium without one cannot be credited and is reported, not guessed.
    """
    premiums = []
    for transaction in policy_attr(policy, "get_premium_transactions")():
        if transaction.trans_date is None or transaction.trans_date <= valuation_date:
            continue
        if transaction.net_amount is None:
            raise InterimValueUnavailable(
                f"Premium received {transaction.trans_date:%m/%d/%Y} has no net amount.")
        premiums.append(InterimPremium(
            received=transaction.trans_date,
            gross=float(transaction.gross_amount),
            net=float(transaction.net_amount),
        ))
    return tuple(premiums)


def interim_account_value_quote(
    policy,
    ill_policy: IllustrationPolicyData,
    config: PlancodeConfig,
    rates: IllustrationRates,
    quote_date: date,
) -> InterimAccountValue:
    """Interim AV for ``policy`` on ``quote_date`` from its projection basis."""
    if ill_policy.valuation_date is None:
        raise InterimValueUnavailable("Valuation date was not found.")
    return roll_forward_account_value(
        ill_policy, config, rates, resolve_bonus_config(ill_policy, config, None),
        premiums_after_valuation(policy, ill_policy.valuation_date), quote_date,
    )
