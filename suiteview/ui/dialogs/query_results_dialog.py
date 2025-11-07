"""Query Results Dialog - Display query results in a table"""

import logging
import pandas as pd
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QMessageBox, QFileDialog, QCheckBox, QMenu, QApplication)
from PyQt6.QtCore import Qt
from suiteview.ui.widgets.filter_table_view import FilterTableView

logger = logging.getLogger(__name__)


class QueryResultsDialog(QDialog):
    """Dialog for displaying query results"""

    def __init__(self, df: pd.DataFrame, sql: str, execution_time_ms: int, parent=None):
        super().__init__(parent)
        self.df = df
        self.sql = sql
        self.execution_time_ms = execution_time_ms
        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("Query Results")
        self.setMinimumSize(1000, 600)

        layout = QVBoxLayout(self)

        # Header with stats
        header_layout = QHBoxLayout()

        # Stats label
        record_count = len(self.df)
        stats_label = QLabel(
            f"<b>{record_count:,}</b> records returned in <b>{self.execution_time_ms}ms</b>"
        )
        stats_label.setStyleSheet("font-size: 12px; padding: 5px;")
        header_layout.addWidget(stats_label)

        header_layout.addStretch()

        # Format Excel checkbox
        self.format_excel_cb = QCheckBox("Apply Excel Formatting")
        self.format_excel_cb.setChecked(False)  # Default unchecked for speed
        self.format_excel_cb.setToolTip("Apply data type formatting (text, numbers, dates) - slower for large datasets")
        header_layout.addWidget(self.format_excel_cb)

        # Export to Excel button (green, smaller)
        export_excel_btn = QPushButton("Excel")
        export_excel_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        export_excel_btn.clicked.connect(self.export_to_excel_open)
        header_layout.addWidget(export_excel_btn)

        # Export to File button (smaller)
        export_btn = QPushButton("Save")
        export_btn.setObjectName("gold_button")
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        export_btn.clicked.connect(self.export_to_file)
        header_layout.addWidget(export_btn)

        layout.addLayout(header_layout)

        # FilterTableView - Excel-style filterable table
        self.filter_table = FilterTableView()
        self.filter_table.set_dataframe(self.df)
        
        # Style the table headers with standard grey and narrower height
        self.filter_table.setStyleSheet("""
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #000000;
                padding: 2px 4px;
                border: 1px solid #d0d0d0;
                font-weight: normal;
                font-size: 11px;
                height: 20px;
            }
            QTableView::item {
                padding: 2px 4px;
            }
            QTableView {
                gridline-color: #d0d0d0;
            }
        """)
        
        # Try to style row number headers if the table view has them
        try:
            # Access the underlying table view from FilterTableView
            if hasattr(self.filter_table, 'table_view'):
                table_view = self.filter_table.table_view
            else:
                table_view = self.filter_table
                
            if hasattr(table_view, 'verticalHeader'):
                vertical_header = table_view.verticalHeader()
                vertical_header.setDefaultSectionSize(20)
                vertical_header.setStyleSheet("""
                    QHeaderView::section {
                        background-color: #f0f0f0;
                        color: #000000;
                        padding: 2px;
                        border: 1px solid #d0d0d0;
                        font-size: 10px;
                        width: 40px;
                    }
                """)
        except Exception as e:
            logger.debug(f"Could not style vertical header: {e}")
        
        layout.addWidget(self.filter_table)

        # SQL display (collapsible) with context menu
        sql_label = QLabel("<b>Generated SQL:</b>")
        sql_label.setStyleSheet("margin-top: 10px;")
        layout.addWidget(sql_label)

        self.sql_display = QLabel(self.sql)
        self.sql_display.setWordWrap(True)
        self.sql_display.setStyleSheet("""
            background: #2c3e50;
            color: #ecf0f1;
            padding: 10px;
            border-radius: 4px;
            font-family: 'Consolas', monospace;
            font-size: 10px;
        """)
        self.sql_display.setMaximumHeight(100)
        self.sql_display.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        # Add context menu for SQL display
        self.sql_display.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sql_display.customContextMenuRequested.connect(self.show_sql_context_menu)
        
        layout.addWidget(self.sql_display)
    
    def show_sql_context_menu(self, position):
        """Show context menu for SQL display"""
        menu = QMenu(self)
        
        copy_action = menu.addAction("📋 Copy SQL")
        copy_action.triggered.connect(self.copy_sql_silent)
        
        menu.exec(self.sql_display.mapToGlobal(position))
    
    def copy_sql_silent(self):
        """Copy SQL to clipboard without showing message"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.sql)
        logger.info("SQL copied to clipboard")

    def export_to_excel_open(self):
        """Export results to Excel - opens new workbook without saving"""
        try:
            import win32com.client as win32
            
            # Get the currently filtered/displayed data
            export_df = self.filter_table.get_filtered_dataframe()
            
            # Check if formatting is requested
            apply_formatting = self.format_excel_cb.isChecked()
            
            # Create Excel application instance
            excel = win32.Dispatch('Excel.Application')
            excel.Visible = True
            excel.ScreenUpdating = False  # Disable screen updates for performance
            
            # Add a new workbook (Excel will name it Book1, Book2, etc.)
            wb = excel.Workbooks.Add()
            ws = wb.Worksheets(1)
            
            # Prepare data as 2D array (headers + data)
            data_array = []
            
            # Add headers as first row
            headers = [str(col) for col in export_df.columns]
            data_array.append(headers)
            
            # Add data rows, replacing NaN with empty string
            for row in export_df.values:
                data_row = [("" if pd.isna(val) else val) for val in row]
                data_array.append(data_row)
            
            # Write all data at once (much faster than cell-by-cell)
            num_rows = len(data_array)
            num_cols = len(headers)
            
            # Define range from A1 to last cell
            data_range = ws.Range(ws.Cells(1, 1), ws.Cells(num_rows, num_cols))
            data_range.Value = data_array
            
            # Format headers (always applied - fast operation)
            header_range = ws.Range(ws.Cells(1, 1), ws.Cells(1, num_cols))
            header_range.Font.Bold = True
            header_range.Interior.Color = 0x404040  # Dark gray
            header_range.Font.Color = 0xFFFFFF  # White
            
            # Apply column formatting only if requested
            if apply_formatting:
                for col_idx, (col_name, dtype) in enumerate(zip(export_df.columns, export_df.dtypes), start=1):
                    # Get the data range for this column (excluding header)
                    col_range = ws.Range(ws.Cells(2, col_idx), ws.Cells(num_rows, col_idx))
                    
                    # Determine format based on pandas dtype
                    if pd.api.types.is_integer_dtype(dtype):
                        # Integer - format with comma separator, no decimals
                        col_range.NumberFormat = "#,##0"
                    elif pd.api.types.is_float_dtype(dtype):
                        # Float - format with comma separator and 2 decimals
                        col_range.NumberFormat = "#,##0.00"
                    elif pd.api.types.is_datetime64_any_dtype(dtype):
                        # Date/DateTime - standard date format
                        col_range.NumberFormat = "mm/dd/yyyy hh:mm:ss"
                    else:
                        # String/Object - force text format to preserve leading zeros, etc.
                        col_range.NumberFormat = "@"  # @ means text format in Excel
            
            # Auto-fit columns
            ws.Columns.AutoFit()
            
            # Select cell A1
            ws.Range("A1").Select()
            
            # Re-enable screen updates
            excel.ScreenUpdating = True
            
            logger.info(f"Opened Excel with {len(export_df)} rows (formatting: {apply_formatting})")
            
            format_msg = "\n(Formatting applied)" if apply_formatting else "\n(No formatting applied - faster export)"
            
            QMessageBox.information(
                self,
                "Excel Opened",
                f"Data exported to Excel!\n\n"
                f"{len(export_df):,} rows exported (filtered data).{format_msg}\n\n"
                f"The workbook is open in Excel but not saved.\n"
                f"Use 'Save As' in Excel if you want to keep the file."
            )

        except ImportError:
            logger.error("win32com not available")
            QMessageBox.critical(
                self,
                "Export Failed",
                "Excel export requires pywin32 package.\n\n"
                "Install with: pip install pywin32"
            )
        except Exception as e:
            logger.error(f"Export to Excel failed: {e}")
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export to Excel:\n{str(e)}\n\n"
                "Make sure Excel is installed."
            )

    def export_to_file(self):
        """Export results to Excel file (save as)"""
        try:
            # Get the currently filtered/displayed data
            export_df = self.filter_table.get_filtered_dataframe()
            
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save to Excel File",
                "",
                "Excel Files (*.xlsx);;All Files (*)"
            )

            if file_path:
                if not file_path.endswith('.xlsx'):
                    file_path += '.xlsx'

                export_df.to_excel(file_path, index=False, engine='openpyxl')

                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Data exported successfully to:\n{file_path}\n\n"
                    f"{len(export_df):,} rows exported (filtered data)."
                )

        except Exception as e:
            logger.error(f"Export to file failed: {e}")
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export data:\n{str(e)}"
            )

    def export_to_excel(self):
        """Legacy method - redirects to export_to_file"""
        self.export_to_file()

    def copy_sql(self):
        """Copy SQL to clipboard"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.sql)

        QMessageBox.information(
            self,
            "SQL Copied",
            "SQL query has been copied to clipboard."
        )
