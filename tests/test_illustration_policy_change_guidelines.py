from datetime import date
from types import SimpleNamespace

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.monthly_guideline import GuidelineSolveResult
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.models.input_set import PolicyChangeEvent, PolicyChangeKind
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import BenefitInfo, IllustrationPolicyData, RiderInfo


def _patch_policy_change_dependencies(monkeypatch, solve_calls):
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_args: None)
    monkeypatch.setattr(
        calc_engine,
        "compute_target_premiums",
        lambda *_args, **_kwargs: SimpleNamespace(mtp_annual=120.0, ctp_annual=240.0),
    )

    def fake_solve(policy, _config, _attained_age, _change_date, _options, **_kwargs):
        active_items = sum(rider.is_active for rider in policy.riders)
        active_items += sum(benefit.is_active for benefit in policy.benefits)
        solve_calls.append(active_items)
        return GuidelineSolveResult(
            glp=60.0 + active_items * 60.0,
            gsp=120.0 + active_items * 120.0,
            seven_pay=36.0 + active_items * 36.0,
        )

    monkeypatch.setattr(calc_engine, "_solve_guideline_state", fake_solve)


def test_gpt_rider_drop_recalculates_guideline_premiums(monkeypatch):
    solve_calls = []
    _patch_policy_change_dependencies(monkeypatch, solve_calls)
    policy = IllustrationPolicyData(
        def_of_life_ins="GPT",
        glp=1_200.0,
        gsp=2_400.0,
        tamra_7pay_level=72.0,
        riders=[RiderInfo(coverage_phase=2, face_amount=50_000.0, is_active=True)],
    )

    outcome = calc_engine._apply_policy_change(
        policy,
        PlancodeConfig(),
        PolicyChangeEvent(
            kind=PolicyChangeKind.RIDER_DROP,
            effective_date=date(2026, 6, 9),
            value=0.0,
            metadata={"target": "cov:2"},
        ),
        attained_age=56,
        change_date=date(2026, 6, 9),
        rates=IllustrationRates(),
        rate_year=7,
        av=10_000.0,
    )

    assert outcome.coverage_changed
    assert policy.riders[0].is_active is False
    assert policy.glp == 1_140.0
    assert policy.gsp == 2_280.0
    assert policy.tamra_7pay_level == 36.0
    assert solve_calls == [1, 0, 0]


def test_gpt_benefit_drop_recalculates_guideline_premiums(monkeypatch):
    solve_calls = []
    _patch_policy_change_dependencies(monkeypatch, solve_calls)
    policy = IllustrationPolicyData(
        def_of_life_ins="GPT",
        glp=1_200.0,
        gsp=2_400.0,
        tamra_7pay_level=72.0,
        benefits=[BenefitInfo(coverage_phase=1, benefit_type="3", benefit_subtype="9", is_active=True)],
    )

    outcome = calc_engine._apply_policy_change(
        policy,
        PlancodeConfig(),
        PolicyChangeEvent(
            kind=PolicyChangeKind.RIDER_DROP,
            effective_date=date(2026, 6, 9),
            value=0.0,
            metadata={"target": "ben:39:1"},
        ),
        attained_age=56,
        change_date=date(2026, 6, 9),
        rates=IllustrationRates(),
        rate_year=7,
        av=10_000.0,
    )

    assert outcome.coverage_changed
    assert policy.benefits[0].is_active is False
    assert policy.glp == 1_140.0
    assert policy.gsp == 2_280.0
    assert policy.tamra_7pay_level == 36.0
    assert solve_calls == [1, 0, 0]


def test_cvat_rider_drop_does_not_solve_guideline_premiums(monkeypatch):
    solve_calls = []
    _patch_policy_change_dependencies(monkeypatch, solve_calls)
    policy = IllustrationPolicyData(
        def_of_life_ins="CVAT",
        glp=1_200.0,
        gsp=2_400.0,
        tamra_7pay_level=72.0,
        riders=[RiderInfo(coverage_phase=2, face_amount=50_000.0, is_active=True)],
    )

    outcome = calc_engine._apply_policy_change(
        policy,
        PlancodeConfig(),
        PolicyChangeEvent(
            kind=PolicyChangeKind.RIDER_DROP,
            effective_date=date(2026, 6, 9),
            value=0.0,
            metadata={"target": "cov:2"},
        ),
        attained_age=56,
        change_date=date(2026, 6, 9),
        rates=IllustrationRates(),
        rate_year=7,
        av=10_000.0,
    )

    assert outcome.coverage_changed
    assert policy.riders[0].is_active is False
    assert policy.glp == 1_200.0
    assert policy.gsp == 2_400.0
    assert policy.tamra_7pay_level == 72.0
    assert solve_calls == []