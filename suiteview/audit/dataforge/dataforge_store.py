"""
DataForge persistence — save/load/list/delete named DataForge definitions.

Storage: ~/.suiteview/saved_dataforges/<name>.json
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .dataforge_model import DataForge

logger = logging.getLogger(__name__)

_FORGES_DIR = Path.home() / ".suiteview" / "saved_dataforges"


def _ensure_dir() -> Path:
    _FORGES_DIR.mkdir(parents=True, exist_ok=True)
    return _FORGES_DIR


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def list_forges() -> list[DataForge]:
    """Return all saved DataForges (sorted newest first)."""
    _ensure_dir()
    forges: list[DataForge] = []
    for f in _FORGES_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                forges.append(DataForge.from_dict(json.load(fh)))
        except Exception:
            logger.exception("Failed to load DataForge: %s", f)
    forges.sort(key=lambda d: d.created_at, reverse=True)
    return forges


def load_forge(name: str) -> DataForge | None:
    path = _FORGES_DIR / f"{_safe_filename(name)}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return DataForge.from_dict(json.load(f))
    except Exception:
        logger.exception("Failed to load DataForge: %s", name)
        return None


def save_forge(df: DataForge) -> None:
    _ensure_dir()
    path = _FORGES_DIR / f"{_safe_filename(df.name)}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(df.to_dict(), f, indent=2)


def delete_forge(name: str) -> None:
    path = _FORGES_DIR / f"{_safe_filename(name)}.json"
    if path.exists():
        path.unlink()


def forge_exists(name: str) -> bool:
    return (_FORGES_DIR / f"{_safe_filename(name)}.json").exists()
