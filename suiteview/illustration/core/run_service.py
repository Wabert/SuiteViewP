"""Pure Run Values orchestration for the Illustration UI.

The UI owns widgets, cursors and dialogs; this module owns the deterministic
business pipeline.  A :class:`RunRequest` carries a frozen policy basis, compiled
inputs, controls and solve requests.  :func:`execute_run` returns a
plain :class:`RunResult` that the presenter/window can render.

Solve order is intentionally documented and preserved from the original
``_on_run_values`` flow:

1. ABR Quote short-circuits the illustration report.
2. Lumpsum-to-next-premium bridges early lapse before later premium solves.
3. Max Level solves guideline room and layers the solved premium.
4. Prem to Maturity solves minimum level premium to maturity.
5. Prem to Shadow Maturity solves on the shadow-account lapse basis.
6. Target premium solves the amount needed for a target value/age.
7. Duration solves how long an entered premium should run.
8. Loan payoff solves repayment rows in chronological order.
9. Current projection, guaranteed projection and report construction run last.
"""

from __future__ import annotations

import copy
import logging
import platform
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Callable, Optional

from suiteview.illustration.api import project_policy
from suiteview.illustration.core.abr_quote import run_abr_quote
from suiteview.illustration.core.business_mode import is_business_mode
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.deemed_cash_value import DCV_DEFAULTED_NOTICE, dcv_defaulted
from suiteview.illustration.core.face_minimum import min_face_notices
from suiteview.illustration.core.guaranteed_projection import run_guaranteed_projection
from suiteview.illustration.core.report_builder import IllustrationReport, build_ul_report
from suiteview.illustration.core.request_limits import reduced_request_warnings
from suiteview.illustration.core.run_gates import (
    GATE_TITLE,
    GateResult,
    rate_presence_gate,
    run_gate,
)
from suiteview.illustration.core.scenario_builder import build_illustration_scenario
from suiteview.illustration.core.solve_level_to_exception import (
    LevelToExceptionError,
    level_to_exception_options,
    solve_level_to_exception,
)
from suiteview.illustration.core.solve_loan_payoff import (
    PAYOFF_SUBTYPE,
    LoanPayoffError,
    solve_loan_payoff,
)
from suiteview.illustration.core.solve_lumpsum_to_next_premium import (
    solve_lumpsum_to_next_premium,
)
from suiteview.illustration.core.solve_max_level_allowed import (
    MaxLevelAllowedError,
    solve_max_level_allowed,
)
from suiteview.illustration.core.solve_premium_duration import solve_premium_duration
from suiteview.illustration.core.solve_premium_to_target import (
    TARGET_FIELDS,
    PremiumTargetError,
    solve_premium_to_target,
)
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import (
    DatedTransaction,
    IllustrationInputSet,
    IllustrationOptions,
    IssueOverrideSet,
    RollbackOverrideSet,
    ScheduledTransaction,
    TransactionKind,
)

logger = logging.getLogger(__name__)

_STATUS_DATE_FMT = "%#m/%d/%Y" if platform.system() == "Windows" else "%-m/%d/%Y"


@dataclass(frozen=True)
class PolicyBasis:
    """Policy source for a run.

    ``policy_data`` means the caller already has a loaded or frozen
    :class:`IllustrationPolicyData` basis and the service must not retrieve live
    data.  When it is ``None``, ``project_policy(..., months=0)`` loads the
    current basis through the documented façade.
    """

    policy_number: str
    region: str = "CKPR"
    company_code: str = ""
    policy_data: object | None = None
    snapshot_status: str = ""


@dataclass(frozen=True)
class RunControls:
    """Compiled non-solver controls for one Run Values click."""

    options: IllustrationOptions
    projection_months: int | None
    duration_label: str | None
    stop_on_lapse: bool
    run_from_issue: bool = False
    abr_quote: bool = False
    abr_minimum_face_amount: float | None = None
    projection_months_for_policy: Callable[[object], int] | None = field(
        default=None, compare=False, repr=False)
    duration_label_for_policy: Callable[[object], str] | None = field(
        default=None, compare=False, repr=False)
    run_date: date = field(default_factory=date.today)
    rollback_status: str = ""


