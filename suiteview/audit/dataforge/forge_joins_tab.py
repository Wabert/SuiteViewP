"""
Forge Joins Tab — card-based, canvas-positioned merge configuration.

Mirrors the QDesign JoinsTab pattern: movable/resizable ForgeJoinCard
widgets on a scrollable canvas with drag-to-move and snap-to-grid.

Each card defines one pd.merge() operation between two query datasets,
with column dropdowns populated from QDefinition result_columns.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QPoint, QSize, pyqtSignal, QMimeData
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QDrag, QMouseEvent, QPolygon
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QComboBox,
    QLabel, QPushButton, QFrame, QSizePolicy, QToolButton, QMenu,
)

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 8)
_FONT_BOLD = QFont("Segoe UI", 8, QFont.Weight.Bold)
_FONT_SMALL = QFont("Segoe UI", 7)

_MERGE_TYPES = ["inner", "left", "right", "outer"]
_MERGE_LABELS = ["INNER", "LEFT", "RIGHT", "OUTER"]

_DRAG_MIME = "application/x-forge-joincard"
_GRID_SNAP = 8
_CANVAS_MIN_H = 400
_H = 20
_GRIP_W = 10
_RESIZE_HANDLE = 8
_DEFAULT_W = 500
_DEFAULT_CARD_H = 120
_COLLAPSED_H = 26

# ── Teal-themed styles ──────────────────────────────────────────────

_BORDER_COLOR = QColor("#0D9488")
_BORDER_COLOR_DISABLED = QColor("#AAA")
_BG_ENABLED = QColor("#F0FDFA")
_BG_DISABLED = QColor("#F0F0F0")

_COMBO_STYLE = (
    "QComboBox { font-size: 8pt; border: 1px solid #999; border-radius: 2px;"
    " padding: 1px 4px; background: white; }"
    "QComboBox:hover { border-color: #0D9488; }"
    "QComboBox::drop-down { width: 14px; }"
)

_COMBO_MERGE_STYLE = (
    "QComboBox { font-size: 7pt; border: 1px solid #999; border-radius: 2px;"
    " padding: 1px 2px; background: #E6F5F3; color: #0D9488;"
    " font-weight: bold; min-width: 50px; }"
    "QComboBox::drop-down { width: 12px; }"
)

_BTN_ADD_STYLE = (
    "QToolButton { font-size: 8pt; border: 1px solid #0D9488; border-radius: 2px;"
    " background: #E6F5F3; color: #0D9488; padding: 0px 4px; }"
    "QToolButton:hover { background: #B2DFDB; }"
)

_BTN_DEL_STYLE = (
    "QToolButton { font-size: 8pt; border: 1px solid #C00; border-radius: 2px;"
    " background: #FFF0F0; color: #C00; padding: 0px 4px; }"
    "QToolButton:hover { background: #FFD0D0; }"
)

_BTN_TOGGLE_STYLE = (
    "QToolButton { font-size: 7pt; border: 1px solid #0D9488; border-radius: 2px;"
    " background: #E6F5F3; color: #0D9488; padding: 0px 2px; }"
    "QToolButton:hover { background: #B2DFDB; }"
)

_ADD_CARD_BTN_STYLE = (
    "QPushButton { font-size: 8pt; border: 1px solid #0D9488; border-radius: 3px;"
    " background: #E6F5F3; color: #0D9488; padding: 3px 12px;"
    " font-weight: bold; }"
    "QPushButton:hover { background: #B2DFDB; }"
)


# ── ON Condition Row ─────────────────────────────────────────────────

class _ForgeOnRow(QWidget):
    """Single ON condition: left_col = right_col with combo dropdowns."""
    changed = pyqtSignal()
    remove_requested = pyqtSignal(object)

    def __init__(self, left_cols: list[str] | None = None,
                 right_cols: list[str] | None = None,
                 parent=None):
        super().__init__(parent)
        self.setFixedHeight(_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self.cmb_left = QComboBox()
        self.cmb_left.setFont(_FONT)
        self.cmb_left.setStyleSheet(_COMBO_STYLE)
        self.cmb_left.setFixedHeight(_H)
        self.cmb_left.setEditable(True)
        self.cmb_left.setSizePolicy(QSizePolicy.Policy.Expanding,
                                    QSizePolicy.Policy.Fixed)
        if left_cols:
            self.cmb_left.addItems(left_cols)
        lay.addWidget(self.cmb_left, 1)

        lbl_eq = QLabel("=")
        lbl_eq.setFont(_FONT_BOLD)
        lbl_eq.setFixedWidth(12)
        lbl_eq.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_eq)

        self.cmb_right = QComboBox()
        self.cmb_right.setFont(_FONT)
        self.cmb_right.setStyleSheet(_COMBO_STYLE)
        self.cmb_right.setFixedHeight(_H)
        self.cmb_right.setEditable(True)
        self.cmb_right.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Fixed)
        if right_cols:
            self.cmb_right.addItems(right_cols)
        lay.addWidget(self.cmb_right, 1)

        self.btn_remove = QToolButton()
        self.btn_remove.setText("−")
        self.btn_remove.setFont(_FONT_BOLD)
        self.btn_remove.setFixedSize(18, _H)
        self.btn_remove.setStyleSheet(_BTN_DEL_STYLE)
        self.btn_remove.setToolTip("Remove condition")
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self))
        lay.addWidget(self.btn_remove)

        self.cmb_left.currentTextChanged.connect(lambda: self.changed.emit())
        self.cmb_right.currentTextChanged.connect(lambda: self.changed.emit())

    def get_pair(self) -> tuple[str, str]:
        return (self.cmb_left.currentText().strip(),
                self.cmb_right.currentText().strip())

    def set_pair(self, left: str, right: str):
        self.cmb_left.setCurrentText(left)
        self.cmb_right.setCurrentText(right)

    def set_columns(self, left_cols: list[str], right_cols: list[str]):
        cur_l = self.cmb_left.currentText()
        cur_r = self.cmb_right.currentText()
        self.cmb_left.blockSignals(True)
        self.cmb_right.blockSignals(True)
        self.cmb_left.clear()
        self.cmb_left.addItems(left_cols)
        self.cmb_right.clear()
        self.cmb_right.addItems(right_cols)
        if cur_l:
            self.cmb_left.setCurrentText(cur_l)
        if cur_r:
            self.cmb_right.setCurrentText(cur_r)
        self.cmb_left.blockSignals(False)
        self.cmb_right.blockSignals(False)


# ── Forge Join Card ──────────────────────────────────────────────────

class ForgeJoinCard(QWidget):
    """Movable/resizable merge card on the ForgeJoinsTab canvas.

    Header: [grip] [☑] LEFT_QUERY [MERGE_TYPE] RIGHT_QUERY [▲] [×]
    Body:   ON [left_col = right_col] [−] [+]
            (supports multiple ON keys)
    """
    state_changed = pyqtSignal()
    remove_requested = pyqtSignal(object)

    _next_id = 0

    def __init__(self, query_names: list[str],
                 query_columns: dict[str, list[str]],
                 parent=None):
        super().__init__(parent)
        ForgeJoinCard._next_id += 1
        self.card_id = f"fj_{ForgeJoinCard._next_id}"

        self._query_names = list(query_names)
        self._query_columns = dict(query_columns)  # name → [col, ...]
        self._collapsed = False
        self._pre_collapse_h = 0

        # Drag / resize state
        self._drag_start: QPoint | None = None
        self._resizing = False
        self._resize_start: QPoint | None = None
        self._resize_origin_size: QSize | None = None

        self.setMouseTracking(True)
        self.setMinimumWidth(200)

        root = QVBoxLayout(self)
        root.setContentsMargins(_GRIP_W + 4, 3, 4, 3)
        root.setSpacing(2)

        # ── Header row ──────────────────────────────────────────
        r1 = QHBoxLayout()
        r1.setSpacing(3)
        r1.setContentsMargins(0, 0, 0, 0)

        self.chk_enabled = QToolButton()
        self.chk_enabled.setText("☑")
        self.chk_enabled.setFont(_FONT)
        self.chk_enabled.setFixedSize(18, _H)
        self.chk_enabled.setCheckable(True)
        self.chk_enabled.setChecked(True)
        self.chk_enabled.setStyleSheet(
            "QToolButton { border: 1px solid #0D9488; border-radius: 2px;"
            " background: #E6F5F3; color: #0D9488; }"
            "QToolButton:checked { background: #0D9488; color: white; }"
        )
        self.chk_enabled.toggled.connect(self._on_enabled_toggled)
        r1.addWidget(self.chk_enabled)

        self.cmb_left = QComboBox()
        self.cmb_left.setFont(_FONT)
        self.cmb_left.setStyleSheet(_COMBO_STYLE)
        self.cmb_left.setFixedHeight(_H)
        self.cmb_left.setSizePolicy(QSizePolicy.Policy.Expanding,
                                    QSizePolicy.Policy.Fixed)
        self.cmb_left.addItems(self._query_names)
        r1.addWidget(self.cmb_left, 1)

        self.cmb_merge_type = QComboBox()
        self.cmb_merge_type.setFont(_FONT_SMALL)
        self.cmb_merge_type.setStyleSheet(_COMBO_MERGE_STYLE)
        self.cmb_merge_type.setFixedHeight(_H)
        for label, val in zip(_MERGE_LABELS, _MERGE_TYPES):
            self.cmb_merge_type.addItem(label, val)
        r1.addWidget(self.cmb_merge_type)

        self.cmb_right = QComboBox()
        self.cmb_right.setFont(_FONT)
        self.cmb_right.setStyleSheet(_COMBO_STYLE)
        self.cmb_right.setFixedHeight(_H)
        self.cmb_right.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Fixed)
        self.cmb_right.addItems(self._query_names)
        if len(self._query_names) > 1:
            self.cmb_right.setCurrentIndex(1)
        r1.addWidget(self.cmb_right, 1)

        self.btn_toggle = QToolButton()
        self.btn_toggle.setText("▲")
        self.btn_toggle.setFont(_FONT_SMALL)
        self.btn_toggle.setFixedSize(18, _H)
        self.btn_toggle.setStyleSheet(_BTN_TOGGLE_STYLE)
        self.btn_toggle.setToolTip("Collapse / expand")
        self.btn_toggle.clicked.connect(self._toggle_collapse)
        r1.addWidget(self.btn_toggle)

        self.btn_remove = QToolButton()
        self.btn_remove.setText("×")
        self.btn_remove.setFont(_FONT_BOLD)
        self.btn_remove.setFixedSize(18, _H)
        self.btn_remove.setStyleSheet(_BTN_DEL_STYLE)
        self.btn_remove.setToolTip("Remove this merge")
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self))
        r1.addWidget(self.btn_remove)

        root.addLayout(r1)

        # ── Body (ON conditions) ────────────────────────────────
        self._body = QWidget()
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(0, 2, 0, 0)
        body_lay.setSpacing(2)

        r_on = QHBoxLayout()
        r_on.setSpacing(2)
        r_on.setContentsMargins(0, 0, 0, 0)
        lbl_on = QLabel("ON")
        lbl_on.setFont(_FONT_BOLD)
        lbl_on.setStyleSheet("color: #0D9488;")
        lbl_on.setFixedWidth(22)
        r_on.addWidget(lbl_on)
        self._on_container = QVBoxLayout()
        self._on_container.setSpacing(1)
        self._on_container.setContentsMargins(0, 0, 0, 0)
        r_on.addLayout(self._on_container, 1)
        self.btn_add_on = QToolButton()
        self.btn_add_on.setText("+")
        self.btn_add_on.setFont(_FONT_BOLD)
        self.btn_add_on.setFixedSize(18, _H)
        self.btn_add_on.setStyleSheet(_BTN_ADD_STYLE)
        self.btn_add_on.setToolTip("Add ON condition")
        self.btn_add_on.clicked.connect(self._add_on_row)
        r_on.addWidget(self.btn_add_on, alignment=Qt.AlignmentFlag.AlignTop)
        body_lay.addLayout(r_on)

        # Status line
        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet("color: #888;")
        body_lay.addWidget(self.lbl_status)

        root.addWidget(self._body)

        # ── Collapsed summary ───────────────────────────────────
        self._lbl_summary = QLabel("")
        self._lbl_summary.setFont(_FONT_SMALL)
        self._lbl_summary.setStyleSheet("color: #666;")
        self._lbl_summary.setVisible(False)
        root.addWidget(self._lbl_summary)

        # ON rows
        self._on_rows: list[_ForgeOnRow] = []
        self._add_on_row()

        # Wire signals
        self.cmb_left.currentTextChanged.connect(self._on_queries_changed)
        self.cmb_right.currentTextChanged.connect(self._on_queries_changed)
        self.cmb_merge_type.currentIndexChanged.connect(
            lambda: self.state_changed.emit())

        self._on_queries_changed()

    # ── Paint ────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        enabled = self.chk_enabled.isChecked()
        bg = _BG_ENABLED if enabled else _BG_DISABLED
        p.fillRect(self.rect(), bg)

        pen = QPen(_BORDER_COLOR if enabled else _BORDER_COLOR_DISABLED)
        pen.setWidth(1)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # Grip dots
        p.setPen(QPen(QColor("#999"), 1))
        gx = 3
        for gy in range(6, self.height() - 4, 4):
            p.drawPoint(gx, gy)
            p.drawPoint(gx + 3, gy + 2)

        # Resize triangle
        rhs = _RESIZE_HANDLE
        tri = QPolygon([
            QPoint(self.width() - 1, self.height() - rhs),
            QPoint(self.width() - 1, self.height() - 1),
            QPoint(self.width() - rhs, self.height() - 1),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0D9488") if enabled else QColor("#AAA"))
        p.drawPolygon(tri)
        p.end()

    # ── Mouse: grip drag + resize ────────────────────────────────

    def _in_resize_zone(self, pos: QPoint) -> bool:
        return (pos.x() >= self.width() - _RESIZE_HANDLE
                and pos.y() >= self.height() - _RESIZE_HANDLE)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._in_resize_zone(event.pos()):
                self._resizing = True
                self._resize_start = event.globalPosition().toPoint()
                self._resize_origin_size = self.size()
                return
            if event.pos().x() < _GRIP_W:
                self._drag_start = event.pos()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._in_resize_zone(event.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif event.pos().x() < _GRIP_W:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        if self._resizing and self._resize_start:
            delta = event.globalPosition().toPoint() - self._resize_start
            new_w = max(self._resize_origin_size.width() + delta.x(), 200)
            new_h = max(self._resize_origin_size.height() + delta.y(),
                        _COLLAPSED_H)
            self.setFixedSize(new_w, new_h)
            tab = self._tab()
            if tab:
                tab._update_canvas_bounds()
            return

        if self._drag_start is not None:
            dist = (event.pos() - self._drag_start).manhattanLength()
            if dist > 6:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setData(_DRAG_MIME, self.card_id.encode())
                drag.setMimeData(mime)
                drag.setPixmap(self.grab())
                drag.setHotSpot(self._drag_start)
                tab = self._tab()
                if tab:
                    tab._drag_hotspot = self._drag_start
                self._drag_start = None
                drag.exec(Qt.DropAction.MoveAction)
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._resizing:
            self._resizing = False
            self._resize_start = None
            tab = self._tab()
            if tab:
                tab._sizes[self.card_id] = (self.width(), self.height())
                tab._update_canvas_bounds()
                tab.state_changed.emit()
            return
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def _tab(self):
        """Return parent ForgeJoinsTab if available."""
        p = self.parent()
        while p:
            if isinstance(p, ForgeJoinsTab):
                return p
            p = p.parent()
        return None

    # ── Context menu ─────────────────────────────────────────────

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { font-size: 8pt; }"
            "QMenu::item:selected { background: #E6F5F3; }")
        act_collapse = menu.addAction(
            "Expand" if self._collapsed else "Collapse")
        act_collapse.triggered.connect(self._toggle_collapse)
        menu.addSeparator()
        act_remove = menu.addAction("Remove Merge")
        act_remove.triggered.connect(lambda: self.remove_requested.emit(self))
        menu.exec(event.globalPos())

    # ── Collapse / expand ────────────────────────────────────────

    def _toggle_collapse(self):
        if self._collapsed:
            self._expand()
        else:
            self._collapse()

    def _collapse(self):
        self._pre_collapse_h = self.height()
        self._collapsed = True
        self._body.setVisible(False)
        self.btn_toggle.setText("▼")
        # Build summary
        left = self.cmb_left.currentText()
        right = self.cmb_right.currentText()
        mt = self.cmb_merge_type.currentText()
        pairs = [r.get_pair() for r in self._on_rows
                 if r.get_pair()[0] and r.get_pair()[1]]
        keys = ", ".join(f"{l}={r}" for l, r in pairs)
        self._lbl_summary.setText(f"  {left} {mt} → {right}  ({keys})")
        self._lbl_summary.setVisible(True)
        self.setFixedSize(self.width(), _COLLAPSED_H)
        tab = self._tab()
        if tab:
            tab._sizes[self.card_id] = (self.width(), _COLLAPSED_H)
            tab._update_canvas_bounds()
            tab.state_changed.emit()

    def _expand(self):
        self._collapsed = False
        self._body.setVisible(True)
        self._lbl_summary.setVisible(False)
        self.btn_toggle.setText("▲")
        h = max(self._pre_collapse_h, _DEFAULT_CARD_H)
        self.setFixedSize(self.width(), h)
        tab = self._tab()
        if tab:
            tab._sizes[self.card_id] = (self.width(), h)
            tab._update_canvas_bounds()
            tab.state_changed.emit()

    # ── Enabled toggle ───────────────────────────────────────────

    def _on_enabled_toggled(self, checked: bool):
        self.chk_enabled.setText("☑" if checked else "☐")
        self.update()
        self.state_changed.emit()

    # ── ON conditions ────────────────────────────────────────────

    def _get_left_cols(self) -> list[str]:
        name = self.cmb_left.currentText()
        return self._query_columns.get(name, [])

    def _get_right_cols(self) -> list[str]:
        name = self.cmb_right.currentText()
        return self._query_columns.get(name, [])

    def _add_on_row(self):
        row = _ForgeOnRow(self._get_left_cols(), self._get_right_cols(),
                          parent=self)
        row.changed.connect(self._on_condition_changed)
        row.remove_requested.connect(self._remove_on_row)
        self._on_rows.append(row)
        self._on_container.addWidget(row)
        self.state_changed.emit()

    def _remove_on_row(self, row):
        if len(self._on_rows) <= 1:
            return  # keep at least one
        if row in self._on_rows:
            self._on_rows.remove(row)
            self._on_container.removeWidget(row)
            row.deleteLater()
            self.state_changed.emit()

    def _on_condition_changed(self):
        # Auto-match: if columns with same name exist in both sides
        self._update_status()
        self.state_changed.emit()

    def _on_queries_changed(self):
        """Left or right query combo changed — update column lists in ON rows."""
        left_cols = self._get_left_cols()
        right_cols = self._get_right_cols()
        for row in self._on_rows:
            row.set_columns(left_cols, right_cols)

        # Auto-match common column names for first row if empty
        if (self._on_rows and not self._on_rows[0].get_pair()[0]
                and not self._on_rows[0].get_pair()[1]):
            common = [c for c in left_cols if c in right_cols]
            if common:
                self._on_rows[0].set_pair(common[0], common[0])

        self._update_status()
        self.state_changed.emit()

    def _update_status(self):
        pairs = [r.get_pair() for r in self._on_rows]
        valid = sum(1 for l, r in pairs if l and r)
        self.lbl_status.setText(f"{valid} key pair(s) configured")

    # ── Update queries (external) ────────────────────────────────

    def update_queries(self, query_names: list[str],
                       query_columns: dict[str, list[str]] | None = None):
        self._query_names = list(query_names)
        if query_columns is not None:
            self._query_columns = dict(query_columns)
        # Update combos
        for combo in (self.cmb_left, self.cmb_right):
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(self._query_names)
            if cur:
                idx = combo.findText(cur)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)
        self._on_queries_changed()

    # ── Public: get merge info ───────────────────────────────────

    def get_merge_info(self) -> dict | None:
        """Return merge op dict, or None if disabled / incomplete."""
        if not self.chk_enabled.isChecked():
            return None
        left = self.cmb_left.currentText().strip()
        right = self.cmb_right.currentText().strip()
        if not left or not right:
            return None
        # Collect all valid ON pairs
        pairs = [(l, r) for l, r in
                 (row.get_pair() for row in self._on_rows)
                 if l and r]
        if not pairs:
            return None
        # For pd.merge: if multiple keys, pass as lists
        left_on = [p[0] for p in pairs]
        right_on = [p[1] for p in pairs]
        if len(left_on) == 1:
            left_on = left_on[0]
            right_on = right_on[0]
        return {
            "left": left,
            "right": right,
            "left_on": left_on,
            "right_on": right_on,
            "how": self.cmb_merge_type.currentData(),
        }

    # ── State persistence ────────────────────────────────────────

    def get_state(self) -> dict:
        return {
            "card_id": self.card_id,
            "enabled": self.chk_enabled.isChecked(),
            "left": self.cmb_left.currentText(),
            "right": self.cmb_right.currentText(),
            "how": self.cmb_merge_type.currentData(),
            "on_pairs": [row.get_pair() for row in self._on_rows],
            "collapsed": self._collapsed,
        }

    def set_state(self, state: dict):
        if "card_id" in state:
            self.card_id = state["card_id"]
        self.chk_enabled.setChecked(state.get("enabled", True))
        idx = self.cmb_left.findText(state.get("left", ""))
        if idx >= 0:
            self.cmb_left.setCurrentIndex(idx)
        idx = self.cmb_right.findText(state.get("right", ""))
        if idx >= 0:
            self.cmb_right.setCurrentIndex(idx)
        how = state.get("how", "inner")
        idx = self.cmb_merge_type.findData(how)
        if idx >= 0:
            self.cmb_merge_type.setCurrentIndex(idx)

        # Restore ON pairs
        pairs = state.get("on_pairs", [])
        while len(self._on_rows) < len(pairs):
            self._add_on_row()
        for i, (l, r) in enumerate(pairs):
            if i < len(self._on_rows):
                self._on_rows[i].set_pair(l, r)

        if state.get("collapsed", False):
            self._collapse()


# ── Forge Joins Tab (canvas) ─────────────────────────────────────────

class ForgeJoinsTab(QScrollArea):
    """Canvas of ForgeJoinCard widgets — mirrors QDesign JoinsTab pattern.

    Cards are absolutely positioned with snap-to-grid, drag-to-move,
    and edge-resize.
    """
    state_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._query_names: list[str] = []
        self._query_columns: dict[str, list[str]] = {}
        self._cards: list[ForgeJoinCard] = []
        self._positions: dict[str, tuple[int, int]] = {}
        self._sizes: dict[str, tuple[int, int]] = {}
        self._drag_hotspot: QPoint = QPoint(0, 0)

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Canvas
        self._canvas = QWidget()
        self._canvas.setMinimumHeight(_CANVAS_MIN_H)
        self._canvas.setAcceptDrops(True)
        self._canvas.dragEnterEvent = self._canvas_dragEnterEvent
        self._canvas.dragMoveEvent = self._canvas_dragMoveEvent
        self._canvas.dropEvent = self._canvas_dropEvent
        self.setWidget(self._canvas)

        # Ghost preview
        self._ghost = QFrame(self._canvas)
        self._ghost.setStyleSheet(
            "border: 2px dashed #0D9488; background: transparent;")
        self._ghost.hide()

        # '+ Add Merge' button
        self.btn_add = QPushButton("+ Add Merge", self._canvas)
        self.btn_add.setFont(_FONT_BOLD)
        self.btn_add.setFixedHeight(22)
        self.btn_add.setStyleSheet(_ADD_CARD_BTN_STYLE)
        self.btn_add.move(4, 4)
        self.btn_add.clicked.connect(self._add_card)

    @staticmethod
    def _snap(val: int) -> int:
        return round(val / _GRID_SNAP) * _GRID_SNAP

    def _default_position(self, idx: int) -> tuple[int, int]:
        y = 32
        for i, card in enumerate(self._cards):
            if i >= idx:
                break
            cid = card.card_id
            _, ch = self._sizes.get(cid, (0, 0))
            if ch <= 0:
                ch = card.sizeHint().height()
            y += ch + 8
        return (4, self._snap(y))

    def _add_card(self, state: dict | None = None) -> ForgeJoinCard:
        card = ForgeJoinCard(self._query_names, self._query_columns,
                             parent=self._canvas)
        card.state_changed.connect(self._on_card_changed)
        card.remove_requested.connect(self._remove_card)

        if isinstance(state, dict):
            card.set_state(state)

        self._cards.append(card)

        cid = card.card_id
        if cid not in self._positions:
            self._positions[cid] = self._default_position(len(self._cards) - 1)

        if cid in self._sizes:
            w, h = self._sizes[cid]
            card.setFixedSize(max(w, 200), max(h, _COLLAPSED_H))
        else:
            card.adjustSize()
            sh = card.sizeHint()
            w = max(sh.width(), _DEFAULT_W)
            h = max(sh.height(), _DEFAULT_CARD_H)
            card.setFixedSize(w, h)
            self._sizes[cid] = (w, h)

        x, y = self._positions[cid]
        card.move(x, y)
        card.show()
        self._update_canvas_bounds()
        self.state_changed.emit()
        return card

    def _remove_card(self, card: ForgeJoinCard):
        if card in self._cards:
            cid = card.card_id
            self._cards.remove(card)
            self._positions.pop(cid, None)
            self._sizes.pop(cid, None)
            card.setParent(None)
            card.deleteLater()
            self._update_canvas_bounds()
            self.state_changed.emit()

    def _on_card_changed(self):
        self.state_changed.emit()

    # ── Canvas bounds ────────────────────────────────────────────

    def _update_canvas_bounds(self):
        max_y = _CANVAS_MIN_H
        max_x = self.viewport().width()
        for card in self._cards:
            cid = card.card_id
            px, py = self._positions.get(cid, (0, 0))
            bottom = py + card.height()
            right = px + card.width()
            if bottom > max_y:
                max_y = bottom
            if right > max_x:
                max_x = right
        self._canvas.setMinimumHeight(max(max_y + 40, _CANVAS_MIN_H))
        self._canvas.setMinimumWidth(max(max_x + 20, self.viewport().width()))

    # ── Drag-drop on canvas ──────────────────────────────────────

    def _canvas_dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_DRAG_MIME):
            event.acceptProposedAction()

    def _canvas_dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(_DRAG_MIME):
            return
        event.acceptProposedAction()
        key = bytes(event.mimeData().data(_DRAG_MIME)).decode()
        card = self._card_by_id(key)
        if not card:
            return
        pos = event.position().toPoint()
        sx = self._snap(max(pos.x() - self._drag_hotspot.x(), 0))
        sy = self._snap(max(pos.y() - self._drag_hotspot.y(), 0))
        self._ghost.setGeometry(sx, sy, card.width(), card.height())
        self._ghost.show()

    def _canvas_dropEvent(self, event):
        self._ghost.hide()
        if not event.mimeData().hasFormat(_DRAG_MIME):
            return
        key = bytes(event.mimeData().data(_DRAG_MIME)).decode()
        card = self._card_by_id(key)
        if not card:
            return
        pos = event.position().toPoint()
        sx = self._snap(max(pos.x() - self._drag_hotspot.x(), 0))
        sy = self._snap(max(pos.y() - self._drag_hotspot.y(), 0))
        self._positions[key] = (sx, sy)
        card.move(sx, sy)
        self._update_canvas_bounds()
        self.state_changed.emit()
        event.acceptProposedAction()

    def _card_by_id(self, card_id: str) -> ForgeJoinCard | None:
        for card in self._cards:
            if card.card_id == card_id:
                return card
        return None

    # ── Update queries ───────────────────────────────────────────

    def update_queries(self, query_names: list[str],
                       query_columns: dict[str, list[str]] | None = None):
        self._query_names = list(query_names)
        if query_columns is not None:
            self._query_columns = dict(query_columns)
        for card in self._cards:
            card.update_queries(self._query_names, self._query_columns)

    # ── Public: get merge ops (backward compatible) ──────────────

    def get_merge_ops(self) -> list[dict]:
        ops = []
        for card in self._cards:
            info = card.get_merge_info()
            if info is not None:
                ops.append(info)
        return ops

    # ── State persistence ────────────────────────────────────────

    def get_state(self) -> dict:
        for card in self._cards:
            self._sizes[card.card_id] = (card.width(), card.height())
        return {
            "cards": [card.get_state() for card in self._cards],
            "positions": dict(self._positions),
            "sizes": {k: list(v) for k, v in self._sizes.items()},
        }

    def set_state(self, state: dict):
        # Handle legacy format: {"merges": [...]}
        if "merges" in state and "cards" not in state:
            self._set_state_legacy(state)
            return

        for card in list(self._cards):
            self._cards.remove(card)
            card.setParent(None)
            card.deleteLater()
        self._positions.clear()
        self._sizes.clear()

        positions = state.get("positions", {})
        for key, pos in positions.items():
            self._positions[key] = (int(pos[0]), int(pos[1]))
        sizes = state.get("sizes", {})
        for key, sz in sizes.items():
            self._sizes[key] = (int(sz[0]), int(sz[1]))

        for card_state in state.get("cards", []):
            self._add_card(card_state)

    def _set_state_legacy(self, state: dict):
        """Restore from old format: {"merges": [{left, right, left_on, right_on, how}]}."""
        for card in list(self._cards):
            self._cards.remove(card)
            card.setParent(None)
            card.deleteLater()
        self._positions.clear()
        self._sizes.clear()

        for m in state.get("merges", []):
            card = self._add_card()
            idx = card.cmb_left.findText(m.get("left", ""))
            if idx >= 0:
                card.cmb_left.setCurrentIndex(idx)
            idx = card.cmb_right.findText(m.get("right", ""))
            if idx >= 0:
                card.cmb_right.setCurrentIndex(idx)
            # ON keys
            left_on = m.get("left_on", "")
            right_on = m.get("right_on", "")
            if isinstance(left_on, str):
                left_on = [left_on]
                right_on = [right_on] if isinstance(right_on, str) else right_on
            for i, (l, r) in enumerate(zip(left_on, right_on)):
                if i >= len(card._on_rows):
                    card._add_on_row()
                card._on_rows[i].set_pair(l, r)
            how = m.get("how", "inner")
            idx = card.cmb_merge_type.findData(how)
            if idx >= 0:
                card.cmb_merge_type.setCurrentIndex(idx)

    def card_count(self) -> int:
        return len(self._cards)
