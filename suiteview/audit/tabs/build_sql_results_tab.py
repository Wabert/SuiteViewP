"""
Build SQL Results tab — displays results from user-edited SQL queries.

Shows query output in a FilterTableView, matching the style of the
main Results tab.
"""
from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtGui import QFont

from suiteview.ui.widgets.filter_table_view import FilterTableView

_FONT = QFont("Segoe UI", 9)


class BuildSqlResultsTab(QWidget):
    """Build SQL Results tab — shows output from user-edited queries."""

    def __init__(self, parent=None):
        super().__init__(parent)
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

    def set_results(self, df: pd.DataFrame):
        """Load query results into the table."""
        self.table.set_dataframe(df, limit_rows=False)
