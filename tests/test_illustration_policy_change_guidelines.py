from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.bonus_rates import BonusConfig
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.input_compiler import CompiledMonthInputs
from suiteview.illustration.core.monthly_guideline import GuidelineSolveResult
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.withdrawal_handler import WithdrawalResult
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import PolicyChangeEvent, PolicyChangeKind
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
    RiderInfo,
)


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


def test_new_increase_segment_preserves_guaranteed_rate_basis(monkeypatch):
    calls = []

    class FakeRates:
        def get_rates(
            self, kind, plancode, issue_age, sex, rateclass, *, scale, band
        ):
            calls.append((kind, scale, band))
            return [None, float(scale)]

    monkeypatch.setattr("suiteview.core.rates.Rates", FakeRates)
    segment = CoverageSegment(
        coverage_phase=2,
        issue_age=79,
        rate_sex="F",
        rate_class="N",
        band=2,
    )
    rates = IllustrationRates(coi_scale=0, expense_scale=0)

    calc_engine._load_segment_rates(
        rates, segment, "1U145500", PlancodeConfig(rachet_banding=True)
    )

    assert calls == [
        ("COI", 0, 2),
        ("EPU", 0, 2),
        ("SCR", 1, 2),
        ("COI", 0, 1),
        ("COI", 0, 2),
    ]
    assert rates.segment_coi[2] == [None, 0.0]
    assert rates.segment_epu[2] == [None, 0.0]


def test_new_increase_segment_keeps_current_rate_basis(monkeypatch):
    calls = []

    class FakeRates:
        def get_rates(
            self, kind, plancode, issue_age, sex, rateclass, *, scale, band
        ):
            calls.append((kind, scale))
            return [None, float(scale)]

    monkeypatch.setattr("suiteview.core.rates.Rates", FakeRates)
    segment = CoverageSegment(
        coverage_phase=2,
        issue_age=79,
        rate_sex="F",
        rate_class="N",
        band=2,
    )

    calc_engine._load_segment_rates(
        IllustrationRates(), segment, "1U145500", PlancodeConfig()
    )

    assert calls == [("COI", 1), ("EPU", 1), ("SCR", 1)]


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
    assert solve_calls == [1, 1, 0, 0]


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
    assert solve_calls == [1, 1, 0, 0]


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


@pytest.mark.parametrize(
    ("sa_basis", "expected_psc"),
    [("CurrentSA", 400.0), ("OriginalSA", 0.0)],
)
def test_specified_face_decrease_follows_sa_basis_without_withdrawal_fee(
    monkeypatch, sa_basis, expected_psc,
):
    """A specified (elective) face decrease never incurs the $25 withdrawal fee.

    The fee is a withdrawal charge (RERUN CalcEngine BN — see
    ``withdrawal_handler.compute_withdrawal``). Reducing the specified amount is
    a coverage change: it charges only the decreased units' surrender charge
    (SCR/PSC) only for CurrentSA plans. OriginalSA plans do not assess PSC.
    Neither basis may leak the withdrawal-only $25 fee into this path.
    """
    solve_calls = []
    _patch_policy_change_dependencies(monkeypatch, solve_calls)
    policy = IllustrationPolicyData(
        def_of_life_ins="GPT",
        face_amount=100_000.0,
        glp=1_200.0,
        gsp=2_400.0,
        tamra_7pay_level=72.0,
        segments=[CoverageSegment(coverage_phase=1, face_amount=100_000.0)],
    )

    outcome = calc_engine._apply_policy_change(
        policy,
        PlancodeConfig(withdrawal_fee=25.0, sa_basis=sa_basis),
        PolicyChangeEvent(
            kind=PolicyChangeKind.FACE_AMOUNT,
            effective_date=date(2026, 6, 9),
            value=60_000.0,
        ),
        attained_age=56,
        change_date=date(2026, 6, 9),
        rates=IllustrationRates(
            scr=[None, 10.0],
            segment_scr={1: [None, 10.0]},
        ),
        rate_year=7,
        av=10_000.0,
    )

    assert outcome.coverage_changed
    assert policy.face_amount == 60_000.0
    assert outcome.face_detail["Specified Face Decrease"] == 40_000.0
    assert outcome.av_adjustment == pytest.approx(-expected_psc)
    assert outcome.face_detail["Total PSC Spec Dec"] == pytest.approx(expected_psc)


