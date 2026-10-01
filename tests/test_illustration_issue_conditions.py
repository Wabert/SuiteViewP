from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import rate_loader
from suiteview.illustration.core.scenario_builder import (
    build_illustration_scenario,
    issue_base_segments,
)
from suiteview.illustration.models.input_set import InforceOverrideSet, IssueOverrideSet
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import (
    BenefitInfo,
    CoverageSegment,
    IllustrationPolicyData,
    RiderInfo,
)

ISSUE = date(2010, 5, 15)
LATER = date(2015, 5, 15)


def _policy():
    return IllustrationPolicyData(
        plancode="TEST", issue_date=ISSUE, issue_age=40, attained_age=56,
        valuation_date=date(2026, 5, 15), illustration_date=date(2026, 8, 27),
        rate_class="N", rate_sex="F", face_amount=225_000, units=225,
        account_value=12_345, cost_basis=5_000, accumulated_glp=123,
        accumulated_mtp=234, glp=1_000, gsp=2_000, mtp=10, ctp=20,
        tamra_7pay_level=3_000, tamra_7pay_start_av=4_000,
        tamra_7pay_cash_value=5_000, tamra_7year_lowest_db=6_000,
        tamra_7year_contributions=[100] * 7, is_mec=True,
        fund_values={"SW": 12_000, "IP": 345},
        premium_allocations={"SW": 0.2, "IP": 0.8},
        index_illustration_rates={"IP": 0.06}, current_interest_rate=0.045,
        regular_loan_principal=500, preferred_loan_accrued=10,
        variable_loan_principal=100, premiums_paid_to_date=500,
        premiums_ytd=400, withdrawals_to_date=300,
        shadow_account_value=100, deemed_cash_value=200, swam=50,
        ccv_active=False, ccv_ceased=True, ccv_units=100,
        segments=[
            CoverageSegment(
                coverage_phase=1, issue_date=ISSUE, issue_age=40,
                rate_class="N", rate_sex="F", face_amount=75_000,
                original_face_amount=100_000, units=75, band=4, original_band=4,
                status="T", months_since_terminated=5,
            ),
            CoverageSegment(
                coverage_phase=2, issue_date=ISSUE, issue_age=40,
                face_amount=50_000, original_face_amount=0, units=50,
            ),
            CoverageSegment(
                coverage_phase=3, issue_date=LATER, issue_age=45,
                face_amount=100_000, original_face_amount=100_000, is_cola=True,
            ),
        ],
        riders=[
            RiderInfo(coverage_phase=4, plancode="1U144A00", issue_date=ISSUE,
                      face_amount=100_000, is_active=False, status="T"),
            RiderInfo(coverage_phase=5, plancode="RIDER", issue_date=LATER,
                      face_amount=200_000),
        ],
        benefits=[
            BenefitInfo(coverage_phase=1, benefit_type="A", issue_date=ISSUE,
                        units=50, is_active=False),
            BenefitInfo(coverage_phase=4, benefit_type="W", benefit_subtype="1",
                        issue_date=ISSUE, is_active=False),
            BenefitInfo(coverage_phase=1, benefit_type="W", benefit_subtype="2",
                        issue_date=LATER),
        ],
    )


def test_issue_selection_resets_state_and_preserves_recorded_demographics_and_assumptions():
    base = _policy()
    untouched = deepcopy(base)
    assert [s.coverage_phase for s in issue_base_segments(base)] == [1, 2]
    projected = build_illustration_scenario(base, run_from_issue=True).projectable_policy
    assert base == untouched
    assert projected.face_amount == 150_000
    assert projected.units == 150
    assert [s.face_amount for s in projected.segments] == [100_000, 50_000]
    assert [r.coverage_phase for r in projected.riders] == [4]
    assert len(projected.benefits) == 2
    assert all(s.status == "A" and s.months_since_terminated == 0 for s in projected.segments)
    assert projected.riders[0].is_active and projected.riders[0].status == "A"
    assert all(b.is_active for b in projected.benefits)
    assert projected.ccv_active and not projected.ccv_ceased and projected.ccv_units == 50
    assert projected.illustration_date == untouched.illustration_date
    assert projected.issue_date == ISSUE
    assert projected.issue_age == projected.attained_age == 40
    assert projected.rate_class == "N" and projected.rate_sex == "F"
    assert projected.fund_values == {"SW": 0, "IP": 0}
    assert projected.premium_allocations == untouched.premium_allocations
    assert projected.index_illustration_rates == untouched.index_illustration_rates
    assert projected.current_interest_rate == 0.045
    assert projected.tamra_7year_contributions == [0] * 7
    assert not projected.is_mec
    for name in (
        "account_value", "cost_basis", "glp", "gsp", "mtp", "ctp",
        "accumulated_glp", "accumulated_mtp", "tamra_7pay_level",
        "tamra_7pay_start_av", "tamra_7pay_cash_value", "tamra_7year_lowest_db",
        "regular_loan_principal", "preferred_loan_accrued", "variable_loan_principal",
        "premiums_paid_to_date", "premiums_ytd", "withdrawals_to_date",
        "shadow_account_value", "deemed_cash_value", "swam",
    ):
        assert getattr(projected, name) == 0, name


