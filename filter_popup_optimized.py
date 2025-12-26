"""Optimized FilterPopup using QListView for 10,000+ values"""

from PyQt6.QtWidgets import QMenu, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QListView, QWidgetAction
from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QSortFilterProxyModel, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from typing import List, Set, Optional, Any
import pandas as pd


class CheckableListModel(QAbstractListModel):
    """Model for checkable list items - much more efficient than creating 10,000 QCheckBox widgets"""
    
    def __init__(self, values: List[str], checked_values: Set[str], parent=None):
        super().__init__(parent)
        self._values = values
        self._checked = set(checked_values)
        self._all_values = set(values)
    
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
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            return True
        
        return False
    
    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
    
    def get_checked_values(self) -> Set[str]:
        """Get all checked values"""
        return self._checked.copy()
    
    def set_all_checked(self, checked: bool):
        """Check or uncheck all items"""
        if checked:
            self._checked = self._all_values.copy()
        else:
            self._checked.clear()
        # Emit dataChanged for all rows
        if self._values:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._values) - 1, 0),
                [Qt.ItemDataRole.CheckStateRole]
            )
    
    def check_visible_items(self, proxy_model: QSortFilterProxyModel):
        """Check all currently visible (filtered) items"""
        visible_values = set()
        for row in range(proxy_model.rowCount()):
            source_index = proxy_model.mapToSource(proxy_model.index(row, 0))
            if source_index.isValid() and source_index.row() < len(self._values):
                visible_values.add(self._values[source_index.row()])
        
        self._checked.update(visible_values)
        
        # Emit dataChanged for visible items
        if visible_values:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._values) - 1, 0),
                [Qt.ItemDataRole.CheckStateRole]
            )


class FilterPopup(QMenu):
    """Optimized popup menu for column filtering using QListView"""

    filter_changed = pyqtSignal(str, set)  # column_name, selected_values
    
    def __init__(self, column_name: str, unique_values: List[Any], 
                 current_selection: Optional[Set[Any]] = None, parent=None):
        super().__init__(parent)
        self.column_name = column_name
        
        # Convert and sort unique values
        self.all_unique_values = sorted([str(v) if not pd.isna(v) else "(Blanks)" 
                                         for v in unique_values])
        
        self.current_selection = current_selection if current_selection else set(self.all_unique_values)
        
        self.init_ui()

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

        # Create the list model and view
        self.model = CheckableListModel(self.all_unique_values, self.current_selection)
        
        # Create proxy model for filtering
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        
        # Create list view
        self.list_view = QListView()
        self.list_view.setModel(self.proxy_model)
        self.list_view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.list_view.setMinimumWidth(200)
        self.list_view.setMaximumWidth(400)
        self.list_view.setMinimumHeight(250)
        self.list_view.setMaximumHeight(400)
        self.list_view.setStyleSheet("""
            QListView {
                font-size: 10px;
                border: 1px solid #ccc;
            }
            QListView::item {
                padding: 2px;
            }
            QListView::item:hover {
                background-color: #e8f0fa;
            }
        """)
        layout.addWidget(self.list_view)

        # Info label
        self.info_label = QLabel(f"Showing all {len(self.all_unique_values):,} values")
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
        
        # Auto-focus the search box when the popup opens
        QTimer.singleShot(0, self.search_box.setFocus)
    
    def filter_list(self, search_text: str):
        """Filter the list based on search text"""
        self.proxy_model.setFilterFixedString(search_text)
        
        # Update info label
        visible_count = self.proxy_model.rowCount()
        if search_text:
            self.info_label.setText(f"Showing {visible_count:,} of {len(self.all_unique_values):,} values")
            # Auto-check matching items when typing
            if visible_count > 0:
                self.model.check_visible_items(self.proxy_model)
        else:
            self.info_label.setText(f"Showing all {len(self.all_unique_values):,} values")
    
    def clear_filter(self):
        """Clear the filter (select all and apply)"""
        self.model.set_all_checked(True)
        self.apply_filter()
    
    def select_all(self):
        """Select all items"""
        self.model.set_all_checked(True)
    
    def deselect_all(self):
        """Deselect all items"""
        self.model.set_all_checked(False)
    
    def apply_filter(self):
        """Apply the filter and emit signal"""
        checked_values = self.model.get_checked_values()
        self.filter_changed.emit(self.column_name, checked_values)
        self.close()
    
    def get_selected_values(self) -> Set[str]:
        """Get currently selected values"""
        return self.model.get_checked_values()
