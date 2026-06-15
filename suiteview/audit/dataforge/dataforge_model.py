"""
DataForge model — a saved combination of Queries (the **Forge**) that joins and
queries several **Sources** with DuckDB over cached **Snapshots**.

Persisted as JSON in ~/.suiteview/saved_dataforges/<name>.json; each Source's
Snapshot is a parquet file under ~/.suiteview/saved_dataforges/<name>/.

Vocabulary & decisions (see DATAFORGE_DESIGN.md):
- A **Source** is an *editable copy* of a Query: it carries its own
  ``definition`` (a QueryObject dict) plus its own ``filters`` and ``snapshot``,
  so editing a Source never touches the shared Query and a Forge stays stable.
- **Refresh** re-pulls a Source's data (updates its Snapshot). **Re-sync**
  pulls the latest *definition* from the original shared Query (opt-in).
- ``query_name`` is retained only so Re-sync knows which shared Query to pull.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SourceSnapshot:
    """Metadata about a Source's cached parquet Snapshot.

    The parquet file itself lives on disk (managed by dataforge_store); this
    records what it contains and when it was pulled, plus whether it is stale
    (definition or Source filters changed since the last Refresh).
    """
    created_at: str = ""           # ISO timestamp of the last Refresh
    row_count: int = 0
    columns: list[str] = field(default_factory=list)
    stale: bool = False            # True => "Refresh to apply" pending changes

    @property
    def exists(self) -> bool:
        """Whether a Refresh has ever produced a Snapshot (metadata present)."""
        return bool(self.created_at)

    def to_dict(self) -> dict:
        return {
            "created_at": self.created_at,
            "row_count": self.row_count,
            "columns": list(self.columns),
            "stale": self.stale,
        }

    @staticmethod
    def from_dict(data: dict | None) -> SourceSnapshot:
        data = data or {}
        return SourceSnapshot(
            created_at=data.get("created_at", ""),
            row_count=data.get("row_count", 0),
            columns=list(data.get("columns", [])),
            stale=data.get("stale", False),
        )


@dataclass
class DataForgeSource:
    """One Query included in a Forge, as an editable copy.

    ``definition`` is a QueryObject dict (the copied, Forge-local definition).
    ``filters`` are Source-scope filters (FilterSpec-shaped dicts) that narrow
    this one dataset before it joins. ``snapshot`` tracks the cached parquet.
    """
    query_name: str                       # original shared Query (for Re-sync)
    query_object_id: str = ""              # permanent id of the Forge-local QueryObject
    alias: str = ""                        # short handle used in joins/filters
    definition: dict[str, Any] = field(default_factory=dict)
    filters: list[dict[str, Any]] = field(default_factory=list)
    snapshot: SourceSnapshot = field(default_factory=SourceSnapshot)
    synced_at: str = ""                    # when definition was last Re-synced

    def effective_alias(self) -> str:
        """The handle to use in SQL — falls back to the Query name."""
        return self.alias or self.query_name

    def to_dict(self) -> dict:
        return {
            "query_name": self.query_name,
            "query_object_id": self.query_object_id,
            "alias": self.alias,
            "definition": self.definition,
            "filters": self.filters,
            "snapshot": self.snapshot.to_dict(),
            "synced_at": self.synced_at,
        }

    @staticmethod
    def from_dict(data: dict) -> DataForgeSource:
        return DataForgeSource(
            query_name=data["query_name"],
            query_object_id=data.get("query_object_id", ""),
            alias=data.get("alias", ""),
            definition=data.get("definition", {}) or {},
            filters=list(data.get("filters", [])),
            snapshot=SourceSnapshot.from_dict(data.get("snapshot")),
            synced_at=data.get("synced_at", ""),
        )


@dataclass
class DataForge:
    """A named Forge — joins/queries several Queries (as Sources) via DuckDB."""
    name: str
    sources: list[DataForgeSource] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)  # join/filter/display state
    created_at: datetime = field(default_factory=datetime.now)

    def source_by_alias(self, alias: str) -> DataForgeSource | None:
        for s in self.sources:
            if s.effective_alias() == alias:
                return s
        return None

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
