"""Canonical projection façade for SuiteView UL illustrations.

Use :func:`project_policy` when application code wants a projection. It owns the
standard wiring once: build/load the policy data, load the plancode config and
rate bundle, then call ``IllustrationEngine.project`` through its public
signature. Callers remain responsible for scenario construction, solve layering
and UI/report reduction.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import date
from typing import Any

from suiteview.illustration.core.calc_engine import IllustrationEngine, ProjectionTiming
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.core.rate_loader import IllustrationRates, load_rates
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.input_set import IllustrationInputSet, IllustrationOptions
from suiteview.illustration.models.plancode_config import PlancodeConfig, load_plancode
from suiteview.illustration.models.policy_data import IllustrationPolicyData


@dataclass(frozen=True)
class ProjectionRun:
    """A completed projection plus the loaded basis used to run it."""

    policy: IllustrationPolicyData
    config: PlancodeConfig | None
    rates: IllustrationRates | None
    states: list[MonthlyState]
    inputs: IllustrationInputSet | None
    options: IllustrationOptions
    timing: ProjectionTiming
    months: int | None
    stop_on_lapse: bool


def project_policy(
    policy_or_number_or_pi: str | IllustrationPolicyData | Any,
    *,
    inputs: IllustrationInputSet | None = None,
    options: IllustrationOptions | None = None,
    timing: ProjectionTiming = ProjectionTiming.ILLUSTRATION,
    months: int | None = None,
    stop_on_lapse: bool = True,
    rates: IllustrationRates | None = None,
    config: PlancodeConfig | None = None,
    region: str = "CKPR",
    company_code: str | None = None,
    illustration_date: date | None = None,
    reinstatement_date: date | None = None,
    engine: IllustrationEngine | None = None,
    bonus_override=None,
) -> ProjectionRun:
    """Build/load a policy basis and run one projection through the engine.

    ``policy_or_number_or_pi`` accepts an already-built
    :class:`IllustrationPolicyData`, a policy number string, or a
    PolicyInformation-like object with ``policy_number``/``region`` attributes.
    Passing ``rates`` or ``config`` preserves specialized callers' existing
    overrides; otherwise the standard plancode and rate loaders are used.
    """
    policy = _coerce_policy(
        policy_or_number_or_pi,
        region=region,
        company_code=company_code,
        illustration_date=illustration_date,
        reinstatement_date=reinstatement_date,
    )
    runner = engine or IllustrationEngine()
    project_parameters = inspect.signature(runner.project).parameters
    should_load_rates = engine is None or rates is not None or config is not None
    run_config = (
        config if config is not None
        else load_plancode(policy.plancode) if should_load_rates
        else None
    )
    run_rates = (
        rates if rates is not None
        else load_rates(policy, run_config) if should_load_rates and run_config is not None
        else None
    )
    run_options = options if options is not None else IllustrationOptions()
    states = _project_with_supported_kwargs(
        runner,
        policy,
        months=months,
        future_inputs=inputs,
        timing=timing,
        stop_on_lapse=stop_on_lapse,
        options=run_options,
        bonus_override=bonus_override,
        rates_override=run_rates,
    )
    return ProjectionRun(
        policy=policy,
        config=run_config,
        rates=run_rates,
        states=states,
        inputs=inputs,
        options=run_options,
        timing=timing,
        months=months,
        stop_on_lapse=stop_on_lapse,
    )


def _project_with_supported_kwargs(
    runner: IllustrationEngine,
    policy: IllustrationPolicyData,
    **kwargs,
) -> list[MonthlyState]:
    """Call ``project`` with public kwargs, tolerating narrow test doubles."""
    parameters = inspect.signature(runner.project).parameters
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        return runner.project(policy, **kwargs)
    accepted = {
        name: value for name, value in kwargs.items()
        if name in parameters
    }
    return runner.project(policy, **accepted)


def _coerce_policy(
    policy_or_number_or_pi: str | IllustrationPolicyData | Any,
    *,
    region: str,
    company_code: str | None,
    illustration_date: date | None,
    reinstatement_date: date | None,
) -> IllustrationPolicyData:
    if isinstance(policy_or_number_or_pi, IllustrationPolicyData):
        return policy_or_number_or_pi
    if isinstance(policy_or_number_or_pi, str):
        return build_illustration_data(
            policy_or_number_or_pi,
            region=region,
            company_code=company_code,
            illustration_date=illustration_date,
            reinstatement_date=reinstatement_date,
        )
    policy_number = getattr(policy_or_number_or_pi, "policy_number", None)
    if not policy_number:
        return policy_or_number_or_pi
    return build_illustration_data(
        str(policy_number),
        region=getattr(policy_or_number_or_pi, "region", region) or region,
        company_code=company_code or getattr(policy_or_number_or_pi, "company_code", None),
        illustration_date=illustration_date,
        reinstatement_date=reinstatement_date,
    )
