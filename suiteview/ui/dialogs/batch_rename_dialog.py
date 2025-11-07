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
        
        # Info
        info_label = QLabel(f"<b>Renaming {len(self.file_paths)} files</b>")
        info_label.setStyleSheet("font-size: 11pt; padding: 5px;")
        layout.addWidget(info_label)
        
        # Rename options
        options_group = QGroupBox("Rename Options")
        options_layout = QVBoxLayout(options_group)
        
        # Mode selection
        mode_label = QLabel("<b>Rename Mode:</b>")
        options_layout.addWidget(mode_label)
        
        self.mode_group = QButtonGroup(self)
        
        # Replace text mode
        self.replace_mode = QRadioButton("Find and Replace")
        self.replace_mode.setChecked(True)
        self.mode_group.addButton(self.replace_mode, 0)
        options_layout.addWidget(self.replace_mode)
        
        replace_layout = QHBoxLayout()
        replace_layout.addSpacing(20)
        replace_layout.addWidget(QLabel("Find:"))
        self.find_text = QLineEdit()
        self.find_text.setPlaceholderText("Text to find")
        replace_layout.addWidget(self.find_text)
        replace_layout.addWidget(QLabel("Replace with:"))
        self.replace_text = QLineEdit()
        self.replace_text.setPlaceholderText("Replacement text")
        replace_layout.addWidget(self.replace_text)
        options_layout.addLayout(replace_layout)
        
        # Prefix/Suffix mode
        self.prefix_suffix_mode = QRadioButton("Add Prefix/Suffix")
        self.mode_group.addButton(self.prefix_suffix_mode, 1)
        options_layout.addWidget(self.prefix_suffix_mode)
        
        prefix_layout = QHBoxLayout()
        prefix_layout.addSpacing(20)
        prefix_layout.addWidget(QLabel("Prefix:"))
        self.prefix_text = QLineEdit()
        self.prefix_text.setPlaceholderText("Add to beginning")
        prefix_layout.addWidget(self.prefix_text)
        prefix_layout.addWidget(QLabel("Suffix:"))
        self.suffix_text = QLineEdit()
        self.suffix_text.setPlaceholderText("Add before extension")
        prefix_layout.addWidget(self.suffix_text)
        options_layout.addLayout(prefix_layout)
        
        # Number sequence mode
        self.number_mode = QRadioButton("Number Sequence")
        self.mode_group.addButton(self.number_mode, 2)
        options_layout.addWidget(self.number_mode)
        
        number_layout = QHBoxLayout()
        number_layout.addSpacing(20)
        number_layout.addWidget(QLabel("Base name:"))
        self.base_name = QLineEdit()
        self.base_name.setPlaceholderText("e.g., File")
        number_layout.addWidget(self.base_name)
        number_layout.addWidget(QLabel("Start number:"))
        self.start_number = QSpinBox()
        self.start_number.setRange(0, 9999)
        self.start_number.setValue(1)
        number_layout.addWidget(self.start_number)
        number_layout.addWidget(QLabel("Digits:"))
        self.num_digits = QSpinBox()
        self.num_digits.setRange(1, 6)
        self.num_digits.setValue(3)
        number_layout.addWidget(self.num_digits)
        options_layout.addLayout(number_layout)
        
        # Case conversion
        self.case_mode = QRadioButton("Change Case")
        self.mode_group.addButton(self.case_mode, 3)
        options_layout.addWidget(self.case_mode)
        
        case_layout = QHBoxLayout()
        case_layout.addSpacing(20)
        case_layout.addWidget(QLabel("Convert to:"))
        self.case_combo = QComboBox()
        self.case_combo.addItems(["lowercase", "UPPERCASE", "Title Case", "Sentence case"])
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
        preview_btn.clicked.connect(self.update_preview)
        layout.addWidget(preview_btn)
        
        # Preview table
        preview_label = QLabel("<b>Preview:</b>")
        layout.addWidget(preview_label)
        
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(3)
        self.preview_table.setHorizontalHeaderLabels(['Original Name', '→', 'New Name'])
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setColumnWidth(0, 300)
        self.preview_table.setColumnWidth(1, 30)
        layout.addWidget(self.preview_table)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
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
