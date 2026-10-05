"""7702 GPT corridor factors from UL_Rates schema ``rates`` PLAN ``CORR``.

``PlancodeConfig.corridor_by_age`` holds the plan's ``CORR`` by attained age (grain
AA). The factors do NOT vary by sex or rate class. A plan without ``CORR`` has no GPT
corridor (factor 1.0 here): the CVAT UL plans and the CVAT ISWL plans, whose minimum
death benefit ratio ``face / NS`` comes from ``cvat_nsp.CvatCorridor`` and is passed to
the deduction as ``corridor_rate``. The GPT ISWL plans carry the standard 7702 ``CORR``
in schema ``rates``, matching the in-force CyberLife NAR at attained age.

The corridor death benefit is whole dollars. ISWL plans (GPT ``CORR`` and CVAT
``face / NS``) round ``AV x factor`` half up and UL plans take the FLOOR, as reproduced
from CyberLife's ``LH_POL_MVRY_VAL.NAR_AMT`` (``RERUN_MANUAL.md`` § Corridor death
benefit rounding).
"""
from __future__ import annotations

import math

from suiteview.illustration.models.plan_facts import corridor_factor_at
from suiteview.illustration.models.plancode_config import PlancodeConfig

NO_CORRIDOR = 1.0


def corridor_factor(config: PlancodeConfig, attained_age: int) -> float:
    """The GPT corridor factor at an attained age (past either end of the table, the end
    value); 1.0 when the plan has no ``CORR``."""
    if config.corridor_by_age:
        return corridor_factor_at(config.corridor_by_age, attained_age)
    return NO_CORRIDOR


def corridor_death_benefit(av: float, factor: float, config: PlancodeConfig) -> float:
    """The whole-dollar corridor death benefit ``av x factor``: rounded half up for ISWL
    plans, floored for UL plans. The 1e-6 absorbs float noise at an exact boundary."""
    amount = av * factor
    if config.is_iswl:
        return float(math.floor(amount + 0.5 + 1e-6))
    return float(math.floor(amount + 1e-6))
