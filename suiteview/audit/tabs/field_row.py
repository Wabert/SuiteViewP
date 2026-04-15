"""
FieldRow and FieldGrid — compact, dynamic-height filter field widgets.

FieldRow: a single filter field (grip + label + input + toggle) that can
          grow vertically when in *range* mode (adds a "to" input) or when
          a list is *pinned* inline.
FieldGrid: a free-form canvas with absolute positioning — fields can be
           placed at any (x, y) position and dragged anywhere, similar to
           a Visual Studio form designer.  Snap-to-grid keeps positioning
           tidy.  Overlapping controls are allowed.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QPoint, QSize, QRect, QEvent, QElapsedTimer, QMimeData
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QListWidget, QAbstractItemView, QFrame, QMenu,
    QMessageBox, QApplication, QSizePolicy, QToolBar,
)
from PyQt6.QtGui import QFont, QDrag, QMouseEvent, QPainter, QColor, QPen, QCursor, QPolygon

from ._styles import TightItemDelegate

logger = logging.getLogger(__name__)

# ── Styles ────────────────────────────────────────────────────────────

_MODES = ["contains", "regex", "combo", "list", "range"]

_FONT = QFont("Segoe UI", 8)
_FONT_BOLD = QFont("Segoe UI", 8, QFont.Weight.Bold)
_CTRL_H = 20          # compact control height
_LBL_W = 62           # label width — narrow
_INPUT_W = 90          # default input width — narrow

_TOGGLE_STYLE = (
    "QPushButton { font-size: 8pt; padding: 0px 4px;"
    " border: 1px solid #1E5BA8; border-radius: 2px;"
    " background-color: #E8F0FB; color: #1E5BA8; min-width: 44px; }"
    "QPushButton:hover { background-color: #C5D8F5; }"
)

_LIST_INPUT_STYLE = (
    "QLineEdit { font-size: 9pt; background-color: #E8F0FB;"
    " border: 1px solid #1E5BA8; border-radius: 2px;"
    " padding: 0px 3px; color: #1E5BA8; }"
    "QLineEdit:hover { background-color: #C5D8F5; }"
)

_TEXT_INPUT_STYLE = (
    "QLineEdit { font-size: 9pt; background-color: white;"
    " border: 1px solid #888; border-top: 2px solid #666;"
    " border-left: 2px solid #666; padding: 0px 3px; }"
)

_COMBO_STYLE = (
    "QComboBox { font-size: 9pt; background-color: white;"
    " border: 1px solid #888; border-top: 2px solid #666;"
    " border-left: 2px solid #666; padding: 0px 3px; }"
    "QComboBox::drop-down { border-left: 1px solid #888;"
    " width: 14px; subcontrol-position: right center; }"
    "QComboBox::down-arrow { image: none; border-left: 4px solid transparent;"
    " border-right: 4px solid transparent; border-top: 5px solid #444;"
    " width: 0px; height: 0px; margin-right: 2px; }"
    "QComboBox QAbstractItemView { border: 1px solid #888;"
    " background-color: white; selection-background-color: #A0C4E8;"
    " selection-color: black; outline: none; }"
    "QComboBox QAbstractItemView::item { padding: 0px 3px;"
    " min-height: 15px; max-height: 15px; }"
)

_GRIP_STYLE = (
    "QLabel { color: #bbb; font-size: 9pt; padding: 0px 1px;"
    " background: transparent; }"
    "QLabel:hover { color: #1E5BA8; }"
)

_PINNED_LIST_STYLE = (
    "QListWidget { border: 1px solid #1E5BA8; font-size: 8pt; }"
    "QListWidget::item { padding: 0px 3px; }"
    "QListWidget::item:selected { background-color: #A0C4E8;"
    " color: black; }"
)

_BTN_SMALL = (
    "QPushButton { font: 7pt 'Segoe UI'; padding: 0px 4px;"
    " border: 1px solid #aaa; border-radius: 2px;"
    " background-color: #f0f0f0; color: #333; }"
    "QPushButton:hover { background-color: #ddd; }"
)

_MAX_COMBO_ITEMS = 50
_PINNED_LIST_H = 120   # default pinned-list height

_DRAG_MIME = "application/x-fieldrow-key"

# Border colors — drawn in paintEvent, not via stylesheet (custom QWidget
# subclasses need QStyleOption for stylesheet class selectors to work).
_BORDER_COLOR = QColor("#1E5BA8")
_BORDER_COLOR_SELECTED = QColor("#1E5BA8")
_BG_COLOR = QColor("#f0f0f0")
_BG_COLOR_SELECTED = QColor("#E0E8F4")
_RESIZE_HANDLE_SIZE = 8   # resize grip area in bottom-right corner


# ── List popup ────────────────────────────────────────────────────────

class _ListPopup(QFrame):
    """Floating multi-select list popup with search, All/Clear/Pin."""

    def __init__(self, parent_widget, items: list[str],
                 selected: set[str], on_close_cb, on_pin_cb, *,
                 field_name: str = ""):
        super().__init__(parent_widget.window(),
                         Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._on_close_cb = on_close_cb
        self._on_pin_cb = on_pin_cb
        self._all_items = items
        self._close_timer = QElapsedTimer()
        self._pinned = False
        self.setStyleSheet(
            "QFrame { background-color: white; border: 1px solid #1E5BA8; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)

        # Search box
        self.search = QLineEdit()
        self.search.setFont(QFont("Segoe UI", 8))
        self.search.setPlaceholderText("Search...")
        self.search.setFixedHeight(18)
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet(
            "QLineEdit { border: 1px solid #1E5BA8; padding: 0px 3px; }"
            "QLineEdit QToolButton { border: none; margin: 0px;"
            " padding: 0px; }")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        # All / Clear / Pin button row
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(2)
        for text, slot in [("All", self._select_all),
                           ("Clear", self._clear_all)]:
            b = QPushButton(text)
            b.setFixedHeight(16)
            b.setStyleSheet(_BTN_SMALL)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        self.btn_pin = QPushButton("Pin")
        self.btn_pin.setFixedHeight(16)
        self.btn_pin.setStyleSheet(_BTN_SMALL)
        self.btn_pin.clicked.connect(self._do_pin)
        btn_row.addWidget(self.btn_pin)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Listbox
        self.listbox = QListWidget()
        self.listbox.setFont(QFont("Segoe UI", 8))
        self.listbox.setItemDelegate(TightItemDelegate(self.listbox))
        self.listbox.setUniformItemSizes(True)
        self.listbox.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection)
        self.listbox.setStyleSheet(
            "QListWidget { border: none; }"
            "QListWidget::item { padding: 0px 3px; }"
            "QListWidget::item:selected { background-color: #A0C4E8;"
            " color: black; }")
        self.listbox.addItems(items)
        for i in range(self.listbox.count()):
            if self.listbox.item(i).text() in selected:
                self.listbox.item(i).setSelected(True)
        lay.addWidget(self.listbox, 1)

        # Field name at bottom
        if field_name:
            lbl = QLabel(field_name)
            lbl.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            lbl.setStyleSheet(
                "background-color: #e0e0e0; color: #333;"
                " padding: 1px 3px; border-top: 1px solid #ccc;")
            lay.addWidget(lbl)

    def _do_pin(self):
        """Pin: transfer selection + items into the inline widget."""
        self._pinned = True
        self._on_pin_cb(self._all_items, self.selected_values())
        self.close()

    def _select_all(self):
        for i in range(self.listbox.count()):
            item = self.listbox.item(i)
            if not item.isHidden():
                item.setSelected(True)

    def _clear_all(self):
        self.listbox.clearSelection()

    def _filter(self, text: str):
        filt = text.strip().lower()
        for i in range(self.listbox.count()):
            item = self.listbox.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def selected_values(self) -> list[str]:
        return [self.listbox.item(i).text()
                for i in range(self.listbox.count())
                if self.listbox.item(i).isSelected()]

    def hideEvent(self, event):
        super().hideEvent(event)
        self._close_timer.start()
        if not self._pinned:
            self._on_close_cb(self.selected_values())


# ── FieldRow widget ──────────────────────────────────────────────────

class FieldRow(QWidget):
    """Self-contained filter field with dynamic height.

    Layout (vertical):
        [control row]  grip | label | txt/cmb | mode_lbl | txt_hi
        [pinned list]  optional inline QListWidget (list mode, pinned)
    """

    def __init__(self, field_key: str, label_text: str, placeholder: str,
                 registry_info: tuple[str, str, str] | None = None, *,
                 input_width: int = _INPUT_W, parent: QWidget | None = None):
        super().__init__(parent)
        self.field_key = field_key
        self._placeholder = placeholder
        self._registry_info = registry_info
        self._list_popup: _ListPopup | None = None
        self._list_selected: list[str] = []
        self._pinned = False
        self._pinned_items: list[str] = []
        self._pre_pin_size: tuple[int, int] | None = None
        self._pre_range_size: tuple[int, int] | None = None

        # Display options
        self._display_name_shown = False   # stacked: name on top, input below
        self._format_hidden = False        # hide mode label (contains/regex/list...)

        # No fixed height — grows with content
        sp = self.sizePolicy()
        sp.setVerticalPolicy(QSizePolicy.Policy.Preferred)
        self.setSizePolicy(sp)

        self._selected = False
        # Background handled in paintEvent; keep child widgets transparent
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        # ── Resize state ────────────────────────────────────────────
        self._resizing = False
        self._resize_start: QPoint | None = None
        self._resize_origin_size: QSize | None = None
        self.setMouseTracking(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(3, 3, 3, 3)  # inset so border is visible
        outer.setSpacing(1)

        # ── Display-name row (hidden until Display Name mode) ────────
        self._display_name_row = QHBoxLayout()
        self._display_name_row.setContentsMargins(0, 0, 0, 0)
        self._display_name_row.setSpacing(2)
        # Spacer to align with grip width
        self._dn_spacer = QLabel("")
        self._dn_spacer.setFixedSize(12, _CTRL_H)
        self._display_name_row.addWidget(self._dn_spacer)
        self._dn_lbl = QLabel(label_text)
        self._dn_lbl.setFont(_FONT_BOLD)
        self._dn_lbl.setFixedHeight(_CTRL_H)
        self._dn_lbl.setStyleSheet("QLabel { color: #1E5BA8; }")
        self._display_name_row.addWidget(self._dn_lbl)
        self._display_name_row.addStretch()
        outer.addLayout(self._display_name_row)
        # Initially hidden
        self._dn_spacer.setVisible(False)
        self._dn_lbl.setVisible(False)

        # ── Control row ──────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setContentsMargins(0, 0, 0, 0)
        ctrl.setSpacing(2)

        self._grip = QLabel("⋮⋮")
        self._grip.setFont(QFont("Segoe UI", 8))
        self._grip.setFixedSize(12, _CTRL_H)
        self._grip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grip.setStyleSheet(_GRIP_STYLE)
        self._grip.setCursor(Qt.CursorShape.OpenHandCursor)
        ctrl.addWidget(self._grip)

        self._lbl = QLabel(label_text)
        self._lbl.setFont(_FONT_BOLD)
        self._lbl.setFixedWidth(_LBL_W)
        self._lbl.setFixedHeight(_CTRL_H)
        ctrl.addWidget(self._lbl)

        self.txt = QLineEdit()
        self.txt.setFont(_FONT)
        self.txt.setFixedHeight(_CTRL_H)
        self.txt.setFixedWidth(input_width)
        self.txt.setPlaceholderText(placeholder)
        self.txt.setStyleSheet(_TEXT_INPUT_STYLE)
        self.txt.installEventFilter(self)
        ctrl.addWidget(self.txt)

        self.cmb = QComboBox()
        self.cmb.setFont(_FONT)
        self.cmb.setFixedHeight(_CTRL_H)
        self.cmb.setFixedWidth(input_width)
        self.cmb.setEditable(True)
        self.cmb.setStyleSheet(_COMBO_STYLE)
        self.cmb.setVisible(False)
        ctrl.addWidget(self.cmb)

        # Mode indicator label (right-click label to change mode)
        self._mode_lbl = QLabel("contains")
        self._mode_lbl.setFont(QFont("Segoe UI", 7))
        self._mode_lbl.setFixedHeight(_CTRL_H)
        self._mode_lbl.setStyleSheet(
            "QLabel { color: #1E5BA8; padding: 0px 4px; }")
        self._mode_idx = 0
        ctrl.addWidget(self._mode_lbl)

        # Range "to" field — inline, right of the mode label (hidden until range)
        self.txt_hi = QLineEdit()
        self.txt_hi.setFont(_FONT)
        self.txt_hi.setFixedHeight(_CTRL_H)
        self.txt_hi.setFixedWidth(input_width)
        self.txt_hi.setPlaceholderText("to")
        self.txt_hi.setStyleSheet(_TEXT_INPUT_STYLE)
        self.txt_hi.setVisible(False)
        ctrl.addWidget(self.txt_hi)

        ctrl.addStretch()
        outer.addLayout(ctrl)

        # ── Pinned list area (hidden until pinned) ───────────────────
        self._pin_frame = QFrame()
        self._pin_frame.setVisible(False)
        pin_sp = self._pin_frame.sizePolicy()
        pin_sp.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        pin_sp.setVerticalStretch(1)
        self._pin_frame.setSizePolicy(pin_sp)
        pin_lay = QVBoxLayout(self._pin_frame)
        pin_lay.setContentsMargins(2, 0, 2, 2)  # small margin inside border
        pin_lay.setSpacing(1)

        # Search row
        self._pin_search = QLineEdit()
        self._pin_search.setFont(QFont("Segoe UI", 7))
        self._pin_search.setPlaceholderText("Search...")
        self._pin_search.setFixedHeight(16)
        self._pin_search.setClearButtonEnabled(True)
        self._pin_search.setStyleSheet(
            "QLineEdit { border: 1px solid #1E5BA8; padding: 0px 2px;"
            " font-size: 7pt; }"
            "QLineEdit QToolButton { border: none; margin: 0; padding: 0; }")
        self._pin_search.textChanged.connect(self._pin_filter)
        pin_lay.addWidget(self._pin_search)

        # Button row (All / Clear / Unpin)
        pin_btn_row = QHBoxLayout()
        pin_btn_row.setContentsMargins(0, 0, 0, 0)
        pin_btn_row.setSpacing(2)
        for txt, slot in [("All", self._pin_select_all),
                          ("Clear", self._pin_clear_all)]:
            b = QPushButton(txt)
            b.setFixedHeight(16)
            b.setStyleSheet(_BTN_SMALL)
            b.clicked.connect(slot)
            pin_btn_row.addWidget(b)

        self._btn_unpin = QPushButton("Unpin")
        self._btn_unpin.setFixedHeight(16)
        self._btn_unpin.setStyleSheet(_BTN_SMALL)
        self._btn_unpin.clicked.connect(self._unpin_list)
        pin_btn_row.addWidget(self._btn_unpin)
        pin_btn_row.addStretch()
        pin_lay.addLayout(pin_btn_row)

        self._pin_listbox = QListWidget()
        self._pin_listbox.setFont(QFont("Segoe UI", 8))
        self._pin_listbox.setItemDelegate(TightItemDelegate(self._pin_listbox))
        self._pin_listbox.setUniformItemSizes(True)
        self._pin_listbox.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection)
        self._pin_listbox.setStyleSheet(_PINNED_LIST_STYLE)
        self._pin_listbox.setMinimumHeight(40)
        # Let the listbox stretch to fill available vertical space
        sp_lb = self._pin_listbox.sizePolicy()
        sp_lb.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        sp_lb.setVerticalStretch(1)
        self._pin_listbox.setSizePolicy(sp_lb)
        self._pin_listbox.itemSelectionChanged.connect(
            self._on_pin_selection_changed)
        pin_lay.addWidget(self._pin_listbox, 1)

        outer.addWidget(self._pin_frame, 1)  # stretch=1 so pinned list fills space

        # ── Right-click context menu on label ─────────────────────────
        self._lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._lbl.customContextMenuRequested.connect(self._show_label_menu)

        # ── Drag state ───────────────────────────────────────────────
        self._drag_start: QPoint | None = None

    # ── Selection ────────────────────────────────────────────────────

    @property
    def selected(self) -> bool:
        return self._selected

    @selected.setter
    def selected(self, val: bool):
        self._selected = val
        self.update()  # trigger repaint for border/bg change

    # ── Resize handle helpers ────────────────────────────────────────

    def _resize_rect(self) -> QRect:
        """Return the bottom-right resize grip rectangle."""
        s = _RESIZE_HANDLE_SIZE
        return QRect(self.width() - s, self.height() - s, s, s)

    def _in_resize_zone(self, pos: QPoint) -> bool:
        return self._resize_rect().contains(pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Fill background
        bg = _BG_COLOR_SELECTED if self._selected else _BG_COLOR
        p.fillRect(self.rect(), bg)

        # Draw border
        border_w = 2 if self._selected else 1
        pen = QPen(_BORDER_COLOR_SELECTED if self._selected else _BORDER_COLOR)
        pen.setWidth(border_w)
        p.setPen(pen)
        # Inset by pen-width so the stroke is fully visible
        inset = border_w
        p.drawRect(self.rect().adjusted(inset, inset, -inset, -inset))

        # Resize handle triangle in bottom-right corner
        p.setPen(Qt.PenStyle.NoPen)
        handle_color = QColor("#1E5BA8") if self._selected else QColor("#8899BB")
        p.setBrush(handle_color)
        s = _RESIZE_HANDLE_SIZE
        rx, ry = self.width() - s, self.height() - s
        p.drawPolygon(QPolygon([
            QPoint(rx + s, ry),
            QPoint(rx + s, ry + s),
            QPoint(rx, ry + s),
        ]))
        p.end()

    # ── Mode ─────────────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        return _MODES[self._mode_idx]

    @mode.setter
    def mode(self, value: str):
        if value in _MODES:
            self.set_mode_idx(_MODES.index(value))

    @property
    def mode_idx(self) -> int:
        return self._mode_idx

    def _cycle_mode(self, *_args):
        idx = (self._mode_idx + 1) % len(_MODES)
        self.set_mode_idx(idx)

    def set_mode_idx(self, idx: int):
        prev_mode = _MODES[self._mode_idx] if hasattr(self, '_mode_idx') else None
        self._mode_idx = idx
        self._mode_lbl.setText(_MODES[idx])
        mode = _MODES[idx]

        # Close floating popup when switching away from list
        if mode != "list" and self._list_popup is not None:
            self._list_popup.close()
            self._list_popup = None

        # Collapse pinned list when leaving list mode
        if mode != "list" and self._pinned:
            self._unpin_list()

        # ── Range auto-resize ─────────────────────────────────────
        if mode == "range" and prev_mode != "range":
            # Save original size and widen to fit both from/to fields
            self._pre_range_size = (self.width(), self.height())
            extra = _INPUT_W + 8  # width of the "to" field + spacing
            self.setFixedSize(self.width() + extra, self.height())
        elif mode != "range" and prev_mode == "range":
            # Restore original size
            if self._pre_range_size:
                w, h = self._pre_range_size
                self.setFixedSize(w, h)
                self._pre_range_size = None

        # Visibility
        self.txt.setVisible(mode in ("contains", "regex", "range", "list"))
        self.cmb.setVisible(mode == "combo")
        self.txt_hi.setVisible(mode == "range")

        if mode == "combo":
            self._populate_combo()

        if mode == "list":
            self.txt.setReadOnly(True)
            self.txt.setStyleSheet(_LIST_INPUT_STYLE)
            sel = self._list_selected
            self.txt.setText(f"{len(sel)} selected" if sel else "")
            self.txt.setPlaceholderText("0 selected")
        else:
            self.txt.setReadOnly(False)
            self.txt.setStyleSheet(_TEXT_INPUT_STYLE)
            if mode != "range":
                self.txt.setPlaceholderText(self._placeholder)

        if mode == "range":
            self.txt.setPlaceholderText("from")

    # ── Pinned-list helpers ──────────────────────────────────────────

    def _pin_list(self, items: list[str], selected: list[str]):
        """Embed the list inline under the control row."""
        self._pinned = True
        self._pinned_items = items
        self._list_selected = selected

        # Save original size before expanding
        self._pre_pin_size = (self.width(), self.height())

        self._pin_listbox.blockSignals(True)
        self._pin_listbox.clear()
        self._pin_listbox.addItems(items)
        sel_set = set(selected)
        for i in range(self._pin_listbox.count()):
            if self._pin_listbox.item(i).text() in sel_set:
                self._pin_listbox.item(i).setSelected(True)
        self._pin_listbox.blockSignals(False)

        # Hide the input row (txt + mode label) — not needed while pinned
        self.txt.setVisible(False)
        self._mode_lbl.setVisible(False)

        self._pin_frame.setVisible(True)
        self._update_list_label()

        # Auto-resize to show ~10 rows
        row_h = 16  # approximate height per list item
        list_h = min(len(items), 10) * row_h + 24  # +24 for search/button row
        ctrl_h = _CTRL_H + 6  # grip row + margins
        new_h = ctrl_h + list_h + 10  # +10 for margins/border
        cur_w = max(self.width(), 260)
        self.setFixedSize(cur_w, new_h)

    def _unpin_list(self):
        """Collapse the inline list back to the compact row."""
        # Capture current selection before hiding
        self._list_selected = [
            self._pin_listbox.item(i).text()
            for i in range(self._pin_listbox.count())
            if self._pin_listbox.item(i).isSelected()]
        self._pinned = False
        self._pin_frame.setVisible(False)

        # Restore input row
        self.txt.setVisible(True)
        self._mode_lbl.setVisible(True)

        # Restore original size
        if hasattr(self, '_pre_pin_size') and self._pre_pin_size:
            w, h = self._pre_pin_size
            self.setFixedSize(w, h)
            self._pre_pin_size = None
        else:
            # Fallback: shrink to natural height
            self.setMaximumSize(16777215, 16777215)  # QWIDGETSIZE_MAX
            self.adjustSize()

        self._update_list_label()

    def _on_pin_selection_changed(self):
        self._list_selected = [
            self._pin_listbox.item(i).text()
            for i in range(self._pin_listbox.count())
            if self._pin_listbox.item(i).isSelected()]
        self._update_list_label()

    def _pin_filter(self, text: str):
        filt = text.strip().lower()
        for i in range(self._pin_listbox.count()):
            item = self._pin_listbox.item(i)
            item.setHidden(filt not in item.text().lower() if filt else False)

    def _pin_select_all(self):
        for i in range(self._pin_listbox.count()):
            item = self._pin_listbox.item(i)
            if not item.isHidden():
                item.setSelected(True)

    def _pin_clear_all(self):
        self._pin_listbox.clearSelection()

    def _update_list_label(self):
        n = len(self._list_selected)
        self.txt.setText(f"{n} selected" if n else "")

    # ── Value access (for query builder) ─────────────────────────────

    def get_value(self) -> str:
        if self.mode == "combo":
            return self.cmb.currentText().strip()
        return self.txt.text().strip()

    def get_range(self) -> tuple[str, str]:
        return (self.txt.text().strip(), self.txt_hi.text().strip())

    def get_list_values(self) -> list[str]:
        return list(self._list_selected)

    # ── State persistence ────────────────────────────────────────────

    def get_state(self) -> dict:
        mode = self.mode
        s: dict = {"mode": self.mode_idx, "pinned": self._pinned,
                   "display_name_shown": self._display_name_shown,
                   "format_hidden": self._format_hidden}
        if mode == "combo":
            s["val"] = self.cmb.currentText()
        elif mode == "range":
            s["val"] = self.txt.text()
            s["hi"] = self.txt_hi.text()
        elif mode == "list":
            s["val"] = ""
            s["list_selected"] = list(self._list_selected)
            if self._pinned:
                s["pinned_items"] = list(self._pinned_items)
        else:
            s["val"] = self.txt.text()
        return s

    def set_state(self, s: dict):
        idx = s.get("mode", 0)
        self.set_mode_idx(idx)
        mode = _MODES[idx]
        if mode == "combo":
            self.cmb.setCurrentText(s.get("val", ""))
        elif mode == "range":
            self.txt.setText(s.get("val", ""))
            self.txt_hi.setText(s.get("hi", ""))
        elif mode == "list":
            self._list_selected = s.get("list_selected", [])
            self._update_list_label()
            if s.get("pinned") and s.get("pinned_items"):
                self._pin_list(s["pinned_items"], self._list_selected)
        else:
            self.txt.setText(s.get("val", ""))
        # Restore display options
        self._display_name_shown = s.get("display_name_shown", False)
        self._format_hidden = s.get("format_hidden", False)
        if self._display_name_shown or self._format_hidden:
            self._apply_display_options()

    # ── Combo population ─────────────────────────────────────────────

    def _populate_combo(self):
        from ..shared_field_registry import get_field_id, get_values
        prev = self.cmb.currentText()
        self.cmb.clear()
        self.cmb.addItem("")
        if not self._registry_info:
            return
        table, column, _ = self._registry_info
        fid = get_field_id(table, column)
        if fid is not None:
            for val, _ in get_values(fid)[:_MAX_COMBO_ITEMS]:
                self.cmb.addItem(val)
        idx = self.cmb.findText(prev)
        if idx >= 0:
            self.cmb.setCurrentIndex(idx)

    # ── List popup ───────────────────────────────────────────────────

    def toggle_list_popup(self):
        if self._list_popup is not None and self._list_popup.isVisible():
            self._list_popup.close()
            self._list_popup = None
            return

        if (self._list_popup is not None
                and self._list_popup._close_timer.isValid()
                and self._list_popup._close_timer.elapsed() < 150):
            self._list_popup = None
            return

        from ..shared_field_registry import get_field_id, get_values
        if not self._registry_info:
            return
        table, column, display = self._registry_info

        items: list[str] = []
        fid = get_field_id(table, column)
        if fid is not None:
            items = sorted([v for v, _c in get_values(fid)],
                           reverse=True)

        if not items:
            QMessageBox.information(
                self, "No Registered Values",
                f"No unique values registered for {table}.{column}.\n"
                "Right-click the field and choose "
                "\"Find & Register Unique Values\" first.")
            return

        selected_set = set(self._list_selected)

        def _on_close(sel_list):
            self._list_selected = sel_list
            self._update_list_label()

        def _on_pin(all_items, sel_list):
            self._pin_list(all_items, sel_list)

        popup = _ListPopup(self.txt, items, selected_set,
                           _on_close, _on_pin, field_name=display)
        self._list_popup = popup

        g = self.txt.mapToGlobal(QPoint(0, self.txt.height()))
        screen = self.txt.screen().availableGeometry()
        pw = max(self.txt.width(), 180)
        ph = 280
        if g.y() + ph > screen.bottom():
            g = self.txt.mapToGlobal(QPoint(0, -ph))
        popup.setFixedWidth(pw)
        popup.resize(pw, ph)
        popup.move(g)
        popup.show()

    # ── Event filter (click txt in list mode) ────────────────────────

    def eventFilter(self, obj, event):
        if (obj is self.txt
                and event.type() == QEvent.Type.MouseButtonPress
                and self.mode == "list"
                and not self._pinned):
            self.toggle_list_popup()
            return True
        return super().eventFilter(obj, event)

    # ── Context menu (right-click on label) ─────────────────────────

    _MENU_STYLE = (
        "QMenu { background-color: white; border: 1px solid #1E5BA8;"
        "  font-size: 9pt; }"
        "QMenu::item { padding: 3px 16px; }"
        "QMenu::item:selected { background-color: #A0C4E8; color: black; }"
        "QMenu::item:disabled { color: #999; }"
        "QMenu::separator { height: 1px; background: #C8D8E8;"
        "  margin: 2px 4px; }")

    def _show_label_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(self._MENU_STYLE)

        # Header: field_key or Table.Column (disabled, just informational)
        if self._registry_info:
            table, column, _ = self._registry_info
            header = menu.addAction(f"{table}.{column}")
            header.setEnabled(False)
            menu.addSeparator()
        elif self.field_key:
            header = menu.addAction(self.field_key)
            header.setEnabled(False)
            menu.addSeparator()

        # Mode actions — checkmark on current
        mode_actions = []
        for i, mode_name in enumerate(_MODES):
            act = menu.addAction(mode_name)
            act.setCheckable(True)
            act.setChecked(i == self._mode_idx)
            mode_actions.append((act, i))

        menu.addSeparator()

        # ── Display submenu ──────────────────────────────────────────
        display_menu = menu.addMenu("Display")
        display_menu.setStyleSheet(self._MENU_STYLE)

        act_dn_toggle = display_menu.addAction("Display Name")
        act_dn_toggle.setCheckable(True)
        act_dn_toggle.setChecked(self._display_name_shown)

        act_fmt_toggle = display_menu.addAction("Remove Format Display")
        act_fmt_toggle.setCheckable(True)
        act_fmt_toggle.setChecked(self._format_hidden)

        # Display Name edit (always available)
        act_display_name = menu.addAction("Update Display Name")

        # Remove from tab (available on dynamic tabs)
        act_remove = menu.addAction("Remove from Tab")

        menu.addSeparator()

        # Registry actions (only if registry_info is set)
        act_find = act_open = None
        if self._registry_info:
            table, column, _ = self._registry_info
            act_find = menu.addAction(
                f"Find && Register Unique Values  ({table}.{column})")
            act_open = menu.addAction("Open Unique Value Registry")
            menu.addSeparator()

        act_regex = menu.addAction("Open Regex / LIKE Help")

        chosen = menu.exec(self._lbl.mapToGlobal(pos))
        if chosen is None:
            return

        # Check mode actions
        for act, idx in mode_actions:
            if chosen is act:
                self.set_mode_idx(idx)
                return

        if chosen is act_display_name:
            self._edit_display_name()
        elif chosen is act_remove:
            self._remove_from_tab()
        elif chosen is act_dn_toggle:
            self._toggle_display_name_mode()
        elif chosen is act_fmt_toggle:
            self._toggle_format_display()
        elif chosen is act_find:
            self._find_and_register()
        elif chosen is act_open:
            self._open_registry()
        elif chosen is act_regex:
            self._show_regex_help()

    def _edit_display_name(self):
        """Show a dialog to update the display name of this field."""
        from PyQt6.QtWidgets import QInputDialog
        current = self._lbl.text()
        new_name, ok = QInputDialog.getText(
            self, "Update Display Name",
            "Display name:", text=current)
        if ok and new_name.strip():
            new_name = new_name.strip()
            self._lbl.setText(new_name)
            # Notify the parent DynamicGroup if it has update_display_name
            grid = self.parent()
            if grid:
                tab = grid.parent()
                if tab:
                    scroll = tab.parent()
                    if scroll:
                        group = scroll.parent()
                        if hasattr(group, 'update_display_name'):
                            group.update_display_name(self.field_key, new_name)
            # Also update the stacked display-name label
            self._dn_lbl.setText(new_name)

    def _toggle_display_name_mode(self):
        """Toggle stacked display-name mode: name on top, input below."""
        self._display_name_shown = not self._display_name_shown
        self._apply_display_options()

    def _toggle_format_display(self):
        """Toggle visibility of the format/mode label (contains, regex, etc.)."""
        self._format_hidden = not self._format_hidden
        self._apply_display_options()

    def _apply_display_options(self):
        """Apply current display option state to the widget layout."""
        # Display Name row
        self._dn_spacer.setVisible(self._display_name_shown)
        self._dn_lbl.setVisible(self._display_name_shown)
        # In stacked mode, hide the inline label — it's shown in the row above
        self._lbl.setVisible(not self._display_name_shown)
        # Format display
        if self._format_hidden:
            self._mode_lbl.setVisible(False)
        else:
            # Restore mode_lbl visibility based on pinned state
            self._mode_lbl.setVisible(not self._pinned)

    def _remove_from_tab(self):
        """Remove this field from the tab."""
        grid = self.parent()
        if grid and hasattr(grid, 'parent'):
            tab = grid.parent()
            if tab and hasattr(tab, 'parent'):
                scroll = tab.parent()
                if scroll and hasattr(scroll, 'remove_field'):
                    scroll.remove_field(self.field_key)
                    return
        # Fallback: just remove from grid
        if grid and hasattr(grid, '_rows'):
            if self in grid._rows:
                grid._rows.remove(self)
            if self.field_key in grid._field_map:
                del grid._field_map[self.field_key]
            grid._positions.pop(self.field_key, None)
            grid._sizes.pop(self.field_key, None)
            if self in grid._selection:
                grid._selection.remove(self)
            self.setParent(None)
            self.deleteLater()
            if hasattr(grid, '_update_canvas_bounds'):
                grid._update_canvas_bounds()

    def _show_regex_help(self):
        from .tai_all_tab import _RegexHelpDialog
        dlg = _RegexHelpDialog(self)
        dlg.exec()

    def _find_and_register(self):
        from ..shared_field_registry import fetch_and_register
        if not self._registry_info:
            return
        table, column, display = self._registry_info
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            rows = fetch_and_register(table, column, display)
            QApplication.restoreOverrideCursor()
            QMessageBox.information(
                self, "Unique Values Registered",
                f"{table}.{column}:  {len(rows)} distinct values found.")
            from ..unique_value_registry_window import UniqueValueRegistryWindow
            if (UniqueValueRegistryWindow._instance is not None
                    and UniqueValueRegistryWindow._instance.isVisible()):
                UniqueValueRegistryWindow._instance.refresh_and_select(
                    table, column)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(
                self, "Query Error",
                f"Failed to query unique values:\n\n{exc}")

    def _open_registry(self):
        from ..unique_value_registry_window import UniqueValueRegistryWindow
        UniqueValueRegistryWindow.show_instance(parent=None)

    # ── Drag support (initiated from the grip) ───────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # Resize handle takes priority
            if self._in_resize_zone(event.pos()):
                self._resizing = True
                self._resize_start = event.globalPosition().toPoint()
                self._resize_origin_size = self.size()
                return
            # Drag grip
            grip_rect = self._grip.geometry()
            if grip_rect.contains(event.pos()):
                self._drag_start = event.pos()
                self._grip.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
            # Selection (notify grid)
            grid = self.parent()
            if hasattr(grid, '_handle_field_click'):
                ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                grid._handle_field_click(self, ctrl)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Live resize
        if self._resizing and self._resize_start is not None:
            delta = event.globalPosition().toPoint() - self._resize_start
            new_w = max(self._resize_origin_size.width() + delta.x(), 120)
            new_h = max(self._resize_origin_size.height() + delta.y(), _CTRL_H)
            self.setFixedSize(new_w, new_h)
            return
        # Drag from grip
        if (self._drag_start is not None
                and (event.pos() - self._drag_start).manhattanLength() > 6):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(_DRAG_MIME, self.field_key.encode())
            drag.setMimeData(mime)
            pix = self.grab()
            drag.setPixmap(pix)
            hotspot = event.pos()
            drag.setHotSpot(hotspot)
            # Tell the parent grid where the grab happened relative to widget
            grid = self.parent()
            if hasattr(grid, '_drag_hotspot'):
                grid._drag_hotspot = hotspot
            self._drag_start = None
            self._grip.setCursor(Qt.CursorShape.OpenHandCursor)
            drag.exec(Qt.DropAction.MoveAction)
            return
        # Cursor hint for resize zone
        if self._in_resize_zone(event.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._resizing:
            self._resizing = False
            self._resize_start = None
            self._resize_origin_size = None
            # Notify grid to persist the new size
            grid = self.parent()
            if hasattr(grid, '_update_canvas_bounds'):
                grid._update_canvas_bounds()
            return
        self._drag_start = None
        self._grip.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


# ── FieldGrid (free-form canvas) ─────────────────────────────────────

_GRID_SNAP = 8         # snap-to-grid increment in pixels
_DEFAULT_COL_W = 280   # default column width for initial placement
_DEFAULT_ROW_H = 32    # default row height for initial placement
_CANVAS_MIN_H = 400    # minimum canvas height

_TOOLBAR_BTN_STYLE = (
    "QPushButton { font: 7pt 'Segoe UI'; padding: 1px 6px;"
    " border: 1px solid #1E5BA8; border-radius: 2px;"
    " background-color: #E8F0FB; color: #1E5BA8; }"
    "QPushButton:hover { background-color: #C5D8F5; }"
    "QPushButton:disabled { background-color: #f0f0f0;"
    " color: #aaa; border-color: #ccc; }"
)


class FieldGrid(QWidget):
    """Free-form canvas — fields can be placed at any (x, y) position.

    Supports drag-and-drop repositioning with snap-to-grid.  Controls can
    overlap.  Behaves like a Visual Studio form designer surface.
    Multi-select with Ctrl+click, toolbar for alignment operations.
    """

    def __init__(self, columns: int = 2, parent: QWidget | None = None):
        super().__init__(parent)
        self._cols = columns          # used for default placement only
        self._rows: list[FieldRow] = []
        self._field_map: dict[str, FieldRow] = {}
        self._positions: dict[str, tuple[int, int]] = {}   # field_key → (x, y)
        self._sizes: dict[str, tuple[int, int]] = {}       # field_key → (w, h)
        self._selection: list[FieldRow] = []                # multi-select list

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        # ── Toolbar ──────────────────────────────────────────────────
        tb = QHBoxLayout()
        tb.setContentsMargins(2, 2, 2, 0)
        tb.setSpacing(4)

        self._btn_align_left = QPushButton("⬏ Align Left")
        self._btn_align_left.setFixedHeight(18)
        self._btn_align_left.setStyleSheet(_TOOLBAR_BTN_STYLE)
        self._btn_align_left.setToolTip(
            "Align selected controls to the left edge of the leftmost one")
        self._btn_align_left.setEnabled(False)
        self._btn_align_left.clicked.connect(self._align_left)
        tb.addWidget(self._btn_align_left)

        self._btn_align_top = QPushButton("⬑ Align Top")
        self._btn_align_top.setFixedHeight(18)
        self._btn_align_top.setStyleSheet(_TOOLBAR_BTN_STYLE)
        self._btn_align_top.setToolTip(
            "Align selected controls to the top edge of the topmost one")
        self._btn_align_top.setEnabled(False)
        self._btn_align_top.clicked.connect(self._align_top)
        tb.addWidget(self._btn_align_top)

        self._lbl_sel = QLabel("")
        self._lbl_sel.setFont(QFont("Segoe UI", 7))
        self._lbl_sel.setStyleSheet("color: #666;")
        tb.addWidget(self._lbl_sel)

        tb.addStretch()
        root.addLayout(tb)

        # ── Canvas area ──────────────────────────────────────────────
        self._canvas = QWidget(self)
        self._canvas.setMinimumHeight(_CANVAS_MIN_H)
        self._canvas.setAcceptDrops(True)
        # Forward drop events from canvas to self
        self._canvas.dragEnterEvent = self._canvas_dragEnterEvent
        self._canvas.dragMoveEvent = self._canvas_dragMoveEvent
        self._canvas.dragLeaveEvent = self._canvas_dragLeaveEvent
        self._canvas.dropEvent = self._canvas_dropEvent
        self._canvas.mousePressEvent = self._canvas_mousePressEvent
        self._canvas.mouseMoveEvent = self._canvas_mouseMoveEvent
        self._canvas.mouseReleaseEvent = self._canvas_mouseReleaseEvent
        root.addWidget(self._canvas, 1)

        # Visual guide during drag
        self._drop_pos: QPoint | None = None
        self._drag_hotspot: QPoint = QPoint(0, 0)

        # Ghost rectangle shown during drag
        self._ghost = QFrame(self._canvas)
        self._ghost.setStyleSheet(
            "background-color: rgba(30, 91, 168, 30);"
            " border: 1px dashed #1E5BA8;")
        self._ghost.hide()

        # Rubber-band rectangle for lasso selection
        self._rubber = QFrame(self._canvas)
        self._rubber.setStyleSheet(
            "background-color: rgba(30, 91, 168, 25);"
            " border: 1px dashed #1E5BA8;")
        self._rubber.hide()
        self._rubber.raise_()
        self._rubber_origin: QPoint | None = None

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _snap(val: int) -> int:
        """Snap a coordinate to the nearest grid point."""
        return round(val / _GRID_SNAP) * _GRID_SNAP

    def _default_position(self, index: int) -> tuple[int, int]:
        """Return a default (x, y) for field at *index* in a 2-column grid."""
        col = index % self._cols
        row = index // self._cols
        x = col * _DEFAULT_COL_W + 4
        y = row * _DEFAULT_ROW_H
        return (self._snap(x), self._snap(y))

    def _apply_positions(self):
        """Move every field widget to its stored (x, y) position and size."""
        max_y = _CANVAS_MIN_H
        for row in self._rows:
            x, y = self._positions.get(row.field_key,
                                       self._default_position(
                                           self._rows.index(row)))
            row.setParent(self._canvas)
            row.move(x, y)
            # Apply persisted size if any
            sz = self._sizes.get(row.field_key)
            if sz:
                row.setFixedSize(sz[0], sz[1])
            else:
                row.adjustSize()
            row.show()
            bottom = y + (sz[1] if sz else row.sizeHint().height())
            if bottom > max_y:
                max_y = bottom
        # Expand canvas so all fields are visible
        self._canvas.setMinimumHeight(max_y + 20)

    # ── Public API ───────────────────────────────────────────────────

    def add_field(self, row: FieldRow):
        self._rows.append(row)
        self._field_map[row.field_key] = row
        row.setParent(self._canvas)
        if row.field_key not in self._positions:
            idx = len(self._rows) - 1
            self._positions[row.field_key] = self._default_position(idx)
        self._apply_positions()

    def field(self, key: str) -> FieldRow | None:
        return self._field_map.get(key)

    def field_keys(self) -> list[str]:
        return [r.field_key for r in self._rows]

    def set_order(self, keys: list[str]):
        key_set = set(keys)
        ordered = [self._field_map[k] for k in keys if k in self._field_map]
        for r in self._rows:
            if r.field_key not in key_set:
                ordered.append(r)
        self._rows = ordered
        self._apply_positions()

    def move_field(self, key: str, x: int, y: int):
        """Programmatically place a field at (x, y), snapped to grid."""
        x, y = self._snap(max(x, 0)), self._snap(max(y, 0))
        self._positions[key] = (x, y)
        row = self._field_map.get(key)
        if row:
            row.move(x, y)
            row.adjustSize()
        self._update_canvas_bounds()

    def _update_canvas_bounds(self):
        """Recompute canvas minimum height to fit all fields."""
        max_y = _CANVAS_MIN_H
        for k, (px, py) in self._positions.items():
            row = self._field_map.get(k)
            if not row:
                continue
            h = row.height() or row.sizeHint().height()
            bottom = py + h
            if bottom > max_y:
                max_y = bottom
        self._canvas.setMinimumHeight(max(max_y + 20, _CANVAS_MIN_H))

    # ── Selection / multi-select ─────────────────────────────────────

    def _handle_field_click(self, field: FieldRow, ctrl: bool):
        """Handle a click on a FieldRow — manage selection."""
        if ctrl:
            # Toggle in/out of selection
            if field in self._selection:
                self._selection.remove(field)
                field.selected = False
            else:
                self._selection.append(field)
                field.selected = True
        else:
            # Exclusive select
            for r in self._selection:
                r.selected = False
            self._selection = [field]
            field.selected = True
        self._update_selection_ui()

    def _clear_selection(self):
        for r in self._selection:
            r.selected = False
        self._selection.clear()
        self._update_selection_ui()

    def _update_selection_ui(self):
        n = len(self._selection)
        self._btn_align_left.setEnabled(n >= 2)
        self._btn_align_top.setEnabled(n >= 2)
        self._lbl_sel.setText(f"{n} selected" if n else "")

    def _canvas_mousePressEvent(self, event):
        """Click on empty canvas area — start rubber-band selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if not ctrl:
                self._clear_selection()
            self._rubber_origin = event.pos()
            self._rubber.setGeometry(QRect(event.pos(), QSize(0, 0)))
            self._rubber.show()
            self._rubber.raise_()

    def _canvas_mouseMoveEvent(self, event):
        """Expand rubber-band rectangle while dragging."""
        if self._rubber_origin is not None:
            rect = QRect(self._rubber_origin, event.pos()).normalized()
            self._rubber.setGeometry(rect)

    def _canvas_mouseReleaseEvent(self, event):
        """Finish rubber-band — select all FieldRows that intersect."""
        if self._rubber_origin is not None and event.button() == Qt.MouseButton.LeftButton:
            rect = QRect(self._rubber_origin, event.pos()).normalized()
            self._rubber.hide()
            self._rubber_origin = None

            # Only treat as lasso if dragged more than a few pixels
            if rect.width() < 4 and rect.height() < 4:
                return

            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if not ctrl:
                for r in self._selection:
                    r.selected = False
                self._selection.clear()

            for row in self._rows:
                if row.geometry().intersects(rect):
                    if row not in self._selection:
                        self._selection.append(row)
                        row.selected = True
            self._update_selection_ui()

    # ── Alignment actions ────────────────────────────────────────────

    def _align_left(self):
        """Align all selected controls to the left edge of the leftmost one."""
        if len(self._selection) < 2:
            return
        min_x = min(self._positions.get(r.field_key, (0, 0))[0]
                    for r in self._selection)
        for r in self._selection:
            _x, y = self._positions.get(r.field_key, (0, 0))
            self._positions[r.field_key] = (min_x, y)
            r.move(min_x, y)
        self._update_canvas_bounds()

    def _align_top(self):
        """Align all selected controls to the top edge of the topmost one."""
        if len(self._selection) < 2:
            return
        min_y = min(self._positions.get(r.field_key, (0, 0))[1]
                    for r in self._selection)
        for r in self._selection:
            x, _y = self._positions.get(r.field_key, (0, 0))
            self._positions[r.field_key] = (x, min_y)
            r.move(x, min_y)
        self._update_canvas_bounds()

    # ── Drag and drop (delegated from canvas) ────────────────────────

    def _canvas_dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_DRAG_MIME):
            event.acceptProposedAction()

    def _canvas_dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(_DRAG_MIME):
            return
        event.acceptProposedAction()
        pos = event.position().toPoint()
        key = bytes(event.mimeData().data(_DRAG_MIME)).decode()
        row = self._field_map.get(key)
        if not row:
            return

        # Compute snapped position accounting for the drag hotspot
        sx = self._snap(max(pos.x() - self._drag_hotspot.x(), 0))
        sy = self._snap(max(pos.y() - self._drag_hotspot.y(), 0))
        self._drop_pos = QPoint(sx, sy)

        # Show ghost outline (for the dragged item only)
        w = row.width() or row.sizeHint().width()
        h = row.height() or row.sizeHint().height()
        self._ghost.setGeometry(sx, sy, w, h)
        self._ghost.show()
        self._ghost.raise_()

    def _canvas_dragLeaveEvent(self, event):
        self._ghost.hide()
        self._drop_pos = None

    def _canvas_dropEvent(self, event):
        self._ghost.hide()
        key = bytes(event.mimeData().data(_DRAG_MIME)).decode()
        field_row = self._field_map.get(key)
        if not field_row or self._drop_pos is None:
            return
        new_x, new_y = self._drop_pos.x(), self._drop_pos.y()
        self._drop_pos = None

        # Calculate delta from the dragged field's old position
        old_x, old_y = self._positions.get(key, (0, 0))
        dx = new_x - old_x
        dy = new_y - old_y

        # If the dragged field is part of a multi-selection, move the group
        if field_row in self._selection and len(self._selection) > 1:
            for r in self._selection:
                rx, ry = self._positions.get(r.field_key, (0, 0))
                nx = self._snap(max(rx + dx, 0))
                ny = self._snap(max(ry + dy, 0))
                self._positions[r.field_key] = (nx, ny)
                r.move(nx, ny)
        else:
            self._positions[key] = (new_x, new_y)
            field_row.move(new_x, new_y)

        self._update_canvas_bounds()
        event.acceptProposedAction()

    # ── Query interface ──────────────────────────────────────────────

    def get_field_mode(self, key: str) -> str:
        r = self._field_map.get(key)
        return r.mode if r else "contains"

    def get_field_value(self, key: str) -> str:
        r = self._field_map.get(key)
        return r.get_value() if r else ""

    def get_field_range(self, key: str) -> tuple[str, str]:
        r = self._field_map.get(key)
        return r.get_range() if r else ("", "")

    def get_field_list_values(self, key: str) -> list[str]:
        r = self._field_map.get(key)
        return r.get_list_values() if r else []

    # ── State ────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        # Capture current sizes from live widgets
        for r in self._rows:
            w, h = r.width(), r.height()
            if w > 0 and h > 0:
                self._sizes[r.field_key] = (w, h)
        return {
            "order": self.field_keys(),
            "positions": dict(self._positions),
            "sizes": dict(self._sizes),
            "fields": {r.field_key: r.get_state() for r in self._rows},
        }

    def set_state(self, state: dict):
        # Restore positions
        positions = state.get("positions")
        if positions:
            for key, pos in positions.items():
                if isinstance(pos, (list, tuple)) and len(pos) == 2:
                    self._positions[key] = (int(pos[0]), int(pos[1]))

        # Restore sizes
        sizes = state.get("sizes")
        if sizes:
            for key, sz in sizes.items():
                if isinstance(sz, (list, tuple)) and len(sz) == 2:
                    self._sizes[key] = (int(sz[0]), int(sz[1]))

        order = state.get("order")
        if order:
            self.set_order(order)
        else:
            self._apply_positions()

        fields = state.get("fields", {})
        for key, s in fields.items():
            r = self._field_map.get(key)
            if r:
                r.set_state(s)
