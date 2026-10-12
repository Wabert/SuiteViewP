"""Step-by-step workup of one CyberLife NSP roll-forward year for the NSP Workup page.

Pick an anniversary after ``LOW_DUR_PER`` and the workup rebuilds its NSP per $1,000 from
the previous anniversary's value with ``nsp_roll.roll_step`` (CyberDoc B10 p.57, S45
p.519): the mortality rate one age past the value rolled from, the coverage's mortality
function code ``MTL_FUN_CD`` (CyberDoc D20 p.94) and the claims factor it gives, the
accumulation, the claim cost and the survivorship division, then the 6-decimal carry
and the cents value the cash value uses. Stored values are checked against the record
(``LOW_DUR_1_NSP_AMT`` from ``LOW_DUR_NSP_AMT``, ``LOW_DUR_2_NSP_AMT`` from
``LOW_DUR_1_NSP_AMT``); later ones against the engine's schedule. The paid-up endowment's NSP
at the same age is shown beside it, like the par WL RPU workup (``parwl/rpu_workup.py``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from suiteview.illustration.core.iswl_rpu.nsp_roll import RollStep, half_up, roll_step, stored_step_tolerance
from suiteview.illustration.core.parwl.nsp import claims_basis, function_code_text, mortality_table
from suiteview.illustration.models.iswl_rpu import SOURCE_NEGATIVE, ISWLRPUPolicy, NSPValue


@dataclass(frozen=True)
class WorkupStep:
    item: str
    formula: str
    value: str
    check: str = ""


@dataclass(frozen=True)
class RollWorkup:
    duration: int                 # the anniversary worked (NSP at duration from duration - 1)
    step: RollStep
    steps: Tuple[WorkupStep, ...]
    matches: bool


def _rate(rate: float) -> str:
    return f"{rate * 100:.4f}".rstrip("0").rstrip(".") + "%"


def workup_durations(policy: ISWLRPUPolicy, schedule: Sequence[NSPValue]) -> List[int]:
    """The anniversaries a workup can rebuild: every one after ``LOW_DUR_PER``."""
    return [v.duration for v in schedule if v.duration > policy.low_duration]


def roll_workup(policy: ISWLRPUPolicy, schedule: Sequence[NSPValue], duration: int) -> RollWorkup:
    """Rebuild the NSP at ``duration`` from the value at ``duration - 1``."""
    by_duration: Dict[int, NSPValue] = {v.duration: v for v in schedule}
    target, source = by_duration.get(duration), by_duration.get(duration - 1)
    if target is None or source is None or duration <= policy.low_duration:
        raise ValueError(f"Duration {duration} is not rolled forward from the stored values.")
    step = roll_step(source.carry, policy.nsp_table, policy.nsp_interest, policy.issue_age, source.duration,
                     policy.mortality_function_code)
    table = mortality_table(policy.nsp_table)
    _factor, claims_rule = claims_basis(table, step.interest, policy.mortality_function_code)
    from_text = (f"{source.column} (stored)" if source.column
                 else f"carried value of duration {source.duration} (6 decimals)")
    steps = [
        WorkupStep("Anniversary", f"duration {duration}, age {target.age}", f"{target.anniversary:%m/%d/%Y}"),
        WorkupStep("Base coverage", f"{policy.plancode} phase {policy.phase}, issued {policy.issue_date:%m/%d/%Y}",
                   f"issue age {policy.issue_age}"),
        WorkupStep("Mortality table", f"NSP_RPU_TBL_CD {table.code}: {table.description}",
                   f"ages {table.first_age}-{table.last_age}"),
        WorkupStep("Interest rate i", "NSP_ITS_RT", _rate(step.interest)),
        WorkupStep("Mortality function code",
                   "LH_COV_PHA.MTL_FUN_CD (CyberDoc D20 p.94 FCVVFNCT: 0 curtate, 1 semicontinuous, "
                   "2 fully continuous, 3 discounted continuous)",
                   function_code_text(policy.mortality_function_code)),
        WorkupStep("Claims factor c", claims_rule, f"{step.claims_factor:.10f}"),
        WorkupStep(f"NSP({source.duration}) per $1,000", from_text, f"{source.carry:,.6f}"),
        WorkupStep("Mortality age", f"issue age {policy.issue_age} + {source.duration} + 1 (CyberLife's step)",
                   f"{step.q_age}"),
        WorkupStep(f"q({step.q_age})", f"{table.code} mortality rate", f"{step.q:.8f}"),
        WorkupStep("Accumulated", f"{source.carry:,.6f} x (1 + {step.interest:.4f})", f"{step.accumulated:,.6f}"),
        WorkupStep("Claim cost", f"1000 x {step.q:.8f} x {step.claims_factor:.10f}", f"{step.claim_cost:,.6f}"),
        WorkupStep("Survivorship 1 - q", f"1 - {step.q:.8f}", f"{step.survival:.8f}"),
        WorkupStep(f"NSP({duration}) per $1,000",
                   f"({step.accumulated:,.6f} - {step.claim_cost:,.6f}) / {step.survival:.8f}", f"{step.value:,.6f}"),
    ]
    matches = True
    if target.column:
        index = 0 if duration == policy.low_duration + 1 else 1
        stored = target.carry
        tolerance = stored_step_tolerance(step, index)
        difference = stored - step.value
        matches = abs(difference) < tolerance
        check = (f"Matches {target.column} within rounding ({difference:+.6f}; tolerance {tolerance:.4f})"
                 if matches else f"Differs from {target.column} {stored:,.6f} by {difference:+.6f}")
        steps.append(WorkupStep("CyberLife stored value", target.column, f"{stored:,.6f}", check))
    else:
        matches = abs(step.carried - target.carry) < 0.0000005
        steps.append(WorkupStep("Carried value", "rounded half-up to 6 decimals", f"{step.carried:,.6f}",
                                "Matches the NSP schedule" if matches
                                else f"Differs from the NSP schedule {target.carry:,.6f}"))
    steps.append(WorkupStep("NSP the cash value uses", "stored value as is (fields 1-2)"
                            if target.duration <= policy.low_duration + 1 else "carried value in cents",
                            f"{target.per_unit:,.2f}"))
    if target.source == SOURCE_NEGATIVE:
        steps.append(WorkupStep("Negative value", "CyberDoc B10 p.57",
                                "CyberLife stops updating the NSPs",
                                f"Not verified: the illustration holds NSP({source.duration}) "
                                f"{source.per_unit:,.2f} from {source.anniversary:%m/%d/%Y}"))
    if target.comparison is not None:
        steps.append(WorkupStep(f"Endowment NSP at age {target.age}",
                                f"Paid-up endowment to age {policy.maturity_age}: {table.code} at "
                                f"{_rate(step.interest)}, same claims rule (the conversion basis)",
                                f"{target.comparison:,.6f}",
                                f"CyberLife basis differs by {target.per_unit - target.comparison:+,.2f}"))
    if target.source != SOURCE_NEGATIVE:
        cash_value = half_up(policy.units * target.per_unit * policy.value_per_unit / 1000.0)
        steps.append(WorkupStep(
            "Cash value at the anniversary",
            f"round({policy.units:,.3f} x {target.per_unit:,.2f} x {policy.value_per_unit:,.2f} / 1000, 2)",
            f"{cash_value:,.2f}"))
    return RollWorkup(duration, step, tuple(steps), matches)
