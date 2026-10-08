"""Step-by-step workup of a reduced paid-up (RPU) base cash value for the Values tab.

On reduced paid-up the engine values the base coverage at the net single premium of
whole life on the coverage's RPU basis (``NSP_RPU_TBL_CD`` / ``NSP_ITS_RT``), calculated
from the CyberLife mortality table (see ``nsp.py``). This module rebuilds one month's
base cash value one step at a time from the engine's own functions, with the
mortality terms behind each NSP, so a reviewer can reproduce every number by hand
or in Excel. The result is checked against the engine's base cash value for that month.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple

from suiteview.illustration.core.parwl.engine import cents, completed_months
from suiteview.illustration.core.parwl.nsp import NSPError, NSPWorkup, net_single_premium, nsp_workup
from suiteview.illustration.models.parwl import ParWLMonth, ParWLPolicy

STORED_NSP_COLUMNS = ("LOW_DUR_NSP_AMT", "LOW_DUR_1_NSP_AMT", "LOW_DUR_2_NSP_AMT")


@dataclass(frozen=True)
class WorkupStep:
    """One line of the workup: what it is, how it is derived, its value and any check."""

    item: str
    formula: str
    value: str
    check: str = ""


@dataclass(frozen=True)
class RPUWorkup:
    when: date
    steps: Tuple[WorkupStep, ...]
    at_age: NSPWorkup              # NSP at the policy year's start age x
    at_next_age: NSPWorkup         # NSP at x + 1
    base_cv: float                 # recalculated here
    engine_base_cv: float          # the projection's base cash value for the month

    @property
    def matches(self) -> bool:
        return abs(self.base_cv - self.engine_base_cv) < 0.005


def _rate_text(rate: float) -> str:
    return f"{rate * 100:.4f}".rstrip("0").rstrip(".") + "%"


def _check(calculated: float, expected: float, label: str) -> str:
    difference = round(expected - calculated, 2)
    if abs(difference) < 0.005:
        return f"Matches {label}"
    return f"Differs from {label} {expected:,.2f} by {difference:,.2f}"


def rpu_cash_value_workup(policy: ParWLPolicy, month: ParWLMonth) -> RPUWorkup:
    """Rebuild ``month``'s reduced paid-up base cash value from the mortality table."""
    if not month.rpu:
        raise ValueError(f"{month.when:%m/%d/%Y} is not on reduced paid-up; the base cash value is tabular.")
    cov = policy.base
    if not cov.nsp_table or cov.nsp_interest is None:
        raise NSPError(f"{cov.plancode} has no reduced paid-up NSP basis (NSP_RPU_TBL_CD / NSP_ITS_RT).")
    months_done = completed_months(cov.issue_date, month.when)
    years, k = months_done // 12, months_done % 12
    x = cov.issue_age + years
    at_x = nsp_workup(cov.nsp_table, cov.nsp_interest, x)
    at_next = nsp_workup(cov.nsp_table, cov.nsp_interest, x + 1)
    table = at_x.table
    mid = (at_x.nsp * (12 - k) + at_next.nsp * k) / 12.0
    per_unit = mid * cov.value_per_unit / 1000.0
    base_cv = cents(month.units * per_unit)
    immediate = at_x.claims_factor != 1.0

    steps = [
        WorkupStep("Value date", "Selected monthliversary", f"{month.when:%m/%d/%Y}"),
        WorkupStep("Base coverage", f"{cov.plancode} phase {cov.phase}, issued {cov.issue_date:%m/%d/%Y}",
                   f"issue age {cov.issue_age}"),
        WorkupStep("Mortality table", f"NSP_RPU_TBL_CD {table.code}: {table.description}",
                   f"ages {table.first_age}-{table.last_age}"),
        WorkupStep("Interest rate i", "NSP_ITS_RT", _rate_text(at_x.interest)),
        WorkupStep("Discount factor v", "1 / (1 + i)", f"{at_x.discount_factor:.10f}"),
        WorkupStep("Claims factor",
                   "Age-last-birthday table: claims paid at death, i / ln(1 + i)" if immediate
                   else "Claims at the end of the year of death (curtate)",
                   f"{at_x.claims_factor:.10f}"),
        WorkupStep("Completed months", f"{cov.issue_date:%m/%d/%Y} to {month.when:%m/%d/%Y}", f"{months_done}"),
        WorkupStep("Completed policy years", "completed months // 12", f"{years}"),
        WorkupStep("Month of policy year k", "completed months mod 12", f"{k}"),
        WorkupStep("Attained age x", f"issue age {cov.issue_age} + {years}", f"{x}"),
    ]
    for label, work in (("x", at_x), ("x + 1", at_next)):
        if work.terms:
            last = work.terms[-1]
            steps.append(WorkupStep(
                f"Sum at age {work.attained_age} ({label})",
                f"sum of tpx * q(x+t) * v^(t+1), t = 0..{last.t} (Mortality Terms, age {work.attained_age})",
                f"{work.curtate_sum:.10f}"))
            steps.append(WorkupStep(f"NSP per $1,000 at {work.attained_age}", "1000 * sum * claims factor",
                                    f"{work.nsp:.6f}"))
        else:
            steps.append(WorkupStep(f"NSP per $1,000 at {work.attained_age}",
                                    f"past the table's last age {table.last_age}: the face", f"{work.nsp:.6f}"))
    steps += [
        WorkupStep("Interpolated NSP per $1,000",
                   f"({at_x.nsp:.6f} * {12 - k} + {at_next.nsp:.6f} * {k}) / 12", f"{mid:.6f}"),
        WorkupStep("Value per unit", "coverage value per unit", f"{cov.value_per_unit:,.2f}"),
        WorkupStep("Cash value per unit", f"{mid:.6f} * {cov.value_per_unit:,.2f} / 1000", f"{per_unit:.6f}",
                   "Matches Cash Value page CV/Unit" if abs(per_unit - month.cv_per_unit) < 0.000001
                   else f"Differs from Cash Value page CV/Unit {month.cv_per_unit:.6f}"),
        WorkupStep("Reduced paid-up units", "units on reduced paid-up", f"{month.units:,.3f}"),
        WorkupStep("Base cash value", f"round({month.units:,.3f} * {per_unit:.6f}, 2)", f"{base_cv:,.2f}",
                   _check(base_cv, month.base_cv, "Cash Value page Base CV")),
    ]
    conversion = next((part.strip() for part in month.notes.split(";") if "Reduced paid-up:" in part), "")
    if conversion:
        steps.append(WorkupStep("Conversion to RPU", "net value / NSP per unit = units (3 decimals)", conversion))
    steps += _stored_nsp_steps(policy)
    return RPUWorkup(month.when, tuple(steps), at_x, at_next, base_cv, month.base_cv)


def _stored_nsp_steps(policy: ParWLPolicy) -> Tuple[WorkupStep, ...]:
    """CyberLife's stored RPU NSPs per unit (anniversary values) against the calculation."""
    cov = policy.base
    if not policy.is_rpu or cov.stored_low_duration is None:
        return ()
    steps = []
    for offset, stored in enumerate(cov.stored_nsp_values[:len(STORED_NSP_COLUMNS)]):
        if not stored:
            continue
        duration = cov.stored_low_duration + offset
        age = cov.issue_age + duration
        try:
            calc: Optional[float] = round(
                net_single_premium(cov.nsp_table, cov.nsp_interest, age) * cov.value_per_unit / 1000.0, 2)
        except NSPError as exc:
            steps.append(WorkupStep(f"CyberLife NSP/unit, duration {duration}", STORED_NSP_COLUMNS[offset],
                                    f"{stored:,.2f}", str(exc)))
            continue
        steps.append(WorkupStep(
            f"CyberLife NSP/unit, duration {duration}",
            f"{STORED_NSP_COLUMNS[offset]} vs round(NSP at age {age} * value per unit / 1000, 2) = {calc:,.2f}",
            f"{stored:,.2f}", _check(calc, stored, "CyberLife")))
    return tuple(steps)
