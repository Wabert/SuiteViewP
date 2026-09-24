from datetime import date

import pytest

from suiteview.illustration.core.bonus_rates import BonusConfig, load_bonus_config
from suiteview.illustration.core.interest_calc import credit_interest
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def test_int_bonus_table_resolves_1u135d00_latest_effective_rate():
    bonus = load_bonus_config(" 1u135d00 ", date(2026, 6, 15))

    assert bonus.bonus_dur_rate == 0.009
    assert bonus.bonus_dur_threshold == 10
    assert bonus.bonus_av_rate == 0.0
    assert bonus.bonus_av_threshold == 0.0


def test_int_bonus_table_resolves_1u135k00_latest_effective_rate():
    bonus = load_bonus_config("1U135K00", date(2026, 5, 26))

    assert bonus.bonus_dur_rate == 0.009
    assert bonus.bonus_dur_threshold == 10
    assert bonus.bonus_av_rate == 0.0
    assert bonus.bonus_av_threshold == 0.0


@pytest.mark.parametrize(
    ("valuation_date", "expected_rate"),
    [
        (date(2023, 1, 31), 0.005),
        (date(2023, 2, 1), 0.009),
        (date(2026, 9, 22), 0.009),
    ],
)
def test_int_bonus_table_resolves_1u135p00_effective_rate(valuation_date, expected_rate):
    bonus = load_bonus_config(" 1u135p00 ", valuation_date)

    assert bonus.bonus_dur_rate == expected_rate
    assert bonus.bonus_dur_threshold == 10
    assert bonus.bonus_av_rate == 0.0
    assert bonus.bonus_av_threshold == 0.0
    assert bonus.guaranteed().bonus_dur_rate == 0.0
    assert bonus.guaranteed().bonus_av_rate == 0.0


@pytest.mark.parametrize(
    ("rate_year", "guaranteed", "expected_rate"),
    [(10, False, 0.0), (11, False, 0.009), (12, False, 0.009), (11, True, 0.0)],
)
def test_1u135p00_duration_bonus_starts_in_year_11(rate_year, guaranteed, expected_rate):
    bonus = load_bonus_config("1U135P00", date(2023, 2, 1))
    if guaranteed:
        bonus = bonus.guaranteed()

    result = credit_interest(
        100_000.0,
        IllustrationPolicyData(current_interest_rate=0.03),
        load_plancode("1U135P00"),
        IllustrationRates(),
        bonus,
        rate_year=rate_year,
        attained_age=60,
        month_date=date(2023, 2, 1),
    )

    assert result.bonus_interest_rate == expected_rate
    assert result.effective_annual_rate == pytest.approx(0.03 + expected_rate)


def test_int_bonus_table_resolves_1u147800_current_and_guaranteed_rates():
    bonus = load_bonus_config("1U147800", date(2026, 8, 3))

    assert bonus.bonus_dur_rate == 0.0025
    assert bonus.bonus_dur_threshold == 0
    assert bonus.guaranteed().bonus_dur_rate == 0.001
    assert bonus.guaranteed().bonus_av_rate == 0.0


def test_missing_guaranteed_bonus_fields_default_to_zero():
    bonus = load_bonus_config("1U135D00", date(2026, 6, 15)).guaranteed()

    assert bonus.bonus_dur_rate == 0.0
    assert bonus.bonus_av_rate == 0.0


def test_guaranteed_projection_uses_1u147800_guaranteed_bonus(monkeypatch):
    from suiteview.illustration.core import guaranteed_projection

    captured = {}

    class RecordingEngine:
        def project(self, _policy, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(
        guaranteed_projection, "load_plancode",
        lambda _plancode: PlancodeConfig(plancode="1U147800"),
    )
    monkeypatch.setattr(
        guaranteed_projection, "load_rates",
        lambda *_args, **_kwargs: IllustrationRates(),
    )
    policy = IllustrationPolicyData(
        plancode="1U147800",
        issue_date=date(2010, 1, 1),
        valuation_date=date(2026, 8, 3),
    )

    guaranteed_projection.run_guaranteed_projection(
        policy,
        [MonthlyState(duration=0), MonthlyState(duration=1)],
        engine=RecordingEngine(),
    )

    bonus = captured["bonus_override"]
    assert bonus.bonus_dur_rate == 0.001
    assert bonus.bonus_dur_threshold == 0
    assert bonus.bonus_av_rate == 0.0


@pytest.mark.parametrize(
    ("guaranteed", "expected_rate"),
    [(False, 0.0025), (True, 0.001)],
)
def test_1u147800_duration_bonus_starts_immediately(guaranteed, expected_rate):
    bonus = load_bonus_config("1U147800", date(2026, 8, 3))
    if guaranteed:
        bonus = bonus.guaranteed()

    result = credit_interest(
        100_000.0,
        IllustrationPolicyData(current_interest_rate=0.03),
        load_plancode("1U147800"),
        IllustrationRates(),
        bonus,
        rate_year=1,
        attained_age=40,
        month_date=date(2026, 8, 3),
    )

    assert result.bonus_interest_rate == expected_rate
    assert result.effective_annual_rate == 0.03 + expected_rate


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
    assert result.unimpaired_int == pytest.approx(70_000.0 * free_monthly)
    assert result.interest_credited == pytest.approx(
        70_000.0 * free_monthly
        + 20_000.0 * regular_monthly
        + 10_000.0 * preferred_monthly
    )