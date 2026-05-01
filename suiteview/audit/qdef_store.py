"""
QDefinition persistence — save/load/list/delete named query definitions.

Storage: ~/.suiteview/qdefinitions/<forge_name>/<qdef_name>.json
Snapshots: ~/.suiteview/qdefinitions/<forge_name>/<qdef_name>.parquet

QDefs are scoped to a DataForge. Names must be unique within a forge,
but the same name can exist under different forges.
QDefs without a forge go into the '_commons' folder.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from suiteview.audit.qdefinition import QDefinition

logger = logging.getLogger(__name__)

_QDEFS_DIR = Path.home() / ".suiteview" / "qdefinitions"
COMMONS_NAME = "_commons"


def _ensure_dir(forge_name: str = "") -> Path:
    d = _QDEFS_DIR / _safe_filename(forge_name) if forge_name else _QDEFS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_filename(name: str) -> str:
    """Convert a name to a safe filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def _forge_dir(forge_name: str) -> Path:
    """Return the directory for a specific forge's QDefs."""
    return _QDEFS_DIR / _safe_filename(forge_name)


def list_forge_names() -> list[str]:
    """Return all forge names that have QDefs stored."""
    _QDEFS_DIR.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for d in _QDEFS_DIR.iterdir():
        if d.is_dir() and any(d.glob("*.json")):
            names.append(d.name)
    return sorted(names)


