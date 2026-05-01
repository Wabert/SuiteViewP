"""
Reusable widgets for SuiteView.

Contains the core UI building blocks used across tabs:
- TooltipManager       – singleton that loads field tooltips from JSON
- ColumnFilterPopup     – Excel-style column filter dropdown
- FixedHeaderTableWidget – styled table with fixed header and column filtering
- StyledInfoTableGroup  – compound info-fields + table GroupBox widget
- StyledTableGroup      – convenience alias (table-only mode)
- CopyableLabel         – QLabel with right-click copy
- ClickableTooltipLabel – QLabel that shows help popup on click
- PolicyLookupBar       – top bar for policy number / region entry
- TableDataWidget       – transposed table display for raw DB2 data
"""

import json
from pathlib import Path
from typing import Dict, List, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QHeaderView,
    QTableWidget, QTableWidgetItem, QLabel, QGroupBox,
    QLineEdit, QPushButton, QComboBox, QGridLayout,
    QListWidget, QListWidgetItem, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint
from PyQt6.QtGui import QColor, QFontMetrics

from suiteview.core.db2_constants import REGIONS
from .formatting import is_numeric
from .styles import (
    BLUE_PRIMARY, BLUE_LIGHT,
    BLUE_SCROLL, BLUE_DARK, BLUE_SUBTLE, WHITE, GRAY_MID, GRAY_DARK,
    COMPACT_TABLE_STYLE, CONTEXT_MENU_STYLE, LOOKUP_BAR_STYLE,
    POLICY_DISPLAY_STYLE, POLICY_INFO_FRAME_STYLE,
)


# =============================================================================
# TOOLTIP MANAGER - Loads and provides field tooltips from JSON
# =============================================================================

