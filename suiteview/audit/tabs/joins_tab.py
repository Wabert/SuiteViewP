"""
Joins Tab — compact, free-positioned join cards on a canvas.

Each JoinCard is a movable/resizable widget (like FieldRow) that can be
collapsed to a single summary line or expanded to show full ON/extra
conditions.  Cards live on a canvas with absolute positioning, snap-grid,
drag-to-move, and edge-resize — identical UX to FieldGrid.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import pyodbc
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QPoint, QMimeData, QRect
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPen, QDrag, QMouseEvent, QPolygon, QCursor,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QComboBox,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFrame, QSizePolicy,
    QToolButton, QMenu, QApplication, QMessageBox,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 8)
_FONT_BOLD = QFont("Segoe UI", 8, QFont.Weight.Bold)
_FONT_SMALL = QFont("Segoe UI", 7)

_JOIN_TYPES = ["INNER JOIN", "LEFT OUTER JOIN", "RIGHT OUTER JOIN", "FULL OUTER JOIN"]
_JOIN_SHORT = ["INNER", "LEFT", "RIGHT", "FULL"]

_DRAG_MIME = "application/x-joincard-key"
_GRID_SNAP = 8
_CANVAS_MIN_H = 400
_H = 20  # standard widget height
_GRIP_W = 10
_RESIZE_HANDLE = 8
_DEFAULT_W = 520
_COLLAPSED_H = 26

# ── Styles ───────────────────────────────────────────────────────────

_BORDER_COLOR = QColor("#1E5BA8")
_BORDER_COLOR_DISABLED = QColor("#AAA")
_BG_ENABLED = QColor("#FAFCFF")
_BG_DISABLED = QColor("#F0F0F0")

_COMBO_STYLE = (
    "QComboBox { font-size: 8pt; border: 1px solid #999; border-radius: 2px;"
    " padding: 1px 4px; background: white; }"
    "QComboBox:hover { border-color: #1E5BA8; }"
    "QComboBox::drop-down { width: 14px; }"
)

_COMBO_JOIN_STYLE = (
    "QComboBox { font-size: 7pt; border: 1px solid #999; border-radius: 2px;"
    " padding: 1px 2px; background: #E8F0FB; color: #1E5BA8;"
    " font-weight: bold; min-width: 50px; }"
    "QComboBox::drop-down { width: 12px; }"
)

_INPUT_STYLE = (
    "QLineEdit { font-size: 8pt; border: 1px solid #999; border-radius: 2px;"
    " padding: 1px 3px; background: white; }"
    "QLineEdit:focus { border-color: #1E5BA8; }"
)

_BTN_ADD_STYLE = (
    "QToolButton { font-size: 8pt; border: 1px solid #1E5BA8; border-radius: 2px;"
    " background: #E8F0FB; color: #1E5BA8; padding: 0px 4px; }"
    "QToolButton:hover { background: #C5D8F5; }"
)

_BTN_DEL_STYLE = (
    "QToolButton { font-size: 8pt; border: 1px solid #C00; border-radius: 2px;"
    " background: #FFF0F0; color: #C00; padding: 0px 4px; }"
    "QToolButton:hover { background: #FFD0D0; }"
)

_BTN_TOGGLE_STYLE = (
    "QToolButton { font-size: 7pt; border: 1px solid #1E5BA8; border-radius: 2px;"
    " background: #E8F0FB; color: #1E5BA8; padding: 0px 2px; }"
    "QToolButton:hover { background: #C5D8F5; }"
)

_ADD_CARD_BTN_STYLE = (
    "QPushButton { font-size: 8pt; border: 1px solid #1E5BA8; border-radius: 3px;"
    " background: #E8F0FB; color: #1E5BA8; padding: 3px 12px;"
    " font-weight: bold; }"
    "QPushButton:hover { background: #C5D8F5; }"
)

_DEFAULT_CARD_H = 160  # comfortable initial height for a new join card

# ── Checkmark icon (shared with _styles.py pattern) ──────────────────

_CHECKMARK_PNG = os.path.join(os.path.dirname(__file__), "_checkmark.png")


def _checkmark_path() -> str:
    """Return forward-slash path to the checkmark icon, creating it if needed."""
    if not os.path.exists(_CHECKMARK_PNG):
        from PyQt6.QtGui import QPixmap, QPainter as _QP, QPen as _QPen, QColor as _QC
        from PyQt6.QtCore import QPoint as _QP2
        pix = QPixmap(12, 12)
        pix.fill(_QC(0, 0, 0, 0))
        p = _QP(pix)
        pen = _QPen(_QC("white"))
        pen.setWidth(2)
        p.setPen(pen)
        p.setRenderHint(_QP.RenderHint.Antialiasing)
        p.drawLine(_QP2(2, 6), _QP2(5, 9))
        p.drawLine(_QP2(5, 9), _QP2(10, 3))
        p.end()
        pix.save(_CHECKMARK_PNG)
    return _CHECKMARK_PNG.replace("\\", "/")


# ── Key loader thread ────────────────────────────────────────────────

class _KeyLoaderThread(QThread):
    """Background: fetch primary keys and column names for two tables."""
    keys_loaded = pyqtSignal(str, str, list, list, list, list)
    # left_table, right_table, left_keys, right_keys, left_cols, right_cols
    error_occurred = pyqtSignal(str)

    def __init__(self, dsn: str, left_table: str, right_table: str,
                 parent=None):
        super().__init__(parent)
        self.dsn = dsn
        self.left_table = left_table
        self.right_table = right_table

    def _parse_table(self, full_name: str):
        parts = full_name.split(".", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return None, parts[0]

    def _get_pk_columns(self, cursor, schema, table) -> list[str]:
        """Get primary key column names."""
        try:
            pks = []
            rows = cursor.primaryKeys(table=table, schema=schema)
            for row in rows:
                pks.append(row.column_name)
            return pks
        except Exception:
            return []

    def _get_columns(self, cursor, schema, table) -> list[tuple[str, str]]:
        """Get (col_name, type_name) list."""
        cols = []
        try:
            rows = cursor.columns(table=table, schema=schema)
            for row in rows:
                cols.append((row.column_name, row.type_name))
        except Exception:
            pass
        return cols

    def run(self):
        try:
            conn = pyodbc.connect(f"DSN={self.dsn}", autocommit=True, timeout=15)
            cursor = conn.cursor()

            ls, lt = self._parse_table(self.left_table)
            rs, rt = self._parse_table(self.right_table)

            left_pks = self._get_pk_columns(cursor, ls, lt)
            right_pks = self._get_pk_columns(cursor, rs, rt)
            left_cols = self._get_columns(cursor, ls, lt)
            right_cols = self._get_columns(cursor, rs, rt)

            conn.close()
            self.keys_loaded.emit(
                self.left_table, self.right_table,
                left_pks, right_pks, left_cols, right_cols)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


# ── ON Condition Row ─────────────────────────────────────────────────

class _OnConditionRow(QWidget):
    """Single ON condition: left_col = right_col."""
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


# ── Extra Condition Row ──────────────────────────────────────────────

class _ExtraConditionRow(QWidget):
    """Extra condition: table.column + expression (e.g., '= 1', '> 5', "IN ('A','B')")."""
    changed = pyqtSignal()
    remove_requested = pyqtSignal(object)

    def __init__(self, all_cols: list[str] | None = None, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        self.cmb_column = QComboBox()
        self.cmb_column.setFont(_FONT)
        self.cmb_column.setStyleSheet(_COMBO_STYLE)
        self.cmb_column.setFixedHeight(_H)
        self.cmb_column.setEditable(True)
        self.cmb_column.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Fixed)
        if all_cols:
            self.cmb_column.addItems(all_cols)
        lay.addWidget(self.cmb_column, 1)

        self.txt_expr = QLineEdit()
        self.txt_expr.setFont(_FONT)
        self.txt_expr.setStyleSheet(_INPUT_STYLE)
        self.txt_expr.setFixedHeight(_H)
        self.txt_expr.setPlaceholderText("= 1, > 5, IN ('A','B')")
        self.txt_expr.setSizePolicy(QSizePolicy.Policy.Expanding,
                                    QSizePolicy.Policy.Fixed)
        lay.addWidget(self.txt_expr, 1)

        self.btn_remove = QToolButton()
        self.btn_remove.setText("−")
        self.btn_remove.setFont(_FONT_BOLD)
        self.btn_remove.setFixedSize(18, _H)
        self.btn_remove.setStyleSheet(_BTN_DEL_STYLE)
        self.btn_remove.setToolTip("Remove condition")
        self.btn_remove.clicked.connect(lambda: self.remove_requested.emit(self))
        lay.addWidget(self.btn_remove)

        self.cmb_column.currentTextChanged.connect(lambda: self.changed.emit())
        self.txt_expr.textChanged.connect(lambda: self.changed.emit())

    def get_condition(self) -> tuple[str, str]:
        return (self.cmb_column.currentText().strip(),
                self.txt_expr.text().strip())

    def set_condition(self, column: str, expr: str):
        self.cmb_column.setCurrentText(column)
        self.txt_expr.setText(expr)

    def set_columns(self, all_cols: list[str]):
        cur = self.cmb_column.currentText()
        self.cmb_column.blockSignals(True)
        self.cmb_column.clear()
        self.cmb_column.addItems(all_cols)
        if cur:
            self.cmb_column.setCurrentText(cur)
        self.cmb_column.blockSignals(False)


# ── Join Card ────────────────────────────────────────────────────────

class JoinCard(QWidget):
    """Movable/resizable join card — placed on canvas with absolute positioning.

    Collapsed (single line):
      [grip] [☑] LEFT_TABLE INNER → RIGHT_TABLE (3 ON keys) [▼] [×]

    Expanded (full):
      [grip] [☑] [as] LEFT_TABLE [JOIN_TYPE] RIGHT_TABLE [as] [▼] [×]
      ON  [left_col = right_col] [−] [+]
      AND [column] [expr]        [−] [+]
      Status line

    Supports drag-to-move via grip area and resize via bottom-right handle.
    """
    state_changed = pyqtSignal()
    remove_requested = pyqtSignal(object)

    _next_id = 0

    def __init__(self, tables: list[str], dsn: str, parent=None):
        super().__init__(parent)
        JoinCard._next_id += 1
        self.card_id = f"join_{JoinCard._next_id}"

        self._dsn = dsn
        self._tables = list(tables)
        self._left_cols: list[str] = []
        self._right_cols: list[str] = []
        self._all_cols: list[str] = []
        self._loader: _KeyLoaderThread | None = None
        self._auto_matched = False
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

        # ── Row 1 (header): Checkbox + Tables + Join + Toggle + Remove ──
        r1 = QHBoxLayout()
        r1.setSpacing(3)
        r1.setContentsMargins(0, 0, 0, 0)

        self.chk_enabled = QCheckBox()
        self.chk_enabled.setChecked(True)
        self.chk_enabled.setFixedSize(16, 16)
        self.chk_enabled.setToolTip("Include this join in SQL")
        self.chk_enabled.setStyleSheet(
            "QCheckBox::indicator { border: 1px solid #1E5BA8;"
            " width: 12px; height: 12px; background-color: white; }"
            "QCheckBox::indicator:checked {"
            "  background-color: #1E5BA8; border: 1px solid #14407A;"
            "  image: url(" + _checkmark_path() + ");"
            "}")
        self.chk_enabled.toggled.connect(self._on_enabled_toggled)
        r1.addWidget(self.chk_enabled)

        self.txt_alias_left = QLineEdit()
        self.txt_alias_left.setFont(_FONT_SMALL)
        self.txt_alias_left.setStyleSheet(_INPUT_STYLE)
        self.txt_alias_left.setFixedSize(28, _H)
        self.txt_alias_left.setPlaceholderText("as")
        self.txt_alias_left.setToolTip("Left table alias")
        r1.addWidget(self.txt_alias_left)

        self.cmb_left_table = QComboBox()
        self.cmb_left_table.setFont(_FONT)
        self.cmb_left_table.setStyleSheet(_COMBO_STYLE)
        self.cmb_left_table.setFixedHeight(_H)
        self.cmb_left_table.setSizePolicy(QSizePolicy.Policy.Expanding,
                                          QSizePolicy.Policy.Fixed)
        self.cmb_left_table.addItems(self._tables)
        r1.addWidget(self.cmb_left_table, 1)

        self.cmb_join_type = QComboBox()
        self.cmb_join_type.setFont(_FONT_SMALL)
        self.cmb_join_type.setStyleSheet(_COMBO_JOIN_STYLE)
        self.cmb_join_type.setFixedHeight(_H)
        for short, full in zip(_JOIN_SHORT, _JOIN_TYPES):
            self.cmb_join_type.addItem(short, full)
        r1.addWidget(self.cmb_join_type)

        self.cmb_right_table = QComboBox()
        self.cmb_right_table.setFont(_FONT)
        self.cmb_right_table.setStyleSheet(_COMBO_STYLE)
        self.cmb_right_table.setFixedHeight(_H)
        self.cmb_right_table.setSizePolicy(QSizePolicy.Policy.Expanding,
                                           QSizePolicy.Policy.Fixed)
        self.cmb_right_table.addItems(self._tables)
        if len(self._tables) > 1:
            self.cmb_right_table.setCurrentIndex(1)
        r1.addWidget(self.cmb_right_table, 1)

        self.txt_alias_right = QLineEdit()
        self.txt_alias_right.setFont(_FONT_SMALL)
        self.txt_alias_right.setStyleSheet(_INPUT_STYLE)
        self.txt_alias_right.setFixedSize(28, _H)
        self.txt_alias_right.setPlaceholderText("as")
        self.txt_alias_right.setToolTip("Right table alias")
        r1.addWidget(self.txt_alias_right)

        # Collapse / expand toggle
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
        self.btn_remove.setToolTip("Remove this join")
        self.btn_remove.clicked.connect(self._confirm_remove)
        r1.addWidget(self.btn_remove)

        root.addLayout(r1)

        # ── Expandable body (hidden when collapsed) ──────────────
        self._body = QWidget()
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(2)

        # ON section
        r2 = QHBoxLayout()
        r2.setSpacing(2)
        r2.setContentsMargins(0, 0, 0, 0)
        lbl_on = QLabel("ON")
        lbl_on.setFont(_FONT_BOLD)
        lbl_on.setStyleSheet("color: #1E5BA8;")
        lbl_on.setFixedWidth(22)
        r2.addWidget(lbl_on)
        self._on_container = QVBoxLayout()
        self._on_container.setSpacing(1)
        self._on_container.setContentsMargins(0, 0, 0, 0)
        r2.addLayout(self._on_container, 1)
        self.btn_add_on = QToolButton()
        self.btn_add_on.setText("+")
        self.btn_add_on.setFont(_FONT_BOLD)
        self.btn_add_on.setFixedSize(18, _H)
        self.btn_add_on.setStyleSheet(_BTN_ADD_STYLE)
        self.btn_add_on.setToolTip("Add ON condition")
        self.btn_add_on.clicked.connect(self._add_on_row)
        r2.addWidget(self.btn_add_on, alignment=Qt.AlignmentFlag.AlignTop)
        body_lay.addLayout(r2)

        # Extra conditions section
        r3 = QHBoxLayout()
        r3.setSpacing(2)
        r3.setContentsMargins(0, 0, 0, 0)
        lbl_extra = QLabel("AND")
        lbl_extra.setFont(_FONT_BOLD)
        lbl_extra.setStyleSheet("color: #666;")
        lbl_extra.setFixedWidth(22)
        r3.addWidget(lbl_extra)
        self._extra_container = QVBoxLayout()
        self._extra_container.setSpacing(1)
        self._extra_container.setContentsMargins(0, 0, 0, 0)
        r3.addLayout(self._extra_container, 1)
        self.btn_add_extra = QToolButton()
        self.btn_add_extra.setText("+")
        self.btn_add_extra.setFont(_FONT_BOLD)
        self.btn_add_extra.setFixedSize(18, _H)
        self.btn_add_extra.setStyleSheet(_BTN_ADD_STYLE)
        self.btn_add_extra.setToolTip("Add extra condition")
        self.btn_add_extra.clicked.connect(self._add_extra_row)
        r3.addWidget(self.btn_add_extra, alignment=Qt.AlignmentFlag.AlignTop)
        body_lay.addLayout(r3)

        # Status line
        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet("color: #888;")
        body_lay.addWidget(self.lbl_status)

        root.addWidget(self._body)

        # ── Collapsed summary label (hidden when expanded) ───────
        self._lbl_summary = QLabel("")
        self._lbl_summary.setFont(_FONT_SMALL)
        self._lbl_summary.setStyleSheet("color: #666;")
        self._lbl_summary.setVisible(False)
        root.addWidget(self._lbl_summary)

        # ── ON/Extra condition rows ──────────────────────────────
        self._on_rows: list[_OnConditionRow] = []
        self._extra_rows: list[_ExtraConditionRow] = []
        self._add_on_row()

        # ── Wire signals ─────────────────────────────────────────
        self.cmb_left_table.currentTextChanged.connect(self._on_tables_changed)
        self.cmb_right_table.currentTextChanged.connect(self._on_tables_changed)
        self.cmb_join_type.currentIndexChanged.connect(
            lambda: self.state_changed.emit())
        self.txt_alias_left.textChanged.connect(lambda: self.state_changed.emit())
        self.txt_alias_right.textChanged.connect(lambda: self.state_changed.emit())

        if (self.cmb_left_table.currentText()
                and self.cmb_right_table.currentText()
                and self.cmb_left_table.currentText()
                    != self.cmb_right_table.currentText()):
            self._on_tables_changed()

    # ── Paint (border, grip, resize handle) ──────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        enabled = self.chk_enabled.isChecked()
        bg = _BG_ENABLED if enabled else _BG_DISABLED
        p.fillRect(self.rect(), bg)

        # Border
        pen = QPen(_BORDER_COLOR if enabled else _BORDER_COLOR_DISABLED)
        pen.setWidth(1)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # Grip area (left edge, dotted pattern)
        p.setPen(QPen(QColor("#999"), 1))
        gx = 3
        for gy in range(6, self.height() - 4, 4):
            p.drawPoint(gx, gy)
            p.drawPoint(gx + 3, gy + 2)

        # Resize handle (bottom-right triangle)
        rhs = _RESIZE_HANDLE
        tri = QPolygon([
            QPoint(self.width() - 1, self.height() - rhs),
            QPoint(self.width() - 1, self.height() - 1),
            QPoint(self.width() - rhs, self.height() - 1),
        ])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#1E5BA8") if enabled else QColor("#AAA"))
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
        # Cursor shape
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
            grid = self._grid()
            if grid:
                grid._update_canvas_bounds()
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
                grid = self._grid()
                if grid:
                    grid._drag_hotspot = self._drag_start
                self._drag_start = None
                drag.exec(Qt.DropAction.MoveAction)
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._resizing:
            self._resizing = False
            self._resize_start = None
            grid = self._grid()
            if grid:
                grid._sizes[self.card_id] = (self.width(), self.height())
                grid._update_canvas_bounds()
                grid.state_changed.emit()
            return
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def _grid(self):
        """Return parent JoinsTab if available."""
        p = self.parent()
        while p:
            if isinstance(p, JoinsTab):
                return p
            p = p.parent()
        return None

    # ── Right-click context menu ─────────────────────────────────

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { font-size: 8pt; }"
            "QMenu::item:selected { background: #E8F0FB; }")
        act_collapse = menu.addAction(
            "Expand" if self._collapsed else "Collapse")
        act_collapse.triggered.connect(self._toggle_collapse)
        menu.addSeparator()
        act_remove = menu.addAction("Remove Join")
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
        self._lbl_summary.setVisible(False)
        self.btn_toggle.setText("▼")
        self.setFixedSize(self.width(), _COLLAPSED_H)
        grid = self._grid()
        if grid:
            grid._sizes[self.card_id] = (self.width(), _COLLAPSED_H)
            grid._update_canvas_bounds()
        self.state_changed.emit()

    def _expand(self):
        self._collapsed = False
        self._body.setVisible(True)
        self._lbl_summary.setVisible(False)
        self.btn_toggle.setText("▲")
        h = self._pre_collapse_h or self.sizeHint().height()
        self.setFixedSize(self.width(), max(h, _COLLAPSED_H + 20))
        grid = self._grid()
        if grid:
            grid._sizes[self.card_id] = (self.width(), self.height())
            grid._update_canvas_bounds()
        self.state_changed.emit()

    def _update_summary(self):
        """Build collapsed summary text."""
        lt = self.cmb_left_table.currentText().split(".")[-1]
        rt = self.cmb_right_table.currentText().split(".")[-1]
        jt = self.cmb_join_type.currentText()
        n_on = sum(1 for r in self._on_rows
                   if r.get_pair()[0] and r.get_pair()[1])
        self._lbl_summary.setText(
            f"{lt} {jt}\u2192 {rt}  ({n_on} key{'s' if n_on != 1 else ''})")

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    # ── Confirm remove ────────────────────────────────────────────

    def _confirm_remove(self):
        lt = self.cmb_left_table.currentText().split(".")[-1]
        rt = self.cmb_right_table.currentText().split(".")[-1]
        ans = QMessageBox.question(
            self, "Remove Join",
            f"Remove join {lt} \u2194 {rt}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            self.remove_requested.emit(self)

    # ── Enable toggle ────────────────────────────────────────────

    def _on_enabled_toggled(self, checked: bool):
        self.update()  # repaint border/bg
        self.state_changed.emit()

    @property
    def enabled(self) -> bool:
        return self.chk_enabled.isChecked()

    # ── ON condition management ──────────────────────────────────

    def _add_on_row(self, left: str = "", right: str = ""):
        row = _OnConditionRow(self._left_cols, self._right_cols, self._body)
        if left or right:
            row.set_pair(left, right)
        row.changed.connect(self.state_changed.emit)
        row.remove_requested.connect(self._remove_on_row)
        self._on_rows.append(row)
        self._on_container.addWidget(row)
        self.state_changed.emit()

    def _remove_on_row(self, row: _OnConditionRow):
        if row in self._on_rows:
            self._on_rows.remove(row)
            self._on_container.removeWidget(row)
            row.deleteLater()
            self.state_changed.emit()

    # ── Extra condition management ───────────────────────────────

    def _add_extra_row(self, column: str = "", expr: str = ""):
        row = _ExtraConditionRow(self._all_cols, self._body)
        if column or expr:
            row.set_condition(column, expr)
        row.changed.connect(self.state_changed.emit)
        row.remove_requested.connect(self._remove_extra_row)
        self._extra_rows.append(row)
        self._extra_container.addWidget(row)
        self.state_changed.emit()

    def _remove_extra_row(self, row: _ExtraConditionRow):
        if row in self._extra_rows:
            self._extra_rows.remove(row)
            self._extra_container.removeWidget(row)
            row.deleteLater()
            self.state_changed.emit()

    # ── Table change → auto-key detection ────────────────────────

    def _on_tables_changed(self):
        left = self.cmb_left_table.currentText().strip()
        right = self.cmb_right_table.currentText().strip()
        if not left or not right or left == right:
            self.lbl_status.setText("")
            return

        self.lbl_status.setText("Loading keys...")
        self._loader = _KeyLoaderThread(self._dsn, left, right, self)
        self._loader.keys_loaded.connect(self._on_keys_loaded)
        self._loader.error_occurred.connect(self._on_keys_error)
        self._loader.start()

    def _on_keys_loaded(self, left_table, right_table, left_pks, right_pks,
                        left_cols, right_cols):
        # Store column lists for combo boxes
        self._left_cols = [c[0] for c in left_cols]
        self._right_cols = [c[0] for c in right_cols]
        self._all_cols = sorted(set(self._left_cols + self._right_cols))

        # Build type map for smarter matching
        left_type_map = {c[0]: c[1] for c in left_cols}
        right_type_map = {c[0]: c[1] for c in right_cols}

        # Update existing ON rows with column lists
        for row in self._on_rows:
            row.set_columns(self._left_cols, self._right_cols)
        for row in self._extra_rows:
            row.set_columns(self._all_cols)

        # Auto-match logic (only if no user edits yet)
        if not self._auto_matched:
            matches = self._find_key_matches(
                left_pks, right_pks,
                self._left_cols, self._right_cols,
                left_type_map, right_type_map)

            if matches:
                # Clear default empty ON row and populate with matches
                for row in list(self._on_rows):
                    self._on_rows.remove(row)
                    self._on_container.removeWidget(row)
                    row.deleteLater()

                for left_col, right_col in matches:
                    self._add_on_row(left_col, right_col)

                self._auto_matched = True
                self.lbl_status.setText(
                    f"Auto-matched {len(matches)} key"
                    f"{'s' if len(matches) > 1 else ''}: "
                    + ", ".join(f"{l}={r}" for l, r in matches))
            else:
                self.lbl_status.setText("No auto-match — set ON conditions manually")
        else:
            self.lbl_status.setText("")

        self._loader = None
        self.state_changed.emit()

    def _on_keys_error(self, msg: str):
        self.lbl_status.setText("Key load failed")
        logger.warning("Key loader error: %s", msg)
        self._loader = None

    @staticmethod
    def _find_key_matches(left_pks, right_pks, left_cols, right_cols,
                          left_types, right_types) -> list[tuple[str, str]]:
        """Find matching columns between two tables.

        Strategy:
        1. If both tables have PKs, match PK columns by name
        2. Fall back to column-name + type matching for common columns
        3. Prioritize known key patterns (CK_SYS_CD, POL_NUM, CO_CODE, etc.)
        """
        right_set = set(right_cols)
        matches = []
        seen = set()

        # Strategy 1: PK overlap
        if left_pks and right_pks:
            for col in left_pks:
                if col in right_set and col not in seen:
                    matches.append((col, col))
                    seen.add(col)

        # Strategy 2: Common column names with compatible types
        if not matches:
            # Known key column patterns (common DB2 join keys)
            _KEY_PATTERNS = {
                "CK_SYS_CD", "POL_NUM", "CO_CODE", "COV_SEQ_NUM",
                "PHA_SEQ_NUM", "BNF_SEQ_NUM", "CLT_NUM", "LOC_NUM",
                "POLICY_NUMBER", "COMPANY_CODE", "COVERAGE_NUMBER",
            }
            for col in left_cols:
                if col in right_set and col not in seen:
                    # Only auto-match if it's a known key pattern
                    # or types are compatible
                    if col in _KEY_PATTERNS:
                        matches.append((col, col))
                        seen.add(col)
                    elif (col in left_types and col in right_types
                          and left_types[col] == right_types[col]):
                        # Same name + same type — possible join key
                        # Only include if it looks like a key (short name,
                        # not a data column)
                        if any(kw in col.upper() for kw in (
                                "CD", "NUM", "ID", "KEY", "CODE", "SYS",
                                "SEQ", "TYPE", "NBR")):
                            matches.append((col, col))
                            seen.add(col)

        return matches

    # ── Update tables list (when group tables change) ────────────

    def update_tables(self, tables: list[str]):
        cur_left = self.cmb_left_table.currentText()
        cur_right = self.cmb_right_table.currentText()
        self._tables = list(tables)

        self.cmb_left_table.blockSignals(True)
        self.cmb_right_table.blockSignals(True)
        self.cmb_left_table.clear()
        self.cmb_left_table.addItems(tables)
        self.cmb_right_table.clear()
        self.cmb_right_table.addItems(tables)
        if cur_left in tables:
            self.cmb_left_table.setCurrentText(cur_left)
        if cur_right in tables:
            self.cmb_right_table.setCurrentText(cur_right)
        self.cmb_left_table.blockSignals(False)
        self.cmb_right_table.blockSignals(False)

    # ── State persistence ────────────────────────────────────────

    def get_state(self) -> dict:
        on_conds = []
        for row in self._on_rows:
            l, r = row.get_pair()
            if l or r:
                on_conds.append({"left": l, "right": r})

        extra_conds = []
        for row in self._extra_rows:
            col, expr = row.get_condition()
            if col or expr:
                extra_conds.append({"column": col, "expr": expr})

        return {
            "card_id": self.card_id,
            "enabled": self.chk_enabled.isChecked(),
            "collapsed": self._collapsed,
            "left_table": self.cmb_left_table.currentText(),
            "right_table": self.cmb_right_table.currentText(),
            "join_type": self.cmb_join_type.currentData(),
            "alias_left": self.txt_alias_left.text().strip(),
            "alias_right": self.txt_alias_right.text().strip(),
            "on_conditions": on_conds,
            "extra_conditions": extra_conds,
        }

    def set_state(self, state: dict):
        cid = state.get("card_id")
        if cid:
            self.card_id = cid
        self.chk_enabled.setChecked(state.get("enabled", True))
        lt = state.get("left_table", "")
        rt = state.get("right_table", "")
        if lt:
            self.cmb_left_table.setCurrentText(lt)
        if rt:
            self.cmb_right_table.setCurrentText(rt)

        jt = state.get("join_type", "INNER JOIN")
        idx = _JOIN_TYPES.index(jt) if jt in _JOIN_TYPES else 0
        self.cmb_join_type.setCurrentIndex(idx)

        self.txt_alias_left.setText(state.get("alias_left", ""))
        self.txt_alias_right.setText(state.get("alias_right", ""))

        # Clear and rebuild ON conditions
        for row in list(self._on_rows):
            self._on_rows.remove(row)
            self._on_container.removeWidget(row)
            row.deleteLater()
        for cond in state.get("on_conditions", []):
            self._add_on_row(cond.get("left", ""), cond.get("right", ""))

        # Clear and rebuild extra conditions
        for row in list(self._extra_rows):
            self._extra_rows.remove(row)
            self._extra_container.removeWidget(row)
            row.deleteLater()
        for cond in state.get("extra_conditions", []):
            self._add_extra_row(cond.get("column", ""), cond.get("expr", ""))

        self._auto_matched = True  # don't re-auto-match on restore

        if state.get("collapsed", False):
            self._collapse()

    # ── SQL generation helpers ───────────────────────────────────

    def get_join_info(self) -> dict | None:
        """Return join info for SQL generation, or None if disabled/incomplete."""
        if not self.chk_enabled.isChecked():
            return None

        left = self.cmb_left_table.currentText().strip()
        right = self.cmb_right_table.currentText().strip()
        if not left or not right:
            return None

        on_pairs = []
        for row in self._on_rows:
            l, r = row.get_pair()
            if l and r:
                on_pairs.append((l, r))
        if not on_pairs:
            return None

        extra = []
        for row in self._extra_rows:
            col, expr = row.get_condition()
            if col and expr:
                extra.append((col, expr))

        return {
            "left_table": left,
            "right_table": right,
            "join_type": self.cmb_join_type.currentData(),
            "alias_left": self.txt_alias_left.text().strip(),
            "alias_right": self.txt_alias_right.text().strip(),
            "on_pairs": on_pairs,
            "extra_conditions": extra,
        }


# ── Joins Tab (canvas-based) ────────────────────────────────────────

class JoinsTab(QScrollArea):
    """Tab with a free-form canvas of JoinCard widgets.

    Cards are positioned absolutely (like FieldGrid) with snap-to-grid,
    drag-to-move, and resize.  An '+ Add Join' button floats at the top.
    """
    state_changed = pyqtSignal()

    def __init__(self, tables: list[str] | None = None,
                 dsn: str = "", parent=None):
        super().__init__(parent)
        self._tables = list(tables or [])
        self._dsn = dsn
        self._cards: list[JoinCard] = []
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
            "border: 2px dashed #1E5BA8; background: transparent;")
        self._ghost.hide()

        # '+ Add Join' button pinned at top-left of canvas
        self.btn_add_join = QPushButton("+ Add Join", self._canvas)
        self.btn_add_join.setFont(_FONT_BOLD)
        self.btn_add_join.setFixedHeight(22)
        self.btn_add_join.setStyleSheet(_ADD_CARD_BTN_STYLE)
        self.btn_add_join.move(4, 4)
        self.btn_add_join.clicked.connect(self._add_card)

    @staticmethod
    def _snap(val: int) -> int:
        return round(val / _GRID_SNAP) * _GRID_SNAP

    def _default_position(self, idx: int) -> tuple[int, int]:
        """Stack cards vertically starting below the add button."""
        y = 32  # below add-join button
        for i, card in enumerate(self._cards):
            if i >= idx:
                break
            cid = card.card_id
            _, ch = self._sizes.get(cid, (0, 0))
            if ch <= 0:
                ch = card.sizeHint().height()
            y += ch + 8
        return (4, self._snap(y))

    def _add_card(self, state: dict | None = None) -> JoinCard:
        card = JoinCard(self._tables, self._dsn, parent=self._canvas)
        card.state_changed.connect(self._on_card_changed)
        card.remove_requested.connect(self._remove_card)

        if isinstance(state, dict):
            card.set_state(state)

        self._cards.append(card)

        # Position
        cid = card.card_id
        if cid not in self._positions:
            self._positions[cid] = self._default_position(len(self._cards) - 1)

        # Size
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

    def _remove_card(self, card: JoinCard):
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

    def _card_by_id(self, card_id: str) -> JoinCard | None:
        for card in self._cards:
            if card.card_id == card_id:
                return card
        return None

    # ── Update tables ────────────────────────────────────────────

    def update_tables(self, tables: list[str]):
        self._tables = list(tables)
        for card in self._cards:
            card.update_tables(tables)

    # ── Public accessors ─────────────────────────────────────────

    def get_join_infos(self) -> list[dict]:
        infos = []
        for card in self._cards:
            info = card.get_join_info()
            if info is not None:
                infos.append(info)
        return infos

    def get_state(self) -> dict:
        for card in self._cards:
            self._sizes[card.card_id] = (card.width(), card.height())
        return {
            "cards": [card.get_state() for card in self._cards],
            "positions": dict(self._positions),
            "sizes": {k: list(v) for k, v in self._sizes.items()},
        }

    def set_state(self, state: dict):
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

    def card_count(self) -> int:
        return len(self._cards)
