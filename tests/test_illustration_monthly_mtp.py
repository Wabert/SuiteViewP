"""Monthly targets retain exact cents and truncate fractional cents."""
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine, ProjectionTiming
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.summary_results import project_summary_row
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.illustration.ui.values_tab import IllustrationValuesTab


@pytest.mark.parametrize("timing", list(ProjectionTiming))
@pytest.mark.parametrize("monthly, expected", [
    (32.66, 32.66),  # UIP12968: recorded monthly MAP for an annual MAP of 392.
    (392.0 / 12.0, 32.66),
    (32.659, 32.65),
    (100.0, 100.0),
    (0.0, 0.0),
])
def test_projection_monthly_mtp_and_accumulation(monkeypatch, timing, monthly, expected):
    policy = IllustrationPolicyData(
        policy_number="UIP12968",
        plancode="TEST",
        issue_date=date(2020, 1, 15),
        valuation_date=date(2026, 9, 15),
        issue_age=40,
        attained_age=46,
        policy_year=7,
        policy_month=9,
        duration=81,
        maturity_age=121,
        face_amount=100_000.0,
        account_value=10_000.0,
        mtp=monthly,
        accumulated_mtp=3_951.86,
    )
    config = PlancodeConfig(
        plancode="TEST")
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _plan: config)
    monkeypatch.setattr(
        calc_engine, "compute_target_premiums",
        lambda *_args, **_kwargs: TargetPremiumResult(
            mtp_annual=392.0, mtp_by_coverage={1: 392.0}),
    )
    states = IllustrationEngine().project(
        policy, months=12, timing=timing, stop_on_lapse=False,
        rates_override=IllustrationRates(), bonus_override=BonusConfig(),
    )

    assert len(states) == 13
    for month, state in enumerate(states):
        assert state.monthly_mtp == expected
        assert state.accumulated_mtp == pytest.approx(3_951.86 + month * expected)
        detail = IllustrationValuesTab._target_premium_values(state)
        assert detail["vMonthlyMTP"] == expected
        assert detail["vAccumMTP"] == state.accumulated_mtp
        assert project_summary_row(policy, state)["MonthlyMTP"] == expected
    assert policy.mtp == monthly


def test_annual_map_truncates_to_monthly_cents():
    assert TargetPremiumResult(mtp_annual=392.0).mtp_monthly == 32.66
