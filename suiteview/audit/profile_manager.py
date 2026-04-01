"""
Audit profile manager — save/load/delete named query profiles.

Profiles are stored as JSON files in ~/.suiteview/audit_profiles/.
Each profile captures the complete form state across all tabs.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

_PROFILE_DIR = Path.home() / ".suiteview" / "audit_profiles"

# Characters allowed in profile filenames (replace others with _)
_SAFE_RE = re.compile(r'[^\w\s\-()]')


def _safe_filename(name: str) -> str:
    """Convert profile name to a safe filename."""
    return _SAFE_RE.sub('_', name).strip()


def profile_dir() -> Path:
    """Return the profile directory, creating it if needed."""
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return _PROFILE_DIR


def list_profiles() -> list[str]:
    """Return sorted list of saved profile names."""
    d = profile_dir()
    names = []
    for f in d.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            names.append(data.get("name", f.stem))
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(names, key=str.casefold)


def save_profile(name: str, state: dict) -> Path:
    """Save a profile to disk. Returns the path written."""
    d = profile_dir()
    state["name"] = name
    state["saved_at"] = datetime.now().isoformat(timespec="seconds")
    path = d / f"{_safe_filename(name)}.json"
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


def load_profile(name: str) -> dict | None:
    """Load a profile by name. Returns None if not found."""
    d = profile_dir()
    path = d / f"{_safe_filename(name)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def delete_profile(name: str) -> bool:
    """Delete a profile by name. Returns True if deleted."""
    d = profile_dir()
    path = d / f"{_safe_filename(name)}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def profile_exists(name: str) -> bool:
    """Check if a profile with the given name exists."""
    d = profile_dir()
    return (d / f"{_safe_filename(name)}.json").exists()


# ── Generic widget state helpers ──────────────────────────────────────

def get_lineedit_text(widget) -> str:
    return widget.text()


def get_checkbox_checked(widget) -> bool:
    return widget.isChecked()


def get_combo_text(widget) -> str:
    return widget.currentText()


def get_listbox_selected(widget) -> list[str]:
    """Return texts of selected items in a QListWidget."""
    return [
        widget.item(i).text()
        for i in range(widget.count())
        if widget.item(i).isSelected()
    ]


def set_lineedit_text(widget, value: str):
    widget.setText(value or "")


def set_checkbox_checked(widget, value: bool):
    widget.setChecked(bool(value))


def set_combo_text(widget, value: str):
    idx = widget.findText(value or "")
    if idx >= 0:
        widget.setCurrentIndex(idx)
    else:
        widget.setCurrentIndex(0)


def set_listbox_selected(widget, values: list[str]):
    """Select items in a QListWidget whose text matches values."""
    widget.clearSelection()
    value_set = set(values) if values else set()
    for i in range(widget.count()):
        item = widget.item(i)
        item.setSelected(item.text() in value_set)


def get_groupbox_checked(widget) -> bool:
    """Get checked state of a checkable QGroupBox."""
    return widget.isChecked()


def set_groupbox_checked(widget, value: bool):
    """Set checked state of a checkable QGroupBox."""
    widget.setChecked(bool(value))
