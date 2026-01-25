"""
Unified Bookmark Widgets for SuiteView

This module provides shared bookmark and category widgets used by both:
- Top bookmark bar (shortcuts_dialog.py / BookmarkBar)
- Quick Links sidebar (file_explorer_multitab.py)

Classes:
- CategoryButton: Draggable category button with popup support
- CategoryPopup: Popup window showing category contents
- CategoryBookmarkButton: Bookmark button inside category popups
- BookmarkButton: Standalone bookmark button (for bar or sidebar)
"""

import json
import logging
import os
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QFrame, QVBoxLayout, QHBoxLayout,
    QScrollArea, QMenu, QInputDialog, QMessageBox, QLineEdit,
    QFileIconProvider, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QFileInfo, QTimer, QEventLoop, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QAction, QDrag, QCursor, QIcon, QPixmap

logger = logging.getLogger(__name__)


# Shared icon provider and cache for all bookmark widgets
_icon_provider = None
_icon_cache = {}  # Cache by extension for files
_path_cache = {}  # Cache full results by path for folders
_folder_icon = None
_file_icon = None
_db_icons_loaded = False  # Track if DB icons have been loaded


def _get_icon_provider():
    """Get or create the shared QFileIconProvider"""
    global _icon_provider, _folder_icon, _file_icon
    if _icon_provider is None:
        _icon_provider = QFileIconProvider()
        _folder_icon = _icon_provider.icon(QFileIconProvider.IconType.Folder)
        _file_icon = _icon_provider.icon(QFileIconProvider.IconType.File)
    return _icon_provider


def _is_url(path_str):
    """Check if a path is a URL (http/https)"""
    if not path_str:
        return False
    lower = path_str.lower()
    return lower.startswith('http://') or lower.startswith('https://')


def get_file_icon_placeholder(path_str):
    """
    Get a placeholder icon instantly - no filesystem access.
    Returns (icon, needs_async_load) tuple.
    For .lnk files, returns generic file icon and True.
    For other files, tries extension cache first.
    """
    global _icon_cache, _path_cache, _folder_icon, _file_icon
    
    _get_icon_provider()  # Ensure icons are initialized
    
    if not path_str:
        return None, False
    
    # URLs get no icon (will use emoji in text)
    if _is_url(path_str):
        return None, False
    
    # Check full path cache first
    if path_str in _path_cache:
        return _path_cache[path_str], False
    
    # Quick check for folder paths
    if path_str.endswith('/') or path_str.endswith('\\'):
        _path_cache[path_str] = _folder_icon
        return _folder_icon, False
    
    path_obj = Path(path_str)
    suffix = path_obj.suffix.lower()
    
    if suffix:
        # .lnk files need async loading - return placeholder
        if suffix == '.lnk':
            return _file_icon, True  # Needs async load
        
        # Regular files - check extension cache
        if suffix in _icon_cache:
            return _icon_cache[suffix], False
        
        # Extension not cached - needs async load
        return _file_icon, True
    
    # No extension - folder check needs filesystem
    return _file_icon, True


def get_file_icon(path_str, save_to_db=True):
    """
    Get the real system icon for a file or folder path.
    Returns QIcon or None for URLs.
    Uses aggressive caching to avoid slow filesystem calls.
    
    Args:
        path_str: File or folder path
        save_to_db: If True, saves newly fetched icons to database for instant loading
    """
    global _icon_cache, _path_cache, _folder_icon, _file_icon
    
    if not path_str:
        return None
    
    # URLs get no icon (will use globe emoji in text)
    if _is_url(path_str):
        return None
    
    # Check full path cache first (loaded from DB at startup)
    if path_str in _path_cache:
        return _path_cache[path_str]
    
    provider = _get_icon_provider()
    
    # Quick check: if path has no extension and ends with slash or backslash, it's a folder
    if path_str.endswith('/') or path_str.endswith('\\'):
        _path_cache[path_str] = _folder_icon
        if save_to_db:
            try:
                save_icon_to_db(path_str, _folder_icon, 'folder')
            except:
                pass
        return _folder_icon
    
    # Check extension - if it has one, treat it as a file
    path_obj = Path(path_str)
    suffix = path_obj.suffix.lower()
    
    if suffix:
        # Special handling for .lnk files - they need full path caching
        # because each shortcut can point to different file types
        if suffix == '.lnk':
            try:
                file_info = QFileInfo(path_str)
                icon = provider.icon(file_info)
                if not icon.isNull():
                    _path_cache[path_str] = icon  # Cache by full path
                    if save_to_db:
                        try:
                            save_icon_to_db(path_str, icon, 'lnk')
                        except:
                            pass
                    return icon
            except:
                pass
            # Fallback - use generic file icon
            _path_cache[path_str] = _file_icon
            return _file_icon
        
        # Regular files - check extension cache first (fast path)
        if suffix in _icon_cache:
            # Also cache by full path for DB storage
            icon = _icon_cache[suffix]
            _path_cache[path_str] = icon
            if save_to_db:
                try:
                    save_icon_to_db(path_str, icon, 'file')
                except:
                    pass
            return icon
        
        # Get icon for this extension (QFileInfo doesn't need the file to exist)
        try:
            file_info = QFileInfo(path_str)
            icon = provider.icon(file_info)
            if not icon.isNull():
                _icon_cache[suffix] = icon
                _path_cache[path_str] = icon
                if save_to_db:
                    try:
                        save_icon_to_db(path_str, icon, 'file')
                    except:
                        pass
                return icon
        except:
            pass
        
        # Fallback to generic file icon
        _icon_cache[suffix] = _file_icon
        _path_cache[path_str] = _file_icon
        return _file_icon
    
    # No extension - need to check if it's a folder (this is the slow path)
    # Only do filesystem check when absolutely necessary
    try:
        if path_obj.is_dir():
            _path_cache[path_str] = _folder_icon
            if save_to_db:
                try:
                    save_icon_to_db(path_str, _folder_icon, 'folder')
                except:
                    pass
            return _folder_icon
    except:
        pass
    
    # Default to file icon for extensionless items
    _path_cache[path_str] = _file_icon
    return _file_icon


# =============================================================================
# Database Icon Caching - Pre-cache icons to DB for instant loading
# =============================================================================

def _get_db():
    """Get database connection (lazy import to avoid circular deps)"""
    from suiteview.data.database import get_database
    return get_database()


def save_icon_to_db(path_str: str, icon: QIcon, icon_type: str = "file"):
    """
    Save a QIcon to the database as PNG data.
    icon_type: 'file', 'folder', 'lnk', or 'url'
    """
    if icon is None or icon.isNull():
        return
    
    try:
        # Get a reasonably sized pixmap (32x32 is good for menus/lists)
        pixmap = icon.pixmap(32, 32)
        if pixmap.isNull():
            return
        
        # Convert to PNG bytes
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, "PNG")
        buffer.close()
        
        icon_data = bytes(byte_array.data())
        
        # Save to database
        db = _get_db()
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO bookmark_icons (path, icon_data, icon_type, last_updated)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (path_str, icon_data, icon_type))
        conn.commit()
        
        logger.debug(f"Saved icon to DB for: {path_str}")
    except Exception as e:
        logger.warning(f"Failed to save icon to DB: {e}")


def load_icon_from_db(path_str: str) -> QIcon:
    """
    Load a QIcon from the database.
    Returns None if not found or on error.
    """
    try:
        db = _get_db()
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT icon_data FROM bookmark_icons WHERE path = ?", (path_str,))
        row = cursor.fetchone()
        
        if row and row[0]:
            # Convert bytes back to QIcon
            pixmap = QPixmap()
            pixmap.loadFromData(row[0])
            if not pixmap.isNull():
                return QIcon(pixmap)
    except Exception as e:
        logger.warning(f"Failed to load icon from DB: {e}")
    
    return None


def load_all_icons_from_db():
    """
    Bulk load all cached icons from database into _path_cache.
    Call this at startup for instant icon loading.
    """
    global _path_cache, _db_icons_loaded
    
    if _db_icons_loaded:
        return 0  # Already loaded
    
    try:
        db = _get_db()
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT path, icon_data FROM bookmark_icons")
        rows = cursor.fetchall()
        
        loaded_count = 0
        for path, icon_data in rows:
            if icon_data:
                pixmap = QPixmap()
                pixmap.loadFromData(icon_data)
                if not pixmap.isNull():
                    _path_cache[path] = QIcon(pixmap)
                    loaded_count += 1
        
        _db_icons_loaded = True
        logger.info(f"Loaded {loaded_count} icons from database cache")
        return loaded_count
    except Exception as e:
        logger.warning(f"Failed to load icons from DB: {e}")
        return 0


def ensure_icons_loaded():
    """
    Ensure icons are loaded from database.
    Call this before displaying any bookmark UI.
    Safe to call multiple times - will only load once.
    """
    global _db_icons_loaded
    if not _db_icons_loaded:
        load_all_icons_from_db()


def delete_icon_from_db(path_str: str):
    """Remove an icon from the database cache."""
    try:
        db = _get_db()
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bookmark_icons WHERE path = ?", (path_str,))
        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to delete icon from DB: {e}")


# =============================================================================
# Style Constants - Unified theming for all bookmark widgets
# =============================================================================

CATEGORY_BUTTON_STYLE = """
    QPushButton {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #E8D4F8, stop:1 #C9A8E8);
        border: 1px solid #A080C0;
        border-top-color: #D0B8E8;
        border-left-color: #D0B8E8;
        border-bottom-color: #8060A0;
        border-right-color: #8060A0;
        border-radius: 10px;
        padding: 3px 10px;
        text-align: left;
        font-size: 9pt;
        font-weight: normal;
        color: #202124;
    }
    QPushButton:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #DCC8F0, stop:1 #B898D8);
        border-color: #8060A0;
    }
    QPushButton:pressed {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #B898D8, stop:1 #DCC8F0);
        border-top-color: #8060A0;
        border-left-color: #8060A0;
        border-bottom-color: #D0B8E8;
        border-right-color: #D0B8E8;
    }
    QPushButton::menu-indicator {
        image: none;
    }
    QToolTip {
        background-color: #FFFFDD;
        color: #333333;
        border: 1px solid #888888;
        padding: 4px;
        font-size: 9pt;
    }
"""

CATEGORY_BUTTON_STYLE_SIDEBAR = """
    QPushButton {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #E8D4F8, stop:1 #C9A8E8);
        border: 1px solid #A080C0;
        border-radius: 6px;
        padding: 3px 8px;
        text-align: left;
        font-size: 9pt;
        font-weight: normal;
        color: #202124;
        margin: 1px 0px;
    }
    QPushButton:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #DCC8F0, stop:1 #B898D8);
    }
    QPushButton:pressed {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #B898D8, stop:1 #DCC8F0);
    }
    QToolTip {
        background-color: #FFFFDD;
        color: #333333;
        border: 1px solid #888888;
        padding: 4px;
        font-size: 9pt;
    }
"""

