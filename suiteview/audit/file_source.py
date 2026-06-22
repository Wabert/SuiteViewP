"""
FileDataSource model — a flat-file *data source* (peer of a DSN), not a query.

A FileDataSource captures a file *type* once — its format, parsing spec, and
column schema — then points at a LIST of member files that all share that type
(e.g. CLAIMS.txt and a sibling RGACLAIMS.txt in another folder). **Each member
file is exposed as its own table**; queries reference them by table name and
UNION in SQL when they want them combined.

Queries run against a FileDataSource through the existing Visual / Manual
builders, compiled to DuckDB and executed over the member files (see
``file_query_runner``). This deliberately splits the file *type* from the
*query* — the old ``adhoc_source`` QueryObject conflated both (parsing spec +
columns + a single path + one light query) in a single object, which broke down
as soon as you wanted many files of one type with real queries on top.

The parsing spec (``parse_spec``) is intentionally the same dict shape the
``adhoc_source_intake`` readers consume, so loading a member is just
``{**parse_spec, "path": member.path}`` — no parallel parsing logic.

This module is pure data (no pandas / PyQt), so it stays unit-testable on the
minipc. The DataFrame loading + DuckDB execution live in ``file_query_runner``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

# Source-type vocabulary — matches adhoc_source_intake's dispatch keys so the
# same readers parse a member file.
SOURCE_TYPE_CSV = "csv"
SOURCE_TYPE_FIXED_WIDTH = "fixed_width"
SOURCE_TYPE_EXCEL = "excel"
SUPPORTED_SOURCE_TYPES = (SOURCE_TYPE_CSV, SOURCE_TYPE_FIXED_WIDTH, SOURCE_TYPE_EXCEL)


@dataclass
class FileColumn:
    """One column in a File Source's schema (defined once, applies to every member)."""

    name: str
    data_type: str = "TEXT"
    display_name: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "data_type": self.data_type,
            "display_name": self.display_name,
        }

    @staticmethod
    def from_dict(data: dict) -> "FileColumn":
        return FileColumn(
            name=data["name"],
            data_type=data.get("data_type", "TEXT"),
            display_name=data.get("display_name", ""),
        )


@dataclass
class FileMember:
    """One physical file in a File Source — its own DuckDB table."""

    path: str
    table_name: str = ""  # explicit DuckDB table name; defaults to the file stem
    label: str = ""

    def resolved_table_name(self) -> str:
        """The name this file is queried by (explicit, else the file stem)."""
        explicit = (self.table_name or "").strip()
        if explicit:
            return explicit
        return Path(self.path).stem

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "table_name": self.table_name,
            "label": self.label,
        }

    @staticmethod
    def from_dict(data: dict) -> "FileMember":
        return FileMember(
            path=data["path"],
            table_name=data.get("table_name", ""),
            label=data.get("label", ""),
        )


@dataclass
class FileDataSource:
    """A named flat-file data source: one parsing spec + schema over many files."""

    name: str
    source_type: str = SOURCE_TYPE_CSV
    parse_spec: dict[str, Any] = field(default_factory=dict)
    columns: list[FileColumn] = field(default_factory=list)
    members: list[FileMember] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    # Permanent identity (uuid4 hex) — names need NOT be unique; queries and the
    # store reference a File Source by id (mirrors QueryObject.id).
    id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def table_names(self) -> list[str]:
        return [m.resolved_table_name() for m in self.members]

    def member_metadata(self, member: FileMember) -> dict[str, Any]:
        """The ad-hoc-intake metadata dict for loading one member file."""
        meta = dict(self.parse_spec)
        meta["path"] = member.path
        return meta

    def find_member_by_table(self, table_name: str) -> FileMember | None:
        for member in self.members:
            if member.resolved_table_name() == table_name:
                return member
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "source_type": self.source_type,
            "parse_spec": self.parse_spec,
            "columns": [c.to_dict() for c in self.columns],
            "members": [m.to_dict() for m in self.members],
            "description": self.description,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict) -> "FileDataSource":
        return FileDataSource(
            id=data.get("id") or uuid4().hex,  # legacy objects: stamp now
            name=data["name"],
            source_type=data.get("source_type", SOURCE_TYPE_CSV),
            parse_spec=dict(data.get("parse_spec", {})),
            columns=[FileColumn.from_dict(c) for c in data.get("columns", [])],
            members=[FileMember.from_dict(m) for m in data.get("members", [])],
            description=data.get("description", ""),
            tags=list(data.get("tags", [])),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now().isoformat())
            ),
            updated_at=datetime.fromisoformat(
                data.get("updated_at", datetime.now().isoformat())
            ),
        )


def datasource_label(file_source: FileDataSource) -> str:
    """The bracketed datasource tag for display (parallel to a DSN label)."""
    labels = {
        SOURCE_TYPE_CSV: "CSV",
        SOURCE_TYPE_FIXED_WIDTH: "Fixed Width",
        SOURCE_TYPE_EXCEL: "Excel",
    }
    return labels.get(file_source.source_type, file_source.source_type or "File")
