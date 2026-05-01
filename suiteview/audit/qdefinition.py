"""
QDefinition model — a fully-specified, executable query that captures
the exact SQL, bound parameter values, target database, connection,
and expected result schema (field names and types).

Produced by applying specific inputs to a Query Design.
Persisted as JSON in ~/.suiteview/qdefinitions/<forge_name>/<name>.json
Snapshots stored as .parquet in the same folder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class QDefinition:
    """A fully-specified, executable query definition."""
    name: str
    forge_name: str = ""                             # DataForge this QDef belongs to
    sql: str = ""                                    # fully-rendered SQL
    dsn: str = ""                                    # connection DSN
    source_design: str = ""                          # name of the Query Design that produced this
    result_columns: list[str] = field(default_factory=list)
    column_types: dict[str, str] = field(default_factory=dict)
    tables: list[str] = field(default_factory=list)
    display_names: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "forge_name": self.forge_name,
            "sql": self.sql,
            "dsn": self.dsn,
            "source_design": self.source_design,
            "result_columns": self.result_columns,
            "column_types": self.column_types,
            "tables": self.tables,
            "display_names": self.display_names,
            "created_at": self.created_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict) -> QDefinition:
        return QDefinition(
            name=data["name"],
            forge_name=data.get("forge_name", ""),
            sql=data.get("sql", ""),
            dsn=data.get("dsn", ""),
            source_design=data.get("source_design", ""),
            result_columns=data.get("result_columns", []),
            column_types=data.get("column_types", {}),
            tables=data.get("tables", []),
            display_names=data.get("display_names", {}),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now().isoformat())
            ),
        )
