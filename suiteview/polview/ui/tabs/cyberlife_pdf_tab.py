"""
CYBERLIFE_PDF tab - queries dbo.CYBERLIFE_PDF in the UL_Rates database.

Opened from the "CYBERLIFE_PDF" button on the Policy Support tab's left nav panel.
Looks up every plancode on the policy (the base plancode plus any rider
plancodes - benefits are excluded) and returns the UserID / Plancode /
FieldName / FieldValue rows for those plancodes.

The result is pivoted: FieldName runs down the first column and there is one
column per plancode, with FieldValue as the cell values.  A "UserID" row at the
top of the grid shows the UserID behind each plancode column.

There is no date filter for this table.  A search bar sits at the top of the
grid (provided by FilterTableView).

If the user has no "UL_Rates" DSN configured (or the database refuses the
connection) the canvas states access is not available; if none of the policy's
plancodes return rows, a single placeholder row says so.
"""

from typing import Optional, TYPE_CHECKING

import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
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
TABLE_NAME = "dbo.CYBERLIFE_PDF"
PLANCODE_COLUMN = "Plancode"
FIELD_NAME_COLUMN = "FieldName"

_NO_ACCESS_MESSAGE = (
    "You do not have access to this database (UL_Rates) set up on your machine."
)
_NO_RECORDS_MESSAGE = "No CYBERLIFE_PDF records found for this policy's plancodes."


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

_LBL_STYLE = (
    f"font-size: 11px; font-weight: bold; color: {GREEN_DARK}; "
    f"background: transparent; border: none;"
)


