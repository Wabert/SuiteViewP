"""
QueryPreviewWindow — lightweight viewer for DataForge query results.

Shows the first 1,000 rows by default with a "Show All Rows" button
to load the full dataset into the table.
"""
from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

from suiteview.ui.widgets.filter_table_view import FilterTableView

_PREVIEW_LIMIT = 1000


class QueryPreviewWindow(QWidget):
    """Modeless window showing a preview of a DataForge query's cached data."""

    def __init__(self, query_name: str, df: pd.DataFrame, parent=None):
        super().__init__(parent)
        self._query_name = query_name
        self._full_df = df
        self._showing_all = len(df) <= _PREVIEW_LIMIT

        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumSize(900, 550)
        self.resize(1000, 600)
        self.setWindowTitle(f"View — {query_name}")

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
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
        self._table = FilterTableView(self)
        tv = self._table.table_view
        tv.verticalHeader().setVisible(False)
        tv.verticalHeader().setDefaultSectionSize(18)
        tv.verticalHeader().setMinimumSectionSize(14)
        tv.setSelectionBehavior(tv.SelectionBehavior.SelectRows)

        # Show first N rows
        preview = self._full_df if self._showing_all else self._full_df.head(_PREVIEW_LIMIT)
        self._table.set_dataframe(preview, limit_rows=False)
        root.addWidget(self._table, 1)

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
        try:
            import win32com.client
            xl = win32com.client.Dispatch("Excel.Application")
            xl.Visible = True
            wb = xl.Workbooks.Add()
            ws = wb.ActiveSheet
            ws.Name = self._query_name[:31]  # Excel sheet name limit

            df = self._full_df if self._showing_all else self._full_df.head(_PREVIEW_LIMIT)

            # Write headers
            for c, col in enumerate(df.columns, 1):
                ws.Cells(1, c).Value = col

            # Write data in bulk
            if len(df) > 0:
                data = []
                for row in df.itertuples(index=False, name=None):
                    data.append([
                        str(v) if not isinstance(v, (int, float, str, type(None))) else v
                        for v in row
                    ])
                ws.Range(
                    ws.Cells(2, 1),
                    ws.Cells(len(data) + 1, len(df.columns))
                ).Value = data

            # Autofit columns
            ws.Columns.AutoFit()
            # Bold headers
            ws.Range(ws.Cells(1, 1), ws.Cells(1, len(df.columns))).Font.Bold = True

        except Exception as exc:
            QMessageBox.warning(self, "Excel Error", str(exc))
