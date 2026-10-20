"""A face decrease whose partial surrender charge exceeds the surrender value.

CyberLife will not process a specified decrease (or the face reduction of a
DB option A->B change) when the surrender value at the change cannot cover
its partial surrender charge, even while a no-lapse guarantee keeps the policy
in force (UE204564: face 250,000 -> 100,000, PSC 4,657.50 vs SV -7,597.88).
The engine flags the month; Run Values then builds no report.
"""
from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine
from suiteview.illustration.core.decrease_charge_check import (
    BLOCKED_TITLE,
    PSC_EXCEEDS_SV_KEY,
    SV_BEFORE_CHANGE_KEY,
    record_charge_coverage,
    uncovered_decrease_charge_message,
    uncovered_decrease_charges,
)
from suiteview.illustration.core.loan_handler import LoanState
from suiteview.illustration.core.monthly_guideline import GuidelineSolveResult
from suiteview.illustration.core.rate_loader import IllustrationRates
from suiteview.illustration.core.run_service import (
    EngineServices,
    PolicyBasis,
    RunControls,
    RunRequest,
    SolveRequestSet,
    execute_run,
)
from suiteview.illustration.core.withdrawal_handler import WithdrawalResult
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    PolicyChangeEvent,
    PolicyChangeKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

CHANGE_DATE = date(2026, 10, 19)


# ── detail recording ──────────────────────────────────────────────────


def test_no_partial_surrender_charge_leaves_detail_untouched():
    detail = {"Total PSC Spec Dec": 0.0}
    record_charge_coverage(detail, "Total PSC Spec Dec", account_value=100.0,
                           surrender_charge=5_000.0, policy_debt=0.0)
    assert detail == {"Total PSC Spec Dec": 0.0}


@pytest.mark.parametrize(("account_value", "debt", "exceeds"), [
    (164.62, 0.0, True),        # UE204564: SV deeply negative
    (6_000.0, 0.0, True),       # SV 2,000 < PSC 4,657.50
    (12_500.0, 0.0, False),     # SV 4,737.50 covers it
    (12_500.0, 100.0, True),    # policy debt eats the cover
    (12_420.0, 0.0, False),     # SV exactly equals the PSC
])
def test_charge_coverage_compares_psc_with_surrender_value(account_value, debt, exceeds):
    detail = {"Total PSC Spec Dec": 4_657.50}
    record_charge_coverage(detail, "Total PSC Spec Dec", account_value=account_value,
                           surrender_charge=7_762.50, policy_debt=debt)
    assert detail[SV_BEFORE_CHANGE_KEY] == pytest.approx(account_value - 7_762.50 - debt)
    assert detail[PSC_EXCEEDS_SV_KEY] is exceeds


def _flagged_state(attr: str, psc_key: str, decrease_key: str) -> MonthlyState:
    detail = {decrease_key: 150_000.0, psc_key: 4_657.50}
    record_charge_coverage(detail, psc_key, account_value=164.62,
                           surrender_charge=7_762.50, policy_debt=0.0)
    return MonthlyState(date=CHANGE_DATE, **{attr: detail})


def test_uncovered_charges_found_for_face_and_dbo_changes_and_explained():
    states = [
        MonthlyState(date=date(2026, 9, 19)),
        _flagged_state("face_change_detail", "Total PSC Spec Dec", "Specified Face Decrease"),
        _flagged_state("dbo_change_detail", "Total PSC DBO", "DBO Face Decrease"),
    ]
    findings = uncovered_decrease_charges(states)

    assert [f.description for f in findings] == [
        "specified face decrease", "death benefit option A to B change"]
    message = uncovered_decrease_charge_message(findings[:1])
    assert message.startswith("The illustration report was not generated.")
    assert ("The specified face decrease effective 10/19/2026 reduces the specified amount "
            "by $150,000.00 and assesses a partial surrender charge of $4,657.50, but the "
            "surrender value at that date is only -$7,597.88 (account value $164.62 less "
            "surrender charge $7,762.50 less policy debt $0.00).") in message
    assert "administration system will not process" in message


def test_covered_decrease_is_not_reported():
    detail = {"Specified Face Decrease": 10_000.0, "Total PSC Spec Dec": 300.0}
    record_charge_coverage(detail, "Total PSC Spec Dec", account_value=20_000.0,
                           surrender_charge=7_762.50, policy_debt=0.0)
    assert uncovered_decrease_charges([MonthlyState(face_change_detail=detail)]) == []


# ── engine: the policy-change step records the pre-change surrender value ──


def _patch_policy_change_dependencies(monkeypatch):
    monkeypatch.setattr(calc_engine, "_reload_policy_band_rates", lambda *_args: None)
    monkeypatch.setattr(
        calc_engine, "compute_target_premiums",
        lambda *_args, **_kwargs: SimpleNamespace(mtp_annual=120.0, ctp_annual=240.0))
    monkeypatch.setattr(
        calc_engine, "_solve_guideline_state",
        lambda *_args, **_kwargs: GuidelineSolveResult(glp=60.0, gsp=120.0, seven_pay=36.0))


