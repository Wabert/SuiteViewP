"""FilterTableView - Excel-style filterable table view for DataFrames"""

import logging
import time
from typing import Optional, Dict, Set, List, Any
import pandas as pd
from functools import reduce
import operator
from pandas.api.types import is_numeric_dtype
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView, QListView, QAbstractItemView,
                              QHeaderView, QLineEdit, QPushButton, QMenu, QStyledItemDelegate,
                              QLabel, QWidgetAction)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, pyqtSignal, QRect, QPoint, QTimer, QThread, QStringListModel, QSize
from PyQt6.QtGui import QFont, QFontMetrics, QAction, QPainter, QColor

logger = logging.getLogger(__name__)

# Performance optimization: Limit displayed rows for large datasets
MAX_DISPLAY_ROWS = 50000  # Configurable maximum rows to display


class ClickableHeaderView(QHeaderView):
    """Custom header view with clickable sort icons"""
    
    sort_clicked = pyqtSignal(int)  # column_index
    
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.sort_icon_width = 16
        self.sort_icon_margin = 4
        self.resize_margin = 5  # Pixels from edge for resize cursor
        self.hovered_section = -1
        self.sort_order = {}  # column_index -> Qt.SortOrder
        self.filtered_columns = set()  # Track which columns have active filters
        # Wrapped-header mode (ledger style): sections are painted manually with
        # word-wrapped labels instead of the single-line elided default.
        self.wrap_mode = False
        self.wrap_bg = QColor("#E8DDF8")
        self.wrap_fg = QColor("#2A1458")
        self.wrap_border = QColor("#B79CDE")
        self.setMouseTracking(True)

    def wrap_font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(10)
        font.setBold(True)
        return font

    @staticmethod
    def wrap_flags(metrics: QFontMetrics, avail: QRect, label: str) -> int:
        """Word-wrap, falling back to wrap-anywhere for unbreakable long names."""
        flags = (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                 | Qt.TextFlag.TextWordWrap)
        needed = metrics.boundingRect(avail, flags, label)
        if needed.width() > avail.width():
            flags = (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                     | Qt.TextFlag.TextWrapAnywhere)
        return flags

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.wrap_mode:
            return
        # Columns no longer stretch to fill the viewport — continue the header
        # band across the empty strip beyond the last section so the bar reads
        # as one piece instead of ending mid-window.
        end = self.length() - self.offset()
        viewport = self.viewport()
        if end < viewport.width():
            painter = QPainter(viewport)
            strip = QRect(end, 0, viewport.width() - end, viewport.height())
            painter.fillRect(strip, self.wrap_bg)
            painter.setPen(self.wrap_border)
            painter.drawLine(strip.bottomLeft(), strip.bottomRight())
            painter.end()

    def paintSection(self, painter: QPainter, rect: QRect, logicalIndex: int):
        """Paint header section with sort icon"""
        if self.wrap_mode:
            self._paint_wrapped_section(painter, rect, logicalIndex)
        else:
            # Let default painting happen first
            super().paintSection(painter, rect, logicalIndex)

        # If this column is filtered, draw a pale blue background overlay
        if logicalIndex in self.filtered_columns:
            painter.save()
            # Draw semi-transparent pale blue overlay
            painter.fillRect(rect, QColor(173, 216, 230, 80))  # Light blue with transparency
            painter.restore()

        # Draw sort icon on the right side
        icon_rect = self.get_sort_icon_rect(rect)
        
        # Draw sort icon (square/triangle/arrow based on sort state)
        painter.save()
        
        # Highlight if hovered
        if logicalIndex == self.hovered_section:
            painter.fillRect(icon_rect, QColor(200, 220, 255, 100))
        
        painter.setPen(QColor(100, 100, 100))
        painter.setBrush(QColor(100, 100, 100))
        center_x = icon_rect.center().x()
        center_y = icon_rect.center().y()
        
        # Get sort state
        from PyQt6.QtCore import Qt as QtCore
        sort_order = self.sort_order.get(logicalIndex, None)
        
        if sort_order == QtCore.SortOrder.DescendingOrder:
            # Draw down arrow (▼)
            points = [
                QPoint(center_x - 4, center_y - 2),
                QPoint(center_x + 4, center_y - 2),
                QPoint(center_x, center_y + 3)
            ]
            painter.drawPolygon(points)
        elif sort_order == QtCore.SortOrder.AscendingOrder:
            # Draw up arrow (▲)
            points = [
                QPoint(center_x, center_y - 3),
                QPoint(center_x - 4, center_y + 2),
                QPoint(center_x + 4, center_y + 2)
            ]
            painter.drawPolygon(points)
        # No icon drawn for unsorted columns
        
        painter.restore()
    
    def _paint_wrapped_section(self, painter: QPainter, rect: QRect, logicalIndex: int):
        """Ledger-style section: tinted background, hairline borders, wrapped label."""
        painter.save()
        painter.fillRect(rect, self.wrap_bg)
        painter.setPen(self.wrap_border)
        painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        model = self.model()
        label = ""
        if model is not None:
            value = model.headerData(
                logicalIndex, self.orientation(), Qt.ItemDataRole.DisplayRole)
            label = "" if value is None else str(value)
        avail = rect.adjusted(5, 1, -(self.sort_icon_width + 3), -1)
        painter.setFont(self.wrap_font())
        painter.setPen(self.wrap_fg)
        painter.drawText(avail, self.wrap_flags(painter.fontMetrics(), avail, label), label)
        painter.restore()

    def get_sort_icon_rect(self, section_rect: QRect) -> QRect:
        """Get the rectangle for the sort icon within a section"""
        icon_x = section_rect.right() - self.sort_icon_width - self.sort_icon_margin
        icon_y = section_rect.top() + (section_rect.height() - self.sort_icon_width) // 2
        return QRect(icon_x, icon_y, self.sort_icon_width, self.sort_icon_width)
    
    def is_on_resize_edge(self, pos: QPoint, logical_index: int) -> bool:
        """Check if position is on the resize edge of a column"""
        if logical_index < 0:
            return False
            
        # Get the position within the section
        section_start = self.sectionViewportPosition(logical_index)
        section_end = section_start + self.sectionSize(logical_index)
        x = pos.x()
        
        # Check if we're near the left or right edge of the section
        # Left edge (for resizing previous column)
        if x >= section_start and x <= section_start + self.resize_margin:
            return True
        # Right edge (for resizing current column)
        if x >= section_end - self.resize_margin and x <= section_end:
            return True
            
        return False
    
    def set_sort_indicator(self, column_index: int, sort_order):
        """Set sort indicator for a column and trigger repaint"""
        self.sort_order.clear()  # Clear all other sorts
        if sort_order is not None:
            self.sort_order[column_index] = sort_order
        self.viewport().update()  # Trigger repaint
    
    def mousePressEvent(self, event):
        """Handle mouse press - check if sort icon was clicked"""
        from PyQt6.QtCore import Qt as QtCore
        
        logical_index = self.logicalIndexAt(event.pos())
        if logical_index >= 0:
            if event.button() == QtCore.MouseButton.RightButton:
                super().mousePressEvent(event)
                return

            # First check if we're on a resize edge - if so, let default handler resize
            if self.is_on_resize_edge(event.pos(), logical_index):
                logger.debug(f"Resize edge detected for column {logical_index} - allowing default resize")
                super().mousePressEvent(event)
                return
            
            section_rect = QRect(
                self.sectionViewportPosition(logical_index),
                0,
                self.sectionSize(logical_index),
                self.height()
            )
            
            icon_rect = self.get_sort_icon_rect(section_rect)
            
            if icon_rect.contains(event.pos()):
                # Sort icon clicked - emit custom signal
                logger.debug(f"Sort icon clicked for column {logical_index}")
                self.sort_clicked.emit(logical_index)
                event.accept()
                return
            elif event.button() == QtCore.MouseButton.LeftButton:
                # Header area clicked (not icon, not resize edge) - emit sectionClicked signal
                logger.debug(f"Header area clicked for column {logical_index} - emitting sectionClicked")
                self.sectionClicked.emit(logical_index)
                event.accept()
                return
        
        # Default handling for anything else
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Track which section is hovered for visual feedback and set resize cursor"""
        from PyQt6.QtCore import Qt as QtCore
        from PyQt6.QtGui import QCursor
        
        logical_index = self.logicalIndexAt(event.pos())
        if logical_index >= 0:
            # Check if we're on a resize edge
            if self.is_on_resize_edge(event.pos(), logical_index):
                # Set resize cursor
                self.setCursor(QCursor(QtCore.CursorShape.SplitHCursor))
                # Clear hover state for sort icon
                if self.hovered_section != -1:
                    self.hovered_section = -1
                    self.viewport().update()
            else:
                # Not on resize edge - restore normal cursor
                self.setCursor(QCursor(QtCore.CursorShape.ArrowCursor))
                
                section_rect = QRect(
                    self.sectionViewportPosition(logical_index),
                    0,
                    self.sectionSize(logical_index),
                    self.height()
                )
                
                icon_rect = self.get_sort_icon_rect(section_rect)
                
                if icon_rect.contains(event.pos()):
                    if self.hovered_section != logical_index:
                        self.hovered_section = logical_index
                        self.viewport().update()
                else:
                    if self.hovered_section != -1:
                        self.hovered_section = -1
                        self.viewport().update()
        else:
            # Restore normal cursor
            self.setCursor(QCursor(QtCore.CursorShape.ArrowCursor))
            if self.hovered_section != -1:
                self.hovered_section = -1
                self.viewport().update()
        
        super().mouseMoveEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Handle double-click for auto-resize on edge"""
        
        logical_index = self.logicalIndexAt(event.pos())
        if logical_index >= 0:
            # Check if we're on a resize edge
            if self.is_on_resize_edge(event.pos(), logical_index):
                logger.debug(f"Double-click on resize edge for column {logical_index} - auto-resizing")
                # Let default handler auto-resize the column
                super().mouseDoubleClickEvent(event)
                return
        
        # For any other double-click, use default handling
        super().mouseDoubleClickEvent(event)


