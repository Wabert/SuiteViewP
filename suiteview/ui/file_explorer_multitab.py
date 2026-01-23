
"""
File Explorer - Multi-Tab Edition
Wraps FileExplorerCore with tab support, breadcrumbs, and enhanced features
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                              QPushButton, QLabel, QFrame, QMenu, QLineEdit, QTreeView, QStyle, QTabBar, QToolButton,
                              QListWidget, QListWidgetItem, QSplitter, QAbstractItemView, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QSize
from PyQt6.QtGui import QAction, QCursor, QMouseEvent

# Import the base FileExplorerCore
from suiteview.ui.file_explorer_core import FileExplorerCore, DropTreeView

# Import unified bookmark widgets for sidebar categories
from suiteview.ui.widgets.bookmark_widgets import (
    CategoryButton, CategoryPopup, CategoryBookmarkButton,
    CATEGORY_BUTTON_STYLE_SIDEBAR, CONTEXT_MENU_STYLE
)

import logging
logger = logging.getLogger(__name__)


class DropListWidget(QListWidget):
    """QListWidget that accepts bookmark and file drops, supports dragging items out, and internal reordering"""
    
    bookmark_dropped = pyqtSignal(dict)  # Signal when a bookmark is dropped
    file_dropped = pyqtSignal(str)  # Signal when a file/folder is dropped
    items_reordered = pyqtSignal(list)  # Signal with new order of paths
    category_dropped = pyqtSignal(dict)  # Signal when a category is dropped (for moving categories from bookmark bar)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.drag_start_pos = None
        self.dragging_item_row = -1
        self.drop_indicator_row = -1
    
    def mousePressEvent(self, event):
        """Track drag start position"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            item = self.itemAt(event.pos())
            if item:
                self.dragging_item_row = self.row(item)
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Start drag if moved far enough"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self.drag_start_pos is None:
            return
        
        distance = (event.pos() - self.drag_start_pos).manhattanLength()
        if distance < 10:
            return
        
        item = self.currentItem()
        if not item:
            return
        
        # Start drag with bookmark data format
        from PyQt6.QtGui import QDrag
        from PyQt6.QtCore import QMimeData
        import json
        
        path = item.data(Qt.ItemDataRole.UserRole)
        name = item.text()
        row = self.row(item)
        
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Create bookmark-compatible data
        bookmark_data = {
            'bookmark': {
                'name': name,
                'path': path,
                'type': 'folder' if Path(path).is_dir() else 'file'
            },
            'source_category': '__QUICK_LINKS__',
            'source_row': row  # Include row for internal reordering
        }
        mime_data.setData('application/x-bookmark-move', json.dumps(bookmark_data).encode())
        mime_data.setData('application/x-quicklink-reorder', str(row).encode())
        mime_data.setText(name)
        
        # Also add as URL for compatibility
        from PyQt6.QtCore import QUrl
        mime_data.setUrls([QUrl.fromLocalFile(path)])
        
        drag.setMimeData(mime_data)
        result = drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)
        self.drag_start_pos = None
        self.dragging_item_row = -1
    
    def dragEnterEvent(self, event):
        """Accept bookmark, file, category, and internal reorder drops"""
        mime = event.mimeData()
        if (mime.hasFormat('application/x-quicklink-reorder') or 
            mime.hasFormat('application/x-bookmark-move') or 
            mime.hasFormat('application/x-category-move') or 
            mime.hasUrls()):
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        """Accept drops and show drop indicator"""
        mime = event.mimeData()
        if (mime.hasFormat('application/x-quicklink-reorder') or 
            mime.hasFormat('application/x-bookmark-move') or 
            mime.hasFormat('application/x-category-move') or 
            mime.hasUrls()):
            event.acceptProposedAction()
            # Update visual drop indicator
            self.drop_indicator_row = self._get_drop_row(event.position().toPoint())
            self.viewport().update()
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        """Clear drop indicator"""
        self.drop_indicator_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)
    
    def _get_drop_row(self, pos):
        """Get the row index where item would be dropped"""
        item = self.itemAt(pos)
        if item:
            item_rect = self.visualItemRect(item)
            row = self.row(item)
            # If in bottom half, drop after this item
            if pos.y() > item_rect.center().y():
                return row + 1
            return row
        # If no item at position, drop at end
        return self.count()
    
    def paintEvent(self, event):
        """Paint with drop indicator line"""
        super().paintEvent(event)
        
        # Draw drop indicator
        if self.drop_indicator_row >= 0:
            from PyQt6.QtGui import QPainter, QPen, QColor
            painter = QPainter(self.viewport())
            pen = QPen(QColor("#1a73e8"), 2)
            painter.setPen(pen)
            
            if self.drop_indicator_row < self.count():
                item = self.item(self.drop_indicator_row)
                rect = self.visualItemRect(item)
                y = rect.top()
            else:
                # Drop at end
                if self.count() > 0:
                    item = self.item(self.count() - 1)
                    rect = self.visualItemRect(item)
                    y = rect.bottom()
                else:
                    y = 5
            
            painter.drawLine(5, y, self.viewport().width() - 5, y)
            painter.end()
    
    def dropEvent(self, event):
        """Handle bookmark, file, or internal reorder drop"""
        mime = event.mimeData()
        drop_row = self._get_drop_row(event.position().toPoint())
        self.drop_indicator_row = -1
        self.viewport().update()
        
        # Check for internal reorder first
        if mime.hasFormat('application/x-quicklink-reorder'):
            try:
                source_row = int(mime.data('application/x-quicklink-reorder').data().decode())
                if source_row != drop_row and source_row != drop_row - 1:
                    # Emit signal with new order
                    paths = []
                    for i in range(self.count()):
                        item = self.item(i)
                        paths.append(item.data(Qt.ItemDataRole.UserRole))
                    
                    # Reorder the paths
                    path_to_move = paths.pop(source_row)
                    if drop_row > source_row:
                        drop_row -= 1
                    paths.insert(drop_row, path_to_move)
                    
                    self.items_reordered.emit(paths)
                event.acceptProposedAction()
                return
            except Exception as e:
                logger.error(f"Error handling reorder: {e}")
        
        # Check for category drop (from bookmark bar or another Quick Links category)
        if mime.hasFormat('application/x-category-move'):
            try:
                import json
                category_data = json.loads(mime.data('application/x-category-move').data().decode())
                self.category_dropped.emit(category_data)
                event.acceptProposedAction()
                return
            except Exception as e:
                logger.error(f"Error handling category drop: {e}")
        
        # Check for bookmark drop
        if mime.hasFormat('application/x-bookmark-move'):
            try:
                import json
                drag_data = json.loads(mime.data('application/x-bookmark-move').data().decode())
                # Skip if it's from our own list (already handled above)
                if drag_data.get('source_category') == '__QUICK_LINKS__':
                    event.acceptProposedAction()
                    return
                bookmark = drag_data.get('bookmark', {})
                if bookmark:
                    self.bookmark_dropped.emit(bookmark)
                event.acceptProposedAction()
                return
            except Exception as e:
                logger.error(f"Error handling bookmark drop: {e}")
        
        # Check for file/URL drop
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    self.file_dropped.emit(path)
            event.acceptProposedAction()
            return
        
        event.ignore()


class DropScrollArea(QWidget):
    """Container widget that accepts drops anywhere with position-aware drop handling"""
    
    item_dropped = pyqtSignal(dict, int)  # Emits (item_data, drop_index)
    bookmark_dropped = pyqtSignal(dict)   # Emits bookmark data when bookmark dropped
    file_dropped = pyqtSignal(object)     # Emits path or dict when file dropped
    category_dropped = pyqtSignal(dict)   # Emits category data when category dropped
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.drop_indicator = None
        self.drop_index = -1
        self.items_layout = None  # Will be set by parent
    
    def set_items_layout(self, layout):
        """Set the layout containing the draggable items"""
        self.items_layout = layout
    
    def _get_drop_index(self, pos):
        """Determine which index the item should be dropped at based on position"""
        if not self.items_layout:
            return 0
        
        # Go through all widgets in the layout
        for i in range(self.items_layout.count()):
            item = self.items_layout.itemAt(i)
            widget = item.widget()
            if widget and widget.isVisible():
                widget_rect = widget.geometry()
                # If mouse is above the center of this widget, insert before it
                if pos.y() < widget_rect.center().y():
                    return i
        
        # If we're past all widgets, insert at the end
        return self.items_layout.count()
    
    def _show_drop_indicator(self, pos):
        """Show a visual indicator where the item will be dropped"""
        if not self.drop_indicator:
            self.drop_indicator = QFrame(self)
            self.drop_indicator.setStyleSheet("background-color: #1a73e8;")
            self.drop_indicator.setFixedHeight(2)
        
        self.drop_index = self._get_drop_index(pos)
        
        # Position the indicator
        y_pos = 0
        if self.items_layout:
            if self.drop_index < self.items_layout.count():
                item = self.items_layout.itemAt(self.drop_index)
                if item and item.widget():
                    y_pos = item.widget().geometry().top()
            elif self.items_layout.count() > 0:
                # After the last widget
                last_item = self.items_layout.itemAt(self.items_layout.count() - 1)
                if last_item and last_item.widget():
                    y_pos = last_item.widget().geometry().bottom() + 2
        
        self.drop_indicator.setGeometry(4, y_pos, self.width() - 8, 2)
        self.drop_indicator.show()
        self.drop_indicator.raise_()
    
    def _hide_drop_indicator(self):
        """Hide the drop indicator"""
        if self.drop_indicator:
            self.drop_indicator.hide()
        self.drop_index = -1
    
    def dragEnterEvent(self, event):
        """Accept bookmark, file, and category drops"""
        mime = event.mimeData()
        if (mime.hasFormat('application/x-bookmark-move') or 
            mime.hasFormat('application/x-category-move') or 
            mime.hasFormat('application/x-quicklink-item') or
            mime.hasUrls()):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        """Continue accepting drops and update indicator"""
        mime = event.mimeData()
        if (mime.hasFormat('application/x-bookmark-move') or 
            mime.hasFormat('application/x-category-move') or 
            mime.hasFormat('application/x-quicklink-item') or
            mime.hasUrls()):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        """Hide indicator when drag leaves"""
        self._hide_drop_indicator()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        """Handle drops with position awareness"""
        import json
        mime = event.mimeData()
        drop_idx = self.drop_index if self.drop_index >= 0 else self._get_drop_index(event.position().toPoint())
        self._hide_drop_indicator()
        
        # Check for internal quicklink reorder
        if mime.hasFormat('application/x-quicklink-item'):
            try:
                item_data = json.loads(mime.data('application/x-quicklink-item').data().decode())
                item_data['_drop_index'] = drop_idx
                self.item_dropped.emit(item_data, drop_idx)
                event.acceptProposedAction()
                return
            except Exception as e:
                logger.error(f"Error handling quicklink reorder: {e}")
        
        # Check for category drop (from bookmark bar or elsewhere)
        if mime.hasFormat('application/x-category-move'):
            try:
                category_data = json.loads(mime.data('application/x-category-move').data().decode())
                category_data['_drop_index'] = drop_idx
                # Emit legacy signal for category drops from external sources
                self.category_dropped.emit(category_data)
                event.acceptProposedAction()
                return
            except Exception as e:
                logger.error(f"Error handling category drop: {e}")
        
        # Check for bookmark drop (from bookmark bar)
        if mime.hasFormat('application/x-bookmark-move'):
            try:
                drag_data = json.loads(mime.data('application/x-bookmark-move').data().decode())
                bookmark = drag_data.get('bookmark', {})
                if bookmark:
                    bookmark['_drop_index'] = drop_idx
                    bookmark['_source_category'] = drag_data.get('source_category', '')
                    # Emit legacy signal for bookmark drops from external sources
                    self.bookmark_dropped.emit(bookmark)
                event.acceptProposedAction()
                return
            except Exception as e:
                logger.error(f"Error handling bookmark drop: {e}")
        
        # Check for file/URL drop
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    # Emit legacy file drop signal
                    self.file_dropped.emit({'path': path, '_drop_index': drop_idx})
            event.acceptProposedAction()
            return
        
        event.ignore()


