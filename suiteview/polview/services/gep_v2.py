"""GEP v2 — target-date premium projections for Policy Support.

GLP Exception (``guideline_exception_adjustment``) solves a *level* premium
paid from today, so its answer depends on when the owner pays. GEP v2 removes
that timing. It pays **nothing between premium dates**. A premium is paid on
each **policy anniversary** after the quote and before the target, and on the
**target monthliversary** itself. Each premium must carry the policy to its own
date. The question is simply: what would it take for the policy to stay in force
through each of those dates under current circumstances?

All three scenarios open from the same basis as GLP Exception: the Interim AV Quote
on the quote date, current GLP/GSP/AccumGLP and accumulators, and monthly
compounding (RERUN's unchecked Exact Days Interest). Monthly deductions run on
every monthliversary through the target. ``no_lapse`` lets the account value go
negative between premiums instead of lapsing the projection.

Every premium is figured the same way, in date order, given the premiums
already paid:

* **Max Premium Projection** pays the premium the GPT limit allows, treated as
  received just *before* its date. It is measured against the guideline limit
  in force the moment before,
  ``max(0, max(GSP, AccumGLP)_before - (PremTD - WDs))``. GLP added at an
  earlier anniversary counts. The GLP added at the premium date's own
  anniversary does **not**: that premium is subject to the ending year's limit.
  Guideline forceouts and the guideline acceptance cap stay on.
* **Min Prem w Forceouts** pays the smallest premium on each date that keeps
  the policy in force on that date, with guideline forceouts processed. A
  forceout is taken in full even when it drives the account value (further)
  negative, so it surfaces in the premiums required. Forceouts are measured on
  the opening premiums to date: the scenario's own premiums are GEP premiums
  and are never forced back out. The guideline limit does not cap them.
* **Min Prem No outs** pays the smallest premium on each date that keeps the
  policy in force on that date. It ignores the guideline limit and suppresses
  forceouts (as if a negative GLP were set to zero). With no premium needed,
  the premium is $0.

"In force" on a premium date means the account value on that date, after that
day's premium and before that day's monthly deduction, is not negative. A
scenario stays in force only if every premium date passes. The TAMRA 7-pay
limit is not enforced in any scenario, so a premium that would make the
policy a MEC is reported rather than capped.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Optional

from suiteview.illustration.api import project_policy
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.interim_value import InterimAccountValue
from suiteview.illustration.core.solve_level_to_exception import default_premium_mode
from suiteview.illustration.core.solvers import bracket_and_bisect
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    ScheduledTransaction,
    TransactionKind,
)

from .guideline_exception_adjustment import (
    TargetProjectionBasis,
    prepare_target_projection,
    with_date,
)

# AV at or above minus half a cent displays as $0.00, so it counts as in force.
IN_FORCE_TOLERANCE = 0.005
MAX_PREMIUM_LABEL = "Max Premium Projection"
MIN_FORCEOUTS_LABEL = "Min Prem w Forceouts"
MIN_NO_OUTS_LABEL = "Min Prem No outs"
# The first bracket seed is the account-value shortfall; ×1.25 per step covers
# premium loads, and 40 steps is far beyond any real policy.
_MIN_BRACKET_GROWTH = 1.25
_MIN_BRACKET_STEPS = 40


@dataclass(frozen=True)
class GepV2Payment:
    """One premium date in a scenario and how the policy stands on it.

    ``state`` is that date's month in the scenario's final projection: its
    premium is applied before its monthly deduction. ``av_entering`` is the
    account value carried into the month, before the premium.
    ``guideline_limit`` and ``premiums_less_withdrawals`` are the GPT basis of a
    Max premium; they are ``None`` for the unlimited Min premium.
    """

    date: date
    requested_premium: float
    state: MonthlyState
    av_entering: float
    guideline_limit: Optional[float] = None
    premiums_less_withdrawals: Optional[float] = None

    @property
    def applied_premium(self) -> float:
        return float(self.state.gross_premium or 0.0)

    @property
    def av_before_md(self) -> float:
        """AV after the premium (and any forceout), before the deduction."""
        return float(self.state.guideline_av_before_monthly_deduction or 0.0)

    @property
    def in_force(self) -> bool:
        return self.av_before_md >= -IN_FORCE_TOLERANCE

    @property
    def shortfall(self) -> float:
        """Additional account value this date needs; zero when in force."""
        return 0.0 if self.in_force else -self.av_before_md


@dataclass(frozen=True)
class GepV2Scenario:
    """One GEP v2 projection: opening snapshot through the target month.

    ``states[0]`` is the opening (valuation or interim) row and ``states[-1]``
    the target monthliversary. ``payments`` lists each premium date in order;
    the last one is the target.
    """

    label: str
    payments: tuple[GepV2Payment, ...]
    states: tuple[MonthlyState, ...]
    becomes_mec: bool = False

    @property
    def total_premium(self) -> float:
        """Total premium paid into the policy over all premium dates."""
        return sum(payment.applied_premium for payment in self.payments)

    @property
    def total_forceouts(self) -> float:
        """Guideline forceouts processed over the projected months (not the opening row)."""
        return sum(float(state.guideline_forceout or 0.0) for state in self.states[1:])

    @property
    def target_av_before_md(self) -> float:
        """Target-date AV after its premium, before its monthly deduction."""
        return float(self.target_state.guideline_av_before_monthly_deduction or 0.0)

    @property
    def target_state(self) -> MonthlyState:
        return self.states[-1]

    @property
    def in_force(self) -> bool:
        """True when every premium date leaves a non-negative AV before its MD."""
        return all(payment.in_force for payment in self.payments)

    @property
    def first_failure(self) -> Optional[GepV2Payment]:
        return next((payment for payment in self.payments if not payment.in_force), None)


@dataclass(frozen=True)
class GepV2Result:
    """The three GEP v2 scenarios plus the shared quote basis.

    ``premium_dates`` are the anniversaries after the opening and before the
    target, then the target monthliversary. That is the requested target date
    when it is a monthliversary, else the first monthliversary after it.
    """

    target_date: date
    premium_dates: tuple[date, ...]
    valuation_date: date
    max_premium: GepV2Scenario
    min_premium_forceouts: GepV2Scenario
    min_premium_no_outs: GepV2Scenario
    interim: InterimAccountValue | None = None
    interim_unavailable_reason: str = ""

    @property
    def scenarios(self) -> tuple[GepV2Scenario, ...]:
        """Max, Min w Forceouts, Min No outs — the display and export order."""
        return (self.max_premium, self.min_premium_forceouts, self.min_premium_no_outs)

    @property
    def premium_date(self) -> date:
        """The target monthliversary (the last premium date)."""
        return self.premium_dates[-1]

    @property
    def gep_exception_forceouts(self) -> float:
        """GEP exception premium with forceouts processed (Min w Forceouts over Max)."""
        return self.gep_exception_for(self.min_premium_forceouts)

    @property
    def gep_exception_no_outs(self) -> float:
        """GEP exception premium with forceouts suppressed (Min No outs over Max)."""
        return self.gep_exception_for(self.min_premium_no_outs)

    @property
    def current_accum_glp(self) -> float:
        """AccumGLP on the opening row (valuation or interim quote date)."""
        return float(self.max_premium.states[0].accumulated_glp or 0.0)

    @property
    def new_accum_glp(self) -> float:
        """Current AccumGLP raised by the GEP exception required with forceouts."""
        return round(self.current_accum_glp + self.gep_exception_forceouts, 2)

    def gep_exception_for(self, minimum: GepV2Scenario) -> float:
        """Premium a Min schedule needs beyond what the GPT limit allows.

        ``max(0, Min total - Max total)``: when keeping the policy in force takes
        more premium than the guideline admits, the difference must come in as
        GP exception premium.
        """
        return max(0.0, round(minimum.total_premium - self.max_premium.total_premium, 2))


def project_gep_v2(policy, target_date: date, *, quote_date: date) -> GepV2Result:
    """Project the Max and both Min premium-schedule scenarios for ``policy``.

    ``policy`` is the PolView ``PolicyInformation`` (or a compatible source).
    ``quote_date`` is the day the quote is run; the projection opens from that
    day's Interim AV Quote. Raises ``ValueError`` when the policy cannot be
    forecast or the target is unreachable.
    """
    basis = prepare_target_projection(policy, target_date, quote_date)
    ill_policy = basis.policy
    if not ill_policy.is_gpt:
        raise ValueError("The guideline premium limit does not apply to this policy (not GPT).")
    runner = _ScenarioRunner(basis)

    max_options = _max_options(basis)
    baseline = runner.project(max_options, {})
    premium_dates = tuple(
        [state.date for state in baseline[1:-1] if state.is_anniversary]
        + [baseline[-1].date])

    max_premiums: dict[date, float] = {}
    gpt_basis: dict[date, tuple[float, float]] = {}
    for when in premium_dates:
        states = runner.project(max_options, max_premiums, through=when)
        limit, premiums_less_withdrawals, room = _gpt_room_before(states)
        max_premiums[when] = room
        gpt_basis[when] = (limit, premiums_less_withdrawals)
    max_states = runner.project(max_options, max_premiums)

    opening_mec = bool(ill_policy.is_mec)
    return GepV2Result(
        target_date=target_date,
        premium_dates=premium_dates,
        valuation_date=basis.valuation_date,
        max_premium=GepV2Scenario(
            MAX_PREMIUM_LABEL,
            _payments(max_states, max_premiums, gpt_basis),
            max_states,
            becomes_mec=_becomes_mec(max_states, opening_mec)),
        min_premium_forceouts=_min_scenario(
            runner, _min_options(basis, forceouts=True), premium_dates,
            MIN_FORCEOUTS_LABEL, opening_mec),
        min_premium_no_outs=_min_scenario(
            runner, _min_options(basis, forceouts=False), premium_dates,
            MIN_NO_OUTS_LABEL, opening_mec),
        interim=basis.interim,
        interim_unavailable_reason=basis.interim_unavailable_reason,
    )


def _min_scenario(
    runner: "_ScenarioRunner",
    options: IllustrationOptions,
    premium_dates: tuple[date, ...],
    label: str,
    opening_mec: bool,
) -> GepV2Scenario:
    """Solve each date's least premium in order, then project the schedule."""
    premiums: dict[date, float] = {}
    for when in premium_dates:
        premiums[when] = _solve_min_premium(runner, options, premiums, when)
    states = runner.project(options, premiums)
    for when in premium_dates:
        if _state_on(states, when).guideline_av_before_monthly_deduction < 0.0:
            raise ValueError(
                f"The {label} schedule does not keep the policy in force on "
                f"{when:%m/%d/%Y}.")
    return GepV2Scenario(
        label,
        _payments(states, premiums, {}),
        states,
        becomes_mec=_becomes_mec(states, opening_mec))


