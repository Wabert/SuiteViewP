"""Explicit, restartable profile migration and opt-in removal of retired data."""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sys

from suiteview.core.json_store import write_json
from suiteview.core.profile_paths import (
    PROFILE_LAYOUT_VERSION, PROFILE_PATHS, profile_root,
)

logger = logging.getLogger(__name__)


class ProfileMaintenanceError(RuntimeError):
    """Maintenance cannot safely proceed without user attention."""


_OBSOLETE_DIRECTORIES = (
    "agent_chat", "task_attachments", "workbench", "datasets",
    "sample", "final", "audit_profiles", "iul_report_preview", "data/agent_chat",
)
_OBSOLETE_FILES = (
    "tasktracker.json", "clipboard_history.json", "inbox_width.json",
    "launcher_settings.json", "links.json", "shortcuts.json", "todo_list.json",
    "unique_value_registry.db", "unique_value_registry.db-wal",
    "unique_value_registry.db-shm", "unique_value_registry.db-journal",
    "advprod_preview.png", "diag_checkbox.png", "frameless_min_check.png",
    "frameless_resize_check.png", "illustration_UX012760_control.png",
    "policy_record_layout.png", "policy_record_preview.png",
    "policy_record_tooltip.png", "policy_record_top.png",
    "polview_header_preview.png",
    "audit_groups/CKMO - FH_FIXED.json", "audit_groups/FH_FIXED.json",
    "audit_groups/SAP_LDTI.json", "audit_groups/TAI_Cession.json",
)
_MUTEX_NAMES = (
    "SuiteView_SingleInstance_Mutex", "SuiteView_Local_SingleInstance_Mutex",
    "SuiteView_FileNav_SingleInstance_Mutex",
)


def _is_default_profile(root: Path) -> bool:
    return root.resolve() == (Path.home() / ".suiteview").resolve()


def _source_name(name: str) -> str:
    return "audit_groups/_ui_settings.json" if name == "audit_ui_settings.json" else name


def _path(root: Path, relative: str) -> Path:
    return root.joinpath(*relative.split("/"))


def _check_tree(path: Path) -> None:
    if path.is_symlink() or path.is_junction():
        raise ProfileMaintenanceError(f"Linked profile paths require manual review: {path}")
    if path.is_dir():
        for child in path.iterdir():
            _check_tree(child)


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@contextmanager
def _app_guard(root: Path):
    """Reserve launcher identities during maintenance of the real user profile."""
    handles = []
    if sys.platform != "win32" or not _is_default_profile(root):
        yield
        return
    from suiteview.core.single_instance import owned_mutex_names

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
    kernel32.CreateMutexW.restype = wt.HANDLE
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    kernel32.CloseHandle.restype = wt.BOOL
    try:
        for name in _MUTEX_NAMES:
            if name in owned_mutex_names():
                continue
            handle = kernel32.CreateMutexW(None, False, name)
            error = ctypes.get_last_error()
            if not handle:
                raise ctypes.WinError(error)
            handles.append(handle)
            if error == 183:
                raise ProfileMaintenanceError(
                    "Save your work and exit SuiteView (including local-data and "
                    "standalone FileNav instances) before reorganizing its profile."
                )
        yield
    finally:
        for handle in handles:
            kernel32.CloseHandle(handle)


@contextmanager
def _profile_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".maintenance.lock").open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ProfileMaintenanceError("Another profile maintenance operation is running.") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _moves(root: Path) -> list[tuple[Path, Path]]:
    pairs = [
        (_path(root, _source_name(name)), _path(root, destination))
        for name, destination in PROFILE_PATHS.items()
        if _source_name(name) != destination
    ]
    pairs.append((root / "quick_notes.txt", root / "data" / "notes" / "scratchpad.txt"))
    return pairs


def _legacy_policy_support_tasks_path() -> Path:
    appdata = Path(os.environ.get("APPDATA", str(Path.home())))
    return appdata / "SuiteView" / "policy_support_tasks.json"


def _external_moves(root: Path) -> list[tuple[Path, Path]]:
    if not _is_default_profile(root):
        return []
    source = _legacy_policy_support_tasks_path()
    target = _path(root, PROFILE_PATHS["policy_support_tasks.json"])
    if source.exists() and not target.exists():
        try:
            if source.resolve() == target.resolve():
                return []
        except OSError:
            pass
        return [(source, target)]
    return []


def plan_profile(root: Path | None = None, *, cleanup: bool = False) -> dict:
    """Return filenames/counts only; never read or report credential values."""
    root = root or profile_root()
    _check_tree(root)
    obsolete = [
        _path(root, name)
        for name in (*_OBSOLETE_DIRECTORIES, *_OBSOLETE_FILES)
        if _path(root, name).exists()
    ] if cleanup else []
    excluded = set(obsolete)
    moves = [
        (source, target) for source, target in _moves(root)
        if source.exists() and source not in excluded
    ]
    external_moves = _external_moves(root)
    targets = set()
    for source, target in moves:
        if target.exists() or target in targets:
            raise ProfileMaintenanceError(
                f"Both old and new profile data exist for {source.name}; "
                f"reconcile them before continuing: {source} -> {target}"
            )
        targets.add(target)
    manifest = root / "layout.json"
    if manifest.exists():
        version = json.loads(manifest.read_text(encoding="utf-8"))["version"]
        if version != PROFILE_LAYOUT_VERSION:
            raise ProfileMaintenanceError(f"Unsupported profile layout version: {version}")
    return {
        "root": str(root),
        "moves": [{"from": str(s.relative_to(root)), "to": str(t.relative_to(root))}
                  for s, t in moves],
        "external_moves": [{"from": str(s), "to": str(t.relative_to(root))}
                           for s, t in external_moves],
        "remove": [str(p.relative_to(root)) for p in obsolete],
        "layout_version": PROFILE_LAYOUT_VERSION,
    }


