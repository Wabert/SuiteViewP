"""Plain view models shared by ABR Quote UI panels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.assessment_solver import AssessmentInputs, AssessmentResultViewModel


@dataclass(frozen=True)
class AssessmentFormState:
    """Snapshot of the Assessment panel form."""

    inputs: AssessmentInputs


@dataclass(frozen=True)
class AccelerationInputState:
    """User-entered acceleration/minimum-face values and related warnings."""

    acceleration_amount: float = 0.0
    min_face_amount: float = 0.0
    after_partial_override: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CalcViewerModel:
    """Data required by the calculation-detail viewer."""

    mortality_rows: list[dict]
    apv_rows: list[dict]
    apv_summary: dict[str, Any]
    policy_info: str = ""
    policy: Any = None
    assessment: Any = None
    result: Any = None
    derived_values: dict[str, str] = field(default_factory=dict)
    acceleration: AccelerationInputState = field(default_factory=AccelerationInputState)


__all__ = [
    "AccelerationInputState",
    "AssessmentFormState",
    "AssessmentResultViewModel",
    "CalcViewerModel",
]
