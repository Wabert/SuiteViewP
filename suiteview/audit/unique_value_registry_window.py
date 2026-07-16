"""
Unique Value Registry Window — non-blocking themed viewer for registered values.

Left panel: compact navigation list of registered table.column entries
Right panel: sortable value table with description, notes, active flag,
             counts, and a More/Less toggle for extra columns.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QSortFilterProxyModel, pyqtSignal
from PyQt6.QtGui import QFont, QStandardItemModel, QStandardItem, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
    QTableView, QPushButton, QAbstractItemView, QMessageBox,
    QApplication, QMenu,
    QTableWidget, QTableWidgetItem,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from . import shared_field_registry as registry
from .tabs._styles import make_checkbox as _make_checkbox


def _database_display_name(source_dsn: str | None, database_name: str | None) -> str:
    """Derive a display label for the database node.

    Uses the ODBC DSN name when available, otherwise falls back to the
    stored database_name.
    """
    if source_dsn:
        return source_dsn
    if database_name:
        return database_name
    return "Unknown Database"

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_MONO = QFont("Consolas", 9)
_FONT_SMALL = QFont("Segoe UI", 8)

_HEADER_COLORS = ("#1E5BA8", "#0D3A7A", "#082B5C")
_BORDER_COLOR = "#D4A017"

# Tree node data roles
_ROLE_FIELD_ID = Qt.ItemDataRole.UserRole       # int  — field_id (leaf nodes)
_ROLE_DSN = Qt.ItemDataRole.UserRole + 1         # str  — ODBC DSN name
_ROLE_TABLE_NAME = Qt.ItemDataRole.UserRole + 2  # str  — qualified table name
_ROLE_NODE_TYPE = Qt.ItemDataRole.UserRole + 3   # str  — "db" | "table" | "field"

# Column indices — basic view
_COL_VALUE = 0
_COL_DESC = 1
_COL_ACTIVE = 2
_COL_COUNT = 3
_COL_PCT = 4
_COL_NOTES = 5
# Extended columns (shown in "More" mode)
_COL_FIRST_SEEN = 6
_COL_LAST_SEEN = 7
_COL_CREATED_BY = 8
_COL_CREATED_AT = 9
_COL_UPDATED_BY = 10
_COL_UPDATED_AT = 11

_ALL_HEADERS = [
    "Value", "Description", "Active", "Count", "% of Total", "Notes",
    "First Seen", "Last Seen", "Created By", "Created At",
    "Updated By", "Updated At",
]
_BASIC_COUNT = 6  # columns 0-5 visible in basic mode
_EXTENDED_COLS = list(range(_BASIC_COUNT, len(_ALL_HEADERS)))

# Style constants
_TREE_STYLE = (
    "QTreeWidget { border: 1px solid #1E5BA8; background-color: white;"
    "  font-size: 9pt; }"
    "QTreeWidget::item { padding: 1px 4px; }"
    "QTreeWidget::item:selected { background-color: #A0C4E8; color: black; }"
    "QTreeWidget::item:hover { background-color: #D6E8FA; }"
    "QHeaderView::section { background-color: #E8F0FB; color: #0A1E5E;"
    "  font-size: 8pt; font-weight: bold; padding: 2px 6px;"
    "  border: none; border-bottom: 1px solid #1E5BA8;"
    "  border-right: 1px solid #C8D8E8; }"
)

_TABLE_STYLE = (
    "QTableView { border: 1px solid #1E5BA8; background-color: white;"
    "  gridline-color: #D0D8E0; font-size: 9pt; }"
    "QTableView::item { padding: 1px 6px; }"
    "QTableView::item:selected { background-color: #D6E8FA; color: black; }"
    "QTableView::item:focus { background-color: #D6E8FA; color: black;"
    "  outline: none; border: none; }"
    "QHeaderView::section { background-color: #E8F0FB; color: #0A1E5E;"
    "  font-size: 8pt; font-weight: bold; padding: 2px 6px;"
    "  border: none; border-bottom: 1px solid #1E5BA8;"
    "  border-right: 1px solid #C8D8E8; }"
)

_SETTINGS_PATH = Path.home() / ".suiteview" / "registry_window_geometry.json"

_BTN_STYLE = (
    "QPushButton { background-color: #1E5BA8; color: white;"
    " border: 1px solid #14407A; border-radius: 2px;"
    " padding: 2px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #2A6BC4; }"
    "QPushButton:disabled { background-color: #A0A0A0; border: 1px solid #888; }"
)

_BTN_RED_STYLE = (
    "QPushButton { background-color: #C00000; color: white;"
    " border: 1px solid #900; border-radius: 2px;"
    " padding: 2px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #E00000; }"
    "QPushButton:disabled { background-color: #A0A0A0; border: 1px solid #888; }"
)

_BTN_TOGGLE_STYLE = (
    "QPushButton { background-color: #E8F0FB; color: #1E5BA8;"
    " border: 1px solid #1E5BA8; border-radius: 2px;"
    " padding: 2px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #C5D8F5; }"
)

_BTN_GREEN_STYLE = (
    "QPushButton { background-color: #2E7D32; color: white;"
    " border: 1px solid #1B5E20; border-radius: 2px;"
    " padding: 2px 12px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #388E3C; }"
    "QPushButton:disabled { background-color: #A0A0A0; border: 1px solid #888; }"
)

_INACTIVE_FG = QColor("#999999")


class _NumericSortItem(QStandardItem):
    """QStandardItem that sorts numerically when the data is an int."""

    def __lt__(self, other):
        try:
            return int(self.text().replace(",", "")) < int(other.text().replace(",", ""))
        except (ValueError, AttributeError):
            return super().__lt__(other)


class RegistryValueEditorWindow(FramelessWindowBase):
    """Pop-out datagrid editor for a single field's registered values.

    Shows Value (read-only), Description, Active, and Notes. The Value is
    never editable but is included on Excel export so it can drive VLOOKUPs.
    Paste anchors at the selected row and only writes the Description, Active,
    and Notes columns, never running past the last existing row.
    """

    values_changed = pyqtSignal()

    # Editable column indices in this editor's grid.
    COL_VALUE = 0
    COL_DESC = 1
    COL_ACTIVE = 2
    COL_NOTES = 3
    _HEADERS = ["Value", "Description", "Active", "Notes"]
    # Clipboard columns map onto these grid columns, in order.
    _PASTE_TARGET_COLS = (COL_DESC, COL_ACTIVE, COL_NOTES)
    _ACTIVE_TRUE = {"1", "y", "yes", "true", "t", "active", "x", "\u2713"}

    def __init__(self, field_id: int, field_label: str, parent=None):
        self._field_id = field_id
        self._field_label = field_label
        self._dirty = False
        super().__init__(
            title=f"Edit Values \u2014 {field_label}",
            default_size=(760, 560),
            min_size=(520, 360),
            parent=parent,
            header_colors=_HEADER_COLORS,
            border_color=_BORDER_COLOR,
        )
        self._load_rows()

    # ── UI ────────────────────────────────────────────────────────────

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet("QWidget { background-color: #F0F0F0; }")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(5)

        lbl = QLabel(self._field_label)
        lbl.setFont(_FONT_BOLD)
        lbl.setStyleSheet("color: #0A1E5E; padding: 2px 0px;")
        lay.addWidget(lbl)

        # ── Action row ───────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(6)
        btn_paste = QPushButton("Paste")
        btn_paste.setFont(_FONT_SMALL)
        btn_paste.setFixedHeight(22)
        btn_paste.setStyleSheet(_BTN_STYLE)
        btn_paste.setToolTip(
            "Paste Description / Active / Notes from a copied Excel selection,"
            " starting at the selected row")
        btn_paste.clicked.connect(self._on_paste)
        actions.addWidget(btn_paste)

        btn_export = QPushButton("Export to Excel")
        btn_export.setFont(_FONT_SMALL)
        btn_export.setFixedHeight(22)
        btn_export.setStyleSheet(_BTN_STYLE)
        btn_export.setToolTip(
            "Export Value, Description, Active and Notes to an Excel workbook")
        btn_export.clicked.connect(self._on_export)
        actions.addWidget(btn_export)

        actions.addStretch()

        btn_save = QPushButton("Save")
        btn_save.setFont(_FONT_SMALL)
        btn_save.setFixedHeight(22)
        btn_save.setStyleSheet(_BTN_GREEN_STYLE)
        btn_save.clicked.connect(self._on_save)
        actions.addWidget(btn_save)
        lay.addLayout(actions)

        # ── Grid ─────────────────────────────────────────────────────
        self.table = QTableWidget(0, len(self._HEADERS))
        self.table.setHorizontalHeaderLabels(self._HEADERS)
        self.table.setFont(_FONT)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(20)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(self.COL_VALUE, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(self.COL_DESC, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_ACTIVE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self.COL_NOTES, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        active_hdr = self.table.horizontalHeaderItem(self.COL_ACTIVE)
        if active_hdr is not None:
            active_hdr.setToolTip("Type Yes/No (TRUE/FALSE or 1/0 also accepted)")
        lay.addWidget(self.table, 1)

        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet("color: #666; font-size: 8pt;")
        lay.addWidget(self.lbl_info)
        return body

    # ── Data ──────────────────────────────────────────────────────────

    def reload(self, field_id: int, field_label: str) -> None:
        """Point the editor at a different field and reload its values."""
        self._field_id = field_id
        self._field_label = field_label
        title = f"Edit Values \u2014 {field_label}"
        self.setWindowTitle(title)
        if hasattr(self, "_window_title_text"):
            self._window_title_text = title
        if hasattr(self, "_title_label"):
            self._title_label.setText(title)
        self._load_rows()

    def _load_rows(self) -> None:
        rows = registry.get_values_full(self._field_id, include_inactive=True)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for rec in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)

            item_val = QTableWidgetItem(rec.get("field_value") or "")
            item_val.setFlags(item_val.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_val.setData(Qt.ItemDataRole.UserRole, rec["value_id"])
            self.table.setItem(r, self.COL_VALUE, item_val)

            self.table.setItem(
                r, self.COL_DESC,
                QTableWidgetItem(rec.get("value_description") or ""))

            item_active = QTableWidgetItem(
                self._active_text(bool(rec.get("is_active", 1))))
            item_active.setFlags(
                item_active.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item_active.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, self.COL_ACTIVE, item_active)

            self.table.setItem(
                r, self.COL_NOTES, QTableWidgetItem(rec.get("notes") or ""))

        self.table.blockSignals(False)
        self._dirty = False
        self.lbl_info.setText(f"{self.table.rowCount()} value(s)")

    def _mark_dirty(self) -> None:
        self._dirty = True

    @staticmethod
    def _active_text(active: bool) -> str:
        return "Yes" if active else "No"

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Mark dirty and normalize the Active cell to Yes/No on edit."""
        self._dirty = True
        if item.column() == self.COL_ACTIVE:
            normalized = self._active_text(self._parse_active(item.text()))
            if item.text() != normalized:
                self.table.blockSignals(True)
                item.setText(normalized)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.blockSignals(False)

    # ── Paste ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_clipboard(text: str) -> list[list[str]]:
        """Split clipboard text into a grid of rows/cells (Excel TSV)."""
        if not text:
            return []
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()  # Excel appends a trailing newline
        return [line.split("\t") for line in lines]

    @classmethod
    def _parse_active(cls, text: str) -> bool:
        return str(text).strip().lower() in cls._ACTIVE_TRUE

    def _on_paste(self) -> None:
        grid = self._parse_clipboard(QApplication.clipboard().text())
        if not grid:
            return
        anchor = self.table.currentRow()
        if anchor < 0:
            anchor = 0
        self.table.blockSignals(True)
        written = 0
        for i, cells in enumerate(grid):
            row = anchor + i
            if row >= self.table.rowCount():
                break  # never run past the last existing row
            for col, value in zip(self._PASTE_TARGET_COLS, cells):
                if col == self.COL_ACTIVE:
                    self.table.item(row, col).setText(
                        self._active_text(self._parse_active(value)))
                else:
                    self.table.item(row, col).setText(value)
            written += 1
        self.table.blockSignals(False)
        self._dirty = True
        self.lbl_info.setText(
            f"Pasted into {written} row(s) starting at row {anchor + 1}")

    # ── Export ────────────────────────────────────────────────────────

    def _collect_export_rows(self) -> list[list[str]]:
        out = []
        for r in range(self.table.rowCount()):
            active = self._parse_active(self.table.item(r, self.COL_ACTIVE).text())
            out.append([
                self.table.item(r, self.COL_VALUE).text(),
                self.table.item(r, self.COL_DESC).text(),
                self._active_text(active),
                self.table.item(r, self.COL_NOTES).text(),
            ])
        return out

    def _on_export(self) -> None:
        rows = self._collect_export_rows()
        if not rows:
            QMessageBox.information(self, "Export", "No data to export.")
            return
        try:
            from suiteview.core.excel_export import (
                dump_to_new_workbook, ExcelExportError)
            sheet = self._field_label.replace(".", "_")
            # Value is column 1 — force text so leading-zero codes are preserved.
            dump_to_new_workbook(
                self._HEADERS, rows, sheet_name=sheet, text_col_indexes=[1])
        except ExcelExportError as exc:
            QMessageBox.warning(self, "Excel Error", str(exc))
        except Exception as exc:
            logger.exception("Registry value editor Excel export failed")
            QMessageBox.warning(self, "Excel Error", f"Could not export:\n{exc}")

    # ── Save ──────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        try:
            for r in range(self.table.rowCount()):
                value_id = self.table.item(r, self.COL_VALUE).data(
                    Qt.ItemDataRole.UserRole)
                active = self._parse_active(
                    self.table.item(r, self.COL_ACTIVE).text())
                registry.update_value(
                    value_id,
                    value_description=self.table.item(r, self.COL_DESC).text(),
                    notes=self.table.item(r, self.COL_NOTES).text(),
                    is_active=1 if active else 0,
                )
        except Exception as exc:
            logger.exception("Failed to save registry values")
            QMessageBox.warning(self, "Save Error", str(exc))
            return
        self._dirty = False
        self.values_changed.emit()
        self.lbl_info.setText("Saved.")


