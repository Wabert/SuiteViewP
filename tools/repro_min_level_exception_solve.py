"""Reproduce the Prem-to-Maturity solve with Allow GP Exception ON vs OFF.

NOTE: the app itself now ALWAYS solves Prem to Maturity with exceptions
allowed (the checkbox is ignored for this premium type); this tool keeps the
ON/OFF comparison for diagnostics.

Faithful to the app's Run Values path for a policy whose only premium row is
"Prem to Maturity" (UI defaults everywhere else):

  * scenario = build_illustration_scenario(policy_data, overrides, empty inputs)
    with overrides.current_interest_rate = the UI's default illustrated rate
    (plancode gint, falling back to the policy's current rate — see
    inputs_dynamic.context_from_policy).
  * base run options as inputs_tab.export_options() defaults them:
    tefra/tamra True, exact_days False, levelizing True, apply_prem_to_loan
    False (the solver only inherits exact/levelizing/apply_prem_to_loan).
  * solve start year = the UI forecast year, mode = billing-frequency default.

Runs the solve for allow_exceptions in (True, False) with an INSTRUMENTED copy
of the solver's bracket+bisection loop (identical math; production untouched),
logging every probed premium, whether it survived, and where a failing
projection terminated (last month date/year/age, AV, exception flags).

Cross-checks afterward:
  * project the OFF-solved premium under the ON options — does it survive?
  * project the ON-solved premium under the OFF options — does it survive?

Usage:
    venv\\Scripts\\python.exe tools/repro_min_level_exception_solve.py '{"policy":"U0356726"}'

Optional keys: region (CKPR), company (01), mode (default from billing freq),
start_year (default UI forecast year), resolution (0.01), tail (months of
termination detail, default 8).
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

from dateutil.relativedelta import relativedelta  # noqa: E402

_MODE_FROM_FREQ = {1: "M", 3: "Q", 6: "S", 12: "A"}
_MAX_BRACKET_DOUBLINGS = 24


def _state_brief(s) -> dict:
    return {
        "date": str(s.date),
        "policy_year": s.policy_year,
        "policy_month": getattr(s, "policy_month", None),
        "attained_age": s.attained_age,
        "gross_premium": round(float(getattr(s, "gross_premium", 0.0) or 0.0), 2),
        "premium_capped": bool(getattr(s, "premium_capped", False)),
        "guideline_limit": round(float(getattr(s, "guideline_limit", 0.0) or 0.0), 2),
        "premiums_to_date": round(float(getattr(s, "premiums_to_date", 0.0) or 0.0), 2),
        "exception_prem_mode": bool(getattr(s, "exception_prem_mode", False)),
        "gp_exception_prem": round(float(getattr(s, "gp_exception_prem", 0.0) or 0.0), 2),
        "av_end_of_month": round(float(getattr(s, "av_end_of_month", 0.0) or 0.0), 2),
        "surrender_value": round(float(getattr(s, "surrender_value", 0.0) or 0.0), 2),
    }


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    policy_number = cmd.get("policy", "U0356726")
    region = cmd.get("region", "CKPR")
    company = cmd.get("company", "01")
    resolution = float(cmd.get("resolution", 0.01))
    tail = int(cmd.get("tail", 8))

    from suiteview.illustration.core.calc_engine import IllustrationEngine
    from suiteview.illustration.core.illustration_policy_service import build_illustration_data
    from suiteview.illustration.models.plancode_config import load_plancode
    from suiteview.illustration.core.scenario_builder import build_illustration_scenario
    from suiteview.illustration.core.solve_level_to_exception import (
        level_to_exception_options,
    )
    from suiteview.illustration.models.input_set import (
        IllustrationInputSet,
        IllustrationOptions,
        InforceOverrideSet,
        ScheduledTransaction,
        TransactionKind,
    )

    policy_data = build_illustration_data(policy_number, region=region, company_code=company)

    # UI default illustrated rate (context_from_policy): plancode gint first.
    plancode = str(policy_data.plancode or "")
    illustrated_rate = 0.0
    if plancode:
        illustrated_rate = float(load_plancode(plancode).gint or 0.0)
    if illustrated_rate == 0.0:
        illustrated_rate = float(
            getattr(policy_data, "current_interest_rate", None)
            or getattr(policy_data, "guaranteed_interest_rate", 0.0) or 0.0)
        if illustrated_rate > 1.0:
            illustrated_rate /= 100.0

    overrides = InforceOverrideSet(current_interest_rate=illustrated_rate)
    scenario = build_illustration_scenario(
        policy_data, inforce_overrides=overrides, future_inputs=IllustrationInputSet())
    proj = scenario.projectable_policy

    # UI forecast year (context_from_policy lines 226-232).
    valuation = getattr(proj, "valuation_date", None)
    issue = getattr(proj, "issue_date", None)
    forecast = valuation + relativedelta(months=1) if valuation else None
    if issue is not None and forecast is not None:
        months = (forecast.year - issue.year) * 12 + (forecast.month - issue.month)
        if forecast.day < issue.day:
            months -= 1
        forecast_year = max(1, months // 12 + 1)
    else:
        forecast_year = int(getattr(proj, "policy_year", 1) or 1)
    start_year = int(cmd.get("start_year", forecast_year))
    mode = str(cmd.get("mode")
               or _MODE_FROM_FREQ.get(int(proj.billing_frequency or 1), "M")).upper()

    # Base options exactly as inputs_tab.export_options() defaults them.
    base_options = IllustrationOptions(
        conform_to_tefra=True,
        conform_to_tamra=True,
        allow_exception_prems=True,   # ignored by the solver's option builder
        exact_days_interest=False,
        cap_premiums_at_acceptance=True,
        levelizing_premium=True,
        guideline_by_search=False,
        apply_prem_to_loan=False,
        apply_excess_repayment_as_premium=False,
        pay_monthly_deduction=False,
    )

    engine = IllustrationEngine()
    base_inputs = IllustrationInputSet()  # Min-Level-only UI state exports nothing

    def project(premium: float, options):
        scheds = list(base_inputs.scheduled_transactions)
        scheds.append(ScheduledTransaction(
            kind=TransactionKind.PREMIUM, policy_year=start_year,
            amount=float(premium), mode=mode))
        future = IllustrationInputSet(
            scheduled_transactions=scheds,
            dated_transactions=list(base_inputs.dated_transactions),
            policy_changes=list(base_inputs.policy_changes),
        )
        return engine.project(proj, options=options, future_inputs=future)

    def survives(states) -> bool:
        return bool(states) and states[-1].attained_age >= proj.maturity_age

    def termination(states) -> dict:
        exc_months = sum(1 for s in states if getattr(s, "exception_prem_mode", False))
        return {
            "months": len(states),
            "survives": survives(states),
            "entered_exception_mode": exc_months > 0,
            "exception_months": exc_months,
            "total_exception_prem": round(sum(
                float(getattr(s, "gp_exception_prem_gross", 0.0) or 0.0) for s in states), 2),
            "final": _state_brief(states[-1]) if states else None,
            "tail": [_state_brief(s) for s in states[-tail:]],
        }

    def instrumented_solve(allow: bool) -> dict:
        options = level_to_exception_options(base_options, allow)
        trace = []

        def probe(p: float):
            states = project(p, options)
            ok = survives(states)
            trace.append({
                "premium": round(p, 6), "survives": ok,
                "last_date": str(states[-1].date) if states else None,
                "last_age": states[-1].attained_age if states else None,
                "last_av": round(float(states[-1].av_end_of_month or 0.0), 2) if states else None,
                "exception_months": sum(
                    1 for s in states if getattr(s, "exception_prem_mode", False)),
            })
            return ok, states

        result: dict = {"allow_exceptions": allow, "options": {
            "conform_to_tefra": options.conform_to_tefra,
            "conform_to_tamra": options.conform_to_tamra,
            "allow_exception_prems": options.allow_exception_prems,
            "exact_days_interest": options.exact_days_interest,
            "levelizing_premium": options.levelizing_premium,
            "apply_prem_to_loan": options.apply_prem_to_loan,
            "cap_premiums_at_acceptance": options.cap_premiums_at_acceptance,
            "pay_monthly_deduction": options.pay_monthly_deduction,
        }}

        ok0, _ = probe(0.0)
        if ok0:
            result.update(premium=0.0, trace=trace)
            return result
        lo = 0.0
        hi = max(proj.modal_premium, 1.0)
        doublings = 0
        ok, states = probe(hi)
        while not ok:
            hi *= 2.0
            doublings += 1
            if doublings > _MAX_BRACKET_DOUBLINGS:
                result.update(error="no level premium survives", trace=trace)
                return result
            ok, states = probe(hi)
        while hi - lo > resolution:
            mid = (lo + hi) / 2.0
            ok, states = probe(mid)
            if ok:
                hi = mid
            else:
                lo = mid
        premium = math.ceil(hi / resolution) * resolution
        final_states = project(premium, options)
        result.update(
            premium=round(premium, 2),
            solved_run=termination(final_states),
            highest_failing_probe=round(lo, 6),
            trace=trace,
        )
        return result

    on = instrumented_solve(True)
    off = instrumented_solve(False)

    cross = {}
    if "premium" in off and "premium" in on:
        opts_on = level_to_exception_options(base_options, True)
        opts_off = level_to_exception_options(base_options, False)
        cross["off_premium_under_on_options"] = termination(project(off["premium"], opts_on))
        cross["on_premium_under_off_options"] = termination(project(on["premium"], opts_off))
        # The mechanism probe: just below the ON boundary, under ON options.
        below = max(0.0, on["premium"] - resolution * 2)
        cross["just_below_on_premium_under_on_options"] = {
            "premium": round(below, 2),
            **termination(project(below, opts_on)),
        }

    print(json.dumps({
        "policy": policy_number, "region": region, "company": company,
        "plancode": plancode,
        "valuation_date": str(valuation), "issue_date": str(issue),
        "forecast_year_start": start_year, "mode": mode,
        "maturity_age": proj.maturity_age,
        "attained_age": proj.attained_age,
        "db_option": getattr(proj, "db_option", None),
        "billed_modal_premium": proj.modal_premium,
        "illustrated_rate": illustrated_rate,
        "account_value_start": proj.account_value,
        "solve_ON": {k: v for k, v in on.items() if k != "trace"},
        "solve_OFF": {k: v for k, v in off.items() if k != "trace"},
        "trace_ON": on.get("trace"),
        "trace_OFF": off.get("trace"),
        "cross_checks": cross,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
