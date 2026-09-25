"""CyberLife (DB2) query builder orchestrator."""
from __future__ import annotations

from ..cyberlife_criteria import AuditCriteria
from .state import BuildState
from .context import build_step_001, build_step_002
from .ctes_policy import build_step_003, build_step_004, build_step_005
from .ctes_values import build_step_006, build_step_007, build_step_008, build_step_009
from .joins import build_step_016, build_step_017, build_step_018, build_step_019
from .select_display import build_step_013, build_step_014, build_step_015
from .select_policy import build_step_010, build_step_011, build_step_012
from .where_advanced import build_step_023, build_step_024
from .where_policy import build_step_020, build_step_021, build_step_022


def build_cyberlife_sql(criteria: AuditCriteria) -> str:
    """Build the CyberLife audit SQL from widget-free audit criteria."""
    state = BuildState(criteria)
    build_step_001(state)
    build_step_002(state)
    build_step_003(state)
    build_step_004(state)
    build_step_005(state)
    build_step_006(state)
    build_step_007(state)
    build_step_008(state)
    build_step_009(state)
    build_step_010(state)
    build_step_011(state)
    build_step_012(state)
    build_step_013(state)
    build_step_014(state)
    build_step_015(state)
    build_step_016(state)
    build_step_017(state)
    build_step_018(state)
    build_step_019(state)
    build_step_020(state)
    build_step_021(state)
    build_step_022(state)
    build_step_023(state)
    build_step_024(state)
    return state._result
