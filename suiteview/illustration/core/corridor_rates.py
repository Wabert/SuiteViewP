"""Corridor factor loader — reads from tRates_CORR.json.

7702 statutory corridor factors (GPT) keyed by CorridorCode and
attained age.  There are only 3 sets — they share the same rate
curve (ages 0-94) and differ only in tail behavior past age 94.
They do NOT vary by sex or rate class.

Separate from CVAT minimum-death-benefit ratios (MDBR) which are
stored in tRates_MDBR.json and vary by plancode, sex, and rateclass.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


_TABLE_PATH = Path(__file__).resolve().parent.parent / "plancodes" / "tRates_CORR.json"
_CACHE: Optional[dict] = None


def _load_table() -> dict:
    """Load and cache the tRates_CORR JSON table."""
    global _CACHE
    if _CACHE is None:
        with open(_TABLE_PATH, "r") as f:
            _CACHE = json.load(f)
    return _CACHE


def get_corridor_factor(plancode: str, attained_age: int) -> float:
    """Look up the corridor factor for a plan code at a given attained age.

    Args:
        plancode: Product plan code (e.g., "1U143900").
        attained_age: Current attained age of the insured.

    Returns:
        Corridor factor (e.g. 1.34 at age 59).  Returns 1.0 if the
        plan code is not found or the age is beyond the table range.
    """
    table = _load_table()

    plancode_map: Dict[str, int] = table.get("plancode_map", {})
    set_id = plancode_map.get(plancode)
    if set_id is None:
        return 1.0

    sets: Dict[str, dict] = table.get("sets", {})
    rate_set = sets.get(str(set_id))
    if rate_set is None:
        return 1.0

    # Direct lookup by attained age (string key in JSON)
    val = rate_set.get(str(attained_age))
    if val is not None:
        return float(val)

    # Age beyond the table — find the nearest available
    ages = sorted(int(a) for a in rate_set.keys())
    if not ages:
        return 1.0

    if attained_age < ages[0]:
        return float(rate_set[str(ages[0])])
    if attained_age > ages[-1]:
        return float(rate_set[str(ages[-1])])

    return 1.0
