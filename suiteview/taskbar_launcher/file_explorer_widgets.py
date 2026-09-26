"""Small taskbar launcher widgets used by FileNav."""

import ctypes
import logging
import os
import subprocess
import sys
import time
import traceback
import webbrowser
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QStandardItemModel,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSizePolicy,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from suiteview import __version__ as APP_VERSION
from suiteview.core.access_control import (
    AccessDeniedError,
    AccessUnavailableError,
    can_access_app,
    get_access,
    guard_app_access,
    requires_app_access,
)
from suiteview.core.profile_paths import profile_path, profile_root
from suiteview.file_nav.file_explorer_core import DropTreeView, FileExplorerCore, NoFocusDelegate
from suiteview.file_nav.sharepoint_client import is_sp_path
from suiteview.scratchpad.scratchpad_panel import ScratchPadPanel
from suiteview.taskbar_launcher import appbar
from suiteview.taskbar_launcher.albert_launcher import AlbertButton
from suiteview.taskbar_launcher.single_instance import activation_message
from suiteview.ui.dialogs.shortcuts_dialog import AddBookmarkDialog
from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
from suiteview.ui.widgets.bookmark_widgets import (
    BookmarkContainer,
    BookmarkContainerRegistry,
    CATEGORY_CONTEXT_MENU_STYLE,
    CategoryButton,
    CategoryPopup,
    StandaloneBookmarkButton,
    set_footer_status_callback,
)
from suiteview.ui.widgets.file_open_history import FileOpenHistoryPanel
from suiteview.ui.widgets.frame_geometry import (
    ALL_RESIZE_EDGES,
    cursor_for_resize_edge,
    resize_edge_at,
    resize_geometry_for_edge,
    update_cursor_for_resize_edge,
)
from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.ui.widgets.uppercase_input import force_uppercase
from suiteview.ui.widgets.window_state import NativeMinimizeMixin
from suiteview.administrator.launcher import AdministratorMenuAccess

logger = logging.getLogger(__name__)

class NavigableTreeView(DropTreeView):
    """Custom QTreeView that emits signals for back/forward mouse buttons and supports file drops"""
    
    back_button_clicked = pyqtSignal()
    forward_button_clicked = pyqtSignal()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Override to catch back/forward mouse buttons"""
        if event.button() == Qt.MouseButton.XButton1:
            self.back_button_clicked.emit()
            event.accept()
            return
        elif event.button() == Qt.MouseButton.XButton2:
            self.forward_button_clicked.emit()
            event.accept()
            return
        
        # Pass other events to parent
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Override to handle double-clicks"""
        super().mouseDoubleClickEvent(event)


class ClickableBreadcrumb(QWidget):
    """Breadcrumb widget with clickable path segments"""
    
    path_clicked = pyqtSignal(str)  # Emits path when segment is clicked
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_path = ""
        self.is_edit_mode = False
        
        # Main layout
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Breadcrumb display widget (shows clickable segments)
        self.breadcrumb_display = QWidget()
        self.breadcrumb_display.setStyleSheet("background-color: #FFFDE7;")
        self.breadcrumb_layout = QHBoxLayout(self.breadcrumb_display)
        self.breadcrumb_layout.setContentsMargins(2, 0, 2, 0)
        self.breadcrumb_layout.setSpacing(0)
        self.breadcrumb_layout.addStretch()
        
        # Text input for editing (hidden by default)
        self.path_input = QLineEdit()
        self.path_input.setStyleSheet("""
            QLineEdit {
                background-color: #FFFDE7;
                border: 1px solid #ced4da;
                border-radius: 2px;
                padding: 2px 6px;
                font-family: Segoe UI;
                font-size: 9pt;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """)
        self.path_input.hide()
        self.path_input.returnPressed.connect(self.finish_editing)
        self.path_input.installEventFilter(self)
        
        self.layout.addWidget(self.breadcrumb_display)
        self.layout.addWidget(self.path_input)
        
        self.setStyleSheet("""
            ClickableBreadcrumb {
                background-color: #FFFDE7;
                border: 2px solid #6B8DC9;
                border-radius: 3px;
                padding: 1px;
            }
            ClickableBreadcrumb:hover {
                border-color: #2563EB;
            }
        """)
    
    def eventFilter(self, obj, event):
        """Handle events for path input"""
        if obj == self.path_input and event.type() == QEvent.Type.FocusOut:
            self.finish_editing()
        return super().eventFilter(obj, event)
    
    def mousePressEvent(self, event):
        """Switch to edit mode when clicking on breadcrumb"""
        if not self.is_edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self.enter_edit_mode()
    
    def enter_edit_mode(self):
        """Switch to editable text input"""
        self.is_edit_mode = True
        self.breadcrumb_display.hide()
        self.path_input.setText(self.current_path)
        self.path_input.show()
        self.path_input.setFocus()
        self.path_input.selectAll()
    
    def finish_editing(self):
        """Finish editing and emit signal if path changed"""
        if self.is_edit_mode:
            new_path = self.path_input.text().strip()
            if new_path and new_path != self.current_path:
                if Path(new_path).exists():
                    self.path_clicked.emit(new_path)
            
            self.is_edit_mode = False
            self.path_input.hide()
            self.breadcrumb_display.show()
    
    def set_path(self, path):
        """Update the breadcrumb with a new path"""
        self.current_path = str(path)
        self.update_display()
    
    def update_display(self):
        """Update the breadcrumb display with clickable segments"""
        # Clear existing widgets
        while self.breadcrumb_layout.count() > 1:  # Keep the stretch
            item = self.breadcrumb_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.current_path:
            return
        
        try:
            path_obj = Path(self.current_path)
            
            # Build path segments
            parts = path_obj.parts
            
            for i, part in enumerate(parts):
                # Create button for this segment
                btn = QPushButton(part)
                btn.setFlat(True)
                btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FFFDE7;
                        border: none;
                        padding: 2px 6px;
                        text-align: left;
                        font-family: Segoe UI;
                        font-size: 9pt;
                        font-weight: bold;
                        color: #0066cc;
                    }
                    QPushButton:hover {
                        background-color: #FFFDE7;
                        text-decoration: underline;
                    }
                """)
                
                # Build the full path up to this segment
                segment_path = Path(*parts[:i+1])
                btn.clicked.connect(lambda checked, p=str(segment_path): self.path_clicked.emit(p))
                
                self.breadcrumb_layout.insertWidget(self.breadcrumb_layout.count() - 1, btn)
                
                # Add separator (except after last item)
                if i < len(parts) - 1:
                    separator = QLabel(" > ")
                    separator.setStyleSheet("color: #6c757d; font-size: 9pt;")
                    self.breadcrumb_layout.insertWidget(self.breadcrumb_layout.count() - 1, separator)
        
        except Exception as e:
            logger.error(f"Failed to update breadcrumb display: {e}")
