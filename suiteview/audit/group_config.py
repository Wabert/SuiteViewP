"""Group configuration persistence — UI settings for audit groups."""
from __future__ import annotations

import json
import logging
from suiteview.core.profile_paths import profile_path
from suiteview.core.json_store import ensure_dir, write_json

logger = logging.getLogger(__name__)

def _settings_file():
    return profile_path("audit_ui_settings.json")


def _ensure_dir():
    ensure_dir(_settings_file().parent)


def load_ui_settings() -> dict:
    """Load window-level UI settings (field picker sizes, etc.)."""
    _ensure_dir()
    path = _settings_file()
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
    write_json(_settings_file(), settings, ensure_ascii=True)
