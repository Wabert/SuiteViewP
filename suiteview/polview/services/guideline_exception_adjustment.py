"""Guideline Exception Adjustment calculations.

The Policy Support GLP Exception window first runs the established
**Prem-to-Maturity** solve, then displays its illustrated monthly values through
the requested target date. Its first GP exception-premium month determines
whether the target is relevant: only when that date is strictly before the
target does the window also run the $0 **INPUT to MD** calculation.

The 0-input-to-MD calculation uses a Lumpsum-to-Next-Premium bridge on a
monthly cadence with TEFRA enforcement off. Its projected premium outlay is the
premium needed to stay in force, and its adjustment summary sizes the AccumGLP
room needed to admit that exception-premium alternative.

Room and adjustment:

* ``room = max(0, AccumGLP - PremiumsPaidToDate + AccumWDs)`` — the same
  "Prem Allowed by GPT" figure shown on the Targets & Accumulators tab, but with
  ``PremiumsPaidToDate`` brought current by adding premiums paid *since* the
  valuation date (mirroring the existing GLP-Exception solve).
* ``total_premium_needed`` — the gross premium actually paid into the policy
  (bridge lumpsum + monthly Monthly-Deduction / exception premiums), summed for
  every projected month **strictly before** the target date (the target date
  itself is excluded).
* ``adjustment_to_accum_glp = max(0, total_premium_needed - room)`` — the
  increase the AccumGLP needs to admit all of that premium under the guideline.

This is a single-target-date solve: it uses the policy's current AccumGLP and
does not chain intermediate anniversary adjustments.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date

from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.solve_level_to_exception import (
    LevelToExceptionError,
    level_to_exception_options,
    solve_level_to_exception,
)
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    ScheduledTransaction,
    TransactionKind,
)
from suiteview.illustration.models.policy_data import IllustrationPolicyData

from .glp_exception import (
    PremiumAdjustmentSinceValuation,
    _months_between_exclusive,
    _policy_with_post_valuation_premiums,
    _premium_adjustment_since_valuation,
    check_forecast_availability,
)


@dataclass
class GuidelineExceptionAdjustmentResult:
    """Outcome of a Guideline Exception Adjustment solve."""

    current_valuation_date: date | None
    target_date: date
    months_to_target: int
    premiums_since_valuation_date: float
    total_premium_needed: float
    room_available: float
    accumulated_glp: float
    premiums_paid_to_date: float
    accumulated_withdrawals: float
    adjustment_to_accum_glp: float
    new_accum_glp: float
    message: str

    @property
    def premiums_to_date_on_target(self) -> float:
        """Premiums paid to date *including* the forecast premium needed to reach
        the target — i.e. the PremTD the policy carries on the target date.

        With this figure the adjustment is the single-formula form shown on the
        Policy Support GLP Exception page:
        ``adjustment = max(0, PremTD_on_target - AccumWDs - AccumGLP)``.
        """
        return self.premiums_paid_to_date + self.total_premium_needed


@dataclass
class GuidelineExceptionForecastRow:
    """One month of the INPUT-to-MD ($0) guideline exception forecast."""

    date: date | None
    policy_year: int
    policy_month: int
    interest_credited: float
    premium: float
    monthly_deduction: float
    account_value: float
    glp: float
    accumulated_glp: float
    premiums_to_date: float
    accumulated_withdrawals: float
    force_out: float
    exception_premium: float
    in_exception_mode: bool
    policy_debt: float


@dataclass
class GuidelineExceptionForecastResult:
    """Full result of the Policy Support GLP Exception forecast.

    Bundles the month-by-month INPUT-to-MD projection (``rows``) with the
    :class:`GuidelineExceptionAdjustmentResult` ``summary`` so the UI can show
    both the guideline-annotated forecast table and the adjustment summary.

    Used for the conditional 0-input-to-Monthly-Deduction forecast after the
    Prem-to-Maturity projection establishes that exception premium status begins
    before the requested target date.
    """

    summary: GuidelineExceptionAdjustmentResult
    rows: list[GuidelineExceptionForecastRow]


@dataclass
class GuidelineExceptionMaturityForecastResult:
    """Prem-to-Maturity projection and its conditional 0-MD calculation.

    The Prem-to-Maturity solve identifies the first illustrated month in the GP
    exception-premium state. The table always shows this solved projection up to
    the target. ``zero_md`` is calculated only if that first status date is
    strictly before the target date.
    """

    premium: float
    premium_mode: str
    exception_start: date | None
    rows: list[GuidelineExceptionForecastRow]
    zero_md: GuidelineExceptionForecastResult | None
    current_glp: float = 0.0

    @property
    def exception_before_target(self) -> bool:
        return self.exception_start is not None and self.zero_md is not None


def project_guideline_exception_forecast(
    policy,
    target_date: date,
) -> GuidelineExceptionForecastResult:
    """Run the INPUT-to-MD ($0) guideline exception forecast to ``target_date``.

    Projects the policy on the INPUT-to-MD premium type (0 input premium,
    monthly Lumpsum-to-Next-Premium bridge, TEFRA enforcement OFF) so premiums
    are *not* restricted by the guideline, and returns the month-by-month rows
    (annotated with GLP / AccumGLP / PremTD / AccumWD / Policy Debt so the user
    can see how much room the AccumGLP needs) together with the adjustment
    summary.
    """
    ill_policy, valuation_date, premium_adjustment, months_to_target = (
        _prepare_projection(policy, target_date))

    return _project_input_to_md_forecast(
        policy,
        ill_policy,
        valuation_date,
        premium_adjustment,
        months_to_target,
        target_date,
    )


def _project_input_to_md_forecast(
    policy,
    ill_policy: IllustrationPolicyData,
    valuation_date: date,
    premium_adjustment: "PremiumAdjustmentSinceValuation",
    months_to_target: int,
    target_date: date,
) -> GuidelineExceptionForecastResult:
    """Build the 0-input-to-MD forecast from already-prepared policy data."""
    states = _run_input_to_md_states(ill_policy, months_to_target)
    total_premium_needed = sum(
        state.premium_outlay
        for state in states
        if state.date is not None and state.date < target_date
    )

    summary = _summarize(
        policy, valuation_date, target_date, months_to_target,
        premium_adjustment, total_premium_needed)

    rows = [
        _forecast_row(state)
        for state in states
        if state.date is not None and state.date <= target_date
    ]
    return GuidelineExceptionForecastResult(summary=summary, rows=rows)


def project_guideline_exception_maturity_forecast(
    policy,
    target_date: date,
) -> GuidelineExceptionMaturityForecastResult:
    """Project the Prem-to-Maturity solve through ``target_date``.

    The existing Prem-to-Maturity engine solve supplies the level premium and
    its guideline-conforming / exception-enabled basis. Its first exception
    month is the authoritative date for deciding whether the 0-MD calculation
    is relevant to this target.
    """
    ill_policy, valuation_date, premium_adjustment, months_to_target = (
        _prepare_projection(policy, target_date))
    engine = IllustrationEngine()

    allow_exceptions = not ill_policy.is_cvat
    try:
        solved = solve_level_to_exception(
            ill_policy,
            mode=None,
            start_policy_year=int(ill_policy.policy_year or 1),
            allow_exceptions=allow_exceptions,
            conform_to_tamra=not ill_policy.is_cvat,
            engine=engine,
        )
    except LevelToExceptionError as exc:
        raise ValueError(str(exc)) from exc

    future = IllustrationInputSet(scheduled_transactions=[
        ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=int(ill_policy.policy_year or 1),
            amount=solved.premium,
            mode=solved.mode,
        )
    ])
    options = level_to_exception_options(
        None,
        allow_exceptions=allow_exceptions,
        conform_to_tamra=not ill_policy.is_cvat,
    )
    states = engine.project(
        copy.deepcopy(ill_policy),
        options=options,
        future_inputs=future,
        months=months_to_target + 2,
        stop_on_lapse=False,
    )
    rows = [
        _forecast_row(state)
        for state in states
        if state.date is not None and state.date <= target_date
    ]
    exception_start = next(
        (row.date for row in rows if row.in_exception_mode),
        None,
    )

    zero_md = None
    if exception_start is not None and exception_start < target_date:
        # Entering the exception-premium period means the GLP is set to 0 going
        # forward, so the 0-MD forecast runs off a zero GLP (the AccumGLP no
        # longer grows at anniversaries) and the room is measured from there.
        zero_md_policy = copy.deepcopy(ill_policy)
        zero_md_policy.glp = 0.0
        zero_md = _project_input_to_md_forecast(
            policy,
            zero_md_policy,
            valuation_date,
            premium_adjustment,
            months_to_target,
            target_date,
        )

    return GuidelineExceptionMaturityForecastResult(
        premium=solved.premium,
        premium_mode=solved.mode,
        exception_start=exception_start,
        rows=rows,
        zero_md=zero_md,
        current_glp=_f(getattr(ill_policy, "glp", 0.0)),
    )


def _prepare_projection(
    policy,
    target_date: date,
) -> tuple[IllustrationPolicyData, date, "PremiumAdjustmentSinceValuation", int]:
    """Shared setup for the solve and the forecast.

    Gates availability, rolls the projection's starting state forward with
    premiums paid since the valuation date (mirrors the existing GLP-Exception
    solve so the two agree on the policy's current position), and computes the
    number of monthly deductions strictly before the target.
    """
    availability = check_forecast_availability(policy)
    if not availability.available or availability.policy is None:
        raise ValueError(availability.message)

    ill_policy = availability.policy
    valuation_date = ill_policy.valuation_date
    if valuation_date is None:
        raise ValueError("Current valuation date was not found")
    if target_date <= valuation_date:
        raise ValueError("Target inforce date must be after the current valuation date")

    premium_adjustment = _premium_adjustment_since_valuation(policy, valuation_date)
    ill_policy = _policy_with_post_valuation_premiums(ill_policy, premium_adjustment)

    months_to_target = _months_between_exclusive(valuation_date, target_date)
    if months_to_target <= 0:
        raise ValueError("Target date must leave at least one monthly deduction before the target")

    return ill_policy, valuation_date, premium_adjustment, months_to_target


def _summarize(
    policy,
    valuation_date: date,
    target_date: date,
    months_to_target: int,
    premium_adjustment: "PremiumAdjustmentSinceValuation",
    total_premium_needed: float,
    accum_glp: float | None = None,
    accum_wds: float | None = None,
) -> GuidelineExceptionAdjustmentResult:
    """Build the adjustment summary from the projected premium needed.

    ``room = max(0, AccumGLP - PremiumsPaidToDate + AccumWDs)`` — withdrawals
    create room — and ``adjustment = max(0, total_premium_needed - room)``. This
    is algebraically the single-formula form
    ``max(0, PremTD_on_target - AccumWDs - AccumGLP)``.

    ``accum_glp`` / ``accum_wds`` default to the policy's current DB2
    accumulators (the Targets-tab solve and the INPUT-to-MD forecast). The
    two-solve dual forecast passes the **projected** AccumGLP / AccumWD off the
    month before the target instead, so the guideline shown in the table (which
    evolves over the projection and absorbs any force-out into AccumWD) is the
    exact figure the adjustment is measured against.
    """
    if accum_glp is None:
        accum_glp = _f(getattr(policy, "accumulated_glp_target", None))
    if accum_wds is None:
        accum_wds = _f(getattr(policy, "total_withdrawals", None))
    # Premiums paid to date, brought current with post-valuation premiums — the
    # DB2 accumulator is as-of the valuation snapshot, so add anything paid since.
    premiums_paid = _f(getattr(policy, "premium_td", None)) + premium_adjustment.gross_premium

    room = max(0.0, accum_glp - premiums_paid + accum_wds)
    adjustment = max(0.0, total_premium_needed - room)
    message = (
        "No adjustment needed" if adjustment <= 0.0
        else f"Increase AccumGLP by {adjustment:,.2f}")

    return GuidelineExceptionAdjustmentResult(
        current_valuation_date=valuation_date,
        target_date=target_date,
        months_to_target=months_to_target,
        premiums_since_valuation_date=premium_adjustment.gross_premium,
        total_premium_needed=total_premium_needed,
        room_available=room,
        accumulated_glp=accum_glp,
        premiums_paid_to_date=premiums_paid,
        accumulated_withdrawals=accum_wds,
        adjustment_to_accum_glp=adjustment,
        new_accum_glp=accum_glp + adjustment,
        message=message,
    )


def _forecast_row(state) -> GuidelineExceptionForecastRow:
    """Map a projected :class:`MonthlyState` to a guideline forecast display row.

    ``premiums_to_date`` uses the *after-exception* accumulator so the
    Monthly-Deduction / GP-exception premiums the policy needed count toward the
    PremTD the guideline is measured against.
    """
    return GuidelineExceptionForecastRow(
        date=state.date,
        policy_year=int(getattr(state, "policy_year", 0) or 0),
        policy_month=int(getattr(state, "policy_month", 0) or 0),
        interest_credited=_f(getattr(state, "interest_credited", 0.0)),
        premium=_f(getattr(state, "premium_outlay", 0.0)),
        monthly_deduction=_f(getattr(state, "total_deduction", 0.0)),
        account_value=_f(getattr(state, "av_end_of_month", 0.0)),
        glp=_f(getattr(state, "glp", 0.0)),
        accumulated_glp=_f(getattr(state, "accumulated_glp", 0.0)),
        premiums_to_date=_f(getattr(state, "premiums_to_date_after_exception", 0.0)),
        accumulated_withdrawals=_f(getattr(state, "withdrawals_to_date", 0.0)),
        force_out=_f(getattr(state, "guideline_forceout", 0.0)),
        exception_premium=_f(getattr(state, "gp_exception_prem", 0.0)),
        in_exception_mode=bool(getattr(state, "exception_prem_mode", False)),
        policy_debt=_f(getattr(state, "policy_debt", 0.0)),
    )


def _run_input_to_md_states(
    policy: IllustrationPolicyData,
    months_to_target: int,
    engine: IllustrationEngine | None = None,
) -> list:
    """Project the INPUT-to-MD ($0) run past the target and return every state.

    Builds the INPUT-to-MD run (input premium 0, monthly, Lumpsum-to-Next-Premium
    bridge, TEFRA off) and projects two months past the target so the target-date
    row itself is available for display.
    """
    return _run_forecast_states(
        policy, months_to_target, _input_to_md_run, engine=engine)


def _run_forecast_states(
    policy: IllustrationPolicyData,
    months_to_target: int,
    run_builder,
    engine: IllustrationEngine | None = None,
) -> list:
    """Project a GLP-Exception run built by ``run_builder`` and return the states.

    ``run_builder(policy) -> (future_inputs, options)`` supplies the premium
    schedule and options (the INPUT-to-MD run). The Lumpsum-to-Next-Premium
    bridge is layered on afterwards, forced to a monthly cadence. Projects two
    months past the target so the target-date row is available for display.
    """
    engine = engine or IllustrationEngine()

    run_policy = copy.deepcopy(policy)
    future, options = run_builder(run_policy)
    future, options = _apply_lumpsum_to_next(
        run_policy, future, options, engine, force_monthly=True)

    return engine.project(
        copy.deepcopy(run_policy),
        options=options,
        future_inputs=future,
        months=months_to_target + 2,
        stop_on_lapse=False,
    )


def _input_to_md_run(
    policy: IllustrationPolicyData,
) -> tuple[IllustrationInputSet, IllustrationOptions]:
    """Future inputs + options for an INPUT-to-MD run with a 0 input premium.

    Silences the default modal billing (input premium is 0) and lets the engine
    hand off from the (zero) premium to the Monthly Deduction premium — then GP
    exceptions — across the whole remaining policy life. TEFRA enforcement is
    OFF so the guideline never caps the Monthly Deduction premium: the outlay is
    the raw premium the policy needs to stay in force.
    """
    issue_age = int(policy.issue_age or 0)
    maturity_age = int(policy.maturity_age or 121)
    forecast_year = int(policy.policy_year or 1)
    maturity_year = max(1, maturity_age - issue_age)

    scheduled = [ScheduledTransaction(
        kind=TransactionKind.PREMIUM, policy_year=forecast_year,
        amount=0.0, mode="A")]
    future = IllustrationInputSet(scheduled_transactions=scheduled)
    options = IllustrationOptions(
        # TEFRA limit enforcement OFF — the whole point of the solve is to size
        # the premium the policy needs regardless of the guideline cap.
        conform_to_tefra=False,
        conform_to_tamra=False,
        # INPUT to MD always allows GP exceptions — the billable → MD → exception
        # sequence is the mechanism.
        allow_exception_prems=True,
        billable_to_md_windows=[(forecast_year, maturity_year)],
    )
    return future, options


def _apply_lumpsum_to_next(
    policy: IllustrationPolicyData,
    future: IllustrationInputSet,
    options: IllustrationOptions,
    engine: IllustrationEngine,
    force_monthly: bool = True,
) -> tuple[IllustrationInputSet, IllustrationOptions]:
    """Solve the Lumpsum-to-Next-Premium bridge and layer it in.

    Bridges the policy from the valuation date up to its next premium, funding
    the policy until then and suppressing the MD hand-off until that premium —
    mirroring the Billable-to-MD batch run. ``force_monthly`` forces a monthly
    cadence for the bridge (the $0 → MD solve's "mode beginning monthly"); the
    level-premium run passes ``False`` so the bridge targets the next premium on
    the policy's own mode. A failed or unneeded bridge leaves the run unchanged.
    """
    from dataclasses import replace

    from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
        LUMPSUM_SUBTYPE,
        solve_lumpsum_to_next_premium,
    )

    bridge_policy = copy.deepcopy(policy)
    if force_monthly:
        bridge_policy.billing_frequency = 1  # monthly cadence for the bridge

    try:
        lump = solve_lumpsum_to_next_premium(
            bridge_policy,
            base_future_inputs=future,
            base_options=options,
            engine=engine)
    except Exception:  # bridge solve failed — run without it
        lump = None

    if lump is None or lump.lumpsum <= 0:
        return future, options

    dated = list(future.dated_transactions)
    dated.append(DatedTransaction(
        kind=TransactionKind.PREMIUM,
        effective_date=lump.forecast_date,
        amount=lump.lumpsum,
        subtype=LUMPSUM_SUBTYPE))
    future = IllustrationInputSet(
        scheduled_transactions=list(future.scheduled_transactions),
        dated_transactions=dated,
        policy_changes=list(future.policy_changes))
    options = replace(options, billable_to_md_no_latch_before=lump.next_premium_date)
    return future, options


def _f(value) -> float:
    """Coerce a possibly-Decimal / None DB value to float."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
