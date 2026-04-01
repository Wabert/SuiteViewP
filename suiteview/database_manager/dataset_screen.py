"""
Data Set Screen - Dynamic SQL builder with Python scripting
"""

import logging
from pathlib import Path
import json
import re
from typing import Optional, Dict, Any
import sqlparse
import sys
from datetime import datetime
import psutil

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QLineEdit, QTextEdit, QTabWidget,
                              QSplitter, QListWidget, QMessageBox, QDialog,
                              QDialogButtonBox, QFormLayout, QTableWidget,
                              QTableWidgetItem, QHeaderView, QAbstractItemView,
                              QComboBox, QCheckBox, QFrame, QGroupBox, QListWidgetItem,
                              QSpinBox, QScrollArea, QApplication, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QTime
from PyQt6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat

from suiteview.models.data_set import DataSet, DataSetParameter, DataSetField
from suiteview.data.repositories import SavedTableRepository, ConnectionRepository, get_metadata_cache_repository
from suiteview.core.schema_discovery import SchemaDiscovery
from suiteview.core.query_executor import QueryExecutor
from suiteview.ui.dialogs.query_results_dialog import QueryResultsDialog
from suiteview.ui.widgets.filter_table_view import FilterTableView

logger = logging.getLogger(__name__)


class UndoRedoManager:
    """Helper class to manage undo/redo functionality for text editors"""
    
    def __init__(self, text_edit: QTextEdit):
        self.text_edit = text_edit
        self.undo_btn = None
        self.redo_btn = None
        
        # Connect to document signals to update button states
        self.text_edit.undoAvailable.connect(self._update_undo_state)
        self.text_edit.redoAvailable.connect(self._update_redo_state)
    
    def create_toolbar_buttons(self) -> tuple:
        """Create and return undo/redo buttons for toolbar"""
        button_style = """
            QPushButton {
                background-color: #ffffff;
                color: #0078d4;
                padding: 2px 6px;
                font-size: 9pt;
                border: 1px solid #0078d4;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
            }
            QPushButton:disabled {
                background-color: #f5f5f5;
                color: #cccccc;
                border-color: #cccccc;
            }
        """
        
        self.undo_btn = QPushButton("↶ Undo")
        self.undo_btn.setFixedWidth(70)
        self.undo_btn.setFixedHeight(26)
        self.undo_btn.setStyleSheet(button_style)
        self.undo_btn.clicked.connect(self.text_edit.undo)
        self.undo_btn.setEnabled(False)
        
        self.redo_btn = QPushButton("↷ Redo")
        self.redo_btn.setFixedWidth(70)
        self.redo_btn.setFixedHeight(26)
        self.redo_btn.setStyleSheet(button_style)
        self.redo_btn.clicked.connect(self.text_edit.redo)
        self.redo_btn.setEnabled(False)
        
        return self.undo_btn, self.redo_btn
    
    def _update_undo_state(self, available: bool):
        """Update undo button enabled state"""
        if self.undo_btn:
            self.undo_btn.setEnabled(available)
    
    def _update_redo_state(self, available: bool):
        """Update redo button enabled state"""
        if self.redo_btn:
            self.redo_btn.setEnabled(available)


class SQLHighlighter(QSyntaxHighlighter):
    """SQL syntax highlighter with color formatting"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Define formats for different SQL elements
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor("#0000FF"))  # Blue
        self.keyword_format.setFontWeight(QFont.Weight.Bold)
        
        self.function_format = QTextCharFormat()
        self.function_format.setForeground(QColor("#FF00FF"))  # Magenta
        
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#00AA00"))  # Green
        
        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#FF6600"))  # Orange
        
        # SQL keywords
        self.keywords = [
            'SELECT', 'FROM', 'WHERE', 'INNER', 'JOIN', 'LEFT', 'RIGHT', 'OUTER',
            'ON', 'AND', 'OR', 'NOT', 'IN', 'LIKE', 'BETWEEN', 'IS', 'NULL',
            'AS', 'ORDER', 'BY', 'GROUP', 'HAVING', 'LIMIT', 'OFFSET', 'FETCH',
            'FIRST', 'ROWS', 'ONLY', 'UNION', 'ALL', 'DISTINCT', 'ASC', 'DESC',
            'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE', 'CREATE',
            'TABLE', 'ALTER', 'DROP', 'INDEX', 'VIEW', 'CASE', 'WHEN', 'THEN',
            'ELSE', 'END', 'WITH'
        ]
        
        # SQL functions
        self.functions = [
            'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'ROUND', 'REAL', 'LEFT', 'RIGHT',
            'SUBSTRING', 'TRIM', 'RTRIM', 'LTRIM', 'UPPER', 'LOWER', 'CAST',
            'COALESCE', 'NULLIF', 'LENGTH', 'CONCAT'
        ]
    
    def highlightBlock(self, text):
        """Apply syntax highlighting to a block of text"""
        
        # Highlight keywords
        for keyword in self.keywords:
            pattern = r'\b' + keyword + r'\b'
            for match in re.finditer(pattern, text, re.IGNORECASE):
                self.setFormat(match.start(), match.end() - match.start(), self.keyword_format)
        
        # Highlight functions
        for function in self.functions:
            pattern = r'\b' + function + r'\s*\('
            for match in re.finditer(pattern, text, re.IGNORECASE):
                self.setFormat(match.start(), len(function), self.function_format)
        
        # Highlight strings (single quotes)
        for match in re.finditer(r"'[^']*'", text):
            self.setFormat(match.start(), match.end() - match.start(), self.string_format)
        
        # Highlight numbers
        for match in re.finditer(r'\b\d+\.?\d*\b', text):
            self.setFormat(match.start(), match.end() - match.start(), self.number_format)


class PythonSyntaxHighlighter(QSyntaxHighlighter):
    """Simple Python syntax highlighter"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Define formatting styles
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor("#CC7832"))
        self.keyword_format.setFontWeight(700)
        
        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#6A8759"))
        
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#808080"))
        self.comment_format.setFontItalic(True)
        
        self.function_format = QTextCharFormat()
        self.function_format.setForeground(QColor("#FFC66D"))
        
        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#6897BB"))
        
        # Python keywords
        self.keywords = [
            'def', 'class', 'if', 'elif', 'else', 'for', 'while', 'return',
            'import', 'from', 'as', 'try', 'except', 'finally', 'with',
            'None', 'True', 'False', 'and', 'or', 'not', 'in', 'is',
            'lambda', 'pass', 'break', 'continue', 'yield'
        ]
    
    def highlightBlock(self, text):
        """Highlight a block of text"""
        # Keywords
        for keyword in self.keywords:
            pattern = r'\b' + keyword + r'\b'
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), self.keyword_format)
        
        # Strings
        for match in re.finditer(r'(["\'])(?:(?=(\\?))\2.)*?\1', text):
            self.setFormat(match.start(), match.end() - match.start(), self.string_format)
        
        # Comments
        for match in re.finditer(r'#.*$', text):
            self.setFormat(match.start(), match.end() - match.start(), self.comment_format)
        
        # Numbers
        for match in re.finditer(r'\b\d+\.?\d*\b', text):
            self.setFormat(match.start(), match.end() - match.start(), self.number_format)


class DataSetParametersDialog(QDialog):
    """Dialog for entering Data Set parameter values at runtime"""
    
    def __init__(self, parent, dataset: DataSet):
        super().__init__(parent)
        self.dataset = dataset
        self.param_widgets = {}
        
        self.setWindowTitle(f"Run Data Set: {dataset.name}")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        self.init_ui()





