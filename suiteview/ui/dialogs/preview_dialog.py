"""Preview Dialog - Shows table data in a grid"""

import logging
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                              QTableWidgetItem, QPushButton, QLabel, QHeaderView)
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)


class PreviewDialog(QDialog):
    """Dialog to preview table data"""

    def __init__(self, table_name: str, data: list, columns: list, parent=None):
        super().__init__(parent)
        self.table_name = table_name
        self.data = data
        self.columns = columns

        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle(f"Preview: {self.table_name}")
        self.resize(1000, 600)

        # Main layout
        layout = QVBoxLayout(self)

        # Header with info
        info_label = QLabel(f"Showing first {len(self.data)} rows")
        info_label.setStyleSheet("""
            font-size: 12px;
            font-weight: 600;
            color: #2c3e50;
            padding: 10px;
        """)
        layout.addWidget(info_label)

        # Data table
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.setHorizontalHeaderLabels(self.columns)
        self.table.setRowCount(len(self.data))

        # Configure table
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)

        # Populate data
        for row_idx, row_data in enumerate(self.data):
            for col_idx, value in enumerate(row_data):
                # Convert value to string for display
                display_value = str(value) if value is not None else ""
                item = QTableWidgetItem(display_value)
                self.table.setItem(row_idx, col_idx, item)

        layout.addWidget(self.table)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        logger.info(f"Preview dialog created with {len(self.data)} rows, {len(self.columns)} columns")
