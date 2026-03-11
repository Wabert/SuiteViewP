"""Data Package Screen - Visual query builder with compact table-based layout"""

import logging
import re
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
                              QTreeWidget, QTreeWidgetItem, QTabWidget, QPushButton,
                              QScrollArea, QFrame, QLineEdit, QComboBox, QCheckBox,
                              QMessageBox, QInputDialog, QToolBar, QSizePolicy,
                              QMenu, QToolButton, QTableWidget, QTableWidgetItem,
                              QHeaderView, QAbstractItemView, QStyledItemDelegate,
                              QApplication, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QPoint
from PyQt6.QtGui import QDrag, QAction, QColor, QBrush, QPainter, QPen

from suiteview.data.repositories import (SavedTableRepository, ConnectionRepository,
                                         get_metadata_cache_repository, get_query_repository)
from suiteview.core.schema_discovery import SchemaDiscovery
from suiteview.core.query_builder import QueryBuilder
from suiteview.core.query_executor import QueryExecutor
from suiteview.ui import theme

logger = logging.getLogger(__name__)


class ComboBoxDelegate(QStyledItemDelegate):
    """Delegate for dropdown columns in the table - opens dropdown on first click"""
    
    def __init__(self, items: list, parent=None):
        super().__init__(parent)
        self.items = items
    
    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems(self.items)
        # Make combo fill the cell completely
        combo.setStyleSheet("""
            QComboBox {
                border: none;
                padding: 0px 2px;
                margin: 0px;
                background: white;
            }
            QComboBox::drop-down {
                width: 16px;
            }
        """)
        # Auto-open the dropdown when editor is created
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, combo.showPopup)
        return combo
    
    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.DisplayRole)
        idx = editor.findText(value)
        if idx >= 0:
            editor.setCurrentIndex(idx)
    
    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)
    
    def updateEditorGeometry(self, editor, option, index):
        """Make editor fill the entire cell"""
        editor.setGeometry(option.rect)
    
    def paint(self, painter, option, index):
        """Draw a combobox-like appearance even when not editing"""
        # Draw the text
        super().paint(painter, option, index)
        
        # Draw dropdown arrow indicator on right side
        rect = option.rect
        arrow_rect = rect.adjusted(rect.width() - 16, 0, 0, 0)
        painter.save()
        painter.setPen(QColor("#888888"))
        # Draw a small triangle
        center_y = arrow_rect.center().y()
        center_x = arrow_rect.center().x()
        painter.drawLine(center_x - 3, center_y - 2, center_x, center_y + 2)
        painter.drawLine(center_x, center_y + 2, center_x + 3, center_y - 2)
        painter.restore()


class LineEditDelegate(QStyledItemDelegate):
    """Delegate for text input that fills the cell completely"""
    
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setStyleSheet("""
            QLineEdit {
                border: 1px solid #0078d4;
                padding: 0px;
                margin: 0px;
                background: white;
            }
        """)
        editor.setFrame(False)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setTextMargins(2, 0, 2, 0)  # Small left/right margin for text readability
        return editor
    
    def updateEditorGeometry(self, editor, option, index):
        """Make editor fill the entire cell with no margins"""
        editor.setGeometry(option.rect)
    
    def setEditorData(self, editor, index):
        value = index.data(Qt.ItemDataRole.DisplayRole) or ""
        editor.setText(value)
    
    def setModelData(self, editor, model, index):
        model.setData(index, editor.text(), Qt.ItemDataRole.EditRole)


class ReadOnlyDelegate(QStyledItemDelegate):
    """Delegate for read-only text that fills the cell completely with no padding"""
    
    def paint(self, painter, option, index):
        """Draw text with no padding"""
        from PyQt6.QtWidgets import QStyle
        
        painter.save()
        
        # Handle selection background
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#E8F0FF"))
            painter.setPen(QColor("#1E3A8A"))
        else:
            painter.setPen(QColor("#000000"))
        
        # Draw text with minimal padding
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        text_rect = option.rect.adjusted(4, 0, -2, 0)  # Small left padding for readability
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        
        painter.restore()


class DraggableFieldTree(QTreeWidget):
    """Tree widget that supports dragging fields to the tables"""
    
    field_dropped = pyqtSignal(dict, int)  # field_data, row_index (-1 for append)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
    
    def startDrag(self, supportedActions):
        """Start drag with field data"""
        item = self.currentItem()
        if not item:
            return
        
        # Get field data from item
        field_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not field_data:
            return
        
        drag = QDrag(self)
        mime_data = QMimeData()
        # Store field info in mime data
        field_info = f"{field_data.get('table_name', '')}.{field_data.get('field_name', '')}"
        mime_data.setText(field_info)
        mime_data.setData("application/x-field-data", str(field_data).encode())
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)


class DraggableVerticalHeader(QHeaderView):
    """Vertical header that supports drag and drop row reordering"""
    
    drag_started = pyqtSignal(int)  # row being dragged
    row_dropped = pyqtSignal(int, int)  # from_row, to_row
    
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)
        self._drag_start_pos = None
        self._drag_row = -1
        self._drop_indicator_row = -1
        self.setSectionsClickable(True)
        self.setHighlightSections(True)
        self.setAcceptDrops(True)  # Accept drops on the header too
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._drag_row = self.logicalIndexAt(event.position().toPoint())
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if (self._drag_start_pos is not None and 
            self._drag_row >= 0 and
            event.buttons() & Qt.MouseButton.LeftButton):
            # Check if we've moved enough to start a drag
            diff = event.position().toPoint() - self._drag_start_pos
            if diff.manhattanLength() > 10:  # Drag threshold
                self._start_drag()
                return
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self._drag_row = -1
        super().mouseReleaseEvent(event)
    
    def _start_drag(self):
        """Start the drag operation"""
        if self._drag_row < 0:
            return
        
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData("application/x-row-reorder", str(self._drag_row).encode())
        drag.setMimeData(mime_data)
        
        # Emit signal so table can track which row is being dragged
        self.drag_started.emit(self._drag_row)
        
        # Execute drag
        result = drag.exec(Qt.DropAction.MoveAction)
        
        # Reset
        self._drag_start_pos = None
        self._drag_row = -1
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-row-reorder"):
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-row-reorder"):
            # Calculate drop row from y position
            self._drop_indicator_row = self.logicalIndexAt(event.position().toPoint())
            if self._drop_indicator_row == -1:
                # Below all rows - use row count
                self._drop_indicator_row = self.count()
            self.viewport().update()
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        self._drop_indicator_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        self._drop_indicator_row = -1
        self.viewport().update()
        
        if event.mimeData().hasFormat("application/x-row-reorder"):
            from_row = int(event.mimeData().data("application/x-row-reorder").data().decode())
            to_row = self.logicalIndexAt(event.position().toPoint())
            if to_row == -1:
                to_row = self.count()
            
            if from_row != to_row and from_row != to_row - 1:
                self.row_dropped.emit(from_row, to_row)
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def paintEvent(self, event):
        """Paint with drop indicator"""
        super().paintEvent(event)
        
        if self._drop_indicator_row >= 0:
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor("#0078d4"), 2))
            
            if self._drop_indicator_row < self.count():
                y = self.sectionViewportPosition(self._drop_indicator_row)
            else:
                # At the end
                if self.count() > 0:
                    y = self.sectionViewportPosition(self.count() - 1) + self.sectionSize(self.count() - 1)
                else:
                    y = 0
            
            painter.drawLine(0, y, self.width(), y)
            painter.end()


class ReorderableTableWidget(QTableWidget):
    """Table widget that accepts field drops and supports row reordering via vertical header drag.
    
    Features:
    - Drag rows by clicking and dragging the row number (vertical header)
    - Drop to insert row at new position (other rows shift)
    - Right-click on row number for context menu (Move Up/Down/Delete)
    - External field drops still work
    """
    
    field_added = pyqtSignal(dict, int)  # field_data, row_index
    row_reordered = pyqtSignal(int, int)  # from_row, to_row (insert position)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        self._dragging_row = -1
        self._drop_indicator_row = -1
        
        # Replace default vertical header with draggable one
        self._drag_header = DraggableVerticalHeader(self)
        self.setVerticalHeader(self._drag_header)
        self._drag_header.drag_started.connect(self._on_drag_started)
        # Forward the header's row_dropped signal through our row_reordered signal
        self._drag_header.row_dropped.connect(self.row_reordered.emit)
    
    def _on_drag_started(self, row):
        """Track which row is being dragged"""
        self._dragging_row = row
        self.selectRow(row)
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-row-reorder"):
            event.acceptProposedAction()
        elif event.mimeData().hasFormat("application/x-field-data"):
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-row-reorder"):
            # Show drop indicator
            drop_row = self.rowAt(int(event.position().y()))
            if drop_row == -1:
                drop_row = self.rowCount()
            self._drop_indicator_row = drop_row
            self.viewport().update()
            event.acceptProposedAction()
        elif event.mimeData().hasFormat("application/x-field-data"):
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        self._drop_indicator_row = -1
        self.viewport().update()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        self._drop_indicator_row = -1
        self.viewport().update()
        
        if event.mimeData().hasFormat("application/x-row-reorder"):
            # Row reorder
            from_row = int(event.mimeData().data("application/x-row-reorder").data().decode())
            to_row = self.rowAt(int(event.position().y()))
            if to_row == -1:
                to_row = self.rowCount()
            
            if from_row != to_row and from_row != to_row - 1:
                self.row_reordered.emit(from_row, to_row)
            event.acceptProposedAction()
            
        elif event.mimeData().hasFormat("application/x-field-data"):
            # External field drop
            drop_row = self.rowAt(int(event.position().y()))
            if drop_row == -1:
                drop_row = self.rowCount()
            
            data_bytes = event.mimeData().data("application/x-field-data")
            try:
                field_data = eval(data_bytes.data().decode())
                self.field_added.emit(field_data, drop_row)
            except:
                pass
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def paintEvent(self, event):
        """Paint with drop indicator line"""
        super().paintEvent(event)
        
        if self._drop_indicator_row >= 0:
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor("#0078d4"), 2))
            
            if self._drop_indicator_row < self.rowCount():
                # Draw line above the target row
                rect = self.visualRect(self.model().index(self._drop_indicator_row, 0))
                y = rect.top()
            else:
                # Draw line at the bottom
                if self.rowCount() > 0:
                    rect = self.visualRect(self.model().index(self.rowCount() - 1, 0))
                    y = rect.bottom()
                else:
                    y = 0
            
            painter.drawLine(0, y, self.viewport().width(), y)
            painter.end()


class DroppableTableWidget(QTableWidget):
    """Table widget that accepts field drops and supports row reordering (legacy)"""
    
    field_added = pyqtSignal(dict, int)  # field_data, row_index
    row_moved = pyqtSignal(int, int)  # from_row, to_row
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._drag_row = -1
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-field-data"):
            event.acceptProposedAction()
        elif event.source() == self:
            # Internal row reorder
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        if event.mimeData().hasText() or event.mimeData().hasFormat("application/x-field-data"):
            event.acceptProposedAction()
        elif event.source() == self:
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event):
        if event.source() == self:
            # Internal row reorder
            drop_row = self.rowAt(event.position().toPoint().y())
            if drop_row == -1:
                drop_row = self.rowCount()
            if self._drag_row != -1 and self._drag_row != drop_row:
                self.row_moved.emit(self._drag_row, drop_row)
            self._drag_row = -1
            event.acceptProposedAction()
        elif event.mimeData().hasFormat("application/x-field-data"):
            # External field drop
            drop_row = self.rowAt(event.position().toPoint().y())
            if drop_row == -1:
                drop_row = self.rowCount()
            
            data_bytes = event.mimeData().data("application/x-field-data")
            try:
                field_data = eval(data_bytes.data().decode())
                self.field_added.emit(field_data, drop_row)
            except:
                pass
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_row = self.rowAt(event.position().toPoint().y())


