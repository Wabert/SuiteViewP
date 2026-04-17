"""
Unique Value Registry Window — non-blocking themed viewer for registered values.

Left panel: compact navigation list of registered table.column entries
Right panel: sortable value table with description, notes, active flag,
             counts, and a More/Less toggle for extra columns.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QSortFilterProxyModel
from PyQt6.QtGui import QFont, QStandardItemModel, QStandardItem, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
    QTableView, QPushButton, QAbstractItemView, QMessageBox,
    QApplication, QStyledItemDelegate, QStyle, QMenu,
    QLineEdit, QDialog, QFormLayout, QDialogButtonBox, QCheckBox,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from . import shared_field_registry as registry
from .tabs._styles import make_checkbox as _make_checkbox

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_MONO = QFont("Consolas", 9)
_FONT_SMALL = QFont("Segoe UI", 8)

_HEADER_COLORS = ("#1E5BA8", "#0D3A7A", "#082B5C")
_BORDER_COLOR = "#D4A017"

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

_INACTIVE_FG = QColor("#999999")


class _NumericSortItem(QStandardItem):
    """QStandardItem that sorts numerically when the data is an int."""

    def __lt__(self, other):
        try:
            return int(self.text().replace(",", "")) < int(other.text().replace(",", ""))
        except (ValueError, AttributeError):
            return super().__lt__(other)


class _AddValueDialog(QDialog):
    """Small dialog to add a new value entry."""

    def __init__(self, field_title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Add Value — {field_title}")
        self.setMinimumWidth(360)
        lay = QFormLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.txt_value = QLineEdit()
        self.txt_value.setPlaceholderText("Field value (required)")
        lay.addRow("Value:", self.txt_value)

        self.txt_desc = QLineEdit()
        self.txt_desc.setPlaceholderText("Optional description")
        lay.addRow("Description:", self.txt_desc)

        self.txt_notes = QLineEdit()
        self.txt_notes.setPlaceholderText("Optional notes")
        lay.addRow("Notes:", self.txt_notes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addRow(buttons)

    def get_data(self) -> tuple[str, str, str]:
        return (self.txt_value.text().strip(),
                self.txt_desc.text().strip(),
                self.txt_notes.text().strip())


class UniqueValueRegistryWindow(FramelessWindowBase):
    """Non-blocking registry viewer window."""

    _instance = None  # singleton reference

    def __init__(self, parent=None):
        saved = self._load_geometry_settings()
        self._current_field_id = None
        self._expanded = False  # More/Less state
        self._show_inactive = False
        self._value_rows: list[dict] = []  # raw data backing the model
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
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_refresh = QPushButton("Refresh All")
        self.btn_refresh.setFont(_FONT_SMALL)
        self.btn_refresh.setFixedHeight(22)
        self.btn_refresh.setStyleSheet(_BTN_STYLE)
        self.btn_refresh.setToolTip("Re-query all registered fields from the database")
        self.btn_refresh.clicked.connect(self._refresh_all)
        toolbar.addWidget(self.btn_refresh)

        self.btn_delete = QPushButton("Deactivate Field")
        self.btn_delete.setFont(_FONT_SMALL)
        self.btn_delete.setFixedHeight(22)
        self.btn_delete.setStyleSheet(_BTN_RED_STYLE)
        self.btn_delete.setToolTip("Deactivate selected field registration")
        self.btn_delete.clicked.connect(self._delete_selected)
        toolbar.addWidget(self.btn_delete)

        toolbar.addStretch()

        self.lbl_summary = QLabel("")
        self.lbl_summary.setFont(_FONT_SMALL)
        self.lbl_summary.setStyleSheet("color: #666;")
        toolbar.addWidget(self.lbl_summary)

        root.addLayout(toolbar)

        # ── Splitter: left nav tree + right value table ──────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

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
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        left_lay.addWidget(self.tree)

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

        self.btn_add = QPushButton("Add Value")
        self.btn_add.setFont(_FONT_SMALL)
        self.btn_add.setFixedHeight(22)
        self.btn_add.setStyleSheet(_BTN_STYLE)
        self.btn_add.setToolTip("Manually add a new value entry")
        self.btn_add.clicked.connect(self._add_value)
        self.btn_add.setEnabled(False)
        action_bar.addWidget(self.btn_add)

        self.btn_deactivate = QPushButton("Deactivate Value")
        self.btn_deactivate.setFont(_FONT_SMALL)
        self.btn_deactivate.setFixedHeight(22)
        self.btn_deactivate.setStyleSheet(_BTN_RED_STYLE)
        self.btn_deactivate.setToolTip("Mark selected value as inactive")
        self.btn_deactivate.clicked.connect(self._deactivate_selected_value)
        self.btn_deactivate.setEnabled(False)
        action_bar.addWidget(self.btn_deactivate)

        self.btn_export = QPushButton("Export to Excel")
        self.btn_export.setFont(_FONT_SMALL)
        self.btn_export.setFixedHeight(22)
        self.btn_export.setStyleSheet(_BTN_STYLE)
        self.btn_export.setToolTip("Export all values to an Excel workbook")
        self.btn_export.clicked.connect(self._export_values_to_excel)
        self.btn_export.setEnabled(False)
        action_bar.addWidget(self.btn_export)

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
        self.value_table.selectionModel().selectionChanged.connect(
            self._on_value_selection_changed)
        right_lay.addWidget(self.value_table)

        splitter.addWidget(right_panel)

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
        """Populate the left navigation tree from the registry."""
        self.tree.clear()
        regs = registry.list_registrations()

        # Group by table_name
        table_groups: dict[str, list[dict]] = {}
        for r in regs:
            table_groups.setdefault(r["table_name"], []).append(r)

        total_registrations = len(regs)

        for table_name, items in sorted(table_groups.items()):
            table_node = QTreeWidgetItem(self.tree)
            table_node.setText(0, table_name)
            table_node.setFont(0, _FONT_BOLD)
            table_node.setForeground(0, QColor("#0A1E5E"))
            table_node.setExpanded(True)
            table_node.setFlags(
                table_node.flags() & ~Qt.ItemFlag.ItemIsSelectable)

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
                child.setData(0, Qt.ItemDataRole.UserRole, reg["field_id"])
                child.setToolTip(
                    0,
                    f"{reg['table_name']}.{reg['column_name']}\n"
                    f"{reg['value_count']} unique values\n"
                    f"Last scanned: {reg.get('last_scanned_at', '\u2014')}",
                )

        self.lbl_summary.setText(
            f"{total_registrations} registration(s) across "
            f"{len(table_groups)} table(s)")

    def _show_values(self, field_id: int):
        """Load and display values for the selected field."""
        self._current_field_id = field_id
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

        # Enable buttons
        self.btn_add.setEnabled(True)
        self.btn_export.setEnabled(len(self._value_rows) > 0)

        # Default sort by count descending
        self.value_table.sortByColumn(_COL_COUNT, Qt.SortOrder.DescendingOrder)

    # ── Inline editing ───────────────────────────────────────────────

    def _on_item_changed(self, item: QStandardItem):
        """Persist description or notes edits to SQL Server."""
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
        reg_id = current.data(0, Qt.ItemDataRole.UserRole)
        if reg_id is None:
            return  # table group node, not a leaf

        # Update title
        parent = current.parent()
        table_name = parent.text(0) if parent else ""
        col_name = current.text(0)
        self.lbl_field_title.setText(f"{table_name}.{col_name}")
        self._show_values(reg_id)

    def _on_tree_context_menu(self, pos):
        """Right-click menu on tree: permanently delete a table or field."""
        item = self.tree.itemAt(pos)
        if item is None:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: white; border: 1px solid #1E5BA8;"
            "  font-size: 9pt; }"
            "QMenu::item { padding: 4px 20px; }"
            "QMenu::item:selected { background-color: #A0C4E8; color: black; }"
        )

        field_id = item.data(0, Qt.ItemDataRole.UserRole)
        if field_id is not None:
            # This is a field (leaf) node
            parent = item.parent()
            table_name = parent.text(0) if parent else ""
            col_name = item.text(0)
            act_del = menu.addAction(
                f"Permanently Delete \"{col_name}\" from Registry")
            chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
            if chosen == act_del:
                self._permanently_delete_field(
                    field_id, table_name, col_name)
        else:
            # This is a table (group) node
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
            self.btn_add.setEnabled(False)
            self.btn_export.setEnabled(False)
            self.btn_deactivate.setEnabled(False)
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
        self.btn_add.setEnabled(False)
        self.btn_export.setEnabled(False)
        self.btn_deactivate.setEnabled(False)
        self._load_registrations()

    def _on_value_selection_changed(self, selected, _deselected):
        has_sel = len(self.value_table.selectionModel().selectedRows()) > 0
        self.btn_deactivate.setEnabled(has_sel)

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

    def _delete_selected(self):
        current = self.tree.currentItem()
        if current is None:
            return
        reg_id = current.data(0, Qt.ItemDataRole.UserRole)
        if reg_id is None:
            return

        parent = current.parent()
        table_name = parent.text(0) if parent else ""
        col_name = current.text(0)

        reply = QMessageBox.question(
            self, "Deactivate Field",
            f"Deactivate {table_name}.{col_name}?\n"
            "The field and its values will be hidden but not deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            registry.delete_registration(reg_id)
            self._current_field_id = None
            self.value_model.itemChanged.disconnect(self._on_item_changed)
            self.value_model.clear()
            self.value_model.setHorizontalHeaderLabels(_ALL_HEADERS)
            self.value_model.itemChanged.connect(self._on_item_changed)
            self.lbl_field_title.setText("Select a field \u2192")
            self.lbl_stats.setText("")
            self.btn_add.setEnabled(False)
            self.btn_export.setEnabled(False)
            self.btn_deactivate.setEnabled(False)
            self._load_registrations()

    def _add_value(self):
        """Add a new value entry via dialog."""
        if self._current_field_id is None:
            return
        title = self.lbl_field_title.text()
        dlg = _AddValueDialog(title, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        val, desc, notes = dlg.get_data()
        if not val:
            QMessageBox.warning(self, "Add Value", "Value cannot be empty.")
            return
        try:
            registry.add_value(self._current_field_id, val, desc, notes)
            self._show_values(self._current_field_id)
        except Exception as exc:
            QMessageBox.warning(self, "Add Error",
                                f"Could not add value:\n\n{exc}")

    def _deactivate_selected_value(self):
        """Deactivate the selected value row."""
        rows = self.value_table.selectionModel().selectedRows()
        if not rows:
            return
        proxy_idx = rows[0]
        source_idx = self.proxy_model.mapToSource(proxy_idx)
        val_item = self.value_model.item(source_idx.row(), _COL_VALUE)
        if val_item is None:
            return
        value_id = val_item.data(Qt.ItemDataRole.UserRole)
        field_value = val_item.text()
        if value_id is None:
            return
        reply = QMessageBox.question(
            self, "Deactivate Value",
            f"Deactivate value \"{field_value}\"?\n"
            "It will be marked inactive but not deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                registry.deactivate_value(value_id)
                self._show_values(self._current_field_id)
            except Exception as exc:
                QMessageBox.warning(self, "Deactivate Error",
                                    f"Could not deactivate:\n\n{exc}")

    def _select_registration(self, field_id: int):
        """Find and select a tree item by field ID."""
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.data(0, Qt.ItemDataRole.UserRole) == field_id:
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
        try:
            import pandas as pd
        except ImportError:
            QMessageBox.warning(self, "Export Error",
                                "pandas is required for Excel export.")
            return

        # Export all columns regardless of More/Less state
        headers, rows = self._get_table_data(visible_only=False)
        if not rows:
            QMessageBox.information(self, "Export", "No data to export.")
            return

        from PyQt6.QtWidgets import QFileDialog
        title = self.lbl_field_title.text().replace(".", "_")
        default_name = f"field_values_{title}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to Excel", default_name,
            "Excel Files (*.xlsx)")
        if not path:
            return

        try:
            df = pd.DataFrame(rows, columns=headers)
            df.to_excel(path, index=False)
            os.startfile(path)
        except Exception as exc:
            QMessageBox.warning(self, "Export Error", str(exc))

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
        # Find and select the matching entry
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            if group.text(0) == table_name:
                for j in range(group.childCount()):
                    child = group.child(j)
                    rid = child.data(0, Qt.ItemDataRole.UserRole)
                    if rid is not None:
                        # Look up the actual column name
                        regs = registry.list_registrations()
                        for r in regs:
                            if r["field_id"] == rid and r["column_name"] == column_name:
                                self.tree.setCurrentItem(child)
                                return
