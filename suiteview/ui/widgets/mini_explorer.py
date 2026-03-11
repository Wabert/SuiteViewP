"""
Mini File Explorer Widget — Reusable component for file navigation and management.

This module provides a compact file explorer meant to be embedded in other tools.
It supports:
- Navigation (Home, Up, Double-click to enter)
- Pinned "Home" entries (optional)
- Drag-and-drop (via custom list widget classes)
- Context menus
"""

import os
import shutil
from typing import Optional, List, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QMenu,
    QStyledItemDelegate, QSizePolicy, QAbstractItemView,
    QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QMimeData
from PyQt6.QtGui import QColor, QDrag, QPixmap, QPainter, QFont

# Shared styles (could be imported, but for standalone usage keeping some here or relying on caller to style)
# We will use the styles from policy_support_tab as a base, effectively copying them to keep this self-contained
# or we could import if they were in a shared styles file.
# For now, I'll copy the relevant style constants to ensure it looks right.

WHITE = "#FFFFFF"
GRAY_DARK = "#333333"
GRAY_MID = "#A0A0A0"
GRAY_LIGHT = "#E0E0E0"
GREEN_DARK = "#004d40"
GREEN_PRIMARY = "#00796b"
GREEN_SUBTLE = "#e0f2f1"
GOLD_PRIMARY = "#ffb300"
GOLD_TEXT = "#ff6f00"
GOLD_DARK = "#ff6f00"
GOLD_LIGHT = "#ffecb3"

POLICY_INFO_FRAME_STYLE = f"""
    QGroupBox {{
        font-weight: bold;
        border: 1px solid {GREEN_PRIMARY};
        border-radius: 6px;
        margin-top: 24px;
        background-color: {WHITE};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 4px;
        color: {GREEN_DARK};
    }}
"""

_CONTEXT_MENU_STYLE = f"""
    QMenu {{
        background-color: #F0F0F0;
        border: 1px solid {GRAY_DARK};
        padding: 2px;
        font-size: 11px;
    }}
    QMenu::item {{ padding: 3px 20px 3px 8px; color: #1a1a1a; }}
    QMenu::item:selected {{ background-color: {GOLD_LIGHT}; color: {GREEN_DARK}; }}
    QMenu::item:disabled {{ color: #999999; }}
    QMenu::separator {{ height: 1px; background: {GRAY_MID}; margin: 2px 4px; }}
"""

_LIST_STYLE = f"""
    QListWidget {{
        font-size: 11px;
        border: none;
        background-color: {WHITE};
        outline: none;
        padding: 0px;
        margin: 0px;
    }}
    QListWidget::item {{
        padding: 0px 4px;
        margin: 0px;
        border: none;
        min-height: 0px;
    }}
    QListWidget::item:hover   {{ background-color: {GREEN_SUBTLE}; }}
    QListWidget::item:selected {{ background-color: {GOLD_LIGHT}; color: {GREEN_DARK}; font-weight: bold; }}
"""

_NAV_BTN_STYLE = f"""
    QPushButton {{
        background: {GREEN_SUBTLE};
        color: {GREEN_DARK};
        border: 1px solid {GREEN_PRIMARY};
        border-radius: 3px;
        padding: 1px 5px;
        font-size: 11px;
        font-weight: bold;
        min-height: 16px;
        max-height: 18px;
    }}
    QPushButton:hover {{ background: {GREEN_PRIMARY}; color: {WHITE}; }}
    QPushButton:disabled {{ background: {GRAY_LIGHT}; color: {GRAY_MID}; border-color: {GRAY_MID}; }}
"""

_PATH_BAR_STYLE = f"""
    font-size: 10px;
    color: {GREEN_DARK};
    background: {GREEN_SUBTLE};
    border: 1px solid {GREEN_PRIMARY};
    border-radius: 3px;
    padding: 1px 4px;
"""

# Mime types
_MIME_CATEGORY = "application/x-suiteview-category"
_MIME_TOOL_FILE = "application/x-suiteview-toolfile"


def _icon_for_ext(ext: str) -> str:
    return {
        ".py": "🐍", ".r": "📊", ".R": "📊",
        ".xlsx": "📗", ".xls": "📗", ".xlsm": "📗",
        ".sql": "🗃️", ".vbs": "⚙️", ".bat": "⚙️", ".ps1": "⚙️",
        ".txt": "📝", ".pdf": "📕", ".docx": "📘",
    }.get(ext, "📄")


class TightItemDelegate(QStyledItemDelegate):
    ROW_H = 16
    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self.ROW_H)


