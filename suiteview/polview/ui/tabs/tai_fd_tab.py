"""
TAICyberTAIFd tab - queries dbo.TAICyberTAIFd in the UL_Rates database.

Opened from the "TAICyberTAIFd" button on the Policy Support tab's left nav panel.
Provides a LastUpdate date range (defaulting the start to one month ago), a
TAICyberTAIFd button that runs the query against the "UL_Rates" SQL Server ODBC
connection, and a filterable/searchable grid.

Matching is on policy number only (Pol), not company code.  Every column is
displayed with LastUpdate moved to the front and rows ordered LastUpdate DESC.

If the user has no "UL_Rates" DSN configured (or the database refuses the
connection) the canvas states access is not available; if the policy has no
records, a single placeholder row says so.
"""

from datetime import date, datetime
from typing import Optional, TYPE_CHECKING

import pandas as pd
from dateutil.relativedelta import relativedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QApplication, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor

from suiteview.ui.widgets.filter_table_view import FilterTableView
from ..styles import (
    WHITE, GREEN_DARK, GREEN_PRIMARY, GREEN_SUBTLE, GRAY_DARK, GOLD_LIGHT,
)

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


UL_RATES_DSN = "UL_Rates"
TABLE_NAME = "dbo.TAICyberTAIFd"
POLICY_COLUMN = "Pol"
DATE_COLUMN = "LastUpdate"

_NO_ACCESS_MESSAGE = (
    "You do not have access to this database (UL_Rates) set up on your machine."
)
_NO_RECORDS_MESSAGE = "No records for this policy number found in TAICyberTAIFd."


def _ul_rates_available() -> bool:
    """True when a 'UL_Rates' ODBC DSN is configured on this machine."""
    try:
        import pyodbc
        return UL_RATES_DSN in set(pyodbc.dataSources())
    except Exception:
        return False


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