class PandasTableModel(QAbstractTableModel):
    """Table model for displaying filtered Pandas DataFrame - optimized to use index-based filtering"""

    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self._original_df = df  # Keep original (no copy!)
        self._filtered_indices = df.index  # Indices after column filters
        self._display_indices = df.index   # Indices after global search
        self._default_numeric_decimals: Optional[int] = None
        self._column_decimals: Dict[str, Optional[int]] = {}
        self._highlighted_cells: Dict[tuple[int, str], QColor] = {}
        self._header_labels: Dict[str, str] = {}

    def set_filtered_indices(self, indices: pd.Index):
        """Update the filtered indices (after column filters)"""
        self.beginResetModel()
        self._filtered_indices = indices
        self._display_indices = indices
        self.endResetModel()

    def set_display_indices(self, indices: pd.Index):
        """Update the display indices (after global search)"""
        self.beginResetModel()
        self._display_indices = indices
        self.endResetModel()

    def get_original_data(self) -> pd.DataFrame:
        """Get the original unfiltered data"""
        return self._original_df

    def get_filtered_data(self) -> pd.DataFrame:
        """Get the filtered data (after column filters, before search)"""
        return self._original_df.loc[self._filtered_indices]

    def get_display_data(self) -> pd.DataFrame:
        """Get the currently displayed data"""
        return self._original_df.loc[self._display_indices]

    def set_numeric_formatting(
        self,
        default_decimals: Optional[int] = None,
        column_decimals: Optional[Dict[str, Optional[int]]] = None,
    ):
        self._default_numeric_decimals = default_decimals
        self._column_decimals = dict(column_decimals or {})
        if self.rowCount() > 0 and self.columnCount() > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])

    def set_highlighted_cells(self, highlighted_cells: Dict[tuple[int, str], QColor]):
        self._highlighted_cells = dict(highlighted_cells)
        if self.rowCount() > 0 and self.columnCount() > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.BackgroundRole])

    def set_header_labels(self, header_labels: Dict[str, str]):
        """Override the displayed header text for specific column keys.

        Lets two columns carry distinct DataFrame keys (needed for uniqueness)
        while showing the same human-facing label in the header.
        """
        self._header_labels = dict(header_labels or {})
        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal, 0, max(0, self.columnCount() - 1)
        )

    def is_numeric_column(self, column_index: int) -> bool:
        if column_index < 0 or column_index >= self.columnCount():
            return False
        return is_numeric_dtype(self._original_df.iloc[:, column_index])

    def column_name(self, column_index: int) -> str:
        return str(self._original_df.columns[column_index])

    def decimal_mode_for_column(self, column_index: int) -> Optional[int]:
        return self._column_decimals.get(self.column_name(column_index), self._default_numeric_decimals)

    def format_value_for_column(self, column_name: str, value: Any) -> str:
        if pd.isna(value):
            return ""

        if column_name in self._original_df.columns:
            column_index = self._original_df.columns.get_loc(column_name)
            if self.is_numeric_column(column_index):
                decimals = self._column_decimals.get(column_name, self._default_numeric_decimals)
                if decimals is not None:
                    return f"{float(value):,.{decimals}f}"
        return str(value)

    def rowCount(self, parent=QModelIndex()):
        return len(self._display_indices)

    def columnCount(self, parent=QModelIndex()):
        return len(self._original_df.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            # Use display indices to get actual row
            actual_row = self._display_indices[index.row()]
            value = self._original_df.iloc[self._original_df.index.get_loc(actual_row), index.column()]
            return self.format_value_for_column(self.column_name(index.column()), value)

        if role == Qt.ItemDataRole.BackgroundRole:
            return self._highlighted_cells.get((index.row(), self.column_name(index.column())))

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if hasattr(self, '_left_align_columns') and index.column() in self._left_align_columns:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                column_key = str(self._original_df.columns[section])
                return self._header_labels.get(column_key, column_key)
            else:
                return str(section + 1)
        return None


class _CompactDelegate(QStyledItemDelegate):
    """Minimal-height rows for filter popup list items."""

    _HEIGHT = 18

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self._HEIGHT)


