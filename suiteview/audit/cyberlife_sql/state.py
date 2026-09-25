"""Mutable SQL build state for CyberLife query assembly."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..cyberlife_criteria import AuditCriteria


@dataclass
class SqlParts:
    lines: list[str] = field(default_factory=list)
    wheres: list[str] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)


@dataclass
class BuildState:
    criteria: AuditCriteria
    parts: SqlParts = field(default_factory=SqlParts)
    _result: str = ""

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)