def list_qdefs(forge_name: str = "") -> list[QDefinition]:
    """Return QDefinitions for a specific forge, or all QDefs across all forges.

    If forge_name is empty, returns all QDefs from all forges.
    When a specific forge is given, also includes QDefs from _commons.
    """
    _QDEFS_DIR.mkdir(parents=True, exist_ok=True)
    qdefs: list[QDefinition] = []

    if forge_name:
        # Scan the requested forge folder + _commons
        dirs_to_scan = [_forge_dir(forge_name)]
        if forge_name != COMMONS_NAME:
            commons_dir = _forge_dir(COMMONS_NAME)
            if commons_dir.exists():
                dirs_to_scan.append(commons_dir)
        for d in dirs_to_scan:
            if not d.exists():
                continue
            fn = d.name
            for f in d.glob("*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        qd = QDefinition.from_dict(json.load(fh))
                        if not qd.forge_name:
                            qd.forge_name = fn
                        qdefs.append(qd)
                except Exception:
                    logger.exception("Failed to load QDefinition: %s", f)
    else:
        # All forges
        for d in _QDEFS_DIR.iterdir():
            if not d.is_dir():
                continue
            fn = d.name
            for f in d.glob("*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        qd = QDefinition.from_dict(json.load(fh))
                        if not qd.forge_name:
                            qd.forge_name = fn
                        qdefs.append(qd)
                except Exception:
                    logger.exception("Failed to load QDefinition: %s", f)

    qdefs.sort(key=lambda q: q.created_at, reverse=True)
    return qdefs


def load_qdef(name: str, forge_name: str = "") -> QDefinition | None:
    """Load a single QDefinition by name within a forge."""
    if not forge_name:
        # Search all forges for this name
        for d in _QDEFS_DIR.iterdir():
            if not d.is_dir():
                continue
            path = d / f"{_safe_filename(name)}.json"
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        qd = QDefinition.from_dict(json.load(f))
                        if not qd.forge_name:
                            qd.forge_name = d.name
                        return qd
                except Exception:
                    logger.exception("Failed to load QDefinition: %s", name)
        return None

    path = _forge_dir(forge_name) / f"{_safe_filename(name)}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            qd = QDefinition.from_dict(json.load(f))
            if not qd.forge_name:
                qd.forge_name = forge_name
            return qd
    except Exception:
        logger.exception("Failed to load QDefinition: %s", name)
        return None


def save_qdef(qd: QDefinition) -> None:
    """Save a QDefinition. Overwrites if same name exists in the same forge."""
    forge = qd.forge_name or COMMONS_NAME
    d = _ensure_dir(forge)
    path = d / f"{_safe_filename(qd.name)}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(qd.to_dict(), f, indent=2)


def delete_qdef(name: str, forge_name: str = "") -> None:
    """Delete a QDefinition file and its snapshot if present."""
    safe = _safe_filename(name)
    if forge_name:
        d = _forge_dir(forge_name)
        json_path = d / f"{safe}.json"
        parquet_path = d / f"{safe}.parquet"
        if json_path.exists():
            json_path.unlink()
        if parquet_path.exists():
            parquet_path.unlink()
    else:
        # Search all forges
        for d in _QDEFS_DIR.iterdir():
            if not d.is_dir():
                continue
            json_path = d / f"{safe}.json"
            parquet_path = d / f"{safe}.parquet"
            if json_path.exists():
                json_path.unlink()
            if parquet_path.exists():
                parquet_path.unlink()
                break


def qdef_exists(name: str, forge_name: str = "") -> bool:
    if forge_name:
        return (_forge_dir(forge_name) / f"{_safe_filename(name)}.json").exists()
    # Search all forges
    for d in _QDEFS_DIR.iterdir():
        if d.is_dir() and (d / f"{_safe_filename(name)}.json").exists():
            return True
    return False


def snapshot_path(name: str, forge_name: str = "") -> Path:
    """Return the path to the parquet snapshot for a QDefinition."""
    if forge_name:
        return _forge_dir(forge_name) / f"{_safe_filename(name)}.parquet"
    # Search all forges for existing snapshot
    for d in _QDEFS_DIR.iterdir():
        if d.is_dir():
            p = d / f"{_safe_filename(name)}.parquet"
            if p.exists():
                return p
    # Default to first forge found with the json, or _unassigned
    for d in _QDEFS_DIR.iterdir():
        if d.is_dir() and (d / f"{_safe_filename(name)}.json").exists():
            return d / f"{_safe_filename(name)}.parquet"
    return _QDEFS_DIR / COMMONS_NAME / f"{_safe_filename(name)}.parquet"


def has_snapshot(name: str, forge_name: str = "") -> bool:
    """Check if a parquet snapshot exists for a QDefinition."""
    return snapshot_path(name, forge_name).exists()


def save_snapshot(name: str, df, forge_name: str = "") -> None:
    """Save a DataFrame as a parquet snapshot."""
    import pandas as pd
    if forge_name:
        d = _ensure_dir(forge_name)
        path = d / f"{_safe_filename(name)}.parquet"
    else:
        path = snapshot_path(name, forge_name)
        path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def load_snapshot(name: str, forge_name: str = ""):
    """Load a parquet snapshot as a DataFrame. Returns None if not found."""
    import pandas as pd
    path = snapshot_path(name, forge_name)
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        logger.exception("Failed to load snapshot: %s", name)
        return None


def snapshot_date(name: str, forge_name: str = "") -> str | None:
    """Return the last modified date of the snapshot file, or None."""
    from datetime import datetime
    path = snapshot_path(name, forge_name)
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def copy_qdef(name: str, src_forge: str, dst_forge: str,
              new_name: str = "") -> bool:
    """Copy a QDefinition (and snapshot) from one forge to another.

    Returns True on success.
    """
    qd = load_qdef(name, forge_name=src_forge)
    if not qd:
        return False
    target_name = new_name or name
    qd.name = target_name
    qd.forge_name = dst_forge
    save_qdef(qd)

    # Copy snapshot if present
    src_snap = snapshot_path(name, forge_name=src_forge)
    if src_snap.exists():
        dst_snap = snapshot_path(target_name, forge_name=dst_forge)
        dst_snap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src_snap), str(dst_snap))
    return True


def move_qdef(name: str, src_forge: str, dst_forge: str,
              new_name: str = "") -> bool:
    """Move a QDefinition (and snapshot) from one forge to another.

    Returns True on success.
    """
    if not copy_qdef(name, src_forge, dst_forge, new_name=new_name):
        return False
    delete_qdef(name, forge_name=src_forge)
    return True