def test_issue_overrides_are_separate_from_inforce_overrides():
    base = _policy()
    issue = IssueOverrideSet(face_amount=90_000, db_option="B", excluded_rider_phases=[4])
    inforce = InforceOverrideSet(
        face_amount=500_000, db_option="C", rate_class="S",
        account_value=900, current_interest_rate=0.055,
    )
    scenario = build_illustration_scenario(
        base, inforce, run_from_issue=True, issue_overrides=issue,
    )
    policy = scenario.projectable_policy
    assert scenario.issue_overrides == issue
    assert [s.face_amount for s in policy.segments] == [60_000, 30_000]
    assert [s.original_face_amount for s in policy.segments] == [60_000, 30_000]
    assert policy.units == 90
    assert policy.db_option == "B" and policy.rate_class == "N"
    assert policy.account_value == 0 and policy.current_interest_rate == 0.055
    assert policy.riders == []
    assert [b.benefit_type for b in policy.benefits] == ["A"]
    inforce_policy = build_illustration_scenario(
        base, inforce, issue_overrides=issue,
    ).projectable_policy
    assert inforce_policy.face_amount == 500_000
    assert inforce_policy.db_option == "C" and inforce_policy.account_value == 900
    assert len(inforce_policy.segments) == 3 and len(inforce_policy.riders) == 2


def test_benefit_removal_disables_shadow_account():
    policy = build_illustration_scenario(
        _policy(), run_from_issue=True,
        issue_overrides=IssueOverrideSet(excluded_benefit_keys=[(1, "A", "")]),
    ).projectable_policy
    assert not policy.ccv_active and not policy.ccv_ceased and policy.ccv_units == 0


@pytest.mark.parametrize("shadow_benefit", [None, LATER])
def test_ui_candidate_is_database_free_and_has_only_retained_shadow_state(monkeypatch, shadow_benefit):
    from suiteview.core.rates import Rates

    def forbidden_lookup(*args, **kwargs):
        pytest.fail("Building an issue editor candidate must not access rates.")

    monkeypatch.setattr(Rates, "__init__", forbidden_lookup)
    base = _policy()
    base.ccv_active = True
    base.ccv_ceased = True
    base.benefits = (
        [BenefitInfo(coverage_phase=1, benefit_type="A", issue_date=shadow_benefit)]
        if shadow_benefit else []
    )
    candidate = build_illustration_scenario(base, run_from_issue=True).projectable_policy
    assert not candidate.has_shadow_account
    assert not candidate.ccv_ceased
    assert candidate.ccv_units == 0
    assert candidate.fund_values == {"SW": 0, "IP": 0}
    assert candidate.premium_allocations == {"SW": 0.2, "IP": 0.8}
    assert base.ccv_active and base.fund_values["SW"] == 12_000


@pytest.mark.parametrize("face", [0, -1, float("nan"), float("inf")])
def test_invalid_issue_face_is_rejected(face):
    with pytest.raises(ValueError, match="face"):
        build_illustration_scenario(
            _policy(), run_from_issue=True, issue_overrides=IssueOverrideSet(face_amount=face),
        )


@pytest.mark.parametrize("overrides", [
    IssueOverrideSet(db_option="D"),
    IssueOverrideSet(excluded_rider_phases=[999]),
    IssueOverrideSet(excluded_benefit_keys=[(99, "W", "")]),
])
def test_invalid_issue_conditions_are_rejected(overrides):
    with pytest.raises(ValueError):
        build_illustration_scenario(_policy(), run_from_issue=True, issue_overrides=overrides)


