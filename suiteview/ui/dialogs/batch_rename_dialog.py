"""
Batch Rename Dialog - Rename multiple files with patterns
"""

from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                              QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                              QDialogButtonBox, QMessageBox, QGroupBox, QRadioButton,
                              QButtonGroup, QSpinBox, QComboBox, QCheckBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

import logging
logger = logging.getLogger(__name__)


class BatchRenameDialog(QDialog):
    """Dialog for batch renaming files"""
    
    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        self.file_paths = [Path(p) for p in file_paths]
        self.setWindowTitle(f"Batch Rename - {len(self.file_paths)} Files")
        self.setModal(True)
        self.resize(800, 600)
        
        self.init_ui()
        self.update_preview()
    
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)
        
        # Compact stylesheet for all input controls
        compact_input_style = """
            QDialog {
                background-color: white;
            }
            QLineEdit, QSpinBox, QComboBox {
                padding: 2px 5px;
                margin: 0px;
                height: 22px;
                background-color: white;
                color: black;
                border: 1px solid #A0A0A0;
                border-radius: 2px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                background-color: white;
                border: 1px solid #0078d4;
            }
            QSpinBox {
                padding-right: 18px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 16px;
                background-color: #E0E0E0;
                border: 1px solid #A0A0A0;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #C8DCF0;
            }
            QSpinBox::up-arrow {
                image: none;
                width: 0px;
                height: 0px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid #404040;
            }
            QSpinBox::down-arrow {
                image: none;
                width: 0px;
                height: 0px;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #404040;
            }
            QLabel {
                color: black;
                background-color: transparent;
            }
            QGroupBox {
                background-color: white;
                border: 1px solid #CCCCCC;
                border-radius: 3px;
                margin-top: 3px;
                padding-top: 3px;
            }
            QRadioButton {
                background-color: transparent;
                spacing: 3px;
            }
            QCheckBox {
                background-color: transparent;
            }
        """
        self.setStyleSheet(compact_input_style)
        
        # Rename options
        options_group = QGroupBox()
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(8, 6, 8, 6)
        options_layout.setSpacing(4)
        
        self.mode_group = QButtonGroup(self)
        
        # Replace text mode
        self.replace_mode = QRadioButton("Find and Replace")
        self.replace_mode.setChecked(True)
        self.mode_group.addButton(self.replace_mode, 0)
        options_layout.addWidget(self.replace_mode)
        
        replace_layout = QHBoxLayout()
        replace_layout.setContentsMargins(20, 1, 0, 1)
        replace_layout.setSpacing(6)
        find_label = QLabel("Find:")
        find_label.setMinimumWidth(80)
        replace_layout.addWidget(find_label)
        self.find_text = QLineEdit()
        self.find_text.setPlaceholderText("Text to find")
        replace_layout.addWidget(self.find_text)
        replace_with_label = QLabel("Replace with:")
        replace_with_label.setMinimumWidth(90)
        replace_layout.addWidget(replace_with_label)
        self.replace_text = QLineEdit()
        self.replace_text.setPlaceholderText("Replacement text")
        replace_layout.addWidget(self.replace_text)
        options_layout.addLayout(replace_layout)
        
        # Prefix/Suffix mode
        self.prefix_suffix_mode = QRadioButton("Add Prefix/Suffix")
        self.mode_group.addButton(self.prefix_suffix_mode, 1)
        options_layout.addWidget(self.prefix_suffix_mode)
        
        prefix_layout = QHBoxLayout()
        prefix_layout.setContentsMargins(20, 1, 0, 1)
        prefix_layout.setSpacing(6)
        prefix_label = QLabel("Prefix:")
        prefix_label.setMinimumWidth(80)
        prefix_layout.addWidget(prefix_label)
        self.prefix_text = QLineEdit()
        self.prefix_text.setPlaceholderText("Add to beginning")
        prefix_layout.addWidget(self.prefix_text)
        suffix_label = QLabel("Suffix:")
        suffix_label.setMinimumWidth(90)
        prefix_layout.addWidget(suffix_label)
        self.suffix_text = QLineEdit()
        self.suffix_text.setPlaceholderText("Add before extension")
        prefix_layout.addWidget(self.suffix_text)
        options_layout.addLayout(prefix_layout)
        
        # Number sequence mode
        self.number_mode = QRadioButton("Number Sequence")
        self.mode_group.addButton(self.number_mode, 2)
        options_layout.addWidget(self.number_mode)
        
        number_layout = QHBoxLayout()
        number_layout.setContentsMargins(20, 1, 0, 1)
        number_layout.setSpacing(6)
        base_label = QLabel("Base name:")
        base_label.setMinimumWidth(80)
        number_layout.addWidget(base_label)
        self.base_name = QLineEdit()
        self.base_name.setPlaceholderText("e.g., File")
        number_layout.addWidget(self.base_name)
        start_label = QLabel("Start number:")
        start_label.setMinimumWidth(90)
        number_layout.addWidget(start_label)
        self.start_number = QSpinBox()
        self.start_number.setRange(0, 9999)
        self.start_number.setValue(1)
        self.start_number.setMinimumWidth(80)
        self.start_number.setAlignment(Qt.AlignmentFlag.AlignRight)
        number_layout.addWidget(self.start_number)
        digits_label = QLabel("Digits:")
        digits_label.setMinimumWidth(50)
        number_layout.addWidget(digits_label)
        self.num_digits = QSpinBox()
        self.num_digits.setRange(1, 6)
        self.num_digits.setValue(3)
        self.num_digits.setMinimumWidth(70)
        self.num_digits.setAlignment(Qt.AlignmentFlag.AlignRight)
        number_layout.addWidget(self.num_digits)
        options_layout.addLayout(number_layout)
        
        # Case conversion
        self.case_mode = QRadioButton("Change Case")
        self.mode_group.addButton(self.case_mode, 3)
        options_layout.addWidget(self.case_mode)
        
        case_layout = QHBoxLayout()
        case_layout.setContentsMargins(20, 1, 0, 1)
        case_layout.setSpacing(6)
        case_label = QLabel("Convert to:")
        case_label.setMinimumWidth(80)
        case_layout.addWidget(case_label)
        self.case_combo = QComboBox()
        self.case_combo.addItems(["lowercase", "UPPERCASE", "Title Case", "Sentence case"])
        self.case_combo.setMinimumWidth(150)
        case_layout.addWidget(self.case_combo)
        case_layout.addStretch()
        options_layout.addLayout(case_layout)
        
        # Keep extension checkbox
        self.keep_extension_cb = QCheckBox("Keep original file extension")
        self.keep_extension_cb.setChecked(True)
        options_layout.addWidget(self.keep_extension_cb)
        
        layout.addWidget(options_group)
        
        # Preview button
        preview_btn = QPushButton("🔍 Update Preview")
        preview_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                padding: 4px 12px;
                border: none;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
        """)
        preview_btn.clicked.connect(self.update_preview)
        layout.addWidget(preview_btn)
        
        # Preview table
        preview_label = QLabel("<b>Preview:</b>")
        preview_label.setStyleSheet("padding: 2px;")
        layout.addWidget(preview_label)
        
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(3)
        self.preview_table.setHorizontalHeaderLabels(['Original Name', '→', 'New Name'])
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setColumnWidth(0, 300)
        self.preview_table.setColumnWidth(1, 30)
        self.preview_table.verticalHeader().setDefaultSectionSize(20)  # Compact rows
        layout.addWidget(self.preview_table)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                padding: 4px 16px;
                border: none;
                border-radius: 3px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
        """)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def update_preview(self):
        """Update preview table with new names"""
        self.preview_table.setRowCount(len(self.file_paths))
        
        for i, path in enumerate(self.file_paths):
            new_name = self.generate_new_name(path, i)
            
            # Original name
            orig_item = QTableWidgetItem(path.name)
            self.preview_table.setItem(i, 0, orig_item)
            
            # Arrow
            arrow_item = QTableWidgetItem("→")
            arrow_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.preview_table.setItem(i, 1, arrow_item)
            
            # New name
            new_item = QTableWidgetItem(new_name)
            if new_name != path.name:
                new_item.setForeground(Qt.GlobalColor.darkGreen)
                font = QFont()
                font.setBold(True)
                new_item.setFont(font)
            self.preview_table.setItem(i, 2, new_item)
    
    def generate_new_name(self, path, index):
        """Generate new name based on selected mode"""
        name = path.stem
        ext = path.suffix if self.keep_extension_cb.isChecked() else ""
        
        # Replace mode
        if self.replace_mode.isChecked():
            find = self.find_text.text()
            replace = self.replace_text.text()
            if find:
                name = name.replace(find, replace)
        
        # Prefix/Suffix mode
        elif self.prefix_suffix_mode.isChecked():
            prefix = self.prefix_text.text()
            suffix = self.suffix_text.text()
            name = f"{prefix}{name}{suffix}"
        
        # Number sequence mode
        elif self.number_mode.isChecked():
            base = self.base_name.text() or "File"
            start = self.start_number.value()
            digits = self.num_digits.value()
            number = str(start + index).zfill(digits)
            name = f"{base}_{number}"
        
        # Case mode
        elif self.case_mode.isChecked():
            case_type = self.case_combo.currentText()
            if case_type == "lowercase":
                name = name.lower()
            elif case_type == "UPPERCASE":
                name = name.upper()
            elif case_type == "Title Case":
                name = name.title()
            elif case_type == "Sentence case":
                name = name.capitalize()
        
        return name + ext
    
    def get_rename_map(self):
        """Get mapping of old path to new path"""
        rename_map = {}
        
        for i, path in enumerate(self.file_paths):
            new_name = self.generate_new_name(path, i)
            if new_name != path.name:
                new_path = path.parent / new_name
                rename_map[str(path)] = str(new_path)
        
        return rename_map
    
    def perform_rename(self):
        """Perform the actual rename operation"""
        rename_map = self.get_rename_map()
        
        if not rename_map:
            QMessageBox.information(self, "No Changes", "No files will be renamed with current settings")
            return False
        
        # Confirm
        reply = QMessageBox.question(
            self,
            "Confirm Batch Rename",
            f"Rename {len(rename_map)} files?\n\nThis operation cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return False
        
        # Perform renames
        success_count = 0
        errors = []
        
        for old_path, new_path in rename_map.items():
            try:
                Path(old_path).rename(new_path)
                success_count += 1
            except Exception as e:
                errors.append(f"{Path(old_path).name}: {str(e)}")
        
        # Show results
        if errors:
            error_msg = "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more errors"
            
            QMessageBox.warning(
                self,
                "Partial Success",
                f"✅ {success_count} files renamed successfully\n"
                f"❌ {len(errors)} files failed:\n\n{error_msg}"
            )
        else:
            QMessageBox.information(
                self,
                "Success",
                f"✅ Successfully renamed {success_count} files!"
            )
        
        return True