# =============================================================================
# DEPRECATED: The following classes are no longer used for sidebar categories.
# They have been replaced by unified classes from bookmark_widgets.py:
# - QuickLinkCategoryWidget -> CategoryButton (with source_location='sidebar')
# - QuickLinkCategoryPopup -> CategoryPopup (with source_location='sidebar')
# - QuickLinkCategoryBookmarkButton -> CategoryBookmarkButton (with source_location='sidebar')
# Keeping for reference. QuickLinkBookmarkButton is still used for standalone bookmarks.
# =============================================================================

class QuickLinkCategoryBookmarkButton(QPushButton):
    """DEPRECATED: Use CategoryBookmarkButton from bookmark_widgets.py instead.
    Draggable bookmark button for use inside Quick Links category popups"""
    
    clicked_path = pyqtSignal(str)
    
    def __init__(self, bookmark_data, source_category, parent=None, popup=None, icon_provider=None):
        super().__init__(parent)
        
        self.bookmark_data = bookmark_data
        self.source_category = source_category
        self.parent_popup = popup
        self.icon_provider = icon_provider
        self.drag_start_pos = None
        
        path = bookmark_data.get('path', '')
        name = bookmark_data.get('name', Path(path).name if path else 'Unknown')
        bookmark_type = bookmark_data.get('type', '')
        
        # Determine icon based on type
        icon_prefix = self._get_icon_for_type(bookmark_type, path)
        
        self.setText(f"{icon_prefix} {name}")
        self.setToolTip(path)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
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
        """)
    
    def _get_icon_for_type(self, bookmark_type, path):
        """Get emoji icon for bookmark type"""
        # Check if it's a URL
        if path.startswith('http://') or path.startswith('https://'):
            if 'sharepoint' in path.lower():
                return '🔗'
            return '🌐'
        
        # Check explicit type
        icons = {
            'folder': '📁',
            'file': '📄',
            'url': '🌐',
            'sharepoint': '🔗',
            'path': '📂'
        }
        if bookmark_type in icons:
            return icons[bookmark_type]
        
        # Fallback: check if path exists
        try:
            path_obj = Path(path)
            if path_obj.exists():
                return '📁' if path_obj.is_dir() else '📄'
        except:
            pass
        
        return '📌'
    
    def _show_context_menu(self, pos):
        """Show context menu for this bookmark item"""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        
        menu = QMenu(self)
        
        remove_action = QAction("🗑️ Remove", self)
        remove_action.triggered.connect(self._remove_bookmark)
        menu.addAction(remove_action)
        
        menu.exec(self.mapToGlobal(pos))
    
    def _remove_bookmark(self):
        """Remove this bookmark from its category in Quick Links"""
        try:
            # Find the file explorer to access Quick Links data
            parent = self.parent()
            while parent and not hasattr(parent, 'custom_quick_links'):
                parent = parent.parent()
            
            if parent and hasattr(parent, 'custom_quick_links'):
                categories = parent.custom_quick_links.get('categories', {})
                if self.source_category in categories:
                    category_items = categories[self.source_category]
                    # Find and remove the bookmark
                    for i, item in enumerate(category_items):
                        if item.get('path') == self.bookmark_data.get('path'):
                            category_items.pop(i)
                            break
                    parent.save_quick_links()
                    # Close popup and refresh
                    if self.parent_popup:
                        self.parent_popup.close()
                    parent.refresh_quick_links_list()
        except Exception as e:
            logger.error(f"Error removing bookmark from Quick Links category: {e}")
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_start_pos:
            distance = (event.pos() - self.drag_start_pos).manhattanLength()
            if distance < 10:
                # Emit click
                self.clicked_path.emit(self.bookmark_data.get('path', ''))
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
        from PyQt6.QtGui import QDrag
        from PyQt6.QtCore import QMimeData
        import json
        
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Use bookmark-move format for dropping on bookmark bar or into categories
        drag_data = {
            'bookmark': self.bookmark_data,
            'source_category': self.source_category,
            'source': 'quick_links_category'  # Mark as coming from Quick Links category
        }
        mime_data.setData('application/x-bookmark-move', json.dumps(drag_data).encode())
        
        # Also include quicklink-item format for dropping back on Quick Links sidebar
        item_data = {
            'type': 'bookmark',
            'name': self.bookmark_data.get('name', ''),
            'path': self.bookmark_data.get('path', ''),
            'source_category': self.source_category,
            'source': 'quick_links_category'
        }
        mime_data.setData('application/x-quicklink-item', json.dumps(item_data).encode())
        
        mime_data.setText(f"Move: {self.bookmark_data.get('name', 'bookmark')}")
        
        drag.setMimeData(mime_data)
        
        logger.info(f"Dragging bookmark '{self.bookmark_data.get('name')}' from Quick Links category '{self.source_category}'")
        result = drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        
        # Close parent popup if drag was successful
        if result == Qt.DropAction.MoveAction and self.parent_popup:
            self.parent_popup.close()


class QuickLinkBookmarkButton(QPushButton):
    """Draggable bookmark button for Quick Links sidebar"""
    
    clicked_path = pyqtSignal(str)
    double_clicked_path = pyqtSignal(str)
    
    def __init__(self, name, path, icon=None, item_index=0, parent=None):
        super().__init__(parent)
        self.bookmark_name = name
        self.bookmark_path = path
        self.item_index = item_index
        self.drag_start_pos = None
        
        # Set up the button
        self.setText(f"  {name}")
        self.setToolTip(path)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon:
            self.setIcon(icon)
        
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 3px;
                padding: 2px 4px;
                text-align: left;
                font-size: 9pt;
                font-weight: normal;
                color: #202124;
            }
            QPushButton:hover {
                background-color: #C8DCF0;
            }
            QPushButton:pressed {
                background-color: #B0C8E8;
            }
            QToolTip {
                background-color: #FFFFDD;
                color: #333333;
                border: 1px solid #888888;
                padding: 4px;
                font-size: 9pt;
            }
        """)
        self.setFixedHeight(24)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_start_pos:
            # Only emit click if we didn't drag
            distance = (event.pos() - self.drag_start_pos).manhattanLength()
            if distance < 10:
                self.clicked_path.emit(self.bookmark_path)
        self.drag_start_pos = None
        super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked_path.emit(self.bookmark_path)
        super().mouseDoubleClickEvent(event)
    
    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self.drag_start_pos is None:
            return
        
        distance = (event.pos() - self.drag_start_pos).manhattanLength()
        if distance < 10:
            return
        
        # Start drag
        from PyQt6.QtGui import QDrag
        from PyQt6.QtCore import QMimeData
        import json
        
        drag = QDrag(self)
        mime_data = QMimeData()
        
        item_data = {
            'type': 'bookmark',
            'name': self.bookmark_name,
            'path': self.bookmark_path,
            'index': self.item_index,
            'source': 'quick_links'
        }
        mime_data.setData('application/x-quicklink-item', json.dumps(item_data).encode())
        
        # Also include bookmark-move format for dropping on bookmark bar
        bookmark_data = {
            'bookmark': {
                'name': self.bookmark_name,
                'path': self.bookmark_path,
                'type': 'folder' if Path(self.bookmark_path).is_dir() else 'file'
            },
            'source_category': '__QUICK_LINKS__'
        }
        mime_data.setData('application/x-bookmark-move', json.dumps(bookmark_data).encode())
        
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.MoveAction)
        self.drag_start_pos = None


