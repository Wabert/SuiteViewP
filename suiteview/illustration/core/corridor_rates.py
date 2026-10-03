"""7702 GPT corridor factors from UL_Rates schema ``rates`` PLAN ``CORR``.

``PlancodeConfig.corridor_by_age`` holds the plan's ``CORR`` by attained age (grain
AA). The factors do NOT vary by sex or rate class. A plan without ``CORR``:

* **ISWL** — CyberLife applies the standard 7702 corridor to ISWL GPT policies, but
  schema ``rates`` has no ``CORR`` for the ISWL plans yet. Until it does, they use the
  standard set in ``plancodes/tRates_CORR.json`` (logged once per plancode; the RERUN
  load shows a notice). This is the only use of that file.
* **anything else** (CVAT-only UL plans, whose minimum death benefit is the deemed cash
  value test in ``deemed_cash_value``) — no GPT corridor, factor 1.0.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict

from suiteview.illustration.models.plan_facts import corridor_factor_at
from suiteview.illustration.models.plancode_config import PlancodeConfig

logger = logging.getLogger(__name__)

NO_CORRIDOR = 1.0
ISWL_FALLBACK_PATH = Path(__file__).resolve().parent.parent / "plancodes" / "tRates_CORR.json"
_WARNED: set[str] = set()


@lru_cache(maxsize=1)
def _iswl_fallback_corridor() -> Dict[int, float]:
    with open(ISWL_FALLBACK_PATH, "r", encoding="utf-8") as f:
        return {int(age): float(value) for age, value in json.load(f)["corridor"].items()}


def uses_iswl_corridor_fallback(config: PlancodeConfig) -> bool:
    """Whether the plan's corridor is the tRates_CORR.json standard set (ISWL without CORR)."""
    return config.is_iswl and not config.corridor_by_age


def corridor_factor(config: PlancodeConfig, attained_age: int) -> float:
    """The GPT corridor factor at an attained age (past either end of the table, the end
    value); 1.0 when a non-ISWL plan has no ``CORR``."""
    if config.corridor_by_age:
        return corridor_factor_at(config.corridor_by_age, attained_age)
    if uses_iswl_corridor_fallback(config):
        if config.plancode not in _WARNED:
            _WARNED.add(config.plancode)
            logger.warning(
                "%s (ISWL) has no CORR in UL_Rates schema rates; using the standard 7702 "
                "corridor from %s", config.plancode, ISWL_FALLBACK_PATH.name)
        return corridor_factor_at(_iswl_fallback_corridor(), attained_age)
    return NO_CORRIDOR