class DataSetParametersDialog(QDialog):
    """Dialog for entering Data Set parameter values at runtime"""
    
    def __init__(self, parent, dataset: DataSet):
        super().__init__(parent)
        self.dataset = dataset
        self.param_widgets = {}
        
        self.setWindowTitle(f"Run Data Set: {dataset.name}")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        
        # Description
        if self.dataset.description:
            desc_label = QLabel(self.dataset.description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #666; font-style: italic; padding: 10px;")
            layout.addWidget(desc_label)
        
        # Parameters form
        params_group = QGroupBox("Parameters")
        params_form = QFormLayout()
        
        for param in self.dataset.parameters:
            label = QLabel(param.name + ("*" if param.required else ""))
            
            # Create appropriate widget based on type
            if param.param_type == "boolean":
                widget = QCheckBox()
                if param.default_value is not None:
                    widget.setChecked(bool(param.default_value))
            elif param.param_type == "number":
                widget = QLineEdit()
                if param.default_value is not None:
                    widget.setText(str(param.default_value))
                widget.setPlaceholderText("Enter number...")
            elif param.param_type == "list":
                widget = QTextEdit()
                widget.setMaximumHeight(80)
                if param.default_value is not None:
                    if isinstance(param.default_value, list):
                        widget.setPlainText('\n'.join(str(v) for v in param.default_value))
                    else:
                        widget.setPlainText(str(param.default_value))
                widget.setPlaceholderText("Enter values (one per line)...")
            else:  # text, date
                widget = QLineEdit()
                if param.default_value is not None:
                    widget.setText(str(param.default_value))
                widget.setPlaceholderText(f"Enter {param.param_type}...")
            
            if param.description:
                label.setToolTip(param.description)
                widget.setToolTip(param.description)
            
            self.param_widgets[param.name] = (widget, param)
            params_form.addRow(label, widget)
        
        params_group.setLayout(params_form)
        layout.addWidget(params_group)
        
        # Preview SQL button
        preview_btn = QPushButton("🔍 Preview SQL")
        preview_btn.clicked.connect(self.preview_sql)
        layout.addWidget(preview_btn)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def preview_sql(self):
        """Preview the generated SQL with current parameter values"""
        param_values = self.get_parameter_values()
        if param_values is None:
            return
        
        sql, error = self.dataset.execute_script(param_values)
        
        if error:
            QMessageBox.critical(self, "Error", f"Failed to generate SQL:\n{error}")
            return
        
        # Show SQL in a dialog
        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle("SQL Preview")
        preview_dialog.setMinimumWidth(600)
        preview_dialog.setMinimumHeight(400)
        
        layout = QVBoxLayout(preview_dialog)
        
        sql_edit = QTextEdit()
        sql_edit.setPlainText(sql)
        sql_edit.setReadOnly(True)
        sql_edit.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11pt;
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                padding: 8px;
            }
        """)
        layout.addWidget(sql_edit)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(preview_dialog.accept)
        layout.addWidget(close_btn)
        
        preview_dialog.exec()
    
    def get_parameter_values(self) -> Optional[Dict[str, Any]]:
        """Get the parameter values from the form.
        
        Returns None if validation fails.
        """
        values = {}
        
        for param_name, (widget, param) in self.param_widgets.items():
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QTextEdit):
                text = widget.toPlainText().strip()
                if text:
                    value = [line.strip() for line in text.split('\n') if line.strip()]
                else:
                    value = None
            else:  # QLineEdit
                text = widget.text().strip()
                if text:
                    if param.param_type == "number":
                        try:
                            value = int(text) if '.' not in text else float(text)
                        except ValueError:
                            QMessageBox.warning(self, "Invalid Input",
                                              f"'{param_name}' must be a number")
                            return None
                    else:
                        value = text
                else:
                    value = None
            
            # Check required
            if param.required and value is None:
                QMessageBox.warning(self, "Required Parameter",
                                  f"Parameter '{param_name}' is required")
                return None
            
            values[param_name] = value
        
        return values


class DataSetScreen(QWidget):
    """Data Set screen for dynamic SQL building with Python scripts"""
    
    # Signal emitted when a query should be executed
    execute_query_signal = pyqtSignal(str, str)  # (sql, name)
    
    def __init__(self):
        super().__init__()
        
        self.current_dataset: Optional[DataSet] = None
        self.datasets_dir = Path.home() / '.suiteview' / 'datasets'
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory dataset storage: {dataset_name: {'dataframe': df, 'executed_time': datetime, 'memory_bytes': int}}
        self.loaded_datasets: Dict[str, Dict[str, Any]] = {}
        
        # Memory tracking (8GB max for laptops)
        self.max_memory_bytes = 8 * 1024 * 1024 * 1024  # 8 GB
        self.memory_footer_label = None  # Will be created in UI
        
        # Initialize repositories and discovery
        self.saved_table_repo = SavedTableRepository()
        self.conn_repo = ConnectionRepository()
        self.schema_discovery = SchemaDiscovery()
        self.metadata_cache_repo = get_metadata_cache_repository()
        self.query_executor = QueryExecutor()
        
        # Track current state
        self.current_connection_id = None
        self.current_table_name = None
        self.current_schema_name = None
        
        self.init_ui()
        self.load_datasets_list()
        self.load_data_sources()
    
    def init_ui(self):
        """Initialize the user interface with 3-panel layout like Data Package screen"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create horizontal splitter for panels (like Data Package screen)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Panel 1 - Saved Data Sets (left side list)
        panel1 = self._create_datasets_panel()
        panel1.setMinimumWidth(150)
        splitter.addWidget(panel1)

        # Panel 2 - Data Source (cascading dropdown + tables)
        panel2 = self._create_data_source_panel()
        panel2.setMinimumWidth(150)
        splitter.addWidget(panel2)

        # Panel 3 - Fields
        panel3 = self._create_fields_panel()
        panel3.setMinimumWidth(150)
        splitter.addWidget(panel3)

        # Panel 4 - Content area with dataset name + tabs
        panel4 = self._create_content_panel()
        panel4.setMinimumWidth(400)
        splitter.addWidget(panel4)

        # Set initial sizes
        splitter.setSizes([180, 180, 180, 700])

        layout.addWidget(splitter)

    def _create_datasets_panel(self) -> QWidget:
        """Create left panel with saved data sets list"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header - styled like Data Package screen
        header = QPushButton("SAVED DATA SETS")
        header.setObjectName("section_header")
        header.setEnabled(False)  # Just a label, not clickable
        panel_layout.addWidget(header)
        
        # New button row
        new_btn_container = QWidget()
        new_btn_layout = QHBoxLayout(new_btn_container)
        new_btn_layout.setContentsMargins(4, 4, 4, 4)
        new_btn_layout.setSpacing(0)
        
        new_btn = QPushButton("+ New")
        new_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFD700;
                color: #0A1E5E;
                padding: 4px 12px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 11px;
                border: none;
            }
            QPushButton:hover {
                background-color: #FFC107;
            }
        """)
        new_btn.clicked.connect(self.new_dataset)
        new_btn_layout.addWidget(new_btn)
        new_btn_layout.addStretch()
        panel_layout.addWidget(new_btn_container)

        # Search box - compact
        self.datasets_search = QLineEdit()
        self.datasets_search.setPlaceholderText("Search datasets...")
        self.datasets_search.setStyleSheet("padding: 3px 6px; margin: 2px 4px; font-size: 11px;")
        self.datasets_search.textChanged.connect(self._filter_datasets)
        panel_layout.addWidget(self.datasets_search)

        # Separator
        from PyQt6.QtWidgets import QFrame
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #B0C8E8; max-height: 1px;")
        panel_layout.addWidget(separator)

        # Datasets list
        self.datasets_list = QListWidget()
        self.datasets_list.setObjectName("sidebar_tree")
        self.datasets_list.currentItemChanged.connect(self.on_dataset_selected)
        self.datasets_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.datasets_list.customContextMenuRequested.connect(self.show_dataset_context_menu)
        panel_layout.addWidget(self.datasets_list)
        
        # Memory footer
        self.memory_footer_label = QLabel("Memory: Calculating...")
        self.memory_footer_label.setStyleSheet("""
            QLabel {
                background-color: #D8E8FF;
                color: #0A1E5E;
                padding: 4px 6px;
                font-size: 10px;
                font-weight: bold;
                border-top: 1px solid #B0C8E8;
            }
        """)
        self.memory_footer_label.setWordWrap(True)
        panel_layout.addWidget(self.memory_footer_label)
        
        # Update memory display initially
        self.update_memory_display()

        return panel

    def _create_data_source_panel(self) -> QWidget:
        """Create panel with cascading data source selection and tables"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header
        header = QPushButton("DATA SOURCE")
        header.setObjectName("section_header")
        header.setEnabled(False)
        panel_layout.addWidget(header)

        # Compact style for combos
        compact_combo_style = """
            QComboBox {
                padding: 2px 4px;
                min-height: 18px;
                font-size: 11px;
            }
            QLabel {
                font-size: 11px;
            }
        """

        # Cascading dropdowns container - compact
        dropdown_container = QWidget()
        dropdown_layout = QVBoxLayout(dropdown_container)
        dropdown_layout.setContentsMargins(4, 4, 4, 4)
        dropdown_layout.setSpacing(2)

        # Type dropdown (horizontal layout)
        type_row = QHBoxLayout()
        type_row.setSpacing(4)
        type_label = QLabel("Type:")
        type_label.setFixedWidth(35)
        type_label.setStyleSheet("font-size: 11px;")
        self.type_combo = QComboBox()
        self.type_combo.setStyleSheet(compact_combo_style)
        type_row.addWidget(type_label)
        type_row.addWidget(self.type_combo)
        dropdown_layout.addLayout(type_row)

        # Connection dropdown (horizontal layout)
        conn_row = QHBoxLayout()
        conn_row.setSpacing(4)
        conn_label = QLabel("Conn:")
        conn_label.setFixedWidth(35)
        conn_label.setStyleSheet("font-size: 11px;")
        self.connection_combo = QComboBox()
        self.connection_combo.setStyleSheet(compact_combo_style)
        conn_row.addWidget(conn_label)
        conn_row.addWidget(self.connection_combo)
        dropdown_layout.addLayout(conn_row)

        panel_layout.addWidget(dropdown_container)

        # Separator line
        from PyQt6.QtWidgets import QFrame
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setStyleSheet("background-color: #B0C8E8; max-height: 1px;")
        panel_layout.addWidget(separator1)

        # Search box - compact
        self.table_search = QLineEdit()
        self.table_search.setPlaceholderText("Search tables...")
        self.table_search.setStyleSheet("padding: 3px 6px; margin: 2px 4px; font-size: 11px;")
        panel_layout.addWidget(self.table_search)

        # Another separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setStyleSheet("background-color: #B0C8E8; max-height: 1px;")
        panel_layout.addWidget(separator2)

        # Tables list
        self.tables_list = QListWidget()
        self.tables_list.setStyleSheet("""
            QListWidget {
                background-color: #E8F0FF;
                border: none;
                font-size: 11px;
                outline: 0;
            }
            QListWidget::item {
                padding: 2px 4px;
                border: none;
                background-color: transparent;
            }
            QListWidget::item:hover {
                background-color: #D8E8FF;
            }
            QListWidget::item:selected {
                background-color: #2563EB;
                color: #FFD700;
            }
        """)
        panel_layout.addWidget(self.tables_list)

        return panel

    def _create_fields_panel(self) -> QWidget:
        """Create fields panel"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header
        header = QPushButton("FIELDS")
        header.setObjectName("section_header")
        header.setEnabled(False)
        panel_layout.addWidget(header)

        # Separator
        from PyQt6.QtWidgets import QFrame
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #B0C8E8; max-height: 1px;")
        panel_layout.addWidget(separator)

        # Search box - compact
        self.field_search = QLineEdit()
        self.field_search.setPlaceholderText("Search fields...")
        self.field_search.setStyleSheet("padding: 3px 6px; margin: 2px 4px; font-size: 11px;")
        panel_layout.addWidget(self.field_search)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setStyleSheet("background-color: #B0C8E8; max-height: 1px;")
        panel_layout.addWidget(separator2)

        # Fields list
        self.fields_list = QListWidget()
        self.fields_list.setStyleSheet("""
            QListWidget {
                background-color: #E8F0FF;
                border: none;
                font-size: 11px;
                outline: 0;
            }
            QListWidget::item {
                padding: 2px 4px;
                border: none;
                background-color: transparent;
            }
            QListWidget::item:hover {
                background-color: #D8E8FF;
            }
            QListWidget::item:selected {
                background-color: #2563EB;
                color: #FFD700;
            }
        """)
        panel_layout.addWidget(self.fields_list)

        return panel

    def _create_content_panel(self) -> QWidget:
        """Create content panel with dataset name header and tabs"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header with dataset name, timer, run, and save buttons
        header_container = QWidget()
        header_container.setStyleSheet("""
            QWidget {
                background-color: white;
                border-bottom: 2px solid #0A1E5E;
            }
        """)
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(2, 2, 2, 2)
        header_layout.setSpacing(2)
        
        # Dataset name (left side - clickable to edit)
        self.dataset_name_label = QLineEdit("New Data Set")
        self.dataset_name_label.setReadOnly(True)
        self.dataset_name_label.setFrame(False)
        self.dataset_name_label.setMinimumHeight(40)  # Ensure height accommodates large font
        self.dataset_name_label.setTextMargins(0, 0, 0, 0)
        self.dataset_name_label.setContentsMargins(0, 0, 0, 0)
        self.dataset_name_label.setStyleSheet("""
            QLineEdit {
                color: #0A1E5E;
                background: transparent;
                border: none;
                font-size: 20pt;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
            }
            QLineEdit:hover {
                color: #0056b3;
            }
        """)
        self.dataset_name_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dataset_name_label.mousePressEvent = lambda event: self.edit_dataset_name()
        header_layout.addWidget(self.dataset_name_label, 0)  # Give it stretch factor of 0 but let it expand naturally
        
        header_layout.addStretch()
        
        # Timer label (middle)
        self.timer_label = QLineEdit("")
        self.timer_label.setReadOnly(True)
        self.timer_label.setMinimumWidth(300)
        timer_font = QFont()
        timer_font.setPointSize(9)
        self.timer_label.setFont(timer_font)
        self.timer_label.setFrame(False)
        self.timer_label.setStyleSheet("""
            QLineEdit {
                color: #888888;
                background: transparent;
                border: none;
            }
        """)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.timer_label)
        
        header_layout.addStretch()
        
        # 2x2 Button Grid Layout
        button_grid = QVBoxLayout()
        button_grid.setSpacing(4)
        
        # Top row: Run | Save
        top_row = QHBoxLayout()
        top_row.setSpacing(4)
        
        # Run button (yellow background, blue text)
        self.run_btn = QPushButton("▶ Run")
        self.run_btn.clicked.connect(self.run_sql_query)
        self.run_btn.setFixedSize(65, 26)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFD700;
                color: #0A1E5E;
                font-weight: bold;
                font-size: 10px;
                border: none;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #FFC107;
            }
            QPushButton:pressed {
                background-color: #FFB300;
            }
        """)
        top_row.addWidget(self.run_btn)
        
        # Save button
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.clicked.connect(self.save_dataset)
        self.save_btn.setFixedSize(65, 26)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0078d4;
                font-weight: bold;
                font-size: 10px;
                border: 2px solid #0078d4;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
                border-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #bbdefb;
            }
        """)
        top_row.addWidget(self.save_btn)
        
        button_grid.addLayout(top_row)
        
        # Bottom row: (blank) | Reload
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(4)
        
        # Blank space on left
        blank_spacer = QWidget()
        blank_spacer.setFixedSize(65, 26)
        bottom_row.addWidget(blank_spacer)
        
        # Reload button
        self.reload_btn = QPushButton("↻ Reload")
        self.reload_btn.clicked.connect(self.reload_dataset)
        self.reload_btn.setFixedSize(65, 26)
        self.reload_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #28a745;
                font-weight: bold;
                font-size: 10px;
                border: 2px solid #28a745;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #d4edda;
                border-color: #1e7e34;
            }
            QPushButton:pressed {
                background-color: #c3e6cb;
            }
        """)
        bottom_row.addWidget(self.reload_btn)
        
        button_grid.addLayout(bottom_row)
        
        header_layout.addLayout(button_grid)
        
        # Initialize timer
        from PyQt6.QtCore import QTimer, QTime
        self.query_timer = QTimer()
        self.query_timer.timeout.connect(self.update_timer)
        self.query_start_time = None
        
        panel_layout.addWidget(header_container)

        # Tab widget for Script / Signatures / Calling / SQL
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #B0C8E8;
                background-color: #E8F0FF;
            }
            QTabBar {
                background-color: #E8F0FF;
            }
            QTabBar::tab {
                padding: 6px 14px;
                margin-right: 2px;
                background-color: #D8E8FF;
                color: #0A1E5E;
                font-weight: 600;
                font-size: 11px;
                border: 1px solid #B0C8E8;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #6BA3E8;
                border-bottom: 2px solid #FFD700;
                color: #0A1E5E;
            }
            QTabBar::tab:!selected {
                background-color: #D8E8FF;
                color: #5a6c7d;
            }
            QTabBar::tab:hover {
                background-color: #C8DFFF;
            }
        """)
        
        # Create tab content using the existing _create_script_tab method
        # which creates all tabs internally
        self._create_tabs_content()
        
        panel_layout.addWidget(self.tab_widget)
        
        return panel

    def _create_tabs_content(self):
        """Create all tab content (Script Builder, Signatures, Calling, SQL)"""
        script_tab = QWidget()
        script_layout = QVBoxLayout(script_tab)
        script_layout.setContentsMargins(5, 5, 5, 5)
        
        script_toolbar = QHBoxLayout()
        script_toolbar.setSpacing(6)
        
        validate_btn = QPushButton("✓ Validate")
        validate_btn.clicked.connect(self.validate_script)
        validate_btn.setFixedWidth(90)
        validate_btn.setFixedHeight(26)
        validate_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0078d4;
                padding: 2px 6px;
                font-size: 9pt;
                border: 1px solid #0078d4;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
            }
        """)
        script_toolbar.addWidget(validate_btn)
        
        # Template button
        template_btn = QPushButton("📋 Template")
        template_btn.clicked.connect(self.load_script_template)
        template_btn.setFixedWidth(95)
        template_btn.setFixedHeight(26)
        template_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #28a745;
                padding: 2px 6px;
                font-size: 9pt;
                border: 1px solid #28a745;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #d4edda;
            }
        """)
        script_toolbar.addWidget(template_btn)
        
        # Undo/Redo buttons (will be created after text editor is initialized)
        # Placeholder for now
        self._script_undo_placeholder = script_toolbar
        
        # Text size controls
        size_label = QLabel("Size:")
        size_label.setStyleSheet("color: #333; font-size: 9pt;")
        script_toolbar.addWidget(size_label)
        
        self.text_size_spinner = QSpinBox()
        self.text_size_spinner.setRange(8, 20)
        self.text_size_spinner.setValue(11)
        self.text_size_spinner.setSuffix(" pt")
        self.text_size_spinner.setFixedWidth(70)
        self.text_size_spinner.setFixedHeight(26)
        self.text_size_spinner.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        self.text_size_spinner.setStyleSheet("""
            QSpinBox {
                background-color: white;
                color: #333;
                border: 1px solid #0078d4;
                border-radius: 3px;
                padding: 2px 4px;
                font-size: 9pt;
            }
            QSpinBox::up-button {
                width: 16px;
                background-color: #e3f2fd;
                border-left: 1px solid #0078d4;
                border-top-right-radius: 2px;
            }
            QSpinBox::up-button:hover {
                background-color: #0078d4;
            }
            QSpinBox::down-button {
                width: 16px;
                background-color: #e3f2fd;
                border-left: 1px solid #0078d4;
                border-bottom-right-radius: 2px;
            }
            QSpinBox::down-button:hover {
                background-color: #0078d4;
            }
        """)
        self.text_size_spinner.valueChanged.connect(self.change_text_size)
        script_toolbar.addWidget(self.text_size_spinner)
        
        script_toolbar.addStretch()
        
        script_layout.addLayout(script_toolbar)
        
        # Script editor
        self.script_editor = QTextEdit()
        self.script_editor.setFont(QFont("Consolas", 11))
        self.script_editor.setPlaceholderText("Write your build_query() function here...")
        self.script_editor.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 2px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        
        # Add syntax highlighter
        self.highlighter = PythonSyntaxHighlighter(self.script_editor.document())
        
        # Create undo/redo manager and add buttons to toolbar
        self.script_undo_manager = UndoRedoManager(self.script_editor)
        undo_btn, redo_btn = self.script_undo_manager.create_toolbar_buttons()
        self._script_undo_placeholder.addWidget(undo_btn)
        self._script_undo_placeholder.addWidget(redo_btn)
        
        script_layout.addWidget(self.script_editor)
        
        self.tab_widget.addTab(script_tab, "Script Builder")
        
        # Signatures Tab (two-column: Parameters | Output Fields)
        signatures_tab = QWidget()
        signatures_layout = QVBoxLayout(signatures_tab)
        signatures_layout.setContentsMargins(5, 5, 5, 5)
        signatures_layout.setSpacing(5)
        
        # Toolbar with generate button
        sig_toolbar = QHBoxLayout()
        sig_toolbar.setSpacing(6)
        
        generate_sig_btn = QPushButton("🔄 Generate Signatures")
        generate_sig_btn.clicked.connect(self.generate_signatures)
        generate_sig_btn.setFixedHeight(28)
        generate_sig_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0078d4;
                padding: 4px 12px;
                font-weight: bold;
                border: 2px solid #0078d4;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
            }
        """)
        sig_toolbar.addWidget(generate_sig_btn)
        sig_toolbar.addStretch()
        
        signatures_layout.addLayout(sig_toolbar)
        
        # Two-column layout: Parameters | Output Fields
        columns_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left column: Parameters
        params_widget = QWidget()
        params_layout = QVBoxLayout(params_widget)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(3)
        
        params_header = QLabel("PARAMETERS")
        params_header.setStyleSheet("""
            QLabel {
                background-color: #0A1E5E;
                color: white;
                padding: 4px;
                font-weight: bold;
                font-size: 10pt;
            }
        """)
        params_layout.addWidget(params_header)
        
        self.params_table = QTableWidget()
        self.params_table.setColumnCount(2)
        self.params_table.setHorizontalHeaderLabels(["Name", "DataType"])
        self.params_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.params_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.params_table.verticalHeader().setVisible(False)
        self.params_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.params_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                gridline-color: #d0d0d0;
                border: 1px solid #d0d0d0;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
                font-size: 9pt;
            }
            QTableWidget::item {
                padding: 2px 4px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: #000;
            }
            QTableWidget::item:focus {
                background-color: white;
                border: none;
                outline: none;
            }
        """)
        params_layout.addWidget(self.params_table)
        
        columns_splitter.addWidget(params_widget)
        
        # Right column: Output Fields
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(3)
        
        output_header = QLabel("OUTPUT FIELDS")
        output_header.setStyleSheet("""
            QLabel {
                background-color: #0A1E5E;
                color: white;
                padding: 4px;
                font-weight: bold;
                font-size: 10pt;
            }
        """)
        output_layout.addWidget(output_header)
        
        self.display_table = QTableWidget()
        self.display_table.setColumnCount(2)
        self.display_table.setHorizontalHeaderLabels(["Name", "DataType"])
        self.display_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.display_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.display_table.verticalHeader().setVisible(False)
        self.display_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.display_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                gridline-color: #d0d0d0;
                border: 1px solid #d0d0d0;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
                font-size: 9pt;
            }
            QTableWidget::item {
                padding: 2px 4px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: #000;
            }
            QTableWidget::item:focus {
                background-color: white;
                border: none;
                outline: none;
            }
        """)
        output_layout.addWidget(self.display_table)
        
        columns_splitter.addWidget(output_widget)
        
        # Set equal sizes for both columns
        columns_splitter.setSizes([400, 400])
        
        signatures_layout.addWidget(columns_splitter)
        
        self.tab_widget.addTab(signatures_tab, "Signatures")
        
        # Calling Tab - code editor to call the build_query function
        calling_tab = QWidget()
        calling_layout = QVBoxLayout(calling_tab)
        calling_layout.setContentsMargins(5, 5, 5, 5)
        
        calling_toolbar = QHBoxLayout()
        calling_toolbar.setSpacing(6)
        
        run_calling_btn = QPushButton("▶️ Run")
        run_calling_btn.clicked.connect(self.run_calling_code)
        run_calling_btn.setFixedWidth(80)
        run_calling_btn.setFixedHeight(26)
        run_calling_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 2px 6px;
                font-size: 9pt;
                font-weight: bold;
                border: 2px solid #28a745;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        calling_toolbar.addWidget(run_calling_btn)
        
        # Populate button
        populate_btn = QPushButton("📝 Populate")
        populate_btn.clicked.connect(self.populate_calling_template)
        populate_btn.setFixedWidth(95)
        populate_btn.setFixedHeight(26)
        populate_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #17a2b8;
                padding: 2px 6px;
                font-size: 9pt;
                font-weight: bold;
                border: 1px solid #17a2b8;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #d1ecf1;
            }
        """)
        calling_toolbar.addWidget(populate_btn)
        
        # Placeholder for undo/redo buttons
        self._calling_undo_placeholder = calling_toolbar
        
        calling_toolbar.addStretch()
        
        calling_layout.addLayout(calling_toolbar)
        
        # Calling code editor
        self.calling_editor = QTextEdit()
        self.calling_editor.setFont(QFont("Consolas", 11))
        self.calling_editor.setPlaceholderText("Write code to call build_query() with parameters...")
        self.calling_editor.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 2px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        
        # Add syntax highlighter for calling editor
        self.calling_highlighter = PythonSyntaxHighlighter(self.calling_editor.document())
        
        # Create undo/redo manager and add buttons to toolbar
        self.calling_undo_manager = UndoRedoManager(self.calling_editor)
        undo_btn, redo_btn = self.calling_undo_manager.create_toolbar_buttons()
        self._calling_undo_placeholder.addWidget(undo_btn)
        self._calling_undo_placeholder.addWidget(redo_btn)
        
        calling_layout.addWidget(self.calling_editor)
        
        # Help text
        calling_help_text = QLabel(
            "💡 Tip: Write Python code to call build_query() with your parameter values.\n"
            "The function and SQL will be generated when you click Run."
        )
        calling_help_text.setStyleSheet("color: #888; font-size: 10pt; font-style: italic; padding: 5px;")
        calling_help_text.setWordWrap(True)
        calling_layout.addWidget(calling_help_text)
        
        self.tab_widget.addTab(calling_tab, "Calling")
        
        # SQL Tab - shows generated SQL
        sql_tab = QWidget()
        sql_layout = QVBoxLayout(sql_tab)
        sql_layout.setContentsMargins(5, 5, 5, 5)
        
        sql_toolbar = QHBoxLayout()
        sql_toolbar.setSpacing(6)
        
        copy_sql_btn = QPushButton("📋 Copy SQL")
        copy_sql_btn.clicked.connect(self.copy_sql_to_clipboard)
        copy_sql_btn.setFixedHeight(26)
        copy_sql_btn.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
        """)
        sql_toolbar.addWidget(copy_sql_btn)
        
        format_sql_btn = QPushButton("✨ Format")
        format_sql_btn.clicked.connect(self.format_sql_display)
        format_sql_btn.setFixedHeight(26)
        format_sql_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                padding: 4px 12px;
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        sql_toolbar.addWidget(format_sql_btn)
        
        sql_toolbar.addStretch()
        
        sql_layout.addLayout(sql_toolbar)
        
        self.sql_display = QTextEdit()
        self.sql_display.setReadOnly(True)
        self.sql_display.setFont(QFont("Consolas", 10))
        self.sql_display.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        
        # Add SQL syntax highlighter
        self.sql_highlighter = SQLHighlighter(self.sql_display.document())
        
        sql_layout.addWidget(self.sql_display)
        
        self.tab_widget.addTab(sql_tab, "SQL")
    
    def edit_dataset_name(self):
        """Edit the current dataset name"""
        if not self.current_dataset:
            return
        
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "Edit Dataset Name", 
            "Dataset name:",
            text=self.current_dataset.name
        )
        
        if ok and new_name.strip():
            old_name = self.current_dataset.name
            self.current_dataset.name = new_name.strip()
            self.dataset_name_label.setText(self.current_dataset.name)
            
            # If this is a saved dataset, we may need to rename the file
            old_filename = self.datasets_dir / f"{old_name}.json"
            if old_filename.exists():
                # Save with new name and delete old file
                self.save_dataset()
                try:
                    old_filename.unlink()
                    logger.info(f"Renamed dataset from '{old_name}' to '{new_name}'")
                except Exception as e:
                    logger.error(f"Could not delete old file {old_filename}: {e}")
                
                self.load_datasets_list()
    
    def new_dataset(self):
        """Create a new Data Set"""
        if self.current_dataset and self.is_modified():
            reply = QMessageBox.question(
                self, "Save Changes?",
                "Current Data Set has unsaved changes. Save before creating new?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.save_dataset()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
        
        self.current_dataset = DataSet(name="New Data Set")
        self.load_dataset_to_ui()
        
        # Auto-populate Script Builder with template
        script_template = '''def build_query(policy_nums=None, state=None, as_of_date=None):
    """
    Build a dynamic SQL query based on parameters.
    
    Parameters:
    - policy_nums: List of policy numbers (optional)
    - state: State code (optional)
    - as_of_date: Effective date filter (optional)
    
    Returns:
    - SQL query string
    """
    sql = "SELECT PolicyNumber, State, EffectiveDate, Premium FROM Policies WHERE 1=1"
    
    if policy_nums:
        policy_list = "','".join(str(p) for p in policy_nums)
        sql += f" AND PolicyNumber IN ('{policy_list}')"
    
    if state:
        sql += f" AND State = '{state}'"
    
    if as_of_date:
        sql += f" AND EffectiveDate <= '{as_of_date}'"
    
    return sql
'''
        # Use text cursor to set initial content (preserves undo stack)
        cursor = self.script_editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        cursor.insertText(script_template)
        
        # Auto-populate Calling tab with template
        calling_template = '''# Call the build_query function with parameter values
# Example:

sql = build_query(
    policy_nums=['12345', '67890'],
    state='CA',
    as_of_date='2024-12-31'
)
'''
        cursor = self.calling_editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        cursor.insertText(calling_template)
    
    def save_dataset(self):
        """Save the current Data Set"""
        if not self.current_dataset:
            QMessageBox.warning(self, "No Data Set", "No Data Set to save")
            return
        
        # Update from UI
        self.update_dataset_from_ui()
        
        # Validate
        error = self.current_dataset.validate()
        if error:
            QMessageBox.critical(self, "Validation Error", error)
            return
        
        # Save to file
        filename = self.datasets_dir / f"{self.current_dataset.name}.json"
        
        try:
            with open(filename, 'w') as f:
                json.dump(self.current_dataset.to_dict(), f, indent=2)
            
            logger.info(f"Saved Data Set: {filename}")
            QMessageBox.information(self, "Saved", f"Data Set '{self.current_dataset.name}' saved successfully")
            
            self.load_datasets_list()
            
        except Exception as e:
            logger.error(f"Error saving Data Set: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save Data Set:\n{e}")
    
    def show_dataset_context_menu(self, position):
        """Show context menu for dataset list"""
        item = self.datasets_list.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        delete_action = menu.addAction("Delete Dataset")
        delete_action.triggered.connect(self.delete_dataset)
        menu.exec(self.datasets_list.mapToGlobal(position))
    
    def delete_dataset(self):
        """Delete the selected Data Set"""
        current_item = self.datasets_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a Data Set to delete")
            return
        
        # Get actual dataset name from UserRole
        dataset_name = current_item.data(Qt.ItemDataRole.UserRole)
        if not dataset_name:
            dataset_name = current_item.text().replace("🟢 ", "")  # Fallback
        
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete '{dataset_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        filename = self.datasets_dir / f"{dataset_name}.json"
        
        try:
            filename.unlink()
            logger.info(f"Deleted Data Set: {filename}")
            
            # Also remove from memory if loaded
            if dataset_name in self.loaded_datasets:
                del self.loaded_datasets[dataset_name]
                self.update_memory_display()
            
            if self.current_dataset and self.current_dataset.name == dataset_name:
                self.current_dataset = None
                self.load_dataset_to_ui()
            
            self.load_datasets_list()
            
        except Exception as e:
            logger.error(f"Error deleting Data Set: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete Data Set:\n{e}")
    
    def load_datasets_list(self):
        """Load the list of saved Data Sets with green indicators for loaded datasets"""
        self.datasets_list.clear()
        
        for file in sorted(self.datasets_dir.glob("*.json")):
            dataset_name = file.stem
            
            # Add green indicator if dataset is loaded in memory
            if self.is_dataset_loaded(dataset_name):
                display_name = f"🟢 {dataset_name}"
            else:
                display_name = dataset_name
            
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, dataset_name)  # Store actual name
            self.datasets_list.addItem(item)
    
    def _filter_datasets(self, text: str):
        """Filter datasets list based on search text"""
        search_text = text.lower()
        for i in range(self.datasets_list.count()):
            item = self.datasets_list.item(i)
            item.setHidden(search_text not in item.text().lower())
    
    def on_dataset_selected(self, current, previous):
        """Handle Data Set selection from list"""
        if not current:
            return
        
        if self.current_dataset and self.is_modified():
            reply = QMessageBox.question(
                self, "Save Changes?",
                "Current Data Set has unsaved changes. Save?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.save_dataset()
            elif reply == QMessageBox.StandardButton.Cancel:
                # Revert selection
                self.datasets_list.blockSignals(True)
                self.datasets_list.setCurrentItem(previous)
                self.datasets_list.blockSignals(False)
                return
        
        # Get actual dataset name from UserRole (since display text may have green indicator)
        dataset_name = current.data(Qt.ItemDataRole.UserRole)
        if not dataset_name:
            dataset_name = current.text().replace("🟢 ", "")  # Fallback
        
        self.load_dataset_from_file(dataset_name)
    
    def load_dataset_from_file(self, name: str):
        """Load a Data Set from file"""
        filename = self.datasets_dir / f"{name}.json"
        
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            
            self.current_dataset = DataSet.from_dict(data)
            self.load_dataset_to_ui()
            
            logger.info(f"Loaded Data Set: {name}")
            
        except Exception as e:
            logger.error(f"Error loading Data Set: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load Data Set:\n{e}")
    
    def load_dataset_to_ui(self):
        """Load current Data Set into UI"""
        if not self.current_dataset:
            self.script_editor.clear()
            self.calling_editor.clear()
            self.params_table.setRowCount(0)
            self.display_table.setRowCount(0)
            self.dataset_name_label.setText("")
            return
        
        self.dataset_name_label.setText(self.current_dataset.name)
        
        # Restore data source type and connection
        if self.current_dataset.connection_type:
            index = self.type_combo.findText(self.current_dataset.connection_type)
            if index >= 0:
                self.type_combo.setCurrentIndex(index)
        
        if self.current_dataset.connection_name:
            index = self.connection_combo.findText(self.current_dataset.connection_name)
            if index >= 0:
                self.connection_combo.setCurrentIndex(index)
        
        # Use text cursor to load script (preserves undo stack)
        cursor = self.script_editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        cursor.insertText(self.current_dataset.script_code)
        
        # Use text cursor to load calling code (preserves undo stack)
        calling_cursor = self.calling_editor.textCursor()
        calling_cursor.select(calling_cursor.SelectionType.Document)
        calling_cursor.insertText(self.current_dataset.calling_code or '')
        
        # Parameters table (2 columns: Name, DataType)
        self.params_table.setRowCount(len(self.current_dataset.parameters))
        for i, param in enumerate(self.current_dataset.parameters):
            name_item = QTableWidgetItem(param.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.params_table.setItem(i, 0, name_item)
            
            type_item = QTableWidgetItem(param.param_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.params_table.setItem(i, 1, type_item)
        
        # Display fields table (2 columns: Name, DataType)
        self.display_table.setRowCount(len(self.current_dataset.display_fields))
        for i, field in enumerate(self.current_dataset.display_fields):
            name_item = QTableWidgetItem(field.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.display_table.setItem(i, 0, name_item)
            
            type_item = QTableWidgetItem(field.data_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.display_table.setItem(i, 1, type_item)
    
    def update_dataset_from_ui(self):
        """Update current Data Set from UI values"""
        if not self.current_dataset:
            return
        
        # Name is managed separately (from dataset_name_label or prompts), not edited inline
        self.current_dataset.script_code = self.script_editor.toPlainText()
        self.current_dataset.calling_code = self.calling_editor.toPlainText()
        
        # Save data source type and connection
        self.current_dataset.connection_type = self.type_combo.currentText()
        self.current_dataset.connection_name = self.connection_combo.currentText()
        
        # Display fields from table (2 columns: Name, DataType)
        fields = []
        for i in range(self.display_table.rowCount()):
            name_item = self.display_table.item(i, 0)
            type_item = self.display_table.item(i, 1)
            
            if name_item and name_item.text().strip():
                fields.append(DataSetField(
                    name=name_item.text().strip(),
                    data_type=type_item.text().strip() if type_item else "text",
                    description=""
                ))
        
        self.current_dataset.display_fields = fields
    
    def is_modified(self) -> bool:
        """Check if current Data Set has unsaved changes"""
        if not self.current_dataset:
            return False
        
        # Simple check: compare UI script with saved dataset script
        return self.script_editor.toPlainText() != self.current_dataset.script_code
    
    def validate_script(self):
        """Validate the Python script (just check syntax)"""
        if not self.current_dataset:
            self.current_dataset = DataSet(name="New Data Set")
        
        self.current_dataset.script_code = self.script_editor.toPlainText()
        
        params, error = self.current_dataset.parse_script()
        
        if error:
            QMessageBox.critical(self, "Script Error", error)
            return
        
        QMessageBox.information(self, "Valid Script", 
                              f"Script is valid!\nFound {len(params)} parameter(s)")
    
    def generate_signatures(self):
        """Generate both parameters and display fields signatures"""
        if not self.current_dataset:
            self.current_dataset = DataSet(name="New Data Set")
        
        self.current_dataset.script_code = self.script_editor.toPlainText()
        
        # Parse parameters
        params, error = self.current_dataset.parse_script()
        
        if error:
            QMessageBox.critical(self, "Script Error", error)
            return
        
        # Update parameters
        self.current_dataset.parameters = params
        
        # Refresh parameters table (2 columns: Name, DataType)
        self.params_table.setRowCount(len(params))
        for i, param in enumerate(params):
            name_item = QTableWidgetItem(param.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.params_table.setItem(i, 0, name_item)
            
            type_item = QTableWidgetItem(param.param_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.params_table.setItem(i, 1, type_item)
        
        # Auto-detect display fields
        self.auto_detect_fields()
        
        QMessageBox.information(self, "Signatures Generated", 
                              f"Generated signatures:\n• {len(params)} parameter(s)\n• {len(self.current_dataset.display_fields)} display field(s)")
        
        # Switch to Signatures tab to show results
        self.tab_widget.setCurrentIndex(1)
    
    def load_script_template(self):
        """Load a template Python script"""
        template = '''def build_query(policy_nums=None, state=None, as_of_date=None):
    """
    Build dynamic SQL based on parameters
    
    Args:
        policy_nums: Policy number(s) - single value or list
        state: State code (optional)
        as_of_date: As-of date for filtering (optional)
    
    Returns:
        SQL string
    """
    sql = "SELECT PolicyNumber, State, EffectiveDate, Premium FROM Policies WHERE 1=1"
    
    # Handle policy numbers
    if policy_nums is not None:
        if isinstance(policy_nums, list):
            # Multiple policy numbers
            nums = ",".join(f"'{n}'" for n in policy_nums)
            sql += f" AND PolicyNumber IN ({nums})"
        else:
            # Single policy number
            sql += f" AND PolicyNumber = '{policy_nums}'"
    
    # Optional state filter
    if state is not None:
        sql += f" AND State = '{state}'"
    
    # Optional date filter
    if as_of_date is not None:
        sql += f" AND EffectiveDate <= '{as_of_date}'"
    
    return sql
'''
        
        # Use text cursor to replace content (preserves undo stack)
        cursor = self.script_editor.textCursor()
        cursor.select(cursor.SelectionType.Document)  # Select all text
        cursor.insertText(template)  # Replace with template (creates undo command)
    
    def auto_detect_fields(self):
        """Auto-detect display fields from generated SQL"""
        if not self.current_dataset:
            return
        
        # Generate SQL with sample/empty parameters
        self.update_dataset_from_ui()
        
        # Create sample parameter values
        sample_params = {}
        for param in self.current_dataset.parameters:
            if param.default_value is not None:
                sample_params[param.name] = param.default_value
            else:
                # Use None for optional params
                sample_params[param.name] = None
        
        sql, error = self.current_dataset.execute_script(sample_params)
        
        if error:
            # Silently fail - not critical
            return
        
        # Extract fields from SQL
        fields = self.current_dataset.extract_fields_from_sql(sql)
        
        if not fields:
            return
        
        # Update display fields
        self.current_dataset.display_fields = fields
        
        # Refresh display table (2 columns: Name, DataType)
        self.display_table.setRowCount(len(fields))
        for i, field in enumerate(fields):
            name_item = QTableWidgetItem(field.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.display_table.setItem(i, 0, name_item)
            
            type_item = QTableWidgetItem(field.data_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.display_table.setItem(i, 1, type_item)
    
    def add_display_field(self):
        """Add a new display field manually"""
        if not self.current_dataset:
            self.current_dataset = DataSet(name="New Data Set")
        
        row = self.display_table.rowCount()
        self.display_table.insertRow(row)
        
        self.display_table.setItem(row, 0, QTableWidgetItem(""))
        
        type_combo = QComboBox()
        type_combo.addItems(["text", "number", "date", "boolean"])
        self.display_table.setCellWidget(row, 1, type_combo)
        
        self.display_table.setItem(row, 2, QTableWidgetItem(""))
        
        # Start editing the name cell
        self.display_table.editItem(self.display_table.item(row, 0))
    
    def remove_display_field(self):
        """Remove the selected display field"""
        current_row = self.display_table.currentRow()
        if current_row >= 0:
            self.display_table.removeRow(current_row)
    
    def format_sql(self, sql):
        """Format SQL for better readability using sqlparse"""
        if not sql:
            return sql
        
        try:
            # Format SQL with sqlparse
            formatted = sqlparse.format(
                sql,
                reindent=True,
                keyword_case='upper',
                indent_width=3
            )
            return formatted
        except Exception as e:
            logger.error(f"Failed to format SQL: {e}")
            return sql
    
    def change_text_size(self, size):
        """Change the script editor font size"""
        font = self.script_editor.font()
        font.setPointSize(size)
        self.script_editor.setFont(font)
    
    def load_calling_template(self):
        """Load a template for calling code"""
        template = '''# Call the build_query function with parameter values
# Example:

sql = build_query(
    policy_nums=['12345', '67890'],
    state='CA',
    as_of_date='2024-12-31'
)
'''
        
        if self.calling_editor.toPlainText().strip():
            reply = QMessageBox.question(
                self, "Replace Code?",
                "This will replace your current calling code. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        self.calling_editor.setPlainText(template)
    
    def populate_calling_template(self):
        """Generate calling code template based on the script's function signature"""
        if not self.current_dataset:
            self.current_dataset = DataSet(name="New Data Set")
        
        # Update script from editor
        self.current_dataset.script_code = self.script_editor.toPlainText()
        
        # Parse the script to get parameters
        params, error = self.current_dataset.parse_script()
        
        if error:
            QMessageBox.warning(self, "Parse Error", 
                              f"Could not parse script to extract parameters:\n{error}\n\nPlease fix the script first.")
            return
        
        if not params:
            QMessageBox.information(self, "No Parameters", 
                                  "The build_query function has no parameters.\n\nTemplate: sql = build_query()")
            template = "# Call the build_query function\n\nsql = build_query()\nprint(sql)\n"
        else:
            # Build calling code with parameter placeholders
            param_lines = []
            for param in params:
                if param.param_type == "list":
                    param_lines.append(f"    {param.name}=['value1', 'value2'],  # List of values")
                elif param.param_type == "bool":
                    param_lines.append(f"    {param.name}=True,  # Boolean")
                elif param.param_type == "number":
                    param_lines.append(f"    {param.name}=123,  # Number")
                else:
                    param_lines.append(f"    {param.name}='value',  # String")
            
            params_str = "\n".join(param_lines)
            template = f"""# Call the build_query function with parameter values

sql = build_query(
{params_str}
)

print(sql)
"""
        
        # Use text cursor to insert template (preserves undo)
        cursor = self.calling_editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        cursor.insertText(template)
    
    def run_calling_code(self):
        """Execute the calling code to generate SQL and populate signatures"""
        if not self.current_dataset:
            QMessageBox.warning(self, "No Data Set", "Please create or load a Data Set first")
            return
        
        # Get the script and calling code
        script_code = self.script_editor.toPlainText()
        calling_code = self.calling_editor.toPlainText()
        
        if not script_code.strip():
            QMessageBox.warning(self, "No Script", "Please write a build_query function in the Script Builder tab")
            return
        
        if not calling_code.strip():
            QMessageBox.warning(self, "No Calling Code", "Please write code to call build_query()")
            return
        
        try:
            # Create execution namespace
            namespace = {}
            
            # Execute the script to define the function
            exec(script_code, namespace)
            
            # Check if build_query exists
            if 'build_query' not in namespace:
                QMessageBox.critical(self, "Error", "Script must define a 'build_query' function")
                return
            
            # Execute the calling code
            exec(calling_code, namespace)
            
            # Get the SQL from the namespace (user should assign it to 'sql' variable)
            if 'sql' not in namespace:
                QMessageBox.warning(self, "No SQL Generated", 
                                  "Calling code must assign the result to a variable named 'sql'\n\nExample:\nsql = build_query(...)")
                return
            
            sql = namespace['sql']
            
            if not isinstance(sql, str):
                QMessageBox.critical(self, "Error", "build_query must return a string (SQL)")
                return
            
            # Format and display SQL in SQL tab
            formatted_sql = self.format_sql(sql)
            self.sql_display.setPlainText(formatted_sql)
            
            # Parse script to populate signatures
            self.current_dataset.script_code = script_code
            params, error = self.current_dataset.parse_script()
            
            if not error:
                self.current_dataset.parameters = params
                
                # Refresh parameters table
                self.params_table.setRowCount(len(params))
                for i, param in enumerate(params):
                    name_item = QTableWidgetItem(param.name)
                    name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.params_table.setItem(i, 0, name_item)
                    
                    type_item = QTableWidgetItem(param.param_type)
                    type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.params_table.setItem(i, 1, type_item)
                
                # Auto-detect display fields from generated SQL
                fields = self.current_dataset.extract_fields_from_sql(sql)
                if fields:
                    self.current_dataset.display_fields = fields
                    
                    self.display_table.setRowCount(len(fields))
                    for i, field in enumerate(fields):
                        name_item = QTableWidgetItem(field.name)
                        name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.display_table.setItem(i, 0, name_item)
                        
                        type_item = QTableWidgetItem(field.data_type)
                        type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        self.display_table.setItem(i, 1, type_item)
            
            # Switch to SQL tab to show results
            self.tab_widget.setCurrentIndex(3)
            
        except Exception as e:
            QMessageBox.critical(self, "Execution Error", f"Error running calling code:\n\n{str(e)}")
    
    def refresh_calling_params(self):
        """No longer needed - kept for compatibility"""
        pass
    
    def generate_sql_from_calling(self):
        """No longer needed - kept for compatibility"""
        pass
    
    def copy_sql_to_clipboard(self):
        """Copy the generated SQL to clipboard"""
        sql = self.sql_display.toPlainText()
        if sql:
            QApplication.clipboard().setText(sql)
        else:
            QMessageBox.warning(self, "No SQL", "Generate SQL first by running the Calling code")
    
    def format_sql_display(self):
        """Format the SQL in the display using sqlparse"""
        try:
            current_sql = self.sql_display.toPlainText()
            if current_sql.strip():
                # Format SQL with sqlparse
                formatted_sql = sqlparse.format(
                    current_sql,
                    reindent=True,
                    keyword_case='upper',
                    indent_width=3,
                    comma_first=False
                )
                self.sql_display.setPlainText(formatted_sql)
        except Exception as e:
            logger.error(f"Failed to format SQL: {e}")
            QMessageBox.warning(self, "Format Error", f"Could not format SQL: {e}")
    
    def update_timer(self):
        """Update the timer label to show elapsed time"""
        if self.query_start_time:
            from PyQt6.QtCore import QTime
            elapsed = self.query_start_time.msecsTo(QTime.currentTime())
            seconds = elapsed // 1000
            minutes = seconds // 60
            secs = seconds % 60
            self.timer_label.setText(f"Running: {minutes}m {secs}s")
    
    def run_sql_query(self):
        """Execute the SQL from the SQL tab using the selected data source connection"""
        if not self.current_dataset:
            QMessageBox.warning(self, "No Dataset", "Please create or load a Data Set first")
            return
        
        # Check memory before running
        if not self.check_memory_before_query():
            return
        
        # First, generate SQL from calling code if available
        calling_code = self.calling_editor.toPlainText().strip()
        if calling_code:
            # Generate SQL from calling code
            self.run_calling_code()
        
        # Now get the SQL to execute
        sql = self.sql_display.toPlainText().strip()
        if not sql:
            QMessageBox.warning(self, "No SQL", "No SQL query to execute. Generate SQL first by writing code in the Calling tab.")
            return
        
        # Get selected connection ID from Data Source panel (stored as currentData)
        connection_id = self.connection_combo.currentData()
        if not connection_id:
            QMessageBox.warning(self, "No Connection", "Please select a data source connection first.")
            return
        
        # Start main timer
        self.query_start_time = QTime.currentTime()
        self.timer_label.setText("Running...")
        self.query_timer.start(100)  # Update every 100ms
        QApplication.processEvents()
        
        try:
            # Execute query
            import time
            start_time = time.time()
            execution_start = datetime.now()
            df = self.query_executor.execute_sql(connection_id, sql)
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Stop timer
            self.query_timer.stop()
            
            # Calculate memory usage
            memory_bytes = self.get_dataframe_memory_bytes(df)
            
            # Store in memory (replace if already exists)
            dataset_name = self.current_dataset.name
            self.loaded_datasets[dataset_name] = {
                'dataframe': df,
                'executed_time': execution_start,
                'memory_bytes': memory_bytes
            }
            
            # Get stats
            record_count = len(df)
            column_count = len(df.columns)
            
            # Show final time with rows x columns
            final_seconds = self.query_start_time.msecsTo(QTime.currentTime()) // 1000
            final_minutes = final_seconds // 60
            final_secs = final_seconds % 60
            self.timer_label.setText(f"Completed: {final_minutes}m {final_secs}s ({record_count:,} rows x {column_count} columns)")
            
            # Create or update Data tab
            self.create_or_update_data_tab(df, execution_start, memory_bytes)
            
            # Update memory display and dataset list (to show green indicator)
            self.update_memory_display()
            self.load_datasets_list()
            
            logger.info(f"Query executed and stored in memory: {dataset_name}, {self.format_memory_size(memory_bytes)}")
            
        except Exception as e:
            self.query_timer.stop()
            self.timer_label.setText("")
            logger.error(f"Failed to execute SQL: {e}")
            QMessageBox.critical(self, "SQL Execution Error", f"Failed to execute SQL:\n\n{str(e)}")
    
    def run_dataset(self):
        """Run the current Data Set (prompt for parameters and execute)"""
        if not self.current_dataset:
            QMessageBox.warning(self, "No Data Set", "Please create or load a Data Set first")
            return
        
        # Update from UI
        self.update_dataset_from_ui()
        
        # Validate
        error = self.current_dataset.validate()
        if error:
            QMessageBox.critical(self, "Validation Error", error)
            return
        
        # Show parameter dialog
        dialog = DataSetParametersDialog(self, self.current_dataset)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        # Get parameter values
        param_values = dialog.get_parameter_values()
        if param_values is None:
            return
        
        # Execute script to generate SQL
        sql, error = self.current_dataset.execute_script(param_values)
        
        if error:
            QMessageBox.critical(self, "Error", f"Failed to generate SQL:\n{error}")
            return
        
        # Emit signal to execute query (will be handled by main window or query screen)
        self.execute_query_signal.emit(sql, self.current_dataset.name)
        
        QMessageBox.information(self, "Query Generated",
                              f"SQL generated successfully!\n\n{sql[:200]}{'...' if len(sql) > 200 else ''}")
    
    def load_data_sources(self):
        """Load available data sources into the cascading dropdowns"""
        # Get all connections grouped by type
        connections = self.conn_repo.get_all_connections()
        
        # Group by connection type
        self.connections_by_type = {}
        for conn in connections:
            conn_type = conn['connection_type']
            if conn_type not in self.connections_by_type:
                self.connections_by_type[conn_type] = []
            self.connections_by_type[conn_type].append(conn)
        
        # Populate type dropdown
        self.type_combo.clear()
        self.type_combo.addItem("")  # Empty first item
        for conn_type in sorted(self.connections_by_type.keys()):
            self.type_combo.addItem(conn_type)
        
        # Connect signals
        self.type_combo.currentTextChanged.connect(self._on_db_type_changed)
        self.connection_combo.currentTextChanged.connect(self._on_connection_changed)
        self.tables_list.itemClicked.connect(self._on_table_clicked)
    
    def _on_db_type_changed(self, db_type: str):
        """Handle database type selection"""
        self.connection_combo.clear()
        self.connection_combo.addItem("")
        
        if db_type and db_type in self.connections_by_type:
            for conn in self.connections_by_type[db_type]:
                self.connection_combo.addItem(conn['connection_name'], conn['connection_id'])
    
    def _on_connection_changed(self, conn_name: str):
        """Handle connection selection - load tables"""
        self.tables_list.clear()
        
        if not conn_name:
            return
        
        # Get connection ID
        conn_id = self.connection_combo.currentData()
        if not conn_id:
            return
        
        self.current_connection_id = conn_id
        
        # Load tables for this connection
        try:
            # Get saved tables for this connection
            saved_tables = self.saved_table_repo.get_saved_tables(conn_id)
            
            if not saved_tables:
                return
            
            for table in saved_tables:
                table_name = table['table_name']
                schema_name = table.get('schema_name', '')
                
                # Display name
                display_name = f"{schema_name}.{table_name}" if schema_name else table_name
                
                item = QListWidgetItem(display_name)
                item.setData(Qt.ItemDataRole.UserRole, {
                    'table_name': table_name,
                    'schema_name': schema_name,
                    'connection_id': conn_id
                })
                self.tables_list.addItem(item)
            
        except Exception as e:
            logger.error(f"Error loading tables: {e}")
    
    def _on_table_clicked(self, item):
        """Handle table selection - load fields"""
        self.fields_list.clear()
        
        table_data = item.data(Qt.ItemDataRole.UserRole)
        if not table_data:
            return
        
        self.current_table_name = table_data['table_name']
        self.current_schema_name = table_data.get('schema_name', '')
        
        # Load fields for this table
        try:
            fields = self.schema_discovery.get_columns(
                table_data['connection_id'],
                table_data['table_name'],
                table_data.get('schema_name')
            )
            
            for field in fields:
                field_name = field.get('column_name') or field.get('COLUMN_NAME')
                data_type = field.get('data_type') or field.get('DATA_TYPE') or ''
                
                display_text = f"{field_name} ({data_type})" if data_type else field_name
                
                field_item = QListWidgetItem(display_text)
                field_item.setData(Qt.ItemDataRole.UserRole, field_name)
                self.fields_list.addItem(field_item)
            
        except Exception as e:
            logger.error(f"Error loading fields: {e}")
    
    # ========== Memory Management and In-Memory Dataset Methods ==========
    
    def get_dataframe_memory_bytes(self, df) -> int:
        """Calculate memory usage of a pandas DataFrame in bytes"""
        try:
            return int(df.memory_usage(deep=True).sum())
        except:
            # Fallback estimation
            return sys.getsizeof(df)
    
    def get_total_datasets_memory(self) -> int:
        """Get total memory used by all loaded datasets in bytes"""
        total = 0
        for dataset_info in self.loaded_datasets.values():
            total += dataset_info.get('memory_bytes', 0)
        return total
    
    def get_available_system_memory(self) -> int:
        """Get available system memory in bytes"""
        try:
            return psutil.virtual_memory().available
        except:
            return 0
    
    def format_memory_size(self, bytes_size: int) -> str:
        """Format bytes into human-readable string"""
        if bytes_size < 1024:
            return f"{bytes_size} B"
        elif bytes_size < 1024 * 1024:
            return f"{bytes_size / 1024:.1f} KB"
        elif bytes_size < 1024 * 1024 * 1024:
            return f"{bytes_size / (1024 * 1024):.1f} MB"
        else:
            return f"{bytes_size / (1024 * 1024 * 1024):.2f} GB"
    
    def update_memory_display(self):
        """Update the memory footer label"""
        if not self.memory_footer_label:
            return
        
        datasets_memory = self.get_total_datasets_memory()
        available_memory = self.get_available_system_memory()
        
        datasets_str = self.format_memory_size(datasets_memory)
        available_str = self.format_memory_size(available_memory)
        
        self.memory_footer_label.setText(
            f"Datasets: {datasets_str} | Available: {available_str}"
        )
    
    def check_memory_before_query(self, estimated_size: int = 0) -> bool:
        """Check if there's enough memory for a new query. Returns True if OK to proceed."""
        current_usage = self.get_total_datasets_memory()
        available = self.get_available_system_memory()
        
        # Warn if we're using more than 6GB for datasets or available memory is low
        if current_usage > (6 * 1024 * 1024 * 1024):  # 6 GB
            reply = QMessageBox.warning(
                self,
                "High Memory Usage",
                f"Datasets are using {self.format_memory_size(current_usage)} of memory.\n\n"
                f"Available system memory: {self.format_memory_size(available)}\n\n"
                "You may need to dump some datasets to free memory.\n\n"
                "Continue with query execution?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            return reply == QMessageBox.StandardButton.Yes
        
        if available < (1 * 1024 * 1024 * 1024):  # Less than 1 GB available
            reply = QMessageBox.warning(
                self,
                "Low System Memory",
                f"System memory is low: {self.format_memory_size(available)} available\n\n"
                "You may need to dump some datasets or close other applications.\n\n"
                "Continue with query execution?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            return reply == QMessageBox.StandardButton.Yes
        
        return True
    
    def is_dataset_loaded(self, dataset_name: str) -> bool:
        """Check if a dataset has data loaded in memory"""
        return dataset_name in self.loaded_datasets
    
    def reload_dataset(self):
        """Reload the current dataset from file, resetting all fields"""
        if not self.current_dataset:
            QMessageBox.warning(self, "No Data Set", "No Data Set to reload")
            return
        
        dataset_name = self.current_dataset.name
        
        # Confirm if there are unsaved changes
        if self.is_modified():
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "Current Data Set has unsaved changes. Reload will discard them.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # Reload from file
        self.load_dataset_from_file(dataset_name)
        
        logger.info(f"Reloaded Data Set: {dataset_name}")
        QMessageBox.information(self, "Reloaded", f"Data Set '{dataset_name}' reloaded from file")
    
    def dump_dataset_data(self, dataset_name: str):
        """Remove a dataset's data from memory"""
        if dataset_name in self.loaded_datasets:
            del self.loaded_datasets[dataset_name]
            logger.info(f"Dumped dataset from memory: {dataset_name}")
            
            # Update UI
            self.update_memory_display()
            self.load_datasets_list()  # Refresh to update green indicators
            
            # Clear the data tab if it's the current dataset
            if self.current_dataset and self.current_dataset.name == dataset_name:
                self.clear_data_tab()
    
    def clear_data_tab(self):
        """Clear the data tab and show empty state"""
        # Find the Data tab
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Data":
                # Get the tab widget
                data_tab = self.tab_widget.widget(i)
                
                # Clear the FilterTableView by setting empty DataFrame
                if hasattr(self, 'data_filter_view'):
                    import pandas as pd
                    empty_df = pd.DataFrame()
                    self.data_filter_view.set_dataframe(empty_df, limit_rows=False)
                
                # Update info label
                if hasattr(self, 'data_info_label'):
                    self.data_info_label.setText("No data loaded. Run query to load data.")
                
                break
    
    def remove_data_tab(self):
        """Remove the Data tab from tab widget"""
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Data":
                self.tab_widget.removeTab(i)
                break
    
    def create_or_update_data_tab(self, df, executed_time: datetime, memory_bytes: int):
        """Create or update the Data tab with query results"""
        # Check if Data tab already exists
        data_tab_index = -1
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Data":
                data_tab_index = i
                break
        
        if data_tab_index == -1:
            # Create new Data tab
            data_tab = QWidget()
            data_layout = QVBoxLayout(data_tab)
            data_layout.setContentsMargins(5, 5, 5, 5)
            data_layout.setSpacing(5)
            
            # Info panel at top
            info_panel = QWidget()
            info_layout = QHBoxLayout(info_panel)
            info_layout.setContentsMargins(5, 5, 5, 5)
            info_layout.setSpacing(10)
            
            # Info label
            self.data_info_label = QLabel()
            self.data_info_label.setStyleSheet("""
                QLabel {
                    color: #0A1E5E;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
            info_layout.addWidget(self.data_info_label)
            
            info_layout.addStretch()
            
            # Dump button
            dump_btn = QPushButton("🗑 Dump")
            dump_btn.clicked.connect(self.dump_current_dataset)
            dump_btn.setFixedSize(80, 28)
            dump_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffffff;
                    color: #dc3545;
                    font-weight: bold;
                    font-size: 10px;
                    border: 2px solid #dc3545;
                    border-radius: 3px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #f8d7da;
                    border-color: #c82333;
                }
                QPushButton:pressed {
                    background-color: #f5c6cb;
                }
            """)
            info_layout.addWidget(dump_btn)
            
            data_layout.addWidget(info_panel)
            
            # FilterTableView
            self.data_filter_view = FilterTableView()
            data_layout.addWidget(self.data_filter_view)
            
            # Add tab
            data_tab_index = self.tab_widget.addTab(data_tab, "Data")
        
        # Update info label
        time_str = executed_time.strftime("%Y-%m-%d %H:%M:%S")
        memory_str = self.format_memory_size(memory_bytes)
        row_count = len(df)
        col_count = len(df.columns)
        
        self.data_info_label.setText(
            f"Executed: {time_str} | Memory: {memory_str} | {row_count:,} rows × {col_count} columns"
        )
        
        # Load data into FilterTableView (use limit_rows=False for query results)
        self.data_filter_view.set_dataframe(df, limit_rows=False)
        
        # Switch to Data tab
        self.tab_widget.setCurrentIndex(data_tab_index)
    
    def dump_current_dataset(self):
        """Dump the current dataset from memory"""
        if not self.current_dataset:
            return
        
        dataset_name = self.current_dataset.name
        
        if dataset_name not in self.loaded_datasets:
            QMessageBox.information(self, "No Data", "This dataset has no data loaded in memory")
            return
        
        reply = QMessageBox.question(
            self,
            "Dump Dataset",
            f"Remove '{dataset_name}' data from memory?\n\nThe dataset definition will remain, but the query results will be cleared.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.dump_dataset_data(dataset_name)