def _base_options(basis: TargetProjectionBasis, **guideline) -> IllustrationOptions:
    """Projection basis shared by every scenario; ``guideline`` sets the GPT handling."""
    return IllustrationOptions(
        recognize_inforce_exception_period=False,
        conform_to_tamra=False,
        allow_exception_prems=False,
        exact_days_interest=False,
        interim_opening=basis.interim_opening,
        no_lapse=True,
        **guideline,
    )


def _max_options(basis: TargetProjectionBasis) -> IllustrationOptions:
    """Max scenario: GPT acceptance cap and (AV-capped) forceouts on."""
    return _base_options(basis, conform_to_tefra=True, guideline_forceouts=True)


def _min_options(basis: TargetProjectionBasis, *, forceouts: bool) -> IllustrationOptions:
    """Min scenarios: premiums are never capped at the guideline limit.

    ``forceouts=True`` (Min w Forceouts) processes every guideline forceout in
    full, even below a zero AV, measured on the opening premiums only so the
    scenario's own GEP premiums are never forced back out. ``forceouts=False``
    (Min No outs) suppresses forceouts entirely.
    """
    if not forceouts:
        return _base_options(basis, conform_to_tefra=False, guideline_forceouts=False)
    return _base_options(
        basis,
        conform_to_tefra=True,
        cap_premiums_at_acceptance=False,
        guideline_forceouts=True,
        forceouts_overdraw_account_value=True,
        forceout_projected_premiums=False,
    )


