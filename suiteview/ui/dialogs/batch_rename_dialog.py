"""
Batch Rename Dialog - Rename multiple files with patterns
Uses FramelessWindowBase for consistent custom window frame.
"""

from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                              QMessageBox, QRadioButton,
                              QButtonGroup, QSpinBox, QComboBox, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal, QEventLoop
from PyQt6.QtGui import QFont

from suiteview.ui.widgets.frameless_window import FramelessWindowBase

import logging
logger = logging.getLogger(__name__)


# SuiteView blue theme (matches main app)
_HEADER_COLORS = ("#1E5BA8", "#0D3A7A", "#082B5C")
_BORDER_COLOR = "#D4A017"


class BatchRenameDialog(FramelessWindowBase):
    """Dialog for batch renaming files"""

    rename_completed = pyqtSignal()  # emitted after successful rename

    def __init__(self, file_paths, parent=None):
        self.file_paths = [Path(p) for p in file_paths]
        self._accepted = False
        self._event_loop = None

        # Collect input widgets per mode for enable/disable
        self._mode_widgets = {}

        super().__init__(
            title=f"SuiteView:  Batch Rename — {len(self.file_paths)} Files",
            default_size=(780, 520),
            min_size=(600, 400),
            parent=parent,
            header_colors=_HEADER_COLORS,
            border_color=_BORDER_COLOR,
        )

        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._on_mode_changed(0)
        self.update_preview()

    def build_content(self) -> QWidget:
        """Build the body widget below the title bar."""
        body = QWidget()
        body.setStyleSheet("""
            QWidget { background-color: white; }
            QLineEdit, QSpinBox, QComboBox {
                padding: 2px 5px; margin: 0px; height: 22px;
                background-color: white; color: black;
                border: 1px solid #A0A0A0; border-radius: 2px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border: 1px solid #0078d4;
            }
            QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {
                background-color: #F0F0F0; color: #999999;
            }
            QSpinBox { padding-right: 18px; }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 16px; background-color: #E0E0E0; border: 1px solid #A0A0A0;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: #C8DCF0; }
            QSpinBox::up-arrow {
                image: none; width: 0; height: 0;
                border-left: 4px solid transparent; border-right: 4px solid transparent;
                border-bottom: 5px solid #404040;
            }
            QSpinBox::down-arrow {
                image: none; width: 0; height: 0;
                border-left: 4px solid transparent; border-right: 4px solid transparent;
                border-top: 5px solid #404040;
            }
            QLabel { color: black; background-color: transparent; }
            QRadioButton { background-color: transparent; spacing: 3px; color: black; }
            QRadioButton:disabled { color: #999999; }
            QCheckBox { background-color: transparent; color: black; }
        """)

        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 6, 8, 4)
        layout.setSpacing(2)

        self.mode_group = QButtonGroup(self)

        # ── Mode 0: Find and Replace ──
        self.replace_mode = QRadioButton("Find and Replace")
        self.replace_mode.setChecked(True)
        self.mode_group.addButton(self.replace_mode, 0)
        layout.addWidget(self.replace_mode)

        replace_row = QHBoxLayout()
        replace_row.setContentsMargins(22, 0, 0, 2)
        replace_row.setSpacing(6)
        replace_row.addWidget(QLabel("Find:"))
        self.find_text = QLineEdit()
        self.find_text.setPlaceholderText("Text to find")
        replace_row.addWidget(self.find_text)
        replace_row.addWidget(QLabel("Replace with:"))
        self.replace_text = QLineEdit()
        self.replace_text.setPlaceholderText("Replacement text")
        replace_row.addWidget(self.replace_text)
        layout.addLayout(replace_row)
        self._mode_widgets[0] = [self.find_text, self.replace_text]

        # ── Mode 1: Add Prefix/Suffix ──
        self.prefix_suffix_mode = QRadioButton("Add Prefix/Suffix")
        self.mode_group.addButton(self.prefix_suffix_mode, 1)
        layout.addWidget(self.prefix_suffix_mode)

        prefix_row = QHBoxLayout()
        prefix_row.setContentsMargins(22, 0, 0, 2)
        prefix_row.setSpacing(6)
        prefix_row.addWidget(QLabel("Prefix:"))
        self.prefix_text = QLineEdit()
        self.prefix_text.setPlaceholderText("Add to beginning")
        prefix_row.addWidget(self.prefix_text)
        suffix_lbl = QLabel("Suffix:")
        prefix_row.addWidget(suffix_lbl)
        self.suffix_text = QLineEdit()
        self.suffix_text.setPlaceholderText("Add before extension")
        prefix_row.addWidget(self.suffix_text)
        layout.addLayout(prefix_row)
        self._mode_widgets[1] = [self.prefix_text, self.suffix_text]

        # ── Mode 2: Number Sequence ──
        self.number_mode = QRadioButton("Number Sequence")
        self.mode_group.addButton(self.number_mode, 2)
        layout.addWidget(self.number_mode)

        number_row = QHBoxLayout()
        number_row.setContentsMargins(22, 0, 0, 2)
        number_row.setSpacing(6)
        number_row.addWidget(QLabel("Base name:"))
        self.base_name = QLineEdit()
        self.base_name.setPlaceholderText("e.g., File")
        number_row.addWidget(self.base_name)
        number_row.addWidget(QLabel("Start number:"))
        self.start_number = QSpinBox()
        self.start_number.setRange(0, 9999)
        self.start_number.setValue(1)
        self.start_number.setFixedWidth(70)
        self.start_number.setAlignment(Qt.AlignmentFlag.AlignRight)
        number_row.addWidget(self.start_number)
        number_row.addWidget(QLabel("Digits:"))
        self.num_digits = QSpinBox()
        self.num_digits.setRange(1, 6)
        self.num_digits.setValue(3)
        self.num_digits.setFixedWidth(55)
        self.num_digits.setAlignment(Qt.AlignmentFlag.AlignRight)
        number_row.addWidget(self.num_digits)
        layout.addLayout(number_row)
        self._mode_widgets[2] = [self.base_name, self.start_number, self.num_digits]

        # ── Mode 3: Change Case ──
        self.case_mode = QRadioButton("Change Case")
        self.mode_group.addButton(self.case_mode, 3)
        layout.addWidget(self.case_mode)

        case_row = QHBoxLayout()
        case_row.setContentsMargins(22, 0, 0, 2)
        case_row.setSpacing(6)
        case_row.addWidget(QLabel("Convert to:"))
        self.case_combo = QComboBox()
        self.case_combo.addItems(["lowercase", "UPPERCASE", "Title Case", "Sentence case"])
        self.case_combo.setFixedWidth(140)
        case_row.addWidget(self.case_combo)
        case_row.addStretch()
        layout.addLayout(case_row)
        self._mode_widgets[3] = [self.case_combo]

        # Connect mode toggle for enable/disable
        self.mode_group.idToggled.connect(self._on_mode_changed)

        # ── Keep extension ──
        self.keep_extension_cb = QCheckBox("Keep original file extension")
        self.keep_extension_cb.setChecked(True)
        keep_row = QHBoxLayout()
        keep_row.setContentsMargins(4, 2, 0, 0)
        keep_row.addWidget(self.keep_extension_cb)
        layout.addLayout(keep_row)

        # ── Preview button ──
        preview_btn = QPushButton("Update Preview")
        preview_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4; color: white;
                padding: 3px 14px; border: none; border-radius: 3px;
                font-weight: bold; font-size: 11px;
            }
            QPushButton:hover { background-color: #005a9e; }
        """)
        preview_btn.clicked.connect(self.update_preview)
        layout.addWidget(preview_btn)

        # ── Preview label ──
        preview_label = QLabel("<b>Preview:</b>")
        preview_label.setStyleSheet("padding: 1px 0px;")
        layout.addWidget(preview_label)

        # ── Preview table ──
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(3)
        self.preview_table.setHorizontalHeaderLabels(["Original Name", "→", "New Name"])
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setColumnWidth(0, 300)
        self.preview_table.setColumnWidth(1, 30)
        self.preview_table.verticalHeader().setDefaultSectionSize(20)
        self.preview_table.setStyleSheet("""
            QTableWidget { border: 1px solid #CCCCCC; gridline-color: #E8E8E8; }
            QHeaderView::section {
                background-color: #F0F0F0; border: 1px solid #D0D0D0;
                padding: 2px 4px; font-weight: bold; font-size: 11px;
            }
        """)
        layout.addWidget(self.preview_table, 1)

        # ── OK / Cancel buttons ──
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 2)
        btn_row.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4; color: white;
                padding: 4px 16px; border: none; border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #005a9e; }
        """)
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(80)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4; color: white;
                padding: 4px 16px; border: none; border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #005a9e; }
        """)
        cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        return body

    # ── Mode enable/disable ──────────────────────────────────────────

    def _on_mode_changed(self, mode_id, checked=True):
        """Enable only the input widgets for the active mode."""
        if not checked:
            return
        for mid, widgets in self._mode_widgets.items():
            enabled = (mid == mode_id)
            for w in widgets:
                w.setEnabled(enabled)
    
    # ── Modal exec compatibility ────────────────────────────────────

    def exec(self):
        """Block like QDialog.exec() — returns 1 (accepted) or 0 (rejected)."""
        self._event_loop = QEventLoop()
        self.show()
        self._event_loop.exec()
        return 1 if self._accepted else 0

    def _on_ok(self):
        self._accepted = True
        self.close()

    def _on_cancel(self):
        self._accepted = False
        self.close()

    def closeEvent(self, event):
        if self._event_loop and self._event_loop.isRunning():
            self._event_loop.quit()
        super().closeEvent(event)

    # ── Preview ──────────────────────────────────────────────────────

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
