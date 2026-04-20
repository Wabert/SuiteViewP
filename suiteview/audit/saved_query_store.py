"""
Saved query persistence — save/load/list/delete named query snapshots.

Storage: ~/.suiteview/saved_queries/<name>.json
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from suiteview.audit.saved_query import SavedQuery

logger = logging.getLogger(__name__)

_QUERIES_DIR = Path.home() / ".suiteview" / "saved_queries"


def _ensure_dir() -> Path:
    _QUERIES_DIR.mkdir(parents=True, exist_ok=True)
    return _QUERIES_DIR


def _safe_filename(name: str) -> str:
    """Convert a query name to a safe filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def list_queries() -> list[SavedQuery]:
    """Return all saved queries (sorted newest first)."""
    _ensure_dir()
    queries: list[SavedQuery] = []
    for f in _QUERIES_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                queries.append(SavedQuery.from_dict(json.load(fh)))
        except Exception:
            logger.exception("Failed to load saved query: %s", f)
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
    except Exception:
        logger.exception("Failed to load query: %s", name)
        return None


def save_query(sq: SavedQuery) -> None:
    """Save a query. Overwrites if same name exists."""
    _ensure_dir()
    path = _QUERIES_DIR / f"{_safe_filename(sq.name)}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sq.to_dict(), f, indent=2)


def delete_query(name: str) -> None:
    """Delete a saved query file."""
    path = _QUERIES_DIR / f"{_safe_filename(name)}.json"
    if path.exists():
        path.unlink()


def query_exists(name: str) -> bool:
    return (_QUERIES_DIR / f"{_safe_filename(name)}.json").exists()
