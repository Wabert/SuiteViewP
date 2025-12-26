"""Optimized FilterPopup using QListView instead of QCheckBox widgets"""

from typing import Optional, Set, List, Any
import pandas as pd
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QMenu, QLabel, QWidgetAction, QListView, QCheckBox
from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QSortFilterProxyModel, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

import logging
logger = logging.getLogger(__name__)


class CheckableListModel(QAbstractListModel):
    """Lightweight model for checkable list items - only stores data, no widgets"""
    
    def __init__(self, values: List[str], checked_values: Set[str], parent=None):
        super().__init__(parent)
        self._values = values  # All values
        self._checked = set(checked_values)  # Set of checked values for O(1) lookup
        
    def rowCount(self, parent=QModelIndex()):
        return len(self._values)
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._values):
            return None
        
        value = self._values[index.row()]
        
        if role == Qt.ItemDataRole.DisplayRole:
            return value
        elif role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if value in self._checked else Qt.CheckState.Unchecked
        
        return None
    
    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or index.row() >= len(self._values):
            return False
        
        if role == Qt.ItemDataRole.CheckStateRole:
            item_value = self._values[index.row()]
            if value == Qt.CheckState.Checked:
                self._checked.add(item_value)
            else:
                self._checked.discard(item_value)
            self.dataChanged.emit(index, index, [role])
            return True
        
        return False
    
    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
    
    def get_checked_values(self) -> Set[str]:
        """Return set of currently checked values"""
        return self._checked.copy()
    
    def set_all_checked(self, checked: bool):
        """Check or uncheck all items"""
        if checked:
            self._checked = set(self._values)
        else:
            self._checked.clear()
        # Emit data changed for all items
        if self._values:
            self.dataChanged.emit(self.index(0), self.index(len(self._values) - 1), [Qt.ItemDataRole.CheckStateRole])
    
    def get_all_values(self) -> List[str]:
        """Return all values in the model"""
        return self._values


class FilterPopup(QMenu):
    """Optimized filter popup using QListView for fast rendering of thousands of items"""

    filter_changed = pyqtSignal(str, set)  # column_name, selected_values
    
    def __init__(self, column_name: str, unique_values: List[Any], 
                 current_selection: Optional[Set[Any]] = None, parent=None):
        super().__init__(parent)
        self.column_name = column_name
        
        # Convert and sort unique values
        self.all_unique_values = sorted([str(v) if not pd.isna(v) else "(Blanks)" 
                                         for v in unique_values])
        
        # Current selection (all values if None)
        if current_selection is None:
            self.current_selection = set(self.all_unique_values)
        else:
            self.current_selection = current_selection
        
        # Create model
        self.model = CheckableListModel(self.all_unique_values, self.current_selection)
        
        # Create proxy model for filtering
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        
        self.init_ui()

    def init_ui(self):
        """Initialize the filter popup UI"""
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
        self.search_box.textChanged.connect(self.on_search_changed)
        self.search_box.returnPressed.connect(self.apply_filter)
        layout.addWidget(self.search_box)

        # Control buttons row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(5)
        
        # Clear Filter button
        clear_btn = QPushButton("Clear Filter")
        clear_btn.setStyleSheet("""
            QPushButton {
                font-size: 10px;
                padding: 2px 8px;
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        clear_btn.clicked.connect(self.clear_filter)
        controls_layout.addWidget(clear_btn)
        
        # Select All / Deselect All toggle
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setStyleSheet("""
            QPushButton {
                font-size: 10px;
                padding: 2px 8px;
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.select_all_btn.clicked.connect(self.toggle_select_all)
        controls_layout.addWidget(self.select_all_btn)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        # List view for values (FAST - virtual rendering)
        self.list_view = QListView()
        self.list_view.setModel(self.proxy_model)
        self.list_view.setMinimumWidth(200)
        self.list_view.setMaximumWidth(400)
        self.list_view.setMinimumHeight(200)
        self.list_view.setMaximumHeight(400)
        self.list_view.setStyleSheet("""
            QListView {
                font-size: 10px;
                border: 1px solid #ccc;
                background-color: white;
            }
            QListView::item {
                padding: 2px;
            }
            QListView::item:hover {
                background-color: #e8f0fa;
            }
        """)
        
        # Connect model changes to update selection
        self.model.dataChanged.connect(self.on_model_data_changed)
        
        layout.addWidget(self.list_view)

        # Info label
        self.info_label = QLabel(f"{len(self.all_unique_values):,} values")
        self.info_label.setStyleSheet("font-size: 9px; color: #666; padding: 2px;")
        layout.addWidget(self.info_label)

        # OK button
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 15px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        ok_btn.clicked.connect(self.apply_filter)
        layout.addWidget(ok_btn)

        # Add widget action
        action = QWidgetAction(self)
        action.setDefaultWidget(container)
        self.addAction(action)

        self.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 2px solid #3498db;
                border-radius: 5px;
            }
        """)
        
        # Auto-focus the search box
        QTimer.singleShot(0, self.search_box.setFocus)
        
        # Update button state
        self.update_select_all_button()

    def on_search_changed(self, text: str):
        """Filter the list based on search text"""
        self.proxy_model.setFilterFixedString(text)
        
        # Update info label
        visible_count = self.proxy_model.rowCount()
        total_count = len(self.all_unique_values)
        
        if text:
            self.info_label.setText(f"Showing {visible_count:,} of {total_count:,} values")
        else:
            self.info_label.setText(f"{total_count:,} values")

    def on_model_data_changed(self):
        """Update button state when checks change"""
        self.update_select_all_button()

    def update_select_all_button(self):
        """Update the Select All button text based on current state"""
        checked_count = len(self.model.get_checked_values())
        total_count = len(self.all_unique_values)
        
        if checked_count == total_count:
            self.select_all_btn.setText("Deselect All")
        else:
            self.select_all_btn.setText("Select All")

    def toggle_select_all(self):
        """Toggle between select all and deselect all"""
        checked_count = len(self.model.get_checked_values())
        total_count = len(self.all_unique_values)
        
        if checked_count == total_count:
            # Deselect all
            self.model.set_all_checked(False)
        else:
            # Select all
            self.model.set_all_checked(True)
        
        self.update_select_all_button()

    def clear_filter(self):
        """Clear the filter (select all and apply)"""
        self.model.set_all_checked(True)
        self.apply_filter()

    def apply_filter(self):
        """Apply the filter and emit signal"""
        checked_values = self.model.get_checked_values()
        self.filter_changed.emit(self.column_name, checked_values)
        self.close()
