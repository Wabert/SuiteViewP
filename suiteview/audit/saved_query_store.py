"""
Saved query persistence — save/load/list/delete named query snapshots.

Storage: ~/.suiteview/data/query/saved_queries/<name>.json
"""
from __future__ import annotations

from suiteview.core.profile_paths import profile_path

import json
import logging
from pathlib import Path

from suiteview.audit.saved_query import SavedQuery
from suiteview.core.json_store import ensure_dir, safe_filename as _safe_filename, write_json

logger = logging.getLogger(__name__)

_QUERIES_DIR = profile_path('saved_queries')


def _ensure_dir() -> Path:
    return ensure_dir(_QUERIES_DIR)


def list_queries() -> list[SavedQuery]:
    """Return all saved queries (sorted newest first)."""
    _ensure_dir()
    queries: list[SavedQuery] = []
    for f in _QUERIES_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                queries.append(SavedQuery.from_dict(json.load(fh)))
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.exception("Failed to load saved query: %s", f)
            raise RuntimeError(f"Failed to load saved query: {f}") from exc
    queries.sort(key=lambda q: q.created_at, reverse=True)
    return queries


def load_query(name: str) -> SavedQuery | None:
    """Load a single saved query by name."""
    path = _QUERIES_DIR / f"{_safe_filename(name)}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return SavedQuery.from_dict(json.load(f))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.exception("Failed to load query: %s", name)
        raise RuntimeError(f"Failed to load query: {name}") from exc


def save_query(sq: SavedQuery) -> None:
    """Save a query. Overwrites if same name exists."""
    _ensure_dir()
    path = _QUERIES_DIR / f"{_safe_filename(sq.name)}.json"
    write_json(path, sq.to_dict())
    try:
        from suiteview.audit.query_object import object_from_saved_query
        from suiteview.audit import query_object_store
        query_object_store.save_object(object_from_saved_query(sq))
    except Exception:
        logger.exception("Failed to publish query object for saved query: %s", sq.name)


def rename_query(old_name: str, new_name: str) -> None:
    """Move a saved visual design file from old_name to new_name in place.

    Cascade-free on purpose: the QueryObject is renamed separately (id-keyed),
    so this only relocates the name-keyed design snapshot. Using ``save_query`` +
    ``delete_query`` here would fire the name-keyed QueryObject publish/delete
    cascade and could resurrect or drop the wrong object — see ``rename_object``
    in query_object_store.
    """
    if old_name == new_name:
        return
    saved = load_query(old_name)
    if saved is None:
        return
    saved.name = new_name
    _ensure_dir()
    write_json(_QUERIES_DIR / f"{_safe_filename(new_name)}.json", saved.to_dict())
    delete_query_file(old_name)


def delete_query_file(name: str) -> None:
    """Delete only the saved-query design file (no QueryObject cascade)."""
    path = _QUERIES_DIR / f"{_safe_filename(name)}.json"
    if path.exists():
        path.unlink()


def delete_query(name: str) -> None:
    """Delete a saved query file and its published QueryObject (by name)."""
    delete_query_file(name)
    try:
        from suiteview.audit import query_object_store
        query_object_store.delete_object(name)
    except Exception:
        logger.exception("Failed to delete query object for saved query: %s", name)


def query_exists(name: str) -> bool:
    return (_QUERIES_DIR / f"{_safe_filename(name)}.json").exists()