class FilterPopup(QMenu):
    """Optimized popup menu for column filtering using QListView instead of 10,000+ QCheckBox widgets"""

    filter_changed = pyqtSignal(str, set)  # column_name, selected_values
    
    def __init__(self, column_name: str, unique_values: List[Any], 
                 current_selection: Optional[Set[Any]] = None, parent=None):
        super().__init__(parent)
        self.column_name = column_name
        
        init_start = time.perf_counter()
        
        logger.debug(f"[FILTER] FilterPopup.__init__ started for {column_name} with {len(unique_values)} values")
        
        # Convert and sort unique values
        sort_start = time.perf_counter()
        self.all_unique_values = sorted([str(v) if not pd.isna(v) else "(Blanks)" 
                                         for v in unique_values])
        sort_time = time.perf_counter()
        logger.debug(f"[FILTER]   - Sort {len(unique_values)} values: {(sort_time - sort_start)*1000:.2f}ms")
        
        self.current_selection = current_selection if current_selection else set(self.all_unique_values)
        
        # Style the popup menu itself with a blue-grey border
        self.setStyleSheet("""
            QMenu {
                background-color: #E8EDF2;
                border: 2px solid #1E5BA8;
                border-radius: 4px;
            }
        """)
        
        ui_start = time.perf_counter()
        self.init_ui()
        ui_time = time.perf_counter()
        logger.debug(f"[FILTER]   - init_ui completed: {(ui_time - ui_start)*1000:.2f}ms")
        
        init_total = time.perf_counter()
        logger.debug(f"[FILTER] TOTAL FilterPopup creation time: {(init_total - init_start)*1000:.2f}ms")

    def init_ui(self):
        """Initialize the filter popup UI"""
        # Create a widget to hold everything
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # Top bar with close button
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #666;
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                color: #000;
                background-color: #f0f0f0;
                border-radius: 3px;
            }
        """)
        close_btn.clicked.connect(self.close)
        top_bar.addWidget(close_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search values...")
        self.search_box.setFixedHeight(24)
        self.search_box.setStyleSheet("""
            QLineEdit {
                padding: 2px 6px;
                font-size: 10px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QLineEdit:focus {
                border: 1px solid #3498db;
            }
        """)
        self.search_box.textChanged.connect(self.filter_list)
        self.search_box.returnPressed.connect(self.apply_filter)
        layout.addWidget(self.search_box)

        # Control buttons row
        button_row = QHBoxLayout()
        button_row.setSpacing(4)
        
        # (Clear Filter) button
        clear_btn = QPushButton("Clear Filter")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 9px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        clear_btn.clicked.connect(self.clear_filter)
        button_row.addWidget(clear_btn)
        
        # Select All button
        select_all_btn = QPushButton("All")
        select_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 9px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        select_all_btn.clicked.connect(self.select_all)
        button_row.addWidget(select_all_btn)
        
        # Deselect All button
        deselect_all_btn = QPushButton("None")
        deselect_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 9px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
        """)
        deselect_all_btn.clicked.connect(self.deselect_all)
        button_row.addWidget(deselect_all_btn)
        
        button_row.addStretch()
        layout.addLayout(button_row)

        # Create QStringListModel for efficient handling of large lists
        create_model_start = time.perf_counter()
        self.string_model = QStringListModel(self.all_unique_values)
        create_model_time = time.perf_counter()
        logger.debug(f"[FILTER]   - QStringListModel created with {len(self.all_unique_values)} items in {(create_model_time - create_model_start)*1000:.2f}ms")
        
        # Create proxy model for search filtering
        proxy_start = time.perf_counter()
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.string_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        proxy_time = time.perf_counter()
        logger.debug(f"[FILTER]   - Proxy model created: {(proxy_time - proxy_start)*1000:.2f}ms")
        
        # Create multi-select list view with virtual rendering
        view_start = time.perf_counter()
        self.list_view = QListView()
        view_created = time.perf_counter()
        logger.debug(f"[FILTER]   - QListView created: {(view_created - view_start)*1000:.2f}ms")
        
        # Configure list view BEFORE setting model (faster)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.list_view.setMinimumWidth(200)
        self.list_view.setMaximumWidth(400)
        self.list_view.setMinimumHeight(250)
        self.list_view.setMaximumHeight(400)
        
        # CRITICAL: Enable uniform item sizes to avoid expensive layout calculations
        # With 50k items, Qt calculating individual heights is extremely slow
        self.list_view.setUniformItemSizes(True)
        self.list_view.setSpacing(0)
        # Compact font and tight row height for filter items
        self.list_view.setFont(QFont("Segoe UI", 8))
        self.list_view.setItemDelegate(_CompactDelegate(self.list_view))
        self.list_view.setStyleSheet("""
            QListView {
                background-color: white;
                border: 1px solid #A0B0C0;
                border-radius: 2px;
            }
            QListView::item {
                padding: 1px 4px;
            }
            QListView::item:selected {
                background-color: #C8D8E8;
                color: black;
            }
            QListView::item:hover {
                background-color: #D6E4F0;
            }
        """)
        
        # KEY OPTIMIZATION: Add widget to layout BEFORE setting model
        # This way Qt adds an empty list view (fast), then we populate it
        add_widget_start = time.perf_counter()
        layout.addWidget(self.list_view)
        add_widget_time = time.perf_counter()
        logger.debug(f"[FILTER]   - addWidget(empty list_view) to layout: {(add_widget_time - add_widget_start)*1000:.2f}ms")
        
        # Now set the model after the widget is in the layout
        set_model_start = time.perf_counter()
        self.list_view.setModel(self.proxy_model)
        set_model_time = time.perf_counter()
        logger.debug(f"[FILTER]   - setModel() called AFTER addWidget: {(set_model_time - set_model_start)*1000:.2f}ms")

        # Info label
        self.info_label = QLabel(f"Showing all {len(self.all_unique_values):,} values")
        self.info_label.setStyleSheet("font-size: 9px; color: #14407A; padding: 2px;")
        layout.addWidget(self.info_label)

        # Add widget action
        action = QWidgetAction(self)
        action.setDefaultWidget(container)
        self.addAction(action)

        # Auto-focus the search box when the popup opens
        QTimer.singleShot(0, self.search_box.setFocus)

        # Live filtering: emit filter on every selection change
        self.list_view.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        """Emit filter immediately when user clicks/unclicks an item."""
        selected_values = set()
        for index in self.list_view.selectionModel().selectedIndexes():
            value = self.proxy_model.data(index, Qt.ItemDataRole.DisplayRole)
            selected_values.add(value)
        if not selected_values:
            selected_values = set(self.all_unique_values)
        self.filter_changed.emit(self.column_name, selected_values)

    def filter_list(self, search_text: str):
        """Filter the list based on search text using proxy model"""
        self.proxy_model.setFilterFixedString(search_text)
        
        visible_count = self.proxy_model.rowCount()
        
        # Update info label
        if search_text:
            self.info_label.setText(f"Showing {visible_count:,} of {len(self.all_unique_values):,} values")
        else:
            self.info_label.setText(f"Showing all {len(self.all_unique_values):,} values")
    
    def clear_filter(self):
        """Clear the filter (emit all values without selecting UI items)"""
        start_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER] Clear Filter clicked for column: {self.column_name}")
        
        # Don't select items in UI - just emit all values directly (instant!)
        # Selecting 100k items in QListWidget takes 2+ minutes
        all_values_set = set(self.all_unique_values)
        
        emit_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER]   - Created set of {len(all_values_set)} values in {(emit_time - start_time)*1000:.2f}ms")
        
        self.filter_changed.emit(self.column_name, all_values_set)
        
        signal_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER]   - Emit signal completed in {(signal_time - emit_time)*1000:.2f}ms")
        
        self.close()
        
        end_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER] TOTAL Clear Filter time: {(end_time - start_time)*1000:.2f}ms")
    
    def select_all(self):
        """Select all visible items in the filtered view"""
        self.list_view.selectAll()
    
    def deselect_all(self):
        """Deselect all items"""
        self.list_view.clearSelection()
    
    def apply_filter(self):
        """Apply the filter and emit signal"""
        start_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER] Apply Filter (OK clicked) for column: {self.column_name}")
        
        # Get selected items from the view
        selected_values = set()
        selected_indexes = self.list_view.selectionModel().selectedIndexes()
        for index in selected_indexes:
            # Get the actual string value from the model
            value = self.proxy_model.data(index, Qt.ItemDataRole.DisplayRole)
            selected_values.add(value)
        
        get_values_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER]   - Get selected values: {len(selected_values)} items in {(get_values_time - start_time)*1000:.2f}ms")
        
        # If nothing is selected, select all (clear filter)
        if not selected_values:
            selected_values = set(self.all_unique_values)
            logger.info(f"⏱️ [FILTER]   - No selection, defaulting to all {len(selected_values)} values")
        
        emit_time = time.perf_counter()
        self.filter_changed.emit(self.column_name, selected_values)
        after_emit = time.perf_counter()
        logger.info(f"⏱️ [FILTER]   - Emit signal completed in {(after_emit - emit_time)*1000:.2f}ms")
        
        self.close()
        end_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER] TOTAL Apply Filter time: {(end_time - start_time)*1000:.2f}ms")
    
    def get_selected_values(self) -> Set[str]:
        """Get currently selected values"""
        selected_values = set()
        selected_indexes = self.list_view.selectionModel().selectedIndexes()
        for index in selected_indexes:
            value = self.proxy_model.data(index, Qt.ItemDataRole.DisplayRole)
            selected_values.add(value)
        return selected_values if selected_values else set(self.all_unique_values)