@pytest.mark.parametrize(
    ("sa_basis", "decrease_charge_allowed", "expected_psc"),
    [
        ("CurrentSA", False, 0.0),
        ("CurrentSA", True, 400.0),
        ("CurrentSA", None, 400.0),
        ("OriginalSA", True, 0.0),
    ],
)
def test_specified_face_decrease_honors_decrease_charge_rule(
    monkeypatch, sa_basis, decrease_charge_allowed, expected_psc,
):
    """TH_NON_TRD_POL.DECR_CHRG_ALLOW = 0 removes the specified-decrease PSC.

    An unset rule keeps the plancode rule; the policy rule never adds a charge
    to a plan that does not assess one.
    """
    _patch_policy_change_dependencies(monkeypatch, [])
    policy = IllustrationPolicyData(
        def_of_life_ins="GPT",
        face_amount=100_000.0,
        glp=1_200.0,
        gsp=2_400.0,
        tamra_7pay_level=72.0,
        decrease_charge_allowed=decrease_charge_allowed,
        segments=[CoverageSegment(coverage_phase=1, face_amount=100_000.0)],
    )

    outcome = calc_engine._apply_policy_change(
        policy,
        PlancodeConfig(sa_basis=sa_basis),
        PolicyChangeEvent(
            kind=PolicyChangeKind.FACE_AMOUNT,
            effective_date=date(2026, 6, 9),
            value=60_000.0,
        ),
        attained_age=56,
        change_date=date(2026, 6, 9),
        rates=IllustrationRates(scr=[None, 10.0], segment_scr={1: [None, 10.0]}),
        rate_year=7,
        av=10_000.0,
    )

    assert policy.face_amount == 60_000.0
    assert outcome.face_detail["Specified Face Decrease"] == 40_000.0
    assert outcome.av_adjustment == pytest.approx(-expected_psc)
    assert outcome.face_detail["Total PSC Spec Dec"] == pytest.approx(expected_psc)


def test_increase_segment_gets_true_segment_maturity_date(monkeypatch):
    class FakeRates:
        def get_band(self, *_args, **_kwargs):
            return 2

        def get_rates(
            self, kind, plancode, issue_age, sex, rateclass, *, scale, band
        ):
            return [None, float(scale)]

    monkeypatch.setattr("suiteview.core.rates.Rates", FakeRates)
    policy = IllustrationPolicyData(
        issue_date=date(2006, 8, 13),
        issue_age=55,
        maturity_age=95,
        insured_birth_date=date(1951, 6, 1),
        segments=[
            CoverageSegment(
                coverage_phase=1,
                is_base=True,
                issue_date=date(2006, 8, 13),
                issue_age=55,
                rate_sex="M",
                rate_class="N",
                face_amount=100_000.0,
                units=100.0,
                band=2,
                vpu=1000.0,
            )
        ],
    )

    calc_engine._append_face_increase_segment(
        policy,
        IllustrationRates(),
        50_000.0,
        attained_age=75,
        change_date=date(2026, 8, 13),
        config=PlancodeConfig(),
    )

    increase = policy.segments[-1]
    # Issue age is the insured's true age on the increase date (bumped off the
    # policy anniversary); maturity is measured from THAT age.
    assert increase.issue_age == 75
    assert increase.maturity_date == date(2046, 8, 13)