@dataclass(frozen=True)
class SolveRequestSet:
    """Optional premium/loan solve requests, in the documented solve order."""

    lumpsum_to_next: bool = False
    max_level: Optional[dict] = None
    min_level: Optional[dict] = None
    shadow_level: Optional[dict] = None
    target_premium: Optional[dict] = None
    duration: Optional[dict] = None
    loan_payoffs: tuple[dict, ...] = ()


@dataclass(frozen=True)
class RunRequest:
    """Complete, widget-free Run Values request."""

    basis: PolicyBasis
    inputs: IllustrationInputSet
    controls: RunControls
    solves: SolveRequestSet
    inforce_overrides: object | None = None
    issue_overrides: IssueOverrideSet | None = None
    rollback_overrides: RollbackOverrideSet | None = None


@dataclass(frozen=True)
class EngineServices:
    """Injectable service functions for tests and offline characterization."""

    project: Callable = field(default_factory=lambda: project_policy)
    scenario_builder: Callable = field(default_factory=lambda: build_illustration_scenario)
    engine_factory: Callable[[], IllustrationEngine] = field(
        default_factory=lambda: IllustrationEngine)
    report_builder: Callable[..., IllustrationReport] = field(default_factory=lambda: build_ul_report)
    abr_quote_runner: Callable = field(default_factory=lambda: run_abr_quote)
    guaranteed_runner: Callable = field(default_factory=lambda: run_guaranteed_projection)
    business_mode: Callable[[], bool] = field(default_factory=lambda: is_business_mode)
    # Rate-presence check for business runs; None uses run_gates.missing_rate_findings.
    missing_rates: Callable | None = None


@dataclass
class SolvedInputs:
    """Solved values the UI should render back into its draft widgets."""

    lumpsum_amount: float | None = None
    max_level_amount: float | None = None
    min_level_amount: float | None = None
    shadow_level_amount: float | None = None
    target_amount: float | None = None
    duration_years: int | None = None
    loan_payoff_amounts: list[float] | None = None


@dataclass(frozen=True)
class ReportResult:
    """Report payload plus non-fatal guaranteed-side failure text."""

    report: IllustrationReport | None
    guaranteed_error: str | None = None


@dataclass(frozen=True)
class RunResult:
    """Plain output from a Run Values execution."""

    policy: object
    scenario: object | None
    current: list[MonthlyState]
    guaranteed: list[MonthlyState] | None
    solved_inputs: SolvedInputs
    report: ReportResult
    messages: list[str]
    abr_quote: object | None = None
    lumpsum_result: object | None = None
    duration_label: str = ""
    # Non-blocking notices the user must see (gate warnings, reduced requests).
    warnings: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        return self.messages[-1] if self.messages else ""


class RunFlowError(Exception):
    """Expected user-facing stop in the Run Values pipeline."""

    def __init__(self, title: str, message: str, *, clear_field: str | None = None):
        super().__init__(message)
        self.title = title
        self.message = message
        self.clear_field = clear_field


@dataclass(frozen=True)
class PreparedPolicyData:
    policy_data: object


@dataclass(frozen=True)
class RunScenario:
    scenario: object
    projection_months: int
    duration_label: str


@dataclass(frozen=True)
class ResolvedRunInputs:
    future_inputs: IllustrationInputSet
    options: IllustrationOptions
    solved_inputs: SolvedInputs
    messages: list[str]
    lumpsum_result: object | None = None


def execute_run(request: RunRequest, services: EngineServices | None = None) -> RunResult:
    """Run the illustration flow without touching Qt widgets."""

    services = services or EngineServices()
    prepared = prepare_policy_data(request, services)
    gate = check_run_gates(request, prepared, services)
    scenario = build_run_scenario(request, prepared, services)
    engine = services.engine_factory()
    if request.controls.abr_quote:
        result = _execute_abr_quote(request, scenario, engine, services)
        return replace(result, warnings=gate.warnings)
    resolved = resolve_solved_inputs(request, scenario, engine)
    current = run_current_projection(request, scenario, resolved, engine, services)
    guaranteed, guaranteed_error = run_guaranteed_projection_safe(
        request, scenario, current, resolved, engine, services)
    report = build_report_result(
        request, scenario, current, resolved, guaranteed, guaranteed_error, services)
    status = _final_status(request, scenario, current, guaranteed_error, resolved.lumpsum_result)
    return RunResult(
        policy=scenario.scenario.projectable_policy,
        scenario=scenario.scenario,
        current=current,
        guaranteed=guaranteed,
        solved_inputs=resolved.solved_inputs,
        report=report,
        messages=[*resolved.messages, status],
        lumpsum_result=resolved.lumpsum_result,
        duration_label=scenario.duration_label,
        warnings=gate.warnings + _reduced_request_warnings(scenario, resolved, current),
    )


