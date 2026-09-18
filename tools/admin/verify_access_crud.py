"""Exercise real SQL Server CRUD using session-local #tables, never live access rows.

The adapter rewrites only the three access-table identifiers to temporary tables.
They disappear when the connection closes; no persistent schema is created.
"""

from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pyodbc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.administrator import service


class TemporaryCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @staticmethod
    def sql(statement):
        for table in ("SV_AccessRoleApp", "SV_AccessRole", "SV_AccessUser"):
            statement = statement.replace(f"[dbo].[{table}]", f"[#{table}]")
        if "[dbo]" in statement:
            raise ValueError("Verification refused an unmapped live-table reference.")
        return statement

    def execute(self, statement, *parameters):
        self.cursor.execute(self.sql(statement), *parameters)
        return self

    def executemany(self, statement, parameters):
        self.cursor.executemany(self.sql(statement), parameters)
        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        self.cursor.close()


class BorrowedConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return TemporaryCursor(self.connection.cursor())

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        # The outer verification owns the connection and its session-local tables.
        pass


def main():
    before = service.AccessRepository().load()
    actor = service.current_network_id()
    checks = []
    with closing(pyodbc.connect("DSN=UL_Rates", autocommit=False, timeout=10)) as connection:
        connection.timeout = 15
        with closing(connection.cursor()) as cursor:
            cursor.execute("""
                CREATE TABLE #SV_AccessRole (
                    RoleCode varchar(50) NOT NULL PRIMARY KEY,
                    Description nvarchar(500) NOT NULL,
                    AllApps bit NOT NULL, CanUpdateDatabase bit NOT NULL,
                    CanWriteSupportFiles bit NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE #SV_AccessUser (
                    NetworkID varchar(128) NOT NULL PRIMARY KEY,
                    Name nvarchar(200) NOT NULL, Enabled bit NOT NULL, RoleCode varchar(50) NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE #SV_AccessRoleApp (
                    RoleCode varchar(50) NOT NULL, AppCode varchar(50) NOT NULL,
                    PRIMARY KEY (RoleCode, AppCode), CHECK (AppCode <> 'RERUN')
                )
            """)
            cursor.execute("INSERT INTO #SV_AccessRole VALUES ('ADMIN', 'Test admin', 1, 1, 1)")
            cursor.execute("INSERT INTO #SV_AccessUser VALUES (?, 'Test actor', 1, 'ADMIN')", actor)
            connection.commit()
        with patch.object(service, "_connect", lambda: BorrowedConnection(connection)):
            repository = service.AccessRepository()
            assert repository.is_admin()
            role = service.AccessRole("TEST", "A test role", False, False, True, frozenset({"POLVIEW"}))
            repository.save_role(role, original=None)
            user = service.AccessUser("TEST_USER", "O'Connor", False, "TEST")
            repository.save_user(user, original=None)
            loaded = repository.load()
            assert role in loaded.roles and user in loaded.users
            checks.append("create_role_grants_and_user")
            edited = replace(user, name="Updated name", enabled=True)
            repository.save_user(edited, original=user)
            assert edited in repository.load().users
            checks.append("update_user")
            try:
                repository.save_user(user, original=user)
            except ValueError as exc:
                assert "another administrator" in str(exc)
            else:
                raise AssertionError("Stale update was accepted")
            checks.append("optimistic_conflict")
            changed = replace(role, description="Changed", apps=frozenset({"ABR", "QUERY"}))
            repository.save_role(changed, original=role)
            assert changed in repository.load().roles
            checks.append("replace_role_and_whitelist")
            try:
                repository.save_role(replace(changed, description="Must roll back",
                                             apps=frozenset({"RERUN"})), original=changed)
            except pyodbc.IntegrityError:
                pass
            else:
                raise AssertionError("Expected temp-table CHECK failure")
            assert changed in repository.load().roles
            checks.append("failed_whitelist_insert_rolls_back_role_and_grants")
            try:
                repository.delete_role(changed)
            except ValueError as exc:
                assert "Reassign" in str(exc)
            else:
                raise AssertionError("Assigned role deletion was accepted")
            checks.append("assigned_role_protected")
            admin = next(u for u in repository.load().users if u.network_id == actor)
            try:
                repository.delete_user(admin)
            except ValueError as exc:
                assert "at least one enabled ADMIN" in str(exc)
            else:
                raise AssertionError("Last ADMIN deletion was accepted")
            checks.append("last_admin_protected")
            repository.delete_user(edited)
            repository.delete_role(changed)
            assert len(repository.load().users) == len(repository.load().roles) == 1
            checks.append("delete_user_role_and_grants")
    after = service.AccessRepository().load()
    if before != after:
        raise RuntimeError("Live access data changed during verification; inspect concurrent edits.")
    print(json.dumps({
        "all_ok": True, "checks": checks, "live_access_tables_unchanged": True,
        "test_tables": "connection-local SQL Server #tables, removed on disconnect",
    }, indent=2))


if __name__ == "__main__":
    main()
