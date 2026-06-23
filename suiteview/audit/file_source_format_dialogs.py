"""
Qt prompts for establishing a File Source's format from its first file.

When a flat-file source is created, its *type* (delimiter, header, fixed-width
layout, …) is set by the first file added. These small dialogs ask the user how
to parse a text file and then build the initial ``FileDataSource`` via the pure
``file_source_intake`` inference. They live here (rather than on a widget) so the
single editable File Source screen — the Data Sources dashboard — can drive them
without a dedicated editor.

Cancellation is signalled by raising ``DialogCancelled`` so callers can abort the
add cleanly (no ``None``/``False`` ambiguity).
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QInputDialog, QMessageBox

from suiteview.audit.adhoc_source_intake import delimited_text_spec, fixed_width_spec
from suiteview.audit.file_source import FileDataSource
from suiteview.audit.file_source_intake import infer_file_source_from_file


class DialogCancelled(Exception):
    """The user cancelled a format prompt — abort the add."""


def establish_source_from_first_file(
    parent, path: str, name: str
) -> FileDataSource | None:
    """Infer a new FileDataSource from the first file, prompting for text layout.

    Returns the FileDataSource, or ``None`` if the file could not be read (a
    warning is shown). Raises ``DialogCancelled`` if the user cancels a prompt.
    """
    format_spec = prompt_text_format_spec(parent, path)  # may raise DialogCancelled
    name = (name or "").strip() or Path(path).stem
    try:
        return infer_file_source_from_file(path, name=name, format_spec=format_spec)
    except Exception as exc:  # noqa: BLE001 — surface any read error to the user
        QMessageBox.warning(parent, "Could Not Read File", f"{exc}")
        return None


def prompt_format_spec_for_source(parent, fds) -> dict:
    """Re-prompt the parsing format/layout for an EXISTING source, pre-filled.

    Used to fix a mis-detected text file or change a fixed-width column layout
    after creation. Returns a new parse-spec dict; raises ``DialogCancelled`` if
    the user cancels (or the type can't be re-edited here, e.g. Excel)."""
    from suiteview.audit.file_source import (
        SOURCE_TYPE_CSV, SOURCE_TYPE_EXCEL, SOURCE_TYPE_FIXED_WIDTH)

    path = fds.members[0].path if fds.members else ""
    spec = fds.parse_spec or {}
    if fds.source_type == SOURCE_TYPE_FIXED_WIDTH:
        return _prompt_fixed_width_spec(parent, current=spec.get("columns"))
    if fds.source_type == SOURCE_TYPE_CSV:
        return _prompt_delimited_spec(parent, path, current=spec)
    if fds.source_type == SOURCE_TYPE_EXCEL:
        QMessageBox.information(
            parent, "Excel Format",
            "Excel columns follow the sheet's header row and can't be redefined here.")
        raise DialogCancelled
    raise DialogCancelled


def prompt_text_format_spec(parent, path: str) -> dict | None:
    """Ask how a text file should be parsed.

    Returns an explicit parse-spec dict for a delimited / fixed-width layout, or
    ``None`` to let intake auto-detect (CSV/Excel/auto-delimited). Raises
    ``DialogCancelled`` if the user cancels.
    """
    suffix = Path(path).suffix.lower()
    if suffix not in {".txt", ".dat", ".psv", ".tsv"}:
        return None
    default_mode = "Delimited" if suffix in {".psv", ".tsv"} else "Auto-detect delimited"
    mode, ok = QInputDialog.getItem(
        parent, "Text File Layout", "How should this text file be parsed?",
        [default_mode, "Delimited", "Fixed width"], 0, False)
    if not ok:
        raise DialogCancelled
    if mode == "Fixed width":
        return _prompt_fixed_width_spec(parent)
    if mode == "Delimited":
        return _prompt_delimited_spec(parent, path)
    return None


def _prompt_delimited_spec(parent, path: str, current: dict | None = None) -> dict:
    suffix = Path(path).suffix.lower()
    if current and current.get("delimiter") is not None:
        cur_delim = current["delimiter"]
        default_delimiter = "\\t" if cur_delim == "\t" else cur_delim
    else:
        default_delimiter = {".tsv": "\\t", ".psv": "|"}.get(suffix, ",")
    delimiter_text, ok = QInputDialog.getText(
        parent, "Delimited Text Settings", "Delimiter (use \\t for tab):",
        text=default_delimiter)
    if not ok:
        raise DialogCancelled
    delimiter = delimiter_text or default_delimiter
    delimiter = "\t" if delimiter == "\\t" else delimiter
    header_default = (QMessageBox.StandardButton.Yes
                      if (current is None or current.get("has_header", True))
                      else QMessageBox.StandardButton.No)
    has_header = QMessageBox.question(
        parent, "Delimited Text Settings",
        "Does the first row contain column names?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        header_default) == QMessageBox.StandardButton.Yes
    skip_rows, ok = QInputDialog.getInt(
        parent, "Delimited Text Settings", "Rows to skip before reading:",
        int((current or {}).get("skip_rows", 0)), 0, 100000, 1)
    if not ok:
        raise DialogCancelled
    return delimited_text_spec(
        delimiter=delimiter, has_header=has_header, skip_rows=skip_rows)


def _prompt_fixed_width_spec(parent, current: list | None = None) -> dict:
    message = ("Enter one column per line as: name,start,width\n"
               "Example:\nPolicy,1,10\nCompany,11,2\nAmount,13,9")
    initial = "\n".join(
        f"{c.get('name', '')},{c.get('start', '')},{c.get('width', '')}"
        for c in (current or [])
    )
    text, ok = QInputDialog.getMultiLineText(
        parent, "Fixed Width Layout", message, initial)
    if not ok:
        raise DialogCancelled
    try:
        columns = _parse_fixed_width_columns(text)
    except ValueError as exc:
        QMessageBox.warning(parent, "Invalid Fixed Width Layout", str(exc))
        raise DialogCancelled from exc
    skip_rows, ok = QInputDialog.getInt(
        parent, "Fixed Width Layout", "Rows to skip before reading:",
        0, 0, 100000, 1)
    if not ok:
        raise DialogCancelled
    return fixed_width_spec(columns, skip_rows=skip_rows)


def _parse_fixed_width_columns(text: str) -> list[dict]:
    columns = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = [part.strip() for part in stripped.split(",")]
        if len(parts) != 3:
            raise ValueError("Each fixed-width line must be: name,start,width")
        name, start, width = parts
        try:
            columns.append({"name": name, "start": int(start), "width": int(width)})
        except ValueError as exc:
            raise ValueError("Fixed-width start and width must be numbers.") from exc
    if not columns:
        raise ValueError("Enter at least one fixed-width column.")
    return columns
