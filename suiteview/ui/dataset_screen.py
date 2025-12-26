"""
Data Set Screen - Dynamic SQL builder with Python scripting
"""

import logging
from pathlib import Path
import json
import re
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QLineEdit, QTextEdit, QTabWidget,
                              QSplitter, QListWidget, QMessageBox, QDialog,
                              QDialogButtonBox, QFormLayout, QTableWidget,
                              QTableWidgetItem, QHeaderView, QAbstractItemView,
                              QComboBox, QCheckBox, QFrame, QGroupBox, QListWidgetItem,
                              QSpinBox, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat

from suiteview.models.data_set import DataSet, DataSetParameter, DataSetField

logger = logging.getLogger(__name__)


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
        
        self.init_ui()
        self.load_datasets_list()
    
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Top toolbar - compact header with name inline
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        
        # Name input (left side)
        toolbar.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter Data Set name...")
        self.name_input.setFixedWidth(250)
        toolbar.addWidget(self.name_input)
        
        # Buttons in middle
        new_btn = QPushButton("➕ New")
        new_btn.clicked.connect(self.new_dataset)
        new_btn.setFixedWidth(80)
        new_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0078d4;
                padding: 4px 8px;
                font-weight: bold;
                border: 2px solid #0078d4;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
                border-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #bbdefb;
            }
        """)
        toolbar.addWidget(new_btn)
        
        save_btn = QPushButton("💾 Save")
        save_btn.clicked.connect(self.save_dataset)
        save_btn.setFixedWidth(80)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0078d4;
                padding: 4px 8px;
                font-weight: bold;
                border: 2px solid #0078d4;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
                border-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #bbdefb;
            }
        """)
        toolbar.addWidget(save_btn)
        
        delete_btn = QPushButton("🗑️ Delete")
        delete_btn.clicked.connect(self.delete_dataset)
        delete_btn.setFixedWidth(80)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #dc3545;
                padding: 4px 8px;
                font-weight: bold;
                border: 2px solid #dc3545;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f8d7da;
                border-color: #bd2130;
            }
            QPushButton:pressed {
                background-color: #f5c6cb;
            }
        """)
        toolbar.addWidget(delete_btn)
        
        toolbar.addStretch()
        
        run_btn = QPushButton("▶️ Run Data Set")
        run_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                padding: 6px 16px;
                font-weight: bold;
                border: 2px solid #28a745;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #218838;
                border-color: #1e7e34;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
        """)
        run_btn.clicked.connect(self.run_dataset)
        toolbar.addWidget(run_btn)
        
        layout.addLayout(toolbar)
        
        # Main splitter: saved datasets list | editor
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel: Saved Data Sets list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_header = QLabel("SAVED DATA SETS")
        left_header.setStyleSheet("""
            QLabel {
                background-color: #0A1E5E;
                color: white;
                padding: 8px;
                font-weight: bold;
                font-size: 11pt;
            }
        """)
        left_layout.addWidget(left_header)
        
        self.datasets_list = QListWidget()
        self.datasets_list.currentItemChanged.connect(self.on_dataset_selected)
        self.datasets_list.setStyleSheet("""
            QListWidget {
                background-color: #D6E9FF;
                border: 1px solid #ccc;
            }
            QListWidget::item {
                padding: 8px 12px;
                font-size: 10pt;
                font-weight: bold;
                color: #333;
                background-color: #D6E9FF;
            }
            QListWidget::item:selected {
                background-color: #2563EB;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #C0DDFF;
            }
        """)
        left_layout.addWidget(self.datasets_list)
        
        main_splitter.addWidget(left_panel)
        
        # Right panel: Editor
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Tab widget for Script / Parameters / Display
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #d0d0d0;
                background-color: white;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #f0f0f0;
                color: #333;
                padding: 6px 16px;
                border: 1px solid #d0d0d0;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 1px solid white;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #e8e8e8;
            }
            QTabWidget {
                background-color: transparent;
            }
            QTabBar {
                background-color: transparent;
            }
        """)
        
        # Script Builder Tab
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
        
        # Text size controls
        size_label = QLabel("Size:")
        size_label.setStyleSheet("color: #333; font-size: 9pt;")
        script_toolbar.addWidget(size_label)
        
        self.text_size_spinner = QSpinBox()
        self.text_size_spinner.setRange(8, 20)
        self.text_size_spinner.setValue(11)
        self.text_size_spinner.setSuffix(" pt")
        self.text_size_spinner.setFixedWidth(65)
        self.text_size_spinner.setFixedHeight(24)
        self.text_size_spinner.setStyleSheet("""
            QSpinBox {
                background-color: white;
                color: #333;
                border: 1px solid #0078d4;
                border-radius: 3px;
                padding: 2px;
                font-size: 9pt;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 14px;
                background-color: #e3f2fd;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #bbdefb;
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
        
        script_layout.addWidget(self.script_editor)
        
        # Help text
        help_text = QLabel(
            "💡 Tip: Define a function named 'build_query' that takes parameters and returns a SQL string.\n"
            "Parameters will be auto-detected from the function signature."
        )
        help_text.setStyleSheet("color: #888; font-size: 10pt; font-style: italic; padding: 5px;")
        help_text.setWordWrap(True)
        script_layout.addWidget(help_text)
        
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
        
        copy_sql_btn = QPushButton("📋 Copy SQL")
        copy_sql_btn.clicked.connect(self.copy_sql_to_clipboard)
        copy_sql_btn.setStyleSheet("""
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
        sql_toolbar.addWidget(copy_sql_btn)
        sql_toolbar.addStretch()
        
        sql_layout.addLayout(sql_toolbar)
        
        self.sql_display = QTextEdit()
        self.sql_display.setReadOnly(True)
        self.sql_display.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11pt;
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 2px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        sql_layout.addWidget(self.sql_display)
        
        self.tab_widget.addTab(sql_tab, "SQL")
        
        right_layout.addWidget(self.tab_widget)
        
        main_splitter.addWidget(right_panel)
        
        # Set splitter sizes (20% list, 80% editor)
        main_splitter.setSizes([200, 800])
        
        layout.addWidget(main_splitter)
    
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
        self.script_editor.setPlainText(script_template)
        
        # Auto-populate Calling tab with template
        calling_template = '''# Call the build_query function with parameter values
# Example:

sql = build_query(
    policy_nums=['12345', '67890'],
    state='CA',
    as_of_date='2024-12-31'
)
'''
        self.calling_editor.setPlainText(calling_template)
    
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
    
    def delete_dataset(self):
        """Delete the selected Data Set"""
        current_item = self.datasets_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a Data Set to delete")
            return
        
        dataset_name = current_item.text()
        
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
            
            if self.current_dataset and self.current_dataset.name == dataset_name:
                self.current_dataset = None
                self.load_dataset_to_ui()
            
            self.load_datasets_list()
            
        except Exception as e:
            logger.error(f"Error deleting Data Set: {e}")
            QMessageBox.critical(self, "Error", f"Failed to delete Data Set:\n{e}")
    
    def load_datasets_list(self):
        """Load the list of saved Data Sets"""
        self.datasets_list.clear()
        
        for file in sorted(self.datasets_dir.glob("*.json")):
            self.datasets_list.addItem(file.stem)
    
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
        
        dataset_name = current.text()
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
            self.name_input.clear()
            self.script_editor.clear()
            self.params_table.setRowCount(0)
            self.display_table.setRowCount(0)
            return
        
        self.name_input.setText(self.current_dataset.name)
        self.script_editor.setPlainText(self.current_dataset.script_code)
        
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
        
        self.current_dataset.name = self.name_input.text().strip()
        self.current_dataset.script_code = self.script_editor.toPlainText()
        
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
        
        # Simple check: compare UI values with saved dataset
        return (
            self.name_input.text().strip() != self.current_dataset.name or
            self.script_editor.toPlainText() != self.current_dataset.script_code
        )
    
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
        
        if self.script_editor.toPlainText().strip():
            reply = QMessageBox.question(
                self, "Replace Script?",
                "This will replace your current script. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        self.script_editor.setPlainText(template)
        QMessageBox.information(self, "Template Loaded",
                              "Template loaded successfully!\nClick 'Validate Script' to parse parameters.")
    
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
        """Format SQL for better readability"""
        if not sql:
            return sql
        
        # Simple SQL formatter - add line breaks for major keywords
        formatted = sql
        
        # Replace major SQL keywords with newline + keyword
        keywords = ['SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'ORDER BY', 'GROUP BY', 'HAVING']
        
        for keyword in keywords:
            if keyword == 'SELECT':
                # SELECT stays on first line
                formatted = formatted.replace(keyword, keyword)
            elif keyword == 'FROM':
                formatted = formatted.replace(' ' + keyword + ' ', '\n' + keyword + ' ')
            elif keyword == 'WHERE':
                formatted = formatted.replace(' ' + keyword + ' ', '\n' + keyword + ' ')
            elif keyword in ['AND', 'OR']:
                formatted = formatted.replace(' ' + keyword + ' ', '\n  ' + keyword + ' ')
            else:
                formatted = formatted.replace(' ' + keyword + ' ', '\n' + keyword + ' ')
        
        return formatted
    
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
            
            QMessageBox.information(self, "Success", 
                                  f"SQL generated successfully!\n\nParameters: {len(params)}\nFields: {len(self.current_dataset.display_fields)}")
            
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
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(sql)
            QMessageBox.information(self, "Copied", "SQL copied to clipboard")
        else:
            QMessageBox.warning(self, "No SQL", "Generate SQL first")
    
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