def _run_change_loop(change, *, av, debt=0.0, db_option="A"):
    policy = IllustrationPolicyData(
        def_of_life_ins="GPT", face_amount=100_000.0, db_option=db_option,
        glp=1_200.0, gsp=2_400.0, tamra_7pay_level=72.0,
        segments=[CoverageSegment(coverage_phase=1, face_amount=100_000.0, units=100.0)],
    )
    ctx = SimpleNamespace(
        policy=policy,
        config=PlancodeConfig(sa_basis="CurrentSA"),
        rates=IllustrationRates(scr=[None, 10.0], segment_scr={1: [None, 10.0]}),
        options=IllustrationOptions(),
        policy_changes=[change],
    )
    work = SimpleNamespace(
        wd=WithdrawalResult(), attained_age=56, month_date=CHANGE_DATE, rate_year=7,
        av=av, cap_loan=LoanState(rg_loan_princ=debt), policy_change_av_reduction=0.0,
        tamra_reset=False, dbo_change_detail={}, face_change_detail={},
    )
    calc_engine._apply_policy_change_loop(ctx, work)
    return work


def test_specified_decrease_psc_above_surrender_value_is_flagged(monkeypatch):
    _patch_policy_change_dependencies(monkeypatch)
    work = _run_change_loop(
        PolicyChangeEvent(PolicyChangeKind.FACE_AMOUNT, CHANGE_DATE, 60_000.0), av=500.0)

    detail = work.face_change_detail
    assert detail["Total PSC Spec Dec"] == pytest.approx(400.0)
    assert detail["SC Before Change"] == pytest.approx(1_000.0)
    assert detail[SV_BEFORE_CHANGE_KEY] == pytest.approx(-500.0)
    assert detail[PSC_EXCEEDS_SV_KEY] is True


def test_specified_decrease_covered_by_surrender_value_is_not_flagged(monkeypatch):
    _patch_policy_change_dependencies(monkeypatch)
    work = _run_change_loop(
        PolicyChangeEvent(PolicyChangeKind.FACE_AMOUNT, CHANGE_DATE, 60_000.0),
        av=1_600.0, debt=150.0)

    assert work.face_change_detail[SV_BEFORE_CHANGE_KEY] == pytest.approx(450.0)
    assert work.face_change_detail[PSC_EXCEEDS_SV_KEY] is False


def test_option_a_to_b_psc_above_surrender_value_is_flagged(monkeypatch):
    _patch_policy_change_dependencies(monkeypatch)
    work = _run_change_loop(
        PolicyChangeEvent(PolicyChangeKind.DB_OPTION, CHANGE_DATE, "B"), av=1_005.0)

    detail = work.dbo_change_detail
    assert detail["DBO Face Decrease"] == pytest.approx(1_005.0)
    assert detail["Total PSC DBO"] == pytest.approx(10.05)
    assert detail[SV_BEFORE_CHANGE_KEY] == pytest.approx(5.0)
    assert detail[PSC_EXCEEDS_SV_KEY] is True


def test_option_a_to_b_psc_covered_by_surrender_value_is_not_flagged(monkeypatch):
    _patch_policy_change_dependencies(monkeypatch)
    work = _run_change_loop(
        PolicyChangeEvent(PolicyChangeKind.DB_OPTION, CHANGE_DATE, "B"), av=1_200.0)

    detail = work.dbo_change_detail
    assert detail["Total PSC DBO"] == pytest.approx(12.0)
    assert detail[SV_BEFORE_CHANGE_KEY] == pytest.approx(200.0)
    assert detail[PSC_EXCEEDS_SV_KEY] is False


def test_face_increase_records_no_charge_coverage(monkeypatch):
    _patch_policy_change_dependencies(monkeypatch)
    monkeypatch.setattr(calc_engine, "_append_face_increase_segment", lambda *_a, **_kw: None)
    work = _run_change_loop(
        PolicyChangeEvent(PolicyChangeKind.FACE_AMOUNT, CHANGE_DATE, 150_000.0), av=10.0)

    assert PSC_EXCEEDS_SV_KEY not in work.face_change_detail


# ── Run Values: no report for an uncovered decrease ───────────────────


def _request(policy) -> RunRequest:
    return RunRequest(
        basis=PolicyBasis("UE204564", policy_data=policy),
        inputs=IllustrationInputSet(),
        controls=RunControls(options=IllustrationOptions(), projection_months=2,
                             duration_label="2 months", stop_on_lapse=True),
        solves=SolveRequestSet(),
    )


def _services(states) -> EngineServices:
    def never(*_args, **_kwargs):
        raise AssertionError("a blocked run builds no guaranteed projection or report")

    return EngineServices(
        scenario_builder=lambda data, **kw: SimpleNamespace(
            projectable_policy=data, future_inputs=kw["future_inputs"]),
        engine_factory=lambda: object(),
        project=lambda *_a, **_kw: SimpleNamespace(states=states),
        guaranteed_runner=never,
        report_builder=never,
        business_mode=lambda: False,
        missing_rates=lambda _policy: (),
    )


def test_execute_run_builds_no_report_when_psc_exceeds_surrender_value():
    policy = IllustrationPolicyData(
        policy_number="UE204564", plancode="1U147600", premium_pay_status_code="22")
    states = [
        MonthlyState(date=date(2026, 9, 19)),
        _flagged_state("face_change_detail", "Total PSC Spec Dec", "Specified Face Decrease"),
    ]

    result = execute_run(_request(policy), _services(states))

    assert result.report.report is None
    assert result.guaranteed is None
    assert result.current == states
    assert result.report.blocked_reason.startswith("The illustration report was not generated.")
    assert "partial surrender charge of $4,657.50" in result.report.blocked_reason
    assert result.status.startswith(BLOCKED_TITLE)