class TaiFdTab(QWidget):
    """dbo.TAICyberTAIFd viewer for the loaded policy."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional['PolicyInformation'] = None
        self._has_access = _ul_rates_available()
        self._setup_ui()
        self._apply_access_state()

    # -- UI ----------------------------------------------------------------

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {WHITE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Controls row ──────────────────────────────────────────────────
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self._policy_label = QLabel("No policy loaded")
        self._policy_label.setStyleSheet(_LBL_STYLE)
        controls.addWidget(self._policy_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {GREEN_PRIMARY};")
        controls.addWidget(sep)

        controls.addWidget(self._mk_label("LastUpdate"))

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

        controls.addSpacing(6)
        self.query_btn = QPushButton("TAICyberTAIFd")
        self.query_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.query_btn.setStyleSheet(_BTN_STYLE)
        self.query_btn.clicked.connect(self._on_query)
        controls.addWidget(self.query_btn)

        controls.addStretch(1)
        layout.addLayout(controls)

        # ── No-access notice (red) ────────────────────────────────────────
        self._no_access_label = QLabel(_NO_ACCESS_MESSAGE)
        self._no_access_label.setStyleSheet(
            "color: #C0392B; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        self._no_access_label.setVisible(False)
        layout.addWidget(self._no_access_label)

        # ── Results grid ──────────────────────────────────────────────────
        self.grid = FilterTableView(self)
        self.grid.apply_ledger_style(
            header_bg=GREEN_SUBTLE,
            header_fg=GREEN_DARK,
            border=GREEN_PRIMARY,
            selection_bg=GOLD_LIGHT,
            selection_fg=GREEN_DARK,
        )
        layout.addWidget(self.grid, 1)

        # ── Status line ───────────────────────────────────────────────────
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"font-size: 10px; color: {GRAY_DARK}; background: transparent; border: none;"
        )
        layout.addWidget(self._status_label)

        self._set_default_dates()

    def _mk_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(_LBL_STYLE)
        return lbl

    # -- Public API --------------------------------------------------------

    def load_policy(self, policy: Optional['PolicyInformation']):
        """Bind a policy and reset the default LastUpdate range."""
        self._policy = policy
        self._has_access = _ul_rates_available()
        self._apply_access_state()

        if policy is not None and getattr(policy, "exists", False):
            company = str(getattr(policy, "company_code", "") or "").strip()
            number = str(getattr(policy, "policy_number", "") or "").strip()
            self._policy_label.setText(f"{company}  /  {number}")
        else:
            self._policy_label.setText("No policy loaded")
        self._set_default_dates()

    def reset(self):
        """Clear all data for a clean slate (used when a new policy loads)."""
        self._policy = None
        self._has_access = _ul_rates_available()
        self._apply_access_state()
        self._policy_label.setText("No policy loaded")
        self.grid.set_dataframe(pd.DataFrame(), limit_rows=False)
        self._set_default_dates()
        self._set_status("")

    def export_state(self) -> dict:
        """Snapshot inputs and results for restoration on policy switch."""
        df = None
        if self.grid.model is not None:
            df = self.grid.model.get_original_data().copy()
        return {
            "from": self.date_from.text(),
            "to": self.date_to.text(),
            "df": df,
            "status": self._status_label.text(),
            "no_access": self._no_access_label.isVisible(),
        }

    def restore_state(self, policy: Optional['PolicyInformation'], state: dict):
        """Re-bind a policy and restore a previously captured snapshot."""
        self._policy = policy
        self._has_access = _ul_rates_available()
        self._apply_access_state()
        if policy is not None and getattr(policy, "exists", False):
            company = str(getattr(policy, "company_code", "") or "").strip()
            number = str(getattr(policy, "policy_number", "") or "").strip()
            self._policy_label.setText(f"{company}  /  {number}")
        else:
            self._policy_label.setText("No policy loaded")
        self.date_from.setText(state.get("from", ""))
        self.date_to.setText(state.get("to", ""))
        if state.get("no_access"):
            self._show_no_access()
        else:
            self._show_grid()
            df = state.get("df")
            if df is not None:
                self.grid.set_dataframe(df, limit_rows=False)
                self.grid.autofit_columns_to_data()
        self._set_status(state.get("status", ""))

    # -- Internal ----------------------------------------------------------

    def _set_default_dates(self):
        """Default the start to one month ago; leave the end blank (no upper limit)."""
        start = date.today() - relativedelta(months=1)
        self.date_from.setText(start.strftime("%m/%d/%Y"))
        self.date_to.clear()

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
        """Enable/disable the query controls based on UL_Rates availability."""
        self.query_btn.setEnabled(self._has_access)
        self.date_from.setEnabled(self._has_access)
        self.date_to.setEnabled(self._has_access)
        self._no_access_label.setVisible(not self._has_access)
        self.grid.setVisible(self._has_access)

    def _show_no_access(self):
        self._no_access_label.setVisible(True)
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
        if not self._policy or not getattr(self._policy, "exists", False):
            self._set_status("Load a policy first, then run the query.", error=True)
            return

        policy_no = str(getattr(self._policy, "policy_number", "") or "").strip()

        from_text = self.date_from.text().strip()
        date_from = self._parse_date(from_text)
        if from_text and date_from is None:
            self._set_status("Start date is not a valid date (use MM/DD/YYYY).", error=True)
            return

        to_text = self.date_to.text().strip()
        date_to = self._parse_date(to_text)
        if to_text and date_to is None:
            self._set_status("End date is not a valid date (use MM/DD/YYYY).", error=True)
            return

        if date_from and date_to and date_from > date_to:
            self._set_status("Start date must be on or before the end date.", error=True)
            return

        # Match on policy number only (no company code).
        where = [f"[{POLICY_COLUMN}] = ?"]
        params = [policy_no]
        if date_from is not None:
            where.append(f"[{DATE_COLUMN}] >= ?")
            params.append(date_from.isoformat())
        if date_to is not None:
            # Inclusive of the whole end day.
            where.append(f"[{DATE_COLUMN}] < ?")
            params.append((date_to + relativedelta(days=1)).isoformat())

        sql = (
            f"SELECT * FROM {TABLE_NAME} "
            f"WHERE {' AND '.join(where)} "
            f"ORDER BY [{DATE_COLUMN}] DESC"
        )

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self._set_status(f"Querying {TABLE_NAME} …")
        try:
            df = self._run_query(sql, tuple(params))
        except Exception as exc:  # noqa: BLE001 - surface any ODBC/query error
            QApplication.restoreOverrideCursor()
            if _is_access_error(exc):
                self._show_no_access()
                self._set_status("")
            else:
                self._show_grid()
                self._set_status(f"Query failed: {exc}", error=True)
            return

        self._show_grid()
        if df.empty:
            placeholder = pd.DataFrame({"Result": [_NO_RECORDS_MESSAGE]})
            self.grid.set_dataframe(placeholder, limit_rows=False)
            self.grid.autofit_columns_to_data()
            QApplication.restoreOverrideCursor()
            self._set_status("0 record(s) found.")
            return

        self.grid.set_dataframe(df, limit_rows=False)
        self.grid.autofit_columns_to_data()
        QApplication.restoreOverrideCursor()
        self._set_status(f"{len(df):,} record(s) found.")

    def _run_query(self, sql: str, params: tuple) -> pd.DataFrame:
        """Execute the query on a one-shot 'UL_Rates' connection.

        Returns every column with LastUpdate moved to the front.
        """
        import pyodbc

        conn = pyodbc.connect(f"DSN={UL_RATES_DSN}", autocommit=True)
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

        df = pd.DataFrame(rows, columns=columns)
        # Move the date column to the front.
        if DATE_COLUMN in df.columns:
            ordered = [DATE_COLUMN] + [c for c in df.columns if c != DATE_COLUMN]
            df = df[ordered]
        return df


def _is_access_error(exc: Exception) -> bool:
    """Heuristic: login/permission/connection failures mean 'no access'."""
    text = str(exc).lower()
    needles = ("login failed", "permission", "access", "28000", "untrusted", "cannot open database")
    return any(n in text for n in needles)