BOOKMARK_BUTTON_STYLE = """
    QPushButton {
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 2px;
        padding: 4px 8px;
        text-align: left;
        font-size: 9pt;
        font-weight: normal;
        color: #202124;
    }
    QPushButton:hover {
        background-color: #E8D4F8;
    }
    QPushButton:pressed {
        background-color: #D4C0E8;
    }
    QToolTip {
        background-color: #FFFFDD;
        color: #333333;
        border: 1px solid #888888;
        padding: 4px;
        font-size: 9pt;
    }
"""

POPUP_STYLE = """
    QFrame {
        background-color: #FFFFFF;
        border: 1px solid #A080C0;
        border-radius: 4px;
    }
"""

CONTEXT_MENU_STYLE = """
    QMenu {
        background-color: #ffffff;
        border: 2px solid #0078d4;
        padding: 2px;
    }
    QMenu::item {
        padding: 3px 12px;
        background-color: transparent;
    }
    QMenu::item:selected {
        background-color: #e0e0e0;
    }
    QMenu::separator {
        height: 1px;
        background-color: #d0d0d0;
        margin: 2px 6px;
    }
"""

# Compact purple-bordered style for category context menus
CATEGORY_CONTEXT_MENU_STYLE = """
    QMenu {
        background-color: #ffffff;
        border: 2px solid #7b2d8e;
        padding: 2px;
    }
    QMenu::item {
        padding: 3px 10px;
        background-color: transparent;
        font-size: 9pt;
    }
    QMenu::item:selected {
        background-color: #f3e5f5;
    }
    QMenu::separator {
        height: 1px;
        background-color: #d0d0d0;
        margin: 2px 6px;
    }
"""

# =============================================================================
# Category Color Palette - 6x6 grid of colors for categories
# =============================================================================

CATEGORY_COLORS = [
    # Row 1 - Reds/Pinks
    "#FF6B6B", "#FF8E8E", "#FFB4B4", "#FF69B4", "#FF85C1", "#FFB6C1",
    # Row 2 - Oranges/Yellows  
    "#FFA500", "#FFB347", "#FFCC80", "#FFD700", "#FFEB3B", "#FFF59D",
    # Row 3 - Greens
    "#4CAF50", "#81C784", "#A5D6A7", "#8BC34A", "#AED581", "#C5E1A5",
    # Row 4 - Blues/Cyans
    "#2196F3", "#64B5F6", "#90CAF9", "#00BCD4", "#4DD0E1", "#80DEEA",
    # Row 5 - Purples (default category color area)
    "#9C27B0", "#BA68C8", "#CE93D8", "#7B1FA2", "#AB47BC", "#E1BEE7",
    # Row 6 - Grays/Browns
    "#795548", "#A1887F", "#BCAAA4", "#607D8B", "#90A4AE", "#B0BEC5",
]

# Default category color (purple)
DEFAULT_CATEGORY_COLOR = "#CE93D8"


def darken_color(hex_color, factor=0.7):
    """Darken a hex color by a factor (0-1, lower = darker)"""
    hex_color = hex_color.lstrip('#')
    r = int(int(hex_color[0:2], 16) * factor)
    g = int(int(hex_color[2:4], 16) * factor)
    b = int(int(hex_color[4:6], 16) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def lighten_color(hex_color, factor=0.3):
    """Lighten a hex color by mixing with white"""
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def get_category_button_style(color, orientation='horizontal'):
    """Generate category button stylesheet based on color"""
    light_color = lighten_color(color, 0.4)
    dark_color = darken_color(color, 0.7)
    border_color = darken_color(color, 0.6)
    hover_color = lighten_color(color, 0.2)
    
    # Sidebar (vertical) uses smaller margins
    if orientation == 'vertical':
        margin = "1px 0px"
    else:
        margin = "0px"
    
    base_style = f"""
        QPushButton {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {light_color}, stop:1 {color});
            border: 2px solid {border_color};
            border-radius: 10px;
            padding: 3px 10px;
            margin: {margin};
            text-align: left;
            font-size: 9pt;
            font-weight: normal;
            color: #202124;
        }}
        QPushButton:hover {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {hover_color}, stop:1 {light_color});
            border-color: {dark_color};
        }}
        QPushButton:pressed {{
            background-color: {color};
        }}
        QToolTip {{
            background-color: #FFFFDD;
            color: #333333;
            border: 1px solid #888888;
            padding: 4px;
            font-size: 9pt;
        }}
    """
    return base_style


# Style for message boxes (confirmation dialogs, warnings, etc.)
MESSAGE_BOX_STYLE = """
    QMessageBox {
        background-color: #F5F5F5;
    }
    QMessageBox QLabel {
        color: #202124;
        font-size: 10pt;
        padding: 4px;
    }
    QMessageBox QPushButton {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #F0F0F0, stop:1 #D8D8D8);
        border: 1px solid #A0A0A0;
        border-radius: 4px;
        padding: 5px 16px;
        min-width: 60px;
        font-size: 9pt;
        font-weight: 500;
        color: #202124;
    }
    QMessageBox QPushButton:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #E8E8E8, stop:1 #C8C8C8);
        border-color: #808080;
    }
    QMessageBox QPushButton:pressed {
        background-color: #C0C0C0;
    }
    QMessageBox QPushButton:default {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #5090D0, stop:1 #3070B0);
        border: 1px solid #2060A0;
        color: white;
    }
    QMessageBox QPushButton:default:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #60A0E0, stop:1 #4080C0);
    }
"""


def show_styled_question(parent, title, message, default_no=True):
    """
    Show a styled Yes/No question dialog.
    Returns True if Yes was clicked, False otherwise.
    """
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setIcon(QMessageBox.Icon.Question)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    if default_no:
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
    else:
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
    msg_box.setStyleSheet(MESSAGE_BOX_STYLE)
    
    return msg_box.exec() == QMessageBox.StandardButton.Yes


def show_styled_warning(parent, title, message):
    """Show a styled warning dialog."""
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setIcon(QMessageBox.Icon.Warning)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.setStyleSheet(MESSAGE_BOX_STYLE)
    msg_box.exec()


class ColorPickerPopup(QFrame):
    """
    A popup with a 6x6 grid of colors for category customization.
    """
    
    color_selected = pyqtSignal(str)  # Emits hex color
    
    def __init__(self, parent=None, current_color=None):
        super().__init__(parent, Qt.WindowType.Popup)
        
        self.current_color = current_color
        
        # Use current color for border, or default purple
        border_color = darken_color(current_color, 0.7) if current_color else "#7b2d8e"
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #ffffff;
                border: 2px solid {border_color};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        # Title
        from PyQt6.QtWidgets import QLabel
        title = QLabel("Select Category Color")
        title.setStyleSheet("font-weight: bold; font-size: 9pt; color: #333; border: none;")
        layout.addWidget(title)
        
        # Color grid - 6x6
        from PyQt6.QtWidgets import QGridLayout
        grid = QGridLayout()
        grid.setSpacing(4)
        
        # Use category color for hover, or default purple
        hover_border = border_color
        
        for i, color in enumerate(CATEGORY_COLORS):
            row = i // 6
            col = i % 6
            
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Highlight current color
            border = "3px solid #333" if color == current_color else "1px solid #ccc"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: {border};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid {hover_border};
                }}
            """)
            
            btn.clicked.connect(lambda checked, c=color: self._select_color(c))
            grid.addWidget(btn, row, col)
        
        layout.addLayout(grid)
        
        # Reset to default button
        reset_btn = QPushButton("Reset to Default")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        reset_btn.clicked.connect(lambda: self._select_color(DEFAULT_CATEGORY_COLOR))
        layout.addWidget(reset_btn)
    
    def _select_color(self, color):
        """Handle color selection"""
        self.color_selected.emit(color)
        self.close()


# =============================================================================
# EditBookmarkDialog - Compact dialog for editing bookmark name and path
# =============================================================================

class EditBookmarkDialog(QFrame):
    """
    Compact dialog for editing a bookmark's name and path.
    Styled to match the Add Bookmark dialog but simpler.
    """
    
    accepted = pyqtSignal(str, str)  # Emits (new_name, new_path)
    rejected = pyqtSignal()
    
    def __init__(self, current_name, current_path, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 2px solid #0078d4;
                border-radius: 4px;
            }
        """)
        
        self._setup_ui(current_name, current_path)
        self.adjustSize()
        self.setFixedWidth(350)
        
    def _setup_ui(self, current_name, current_path):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(4)
        
        # Title bar
        title = QLabel("Edit Bookmark")
        title.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 10pt;
                color: #0078d4;
                border: none;
                padding: 2px 0;
            }
        """)
        layout.addWidget(title)
        
        # Form layout
        form_widget = QWidget()
        form_widget.setStyleSheet("QWidget { border: none; }")
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(4)
        
        # Name row
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_label = QLabel("Name:")
        name_label.setFixedWidth(50)
        name_label.setStyleSheet("QLabel { border: none; font-size: 9pt; }")
        self.name_edit = QLineEdit(current_name)
        self.name_edit.setPlaceholderText("Display name")
        self.name_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 2px;
                padding: 3px 6px;
                font-size: 9pt;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """)
        name_row.addWidget(name_label)
        name_row.addWidget(self.name_edit)
        form_layout.addLayout(name_row)
        
        # Path row
        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        path_label = QLabel("Path/URL:")
        path_label.setFixedWidth(50)
        path_label.setStyleSheet("QLabel { border: none; font-size: 9pt; }")
        self.path_edit = QLineEdit(current_path)
        self.path_edit.setPlaceholderText("File path, folder path, or URL")
        self.path_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 2px;
                padding: 3px 6px;
                font-size: 9pt;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """)
        path_row.addWidget(path_label)
        path_row.addWidget(self.path_edit)
        form_layout.addLayout(path_row)
        
        layout.addWidget(form_widget)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(70)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(70)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)
        save_btn.clicked.connect(self._on_save)
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
        
        # Enter key saves
        self.name_edit.returnPressed.connect(self._on_save)
        self.path_edit.returnPressed.connect(self._on_save)
    
    def _on_save(self):
        new_name = self.name_edit.text().strip()
        new_path = self.path_edit.text().strip()
        self.accepted.emit(new_name, new_path)
        self.close()
    
    def _on_cancel(self):
        self.rejected.emit()
        self.close()
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._on_cancel()
        else:
            super().keyPressEvent(event)

    @staticmethod
    def edit_bookmark(current_name, current_path, parent=None):
        """
        Static method to show dialog and return (name, path) or (None, None) if cancelled.
        """
        dialog = EditBookmarkDialog(current_name, current_path, parent)
        
        result = [None, None]
        
        def on_accepted(name, path):
            result[0] = name
            result[1] = path
        
        dialog.accepted.connect(on_accepted)
        
        # Center on parent or screen
        if parent:
            parent_geo = parent.window().geometry()
            dialog.move(
                parent_geo.center().x() - dialog.width() // 2,
                parent_geo.center().y() - dialog.height() // 2
            )
        
        dialog.show()
        dialog.name_edit.setFocus()
        dialog.name_edit.selectAll()
        
        # Block until closed (simple event loop)
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QEventLoop
        loop = QEventLoop()
        dialog.destroyed.connect(loop.quit)
        dialog.accepted.connect(loop.quit)
        dialog.rejected.connect(loop.quit)
        loop.exec()
        
        return result[0], result[1]


# =============================================================================
# CategoryBookmarkButton - Bookmark button inside category popups
# =============================================================================

class CategoryBookmarkButton(QPushButton):
    """
    Draggable bookmark button for use inside category popups.
    Used by both top bar and sidebar category popups.
    """
    
    clicked_path = pyqtSignal(str)
    
    def __init__(self, bookmark_data, source_category, parent=None, popup=None, 
                 data_manager=None, source_location='bar'):
        """
        Args:
            bookmark_data: dict with 'name', 'path', optionally 'type'
            source_category: name of the category this bookmark belongs to
            parent: parent widget
            popup: reference to the popup window (for closing on actions)
            data_manager: object with bookmarks_data, save_bookmarks(), refresh_bookmarks()
                         or custom_quick_links, save_quick_links(), refresh_quick_links_list()
            source_location: 'bar' for top bookmark bar, 'sidebar' for Quick Links
        """
        super().__init__(parent)
        
        self.bookmark_data = bookmark_data
        self.source_category = source_category
        self.parent_popup = popup
        self.data_manager = data_manager
        self.source_location = source_location
        self.drag_start_pos = None
        self._path = bookmark_data.get('path', '')
        
        # Set up display
        name = bookmark_data.get('name', Path(self._path).name if self._path else 'Unknown')
        
        # Get placeholder icon instantly (no filesystem access for .lnk files)
        icon, needs_async = get_file_icon_placeholder(self._path)
        if icon:
            self.setIcon(icon)
            self.setText(f" {name}")  # Small space before name when using icon
            # Schedule async icon load if needed
            if needs_async:
                QTimer.singleShot(0, self._load_icon_async)
        else:
            # URL - use globe emoji in text
            icon_prefix = self._get_url_icon_char(self._path)
            self.setText(f"{icon_prefix} {name}")
        
        self.setToolTip(self._path)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setStyleSheet(BOOKMARK_BUTTON_STYLE)
    
    def _load_icon_async(self):
        """Load the real icon asynchronously on the main thread.
        Uses QTimer to yield to the event loop, allowing the popup to render first.
        """
        # Small delay to let the popup render before loading icons
        QTimer.singleShot(10, self._do_load_icon)
    
    def _do_load_icon(self):
        """Actually load the icon (called from timer on main thread)"""
        try:
            icon = get_file_icon(self._path)
            if icon and not icon.isNull():
                self.setIcon(icon)
                # DB caching is handled inside get_file_icon for .lnk files
        except Exception:
            pass  # Keep placeholder on error
    
    def _get_url_icon_char(self, path):
        """Get emoji icon for URLs only"""
        if not path:
            return '📌'
        
        # Check if it's a URL
        if _is_url(path):
            if 'sharepoint' in path.lower():
                return '☁️'
            return '🌐'
        
        return '📌'
    
    def _show_context_menu(self, pos):
        """Show context menu for this bookmark"""
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)
        
        edit_action = menu.addAction("✏️ Edit")
        menu.addSeparator()
        remove_action = menu.addAction("🗑️ Remove")
        
        action = menu.exec(self.mapToGlobal(pos))
        if action == edit_action:
            self._edit_bookmark()
        elif action == remove_action:
            self._remove_bookmark()
    
    def _edit_bookmark(self):
        """Edit this bookmark's name and path using compact dialog"""
        current_name = self.bookmark_data.get('name', '')
        current_path = self.bookmark_data.get('path', '')
        
        new_name, new_path = EditBookmarkDialog.edit_bookmark(current_name, current_path, self)
        
        if new_name is None:  # Cancelled
            return
        
        # Update the bookmark data
        self.bookmark_data['name'] = new_name if new_name else current_name
        self.bookmark_data['path'] = new_path if new_path else current_path
        
        # Save changes
        if self.data_manager:
            if self.source_location == 'bar':
                self.data_manager.save_bookmarks()
                self.data_manager.refresh_bookmarks()
            else:
                self.data_manager.save_quick_links()
                self.data_manager.refresh_quick_links_list()
        
        # Close popup to show refreshed content
        if self.parent_popup:
            self.parent_popup.close()

    def _remove_bookmark(self):
        """Remove this bookmark from its category"""
        try:
            if not self.data_manager:
                return
            
            if self.source_location == 'bar':
                # Top bookmark bar
                if hasattr(self.data_manager, 'bookmarks_data'):
                    categories = self.data_manager.bookmarks_data.get('categories', {})
                    if self.source_category in categories:
                        items = categories[self.source_category]
                        for i, item in enumerate(items):
                            if item.get('path') == self.bookmark_data.get('path'):
                                items.pop(i)
                                break
                        self.data_manager.save_bookmarks()
                        if self.parent_popup:
                            self.parent_popup.close()
                        self.data_manager.refresh_bookmarks()
            else:
                # Quick Links sidebar
                if hasattr(self.data_manager, 'custom_quick_links'):
                    categories = self.data_manager.custom_quick_links.get('categories', {})
                    if self.source_category in categories:
                        items = categories[self.source_category]
                        for i, item in enumerate(items):
                            if item.get('path') == self.bookmark_data.get('path'):
                                items.pop(i)
                                break
                        self.data_manager.save_quick_links()
                        if self.parent_popup:
                            self.parent_popup.close()
                        self.data_manager.refresh_quick_links_list()
        except Exception as e:
            logger.error(f"Error removing bookmark: {e}")
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_start_pos:
            distance = (event.pos() - self.drag_start_pos).manhattanLength()
            if distance < 10:
                # It was a click, not a drag
                path = self.bookmark_data.get('path', '')
                if path:
                    self.clicked_path.emit(path)
        self.drag_start_pos = None
        super().mouseReleaseEvent(event)
    
    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self.drag_start_pos is None:
            return
        
        distance = (event.pos() - self.drag_start_pos).manhattanLength()
        if distance < 10:
            return
        
        # Start drag
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Bookmark move format - works for both bar and sidebar
        drag_data = {
            'bookmark': self.bookmark_data,
            'source_category': self.source_category,
            'source_location': self.source_location,  # 'bar' or 'sidebar'
            'source': 'quick_links_category' if self.source_location == 'sidebar' else 'bar_category'
        }
        mime_data.setData('application/x-bookmark-move', json.dumps(drag_data).encode())
        
        # Also include quicklink-item format for sidebar drops
        item_data = {
            'type': 'bookmark',
            'name': self.bookmark_data.get('name', ''),
            'path': self.bookmark_data.get('path', ''),
            'source_category': self.source_category,
            'source': 'quick_links_category' if self.source_location == 'sidebar' else 'bar_category'
        }
        mime_data.setData('application/x-quicklink-item', json.dumps(item_data).encode())
        
        mime_data.setText(f"Move: {self.bookmark_data.get('name', 'bookmark')}")
        
        drag.setMimeData(mime_data)
        
        logger.info(f"Dragging bookmark '{self.bookmark_data.get('name')}' from category '{self.source_category}'")
        result = drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        
        # Close popup if drag was successful
        if result == Qt.DropAction.MoveAction and self.parent_popup:
            self.parent_popup.close()


