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
from suiteview.audit.file_source import (
    SOURCE_TYPE_CSV,
    SOURCE_TYPE_FIXED_WIDTH,
    FileColumn,
    FileDataSource,
    FileMember,
)
from suiteview.audit.query_object import OBJECT_KIND_ADHOC_SOURCE

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


def migrate_adhoc_to_file_source(query_object) -> FileDataSource:
    """Convert a legacy ``adhoc_source`` QueryObject into a FileDataSource.

    The old model stored the parse spec + columns + a single file path on one
    QueryObject; this lifts those into a FileDataSource with one member. Caller
    persists the result and removes the legacy QueryObject (see
    ``tools/migrate_adhoc_sources.py``).
    """
    if query_object.kind != OBJECT_KIND_ADHOC_SOURCE:
        raise FileValidationError(
            "Only adhoc_source QueryObjects can be migrated to a File Source.")
    source = query_object.sources[0] if query_object.sources else None
    metadata = dict(source.metadata) if source else {}
    parse_spec = _parse_spec_from_metadata(metadata)
    columns = [
        FileColumn(name=f.name, data_type=f.data_type,
                   display_name=f.display_name or f.name)
        for f in query_object.fields
    ]
    fds = FileDataSource(
        name=query_object.name,
        source_type=(source.source_type if source else query_object.source_design) or "csv",
        parse_spec=parse_spec,
        columns=columns,
        description=query_object.description or "",
        tags=list(query_object.tags or []),
    )
    path = metadata.get("path", "")
    if path:
        fds.members.append(
            FileMember(path=path, table_name=unique_table_name(fds, Path(path).stem)))
    return fds


def parse_column_names(text: str) -> list[str]:
    """Parse user-entered column names (one per line, or comma-separated).

    Raises ValueError if empty or if names collide case-insensitively.
    """
    raw_parts: list[str] = []
    for line in text.splitlines():
        raw_parts.extend(line.split(","))
    names = [part.strip() for part in raw_parts if part.strip()]
    if not names:
        raise ValueError("Enter at least one column name.")
    lowered = [name.lower() for name in names]
    if len(lowered) != len(set(lowered)):
        raise ValueError("Column names must be unique.")
    return names


def _looks_like_fixed_width_line(line: str) -> bool:
    """True if ``line`` is ``name,start,width`` with integer start and width."""
    parts = [part.strip() for part in line.split(",")]
    if len(parts) != 3:
        return False
    try:
        int(parts[1])
        int(parts[2])
    except ValueError:
        return False
    return True


def parse_column_spec_text(text: str) -> tuple[str, list]:
    """Parse the multi-line column-spec box into one of two shapes.

    Returns ``("fixed_width", [{"name", "start", "width"}, ...])`` when *every*
    non-empty line is ``name,start,width`` (integer start/width), otherwise
    ``("names", [name, ...])`` parsed the same way as ``parse_column_names``
    (one per line or comma-separated). Raises ValueError if the box is empty,
    mixes the two formats, or has blank/duplicate names.
    """
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not raw_lines:
        raise ValueError("Enter at least one column.")
    fixed_flags = [_looks_like_fixed_width_line(line) for line in raw_lines]
    if all(fixed_flags):
        columns: list[dict] = []
        for line in raw_lines:
            name, start, width = (part.strip() for part in line.split(","))
            columns.append({"name": name, "start": int(start), "width": int(width)})
        names = [col["name"] for col in columns]
        if any(not name for name in names):
            raise ValueError("Each fixed-width column needs a name.")
        if len({name.lower() for name in names}) != len(names):
            raise ValueError("Column names must be unique.")
        return "fixed_width", columns
    if any(fixed_flags):
        raise ValueError(
            "Mixed formats. Use either one column name per line, or "
            "name,start,width on every line.")
    return "names", parse_column_names(text)


def apply_column_names(file_source: FileDataSource, names: list[str]) -> None:
    """Rename schema columns and push the rename into the parse spec.

    Keeps the schema and the data the readers produce in agreement:
    - Delimited: the readers rename via ``column_names`` (works with or without a
      header row).
    - Fixed-width: each column spec is renamed in place.
    Excel follows the sheet's header row and is not renamed here. Raises
    ValueError if ``names`` doesn't match the current column count.
    """
    current = file_source.columns
    if len(names) != len(current):
        raise ValueError(
            f"Enter exactly {len(current)} names. You entered {len(names)}.")
    for col, new_name in zip(current, names):
        col.name = new_name
    if file_source.source_type == SOURCE_TYPE_CSV:
        file_source.parse_spec["column_names"] = list(names)
    elif file_source.source_type == SOURCE_TYPE_FIXED_WIDTH:
        for spec, new_name in zip(file_source.parse_spec.get("columns", []), names):
            spec["name"] = new_name


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
