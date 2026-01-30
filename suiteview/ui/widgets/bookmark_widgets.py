"""
Unified Bookmark Widgets for SuiteView

This module provides all bookmark bar UI components. Bookmark bars can be placed
anywhere in the app (top, side, bottom, etc.) and items can be freely dragged
between any bars as if they were one unified system.

Classes:
- BookmarkContainerRegistry: Registry for cross-bar drag/drop communication
- BookmarkContainer: Main container widget for bookmarks and categories
- CategoryButton: Draggable category button with popup support
- CategoryPopup: Popup window showing category contents
- CategoryBookmarkButton: Bookmark button inside category popups
- StandaloneBookmarkButton: Standalone bookmark button

Architecture:
- Each bookmark bar has an integer ID (0, 1, 2, ...)
- Bar 0 = default horizontal (top) bar
- Bar 1 = default vertical (side) bar
- Data stored in ~/.suiteview/bookmarks.json via BookmarkDataManager
- BookmarkContainerRegistry enables cross-bar drag/drop between any bars
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, Callable

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

# Themed colors (first row) - SuiteView brand colors
THEMED_COLORS = [
    # Blue gradient with gold - main theme
    "theme:blue_gold",
    # Gold gradient with blue - inverted theme  
    "theme:gold_blue",
    # Navy with silver trim - professional
    "theme:navy_silver",
    # Teal with coral - complementary
    "theme:teal_coral",
]

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
    """Darken a hex color by a factor (0-1, lower = darker)
    
    Also handles themed colors like 'theme:blue_gold' by returning
    the theme's border color.
    """
    if not hex_color:
        return "#7b2d8e"  # Default purple
    
    # Handle themed colors
    if hex_color.startswith('theme:'):
        # Return the border color for themed categories
        theme_borders = {
            'theme:blue_gold': '#B8860B',    # Darker gold
            'theme:gold_blue': '#0A2D5C',    # Darker blue
            'theme:navy_silver': '#808080',  # Darker silver
            'theme:teal_coral': '#CC5F40',   # Darker coral
        }
        return theme_borders.get(hex_color, '#7b2d8e')
    
    # Handle regular hex colors
    if not hex_color.startswith('#'):
        return "#7b2d8e"  # Default purple for invalid colors
    
    hex_color = hex_color.lstrip('#')
    try:
        r = int(int(hex_color[0:2], 16) * factor)
        g = int(int(hex_color[2:4], 16) * factor)
        b = int(int(hex_color[4:6], 16) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"
    except (ValueError, IndexError):
        return "#7b2d8e"  # Default purple on error


def lighten_color(hex_color, factor=0.3):
    """Lighten a hex color by mixing with white
    
    Also handles themed colors like 'theme:blue_gold' by returning
    a lighter version of the theme's border color.
    """
    if not hex_color:
        return "#E1BEE7"  # Light purple
    
    # Handle themed colors
    if hex_color.startswith('theme:'):
        # Return a lighter version for themed categories
        theme_lights = {
            'theme:blue_gold': '#FFD700',    # Bright gold
            'theme:gold_blue': '#4A7DC4',    # Lighter blue
            'theme:navy_silver': '#D0D0D0',  # Light silver
            'theme:teal_coral': '#FF9F7F',   # Light coral
        }
        return theme_lights.get(hex_color, '#E1BEE7')
    
    # Handle regular hex colors
    if not hex_color.startswith('#'):
        return "#E1BEE7"  # Light purple for invalid colors
    
    hex_color = hex_color.lstrip('#')
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = int(r + (255 - r) * factor)
        g = int(g + (255 - g) * factor)
        b = int(b + (255 - b) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"
    except (ValueError, IndexError):
        return "#E1BEE7"  # Light purple on error


def get_themed_style(theme_id, orientation='horizontal'):
    """Generate category button stylesheet for themed colors"""
    # Sidebar (vertical) uses smaller margins
    margin = "1px 0px" if orientation == 'vertical' else "0px"
    
    # Theme definitions: (gradient_start, gradient_end, border, text_color)
    themes = {
        'theme:blue_gold': ('#1E5BA8', '#082B5C', '#D4A017', '#D4A017'),
        'theme:gold_blue': ('#D4A017', '#8B6914', '#0D3A7A', '#0D3A7A'),
        'theme:navy_silver': ('#0A1E3E', '#050F1F', '#C0C0C0', '#C0C0C0'),
        'theme:teal_coral': ('#008080', '#004040', '#FF7F50', '#FF7F50'),
    }
    
    if theme_id not in themes:
        return get_category_button_style(DEFAULT_CATEGORY_COLOR, orientation)
    
    grad_start, grad_end, border, text = themes[theme_id]
    
    return f"""
        QPushButton {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {grad_start}, stop:1 {grad_end});
            border: 2px solid {border};
            border-radius: 10px;
            padding: 3px 10px;
            margin: {margin};
            text-align: left;
            font-size: 9pt;
            font-weight: bold;
            color: {text};
        }}
        QPushButton:hover {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {lighten_color(grad_start, 0.2)}, stop:1 {grad_start});
            border-color: {lighten_color(border, 0.3)};
        }}
        QPushButton:pressed {{
            background-color: {grad_end};
        }}
        QToolTip {{
            background-color: #FFFFDD;
            color: #333333;
            border: 1px solid #888888;
            padding: 4px;
            font-size: 9pt;
        }}
    """


def get_category_button_style(color, orientation='horizontal'):
    """Generate category button stylesheet based on color (or theme)"""
    # Handle themed colors
    if color and color.startswith('theme:'):
        return get_themed_style(color, orientation)
    
    # Handle None or invalid color
    if not color or not color.startswith('#'):
        color = DEFAULT_CATEGORY_COLOR
    
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
    A popup with themed colors and a 6x6 grid of colors for category customization.
    """
    
    color_selected = pyqtSignal(str)  # Emits hex color or theme identifier
    
    def __init__(self, parent=None, current_color=None):
        super().__init__(parent, Qt.WindowType.Popup)
        
        self.current_color = current_color
        
        # Use current color for border, or default blue
        if current_color and current_color.startswith('theme:'):
            border_color = "#D4A017"  # Gold for themed
        else:
            border_color = darken_color(current_color, 0.7) if current_color else "#0D3A7A"
        
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
        layout.setSpacing(6)
        
        # Title
        from PyQt6.QtWidgets import QLabel
        title = QLabel("Select Category Color")
        title.setStyleSheet("font-weight: bold; font-size: 9pt; color: #333; border: none;")
        layout.addWidget(title)
        
        # ====== THEMED COLORS SECTION ======
        themed_label = QLabel("SuiteView Themes")
        themed_label.setStyleSheet("font-size: 8pt; color: #666; border: none; margin-top: 4px;")
        layout.addWidget(themed_label)
        
        from PyQt6.QtWidgets import QGridLayout
        themed_grid = QGridLayout()
        themed_grid.setSpacing(4)
        
        # Theme button definitions with gradient previews
        theme_defs = [
            ("theme:blue_gold", "Blue & Gold", "#1E5BA8", "#D4A017"),
            ("theme:gold_blue", "Gold & Blue", "#D4A017", "#0D3A7A"),
            ("theme:navy_silver", "Navy & Silver", "#0A1E3E", "#C0C0C0"),
            ("theme:teal_coral", "Teal & Coral", "#008080", "#FF7F50"),
        ]
        
        for i, (theme_id, tooltip, color1, color2) in enumerate(theme_defs):
            btn = QPushButton()
            btn.setFixedSize(36, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            
            # Highlight current theme
            border = "3px solid #333" if theme_id == current_color else "1px solid #888"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {color1}, stop:1 {color2});
                    border: {border};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid #D4A017;
                }}
            """)
            
            btn.clicked.connect(lambda checked, t=theme_id: self._select_color(t))
            themed_grid.addWidget(btn, 0, i)
        
        layout.addLayout(themed_grid)
        
        # ====== SOLID COLORS SECTION ======
        colors_label = QLabel("Solid Colors")
        colors_label.setStyleSheet("font-size: 8pt; color: #666; border: none; margin-top: 4px;")
        layout.addWidget(colors_label)
        
        # Color grid - 6x6
        grid = QGridLayout()
        grid.setSpacing(4)
        
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
                    border: 2px solid #D4A017;
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
                 data_manager=None, source_bar_id: int = 0):
        """
        Args:
            bookmark_data: dict with 'name', 'path', optionally 'type'
            source_category: name of the category this bookmark belongs to
            parent: parent widget
            popup: reference to the popup window (for closing on actions)
            data_manager: BookmarkContainer instance managing the data
            source_bar_id: integer ID of the bookmark bar (0, 1, 2, ...)
        """
        super().__init__(parent)
        
        self.bookmark_data = bookmark_data
        self.source_category = source_category
        self.parent_popup = popup
        self.data_manager = data_manager
        self.source_bar_id = source_bar_id
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
        
        # Save changes via data manager (BookmarkContainer)
        if self.data_manager:
            self.data_manager._save_and_refresh()
        
        # Close popup to show refreshed content
        if self.parent_popup:
            self.parent_popup.close()

    def _remove_bookmark(self):
        """Remove this bookmark from its category"""
        try:
            if not self.data_manager:
                return
            
            # Use BookmarkContainer's method to remove bookmark from category
            self.data_manager.remove_bookmark_from_category(
                self.source_category, 
                self.bookmark_data.get('path', '')
            )
            
            # Close popup
            if self.parent_popup:
                self.parent_popup.close()
                
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
        
        # Bookmark move format - includes source bar ID for cross-bar detection
        drag_data = {
            'bookmark': self.bookmark_data,
            'source_category': self.source_category,
            'source_bar_id': self.source_bar_id  # Integer bar ID
        }
        mime_data.setData('application/x-bookmark-move', json.dumps(drag_data).encode())
        
        mime_data.setText(f"Move: {self.bookmark_data.get('name', 'bookmark')}")
        
        drag.setMimeData(mime_data)
        
        logger.info(f"Dragging bookmark '{self.bookmark_data.get('name')}' from category '{self.source_category}' (bar {self.source_bar_id})")
        result = drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        
        # Close popup if drag was successful
        if result == Qt.DropAction.MoveAction and self.parent_popup:
            self.parent_popup.close_entire_chain()


# =============================================================================
# SubcategoryButton - Button for subcategories inside popups (shows ▸ arrow)
# =============================================================================

class SubcategoryButton(QPushButton):
    """
    Button for subcategories displayed inside category popups.
    Shows expansion arrow (▸) and opens nested popup to the right on click.
    """
    
    subcategory_clicked = pyqtSignal(str)  # Emits subcategory name
    item_clicked = pyqtSignal(str)  # Forward item clicks from nested popups
    
    def __init__(self, subcategory_name, parent_category, parent=None, popup=None,
                 data_manager=None, source_bar_id: int = 0, color=None):
        """
        Args:
            subcategory_name: name of the subcategory
            parent_category: name of the parent category
            parent: parent widget
            popup: reference to the parent popup window
            data_manager: BookmarkContainer instance managing the data
            source_bar_id: integer ID of the bookmark bar
            color: hex color string for the subcategory
        """
        super().__init__(parent)
        
        self.subcategory_name = subcategory_name
        self.parent_category = parent_category
        self.parent_popup = popup
        self.data_manager = data_manager
        self.source_bar_id = source_bar_id
        self.subcategory_color = color
        self.drag_start_pos = None
        self.nested_popup = None
        
        # Set display text with folder icon and expansion arrow
        self.setText(f"🗄 {subcategory_name} ▸")
        
        # Get item count for tooltip
        item_count = self._get_item_count()
        self.setToolTip(f"{item_count} item(s)")
        
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # Apply subcategory style with color
        self._apply_style()
        
        # Accept drops for nesting
        self.setAcceptDrops(True)
    
    def _get_item_count(self):
        """Get the total item count (bookmarks + subcategories)"""
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        categories = manager.get_global_categories()
        cat_data = categories.get(self.subcategory_name, {})
        if isinstance(cat_data, dict):
            items = cat_data.get('items', [])
            subcats = cat_data.get('subcategories', [])
            return len(items) + len(subcats)
        elif isinstance(cat_data, list):
            return len(cat_data)
        return 0
    
    def _apply_style(self):
        """Apply button style based on color"""
        color = self.subcategory_color or DEFAULT_CATEGORY_COLOR
        light_color = lighten_color(color, 0.4)
        dark_color = darken_color(color, 0.7)
        border_color = darken_color(color, 0.6)
        hover_color = lighten_color(color, 0.2)
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {light_color}, stop:1 {color});
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 3px 8px;
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
        """)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_start_pos:
            distance = (event.pos() - self.drag_start_pos).manhattanLength()
            if distance < 10:
                # It was a click - toggle nested popup
                self._toggle_nested_popup()
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
        
        # Start drag for category move
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Get subcategory items from global categories
        items = []
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        if manager:
            categories = manager.get_global_categories()
            cat_data = categories.get(self.subcategory_name, {})
            if isinstance(cat_data, dict):
                items = cat_data.get('items', [])
            elif isinstance(cat_data, list):
                items = cat_data
        
        # Category move data
        category_data = {
            'name': self.subcategory_name,
            'items': items,
            'source_bar_id': self.source_bar_id,
            'source_parent_category': self.parent_category,
            'color': self.subcategory_color,
            'is_subcategory': True
        }
        mime_data.setData('application/x-category-move', json.dumps(category_data).encode())
        
        drag.setMimeData(mime_data)
        
        logger.info(f"Dragging subcategory '{self.subcategory_name}' from parent '{self.parent_category}'")
        result = drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        
        # Close popup chain if drag was successful
        if result == Qt.DropAction.MoveAction and self.parent_popup:
            self.parent_popup.close_entire_chain()
    
    def _toggle_nested_popup(self):
        """Toggle the nested popup for this subcategory"""
        if self.nested_popup and self.nested_popup.isVisible():
            self.nested_popup.hide()
            return
        
        self._show_nested_popup()
    
    def _show_nested_popup(self):
        """Show nested popup to the right"""
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        
        # Get subcategory data from global categories
        categories = manager.get_global_categories()
        cat_data = categories.get(self.subcategory_name, {})
        
        # Handle both old (list) and new (dict) formats
        if isinstance(cat_data, dict):
            items = cat_data.get('items', [])
            subcategories = cat_data.get('subcategories', [])
        else:
            items = cat_data if isinstance(cat_data, list) else []
            subcategories = []
        
        # Create or reuse popup
        if not self.nested_popup:
            self.nested_popup = CategoryPopup(
                category_name=self.subcategory_name,
                category_items=items,
                subcategories=subcategories,
                parent_widget=self,
                data_manager=self.data_manager,
                source_bar_id=self.source_bar_id,
                color=self.subcategory_color,
                parent_popup=self.parent_popup,
                nesting_level=(self.parent_popup.nesting_level + 1) if self.parent_popup else 1
            )
            self.nested_popup.item_clicked.connect(self.item_clicked.emit)
            self.nested_popup.popup_closed.connect(self._on_nested_popup_closed)
        
        # Position to the right of this button
        global_pos = self.mapToGlobal(self.rect().topRight())
        
        # Adjust for screen boundaries
        screen = self.screen()
        if screen:
            screen_geo = screen.availableGeometry()
            popup_width = self.nested_popup.width() if self.nested_popup.width() > 0 else 250
            
            # If popup would go off right edge, position to the left instead
            if global_pos.x() + popup_width > screen_geo.right():
                global_pos = self.mapToGlobal(self.rect().topLeft())
                global_pos.setX(global_pos.x() - popup_width)
        
        self.nested_popup.move(global_pos)
        self.nested_popup.show()
    
    def _on_nested_popup_closed(self):
        """Handle nested popup closing"""
        pass  # Keep reference for reuse
    
    def _show_context_menu(self, pos):
        """Show context menu for this subcategory"""
        menu = QMenu(self)
        
        border_color = darken_color(self.subcategory_color, 0.7) if self.subcategory_color else "#7b2d8e"
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
        new_subcat_action = menu.addAction("📁 New Subcategory")
        menu.addSeparator()
        remove_action = menu.addAction("🗑️ Remove from here")
        delete_action = menu.addAction("❌ Delete permanently")
        
        action = menu.exec(self.mapToGlobal(pos))
        
        if action == rename_action:
            self._rename_subcategory()
        elif action == color_action:
            self._change_color()
        elif action == new_subcat_action:
            self._create_new_subcategory()
        elif action == remove_action:
            self._remove_from_parent()
        elif action == delete_action:
            self._delete_permanently()
    
    def _rename_subcategory(self):
        """Rename this subcategory (global rename)"""
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Subcategory",
            f"Enter new name for '{self.subcategory_name}':",
            QLineEdit.EchoMode.Normal,
            self.subcategory_name
        )
        
        if ok and new_name:
            new_name = new_name.strip()
            if new_name == self.subcategory_name:
                return
            
            from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
            manager = get_bookmark_manager()
            
            if manager.category_exists(new_name):
                show_styled_warning(self, "Duplicate", f"Category '{new_name}' already exists.")
                return
            
            if manager.rename_category(self.subcategory_name, new_name):
                manager.save()
                if self.data_manager:
                    self.data_manager._save_and_refresh()
            
            if self.parent_popup:
                self.parent_popup.close_entire_chain()
    
    def _change_color(self):
        """Change subcategory color"""
        picker = ColorPickerPopup(self, self.subcategory_color)
        picker.color_selected.connect(self._on_color_selected)
        
        global_pos = self.mapToGlobal(self.rect().bottomLeft())
        picker.move(global_pos)
        picker.show()
    
    def _on_color_selected(self, color):
        """Handle color selection"""
        self.subcategory_color = color
        self._apply_style()
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        colors = manager.get_global_colors()
        colors[self.subcategory_name] = color
        manager.save()
        
        if self.data_manager:
            self.data_manager.refresh()
    
    def _create_new_subcategory(self):
        """Create a new subcategory inside this subcategory"""
        name, ok = QInputDialog.getText(
            self,
            "New Subcategory",
            f"Enter name for new subcategory in '{self.subcategory_name}':",
            QLineEdit.EchoMode.Normal,
            ""
        )
        
        if ok and name:
            name = name.strip()
            if not name:
                return
            
            from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
            manager = get_bookmark_manager()
            
            if manager.category_exists(name):
                show_styled_warning(self, "Duplicate", f"Category '{name}' already exists.")
                return
            
            # Create new category globally
            manager.create_category(name)
            
            # Make it a subcategory of this category
            manager.make_subcategory(name, self.subcategory_name)
            manager.save()
            
            if self.data_manager:
                self.data_manager._save_and_refresh()
            
            if self.parent_popup:
                self.parent_popup.close_entire_chain()
    
    def _remove_from_parent(self):
        """Remove this subcategory from parent (keeps category data)"""
        if not self.data_manager:
            return
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        categories = manager.get_global_categories()
        parent_data = categories.get(self.parent_category, {})
        
        if isinstance(parent_data, dict):
            subcats = parent_data.get('subcategories', [])
            if self.subcategory_name in subcats:
                subcats.remove(self.subcategory_name)
            # Also remove from item_order if present
            item_order = parent_data.get('item_order', [])
            parent_data['item_order'] = [
                i for i in item_order
                if not (i.get('type') == 'subcategory' and i.get('name') == self.subcategory_name)
            ]
        
        manager.save()
        if self.data_manager:
            self.data_manager._save_and_refresh()
        
        if self.parent_popup:
            self.parent_popup.close_entire_chain()
    
    def _delete_permanently(self):
        """Delete this subcategory and all contents permanently"""
        # Get item count for warning
        item_count = self._get_item_count()
        
        message = f"Are you sure you want to permanently delete '{self.subcategory_name}'?"
        if item_count > 0:
            message += f"\n\nThis will delete {item_count} item(s) inside it."
        
        if not show_styled_question(self, "Delete Subcategory", message):
            return
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        
        # Use global delete which handles recursive deletion
        manager.delete_category(self.subcategory_name, recursive=True)
        manager.save()
        
        if self.data_manager:
            self.data_manager._save_and_refresh()
        
        if self.parent_popup:
            self.parent_popup.close_entire_chain()
    
    # Drag-drop handling for accepting drops onto the subcategory
    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat('application/x-bookmark-move') or mime.hasFormat('application/x-category-move') or mime.hasUrls():
            # Check for circular reference when receiving category
            if mime.hasFormat('application/x-category-move'):
                try:
                    cat_data = json.loads(mime.data('application/x-category-move').data().decode())
                    dragged_name = cat_data.get('name', '')
                    # Prevent dropping category into itself or its descendants
                    if self._is_descendant_of(dragged_name):
                        event.ignore()
                        return
                except:
                    pass
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def _is_descendant_of(self, ancestor_name):
        """Check if this subcategory is a descendant of the given category"""
        if self.subcategory_name == ancestor_name:
            return True
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        
        # Use global categories for the check
        return manager._is_ancestor_of(ancestor_name, self.subcategory_name)
    
    def dropEvent(self, event):
        """Handle drops onto this subcategory"""
        mime = event.mimeData()
        
        if mime.hasFormat('application/x-bookmark-move'):
            try:
                drag_data = json.loads(mime.data('application/x-bookmark-move').data().decode())
                bookmark = drag_data['bookmark']
                source = drag_data.get('source_category', '__CONTAINER__')
                source_bar_id = drag_data.get('source_bar_id')
                
                self._handle_bookmark_drop(bookmark, source, source_bar_id)
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error handling bookmark drop on subcategory: {e}")
                event.ignore()
        
        elif mime.hasFormat('application/x-category-move'):
            try:
                cat_data = json.loads(mime.data('application/x-category-move').data().decode())
                dragged_name = cat_data.get('name', '')
                
                # Prevent circular reference
                if self._is_descendant_of(dragged_name):
                    logger.warning(f"Cannot drop '{dragged_name}' into its descendant '{self.subcategory_name}'")
                    event.ignore()
                    return
                
                self._handle_category_drop(cat_data)
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error handling category drop on subcategory: {e}")
                event.ignore()
        
        elif mime.hasUrls():
            try:
                for url in mime.urls():
                    path = url.toLocalFile()
                    if path:
                        name = Path(path).name
                        bookmark = {'name': name, 'path': path}
                        self._handle_bookmark_drop(bookmark, '__NEW__', None)
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error handling URL drop on subcategory: {e}")
                event.ignore()
        else:
            event.ignore()
    
    def _handle_bookmark_drop(self, bookmark, source, source_bar_id):
        """Handle bookmark dropped onto this subcategory"""
        path = bookmark.get('path')
        if not path:
            return
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        categories = manager.get_global_categories()
        
        # Ensure this subcategory exists with proper structure
        if self.subcategory_name not in categories:
            categories[self.subcategory_name] = {"items": [], "subcategories": []}
        
        cat_data = categories[self.subcategory_name]
        if isinstance(cat_data, list):
            categories[self.subcategory_name] = {"items": cat_data, "subcategories": []}
            cat_data = categories[self.subcategory_name]
        
        items = cat_data.setdefault('items', [])
        
        # Check duplicate
        if any(b.get('path') == path for b in items):
            return
        
        # Add bookmark
        clean_bookmark = {k: v for k, v in bookmark.items() if not k.startswith('_')}
        items.append(clean_bookmark)
        
        # Also add to item_order if it exists
        item_order = cat_data.get('item_order', None)
        if item_order is not None:
            item_order.append({'type': 'bookmark', 'path': path})
        
        # Remove from source
        self._remove_bookmark_from_source(path, source, source_bar_id)
        
        manager.save()
        if self.data_manager:
            self.data_manager._save_and_refresh()
        
        if self.parent_popup:
            self.parent_popup.close_entire_chain()
    
    def _handle_category_drop(self, cat_data):
        """Handle category dropped onto this subcategory (making it a nested subcategory)"""
        dragged_name = cat_data.get('name', '')
        source_parent = cat_data.get('source_parent_category')
        source_bar_id = cat_data.get('source_bar_id')
        is_subcategory = cat_data.get('is_subcategory', False)
        
        if not dragged_name:
            return
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        
        # Check circular reference
        if manager._is_ancestor_of(dragged_name, self.subcategory_name):
            logger.warning(f"Cannot make '{dragged_name}' a subcategory of its descendant")
            return
        
        # Remove from old parent first if it was a subcategory
        if is_subcategory and source_parent:
            categories = manager.get_global_categories()
            parent_data = categories.get(source_parent, {})
            if isinstance(parent_data, dict):
                old_subcats = parent_data.get('subcategories', [])
                if dragged_name in old_subcats:
                    old_subcats.remove(dragged_name)
        
        # Make it a subcategory of this category
        if manager.make_subcategory(dragged_name, self.subcategory_name, source_bar_id):
            manager.save()
            if self.data_manager:
                self.data_manager._save_and_refresh()
            
            # Refresh source container if different
            if source_bar_id is not None and source_bar_id != self.source_bar_id:
                source_container = BookmarkContainerRegistry.get(source_bar_id)
                if source_container:
                    source_container.refresh()
        
        if self.parent_popup:
            self.parent_popup.close_entire_chain()
    
    def _remove_bookmark_from_source(self, path, source, source_bar_id):
        """Remove bookmark from its source location"""
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        
        is_cross_bar = source_bar_id is not None and source_bar_id != self.source_bar_id
        
        if is_cross_bar:
            source_container = BookmarkContainerRegistry.get(source_bar_id)
            if source_container:
                if source in ('__BAR__', '__CONTAINER__'):
                    source_container.remove_item_by_path(path)
                elif source and source != '__NEW__':
                    source_container.remove_bookmark_from_category(source, path)
        else:
            if source in ('__BAR__', '__CONTAINER__'):
                if self.data_manager:
                    self.data_manager.remove_item_by_path(path)
            elif source and source != '__NEW__':
                # Use global categories
                categories = manager.get_global_categories()
                cat_data = categories.get(source, {})
                if isinstance(cat_data, dict):
                    items = cat_data.get('items', [])
                    # Also remove from item_order if present
                    item_order = cat_data.get('item_order', [])
                    cat_data['item_order'] = [
                        i for i in item_order
                        if not (i.get('type') == 'bookmark' and i.get('path') == path)
                    ]
                elif isinstance(cat_data, list):
                    items = cat_data
                else:
                    items = []
                
                for i, b in enumerate(items):
                    if b.get('path') == path:
                        items.pop(i)
                        break


