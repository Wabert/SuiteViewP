"""Explicit SQL state objects for CyberLife query assembly."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..cyberlife_criteria import AuditCriteria


@dataclass(slots=True)
class SqlParts:
    sql_parts: list[str] = field(default_factory=list)
    wheres: list[str] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    result: str = ""


@dataclass(frozen=True, slots=True)
class SqlFragment:
    """Immutable SQL lines produced by one assembly section."""

    ctes: tuple[str, ...] = ()
    selects: tuple[str, ...] = ()
    joins: tuple[str, ...] = ()
    wheres: tuple[str, ...] = ()
    order: tuple[str, ...] = ()
    result: str = ""


@dataclass(frozen=True, slots=True)
class DerivedAuditContext:
    """Frozen criteria-derived facts shared by CyberLife SQL fragments."""

    criteria: AuditCriteria
    values: Mapping[str, Any]
    initial_ctes: tuple[str, ...] = ()

    def __getattr__(self, name: str) -> Any:
        try:
            return self.values[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class QueryContext:
    """Compatibility view over :class:`DerivedAuditContext` for legacy helpers."""

    __slots__ = ("derived", "__dict__")

    def __init__(self, source: AuditCriteria | DerivedAuditContext) -> None:
        if isinstance(source, DerivedAuditContext):
            self.derived = source
            self.criteria = source.criteria
            self.__dict__.update(source.values)
        else:
            self.derived = None
            self.criteria = source
