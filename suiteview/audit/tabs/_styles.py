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
    QCheckBox, QComboBox, QListWidget, QAbstractItemView, QStyledItemDelegate,
    QStyleOptionViewItem,
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
