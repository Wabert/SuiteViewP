"""
TAI All tab — filter criteria common across all four TAI tables.

Queries TAICLAIMS, TAICession, TAIReserve, and TAITransaction using
the 13 fields that exist (under different names) in every table:
  Co, Pol, Cov, Face, LOB, ReinsCo, Treaty, Plan/PlanCode,
  TreatyGrp/TrtyGrp, ReinsTyp/ReType/ReinsType, PolStatus/ClmStatus/CessStat,
  IssueDate/PolDt/IssDt, CstCntr/CC.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout,
    QPushButton,
    QDialog, QTextBrowser,
)
from PyQt6.QtGui import QFont

from .field_row import FieldRow, FieldGrid


# ── Regex help dialog ────────────────────────────────────────────────

_REGEX_HELP_HTML = """
<h3 style="color:#1E5BA8;">SQL LIKE &amp; Regex Cheat Sheet</h3>
<p>When mode is <b>contains</b>, your text is wrapped in
<code>%...%</code> automatically (SQL <code>LIKE</code>).</p>
<p>When mode is <b>regex</b>, the value is used as a SQL
<code>LIKE</code> pattern directly. Use these wildcards:</p>
<table border="1" cellpadding="4" cellspacing="0"
       style="border-collapse:collapse; font-size:9pt;">
<tr style="background:#E8F0FB;">
  <th>Pattern</th><th>Meaning</th><th>Example</th></tr>
<tr><td><code>%</code></td>
  <td>Any sequence of characters (0+)</td>
  <td><code>RGA%</code> → starts with RGA</td></tr>
<tr><td><code>_</code></td>
  <td>Any single character</td>
  <td><code>10_</code> → 101, 104, 106 …</td></tr>
<tr><td><code>[abc]</code></td>
  <td>Any one of a, b, c</td>
  <td><code>[AW]%</code> → starts with A or W</td></tr>
<tr><td><code>[a-f]</code></td>
  <td>Any character in range a–f</td>
  <td><code>[0-9]%</code> → starts with a digit</td></tr>
<tr><td><code>[^abc]</code></td>
  <td>NOT a, b, or c</td>
  <td><code>[^X]%</code> → not starting with X</td></tr>
</table>
<h4 style="color:#1E5BA8; margin-top:10px;">Common examples</h4>
<table border="1" cellpadding="4" cellspacing="0"
       style="border-collapse:collapse; font-size:9pt;">
<tr style="background:#E8F0FB;">
  <th>Goal</th><th>Pattern (regex mode)</th></tr>
<tr><td>Starts with "RGA"</td><td><code>RGA%</code></td></tr>
<tr><td>Ends with "01"</td><td><code>%01</code></td></tr>
<tr><td>Contains "FIRE"</td><td><code>%FIRE%</code></td></tr>
<tr><td>Exactly 3 characters</td><td><code>___</code></td></tr>
<tr><td>Starts with A or B</td><td><code>[AB]%</code></td></tr>
<tr><td>Second char is a digit</td><td><code>_[0-9]%</code></td></tr>
</table>
<h4 style="color:#1E5BA8; margin-top:10px;">NOT special in SQL LIKE</h4>
<p style="font-size:9pt;">
These characters are <b>literal</b> — they match themselves:<br/>
<code>.</code> &nbsp; <code>(</code> <code>)</code> &nbsp; <code>/</code>
&nbsp; <code>*</code> &nbsp; <code>?</code> &nbsp; <code>+</code>
&nbsp; <code>\\</code> &nbsp; <code>^</code> &nbsp; <code>$</code><br/>
SQL <code>LIKE</code> is <b>not</b> regex. Only
<code>%</code>, <code>_</code>, and <code>[ ]</code> are wildcards.</p>
<p style="margin-top:8px; color:#888; font-size:8pt;">
Note: SQL Server <code>LIKE</code> is case-insensitive by default.</p>
"""


class _RegexHelpDialog(QDialog):
    """Non-blocking regex cheat-sheet dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Regex / LIKE Pattern Help")
        self.setMinimumSize(420, 440)
        lay = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(_REGEX_HELP_HTML)
        lay.addWidget(browser)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        lay.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

logger = logging.getLogger(__name__)


# ── Column-name mapping per table ────────────────────────────────────
# Maps the canonical field name → actual column name in each table.

COLUMN_MAP = {
    #                    TAICLAIMS      TAICession     TAIReserve     TAITransaction
    "Co":           ("Co",          "Co",          "Co",          "Co"),
    "Pol":          ("Pol",         "Pol",         "Pol",         "Pol"),
    "Cov":          ("Cov",         "Cov",         "Cov",         "Cov"),
    "Face":         ("Face",        "Face",        "Face",        "Face"),
    "LOB":          ("LOB",         "LOB",         "LOB",         "LOB"),
    "ReinsCo":      ("ReinsCo",     "ReinsCo",     "ReinsCo",     "ReinsCo"),
    "Treaty":       ("Treaty",      "Treaty",      "Treaty",      "Treaty"),
    "Plan":         ("PlanCode",    "Plan",        "Plan",        "Plan"),
    "TreatyGrp":    ("TrtyGrp",     "TreatyGrp",   "TreatyGrp",  "TreatyGrp"),
    "ReinsTyp":     ("ReType",      "ReinsTyp",    "ReinsType",   "ReinsTyp"),
    "PolStatus":    ("ClmStatus",   "PolStatus",   "CessStat",    "PolStatus"),
    "IssueDate":    ("IssDate",     "PolDt",       "IssDt",       "PolDt"),
    "CstCntr":      ("CC",          "CstCntr",     "CstCntr",     "CstCntr"),
    "MonthEnd":     ("MonthEnd",    "monthEnd",    "MonthEnd",    None),
}

