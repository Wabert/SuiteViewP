"""
Intake + validation for File Sources — the logic behind "add a file" and the
drag-and-drop drop target.

A File Source's *type* (format + parse spec + column schema) is established by
its **first** file. Every file added afterwards must match that type, so a
``FileDataSource`` always describes one consistent shape of file spread across
many physical files (CLAIMS.txt, RGACLAIMS.txt, ...). This module:

- ``infer_file_source_from_file`` — build a new FileDataSource from a first file
  (reuses ``adhoc_source_intake`` inference so columns/types/parse spec match the
  rest of the app).
- ``validate_member_file`` — does a candidate file parse with this source's
  format and contain its schema columns? Returns the missing columns.
- ``add_member_file`` — validate, dedupe, and append a member.

Pure logic (pandas via the shared readers, no PyQt) so it's unit-testable on the
minipc.
"""
from __future__ import annotations

import os
from pathlib import Path

from suiteview.audit.adhoc_source_intake import (
    dataframe_from_adhoc_metadata,
    query_object_from_file,
)
from suiteview.audit.file_source import FileColumn, FileDataSource, FileMember

# Metadata keys that describe the *file instance*, not the reusable parse spec.
_INSTANCE_KEYS = {"path", "detected_at", "promoted", "promoted_at", "sample_rows"}


class FileValidationError(Exception):
    """Raised when a file cannot be added to a File Source (format/schema mismatch)."""


def _parse_spec_from_metadata(metadata: dict) -> dict:
    """Strip file-instance keys, leaving the reusable parsing spec."""
    return {k: v for k, v in metadata.items() if k not in _INSTANCE_KEYS}


def infer_file_source_from_file(
    path: str | Path,
    *,
    name: str | None = None,
    format_spec: dict | None = None,
    sheet_name: str | int | None = 0,
) -> FileDataSource:
    """Build a new FileDataSource from a first file (format + schema + 1 member)."""
    obj = query_object_from_file(
        path, name=name, format_spec=format_spec, sheet_name=sheet_name)
    source = obj.sources[0]
    parse_spec = _parse_spec_from_metadata(dict(source.metadata))
    columns = [
        FileColumn(name=f.name, data_type=f.data_type,
                   display_name=f.display_name or f.name)
        for f in obj.fields
    ]
    fds = FileDataSource(
        name=obj.name,
        source_type=source.source_type,
        parse_spec=parse_spec,
        columns=columns,
        members=[],
    )
    fds.members.append(
        FileMember(path=str(path),
                   table_name=unique_table_name(fds, Path(path).stem)))
    return fds


def validate_member_file(
    file_source: FileDataSource,
    path: str | Path,
    *,
    sample_rows: int = 50,
) -> list[str]:
    """Return the schema columns MISSING from ``path`` (empty list = it matches).

    Reads a small sample of the candidate file using this source's parse spec; a
    read failure (wrong format) raises FileValidationError.
    """
    metadata = dict(file_source.parse_spec)
    metadata["path"] = str(path)
    try:
        df = dataframe_from_adhoc_metadata(
            file_source.source_type, metadata, nrows=sample_rows)
    except Exception as exc:
        raise FileValidationError(
            "Could not read this file with the source's format "
            f"({file_source.source_type}):\n{exc}") from exc

    file_cols = {str(c).lower() for c in df.columns}
    return [c.name for c in file_source.columns if c.name.lower() not in file_cols]


def _same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def unique_table_name(file_source: FileDataSource, base: str) -> str:
    """A table name not already used by another member (suffixes _2, _3, ...)."""
    existing = {m.resolved_table_name() for m in file_source.members}
    name = (base or "Table").strip() or "Table"
    if name not in existing:
        return name
    n = 2
    while f"{name}_{n}" in existing:
        n += 1
    return f"{name}_{n}"


def add_member_file(
    file_source: FileDataSource,
    path: str | Path,
    *,
    sample_rows: int = 50,
) -> FileMember:
    """Validate ``path`` against the source's format/schema and append it.

    Raises FileValidationError if the file is already present, can't be parsed
    with this source's format, or is missing schema columns.
    """
    path = str(path)
    for member in file_source.members:
        if _same_path(member.path, path):
            raise FileValidationError("That file is already in this source.")

    missing = validate_member_file(file_source, path, sample_rows=sample_rows)
    if missing:
        shown = ", ".join(missing[:10]) + ("…" if len(missing) > 10 else "")
        raise FileValidationError(
            "This file doesn't match the source's columns.\nMissing: " + shown)

    member = FileMember(
        path=path, table_name=unique_table_name(file_source, Path(path).stem))
    file_source.members.append(member)
    return member
