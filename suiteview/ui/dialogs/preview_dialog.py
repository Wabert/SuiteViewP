"""Preview Dialog - Shows table data in a filterable grid"""

import logging
import time
import pandas as pd
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                              QLabel, QLineEdit, QMessageBox, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIntValidator
from suiteview.ui.widgets.filter_table_view import FilterTableView

logger = logging.getLogger(__name__)


class PreviewFetchWorker(QThread):
    """Background worker thread for fetching preview data in chunks"""
    
    # Signals
    chunk_received = pyqtSignal(object, object, dict)  # (columns, chunk_data, progress_info)
    fetch_complete = pyqtSignal()
    fetch_error = pyqtSignal(str)
    
    def __init__(self, dsn, table_name, schema_name, limit, chunk_size=10000):
        super().__init__()
        self.dsn = dsn  # Pass DSN directly instead of connection_id
        self.table_name = table_name
        self.schema_name = schema_name
        self.limit = limit
        self.chunk_size = chunk_size
        self._cancelled = False
    
    def run(self):
        """Fetch data in chunks and emit signals"""
        try:
            import pyodbc
            import time
            
            logger.info(f"Worker thread: Starting chunked fetch from {self.schema_name}.{self.table_name}")
            
            # Connect to database in THIS thread
            conn_str = f"DSN={self.dsn};BLOCKSIZE=65535;MAXLOBSIZE=0;DEFERREDPREPARE=1;CURRENTPACKAGESET=NULLID"
            conn = pyodbc.connect(conn_str, autocommit=True)
            
            cursor = conn.cursor()
            cursor.arraysize = self.chunk_size
            
            # Build query
            qualified_table = f'{self.schema_name}.{self.table_name}'
            query = f"SELECT * FROM {qualified_table} FETCH FIRST {self.limit} ROWS ONLY WITH UR OPTIMIZE FOR {self.limit} ROWS"
            
            # Execute query
            cursor.execute(query)
            
            # Get column names
            columns = [column[0] for column in cursor.description]
            
            # Fetch data in chunks
            total_fetched = 0
            chunk_num = 0
            fetch_start = time.perf_counter()
            
            while total_fetched < self.limit:
                # Check if cancelled
                if self._cancelled:
                    logger.info("Worker thread: Fetch cancelled by user")
                    cursor.close()
                    conn.close()
                    return
                
                chunk_start = time.perf_counter()
                chunk = cursor.fetchmany(self.chunk_size)
                
                if not chunk:
                    break
                
                chunk_time = time.perf_counter() - chunk_start
                total_fetched += len(chunk)
                chunk_num += 1
                is_last = (len(chunk) < self.chunk_size) or (total_fetched >= self.limit)
                
                logger.info(f"Worker thread: Chunk {chunk_num} fetched {len(chunk):,} rows in {chunk_time:.2f}s (total: {total_fetched:,})")
                
                # Build progress info
                progress = {
                    'rows_fetched': total_fetched,
                    'total_rows': self.limit,
                    'chunk_number': chunk_num,
                    'is_last_chunk': is_last,
                    'elapsed_time': time.perf_counter() - fetch_start
                }
                
                # Emit chunk - first chunk includes columns
                if chunk_num == 1:
                    self.chunk_received.emit(columns, chunk, progress)
                else:
                    self.chunk_received.emit(None, chunk, progress)
                
                if is_last:
                    break
            
            cursor.close()
            conn.close()
            
            # All chunks fetched successfully
            self.fetch_complete.emit()
            
        except Exception as e:
            logger.error(f"Error in preview fetch worker: {e}", exc_info=True)
            self.fetch_error.emit(str(e))
    
    def cancel(self):
        """Cancel the fetch operation"""
        self._cancelled = True