def _rewrite_paths(value, pairs: list[tuple[Path, Path]]):
    if isinstance(value, dict):
        return {key: _rewrite_paths(item, pairs) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite_paths(item, pairs) for item in value]
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        for source, target in pairs:
            old = str(source).replace("\\", "/")
            if normalized.casefold() == old.casefold():
                return str(target)
            if normalized.casefold().startswith(old.casefold() + "/"):
                return str(target.joinpath(*normalized[len(old) + 1:].split("/")))
    return value


def _json_updates(root: Path, moves: list[tuple[Path, Path]]) -> list[tuple[Path, dict | list]]:
    updates = []
    paths = []
    for source, target in moves:
        files = source.rglob("*.json") if source.is_dir() else [source]
        for path in files:
            if path.suffix == ".json":
                destination = target / path.relative_to(source) if source.is_dir() else target
                paths.append((path, destination))
    for area in ("data", "settings"):
        if (root / area).exists():
            paths.extend((path, path) for path in (root / area).rglob("*.json"))
    for path, target in paths:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        updated = _rewrite_paths(value, _moves(root))
        if updated != value:
            updates.append((target, updated))
    return updates


def _shortcut_updates(root: Path) -> list:
    if sys.platform != "win32" or not _is_default_profile(root):
        return []
    from win32com.client import dynamic

    shell = dynamic.Dispatch("WScript.Shell")
    desktop = Path(shell.SpecialFolders("Desktop"))
    updates = []
    for path in desktop.glob("SuiteView*.lnk"):
        shortcut = shell.CreateShortcut(str(path))
        icon = shortcut.IconLocation
        location, separator, index = icon.rpartition(",")
        if not separator:
            location, index = icon, ""
        for name in ("suiteview.ico", "suiteview_local.ico"):
            if location.strip('"').casefold() == str(root / name).casefold():
                target = _path(root, PROFILE_PATHS[name])
                if (root / name).exists() or target.exists():
                    updates.append((shortcut, str(target) + (f",{index}" if separator else "")))
    return updates


def maintain_profile(root: Path | None = None, *, cleanup: bool = False) -> dict:
    """Migrate known data without overwrites; cleanup is always explicit opt-in."""
    root = root or profile_root()
    with _app_guard(root), _profile_lock(root):
        plan = plan_profile(root, cleanup=cleanup)
        moves = [(_path(root, item["from"]), _path(root, item["to"])) for item in plan["moves"]]
        external_moves = [
            (Path(item["from"]), _path(root, item["to"])) for item in plan["external_moves"]
        ]
        updates = _json_updates(root, moves)
        shortcuts = _shortcut_updates(root)
        verified = 0
        for source, target in moves:
            hashes = (
                {file.relative_to(source): _hash(file) for file in source.rglob("*") if file.is_file()}
                if source.is_dir() else {None: _hash(source)}
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ProfileMaintenanceError(f"Destination appeared during migration: {target}")
            source.rename(target)
            for relative, digest in hashes.items():
                moved = target if relative is None else target / relative
                if _hash(moved) != digest:
                    raise ProfileMaintenanceError(f"Content verification failed after moving {moved}")
                verified += 1
        external_verified = 0
        for source, target in external_moves:
            _check_tree(source)
            digest = _hash(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                logger.info(
                    "Skipped legacy policy support task migration because profile file exists: %s",
                    target,
                )
                continue
            shutil.move(str(source), str(target))
            if _hash(target) != digest:
                raise ProfileMaintenanceError(f"Content verification failed after moving {target}")
            external_verified += 1
            logger.info("Moved legacy policy support tasks from %s to %s", source, target)
        for target, value in updates:
            write_json(target, value)
            if json.loads(target.read_text(encoding="utf-8")) != value:
                raise ProfileMaintenanceError(f"Path-reference verification failed: {target}")
        for shortcut, icon in shortcuts:
            shortcut.IconLocation = icon
            shortcut.Save()
        removed = 0
        for relative in plan["remove"]:
            path = _path(root, relative)
            _check_tree(path)
            if path.is_dir():
                removed += sum(1 for item in path.rglob("*") if item.is_file())
                shutil.rmtree(path)
            else:
                path.unlink()
                removed += 1
        old_groups = root / "audit_groups"
        if old_groups.is_dir() and not any(old_groups.iterdir()):
            old_groups.rmdir()
        for area in ("settings", "data", "auth", "logs", "backups", "diagnostics", "assets", "screenshots"):
            (root / area).mkdir(exist_ok=True)
        write_json(root / "layout.json", {"version": PROFILE_LAYOUT_VERSION})
        result = {
            **plan, "verified_files": verified, "rewritten_json_files": len(updates),
            "external_verified_files": external_verified,
            "removed_files": removed, "updated_shortcuts": len(shortcuts),
        }
        write_json(root / "logs" / "profile-maintenance.json", result)
        return result


def initialize_profile() -> None:
    """Called by launchers before importing modules with persisted state."""
    root = profile_root()
    plan = plan_profile(root)
    if plan["moves"] or plan["external_moves"] or not (root / "layout.json").exists():
        maintain_profile(root)
