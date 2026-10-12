"""Net single premiums for paid-up insurance from CyberLife mortality tables.

CyberLife values paid-up additions and reduced paid-up insurance at the net single
premium of whole life insurance on the addition's own basis: the mortality table
(CKAPTB32 code, e.g. ``N0`` = 1980 CSO male nonsmoker ANB) and interest rate stored
on each ``LH_PAID_UP_ADD`` row, or the coverage's ``NSP_RPU_TBL_CD``/``NSP_ITS_RT``
(CyberDoc S45 ``CKISPUAV``: "the net single premium is calculated by calling the
reduced paid-up net single premium calculation series").

The NSP per $1,000 at attained age ``x`` is whole life insurance to the table's last age
(whose q is 1): ``1000 * sum(v**(k+1) * kpx * q(x+k))``, times the claims factor ``c``.

**Claims basis.** A coverage's mortality function code ``LH_COV_PHA.MTL_FUN_CD``
(CyberDoc D20 p.94, field FCVVFNCT "Function": 0 curtate, 1 semicontinuous (immediate
payment of claims), 2 fully continuous, 3 discounted continuous) decides it: codes 1 and 2
pay claims at death, ``c = i / ln(1 + i)`` (S48 p.250 "Interest/Delta Factor"); code 0 is
curtate, ``c = 1``. CyberDoc describes the code for valuation, but the stored nonforfeiture
NSPs follow it (live CKPR status 45 traditional coverages, 10/9/2026: L0/L1/L5 with code 2
fit ``i / ln(1 + i)``, with code 0 curtate; N5 (age nearest) with code 2 fits ``i / ln(1 + i)``,
with 0 curtate; LP code 2 and OK/OL code 0 as their codes say), whatever the table's age
basis. Code 2 is "fully continuous" in CyberDoc; for a single premium only the claims
timing matters, so it is treated like 1. Code 3 and any other code are refused.

Only when no code is available (``function_code`` None or blank: paid-up additions rows,
``LH_PAID_UP_ADD``, carry a table and rate but no function code) does the table's
description decide: age-last-birthday tables ("ALB" / "Age Last") pay at death. The
additions roll-forwards verified against CyberLife (e.g. 000282131's NB1PU300 rider, whose
coverage code is 1 but whose N0 4.5% additions are curtate) follow that fallback.

Reproduced to the cent:

* CyberLife's stored RPU NSPs (``LOW_DUR_*_NSP_AMT``): plancode 10150100 (table O, 3%,
  code 0, curtate), 14766291 / 13551097 / 12142776 (LP 4%, L5 4.5%, L5 6%, code 2),
  13265849 (09100500, N5 5.75%, code 2: an age-nearest table with immediate claims) and
  08:05201003 (201WL300, L1 6%, code 0: an age-last table, curtate);
* the par WL workbook's NSP sheet: B711E100 (OK 4.5%, curtate), B111A100 (LQ/LP 4%,
  immediate claims) at every age; NB1XSL00 (N0 4%) within 0.1 per $1,000.

The tables are the official ``Mortality Tables (Cyberlife).xlsx`` bundled by
``tools/rerun/build_cyberlife_mortality.py``.
"""
from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional, Tuple

MORTALITY_FILE = Path(__file__).resolve().parents[2] / "plancodes" / "cyberlife_mortality.json"

_LOCK = threading.Lock()
_TABLES: Dict[str, "MortalityTable"] = {}


class NSPError(ValueError):
    """A net single premium cannot be calculated from the bundled tables."""


@dataclass(frozen=True)
class MortalityTable:
    code: str
    description: str
    first_age: int
    qx: Tuple[float, ...]

    @property
    def last_age(self) -> int:
        return self.first_age + len(self.qx) - 1

    @property
    def age_last_birthday(self) -> bool:
        text = self.description.upper()
        return "ALB" in text or "AGE LAST" in text


def _tables() -> Dict[str, MortalityTable]:
    with _LOCK:
        if not _TABLES:
            try:
                payload = json.loads(MORTALITY_FILE.read_text(encoding="utf-8"))
            except OSError as exc:
                raise NSPError(f"CyberLife mortality tables are missing: {MORTALITY_FILE}") from exc
            for code, table in payload["tables"].items():
                _TABLES[code.strip()] = MortalityTable(
                    code.strip(), str(table.get("description", "")), int(table["first_age"]),
                    tuple(float(q) for q in table["qx"]))
        return _TABLES


def mortality_table(code: str) -> MortalityTable:
    """The CKAPTB32 mortality table for ``code``."""
    table = _tables().get(str(code or "").strip())
    if table is None:
        raise NSPError(f"Mortality table {str(code).strip() or '(blank)'} is not in the bundled CyberLife tables.")
    return table


# LH_COV_PHA.MTL_FUN_CD (CyberDoc D20 p.94, FCVVFNCT "Function").
FUNCTION_CODES = {
    "0": "curtate",
    "1": "semicontinuous (immediate payment of claims)",
    "2": "fully continuous",
    "3": "discounted continuous",
}
IMMEDIATE_CLAIMS_CODES = frozenset({"1", "2"})
CURTATE_CODES = frozenset({"0"})


def normalize_function_code(function_code) -> Optional[str]:
    """``MTL_FUN_CD`` stripped; None when no code is available (None or blank)."""
    text = str(function_code if function_code is not None else "").strip()
    return text or None


def function_code_text(function_code) -> str:
    """``"2 fully continuous"``, or a note that no code is available."""
    code = normalize_function_code(function_code)
    if code is None:
        return "none on the record"
    return f"{code} {FUNCTION_CODES.get(code, 'unknown')}"