class PreviewDialog(QWidget):
    """Window to preview table data with filtering capabilities (modeless)"""
    
    # Keep references to open windows to prevent garbage collection
    _open_windows = []

    def __init__(self, table_name: str, data: list, columns: list, parent=None, 
                 connection_id=None, schema_name=None, schema_discovery=None,
                 use_progressive_loading=False):
        # Create without parent for true modeless behavior
        super().__init__()
        self.table_name = table_name
        self.data = data
        self.columns = columns
        self.connection_id = connection_id
        self.schema_name = schema_name
        self.schema_discovery = schema_discovery
        self.current_limit = len(data) if data else 10000
        self.use_progressive_loading = use_progressive_loading
        
        # Progressive loading state
        self.fetch_worker = None
        self.accumulated_data = []
        self.is_loading = False
        
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

        # Progress bar for progressive loading (hidden by default)
        self.progress_layout = QHBoxLayout()
        self.progress_layout.setSpacing(10)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(True)
        self.progress_layout.addWidget(self.progress_bar)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setFixedHeight(26)
        self.cancel_btn.setFixedWidth(80)
        self.cancel_btn.clicked.connect(self.cancel_loading)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        self.progress_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(self.progress_layout)

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
        """Reload data with new record limit - uses progressive loading for large datasets"""
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
            
            if new_limit == self.current_limit and not self.is_loading:
                QMessageBox.information(self, "No Change", 
                    f"Already showing {self.current_limit:,} records.")
                return

            # Use progressive loading for large datasets (> 20k rows)
            if new_limit > 20000:
                self.start_progressive_loading(new_limit)
            else:
                self.load_data_immediately(new_limit)

        except Exception as e:
            logger.error(f"Error reloading data: {e}")
            QMessageBox.critical(self, "Error", f"Failed to reload data:\n{str(e)}")

    def load_data_immediately(self, limit):
        """Load data all at once (for smaller datasets)"""
        logger.info(f"Loading {limit:,} rows immediately (non-progressive)")
        
        # Show loading message
        self.info_label.setText(f"Loading {limit:,} records...")
        self.info_label.repaint()

        try:
            # Fetch data
            columns, data = self.schema_discovery.get_preview_data(
                self.connection_id,
                self.table_name.split('.')[-1],
                self.schema_name,
                limit=limit
            )

            # Update display
            self.data = data
            self.columns = columns
            self.current_limit = len(data)
            self.info_label.setText(f"Showing first <b>{len(data):,}</b> rows")

            # Update table
            data_rows = [tuple(row) if not isinstance(row, (list, tuple)) else row for row in data]
            df = pd.DataFrame(data_rows, columns=columns)
            self.filter_table.set_dataframe(df)
            
            logger.info(f"Loaded {len(data):,} rows successfully")

        except Exception as e:
            logger.error(f"Error loading data immediately: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load data:\n{str(e)}")
            self.info_label.setText(f"Showing first <b>{len(self.data):,}</b> rows")

    def start_progressive_loading(self, limit):
        """Start progressive loading in background thread"""
        logger.info(f"Starting progressive loading for {limit:,} rows")
        
        if self.is_loading:
            QMessageBox.warning(self, "Loading in Progress", 
                "Data is already being loaded. Please wait or cancel.")
            return
        
        # Get connection info in MAIN thread (before starting worker)
        try:
            connection = self.schema_discovery.conn_manager.get_connection(self.connection_id)
            if not connection:
                raise ValueError(f"Connection {self.connection_id} not found")
            
            dsn = connection.get('connection_string', '').replace('DSN=', '')
            if not dsn:
                raise ValueError("DB2 connection requires DSN")
                
        except Exception as e:
            logger.error(f"Failed to get connection info: {e}")
            QMessageBox.critical(self, "Error", f"Failed to get connection info:\n{str(e)}")
            return
        
        # Reset state
        self.accumulated_data = []
        self.is_loading = True
        
        # Show progress UI
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Loading... 0 of %v rows")
        self.progress_bar.setMaximum(limit)
        self.cancel_btn.setVisible(True)
        self.info_label.setText(f"Loading {limit:,} records...")
        
        # Clear existing table
        self.filter_table.set_dataframe(pd.DataFrame())
        
        # Start worker thread with DSN (not connection_id)
        self.fetch_worker = PreviewFetchWorker(
            dsn,  # Pass DSN directly
            self.table_name.split('.')[-1],
            self.schema_name,
            limit,
            chunk_size=10000
        )
        
        # Connect signals
        self.fetch_worker.chunk_received.connect(self.on_chunk_received)
        self.fetch_worker.fetch_complete.connect(self.on_fetch_complete)
        self.fetch_worker.fetch_error.connect(self.on_fetch_error)
        
        # Start fetching
        self.fetch_worker.start()

    def on_chunk_received(self, columns, chunk_data, progress_info):
        """Handle a chunk of data from the worker thread"""
        try:
            # Store columns from first chunk
            if columns is not None:
                self.columns = columns
            
            # Accumulate data
            self.accumulated_data.extend(chunk_data)
            
            # Update progress
            rows_fetched = progress_info['rows_fetched']
            total_rows = progress_info['total_rows']
            elapsed = progress_info['elapsed_time']
            
            self.progress_bar.setValue(rows_fetched)
            self.progress_bar.setFormat(f"Loading... {rows_fetched:,} of {total_rows:,} rows ({elapsed:.1f}s)")
            
            # Update table progressively
            data_rows = [tuple(row) if not isinstance(row, (list, tuple)) else row for row in self.accumulated_data]
            df = pd.DataFrame(data_rows, columns=self.columns)
            self.filter_table.set_dataframe(df)
            
            logger.info(f"Updated table with {rows_fetched:,} rows (chunk {progress_info['chunk_number']})")
            
        except Exception as e:
            logger.error(f"Error processing chunk: {e}")

    def on_fetch_complete(self):
        """Handle fetch completion"""
        logger.info(f"Progressive loading complete: {len(self.accumulated_data):,} rows")
        
        # Update state
        self.data = self.accumulated_data
        self.current_limit = len(self.data)
        self.is_loading = False
        
        # Hide progress UI
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        
        # Update info label
        self.info_label.setText(f"Showing first <b>{len(self.data):,}</b> rows")
        
        # Clean up worker
        self.fetch_worker = None

    def on_fetch_error(self, error_msg):
        """Handle fetch error"""
        logger.error(f"Progressive loading error: {error_msg}")
        
        self.is_loading = False
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        
        QMessageBox.critical(self, "Error", f"Failed to load data:\n{error_msg}")
        
        # Restore previous data if any
        if self.data:
            self.info_label.setText(f"Showing first <b>{len(self.data):,}</b> rows")
        
        self.fetch_worker = None

    def cancel_loading(self):
        """Cancel ongoing progressive loading"""
        if self.fetch_worker and self.is_loading:
            logger.info("Cancelling progressive loading")
            self.fetch_worker.cancel()
            self.fetch_worker.wait()  # Wait for thread to finish
            
            self.is_loading = False
            self.progress_bar.setVisible(False)
            self.cancel_btn.setVisible(False)
            
            # Keep whatever data we've loaded so far
            if self.accumulated_data:
                self.data = self.accumulated_data
                self.current_limit = len(self.data)
                self.info_label.setText(f"Showing first <b>{len(self.data):,}</b> rows (cancelled)")
            else:
                self.info_label.setText("Loading cancelled")
            
            self.fetch_worker = None
