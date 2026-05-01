"""
Shared query execution helpers for the audit tool.
"""
from __future__ import annotations

import time
from contextlib import contextmanager

import pandas as pd
import pyodbc

from PyQt6.QtWidgets import QApplication, QPushButton

from suiteview.audit.sql_helpers import fmt_time
from suiteview.audit.ui.bottom_bar import AuditBottomBar


def execute_odbc_query(dsn: str, sql: str) -> tuple[list[str], list]:
    """Execute SQL via ODBC and return (columns, rows)."""
    conn = pyodbc.connect(f"DSN={dsn}", autocommit=True)
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    finally:
        conn.close()
    return columns, rows


# Mapping from pyodbc type codes to readable SQL type names
_TYPE_CODE_MAP = {
    str: "VARCHAR",
    int: "INTEGER",
    float: "DOUBLE",
    bool: "BOOLEAN",
}


def execute_odbc_query_with_types(dsn: str, sql: str) -> tuple[list[str], list, dict[str, str]]:
    """Execute SQL via ODBC and return (columns, rows, column_types).

    column_types maps column name → SQL type string (e.g. 'VARCHAR(50)', 'INTEGER').
    """
    conn = pyodbc.connect(f"DSN={dsn}", autocommit=True)
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description]
        col_types: dict[str, str] = {}
        for desc in cursor.description:
            name = desc[0]
            type_code = desc[1]       # Python type object
            display_size = desc[2]    # display size
            internal_size = desc[3]   # internal size
            precision = desc[4]       # precision
            scale = desc[5]           # scale

            base = _TYPE_CODE_MAP.get(type_code, type_code.__name__ if hasattr(type_code, '__name__') else str(type_code))

            if type_code is str and internal_size:
                col_types[name] = f"VARCHAR({internal_size})"
            elif base in ("DOUBLE", "float") and precision:
                if scale:
                    col_types[name] = f"DECIMAL({precision},{scale})"
                else:
                    col_types[name] = f"DECIMAL({precision})"
            else:
                col_types[name] = base

        rows = cursor.fetchall()
    finally:
        conn.close()
    return columns, rows, col_types


def execute_to_dataframe(dsn: str, sql: str) -> pd.DataFrame:
    """Execute SQL via ODBC and return a DataFrame."""
    columns, rows = execute_odbc_query(dsn, sql)
    return pd.DataFrame([list(r) for r in rows], columns=columns)


@contextmanager
def run_button_context(
    btn: QPushButton,
    running_text: str = "Running...",
    restore_text: str = "Run\nAudit",
    bar: AuditBottomBar | None = None,
):
    """Context manager that disables a run button during query execution.

    Usage::

        with run_button_context(self.bar.btn_run, bar=self.bar):
            # execute query ...
    """
    btn.setEnabled(False)
    btn.setText(running_text)
    if bar is not None:
        bar.reset_timing()
    QApplication.processEvents()
    try:
        yield
    finally:
        btn.setEnabled(True)
        btn.setText(restore_text)


def timed_query(
    dsn: str,
    sql: str,
    bar: AuditBottomBar,
) -> pd.DataFrame:
    """Execute a query, update timing labels on bar, return DataFrame."""
    t0 = time.time()
    columns, rows = execute_odbc_query(dsn, sql)
    t_query = time.time() - t0

    t1 = time.time()
    df = pd.DataFrame([list(r) for r in rows], columns=columns)
    t_print = time.time() - t1
    t_total = time.time() - t0

    bar.lbl_query_time.setText(f"Query time:  {fmt_time(t_query)}")
    bar.lbl_print_time.setText(f"Print time:  {fmt_time(t_print)}")
    bar.lbl_total_time.setText(f"Total time:  {fmt_time(t_total)}")
    bar.lbl_result_count.setText(f"Result count:   {len(df)}")

    return df
