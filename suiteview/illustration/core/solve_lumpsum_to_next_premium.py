"""Solve a bridging lumpsum that keeps a thin policy in force until its next
scheduled modal premium.

A policy can be too thin to coast from the forecast date to the next premium —
on annual mode the next premium may be most of a year away; on quarterly /
semiannual modes the gap is shorter but the same thing happens. This solver
finds the unscheduled premium to apply ON the forecast date so the policy stays
in force every month up to (and including) the next modal premium, where the
illustrated premium picks the policy back up.

*How much* is read from the same lapse test the engine runs each month
(``calc_engine`` § 18): the surrender-value shortfall (SV-lapse plancodes), the
account-value-less-loans shortfall (AV / MLUL-lapse plancodes), or the
safety-net gap (accumulated premium short of accumulated MTP) while inside the
SNET period — whichever is the *lower* amount. That gives a seed estimate.

Because the lumpsum is a premium (loads shave it, interest grows it), the seed
understates the gross premium needed, so it is only a starting bracket — the
real engine then brackets and bisects "survives the window" the same way
``solve_level_to_exception`` solves the level premium. The result lands exactly
on the in-force side of the lapse boundary after every load, deduction, and
interest credit.

When the 7702 guideline caps the premium below what the bridge needs (a policy
already sitting at its guideline limit), no premium-only bridge exists — the
solver applies the largest premium the guideline accepts and flags
``guideline_limited`` so the caller can tell the user GP exception premiums are
required.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from dateutil.relativedelta import relativedelta

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.plancode_config import PlancodeConfig
from suiteview.illustration.models.policy_data import IllustrationPolicyData

# Subtype stamped on the injected premium so the value / report can label it.
LUMPSUM_SUBTYPE = "lumpsum_to_next_premium"

# Backstop so a guideline-bound policy can never loop the upper-bracket search.
_MAX_BRACKET_DOUBLINGS = 24

# Modal cadence → months between payments. Anything else is treated as monthly
# (non-standard modes are collected monthly out of the premium-depositor fund).
_VALID_INTERVALS = (1, 3, 6, 12)


@dataclass
class LumpsumToNextPremiumResult:
    lumpsum: float                  # gross premium to inject on the forecast date
    applied: float                  # premium the engine accepted (after caps)
    forecast_date: date             # the month the lumpsum lands on
    next_premium_date: date         # the modal due date it carries the policy to
    seed_shortfall: float           # raw SV / AV / SNET shortfall (for display)
    binding_reason: str             # "SV" | "AV" | "SNET" — what set the seed
    guideline_limited: bool         # guideline cap stopped a full bridge
    iterations: int                 # engine projections spent solving


def _billing_interval(policy: IllustrationPolicyData) -> int:
    try:
        freq = int(policy.billing_frequency or 1)
    except (TypeError, ValueError):
        freq = 1
    return freq if freq in _VALID_INTERVALS else 1


def _forecast_date(policy: IllustrationPolicyData) -> Optional[date]:
    """First projected (forecast) month — the inforce snapshot plus one month.

    Anchored on ``issue + duration`` so the injected dated premium lands on the
    exact monthliversary the input compiler maps to the first forecast row
    (``input_compiler`` offset 1), independent of how the valuation date is set.
    """
    if policy.issue_date is None:
        return None
    return policy.issue_date + relativedelta(months=policy.duration)


def _next_modal_due(policy: IllustrationPolicyData, forecast: date) -> tuple[date, int]:
    """The next modal premium due date after the forecast date, and the number of
    whole months from the forecast date to it.

    Modal due dates fall on the anniversary cadence (anniversary + k·interval),
    i.e. at whole-month counts since issue that are multiples of the interval.
    When the forecast date already lands on a modal date the gap is 0 — a premium
    is collected on the forecast date itself, so there is nothing to bridge.
    """
    interval = _billing_interval(policy)
    months_at_forecast = policy.duration          # whole months issue → forecast
    remainder = months_at_forecast % interval
    gap = (interval - remainder) if remainder else 0
    next_due = policy.issue_date + relativedelta(months=months_at_forecast + gap)
    return next_due, gap


def _within_snet(state: MonthlyState, policy: IllustrationPolicyData,
                 config: PlancodeConfig) -> bool:
    """Whether ``state``'s month is inside the safety-net window — the same test
    the engine runs (``calc_engine`` line 595)."""
    if policy.map_cease_date is not None and state.date is not None:
        return state.date <= policy.map_cease_date
    return state.policy_year <= config.snet_period


def _seed_shortfall(window: List[MonthlyState], policy: IllustrationPolicyData,
                    config: PlancodeConfig) -> tuple[float, str]:
    """Worst single-month bridge shortfall across the window, and what bound it.

    Per lapsed month the need is the surrender-value shortfall (SV plancodes) or
    the account-value-less-loans shortfall (AV / MLUL plancodes); inside the SNET
    period the safety-net gap is used instead when it is the lower amount. The
    worst (largest) month sizes the lumpsum, since one deposit at the forecast
    date must hold the policy in force through the whole window.
    """
    worst = 0.0
    reason = config.lapse_value
    for state in window:
        if not state.lapsed:
            continue
        if config.lapse_value == "AV":
            base_need = max(0.0, -state.av_less_loans)
        else:
            base_need = max(0.0, -state.surrender_value)
        need, month_reason = base_need, config.lapse_value
        if _within_snet(state, policy, config):
            snet_need = max(0.0, -state.accum_mtp_less_prem)
            if snet_need < base_need:
                need, month_reason = snet_need, "SNET"
        if need > worst:
            worst, reason = need, month_reason
    return worst, reason


def solve_lumpsum_to_next_premium(
    policy: IllustrationPolicyData,
    *,
    base_future_inputs: Optional[IllustrationInputSet] = None,
    base_options: Optional[IllustrationOptions] = None,
    config: Optional[PlancodeConfig] = None,
    engine: Optional[IllustrationEngine] = None,
    resolution: float = 0.01,
) -> Optional[LumpsumToNextPremiumResult]:
    """Bridging lumpsum that keeps ``policy`` in force to its next modal premium.

    Returns ``None`` when no bridge is needed — the policy already survives from
    the forecast date to the next modal premium on the user's illustrated inputs.

    Args:
        base_future_inputs: the run's future inputs; the lumpsum is layered on
            top as a dated premium on the forecast date so the bridge accounts
            for whatever premiums the user illustrated.
        base_options: the run's guideline toggles — honored as-is so the lumpsum
            is a real premium (capped at the guideline like any other).
        config: plancode config (lapse value, SNET period); defaults to the
            policy's. Only used to size and label the seed estimate.
        resolution: rounding granularity; the lumpsum is rounded UP to this so it
            lands on the in-force side of the lapse boundary.
    """
    engine = engine or IllustrationEngine()
    options = base_options if base_options is not None else IllustrationOptions()
    if config is None:
        from suiteview.illustration.models.plancode_config import load_plancode
        config = load_plancode(policy.plancode)

    forecast = _forecast_date(policy)
    if forecast is None:
        return None
    next_due, gap = _next_modal_due(policy, forecast)
    if gap <= 0:
        return None  # a modal premium already lands on the forecast date — no gap

    # A "Billable to MD" run hands off to Monthly Deduction premiums the first
    # month the policy can't carry itself — which would trivially rescue any
    # lumpsum and defeat the bridge. The bridge must be sized on premium ALONE,
    # so suppress the hand-off across the whole solve window (up to the next
    # premium). The main run applies the same floor, so the bridge the solver
    # sizes is the bridge the run experiences.
    if options.billable_to_md_windows:
        from dataclasses import replace
        options = replace(options, billable_to_md_no_latch_before=next_due)

    # Project a touch past the next due date so its lapse test is fully formed.
    project_months = gap + 2
    base = base_future_inputs
    forecast_year = max(1, policy.duration // 12 + 1)

    def project(lumpsum: float) -> List[MonthlyState]:
        dated = list(base.dated_transactions) if base is not None else []
        if lumpsum > 0:
            dated.append(DatedTransaction(
                kind=TransactionKind.PREMIUM, effective_date=forecast,
                amount=float(lumpsum), subtype=LUMPSUM_SUBTYPE))
        # Silence premium billing across the bridge: the lumpsum must carry the
        # policy to the next scheduled premium on the inforce account value
        # ALONE, independent of whatever ongoing premium is planned. The two
        # never overlap — the ongoing premium resumes only at that next modal
        # date, which is the target we bridge to, not a month we lean on here.
        scheds = [s for s in (base.scheduled_transactions if base is not None else [])
                  if s.kind != TransactionKind.PREMIUM]
        scheds.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=forecast_year, amount=0.0, mode="A"))
        future = IllustrationInputSet(
            scheduled_transactions=scheds,
            dated_transactions=dated,
            policy_changes=list(base.policy_changes) if base is not None else [])
        # stop_on_lapse off so the whole window is populated even past a lapse.
        return engine.project(policy, months=project_months, future_inputs=future,
                              options=options, stop_on_lapse=False)

    def window(states: List[MonthlyState]) -> List[MonthlyState]:
        # Up to BUT NOT INCLUDING the next modal date: the scheduled premium is
        # collected there and rescues that month, so the bridge only has to keep
        # the policy alive through every deduction before it.
        return [s for s in states
                if s.date is not None and forecast <= s.date < next_due]

    def survives(states: List[MonthlyState]) -> bool:
        return not any(s.lapsed for s in window(states))

    iterations = 1
    base_states = project(0.0)
    if survives(base_states):
        return None  # already carries to the next premium — nothing to do

    seed, reason = _seed_shortfall(window(base_states), policy, config)

    # Bracket an upper bound that survives, seeded just above the raw shortfall
    # (grossed for the premium load it has yet to pay).
    lo = 0.0
    hi = max(seed * 1.15, policy.modal_premium, 1.0)
    doublings = 0
    while not survives(project(hi)):
        iterations += 1
        hi *= 2.0
        doublings += 1
        if doublings > _MAX_BRACKET_DOUBLINGS:
            # The guideline caps the premium below the bridge — no premium-only
            # solution. Apply the largest premium the guideline accepts and flag
            # it so the caller can prompt for GP exception premiums.
            capped = project(hi)
            iterations += 1
            applied = _accepted_lumpsum(capped, forecast)
            return LumpsumToNextPremiumResult(
                lumpsum=round(applied, 2), applied=round(applied, 2),
                forecast_date=forecast, next_premium_date=next_due,
                seed_shortfall=round(seed, 2), binding_reason=reason,
                guideline_limited=True, iterations=iterations)
    iterations += 1

    # Bisect to HALF the resolution, then test the rounded candidate directly
    # — ceiling the raw ``hi`` can overshoot a full step when the boundary
    # sits just under a grid point.
    while hi - lo > resolution / 2.0:
        mid = (lo + hi) / 2.0
        if survives(project(mid)):
            hi = mid
        else:
            lo = mid
        iterations += 1

    lumpsum = round(math.ceil(lo / resolution - 1e-9) * resolution, 2)
    final = project(lumpsum)
    iterations += 1
    if not survives(final):
        lumpsum = round(lumpsum + resolution, 2)
        final = project(lumpsum)
        iterations += 1
    applied = _accepted_lumpsum(final, forecast)
    return LumpsumToNextPremiumResult(
        lumpsum=round(lumpsum, 2), applied=round(applied, 2),
        forecast_date=forecast, next_premium_date=next_due,
        seed_shortfall=round(seed, 2), binding_reason=reason,
        guideline_limited=False, iterations=iterations)


def _accepted_lumpsum(states: List[MonthlyState], forecast: date) -> float:
    for state in states:
        if state.date == forecast:
            return float(state.applied_lumpsum or 0.0)
    return 0.0
