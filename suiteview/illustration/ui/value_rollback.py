"""Compact historical-basis controls and explicit coverage assumption editing."""

from datetime import date

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from suiteview.polview.ui.widgets import StyledInfoTableGroup
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

from .styles import GROUP_STYLE, VALUE_BUTTON_STYLE


ROLLBACK_COLORS = ("#4B2274", "#B799D9", "#FFFFFF")
ROLLBACK_NOTICE_STYLE = (
    "color: #351554; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
    "stop:0 #D7C4ED, stop:0.5 #EEE4F8, stop:1 #FFFFFF); border-left: 4px solid #7850A4;"
    " padding: 5px 12px; font-weight: bold;")


class ValueRollbackControls(QWidget):
    update_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 12, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.date_label = QLabel("Valuation Date")
        self.date_label.setFixedHeight(26)
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.date_label.setStyleSheet("color: #351554; font-size: 11px; font-weight: bold;")
        self.dates = QComboBox()
        self.dates.setFixedSize(116, 26)
        self.dates.setStyleSheet(
            "QComboBox { background: white; color: #351554; border: 1px solid #987ABB; "
            "border-radius: 4px; padding: 0px 7px; font-size: 11px; }"
            "QComboBox:disabled { background: #EEE; color: #777; border-color: #CCC; }")
        self.dates.setToolTip(
            "Loaded valuation date and recorded monthliversaries from the prior six "
            "months. Select a date, then Update. Updating the current date restores "
            "loaded values and clears manual value/coverage assumptions.")
        self.update = QPushButton("Update")
        self.update.setStyleSheet(
            "QPushButton { color: white; background: #60368B; border: 1px solid #4B2274; "
            "border-radius: 4px; padding: 0px 8px; font-size: 11px; font-weight: bold; }"
            "QPushButton:hover { background: #79509F; }"
            "QPushButton:pressed { background: #4B2274; }"
            "QPushButton:disabled { background: #DDD; color: #777; border-color: #CCC; }")
        self.update.setFixedSize(70, 26)
        self.state_label = QLabel("Load a policy")
        self.state_label.setFixedHeight(26)
        self.state_label.setStyleSheet("color: #60368B; font-size: 10px;")
        layout.addWidget(self.state_label)
        layout.addWidget(self.date_label)
        layout.addWidget(self.dates)
        layout.addWidget(self.update)
        self._applied_date: date | None = None
        self._current_date: date | None = None
        self._enabled = False
        self.dates.currentIndexChanged.connect(self._refresh)
        self.update.clicked.connect(
            lambda: self.update_requested.emit(self.dates.currentData()))
        self.set_basis([], None, enabled=False)

    def set_basis(
        self, dates: list[date], applied_date: date | None, *,
        current_date: date | None = None, enabled: bool = True, reason: str = "",
    ):
        self._current_date = current_date
        self._applied_date = applied_date or current_date
        self._enabled = enabled
        choices = ([current_date] if current_date is not None else []) + [
            when for when in dates if when != current_date]
        self.dates.blockSignals(True)
        try:
            self.dates.clear()
            for when in choices:
                self.dates.addItem(when.strftime("%m/%d/%Y"), when)
            if self._applied_date is not None:
                self.dates.setCurrentIndex(
                    choices.index(self._applied_date) if self._applied_date in choices else -1)
            self.state_label.setToolTip(reason)
        finally:
            self.dates.blockSignals(False)
        self._refresh()
        if reason:
            self.state_label.setText(reason)
            self.state_label.setVisible(True)

    def _refresh(self):
        selected = self.dates.currentData()
        active = self._enabled and bool(self.dates.count())
        self.dates.setEnabled(active)
        self.update.setEnabled(active and selected is not None)
        if self._applied_date is not None:
            self.state_label.setText(
                ("Current" if self._applied_date == self._current_date
                 else f"Rollback {self._applied_date:%m/%d/%Y}")
                + (" (selection not applied)" if selected != self._applied_date else ""))
        elif active:
            self.state_label.setText("Select date, then Update")
        else:
            self.state_label.setText("Load a policy")
        self.state_label.setVisible(selected != self._applied_date or not active)


