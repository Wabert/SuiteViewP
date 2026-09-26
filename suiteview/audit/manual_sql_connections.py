"""Manual SQL connection discovery services."""
from __future__ import annotations

import logging

import pyodbc

logger = logging.getLogger(__name__)


class ManualSqlConnectionService:
    """Return saved ODBC connections plus system/user DSNs."""

    def connections(self) -> list[tuple[str, str]]:
        saved: list[tuple[str, str]] = []
        seen: set[str] = set()
        self._add_saved_connections(saved, seen)
        self._add_system_dsns(saved, seen)
        return saved

    def _add_saved_connections(
        self,
        saved: list[tuple[str, str]],
        seen: set[str],
    ) -> None:
        try:
            from suiteview.data.repositories import get_connection_repository

            for connection in get_connection_repository().get_all_connections():
                connection_string = str(connection.get("connection_string") or "")
                if not connection_string.upper().startswith("DSN="):
                    continue
                dsn = connection_string.split("=", 1)[1].strip()
                dsn_key = dsn.lower()
                if not dsn or dsn_key in seen:
                    continue
                name = str(connection.get("connection_name") or dsn)
                saved.append((f"{name} ({dsn})", dsn))
                seen.add(dsn_key)
        except Exception:
            logger.exception("Failed to load saved ODBC connections")

    def _add_system_dsns(
        self,
        saved: list[tuple[str, str]],
        seen: set[str],
    ) -> None:
        try:
            for dsn in sorted(pyodbc.dataSources().keys(), key=str.lower):
                dsn_key = dsn.lower()
                if dsn_key in seen:
                    continue
                saved.append((dsn, dsn))
                seen.add(dsn_key)
        except Exception:
            logger.exception("Failed to load system ODBC data sources")

