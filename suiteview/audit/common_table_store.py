"""
Common table persistence — save/load/list/delete user-defined tables.

Storage: ~/.suiteview/data/query/common_tables/<name>.json
"""
from __future__ import annotations

from suiteview.core.profile_paths import profile_path

import json
import logging
from pathlib import Path

from suiteview.audit.common_table import CommonTable
from suiteview.core.json_store import ensure_dir, safe_filename as _safe_filename, write_json

logger = logging.getLogger(__name__)

_TABLES_DIR = profile_path('common_tables')


def _ensure_dir() -> Path:
    return ensure_dir(_TABLES_DIR)


def list_tables() -> list[CommonTable]:
    """Return all common tables sorted by name."""
    _ensure_dir()
    tables: list[CommonTable] = []
    for f in _TABLES_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                tables.append(CommonTable.from_dict(json.load(fh)))
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.exception("Failed to load common table: %s", f)
            raise RuntimeError(f"Failed to load common table: {f}") from exc
    tables.sort(key=lambda t: t.name.lower())
    return tables


def load_table(name: str) -> CommonTable | None:
    """Load a single common table by name."""
    path = _TABLES_DIR / f"{_safe_filename(name)}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return CommonTable.from_dict(json.load(f))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.exception("Failed to load common table: %s", name)
        raise RuntimeError(f"Failed to load common table: {name}") from exc


def save_table(ct: CommonTable) -> None:
    """Save a common table. Overwrites if same name exists."""
    _ensure_dir()
    path = _TABLES_DIR / f"{_safe_filename(ct.name)}.json"
    write_json(path, ct.to_dict(), ensure_ascii=True)


def delete_table(name: str) -> None:
    """Delete a common table file."""
    path = _TABLES_DIR / f"{_safe_filename(name)}.json"
    if path.exists():
        path.unlink()


def table_exists(name: str) -> bool:
    return (_TABLES_DIR / f"{_safe_filename(name)}.json").exists()
