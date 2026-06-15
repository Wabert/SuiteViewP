from datetime import date

from suiteview.illustration.core.bonus_rates import BonusConfig, load_bonus_config
from suiteview.illustration.core.interest_calc import credit_interest
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import load_plancode
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