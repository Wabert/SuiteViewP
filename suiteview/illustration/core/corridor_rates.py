"""Corridor factors: UL_Rates schema ``rates`` PLAN ``CORR`` first, tRates_CORR.json as fallback.

7702 statutory corridor factors (GPT) by attained age; they do NOT vary by sex or
rate class. ``PlancodeConfig.corridor_by_age`` holds the plan's schema ``CORR``
(grain AA). Only a plan without ``CORR`` falls back to the local ``tRates_CORR.json``
set named by its plancode-table ``CorridorCode`` (or the file's ``plancode_map``).

Separate from CVAT minimum-death-benefit ratios (MDBR) which are
stored in tRates_MDBR.json and vary by plancode, sex, and rateclass.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from suiteview.illustration.models.plan_facts import corridor_factor_at
from suiteview.illustration.models.plancode_config import PlancodeConfig

_TABLE_PATH = Path(__file__).resolve().parent.parent / "plancodes" / "tRates_CORR.json"
_CACHE: Optional[dict] = None


def _load_table() -> dict:
    """Load and cache the tRates_CORR JSON table."""
    global _CACHE
    if _CACHE is None:
        with open(_TABLE_PATH, "r", encoding="utf-8") as f:
            _CACHE = json.load(f)
    return _CACHE


def corridor_factor(config: PlancodeConfig, attained_age: int) -> float:
    """The corridor factor for a plancode at an attained age.

    Schema ``CORR`` when the plan carries it; otherwise the tRates_CORR.json
    fallback. Past either end of a table the end value applies; a plan in
    neither source gets 1.0 (no corridor).
    """
    if config.corridor_by_age:
        return corridor_factor_at(config.corridor_by_age, attained_age)
    return _fallback_corridor_factor(config.plancode, attained_age, config.corridor_code)


def _fallback_corridor_factor(plancode: str, attained_age: int, corridor_code: int | None) -> float:
    table = _load_table()

    set_id = corridor_code
    if set_id is None:
        plancode_map: Dict[str, int] = table.get("plancode_map", {})
        set_id = plancode_map.get(plancode)
    if set_id is None:
        return 1.0

    sets: Dict[str, dict] = table.get("sets", {})
    rate_set = sets.get(str(set_id))
    if not rate_set:
        return 1.0
    return corridor_factor_at({int(age): float(v) for age, v in rate_set.items()}, attained_age)
