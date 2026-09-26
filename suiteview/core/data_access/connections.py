"""Connection factory for SuiteView live data sources."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

import pyodbc

from suiteview.core import odbc_utils
from suiteview.core.data_access.errors import ConnectionUnavailable
from suiteview.core.data_sources import DEFAULT_REGION, UL_RATES_DSN, dsn_for_region
from suiteview.core.local_dev import (
    connect_local_policy_database,
    connect_local_rates_database,
    local_data_enabled,
)


class NamedSource(StrEnum):
    """Canonical live-source names understood by :class:`ConnectionFactory`."""

    POLICY_DB2 = "policy_db2"
    UL_RATES = "ul_rates"


@dataclass(frozen=True)
class ConnectionOptions:
    """Explicit connection options passed to ODBC/local connection openers."""

    autocommit: bool = True
    timeout: int | None = None
    readonly: bool = False
    attributes: Mapping[str, str] | None = None


class ConnectionFactory:
    """Open SuiteView data sources with one local-data gate and ODBC path."""

    def connect_named(
        self,
        source: NamedSource | str,
        *,
        region: str = DEFAULT_REGION,
        autocommit: bool = True,
        timeout: int | None = None,
        readonly: bool = False,
        attributes: Mapping[str, str] | None = None,
    ) -> Any:
        """Open a named source.

        ``policy_db2`` honors the exact ``SUITEVIEW_LOCAL_DATA == "1"`` gate.
        ``ul_rates`` honors the same gate for local rates; otherwise both use
        their configured ODBC DSNs.
        """
        normalized = NamedSource(source)
        if normalized is NamedSource.POLICY_DB2:
            return self.connect_policy_db2(
                region,
                autocommit=autocommit,
                timeout=timeout,
                readonly=readonly,
                attributes=attributes,
            )
        if normalized is NamedSource.UL_RATES:
            return self.connect_ul_rates(
                autocommit=autocommit,
                timeout=timeout,
                readonly=readonly,
                attributes=attributes,
            )
        raise ConnectionUnavailable(f"Unsupported data source: {source!r}")

    def connect_policy_db2(
        self,
        region: str = DEFAULT_REGION,
        *,
        autocommit: bool = True,
        timeout: int | None = None,
        readonly: bool = False,
        attributes: Mapping[str, str] | None = None,
    ) -> Any:
        """Open the policy DB2 source for *region* or the gated local clone."""
        if local_data_enabled():
            try:
                return connect_local_policy_database(region)
            except Exception as exc:
                raise ConnectionUnavailable(
                    f"Failed to connect to local SuiteView policy database: {exc}"
                ) from exc
        return self.connect_dsn(
            dsn_for_region(region),
            autocommit=autocommit,
            timeout=timeout,
            readonly=readonly,
            attributes=attributes,
        )

    def connect_ul_rates(
        self,
        *,
        autocommit: bool = True,
        timeout: int | None = None,
        readonly: bool = False,
        attributes: Mapping[str, str] | None = None,
    ) -> Any:
        """Open UL_Rates or the gated local rates clone."""
        if local_data_enabled():
            try:
                return connect_local_rates_database()
            except Exception as exc:
                raise ConnectionUnavailable(
                    f"Failed to connect to local SuiteView rates database: {exc}"
                ) from exc
        return self.connect_dsn(
            UL_RATES_DSN,
            autocommit=autocommit,
            timeout=timeout,
            readonly=readonly,
            attributes=attributes,
        )

    def connect_dsn(
        self,
        dsn: str,
        *,
        autocommit: bool,
        timeout: int | None = None,
        readonly: bool = False,
        attributes: Mapping[str, str] | None = None,
    ) -> pyodbc.Connection:
        """Open any ODBC DSN through the shared ODBC utilities."""
        try:
            if attributes:
                suffix = "".join(f";{key}={value}" for key, value in attributes.items())
                return odbc_utils.connect_connection_string(
                    f"DSN={dsn}{suffix}",
                    autocommit=autocommit,
                    timeout=timeout,
                    readonly=readonly,
                )
            return odbc_utils.connect_dsn(
                dsn, autocommit=autocommit, timeout=timeout, readonly=readonly,
            )
        except Exception as exc:
            raise ConnectionUnavailable(f"Failed to connect to DSN {dsn!r}: {exc}") from exc

    def connect_connection_string(
        self,
        connection_string: str,
        *,
        autocommit: bool,
        timeout: int | None = None,
        readonly: bool = False,
    ) -> pyodbc.Connection:
        """Open an explicit ODBC connection string."""
        try:
            return odbc_utils.connect_connection_string(
                connection_string,
                autocommit=autocommit,
                timeout=timeout,
                readonly=readonly,
            )
        except Exception as exc:
            raise ConnectionUnavailable("Failed to connect with the supplied ODBC string.") from exc

    def connect_access_file(
        self,
        path: str,
        *,
        autocommit: bool = True,
        timeout: int | None = None,
        readonly: bool = False,
    ) -> pyodbc.Connection:
        """Open an Access database file through the shared ODBC utilities."""
        try:
            return odbc_utils.connect_access_file(
                path, autocommit=autocommit, timeout=timeout, readonly=readonly,
            )
        except Exception as exc:
            raise ConnectionUnavailable(f"Failed to connect to Access file {path!r}: {exc}") from exc


connection_factory = ConnectionFactory()
