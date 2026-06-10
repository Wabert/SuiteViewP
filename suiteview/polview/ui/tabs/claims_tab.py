"""
Claims tab - queries the CLAIMSFILE flat file for the loaded policy.

Opened from the "CLAIMSFILE" button on the Policy Support tab's left nav panel.
Reads a semicolon-delimited flat file on the TAI reinsurance share and shows every
claim record whose ``Policy_Number`` matches the loaded policy.

If the user cannot read the file, the canvas states access is not available.  If
the file is readable but holds no matching records, a single placeholder row is
shown instead.
"""

from typing import Optional, TYPE_CHECKING

import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor

from suiteview.ui.widgets.filter_table_view import FilterTableView
from ..styles import (
    WHITE, GREEN_DARK, GREEN_PRIMARY, GREEN_SUBTLE, GRAY_DARK, GOLD_LIGHT,
)

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


CLAIMS_FILE_PATH = r"\\sranico7\Actuarial\Reinsurance\TAI\PRDOUT\TAJR001P\CLAIMSDATA.TXT"

# Field names in positional order, as defined by the flat-file layout.
FIELD_NAMES = [
    "Policy_number0",
    "Claim_number",
    "Date_of_death",
    "Cause_of_death",
    "Date_of_notification",
    "Settlement_date",
    "Policy_Number",
    "Company_code",
    "Insured_name",
    "Date_of_birth",
    "Who_died_code",
]

_MATCH_FIELD = "Policy_Number"

_NO_ACCESS_MESSAGE = "Access not available to this file."
_NO_RECORDS_MESSAGE = "No records for this policy number found in the claim file."


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

_PATH_STYLE = (
    f"font-size: 11px; color: {GRAY_DARK}; background: transparent; border: none;"
)