class _ScenarioRunner:
    """Project the policy with premiums only on chosen monthliversaries."""

    def __init__(self, basis: TargetProjectionBasis):
        self._basis = basis
        self._final_months = basis.months_to_target + 1
        self._engine = IllustrationEngine()

    def project(
        self,
        options: IllustrationOptions,
        premiums: Mapping[date, float],
        *,
        through: Optional[date] = None,
    ) -> tuple[MonthlyState, ...]:
        """States from the opening row through ``through`` (default: the target).

        ``premiums`` maps monthliversary dates to gross premiums; every other
        month pays nothing (an explicit zero schedule overrides billing).
        """
        policy = self._basis.policy
        months = self._final_months if through is None else _months_through(policy, through)
        inputs = IllustrationInputSet(
            scheduled_transactions=[ScheduledTransaction(
                kind=TransactionKind.PREMIUM,
                policy_year=int(policy.policy_year or 1),
                amount=0.0,
                mode=default_premium_mode(policy),
            )],
            dated_transactions=[
                DatedTransaction(
                    kind=TransactionKind.PREMIUM,
                    effective_date=when,
                    amount=round(amount, 2),
                    subtype="gep_v2_premium",
                )
                for when, amount in sorted(premiums.items())
                if amount > 0.0 and (through is None or when <= through)
            ],
        )
        states = project_policy(
            copy.deepcopy(policy),
            inputs=inputs,
            options=options,
            months=months,
            engine=self._engine,
            rates=self._basis.rates,
            config=self._basis.config,
        ).states
        reached = states[-1].date if states else None
        if not states or len(states) != months + 1 or (
                through is not None and reached != through):
            raise ValueError(
                f"The projection ended on {reached:%m/%d/%Y} before the target "
                "monthliversary (the policy matures first)."
                if reached is not None else
                "The projection returned no months.")
        interim_opening = self._basis.interim_opening
        if interim_opening is not None:
            states = [with_date(states[0], interim_opening.as_of), *states[1:]]
        return tuple(states)