# =============================================================================
# CategoryPopup - Popup window showing category contents
# =============================================================================

class CategoryPopup(QFrame):
    """
    Popup window for category contents.
    Used by both top bar and sidebar categories.
    """
    
    item_clicked = pyqtSignal(str)
    popup_closed = pyqtSignal()
    
    def __init__(self, category_name, category_items, parent_widget=None,
                 data_manager=None, source_location='bar', color=None):
        """
        Args:
            category_name: name of the category
            category_items: list of bookmark dicts
            parent_widget: parent widget for positioning
            data_manager: object managing the bookmark data
            source_location: 'bar' or 'sidebar'
            color: hex color string for the category border
        """
        # Use Tool window type instead of Popup - Popup windows get destroyed on hide
        # Tool windows stay alive and can be shown/hidden efficiently
        super().__init__(parent_widget, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        self.category_name = category_name
        self.category_items = category_items
        self.data_manager = data_manager
        self.source_location = source_location
        self.category_color = color
        self.drop_indicator = None
        self.drop_index = -1
        
        # Track parent button for auto-close behavior
        self._parent_button = parent_widget
        
        self.setAcceptDrops(True)
        
        # Apply style with category color or default
        border_color = darken_color(color, 0.7) if color else "#A080C0"
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border: 2px solid {border_color};
                border-radius: 4px;
            }}
        """)
        
        self.setMinimumWidth(200)
        self.setMaximumWidth(350)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the popup UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        
        # Scroll area for items
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        # Container for items
        self.container = QWidget()
        self.container.setStyleSheet("background-color: transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)
        
        # Add bookmark buttons
        for item_data in self.category_items:
            btn = CategoryBookmarkButton(
                bookmark_data=item_data,
                source_category=self.category_name,
                parent=self.container,
                popup=self,
                data_manager=self.data_manager,
                source_location=self.source_location
            )
            btn.clicked_path.connect(self._on_item_clicked)
            self.container_layout.addWidget(btn)
        
        self.container_layout.addStretch()
        scroll.setWidget(self.container)
        layout.addWidget(scroll)
        
        # Drop indicator
        self.drop_indicator = QFrame(self)
        self.drop_indicator.setStyleSheet("background-color: #A080C0;")
        self.drop_indicator.setFixedHeight(2)
        self.drop_indicator.hide()
        
        # Calculate size
        item_count = len(self.category_items)
        item_height = 28
        total_height = item_count * item_height + 8
        max_height = 400
        self.setFixedHeight(min(total_height, max_height))
    
    def _on_item_clicked(self, path):
        """Handle item click"""
        if path:
            self.item_clicked.emit(path)
            self.close()
    
    def _get_drop_index(self, pos):
        """Get drop index based on position"""
        container_pos = self.container.mapFrom(self, pos)
        
        for i in range(self.container_layout.count() - 1):  # Skip stretch
            widget = self.container_layout.itemAt(i).widget()
            if widget:
                widget_geo = widget.geometry()
                if container_pos.y() < widget_geo.center().y():
                    return i
        return len(self.category_items)
    
    def _show_drop_indicator(self, pos):
        """Show drop indicator"""
        self.drop_index = self._get_drop_index(pos)
        
        y_pos = 2
        if self.drop_index < self.container_layout.count() - 1:
            widget = self.container_layout.itemAt(self.drop_index).widget()
            if widget:
                widget_pos = widget.mapTo(self, widget.rect().topLeft())
                y_pos = widget_pos.y()
        else:
            if self.container_layout.count() > 1:
                last_widget = self.container_layout.itemAt(self.container_layout.count() - 2).widget()
                if last_widget:
                    widget_pos = last_widget.mapTo(self, last_widget.rect().bottomLeft())
                    y_pos = widget_pos.y() + 2
        
        self.drop_indicator.setGeometry(4, y_pos, self.width() - 8, 2)
        self.drop_indicator.show()
        self.drop_indicator.raise_()
    
    def _hide_drop_indicator(self):
        """Hide drop indicator"""
        if self.drop_indicator:
            self.drop_indicator.hide()
        self.drop_index = -1
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-bookmark-move'):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat('application/x-bookmark-move'):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        self._hide_drop_indicator()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        """Handle bookmark drop"""
        self._hide_drop_indicator()
        
        if not event.mimeData().hasFormat('application/x-bookmark-move'):
            event.ignore()
            return
        
        try:
            drag_data = json.loads(event.mimeData().data('application/x-bookmark-move').data().decode())
            bookmark = drag_data.get('bookmark', {})
            source_category = drag_data.get('source_category', '')
            drop_idx = self.drop_index if self.drop_index >= 0 else self._get_drop_index(event.position().toPoint())
            
            if not bookmark or not bookmark.get('path'):
                event.ignore()
                return
            
            path = bookmark.get('path')
            
            if source_category == self.category_name:
                # Reordering within same category
                old_index = -1
                for i, item in enumerate(self.category_items):
                    if item.get('path') == path:
                        old_index = i
                        break
                
                if old_index != -1 and old_index != drop_idx:
                    moved_item = self.category_items.pop(old_index)
                    if old_index < drop_idx:
                        drop_idx -= 1
                    self.category_items.insert(drop_idx, moved_item)
                    
                    # Save changes
                    if self.data_manager:
                        if self.source_location == 'bar':
                            self.data_manager.bookmarks_data['categories'][self.category_name] = self.category_items
                            self.data_manager.save_bookmarks()
                        else:
                            self.data_manager.custom_quick_links['categories'][self.category_name] = self.category_items
                            self.data_manager.save_quick_links()
                    
                    logger.info(f"Reordered item in category '{self.category_name}' from {old_index} to {drop_idx}")
                    self.close()
                    
                    # Refresh
                    if self.data_manager:
                        if self.source_location == 'bar':
                            self.data_manager.refresh_bookmarks()
                        else:
                            self.data_manager.refresh_quick_links_list()
            else:
                # Moving from another category - delegate to data manager
                if self.data_manager:
                    bookmark['_source_category'] = source_category
                    if self.source_location == 'sidebar' and hasattr(self.data_manager, '_on_bookmark_dropped_to_category'):
                        self.data_manager._on_bookmark_dropped_to_category(self.category_name, bookmark)
                    # For bar, handle here
                    elif self.source_location == 'bar':
                        self._handle_cross_category_drop(bookmark, source_category, drop_idx)
                self.close()
            
            event.acceptProposedAction()
        except Exception as e:
            logger.error(f"Error handling drop in category popup: {e}")
            import traceback
            traceback.print_exc()
            event.ignore()
    
    def _handle_cross_category_drop(self, bookmark, source_category, drop_idx):
        """Handle dropping bookmark from another category or the bar (bar mode)"""
        if not self.data_manager or not hasattr(self.data_manager, 'bookmarks_data'):
            return
        
        path = bookmark.get('path')
        if not path:
            return
        
        # Normalize path for comparison
        path_normalized = os.path.normpath(path).lower() if path else ''
        
        # Add to this category
        if self.category_name not in self.data_manager.bookmarks_data['categories']:
            self.data_manager.bookmarks_data['categories'][self.category_name] = []
        
        # Check for duplicate
        existing = self.data_manager.bookmarks_data['categories'][self.category_name]
        for b in existing:
            b_path = b.get('path', '')
            if b_path and os.path.normpath(b_path).lower() == path_normalized:
                return
        
        # Clean bookmark data for storage (remove internal fields)
        clean_bookmark = {k: v for k, v in bookmark.items() if not k.startswith('_')}
        
        # Insert at position
        if drop_idx >= 0 and drop_idx < len(existing):
            existing.insert(drop_idx, clean_bookmark)
        else:
            existing.append(clean_bookmark)
        
        # Remove from source
        if source_category in ('__BAR__', '__CONTAINER__'):
            # Item was on the bar/container directly - remove from bar_items list
            bar_items = self.data_manager.bookmarks_data.get('bar_items', [])
            removed = False
            for i, item in enumerate(bar_items):
                if item.get('type') == 'bookmark':
                    item_path = item.get('path') or item.get('data', {}).get('path')
                    item_path_normalized = os.path.normpath(item_path).lower() if item_path else ''
                    if item_path_normalized == path_normalized:
                        bar_items.pop(i)
                        logger.info(f"Removed bookmark from bar_items at index {i}")
                        removed = True
                        break
            
            # Also check 'items' key as fallback
            if not removed:
                items = self.data_manager.bookmarks_data.get('items', [])
                for i, item in enumerate(items):
                    if item.get('type') == 'bookmark':
                        item_path = item.get('path') or item.get('data', {}).get('path')
                        item_path_normalized = os.path.normpath(item_path).lower() if item_path else ''
                        if item_path_normalized == path_normalized:
                            items.pop(i)
                            logger.info(f"Removed bookmark from items at index {i}")
                            break
        elif source_category in self.data_manager.bookmarks_data.get('categories', {}):
            src_list = self.data_manager.bookmarks_data['categories'][source_category]
            for i, b in enumerate(src_list):
                if b.get('path') == path:
                    src_list.pop(i)
                    break
        
        self.data_manager.save_bookmarks()
        self.data_manager.refresh_bookmarks()
    
    def showEvent(self, event):
        """When shown, activate to receive focus events"""
        super().showEvent(event)
        # Use timer to defer focus activation - allows window to render first
        QTimer.singleShot(0, self._activate_popup)
    
    def _activate_popup(self):
        """Activate popup after it's visible"""
        if self.isVisible():
            self.activateWindow()
            self.setFocus()
    
    def focusOutEvent(self, event):
        """Auto-hide when focus is lost (like Popup behavior)"""
        super().focusOutEvent(event)
        # Small delay to allow click events to process first
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self._check_and_hide)
    
    def _check_and_hide(self):
        """Hide if we don't have focus and mouse isn't over us"""
        if not self.isActiveWindow() and not self.underMouse():
            self.hide()
            self.popup_closed.emit()
    
    def closeEvent(self, event):
        """Intercept close and convert to hide for reuse"""
        self.popup_closed.emit()
        # Hide instead of close so we can reuse
        event.ignore()
        self.hide()


