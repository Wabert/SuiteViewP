"""7702 GPT corridor factors from UL_Rates schema ``rates`` PLAN ``CORR``.

``PlancodeConfig.corridor_by_age`` holds the plan's ``CORR`` by attained age (grain
AA). The factors do NOT vary by sex or rate class. A plan without ``CORR`` has no GPT
corridor (factor 1.0): the CVAT-only UL plans, whose minimum death benefit is the
deemed cash value test in ``deemed_cash_value``, and the two CVAT ISWL plans
(80136200, B11SB600). The GPT ISWL plans carry the standard 7702 ``CORR`` in schema
``rates``, matching the in-force CyberLife NAR at attained age.
"""
from __future__ import annotations

from suiteview.illustration.models.plan_facts import corridor_factor_at
from suiteview.illustration.models.plancode_config import PlancodeConfig

NO_CORRIDOR = 1.0


def corridor_factor(config: PlancodeConfig, attained_age: int) -> float:
    """The GPT corridor factor at an attained age (past either end of the table, the end
    value); 1.0 when the plan has no ``CORR``."""
    if config.corridor_by_age:
        return corridor_factor_at(config.corridor_by_age, attained_age)
    return NO_CORRIDOR