def _reduced_request_warnings(
    run_scenario: RunScenario,
    resolved: ResolvedRunInputs,
    current: list[MonthlyState],
) -> tuple[str, ...]:
    """Withdrawal/loan requests the engine reduced (never fails the run)."""
    try:
        return tuple(reduced_request_warnings(
            run_scenario.scenario.projectable_policy, resolved.future_inputs, current))
    except Exception:
        logger.exception("Could not check for reduced withdrawal/loan requests")
        return ()


def check_run_gates(
    request: RunRequest,
    prepared: PreparedPolicyData,
    services: EngineServices,
) -> GateResult:
    """Apply the soft-launch gates to every run (saved/imported cases included).

    Business users are refused out-of-scope policies and developer-only run
    modes with a :class:`RunFlowError`; developers get the same findings back
    as warnings.
    """
    business = bool(services.business_mode())
    if business:
        controls = request.controls
        refused = [
            label for label, used in (
                ("New Business - From Issue", controls.run_from_issue),
                ("ABR Quote", controls.abr_quote),
                ("Edit Record", request.rollback_overrides is not None),
            ) if used
        ]
        if refused:
            raise RunFlowError(
                GATE_TITLE,
                f"{', '.join(refused)} is not available to business users.")
    # ABR Quote (developer only) deliberately solves at any rate: no rate cap.
    overrides = None if request.controls.abr_quote else request.inforce_overrides
    gate = run_gate(prepared.policy_data, overrides, business_mode=business)
    if gate.blocked:
        raise RunFlowError(GATE_TITLE, "\n\n".join(gate.blocks))
    rates = rate_presence_gate(
        prepared.policy_data, business_mode=business, findings_for=services.missing_rates)
    if rates.blocked:
        raise RunFlowError(GATE_TITLE, "\n\n".join(rates.blocks))
    return gate


def prepare_policy_data(request: RunRequest, services: EngineServices) -> PreparedPolicyData:
    """Load or copy the policy basis for a run."""

    if request.basis.policy_data is not None:
        return PreparedPolicyData(copy.deepcopy(request.basis.policy_data))
    policy = services.project(
        request.basis.policy_number,
        region=request.basis.region,
        company_code=request.basis.company_code,
        months=0,
    ).policy
    return PreparedPolicyData(policy)


def build_run_scenario(
    request: RunRequest,
    prepared: PreparedPolicyData,
    services: EngineServices,
) -> RunScenario:
    """Apply inforce, issue-mode and rollback basis assumptions."""

    scenario_args = {
        "inforce_overrides": request.inforce_overrides,
        "future_inputs": request.inputs,
    }
    if request.controls.run_from_issue:
        scenario_args["run_from_issue"] = True
        scenario_args["issue_overrides"] = request.issue_overrides
    if request.rollback_overrides is not None:
        scenario_args["rollback_overrides"] = request.rollback_overrides
    scenario = services.scenario_builder(prepared.policy_data, **scenario_args)
    months = request.controls.projection_months
    if months is None:
        if request.controls.projection_months_for_policy is None:
            raise ValueError("RunControls must provide projection months or a policy callback.")
        months = request.controls.projection_months_for_policy(scenario.projectable_policy)
    duration_label = request.controls.duration_label
    if duration_label is None:
        if request.controls.duration_label_for_policy is None:
            raise ValueError("RunControls must provide duration label or a policy callback.")
        duration_label = request.controls.duration_label_for_policy(scenario.projectable_policy)
    return RunScenario(
        scenario=scenario,
        projection_months=months,
        duration_label=duration_label,
    )


