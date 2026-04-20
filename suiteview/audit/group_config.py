"""Group configuration persistence — UI settings for audit groups."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_GROUPS_DIR = Path.home() / ".suiteview" / "audit_groups"


def _ensure_dir():
    _GROUPS_DIR.mkdir(parents=True, exist_ok=True)


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
