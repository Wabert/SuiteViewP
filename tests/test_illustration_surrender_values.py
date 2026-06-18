from datetime import date

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData


def test_engine_allows_negative_ending_surrender_value(monkeypatch):
    monkeypatch.setattr(
        calc_engine,
        "load_plancode",
        lambda _plancode: PlancodeConfig(
            plancode="TEST",
            gint=0.0,
            dbd=0.0,
            premium_load="0",
            prem_flat_load=0.0,
            epu_code="0",
            mfee="0",
            poav_code="0",
            bonus="0",
            corridor_code=None,
            snet_period=0,
            lapse_value="SV",
        ),
    )
    monkeypatch.setattr(calc_engine, "load_bonus_config", lambda _plancode, _date: BonusConfig())

    policy = IllustrationPolicyData(
        plancode="TEST",
        issue_date=date(2026, 1, 1),
        valuation_date=date(2026, 1, 1),
        issue_age=45,
        attained_age=45,
        maturity_age=46,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=10.0,
        segments=[CoverageSegment(coverage_phase=1, issue_date=date(2026, 1, 1), face_amount=100_000.0, units=100.0)],
    )
    rates = IllustrationRates(scr=[0.0, 1.0])

    results = IllustrationEngine().project(
        policy,
        months=1,
        stop_on_lapse=False,
        rates_override=rates,
        bonus_override=BonusConfig(),
    )

    assert results[0].surrender_value == -90.0
    assert results[1].surrender_value == -90.0