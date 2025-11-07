"""Preview Dialog - Shows table data in a filterable grid"""

import logging
import pandas as pd
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                              QLabel, QLineEdit, QMessageBox, QSpinBox)
from PyQt6.QtCore import Qt
from suiteview.ui.widgets.filter_table_view import FilterTableView

logger = logging.getLogger(__name__)


class PreviewDialog(QDialog):
    """Dialog to preview table data with filtering capabilities"""

    def __init__(self, table_name: str, data: list, columns: list, parent=None, 
                 connection_id=None, schema_name=None, schema_discovery=None):
        super().__init__(parent)
        self.table_name = table_name
        self.data = data
        self.columns = columns
        self.connection_id = connection_id
        self.schema_name = schema_name
        self.schema_discovery = schema_discovery
        self.current_limit = len(data)

        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle(f"Preview: {self.table_name}")
        self.setMinimumSize(1200, 700)

        # Main layout
        layout = QVBoxLayout(self)

        # Header with controls
        header_layout = QHBoxLayout()

        # Info label
        self.info_label = QLabel(f"Showing first <b>{len(self.data):,}</b> rows")
        self.info_label.setStyleSheet("font-size: 12px; padding: 5px;")
        header_layout.addWidget(self.info_label)

        header_layout.addStretch()

        # Record limit control
        if self.schema_discovery and self.connection_id:
            limit_label = QLabel("Records to load:")
            limit_label.setStyleSheet("font-weight: bold;")
            header_layout.addWidget(limit_label)

            self.limit_spinbox = QSpinBox()
            self.limit_spinbox.setMinimum(100)
            self.limit_spinbox.setMaximum(1000000)
            self.limit_spinbox.setSingleStep(100)
            self.limit_spinbox.setValue(self.current_limit)
            self.limit_spinbox.setToolTip("Number of records to fetch from the database")
            self.limit_spinbox.setMinimumWidth(100)
            header_layout.addWidget(self.limit_spinbox)

            # Reload button
            reload_btn = QPushButton("🔄 Reload")
            reload_btn.setToolTip("Reload data with new record limit")
            reload_btn.clicked.connect(self.reload_data)
            reload_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)
            header_layout.addWidget(reload_btn)

        # Close button
        close_btn = QPushButton("✖ Close")
        close_btn.clicked.connect(self.accept)
        header_layout.addWidget(close_btn)

        layout.addLayout(header_layout)

        # FilterTableView - Excel-style filterable table
        self.filter_table = FilterTableView()
        
        # Convert data to DataFrame
        df = pd.DataFrame(self.data, columns=self.columns)
        self.filter_table.set_dataframe(df)
        
        layout.addWidget(self.filter_table)

        logger.info(f"Preview dialog created with {len(self.data)} rows, {len(self.columns)} columns")

    def reload_data(self):
        """Reload data with new record limit"""
        if not self.schema_discovery or not self.connection_id:
            return

        try:
            new_limit = self.limit_spinbox.value()
            
            if new_limit == self.current_limit:
                QMessageBox.information(self, "No Change", 
                    f"Already showing {self.current_limit:,} records.")
                return

            logger.info(f"Reloading preview data with limit: {new_limit}")
            
            # Show loading message
            self.info_label.setText(f"Loading {new_limit:,} records...")
            self.info_label.repaint()

            # Fetch new data
            columns, data = self.schema_discovery.get_preview_data(
                self.connection_id,
                self.table_name.split('.')[-1],  # Extract table name if schema.table format
                self.schema_name,
                limit=new_limit
            )

            # Update the display
            self.data = data
            self.columns = columns
            self.current_limit = len(data)

            # Update info label
            self.info_label.setText(f"Showing first <b>{len(data):,}</b> rows")

            # Update the table
            df = pd.DataFrame(data, columns=columns)
            self.filter_table.set_dataframe(df)

            logger.info(f"Preview data reloaded: {len(data)} rows")

        except Exception as e:
            logger.error(f"Error reloading data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to reload data:\n{str(e)}")
            # Restore original info label
            self.info_label.setText(f"Showing first <b>{len(self.data):,}</b> rows")
