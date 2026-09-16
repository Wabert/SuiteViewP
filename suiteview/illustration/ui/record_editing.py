"""Compact value-only editors for illustration starting-record assumptions."""

from datetime import date

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import QDateEdit, QDoubleSpinBox, QStyledItemDelegate


class RecordDateInput(QDateEdit):
    value_committed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDisplayFormat("MM/dd/yyyy")
        self.setCalendarPopup(True)
        self.setKeyboardTracking(False)
        self.setSpecialValueText("Not set")
        self.setFixedHeight(20)
        self.setMinimumWidth(105)
        self.setStyleSheet(
            "QDateEdit { background: white; color: #351554; border: 1px solid #987ABB; "
            "padding: 0px 3px; font-size: 11px; }")
        self.set_value(None)
        self.editingFinished.connect(self._commit)

    def set_value(self, value: date | None):
        self.setDate(QDate(value) if value is not None else self.minimumDate())
        self._applied = self.date()

    def _commit(self):
        if self.isEnabled() and self.date() != self._applied:
            self.value_committed.emit(
                None if self.date() == self.minimumDate() else self.date().toPyDate())


class FundValueDelegate(QStyledItemDelegate):
    """Keep fund identifiers outside the editor; only column 1 has a delegate."""

    def __init__(self, *, percent=False, parent=None):
        super().__init__(parent)
        self.percent = percent

    def createEditor(self, parent, option, index):
        editor = QDoubleSpinBox(parent)
        editor.setDecimals(2)
        editor.setRange(0 if self.percent else -999_999_999_999.99,
                        100 if self.percent else 999_999_999_999.99)
        editor.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        editor.setGroupSeparatorShown(True)
        editor.setSuffix(" %" if self.percent else "")
        editor.setKeyboardTracking(False)
        return editor

    def setEditorData(self, editor, index):
        editor.setValue(float(index.data(Qt.ItemDataRole.UserRole)))

    def setModelData(self, editor, model, index):
        value = editor.value()
        model.setData(index, value, Qt.ItemDataRole.UserRole)
        model.setData(index, f"{value:,.2f}" + ("%" if self.percent else ""),
                      Qt.ItemDataRole.DisplayRole)
