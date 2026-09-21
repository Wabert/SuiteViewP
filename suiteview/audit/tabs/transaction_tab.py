"""Transaction reference and two compact criteria sets with optional date links."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QVBoxLayout, QWidget,
)

from ..constants import TRANSACTION_TYPE_ITEMS
from ..transaction_filters import TransactionCriteria, TransactionDateComparison, parse_date_comparison
from ..profile_manager import get_listbox_selected, set_listbox_selected
from ._styles import (
    TightItemDelegate, connect_checkbox_listbox, make_checkbox, make_combo, make_listbox,
    make_multiselect_popup,
)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_CTRL_H = 22
_DATE_COMPARISON_HINT = (
    "Compare this Transaction 2 date with a matching Transaction 1 date on the same policy. "
    "After/Before are strict date comparisons; both dropdowns must match the same pair. "
    "Date ranges still apply. If Transaction 1 is empty, any transaction can be the reference. "
    "With Transaction 2 Exclude, require Transaction 1 but no qualifying pair."
)
_TRANSACTION_SELECT_ITEMS = [
    (label, label.split(" - ", 1)[0].strip()) for label in TRANSACTION_TYPE_ITEMS
]
_GRP_STYLE_GREEN = (
    "QGroupBox { font-weight: bold; color: #2E7D32; border: 1px solid #4CAF50;"
    " border-radius: 3px; margin-top: 8px; padding-top: 10px; }"
    "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
)


def _label(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(_FONT)
    label.setFixedHeight(_CTRL_H)
    return label


def _entry(width: int = 90) -> QLineEdit:
    entry = QLineEdit()
    entry.setFont(_FONT)
    entry.setFixedSize(width, _CTRL_H)
    return entry


class TransactionCriteriaPanel(QWidget):
    """One self-contained transaction filter; all its fields match the same row."""

    def __init__(self, number: int, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)
        title = _label(f"Transaction {number}")
        title.setFont(_FONT_BOLD)
        title.setStyleSheet("color: #1E5BA8;")
        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(title)
        self.chk_exclude = make_checkbox("Exclude")
        self.chk_exclude.setToolTip(
            "Find policies with no transaction matching all criteria in this section. "
            "An empty section is still ignored."
            + (" Checking this also clears and disables Transaction 2 date comparisons."
               if number == 1 else "")
        )
        header.addWidget(self.chk_exclude)
        header.addStretch()
        root.addLayout(header)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        grid.setColumnStretch(2, 1)
        self.transaction_types = make_multiselect_popup(
            _TRANSACTION_SELECT_ITEMS, width=280, height_rows=20,
        )
        grid.addWidget(_label("Transaction Type"), 0, 0)
        grid.addWidget(self.transaction_types, 0, 1, Qt.AlignmentFlag.AlignLeft)

        self.ranges: dict[str, tuple[QLineEdit, QLineEdit]] = {}
        self.date_comparisons: dict[str, QComboBox] = {}
        for row, name, text in (
            (1, "entry", "Entry Dt"), (2, "eff", "Eff Dt"),
            (3, "eff_month", "Eff Mth"), (4, "eff_day", "Eff Day"),
            (5, "gross", "Gross Amt"),
        ):
            width = 40 if name in ("eff_month", "eff_day") else 90
            lo, hi = _entry(width), _entry(width)
            self.ranges[name] = (lo, hi)
            bounds = QHBoxLayout()
            bounds.setSpacing(6)
            bounds.addWidget(lo)
            bounds.addWidget(_label("to"))
            bounds.addWidget(hi)
            if number == 2 and name in ("entry", "eff"):
                comparison = make_combo([item.value for item in TransactionDateComparison], width=190)
                comparison.setToolTip(_DATE_COMPARISON_HINT)
                comparison.setAccessibleName(f"Transaction 2 {text} comparison")
                self.date_comparisons[name] = comparison
                bounds.addWidget(comparison)
            if name == "eff_month":
                self.chk_eff_month = make_checkbox("Eff Mth = Issue Mth")
                bounds.addWidget(self.chk_eff_month)
            elif name == "eff_day":
                self.chk_eff_day = make_checkbox("Eff Day = Issue Day")
                bounds.addWidget(self.chk_eff_day)
            bounds.addStretch()
            grid.addWidget(_label(text), row, 0)
            grid.addLayout(bounds, row, 1)
            if name in ("entry", "eff"):
                for edit in (lo, hi):
                    edit.setToolTip("Inclusive date: MM/DD/YYYY or YYYY-MM-DD; either end may be blank.")

        for name, maximum in (("eff_month", 12), ("eff_day", 31)):
            for edit in self.ranges[name]:
                edit.setToolTip(f"Optional inclusive range: 1 to {maximum}.")

        reversals = QHBoxLayout()
        reversals.setSpacing(12)
        self.reversal_filters: dict[str, tuple[QCheckBox, QListWidget]] = {}
        for name, text, column in (
            ("is_reversal", "Is Reversal", "FCB0_REV_IND"),
            ("reversed", "Reversed", "FCB2_REV_APPL_IND"),
        ):
            group = QVBoxLayout()
            group.setSpacing(2)
            checkbox = make_checkbox(text)
            choices = make_listbox(["0", "1"], height_rows=2, enabled=False)
            choices.setFixedWidth(max(90, checkbox.sizeHint().width()))
            hint = (
                f"{column}: 0 = No, 1 = Yes. Check to enable, then select values. "
                "No selection leaves this flag unrestricted."
            )
            checkbox.setToolTip(hint)
            choices.setToolTip(hint)
            connect_checkbox_listbox(checkbox, choices)
            group.addWidget(checkbox)
            group.addWidget(choices)
            reversals.addLayout(group)
            self.reversal_filters[name] = (checkbox, choices)
        details = QHBoxLayout()
        details.setSpacing(6)
        self.txt_origin = _entry(45)
        self.txt_origin.setToolTip("Exact ORIGIN_OF_TRANS value")
        self.txt_fund_id = _entry(110)
        self.txt_fund_id.setToolTip("Comma-separated fund IDs; any listed ID may match.")
        details.addWidget(_label("Origin"))
        details.addWidget(self.txt_origin)
        details.addWidget(_label("Fund ID List"))
        details.addWidget(self.txt_fund_id)
        details.addStretch()
        reversals.addLayout(details)
        grid.addLayout(reversals, 6, 1)
        root.addLayout(grid)

    def criteria(self) -> TransactionCriteria:
        def bounds(name: str) -> tuple[str, str]:
            lo, hi = self.ranges[name]
            return lo.text().strip(), hi.text().strip()

        def flags(name: str) -> tuple[str, ...]:
            checkbox, choices = self.reversal_filters[name]
            return tuple(get_listbox_selected(choices)) if checkbox.isChecked() else ()

        def comparison(name: str) -> TransactionDateComparison:
            combo = self.date_comparisons.get(name)
            return (TransactionDateComparison(combo.currentText()) if combo is not None
                    else TransactionDateComparison.NONE)

        return TransactionCriteria(
            transaction_types=tuple(self.transaction_types.selected_values()),
            entry_date=bounds("entry"), effective_date=bounds("eff"),
            effective_month=bounds("eff_month"), effective_day=bounds("eff_day"),
            gross_amount=bounds("gross"), origin=self.txt_origin.text().strip(),
            fund_ids=self.txt_fund_id.text().strip(),
            on_issue_month=self.chk_eff_month.isChecked(),
            on_issue_day=self.chk_eff_day.isChecked(),
            exclude=self.chk_exclude.isChecked(),
            is_reversal_values=flags("is_reversal"),
            reversed_values=flags("reversed"),
            entry_comparison=comparison("entry"),
            effective_comparison=comparison("eff"),
        )

    def get_state(self) -> dict:
        state = {
            "chk_exclude": self.chk_exclude.isChecked(),
            "transaction_types": self.transaction_types.text(),
            "chk_eff_month": self.chk_eff_month.isChecked(),
            "chk_eff_day": self.chk_eff_day.isChecked(),
            "txt_origin": self.txt_origin.text(),
            "txt_fund_id": self.txt_fund_id.text(),
        }
        for name, (lo, hi) in self.ranges.items():
            state[f"txt_{name}_lo"] = lo.text()
            state[f"txt_{name}_hi"] = hi.text()
        for name, (checkbox, choices) in self.reversal_filters.items():
            state[f"chk_{name}"] = checkbox.isChecked()
            state[f"list_{name}"] = get_listbox_selected(choices)
        for name, combo in self.date_comparisons.items():
            state[f"{name}_comparison"] = combo.currentText()
        return state

    def set_state(self, state: dict):
        comparisons = {
            name: parse_date_comparison(
                state.get(f"{name}_comparison", "none"),
                f"Transaction 2 - {'Entry Dt' if name == 'entry' else 'Eff Dt'}",
            )
            for name in self.date_comparisons
        }
        self.chk_exclude.setChecked(state.get("chk_exclude", False))
        self.transaction_types.setText(state.get("transaction_types", ""))
        self.chk_eff_month.setChecked(state.get("chk_eff_month", False))
        self.chk_eff_day.setChecked(state.get("chk_eff_day", False))
        self.txt_origin.setText(state.get("txt_origin", ""))
        self.txt_fund_id.setText(state.get("txt_fund_id", ""))
        for name, (lo, hi) in self.ranges.items():
            lo.setText(state.get(f"txt_{name}_lo", ""))
            hi.setText(state.get(f"txt_{name}_hi", ""))
        for name, (checkbox, choices) in self.reversal_filters.items():
            checkbox.setChecked(state.get(f"chk_{name}", False))
            set_listbox_selected(
                choices, state.get(f"list_{name}", []) if checkbox.isChecked() else [],
            )
        for name, comparison in comparisons.items():
            self.date_comparisons[name].setCurrentText(comparison.value)


class TransactionTab(QWidget):
    """Reference list plus stacked Transaction 1 AND Transaction 2 criteria."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(4)
        grp_ref = QGroupBox("Transaction Type and Subtype")
        grp_ref.setStyleSheet(_GRP_STYLE_GREEN)
        ref_lay = QVBoxLayout(grp_ref)
        ref_lay.setContentsMargins(6, 6, 6, 4)
        self.list_trans_ref = QListWidget()
        self.list_trans_ref.setFont(_FONT)
        self.list_trans_ref.setItemDelegate(TightItemDelegate(self.list_trans_ref))
        self.list_trans_ref.setUniformItemSizes(True)
        self.list_trans_ref.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_trans_ref.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_trans_ref.setStyleSheet(
            "QListWidget { border: none; background-color: #F5F5F0; color: #555; }"
            "QListWidget::item { padding: 0px 2px; }"
        )
        self.list_trans_ref.addItems(TRANSACTION_TYPE_ITEMS)
        self.list_trans_ref.setFixedWidth(320)
        ref_lay.addWidget(self.list_trans_ref)
        left.addWidget(grp_ref, 1)
        note = QLabel(
            "Note: Query time on transactions will\n"
            "be much longer without a plancode"
        )
        note.setFont(_FONT)
        note.setStyleSheet("color: #C00000;")
        left.addWidget(note)
        root.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.transaction1 = TransactionCriteriaPanel(1)
        self.transaction2 = TransactionCriteriaPanel(2)
        self.transaction1.chk_exclude.toggled.connect(self._on_first_exclude_toggled)
        right.addWidget(self.transaction1)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #6A9BD1;")
        right.addWidget(separator)
        right.addWidget(self.transaction2)
        hint = QLabel(
            "Transaction 1 AND Transaction 2; date comparisons link a matching pair.\n"
            "Exclude requires no matching transaction; otherwise at least one must match."
        )
        hint.setFont(_FONT)
        hint.setStyleSheet("color: #555;")
        right.addWidget(hint)
        right.addStretch()
        root.addLayout(right, 1)

    @pyqtSlot(bool)
    def _on_first_exclude_toggled(self, excluded: bool):
        for combo in self.transaction2.date_comparisons.values():
            if excluded:
                combo.setCurrentIndex(0)
            combo.setEnabled(not excluded)
            combo.setToolTip(
                "Turn off Transaction 1 Exclude to compare dates. Enabling it clears comparisons."
                if excluded else _DATE_COMPARISON_HINT
            )

    def criteria(self) -> tuple[TransactionCriteria, TransactionCriteria]:
        return self.transaction1.criteria(), self.transaction2.criteria()

    def get_state(self) -> dict:
        return {
            **self.transaction1.get_state(),
            "transaction2": self.transaction2.get_state(),
        }

    def set_state(self, state: dict):
        second_state = state.get("transaction2", {})
        if state.get("chk_exclude", False) and any(
            second_state.get(f"{name}_comparison", "none") != "none"
            for name in self.transaction2.date_comparisons
        ):
            raise ValueError("Transaction 2 - date comparisons require Transaction 1 Exclude to be off.")
        self.transaction1.set_state(state)
        self.transaction2.set_state(second_state)
        self._on_first_exclude_toggled(self.transaction1.chk_exclude.isChecked())
