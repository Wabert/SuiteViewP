"""
Common table persistence — save/load/list/delete user-defined tables.

Storage: ~/.suiteview/common_tables/<name>.json
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from suiteview.audit.common_table import CommonTable

logger = logging.getLogger(__name__)

_TABLES_DIR = Path.home() / ".suiteview" / "common_tables"


def _ensure_dir() -> Path:
    _TABLES_DIR.mkdir(parents=True, exist_ok=True)
    return _TABLES_DIR


def _safe_filename(name: str) -> str:
    """Convert a table name to a safe filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def list_tables() -> list[CommonTable]:
    """Return all common tables sorted by name."""
    _ensure_dir()
    tables: list[CommonTable] = []
    for f in _TABLES_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                tables.append(CommonTable.from_dict(json.load(fh)))
        except Exception:
            logger.exception("Failed to load common table: %s", f)
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
    except Exception:
        logger.exception("Failed to load common table: %s", name)
        return None


def save_table(ct: CommonTable) -> None:
    """Save a common table. Overwrites if same name exists."""
    _ensure_dir()
    path = _TABLES_DIR / f"{_safe_filename(ct.name)}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ct.to_dict(), f, indent=2)


def delete_table(name: str) -> None:
    """Delete a common table file."""
    path = _TABLES_DIR / f"{_safe_filename(name)}.json"
    if path.exists():
        path.unlink()


def table_exists(name: str) -> bool:
    return (_TABLES_DIR / f"{_safe_filename(name)}.json").exists()
