"""Interim AV Quote: monthliversary AV rolled forward to a quote date."""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.interest_calc import interest_days
from suiteview.illustration.core.interim_value import (
    InterimPremium,
    InterimValueUnavailable,
    apply_interim_value,
    roll_forward_account_value,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.polview.services.interim_account_value import premiums_after_valuation


def _policy(**overrides):
    values = dict(
        policy_number="INT001", issue_date=date(2020, 5, 1), issue_age=45,
        valuation_date=date(2026, 5, 1), policy_year=7, duration=73, maturity_age=121,
        account_value=1_000.0, current_interest_rate=0.04,
        premiums_paid_to_date=5_000.0, premiums_ytd=100.0, cost_basis=4_000.0,
    )
    values.update(overrides)
    return IllustrationPolicyData(**values)


def _roll(policy, premiums, quote):
    return roll_forward_account_value(
        policy, PlancodeConfig(), IllustrationRates(), BonusConfig(), premiums, quote)


def test_interest_days_exclude_leap_day():
    assert interest_days(date(2026, 9, 1), date(2026, 9, 28)) == 27
    assert interest_days(date(2028, 2, 15), date(2028, 3, 15)) == 28
    assert interest_days(date(2028, 2, 29), date(2028, 3, 1)) == 1
    assert interest_days(date(2026, 9, 28), date(2026, 9, 1)) == 0


def test_roll_forward_credits_each_premium_from_its_effective_date():
    premium = InterimPremium(date(2026, 5, 11), gross=500.0, net=475.0)
    interim = _roll(_policy(), [premium], date(2026, 5, 21))
    first = 1_000.0 * (1.04 ** (10 / 365) - 1)
    second = (1_000.0 + first + 475.0) * (1.04 ** (10 / 365) - 1)
    assert interim.premiums == (premium,)
    assert interim.interest == round(first + second, 2)
    assert interim.account_value == round(1_475.0 + first + second, 2)
    assert interim.gross_premium == 500.0 and interim.net_premium == 475.0
    assert interim.next_monthliversary == date(2026, 6, 1)
    assert interim.is_rolled_forward


def test_negative_value_earns_interest_only_once_premium_makes_it_positive():
    premium = InterimPremium(date(2026, 5, 11), gross=1_500.0, net=1_500.0)
    interim = _roll(_policy(account_value=-817.16), [premium], date(2026, 5, 21))
    expected = (1_500.0 - 817.16) * (1.04 ** (10 / 365) - 1)
    assert interim.interest == round(expected, 2)


def test_quote_on_valuation_date_is_the_monthliversary_value():
    later = InterimPremium(date(2026, 5, 2), 100.0, 100.0)
    interim = _roll(_policy(), [later], date(2026, 5, 1))
    assert interim.premiums == () and interim.interest == 0.0
    assert interim.account_value == 1_000.0 and not interim.is_rolled_forward


def test_unprocessed_monthliversary_is_reported():
    with pytest.raises(InterimValueUnavailable, match="06/01/2026 monthliversary"):
        _roll(_policy(), [], date(2026, 6, 1))


def test_apply_interim_value_adds_received_premiums_to_accumulators():
    policy = _policy(
        tamra_7pay_start_date=date(2024, 3, 1),
        tamra_7year_contributions=[1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 0.0],
    )
    interim = _roll(policy, [InterimPremium(date(2026, 5, 11), 500.0, 475.0)], date(2026, 5, 21))
    rolled = apply_interim_value(policy, interim)
    assert rolled.account_value == interim.account_value
    assert rolled.premiums_paid_to_date == 5_500.0
    assert rolled.premiums_ytd == 600.0 and rolled.cost_basis == 4_500.0
    assert rolled.tamra_7year_contributions == [1.0, 2.0, 503.0, 0.0, 0.0, 0.0, 0.0]
    assert policy.account_value == 1_000.0 and policy.premiums_paid_to_date == 5_000.0


def test_premiums_after_valuation_reads_net_and_rejects_missing_net():
    def tx(when, gross, net):
        return SimpleNamespace(trans_date=when, gross_amount=gross, net_amount=net)

    source = SimpleNamespace(get_premium_transactions=lambda: [
        tx(date(2026, 5, 1), 10, 10), tx(date(2026, 5, 4), 160, 144.8)])
    assert premiums_after_valuation(source, date(2026, 5, 1)) == (
        InterimPremium(date(2026, 5, 4), 160.0, 144.8),)
    missing = SimpleNamespace(get_premium_transactions=lambda: [tx(date(2026, 5, 4), 160, None)])
    with pytest.raises(InterimValueUnavailable, match="no net amount"):
        premiums_after_valuation(missing, date(2026, 5, 1))
