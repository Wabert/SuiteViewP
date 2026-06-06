"""
DataForge persistence — save/load/list/delete named DataForge definitions, plus
per-Source parquet Snapshot I/O.

Storage:
  ~/.suiteview/saved_dataforges/<name>.json          — the Forge definition
  ~/.suiteview/saved_dataforges/<name>/<alias>.parquet — each Source's Snapshot
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from suiteview.core.json_store import write_json

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
    write_json(path, df.to_dict())


def delete_forge(name: str) -> None:
    safe = _safe_filename(name)
    path = _FORGES_DIR / f"{safe}.json"
    if path.exists():
        path.unlink()
    snap_dir = _FORGES_DIR / safe
    if snap_dir.is_dir():
        shutil.rmtree(snap_dir, ignore_errors=True)


def forge_exists(name: str) -> bool:
    return (_FORGES_DIR / f"{_safe_filename(name)}.json").exists()


# ── Per-Source Snapshot I/O ─────────────────────────────────────────────

def _forge_snapshot_dir(forge_name: str) -> Path:
    return _FORGES_DIR / _safe_filename(forge_name)


def source_snapshot_path(forge_name: str, alias: str) -> Path:
    """Path to a Source's parquet Snapshot (may not exist yet)."""
    return _forge_snapshot_dir(forge_name) / f"{_safe_filename(alias)}.parquet"


def has_source_snapshot(forge_name: str, alias: str) -> bool:
    return source_snapshot_path(forge_name, alias).exists()


def save_source_snapshot(forge_name: str, alias: str, dataframe) -> Path:
    """Write a Source's DataFrame to its parquet Snapshot. Returns the path."""
    snap_dir = _forge_snapshot_dir(forge_name)
    snap_dir.mkdir(parents=True, exist_ok=True)
    path = snap_dir / f"{_safe_filename(alias)}.parquet"
    dataframe.to_parquet(path, index=False)
    return path


def load_source_snapshot(forge_name: str, alias: str):
    """Load a Source's parquet Snapshot as a DataFrame, or None if absent."""
    import pandas as pd

    path = source_snapshot_path(forge_name, alias)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        logger.exception("Failed to load Snapshot for %s/%s", forge_name, alias)
        return None


def delete_source_snapshot(forge_name: str, alias: str) -> None:
    path = source_snapshot_path(forge_name, alias)
    if path.exists():
        path.unlink()


def snapshot_mtime(forge_name: str, alias: str) -> str | None:
    """Last-modified timestamp of a Source's Snapshot file, or None."""
    from datetime import datetime

    path = source_snapshot_path(forge_name, alias)
    if not path.exists():
        return None
    return datetime.fromtimestamp(
        path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
