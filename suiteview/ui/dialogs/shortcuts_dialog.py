"""
Bookmarks Panel Dialog
Displays categorized bookmarks to folders, files, SharePoint sites, and URLs
Similar to browser bookmarks bar
"""

import os
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

import logging
logger = logging.getLogger(__name__)


def show_compact_confirm(parent, title, message):
    """Show a compact confirmation dialog near the cursor"""
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QCursor
    
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
    
    dialog.setStyleSheet("""
        QDialog {
            background-color: #FFFFFF;
            border: 1px solid #888888;
            border-radius: 4px;
        }
    """)
    
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(8)
    
    # Message
    label = QLabel(message)
    label.setStyleSheet("color: #333333; font-size: 9pt;")
    label.setWordWrap(True)
    layout.addWidget(label)
    
    # Buttons
    btn_layout = QHBoxLayout()
    btn_layout.setSpacing(6)
    
    no_btn = QPushButton("Cancel")
    no_btn.setFixedHeight(22)
    no_btn.setStyleSheet("""
        QPushButton {
            background-color: #E0E0E0;
            border: 1px solid #AAAAAA;
            border-radius: 3px;
            color: #333333;
            font-size: 8pt;
            padding: 2px 10px;
        }
        QPushButton:hover { background-color: #D0D0D0; }
        QPushButton:pressed { background-color: #C0C0C0; }
    """)
    no_btn.clicked.connect(dialog.reject)
    
    yes_btn = QPushButton("Delete")
    yes_btn.setFixedHeight(22)
    yes_btn.setStyleSheet("""
        QPushButton {
            background-color: #DC3545;
            border: 1px solid #B02A37;
            border-radius: 3px;
            color: white;
            font-size: 8pt;
            font-weight: 600;
            padding: 2px 10px;
        }
        QPushButton:hover { background-color: #BB2D3B; }
        QPushButton:pressed { background-color: #A52834; }
    """)
    yes_btn.clicked.connect(dialog.accept)
    
    btn_layout.addStretch()
    btn_layout.addWidget(no_btn)
    btn_layout.addWidget(yes_btn)
    layout.addLayout(btn_layout)
    
    # Position near cursor
    cursor_pos = QCursor.pos()
    dialog.adjustSize()
    dialog.move(cursor_pos.x() - dialog.width() // 2, cursor_pos.y() - 20)
    
    return dialog.exec() == QDialog.DialogCode.Accepted


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
    
    # Signal to highlight a bookmark bar (bar_id or -1 to clear)
    highlight_bar = None  # Will be set as pyqtSignal
    
    def __init__(self, categories, parent=None):
        super().__init__(parent)
        self.categories = categories
        self.parent_widget = parent  # Store reference to parent for bar highlighting
        self.setWindowTitle("Add Bookmark")
        self.setModal(True)
        self.resize(500, 220)
        
        # Apply compact styling
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QLabel {
                font-size: 9pt;
                padding: 0px;
                margin: 0px;
            }
            QLineEdit {
                padding: 4px 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                font-size: 9pt;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
            QComboBox {
                padding: 4px 6px;
                border: 1px solid #ccc;
                border-radius: 3px;
                font-size: 9pt;
            }
            QComboBox:focus {
                border-color: #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #666;
                margin-right: 5px;
            }
            QCheckBox {
                font-size: 9pt;
                spacing: 4px;
            }
            QPushButton {
                padding: 5px 16px;
                border: 1px solid #c0c0c0;
                border-radius: 3px;
                background-color: #f0f0f0;
                font-size: 9pt;
                color: #333;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-color: #a0a0a0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
            QPushButton:default {
                background-color: #0078d4;
                color: white;
                border-color: #0078d4;
            }
            QPushButton:default:hover {
                background-color: #006cc1;
            }
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 3px;
                font-size: 9pt;
            }
            QListWidget::item {
                padding: 4px 8px;
            }
            QListWidget::item:hover {
                background-color: #e8f0fe;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
                color: white;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        
        # Title
        title_label = QLabel("<b>Add New Bookmark</b>")
        title_label.setStyleSheet("font-size: 11pt; margin-bottom: 4px;")
        layout.addWidget(title_label)
        
        # Name input
        name_layout = QHBoxLayout()
        name_layout.setSpacing(8)
        name_label = QLabel("Name:")
        name_label.setFixedWidth(55)
        name_layout.addWidget(name_label)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Display name for the bookmark")
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # Path/URL input
        path_layout = QHBoxLayout()
        path_layout.setSpacing(8)
        path_label = QLabel("Path/URL:")
        path_label.setFixedWidth(55)
        path_layout.addWidget(path_label)
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("File path, folder path, URL, or SharePoint link")
        path_layout.addWidget(self.path_input)
        layout.addLayout(path_layout)
        
        # Location selection (replaces Category)
        location_layout = QHBoxLayout()
        location_layout.setSpacing(8)
        location_label = QLabel("Location:")
        location_label.setFixedWidth(55)
        location_layout.addWidget(location_label)
        
        # Use QComboBox with custom view for hover highlighting
        self.location_combo = QComboBox()
        self.location_combo.setEditable(True)
        self.location_combo.lineEdit().setPlaceholderText("Select location or type new category")
        
        # Populate locations dynamically
        self._populate_locations()
        
        # Connect to highlight bars on hover - enable mouse tracking for the view
        self.location_combo.view().setMouseTracking(True)
        self.location_combo.view().entered.connect(self._on_location_hover)
        self.location_combo.view().viewport().installEventFilter(self)
        
        location_layout.addWidget(self.location_combo)
        layout.addLayout(location_layout)
        
        # Hint for new category creation
        location_hint = QLabel("💡 Type a new name to create a new category")
        location_hint.setStyleSheet("color: #666; font-size: 8pt; margin-left: 63px;")
        layout.addWidget(location_hint)
        
        # Open in App checkbox (for SharePoint files)
        from PyQt6.QtWidgets import QCheckBox
        self.open_in_app_checkbox = QCheckBox("Open in App (SharePoint files open in desktop app instead of browser)")
        self.open_in_app_checkbox.setChecked(True)
        layout.addWidget(self.open_in_app_checkbox)
        
        # Type hint
        type_label = QLabel("💡 Tip: This can be a folder path, file path, SharePoint URL, or any web URL")
        type_label.setStyleSheet("color: #0066cc; font-size: 8pt;")
        layout.addWidget(type_label)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        button_layout.addWidget(save_btn)
        
        layout.addLayout(button_layout)
    
    def _populate_locations(self):
        """Populate location combo with all bars and categories dynamically"""
        from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
        
        self.location_combo.clear()
        self._bar_ids = []  # Track which items are bookmark bars
        self._location_to_bar_id = {}  # Map location text to bar_id
        
        manager = get_bookmark_manager()
        all_bar_ids = manager.get_all_bar_ids()
        
        # Add bookmark bars first (Bookmark 0, Bookmark 1, etc.)
        for bar_id in sorted(all_bar_ids):
            label = f"📌 Bookmark Bar {bar_id}"
            self.location_combo.addItem(label)
            self._bar_ids.append(self.location_combo.count() - 1)  # Track index
            self._location_to_bar_id[label] = bar_id
        
        # Collect all unique categories from all bars (new format - from items)
        all_categories = set(manager.get_all_category_names())
        
        # Add separator if we have both bars and categories
        if all_bar_ids and all_categories:
            self.location_combo.insertSeparator(self.location_combo.count())
        
        # Add categories in alphabetical order
        for category in sorted(all_categories, key=str.lower):
            self.location_combo.addItem(f"📁 {category}")
    
    def _on_location_hover(self, index):
        """Handle hover over location items to highlight bookmark bars"""
        item_index = index.row()
        
        # Check if this is a bookmark bar item
        if item_index in self._bar_ids:
            bar_id = list(self._location_to_bar_id.values())[self._bar_ids.index(item_index)]
            self._highlight_bookmark_bar(bar_id)
        else:
            # Clear any highlight
            self._highlight_bookmark_bar(-1)
    
    def _highlight_bookmark_bar(self, bar_id: int):
        """Highlight a bookmark bar or clear highlight if bar_id is -1"""
        from suiteview.ui.widgets.bookmark_widgets import BookmarkContainerRegistry
        
        # Clear all highlights first
        for bid, container in BookmarkContainerRegistry.get_all().items():
            if hasattr(container, 'set_highlight'):
                container.set_highlight(False)
        
        # Apply highlight to specified bar
        if bar_id >= 0:
            container = BookmarkContainerRegistry.get(bar_id)
            if container and hasattr(container, 'set_highlight'):
                container.set_highlight(True)
    
    def eventFilter(self, obj, event):
        """Event filter to clear highlight when mouse leaves combo popup"""
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.Leave:
            self._highlight_bookmark_bar(-1)
        return super().eventFilter(obj, event)
    
    def hideEvent(self, event):
        """Clear highlight when dialog is hidden"""
        self._highlight_bookmark_bar(-1)
        super().hideEvent(event)
    
    def closeEvent(self, event):
        """Clear highlight when dialog is closed"""
        self._highlight_bookmark_bar(-1)
        super().closeEvent(event)
    
    def get_bookmark_data(self):
        """Return the bookmark data"""
        location_text = self.location_combo.currentText()
        
        # Determine if it's a bookmark bar or category
        category = None
        target_bar_id = None
        
        if location_text.startswith("📌 Bookmark Bar "):
            # It's a bookmark bar - extract bar ID
            try:
                target_bar_id = int(location_text.replace("📌 Bookmark Bar ", ""))
            except ValueError:
                target_bar_id = 0  # Default to bar 0
            category = "__BAR__"  # Special marker for bar items
        elif location_text.startswith("📁 "):
            # It's an existing category
            category = location_text[2:].strip()  # Remove emoji prefix
        else:
            # It's a new category name (user typed it)
            category = location_text.strip()
        
        return {
            'name': self.name_input.text().strip(),
            'path': self.path_input.text().strip(),
            'category': category,
            'target_bar_id': target_bar_id,  # New field for bar selection
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
