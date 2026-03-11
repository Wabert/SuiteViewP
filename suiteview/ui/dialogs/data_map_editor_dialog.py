"""Dialog for creating and editing data mappings"""

import logging
from typing import List, Dict, Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox, QMessageBox,
    QHeaderView, QAbstractItemView, QApplication
)
from PyQt6.QtCore import Qt, QDateTime
from PyQt6.QtGui import QIcon

from suiteview.data.repositories import get_data_map_repository

logger = logging.getLogger(__name__)


class DataMapEditorDialog(QDialog):
    """Dialog for creating and editing data mappings"""

    def __init__(self, parent=None, data_map_id: int = None, 
                 map_name: str = None, folder_id: int = None,
                 pre_populate_keys: List[str] = None):
        """
        Initialize the data map editor dialog
        
        Args:
            parent: Parent widget
            data_map_id: ID of existing data map to edit (None for new)
            map_name: Pre-filled map name (for new maps)
            folder_id: Folder to place the map in
            pre_populate_keys: List of keys to pre-populate (from unique values)
        """
        super().__init__(parent)
        self.data_map_id = data_map_id
        self.folder_id = folder_id
        self.pre_populate_keys = pre_populate_keys or []
        self.data_map_repo = get_data_map_repository()
        
        self.setWindowTitle("Data Map Editor")
        self.setModal(True)
        self.resize(900, 600)
        
        self.init_ui()
        
        # Load existing data if editing
        if data_map_id:
            self.load_data_map()
        elif map_name:
            self.name_input.setText(map_name)
        
        # Pre-populate keys if provided
        if self.pre_populate_keys:
            self.populate_keys(self.pre_populate_keys)

    def init_ui(self):
        """Initialize the UI components"""
        layout = QVBoxLayout()
        
        # Map name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Map Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter a unique name for this data map...")
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # Data types
        types_layout = QHBoxLayout()
        types_layout.addWidget(QLabel("Key Data Type:"))
        self.key_type_combo = QComboBox()
        self.key_type_combo.addItems(['string', 'integer', 'decimal', 'date', 'boolean'])
        types_layout.addWidget(self.key_type_combo)
        
        types_layout.addSpacing(20)
        types_layout.addWidget(QLabel("Value Data Type:"))
        self.value_type_combo = QComboBox()
        self.value_type_combo.addItems(['string', 'integer', 'decimal', 'date', 'boolean'])
        types_layout.addWidget(self.value_type_combo)
        types_layout.addStretch()
        layout.addLayout(types_layout)
        
        # Notes
        layout.addWidget(QLabel("Notes / Description:"))
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("Enter notes or description for this data mapping...")
        self.notes_input.setMaximumHeight(80)
        layout.addWidget(self.notes_input)
        
        # Entries table
        layout.addWidget(QLabel("Key-Value Mappings:"))
        
        # Buttons above table
        table_buttons_layout = QHBoxLayout()
        
        self.add_row_btn = QPushButton("➕ Add Row")
        self.add_row_btn.clicked.connect(self.add_empty_row)
        table_buttons_layout.addWidget(self.add_row_btn)
        
        self.delete_rows_btn = QPushButton("🗑️ Delete Selected")
        self.delete_rows_btn.clicked.connect(self.delete_selected_rows)
        table_buttons_layout.addWidget(self.delete_rows_btn)
        
        table_buttons_layout.addSpacing(20)
        
        self.paste_btn = QPushButton("📋 Paste from Clipboard")
        self.paste_btn.clicked.connect(self.paste_from_clipboard)
        table_buttons_layout.addWidget(self.paste_btn)
        
        self.import_excel_btn = QPushButton("📊 Import from Excel")
        self.import_excel_btn.clicked.connect(self.import_from_excel)
        table_buttons_layout.addWidget(self.import_excel_btn)
        
        table_buttons_layout.addStretch()
        layout.addLayout(table_buttons_layout)
        
        # Table
        self.entries_table = QTableWidget()
        self.entries_table.setColumnCount(4)
        self.entries_table.setHorizontalHeaderLabels(['Key', 'Value', 'Comment', 'Last Updated'])
        self.entries_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.entries_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        
        # Set column widths
        header = self.entries_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.entries_table)
        
        # Bottom buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.save_btn = QPushButton("💾 Save Data Map")
        self.save_btn.clicked.connect(self.save_data_map)
        self.save_btn.setDefault(True)
        buttons_layout.addWidget(self.save_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)

    def load_data_map(self):
        """Load existing data map for editing"""
        try:
            data_map = self.data_map_repo.get_data_map(self.data_map_id)
            if not data_map:
                QMessageBox.warning(self, "Error", "Data map not found")
                return
            
            self.name_input.setText(data_map['map_name'])
            self.key_type_combo.setCurrentText(data_map['key_data_type'])
            self.value_type_combo.setCurrentText(data_map['value_data_type'])
            if data_map['notes']:
                self.notes_input.setPlainText(data_map['notes'])
            
            # Load entries
            entries = self.data_map_repo.get_map_entries(self.data_map_id)
            for entry in entries:
                self.add_entry_row(
                    entry['key_value'],
                    entry['mapped_value'] or '',
                    entry['comment'] or '',
                    entry['last_updated'],
                    entry['entry_id']
                )
            
        except Exception as e:
            logger.error(f"Error loading data map: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load data map:\n{str(e)}")

    def populate_keys(self, keys: List[str]):
        """Pre-populate the table with keys from unique values"""
        for key in keys:
            self.add_entry_row(str(key), '', '', None, None)

    def add_empty_row(self):
        """Add an empty row to the table"""
        self.add_entry_row('', '', '', None, None)

    def add_entry_row(self, key: str, value: str, comment: str, 
                     last_updated: str, entry_id: int):
        """Add a row to the entries table"""
        row = self.entries_table.rowCount()
        self.entries_table.insertRow(row)
        
        # Key
        key_item = QTableWidgetItem(key)
        self.entries_table.setItem(row, 0, key_item)
        
        # Value
        value_item = QTableWidgetItem(value)
        self.entries_table.setItem(row, 1, value_item)
        
        # Comment
        comment_item = QTableWidgetItem(comment)
        self.entries_table.setItem(row, 2, comment_item)
        
        # Last Updated
        if last_updated:
            last_updated_item = QTableWidgetItem(last_updated)
        else:
            last_updated_item = QTableWidgetItem('')
        last_updated_item.setFlags(last_updated_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.entries_table.setItem(row, 3, last_updated_item)
        
        # Store entry_id in row data
        self.entries_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, entry_id)

    def delete_selected_rows(self):
        """Delete selected rows from the table"""
        selected_rows = set()
        for item in self.entries_table.selectedItems():
            selected_rows.add(item.row())
        
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select rows to delete")
            return
        
        # Remove rows in reverse order to maintain indices
        for row in sorted(selected_rows, reverse=True):
            self.entries_table.removeRow(row)

    def paste_from_clipboard(self):
        """Paste data from clipboard (tab-separated values)"""
        try:
            clipboard = QApplication.clipboard()
            text = clipboard.text()
            
            if not text.strip():
                QMessageBox.information(self, "Empty Clipboard", "Clipboard is empty")
                return
            
            lines = text.strip().split('\n')
            added_count = 0
            
            for line in lines:
                parts = line.split('\t')
                if len(parts) >= 1:
                    key = parts[0].strip()
                    value = parts[1].strip() if len(parts) > 1 else ''
                    comment = parts[2].strip() if len(parts) > 2 else ''
                    
                    if key:  # Only add if key is not empty
                        self.add_entry_row(key, value, comment, None, None)
                        added_count += 1
            
            QMessageBox.information(self, "Success", f"Added {added_count} entries from clipboard")
            
        except Exception as e:
            logger.error(f"Error pasting from clipboard: {e}")
            QMessageBox.critical(self, "Error", f"Failed to paste from clipboard:\n{str(e)}")

    def import_from_excel(self):
        """Import data from Excel file"""
        from PyQt6.QtWidgets import QFileDialog
        
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Excel File",
                "",
                "Excel Files (*.xlsx *.xls)"
            )
            
            if not file_path:
                return
            
            # Try to import pandas
            try:
                import pandas as pd
            except ImportError:
                QMessageBox.warning(
                    self,
                    "pandas Required",
                    "pandas library is required for Excel import.\n"
                    "Please install it using: pip install pandas openpyxl"
                )
                return
            
            # Read Excel file
            df = pd.read_excel(file_path)
            
            if df.empty:
                QMessageBox.information(self, "Empty File", "Excel file is empty")
                return
            
            # Assume first column is key, second is value, third is comment (if present)
            added_count = 0
            for _, row in df.iterrows():
                key = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ''
                value = str(row.iloc[1]) if len(row) > 1 and pd.notna(row.iloc[1]) else ''
                comment = str(row.iloc[2]) if len(row) > 2 and pd.notna(row.iloc[2]) else ''
                
                if key:  # Only add if key is not empty
                    self.add_entry_row(key, value, comment, None, None)
                    added_count += 1
            
            QMessageBox.information(self, "Success", f"Imported {added_count} entries from Excel")
            
        except Exception as e:
            logger.error(f"Error importing from Excel: {e}")
            QMessageBox.critical(self, "Error", f"Failed to import from Excel:\n{str(e)}")

    def save_data_map(self):
        """Save the data map"""
        try:
            map_name = self.name_input.text().strip()
            if not map_name:
                QMessageBox.warning(self, "Validation Error", "Please enter a map name")
                return
            
            # Check if name is unique (unless editing the same map)
            existing = self.data_map_repo.get_data_map_by_name(map_name)
            if existing and existing['data_map_id'] != self.data_map_id:
                QMessageBox.warning(
                    self,
                    "Validation Error",
                    f"A data map named '{map_name}' already exists.\nPlease choose a different name."
                )
                return
            
            key_data_type = self.key_type_combo.currentText()
            value_data_type = self.value_type_combo.currentText()
            notes = self.notes_input.toPlainText().strip() or None
            
            # Create or update data map
            if self.data_map_id:
                self.data_map_repo.update_data_map(
                    self.data_map_id,
                    map_name=map_name,
                    key_data_type=key_data_type,
                    value_data_type=value_data_type,
                    notes=notes,
                    folder_id=self.folder_id
                )
                data_map_id = self.data_map_id
            else:
                data_map_id = self.data_map_repo.create_data_map(
                    map_name,
                    key_data_type=key_data_type,
                    value_data_type=value_data_type,
                    notes=notes,
                    folder_id=self.folder_id
                )
                self.data_map_id = data_map_id
            
            # Get existing entries to track what to delete
            existing_entries = self.data_map_repo.get_map_entries(data_map_id)
            existing_entry_ids = {e['entry_id'] for e in existing_entries}
            kept_entry_ids = set()
            
            # Save all entries
            for row in range(self.entries_table.rowCount()):
                key = self.entries_table.item(row, 0).text().strip()
                value = self.entries_table.item(row, 1).text().strip()
                comment = self.entries_table.item(row, 2).text().strip() or None
                entry_id = self.entries_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                
                if not key:  # Skip empty keys
                    continue
                
                if entry_id and entry_id in existing_entry_ids:
                    # Update existing entry
                    self.data_map_repo.update_map_entry(
                        entry_id,
                        key_value=key,
                        mapped_value=value or None,
                        comment=comment
                    )
                    kept_entry_ids.add(entry_id)
                else:
                    # Add new entry
                    new_entry_id = self.data_map_repo.add_map_entry(
                        data_map_id,
                        key_value=key,
                        mapped_value=value or None,
                        comment=comment
                    )
                    kept_entry_ids.add(new_entry_id)
            
            # Delete entries that were removed
            deleted_ids = existing_entry_ids - kept_entry_ids
            if deleted_ids:
                self.data_map_repo.delete_map_entries(list(deleted_ids))
            
            QMessageBox.information(self, "Success", f"Data map '{map_name}' saved successfully!")
            self.accept()
            
        except Exception as e:
            logger.error(f"Error saving data map: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save data map:\n{str(e)}")