class DoubleClickablePathLabel(QLabel):
    """Path-bar label that opens its associated folder in Windows Explorer on double-click."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._open_path: str = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_open_path(self, path: str):
        """Set the full path that will be opened on double-click."""
        self._open_path = path
        if path:
            self.setToolTip(f"Double-click to open in Explorer:\n{path}")
        else:
            self.setToolTip("")

    def mouseDoubleClickEvent(self, event):
        path = self._open_path or self.text().strip()
        if path and os.path.isdir(path):
            os.startfile(path)
        super().mouseDoubleClickEvent(event)


class MiniExplorer(QWidget):
    """Compact file explorer with Home/Up navigation and path breadcrumb.

    The list widget passed in (via list_widget_class) is used so callers
    can supply a drag-enabled subclass.
    """

    file_selected = pyqtSignal(str)
    
    # Path role for storing full paths in list items
    PATH_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, title: str = "", root_path: str = "",
                 list_widget_class=None, parent=None):
        super().__init__(parent)
        self._root_path = root_path
        self._current_path = root_path
        self._title = title
        
        # Mode: "home" (showing pinned entries) or "folder" (browsing a directory)
        # If root_path is provided initially, we might start in folder mode, 
        # unless Home entries are set. 
        self._at_home = True if not root_path else False
        
        self._home_entries: list = [] # [(label, full_path), ...] for home view
        self._list_cls = list_widget_class or QListWidget
        self._setup_ui()
        
        # If a root path was given, refresh to show it
        if self._root_path:
            self._refresh()

    def _setup_ui(self):
        outer = QGroupBox(self._title)
        outer.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(2, 14, 2, 2)
        ol.setSpacing(2)

        # Nav bar
        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(2)

        self._home_btn = QPushButton("⌂")
        self._home_btn.setStyleSheet(_NAV_BTN_STYLE)
        self._home_btn.setFixedWidth(22)
        self._home_btn.setToolTip("Go home")
        self._home_btn.clicked.connect(self._go_home)

        self._up_btn = QPushButton("↑")
        self._up_btn.setStyleSheet(_NAV_BTN_STYLE)
        self._up_btn.setFixedWidth(22)
        self._up_btn.setToolTip("Go up one level")
        self._up_btn.clicked.connect(self._go_up)

        self._path_label = DoubleClickablePathLabel("")
        self._path_label.setStyleSheet(_PATH_BAR_STYLE)
        self._path_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        nav.addWidget(self._home_btn)
        nav.addWidget(self._up_btn)
        nav.addWidget(self._path_label, 1)
        ol.addLayout(nav)

        # List
        self._list = self._list_cls()
        self._list.setStyleSheet(_LIST_STYLE)
        self._list.setItemDelegate(TightItemDelegate(self._list))
        self._list.setUniformItemSizes(True)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        self._list.currentItemChanged.connect(self._on_sel_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        ol.addWidget(self._list, 1)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(outer)

    # -- Home entries (pinned folders) -------------------------------------

    def set_home_entries(self, entries: list):
        """Set the list of (label, full_path) tuples shown on the home screen."""
        self._home_entries = entries
        # If we were at home (or empty), refresh home
        if not self._current_path or self._at_home:
            self._go_home()

    # -- Navigation --------------------------------------------------------

    def set_root(self, path: str):
        """Set a new root path. 
        
        If path is empty, we go to 'Home' view (if entries exist) or just clear.
        If path is valid, we browse it.
        """
        self._root_path = path if path else ""
        if not path:
             # No root implies "Home" mode if we have entries
             self._go_home()
        else:
            self._current_path = path
            self._at_home = False
            self._refresh()

    def _go_home(self):
        if not self._home_entries and self._root_path:
             # If no special home entries, "Home" means the root path
             self._current_path = self._root_path
             self._at_home = False
        else:
            # Show pinned entries
            self._at_home = True
            self._current_path = ""
            
        self._refresh()

    @property
    def list_widget(self):
        return self._list

    def _go_up(self):
        """Navigate to the parent directory. Goes home only if already at a filesystem root."""
        if self._at_home:
            return
            
        # If we are at the root_path (and we have a root_path), we might want to go to special Home
        if self._root_path and os.path.normpath(self._current_path) == os.path.normpath(self._root_path):
            if self._home_entries:
                self._go_home()
            return # Already at root, can't go up further unless we have home entries

        if not self._current_path:
            self._go_home()
            return

        parent = os.path.dirname(self._current_path)
        # Check if we hit filesystem root
        if parent == self._current_path:
            if self._home_entries:
                self._go_home()
        else:
            self._current_path = parent
            self._refresh()

    def _on_double_click(self, item: QListWidgetItem):
        """Navigate into a folder (or do nothing for files — files are drag-only)."""
        path = item.data(self.PATH_ROLE)
        if path and os.path.isdir(path):
            self._at_home = False
            # If we were at home, this new path effectively becomes a temporary root if we wanted
            # but usually we just browse.
            self._current_path = path
            self._refresh()
        elif path and os.path.isfile(path):
            os.startfile(path)

    def _on_sel_changed(self, current: QListWidgetItem, _prev):
        if not current:
            return
        path = current.data(self.PATH_ROLE) or ""
        if os.path.isfile(path):
            self.file_selected.emit(path)

    def _on_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(_CONTEXT_MENU_STYLE)
        
        # Navigation actions
        can_go_up = False
        if not self._at_home:
             # Can go up if not at home. 
             # Be nuanced: if at root_path, can go up ONLY if there is a 'Home' screen to go to.
             if self._root_path and os.path.normpath(self._current_path) == os.path.normpath(self._root_path):
                 can_go_up = bool(self._home_entries)
             else:
                 can_go_up = True
                 
        up_act = menu.addAction("↑  Go Up")
        up_act.setEnabled(can_go_up)
        
        home_act = menu.addAction("⌂  Go Home")
        # Can go home if not currently at home
        home_act.setEnabled(not self._at_home)

        item = self._list.itemAt(pos)
        open_act = rename_act = delete_act = None
        entry_name = ""
        
        if item:
            path = item.data(self.PATH_ROLE) or ""
            entry_name = os.path.basename(path)
            if entry_name:
                menu.addSeparator()
                if os.path.isdir(path):
                    open_act = menu.addAction(f"Open in Explorer")
                else:
                    open_act = menu.addAction(f"Open '{entry_name}'")
                
                # Only allow rename/delete if we are browsing a real folder, not the pinned home
                if not self._at_home:
                    rename_act = menu.addAction(f"Rename '{entry_name}'...")
                    delete_act = menu.addAction(f"Delete '{entry_name}'")

        action = menu.exec(self._list.viewport().mapToGlobal(pos))
        if action is up_act:
            self._go_up()
        elif action is home_act:
            self._go_home()
        elif action is open_act and item:
            path = item.data(self.PATH_ROLE) or ""
            if os.path.exists(path):
                os.startfile(path)
        elif action is rename_act:
            self._rename_entry(item)
        elif action is delete_act:
            self._delete_entry(item)

    # -- Operations --------------------------------------------------------

    def _rename_entry(self, item: QListWidgetItem):
        path = item.data(self.PATH_ROLE) or ""
        old_name = os.path.basename(path)
        new_name, ok = QInputDialog.getText(
            self, "Rename", f"Rename '{old_name}' to:", text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_path = os.path.join(os.path.dirname(path), new_name.strip())
        if os.path.exists(new_path):
            QMessageBox.information(self, "Exists", f"'{new_name}' already exists.")
            return
        try:
            os.rename(path, new_path)
            self._refresh()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to rename:\n{e}")

    def _delete_entry(self, item: QListWidgetItem):
        path = item.data(self.PATH_ROLE) or ""
        name = os.path.basename(path)
        is_dir = os.path.isdir(path)
        kind = "folder" if is_dir else "file"
        reply = QMessageBox.question(
            self, f"Delete {kind.title()}",
            f"Permanently delete {kind} '{name}'?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if is_dir:
                shutil.rmtree(path)
            else:
                os.remove(path)
            self._refresh()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to delete:\n{e}")

    # -- Rendering ---------------------------------------------------------

    def _refresh(self):
        self._list.clear()
        
        # Enable nav buttons
        # Up button: Same logic as in context menu
        can_go_up = False
        if not self._at_home:
             if self._root_path and os.path.normpath(self._current_path) == os.path.normpath(self._root_path):
                 can_go_up = bool(self._home_entries)
             else:
                 can_go_up = True
                 
        self._up_btn.setEnabled(can_go_up)
        self._home_btn.setEnabled(not self._at_home)

        if self._at_home:
            self._path_label.setText("Home")
            self._path_label.set_open_path("")  # nothing to open at home
            for label, full_path in self._home_entries:
                exists = os.path.isdir(full_path)
                icon = "📁" if exists else "⚠️"
                item = QListWidgetItem(f"{icon}  {label}")
                item.setData(self.PATH_ROLE, full_path)
                if not exists:
                    item.setForeground(QColor(GRAY_MID))
                    item.setToolTip("Folder not found")
                self._list.addItem(item)
            return

        self._update_path_label()
        
        if not self._current_path or not os.path.isdir(self._current_path):
            # If path is invalid or empty (and not at home), show nothing
            return

        try:
            entries = sorted(
                os.listdir(self._current_path),
                key=lambda e: (
                    not os.path.isdir(os.path.join(self._current_path, e)),
                    e.lower()
                )
            )
            for entry in entries:
                full = os.path.join(self._current_path, entry)
                if os.path.isdir(full):
                    item = QListWidgetItem(f"📁  {entry}")
                else:
                    ext = os.path.splitext(entry)[1].lower()
                    item = QListWidgetItem(f"{_icon_for_ext(ext)}  {entry}")
                item.setData(self.PATH_ROLE, full)
                self._list.addItem(item)
        except Exception as e:
            self._list.addItem(QListWidgetItem(f"(Error: {e})"))

    def _update_path_label(self):
        if not self._current_path:
            self._path_label.setText("")
            self._path_label.set_open_path("")
            return
        
        # Try to show path relative to root if possible, or just last few segments
        if self._root_path and os.path.normpath(self._current_path).startswith(os.path.normpath(self._root_path)):
             try:
                rel = os.path.relpath(self._current_path, os.path.dirname(self._root_path))
                self._path_label.setText(rel)
             except ValueError:
                self._path_label.setText(self._current_path)
        else:
             # Fallback relative display
             try:
                 parts = self._current_path.replace("\\", "/").split("/")
                 rel = "\\".join(parts[-2:]) if len(parts) >= 2 else self._current_path
                 self._path_label.setText(rel)
             except Exception:
                 self._path_label.setText(self._current_path)
                 
        self._path_label.set_open_path(self._current_path)

    # -- Public helpers ----------------------------------------------------

    def current_path(self) -> str:
        return self._current_path if not self._at_home else ""

    def selected_file_path(self) -> str:
        item = self._list.currentItem()
        if not item:
            return ""
        path = item.data(self.PATH_ROLE) or ""
        return path if os.path.isfile(path) else ""

    def refresh(self):
        self._refresh()


# ---------------------------------------------------------------------------
# DraggableToolsList  — List with drag support (Source)
# ---------------------------------------------------------------------------

class DraggableToolsList(QListWidget):
    """QListWidget that starts a drag carrying a file path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        path = item.data(MiniExplorer.PATH_ROLE) or ""
        if not path or not os.path.isfile(path):
            return  # only drag files, not folders
        mime = QMimeData()
        mime.setData(_MIME_TOOL_FILE, path.encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        pix = QPixmap(200, 18)
        pix.fill(QColor(GOLD_LIGHT))
        painter = QPainter(pix)
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor(GREEN_DARK))
        painter.drawText(4, 13, os.path.basename(path))
        painter.end()
        drag.exec(Qt.DropAction.CopyAction)