class DataPackageScreen(QWidget):
    """Data Package screen with visual query builder - compact table layout"""
    
    # Signal when data packages change
    packages_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.saved_table_repo = SavedTableRepository()
        self.conn_repo = ConnectionRepository()
        self.schema_discovery = SchemaDiscovery()
        self.metadata_cache_repo = get_metadata_cache_repository()
        self.query_repo = get_query_repository()
        self.query_builder = QueryBuilder()
        self.query_executor = QueryExecutor()

        # Track current state
        self.current_connection_id = None
        self.current_database_name = None
        self.current_table_name = None
        self.current_schema_name = None
        self.current_package_name = None
        self.current_package_id = None

        # Track package components
        self.display_fields = []  # List of display field configs
        self.criteria_fields = []  # List of criteria configs
        self.tables_involved = set()
        
        # Cache for unique values (keyed by "table_name.field_name")
        self.unique_values_cache = {}
        
        # View mode toggle
        self._compact_view = True  # Default to compact table view

        self.init_ui()
        self.load_data_sources()

    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter for panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Panel 1 - Data Packages (saved packages list)
        panel1 = self._create_packages_panel()
        panel1.setMinimumWidth(150)
        splitter.addWidget(panel1)

        # Panel 2 - Data Source (cascading dropdown + tables)
        panel2 = self._create_data_source_panel()
        panel2.setMinimumWidth(150)
        splitter.addWidget(panel2)

        # Panel 3 - Fields
        panel3 = self._create_fields_panel()
        panel3.setMinimumWidth(150)
        splitter.addWidget(panel3)

        # Panel 4 - Query Builder (tabs)
        right_panel = self._create_query_builder_panel()
        right_panel.setMinimumWidth(400)
        splitter.addWidget(right_panel)

        # Set initial sizes
        splitter.setSizes([180, 180, 180, 700])

        layout.addWidget(splitter)

    def _create_packages_panel(self) -> QWidget:
        """Create left panel with saved data packages"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header - styled like DATA SOURCE and FIELDS
        header = QPushButton("DATA PACKAGES")
        header.setObjectName("section_header")
        header.setEnabled(False)  # Just a label, not clickable
        panel_layout.addWidget(header)
        
        # New button row
        new_btn_container = QWidget()
        new_btn_layout = QHBoxLayout(new_btn_container)
        new_btn_layout.setContentsMargins(4, 4, 4, 4)
        new_btn_layout.setSpacing(0)
        
        self.new_package_btn = QPushButton("+ New")
        self.new_package_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFD700;
                color: #0A1E5E;
                padding: 4px 12px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 11px;
                border: none;
            }
            QPushButton:hover {
                background-color: #FFC107;
            }
        """)
        self.new_package_btn.clicked.connect(self._new_package)
        new_btn_layout.addWidget(self.new_package_btn)
        new_btn_layout.addStretch()
        panel_layout.addWidget(new_btn_container)

        # Packages tree
        self.packages_tree = QTreeWidget()
        self.packages_tree.setObjectName("sidebar_tree")
        self.packages_tree.setHeaderHidden(True)
        self.packages_tree.itemClicked.connect(self._on_package_clicked)
        self.packages_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.packages_tree.customContextMenuRequested.connect(self._show_package_context_menu)
        panel_layout.addWidget(self.packages_tree)

        return panel

    def _create_data_source_panel(self) -> QWidget:
        """Create panel with cascading data source selection and tables"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header
        header = QPushButton("DATA SOURCE")
        header.setObjectName("section_header")
        header.setEnabled(False)
        panel_layout.addWidget(header)

        # Compact style for combos
        compact_combo_style = """
            QComboBox {
                padding: 2px 4px;
                min-height: 18px;
                font-size: 11px;
            }
            QLabel {
                font-size: 11px;
            }
        """

        # Cascading dropdowns container - compact
        dropdown_container = QWidget()
        dropdown_layout = QVBoxLayout(dropdown_container)
        dropdown_layout.setContentsMargins(4, 4, 4, 4)
        dropdown_layout.setSpacing(2)

        # Database type dropdown (DB2, SQL_SERVER, etc.)
        type_row = QHBoxLayout()
        type_row.setSpacing(4)
        type_label = QLabel("Type:")
        type_label.setFixedWidth(35)
        type_label.setStyleSheet("font-size: 11px;")
        self.db_type_combo = QComboBox()
        self.db_type_combo.setStyleSheet(compact_combo_style)
        self.db_type_combo.currentTextChanged.connect(self._on_db_type_changed)
        type_row.addWidget(type_label)
        type_row.addWidget(self.db_type_combo)
        dropdown_layout.addLayout(type_row)

        # Connection dropdown (cascades from type)
        conn_row = QHBoxLayout()
        conn_row.setSpacing(4)
        conn_label = QLabel("Conn:")
        conn_label.setFixedWidth(35)
        conn_label.setStyleSheet("font-size: 11px;")
        self.connection_combo = QComboBox()
        self.connection_combo.setStyleSheet(compact_combo_style)
        self.connection_combo.currentTextChanged.connect(self._on_connection_changed)
        conn_row.addWidget(conn_label)
        conn_row.addWidget(self.connection_combo)
        dropdown_layout.addLayout(conn_row)

        panel_layout.addWidget(dropdown_container)

        # Subtle separator line instead of TABLES header
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.Shape.HLine)
        separator1.setStyleSheet("background-color: #B0C8E8; max-height: 1px;")
        panel_layout.addWidget(separator1)

        # Search box - compact
        self.tables_search = QLineEdit()
        self.tables_search.setPlaceholderText("Search tables...")
        self.tables_search.setStyleSheet("padding: 3px 6px; margin: 2px 4px; font-size: 11px;")
        self.tables_search.textChanged.connect(self._filter_tables)
        panel_layout.addWidget(self.tables_search)

        # Another subtle separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setStyleSheet("background-color: #B0C8E8; max-height: 1px;")
        panel_layout.addWidget(separator2)

        # Tables list - pale blue like left panel
        self.tables_tree = QTreeWidget()
        self.tables_tree.setHeaderHidden(True)
        self.tables_tree.setIndentation(15)
        self.tables_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #E8F0FF;
                border: none;
                font-size: 11px;
                outline: 0;
            }
            QTreeWidget::item {
                padding: 2px 4px;
                border: none;
                background-color: transparent;
            }
            QTreeWidget::item:hover {
                background-color: #D8E8FF;
            }
            QTreeWidget::item:selected {
                background-color: #2563EB;
                color: #FFD700;
            }
        """)
        self.tables_tree.itemClicked.connect(self._on_table_clicked)
        panel_layout.addWidget(self.tables_tree)

        # Info label - compact
        self.tables_info = QLabel("Select a data source")
        self.tables_info.setStyleSheet("color: #7f8c8d; font-size: 9px; padding: 2px 4px;")
        panel_layout.addWidget(self.tables_info)

        return panel

    def _create_fields_panel(self) -> QWidget:
        """Create panel with fields list (draggable)"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header
        header = QPushButton("FIELDS")
        header.setObjectName("section_header")
        header.setEnabled(False)
        panel_layout.addWidget(header)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #B0C8E8; max-height: 1px;")
        panel_layout.addWidget(separator)

        # Search box - compact
        self.fields_search = QLineEdit()
        self.fields_search.setPlaceholderText("Search fields...")
        self.fields_search.setStyleSheet("padding: 3px 6px; margin: 2px 4px; font-size: 11px;")
        self.fields_search.textChanged.connect(self._filter_fields)
        panel_layout.addWidget(self.fields_search)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setStyleSheet("background-color: #B0C8E8; max-height: 1px;")
        panel_layout.addWidget(separator2)

        # Fields tree (draggable) - pale blue like left panel
        self.fields_tree = DraggableFieldTree()
        self.fields_tree.setHeaderHidden(True)
        self.fields_tree.setIndentation(15)
        self.fields_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #E8F0FF;
                border: none;
                font-size: 11px;
                outline: 0;
            }
            QTreeWidget::item {
                padding: 2px 4px;
                border: none;
                background-color: transparent;
            }
            QTreeWidget::item:hover {
                background-color: #D8E8FF;
            }
            QTreeWidget::item:selected {
                background-color: #2563EB;
                color: #FFD700;
            }
        """)
        self.fields_tree.itemDoubleClicked.connect(self._on_field_double_clicked)
        panel_layout.addWidget(self.fields_tree)

        # Info label - compact
        self.fields_info = QLabel("Select a table")
        self.fields_info.setStyleSheet("color: #7f8c8d; font-size: 9px; padding: 2px 4px;")
        panel_layout.addWidget(self.fields_info)

        return panel

    def _create_query_builder_panel(self) -> QWidget:
        """Create right panel with query builder tabs"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(2, 2, 2, 2)
        panel_layout.setSpacing(2)

        # Compact button style
        compact_btn_style = """
            QPushButton {
                padding: 4px 10px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 11px;
            }
        """

        # Toolbar with actions - compact
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        
        # Package name label - prominent, on the left
        self.package_name_label = QLabel("New Package")
        self.package_name_label.setStyleSheet("""
            font-weight: bold;
            color: #0A1E5E;
            font-size: 14px;
            padding: 2px 8px;
            background-color: #E8F0FF;
            border: 1px solid #B0C8E8;
            border-radius: 3px;
        """)
        toolbar.addWidget(self.package_name_label)
        
        toolbar.addStretch()
        
        # Save button
        self.save_btn = QPushButton("💾 Save")
        self.save_btn.setStyleSheet(compact_btn_style + """
            QPushButton {
                background-color: #e74c3c;
                color: white;
            }
            QPushButton:hover { background-color: #c0392b; }
        """)
        self.save_btn.clicked.connect(self._save_package)
        toolbar.addWidget(self.save_btn)

        # Save As button (was Reset)
        self.save_as_btn = QPushButton("📋 Save As")
        self.save_as_btn.setStyleSheet(compact_btn_style + """
            QPushButton {
                background-color: #9b59b6;
                color: white;
            }
            QPushButton:hover { background-color: #8e44ad; }
        """)
        self.save_as_btn.clicked.connect(self._save_as_package)
        toolbar.addWidget(self.save_as_btn)

        panel_layout.addLayout(toolbar)

        # Tab widget - styled like DB Query
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #B0C8E8;
                background-color: #E8F0FF;
            }
            QTabBar {
                background-color: #E8F0FF;
            }
            QTabBar::tab {
                padding: 6px 14px;
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
                border-bottom: 2px solid #FFD700;
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
        
        # Display tab
        display_tab = self._create_display_tab()
        self.tabs.addTab(display_tab, "Display")

        # Criteria tab
        criteria_tab = self._create_criteria_tab()
        self.tabs.addTab(criteria_tab, "Criteria")

        # Tables tab
        tables_tab = self._create_tables_tab()
        self.tabs.addTab(tables_tab, "Tables")

        # Query Statement tab
        query_tab = self._create_query_statement_tab()
        self.tabs.addTab(query_tab, "Query Statement")
        
        # Connect tab change to update indicators
        self.tabs.currentChanged.connect(self._on_tab_changed)

        panel_layout.addWidget(self.tabs)

        return panel
    
    def _on_tab_changed(self, index: int):
        """Handle tab change - update field/table indicators"""
        self._update_field_indicators()
        self.update_table_indicators()

    def _create_display_tab(self) -> QWidget:
        """Create Display tab with compact table view"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Data source label row - shows Type and Connection
        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        self.display_source_label = QLabel("No data source selected")
        self.display_source_label.setStyleSheet("""
            font-size: 11px;
            font-weight: bold;
            color: #1E3A8A;
            padding: 2px 6px;
            background-color: #E8F0FF;
            border-radius: 3px;
        """)
        source_row.addWidget(self.display_source_label)
        source_row.addStretch()
        layout.addLayout(source_row)

        # Toggle button for view mode - compact with good contrast
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(4)
        hint_label = QLabel("Drag fields here to add to SELECT list")
        hint_label.setStyleSheet("font-size: 10px; color: #5a6c7d;")
        toggle_row.addWidget(hint_label)
        toggle_row.addStretch()
        
        self.view_toggle_btn = QPushButton("☰ Tile View")
        self.view_toggle_btn.setCheckable(True)
        self.view_toggle_btn.setStyleSheet("""
            QPushButton {
                padding: 2px 8px;
                font-size: 10px;
                background-color: #D8E8FF;
                color: #0A1E5E;
                border: 1px solid #6BA3E8;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #C8DFFF;
            }
            QPushButton:checked {
                background-color: #6BA3E8;
                color: white;
            }
        """)
        self.view_toggle_btn.clicked.connect(self._toggle_display_view)
        toggle_row.addWidget(self.view_toggle_btn)
        
        layout.addLayout(toggle_row)

        # Stacked container for both views
        self.display_stack = QWidget()
        stack_layout = QVBoxLayout(self.display_stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)

        # Compact table view (default) - uses ReorderableTableWidget for drag reorder from row numbers
        self.display_table = ReorderableTableWidget()
        self.display_table.setColumnCount(6)
        self.display_table.setHorizontalHeaderLabels(["Field Name", "Table", "Alias", "Agg", "Order", "Having"])
        
        # Make all columns resizable (Interactive mode)
        header = self.display_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        # Set initial column widths
        self.display_table.setColumnWidth(0, 180)  # Field Name
        self.display_table.setColumnWidth(1, 120)  # Table
        self.display_table.setColumnWidth(2, 100)  # Alias
        self.display_table.setColumnWidth(3, 70)   # Agg
        self.display_table.setColumnWidth(4, 70)   # Order
        # Having stretches to fill
        
        # Style the table with light grey headers like My Data
        self.display_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #d0d0d0;
                selection-background-color: #E8F0FF;
                selection-color: #1E3A8A;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 0px;
                margin: 0px;
            }
            QTableWidget::item:selected {
                background-color: #E8F0FF;
                color: #1E3A8A;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #000000;
                padding: 4px 6px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        
        # Style vertical header (row numbers) with same light grey and drag cursor
        v_header = self.display_table.verticalHeader()
        v_header.setStyleSheet("""
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #000000;
                padding: 2px 4px;
                border: 1px solid #d0d0d0;
                font-size: 11px;
                min-width: 24px;
            }
            QHeaderView::section:hover {
                background-color: #e0e0e0;
                cursor: grab;
            }
        """)
        v_header.setDefaultSectionSize(26)  # Row height
        v_header.setCursor(Qt.CursorShape.OpenHandCursor)  # Indicate draggable
        
        # Set up delegates for all text columns (fill cell completely)
        # Field Name and Table use LineEditDelegate for proper text display
        field_name_delegate = LineEditDelegate(self.display_table)
        self.display_table.setItemDelegateForColumn(0, field_name_delegate)
        
        table_delegate = LineEditDelegate(self.display_table)
        self.display_table.setItemDelegateForColumn(1, table_delegate)
        
        alias_delegate = LineEditDelegate(self.display_table)
        self.display_table.setItemDelegateForColumn(2, alias_delegate)
        
        having_delegate = LineEditDelegate(self.display_table)
        self.display_table.setItemDelegateForColumn(5, having_delegate)
        
        # Agg and Order columns will use embedded combobox widgets (setCellWidget)
        # This is handled in _add_display_field method
        
        # Make cells editable on single click
        self.display_table.setEditTriggers(
            QAbstractItemView.EditTrigger.CurrentChanged | 
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        
        # Connect signals
        self.display_table.field_added.connect(self._add_display_field)
        self.display_table.row_reordered.connect(self._insert_display_row)
        
        # Set up context menu for vertical header (row numbers) only
        self.display_table.verticalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.display_table.verticalHeader().customContextMenuRequested.connect(self._show_row_context_menu)
        
        # Enable keyboard shortcuts
        self.display_table.keyPressEvent = self._display_table_key_press
        
        stack_layout.addWidget(self.display_table)
        
        # Row action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        action_row.addStretch()
        
        move_up_btn = QPushButton("⬆")
        move_up_btn.setToolTip("Move selected row up")
        move_up_btn.setFixedSize(28, 24)
        move_up_btn.setStyleSheet("font-size: 12px; padding: 2px;")
        move_up_btn.clicked.connect(self._move_selected_row_up)
        action_row.addWidget(move_up_btn)
        
        move_down_btn = QPushButton("⬇")
        move_down_btn.setToolTip("Move selected row down")
        move_down_btn.setFixedSize(28, 24)
        move_down_btn.setStyleSheet("font-size: 12px; padding: 2px;")
        move_down_btn.clicked.connect(self._move_selected_row_down)
        action_row.addWidget(move_down_btn)
        
        delete_btn = QPushButton("🗑")
        delete_btn.setToolTip("Delete selected row (Del)")
        delete_btn.setFixedSize(28, 24)
        delete_btn.setStyleSheet("font-size: 12px; padding: 2px;")
        delete_btn.clicked.connect(self._delete_selected_row)
        action_row.addWidget(delete_btn)
        
        stack_layout.addLayout(action_row)

        # Tile view (hidden by default) - placeholder for now
        self.display_tile_scroll = QScrollArea()
        self.display_tile_scroll.setWidgetResizable(True)
        self.display_tile_scroll.setVisible(False)
        self.display_tile_container = QWidget()
        self.display_tile_layout = QVBoxLayout(self.display_tile_container)
        self.display_tile_scroll.setWidget(self.display_tile_container)
        stack_layout.addWidget(self.display_tile_scroll)

        layout.addWidget(self.display_stack)

        return tab

    def _create_criteria_tab(self) -> QWidget:
        """Create Criteria tab with compact table view - matching Display tab style"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        # Data source label row - shows Type and Connection (same as Display)
        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        self.criteria_source_label = QLabel("No data source selected")
        self.criteria_source_label.setStyleSheet("""
            font-size: 11px;
            font-weight: bold;
            color: #1E3A8A;
            padding: 2px 6px;
            background-color: #E8F0FF;
            border-radius: 3px;
        """)
        source_row.addWidget(self.criteria_source_label)
        source_row.addStretch()
        layout.addLayout(source_row)

        # Toggle button for view mode - compact with good contrast
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(4)
        hint_label = QLabel("Drag fields here to add filter criteria")
        hint_label.setStyleSheet("font-size: 10px; color: #5a6c7d;")
        toggle_row.addWidget(hint_label)
        toggle_row.addStretch()
        
        self.criteria_view_toggle = QPushButton("☰ Tile View")
        self.criteria_view_toggle.setCheckable(True)
        self.criteria_view_toggle.setStyleSheet("""
            QPushButton {
                padding: 2px 8px;
                font-size: 10px;
                background-color: #D8E8FF;
                color: #0A1E5E;
                border: 1px solid #6BA3E8;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #C8DFFF;
            }
            QPushButton:checked {
                background-color: #6BA3E8;
                color: white;
            }
        """)
        self.criteria_view_toggle.clicked.connect(self._toggle_criteria_view)
        toggle_row.addWidget(self.criteria_view_toggle)
        
        layout.addLayout(toggle_row)

        # Stacked container for both views
        self.criteria_stack = QWidget()
        stack_layout = QVBoxLayout(self.criteria_stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)

        # Compact table view - uses ReorderableTableWidget for drag reorder from row numbers
        # Columns: Field Name, Table, Data Type, Match Type, List (icon), Edit (pen icon), Value
        self.criteria_table = ReorderableTableWidget()
        self.criteria_table.setColumnCount(7)
        self.criteria_table.setHorizontalHeaderLabels(["Field Name", "Table", "Data Type", "Match Type", "☰", "✎", "Value"])
        
        # Make all columns resizable (Interactive mode)
        header = self.criteria_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        
        # Set initial column widths
        self.criteria_table.setColumnWidth(0, 140)  # Field Name
        self.criteria_table.setColumnWidth(1, 100)  # Table
        self.criteria_table.setColumnWidth(2, 80)   # Data Type
        self.criteria_table.setColumnWidth(3, 90)   # Match Type
        self.criteria_table.setColumnWidth(4, 30)   # List icon (small)
        self.criteria_table.setColumnWidth(5, 30)   # Edit icon (small)
        self.criteria_table.setColumnWidth(6, 200)  # Value
        
        # Stretch Value column (now column 6)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        
        # Style the table with light grey headers like Display
        self.criteria_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #d0d0d0;
                selection-background-color: #E8F0FF;
                selection-color: #1E3A8A;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 0px;
                margin: 0px;
            }
            QTableWidget::item:selected {
                background-color: #E8F0FF;
                color: #1E3A8A;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #000000;
                padding: 4px 6px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        
        # Style vertical header (row numbers) with same light grey and drag cursor
        v_header = self.criteria_table.verticalHeader()
        v_header.setStyleSheet("""
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #000000;
                padding: 2px 4px;
                border: 1px solid #d0d0d0;
                font-size: 11px;
                min-width: 24px;
            }
            QHeaderView::section:hover {
                background-color: #e0e0e0;
                cursor: grab;
            }
        """)
        v_header.setDefaultSectionSize(26)  # Row height
        v_header.setCursor(Qt.CursorShape.OpenHandCursor)  # Indicate draggable
        
        # Set up delegates for text columns
        field_name_delegate = LineEditDelegate(self.criteria_table)
        self.criteria_table.setItemDelegateForColumn(0, field_name_delegate)
        
        table_delegate = LineEditDelegate(self.criteria_table)
        self.criteria_table.setItemDelegateForColumn(1, table_delegate)
        
        # Value column (6) - editable with delegate (but may be replaced with custom widget for Range/Date)
        value_delegate = LineEditDelegate(self.criteria_table)
        self.criteria_table.setItemDelegateForColumn(6, value_delegate)
        
        # Data Type column (2) - read-only display
        # Match Type column (3) will use embedded combobox widgets (setCellWidget)
        # List column (4) will have a button widget
        # Edit column (5) will have a button widget
        # This is handled in _add_criteria_field method
        
        # Allow editing on Value column with CurrentChanged like Display table
        self.criteria_table.setEditTriggers(
            QAbstractItemView.EditTrigger.CurrentChanged |
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.SelectedClicked
        )
        
        # Connect cell changes to update SQL preview when Value column is edited
        self.criteria_table.cellChanged.connect(self._on_criteria_cell_changed)
        
        # Connect signals
        self.criteria_table.field_added.connect(self._add_criteria_field)
        self.criteria_table.row_reordered.connect(self._insert_criteria_row)
        
        # Set up context menu for vertical header (row numbers) only
        self.criteria_table.verticalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.criteria_table.verticalHeader().customContextMenuRequested.connect(self._show_criteria_row_context_menu)
        
        # Set up context menu for the table cells (for fetching unique values)
        self.criteria_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.criteria_table.customContextMenuRequested.connect(self._show_criteria_cell_context_menu)
        
        # Enable keyboard shortcuts
        self.criteria_table.keyPressEvent = self._criteria_table_key_press
        
        stack_layout.addWidget(self.criteria_table)
        
        # Row action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        action_row.addStretch()
        
        criteria_move_up_btn = QPushButton("⬆")
        criteria_move_up_btn.setToolTip("Move selected row up")
        criteria_move_up_btn.setFixedSize(28, 24)
        criteria_move_up_btn.setStyleSheet("font-size: 12px; padding: 2px;")
        criteria_move_up_btn.clicked.connect(self._move_selected_criteria_row_up)
        action_row.addWidget(criteria_move_up_btn)
        
        criteria_move_down_btn = QPushButton("⬇")
        criteria_move_down_btn.setToolTip("Move selected row down")
        criteria_move_down_btn.setFixedSize(28, 24)
        criteria_move_down_btn.setStyleSheet("font-size: 12px; padding: 2px;")
        criteria_move_down_btn.clicked.connect(self._move_selected_criteria_row_down)
        action_row.addWidget(criteria_move_down_btn)
        
        criteria_delete_btn = QPushButton("🗑")
        criteria_delete_btn.setToolTip("Delete selected row (Del)")
        criteria_delete_btn.setFixedSize(28, 24)
        criteria_delete_btn.setStyleSheet("font-size: 12px; padding: 2px;")
        criteria_delete_btn.clicked.connect(self._delete_selected_criteria_row)
        action_row.addWidget(criteria_delete_btn)
        
        stack_layout.addLayout(action_row)

        # Tile view (hidden by default)
        self.criteria_tile_scroll = QScrollArea()
        self.criteria_tile_scroll.setWidgetResizable(True)
        self.criteria_tile_scroll.setVisible(False)
        self.criteria_tile_container = QWidget()
        self.criteria_tile_layout = QVBoxLayout(self.criteria_tile_container)
        self.criteria_tile_scroll.setWidget(self.criteria_tile_container)
        stack_layout.addWidget(self.criteria_tile_scroll)

        layout.addWidget(self.criteria_stack)

        return tab

    def _create_tables_tab(self) -> QWidget:
        """Create Tables tab showing involved tables and JOINs"""
        tab = QWidget()
        tab.setStyleSheet("background-color: #E8F0FF;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # -------- Top: tables used list (auto-updating) --------
        used_frame = QFrame()
        used_frame.setStyleSheet("QFrame{border:1px solid #B0C8E8; background:#E8F0FF;}")
        used_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        used_frame.setMaximumHeight(175)
        used_layout = QVBoxLayout(used_frame)
        used_layout.setContentsMargins(6, 6, 6, 6)
        used_layout.setSpacing(4)

        used_title = QLabel("Tables Used (Display + Criteria)")
        used_title.setStyleSheet("font-weight: 600; font-size: 10px; padding: 0px; margin: 0px; color: #1B1B1B;")
        used_layout.addWidget(used_title)

        self.used_tables_list = QTreeWidget()
        self.used_tables_list.setHeaderHidden(True)
        self.used_tables_list.setRootIsDecorated(False)
        self.used_tables_list.setUniformRowHeights(True)
        self.used_tables_list.setIndentation(10)
        self.used_tables_list.setMaximumHeight(110)
        self.used_tables_list.setStyleSheet(
            "QTreeWidget{font-size:10px; border:none; background:#E8F0FF; outline:0;}"
            "QTreeWidget::item{padding:0px; margin:0px;}"
        )
        used_layout.addWidget(self.used_tables_list)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.setSpacing(4)

        self.manual_table_combo = QComboBox()
        self.manual_table_combo.setEditable(True)
        self.manual_table_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.manual_table_combo.setStyleSheet(
            "QComboBox{font-size:10px; padding:0px; margin:0px; border:1px solid #B0C8E8; background:#E8F0FF;}"
            "QComboBox::drop-down{width:16px; border:none;}"
        )
        add_row.addWidget(self.manual_table_combo, 1)

        self.manual_add_btn = QToolButton()
        self.manual_add_btn.setText("Add")
        self.manual_add_btn.setToolTip("Add a table manually")
        self.manual_add_btn.setAutoRaise(False)
        self.manual_add_btn.setStyleSheet(
            "QToolButton{font-size:10px; padding:2px 10px; margin:0px; color:#1B1B1B; background:#E8F0FF; border:1px solid #0078D4; border-radius:3px;}"
            "QToolButton:hover{background:#E6F0FF;}"
            "QToolButton:pressed{background:#E6F0FF;}"
        )
        self.manual_add_btn.clicked.connect(self._tables_tab_add_table_manually)
        add_row.addWidget(self.manual_add_btn)

        used_layout.addLayout(add_row)
        layout.addWidget(used_frame)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color:#B0C8E8; max-height:1px;")
        layout.addWidget(sep)

        # -------- Main: joins editor --------
        joins_title = QLabel("Joins")
        joins_title.setStyleSheet("font-weight: 600; font-size: 10px; padding: 0px; margin: 0px; color: #1B1B1B;")
        layout.addWidget(joins_title)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)

        self.join_add_btn = QToolButton()
        self.join_add_btn.setText("+ Join")
        self.join_add_btn.setToolTip("Add a JOIN")
        self.join_add_btn.setAutoRaise(False)
        self.join_add_btn.setStyleSheet(
            "QToolButton{font-size:10px; padding:2px 10px; margin:0px; color:#1B1B1B; background:#E8F0FF; border:1px solid #0078D4; border-radius:3px;}"
            "QToolButton:hover{background:#E6F0FF;}"
            "QToolButton:pressed{background:#E6F0FF;}"
        )
        self.join_add_btn.clicked.connect(self._joins_add_join)
        actions.addWidget(self.join_add_btn)

        self.on_add_btn = QToolButton()
        self.on_add_btn.setText("+ ON")
        self.on_add_btn.setToolTip("Add an ON condition")
        self.on_add_btn.setAutoRaise(False)
        self.on_add_btn.setStyleSheet(
            "QToolButton{font-size:10px; padding:2px 10px; margin:0px; color:#1B1B1B; background:#E8F0FF; border:1px solid #0078D4; border-radius:3px;}"
            "QToolButton:hover{background:#E6F0FF;}"
            "QToolButton:pressed{background:#E6F0FF;}"
        )
        self.on_add_btn.clicked.connect(self._joins_add_on)
        actions.addWidget(self.on_add_btn)

        self.join_del_btn = QToolButton()
        self.join_del_btn.setText("Del")
        self.join_del_btn.setToolTip("Delete selected join/ON")
        self.join_del_btn.setAutoRaise(False)
        self.join_del_btn.setStyleSheet(
            "QToolButton{font-size:10px; padding:2px 10px; margin:0px; color:#1B1B1B; background:#E8F0FF; border:1px solid #0078D4; border-radius:3px;}"
            "QToolButton:hover{background:#E6F0FF;}"
            "QToolButton:pressed{background:#E6F0FF;}"
        )
        self.join_del_btn.clicked.connect(self._joins_delete_selected)
        actions.addWidget(self.join_del_btn)

        actions.addStretch()
        layout.addLayout(actions)

        self.joins_tree = QTreeWidget()
        self.joins_tree.setColumnCount(3)
        self.joins_tree.setHeaderLabels(["Left", "Join / =", "Right"])
        self.joins_tree.setIndentation(12)
        self.joins_tree.setRootIsDecorated(True)
        self.joins_tree.setUniformRowHeights(True)
        self.joins_tree.setStyleSheet(
            "QTreeWidget{font-size:10px; border:1px solid #B0C8E8; background:#E8F0FF; outline:0;}"
            "QHeaderView::section{padding:0px 6px; font-size:10px;}"
            "QTreeWidget::item{padding:0px; margin:0px;}"
        )
        self.joins_tree.currentItemChanged.connect(lambda *_: self._joins_update_action_state())
        layout.addWidget(self.joins_tree)

        header = self.joins_tree.header()
        header.setStretchLastSection(True)
        header.resizeSection(0, 260)
        header.resizeSection(1, 110)

        self._joins_updating = False
        self._tables_tab_manual_tables = set()
        self._table_field_names_cache: dict[str, list[str]] = {}
        self._tables_tab_refresh_used_tables()
        self._joins_update_action_state()

        return tab

    def _tables_tab_get_available_tables(self) -> list[str]:
        """Return a list of all tables available from the left tables tree."""
        tables: list[str] = []
        if not hasattr(self, 'tables_tree'):
            return tables
        for i in range(self.tables_tree.topLevelItemCount()):
            item = self.tables_tree.topLevelItem(i)
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            name = (data.get('table_name') or '').strip()
            if name:
                tables.append(name)
        return sorted(list(set(tables)))

    def _tables_tab_refresh_used_tables(self):
        """Refresh the Used Tables list and keep join comboboxes in sync."""
        if not hasattr(self, 'used_tables_list'):
            return

        used = set()

        # From Display
        for r in range(self.display_table.rowCount()):
            table_item = self.display_table.item(r, 1)
            if table_item and table_item.text().strip():
                used.add(table_item.text().strip())

        # From Criteria
        for r in range(self.criteria_table.rowCount()):
            table_item = self.criteria_table.item(r, 1)
            if table_item and table_item.text().strip():
                used.add(table_item.text().strip())

        # From manual adds and existing tables_involved
        used |= set(getattr(self, '_tables_tab_manual_tables', set()))
        used |= set(self.tables_involved)

        # From current join selections
        if hasattr(self, 'joins_tree'):
            for i in range(self.joins_tree.topLevelItemCount()):
                join_item = self.joins_tree.topLevelItem(i)
                left_combo = self.joins_tree.itemWidget(join_item, 0)
                right_combo = self.joins_tree.itemWidget(join_item, 2)
                if isinstance(left_combo, QComboBox) and left_combo.currentText().strip():
                    used.add(left_combo.currentText().strip())
                if isinstance(right_combo, QComboBox) and right_combo.currentText().strip():
                    used.add(right_combo.currentText().strip())

        used_list = sorted(list(used))
        self._tables_used_list = used_list

        # Update tables_involved so it persists/saves
        self.tables_involved |= set(used_list)

        # Update used tables list widget
        self.used_tables_list.clear()
        for t in used_list:
            self.used_tables_list.addTopLevelItem(QTreeWidgetItem([t]))

        # Update manual table combo
        available = self._tables_tab_get_available_tables()
        current_text = self.manual_table_combo.currentText().strip() if hasattr(self, 'manual_table_combo') else ''
        if hasattr(self, 'manual_table_combo'):
            self.manual_table_combo.blockSignals(True)
            try:
                self.manual_table_combo.clear()
                self.manual_table_combo.addItems(available)
                if current_text:
                    self.manual_table_combo.setCurrentText(current_text)
            finally:
                self.manual_table_combo.blockSignals(False)

        # Refresh join combos + ON field combos
        self._joins_refresh_all_combo_models()

    def _tables_tab_add_table_manually(self):
        if not hasattr(self, 'manual_table_combo'):
            return
        name = self.manual_table_combo.currentText().strip()
        if not name:
            return
        self._tables_tab_manual_tables.add(name)
        self.tables_involved.add(name)
        self._tables_tab_refresh_used_tables()
        self._update_sql_preview()

    def _make_tight_combo(self, items: list[str], current: str = "") -> QComboBox:
        combo = QComboBox()
        combo.setStyleSheet(
            "QComboBox{font-size:10px; padding:0px; margin:0px; border:1px solid #B0C8E8; background:#E8F0FF;}"
            "QComboBox::drop-down{width:16px; border:none;}"
        )
        combo.addItems(items)
        if current:
            combo.setCurrentText(current)
        return combo

    def _tables_tab_get_field_names(self, table_name: str) -> list[str]:
        table_name = (table_name or '').strip()
        if not table_name:
            return []
        if table_name in getattr(self, '_table_field_names_cache', {}):
            return self._table_field_names_cache[table_name]

        schema_name = self._tables_tab_get_schema_for_table(table_name)

        # Need a connection to resolve fields
        if not self.current_connection_id:
            self._table_field_names_cache[table_name] = []
            return []

        try:
            metadata_id = self.metadata_cache_repo.get_or_create_metadata(
                self.current_connection_id, table_name, schema_name
            )
            cached_columns = self.metadata_cache_repo.get_cached_columns(metadata_id)
            if cached_columns:
                columns = cached_columns
            else:
                columns = self.schema_discovery.get_columns(self.current_connection_id, table_name, schema_name)
                self.metadata_cache_repo.cache_column_metadata(metadata_id, [
                    {
                        'name': col['column_name'],
                        'type': col['data_type'],
                        'nullable': col.get('is_nullable', True),
                        'primary_key': col.get('is_primary_key', False),
                        'max_length': col.get('max_length')
                    }
                    for col in columns
                ])

            names: list[str] = []
            for col_data in columns:
                col_name = col_data.get('name') or col_data.get('column_name')
                if col_name:
                    names.append(str(col_name))
            names = sorted(list(dict.fromkeys(names)))
            self._table_field_names_cache[table_name] = names
            return names
        except Exception:
            self._table_field_names_cache[table_name] = []
            return []

    def _tables_tab_get_schema_for_table(self, table_name: str) -> str:
        """Resolve schema for a table from the loaded tables tree, falling back to current schema."""
        table_name = (table_name or '').strip()
        if not table_name or not hasattr(self, 'tables_tree'):
            return self.current_schema_name or ''

        for i in range(self.tables_tree.topLevelItemCount()):
            item = self.tables_tree.topLevelItem(i)
            table_data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            if (table_data.get('table_name') or '').strip() == table_name:
                return (table_data.get('schema_name') or self.current_schema_name or '').strip()

        return self.current_schema_name or ''

    def _joins_refresh_all_combo_models(self):
        """Refresh table/field combo models across all join rows."""
        if not hasattr(self, 'joins_tree'):
            return
        tables = list(getattr(self, '_tables_used_list', []))

        for i in range(self.joins_tree.topLevelItemCount()):
            join_item = self.joins_tree.topLevelItem(i)
            left_combo = self.joins_tree.itemWidget(join_item, 0)
            right_combo = self.joins_tree.itemWidget(join_item, 2)
            join_type_combo = self.joins_tree.itemWidget(join_item, 1)

            left_val = left_combo.currentText().strip() if isinstance(left_combo, QComboBox) else ''
            right_val = right_combo.currentText().strip() if isinstance(right_combo, QComboBox) else ''
            join_type_val = join_type_combo.currentText() if isinstance(join_type_combo, QComboBox) else 'INNER JOIN'

            if isinstance(left_combo, QComboBox):
                left_combo.blockSignals(True)
                left_combo.clear()
                left_combo.addItems(tables)
                if left_val:
                    left_combo.setCurrentText(left_val)
                left_combo.blockSignals(False)

            if isinstance(right_combo, QComboBox):
                right_combo.blockSignals(True)
                right_combo.clear()
                right_combo.addItems(tables)
                if right_val:
                    right_combo.setCurrentText(right_val)
                right_combo.blockSignals(False)

            if isinstance(join_type_combo, QComboBox):
                join_type_combo.setCurrentText(join_type_val)

            # Update ON rows field combos
            self._joins_refresh_on_fields_for_join(join_item)

    def _joins_refresh_on_fields_for_join(self, join_item: QTreeWidgetItem):
        left_combo = self.joins_tree.itemWidget(join_item, 0)
        right_combo = self.joins_tree.itemWidget(join_item, 2)
        left_table = left_combo.currentText().strip() if isinstance(left_combo, QComboBox) else ''
        right_table = right_combo.currentText().strip() if isinstance(right_combo, QComboBox) else ''
        left_fields = self._tables_tab_get_field_names(left_table)
        right_fields = self._tables_tab_get_field_names(right_table)

        for j in range(join_item.childCount()):
            on_item = join_item.child(j)
            lf = self.joins_tree.itemWidget(on_item, 0)
            rf = self.joins_tree.itemWidget(on_item, 2)
            lf_val = lf.currentText().strip() if isinstance(lf, QComboBox) else ''
            rf_val = rf.currentText().strip() if isinstance(rf, QComboBox) else ''

            if isinstance(lf, QComboBox):
                lf.blockSignals(True)
                lf.clear()
                lf.addItems(left_fields)
                if lf_val:
                    lf.setCurrentText(lf_val)
                lf.blockSignals(False)

            if isinstance(rf, QComboBox):
                rf.blockSignals(True)
                rf.clear()
                rf.addItems(right_fields)
                if rf_val:
                    rf.setCurrentText(rf_val)
                rf.blockSignals(False)

    def _joins_add_join(self):
        if not hasattr(self, 'joins_tree'):
            return
        tables = list(getattr(self, '_tables_used_list', []))
        if not tables:
            self._tables_tab_refresh_used_tables()
            tables = list(getattr(self, '_tables_used_list', []))

        left_default = tables[0] if len(tables) > 0 else ''
        right_default = tables[1] if len(tables) > 1 else (tables[0] if len(tables) > 0 else '')

        join_item = QTreeWidgetItem(["", "", ""])
        join_item.setData(0, Qt.ItemDataRole.UserRole, {"kind": "join"})
        join_item.setExpanded(True)
        self.joins_tree.addTopLevelItem(join_item)

        left_combo = self._make_tight_combo(tables, left_default)
        right_combo = self._make_tight_combo(tables, right_default)

        join_type_combo = QComboBox()
        join_type_combo.addItems(["INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL OUTER JOIN"])
        join_type_combo.setCurrentText("INNER JOIN")
        join_type_combo.setStyleSheet(
            "QComboBox{font-size:10px; padding:0px; margin:0px; border:1px solid #B0C8E8; background:#E8F0FF;}"
            "QComboBox::drop-down{width:16px; border:none;}"
        )

        def on_tables_changed():
            if getattr(self, '_joins_updating', False):
                return
            self._tables_tab_refresh_used_tables()
            self._joins_refresh_on_fields_for_join(join_item)
            self._update_sql_preview()

        left_combo.currentTextChanged.connect(lambda *_: on_tables_changed())
        right_combo.currentTextChanged.connect(lambda *_: on_tables_changed())
        join_type_combo.currentTextChanged.connect(lambda *_: self._update_sql_preview())

        self.joins_tree.setItemWidget(join_item, 0, left_combo)
        self.joins_tree.setItemWidget(join_item, 1, join_type_combo)
        self.joins_tree.setItemWidget(join_item, 2, right_combo)

        self.joins_tree.setCurrentItem(join_item)
        self._joins_update_action_state()
        self._tables_tab_refresh_used_tables()
        self._update_sql_preview()

    def _joins_add_on(self):
        if not hasattr(self, 'joins_tree'):
            return
        item = self.joins_tree.currentItem()
        if not item:
            return

        kind = (item.data(0, Qt.ItemDataRole.UserRole) or {}).get('kind')
        join_item = item if kind == 'join' else item.parent() if kind == 'on' else None
        if not join_item:
            return

        left_combo = self.joins_tree.itemWidget(join_item, 0)
        right_combo = self.joins_tree.itemWidget(join_item, 2)
        left_table = left_combo.currentText().strip() if isinstance(left_combo, QComboBox) else ''
        right_table = right_combo.currentText().strip() if isinstance(right_combo, QComboBox) else ''

        left_fields = self._tables_tab_get_field_names(left_table)
        right_fields = self._tables_tab_get_field_names(right_table)

        on_item = QTreeWidgetItem(["", "", ""])
        on_item.setData(0, Qt.ItemDataRole.UserRole, {"kind": "on"})
        join_item.addChild(on_item)

        left_field_combo = self._make_tight_combo(left_fields, left_fields[0] if left_fields else "")
        right_field_combo = self._make_tight_combo(right_fields, right_fields[0] if right_fields else "")

        eq_label = QLabel("=")
        eq_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        eq_label.setStyleSheet("font-size:10px; padding:0px; margin:0px; background: transparent;")

        left_field_combo.currentTextChanged.connect(lambda *_: self._update_sql_preview())
        right_field_combo.currentTextChanged.connect(lambda *_: self._update_sql_preview())

        self.joins_tree.setItemWidget(on_item, 0, left_field_combo)
        self.joins_tree.setItemWidget(on_item, 1, eq_label)
        self.joins_tree.setItemWidget(on_item, 2, right_field_combo)

        join_item.setExpanded(True)
        self.joins_tree.setCurrentItem(on_item)
        self._joins_update_action_state()
        self._update_sql_preview()

    def _joins_delete_selected(self):
        if not hasattr(self, 'joins_tree'):
            return
        item = self.joins_tree.currentItem()
        if not item:
            return
        kind = (item.data(0, Qt.ItemDataRole.UserRole) or {}).get('kind')
        if kind == 'join':
            idx = self.joins_tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self.joins_tree.takeTopLevelItem(idx)
        elif kind == 'on':
            parent = item.parent()
            if parent:
                parent.removeChild(item)
        self._joins_update_action_state()
        self._tables_tab_refresh_used_tables()
        self._update_sql_preview()

    def _joins_update_action_state(self):
        item = self.joins_tree.currentItem() if hasattr(self, 'joins_tree') else None
        if not item:
            if hasattr(self, 'on_add_btn'):
                self.on_add_btn.setEnabled(False)
            if hasattr(self, 'join_del_btn'):
                self.join_del_btn.setEnabled(False)
            return

        kind = (item.data(0, Qt.ItemDataRole.UserRole) or {}).get('kind')
        if hasattr(self, 'on_add_btn'):
            self.on_add_btn.setEnabled(kind in {'join', 'on'})
        if hasattr(self, 'join_del_btn'):
            self.join_del_btn.setEnabled(kind in {'join', 'on'})

    def _get_joins_definition(self) -> dict:
        """Serialize join editor state."""
        joins: list[dict] = []
        if not hasattr(self, 'joins_tree'):
            return {"joins": joins}

        for i in range(self.joins_tree.topLevelItemCount()):
            join_item = self.joins_tree.topLevelItem(i)
            left_combo = self.joins_tree.itemWidget(join_item, 0)
            join_type_combo = self.joins_tree.itemWidget(join_item, 1)
            right_combo = self.joins_tree.itemWidget(join_item, 2)

            left_table = left_combo.currentText().strip() if isinstance(left_combo, QComboBox) else ''
            right_table = right_combo.currentText().strip() if isinstance(right_combo, QComboBox) else ''
            join_type = join_type_combo.currentText().strip() if isinstance(join_type_combo, QComboBox) else 'INNER JOIN'

            on_list: list[dict] = []
            for j in range(join_item.childCount()):
                on_item = join_item.child(j)
                lf = self.joins_tree.itemWidget(on_item, 0)
                rf = self.joins_tree.itemWidget(on_item, 2)
                left_field = lf.currentText().strip() if isinstance(lf, QComboBox) else ''
                right_field = rf.currentText().strip() if isinstance(rf, QComboBox) else ''
                if left_field and right_field:
                    on_list.append({"left_field": left_field, "right_field": right_field})

            if left_table and right_table:
                joins.append(
                    {
                        "left_table": left_table,
                        "join_type": join_type,
                        "right_table": right_table,
                        "on": on_list,
                    }
                )

        return {"joins": joins}

    def _load_joins_definition(self, definition: dict):
        """Load join editor state from a saved package definition."""
        if not hasattr(self, 'joins_tree'):
            return

        self._joins_updating = True
        try:
            self.joins_tree.clear()
            joins_raw = definition.get('joins', []) or []

            def _split_qual(expr: str) -> tuple[str, str]:
                expr = (expr or '').strip()
                if '.' in expr:
                    t, f = expr.split('.', 1)
                    return t.strip(), f.strip()
                return '', expr

            # Backward compatibility:
            # - New structure: [{'left_table','join_type','right_table','on':[{'left_field','right_field'}]}]
            # - Old structure: base_table/base_alias + joins: [{'join_type','table','alias','on':[{'left','op','right'}]}]
            joins: list[dict] = []
            if joins_raw and all(('left_table' in j or 'right_table' in j) for j in joins_raw):
                joins = joins_raw
            else:
                base_table = (definition.get('base_table') or '').strip()
                for old in joins_raw:
                    join_table = (old.get('table') or '').strip()
                    join_type = (old.get('join_type') or 'INNER JOIN').strip()
                    on_list = old.get('on') or []
                    converted_on: list[dict] = []
                    left_table_guess = base_table
                    right_table_guess = join_table
                    for cond in on_list:
                        left_expr = (cond.get('left') or '').strip()
                        right_expr = (cond.get('right') or '').strip()
                        lt, lf = _split_qual(left_expr)
                        rt, rf = _split_qual(right_expr)
                        if lt:
                            left_table_guess = lt
                        if rt:
                            right_table_guess = rt
                        if lf and rf:
                            converted_on.append({'left_field': lf, 'right_field': rf})
                    if left_table_guess and right_table_guess:
                        joins.append({
                            'left_table': left_table_guess,
                            'join_type': join_type,
                            'right_table': right_table_guess,
                            'on': converted_on,
                        })

            # If joins exist but ON conditions are missing/empty, attempt to reconstruct from saved SQL.
            sql_text = (definition.get('sql') or '').strip()
            if sql_text and (not joins or all(len((j.get('on') or [])) == 0 for j in joins)):
                parsed = self._tables_tab_parse_joins_from_sql(sql_text)
                if parsed:
                    joins = parsed

            for j in joins:
                if 'left_table' not in j or 'right_table' not in j:
                    continue
                left_table = (j.get('left_table') or '').strip()
                right_table = (j.get('right_table') or '').strip()
                join_type = (j.get('join_type') or 'INNER JOIN').strip()

                join_item = QTreeWidgetItem(["", "", ""])
                join_item.setData(0, Qt.ItemDataRole.UserRole, {"kind": "join"})
                join_item.setExpanded(True)
                self.joins_tree.addTopLevelItem(join_item)

                tables = list(getattr(self, '_tables_used_list', []))
                if not tables:
                    tables = sorted(list(self.tables_involved))
                left_combo = self._make_tight_combo(tables, left_table)
                right_combo = self._make_tight_combo(tables, right_table)

                join_type_combo = QComboBox()
                join_type_combo.addItems(["INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL OUTER JOIN"])
                join_type_combo.setCurrentText(join_type if join_type in [join_type_combo.itemText(i) for i in range(join_type_combo.count())] else "INNER JOIN")
                join_type_combo.setStyleSheet(
                    "QComboBox{font-size:10px; padding:0px; margin:0px; border:1px solid #B0C8E8; background:#E8F0FF;}"
                    "QComboBox::drop-down{width:16px; border:none;}"
                )

                def on_tables_changed():
                    if getattr(self, '_joins_updating', False):
                        return
                    self._tables_tab_refresh_used_tables()
                    self._joins_refresh_on_fields_for_join(join_item)
                    self._update_sql_preview()

                left_combo.currentTextChanged.connect(lambda *_: on_tables_changed())
                right_combo.currentTextChanged.connect(lambda *_: on_tables_changed())
                join_type_combo.currentTextChanged.connect(lambda *_: self._update_sql_preview())

                self.joins_tree.setItemWidget(join_item, 0, left_combo)
                self.joins_tree.setItemWidget(join_item, 1, join_type_combo)
                self.joins_tree.setItemWidget(join_item, 2, right_combo)

                for on_def in j.get('on', []) or []:
                    left_field = (on_def.get('left_field') or '').strip()
                    right_field = (on_def.get('right_field') or '').strip()

                    on_item = QTreeWidgetItem(["", "", ""])
                    on_item.setData(0, Qt.ItemDataRole.UserRole, {"kind": "on"})
                    join_item.addChild(on_item)

                    left_fields = self._tables_tab_get_field_names(left_table)
                    right_fields = self._tables_tab_get_field_names(right_table)

                    lf_combo = self._make_tight_combo(left_fields, left_field)
                    rf_combo = self._make_tight_combo(right_fields, right_field)
                    eq_label = QLabel("=")
                    eq_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    eq_label.setStyleSheet("font-size:10px; padding:0px; margin:0px; background: transparent;")
                    lf_combo.currentTextChanged.connect(lambda *_: self._update_sql_preview())
                    rf_combo.currentTextChanged.connect(lambda *_: self._update_sql_preview())

                    self.joins_tree.setItemWidget(on_item, 0, lf_combo)
                    self.joins_tree.setItemWidget(on_item, 1, eq_label)
                    self.joins_tree.setItemWidget(on_item, 2, rf_combo)

                # Make sure children are actually shown (some layouts only realize expansion after widgets exist)
                try:
                    join_item.setExpanded(True)
                    self.joins_tree.expandItem(join_item)
                except Exception:
                    pass

            self._tables_tab_refresh_used_tables()
        finally:
            self._joins_updating = False
            self._joins_update_action_state()

            # Ensure ON field combos are populated after refresh
            try:
                self._joins_refresh_all_combo_models()
            except Exception:
                pass

            # Post-event-loop: force expand + layout so ON rows appear immediately on first open
            try:
                from PyQt6.QtCore import QTimer

                def _finalize():
                    if not hasattr(self, 'joins_tree'):
                        return
                    try:
                        self.joins_tree.expandAll()
                        self.joins_tree.doItemsLayout()
                        self.joins_tree.viewport().update()
                        if self.joins_tree.topLevelItemCount() > 0 and not self.joins_tree.currentItem():
                            self.joins_tree.setCurrentItem(self.joins_tree.topLevelItem(0))
                    except Exception:
                        pass

                QTimer.singleShot(0, _finalize)
            except Exception:
                pass

    def _tables_tab_parse_joins_from_sql(self, sql: str) -> list[dict]:
        """Parse JOIN/ON blocks from a saved SQL string into the new joins structure.

        Expected patterns (whitespace/newlines flexible):
        - FROM <schema>.<table> [alias]
        - <JOIN TYPE> <schema>.<table> [alias]\n    ON a.x = b.y\n    AND a.x2 = b.y2
        """
        if not sql:
            return []

        text = sql.replace('\r\n', '\n')

        # Build alias->table map from FROM and JOIN clauses
        alias_map: dict[str, str] = {}
        current_schema = (self.current_schema_name or '').strip()

        def _strip_schema(name: str) -> str:
            name = (name or '').strip()
            if '.' in name:
                return name.split('.', 1)[1].strip()
            return name

        from_m = re.search(r"\bFROM\s+([A-Z0-9_$.]+)\s*([A-Z0-9_]+)?", text, flags=re.IGNORECASE)
        if from_m:
            base_full = from_m.group(1)
            base_alias = (from_m.group(2) or '').strip()
            base_table = _strip_schema(base_full)
            if not base_alias:
                base_alias = base_table
            alias_map[base_alias] = base_table

        join_pat = re.compile(
            r"\b(?P<jt>INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|FULL\s+OUTER\s+JOIN)\s+"
            r"(?P<table>[A-Z0-9_$.]+)\s*(?P<alias>[A-Z0-9_]+)?\s*"
            r"\bON\b\s*(?P<conds>.*?)"
            r"(?=(\n\s*(INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|FULL\s+OUTER\s+JOIN)\b|\n\s*WHERE\b|\n\s*GROUP\s+BY\b|\n\s*ORDER\s+BY\b|$))",
            flags=re.IGNORECASE | re.DOTALL,
        )

        joins: list[dict] = []

        def _split_conditions(block: str) -> list[str]:
            block = (block or '').strip()
            if not block:
                return []
            # Normalize separators to newlines then split on AND boundaries
            tmp = block.replace('\t', ' ')
            tmp = re.sub(r"\s+AND\s+", "\nAND ", tmp, flags=re.IGNORECASE)
            parts = [p.strip() for p in tmp.split('\n') if p.strip()]
            # Drop leading AND tokens
            cleaned: list[str] = []
            for p in parts:
                cleaned.append(re.sub(r"^AND\s+", "", p, flags=re.IGNORECASE).strip())
            return cleaned

        def _parse_eq(expr: str) -> tuple[tuple[str, str] | None, tuple[str, str] | None]:
            # Returns ((lt, lf),(rt, rf)) from "A.B = C.D"
            m = re.search(r"([A-Z0-9_]+)\.([A-Z0-9_]+)\s*=\s*([A-Z0-9_]+)\.([A-Z0-9_]+)", expr, flags=re.IGNORECASE)
            if not m:
                return None, None
            return (m.group(1), m.group(2)), (m.group(3), m.group(4))

        # First pass: collect join alias map
        for jm in re.finditer(r"\b(INNER\s+JOIN|LEFT\s+JOIN|RIGHT\s+JOIN|FULL\s+OUTER\s+JOIN)\s+([A-Z0-9_$.]+)\s*([A-Z0-9_]+)?", text, flags=re.IGNORECASE):
            table_full = jm.group(2)
            alias = (jm.group(3) or '').strip()
            table_name = _strip_schema(table_full)
            if not alias:
                alias = table_name
            alias_map[alias] = table_name

        for m in join_pat.finditer(text):
            join_type = re.sub(r"\s+", " ", m.group('jt').strip().upper())
            table_full = m.group('table').strip()
            alias = (m.group('alias') or '').strip()
            right_table = _strip_schema(table_full)
            right_alias = alias or right_table

            conds = _split_conditions(m.group('conds'))
            on_list: list[dict] = []
            left_table_name: str | None = None

            for cond in conds:
                left_tok, right_tok = _parse_eq(cond)
                if not left_tok or not right_tok:
                    continue
                (lt, lf), (rt, rf) = left_tok, right_tok

                lt_name = alias_map.get(lt, lt)
                rt_name = alias_map.get(rt, rt)

                # Decide which side belongs to the joined table
                if alias_map.get(lt, lt) == right_table or lt == right_alias:
                    # Left token is joined table
                    left_table_name = alias_map.get(rt, rt)
                    on_list.append({'left_field': rf, 'right_field': lf})
                elif alias_map.get(rt, rt) == right_table or rt == right_alias:
                    left_table_name = alias_map.get(lt, lt)
                    on_list.append({'left_field': lf, 'right_field': rf})
                else:
                    # Fallback: keep original order
                    left_table_name = lt_name
                    on_list.append({'left_field': lf, 'right_field': rf})

            if not left_table_name:
                # Fallback to base table if known
                if alias_map:
                    # pick first mapped base alias if available
                    left_table_name = next(iter(alias_map.values()))
                else:
                    left_table_name = ''

            if left_table_name and right_table:
                joins.append({
                    'left_table': left_table_name,
                    'join_type': join_type,
                    'right_table': right_table,
                    'on': on_list,
                })

        return joins
    def _create_query_statement_tab(self) -> QWidget:
        """Create Query Statement tab with SQL preview"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(5, 5, 5, 5)

        # Top button row
        top_btn_row = QHBoxLayout()
        
        # Run Query Button
        self.run_custom_query_btn = QPushButton("▶ Run Query")
        self.run_custom_query_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        self.run_custom_query_btn.clicked.connect(self._run_custom_query)
        top_btn_row.addWidget(self.run_custom_query_btn)

        # Build SQL Button
        self.build_sql_btn = QPushButton("↻ Build SQL")
        self.build_sql_btn.setStyleSheet("""
            QPushButton {
                background-color: #E8F0FF;
                color: #1B1B1B;
                font-weight: bold;
                padding: 5px 15px;
                border-radius: 3px;
                border: 1px solid #0078D4;
            }
            QPushButton:hover {
                background-color: #E6F0FF;
            }
        """)
        self.build_sql_btn.clicked.connect(self._on_build_sql_clicked)
        top_btn_row.addWidget(self.build_sql_btn)
        
        top_btn_row.addStretch()
        layout.addLayout(top_btn_row)

        # SQL preview
        self.sql_preview = QTextEdit()
        self.sql_preview.setReadOnly(False)
        self.sql_preview.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                background-color: #1e1e1e;
                color: #d4d4d4;
                padding: 10px;
            }
        """)
        layout.addWidget(self.sql_preview)

        # Buttons
        btn_row = QHBoxLayout()
        
        copy_btn = QPushButton("📋 Copy SQL")
        copy_btn.clicked.connect(self._copy_sql)
        btn_row.addWidget(copy_btn)
        
        btn_row.addStretch()
        layout.addLayout(btn_row)

        return tab

    def _on_build_sql_clicked(self):
        """Force rebuild SQL from current UI state."""
        sql = self._build_sql()
        self.sql_preview.setPlainText(self._format_sql(sql))

    # ==================== DATA LOADING ====================

    def load_data_sources(self):
        """Load available data sources into the cascading dropdowns"""
        # Get all connections grouped by type
        connections = self.conn_repo.get_all_connections()
        
        # Group by connection type
        self.connections_by_type = {}
        for conn in connections:
            conn_type = conn['connection_type']
            if conn_type not in self.connections_by_type:
                self.connections_by_type[conn_type] = []
            self.connections_by_type[conn_type].append(conn)
        
        # Populate type dropdown
        self.db_type_combo.clear()
        self.db_type_combo.addItem("")  # Empty first item
        for conn_type in sorted(self.connections_by_type.keys()):
            self.db_type_combo.addItem(conn_type)
        
        # Load saved packages
        self._load_packages()

    def _load_packages(self):
        """Load saved data packages into the tree"""
        self.packages_tree.clear()
        
        # Get saved queries that are data packages
        try:
            queries = self.query_repo.get_all_queries(query_type='DATAPACKAGE')
            for query in queries:
                item = QTreeWidgetItem([query['query_name']])
                item.setData(0, Qt.ItemDataRole.UserRole, "package")
                item.setData(0, Qt.ItemDataRole.UserRole + 1, query['query_id'])
                self.packages_tree.addTopLevelItem(item)
        except Exception as e:
            logger.error(f"Error loading packages: {e}")

    def _on_db_type_changed(self, db_type: str):
        """Handle database type selection"""
        self.connection_combo.clear()
        self.connection_combo.addItem("")
        
        if db_type and db_type in self.connections_by_type:
            for conn in self.connections_by_type[db_type]:
                self.connection_combo.addItem(conn['connection_name'], conn['connection_id'])

    def _on_connection_changed(self, conn_name: str):
        """Handle connection selection - load tables"""
        self.tables_tree.clear()

        if hasattr(self, '_table_field_names_cache'):
            self._table_field_names_cache.clear()
        
        if not conn_name:
            self.tables_info.setText("Select a data source")
            return
        
        # Get connection ID
        conn_id = self.connection_combo.currentData()
        if not conn_id:
            return
        
        self.current_connection_id = conn_id
        
        # Load tables for this connection - use saved tables like DB Query
        try:
            # Get saved tables for this connection
            saved_tables = self.saved_table_repo.get_saved_tables(conn_id)
            
            if not saved_tables:
                self.tables_info.setText("No saved tables")
                return
            
            for table in saved_tables:
                table_name = table['table_name']
                schema_name = table.get('schema_name', '')
                
                # Display name
                display_name = f"{schema_name}.{table_name}" if schema_name else table_name
                
                item = QTreeWidgetItem([display_name])
                item.setData(0, Qt.ItemDataRole.UserRole, {
                    'table_name': table_name,
                    'schema_name': schema_name,
                    'connection_id': conn_id
                })
                self.tables_tree.addTopLevelItem(item)
            
            self.tables_info.setText(f"{len(saved_tables)} tables")
            
            # Update table indicators to show which are in Display
            self.update_table_indicators()
            
        except Exception as e:
            logger.error(f"Error loading tables: {e}")
            self.tables_info.setText(f"Error: {e}")

    def _get_tables_for_connection(self, conn) -> list:
        """Get tables for a connection from cache or discovery"""
        # Try cache first
        cache_key = f"{conn['connection_type']}:{conn['connection_name']}"
        cached = self.metadata_cache_repo.get_tables(cache_key)
        if cached:
            return cached
        
        # Otherwise use schema discovery
        try:
            tables = self.schema_discovery.get_tables(conn['connection_id'])
            # Cache the result
            self.metadata_cache_repo.save_tables(cache_key, tables)
            return tables
        except Exception as e:
            logger.error(f"Error discovering tables: {e}")
            return []

    def _on_table_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle table click - load fields"""
        self.fields_tree.clear()
        
        table_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not table_data:
            return
        
        table_name = table_data.get('table_name')
        schema_name = table_data.get('schema_name', '')
        conn_id = table_data.get('connection_id')
        
        self.current_table_name = table_name
        self.current_schema_name = schema_name
        
        # Load fields using same approach as DB Query
        try:
            # Get or create metadata
            metadata_id = self.metadata_cache_repo.get_or_create_metadata(
                conn_id, table_name, schema_name
            )
            
            # Try cached columns first
            cached_columns = self.metadata_cache_repo.get_cached_columns(metadata_id)
            
            if cached_columns:
                columns = cached_columns
            else:
                # Load from database via schema discovery
                columns = self.schema_discovery.get_columns(conn_id, table_name, schema_name)
                
                # Cache them
                self.metadata_cache_repo.cache_column_metadata(metadata_id, [
                    {
                        'name': col['column_name'],
                        'type': col['data_type'],
                        'nullable': col.get('is_nullable', True),
                        'primary_key': col.get('is_primary_key', False),
                        'max_length': col.get('max_length')
                    }
                    for col in columns
                ])
            
            # Add fields to tree
            for col_data in columns:
                col_name = col_data.get('name') or col_data.get('column_name')
                col_type = col_data.get('type') or col_data.get('data_type')
                
                field_item = QTreeWidgetItem([f"{col_name} ({col_type})"])
                field_item.setData(0, Qt.ItemDataRole.UserRole, {
                    'field_name': col_name,
                    'data_type': col_type,
                    'table_name': table_name,
                    'schema_name': schema_name,
                    'connection_id': conn_id
                })
                self.fields_tree.addTopLevelItem(field_item)
            
            self.fields_info.setText(f"{len(columns)} fields")
            
            # Update field indicators to show which are in Display
            self._update_field_indicators()
            
        except Exception as e:
            logger.error(f"Error loading fields: {e}")
            self.fields_info.setText(f"Error: {e}")

    def _get_fields_for_table(self, conn_id: int, schema_name: str, table_name: str) -> list:
        """Get fields for a table from cache or discovery"""
        # Try cache first
        cache_key = f"{conn_id}:{schema_name}:{table_name}"
        cached = self.metadata_cache_repo.get_columns(cache_key)
        if cached:
            return cached
        
        # Otherwise use schema discovery
        try:
            columns = self.schema_discovery.get_columns(conn_id, table_name, schema_name)
            self.metadata_cache_repo.save_columns(cache_key, columns)
            return columns
        except Exception as e:
            logger.error(f"Error discovering columns: {e}")
            return []

    # ==================== DISPLAY TAB HANDLERS ====================

    def _add_display_field(self, field_data: dict, row_index: int):
        """Add a field to the display table"""
        # Get connection info from field data
        field_conn_id = field_data.get('connection_id')
        
        # Check if this is a different connection than what's already in display
        if self.display_table.rowCount() > 0:
            # Get the connection from first row
            first_field_item = self.display_table.item(0, 0)
            if first_field_item:
                first_field_data = first_field_item.data(Qt.ItemDataRole.UserRole)
                if first_field_data:
                    existing_conn_id = first_field_data.get('connection_id')
                    if existing_conn_id and field_conn_id != existing_conn_id:
                        QMessageBox.warning(
                            self, "Different Data Source",
                            "Cannot add fields from a different data source.\n\n"
                            "All fields in a Data Package must be from the same connection.\n"
                            "Clear the Display table first if you want to use a different connection."
                        )
                        return
        
        row = row_index if row_index < self.display_table.rowCount() else self.display_table.rowCount()
        self.display_table.insertRow(row)
        
        # Field name
        field_name = field_data.get('field_name', '')
        field_item = QTableWidgetItem(field_name)
        field_item.setData(Qt.ItemDataRole.UserRole, field_data)
        self.display_table.setItem(row, 0, field_item)
        
        # Table name
        table_name = field_data.get('table_name', '')
        self.display_table.setItem(row, 1, QTableWidgetItem(table_name))
        
        # Alias (empty by default - user editable)
        self.display_table.setItem(row, 2, QTableWidgetItem(""))
        
        # Agg - embedded combobox widget (like My Data's Data Map column)
        agg_combo = QComboBox()
        agg_combo.addItems(["", "COUNT", "SUM", "AVG", "MIN", "MAX", "COUNT DISTINCT"])
        agg_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 2px;
                padding: 1px 3px 1px 5px;
                background: white;
                font-size: 11px;
            }
            QComboBox:hover {
                border: 1px solid #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox::down-arrow {
                image: url(none);
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid #555;
                width: 0;
                height: 0;
                margin-right: 3px;
            }
        """)
        agg_combo.currentTextChanged.connect(lambda: self._update_sql_preview())
        self.display_table.setCellWidget(row, 3, agg_combo)
        
        # Order - embedded combobox widget
        order_combo = QComboBox()
        order_combo.addItems(["", "ASC", "DESC"])
        order_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 2px;
                padding: 1px 3px 1px 5px;
                background: white;
                font-size: 11px;
            }
            QComboBox:hover {
                border: 1px solid #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox::down-arrow {
                image: url(none);
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid #555;
                width: 0;
                height: 0;
                margin-right: 3px;
            }
        """)
        order_combo.currentTextChanged.connect(lambda: self._update_sql_preview())
        self.display_table.setCellWidget(row, 4, order_combo)
        
        # Having (empty by default - user editable)
        self.display_table.setItem(row, 5, QTableWidgetItem(""))
        
        # Track table
        self.tables_involved.add(table_name)
        
        # Update data source label
        self._update_display_source_label()
        
        # Update SQL preview and indicators
        self._update_sql_preview()
        self._update_field_indicators()
        self.update_table_indicators()

    def _update_display_source_label(self):
        """Update the data source label above Display table"""
        if self.display_table.rowCount() == 0:
            self.display_source_label.setText("No data source selected")
            return
        
        # Get connection info from first field
        first_field_item = self.display_table.item(0, 0)
        if first_field_item:
            field_data = first_field_item.data(Qt.ItemDataRole.UserRole)
            if field_data:
                conn_id = field_data.get('connection_id')
                # Look up connection name from combo
                db_type = self.db_type_combo.currentText()
                conn_name = self.connection_combo.currentText()
                if db_type and conn_name:
                    self.display_source_label.setText(f"{db_type}: {conn_name}")
                    # Also update criteria source label
                    if hasattr(self, 'criteria_source_label'):
                        self.criteria_source_label.setText(f"{db_type}: {conn_name}")
                else:
                    self.display_source_label.setText(f"Connection ID: {conn_id}")
                    if hasattr(self, 'criteria_source_label'):
                        self.criteria_source_label.setText(f"Connection ID: {conn_id}")
            else:
                self.display_source_label.setText("Data source active")
                if hasattr(self, 'criteria_source_label'):
                    self.criteria_source_label.setText("Data source active")

    def _update_field_indicators(self):
        """Update indicators next to fields based on active tab.
        
        - Display tab (0): Show green dots for fields in Display
        - Criteria tab (1): Show orange dots for fields in Criteria
        """
        current_tab = self.tabs.currentIndex()
        
        # Get all fields currently in Display
        fields_in_display = set()
        for row in range(self.display_table.rowCount()):
            field_item = self.display_table.item(row, 0)
            table_item = self.display_table.item(row, 1)
            if field_item and table_item:
                field_name = field_item.text()
                table_name = table_item.text()
                fields_in_display.add((field_name, table_name))
        
        # Get all fields currently in Criteria
        fields_in_criteria = set()
        for row in range(self.criteria_table.rowCount()):
            field_item = self.criteria_table.item(row, 0)
            table_item = self.criteria_table.item(row, 1)
            if field_item and table_item:
                field_name = field_item.text()
                table_name = table_item.text()
                fields_in_criteria.add((field_name, table_name))
        
        # Update all items in the fields tree
        for i in range(self.fields_tree.topLevelItemCount()):
            item = self.fields_tree.topLevelItem(i)
            field_data = item.data(0, Qt.ItemDataRole.UserRole)
            if not field_data:
                continue
            
            field_name = field_data.get('field_name', '')
            table_name = field_data.get('table_name', '')
            data_type = field_data.get('data_type', 'CHAR')
            
            # Base display name
            base_name = f"{field_name} ({data_type})"
            
            # Check what indicators to show based on current tab
            in_display = (field_name, table_name) in fields_in_display
            in_criteria = (field_name, table_name) in fields_in_criteria
            
            # Only show indicator for the active tab
            if current_tab == 0 and in_display:
                # Display tab - show green for fields in Display
                item.setText(0, f"🟢 {base_name}")
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            elif current_tab == 1 and in_criteria:
                # Criteria tab - show orange for fields in Criteria
                item.setText(0, f"🟠 {base_name}")
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            else:
                # No indicator for this tab
                item.setText(0, base_name)
                font = item.font(0)
                font.setBold(False)
                item.setFont(0, font)

    def update_table_indicators(self):
        """Update dot indicators next to tables based on active tab."""
        current_tab = self.tabs.currentIndex()
        
        # Get all tables currently in Display
        tables_in_display = set()
        for row in range(self.display_table.rowCount()):
            table_item = self.display_table.item(row, 1)
            if table_item:
                tables_in_display.add(table_item.text())
        
        # Get all tables currently in Criteria
        tables_in_criteria = set()
        for row in range(self.criteria_table.rowCount()):
            table_item = self.criteria_table.item(row, 1)
            if table_item:
                tables_in_criteria.add(table_item.text())
        
        # Update all items in the tables tree
        for i in range(self.tables_tree.topLevelItemCount()):
            item = self.tables_tree.topLevelItem(i)
            table_data = item.data(0, Qt.ItemDataRole.UserRole)
            if not table_data:
                continue
            
            table_name = table_data.get('table_name', '')
            schema_name = table_data.get('schema_name', '')
            
            # Base display name
            base_name = f"{schema_name}.{table_name}" if schema_name else table_name
            
            # Check what indicators to show based on current tab
            in_display = table_name in tables_in_display
            in_criteria = table_name in tables_in_criteria
            
            if current_tab == 0 and in_display:
                # Display tab - show green
                item.setText(0, f"🟢 {base_name}")
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            elif current_tab == 1 and in_criteria:
                # Criteria tab - show orange
                item.setText(0, f"🟠 {base_name}")
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            else:
                # No indicator
                item.setText(0, base_name)
                font = item.font(0)
                font.setBold(False)
                item.setFont(0, font)

        # Sync Tables tab "Tables Used" section
        if hasattr(self, '_tables_tab_refresh_used_tables'):
            try:
                self._tables_tab_refresh_used_tables()
            except Exception:
                pass

    def _reorder_display_field(self, from_row: int, to_row: int):
        """Reorder a display field row"""
        if from_row == to_row:
            return
        
        # Store row data
        row_data = []
        for col in range(self.display_table.columnCount()):
            item = self.display_table.item(from_row, col)
            if item:
                row_data.append((item.text(), item.data(Qt.ItemDataRole.UserRole)))
            else:
                row_data.append(("", None))
        
        # Remove old row
        self.display_table.removeRow(from_row)
        
        # Adjust to_row if needed
        if from_row < to_row:
            to_row -= 1
        
        # Insert at new position
        self.display_table.insertRow(to_row)
        for col, (text, data) in enumerate(row_data):
            item = QTableWidgetItem(text)
            if data:
                item.setData(Qt.ItemDataRole.UserRole, data)
            self.display_table.setItem(to_row, col, item)

    def _show_row_context_menu(self, pos: QPoint):
        """Show context menu when right-clicking on row number (vertical header)"""
        # Get the row at this position
        row = self.display_table.verticalHeader().logicalIndexAt(pos)
        
        if row < 0:
            return
        
        # Select the row
        self.display_table.selectRow(row)
        
        menu = QMenu(self)
        
        # Move up action (if not first row)
        if row > 0:
            move_up_action = menu.addAction("⬆️ Move Up")
            move_up_action.triggered.connect(lambda checked, r=row: self._move_row_up(r))
        
        # Move down action (if not last row)
        if row < self.display_table.rowCount() - 1:
            move_down_action = menu.addAction("⬇️ Move Down")
            move_down_action.triggered.connect(lambda checked, r=row: self._move_row_down(r))
        
        menu.addSeparator()
        
        delete_action = menu.addAction("🗑️ Delete Row")
        delete_action.triggered.connect(lambda checked, r=row: self._delete_display_row(r))
        
        menu.addSeparator()
        
        clear_action = menu.addAction("🧹 Clear All")
        clear_action.triggered.connect(self._clear_display_table)
        
        # Show menu at cursor position
        menu.exec(self.display_table.verticalHeader().mapToGlobal(pos))
    
    def _move_row_up(self, row: int):
        """Move a row up by one position (swap with row above)"""
        if row > 0:
            self._swap_rows(row, row - 1)
            self.display_table.selectRow(row - 1)
    
    def _move_row_down(self, row: int):
        """Move a row down by one position (swap with row below)"""
        if row < self.display_table.rowCount() - 1:
            self._swap_rows(row, row + 1)
            self.display_table.selectRow(row + 1)
    
    def _swap_rows(self, row1: int, row2: int):
        """Swap two rows in the display table"""
        if row1 == row2:
            return
        
        # Capture both rows
        data1 = self._capture_row_data(row1)
        data2 = self._capture_row_data(row2)
        
        # Restore swapped
        self._restore_row_data(row1, data2)
        self._restore_row_data(row2, data1)
        
        self._update_sql_preview()
    
    def _insert_display_row(self, from_row: int, to_row: int):
        """Insert a row at a new position (drag and drop reorder).
        
        This removes the row from from_row and inserts it at to_row,
        shifting other rows as needed.
        """
        if from_row == to_row or from_row < 0 or to_row < 0:
            return
        
        if from_row >= self.display_table.rowCount():
            return
        
        # Capture the row data
        row_data = self._capture_row_data(from_row)
        
        # Remove the original row
        self.display_table.removeRow(from_row)
        
        # Adjust to_row if we removed a row before it
        if from_row < to_row:
            to_row -= 1
        
        # Insert new row at target position
        self.display_table.insertRow(to_row)
        
        # Restore the data
        self._restore_row_data(to_row, row_data)
        
        # Select the moved row
        self.display_table.selectRow(to_row)
        self._update_sql_preview()

    def _show_display_context_menu(self, pos: QPoint):
        """Show context menu for display table - only on index column (column 0 header area or vertical header)"""
        # Get the column at this position
        col = self.display_table.columnAt(pos.x())
        row = self.display_table.rowAt(pos.y())
        
        # Only show context menu when clicking on row number area (left side) or first column
        # Check if click is in the vertical header area (row numbers)
        vertical_header = self.display_table.verticalHeader()
        in_row_header = pos.x() < vertical_header.width() if vertical_header.isVisible() else False
        
        # If not in row header area and not on column 0, don't show menu
        if not in_row_header and col != 0:
            return
        
        menu = QMenu(self)
        
        if row >= 0:
            # Select the row first so user sees which row is being affected
            self.display_table.selectRow(row)
            
            # Move up action (if not first row)
            if row > 0:
                move_up_action = menu.addAction("⬆️ Move Up")
                # Use default argument to capture row value at definition time
                move_up_action.triggered.connect(lambda checked, r=row: self._move_row_up(r))
            
            # Move down action (if not last row)
            if row < self.display_table.rowCount() - 1:
                move_down_action = menu.addAction("⬇️ Move Down")
                # Use default argument to capture row value at definition time
                move_down_action.triggered.connect(lambda checked, r=row: self._move_row_down(r))
            
            menu.addSeparator()
            
            delete_action = menu.addAction("🗑️ Delete Row")
            # Use default argument to capture row value at definition time
            delete_action.triggered.connect(lambda checked, r=row: self._delete_display_row(r))
            
            menu.addSeparator()
        
        clear_action = menu.addAction("Clear All")
        clear_action.triggered.connect(self._clear_display_table)
        
        menu.exec(self.display_table.viewport().mapToGlobal(pos))

    def _delete_display_row(self, row: int):
        """Delete a row from display table"""
        self.display_table.removeRow(row)
        self._update_display_source_label()
        self._update_sql_preview()
        self._update_field_indicators()
        self.update_table_indicators()

    def _delete_selected_row(self):
        """Delete the currently selected row"""
        row = self.display_table.currentRow()
        if row >= 0:
            self._delete_display_row(row)

    def _move_selected_row_up(self):
        """Move the selected row up"""
        row = self.display_table.currentRow()
        if row > 0:
            self._move_row_up(row)

    def _move_selected_row_down(self):
        """Move the selected row down"""
        row = self.display_table.currentRow()
        if row >= 0 and row < self.display_table.rowCount() - 1:
            self._move_row_down(row)

    def _display_table_key_press(self, event):
        """Handle keyboard events for display table"""
        from PyQt6.QtWidgets import QTableWidget
        if event.key() == Qt.Key.Key_Delete:
            self._delete_selected_row()
        elif event.key() == Qt.Key.Key_Up and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._move_selected_row_up()
        elif event.key() == Qt.Key.Key_Down and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._move_selected_row_down()
        else:
            # Call the parent's keyPressEvent
            QTableWidget.keyPressEvent(self.display_table, event)

    def _clear_display_table(self):
        """Clear all rows from display table"""
        self.display_table.setRowCount(0)
        self.tables_involved.clear()
        if hasattr(self, '_tables_tab_manual_tables'):
            self._tables_tab_manual_tables.clear()
        self._update_display_source_label()
        self._update_sql_preview()
        self._update_field_indicators()
        self.update_table_indicators()

    def _move_display_row(self, from_row: int, to_row: int):
        """Move a row in the display table by swapping with adjacent row"""
        if from_row == to_row:
            return
        
        if from_row < 0 or from_row >= self.display_table.rowCount():
            return
        if to_row < 0 or to_row >= self.display_table.rowCount():
            return
        
        col_count = self.display_table.columnCount()
        
        # Capture complete row data for both rows
        from_row_data = self._capture_row_data(from_row)
        to_row_data = self._capture_row_data(to_row)
        
        # Swap the data
        self._restore_row_data(to_row, from_row_data)
        self._restore_row_data(from_row, to_row_data)
        
        # Select the moved row
        self.display_table.selectRow(to_row)
        self._update_sql_preview()
    
    def _capture_row_data(self, row: int) -> dict:
        """Capture all data from a row"""
        data = {
            'items': {},
            'combos': {}
        }
        
        for col in range(self.display_table.columnCount()):
            item = self.display_table.item(row, col)
            widget = self.display_table.cellWidget(row, col)
            
            if item:
                data['items'][col] = {
                    'text': item.text(),
                    'user_data': item.data(Qt.ItemDataRole.UserRole)
                }
            
            if widget and isinstance(widget, QComboBox):
                data['combos'][col] = {
                    'value': widget.currentText(),
                    'items': [widget.itemText(i) for i in range(widget.count())]
                }
        
        return data
    
    def _restore_row_data(self, row: int, data: dict):
        """Restore row data from captured data"""
        combo_style = """
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 2px;
                padding: 1px 3px 1px 5px;
                background: white;
                font-size: 11px;
            }
            QComboBox:hover {
                border: 1px solid #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox::down-arrow {
                image: url(none);
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid #555;
                width: 0;
                height: 0;
                margin-right: 3px;
            }
        """
        
        # Restore items
        for col, item_data in data['items'].items():
            item = QTableWidgetItem(item_data['text'])
            if item_data['user_data']:
                item.setData(Qt.ItemDataRole.UserRole, item_data['user_data'])
            self.display_table.setItem(row, col, item)
        
        # Restore combo widgets
        for col, combo_data in data['combos'].items():
            # Remove existing widget first
            existing = self.display_table.cellWidget(row, col)
            if existing:
                self.display_table.removeCellWidget(row, col)
            
            combo = QComboBox()
            combo.addItems(combo_data['items'])
            combo.setCurrentText(combo_data['value'])
            combo.setStyleSheet(combo_style)
            combo.currentTextChanged.connect(self._update_sql_preview)
            self.display_table.setCellWidget(row, col, combo)

    def _toggle_display_view(self):
        """Toggle between compact table and tile view"""
        self._compact_view = not self.view_toggle_btn.isChecked()
        
        if self._compact_view:
            self.display_table.setVisible(True)
            self.display_tile_scroll.setVisible(False)
            self.view_toggle_btn.setText("📊 Tile View")
        else:
            self.display_table.setVisible(False)
            self.display_tile_scroll.setVisible(True)
            self.view_toggle_btn.setText("📋 Table View")
            # Sync tile view from table data
            self._sync_tile_view_from_table()

    def _sync_tile_view_from_table(self):
        """Sync tile view with table data"""
        # Clear existing tiles
        while self.display_tile_layout.count():
            item = self.display_tile_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Create tiles for each row
        for row in range(self.display_table.rowCount()):
            field_item = self.display_table.item(row, 0)
            if field_item:
                field_data = field_item.data(Qt.ItemDataRole.UserRole)
                if field_data:
                    tile = self._create_field_tile(field_data)
                    self.display_tile_layout.addWidget(tile)
        
        self.display_tile_layout.addStretch()

    def _create_field_tile(self, field_data: dict) -> QWidget:
        """Create a tile widget for a field (for tile view)"""
        tile = QFrame()
        tile.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 2px solid #27ae60;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        
        layout = QVBoxLayout(tile)
        layout.setSpacing(4)
        
        # Field name
        name_label = QLabel(field_data.get('field_name', ''))
        name_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(name_label)
        
        # Table name
        table_label = QLabel(f"📊 {field_data.get('table_name', '')}")
        table_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        layout.addWidget(table_label)
        
        return tile

    # ==================== CRITERIA TAB HANDLERS ====================

    def _add_criteria_field(self, field_data: dict, row_index: int):
        """Add a field to the criteria table with embedded combo widgets
        
        Columns: Field Name (0), Table (1), Data Type (2), Match Type (3), List (4), Edit (5), Value (6)
        """
        row = row_index if row_index < self.criteria_table.rowCount() else self.criteria_table.rowCount()
        self.criteria_table.insertRow(row)
        
        # Column 0: Field name (read-only)
        field_name = field_data.get('field_name', '')
        field_item = QTableWidgetItem(field_name)
        field_item.setData(Qt.ItemDataRole.UserRole, field_data)
        field_item.setFlags(field_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.criteria_table.setItem(row, 0, field_item)
        
        # Column 1: Table name (read-only)
        table_name = field_data.get('table_name', '')
        table_item = QTableWidgetItem(table_name)
        table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.criteria_table.setItem(row, 1, table_item)
        
        # Column 2: Data Type (read-only)
        data_type = field_data.get('data_type', 'CHAR')
        data_type_item = QTableWidgetItem(data_type)
        data_type_item.setFlags(data_type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        data_type_item.setForeground(QBrush(QColor('#666666')))  # Grey text
        self.criteria_table.setItem(row, 2, data_type_item)
        
        # Column 3: Match type combo (embedded widget) - options based on data type
        match_combo = self._create_match_combo(data_type)
        match_combo.setCurrentText("Exact")
        # Connect to handler that updates value widget when match type changes
        match_combo.currentTextChanged.connect(lambda text, r=row, dt=data_type: self._on_match_type_changed(r, dt))
        self.criteria_table.setCellWidget(row, 3, match_combo)
        
        # Column 4: List button (for selecting from unique values)
        list_btn = self._create_criteria_list_button(row, field_data)
        self.criteria_table.setCellWidget(row, 4, list_btn)
        
        # Column 5: Edit button (pen icon to open larger editor)
        edit_btn = self._create_criteria_edit_button(row)
        self.criteria_table.setCellWidget(row, 5, edit_btn)
        
        # Column 6: Value (editable - type depends on data type)
        category = self._get_data_type_category(data_type)
        if category == 'date':
            # Use date picker for date types
            date_widget = self._create_date_value_widget(row)
            self.criteria_table.setCellWidget(row, 6, date_widget)
            # Also set a blank item for compatibility
            value_item = QTableWidgetItem("")
            self.criteria_table.setItem(row, 6, value_item)
        else:
            # Regular text input
            value_item = QTableWidgetItem("")
            value_item.setToolTip("Click or double-click to edit value")
            self.criteria_table.setItem(row, 6, value_item)
        
        self._update_sql_preview()
        self._update_criteria_indicators()

    def _create_criteria_list_button(self, row: int, field_data: dict) -> QPushButton:
        """Create a list button for selecting from unique values"""
        btn = QPushButton("☰")
        btn.setFixedSize(24, 22)
        
        # Check if unique values are already cached for this field
        table_name = field_data.get('table_name', '')
        field_name = field_data.get('field_name', '')
        schema_name = field_data.get('schema_name', self.current_schema_name or '')
        cache_key = f"{table_name}.{field_name}"
        
        # First check memory cache
        cached_values = self.unique_values_cache.get(cache_key)
        
        # If not in memory, check database cache (from My Data screen)
        if not cached_values and self.current_connection_id:
            try:
                # Try with provided schema_name first
                metadata_id = None
                db_cached = None
                
                # First try with the schema_name we have
                if schema_name:
                    metadata_id = self.metadata_cache_repo.get_metadata_id(
                        self.current_connection_id,
                        table_name,
                        schema_name
                    )
                    if metadata_id:
                        db_cached = self.metadata_cache_repo.get_cached_unique_values(
                            metadata_id,
                            field_name
                        )
                
                # If not found (schema was empty or no cached values), try to find any matching entry
                if not db_cached:
                    # Search for any cached unique values for this table/column combination
                    from suiteview.data.database import get_database
                    db = get_database()
                    row_data = db.fetchone("""
                        SELECT tm.metadata_id, tm.schema_name 
                        FROM table_metadata tm
                        JOIN unique_values_cache uvc ON tm.metadata_id = uvc.metadata_id
                        WHERE tm.connection_id = ? AND tm.table_name = ? AND uvc.column_name = ?
                        LIMIT 1
                    """, (self.current_connection_id, table_name, field_name))
                    
                    if row_data:
                        metadata_id = row_data[0]
                        db_cached = self.metadata_cache_repo.get_cached_unique_values(
                            metadata_id,
                            field_name
                        )
                
                if db_cached and db_cached.get('unique_values'):
                    cached_values = db_cached['unique_values']
                    # Store in memory cache for quick access
                    self.unique_values_cache[cache_key] = cached_values
            except Exception as e:
                logger.debug(f"Could not load cached unique values: {e}")
        
        has_values = cached_values is not None and len(cached_values) > 0
        
        if has_values:
            # Values available - blue style (matching dbquery_screen)
            btn.setProperty("unique_values", cached_values)
            btn.setProperty("selected_values", cached_values[:])  # All selected by default
            btn.setEnabled(True)
            btn.setToolTip(f"Select from {len(cached_values)} unique values\nRight-click for options")
            btn.setStyleSheet("""
                QPushButton {
                    background: white;
                    color: #3498db;
                    border: 2px solid #3498db;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 0px;
                }
                QPushButton:hover {
                    background: #e3f2fd;
                }
            """)
        else:
            # No values yet - grey style, still clickable for right-click
            btn.setEnabled(True)  # Keep enabled so right-click works
            btn.setToolTip("Right-click to fetch unique values")
            btn.setStyleSheet("""
                QPushButton {
                    background: #f5f5f5;
                    color: #888;
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #e8e8e8;
                    color: #666;
                }
            """)
        
        # Store row reference for later
        btn.setProperty("row", row)
        btn.setProperty("field_data", field_data)
        btn.setProperty("has_values", has_values)
        btn.clicked.connect(lambda checked, r=row: self._on_list_button_clicked(r))
        
        # Enable right-click context menu on the button
        btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        btn.customContextMenuRequested.connect(lambda pos, r=row: self._show_list_button_context_menu(r, pos))
        
        return btn

    def _create_criteria_edit_button(self, row: int) -> QPushButton:
        """Create an edit button (pen icon) to open the larger value editor"""
        btn = QPushButton("✎")
        btn.setFixedSize(24, 22)
        btn.setToolTip("Open editor for entering complex values")
        btn.setStyleSheet("""
            QPushButton {
                background: white;
                color: #e67e22;
                border: 2px solid #e67e22;
                border-radius: 3px;
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background: #fef5e7;
            }
        """)
        btn.clicked.connect(lambda checked, r=row: self._open_criteria_value_editor(r))
        return btn
    
    def _on_list_button_clicked(self, row: int):
        """Handle click on list button - open value list if available, else show message"""
        list_btn = self.criteria_table.cellWidget(row, 4)  # List is column 4
        if not list_btn:
            return
        
        has_values = list_btn.property("has_values")
        if has_values:
            self._open_criteria_value_list(row)
        else:
            # No values - offer to fetch
            reply = QMessageBox.question(
                self, "Fetch Values?",
                "No unique values loaded for this field.\nWould you like to fetch them now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._fetch_criteria_unique_values(row)

    def _show_list_button_context_menu(self, row: int, pos: QPoint):
        """Show context menu when right-clicking the list button"""
        list_btn = self.criteria_table.cellWidget(row, 4)  # List is column 4
        if not list_btn:
            return
        
        field_data = list_btn.property("field_data")
        if not field_data:
            return
        
        field_name = field_data.get('field_name', 'field')
        
        menu = QMenu(self)
        
        # Check if values are already loaded
        has_values = list_btn.property("unique_values") is not None
        
        if has_values:
            # Option to refresh values
            refresh_action = menu.addAction(f"🔄 Refresh Unique Values for {field_name}")
            refresh_action.triggered.connect(lambda checked, r=row: self._fetch_criteria_unique_values(r))
            
            # Option to clear values
            clear_action = menu.addAction(f"🗑️ Clear Cached Values")
            clear_action.triggered.connect(lambda checked, r=row: self._clear_criteria_unique_values(r))
        else:
            # Fetch values
            fetch_action = menu.addAction(f"🔍 Fetch Unique Values for {field_name}")
            fetch_action.triggered.connect(lambda checked, r=row: self._fetch_criteria_unique_values(r))
        
        menu.exec(list_btn.mapToGlobal(pos))

    def _clear_criteria_unique_values(self, row: int):
        """Clear cached unique values for a criteria row"""
        list_btn = self.criteria_table.cellWidget(row, 4)  # List is column 4
        if not list_btn:
            return
        
        field_data = list_btn.property("field_data")
        if field_data:
            table_name = field_data.get('table_name', '')
            field_name = field_data.get('field_name', '')
            cache_key = f"{table_name}.{field_name}"
            if cache_key in self.unique_values_cache:
                del self.unique_values_cache[cache_key]
        
        list_btn.setProperty("unique_values", None)
        list_btn.setEnabled(False)
        list_btn.setToolTip("Right-click to fetch unique values")

    def _open_criteria_value_list(self, row: int):
        """Open value selection dialog for a criteria row"""
        # Get the list button and check if it has unique values
        list_btn = self.criteria_table.cellWidget(row, 4)  # List is column 4
        if not list_btn:
            return
        
        unique_values = list_btn.property("unique_values")
        if not unique_values:
            QMessageBox.information(
                self, "No Values",
                "Right-click on the field in the Fields list to fetch unique values first."
            )
            return
        
        field_data = list_btn.property("field_data")
        field_name = field_data.get('field_name', 'Field') if field_data else 'Field'
        
        # Get current value from cell (column 6)
        value_item = self.criteria_table.item(row, 6)  # Value is column 6
        current_value = value_item.text() if value_item else ""
        
        # Parse current value to get selected items
        currently_selected = []
        if current_value:
            # Parse IN(...) or comma-separated list
            if current_value.upper().startswith("IN(") or current_value.upper().startswith("IN ("):
                # Extract values from IN clause
                inner = current_value[current_value.find("(")+1:current_value.rfind(")")]
                for val in inner.split(","):
                    val = val.strip().strip("'\"")
                    if val in unique_values:
                        currently_selected.append(val)
            else:
                # Single value or comma-separated
                for val in current_value.split(","):
                    val = val.strip().strip("'\"")
                    if val in unique_values:
                        currently_selected.append(val)
        
        if not currently_selected:
            currently_selected = unique_values[:]  # Default: all selected
        
        # Import and show the dialog
        from suiteview.ui.dbquery_screen import ValueSelectionDialog
        
        dialog = ValueSelectionDialog(
            field_name,
            unique_values,
            currently_selected,
            self
        )
        
        # Connect to update the value cell
        dialog.values_selected.connect(lambda vals, r=row: self._update_criteria_value_from_list(r, vals, unique_values))
        dialog.show()

    def _update_criteria_value_from_list(self, row: int, selected_values: list, all_values: list):
        """Update criteria value cell from list selection"""
        value_item = self.criteria_table.item(row, 6)  # Value is column 6
        if not value_item:
            return
        
        all_selected = len(selected_values) == len(all_values)
        
        if all_selected:
            # All selected - clear the value (no filter)
            value_item.setText("")
        elif len(selected_values) == 1:
            # Single value
            value_item.setText(selected_values[0])
        else:
            # Multiple values - create IN clause
            quoted = [f"'{v}'" for v in selected_values]
            value_item.setText(f"IN ({', '.join(quoted)})")
        
        # Update the list button style and stored selected values
        list_btn = self.criteria_table.cellWidget(row, 4)  # List is column 4
        if list_btn:
            # Store selected values on the button
            list_btn.setProperty("selected_values", selected_values[:])
            
            if all_selected:
                # All selected - blue border only
                list_btn.setStyleSheet("""
                    QPushButton {
                        background: white;
                        color: #3498db;
                        border: 2px solid #3498db;
                        border-radius: 3px;
                        font-size: 11px;
                        font-weight: bold;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background: #e3f2fd;
                    }
                """)
            else:
                # Some values filtered - solid blue fill
                list_btn.setStyleSheet("""
                    QPushButton {
                        background: #3498db;
                        color: white;
                        border: 2px solid #3498db;
                        border-radius: 3px;
                        font-size: 11px;
                        font-weight: bold;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background: #2980b9;
                    }
                """)
        
        # Update match type combo
        match_combo = self.criteria_table.cellWidget(row, 3)  # Match Type is column 3
        if match_combo:
            if not all_selected and len(selected_values) > 0:
                # Values are being filtered - set to List and disable
                if match_combo.findText("List") == -1:
                    match_combo.addItem("List")
                match_combo.setCurrentText("List")
                match_combo.setEnabled(False)
                match_combo.setStyleSheet("""
                    QComboBox {
                        background-color: #E0E0E0;
                        color: #808080;
                        font-size: 10px;
                        padding: 2px 4px;
                    }
                """)
            else:
                # All selected or none - restore normal behavior
                match_combo.setEnabled(True)
                # Remove "List" option if it exists and not currently selected
                if match_combo.currentText() != "List":
                    list_index = match_combo.findText("List")
                    if list_index != -1:
                        match_combo.removeItem(list_index)
                match_combo.setStyleSheet("""
                    QComboBox {
                        font-size: 10px;
                        padding: 2px 4px;
                        background: white;
                    }
                """)
        
        self._update_sql_preview()

    def _on_criteria_cell_changed(self, row: int, col: int):
        """Handle cell value changes in criteria table"""
        if col == 6:  # Value column was edited (column 6)
            self._update_sql_preview()

    def _show_criteria_cell_context_menu(self, pos: QPoint):
        """Show context menu for criteria table cells"""
        row = self.criteria_table.rowAt(pos.y())
        col = self.criteria_table.columnAt(pos.x())
        
        if row < 0:
            return
        
        menu = QMenu(self)
        
        # Get field data for this row
        field_item = self.criteria_table.item(row, 0)
        field_data = field_item.data(Qt.ItemDataRole.UserRole) if field_item else None
        
        if field_data:
            field_name = field_data.get('field_name', 'field')
            
            # Add "Fetch Unique Values" option
            fetch_action = menu.addAction(f"🔍 Fetch Unique Values for {field_name}")
            fetch_action.triggered.connect(lambda checked, r=row: self._fetch_criteria_unique_values(r))
            
            menu.addSeparator()
        
        # Standard row actions
        if row > 0:
            move_up_action = menu.addAction("⬆️ Move Up")
            move_up_action.triggered.connect(lambda checked, r=row: self._move_criteria_row_up(r))
        
        if row < self.criteria_table.rowCount() - 1:
            move_down_action = menu.addAction("⬇️ Move Down")
            move_down_action.triggered.connect(lambda checked, r=row: self._move_criteria_row_down(r))
        
        menu.addSeparator()
        
        delete_action = menu.addAction("🗑️ Delete Row")
        delete_action.triggered.connect(lambda checked, r=row: self._delete_criteria_row(r))
        
        menu.exec(self.criteria_table.viewport().mapToGlobal(pos))

    def _fetch_criteria_unique_values(self, row: int):
        """Fetch unique values for a criteria field"""
        field_item = self.criteria_table.item(row, 0)
        table_item = self.criteria_table.item(row, 1)
        
        if not field_item or not table_item:
            return
        
        field_data = field_item.data(Qt.ItemDataRole.UserRole)
        if not field_data:
            # Try to get field name from item text
            field_name = field_item.text()
            table_name = table_item.text()
            schema_name = self.current_schema_name or ''
        else:
            field_name = field_data.get('field_name', field_item.text())
            table_name = field_data.get('table_name', table_item.text())
            schema_name = field_data.get('schema_name', self.current_schema_name or '')
        
        if not field_name or not table_name:
            return
        
        if not self.current_connection_id:
            QMessageBox.warning(self, "No Connection", "Please select a data source first.")
            return
        
        # Show progress
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        
        try:
            # Use schema_discovery to get unique values (same as dbquery_screen)
            unique_values = self.schema_discovery.get_unique_values(
                self.current_connection_id,
                table_name,
                field_name,
                schema_name
            )
            
            if unique_values and len(unique_values) > 0:
                # unique_values is already a list from schema_discovery
                # Filter out empty values just in case
                unique_values = [str(v) for v in unique_values if v is not None and str(v).strip()]
                
                # Store in memory cache for future use
                cache_key = f"{table_name}.{field_name}"
                self.unique_values_cache[cache_key] = unique_values
                
                # Also save to database cache so it shows in My Data screen
                try:
                    metadata_id = self.metadata_cache_repo.get_or_create_metadata(
                        self.current_connection_id,
                        table_name,
                        schema_name
                    )
                    self.metadata_cache_repo.cache_unique_values(
                        metadata_id,
                        field_name,
                        unique_values
                    )
                    logger.info(f"Cached {len(unique_values)} unique values for {table_name}.{field_name}")
                except Exception as e:
                    logger.warning(f"Could not cache unique values to database: {e}")
                
                # Update the list button with values and blue style (matching dbquery_screen)
                list_btn = self.criteria_table.cellWidget(row, 4)  # List is column 4
                if list_btn:
                    list_btn.setProperty("unique_values", unique_values)
                    list_btn.setProperty("has_values", True)
                    list_btn.setProperty("selected_values", unique_values[:])  # All selected by default
                    list_btn.setEnabled(True)
                    list_btn.setToolTip(f"Select from {len(unique_values)} unique values\nRight-click for options")
                    # Update to blue style (matching dbquery_screen)
                    list_btn.setStyleSheet("""
                        QPushButton {
                            background: white;
                            color: #3498db;
                            border: 2px solid #3498db;
                            border-radius: 3px;
                            font-size: 11px;
                            font-weight: bold;
                            padding: 0px;
                        }
                        QPushButton:hover {
                            background: #e3f2fd;
                        }
                    """)
                
                QMessageBox.information(
                    self, "Values Fetched",
                    f"Found {len(unique_values)} unique values for {field_name}.\n"
                    f"Click the ☰ button to select from the list."
                )
            else:
                QMessageBox.information(self, "No Values", f"No values found for {field_name}.")
                
        except Exception as e:
            logger.error(f"Error fetching unique values: {e}")
            QMessageBox.warning(self, "Error", f"Could not fetch values: {str(e)}")
        finally:
            QApplication.restoreOverrideCursor()

    def _open_criteria_value_editor(self, row: int):
        """Open a larger editor dialog for criteria value"""
        from PyQt6.QtWidgets import QDialog, QTextEdit
        
        # Get field name for title
        field_item = self.criteria_table.item(row, 0)
        field_name = field_item.text() if field_item else "Value"
        
        # Get current value (column 6)
        value_item = self.criteria_table.item(row, 6)  # Value is column 6
        current_value = value_item.text() if value_item else ""
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit Value - {field_name}")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(200)
        
        layout = QVBoxLayout(dialog)
        
        # Instructions
        instructions = QLabel("Enter your filter value below. Use commas for multiple values.")
        instructions.setStyleSheet("font-size: 10px; color: #666;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Text input
        text_edit = QTextEdit()
        text_edit.setPlaceholderText("Enter filter value(s)...")
        text_edit.setPlainText(current_value)
        text_edit.setStyleSheet("""
            QTextEdit {
                font-size: 11px;
                font-family: 'Courier New', monospace;
                background: white;
            }
        """)
        layout.addWidget(text_edit)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(lambda: text_edit.clear())
        button_layout.addWidget(clear_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        ok_btn.setDefault(True)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
        
        # Show dialog and process result
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_value = text_edit.toPlainText().strip()
            if value_item:
                value_item.setText(new_value)
            self._update_sql_preview()
        
        self._update_sql_preview()
        self._update_criteria_indicators()

    def _get_data_type_category(self, data_type: str) -> str:
        """Categorize a SQL data type as 'numeric', 'date', or 'string'.
        
        Returns:
            'numeric' for INT, DECIMAL, FLOAT, etc.
            'date' for DATE, DATETIME, TIMESTAMP, etc.
            'string' for CHAR, VARCHAR, TEXT, etc.
        """
        if not data_type:
            return 'string'
        
        dtype_upper = data_type.upper()
        
        # Numeric types
        numeric_types = ['INT', 'INTEGER', 'SMALLINT', 'BIGINT', 'TINYINT',
                        'DECIMAL', 'NUMERIC', 'FLOAT', 'REAL', 'DOUBLE',
                        'MONEY', 'SMALLMONEY', 'NUMBER', 'DEC']
        for nt in numeric_types:
            if nt in dtype_upper:
                return 'numeric'
        
        # Date/time types
        date_types = ['DATE', 'TIME', 'DATETIME', 'DATETIME2', 'SMALLDATETIME',
                     'TIMESTAMP', 'DATETIMEOFFSET']
        for dt in date_types:
            if dt in dtype_upper:
                return 'date'
        
        # Default to string
        return 'string'
    
    def _is_numeric_type(self, data_type: str) -> bool:
        """Check if a data type is numeric."""
        return self._get_data_type_category(data_type) == 'numeric'
    
    def _is_date_type(self, data_type: str) -> bool:
        """Check if a data type is a date/time type."""
        return self._get_data_type_category(data_type) == 'date'

    def _create_match_combo(self, data_type: str = 'CHAR') -> QComboBox:
        """Create a Match Type combo box for criteria table with appropriate options based on data type.
        
        Args:
            data_type: The SQL data type of the field (e.g., 'VARCHAR', 'INT', 'DATE')
        
        Returns:
            QComboBox with appropriate match type options
        """
        combo = QComboBox()
        
        # Determine which options to show based on data type category
        category = self._get_data_type_category(data_type)
        
        if category == 'numeric':
            # Numeric types: Exact, Range, List, Expression, Is Null, Is Not Null
            # No Contains, Starts, Ends (these are for strings only)
            combo.addItems(["Exact", "Range", "List", "Expression", "Is Null", "Is Not Null"])
        elif category == 'date':
            # Date types: Exact, Range, List, Expression, Is Null, Is Not Null
            # No Contains, Starts, Ends (these are for strings only)
            combo.addItems(["Exact", "Range", "List", "Expression", "Is Null", "Is Not Null"])
        else:
            # String types: All options except Range
            combo.addItems(["Exact", "Contains", "Starts", "Ends", "List", "Expression", "Is Null", "Is Not Null"])
        combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 2px;
                padding: 1px 3px 1px 5px;
                background: white;
                font-size: 11px;
            }
            QComboBox:hover {
                border: 1px solid #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox::down-arrow {
                image: url(none);
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid #555;
                width: 0;
                height: 0;
                margin-right: 3px;
            }
        """)
        combo.currentTextChanged.connect(self._update_sql_preview)
        return combo

    def _create_range_value_widget(self, data_type: str, row: int) -> QWidget:
        """Create a value widget for Range match type with two inputs.
        
        Args:
            data_type: The SQL data type ('numeric' or 'date')
            row: The row index in criteria table
        
        Returns:
            QWidget containing low value input, 'to' label, and high value input
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)
        
        category = self._get_data_type_category(data_type)
        
        if category == 'date':
            # Use line edits with placeholder for date format
            low_input = QLineEdit()
            low_input.setPlaceholderText("mm/dd/yyyy")
            low_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    padding: 1px 3px;
                    font-size: 10px;
                    min-width: 75px;
                    background-color: white;
                    color: black;
                }
                QLineEdit:focus {
                    border: 1px solid #0078d4;
                }
            """)
            low_input.textChanged.connect(self._update_sql_preview)
            low_input.setProperty("is_date", True)
            
            high_input = QLineEdit()
            high_input.setPlaceholderText("mm/dd/yyyy")
            high_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    padding: 1px 3px;
                    font-size: 10px;
                    min-width: 75px;
                    background-color: white;
                    color: black;
                }
                QLineEdit:focus {
                    border: 1px solid #0078d4;
                }
            """)
            high_input.textChanged.connect(self._update_sql_preview)
            high_input.setProperty("is_date", True)
        else:
            # Use line edits for numeric types
            low_input = QLineEdit()
            low_input.setPlaceholderText("low value")
            low_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    padding: 1px 3px;
                    font-size: 10px;
                    min-width: 60px;
                }
            """)
            low_input.textChanged.connect(self._update_sql_preview)
            
            high_input = QLineEdit()
            high_input.setPlaceholderText("high value")
            high_input.setStyleSheet("""
                QLineEdit {
                    border: 1px solid #ccc;
                    border-radius: 2px;
                    padding: 1px 3px;
                    font-size: 10px;
                    min-width: 60px;
                }
            """)
            high_input.textChanged.connect(self._update_sql_preview)
        
        # Store property to identify low/high inputs
        low_input.setProperty("range_type", "low")
        high_input.setProperty("range_type", "high")
        
        to_label = QLabel("to")
        to_label.setStyleSheet("color: #666; font-size: 10px;")
        
        layout.addWidget(low_input)
        layout.addWidget(to_label)
        layout.addWidget(high_input)
        layout.addStretch()
        
        return container

    def _create_date_value_widget(self, row: int) -> QWidget:
        """Create a date input widget for date field values (simple text input with mm/dd/yyyy format).
        
        Args:
            row: The row index in criteria table
        
        Returns:
            QWidget containing a date input field
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)
        
        date_input = QLineEdit()
        date_input.setPlaceholderText("mm/dd/yyyy")
        date_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 2px;
                padding: 1px 3px;
                font-size: 10px;
                min-width: 80px;
                background-color: white;
                color: black;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
            }
        """)
        date_input.textChanged.connect(self._update_sql_preview)
        date_input.setProperty("date_value", True)
        date_input.setProperty("is_date", True)
        
        layout.addWidget(date_input)
        layout.addStretch()
        
        return container
    
    def _get_range_values(self, row: int) -> tuple:
        """Get the low and high values from a Range value widget.
        
        Args:
            row: The row index in criteria table
        
        Returns:
            Tuple of (low_value, high_value) as strings
        """
        value_widget = self.criteria_table.cellWidget(row, 6)  # Value is column 6
        if not value_widget:
            return ('', '')
        
        low_value = ''
        high_value = ''
        
        # Find the low and high inputs within the container
        for child in value_widget.findChildren(QLineEdit):
            range_type = child.property("range_type")
            text = child.text().strip()
            
            # Check if this is a date input that needs conversion
            if child.property("is_date") and text:
                # Convert mm/dd/yyyy to yyyy-MM-dd for SQL
                text = self._convert_date_to_sql_format(text)
            
            if range_type == "low":
                low_value = text
            elif range_type == "high":
                high_value = text
        
        return (low_value, high_value)
    
    def _convert_date_to_sql_format(self, date_str: str) -> str:
        """Convert a date string from mm/dd/yyyy format to yyyy-MM-dd for SQL.
        
        Args:
            date_str: Date string in mm/dd/yyyy format
        
        Returns:
            Date string in yyyy-MM-dd format, or original string if conversion fails
        """
        if not date_str:
            return date_str
        
        # Try to parse mm/dd/yyyy format
        parts = date_str.split('/')
        if len(parts) == 3:
            try:
                month = parts[0].zfill(2)
                day = parts[1].zfill(2)
                year = parts[2]
                # Pad year if needed
                if len(year) == 2:
                    year = '20' + year if int(year) < 50 else '19' + year
                return f"{year}-{month}-{day}"
            except (ValueError, IndexError):
                pass
        
        # Return original if not in expected format
        return date_str

    def _normalize_date_in_list_clause(self, value: str) -> str:
        """Normalize a user-entered/List-match value into a safe IN(...) clause for date fields.

        - Ensures date literals are wrapped in single quotes.
        - Converts mm/dd/yyyy to yyyy-MM-dd.
        - Preserves already-quoted values and common SQL date expressions.

        Returns:
            A string like: "IN ('2025-12-18', '2025-12-19')"
        """
        raw = (value or "").strip()
        if not raw:
            return "IN ()"

        # Extract inner list from "IN (...)" if provided; otherwise treat whole value as comma-separated
        inner = raw
        if raw.upper().startswith("IN"):
            match = re.search(r"\((.*)\)", raw)
            if match:
                inner = match.group(1)
            else:
                inner = raw[2:].strip()

        parts = [p.strip() for p in inner.split(",") if p.strip()]
        normalized_parts: list[str] = []

        for part in parts:
            upper = part.upper()
            # Keep common SQL expressions as-is
            if upper in {"CURRENT DATE", "CURRENT_DATE"}:
                normalized_parts.append(part)
                continue
            if re.match(r"(?i)^(DATE|TIMESTAMP)\s*\(.*\)$", part):
                normalized_parts.append(part)
                continue

            # If already quoted, normalize double quotes to single quotes
            if (len(part) >= 2) and ((part[0] == "'" and part[-1] == "'") or (part[0] == '"' and part[-1] == '"')):
                unquoted = part[1:-1]
                unquoted = self._convert_date_to_sql_format(unquoted.strip())
                normalized_parts.append("'" + unquoted.replace("'", "''") + "'")
                continue

            # Otherwise treat as a date literal
            converted = self._convert_date_to_sql_format(part)
            normalized_parts.append("'" + converted.replace("'", "''") + "'")

        return f"IN ({', '.join(normalized_parts)})"
    
    def _convert_date_to_display_format(self, date_str: str) -> str:
        """Convert a date string from yyyy-MM-dd format to mm/dd/yyyy for display.
        
        Args:
            date_str: Date string in yyyy-MM-dd format
        
        Returns:
            Date string in mm/dd/yyyy format, or original string if conversion fails
        """
        if not date_str:
            return date_str
        
        # Try to parse yyyy-MM-dd format
        parts = date_str.split('-')
        if len(parts) == 3:
            try:
                year = parts[0]
                month = parts[1]
                day = parts[2]
                return f"{month}/{day}/{year}"
            except (ValueError, IndexError):
                pass
        
        # Return original if not in expected format
        return date_str
    
    def _get_date_value(self, row: int) -> str:
        """Get the value from a date input widget.
        
        Args:
            row: The row index in criteria table
        
        Returns:
            Date value as string in yyyy-MM-dd format
        """
        value_widget = self.criteria_table.cellWidget(row, 6)  # Value is column 6
        if not value_widget:
            return ''
        
        for child in value_widget.findChildren(QLineEdit):
            if child.property("date_value"):
                text = child.text().strip()
                if text:
                    return self._convert_date_to_sql_format(text)
        
        return ''

    def _on_match_type_changed(self, row: int, data_type: str):
        """Handle match type change to update the value widget appropriately.
        
        Args:
            row: The row index in criteria table
            data_type: The SQL data type of the field
        """
        match_widget = self.criteria_table.cellWidget(row, 3)  # Match Type is column 3
        if not match_widget or not isinstance(match_widget, QComboBox):
            return
        
        match_type = match_widget.currentText()
        category = self._get_data_type_category(data_type)
        
        # Clear any existing value widget
        existing_widget = self.criteria_table.cellWidget(row, 6)
        if existing_widget:
            self.criteria_table.removeCellWidget(row, 6)
        
        if match_type == "Range":
            # Create range widget with two inputs
            range_widget = self._create_range_value_widget(data_type, row)
            self.criteria_table.setCellWidget(row, 6, range_widget)
            # Clear the table item text (we're using widget now)
            value_item = self.criteria_table.item(row, 6)
            if value_item:
                value_item.setText("")
        elif match_type in ["Is Null", "Is Not Null"]:
            # No value needed - just set a placeholder
            value_item = self.criteria_table.item(row, 6)
            if value_item:
                value_item.setText("")
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        elif category == 'date' and match_type not in ["List", "Expression"]:
            # Use date picker for date types (except List and Expression)
            date_widget = self._create_date_value_widget(row)
            self.criteria_table.setCellWidget(row, 6, date_widget)
            value_item = self.criteria_table.item(row, 6)
            if value_item:
                value_item.setText("")
        else:
            # Regular text input - ensure it's editable
            value_item = self.criteria_table.item(row, 6)
            if value_item:
                value_item.setFlags(value_item.flags() | Qt.ItemFlag.ItemIsEditable)
        
        self._update_sql_preview()

    def _insert_criteria_row(self, from_row: int, to_row: int):
        """Insert a criteria row at a new position (drag and drop reorder)."""
        if from_row == to_row or from_row < 0 or to_row < 0:
            return
        
        if from_row >= self.criteria_table.rowCount():
            return
        
        # Capture the row data
        row_data = self._capture_criteria_row_data(from_row)
        
        # Remove the original row
        self.criteria_table.removeRow(from_row)
        
        # Adjust to_row if we removed a row before it
        if from_row < to_row:
            to_row -= 1
        
        # Insert new row at target position
        self.criteria_table.insertRow(to_row)
        
        # Restore the data
        self._restore_criteria_row_data(to_row, row_data)
        
        # Select the moved row
        self.criteria_table.selectRow(to_row)
        self._update_sql_preview()

    def _capture_criteria_row_data(self, row: int) -> dict:
        """Capture all data from a criteria row
        
        Columns: 0=Field Name, 1=Table, 2=Data Type, 3=Match Type (combo), 4=List (button), 5=Edit (button), 6=Value
        """
        data = {
            'items': {},
            'combos': {},
            'list_button': None
        }
        
        for col in range(self.criteria_table.columnCount()):
            item = self.criteria_table.item(row, col)
            widget = self.criteria_table.cellWidget(row, col)
            
            if item:
                data['items'][col] = {
                    'text': item.text(),
                    'user_data': item.data(Qt.ItemDataRole.UserRole)
                }
            
            if widget:
                if isinstance(widget, QComboBox):
                    data['combos'][col] = {
                        'value': widget.currentText(),
                        'items': [widget.itemText(i) for i in range(widget.count())]
                    }
                elif isinstance(widget, QPushButton) and col == 4:
                    # List button - capture its properties
                    data['list_button'] = {
                        'field_data': widget.property("field_data"),
                        'unique_values': widget.property("unique_values"),
                        'enabled': widget.isEnabled()
                    }
        
        return data

    def _restore_criteria_row_data(self, row: int, data: dict):
        """Restore criteria row data from captured data
        
        Columns: 0=Field Name, 1=Table, 2=Data Type, 3=Match Type (combo), 4=List (button), 5=Edit (button), 6=Value
        """
        # Restore items
        for col, item_data in data['items'].items():
            item = QTableWidgetItem(item_data['text'])
            if item_data['user_data']:
                item.setData(Qt.ItemDataRole.UserRole, item_data['user_data'])
            self.criteria_table.setItem(row, col, item)
        
        # Restore combo widgets (column 3 = Match Type)
        for col, combo_data in data['combos'].items():
            if col == 3:  # Match Type
                combo = self._create_match_combo()
                combo.setCurrentText(combo_data['value'])
                self.criteria_table.setCellWidget(row, col, combo)
        
        # Restore list button (column 4)
        if data.get('list_button'):
            btn_data = data['list_button']
            field_data = btn_data.get('field_data', {})
            btn = self._create_criteria_list_button(row, field_data)
            if btn_data.get('unique_values'):
                btn.setProperty("unique_values", btn_data['unique_values'])
                btn.setEnabled(True)
            else:
                btn.setEnabled(btn_data.get('enabled', False))
            self.criteria_table.setCellWidget(row, 4, btn)
        
        # Restore edit button (column 5)
        edit_btn = self._create_criteria_edit_button(row)
        self.criteria_table.setCellWidget(row, 5, edit_btn)

    def _show_criteria_row_context_menu(self, pos: QPoint):
        """Show context menu for criteria table vertical header (row numbers)"""
        row = self.criteria_table.verticalHeader().logicalIndexAt(pos)
        
        menu = QMenu(self)
        
        if row >= 0:
            # Select the row first so user sees which row is being affected
            self.criteria_table.selectRow(row)
            
            # Move up action (if not first row)
            if row > 0:
                move_up_action = menu.addAction("⬆️ Move Up")
                move_up_action.triggered.connect(lambda checked, r=row: self._move_criteria_row_up(r))
            
            # Move down action (if not last row)
            if row < self.criteria_table.rowCount() - 1:
                move_down_action = menu.addAction("⬇️ Move Down")
                move_down_action.triggered.connect(lambda checked, r=row: self._move_criteria_row_down(r))
            
            menu.addSeparator()
            
            delete_action = menu.addAction("🗑️ Delete Row")
            delete_action.triggered.connect(lambda checked, r=row: self._delete_criteria_row(r))
            
            menu.addSeparator()
        
        clear_action = menu.addAction("🧹 Clear All Criteria")
        clear_action.triggered.connect(self._clear_criteria_table)
        
        menu.exec(self.criteria_table.verticalHeader().mapToGlobal(pos))

    def _move_criteria_row_up(self, row: int):
        """Move a criteria row up one position"""
        if row > 0:
            self._swap_criteria_rows(row, row - 1)
            self.criteria_table.selectRow(row - 1)

    def _move_criteria_row_down(self, row: int):
        """Move a criteria row down one position"""
        if row < self.criteria_table.rowCount() - 1:
            self._swap_criteria_rows(row, row + 1)
            self.criteria_table.selectRow(row + 1)

    def _swap_criteria_rows(self, row1: int, row2: int):
        """Swap two criteria rows"""
        data1 = self._capture_criteria_row_data(row1)
        data2 = self._capture_criteria_row_data(row2)
        
        # Clear both rows
        for col in range(self.criteria_table.columnCount()):
            self.criteria_table.setItem(row1, col, None)
            self.criteria_table.setItem(row2, col, None)
            self.criteria_table.removeCellWidget(row1, col)
            self.criteria_table.removeCellWidget(row2, col)
        
        # Restore swapped
        self._restore_criteria_row_data(row1, data2)
        self._restore_criteria_row_data(row2, data1)
        
        self._update_sql_preview()

    def _move_selected_criteria_row_up(self):
        """Move the selected criteria row up"""
        selected = self.criteria_table.selectedItems()
        if selected:
            row = selected[0].row()
            self._move_criteria_row_up(row)

    def _move_selected_criteria_row_down(self):
        """Move the selected criteria row down"""
        selected = self.criteria_table.selectedItems()
        if selected:
            row = selected[0].row()
            self._move_criteria_row_down(row)

    def _delete_selected_criteria_row(self):
        """Delete the selected criteria row"""
        selected = self.criteria_table.selectedItems()
        if selected:
            row = selected[0].row()
            self._delete_criteria_row(row)

    def _criteria_table_key_press(self, event):
        """Handle keyboard shortcuts for criteria table"""
        if event.key() == Qt.Key.Key_Delete:
            self._delete_selected_criteria_row()
        else:
            QTableWidget.keyPressEvent(self.criteria_table, event)

    def _delete_criteria_row(self, row: int):
        """Delete a row from criteria table"""
        self.criteria_table.removeRow(row)
        self._update_sql_preview()
        self._update_criteria_indicators()

    def _clear_criteria_table(self):
        """Clear all rows from criteria table"""
        self.criteria_table.setRowCount(0)
        self._update_sql_preview()
        self._update_field_indicators()

    def _update_criteria_indicators(self):
        """Update indicators - delegates to unified _update_field_indicators"""
        self._update_field_indicators()

    def _toggle_criteria_view(self):
        """Toggle between compact table and tile view for criteria"""
        is_tile = self.criteria_view_toggle.isChecked()
        self.criteria_table.setVisible(not is_tile)
        self.criteria_tile_scroll.setVisible(is_tile)

    # ==================== FIELD HANDLERS ====================

    def _on_field_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on field - add to active tab (Display or Criteria)"""
        field_data = item.data(0, Qt.ItemDataRole.UserRole)
        if field_data:
            # Check which tab is active
            current_tab = self.tabs.currentIndex()
            if current_tab == 1:  # Criteria tab
                self._add_criteria_field(field_data, self.criteria_table.rowCount())
            else:  # Display tab (default) or any other tab
                self._add_display_field(field_data, self.display_table.rowCount())

    def _filter_tables(self, text: str):
        """Filter tables tree by search text"""
        text = text.lower()
        for i in range(self.tables_tree.topLevelItemCount()):
            item = self.tables_tree.topLevelItem(i)
            item.setHidden(text not in item.text(0).lower())

    def _filter_fields(self, text: str):
        """Filter fields tree by search text"""
        text = text.lower()
        for i in range(self.fields_tree.topLevelItemCount()):
            item = self.fields_tree.topLevelItem(i)
            item.setHidden(text not in item.text(0).lower())

    # ==================== PACKAGE HANDLERS ====================

    def _on_package_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on a saved package"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        if item_type == "package":
            package_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            self._load_package(package_id)

    def _load_package(self, package_id: int):
        """Load a saved package"""
        try:
            query = self.query_repo.get_query(package_id)
            if not query:
                logger.error(f"Package {package_id} not found")
                return
            
            self.current_package_id = package_id
            self.current_package_name = query['query_name']
            self.package_name_label.setText(query['query_name'])
            
            definition = query.get('query_definition', {})
            
            # Clear existing data
            self._clear_display_table()
            self._clear_criteria_table()
            
            # Restore connection/data source
            connection_id = definition.get('connection_id')
            if connection_id:
                self.current_connection_id = connection_id
                # Find and select the connection in the dropdowns
                conn = self.conn_repo.get_connection(connection_id)
                if conn:
                    # Set db type dropdown (this triggers _on_db_type_changed which populates connections)
                    # Note: connection uses 'connection_type', not 'db_type'
                    db_type = conn.get('connection_type', '')
                    logger.info(f"Loading package - connection_id={connection_id}, db_type={db_type}, conn_name={conn.get('connection_name')}")
                    
                    type_index = self.db_type_combo.findText(db_type)
                    if type_index >= 0:
                        self.db_type_combo.setCurrentIndex(type_index)
                        # Manually trigger to ensure connections are populated
                        self._on_db_type_changed(db_type)
                    else:
                        logger.warning(f"db_type '{db_type}' not found in combo. Available: {[self.db_type_combo.itemText(i) for i in range(self.db_type_combo.count())]}")
                    
                    # Now set connection dropdown (this triggers _on_connection_changed which loads tables)
                    conn_index = self.connection_combo.findData(connection_id)
                    if conn_index >= 0:
                        self.connection_combo.setCurrentIndex(conn_index)
                        # Manually trigger to ensure tables are loaded
                        self._on_connection_changed(conn.get('connection_name', ''))
                    else:
                        logger.warning(f"connection_id {connection_id} not found in combo. Available data: {[self.connection_combo.itemData(i) for i in range(self.connection_combo.count())]}")
                else:
                    logger.warning(f"Connection {connection_id} not found in database")
            
            # Restore tables involved
            self.tables_involved = set(definition.get('tables', []))

            # Restore joins (Tables tab)
            if hasattr(self, 'joins_tree'):
                self._load_joins_definition(definition)
            
            # Restore display fields
            display_fields = definition.get('display_fields', [])
            for field_def in display_fields:
                row = self.display_table.rowCount()
                self.display_table.insertRow(row)
                
                # Field name with user data
                field_item = QTableWidgetItem(field_def.get('field_name', ''))
                field_item.setData(Qt.ItemDataRole.UserRole, {
                    'field_name': field_def.get('field_name', ''),
                    'table_name': field_def.get('table_name', ''),
                    'data_type': field_def.get('data_type', 'CHAR'),
                    'connection_id': connection_id
                })
                self.display_table.setItem(row, 0, field_item)
                
                # Table name
                self.display_table.setItem(row, 1, QTableWidgetItem(field_def.get('table_name', '')))
                
                # Alias
                self.display_table.setItem(row, 2, QTableWidgetItem(field_def.get('alias', '')))
                
                # Agg combobox
                agg_combo = self._create_agg_combo()
                agg_combo.setCurrentText(field_def.get('agg', ''))
                self.display_table.setCellWidget(row, 3, agg_combo)
                
                # Order combobox
                order_combo = self._create_order_combo()
                order_combo.setCurrentText(field_def.get('order', ''))
                self.display_table.setCellWidget(row, 4, order_combo)
                
                # Having
                self.display_table.setItem(row, 5, QTableWidgetItem(field_def.get('having', '')))
            
            # Restore schema_name from package if available
            package_schema_name = definition.get('schema_name', '')
            if package_schema_name:
                self.current_schema_name = package_schema_name
            
            # Restore criteria
            criteria = definition.get('criteria', [])
            for crit_def in criteria:
                row = self.criteria_table.rowCount()
                self.criteria_table.insertRow(row)
                
                # Column 0: Field Name with data (including schema_name for unique values lookup)
                field_name = crit_def.get('field_name', '')
                table_name = crit_def.get('table_name', '')
                schema_name = crit_def.get('schema_name', package_schema_name)
                data_type = crit_def.get('data_type', 'CHAR')
                field_item = QTableWidgetItem(field_name)
                field_item.setData(Qt.ItemDataRole.UserRole, {
                    'field_name': field_name,
                    'table_name': table_name,
                    'schema_name': schema_name,
                    'data_type': data_type
                })
                field_item.setFlags(field_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.criteria_table.setItem(row, 0, field_item)
                
                # Column 1: Table (read-only)
                table_item = QTableWidgetItem(table_name)
                table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.criteria_table.setItem(row, 1, table_item)
                
                # Column 2: Data Type (read-only)
                data_type_item = QTableWidgetItem(data_type)
                data_type_item.setFlags(data_type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                data_type_item.setForeground(QBrush(QColor('#666666')))
                self.criteria_table.setItem(row, 2, data_type_item)
                
                # Column 3: Match Type combo (options based on data type)
                match_combo = self._create_match_combo(data_type)
                match_type = crit_def.get('match_type', 'Exact')
                # Add "List" option if needed
                if match_type == 'List' and match_combo.findText("List") == -1:
                    match_combo.addItem("List")
                # Add "Range" option if needed (in case stored package uses Range with older combo)
                if match_type == 'Range' and match_combo.findText("Range") == -1:
                    match_combo.addItem("Range")
                match_combo.setCurrentText(match_type)
                # Connect to handler for value widget updates
                match_combo.currentTextChanged.connect(lambda text, r=row, dt=data_type: self._on_match_type_changed(r, dt))
                self.criteria_table.setCellWidget(row, 3, match_combo)
                
                # Column 4: List button (will check database cache for unique values)
                field_data = {'field_name': field_name, 'table_name': table_name, 'schema_name': schema_name, 'data_type': data_type}
                list_btn = self._create_criteria_list_button(row, field_data)
                self.criteria_table.setCellWidget(row, 4, list_btn)
                
                # Column 5: Edit button (pen icon)
                edit_btn = self._create_criteria_edit_button(row)
                self.criteria_table.setCellWidget(row, 5, edit_btn)
                
                # Column 6: Value - handle Range type specially
                value = crit_def.get('value', '')
                category = self._get_data_type_category(data_type)
                
                if match_type == 'Range':
                    # Create range widget
                    range_widget = self._create_range_value_widget(data_type, row)
                    self.criteria_table.setCellWidget(row, 6, range_widget)
                    # Parse stored value (format: "low|high")
                    if '|' in value:
                        low_val, high_val = value.split('|', 1)
                        # Convert yyyy-MM-dd back to mm/dd/yyyy for date inputs
                        if category == 'date':
                            low_val = self._convert_date_to_display_format(low_val)
                            high_val = self._convert_date_to_display_format(high_val)
                        # Set values in range widget
                        for child in range_widget.findChildren(QLineEdit):
                            if child.property("range_type") == "low":
                                child.setText(low_val)
                            elif child.property("range_type") == "high":
                                child.setText(high_val)
                    self.criteria_table.setItem(row, 6, QTableWidgetItem(""))
                elif category == 'date' and match_type not in ['List', 'Expression', 'Is Null', 'Is Not Null']:
                    # Date input widget
                    date_widget = self._create_date_value_widget(row)
                    self.criteria_table.setCellWidget(row, 6, date_widget)
                    # Set date value (convert from yyyy-MM-dd to mm/dd/yyyy)
                    if value:
                        display_val = self._convert_date_to_display_format(value)
                        for child in date_widget.findChildren(QLineEdit):
                            if child.property("date_value"):
                                child.setText(display_val)
                    self.criteria_table.setItem(row, 6, QTableWidgetItem(""))
                else:
                    # Regular text value
                    self.criteria_table.setItem(row, 6, QTableWidgetItem(value))
                
                # If Match Type is List, update button and combo styling
                if match_type == 'List' and value:
                    # Set solid blue button style (values are being filtered)
                    list_btn.setStyleSheet("""
                        QPushButton {
                            background: #3498db;
                            color: white;
                            border: 2px solid #3498db;
                            border-radius: 3px;
                            font-size: 11px;
                            font-weight: bold;
                            padding: 0px;
                        }
                        QPushButton:hover {
                            background: #2980b9;
                        }
                    """)
                    # Disable combo and style as read-only
                    match_combo.setEnabled(False)
                    match_combo.setStyleSheet("""
                        QComboBox {
                            background-color: #E0E0E0;
                            color: #808080;
                            font-size: 10px;
                            padding: 2px 4px;
                        }
                    """)
            
            # Update SQL preview
            sql = definition.get('sql', '')
            if sql:
                # Always format SQL nicely before displaying
                formatted_sql = self._format_sql(sql)
                self.sql_preview.setPlainText(formatted_sql)
            else:
                self._update_sql_preview()
            
            # Update indicators
            self._update_field_indicators()
            self.update_table_indicators()
            self._update_display_source_label()
            
            # If we have tables in the package, select the first one to show its fields
            if self.tables_involved and self.tables_tree.topLevelItemCount() > 0:
                # Find and select the first table that's in the package
                for i in range(self.tables_tree.topLevelItemCount()):
                    item = self.tables_tree.topLevelItem(i)
                    table_data = item.data(0, Qt.ItemDataRole.UserRole)
                    if table_data:
                        table_name = table_data.get('table_name', '')
                        if table_name in self.tables_involved:
                            self.tables_tree.setCurrentItem(item)
                            self._on_table_clicked(item, 0)
                            break
            
            logger.info(f"Loaded package: {self.current_package_name}")
            
        except Exception as e:
            logger.error(f"Error loading package: {e}")
            import traceback
            traceback.print_exc()
    
    def _create_agg_combo(self) -> QComboBox:
        """Create an Agg combobox for display table"""
        combo = QComboBox()
        combo.addItems(["", "COUNT", "SUM", "AVG", "MIN", "MAX", "COUNT DISTINCT"])
        combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 2px;
                padding: 1px 3px 1px 5px;
                background: white;
                font-size: 11px;
            }
            QComboBox:hover {
                border: 1px solid #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox::down-arrow {
                image: url(none);
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid #555;
                width: 0;
                height: 0;
                margin-right: 3px;
            }
        """)
        combo.currentTextChanged.connect(self._update_sql_preview)
        return combo
    
    def _create_order_combo(self) -> QComboBox:
        """Create an Order combobox for display table"""
        combo = QComboBox()
        combo.addItems(["", "ASC", "DESC"])
        combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #ccc;
                border-radius: 2px;
                padding: 1px 3px 1px 5px;
                background: white;
                font-size: 11px;
            }
            QComboBox:hover {
                border: 1px solid #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox::down-arrow {
                image: url(none);
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid #555;
                width: 0;
                height: 0;
                margin-right: 3px;
            }
        """)
        combo.currentTextChanged.connect(self._update_sql_preview)
        return combo

    def _show_package_context_menu(self, pos: QPoint):
        """Show context menu for packages tree"""
        menu = QMenu(self)
        
        item = self.packages_tree.itemAt(pos)
        if item:
            edit_action = menu.addAction("✏️ Open")
            edit_action.triggered.connect(lambda checked, i=item: self._on_package_clicked(i, 0))
            
            menu.addSeparator()
            
            copy_action = menu.addAction("📋 Copy")
            copy_action.triggered.connect(lambda checked, i=item: self._copy_package(i))
            
            rename_action = menu.addAction("📝 Rename")
            rename_action.triggered.connect(lambda checked, i=item: self._rename_package(i))
            
            menu.addSeparator()
            
            delete_action = menu.addAction("🗑️ Delete")
            delete_action.triggered.connect(lambda checked, i=item: self._delete_package(i))
        else:
            new_action = menu.addAction("✨ New Package")
            new_action.triggered.connect(self._new_package)
        
        menu.exec(self.packages_tree.viewport().mapToGlobal(pos))

    def _rename_package(self, item: QTreeWidgetItem):
        """Rename a package"""
        package_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        old_name = item.text(0)
        
        new_name, ok = QInputDialog.getText(self, "Rename Package", "New name:", text=old_name)
        if ok and new_name and new_name != old_name:
            try:
                self.query_repo.update_query_name(package_id, new_name)
                item.setText(0, new_name)
                # Update the package name label if this package is currently open
                if self.current_package_id == package_id:
                    self.current_package_name = new_name
                    self.package_name_label.setText(new_name)
                self.packages_changed.emit()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to rename: {e}")
    
    def _copy_package(self, item: QTreeWidgetItem):
        """Copy a package with a new name"""
        package_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        old_name = item.text(0)
        
        # Suggest a new name
        new_name, ok = QInputDialog.getText(
            self, "Copy Package", 
            "Name for the copy:", 
            text=f"{old_name} (Copy)"
        )
        if ok and new_name:
            try:
                # Get the original package definition
                original = self.query_repo.get_query(package_id)
                if original:
                    # Save as new package with the new name
                    new_id = self.query_repo.save_query(
                        query_name=new_name,
                        query_type='DATAPACKAGE',
                        query_definition=original['query_definition']
                    )
                    # Refresh the packages list
                    self._load_packages()
                    self.packages_changed.emit()
                    QMessageBox.information(self, "Copied", f"Package copied as '{new_name}'.")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to copy: {e}")

    def _delete_package(self, item: QTreeWidgetItem):
        """Delete a package"""
        package_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        name = item.text(0)
        
        reply = QMessageBox.question(
            self, "Delete Package",
            f"Are you sure you want to delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.query_repo.delete_query(package_id)
                idx = self.packages_tree.indexOfTopLevelItem(item)
                self.packages_tree.takeTopLevelItem(idx)
                
                if self.current_package_id == package_id:
                    self._new_package()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to delete: {e}")

    # ==================== ACTIONS ====================

    def _run_query(self):
        """Run the current query"""
        sql = self._build_sql()
        if not sql:
            QMessageBox.warning(self, "No Query", "Please add some fields to the query first.")
            return
        
        # Execute query
        try:
            if not self.current_connection_id:
                QMessageBox.warning(self, "No Connection", "Please select a data source first.")
                return
            
            result = self.query_executor.execute_sql(self.current_connection_id, sql)
            
            # Get execution metadata
            metadata = self.query_executor.get_execution_metadata()
            
            # Show results dialog
            from suiteview.ui.dialogs.query_results_dialog import QueryResultsDialog
            dialog = QueryResultsDialog(result, sql, metadata['execution_time_ms'], self)
            dialog.show()  # Modeless - allows interaction with main app
            
        except Exception as e:
            QMessageBox.critical(self, "Query Error", f"Error executing query:\n{e}")

    def _save_package(self):
        """Save the current package"""
        if not self.current_package_name or self.current_package_name == "unnamed":
            name, ok = QInputDialog.getText(self, "Save Package", "Package name:")
            if not ok or not name:
                return
            self.current_package_name = name
        
        # Build definition
        definition = self._build_package_definition()
        
        try:
            # save_query handles both insert and update (updates if name exists)
            self.current_package_id = self.query_repo.save_query(
                query_name=self.current_package_name,
                query_type='DATAPACKAGE',
                query_definition=definition
            )
            
            self.package_name_label.setText(self.current_package_name)
            self._load_packages()
            self.packages_changed.emit()
            
            QMessageBox.information(self, "Saved", f"Package '{self.current_package_name}' saved.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def _reset_query(self):
        """Reset the current query"""
        reply = QMessageBox.question(
            self, "Reset Query",
            "Are you sure you want to reset? All unsaved changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._clear_display_table()
            self._clear_criteria_table()
            self.sql_preview.clear()

    def _new_package(self):
        """Start a new package"""
        self._clear_display_table()
        self._clear_criteria_table()
        self.sql_preview.clear()
        
        self.current_package_id = None
        self.current_package_name = None
        self.package_name_label.setText("New Package")
        self.tables_involved.clear()
        self._update_display_source_label()

    def _save_as_package(self):
        """Save current query as a new package with a new name"""
        # Always prompt for a new name
        name, ok = QInputDialog.getText(self, "Save As", "New package name:")
        if not ok or not name:
            return
        
        # Check if name already exists
        existing_queries = self.query_repo.get_all_queries(query_type='DATAPACKAGE')
        for q in existing_queries:
            if q['query_name'].lower() == name.lower():
                reply = QMessageBox.question(
                    self, "Name Exists",
                    f"A package named '{name}' already exists. Overwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                break
        
        # Build definition
        definition = self._build_package_definition()
        
        try:
            # Save as new (or overwrite if same name)
            new_id = self.query_repo.save_query(
                query_name=name,
                query_type='DATAPACKAGE',
                query_definition=definition
            )
            
            # Update current package to the new one
            self.current_package_id = new_id
            self.current_package_name = name
            self.package_name_label.setText(name)
            
            self._load_packages()
            self.packages_changed.emit()
            
            QMessageBox.information(self, "Saved", f"Package saved as '{name}'.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def _copy_sql(self):
        """Copy SQL to clipboard"""
        sql = self.sql_preview.toPlainText()
        if sql:
            QApplication.clipboard().setText(sql)
            # Brief visual feedback could be added here

    # ==================== SQL BUILDING ====================

    def _build_sql(self) -> str:
        """Build SQL statement from current state"""
        if self.display_table.rowCount() == 0:
            return ""
        
        # Collect SELECT fields
        select_parts = []
        order_parts = []
        
        for row in range(self.display_table.rowCount()):
            field_item = self.display_table.item(row, 0)
            table_item = self.display_table.item(row, 1)
            alias_item = self.display_table.item(row, 2)
            agg_widget = self.display_table.cellWidget(row, 3)
            order_widget = self.display_table.cellWidget(row, 4)
            
            if not field_item:
                continue
            
            field_name = field_item.text()
            table_name = table_item.text() if table_item else ""
            _alias = alias_item.text() if alias_item else ""
            agg = agg_widget.currentText() if agg_widget and isinstance(agg_widget, QComboBox) else ""
            order = order_widget.currentText() if order_widget and isinstance(order_widget, QComboBox) else ""
            
            # Build field reference
            if table_name:
                field_ref = f"{table_name}.{field_name}"
            else:
                field_ref = field_name
            
            # Apply aggregation
            if agg:
                select_parts.append(f"{agg}({field_ref})")
            else:
                select_parts.append(field_ref)
            
            # Track order by
            if order:
                order_parts.append(f"{field_ref} {order}")
        
        if not select_parts:
            return ""
        
        # Build FROM clause - include schema prefix if available
        from_tables = list(self.tables_involved)
        if not from_tables:
            # Get tables from fields
            for row in range(self.display_table.rowCount()):
                table_item = self.display_table.item(row, 1)
                if table_item and table_item.text():
                    from_tables.append(table_item.text())
            from_tables = list(set(from_tables))
        
        # Build FROM clause
        from_clause_parts: list[str] = []
        join_clause_parts: list[str] = []

        joins_def = self._get_joins_definition() if hasattr(self, 'joins_tree') else {"joins": []}
        joins_list = joins_def.get("joins") or []

        if len(joins_list) > 0:
            base_table = (joins_list[0].get("left_table") or "").strip()
            if base_table:
                # Always provide a correlation name so references like BASE.COL work even when schema-qualified.
                base_target = (
                    f"{self.current_schema_name}.{base_table} {base_table}"
                    if self.current_schema_name
                    else f"{base_table} {base_table}"
                )
                from_clause_parts.append(base_target)

            for j in joins_list:
                join_type = (j.get("join_type") or "INNER JOIN").strip()
                left_table = (j.get("left_table") or "").strip()
                right_table = (j.get("right_table") or "").strip()
                on_list = j.get("on") or []
                if not right_table:
                    continue

                # Always provide a correlation name so references like TABLE.COL resolve.
                join_target = (
                    f"{self.current_schema_name}.{right_table} {right_table}"
                    if self.current_schema_name
                    else f"{right_table} {right_table}"
                )

                on_parts: list[str] = []
                for cond in on_list:
                    left_field = (cond.get("left_field") or "").strip()
                    right_field = (cond.get("right_field") or "").strip()
                    if left_table and right_table and left_field and right_field:
                        on_parts.append(f"{left_table}.{left_field} = {right_table}.{right_field}")

                if on_parts:
                    join_clause_parts.append(
                        f"{join_type} {join_target}\n"
                        f"    ON {on_parts[0]}" +
                        "".join([f"\n    AND {p}" for p in on_parts[1:]])
                    )
                else:
                    join_clause_parts.append(f"{join_type} {join_target}")

            # Keep tables_involved updated for Tables Used + saving
            self.tables_involved |= {j.get('left_table', '') for j in joins_list if j.get('left_table')} | {j.get('right_table', '') for j in joins_list if j.get('right_table')}
        else:
            # Legacy behavior: comma-separated tables with schema prefix and alias
            for table in from_tables:
                if self.current_schema_name:
                    from_clause_parts.append(f"{self.current_schema_name}.{table} {table}")
                else:
                    from_clause_parts.append(table)
        
        # Build WHERE clause
        # Criteria columns: Field Name (0), Table (1), Data Type (2), Match Type combo (3), List button (4), Edit (5), Value (6)
        where_parts = []
        for row in range(self.criteria_table.rowCount()):
            field_item = self.criteria_table.item(row, 0)
            table_item = self.criteria_table.item(row, 1)
            data_type_item = self.criteria_table.item(row, 2)
            value_item = self.criteria_table.item(row, 6)  # Value is column 6
            
            # Get match type from combo widget (column 3)
            match_widget = self.criteria_table.cellWidget(row, 3)
            
            if not field_item:
                continue
            
            field_name = field_item.text()
            table_name = table_item.text() if table_item else ""
            data_type = data_type_item.text() if data_type_item else "CHAR"
            match_type = match_widget.currentText() if match_widget and isinstance(match_widget, QComboBox) else "Exact"
            
            # Build field reference
            if table_name:
                field_ref = f"{table_name}.{field_name}"
            else:
                field_ref = field_name
            
            # Get the data type category to determine quoting
            category = self._get_data_type_category(data_type)
            
            # Handle Is Null and Is Not Null (no value needed)
            if match_type == "Is Null":
                condition = f"{field_ref} IS NULL"
            elif match_type == "Is Not Null":
                condition = f"{field_ref} IS NOT NULL"
            elif match_type == "Range":
                # Get range values from widget
                low_value, high_value = self._get_range_values(row)
                if not low_value and not high_value:
                    continue
                
                if category == 'date':
                    # Date range: use quotes
                    condition = f"{field_ref} BETWEEN '{low_value}' AND '{high_value}'"
                elif category == 'numeric':
                    # Numeric range: no quotes
                    condition = f"{field_ref} BETWEEN {low_value} AND {high_value}"
                else:
                    # String range: use quotes
                    condition = f"{field_ref} BETWEEN '{low_value}' AND '{high_value}'"
            else:
                # Get value from either widget or item
                value = ""
                value_widget = self.criteria_table.cellWidget(row, 6)
                
                if value_widget:
                    # Check for date input widget
                    for child in value_widget.findChildren(QLineEdit):
                        if child.property("date_value"):
                            value = self._convert_date_to_sql_format(child.text().strip())
                            break
                
                if not value and value_item:
                    value = value_item.text()
                
                if not value:
                    continue
                
                # Build condition based on match type
                if match_type == "Exact":
                    if category == 'numeric':
                        condition = f"{field_ref} = {value}"
                    elif category == 'date':
                        condition = f"{field_ref} = '{value}'"
                    else:
                        condition = f"{field_ref} = '{value}'"
                elif match_type == "Contains":
                    condition = f"{field_ref} LIKE '%{value}%'"
                elif match_type == "Starts":
                    condition = f"{field_ref} LIKE '{value}%'"
                elif match_type == "Ends":
                    condition = f"{field_ref} LIKE '%{value}'"
                elif match_type == "List":
                    # List - value already contains IN(...) or is comma-separated
                    # Don't add quotes - user provides the exact value
                    if category == 'date':
                        condition = f"{field_ref} {self._normalize_date_in_list_clause(value)}"
                    else:
                        if value.upper().startswith("IN"):
                            condition = f"{field_ref} {value}"
                        else:
                            # Assume comma-separated, build IN clause
                            condition = f"{field_ref} IN ({value})"
                elif match_type == "Expression":
                    # Expression - use value exactly as provided (no quotes added)
                    condition = f"{field_ref} {value}"
                else:
                    # Default to Exact with quotes
                    condition = f"{field_ref} = '{value}'"
            
            if where_parts:
                where_parts.append(f"AND {condition}")
            else:
                where_parts.append(condition)
        
        # Assemble SQL
        sql = f"SELECT {', '.join(select_parts)}"
        if from_clause_parts:
            sql += f"\nFROM {', '.join(from_clause_parts)}"
        if join_clause_parts:
            sql += "\n" + "\n".join(join_clause_parts)
        
        if where_parts:
            sql += f"\nWHERE {' '.join(where_parts)}"
        
        if order_parts:
            sql += f"\nORDER BY {', '.join(order_parts)}"
        
        return sql

    def _run_custom_query(self):
        """Run the query from the SQL preview box"""
        sql = self.sql_preview.toPlainText().strip()
        if not sql:
            QMessageBox.warning(self, "No Query", "Please enter a SQL query.")
            return
        
        # Execute query
        try:
            if not self.current_connection_id:
                QMessageBox.warning(self, "No Connection", "Please select a data source first.")
                return
            
            result = self.query_executor.execute_sql(self.current_connection_id, sql)
            
            # Get execution metadata
            metadata = self.query_executor.get_execution_metadata()
            
            # Show results dialog
            from suiteview.ui.dialogs.query_results_dialog import QueryResultsDialog
            dialog = QueryResultsDialog(result, sql, metadata['execution_time_ms'], self)
            dialog.show()  # Modeless - allows interaction with main app
            
        except Exception as e:
            QMessageBox.critical(self, "Query Error", f"Error executing query:\n{e}")

    def _format_sql(self, sql: str) -> str:
        """Format SQL with proper indentation"""
        if not sql:
            return ""

        # Preserve line breaks (needed for JOIN/ON/AND formatting).
        sql = sql.replace("\r\n", "\n").strip()

        normalized_lines: list[str] = []
        for line in sql.split("\n"):
            if not line.strip():
                continue
            m = re.match(r"^(\s*)(.*)$", line)
            indent = m.group(1) if m else ""
            content = m.group(2) if m else line
            content = re.sub(r"\s+", " ", content).strip()
            normalized_lines.append(indent + content)

        formatted = "\n".join(normalized_lines)
        
        # Handle SELECT specially to indent columns
        if formatted.startswith("SELECT "):
            # Split the SELECT part from the rest
            parts = formatted.split("\n", 1)
            select_line = parts[0]
            rest = parts[1] if len(parts) > 1 else ""
            
            # Get columns
            cols_str = select_line[7:] # After "SELECT "
            
            # Split by comma, but be careful about functions like COUNT(DISTINCT x)
            # Simple split by comma might break functions.
            # For now, let's assume simple columns or simple aggregations without nested commas
            # If we want to be safer, we can just indent the whole block or use a smarter split
            
            # Let's try to split by comma only if not inside parentheses (simple check)
            cols = []
            current_col = ""
            paren_depth = 0
            
            for char in cols_str:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
                
                if char == ',' and paren_depth == 0:
                    cols.append(current_col.strip())
                    current_col = ""
                else:
                    current_col += char
            
            if current_col:
                cols.append(current_col.strip())
            
            # Reconstruct SELECT
            formatted_select = "SELECT\n    " + ",\n    ".join(cols)
            
            formatted = formatted_select
            if rest:
                formatted += "\n" + rest
                
        return formatted

    def _update_sql_preview(self):
        """Update the SQL preview"""
        sql = self._build_sql()
        formatted_sql = self._format_sql(sql)
        self.sql_preview.setPlainText(formatted_sql)

    def _build_package_definition(self) -> dict:
        """Build package definition for saving"""
        definition = {
            'sql': self._build_sql(),
            'display_fields': [],
            'criteria': [],
            'tables': list(self.tables_involved),
            'connection_id': self.current_connection_id,
            'schema_name': self.current_schema_name or '',
        }

        # Capture joins (Tables tab)
        if hasattr(self, 'joins_tree'):
            joins_def = self._get_joins_definition()
            definition['joins'] = joins_def.get('joins', [])
        
        # Capture display fields
        for row in range(self.display_table.rowCount()):
            field_item = self.display_table.item(row, 0)
            if field_item:
                field_data = field_item.data(Qt.ItemDataRole.UserRole) or {}
                
                # Get Agg from combobox widget (column 3)
                agg_widget = self.display_table.cellWidget(row, 3)
                agg_value = agg_widget.currentText() if agg_widget and isinstance(agg_widget, QComboBox) else ""
                
                # Get Order from combobox widget (column 4)
                order_widget = self.display_table.cellWidget(row, 4)
                order_value = order_widget.currentText() if order_widget and isinstance(order_widget, QComboBox) else ""
                
                # Get Alias from item (column 2)
                alias_item = self.display_table.item(row, 2)
                alias_value = alias_item.text() if alias_item else ""
                
                # Get Having from item (column 5)
                having_item = self.display_table.item(row, 5)
                having_value = having_item.text() if having_item else ""
                
                definition['display_fields'].append({
                    'field_name': field_item.text(),
                    'table_name': self.display_table.item(row, 1).text() if self.display_table.item(row, 1) else "",
                    'alias': alias_value,
                    'agg': agg_value,
                    'order': order_value,
                    'having': having_value,
                    'data_type': field_data.get('data_type', 'CHAR'),
                })
        
        # Capture criteria
        # Columns: Field Name (0), Table (1), Data Type (2), Match Type combo (3), List button (4), Edit (5), Value (6)
        for row in range(self.criteria_table.rowCount()):
            field_item = self.criteria_table.item(row, 0)
            if field_item:
                field_data = field_item.data(Qt.ItemDataRole.UserRole) or {}
                
                # Get Data Type from item (column 2)
                data_type_item = self.criteria_table.item(row, 2)
                data_type = data_type_item.text() if data_type_item else "CHAR"
                
                # Get Match Type from combobox widget (column 3)
                match_widget = self.criteria_table.cellWidget(row, 3)
                match_value = match_widget.currentText() if match_widget and isinstance(match_widget, QComboBox) else "Exact"
                
                # Get Value - check for widget first (Range or Date picker), then item
                value_text = ""
                value_widget = self.criteria_table.cellWidget(row, 6)
                
                if match_value == "Range" and value_widget:
                    # Get range values and store as "low|high" format
                    low_val, high_val = self._get_range_values(row)
                    value_text = f"{low_val}|{high_val}"
                elif value_widget:
                    # Check for date input
                    for child in value_widget.findChildren(QLineEdit):
                        if child.property("date_value"):
                            value_text = self._convert_date_to_sql_format(child.text().strip())
                            break
                
                if not value_text:
                    # Fall back to item text
                    value_item = self.criteria_table.item(row, 6)
                    value_text = value_item.text() if value_item else ""
                
                definition['criteria'].append({
                    'field_name': field_item.text(),
                    'table_name': self.criteria_table.item(row, 1).text() if self.criteria_table.item(row, 1) else "",
                    'schema_name': field_data.get('schema_name', self.current_schema_name or ''),
                    'data_type': data_type,
                    'match_type': match_value,
                    'value': value_text,
                })
        
        return definition