def test_rate_class_change_applies_to_all_base_segments(monkeypatch):
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_a, **_k: None)
    monkeypatch.setattr(calc_engine, "_load_segment_rates", lambda *_a, **_k: None)
    monkeypatch.setattr(calc_engine, "_reband_benefits", lambda *_a, **_k: None)
    monkeypatch.setattr(
        calc_engine,
        "_solve_guideline_state",
        lambda *_a, **_k: GuidelineSolveResult(glp=0.0, gsp=0.0, seven_pay=0.0),
    )
    monkeypatch.setattr(
        calc_engine,
        "compute_target_premiums",
        lambda *_a, **_k: SimpleNamespace(mtp_annual=120.0, ctp_annual=240.0),
    )
    policy = IllustrationPolicyData(
        rate_class="N",
        segments=[
            CoverageSegment(coverage_phase=1, is_base=True, rate_class="N"),
            CoverageSegment(coverage_phase=2, is_base=True, rate_class="N"),
        ],
    )

    outcome = calc_engine._apply_policy_change(
        policy,
        PlancodeConfig(),
        PolicyChangeEvent(PolicyChangeKind.RATE_CLASS, date(2028, 1, 1), "S"),
        attained_age=60,
        change_date=date(2028, 1, 1),
        rates=IllustrationRates(),
        rate_year=3,
        av=0.0,
        defer_guideline_recalc=True,
    )

    assert outcome.coverage_changed
    assert policy.rate_class == "S"
    assert [seg.rate_class for seg in policy.segments] == ["S", "S"]


def test_same_month_changes_are_compiled_in_policy_pipeline_order():
    policy = IllustrationPolicyData(issue_date=date(2026, 1, 1))
    when = date(2026, 2, 1)
    changes = [
        PolicyChangeEvent(PolicyChangeKind.RIDER_DROP, when, 0.0),
        PolicyChangeEvent(PolicyChangeKind.SUBSTANDARD, when, 2),
        PolicyChangeEvent(PolicyChangeKind.FACE_AMOUNT, when, 40_000.0),
        PolicyChangeEvent(PolicyChangeKind.DB_OPTION, when, "B"),
        PolicyChangeEvent(PolicyChangeKind.RATE_CLASS, when, "N"),
    ]

    compiled = calc_engine._compile_policy_changes(policy, changes)

    assert [change.kind for change in compiled[2]] == [
        PolicyChangeKind.DB_OPTION,
        PolicyChangeKind.FACE_AMOUNT,
        PolicyChangeKind.RATE_CLASS,
        PolicyChangeKind.SUBSTANDARD,
        PolicyChangeKind.RIDER_DROP,
    ]