# ---------------------------------------------------------------------------
# DropTargetSubfolderList  — List that accepts drops (Target + Source)
# ---------------------------------------------------------------------------

class DropTargetSubfolderList(QListWidget):
    """QListWidget that accepts drops and can also drag its own files."""

    category_dropped = pyqtSignal(str)   # category name
    file_dropped     = pyqtSignal(str)   # source file path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        # Internal move or copy from outside
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDropIndicatorShown(True)

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(_MIME_CATEGORY) or md.hasFormat(_MIME_TOOL_FILE):
            event.acceptProposedAction()
        else:
            # Maybe internal drag?
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(_MIME_CATEGORY) or md.hasFormat(_MIME_TOOL_FILE):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasFormat(_MIME_CATEGORY):
            name = bytes(md.data(_MIME_CATEGORY)).decode()
            self.category_dropped.emit(name)
            event.acceptProposedAction()
        elif md.hasFormat(_MIME_TOOL_FILE):
            path = bytes(md.data(_MIME_TOOL_FILE)).decode()
            self.file_dropped.emit(path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
            
    def startDrag(self, supportedActions):
        # Also allow dragging files OUT of this list (same as DraggableToolsList)
        item = self.currentItem()
        if not item:
            return
        path = item.data(MiniExplorer.PATH_ROLE) or ""
        if not path or not os.path.isfile(path):
            return
        mime = QMimeData()
        mime.setData(_MIME_TOOL_FILE, path.encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        pix = QPixmap(200, 18)
        pix.fill(QColor(GOLD_LIGHT))
        painter = QPainter(pix)
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor(GREEN_DARK))
        painter.drawText(4, 13, os.path.basename(path))
        painter.end()
        drag.exec(Qt.DropAction.CopyAction)