# =============================================================================
# CategoryButton - Category button that shows popup on click
# =============================================================================

class CategoryButton(QPushButton):
    """
    Draggable category button with popup support.
    Used by both top bar and sidebar.
    """
    
    popup_opened = pyqtSignal(object)  # Emits the popup
    popup_closed = pyqtSignal()
    item_clicked = pyqtSignal(str)
    
    def __init__(self, category_name, category_items, item_index=0, parent=None,
                 data_manager=None, source_location='bar', orientation='horizontal',
                 color=None):
        """
        Args:
            category_name: name of the category
            category_items: list of bookmark dicts
            item_index: index in the bar/sidebar for drag reordering
            parent: parent widget
            data_manager: object managing bookmark data
            source_location: 'bar' or 'sidebar'
            orientation: 'horizontal' (top bar) or 'vertical' (sidebar)
            color: hex color string for the category (e.g., '#CE93D8')
        """
        super().__init__(f"🗄 {category_name} ▾", parent)
        
        self.category_name = category_name
        self.category_items = category_items
        self.item_index = item_index
        self.data_manager = data_manager
        self.source_location = source_location
        self.orientation = orientation
        self.category_color = color  # Store the color
        self.drag_start_pos = None
        self.dragging = False
        self.active_popup = None
        self.popup_closed_time = 0
        
        self.setToolTip(f"{len(category_items)} bookmark(s)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty('category_name', category_name)
        self.setAcceptDrops(True)
        
        # For vertical orientation (sidebar), set size policy to allow shrinking
        # This ensures the button stays within the visible area and rounded corners are visible
        if self.orientation == 'vertical':
            from PyQt6.QtWidgets import QSizePolicy
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        # Apply appropriate style (with custom color if provided)
        self._apply_style()
    
    def _apply_style(self):
        """Apply the button style based on color and orientation"""
        if self.category_color:
            # Use custom color
            self.setStyleSheet(get_category_button_style(self.category_color, self.orientation))
        else:
            # Use default style
            if self.orientation == 'horizontal':
                self.setStyleSheet(CATEGORY_BUTTON_STYLE)
            else:
                self.setStyleSheet(CATEGORY_BUTTON_STYLE_SIDEBAR)
        
        # Set size constraints
        if self.orientation == 'horizontal':
            self.setMaximumWidth(200)
        else:
            self.setFixedHeight(26)
    
    def set_color(self, color):
        """Set a new color for this category button"""
        self.category_color = color
        self._apply_style()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.dragging = False
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.pos())
        # Don't call super to prevent automatic handling
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was_click = not self.dragging and self.drag_start_pos is not None
            self.drag_start_pos = None
            self.dragging = False
            
            if was_click:
                # Check if we just closed the popup (prevent flicker)
                if time.time() - self.popup_closed_time < 0.3:
                    return
                self._show_popup()
        super().mouseReleaseEvent(event)
    
    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self.drag_start_pos is None:
            return
        
        distance = (event.pos() - self.drag_start_pos).manhattanLength()
        if distance < 10:
            return
        
        self.dragging = True
        
        # Start drag
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Store index for reordering within container
        mime_data.setText(str(self.item_index))
        mime_data.setData('application/x-container-item-index', str(self.item_index).encode())
        
        if self.source_location == 'bar':
            mime_data.setData('application/x-bar-item-index', str(self.item_index).encode())
        
        # Category move data (include color for transfer)
        category_data = {
            'name': self.category_name,
            'items': self.category_items,
            'source_location': self.source_location,  # 'bar' or 'sidebar'
            'source': 'bookmark_bar' if self.source_location == 'bar' else 'quick_links',
            'bar_item_index': self.item_index,
            'color': self.category_color  # Include color for transfer
        }
        mime_data.setData('application/x-category-move', json.dumps(category_data).encode())
        
        # Also quicklink format for sidebar
        if self.source_location == 'sidebar':
            item_data = {
                'type': 'category',
                'name': self.category_name,
                'items': self.category_items,
                'index': self.item_index,
                'source': 'quick_links',
                'color': self.category_color  # Include color for transfer
            }
            mime_data.setData('application/x-quicklink-item', json.dumps(item_data).encode())
        
        drag.setMimeData(mime_data)
        
        logger.info(f"Dragging category: {self.category_name}")
        result = drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        self.dragging = False
    
    def _show_popup(self):
        """Show the category popup - reuses existing popup if available"""
        # Toggle off if already visible
        if self.active_popup and self.active_popup.isVisible():
            self.active_popup.hide()
            return
        
        # Reuse existing popup if it exists and items haven't changed
        if self.active_popup:
            # Position below button and show - popup already has icons loaded
            global_pos = self.mapToGlobal(self.rect().bottomLeft())
            self.active_popup.move(global_pos)
            self.active_popup.show()
            self.popup_opened.emit(self.active_popup)
            return
        
        # Create new popup only if we don't have one
        popup = CategoryPopup(
            category_name=self.category_name,
            category_items=self.category_items,
            parent_widget=self,
            data_manager=self.data_manager,
            source_location=self.source_location,
            color=self.category_color
        )
        
        popup.item_clicked.connect(self._on_popup_item_clicked)
        popup.popup_closed.connect(self._on_popup_closed)
        
        # Position below button
        global_pos = self.mapToGlobal(self.rect().bottomLeft())
        popup.move(global_pos)
        popup.show()
        
        self.active_popup = popup
        self.popup_opened.emit(popup)
    
    def invalidate_popup(self):
        """Call this when category contents change to force popup recreation"""
        if self.active_popup:
            self.active_popup.close()
            self.active_popup.deleteLater()
            self.active_popup = None
    
    def update_items(self, new_items):
        """Update the category items and invalidate the popup cache"""
        self.category_items = new_items
        self.setToolTip(f"{len(new_items)} bookmark(s)")
        self.invalidate_popup()
    
    def _on_popup_item_clicked(self, path):
        self.item_clicked.emit(path)
    
    def _on_popup_closed(self):
        """Called when popup closes - keep reference for reuse"""
        self.popup_closed_time = time.time()
        # Don't set active_popup = None, keep it for reuse
        # The popup will be shown again on next click
        self.popup_closed.emit()
    
    def _show_context_menu(self, pos):
        """Show context menu with Rename, Change Color, and Remove options"""
        menu = QMenu(self)
        
        # Use category color for border, or default purple
        border_color = darken_color(self.category_color, 0.7) if self.category_color else "#7b2d8e"
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: #ffffff;
                border: 2px solid {border_color};
                padding: 2px;
            }}
            QMenu::item {{
                padding: 4px 12px;
                background-color: transparent;
                font-size: 9pt;
            }}
            QMenu::item:selected {{
                background-color: #f3e5f5;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #d0d0d0;
                margin: 2px 6px;
            }}
        """)
        
        rename_action = menu.addAction("✏️ Rename")
        color_action = menu.addAction("🎨 Change Color")
        remove_action = menu.addAction("🗑️ Remove")
        
        action = menu.exec(self.mapToGlobal(pos))
        
        if action == rename_action:
            self._rename_category()
        elif action == color_action:
            self._change_color()
        elif action == remove_action:
            self._remove_category()
    
    def _change_color(self):
        """Show color picker to change category color"""
        picker = ColorPickerPopup(self, self.category_color)
        picker.color_selected.connect(self._on_color_selected)
        
        # Position near the button
        global_pos = self.mapToGlobal(self.rect().bottomLeft())
        picker.move(global_pos)
        picker.show()
    
    def _on_color_selected(self, color):
        """Handle color selection from picker"""
        self.set_color(color)
        
        # Save the color to data
        if not self.data_manager:
            return
        
        if self.source_location == 'bar':
            if hasattr(self.data_manager, 'bookmarks_data'):
                # Store color in category_colors dict
                if 'category_colors' not in self.data_manager.bookmarks_data:
                    self.data_manager.bookmarks_data['category_colors'] = {}
                self.data_manager.bookmarks_data['category_colors'][self.category_name] = color
                self.data_manager.save_bookmarks()
        else:
            # Quick Links sidebar
            if hasattr(self.data_manager, 'custom_quick_links'):
                if 'category_colors' not in self.data_manager.custom_quick_links:
                    self.data_manager.custom_quick_links['category_colors'] = {}
                self.data_manager.custom_quick_links['category_colors'][self.category_name] = color
                self.data_manager.save_quick_links()
    
    def _rename_category(self):
        """Rename this category"""
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Category",
            f"Enter new name for '{self.category_name}':",
            QLineEdit.EchoMode.Normal,
            self.category_name
        )
        
        if ok and new_name:
            new_name = new_name.strip()
            if new_name == self.category_name:
                return
            
            if not self.data_manager:
                return
            
            if self.source_location == 'bar':
                if not hasattr(self.data_manager, 'bookmarks_data'):
                    return
                
                # Check for duplicate
                if new_name in self.data_manager.bookmarks_data.get('categories', {}):
                    show_styled_warning(self, "Duplicate", f"Category '{new_name}' already exists.")
                    return
                
                # Rename in categories
                categories = self.data_manager.bookmarks_data.get('categories', {})
                if self.category_name in categories:
                    categories[new_name] = categories.pop(self.category_name)
                
                # Transfer color to new name
                category_colors = self.data_manager.bookmarks_data.get('category_colors', {})
                if self.category_name in category_colors:
                    category_colors[new_name] = category_colors.pop(self.category_name)
                
                # Update bar_items
                for item in self.data_manager.bookmarks_data.get('bar_items', []):
                    if item.get('type') == 'category' and item.get('name') == self.category_name:
                        item['name'] = new_name
                        break
                
                self.data_manager.save_bookmarks()
                self.data_manager.refresh_bookmarks()
            else:
                # Sidebar
                if not hasattr(self.data_manager, 'custom_quick_links'):
                    return
                
                if hasattr(self.data_manager, 'rename_category_in_quick_links'):
                    if new_name in self.data_manager.custom_quick_links.get('categories', {}):
                        show_styled_warning(self, "Duplicate", f"Category '{new_name}' already exists.")
                        return
                    
                    # Transfer color to new name (sidebar)
                    category_colors = self.data_manager.custom_quick_links.get('category_colors', {})
                    if self.category_name in category_colors:
                        category_colors[new_name] = category_colors.pop(self.category_name)
                    
                    self.data_manager.rename_category_in_quick_links(self.category_name, new_name)
                    self.data_manager.refresh_quick_links_list()
    
    def _remove_category(self):
        """Remove this category with confirmation"""
        # Build message
        if self.category_items:
            items_list = "\n".join([f"  • {item.get('name', item.get('path', 'Unknown'))}" for item in self.category_items])
            message = f"Are you sure you want to remove the category '{self.category_name}'?\n\nThe following {len(self.category_items)} bookmark(s) will be deleted:\n{items_list}"
        else:
            message = f"Are you sure you want to remove the empty category '{self.category_name}'?"
        
        if not show_styled_question(self, "Remove Category", message):
            return
        
        if not self.data_manager:
            return
        
        if self.source_location == 'bar':
            if not hasattr(self.data_manager, 'bookmarks_data'):
                return
            
            # Remove from categories
            categories = self.data_manager.bookmarks_data.get('categories', {})
            if self.category_name in categories:
                del categories[self.category_name]
            
            # Remove color
            category_colors = self.data_manager.bookmarks_data.get('category_colors', {})
            if self.category_name in category_colors:
                del category_colors[self.category_name]
            
            # Remove from bar_items
            bar_items = self.data_manager.bookmarks_data.get('bar_items', [])
            for i, item in enumerate(bar_items):
                if item.get('type') == 'category' and item.get('name') == self.category_name:
                    bar_items.pop(i)
                    break
            
            self.data_manager.save_bookmarks()
            self.data_manager.refresh_bookmarks()
        else:
            # Sidebar - remove color first
            if hasattr(self.data_manager, 'custom_quick_links'):
                category_colors = self.data_manager.custom_quick_links.get('category_colors', {})
                if self.category_name in category_colors:
                    del category_colors[self.category_name]
            
            if hasattr(self.data_manager, 'remove_category_from_quick_links'):
                self.data_manager.remove_category_from_quick_links(self.category_name)
                self.data_manager.refresh_quick_links_list()
    
    # Drag-drop handling for accepting drops onto the category
    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat('application/x-bookmark-move') or mime.hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        event.accept()
    
    def dropEvent(self, event):
        """Handle drops onto this category"""
        mime = event.mimeData()
        
        if mime.hasFormat('application/x-bookmark-move'):
            try:
                drag_data = json.loads(mime.data('application/x-bookmark-move').data().decode())
                bookmark = drag_data['bookmark']
                source = drag_data.get('source_category', '__BAR__')
                
                logger.info(f"Dropping bookmark '{bookmark.get('name')}' into category '{self.category_name}'")
                
                if not self.data_manager:
                    event.ignore()
                    return
                
                if self.source_location == 'bar':
                    self._handle_bar_drop(bookmark, source)
                else:
                    self._handle_sidebar_drop(bookmark, source)
                
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error handling drop: {e}")
                event.ignore()
        
        elif mime.hasUrls():
            try:
                for url in mime.urls():
                    path = url.toLocalFile()
                    if path:
                        name = Path(path).name
                        bookmark = {'name': name, 'path': path}
                        
                        if self.source_location == 'bar':
                            self._handle_bar_drop(bookmark, '__NEW__')
                        else:
                            self._handle_sidebar_drop(bookmark, '__NEW__')
                
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error handling URL drop: {e}")
                event.ignore()
        else:
            event.ignore()
    
    def _handle_bar_drop(self, bookmark, source):
        """Handle drop onto bar category"""
        if not hasattr(self.data_manager, 'bookmarks_data'):
            return
        
        path = bookmark.get('path')
        
        # Add to category
        if self.category_name not in self.data_manager.bookmarks_data['categories']:
            self.data_manager.bookmarks_data['categories'][self.category_name] = []
        
        # Check duplicate
        existing = self.data_manager.bookmarks_data['categories'][self.category_name]
        if any(b.get('path') == path for b in existing):
            return
        
        existing.append(bookmark)
        
        # Remove from source
        if source in ('__BAR__', '__CONTAINER__'):
            bar_items = self.data_manager.bookmarks_data.get('bar_items', [])
            for i, item in enumerate(bar_items):
                if item.get('type') == 'bookmark':
                    item_path = item.get('path') or item.get('data', {}).get('path')
                    if item_path == path:
                        bar_items.pop(i)
                        logger.info(f"Removed bookmark from bar_items at index {i}")
                        break
        elif source and source != '__NEW__' and source != self.category_name:
            if source in self.data_manager.bookmarks_data.get('categories', {}):
                src_list = self.data_manager.bookmarks_data['categories'][source]
                for i, b in enumerate(src_list):
                    if b.get('path') == path:
                        src_list.pop(i)
                        break
        
        self.data_manager.save_bookmarks()
        self.data_manager.refresh_bookmarks()
    
    def _handle_sidebar_drop(self, bookmark, source):
        """Handle drop onto sidebar category"""
        if not hasattr(self.data_manager, 'custom_quick_links'):
            return
        
        path = bookmark.get('path')
        
        # Add to category
        categories = self.data_manager.custom_quick_links.get('categories', {})
        if self.category_name not in categories:
            categories[self.category_name] = []
        
        # Check duplicate
        if any(b.get('path') == path for b in categories[self.category_name]):
            return
        
        categories[self.category_name].append(bookmark)
        
        # Remove from source
        if source in ('__QUICK_LINKS__', '__CONTAINER__'):
            # Remove from sidebar items list
            items = self.data_manager.custom_quick_links.get('items', [])
            for i, item in enumerate(items):
                if item.get('type') == 'bookmark':
                    item_path = item.get('path') or item.get('data', {}).get('path')
                    if item_path == path:
                        items.pop(i)
                        logger.info(f"Removed bookmark from sidebar items at index {i}")
                        break
        elif source and source != '__NEW__' and source != self.category_name:
            # Remove from source category
            if source in categories:
                src_list = categories[source]
                for i, b in enumerate(src_list):
                    if b.get('path') == path:
                        src_list.pop(i)
                        break
        
        self.data_manager.save_quick_links()
        self.data_manager.refresh_quick_links_list()


# =============================================================================
# BookmarkContainer - Unified container for bookmarks and categories
# =============================================================================

# Style for standalone bookmark buttons in containers
STANDALONE_BOOKMARK_STYLE_HORIZONTAL = """
    QPushButton {
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 4px 8px;
        text-align: left;
        font-size: 9pt;
        color: #202124;
    }
    QPushButton:hover {
        background-color: #E8E8E8;
        border-color: #D0D0D0;
    }
    QPushButton:pressed {
        background-color: #D8D8D8;
    }
    QToolTip {
        background-color: #FFFFDD;
        color: #333333;
        border: 1px solid #888888;
        padding: 4px;
        font-size: 9pt;
    }
