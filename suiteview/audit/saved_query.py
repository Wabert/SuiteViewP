"""
SavedQuery model — a snapshot of a dynamic query's full designer config.

Persisted as JSON in ~/.suiteview/saved_queries/<name>.json
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SavedQuery:
    """A named snapshot of a dynamic query design."""
    name: str
    source_group: str = ""       # group name it was saved from
    dsn: str = ""
    tables: list[str] = field(default_factory=list)
    display_names: dict[str, str] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)  # full get_config() snapshot
    sql: str = ""                # generated SQL at save time
    result_columns: list[str] = field(default_factory=list)  # column names from last run
    column_types: dict[str, str] = field(default_factory=dict)  # col -> type e.g. {"POLNO": "VARCHAR(20)"}
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source_group": self.source_group,
            "dsn": self.dsn,
            "tables": self.tables,
            "display_names": self.display_names,
            "config": self.config,
            "sql": self.sql,
            "result_columns": self.result_columns,
            "column_types": self.column_types,
            "created_at": self.created_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict) -> SavedQuery:
        result_columns = data.get("result_columns", [])

        # Backfill result_columns from config.select_tab.fields when missing
        if not result_columns:
            select_tab = data.get("config", {}).get("select_tab", {})
            if not select_tab.get("display_all", False):
                for f in select_tab.get("fields", []):
                    key = f.get("field_key", "")
                    col = key.rsplit(".", 1)[-1] if key else ""
                    if col:
                        result_columns.append(col)

        return SavedQuery(
            name=data["name"],
            source_group=data.get("source_group", ""),
            dsn=data.get("dsn", ""),
            tables=data.get("tables", []),
            display_names=data.get("display_names", {}),
            config=data.get("config", {}),
            sql=data.get("sql", ""),
            result_columns=result_columns,
            column_types=data.get("column_types", {}),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now().isoformat())
            ),
        )
