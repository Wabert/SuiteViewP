"""Net single premiums for paid-up insurance from CyberLife mortality tables.

CyberLife values paid-up additions and reduced paid-up insurance at the net single
premium of whole life insurance on the addition's own basis: the mortality table
(CKAPTB32 code, e.g. ``N0`` = 1980 CSO male nonsmoker ANB) and interest rate stored
on each ``LH_PAID_UP_ADD`` row, or the coverage's ``NSP_RPU_TBL_CD``/``NSP_ITS_RT``
(CyberDoc S45 ``CKISPUAV``: "the net single premium is calculated by calling the
reduced paid-up net single premium calculation series").

The NSP per $1,000 at attained age ``x`` is whole life insurance to the table's last age
(whose q is 1): ``1000 * sum(v**(k+1) * kpx * q(x+k))``. Age-last-birthday tables
(description "ALB" / "Age Last") pay claims immediately, so their NSP carries the
``i / ln(1 + i)`` factor. Reproduced to the cent:

* CyberLife's stored RPU NSPs (``LOW_DUR_*_NSP_AMT``): 10150100 (table O, 3%, curtate)
  and 14766291 / 13551097 / 12142776 (LP 4%, L5 4.5%, L5 6%, immediate claims);
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
from typing import Dict, Tuple

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
    claims_factor: float     # i / ln(1 + i) for age-last-birthday tables, else 1
    nsp: float               # per $1,000

    @property
    def discount_factor(self) -> float:
        return 1.0 / (1.0 + self.interest)

    @property
    def curtate_sum(self) -> float:
        return self.terms[-1].cumulative if self.terms else 0.0


def nsp_workup(code: str, interest: float, attained_age: int) -> NSPWorkup:
    """The whole life NSP per $1,000 at ``attained_age`` with every term of its sum."""
    table = mortality_table(code)
    if attained_age < table.first_age:
        raise NSPError(
            f"Mortality table {table.code} starts at age {table.first_age}; no NSP at age {attained_age}.")
    rate = float(interest)
    immediate = table.age_last_birthday and rate > 0
    factor = rate / math.log(1.0 + rate) if immediate else 1.0
    if attained_age > table.last_age:
        return NSPWorkup(table, rate, attained_age, (), factor, 1000.0)
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
    if immediate:
        total *= factor
    return NSPWorkup(table, rate, attained_age, tuple(terms), factor, total * 1000.0)


@lru_cache(maxsize=8192)
def net_single_premium(code: str, interest: float, attained_age: int) -> float:
    """Whole life net single premium per $1,000 at ``attained_age``."""
    return nsp_workup(code, interest, attained_age).nsp


def interpolated_nsp(code: str, interest: float, start_age: int, month_of_year: int) -> Tuple[float, float, float]:
    """(NSP at the policy year's start age, at the next age, monthly interpolation)."""
    start = net_single_premium(code, interest, start_age)
    end = net_single_premium(code, interest, start_age + 1)
    return start, end, (start * (12 - month_of_year) + end * month_of_year) / 12.0
