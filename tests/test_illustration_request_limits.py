"""Reduced withdrawal/loan requests are reported, not silently clipped (should-do 2)."""
from datetime import date

import pytest

from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.core.request_limits import reduced_request_warnings
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

_QT_APP = None

def _policy() -> IllustrationPolicyData:
    return IllustrationPolicyData(
        policy_number="UL000001", issue_date=date(2019, 11, 9), issue_age=50,
        valuation_date=date(2026, 5, 9), duration=78, policy_year=7)


def _inputs(*transactions) -> IllustrationInputSet:
    return IllustrationInputSet(dated_transactions=list(transactions))


def _states(policy, count=12, **by_offset):
    states = [MonthlyState(duration=policy.duration, policy_year=7)]
    for offset in range(1, count + 1):
        duration = policy.duration + offset
        state = MonthlyState(duration=duration, policy_year=(duration - 1) // 12 + 1)
        for name, value in by_offset.get(f"m{offset}", {}).items():
            setattr(state, name, value)
        states.append(state)
    return states


def _loan_month(policy, inputs) -> int:
    compiled = compile_month_inputs(policy, inputs, 12)
    return next(d for d, month in compiled.items() if month.regular_loan > 0) - policy.duration


def test_withdrawal_reduced_by_engine_is_reported_per_policy_year():
    policy = _policy()
    states = _states(policy, m2={"input_withdrawal": 10_000.0,
                                 "applied_net_withdrawal": 6_543.21})
    assert reduced_request_warnings(policy, IllustrationInputSet(), states) == [
        "Requested withdrawal of $10,000.00 in policy year 7 was reduced to $6,543.21 — "
        "the most the policy allows. The illustration shows the reduced amount."]


def test_loan_reduced_by_engine_is_reported():
    policy = _policy()
    inputs = _inputs(DatedTransaction(
        kind=TransactionKind.LOAN, effective_date=date(2026, 8, 9), amount=5_000.0))
    offset = _loan_month(policy, inputs)
    states = _states(policy, **{f"m{offset}": {"applied_regular_loan": 1_200.0}})
    [message] = reduced_request_warnings(policy, inputs, states)
    assert message.startswith("Requested loan of $5,000.00 in policy year 7 was reduced to $1,200.00")


def test_fully_applied_requests_are_silent():
    policy = _policy()
    inputs = _inputs(DatedTransaction(
        kind=TransactionKind.LOAN, effective_date=date(2026, 8, 9), amount=5_000.0))
    offset = _loan_month(policy, inputs)
    states = _states(policy, **{
        f"m{offset}": {"applied_regular_loan": 4_000.0, "applied_preferred_loan": 1_000.0},
        "m3": {"input_withdrawal": 2_000.0, "applied_net_withdrawal": 2_000.0},
    })
    assert reduced_request_warnings(policy, inputs, states) == []


def test_lapsed_months_are_not_reported_as_reductions():
    policy = _policy()
    states = _states(policy, m2={"input_withdrawal": 1_000.0, "lapsed": True})
    assert reduced_request_warnings(policy, IllustrationInputSet(), states) == []


def test_run_result_carries_the_reduction_warning(monkeypatch):
    from suiteview.illustration.core import run_service

    policy = _policy()
    states = _states(policy, m1={"input_withdrawal": 500.0, "applied_net_withdrawal": 0.0})
    scenario = run_service.RunScenario(
        scenario=type("S", (), {"projectable_policy": policy})(),
        projection_months=12, duration_label="for 1 years")
    resolved = run_service.ResolvedRunInputs(
        IllustrationInputSet(), None, run_service.SolvedInputs(), [])
    warnings = run_service._reduced_request_warnings(scenario, resolved, states)
    assert warnings == (
        "Requested withdrawal of $500.00 in policy year 7 was reduced to $0.00 — the most "
        "the policy allows. The illustration shows the reduced amount.",)
    # A check that can't run never fails the illustration.
    assert run_service._reduced_request_warnings(scenario, resolved, [object(), object()]) == ()


@pytest.mark.parametrize("business", [False, True])
def test_window_shows_run_warnings_in_the_notice(monkeypatch, business):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    from suiteview.illustration.core.business_mode import BUSINESS_MODE_ENV
    from suiteview.illustration.ui.main_window import IllustrationWindow

    if business:
        monkeypatch.setenv(BUSINESS_MODE_ENV, "1")
    else:
        monkeypatch.delenv(BUSINESS_MODE_ENV, raising=False)
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    win = IllustrationWindow()
    win._load_warnings = ("Load warning.",)
    win._show_run_warnings(["Requested withdrawal of $1.00 in policy year 7 was reduced."])
    assert not win.run_notice.isHidden()
    assert win.run_notice.text().splitlines() == [
        "Load warning.", "Requested withdrawal of $1.00 in policy year 7 was reduced."]
