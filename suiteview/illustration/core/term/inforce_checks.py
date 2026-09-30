"""Reproduce CyberLife's current indeterminate premium term values from schema ``rates``.

Each check compares a value CyberLife holds on the record with SuiteView's own:

* **Premium per unit** - the coverage's stored ``ANN_PRM_UNT_AMT`` against the ``PREM``
  current scale at the coverage's policy year (riders and benefits the same way);
* **Renewal rate** - the next period's rate on the renewal rates segment (67) against the
  ``PREM`` current scale at the year that period starts;
* **Table extra** - the stored extra per unit against ``rate x (percent - 1)``;
* **Modal premium** - the billed ``POL_PRM_AMT`` against the engine's modal premium.
"""
from __future__ import annotations

from typing import List, Optional

from suiteview.illustration.core.fixed_premium import cents
from suiteview.illustration.core.inforce_check import CheckLine, check_line
from suiteview.illustration.core.term.engine import TermEngine, TermProjectionError, policy_year
from suiteview.illustration.core.term.rates import TermRates
from suiteview.illustration.models.term import SCALE_CURRENT, SCALE_GUARANTEED, TermPolicy


def rate_checks(policy: TermPolicy, rates: TermRates, engine: TermEngine) -> List[CheckLine]:
    lines: List[CheckLine] = []
    for cov in policy.coverages:
        schedule = rates.coverages.get(cov.phase)
        year = engine.record_year(cov)
        if schedule is None:
            lines.append(CheckLine("Premium", f"{cov.plancode} premium per unit (yr {year})",
                                   cov.annual_premium_per_unit, None, "info", "no PREM rates in schema rates"))
            continue
        lines.append(check_line("Premium", f"{cov.plancode} premium per unit (yr {year})", cov.annual_premium_per_unit,
                                schedule.rate(SCALE_CURRENT, year), f"stored ANN_PRM_UNT_AMT vs {schedule.source} C"))
        if cov.next_renewal_rate is not None:
            change = engine.next_premium_change(cov)
            next_year = policy_year(cov.issue_date, change)
            if cov.maturity_date is not None and change >= cov.maturity_date:
                continue
            lines.append(check_line(
                "Premium", f"{cov.plancode} renewal rate from {change:%m/%d/%Y} (yr {next_year})",
                cov.next_renewal_rate, schedule.rate(SCALE_CURRENT, next_year),
                f"renewal rates segment (67) vs {schedule.source} C; guaranteed "
                f"{schedule.rate(SCALE_GUARANTEED, next_year)}"))
        for extra in cov.extras:
            if extra.percent is not None and extra.percent > 1.0 and extra.per_unit is not None:
                lines.append(check_line(
                    "Substandard", f"{cov.plancode} table {extra.table_code} extra per unit", extra.per_unit,
                    cents(cov.annual_premium_per_unit * (extra.percent - 1.0)),
                    f"stored SST_XTR_UNT_AMT vs {cov.annual_premium_per_unit:,.2f} x ({extra.percent:g} - 1)"))
    for benefit in policy.benefits:
        schedule = rates.benefits.get((benefit.phase, benefit.code))
        if schedule is None or not benefit.annual_premium_per_unit:
            continue
        year = policy_year(benefit.issue_date or policy.base.issue_date, policy.valuation_date)
        lines.append(check_line("Premium", f"benefit {benefit.code} premium per unit (yr {year})",
                                benefit.annual_premium_per_unit, schedule.rate(SCALE_CURRENT, year),
                                f"stored BNF_ANN_PPU_AMT vs {schedule.source} C"))
    return lines


def premium_checks(policy: TermPolicy, engine: TermEngine) -> List[CheckLine]:
    if not policy.premium_paying or not policy.modal_premium:
        return []
    if engine.blocking_error:
        return [CheckLine("Premium", "Modal premium", policy.modal_premium, None, "differs", engine.blocking_error)]
    when = engine.record_premium_date()
    try:
        parts, basis = engine.billed_parts()
    except TermProjectionError as exc:
        return [CheckLine("Premium", "Modal premium", policy.modal_premium, None, "info", str(exc))]
    calculated = cents(sum(p.current for p in parts))
    detail = f"due {when:%m/%d/%Y} at {basis}: " + " + ".join(f"{p.label} {p.current:,.2f}" for p in parts)
    line = check_line("Premium", "Modal premium", policy.modal_premium, calculated, detail)
    if line.status == "differs" and policy.forced_premium:
        line = CheckLine(line.area, line.item, line.cyberlife, line.calculated, "info",
                         detail + "; forced premium on the record (billed as forced)")
    return [line]


def inforce_checks(policy: TermPolicy, rates: TermRates, engine: Optional[TermEngine] = None) -> List[CheckLine]:
    """Every in-force check for ``policy``; ``engine`` defaults to a record-mode engine."""
    engine = engine or TermEngine(policy, rates)
    return rate_checks(policy, rates, engine) + premium_checks(policy, engine)
