"""Named SuiteView data sources and DB2 region meanings."""

from __future__ import annotations

from dataclasses import dataclass

from suiteview.core.db2_constants import (
    DEFAULT_REGION,
    DEFAULT_SCHEMA,
    REGION_DSN_MAP,
    REGION_SCHEMA_MAP,
)

UL_RATES_DSN = "UL_Rates"
UL_RATES_DATABASE = "UL_Rates"
VRD_PROD_DSN = "VRD Prod"

NEON_DSN = REGION_DSN_MAP["CKPR"]
NEON_DSNM = REGION_DSN_MAP["CKMO"]
NEON_DSNT = REGION_DSN_MAP["CKAS"]
NEON_DSNS = "NEON_DSNS"

REGION_CKPR = "CKPR"
REGION_CKMO = "CKMO"
REGION_CKAS = "CKAS"
REGION_CKCS = "CKCS"
REGION_CKSR = "CKSR"


@dataclass(frozen=True)
class DataSourceInfo:
    """One configured source name and its one-line purpose."""

    name: str
    meaning: str


DATA_SOURCE_MEANINGS: dict[str, DataSourceInfo] = {
    UL_RATES_DSN: DataSourceInfo(
        UL_RATES_DSN,
        "SQL Server rate, access-control, ABR, WL and auxiliary policy tables.",
    ),
    VRD_PROD_DSN: DataSourceInfo(
        VRD_PROD_DSN,
        "SQL Server VRD production ledger/reporting source.",
    ),
    NEON_DSN: DataSourceInfo(
        NEON_DSN,
        "DB2 CyberLife production ODBC source for CKPR.",
    ),
    NEON_DSNM: DataSourceInfo(
        NEON_DSNM,
        "DB2 CyberLife model-office ODBC source for CKMO.",
    ),
    NEON_DSNT: DataSourceInfo(
        NEON_DSNT,
        "DB2 CyberLife test/acceptance ODBC source shared by CKAS, CKCS and CKSR.",
    ),
    NEON_DSNS: DataSourceInfo(
        NEON_DSNS,
        "DB2 CyberLife secondary/system ODBC source when configured on a workstation.",
    ),
}

REGION_MEANINGS: dict[str, DataSourceInfo] = {
    REGION_CKPR: DataSourceInfo(REGION_CKPR, "CyberLife production region; default policy-data region."),
    REGION_CKMO: DataSourceInfo(REGION_CKMO, "CyberLife model-office region."),
    REGION_CKAS: DataSourceInfo(REGION_CKAS, "CyberLife acceptance region using UNIT schema."),
    REGION_CKCS: DataSourceInfo(REGION_CKCS, "CyberLife Cybertek/test region using CYBERTEK schema."),
    REGION_CKSR: DataSourceInfo(REGION_CKSR, "CyberLife system region using CKSR schema."),
}


def dsn_for_region(region: str) -> str:
    """Return the configured DB2 DSN for a CyberLife region."""
    return REGION_DSN_MAP[region.strip().upper()]


def schema_for_region(region: str) -> str:
    """Return the DB2 schema qualifier for a CyberLife region."""
    return REGION_SCHEMA_MAP.get(region.strip().upper(), DEFAULT_SCHEMA)


__all__ = [
    "UL_RATES_DSN",
    "UL_RATES_DATABASE",
    "VRD_PROD_DSN",
    "NEON_DSN",
    "NEON_DSNM",
    "NEON_DSNT",
    "NEON_DSNS",
    "REGION_CKPR",
    "REGION_CKMO",
    "REGION_CKAS",
    "REGION_CKCS",
    "REGION_CKSR",
    "DEFAULT_REGION",
    "DATA_SOURCE_MEANINGS",
    "REGION_MEANINGS",
    "dsn_for_region",
    "schema_for_region",
]
