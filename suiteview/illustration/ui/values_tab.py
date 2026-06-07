"""Values tab for monthly illustration output."""

from __future__ import annotations

from typing import Iterable

import pandas as pd
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.audit.tabs._styles import TightItemDelegate
from suiteview.ui.widgets.filter_table_view import FilterTableView

from .styles import PURPLE_BG, PURPLE_DARK


class ColumnDisplayPicker(QWidget):
    """Collapsed input-style multi-select picker with a popup list."""

    selectionChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: dict[str, QListWidgetItem] = {}
        self._popup = QFrame(None, Qt.WindowType.Popup)
        self._popup.setObjectName("columnDisplayPopup")
        self._popup.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.display = QLineEdit(self)
        self.display.setReadOnly(True)
        self.display.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.display.setFixedHeight(22)
        self.display.setMinimumWidth(160)
        self.display.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #B79CDE; border-right: none;"
            " border-top-left-radius: 3px; border-bottom-left-radius: 3px; padding: 0px 6px;"
            " font-size: 9pt; color: #2A1458; }"
            "QLineEdit:hover { background: #FBF9FE; }"
        )
        self.display.mousePressEvent = self._display_mouse_press_event
        layout.addWidget(self.display)

        self.button = QToolButton(self)
        self.button.setText("▾")
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setFixedSize(22, 22)
        self.button.clicked.connect(self.toggle_popup)
        self.button.setStyleSheet(
            "QToolButton { background: white; border: 1px solid #B79CDE; border-left: none;"
            " border-top-right-radius: 3px; border-bottom-right-radius: 3px;"
            " color: #2A1458; font-size: 10pt; padding: 0px; }"
            "QToolButton:hover { background: #FBF9FE; }"
        )
        layout.addWidget(self.button)

        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        popup_layout.setSpacing(0)

        self.list_widget = QListWidget(self._popup)
        self.list_widget.setItemDelegate(TightItemDelegate(self.list_widget))
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSpacing(0)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.list_widget.setStyleSheet(
            "QListWidget { background: white; border: 1px solid #B79CDE; outline: none; font-size: 9pt; }"
            "QListWidget::item { padding: 0px 3px; border: none; }"
            "QListWidget::item:selected { background-color: #DDEEFF; color: #2A1458; border: none; }"
            "QListWidget::item:hover { background-color: #F6F1FB; }"
            "QListWidget::item:focus { outline: none; border: none; }"
        )
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        popup_layout.addWidget(self.list_widget)

    def _display_mouse_press_event(self, event):
        self.toggle_popup()
        event.accept()

    def set_items(self, items: list[tuple[str, bool, bool]]):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self._items.clear()
        for label, selected, enabled in items:
            item = QListWidgetItem(label)
            flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            if not enabled:
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags)
            if not enabled:
                item.setToolTip("Not wired yet")
                item.setForeground(QColor("#8A7BA8"))
            self.list_widget.addItem(item)
            self._items[label] = item
            item.setSelected(selected and enabled)
        frame_height = self.list_widget.frameWidth() * 2
        popup_height = max(4, self.list_widget.count()) * TightItemDelegate.ROW_H + frame_height + 2
        self.list_widget.setFixedHeight(popup_height)
        self._popup.setFixedWidth(self.width())
        self.list_widget.blockSignals(False)
        self._update_display_text()

    def selected_labels(self) -> set[str]:
        return {item.text() for item in self.list_widget.selectedItems()}

    def set_selected(self, label: str, selected: bool):
        item = self._items.get(label)
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        self.list_widget.blockSignals(True)
        item.setSelected(selected)
        self.list_widget.blockSignals(False)
        self._update_display_text()

    def toggle_popup(self):
        if self._popup.isVisible():
            self._popup.hide()
            return
        self._popup.setFixedWidth(self.width())
        popup_pos = self.mapToGlobal(self.rect().bottomLeft())
        self._popup.move(popup_pos)
        self._popup.show()
        self._popup.raise_()
        self.list_widget.setFocus(Qt.FocusReason.PopupFocusReason)

    def hide_popup(self):
        self._popup.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._popup.setFixedWidth(self.width())

    def _on_selection_changed(self):
        self._update_display_text()
        self.selectionChanged.emit()

    def _update_display_text(self):
        selected = [item.text() for item in self.list_widget.selectedItems()]
        self.display.setText(", ".join(selected) if selected else "Select columns")


