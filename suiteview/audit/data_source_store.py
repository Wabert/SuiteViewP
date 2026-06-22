"""
RegisteredDataSource persistence — id-keyed, atomic.

Storage: ~/.suiteview/data_sources/<safe_name>__<id8>.json. Mirrors
``file_source_store`` exactly (same id8-suffixed filenames, atomic writes via
``core.json_store``); the two stores stay separate because a File Source and a
registered ODBC/Access source are different shapes. Tests/tools can override the
directory with SUITEVIEW_DATA_SOURCES_DIR.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from uuid import uuid4

from suiteview.audit.data_source import RegisteredDataSource
from suiteview.core.json_store import read_json, write_json

logger = logging.getLogger(__name__)


def _sources_dir() -> Path:
    override = os.environ.get("SUITEVIEW_DATA_SOURCES_DIR")
    if override:
        return Path(override)
    return Path.home() / ".suiteview" / "data_sources"


def _ensure_dir() -> Path:
    directory = _sources_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def source_path(source: RegisteredDataSource) -> Path:
    """The canonical on-disk path for a registered source (name + id8)."""
    return _sources_dir() / f"{_safe_filename(source.name)}__{source.id[:8]}.json"


def _load_path(path: Path) -> RegisteredDataSource | None:
    data = read_json(path, None)
    if not isinstance(data, dict):
        return None
    try:
        return RegisteredDataSource.from_dict(data)
    except Exception:
        logger.exception("Failed to parse registered data source: %s", path)
        return None


def list_data_sources() -> list[RegisteredDataSource]:
    """Return all registered data sources, newest-updated first."""
    _ensure_dir()
    sources: list[RegisteredDataSource] = []
    for path in sorted(_sources_dir().glob("*.json")):
        ds = _load_path(path)
        if ds is not None:
            sources.append(ds)
    sources.sort(key=lambda ds: ds.updated_at, reverse=True)
    return sources


def load_data_source_by_id(source_id: str) -> RegisteredDataSource | None:
    """Load one registered source by its permanent id."""
    if not source_id:
        return None
    _ensure_dir()
    for path in _sources_dir().glob(f"*__{source_id[:8]}.json"):
        ds = _load_path(path)
        if ds is not None and ds.id == source_id:
            return ds
    for ds in list_data_sources():
        if ds.id == source_id:
            return ds
    return None


def save_data_source(source: RegisteredDataSource) -> None:
    """Save or overwrite a registered source (keyed by id; filename tracks name)."""
    _ensure_dir()
    if not source.id:
        source.id = uuid4().hex
    target = source_path(source)
    write_json(target, source.to_dict())

    # A rename moves the file: clear any other file carrying this id.
    for path in _sources_dir().glob(f"*__{source.id[:8]}.json"):
        if path == target:
            continue
        data = read_json(path, {})
        if isinstance(data, dict) and data.get("id") == source.id:
            path.unlink(missing_ok=True)


def delete_data_source_by_id(source_id: str) -> None:
    """Delete a registered source by its permanent id."""
    ds = load_data_source_by_id(source_id)
    if ds is None:
        return
    source_path(ds).unlink(missing_ok=True)


def dsn_is_registered(dsn: str) -> bool:
    """Whether an ODBC DSN already has a registered source."""
    key = (dsn or "").strip().lower()
    if not key:
        return False
    return any(ds.kind == "odbc" and ds.dsn.strip().lower() == key
               for ds in list_data_sources())
