"""Guideline Exception Adjustment calculations.

The Policy Support GLP Exception window exists to decide one thing: must this
policy's AccumGLP be raised to make room for GP exception premiums before a
target date? It answers that by solving the **minimum level premium that keeps
the policy in force through the target date** — $0 if the account value alone
carries it, a positive premium if the policy needs funding — and then reading
whether that cheapest path fires a GP exception premium. A second independent
minimum-premium solve always runs with starting GLP=0, preserving guideline
enforcement. Its outlay sizes the adjustment only if the original needs exceptions.
A third independent GLP=0 solve suppresses only forceouts, for comparison;
it never determines the recommended adjustment.

For negative opening AV, solve a one-time initial bridge first, then minimize
the ongoing modal premium with that first-payment funding floor. Only the
excess over the scheduled first payment is a lump sum; it is never repeated.

Solving to the target date (not to maturity) is the point: a maturity solve
answers "what premium sustains this policy forever", which can demand guideline
room the policy never actually needs by the target.

Room and adjustment:

* ``room = max(0, AccumGLP - PremiumsPaidToDate + AccumWDs)`` — the same
  "Prem Allowed by GPT" figure shown on the Targets & Accumulators tab, but with
  the valuation-date ``PremiumsPaidToDate``. Later financial history is not
  injected into an earlier snapshot.
* ``total_premium_needed`` — the gross premium actually paid into the policy
  (ordinary + exception premiums, not loan repayments), summed for
  every projected month **strictly before** the target date (the target date
  itself is excluded).
* ``adjustment_to_accum_glp = max(0, PremiumsPaidToDate + total_premium_needed
  - AccumWDs - AccumGLP)`` — the increase needed to admit that premium,
  including any existing excess above the current AccumGLP.

This is a single-target-date solve: it uses the policy's current AccumGLP and
does not chain intermediate anniversary adjustments.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta

from suiteview.illustration.api import project_policy
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.input_compiler import compile_month_inputs
from suiteview.illustration.core.solve_level_to_exception import (
    LevelToExceptionError,
    default_premium_mode,
    level_to_exception_inputs,
    level_to_exception_options,
    solve_level_to_exception,
)
from suiteview.illustration.models.input_set import IllustrationOptions
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.illustration.models.calc_state import MonthlyState

from .glp_exception import (
    check_forecast_availability,
)
from suiteview.polview.models.policy_sections.lookup import policy_attr


@dataclass
class GuidelineExceptionAdjustmentResult:
    """Outcome of a Guideline Exception Adjustment solve."""

    current_valuation_date: date | None
    target_date: date
    months_to_target: int
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
    """Forecast amounts plus the full engine state for the shared values ledger."""

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
    surrender_value: float = 0.0
    state: MonthlyState | None = None


@dataclass
class GuidelineExceptionZeroGlpForecastResult:
    """Independently solved GLP=0 scenario, retaining the original GP accumulators."""

    summary: GuidelineExceptionAdjustmentResult
    rows: list[GuidelineExceptionForecastRow]
    premium: float
    premium_mode: str
    exception_start: date | None
    lump_sum: float = 0.0
    lump_sum_date: date | None = None


@dataclass
class GuidelineExceptionTargetForecastResult:
    """Min-premium-to-target projection and two always-available GLP=0 solves.

    ``premium`` is the **minimum** ongoing level premium (on the policy's billing mode)
    that keeps the policy in force through the target date — $0 when the account
    value alone carries it that far. Solving the least the policy must take in is
    what makes the exception test meaningful: if even the cheapest way to stay in
    force needs a GP exception premium, the AccumGLP genuinely has to be opened
    up; if it does not, no adjustment is warranted.

    ``exception_start`` is the first illustrated month of that projection in the
    GP exception-premium state strictly before the target. ``zero_glp`` is
    independently calculated whether or not the original needs exceptions.
    ``no_forceout`` independently solves GLP=0 with only forceouts disabled;
    its summary is comparison-only, not the recommended adjustment.
    ``lump_sum`` is the accepted one-time top-up on ``lump_sum_date``, in addition
    to any ongoing premium due that month, already included in the ledger outlay.
    """

    premium: float
    premium_mode: str
    exception_start: date | None
    rows: list[GuidelineExceptionForecastRow]
    zero_glp: GuidelineExceptionZeroGlpForecastResult
    no_forceout: GuidelineExceptionZeroGlpForecastResult
    current_glp: float = 0.0
    lump_sum: float = 0.0
    lump_sum_date: date | None = None

    @property
    def exception_before_target(self) -> bool:
        return self.exception_start is not None


def project_guideline_exception_target_forecast(
    policy,
    target_date: date,
) -> GuidelineExceptionTargetForecastResult:
    """Solve the minimum premium that holds the policy to ``target_date``.

    The screen exists to answer one question: does this policy need GP exception
    premiums before the target date, and therefore AccumGLP room to accept them?
    So the solve horizon is the **target date**, not maturity. The minimum level
    premium that keeps the policy in force that far lands in one of three places:

    * **$0** — the account value alone carries the policy to the target.
    * **a positive premium inside the guideline** — fundable out of the
      remaining AccumGLP room, so no exception and no adjustment.
    * **a premium that exhausts the room** — the engine then fires GP exception
      premiums, and the AccumGLP must be opened up to admit them.

    Only the third case warrants adjustment from the GLP=0 scenario.
    Solving the *minimum* is what makes that test fair: a
    larger premium could hit the guideline for reasons the policy never actually
    has to incur.
    """
    ill_policy, valuation_date, months_to_target = (
        _prepare_projection(policy, target_date))
    solved, rows, exception_start, lump_sum, lump_sum_date = _solve_and_project_target(
        ill_policy, months_to_target, target_date)
    zero_glp_policy = copy.deepcopy(ill_policy)
    zero_glp_policy.glp = 0.0
    zero_solved, zero_rows, zero_exception_start, zero_lump, zero_lump_date = _solve_and_project_target(
        zero_glp_policy, months_to_target, target_date)
    summary = _summarize(
        policy, valuation_date, target_date, months_to_target,
        sum(row.premium for row in zero_rows),
    )
    no_forceout_solved, no_forceout_rows, no_forceout_exception_start, no_forceout_lump, no_forceout_lump_date = (
        _solve_and_project_target(
            zero_glp_policy, months_to_target, target_date,
            guideline_forceouts=False))
    return GuidelineExceptionTargetForecastResult(
        premium=solved.premium,
        premium_mode=solved.mode,
        exception_start=exception_start,
        rows=rows,
        lump_sum=lump_sum, lump_sum_date=lump_sum_date,
        zero_glp=GuidelineExceptionZeroGlpForecastResult(
            summary=summary, rows=zero_rows, premium=zero_solved.premium,
            premium_mode=zero_solved.mode, exception_start=zero_exception_start,
            lump_sum=zero_lump, lump_sum_date=zero_lump_date),
        no_forceout=GuidelineExceptionZeroGlpForecastResult(
            summary=_summarize(
                policy, valuation_date, target_date, months_to_target,
                sum(row.premium for row in no_forceout_rows)),
            rows=no_forceout_rows, premium=no_forceout_solved.premium,
            premium_mode=no_forceout_solved.mode,
            exception_start=no_forceout_exception_start,
            lump_sum=no_forceout_lump, lump_sum_date=no_forceout_lump_date),
        current_glp=_f(ill_policy.glp),
    )


def _solve_and_project_target(
    policy: IllustrationPolicyData, months_to_target: int, target_date: date,
    *, guideline_forceouts: bool = True,
):
    """Use the same scenario basis in each independent solve and displayed run."""
    ill_policy = copy.deepcopy(policy)
    engine = IllustrationEngine()

    allow_exceptions = not ill_policy.is_cvat
    # Match RERUN's unchecked Exact Days Interest control: monthly compounding.
    base_options = IllustrationOptions(
        exact_days_interest=False, guideline_forceouts=guideline_forceouts,
        recognize_inforce_exception_period=False)
    first_month_floor = 0.0
    try:
        if ill_policy.account_value < 0 and months_to_target > 0:
            cadence = default_premium_mode(ill_policy)
            schedule = level_to_exception_inputs(
                ill_policy, 1.0, cadence, int(ill_policy.policy_year or 1))
            compiled = compile_month_inputs(ill_policy, schedule, months_to_target)
            bridge_months = next(
                (offset - 1 for offset in range(2, months_to_target + 1)
                 if compiled[ill_policy.duration + offset].scheduled_premium),
                months_to_target)
            initial = solve_level_to_exception(
                ill_policy, mode=cadence,
                start_policy_year=int(ill_policy.policy_year or 1),
                allow_exceptions=allow_exceptions,
                conform_to_tamra=not ill_policy.is_cvat,
                horizon_months=bridge_months, fund_transition_cleanly=False,
                base_options=base_options, engine=engine,
                single_premium=True,
            )
            first_month_floor = initial.premium
        solved = solve_level_to_exception(
            ill_policy,
            mode=None,
            start_policy_year=int(ill_policy.policy_year or 1),
            allow_exceptions=allow_exceptions,
            conform_to_tamra=not ill_policy.is_cvat,
            horizon_months=months_to_target,
            fund_transition_cleanly=False,
            base_options=base_options,
            engine=engine,
            first_month_premium_floor=first_month_floor,
        )
    except LevelToExceptionError as exc:
        raise ValueError(str(exc)) from exc

    options = level_to_exception_options(
        base_options,
        allow_exceptions=allow_exceptions,
        conform_to_tamra=not ill_policy.is_cvat,
    )
    # An explicit zero overrides billing; an empty input set bills modal_premium.
    future = level_to_exception_inputs(
        ill_policy, solved.premium, solved.mode, int(ill_policy.policy_year or 1),
        first_month_premium_floor=first_month_floor,
    )
    projection_overrides = {}
    if not ill_policy.plancode:
        from suiteview.illustration.core.rate_loader import IllustrationRates
        from suiteview.illustration.models.plancode_config import PlancodeConfig
        projection_overrides = {
            "config": PlancodeConfig(),
            "rates": IllustrationRates(),
        }
    states = project_policy(
        copy.deepcopy(ill_policy),
        options=options,
        inputs=future,
        months=months_to_target,
        engine=engine,
        **projection_overrides,
    ).states
    rows = [
        _forecast_row(state)
        for state in states
        if state.date is not None and state.date < target_date
    ]
    exception_start = next(
        (row.date for row in rows if row.exception_premium > 0.0),
        None,
    )

    lump_sum = sum(getattr(row.state, "applied_lumpsum", 0.0) for row in rows)
    lump_sum_date = next(
        (row.date for row in rows if getattr(row.state, "applied_lumpsum", 0.0) > 0), None)
    return solved, rows, exception_start, lump_sum, lump_sum_date


def _prepare_projection(
    policy,
    target_date: date,
) -> tuple[IllustrationPolicyData, date, int]:
    """Shared setup for the solve and the forecast.

    Preserve the same valuation-date snapshot RERUN loads: account value is
    already after the valuation month's deduction. Later receipts must not be
    backdated into that AV or its premium/cost-basis accumulators.
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

    if ill_policy.issue_date is None:
        raise ValueError("Issue date is required to determine the monthly deduction dates")
    months_to_target = 0
    while (ill_policy.issue_date + relativedelta(
            months=ill_policy.duration + months_to_target)) < target_date:
        months_to_target += 1

    return ill_policy, valuation_date, months_to_target


def _summarize(
    policy,
    valuation_date: date,
    target_date: date,
    months_to_target: int,
    total_premium_needed: float,
) -> GuidelineExceptionAdjustmentResult:
    """Build the adjustment summary from the projected premium needed.

    Withdrawals create room. The adjustment is
    ``max(0, PremTD_on_target - AccumWDs - AccumGLP)``; do not subtract the
    clamped room from the new premium, which would lose any existing excess.

    The exception adjustment uses current AccumGLP and withdrawals, with
    future GLP set to zero.
    """
    accum_glp = _f(policy_attr(policy, "accumulated_glp_target", None))
    accum_wds = _f(policy_attr(policy, "total_withdrawals", None))
    premiums_paid = _f(policy_attr(policy, "premium_td", None))

    room = max(0.0, accum_glp - premiums_paid + accum_wds)
    adjustment = max(0.0, premiums_paid + total_premium_needed - accum_wds - accum_glp)
    message = (
        "No adjustment needed" if adjustment <= 0.0
        else f"Increase AccumGLP by {adjustment:,.2f}")

    return GuidelineExceptionAdjustmentResult(
        current_valuation_date=valuation_date,
        target_date=target_date,
        months_to_target=months_to_target,
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
        surrender_value=_f(getattr(state, "ending_sv", 0.0)),
        state=state,
    )


def _f(value) -> float:
    """Coerce a possibly-Decimal / None DB value to float."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
