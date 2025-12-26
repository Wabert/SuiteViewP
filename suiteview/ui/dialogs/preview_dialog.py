"""Preview Dialog - Shows table data in a filterable grid"""

import logging
import time
import pandas as pd
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                              QLabel, QLineEdit, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from suiteview.ui.widgets.filter_table_view import FilterTableView

logger = logging.getLogger(__name__)


class PreviewDialog(QWidget):
    """Window to preview table data with filtering capabilities (modeless)"""
    
    # Keep references to open windows to prevent garbage collection
    _open_windows = []

    def __init__(self, table_name: str, data: list, columns: list, parent=None, 
                 connection_id=None, schema_name=None, schema_discovery=None):
        # Create without parent for true modeless behavior
        super().__init__()
        self.table_name = table_name
        self.data = data
        self.columns = columns
        self.connection_id = connection_id
        self.schema_name = schema_name
        self.schema_discovery = schema_discovery
        self.current_limit = len(data)
        
        # Make this a top-level independent window
        self.setWindowFlags(Qt.WindowType.Window)
        # Delete on close to free memory
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        # Track this window
        PreviewDialog._open_windows.append(self)

        self.init_ui()
    
    def closeEvent(self, event):
        """Remove from tracking when closed"""
        if self in PreviewDialog._open_windows:
            PreviewDialog._open_windows.remove(self)
        super().closeEvent(event)

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle(f"Preview: {self.table_name}")
        self.setMinimumSize(1200, 700)

        # Main layout
        layout = QVBoxLayout(self)

        # Header with controls - compact and uniform styling
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        header_layout.setContentsMargins(5, 5, 5, 5)

        # Info label with better contrast
        self.info_label = QLabel(f"Showing first <b>{len(self.data):,}</b> rows")
        self.info_label.setStyleSheet("""
            font-size: 11px; 
            color: #2c3e50;
            font-weight: bold;
            padding: 4px 8px;
        """)
        header_layout.addWidget(self.info_label)

        header_layout.addStretch()

        # Record limit control - compact and uniform
        if self.schema_discovery and self.connection_id:
            limit_label = QLabel("Records:")
            limit_label.setStyleSheet("""
                font-size: 11px;
                color: #2c3e50;
                font-weight: bold;
                padding: 4px;
            """)
            header_layout.addWidget(limit_label)

            self.limit_input = QLineEdit()
            self.limit_input.setText(str(self.current_limit))
            self.limit_input.setValidator(QIntValidator(100, 1000000))
            self.limit_input.setToolTip("Number of records to fetch from the database")
            self.limit_input.setFixedWidth(90)
            self.limit_input.setFixedHeight(26)
            self.limit_input.setStyleSheet("""
                QLineEdit {
                    padding: 3px 8px;
                    border: 1px solid #bdc3c7;
                    border-radius: 3px;
                    background: white;
                    color: black;
                    font-size: 11px;
                }
                QLineEdit:focus {
                    border: 1px solid #3498db;
                }
            """)
            header_layout.addWidget(self.limit_input)

            # Reload button - uniform size and better styling
            reload_btn = QPushButton("Reload")
            reload_btn.setToolTip("Reload data with new record limit")
            reload_btn.clicked.connect(self.reload_data)
            reload_btn.setFixedHeight(26)
            reload_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    padding: 4px 12px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #21618c;
                }
            """)
            header_layout.addWidget(reload_btn)

        # Close button - uniform size and better styling
        close_btn = QPushButton("Close")
        close_btn.setToolTip("Close this preview window")
        close_btn.clicked.connect(self.close)
        close_btn.setFixedHeight(26)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
            QPushButton:pressed {
                background-color: #626c6d;
            }
        """)

        layout.addLayout(header_layout)

        # FilterTableView - Excel-style filterable table
        self.filter_table = FilterTableView()
        
        # Convert data to DataFrame with error handling
        try:
            # Validate data shape
            if self.data and len(self.data) > 0:
                # Get first row length - handle various row types (list, tuple, pyodbc.Row, etc.)
                first_row = self.data[0]
                if hasattr(first_row, '__len__'):
                    first_row_len = len(first_row)
                else:
                    first_row_len = 1
                    
                logger.info(f"Creating DataFrame: {len(self.data)} rows x {len(self.columns)} columns. First row has {first_row_len} values")
                
                if first_row_len != len(self.columns):
                    logger.error(f"Data shape mismatch: first row has {first_row_len} values but {len(self.columns)} columns expected")
                    raise ValueError(f"Data shape mismatch: got {first_row_len} values per row, expected {len(self.columns)} columns")
            
            # Convert data to list of tuples if needed (handles pyodbc.Row objects)
            data_rows = [tuple(row) if not isinstance(row, (list, tuple)) else row for row in self.data]
            
            df = pd.DataFrame(data_rows, columns=self.columns)
            self.filter_table.set_dataframe(df)
            logger.info(f"Preview dialog created with {len(self.data)} rows, {len(self.columns)} columns")
        except Exception as e:
            logger.error(f"Failed to create DataFrame: {e}")
            QMessageBox.critical(self, "Error", f"Failed to preview table:\n{str(e)}")
            self.close()
            return
        
        layout.addWidget(self.filter_table)

    def reload_data(self):
        """Reload data with new record limit"""
        start_time = time.perf_counter()
        logger.info(f"⏱️ [RELOAD] Reload button clicked")
        
        if not self.schema_discovery or not self.connection_id:
            return

        try:
            # Get and validate the limit value
            limit_text = self.limit_input.text().strip()
            if not limit_text:
                QMessageBox.warning(self, "Invalid Input", "Please enter a number of records.")
                return
            
            try:
                new_limit = int(limit_text)
            except ValueError:
                QMessageBox.warning(self, "Invalid Input", "Please enter a valid number.")
                return
            
            if new_limit < 100 or new_limit > 1000000:
                QMessageBox.warning(self, "Invalid Range", "Please enter a value between 100 and 1,000,000.")
                return
            
            if new_limit == self.current_limit:
                QMessageBox.information(self, "No Change", 
                    f"Already showing {self.current_limit:,} records.")
                return

            logger.info(f"⏱️ [RELOAD] Reloading preview data with limit: {new_limit}")
            
            # Show loading message
            self.info_label.setText(f"Loading {new_limit:,} records...")
            self.info_label.repaint()

            # Fetch new data
            fetch_start = time.perf_counter()
            columns, data = self.schema_discovery.get_preview_data(
                self.connection_id,
                self.table_name.split('.')[-1],  # Extract table name if schema.table format
                self.schema_name,
                limit=new_limit
            )
            fetch_time = time.perf_counter()
            logger.info(f"⏱️ [RELOAD]   - Fetch data from database: {len(data)} rows in {(fetch_time - fetch_start)*1000:.2f}ms")

            # Update the display
            self.data = data
            self.columns = columns
            self.current_limit = len(data)

            # Update info label
            self.info_label.setText(f"Showing first <b>{len(data):,}</b> rows")

            # Update the table
            df_start = time.perf_counter()
            try:
                # Validate data shape before creating DataFrame
                if data and len(data) > 0:
                    # Get first row length - handle various row types
                    first_row = data[0]
                    if hasattr(first_row, '__len__'):
                        first_row_len = len(first_row)
                    else:
                        first_row_len = 1
                        
                    logger.info(f"Reload: Creating DataFrame with {len(data)} rows x {len(columns)} columns. First row has {first_row_len} values")
                    
                    if first_row_len != len(columns):
                        logger.error(f"Data shape mismatch in reload: first row has {first_row_len} values but {len(columns)} columns expected")
                        raise ValueError(f"Data shape mismatch: got {first_row_len} values per row, expected {len(columns)} columns")
                
                # Convert data to list of tuples if needed (handles pyodbc.Row objects)
                data_rows = [tuple(row) if not isinstance(row, (list, tuple)) else row for row in data]
                
                df = pd.DataFrame(data_rows, columns=columns)
                df_time = time.perf_counter()
                logger.info(f"⏱️ [RELOAD]   - Create DataFrame in {(df_time - df_start)*1000:.2f}ms")
                
                set_df_start = time.perf_counter()
                self.filter_table.set_dataframe(df)
                set_df_time = time.perf_counter()
                logger.info(f"⏱️ [RELOAD]   - set_dataframe (includes pre-computation) in {(set_df_time - set_df_start)*1000:.2f}ms")
            except Exception as e:
                logger.error(f"Failed to create DataFrame during reload: {e}")
                QMessageBox.critical(self, "Error", f"Failed to reload data:\n{str(e)}")
                return

            end_time = time.perf_counter()
            logger.info(f"⏱️ [RELOAD] TOTAL reload time: {(end_time - start_time)*1000:.2f}ms")
            logger.info(f"⏱️ [RELOAD] Preview data reloaded: {len(data)} rows")

        except Exception as e:
            logger.error(f"Error reloading data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to reload data:\n{str(e)}")
            # Restore original info label
            self.info_label.setText(f"Showing first <b>{len(self.data):,}</b> rows")