class TooltipManager:
    """
    Manages field tooltips loaded from a JSON configuration file.
    
    Usage:
        tooltips = TooltipManager()
        tip = tooltips.get_tooltip("AdvProdValues", "total_av")
    """
    _instance = None
    _tooltips = None
    
    def __new__(cls):
        """Singleton pattern - only one instance needed."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_tooltips()
        return cls._instance
    
    def _load_tooltips(self):
        """Load tooltips from JSON file."""
        self._tooltips = {}
        config_path = Path(__file__).parent.parent / "config" / "field_tooltips.json"
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._tooltips = json.load(f)
        except Exception as e:
            pass
    
    def get_tooltip(self, section: str, field: str) -> str:
        """
        Get tooltip text for a field.
        
        Args:
            section: The section name (e.g., "AdvProdValues", "MonthliversaryValues")
            field: The field attribute name (e.g., "total_av", "eff_date")
            
        Returns:
            Tooltip text, or empty string if not found
        """
        section_data = self._tooltips.get(section, {})
        field_data = section_data.get(field, {})
        return field_data.get("tooltip", "")
    
    def get_all_fields(self, section: str) -> dict:
        """Get all field tooltips for a section."""
        section_data = self._tooltips.get(section, {})
        # Filter out metadata keys starting with "_"
        return {k: v for k, v in section_data.items() if not k.startswith("_")}
    
    def reload(self):
        """Reload tooltips from file (for maintenance screen)."""
        self._load_tooltips()


# Global tooltip manager instance
_tooltip_manager = None

def get_tooltip_manager() -> TooltipManager:
    """Get the global tooltip manager instance."""
    global _tooltip_manager
    if _tooltip_manager is None:
        _tooltip_manager = TooltipManager()
    return _tooltip_manager


# =============================================================================
# COLUMN FILTER POPUP - Excel-style column filtering for tables
# =============================================================================

class ColumnFilterPopup(QFrame):
    """
    A compact popup that shows unique column values for filtering.
    
    Appears below the column header when clicked. Shows:
    - [CLR*]  : Clear ALL column filters across the table
    - [CLEAR] : Clear THIS column's filter only
    - [CLOSE] : Close the popup
    - (separator)
    - Unique values for the column (respecting other columns' active filters)
    
    Selection behavior: no items selected = all rows shown.
    Clicking a value selects it (highlighted). Multiple values are additive
    (show rows matching ANY selected value). Click again to deselect.
    """
    
    filter_changed = pyqtSignal(int, set)   # column_index, selected_values (empty = no filter)
    clear_all_requested = pyqtSignal()       # request to clear all column filters
    
    # Number of special action items at the top of the list
    _SPECIAL_COUNT = 3
    
    def __init__(self, col_index: int, unique_values: list, current_selection: set, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._col_index = col_index
        self._unique_values = unique_values
        self._current_selection = set(current_selection)  # copy
        self._setup_ui()
    
    def _setup_ui(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {WHITE};
                border: 1px solid {BLUE_PRIMARY};
                border-radius: 2px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        
        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background-color: {WHITE};
                font-size: 10px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 0px 4px;
                margin: 0px;
                border: none;
                max-height: 13px;
            }}
            QListWidget::item:hover {{
                background-color: {BLUE_SUBTLE};
            }}
            QScrollBar:vertical {{
                background-color: {BLUE_SUBTLE};
                width: 10px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background-color: {BLUE_SCROLL};
                min-height: 20px;
                margin: 1px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {BLUE_LIGHT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        # Add special action items
        for text in ["[CLR*]", "[CLEAR]", "[CLOSE]"]:
            item = QListWidgetItem(text)
            item.setForeground(QColor(BLUE_PRIMARY))
            font = item.font()
            font.setBold(True)
            font.setPointSizeF(8.5)
            item.setFont(font)
            self._list.addItem(item)
        
        # Separator
        sep_item = QListWidgetItem("")
        sep_item.setFlags(Qt.ItemFlag.NoItemFlags)
        sep_item.setSizeHint(QSize(0, 2))
        # Draw a line via background
        sep_item.setBackground(QColor(GRAY_MID))
        self._list.addItem(sep_item)
        
        # Add unique values
        for val in self._unique_values:
            item = QListWidgetItem(str(val))
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            font = item.font()
            font.setPointSizeF(8.5)
            item.setFont(font)
            # If this value is in current selection, show it bold
            if val in self._current_selection:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self._list.addItem(item)
        
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)
        
        # Size the popup
        self._size_popup()
    
    def _size_popup(self):
        """Calculate compact popup size based on content."""
        # Use a bold font for metrics since some items are bold
        bold_font = self._list.font()
        bold_font.setBold(True)
        fm = QFontMetrics(bold_font)
        
        # Width: max of all item texts + padding, autofit to content
        max_width = 60  # minimum
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.text():
                w = fm.horizontalAdvance(item.text()) + 24
                max_width = max(max_width, w)
        # Add scrollbar width if needed
        max_width += 12
        max_width = min(max_width, 400)  # cap width
        
        # Height: measure actual item heights, cap total
        item_count = self._list.count()
        item_height = 13  # compact row height
        list_height = min(item_count * item_height + 4, 300)
        
        self.setFixedSize(max_width, list_height + 2)
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle clicks on list items."""
        row = self._list.row(item)
        text = item.text()
        
        if row == 0:  # [CLR*] - clear all filters
            self.clear_all_requested.emit()
            self.close()
            return
        elif row == 1:  # [CLEAR] - clear this column's filter
            self._current_selection.clear()
            self.filter_changed.emit(self._col_index, set())
            self.close()
            return
        elif row == 2:  # [CLOSE]
            self.close()
            return
        elif row == 3:  # separator
            return
        
        # Data value - toggle selection
        val = text
        if val in self._current_selection:
            # Deselect - revert to normal weight
            self._current_selection.discard(val)
            f = item.font()
            f.setBold(False)
            item.setFont(f)
        else:
            # Select - bold to indicate active
            self._current_selection.add(val)
            f = item.font()
            f.setBold(True)
            item.setFont(f)
        
        # Emit filter change
        self.filter_changed.emit(self._col_index, set(self._current_selection))


# =============================================================================
# FIXED HEADER TABLE WIDGET
# =============================================================================

class FixedHeaderTableWidget(QWidget):
    """
    A table widget with a styled header inside a rounded frame.
    
    Uses a single QTableWidget with native QHeaderView so headers and data
    always scroll together horizontally.  Column resize and double-click
    auto-fit are handled natively by QHeaderView.
    
    Features:
    - Headers scroll with data automatically (no sync needed)
    - Column resizing by dragging header edges (native)
    - Double-click header edge to auto-fit column
    - Rounded corners on the overall container
    - Clean, minimal styling with no grid lines
    """
    
    def __init__(self, parent=None, filterable: bool = False):
        super().__init__(parent)
        self._column_count = 0
        self._filterable = filterable
        self._column_filters = {}      # col_index -> set of selected values (empty = no filter)
        self._original_headers = []    # store original header labels
        self._filter_popup = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the table inside a rounded frame."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create a frame to hold everything with rounded corners
        self._outer_frame = QFrame()
        self._outer_frame.setObjectName("outerFrame")
        self._outer_frame.setStyleSheet(f"""
            QFrame#outerFrame {{
                background-color: {WHITE};
                border: 1px solid {BLUE_PRIMARY};
                border-radius: 4px;
            }}
        """)
        outer_layout = QVBoxLayout(self._outer_frame)
        outer_layout.setContentsMargins(1, 1, 1, 1)
        outer_layout.setSpacing(0)
        
        # Single QTableWidget with native header
        self._data_table = QTableWidget()
        self._data_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {WHITE};
                border: none;
                gridline-color: transparent;
                font-size: 11px;
                selection-background-color: {WHITE};
                selection-color: {BLUE_DARK};
            }}
            QTableWidget::item {{
                padding: 0px 4px;
                border: none;
            }}
            QTableWidget::item:selected {{
                background-color: {WHITE};
                color: {BLUE_DARK};
                border: none;
            }}
            /* Native header styled to match the custom QLabel headers */
            QHeaderView::section {{
                background-color: {BLUE_SUBTLE};
                color: {BLUE_DARK};
                padding: 2px 4px;
                border: none;
                border-right: 1px solid {GRAY_MID};
                border-bottom: 1px solid {BLUE_PRIMARY};
                font-size: 10px;
                font-weight: normal;
                height: 18px;
            }}
            QHeaderView::section:last {{
                border-right: none;
            }}
            /* Scrollbar styling */
            QScrollBar:vertical {{
                background-color: {BLUE_SUBTLE};
                width: 14px;
                margin: 0px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background-color: {BLUE_SCROLL};
                min-height: 30px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {BLUE_LIGHT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar:horizontal {{
                background-color: {BLUE_SUBTLE};
                height: 14px;
                margin: 0px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {BLUE_SCROLL};
                min-width: 30px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {BLUE_LIGHT};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """)
        
        # Table config
        self._data_table.verticalHeader().setVisible(False)
        self._data_table.verticalHeader().setMinimumSectionSize(16)
        self._data_table.verticalHeader().setDefaultSectionSize(16)
        self._data_table.setAlternatingRowColors(False)
        self._data_table.setShowGrid(False)
        
        # Header config — native interactive resize + double-click auto-fit
        header = self._data_table.horizontalHeader()
        header.setFixedHeight(22)
        header.setVisible(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.sectionDoubleClicked.connect(self._auto_fit_column)
        
        outer_layout.addWidget(self._data_table, 1)
        main_layout.addWidget(self._outer_frame)
        
        # Context menu
        self._data_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._data_table.customContextMenuRequested.connect(self._show_context_menu)
        
        # Column filtering - connect header click
        if self._filterable:
            header.sectionClicked.connect(self._on_header_clicked)
            header.setCursor(Qt.CursorShape.PointingHandCursor)
    
    # =========================================================================
    # Auto-fit
    # =========================================================================
    
    def _auto_fit_column(self, col_index):
        """Auto-fit a single column to its content (on header double-click)."""
        if col_index < 0 or col_index >= self._column_count:
            return
        fm = QFontMetrics(self._data_table.font())
        
        # Header text width
        h_item = self._data_table.horizontalHeaderItem(col_index)
        header_width = fm.horizontalAdvance(h_item.text()) + 16 if h_item else 40
        
        # Max data width
        max_data_width = 0
        for row in range(self._data_table.rowCount()):
            item = self._data_table.item(row, col_index)
            if item:
                max_data_width = max(max_data_width, fm.horizontalAdvance(item.text()) + 16)
        
        self._data_table.setColumnWidth(col_index, max(40, header_width, max_data_width))
    
    # =========================================================================
    # Public API (unchanged signatures)
    # =========================================================================
    
    def setColumnCount(self, count):
        """Set the number of columns."""
        self._column_count = count
        self._data_table.setColumnCount(count)
    
    def setRowCount(self, count):
        """Set the number of rows."""
        self._clear_all_filters(apply=False)
        self._data_table.setRowCount(count)
    
    def rowCount(self):
        """Get the number of rows."""
        return self._data_table.rowCount()
    
    def columnCount(self):
        """Get the number of columns."""
        return self._data_table.columnCount()
    
    def setItem(self, row, col, item, alignment=None):
        """Set a table item (right-aligned by default, or use custom alignment)."""
        if alignment is not None:
            item.setTextAlignment(alignment)
        else:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._data_table.setItem(row, col, item)
    
    def item(self, row, col):
        """Get a table item."""
        return self._data_table.item(row, col)
    
    def itemAt(self, pos):
        """Get item at position."""
        return self._data_table.itemAt(pos)
    
    def currentRow(self):
        """Get current selected row."""
        return self._data_table.currentRow()
    
    def clear(self):
        """Clear all data."""
        self._clear_all_filters(apply=False)
        self._data_table.clear()
        self._data_table.setRowCount(0)
    
    def setHorizontalHeaderLabels(self, labels):
        """Set column headers using the native QTableWidget header (right-aligned)."""
        self._original_headers = list(labels)
        self._data_table.setHorizontalHeaderLabels(labels)
        # Right-align all headers
        for col in range(len(labels)):
            item = self._data_table.horizontalHeaderItem(col)
            if item:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    
    def resizeColumnsToContents(self):
        """Resize columns to fit content."""
        self._data_table.resizeColumnsToContents()
        # Enforce minimum width
        for i in range(self._column_count):
            if self._data_table.columnWidth(i) < 40:
                self._data_table.setColumnWidth(i, 40)
    
    def autoFitAllColumns(self):
        """Auto-fit all columns to their content, considering both header and data."""
        fm = QFontMetrics(self._data_table.font())
        
        for col in range(self._column_count):
            # Header text width
            h_item = self._data_table.horizontalHeaderItem(col)
            header_width = fm.horizontalAdvance(h_item.text()) + 16 if h_item else 40
            
            # Max data width
            max_data_width = 0
            for row in range(self._data_table.rowCount()):
                item = self._data_table.item(row, col)
                if item:
                    max_data_width = max(max_data_width, fm.horizontalAdvance(item.text()) + 16)
            
            self._data_table.setColumnWidth(col, max(40, header_width, max_data_width))
    
    def columnWidth(self, col):
        """Get column width."""
        return self._data_table.columnWidth(col)
    
    def setColumnWidth(self, col, width):
        """Set column width."""
        self._data_table.setColumnWidth(col, width)
    
    def mapToGlobal(self, pos):
        """Map position to global coordinates."""
        return self._data_table.mapToGlobal(pos)
    
    # =========================================================================
    # Column Filtering (Excel-style)
    # =========================================================================
    
    def _on_header_clicked(self, col_index: int):
        """Show filter popup when a column header is clicked (toggle behavior)."""
        if not self._filterable or col_index < 0 or col_index >= self._column_count:
            return
        
        # If popup is open for THIS column, close it (toggle off) and return
        if self._filter_popup and getattr(self._filter_popup, '_col_index', None) == col_index:
            self._filter_popup.close()
            self._filter_popup = None
            self._data_table.clearSelection()
            return
        
        # Close any existing popup (different column)
        if self._filter_popup:
            self._filter_popup.close()
            self._filter_popup = None
        
        # Compute unique values for this column, considering OTHER columns' filters
        unique_values = self._get_filtered_unique_values(col_index)
        current_selection = self._column_filters.get(col_index, set())
        
        # Create and show popup
        self._filter_popup = ColumnFilterPopup(col_index, unique_values, current_selection, self)
        self._filter_popup.filter_changed.connect(self._on_filter_changed)
        self._filter_popup.clear_all_requested.connect(self._clear_all_filters)
        
        # Position popup below the header, aligned to the column
        header = self._data_table.horizontalHeader()
        header_pos = header.mapToGlobal(header.rect().bottomLeft())
        col_x = header.sectionPosition(col_index) - header.offset()
        popup_x = header_pos.x() + col_x
        popup_y = header_pos.y() + 1
        
        self._filter_popup.move(QPoint(popup_x, popup_y))
        self._filter_popup.show()
        
        # Clear the column selection so it doesn't highlight yellow
        self._data_table.clearSelection()
    
    def _get_filtered_unique_values(self, col_index: int) -> list:
        """Get sorted unique values for a column, considering all OTHER columns' filters.
        
        This provides Excel-style cross-column filtering: the dropdown for a column
        only shows values that exist in rows passing all OTHER columns' filters.
        """
        values = set()
        row_count = self._data_table.rowCount()
        
        for row in range(row_count):
            # Check if this row passes ALL other column filters (not col_index)
            passes = True
            for other_col, selected_vals in self._column_filters.items():
                if other_col == col_index or not selected_vals:
                    continue
                item = self._data_table.item(row, other_col)
                cell_text = item.text() if item else ""
                if cell_text not in selected_vals:
                    passes = False
                    break
            
            if passes:
                item = self._data_table.item(row, col_index)
                cell_text = item.text() if item else ""
                values.add(cell_text)
        
        # Sort: numbers first (by value), then dates chronologically, then strings
        def sort_key(v):
            # Try numeric
            try:
                return (0, float(v.replace(',', '').replace('$', '').replace('%', '')))
            except (ValueError, AttributeError):
                pass
            # Try date (m/d/yyyy or mm/dd/yyyy)
            try:
                from datetime import datetime
                dt = datetime.strptime(v.strip(), "%m/%d/%Y")
                return (0.5, dt.timestamp())
            except (ValueError, AttributeError):
                pass
            return (1, v)
        
        return sorted(values, key=sort_key)
    
    def _on_filter_changed(self, col_index: int, selected_values: set):
        """Handle filter change from popup."""
        if selected_values:
            self._column_filters[col_index] = selected_values
        else:
            self._column_filters.pop(col_index, None)
        
        self._apply_filters()
        self._update_header_indicators()
    
    def _apply_filters(self):
        """Show/hide rows based on active column filters."""
        row_count = self._data_table.rowCount()
        
        if not self._column_filters:
            # No filters active - show all rows
            for row in range(row_count):
                self._data_table.setRowHidden(row, False)
            return
        
        for row in range(row_count):
            visible = True
            for col, selected_vals in self._column_filters.items():
                if not selected_vals:
                    continue
                item = self._data_table.item(row, col)
                cell_text = item.text() if item else ""
                if cell_text not in selected_vals:
                    visible = False
                    break
            self._data_table.setRowHidden(row, not visible)
    
    def _clear_all_filters(self, apply: bool = True):
        """Clear all column filters and show all rows."""
        self._column_filters.clear()
        if apply:
            row_count = self._data_table.rowCount()
            for row in range(row_count):
                self._data_table.setRowHidden(row, False)
            self._update_header_indicators()
    
    def _update_header_indicators(self):
        """Update header labels to show filter indicators."""
        if not self._original_headers:
            return
        for col in range(min(len(self._original_headers), self._column_count)):
            base_label = self._original_headers[col]
            if col in self._column_filters and self._column_filters[col]:
                label = f"{base_label} ▼"
            else:
                label = base_label
            h_item = self._data_table.horizontalHeaderItem(col)
            if h_item:
                h_item.setText(label)
    
    def _show_context_menu(self, pos):
        """Show context menu for the table."""
        from PyQt6.QtWidgets import QMenu, QApplication
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)
        
        item = self._data_table.itemAt(pos)
        
        if item:
            copy_cell_action = menu.addAction("Copy Cell")
        else:
            copy_cell_action = None
        
        copy_row_action = menu.addAction("Copy Row")
        copy_table_action = menu.addAction("Copy Entire Table")
        menu.addSeparator()
        dump_excel_action = menu.addAction("Dump to Excel")
        
        action = menu.exec(self._data_table.mapToGlobal(pos))
        
        if action == copy_cell_action and item:
            QApplication.clipboard().setText(item.text())
        elif action == copy_row_action:
            row = self._data_table.currentRow()
            if row >= 0:
                cells = []
                for c in range(self._data_table.columnCount()):
                    item = self._data_table.item(row, c)
                    cells.append(item.text() if item else "")
                QApplication.clipboard().setText("\t".join(cells))
        elif action == copy_table_action:
            self._copy_table_to_clipboard()
        elif action == dump_excel_action:
            self._dump_to_excel()
    
    def _copy_table_to_clipboard(self):
        """Copy visible table rows (headers + data) to clipboard."""
        from PyQt6.QtWidgets import QApplication
        lines = []
        
        # Headers from native QHeaderView (strip filter indicator)
        headers = []
        for i in range(self._data_table.columnCount()):
            h_item = self._data_table.horizontalHeaderItem(i)
            header_text = h_item.text() if h_item else ""
            if header_text.endswith(" ▼"):
                header_text = header_text[:-2]
            headers.append(header_text)
        if any(headers):
            lines.append("\t".join(headers))
        
        # Data rows (visible only - skip hidden/filtered rows)
        for row in range(self._data_table.rowCount()):
            if self._data_table.isRowHidden(row):
                continue
            cells = []
            for col in range(self._data_table.columnCount()):
                item = self._data_table.item(row, col)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))
        
        QApplication.clipboard().setText("\n".join(lines))

    def _dump_to_excel(self):
        """Open a fresh Excel workbook and dump table data with frozen header and filters."""
        try:
            from win32com.client import dynamic
            excel = dynamic.Dispatch("Excel.Application")
            excel.Visible = True
            excel.ScreenUpdating = False  # Suppress redraw until done
            wb = excel.Workbooks.Add()
            ws = wb.ActiveSheet

            col_count = self._data_table.columnCount()
            if col_count == 0:
                excel.ScreenUpdating = True
                return

            # Build header row
            headers = []
            for c in range(col_count):
                h_item = self._data_table.horizontalHeaderItem(c)
                header_text = h_item.text() if h_item else ""
                # Strip filter indicator
                if header_text.endswith(" ▼"):
                    header_text = header_text[:-2]
                headers.append(header_text)

            # Build data rows (visible only), converting numerics
            data_rows = []
            for row in range(self._data_table.rowCount()):
                if self._data_table.isRowHidden(row):
                    continue
                row_data = []
                for col in range(col_count):
                    item = self._data_table.item(row, col)
                    cell_text = item.text() if item else ""
                    if cell_text:
                        clean = cell_text.replace(",", "").replace("$", "").replace("%", "").strip()
                        try:
                            row_data.append(float(clean))
                        except (ValueError, TypeError):
                            row_data.append(cell_text)
                    else:
                        row_data.append(cell_text)
                data_rows.append(tuple(row_data))

            # Bulk-write header + data in a single COM call
            all_rows = [tuple(headers)] + data_rows
            total_rows = len(all_rows)
            rng = ws.Range(ws.Cells(1, 1), ws.Cells(total_rows, col_count))
            rng.Value = all_rows

            # Bold the header row
            ws.Range(ws.Cells(1, 1), ws.Cells(1, col_count)).Font.Bold = True

            # Freeze top row
            ws.Range("A2").Select()
            excel.ActiveWindow.FreezePanes = True

            # Add auto-filters
            if total_rows > 1:
                ws.Range(ws.Cells(1, 1), ws.Cells(total_rows, col_count)).AutoFilter()

            # Auto-fit columns
            ws.Columns.AutoFit()

            # Select cell A1 and re-enable screen updating
            ws.Range("A1").Select()
            excel.ScreenUpdating = True

        except ImportError:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "win32com is not available. Cannot export to Excel.")
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Excel Error", f"Failed to dump to Excel:\n{e}")


# =============================================================================
# STYLED INFO TABLE GROUP - Compound info + table widget
# =============================================================================

class StyledInfoTableGroup(QGroupBox):
    """
    Unified styled container that can display:
    - Info fields only (label/value pairs) - use show_table=False
    - Table only - use show_info=False
    - Both info fields and table (default)
    
    Features:
    - Blue bordered GroupBox with rounded corners and gold title
    - Variable columns for info section
    - Compact table with styled scrollbars and rounded corners
    - Fixed header that doesn't scroll vertically
    - Right-click copy on all values and table cells
    
    Usage Examples:
    
    # Info fields only (like Policy Info)
    info = StyledInfoTableGroup("Policy Info", columns=3, show_table=False)
    info.add_field("Policy", "policy_val", 80, 80)
    info.set_value("policy_val", "U0532652")
    
    # Table only (like Coverages, Benefits)
    table = StyledInfoTableGroup("Coverages", show_info=False)
    table.setup_table(["Phs", "Form", "Plancode", "Amount"])
    table.load_table_data([["1", "MLUL", "MLUL502", "110,000"]])
    
    # Both (like TAMRA Values)
    hybrid = StyledInfoTableGroup("TAMRA Values", columns=1)
    hybrid.add_field("7 Pay Prem", "seven_pay", 100, 80)
    hybrid.setup_table(["Year", "Premium", "Withdrawal"])
    hybrid.set_value("seven_pay", "4,807.83")
    hybrid.load_table_data([["1", "457.68", "0.00"]])
    """
    
    def __init__(self, title: str, columns: int = 1, 
                 show_info: bool = True, show_table: bool = True, 
                 filterable: bool = False, parent=None):
        """
        Args:
            title: GroupBox title text
            columns: Number of columns for info field layout
            show_info: Whether to show the info fields section
            show_table: Whether to show the table section
            filterable: Whether to enable Excel-style column filtering on the table
        """
        super().__init__(title, parent)
        self._columns = columns
        self._show_info = show_info
        self._show_table = show_table
        self._filterable = filterable
        self._fields = {}  # attr_name -> CopyableLabel
        self._current_row = 0
        self._current_col = 0
        self.table = None  # Will be created if show_table=True
        self._info_widget = None  # Will be created if show_info=True
        self.setStyleSheet(POLICY_INFO_FRAME_STYLE)
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the main layout with optional info section and/or table."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 16, 6, 4)
        main_layout.setSpacing(2)
        
        # Style definitions - transparent backgrounds for labels
        self._lbl_style = f"font-size: 11px; font-weight: bold; color: {BLUE_DARK}; background: transparent; border: none;"
        self._val_style = f"font-size: 11px; color: {GRAY_DARK}; background: transparent; border: none;"
        
        # Info section (optional)
        if self._show_info:
            self._info_widget = QWidget()
            self._info_widget.setStyleSheet("background: transparent;")
            self._info_layout = QGridLayout(self._info_widget)
            self._info_layout.setContentsMargins(0, 0, 0, 0)
            self._info_layout.setHorizontalSpacing(4)
            self._info_layout.setVerticalSpacing(2)
            # Layout: each field group uses 3 grid columns: label, value, gutter
            # Explicitly set stretch=0 on all label/value columns so they don't grow
            for c in range(self._columns):
                self._info_layout.setColumnStretch(c * 3, 0)      # label col
                self._info_layout.setColumnStretch(c * 3 + 1, 0)  # value col
            # Final column absorbs remaining space to pack fields left
            self._info_layout.setColumnStretch(self._columns * 3 - 1, 1)
            # Add fixed-width gutter columns between groups for visual separation
            if self._columns > 1:
                for i in range(self._columns - 1):
                    gutter_col = i * 3 + 2
                    self._info_layout.setColumnMinimumWidth(gutter_col, 20)
            main_layout.addWidget(self._info_widget)
        
        # Table section (optional)
        if self._show_table:
            # Use our new FixedHeaderTableWidget
            self.table = FixedHeaderTableWidget(filterable=self._filterable)
            main_layout.addWidget(self.table, 1)  # Stretch factor 1
        else:
            # If no table, add stretch to push info fields to top (consistent spacing)
            main_layout.addStretch(1)
        
        # Enable context menu on container
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_container_context_menu)
    
    # -------------------------------------------------------------------------
    # Info field methods
    # -------------------------------------------------------------------------
    
    def add_field(self, label_text: str, attr_name: str, label_width: int = 80, value_width: int = 80,
                  tooltip_section: str = "", tooltip_key: str = ""):
        """
        Add a label/value field pair to the info section.
        
        Args:
            label_text: Display text for the label
            attr_name: Attribute name for accessing the value programmatically
            label_width: Width of the label in pixels
            value_width: Width of the value field in pixels
            tooltip_section: Section name in tooltips JSON (e.g., "AdvProdValues")
            tooltip_key: Field key in tooltips JSON (defaults to attr_name if not provided)
        """
        if not self._show_info:
            raise RuntimeError("Cannot add fields when show_info=False")
        
        # Calculate actual column position (each field uses 3 grid cols: label + value + gutter)
        col_group = self._current_col * 3
        
        # Get tooltip text if section specified
        tooltip_text = ""
        if tooltip_section:
            tip_key = tooltip_key if tooltip_key else attr_name
            tooltip_text = get_tooltip_manager().get_tooltip(tooltip_section, tip_key)
        
        # Create label - use ClickableTooltipLabel if tooltip exists
        display_text = label_text + ":" if not label_text.endswith(":") else label_text
        if tooltip_text:
            lbl = ClickableTooltipLabel(display_text, tooltip_text)
        else:
            lbl = QLabel(display_text)
        lbl.setStyleSheet(self._lbl_style)
        lbl.setFixedWidth(label_width)
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._info_layout.addWidget(lbl, self._current_row, col_group)
        
        # Create copyable value label (right-aligned for numeric values)
        val_lbl = CopyableLabel("")
        val_lbl.setStyleSheet(self._val_style)
        val_lbl.setMinimumWidth(value_width)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._info_layout.addWidget(val_lbl, self._current_row, col_group + 1)
        
        # Store references
        self._fields[attr_name] = val_lbl
        if not hasattr(self, '_labels'):
            self._labels = {}
        self._labels[attr_name] = lbl
        setattr(self, attr_name, val_lbl)
        
        # Advance to next position
        self._current_col += 1
        if self._current_col >= self._columns:
            self._current_col = 0
            self._current_row += 1
    
    def set_field_tooltip(self, attr_name: str, tooltip_text: str):
        """Set or update tooltip for a field label."""
        if hasattr(self, '_labels') and attr_name in self._labels:
            lbl = self._labels[attr_name]
            if isinstance(lbl, ClickableTooltipLabel):
                lbl.set_tooltip_text(tooltip_text)
    
    def set_value(self, attr_name: str, value: str):
        """Set the value of an info field by attribute name."""
        if attr_name in self._fields:
            text = str(value).strip() if value is not None else ""
            self._fields[attr_name].setText(text)
    
    def get_value(self, attr_name: str) -> str:
        """Get the value of an info field by attribute name."""
        if attr_name in self._fields:
            return self._fields[attr_name].text()
        return ""
    
    def clear_info(self):
        """Clear all info field values."""
        for val_lbl in self._fields.values():
            val_lbl.setText("")
    
    # -------------------------------------------------------------------------
    # Table methods
    # -------------------------------------------------------------------------
    
    def setup_table(self, headers: list):
        """Setup the table with column headers."""
        if not self._show_table:
            raise RuntimeError("Cannot setup table when show_table=False")
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        # Right-align all headers by default
        header = self.table._data_table.horizontalHeader()
        for col in range(len(headers)):
            item = self.table._data_table.horizontalHeaderItem(col)
            if item:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    
    def load_table_data(self, rows: list):
        """
        Load data into the table.
        
        Args:
            rows: List of row data, where each row is a list of cell values.
                  All columns are right-aligned by default.
        """
        if not self._show_table:
            raise RuntimeError("Cannot load table data when show_table=False")
        self.table.setRowCount(len(rows))
        for row_idx, row_data in enumerate(rows):
            for col_idx, cell_value in enumerate(row_data):
                text = str(cell_value) if cell_value is not None else ""
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, col_idx, item)
        self.table.autoFitAllColumns()
    
    def load_data(self, columns: List[str], rows: List[tuple]):
        """
        Load data into the table (alternative API matching old StyledTableGroup).
        
        Args:
            columns: List of column header names
            rows: List of row tuples
        """
        if not self._show_table:
            raise RuntimeError("Cannot load data when show_table=False")
        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(rows))
        
        for row_idx, row_data in enumerate(rows):
            for col_idx, value in enumerate(row_data):
                text = str(value) if value is not None else ""
                item = QTableWidgetItem(text)
                if is_numeric(text):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_idx, col_idx, item)
        
        self.table.autoFitAllColumns()
    
    def clear_table(self):
        """Clear all table data."""
        if self.table:
            self.table.clear()
    
    def clear_all(self):
        """Clear both info fields and table data."""
        self.clear_info()
        self.clear_table()
    
    # -------------------------------------------------------------------------
    # Context menu methods
    # -------------------------------------------------------------------------
    
    def _show_container_context_menu(self, pos):
        """Show context menu when right-clicking on container."""
        from PyQt6.QtWidgets import QMenu, QApplication
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)
        
        if self._show_table and self.table.rowCount() > 0:
            copy_table_action = menu.addAction("Copy Entire Table")
            dump_excel_action = menu.addAction("Dump to Excel")
            action = menu.exec(self.mapToGlobal(pos))
            if action == copy_table_action:
                self.table._copy_table_to_clipboard()
            elif action == dump_excel_action:
                self.table._dump_to_excel()


# Backward compatibility alias
StyledTableGroup = lambda title, parent=None: StyledInfoTableGroup(title, show_info=False, parent=parent)


# =============================================================================
# COPYABLE / CLICKABLE LABELS
# =============================================================================

class CopyableLabel(QLabel):
    """A QLabel that supports right-click copy to clipboard."""
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    def _show_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu, QApplication
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)
        copy_action = menu.addAction("Copy")
        action = menu.exec(self.mapToGlobal(pos))
        if action == copy_action:
            selected = self.selectedText()
            QApplication.clipboard().setText(selected if selected else self.text())


class ClickableTooltipLabel(QLabel):
    """
    A QLabel that shows a tooltip popup when clicked.
    Used for field labels that have associated help text.
    Displays with a subtle underline to indicate it's clickable.
    """
    
    def __init__(self, text="", tooltip_text="", parent=None):
        super().__init__(text, parent)
        self._tooltip_text = tooltip_text
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_tooltip_menu)
        
        # Update style to show clickable indicator if has tooltip
        if tooltip_text:
            self._apply_clickable_style()
    
    def _apply_clickable_style(self):
        """Add underline to indicate clickable."""
        current_style = self.styleSheet()
        if "text-decoration" not in current_style:
            self.setStyleSheet(current_style + " text-decoration: underline;")
    
    def set_tooltip_text(self, tooltip_text: str):
        """Set or update the tooltip text."""
        self._tooltip_text = tooltip_text
        if tooltip_text:
            self._apply_clickable_style()
    
    def mousePressEvent(self, event):
        """Show tooltip popup on left click."""
        if event.button() == Qt.MouseButton.LeftButton and self._tooltip_text:
            self._show_tooltip_popup()
        super().mousePressEvent(event)
    
    def _show_tooltip_popup(self):
        """Show a styled tooltip popup near the label."""
        from PyQt6.QtWidgets import QToolTip
        # Show tooltip at cursor position
        pos = self.mapToGlobal(self.rect().bottomLeft())
        QToolTip.showText(pos, self._tooltip_text, self)
    
    def _show_tooltip_menu(self, pos):
        """Show context menu with tooltip and copy options."""
        from PyQt6.QtWidgets import QMenu, QApplication
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)
        
        if self._tooltip_text:
            info_action = menu.addAction("Show Info")
            menu.addSeparator()
        else:
            info_action = None
        
        copy_action = menu.addAction("Copy Label")
        
        action = menu.exec(self.mapToGlobal(pos))
        if action == info_action and self._tooltip_text:
            self._show_tooltip_popup()
        elif action == copy_action:
            QApplication.clipboard().setText(self.text().rstrip(":"))


# =============================================================================
# POLICY LOOKUP BAR
# =============================================================================

class PolicyLookupBar(QWidget):
    """Top bar for policy lookup with blue/gold styling."""
    
    policy_requested = pyqtSignal(str, str, str)  # policy_number, region, company_code
    company_chosen = pyqtSignal(str, str, str)     # policy_number, region, company_code
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("lookupBar")
        self._setup_ui()
    
    def _setup_ui(self):
        self.setStyleSheet(LOOKUP_BAR_STYLE)
        
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        
        # Top row: inputs + buttons
        top_row = QWidget()
        layout = QHBoxLayout(top_row)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        
        # Policy display label (shows Company - Policy after lookup) - at far left
        self.policy_label = QLabel("")
        self.policy_label.setObjectName("policyDisplay")
        self.policy_label.setTextFormat(Qt.TextFormat.RichText)
        self.policy_label.setStyleSheet(POLICY_DISPLAY_STYLE)
        layout.addWidget(self.policy_label)
        
        layout.addStretch()
        
        # Inline inputs: Region, Company, Policy # — no labels, just placeholders
        input_style = """
            QLineEdit {
                font-size: 11px; padding: 3px 4px;
                border: 1px solid #8B8B00; border-radius: 3px;
                background: white; color: #333;
            }
            QLineEdit:focus { border-color: #D4A017; }
        """
        
        self.region_input = QLineEdit()
        self.region_input.setPlaceholderText("Region")
        self.region_input.setText("CKPR")
        self.region_input.setFixedWidth(50)
        self.region_input.setStyleSheet(input_style)
        layout.addWidget(self.region_input)
        
        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("Co")
        self.company_input.setFixedWidth(30)
        self.company_input.setStyleSheet(input_style)
        layout.addWidget(self.company_input)
        
        self.policy_input = QLineEdit()
        self.policy_input.setPlaceholderText("Policy #")
        self.policy_input.setFixedWidth(90)
        self.policy_input.setStyleSheet(input_style)
        self.policy_input.returnPressed.connect(self._on_get_policy)
        layout.addWidget(self.policy_input)
        
        # Get button
        self.get_button = QPushButton("Get")
        self.get_button.clicked.connect(self._on_get_policy)
        self.get_button.setFixedWidth(50)
        self.get_button.setFixedHeight(26)
        layout.addWidget(self.get_button)
        
        # Store reference to top_row layout so main_window can add list toggle btn
        self._top_layout = layout
        outer_layout.addWidget(top_row)
        
        # Company chooser row (hidden by default) — right-aligned below inputs
        self._company_chooser = QWidget()
        self._company_chooser.setVisible(False)
        chooser_layout = QHBoxLayout(self._company_chooser)
        chooser_layout.setContentsMargins(8, 2, 8, 4)
        chooser_layout.setSpacing(6)
        
        chooser_layout.addStretch()  # Push everything to the right
        
        self._chooser_label = QLabel("Multiple companies found — select one:")
        self._chooser_label.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #0A3D0A; background: transparent;"
        )
        chooser_layout.addWidget(self._chooser_label)
        
        self._chooser_btn_container = QWidget()
        self._chooser_btn_layout = QHBoxLayout(self._chooser_btn_container)
        self._chooser_btn_layout.setContentsMargins(0, 0, 0, 0)
        self._chooser_btn_layout.setSpacing(4)
        chooser_layout.addWidget(self._chooser_btn_container)
        
        outer_layout.addWidget(self._company_chooser)
    
    def layout(self):
        """Return the top row layout so external code can add widgets to the bar."""
        return self._top_layout
    
    def _on_get_policy(self):
        self.hide_company_chooser()
        policy = self.policy_input.text().strip()
        region = self.region_input.text().strip() or "CKPR"
        company = self.company_input.text().strip()  # Allow empty!
        if policy:
            self.policy_requested.emit(policy, region, company)
    
    def set_policy_display(self, company: str, policy: str, region: str = "",
                            is_pending: bool = False):
        """Update the policy display label."""
        pending_tag = '  <span style="color:#FF1744; font-weight:bold;">(Pending)</span>' if is_pending else ''
        if region:
            self.policy_label.setText(f"{region} - {company} - {policy}{pending_tag}")
        else:
            self.policy_label.setText(f"{company} - {policy}{pending_tag}")
    
    def show_company_chooser(self, companies: list, policy_number: str, region: str):
        """Show company choice buttons when a policy exists in multiple companies."""
        # Clear old buttons
        while self._chooser_btn_layout.count():
            child = self._chooser_btn_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        for co in companies:
            btn = QPushButton(co.strip())
            btn.setFixedHeight(22)
            btn.setFixedWidth(40)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 11px; font-weight: bold;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #1B5E20, stop:1 #0A3D0A);
                    border: 1px solid #0A3D0A; border-radius: 3px;
                    color: #FFD54F; padding: 2px 8px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #2E7D32, stop:1 #1B5E20);
                    color: #FFF;
                }
            """)
            btn.clicked.connect(
                lambda checked, c=co.strip(), p=policy_number, r=region: self._on_company_chosen(p, r, c)
            )
            self._chooser_btn_layout.addWidget(btn)
        
        self._company_chooser.setVisible(True)
    
    def hide_company_chooser(self):
        """Hide the company chooser row."""
        self._company_chooser.setVisible(False)
    
    def _on_company_chosen(self, policy_number: str, region: str, company_code: str):
        """Handle a company button click."""
        self.hide_company_chooser()
        self.company_input.setText(company_code)
        self.company_chosen.emit(policy_number, region, company_code)


# =============================================================================
# TABLE DATA WIDGET - Transposed DB2 table display
# =============================================================================

class TableDataWidget(QTableWidget):
    """Widget to display DB2 table data in a TRANSPOSED grid (fields as rows)."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)  # No grid lines
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.horizontalHeader().setStretchLastSection(False)
        self.verticalHeader().setVisible(False)  # Hide row numbers
        self.verticalHeader().setMinimumSectionSize(16)
        self.verticalHeader().setDefaultSectionSize(16)  # Compact row height
        self._apply_compact_style()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _show_context_menu(self, pos):
        """Show context menu for copying cell, row, or entire table."""
        from PyQt6.QtWidgets import QMenu, QApplication
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLE)

        item = self.itemAt(pos)
        if item:
            copy_cell_action = menu.addAction("Copy Cell")
        else:
            copy_cell_action = None

        copy_row_action = menu.addAction("Copy Row")
        copy_table_action = menu.addAction("Copy Entire Table")
        menu.addSeparator()
        dump_excel_action = menu.addAction("Dump to Excel")

        action = menu.exec(self.mapToGlobal(pos))

        if action == copy_cell_action and item:
            QApplication.clipboard().setText(item.text())
        elif action == copy_row_action:
            row = self.currentRow()
            if row >= 0:
                cells = []
                for c in range(self.columnCount()):
                    it = self.item(row, c)
                    cells.append(it.text() if it else "")
                QApplication.clipboard().setText("\t".join(cells))
        elif action == copy_table_action:
            self._copy_table_to_clipboard()
        elif action == dump_excel_action:
            self._dump_to_excel()

    def _copy_table_to_clipboard(self):
        """Copy all table data (headers + rows) to clipboard."""
        from PyQt6.QtWidgets import QApplication
        lines = []
        headers = []
        for i in range(self.columnCount()):
            h_item = self.horizontalHeaderItem(i)
            headers.append(h_item.text() if h_item else "")
        if any(headers):
            lines.append("\t".join(headers))
        for row in range(self.rowCount()):
            if self.isRowHidden(row):
                continue
            cells = []
            for col in range(self.columnCount()):
                it = self.item(row, col)
                cells.append(it.text() if it else "")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))

    def _dump_to_excel(self):
        """Open a fresh Excel workbook and dump table data."""
        try:
            from win32com.client import dynamic
            excel = dynamic.Dispatch("Excel.Application")
            excel.Visible = True
            excel.ScreenUpdating = False
            wb = excel.Workbooks.Add()
            ws = wb.ActiveSheet
            for col in range(self.columnCount()):
                h_item = self.horizontalHeaderItem(col)
                ws.Cells(1, col + 1).Value = h_item.text() if h_item else ""
            for row in range(self.rowCount()):
                if self.isRowHidden(row):
                    continue
                for col in range(self.columnCount()):
                    it = self.item(row, col)
                    ws.Cells(row + 2, col + 1).Value = it.text() if it else ""
            excel.ScreenUpdating = True
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Excel Export", f"Could not export: {exc}")
    
    def _apply_compact_style(self):
        """Apply compact flat styling with minimal row height."""
        self.setStyleSheet(COMPACT_TABLE_STYLE)
        self.horizontalHeader().setDefaultSectionSize(80)
    
    def load_data(self, columns: List[str], rows: List[tuple]):
        """Load data into the table - TRANSPOSED (fields as rows, records as columns)."""
        self.clear()
        
        if not rows:
            self.setRowCount(1)
            self.setColumnCount(1)
            self.setItem(0, 0, QTableWidgetItem("No data"))
            return
        
        # Transposed: fields as rows, each record is a column
        num_fields = len(columns)
        num_records = len(rows)
        
        self.setRowCount(num_fields)
        self.setColumnCount(num_records + 1)  # +1 for field name column
        
        # Header: Field, Record 1, Record 2, ...
        headers = ["Field"] + [f"Row {i+1}" for i in range(num_records)]
        self.setHorizontalHeaderLabels(headers)
        
        # Fill transposed data
        for field_idx, field_name in enumerate(columns):
            # Field name in first column (left-aligned, bold)
            field_item = QTableWidgetItem(field_name)
            field_item.setFlags(field_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            field_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            font = field_item.font()
            font.setBold(True)
            field_item.setFont(font)
            self.setItem(field_idx, 0, field_item)
            
            # Values in subsequent columns (right-aligned)
            for rec_idx, row_data in enumerate(rows):
                value = row_data[field_idx] if field_idx < len(row_data) else ""
                text = str(value) if value is not None else ""
                value_item = QTableWidgetItem(text)
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(field_idx, rec_idx + 1, value_item)
        
        self.resizeColumnsToContents()
    
    def load_dict_data(self, data: Dict[str, Any]):
        """Load a single-row dict as field/value pairs (already transposed format)."""
        self.clear()
        self.setColumnCount(2)
        self.setRowCount(len(data))
        self.setHorizontalHeaderLabels(["Field", "Value"])
        
        for row_idx, (field, value) in enumerate(data.items()):
            field_item = QTableWidgetItem(field)
            field_item.setFlags(field_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            field_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            font = field_item.font()
            font.setBold(True)
            field_item.setFont(font)
            self.setItem(row_idx, 0, field_item)
            
            text = str(value) if value is not None else ""
            value_item = QTableWidgetItem(text)
            value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row_idx, 1, value_item)
        
        self.resizeColumnsToContents()