class ClaimsTab(QWidget):
    """CLAIMSFILE viewer for the loaded policy."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional['PolicyInformation'] = None
        self._setup_ui()

    # -- UI ----------------------------------------------------------------

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {WHITE};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── File location row ─────────────────────────────────────────────
        file_row = QHBoxLayout()
        file_row.setSpacing(6)

        loc_label = QLabel("File Location:")
        loc_label.setStyleSheet(_LBL_STYLE)
        file_row.addWidget(loc_label)

        path_value = QLabel(CLAIMS_FILE_PATH)
        path_value.setStyleSheet(_PATH_STYLE)
        path_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        file_row.addWidget(path_value)

        file_row.addStretch(1)
        layout.addLayout(file_row)

        # ── Controls row ──────────────────────────────────────────────────
        controls = QHBoxLayout()
        controls.setSpacing(6)

        self._policy_label = QLabel("No policy loaded")
        self._policy_label.setStyleSheet(_LBL_STYLE)
        controls.addWidget(self._policy_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {GREEN_PRIMARY};")
        controls.addWidget(sep)

        self.query_btn = QPushButton("CLAIMSFILE")
        self.query_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.query_btn.setStyleSheet(_BTN_STYLE)
        self.query_btn.clicked.connect(self._on_query)
        controls.addWidget(self.query_btn)

        controls.addStretch(1)
        layout.addLayout(controls)

        # ── No-access notice (red) ────────────────────────────────────────
        self._no_access_label = QLabel(_NO_ACCESS_MESSAGE)
        self._no_access_label.setStyleSheet(
            "color: #C0392B; font-size: 12px; font-weight: bold; "
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

    # -- Public API --------------------------------------------------------

    def load_policy(self, policy: Optional['PolicyInformation']):
        """Bind a policy and run the claim-file query."""
        self._policy = policy

        if policy is not None and getattr(policy, "exists", False):
            company = str(getattr(policy, "company_code", "") or "").strip()
            number = str(getattr(policy, "policy_number", "") or "").strip()
            self._policy_label.setText(f"{company}  /  {number}")
            self._on_query()
        else:
            self._policy_label.setText("No policy loaded")
            self.grid.set_dataframe(pd.DataFrame(columns=FIELD_NAMES), limit_rows=False)
            self._set_status("Load a policy to view its claim records.")

    def reset(self):
        """Clear all data for a clean slate (used when a new policy loads)."""
        self._policy = None
        self._policy_label.setText("No policy loaded")
        self._show_grid()
        self.grid.set_dataframe(pd.DataFrame(columns=FIELD_NAMES), limit_rows=False)
        self._set_status("")

    def export_state(self) -> dict:
        """Snapshot the current results so they can be restored when the user
        switches back to this policy."""
        df = None
        if self.grid.model is not None:
            df = self.grid.model.get_original_data().copy()
        return {
            "df": df,
            "status": self._status_label.text(),
            "no_access": self._no_access_label.isVisible(),
        }

    def restore_state(self, policy: Optional['PolicyInformation'], state: dict):
        """Re-bind a policy and restore a previously captured snapshot."""
        self._policy = policy
        if policy is not None and getattr(policy, "exists", False):
            company = str(getattr(policy, "company_code", "") or "").strip()
            number = str(getattr(policy, "policy_number", "") or "").strip()
            self._policy_label.setText(f"{company}  /  {number}")
        else:
            self._policy_label.setText("No policy loaded")
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

    def _set_status(self, text: str, is_error: bool = False):
        color = "#C0392B" if is_error else GRAY_DARK
        weight = "bold" if is_error else "normal"
        self._status_label.setStyleSheet(
            f"font-size: 10px; color: {color}; font-weight: {weight}; "
            f"background: transparent; border: none;"
        )
        self._status_label.setText(text)
        QApplication.processEvents()

    def _show_no_access(self):
        self._no_access_label.setVisible(True)
        self.grid.setVisible(False)
        self._set_status("")

    def _show_grid(self):
        self._no_access_label.setVisible(False)
        self.grid.setVisible(True)

    def _on_query(self):
        if not self._policy or not getattr(self._policy, "exists", False):
            self._set_status("Load a policy first, then run the query.")
            return

        policy_no = str(getattr(self._policy, "policy_number", "") or "").strip()

        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        self._set_status("Reading claim file …")
        try:
            df = self._read_claims_file()
        except (PermissionError, OSError):
            QApplication.restoreOverrideCursor()
            self._show_no_access()
            return
        except Exception as exc:  # noqa: BLE001 - surface unexpected parse errors
            QApplication.restoreOverrideCursor()
            self._show_grid()
            self.grid.set_dataframe(pd.DataFrame(columns=FIELD_NAMES), limit_rows=False)
            self._set_status(f"Could not read claim file: {exc}", is_error=True)
            return

        self._show_grid()
        matches = self._filter_by_policy(df, policy_no)

        if matches.empty:
            placeholder = pd.DataFrame({"Claim File Result": [_NO_RECORDS_MESSAGE]})
            self.grid.set_dataframe(placeholder, limit_rows=False)
            self.grid.autofit_columns_to_data()
            QApplication.restoreOverrideCursor()
            self._set_status("0 record(s) found.")
            return

        self.grid.set_dataframe(matches, limit_rows=False)
        self.grid.autofit_columns_to_data()
        QApplication.restoreOverrideCursor()
        self._set_status(f"{len(matches):,} record(s) found.")

    def _read_claims_file(self) -> pd.DataFrame:
        """Read the semicolon-delimited claim file into a string DataFrame."""
        # Probe readability first so a missing/locked file surfaces as no-access.
        with open(CLAIMS_FILE_PATH, "r", encoding="latin-1"):
            pass

        df = pd.read_csv(
            CLAIMS_FILE_PATH,
            sep=";",
            header=None,
            names=FIELD_NAMES,
            dtype=str,
            keep_default_na=False,
            encoding="latin-1",
            engine="python",
            on_bad_lines="skip",
        )
        return df

    @staticmethod
    def _filter_by_policy(df: pd.DataFrame, policy_no: str) -> pd.DataFrame:
        """Return rows whose Policy_Number matches, tolerating leading zeros."""
        if df.empty or _MATCH_FIELD not in df.columns:
            return df.iloc[0:0]

        col = df[_MATCH_FIELD].astype(str).str.strip()
        target = policy_no.strip()

        mask = col == target
        if not mask.any() and target:
            mask = col.str.lstrip("0") == target.lstrip("0")
        return df[mask]