def claims_factor_for(function_code, interest: float) -> float:
    """The claims factor of mortality function code ``function_code`` (``MTL_FUN_CD``).

    Codes 1 (semicontinuous) and 2 (fully continuous) pay claims at death:
    ``i / ln(1 + i)`` (CyberDoc S48 p.250). For a single premium only the claims timing
    matters, so "fully continuous" is not a different premium basis here. Code 0 is
    curtate: 1. Code 3 (discounted continuous) and unknown codes raise ``NSPError``.
    """
    code = normalize_function_code(function_code)
    if code in IMMEDIATE_CLAIMS_CODES:
        rate = float(interest)
        return rate / math.log(1.0 + rate) if rate > 0 else 1.0
    if code in CURTATE_CODES:
        return 1.0
    if code is None:
        raise NSPError("No mortality function code (MTL_FUN_CD) was given.")
    raise NSPError(
        f"Mortality function code (MTL_FUN_CD) {code} ({FUNCTION_CODES.get(code, 'unknown code')}) is not "
        "supported: only 0 (curtate) and 1/2 (claims paid at death, i / ln(1 + i)) have been verified "
        "against CyberLife's stored net single premiums (CyberDoc D20 p.94).")


def claims_basis(table: MortalityTable, interest: float, function_code=None) -> Tuple[float, str]:
    """(claims factor, how it was decided) for ``table`` at ``interest``.

    The coverage's ``MTL_FUN_CD`` decides when given; without one (paid-up additions rows
    carry only a table and rate) the table's description does: age last birthday pays at
    death, otherwise curtate.
    """
    code = normalize_function_code(function_code)
    rate = float(interest)
    if code is not None:
        factor = claims_factor_for(code, rate)
        timing = "claims paid at death, i / ln(1 + i)" if code in IMMEDIATE_CLAIMS_CODES \
            else "claims at the end of the year of death (curtate), 1"
        return factor, f"MTL_FUN_CD {function_code_text(code)} (CyberDoc D20 p.94): {timing}"
    if table.age_last_birthday and rate > 0:
        return (rate / math.log(1.0 + rate),
                "No MTL_FUN_CD: age-last-birthday table, claims paid at death, i / ln(1 + i)")
    return 1.0, "No MTL_FUN_CD: table not age last birthday, claims at the end of the year (curtate), 1"


@dataclass(frozen=True)
class NSPTerm:
    """One year ``t`` of the NSP sum: death in year ``t`` of a life aged ``x`` now."""

    age: int                 # x + t
    t: int
    q: float                 # q(x+t)
    survival: float          # tpx: alive at the start of year t
    discount: float          # v ** (t + 1)
    term: float              # tpx * q(x+t) * v ** (t + 1)
    cumulative: float        # running sum of the terms through t


@dataclass(frozen=True)
class NSPWorkup:
    """Every term of a net single premium, so the sum can be followed line by line."""

    table: MortalityTable
    interest: float
    attained_age: int
    terms: Tuple[NSPTerm, ...]
    claims_factor: float     # i / ln(1 + i) when claims are paid at death, else 1
    nsp: float               # per $1,000
    function_code: Optional[str] = None   # MTL_FUN_CD used (None: the table fallback)
    claims_rule: str = ""                 # how the claims factor was decided

    @property
    def discount_factor(self) -> float:
        return 1.0 / (1.0 + self.interest)

    @property
    def curtate_sum(self) -> float:
        return self.terms[-1].cumulative if self.terms else 0.0


def nsp_workup(code: str, interest: float, attained_age: int, function_code: Optional[str] = None) -> NSPWorkup:
    """The whole life NSP per $1,000 at ``attained_age`` with every term of its sum.

    ``function_code`` is the coverage's ``MTL_FUN_CD``; None uses the table fallback of
    :func:`claims_basis`.
    """
    table = mortality_table(code)
    if attained_age < table.first_age:
        raise NSPError(
            f"Mortality table {table.code} starts at age {table.first_age}; no NSP at age {attained_age}.")
    rate = float(interest)
    fun = normalize_function_code(function_code)
    factor, rule = claims_basis(table, rate, fun)
    if attained_age > table.last_age:
        return NSPWorkup(table, rate, attained_age, (), factor, 1000.0, fun, rule)
    v = 1.0 / (1.0 + rate)
    total, survival, discount = 0.0, 1.0, 1.0
    terms = []
    for t, age in enumerate(range(attained_age, table.last_age + 1)):
        discount *= v
        q = table.qx[age - table.first_age]
        term = survival * q * discount
        total += term
        terms.append(NSPTerm(age, t, q, survival, discount, term, total))
        survival *= 1.0 - q
    if factor != 1.0:
        total *= factor
    return NSPWorkup(table, rate, attained_age, tuple(terms), factor, total * 1000.0, fun, rule)


@lru_cache(maxsize=8192)
def net_single_premium(code: str, interest: float, attained_age: int, function_code: Optional[str] = None) -> float:
    """Whole life net single premium per $1,000 at ``attained_age`` (the cache key includes
    the function code, so each claims basis is cached apart)."""
    return nsp_workup(code, interest, attained_age, function_code).nsp


def interpolated_nsp(code: str, interest: float, start_age: int, month_of_year: int,
                     function_code: Optional[str] = None) -> Tuple[float, float, float]:
    """(NSP at the policy year's start age, at the next age, monthly interpolation)."""
    start = net_single_premium(code, interest, start_age, function_code)
    end = net_single_premium(code, interest, start_age + 1, function_code)
    return start, end, (start * (12 - month_of_year) + end * month_of_year) / 12.0
