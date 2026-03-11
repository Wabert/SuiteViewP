"""
Search Content Window - Advanced dataset content search with dataset management
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QSplitter, QHeaderView,
    QCheckBox, QMessageBox, QDialog, QApplication, QStyle, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
import logging
import re

logger = logging.getLogger(__name__)


class SearchContentWindow(QWidget):
    """Standalone window for advanced dataset content searching"""
    
    def __init__(self, ftp_manager, parent=None):
        super().__init__(parent)
        self.ftp_manager = ftp_manager
        self.datasets_to_search = []  # List of datasets added for searching
        self.current_results = []
        
        # Make it a separate standalone window
        self.setWindowFlags(Qt.WindowType.Window)
        self.setWindowTitle("🔍 Search Dataset Content")
        self.resize(1200, 800)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # SEARCH CRITERIA AT TOP - 4 search boxes with checkboxes
        search_control_widget = QWidget()
        search_control_widget.setStyleSheet("background-color: #f8f9fa; border: 1px solid #bdc3c7; border-radius: 3px;")
        search_control_layout = QVBoxLayout(search_control_widget)
        search_control_layout.setContentsMargins(6, 3, 6, 3)
        search_control_layout.setSpacing(2)
        
        # Create 4 search rows
        self.search_inputs = []
        self.case_sensitive_cbs = []
        self.allow_wildcard_cbs = []
        
        for i in range(4):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(6)
            
            # Search label
            search_label = QLabel(f"Search {i+1}:")
            search_label.setStyleSheet("font-weight: bold; font-size: 8pt; color: #2c3e50; min-width: 55px;")
            row_layout.addWidget(search_label)
            
            # Search input
            search_input = QLineEdit()
            search_input.setPlaceholderText(f"Enter search string {i+1}...")
            search_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #bdc3c7;
                    border-radius: 2px;
                    padding: 2px 4px;
                    font-family: Consolas, monospace;
                    font-size: 8pt;
                    background-color: white;
                }
            """)
            row_layout.addWidget(search_input, 1)
            self.search_inputs.append(search_input)
            
            # Case sensitive checkbox
            case_cb = QCheckBox("Case Sensitive")
            case_cb.setStyleSheet("font-size: 8pt;")
            row_layout.addWidget(case_cb)
            self.case_sensitive_cbs.append(case_cb)
            
            # Allow wildcard checkbox
            wildcard_cb = QCheckBox("Allow Wildcard")
            wildcard_cb.setStyleSheet("font-size: 8pt;")
            row_layout.addWidget(wildcard_cb)
            self.allow_wildcard_cbs.append(wildcard_cb)
            
            search_control_layout.addLayout(row_layout)
        
        # Search button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        search_btn = QPushButton("Search")
        search_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 3px 16px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #5dade2;
            }
        """)
        search_btn.clicked.connect(self.perform_search)
        button_layout.addWidget(search_btn)
        search_control_layout.addLayout(button_layout)
        
        # Set size policy to not expand vertically
        search_control_widget.setSizePolicy(
            search_control_widget.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Fixed
        )
        layout.addWidget(search_control_widget)
        
        # MAIN AREA - Horizontal splitter with 2 lists (takes all remaining space)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # LEFT SECTION - Datasets to search
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)
        
        # Dataset list header
        dataset_header = QLabel("📋 Datasets to Search")
        dataset_header.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 10pt;
                color: #2c3e50;
                padding: 4px 6px;
                background-color: #e8f4f8;
                border-radius: 3px;
            }
        """)
        left_layout.addWidget(dataset_header)
        
        dataset_info = QLabel("Right-click datasets in Mainframe Nav and select 'Add to Search'")
        dataset_info.setStyleSheet("color: #7f8c8d; font-size: 8pt; font-style: italic; padding: 2px;")
        left_layout.addWidget(dataset_info)
        
        # Dataset table with filter
        dataset_controls = QHBoxLayout()
        dataset_filter_label = QLabel("Filter:")
        dataset_filter_label.setStyleSheet("font-size: 9pt; color: #34495e;")
        dataset_controls.addWidget(dataset_filter_label)
        
        self.dataset_filter = QLineEdit()
        self.dataset_filter.setPlaceholderText("Filter dataset list...")
        self.dataset_filter.setStyleSheet("""
            QLineEdit {
                padding: 3px 6px;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                font-size: 9pt;
            }
        """)
        self.dataset_filter.textChanged.connect(self.filter_dataset_list)
        dataset_controls.addWidget(self.dataset_filter)
        
        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 3px 10px;
                border-radius: 3px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        clear_all_btn.clicked.connect(self.clear_all_datasets)
        dataset_controls.addWidget(clear_all_btn)
        
        left_layout.addLayout(dataset_controls)
        
        # Dataset list table
        self.dataset_table = QTableWidget()
        self.dataset_table.setColumnCount(2)
        self.dataset_table.setHorizontalHeaderLabels(["Dataset", "Path"])
        self.dataset_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.dataset_table.setAlternatingRowColors(True)
        self.dataset_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.dataset_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.dataset_table.verticalHeader().setVisible(False)
        self.dataset_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #bdc3c7;
                background-color: white;
            }
            QTableWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
        """)
        self.dataset_table.itemDoubleClicked.connect(self.view_dataset)
        self.dataset_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.dataset_table.customContextMenuRequested.connect(self.show_dataset_context_menu)
        left_layout.addWidget(self.dataset_table)
        
        main_splitter.addWidget(left_widget)
        
        # RIGHT SECTION - Matching datasets
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)
        
        # Results header
        results_header_layout = QHBoxLayout()
        results_label = QLabel("✓ Datasets with Matches")
        results_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 10pt;
                color: #2c3e50;
                padding: 4px 6px;
                background-color: #e8f8f5;
                border-radius: 3px;
            }
        """)
        results_header_layout.addWidget(results_label)
        
        self.results_info_label = QLabel("")
        self.results_info_label.setStyleSheet("color: #7f8c8d; font-style: italic; font-size: 8pt; padding: 4px;")
        results_header_layout.addWidget(self.results_info_label)
        
        results_header_layout.addStretch()
        
        right_layout.addLayout(results_header_layout)
        
        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Dataset", "Matches", "Path"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #bdc3c7;
                background-color: white;
            }
            QTableWidget::item:selected {
                background-color: #27ae60;
                color: white;
            }
        """)
        self.results_table.itemDoubleClicked.connect(self.view_result_details)
        right_layout.addWidget(self.results_table)
        
        # Copy button
        copy_btn_layout = QHBoxLayout()
        copy_btn_layout.addStretch()
        copy_results_btn = QPushButton("📋 Copy Results")
        copy_results_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                padding: 4px 12px;
                border-radius: 3px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        copy_results_btn.clicked.connect(self.copy_results)
        copy_btn_layout.addWidget(copy_results_btn)
        right_layout.addLayout(copy_btn_layout)
        
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([500, 700])
        
        layout.addWidget(main_splitter)
    
    def add_dataset(self, dataset_name, full_path, dsorg=''):
        """Add a dataset to the search list"""
        # Check if already added
        for row in range(self.dataset_table.rowCount()):
            path_item = self.dataset_table.item(row, 1)
            if path_item and path_item.text() == full_path:
                return
        
        # Skip PO datasets
        if dsorg == 'PO':
            QMessageBox.warning(
                self,
                "Cannot Add PO Dataset",
                f"{dataset_name} is a PO (partitioned) dataset and cannot be searched directly.\n\n"
                "Please add its members instead."
            )
            return
        
        row = self.dataset_table.rowCount()
        self.dataset_table.insertRow(row)
        
        self.dataset_table.setItem(row, 0, QTableWidgetItem(dataset_name))
        self.dataset_table.setItem(row, 1, QTableWidgetItem(full_path))
        
        self.datasets_to_search.append({
            'name': dataset_name,
            'full_path': full_path,
            'dsorg': dsorg
        })
        
        logger.info(f"Added {dataset_name} to search list")
    
    def filter_dataset_list(self, text):
        """Filter the dataset list"""
        for row in range(self.dataset_table.rowCount()):
            name_item = self.dataset_table.item(row, 0)
            if name_item:
                self.dataset_table.setRowHidden(row, text.lower() not in name_item.text().lower())
    
    def clear_all_datasets(self):
        """Clear all datasets from the list"""
        self.dataset_table.setRowCount(0)
        self.results_table.setRowCount(0)
        self.datasets_to_search.clear()
        self.results_info_label.setText("")
    
    def show_dataset_context_menu(self, position):
        """Show context menu for dataset table"""
        from PyQt6.QtWidgets import QMenu
        
        item = self.dataset_table.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        remove_action = menu.addAction("Remove from List")
        view_action = menu.addAction("View Dataset")
        
        action = menu.exec(self.dataset_table.viewport().mapToGlobal(position))
        
        if action == remove_action:
            row = item.row()
            self.dataset_table.removeRow(row)
            if row < len(self.datasets_to_search):
                removed = self.datasets_to_search.pop(row)
        elif action == view_action:
            self.view_dataset(item)
    
    def view_dataset(self, item):
        """View dataset content in a dialog"""
        row = item.row()
        name_item = self.dataset_table.item(row, 0)
        path_item = self.dataset_table.item(row, 1)
        
        if not name_item or not path_item:
            return
        
        dataset_name = name_item.text()
        full_path = path_item.text()
        
        # Read dataset content
        try:
            content, total_lines = self.ftp_manager.read_dataset(full_path, max_lines=1000)
            
            if total_lines == 0:
                QMessageBox.warning(self, "No Content", f"Dataset {dataset_name} is empty or could not be read.")
                return
            
            # Show in dialog
            dialog = QDialog(self)
            dialog.setWindowTitle(f"View: {dataset_name}")
            dialog.resize(900, 700)
            
            layout = QVBoxLayout(dialog)
            
            info_label = QLabel(f"Showing first 1000 lines of {dataset_name} (Total: {total_lines} lines)")
            info_label.setStyleSheet("font-weight: bold; padding: 4px; background-color: #e8f4f8;")
            layout.addWidget(info_label)
            
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setFont(QFont("Courier New", 9))
            text_edit.setPlainText(content)
            layout.addWidget(text_edit)
            
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn)
            
            dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to view dataset:\n{str(e)}")
            logger.error(f"Error viewing dataset {dataset_name}: {e}")
    
    def perform_search(self):
        """Perform the search"""
        if not self.datasets_to_search:
            QMessageBox.warning(self, "No Datasets", "Please add datasets to search first.")
            return
        
        # Collect search strings from all 4 search boxes
        search_strings = []
        for i, search_input in enumerate(self.search_inputs):
            search_text = search_input.text().strip()
            if search_text:
                search_strings.append(search_text)
        
        if not search_strings:
            QMessageBox.warning(self, "No Search Strings", "Please enter at least one search string.")
            return
        
        # For now, use the first search box's settings for case_sensitive and whole_word
        # TODO: Handle individual settings per search string
        case_sensitive = self.case_sensitive_cbs[0].isChecked() if self.case_sensitive_cbs else False
        # Note: Allow wildcard will be handled in the search thread
        
        # Import and use the search thread from mainframe_nav_screen
        from suiteview.ui.mainframe_nav_screen import ContentSearchThread
        
        # Create progress dialog
        progress_dialog = QDialog(self)
        progress_dialog.setWindowTitle("Searching...")
        progress_dialog.setModal(True)
        progress_dialog.resize(400, 100)
        
        progress_layout = QVBoxLayout(progress_dialog)
        progress_label = QLabel(f"Searching dataset 0 of {len(self.datasets_to_search)}...")
        progress_layout.addWidget(progress_label)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        progress_layout.addWidget(cancel_btn)
        
        # Start search
        self.search_thread = ContentSearchThread(
            self.ftp_manager,
            self.datasets_to_search,
            search_strings,
            case_sensitive,
            False,  # whole_word not used anymore
            ""  # current_dataset not needed here
        )
        
        cancel_btn.clicked.connect(self.search_thread.cancel)
        cancel_btn.clicked.connect(progress_dialog.close)
        
        self.search_thread.progress_update.connect(
            lambda msg, curr, total: progress_label.setText(f"{msg} ({curr} of {total})")
        )
        
        self.search_thread.search_complete.connect(self.display_results)
        self.search_thread.search_complete.connect(progress_dialog.close)
        
        self.search_thread.start()
        progress_dialog.exec()
    
    def display_results(self, result_data):
        """Display search results in the results table"""
        results = result_data.get('results', [])
        errors = result_data.get('errors', [])
        skipped = result_data.get('skipped', [])
        
        self.current_results = results
        
        # Clear results table
        self.results_table.setRowCount(0)
        
        # Update info
        info_parts = []
        if results:
            info_parts.append(f"{len(results)} with matches")
        if skipped:
            info_parts.append(f"{len(skipped)} skipped")
        if errors:
            info_parts.append(f"{len(errors)} errors")
        
        if results:
            self.results_info_label.setText(", ".join(info_parts))
            self.results_info_label.setStyleSheet("color: #27ae60; font-style: italic; font-size: 9pt; padding: 6px;")
        else:
            self.results_info_label.setText("No matches found" + (f" ({', '.join(info_parts[1:])})" if info_parts[1:] else ""))
            self.results_info_label.setStyleSheet("color: #e74c3c; font-style: italic; font-size: 9pt; padding: 6px;")
        
        # Populate results table
        for result in results:
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)
            
            dataset_name = result['dataset']
            full_path = result['full_path']
            
            # Count total matches
            total_matches = sum(len(mg['matches']) for mg in result['matches'])
            
            # Store result data in first item
            name_item = QTableWidgetItem(dataset_name)
            name_item.setData(Qt.ItemDataRole.UserRole, result)
            
            self.results_table.setItem(row, 0, name_item)
            self.results_table.setItem(row, 1, QTableWidgetItem(str(total_matches)))
            self.results_table.setItem(row, 2, QTableWidgetItem(full_path))
        
        logger.info(f"Display complete: {len(results)} results, {len(skipped)} skipped, {len(errors)} errors")
    
    def view_result_details(self, item):
        """View detailed match information for a result"""
        row = item.row()
        name_item = self.results_table.item(row, 0)
        
        if not name_item:
            return
        
        result = name_item.data(Qt.ItemDataRole.UserRole)
        if not result:
            return
        
        # Create dialog to show details
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Match Details: {result['dataset']}")
        dialog.resize(900, 700)
        
        layout = QVBoxLayout(dialog)
        
        # Header
        header = QLabel(f"Dataset: {result['dataset']}\nPath: {result['full_path']}")
        header.setStyleSheet("""
            QLabel {
                font-weight: bold;
                padding: 8px;
                background-color: #e8f4f8;
                border-radius: 3px;
            }
        """)
        layout.addWidget(header)
        
        # Match details
        details_text = QTextEdit()
        details_text.setReadOnly(True)
        details_text.setFont(QFont("Courier New", 9))
        
        output = []
        for match_group in result['matches']:
            search_str = match_group['search_string']
            matches = match_group['matches']
            output.append(f"\n{'='*80}")
            output.append(f"Search String: '{search_str}' - {len(matches)} match(es) found")
            output.append(f"{'-'*80}")
            
            for match in matches:
                line_num = match['line_number']
                line_content = match['line_content']
                output.append(f"  Line {line_num}: {line_content}")
        
        details_text.setPlainText('\n'.join(output))
        layout.addWidget(details_text)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec()
    
    def copy_results(self):
        """Copy results to clipboard"""
        if not self.current_results:
            return
        
        from PyQt6.QtGui import QGuiApplication
        clipboard = QGuiApplication.clipboard()
        
        output = []
        for result in self.current_results:
            output.append(f"\n{'='*80}")
            output.append(f"Dataset: {result['dataset']}")
            output.append(f"Path: {result['full_path']}")
            output.append(f"{'-'*80}")
            
            for match_group in result['matches']:
                search_str = match_group['search_string']
                matches = match_group['matches']
                output.append(f"\n  Search String: '{search_str}' - {len(matches)} match(es)")
                
                for match in matches:
                    line_num = match['line_number']
                    line_content = match['line_content']
                    output.append(f"    Line {line_num}: {line_content}")
        
        clipboard.setText('\n'.join(output))
