"""
File Source browser — find, open, or delete saved File Sources.

Saved File Sources live in their own store (`file_source_store`), separate from
the QueryObject browser. This compact chooser lists them so a saved source can
be reopened for editing (add files, rename columns) instead of being a
write-once object. Returns the chosen source's id via :attr:`selected_id`.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from suiteview.audit import file_source_store
from suiteview.audit.file_source import datasource_label

_FONT = QFont("Segoe UI", 9)


class FileSourceBrowserDialog(QDialog):
    """Pick a saved File Source to open (or delete)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_id = ""
        self.setWindowTitle("Open File Source")
        self.setModal(True)
        self.resize(560, 420)
        self._build_ui()
        self._reload()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        self.setStyleSheet(
            "QDialog { background-color: #F0F0F0; }"
            "QLabel#title { color: #1E5BA8; font-size: 14pt; font-weight: bold; }"
            "QListWidget { background: white; border: 1px solid #9FB4CC; }"
            "QListWidget::item { padding: 4px 6px; }"
            "QListWidget::item:selected { background: #D9E8F7; color: #0A2A5C; }"
            "QPushButton { background: white; border: 1px solid #A0C4E8;"
            " border-radius: 3px; padding: 5px 12px; color: #111; }"
            "QPushButton:hover { background: #E8F0FB; border-color: #1E5BA8; }"
            "QPushButton:disabled { color: #9AA7B6; border-color: #CBD6E4; }"
        )

        title = QLabel("Open File Source")
        title.setObjectName("title")
        root.addWidget(title)

        self.list = QListWidget()
        self.list.setFont(_FONT)
        self.list.itemDoubleClicked.connect(lambda _i: self._open())
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        root.addWidget(self.list, 1)

        self.lbl_empty = QLabel("No saved File Sources yet.")
        self.lbl_empty.setStyleSheet("color: #6B7280; font-style: italic;")
        self.lbl_empty.setVisible(False)
        root.addWidget(self.lbl_empty)

        buttons = QHBoxLayout()
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self._delete)
        buttons.addWidget(self.btn_delete)
        buttons.addStretch()
        self.btn_open = QPushButton("Open")
        self.btn_open.setDefault(True)
        self.btn_open.clicked.connect(self._open)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        buttons.addWidget(btn_close)
        buttons.addWidget(self.btn_open)
        root.addLayout(buttons)

    def _reload(self):
        self.list.clear()
        sources = file_source_store.list_file_sources()
        for fds in sources:
            cols = len(fds.columns)
            files = len(fds.members)
            label = (f"{fds.name}  [{datasource_label(fds)}]"
                     f"      {files} file(s), {cols} column(s)")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, fds.id)
            if fds.description:
                item.setToolTip(fds.description)
            self.list.addItem(item)
        self.lbl_empty.setVisible(not sources)
        self.list.setVisible(bool(sources))
        if sources:
            self.list.setCurrentRow(0)
        self._update_buttons()

    def _current_id(self) -> str:
        item = self.list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else ""

    def _update_buttons(self):
        has_sel = bool(self._current_id())
        self.btn_open.setEnabled(has_sel)
        self.btn_delete.setEnabled(has_sel)

    def _open(self):
        source_id = self._current_id()
        if not source_id:
            return
        self.selected_id = source_id
        self.accept()

    def _delete(self):
        source_id = self._current_id()
        if not source_id:
            return
        item = self.list.currentItem()
        name = item.text().split("  [", 1)[0] if item else "this source"
        reply = QMessageBox.question(
            self, "Delete File Source",
            f"Delete the File Source “{name}”?\n\n"
            "This removes the source definition only — the underlying files are "
            "not touched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            file_source_store.delete_file_source_by_id(source_id)
            self._reload()