def resolve_solved_inputs(
    request: RunRequest,
    run_scenario: RunScenario,
    engine: IllustrationEngine,
) -> ResolvedRunInputs:
    """Resolve optional solve rows in the documented order."""

    scenario = run_scenario.scenario
    future_inputs = scenario.future_inputs
    run_options = request.controls.options
    solved = SolvedInputs()
    messages: list[str] = []
    lumpsum_result = None

    if request.solves.lumpsum_to_next:
        result = _resolve_lumpsum_to_next(
            request, scenario, future_inputs, run_options, engine)
        future_inputs = result.future_inputs
        run_options = result.options
        lumpsum_result = result.lumpsum_result
        solved.lumpsum_amount = (
            0.0 if lumpsum_result is None else float(lumpsum_result.lumpsum or 0.0)
        )

    if request.solves.max_level is not None:
        result = _resolve_max_level(
            request.solves.max_level, scenario, future_inputs, run_options, engine)
        future_inputs = result.future_inputs
        run_options = result.options
        solved.max_level_amount = result.solved_inputs.max_level_amount

    if request.solves.min_level is not None:
        result = _resolve_min_level(
            request.solves.min_level, scenario, future_inputs, run_options)
        future_inputs = result.future_inputs
        run_options = result.options
        solved.min_level_amount = result.solved_inputs.min_level_amount

    if request.solves.shadow_level is not None:
        result = _resolve_shadow_level(
            request.solves.shadow_level, scenario, future_inputs, run_options)
        future_inputs = result.future_inputs
        run_options = result.options
        solved.shadow_level_amount = result.solved_inputs.shadow_level_amount

    if request.solves.target_premium is not None:
        result = _resolve_target_premium(
            request.solves.target_premium, scenario, future_inputs, run_options, engine)
        future_inputs = result.future_inputs
        solved.target_amount = result.solved_inputs.target_amount
        messages.extend(result.messages)

    if request.solves.duration is not None:
        result = _resolve_duration(
            request.solves.duration, scenario, future_inputs, run_options, engine)
        future_inputs = result.future_inputs
        solved.duration_years = result.solved_inputs.duration_years
        messages.extend(result.messages)

    if request.solves.loan_payoffs:
        result = _resolve_loan_payoffs(
            request.solves.loan_payoffs, scenario, future_inputs, run_options, engine)
        future_inputs = result.future_inputs
        solved.loan_payoff_amounts = result.solved_inputs.loan_payoff_amounts

    return ResolvedRunInputs(future_inputs, run_options, solved, messages, lumpsum_result)


def run_current_projection(
    request: RunRequest,
    run_scenario: RunScenario,
    resolved: ResolvedRunInputs,
    engine: IllustrationEngine,
    services: EngineServices,
) -> list[MonthlyState]:
    """Run the current/non-guaranteed projection."""

    return services.project(
        run_scenario.scenario.projectable_policy,
        months=run_scenario.projection_months,
        inputs=resolved.future_inputs,
        options=resolved.options,
        stop_on_lapse=request.controls.stop_on_lapse,
        engine=engine,
    ).states


def run_guaranteed_projection_safe(
    request: RunRequest,
    run_scenario: RunScenario,
    current: list[MonthlyState],
    resolved: ResolvedRunInputs,
    engine: IllustrationEngine,
    services: EngineServices,
) -> tuple[list[MonthlyState] | None, str | None]:
    """Run guaranteed values; return a warning instead of failing the run."""

    try:
        return (
            services.guaranteed_runner(
                run_scenario.scenario.projectable_policy,
                current,
                base_options=resolved.options,
                base_future_inputs=resolved.future_inputs,
                engine=engine,
            ),
            None,
        )
    except Exception as exc:
        guaranteed_error = str(exc) or type(exc).__name__
        logger.error(
            "Guaranteed projection failed for %s: %s",
            request.basis.policy_number,
            guaranteed_error,
            exc_info=True,
        )
        return None, guaranteed_error


