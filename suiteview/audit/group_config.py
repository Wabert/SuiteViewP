"""Group configuration persistence — UI settings for audit groups."""
from __future__ import annotations

import json
import logging
from suiteview.core.profile_paths import profile_path

logger = logging.getLogger(__name__)

_SETTINGS_FILE = profile_path("audit_ui_settings.json")


def _ensure_dir():
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_ui_settings() -> dict:
    """Load window-level UI settings (field picker sizes, etc.)."""
    _ensure_dir()
    path = _SETTINGS_FILE
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
    path = _SETTINGS_FILE
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
