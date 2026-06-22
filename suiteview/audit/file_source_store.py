"""
FileDataSource persistence — id-keyed, atomic.

Storage: ~/.suiteview/file_sources/<safe_name>__<id8>.json. Names need NOT be
unique (queries reference a File Source by ``FileDataSource.id``); the id8
suffix keeps filenames collision-free and readable. Tests/tools can override the
directory with SUITEVIEW_FILE_SOURCES_DIR.

Writes go through ``core.json_store.write_json`` (atomic temp-file + os.replace),
so a crash mid-write can never corrupt a saved File Source. Mirrors the shape of
``query_object_store`` but stays simpler: there is no pre-id legacy format to
migrate (File Sources are new).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from uuid import uuid4

from suiteview.audit.file_source import FileDataSource
from suiteview.core.json_store import read_json, write_json

logger = logging.getLogger(__name__)

_ID_SUFFIX_RE = re.compile(r"__([0-9a-f]{8})$")


def _sources_dir() -> Path:
    override = os.environ.get("SUITEVIEW_FILE_SOURCES_DIR")
    if override:
        return Path(override)
    return Path.home() / ".suiteview" / "file_sources"


def _ensure_dir() -> Path:
    directory = _sources_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def source_path(file_source: FileDataSource) -> Path:
    """The canonical on-disk path for a File Source (name + id8)."""
    return (_sources_dir()
            / f"{_safe_filename(file_source.name)}__{file_source.id[:8]}.json")


def _load_path(path: Path) -> FileDataSource | None:
    data = read_json(path, None)
    if not isinstance(data, dict):
        return None
    try:
        return FileDataSource.from_dict(data)
    except Exception:
        logger.exception("Failed to parse File Source: %s", path)
        return None


def list_file_sources() -> list[FileDataSource]:
    """Return all File Sources, newest-updated first."""
    _ensure_dir()
    sources: list[FileDataSource] = []
    for path in sorted(_sources_dir().glob("*.json")):
        fds = _load_path(path)
        if fds is not None:
            sources.append(fds)
    sources.sort(key=lambda fds: fds.updated_at, reverse=True)
    return sources


def load_file_source_by_id(source_id: str) -> FileDataSource | None:
    """Load one File Source by its permanent id."""
    if not source_id:
        return None
    _ensure_dir()
    for path in _sources_dir().glob(f"*__{source_id[:8]}.json"):
        fds = _load_path(path)
        if fds is not None and fds.id == source_id:
            return fds
    # Renamed/odd-filename fallback: full scan.
    for fds in list_file_sources():
        if fds.id == source_id:
            return fds
    return None


def load_file_source(name: str) -> FileDataSource | None:
    """Load one File Source by name (compat seam; newest-updated match wins)."""
    matches = [fds for fds in list_file_sources() if fds.name == name]
    return matches[0] if matches else None


def save_file_source(file_source: FileDataSource) -> None:
    """Save or overwrite a File Source (keyed by id; filename tracks name)."""
    _ensure_dir()
    if not file_source.id:
        file_source.id = uuid4().hex
    target = source_path(file_source)
    write_json(target, file_source.to_dict())

    # A rename moves the file: clear any other file carrying this id.
    for path in _sources_dir().glob(f"*__{file_source.id[:8]}.json"):
        if path == target:
            continue
        data = read_json(path, {})
        if isinstance(data, dict) and data.get("id") == file_source.id:
            path.unlink(missing_ok=True)


def delete_file_source_by_id(source_id: str) -> None:
    """Delete a File Source by its permanent id."""
    fds = load_file_source_by_id(source_id)
    if fds is None:
        return
    path = source_path(fds)
    path.unlink(missing_ok=True)


def delete_file_source(name: str) -> None:
    """Delete a File Source by name (newest match, symmetric with load_file_source)."""
    fds = load_file_source(name)
    if fds is None:
        return
    source_path(fds).unlink(missing_ok=True)


def file_source_exists(name: str) -> bool:
    """Whether ANY File Source has this name (names may be duplicated)."""
    return any(fds.name == name for fds in list_file_sources())
