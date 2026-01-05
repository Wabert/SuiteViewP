"""
Bookmarks Panel Dialog
Displays categorized bookmarks to folders, files, SharePoint sites, and URLs
Similar to browser bookmarks bar
"""

import os
import sys
import json
import subprocess
import webbrowser
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget,
                              QPushButton, QLabel, QScrollArea, QFrame,
                              QInputDialog, QMessageBox, QLineEdit, QComboBox,
                              QMenu, QGridLayout, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint
from PyQt6.QtGui import QIcon, QAction, QCursor, QDrag

import logging
logger = logging.getLogger(__name__)


def detect_sharepoint_type(url):
    """Detect if SharePoint URL points to a file or folder"""
    url_lower = url.lower()
    
    # Common file extensions to check for
    file_extensions = [
        '.xls', '.xlsx', '.xlsm', '.xlsb',  # Excel
        '.doc', '.docx', '.docm',  # Word
        '.ppt', '.pptx', '.pptm',  # PowerPoint
        '.pdf', '.txt', '.csv',  # Common files
        '.zip', '.rar', '.7z',  # Archives
        '.png', '.jpg', '.jpeg', '.gif', '.bmp',  # Images
        '.mp4', '.avi', '.mov', '.wmv',  # Video
        '.mp3', '.wav',  # Audio
        '.py', '.js', '.html', '.css', '.json', '.xml'  # Code files
    ]
    
    # Check if URL contains a file extension
    for ext in file_extensions:
        if ext in url_lower:
            return 'file'
    
    # SharePoint URL patterns that indicate folders
    # e.g., /sites/SiteName/FolderName or /Shared%20Documents/
    folder_indicators = ['/forms/allitems', '/shared%20documents', '/:f:/']
    for indicator in folder_indicators:
        if indicator in url_lower:
            return 'folder'
    
    # Default to URL if we can't determine
    return 'url'


class AddBookmarkDialog(QDialog):
    """Dialog to add a new bookmark"""
    
    def __init__(self, categories, parent=None):
        super().__init__(parent)
        self.categories = categories
        self.setWindowTitle("Add Bookmark")
        self.setModal(True)
        self.resize(650, 240)
        
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("<h3>Add New Bookmark</h3>")
        layout.addWidget(title_label)
        
        # Name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Display name for the bookmark")
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # Path/URL input
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Path/URL:"))
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("File path, folder path, URL, or SharePoint link")
        path_layout.addWidget(self.path_input)
        layout.addLayout(path_layout)
        
        # Category selection
        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(categories)
        category_layout.addWidget(self.category_combo)
        layout.addLayout(category_layout)
        
        # Open in App checkbox (for SharePoint files)
        from PyQt6.QtWidgets import QCheckBox
        self.open_in_app_checkbox = QCheckBox("Open in App (SharePoint files open in desktop app instead of browser)")
        self.open_in_app_checkbox.setChecked(True)  # Default to checked
        self.open_in_app_checkbox.setStyleSheet("margin-top: 5px;")
        layout.addWidget(self.open_in_app_checkbox)
        
        # Type hint
        type_label = QLabel("💡 Tip: This can be a folder path, file path, SharePoint URL, or any web URL")
        type_label.setStyleSheet("color: #0066cc; font-size: 9pt; margin-top: 10px;")
        layout.addWidget(type_label)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
    
    def get_bookmark_data(self):
        """Return the bookmark data"""
        return {
            'name': self.name_input.text().strip(),
            'path': self.path_input.text().strip(),
            'category': self.category_combo.currentText(),
            'type': self.detect_type(self.path_input.text().strip()),
            'open_in_app': self.open_in_app_checkbox.isChecked()
        }
    
    def detect_type(self, path):
        """Detect the type of shortcut"""
        if path.startswith('http://') or path.startswith('https://'):
            if 'sharepoint' in path.lower():
                # Check if SharePoint link points to a file or folder
                return detect_sharepoint_type(path)
            else:
                return 'url'
        elif os.path.isfile(path):
            return 'file'
        elif os.path.isdir(path):
            return 'folder'
        else:
            # Could be network path or invalid
            return 'path'


