"""Shadow-account products refuse specified-amount increases; decreases are allowed."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import calc_engine as ce
from suiteview.illustration.core import run_service
from suiteview.illustration.core.calc_engine import (
    IllustrationEngine,
    ShadowFaceIncreaseError,
    validate_shadow_face_changes,
)
from suiteview.illustration.core.run_service import RunFlowError, check_shadow_face_changes
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    PolicyChangeEvent,
    PolicyChangeKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import CoverageSegment, IllustrationPolicyData

WHEN = date(2027, 3, 1)


def _policy(face: float = 100_000.0, **kwargs) -> IllustrationPolicyData:
    return IllustrationPolicyData(
        db_option="A", face_amount=face,
        segments=[CoverageSegment(coverage_phase=1, face_amount=face, units=face / 1000.0)],
        **kwargs)


def _face(value: float, when: date = WHEN) -> PolicyChangeEvent:
    return PolicyChangeEvent(kind=PolicyChangeKind.FACE_AMOUNT, effective_date=when,
                             value=value, metadata={"charge_surrender": False})


def _inputs(*changes) -> IllustrationInputSet:
    return IllustrationInputSet(policy_changes=list(changes))


@pytest.mark.parametrize("shadow", [{"ccv_active": True}, {"ccv_ceased": True}])
def test_increase_on_shadow_product_is_refused(shadow):
    with pytest.raises(ShadowFaceIncreaseError) as exc:
        validate_shadow_face_changes(_policy(**shadow), _inputs(_face(150_000.0)))
    message = str(exc.value)
    assert "not allowed on shadow account products" in message
    assert "03/01/2027" in message and "$150,000.00" in message and "$100,000.00" in message
    assert "Decreases are allowed" in message


def test_decreases_on_shadow_product_are_allowed():
    validate_shadow_face_changes(
        _policy(ccv_active=True),
        _inputs(_face(80_000.0), _face(60_000.0, date(2029, 3, 1)),
                _face(60_000.0, date(2030, 3, 1))))


def test_increase_after_an_earlier_decrease_is_refused():
    changes = _inputs(_face(90_000.0, date(2029, 3, 1)), _face(80_000.0))
    with pytest.raises(ShadowFaceIncreaseError,
                       match=r"\$90,000.00, above the specified amount of \$80,000.00"):
        validate_shadow_face_changes(_policy(ccv_active=True), changes)


def test_increase_on_non_shadow_product_is_allowed():
    validate_shadow_face_changes(_policy(), _inputs(_face(150_000.0)))


def test_face_changes_after_a_db_option_change_are_left_to_the_engine():
    # B to A adds the account value to the face, so the request may still be a decrease.
    dbo = PolicyChangeEvent(kind=PolicyChangeKind.DB_OPTION, effective_date=WHEN, value="A")
    validate_shadow_face_changes(
        _policy(ccv_active=True), _inputs(dbo, _face(105_000.0, date(2028, 3, 1))))


def _apply(policy, new_face):
    outcome = ce._PolicyChangeOutcome()
    change = _face(new_face)
    ce._apply_face_amount_change(policy, PlancodeConfig(sa_basis="OriginalSA"), change, 60, WHEN,
                                 None, 5, policy.total_face, change.metadata, outcome)
    return outcome


def test_engine_refuses_an_increase_when_the_change_is_applied():
    policy = _policy(ccv_active=True)
    with pytest.raises(ShadowFaceIncreaseError):
        _apply(policy, 125_000.0)
    assert policy.total_face == pytest.approx(100_000.0)
    assert len(policy.segments) == 1


def test_engine_applies_a_decrease_on_a_shadow_product():
    policy = _policy(ccv_active=True)
    _apply(policy, 75_000.0)
    assert policy.total_face == pytest.approx(75_000.0)


def test_project_refuses_before_running():
    with pytest.raises(ShadowFaceIncreaseError):
        IllustrationEngine().project(_policy(ccv_active=True), months=1,
                                     future_inputs=_inputs(_face(150_000.0)))


def _run_scenario(policy, inputs):
    return SimpleNamespace(
        scenario=SimpleNamespace(projectable_policy=policy, future_inputs=inputs))


def test_run_flow_shows_a_user_facing_error():
    with pytest.raises(RunFlowError) as exc:
        check_shadow_face_changes(
            _run_scenario(_policy(ccv_active=True), _inputs(_face(150_000.0))))
    assert exc.value.title == "Specified Amount Increase Not Allowed"
    assert "not allowed on shadow account products" in exc.value.message
    check_shadow_face_changes(_run_scenario(_policy(ccv_active=True), _inputs(_face(50_000.0))))


def test_execute_run_refuses_before_any_projection(monkeypatch):
    policy = _policy(ccv_active=True)
    scenario = _run_scenario(policy, _inputs(_face(150_000.0)))
    monkeypatch.setattr(run_service, "prepare_policy_data",
                        lambda *_a: SimpleNamespace(policy_data=policy))
    monkeypatch.setattr(run_service, "check_run_gates", lambda *_a: None)
    monkeypatch.setattr(run_service, "build_run_scenario", lambda *_a: scenario)

    def no_engine():
        raise AssertionError("no projection may run for a refused face increase")

    services = run_service.EngineServices(engine_factory=no_engine)
    with pytest.raises(RunFlowError, match="not allowed on shadow account products"):
        run_service.execute_run(SimpleNamespace(), services)