"""

STANDALONE_BOOKMARK_STYLE_VERTICAL = """
    QPushButton {
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 3px;
        padding: 4px 8px;
        text-align: left;
        font-size: 9pt;
        color: #202124;
        min-height: 22px;
    }
    QPushButton:hover {
        background-color: #E8D4F8;
        border-color: #D0B8E8;
    }
    QPushButton:pressed {
        background-color: #D8C8E8;
    }
    QToolTip {
        background-color: #FFFFDD;
        color: #333333;
        border: 1px solid #888888;
        padding: 4px;
        font-size: 9pt;
    }
"""


class StandaloneBookmarkButton(QPushButton):
    """
    Draggable bookmark button for standalone bookmarks (not inside categories).
    Used by BookmarkContainer for both horizontal (bar) and vertical (sidebar) layouts.
    """
    
    clicked_path = pyqtSignal(str)
    double_clicked_path = pyqtSignal(str)
    
    def __init__(self, bookmark_data, item_index=0, parent=None, container=None, 
                 orientation='horizontal'):
        """
        Args:
            bookmark_data: dict with 'name', 'path', optionally 'type'
            item_index: index in the container's items list
            parent: parent widget
            container: reference to the BookmarkContainer
            orientation: 'horizontal' or 'vertical'
        """
        super().__init__(parent)
        
        self.bookmark_data = bookmark_data
        self.item_index = item_index
        self.container = container
        self.orientation = orientation
        self.drag_start_pos = None
        self.dragging = False
        
        # Set text and icon
        name = bookmark_data.get('name', 'Unnamed')
        path = bookmark_data.get('path', '')
        
        # Try to get real file icon first (DB caching is handled inside get_file_icon)
        icon = get_file_icon(path)
        if icon:
            self.setIcon(icon)
            self.setText(f" {name}")  # Small space before name when using icon
        else:
            # URL - use globe emoji in text
            icon_char = self._get_url_icon_char(path)
            self.setText(f"{icon_char} {name}")
        
        self.setToolTip(path)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Apply style based on orientation
        if orientation == 'horizontal':
            self.setStyleSheet(STANDALONE_BOOKMARK_STYLE_HORIZONTAL)
            self.setMaximumWidth(180)
        else:
            self.setStyleSheet(STANDALONE_BOOKMARK_STYLE_VERTICAL)
            self.setFixedHeight(26)
        
        # Enable context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def _get_url_icon_char(self, path):
        """Get an icon character for URLs only"""
        if not path:
            return '📌'
        
        path_lower = path.lower()
        
        # URLs
        if path.startswith('http://') or path.startswith('https://'):
            if 'sharepoint' in path_lower:
                return '☁️'
            return '🌐'
        
        return '📌'
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.dragging = False
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.dragging and self.drag_start_pos is not None:
                # It was a click, emit the signal
                self.clicked_path.emit(self.bookmark_data.get('path', ''))
            self.drag_start_pos = None
            self.dragging = False
        super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked_path.emit(self.bookmark_data.get('path', ''))
        super().mouseDoubleClickEvent(event)
    
    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self.drag_start_pos is None:
            return
        
        distance = (event.pos() - self.drag_start_pos).manhattanLength()
        if distance < 10:
            return
        
        self.dragging = True
        
        # Start drag
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Store index for reordering within container
        mime_data.setText(str(self.item_index))
        mime_data.setData('application/x-container-item-index', str(self.item_index).encode())
        
        # Bookmark move data
        drag_data = {
            'bookmark': self.bookmark_data,
            'source_category': '__CONTAINER__',
            'source_location': self.container.location if self.container else 'unknown',
            'item_index': self.item_index
        }
        mime_data.setData('application/x-bookmark-move', json.dumps(drag_data).encode())
        
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        self.dragging = False
    
    def _show_context_menu(self, pos):
        """Show context menu for this bookmark"""
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)
        
        # Open folder location
        open_folder_action = menu.addAction("📂 Open folder location")
        
        # Copy link
        copy_action = menu.addAction("📋 Copy link")
        
        # Edit
        edit_action = menu.addAction("✏️ Edit")
        
        menu.addSeparator()
        
        # Remove
        remove_action = menu.addAction("🗑️ Remove")
        
        action = menu.exec(self.mapToGlobal(pos))
        
        if action == open_folder_action:
            self._open_folder_location()
        elif action == copy_action:
            self._copy_link()
        elif action == edit_action:
            self._edit_bookmark()
        elif action == remove_action:
            self._remove_bookmark()
    
    def _open_folder_location(self):
        """Open the parent folder in file explorer"""
        import subprocess
        from pathlib import Path as PathLib
        path = PathLib(self.bookmark_data.get('path', ''))
        if path.exists():
            parent = path.parent if path.is_file() else path
            subprocess.run(['explorer', str(parent)])
    
    def _copy_link(self):
        """Copy the path to clipboard"""
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.bookmark_data.get('path', ''))
    
    def _edit_bookmark(self):
        """Edit this bookmark's name and path using compact dialog"""
        current_name = self.bookmark_data.get('name', '')
        current_path = self.bookmark_data.get('path', '')
        
        new_name, new_path = EditBookmarkDialog.edit_bookmark(current_name, current_path, self)
        
        if new_name is None:  # Cancelled
            return
        
        # Update the bookmark data
        self.bookmark_data['name'] = new_name if new_name else current_name
        self.bookmark_data['path'] = new_path if new_path else current_path
        
        # Refresh the container to show updated bookmark
        if self.container:
            self.container.refresh()
    
    def _remove_bookmark(self):
        """Remove this bookmark from the container"""
        if self.container:
            self.container.remove_item(self.item_index)


