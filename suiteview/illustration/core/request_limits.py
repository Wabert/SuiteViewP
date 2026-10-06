"""Requested withdrawals and loans the engine reduced (soft-launch should-do 2).

The engine silently applies MIN(request, maximum available) to a withdrawal
(RERUN AY/BA) and caps a new fixed loan at the loanable value. The ledger shows
the applied amount while the cover lists the request, so a user can't tell a
request was cut. :func:`reduced_request_warnings` compares each month's request
with what the engine applied and returns one warning per policy year and kind.
Reads results only; no calculation changes.
"""

from __future__ import annotations

from collections import defaultdict

from suiteview.illustration.core.input_compiler import compile_month_inputs

_EPSILON = 0.005


def _money(value: float) -> str:
    return f"${value:,.2f}"


def reduced_request_warnings(policy, future_inputs, states) -> list[str]:
    """One message per (kind, policy year) whose request was reduced."""
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
                bucket = totals[("withdrawal", state.policy_year)]
                bucket[0] += requested_wd
                bucket[1] += applied_wd
        month = compiled.get(state.duration)
        if month is None:
            continue
        for kind, requested, applied in (
            ("loan", month.regular_loan,
             state.applied_regular_loan + state.applied_preferred_loan),
            ("variable loan", month.variable_loan, state.applied_variable_loan),
        ):
            requested = float(requested or 0.0)
            if requested > _EPSILON and float(applied or 0.0) < requested - _EPSILON:
                bucket = totals[(kind, state.policy_year)]
                bucket[0] += requested
                bucket[1] += float(applied or 0.0)
    return [
        f"Requested {kind} of {_money(requested)} in policy year {year} was reduced to "
        f"{_money(applied)} — the most the policy allows. The illustration shows the "
        "reduced amount."
        for (kind, year), (requested, applied) in sorted(
            totals.items(), key=lambda item: (item[0][1], item[0][0]))
    ]
