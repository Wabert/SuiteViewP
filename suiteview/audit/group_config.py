"""
Group configuration persistence — save/load dynamic audit groups to JSON.

Each group config file stores:
  - Group name
  - ODBC DSN
  - Selected tables
  - Field display names (per-group)
  - Tab layout (tab names, field positions per tab)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_GROUPS_DIR = Path.home() / ".suiteview" / "audit_groups"


def _ensure_dir():
    _GROUPS_DIR.mkdir(parents=True, exist_ok=True)


def list_groups() -> list[str]:
    """Return sorted list of saved group names."""
    _ensure_dir()
    names = []
    for f in _GROUPS_DIR.glob("*.json"):
        names.append(f.stem)
    return sorted(names)


def load_group(name: str) -> dict | None:
    """Load a group config by name. Returns None if not found."""
    _ensure_dir()
    path = _GROUPS_DIR / f"{name}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load group config: %s", name)
        return None


def save_group(name: str, config: dict):
    """Save a group config. Overwrites if exists."""
    _ensure_dir()
    path = _GROUPS_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def delete_group(name: str):
    """Delete a group config file."""
    path = _GROUPS_DIR / f"{name}.json"
    if path.exists():
        path.unlink()


def group_exists(name: str) -> bool:
    return (_GROUPS_DIR / f"{name}.json").exists()


def load_ui_settings() -> dict:
    """Load window-level UI settings (field picker sizes, etc.)."""
    _ensure_dir()
    path = _GROUPS_DIR / "_ui_settings.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load UI settings")
        return {}


def save_ui_settings(settings: dict):
    """Save window-level UI settings."""
    _ensure_dir()
    path = _GROUPS_DIR / "_ui_settings.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