# =============================================================================
# BookmarkContainer Registry - enables cross-bar communication
# =============================================================================

class BookmarkContainerRegistry:
    """
    Singleton registry that tracks all BookmarkContainer instances.
    Enables cross-bar drag and drop operations by allowing containers
    to find and communicate with each other.
    """
    _instance = None
    _containers = {}  # location -> BookmarkContainer
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, location: str, container: 'BookmarkContainer'):
        """Register a container by its location identifier"""
        cls._containers[location] = container
        logger.debug(f"BookmarkContainer registered: {location}")
    
    @classmethod
    def unregister(cls, location: str):
        """Unregister a container"""
        if location in cls._containers:
            del cls._containers[location]
            logger.debug(f"BookmarkContainer unregistered: {location}")
    
    @classmethod
    def get(cls, location: str) -> 'BookmarkContainer':
        """Get a container by location"""
        return cls._containers.get(location)
    
    @classmethod
    def get_all(cls) -> dict:
        """Get all registered containers"""
        return cls._containers.copy()
    
    @classmethod
    def get_other(cls, exclude_location: str) -> list:
        """Get all containers except the specified one"""
        return [c for loc, c in cls._containers.items() if loc != exclude_location]


class DropForwardingWidget(QWidget):
    """
    A QWidget that accepts drops and forwards all drop events to its parent BookmarkContainer.
    Used as the items_container inside BookmarkContainer to ensure drops are handled properly.
    """
    
    def __init__(self, bookmark_container):
        super().__init__()
        self.bookmark_container = bookmark_container
        self.setAcceptDrops(True)
    
    def dragEnterEvent(self, event):
        """Forward to parent BookmarkContainer"""
        self.bookmark_container.dragEnterEvent(event)
    
    def dragMoveEvent(self, event):
        """Forward to parent BookmarkContainer"""
        self.bookmark_container.dragMoveEvent(event)
    
    def dragLeaveEvent(self, event):
        """Forward to parent BookmarkContainer"""
        self.bookmark_container.dragLeaveEvent(event)
    
    def dropEvent(self, event):
        """Forward to parent BookmarkContainer"""
        self.bookmark_container.dropEvent(event)