# =============================================================================
# CategoryPopup - Popup window showing category contents (supports nesting)
# =============================================================================

class CategoryPopup(QFrame):
    """
    Popup window for category contents.
    Supports nested categories with subcategories displayed as expandable items.
    Used by both top bar and sidebar categories.
    
    Key behaviors for nested categories:
    - Popup stays open until category button is clicked again (toggle)
    - Clicking outside does NOT close (enables drag into nested categories)
    - Clicking a bookmark closes the entire popup chain
    - Nested popups open to the right of their parent
    """
    
    item_clicked = pyqtSignal(str)
    popup_closed = pyqtSignal()
    
    def __init__(self, category_name, category_items, parent_widget=None,
                 data_manager=None, source_bar_id: int = 0, color=None,
                 subcategories=None, parent_popup=None, nesting_level=0):
        """
        Args:
            category_name: name of the category
            category_items: list of bookmark dicts
            parent_widget: parent widget for positioning
            data_manager: object managing the bookmark data (BookmarkContainer)
            source_bar_id: integer ID of the bookmark bar (0, 1, 2, ...)
            color: hex color string for the category border
            subcategories: list of subcategory names (for nested categories)
            parent_popup: reference to parent popup (for closing chain)
            nesting_level: depth of nesting (0 = top level)
        """
        # Use Tool window type instead of Popup - Popup windows get destroyed on hide
        # Tool windows stay alive and can be shown/hidden efficiently
        super().__init__(parent_widget, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        self.category_name = category_name
        self.category_items = category_items
        self.subcategories = subcategories or []
        self.data_manager = data_manager
        self.source_bar_id = source_bar_id
        self.category_color = color
        self.parent_popup = parent_popup
        self.nesting_level = nesting_level
        self.child_popups = []  # Track nested popups
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
        """Set up the popup UI with bookmarks and subcategories in unified order"""
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
        
        # Get category colors and data for subcategories (from global)
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        category_colors = manager.get_global_colors()
        global_categories = manager.get_global_categories()
        
        # Build unified display order
        # Check if category has item_order (new format) or fall back to old format
        cat_data = global_categories.get(self.category_name, {})
        if isinstance(cat_data, dict):
            item_order = cat_data.get('item_order', None)
        else:
            item_order = None
        
        # Build display list - unified_items contains tuples of (type, data)
        # type is 'subcategory' or 'bookmark'
        unified_items = []
        
        if item_order is not None:
            # New format: use item_order for display sequence
            for order_item in item_order:
                if order_item.get('type') == 'subcategory':
                    subcat_name = order_item.get('name')
                    if subcat_name and subcat_name in self.subcategories:
                        unified_items.append(('subcategory', subcat_name))
                elif order_item.get('type') == 'bookmark':
                    # Find bookmark by path
                    path = order_item.get('path')
                    for item in self.category_items:
                        if item.get('path') == path:
                            unified_items.append(('bookmark', item))
                            break
            
            # Add any items not in item_order (shouldn't happen but be safe)
            ordered_subcat_names = {i.get('name') for i in item_order if i.get('type') == 'subcategory'}
            ordered_bookmark_paths = {i.get('path') for i in item_order if i.get('type') == 'bookmark'}
            for subcat in self.subcategories:
                if subcat not in ordered_subcat_names:
                    unified_items.append(('subcategory', subcat))
            for item in self.category_items:
                if item.get('path') not in ordered_bookmark_paths:
                    unified_items.append(('bookmark', item))
        else:
            # Old format: subcategories first, then bookmarks
            for subcat_name in self.subcategories:
                unified_items.append(('subcategory', subcat_name))
            for item_data in self.category_items:
                unified_items.append(('bookmark', item_data))
        
        # Store unified items for drop index calculation
        self._unified_items = unified_items
        
        # Render items in unified order
        for item_type, item_data in unified_items:
            if item_type == 'subcategory':
                subcat_name = item_data
                subcat_color = category_colors.get(subcat_name)
                
                # Get subcategory data
                subcat_data = global_categories.get(subcat_name, {})
                if isinstance(subcat_data, dict):
                    subcat_items = subcat_data.get('items', [])
                    subcat_subcats = subcat_data.get('subcategories', [])
                else:
                    subcat_items = subcat_data if isinstance(subcat_data, list) else []
                    subcat_subcats = []
                
                btn = CategoryButton(
                    category_name=subcat_name,
                    category_items=subcat_items,
                    subcategories=subcat_subcats,
                    parent=self.container,
                    data_manager=self.data_manager,
                    source_bar_id=self.source_bar_id,
                    orientation='popup',  # Inside a popup
                    color=subcat_color,
                    parent_popup=self,
                    parent_category=self.category_name
                )
                btn.item_clicked.connect(self._on_item_clicked)
                self.container_layout.addWidget(btn)
            else:
                # Bookmark
                btn = CategoryBookmarkButton(
                    bookmark_data=item_data,
                    source_category=self.category_name,
                    parent=self.container,
                    popup=self,
                    data_manager=self.data_manager,
                    source_bar_id=self.source_bar_id
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
        item_count = len(unified_items)
        item_height = 28
        total_height = item_count * item_height + 8
        max_height = 400
        self.setFixedHeight(min(total_height, max_height))
    
    def _on_item_clicked(self, path):
        """Handle item click - closes entire popup chain"""
        if path:
            self.item_clicked.emit(path)
            self.close_entire_chain()
    
    def close_entire_chain(self):
        """Close this popup and all parent/child popups in the chain"""
        # Close all child popups first
        for child in self.child_popups:
            if child and hasattr(child, 'close_entire_chain'):
                child.close_entire_chain()
        self.child_popups.clear()
        
        # Hide this popup
        self.hide()
        self.popup_closed.emit()
        
        # Close parent chain
        if self.parent_popup and hasattr(self.parent_popup, 'close_entire_chain'):
            self.parent_popup.close_entire_chain()
    
    def register_child_popup(self, popup):
        """Register a child popup for chain management"""
        if popup not in self.child_popups:
            self.child_popups.append(popup)
    
    def _get_total_item_count(self):
        """Get total count of items (bookmarks + subcategories) for drop index calculation"""
        # Use unified items if available
        if hasattr(self, '_unified_items'):
            return len(self._unified_items)
        return len(self.subcategories) + len(self.category_items)
    
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
        mime = event.mimeData()
        if mime.hasFormat('application/x-bookmark-move') or mime.hasFormat('application/x-category-move'):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat('application/x-bookmark-move') or mime.hasFormat('application/x-category-move'):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        self._hide_drop_indicator()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        """Handle bookmark or category drop"""
        self._hide_drop_indicator()
        mime = event.mimeData()
        
        # Handle category drops (for reordering subcategories within this popup)
        if mime.hasFormat('application/x-category-move'):
            self._handle_category_drop_in_popup(event)
            return
        
        if not mime.hasFormat('application/x-bookmark-move'):
            event.ignore()
            return
        
        try:
            drag_data = json.loads(event.mimeData().data('application/x-bookmark-move').data().decode())
            bookmark = drag_data.get('bookmark', {})
            source_category = drag_data.get('source_category', '')
            source_bar_id = drag_data.get('source_bar_id')
            drop_idx = self.drop_index if self.drop_index >= 0 else self._get_drop_index(event.position().toPoint())
            
            if not bookmark or not bookmark.get('path'):
                event.ignore()
                return
            
            path = bookmark.get('path')
            
            # Check if same bar and same category (reordering within category)
            is_same_bar = source_bar_id == self.source_bar_id
            is_same_category = source_category == self.category_name
            
            if is_same_bar and is_same_category:
                # Reordering within same category - use item_order for unified positioning
                from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
                manager = get_bookmark_manager()
                if manager:
                    categories = manager.get_global_categories()
                    cat_data = categories.get(self.category_name, {})
                    if isinstance(cat_data, list):
                        categories[self.category_name] = {"items": cat_data, "subcategories": []}
                        cat_data = categories[self.category_name]
                    
                    items = cat_data.get('items', [])
                    subcats = cat_data.get('subcategories', [])
                    
                    # Find old index in items list
                    old_items_index = -1
                    for i, item in enumerate(items):
                        if item.get('path') == path:
                            old_items_index = i
                            break
                    
                    if old_items_index != -1:
                        moved_item = items.pop(old_items_index)
                        
                        # Get or create item_order
                        item_order = cat_data.get('item_order', None)
                        if item_order is None:
                            # Create item_order from current state
                            item_order = []
                            for sc in subcats:
                                item_order.append({'type': 'subcategory', 'name': sc})
                            for it in items:
                                item_order.append({'type': 'bookmark', 'path': it.get('path')})
                            # Add the moved item back at end temporarily
                            items.append(moved_item)
                            item_order.append({'type': 'bookmark', 'path': path})
                            cat_data['item_order'] = item_order
                        
                        # Find old index in item_order
                        old_order_idx = -1
                        for i, order_item in enumerate(item_order):
                            if order_item.get('type') == 'bookmark' and order_item.get('path') == path:
                                old_order_idx = i
                                break
                        
                        if old_order_idx != -1:
                            removed_order_item = item_order.pop(old_order_idx)
                            
                            # Adjust drop index
                            new_idx = drop_idx
                            if old_order_idx < drop_idx:
                                new_idx = max(0, drop_idx - 1)
                            new_idx = min(new_idx, len(item_order))
                            
                            item_order.insert(new_idx, removed_order_item)
                            
                            # Also reorder in items list to maintain consistency
                            # Calculate the new items index based on position relative to other bookmarks
                            bookmark_indices = [i for i, o in enumerate(item_order) if o.get('type') == 'bookmark']
                            try:
                                new_items_index = bookmark_indices.index(new_idx)
                            except ValueError:
                                # Find the closest bookmark index
                                new_items_index = len([i for i in bookmark_indices if i < new_idx])
                            
                            # Reinsert in items list
                            if new_items_index >= len(items):
                                items.append(moved_item)
                            else:
                                items.insert(new_items_index, moved_item)
                            
                            logger.info(f"Reordered bookmark in item_order from {old_order_idx} to {new_idx}")
                        else:
                            # Fallback - just append
                            items.append(moved_item)
                        
                        manager.save()
                    
                    logger.info(f"Reordered item in category '{self.category_name}'")
                    self.close()
            else:
                # Moving from another category or bar - use unified handler
                self._handle_cross_category_drop(bookmark, source_category, source_bar_id, drop_idx)
                self.close()
            
            event.acceptProposedAction()
        except Exception as e:
            logger.error(f"Error handling drop in category popup: {e}")
            import traceback
            traceback.print_exc()
            event.ignore()
    
    def _handle_cross_category_drop(self, bookmark, source_category, source_bar_id, drop_idx):
        """Handle dropping bookmark from another category or the bar (same or different bar)"""
        path = bookmark.get('path')
        if not path:
            return
        
        # Normalize path for comparison
        path_normalized = os.path.normpath(path).lower() if path else ''
        
        # Get global categories
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        categories = manager.get_global_categories()
        
        # Ensure this category exists with proper structure
        if self.category_name not in categories:
            categories[self.category_name] = {"items": [], "subcategories": []}
        
        cat_data = categories[self.category_name]
        # Handle old list format
        if isinstance(cat_data, list):
            categories[self.category_name] = {"items": cat_data, "subcategories": []}
            cat_data = categories[self.category_name]
        
        # Get items list and subcats
        existing = cat_data.setdefault('items', [])
        subcats = cat_data.get('subcategories', [])
        
        # Check for duplicate
        for b in existing:
            b_path = b.get('path', '')
            if b_path and os.path.normpath(b_path).lower() == path_normalized:
                return
        
        # Clean bookmark data for storage (remove internal fields)
        clean_bookmark = {k: v for k, v in bookmark.items() if not k.startswith('_')}
        
        # Add to items list
        existing.append(clean_bookmark)
        
        # Update item_order if it exists, or create it
        item_order = cat_data.get('item_order', None)
        if item_order is None:
            # Create item_order from current state (before adding new item)
            item_order = []
            for sc in subcats:
                item_order.append({'type': 'subcategory', 'name': sc})
            for it in existing[:-1]:  # Exclude the just-added item
                item_order.append({'type': 'bookmark', 'path': it.get('path')})
            cat_data['item_order'] = item_order
        
        # Insert new bookmark at drop position in item_order
        insert_idx = min(drop_idx, len(item_order))
        item_order.insert(insert_idx, {'type': 'bookmark', 'path': path})
        
        logger.info(f"Added bookmark to '{self.category_name}' at item_order index {insert_idx}")
        
        # Remove from source - need to handle cross-bar case
        is_cross_bar = source_bar_id is not None and source_bar_id != self.source_bar_id
        
        if is_cross_bar:
            # Cross-bar move: get source container from registry
            source_container = BookmarkContainerRegistry.get(source_bar_id)
            if source_container:
                if source_category in ('__BAR__', '__CONTAINER__'):
                    # Remove standalone from source bar
                    source_container.remove_item_by_path(path)
                else:
                    # Remove from category in source bar (uses global categories)
                    source_container.remove_bookmark_from_category(source_category, path)
                logger.info(f"Removed from source bar {source_bar_id}")
            else:
                logger.warning(f"Source container not found for bar_id={source_bar_id}")
        else:
            # Same bar move
            if source_category in ('__BAR__', '__CONTAINER__'):
                # Item was on the bar/container directly - remove from items list
                if self.data_manager:
                    self.data_manager.remove_item_by_path(path)
            elif source_category in categories:
                # Remove from source category (uses global categories)
                src_data = categories[source_category]
                if isinstance(src_data, dict):
                    src_list = src_data.get('items', [])
                    # Also remove from source's item_order
                    src_item_order = src_data.get('item_order', [])
                    src_data['item_order'] = [i for i in src_item_order 
                                               if not (i.get('type') == 'bookmark' and i.get('path') == path)]
                elif isinstance(src_data, list):
                    src_list = src_data
                else:
                    src_list = []
                
                for i, b in enumerate(src_list):
                    if b.get('path') == path:
                        src_list.pop(i)
                        break
        
        manager.save()
        if self.data_manager:
            self.data_manager._save_and_refresh()
    
    def _handle_category_drop_in_popup(self, event):
        """Handle dropping a category (subcategory) within this popup for reordering"""
        try:
            cat_data = json.loads(event.mimeData().data('application/x-category-move').data().decode())
            dragged_name = cat_data.get('name', '')
            source_parent = cat_data.get('source_parent_category')
            is_subcategory = cat_data.get('is_subcategory', False)
            
            drop_idx = self.drop_index if self.drop_index >= 0 else self._get_drop_index(event.position().toPoint())
            
            logger.info(f"_handle_category_drop_in_popup: dragged='{dragged_name}', source_parent='{source_parent}', "
                       f"this_category='{self.category_name}', is_subcategory={is_subcategory}, drop_idx={drop_idx}")
            
            if not dragged_name:
                event.ignore()
                return
            
            from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
            manager = get_bookmark_manager()
            categories = manager.get_global_categories()
            
            # Get this category's data
            cat_data_here = categories.get(self.category_name, {})
            if isinstance(cat_data_here, list):
                categories[self.category_name] = {"items": cat_data_here, "subcategories": []}
                cat_data_here = categories[self.category_name]
            
            subcats = cat_data_here.setdefault('subcategories', [])
            items = cat_data_here.get('items', [])
            logger.info(f"Current subcats of '{self.category_name}': {subcats}")
            
            # Check if this is reordering within the same category
            if source_parent == self.category_name and dragged_name in subcats:
                # Reordering within same popup - update item_order for unified positioning
                
                # Build or get item_order
                item_order = cat_data_here.get('item_order', None)
                if item_order is None:
                    # Create item_order from current state (subcats first, then items)
                    item_order = []
                    for sc in subcats:
                        item_order.append({'type': 'subcategory', 'name': sc})
                    for it in items:
                        item_order.append({'type': 'bookmark', 'path': it.get('path')})
                    cat_data_here['item_order'] = item_order
                
                # Find old index of dragged subcategory in item_order
                old_order_idx = -1
                for i, order_item in enumerate(item_order):
                    if order_item.get('type') == 'subcategory' and order_item.get('name') == dragged_name:
                        old_order_idx = i
                        break
                
                if old_order_idx != -1:
                    # Remove from old position
                    removed_item = item_order.pop(old_order_idx)
                    
                    # Adjust drop index if moving down
                    new_idx = drop_idx
                    if old_order_idx < drop_idx:
                        new_idx = max(0, drop_idx - 1)
                    new_idx = min(new_idx, len(item_order))
                    
                    # Insert at new position
                    item_order.insert(new_idx, removed_item)
                    
                    logger.info(f"Reordered subcategory '{dragged_name}' in item_order from {old_order_idx} to {new_idx}")
                    logger.info(f"New item_order: {item_order}")
            else:
                # Moving from another category into this one as subcategory
                # First remove from old parent if it was a subcategory
                if is_subcategory and source_parent and source_parent in categories:
                    parent_data = categories[source_parent]
                    if isinstance(parent_data, dict):
                        old_subcats = parent_data.get('subcategories', [])
                        if dragged_name in old_subcats:
                            old_subcats.remove(dragged_name)
                        # Also remove from source's item_order if present
                        old_item_order = parent_data.get('item_order', [])
                        parent_data['item_order'] = [i for i in old_item_order 
                                                     if not (i.get('type') == 'subcategory' and i.get('name') == dragged_name)]
                
                # Check for circular reference
                if manager._is_ancestor_of(dragged_name, self.category_name):
                    logger.warning(f"Cannot make '{dragged_name}' a subcategory of its descendant '{self.category_name}'")
                    event.ignore()
                    return
                
                # Add to this category's subcategories
                if dragged_name not in subcats:
                    subcats.append(dragged_name)
                    logger.info(f"Added '{dragged_name}' to subcategories of '{self.category_name}'")
                
                # Add to item_order at the drop position
                item_order = cat_data_here.get('item_order', None)
                if item_order is None:
                    # Create item_order from current state
                    item_order = []
                    for sc in subcats:
                        if sc != dragged_name:  # Don't double-add
                            item_order.append({'type': 'subcategory', 'name': sc})
                    for it in items:
                        item_order.append({'type': 'bookmark', 'path': it.get('path')})
                    cat_data_here['item_order'] = item_order
                
                # Insert at drop position
                insert_idx = min(drop_idx, len(item_order))
                item_order.insert(insert_idx, {'type': 'subcategory', 'name': dragged_name})
                logger.info(f"Added '{dragged_name}' to item_order at index {insert_idx}")
            
            manager.save()
            if self.data_manager:
                self.data_manager._save_and_refresh()
            
            # Close popup chain to refresh display
            self.close_entire_chain()
            
            event.acceptProposedAction()
        except Exception as e:
            logger.error(f"Error handling category drop in popup: {e}")
            import traceback
            traceback.print_exc()
            event.ignore()

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
        """
        Don't auto-hide on focus loss - popups stay open until toggle.
        This enables dragging items into nested categories.
        """
        super().focusOutEvent(event)
        # NOTE: Removed auto-hide behavior to support nested category drag-drop
    
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
    Used everywhere - on bookmark bars AND inside category popups (for nested categories).
    """
    
    popup_opened = pyqtSignal(object)  # Emits the popup
    popup_closed = pyqtSignal()
    item_clicked = pyqtSignal(str)
    
    def __init__(self, category_name, category_items, item_index=0, parent=None,
                 data_manager=None, source_bar_id: int = 0, orientation='horizontal',
                 color=None, subcategories=None, parent_popup=None, parent_category=None):
        """
        Args:
            category_name: name of the category
            category_items: list of bookmark dicts
            item_index: index in the bar/sidebar for drag reordering
            parent: parent widget
            data_manager: object managing bookmark data (BookmarkContainer)
            source_bar_id: integer ID of the bookmark bar (0, 1, 2, ...)
            orientation: 'horizontal' (top bar), 'vertical' (sidebar), or 'popup' (inside popup)
            color: hex color string for the category (e.g., '#CE93D8')
            subcategories: list of subcategory names (for nested categories)
            parent_popup: reference to parent CategoryPopup (for nested categories)
            parent_category: name of parent category (for nested categories)
        """
        super().__init__(f"🗄 {category_name} ▸", parent)
        
        self.category_name = category_name
        self.category_items = category_items
        self.subcategories = subcategories or []
        self.item_index = item_index
        self.data_manager = data_manager
        self.source_bar_id = source_bar_id
        self.orientation = orientation
        self.category_color = color  # Store the color
        self.drag_start_pos = None
        self.dragging = False
        self.active_popup = None
        self.popup_closed_time = 0
        self.parent_popup = parent_popup  # For nested categories in popups
        self.parent_category = parent_category  # For nested categories
        
        # Update tooltip to show total items
        total_items = len(category_items) + len(self.subcategories)
        self.setToolTip(f"{total_items} item(s)")
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
        if self.orientation == 'popup':
            # Inside a popup - use popup-specific style that handles theme colors
            color = self.category_color or DEFAULT_CATEGORY_COLOR
            
            # Check if it's a theme color - if so, use get_themed_style
            if color and color.startswith('theme:'):
                # Use themed style with popup adjustments
                base_style = get_themed_style(color, 'popup')
                # Override some properties for popup context (smaller, less bold)
                self.setStyleSheet(base_style.replace('font-weight: bold', 'font-weight: normal')
                                            .replace('border-radius: 10px', 'border-radius: 6px')
                                            .replace('border: 2px', 'border: 1px'))
            else:
                # Regular color
                light_color = lighten_color(color, 0.4)
                dark_color = darken_color(color, 0.7)
                border_color = darken_color(color, 0.6)
                hover_color = lighten_color(color, 0.2)
                
                self.setStyleSheet(f"""
                    QPushButton {{
                        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 {light_color}, stop:1 {color});
                        border: 1px solid {border_color};
                        border-radius: 6px;
                        padding: 3px 8px;
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
                """)
        elif self.category_color:
            # Use custom color
            self.setStyleSheet(get_category_button_style(self.category_color, self.orientation))
        else:
            # Use default style
            if self.orientation == 'horizontal':
                self.setStyleSheet(CATEGORY_BUTTON_STYLE)
            else:
                self.setStyleSheet(CATEGORY_BUTTON_STYLE_SIDEBAR)
        
        # Set size constraints based on orientation
        if self.orientation == 'horizontal':
            self.setMaximumWidth(200)
        elif self.orientation == 'popup':
            # No fixed size in popup - let layout manage it
            pass
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
        
        # Category move data (include color for transfer)
        category_data = {
            'name': self.category_name,
            'items': self.category_items,
            'source_bar_id': self.source_bar_id,  # Integer bar ID
            'bar_item_index': self.item_index,
            'color': self.category_color,  # Include color for transfer
            'source_parent_category': self.parent_category,  # For nested categories
            'is_subcategory': self.parent_popup is not None
        }
        mime_data.setData('application/x-category-move', json.dumps(category_data).encode())
        
        drag.setMimeData(mime_data)
        
        logger.info(f"Dragging category: {self.category_name}")
        result = drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        self.dragging = False
    
    def _show_popup(self):
        """Show the category popup - position depends on context (bar vs nested)"""
        # Toggle off if already visible
        if self.active_popup and self.active_popup.isVisible():
            self.active_popup.hide()
            return
        
        # Determine nesting level
        nesting_level = 0
        if self.parent_popup:
            nesting_level = self.parent_popup.nesting_level + 1
        
        # Reuse existing popup if it exists
        if self.active_popup:
            global_pos = self._calculate_popup_position()
            self.active_popup.move(global_pos)
            self.active_popup.show()
            self.popup_opened.emit(self.active_popup)
            return
        
        # Create new popup
        popup = CategoryPopup(
            category_name=self.category_name,
            category_items=self.category_items,
            subcategories=self.subcategories,
            parent_widget=self,
            data_manager=self.data_manager,
            source_bar_id=self.source_bar_id,
            color=self.category_color,
            parent_popup=self.parent_popup,
            nesting_level=nesting_level
        )
        
        popup.item_clicked.connect(self._on_popup_item_clicked)
        popup.popup_closed.connect(self._on_popup_closed)
        
        # Register with parent popup if nested
        if self.parent_popup:
            self.parent_popup.register_child_popup(popup)
        
        # Position popup
        global_pos = self._calculate_popup_position()
        popup.move(global_pos)
        popup.show()
        
        self.active_popup = popup
        self.popup_opened.emit(popup)
    
    def _calculate_popup_position(self):
        """Calculate popup position based on context (bar vs nested in popup)"""
        if self.orientation == 'popup' or self.parent_popup:
            # Inside a popup - position to the right
            global_pos = self.mapToGlobal(self.rect().topRight())
            
            # Adjust for screen boundaries
            screen = self.screen()
            if screen:
                screen_geo = screen.availableGeometry()
                popup_width = self.active_popup.width() if self.active_popup and self.active_popup.width() > 0 else 250
                
                # If popup would go off right edge, position to the left instead
                if global_pos.x() + popup_width > screen_geo.right():
                    global_pos = self.mapToGlobal(self.rect().topLeft())
                    global_pos.setX(global_pos.x() - popup_width)
            
            return global_pos
        else:
            # On a bar - position below
            return self.mapToGlobal(self.rect().bottomLeft())
    
    def invalidate_popup(self):
        """Call this when category contents change to force popup recreation"""
        if self.active_popup:
            self.active_popup.close()
            self.active_popup.deleteLater()
            self.active_popup = None
    
    def update_items(self, new_items, new_subcategories=None):
        """Update the category items/subcategories and invalidate the popup cache"""
        self.category_items = new_items
        if new_subcategories is not None:
            self.subcategories = new_subcategories
        total_items = len(new_items) + len(self.subcategories)
        self.setToolTip(f"{total_items} item(s)")
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
        new_subcat_action = menu.addAction("📁 New Subcategory")
        menu.addSeparator()
        
        # Different remove options depending on whether this is nested
        remove_from_parent_action = None
        delete_action = None
        
        if self.parent_category:
            # Nested category - show both options
            remove_from_parent_action = menu.addAction("🗑️ Remove from here")
            delete_action = menu.addAction("❌ Delete permanently")
        else:
            # Top-level category - just show remove
            delete_action = menu.addAction("🗑️ Remove")
        
        action = menu.exec(self.mapToGlobal(pos))
        
        if action == rename_action:
            self._rename_category()
        elif action == color_action:
            self._change_color()
        elif action == new_subcat_action:
            self._create_new_subcategory()
        elif action == remove_from_parent_action:
            self._remove_from_parent()
        elif action == delete_action:
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
        
        # Save the color to global colors via BookmarkDataManager
        if not self.data_manager:
            return
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        colors = manager.get_global_colors()
        colors[self.category_name] = color
        self.data_manager._save_and_refresh()
    
    def _rename_category(self):
        """Rename this category (global rename)"""
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
            
            # Use the data manager's global rename
            from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
            manager = get_bookmark_manager()
            
            if manager.category_exists(new_name):
                show_styled_warning(self, "Duplicate", f"Category '{new_name}' already exists.")
                return
            
            if manager.rename_category(self.category_name, new_name):
                manager.save()
                self.data_manager._save_and_refresh()
    
    def _remove_category(self):
        """Remove this category with confirmation"""
        # Build message
        total_items = len(self.category_items) + len(self.subcategories)
        if total_items > 0:
            items_desc = []
            for item in self.category_items:
                items_desc.append(f"  • {item.get('name', item.get('path', 'Unknown'))}")
            for subcat in self.subcategories:
                items_desc.append(f"  • 📁 {subcat} (subcategory)")
            items_list = "\n".join(items_desc)
            message = f"Are you sure you want to remove the category '{self.category_name}'?\n\nThe following {total_items} item(s) will be deleted:\n{items_list}"
        else:
            message = f"Are you sure you want to remove the empty category '{self.category_name}'?"
        
        if not show_styled_question(self, "Remove Category", message):
            return
        
        if not self.data_manager:
            return
        
        # Use BookmarkContainer's remove method
        self.data_manager.remove_category(self.category_name)
    
    def _create_new_subcategory(self):
        """Create a new subcategory inside this category"""
        name, ok = QInputDialog.getText(
            self,
            "New Subcategory",
            f"Enter name for new subcategory in '{self.category_name}':",
            QLineEdit.EchoMode.Normal,
            ""
        )
        
        if ok and name:
            name = name.strip()
            if not name:
                return
            
            if not self.data_manager:
                return
            
            from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
            manager = get_bookmark_manager()
            
            # Check if category name already exists globally
            if manager.category_exists(name):
                show_styled_warning(self, "Duplicate", f"Category '{name}' already exists.")
                return
            
            # Create new category globally
            manager.create_category(name)
            
            # Make it a subcategory of this category
            manager.make_subcategory(name, self.category_name)
            manager.save()
            
            self.data_manager._save_and_refresh()
    
    def _remove_from_parent(self):
        """Remove this category from its parent (keeps category data, just removes nesting)"""
        if not self.parent_category or not self.data_manager:
            return
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        categories = manager.get_global_categories()
        
        # Remove from parent's subcategories list
        parent_data = categories.get(self.parent_category, {})
        if isinstance(parent_data, dict):
            subcats = parent_data.get('subcategories', [])
            if self.category_name in subcats:
                subcats.remove(self.category_name)
        
        manager.save()
        self.data_manager._save_and_refresh()
        
        # Close popup chain
        if self.parent_popup:
            self.parent_popup.close_entire_chain()

    # Drag-drop handling for accepting drops onto the category
    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat('application/x-bookmark-move') or mime.hasFormat('application/x-category-move') or mime.hasUrls():
            # Check for circular reference when receiving category
            if mime.hasFormat('application/x-category-move'):
                try:
                    cat_data = json.loads(mime.data('application/x-category-move').data().decode())
                    dragged_name = cat_data.get('name', '')
                    # Prevent dropping category into itself or its descendants
                    if self._is_descendant_of(dragged_name):
                        event.ignore()
                        return
                except:
                    pass
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def _is_descendant_of(self, ancestor_name):
        """Check if this category is a descendant of the given category"""
        if self.category_name == ancestor_name:
            return True
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        
        # Use global categories for the check
        return manager._is_ancestor_of(ancestor_name, self.category_name)
    
    def dragLeaveEvent(self, event):
        event.accept()
    
    def dropEvent(self, event):
        """Handle drops onto this category"""
        mime = event.mimeData()
        
        # Handle category drop (making it a subcategory)
        if mime.hasFormat('application/x-category-move'):
            try:
                cat_data = json.loads(mime.data('application/x-category-move').data().decode())
                dragged_name = cat_data.get('name', '')
                source_parent = cat_data.get('source_parent_category')
                
                # If both dragged category and this category share the same parent popup,
                # forward to the popup for reordering instead of making a subcategory
                if self.parent_popup and source_parent == self.parent_category:
                    # Both are siblings in the same popup - forward to popup for reorder
                    logger.info(f"Sibling category drop: '{dragged_name}' dropped on '{self.category_name}' in popup '{self.parent_category}'")
                    self.parent_popup._handle_category_drop_in_popup(event)
                    return
                
                # Prevent circular reference
                if self._is_descendant_of(dragged_name):
                    logger.warning(f"Cannot drop '{dragged_name}' into its descendant '{self.category_name}'")
                    event.ignore()
                    return
                
                self._handle_category_drop(cat_data)
                event.acceptProposedAction()
                return
            except Exception as e:
                logger.error(f"Error handling category drop: {e}")
                event.ignore()
                return
        
        if mime.hasFormat('application/x-bookmark-move'):
            try:
                drag_data = json.loads(mime.data('application/x-bookmark-move').data().decode())
                bookmark = drag_data['bookmark']
                source = drag_data.get('source_category', '__CONTAINER__')
                source_bar_id = drag_data.get('source_bar_id')
                
                logger.info(f"Dropping bookmark '{bookmark.get('name')}' into category '{self.category_name}'")
                
                if not self.data_manager:
                    event.ignore()
                    return
                
                self._handle_drop(bookmark, source, source_bar_id)
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
                        self._handle_drop(bookmark, '__NEW__')
                
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error handling URL drop: {e}")
                event.ignore()
        else:
            event.ignore()
    
    def _handle_drop(self, bookmark, source, source_bar_id=None):
        """Handle drop onto this category - unified for all bar types
        
        Args:
            bookmark: Bookmark data dict
            source: Source category name, or '__CONTAINER__'/'__BAR__' for standalone, '__NEW__' for new
            source_bar_id: Integer bar ID of source container (for cross-bar moves)
        """
        if not self.data_manager:
            return
        
        path = bookmark.get('path')
        if not path:
            return
        
        # Get global categories
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        categories = manager.get_global_categories()
        
        # Ensure category exists with proper structure
        if self.category_name not in categories:
            categories[self.category_name] = {"items": [], "subcategories": []}
        
        cat_data = categories[self.category_name]
        if isinstance(cat_data, list):
            categories[self.category_name] = {"items": cat_data, "subcategories": []}
            cat_data = categories[self.category_name]
        
        # Get items list
        existing = cat_data.setdefault('items', [])
        
        # Check duplicate
        if any(b.get('path') == path for b in existing):
            return
        
        # Clean bookmark data
        clean_bookmark = {k: v for k, v in bookmark.items() if not k.startswith('_')}
        existing.append(clean_bookmark)
        
        # Determine if cross-bar move
        is_cross_bar = source_bar_id is not None and source_bar_id != self.source_bar_id
        
        # Remove from source
        if is_cross_bar:
            # Cross-bar move: get source container from registry
            source_container = BookmarkContainerRegistry.get(source_bar_id)
            if source_container:
                if source in ('__BAR__', '__CONTAINER__'):
                    # Remove standalone from source bar
                    source_container.remove_item_by_path(path)
                elif source and source != '__NEW__' and source != self.category_name:
                    # Remove from category in source bar (global categories)
                    if source in categories:
                        src_data = categories[source]
                        if isinstance(src_data, dict):
                            src_list = src_data.get('items', [])
                        elif isinstance(src_data, list):
                            src_list = src_data
                        else:
                            src_list = []
                        
                        for i, b in enumerate(src_list):
                            if b.get('path') == path:
                                src_list.pop(i)
                                break
                logger.info(f"Removed bookmark from source bar {source_bar_id}")
            else:
                logger.warning(f"Source container not found for bar_id={source_bar_id}")
        else:
            # Same bar move
            if source in ('__BAR__', '__CONTAINER__'):
                # Item was standalone on the bar - remove from items list
                self.data_manager.remove_item_by_path(path)
            elif source and source != '__NEW__' and source != self.category_name:
                # Remove from source category (global categories)
                if source in categories:
                    src_data = categories[source]
                    if isinstance(src_data, dict):
                        src_list = src_data.get('items', [])
                    elif isinstance(src_data, list):
                        src_list = src_data
                    else:
                        src_list = []
                    
                    for i, b in enumerate(src_list):
                        if b.get('path') == path:
                            src_list.pop(i)
                            break
        
        manager.save()
        self.data_manager._save_and_refresh()
    
    def _handle_category_drop(self, cat_data):
        """Handle category dropped onto this category (making it a nested subcategory)"""
        if not self.data_manager:
            return
        
        dragged_name = cat_data.get('name', '')
        source_parent = cat_data.get('source_parent_category')
        source_bar_id = cat_data.get('source_bar_id')
        is_subcategory = cat_data.get('is_subcategory', False)
        
        if not dragged_name:
            return
        
        # Don't allow dropping onto itself
        if dragged_name == self.category_name:
            return
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        
        # Check for circular reference using global categories
        if manager._is_ancestor_of(dragged_name, self.category_name):
            logger.warning(f"Cannot make '{dragged_name}' a subcategory of its descendant '{self.category_name}'")
            return
        
        # If it was a subcategory, remove from old parent first
        if is_subcategory and source_parent:
            categories = manager.get_global_categories()
            parent_data = categories.get(source_parent, {})
            if isinstance(parent_data, dict):
                old_subcats = parent_data.get('subcategories', [])
                if dragged_name in old_subcats:
                    old_subcats.remove(dragged_name)
        
        # Make it a subcategory of this category
        if manager.make_subcategory(dragged_name, self.category_name, source_bar_id):
            manager.save()
            logger.info(f"Made category '{dragged_name}' a subcategory of '{self.category_name}'")
            self.data_manager._save_and_refresh()
            
            # Refresh source container if different
            if source_bar_id is not None and source_bar_id != self.source_bar_id:
                source_container = BookmarkContainerRegistry.get(source_bar_id)
                if source_container:
                    source_container.refresh()


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
        font-weight: normal;
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
        font-weight: normal;
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
        
        # Bookmark move data - include source bar ID for cross-bar detection
        drag_data = {
            'bookmark': self.bookmark_data,
            'source_category': '__CONTAINER__',
            'source_bar_id': self.container.bar_id if self.container else 0,
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
    
    Bars are identified by integer IDs (0, 1, 2, ...).
    """
    _instance = None
    _containers: Dict[int, 'BookmarkContainer'] = {}  # bar_id -> BookmarkContainer
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, bar_id: int, container: 'BookmarkContainer'):
        """Register a container by its bar ID"""
        cls._containers[bar_id] = container
        logger.debug(f"BookmarkContainer registered: bar_id={bar_id}")
    
    @classmethod
    def unregister(cls, bar_id: int):
        """Unregister a container"""
        if bar_id in cls._containers:
            del cls._containers[bar_id]
            logger.debug(f"BookmarkContainer unregistered: bar_id={bar_id}")
    
    @classmethod
    def get(cls, bar_id: int) -> Optional['BookmarkContainer']:
        """Get a container by bar ID"""
        return cls._containers.get(bar_id)
    
    @classmethod
    def get_all(cls) -> Dict[int, 'BookmarkContainer']:
        """Get all registered containers"""
        return cls._containers.copy()
    
    @classmethod
    def get_others(cls, exclude_bar_id: int) -> list:
        """Get all containers except the specified one"""
        return [c for bid, c in cls._containers.items() if bid != exclude_bar_id]


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
    - All BookmarkContainer instances register with BookmarkContainerRegistry by bar_id
    - When an item is dropped from another container, it's automatically moved
    - Source container is found via the registry and item is removed from it
    
    Data Storage:
    - Uses the centralized BookmarkDataManager
    - Data is automatically loaded from/saved to ~/.suiteview/bookmarks.json
    - Each bar is identified by an integer ID (0, 1, 2, ...)
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
    
    def __init__(self, bar_id: int, orientation: str = None, parent=None):
        """
        Args:
            bar_id: Integer identifier for this bookmark bar (0, 1, 2, ...)
                    Bar 0 = default horizontal (top) bar
                    Bar 1 = default vertical (side) bar
            orientation: 'horizontal' or 'vertical'. If None, uses the orientation
                        stored in the data manager for this bar.
            parent: Parent widget
        """
        super().__init__(parent)
        
        # Ensure icons are loaded from database cache before creating UI
        ensure_icons_loaded()
        
        self.bar_id = bar_id
        
        # Get data manager
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        self._data_manager = get_bookmark_manager()
        
        # Get bar data (creates default if doesn't exist)
        self.data_store = self._data_manager.get_bar_data(bar_id)
        
        # Determine orientation
        if orientation is not None:
            self.orientation = orientation
            # Update stored orientation if different
            if self.data_store.get("orientation") != orientation:
                self.data_store["orientation"] = orientation
        else:
            self.orientation = self.data_store.get("orientation", "horizontal")
        
        self.save_callback = self._data_manager.save
        
        # Register with the global registry for cross-bar communication
        BookmarkContainerRegistry.register(bar_id, self)
        
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
        
        # Connect scrollbar visibility changes to update button widths
        self.scroll_area.verticalScrollBar().rangeChanged.connect(
            lambda: QTimer.singleShot(10, self._update_button_widths)
        )
        
        # Items container - accepts drops and forwards to parent
        self.items_container = DropForwardingWidget(self)
        self.items_container.setStyleSheet("background-color: transparent;")
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(4, 2, 4, 2)  # Reduced right margin, dynamic adjustment handles scrollbar
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
        
        # Calculate available width: container width minus padding
        available_width = self.width() - 4  # Base padding
        
        # Check if vertical scrollbar is visible and account for its width
        if hasattr(self, 'scroll_area') and self.scroll_area.verticalScrollBar().isVisible():
            scrollbar_width = self.scroll_area.verticalScrollBar().width()
            available_width -= scrollbar_width + 2  # Extra margin for clean appearance
        
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
        """Get the ordered items list for this bar"""
        return self.data_store.get("items", [])
    
    @property
    def categories(self):
        """Get the GLOBAL categories dict (shared across all bars)"""
        return self._data_manager.get_global_categories()
    
    @property
    def category_colors(self):
        """Get the GLOBAL category colors dict (shared across all bars)"""
        return self._data_manager.get_global_colors()
    
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
    
    def set_highlight(self, highlight: bool):
        """Set highlight state for this container (used when hovering over location in Add Bookmark dialog)"""
        if highlight:
            # Apply light gold highlight background
            self.setAutoFillBackground(True)
            palette = self.palette()
            from PyQt6.QtGui import QColor
            palette.setColor(self.backgroundRole(), QColor(255, 223, 128))  # Light gold
            self.setPalette(palette)
            # Also style the scroll area and items container
            if hasattr(self, 'scroll_area'):
                self.scroll_area.setStyleSheet("QScrollArea { background-color: #FFDF80; border: 2px solid #FFB300; }")
            if hasattr(self, 'items_container'):
                self.items_container.setStyleSheet("background-color: #FFDF80;")
        else:
            # Clear highlight - restore default
            self.setAutoFillBackground(False)
            if hasattr(self, 'scroll_area'):
                self.scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
            if hasattr(self, 'items_container'):
                self.items_container.setStyleSheet("background-color: transparent;")
    
    def add_bookmark(self, bookmark_data, insert_at=None):
        """Add a standalone bookmark to the container"""
        new_item = {
            'type': 'bookmark',
            'data': bookmark_data
        }
        
        items = self.data_store.setdefault("items", [])
        
        if insert_at is not None and 0 <= insert_at <= len(items):
            items.insert(insert_at, new_item)
        else:
            items.append(new_item)
        
        self._save_and_refresh()
    
    def add_category(self, category_name, category_items=None, color=None, insert_at=None):
        """Add a category to this bar (creates globally if doesn't exist)"""
        # Create in global categories if doesn't exist
        if not self._data_manager.category_exists(category_name):
            self._data_manager.create_category(category_name, category_items, color)
        elif category_items:
            # Category exists, but we might want to add items
            categories = self.categories
            if category_name in categories:
                cat_data = categories[category_name]
                if isinstance(cat_data, dict):
                    cat_data.setdefault('items', []).extend(category_items)
                elif isinstance(cat_data, list):
                    cat_data.extend(category_items)
        
        # Check if already in this bar's items
        items = self.data_store.setdefault("items", [])
        for item in items:
            if item.get('type') == 'category' and item.get('name') == category_name:
                return False  # Already in this bar
        
        # Add to this bar's items list
        new_item = {
            'type': 'category',
            'name': category_name
        }
        
        if insert_at is not None and 0 <= insert_at <= len(items):
            items.insert(insert_at, new_item)
        else:
            items.append(new_item)
        
        # Set color if provided (updates global)
        if color:
            self.category_colors[category_name] = color
        
        self._save_and_refresh()
        return True
    
    def remove_item(self, index):
        """Remove an item by index from this bar's items list"""
        items = self.items
        if 0 <= index < len(items):
            item = items[index]
            
            # If it's a category, also delete globally
            if item.get('type') == 'category':
                category_name = item.get('name')
                if category_name:
                    self._data_manager.delete_category(category_name, recursive=True)
            
            items.pop(index)
            self._save_and_refresh()
    
    def remove_category(self, category_name):
        """Remove a category globally (deletes from all bars)"""
        self._data_manager.delete_category(category_name, recursive=True)
        self._save_and_refresh()
    
    def rename_category(self, old_name, new_name):
        """Rename a category globally"""
        if self._data_manager.rename_category(old_name, new_name):
            self._save_and_refresh()
            return True
        return False
    
    def set_category_color(self, category_name, color):
        """Set the color for a category (global)"""
        colors = self._data_manager.get_global_colors()
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
        
        # Get category data (handle both old list and new dict formats)
        cat_data = self.categories.get(category_name, {})
        if isinstance(cat_data, dict):
            category_items = cat_data.get('items', [])
            subcategories = cat_data.get('subcategories', [])
        elif isinstance(cat_data, list):
            category_items = cat_data
            subcategories = []
        else:
            category_items = []
            subcategories = []
        
        category_color = self.category_colors.get(category_name, None)
        
        btn = CategoryButton(
            category_name=category_name,
            category_items=category_items,
            subcategories=subcategories,
            item_index=index,
            parent=self.items_container,
            data_manager=self,
            source_bar_id=self.bar_id,
            orientation=self.orientation,
            color=category_color
        )
        btn.item_clicked.connect(self.item_clicked.emit)
        
        return btn
    
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
                if self._data_manager.category_exists(name):
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
        
        # Category move (check source bar ID to determine if cross-bar OR subcategory promotion)
        if mime.hasFormat('application/x-category-move'):
            try:
                category_data = json.loads(mime.data('application/x-category-move').data().decode())
                # Get source bar ID - may be int or string
                source_bar_id_raw = category_data.get('source_bar_id', category_data.get('source_location', category_data.get('source')))
                try:
                    source_bar_id = int(source_bar_id_raw) if source_bar_id_raw is not None else None
                except (ValueError, TypeError):
                    source_bar_id = None
                
                is_subcategory = category_data.get('is_subcategory', False)
                
                logger.info(f"Received category drop: name='{category_data.get('name')}', source_bar_id={source_bar_id}, is_subcategory={is_subcategory}")
                
                # Determine if this is from a different container
                is_cross_bar = self._is_cross_bar_source(source_bar_id)
                logger.info(f"Is cross-bar: {is_cross_bar} (source_bar_id={source_bar_id}, self.bar_id={self.bar_id})")
                
                # Handle cross-bar moves OR subcategory promotions (even from same bar)
                if is_cross_bar or is_subcategory:
                    # Handle cross-bar move or subcategory promotion
                    if self._handle_cross_bar_category_move(category_data, drop_index):
                        logger.info("Category move/promotion handled successfully")
                        event.acceptProposedAction()
                        return
                    # Fallback: emit signal
                    logger.info("Handler returned False, falling back to signal")
                    category_data['_drop_index'] = drop_index
                    self.category_dropped.emit(category_data)
                    event.acceptProposedAction()
                    return
                else:
                    logger.info("Not cross-bar and not subcategory, falling through to internal reorder")
                # Not cross-bar - fall through to internal reorder
            except Exception as e:
                logger.error(f"Error handling category drop: {e}")
                import traceback
                traceback.print_exc()
        
        # Bookmark move (check source bar ID to determine if cross-bar)
        if mime.hasFormat('application/x-bookmark-move'):
            try:
                drag_data = json.loads(mime.data('application/x-bookmark-move').data().decode())
                # Get source bar ID - may be int or string
                source_bar_id_raw = drag_data.get('source_bar_id', drag_data.get('source_location', drag_data.get('source')))
                try:
                    source_bar_id = int(source_bar_id_raw) if source_bar_id_raw is not None else None
                except (ValueError, TypeError):
                    source_bar_id = None
                source_category = drag_data.get('source_category', '')
                
                logger.info(f"Received bookmark drop: source_bar_id={source_bar_id}, source_category='{source_category}'")
                
                # Determine if this is from a different container
                is_cross_bar = self._is_cross_bar_source(source_bar_id)
                # Also consider it cross-bar if coming from a category (even same container)
                is_from_category = source_category and source_category != '__CONTAINER__'
                
                logger.info(f"Bookmark: is_cross_bar={is_cross_bar}, is_from_category={is_from_category}")
                
                if is_cross_bar or is_from_category:
                    bookmark = drag_data.get('bookmark', {})
                    # Handle cross-bar or category-to-bar move
                    if self._handle_cross_bar_bookmark_move(bookmark, source_category, source_bar_id, drop_index):
                        logger.info("Cross-bar bookmark move handled successfully")
                        event.acceptProposedAction()
                        return
                    # Fallback: emit signal
                    logger.info("Cross-bar bookmark handler returned False, falling back to signal")
                    bookmark['_drop_index'] = drop_index
                    bookmark['_source_category'] = source_category
                    bookmark['source_category'] = source_category
                    bookmark['source_bar_id'] = source_bar_id
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
                logger.info(f"Internal reorder: from_index={from_index}, drop_index={drop_index}")
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
    
    def _is_cross_bar_source(self, source_bar_id: int) -> bool:
        """
        Check if the source bar ID represents a different container than this one.
        Returns True if the drag is from a different bookmark bar.
        
        Args:
            source_bar_id: Integer bar ID from the drag source
        """
        if source_bar_id is None:
            return False
        
        return source_bar_id != self.bar_id
    
    def _handle_cross_bar_bookmark_move(self, bookmark, source_category, source_bar_id: int, drop_index):
        """
        Handle moving a bookmark from another container to this one.
        Returns True if handled, False to fall back to signal emission.
        
        Args:
            bookmark: Bookmark data dict
            source_category: Category name if from a category, else '__CONTAINER__' or None
            source_bar_id: Integer bar ID of the source container
            drop_index: Index to insert at in this container
        """
        logger.info(f"_handle_cross_bar_bookmark_move: bookmark='{bookmark.get('name')}', "
                    f"source_category='{source_category}', source_bar_id={source_bar_id}, "
                    f"target_bar_id={self.bar_id}")
        
        if source_bar_id is None:
            logger.warning("No source bar ID provided")
            return False
        
        # Check if this is a standalone bookmark (not from a category)
        is_standalone = source_category in ('__CONTAINER__', '', None)
        logger.debug(f"is_standalone={is_standalone}")
        
        # Don't process if source is same as target AND it's a standalone bookmark
        # (internal reordering is handled separately via x-container-item-index)
        if source_bar_id == self.bar_id and is_standalone:
            logger.info("Same container standalone bookmark - letting internal reorder handle it")
            return False
        
        # Get source container from registry
        source_container = BookmarkContainerRegistry.get(source_bar_id)
        if not source_container:
            logger.warning(f"Source container not found in registry for bar_id={source_bar_id}")
            logger.debug(f"Registered containers: {list(BookmarkContainerRegistry.get_all().keys())}")
            return False
        
        # Create clean bookmark data
        clean_bookmark = {
            'name': bookmark.get('name', ''),
            'path': bookmark.get('path', '')
        }
        
        # Add to this container at the drop index
        self.add_bookmark(clean_bookmark, insert_at=drop_index)
        logger.info(f"Added bookmark '{clean_bookmark['name']}' to bar {self.bar_id}")
        
        # Remove from source
        if not is_standalone:
            # Remove from category in source container
            logger.info(f"Removing from category '{source_category}' in source container")
            source_container.remove_bookmark_from_category(source_category, bookmark.get('path', ''))
        else:
            # Remove standalone bookmark from source container
            logger.info(f"Removing standalone bookmark from source container")
            source_container.remove_item_by_path(bookmark.get('path', ''))
        
        logger.info(f"Moved bookmark '{clean_bookmark['name']}' from bar {source_bar_id} to bar {self.bar_id}")
        return True
    
    def _handle_cross_bar_category_move(self, category_data, drop_index):
        """
        Handle moving a category from another container to this one.
        Also handles promoting a subcategory to top-level category.
        
        With global categories (v4), this is now just moving references!
        No deep copy needed - categories are shared across all bars.
        
        Returns True if handled, False to fall back to signal emission.
        """
        # Get source bar ID - could be int or string from drag data
        source_bar_id_raw = category_data.get('source_bar_id', category_data.get('source_location', category_data.get('source')))
        category_name = category_data.get('name', '')
        is_subcategory = category_data.get('is_subcategory', False)
        source_parent = category_data.get('source_parent_category')
        
        # Convert to int if string
        try:
            source_bar_id = int(source_bar_id_raw) if source_bar_id_raw is not None else None
        except (ValueError, TypeError):
            logger.warning(f"Invalid source bar ID: {source_bar_id_raw}")
            source_bar_id = None
        
        logger.info(f"_handle_cross_bar_category_move: category='{category_name}', source_bar_id={source_bar_id}, "
                    f"target_bar_id={self.bar_id}, is_subcategory={is_subcategory}, source_parent={source_parent}")
        
        if not category_name:
            logger.warning("No category name provided")
            return False
        
        # Verify category exists globally
        if not self._data_manager.category_exists(category_name):
            logger.warning(f"Category '{category_name}' does not exist globally")
            return False
        
        # Handle subcategory promotion (dragging subcategory to a bar)
        if is_subcategory:
            # Use data manager's promote method
            if self._data_manager.promote_to_toplevel(category_name, source_parent, 
                                                       self.bar_id, drop_index):
                self._save_and_refresh()
                # Refresh source container if different
                if source_bar_id is not None and source_bar_id != self.bar_id:
                    source_container = BookmarkContainerRegistry.get(source_bar_id)
                    if source_container:
                        source_container.refresh()
                return True
            return False
        
        # Regular category move between bars - just move the reference
        if source_bar_id is not None and source_bar_id != self.bar_id:
            if self._data_manager.move_category_to_bar(category_name, self.bar_id, 
                                                        source_bar_id, drop_index):
                self._save_and_refresh()
                # Refresh source container
                source_container = BookmarkContainerRegistry.get(source_bar_id)
                if source_container:
                    source_container.refresh()
                logger.info(f"Moved category '{category_name}' from bar {source_bar_id} to bar {self.bar_id}")
                return True
        
        # Same bar - this is internal reordering, handle via items list
        if source_bar_id == self.bar_id:
            # Find current index
            items = self.data_store.get('items', [])
            current_idx = None
            for i, item in enumerate(items):
                if item.get('type') == 'category' and item.get('name') == category_name:
                    current_idx = i
                    break
            
            if current_idx is not None and current_idx != drop_index:
                # Reorder
                item = items.pop(current_idx)
                if drop_index > current_idx:
                    drop_index -= 1
                items.insert(drop_index, item)
                self._save_and_refresh()
                return True
        
        return False
    
    def _promote_subcategory_to_toplevel(self, category_name, parent_name, drop_index):
        """Promote a subcategory to a top-level category on this bar"""
        logger.info(f"Promoting subcategory '{category_name}' from parent '{parent_name}' to top-level")
        
        if self._data_manager.promote_to_toplevel(category_name, parent_name, 
                                                   self.bar_id, drop_index):
            self._save_and_refresh()
            return True
        return False
    
    def remove_bookmark_from_category(self, category_name, path):
        """Remove a bookmark from a category by its path (uses global categories)"""
        categories = self._data_manager.get_global_categories()
        if category_name in categories:
            cat_data = categories[category_name]
            # Handle both old list and new dict formats
            if isinstance(cat_data, dict):
                items = cat_data.get('items', [])
                # Also remove from item_order if present
                item_order = cat_data.get('item_order', [])
                cat_data['item_order'] = [i for i in item_order 
                                          if not (i.get('type') == 'bookmark' and i.get('path') == path)]
            elif isinstance(cat_data, list):
                items = cat_data
            else:
                items = []
            
            for i, item in enumerate(items):
                if item.get('path') == path:
                    items.pop(i)
                    break
            if self.save_callback:
                self.save_callback()
            self.refresh()
    
    def remove_item_by_path(self, path):
        """Remove an item from the items list by its path"""
        items = self.data_store.get("items", [])
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
