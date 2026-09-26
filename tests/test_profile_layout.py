"""Profile migrations use synthetic data and never touch the real user's profile."""

import json
import ast
from contextlib import closing
from pathlib import Path
import sqlite3
from unittest.mock import Mock
from types import SimpleNamespace

from cryptography.fernet import Fernet
import pytest

from suiteview.core import profile_maintenance as maintenance
from suiteview.core.profile_paths import PROFILE_PATHS, profile_path, profile_root


@pytest.fixture
def profile(tmp_path, monkeypatch):
    root = tmp_path / "profile"
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(root))
    root.mkdir()
    return root


def put(root, name, value=b"preserve exactly"):
    path = root.joinpath(*name.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return path


def test_paths_are_registered_and_do_not_create_directories(profile):
    assert profile_root() == profile
    for name in PROFILE_PATHS:
        assert profile_path(name).is_relative_to(profile)
    assert not list(profile.iterdir())
    with pytest.raises(ValueError, match="Unregistered"):
        profile_path("../unsafe")


def test_relative_override_is_rejected(monkeypatch):
    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", "relative")
    with pytest.raises(ValueError, match="absolute"):
        profile_root()


def test_old_data_never_silently_becomes_a_new_empty_profile(profile):
    put(profile, "suiteview.db")
    with pytest.raises(RuntimeError, match="migration is required"):
        profile_path("suiteview.db")


def test_migration_is_exact_and_repeatable(profile):
    payloads = {
        "suiteview.db": b"database fixture",
        "suiteview.db-wal": b"wal fixture",
        ".key": Fernet.generate_key(),
        "sp_token_cache.bin": b"protected token fixture",
        "bookmarks.json": b'{"bars": {}}',
        "audit_groups/_ui_settings.json": b'{"picker_width": 250}',
        "file_sources/test.json": b'{"id": "test"}',
        "illustration_cases/test.json": b'{"id": "case"}',
        "suiteview.ico": b"icon",
        "rate_manager_backups/load/receipt.json": b'{"loaded": true}',
    }
    for name, contents in payloads.items():
        put(profile, name, contents)
    plan = maintenance.plan_profile(profile)
    assert len(plan["moves"]) == len(payloads)
    assert not (profile / "layout.json").exists()
    result = maintenance.maintain_profile(profile)
    assert result["verified_files"] == len(payloads)
    for old, contents in payloads.items():
        if old.startswith("audit_groups"):
            target = profile_path("audit_ui_settings.json")
        elif old.startswith("file_sources"):
            target = profile_path("file_sources") / "test.json"
        elif old.startswith("illustration_cases"):
            target = profile_path("illustration_cases") / "test.json"
        elif old.startswith("rate_manager_backups"):
            target = profile_path("rate_manager_backups") / "load" / "receipt.json"
        else:
            target = profile_path(old)
        assert target.read_bytes() == contents
        assert not (profile / old).exists()
    again = maintenance.maintain_profile(profile)
    assert again["moves"] == []
    assert again["verified_files"] == 0


def test_conflict_blocks_every_move_and_cleanup(profile):
    put(profile, ".key")
    put(profile, "bookmarks.json", b"{}")
    put(profile, "data/bookmarks.json", b'{"different": true}')
    put(profile, "tasktracker.json", b"{}")
    with pytest.raises(maintenance.ProfileMaintenanceError, match="Both old and new"):
        maintenance.maintain_profile(profile, cleanup=True)
    assert (profile / ".key").exists()
    assert (profile / "tasktracker.json").exists()
    assert not (profile / "auth").exists()


def test_invalid_json_blocks_before_moves(profile):
    put(profile, ".key")
    put(profile, "file_sources/broken.json", b"{invalid")
    with pytest.raises(json.JSONDecodeError):
        maintenance.maintain_profile(profile)
    assert (profile / ".key").exists()
    assert not (profile / "auth").exists()


def test_cleanup_is_explicit_and_preserves_live_audit_settings(profile):
    put(profile, "audit_groups/_ui_settings.json", b'{"size": 123}')
    put(profile, "audit_groups/FH_FIXED.json", b"{}")
    put(profile, "audit_groups/unknown.json", b"{}")
    put(profile, "workbench/old.pkl")
    put(profile, "sample/preview.png")
    put(profile, "agent_chat/sessions.json", b'{"conversations": []}')
    put(profile, "tasktracker.json", b"{}")
    put(profile, "screenshots/keep.png")
    put(profile, "file_sources/keep.json", b"{}")
    put(profile, "unrecognized.txt")
    maintenance.maintain_profile(profile)
    assert (profile / "workbench").exists()
    assert (profile / "tasktracker.json").exists()
    assert profile_path("agent_chat").exists()
    maintenance.maintain_profile(profile, cleanup=True)
    assert not (profile / "workbench").exists()
    assert not (profile / "sample").exists()
    assert not (profile / "tasktracker.json").exists()
    assert not profile_path("agent_chat").exists()
    assert profile_path("audit_ui_settings.json").exists()
    assert (profile / "audit_groups/unknown.json").exists()
    assert (profile / "screenshots/keep.png").exists()
    assert (profile / "unrecognized.txt").exists()
    assert (profile_path("file_sources") / "keep.json").exists()


def test_cleanup_directly_does_not_migrate_discarded_agent_chat(profile):
    put(profile, "agent_chat/sessions.json", b'{"conversations": []}')
    maintenance.maintain_profile(profile, cleanup=True)
    assert not (profile / "agent_chat").exists()
    assert not profile_path("agent_chat").exists()


def test_absolute_snapshot_references_follow_moves(profile):
    old_snapshot = profile / "qdefinitions" / "forge" / "result.parquet"
    put(profile, "qdefinitions/forge/result.parquet")
    value = {
        "snapshot": str(old_snapshot),
        "slash_path": old_snapshot.as_posix(),
        "outside": str(profile.parent / "unrelated.parquet"),
        "sql": "select 'not a filesystem path'",
    }
    put(profile, "saved_dataforges/test.json", json.dumps(value).encode())
    result = maintenance.maintain_profile(profile)
    restored = json.loads((profile_path("saved_dataforges") / "test.json").read_text())
    assert restored["snapshot"] == str(profile_path("qdefinitions") / "forge/result.parquet")
    assert restored["slash_path"] == restored["snapshot"]
    assert restored["outside"] == value["outside"]
    assert restored["sql"] == value["sql"]
    assert result["rewritten_json_files"] == 1


def test_restart_finishes_path_rewrite_after_interrupted_move(profile, monkeypatch):
    old = profile / "qdefinitions" / "test.parquet"
    put(profile, "qdefinitions/test.parquet")
    put(profile, "saved_queries/test.json", json.dumps({"snapshot": str(old)}).encode())
    real_writer = maintenance.write_json
    monkeypatch.setattr(maintenance, "write_json", Mock(side_effect=OSError("disk unavailable")))
    with pytest.raises(OSError, match="disk unavailable"):
        maintenance.maintain_profile(profile)
    assert not (profile / "layout.json").exists()
    monkeypatch.setattr(maintenance, "write_json", real_writer)
    maintenance.maintain_profile(profile)
    saved = json.loads((profile_path("saved_queries") / "test.json").read_text())
    assert saved["snapshot"] == str(profile_path("qdefinitions") / "test.parquet")


def test_migrated_key_decrypts_same_saved_credentials(profile):
    from suiteview.core.credential_manager import CredentialManager

    key = Fernet.generate_key()
    encrypted = Fernet(key).encrypt(b"synthetic-secret")
    put(profile, ".key", key)
    database = profile / "suiteview.db"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE connections (encrypted_username BLOB, encrypted_password BLOB)")
        connection.execute("INSERT INTO connections VALUES (?, ?)", (encrypted, encrypted))
    before = database.read_bytes()
    maintenance.maintain_profile(profile)
    assert profile_path("suiteview.db").read_bytes() == before
    assert profile_path(".key").read_bytes() == key
    manager = CredentialManager()
    assert manager.decrypt(encrypted) == "synthetic-secret"


def test_missing_key_does_not_replace_existing_credential_key(profile):
    from suiteview.core.credential_manager import CredentialManager

    database = profile_path("suiteview.db")
    database.parent.mkdir()
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE connections (encrypted_username BLOB, encrypted_password BLOB)")
        connection.execute("INSERT INTO connections VALUES (?, ?)", (b"encrypted", b"encrypted"))
    with pytest.raises(RuntimeError, match="encryption key is missing"):
        CredentialManager()
    assert not profile_path(".key").exists()


def test_fresh_database_does_not_recreate_tasktracker_tables(profile):
    from suiteview.data.database import Database

    database = Database()
    try:
        database.initialize_schema()
        names = {row[0] for row in database.connect().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "connections" in names
        assert not {"tasks", "task_attachments", "task_id_sequence"} & names
    finally:
        database.close()


def test_newer_layout_is_not_downgraded(profile):
    put(profile, "layout.json", b'{"version": 999}')
    with pytest.raises(maintenance.ProfileMaintenanceError, match="Unsupported"):
        maintenance.maintain_profile(profile)


def test_linked_directory_blocks_even_unrelated_cleanup(profile, monkeypatch):
    linked = profile / "workbench"
    linked.mkdir()
    real_check = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda path: path == linked or real_check(path))
    with pytest.raises(maintenance.ProfileMaintenanceError, match="Linked profile"):
        maintenance.maintain_profile(profile, cleanup=True)
    assert linked.exists()


def test_concurrent_maintenance_is_refused(profile):
    with maintenance._profile_lock(profile):
        with pytest.raises(maintenance.ProfileMaintenanceError, match="Another profile"):
            maintenance.maintain_profile(profile)


def test_running_launcher_blocks_before_any_files_change(tmp_path, monkeypatch):
    from suiteview.core import single_instance

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / ".suiteview"
    root.mkdir()
    put(root, "tasktracker.json", b"{}")
    kernel = SimpleNamespace(CreateMutexW=Mock(return_value=123), CloseHandle=Mock())
    monkeypatch.setattr(maintenance.ctypes, "WinDLL", Mock(return_value=kernel))
    monkeypatch.setattr(maintenance.ctypes, "get_last_error", lambda: 183)
    monkeypatch.setattr(single_instance, "owned_mutex_names", lambda: frozenset())
    with pytest.raises(maintenance.ProfileMaintenanceError, match="Save your work"):
        maintenance.maintain_profile(root, cleanup=True)
    kernel.CloseHandle.assert_called_once_with(123)
    assert {path.name for path in root.iterdir()} == {"tasktracker.json"}


def test_launcher_can_migrate_while_holding_its_own_identity(tmp_path, monkeypatch):
    from suiteview.core import single_instance

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / ".suiteview"
    kernel = SimpleNamespace(CreateMutexW=Mock(return_value=123), CloseHandle=Mock())
    monkeypatch.setattr(maintenance.ctypes, "WinDLL", Mock(return_value=kernel))
    monkeypatch.setattr(maintenance.ctypes, "get_last_error", lambda: 0)
    monkeypatch.setattr(
        single_instance, "owned_mutex_names", lambda: frozenset({"SuiteView_SingleInstance_Mutex"})
    )
    with maintenance._app_guard(root):
        assert kernel.CreateMutexW.call_count == 2
    assert kernel.CloseHandle.call_count == 2


def test_shortcut_repair_changes_only_profile_icon_paths(tmp_path, monkeypatch):
    from win32com.client import dynamic

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = tmp_path / ".suiteview"
    root.mkdir()
    put(root, "suiteview.ico", b"icon")
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    (desktop / "SuiteView.lnk").touch()
    (desktop / "SuiteView other.lnk").touch()
    intended = SimpleNamespace(IconLocation=str(root / "suiteview.ico") + ",0", Save=Mock())
    unrelated = SimpleNamespace(IconLocation=r"C:\Other\App.ico,0", Save=Mock())
    shell = SimpleNamespace(
        SpecialFolders=lambda _: str(desktop),
        CreateShortcut=lambda path: intended if Path(path).name == "SuiteView.lnk" else unrelated,
    )
    monkeypatch.setattr(dynamic, "Dispatch", lambda _: shell)
    updates = maintenance._shortcut_updates(root)
    assert updates == [(intended, str(root / "assets/suiteview.ico") + ",0")]
    intended.Save.assert_not_called()
    unrelated.Save.assert_not_called()


def test_runtime_storage_uses_registered_profile_locations():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "suiteview").rglob("*.py"):
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "profile_path" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                assert node.args[0].value in PROFILE_PATHS, str(path)
            if isinstance(node, ast.Constant) and node.value == ".suiteview":
                assert path.name in {"profile_paths.py", "profile_maintenance.py"}, str(path)


def test_preview_helpers_compile():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "tools").rglob("*.py"):
        source = path.read_text(encoding="utf-8-sig")
        if "diagnostics_dir" in source or "profile_path" in source:
            compile(source, str(path), "exec")