class UniqueValueRegistryWindow(FramelessWindowBase):
    """Non-blocking registry viewer window."""

    _instance = None  # singleton reference

    def __init__(self, parent=None):
        saved = self._load_geometry_settings()
        self._current_field_id = None
        self._expanded = False  # More/Less state
        self._show_inactive = False
        self._value_rows: list[dict] = []  # raw data backing the model
        # (dsn, table_name) while the column list is shown; None otherwise
        self._table_columns_context: tuple[str, str] | None = None
        super().__init__(
            title="Unique Value Registry",
            default_size=(saved.get("w", 1100), saved.get("h", 540)),
            min_size=(620, 360),
            parent=parent,
            header_colors=_HEADER_COLORS,
            border_color=_BORDER_COLOR,
        )
        if "x" in saved and "y" in saved:
            self.move(saved["x"], saved["y"])
        try:
            self._load_registrations()
        except Exception:
            logger.exception("Failed to load registrations on startup")

    @classmethod
    def show_instance(cls, parent=None):
        """Show or raise the singleton window."""
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(parent)
            cls._instance.show()
        else:
            cls._instance.raise_()
            cls._instance.activateWindow()
        return cls._instance

    # ── UI construction ──────────────────────────────────────────────

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet("QWidget { background-color: #F0F0F0; }")
        root = QVBoxLayout(body)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(4)

        # ── Toolbar ──────────────────────────────────────────────────
        toolbar_widget = QWidget()
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(6)

        self.btn_refresh = QPushButton("Refresh All")
        self.btn_refresh.setFont(_FONT_SMALL)
        self.btn_refresh.setFixedHeight(22)
        self.btn_refresh.setStyleSheet(_BTN_STYLE)
        self.btn_refresh.setToolTip("Re-query all registered fields from the database")
        self.btn_refresh.clicked.connect(self._refresh_all)
        toolbar.addWidget(self.btn_refresh)

        toolbar.addStretch()

        self.lbl_summary = QLabel("")
        self.lbl_summary.setFont(_FONT_SMALL)
        self.lbl_summary.setStyleSheet("color: #666;")
        toolbar.addWidget(self.lbl_summary)

        self._toolbar_panel = toolbar_widget

        # ── Splitter: left nav tree + right value table ──────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        self._splitter = splitter

        # LEFT: Navigation tree grouped by table
        left_panel = QWidget()
        left_lay = QVBoxLayout(left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(2)

        lbl_nav = QLabel("Registered Fields")
        lbl_nav.setFont(_FONT_BOLD)
        lbl_nav.setStyleSheet("color: #0A1E5E; padding: 2px 0px;")
        left_lay.addWidget(lbl_nav)

        self.tree = QTreeWidget()
        self.tree.setFont(_FONT)
        self.tree.setHeaderLabels(["Table / Column", "Values", "Updated"])
        self.tree.setStyleSheet(_TREE_STYLE)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIndentation(14)
        self.tree.header().setDefaultSectionSize(130)
        self.tree.header().resizeSection(1, 50)
        self.tree.header().resizeSection(2, 80)
        self.tree.header().setStretchLastSection(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.currentItemChanged.connect(self._on_tree_selection_changed)
        self.tree.currentItemChanged.connect(self._sync_edit_window_button)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        left_lay.addWidget(self.tree)

        self._nav_panel = left_panel
        splitter.addWidget(left_panel)

        # RIGHT: Value table + stats + buttons
        right_panel = QWidget()
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(2)

        # Header row with field name and stats
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.lbl_field_title = QLabel("Select a field \u2192")
        self.lbl_field_title.setFont(_FONT_BOLD)
        self.lbl_field_title.setStyleSheet("color: #0A1E5E; padding: 2px 0px;")
        header_row.addWidget(self.lbl_field_title)

        header_row.addStretch()

        self.lbl_stats = QLabel("")
        self.lbl_stats.setFont(_FONT_SMALL)
        self.lbl_stats.setStyleSheet("color: #666;")
        header_row.addWidget(self.lbl_stats)

        right_lay.addLayout(header_row)

        # Value action bar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(6)

        self.btn_export = QPushButton("Export to Excel")
        self.btn_export.setFont(_FONT_SMALL)
        self.btn_export.setFixedHeight(22)
        self.btn_export.setStyleSheet(_BTN_STYLE)
        self.btn_export.setToolTip("Export all values to an Excel workbook")
        self.btn_export.clicked.connect(self._export_values_to_excel)
        self.btn_export.setEnabled(False)
        action_bar.addWidget(self.btn_export)

        self.btn_edit_window = QPushButton("\u270e  Edit in Window")
        self.btn_edit_window.setFont(_FONT_SMALL)
        self.btn_edit_window.setFixedHeight(22)
        self.btn_edit_window.setStyleSheet(_BTN_GREEN_STYLE)
        self.btn_edit_window.setToolTip(
            "Open the selected field's values in an editable datagrid window"
            " (Value is read-only; paste/edit Description, Active and Notes)")
        self.btn_edit_window.clicked.connect(self._open_value_editor_window)
        self.btn_edit_window.setEnabled(False)
        action_bar.addWidget(self.btn_edit_window)

        action_bar.addStretch()

        self.chk_inactive = _make_checkbox("Show Inactive")
        self.chk_inactive.setToolTip("Include inactive values in the table")
        self.chk_inactive.toggled.connect(self._toggle_inactive)
        action_bar.addWidget(self.chk_inactive)

        self.btn_more = QPushButton("More \u25b6")
        self.btn_more.setFont(_FONT_SMALL)
        self.btn_more.setFixedHeight(22)
        self.btn_more.setStyleSheet(_BTN_TOGGLE_STYLE)
        self.btn_more.setToolTip("Show/hide additional columns")
        self.btn_more.clicked.connect(self._toggle_more)
        action_bar.addWidget(self.btn_more)

        right_lay.addLayout(action_bar)

        # Value table (sortable, editable on description/notes)
        self.value_model = QStandardItemModel()
        self.value_model.setHorizontalHeaderLabels(_ALL_HEADERS)
        self.value_model.itemChanged.connect(self._on_item_changed)

        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.value_model)

        self.value_table = QTableView()
        self.value_table.setModel(self.proxy_model)
        self.value_table.setFont(_FONT_MONO)
        self.value_table.setStyleSheet(_TABLE_STYLE)
        self.value_table.setSortingEnabled(True)
        self.value_table.setAlternatingRowColors(True)
        self.value_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.value_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.value_table.verticalHeader().setDefaultSectionSize(20)
        self.value_table.verticalHeader().setVisible(False)
        self.value_table.horizontalHeader().setStretchLastSection(True)
        self.value_table.horizontalHeader().setDefaultSectionSize(100)
        self.value_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.value_table.customContextMenuRequested.connect(
            self._on_value_table_context_menu)
        right_lay.addWidget(self.value_table)

        self._canvas_panel = QWidget()
        canvas_lay = QVBoxLayout(self._canvas_panel)
        canvas_lay.setContentsMargins(0, 0, 0, 0)
        canvas_lay.setSpacing(4)
        canvas_lay.addWidget(toolbar_widget)
        canvas_lay.addWidget(right_panel, 1)
        splitter.addWidget(self._canvas_panel)

        # Set initial splitter proportions (25% nav, 75% values)
        splitter.setSizes([220, 600])
        root.addWidget(splitter, 1)

        # Hide extended columns by default
        self._apply_column_visibility()

        return body

    # ── Column visibility ────────────────────────────────────────────

    def _apply_column_visibility(self):
        for col in _EXTENDED_COLS:
            self.value_table.setColumnHidden(col, not self._expanded)

    def _toggle_more(self):
        self._expanded = not self._expanded
        self.btn_more.setText("\u25c0 Less" if self._expanded else "More \u25b6")
        self._apply_column_visibility()

    def _toggle_inactive(self, checked: bool):
        self._show_inactive = checked
        if self._current_field_id is not None:
            self._show_values(self._current_field_id)

    # ── Data loading ─────────────────────────────────────────────────

    def _load_registrations(self):
        """Populate the left navigation tree from the registry.

        Three-level hierarchy: Database (DSN) → Table → Field.
        Database and Table nodes are selectable — clicking them shows
        connection details or table columns respectively.
        """
        self.tree.clear()
        regs = registry.list_registrations()

        # Group by database → table → fields
        # Also track the DSN used per db_label
        db_groups: dict[str, dict[str, list[dict]]] = {}
        db_dsn_map: dict[str, str] = {}  # db_label → source_dsn
        for r in regs:
            db_label = _database_display_name(
                r.get("source_dsn"), r.get("database_name"))
            table_name = r["table_name"]
            db_groups.setdefault(db_label, {}).setdefault(table_name, []).append(r)
            if r.get("source_dsn"):
                db_dsn_map[db_label] = r["source_dsn"]

        total_registrations = len(regs)
        total_tables = sum(len(tables) for tables in db_groups.values())

        for db_label, table_groups in sorted(db_groups.items()):
            dsn_name = db_dsn_map.get(db_label, db_label)

            # Database node (top level) — selectable to show ODBC details
            db_node = QTreeWidgetItem(self.tree)
            db_node.setText(0, db_label)
            db_node.setFont(0, _FONT_BOLD)
            db_node.setForeground(0, QColor("#0A1E5E"))
            db_node.setExpanded(True)
            db_node.setData(0, _ROLE_NODE_TYPE, "db")
            db_node.setData(0, _ROLE_DSN, dsn_name)

            for table_name, items in sorted(table_groups.items()):
                # Table node (second level) — selectable to show columns
                table_node = QTreeWidgetItem(db_node)
                table_node.setText(0, table_name)
                table_node.setFont(0, _FONT_BOLD)
                table_node.setForeground(0, QColor("#1E5BA8"))
                table_node.setExpanded(True)
                table_node.setData(0, _ROLE_NODE_TYPE, "table")
                table_node.setData(0, _ROLE_DSN, dsn_name)
                table_node.setData(0, _ROLE_TABLE_NAME, table_name)

                # Collect registered column names for this table
                registered_cols = {r["column_name"] for r in items}
                table_node.setData(
                    0, _ROLE_FIELD_ID, None)  # no field_id for table nodes
                table_node.setToolTip(
                    0,
                    f"{table_name}\n"
                    f"{len(items)} registered field(s)\n"
                    f"{len(registered_cols)} unique column(s)",
                )

                for reg in items:
                    child = QTreeWidgetItem(table_node)
                    child.setText(0, reg["display_name"] or reg["column_name"])
                    child.setText(1, str(reg["value_count"]))
                    # Format timestamp compactly
                    try:
                        ts = reg.get("last_scanned_at")
                        if ts:
                            dt = datetime.fromisoformat(str(ts))
                            child.setText(2, dt.strftime("%m/%d %H:%M"))
                        else:
                            child.setText(2, "\u2014")
                    except (ValueError, TypeError):
                        child.setText(2, "\u2014")
                    child.setData(0, _ROLE_FIELD_ID, reg["field_id"])
                    child.setData(0, _ROLE_NODE_TYPE, "field")
                    child.setData(0, _ROLE_DSN, dsn_name)
                    child.setData(0, _ROLE_TABLE_NAME, table_name)
                    child.setToolTip(
                        0,
                        f"{reg['table_name']}.{reg['column_name']}\n"
                        f"{reg['value_count']} unique values\n"
                        f"Last scanned: {reg.get('last_scanned_at', '\u2014')}",
                    )

        self.lbl_summary.setText(
            f"{total_registrations} registration(s) across "
            f"{total_tables} table(s) in {len(db_groups)} database(s)")

    def _show_values(self, field_id: int):
        """Load and display values for the selected field."""
        self._current_field_id = field_id
        self._table_columns_context = None
        self._value_rows = registry.get_values_full(
            field_id, include_inactive=self._show_inactive)

        # Disconnect itemChanged while populating to avoid triggering edits
        # (blockSignals would starve the proxy model of rowsInserted signals)
        self.value_model.itemChanged.disconnect(self._on_item_changed)
        self.value_model.clear()
        self.value_model.setHorizontalHeaderLabels(_ALL_HEADERS)

        total_count = sum(
            (r.get("occurrence_count") or 0) for r in self._value_rows)

        for rec in self._value_rows:
            count = rec.get("occurrence_count") or 0
            active = rec.get("is_active", 1)

            # Value (read-only)
            item_val = QStandardItem(rec.get("field_value") or "")
            item_val.setEditable(False)
            item_val.setData(rec["value_id"], Qt.ItemDataRole.UserRole)

            # Description (editable)
            item_desc = QStandardItem(rec.get("value_description") or "")
            item_desc.setEditable(True)

            # Active (read-only display)
            item_active = QStandardItem("Yes" if active else "No")
            item_active.setEditable(False)
            item_active.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

            # Count (read-only)
            item_cnt = _NumericSortItem(f"{count:,}" if count else "")
            item_cnt.setEditable(False)
            item_cnt.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # % of Total (read-only)
            pct = (count / total_count * 100) if total_count > 0 else 0
            item_pct = _NumericSortItem(f"{pct:.1f}%")
            item_pct.setEditable(False)
            item_pct.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            # Notes (editable)
            item_notes = QStandardItem(rec.get("notes") or "")
            item_notes.setEditable(True)

            # Extended columns (all read-only)
            def _ts(val):
                if not val:
                    return "\u2014"
                try:
                    return datetime.fromisoformat(str(val)).strftime(
                        "%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    return str(val)

            item_first = QStandardItem(_ts(rec.get("first_seen_at")))
            item_first.setEditable(False)
            item_last = QStandardItem(_ts(rec.get("last_seen_at")))
            item_last.setEditable(False)
            item_cby = QStandardItem(rec.get("created_by") or "")
            item_cby.setEditable(False)
            item_cat = QStandardItem(_ts(rec.get("created_at")))
            item_cat.setEditable(False)
            item_uby = QStandardItem(rec.get("updated_by") or "")
            item_uby.setEditable(False)
            item_uat = QStandardItem(_ts(rec.get("updated_at")))
            item_uat.setEditable(False)

            row_items = [item_val, item_desc, item_active, item_cnt,
                         item_pct, item_notes, item_first, item_last,
                         item_cby, item_cat, item_uby, item_uat]

            # Grey out inactive rows
            if not active:
                for item in row_items:
                    item.setForeground(_INACTIVE_FG)

            self.value_model.appendRow(row_items)

        self.value_model.itemChanged.connect(self._on_item_changed)

        # Column sizing
        self.value_table.resizeColumnsToContents()
        hdr = self.value_table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(_COL_VALUE, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_DESC, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_ACTIVE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_COUNT, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_PCT, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_NOTES, QHeaderView.ResizeMode.Stretch)
        for c in _EXTENDED_COLS:
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        # Re-apply hidden state
        self._apply_column_visibility()

        # Stats
        active_count = sum(1 for r in self._value_rows if r.get("is_active", 1))
        inactive_count = len(self._value_rows) - active_count
        stats = f"{active_count} active"
        if inactive_count:
            stats += f"  |  {inactive_count} inactive"
        stats += f"  |  {total_count:,} total rows"
        self.lbl_stats.setText(stats)

        # Enable export when there are values to export
        self.btn_export.setEnabled(len(self._value_rows) > 0)

        # Default sort by count descending
        self.value_table.sortByColumn(_COL_COUNT, Qt.SortOrder.DescendingOrder)

    # ── Inline editing ───────────────────────────────────────────────

    def _on_item_changed(self, item: QStandardItem):
        """Persist description or notes edits to SQL Server."""
        # Column-notes context: the value table is showing a table's columns.
        if self._table_columns_context is not None:
            if item.column() != 1:  # only the Notes column is editable here
                return
            dsn, table_name = self._table_columns_context
            col_name = item.data(Qt.ItemDataRole.UserRole)
            if not col_name:
                return
            try:
                registry.set_column_note(
                    dsn, table_name, str(col_name), item.text().strip())
            except Exception as exc:
                logger.error("Failed to save note for %s.%s: %s",
                             table_name, col_name, exc)
                QMessageBox.warning(self, "Save Error",
                                    f"Could not save note:\n\n{exc}")
            return
        col = item.column()
        if col not in (_COL_DESC, _COL_NOTES):
            return
        row = item.row()
        val_item = self.value_model.item(row, _COL_VALUE)
        if val_item is None:
            return
        value_id = val_item.data(Qt.ItemDataRole.UserRole)
        if value_id is None:
            return
        try:
            if col == _COL_DESC:
                registry.update_value(value_id,
                                      value_description=item.text().strip() or None)
            elif col == _COL_NOTES:
                registry.update_value(value_id,
                                      notes=item.text().strip() or None)
        except Exception as exc:
            logger.error("Failed to update value %s: %s", value_id, exc)
            QMessageBox.warning(self, "Save Error",
                                f"Could not save change:\n\n{exc}")

    # ── Slots ────────────────────────────────────────────────────────

    def _on_tree_selection_changed(self, current, _previous):
        if current is None:
            return
        node_type = current.data(0, _ROLE_NODE_TYPE)

        if node_type == "field":
            reg_id = current.data(0, _ROLE_FIELD_ID)
            if reg_id is None:
                return
            parent = current.parent()
            table_name = parent.text(0) if parent else ""
            col_name = current.text(0)
            self.lbl_field_title.setText(f"{table_name}.{col_name}")
            self._show_values(reg_id)
        elif node_type == "table":
            dsn = current.data(0, _ROLE_DSN) or ""
            table_name = current.data(0, _ROLE_TABLE_NAME) or current.text(0)
            self._show_table_columns(dsn, table_name, current)
        elif node_type == "db":
            dsn = current.data(0, _ROLE_DSN) or current.text(0)
            self._show_dsn_details(dsn)

    def _show_table_columns(self, dsn: str, table_name: str,
                            table_node: QTreeWidgetItem):
        """Show all columns of the table; highlight registered ones."""
        self._current_field_id = None
        self._table_columns_context = (dsn, table_name)
        self.lbl_field_title.setText(f"{table_name}  (all columns)")

        # Collect registered column names from child nodes
        registered_cols: set[str] = set()
        regs = registry.list_registrations()
        for r in regs:
            if r["table_name"] == table_name:
                registered_cols.add(r["column_name"].upper())

        # Fetch all columns from ODBC
        try:
            columns = registry.list_table_columns(dsn, table_name)
        except Exception as exc:
            logger.error("Failed to list columns for %s: %s", table_name, exc)
            self.lbl_stats.setText(f"Error: {exc}")
            self.value_model.itemChanged.disconnect(self._on_item_changed)
            self.value_model.clear()
            self.value_model.setHorizontalHeaderLabels(
                ["Column", "Notes", "Type", "Size", "Nullable", "Registered"])
            self.value_model.itemChanged.connect(self._on_item_changed)
            self.btn_export.setEnabled(False)
            return

        # Saved per-column notes (column_name upper → note)
        try:
            col_notes = registry.get_column_notes(dsn, table_name)
        except Exception as exc:
            logger.error("Failed to load column notes for %s: %s", table_name, exc)
            col_notes = {}

        self.value_model.itemChanged.disconnect(self._on_item_changed)
        self.value_model.clear()
        headers = ["Column", "Notes", "Type", "Size", "Nullable", "Registered"]
        self.value_model.setHorizontalHeaderLabels(headers)

        registered_count = 0
        for col_name, type_name, col_size, nullable in columns:
            is_reg = col_name.upper() in registered_cols
            if is_reg:
                registered_count += 1

            item_name = QStandardItem(col_name)
            item_name.setEditable(False)
            if is_reg:
                item_name.setFont(_FONT_BOLD)
                item_name.setForeground(QColor("#1E5BA8"))

            item_notes = QStandardItem(col_notes.get(col_name.upper(), ""))
            item_notes.setEditable(True)
            # Stash the column name so edits can be saved back
            item_notes.setData(col_name, Qt.ItemDataRole.UserRole)

            item_type = QStandardItem(str(type_name))
            item_type.setEditable(False)

            item_size = QStandardItem(str(col_size) if col_size else "")
            item_size.setEditable(False)
            item_size.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            item_null = QStandardItem(nullable)
            item_null.setEditable(False)
            item_null.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

            item_reg = QStandardItem("\u2713" if is_reg else "")
            item_reg.setEditable(False)
            item_reg.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if is_reg:
                item_reg.setForeground(QColor("#228B22"))
                item_reg.setFont(_FONT_BOLD)

            self.value_model.appendRow(
                [item_name, item_notes, item_type, item_size,
                 item_null, item_reg])

        self.value_model.itemChanged.connect(self._on_item_changed)

        # Column sizing
        self.value_table.resizeColumnsToContents()
        hdr = self.value_table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Column
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)      # Notes
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)      # Type
        for c in range(3, 6):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        # Hide extended value columns that don't apply
        for col in range(6, self.value_model.columnCount()):
            self.value_table.setColumnHidden(col, True)

        self.lbl_stats.setText(
            f"{len(columns)} column(s)  |  "
            f"{registered_count} registered")
        self.btn_export.setEnabled(False)

    def _show_dsn_details(self, dsn: str):
        """Show ODBC connection details for a DSN in the right panel."""
        from suiteview.core.odbc_utils import get_dsn_details

        self._current_field_id = None
        self._table_columns_context = None
        self.lbl_field_title.setText(f"Connection: {dsn}")

        details = get_dsn_details(dsn)

        self.value_model.itemChanged.disconnect(self._on_item_changed)
        self.value_model.clear()
        headers = ["Property", "Value"]
        self.value_model.setHorizontalHeaderLabels(headers)

        for key, val in details.items():
            if key == "Password":
                val = "********"
            item_key = QStandardItem(key)
            item_key.setEditable(False)
            item_key.setFont(_FONT_BOLD)

            item_val = QStandardItem(str(val))
            item_val.setEditable(False)

            self.value_model.appendRow([item_key, item_val])

        self.value_model.itemChanged.connect(self._on_item_changed)

        # Column sizing
        self.value_table.resizeColumnsToContents()
        hdr = self.value_table.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        # Hide extra columns
        for col in range(2, self.value_model.columnCount()):
            self.value_table.setColumnHidden(col, True)

        self.lbl_stats.setText(f"{len(details)} properties")
        self.btn_export.setEnabled(False)

    def _on_tree_context_menu(self, pos):
        """Right-click menu on tree: permanently delete a table or field."""
        item = self.tree.itemAt(pos)
        if item is None:
            return

        node_type = item.data(0, _ROLE_NODE_TYPE)
        if node_type == "db":
            return  # no context menu for database nodes

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: white; border: 1px solid #1E5BA8;"
            "  font-size: 9pt; }"
            "QMenu::item { padding: 4px 20px; }"
            "QMenu::item:selected { background-color: #A0C4E8; color: black; }"
        )

        if node_type == "field":
            field_id = item.data(0, _ROLE_FIELD_ID)
            if field_id is None:
                return
            parent = item.parent()
            table_name = parent.text(0) if parent else ""
            col_name = item.text(0)
            act_del = menu.addAction(
                f"Permanently Delete \"{col_name}\" from Registry")
            chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
            if chosen == act_del:
                self._permanently_delete_field(
                    field_id, table_name, col_name)
        elif node_type == "table":
            table_name = item.text(0)
            field_count = item.childCount()
            act_del = menu.addAction(
                f"Permanently Delete \"{table_name}\" "
                f"({field_count} field(s)) from Registry")
            chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
            if chosen == act_del:
                self._permanently_delete_table(table_name, field_count)

    def _permanently_delete_field(self, field_id: int, table_name: str,
                                  col_name: str):
        """Prompt and permanently delete a single field registration."""
        reply = QMessageBox.warning(
            self, "Permanently Delete Field",
            f"Are you sure you want to permanently delete "
            f"\"{table_name}.{col_name}\" and all of its values "
            f"from the registry?\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            registry.permanently_delete_field(field_id)
        except Exception as exc:
            QMessageBox.warning(self, "Delete Error",
                                f"Could not delete field:\n\n{exc}")
            return
        if self._current_field_id == field_id:
            self._current_field_id = None
            self.value_model.itemChanged.disconnect(self._on_item_changed)
            self.value_model.clear()
            self.value_model.setHorizontalHeaderLabels(_ALL_HEADERS)
            self.value_model.itemChanged.connect(self._on_item_changed)
            self.lbl_field_title.setText("Select a field \u2192")
            self.lbl_stats.setText("")
            self.btn_export.setEnabled(False)
        self._load_registrations()

    def _permanently_delete_table(self, table_name: str, field_count: int):
        """Prompt and permanently delete all fields for a table."""
        reply = QMessageBox.warning(
            self, "Permanently Delete Table",
            f"Are you sure you want to permanently delete "
            f"\"{table_name}\" and all {field_count} field(s) "
            f"(including all their values) from the registry?\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            registry.permanently_delete_table(table_name)
        except Exception as exc:
            QMessageBox.warning(self, "Delete Error",
                                f"Could not delete table:\n\n{exc}")
            return
        self._current_field_id = None
        self.value_model.itemChanged.disconnect(self._on_item_changed)
        self.value_model.clear()
        self.value_model.setHorizontalHeaderLabels(_ALL_HEADERS)
        self.value_model.itemChanged.connect(self._on_item_changed)
        self.lbl_field_title.setText("Select a field \u2192")
        self.lbl_stats.setText("")
        self.btn_export.setEnabled(False)
        self._load_registrations()

    def _refresh_all(self):
        """Re-query all registered fields from the live database."""
        regs = registry.list_registrations()
        if not regs:
            QMessageBox.information(self, "Registry", "No registrations to refresh.")
            return

        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("Refreshing\u2026")
        QApplication.processEvents()

        errors = []
        for r in regs:
            try:
                registry.fetch_and_register(
                    r["table_name"], r["column_name"],
                    r.get("display_name", ""),
                    source_dsn=r.get("source_dsn") or "")
            except Exception as exc:
                errors.append(f"{r['table_name']}.{r['column_name']}: {exc}")

        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("Refresh All")
        self._load_registrations()

        # Reselect previous if it was selected
        if self._current_field_id is not None:
            self._select_registration(self._current_field_id)

        if errors:
            QMessageBox.warning(
                self, "Refresh Errors",
                "Some fields failed to refresh:\n\n" + "\n".join(errors))

    def _select_registration(self, field_id: int):
        """Find and select a tree item by field ID (3-level tree)."""
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):            # db nodes
            db_node = root.child(i)
            for j in range(db_node.childCount()):     # table nodes
                table_node = db_node.child(j)
                for k in range(table_node.childCount()):  # field nodes
                    child = table_node.child(k)
                    if child.data(0, _ROLE_FIELD_ID) == field_id:
                        self.tree.setCurrentItem(child)
                        return

    # ── Value table context menu ──────────────────────────────────

    def _on_value_table_context_menu(self, pos):
        """Right-click menu: copy to clipboard."""
        if self.value_model.rowCount() == 0:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: white; border: 1px solid #1E5BA8;"
            "  font-size: 9pt; }"
            "QMenu::item { padding: 4px 20px; }"
            "QMenu::item:selected { background-color: #A0C4E8; color: black; }"
            "QMenu::separator { height: 1px; background: #C8D8E8;"
            "  margin: 2px 4px; }"
        )
        act_copy = menu.addAction("Copy to Clipboard")

        chosen = menu.exec(self.value_table.viewport().mapToGlobal(pos))
        if chosen == act_copy:
            self._copy_values_to_clipboard()

    def _get_table_data(self, visible_only: bool = True
                        ) -> tuple[list[str], list[list[str]]]:
        """Extract headers and rows from the value model (respecting sort)."""
        headers = []
        col_indices = []
        for col in range(self.value_model.columnCount()):
            if visible_only and self.value_table.isColumnHidden(col):
                continue
            headers.append(
                self.value_model.headerData(col, Qt.Orientation.Horizontal))
            col_indices.append(col)
        rows = []
        proxy = self.proxy_model
        for r in range(proxy.rowCount()):
            row = []
            for c in col_indices:
                idx = proxy.index(r, c)
                row.append(idx.data(Qt.ItemDataRole.DisplayRole) or "")
            rows.append(row)
        return headers, rows

    def _copy_values_to_clipboard(self):
        """Copy all values as tab-separated text to the clipboard."""
        headers, rows = self._get_table_data()
        lines = ["\t".join(headers)]
        for row in rows:
            lines.append("\t".join(row))
        text = "\n".join(lines)
        QApplication.clipboard().setText(text)

    def _export_values_to_excel(self):
        """Export all values (all columns) to an Excel workbook."""
        # Export all columns regardless of More/Less state
        headers, rows = self._get_table_data(visible_only=False)
        if not rows:
            QMessageBox.information(self, "Export", "No data to export.")
            return

        try:
            from suiteview.core.excel_export import (
                dump_to_new_workbook, ExcelExportError)
            sheet = self.lbl_field_title.text().replace(".", "_")
            # Value is column 1 — force text so leading-zero codes are preserved.
            dump_to_new_workbook(
                headers, rows, sheet_name=sheet, text_col_indexes=[1])
        except ExcelExportError as exc:
            QMessageBox.warning(self, "Excel Error", str(exc))
        except Exception as exc:
            logger.exception("Registry Excel export failed")
            QMessageBox.warning(self, "Excel Error", f"Could not export:\n{exc}")

    # ── Pop-out value editor ─────────────────────────────────────────

    def _sync_edit_window_button(self, current, _previous=None) -> None:
        """Enable the Edit-in-Window button only when a field leaf is selected."""
        is_field = (
            current is not None
            and current.data(0, _ROLE_NODE_TYPE) == "field"
            and current.data(0, _ROLE_FIELD_ID) is not None
        )
        self.btn_edit_window.setEnabled(bool(is_field))

    def _open_value_editor_window(self) -> None:
        """Pop the selected field's values open in an editable datagrid window."""
        if self._current_field_id is None:
            return
        win = getattr(self, "_value_editor_win", None)
        if win is None:
            win = RegistryValueEditorWindow(
                self._current_field_id, self.lbl_field_title.text())
            win.values_changed.connect(self._on_value_editor_saved)
            self._value_editor_win = win
        else:
            win.reload(self._current_field_id, self.lbl_field_title.text())
        win.show()
        win.raise_()
        win.activateWindow()

    def _on_value_editor_saved(self) -> None:
        """Reload the value table after the pop-out editor saves."""
        if self._current_field_id is not None:
            self._show_values(self._current_field_id)

    # ── Window geometry persistence ──────────────────────────────────

    @staticmethod
    def _load_geometry_settings() -> dict:
        try:
            if _SETTINGS_PATH.exists():
                return json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        return {}

    def _save_geometry_settings(self):
        geo = self.geometry()
        data = {"x": geo.x(), "y": geo.y(),
                "w": geo.width(), "h": geo.height()}
        try:
            _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _SETTINGS_PATH.write_text(
                json.dumps(data), encoding="utf-8")
        except OSError:
            pass

    def closeEvent(self, event):
        self._save_geometry_settings()
        super().closeEvent(event)

    def refresh_and_select(self, table_name: str, column_name: str):
        """Reload registrations and select the given table.column entry."""
        self._load_registrations()
        # Find and select the matching entry (3-level tree)
        root = self.tree.invisibleRootItem()
        regs = registry.list_registrations()
        for i in range(root.childCount()):            # db nodes
            db_node = root.child(i)
            for j in range(db_node.childCount()):     # table nodes
                tbl_node = db_node.child(j)
                if tbl_node.text(0) == table_name:
                    for k in range(tbl_node.childCount()):  # field nodes
                        child = tbl_node.child(k)
                        rid = child.data(0, _ROLE_FIELD_ID)
                        if rid is not None:
                            for r in regs:
                                if r["field_id"] == rid and r["column_name"] == column_name:
                                    self.tree.setCurrentItem(child)
                                    return
