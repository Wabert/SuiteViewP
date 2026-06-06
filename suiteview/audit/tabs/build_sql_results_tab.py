"""
Build SQL Results tab — displays results from user-edited SQL queries.

Shows query output in a FilterTableView, matching the style of the
main Results tab.
"""
from __future__ import annotations

import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox, QInputDialog,
)
from PyQt6.QtGui import QFont

from suiteview.ui.widgets.filter_table_view import FilterTableView

_FONT = QFont("Segoe UI", 9)


class BuildSqlResultsTab(QWidget):
    """Build SQL Results tab — shows output from user-edited queries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._sql = ""
        self._dsn = ""
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        self.table = FilterTableView(self)

        tv = self.table.table_view
        tv.verticalHeader().setVisible(False)
        tv.verticalHeader().setDefaultSectionSize(16)
        tv.verticalHeader().setMinimumSectionSize(14)
        tv.setSelectionBehavior(tv.SelectionBehavior.SelectRows)
        tv.setEditTriggers(tv.EditTrigger.NoEditTriggers)

        tv.setStyleSheet("""
            QTableView#filterTableView {
                gridline-color: transparent;
                background-color: white;
                alternate-background-color: white;
                selection-background-color: #e0e8f0;
                selection-color: black;
                font-size: 9pt;
                border: none;
            }
            QTableView#filterTableView::item {
                padding: 0px 2px;
                border: none;
            }
            QTableView#filterTableView::item:selected {
                background-color: #e0e8f0;
                color: black;
            }
            QTableView#filterTableView::item:hover {
                background-color: transparent;
            }
            QHeaderView::section {
                background-color: #e8e8e8;
                color: #000000;
                font-weight: normal;
                font-size: 8pt;
                padding: 1px 16px 1px 4px;
                border: 1px solid #c0c0c0;
            }
            QHeaderView::section:hover {
                background-color: #d8d8d8;
            }
        """)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.btn_save_object = QPushButton("Save Object")
        self.btn_save_object.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_save_object.setFixedSize(100, 28)
        self.btn_save_object.setStyleSheet(
            "QPushButton { background-color: #7C3AED; color: white;"
            " border: 1px solid #6D28D9; border-radius: 3px; }"
            "QPushButton:hover { background-color: #8B5CF6; }"
            "QPushButton:disabled { background-color: #C4B5FD; }"
        )
        self.btn_save_object.setEnabled(False)
        self.btn_save_object.setToolTip("Save this manual SQL result schema as a Query Object")
        self.btn_save_object.clicked.connect(self._on_save_object)
        bottom.addWidget(self.btn_save_object)
        root.addLayout(bottom)

    def set_results(self, df: pd.DataFrame, *, sql: str = "", dsn: str = ""):
        """Load query results into the table."""
        self._df = df
        self._sql = sql
        self._dsn = dsn
        self.table.set_dataframe(df, limit_rows=False)
        self.btn_save_object.setEnabled(bool(sql) and df is not None)

    def _on_save_object(self):
        if self._df is None or not self._sql:
            QMessageBox.information(self, "No Results", "Run SQL before saving an object.")
            return
        name, ok = QInputDialog.getText(
            self,
            "Save Manual SQL Object",
            "Object name:",
            text="Manual SQL Object",
        )
        if not ok or not name.strip():
            return
        from suiteview.audit.query_object import manual_sql_query_object
        from suiteview.audit import query_object_store

        column_types = {column: str(self._df[column].dtype) for column in self._df.columns}
        obj = manual_sql_query_object(
            name.strip(),
            sql=self._sql,
            dsn=self._dsn,
            result_columns=list(self._df.columns),
            column_types=column_types,
        )
        query_object_store.save_object(obj)
        QMessageBox.information(
            self,
            "Query Object Saved",
            f"Manual SQL query object \"{obj.name}\" saved successfully.",
        )