def test_same_month_withdrawal_and_changes_use_one_complete_guideline_recalc(monkeypatch):
    solve_bases = []
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_args: None)
    monkeypatch.setattr(calc_engine, "_reband_segment", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calc_engine, "_reband_benefits", lambda *_args: None)
    monkeypatch.setattr(calc_engine, "_safe_guideline_pv_recalc_detail", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(calc_engine, "_safe_seven_pay_pv_detail", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        calc_engine, "build_target_detail_snapshots", lambda *_args, **_kwargs: ({}, {}))
    monkeypatch.setattr(
        calc_engine,
        "compute_target_premiums",
        lambda *_args, **_kwargs: SimpleNamespace(mtp_annual=120.0, ctp_annual=240.0),
    )
    monkeypatch.setattr(
        calc_engine,
        "compute_withdrawal",
        lambda *_args, **_kwargs: WithdrawalResult(
            input_withdrawal=1_000.0,
            applied_net_withdrawal=1_000.0,
            cost_basis_before_wd=20_000.0,
            cost_basis_after_wd=19_000.0,
            withdrawals_to_date=1_000.0,
            withdrawals_ytd=1_000.0,
            gross_withdrawal=1_000.0,
            av_post_withdrawal=49_000.0,
            face_decrease=1_000.0,
        ),
    )

    def fake_solve(policy, _config, _attained_age, _change_date, _options, **_kwargs):
        active_rider = policy.riders[0].is_active
        table_rating = policy.base_segment.table_rating
        solve_bases.append((policy.total_face, table_rating, active_rider))
        return GuidelineSolveResult(
            glp=policy.total_face / 100.0 + table_rating * 10.0 + active_rider * 5.0,
            gsp=policy.total_face / 50.0 + table_rating * 20.0 + active_rider * 10.0,
            seven_pay=policy.total_face / 200.0,
        )

    monkeypatch.setattr(calc_engine, "_solve_guideline_state", fake_solve)
    policy = IllustrationPolicyData(
        plancode="TEST",
        def_of_life_ins="GPT",
        issue_date=date(2026, 1, 1),
        valuation_date=date(2026, 1, 1),
        issue_age=40,
        attained_age=40,
        maturity_age=121,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=50_000.0,
        glp=1_200.0,
        gsp=2_400.0,
        tamra_7pay_level=600.0,
        segments=[
            CoverageSegment(
                coverage_phase=1,
                issue_date=date(2026, 1, 1),
                face_amount=100_000.0,
                units=100.0,
                vpu=1_000.0,
            )
        ],
        riders=[RiderInfo(coverage_phase=2, face_amount=10_000.0, is_active=True)],
    )
    state = MonthlyState(
        date=date(2026, 1, 1),
        policy_year=1,
        policy_month=1,
        duration=1,
        attained_age=40,
        av_end_of_month=50_000.0,
        cost_basis=20_000.0,
        cost_basis_after_exception=20_000.0,
    )
    changes = [
        PolicyChangeEvent(
            PolicyChangeKind.FACE_AMOUNT, date(2026, 2, 1), 40_000.0),
        PolicyChangeEvent(
            PolicyChangeKind.SUBSTANDARD, date(2026, 2, 1), 2),
        PolicyChangeEvent(
            PolicyChangeKind.RIDER_DROP,
            date(2026, 2, 1),
            0.0,
            metadata={"target": "cov:2"},
        ),
    ]

    result = calc_engine.run_month(
        calc_engine.MonthContext(
            state=state,
            policy=policy,
            config=PlancodeConfig(
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
            ),
            rates=IllustrationRates(),
            bonus=BonusConfig(),
            month_inputs=CompiledMonthInputs(withdrawal=1_000.0),
            options=calc_engine.IllustrationOptions(),
            policy_changes=changes,
        ),
        calc_engine.ILLUSTRATION_TIMING,
    )

    assert solve_bases == [
        (100_000.0, 0, True),
        (40_000.0, 2, False),
        (40_000.0, 2, False),
    ]
    assert result.guideline_recalc["change_kind"] == "Combined Policy Changes"
    assert result.guideline_recalc["glp_before"] == 1_005.0
    assert result.guideline_recalc["glp_after"] == 420.0
    assert policy.glp == 615.0


def test_same_month_withdrawal_and_face_decrease_recalc_reflects_final_face(monkeypatch):
    """Regression for policy 000170001: a net withdrawal and a specified face
    decrease at the same age must produce ONE combined guideline recalc whose
    "after" reflects the FINAL specified face (40,000) — not the intermediate
    face left by the withdrawal's partial reduction (~50,911). The Overview
    (state.glp/gsp) and the TEFRA/TAMRA recalc row must agree."""
    solve_faces = []
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_args: None)
    monkeypatch.setattr(calc_engine, "_reband_segment", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calc_engine, "_reband_benefits", lambda *_args: None)
    monkeypatch.setattr(calc_engine, "_safe_guideline_pv_recalc_detail", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(calc_engine, "_safe_seven_pay_pv_detail", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        calc_engine, "build_target_detail_snapshots", lambda *_args, **_kwargs: ({}, {}))
    monkeypatch.setattr(
        calc_engine,
        "compute_target_premiums",
        lambda *_args, **_kwargs: SimpleNamespace(mtp_annual=120.0, ctp_annual=240.0),
    )
    # Withdrawal reduces the specified amount by 1,025 (51,936 -> 50,911), the
    # partial-face figure the user saw wrongly reflected in the recalc.
    monkeypatch.setattr(
        calc_engine,
        "compute_withdrawal",
        lambda *_args, **_kwargs: WithdrawalResult(
            input_withdrawal=1_000.0,
            applied_net_withdrawal=1_000.0,
            cost_basis_before_wd=20_000.0,
            cost_basis_after_wd=19_000.0,
            withdrawals_to_date=1_000.0,
            withdrawals_ytd=1_000.0,
            gross_withdrawal=1_025.0,
            av_post_withdrawal=49_000.0,
            face_decrease=1_025.0,
        ),
    )

    def fake_solve(policy, _config, _attained_age, _change_date, _options, **_kwargs):
        solve_faces.append(policy.total_face)
        return GuidelineSolveResult(
            glp=policy.total_face / 100.0,
            gsp=policy.total_face / 50.0,
            seven_pay=policy.total_face / 200.0,
        )

    monkeypatch.setattr(calc_engine, "_solve_guideline_state", fake_solve)
    policy = IllustrationPolicyData(
        plancode="TEST",
        def_of_life_ins="GPT",
        issue_date=date(2026, 1, 1),
        valuation_date=date(2026, 1, 1),
        issue_age=40,
        attained_age=40,
        maturity_age=121,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=51_936.0,
        units=51.936,
        db_option="A",
        account_value=50_000.0,
        glp=1_200.0,
        gsp=2_400.0,
        tamra_7pay_level=600.0,
        segments=[
            CoverageSegment(
                coverage_phase=1,
                issue_date=date(2026, 1, 1),
                face_amount=51_936.0,
                units=51.936,
                vpu=1_000.0,
            )
        ],
    )
    state = MonthlyState(
        date=date(2026, 1, 1),
        policy_year=1,
        policy_month=1,
        duration=1,
        attained_age=40,
        av_end_of_month=50_000.0,
        cost_basis=20_000.0,
        cost_basis_after_exception=20_000.0,
    )
    changes = [
        PolicyChangeEvent(PolicyChangeKind.FACE_AMOUNT, date(2026, 2, 1), 40_000.0),
    ]

    result = calc_engine.run_month(
        calc_engine.MonthContext(
            state=state,
            policy=policy,
            config=PlancodeConfig(
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
            ),
            rates=IllustrationRates(),
            bonus=BonusConfig(),
            month_inputs=CompiledMonthInputs(withdrawal=1_000.0),
            options=calc_engine.IllustrationOptions(),
            policy_changes=changes,
        ),
        calc_engine.ILLUSTRATION_TIMING,
    )

    # Exactly one combined recalc, from the pre-withdrawal face (51,936) to the
    # final specified face (40,000) — never the intermediate 50,911.
    assert result.guideline_recalc["change_kind"] == "Combined Policy Changes"
    assert result.guideline_recalc["glp_before"] == 519.36
    assert result.guideline_recalc["glp_after"] == 400.0
    assert result.guideline_recalc["gsp_after"] == 800.0
    # The recalc's "after" solve must use the final 40,000 face, never the
    # intermediate 50,911 face the withdrawal alone would have left.
    assert 40_000.0 in solve_faces
    assert 50_911.0 not in solve_faces
    # The applied (Overview) premiums come from that same final-state recalc.
    assert result.guideline_recalc["glp_new"] == policy.glp
    assert result.guideline_recalc["gsp_new"] == policy.gsp


def _patch_dbo_a_withdrawal_recalc(monkeypatch, solve_faces):
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_args: None)
    monkeypatch.setattr(calc_engine, "_reband_segment", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calc_engine, "_reband_benefits", lambda *_args: None)
    monkeypatch.setattr(calc_engine, "_safe_guideline_pv_recalc_detail", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(calc_engine, "_safe_seven_pay_pv_detail", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        calc_engine, "build_target_detail_snapshots", lambda *_args, **_kwargs: ({}, {}))
    monkeypatch.setattr(
        calc_engine,
        "compute_target_premiums",
        lambda *_args, **_kwargs: SimpleNamespace(mtp_annual=120.0, ctp_annual=240.0),
    )
    monkeypatch.setattr(
        calc_engine,
        "compute_withdrawal",
        lambda *_args, **_kwargs: WithdrawalResult(
            input_withdrawal=1_000.0,
            applied_net_withdrawal=1_000.0,
            cost_basis_before_wd=20_000.0,
            cost_basis_after_wd=19_000.0,
            withdrawals_to_date=1_000.0,
            withdrawals_ytd=1_000.0,
            gross_withdrawal=1_000.0,
            av_post_withdrawal=49_000.0,
            face_decrease=10_000.0,
        ),
    )

    def fake_solve(policy, _config, _attained_age, _change_date, _options, **_kwargs):
        solve_faces.append(policy.total_face)
        return GuidelineSolveResult(
            glp=policy.total_face / 100.0 + 200.0,
            gsp=policy.total_face / 50.0 + 400.0,
            seven_pay=policy.total_face / 200.0,
        )

    monkeypatch.setattr(calc_engine, "_solve_guideline_state", fake_solve)


def _dbo_a_policy_for_withdrawal_recalc() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        plancode="TEST",
        def_of_life_ins="GPT",
        issue_date=date(2026, 1, 1),
        valuation_date=date(2026, 1, 1),
        issue_age=40,
        attained_age=40,
        maturity_age=121,
        policy_year=1,
        policy_month=1,
        duration=1,
        face_amount=100_000.0,
        units=100.0,
        db_option="A",
        account_value=50_000.0,
        glp=1_200.0,
        gsp=2_400.0,
        tamra_7pay_level=600.0,
        segments=[
            CoverageSegment(
                coverage_phase=1,
                issue_date=date(2026, 1, 1),
                face_amount=100_000.0,
                units=100.0,
                vpu=1_000.0,
            )
        ],
    )


