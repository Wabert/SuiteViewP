"""Whole-year premium-duration solve mechanics."""
from types import SimpleNamespace

from suiteview.illustration.core.solve_premium_duration import solve_premium_duration
from suiteview.illustration.models.input_set import TransactionKind
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def _policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        issue_age=50,
        maturity_age=70,
        billing_frequency=1,
        modal_premium=100.0,
    )


def _duration(future_inputs, start_year: int, maturity_year: int) -> int:
    stops = [
        entry.policy_year
        for entry in future_inputs.scheduled_transactions
        if entry.kind == TransactionKind.PREMIUM
        and entry.policy_year > start_year
        and entry.amount == 0.0
    ]
    end_year = min(stops) - 1 if stops else maturity_year
    return end_year - start_year + 1


def _states(value: float) -> list:
    return [
        SimpleNamespace(
            policy_year=year,
            policy_month=month,
            av_end_of_month=value if year == 10 and month == 12 else 0.0,
            ending_sv=value if year == 10 and month == 12 else 0.0,
            shadow_eav=value if year == 10 and month == 12 else 0.0,
        )
        for year in range(1, 21)
        for month in range(1, 13)
    ]


def test_solve_returns_minimum_whole_year_duration():
    class _StubEngine:
        def project(self, _policy, *, future_inputs=None, **_kwargs):
            years = _duration(future_inputs, start_year=1, maturity_year=20)
            return _states(years * 1_000.0)

    result = solve_premium_duration(
        _policy(),
        premium=100.0,
        mode="M",
        target="av",
        amount=5_500.0,
        at_age=60,
        engine=_StubEngine(),
    )

    assert result.duration_years == 6
    assert result.end_policy_year == 6
    assert result.achieved_value == 6_000.0
    assert result.reached_target is True


def test_unreachable_target_returns_maturity_duration():
    class _PlateauEngine:
        def project(self, _policy, *, future_inputs=None, **_kwargs):
            return _states(3_000.0)

    result = solve_premium_duration(
        _policy(),
        premium=100.0,
        mode="M",
        target="sv",
        amount=5_000.0,
        at_age=60,
        engine=_PlateauEngine(),
    )

    assert result.duration_years == 20
    assert result.end_policy_year == 20
    assert result.achieved_value == 3_000.0
    assert result.reached_target is False