class BookmarkContainer(QWidget):
    """
    Unified container for bookmarks and categories.
    Can be used horizontally (top bar) or vertically (sidebar).
    
    This class provides a standardized interface for:
    - Displaying bookmarks and categories
    - Drag and drop reordering
    - Moving items between containers (cross-bar support via registry)
    - Adding/removing items
    - Context menus
    
    Cross-bar drag and drop:
    - All BookmarkContainer instances register with BookmarkContainerRegistry
    - When an item is dropped from another container, it's automatically moved
    - Source container is found via the registry and item is removed from it
    """
    
    # Signals
    item_clicked = pyqtSignal(str)  # Emits path when a bookmark is clicked
    item_double_clicked = pyqtSignal(str)  # Emits path on double-click
    navigate_to_path = pyqtSignal(str)  # Request navigation to a path
    
    # Signals for external drop handling (allows parent to handle complex move logic)
    bookmark_dropped = pyqtSignal(dict)   # Emits bookmark data when bookmark dropped from external source
    category_dropped = pyqtSignal(dict)   # Emits category data when category dropped from external source
    file_dropped = pyqtSignal(object)     # Emits path/dict when file dropped
    item_reordered = pyqtSignal(int, int) # Emits (old_index, new_index) when item reordered internally
    
    def __init__(self, location, orientation='horizontal', parent=None,
                 data_store=None, save_callback=None, items_key='items',
                 categories_key='categories', colors_key='category_colors'):
        """
        Args:
            location: Identifier for this container ('bar' or 'sidebar')
            orientation: 'horizontal' or 'vertical'
            parent: Parent widget
            data_store: Dict reference for storing data (e.g., bookmarks_data or custom_quick_links)
            save_callback: Function to call after data changes (e.g., save to disk)
            items_key: Key in data_store for the ordered items list
            categories_key: Key in data_store for categories dict
            colors_key: Key in data_store for category colors dict
        """
        super().__init__(parent)
        
        # Ensure icons are loaded from database cache before creating UI
        ensure_icons_loaded()
        
        self.location = location
        self.orientation = orientation
        self.data_store = data_store or {}
        self.save_callback = save_callback
        self.items_key = items_key
        self.categories_key = categories_key
        self.colors_key = colors_key
        
        # Register with the global registry for cross-bar communication
        BookmarkContainerRegistry.register(location, self)
        
        self.setAcceptDrops(True)
        
        self._setup_ui()
        self._setup_drop_indicator()
    
    def _setup_drop_indicator(self):
        """Set up the visual drop indicator for drag operations"""
        self.drop_indicator = QFrame(self)
        if self.orientation == 'horizontal':
            self.drop_indicator.setFixedWidth(3)
            self.drop_indicator.setFixedHeight(24)
        else:
            self.drop_indicator.setFixedHeight(3)
            self.drop_indicator.setFixedWidth(200)
        self.drop_indicator.setStyleSheet("""
            QFrame {
                background-color: #0078D4;
                border-radius: 1px;
            }
        """)
        self.drop_indicator.hide()
    
    def _setup_ui(self):
        """Set up the container UI"""
        if self.orientation == 'horizontal':
            self._setup_horizontal()
        else:
            self._setup_vertical()
    
    def _setup_horizontal(self):
        """Set up horizontal layout (for top bar)"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        # Scroll area for overflow
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        self.scroll_area.setAcceptDrops(False)  # Let drops pass through
        
        # Items container - accepts drops and forwards to parent
        self.items_container = DropForwardingWidget(self)
        self.items_container.setStyleSheet("background-color: transparent;")
        self.items_layout = QHBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(1)
        self.items_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.scroll_area.setWidget(self.items_container)
        layout.addWidget(self.scroll_area, 1)
        
        # Context menu for empty space
        self.items_container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.items_container.customContextMenuRequested.connect(self._show_container_context_menu)
    
    def _setup_vertical(self):
        """Set up vertical layout (for sidebar)"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        # Disable horizontal scrolling - buttons should shrink to fit, not extend beyond
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollArea > QWidget > QWidget { background-color: transparent; }
        """)
        self.scroll_area.setAcceptDrops(False)  # Let drops pass through
        
        # Items container - accepts drops and forwards to parent
        self.items_container = DropForwardingWidget(self)
        self.items_container.setStyleSheet("background-color: transparent;")
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(4, 2, 14, 2)  # Extra right margin (14px) for rounded corners
        self.items_layout.setSpacing(1)
        self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.items_container)
        layout.addWidget(self.scroll_area, 1)
        
        # Context menu for empty space
        self.items_container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.items_container.customContextMenuRequested.connect(self._show_container_context_menu)
    
    def resizeEvent(self, event):
        """Handle resize events - update button widths for vertical orientation"""
        super().resizeEvent(event)
        if self.orientation == 'vertical':
            self._update_button_widths()
    
    def _update_button_widths(self):
        """Update all button widths to fit within the container (for vertical/sidebar)"""
        if self.orientation != 'vertical':
            return
        
        # Calculate available width: container width minus minimal padding
        available_width = self.width() - 4  # Just 4px to prevent clipping
        if available_width < 50:
            available_width = 50  # Minimum width
        
        # Update all widgets in the layout
        for i in range(self.items_layout.count()):
            item = self.items_layout.itemAt(i)
            widget = item.widget()
            if widget and isinstance(widget, (CategoryButton, StandaloneBookmarkButton)):
                widget.setMaximumWidth(available_width)
    
    # -------------------------------------------------------------------------
    # Data Access Properties
    # -------------------------------------------------------------------------
    
    @property
    def items(self):
        """Get the ordered items list"""
        return self.data_store.get(self.items_key, [])
    
    @property
    def categories(self):
        """Get the categories dict"""
        return self.data_store.get(self.categories_key, {})
    
    @property
    def category_colors(self):
        """Get the category colors dict"""
        return self.data_store.get(self.colors_key, {})
    
    # -------------------------------------------------------------------------
    # Public Methods
    # -------------------------------------------------------------------------
    
    def refresh(self):
        """Refresh the container display"""
        # Clear existing widgets
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add items in order
        for idx, item_data in enumerate(self.items):
            try:
                if item_data.get('type') == 'bookmark':
                    widget = self._create_bookmark_widget(item_data, idx)
                elif item_data.get('type') == 'category':
                    widget = self._create_category_widget(item_data, idx)
                else:
                    continue
                
                if widget:
                    self.items_layout.addWidget(widget)
            except Exception as e:
                logger.error(f"Error creating widget for item {idx}: {e}")
        
        # Add stretch at the end
        self.items_layout.addStretch()
        
        # Update button widths for vertical orientation
        if self.orientation == 'vertical':
            # Use a timer to update after layout is complete
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._update_button_widths)
    
    def add_bookmark(self, bookmark_data, insert_at=None):
        """Add a standalone bookmark to the container"""
        new_item = {
            'type': 'bookmark',
            'data': bookmark_data
        }
        
        items = self.data_store.setdefault(self.items_key, [])
        
        if insert_at is not None and 0 <= insert_at <= len(items):
            items.insert(insert_at, new_item)
        else:
            items.append(new_item)
        
        self._save_and_refresh()
    
    def add_category(self, category_name, category_items=None, color=None, insert_at=None):
        """Add a category to the container"""
        # Ensure categories dict exists
        categories = self.data_store.setdefault(self.categories_key, {})
        
        # Don't add if already exists
        if category_name in categories:
            return False
        
        # Add category data
        categories[category_name] = category_items or []
        
        # Add color if provided
        if color:
            colors = self.data_store.setdefault(self.colors_key, {})
            colors[category_name] = color
        
        # Add to items list
        new_item = {
            'type': 'category',
            'name': category_name
        }
        
        items = self.data_store.setdefault(self.items_key, [])
        
        if insert_at is not None and 0 <= insert_at <= len(items):
            items.insert(insert_at, new_item)
        else:
            items.append(new_item)
        
        self._save_and_refresh()
        return True
    
    def remove_item(self, index):
        """Remove an item by index"""
        items = self.items
        if 0 <= index < len(items):
            item = items[index]
            
            # If it's a category, also remove from categories dict and colors
            if item.get('type') == 'category':
                category_name = item.get('name')
                if category_name:
                    categories = self.categories
                    if category_name in categories:
                        del categories[category_name]
                    colors = self.category_colors
                    if category_name in colors:
                        del colors[category_name]
            
            items.pop(index)
            self._save_and_refresh()
    
    def remove_category(self, category_name):
        """Remove a category by name"""
        # Find and remove from items list
        items = self.items
        for i, item in enumerate(items):
            if item.get('type') == 'category' and item.get('name') == category_name:
                items.pop(i)
                break
        
        # Remove from categories dict
        categories = self.categories
        if category_name in categories:
            del categories[category_name]
        
        # Remove color
        colors = self.category_colors
        if category_name in colors:
            del colors[category_name]
        
        self._save_and_refresh()
    
    def rename_category(self, old_name, new_name):
        """Rename a category"""
        if old_name == new_name:
            return False
        
        categories = self.categories
        if new_name in categories:
            return False  # Already exists
        
        # Rename in categories dict
        if old_name in categories:
            categories[new_name] = categories.pop(old_name)
        
        # Rename in items list
        for item in self.items:
            if item.get('type') == 'category' and item.get('name') == old_name:
                item['name'] = new_name
                break
        
        # Transfer color
        colors = self.category_colors
        if old_name in colors:
            colors[new_name] = colors.pop(old_name)
        
        self._save_and_refresh()
        return True
    
    def set_category_color(self, category_name, color):
        """Set the color for a category"""
        colors = self.data_store.setdefault(self.colors_key, {})
        colors[category_name] = color
        self._save_and_refresh()
    
    def move_item(self, from_index, to_index):
        """Move an item from one position to another"""
        items = self.items
        if 0 <= from_index < len(items) and 0 <= to_index <= len(items):
            item = items.pop(from_index)
            # Adjust to_index if needed
            if to_index > from_index:
                to_index -= 1
            items.insert(to_index, item)
            self._save_and_refresh()
    
    # -------------------------------------------------------------------------
    # Widget Creation
    # -------------------------------------------------------------------------
    
    def _create_bookmark_widget(self, item_data, index):
        """Create a widget for a standalone bookmark"""
        bookmark_data = item_data.get('data', {})
        
        btn = StandaloneBookmarkButton(
            bookmark_data=bookmark_data,
            item_index=index,
            parent=self.items_container,
            container=self,
            orientation=self.orientation
        )
        btn.clicked_path.connect(self.item_clicked.emit)
        btn.double_clicked_path.connect(self.item_double_clicked.emit)
        
        return btn
    
    def _create_category_widget(self, item_data, index):
        """Create a widget for a category"""
        category_name = item_data.get('name', '')
        if not category_name:
            return None
        
        category_items = self.categories.get(category_name, [])
        category_color = self.category_colors.get(category_name, None)
        
        btn = CategoryButton(
            category_name=category_name,
            category_items=category_items,
            item_index=index,
            parent=self.items_container,
            data_manager=self,
            source_location=self.location,
            orientation=self.orientation,
            color=category_color
        )
        btn.item_clicked.connect(self.item_clicked.emit)
        
        return btn
    
    # -------------------------------------------------------------------------
    # Data Manager Interface (for CategoryButton compatibility)
    # -------------------------------------------------------------------------
    
    @property
    def bookmarks_data(self):
        """Alias for data_store (for CategoryButton compatibility when location='bar')"""
        return self.data_store
    
    @property
    def custom_quick_links(self):
        """Alias for data_store (for CategoryButton compatibility when location='sidebar')"""
        return self.data_store
    
    def save_bookmarks(self):
        """Save data (for CategoryButton compatibility)"""
        self._save()
    
    def save_quick_links(self):
        """Save data (for CategoryButton compatibility)"""
        self._save()
    
    def refresh_bookmarks(self):
        """Refresh display (for CategoryButton compatibility)"""
        self.refresh()
    
    def refresh_quick_links_list(self):
        """Refresh display (for CategoryButton compatibility)"""
        self.refresh()
    
    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------
    
    def _save(self):
        """Save data using the callback"""
        if self.save_callback:
            self.save_callback()
    
    def _save_and_refresh(self):
        """Save data and refresh display"""
        self._save()
        self.refresh()
    
    def _show_container_context_menu(self, pos):
        """Show context menu for empty space in the container"""
        menu = QMenu(self)
        menu.setStyleSheet(CATEGORY_CONTEXT_MENU_STYLE)
        
        # Add new category
        add_category_action = menu.addAction("📁 New Category")
        
        action = menu.exec(self.items_container.mapToGlobal(pos))
        
        if action == add_category_action:
            self._prompt_new_category()
    
    def _prompt_new_category(self):
        """Prompt user to create a new category"""
        name, ok = QInputDialog.getText(
            self,
            "New Category",
            "Enter category name:",
            QLineEdit.EchoMode.Normal,
            ""
        )
        
        if ok and name:
            name = name.strip()
            if name:
                if name in self.categories:
                    show_styled_warning(self, "Duplicate", f"Category '{name}' already exists.")
                else:
                    self.add_category(name)
    
    # -------------------------------------------------------------------------
    # Drag and Drop
    # -------------------------------------------------------------------------
    
    def dragEnterEvent(self, event):
        """Accept drag events"""
        mime = event.mimeData()
        if (mime.hasFormat('application/x-container-item-index') or
            mime.hasFormat('application/x-bookmark-move') or
            mime.hasFormat('application/x-category-move') or
            mime.hasUrls()):
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        """Handle drag move - show drop indicator"""
        mime = event.mimeData()
        if (mime.hasFormat('application/x-container-item-index') or
            mime.hasFormat('application/x-bookmark-move') or
            mime.hasFormat('application/x-category-move') or
            mime.hasUrls()):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
            self._hide_drop_indicator()
    
    def dragLeaveEvent(self, event):
        """Hide drop indicator when drag leaves"""
        self._hide_drop_indicator()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        """
        Handle drop events - supports internal reordering and cross-bar moves.
        
        Cross-bar moves are handled automatically via the BookmarkContainerRegistry.
        When an item is dropped from another container, this method:
        1. Adds the item to this container
        2. Finds the source container via the registry
        3. Removes the item from the source container
        """
        self._hide_drop_indicator()
        mime = event.mimeData()
        
        # Calculate drop index based on position
        drop_index = self._calculate_drop_index(event.position().toPoint())
        
        # Check for cross-bar moves FIRST (before internal reordering)
        # This prevents x-container-item-index from catching cross-bar drops
        
        # Category move (check source location to determine if cross-bar)
        if mime.hasFormat('application/x-category-move'):
            try:
                category_data = json.loads(mime.data('application/x-category-move').data().decode())
                source_location = category_data.get('source_location', category_data.get('source', ''))
                
                # Determine if this is from a different container
                is_cross_bar = self._is_cross_bar_source(source_location)
                
                if is_cross_bar:
                    # Handle cross-bar move
                    if self._handle_cross_bar_category_move(category_data, drop_index):
                        event.acceptProposedAction()
                        return
                    # Fallback: emit signal
                    category_data['_drop_index'] = drop_index
                    self.category_dropped.emit(category_data)
                    event.acceptProposedAction()
                    return
                # Not cross-bar - fall through to internal reorder
            except Exception as e:
                logger.error(f"Error handling category drop: {e}")
        
        # Bookmark move (check source location to determine if cross-bar)
        if mime.hasFormat('application/x-bookmark-move'):
            try:
                drag_data = json.loads(mime.data('application/x-bookmark-move').data().decode())
                source_location = drag_data.get('source_location', drag_data.get('source', ''))
                source_category = drag_data.get('source_category', '')
                
                # Determine if this is from a different container
                is_cross_bar = self._is_cross_bar_source(source_location)
                # Also consider it cross-bar if coming from a category (even same container)
                is_from_category = source_category and source_category != '__CONTAINER__'
                
                if is_cross_bar or is_from_category:
                    bookmark = drag_data.get('bookmark', {})
                    # Handle cross-bar or category-to-bar move
                    if self._handle_cross_bar_bookmark_move(bookmark, source_category, source_location, drop_index):
                        event.acceptProposedAction()
                        return
                    # Fallback: emit signal
                    bookmark['_drop_index'] = drop_index
                    bookmark['_source_category'] = source_category
                    bookmark['source_category'] = source_category
                    bookmark['source_location'] = source_location
                    self.bookmark_dropped.emit(bookmark)
                    event.acceptProposedAction()
                    return
                # Not cross-bar and not from category - fall through to internal reorder
            except Exception as e:
                logger.error(f"Error handling bookmark drop: {e}")
        
        # Internal reordering (same container, standalone items only)
        if mime.hasFormat('application/x-container-item-index'):
            try:
                from_index = int(mime.data('application/x-container-item-index').data().decode())
                if from_index != drop_index:
                    self.move_item(from_index, drop_index)
                    self.item_reordered.emit(from_index, drop_index)
                event.acceptProposedAction()
                return
            except Exception as e:
                logger.error(f"Error in internal reorder: {e}")
        
        # File/folder drops - emit signal for parent to handle
        if mime.hasUrls():
            for url in mime.urls():
                path = url.toLocalFile()
                if path:
                    self.file_dropped.emit({'path': path, '_drop_index': drop_index})
            event.acceptProposedAction()
            return
        
        event.ignore()
    
    def _is_cross_bar_source(self, source_location):
        """
        Check if the source location represents a different container than this one.
        Returns True if the drag is from a different bar/sidebar.
        """
        if not source_location:
            return False
        
        # Normalize the source location
        if source_location in ('bar', 'sidebar'):
            src_loc = source_location
        elif 'sidebar' in str(source_location) or 'quick_links' in str(source_location):
            src_loc = 'sidebar'
        elif 'bar' in str(source_location):
            src_loc = 'bar'
        else:
            return False
        
        # Compare with this container's location
        return src_loc != self.location
    
    def _handle_cross_bar_bookmark_move(self, bookmark, source_category, source_location, drop_index):
        """
        Handle moving a bookmark from another container to this one.
        Returns True if handled, False to fall back to signal emission.
        """
        # Determine the source container location
        if source_location in ('bar', 'sidebar'):
            src_container_location = source_location
        elif 'bar' in str(source_location):
            src_container_location = 'bar'
        elif 'sidebar' in str(source_location) or 'quick_links' in str(source_location):
            src_container_location = 'sidebar'
        else:
            return False  # Can't determine source
        
        # Check if this is a standalone bookmark (not from a category)
        is_standalone = source_category in ('__CONTAINER__', '', None)
        
        # Don't process if source is same as target AND it's a standalone bookmark
        # (internal reordering is handled separately via x-container-item-index)
        if src_container_location == self.location and is_standalone:
            return False
        
        # Get source container from registry
        source_container = BookmarkContainerRegistry.get(src_container_location)
        if not source_container:
            logger.warning(f"Source container not found in registry: {src_container_location}")
            return False
        
        # Create clean bookmark data
        clean_bookmark = {
            'name': bookmark.get('name', ''),
            'path': bookmark.get('path', '')
        }
        
        # Add to this container at the drop index
        self.add_bookmark(clean_bookmark, insert_at=drop_index)
        
        # Remove from source
        if not is_standalone:
            # Remove from category in source container
            source_container.remove_bookmark_from_category(source_category, bookmark.get('path', ''))
        else:
            # Remove standalone bookmark from source container
            source_container.remove_item_by_path(bookmark.get('path', ''))
        
        logger.info(f"Moved bookmark '{clean_bookmark['name']}' from {src_container_location} to {self.location}")
        return True
    
    def _handle_cross_bar_category_move(self, category_data, drop_index):
        """
        Handle moving a category from another container to this one.
        Returns True if handled, False to fall back to signal emission.
        """
        source_location = category_data.get('source_location', category_data.get('source', ''))
        category_name = category_data.get('name', '')
        
        if not category_name:
            return False
        
        # Determine the source container location
        if source_location in ('bar', 'sidebar'):
            src_container_location = source_location
        elif 'bar' in str(source_location):
            src_container_location = 'bar'
        elif 'sidebar' in str(source_location) or 'quick_links' in str(source_location):
            src_container_location = 'sidebar'
        else:
            return False
        
        # Don't process if source is same as target
        if src_container_location == self.location:
            return False
        
        # Get source container from registry
        source_container = BookmarkContainerRegistry.get(src_container_location)
        if not source_container:
            logger.warning(f"Source container not found in registry: {src_container_location}")
            return False
        
        # Get category items from source
        source_categories = source_container.data_store.get(source_container.categories_key, {})
        category_items = source_categories.get(category_name, [])
        
        # Get category color from source
        source_colors = source_container.data_store.get(source_container.colors_key, {})
        category_color = source_colors.get(category_name)
        
        # Add category to this container
        self.add_category(category_name, category_items=category_items, color=category_color, insert_at=drop_index)
        
        # Remove from source container
        source_container.remove_category(category_name)
        
        logger.info(f"Moved category '{category_name}' from {src_container_location} to {self.location}")
        return True
    
    def remove_bookmark_from_category(self, category_name, path):
        """Remove a bookmark from a category by its path"""
        categories = self.data_store.get(self.categories_key, {})
        if category_name in categories:
            items = categories[category_name]
            for i, item in enumerate(items):
                if item.get('path') == path:
                    items.pop(i)
                    break
            if self.save_callback:
                self.save_callback()
            self.refresh()
    
    def remove_item_by_path(self, path):
        """Remove an item from the bar_items list by its path"""
        items = self.data_store.get(self.items_key, [])
        for i, item in enumerate(items):
            if item.get('type') == 'bookmark' and item.get('path') == path:
                items.pop(i)
                break
            # Also check for nested bookmark data structure
            if item.get('type') == 'bookmark' and item.get('data', {}).get('path') == path:
                items.pop(i)
                break
        if self.save_callback:
            self.save_callback()
        self.refresh()
    
    def _calculate_drop_index(self, pos):
        """Calculate the index where an item should be inserted based on drop position"""
        # Get position relative to items container
        container_pos = self.items_container.mapFrom(self, pos)
        
        # Iterate through widgets to find insertion point
        for i in range(self.items_layout.count()):
            item = self.items_layout.itemAt(i)
            widget = item.widget()
            if widget:
                if self.orientation == 'horizontal':
                    widget_center = widget.x() + widget.width() / 2
                    if container_pos.x() < widget_center:
                        return i
                else:
                    widget_center = widget.y() + widget.height() / 2
                    if container_pos.y() < widget_center:
                        return i
        
        # Past all widgets - insert at end (before stretch)
        return max(0, self.items_layout.count() - 1)
    
    def _show_drop_indicator(self, pos):
        """Show the drop indicator at the appropriate position"""
        # Get position relative to items container
        container_pos = self.items_container.mapFrom(self, pos)
        
        # Find the position to show the indicator
        indicator_pos = None
        
        for i in range(self.items_layout.count()):
            item = self.items_layout.itemAt(i)
            widget = item.widget()
            if widget:
                widget_global = widget.mapToGlobal(widget.rect().topLeft())
                widget_pos = self.mapFromGlobal(widget_global)
                
                if self.orientation == 'horizontal':
                    widget_center = widget.x() + widget.width() / 2
                    if container_pos.x() < widget_center:
                        # Position indicator at left edge of this widget
                        indicator_pos = (widget_pos.x() - 2, widget_pos.y())
                        break
                else:
                    widget_center = widget.y() + widget.height() / 2
                    if container_pos.y() < widget_center:
                        # Position indicator at top edge of this widget
                        indicator_pos = (widget_pos.x(), widget_pos.y() - 2)
                        break
        
        # If no position found, put at end of last widget
        if indicator_pos is None and self.items_layout.count() > 0:
            last_item = None
            for i in range(self.items_layout.count() - 1, -1, -1):
                item = self.items_layout.itemAt(i)
                if item and item.widget():
                    last_item = item.widget()
                    break
            
            if last_item:
                last_global = last_item.mapToGlobal(last_item.rect().topLeft())
                last_pos = self.mapFromGlobal(last_global)
                
                if self.orientation == 'horizontal':
                    indicator_pos = (last_pos.x() + last_item.width() + 2, last_pos.y())
                else:
                    indicator_pos = (last_pos.x(), last_pos.y() + last_item.height() + 2)
        
        if indicator_pos:
            self.drop_indicator.move(indicator_pos[0], indicator_pos[1])
            self.drop_indicator.raise_()
            self.drop_indicator.show()
    
    def _hide_drop_indicator(self):
        """Hide the drop indicator"""
        self.drop_indicator.hide()