class BookmarkButton(QPushButton):
    """Individual bookmark button - compact version with drag support"""
    
    right_clicked = pyqtSignal(object)  # Emits the bookmark data
    bookmark_clicked = pyqtSignal()  # Signal when bookmark is opened
    folder_bookmark_clicked = pyqtSignal(str)  # Signal when folder bookmark is clicked (path)
    
    def __init__(self, bookmark_data, parent=None):
        super().__init__(parent)
        self.bookmark_data = bookmark_data
        self.drag_start_position = None
        
        # Set button text without icon
        self.setText(bookmark_data['name'])
        
        self.setToolTip(bookmark_data['path'])
        
        # Get colors based on bookmark type
        bookmark_type = bookmark_data.get('type', 'path')
        path = bookmark_data.get('path', '')
        
        # Check if it's a SharePoint URL
        is_sharepoint_url = path.startswith('http') and 'sharepoint' in path.lower()
        
        # Determine SharePoint type (file or folder)
        sharepoint_type = None
        if is_sharepoint_url:
            sharepoint_type = detect_sharepoint_type(path)
        
        # Detect file type for color coding
        file_app_type = self.detect_file_app_type(path)
        
        style = self.get_style_for_type(bookmark_type, is_sharepoint_url, sharepoint_type, file_app_type)
        self.setStyleSheet(style)
        
        self.clicked.connect(self.open_bookmark)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
    
    def detect_file_app_type(self, path):
        """Detect which application type a file belongs to based on extension"""
        path_lower = path.lower()
        
        # Excel files - green
        if any(ext in path_lower for ext in ['.xlsx', '.xls', '.xlsm', '.xlsb', '.csv']):
            return 'excel'
        # Word files - blue
        elif any(ext in path_lower for ext in ['.docx', '.doc', '.docm', '.rtf']):
            return 'word'
        # PowerPoint files - orange
        elif any(ext in path_lower for ext in ['.pptx', '.ppt', '.pptm']):
            return 'powerpoint'
        # Access files - maroon
        elif any(ext in path_lower for ext in ['.accdb', '.mdb', '.accde', '.mde']):
            return 'access'
        # PDF files - red
        elif '.pdf' in path_lower:
            return 'pdf'
        # Text/code files - gray
        elif any(ext in path_lower for ext in ['.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.sql']):
            return 'text'
        # Image files - purple
        elif any(ext in path_lower for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg']):
            return 'image'
        # Archive files - brown
        elif any(ext in path_lower for ext in ['.zip', '.rar', '.7z', '.tar', '.gz']):
            return 'archive'
        else:
            return None
    
    def get_file_type_colors(self, file_app_type):
        """Get colors based on file application type"""
        colors = {
            'excel': {
                'bg_color': '#d4edda',      # Light green
                'text_color': '#155724',     # Dark green
                'hover_bg': '#c3e6cb',
                'border_color': '#28a745',   # Excel green
                'gradient_end': '#28a745'
            },
            'word': {
                'bg_color': '#cce5ff',       # Light blue
                'text_color': '#004085',     # Dark blue
                'hover_bg': '#b8daff',
                'border_color': '#2b579a',   # Word blue
                'gradient_end': '#2b579a'
            },
            'powerpoint': {
                'bg_color': '#ffe4cc',       # Light orange
                'text_color': '#7d3c00',     # Dark orange
                'hover_bg': '#ffd4b3',
                'border_color': '#d24726',   # PowerPoint orange/red
                'gradient_end': '#d24726'
            },
            'access': {
                'bg_color': '#f5d7d7',       # Light maroon/pink
                'text_color': '#5c1a1a',     # Dark maroon
                'hover_bg': '#f0c4c4',
                'border_color': '#a4373a',   # Access maroon
                'gradient_end': '#a4373a'
            },
            'pdf': {
                'bg_color': '#f8d7da',       # Light red
                'text_color': '#721c24',     # Dark red
                'hover_bg': '#f5c6cb',
                'border_color': '#dc3545',   # PDF red
                'gradient_end': '#dc3545'
            },
            'text': {
                'bg_color': '#e9ecef',       # Light gray
                'text_color': '#495057',     # Dark gray
                'hover_bg': '#dee2e6',
                'border_color': '#6c757d',   # Gray
                'gradient_end': '#6c757d'
            },
            'image': {
                'bg_color': '#e8daef',       # Light purple
                'text_color': '#4a235a',     # Dark purple
                'hover_bg': '#d7bde2',
                'border_color': '#8e44ad',   # Purple
                'gradient_end': '#8e44ad'
            },
            'archive': {
                'bg_color': '#f5e6d3',       # Light brown
                'text_color': '#5d4e37',     # Dark brown
                'hover_bg': '#eddcc8',
                'border_color': '#8b7355',   # Brown
                'gradient_end': '#8b7355'
            }
        }
        return colors.get(file_app_type)
    
    def get_style_for_type(self, bookmark_type, is_sharepoint_url=False, sharepoint_type=None, file_app_type=None):
        """Get stylesheet based on bookmark type"""
        
        # Get file type colors if applicable
        file_colors = self.get_file_type_colors(file_app_type) if file_app_type else None
        
        # Special gradient style for SharePoint files (file color to blue)
        if is_sharepoint_url and sharepoint_type == 'file':
            if file_colors:
                # Use file type color gradient to blue
                return f"""
                    QPushButton {{
                        text-align: left;
                        padding: 1px 3px;
                        margin: 0px;
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                            stop:0 {file_colors['bg_color']}, stop:1 #a8d4ff);
                        color: {file_colors['text_color']};
                        border: 1px solid {file_colors['border_color']};
                        border-radius: 2px;
                        font-size: 8pt;
                        font-weight: normal;
                        min-height: 16px;
                        max-height: 18px;
                    }}
                    QPushButton:hover {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                            stop:0 {file_colors['hover_bg']}, stop:1 #c4e3ff);
                        border-color: #0078d4;
                    }}
                    QPushButton:pressed {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                            stop:0 {file_colors['border_color']}, stop:1 #7abfff);
                    }}
                """
            else:
                # Default white to blue gradient
                return """
                    QPushButton {
                        text-align: left;
                        padding: 1px 3px;
                        margin: 0px;
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                            stop:0 #ffffff, stop:1 #a8d4ff);
                        color: #1a3a5c;
                        border: 1px solid #7abfff;
                        border-radius: 2px;
                        font-size: 8pt;
                        font-weight: normal;
                        min-height: 16px;
                        max-height: 18px;
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                            stop:0 #f0f8ff, stop:1 #c4e3ff);
                        border-color: #0078d4;
                    }
                    QPushButton:pressed {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                            stop:0 #e8f4ff, stop:1 #7abfff);
                    }
                """
        
        # Special gradient style for SharePoint folders (yellow to blue)
        if is_sharepoint_url and sharepoint_type == 'folder':
            return """
                QPushButton {
                    text-align: left;
                    padding: 1px 3px;
                    margin: 0px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #fff3b0, stop:1 #a8d4ff);
                    color: #1a3a5c;
                    border: 1px solid #7abfff;
                    border-radius: 2px;
                    font-size: 8pt;
                    font-weight: normal;
                    min-height: 16px;
                    max-height: 18px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #ffe680, stop:1 #c4e3ff);
                    border-color: #0078d4;
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #e6d280, stop:1 #7abfff);
                }
            """
        
        # Local files with file type colors
        if bookmark_type == 'file' and file_colors:
            return f"""
                QPushButton {{
                    text-align: left;
                    padding: 1px 3px;
                    margin: 0px;
                    background-color: {file_colors['bg_color']};
                    color: {file_colors['text_color']};
                    border: 1px solid {file_colors['border_color']};
                    border-radius: 2px;
                    font-size: 8pt;
                    font-weight: normal;
                    min-height: 16px;
                    max-height: 18px;
                }}
                QPushButton:hover {{
                    background-color: {file_colors['hover_bg']};
                    border-color: #0078d4;
                }}
                QPushButton:pressed {{
                    background-color: {file_colors['border_color']};
                }}
            """
        
        # Define colors for each type
        if bookmark_type == 'folder':
            bg_color = '#fff3b0'  # Light yellow
            text_color = '#333333'  # Dark text for contrast
            hover_bg = '#ffe680'
            border_color = '#e6d280'
        elif bookmark_type in ['url', 'sharepoint']:
            bg_color = '#a8d4ff'  # Light blue
            text_color = '#1a3a5c'  # Dark blue text
            hover_bg = '#c4e3ff'
            border_color = '#7abfff'
        else:  # file, path, or unknown
            bg_color = '#ffffff'  # White
            text_color = '#333333'  # Dark text
            hover_bg = '#f0f0f0'
            border_color = '#cccccc'
        
        return f"""
            QPushButton {{
                text-align: left;
                padding: 1px 3px;
                margin: 0px;
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 2px;
                font-size: 8pt;
                font-weight: normal;
                min-height: 16px;
                max-height: 18px;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border-color: #0078d4;
            }}
            QPushButton:pressed {{
                background-color: {border_color};
            }}
        """
    
    def get_icon_for_type(self, bookmark_type):
        """Get emoji icon for bookmark type"""
        icons = {
            'folder': '📁',
            'file': '📄',
            'url': '🌐',
            'sharepoint': '🔗',
            'path': '📍'
        }
        return icons.get(bookmark_type, '📌')
    
    def open_bookmark(self):
        """Open the bookmark"""
        path = self.bookmark_data['path']
        bookmark_type = self.bookmark_data['type']
        open_in_app = self.bookmark_data.get('open_in_app', True)  # Default to True
        
        try:
            # Check if this is a URL (SharePoint or otherwise)
            is_url = path.startswith('http://') or path.startswith('https://')
            
            if is_url:
                # It's a URL - handle SharePoint specially, otherwise just open in browser
                if 'sharepoint' in path.lower() and open_in_app:
                    sp_type = detect_sharepoint_type(path)
                    if sp_type == 'file':
                        # Convert SharePoint URL to open in desktop app
                        desktop_url = self.convert_sharepoint_to_desktop_url(path)
                        webbrowser.open(desktop_url)
                    else:
                        # SharePoint folder or unknown - open in browser
                        webbrowser.open(path)
                else:
                    # Regular URL - open in default browser
                    webbrowser.open(path)
                self.bookmark_clicked.emit()
            elif bookmark_type == 'folder':
                # Local folder - emit signal for folder navigation in the app
                self.folder_bookmark_clicked.emit(path)
                self.bookmark_clicked.emit()
            elif bookmark_type == 'file':
                # Local file - open with default application
                if sys.platform == 'win32':
                    os.startfile(path)
                elif sys.platform == 'darwin':
                    subprocess.run(['open', path])
                else:
                    subprocess.run(['xdg-open', path])
                self.bookmark_clicked.emit()
            else:
                # Try to open as path
                if sys.platform == 'win32':
                    os.startfile(path)
                else:
                    QMessageBox.warning(self, "Cannot Open", f"Cannot open: {path}")
                self.bookmark_clicked.emit()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open bookmark: {str(e)}")
    
    def convert_sharepoint_to_desktop_url(self, url):
        """Convert SharePoint web URL to desktop app URL"""
        # SharePoint URLs for files typically look like:
        # https://company.sharepoint.com/:x:/r/sites/SiteName/Shared%20Documents/file.xlsx
        # or https://company.sharepoint.com/sites/SiteName/Shared%20Documents/file.xlsx
        # 
        # To open in desktop app, we can use the ms-excel:/ms-word:/ms-powerpoint: protocol
        # or add ?web=0 parameter to force desktop app
        
        url_lower = url.lower()
        
        # Check file type and construct appropriate URL
        if any(ext in url_lower for ext in ['.xlsx', '.xls', '.xlsm', '.xlsb']):
            # Excel file - use ms-excel: protocol
            return f"ms-excel:ofe|u|{url}"
        elif any(ext in url_lower for ext in ['.docx', '.doc', '.docm']):
            # Word file - use ms-word: protocol  
            return f"ms-word:ofe|u|{url}"
        elif any(ext in url_lower for ext in ['.pptx', '.ppt', '.pptm']):
            # PowerPoint file - use ms-powerpoint: protocol
            return f"ms-powerpoint:ofe|u|{url}"
        else:
            # For other files, try adding web=0 parameter or just return original
            # The web=0 parameter tells SharePoint to open in desktop app
            if '?' in url:
                return f"{url}&web=0"
            else:
                return f"{url}?web=0"
    
    def show_context_menu(self, pos):
        """Show context menu for bookmark"""
        self.right_clicked.emit(self.bookmark_data)
    
    def mousePressEvent(self, event):
        """Handle mouse press for drag start"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for drag operation"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self.drag_start_position is None:
            return
        
        # Check if we've moved far enough to start a drag
        if (event.pos() - self.drag_start_position).manhattanLength() < 10:
            return
        
        # Start drag operation
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Store bookmark data as JSON in mime data
        mime_data.setText(json.dumps(self.bookmark_data))
        drag.setMimeData(mime_data)
        
        # Execute drag (this blocks until drop or cancel)
        drag.exec(Qt.DropAction.MoveAction)


class CategoryPanel(QFrame):
    """Panel for a category of bookmarks - vertical column layout with drop support"""
    
    bookmark_opened = pyqtSignal()  # Signal when any bookmark is clicked
    folder_opened = pyqtSignal(str)  # Signal when folder bookmark is clicked (path)
    remove_bookmark = pyqtSignal(str, dict)  # category, bookmark_data
    edit_bookmark = pyqtSignal(str, dict)  # category, bookmark_data
    remove_category = pyqtSignal(str)  # category name
    rename_category_signal = pyqtSignal(str)  # category name to rename
    move_bookmark = pyqtSignal(dict, str, int)  # bookmark_data, target_category, insert_index
    
    def __init__(self, category_name, bookmarks, parent=None):
        super().__init__(parent)
        self.category_name = category_name
        self.bookmarks = bookmarks
        self.drop_indicator_index = -1  # Track where to show drop indicator
        
        # Enable drop support
        self.setAcceptDrops(True)
        
        # Fixed width for column layout
        self.setFixedWidth(180)
        
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            CategoryPanel {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 3px;
                margin: 0px;
                padding: 0px;
            }
        """)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 2, 4, 2)
        self.main_layout.setSpacing(0)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Category header with right-click menu
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        
        self.category_label = QLabel(category_name)
        self.category_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.category_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.category_label.setStyleSheet("""
            QLabel {
                font-size: 10pt;
                font-weight: bold;
                color: #000000;
                background-color: transparent;
                padding: 6px 0px;
                margin: 0px;
                border: none;
                border-bottom: 1px solid #dee2e6;
            }
        """)
        self.category_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.category_label.customContextMenuRequested.connect(self.show_category_menu)
        header_layout.addWidget(self.category_label, 1)
        
        self.main_layout.addLayout(header_layout)
        
        # Container for bookmarks (so we can manipulate them easily)
        self.bookmarks_container = QWidget()
        self.bookmarks_layout = QVBoxLayout(self.bookmarks_container)
        self.bookmarks_layout.setContentsMargins(0, 0, 0, 0)
        self.bookmarks_layout.setSpacing(0)
        
        # Bookmarks - vertical list (no grid, just stacked)
        for bookmark in bookmarks:
            btn = BookmarkButton(bookmark)
            btn.right_clicked.connect(lambda b: self.show_bookmark_menu(b))
            btn.bookmark_clicked.connect(self.bookmark_opened.emit)
            btn.folder_bookmark_clicked.connect(self.folder_opened.emit)
            self.bookmarks_layout.addWidget(btn)
        
        # Add empty state message if no bookmarks
        if not bookmarks:
            empty_label = QLabel("No bookmarks in this category")
            empty_label.setStyleSheet("color: #6c757d; font-style: italic; padding: 4px; font-size: 8pt;")
            self.bookmarks_layout.addWidget(empty_label)
        
        self.main_layout.addWidget(self.bookmarks_container)
    
    def show_bookmark_menu(self, bookmark_data):
        """Show context menu for a bookmark"""
        menu = QMenu(self)
        
        edit_action = QAction("✏️ Edit Bookmark", self)
        edit_action.triggered.connect(lambda: self.edit_bookmark.emit(self.category_name, bookmark_data))
        menu.addAction(edit_action)
        
        menu.addSeparator()
        
        remove_action = QAction("🗑️ Remove from Bookmarks", self)
        remove_action.triggered.connect(lambda: self.remove_bookmark.emit(self.category_name, bookmark_data))
        menu.addAction(remove_action)
        
        menu.exec(QCursor.pos())
    
    def show_category_menu(self, pos):
        """Show context menu for category name"""
        menu = QMenu(self)
        
        rename_action = QAction("✏️ Rename Category", self)
        rename_action.triggered.connect(lambda: self.rename_category_signal.emit(self.category_name))
        menu.addAction(rename_action)
        
        # Only allow deletion for non-default categories
        if self.category_name not in ['General', 'Favorites']:
            menu.addSeparator()
            delete_action = QAction("🗑️ Delete Category", self)
            delete_action.triggered.connect(lambda: self.remove_category.emit(self.category_name))
            menu.addAction(delete_action)
        
        menu.exec(self.category_label.mapToGlobal(pos))
    
    def get_drop_index(self, pos):
        """Calculate the index where a bookmark should be inserted based on drop position"""
        # Get the position relative to the bookmarks container
        container_pos = self.bookmarks_container.mapFrom(self, pos)
        
        # Iterate through bookmark buttons to find insertion point
        for i in range(self.bookmarks_layout.count()):
            widget = self.bookmarks_layout.itemAt(i).widget()
            if widget and isinstance(widget, BookmarkButton):
                widget_center = widget.y() + widget.height() / 2
                if container_pos.y() < widget_center:
                    return i  # Insert before this widget
        
        # If we're past all widgets, insert at the end
        return self.bookmarks_layout.count()
    
    def dragEnterEvent(self, event):
        """Handle drag enter - accept if it's text (bookmark JSON)"""
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def dragMoveEvent(self, event):
        """Handle drag move - show insertion indicator"""
        if event.mimeData().hasText():
            event.acceptProposedAction()
            
            # Calculate insertion index (use position() for PyQt6)
            pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            drop_index = self.get_drop_index(pos)
            
            # Update visual feedback
            self.update_drop_indicator(drop_index)
    
    def dragLeaveEvent(self, event):
        """Handle drag leave - remove indicator"""
        self.clear_drop_indicator()
    
    def update_drop_indicator(self, index):
        """Show a visual indicator of where the bookmark will be inserted"""
        # Remove old indicators
        self.clear_drop_indicator()
        
        # Add visual indicator at the insertion point
        for i in range(self.bookmarks_layout.count()):
            widget = self.bookmarks_layout.itemAt(i).widget()
            if widget and isinstance(widget, BookmarkButton):
                if i == index:
                    # Show drop line above this button
                    widget.setStyleSheet("""
                        QPushButton {
                            text-align: left;
                            padding: 2px 6px;
                            background-color: #ffffff;
                            border: 1px solid #dee2e6;
                            border-radius: 2px;
                            font-size: 9pt;
                            min-height: 20px;
                            max-height: 24px;
                            border-top: 2px solid #0078d4;
                        }
                    """)
                else:
                    # Reset to normal
                    widget.setStyleSheet("""
                        QPushButton {
                            text-align: left;
                            padding: 2px 6px;
                            background-color: #ffffff;
                            border: 1px solid #dee2e6;
                            border-radius: 2px;
                            font-size: 9pt;
                            min-height: 20px;
                            max-height: 24px;
                        }
                        QPushButton:hover {
                            background-color: #e7f3ff;
                            border-color: #0078d4;
                        }
                        QPushButton:pressed {
                            background-color: #deecf9;
                        }
                    """)
    
    def clear_drop_indicator(self):
        """Remove all drop indicators"""
        for i in range(self.bookmarks_layout.count()):
            widget = self.bookmarks_layout.itemAt(i).widget()
            if widget and isinstance(widget, BookmarkButton):
                widget.setStyleSheet("""
                    QPushButton {
                        text-align: left;
                        padding: 2px 6px;
                        background-color: #ffffff;
                        border: 1px solid #dee2e6;
                        border-radius: 2px;
                        font-size: 9pt;
                        min-height: 20px;
                        max-height: 24px;
                    }
                    QPushButton:hover {
                        background-color: #e7f3ff;
                        border-color: #0078d4;
                    }
                    QPushButton:pressed {
                        background-color: #deecf9;
                    }
                """)
    
    def dropEvent(self, event):
        """Handle drop - move bookmark to this category at specific position"""
        # Clear indicators
        self.clear_drop_indicator()
        
        if event.mimeData().hasText():
            try:
                # Parse the bookmark data from JSON
                bookmark_data = json.loads(event.mimeData().text())
                
                # Calculate insertion index (use position() for PyQt6)
                pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                drop_index = self.get_drop_index(pos)
                
                # Emit signal to move the bookmark with position
                self.move_bookmark.emit(bookmark_data, self.category_name, drop_index)
                
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error handling drop: {e}")


