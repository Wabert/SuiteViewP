"""Standalone CyberLife lookups ported from frmAudit's Other queries page."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

import pandas as pd

from suiteview.core.db2_connection import DB2Connection
from suiteview.core.db2_constants import DEFAULT_SCHEMA, REGION_DSN_MAP, REGION_SCHEMA_MAP
from .sql_helpers import esc

LookupKind = Literal["riders", "bases", "values"]


@dataclass(frozen=True)
class OtherQuery:
    sql: str
    params: tuple[str, ...]
    columns: tuple[str, ...]

    def display_sql(self) -> str:
        """Render a copyable SQL preview; execution still uses bound parameters."""
        parts = self.sql.split("?")
        return "".join(
            part + f"'{esc(value)}'" for part, value in zip(parts, self.params)
        ) + parts[-1]


def _identifier(value: str, label: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", value):
        raise ValueError(f"{label}: enter an unqualified name using letters, digits and underscores.")
    return value


def build_other_query(
    kind: LookupKind, region: str, *, plancode: str = "",
    show_policies: bool = False, table: str = "", field: str = "",
) -> OtherQuery:
    if region not in REGION_DSN_MAP:
        raise ValueError(f"Unknown CyberLife region: {region}")
    schema = REGION_SCHEMA_MAP.get(region, DEFAULT_SCHEMA)
    if kind == "values":
        table = _identifier(table, "Table")
        field = _identifier(field, "Field")
        count = "SUM(CASE WHEN V.TCH_POL_ID IS NOT NULL THEN 1 ELSE 0 END)"
        return OtherQuery(
            f'SELECT V."{field}", {count}\n'
            f'FROM {schema}."{table}" V\n'
            f'GROUP BY V."{field}"\n'
            f'ORDER BY {count} DESC, V."{field}"',
            (), ("Field Value", "Record Count"),
        )
    if kind not in ("riders", "bases"):
        raise ValueError(f"Unknown Other Queries lookup: {kind}")
    plancode = plancode.strip().upper()
    if not plancode:
        raise ValueError("Enter a base plancode." if kind == "riders" else "Enter a rider plancode.")
    aliases = ("B", "R") if kind == "riders" else ("R", "B")
    columns = (
        ("Base Plancode", "Base Form", "Rider Plancode", "Rider Form")
        if kind == "riders" else
        ("Rider Plancode", "Rider Form", "Base Plancode", "Base Form")
    )
    fields = [f"{alias}.{column}" for alias in aliases for column in ("PLN_DES_SER_CD", "POL_FRM_NBR")]
    # The live Data Virtualization driver counts distinct values for COUNT(column).
    selected = fields + (["P.CK_POLICY_NBR", "P.CK_CMP_CD"] if show_policies else ["COUNT(*)"])
    sql = (
        "SELECT " + ", ".join(selected) + "\n"
        f"FROM {schema}.LH_COV_PHA R\n"
        f"INNER JOIN {schema}.LH_COV_PHA B\n"
        "  ON R.CK_SYS_CD = B.CK_SYS_CD AND R.CK_CMP_CD = B.CK_CMP_CD\n"
        "  AND R.TCH_POL_ID = B.TCH_POL_ID AND B.COV_PHA_NBR = 1\n"
    )
    if show_policies:
        sql += (
            f"INNER JOIN {schema}.LH_BAS_POL P\n"
            "  ON P.CK_SYS_CD = R.CK_SYS_CD AND P.CK_CMP_CD = R.CK_CMP_CD\n"
            "  AND P.TCH_POL_ID = R.TCH_POL_ID\n"
        )
    if kind == "riders":
        sql += "WHERE B.PLN_DES_SER_CD = ? AND R.PLN_DES_SER_CD <> ? AND R.COV_PHA_NBR > 1\n"
        params = (plancode, plancode)
    else:
        sql += "WHERE R.PLN_DES_SER_CD = ? AND R.COV_PHA_NBR > 1\n"
        params = (plancode,)
    if not show_policies:
        sql += "GROUP BY " + ", ".join(fields) + "\n"
    sql += "ORDER BY " + ", ".join(fields + (["P.CK_CMP_CD", "P.CK_POLICY_NBR", "R.COV_PHA_NBR"] if show_policies else []))
    return OtherQuery(
        sql, params,
        columns + (("Policy Number", "Company") if show_policies else ("Rider Count",)),
    )


def execute_other_query(query: OtherQuery, region: str) -> pd.DataFrame:
    """Run with the standard isolated DB2 connection, never on a shared cursor."""
    columns, rows = DB2Connection(region).execute_query_with_headers_isolated(
        query.sql, query.params,
    )
    if len(columns) != len(query.columns):
        raise ValueError(f"Lookup returned {len(columns)} columns; expected {len(query.columns)}.")
    return pd.DataFrame.from_records([tuple(row) for row in rows], columns=query.columns)
