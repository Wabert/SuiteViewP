"""
QueryObject persistence.

Storage defaults to ~/.suiteview/query_objects/<name>.json. Tests and tools can
override the directory with SUITEVIEW_QUERY_OBJECTS_DIR.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from suiteview.audit.query_object import OBJECT_KIND_VISUAL, QueryObject

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


def copy_object(source_name: str, new_name: str) -> QueryObject:
    """Copy a query object to a new name and return the saved copy."""
    source = load_object(source_name)
    if source is None:
        raise ValueError(f"Query object not found: {source_name}")
    clean_name = new_name.strip()
    if not clean_name:
        raise ValueError("New query object name cannot be blank.")
    if object_exists(clean_name):
        raise ValueError(f"A Query Object named \"{clean_name}\" already exists.")

    copied = QueryObject.from_dict(source.to_dict())
    copied.name = clean_name
    copied.created_at = datetime.now()
    copied.updated_at = copied.created_at
    for source_ref in copied.sources:
        if source_ref.name == source_name:
            source_ref.name = clean_name
    for field in copied.fields:
        if field.source == source_name:
            field.source = clean_name
    _copy_saved_visual_design(source_name, clean_name, copied.created_at, source.kind)
    save_object(copied)
    return copied


def _copy_saved_visual_design(source_name: str, new_name: str, created_at: datetime, kind: str) -> None:
    if kind != OBJECT_KIND_VISUAL:
        return
    try:
        from suiteview.audit import saved_query_store

        saved = saved_query_store.load_query(source_name)
        if saved is None:
            logger.warning("No saved visual design found while copying query object: %s", source_name)
            return
        if saved_query_store.query_exists(new_name):
            raise ValueError(f"A saved visual design named \"{new_name}\" already exists.")
        copied_saved = copy.deepcopy(saved)
        copied_saved.name = new_name
        copied_saved.created_at = created_at
        saved_query_store.save_query(copied_saved)
    except ValueError:
        raise
    except Exception:
        logger.exception("Failed to copy saved visual design for query object: %s", source_name)
        raise


def restore_saved_visual_design(query_object: QueryObject):
    """Restore a missing SavedQuery design from a visual QueryObject snapshot."""
    if query_object.kind != OBJECT_KIND_VISUAL or not query_object.config:
        return None
    try:
        from suiteview.audit import saved_query_store
        from suiteview.audit.saved_query import SavedQuery

        existing = saved_query_store.load_query(query_object.name)
        if existing is not None:
            return existing
        restored = SavedQuery(
            name=query_object.name,
            source_group=query_object.source_design,
            dsn=query_object.dsn,
            tables=[source.name for source in query_object.sources],
            config=query_object.config,
            sql=query_object.sql,
            result_columns=query_object.result_columns,
            column_types={field.name: field.data_type for field in query_object.fields if field.data_type},
            created_at=query_object.created_at,
        )
        saved_query_store.save_query(restored)
        save_object(query_object)
        return restored
    except Exception:
        logger.exception("Failed to restore saved visual design for query object: %s", query_object.name)
        raise


def delete_object(name: str) -> None:
    """Delete a query object if present."""
    path = object_path(name)
    if path.exists():
        path.unlink()


def object_exists(name: str) -> bool:
    return object_path(name).exists()