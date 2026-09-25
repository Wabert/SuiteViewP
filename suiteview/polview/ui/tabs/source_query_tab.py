"""Shared PolView source-query tab behavior."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, TYPE_CHECKING

import pandas as pd
from dateutil.relativedelta import relativedelta

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from suiteview.core.odbc_utils import connect_dsn
from suiteview.ui.widgets.filter_table_view import FilterTableView
from ..styles import (
    GOLD_LIGHT,
    GRAY_DARK,
    GREEN_DARK,
    GREEN_PRIMARY,
    GREEN_SUBTLE,
    WHITE,
)

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


_BTN_STYLE = f"""
    QPushButton {{
        background: {GREEN_PRIMARY};
        color: {WHITE};
        border: 1px solid {GREEN_DARK};
        border-radius: 4px;
        padding: 3px 14px;
        font-size: 11px;
        font-weight: bold;
        min-height: 20px;
    }}
    QPushButton:hover {{ background: {GREEN_DARK}; }}
    QPushButton:disabled {{ background: #BDBDBD; color: #F0F0F0; border-color: #9E9E9E; }}
"""

_DATE_STYLE = f"""
    QLineEdit {{
        background: {WHITE};
        color: {GREEN_DARK};
        border: 1px solid {GREEN_PRIMARY};
        border-radius: 3px;
        padding: 1px 6px;
        font-size: 11px;
        min-height: 18px;
    }}
    QLineEdit:disabled {{ background: #F0F0F0; color: #9E9E9E; }}
"""

_LBL_STYLE = (
    f"font-size: 11px; font-weight: bold; color: {GREEN_DARK}; "
    f"background: transparent; border: none;"
)


def is_dsn_available(dsn: str) -> bool:
    """True when an ODBC DSN is configured on this machine."""
    try:
        import pyodbc

        return dsn in set(pyodbc.dataSources())
    except Exception:
        return False


def is_access_error(exc: Exception) -> bool:
    """Heuristic: login/permission/connection failures mean 'no access'."""
    text = str(exc).lower()
    needles = (
        "login failed",
        "permission",
        "access",
        "28000",
        "untrusted",
        "cannot open database",
    )
    return any(n in text for n in needles)


class SourceQueryTab(QWidget):
    """Base class for PolView source-backed query tabs."""

    dsn = ""
    date_label = ""
    query_button_text = "Query"
    no_access_message = ""
    no_records_message: str | None = None
    has_date_controls = True
    hide_grid_on_no_access = True
    include_no_access_state = True
    auto_query_on_load = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional["PolicyInformation"] = None
        self._has_access = self._dsn_available()
        self._setup_ui()
        self._apply_access_state()

    # -- UI ----------------------------------------------------------------

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {WHITE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._policy_label = QLabel("No policy loaded")
        self._policy_label.setStyleSheet(_LBL_STYLE)
        controls.addWidget(self._policy_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {GREEN_PRIMARY};")
        controls.addWidget(sep)

        self._add_query_controls(controls)

        controls.addSpacing(6)
        self.query_btn = QPushButton(self.query_button_text)
        self.query_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.query_btn.setStyleSheet(_BTN_STYLE)
        self.query_btn.clicked.connect(self._on_query)
        controls.addWidget(self.query_btn)

        controls.addStretch(1)
        layout.addLayout(controls)

        self._no_access_label = QLabel(self.no_access_message)
        self._no_access_label.setStyleSheet(
            "color: #C0392B; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._no_access_label.setVisible(False)
        layout.addWidget(self._no_access_label)

        self.grid = FilterTableView(self)
        self.grid.apply_ledger_style(
            header_bg=GREEN_SUBTLE,
            header_fg=GREEN_DARK,
            border=GREEN_PRIMARY,
            selection_bg=GOLD_LIGHT,
            selection_fg=GREEN_DARK,
        )
        self._configure_grid()
        layout.addWidget(self.grid, 1)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"font-size: 10px; color: {GRAY_DARK}; background: transparent; border: none;"
        )
        layout.addWidget(self._status_label)

        if self.has_date_controls:
            self._set_default_dates_for_policy(None)

    def _add_query_controls(self, controls: QHBoxLayout) -> None:
        if not self.has_date_controls:
            return
        controls.addWidget(self._mk_label(self.date_label))

        self.date_from = QLineEdit()
        self.date_from.setFixedWidth(96)
        self.date_from.setPlaceholderText("MM/DD/YYYY")
        self.date_from.setStyleSheet(_DATE_STYLE)
        self.date_from.returnPressed.connect(self._on_query)
        controls.addWidget(self.date_from)

        controls.addWidget(self._mk_label("to"))

        self.date_to = QLineEdit()
        self.date_to.setFixedWidth(96)
        self.date_to.setPlaceholderText("(no upper limit)")
        self.date_to.setStyleSheet(_DATE_STYLE)
        self.date_to.returnPressed.connect(self._on_query)
        controls.addWidget(self.date_to)

    def _mk_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(_LBL_STYLE)
        return lbl

    def _configure_grid(self) -> None:
        """Subclasses may apply source-specific grid options."""

    # -- Public API --------------------------------------------------------

    def load_policy(self, policy: Optional["PolicyInformation"]):
        """Bind a policy and reset source-specific inputs."""
        self._policy = policy
        self._has_access = self._dsn_available()
        self._apply_access_state()
        self._set_policy_label(policy)
        if self.has_date_controls:
            self._set_default_dates_for_policy(policy)
        self._after_policy_loaded(policy)
        if self.auto_query_on_load and policy is not None and getattr(policy, "exists", False):
            self._on_query()

    def reset(self):
        """Clear all data for a clean slate."""
        self._policy = None
        self._has_access = self._dsn_available()
        self._apply_access_state()
        self._policy_label.setText("No policy loaded")
        self._reset_extra_state()
        self.grid.set_dataframe(self._empty_dataframe(), limit_rows=False)
        if self.has_date_controls:
            self._set_default_dates_for_policy(None)
        self._set_status("")

    def export_state(self) -> dict:
        """Snapshot inputs and results for restoration on policy switch."""
        df = None
        if self.grid.model is not None:
            df = self.grid.model.get_original_data().copy()
        state = {
            "df": df,
            "status": self._status_label.text(),
        }
        if self.has_date_controls:
            state["from"] = self.date_from.text()
            state["to"] = self.date_to.text()
        if self.include_no_access_state:
            state["no_access"] = not self._no_access_label.isHidden()
        state.update(self._export_extra_state())
        return state

    def restore_state(self, policy: Optional["PolicyInformation"], state: dict):
        """Re-bind a policy and restore a previously captured snapshot."""
        self._policy = policy
        self._has_access = self._dsn_available()
        self._apply_access_state()
        self._restore_extra_state(policy, state)
        self._set_policy_label(policy)
        if self.has_date_controls:
            self.date_from.setText(state.get("from", ""))
            self.date_to.setText(state.get("to", ""))
        if self.include_no_access_state and state.get("no_access"):
            self._show_no_access()
        else:
            if self.include_no_access_state or self._has_access:
                self._show_grid()
            df = state.get("df")
            if df is not None:
                self.grid.set_dataframe(df, limit_rows=False)
                self.grid.autofit_columns_to_data()
        self._set_status(state.get("status", ""))

    # -- Hooks -------------------------------------------------------------

    def _default_start_date(self, policy: Optional["PolicyInformation"]) -> date:
        return date.today() - relativedelta(months=1)

    def _set_default_dates_for_policy(
        self, policy: Optional["PolicyInformation"]
    ) -> None:
        start = self._default_start_date(policy)
        self.date_from.setText(start.strftime("%m/%d/%Y"))
        self.date_to.clear()

    def _after_policy_loaded(self, policy: Optional["PolicyInformation"]) -> None:
        pass

    def _reset_extra_state(self) -> None:
        pass

    def _export_extra_state(self) -> dict:
        return {}

    def _restore_extra_state(
        self, policy: Optional["PolicyInformation"], state: dict
    ) -> None:
        pass

    def _empty_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame()

    def _prepare_query_request(self):
        if not self._policy or not getattr(self._policy, "exists", False):
            self._set_status("Load a policy first, then run the query.", error=True)
            return None
        if not self.has_date_controls:
            return self._build_query_request(self._policy, None, None)

        from_text = self.date_from.text().strip()
        date_from = self._parse_date(from_text)
        if from_text and date_from is None:
            self._set_status("Start date is not a valid date (use MM/DD/YYYY).", error=True)
            return None

        to_text = self.date_to.text().strip()
        date_to = self._parse_date(to_text)
        if to_text and date_to is None:
            self._set_status("End date is not a valid date (use MM/DD/YYYY).", error=True)
            return None

        if date_from and date_to and date_from > date_to:
            self._set_status("Start date must be on or before the end date.", error=True)
            return None

        return self._build_query_request(self._policy, date_from, date_to)

    def _build_query_request(
        self,
        policy: "PolicyInformation",
        date_from: Optional[date],
        date_to: Optional[date],
    ):
        raise NotImplementedError

    def _query_status_text(self, request) -> str:
        return "Querying …"

    def _run_query_for_request(self, request) -> pd.DataFrame:
        sql, params = request
        columns, rows = self._fetch_rows(sql, params)
        return self._dataframe_from_rows(columns, rows)

    def _fetch_rows(self, sql: str, params: tuple) -> tuple[list[str], list[tuple]]:
        conn = connect_dsn(self.dsn, autocommit=True, timeout=None, readonly=False)
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params)
                columns = [d[0] for d in cursor.description] if cursor.description else []
                rows = [tuple(r) for r in cursor.fetchall()]
            finally:
                cursor.close()
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return columns, rows

    def _dataframe_from_rows(self, columns: list[str], rows: list[tuple]) -> pd.DataFrame:
        return pd.DataFrame(rows, columns=columns)

    def _empty_query_status(self) -> str:
        return "0 record(s) found."

    def _success_status(self, df: pd.DataFrame) -> str:
        return f"{len(df):,} record(s) found."

    def _treat_exception_as_no_access(self, exc: Exception) -> bool:
        return is_access_error(exc)

    # -- Internal ----------------------------------------------------------

    def _dsn_available(self) -> bool:
        return is_dsn_available(self.dsn)

    def _set_policy_label(self, policy: Optional["PolicyInformation"]) -> None:
        if policy is not None and getattr(policy, "exists", False):
            company = str(getattr(policy, "company_code", "") or "").strip()
            number = str(getattr(policy, "policy_number", "") or "").strip()
            self._policy_label.setText(f"{company}  /  {number}")
        else:
            self._policy_label.setText("No policy loaded")

    @staticmethod
    def _parse_date(text: str) -> Optional[date]:
        """Parse a typed date in a few common formats; None if blank/invalid."""
        text = (text or "").strip()
        if not text:
            return None
        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _apply_access_state(self):
        self.query_btn.setEnabled(self._has_access)
        if self.has_date_controls:
            self.date_from.setEnabled(self._has_access)
            self.date_to.setEnabled(self._has_access)
        self._no_access_label.setVisible(not self._has_access)
        if self.hide_grid_on_no_access:
            self.grid.setVisible(self._has_access)

    def _show_no_access(self):
        self._no_access_label.setVisible(True)
        if self.hide_grid_on_no_access:
            self.grid.setVisible(False)

    def _show_grid(self):
        self._no_access_label.setVisible(False)
        self.grid.setVisible(True)

    def _set_status(self, text: str, error: bool = False):
        color = "#C0392B" if error else GRAY_DARK
        weight = "bold" if error else "normal"
        self._status_label.setStyleSheet(
            f"font-size: 10px; color: {color}; font-weight: {weight}; "
            f"background: transparent; border: none;"
        )
        self._status_label.setText(text)
        QApplication.processEvents()

    def _on_query(self):
        if not self._has_access:
            return
        request = self._prepare_query_request()
        if request is None:
            return

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self._set_status(self._query_status_text(request))
        try:
            df = self._run_query_for_request(request)
        except Exception as exc:  # noqa: BLE001 - surface any ODBC/query error
            QApplication.restoreOverrideCursor()
            if self._treat_exception_as_no_access(exc):
                self._show_no_access()
                self._set_status("")
            else:
                self._show_grid()
                self._set_status(f"Query failed: {exc}", error=True)
            return

        self._show_grid()
        if df.empty and self.no_records_message:
            placeholder = pd.DataFrame({"Result": [self.no_records_message]})
            self.grid.set_dataframe(placeholder, limit_rows=False)
            self.grid.autofit_columns_to_data()
            QApplication.restoreOverrideCursor()
            self._set_status(self._empty_query_status())
            return

        self.grid.set_dataframe(df, limit_rows=False)
        self.grid.autofit_columns_to_data()
        QApplication.restoreOverrideCursor()
        self._set_status(self._success_status(df))
