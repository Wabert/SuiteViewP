"""
Shared styled widget factories for audit tabs.

Provides blue-themed checkboxes (white checkmark), blue-bordered listboxes,
styled comboboxes with visible drop-down arrows, and wiring helpers.
All tabs should import from here for visual consistency.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QAbstractItemView, QStyledItemDelegate, QStyleOptionViewItem,
    QPushButton, QToolButton, QVBoxLayout, QWidget,
)
from PyQt6.QtGui import QFont
from suiteview.ui.checkmark_icon import CHECKMARK_PATH, ensure_checkmark
from suiteview.ui import tokens

_FONT = QFont(tokens.FONT_FAMILY_UI, tokens.FONT_SIZE_COMPACT_PT)
_ROW_H = tokens.ROW_HEIGHT_COMPACT
_CTRL_H = tokens.CONTROL_HEIGHT_COMPACT
_AUDIT_BLUE = tokens.AUDIT.primary
_AUDIT_BLUE_DARK = tokens.AUDIT_CHECKED_BORDER
_AUDIT_TINT = tokens.AUDIT.subtle
_AUDIT_PRESSED = tokens.AUDIT_PRESSED_SURFACE
_SELECTION = tokens.SELECTION
_DISABLED_BG = tokens.DISABLED_SURFACE
_SURFACE = "white"
_MUTED_BG = tokens.MUTED_CONTROL_SURFACE
_ACTIVE_HOVER = tokens.CONTROL_HOVER_SURFACE

# ── checkmark icon (created once, shared by all checkboxes) ────────────
_CHECKMARK_PATH = str(CHECKMARK_PATH)
_ensure_checkmark = ensure_checkmark


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
        f"QCheckBox::indicator {{ border: 1px solid {_AUDIT_BLUE}; width: 12px;"
        f" height: 12px; background-color: {_SURFACE}; }}"
        "QCheckBox::indicator:checked {"
        f"  background-color: {_AUDIT_BLUE}; border: 1px solid {_AUDIT_BLUE_DARK};"
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
    bg_color = _SURFACE if enabled else _DISABLED_BG
    lb.setStyleSheet(
        f"QListWidget {{ border: 1px solid {_AUDIT_BLUE}; background-color: {bg_color}; outline: none; }}"
        "QListWidget::item { padding: 0px 2px; border: none; }"
        f"QListWidget::item:selected {{ background-color: {_SELECTION}; color: black; border: none; }}"
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
                 height_rows: int | None = None, multi: bool = True,
                 show_search: bool = False, parent=None):
        super().__init__(parent)
        self._multi = multi
        self._show_search = show_search
        self._popup = QFrame(None, Qt.WindowType.Popup)
        self._popup.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._muted = False
        self.display = QLineEdit(self)
        self.display.setReadOnly(True)
        self.display.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.display.setFont(_FONT)
        self.display.setFixedSize(width, _CTRL_H)
        self.display.mousePressEvent = self._display_mouse_press_event
        layout.addWidget(self.display)

        self.button = QToolButton(self)
        self.button.setText("v")
        self.button.setFixedSize(18, _CTRL_H)
        self.button.clicked.connect(self.toggle_popup)
        layout.addWidget(self.button)
        self._apply_input_style()

        # Keep the widget exactly as wide as its contents so there is no gap
        # between the display box and the dropdown button.
        self.setFixedSize(width + 18, _CTRL_H)

        popup_layout = QVBoxLayout(self._popup)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        popup_layout.setSpacing(0)

        # ── Optional search + clear bar ──────────────────────────
        self.search_bar: QLineEdit | None = None
        if show_search:
            bar_row = QHBoxLayout()
            bar_row.setContentsMargins(2, 2, 2, 2)
            bar_row.setSpacing(4)

            self.search_bar = QLineEdit()
            self.search_bar.setPlaceholderText("Search…")
            self.search_bar.setFont(_FONT)
            self.search_bar.setFixedHeight(_CTRL_H)
            self.search_bar.setStyleSheet(
                f"QLineEdit {{ border: 1px solid {_AUDIT_BLUE}; padding: 0px 4px;"
                f" background: {_SURFACE}; }}"
            )
            self.search_bar.textChanged.connect(self._apply_filter)
            bar_row.addWidget(self.search_bar, 1)

            clear_btn = QPushButton("Clear")
            clear_btn.setFont(_FONT)
            clear_btn.setFixedHeight(_CTRL_H)
            clear_btn.setStyleSheet(
                f"QPushButton {{ border: 1px solid {_AUDIT_BLUE}; background: {_SURFACE};"
                f" color: {_AUDIT_BLUE}; padding: 0px 6px; }}"
                f"QPushButton:hover {{ background: {_AUDIT_TINT}; }}"
                f"QPushButton:pressed {{ background: {_AUDIT_PRESSED}; }}"
            )
            clear_btn.clicked.connect(self._clear_all)
            bar_row.addWidget(clear_btn)

            bar_widget = QWidget()
            bar_widget.setLayout(bar_row)
            popup_layout.addWidget(bar_widget)

        self.list_widget = make_listbox(
            [], height_rows=height_rows or max(len(items), 1),
            multi=multi, enabled=True)
        self.set_items(items)
        self.list_widget.itemSelectionChanged.connect(self._update_display_text)
        if not multi:
            # single-select: close the popup once the user picks an item
            self.list_widget.itemClicked.connect(lambda _i: self._popup.hide())
        popup_layout.addWidget(self.list_widget)

        self._popup.setFixedWidth(self.width())
        self._update_display_text()

    def set_items(self, items: list[str | tuple[str, str]]):
        """Replace the popup's items, preserving any still-valid selection."""
        previously = set(self.selected_values())
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for item in items:
            if isinstance(item, tuple):
                label, value = item
            else:
                label = value = item
            list_item = QListWidgetItem(label)
            list_item.setData(Qt.ItemDataRole.UserRole, value)
            self.list_widget.addItem(list_item)
            if value in previously:
                list_item.setSelected(True)
        self.list_widget.blockSignals(False)
        self._update_display_text()

    def _apply_input_style(self):
        bg = _MUTED_BG if self._muted else _SURFACE
        hover = _MUTED_BG if self._muted else _ACTIVE_HOVER
        self.display.setStyleSheet(
            f"QLineEdit {{ background: {bg}; border: 1px solid {_AUDIT_BLUE}; border-right: none;"
            " padding: 0px 4px; }"
            f"QLineEdit:hover {{ background: {hover}; }}"
        )
        self.button.setStyleSheet(
            f"QToolButton {{ background: {bg}; border: 1px solid {_AUDIT_BLUE}; border-left: none;"
            f" color: {_AUDIT_BLUE}; padding: 0px; }}"
            f"QToolButton:hover {{ background: {hover}; }}"
        )

    def set_muted(self, muted: bool):
        """Grey out the input to signal it is inactive (still usable)."""
        self._muted = bool(muted)
        self._apply_input_style()

    def _display_mouse_press_event(self, event):
        self.toggle_popup()
        event.accept()

    def _apply_filter(self, text: str):
        """Show only list items whose label contains the search text (case-insensitive)."""
        needle = text.strip().lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(bool(needle and needle not in item.text().lower()))

    def _clear_all(self):
        """Deselect all items and reset the search bar."""
        if self.search_bar is not None:
            self.search_bar.blockSignals(True)
            self.search_bar.clear()
            self.search_bar.blockSignals(False)
            self._apply_filter("")
        self.list_widget.blockSignals(True)
        self.list_widget.clearSelection()
        self.list_widget.blockSignals(False)
        self._update_display_text()


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
        # Reset search filter each time the popup opens
        if self.search_bar is not None:
            self.search_bar.blockSignals(True)
            self.search_bar.clear()
            self.search_bar.blockSignals(False)
            self._apply_filter("")
        self._popup.setFixedWidth(self._popup_width())
        self._popup.move(self.mapToGlobal(self.rect().bottomLeft()))
        self._popup.show()
        self._popup.raise_()
        if self.search_bar is not None:
            self.search_bar.setFocus(Qt.FocusReason.PopupFocusReason)
        else:
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
                           height_rows: int | None = None,
                           multi: bool = True,
                           show_search: bool = False) -> MultiSelectPopup:
    return MultiSelectPopup(items, width=width, height_rows=height_rows,
                            multi=multi, show_search=show_search)


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
        bg_color = _SURFACE if checked else _DISABLED_BG
        lb.setStyleSheet(
            f"QListWidget {{ border: 1px solid {_AUDIT_BLUE}; background-color: {bg_color}; }}"
            "QListWidget::item { padding: 0px 2px; border: none; }"
            f"QListWidget::item:selected {{ background-color: {_SELECTION}; color: black; border: none; }}"
        )
        if not checked:
            lb.clearSelection()
    chk.toggled.connect(_on_toggle)