class IllustrationValuesTab(QWidget):
    """Tab that displays monthly illustration values in a filterable grid."""

    LIGHT_PURPLE = QColor("#E8DDF8")
    MINIMAL_COLUMNS = [
        "Date",
        "Year",
        "Month",
        "Premium",
        "Death Benefit",
        "Account Value",
        "PolicyDebt",
    ]
    PRESET_ITEMS = [
        ("Minimal", True, True),
        ("+Standard", True, True),
        ("+Coverages", False, False),
        ("+Rates", False, False),
        ("+LapseTest", False, False),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_columns: list[str] = []
        self._setup_ui()
        self.clear_results()

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;"
        )
        layout.addWidget(self.status_label)

        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 0, 0, 0)
        controls_row.setSpacing(8)

        display_label = QLabel("Column Display")
        display_label.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;"
        )
        controls_row.addWidget(display_label, 0, Qt.AlignmentFlag.AlignTop)

        self.column_display_picker = ColumnDisplayPicker(self)
        self.column_display_picker.selectionChanged.connect(self._apply_column_display)
        self._setup_column_display_items()
        controls_row.addWidget(self.column_display_picker)
        controls_row.addStretch(1)
        layout.addLayout(controls_row)

        self.grid = FilterTableView(self)
        self.grid.set_search_visible(False)
        layout.addWidget(self.grid)

    def _setup_column_display_items(self):
        self.column_display_picker.set_items(self.PRESET_ITEMS)

    def clear_results(self, message: str = "Load a policy, then click Run Values."):
        self.status_label.setText(message)
        self.grid.set_dataframe(pd.DataFrame(), limit_rows=False)

    def display_projection(
        self,
        policy: IllustrationPolicyData,
        results: Iterable[MonthlyState],
        months: int = 24,
        injected_first_row_columns: set[str] | None = None,
    ):
        rows = [self._state_to_row(policy, state) for state in results]
        frame = pd.DataFrame(rows)
        self._all_columns = list(frame.columns)
        self.grid.set_dataframe(frame, limit_rows=False)
        self.grid.set_numeric_formatting(
            default_decimals=2,
            column_decimals={"Face Amount": 0, "Year": 0, "Month": 0},
        )
        self.grid.set_highlighted_cells(
            {(0, column_name): self.LIGHT_PURPLE for column_name in (injected_first_row_columns or set())}
        )
        if self.grid.model is not None:
            self.grid.model._left_align_columns = {0}
        self._apply_column_display()
        self.status_label.setText(f"Showing valuation snapshot plus {months} projected months.")

    def _state_to_row(self, policy: IllustrationPolicyData, state: MonthlyState) -> dict:
        return {
            "Date": state.date,
            "Year": state.policy_year,
            "Month": state.policy_month,
            "Premium": state.gross_premium,
            "Premium Load": state.total_premium_load,
            "RegLn Total": state.end_rg_loan_princ + state.end_rg_loan_accrued,
            "PrefLn Total": state.end_pf_loan_princ + state.end_pf_loan_accrued,
            "Varln Total": state.end_vbl_loan_princ + state.end_vbl_loan_accrued,
            "AV before MD": self._av_before_md(state),
            "Face Amount": policy.total_face,
            "Death Benefit": self._death_benefit(state),
            "NAR": state.total_nar or state.nar,
            "COI Charge": state.total_coi_charge or state.coi_charge,
            "Rider Charge": state.rider_charges,
            "EPU Fee": state.epu_charge,
            "Monthly Fee": state.mfee_charge,
            "Monthly Deduction": state.total_deduction,
            "AV after MD": state.av_after_deduction,
            "Interest Days": state.days_in_month,
            "Interest Rate": state.annual_interest_rate * 100.0,
            "Interest": state.interest_credited,
            "RegLn Int": state.reg_loan_charge,
            "PrefLn Int": state.pref_loan_charge,
            "VarLn Int": state.vbl_loan_charge,
            "Account Value": state.av_end_of_month,
            "PolicyDebt": state.policy_debt,
        }

    def _apply_column_display(self, item: QListWidgetItem | None = None):
        if self.grid.model is None or not self._all_columns:
            return

        visible_columns = set(self.MINIMAL_COLUMNS)
        selected_labels = self.column_display_picker.selected_labels()
        if "Minimal" not in selected_labels:
            self.column_display_picker.set_selected("Minimal", True)
            selected_labels = self.column_display_picker.selected_labels()
        if "+Standard" in selected_labels:
            visible_columns = set(self._all_columns)

        for column_index, column_name in enumerate(self._all_columns):
            self.grid.table_view.setColumnHidden(column_index, column_name not in visible_columns)

    @staticmethod
    def _av_before_md(state: MonthlyState) -> float:
        return state.md_check_av_before_deduction or state.av_after_premium

    @staticmethod
    def _death_benefit(state: MonthlyState) -> float:
        return state.ending_db or state.total_db or state.gross_db