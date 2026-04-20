"""
DataForgeShelf — right-side panel listing saved DataForges using the
shared FilterTableView widget for consistent look-and-feel.
"""
from __future__ import annotations

import logging

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
)

from suiteview.audit.dataforge.dataforge_model import DataForge
from suiteview.audit.dataforge import dataforge_store as df_store
from suiteview.ui.widgets.filter_table_view import FilterTableView

logger = logging.getLogger(__name__)


class DataForgeShelf(QWidget):
    """Compact table panel of saved DataForges."""

    designer_requested = pyqtSignal(object)   # DataForge → open designer
    close_requested = pyqtSignal(str)         # forge name → close open designer
    new_forge_requested = pyqtSignal()        # user clicked "+ New DataForge"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180)
        self._forges: dict[str, DataForge] = {}  # name → DataForge
        self._build_ui()
        self.refresh()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header label ─────────────────────────────────────────────
        lbl_title = QLabel("Saved DataForges")
        lbl_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl_title.setFixedHeight(24)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet(
            "QLabel { color: white; font-weight: bold; border: none;"
            " background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            " stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C); }")
        root.addWidget(lbl_title)

        # ── FilterTableView ──────────────────────────────────────────
        self._ftv = FilterTableView(self)

        # Hide search bar row and info label — compact shelf mode
        self._ftv.global_search_box.setVisible(False)
        self._ftv.info_label.setVisible(False)
        ftv_lay = self._ftv.layout()
        if ftv_lay and ftv_lay.count() >= 1:
            search_item = ftv_lay.itemAt(0)
            if search_item and search_item.layout():
                sl = search_item.layout()
                for i in range(sl.count()):
                    w = sl.itemAt(i).widget()
                    if w:
                        w.setVisible(False)

        tv = self._ftv.table_view
        tv.setSelectionBehavior(tv.SelectionBehavior.SelectRows)
        tv.setSelectionMode(tv.SelectionMode.SingleSelection)
        tv.setEditTriggers(tv.EditTrigger.NoEditTriggers)
        tv.verticalHeader().setVisible(False)
        tv.setAlternatingRowColors(False)
        tv.setShowGrid(False)
        tv.verticalHeader().setDefaultSectionSize(16)
        tv.verticalHeader().setMinimumSectionSize(16)
        from PyQt6.QtWidgets import QHeaderView
        tv.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        tv.setFont(QFont("Segoe UI", 9))
        tv.setStyleSheet("""
            QTableView {
                font-size: 9pt;
                background-color: white;
                alternate-background-color: white;
            }
            QTableView::item {
                padding: 0px;
                margin: 0px;
                border: none;
                background-color: white;
            }
            QTableView::item:selected {
                background-color: #DDD6FE;
                color: black;
            }
            QHeaderView::section {
                padding: 0px 4px;
                margin: 0px;
                font-size: 7pt;
                font-weight: bold;
            }
        """)
        tv.horizontalHeader().setFixedHeight(18)

        # Context menu & click handling
        try:
            self._ftv.table_view.customContextMenuRequested.disconnect(
                self._ftv.show_table_context_menu)
        except TypeError:
            pass
        self._ftv.table_view.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._ftv.table_view.customContextMenuRequested.connect(
            self._show_context_menu)
        self._ftv.table_view.clicked.connect(self._on_index_clicked)
        root.addWidget(self._ftv)

        # ── Footer (New DataForge button + count) ─────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 2, 0)
        footer.setSpacing(4)

        btn_new = QPushButton("+ New DataForge")
        btn_new.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        btn_new.setFixedHeight(16)
        btn_new.setStyleSheet(
            "QPushButton { background: #7C3AED; color: white; border: none;"
            " border-radius: 2px; padding: 0 6px; }"
            "QPushButton:hover { background: #6D28D9; }")
        btn_new.clicked.connect(self.new_forge_requested)
        footer.addWidget(btn_new)

        self._lbl_count = QLabel("0 dataforges")
        self._lbl_count.setFont(QFont("Segoe UI", 7))
        self._lbl_count.setAlignment(Qt.AlignmentFlag.AlignRight
                                     | Qt.AlignmentFlag.AlignVCenter)
        self._lbl_count.setFixedHeight(16)
        footer.addWidget(self._lbl_count)

        footer_widget = QWidget()
        footer_widget.setFixedHeight(18)
        footer_widget.setStyleSheet(
            "background: #EDE9FE; color: #4C1D95; border: none;")
        footer_widget.setLayout(footer)
        root.addWidget(footer_widget)

    # ── Public API ───────────────────────────────────────────────────

    def refresh(self):
        """Reload the table from disk."""
        self._forges.clear()
        forges = df_store.list_forges()

        rows = []
        for forge in forges:
            self._forges[forge.name] = forge
            n_sources = len(forge.sources)
            rows.append({
                "Name": forge.name,
                "Queries": str(n_sources),
                "Date": forge.created_at.strftime("%b %d").lstrip("0"),
            })

        df = pd.DataFrame(rows, columns=["Name", "Queries", "Date"])
        self._ftv.set_dataframe(df, limit_rows=False)

        # Set all columns to independent interactive resizing
        from PyQt6.QtWidgets import QHeaderView
        hdr = self._ftv.table_view.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._ftv.table_view.resizeColumnsToContents()
        # Stretch the Name column to fill remaining space
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        self._lbl_count.setText(f"{len(forges)} dataforges")

    # ── Internals ────────────────────────────────────────────────────

    def _get_forge_at_row(self, row: int) -> DataForge | None:
        model = self._ftv.model
        if model is None or row < 0 or row >= len(model._display_indices):
            return None
        source_idx = model._display_indices[row]
        name = model._original_df.at[source_idx, "Name"]
        return self._forges.get(name)

    def _on_index_clicked(self, index):
        forge = self._get_forge_at_row(index.row())
        if forge:
            self.designer_requested.emit(forge)

    def _show_context_menu(self, pos):
        index = self._ftv.table_view.indexAt(pos)
        if not index.isValid():
            return
        forge = self._get_forge_at_row(index.row())
        if not forge:
            return

        menu = QMenu(self)
        act_close = menu.addAction("Close")
        menu.addSeparator()
        act_delete = menu.addAction("Delete")

        chosen = menu.exec(self._ftv.table_view.mapToGlobal(pos))
        if chosen is act_close:
            self.close_requested.emit(forge.name)
        elif chosen is act_delete:
            reply = QMessageBox.question(
                self, "Delete DataForge",
                f"Delete saved DataForge \"{forge.name}\"?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                df_store.delete_forge(forge.name)
                self.refresh()
