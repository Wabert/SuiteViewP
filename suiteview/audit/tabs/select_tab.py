"""
SelectTab — tab for managing SELECT columns in a dynamic audit query.

Each field is shown as a SelectFieldRow with a toggle button for aggregate
(display / COUNT / SUM / MIN / MAX) plus display name and Table.Field reference.
Fields dropped here always appear in the query SELECT list.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QMimeData, pyqtSignal, QPoint
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QDrag
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QCheckBox, QSizePolicy, QMenu, QFrame, QApplication,
)

from ._styles import make_checkbox

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_SMALL = QFont("Segoe UI", 8)
_FONT_KEY = QFont("Segoe UI", 7)

_AGGREGATES = ["display", "COUNT", "SUM", "MIN", "MAX"]

_TOGGLE_STYLE = (
    "QPushButton { font-size: 7pt; padding: 0px 4px;"
    " border: 1px solid #1E5BA8; border-radius: 2px;"
    " background-color: #E8F0FB; color: #1E5BA8;"
    " min-width: 48px; max-width: 60px; }"
    "QPushButton:hover { background-color: #C5D8F5; }"
)

_ROW_STYLE_NORMAL = "background-color: #f0f0f0;"
_ROW_STYLE_HOVER = "background-color: #E0E8F4;"

# MIME type — same as tables_dialog
FIELD_DRAG_MIME = "application/x-audit-field-drag"
REORDER_MIME = "application/x-select-row-reorder"


class SelectFieldRow(QFrame):
    """A single select-field entry: [toggle] DisplayName  (Table.Field)"""
    state_changed = pyqtSignal()

    def __init__(self, field_key: str, display_name: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.field_key = field_key       # e.g. "SAP.LDTI_TX7.POLNO"
        self._display_name = display_name
        self._agg_idx = 0                # index into _AGGREGATES
        self._drag_start_pos: QPoint | None = None

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(26)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet(
            "SelectFieldRow { border: 1px solid #C0C0C0;"
            " border-radius: 2px; background-color: #f0f0f0; }"
            "SelectFieldRow:hover { background-color: #E0E8F4; }"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)

        # Toggle button for aggregate
        self.btn_agg = QPushButton("display")
        self.btn_agg.setFont(QFont("Segoe UI", 7))
        self.btn_agg.setFixedSize(52, 18)
        self.btn_agg.setStyleSheet(_TOGGLE_STYLE)
        self.btn_agg.setToolTip(
            "Click to cycle: display → COUNT → SUM → MIN → MAX")
        self.btn_agg.clicked.connect(self._cycle_agg)
        # Right-click for direct pick
        self.btn_agg.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_agg.customContextMenuRequested.connect(self._show_agg_menu)
        lay.addWidget(self.btn_agg)

        # Display name label
        self.lbl_name = QLabel(display_name)
        self.lbl_name.setFont(_FONT_BOLD)
        self.lbl_name.setStyleSheet("color: black; background: transparent;")
        lay.addWidget(self.lbl_name)

        # Table.Field reference in parens
        self.lbl_key = QLabel(f"({field_key})")
        self.lbl_key.setFont(_FONT_KEY)
        self.lbl_key.setStyleSheet("color: #666; background: transparent;")
        lay.addWidget(self.lbl_key)

        lay.addStretch()

        # Remove button
        self.btn_remove = QPushButton("✕")
        self.btn_remove.setFont(QFont("Segoe UI", 7))
        self.btn_remove.setFixedSize(16, 16)
        self.btn_remove.setStyleSheet(
            "QPushButton { border: none; color: #999; background: transparent; }"
            "QPushButton:hover { color: #C00000; }")
        self.btn_remove.setToolTip("Remove from Select")
        lay.addWidget(self.btn_remove)

    # ── Aggregate toggle ─────────────────────────────────────────────

    @property
    def aggregate(self) -> str:
        return _AGGREGATES[self._agg_idx]

    def _cycle_agg(self):
        self._agg_idx = (self._agg_idx + 1) % len(_AGGREGATES)
        self.btn_agg.setText(_AGGREGATES[self._agg_idx])
        self.state_changed.emit()

    def _show_agg_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: white; border: 1px solid #1E5BA8;"
            " font-size: 9pt; }"
            "QMenu::item { padding: 3px 16px; }"
            "QMenu::item:selected { background-color: #A0C4E8; color: black; }"
        )
        actions = []
        for i, name in enumerate(_AGGREGATES):
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(i == self._agg_idx)
            actions.append((act, i))
        chosen = menu.exec(self.btn_agg.mapToGlobal(pos))
        if chosen:
            for act, idx in actions:
                if chosen is act:
                    self._agg_idx = idx
                    self.btn_agg.setText(_AGGREGATES[idx])
                    self.state_changed.emit()
                    break

    # ── State ────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        return {
            "field_key": self.field_key,
            "display_name": self._display_name,
            "aggregate": self._agg_idx,
        }

    def set_state(self, s: dict):
        self._agg_idx = s.get("aggregate", 0)
        self.btn_agg.setText(_AGGREGATES[self._agg_idx])
        dn = s.get("display_name", self._display_name)
        if dn:
            self._display_name = dn
            self.lbl_name.setText(dn)

    # ── Drag support (reorder) ───────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_start_pos is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                self._start_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self):
        self._drag_start_pos = None
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(REORDER_MIME, self.field_key.encode("utf-8"))
        drag.setMimeData(mime)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag.exec(Qt.DropAction.MoveAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)


class SelectTab(QScrollArea):
    """Tab for managing SELECT columns via drag-drop from Tables dialog."""
    state_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAcceptDrops(True)

        self._container = QWidget()
        self.setWidget(self._container)

        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(4)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── Display all fields checkbox ──────────────────────────────
        chk_row = QHBoxLayout()
        chk_row.setSpacing(12)
        chk_row.setContentsMargins(0, 0, 0, 0)

        self.chk_all_fields = make_checkbox("Display all fields")
        self.chk_all_fields.setToolTip(
            "When checked, SELECT * is used instead of specific columns")
        chk_row.addWidget(self.chk_all_fields)

        self.chk_distinct = make_checkbox("Show distinct")
        self.chk_distinct.setToolTip(
            "When checked, SELECT DISTINCT is used")
        chk_row.addWidget(self.chk_distinct)

        chk_row.addStretch()
        self._layout.addLayout(chk_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #C0C0C0;")
        self._layout.addWidget(sep)

        # Hint
        self._hint = QLabel("Drag fields here from the Tables dialog, "
                            "or double-click to add.")
        self._hint.setFont(QFont("Segoe UI", 8))
        self._hint.setStyleSheet("color: #888;")
        self._hint.setWordWrap(True)
        self._layout.addWidget(self._hint)

        # Stretch at bottom
        self._layout.addStretch()

        self._rows: list[SelectFieldRow] = []
        self._field_set: set[str] = set()  # quick lookup of existing keys

        # Drop indicator (landing bar)
        self._drop_indicator = QFrame(self._container)
        self._drop_indicator.setFixedHeight(3)
        self._drop_indicator.setStyleSheet(
            "background-color: #1E5BA8; border-radius: 1px;")
        self._drop_indicator.hide()

        # Connect checkboxes to state_changed
        self.chk_all_fields.stateChanged.connect(
            lambda: self.state_changed.emit())
        self.chk_distinct.stateChanged.connect(
            lambda: self.state_changed.emit())

    # ── Add / Remove fields ──────────────────────────────────────────

    def add_field(self, field_key: str, display_name: str):
        """Add a select field (no duplicates)."""
        if field_key in self._field_set:
            return
        row = SelectFieldRow(field_key, display_name, self._container)
        row.btn_remove.clicked.connect(lambda: self._remove_row(row))
        row.state_changed.connect(self.state_changed)
        self._rows.append(row)
        self._field_set.add(field_key)
        # Insert before the stretch
        idx = self._layout.count() - 1  # before the final stretch
        self._layout.insertWidget(idx, row)
        self._update_hint_visibility()
        self.state_changed.emit()

    def _remove_row(self, row: SelectFieldRow):
        self._rows.remove(row)
        self._field_set.discard(row.field_key)
        self._layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._update_hint_visibility()
        self.state_changed.emit()

    def _update_hint_visibility(self):
        self._hint.setVisible(len(self._rows) == 0)

    # ── Drag & drop ──────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(FIELD_DRAG_MIME) or md.hasFormat(REORDER_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(REORDER_MIME):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        elif md.hasFormat(FIELD_DRAG_MIME):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._drop_indicator.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drop_indicator.hide()
        md = event.mimeData()
        if md.hasFormat(REORDER_MIME):
            key = bytes(md.data(REORDER_MIME)).decode("utf-8")
            insert_idx = self._drop_index(event.position().toPoint())
            self._reorder_row(key, insert_idx)
            event.acceptProposedAction()
            return
        if md.hasFormat(FIELD_DRAG_MIME):
            data = bytes(event.mimeData().data(FIELD_DRAG_MIME)).decode("utf-8")
            # Support multi-field drops separated by newlines
            for line in data.split("\n"):
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|", 3)
                if len(parts) == 4:
                    table, column, type_name, display = parts
                    key = f"{table}.{column}"
                    self.add_field(key, display or column)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # ── Public API ───────────────────────────────────────────────────

    def get_select_columns(self) -> list[dict]:
        """Return list of {column, aggregate, field_key} for SQL building."""
        result = []
        for row in self._rows:
            parts = row.field_key.split(".")
            col = parts[-1] if parts else row.field_key
            result.append({
                "column": col,
                "field_key": row.field_key,
                "aggregate": row.aggregate,
            })
        return result

    # ── Internal reorder helpers ───────────────────────────────────

    def _drop_index(self, pos: QPoint) -> int:
        """Return the row index where a drop at *pos* should insert."""
        container_pos = self._container.mapFrom(self, pos)
        for i, row in enumerate(self._rows):
            row_mid = row.y() + row.height() // 2
            if container_pos.y() < row_mid:
                return i
        return len(self._rows)

    def _show_drop_indicator(self, pos: QPoint):
        """Position the landing-bar indicator between rows."""
        idx = self._drop_index(pos)
        if not self._rows:
            self._drop_indicator.hide()
            return
        if idx < len(self._rows):
            target_row = self._rows[idx]
            y = target_row.y() - 2
        else:
            last = self._rows[-1]
            y = last.y() + last.height() + 1
        self._drop_indicator.setGeometry(
            self._rows[0].x(), y,
            self._rows[0].width(), 3)
        self._drop_indicator.raise_()
        self._drop_indicator.show()

    def _reorder_row(self, field_key: str, new_idx: int):
        """Move an existing row to *new_idx* in the list."""
        row = None
        old_idx = -1
        for i, r in enumerate(self._rows):
            if r.field_key == field_key:
                row = r
                old_idx = i
                break
        if row is None:
            return
        if new_idx > old_idx:
            new_idx -= 1
        if new_idx == old_idx:
            return
        # Remove from layout and list
        self._layout.removeWidget(row)
        self._rows.pop(old_idx)
        # Re-insert at new position
        self._rows.insert(new_idx, row)
        # Layout index: rows start after checkbox-row, separator, and hint
        layout_base = self._layout.count() - 1 - len(self._rows)  # before stretch
        self._layout.insertWidget(layout_base + new_idx, row)
        self.state_changed.emit()

    @property
    def display_all(self) -> bool:
        return self.chk_all_fields.isChecked()

    @property
    def show_distinct(self) -> bool:
        return self.chk_distinct.isChecked()

    # ── State ────────────────────────────────────────────────────────

    def get_state(self) -> dict:
        return {
            "display_all": self.chk_all_fields.isChecked(),
            "show_distinct": self.chk_distinct.isChecked(),
            "fields": [r.get_state() for r in self._rows],
        }

    def set_state(self, s: dict):
        self.chk_all_fields.setChecked(s.get("display_all", False))
        self.chk_distinct.setChecked(s.get("show_distinct", False))
        # Clear existing
        for row in list(self._rows):
            self._remove_row(row)
        # Restore fields
        for fs in s.get("fields", []):
            key = fs.get("field_key", "")
            display = fs.get("display_name", key)
            self.add_field(key, display)
            if self._rows:
                self._rows[-1].set_state(fs)

    def clear(self):
        """Remove all fields."""
        for row in list(self._rows):
            self._remove_row(row)
        self.chk_all_fields.setChecked(False)
        self.chk_distinct.setChecked(False)
