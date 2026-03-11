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
from typing import Optional, Dict, Any, Callable, List

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QFrame, QVBoxLayout, QHBoxLayout,
    QScrollArea, QMenu, QInputDialog, QMessageBox, QLineEdit,
    QFileIconProvider, QLabel, QToolTip, QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QFileInfo, QTimer, QEventLoop, QByteArray, QBuffer, QIODevice, QRect
from PyQt6.QtGui import QAction, QDrag, QCursor, QIcon, QPixmap

logger = logging.getLogger(__name__)


# Shared icon provider and cache for all bookmark widgets
_icon_provider = None
_icon_cache = {}  # Cache by extension for files
_path_cache = {}  # Cache full results by path for folders
_folder_icon = None
_file_icon = None
_db_icons_loaded = False  # Track if DB icons have been loaded

# Global callback for footer status updates (set by main window)
_footer_status_callback = None


def set_footer_status_callback(callback):
    """Set the callback function for updating footer status.
    The callback should accept a single string argument (the path to display).
    Pass empty string to clear the footer.
    """
    global _footer_status_callback
    _footer_status_callback = callback


def update_footer_status(path: str):
    """Update the footer status with the given path.
    Call with empty string to clear.
    """
    global _footer_status_callback
    if _footer_status_callback:
        _footer_status_callback(path)


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
        border-left: 3px solid transparent;
        border-radius: 2px;
        padding: 4px 8px;
        text-align: left;
        font-size: 9pt;
        font-weight: normal;
        color: #202124;
    }
    QPushButton:hover {
        background-color: #00FFFF;
        border: 2px solid #0088FF;
    }
    QPushButton:pressed {
        background-color: #00CCCC;
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
    # Row 1 - Pinks
    "#FF69B4", "#FF85C1", "#FFB6C1", "#FFC0CB",
    # Row 2 - Yellows
    "#FFD700", "#FFEB3B", "#FFF59D", "#FFFACD",
    # Row 3 - Greens
    "#228B22", "#32CD32", "#90EE90", "#98FB98",
    # Row 4 - Blues
    "#1E90FF", "#6495ED", "#87CEEB", "#ADD8E6",
    # Row 5 - Oranges
    "#FF8C00", "#FFA500", "#FFB347", "#FFDAB9",
    # Row 6 - Reds
    "#DC143C", "#FF6347", "#FF7F7F", "#FFA07A",
    # Row 7 - Dark Greys
    "#2F4F4F", "#696969", "#808080", "#A9A9A9",
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
            'theme:purple_gold': '#B8860B',  # Darker gold
            'theme:forest_cream': '#1A6B1A', # Darker forest
            'theme:crimson_slate': '#505860', # Darker slate
            'theme:ocean_sunset': '#CC5528', # Darker sunset
            'theme:silver_blue': '#0A4A7A',  # Darker blue border
            'theme:mint_chocolate': '#3D2817', # Darker chocolate
            'theme:sunset_purple': '#4A1A6B', # Darker purple
            'theme:steel_orange': '#CC5500', # Darker orange
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
        'theme:purple_gold': ('#6B2D8E', '#3D1A52', '#FFD700', '#FFD700'),
        'theme:forest_cream': ('#228B22', '#145214', '#FFFDD0', '#FFFDD0'),
        'theme:crimson_slate': ('#DC143C', '#8B0A25', '#708090', '#B0C0D0'),
        'theme:ocean_sunset': ('#006994', '#003D56', '#FF6B35', '#FF6B35'),
        'theme:silver_blue': ('#C0C0C0', '#808080', '#1E5BA8', '#1E5BA8'),
        'theme:mint_chocolate': ('#98FB98', '#3CB371', '#8B4513', '#5D2E0C'),
        'theme:sunset_purple': ('#FF7F50', '#FF6347', '#6B2D8E', '#6B2D8E'),
        'theme:steel_orange': ('#708090', '#4A5568', '#FF8C00', '#FF8C00'),
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


def show_styled_input(parent, title, label, default_text=""):
    """
    Show a styled input dialog that matches the app theme.
    Returns (text, ok) tuple like QInputDialog.getText().
    """
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(300)
    dialog.setStyleSheet("""
        QDialog {
            background-color: #F5F5F5;
        }
        QLabel {
            color: #202124;
            font-size: 10pt;
            padding: 4px;
        }
        QLineEdit {
            background-color: white;
            border: 1px solid #C0C0C0;
            border-radius: 4px;
            padding: 6px 8px;
            font-size: 10pt;
            color: #202124;
            selection-background-color: #4080C0;
        }
        QLineEdit:focus {
            border: 2px solid #4080C0;
        }
        QPushButton {
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
        QPushButton:hover {
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #E8E8E8, stop:1 #C8C8C8);
            border-color: #808080;
        }
        QPushButton:pressed {
            background-color: #C0C0C0;
        }
        QPushButton:default {
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #5090D0, stop:1 #3070B0);
            border: 1px solid #2060A0;
            color: white;
        }
        QPushButton:default:hover {
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #60A0E0, stop:1 #4080C0);
        }
    """)
    
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)
    
    # Label
    lbl = QLabel(label)
    layout.addWidget(lbl)
    
    # Input field
    line_edit = QLineEdit(default_text)
    line_edit.selectAll()
    layout.addWidget(line_edit)
    
    # Buttons
    button_layout = QHBoxLayout()
    button_layout.addStretch()
    
    ok_btn = QPushButton("OK")
    ok_btn.setDefault(True)
    ok_btn.clicked.connect(dialog.accept)
    
    cancel_btn = QPushButton("Cancel")
    cancel_btn.clicked.connect(dialog.reject)
    
    button_layout.addWidget(ok_btn)
    button_layout.addWidget(cancel_btn)
    layout.addLayout(button_layout)
    
    # Connect Enter key to accept
    line_edit.returnPressed.connect(dialog.accept)
    
    result = dialog.exec()
    return (line_edit.text(), result == QDialog.DialogCode.Accepted)


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
            # Row 1
            ("theme:blue_gold", "Blue & Gold", "#1E5BA8", "#D4A017"),
            ("theme:gold_blue", "Gold & Blue", "#D4A017", "#0D3A7A"),
            ("theme:navy_silver", "Navy & Silver", "#0A1E3E", "#C0C0C0"),
            ("theme:teal_coral", "Teal & Coral", "#008080", "#FF7F50"),
            # Row 2
            ("theme:purple_gold", "Purple & Gold", "#6B2D8E", "#FFD700"),
            ("theme:forest_cream", "Forest & Cream", "#228B22", "#FFFDD0"),
            ("theme:crimson_slate", "Crimson & Slate", "#DC143C", "#708090"),
            ("theme:ocean_sunset", "Ocean & Sunset", "#006994", "#FF6B35"),
            # Row 3 - New themes
            ("theme:silver_blue", "Silver & Blue", "#C0C0C0", "#1E5BA8"),
            ("theme:mint_chocolate", "Mint & Chocolate", "#98FB98", "#8B4513"),
            ("theme:sunset_purple", "Sunset & Purple", "#FF7F50", "#6B2D8E"),
            ("theme:steel_orange", "Steel & Orange", "#708090", "#FF8C00"),
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
            themed_grid.addWidget(btn, i // 4, i % 4)
        
        layout.addLayout(themed_grid)
        
        # ====== SOLID COLORS SECTION ======
        colors_label = QLabel("Solid Colors")
        colors_label.setStyleSheet("font-size: 8pt; color: #666; border: none; margin-top: 4px;")
        layout.addWidget(colors_label)
        
        # Color grid - 4 columns (pinks and yellows)
        grid = QGridLayout()
        grid.setSpacing(4)
        
        for i, color in enumerate(CATEGORY_COLORS):
            row = i // 4
            col = i % 4
            
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

class EditBookmarkDialog(QDialog):
    """
    Movable/resizable dialog for editing a bookmark's name and path.
    Uses SuiteView dark blue/gold framing.
    """
    
    accepted_result = pyqtSignal(str, str)  # Emits (new_name, new_path)
    rejected_result = pyqtSignal()
    
    def __init__(self, current_name, current_path, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        # For dragging the title bar
        self._drag_pos = None
        # For edge resizing
        self._resize_edge = None
        self._resize_start_pos = None
        self._resize_start_geo = None
        self.setMouseTracking(True)
        
        self.setMinimumSize(320, 160)
        self.resize(400, 180)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #F5F8FF;
                border: 3px solid #2563EB;
                border-radius: 4px;
            }
        """)
        
        self._result_set = False  # Track whether save was clicked
        self._setup_ui(current_name, current_path)
        
    def _setup_ui(self, current_name, current_path):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        
        # --- SuiteView-style title bar (royal blue/gold, matches dialog_title_bar) ---
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(32)
        self.title_bar.setCursor(Qt.CursorShape.SizeAllCursor)
        self.title_bar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1E3A8A, stop:0.5 #2563EB, stop:1 #1E3A8A);
                border: none;
                border-bottom: 2px solid #D4AF37;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
        """)
        tb_layout = QHBoxLayout(self.title_bar)
        tb_layout.setContentsMargins(10, 0, 4, 0)
        
        title_lbl = QLabel("Edit Bookmark")
        title_lbl.setStyleSheet("""
            QLabel {
                color: #FFD700;
                font-weight: 800;
                font-size: 10pt;
                font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
                background: transparent;
                border: none;
            }
        """)
        tb_layout.addWidget(title_lbl)
        tb_layout.addStretch()
        
        close_btn = QPushButton(" X ")
        close_btn.setFixedSize(28, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #F4D03F;
                font-size: 10pt;
                font-weight: bold;
                font-family: "Segoe UI", Tahoma, sans-serif;
                border: none;
                border-radius: 3px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #DC2626;
                color: white;
            }
        """)
        close_btn.clicked.connect(self._on_cancel)
        tb_layout.addWidget(close_btn)
        outer.addWidget(self.title_bar)
        
        # --- Content area ---
        content = QWidget()
        content.setStyleSheet("QWidget { border: none; background: transparent; }")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        
        # Name row
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_label = QLabel("Name:")
        name_label.setFixedWidth(55)
        name_label.setStyleSheet("QLabel { font-size: 9pt; color: #1E3A8A; font-weight: 700; font-family: 'Segoe UI', Tahoma, sans-serif; }")
        self.name_edit = QLineEdit(current_name)
        self.name_edit.setPlaceholderText("Display name")
        self.name_edit.setStyleSheet("""
            QLineEdit {
                border: 2px solid #8AAED8;
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 9pt;
                background: white;
                font-family: "Segoe UI", Tahoma, sans-serif;
            }
            QLineEdit:focus {
                border-color: #2563EB;
            }
        """)
        name_row.addWidget(name_label)
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)
        
        # Path row
        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        path_label = QLabel("Path/URL:")
        path_label.setFixedWidth(55)
        path_label.setStyleSheet("QLabel { font-size: 9pt; color: #1E3A8A; font-weight: 700; font-family: 'Segoe UI', Tahoma, sans-serif; }")
        self.path_edit = QLineEdit(current_path)
        self.path_edit.setPlaceholderText("File path, folder path, or URL")
        self.path_edit.setStyleSheet("""
            QLineEdit {
                border: 2px solid #8AAED8;
                border-radius: 3px;
                padding: 4px 6px;
                font-size: 9pt;
                background: white;
                font-family: "Segoe UI", Tahoma, sans-serif;
            }
            QLineEdit:focus {
                border-color: #2563EB;
            }
        """)
        path_row.addWidget(path_label)
        path_row.addWidget(self.path_edit)
        layout.addLayout(path_row)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(75)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #C0D8F0, stop:1 #A8C8E8);
                color: #1E3A8A;
                border: 2px solid #8AAED8;
                border-radius: 3px;
                padding: 5px 12px;
                font-size: 9pt;
                font-weight: 700;
                font-family: "Segoe UI", Tahoma, sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #D0E8FF, stop:1 #B8D8F8);
                border: 2px solid #2563EB;
            }
        """)
        cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(75)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #F4D03F, stop:1 #D4AF37);
                color: #0A1E5E;
                font-weight: 800;
                border: 2px solid #FFD700;
                border-radius: 3px;
                padding: 5px 12px;
                font-size: 9pt;
                font-family: "Segoe UI", Tahoma, sans-serif;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFD700, stop:1 #F4D03F);
                border: 2px solid #FFD700;
            }
        """)
        save_btn.clicked.connect(self._on_save)
        save_btn.setDefault(True)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
        outer.addWidget(content, 1)
        
        # Enter key saves
        self.name_edit.returnPressed.connect(self._on_save)
        self.path_edit.returnPressed.connect(self._on_save)
    
    # --- Drag-to-move via title bar ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check for edge resize first
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geo = self.geometry()
                return
            # Title bar drag
            if event.position().y() <= self.title_bar.height():
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        # Edge resize in progress
        if self._resize_edge and self._resize_start_pos:
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            geo = QRect(self._resize_start_geo)
            edge = self._resize_edge
            if 'right' in edge:
                geo.setRight(geo.right() + delta.x())
            if 'bottom' in edge:
                geo.setBottom(geo.bottom() + delta.y())
            if 'left' in edge:
                geo.setLeft(geo.left() + delta.x())
            if 'top' in edge:
                geo.setTop(geo.top() + delta.y())
            if geo.width() >= self.minimumWidth() and geo.height() >= self.minimumHeight():
                self.setGeometry(geo)
            return
        # Title bar dragging
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            return
        # Update cursor for edge hover
        edge = self._edge_at(event.position().toPoint())
        if edge:
            cursors = {
                'right': Qt.CursorShape.SizeHorCursor,
                'left': Qt.CursorShape.SizeHorCursor,
                'bottom': Qt.CursorShape.SizeVerCursor,
                'top': Qt.CursorShape.SizeVerCursor,
                'bottom-right': Qt.CursorShape.SizeFDiagCursor,
                'bottom-left': Qt.CursorShape.SizeBDiagCursor,
                'top-right': Qt.CursorShape.SizeBDiagCursor,
                'top-left': Qt.CursorShape.SizeFDiagCursor,
            }
            self.setCursor(cursors.get(edge, Qt.CursorShape.ArrowCursor))
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_edge = None
        self._resize_start_pos = None
        self._resize_start_geo = None
        super().mouseReleaseEvent(event)
    
    def _edge_at(self, pos, margin=6):
        """Return edge name if pos is near a dialog edge, else None."""
        r = self.rect()
        edge = ''
        if pos.y() >= r.height() - margin:
            edge += 'bottom'
        elif pos.y() <= margin:
            edge += 'top'
        if pos.x() >= r.width() - margin:
            edge += ('-' if edge else '') + 'right'
        elif pos.x() <= margin:
            edge += ('-' if edge else '') + 'left'
        return edge or None
    
    def _on_save(self):
        new_name = self.name_edit.text().strip()
        new_path = self.path_edit.text().strip()
        self._result_set = True
        self.accepted_result.emit(new_name, new_path)
        self.hide()
    
    def _on_cancel(self):
        self._result_set = False
        self.rejected_result.emit()
        self.hide()
    
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
        
        dialog.accepted_result.connect(on_accepted)
        
        # Center on parent or screen
        if parent:
            parent_geo = parent.window().geometry()
            dialog.move(
                parent_geo.center().x() - dialog.width() // 2,
                parent_geo.center().y() - dialog.height() // 2
            )
        
        dialog.name_edit.setFocus()
        dialog.name_edit.selectAll()
        
        # Use a local event loop so we block without calling exec()
        # which can propagate accept/reject up the widget hierarchy
        from PyQt6.QtCore import QEventLoop
        loop = QEventLoop()
        dialog.accepted_result.connect(loop.quit)
        dialog.rejected_result.connect(loop.quit)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        loop.exec()
        
        dialog.deleteLater()
        
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
        
        # Don't set tooltip directly - we'll show it with delay via enterEvent
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setStyleSheet(BOOKMARK_BUTTON_STYLE)
        
        # Enable hover tracking for stylesheet :hover to work
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    
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
        
        final_name = new_name if new_name else current_name
        final_path = new_path if new_path else current_path
        
        # Update via data manager using the bookmark's ID for proper persistence
        item_id = self.bookmark_data.get('id')
        if item_id is not None and self.data_manager:
            from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
            manager = get_bookmark_manager()
            manager.update_bookmark(item_id, name=final_name, path=final_path)
            manager.save()
            # Refresh the container display
            self.data_manager.refresh()
        elif self.data_manager:
            # Fallback: update in-place and save
            self.bookmark_data['name'] = final_name
            self.bookmark_data['path'] = final_path
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
    
    def enterEvent(self, event):
        """Highlight on hover and show path in footer immediately"""
        # Manually set hover background since stylesheet :hover isn't working
        self.setStyleSheet("""
            QPushButton {
                background-color: #B0E0FF;
                border: 1px solid #0088FF;
                border-radius: 2px;
                padding: 4px 8px;
                text-align: left;
                font-size: 9pt;
                color: #202124;
            }
        """)
        # Show path in footer immediately
        update_footer_status(self._path)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Remove highlight and clear footer on mouse leave"""
        # Restore normal style
        self.setStyleSheet(BOOKMARK_BUTTON_STYLE)
        # Clear footer
        update_footer_status("")
        super().leaveEvent(event)
    
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
        global _drag_in_progress
        
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self.drag_start_pos is None:
            return
        
        distance = (event.pos() - self.drag_start_pos).manhattanLength()
        if distance < 10:
            return
        
        _drag_in_progress = True  # Set global flag
        
        # Start drag
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Unified item move format - bookmarks and categories use the same structure
        item_data = {
            'type': 'bookmark',
            'item': self.bookmark_data  # {id, name, path}
        }
        mime_data.setData('application/x-item-move', json.dumps(item_data).encode())
        
        mime_data.setText(f"Move: {self.bookmark_data.get('name', 'bookmark')}")
        
        drag.setMimeData(mime_data)
        
        logger.info(f"Dragging bookmark '{self.bookmark_data.get('name')}' from category '{self.source_category}' (bar {self.source_bar_id})")
        result = drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        _drag_in_progress = False  # Clear global flag
        
        # Don't close popup here - let the dropEvent handler decide whether to close
        # (dropEvent keeps popup open for same-category reorders, closes for cross-category moves)


