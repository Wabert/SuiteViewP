"""
QDefinition Viewer Window — popup viewer for saved QDefinitions.

Left panel:  list of QDefs grouped by DSN/database.
Right panel: detail view (name, date, SQL, schema, snapshot indicator, Run/View/Delete).
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QTreeWidget, QTreeWidgetItem, QHeaderView,
    QPushButton, QTextEdit, QMessageBox, QApplication,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.audit.qdefinition import QDefinition
from suiteview.audit import qdef_store

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)
_FONT_BOLD = QFont("Segoe UI", 9, QFont.Weight.Bold)
_FONT_MONO = QFont("Consolas", 9)
_FONT_SMALL = QFont("Segoe UI", 8)

_HEADER_COLORS = ("#7C3AED", "#6D28D9", "#5B21B6")
_BORDER_COLOR = "#D4A017"

_BTN_STYLE = (
    "QPushButton { background-color: #7C3AED; color: white;"
    " border: 1px solid #6D28D9; border-radius: 3px;"
    " padding: 3px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #8B5CF6; }"
)

_BTN_DANGER_STYLE = (
    "QPushButton { background-color: #DC2626; color: white;"
    " border: 1px solid #B91C1C; border-radius: 3px;"
    " padding: 3px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #EF4444; }"
)

_BTN_GREEN_STYLE = (
    "QPushButton { background-color: #059669; color: white;"
    " border: 1px solid #047857; border-radius: 3px;"
    " padding: 3px 10px; font-size: 8pt; }"
    "QPushButton:hover { background-color: #10B981; }"
)


class QDefViewerWindow(FramelessWindowBase):
    """Non-blocking QDefinition viewer window."""

    _instance = None

    def __init__(self, parent=None):
        self._current_qdef: QDefinition | None = None
        super().__init__(
            title="QDefinition Viewer",
            default_size=(1100, 600),
            min_size=(700, 400),
            parent=parent,
            header_colors=_HEADER_COLORS,
            border_color=_BORDER_COLOR,
        )

    @classmethod
    def show_instance(cls, parent=None):
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(parent)
            cls._instance.show()
        else:
            cls._instance.raise_()
            cls._instance.activateWindow()
        return cls._instance

    # ── UI ────────────────────────────────────────────────────────────

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet("QWidget { background-color: #F5F3FF; }")
        root = QVBoxLayout(body)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Left: tree grouped by DSN ─────────────────────────────────
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(4)

        lbl_left = QLabel("QDefinitions")
        lbl_left.setFont(_FONT_BOLD)
        lbl_left.setStyleSheet("color: #7C3AED;")
        left_lay.addWidget(lbl_left)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFont(_FONT)
        self.tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #C4B5FD; background: white; }"
            "QTreeWidget::item { padding: 2px 4px; }"
            "QTreeWidget::item:selected { background-color: #DDD6FE; color: black; }"
        )
        self.tree.currentItemChanged.connect(self._on_tree_selection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        left_lay.addWidget(self.tree, 1)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setFont(_FONT_SMALL)
        btn_refresh.setFixedHeight(24)
        btn_refresh.setStyleSheet(_BTN_STYLE)
        btn_refresh.clicked.connect(self._load_tree)
        left_lay.addWidget(btn_refresh)

        splitter.addWidget(left)

        # ── Right: tabbed detail panel ─────────────────────────────────
        self._right_panel = QWidget()
        self._right_lay = QVBoxLayout(self._right_panel)
        self._right_lay.setContentsMargins(0, 0, 0, 0)
        self._right_lay.setSpacing(0)

        # Tab widget for Definition / Schema / Data
        from PyQt6.QtWidgets import QTabWidget
        self._right_tabs = QTabWidget()
        self._right_tabs.setFont(_FONT)
        self._right_tabs.setStyleSheet(
            "QTabWidget::pane { border: 2px solid #7C3AED; background: white; }"
            "QTabBar::tab { padding: 6px 18px; font-size: 9pt;"
            " border: 1px solid #C4B5FD; border-bottom: none;"
            " margin-right: 2px; border-top-left-radius: 4px;"
            " border-top-right-radius: 4px; }"
            "QTabBar::tab:selected { background: white;"
            " border: 2px solid #7C3AED; border-bottom: 2px solid white;"
            " font-weight: bold; color: #7C3AED; }"
            "QTabBar::tab:!selected { background: #EDE9FE; color: #666;"
            " border: 1px solid #C4B5FD; }"
            "QTabBar::tab:hover:!selected { background: #DDD6FE; color: #7C3AED; }"
        )

        # ── Tab 1: Definition ─────────────────────────────────────────
        def_tab = QWidget()
        def_lay = QVBoxLayout(def_tab)
        def_lay.setContentsMargins(8, 8, 8, 4)
        def_lay.setSpacing(6)

        # Info section
        self.lbl_name = QLabel("")
        self.lbl_name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_name.setStyleSheet("color: #7C3AED;")
        def_lay.addWidget(self.lbl_name)

        info_row = QHBoxLayout()
        info_row.setSpacing(20)
        self.lbl_date = QLabel("")
        self.lbl_date.setFont(_FONT)
        self.lbl_date.setStyleSheet("color: #666;")
        info_row.addWidget(self.lbl_date)
        self.lbl_source = QLabel("")
        self.lbl_source.setFont(_FONT)
        self.lbl_source.setStyleSheet("color: #666;")
        info_row.addWidget(self.lbl_source)
        self.lbl_dsn = QLabel("")
        self.lbl_dsn.setFont(_FONT)
        self.lbl_dsn.setStyleSheet("color: #666;")
        info_row.addWidget(self.lbl_dsn)
        info_row.addStretch()
        def_lay.addLayout(info_row)

        # Snapshot indicator
        snap_row = QHBoxLayout()
        snap_row.setSpacing(8)
        self.lbl_snapshot = QLabel("")
        self.lbl_snapshot.setFont(_FONT)
        snap_row.addWidget(self.lbl_snapshot)
        snap_row.addStretch()
        def_lay.addLayout(snap_row)

        # SQL section — takes most of the space
        lbl_sql = QLabel("SQL:")
        lbl_sql.setFont(_FONT_BOLD)
        def_lay.addWidget(lbl_sql)

        self.txt_sql = QTextEdit()
        self.txt_sql.setFont(_FONT_MONO)
        self.txt_sql.setReadOnly(True)
        self.txt_sql.setStyleSheet(
            "QTextEdit { background: white; border: 1px solid #C4B5FD;"
            " border-radius: 3px; }"
        )
        def_lay.addWidget(self.txt_sql, 1)  # stretch=1 so SQL fills space

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self.btn_run = QPushButton("Run")
        self.btn_run.setFont(_FONT_BOLD)
        self.btn_run.setFixedSize(80, 30)
        self.btn_run.setStyleSheet(_BTN_GREEN_STYLE)
        self.btn_run.clicked.connect(self._on_run)
        btn_row.addWidget(self.btn_run)

        self.btn_view = QPushButton("View")
        self.btn_view.setFont(_FONT_BOLD)
        self.btn_view.setFixedSize(80, 30)
        self.btn_view.setStyleSheet(_BTN_STYLE)
        self.btn_view.clicked.connect(self._on_view)
        btn_row.addWidget(self.btn_view)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setFont(_FONT_BOLD)
        self.btn_delete.setFixedSize(80, 30)
        self.btn_delete.setStyleSheet(_BTN_DANGER_STYLE)
        self.btn_delete.clicked.connect(self._on_delete)
        btn_row.addWidget(self.btn_delete)

        def_lay.addLayout(btn_row)

        self._right_tabs.addTab(def_tab, "Definition")

        # ── Tab 2: Schema ─────────────────────────────────────────────
        schema_tab = QWidget()
        schema_lay = QVBoxLayout(schema_tab)
        schema_lay.setContentsMargins(8, 8, 8, 4)
        schema_lay.setSpacing(6)

        self.tbl_schema = QTableWidget()
        self.tbl_schema.setColumnCount(2)
        self.tbl_schema.setHorizontalHeaderLabels(["Column", "Type"])
        self.tbl_schema.horizontalHeader().setStretchLastSection(True)
        self.tbl_schema.verticalHeader().setVisible(False)
        self.tbl_schema.verticalHeader().setDefaultSectionSize(18)
        self.tbl_schema.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_schema.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_schema.setFont(_FONT)
        self.tbl_schema.setStyleSheet(
            "QTableWidget { border: 1px solid #C4B5FD; background: white; }"
            "QHeaderView::section { background: #F5F3FF; font-weight: bold;"
            " font-size: 8pt; border: 1px solid #C0C0C0; padding: 2px 6px; }"
        )
        schema_lay.addWidget(self.tbl_schema, 1)

        self._right_tabs.addTab(schema_tab, "Schema")

        # ── Tab 3: Data ───────────────────────────────────────────────
        data_tab = QWidget()
        data_lay = QVBoxLayout(data_tab)
        data_lay.setContentsMargins(4, 4, 4, 4)
        data_lay.setSpacing(4)

        self.lbl_results_header = QLabel("No data loaded")
        self.lbl_results_header.setFont(_FONT_BOLD)
        self.lbl_results_header.setStyleSheet("color: #666;")
        data_lay.addWidget(self.lbl_results_header)

        self.results_table = FilterTableView()
        tv = self.results_table.table_view
        tv.verticalHeader().setVisible(False)
        tv.verticalHeader().setDefaultSectionSize(16)
        tv.setSelectionBehavior(tv.SelectionBehavior.SelectRows)
        data_lay.addWidget(self.results_table, 1)

        self._right_tabs.addTab(data_tab, "Data")

        self._right_lay.addWidget(self._right_tabs)
        splitter.addWidget(self._right_panel)
        splitter.setSizes([280, 820])

        root.addWidget(splitter, 1)

        # Load initial data
        self._load_tree()
        self._clear_detail()

        return body

    # ── Tree ──────────────────────────────────────────────────────────

    def _load_tree(self):
        self.tree.clear()
        qdefs = qdef_store.list_qdefs()

        # Group by DataForge name
        groups: dict[str, list[QDefinition]] = {}
        for qd in qdefs:
            key = qd.forge_name or qdef_store.COMMONS_NAME
            groups.setdefault(key, []).append(qd)

        # Show Commons first, then alphabetical forge names
        ordered = []
        if qdef_store.COMMONS_NAME in groups:
            ordered.append(qdef_store.COMMONS_NAME)
        for k in sorted(groups):
            if k != qdef_store.COMMONS_NAME:
                ordered.append(k)

        for forge in ordered:
            items = groups[forge]
            if forge == qdef_store.COMMONS_NAME:
                label = "📂 Commons"
            else:
                label = f"⚙ {forge}"
            forge_node = QTreeWidgetItem([label])
            forge_node.setFont(0, _FONT_BOLD)
            forge_node.setForeground(
                0, QColor("#B8860B") if forge == qdef_store.COMMONS_NAME
                else QColor("#7C3AED"))
            forge_node.setData(0, Qt.ItemDataRole.UserRole, None)
            forge_node.setData(0, Qt.ItemDataRole.UserRole + 1, forge)
            self.tree.addTopLevelItem(forge_node)
            for qd in items:
                child = QTreeWidgetItem([qd.name])
                child.setFont(0, _FONT)
                child.setData(0, Qt.ItemDataRole.UserRole, qd.name)
                child.setData(0, Qt.ItemDataRole.UserRole + 1, forge)
                forge_node.addChild(child)
            forge_node.setExpanded(True)

    def _on_tree_selection(self, current, previous):
        if current is None:
            self._clear_detail()
            return
        name = current.data(0, Qt.ItemDataRole.UserRole)
        if name is None:
            self._clear_detail()
            return
        forge = current.data(0, Qt.ItemDataRole.UserRole + 1) or ""
        qd = qdef_store.load_qdef(name, forge_name=forge)
        if qd:
            self._show_detail(qd)
        else:
            self._clear_detail()

    # ── Detail panel ──────────────────────────────────────────────────

    def _clear_detail(self):
        self._current_qdef = None
        self.lbl_name.setText("Select a QDefinition")
        self.lbl_date.setText("")
        self.lbl_source.setText("")
        self.lbl_dsn.setText("")
        self.lbl_snapshot.setText("")
        self.txt_sql.clear()
        self.tbl_schema.setRowCount(0)
        self.btn_run.setVisible(False)
        self.btn_view.setVisible(False)
        self.btn_delete.setVisible(False)
        self.lbl_results_header.setText("No data loaded")
        self.results_table.set_dataframe(pd.DataFrame())
        self._right_tabs.setCurrentIndex(0)

    def _show_detail(self, qd: QDefinition):
        self._current_qdef = qd
        self.lbl_name.setText(qd.name)
        self.lbl_date.setText(f"Created: {qd.created_at.strftime('%Y-%m-%d %H:%M')}")
        self.lbl_source.setText(f"Source Design: {qd.source_design}" if qd.source_design else "")
        self.lbl_dsn.setText(f"DSN: {qd.dsn}" if qd.dsn else "")

        # Snapshot indicator
        forge = qd.forge_name
        has_snap = qdef_store.has_snapshot(qd.name, forge_name=forge)
        if has_snap:
            snap_date = qdef_store.snapshot_date(qd.name, forge_name=forge)
            snap_p = qdef_store.snapshot_path(qd.name, forge_name=forge)
            snap_size = snap_p.stat().st_size
            if snap_size < 1024:
                size_str = f"{snap_size} B"
            elif snap_size < 1024 * 1024:
                size_str = f"{snap_size / 1024:.1f} KB"
            else:
                size_str = f"{snap_size / (1024 * 1024):.1f} MB"
            self.lbl_snapshot.setText(
                f"✅ Snapshot: {snap_p}  ({size_str}, {snap_date})")
            self.lbl_snapshot.setStyleSheet("color: #059669; font-weight: bold;")
            self.btn_run.setVisible(False)
            self.btn_view.setVisible(True)
        else:
            self.lbl_snapshot.setText("⚠ No snapshot")
            self.lbl_snapshot.setStyleSheet("color: #D97706; font-weight: bold;")
            self.btn_run.setVisible(True)
            self.btn_view.setVisible(False)

        self.btn_delete.setVisible(True)

        # SQL
        self.txt_sql.setPlainText(qd.sql)

        # Schema
        cols = qd.result_columns
        types = qd.column_types
        self.tbl_schema.setRowCount(len(cols))
        for i, col in enumerate(cols):
            self.tbl_schema.setItem(i, 0, QTableWidgetItem(col))
            self.tbl_schema.setItem(i, 1, QTableWidgetItem(types.get(col, "")))
        self.tbl_schema.resizeColumnsToContents()

        # Reset Data tab and stay on Definition tab
        self.lbl_results_header.setText("No data loaded")
        self.lbl_results_header.setStyleSheet("color: #666;")
        self.results_table.set_dataframe(pd.DataFrame())
        self._right_tabs.setCurrentIndex(0)

    # ── Actions ───────────────────────────────────────────────────────

    def _on_run(self):
        """Execute the QDef SQL and save as parquet snapshot."""
        qd = self._current_qdef
        if not qd:
            return

        self.btn_run.setEnabled(False)
        self.btn_run.setText("Running...")
        QApplication.processEvents()

        try:
            # Try direct ODBC DSN first; if that fails, try DB2 region mapping
            try:
                from suiteview.audit.query_runner import execute_odbc_query
                columns, rows = execute_odbc_query(qd.dsn, qd.sql)
            except Exception:
                from suiteview.core.db2_connection import DB2Connection
                db = DB2Connection(qd.dsn)
                columns, rows = db.execute_query_with_headers(qd.sql)
            df = pd.DataFrame([list(r) for r in rows], columns=columns)
            qdef_store.save_snapshot(qd.name, df, forge_name=qd.forge_name)
            self._show_detail(qd)  # refresh indicator
            self._show_snapshot(df)
        except Exception as exc:
            logger.exception("Failed to run QDefinition")
            QMessageBox.warning(self, "Run Error", str(exc))
        finally:
            self.btn_run.setEnabled(True)
            self.btn_run.setText("Run")

    def _on_view(self):
        """Load and display the existing parquet snapshot."""
        qd = self._current_qdef
        if not qd:
            return
        df = qdef_store.load_snapshot(qd.name, forge_name=qd.forge_name)
        if df is None:
            QMessageBox.warning(self, "Error", "Snapshot file not found.")
            return
        self._show_snapshot(df)

    def _show_snapshot(self, df: pd.DataFrame):
        """Display a DataFrame in the Data tab and switch to it."""
        self.lbl_results_header.setText(f"Data Snapshot ({len(df)} rows)")
        self.lbl_results_header.setStyleSheet("color: #7C3AED; font-weight: bold;")
        self.results_table.set_dataframe(df, limit_rows=False)
        self._right_tabs.setCurrentIndex(2)  # switch to Data tab

    def _on_delete(self):
        """Delete the current QDefinition."""
        qd = self._current_qdef
        if not qd:
            return
        reply = QMessageBox.question(
            self, "Delete QDefinition",
            f"Delete '{qd.name}' and its snapshot (if any)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            qdef_store.delete_qdef(qd.name, forge_name=qd.forge_name)
            self._clear_detail()
            self._load_tree()

    # ── Context menu ──────────────────────────────────────────────────

    def _on_tree_context_menu(self, pos):
        """Right-click context menu on the QDef tree."""
        item = self.tree.itemAt(pos)
        if item is None:
            return
        name = item.data(0, Qt.ItemDataRole.UserRole)
        if name is None:
            return  # clicked on a forge group node

        forge = item.data(0, Qt.ItemDataRole.UserRole + 1) or ""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        act_rename = menu.addAction("Rename")
        act_copy = menu.addAction("Copy To...")
        act_move = menu.addAction("Move To...")
        chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
        if chosen == act_rename:
            self._rename_qdef(name, forge)
        elif chosen == act_copy:
            self._copy_or_move_qdef(name, forge, move=False)
        elif chosen == act_move:
            self._copy_or_move_qdef(name, forge, move=True)

    def _rename_qdef(self, old_name: str, forge_name: str = ""):
        """Rename a QDefinition (JSON file + snapshot)."""
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "Rename QDefinition", "New name:", text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()

        if qdef_store.qdef_exists(new_name, forge_name=forge_name):
            QMessageBox.warning(
                self, "Name Exists",
                f"A QDefinition named '{new_name}' already exists.")
            return

        qd = qdef_store.load_qdef(old_name, forge_name=forge_name)
        if not qd:
            return

        # Save under new name, delete old
        qd.name = new_name
        qdef_store.save_qdef(qd)

        # Move snapshot if it exists
        old_snap = qdef_store.snapshot_path(old_name, forge_name=forge_name)
        if old_snap.exists():
            new_snap = qdef_store.snapshot_path(new_name, forge_name=forge_name)
            old_snap.rename(new_snap)

        qdef_store.delete_qdef(old_name, forge_name=forge_name)
        self._load_tree()
        self._clear_detail()

    def _copy_or_move_qdef(self, name: str, src_forge: str, move: bool = False):
        """Copy or move a QDefinition to another forge/Commons."""
        from PyQt6.QtWidgets import QDialog, QComboBox, QVBoxLayout, QHBoxLayout, QLabel

        action = "Move" if move else "Copy"

        # Build list of target destinations
        targets: list[str] = []
        if src_forge != qdef_store.COMMONS_NAME:
            targets.append(qdef_store.COMMONS_NAME)
        for fn in qdef_store.list_forge_names():
            if fn != src_forge:
                targets.append(fn)
        # Also include saved DataForge names that may not have QDefs yet
        try:
            from suiteview.audit.dataforge import dataforge_store as df_store
            for f in df_store.list_forges():
                if f.name not in targets and f.name != src_forge:
                    targets.append(f.name)
        except Exception:
            pass

        if not targets:
            QMessageBox.information(
                self, f"No Destinations",
                "No other DataForges or Commons to move to.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{action} '{name}'")
        dlg.setFixedSize(350, 120)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lbl = QLabel(f"{action} to:")
        lbl.setFont(_FONT_BOLD)
        lay.addWidget(lbl)

        cmb = QComboBox()
        cmb.setFont(_FONT)
        cmb.setEditable(True)
        for t in targets:
            display = "Commons" if t == qdef_store.COMMONS_NAME else t
            cmb.addItem(display, t)
        lay.addWidget(cmb)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton(action)
        btn_ok.setFont(_FONT_BOLD)
        btn_ok.setFixedSize(80, 28)
        btn_ok.setStyleSheet(_BTN_STYLE)
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_ok)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(_FONT)
        btn_cancel.setFixedSize(80, 28)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_cancel)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Resolve target: use userData if available, else the typed text
        idx = cmb.currentIndex()
        if idx >= 0 and cmb.itemData(idx):
            dst_forge = cmb.itemData(idx)
        else:
            typed = cmb.currentText().strip()
            dst_forge = qdef_store.COMMONS_NAME if typed.lower() == "commons" else typed
        if not dst_forge:
            return

        if qdef_store.qdef_exists(name, forge_name=dst_forge):
            QMessageBox.warning(
                self, "Name Exists",
                f"A QDefinition named '{name}' already exists in "
                f"'{'Commons' if dst_forge == qdef_store.COMMONS_NAME else dst_forge}'.")
            return

        if move:
            ok = qdef_store.move_qdef(name, src_forge, dst_forge)
        else:
            ok = qdef_store.copy_qdef(name, src_forge, dst_forge)

        if ok:
            self._load_tree()
            self._clear_detail()
        else:
            QMessageBox.warning(self, "Error",
                                f"Failed to {action.lower()} '{name}'.")
