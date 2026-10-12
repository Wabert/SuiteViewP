"""CyberLife's anniversary roll-forward of an ISWL reduced paid-up coverage's net single premiums.

CyberDoc B10 p.57 ("Paid-Up Policies"): an advanced product (ISL) converted to RPU is
treated as traditional; the coverage segment stores the net single premiums of the
nonforfeiture benefit (``LOW_DUR_NSP_AMT``, ``LOW_DUR_1_NSP_AMT``, ``LOW_DUR_2_NSP_AMT``
for durations ``LOW_DUR_PER``, +1, +2), and "during anniversary processing, the values
are extended one year using the extended term net single premium formula". S45 p.518
(CKULNLEC/CKULNLEI): "each iteration buys one more year of insurance"; "anniversary
processing uses the 3rd NSP value for the cash available". "When the value in the third
values field becomes negative, the net single premiums are no longer updated".

The step reproduced from the record (all company 01 ISWL RPU coverages,
``tools/rerun/verify_iswl_rpu_nsp.py``), per $1,000 at duration ``d``::

    NSP(d + 1) = (NSP(d) * (1 + i) - 1000 * q * c) / (1 - q)

with ``i`` = ``NSP_ITS_RT``, ``q`` the ``NSP_RPU_TBL_CD`` mortality rate at age
``issue age + d + 1`` (one year older than the textbook ``A(x+1) = (A(x)(1+i) - q(x)) / p(x)``;
q at ``issue age + d`` misses 11663262 by 0.91) and ``c`` the claims factor of the coverage's
mortality function code ``LH_COV_PHA.MTL_FUN_CD`` (CyberDoc D20 p.94 FCVVFNCT; S48 p.250):
``i / ln(1 + i)`` for 1 (semicontinuous) and 2 (fully continuous), 1 for 0 (curtate); other
codes are refused (``parwl/nsp.claims_factor_for``). Every company 01 ISWL RPU coverage has
code 2 on L4/L5/S/T and 0 on N0/N1/N2 (10/9/2026). Without a code the table's age basis
decides (``parwl/nsp.claims_basis``). The third stored value is the unrounded carry
(6 decimals); the first two are in cents.

**At conversion** (verified on 11663262 and on conversions in roughly the last 11 years;
``ZZTaskRepo\\ISWL-RPU-Illustration-2026-10-09``) the cash buys a paid-up *endowment at the
coverage's maturity age*: the NSP is :func:`endowment_nsp` at the attained ages ``x`` and
``x + 1`` interpolated monthly (CyberDoc B20 p.498: face = cash / NSP, rounded up to the
next dollar), and the three stored values start as that NSP at durations ``d``, ``d + 1``
and ``d + 2``. Older conversions do not start on it.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Optional

from suiteview.illustration.core.parwl.nsp import (
    MortalityTable,
    NSPError,
    claims_basis,
    mortality_table,
    normalize_function_code,
)

CARRY_DECIMALS = 6
CARRY_QUANTUM = Decimal("0.000001")
CENT = Decimal("0.01")


def half_up(value: float, quantum: Decimal = CENT) -> float:
    """Half-up rounding as CyberLife rounds (``quantum`` 0.01 or 0.000001)."""
    return float(Decimal(repr(float(value))).quantize(quantum, rounding=ROUND_HALF_UP))


def claims_factor(table: MortalityTable, interest: float, function_code: Optional[str] = None) -> float:
    """The claims factor of the coverage's ``MTL_FUN_CD`` (``i / ln(1 + i)`` for 1/2, 1 for 0);
    without a code, ``i / ln(1 + i)`` for an age-last-birthday table, else 1."""
    return claims_basis(table, interest, function_code)[0]


@lru_cache(maxsize=8192)
def endowment_nsp(table_code: str, interest: float, age: int, maturity_age: int,
                  function_code: Optional[str] = None) -> float:
    """NSP per $1,000 of the paid-up benefit: $1,000 on death before ``maturity_age`` or at it.

    Built back from the maturity value, ``E(m) = 1000`` and
    ``E(x) = (E(x + 1) * (1 - q(x)) + 1000 * q(x) * c) / (1 + i)``, with the claims factor
    of :func:`claims_factor` for the coverage's ``MTL_FUN_CD`` ``function_code``.
    """
    if age >= maturity_age:
        return 1000.0
    table = mortality_table(table_code)
    if age < table.first_age or maturity_age - 1 > table.last_age:
        raise NSPError(f"Mortality table {table.code} covers ages {table.first_age}-{table.last_age}; "
                       f"an endowment NSP from age {age} to {maturity_age} needs more.")
    rate = float(interest)
    factor = claims_factor(table, rate, function_code)
    value = 1000.0
    for x in range(maturity_age - 1, age - 1, -1):
        q = table.qx[x - table.first_age]
        value = (value * (1.0 - q) + 1000.0 * q * factor) / (1.0 + rate)
    return value


@dataclass(frozen=True)
class RollStep:
    """One anniversary extension: NSP at ``duration`` to NSP at ``duration + 1`` (per $1,000)."""

    table: str
    interest: float
    duration: int            # d: the duration of the value rolled from
    q_age: int               # issue age + d + 1
    q: float
    claims_factor: float
    start: float             # NSP(d)
    accumulated: float       # NSP(d) * (1 + i)
    claim_cost: float        # 1000 * q * c
    value: float             # (accumulated - claim cost) / (1 - q), unrounded
    carried: float           # value rounded to the 6 decimals CyberLife carries
    function_code: Optional[str] = None   # MTL_FUN_CD used (None: the table fallback)

    @property
    def survival(self) -> float:
        return 1.0 - self.q


def roll_step(nsp: float, table_code: str, interest: float, issue_age: int, duration: int,
              function_code: Optional[str] = None) -> RollStep:
    """Extend ``nsp`` (per $1,000 at ``duration``) one year with CyberLife's formula; the
    claims factor follows the coverage's ``MTL_FUN_CD`` ``function_code``."""
    table = mortality_table(table_code)
    age = int(issue_age) + int(duration) + 1
    if not table.first_age <= age <= table.last_age:
        raise NSPError(f"Mortality table {table.code} has no rate at age {age} "
                       f"(ages {table.first_age}-{table.last_age}).")
    q = table.qx[age - table.first_age]
    if q >= 1.0:
        raise NSPError(f"Mortality table {table.code} has q = 1 at age {age}; the NSP cannot be extended.")
    rate = float(interest)
    fun = normalize_function_code(function_code)
    factor = claims_factor(table, rate, fun)
    accumulated = float(nsp) * (1.0 + rate)
    claim_cost = 1000.0 * q * factor
    value = (accumulated - claim_cost) / (1.0 - q)
    return RollStep(table.code, rate, int(duration), age, q, factor, float(nsp), accumulated, claim_cost,
                    value, half_up(value, CARRY_QUANTUM), fun)


def roll_forward_nsp(nsp: float, table_code: str, interest: float, issue_age: int, duration: int,
                     function_code: Optional[str] = None) -> float:
    """NSP per $1,000 at ``duration + 1`` from ``nsp`` at ``duration`` (unrounded)."""
    return roll_step(nsp, table_code, interest, issue_age, duration, function_code).value


def rounding_tolerance(step: RollStep, output_in_cents: bool) -> float:
    """How far a stored value may sit from ``step`` through rounding alone: the cents
    rounding of the value rolled from (+-0.005, carried through ``(1 + i) / (1 - q)``)
    plus the stored value's own rounding."""
    carried = 0.005 * (1.0 + step.interest) / (1.0 - step.q)
    return carried + (0.005 if output_in_cents else 0.0000005) + 1e-9


# The fixed tolerances of the population check (LOW_DUR_1 from LOW_DUR, LOW_DUR_2 from LOW_DUR_1).
STEP_TOLERANCES = (0.0115, 0.0058)


def stored_step_tolerance(step: RollStep, index: int) -> float:
    """The tolerance a stored-value check allows: the fixed one or the rounding propagation, if larger."""
    return max(STEP_TOLERANCES[index], rounding_tolerance(step, output_in_cents=index == 0))