class ScenarioAmountInput(QDoubleSpinBox):
    amount_committed = pyqtSignal(float)

    def __init__(self, parent=None, *, signed=False):
        super().__init__(parent)
        self.setRange(-1_000_000_000_000 if signed else -0.01, 999_999_999_999.99)
        self.setDecimals(2)
        self.setPrefix("$ ")
        self.setSpecialValueText("Enter value")
        self.setGroupSeparatorShown(True)
        self.setKeyboardTracking(False)
        self.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.setFixedHeight(20)
        self.setMinimumWidth(120)
        self.setStyleSheet(
            "QDoubleSpinBox { background: white; border: 1px solid #987ABB; "
            "padding: 0px 3px; color: #241244; font-size: 11px; }"
            "QDoubleSpinBox:disabled { background: #EEE; color: #777; }")
        self.set_amount(None)
        self.editingFinished.connect(self._commit)

    def set_amount(self, value: float | None):
        self.setValue(self.minimum() if value is None else value)
        self._applied_value = self.value()

    def _commit(self):
        if self.isEnabled() and self.value() > self.minimum() and self.value() != self._applied_value:
            self.amount_committed.emit(self.value())


class RollbackAmountEditor(FramelessWindowBase):
    amount_applied = pyqtSignal(float)
    closed = pyqtSignal()

    def __init__(self, title: str, rows, amount: float | None, parent=None, *, notice=None):
        self._rows = rows
        self._amount = amount
        self._notice = notice
        super().__init__(
            title=title, default_size=(510, 660), min_size=(420, 350),
            header_colors=("#2A1458", "#4C2684", "#6C43A5"), parent=parent)
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def closeEvent(self, event):
        super().closeEvent(event)
        if event.isAccepted():
            self.closed.emit()

    def build_content(self):
        body = QWidget()
        layout = QVBoxLayout(body)
        notice = QLabel(self._notice or (
            "ILLUSTRATION ASSUMPTION | Edit Amount below, then Apply. "
            "This changes only this illustration, not the policy record. "
            "For a prior valuation date, enter the amount applicable at that date."))
        notice.setWordWrap(True)
        notice.setStyleSheet(ROLLBACK_NOTICE_STYLE)
        layout.addWidget(notice)
        details = StyledInfoTableGroup("Coverage / Benefit Details", show_table=False)
        details.setStyleSheet(GROUP_STYLE)
        self.amount_edit = ScenarioAmountInput()
        self.amount_edit.set_amount(self._amount)
        amount_inserted = False
        for index, (label, value) in enumerate(self._rows):
            key = f"detail_{index}"
            details.add_field(label.rstrip(":"), key, 125, 190)
            details.set_value(key, value)
            if label.rstrip(":") == "Amount":
                details.set_field_editor(key, self.amount_edit)
                amount_inserted = True
        if not amount_inserted:
            details.add_field("Amount", "amount", 125, 190)
            details.set_field_editor("amount", self.amount_edit)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(details)
        layout.addWidget(scroll, 1)
        controls = QHBoxLayout()
        controls.addStretch(1)
        self.apply_button = QPushButton("Apply")
        self.apply_button.setStyleSheet(VALUE_BUTTON_STYLE)
        self.apply_button.setEnabled(self._amount is not None)
        self.amount_edit.valueChanged.connect(
            lambda value: self.apply_button.setEnabled(value >= 0))
        self.apply_button.clicked.connect(self._apply)
        controls.addWidget(self.apply_button)
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(VALUE_BUTTON_STYLE)
        cancel.clicked.connect(self.close)
        controls.addWidget(cancel)
        layout.addLayout(controls)
        return body

    def _apply(self):
        self.amount_applied.emit(self.amount_edit.value())
