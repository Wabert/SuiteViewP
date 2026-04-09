"""
TAI query builder — builds and executes TAI Cession SQL queries.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import pyodbc

from .sql_helpers import esc, in_list

logger = logging.getLogger(__name__)

TAI_DEFAULT_COLUMNS = [
    "monthEnd", "Co", "Pol", "Cov", "CessSeq", "ReinsCo", "RepCo",
    "FromDt", "ToDt", "RepDt", "Mode", "PolDt", "ReinsDt", "PolStatus",
    "AF", "Treaty", "ReinsTyp", "Plan", "SrchPlan", "ProdCD", "Face",
    "Retn", "Ceded", "NAR", "Prem1", "Prem2", "Prem3", "CstCntr",
    "LOB", "Filler6",
]


def build_tai_sql(ct, max_count_text: str) -> str:
    """Build a SELECT query for the TAICession table from TAI Cession tab filters.

    Parameters
    ----------
    ct : TaiCessionTab
        The TAI Cession tab widget with all filter controls.
    max_count_text : str
        The max row count text (empty string for all rows).
    """
    table = ct.cmb_table.currentText()
    if table == "(none)":
        raise ValueError("Please select a table first.")

    where_parts: list[str] = []

    # Date range (monthEnd column, YYYYMM format)
    date_from = ct.txt_date_from.text().strip()
    date_to = ct.txt_date_to.text().strip()
    if date_from and date_to:
        where_parts.append(
            f"monthEnd BETWEEN '{esc(date_from)}' AND '{esc(date_to)}'")
    elif date_from:
        where_parts.append(f"monthEnd >= '{esc(date_from)}'")
    elif date_to:
        where_parts.append(f"monthEnd <= '{esc(date_to)}'")

    # Inforce checkbox
        where_parts.append("PolStatus = 'PMP'")

    # Status Code
    if ct.chk_status_code.isChecked() and ct.list_status_code.selectedItems():
        codes = [item.text()[:3].strip()
                 for item in ct.list_status_code.selectedItems()]
        where_parts.append(f"PolStatus IN ({in_list(codes)})")

    # ReinsCo
    if ct.chk_reinsco.isChecked() and ct.list_reinsco.selectedItems():
        codes = [item.text().strip() for item in ct.list_reinsco.selectedItems()]
        where_parts.append(f"ReinsCo IN ({in_list(codes)})")

    # RepCo
    if ct.chk_repco.isChecked() and ct.list_repco.selectedItems():
        codes = [item.text().strip() for item in ct.list_repco.selectedItems()]
        where_parts.append(f"RepCo IN ({in_list(codes)})")

    # ReinsType
    if ct.chk_reinstype.isChecked() and ct.list_reinstype.selectedItems():
        codes = [item.text().strip() for item in ct.list_reinstype.selectedItems()]
        where_parts.append(f"ReinsTyp IN ({in_list(codes)})")

    # Mode
    if ct.chk_mode.isChecked() and ct.list_mode.selectedItems():
        codes = [item.text().strip() for item in ct.list_mode.selectedItems()]
        where_parts.append(f"Mode IN ({in_list(codes)})")

    # ProdCD
    if ct.chk_prodcd.isChecked() and ct.list_prodcd.selectedItems():
        codes = [item.text().strip() for item in ct.list_prodcd.selectedItems()]
        where_parts.append(f"ProdCD IN ({in_list(codes)})")

    # Company
    if ct.chk_company.isChecked() and ct.list_company.selectedItems():
        codes = [item.text().strip() for item in ct.list_company.selectedItems()]
        where_parts.append(f"Co IN ({in_list(codes)})")

    # Policynumber criteria
    polnum = ct.txt_polnum.text().strip()
    if polnum:
        crit = ct.cmb_polnum_criteria.currentIndex()
        if crit == 0:
            where_parts.append(f"Pol = '{esc(polnum)}'")
        elif crit == 1:
            where_parts.append(f"Pol LIKE '{esc(polnum)}%'")
        elif crit == 2:
            where_parts.append(f"Pol LIKE '%{esc(polnum)}%'")

    # Plancode criteria
    plancode = ct.txt_plancode.text().strip()
    if plancode:
        crit = ct.cmb_plancode_criteria.currentIndex()
        if crit == 0:
            where_parts.append(f"[Plan] = '{esc(plancode)}'")
        elif crit == 1:
            where_parts.append(f"[Plan] LIKE '{esc(plancode)}%'")
        elif crit == 2:
            where_parts.append(f"[Plan] LIKE '%{esc(plancode)}%'")

    # RGA — filter to RGA reinsurance companies
    if ct.chk_rga.isChecked():
        where_parts.append("ReinsCo IN ('RGAO', 'RG', 'RGA')")

    # Build the final query
    sql = f"SELECT * FROM {table}"
    if where_parts:
        sql += "\nWHERE " + "\n  AND ".join(where_parts)

    if max_count_text:
        try:
            n = int(max_count_text)
            sql = f"SELECT TOP {n} * FROM {table}" + sql[len(f"SELECT * FROM {table}"):]
        except ValueError:
            pass  # invalid value → no TOP clause

    return sql


def run_tai_query(sql: str) -> tuple[pd.DataFrame, float]:
    """Execute a TAI SQL query and return (dataframe, query_seconds).

    The DataFrame is filtered to TAI_DEFAULT_COLUMNS.
    """
    t0 = time.time()
    conn = pyodbc.connect("DSN=UL_Rates")
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    t_query = time.time() - t0

    df = pd.DataFrame([list(r) for r in rows], columns=columns)
    # Show only default columns (keep order, skip missing)
    visible = [c for c in TAI_DEFAULT_COLUMNS if c in df.columns]
    if visible:
        df = df[visible]

    return df, t_query


# ── Compare key columns ─────────────────────────────────────────────────

COMPARE_KEY_COLS = ["Co", "Pol", "Cov", "CessSeq"]


def build_tai_compare_sql(ct, month_end: str) -> str:
    """Build a TAI query for a single monthEnd value (no TOP limit).

    Uses all the same filter criteria from the cession tab, but forces
    monthEnd = *month_end* instead of using the date range fields.
    """
    where_parts: list[str] = [f"monthEnd = '{esc(month_end)}'"]

    # Reuse all non-date filters from build_tai_sql
    if ct.chk_inforce.isChecked():
        where_parts.append("PolStatus = 'PMP'")

    if ct.chk_status_code.isChecked() and ct.list_status_code.selectedItems():
        codes = [item.text()[:3].strip()
                 for item in ct.list_status_code.selectedItems()]
        where_parts.append(f"PolStatus IN ({in_list(codes)})")

    if ct.chk_reinsco.isChecked() and ct.list_reinsco.selectedItems():
        codes = [item.text().strip() for item in ct.list_reinsco.selectedItems()]
        where_parts.append(f"ReinsCo IN ({in_list(codes)})")

    if ct.chk_repco.isChecked() and ct.list_repco.selectedItems():
        codes = [item.text().strip() for item in ct.list_repco.selectedItems()]
        where_parts.append(f"RepCo IN ({in_list(codes)})")

    if ct.chk_reinstype.isChecked() and ct.list_reinstype.selectedItems():
        codes = [item.text().strip() for item in ct.list_reinstype.selectedItems()]
        where_parts.append(f"ReinsTyp IN ({in_list(codes)})")

    if ct.chk_mode.isChecked() and ct.list_mode.selectedItems():
        codes = [item.text().strip() for item in ct.list_mode.selectedItems()]
        where_parts.append(f"Mode IN ({in_list(codes)})")

    if ct.chk_prodcd.isChecked() and ct.list_prodcd.selectedItems():
        codes = [item.text().strip() for item in ct.list_prodcd.selectedItems()]
        where_parts.append(f"ProdCD IN ({in_list(codes)})")

    if ct.chk_company.isChecked() and ct.list_company.selectedItems():
        codes = [item.text().strip() for item in ct.list_company.selectedItems()]
        where_parts.append(f"Co IN ({in_list(codes)})")

    polnum = ct.txt_polnum.text().strip()
    if polnum:
        crit = ct.cmb_polnum_criteria.currentIndex()
        if crit == 0:
            where_parts.append(f"Pol = '{esc(polnum)}'")
        elif crit == 1:
            where_parts.append(f"Pol LIKE '{esc(polnum)}%'")
        elif crit == 2:
            where_parts.append(f"Pol LIKE '%{esc(polnum)}%'")

    plancode = ct.txt_plancode.text().strip()
    if plancode:
        crit = ct.cmb_plancode_criteria.currentIndex()
        if crit == 0:
            where_parts.append(f"[Plan] = '{esc(plancode)}'")
        elif crit == 1:
            where_parts.append(f"[Plan] LIKE '{esc(plancode)}%'")
        elif crit == 2:
            where_parts.append(f"[Plan] LIKE '%{esc(plancode)}%'")

    if ct.chk_rga.isChecked():
        where_parts.append("ReinsCo IN ('RGAO', 'RG', 'RGA')")

    table = ct.cmb_table.currentText()
    if table == "(none)":
        raise ValueError("Please select a table first.")
    sql = f"SELECT * FROM {table}"
    if where_parts:
        sql += "\nWHERE " + "\n  AND ".join(where_parts)
    return sql


def run_tai_compare(ct, eom1: str, eom2: str
                    ) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """Run two TAI queries and return rows unique to each month-end.

    Returns (df_eom1_only, df_eom2_only, total_query_seconds).
    Diff key: Co + Pol + Cov + CessSeq.
    """
    sql1 = build_tai_compare_sql(ct, eom1)
    sql2 = build_tai_compare_sql(ct, eom2)

    t0 = time.time()
    conn = pyodbc.connect("DSN=UL_Rates")

    cursor1 = conn.cursor()
    cursor1.execute(sql1)
    cols1 = [d[0] for d in cursor1.description]
    rows1 = cursor1.fetchall()

    cursor2 = conn.cursor()
    cursor2.execute(sql2)
    cols2 = [d[0] for d in cursor2.description]
    rows2 = cursor2.fetchall()

    conn.close()
    t_query = time.time() - t0

    df1 = pd.DataFrame([list(r) for r in rows1], columns=cols1)
    df2 = pd.DataFrame([list(r) for r in rows2], columns=cols2)

    # Filter to default columns
    visible1 = [c for c in TAI_DEFAULT_COLUMNS if c in df1.columns]
    visible2 = [c for c in TAI_DEFAULT_COLUMNS if c in df2.columns]
    if visible1:
        df1 = df1[visible1]
    if visible2:
        df2 = df2[visible2]

    # Build key sets — use available key columns only
    key_cols = [c for c in COMPARE_KEY_COLS if c in df1.columns and c in df2.columns]
    if not key_cols:
        # Fallback: all rows are "unique"
        return df1, df2, t_query

    keys1 = set(df1[key_cols].apply(tuple, axis=1))
    keys2 = set(df2[key_cols].apply(tuple, axis=1))

    only1_keys = keys1 - keys2
    only2_keys = keys2 - keys1

    df1_only = df1[df1[key_cols].apply(tuple, axis=1).isin(only1_keys)].reset_index(drop=True)
    df2_only = df2[df2[key_cols].apply(tuple, axis=1).isin(only2_keys)].reset_index(drop=True)

    return df1_only, df2_only, t_query


# ── TAICyberTAIFd query support ─────────────────────────────────────────

TAICYBERTAIFD_DEFAULT_COLUMNS = [
    "Co", "Pol", "Cov", "Status", "IssueDate", "PaidtoDate",
    "LastTransDate", "DBOption", "Face", "ADB", "WoP", "ValuesDate",
    "Benefit", "CashValue", "Skip2ClientID", "PricingSex", "Age",
    "Class", "LastUpdate",
]


def build_taicybertaifd_sql(ct, max_count_text: str) -> str:
    """Build a SELECT query for the TAICyberTAIFd table.

    Parameters
    ----------
    ct : TaiTransactionsTab
        The TAICyberTAIFd tab widget with all filter controls.
    max_count_text : str
        The max row count text (empty string for all rows).
    """
    table = ct.cmb_table.currentText()
    if table == "(none)":
        raise ValueError("Please select a table first.")

    where_parts: list[str] = []

    # Date range (LastUpdate column, date values)
    date_from = ct.txt_date_from.text().strip()
    date_to = ct.txt_date_to.text().strip()
    if date_from and date_to:
        where_parts.append(
            f"CAST(LastUpdate AS DATE) BETWEEN '{esc(date_from)}' AND '{esc(date_to)}'")
    elif date_from:
        where_parts.append(f"CAST(LastUpdate AS DATE) >= '{esc(date_from)}'")
    elif date_to:
        where_parts.append(f"CAST(LastUpdate AS DATE) <= '{esc(date_to)}'")

    # Status Code

    # ProdCD
    if ct.chk_prodcd.isChecked() and ct.list_prodcd.selectedItems():
        codes = [item.text().strip() for item in ct.list_prodcd.selectedItems()]
        where_parts.append(f"ProdCD IN ({in_list(codes)})")

    # Company
    if ct.chk_company.isChecked() and ct.list_company.selectedItems():
        codes = [item.text().strip() for item in ct.list_company.selectedItems()]
        where_parts.append(f"Co IN ({in_list(codes)})")

    # Policynumber criteria
    polnum = ct.txt_polnum.text().strip()
    if polnum:
        crit = ct.cmb_polnum_criteria.currentIndex()
        if crit == 0:
            where_parts.append(f"Pol = '{esc(polnum)}'")
        elif crit == 1:
            where_parts.append(f"Pol LIKE '{esc(polnum)}%'")
        elif crit == 2:
            where_parts.append(f"Pol LIKE '%{esc(polnum)}%'")

    # Plancode criteria
    plancode = ct.txt_plancode.text().strip()
    if plancode:
        crit = ct.cmb_plancode_criteria.currentIndex()
        if crit == 0:
            where_parts.append(f"[Plan] = '{esc(plancode)}'")
        elif crit == 1:
            where_parts.append(f"[Plan] LIKE '{esc(plancode)}%'")
        elif crit == 2:
            where_parts.append(f"[Plan] LIKE '%{esc(plancode)}%'")

    # Date range filters (Issue Date, Paid To Date, Last Trans Date, Values Date)
    _date_range_fields = [
        ("txt_issue_date_lo", "txt_issue_date_hi", "IssueDate"),
        ("txt_paid_to_date_lo", "txt_paid_to_date_hi", "PaidtoDate"),
        ("txt_last_trans_date_lo", "txt_last_trans_date_hi", "LastTransDate"),
        ("txt_values_date_lo", "txt_values_date_hi", "ValuesDate"),
    ]
    for lo_attr, hi_attr, col_name in _date_range_fields:
        lo_val = getattr(ct, lo_attr).text().strip()
        hi_val = getattr(ct, hi_attr).text().strip()
        if lo_val and hi_val:
            where_parts.append(
                f"{col_name} BETWEEN '{esc(lo_val)}' AND '{esc(hi_val)}'")
        elif lo_val:
            where_parts.append(f"{col_name} >= '{esc(lo_val)}'")
        elif hi_val:
            where_parts.append(f"{col_name} <= '{esc(hi_val)}'")

    # Build the final query
    sql = f"SELECT * FROM {table}"
    if where_parts:
        sql += "\nWHERE " + "\n  AND ".join(where_parts)

    if max_count_text:
        try:
            n = int(max_count_text)
            sql = f"SELECT TOP {n} * FROM {table}" + sql[len(f"SELECT * FROM {table}"):]
        except ValueError:
            pass

    return sql


def run_taicybertaifd_query(sql: str, *, all_columns: bool = False) -> tuple[pd.DataFrame, float]:
    """Execute a TAICyberTAIFd SQL query and return (dataframe, query_seconds).

    The DataFrame is filtered to TAICYBERTAIFD_DEFAULT_COLUMNS unless
    *all_columns* is True.
    """
    t0 = time.time()
    conn = pyodbc.connect("DSN=UL_Rates")
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    conn.close()
    t_query = time.time() - t0

    df = pd.DataFrame([list(r) for r in rows], columns=columns)
    if not all_columns:
        visible = [c for c in TAICYBERTAIFD_DEFAULT_COLUMNS if c in df.columns]
        if visible:
            df = df[visible]

    return df, t_query
