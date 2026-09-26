import ast
import sqlite3
from pathlib import Path

import pytest

from suiteview.data.database import Database
from suiteview.data.repositories import EmailRepository


ROOT = Path(__file__).resolve().parents[1]
SCOPE_DIRS = [
    Path("suiteview/core"),
    Path("suiteview/data"),
    Path("suiteview/ui"),
    Path("suiteview/file_nav"),
    Path("suiteview/mainframe_nav"),
    Path("suiteview/screenshot_manager"),
    Path("suiteview/agent_chat"),
    Path("suiteview/administrator"),
    Path("suiteview/scratchpad"),
    Path("suiteview/utils"),
]
SCOPE_FILES = {Path("suiteview/main.py")}
EXCLUDED = {Path("suiteview/file_nav/file_explorer_core.py")}


def _scoped_files():
    for path in (ROOT / "suiteview").rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel in EXCLUDED:
            continue
        if rel in SCOPE_FILES or any(rel.is_relative_to(scope) for scope in SCOPE_DIRS):
            yield path


def test_cleanup_scope_has_no_bare_except_handlers():
    offenders = []
    for path in _scoped_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert offenders == []


def test_database_migrations_surface_non_schema_operational_errors():
    class Cursor:
        def execute(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("database is locked")

    class Connection:
        def cursor(self):
            return Cursor()

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        Database(":memory:")._run_migrations(Connection())


def test_email_repository_sender_name_migration_surfaces_unexpected_db_errors():
    class FailingDb:
        def execute(self, sql, params=()):
            if "ALTER TABLE email_attachments" in sql:
                raise sqlite3.OperationalError("database is locked")

    repo = object.__new__(EmailRepository)
    repo.db = FailingDb()

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        repo._ensure_tables()
