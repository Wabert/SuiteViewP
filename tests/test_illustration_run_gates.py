"""Soft-launch run gates (run_gates + run_service): scope rules on every run.

The window disables Run at load time; these tests pin the same rules inside
``execute_run`` (so saved/imported cases are gated too) and in Compare.
"""
from types import SimpleNamespace

import pytest

from suiteview.illustration.core import compare_runner
from suiteview.illustration.core.business_mode import BUSINESS_MODE_ENV
from suiteview.illustration.core.run_gates import (
    GATE_TITLE,
    PHASE1_ALLOWED_PREMIUM_PAY_STATUSES,
    policy_gate,
    status_refusal,
)
from suiteview.illustration.core.run_service import (
    EngineServices,
    PolicyBasis,
    PreparedPolicyData,
    RunControls,
    RunFlowError,
    RunRequest,
    SolveRequestSet,
    check_run_gates,
    execute_run,
)
from suiteview.illustration.models.input_set import (
    IllustrationInputSet,
    IllustrationOptions,
    InforceOverrideSet,
    RollbackOverrideSet,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

PHASE1 = "1U143900"
ISWL = "80110429"


def _policy(plancode=PHASE1, status="22", suspense="0", **extra) -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="UL000001", plancode=plancode,
        premium_pay_status_code=status, suspense_code=suspense, **extra)


def _request(policy, *, overrides=None, run_from_issue=False, abr=False, rollback=None):
    return RunRequest(
        basis=PolicyBasis("UL000001", policy_data=policy),
        inputs=IllustrationInputSet(),
        controls=RunControls(options=IllustrationOptions(), projection_months=12,
                             duration_label="for 1 years", stop_on_lapse=True,
                             run_from_issue=run_from_issue, abr_quote=abr),
        solves=SolveRequestSet(),
        inforce_overrides=overrides,
        rollback_overrides=rollback,
    )


def _services(business: bool) -> EngineServices:
    def project(*_args, **_kwargs):
        raise AssertionError("a refused run must not reach the engine")

    return EngineServices(project=project, business_mode=lambda: business)


# ── status rules (M3) ────────────────────────────────────────────────


def test_allowed_statuses_are_the_phase1_set():
    assert PHASE1_ALLOWED_PREMIUM_PAY_STATUSES == {"22", "32", "33", "34"}
    for status in PHASE1_ALLOWED_PREMIUM_PAY_STATUSES:
        assert status_refusal(_policy(status=status)) is None


@pytest.mark.parametrize("status, label", [
    ("44", "Extended Term"), ("45", "Reduced Paid-Up"), ("99", "Terminated"),
    ("54", "Lapsing"), ("46", "Fully Paid-Up"), ("21", "Premium Paying (at issue)"),
    ("77", "Unknown"), ("", "Not Recorded"),
])
def test_other_statuses_refused_with_status_and_label(status, label):
    message = status_refusal(_policy(status=status))
    assert message == (f"Policy status {status or '(blank)'} ({label}) is not supported "
                       "for in-force illustration in this release.")


def test_suspended_allowed_death_claim_pending_refused():
    assert status_refusal(_policy(suspense="2")) is None
    assert "Death Claim Pending" in status_refusal(_policy(suspense="3"))


# ── plancode allow-list (M5) ─────────────────────────────────────────


def test_policy_gate_business_blocks_plancode_and_status_together():
    gate = policy_gate(_policy(plancode=ISWL, status="45"), business_mode=True)
    assert gate.blocked
    assert gate.blocks[0].startswith(f"Plancode {ISWL} is not supported")
    assert gate.blocks[1].startswith("Policy status 45 (Reduced Paid-Up)")


def test_policy_gate_developer_never_blocks():
    gate = policy_gate(_policy(plancode=ISWL, status="45"), business_mode=False)
    assert not gate.blocked
    assert len(gate.warnings) == 1 and "developer run allowed" in gate.warnings[0]
    assert policy_gate(_policy(plancode=ISWL), business_mode=False).warnings == ()


# ── run_service (saved / imported cases go through execute_run) ─────


@pytest.mark.parametrize("policy", [_policy(plancode=ISWL), _policy(status="44")])
def test_execute_run_refuses_out_of_scope_policy_for_business(policy):
    with pytest.raises(RunFlowError) as error:
        execute_run(_request(policy), _services(True))
    assert error.value.title == GATE_TITLE
    assert "not supported for in-force illustration" in error.value.message