def build_report_result(
    request: RunRequest,
    run_scenario: RunScenario,
    current: list[MonthlyState],
    resolved: ResolvedRunInputs,
    guaranteed: list[MonthlyState] | None,
    guaranteed_error: str | None,
    services: EngineServices,
) -> ReportResult:
    """Build the report dataclass for the current run."""

    report = services.report_builder(
        run_scenario.scenario.projectable_policy,
        current,
        options=resolved.options,
        future_inputs=resolved.future_inputs,
        run_date=request.controls.run_date,
        guaranteed_results=guaranteed,
    )
    return ReportResult(report, guaranteed_error)


@dataclass(frozen=True)
class _ResolveStep:
    future_inputs: IllustrationInputSet
    options: IllustrationOptions
    solved_inputs: SolvedInputs = field(default_factory=SolvedInputs)
    messages: list[str] = field(default_factory=list)
    lumpsum_result: object | None = None


def _execute_abr_quote(
    request: RunRequest,
    run_scenario: RunScenario,
    engine: IllustrationEngine,
    services: EngineServices,
) -> RunResult:
    minimum_face_amount = request.controls.abr_minimum_face_amount
    if minimum_face_amount is None:
        raise RunFlowError(
            "ABR Quote",
            "Enter the Minimum Face Amount Allowed on the Illustration Control tab.",
        )
    try:
        abr = services.abr_quote_runner(
            run_scenario.scenario.projectable_policy,
            minimum_face_amount=minimum_face_amount,
            base_options=request.controls.options,
            engine=engine,
        )
    except (PremiumTargetError, ValueError) as exc:
        raise RunFlowError("ABR Quote", str(exc)) from exc
    status = (
        f"ABR Quote for {request.basis.policy_number}: solved annual premium "
        f"{abr.premium:,.2f} at {abr.illustrated_rate * 100.0:.3f}% "
        f"using the lower {abr.premium_basis} account solve; next "
        f"monthly deduction at the minimum face is "
        f"${abr.max_partial.monthly_deduction:,.2f} on "
        f"{abr.max_partial.monthly_deduction_date:%m/%d/%Y} — see "
        f"the Report tab for details."
    )
    if request.basis.snapshot_status:
        status += f"  ·  {request.basis.snapshot_status}"
    return RunResult(
        policy=abr.policy,
        scenario=run_scenario.scenario,
        current=abr.results,
        guaranteed=None,
        solved_inputs=SolvedInputs(),
        report=ReportResult(None),
        messages=[status],
        abr_quote=abr,
        duration_label=run_scenario.duration_label,
    )


def _resolve_lumpsum_to_next(
    request: RunRequest,
    scenario,
    future_inputs: IllustrationInputSet,
    run_options: IllustrationOptions,
    engine: IllustrationEngine,
) -> _ResolveStep:
    follow_on_premium = None
    level_req = (
        request.solves.min_level
        or request.solves.max_level
        or request.solves.shadow_level
    )
    if level_req is not None:
        follow_on_premium = ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=int(level_req["start_year"]),
            amount=0.0,
            mode=level_req.get("mode") or "",
        )
    result = solve_lumpsum_to_next_premium(
        scenario.projectable_policy,
        base_future_inputs=future_inputs,
        base_options=run_options,
        engine=engine,
        follow_on_premium=follow_on_premium,
    )
    if result is not None and result.lumpsum > 0:
        dated = list(future_inputs.dated_transactions)
        dated.append(DatedTransaction(
            kind=TransactionKind.PREMIUM,
            effective_date=result.forecast_date,
            amount=result.lumpsum,
            subtype="lumpsum_to_next_premium",
        ))
        future_inputs = _replace_inputs(future_inputs, dated_transactions=dated)
        if run_options.billable_to_md_windows:
            run_options = replace(
                run_options,
                billable_to_md_no_latch_before=result.next_premium_date,
            )
    return _ResolveStep(
        future_inputs=future_inputs,
        options=run_options,
        lumpsum_result=result,
    )


