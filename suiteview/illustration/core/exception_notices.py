"""Run notice for a scheduled premium replaced by the GP exception premium.

Once GP exception mode latches (past the safety net, no shadow account), the
engine stops requesting the scheduled/billable premium and the calculated
exception premium becomes the whole monthly contribution (Robert, 10/6/2026;
``calc_engine._gp_exception_premium_replaces_schedule``). The ledger then shows
the exception premium in Contributions and a requested premium of 0 where the
user entered a scheduled premium. :func:`gp_exception_schedule_notices` names
the replaced amount and mode once per run. It reads results only; no calculation
changes. A recognized in-force exception period has its own Input notice and
is not repeated here.

The requested premium stays 0 in the ledger on purpose: it drives the PremCap
flag and the report cover's premium schedule, and neither should show a premium
that is never paid.
"""

from __future__ import annotations

from suiteview.illustration.core.input_compiler import compile_month_inputs

_EPSILON = 0.005
_MODE_LABELS = {"M": "Monthly", "Q": "Quarterly", "S": "Semiannual", "A": "Annual"}
_FREQUENCY_MODES = {1: "M", 3: "Q", 6: "S", 12: "A"}


def _scheduled_request(policy, month) -> tuple[float, str]:
    """The scheduled premium and mode the engine would request this month."""
    if month is None or month.total_premium is None:
        frequency = int(getattr(policy, "billing_frequency", 1) or 1)
        return (float(getattr(policy, "modal_premium", 0.0) or 0.0),
                _FREQUENCY_MODES.get(frequency, "M"))
    return float(month.scheduled_premium or 0.0), (month.premium_mode or "M")


def gp_exception_schedule_notices(policy, future_inputs, states) -> list[str]:
    """One notice for the first scheduled payment a latched GP exception replaced."""
    states = list(states or ())
    if len(states) < 2:
        return []
    compiled = compile_month_inputs(policy, future_inputs, len(states) - 1)
    for index, (prior, state) in enumerate(zip(states, states[1:]), start=1):
        if getattr(state, "lapsed", False):
            return []
        if not prior.gp_exception_mode or state.inforce_exception_period:
            continue
        month = compiled.get(state.duration)
        scheduled, mode = _scheduled_request(policy, month)
        lumpsum = float(month.unscheduled_premium or 0.0) if month is not None else 0.0
        if scheduled <= _EPSILON or state.requested_premium > lumpsum + _EPSILON:
            continue
        mode_label = _MODE_LABELS.get(mode.strip().upper(), mode)
        level = next(
            (s.gp_exception_prem for s in states[index:]
             if s.policy_year == state.policy_year and s.gp_exception_prem > _EPSILON),
            0.0,
        )
        detail = (
            f" (${level:,.2f} a month in policy year {state.policy_year})" if level else "")
        return [
            f"From {state.date:%m/%d/%Y} the policy is in the guideline premium exception "
            f"period: the scheduled premium (${scheduled:,.2f} {mode_label}) is replaced by "
            f"the exception premium needed to keep the policy in force{detail}. "
            "Contributions show the exception premium; it is outside the guideline limit."
        ]
    return []
