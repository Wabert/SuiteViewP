"""
Shared query execution helpers for the audit tool.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Callable, Optional

import pandas as pd
import pyodbc

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QPushButton

from suiteview.audit.sql_helpers import fmt_time
from suiteview.audit.ui.bottom_bar import AuditBottomBar

logger = logging.getLogger(__name__)


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


def format_query_error(exc: BaseException) -> str:
    """Return a human-readable message for a query exception."""
    msg = str(exc)
    if hasattr(exc, "args") and len(exc.args) >= 2 and isinstance(exc.args[1], str):
        msg = f"{exc.args[0]}\n\n{exc.args[1]}"
    return msg


class _QueryWorker(QThread):
    """Runs a no-argument callable on a background thread.

    The callable MUST NOT touch any Qt widgets — it should perform only the
    slow data work (DB I/O, pandas) and return a payload.  The result is
    delivered back to the GUI thread via the ``succeeded``/``failed`` signals.
    """

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(object)

    def __init__(self, work: Callable[[], object], parent=None):
        super().__init__(parent)
        self._work = work

    def run(self):  # executes on the worker thread
        try:
            result = self._work()
        except BaseException as exc:  # noqa: BLE001 — forwarded to GUI thread
            self.failed.emit(exc)
            return
        self.succeeded.emit(result)


def run_query_async(
    *,
    owner,
    work: Callable[[], object],
    on_success: Callable[[object], None],
    on_error: Optional[Callable[[BaseException], None]] = None,
    btn: Optional[QPushButton] = None,
    running_text: str = "Running...",
    restore_text: str = "Run\nAudit",
    bar: AuditBottomBar | None = None,
    on_busy: Optional[Callable[[bool], None]] = None,
) -> Optional[_QueryWorker]:
    """Run ``work()`` on a background thread, keeping the UI responsive.

    ``work`` runs off the GUI thread and must not touch Qt widgets; it returns
    a payload.  ``on_success(payload)`` and ``on_error(exc)`` run back on the
    GUI thread.  While the query is in flight the run button stays disabled, so
    the user can freely switch to other SuiteView tools but cannot launch a
    second copy of the same query.

    The worker is stored on ``owner._active_query_worker`` to keep it alive and
    to guard against re-entrancy.  Returns the worker, or ``None`` if a query is
    already running for this owner.
    """
    if getattr(owner, "_active_query_worker", None) is not None:
        return None

    if btn is not None:
        btn.setEnabled(False)
        btn.setText(running_text)
    if bar is not None:
        bar.reset_timing()
    if on_busy is not None:
        on_busy(True)

    worker = _QueryWorker(work, parent=owner)
    owner._active_query_worker = worker

    def _finish():
        worker.wait()
        if btn is not None:
            btn.setEnabled(True)
            btn.setText(restore_text)
        if on_busy is not None:
            on_busy(False)
        owner._active_query_worker = None
        worker.deleteLater()

    def _on_ok(payload):
        try:
            on_success(payload)
        except Exception:
            logger.exception("Query success handler failed")
        finally:
            _finish()

    def _on_err(exc):
        try:
            if on_error is not None:
                on_error(exc)
            else:
                logger.error("Query failed: %s", format_query_error(exc))
        finally:
            _finish()

    worker.succeeded.connect(_on_ok)
    worker.failed.connect(_on_err)
    worker.start()
    return worker
