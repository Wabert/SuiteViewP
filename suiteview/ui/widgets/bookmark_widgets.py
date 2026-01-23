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
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QFrame, QVBoxLayout, QHBoxLayout,
    QScrollArea, QMenu, QInputDialog, QMessageBox, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData
from PyQt6.QtGui import QAction, QDrag, QCursor

logger = logging.getLogger(__name__)


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
        margin: 1px 2px;
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
        border: 1px solid #c0c0c0;
        padding: 4px;
    }
    QMenu::item {
        padding: 6px 20px;
        background-color: transparent;
    }
    QMenu::item:selected {
        background-color: #e0e0e0;
    }
    QMenu::separator {
        height: 1px;
        background-color: #d0d0d0;
        margin: 4px 8px;
    }
"""


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
        
        # Set up display
        path = bookmark_data.get('path', '')
        name = bookmark_data.get('name', Path(path).name if path else 'Unknown')
        icon_prefix = self._get_icon_for_path(path)
        
        self.setText(f"{icon_prefix} {name}")
        self.setToolTip(path)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setStyleSheet(BOOKMARK_BUTTON_STYLE)
    
    def _get_icon_for_path(self, path):
        """Get emoji icon based on path type"""
        if not path:
            return '📌'
        
        # Check if it's a URL
        if path.startswith('http://') or path.startswith('https://'):
            if 'sharepoint' in path.lower():
                return '🔗'
            return '🌐'
        
        # Check if path exists and determine type
        try:
            path_obj = Path(path)
            if path_obj.exists():
                return '📁' if path_obj.is_dir() else '📄'
        except:
            pass
        
        return '📌'
    
    def _show_context_menu(self, pos):
        """Show context menu for this bookmark"""
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)
        
        remove_action = menu.addAction("🗑️ Remove")
        
        action = menu.exec(self.mapToGlobal(pos))
        if action == remove_action:
            self._remove_bookmark()
    
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
                 data_manager=None, source_location='bar'):
        """
        Args:
            category_name: name of the category
            category_items: list of bookmark dicts
            parent_widget: parent widget for positioning
            data_manager: object managing the bookmark data
            source_location: 'bar' or 'sidebar'
        """
        super().__init__(parent_widget, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        
        self.category_name = category_name
        self.category_items = category_items
        self.data_manager = data_manager
        self.source_location = source_location
        self.drop_indicator = None
        self.drop_index = -1
        
        self.setAcceptDrops(True)
        self.setStyleSheet(POPUP_STYLE)
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
        """Handle dropping bookmark from another category (bar mode)"""
        if not self.data_manager or not hasattr(self.data_manager, 'bookmarks_data'):
            return
        
        path = bookmark.get('path')
        
        # Add to this category
        if self.category_name not in self.data_manager.bookmarks_data['categories']:
            self.data_manager.bookmarks_data['categories'][self.category_name] = []
        
        # Check for duplicate
        existing = self.data_manager.bookmarks_data['categories'][self.category_name]
        if any(b.get('path') == path for b in existing):
            return
        
        # Insert at position
        if drop_idx >= 0 and drop_idx < len(existing):
            existing.insert(drop_idx, bookmark)
        else:
            existing.append(bookmark)
        
        # Remove from source
        if source_category == '__BAR__':
            bar_items = self.data_manager.bookmarks_data.get('bar_items', [])
            for i, item in enumerate(bar_items):
                if item.get('type') == 'bookmark':
                    if item.get('data', {}).get('path') == path:
                        bar_items.pop(i)
                        break
        elif source_category in self.data_manager.bookmarks_data.get('categories', {}):
            src_list = self.data_manager.bookmarks_data['categories'][source_category]
            for i, b in enumerate(src_list):
                if b.get('path') == path:
                    src_list.pop(i)
                    break
        
        self.data_manager.save_bookmarks()
        self.data_manager.refresh_bookmarks()
    
    def closeEvent(self, event):
        self.popup_closed.emit()
        super().closeEvent(event)


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
                 data_manager=None, source_location='bar', orientation='horizontal'):
        """
        Args:
            category_name: name of the category
            category_items: list of bookmark dicts
            item_index: index in the bar/sidebar for drag reordering
            parent: parent widget
            data_manager: object managing bookmark data
            source_location: 'bar' or 'sidebar'
            orientation: 'horizontal' (top bar) or 'vertical' (sidebar)
        """
        super().__init__(f"🗄 {category_name} ▾", parent)
        
        self.category_name = category_name
        self.category_items = category_items
        self.item_index = item_index
        self.data_manager = data_manager
        self.source_location = source_location
        self.orientation = orientation
        self.drag_start_pos = None
        self.dragging = False
        self.active_popup = None
        self.popup_closed_time = 0
        
        self.setToolTip(f"{len(category_items)} bookmark(s)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty('category_name', category_name)
        self.setAcceptDrops(True)
        
        # Apply appropriate style
        if orientation == 'horizontal':
            self.setStyleSheet(CATEGORY_BUTTON_STYLE)
            self.setMaximumWidth(200)
        else:
            self.setStyleSheet(CATEGORY_BUTTON_STYLE_SIDEBAR)
            self.setFixedHeight(26)
    
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
        
        # Store index for reordering
        mime_data.setText(str(self.item_index))
        
        if self.source_location == 'bar':
            mime_data.setData('application/x-bar-item-index', str(self.item_index).encode())
        
        # Category move data
        category_data = {
            'name': self.category_name,
            'items': self.category_items,
            'source': 'bookmark_bar' if self.source_location == 'bar' else 'quick_links',
            'bar_item_index': self.item_index
        }
        mime_data.setData('application/x-category-move', json.dumps(category_data).encode())
        
        # Also quicklink format for sidebar
        if self.source_location == 'sidebar':
            item_data = {
                'type': 'category',
                'name': self.category_name,
                'items': self.category_items,
                'index': self.item_index,
                'source': 'quick_links'
            }
            mime_data.setData('application/x-quicklink-item', json.dumps(item_data).encode())
        
        drag.setMimeData(mime_data)
        
        logger.info(f"Dragging category: {self.category_name}")
        result = drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        self.dragging = False
    
    def _show_popup(self):
        """Show the category popup"""
        # Close existing popup if any
        if self.active_popup and self.active_popup.isVisible():
            self.active_popup.close()
            self.active_popup = None
            return
        
        popup = CategoryPopup(
            category_name=self.category_name,
            category_items=self.category_items,
            parent_widget=self,
            data_manager=self.data_manager,
            source_location=self.source_location
        )
        
        popup.item_clicked.connect(self._on_popup_item_clicked)
        popup.popup_closed.connect(self._on_popup_closed)
        
        # Position below button
        global_pos = self.mapToGlobal(self.rect().bottomLeft())
        popup.move(global_pos)
        popup.show()
        
        self.active_popup = popup
        self.popup_opened.emit(popup)
    
    def _on_popup_item_clicked(self, path):
        self.item_clicked.emit(path)
    
    def _on_popup_closed(self):
        self.popup_closed_time = time.time()
        self.active_popup = None
        self.popup_closed.emit()
    
    def _show_context_menu(self, pos):
        """Show context menu with Rename and Remove options"""
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)
        
        rename_action = menu.addAction("✏️ Rename")
        menu.addSeparator()
        remove_action = menu.addAction("🗑️ Remove")
        
        action = menu.exec(self.mapToGlobal(pos))
        
        if action == rename_action:
            self._rename_category()
        elif action == remove_action:
            self._remove_category()
    
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
                    QMessageBox.warning(self, "Duplicate", f"Category '{new_name}' already exists.")
                    return
                
                # Rename in categories
                categories = self.data_manager.bookmarks_data.get('categories', {})
                if self.category_name in categories:
                    categories[new_name] = categories.pop(self.category_name)
                
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
                        QMessageBox.warning(self, "Duplicate", f"Category '{new_name}' already exists.")
                        return
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
        
        reply = QMessageBox.question(
            self,
            "Remove Category",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
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
            
            # Remove from bar_items
            bar_items = self.data_manager.bookmarks_data.get('bar_items', [])
            for i, item in enumerate(bar_items):
                if item.get('type') == 'category' and item.get('name') == self.category_name:
                    bar_items.pop(i)
                    break
            
            self.data_manager.save_bookmarks()
            self.data_manager.refresh_bookmarks()
        else:
            # Sidebar
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
        if source == '__BAR__':
            bar_items = self.data_manager.bookmarks_data.get('bar_items', [])
            for i, item in enumerate(bar_items):
                if item.get('type') == 'bookmark':
                    if item.get('data', {}).get('path') == path:
                        bar_items.pop(i)
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
        
        # Remove from source category if applicable
        if source and source != '__NEW__' and source != '__QUICK_LINKS__' and source != self.category_name:
            if source in categories:
                src_list = categories[source]
                for i, b in enumerate(src_list):
                    if b.get('path') == path:
                        src_list.pop(i)
                        break
        
        self.data_manager.save_quick_links()
        self.data_manager.refresh_quick_links_list()