# =============================================================================
# CategoryPopup - Popup window showing category contents (supports nesting)
# =============================================================================

# Global registry of all open category popups for proper cleanup
_open_category_popups = set()
_global_close_timer = None
_drag_in_progress = False  # Track if a drag operation is happening

def _check_and_close_orphaned_popups():
    """Check if mouse is over any popup - if not, close all"""
    global _open_category_popups, _drag_in_progress
    from PyQt6.QtGui import QCursor
    from PyQt6.QtWidgets import QApplication
    
    # Don't close popups during drag operations
    if _drag_in_progress:
        return
    
    # Get the widget under the cursor
    cursor_pos = QCursor.pos()
    widget_under = QApplication.widgetAt(cursor_pos)
    
    # Check if widget is part of any popup chain or a category button
    if widget_under:
        # Walk up parent chain to see if it's in a popup or on a category button
        w = widget_under
        while w:
            if isinstance(w, CategoryPopup):
                return  # Mouse is in a popup - don't close
            if isinstance(w, CategoryButton):
                return  # Mouse is on a category button - don't close
            w = w.parent()
    
    # Mouse not in any popup chain - close all
    close_all_category_popups()

def _start_global_close_timer():
    """Start the global timer that checks for orphaned popups"""
    global _global_close_timer
    if _global_close_timer is None:
        _global_close_timer = QTimer()
        _global_close_timer.timeout.connect(_check_and_close_orphaned_popups)
    if not _global_close_timer.isActive():
        _global_close_timer.start(150)  # Check every 150ms

