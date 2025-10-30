"""FilterTableView - Excel-style filterable table view for DataFrames"""

import logging
from typing import Optional, Dict, Set, List, Any
import pandas as pd
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableView, 
                              QHeaderView, QLineEdit, QPushButton, QMenu, 
                              QCheckBox, QScrollArea, QLabel, QFrame, QWidgetAction)
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, pyqtSignal
from PyQt6.QtGui import QFont, QAction

logger = logging.getLogger(__name__)


class PandasTableModel(QAbstractTableModel):
    """Table model for displaying filtered Pandas DataFrame"""

    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self._original_df = df.copy()  # Keep original
        self._filtered_df = df.copy()  # Working filtered copy
        self._display_df = df.copy()   # After global search

    def set_filtered_data(self, df: pd.DataFrame):
        """Update the filtered dataset"""
        self.beginResetModel()
        self._filtered_df = df.copy()
        self._display_df = df.copy()
        self.endResetModel()

    def set_display_data(self, df: pd.DataFrame):
        """Update the display dataset (after global search)"""
        self.beginResetModel()
        self._display_df = df.copy()
        self.endResetModel()

    def get_original_data(self) -> pd.DataFrame:
        """Get the original unfiltered data"""
        return self._original_df

    def get_filtered_data(self) -> pd.DataFrame:
        """Get the filtered data (after column filters, before search)"""
        return self._filtered_df

    def get_display_data(self) -> pd.DataFrame:
        """Get the currently displayed data"""
        return self._display_df

    def rowCount(self, parent=QModelIndex()):
        return len(self._display_df)

    def columnCount(self, parent=QModelIndex()):
        return len(self._display_df.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            value = self._display_df.iloc[index.row(), index.column()]
            if pd.isna(value):
                return ""
            return str(value)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return str(self._display_df.columns[section])
            else:
                return str(section + 1)
        return None


class FilterPopup(QMenu):
    """Popup menu for column filtering with checkbox list"""

    filter_changed = pyqtSignal(str, set)  # column_name, selected_values
    
    MAX_DISPLAY_VALUES = 500  # Maximum values to show at once

    def __init__(self, column_name: str, unique_values: List[Any], 
                 current_selection: Optional[Set[Any]] = None, parent=None):
        super().__init__(parent)
        self.column_name = column_name
        
        # Convert and sort unique values
        self.all_unique_values = sorted([str(v) if not pd.isna(v) else "(Blanks)" 
                                         for v in unique_values])
        
        # Check if we have too many values
        self.has_many_values = len(self.all_unique_values) > self.MAX_DISPLAY_VALUES
        
        # For large datasets, initially show only first MAX_DISPLAY_VALUES
        if self.has_many_values:
            self.unique_values = self.all_unique_values[:self.MAX_DISPLAY_VALUES]
            self.showing_partial = True
        else:
            self.unique_values = self.all_unique_values
            self.showing_partial = False
        
        self.current_selection = current_selection if current_selection else set(self.all_unique_values)
        
        self.checkboxes = {}
        self.init_ui()

    def init_ui(self):
        """Initialize the filter popup UI"""
        # Create a widget to hold everything
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Warning label for large datasets
        if self.has_many_values:
            warning_label = QLabel(
                f"⚠️ {len(self.all_unique_values):,} unique values detected.\n"
                f"Use search box to filter values efficiently."
            )
            warning_label.setStyleSheet("""
                background-color: #fff3cd;
                color: #856404;
                padding: 5px;
                border-radius: 3px;
                font-size: 10px;
            """)
            warning_label.setWordWrap(True)
            layout.addWidget(warning_label)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search values...")
        self.search_box.textChanged.connect(self.filter_checkbox_list)
        layout.addWidget(self.search_box)

        # Select All / Deselect All buttons
        button_layout = QHBoxLayout()
        
        select_all_btn = QPushButton("✓ Select All")
        select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("✗ Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(deselect_all_btn)
        
        layout.addLayout(button_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # Scrollable checkbox list
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(400)
        scroll_area.setMinimumWidth(250)

        self.checkbox_widget = QWidget()
        self.checkbox_layout = QVBoxLayout(self.checkbox_widget)
        self.checkbox_layout.setContentsMargins(5, 5, 5, 5)
        self.checkbox_layout.setSpacing(2)  # Tighter spacing

        # Create checkboxes for initial values
        self.create_checkboxes(self.unique_values)

        self.checkbox_widget.setLayout(self.checkbox_layout)
        scroll_area.setWidget(self.checkbox_widget)
        layout.addWidget(scroll_area)
        
        # Info label
        self.info_label = QLabel()
        self.update_info_label()
        self.info_label.setStyleSheet("font-size: 9px; color: #666; padding: 2px;")
        layout.addWidget(self.info_label)

        # Separator
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator2)

        # OK / Cancel buttons
        action_layout = QHBoxLayout()
        
        ok_btn = QPushButton("✓ OK")
        ok_btn.clicked.connect(self.apply_filter)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        action_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("✗ Cancel")
        cancel_btn.clicked.connect(self.close)
        action_layout.addWidget(cancel_btn)
        
        layout.addLayout(action_layout)

        # Add container as a widget action
        action = QWidgetAction(self)
        action.setDefaultWidget(container)
        self.addAction(action)

        # Style
        self.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #ccc;
            }
            QCheckBox {
                padding: 2px;
            }
            QPushButton {
                padding: 4px 8px;
            }
        """)

    def create_checkboxes(self, values: List[str]):
        """Create checkboxes for given values"""
        for value in values:
            cb = QCheckBox(str(value))
            cb.setChecked(value in self.current_selection)
            cb.stateChanged.connect(self.on_checkbox_changed)
            self.checkboxes[value] = cb
            self.checkbox_layout.addWidget(cb)
    
    def filter_checkbox_list(self, search_text: str):
        """Filter the checkbox list based on search text - rebuild for efficiency"""
        search_text = search_text.lower().strip()
        
        # Clear existing checkboxes
        for cb in self.checkboxes.values():
            cb.setParent(None)
            cb.deleteLater()
        self.checkboxes.clear()
        
        # Filter values based on search
        if search_text:
            # Search in all values, but limit display
            matching_values = [v for v in self.all_unique_values 
                             if search_text in str(v).lower()]
            
            # Limit to MAX_DISPLAY_VALUES for performance
            display_values = matching_values[:self.MAX_DISPLAY_VALUES]
            self.showing_partial = len(matching_values) > self.MAX_DISPLAY_VALUES
        else:
            # No search - show initial set
            if self.has_many_values:
                display_values = self.all_unique_values[:self.MAX_DISPLAY_VALUES]
                self.showing_partial = True
            else:
                display_values = self.all_unique_values
                self.showing_partial = False
        
        # Create checkboxes for filtered values
        self.create_checkboxes(display_values)
        
        # Update info
        self.update_info_label()
    
    def update_info_label(self):
        """Update the info label"""
        visible_count = len(self.checkboxes)
        total_count = len(self.all_unique_values)
        
        if self.showing_partial:
            self.info_label.setText(
                f"Showing {visible_count:,} of {total_count:,} values\n"
                f"Use search to find specific values"
            )
        else:
            self.info_label.setText(f"Showing all {total_count:,} values")

    def select_all(self):
        """Select all visible checkboxes and update current_selection"""
        for value, cb in self.checkboxes.items():
            if cb.isVisible():
                cb.setChecked(True)
                self.current_selection.add(value)

    def deselect_all(self):
        """Deselect all visible checkboxes and update current_selection"""
        for value, cb in self.checkboxes.items():
            if cb.isVisible():
                cb.setChecked(False)
                self.current_selection.discard(value)

    def on_checkbox_changed(self, state):
        """Handle checkbox state change - update current_selection"""
        sender = self.sender()
        for value, cb in self.checkboxes.items():
            if cb == sender:
                if cb.isChecked():
                    self.current_selection.add(value)
                else:
                    self.current_selection.discard(value)
                break

    def apply_filter(self):
        """Apply the filter and emit signal"""
        # Emit current selection (includes items not currently visible)
        self.filter_changed.emit(self.column_name, self.current_selection)
        self.close()

    def get_selected_values(self) -> Set[str]:
        """Get currently selected values"""
        return {value for value, cb in self.checkboxes.items() if cb.isChecked()}


class FilterTableView(QWidget):
    """Excel-style filterable table view for DataFrames"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.df: Optional[pd.DataFrame] = None
        self.model: Optional[PandasTableModel] = None
        self.column_filters: Dict[str, Set[Any]] = {}  # column_name -> selected_values
        self.filtered_columns: Set[str] = set()  # Columns with active filters
        
        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Global search box at top
        search_layout = QHBoxLayout()
        search_label = QLabel("🔍 Search:")
        search_layout.addWidget(search_label)
        
        self.global_search_box = QLineEdit()
        self.global_search_box.setPlaceholderText("Search across all columns...")
        self.global_search_box.textChanged.connect(self.apply_global_search)
        search_layout.addWidget(self.global_search_box)

        # Clear filters button
        clear_btn = QPushButton("✗ Clear All Filters")
        clear_btn.clicked.connect(self.clear_all_filters)
        search_layout.addWidget(clear_btn)

        layout.addLayout(search_layout)

        # Table view
        self.table_view = QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setStyleSheet("""
            QTableView {
                gridline-color: #d0d0d0;
                background-color: white;
                alternate-background-color: #f9f9f9;
                selection-background-color: #667eea;
            }
            QHeaderView::section {
                background-color: #34495e;
                color: white;
                padding: 5px;
                border: 1px solid #2c3e50;
                font-weight: bold;
            }
            QHeaderView::section:hover {
                background-color: #415a77;
            }
        """)

        # Configure header
        self.header = self.table_view.horizontalHeader()
        self.header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.header.setStretchLastSection(True)
        self.header.sectionClicked.connect(self.show_filter_popup)
        self.header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.header.customContextMenuRequested.connect(self.show_column_context_menu)

        # Set font
        font = QFont("Consolas", 9)
        self.table_view.setFont(font)

        layout.addWidget(self.table_view)

        # Info label at bottom
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #666; font-size: 10px; padding: 2px;")
        layout.addWidget(self.info_label)

    def set_dataframe(self, df: pd.DataFrame):
        """Set the DataFrame to display"""
        self.df = df.copy()
        self.model = PandasTableModel(self.df)
        self.table_view.setModel(self.model)
        
        # Reset filters
        self.column_filters.clear()
        self.filtered_columns.clear()
        self.global_search_box.clear()
        
        # Update info
        self.update_info_label()
        
        logger.info(f"FilterTableView loaded {len(df)} rows, {len(df.columns)} columns")

    def show_filter_popup(self, column_index: int):
        """Show filter popup for a column"""
        if self.model is None:
            return

        column_name = self.df.columns[column_index]
        
        # Get unique values from currently filtered data
        filtered_df = self.model.get_filtered_data()
        unique_values = filtered_df[column_name].unique()
        
        # Get current selection for this column (default to all)
        current_selection = self.column_filters.get(column_name, None)
        
        # Create and show popup
        popup = FilterPopup(column_name, unique_values, current_selection, self)
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
        
        popup.exec(popup_position)

    def apply_column_filter(self, column_name: str, selected_values: Set[str]):
        """Apply filter to a specific column"""
        if self.model is None:
            return

        # Store filter
        all_values = set(str(v) if not pd.isna(v) else "(Blanks)" 
                        for v in self.df[column_name].unique())
        
        if selected_values == all_values:
            # All selected = no filter
            if column_name in self.column_filters:
                del self.column_filters[column_name]
            self.filtered_columns.discard(column_name)
        else:
            self.column_filters[column_name] = selected_values
            self.filtered_columns.add(column_name)
        
        # Apply all column filters
        self.apply_all_filters()
        
        # Update header to show filter indicator
        self.update_header_indicators()

    def apply_all_filters(self):
        """Apply all column filters to the DataFrame"""
        if self.model is None:
            return

        # Start with original data
        filtered_df = self.df.copy()

        # Apply each column filter
        for column_name, selected_values in self.column_filters.items():
            # Convert column values to strings for comparison (handle blanks)
            mask = filtered_df[column_name].apply(
                lambda x: (str(x) if not pd.isna(x) else "(Blanks)") in selected_values
            )
            filtered_df = filtered_df[mask]

        # Update model
        self.model.set_filtered_data(filtered_df)
        
        # Re-apply global search if active
        if self.global_search_box.text():
            self.apply_global_search(self.global_search_box.text())
        else:
            self.model.set_display_data(filtered_df)
        
        self.update_info_label()
        
        logger.info(f"Filters applied: {len(filtered_df)} rows visible")

    def apply_global_search(self, search_text: str):
        """Apply global search across all columns"""
        if self.model is None:
            return

        search_text = search_text.lower().strip()
        
        if not search_text:
            # No search - show filtered data
            self.model.set_display_data(self.model.get_filtered_data())
        else:
            # Search within filtered data
            filtered_df = self.model.get_filtered_data()
            
            # Create mask for rows containing search text in any column
            mask = filtered_df.apply(
                lambda row: any(search_text in str(val).lower() for val in row),
                axis=1
            )
            
            search_results = filtered_df[mask]
            self.model.set_display_data(search_results)
        
        self.update_info_label()

    def clear_all_filters(self):
        """Clear all filters and reset to original data"""
        self.column_filters.clear()
        self.filtered_columns.clear()
        self.global_search_box.clear()
        
        if self.model:
            self.model.set_filtered_data(self.df)
            self.model.set_display_data(self.df)
        
        self.update_header_indicators()
        self.update_info_label()

    def update_header_indicators(self):
        """Update header to show filter indicators"""
        # For now, we'll change header text to include funnel icon
        # In a more advanced implementation, we could use custom header painting
        if self.model is None:
            return
        
        # Note: QTableView doesn't easily support per-section icons in header
        # We'll add this to column name for now
        # A proper implementation would require custom QHeaderView
        pass

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
        """Show context menu for column operations (hide/show)"""
        column_index = self.header.logicalIndexAt(pos)
        if column_index < 0:
            return

        menu = QMenu(self)
        
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

    def get_filtered_dataframe(self) -> pd.DataFrame:
        """Get the currently filtered/displayed DataFrame"""
        if self.model:
            return self.model.get_display_data()
        return pd.DataFrame()