def _months_through(policy, when: date) -> int:
    """Projected months from the opening row through the monthliversary ``when``."""
    issue = policy.issue_date
    return (when.year - issue.year) * 12 + (when.month - issue.month) - policy.duration + 1


def _gpt_room_before(states) -> tuple[float, float, float]:
    """GPT room for a premium received just before the last state's date.

    Returns ``(limit, premiums_less_withdrawals, room)``. ``limit`` is the
    guideline limit ``max(GSP, AccumGLP)`` on the row before the premium month.
    On an anniversary that row is the last of the ending policy year, so the
    anniversary's new GLP is excluded; otherwise the limit is unchanged.
    ``premiums_less_withdrawals`` is the premium month's ``PremTD - WDs`` before
    its own premium or forceout. The room is floored to a payable cent.
    """
    if len(states) < 2:
        raise ValueError("The projection did not reach the premium month.")
    limit = float(states[-2].guideline_limit or 0.0)
    premiums_less_withdrawals = float(states[-1].prem_less_wd or 0.0)
    room = max(0.0, limit - premiums_less_withdrawals)
    return limit, premiums_less_withdrawals, math.floor(room * 100.0 + 1e-6) / 100.0


def _solve_min_premium(
    runner: _ScenarioRunner,
    options: IllustrationOptions,
    earlier: Mapping[date, float],
    when: date,
) -> float:
    """Smallest whole-cent premium on ``when`` leaving its pre-deduction AV >= 0.

    ``earlier`` premiums are already fixed. The premium on ``when`` cannot change
    earlier months, so the AV before that date's deduction rises monotonically
    with it. Bracket and bisect on the real engine so premium loads are exact.
    """
    def av_with(premium: float) -> float:
        states = runner.project(options, {**earlier, when: premium}, through=when)
        return float(states[-1].guideline_av_before_monthly_deduction or 0.0)

    shortfall = -av_with(0.0)
    if shortfall <= 0.0:
        return 0.0
    solved = bracket_and_bisect(
        lambda premium: av_with(premium) >= 0.0,
        0.0,
        shortfall,
        growth=_MIN_BRACKET_GROWTH,
        max_iter=_MIN_BRACKET_STEPS,
        round_to=0.01,
        round_up=True,
        carry_lower=True,
    )
    if not solved.bracketed or av_with(solved.value) < 0.0:
        raise ValueError(
            f"No premium on {when:%m/%d/%Y} restores a non-negative account value.")
    return solved.value


def _payments(states, premiums: Mapping[date, float], gpt_basis) -> tuple[GepV2Payment, ...]:
    payments = []
    for when, premium in premiums.items():
        index = next(i for i, state in enumerate(states) if state.date == when)
        limit, premiums_less_withdrawals = gpt_basis.get(when, (None, None))
        payments.append(GepV2Payment(
            date=when,
            requested_premium=premium,
            state=states[index],
            av_entering=float(states[index - 1].av_end_of_month or 0.0) if index else 0.0,
            guideline_limit=limit,
            premiums_less_withdrawals=premiums_less_withdrawals,
        ))
    return tuple(payments)


def _state_on(states, when: date) -> MonthlyState:
    return next(state for state in states if state.date == when)


def _becomes_mec(states, opening_mec: bool) -> bool:
    return not opening_mec and bool(states[-1].is_mec)
