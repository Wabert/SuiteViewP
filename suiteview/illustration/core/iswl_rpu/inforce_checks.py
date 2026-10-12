"""ISWL RPU in-force checks: SuiteView's roll-forward and starting value against the record.

* **Stored NSP** - ``LOW_DUR_1_NSP_AMT`` rolled from ``LOW_DUR_NSP_AMT`` and
  ``LOW_DUR_2_NSP_AMT`` from ``LOW_DUR_1_NSP_AMT`` with ``nsp_roll.roll_step``; a match is
  within rounding (``stored_step_tolerance``). The oldest value can be the conversion
  year's NSP (B20 p.62: "the net single premium at the beginning of the year in which the
  conversion occurred"), which the anniversary formula need not reproduce.
* **Cash value** - the starting cash value against PolView's NSP cash value
  (``rates.guaranteed_cash_value``), to the cent.
* **Death benefit** - the paid-up face against the record's death benefit (``LH_POL_TOTALS``).
* **Comparison** (information) - the paid-up endowment's NSP at each stored value's age.
"""
from __future__ import annotations

from typing import List

from suiteview.illustration.core.inforce_check import CheckLine, check_line
from suiteview.illustration.core.iswl_rpu.engine import ISWLRPUEngine, ISWLRPUError, completed_parts
from suiteview.illustration.core.iswl_rpu.nsp_roll import roll_step, stored_step_tolerance
from suiteview.illustration.core.parwl.nsp import NSPError, function_code_text
from suiteview.illustration.models.iswl_rpu import STORED_NSP_COLUMNS, ISWLRPUPolicy


def inforce_checks(policy: ISWLRPUPolicy, engine: ISWLRPUEngine) -> List[CheckLine]:
    checks: List[CheckLine] = []
    low, stored = policy.low_duration, policy.stored_nsp
    for index in (0, 1):
        duration = low + index
        item = f"{STORED_NSP_COLUMNS[index + 1]} (duration {duration + 1}) from {STORED_NSP_COLUMNS[index]}"
        try:
            step = roll_step(stored[index], policy.nsp_table, policy.nsp_interest, policy.issue_age, duration,
                             policy.mortality_function_code)
        except NSPError as exc:
            checks.append(CheckLine("Stored NSP", item, stored[index + 1], None, "info", str(exc)))
            continue
        tolerance = stored_step_tolerance(step, index)
        detail = (f"({stored[index]:,.6f} x {1 + step.interest:.4f} - 1000 x q({step.q_age}) {step.q:.6f} x "
                  f"{step.claims_factor:.6f}) / (1 - q), claims factor from MTL_FUN_CD "
                  f"{function_code_text(step.function_code)}; match within {tolerance:.4f}")
        line = check_line("Stored NSP", item, stored[index + 1], step.value, detail, tolerance)
        if line.status == "differs":
            line = CheckLine(line.area, line.item, line.cyberlife, line.calculated, line.status,
                             f"Differs by {line.difference:+.6f}. " + detail
                             + (" The oldest stored value can be the conversion year's NSP (B20 p.62)."
                                if index == 0 else ""))
        checks.append(line)

    start = policy.valuation_date
    duration, months = completed_parts(policy.issue_date, start)
    item = f"Starting cash value {start:%m/%d/%Y} (duration {duration}, month {months})"
    try:
        value, _nsp, boy, eoy, _frozen = engine.cash_value(duration, months)
        detail = (f"round({policy.units:,.3f} x ({boy:,.6f} x {12 - months} + {eoy:,.6f} x {months}) / 12, 2) "
                  "against PolView's NSP cash value")
        checks.append(check_line("Cash value", item, policy.polview_cash_value, value,
                                 detail if policy.polview_cash_value is not None
                                 else f"PolView has no NSP cash value: {policy.polview_reason}"))
    except ISWLRPUError as exc:
        checks.append(CheckLine("Cash value", item, policy.polview_cash_value, None, "info", str(exc)))
    checks.append(check_line("Death benefit", "Paid-up face (units x value per unit)", policy.record_death_benefit,
                             policy.face_amount, "against the record's death benefit (LH_POL_TOTALS)"))
    for index, value in enumerate(stored):
        age = policy.issue_age + low + index
        nsp = next((v.comparison for v in engine.schedule if v.duration == low + index), None)
        checks.append(CheckLine(
            "Comparison", f"Endowment NSP at age {age} vs {STORED_NSP_COLUMNS[index]}", value, nsp, "info",
            "The stored values follow CyberLife's roll-forward, not the endowment NSP at the attained age; "
            "shown for comparison."))
    return checks