class QuickLinkCategoryPopup(QFrame):
    """DEPRECATED: Use CategoryPopup from bookmark_widgets.py instead.
    Popup window for Quick Links category items - matches top bar CategoryPopup behavior with reordering support"""
    
    item_clicked = pyqtSignal(str)
    item_double_clicked = pyqtSignal(str)
    items_reordered = pyqtSignal(str, list)  # category_name, new_items_list
    
    def __init__(self, category_name, category_items, parent_widget=None, icon_provider=None, file_explorer=None):
        super().__init__(parent_widget, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        from PyQt6.QtWidgets import QVBoxLayout, QListWidget, QListWidgetItem, QScrollArea
        
        self.category_name = category_name
        self.category_items = category_items
        self.icon_provider = icon_provider
        self.parent_widget = parent_widget
        self.file_explorer = file_explorer
        self.drop_indicator = None
        self.drop_index = -1
        
        # Enable drops for reordering
        self.setAcceptDrops(True)
        
        self.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #A080C0;
                border-radius: 4px;
            }
        """)
        
        self.setMinimumWidth(200)
        self.setMaximumWidth(350)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        
        # Scroll area for items
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)
        
        # Container for items
        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Add items as draggable buttons (supports drag to move between categories/quick links)
        for item_data in self.category_items:
            btn = QuickLinkCategoryBookmarkButton(
                bookmark_data=item_data,
                source_category=category_name,
                parent=container,
                popup=self,
                icon_provider=icon_provider
            )
            btn.clicked_path.connect(self._on_item_clicked)
            container_layout.addWidget(btn)
        
        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)
        
        # Store references for reordering
        self.container = container
        self.container_layout = container_layout
        self.scroll = scroll
        
        # Create drop indicator
        self.drop_indicator = QFrame(self)
        self.drop_indicator.setStyleSheet("background-color: #A080C0;")
        self.drop_indicator.setFixedHeight(2)
        self.drop_indicator.hide()
        
        # Calculate proper size
        item_count = len(self.category_items)
        item_height = 28  # Approximate height per item
        total_height = item_count * item_height + 8  # +8 for margins
        max_height = 400
        
        # Set size - width will auto-adjust, height limited
        self.setFixedHeight(min(total_height, max_height))
    
    def _on_item_clicked(self, path):
        if path:
            self.item_clicked.emit(path)
            self.close()
    
    def _get_drop_index(self, pos):
        """Get the index where an item should be dropped based on position"""
        # Map position to container coordinates
        container_pos = self.container.mapFrom(self, pos)
        
        for i in range(self.container_layout.count() - 1):  # -1 to skip stretch
            widget = self.container_layout.itemAt(i).widget()
            if widget:
                widget_geo = widget.geometry()
                if container_pos.y() < widget_geo.center().y():
                    return i
        return len(self.category_items)
    
    def _show_drop_indicator(self, pos):
        """Show drop indicator at the appropriate position"""
        drop_idx = self._get_drop_index(pos)
        self.drop_index = drop_idx
        
        # Position the indicator
        y_pos = 2  # Start position
        if drop_idx < self.container_layout.count() - 1:
            widget = self.container_layout.itemAt(drop_idx).widget()
            if widget:
                # Map widget position to popup coordinates
                widget_pos = widget.mapTo(self, widget.rect().topLeft())
                y_pos = widget_pos.y()
        else:
            # After last item
            if self.container_layout.count() > 1:
                last_widget = self.container_layout.itemAt(self.container_layout.count() - 2).widget()
                if last_widget:
                    widget_pos = last_widget.mapTo(self, last_widget.rect().bottomLeft())
                    y_pos = widget_pos.y() + 2
        
        self.drop_indicator.setGeometry(4, y_pos, self.width() - 8, 2)
        self.drop_indicator.show()
        self.drop_indicator.raise_()
    
    def _hide_drop_indicator(self):
        """Hide the drop indicator"""
        if self.drop_indicator:
            self.drop_indicator.hide()
        self.drop_index = -1
    
    def dragEnterEvent(self, event):
        """Accept bookmark drops for reordering"""
        if event.mimeData().hasFormat('application/x-bookmark-move'):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        """Update drop indicator position"""
        if event.mimeData().hasFormat('application/x-bookmark-move'):
            event.acceptProposedAction()
            self._show_drop_indicator(event.position().toPoint())
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        """Hide indicator when drag leaves"""
        self._hide_drop_indicator()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        """Handle bookmark drop for reordering within category or moving from elsewhere"""
        import json
        self._hide_drop_indicator()
        
        if event.mimeData().hasFormat('application/x-bookmark-move'):
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
                        # Remove from old position
                        moved_item = self.category_items.pop(old_index)
                        # Adjust drop index if needed
                        if old_index < drop_idx:
                            drop_idx -= 1
                        # Insert at new position
                        self.category_items.insert(drop_idx, moved_item)
                        
                        # Update the actual data and refresh
                        if self.file_explorer:
                            self.file_explorer.custom_quick_links['categories'][self.category_name] = self.category_items
                            self.file_explorer.save_quick_links()
                        
                        logger.info(f"Reordered item in category '{self.category_name}' from {old_index} to {drop_idx}")
                        self.close()
                        if self.file_explorer:
                            self.file_explorer.refresh_quick_links_list()
                else:
                    # Moving from another category or sidebar - delegate to parent handler
                    bookmark['_source_category'] = source_category
                    bookmark['source_category'] = source_category
                    if self.file_explorer:
                        self.file_explorer._on_bookmark_dropped_to_category(self.category_name, bookmark)
                    self.close()
                
                event.acceptProposedAction()
            except Exception as e:
                logger.error(f"Error handling drop in category popup: {e}")
                import traceback
                traceback.print_exc()
                event.ignore()
        else:
            event.ignore()
    
    def closeEvent(self, event):
        """Notify parent when popup closes"""
        if self.parent_widget and hasattr(self.parent_widget, 'on_popup_closed'):
            self.parent_widget.on_popup_closed(self)
        super().closeEvent(event)


class QuickLinkCategoryWidget(QWidget):
    """DEPRECATED: Use CategoryButton from bookmark_widgets.py instead.
    Compact category button for Quick Links panel - shows popup on click with toggle support"""
    
    category_moved = pyqtSignal(str, dict)  # Emits (category_name, category_data) when dragged out
    item_clicked = pyqtSignal(str)  # Emits path when item is clicked
    item_double_clicked = pyqtSignal(str)  # Emits path when item is double-clicked
    bookmark_dropped = pyqtSignal(str, dict)  # Emits (category_name, bookmark_data) when bookmark dropped
    
    def __init__(self, category_name, category_items, item_index=0, parent=None, icon_provider=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QVBoxLayout
        import time
        
        self.category_name = category_name
        self.category_items = category_items
        self.item_index = item_index
        self.icon_provider = icon_provider
        self.drag_start_pos = None
        self.dragging = False
        self.active_popup = None
        self.popup_closed_time = 0  # Track when popup was closed to prevent immediate reopen
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Category header button (compact, shows popup on click)
        self.header = QPushButton(f"🗄 {category_name} ▾")
        self.header.setToolTip(f"{len(category_items)} bookmark(s)")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet("""
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #E8D4F8, stop:1 #C9A8E8);
                border: 1px solid #A080C0;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
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
        """)
        self.header.setAcceptDrops(True)
        self.header.setFixedHeight(26)
        layout.addWidget(self.header)
        
        # Override mouse events for drag support
        self.header.mousePressEvent = self._header_mouse_press
        self.header.mouseMoveEvent = self._header_mouse_move
        self.header.mouseReleaseEvent = self._header_mouse_release
        
        # Enable drop on header
        self.header.dragEnterEvent = self._header_drag_enter
        self.header.dropEvent = self._header_drop
        
        # Set fixed height for the widget (just the button)
        self.setFixedHeight(28)
    
    def toggle_popup(self):
        """Toggle the category popup - like the top bar behavior"""
        import time
        
        # Check if popup was just closed (prevent immediate reopen on same click)
        if time.time() - self.popup_closed_time < 0.3:
            return
        
        # If popup is currently open, close it
        if self.active_popup and self.active_popup.isVisible():
            self.active_popup.close()
            self.active_popup = None
            return
        
        # Otherwise, show the popup
        self.show_popup()
    
    def show_popup(self):
        """Show the category items popup"""
        # Close existing popup if any
        if self.active_popup:
            self.active_popup.close()
            self.active_popup = None
        
        if not self.category_items:
            return
        
        # Create and show popup (icon_provider is typically the file_explorer)
        popup = QuickLinkCategoryPopup(
            self.category_name, 
            self.category_items, 
            self,
            self.icon_provider,
            file_explorer=self.icon_provider  # Pass file_explorer for reordering support
        )
        popup.item_clicked.connect(self.item_clicked.emit)
        popup.item_double_clicked.connect(self.item_double_clicked.emit)
        
        # Position popup below the button, aligned to left edge
        button_pos = self.header.mapToGlobal(self.header.rect().bottomLeft())
        popup.move(button_pos.x(), button_pos.y() + 2)
        
        self.active_popup = popup
        popup.show()
    
    def on_popup_closed(self, popup):
        """Called when popup closes - track time to prevent immediate reopen"""
        import time
        self.popup_closed_time = time.time()
        if self.active_popup == popup:
            self.active_popup = None
    
    def _header_mouse_press(self, event):
        """Handle mouse press on header - start drag tracking"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.dragging = False
    
    def _header_mouse_release(self, event):
        """Handle mouse release - toggle popup if not dragging"""
        if event.button() == Qt.MouseButton.LeftButton:
            was_click = not self.dragging and self.drag_start_pos is not None
            self.drag_start_pos = None
            self.dragging = False
            if was_click:
                self.toggle_popup()
    
    def _header_mouse_move(self, event):
        """Handle mouse move - initiate drag if threshold exceeded"""
        from PyQt6.QtGui import QDrag
        from PyQt6.QtCore import QMimeData
        import json
        
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        
        if self.drag_start_pos is None:
            return
        
        # Check if we've moved far enough to start a drag
        distance = (event.pos() - self.drag_start_pos).manhattanLength()
        if distance < 10:
            return
        
        self.dragging = True
        
        # Start drag operation
        drag = QDrag(self)
        mime_data = QMimeData()
        
        # Store category data for move operation
        category_data = {
            'name': self.category_name,
            'items': self.category_items,
            'source': 'quick_links'
        }
        mime_data.setData('application/x-category-move', json.dumps(category_data).encode())
        mime_data.setText(self.category_name)
        
        # Also include quicklink-item format for internal reordering
        quicklink_data = {
            'type': 'category',
            'name': self.category_name,
            'items': self.category_items,
            'index': self.item_index,
            'source': 'quick_links'
        }
        mime_data.setData('application/x-quicklink-item', json.dumps(quicklink_data).encode())
        
        drag.setMimeData(mime_data)
        
        # Execute drag
        result = drag.exec(Qt.DropAction.MoveAction)
        
        self.drag_start_pos = None
        self.dragging = False
    
    def _header_drag_enter(self, event):
        """Accept bookmark drops on category header"""
        mime = event.mimeData()
        if mime.hasFormat('application/x-bookmark-move') or mime.hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def _header_drop(self, event):
        """Handle bookmark drop on category header"""
        import json
        mime = event.mimeData()
        
        if mime.hasFormat('application/x-bookmark-move'):
            try:
                drag_data = json.loads(mime.data('application/x-bookmark-move').data().decode())
                bookmark = drag_data.get('bookmark', {})
                source_category = drag_data.get('source_category', '')
                if bookmark:
                    # Include source_category in bookmark for proper move handling
                    bookmark['_source_category'] = source_category
                    bookmark['source_category'] = source_category
                    self.bookmark_dropped.emit(self.category_name, bookmark)
                event.acceptProposedAction()
                return
            except Exception as e:
                logger.error(f"Error handling bookmark drop on category: {e}")
        
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    path_obj = Path(path)
                    bookmark = {
                        'name': path_obj.name,
                        'path': path,
                        'type': 'folder' if path_obj.is_dir() else 'file'
                    }
                    self.bookmark_dropped.emit(self.category_name, bookmark)
            event.acceptProposedAction()
            return
        
        event.ignore()


class NavigableTreeView(DropTreeView):
    """Custom QTreeView that emits signals for back/forward mouse buttons and supports file drops"""
    
    back_button_clicked = pyqtSignal()
    forward_button_clicked = pyqtSignal()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Override to catch back/forward mouse buttons"""
        button = event.button()
        
        # Get the item being clicked
        index = self.indexAt(event.pos())
        if index.isValid():
            # Get the name from the model (column 0 is the Name column)
            item_name = self.model().data(index.sibling(index.row(), 0), Qt.ItemDataRole.DisplayRole)
            print(f"NavigableTreeView.mousePressEvent: {button} - Clicked: {item_name}")
        else:
            print(f"NavigableTreeView.mousePressEvent: {button}")
        
        if event.button() == Qt.MouseButton.XButton1:
            print("XButton1 detected")
            self.back_button_clicked.emit()
            event.accept()
            return
        elif event.button() == Qt.MouseButton.XButton2:
            print("XButton2 detected")
            self.forward_button_clicked.emit()
            event.accept()
            return
        
        # Pass other events to parent
        super().mousePressEvent(event)
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Override to see double-clicks"""
        print(f"NavigableTreeView.mouseDoubleClickEvent: {event.button()}")
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