def _resolve_max_level(
    max_level: dict,
    scenario,
    future_inputs: IllustrationInputSet,
    run_options: IllustrationOptions,
    engine: IllustrationEngine,
) -> _ResolveStep:
    allow_exceptions = bool(run_options.allow_exception_prems)
    try:
        solved = solve_max_level_allowed(
            scenario.projectable_policy,
            mode=max_level["mode"],
            start_policy_year=max_level["start_year"],
            base_future_inputs=future_inputs,
            allow_exceptions=allow_exceptions,
            base_options=run_options,
            engine=engine,
        )
    except MaxLevelAllowedError as exc:
        raise RunFlowError("Max Level", str(exc), clear_field="max_level") from exc
    sched = list(future_inputs.scheduled_transactions)
    sched.append(ScheduledTransaction(
        kind=TransactionKind.PREMIUM,
        policy_year=int(max_level["start_year"]),
        amount=solved.premium,
        mode=solved.mode,
    ))
    policy_for_stop = scenario.projectable_policy
    if policy_for_stop.maturity_age > 100:
        sched.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=100 - int(policy_for_stop.issue_age or 0) + 1,
            amount=0.0,
            mode="A",
        ))
    return _ResolveStep(
        future_inputs=_replace_inputs(future_inputs, scheduled_transactions=sched),
        options=level_to_exception_options(run_options, allow_exceptions),
        solved_inputs=SolvedInputs(max_level_amount=solved.premium),
    )


def _resolve_min_level(
    min_level: dict,
    scenario,
    future_inputs: IllustrationInputSet,
    run_options: IllustrationOptions,
) -> _ResolveStep:
    allow_exceptions = not scenario.projectable_policy.is_cvat
    try:
        solved = solve_level_to_exception(
            scenario.projectable_policy,
            mode=min_level["mode"],
            start_policy_year=min_level["start_year"],
            base_future_inputs=future_inputs,
            allow_exceptions=allow_exceptions,
            base_options=run_options,
        )
    except LevelToExceptionError as exc:
        raise RunFlowError("Prem to Maturity", str(exc), clear_field="min_level") from exc
    sched = list(future_inputs.scheduled_transactions)
    sched.append(ScheduledTransaction(
        kind=TransactionKind.PREMIUM,
        policy_year=int(min_level["start_year"]),
        amount=solved.premium,
        mode=solved.mode,
    ))
    return _ResolveStep(
        future_inputs=_replace_inputs(future_inputs, scheduled_transactions=sched),
        options=level_to_exception_options(
            run_options,
            allow_exceptions,
            conform_to_tamra=not scenario.projectable_policy.is_cvat,
        ),
        solved_inputs=SolvedInputs(min_level_amount=solved.premium),
    )


def _resolve_shadow_level(
    shadow_level: dict,
    scenario,
    future_inputs: IllustrationInputSet,
    run_options: IllustrationOptions,
) -> _ResolveStep:
    shadow_policy = scenario.projectable_policy
    if not shadow_policy.has_shadow_account:
        if getattr(shadow_policy, "ccv_ceased", False):
            message = (
                "Prem to Shadow Maturity cannot run: this policy's shadow "
                "account benefit (type A) has ceased, so the shadow account "
                "no longer governs lapse."
            )
        else:
            message = (
                "Prem to Shadow Maturity cannot run: this policy has no shadow "
                "account benefit (type A)."
            )
        raise RunFlowError(
            "Prem to Shadow Maturity",
            message,
            clear_field="shadow_level",
        )
    allow_exceptions = False
    try:
        solved = solve_level_to_exception(
            shadow_policy,
            mode=shadow_level["mode"],
            start_policy_year=shadow_level["start_year"],
            base_future_inputs=future_inputs,
            allow_exceptions=allow_exceptions,
            base_options=run_options,
        )
    except LevelToExceptionError as exc:
        raise RunFlowError(
            "Prem to Shadow Maturity",
            "No level premium keeps the shadow account in force to maturity "
            "(the guideline premium cap limits what can be paid in).",
            clear_field="shadow_level",
        ) from exc
    sched = list(future_inputs.scheduled_transactions)
    sched.append(ScheduledTransaction(
        kind=TransactionKind.PREMIUM,
        policy_year=int(shadow_level["start_year"]),
        amount=solved.premium,
        mode=solved.mode,
    ))
    return _ResolveStep(
        future_inputs=_replace_inputs(future_inputs, scheduled_transactions=sched),
        options=level_to_exception_options(
            run_options,
            allow_exceptions,
            conform_to_tamra=not shadow_policy.is_cvat,
        ),
        solved_inputs=SolvedInputs(shadow_level_amount=solved.premium),
    )