class CyberlifePdfTab(QWidget):
    """dbo.CYBERLIFE_PDF viewer for the loaded policy's plancodes (pivoted)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional['PolicyInformation'] = None
        self._plancodes: list[str] = []
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

        self._plancodes_label = QLabel("Plancodes: —")
        self._plancodes_label.setStyleSheet(
            f"font-size: 11px; color: {GRAY_DARK}; background: transparent; border: none;"
        )
        controls.addWidget(self._plancodes_label)

        controls.addSpacing(6)
        self.query_btn = QPushButton("CYBERLIFE_PDF")
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

        # ── Results grid (pivoted) ────────────────────────────────────────
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

    # -- Public API --------------------------------------------------------

    def load_policy(self, policy: Optional['PolicyInformation']):
        """Bind a policy and capture its plancodes (base + riders)."""
        self._policy = policy
        self._has_access = _ul_rates_available()
        self._apply_access_state()
        self._plancodes = self._collect_plancodes(policy)

        if policy is not None and getattr(policy, "exists", False):
            company = str(getattr(policy, "company_code", "") or "").strip()
            number = str(getattr(policy, "policy_number", "") or "").strip()
            self._policy_label.setText(f"{company}  /  {number}")
        else:
            self._policy_label.setText("No policy loaded")
        self._update_plancodes_label()

    def reset(self):
        """Clear all data for a clean slate (used when a new policy loads)."""
        self._policy = None
        self._plancodes = []
        self._has_access = _ul_rates_available()
        self._apply_access_state()
        self._policy_label.setText("No policy loaded")
        self._update_plancodes_label()
        self.grid.set_dataframe(pd.DataFrame(), limit_rows=False)
        self._set_status("")

    def export_state(self) -> dict:
        """Snapshot results for restoration on policy switch."""
        df = None
        if self.grid.model is not None:
            df = self.grid.model.get_original_data().copy()
        return {
            "plancodes": list(self._plancodes),
            "df": df,
            "status": self._status_label.text(),
            "no_access": self._no_access_label.isVisible(),
        }

    def restore_state(self, policy: Optional['PolicyInformation'], state: dict):
        """Re-bind a policy and restore a previously captured snapshot."""
        self._policy = policy
        self._has_access = _ul_rates_available()
        self._apply_access_state()
        self._plancodes = list(state.get("plancodes") or self._collect_plancodes(policy))
        if policy is not None and getattr(policy, "exists", False):
            company = str(getattr(policy, "company_code", "") or "").strip()
            number = str(getattr(policy, "policy_number", "") or "").strip()
            self._policy_label.setText(f"{company}  /  {number}")
        else:
            self._policy_label.setText("No policy loaded")
        self._update_plancodes_label()
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

    @staticmethod
    def _collect_plancodes(policy: Optional['PolicyInformation']) -> list[str]:
        """All plancodes on the policy (base + riders, no benefits), de-duped.

        Coverages from get_coverages() are the base coverage plus rider
        coverages; benefits live in a separate collection and are excluded.
        Order is preserved (base first, then riders as they appear).
        """
        if policy is None or not getattr(policy, "exists", False):
            return []
        ordered: list[str] = []
        seen: set[str] = set()
        try:
            coverages = policy.get_coverages()
        except Exception:
            coverages = []
        for cov in coverages:
            pc = str(getattr(cov, "plancode", "") or "").strip().upper()
            if pc and pc not in seen:
                seen.add(pc)
                ordered.append(pc)
        return ordered

    def _update_plancodes_label(self):
        if self._plancodes:
            self._plancodes_label.setText("Plancodes: " + ", ".join(self._plancodes))
        else:
            self._plancodes_label.setText("Plancodes: —")

    def _apply_access_state(self):
        """Enable/disable the query controls based on UL_Rates availability."""
        self.query_btn.setEnabled(self._has_access)
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

        # Refresh plancodes in case the policy changed without a reload.
        self._plancodes = self._collect_plancodes(self._policy)
        self._update_plancodes_label()
        if not self._plancodes:
            self._set_status("This policy has no plancodes to look up.", error=True)
            return

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self._set_status(f"Querying {TABLE_NAME} …")
        try:
            df = self._run_query(self._plancodes)
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
        plan_cols = [c for c in df.columns if c != FIELD_NAME_COLUMN]
        # First row is the UserID row, so field rows = len(df) - 1.
        field_rows = max(len(df) - 1, 0)
        self._set_status(
            f"{len(plan_cols)} plancode(s), {field_rows} field(s)."
        )

    def _run_query(self, plancodes: list[str]) -> pd.DataFrame:
        """Fetch CYBERLIFE_PDF rows for the plancodes and pivot them.

        Returns a DataFrame whose first column is FieldName, followed by one
        column per plancode (FieldValue as the cell values).  A leading
        "UserID" row reports the UserID behind each plancode column.
        Empty DataFrame when no rows match.
        """
        import pyodbc

        placeholders = ", ".join("?" for _ in plancodes)
        sql = (
            f"SELECT UserID, Plancode, FieldName, FieldValue "
            f"FROM {TABLE_NAME} "
            f"WHERE LTRIM(RTRIM(Plancode)) IN ({placeholders})"
        )

        conn = pyodbc.connect(f"DSN={UL_RATES_DSN}", autocommit=True)
        try:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, plancodes)
                rows = [tuple(r) for r in cursor.fetchall()]
            finally:
                cursor.close()
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if not rows:
            return pd.DataFrame()

        raw = pd.DataFrame(rows, columns=["UserID", "Plancode", "FieldName", "FieldValue"])
        # CyberLife stores these as fixed-width, space-padded strings.
        for col in raw.columns:
            raw[col] = raw[col].map(lambda v: str(v).strip() if v is not None else "")
        raw["Plancode"] = raw["Plancode"].str.upper()

        # Order plancode columns the way they appear on the policy; only keep
        # plancodes that actually returned rows.
        present = set(raw["Plancode"])
        ordered_plancodes = [pc for pc in plancodes if pc in present]
        # Include any unexpected plancodes returned (defensive) at the end.
        for pc in raw["Plancode"].unique():
            if pc not in ordered_plancodes:
                ordered_plancodes.append(pc)

        # Pivot: FieldName down the rows, one column per plancode.
        pivot = raw.pivot_table(
            index="FieldName",
            columns="Plancode",
            values="FieldValue",
            aggfunc="first",
        )
        pivot = pivot.reindex(columns=ordered_plancodes)
        pivot = pivot.sort_index()
        pivot = pivot.reset_index()  # FieldName becomes the first column

        # Build the leading UserID row (one UserID per plancode column).
        userid_row = {FIELD_NAME_COLUMN: "UserID"}
        for pc in ordered_plancodes:
            uids = sorted({u for u in raw.loc[raw["Plancode"] == pc, "UserID"] if u})
            userid_row[pc] = ", ".join(uids)

        result = pd.concat(
            [pd.DataFrame([userid_row]), pivot],
            ignore_index=True,
        )
        result = result.fillna("")
        # Guarantee column order: FieldName first, then plancodes.
        result = result[[FIELD_NAME_COLUMN] + ordered_plancodes]
        return result


def _is_access_error(exc: Exception) -> bool:
    """Heuristic: login/permission/connection failures mean 'no access'."""
    text = str(exc).lower()
    needles = ("login failed", "permission", "access", "28000", "untrusted", "cannot open database")
    return any(n in text for n in needles)
