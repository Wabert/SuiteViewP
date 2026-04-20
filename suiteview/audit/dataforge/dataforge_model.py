"""
DataForge model — a cross-query dataset definition that merges multiple
saved queries using pandas operations.

Persisted as JSON in ~/.suiteview/saved_dataforges/<name>.json
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DataForgeSource:
    """One saved-query input to a DataForge."""
    query_name: str          # name of the SavedQuery
    alias: str = ""          # short alias for referencing in joins/filters

    def to_dict(self) -> dict:
        return {"query_name": self.query_name, "alias": self.alias}

    @staticmethod
    def from_dict(data: dict) -> DataForgeSource:
        return DataForgeSource(
            query_name=data["query_name"],
            alias=data.get("alias", ""),
        )


@dataclass
class DataForge:
    """A named DataForge — merges saved queries via pandas."""
    name: str
    sources: list[DataForgeSource] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)  # filter/join/display state
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "sources": [s.to_dict() for s in self.sources],
            "config": self.config,
            "created_at": self.created_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict) -> DataForge:
        return DataForge(
            name=data["name"],
            sources=[DataForgeSource.from_dict(s)
                     for s in data.get("sources", [])],
            config=data.get("config", {}),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now().isoformat())
            ),
        )