def _resolve_target_premium(
    solve_req: dict,
    scenario,
    future_inputs: IllustrationInputSet,
    run_options: IllustrationOptions,
    engine: IllustrationEngine,
) -> _ResolveStep:
    if solve_req["amount"] is None or solve_req["at_age"] is None:
        raise RunFlowError(
            "Premium Solve",
            "Enter the Premium Solve criteria first — the target Amount and "
            "the At Age (beginning-of-year age) in the Solve group under the "
            "Premiums section.",
            clear_field="target",
        )
    try:
        solved = solve_premium_to_target(
            scenario.projectable_policy,
            target=solve_req["target"],
            amount=solve_req["amount"],
            at_age=solve_req["at_age"],
            mode=solve_req["mode"],
            start_policy_year=solve_req["start_year"],
            end_policy_year=solve_req["end_year"],
            base_future_inputs=future_inputs,
            base_options=run_options,
            engine=engine,
        )
    except PremiumTargetError as exc:
        raise RunFlowError("Premium Solve", str(exc), clear_field="target") from exc
    sched = list(future_inputs.scheduled_transactions)
    sched.append(ScheduledTransaction(
        kind=TransactionKind.PREMIUM,
        policy_year=int(solve_req["start_year"]),
        amount=solved.premium,
        mode=solved.mode,
    ))
    if solve_req["end_year"] is not None:
        sched.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=int(solve_req["end_year"]) + 1,
            amount=0.0,
            mode="A",
        ))
    target_label = TARGET_FIELDS[solved.target][1]
    message = (
        f"Premium Solve: {solved.premium:,.2f}/{solved.mode} reaches "
        f"{target_label} {solved.achieved_value:,.2f} at age {solved.at_age}."
    )
    return _ResolveStep(
        future_inputs=_replace_inputs(future_inputs, scheduled_transactions=sched),
        options=run_options,
        solved_inputs=SolvedInputs(target_amount=solved.premium),
        messages=[message],
    )


def _resolve_duration(
    duration_req: dict,
    scenario,
    future_inputs: IllustrationInputSet,
    run_options: IllustrationOptions,
    engine: IllustrationEngine,
) -> _ResolveStep:
    if (
        duration_req["premium"] is None
        or duration_req["amount"] is None
        or duration_req["at_age"] is None
    ):
        raise RunFlowError(
            "Solve for Duration",
            "Enter the Solve for Duration premium and criteria first - "
            "Premium, target Amount, and At Age are required.",
        )
    try:
        solved = solve_premium_duration(
            scenario.projectable_policy,
            premium=duration_req["premium"],
            mode=duration_req["mode"],
            target=duration_req["target"],
            amount=duration_req["amount"],
            at_age=duration_req["at_age"],
            start_policy_year=duration_req["start_year"],
            base_future_inputs=future_inputs,
            base_options=run_options,
            engine=engine,
        )
    except PremiumTargetError as exc:
        raise RunFlowError("Solve for Duration", str(exc)) from exc
    sched = list(future_inputs.scheduled_transactions)
    sched.append(ScheduledTransaction(
        kind=TransactionKind.PREMIUM,
        policy_year=duration_req["start_year"],
        amount=solved.premium,
        mode=solved.mode,
    ))
    maturity_year = max(
        1,
        int(scenario.projectable_policy.maturity_age)
        - int(scenario.projectable_policy.issue_age),
    )
    if solved.end_policy_year < maturity_year:
        sched.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM,
            policy_year=solved.end_policy_year + 1,
            amount=0.0,
            mode="A",
        ))
    target_label = TARGET_FIELDS[solved.target][1]
    achieved = (
        f"{solved.achieved_value:,.2f}"
        if solved.achieved_value is not None
        else "no target-age value"
    )
    if solved.reached_target:
        message = (
            f"Solve for Duration: {solved.premium:,.2f}/{solved.mode} for "
            f"{solved.duration_years} years reaches {target_label} {achieved} "
            f"at age {solved.at_age}."
        )
    else:
        message = (
            "Solve for Duration: target not reached; premium set through "
            f"maturity ({solved.duration_years} years), producing "
            f"{target_label} {achieved} at age {solved.at_age}."
        )
    return _ResolveStep(
        future_inputs=_replace_inputs(future_inputs, scheduled_transactions=sched),
        options=run_options,
        solved_inputs=SolvedInputs(duration_years=solved.duration_years),
        messages=[message],
    )


