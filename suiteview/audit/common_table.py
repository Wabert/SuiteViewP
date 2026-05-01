"""
CommonTable model — a user-defined lookup/translation table.

Rendered as a VALUES-based CTE (WITH clause) at query time so users
can join reference data against live database tables without needing
write access to any database.

Persisted as JSON in ~/.suiteview/common_tables/<name>.json
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# Allowed column types (used for display; all data stored as strings)
COLUMN_TYPES = ("TEXT", "INTEGER", "DECIMAL")


@dataclass
class CommonTable:
    """A user-defined lookup / translation table."""

    name: str
    description: str = ""
    columns: list[dict] = field(default_factory=list)
    # Each column dict: {"name": str, "type": "TEXT"|"INTEGER"|"DECIMAL"}
    rows: list[list] = field(default_factory=list)
    # Each row is a list of string values, positionally matched to columns
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # ── Serialisation ────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "columns": self.columns,
            "rows": self.rows,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict) -> CommonTable:
        return CommonTable(
            name=data["name"],
            description=data.get("description", ""),
            columns=data.get("columns", []),
            rows=data.get("rows", []),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now().isoformat())
            ),
            updated_at=datetime.fromisoformat(
                data.get("updated_at", datetime.now().isoformat())
            ),
        )

    # ── Helpers ──────────────────────────────────────────────────

    @property
    def column_names(self) -> list[str]:
        return [c["name"] for c in self.columns]

    @property
    def column_count(self) -> int:
        return len(self.columns)

    @property
    def row_count(self) -> int:
        return len(self.rows)