class BookmarksDialog(QDialog):
    """Main bookmarks panel dialog - compact vertical layout with auto-close"""
    
    navigate_to_path = pyqtSignal(str)  # Signal to navigate file explorer to a path
    
    # Class variable to persist size during session
    _saved_size = None
    
    def __init__(self, parent=None, button_pos=None):
        super().__init__(parent)
        self.setWindowTitle("Bookmarks")
        self.button_pos = button_pos  # Store button position for placement
        self.drag_position = None  # For window dragging
        
        # Calculate width based on parent window
        parent_width = 800  # Default width
        if parent:
            # Get the top-level parent window
            top_parent = parent.window() if hasattr(parent, 'window') else parent
            if top_parent:
                parent_width = top_parent.width()
        
        # Restore saved size or use parent width
        if BookmarksDialog._saved_size:
            self.resize(BookmarksDialog._saved_size)
        else:
            self.resize(parent_width, 400)  # Match parent window width
        self.setMinimumSize(400, 200)  # Minimum size for resizing
        
        # Remove Windows title bar but keep resize functionality
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.Window
        )
        
        # Initialize resize tracking variables
        self.resizing = False
        self.resize_edge = None
        self.resize_start_pos = None
        self.resize_start_geometry = None
        self.edge_margin = 10  # Pixels from edge to detect resize
        
        # Enable mouse tracking for resize cursor updates
        self.setMouseTracking(True)
        
        # Install event filter to handle mouse tracking on child widgets
        self.installEventFilter(self)
        
        # Load bookmarks data
        self.bookmarks_file = Path.home() / ".suiteview" / "bookmarks.json"
        self.bookmarks_data = self.load_bookmarks()
        
        self.init_ui()
        
        # Position under button if position provided
        if button_pos:
            self.move(button_pos.x(), button_pos.y())
    
    def closeEvent(self, event):
        """Save dialog size when closing"""
        BookmarksDialog._saved_size = self.size()
        super().closeEvent(event)
    
    def eventFilter(self, obj, event):
        """Event filter to handle mouse tracking across child widgets"""
        if event.type() == event.Type.MouseMove:
            # Get global position and convert to dialog coordinates
            if hasattr(event, 'globalPosition'):
                global_pos = event.globalPosition().toPoint()
            else:
                global_pos = event.globalPos()
            
            local_pos = self.mapFromGlobal(global_pos)
            
            # Only update cursor if not currently dragging/resizing
            if not self.resizing and self.drag_position is None:
                edge = self.get_resize_edge(local_pos)
                self.update_cursor(edge)
        
        return super().eventFilter(obj, event)
    
    def get_resize_edge(self, pos):
        """Determine which edge of the window the cursor is near"""
        rect = self.rect()
        margin = self.edge_margin
        
        left = pos.x() <= margin
        right = pos.x() >= rect.width() - margin
        top = pos.y() <= margin
        bottom = pos.y() >= rect.height() - margin
        
        if top and left:
            return 'top_left'
        elif top and right:
            return 'top_right'
        elif bottom and left:
            return 'bottom_left'
        elif bottom and right:
            return 'bottom_right'
        elif top:
            return 'top'
        elif bottom:
            return 'bottom'
        elif left:
            return 'left'
        elif right:
            return 'right'
        return None
    
    def update_cursor(self, edge):
        """Update cursor shape based on resize edge"""
        if edge == 'top_left' or edge == 'bottom_right':
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edge == 'top_right' or edge == 'bottom_left':
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edge == 'top' or edge == 'bottom':
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edge == 'left' or edge == 'right':
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
    
    def mousePressEvent(self, event):
        """Handle mouse press for window dragging and resizing"""
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self.get_resize_edge(event.pos())
            if edge:
                # Start resizing
                self.resizing = True
                self.resize_edge = edge
                self.resize_start_pos = event.globalPosition().toPoint()
                self.resize_start_geometry = self.geometry()
                event.accept()
            else:
                # Start dragging
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for window dragging and resizing"""
        if event.buttons() == Qt.MouseButton.LeftButton:
            if self.resizing and self.resize_edge:
                # Handle resizing
                delta = event.globalPosition().toPoint() - self.resize_start_pos
                geo = self.resize_start_geometry
                new_geo = self.geometry()  # Use current geometry as base
                
                # Handle horizontal resizing
                if 'right' in self.resize_edge:
                    new_width = max(self.minimumWidth(), geo.width() + delta.x())
                    new_geo.setWidth(new_width)
                elif 'left' in self.resize_edge:
                    new_width = max(self.minimumWidth(), geo.width() - delta.x())
                    if new_width >= self.minimumWidth():
                        new_geo.setLeft(geo.left() + delta.x())
                        new_geo.setWidth(new_width)
                
                # Handle vertical resizing
                if 'bottom' in self.resize_edge:
                    new_height = max(self.minimumHeight(), geo.height() + delta.y())
                    new_geo.setHeight(new_height)
                elif 'top' in self.resize_edge:
                    new_height = max(self.minimumHeight(), geo.height() - delta.y())
                    if new_height >= self.minimumHeight():
                        new_geo.setTop(geo.top() + delta.y())
                        new_geo.setHeight(new_height)
                
                self.setGeometry(new_geo)
                event.accept()
            elif self.drag_position is not None:
                # Handle dragging
                self.move(event.globalPosition().toPoint() - self.drag_position)
                event.accept()
        else:
            # Update cursor when hovering over edges (no button pressed)
            edge = self.get_resize_edge(event.pos())
            self.update_cursor(edge)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release to end dragging or resizing"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = None
            self.resizing = False
            self.resize_edge = None
            self.resize_start_pos = None
            self.resize_start_geometry = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
    
    def init_ui(self):
        """Initialize the UI - compact layout"""
        # Main container with blue border
        main_container = QFrame(self)
        main_container.setStyleSheet("""
            QFrame {
                border: 5px solid #0078d4;
                background-color: #FFFDE7;
            }
        """)
        main_container.setMouseTracking(True)
        main_container.installEventFilter(self)
        
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(main_container)
        
        layout = QVBoxLayout(main_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header with buttons - compact
        self.header_widget = QFrame()
        self.header_widget.setStyleSheet("""
            QFrame {
                background-color: #0078d4;
                border-bottom: 1px solid #005a9e;
            }
        """)
        self.header_widget.setMouseTracking(True)
        self.header_widget.installEventFilter(self)
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(6, 4, 6, 4)
        header_layout.setSpacing(4)
        
        # Menu button for category management (left side)
        menu_btn = QPushButton("☰ ▼")
        menu_btn.setToolTip("Manage bookmark groups")
        menu_btn.setFixedSize(40, 24)
        menu_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                border: 1px solid white;
                border-radius: 2px;
                font-weight: bold;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
            QPushButton::menu-indicator {
                image: none;
            }
        """)
        # Create and set menu
        category_menu = QMenu(self)
        menu_btn.setMenu(category_menu)
        # Populate menu when button is clicked
        menu_btn.clicked.connect(lambda: self.populate_category_menu(category_menu))
        header_layout.addWidget(menu_btn)
        
        # Add bookmark button (green, longer)
        add_link_btn = QPushButton("+ Add Bookmark")
        add_link_btn.setToolTip("Add a new bookmark")
        add_link_btn.setFixedHeight(24)
        add_link_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 2px;
                font-weight: bold;
                font-size: 9pt;
                padding: 0px 8px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        add_link_btn.clicked.connect(self.add_link)
        header_layout.addWidget(add_link_btn)
        
        # Title in the middle
        header_layout.addStretch()
        title_label = QLabel("<b style='color: white;'>📌 Bookmarks</b>")
        title_label.setStyleSheet("font-size: 10pt;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        # Close button with blue X on gold background
        close_btn = QPushButton("X")
        close_btn.setToolTip("Close bookmarks")
        close_btn.setFixedSize(28, 24)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFD700;
                color: #0078d4;
                border: 2px solid #0078d4;
                border-radius: 3px;
                font-weight: bold;
                font-size: 14pt;
                font-family: Arial;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #FFC700;
                color: #005a9e;
                border-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #FFB700;
            }
        """)
        close_btn.clicked.connect(self.accept)
        header_layout.addWidget(close_btn)
        
        layout.addWidget(self.header_widget)
        
        # Scroll area for categories - horizontal layout
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMouseTracking(True)
        self.scroll.installEventFilter(self)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #FFFDE7;
            }
        """)
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: #FFFDE7;")
        self.content_widget.setMouseTracking(True)
        self.content_widget.installEventFilter(self)
        self.content_layout = QHBoxLayout(self.content_widget)  # HORIZONTAL layout for columns
        self.content_layout.setContentsMargins(2, 2, 2, 2)
        self.content_layout.setSpacing(2)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        self.scroll.setWidget(self.content_widget)
        layout.addWidget(self.scroll)
        
        # Populate categories
        self.refresh_categories()
    
    def load_bookmarks(self):
        """Load bookmarks from JSON file"""
        if self.bookmarks_file.exists():
            try:
                with open(self.bookmarks_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading bookmarks: {e}")
        
        # Default structure
        return {
            'categories': {
                'General': [],
                'Favorites': []
            }
        }
    
    def save_bookmarks(self):
        """Save bookmarks to JSON file"""
        try:
            self.bookmarks_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.bookmarks_file, 'w') as f:
                json.dump(self.bookmarks_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving bookmarks: {e}")
            QMessageBox.warning(self, "Error", f"Failed to save bookmarks: {str(e)}")
    
    def refresh_categories(self):
        """Refresh the category display"""
        # Clear existing widgets
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add category panels
        for category_name, bookmarks in self.bookmarks_data['categories'].items():
            panel = CategoryPanel(category_name, bookmarks)
            panel.remove_bookmark.connect(self.remove_bookmark)
            panel.edit_bookmark.connect(self.edit_bookmark)
            panel.remove_category.connect(self.remove_category_confirm)
            panel.rename_category_signal.connect(self.rename_category)
            panel.move_bookmark.connect(self.move_bookmark_to_category)
            panel.bookmark_opened.connect(self.close_on_bookmark_click)
            panel.folder_opened.connect(self.navigate_to_path.emit)
            self.content_layout.addWidget(panel)
        
        self.content_layout.addStretch()
    
    def close_on_bookmark_click(self):
        """Close dialog when bookmark is clicked"""
        self.accept()
    
    def populate_category_menu(self, menu):
        """Populate the category menu dynamically"""
        menu.clear()
        
        add_action = QAction("➕ Add Category", self)
        add_action.triggered.connect(self.add_category)
        menu.addAction(add_action)
        
        menu.addSeparator()
        
        # List existing categories for removal/rename
        categories = list(self.bookmarks_data['categories'].keys())
        if categories:
            for category_name in categories:
                if category_name not in ['General', 'Favorites']:
                    cat_menu = menu.addMenu(f"📁 {category_name}")
                    
                    rename_action = QAction("✏️ Rename", self)
                    rename_action.triggered.connect(lambda checked, cat=category_name: self.rename_category(cat))
                    cat_menu.addAction(rename_action)
                    
                    remove_action = QAction("🗑️ Remove", self)
                    remove_action.triggered.connect(lambda checked, cat=category_name: self.remove_category_confirm(cat))
                    cat_menu.addAction(remove_action)
    
    def show_category_menu(self):
        """Show category management menu"""
        menu = QMenu(self)
        
        add_action = QAction("➕ Add Category", self)
        add_action.triggered.connect(self.add_category)
        menu.addAction(add_action)
        
        menu.addSeparator()
        
        # List existing categories for removal/rename
        categories = list(self.bookmarks_data['categories'].keys())
        if categories:
            for category_name in categories:
                if category_name not in ['General', 'Favorites']:
                    cat_menu = menu.addMenu(f"📁 {category_name}")
                    
                    rename_action = QAction("✏️ Rename", self)
                    rename_action.triggered.connect(lambda checked, cat=category_name: self.rename_category(cat))
                    cat_menu.addAction(rename_action)
                    
                    remove_action = QAction("🗑️ Remove", self)
                    remove_action.triggered.connect(lambda checked, cat=category_name: self.remove_category_confirm(cat))
                    cat_menu.addAction(remove_action)
        
        menu.exec(QCursor.pos())
    
    def rename_category(self, old_name):
        """Rename a category"""
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Category",
            f"Enter new name for '{old_name}':",
            QLineEdit.EchoMode.Normal,
            old_name
        )
        
        if ok and new_name:
            new_name = new_name.strip()
            if new_name == old_name:
                return
            
            if new_name in self.bookmarks_data['categories']:
                QMessageBox.warning(self, "Duplicate", f"Category '{new_name}' already exists.")
            else:
                # Rename the category
                self.bookmarks_data['categories'][new_name] = self.bookmarks_data['categories'].pop(old_name)
                # Update category field in all bookmarks
                for bookmark in self.bookmarks_data['categories'][new_name]:
                    bookmark['category'] = new_name
                self.save_bookmarks()
                self.refresh_categories()
    
    def add_category(self):
        """Add a new category"""
        category_name, ok = QInputDialog.getText(
            self,
            "Add Category",
            "Enter category name:",
            QLineEdit.EchoMode.Normal
        )
        
        if ok and category_name:
            category_name = category_name.strip()
            if category_name in self.bookmarks_data['categories']:
                QMessageBox.warning(self, "Duplicate", f"Category '{category_name}' already exists.")
            else:
                self.bookmarks_data['categories'][category_name] = []
                self.save_bookmarks()
                self.refresh_categories()
    
    def add_link(self):
        """Add a new link/bookmark using the AddBookmarkDialog"""
        categories = list(self.bookmarks_data['categories'].keys())
        if not categories:
            QMessageBox.warning(self, "No Categories", "Please create a category first.")
            return
        
        # Use the AddBookmarkDialog
        dialog = AddBookmarkDialog(categories, self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            bookmark_data = dialog.get_bookmark_data()
            
            if not bookmark_data['path']:
                QMessageBox.warning(self, "Invalid", "Path/URL cannot be empty.")
                return
            
            # Auto-derive name if not provided
            if not bookmark_data['name']:
                bookmark_data['name'] = self.derive_name_from_path(bookmark_data['path'])
            
            category = bookmark_data['category']
            
            # Add to selected category
            self.bookmarks_data['categories'][category].append(bookmark_data)
            self.save_bookmarks()
            self.refresh_categories()
    
    def derive_name_from_path(self, path):
        """Derive a display name from a path or URL"""
        if path.startswith('http://') or path.startswith('https://'):
            # For URLs, try to extract a meaningful name
            from urllib.parse import urlparse
            parsed = urlparse(path)
            # Use the domain name or last path component
            if parsed.path and parsed.path != '/':
                # Get last path component
                parts = [p for p in parsed.path.split('/') if p]
                if parts:
                    return parts[-1]
            # Use domain
            return parsed.netloc or path
        else:
            # For file paths, use the file/folder name
            return Path(path).name or path
    
    def add_bookmark_to_category(self, name, path, category=None):
        """Add a bookmark programmatically (from context menu)"""
        # Auto-detect type
        if path.startswith('http://') or path.startswith('https://'):
            bookmark_type = 'sharepoint' if 'sharepoint' in path.lower() else 'url'
        elif os.path.isfile(path):
            bookmark_type = 'file'
        elif os.path.isdir(path):
            bookmark_type = 'folder'
        else:
            bookmark_type = 'path'
        
        bookmark_data = {
            'name': name,
            'path': path,
            'type': bookmark_type,
            'category': category or 'General'
        }
        
        # If category specified and doesn't exist, create it
        if category and category not in self.bookmarks_data['categories']:
            self.bookmarks_data['categories'][category] = []
        
        # If no category specified, ask user
        if not category:
            categories = list(self.bookmarks_data['categories'].keys())
            category, ok = QInputDialog.getItem(
                self,
                "Select Category",
                "Choose a category for this bookmark:",
                categories,
                0,
                False
            )
            if not ok:
                return
            bookmark_data['category'] = category
        
        # Add bookmark
        self.bookmarks_data['categories'][category].append(bookmark_data)
        self.save_bookmarks()
        self.refresh_categories()
        
        QMessageBox.information(self, "Success", f"Added '{name}' to '{category}' category.")
    
    def remove_bookmark(self, category, bookmark_data):
        """Remove a bookmark from a category"""
        try:
            self.bookmarks_data['categories'][category].remove(bookmark_data)
            self.save_bookmarks()
            self.refresh_categories()
        except Exception as e:
            logger.error(f"Error removing bookmark: {e}")
    
    def move_bookmark_to_category(self, bookmark_data, target_category, insert_index=-1):
        """Move a bookmark from its current category to a target category at specific position"""
        try:
            source_category = bookmark_data.get('category', 'General')
            
            # Find and remove from source category
            source_index = -1
            if source_category in self.bookmarks_data['categories']:
                # Find the bookmark in the source category
                for i, bookmark in enumerate(self.bookmarks_data['categories'][source_category]):
                    if (bookmark.get('name') == bookmark_data.get('name') and 
                        bookmark.get('path') == bookmark_data.get('path')):
                        # Remove from source
                        self.bookmarks_data['categories'][source_category].pop(i)
                        source_index = i
                        break
            
            # Adjust insert index if moving within same category
            if source_category == target_category and source_index != -1 and insert_index > source_index:
                # If we removed an item before the insertion point, adjust the index
                insert_index -= 1
            
            # Update the category field
            bookmark_data['category'] = target_category
            
            # Add to target category at specific position
            if target_category not in self.bookmarks_data['categories']:
                self.bookmarks_data['categories'][target_category] = []
            
            # Insert at specific index or append at end
            if insert_index >= 0 and insert_index <= len(self.bookmarks_data['categories'][target_category]):
                self.bookmarks_data['categories'][target_category].insert(insert_index, bookmark_data)
            else:
                self.bookmarks_data['categories'][target_category].append(bookmark_data)
            
            # Save and refresh
            self.save_bookmarks()
            self.refresh_categories()
            
            logger.info(f"Moved bookmark '{bookmark_data.get('name')}' from '{source_category}' to '{target_category}' at index {insert_index}")
            
        except Exception as e:
            logger.error(f"Error moving bookmark: {e}")
            QMessageBox.warning(self, "Error", f"Failed to move bookmark: {str(e)}")

    
    def edit_bookmark(self, category, bookmark_data):
        """Edit a bookmark - same layout as Add Bookmark dialog"""
        from PyQt6.QtWidgets import QCheckBox
        
        # Create edit dialog
        edit_dialog = QDialog(self)
        edit_dialog.setWindowTitle("Edit Bookmark")
        edit_dialog.setModal(True)
        edit_dialog.resize(650, 280)
        
        layout = QVBoxLayout(edit_dialog)
        
        # Title
        title_label = QLabel("<h3>Edit Bookmark</h3>")
        layout.addWidget(title_label)
        
        # Name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        name_input = QLineEdit(bookmark_data['name'])
        name_input.setPlaceholderText("Display name for the bookmark")
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)
        
        # Path input
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Path/URL:"))
        path_input = QLineEdit(bookmark_data['path'])
        path_input.setPlaceholderText("File path, folder path, URL, or SharePoint link")
        path_layout.addWidget(path_input)
        layout.addLayout(path_layout)
        
        # Category selection
        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("Category:"))
        category_combo = QComboBox()
        categories = list(self.bookmarks_data['categories'].keys())
        category_combo.addItems(categories)
        # Set current category
        current_index = categories.index(category) if category in categories else 0
        category_combo.setCurrentIndex(current_index)
        category_layout.addWidget(category_combo)
        layout.addLayout(category_layout)
        
        # Open in App checkbox (for SharePoint files)
        open_in_app_checkbox = QCheckBox("Open in App (SharePoint files open in desktop app instead of browser)")
        open_in_app_checkbox.setChecked(bookmark_data.get('open_in_app', True))  # Default to True
        open_in_app_checkbox.setStyleSheet("margin-top: 5px;")
        layout.addWidget(open_in_app_checkbox)
        
        # Type hint
        type_label = QLabel("💡 Tip: This can be a folder path, file path, SharePoint URL, or any web URL")
        type_label.setStyleSheet("color: #0066cc; font-size: 9pt; margin-top: 10px;")
        layout.addWidget(type_label)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(edit_dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(edit_dialog.accept)
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
        
        # Show dialog
        if edit_dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = name_input.text().strip()
            new_path = path_input.text().strip()
            new_category = category_combo.currentText()
            new_open_in_app = open_in_app_checkbox.isChecked()
            
            if not new_name or not new_path:
                QMessageBox.warning(self, "Invalid", "Name and path cannot be empty.")
                return
            
            # Check if category changed - need to move bookmark
            if new_category != category:
                # Remove from old category
                try:
                    self.bookmarks_data['categories'][category].remove(bookmark_data)
                except ValueError:
                    pass
                
                # Update bookmark data
                bookmark_data['name'] = new_name
                bookmark_data['path'] = new_path
                bookmark_data['category'] = new_category
                bookmark_data['open_in_app'] = new_open_in_app
                
                # Re-detect type in case path changed
                if new_path.startswith('http://') or new_path.startswith('https://'):
                    if 'sharepoint' in new_path.lower():
                        bookmark_data['type'] = detect_sharepoint_type(new_path)
                    else:
                        bookmark_data['type'] = 'url'
                elif os.path.isfile(new_path):
                    bookmark_data['type'] = 'file'
                elif os.path.isdir(new_path):
                    bookmark_data['type'] = 'folder'
                else:
                    bookmark_data['type'] = 'path'
                
                # Add to new category
                self.bookmarks_data['categories'][new_category].append(bookmark_data)
            else:
                # Update bookmark data in place
                bookmark_data['name'] = new_name
                bookmark_data['path'] = new_path
                bookmark_data['open_in_app'] = new_open_in_app
                
                # Re-detect type in case path changed
                if new_path.startswith('http://') or new_path.startswith('https://'):
                    if 'sharepoint' in new_path.lower():
                        bookmark_data['type'] = detect_sharepoint_type(new_path)
                    else:
                        bookmark_data['type'] = 'url'
                elif os.path.isfile(new_path):
                    bookmark_data['type'] = 'file'
                elif os.path.isdir(new_path):
                    bookmark_data['type'] = 'folder'
                else:
                    bookmark_data['type'] = 'path'
            
            self.save_bookmarks()
            self.refresh_categories()
    
    def remove_category_confirm(self, category_name):
        """Confirm and remove a category"""
        reply = QMessageBox.question(
            self,
            "Remove Category",
            f"Are you sure you want to remove the '{category_name}' category?\n"
            f"All bookmarks in this category will be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.bookmarks_data['categories'][category_name]
            self.save_bookmarks()
            self.refresh_categories()
