"""Primary-insured table changes also change premium-waiver rating factors."""
from copy import deepcopy
from datetime import date

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.monthly_deduction import calculate_deduction
from suiteview.illustration.core.monthly_guideline import (
    build_guideline_basis,
    solve_guideline_premiums,
)
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.target_premium import TargetPremiumResult
from suiteview.illustration.models.input_set import (
    IllustrationInputSet, IllustrationOptions, PolicyChangeEvent, PolicyChangeKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo, CoverageSegment, IllustrationPolicyData, RiderInfo,
)


CHANGE_DATE = date(2026, 3, 15)


def _fixture(monkeypatch, *, pwot_basis=1, table_factor=0.25):
    policy = IllustrationPolicyData(
        plancode="TEST", issue_date=date(2020, 1, 15),
        valuation_date=date(2026, 1, 15), issue_age=40, attained_age=46,
        maturity_age=65, policy_year=7, policy_month=1, duration=73,
        face_amount=100_000.0, units=100.0, account_value=10_000.0,
        def_of_life_ins="GPT", glp=2000.0, gsp=20_000.0,
        mtp=100.0, ctp=1500.0, tamra_7pay_level=2000.0,
        tamra_7pay_start_date=date(2020, 1, 15),
        segments=[CoverageSegment(
            coverage_phase=1, issue_date=date(2020, 1, 15), issue_age=40,
            face_amount=100_000.0, units=100.0, table_rating=2,
        )],
        benefits=[
            BenefitInfo(
                coverage_phase=phase, benefit_type=kind, benefit_subtype=sub,
                units=10.0, benefit_amount=1000.0,
                rating_factor=1.0 + table_factor * 2 if kind in ("3", "4") else 1.5,
            )
            for kind, sub, phase in [
                ("3", "9", 1), ("4", "9", 2), ("1", "0", 1), ("6", "0", 1),
            ]
        ],
        riders=[RiderInfo(coverage_phase=3, table_rating=3, is_active=False)],
    )
    config = PlancodeConfig(
        plancode="TEST", gint=0.0, dbd=0.0, corridor_code=None,
        mfee="0", epu_code="0", premium_load="0", poav_code="0",
        bonus="0", table_rating_factor=table_factor, pwot_coi_basis=pwot_basis,
    )
    rates = IllustrationRates(
        segment_coi={1: [None] + [0.0] * 50},
        benefit_coi={
            key: [None] + [rate] * 50
            for key, rate in [("39", 0.02), ("49", 0.3), ("10", 0.1), ("60", 0.2)]
        },
    )
    monkeypatch.setattr(calc_engine, "load_plancode", lambda _: config)
    monkeypatch.setattr(calc_engine, "load_rates", lambda *_args, **_kwargs: rates)
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_: None)
    monkeypatch.setattr(
        calc_engine, "compute_target_premiums",
        lambda *_args, **_kwargs: TargetPremiumResult(mtp_annual=1200.0, ctp_annual=1500.0),
    )
    monkeypatch.setattr(calc_engine, "build_target_detail_snapshots", lambda *_: ({}, {}))
    return policy, config, rates