def test_missing_original_history_is_not_invented():
    policy = _policy()
    policy.segments = [policy.segments[-1]]
    with pytest.raises(ValueError, match="original issue-date"):
        issue_base_segments(policy)
    policy.issue_date = None
    with pytest.raises(ValueError, match="issue date"):
        build_illustration_scenario(policy, run_from_issue=True)


@pytest.mark.parametrize("coi_scale,expense_scale", [(1, 1), (0, 0), (0, 1)])
def test_issue_band_and_scales_resolve_at_rate_boundary(monkeypatch, coi_scale, expense_scale):
    calls = []

    class FakeRates:
        def get_band(self, plancode, face, issue_date=None, **_kwargs):
            calls.append(("band", plancode, face, issue_date))
            return 3 if face >= 250_000 else 1

        def get_rates(self, kind, plancode, *args, **kwargs):
            calls.append((kind, plancode, kwargs.get("band"), kwargs.get("scale")))
            return [None, 0.1]

        def get_mtp(self, *args, **_kwargs):
            calls.append(("MTP", args))
            return 1

        def get_ctp(self, *args, **_kwargs):
            return 2

    monkeypatch.setattr(rate_loader, "ULRates", lambda *_args, **_kwargs: FakeRates())
    policy = build_illustration_scenario(_policy(), run_from_issue=True).projectable_policy
    config = PlancodeConfig(plancode="TEST", poav_table="0")
    # The issue scenario restores the shadow account; this plain test plancode
    # has no shadow configuration, which must fail loud (E10/R05).
    assert policy.has_shadow_account
    with pytest.raises(rate_loader.RateLookupError, match="no shadow-account configuration"):
        rate_loader.load_rates(policy, config, coi_scale, expense_scale)
    policy.ccv_active = False
    result = rate_loader.load_rates(policy, config, coi_scale, expense_scale)
    assert policy.band == 3
    assert all(s.band == s.original_band == 3 for s in policy.segments)
    assert policy.riders[0].band == 3
    assert ("band", "TEST", 250_000, ISSUE) in calls
    assert ("COI", "TEST", 3, coi_scale) in calls
    assert ("EPU", "TEST", 3, expense_scale) in calls
    assert ("MFEE", "TEST", 3, expense_scale) in calls
    assert ("TPP", "TEST", 3, expense_scale) in calls
    assert ("COI", "1U144A00", 3, 1) in calls
    assert ("BENCOI", "TEST", 3, 1) in calls
    assert result.coi_scale == coi_scale and result.expense_scale == expense_scale
    assert any(c[0] == "MTP" and c[1][-1] == 3 for c in calls)
    calls.clear()
    rate_loader.load_rates(policy, config, coi_scale, expense_scale)
    assert not any(c[0] == "band" for c in calls)


def test_excluded_base_banding_rider_does_not_inflate_edited_issue_band():
    policy = build_illustration_scenario(
        _policy(), run_from_issue=True,
        issue_overrides=IssueOverrideSet(face_amount=60_000, excluded_rider_phases=[4]),
    ).projectable_policy

    class FakeRates:
        def get_band(self, plancode, face, issue_date=None, **_kwargs):
            assert face == 60_000 and issue_date == ISSUE
            return 1

    rate_loader.initialize_issue_bands(policy, FakeRates())
    assert policy.band == 1
    assert all(s.band == s.original_band == 1 for s in policy.segments)