def _resolve_loan_payoffs(
    payoff_requests: tuple[dict, ...],
    scenario,
    future_inputs: IllustrationInputSet,
    run_options: IllustrationOptions,
    engine: IllustrationEngine,
) -> _ResolveStep:
    solved_amounts = []
    try:
        for request in payoff_requests:
            payoff = solve_loan_payoff(
                scenario.projectable_policy,
                repayment_dates=request["dates"],
                check_date=request["check_date"],
                base_future_inputs=future_inputs,
                base_options=run_options,
                engine=engine,
            )
            solved_amounts.append(payoff.repayment)
            if payoff.repayment > 0:
                dated = list(future_inputs.dated_transactions)
                dated.extend(
                    DatedTransaction(
                        kind=TransactionKind.LOAN_REPAYMENT,
                        effective_date=when,
                        amount=payoff.repayment,
                        subtype=PAYOFF_SUBTYPE,
                    )
                    for when in request["dates"]
                )
                future_inputs = _replace_inputs(future_inputs, dated_transactions=dated)
    except LoanPayoffError as exc:
        raise RunFlowError("Loan Pay-off", str(exc), clear_field="loan_payoff") from exc
    return _ResolveStep(
        future_inputs=future_inputs,
        options=run_options,
        solved_inputs=SolvedInputs(loan_payoff_amounts=solved_amounts),
    )


def _replace_inputs(
    source: IllustrationInputSet,
    *,
    scheduled_transactions: list[ScheduledTransaction] | None = None,
    dated_transactions: list[DatedTransaction] | None = None,
) -> IllustrationInputSet:
    return IllustrationInputSet(
        scheduled_transactions=(
            list(source.scheduled_transactions)
            if scheduled_transactions is None else scheduled_transactions
        ),
        dated_transactions=(
            list(source.dated_transactions)
            if dated_transactions is None else dated_transactions
        ),
        policy_changes=list(source.policy_changes),
    )


def _final_status(
    request: RunRequest,
    run_scenario: RunScenario,
    current: list[MonthlyState],
    guaranteed_error: str | None,
    lumpsum_result: object | None,
) -> str:
    if getattr(run_scenario.scenario, "run_from_issue", False):
        status = (
            f"Values ready for {request.basis.policy_number} - issue opening plus "
            f"{max(len(current) - 1, 0)} projected months from policy issue"
        )
    else:
        status = (
            f"Values ready for {request.basis.policy_number} - valuation snapshot plus "
            f"{max(len(current) - 1, 0)} projected months"
        )
    if request.basis.snapshot_status:
        status += f"  ·  {request.basis.snapshot_status}"
    if request.controls.rollback_status:
        status += f"  |  {request.controls.rollback_status}"
    if dcv_defaulted(current):
        status += f"  ·  {DCV_DEFAULTED_NOTICE}"
    for notice in min_face_notices(current):
        status += f"  ·  {notice}"
    if guaranteed_error:
        status += f"  ·  Guaranteed values unavailable: {guaranteed_error}"
    if lumpsum_result is not None and lumpsum_result.lumpsum > 0:
        reason = {
            "SV": "surrender-value",
            "AV": "account-value-less-loans",
            "SNET": "safety-net",
        }.get(lumpsum_result.binding_reason, lumpsum_result.binding_reason)
        status += (
            f"  ·  Applied a {_format_amount(lumpsum_result.lumpsum)} lumpsum on "
            f"{_format_date(lumpsum_result.forecast_date)} to carry the policy to its "
            f"next premium on {_format_date(lumpsum_result.next_premium_date)} "
            f"(sized by the {reason} shortfall)."
        )
    return status


def _format_amount(value: float) -> str:
    amount = float(value)
    if amount == int(amount):
        return f"{int(amount):,}"
    return f"{amount:,.2f}"


def _format_date(value: date) -> str:
    return value.strftime(_STATUS_DATE_FMT)
