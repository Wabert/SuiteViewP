"""Canonical local profile layout. Resolving a path never creates or moves data."""

from __future__ import annotations

import os
from pathlib import Path


PROFILE_LAYOUT_VERSION = 1
PROFILE_PATHS = {
    "suiteview.db": "data/suiteview.db",
    "abr_quote.db": "data/abr_quote.db",
    ".key": "auth/.key",
    "sp_token_cache.bin": "auth/sp_token_cache.bin",
    "bookmarks.json": "data/bookmarks.json",
    "scratchpad.txt": "data/notes/scratchpad.txt",
    "polview_notes.json": "data/notes/polview_notes.json",
    "policy_support_tasks.json": "settings/policy_support_tasks.json",
    "query_organizer.json": "data/query/query_organizer.json",
    "agent_chat": "data/agent_chat",
    "illustration_cases": "data/illustration/cases",
    "illustration_imported_cases": "data/illustration/imported_cases",
    "audit_ui_settings.json": "settings/audit_ui_settings.json",
    "rate_manager_backups": "backups/rate_manager",
    "suiteview.ico": "assets/suiteview.ico",
    "suiteview_local.ico": "assets/suiteview_local.ico",
    "checkmark.png": "assets/checkmark.png",
    "logs": "logs",
    "diagnostics": "diagnostics",
    "screenshots": "screenshots",
}
for _name in (
    "common_tables", "file_sources", "data_sources", "saved_queries",
    "query_objects", "qdefinitions", "saved_dataforges",
):
    PROFILE_PATHS[_name] = f"data/query/{_name}"
for _name in (
    "hidden_onedrive.json", "pinned_folders.json", "sharepoint_libraries.json",
    "column_widths.json", "file_explorer_panel_widths.json",
    "illustration_settings.json", "registry_window_geometry.json",
    "mainframe_nav_columns.json", "mainframe_nav_splitter.json",
    "terminal_settings.json", "polview_recent.json", "polview_table_columns.json",
    "polview_other_data.json",
):
    PROFILE_PATHS[_name] = f"settings/{_name}"
for _name in (
    "crash.log", "filenav_crash.log", "timing.log",
    "suiteview_crash.log", "suiteview_local_crash.log",
):
    PROFILE_PATHS[_name] = f"logs/{_name}"
for _suffix in ("-wal", "-shm", "-journal"):
    PROFILE_PATHS[f"suiteview.db{_suffix}"] = f"data/suiteview.db{_suffix}"
    PROFILE_PATHS[f"abr_quote.db{_suffix}"] = f"data/abr_quote.db{_suffix}"


def profile_root() -> Path:
    """Allow explicit isolated profiles without changing the default home."""
    override = os.environ.get("SUITEVIEW_PROFILE_DIR")
    if override:
        root = Path(override).expanduser()
        if not root.is_absolute():
            raise ValueError("SUITEVIEW_PROFILE_DIR must be an absolute directory.")
        return root
    return Path.home() / ".suiteview"


def profile_path(name: str) -> Path:
    """Resolve a registered location; unknown names are programming errors."""
    try:
        relative = PROFILE_PATHS[name]
    except KeyError:
        raise ValueError(f"Unregistered SuiteView profile location: {name!r}") from None
    root = profile_root()
    old_name = "audit_groups/_ui_settings.json" if name == "audit_ui_settings.json" else name
    old = root.joinpath(*old_name.split("/"))
    if old_name != relative and old.exists():
        raise RuntimeError(
            f"SuiteView profile migration is required for {old}. "
            "Save your work, exit all SuiteView windows, then restart SuiteView "
            "or run tools\\app\\maintain_profile.py --apply."
        )
    return root.joinpath(*relative.split("/"))


def diagnostics_dir() -> Path:
    """Create the destination for developer screenshots and generated previews."""
    directory = profile_path("diagnostics")
    directory.mkdir(parents=True, exist_ok=True)
    return directory