class FileExplorerTab(FileExplorerCore):
    """
    Extended FileExplorer with breadcrumb navigation and current path tracking
    """
    
    path_changed = pyqtSignal(str)  # Signal when path changes
    
    def __init__(self, initial_path=None):
        super().__init__()
        
        # Store the starting path (OneDrive if available)
        if initial_path:
            self.starting_path = initial_path
        else:
            onedrive_paths = self.get_onedrive_paths()
            self.starting_path = str(onedrive_paths[0]) if onedrive_paths else str(Path.home())
        
        self.current_directory = self.starting_path
        
        # Two separate history tracking systems:
        # 1. Current Path - browser-style with back/forward, truncates on branch
        self.current_path_history = []  # List of visited paths (truncates on branch)
        self.current_path_index = -1  # Current position in current path
        
        # 2. Full History - complete log of everywhere visited (never truncates)
        self.full_history = []  # List of all visited paths
        
        # Which history view is active in the panel
        self.history_view_mode = "current_path"  # "current_path" or "full_history"
        
        # Replace the parent's tree views with our custom NavigableTreeView
        # to catch mouse button events
        self._replace_views_with_navigable()
        
        # Set up dual pane feature
        self._setup_dual_pane()
        
        # Add breadcrumb bar at the top
        self.insert_breadcrumb_bar()
        
        # Only navigate if initial path is explicitly provided
        # Otherwise, stay at root level with Quick Links
        if initial_path:
            self.navigate_to_path(initial_path)
        else:
            # Stay at root level - don't navigate anywhere
            self.update_breadcrumb("Quick Links")
        
        # Set up keyboard shortcuts
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for navigation"""
        modifiers = event.modifiers()
        key = event.key()
        
        # Alt+Left = Back
        if key == Qt.Key.Key_Left and (modifiers & Qt.KeyboardModifier.AltModifier):
            self.navigate_back()
            event.accept()
            return
        
        # Alt+Right = Forward
        if key == Qt.Key.Key_Right and (modifiers & Qt.KeyboardModifier.AltModifier):
            self.navigate_forward()
            event.accept()
            return
        
        # Backspace = Go up one level (like Windows Explorer)
        if key == Qt.Key.Key_Backspace and not modifiers:
            self.go_up_one_level()
            event.accept()
            return
        
        # F5 = Refresh current folder
        if key == Qt.Key.Key_F5 and not modifiers:
            self.refresh_current_folder()
            event.accept()
            return
        
        super().keyPressEvent(event)
    
    def _setup_dual_pane(self):
        """Set up the Quick Links panel (on the right) - unified layout like bookmark bar"""
        from PyQt6.QtWidgets import QSplitter, QHeaderView, QVBoxLayout, QWidget, QLabel, QScrollArea
        from PyQt6.QtGui import QStandardItemModel, QStandardItem
        from PyQt6.QtCore import Qt
        
        # Find the main splitter that contains tree and details
        for child in self.findChildren(QSplitter):
            if child.count() >= 2:
                self.main_splitter = child
                break
        
        if not hasattr(self, 'main_splitter'):
            print("Could not find main splitter")
            return
        
        # Create a panel for Quick Links
        quick_links_panel = QWidget()
        quick_links_panel.setVisible(False)  # Hidden by default
        quick_links_panel.setMinimumWidth(180)  # Ensure minimum width for readability
        panel_layout = QVBoxLayout(quick_links_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # Add "Quick Links" header
        header_label = QLabel("Quick Links")
        header_label.setStyleSheet("""
            QLabel {
                background-color: #D4C0E8;
                padding: 4px 8px;
                font-weight: 600;
                font-size: 10pt;
                color: #4A2080;
                border: none;
                border-bottom: 1px solid #B098D0;
            }
        """)
        # Add context menu to header for creating new categories
        header_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header_label.customContextMenuRequested.connect(self._show_quick_links_panel_context_menu)
        panel_layout.addWidget(header_label)
        self.quick_links_header = header_label
        
        # Create a separate model for Quick Links (kept for compatibility)
        self.quick_links_model = QStandardItemModel()
        self.quick_links_model.setHorizontalHeaderLabels(['Name'])
        
        # Create scroll area to hold all Quick Links content (items + categories unified)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)
        
        # Container widget inside scroll area - use DropScrollArea to accept drops in empty space
        scroll_content = DropScrollArea()
        scroll_content.bookmark_dropped.connect(self.on_bookmark_dropped_to_quick_links)
        scroll_content.file_dropped.connect(self.on_file_dropped_to_quick_links)
        scroll_content.category_dropped.connect(self.on_category_dropped_to_quick_links)
        scroll_content.item_dropped.connect(self.on_quick_link_item_dropped)
        
        # Add context menu to scroll content for creating new categories
        scroll_content.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        scroll_content.customContextMenuRequested.connect(self._show_quick_links_panel_context_menu)
        
        # Unified layout - bookmarks AND categories mixed together in order
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(2, 2, 2, 2)
        scroll_layout.setSpacing(1)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Store reference to the unified items layout
        self.quick_links_items_layout = scroll_layout
        
        # Set the items layout on the drop area for position detection
        scroll_content.set_items_layout(scroll_layout)
        
        # We no longer need separate list and categories container
        # All items (bookmarks and categories) are added directly to scroll_layout
        
        scroll_area.setWidget(scroll_content)
        panel_layout.addWidget(scroll_area)
        self.quick_links_scroll_area = scroll_area
        self.quick_links_scroll_content = scroll_content
        
        # Populate with quick links (items and categories)
        self.refresh_quick_links_list()
        
        # Add footer to Quick Links panel
        footer = QLabel("")
        footer.setStyleSheet("""
            QLabel {
                background-color: #E8D8F0;
                padding: 2px 8px;
                font-size: 9pt;
                color: #555555;
                border: none;
                border-top: 1px solid #B098D0;
            }
        """)
        footer.setFixedHeight(20)
        panel_layout.addWidget(footer)
        self.quick_links_footer = footer
        
        # Add to the RIGHT side of the splitter (after details view)
        self.main_splitter.addWidget(quick_links_panel)
        
        # Store reference to the panel (keep old name for compatibility)
        self.tree_panel_2 = quick_links_panel
        self.quick_links_panel = quick_links_panel
        
        # Store dual pane state
        self.dual_pane_active = False
    
    def show_quick_links_context_menu(self, position):
        """Show context menu for Quick Links panel items - DEPRECATED, using per-item menus now"""
        # This method is deprecated - context menus are now handled by individual item buttons
        pass
    
    def open_quick_link_path(self, path):
        """Open a quick link path - navigate for folders, open for files"""
        path_obj = Path(path)
        if path_obj.is_file():
            self.open_file(path)
        else:
            self.navigate_to_path(path)
    
    def open_path_in_explorer(self, path):
        """Open a path in Windows Explorer"""
        import subprocess
        from pathlib import Path
        path = Path(path)
        if path.exists():
            if path.is_file():
                subprocess.run(['explorer', '/select,', str(path)])
            else:
                subprocess.run(['explorer', str(path)])
    
    def refresh_quick_links_list(self):
        """Refresh the Quick Links list - unified layout with bookmarks and categories intermixed"""
        if not hasattr(self, 'quick_links_items_layout'):
            return
            
        from PyQt6.QtCore import Qt
        from pathlib import Path
        
        # Clear existing widgets from the unified layout
        while self.quick_links_items_layout.count():
            item = self.quick_links_items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Track counts for footer
        bookmark_count = 0
        category_count = 0
        
        # Get the items list from the new structured format
        items = self.custom_quick_links.get('items', [])
        categories = self.custom_quick_links.get('categories', {})
        
        # Process items in order - both bookmarks and categories go into the same layout
        for idx, item_data in enumerate(items):
            if item_data.get('type') == 'bookmark':
                # Top-level bookmark - create a draggable button
                bookmark_data = item_data.get('data', {})
                path_str = bookmark_data.get('path', '')
                name = bookmark_data.get('name', '')
                
                if path_str:
                    path = Path(path_str)
                    display_name = name or path.name
                    
                    # Get icon
                    icon = None
                    if path.exists():
                        icon = self._get_cached_icon(path, path.is_dir())
                    
                    # Create draggable bookmark button
                    bookmark_btn = QuickLinkBookmarkButton(
                        display_name, 
                        path_str, 
                        icon=icon,
                        item_index=idx,
                        parent=self
                    )
                    bookmark_btn.clicked_path.connect(self._on_bookmark_clicked)
                    bookmark_btn.double_clicked_path.connect(self._on_bookmark_double_clicked)
                    bookmark_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    bookmark_btn.customContextMenuRequested.connect(
                        lambda pos, b=bookmark_btn: self._show_bookmark_context_menu(pos, b)
                    )
                    
                    self.quick_links_items_layout.addWidget(bookmark_btn)
                    bookmark_count += 1
                    
            elif item_data.get('type') == 'category':
                # Category with bookmarks inside - use unified CategoryButton
                category_name = item_data.get('name', '')
                if category_name and category_name in categories:
                    category_items = categories[category_name]
                    
                    # Create unified category button (same as top bar)
                    cat_btn = CategoryButton(
                        category_name=category_name,
                        category_items=category_items,
                        item_index=idx,
                        parent=self,
                        data_manager=self,  # FileExplorerTab has custom_quick_links, save_quick_links, refresh_quick_links_list
                        source_location='sidebar',
                        orientation='vertical'
                    )
                    
                    # Connect signals
                    cat_btn.item_clicked.connect(self._on_category_item_clicked)
                    
                    self.quick_links_items_layout.addWidget(cat_btn)
                    category_count += 1
                    bookmark_count += len(category_items)
        
        # Add stretch at the bottom to allow drops
        self.quick_links_items_layout.addStretch()
        
        # Update footer
        if hasattr(self, 'quick_links_footer'):
            if category_count > 0:
                self.quick_links_footer.setText(f"{bookmark_count} item(s), {category_count} categories")
            else:
                self.quick_links_footer.setText(f"{bookmark_count} quick link(s)")
    
    def _on_bookmark_clicked(self, path):
        """Handle click on bookmark button in Quick Links"""
        path_obj = Path(path)
        if path_obj.is_dir():
            self.navigate_to_path(path)
    
    def _on_bookmark_double_clicked(self, path):
        """Handle double-click on bookmark button in Quick Links"""
        path_obj = Path(path)
        if path_obj.is_file():
            self.open_file(path)
        else:
            self.navigate_to_path(path)
    
    def _show_bookmark_context_menu(self, position, bookmark_btn):
        """Show context menu for a bookmark button in Quick Links"""
        from PyQt6.QtWidgets import QMenu, QApplication
        from PyQt6.QtGui import QAction
        
        path = bookmark_btn.bookmark_path
        
        menu = QMenu(self)
        
        # Open folder location - navigate to parent folder
        open_folder_action = QAction("📂 Open folder location", self)
        open_folder_action.triggered.connect(lambda: self._open_folder_location(path))
        menu.addAction(open_folder_action)
        
        # Copy full link to clipboard
        copy_link_action = QAction("📋 Copy full link to clipboard", self)
        copy_link_action.triggered.connect(lambda: QApplication.clipboard().setText(path))
        menu.addAction(copy_link_action)
        
        menu.addSeparator()
        
        # Remove action
        remove_action = QAction("🗑️ Remove from Quick Links", self)
        remove_action.triggered.connect(lambda: self._remove_bookmark_from_quick_links(path))
        menu.addAction(remove_action)
        
        menu.exec(bookmark_btn.mapToGlobal(position))
    
    def _open_folder_location(self, path):
        """Open the folder containing the given path in File Navigator"""
        path_obj = Path(path)
        if path_obj.is_file():
            # Navigate to parent folder
            parent_folder = str(path_obj.parent)
        else:
            # It's already a folder, navigate to its parent
            parent_folder = str(path_obj.parent)
        
        if Path(parent_folder).exists():
            self.navigate_to_path(parent_folder)
    
    def _show_category_context_menu(self, position, cat_widget):
        """Show context menu for a category in Quick Links"""
        from PyQt6.QtWidgets import QMenu, QMessageBox, QInputDialog
        from PyQt6.QtGui import QAction
        
        category_name = cat_widget.category_name
        category_items = cat_widget.category_items
        
        menu = QMenu(self)
        
        # Rename action
        rename_action = QAction("✏️ Rename", self)
        rename_action.triggered.connect(lambda: self._rename_category_in_quick_links(category_name))
        menu.addAction(rename_action)
        
        menu.addSeparator()
        
        # Remove action with confirmation
        remove_action = QAction("🗑️ Remove from Quick Links", self)
        remove_action.triggered.connect(lambda: self._remove_category_with_confirmation(category_name, category_items))
        menu.addAction(remove_action)
        
        menu.exec(cat_widget.mapToGlobal(position))
    
    def _rename_category_in_quick_links(self, old_name):
        """Rename a category in Quick Links"""
        from PyQt6.QtWidgets import QInputDialog, QMessageBox, QLineEdit
        
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
            
            if new_name in self.custom_quick_links.get('categories', {}):
                QMessageBox.warning(self, "Duplicate", f"Category '{new_name}' already exists.")
            else:
                if self.rename_category_in_quick_links(old_name, new_name):
                    self.refresh_quick_links_list()
    
    def _remove_category_with_confirmation(self, category_name, category_items):
        """Remove a category from Quick Links with confirmation showing all items"""
        from PyQt6.QtWidgets import QMessageBox
        
        # Build message with list of items
        if category_items:
            items_list = "\n".join([f"  • {item.get('name', item.get('path', 'Unknown'))}" for item in category_items])
            message = f"Are you sure you want to remove the category '{category_name}'?\n\nThe following {len(category_items)} bookmark(s) will be deleted:\n{items_list}"
        else:
            message = f"Are you sure you want to remove the empty category '{category_name}'?"
        
        reply = QMessageBox.question(
            self,
            "Remove Category",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.remove_category_from_quick_links(category_name)
            self.refresh_quick_links_list()
    
    def _show_quick_links_panel_context_menu(self, position):
        """Show context menu for Quick Links panel (empty area or header) - allows creating new categories"""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        
        menu = QMenu(self)
        
        # New Category action
        new_category_action = QAction("📁 New Category...", self)
        new_category_action.triggered.connect(self._create_new_category)
        menu.addAction(new_category_action)
        
        # Get the sender widget to map position correctly
        sender = self.sender()
        if sender:
            menu.exec(sender.mapToGlobal(position))
        else:
            menu.exec(self.mapToGlobal(position))
    
    def _create_new_category(self):
        """Create a new empty category in Quick Links"""
        from PyQt6.QtWidgets import QInputDialog, QMessageBox, QLineEdit
        
        name, ok = QInputDialog.getText(
            self,
            "New Category",
            "Enter name for the new category:",
            QLineEdit.EchoMode.Normal,
            ""
        )
        
        if ok and name:
            name = name.strip()
            if not name:
                QMessageBox.warning(self, "Invalid Name", "Category name cannot be empty.")
                return
            
            # Check if category already exists
            if name in self.custom_quick_links.get('categories', {}):
                QMessageBox.warning(self, "Duplicate", f"Category '{name}' already exists.")
                return
            
            # Create the category
            if 'categories' not in self.custom_quick_links:
                self.custom_quick_links['categories'] = {}
            self.custom_quick_links['categories'][name] = []
            
            # Add to items list (categories appear at the end by default)
            if 'items' not in self.custom_quick_links:
                self.custom_quick_links['items'] = []
            self.custom_quick_links['items'].append({
                'type': 'category',
                'name': name
            })
            
            self.save_quick_links()
            self.refresh_quick_links_list()
            logger.info(f"Created new category '{name}' in Quick Links")
    
    def _remove_bookmark_from_quick_links(self, path):
        """Remove a bookmark from Quick Links"""
        items = self.custom_quick_links.get('items', [])
        # Find and remove the bookmark
        for i, item_data in enumerate(items):
            if item_data.get('type') == 'bookmark':
                if item_data.get('data', {}).get('path') == path:
                    items.pop(i)
                    self.save_quick_links()
                    self.refresh_quick_links_list()
                    return
    
    def on_quick_link_item_dropped(self, item_data, drop_index):
        """Handle an item being dropped at a specific position in Quick Links"""
        items = self.custom_quick_links.get('items', [])
        
        item_type = item_data.get('type', '')
        source = item_data.get('source', '')
        old_index = item_data.get('index', -1)
        source_category = item_data.get('source_category', '')
        
        if source == 'quick_links' and old_index >= 0:
            # Internal reorder - remove from old position first
            if old_index < len(items):
                moved_item = items.pop(old_index)
                # Adjust drop_index if we removed from before it
                if old_index < drop_index:
                    drop_index -= 1
                # Insert at new position
                items.insert(drop_index, moved_item)
                self.save_quick_links()
                self.refresh_quick_links_list()
        elif source == 'quick_links_category' and source_category:
            # Item from Quick Links category - move to main sidebar
            path = item_data.get('path', '')
            name = item_data.get('name', '')
            if path and not self.is_path_in_quick_links(path):
                # Add to sidebar
                self.add_to_quick_links(path, insert_at=drop_index)
                
                # Remove from source category
                categories = self.custom_quick_links.get('categories', {})
                if source_category in categories:
                    category_items = categories[source_category]
                    for i, item in enumerate(category_items):
                        if item.get('path') == path:
                            category_items.pop(i)
                            break
                self.save_quick_links()
                self.refresh_quick_links_list()
                logger.info(f"Moved '{name}' from category '{source_category}' to Quick Links sidebar")
        else:
            # New item from outside - will be handled by other drop handlers
            pass
    
    def _on_category_item_clicked(self, path):
        """Handle click on item inside a Quick Links category"""
        path_obj = Path(path)
        if path_obj.is_dir():
            self.navigate_to_path(path)
    
    def _on_category_item_double_clicked(self, path):
        """Handle double-click on item inside a Quick Links category"""
        path_obj = Path(path)
        if path_obj.is_file():
            self.open_file(path)
        else:
            self.navigate_to_path(path)
    
    def _on_bookmark_dropped_to_category(self, category_name, bookmark):
        """Handle bookmark dropped onto a Quick Links category"""
        path = bookmark.get('path', '')
        source_category = bookmark.get('_source_category', bookmark.get('source_category', ''))
        if not path:
            return
        
        # Don't move to the same category
        if source_category == category_name:
            return
        
        # Add to the category
        if category_name in self.custom_quick_links.get('categories', {}):
            # Check if already in category
            for item in self.custom_quick_links['categories'][category_name]:
                if item.get('path') == path:
                    return  # Already exists
            
            self.custom_quick_links['categories'][category_name].append({
                'name': bookmark.get('name', Path(path).name),
                'path': path,
                'type': bookmark.get('type', 'folder' if Path(path).is_dir() else 'file')
            })
            
            # Remove from source
            removed_from_source = False
            
            # If from bookmark bar (top level), remove from bar_items list
            if source_category == '__BAR__':
                if hasattr(self, 'bookmark_bar') and self.bookmark_bar:
                    bar_items = self.bookmark_bar.bookmarks_data.get('bar_items', [])
                    for i, item in enumerate(bar_items):
                        if item.get('type') == 'bookmark':
                            if item.get('data', {}).get('path') == path:
                                bar_items.pop(i)
                                self.bookmark_bar.save_bookmarks()
                                self.bookmark_bar.refresh_bookmarks()
                                logger.info(f"Removed '{path}' from bookmark bar")
                                removed_from_source = True
                                break
            
            # If from Quick Links sidebar (top level), remove from items list
            if not removed_from_source and source_category == '__QUICK_LINKS__':
                items = self.custom_quick_links.get('items', [])
                for i, item in enumerate(items):
                    if item.get('type') == 'bookmark':
                        if item.get('data', {}).get('path') == path:
                            items.pop(i)
                            logger.info(f"Removed '{path}' from Quick Links sidebar")
                            removed_from_source = True
                            break
            
            # Check Quick Links categories
            if not removed_from_source and source_category and source_category not in ('__QUICK_LINKS__', '__BAR__', ''):
                categories = self.custom_quick_links.get('categories', {})
                if source_category in categories:
                    category_items = categories[source_category]
                    for i, item in enumerate(category_items):
                        if item.get('path') == path:
                            category_items.pop(i)
                            logger.info(f"Removed '{path}' from Quick Links category '{source_category}'")
                            removed_from_source = True
                            break
                
                # If not found in Quick Links categories, check bookmark bar categories
                if not removed_from_source and hasattr(self, 'bookmark_bar') and self.bookmark_bar:
                    bar_categories = self.bookmark_bar.bookmarks_data.get('categories', {})
                    if source_category in bar_categories:
                        bar_category_items = bar_categories[source_category]
                        for i, item in enumerate(bar_category_items):
                            if item.get('path') == path:
                                bar_category_items.pop(i)
                                self.bookmark_bar.save_bookmarks()
                                self.bookmark_bar.refresh_bookmarks()
                                logger.info(f"Removed '{path}' from bookmark bar category '{source_category}'")
                                removed_from_source = True
                                break
            
            self.save_quick_links()
            self.refresh_quick_links_list()
            logger.info(f"Added '{path}' to category '{category_name}'")
    
    def _on_category_moved_out(self, category_name, category_data):
        """Handle category being dragged out of Quick Links"""
        # This is called when the category is being moved elsewhere
        # The actual removal happens when the drop is accepted
        pass
    
    def refresh_quick_links(self):
        """Refresh the Quick Links panel"""
        self.refresh_quick_links_list()
    
    def on_quick_links_reordered(self, new_order):
        """Handle Quick Links reorder via drag-drop"""
        # Convert the new_order (list of paths) back to structured items
        new_items = []
        for path in new_order:
            new_items.append({
                'type': 'bookmark',
                'data': {
                    'name': Path(path).name,
                    'path': path,
                    'type': 'folder' if Path(path).is_dir() else 'file'
                }
            })
        
        # Keep categories at the end (after the reordered bookmarks)
        for item in self.custom_quick_links.get('items', []):
            if item.get('type') == 'category':
                new_items.append(item)
        
        self.custom_quick_links['items'] = new_items
        self.save_quick_links()
        self.refresh_quick_links_list()
    
    def on_bookmark_dropped_to_quick_links(self, bookmark):
        """Handle bookmark dropped into Quick Links panel"""
        path = bookmark.get('path', '')
        drop_index = bookmark.get('_drop_index', -1)  # Position to insert at
        # Check both _source_category (set by drop handler) and source_category (fallback)
        source_category = bookmark.get('_source_category', bookmark.get('source_category', ''))
        
        logger.debug(f"on_bookmark_dropped_to_quick_links: path={path}, source_category={source_category}, drop_index={drop_index}")
        
        if not path:
            return
        
        # Check if already exists at top level (not in a category)
        already_at_top_level = False
        for item in self.custom_quick_links.get('items', []):
            if item.get('type') == 'bookmark':
                if item.get('data', {}).get('path') == path:
                    already_at_top_level = True
                    break
        
        # If coming from a category or bar, we want to move it to the sidebar
        if source_category and source_category not in ('__QUICK_LINKS__', '') and not already_at_top_level:
            # Add to sidebar at specified position
            self.add_to_quick_links(path, insert_at=drop_index)
            logger.info(f"Added bookmark '{bookmark.get('name', path)}' to Quick Links sidebar at position {drop_index}")
            
            # Remove from source
            removed_from_source = False
            
            # Check if from bookmark bar directly (not a category)
            if source_category == '__BAR__' and hasattr(self, 'bookmark_bar') and self.bookmark_bar:
                bar_items = self.bookmark_bar.bookmarks_data.get('bar_items', [])
                for i, item in enumerate(bar_items):
                    if item.get('type') == 'bookmark':
                        if item.get('data', {}).get('path') == path:
                            bar_items.pop(i)
                            self.bookmark_bar.save_bookmarks()
                            self.bookmark_bar.refresh_bookmarks()
                            logger.info(f"Removed '{path}' from bookmark bar")
                            removed_from_source = True
                            break
            
            # Try Quick Links categories
            if not removed_from_source:
                categories = self.custom_quick_links.get('categories', {})
                if source_category in categories:
                    category_items = categories[source_category]
                    for i, item in enumerate(category_items):
                        if item.get('path') == path:
                            category_items.pop(i)
                            removed_from_source = True
                            logger.info(f"Removed from Quick Links category '{source_category}'")
                            break
            
            # If not found in Quick Links, check bookmark bar categories
            if not removed_from_source and hasattr(self, 'bookmark_bar') and self.bookmark_bar:
                bar_categories = self.bookmark_bar.bookmarks_data.get('categories', {})
                if source_category in bar_categories:
                    bar_category_items = bar_categories[source_category]
                    for i, item in enumerate(bar_category_items):
                        if item.get('path') == path:
                            bar_category_items.pop(i)
                            self.bookmark_bar.save_bookmarks()
                            self.bookmark_bar.refresh_bookmarks()
                            logger.info(f"Removed from bookmark bar category '{source_category}'")
                            removed_from_source = True
                            break
            
            self.save_quick_links()
            self.refresh_quick_links_list()
        elif not self.is_path_in_quick_links(path):
            # New item from outside Quick Links entirely
            self.add_to_quick_links(path, insert_at=drop_index)
            logger.info(f"Added bookmark '{bookmark.get('name', path)}' to Quick Links at position {drop_index}")
    
    def on_file_dropped_to_quick_links(self, path):
        """Handle file/folder dropped into Quick Links panel from details view"""
        # Check if path is a dict with _drop_index
        if isinstance(path, dict):
            drop_index = path.get('_drop_index', -1)
            actual_path = path.get('path', '')
        else:
            drop_index = -1
            actual_path = path
        
        if actual_path and not self.is_path_in_quick_links(actual_path):
            self.add_to_quick_links(actual_path, insert_at=drop_index)
            logger.info(f"Added file '{actual_path}' to Quick Links at position {drop_index}")
    
    def on_category_dropped_to_quick_links(self, category_data):
        """Handle category dropped into Quick Links panel (MOVE from bookmark bar)"""
        category_name = category_data.get('name', '')
        category_items = category_data.get('items', [])
        source = category_data.get('source', '')
        drop_index = category_data.get('_drop_index', -1)  # Position to insert at
        
        if not category_name:
            return
        
        # Check if category already exists in Quick Links
        if category_name in self.custom_quick_links.get('categories', {}):
            logger.warning(f"Category '{category_name}' already exists in Quick Links")
            return
        
        # Add category to Quick Links at the specified position
        self.add_category_to_quick_links(category_name, category_items, insert_at=drop_index)
        
        # If it came from bookmark bar, remove it from there (MOVE semantics)
        if source == 'bookmark_bar' and hasattr(self, 'bookmark_bar'):
            self._remove_category_from_bookmark_bar(category_name)
        
        self.refresh_quick_links_list()
        logger.info(f"Moved category '{category_name}' to Quick Links at position {drop_index}")
    
    def _remove_category_from_bookmark_bar(self, category_name):
        """Remove a category from the bookmark bar (after moving to Quick Links)"""
        if not hasattr(self, 'bookmark_bar'):
            return
        
        bookmarks_data = self.bookmark_bar.bookmarks_data
        
        # Remove from categories dict
        if category_name in bookmarks_data.get('categories', {}):
            del bookmarks_data['categories'][category_name]
        
        # Remove from bar_items
        bar_items = bookmarks_data.get('bar_items', [])
        for i, item in enumerate(bar_items):
            if item.get('type') == 'category' and item.get('name') == category_name:
                bar_items.pop(i)
                break
        
        self.bookmark_bar.save_bookmarks()
        self.bookmark_bar.refresh_bookmarks()
    
    def on_quick_link_clicked(self, item):
        """Handle single click on quick link - navigate to folder or select file"""
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if path_str:
            path = Path(path_str)
            if path.is_dir():
                self.navigate_to_path(path_str)
    
    def on_quick_link_double_clicked(self, item):
        """Handle double click on quick link - open the item"""
        path_str = item.data(Qt.ItemDataRole.UserRole)
        if path_str:
            path = Path(path_str)
            if path.is_file():
                self.open_file(path_str)
            else:
                self.navigate_to_path(path_str)
    
    def toggle_dual_pane(self):
        """Toggle the Quick Links panel on/off"""
        self.dual_pane_active = not self.dual_pane_active
        
        if hasattr(self, 'tree_panel_2'):
            self.tree_panel_2.setVisible(self.dual_pane_active)
            
            # Refresh quick links when showing
            if self.dual_pane_active:
                self.refresh_quick_links()
            
            # Adjust splitter sizes when toggling
            # IMPORTANT: Preserve the left panel width
            current_sizes = self.main_splitter.sizes()
            left_width = current_sizes[0] if current_sizes else 300  # Keep current left width
            
            if self.dual_pane_active:
                # Three panes: left tree (keep size), details (middle), right quick links
                total_available = self.main_splitter.width() - left_width
                right_width = max(200, int(total_available * 0.25))  # At least 200px or 25% for Quick Links
                middle_width = total_available - right_width  # Rest goes to details
                self.main_splitter.setSizes([left_width, middle_width, right_width])
            else:
                # Two panes: left tree (keep size), details (take rest)
                details_width = self.main_splitter.width() - left_width
                self.main_splitter.setSizes([left_width, details_width, 0])
        
        print(f"Dual pane {'enabled' if self.dual_pane_active else 'disabled'}")
    
    def _replace_views_with_navigable(self):
        """Replace parent's QTreeView instances with NavigableTreeView"""
        from suiteview.ui.file_explorer_core import NoFocusDelegate
        
        # Get the parent's splitter that contains the views
        splitter = self.findChild(QWidget.__class__, "")  # Find splitter
        
        # Store old views' properties
        old_tree = self.tree_view
        old_details = self.details_view
        
        # Get the parent widgets (they're in a splitter)
        tree_parent = old_tree.parent()
        details_parent = old_details.parent()
        
        # Get layouts
        tree_layout = tree_parent.layout() if hasattr(tree_parent, 'layout') and tree_parent.layout() else None
        details_layout = details_parent.layout() if hasattr(details_parent, 'layout') and details_parent.layout() else None
        
        # Create new navigable views
        new_tree = NavigableTreeView()
        new_details = NavigableTreeView()
        
        # Copy properties from old tree view to new one
        new_tree.setModel(old_tree.model())
        new_tree.setAnimated(old_tree.isAnimated())
        new_tree.setIndentation(old_tree.indentation())
        new_tree.setHeaderHidden(old_tree.isHeaderHidden())
        new_tree.setSelectionMode(old_tree.selectionMode())
        new_tree.setContextMenuPolicy(old_tree.contextMenuPolicy())
        
        # Copy stylesheet from old tree view
        new_tree.setStyleSheet(old_tree.styleSheet())
        
        # Apply NoFocusDelegate to remove focus rectangle
        new_tree.setItemDelegate(NoFocusDelegate(new_tree))
        
        # Copy properties from old details view to new one  
        new_details.setModel(old_details.model())
        new_details.setAnimated(old_details.isAnimated())
        new_details.setRootIsDecorated(old_details.rootIsDecorated())
        new_details.setIndentation(old_details.indentation())
        new_details.setHeaderHidden(old_details.isHeaderHidden())
        new_details.setSelectionMode(old_details.selectionMode())
        new_details.setSortingEnabled(old_details.isSortingEnabled())
        new_details.setAlternatingRowColors(old_details.alternatingRowColors())
        new_details.setContextMenuPolicy(old_details.contextMenuPolicy())

        # Preserve styling and remove the focus rectangle on selected items.
        # (Without this, Windows styles can draw a visible focus "halo" around the text.)
        new_details.setStyleSheet(old_details.styleSheet())
        new_details.setItemDelegate(NoFocusDelegate(new_details))
        
        # Copy sort column and order from old view (default to Name ascending)
        old_header = old_details.header()
        sort_column = old_header.sortIndicatorSection()
        sort_order = old_header.sortIndicatorOrder()
        new_details.sortByColumn(sort_column, sort_order)
        
        # Replace in layouts
        if tree_layout:
            tree_layout.replaceWidget(old_tree, new_tree)
        if details_layout:
            details_layout.replaceWidget(old_details, new_details)
        
        # Delete old views
        old_tree.deleteLater()
        old_details.deleteLater()
        
        # Update references
        self.tree_view = new_tree
        self.details_view = new_details
        
        # Reconnect signals that were on the old views
        # Note: We don't need to disconnect old signals because old_tree and old_details are being deleted
        self.tree_view.expanded.connect(self.on_item_expanded)
        self.tree_view.clicked.connect(self.on_tree_item_clicked)
        self.tree_view.customContextMenuRequested.connect(self.show_tree_context_menu)
        
        # IMPORTANT: Connect to our overridden method for history tracking
        self.details_view.doubleClicked.connect(self.on_details_item_double_clicked)
        self.details_view.customContextMenuRequested.connect(self.show_details_context_menu)
        
        print(f"Connected details_view.doubleClicked to {self.on_details_item_double_clicked}")
        print(f"details_view type: {type(self.details_view)}")
        print(f"Method owner: {self.on_details_item_double_clicked.__self__.__class__.__name__}")
        
        # Connect navigation signals
        self.tree_view.back_button_clicked.connect(self.navigate_back)
        self.tree_view.forward_button_clicked.connect(self.navigate_forward)
        self.details_view.back_button_clicked.connect(self.navigate_back)
        self.details_view.forward_button_clicked.connect(self.navigate_forward)
        
        # Connect drag/drop signals for tree view (left panel)
        self.tree_view.set_file_explorer(self)
        self.tree_view.files_dropped.connect(self.handle_dropped_files)
        
        # Connect drag/drop signals for details view (middle panel)
        self.details_view.set_file_explorer(self)
        self.details_view.files_dropped.connect(self.handle_dropped_files)
        
        # Reinstall event filter for keyboard shortcuts (F2, Delete, Ctrl+C/V/X)
        self.details_view.installEventFilter(self)
    
    def insert_breadcrumb_bar(self):
        """Insert breadcrumb navigation bar above the tree"""
        # Get the main layout
        main_layout = self.layout()
        
        # Create breadcrumb widget with fixed height
        breadcrumb_frame = QFrame()
        breadcrumb_frame.setObjectName("breadcrumbFrame")
        breadcrumb_frame.setFrameShape(QFrame.Shape.StyledPanel)
        breadcrumb_frame.setFixedHeight(32)  # Fixed height for breadcrumb bar
        breadcrumb_frame.setStyleSheet("""
            QFrame#breadcrumbFrame {
                background-color: #FFFDE7;
                border: 2px solid #6B8DC9;
                border-radius: 4px;
            }
            QFrame#breadcrumbFrame:hover {
                border-color: #2563EB;
            }
        """)
        
        breadcrumb_layout = QHBoxLayout(breadcrumb_frame)
        breadcrumb_layout.setContentsMargins(4, 3, 4, 3)
        breadcrumb_layout.setSpacing(4)

        # History panel toggle button (left of navigation buttons)
        history_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
        self.history_btn = QPushButton()
        self.history_btn.setIcon(history_icon)
        self.history_btn.setToolTip("Toggle History Panel")
        self.history_btn.setFixedSize(24, 24)
        self.history_btn.setCheckable(True)
        self.history_btn.setStyleSheet("""
            QPushButton {
                background-color: #E0ECFF;
                border: 1px solid #2563EB;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #C9DAFF;
            }
            QPushButton:checked {
                background-color: #1E3A8A;
                border: 1px solid #FFD700;
            }
        """)
        self.history_btn.clicked.connect(self.toggle_history_panel)
        breadcrumb_layout.addWidget(self.history_btn)
        
        # Back button
        back_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        self.back_btn = self._create_nav_button(back_icon, "Go Back (Alt+Left)", self.navigate_back)
        breadcrumb_layout.addWidget(self.back_btn)
        
        # Forward button
        forward_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward)
        self.forward_btn = self._create_nav_button(forward_icon, "Go Forward (Alt+Right)", self.navigate_forward)
        breadcrumb_layout.addWidget(self.forward_btn)
        
        # Up/Back button
        up_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        self.up_btn = self._create_nav_button(up_icon, "Go Up One Level", self.go_up_one_level)
        breadcrumb_layout.addWidget(self.up_btn)
        
        # Refresh button
        refresh_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        self.refresh_btn = self._create_nav_button(refresh_icon, "Refresh Folder (F5)", self.refresh_current_folder)
        breadcrumb_layout.addWidget(self.refresh_btn)
        
        # Clickable breadcrumb widget
        self.breadcrumb_widget = ClickableBreadcrumb()
        self.breadcrumb_widget.path_clicked.connect(self.navigate_to_path)
        breadcrumb_layout.addWidget(self.breadcrumb_widget, 1)
        
        # Dual pane toggle button
        self.dual_pane_btn = QPushButton()
        self.dual_pane_btn.setToolTip("Toggle Dual Pane View")
        self.dual_pane_btn.setFixedSize(24, 24)
        self.dual_pane_btn.setCheckable(True)
        list_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)
        self.dual_pane_btn.setIcon(list_icon)
        self.dual_pane_btn.setIconSize(QSize(14, 14))
        self.dual_pane_btn.setStyleSheet("""
            QPushButton {
                background-color: #E0ECFF;
                border: 1px solid #2563EB;
                border-radius: 4px;
                color: #0A1E5E;
            }
            QPushButton:hover {
                background-color: #C9DAFF;
            }
            QPushButton:checked {
                background-color: #1E3A8A;
                border: 1px solid #FFD700;
            }
        """)
        self.dual_pane_btn.clicked.connect(self.toggle_dual_pane)
        breadcrumb_layout.addWidget(self.dual_pane_btn)
        
        # Insert at position 1 (after toolbar)
        main_layout.insertWidget(1, breadcrumb_frame)
        
        # Update initial breadcrumb
        self.update_breadcrumb(self.current_directory)
    
    def update_breadcrumb(self, path):
        """Update breadcrumb display"""
        try:
            path_obj = Path(path)
            if path_obj.exists() and path_obj.is_file():
                path_obj = path_obj.parent
            
            # Update the clickable breadcrumb widget
            self.breadcrumb_widget.set_path(str(path_obj))
            
            self.current_directory = str(path_obj)
            self.path_changed.emit(str(path_obj))
            
        except Exception as e:
            logger.error(f"Failed to update breadcrumb: {e}")
            self.breadcrumb_widget.set_path(str(path))
    
    def go_to_onedrive_home(self):
        """Navigate to the starting path (OneDrive folder where app opened)"""
        if hasattr(self, 'starting_path'):
            self.navigate_to_path(self.starting_path)
        else:
            # Fallback: try to find OneDrive
            onedrive_paths = self.get_onedrive_paths()
            if onedrive_paths:
                self.navigate_to_path(str(onedrive_paths[0]))
            else:
                self.navigate_to_path(str(Path.home()))
    
    def navigate_to_path(self, path, add_to_history=True):
        """Navigate to a specific directory path - loads in details pane (right side)"""
        try:
            path_obj = Path(path)
            if not path_obj.exists():
                return
            
            if path_obj.is_file():
                path_obj = path_obj.parent
            
            path_str = str(path_obj)
            
            # Add to navigation history if requested (not when using back/forward)
            if add_to_history:
                # Current Path History - browser-style with truncation
                # If we're not at the end, truncate everything after current position
                if self.current_path_index < len(self.current_path_history) - 1:
                    self.current_path_history = self.current_path_history[:self.current_path_index + 1]
                
                # Add new path if different from current
                if not self.current_path_history or self.current_path_history[-1] != path_str:
                    self.current_path_history.append(path_str)
                    self.current_path_index = len(self.current_path_history) - 1
                
                # Full History - always append, never truncate
                if not self.full_history or self.full_history[-1] != path_str:
                    self.full_history.append(path_str)
                
                print(f"Added to history: {path_str}")
                print(f"Current Path: {self.current_path_history}, index={self.current_path_index}")
                print(f"Full History: {self.full_history}")
            
            # Update breadcrumb
            self.update_breadcrumb(path_str)
            
            # Update navigation button states
            self._update_nav_button_states()
            
            # Load in the details pane (right side) instead of tree
            self.load_folder_contents_in_details(path_obj)
            
        except Exception as e:
            logger.error(f"Failed to navigate to {path}: {e}")
    
    def _update_nav_button_states(self):
        """Update enabled/disabled state of back/forward buttons based on current path history"""
        if hasattr(self, 'back_btn'):
            self.back_btn.setEnabled(self.current_path_index > 0)
        if hasattr(self, 'forward_btn'):
            self.forward_btn.setEnabled(self.current_path_index < len(self.current_path_history) - 1)
        # Update history panel if visible
        if hasattr(self, 'history_panel') and self.history_panel.isVisible():
            self._update_history_panel()
    
    def toggle_history_panel(self):
        """Toggle the history panel on/off"""
        if not hasattr(self, 'history_panel'):
            self._create_history_panel()
        
        if self.history_panel.isVisible():
            self.history_panel.hide()
            self.history_btn.setChecked(False)
        else:
            self._update_history_panel()
            self.history_panel.show()
            self.history_btn.setChecked(True)
    
    def _create_history_panel(self):
        """Create the history panel widget"""
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QButtonGroup, QToolButton
        
        # Create panel frame
        self.history_panel = QFrame(self)
        self.history_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.history_panel.setStyleSheet("""
            QFrame {
                background-color: #FFFDE7;
                border: 1px solid #94BBD9;
                border-radius: 4px;
            }
        """)
        
        panel_layout = QVBoxLayout(self.history_panel)
        panel_layout.setContentsMargins(6, 4, 6, 6)
        panel_layout.setSpacing(4)
        
        # Header with close button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_label = QLabel("History")
        header_label.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #1A3A6E; background: transparent; border: none; padding: 0px; margin: 0px;"
        )
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        
        # Close button
        close_btn = QToolButton()
        close_btn.setText("x")
        close_btn.setFixedSize(18, 18)
        close_btn.setToolTip("Close")
        close_btn.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                border: none;
                font-size: 12px;
                font-weight: bold;
                color: #B00020;
                padding: 0px;
                margin: 0px;
            }
            QToolButton:hover {
                background-color: rgba(176, 0, 32, 0.12);
                border-radius: 3px;
            }
        """)
        close_btn.clicked.connect(lambda: (self.history_panel.hide(), self.history_btn.setChecked(False)))
        header_layout.addWidget(close_btn)
        panel_layout.addLayout(header_layout)
        
        # Toggle buttons for Current Path vs Full History
        toggle_layout = QHBoxLayout()
        toggle_layout.setSpacing(2)
        
        toggle_btn_style = """
            QPushButton {
                background-color: transparent;
                border: 1px solid #94BBD9;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 9px;
                color: #1A3A6E;
            }
            QPushButton:hover {
                background-color: #C0DAF0;
            }
            QPushButton:checked {
                background-color: #1A3A6E;
                color: white;
                border: 1px solid #1A3A6E;
            }
        """
        
        self.current_path_btn = QPushButton("Current Path")
        self.current_path_btn.setCheckable(True)
        self.current_path_btn.setChecked(True)
        self.current_path_btn.setStyleSheet(toggle_btn_style)
        self.current_path_btn.clicked.connect(lambda: self._set_history_view("current_path"))
        toggle_layout.addWidget(self.current_path_btn)
        
        self.full_history_btn = QPushButton("Full History")
        self.full_history_btn.setCheckable(True)
        self.full_history_btn.setStyleSheet(toggle_btn_style)
        self.full_history_btn.clicked.connect(lambda: self._set_history_view("full_history"))
        toggle_layout.addWidget(self.full_history_btn)
        
        panel_layout.addLayout(toggle_layout)
        
        # History list
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                font-size: 10px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #A8C8E8;
                background: transparent;
            }
            QListWidget::item:selected {
                background-color: #A0C4E8;
                color: #1A3A6E;
            }
            QListWidget::item:hover {
                background-color: #C0DAF0;
            }
        """)
        self.history_list.itemClicked.connect(self._on_history_item_clicked)
        panel_layout.addWidget(self.history_list)
        
        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #94BBD9;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 10px;
                color: #0066cc;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #B8D4EC;
            }
        """)
        clear_btn.clicked.connect(self._clear_history)
        panel_layout.addWidget(clear_btn)
        
        # Position panel on the left side
        self.history_panel.setFixedWidth(200)
        self.history_panel.hide()
        
        # Insert into main layout at the left
        main_layout = self.layout()
        # Find the splitter and insert panel before it
        for i in range(main_layout.count()):
            widget = main_layout.itemAt(i).widget()
            if isinstance(widget, QSplitter):
                # Create a horizontal layout to hold history panel and splitter
                container = QWidget()
                container_layout = QHBoxLayout(container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(4)
                
                # Add history panel
                container_layout.addWidget(self.history_panel)
                
                # Move splitter to container
                main_layout.removeWidget(widget)
                container_layout.addWidget(widget)
                
                # Add container back to main layout
                main_layout.insertWidget(i, container)
                break
    
    def _set_history_view(self, mode):
        """Switch between current path and full history views"""
        self.history_view_mode = mode
        
        # Update button states
        self.current_path_btn.setChecked(mode == "current_path")
        self.full_history_btn.setChecked(mode == "full_history")
        
        # Refresh the list
        self._update_history_panel()
    
    def _update_history_panel(self):
        """Update the history list widget with current history"""
        if not hasattr(self, 'history_list'):
            return
        
        self.history_list.clear()
        
        # Choose which history to display
        if self.history_view_mode == "current_path":
            history = self.current_path_history
            current_index = self.current_path_index
        else:
            history = self.full_history
            current_index = len(self.full_history) - 1 if self.full_history else -1
        
        if not history:
            item = QListWidgetItem("No history yet")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.history_list.addItem(item)
            return
        
        # Show history with most recent at top
        for i, path in enumerate(reversed(history)):
            actual_index = len(history) - 1 - i
            path_obj = Path(path)
            
            # Create display name (folder name or drive letter)
            if path_obj.name:
                display_name = path_obj.name
            else:
                display_name = str(path_obj)
            
            # Mark current position (only for current path view)
            if self.history_view_mode == "current_path" and actual_index == current_index:
                display_name = f"● {display_name}"
            
            item = QListWidgetItem(display_name)
            item.setToolTip(path)
            item.setData(Qt.ItemDataRole.UserRole, actual_index)
            self.history_list.addItem(item)
    
    def _on_history_item_clicked(self, item):
        """Handle click on history list item"""
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return
        
        if self.history_view_mode == "current_path":
            # Current Path view: jump to that position (like back/forward)
            if 0 <= index < len(self.current_path_history):
                self.current_path_index = index
                path = self.current_path_history[index]
                # Also add to full history
                if not self.full_history or self.full_history[-1] != path:
                    self.full_history.append(path)
                self.navigate_to_path(path, add_to_history=False)
        else:
            # Full History view: navigate there as a new entry
            if 0 <= index < len(self.full_history):
                path = self.full_history[index]
                self.navigate_to_path(path, add_to_history=True)
                
    def _jump_to_history_index(self, index):
        """Jump to a specific index in the current path history"""
        if 0 <= index < len(self.current_path_history):
            self.current_path_index = index
            path = self.current_path_history[index]
            self.navigate_to_path(path, add_to_history=False)
    
    def _clear_history(self):
        """Clear navigation history based on current view mode"""
        if self.history_view_mode == "current_path":
            # Clear current path, keep only current location
            if self.current_path_history and 0 <= self.current_path_index < len(self.current_path_history):
                current = self.current_path_history[self.current_path_index]
                self.current_path_history = [current]
                self.current_path_index = 0
            else:
                self.current_path_history = []
                self.current_path_index = -1
        else:
            # Clear full history, keep only current location
            if self.current_path_history and 0 <= self.current_path_index < len(self.current_path_history):
                current = self.current_path_history[self.current_path_index]
                self.full_history = [current]
            else:
                self.full_history = []
        self._update_nav_button_states()
    
    def navigate_back(self):
        """Navigate to previous folder in current path history"""
        print(f"navigate_back called: index={self.current_path_index}, history={self.current_path_history}")
        if self.current_path_index > 0:
            self.current_path_index -= 1
            path = self.current_path_history[self.current_path_index]
            print(f"Going back to: {path}")
            # Also add to full history
            if not self.full_history or self.full_history[-1] != path:
                self.full_history.append(path)
            self.navigate_to_path(path, add_to_history=False)
        else:
            print("Already at beginning of history")
    
    def navigate_forward(self):
        """Navigate to next folder in current path history"""
        print(f"navigate_forward called: index={self.current_path_index}, history={self.current_path_history}")
        if self.current_path_index < len(self.current_path_history) - 1:
            self.current_path_index += 1
            path = self.current_path_history[self.current_path_index]
            print(f"Going forward to: {path}")
            # Also add to full history
            if not self.full_history or self.full_history[-1] != path:
                self.full_history.append(path)
            self.navigate_to_path(path, add_to_history=False)
        else:
            print("Already at end of history")
    
    def on_details_item_double_clicked(self, index):
        """Override to use navigate_to_path for history tracking"""
        print(f"\n=== DOUBLE CLICK DEBUG ===")
        print(f"Proxy Index: row={index.row()}, col={index.column()}")
        
        # Get the data directly from the proxy model (which handles sorting)
        path = self.details_sort_proxy.data(index, Qt.ItemDataRole.UserRole)
        
        # If this column doesn't have the path data, get it from column 0 of the same row
        if not path:
            col0_index = index.sibling(index.row(), 0)
            col0_text = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.DisplayRole)
            print(f"Column 0 text for this row: {col0_text}")
            path = self.details_sort_proxy.data(col0_index, Qt.ItemDataRole.UserRole)
        
        if not path:
            print("No path data found")
            return
        
        print(f"Path retrieved: {path}")
        print(f"=========================\n")
        
        path_obj = Path(path)
        
        # Handle .lnk shortcut files - resolve target and navigate if it's a folder
        if path_obj.suffix.lower() == '.lnk' and path_obj.is_file():
            target_path = self._resolve_shortcut(str(path_obj))
            if target_path:
                target_obj = Path(target_path)
                if target_obj.exists() and target_obj.is_dir():
                    # Navigate to the folder target within File Nav (with history tracking)
                    print(f"Shortcut resolves to folder: {target_obj}")
                    self.navigate_to_path(target_obj, add_to_history=True)
                    return
                elif target_obj.exists() and target_obj.is_file():
                    # Shortcut points to a file, open it
                    print(f"Shortcut resolves to file: {target_obj}")
                    try:
                        if os.name == 'nt':
                            os.startfile(str(target_obj))
                        elif sys.platform == 'darwin':
                            subprocess.run(['open', str(target_obj)])
                        else:
                            subprocess.run(['xdg-open', str(target_obj)])
                    except Exception as e:
                        logger.error(f"Failed to open file: {e}")
                        from PyQt6.QtWidgets import QMessageBox
                        QMessageBox.warning(self, "Cannot Open File", f"Failed to open {target_obj.name}\n\nError: {str(e)}")
                    return
            # If we can't resolve, fall through to open the .lnk file itself
        
        if path_obj.is_dir():
            print(f"Is directory, navigating to: {path_obj}")
            # Use navigate_to_path to track history
            self.navigate_to_path(path_obj, add_to_history=True)
        elif path_obj.is_file():
            # Open file with default application
            try:
                if os.name == 'nt':
                    os.startfile(str(path_obj))
                elif sys.platform == 'darwin':
                    subprocess.run(['open', str(path_obj)])
                else:
                    subprocess.run(['xdg-open', str(path_obj)])
            except Exception as e:
                logger.error(f"Failed to open file: {e}")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Cannot Open File", f"Failed to open {path_obj.name}\n\nError: {str(e)}")
    
    def load_directory_contents_at_root(self, dir_path):
        """Load a specific directory at the root of the tree"""
        self.model.clear()
        self.model.setHorizontalHeaderLabels(['Name', 'Size', 'Type', 'Date Modified'])
        
        try:
            dir_path = Path(dir_path)
            items = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item in items:
                try:
                    if item.is_dir():
                        row_items = self.create_folder_item(item)
                    else:
                        row_items = self.create_file_item(item)
                    
                    self.model.appendRow(row_items)
                except (PermissionError, OSError):
                    continue
                    
        except (PermissionError, OSError) as e:
            logger.error(f"Cannot access {dir_path}: {e}")
    
    def go_up_one_level(self):
        """Go up one directory level - operates on details view"""
        # Use the current details folder, not the tree selection
        if hasattr(self, 'current_details_folder') and self.current_details_folder:
            current = Path(self.current_details_folder)
        else:
            current = Path(self.current_directory)
        
        if current.parent != current:  # Not at root
            parent_path = str(current.parent)
            # Use navigate_to_path which handles history
            self.navigate_to_path(parent_path)
    
    def refresh_current_folder(self):
        """Refresh the current folder contents"""
        if hasattr(self, 'current_details_folder') and self.current_details_folder:
            # Refresh without adding to history
            self.load_folder_contents_in_details(Path(self.current_details_folder))
    
    def on_tree_item_clicked(self, index):
        """Override parent method to use navigate_to_path for history tracking"""
        # Get the path from the clicked item
        item = self.model.itemFromIndex(index)
        if not item:
            return
        
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            # Use navigate_to_path which handles history
            self.navigate_to_path(path)
    
    def navigate_to_bookmark_folder(self, folder_path):
        """Override parent method to use navigate_to_path for history tracking"""
        # Use navigate_to_path which handles history
        self.navigate_to_path(folder_path)
    
    def on_item_double_clicked(self, index):
        """Override to update breadcrumb when navigating into folders"""
        item = self.model.itemFromIndex(self.model.index(index.row(), 0, index.parent()))
        if not item:
            return
        
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        
        path_obj = Path(path)
        
        if path_obj.is_dir():
            # Navigate into this directory
            self.navigate_to_path(str(path_obj))
        elif path_obj.is_file():
            # Open file with default app
            try:
                if os.name == 'nt':
                    os.startfile(str(path_obj))
                elif sys.platform == 'darwin':
                    import subprocess
                    subprocess.run(['open', str(path_obj)])
                else:
                    import subprocess
                    subprocess.run(['xdg-open', str(path_obj)])
            except Exception as e:
                logger.error(f"Failed to open file: {e}")


class FileExplorerMultiTab(QWidget):
    """
    Multi-tab File Explorer with breadcrumb navigation
    Features:
    - Multiple tabs for different folders
    - Breadcrumb navigation per tab
    - New tab, close tab, pin tab functionality
    - All FileExplorerCore features in each tab
    """
    
    def __init__(self):
        super().__init__()
        self.init_ui()
        
        # Create initial tab
        self.add_new_tab()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create header bar (app-level header above tabs)
        header_widget = QWidget()
        header_widget.setFixedHeight(8)
        header_widget.setStyleSheet("""
            QWidget {
                background-color: #1E5BA8;
            }
        """)
        layout.addWidget(header_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #B0C8E8;
                background-color: #E8F0FF;
            }
            QTabBar {
                background-color: #F5F8FC;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
                background-color: #D8E8FF;
                color: #0A1E5E;
                font-weight: 600;
                font-size: 11px;
                border: 1px solid #B0C8E8;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #6BA3E8;
                border-bottom: 3px solid #FFD700;
                color: #0A1E5E;
            }
            QTabBar::tab:!selected {
                background-color: #D8E8FF;
                color: #5a6c7d;
            }
            QTabBar::tab:hover {
                background-color: #C8DFFF;
            }
        """)
        self.tab_widget.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self.show_tab_bar_context_menu)
        
        # Tab bar controls
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        
        layout.addWidget(self.tab_widget)
        
        # Keyboard shortcuts (TODO: implement)
        # Ctrl+T: New tab
        # Ctrl+W: Close tab
        # Ctrl+Tab: Next tab
        # Ctrl+Shift+Tab: Previous tab
    
    def show_tab_bar_context_menu(self, pos):
        """Show context menu for the tab bar.

        - Right-click a tab: offer Duplicate (open new tab at same folder)
        - Right-click empty space: offer New Tab
        """
        tab_bar = self.tab_widget.tabBar()
        tab_index = tab_bar.tabAt(pos)

        menu = QMenu(self)
        if tab_index >= 0:
            duplicate_action = QAction("Duplicate", self)
            duplicate_action.triggered.connect(lambda _: self.duplicate_tab(tab_index))
            menu.addAction(duplicate_action)
        else:
            new_tab_action = QAction("New Tab", self)
            new_tab_action.triggered.connect(lambda _: self.add_new_tab())
            menu.addAction(new_tab_action)

        menu.exec(tab_bar.mapToGlobal(pos))

    def duplicate_tab(self, index: int) -> None:
        """Duplicate the given tab into a new tab at the same folder."""
        try:
            widget = self.tab_widget.widget(index)
            if widget is None:
                return

            # Prefer the tab's current directory (kept in sync with breadcrumb)
            path = getattr(widget, 'current_directory', None)
            if not path:
                path = getattr(widget, 'current_details_folder', None)

            title = self.tab_widget.tabText(index)
            self.add_new_tab(path=path, title=title)
        except Exception as e:
            logger.error(f"Failed to duplicate tab: {e}")

    def add_new_tab(self, path=None, title=None):
        """Add a new tab"""
        # Create new tab - if no path specified, stay at root Quick Links level
        explorer_tab = FileExplorerTab(initial_path=path)
        
        # Determine tab title
        if title is None:
            if path:
                path_obj = Path(path)
                title = path_obj.name if path_obj.name else str(path)
            else:
                title = "Quick Links"
        
        # Add tab
        index = self.tab_widget.addTab(explorer_tab, title)
        self.tab_widget.setCurrentIndex(index)
        self._style_close_button(index)
        
        # Connect path changes to update tab title
        explorer_tab.path_changed.connect(
            lambda p: self.update_tab_title(explorer_tab, p)
        )
        
        return explorer_tab
    
    def close_tab(self, index):
        """Close a tab"""
        # Don't close if it's the last tab
        if self.tab_widget.count() <= 1:
            return
        
        # Get the widget before removing it
        widget = self.tab_widget.widget(index)
        
        # Disconnect signals to prevent crashes during cleanup
        if widget:
            try:
                # Disconnect depth level combo signal to prevent it firing during deletion
                if hasattr(widget, 'depth_level_combo'):
                    widget.depth_level_combo.currentTextChanged.disconnect()
                
                # Disconnect path changed signal
                if hasattr(widget, 'path_changed'):
                    widget.path_changed.disconnect()
                
                # Disconnect other signals that might reference the widget
                if hasattr(widget, 'details_search'):
                    widget.details_search.textChanged.disconnect()
                
                # If depth search is enabled, turn it off before closing
                if hasattr(widget, 'depth_search_enabled') and widget.depth_search_enabled:
                    widget.depth_search_enabled = False
                    widget.depth_search_locked = False
                    widget.depth_search_active_results = None
                
            except Exception as e:
                logger.error(f"Error disconnecting signals during tab close: {e}")
        
        # Now remove the tab
        self.tab_widget.removeTab(index)
        
        # Delete the widget to free resources
        if widget:
            widget.deleteLater()
    
    def update_tab_title(self, tab_widget, path):
        """Update tab title when path changes"""
        index = self.tab_widget.indexOf(tab_widget)
        if index >= 0:
            path_obj = Path(path)
            title = path_obj.name if path_obj.name else str(path)
            self.tab_widget.setTabText(index, title)
            self.tab_widget.setTabToolTip(index, str(path))
    
    def get_current_tab(self):
        """Get currently active tab"""
        return self.tab_widget.currentWidget()
    
    def navigate_to_bookmark_folder(self, folder_path):
        """Navigate the current tab to a bookmark folder"""
        current_tab = self.get_current_tab()
        if current_tab and hasattr(current_tab, 'navigate_to_bookmark_folder'):
            current_tab.navigate_to_bookmark_folder(folder_path)

    def _style_close_button(self, index):
        """Make the tab close button a subtle gold X instead of the default red icon."""
        tab_bar = self.tab_widget.tabBar()
        close_btn = QToolButton(tab_bar)
        close_btn.setAutoRaise(True)
        close_btn.setText("X")
        close_btn.setToolTip("Close Tab")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            """
            QToolButton {
                background: transparent;
                color: #FFD700;
                border: none;
                font-size: 12px;
                font-weight: 700;
                padding: 0px;
                min-width: 14px;
            }
            QToolButton:hover {
                color: #FFE066;
            }
            """
        )
        close_btn.clicked.connect(lambda _: self._emit_close_for_button(close_btn))
        tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, close_btn)

    def _emit_close_for_button(self, button):
        """Map custom close button clicks to the correct tab index."""
        tab_bar = self.tab_widget.tabBar()
        for idx in range(tab_bar.count()):
            if tab_bar.tabButton(idx, QTabBar.ButtonPosition.RightSide) is button:
                self.tab_widget.tabCloseRequested.emit(idx)
                return
