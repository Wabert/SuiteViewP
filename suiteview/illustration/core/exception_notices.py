"""Run notice for a scheduled premium replaced by the GP exception premium.

Once GP exception mode latches (past the safety net, no shadow account), the
engine stops requesting the scheduled/billable premium and the calculated
exception premium becomes the whole monthly contribution (Robert, 10/6/2026;
``calc_engine._gp_exception_premium_replaces_schedule``). The ledger then shows
the exception premium where the user entered a billable premium, so
:func:`gp_exception_schedule_notices` says so once per run. It reads results
only; no calculation changes. A recognized in-force exception period has its
own Input notice and is not repeated here.
"""

from __future__ import annotations

from suiteview.illustration.core.input_compiler import compile_month_inputs

_EPSILON = 0.005


def _scheduled_request(policy, month) -> float:
    """The scheduled premium the engine would request this month (no override = modal)."""
    if month is None or month.total_premium is None:
        return float(getattr(policy, "modal_premium", 0.0) or 0.0)
    return float(month.scheduled_premium or 0.0)


def gp_exception_schedule_notices(policy, future_inputs, states) -> list[str]:
    """One notice for the first month a latched GP exception replaced the schedule."""
    states = list(states or ())
    if len(states) < 2:
        return []
    compiled = compile_month_inputs(policy, future_inputs, len(states) - 1)
    for prior, state in zip(states, states[1:]):
        if getattr(state, "lapsed", False):
            return []
        if not prior.gp_exception_mode or state.inforce_exception_period:
            continue
        month = compiled.get(state.duration)
        scheduled = _scheduled_request(policy, month)
        lumpsum = float(month.unscheduled_premium or 0.0) if month is not None else 0.0
        if scheduled <= _EPSILON or state.requested_premium > lumpsum + _EPSILON:
            continue
        when = state.date.strftime("%m/%d/%Y")
        level = next(
            (s.gp_exception_prem for s in states[states.index(state):]
             if s.policy_year == state.policy_year and s.gp_exception_prem > _EPSILON),
            0.0,
        )
        detail = (
            f" ({level:,.2f} a month in policy year {state.policy_year})" if level else "")
        return [
            f"GP exception period from {when}: the scheduled premium ({scheduled:,.2f}) is "
            f"replaced by the calculated exception premium{detail}. Contributions show the "
            "exception premium; it is outside the guideline limit, so it is not reduced."
        ]
    return []
