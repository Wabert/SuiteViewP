"""
RegisteredDataSource model — a *named, persisted* connection-style data source.

A File Source (``file_source.py``) is rich enough to need its own model+store.
The other source kinds — an ODBC DSN, an MS Access file — are thin: they're a
pointer to where data lives plus a friendly name and some notes. This model
captures those so a DSN can be **registered, named, and health-checked before
any query references it** (the Data Sources tab's "Add Data Source"), instead of
only being *discovered* by scanning which DSNs queries happen to use.

Pure data (no pyodbc / PyQt) so it stays unit-testable on the minipc. Connection
probing and DSN introspection live in ``core/odbc_utils``; the store is
``data_source_store`` (mirrors ``file_source_store``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

KIND_ODBC = "odbc"
KIND_ACCESS = "access"  # reserved for the MS Access slice (not built yet)
SUPPORTED_KINDS = (KIND_ODBC, KIND_ACCESS)


@dataclass
class RegisteredDataSource:
    """A named, persisted data source that points at a connection (DSN / file)."""

    name: str
    kind: str = KIND_ODBC
    dsn: str = ""          # ODBC DSN name (kind == odbc)
    path: str = ""         # file path (kind == access; reserved)
    dialect: str = ""      # DB2 / SQL_SERVER / ACCESS — cached at save time
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    # Permanent identity (uuid4 hex); names need NOT be unique, mirroring
    # FileDataSource / QueryObject.
    id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def target(self) -> str:
        """The thing this source points at — a DSN name or a file path."""
        return self.dsn if self.kind == KIND_ODBC else self.path

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "dsn": self.dsn,
            "path": self.path,
            "dialect": self.dialect,
            "notes": self.notes,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict) -> "RegisteredDataSource":
        return RegisteredDataSource(
            id=data.get("id") or uuid4().hex,
            name=data["name"],
            kind=data.get("kind", KIND_ODBC),
            dsn=data.get("dsn", ""),
            path=data.get("path", ""),
            dialect=data.get("dialect", ""),
            notes=data.get("notes", ""),
            tags=list(data.get("tags", [])),
            created_at=datetime.fromisoformat(
                data.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(
                data.get("updated_at", datetime.now().isoformat())),
        )


def datasource_kind_label(source: RegisteredDataSource) -> str:
    """The bracketed datasource tag for display (parallel to a File Source's)."""
    if source.kind == KIND_ACCESS:
        return "MS Access"
    return source.dialect or "ODBC"
