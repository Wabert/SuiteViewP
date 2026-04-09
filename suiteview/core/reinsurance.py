"""
SuiteView - Reinsurance Module (TAICession Lookup)
====================================================
Shared module to query the TAICession table in the UL_Rates SQL Server
database.  Used by PolView (Reinsurance tab) and ABRQuote.

The query finds all cession records for a given policy number at the
latest available month-end date.

Usage:
    from suiteview.core.reinsurance import fetch_tai_cession

    result = fetch_tai_cession("UE266768")
    if result.found:
        for row in result.rows:
            print(row)
    else:
        print(f"No records as of {result.month_end}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List, Dict, Any, Optional

import pyodbc

logger = logging.getLogger(__name__)

ODBC_DSN = "UL_Rates"

# All columns returned by the TAICession query
TAI_CESSION_COLUMNS = [
    "Co", "Pol", "Cov", "CessSeq", "ReinsCo", "RepCo",
    "FromDt", "ToDt", "RepDt", "PolDt", "ReinsDt", "PolStatus",
    "Treaty", "TreatyRef", "TreatyGrp", "TrtyJoinMeth", "ReinsTyp",
    "Plan", "SrchPlan", "ProdCD", "Face", "Retn", "Ceded",
    "NAR", "Filler6", "monthEnd",
]

# Display-friendly header names (same as column names)
TAI_CESSION_HEADERS = list(TAI_CESSION_COLUMNS)


@dataclass
class TAICessionResult:
    """Result of a TAICession lookup."""
    found: bool = False
    month_end: str = ""          # YYYYMM string from latest _monthEnd
    rows: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""


def _get_connection() -> pyodbc.Connection:
    """Open a connection to UL_Rates via ODBC DSN."""
    return pyodbc.connect(f"DSN={ODBC_DSN}", autocommit=True)


def fetch_tai_cession(policy_number: str) -> TAICessionResult:
    """
    Query the TAICession table for the given policy number.

    Finds the latest _monthEnd date for the policy, then returns all
    cession rows at that month-end.

    Args:
        policy_number: Policy number to search (matched against _Pol).

    Returns:
        TAICessionResult with found=True and rows populated if records
        exist, or found=False with month_end set to the latest available
        month-end across the entire table (for the "not found" message).
    """
    result = TAICessionResult()
    policy_number = policy_number.strip()

    try:
        conn = _get_connection()
    except Exception as e:
        logger.warning("Could not connect to UL_Rates for TAICession lookup: %s", e)
        result.error = str(e)
        return result

    try:
        cursor = conn.cursor()

        # Step 1: Find the latest month-end for this specific policy
        cursor.execute(
            "SELECT MAX(monthEnd) FROM TAICession WHERE Pol = ?",
            (policy_number,),
        )
        row = cursor.fetchone()
        policy_month_end = row[0] if row and row[0] else None

        if policy_month_end:
            # Records exist for this policy
            result.month_end = str(policy_month_end).strip()
            result.found = True

            # Step 2: Fetch all cession records at latest month-end
            col_list = ", ".join(f"[{c}]" for c in TAI_CESSION_COLUMNS)
            sql = (
                f"SELECT {col_list} FROM TAICession "
                f"WHERE Pol = ? AND monthEnd = ?"
            )
            cursor.execute(sql, (policy_number, result.month_end))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            for db_row in rows:
                result.rows.append(
                    {col: db_row[i] for i, col in enumerate(columns)}
                )
        else:
            # No records for this policy — get global latest month-end
            # for the informational message
            cursor.execute("SELECT MAX(monthEnd) FROM TAICession")
            global_row = cursor.fetchone()
            result.month_end = (
                str(global_row[0]).strip()
                if global_row and global_row[0]
                else ""
            )

        cursor.close()
        conn.close()

    except Exception as e:
        logger.warning("TAICession query failed: %s", e)
        result.error = str(e)

    return result


def _cyberlife_to_tai_co(company_code: str, policy_number: str) -> str:
    """Map a Cyberlife company code (e.g. "01") to the TAICession Co value.

    Most companies simply prefix with "1" (01→101, 04→104, …).
    Company 26 maps to "FFL" when the policy number starts with "000"
    or "FF", otherwise to "130".
    """
    company_code = company_code.strip()
    pol = policy_number.strip().upper()
    if company_code == "26":
        if pol.startswith("000") or pol.startswith("FF"):
            return "FFL"
        return "130"
    return f"1{company_code.zfill(2)}"


def fetch_reinsurer_list(
    policy_number: str,
    company_code: str,
    quote_date: date,
) -> str:
    """Return a comma-separated list of distinct RepCo values for a policy.

    Queries TAICession for the given policy number and mapped TAI company
    code, using the latest monthEnd on or before the last month-end prior
    to *quote_date*.  For example, if the quote date is 2026-04-06 the
    cutoff monthEnd is "202603".

    Args:
        policy_number: CyberLife policy number.
        company_code:  CyberLife 2-digit company code (e.g. "01", "26").
        quote_date:    ABR quote date.

    Returns:
        A string like "SW, MU, GG" or "(none)" if no cession records
        are found.
    """
    policy_number = policy_number.strip()
    tai_co = _cyberlife_to_tai_co(company_code, policy_number)

    # Compute the last month-end before the quote date (YYYYMM format).
    # If quote_date is in April 2026, the prior month-end is 202603.
    if quote_date.month == 1:
        cutoff = f"{quote_date.year - 1}12"
    else:
        cutoff = f"{quote_date.year}{quote_date.month - 1:02d}"

    try:
        conn = _get_connection()
    except Exception as e:
        logger.warning("Could not connect to UL_Rates for reinsurer lookup: %s", e)
        return "(none)"

    try:
        cursor = conn.cursor()

        # Find the latest monthEnd <= cutoff for this Co + Pol
        cursor.execute(
            "SELECT MAX(monthEnd) FROM TAICession "
            "WHERE Co = ? AND Pol = ? AND monthEnd <= ?",
            (tai_co, policy_number, cutoff),
        )
        row = cursor.fetchone()
        month_end = row[0] if row and row[0] else None

        if not month_end:
            cursor.close()
            conn.close()
            return "(none)"

        month_end = str(month_end).strip()

        # Fetch distinct RepCo values at that month-end
        cursor.execute(
            "SELECT DISTINCT [RepCo] FROM TAICession "
            "WHERE Co = ? AND Pol = ? AND monthEnd = ?",
            (tai_co, policy_number, month_end),
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        rep_cos = [
            str(r[0]).strip() for r in rows if r[0] and str(r[0]).strip()
        ]
        return ", ".join(sorted(rep_cos)) if rep_cos else "(none)"

    except Exception as e:
        logger.warning("Reinsurer list query failed: %s", e)
        return "(none)"
