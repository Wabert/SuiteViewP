"""Create the initial SuiteView access tables in live UL_Rates, without runtime changes.

Usage:
    venv\\Scripts\\python.exe tools\\admin\\create_access_control.py
    venv\\Scripts\\python.exe tools\\admin\\create_access_control.py --check
    venv\\Scripts\\python.exe tools\\admin\\create_access_control.py --apply

Default: offline seed summary. --check: read-only live comparison.
--apply: create and seed all three tables atomically, then verify after reconnect.
Existing tables are never overwritten; a partial setup or changed seed is an error.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

import pyodbc

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.core.build_env import guard_data_writable
from suiteview.core.access_control import APP_CODES as APPS


ROLES = (
    ("ADMIN", 1, 1, 1, "All access to all roles and apps, even experimental"),
    ("SUPPORT", 0, 1, 1, "All access except for some apps"),
    ("BUSINESS", 0, 0, 1, "Access to generate policy support folders"),
    ("NONBUSINESS", 0, 0, 0,
     "Cannot make updates to database or policy support folders"),
)
BUSINESS_APPS = (
    "POLVIEW", "FILENAV", "ABR", "RERUN", "QUERY", "SCRATCHPAD", "SCREENSHOT",
)
ROLE_APPS = (
    tuple(("SUPPORT", app) for app in APPS if app != "ALBERT")
    + tuple((role, app) for role in ("BUSINESS", "NONBUSINESS") for app in BUSINESS_APPS)
)
USERS = (
    ("AB7Y02", "Rboert Haessly", 1, "ADMIN"),
    ("AC7C02", "Thanh Phan", 0, "SUPPORT"),
    ("AB8Y18", "Alejandro Gonzalez", 0, "SUPPORT"),
    ("F01722", "Dave Mason", 0, "SUPPORT"),
    ("AB2X07", "Jackie Barabino", 0, "SUPPORT"),
    ("MK2021", "Veronica Tovar", 0, "SUPPORT"),
    ("CC3G1R", "Kellie Betz", 0, "SUPPORT"),
    ("AC1Z42", "Jordan Carrillo", 1, "ADMIN"),
    ("AB8Y21", "Paul Peterson", 0, "NONBUSINESS"),
    ("AB8Y39", "Jihui Liu", 0, "NONBUSINESS"),
    ("AB8Y58", "Jeff Bridge", 0, "NONBUSINESS"),
    ("AC7B90", "Nathan Parrish", 0, "NONBUSINESS"),
    ("AC7C00", "Steve Hancock", 0, "NONBUSINESS"),
    ("AD9I64", "Melissa Morris", 0, "NONBUSINESS"),
    ("AD9I77", "Brenda Pratt", 0, "NONBUSINESS"),
    ("CC3G82", "Whitney Eversole", 0, "BUSINESS"),
    ("CL6F03", "Tricia Nelon", 0, "BUSINESS"),
    ("CL6H07", "Mary Darr", 0, "BUSINESS"),
    ("FF01360", "Eileen Hughes", 0, "NONBUSINESS"),
    ("FI5329", "Dave Beckemeier", 0, "NONBUSINESS"),
    ("OI2U16", "Reina Sher-Kraft", 0, "BUSINESS"),
    ("OI2U35", "Pam Nelson", 0, "BUSINESS"),
)

DDL = {
    "SV_AccessRole": """
        CREATE TABLE [dbo].[SV_AccessRole] (
            [RoleCode] varchar(50) NOT NULL
                CONSTRAINT [PK_SV_AccessRole] PRIMARY KEY,
            [AllApps] bit NOT NULL CONSTRAINT [DF_SV_AccessRole_AllApps] DEFAULT (0),
            [CanUpdateDatabase] bit NOT NULL
                CONSTRAINT [DF_SV_AccessRole_CanUpdateDatabase] DEFAULT (0),
            [CanWriteSupportFiles] bit NOT NULL
                CONSTRAINT [DF_SV_AccessRole_CanWriteSupportFiles] DEFAULT (0),
            [Description] nvarchar(500) NOT NULL
        )
    """,
    "SV_AccessRoleApp": """
        CREATE TABLE [dbo].[SV_AccessRoleApp] (
            [RoleCode] varchar(50) NOT NULL,
            [AppCode] varchar(50) NOT NULL,
            CONSTRAINT [PK_SV_AccessRoleApp] PRIMARY KEY ([RoleCode], [AppCode]),
            CONSTRAINT [FK_SV_AccessRoleApp_Role] FOREIGN KEY ([RoleCode])
                REFERENCES [dbo].[SV_AccessRole] ([RoleCode])
        )
    """,
    "SV_AccessUser": """
        CREATE TABLE [dbo].[SV_AccessUser] (
            [NetworkID] varchar(128) NOT NULL
                CONSTRAINT [PK_SV_AccessUser] PRIMARY KEY,
            [Name] nvarchar(200) NOT NULL,
            [Enabled] bit NOT NULL CONSTRAINT [DF_SV_AccessUser_Enabled] DEFAULT (0),
            [RoleCode] varchar(50) NOT NULL,
            CONSTRAINT [FK_SV_AccessUser_Role] FOREIGN KEY ([RoleCode])
                REFERENCES [dbo].[SV_AccessRole] ([RoleCode])
        )
    """,
}
COLUMNS = {
    "SV_AccessRole": ("RoleCode", "AllApps", "CanUpdateDatabase",
                      "CanWriteSupportFiles", "Description"),
    "SV_AccessRoleApp": ("RoleCode", "AppCode"),
    "SV_AccessUser": ("NetworkID", "Name", "Enabled", "RoleCode"),
}
SEED = {"SV_AccessRole": ROLES, "SV_AccessRoleApp": ROLE_APPS, "SV_AccessUser": USERS}


def seed_summary() -> dict:
    return {
        "expected_rows": {table: len(rows) for table, rows in SEED.items()},
        "enabled_users": [row[0] for row in USERS if row[2]],
        "app_counts": {
            role[0]: "all current and future" if role[1] else
            sum(row[0] == role[0] for row in ROLE_APPS)
            for role in ROLES
        },
        "runtime_enforcement_changed": False,
    }


def existing_tables(cursor: pyodbc.Cursor) -> list[str]:
    return [
        table for table in DDL
        if cursor.execute("SELECT OBJECT_ID(?, 'U')", f"dbo.{table}").fetchone()[0]
        is not None
    ]


def verify_seed(cursor: pyodbc.Cursor) -> None:
    """Compare every stored value, not just row counts."""
    for table, expected in SEED.items():
        columns = ", ".join(f"[{column}]" for column in COLUMNS[table])
        actual = [tuple(row) for row in cursor.execute(
            f"SELECT {columns} FROM [dbo].[{table}]"
        ).fetchall()]
        if sorted(actual) != sorted(expected):
            raise ValueError(
                f"dbo.{table} does not match the initial seed. "
                "No existing permissions will be overwritten."
            )


def provision(connection: pyodbc.Connection, *, apply: bool) -> dict:
    if apply:
        guard_data_writable("create SuiteView access-control tables")
    try:
        with closing(connection.cursor()) as cursor:
            database = cursor.execute(
                "SELECT DB_NAME(), CAST(SERVERPROPERTY('ServerName') AS nvarchar(128))"
            ).fetchone()
            if str(database[0]).upper() != "UL_RATES":
                raise ValueError(f"Expected UL_Rates database, connected to {database[0]!r}.")
            report = {"database": database[0], "server": database[1], **seed_summary()}
            found = existing_tables(cursor)
            if found and len(found) != len(DDL):
                raise ValueError(f"Partial access-table setup found: {found}. No changes made.")
            if found:
                verify_seed(cursor)
                return {**report, "state": "verified_existing", "created": False}
            if not apply:
                return {**report, "state": "not_created", "created": False}
            cursor.execute("SET XACT_ABORT ON")
            for table, sql in DDL.items():
                cursor.execute(sql)
                columns = ", ".join(f"[{column}]" for column in COLUMNS[table])
                placeholders = ", ".join("?" for _ in COLUMNS[table])
                cursor.executemany(
                    f"INSERT INTO [dbo].[{table}] ({columns}) VALUES ({placeholders})",
                    SEED[table],
                )
            verify_seed(cursor)
            connection.commit()
            return {**report, "state": "created", "created": True}
    finally:
        connection.rollback()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Compare live data read-only")
    mode.add_argument("--apply", action="store_true", help="Create missing tables and seed")
    args = parser.parse_args()
    try:
        if not (args.check or args.apply):
            report = {"state": "offline_preview", **seed_summary()}
        else:
            if args.apply:
                guard_data_writable("create SuiteView access-control tables")
            with closing(pyodbc.connect(
                "DSN=UL_Rates", autocommit=False, timeout=10
            )) as connection:
                report = provision(connection, apply=args.apply)
            if args.apply:
                with closing(pyodbc.connect(
                    "DSN=UL_Rates", autocommit=False, timeout=10
                )) as connection:
                    verified = provision(connection, apply=False)
                if verified["state"] != "verified_existing":
                    raise RuntimeError("Post-commit verification failed: tables are missing.")
                report["verified_after_reconnect"] = True
        print(json.dumps(report, indent=2))
        return 0
    except (pyodbc.Error, ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
