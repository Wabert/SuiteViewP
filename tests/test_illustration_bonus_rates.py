from datetime import date

import pytest

from suiteview.illustration.core.bonus_rates import BonusConfig, load_bonus_config
from suiteview.illustration.core.interest_calc import credit_interest
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def test_int_bonus_table_resolves_1u135d00_latest_effective_rate():
    bonus = load_bonus_config(" 1u135d00 ", date(2026, 6, 15))

    assert bonus.bonus_dur_rate == 0.009
    assert bonus.bonus_dur_threshold == 10
    assert bonus.bonus_av_rate == 0.0
    assert bonus.bonus_av_threshold == 0.0


def test_credit_interest_uses_duration_bonus_after_threshold():
    policy = IllustrationPolicyData(current_interest_rate=0.03)
    config = load_plancode("1U135D00")
    bonus = BonusConfig(bonus_dur_rate=0.009, bonus_dur_threshold=10)

    result = credit_interest(
        100_000.0,
        policy,
        config,
        IllustrationRates(),
        bonus,
        rate_year=11,
        attained_age=60,
        month_date=date(2026, 6, 15),
    )

    assert result.bonus_interest_rate == 0.009
    assert result.effective_annual_rate == 0.039
    assert result.interest_credited > 0.0


def test_credit_interest_does_not_use_duration_bonus_at_threshold_year():
    policy = IllustrationPolicyData(current_interest_rate=0.03)
    config = load_plancode("1U135D00")
    bonus = BonusConfig(bonus_dur_rate=0.009, bonus_dur_threshold=10)

    result = credit_interest(
        100_000.0,
        policy,
        config,
        IllustrationRates(),
        bonus,
        rate_year=10,
        attained_age=59,
        month_date=date(2026, 6, 15),
    )

    assert result.bonus_interest_rate == 0.0
    assert result.effective_annual_rate == 0.03


def test_credit_interest_displays_average_days_when_exact_days_is_off():
    policy = IllustrationPolicyData(current_interest_rate=0.05)
    config = PlancodeConfig(plancode="TEST", interest_method="ExactDays")

    result = credit_interest(
        100_000.0,
        policy,
        config,
        IllustrationRates(),
        BonusConfig(),
        rate_year=1,
        attained_age=60,
        month_date=date(2026, 1, 15),
        exact_days_interest=False,
    )

    assert result.days_in_month == pytest.approx(365.0 / 12.0)
    assert result.actual_days_in_month == 31
    assert result.monthly_interest_rate == pytest.approx((1.0 + 0.05) ** (1.0 / 12.0) - 1.0)


def test_credit_interest_displays_actual_days_when_exact_days_is_on():
    policy = IllustrationPolicyData(current_interest_rate=0.05)
    config = PlancodeConfig(plancode="TEST", interest_method="MonthlyCompounding")

    result = credit_interest(
        100_000.0,
        policy,
        config,
        IllustrationRates(),
        BonusConfig(),
        rate_year=1,
        attained_age=60,
        month_date=date(2026, 1, 15),
        exact_days_interest=True,
    )

    assert result.days_in_month == 31.0
    assert result.actual_days_in_month == 31
    assert result.monthly_interest_rate == pytest.approx((1.0 + 0.05) ** (31.0 / 365.0) - 1.0)


def test_credit_interest_uses_plancode_loan_collateral_credit_rates():
    policy = IllustrationPolicyData(current_interest_rate=0.05, guaranteed_interest_rate=0.03)
    config = PlancodeConfig(
        plancode="TEST",
        interest_method="MonthlyCompounding",
        loan_charge_rate_curr=0.02,
        pref_loan_charge_rate_curr=0.04,
    )

    result = credit_interest(
        100_000.0,
        policy,
        config,
        IllustrationRates(),
        BonusConfig(),
        rate_year=1,
        attained_age=60,
        month_date=date(2026, 6, 15),
        reg_loan_balance=20_000.0,
        pref_loan_balance=10_000.0,
        exact_days_interest=False,
    )

    regular_monthly = (1.0 + 0.02) ** (1.0 / 12.0) - 1.0
    preferred_monthly = (1.0 + 0.04) ** (1.0 / 12.0) - 1.0
    free_monthly = (1.0 + 0.05) ** (1.0 / 12.0) - 1.0
    assert result.reg_loan_credit_rate == 0.02
    assert result.pref_loan_credit_rate == 0.04
    assert result.reg_impaired_int == pytest.approx(20_000.0 * regular_monthly)
    assert result.pref_impaired_int == pytest.approx(10_000.0 * preferred_monthly)
    assert result.interest_credited == pytest.approx(
        70_000.0 * free_monthly
        + 20_000.0 * regular_monthly
        + 10_000.0 * preferred_monthly
    )