"""
Shared styled widget factories for audit tabs.

Provides blue-themed checkboxes (white checkmark), blue-bordered listboxes,
styled comboboxes with visible drop-down arrows, and wiring helpers.
All tabs should import from here for visual consistency.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QAbstractItemView, QStyledItemDelegate, QStyleOptionViewItem,
    QToolButton, QVBoxLayout, QWidget,
)
from PyQt6.QtGui import QFont

_FONT = QFont("Segoe UI", 9)
_ROW_H = 16
_CTRL_H = 22

# ── checkmark icon (created once, shared by all checkboxes) ────────────
_CHECKMARK_PATH = os.path.join(os.path.dirname(__file__), "_checkmark.png")


def _ensure_checkmark():
    if os.path.exists(_CHECKMARK_PATH):
        return
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor
    from PyQt6.QtCore import QPoint
    pix = QPixmap(12, 12)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    pen = QPen(QColor("white"))
    pen.setWidth(2)
    p.setPen(pen)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.drawLine(QPoint(2, 6), QPoint(5, 9))
    p.drawLine(QPoint(5, 9), QPoint(10, 3))
    p.end()
    pix.save(_CHECKMARK_PATH)


class TightItemDelegate(QStyledItemDelegate):
    """Forces a fixed compact row height on QListWidget items."""
    ROW_H = _ROW_H

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self.ROW_H)

    def initStyleOption(self, option: QStyleOptionViewItem, index):
        super().initStyleOption(option, index)
        from PyQt6.QtWidgets import QStyle
        option.state &= ~QStyle.StateFlag.State_HasFocus


# ── Styled checkbox (blue indicator, white checkmark) ──────────────────

def make_checkbox(text: str, *, checked: bool = False) -> QCheckBox:
    _ensure_checkmark()
    cb = QCheckBox(text)
    cb.setFont(_FONT)
    cb.setChecked(checked)
    icon_path = _CHECKMARK_PATH.replace("\\", "/")
    cb.setStyleSheet(
        "QCheckBox::indicator { border: 1px solid #1E5BA8; width: 12px; height: 12px; background-color: white; }"
        "QCheckBox::indicator:checked {"
        "  background-color: #1E5BA8; border: 1px solid #14407A;"
        f"  image: url({icon_path});"
        "}"
    )
    return cb


# ── Styled listbox (blue border, blue selection highlight) ─────────────

def make_listbox(items: list[str], *, height_rows: int = 10,
                 multi: bool = True, enabled: bool = True) -> QListWidget:
    lb = QListWidget()
    lb.setFont(_FONT)
    lb.setItemDelegate(TightItemDelegate(lb))
    lb.setUniformItemSizes(True)
    bg_color = "white" if enabled else "#F0F0F0"
    lb.setStyleSheet(
        f"QListWidget {{ border: 1px solid #1E5BA8; background-color: {bg_color}; outline: none; }}"
        "QListWidget::item { padding: 0px 2px; border: none; }"
        "QListWidget::item:selected { background-color: #A0C4E8; color: black; border: none; }"
        "QListWidget::item:focus { outline: none; border: none; }"
    )
    if multi:
        lb.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
    else:
        lb.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    lb.addItems(items)
    lb.setFixedHeight(height_rows * _ROW_H + 4)
    lb.setEnabled(enabled)
    return lb


class MultiSelectPopup(QWidget):
    """Input-style multi-select picker with a popup list."""

    def __init__(self, items: list[str | tuple[str, str]], *, width: int = 80,
                 height_rows: int | None = None, parent=None):
        super().__init__(parent)
        self._popup = QFrame(None, Qt.WindowType.Popup)
        self._popup.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.display = QLineEdit(self)
        self.display.setReadOnly(True)
        self.display.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.display.setFont(_FONT)
        self.display.setFixedSize(width, _CTRL_H)
        self.display.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #1E5BA8; border-right: none;"
            " padding: 0px 4px; }"
            "QLineEdit:hover { background: #F8FBFF; }"
        )
        self.display.mousePressEvent = self._display_mouse_press_event
        layout.addWidget(self.display)

        self.button = QToolButton(self)
        self.button.setText("v")
        self.button.setFixedSize(18, _CTRL_H)
        self.button.clicked.connect(self.toggle_popup)
        self.button.setStyleSheet(
            "QToolButton { background: white; border: 1px solid #1E5BA8; border-left: none;"
            " color: #1E5BA8; padding: 0px; }"
            "QToolButton:hover { background: #F8FBFF; }"
        )
        layout.addWidget(self.button)

        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        popup_layout.setSpacing(0)

        self.list_widget = make_listbox([], height_rows=height_rows or len(items), enabled=True)
        for item in items:
            if isinstance(item, tuple):
                label, value = item
            else:
                label = value = item
            list_item = QListWidgetItem(label)
            list_item.setData(Qt.ItemDataRole.UserRole, value)
            self.list_widget.addItem(list_item)
        self.list_widget.itemSelectionChanged.connect(self._update_display_text)
        popup_layout.addWidget(self.list_widget)

        self._popup.setFixedWidth(self.width())
        self._update_display_text()

    def _display_mouse_press_event(self, event):
        self.toggle_popup()
        event.accept()

    def selected_values(self) -> list[str]:
        return [str(item.data(Qt.ItemDataRole.UserRole) or item.text()) for item in self.list_widget.selectedItems()]

    def text(self) -> str:
        return ", ".join(self.selected_values())

    def setText(self, value: str):
        values = {part.strip() for part in (value or "").split(",") if part.strip()}
        self.list_widget.blockSignals(True)
        self.list_widget.clearSelection()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item_value = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
            item.setSelected(item_value in values or item.text() in values)
        self.list_widget.blockSignals(False)
        self._update_display_text()

    def toggle_popup(self):
        if self._popup.isVisible():
            self._popup.hide()
            return
        self._popup.setFixedWidth(self._popup_width())
        self._popup.move(self.mapToGlobal(self.rect().bottomLeft()))
        self._popup.show()
        self._popup.raise_()
        self.list_widget.setFocus(Qt.FocusReason.PopupFocusReason)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._popup.setFixedWidth(self._popup_width())

    def _popup_width(self) -> int:
        fm = self.list_widget.fontMetrics()
        widest = self.width()
        for i in range(self.list_widget.count()):
            widest = max(widest, fm.horizontalAdvance(self.list_widget.item(i).text()) + 30)
        return widest

    def _update_display_text(self):
        self.display.setText(self.text())


def make_multiselect_popup(items: list[str | tuple[str, str]], *, width: int = 80,
                           height_rows: int | None = None) -> MultiSelectPopup:
    return MultiSelectPopup(items, width=width, height_rows=height_rows)


# ── Styled combobox ────────────────────────────────────────────────────

class _ComboItemDelegate(QStyledItemDelegate):
    """Forces compact row height in QComboBox popup dropdowns."""
    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), _ROW_H)

    def initStyleOption(self, option: QStyleOptionViewItem, index):
        super().initStyleOption(option, index)
        from PyQt6.QtWidgets import QStyle
        option.state &= ~QStyle.StateFlag.State_HasFocus


class WidePopupComboBox(QComboBox):
    """QComboBox whose dropdown popup auto-sizes to the widest item."""

    def showPopup(self):
        # Calculate width needed for the widest item
        fm = self.fontMetrics()
        max_w = self.width()
        for i in range(self.count()):
            w = fm.horizontalAdvance(self.itemText(i)) + 30  # padding + scrollbar
            if w > max_w:
                max_w = w
        self.view().setMinimumWidth(max_w)
        super().showPopup()


def make_combo(items: list[str], *, width: int = 130) -> QComboBox:
    cb = WidePopupComboBox()
    cb.setFont(_FONT)
    cb.setItemDelegate(_ComboItemDelegate(cb))
    cb.addItems(items)
    cb.setFixedHeight(_CTRL_H)
    cb.setFixedWidth(width)
    return cb


def style_combo(cb: QComboBox):
    """Apply compact row-height delegate and wide-popup behavior to an existing QComboBox."""
    cb.setItemDelegate(_ComboItemDelegate(cb))
    # Monkey-patch showPopup for wide dropdown
    original_showPopup = cb.showPopup

    def _wide_showPopup():
        fm = cb.fontMetrics()
        max_w = cb.width()
        for i in range(cb.count()):
            w = fm.horizontalAdvance(cb.itemText(i)) + 30
            if w > max_w:
                max_w = w
        cb.view().setMinimumWidth(max_w)
        original_showPopup()

    cb.showPopup = _wide_showPopup


# ── Wiring helpers ─────────────────────────────────────────────────────

def connect_checkbox_listbox(chk: QCheckBox, lb: QListWidget):
    """Wire checkbox to enable/disable listbox and clear selections on uncheck."""
    def _on_toggle(checked: bool):
        lb.setEnabled(checked)
        bg_color = "white" if checked else "#F0F0F0"
        lb.setStyleSheet(
            f"QListWidget {{ border: 1px solid #1E5BA8; background-color: {bg_color}; }}"
            "QListWidget::item { padding: 0px 2px; border: none; }"
            "QListWidget::item:selected { background-color: #A0C4E8; color: black; border: none; }"
        )
        if not checked:
            lb.clearSelection()
    chk.toggled.connect(_on_toggle)