def _dbo_a_withdrawal_context(policy, *, changes=None):
    state = MonthlyState(
        date=date(2026, 1, 1),
        policy_year=1,
        policy_month=1,
        duration=1,
        attained_age=40,
        av_end_of_month=50_000.0,
        cost_basis=20_000.0,
        cost_basis_after_exception=20_000.0,
    )
    return calc_engine.MonthContext(
        state=state,
        policy=policy,
        config=PlancodeConfig(
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
        ),
        rates=IllustrationRates(),
        bonus=BonusConfig(),
        month_inputs=CompiledMonthInputs(withdrawal=1_000.0),
        options=calc_engine.IllustrationOptions(),
        policy_changes=changes or [],
    )


def test_dbo_a_withdrawal_without_policy_changes_does_not_reapply_guideline_delta(monkeypatch):
    solve_faces = []
    _patch_dbo_a_withdrawal_recalc(monkeypatch, solve_faces)
    policy = _dbo_a_policy_for_withdrawal_recalc()

    result = calc_engine.run_month(
        _dbo_a_withdrawal_context(policy),
        calc_engine.ILLUSTRATION_TIMING,
    )

    assert result.guideline_recalc["glp_before"] == 1_200.0
    assert result.guideline_recalc["glp_after"] == 1_100.0
    assert policy.glp == pytest.approx(1_099.92)
    assert policy.gsp == pytest.approx(2_199.96)


def test_dbo_a_withdrawal_with_policy_changes_keeps_single_combined_guideline_recalc(monkeypatch):
    solve_faces = []
    _patch_dbo_a_withdrawal_recalc(monkeypatch, solve_faces)
    policy = _dbo_a_policy_for_withdrawal_recalc()

    result = calc_engine.run_month(
        _dbo_a_withdrawal_context(
            policy,
            changes=[
                PolicyChangeEvent(
                    PolicyChangeKind.FACE_AMOUNT,
                    date(2026, 2, 1),
                    80_000.0,
                )
            ],
        ),
        calc_engine.ILLUSTRATION_TIMING,
    )

    assert result.guideline_recalc["change_kind"] == "Combined Policy Changes"
    assert result.guideline_recalc["glp_before"] == 1_200.0
    assert result.guideline_recalc["glp_after"] == 1_000.0
    assert policy.glp == pytest.approx(999.96)
    assert policy.gsp == pytest.approx(1_999.92)
