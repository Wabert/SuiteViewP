"""
QueryObject persistence.

Storage defaults to ~/.suiteview/query_objects/<name>.json. Tests and tools can
override the directory with SUITEVIEW_QUERY_OBJECTS_DIR.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from suiteview.audit.query_object import QueryObject

logger = logging.getLogger(__name__)


def _objects_dir() -> Path:
    override = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".suiteview" / "query_objects"


def _ensure_dir() -> Path:
    directory = _objects_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def object_path(name: str) -> Path:
    return _objects_dir() / f"{_safe_filename(name)}.json"


def list_objects() -> list[QueryObject]:
    """Return all query objects sorted newest first."""
    _ensure_dir()
    objects: list[QueryObject] = []
    for path in _objects_dir().glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                objects.append(QueryObject.from_dict(json.load(handle)))
        except Exception:
            logger.exception("Failed to load query object: %s", path)
    objects.sort(key=lambda obj: obj.updated_at, reverse=True)
    return objects


def load_object(name: str) -> QueryObject | None:
    """Load one query object by name."""
    path = object_path(name)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return QueryObject.from_dict(json.load(handle))
    except Exception:
        logger.exception("Failed to load query object: %s", name)
        return None


def save_object(query_object: QueryObject) -> None:
    """Save or overwrite a query object."""
    _ensure_dir()
    path = object_path(query_object.name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(query_object.to_dict(), handle, indent=2)


def delete_object(name: str) -> None:
    """Delete a query object if present."""
    path = object_path(name)
    if path.exists():
        path.unlink()


def object_exists(name: str) -> bool:
    return object_path(name).exists()