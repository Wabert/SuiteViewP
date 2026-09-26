"""
CYBERLIFE_PDF tab - queries dbo.CYBERLIFE_PDF in the UL_Rates database.

Embedded in the Other Data tab and queried immediately on first selection.
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

from datetime import date
from typing import Optional, TYPE_CHECKING

import pandas as pd
from PyQt6.QtWidgets import QHBoxLayout, QLabel

from ..styles import GRAY_DARK
from .source_query_tab import SourceQueryTab
from suiteview.core.data_sources import UL_RATES_DSN

if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


TABLE_NAME = "dbo.CYBERLIFE_PDF"
PLANCODE_COLUMN = "Plancode"
FIELD_NAME_COLUMN = "FieldName"

_NO_ACCESS_MESSAGE = (
    "You do not have access to this database (UL_Rates) set up on your machine."
)
_NO_RECORDS_MESSAGE = "No CYBERLIFE_PDF records found for this policy's plancodes."


class CyberlifePdfTab(SourceQueryTab):
    """dbo.CYBERLIFE_PDF viewer for the loaded policy's plancodes."""

    dsn = UL_RATES_DSN
    query_button_text = "Refresh"
    no_access_message = _NO_ACCESS_MESSAGE
    no_records_message = _NO_RECORDS_MESSAGE
    has_date_controls = False
    auto_query_on_load = True

    def __init__(self, parent=None):
        self._plancodes: list[str] = []
        super().__init__(parent)

    def _add_query_controls(self, controls: QHBoxLayout) -> None:
        self._plancodes_label = QLabel("Plancodes: —")
        self._plancodes_label.setStyleSheet(
            f"font-size: 11px; color: {GRAY_DARK}; background: transparent; border: none;"
        )
        controls.addWidget(self._plancodes_label)

    def _after_policy_loaded(self, policy: Optional["PolicyInformation"]) -> None:
        self._plancodes = self._collect_plancodes(policy)
        self._update_plancodes_label()

    def _reset_extra_state(self) -> None:
        self._plancodes = []
        self._update_plancodes_label()

    def _export_extra_state(self) -> dict:
        return {"plancodes": list(self._plancodes)}

    def _restore_extra_state(
        self, policy: Optional["PolicyInformation"], state: dict
    ) -> None:
        self._plancodes = list(state.get("plancodes") or self._collect_plancodes(policy))
        self._update_plancodes_label()

    @staticmethod
    def _collect_plancodes(policy: Optional["PolicyInformation"]) -> list[str]:
        """All plancodes on the policy (base + riders, no benefits), de-duped."""
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

    def _build_query_request(
        self,
        policy: "PolicyInformation",
        date_from: Optional[date],
        date_to: Optional[date],
    ):
        self._plancodes = self._collect_plancodes(policy)
        self._update_plancodes_label()
        if not self._plancodes:
            self._set_status("This policy has no plancodes to look up.", error=True)
            return None
        return list(self._plancodes)

    def _query_status_text(self, request) -> str:
        return f"Querying {TABLE_NAME} …"

    def _run_query_for_request(self, plancodes: list[str]) -> pd.DataFrame:
        placeholders = ", ".join("?" for _ in plancodes)
        sql = (
            f"SELECT UserID, Plancode, FieldName, FieldValue "
            f"FROM {TABLE_NAME} "
            f"WHERE LTRIM(RTRIM({PLANCODE_COLUMN})) IN ({placeholders})"
        )
        _columns, rows = self._fetch_rows(sql, tuple(plancodes))
        if not rows:
            return pd.DataFrame()

        raw = pd.DataFrame(rows, columns=["UserID", "Plancode", "FieldName", "FieldValue"])
        for col in raw.columns:
            raw[col] = raw[col].map(lambda v: str(v).strip() if v is not None else "")
        raw["Plancode"] = raw["Plancode"].str.upper()

        present = set(raw["Plancode"])
        ordered_plancodes = [pc for pc in plancodes if pc in present]
        for pc in raw["Plancode"].unique():
            if pc not in ordered_plancodes:
                ordered_plancodes.append(pc)

        pivot = raw.pivot_table(
            index="FieldName",
            columns="Plancode",
            values="FieldValue",
            aggfunc="first",
        )
        pivot = pivot.reindex(columns=ordered_plancodes)
        pivot = pivot.sort_index()
        pivot = pivot.reset_index()

        userid_row = {FIELD_NAME_COLUMN: "UserID"}
        for pc in ordered_plancodes:
            uids = sorted({u for u in raw.loc[raw["Plancode"] == pc, "UserID"] if u})
            userid_row[pc] = ", ".join(uids)

        result = pd.concat(
            [pd.DataFrame([userid_row]), pivot],
            ignore_index=True,
        )
        result = result.fillna("")
        return result[[FIELD_NAME_COLUMN] + ordered_plancodes]

    def _success_status(self, df: pd.DataFrame) -> str:
        plan_cols = [c for c in df.columns if c != FIELD_NAME_COLUMN]
        field_rows = max(len(df) - 1, 0)
        return f"{len(plan_cols)} plancode(s), {field_rows} field(s)."
