"""
QueryPreviewWindow — lightweight viewer for DataForge query results.

Shows the first 1,000 rows by default with a "Show All Rows" button
to load the full dataset into the table.

Built on ``FramelessWindowBase`` so it carries the SuiteView custom chrome
(gradient header, gold border, live W×H footer) like every other window, and
branded with DataForge's purple identity.
"""
from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

_PREVIEW_LIMIT = 1000

# DataForge dialog identity (matches the Queries dialog / field-picker purple).
_FORGE_HEADER = ("#7C3AED", "#6D28D9", "#5B21B6")


class QueryPreviewWindow(FramelessWindowBase):
    """Modeless window showing a preview of a DataForge query's cached data."""

    def __init__(self, query_name: str, df: pd.DataFrame, parent=None):
        # build_content() runs inside FramelessWindowBase.__init__, so the data
        # it needs must exist first.
        self._query_name = query_name
        self._full_df = df
        self._showing_all = len(df) <= _PREVIEW_LIMIT

        super().__init__(
            title=f"View — {query_name}",
            default_size=(1000, 600),
            min_size=(900, 550),
            parent=parent,
            header_colors=_FORGE_HEADER,
            border_color="#D4A017",
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    # ── Content ──────────────────────────────────────────────────────────

    def build_content(self) -> QWidget:
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(4)

        # ── Header row ───────────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(8)

        total = len(self._full_df)
        shown = min(total, _PREVIEW_LIMIT)
        self._lbl_info = QLabel()
        self._lbl_info.setFont(QFont("Segoe UI", 10))
        self._update_info_label(shown, total)
        header.addWidget(self._lbl_info)

        header.addStretch()

        # "Show All" button — hidden if ≤ 1000 rows
        self._btn_show_all = QPushButton(f"Show All {total:,} Rows")
        self._btn_show_all.setFont(QFont("Segoe UI", 9))
        self._btn_show_all.setStyleSheet(
            "QPushButton { background-color: #7C3AED; color: white;"
            " border: 1px solid #6D28D9; border-radius: 3px;"
            " padding: 4px 14px; }"
            "QPushButton:hover { background-color: #8B5CF6; }")
        self._btn_show_all.clicked.connect(self._on_show_all)
        self._btn_show_all.setVisible(not self._showing_all)
        header.addWidget(self._btn_show_all)

        # Export Excel
        btn_excel = QPushButton("Excel")
        btn_excel.setFont(QFont("Segoe UI", 9))
        btn_excel.setStyleSheet(
            "QPushButton { background-color: #059669; color: white;"
            " border: 1px solid #047857; border-radius: 3px;"
            " padding: 4px 14px; }"
            "QPushButton:hover { background-color: #10B981; }")
        btn_excel.clicked.connect(self._export_excel)
        header.addWidget(btn_excel)

        root.addLayout(header)

        # ── Table ────────────────────────────────────────────────────
        self._table = FilterTableView(body)
        tv = self._table.table_view
        tv.verticalHeader().setVisible(False)
        tv.verticalHeader().setDefaultSectionSize(18)
        tv.verticalHeader().setMinimumSectionSize(14)
        tv.setSelectionBehavior(tv.SelectionBehavior.SelectRows)

        # Show first N rows
        preview = self._full_df if self._showing_all else self._full_df.head(_PREVIEW_LIMIT)
        self._table.set_dataframe(preview, limit_rows=False)
        root.addWidget(self._table, 1)

        return body

    def _update_info_label(self, shown: int, total: int):
        if shown < total:
            self._lbl_info.setText(
                f"<b>{self._query_name}</b> — showing first "
                f"<b>{shown:,}</b> of <b>{total:,}</b> rows")
        else:
            self._lbl_info.setText(
                f"<b>{self._query_name}</b> — <b>{total:,}</b> rows")

    def _on_show_all(self):
        """Load the full dataset into the table."""
        self._table.set_dataframe(self._full_df, limit_rows=False)
        self._showing_all = True
        self._btn_show_all.setVisible(False)
        self._update_info_label(len(self._full_df), len(self._full_df))

    def _export_excel(self):
        """Dump the data into a new unsaved Excel workbook via COM."""
        from PyQt6.QtWidgets import QMessageBox
        from suiteview.core.excel_export import dump_to_new_workbook, ExcelExportError

        df = self._full_df if self._showing_all else self._full_df.head(_PREVIEW_LIMIT)
        headers = list(df.columns)
        rows = [
            [v if isinstance(v, (int, float, str, type(None))) else str(v) for v in row]
            for row in df.itertuples(index=False, name=None)
        ]
        try:
            dump_to_new_workbook(
                headers, rows,
                sheet_name=self._query_name,
                freeze_header=False,
                autofilter=False,
            )
        except ExcelExportError as exc:
            QMessageBox.warning(self, "Excel Error", str(exc))