class SearchWorker(QThread):
    """Background worker for global search operations"""
    
    search_completed = pyqtSignal(pd.Index)  # Emits matching indices
    
    def __init__(self, df: pd.DataFrame, indices: pd.Index, search_text: str):
        super().__init__()
        self.df = df
        self.indices = indices
        self.search_text = search_text.lower().strip()
        self._is_cancelled = False
    
    def run(self):
        """Perform vectorized search across all columns"""
        try:
            if self._is_cancelled:
                return
            
            # Get the subset DataFrame
            subset = self.df.loc[self.indices]
            
            # Vectorized search: convert each column to lowercase strings and check for match
            column_masks = []
            for col in subset.columns:
                if self._is_cancelled:
                    return
                # Convert column to string, fill NaN, lowercase, and check if contains search text
                col_str = subset[col].fillna("").astype(str).str.lower()
                column_masks.append(col_str.str.contains(self.search_text, regex=False, na=False))
            
            # Combine all column masks with OR logic
            if column_masks:
                combined_mask = reduce(operator.or_, column_masks)
                matching_indices = subset[combined_mask].index
            else:
                matching_indices = pd.Index([])
            
            if not self._is_cancelled:
                self.search_completed.emit(matching_indices)
                
        except Exception as e:
            logger.error(f"Search error: {e}")
            self.search_completed.emit(pd.Index([]))
    
    def cancel(self):
        """Cancel the search operation"""
        self._is_cancelled = True


