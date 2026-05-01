"""
Save QDefinition dialog — lets the user enter a new name or pick
an existing QDef to overwrite, and choose the target DataForge.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QRadioButton, QButtonGroup,
)

from suiteview.audit import qdef_store
from suiteview.audit.dataforge import dataforge_store as df_store

_FONT = QFont("Segoe UI", 9)


class SaveQDefDialog(QDialog):
    """Dialog to save a QDefinition — new name or overwrite existing."""

    def __init__(self, suggested_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save QDefinition")
        self.setFixedSize(420, 260)
        self.setFont(_FONT)

        self._selected_name = ""
        self._selected_forge = ""
        self._build_ui(suggested_name)

    def _build_ui(self, suggested_name: str):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        # ── DataForge selector ───────────────────────────────────────
        forge_row = QHBoxLayout()
        forge_row.setSpacing(8)
        lbl_forge = QLabel("DataForge:")
        lbl_forge.setFont(_FONT)
        forge_row.addWidget(lbl_forge)

        self.cmb_forge = QComboBox()
        self.cmb_forge.setFont(_FONT)
        self.cmb_forge.setEditable(True)
        # Populate with existing forge names from store + any that have QDefs
        forge_names: set[str] = set()
        for f in df_store.list_forges():
            forge_names.add(f.name)
        for fn in qdef_store.list_forge_names():
            forge_names.add(fn)
        for fn in sorted(forge_names):
            self.cmb_forge.addItem(fn)
        self.cmb_forge.setCurrentText("")
        self.cmb_forge.lineEdit().setPlaceholderText("(leave blank for Commons)")
        self.cmb_forge.currentTextChanged.connect(self._on_forge_changed)
        forge_row.addWidget(self.cmb_forge, 1)
        root.addLayout(forge_row)

        # ── New name option ──────────────────────────────────────────
        self.rb_new = QRadioButton("Save as new:")
        self.rb_new.setChecked(True)
        self.rb_new.setFont(_FONT)
        root.addWidget(self.rb_new)

        self.txt_name = QLineEdit(suggested_name)
        self.txt_name.setFont(_FONT)
        self.txt_name.setPlaceholderText("Enter QDefinition name")
        root.addWidget(self.txt_name)

        # ── Overwrite option ─────────────────────────────────────────
        self.rb_overwrite = QRadioButton("Overwrite existing:")
        self.rb_overwrite.setFont(_FONT)
        root.addWidget(self.rb_overwrite)

        self.cmb_existing = QComboBox()
        self.cmb_existing.setFont(_FONT)
        self.cmb_existing.setEnabled(False)
        root.addWidget(self.cmb_existing)

        # Radio button group
        grp = QButtonGroup(self)
        grp.addButton(self.rb_new)
        grp.addButton(self.rb_overwrite)
        self.rb_new.toggled.connect(self._on_mode_changed)
        self.rb_overwrite.toggled.connect(self._on_mode_changed)

        root.addStretch()

        # ── Buttons ──────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFont(_FONT)
        btn_cancel.setFixedSize(80, 30)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Save")
        btn_save.setFont(_FONT)
        btn_save.setFixedSize(80, 30)
        btn_save.setStyleSheet(
            "QPushButton { background-color: #7C3AED; color: white;"
            " border: 1px solid #6D28D9; border-radius: 3px; }"
            "QPushButton:hover { background-color: #8B5CF6; }"
        )
        btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(btn_save)

        root.addLayout(btn_row)

        # Populate overwrite list for initial forge (if any)
        self._refresh_existing_list()

    def _on_forge_changed(self, text: str):
        self._refresh_existing_list()

    def _refresh_existing_list(self):
        forge = self.cmb_forge.currentText().strip()
        self.cmb_existing.clear()
        if forge:
            existing = qdef_store.list_qdefs(forge_name=forge)
        else:
            existing = qdef_store.list_qdefs()
        for qd in existing:
            self.cmb_existing.addItem(qd.name)
        has_existing = self.cmb_existing.count() > 0
        self.rb_overwrite.setEnabled(has_existing)
        if not has_existing and self.rb_overwrite.isChecked():
            self.rb_new.setChecked(True)

    def _on_mode_changed(self):
        self.txt_name.setEnabled(self.rb_new.isChecked())
        self.cmb_existing.setEnabled(self.rb_overwrite.isChecked())

    def _on_save(self):
        forge = self.cmb_forge.currentText().strip()
        # Empty forge → save to Commons
        if not forge:
            forge = ""
        self._selected_forge = forge

        if self.rb_new.isChecked():
            name = self.txt_name.text().strip()
            if not name:
                return
            self._selected_name = name
        else:
            self._selected_name = self.cmb_existing.currentText()
        self.accept()

    def selected_name(self) -> str:
        return self._selected_name

    def selected_forge(self) -> str:
        return self._selected_forge
