"""Requested withdrawals and loans the engine reduced (soft-launch should-do 2).

The engine silently applies MIN(request, maximum available) to a withdrawal
(RERUN AY/BA) and caps a new fixed loan at the loanable value. The ledger shows
the applied amount while the cover lists the request, so a user can't tell a
request was cut. :func:`reduced_requests` compares each month's request with
what the engine applied, one entry per policy year and kind;
:func:`reduced_request_warnings` words them for the run notice and the report
marks the restricted cover request lines (``report_builder``).
Reads results only; no calculation changes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from suiteview.illustration.core.input_compiler import compile_month_inputs

_EPSILON = 0.005

KIND_WITHDRAWAL = "withdrawal"
KIND_LOAN = "loan"
KIND_VARIABLE_LOAN = "variable loan"


@dataclass(frozen=True)
class ReducedRequest:
    """A policy year whose requested withdrawal or loan total was reduced."""

    kind: str
    policy_year: int
    requested: float
    applied: float


def _money(value: float) -> str:
    return f"${value:,.2f}"


def reduced_requests(policy, future_inputs, states) -> list[ReducedRequest]:
    """One entry per (kind, policy year) whose request was reduced, in year order."""
    projected = [state for state in list(states)[1:] if not getattr(state, "lapsed", False)]
    if not projected:
        return []
    compiled = compile_month_inputs(policy, future_inputs, len(states) - 1)
    totals: dict[tuple[str, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for state in projected:
        requested_wd = float(getattr(state, "input_withdrawal", 0.0) or 0.0)
        if requested_wd > _EPSILON:
            applied_wd = float(getattr(state, "applied_net_withdrawal", 0.0) or 0.0)
            if applied_wd < requested_wd - _EPSILON:
                bucket = totals[(KIND_WITHDRAWAL, state.policy_year)]
                bucket[0] += requested_wd
                bucket[1] += applied_wd
        month = compiled.get(state.duration)
        if month is None:
            continue
        for kind, requested, applied in (
            (KIND_LOAN, month.regular_loan,
             state.applied_regular_loan + state.applied_preferred_loan),
            (KIND_VARIABLE_LOAN, month.variable_loan, state.applied_variable_loan),
        ):
            requested = float(requested or 0.0)
            if requested > _EPSILON and float(applied or 0.0) < requested - _EPSILON:
                bucket = totals[(kind, state.policy_year)]
                bucket[0] += requested
                bucket[1] += float(applied or 0.0)
    return [
        ReducedRequest(kind, year, requested, applied)
        for (kind, year), (requested, applied) in sorted(
            totals.items(), key=lambda item: (item[0][1], item[0][0]))
    ]


def reduced_request_warnings(policy, future_inputs, states) -> list[str]:
    """One message per (kind, policy year) whose request was reduced."""
    return [
        f"Requested {item.kind} of {_money(item.requested)} in policy year "
        f"{item.policy_year} was reduced to {_money(item.applied)} — the most the policy "
        "allows. The illustration shows the reduced amount."
        for item in reduced_requests(policy, future_inputs, states)
    ]