def test_engine_recalculates_targets_and_guidelines_on_edited_issue_basis(monkeypatch):
    from suiteview.illustration.core import calc_engine
    from suiteview.illustration.core.bonus_rates import BonusConfig
    from suiteview.illustration.core.target_premium import TargetPremiumResult

    policy = build_illustration_scenario(
        _policy(), run_from_issue=True,
        issue_overrides=IssueOverrideSet(
            face_amount=90_000, db_option="B", excluded_rider_phases=[4],
            excluded_benefit_keys=[(1, "A", "")],
        ),
    ).projectable_policy
    seen = []

    def targets(basis, config, **kwargs):
        assert basis.face_amount == 90_000 and basis.db_option == "B"
        assert basis.total_face == 90_000
        assert basis.riders == [] and basis.benefits == []
        seen.append("targets")
        return TargetPremiumResult(mtp_annual=120, ctp_annual=240)

    def guidelines(basis, config, age, solve_date, options, **kwargs):
        assert basis.face_amount == 90_000 and basis.db_option == "B"
        assert age == 40 and solve_date == ISSUE
        assert kwargs["starting_av"] == 0 and kwargs["active_as_of"] == ISSUE
        seen.append("guidelines")
        return SimpleNamespace(glp=1_200, gsp=2_400, seven_pay=3_600)

    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _: PlancodeConfig(plancode="TEST", epu_code="0", mfee="0", corridor_code=None),
    )
    monkeypatch.setattr(calc_engine, "compute_target_premiums", targets)
    monkeypatch.setattr(calc_engine, "_solve_guideline_state", guidelines)
    states = calc_engine.IllustrationEngine().project(
        policy, months=1, stop_on_lapse=False,
        rates_override=rate_loader.IllustrationRates(), bonus_override=BonusConfig(),
    )
    assert seen[:2] == ["targets", "guidelines"]
    assert policy.mtp == 0 and policy.ctp == 0
    assert policy.glp == 0 and policy.gsp == 0 and policy.tamra_7pay_level == 0
    assert states[1].monthly_mtp == 10 and states[1].ctp == 240
    assert states[1].glp == 1_200 and states[1].gsp == 2_400
    assert states[1].tamra_7pay_level == 3_600
    assert states[1].date == ISSUE and states[1].duration == 1


@pytest.mark.parametrize("issue_date", [date(2010, 3, 31), date(2012, 2, 29)])
@pytest.mark.parametrize("cyberlife_timing", [False, True])
def test_month_end_issue_projection_remains_anchored_to_original_issue_date(
    monkeypatch, issue_date, cyberlife_timing,
):
    from dateutil.relativedelta import relativedelta

    from suiteview.illustration.core import calc_engine
    from suiteview.illustration.core.bonus_rates import BonusConfig
    from suiteview.illustration.core.target_premium import TargetPremiumResult
    from suiteview.illustration.models.input_set import (
        DatedTransaction,
        IllustrationInputSet,
        TransactionKind,
    )

    base = IllustrationPolicyData(
        issue_date=issue_date, issue_age=40, plancode="TEST",
        segments=[CoverageSegment(
            issue_date=issue_date, issue_age=40, face_amount=100_000,
            original_face_amount=100_000, units=100,
        )],
    )
    policy = build_illustration_scenario(base, run_from_issue=True).projectable_policy
    monkeypatch.setattr(
        calc_engine, "load_plancode",
        lambda _: PlancodeConfig(plancode="TEST", epu_code="0", mfee="0", corridor_code=None),
    )
    monkeypatch.setattr(
        calc_engine, "compute_target_premiums",
        lambda *args, **kwargs: TargetPremiumResult(),
    )
    monkeypatch.setattr(
        calc_engine, "_solve_guideline_state",
        lambda *args, **kwargs: SimpleNamespace(glp=12_000, gsp=24_000, seven_pay=36_000),
    )
    timing = (
        calc_engine.ProjectionTiming.CYBERLIFE_MONTHLIVERSARY if cyberlife_timing
        else calc_engine.ProjectionTiming.ILLUSTRATION
    )
    inputs = IllustrationInputSet(dated_transactions=[
        DatedTransaction(
            TransactionKind.PREMIUM, issue_date + relativedelta(months=i), 100 + i,
        )
        for i in range(14)
    ])
    states = calc_engine.IllustrationEngine().project(
        policy, months=14, timing=timing, future_inputs=inputs, stop_on_lapse=False,
        rates_override=rate_loader.IllustrationRates(), bonus_override=BonusConfig(),
    )
    for duration, state in enumerate(states[1:], 1):
        month_date = issue_date + relativedelta(months=duration - 1)
        assert state.date == month_date
        assert state.duration == duration
        assert state.policy_year == (duration - 1) // 12 + 1
        assert state.policy_month == (duration - 1) % 12 + 1
        assert state.gross_premium == 99 + duration
        assert calc_engine._change_duration(policy, month_date) == duration