@pytest.mark.parametrize("kwargs, label", [
    ({"run_from_issue": True}, "New Business - From Issue"),
    ({"abr": True}, "ABR Quote"),
    ({"rollback": RollbackOverrideSet(valuation_date=None)}, "Edit Record"),
])
def test_execute_run_refuses_developer_run_modes_for_business(kwargs, label):
    with pytest.raises(RunFlowError, match=label):
        execute_run(_request(_policy(), **kwargs), _services(True))


def test_developer_out_of_scope_run_proceeds_with_warning():
    gate = check_run_gates(_request(_policy(status="44")),
                           PreparedPolicyData(_policy(status="44")), _services(False))
    assert not gate.blocked
    assert "Policy status 44 (Extended Term)" in gate.warnings[0]


def test_business_in_scope_run_passes_gates():
    gate = check_run_gates(_request(_policy()), PreparedPolicyData(_policy()), _services(True))
    assert gate.blocks == () and gate.warnings == ()


# ── Compare (M3/M5 apply to every scenario) ─────────────────────────


def _spec(policy, overrides=None):
    scenario = SimpleNamespace(
        base_policy=policy, projectable_policy=policy, run_from_issue=False,
        rollback_overrides=None, inforce_overrides=overrides or InforceOverrideSet(),
        future_inputs=IllustrationInputSet())
    return compare_runner.ScenarioSpec(
        label="A", scenario=scenario, months=12, options=IllustrationOptions())


def test_compare_refuses_out_of_scope_scenario_for_business(monkeypatch):
    monkeypatch.setenv(BUSINESS_MODE_ENV, "1")
    with pytest.raises(compare_runner.CompareScenarioError, match="Plancode 80110429"):
        compare_runner.run_scenario(_spec(_policy(plancode=ISWL)), engine=object())


# ── Illustrated-rate cap (M2) ────────────────────────────────────────

from suiteview.illustration.core.run_gates import illustrated_rate_cap, rate_gate  # noqa: E402

IUL = "1U144600"


def _declared(plancode=PHASE1, rate=0.0425):
    return _policy(plancode=plancode, current_interest_rate=rate,
                   current_interest_rate_source="UL_Rates CIRF current scale")


def test_cap_is_the_current_declared_rate_on_declared_rate_ul():
    assert illustrated_rate_cap(_declared()) == pytest.approx(0.0425)
    assert illustrated_rate_cap(_declared(plancode=IUL)) is None
    assert illustrated_rate_cap(_declared(plancode=ISWL)) is None


@pytest.mark.parametrize("rate", [0.0425, 0.04, 0.0, 0.042500004])
def test_rates_at_or_below_the_declared_rate_pass(rate):
    gate = rate_gate(_declared(), InforceOverrideSet(current_interest_rate=rate),
                     business_mode=True)
    assert gate.blocks == () and gate.warnings == ()


def test_business_rate_above_declared_is_blocked():
    gate = rate_gate(_declared(), InforceOverrideSet(current_interest_rate=0.05),
                     business_mode=True)
    assert gate.blocks == (
        "The Illustrated Rate 5.000% is above the current declared rate 4.250%. "
        "Illustrated rates can't exceed the current rate.",)


def test_business_blank_rate_is_refused_not_zero():
    gate = rate_gate(_declared(), InforceOverrideSet(current_interest_rate=None),
                     business_mode=True)
    assert gate.blocked and "can't be blank" in gate.blocks[0]
    assert "4.250%" in gate.blocks[0]


def test_developer_rate_above_declared_is_a_warning():
    gate = rate_gate(_declared(), InforceOverrideSet(current_interest_rate=0.05),
                     business_mode=False)
    assert not gate.blocked
    assert "5.000% is above the current declared rate 4.250%" in gate.warnings[0]
    assert rate_gate(_declared(), InforceOverrideSet(current_interest_rate=None),
                     business_mode=False) == rate_gate(_declared(), None, business_mode=True)


def test_execute_run_caps_saved_and_imported_case_rates_for_business():
    request = _request(_declared(), overrides=InforceOverrideSet(current_interest_rate=0.06))
    with pytest.raises(RunFlowError, match="6.000% is above the current declared rate"):
        execute_run(request, _services(True))


def test_abr_quote_developer_run_is_not_rate_capped():
    request = _request(_declared(), overrides=InforceOverrideSet(current_interest_rate=0.08),
                       abr=True)
    gate = check_run_gates(request, PreparedPolicyData(_declared()), _services(False))
    assert gate.warnings == ()


def test_compare_caps_scenario_rate_for_business(monkeypatch):
    monkeypatch.setenv(BUSINESS_MODE_ENV, "1")
    spec = _spec(_declared(), InforceOverrideSet(current_interest_rate=0.05))
    with pytest.raises(compare_runner.CompareScenarioError, match="above the current declared"):
        compare_runner.run_scenario(spec, engine=object())