@pytest.mark.parametrize("new_table", [0, 1, 4])
@pytest.mark.parametrize("table_factor", [0.25, 0.5])
def test_table_change_updates_waivers_before_real_guideline_recalculation(
    monkeypatch, new_table, table_factor,
):
    policy, config, rates = _fixture(monkeypatch, table_factor=table_factor)
    before = deepcopy(policy)
    expected = deepcopy(policy)
    expected.base_segment.table_rating = new_table
    expected.base_segment.table_cease_date = CHANGE_DATE if new_table == 0 else None
    factor = 1.0 + table_factor * new_table
    for benefit in expected.benefits[:2]:
        benefit.rating_factor = factor

    outcome = calc_engine._apply_policy_change(
        policy, config,
        PolicyChangeEvent(PolicyChangeKind.SUBSTANDARD, CHANGE_DATE, new_table),
        attained_age=46, change_date=CHANGE_DATE, rates=rates, rate_year=7,
        av=10_000.0,
    )

    assert outcome.coverage_changed
    assert [benefit.rating_factor for benefit in policy.benefits] == [
        factor, factor, 1.5, 1.5,
    ]
    assert policy.riders == before.riders
    detail = outcome.guideline_recalc
    for side, basis_policy in [("before", before), ("after", expected)]:
        basis = build_guideline_basis(
            basis_policy, config, rates, attained_age=46, as_of=CHANGE_DATE,
            months_into_year=2,
        )
        solved = solve_guideline_premiums(basis)
        assert detail[f"glp_{side}"] == pytest.approx(solved.glp)
        assert detail[f"gsp_{side}"] == pytest.approx(solved.gsp)
        row = detail["monthly_pv_recalc"][side]["glp"]["glp_rows"][0]
        for label, charge in basis.months[0].benefit_charge_detail.items():
            assert row[label] == pytest.approx(round(charge, 2))
    seven_basis = build_guideline_basis(
        expected, config, rates, attained_age=40, as_of=policy.issue_date,
        active_as_of=CHANGE_DATE,
    )
    assert detail["seven_pay_after"] == pytest.approx(
        solve_guideline_premiums(seven_basis).seven_pay,
    )
    assert detail["glp_before"] != detail["glp_after"]


@pytest.mark.parametrize("guaranteed", [False, True])
@pytest.mark.parametrize("pwot_basis", [1, 2, 3])
def test_projection_drop_and_restore_updates_charges_and_preserves_source(
    monkeypatch, guaranteed, pwot_basis,
):
    policy, config, rates = _fixture(monkeypatch, pwot_basis=pwot_basis)
    original = deepcopy(policy)
    restore_date = date(2026, 5, 15)
    inputs = IllustrationInputSet(policy_changes=[
        PolicyChangeEvent(PolicyChangeKind.SUBSTANDARD, CHANGE_DATE, 0),
        PolicyChangeEvent(PolicyChangeKind.SUBSTANDARD, restore_date, 4),
    ])
    engine = calc_engine.IllustrationEngine()
    options = IllustrationOptions(guaranteed_assumption=guaranteed)
    states = engine.project(
        policy, months=5, future_inputs=inputs, options=options,
        rates_override=rates, bonus_override=BonusConfig(),
    )
    assert len(states) == 6
    for state in states:
        table = 2 if state.date < CHANGE_DATE else (0 if state.date < restore_date else 4)
        factor = 1.0 + config.table_rating_factor * table
        target_based = pwot_basis in (2, 3)
        assert state.benefit_rates["39"] == pytest.approx(0.02 * factor)
        # Target-based PWoT (basis 2/3) carries no table factor (E13).
        waiver_factor = 1.0 if target_based else factor
        assert state.benefit_rates["49"] == pytest.approx(0.3 * waiver_factor)
        assert state.benefit_charge_detail["39"] == pytest.approx(2.0 * factor)
        amount = {1: 10.0, 2: 12.0, 3: 15.0}[pwot_basis]
        assert state.benefit_charge_detail["49"] == pytest.approx(amount * 0.3 * waiver_factor)
        assert state.benefit_charge_detail["10"] == 1.5
        assert state.benefit_charge_detail["60"] == 3.0
    assert policy == original
    control = engine.project(
        policy, months=5, options=options,
        rates_override=rates, bonus_override=BonusConfig(),
    )
    assert all(state.benefit_rates["39"] == pytest.approx(0.03) for state in control)
    assert policy == original


def test_no_change_retains_independently_recorded_waiver_factors(monkeypatch):
    policy, config, rates = _fixture(monkeypatch)
    policy.benefits[0].rating_factor = 1.75
    policy.benefits[1].rating_factor = 1.25
    deduction = calculate_deduction(
        policy.account_value, policy, config, rates, rate_year=7,
        attained_age=46, premiums_to_date=0.0, projection_date=policy.valuation_date,
    )
    assert deduction.benefit_rates["39"] == pytest.approx(0.035)
    assert deduction.benefit_rates["49"] == pytest.approx(0.375)
