"""
Paste Policy List dialog — turn policies copied from Excel into a query table.

Reads the clipboard as soon as it opens (and again on **Paste from clipboard**),
guesses the policy and company columns, and shows exactly what will be added:
normalized values in a preview grid, counts, and loud warnings for anything that
could silently miss a match (dropped leading zeros, unknown company codes). The
parsing rules live in :mod:`suiteview.audit.policy_list`.
"""
from __future__ import annotations

import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout,
)

from suiteview.audit.dialogs.tables_dialog import _BTN_SMALL_STYLE, _BTN_STYLE
from suiteview.audit.policy_list import (
    DEFAULT_LIST_NAME,
    PolicyList,
    build_policy_list,
    guess_columns,
    looks_like_header,
    parse_clipboard_text,
    safe_table_name,
)
from suiteview.ui.widgets.filter_table_view import FilterTableView

BAS_POL_TABLE = "DB2TAB.LH_BAS_POL"
_NO_COMPANY = "(none)"
_PREVIEW_ROWS = 500


class PolicyListDialog(QDialog):
    """Preview and confirm a pasted policy list; see :meth:`result_list`."""

    def __init__(self, *, taken_names: set[str], can_join_bas_pol: bool,
                 text: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paste Policy List")
        self.setMinimumSize(620, 460)
        self._taken = set(taken_names)
        self._grid: list[list[str]] = []
        self._result: PolicyList | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(5)

        intro = QLabel(
            "Copy policy numbers (and company codes) from Excel, then paste them here. "
            "They become a list table joined to LH_BAS_POL, so you can add any policy "
            "data to it — every pasted row stays in the results, even if not found.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #334155; font-size: 8pt;")
        lay.addWidget(intro)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Name"))
        self.txt_name = QLineEdit(safe_table_name(DEFAULT_LIST_NAME, self._taken))
        self.txt_name.setFixedWidth(150)
        row1.addWidget(self.txt_name)
        row1.addSpacing(14)
        row1.addWidget(QLabel("Policy column"))
        self.cmb_policy = QComboBox()
        row1.addWidget(self.cmb_policy)
        row1.addWidget(QLabel("Company column"))
        self.cmb_company = QComboBox()
        row1.addWidget(self.cmb_company)
        row1.addStretch(1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        self.chk_header = QCheckBox("First row is column names")
        self.chk_dupes = QCheckBox("Remove duplicate policies")
        self.chk_dupes.setChecked(True)
        self.chk_pad = QCheckBox("Restore leading zeros: pad all-digit policies to")
        self.spn_pad = QSpinBox()
        self.spn_pad.setRange(2, 15)
        self.spn_pad.setValue(9)
        self.spn_pad.setSuffix(" digits")
        for widget in (self.chk_header, self.chk_dupes, self.chk_pad, self.spn_pad):
            row2.addWidget(widget)
        row2.addStretch(1)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        self.chk_join = QCheckBox("Join to LH_BAS_POL")
        self.chk_join.setToolTip(
            f"Adds {BAS_POL_TABLE} to the query, joined on policy number, company code\n"
            "and system code, keeping every pasted row (Left join).")
        self.chk_join.setChecked(can_join_bas_pol)
        self.chk_join.setEnabled(can_join_bas_pol)
        if not can_join_bas_pol:
            self.chk_join.setToolTip(
                "Choose a CyberLife DB2 connection in SQL Assist to join the list to policies.")
        row3.addWidget(self.chk_join)
        row3.addSpacing(10)
        row3.addWidget(QLabel("System code"))
        self.cmb_system = QComboBox()
        self.cmb_system.addItem("I  (inforce)", "I")
        self.cmb_system.addItem("P  (pending)", "P")
        self.cmb_system.addItem("(don't match on system)", "")
        row3.addWidget(self.cmb_system)
        row3.addStretch(1)
        self.btn_paste = QPushButton("\U0001F4CB Paste again from clipboard")
        self.btn_paste.setStyleSheet(_BTN_SMALL_STYLE)
        self.btn_paste.setToolTip("Copy different rows in Excel, then click to replace these.")
        self.btn_paste.clicked.connect(self.paste_from_clipboard)
        row3.addWidget(self.btn_paste)
        lay.addLayout(row3)

        self.preview = FilterTableView()
        lay.addWidget(self.preview, 1)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet("color: #0A2A5C; font-weight: bold; font-size: 8pt;")
        lay.addWidget(self.lbl_summary)
        self.lbl_warnings = QLabel("")
        self.lbl_warnings.setWordWrap(True)
        self.lbl_warnings.setStyleSheet("color: #92400E; font-size: 8pt;")
        lay.addWidget(self.lbl_warnings)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_add = QPushButton("Add to Query")
        self.btn_add.setStyleSheet(_BTN_STYLE)
        self.btn_add.clicked.connect(self._on_add)
        buttons.addWidget(self.btn_add)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(_BTN_SMALL_STYLE)
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        lay.addLayout(buttons)

        for widget in (self.cmb_policy, self.cmb_company, self.cmb_system):
            widget.currentIndexChanged.connect(self._rebuild)
        for widget in (self.chk_dupes, self.chk_pad):
            widget.toggled.connect(self._rebuild)
        self.chk_header.toggled.connect(self._on_header_toggled)
        self.spn_pad.valueChanged.connect(self._rebuild)

        if text is None:
            self.paste_from_clipboard()
        else:
            self.set_text(text)

    # ── Input ────────────────────────────────────────────────────────────

    def paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        self.set_text(clipboard.text() if clipboard is not None else "")

    def set_text(self, text: str):
        self._grid = parse_clipboard_text(text)
        self.chk_header.blockSignals(True)
        self.chk_header.setChecked(looks_like_header(self._grid))
        self.chk_header.blockSignals(False)
        self._fill_column_choices()

    def _on_header_toggled(self, _checked: bool):
        self._fill_column_choices()

    def _fill_column_choices(self):
        has_header = self.chk_header.isChecked()
        width = len(self._grid[0]) if self._grid else 0
        names = []
        for col in range(width):
            name = self._grid[0][col] if has_header and self._grid[0][col] else ""
            names.append(f"{col + 1}: {name}" if name else f"Column {col + 1}")
        policy, company = guess_columns(self._grid, has_header)
        for combo in (self.cmb_policy, self.cmb_company):
            combo.blockSignals(True)
            combo.clear()
        for col, label in enumerate(names):
            self.cmb_policy.addItem(label, col)
        self.cmb_company.addItem(_NO_COMPANY, None)
        for col, label in enumerate(names):
            self.cmb_company.addItem(label, col)
        if width:
            self.cmb_policy.setCurrentIndex(policy)
            self.cmb_company.setCurrentIndex(0 if company is None else company + 1)
        for combo in (self.cmb_policy, self.cmb_company):
            combo.blockSignals(False)
        self._rebuild()

    # ── Normalize + preview ──────────────────────────────────────────────

    def _rebuild(self, *_args):
        if not self._grid:
            self._result = None
            self.preview.set_dataframe(pd.DataFrame())
            self.lbl_summary.setText(
                "Clipboard is empty — copy policy numbers (and company codes) from "
                "Excel, then click Paste from clipboard.")
            self.lbl_warnings.setText("")
            self.btn_add.setEnabled(False)
            return
        company = self.cmb_company.currentData()
        policy = self.cmb_policy.currentData() or 0
        if company == policy:
            company = None
        self._result = build_policy_list(
            self._grid,
            has_header=self.chk_header.isChecked(),
            policy_col=policy,
            company_col=company,
            system_code=self.cmb_system.currentData() or "",
            remove_duplicates=self.chk_dupes.isChecked(),
            pad_numeric_to=self.spn_pad.value() if self.chk_pad.isChecked() else None,
        )
        rows = self._result.rows[:_PREVIEW_ROWS]
        self.preview.set_dataframe(pd.DataFrame(rows, columns=self._result.columns))
        summary = self._result.summary()
        if len(self._result.rows) > _PREVIEW_ROWS:
            summary += f"  (first {_PREVIEW_ROWS} shown)"
        self.lbl_summary.setText(summary)
        self.lbl_warnings.setText("\n".join("\u26A0 " + w for w in self._result.warnings()))
        self.btn_add.setEnabled(bool(self._result.rows))

    def _on_add(self):
        if self._result is None or not self._result.rows:
            return
        self.accept()

    # ── Output ───────────────────────────────────────────────────────────

    def table_name(self) -> str:
        return safe_table_name(self.txt_name.text(), self._taken)

    def result_list(self) -> PolicyList | None:
        return self._result

    def join_to_bas_pol(self) -> bool:
        return self.chk_join.isEnabled() and self.chk_join.isChecked()