TABLE_NAMES = ["TAICLAIMS", "TAICession", "TAIReserve", "TAITransaction"]
TABLE_INDEX = {name: i for i, name in enumerate(TABLE_NAMES)}


def _col(canonical: str, table: str) -> str:
    """Return the actual column name for a canonical field in a given table."""
    return COLUMN_MAP[canonical][TABLE_INDEX[table]]


# ── Field → TAICession column mapping (for unique value registry) ────
# Maps the internal field attribute suffix → (table, column, display_name)
FIELD_REGISTRY_MAP = {
    "monthend":    ("TAICession", "monthEnd",  "MonthEnd"),
    "polnum":      ("TAICession", "Pol",       "Policy #"),
    "plancode":    ("TAICession", "Plan",      "Plancode"),
    "treaty":      ("TAICession", "Treaty",    "Treaty"),
    "treaty_grp":  ("TAICession", "TreatyGrp", "TreatyGrp"),
    "cost_center": ("TAICession", "CstCntr",   "Cost Ctr"),
    "lob":         ("TAICession", "LOB",       "LOB"),
    "polstatus":   ("TAICession", "PolStatus", "PolStatus"),
    "reinsco":     ("TAICession", "ReinsCo",   "ReinsCo"),
    "reinstype":   ("TAICession", "ReinsTyp",  "ReinsType"),
    "company":     ("TAICession", "Co",        "Company"),
    "issue_date":  ("TAICession", "PolDt",     "Issue Date"),
}


class TaiAllTab(QWidget):
    """TAI All tab — common filter criteria across all four TAI tables."""

    # Field definitions: (field_key, label, placeholder)
    _FIELD_DEFS = [
        ("polnum",      "Policy #:",   "Policy number"),
        ("plancode",    "Plancode:",   "Plan code"),
        ("treaty",      "Treaty:",     "Treaty code"),
        ("treaty_grp",  "TreatyGrp:",  "Treaty group"),
        ("cost_center", "Cost Ctr:",   "Cost center"),
        ("lob",         "LOB:",        "Line of business"),
        ("monthend",    "MonthEnd:",   "YYYYMM"),
        ("polstatus",   "PolStatus:",  "Status code"),
        ("reinsco",     "ReinsCo:",    "Reins company"),
        ("reinstype",   "ReinsType:",  "Reins type"),
        ("company",     "Company:",    "Company code"),
        ("issue_date",  "Issue Date:", "YYYYMMDD"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(2)

        # ── Field grid (6 rows × 2 columns, drag-and-drop) ──────────
        self._grid = FieldGrid(columns=2, parent=self)

        for fk, label, placeholder in self._FIELD_DEFS:
            reg = FIELD_REGISTRY_MAP.get(fk)
            row = FieldRow(fk, label, placeholder, registry_info=reg,
                           parent=self._grid)
            self._grid.add_field(row)

        root.addWidget(self._grid)
        root.addStretch(1)

    # ── Regex help ────────────────────────────────────────────────────

    _regex_help_dlg = None

    def _show_regex_help(self):
        if self._regex_help_dlg is None or not self._regex_help_dlg.isVisible():
            self._regex_help_dlg = _RegexHelpDialog(self)
            self._regex_help_dlg.show()
        else:
            self._regex_help_dlg.raise_()
            self._regex_help_dlg.activateWindow()

    # ── Query interface (delegates to FieldGrid) ─────────────────────

    def get_field_mode(self, field_name: str) -> str:
        return self._grid.get_field_mode(field_name)

    def get_field_value(self, field_name: str) -> str:
        return self._grid.get_field_value(field_name)

    def get_field_range(self, field_name: str) -> tuple[str, str]:
        return self._grid.get_field_range(field_name)

    def get_field_list_values(self, field_name: str) -> list[str]:
        return self._grid.get_field_list_values(field_name)

    # ── State management (for profiles) ──────────────────────────────

    def get_state(self) -> dict:
        grid_state = self._grid.get_state()
        # Also produce the legacy flat format so tai_query and profiles
        # continue to work without changes.
        state: dict = {"_grid": grid_state}
        _MODES = ["contains", "regex", "combo", "list", "range"]
        for fk, _label, _ph in self._FIELD_DEFS:
            row = self._grid.field(fk)
            if not row:
                continue
            rs = row.get_state()
            mode_idx = rs["mode"]
            mode = _MODES[mode_idx]
            state[f"{fk}_mode"] = mode_idx
            if mode == "combo":
                state[fk] = rs.get("val", "")
            elif mode == "range":
                state[fk] = rs.get("val", "")
                state[f"{fk}_hi"] = rs.get("hi", "")
            elif mode == "list":
                state[fk] = ""
                state[f"{fk}_list_selected"] = rs.get("list_selected", [])
            else:
                state[fk] = rs.get("val", "")
        return state

    def set_state(self, state: dict):
        # New-format grid state
        grid_state = state.get("_grid")
        if grid_state:
            self._grid.set_state(grid_state)
            return

        # Legacy flat-format: convert to per-field dicts
        _MODES = ["contains", "regex", "combo", "list", "range"]
        for fk, _label, _ph in self._FIELD_DEFS:
            row = self._grid.field(fk)
            if not row:
                continue
            idx = state.get(f"{fk}_mode", 0)
            mode = _MODES[idx]
            s: dict = {"mode": idx}
            if mode == "combo":
                s["val"] = state.get(fk, "")
            elif mode == "range":
                s["val"] = state.get(fk, "")
                s["hi"] = state.get(f"{fk}_hi", "")
            elif mode == "list":
                s["val"] = ""
                s["list_selected"] = state.get(f"{fk}_list_selected", [])
            else:
                s["val"] = state.get(fk, "")
            row.set_state(s)