def _stop_global_close_timer():
    """Stop the global close timer when no popups are open"""
    global _global_close_timer
    if _global_close_timer and _global_close_timer.isActive():
        _global_close_timer.stop()

def close_all_category_popups():
    """Close all open category popups - call this when app closes or needs cleanup"""
    global _open_category_popups
    _stop_global_close_timer()
    for popup in list(_open_category_popups):
        try:
            if popup:
                popup._force_close()
        except:
            pass
    _open_category_popups.clear()

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
                 subcategories=None, parent_popup=None, nesting_level=0,
                 category_id: int = None):
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
            category_id: integer ID of the category for reliable operations
        """
        # Use Tool window type instead of Popup - Popup windows get destroyed on hide
        # Tool windows stay alive and can be shown/hidden efficiently
        super().__init__(parent_widget, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        
        self.category_name = category_name
        self.category_id = category_id  # Integer ID for reliable operations
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
        
        # Mouse tracking for hover-based closing
        self._mouse_inside = False
        self.setMouseTracking(True)
        
        # Register in global popup registry for cleanup
        global _open_category_popups
        _open_category_popups.add(self)
        _start_global_close_timer()  # Start global timer when popup opens
        
        # Set attribute to delete on close
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)  # We manage lifecycle
        
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
        
        # Build and render items using shared helpers
        self._build_unified_items()
        self._render_items()
        
        self.container_layout.addStretch()
        scroll.setWidget(self.container)
        layout.addWidget(scroll)
        
        # Drop indicator
        self.drop_indicator = QFrame(self)
        self.drop_indicator.setStyleSheet("background-color: #A080C0;")
        self.drop_indicator.setFixedHeight(2)
        self.drop_indicator.hide()
        
        self._update_popup_size()
    
    def _build_unified_items(self):
        """Build the unified items list from current category data"""
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        global_categories = manager.get_global_categories()
        
        # Check if category has item_order (new format) or fall back to old format
        cat_data = global_categories.get(self.category_name, {})
        if isinstance(cat_data, dict):
            item_order = cat_data.get('item_order', None)
        else:
            item_order = None
        
        # Build display list - unified_items contains tuples of (type, data)
        unified_items = []
        
        if item_order is not None:
            # New format: use item_order for display sequence
            for order_item in item_order:
                if order_item.get('type') == 'subcategory':
                    subcat_name = order_item.get('name')
                    if subcat_name and subcat_name in self.subcategories:
                        unified_items.append(('subcategory', subcat_name))
                elif order_item.get('type') == 'bookmark':
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
        
        self._unified_items = unified_items
    
    def _render_items(self):
        """Render items into the container layout based on _unified_items"""
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        category_colors = manager.get_global_colors()
        global_categories = manager.get_global_categories()
        
        for item_type, item_data in self._unified_items:
            if item_type == 'subcategory':
                subcat_name = item_data
                subcat_color = category_colors.get(subcat_name)
                
                subcat_data = global_categories.get(subcat_name, {})
                if isinstance(subcat_data, dict):
                    subcat_items = subcat_data.get('items', [])
                    subcat_subcats = subcat_data.get('subcategories', [])
                    subcat_id = subcat_data.get('_item_id')
                else:
                    subcat_items = subcat_data if isinstance(subcat_data, list) else []
                    subcat_subcats = []
                    subcat_id = None
                
                btn = CategoryButton(
                    category_name=subcat_name,
                    category_items=subcat_items,
                    subcategories=subcat_subcats,
                    parent=self.container,
                    data_manager=self.data_manager,
                    source_bar_id=self.source_bar_id,
                    orientation='popup',
                    color=subcat_color,
                    parent_popup=self,
                    parent_category=self.category_name,
                    category_id=subcat_id
                )
                btn.item_clicked.connect(self._on_item_clicked)
                self.container_layout.addWidget(btn)
            else:
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
    
    def _update_popup_size(self):
        """Calculate and set popup height based on item count"""
        item_count = len(self._unified_items)
        item_height = 28
        total_height = item_count * item_height + 8
        max_height = 400
        self.setFixedHeight(min(total_height, max_height))
    
    def _rebuild_contents(self):
        """Rebuild popup contents to reflect updated data (e.g., after reorder)"""
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        
        # Update category items from fresh data
        if self.category_id:
            category_data = manager.find_item_by_id(self.category_id)
            if category_data:
                self.category_items = [i for i in category_data.get('items', []) if i.get('type') == 'bookmark']
                self.subcategories = [i.get('name') for i in category_data.get('items', []) if i.get('type') == 'category']
        
        # Clear existing widgets from container
        while self.container_layout.count() > 0:
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Rebuild using shared helpers
        self._build_unified_items()
        self._render_items()
        self.container_layout.addStretch()
        self._update_popup_size()
    
    def _on_item_clicked(self, path):
        """Handle item click - closes entire popup chain"""
        if path:
            self.item_clicked.emit(path)
            self.close_entire_chain()
    
    def close_entire_chain(self):
        """Close this popup and all parent/child popups in the chain"""
        # Stop any pending hide timers
        if hasattr(self, '_hover_hide_timer'):
            self._hover_hide_timer.stop()
        
        # Close all child popups first (recursively)
        for child in list(self.child_popups):
            if child and hasattr(child, 'close_entire_chain'):
                child.close_entire_chain()
        self.child_popups.clear()
        
        # Hide this popup
        self.hide()
        self._mouse_inside = False
        self.popup_closed.emit()
        
        # Clear parent button's reference to this popup
        if self._parent_button and hasattr(self._parent_button, 'active_popup'):
            if self._parent_button.active_popup == self:
                self._parent_button.active_popup = None
        
        # DON'T close parent chain - only close downward (children)
        # This prevents closing siblings when one branch closes
    
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
        if mime.hasFormat('application/x-item-move') or mime.hasUrls():
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat('application/x-item-move') or mime.hasUrls():
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        self._hide_drop_indicator()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        """
        Handle item drop into this category popup.
        
        Unified logic for bookmarks and categories:
        - Item with ID: use move_item() to move into this category
        - New file (no ID): add as new bookmark
        - Categories: check circular reference before moving
        """
        # Capture drop_index BEFORE hiding indicator (which resets it to -1)
        drop_idx = self.drop_index if self.drop_index >= 0 else None
        self._hide_drop_indicator()
        mime = event.mimeData()
        
        # Handle URL drops (files from file system)
        if mime.hasUrls() and not mime.hasFormat('application/x-item-move'):
            self._handle_url_drop(event)
            return
        
        if not mime.hasFormat('application/x-item-move'):
            event.ignore()
            return
        
        try:
            item_data = json.loads(event.mimeData().data('application/x-item-move').data().decode())
            item_type = item_data.get('type')  # 'bookmark' or 'category'
            item = item_data.get('item', {})
            item_id = item.get('id')
            
            if not item:
                event.ignore()
                return
            
            from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
            manager = get_bookmark_manager()
            
            # Get target category ID
            target_category_id = self.category_id
            if not target_category_id:
                target_category = manager.find_category_by_name(self.category_name)
                target_category_id = target_category.get('id') if target_category else None
            
            if not target_category_id:
                logger.warning(f"Target category '{self.category_name}' not found")
                event.ignore()
                return
            
            # For categories, check for circular reference (can't make category a child of itself or its descendants)
            if item_type == 'category':
                if item.get('name') == self.category_name:
                    logger.warning(f"Cannot drop category '{item.get('name')}' into itself")
                    event.ignore()
                    return
                if manager._is_ancestor_of(item.get('name'), self.category_name):
                    logger.warning(f"Cannot make '{item.get('name')}' a subcategory of its descendant")
                    event.ignore()
                    return
            
            logger.info(f"Drop into category '{self.category_name}': {item_type} '{item.get('name')}' (id={item_id})")
            
            # Track if this is a same-category reorder (popup should stay open)
            is_same_category_reorder = False
            
            if item_id:
                # drop_idx was captured at the start of dropEvent before _hide_drop_indicator reset it
                
                # Check if this is a reorder within the same category
                # move_item() removes then inserts, which shifts indices and causes wrong placement
                # reorder_item() correctly adjusts the index after removal
                source_location = manager.find_item_location(item_id)
                target_category = manager.find_item_by_id(target_category_id)
                target_items = target_category.get('items', []) if target_category else None
                
                is_same_category = (source_location and target_items is not None and 
                                    source_location[0] is target_items)
                
                if is_same_category and drop_idx is not None:
                    # Same category reorder - use reorder_item to handle index adjustment
                    if manager.reorder_item(item_id, drop_idx):
                        manager.save()
                        is_same_category_reorder = True
                        logger.info(f"Reordered {item_type} within category '{self.category_name}'")
                    else:
                        logger.warning(f"reorder_item failed for {item_type} id={item_id}")
                elif manager.move_item(item_id, target_category_id=target_category_id, target_index=drop_idx):
                    # Cross-category move
                    manager.save()
                    # Refresh parent BookmarkContainer UI to show new order immediately
                    if self.data_manager and hasattr(self.data_manager, 'refresh'):
                        self.data_manager.refresh()
                    logger.info(f"Moved {item_type} into category '{self.category_name}'")
                else:
                    logger.warning(f"move_item failed for {item_type} id={item_id}")
            else:
                # No ID - must be new bookmark (categories always have IDs)
                if item_type == 'bookmark':
                    path = item.get('path')
                    name = item.get('name', Path(path).name if path else 'Unnamed')
                    result = manager.add_bookmark_to_category_by_name(self.category_name, name, path)
                    if result:
                        manager.save()
                        # Refresh parent BookmarkContainer UI to show new bookmark immediately
                        if self.data_manager and hasattr(self.data_manager, 'refresh'):
                            self.data_manager.refresh()
                        logger.info(f"Added new bookmark '{name}' to category '{self.category_name}'")
                else:
                    logger.warning(f"Cannot add category without ID")
            
            # For same-category reorder, keep popup open and refresh contents
            # For cross-category moves or new items, close the popup
            if is_same_category_reorder:
                self._rebuild_contents()
            else:
                self.close()
            event.acceptProposedAction()
            
        except Exception as e:
            logger.error(f"Error handling drop in category popup: {e}")
            import traceback
            traceback.print_exc()
            event.ignore()
    
    def _handle_url_drop(self, event):
        """Handle dropping files/folders from file system"""
        try:
            from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
            manager = get_bookmark_manager()
            
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if os.path.exists(path):
                        name = Path(path).name
                        manager.add_bookmark_to_category_by_name(self.category_name, name, path)
            
            manager.save()
            # Refresh parent BookmarkContainer UI to show new bookmark immediately
            if self.data_manager and hasattr(self.data_manager, 'refresh'):
                self.data_manager.refresh()
            self.close()
            event.acceptProposedAction()
        except Exception as e:
            logger.error(f"Error handling URL drop: {e}")
            event.ignore()

    def showEvent(self, event):
        """When shown, activate to receive focus events"""
        super().showEvent(event)
        self._mouse_inside = True  # Assume mouse is inside when shown
        # Use timer to defer focus activation - allows window to render first
        QTimer.singleShot(0, self._activate_popup)
    
    def _activate_popup(self):
        """Activate popup after it's visible"""
        if self.isVisible():
            self.activateWindow()
            self.setFocus()
    
    def enterEvent(self, event):
        """Track mouse entering popup"""
        self._mouse_inside = True
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Track mouse leaving popup"""
        self._mouse_inside = False
        super().leaveEvent(event)
    
    def focusOutEvent(self, event):
        """
        Don't auto-hide on focus loss - popups stay open until toggle.
        This enables dragging items into nested categories.
        """
        super().focusOutEvent(event)
        # NOTE: Removed auto-hide behavior to support nested category drag-drop
    
    def closeEvent(self, event):
        """Handle close event - clean up properly"""
        self._force_close()
        event.accept()
    
    def _force_close(self):
        """Force close this popup and remove from registry"""
        global _open_category_popups
        
        # Close children first
        for child in list(self.child_popups):
            if child and hasattr(child, '_force_close'):
                child._force_close()
        self.child_popups.clear()
        
        # Remove from registry
        _open_category_popups.discard(self)
        
        # Stop global timer if no more popups
        if not _open_category_popups:
            _stop_global_close_timer()
        
        # Clear parent button reference
        if self._parent_button and hasattr(self._parent_button, 'active_popup'):
            if self._parent_button.active_popup == self:
                self._parent_button.active_popup = None
        
        # Hide
        self.hide()
        self.popup_closed.emit()


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
                 color=None, subcategories=None, parent_popup=None, parent_category=None,
                 category_id: int = None):
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
            category_id: integer ID of the category for reliable operations
        """
        super().__init__(f"🗄 {category_name} ▸", parent)
        
        self.category_name = category_name
        self.category_id = category_id  # Integer ID for reliable operations
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
        
        # Hover timer for delayed popup show/hide
        self._hover_show_timer = QTimer(self)
        self._hover_show_timer.setSingleShot(True)
        self._hover_show_timer.timeout.connect(self._on_hover_show_timeout)
        self._mouse_inside = False
        
        # No tooltip for categories - they interfere with the UI
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
            self.drag_start_pos = None
            # For top-level categories (not in popup), toggle on click
            if not self.dragging and not self.parent_popup:
                if self.active_popup and self.active_popup.isVisible():
                    self.active_popup.close()
                else:
                    self._show_popup()
            self.dragging = False
        super().mouseReleaseEvent(event)
    
    def enterEvent(self, event):
        """Show popup on mouse hover - only for nested categories in popups."""
        self._mouse_inside = True
        self._hover_show_timer.stop()
        # Only show on hover for nested categories (inside popups)
        if self.parent_popup:
            self._show_popup()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Track mouse leaving button"""
        self._mouse_inside = False
        self._hover_show_timer.stop()
        super().leaveEvent(event)
    
    def dragEnterEvent(self, event):
        """Accept drag enter but don't auto-open popup to preserve click behavior"""
        mime = event.mimeData()
        if mime.hasFormat('application/x-item-move') or mime.hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        """Accept drag moves over this button"""
        mime = event.mimeData()
        if mime.hasFormat('application/x-item-move') or mime.hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event):
        """
        Handle drop directly onto this category button.
        
        Unified handling for both bookmarks and categories.
        """
        mime = event.mimeData()
        
        if mime.hasFormat('application/x-item-move'):
            try:
                item_data = json.loads(mime.data('application/x-item-move').data().decode())
                item_type = item_data.get('type')  # 'bookmark' or 'category'
                item = item_data.get('item', {})
                item_id = item.get('id')
                
                # For categories, don't drop onto self
                if item_type == 'category' and item.get('name') == self.category_name:
                    event.ignore()
                    return
                
                from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
                manager = get_bookmark_manager()
                
                # For categories, check for circular reference
                if item_type == 'category' and manager._is_ancestor_of(item.get('name'), self.category_name):
                    logger.warning(f"Cannot make '{item.get('name')}' a subcategory of its descendant")
                    event.ignore()
                    return
                
                # Get target category ID
                target_category_id = self.category_id
                if not target_category_id:
                    target_cat = manager.find_category_by_name(self.category_name)
                    target_category_id = target_cat.get('id') if target_cat else None
                
                if item_id and target_category_id:
                    # Move item into this category
                    if manager.move_item(item_id, target_category_id=target_category_id):
                        manager.save()
                        logger.info(f"Moved {item_type} '{item.get('name')}' into '{self.category_name}'")
                        close_all_category_popups()
                        for container in BookmarkContainerRegistry.get_all_flat():
                            try:
                                container.refresh()
                            except RuntimeError:
                                pass
                elif item_type == 'bookmark':
                    # New bookmark without ID
                    self._handle_drop(item)
                    close_all_category_popups()
                
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error dropping item onto category button: {e}")
                event.ignore()
        
        elif mime.hasUrls():
            # Dropping file/folder URLs from file system - create bookmarks
            try:
                for url in mime.urls():
                    if url.isLocalFile():
                        path = url.toLocalFile()
                        if os.path.exists(path):
                            name = Path(path).name
                            self._handle_drop({'name': name, 'path': path})
                
                close_all_category_popups()
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error dropping files onto category: {e}")
                event.ignore()
        else:
            event.ignore()
    
    def _on_hover_show_timeout(self):
        """Called after hover delay - show popup if mouse still inside"""
        if self._mouse_inside:
            self._show_popup()
    
    def mouseMoveEvent(self, event):
        global _drag_in_progress
        
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self.drag_start_pos is None:
            return
        
        distance = (event.pos() - self.drag_start_pos).manhattanLength()
        if distance < 10:
            return
        
        self.dragging = True
        _drag_in_progress = True  # Set global flag
        
        # Start drag
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Store index for reordering within container
        mime_data.setText(str(self.item_index))
        mime_data.setData('application/x-container-item-index', str(self.item_index).encode())
        
        # Unified item move format - categories and bookmarks use the same structure
        item_data = {
            'type': 'category',
            'item': {
                'id': self.category_id,
                'name': self.category_name,
                'color': self.category_color
            }
        }
        mime_data.setData('application/x-item-move', json.dumps(item_data).encode())
        
        drag.setMimeData(mime_data)
        
        logger.info(f"Dragging category: {self.category_name}")
        result = drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        self.dragging = False
        _drag_in_progress = False  # Clear global flag
    
    def _show_popup(self):
        """Show the category popup - position depends on context (bar vs nested)"""
        global _drag_in_progress
        
        # Don't toggle - hover shows, leave hides
        if self.active_popup and self.active_popup.isVisible():
            return  # Already visible, nothing to do
        
        # Close other popups before showing this one (but not during drag operations)
        if not _drag_in_progress:
            if not self.parent_popup:
                # Top-level category - close any other open popups
                close_all_category_popups()
            else:
                # Nested category - close sibling popups (other children of same parent)
                # This prevents multiple branches from staying open
                for child in list(self.parent_popup.child_popups):
                    if child and child.isVisible():
                        child.close_entire_chain()
                self.parent_popup.child_popups.clear()
        
        # Determine nesting level
        nesting_level = 0
        if self.parent_popup:
            nesting_level = self.parent_popup.nesting_level + 1
        
        # Reuse existing popup if it exists
        if self.active_popup:
            global_pos = self._calculate_popup_position(self.active_popup)
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
            nesting_level=nesting_level,
            category_id=self.category_id
        )
        
        popup.item_clicked.connect(self._on_popup_item_clicked)
        popup.popup_closed.connect(self._on_popup_closed)
        
        # Register with parent popup if nested
        if self.parent_popup:
            self.parent_popup.register_child_popup(popup)
        
        # Position popup - first show to get actual size, then reposition if needed
        global_pos = self._calculate_popup_position(popup)
        popup.move(global_pos)
        popup.show()
        
        # Reposition after show to use actual popup width for left-side positioning
        global_pos = self._calculate_popup_position(popup)
        popup.move(global_pos)
        
        self.active_popup = popup
        self.popup_opened.emit(popup)
    
    def _calculate_popup_position(self, popup=None):
        """Calculate popup position based on context (bar vs nested in popup)"""
        if self.orientation == 'popup' or self.parent_popup:
            # Inside a popup - position to the right
            global_pos = self.mapToGlobal(self.rect().topRight())
            
            # Adjust for screen boundaries
            screen = self.screen()
            if screen:
                screen_geo = screen.availableGeometry()
                # Use passed popup, or active_popup, with fallback to estimate
                target_popup = popup or self.active_popup
                popup_width = target_popup.width() if target_popup and target_popup.width() > 0 else 250
                
                # If popup would go off right edge, position to the left instead
                if global_pos.x() + popup_width > screen_geo.right():
                    global_pos = self.mapToGlobal(self.rect().topLeft())
                    global_pos.setX(global_pos.x() - popup_width - 2)  # 2px gap to avoid overlap
            
            return global_pos
        else:
            # On a bar - position below the mouse cursor 
            cursor_pos = QCursor.pos()
            global_pos = self.mapToGlobal(self.rect().bottomLeft())
            global_pos.setX(cursor_pos.x() - 5)  # left/right offset of mouse click
            return global_pos
    
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
        
        # Save the color on the category item
        if not self.data_manager:
            return
        
        # Update color on this bar's category item
        self.data_manager.set_category_color(self.category_name, color)
    
    def _rename_category(self):
        """Rename this category (global rename)"""
        new_name, ok = show_styled_input(
            self,
            "Rename Category",
            f"Enter new name for '{self.category_name}':",
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
        name, ok = show_styled_input(
            self,
            "New Subcategory",
            f"Enter name for new subcategory in '{self.category_name}':",
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
        if mime.hasFormat('application/x-item-move') or mime.hasUrls():
            # Check for circular reference when receiving category
            if mime.hasFormat('application/x-item-move'):
                try:
                    item_data = json.loads(mime.data('application/x-item-move').data().decode())
                    if item_data.get('type') == 'category':
                        dragged_name = item_data.get('item', {}).get('name', '')
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
        """Handle drops onto this category - unified for bookmarks and categories"""
        mime = event.mimeData()
        
        if mime.hasFormat('application/x-item-move'):
            try:
                item_data = json.loads(mime.data('application/x-item-move').data().decode())
                item_type = item_data.get('type')  # 'bookmark' or 'category'
                item = item_data.get('item', {})
                item_id = item.get('id')
                
                # For categories, check circular reference
                if item_type == 'category':
                    dragged_name = item.get('name', '')
                    if self._is_descendant_of(dragged_name):
                        logger.warning(f"Cannot drop '{dragged_name}' into its descendant '{self.category_name}'")
                        event.ignore()
                        return
                
                logger.info(f"Dropping {item_type} '{item.get('name')}' into category '{self.category_name}'")
                
                if not self.data_manager:
                    event.ignore()
                    return
                
                from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
                manager = get_bookmark_manager()
                
                # Get target category ID
                target_category_id = self.category_id
                if not target_category_id:
                    target_cat = manager.find_category_by_name(self.category_name)
                    target_category_id = target_cat.get('id') if target_cat else None
                
                if item_id and target_category_id:
                    # Move item into this category
                    if manager.move_item(item_id, target_category_id=target_category_id):
                        manager.save()
                        logger.info(f"Moved {item_type} '{item.get('name')}' into '{self.category_name}'")
                        close_all_category_popups()
                        for container in BookmarkContainerRegistry.get_all_flat():
                            try:
                                container.refresh()
                            except RuntimeError:
                                pass
                elif item_type == 'bookmark':
                    # New bookmark without ID
                    self._handle_drop(item)
                    close_all_category_popups()
                
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error handling item drop: {e}")
                event.ignore()
        
        elif mime.hasUrls():
            try:
                for url in mime.urls():
                    path = url.toLocalFile()
                    if path:
                        name = Path(path).name
                        bookmark = {'name': name, 'path': path}
                        self._handle_drop(bookmark)
                
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error handling URL drop: {e}")
                event.ignore()
        else:
            event.ignore()
    
    def _handle_drop(self, bookmark):
        """
        Handle drop onto this category button.
        
        Simplified logic:
        - Bookmark with ID: use move_item() to move into this category
        - New bookmark (no ID): add as new bookmark
        """
        if not self.data_manager:
            return
        
        path = bookmark.get('path')
        name = bookmark.get('name', Path(path).name if path else 'Unnamed')
        if not path:
            return
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        
        # Get target category ID
        target_category_id = self.category_id
        if not target_category_id:
            target_category = manager.find_category_by_name(self.category_name)
            target_category_id = target_category.get('id') if target_category else None
        
        if not target_category_id:
            logger.warning(f"Target category '{self.category_name}' not found")
            return
        
        bookmark_id = bookmark.get('id')
        
        logger.info(f"Bookmark drop on category button '{self.category_name}': '{name}' (id={bookmark_id})")
        
        if bookmark_id:
            # Move bookmark into this category - source doesn't matter
            if manager.move_item(bookmark_id, target_category_id=target_category_id):
                logger.info(f"Moved bookmark into category '{self.category_name}'")
            else:
                logger.warning(f"move_item failed for bookmark id={bookmark_id}")
                return
        else:
            # No ID - add as new bookmark
            result = manager.add_bookmark_to_category_by_name(self.category_name, name, path)
            if not result:
                logger.warning(f"Failed to add bookmark to category '{self.category_name}' - may be duplicate")
                return
            logger.info(f"Added new bookmark '{name}' to category '{self.category_name}'")
        
        manager.save()
        
        # Refresh all containers
        for container in BookmarkContainerRegistry.get_all_flat():
            try:
                container.refresh()
            except RuntimeError:
                pass  # Widget may have been deleted


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
        background-color: #00FFFF;
        border: 2px solid #0088FF;
    }
    QPushButton:pressed {
        background-color: #00CCCC;
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
        background-color: #00FFFF;
        border: 2px solid #0088FF;
    }
    QPushButton:pressed {
        background-color: #00CCCC;
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
        self._path = bookmark_data.get('path', '')
        
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
        
        # Don't set tooltip directly - we'll show it with delay via enterEvent
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Apply style based on orientation
        if orientation == 'horizontal':
            self.setStyleSheet(STANDALONE_BOOKMARK_STYLE_HORIZONTAL)
            self.setMaximumWidth(180)
        else:
            self.setStyleSheet(STANDALONE_BOOKMARK_STYLE_VERTICAL)
            self.setFixedHeight(26)
        
        # Enable hover tracking for stylesheet :hover to work
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        
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
    
    def enterEvent(self, event):
        """Show path in footer on mouse enter"""
        # Manually set hover background since stylesheet :hover isn't working
        # Use orientation-specific styles to prevent layout shifts
        if self.orientation == 'horizontal':
            self.setStyleSheet("""
                QPushButton {
                    background-color: #B0E0FF;
                    border: 1px solid #0088FF;
                    border-radius: 4px;
                    padding: 4px 8px;
                    text-align: left;
                    font-size: 9pt;
                    color: #202124;
                }
            """)
        else:
            # Vertical (sidebar) - must match exact dimensions to prevent shift
            self.setStyleSheet("""
                QPushButton {
                    background-color: #B0E0FF;
                    border: 1px solid #0088FF;
                    border-radius: 3px;
                    padding: 4px 8px;
                    text-align: left;
                    font-size: 9pt;
                    color: #202124;
                    min-height: 22px;
                }
            """)
        # Update footer with path
        update_footer_status(self._path)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Clear footer on mouse leave"""
        # Restore normal style based on orientation
        if self.orientation == 'horizontal':
            self.setStyleSheet(STANDALONE_BOOKMARK_STYLE_HORIZONTAL)
        else:
            self.setStyleSheet(STANDALONE_BOOKMARK_STYLE_VERTICAL)
        # Clear footer
        update_footer_status("")
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.dragging = False
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.dragging and self.drag_start_pos is not None:
                # It was a click, emit the signal
                path = self.bookmark_data.get('path', '')
                
                # Handle URLs directly here - open in browser
                if path.startswith('http://') or path.startswith('https://'):
                    import webbrowser
                    webbrowser.open(path)
                else:
                    self.clicked_path.emit(path)
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
        
        # Unified item move format - bookmarks and categories use the same structure
        item_data = {
            'type': 'bookmark',
            'item': self.bookmark_data  # {id, name, path}
        }
        mime_data.setData('application/x-item-move', json.dumps(item_data).encode())
        
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
        """Open the parent folder in SuiteView file navigator"""
        from pathlib import Path as PathLib
        path = PathLib(self.bookmark_data.get('path', ''))
        if path.exists():
            parent = path.parent if path.is_file() else path
            # Navigate within SuiteView instead of opening Windows Explorer
            if self.container:
                self.container.navigate_to_path.emit(str(parent))
    
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
        
        final_name = new_name if new_name else current_name
        final_path = new_path if new_path else current_path
        
        # Update via data manager using the bookmark's ID for proper persistence
        item_id = self.bookmark_data.get('id')
        if item_id is not None:
            from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
            manager = get_bookmark_manager()
            manager.update_bookmark(item_id, name=final_name, path=final_path)
            manager.save()
        
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
    Multiple containers can share the same bar_id (e.g. sidebar bookmarks
    in different tabs all use bar_id=1).
    """
    _instance = None
    _containers: Dict[int, List['BookmarkContainer']] = {}  # bar_id -> [BookmarkContainer, ...]
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, bar_id: int, container: 'BookmarkContainer'):
        """Register a container by its bar ID (supports multiple per bar_id)"""
        if bar_id not in cls._containers:
            cls._containers[bar_id] = []
        if container not in cls._containers[bar_id]:
            cls._containers[bar_id].append(container)
        logger.debug(f"BookmarkContainer registered: bar_id={bar_id} (total for this bar: {len(cls._containers[bar_id])})")
    
    @classmethod
    def unregister(cls, bar_id: int, container: 'BookmarkContainer' = None):
        """Unregister a container. If container is None, removes all for that bar_id."""
        if bar_id in cls._containers:
            if container is not None:
                cls._containers[bar_id] = [c for c in cls._containers[bar_id] if c is not container]
                if not cls._containers[bar_id]:
                    del cls._containers[bar_id]
            else:
                del cls._containers[bar_id]
            logger.debug(f"BookmarkContainer unregistered: bar_id={bar_id}")
    
    @classmethod
    def get(cls, bar_id: int) -> Optional['BookmarkContainer']:
        """Get the first container for a bar ID (backwards compat)"""
        containers = cls._containers.get(bar_id, [])
        return containers[0] if containers else None
    
    @classmethod
    def get_all_for_bar(cls, bar_id: int) -> List['BookmarkContainer']:
        """Get all containers registered for a given bar_id"""
        return list(cls._containers.get(bar_id, []))
    
    @classmethod
    def get_all(cls) -> Dict[int, 'BookmarkContainer']:
        """Get all registered containers (one per bar, backwards compat).
        Returns {bar_id: first_container} for each bar."""
        return {bid: containers[0] for bid, containers in cls._containers.items() if containers}
    
    @classmethod
    def get_all_flat(cls) -> List['BookmarkContainer']:
        """Get every registered container instance as a flat list."""
        result = []
        for containers in cls._containers.values():
            result.extend(containers)
        return result
    
    @classmethod
    def get_others(cls, exclude_bar_id: int) -> list:
        """Get all containers except those with the specified bar_id"""
        result = []
        for bid, containers in cls._containers.items():
            if bid != exclude_bar_id:
                result.extend(containers)
        return result


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
        
        # Connect item_clicked to navigate_to_path for backwards compatibility
        self.item_clicked.connect(self.navigate_to_path.emit)
        
        # Auto-populate bookmarks on creation
        self.refresh()
    
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
        self.scroll_area.viewport().setAcceptDrops(False)  # Let drops pass through to items_container
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
        self.scroll_area.viewport().setAcceptDrops(False)  # Let drops pass through to items_container
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
        # current format: bookmark data is inline with id
        new_item = self._data_manager.create_bookmark(
            bookmark_data.get('name', ''),
            bookmark_data.get('path', '')
        )
        
        items = self.data_store.setdefault("items", [])
        
        if insert_at is not None and 0 <= insert_at <= len(items):
            items.insert(insert_at, new_item)
        else:
            items.append(new_item)
        
        self._save_and_refresh()
    
    def add_category(self, category_name, category_items=None, color=None, insert_at=None):
        """Add a category to this bar"""
        # Check if already in this bar's items
        items = self.data_store.setdefault("items", [])
        for item in items:
            if item.get('type') == 'category' and item.get('name') == category_name:
                return False  # Already in this bar
        
        # current format: create category inline with items
        # Always include color (use default purple if not specified)
        new_item = {
            'id': self._data_manager.generate_item_id(),
            'type': 'category',
            'name': category_name,
            'color': color or DEFAULT_CATEGORY_COLOR,
            'items': []
        }
        
        # Add any initial items
        if category_items:
            for item in category_items:
                if isinstance(item, dict):
                    bookmark = self._data_manager.create_bookmark(
                        item.get('name', ''),
                        item.get('path', '')
                    )
                    new_item['items'].append(bookmark)
        
        if insert_at is not None and 0 <= insert_at <= len(items):
            items.insert(insert_at, new_item)
        else:
            items.append(new_item)
        
        self._save_and_refresh()
        return True
    
    def remove_item(self, index):
        """Remove an item by index from this bar's items list"""
        items = self.items
        if 0 <= index < len(items):
            items.pop(index)
            self._save_and_refresh()
    
    def remove_category(self, category_name):
        """Remove a category by name from this bar"""
        items = self.items
        for i, item in enumerate(items):
            if item.get('type') == 'category' and item.get('name') == category_name:
                items.pop(i)
                self._save_and_refresh()
                return True
        return False
    
    def rename_category(self, old_name, new_name):
        """Rename a category globally"""
        if self._data_manager.rename_category(old_name, new_name):
            self._save_and_refresh()
            return True
        return False
    
    def set_category_color(self, category_name, color):
        """Set the color for a category"""
        # color is stored on the category item itself
        items = self.items
        for item in items:
            if item.get('type') == 'category' and item.get('name') == category_name:
                item['color'] = color
                self._save_and_refresh()
                return True
        return False
    
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
        # bookmark data format: {'id': 1, 'type': 'bookmark', 'name': '...', 'path': '...'}
        bookmark_data = {
            'name': item_data.get('name', ''),
            'path': item_data.get('path', ''),
            'id': item_data.get('id')
        }
        
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
        # category is inline with items nested
        # {'id': 2, 'type': 'category', 'name': 'Work', 'color': '#...', 'items': [...]}
        
        category_name = item_data.get('name', '')
        if not category_name:
            return None
        
        # items and color are inline on the item
        if 'items' in item_data:
            # current format - items are directly nested
            category_items = []
            subcategories = []
            for child in item_data.get('items', []):
                if child.get('type') == 'bookmark':
                    category_items.append({
                        'name': child.get('name', ''),
                        'path': child.get('path', ''),
                        'id': child.get('id')
                    })
                elif child.get('type') == 'category':
                    subcategories.append(child.get('name', ''))
            category_color = item_data.get('color')
        else:
            # Fallback - look up in global categories
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
            color=category_color,
            category_id=item_data.get('id')
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
        """Save data and refresh ALL containers sharing this bar_id.
        
        This ensures that bookmark/category changes propagate across
        all tabs (e.g. multiple FileNav tabs each have their own
        BookmarkContainer with bar_id=1).
        """
        self._save()
        # Refresh every container registered for the same bar_id
        siblings = BookmarkContainerRegistry.get_all_for_bar(self.bar_id)
        for container in siblings:
            try:
                container.refresh()
            except RuntimeError:
                pass  # Widget may have been deleted
        if not siblings:
            # Fallback — at least refresh ourselves
            self.refresh()
    
    # -------------------------------------------------------------------------
    # Backwards Compatibility Methods (for code that used BookmarkBar)
    # -------------------------------------------------------------------------
    
    @property
    def bookmarks_data(self):
        """
        Backwards compatibility property.
        Returns a dict-like view of the data that matches the old BookmarkBar structure:
        - 'items': Same as self.items (from data_store)
        - 'bar_items': Same as self.items (alias)
        - 'categories': Global categories dict
        - 'category_colors': Global category colors
        """
        return {
            'items': self.data_store.get('items', []),
            'bar_items': self.data_store.get('items', []),
            'categories': self.categories,
            'category_colors': self.category_colors,
        }
    
    def save_bookmarks(self):
        """Backwards compatibility method - alias for _save()"""
        self._save()
    
    def refresh_bookmarks(self):
        """Backwards compatibility method - alias for refresh()"""
        self.refresh()
    
    def show_add_bookmark_dialog(self):
        """Show add bookmark dialog (for toolbar button)"""
        from suiteview.ui.dialogs.shortcuts_dialog import AddBookmarkDialog
        from PyQt6.QtWidgets import QDialog
        
        categories = list(self.categories.keys())
        
        dialog = AddBookmarkDialog(categories, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            bookmark = dialog.get_bookmark_data()
            if bookmark['name'] and bookmark['path']:
                category = bookmark['category']
                target_bar_id = bookmark.get('target_bar_id')
                
                # Remove the category and target_bar_id from bookmark data for storage
                del bookmark['category']
                if 'target_bar_id' in bookmark:
                    del bookmark['target_bar_id']
                
                if category == "__BAR__" and target_bar_id is not None:
                    # Add directly to a specific bookmark bar
                    bar_data = self._data_manager.get_bar_data(target_bar_id)
                    
                    # Add to the bar's items
                    if 'items' not in bar_data:
                        bar_data['items'] = []
                    bar_data['items'].append(self._data_manager.create_bookmark(
                        bookmark.get('name', ''),
                        bookmark.get('path', '')
                    ))
                    
                    # Save and refresh ALL containers for the target bar
                    self._data_manager.save()
                    for container in BookmarkContainerRegistry.get_all_for_bar(target_bar_id):
                        try:
                            container.refresh()
                        except RuntimeError:
                            pass  # Widget may have been deleted
                else:
                    # Add to category
                    if not self._data_manager.category_exists(category):
                        self._data_manager.create_category(category)
                        # Add category to this bar's items if it's new
                        self.data_store.setdefault('items', []).append({
                            'type': 'category',
                            'name': category
                        })
                    
                    # Add bookmark to category
                    categories_data = self._data_manager.get_global_categories()
                    if category in categories_data:
                        cat_data = categories_data[category]
                        if isinstance(cat_data, dict):
                            cat_data.setdefault('items', []).append(bookmark)
                        elif isinstance(cat_data, list):
                            cat_data.append(bookmark)
                    
                    self._save_and_refresh()
    
    def _show_container_context_menu(self, pos):
        """Show context menu for empty space in the container"""
        menu = QMenu(self)
        menu.setStyleSheet(CATEGORY_CONTEXT_MENU_STYLE)
        
        # Add new bookmark/link
        add_bookmark_action = menu.addAction("🔗 Add Link")
        
        # Add new category
        add_category_action = menu.addAction("📁 New Category")
        
        action = menu.exec(self.items_container.mapToGlobal(pos))
        
        if action == add_bookmark_action:
            self.show_add_bookmark_dialog()
        elif action == add_category_action:
            self._prompt_new_category()
    
    def _prompt_new_category(self):
        """Prompt user to create a new category"""
        name, ok = show_styled_input(
            self,
            "New Category",
            "Enter category name:",
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
            mime.hasFormat('application/x-item-move') or
            mime.hasUrls()):
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        """Handle drag move - show drop indicator"""
        mime = event.mimeData()
        if (mime.hasFormat('application/x-container-item-index') or
            mime.hasFormat('application/x-item-move') or
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
        Handle drop events on the bar.
        
        Unified logic for bookmarks and categories - both are just "items":
        - Item with ID: use move_item() which handles everything
        - New file drop: add as new bookmark
        - Internal reorder: handled by index-based move
        """
        self._hide_drop_indicator()
        mime = event.mimeData()
        drop_index = self._calculate_drop_index(event.position().toPoint())
        
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        manager = get_bookmark_manager()
        
        # Unified item drop (bookmark or category)
        if mime.hasFormat('application/x-item-move'):
            try:
                item_data = json.loads(mime.data('application/x-item-move').data().decode())
                item_type = item_data.get('type')  # 'bookmark' or 'category'
                item = item_data.get('item', {})
                item_id = item.get('id')
                
                logger.info(f"Item drop on bar {self.bar_id}: {item_type} '{item.get('name')}' (id={item_id})")
                
                if item_id:
                    # Move item to this bar using ID - works for both bookmarks and categories
                    if manager.move_item(item_id, target_bar_id=self.bar_id, target_index=drop_index):
                        manager.save()
                        self._refresh_all_containers()
                        event.acceptProposedAction()
                        return
                    else:
                        logger.warning(f"move_item failed for {item_type} id={item_id}")
                elif item_type == 'bookmark':
                    # No ID - add as new bookmark
                    path = item.get('path')
                    name = item.get('name', '')
                    if path:
                        manager.add_bookmark_to_bar(self.bar_id, name, path, drop_index)
                        manager.save()
                        self._refresh_all_containers()
                        event.acceptProposedAction()
                        return
                
                event.ignore()
                return
            except Exception as e:
                logger.error(f"Error handling item drop: {e}")
        
        # Internal reordering (same bar, using visual index)
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
        
        # File/folder drops from file system - add as new bookmark
        if mime.hasUrls():
            for url in mime.urls():
                path = url.toLocalFile()
                if path:
                    self._handle_file_drop(path, drop_index)
            event.acceptProposedAction()
            return
        
        event.ignore()
    
    def _refresh_all_containers(self):
        """Refresh all registered bookmark containers (across all bars)"""
        for container in BookmarkContainerRegistry.get_all_flat():
            try:
                container.refresh()
            except RuntimeError:
                pass  # Widget may have been deleted
    
    def _handle_file_drop(self, path: str, drop_index: int):
        """Handle a file/folder being dropped onto this container - add as bookmark"""
        from pathlib import Path as PathLib
        
        path_obj = PathLib(path)
        if not path_obj.exists():
            logger.warning(f"Dropped path does not exist: {path}")
            return
        
        # Check if already exists in this bar
        items = self.data_store.get('items', [])
        for item in items:
            if item.get('type') == 'bookmark':
                item_path = item.get('path')
                if item_path == path:
                    logger.info(f"Path already exists in bar {self.bar_id}: {path}")
                    return
        
        # Create bookmark data
        bookmark_data = {
            'name': path_obj.name,
            'path': path,
            'type': 'folder' if path_obj.is_dir() else 'file'
        }
        
        # Add to this container
        self.add_bookmark(bookmark_data, insert_at=drop_index)
        logger.info(f"Added dropped file/folder to bar {self.bar_id}: {path}")
    
    def _promote_subcategory_to_toplevel(self, category_name, parent_name, drop_index):
        """Promote a subcategory to a top-level category on this bar"""
        logger.info(f"Promoting subcategory '{category_name}' from parent '{parent_name}' to top-level")
        
        if self._data_manager.promote_to_toplevel(category_name, parent_name, 
                                                   self.bar_id, drop_index):
            self._save_and_refresh()
            return True
        return False
    
    def remove_bookmark_from_category(self, category_name, path):
        """Remove a bookmark from a category by its path"""
        if self._data_manager.remove_bookmark_from_category_by_name(category_name, path):
            self._data_manager.save()
            self.refresh()
    
    def remove_item_by_path(self, path):
        """Remove an item from the items list by its path"""
        items = self.data_store.get("items", [])
        for i, item in enumerate(items):
            if item.get('type') == 'bookmark' and item.get('path') == path:
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