class FilterTableView(QWidget):
    """Excel-style filterable table view for DataFrames"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.df: Optional[pd.DataFrame] = None
        self.model: Optional[PandasTableModel] = None
        self.column_filters: Dict[str, Set[Any]] = {}  # column_name -> selected_values
        self.filtered_columns: Set[str] = set()  # Columns with active filters
        self.sort_order = {}  # column_index -> Qt.SortOrder
        
        # Performance optimizations
        self._unique_values_cache: Dict[str, List[Any]] = {}  # Cache unique values per column
        self._string_columns_cache: Dict[str, pd.Series] = {}  # Pre-converted string columns
        self._all_unique_values: Dict[str, List[Any]] = {}  # Pre-computed unique values per column
        self._search_worker: Optional[SearchWorker] = None  # Background search thread
        self._search_debounce_timer = QTimer()
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.timeout.connect(self._execute_search)
        self._pending_search_text = ""
        self._default_numeric_decimals: Optional[int] = None
        self._column_decimals: Dict[str, Optional[int]] = {}
        
        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Global search box at top
        self.search_bar = QWidget()
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_label = QLabel("🔍 Search:")
        search_layout.addWidget(search_label)
        
        self.global_search_box = QLineEdit()
        self.global_search_box.setPlaceholderText("Search across all columns...")
        self.global_search_box.textChanged.connect(self.apply_global_search)
        search_layout.addWidget(self.global_search_box)

        # Clear filters button (smaller)
        clear_btn = QPushButton("Clear All")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        clear_btn.clicked.connect(self.clear_all_filters)
        search_layout.addWidget(clear_btn)

        layout.addWidget(self.search_bar)

        # Table view
        self.table_view = QTableView()
        self.table_view.setObjectName("filterTableView")  # Custom object name for styling
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_table_context_menu)
        
        # Allow selecting individual items (cells) or rows
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self.table_view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        
        # Enable column reordering
        self.table_view.horizontalHeader().setSectionsMovable(True)
        
        # More compact rows
        self.table_view.verticalHeader().setDefaultSectionSize(18)  # Compact row height
        self.table_view.verticalHeader().setMinimumSectionSize(16)
        
        self.table_view.setStyleSheet("""
            QTableView#filterTableView {
                gridline-color: #d0d0d0;
                background-color: white;
                alternate-background-color: #f9f9f9;
                selection-background-color: #d4e4f7;
            }
            QTableView#filterTableView::item {
                padding: 0px;
                margin: 0px;
                border: none;
            }
            QTableView#filterTableView::item:selected {
                background-color: #d4e4f7 !important;
                border: 1px solid #a8c8e8;
                color: #0A1E5E;
            }
            QTableView#filterTableView::item:selected:active {
                background-color: #d4e4f7 !important;
                border: 1px solid #a8c8e8;
                color: #0A1E5E;
            }
            QTableView#filterTableView::item:selected:!active {
                background-color: #d4e4f7 !important;
                border: 1px solid #a8c8e8;
                color: #0A1E5E;
            }
            QTableView#filterTableView::item:hover {
                background-color: #e8f0fa;
            }
            QHeaderView {
                /* Continues the header band past the last column now that
                   sections no longer stretch to fill the viewport. */
                background-color: #f0f0f0;
                border: none;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #000000;
                padding: 1px 20px 1px 2px;  /* Extra padding on right for sort icon */
                border: 1px solid #d0d0d0;
                font-weight: normal;
                font-size: 11px;
            }
            QHeaderView::section:hover {
                background-color: #e0e0e0;
            }
        """)

        # Configure header - use custom header view
        self.header = ClickableHeaderView(Qt.Orientation.Horizontal, self.table_view)
        self.table_view.setHorizontalHeader(self.header)
        
        self.header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Columns keep their content width — the LAST column no longer
        # stretches into a giant filler when the data underfills the window
        # (the area past it stays an empty sheet, like a spreadsheet). A view
        # that wants a fill column sets Stretch on that column explicitly.
        self.header.setStretchLastSection(False)
        self.header.sectionClicked.connect(self.show_filter_popup)
        self.header.sort_clicked.connect(self.on_sort_clicked)
        self.header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.header.customContextMenuRequested.connect(self.show_column_context_menu)
        
        # Enable column reordering
        self.header.setSectionsMovable(True)
        self.header.setDragEnabled(True)
        self.header.setDragDropMode(QHeaderView.DragDropMode.InternalMove)
        
        # Track sort state per column
        self.sort_order = {}  # column_index -> Qt.SortOrder

        # Set font
        font = QFont("Consolas", 9)
        self.table_view.setFont(font)

        layout.addWidget(self.table_view)

        # Info label at bottom
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        layout.addWidget(self.info_label)

    def apply_ledger_style(
        self,
        header_bg: str = "#E8DDF8",
        header_fg: str = "#2A1458",
        border: str = "#B79CDE",
        selection_bg: str = "#E8DDF8",
        selection_fg: str = "#2A1458",
    ):
        """Opt-in dense ledger look: no grid lines, no zebra striping, tight
        17px rows, 11px default-family text, and a compact tinted header.

        Matches the Illustration Overview ledger aesthetic; callers pass their
        sub-app's header/border colors to rebrand it. The stock FilterTableView
        style is unchanged for existing users.
        """
        self.table_view.setAlternatingRowColors(False)
        self.table_view.setShowGrid(False)
        body_font = QFont()
        body_font.setPixelSize(11)
        self.table_view.setFont(body_font)  # set programmatically so font metrics match
        self.table_view.verticalHeader().setVisible(False)  # no row numbers
        self.table_view.verticalHeader().setDefaultSectionSize(17)
        self.table_view.verticalHeader().setMinimumSectionSize(15)
        # Wrapped multi-line headers painted by the header view itself.
        self.header.wrap_mode = True
        self.header.wrap_bg = QColor(header_bg)
        self.header.wrap_fg = QColor(header_fg)
        self.header.wrap_border = QColor(border)
        self.table_view.setStyleSheet(f"""
            QTableView#filterTableView {{
                background-color: white;
                border: 1px solid {border};
                font-size: 11px;
                selection-background-color: {selection_bg};
                selection-color: {selection_fg};
            }}
            QTableView#filterTableView::item {{
                padding: 0px 4px;
                margin: 0px;
                border: none;
            }}
            QTableView#filterTableView::item:selected {{
                background-color: {selection_bg};
                color: {selection_fg};
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {header_fg};
                font-size: 10px;
                font-weight: bold;
                border: none;
                border-right: 1px solid {border};
                border-bottom: 1px solid {border};
                padding: 2px 20px 2px 6px;  /* right padding clears the sort icon */
                height: 18px;
            }}
            QHeaderView::section:hover {{
                background-color: white;
            }}
        """)

    def autofit_columns_to_data(
        self,
        sample_rows: int = 400,
        padding: int = 14,
        min_width: int = 34,
        max_width: int = 260,
    ):
        """Size each column to its DATA (formatted), not its header.

        Long header names wrap instead of widening the column (ledger style
        paints multi-line headers), so the grid stays as compact as the values
        allow. Samples up to ``sample_rows`` from each end for width
        measurement. Call after set_dataframe / set_numeric_formatting /
        set_header_labels so widths reflect the final formatting.
        """
        if self.model is None or self.model.get_original_data().empty:
            return
        df = self.model.get_display_data()
        if len(df) > sample_rows:
            df = pd.concat([df.head(sample_rows // 2), df.tail(sample_rows // 2)])

        metrics = QFontMetrics(self.table_view.font())
        header_metrics = QFontMetrics(self.header.wrap_font())
        for column_index, column_name in enumerate(self.model.get_original_data().columns):
            if self.table_view.isColumnHidden(column_index):
                continue
            widest = 0
            if column_name in df.columns:
                for value in df[column_name]:
                    text = self.model.format_value_for_column(column_name, value)
                    width = metrics.horizontalAdvance(str(text))
                    if width > widest:
                        widest = width
            target = widest + padding
            if self.header.wrap_mode:
                # The column must fit the header's longest WORD so the wrapped
                # label breaks at spaces, never into letter stacks.
                value = self.model.headerData(
                    column_index, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
                label = "" if value is None else str(value)
                longest_word = max(
                    (header_metrics.horizontalAdvance(word) for word in label.split()),
                    default=0,
                )
                target = max(target, longest_word + self.header.sort_icon_width + 9)
            self.table_view.setColumnWidth(
                column_index, max(min_width, min(target, max_width)))

        self._refresh_wrapped_header_height()

    def _refresh_wrapped_header_height(self):
        """Fit the header band to the tallest wrapped label at current widths."""
        if not self.header.wrap_mode or self.model is None:
            return
        metrics = QFontMetrics(self.header.wrap_font())
        tallest = 18
        for column_index in range(len(self.model.get_original_data().columns)):
            if self.table_view.isColumnHidden(column_index):
                continue
            value = self.model.headerData(
                column_index, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            label = "" if value is None else str(value)
            avail_width = max(
                10, self.table_view.columnWidth(column_index) - self.header.sort_icon_width - 8)
            avail = QRect(0, 0, avail_width, 200)
            flags = self.header.wrap_flags(metrics, avail, label)
            needed = metrics.boundingRect(avail, flags, label).height() + 6
            if needed > tallest:
                tallest = needed
        self.header.setFixedHeight(min(tallest, 56))

    def set_dataframe(self, df: pd.DataFrame, limit_rows: bool = True):
        """Set the DataFrame to display

        Args:
            df: DataFrame to display
            limit_rows: If True, limit to MAX_DISPLAY_ROWS for performance. Set to False for query results.
        """
        # Auto-limit large datasets for optimal performance (only if limit_rows=True)
        original_row_count = len(df)
        if limit_rows and original_row_count > MAX_DISPLAY_ROWS:
            df = df.head(MAX_DISPLAY_ROWS)
            logger.info(f"Limited dataset to {MAX_DISPLAY_ROWS:,} rows (original: {original_row_count:,})")
        
        # Store reference (no copy - saves memory!)
        self.df = df
        
        # Clear caches - don't pre-compute anything yet (lazy loading for better performance)
        logger.info("Clearing caches for new dataframe...")
        self._string_columns_cache.clear()
        self._all_unique_values.clear()
        logger.info(f"DataFrame loaded with {len(df)} rows, {len(df.columns)} columns - caches will be computed on demand")
        
        self.model = PandasTableModel(self.df)
        self.model.set_numeric_formatting(self._default_numeric_decimals, self._column_decimals)
        self.table_view.setModel(self.model)
        
        # Reset filters and caches
        self.column_filters.clear()
        self.filtered_columns.clear()
        self.global_search_box.clear()
        self._unique_values_cache.clear()  # Clear unique values cache
        
        # Cancel any pending search
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
            self._search_worker.wait()
        
        # Update info
        self.update_info_label()
        
        logger.info(f"FilterTableView loaded {len(df)} rows, {len(df.columns)} columns")

    def set_search_visible(self, visible: bool):
        self.search_bar.setVisible(visible)

    def set_numeric_formatting(
        self,
        default_decimals: Optional[int] = None,
        column_decimals: Optional[Dict[str, Optional[int]]] = None,
    ):
        self._default_numeric_decimals = default_decimals
        if column_decimals is not None:
            self._column_decimals = dict(column_decimals)
        if self.model is not None:
            self.model.set_numeric_formatting(self._default_numeric_decimals, self._column_decimals)

    def set_highlighted_cells(self, highlighted_cells: Dict[tuple[int, str], QColor]):
        if self.model is not None:
            self.model.set_highlighted_cells(highlighted_cells)
    
    def set_header_labels(self, header_labels: Dict[str, str]):
        if self.model is not None:
            self.model.set_header_labels(header_labels)
    
    def on_sort_clicked(self, column_index: int):
        """Handle sort icon click - toggle sort order"""
        from PyQt6.QtCore import Qt as QtCore
        
        # Toggle sort
        if self.model is None:
            return
        
        # Get current sort order for this column
        current_order = self.sort_order.get(column_index, None)
        
        # Toggle: None -> Ascending -> Descending -> None
        if current_order is None:
            new_order = QtCore.SortOrder.AscendingOrder
        elif current_order == QtCore.SortOrder.AscendingOrder:
            new_order = QtCore.SortOrder.DescendingOrder
        else:
            new_order = None  # Clear sort
        
        # Clear all other column sorts
        self.sort_order.clear()
        
        if new_order is not None:
            self.sort_order[column_index] = new_order
            self.apply_sort(column_index, new_order)
        else:
            # Clear sort - restore to filtered data order
            self.apply_all_filters()
        
        # Update header sort icons
        self.header.set_sort_indicator(column_index, new_order)
        
        # Update header to show sort indicators
        self.update_header_indicators()
    
    def apply_sort(self, column_index: int, sort_order):
        """Sort the displayed data using index-based operations"""
        if self.model is None:
            return
        
        column_name = self.df.columns[column_index]
        
        # Get current display indices
        current_indices = self.model._display_indices
        
        # Sort the data using these indices
        ascending = (sort_order == Qt.SortOrder.AscendingOrder)
        sorted_data = self.df.loc[current_indices].sort_values(by=column_name, ascending=ascending)
        
        # Update model with sorted indices
        self.model.set_display_indices(sorted_data.index)
        self.update_info_label()

    def _get_filtered_unique_values(self, column_name: str) -> List[Any]:
        """Get unique values for a column, considering all OTHER active filters (Excel cascading behavior)"""
        # Lazy compute unique values for this column if not already done
        if column_name not in self._all_unique_values:
            self._all_unique_values[column_name] = self.df[column_name].unique().tolist()
        
        # If no other filters are active, return all unique values (instant!)
        if not any(col != column_name for col in self.column_filters.keys()):
            return self._all_unique_values[column_name]
        
        # Check cache for filtered scenario
        cache_key = f"{column_name}_{'_'.join(sorted([c for c in self.column_filters.keys() if c != column_name]))}"
        if cache_key in self._unique_values_cache:
            return self._unique_values_cache[cache_key]
        
        # Start with full index
        filtered_indices = self.df.index
        
        # Apply all column filters EXCEPT for the current column
        for col_name, selected_values in self.column_filters.items():
            if col_name != column_name:  # Skip current column's filter
                # Lazy compute string column if needed
                if col_name not in self._string_columns_cache:
                    self._string_columns_cache[col_name] = self.df[col_name].fillna("(Blanks)").astype(str)
                # Use cached string column (no conversion needed!)
                col_str = self._string_columns_cache[col_name]
                mask = col_str.isin(selected_values)
                filtered_indices = filtered_indices[mask[filtered_indices]]
        
        # Get unique values from the filtered data
        unique_vals = self.df.loc[filtered_indices, column_name].unique().tolist()
        
        # Cache the result
        self._unique_values_cache[cache_key] = unique_vals
        
        return unique_vals
    
    def show_filter_popup(self, column_index: int):
        """Show filter popup for a column (triggered by clicking filter icon)"""
        start_time = time.perf_counter()
        
        logger.debug(f"show_filter_popup called for column {column_index}")
        if self.model is None:
            logger.debug("No model - returning")
            return

        column_name = self.df.columns[column_index]
        logger.info(f"⏱️ [FILTER] Opening filter box for column: {column_name}")
        
        # Get unique values considering OTHER filters (Excel cascading behavior)
        get_unique_start = time.perf_counter()
        unique_values = self._get_filtered_unique_values(column_name)
        get_unique_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER]   - Get unique values: {len(unique_values)} items in {(get_unique_time - get_unique_start)*1000:.2f}ms")
        
        # Get current selection for this column (default to all)
        current_selection = self.column_filters.get(column_name, None)
        
        # Create and show popup
        create_popup_start = time.perf_counter()
        popup = FilterPopup(column_name, unique_values, current_selection, self)
        create_popup_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER]   - Create FilterPopup widget in {(create_popup_time - create_popup_start)*1000:.2f}ms")
        
        popup.filter_changed.connect(self.apply_column_filter)
        
        # Position popup below the clicked column header
        # Get the position of the section (column) that was clicked
        section_x = self.header.sectionViewportPosition(column_index)
        section_width = self.header.sectionSize(column_index)
        
        # Calculate global position
        header_bottom_left = self.header.mapToGlobal(self.header.rect().bottomLeft())
        popup_x = header_bottom_left.x() + section_x
        popup_y = header_bottom_left.y()
        
        from PyQt6.QtCore import QPoint
        popup_position = QPoint(popup_x, popup_y)
        
        before_exec = time.perf_counter()
        logger.debug(f"[FILTER] TOTAL time to open filter box: {(before_exec - start_time)*1000:.2f}ms")
        
        popup.exec(popup_position)

    def apply_column_filter(self, column_name: str, selected_values: Set[str]):
        """Apply filter to a specific column"""
        start_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER] apply_column_filter called for column: {column_name} with {len(selected_values)} values")
        
        if self.model is None:
            return

        # Get the values that are actually available considering OTHER filters (cascading)
        get_available_start = time.perf_counter()
        available_values = set(str(v) if not pd.isna(v) else "(Blanks)" 
                              for v in self._get_filtered_unique_values(column_name))
        get_available_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER]   - Get available values in {(get_available_time - get_available_start)*1000:.2f}ms")
        
        if selected_values == available_values:
            # All available values selected = no filter for this column
            if column_name in self.column_filters:
                del self.column_filters[column_name]
            self.filtered_columns.discard(column_name)
            logger.info(f"⏱️ [FILTER]   - All values selected, removing filter for {column_name}")
        else:
            self.column_filters[column_name] = selected_values
            self.filtered_columns.add(column_name)
            logger.info(f"⏱️ [FILTER]   - Filter set for {column_name}: {len(selected_values)} values")
        
        # Apply all column filters
        apply_start = time.perf_counter()
        self.apply_all_filters()
        apply_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER]   - apply_all_filters completed in {(apply_time - apply_start)*1000:.2f}ms")
        
        # Update header to show filter indicator
        header_start = time.perf_counter()
        self.update_header_indicators()
        header_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER]   - update_header_indicators completed in {(header_time - header_start)*1000:.2f}ms")
        
        end_time = time.perf_counter()
        logger.info(f"⏱️ [FILTER] TOTAL apply_column_filter time: {(end_time - start_time)*1000:.2f}ms")
    
    def update_header_indicators(self):
        """Update header sections to show filter and sort indicators"""
        if self.model is None:
            return
        
        # Update the header view's filtered_columns set
        self.header.filtered_columns.clear()
        for i, col_name in enumerate(self.df.columns):
            if col_name in self.filtered_columns:
                self.header.filtered_columns.add(i)
        
        for i, col_name in enumerate(self.df.columns):
            # Build header text with indicators
            header_text = str(col_name)
            
            # Add filter indicator
            if col_name in self.filtered_columns:
                header_text += " 🔽"
            
            # Add sort indicator
            if i in self.sort_order:
                if self.sort_order[i] == Qt.SortOrder.AscendingOrder:
                    header_text += " ▲"
                else:
                    header_text += " ▼"
            
            # Update header
            self.model.headerData(i, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
            self.header.model().setHeaderData(i, Qt.Orientation.Horizontal, header_text)
        
        # Force header repaint to update sort icons and filtered column backgrounds
        self.header.viewport().update()

    def apply_all_filters(self):
        """Apply all column filters using lazy-computed string columns"""
        if self.model is None:
            return

        # Start with all indices
        filtered_indices = self.df.index

        # Apply each column filter using lazy-computed string columns
        for column_name, selected_values in self.column_filters.items():
            # Lazy compute string column if needed
            if column_name not in self._string_columns_cache:
                self._string_columns_cache[column_name] = self.df[column_name].fillna("(Blanks)").astype(str)
            # Use cached string column (no conversion needed!)
            col_str = self._string_columns_cache[column_name]
            mask = col_str.isin(selected_values)
            # Filter the indices
            filtered_indices = filtered_indices[mask[filtered_indices]]

        # Update model with filtered indices (no DataFrame copy!)
        self.model.set_filtered_indices(filtered_indices)
        
        # Invalidate cascading filter cache since filters changed
        self._unique_values_cache.clear()
        
        # Re-apply global search if active
        if self.global_search_box.text():
            self.apply_global_search(self.global_search_box.text())
        else:
            self.model.set_display_indices(filtered_indices)
        
        self.update_info_label()
        
        logger.info(f"Filters applied: {len(filtered_indices)} rows visible")

    def apply_global_search(self, search_text: str):
        """Apply global search with debouncing to avoid blocking on every keystroke"""
        if self.model is None:
            return
        
        # Cancel any running search
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
        
        # Store pending search and start debounce timer
        self._pending_search_text = search_text
        self._search_debounce_timer.start(300)  # 300ms debounce
    
    def _execute_search(self):
        """Execute the search after debounce period"""
        search_text = self._pending_search_text.lower().strip()
        
        if not search_text:
            # No search - show filtered data
            self.model.set_display_indices(self.model._filtered_indices)
            self.update_info_label()
            return
        
        # Start background search
        self._search_worker = SearchWorker(
            self.df,
            self.model._filtered_indices,
            search_text
        )
        self._search_worker.search_completed.connect(self._on_search_completed)
        self._search_worker.start()
        
        # Show searching indicator
        self.info_label.setText("🔍 Searching...")
    
    def _on_search_completed(self, matching_indices: pd.Index):
        """Handle search completion"""
        if self.model:
            self.model.set_display_indices(matching_indices)
            self.update_info_label()

    def clear_all_filters(self):
        """Clear all filters and reset to original data"""
        self.column_filters.clear()
        self.filtered_columns.clear()
        self.global_search_box.clear()
        self._unique_values_cache.clear()  # Clear cache
        
        # Cancel any running search
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.cancel()
        
        if self.model:
            # Reset to all indices
            all_indices = self.df.index
            self.model.set_filtered_indices(all_indices)
            self.model.set_display_indices(all_indices)
        
        self.update_header_indicators()
        self.update_info_label()

    def update_info_label(self):
        """Update the info label with current row counts"""
        if self.model is None:
            self.info_label.setText("")
            return

        total_rows = len(self.df)
        display_rows = len(self.model.get_display_data())
        
        if display_rows == total_rows:
            self.info_label.setText(f"Showing all {total_rows:,} rows")
        else:
            self.info_label.setText(
                f"Showing {display_rows:,} of {total_rows:,} rows "
                f"({len(self.column_filters)} column filter(s) active)"
            )

    def show_column_context_menu(self, pos):
        """Show context menu for column operations and numeric formatting."""
        column_index = self.header.logicalIndexAt(pos)
        if column_index < 0:
            return

        menu = QMenu(self)

        if self.model is not None and self.model.is_numeric_column(column_index):
            decimals_menu = menu.addMenu("Decimals")
            for label, decimals in [("0", 0), ("2", 2), ("7", 7), ("Max", None)]:
                action = QAction(label, self)
                action.setCheckable(True)
                action.setChecked(self.model.decimal_mode_for_column(column_index) == decimals)
                action.triggered.connect(
                    lambda checked=False, c=column_index, d=decimals: self.set_column_decimals(c, d)
                )
                decimals_menu.addAction(action)

            menu.addSeparator()
        
        # Hide column option
        hide_action = QAction("Hide Column", self)
        hide_action.triggered.connect(lambda: self.table_view.hideColumn(column_index))
        menu.addAction(hide_action)

        # Show all columns option
        show_all_action = QAction("Show All Columns", self)
        show_all_action.triggered.connect(self.show_all_columns)
        menu.addAction(show_all_action)

        menu.exec(self.header.mapToGlobal(pos))

    def show_all_columns(self):
        """Show all hidden columns"""
        for i in range(self.model.columnCount()):
            self.table_view.showColumn(i)

    def set_column_decimals(self, column_index: int, decimals: Optional[int]):
        if self.model is None:
            return
        column_name = self.model.column_name(column_index)
        self._column_decimals[column_name] = decimals
        self.model.set_numeric_formatting(self._default_numeric_decimals, self._column_decimals)

    def show_table_context_menu(self, pos):
        """Show context menu for table cell operations"""
        if self.model is None:
            return
        
        
        menu = QMenu(self)
        
        # Get clicked cell index
        index = self.table_view.indexAt(pos)
        
        if index.isValid():
            # Copy Cell action
            copy_cell_action = QAction("📋 Copy Cell", self)
            copy_cell_action.triggered.connect(lambda: self.copy_cell(index))
            menu.addAction(copy_cell_action)
            
            menu.addSeparator()
        
        # Check if filters are active
        display_rows = len(self.model.get_display_data())
        total_rows = len(self.df)
        is_filtered = display_rows != total_rows

        if is_filtered:
            # Default copy action copies filtered data when filters are active
            copy_table_action = QAction(f"📋 Copy Table ({display_rows:,} filtered rows)", self)
            copy_table_action.triggered.connect(self.copy_filtered_table)
            menu.addAction(copy_table_action)
            menu.addSeparator()
            # Offer full table as secondary option
            copy_all_action = QAction(f"📋 Copy All Rows ({total_rows:,} unfiltered)", self)
            copy_all_action.triggered.connect(self.copy_entire_table)
            menu.addAction(copy_all_action)
        else:
            copy_table_action = QAction("📋 Copy Entire Table", self)
            copy_table_action.triggered.connect(self.copy_entire_table)
            menu.addAction(copy_table_action)
        
        menu.exec(self.table_view.viewport().mapToGlobal(pos))
    
    def copy_cell(self, index: QModelIndex):
        """Copy the contents of a single cell to clipboard"""
        if not index.isValid():
            return
        
        from PyQt6.QtWidgets import QApplication
        
        # Get cell value
        cell_value = self.model.data(index, Qt.ItemDataRole.DisplayRole)
        
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(str(cell_value) if cell_value else "")
        
        logger.info(f"Copied cell value: {cell_value}")
    
    def copy_entire_table(self):
        """Copy the entire original table to clipboard using displayed formatting."""
        if self.df is None:
            return
        
        from PyQt6.QtWidgets import QApplication
        
        df_to_copy = self.df
        clipboard_text = self._dataframe_to_clipboard_text(df_to_copy)
        
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text)
        
        logger.info(f"Copied entire table: {len(df_to_copy)} rows, {len(df_to_copy.columns)} columns")
        
        # Optional: Show a brief notification
        from PyQt6.QtWidgets import QToolTip
        from PyQt6.QtGui import QCursor
        QToolTip.showText(
            QCursor.pos(),
            f"✓ Copied {len(df_to_copy):,} rows to clipboard",
            self.table_view,
            self.table_view.rect(),
            2000
        )
    
    def copy_filtered_table(self):
        """Copy the currently filtered/displayed table using displayed formatting."""
        if self.model is None:
            return
        
        from PyQt6.QtWidgets import QApplication
        
        # Get the currently displayed DataFrame
        df_to_copy = self.model.get_display_data()
        
        clipboard_text = self._dataframe_to_clipboard_text(df_to_copy)
        
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text)
        
        logger.info(f"Copied filtered table: {len(df_to_copy)} rows, {len(df_to_copy.columns)} columns")
        
        # Optional: Show a brief notification
        from PyQt6.QtWidgets import QToolTip
        from PyQt6.QtGui import QCursor
        QToolTip.showText(
            QCursor.pos(),
            f"✓ Copied {len(df_to_copy):,} filtered rows to clipboard",
            self.table_view,
            self.table_view.rect(),
            2000
        )

    def get_filtered_dataframe(self) -> pd.DataFrame:
        """Get the currently filtered/displayed DataFrame"""
        if self.model:
            return self.model.get_display_data()
        return pd.DataFrame()

    def _visible_column_names_in_order(self) -> List[str]:
        if self.model is None:
            return []
        names: List[str] = []
        for visual_index in range(self.header.count()):
            logical_index = self.header.logicalIndex(visual_index)
            if self.table_view.isColumnHidden(logical_index):
                continue
            names.append(self.model.column_name(logical_index))
        return names

    def _dataframe_to_clipboard_text(self, df_to_copy: pd.DataFrame) -> str:
        column_names = self._visible_column_names_in_order()
        if not column_names:
            column_names = list(df_to_copy.columns)

        rows: List[str] = ["\t".join(column_names)]
        for _, row in df_to_copy.loc[:, column_names].iterrows():
            formatted = [
                self.model.format_value_for_column(column_name, row[column_name]) if self.model is not None else str(row[column_name])
                for column_name in column_names
            ]
            rows.append("\t".join(formatted))
        return "\n".join(rows)
