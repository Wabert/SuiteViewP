"""My Data Screen"""

import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                              QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
                              QLabel, QPushButton, QGroupBox, QFormLayout, QMessageBox,
                              QHeaderView, QMenu, QCheckBox, QLineEdit, QComboBox, QDialog, QTextEdit, QSizePolicy, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QAction

from suiteview.data.repositories import (SavedTableRepository, ConnectionRepository, 
                                         get_metadata_cache_repository, get_query_repository,
                                         get_data_map_repository)
from suiteview.core.schema_discovery import SchemaDiscovery
from suiteview.ui.dialogs.data_map_editor_dialog import DataMapEditorDialog
from suiteview.ui import theme

logger = logging.getLogger(__name__)


class QueryTreeWidget(QTreeWidget):
    """Custom tree widget with drag-and-drop support for organizing queries"""
    
    query_moved = pyqtSignal(int, int)  # query_id, new_folder_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
    
    def dropEvent(self, event):
        """Handle drop event to move queries between folders"""
        # Get the item being dragged
        dragged_item = self.currentItem()
        if not dragged_item:
            return
        
        # Get drop target
        drop_target = self.itemAt(event.position().toPoint())
        if not drop_target:
            return
        
        # Get item types
        dragged_type = dragged_item.data(0, Qt.ItemDataRole.UserRole)
        target_type = drop_target.data(0, Qt.ItemDataRole.UserRole)
        
        # Only allow dropping queries onto folders
        if dragged_type == "db_query" and target_type == "query_folder":
            query_id = dragged_item.data(0, Qt.ItemDataRole.UserRole + 1)
            folder_id = drop_target.data(0, Qt.ItemDataRole.UserRole + 1)
            
            # Emit signal to move query (the handler will reload the tree)
            self.query_moved.emit(query_id, folder_id)
            
            # Don't perform visual move here - the reload in the signal handler will handle it
            # This avoids issues with accessing deleted items after reload
            
            event.accept()
        else:
            event.ignore()


class DataMappingTreeWidget(QTreeWidget):
    """Custom tree widget with drag-and-drop support for organizing data maps"""
    
    data_map_moved = pyqtSignal(int, int)  # data_map_id, new_folder_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Enable drag-drop for organizing data maps
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
    
    def mousePressEvent(self, event):
        """Override to handle single-click expand while preserving drag-drop"""
        # Let the parent handle the click first
        super().mousePressEvent(event)
        
        # Get the item that was clicked
        item = self.itemAt(event.pos())
        if item:
            item_type = item.data(0, Qt.ItemDataRole.UserRole)
            # If it's a folder, toggle expand on single click
            if item_type == "data_map_folder":
                item.setExpanded(not item.isExpanded())
    
    def dropEvent(self, event):
        """Handle drop event to move data maps between folders"""
        
        # LOG FOLDER STATES BEFORE DROP
        print("=" * 60)
        print("BEFORE DROP - Current folder states:")
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item:
                folder_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
                folder_name = item.text(0)
                is_expanded = item.isExpanded()
                print(f"  Folder {folder_id} ({folder_name}): expanded={is_expanded}")
        
        # Get the item being dragged
        dragged_item = self.currentItem()
        if not dragged_item:
            return
        
        # Get drop target
        drop_target = self.itemAt(event.position().toPoint())
        if not drop_target:
            return
        
        # Get item types
        dragged_type = dragged_item.data(0, Qt.ItemDataRole.UserRole)
        target_type = drop_target.data(0, Qt.ItemDataRole.UserRole)
        
        # Only allow dropping data maps onto folders
        if dragged_type == "data_map" and target_type == "data_map_folder":
            data_map_id = dragged_item.data(0, Qt.ItemDataRole.UserRole + 1)
            folder_id = drop_target.data(0, Qt.ItemDataRole.UserRole + 1)
            
            print(f"Dropping data_map {data_map_id} onto folder {folder_id}")
            
            # Emit signal to move data map (the handler will reload the tree)
            self.data_map_moved.emit(data_map_id, folder_id)
            
            # LOG FOLDER STATES AFTER DROP (before reload happens)
            print("AFTER DROP (before reload) - Current folder states:")
            for i in range(self.topLevelItemCount()):
                item = self.topLevelItem(i)
                if item:
                    folder_id_check = item.data(0, Qt.ItemDataRole.UserRole + 1)
                    folder_name_check = item.text(0)
                    is_expanded_check = item.isExpanded()
                    print(f"  Folder {folder_id_check} ({folder_name_check}): expanded={is_expanded_check}")
            print("=" * 60)
            
            # Don't perform visual move here - the reload in the signal handler will handle it
            # This avoids issues with accessing deleted items after reload
            
            event.accept()
        else:
            event.ignore()




class MyDataScreen(QWidget):
    """My Data screen - shows user's curated tables and saved queries"""

    # Signal to request tab switch for editing queries
    edit_query_requested = pyqtSignal(str, int)  # query_type, query_id
    
    # Signal when queries or folders change
    queries_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.saved_table_repo = SavedTableRepository()
        self.conn_repo = ConnectionRepository()
        self.schema_discovery = SchemaDiscovery()
        self.metadata_cache_repo = get_metadata_cache_repository()
        self.query_repo = get_query_repository()
        self.data_map_repo = get_data_map_repository()

        # Track current selection
        self.current_connection_id = None
        self.current_table_name = None
        self.current_schema_name = None

        self.init_ui()
        self.load_my_data()

    def init_ui(self):
        """Initialize the UI"""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create horizontal splitter for four-panel layout
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Allow Data Mapping panel to collapse to 0
        self.main_splitter.setChildrenCollapsible(True)

        # Left Panel - My Data Sources (200px default)
        left_panel = self._create_left_panel()
        left_panel.setMinimumWidth(20)
        self.main_splitter.addWidget(left_panel)

        # Middle Panel - Tables List (300px default)
        middle_panel = self._create_middle_panel()
        middle_panel.setMinimumWidth(20)
        self.main_splitter.addWidget(middle_panel)

        # Right Panel - Schema Details (flex)
        right_panel = self._create_right_panel()
        right_panel.setMinimumWidth(100)
        self.main_splitter.addWidget(right_panel)

        # Far Right Panel - Data Mapping (4th panel, resizable, can collapse to 0)
        self.data_mapping_panel = self._create_far_right_panel()
        self.data_mapping_panel.setMinimumWidth(0)
        self.main_splitter.addWidget(self.data_mapping_panel)

        # Set initial sizes for 4 panels - Data Mapping closed by default
        self.data_mapping_panel_width = 250
        self.main_splitter.setSizes([200, 300, 850, 0])

        layout.addWidget(self.main_splitter, 1)

        # Create floating toggle button (overlay)
        self.data_mapping_toggle = QPushButton("<<", self)
        self.data_mapping_toggle.setCheckable(True)
        self.data_mapping_toggle.setChecked(False)  # Start unchecked (panel closed)
        self.data_mapping_toggle.clicked.connect(self._toggle_data_mapping_panel)
        self.data_mapping_toggle.setFixedSize(24, 38)
        self.data_mapping_toggle.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                            stop:0 #1E3A8A,
                                            stop:1 #2563EB);
                color: #FFD700;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                            stop:0 #2563EB,
                                            stop:1 #3B82F6);
            }
        """)
        self.data_mapping_toggle.raise_()  # Bring to front
        
        # Connect splitter movement to reposition button
        self.main_splitter.splitterMoved.connect(self._update_toggle_position)

    def resizeEvent(self, event):
        """Handle resize to reposition the toggle button"""
        super().resizeEvent(event)
        self._update_toggle_position()

    def showEvent(self, event):
        """Handle show event to position the toggle button"""
        super().showEvent(event)
        self._update_toggle_position()

    def _update_toggle_position(self):
        """Position the toggle button at the left edge of Data Mapping panel"""
        if not hasattr(self, 'data_mapping_toggle'):
            return
        
        sizes = self.main_splitter.sizes()
        # Calculate x position: sum of first 3 panels + splitter handles
        x_pos = sizes[0] + sizes[1] + sizes[2] + 12  # 12 for splitter handles (3 * 4px approx)
        
        # Position button at top, to the left of Data Mapping panel
        self.data_mapping_toggle.move(x_pos - 24, 0)

    def _toggle_data_mapping_panel(self):
        """Toggle visibility of the Data Mapping panel"""
        sizes = self.main_splitter.sizes()
        is_visible = sizes[3] > 0
        
        if is_visible:
            # Store width and collapse
            self.data_mapping_panel_width = sizes[3]
            new_sizes = [sizes[0], sizes[1], sizes[2] + sizes[3], 0]
            self.main_splitter.setSizes(new_sizes)
            self.data_mapping_toggle.setText("<<")
            self.data_mapping_toggle.setChecked(False)
        else:
            # Restore width from content panel
            content_width = sizes[2] - self.data_mapping_panel_width
            if content_width < 100:
                content_width = 100
            new_sizes = [sizes[0], sizes[1], content_width, self.data_mapping_panel_width]
            self.main_splitter.setSizes(new_sizes)
            self.data_mapping_toggle.setText(">>")
            self.data_mapping_toggle.setChecked(True)
        
        # Update button position after toggle
        self._update_toggle_position()

    def _create_left_panel(self) -> QWidget:
        """Create left panel with My Data sources tree"""
        panel = QWidget()
        panel.setObjectName("left_panel")  # For styling
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # --- Databases Section ---
        self.btn_databases = QPushButton("Databases")
        self.btn_databases.setObjectName("section_header")
        self.btn_databases.setCheckable(False) # Not collapsible anymore since it's the only item
        # self.btn_databases.clicked.connect(lambda: self._toggle_section(self.my_data_tree, self.btn_databases))
        panel_layout.addWidget(self.btn_databases)

        self.my_data_tree = QueryTreeWidget()
        self.my_data_tree.setObjectName("sidebar_tree")
        # Remove size policy constraints to allow full expansion
        self.my_data_tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.my_data_tree.query_moved.connect(self._on_query_moved)
        self.my_data_tree.setHeaderHidden(True)
        self.my_data_tree.itemClicked.connect(self.on_data_source_clicked)
        self.my_data_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.my_data_tree.customContextMenuRequested.connect(self.show_datasource_context_menu)
        panel_layout.addWidget(self.my_data_tree)

        # Removed addStretch to prevent artificial cutoff
        # panel_layout.addStretch() 

        return panel

    def _toggle_section(self, widget, button):
        """Toggle visibility of a section"""
        is_visible = widget.isVisible()
        widget.setVisible(not is_visible)
        button.setChecked(not is_visible)
        
    def _filter_sidebar(self, text):
        """Filter items in all sidebar trees"""
        text = text.lower()
        
        # Helper to filter a tree
        def filter_tree(tree):
            has_visible = False
            for i in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(i)
                item_visible = self._filter_tree_item(item, text)
                if item_visible:
                    has_visible = True
            
            # If searching, expand the tree if it has matches
            if text and has_visible and not tree.isVisible():
                 # Find the button for this tree and click it? 
                 # Or just show it. Let's just show it.
                 tree.setVisible(True)
                 # Update button state
                 if tree == self.my_data_tree: self.btn_databases.setChecked(True)
                 elif tree == self.db_queries_tree: self.btn_db_queries.setChecked(True)
                 elif tree == self.data_mapping_tree: self.btn_data_mapping.setChecked(True)

        filter_tree(self.my_data_tree)
        filter_tree(self.db_queries_tree)
        filter_tree(self.data_mapping_tree)

    def _filter_tree_item(self, item, text):
        """Recursive filter for tree items"""
        child_visible = False
        for i in range(item.childCount()):
            if self._filter_tree_item(item.child(i), text):
                child_visible = True
        
        # Check if this item matches
        matches = text in item.text(0).lower()
        
        should_show = matches or child_visible
        item.setHidden(not should_show)
        
        if should_show and text:
            item.setExpanded(True)
            
        return should_show

    def _create_middle_panel(self) -> QWidget:
        """Create middle panel with TABLES title bar and tables list"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # Title bar - using QPushButton to match "Databases" styling
        title_bar = QPushButton("TABLES")
        title_bar.setObjectName("section_header")
        title_bar.setCheckable(False)
        panel_layout.addWidget(title_bar)
        
        # Tables tree widget
        self.tables_tree = QTreeWidget()
        self.tables_tree.setObjectName("sidebar_tree")
        self.tables_tree.setHeaderHidden(True)
        self.tables_tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tables_tree.itemClicked.connect(self.on_table_clicked)
        panel_layout.addWidget(self.tables_tree)
        
        # Hidden widgets for compatibility
        self.tables_search_box = QLineEdit()
        self.tables_search_box.hide()
        self.table_info_label = QLabel("")
        self.table_info_label.hide()
        
        return panel

    def _create_far_right_panel(self) -> QWidget:
        """Create far right panel for Data Mapping"""
        panel = QWidget()
        panel.setObjectName("data_mapping_panel")  # For border styling
        panel.setStyleSheet("""
            QWidget#data_mapping_panel {
                border-left: 2px solid #1E3A8A;
            }
        """)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # Header title
        header = QPushButton("Data Mapping")
        header.setObjectName("section_header")
        # Add context menu for header
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._show_data_mapping_header_context_menu)
        panel_layout.addWidget(header)

        # Data Mapping Tree
        self.data_mapping_tree = DataMappingTreeWidget()
        self.data_mapping_tree.setObjectName("sidebar_tree")
        self.data_mapping_tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.data_mapping_tree.data_map_moved.connect(self._on_data_map_moved)
        self.data_mapping_tree.setHeaderHidden(True)
        
        # Connect signals - itemClicked for single-click expand
        self.data_mapping_tree.itemClicked.connect(self.on_data_map_clicked)
        self.data_mapping_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_mapping_tree.customContextMenuRequested.connect(self._show_data_map_context_menu)
        
        panel_layout.addWidget(self.data_mapping_tree)

        return panel

    def _create_right_panel(self) -> QWidget:
        """Create right panel for schema details"""
        panel = QWidget()
        self.right_panel_layout = QVBoxLayout(panel)
        self.right_panel_layout.setContentsMargins(5, 5, 5, 5)

        # Default content
        self.default_label = QLabel("Select a table to view schema details")
        self.default_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.default_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        self.right_panel_layout.addWidget(self.default_label)

        return panel

    def load_my_data(self):
        """Load all user's saved data into the tree"""
        # Clear the database connections tree
        self.my_data_tree.clear()

        # Clear tables list
        self.tables_tree.clear()
        self.table_info_label.setText("Select a connection to view tables")

        # Load connections directly at root level in the my_data_tree
        self._load_my_connections()

        # Load DB Queries into separate db_queries_tree - REMOVED
        # self._load_db_queries()
        
        # Load Data Maps in separate tree
        self._load_data_maps()
        
        # Enable drag-and-drop for query reorganization
        self.my_data_tree.setDragEnabled(True)
        self.my_data_tree.setAcceptDrops(True)
        self.my_data_tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.my_data_tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        
        # Connect context menu signal
        self.my_data_tree.customContextMenuRequested.connect(self._show_context_menu)

        # TODO: Load XDB Queries (Phase 5)

    def _load_db_queries(self):
        """Load saved DB queries organized by folders
        
        Preserves the exact expanded/collapsed state of folders as set by the user.
        """
        try:
            # Save the complete expanded/collapsed state before clearing
            folder_states = {}  # folder_id -> is_expanded
            has_prior_state = self.db_queries_tree.topLevelItemCount() > 0
            
            for i in range(self.db_queries_tree.topLevelItemCount()):
                item = self.db_queries_tree.topLevelItem(i)
                if item:
                    folder_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
                    if folder_id:
                        folder_states[folder_id] = item.isExpanded()
            
            # Clear existing query items
            self.db_queries_tree.clear()
            
            # Get all folders for DB queries
            folders = self.query_repo.get_all_folders(query_type='DB')
            
            # Get all queries
            queries = self.query_repo.get_all_queries(query_type='DB')
            
            # Create folder items
            folder_items = {}
            for folder in folders:
                folder_item = QTreeWidgetItem()
                folder_item.setText(0, f"📁 {folder['folder_name']}")
                folder_item.setData(0, Qt.ItemDataRole.UserRole, "query_folder")
                folder_item.setData(0, Qt.ItemDataRole.UserRole + 1, folder['folder_id'])
                
                # Don't set expanded state yet - do it after adding children
                
                folder_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled)
                
                self.db_queries_tree.addTopLevelItem(folder_item)
                folder_items[folder['folder_id']] = folder_item
            
            # Add queries to their respective folders
            for query in queries:
                query_item = QTreeWidgetItem()
                query_item.setText(0, query['query_name'])
                query_item.setData(0, Qt.ItemDataRole.UserRole, "db_query")
                query_item.setData(0, Qt.ItemDataRole.UserRole + 1, query['query_id'])
                query_item.setData(0, Qt.ItemDataRole.UserRole + 2, query['query_definition'])
                query_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                
                # Add to appropriate folder
                folder_id = query.get('folder_id')
                if folder_id and folder_id in folder_items:
                    folder_items[folder_id].addChild(query_item)
                else:
                    # If no folder or folder doesn't exist, add to first folder (General)
                    if folder_items:
                        list(folder_items.values())[0].addChild(query_item)
            
            # NOW set the expanded state AFTER all children are added
            for folder in folders:
                folder_id = folder['folder_id']
                if folder_id in folder_items:
                    folder_item = folder_items[folder_id]
                    # Restore the exact state the user had set
                    if has_prior_state and folder_id in folder_states:
                        # Restore saved state exactly as it was
                        folder_item.setExpanded(folder_states[folder_id])
                    else:
                        # New folder or first load - default to COLLAPSED
                        folder_item.setExpanded(False)
            
            logger.info(f"Loaded {len(queries)} DB queries in {len(folders)} folders")
            
        except Exception as e:
            logger.error(f"Error loading DB queries: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load DB queries:\n{str(e)}")

    def _load_data_maps(self):
        """Load data maps organized by folders in separate tree
        
        Preserves the exact expanded/collapsed state of folders as set by the user.
        """
        try:
            # Save the complete expanded/collapsed state before clearing
            # Store both expanded AND collapsed state with a flag
            folder_states = {}  # folder_id -> is_expanded
            has_prior_state = self.data_mapping_tree.topLevelItemCount() > 0
            
            print(f"Data map tree has {self.data_mapping_tree.topLevelItemCount()} items before clear")
            
            for i in range(self.data_mapping_tree.topLevelItemCount()):
                item = self.data_mapping_tree.topLevelItem(i)
                if item:
                    folder_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
                    if folder_id:
                        folder_states[folder_id] = item.isExpanded()
                        print(f"Saved state for folder {folder_id}: expanded={item.isExpanded()}")
            
            # Clear existing data map items
            self.data_mapping_tree.clear()
            
            # Get all folders for data maps
            folders = self.data_map_repo.get_all_folders()
            
            # Get all data maps
            data_maps = self.data_map_repo.get_all_data_maps()
            
            # Create folder items
            folder_items = {}
            for folder in folders:
                folder_item = QTreeWidgetItem()
                folder_item.setText(0, folder['folder_name'])
                folder_item.setData(0, Qt.ItemDataRole.UserRole, "data_map_folder")
                folder_item.setData(0, Qt.ItemDataRole.UserRole + 1, folder['folder_id'])
                
                # Don't set expanded state yet - do it after adding children
                
                folder_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled)
                
                self.data_mapping_tree.addTopLevelItem(folder_item)
                folder_items[folder['folder_id']] = folder_item
            
            # Add data maps to their respective folders
            for data_map in data_maps:
                map_item = QTreeWidgetItem()
                map_item.setText(0, data_map['map_name'])
                map_item.setData(0, Qt.ItemDataRole.UserRole, "data_map")
                map_item.setData(0, Qt.ItemDataRole.UserRole + 1, data_map['data_map_id'])
                map_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                
                # Add to appropriate folder
                folder_id = data_map.get('folder_id')
                if folder_id and folder_id in folder_items:
                    folder_items[folder_id].addChild(map_item)
                else:
                    # If no folder or folder doesn't exist, add to first folder (General)
                    if folder_items:
                        list(folder_items.values())[0].addChild(map_item)
            
            # NOW set the expanded state AFTER all children are added
            for folder in folders:
                folder_id = folder['folder_id']
                if folder_id in folder_items:
                    folder_item = folder_items[folder_id]
                    # Restore the exact state the user had set
                    if has_prior_state and folder_id in folder_states:
                        # Restore saved state exactly as it was
                        folder_item.setExpanded(folder_states[folder_id])
                        print(f"Restored folder {folder_id} to expanded={folder_states[folder_id]}")
                    else:
                        # New folder or first load - default to COLLAPSED
                        folder_item.setExpanded(False)
                        print(f"Set new folder {folder_id} to expanded=False")
            
            # LOG FINAL STATE AFTER RELOAD
            print("AFTER RELOAD - Final folder states:")
            for i in range(self.data_mapping_tree.topLevelItemCount()):
                item = self.data_mapping_tree.topLevelItem(i)
                if item:
                    folder_id_final = item.data(0, Qt.ItemDataRole.UserRole + 1)
                    folder_name_final = item.text(0)
                    is_expanded_final = item.isExpanded()
                    print(f"  Folder {folder_id_final} ({folder_name_final}): expanded={is_expanded_final}")
            
            logger.info(f"Loaded {len(data_maps)} data maps in {len(folders)} folders")
            
        except Exception as e:
            logger.error(f"Error loading data maps: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load data maps:\n{str(e)}")

    def _load_my_connections(self):
        """Load saved connections directly at root level (no parent)"""
        try:
            # Get all saved tables
            saved_tables = self.saved_table_repo.get_all_saved_tables()

            # Group by connection
            connections_dict = {}
            for table in saved_tables:
                conn_id = table['connection_id']
                if conn_id not in connections_dict:
                    # Get connection details
                    conn = self.conn_repo.get_connection(conn_id)
                    if conn:
                        connections_dict[conn_id] = {
                            'connection': conn,
                            'tables': []
                        }

                if conn_id in connections_dict:
                    connections_dict[conn_id]['tables'].append(table)

            # Map connection types to display categories
            type_mapping = {
                'Local ODBC': 'SQL_SERVER',
                'DB2': 'DB2',
                'MS Access': 'ACCESS',
                'ACCESS': 'ACCESS',
                'Excel File': 'EXCEL',
                'EXCEL': 'EXCEL',
                'CSV File': 'CSV',
                'CSV': 'CSV',
                'Fixed Width File': 'FIXED_WIDTH',
                'FIXED_WIDTH': 'FIXED_WIDTH',
                'Mainframe FTP': 'MAINFRAME_FTP',
                'MAINFRAME_FTP': 'MAINFRAME_FTP'
            }

            # Group connections by normalized type (don't merge types)
            type_groups = {}
            for conn_id, data in connections_dict.items():
                conn = data['connection']
                conn_type = conn['connection_type']
                
                # Normalize the connection type
                normalized_type = type_mapping.get(conn_type, conn_type)
                
                # DEBUG: Log connection type
                logger.info(f"DEBUG: Connection '{conn['connection_name']}' has type '{conn_type}' -> normalized to '{normalized_type}'")
                
                # Use the normalized connection type
                if normalized_type not in type_groups:
                    type_groups[normalized_type] = []
                
                type_groups[normalized_type].append((conn_id, conn))

            # DEBUG: Log all type groups
            logger.info(f"DEBUG: Type groups found: {list(type_groups.keys())}")

            # Define the display order (before DB Queries and XDB Queries)
            type_order = ['DB2', 'SQL_SERVER', 'ACCESS', 'EXCEL', 'CSV', 'FIXED_WIDTH', 'MAINFRAME_FTP']
            
            # Add type nodes in the specified order
            insert_position = 0  # Track actual position in tree
            for type_name in type_order:
                if type_name not in type_groups:
                    continue
                    
                # Create type node at the correct position
                type_item = QTreeWidgetItem()
                type_item.setText(0, type_name)
                type_item.setData(0, Qt.ItemDataRole.UserRole, "connection_type")
                type_item.setExpanded(True)  # Expand type nodes by default
                
                # Insert at the actual position (not the type_order index)
                self.my_data_tree.insertTopLevelItem(insert_position, type_item)
                logger.info(f"DEBUG: Inserted '{type_name}' at position {insert_position}")
                insert_position += 1  # Increment for next type
                
                # Add connections under this type
                for conn_id, conn in sorted(type_groups[type_name], key=lambda x: x[1]['connection_name']):
                    conn_item = QTreeWidgetItem(type_item)
                    conn_item.setText(0, conn['connection_name'])
                    conn_item.setData(0, Qt.ItemDataRole.UserRole, "connection")
                    conn_item.setData(0, Qt.ItemDataRole.UserRole + 1, conn_id)
                    conn_item.setExpanded(False)  # Start collapsed

            logger.info(f"Loaded {len(connections_dict)} connections in {len(type_groups)} type groups")

        except Exception as e:
            logger.error(f"Error loading My Connections: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load My Connections:\n{str(e)}")

    def on_data_source_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on data source tree (left panel)"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        logger.info(f"Data source clicked: type={item_type}, text={item.text(0)}")

        if item_type == "connection":
            # Load tables for this connection in middle panel
            conn_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            self.load_tables_for_connection(conn_id)
            
        elif item_type == "connection_type":
            # Auto-expand/collapse on click
            item.setExpanded(not item.isExpanded())

    def on_data_map_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on data mapping tree (far right panel)"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        
        logger.info(f"Data map clicked: type={item_type}, text={item.text(0)}, expanded={item.isExpanded()}")
        
        if item_type == "data_map_folder":
            # Auto-expand/collapse on click (like Databases)
            item.setExpanded(not item.isExpanded())
            logger.info(f"Toggled folder to expanded={item.isExpanded()}")
        elif item_type == "data_map":
            # Show data map editor in right panel
            data_map_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            self._show_data_map_editor_in_panel(data_map_id)

    def load_tables_for_connection(self, connection_id: int):
        """Load saved tables for a connection into middle panel"""
        self.current_connection_id = connection_id
        self.tables_tree.clear()

        try:
            # Get saved tables for this connection
            saved_tables = self.saved_table_repo.get_saved_tables(connection_id)

            if not saved_tables:
                self.table_info_label.setText("No saved tables for this connection")
                return

            # Add tables to middle panel
            for table in saved_tables:
                table_item = QTreeWidgetItem()
                table_name = table['table_name']
                schema_name = table.get('schema_name', '')

                # Display name (show schema if present)
                display_name = f"{schema_name}.{table_name}" if schema_name else table_name
                table_item.setText(0, display_name)
                table_item.setData(0, Qt.ItemDataRole.UserRole, "table")
                table_item.setData(0, Qt.ItemDataRole.UserRole + 1, connection_id)
                table_item.setData(0, Qt.ItemDataRole.UserRole + 2, table_name)
                table_item.setData(0, Qt.ItemDataRole.UserRole + 3, schema_name)

                self.tables_tree.addTopLevelItem(table_item)

            self.table_info_label.setText(f"{len(saved_tables)} table(s)")
            logger.info(f"Loaded {len(saved_tables)} tables for connection {connection_id}")

        except Exception as e:
            logger.error(f"Error loading tables: {e}")
            self.table_info_label.setText(f"Error: {str(e)}")
            QMessageBox.warning(self, "Error", f"Failed to load tables:\n{str(e)}")

    def _filter_tables(self, search_text: str):
        """Filter tables based on search text"""
        search_text = search_text.lower()
        
        for i in range(self.tables_tree.topLevelItemCount()):
            item = self.tables_tree.topLevelItem(i)
            table_name = item.text(0).lower()
            
            # Show/hide based on search text
            if search_text in table_name:
                item.setHidden(False)
            else:
                item.setHidden(True)

    def on_table_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on table in middle panel"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        if item_type == "table":
            conn_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            table_name = item.data(0, Qt.ItemDataRole.UserRole + 2)
            schema_name = item.data(0, Qt.ItemDataRole.UserRole + 3)

            logger.info(f"Table clicked: conn_id={conn_id}, table={table_name}, schema={schema_name}")
            self.show_table_schema(conn_id, table_name, schema_name)

    def show_table_schema(self, connection_id: int, table_name: str, schema_name: str):
        """Display table schema in right panel"""
        try:
            self.current_connection_id = connection_id
            self.current_table_name = table_name
            self.current_schema_name = schema_name

            # Clear right panel
            self._clear_right_panel()

            # Create schema view widget
            schema_widget = QWidget()
            schema_layout = QVBoxLayout(schema_widget)
            schema_layout.setContentsMargins(0, 0, 0, 0)

            # Header with table name
            display_name = f"{schema_name}.{table_name}" if schema_name else table_name
            header = QLabel(f"Table: {display_name}")
            header.setStyleSheet("""
                font-size: 14px;
                font-weight: 800;
                color: #2c3e50;
                padding: 10px 0;
            """)
            schema_layout.addWidget(header)

            # Buttons above the table
            button_layout = QHBoxLayout()
            button_layout.addStretch()

            self.find_unique_btn = QPushButton("Find Unique")
            self.find_unique_btn.setObjectName("gold_button")
            self.find_unique_btn.setMinimumWidth(120)
            self.find_unique_btn.clicked.connect(self.find_unique_values)
            button_layout.addWidget(self.find_unique_btn)

            self.preview_btn = QPushButton("Preview")
            self.preview_btn.setObjectName("gold_button")
            self.preview_btn.setMinimumWidth(120)
            self.preview_btn.clicked.connect(self.preview_table)
            button_layout.addWidget(self.preview_btn)

            schema_layout.addLayout(button_layout)

            # Schema table with proper columns
            self.schema_table = QTableWidget()
            self.schema_table.setColumnCount(9)
            self.schema_table.setHorizontalHeaderLabels([
                "Field", "Type", "Key", "Nullable", "Data Map", "Common", "Unique", "Last Updated", "Unique Values"
            ])
            self.schema_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.schema_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.schema_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

            # Set specific column widths
            self.schema_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Field
            self.schema_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Type
            self.schema_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)  # Key
            self.schema_table.setColumnWidth(2, 50)
            self.schema_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # Nullable
            self.schema_table.setColumnWidth(3, 70)
            self.schema_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)  # Data Map
            self.schema_table.setColumnWidth(4, 100)
            self.schema_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)  # Common checkbox
            self.schema_table.setColumnWidth(5, 55)
            self.schema_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)  # Find Unique checkbox
            self.schema_table.setColumnWidth(6, 60)
            self.schema_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Last Updated
            self.schema_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)  # Unique Values
            

            # Style the table headers with light grey background and reduced height
            self.schema_table.setStyleSheet("""
                QHeaderView::section {
                    background-color: #f0f0f0;
                    color: #000000;
                    padding: 1px 2px;
                    border: 1px solid #d0d0d0;
                    font-weight: normal;
                    font-size: 11px;
                }
                QTableWidget::item {
                    padding: 2px 4px;
                }
                QTableWidget::item:selected {
                    background-color: #E8F0FF;
                    color: #1E3A8A;
                }
                QTableWidget {
                    gridline-color: #d0d0d0;
                    selection-background-color: #E8F0FF;
                    selection-color: #1E3A8A;
                }
            """)
            
            # Enable text wrapping in headers
            self.schema_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.schema_table.horizontalHeader().setSectionsClickable(True)
            
            # Style the row number headers (vertical header)
            vertical_header = self.schema_table.verticalHeader()
            vertical_header.setDefaultSectionSize(20)  # Smaller row height
            vertical_header.setStyleSheet("""
                QHeaderView::section {
                    background-color: #f0f0f0;
                    color: #000000;
                    padding: 2px;
                    border: 1px solid #d0d0d0;
                    font-size: 10px;
                }
            """)

            # Connect double-click event to show unique values dialog
            self.schema_table.cellDoubleClicked.connect(self.on_schema_cell_double_clicked)

            # Get or create metadata entry
            metadata_id = self.metadata_cache_repo.get_or_create_metadata(
                connection_id, table_name, schema_name
            )

            # Get connection type to determine if we should allow type editing
            connection = self.conn_repo.get_connection(connection_id)
            connection_type = connection.get('connection_type') if connection else None
            is_csv = (connection_type == 'CSV')

            # Try to load cached columns first
            cached_columns = self.metadata_cache_repo.get_cached_columns(metadata_id)
            cached_at = None

            if cached_columns:
                logger.info(f"Using cached columns for {display_name}")
                columns = cached_columns
                cached_at = self.metadata_cache_repo.get_metadata_cached_at(metadata_id)
            else:
                # Load column data from database
                logger.info(f"Fetching fresh column data for {display_name}")
                columns = self.schema_discovery.get_columns(connection_id, table_name, schema_name)
                
                # Cache the column metadata
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
                cached_at = self.metadata_cache_repo.get_metadata_cached_at(metadata_id)

            # Load column data
            self.schema_table.setRowCount(len(columns))

            # Store checkboxes for later access
            self.common_checkboxes = []
            self.find_unique_checkboxes = []
            self.type_comboboxes = []  # Store type dropdowns for CSV files

            for row, col_data in enumerate(columns):
                # Handle both cache format and direct query format
                col_name = col_data.get('name') or col_data.get('column_name')
                col_type = col_data.get('type') or col_data.get('data_type')
                is_pk = col_data.get('primary_key') or col_data.get('is_primary_key', False)
                is_nullable = col_data.get('nullable', True)
                if 'is_nullable' in col_data:
                    is_nullable = col_data['is_nullable']
                is_common = col_data.get('is_common', False)

                # Field (Column Name)
                self.schema_table.setItem(row, 0, QTableWidgetItem(col_name))

                # Type (Data Type) - For CSV files, use QComboBox to allow changing type
                if is_csv:
                    type_combo = QComboBox()
                    type_combo.addItems([
                        "TEXT",
                        "INTEGER", 
                        "FLOAT",
                        "DECIMAL",
                        "DATE",
                        "DATETIME",
                        "BOOLEAN"
                    ])
                    
                    # Apply compact styling to the combobox - fill the entire cell
                    type_combo.setStyleSheet("""
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
                    
                    # Set current type
                    current_type = col_type.upper()
                    if current_type in ["TEXT", "INTEGER", "FLOAT", "DECIMAL", "DATE", "DATETIME", "BOOLEAN"]:
                        type_combo.setCurrentText(current_type)
                    else:
                        type_combo.setCurrentText("TEXT")
                    
                    # Connect change handler
                    type_combo.currentTextChanged.connect(
                        lambda new_type, r=row, c=col_name: self.on_type_changed(r, c, new_type)
                    )
                    
                    # Add directly to cell without wrapper widget
                    self.schema_table.setCellWidget(row, 1, type_combo)
                    self.type_comboboxes.append(type_combo)
                else:
                    # Regular database - just display type as text
                    self.schema_table.setItem(row, 1, QTableWidgetItem(col_type))
                    self.type_comboboxes.append(None)

                # Key (PK, FK, etc.)
                key_value = ""
                if is_pk:
                    key_value = "PK"
                # TODO: Add FK detection when available
                self.schema_table.setItem(row, 2, QTableWidgetItem(key_value))

                # Nullable
                nullable = "Yes" if is_nullable else "No"
                self.schema_table.setItem(row, 3, QTableWidgetItem(nullable))

                # Common (QCheckBox widget) - Column 5 - Professional styled checkbox
                common_checkbox_widget = QWidget()
                common_checkbox_layout = QHBoxLayout(common_checkbox_widget)
                common_checkbox_layout.setContentsMargins(0, 0, 0, 0)
                common_checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                common_checkbox = QCheckBox()
                common_checkbox.setStyleSheet("""
                    QCheckBox::indicator {
                        width: 14px;
                        height: 14px;
                        border: 1px solid #6B8AB8;
                        border-radius: 2px;
                        background-color: #FFFFFF;
                    }
                    QCheckBox::indicator:hover {
                        border: 1px solid #2563EB;
                        background-color: #E8F4FF;
                    }
                    QCheckBox::indicator:checked {
                        background-color: #2563EB;
                        border: 1px solid #1E3A8A;
                    }
                """)
                common_checkbox.setChecked(is_common)
                common_checkbox.stateChanged.connect(
                    lambda state, r=row, c=col_name: self.on_common_checkbox_changed(r, c, state)
                )
                common_checkbox_layout.addWidget(common_checkbox)

                self.schema_table.setCellWidget(row, 5, common_checkbox_widget)
                self.common_checkboxes.append(common_checkbox)

                # Find Unique (QCheckBox widget) - Column 6 - Professional styled checkbox
                find_unique_checkbox_widget = QWidget()
                find_unique_checkbox_layout = QHBoxLayout(find_unique_checkbox_widget)
                find_unique_checkbox_layout.setContentsMargins(0, 0, 0, 0)
                find_unique_checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                find_unique_checkbox = QCheckBox()
                find_unique_checkbox.setStyleSheet("""
                    QCheckBox::indicator {
                        width: 14px;
                        height: 14px;
                        border: 1px solid #6B8AB8;
                        border-radius: 2px;
                        background-color: #FFFFFF;
                    }
                    QCheckBox::indicator:hover {
                        border: 1px solid #2563EB;
                        background-color: #E8F4FF;
                    }
                    QCheckBox::indicator:checked {
                        background-color: #2563EB;
                        border: 1px solid #1E3A8A;
                    }
                """)
                find_unique_checkbox_layout.addWidget(find_unique_checkbox)

                self.schema_table.setCellWidget(row, 6, find_unique_checkbox_widget)
                self.find_unique_checkboxes.append(find_unique_checkbox)

                # Check for cached unique values
                cached_unique = self.metadata_cache_repo.get_cached_unique_values(metadata_id, col_name)
                
                if cached_unique:
                    # Last Updated (timestamp from cache) - Column 7
                    timestamp = cached_unique['cached_at']
                    if timestamp:
                        # Format timestamp nicely
                        from datetime import datetime
                        dt_obj = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        timestamp = dt_obj.strftime("%m/%d/%Y %H:%M")
                    self.schema_table.setItem(row, 7, QTableWidgetItem(timestamp or ""))

                    # Unique Values (display cached unique values) - Column 8
                    unique_values = cached_unique['unique_values']
                    value_count = cached_unique['value_count']
                    
                    if value_count == 0:
                        display_text = "(no values)"
                    elif value_count <= 10:
                        display_text = ", ".join(str(v) for v in unique_values)
                    else:
                        first_ten = ", ".join(str(v) for v in unique_values[:10])
                        display_text = f"{first_ten}... ({value_count} total)"
                    
                    unique_values_item = QTableWidgetItem(display_text)
                    unique_values_item.setData(Qt.ItemDataRole.UserRole, unique_values)
                    self.schema_table.setItem(row, 8, unique_values_item)
                else:
                    # No cached data
                    self.schema_table.setItem(row, 7, QTableWidgetItem(""))
                    self.schema_table.setItem(row, 8, QTableWidgetItem(""))
                
                # Data Map (Column 4) - Create dropdown with assigned map or option to create
                self._create_data_map_widget(row, col_name, connection_id, table_name, schema_name)

            schema_layout.addWidget(self.schema_table)

            # Add to right panel
            self.right_panel_layout.addWidget(schema_widget)

            logger.info(f"Displayed schema for {display_name} with {len(columns)} columns")

        except Exception as e:
            logger.error(f"Error loading schema: {e}")
            error_label = QLabel(f"Error loading schema: {str(e)}")
            error_label.setStyleSheet("color: #e74c3c; padding: 20px;")
            self.right_panel_layout.addWidget(error_label)

    def _create_data_map_widget(self, row: int, column_name: str, connection_id: int, 
                                table_name: str, schema_name: str):
        """Create a button with cascading menu for data map assignment"""
        try:
            # Check if field already has a data map assigned
            assigned_map_id = self.data_map_repo.get_field_data_map(
                connection_id, table_name, column_name, schema_name
            )
            
            # Get all folders and data maps
            all_folders = self.data_map_repo.get_all_folders()
            all_maps = self.data_map_repo.get_all_data_maps()
            
            # Organize maps by folder
            maps_by_folder = {}
            for data_map in all_maps:
                folder_id = data_map.get('folder_id')
                if folder_id not in maps_by_folder:
                    maps_by_folder[folder_id] = []
                maps_by_folder[folder_id].append(data_map)
            
            # Find the assigned map name if any
            assigned_map_name = "(None)"
            for data_map in all_maps:
                if assigned_map_id and data_map['data_map_id'] == assigned_map_id:
                    assigned_map_name = data_map['map_name']
                    break
            
            # Create button - fills the entire cell
            button = QPushButton(assigned_map_name)
            button.setStyleSheet("""
                QPushButton {
                    border: none;
                    border-radius: 0px;
                    padding: 0px 2px;
                    margin: 0px;
                    background: #E8F0FF;
                    font-size: 10px;
                    text-align: left;
                    color: #1E3A8A;
                    font-weight: normal;
                }
                QPushButton:hover {
                    background: #D0E0F5;
                }
                QPushButton::menu-indicator {
                    width: 10px;
                    subcontrol-position: right center;
                    subcontrol-origin: padding;
                    right: 2px;
                }
            """)
            
            # Create menu
            menu = QMenu(button)
            
            # Add "None" option
            none_action = menu.addAction("(None)")
            none_action.triggered.connect(
                lambda: self._assign_data_map(row, column_name, connection_id, table_name, schema_name, None, button)
            )
            
            menu.addSeparator()
            
            # Add folders with cascading menus
            for folder in all_folders:
                folder_id = folder['folder_id']
                folder_name = folder['folder_name']
                
                # Get maps in this folder
                folder_maps = maps_by_folder.get(folder_id, [])
                
                if folder_maps:
                    # Create submenu for folder
                    folder_menu = menu.addMenu(f"📁 {folder_name}")
                    
                    # Add each map in the folder
                    for data_map in folder_maps:
                        map_action = folder_menu.addAction(data_map['map_name'])
                        map_id = data_map['data_map_id']
                        map_action.triggered.connect(
                            lambda checked, mid=map_id, mname=data_map['map_name']: 
                            self._assign_data_map(row, column_name, connection_id, table_name, schema_name, mid, button, mname)
                        )
            
            menu.addSeparator()
            
            # Add "Create New" options
            create_new_action = menu.addAction("➕ Create New...")
            create_new_action.triggered.connect(
                lambda: self._create_data_map_for_field(row, column_name, connection_id, table_name, schema_name, button)
            )
            
            create_from_unique_action = menu.addAction("➕ Create from Unique Values...")
            create_from_unique_action.triggered.connect(
                lambda: self._create_data_map_from_unique(row, column_name, connection_id, table_name, schema_name, button)
            )
            
            button.setMenu(menu)
            self.schema_table.setCellWidget(row, 4, button)
            
        except Exception as e:
            logger.error(f"Error creating data map widget for {column_name}: {e}")
            # Create a simple fallback widget
            fallback_label = QLabel("(None)")
            self.schema_table.setCellWidget(row, 4, fallback_label)

    def _assign_data_map(self, row: int, column_name: str, connection_id: int,
                         table_name: str, schema_name: str, data_map_id: int, 
                         button: QPushButton, map_name: str = None):
        """Assign or remove a data map from a field"""
        try:
            if data_map_id is None:
                # Remove assignment
                self.data_map_repo.remove_field_data_map(connection_id, table_name, column_name, schema_name)
                button.setText("(None)")
                logger.info(f"Removed data map from {table_name}.{column_name}")
            else:
                # Assign the selected data map
                self.data_map_repo.assign_data_map_to_field(
                    connection_id, table_name, column_name, data_map_id, schema_name
                )
                button.setText(map_name or f"Map {data_map_id}")
                logger.info(f"Assigned data map {data_map_id} to {table_name}.{column_name}")
        except Exception as e:
            logger.error(f"Error assigning/removing data map: {e}")
            QMessageBox.critical(self, "Error", f"Failed to update data map:\n{str(e)}")

    def _on_data_map_changed(self, row: int, column_name: str, connection_id: int,
                            table_name: str, schema_name: str, combo: QComboBox):
        """Handle data map selection change"""
        selected_data = combo.currentData()
        
        if selected_data == "create_new":
            # Create new data map
            self._create_data_map_for_field(row, column_name, connection_id, table_name, schema_name, combo)
        elif selected_data == "create_from_unique":
            # Create from unique values
            self._create_data_map_from_unique(row, column_name, connection_id, table_name, schema_name, combo)
        elif selected_data is None:
            # Remove assignment
            try:
                self.data_map_repo.remove_field_data_map(connection_id, table_name, column_name, schema_name)
                logger.info(f"Removed data map from {table_name}.{column_name}")
            except Exception as e:
                logger.error(f"Error removing data map assignment: {e}")
                QMessageBox.critical(self, "Error", f"Failed to remove data map:\n{str(e)}")
        else:
            # Assign the selected data map
            try:
                self.data_map_repo.assign_data_map_to_field(
                    connection_id, table_name, column_name, selected_data, schema_name
                )
                logger.info(f"Assigned data map {selected_data} to {table_name}.{column_name}")
            except Exception as e:
                logger.error(f"Error assigning data map: {e}")
                QMessageBox.critical(self, "Error", f"Failed to assign data map:\n{str(e)}")

    def _create_data_map_for_field(self, row: int, column_name: str, connection_id: int,
                                   table_name: str, schema_name: str, button: QPushButton):
        """Create a new data map for a field"""
        from PyQt6.QtWidgets import QInputDialog
        
        # Suggest a name based on table and column
        suggested_name = f"{table_name}_{column_name}_map"
        map_name, ok = QInputDialog.getText(
            self,
            "Create Data Map",
            "Enter name for the new data map:",
            text=suggested_name
        )
        
        if ok and map_name.strip():
            # Open the data map editor dialog
            dialog = DataMapEditorDialog(self, map_name=map_name.strip())
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # Get the created map ID
                created_map = self.data_map_repo.get_data_map_by_name(map_name.strip())
                if created_map:
                    # Assign it to the field
                    self.data_map_repo.assign_data_map_to_field(
                        connection_id, table_name, column_name, 
                        created_map['data_map_id'], schema_name
                    )
                    
                    # Update button text and menu
                    button.setText(map_name.strip())
                    
                    # Reload the table schema to refresh the dropdown
                    self.load_table_schema(connection_id, table_name, schema_name)
                    logger.info(f"Created and assigned data map '{map_name}' to {table_name}.{column_name}")

    def _create_data_map_from_unique(self, row: int, column_name: str, connection_id: int,
                                     table_name: str, schema_name: str, button: QPushButton):
        """Create a data map from unique values in the field"""
        from PyQt6.QtWidgets import QInputDialog
        
        try:
            # Check if we have cached unique values
            metadata_id = self.metadata_cache_repo.get_or_create_metadata(
                connection_id, table_name, schema_name
            )
            
            cached_unique = self.metadata_cache_repo.get_cached_unique_values(metadata_id, column_name)
            
            if cached_unique and cached_unique['unique_values']:
                unique_values = cached_unique['unique_values']
            else:
                # Query unique values from database
                QMessageBox.information(
                    self,
                    "Finding Unique Values",
                    "Finding unique values for this field. This may take a moment..."
                )
                
                unique_values = self.schema_discovery.get_unique_values(
                    connection_id, table_name, column_name, schema_name
                )
                
                # Cache them
                self.metadata_cache_repo.cache_unique_values(metadata_id, column_name, unique_values)
            
            # Suggest a name
            suggested_name = f"{table_name}_{column_name}_map"
            map_name, ok = QInputDialog.getText(
                self,
                "Create Data Map from Unique Values",
                f"Found {len(unique_values)} unique values.\nEnter name for the data map:",
                text=suggested_name
            )
            
            if ok and map_name.strip():
                # Open the data map editor dialog with pre-populated keys
                dialog = DataMapEditorDialog(
                    self, 
                    map_name=map_name.strip(),
                    pre_populate_keys=[str(v) for v in unique_values]
                )
                
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    # Get the created map ID
                    created_map = self.data_map_repo.get_data_map_by_name(map_name.strip())
                    if created_map:
                        # Assign it to the field
                        self.data_map_repo.assign_data_map_to_field(
                            connection_id, table_name, column_name,
                            created_map['data_map_id'], schema_name
                        )
                        
                        # Update button text
                        button.setText(map_name.strip())
                        
                        # Reload the table schema to refresh the dropdown
                        self.load_table_schema(connection_id, table_name, schema_name)
                        logger.info(f"Created and assigned data map '{map_name}' from unique values")
                
        except Exception as e:
            logger.error(f"Error creating data map from unique values: {e}")
            QMessageBox.critical(self, "Error", f"Failed to create data map:\n{str(e)}")

    def find_unique_values(self):
        """Find unique values for checked columns"""
        if not hasattr(self, 'schema_table') or not hasattr(self, 'find_unique_checkboxes'):
            return

        # Get checked columns using stored checkboxes
        checked_columns = []
        for row, checkbox in enumerate(self.find_unique_checkboxes):
            if checkbox.isChecked():
                col_name_item = self.schema_table.item(row, 0)  # Field name is in column 0
                if col_name_item:
                    checked_columns.append(col_name_item.text())

        if not checked_columns:
            QMessageBox.information(self, "No Columns Selected",
                                   "Please check at least one column to find unique values.")
            return

        # Get or create metadata entry
        metadata_id = self.metadata_cache_repo.get_or_create_metadata(
            self.current_connection_id,
            self.current_table_name,
            self.current_schema_name
        )

        # Execute queries to find unique values
        try:
            import datetime
            from datetime import datetime as dt

            for col_name in checked_columns:
                # Find the row for this column
                row_index = None
                for row in range(self.schema_table.rowCount()):
                    if self.schema_table.item(row, 0).text() == col_name:
                        row_index = row
                        break

                if row_index is None:
                    continue

                # Query unique values for this column
                logger.info(f"Finding unique values for {col_name}")
                unique_values = self.schema_discovery.get_unique_values(
                    self.current_connection_id,
                    self.current_table_name,
                    col_name,
                    self.current_schema_name
                )

                # Cache the unique values
                self.metadata_cache_repo.cache_unique_values(metadata_id, col_name, unique_values)
                
                # Get the cached timestamp
                cached_unique = self.metadata_cache_repo.get_cached_unique_values(metadata_id, col_name)
                timestamp = cached_unique['cached_at'] if cached_unique else dt.now().isoformat()
                
                # Format timestamp nicely
                dt_obj = dt.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_timestamp = dt_obj.strftime("%m/%d/%Y %H:%M")

                # Update the table with results (Column 7 is Last Updated)
                last_updated_item = self.schema_table.item(row_index, 7)
                if last_updated_item:
                    last_updated_item.setText(formatted_timestamp)
                else:
                    self.schema_table.setItem(row_index, 7, QTableWidgetItem(formatted_timestamp))

                # Format unique values for display
                value_count = len(unique_values)
                if value_count == 0:
                    display_text = "(no values)"
                elif value_count <= 10:
                    # Show all values if 10 or fewer
                    display_text = ", ".join(str(v) for v in unique_values)
                else:
                    # Show first 10 + count if more than 10
                    first_ten = ", ".join(str(v) for v in unique_values[:10])
                    display_text = f"{first_ten}... ({value_count} total)"

                # Update Column 8 (Unique Values)
                unique_values_item = self.schema_table.item(row_index, 8)
                if unique_values_item:
                    unique_values_item.setText(display_text)
                else:
                    unique_values_item = QTableWidgetItem(display_text)
                    self.schema_table.setItem(row_index, 8, unique_values_item)
                
                # Store the full unique values list for later access (for double-click dialog)
                unique_values_item = self.schema_table.item(row_index, 8)
                unique_values_item.setData(Qt.ItemDataRole.UserRole, unique_values)

                # Uncheck the "Find Unique" checkbox for this column
                self.find_unique_checkboxes[row_index].setChecked(False)

                logger.info(f"Found and cached {value_count} unique values for {col_name}")

            QMessageBox.information(self, "Find Unique Values",
                                   f"Successfully found unique values for {len(checked_columns)} column(s)")

        except Exception as e:
            logger.error(f"Error finding unique values: {e}")
            QMessageBox.critical(self, "Error", f"Failed to find unique values:\n{str(e)}")

    def on_schema_cell_double_clicked(self, row: int, column: int):
        """Handle double-click on schema table cells"""
        # Only handle double-clicks on the "Unique Values" column (column 8)
        if column != 8:
            return
        
        # Get the unique values stored in the cell
        unique_values_item = self.schema_table.item(row, 8)
        if not unique_values_item:
            return
        
        # Get the full list of unique values from UserRole data
        unique_values = unique_values_item.data(Qt.ItemDataRole.UserRole)
        if not unique_values:
            QMessageBox.information(self, "No Data", 
                                   "No unique values have been found for this column yet.\n"
                                   "Check the 'Find Unique' box and click 'Find Unique Values' to populate.")
            return
        
        # Get the column name
        col_name = self.schema_table.item(row, 0).text()
        
        # Get the field type from column 1
        field_type_item = self.schema_table.item(row, 1)
        field_type = field_type_item.text() if field_type_item else "string"
        
        # Show dialog with all unique values
        self.show_unique_values_dialog(col_name, unique_values, row, field_type)

    def show_unique_values_dialog(self, column_name: str, unique_values: list, row: int = None, field_type: str = "string"):
        """Show a dialog displaying all unique values in a grid with data map options"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Unique Values - {column_name}")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(500)
        
        layout = QVBoxLayout(dialog)
        
        # Header label
        header = QLabel(f"Column: {column_name}")
        header.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
        layout.addWidget(header)
        
        # Count label
        count_label = QLabel(f"Total unique values: {len(unique_values)}")
        count_label.setStyleSheet("padding: 0 10px 10px 10px;")
        layout.addWidget(count_label)
        
        # Table with unique values - single column, no "#"
        table = QTableWidget()
        table.setColumnCount(1)
        table.setHorizontalHeaderLabels(["Value"])
        table.setRowCount(len(unique_values))
        
        # Populate table
        for i, value in enumerate(unique_values):
            # Value (convert to string, handle None)
            display_value = str(value) if value is not None else "(NULL)"
            table.setItem(i, 0, QTableWidgetItem(display_value))
        
        # Set column to stretch
        table.horizontalHeader().setStretchLastSection(True)
        
        # Make read-only
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        # Style the table headers with light grey background and reduced height
        table.setStyleSheet("""
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #000000;
                padding: 2px 4px;
                border: 1px solid #d0d0d0;
                font-weight: normal;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 2px 4px;
            }
            QTableWidget {
                gridline-color: #d0d0d0;
            }
        """)
        
        # Style the row number headers (vertical header)
        vertical_header = table.verticalHeader()
        vertical_header.setDefaultSectionSize(20)  # Smaller row height
        vertical_header.setStyleSheet("""
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #000000;
                padding: 2px;
                border: 1px solid #d0d0d0;
                font-size: 10px;
            }
        """)
        
        layout.addWidget(table)
        
        # Check if field is already mapped to a data map
        assigned_map_id = None
        assigned_map_name = None
        if self.current_connection_id and self.current_table_name:
            assigned_map_id = self.data_map_repo.get_field_data_map(
                self.current_connection_id, 
                self.current_table_name, 
                column_name, 
                self.current_schema_name
            )
            if assigned_map_id:
                data_map = self.data_map_repo.get_data_map(assigned_map_id)
                if data_map:
                    assigned_map_name = data_map['map_name']
        
        # Add buttons
        from PyQt6.QtWidgets import QPushButton, QHBoxLayout
        button_layout = QHBoxLayout()
        
        # Set Data Map button - always visible
        set_map_btn = QPushButton("📋 Set Data Map")
        set_map_btn.setStyleSheet("""
            QPushButton {
                background-color: #1E3A8A;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #2E4A9A;
            }
            QPushButton:pressed {
                background-color: #0E2A7A;
            }
        """)
        set_map_btn.clicked.connect(lambda: self._show_set_data_map_dialog(column_name, dialog))
        button_layout.addWidget(set_map_btn)
        
        # Create Data Map OR Show Data Map button
        if assigned_map_id and assigned_map_name:
            # Field is mapped - show "Show Data Map" button
            show_map_btn = QPushButton(f"👁️ Show Data Map ({assigned_map_name})")
            show_map_btn.setStyleSheet("""
                QPushButton {
                    background-color: #059669;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 12px;
                    min-width: 140px;
                }
                QPushButton:hover {
                    background-color: #06B67A;
                }
                QPushButton:pressed {
                    background-color: #048559;
                }
            """)
            show_map_btn.clicked.connect(lambda: self._show_data_map_from_unique_dialog(assigned_map_id, dialog))
            button_layout.addWidget(show_map_btn)
        else:
            # Field is not mapped - show "Create Data Map" button
            create_map_btn = QPushButton("➕ Create Data Map")
            create_map_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FFD700;
                    color: #1E3A8A;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-weight: bold;
                    font-size: 12px;
                    min-width: 140px;
                }
                QPushButton:hover {
                    background-color: #FFE033;
                }
                QPushButton:pressed {
                    background-color: #E6C200;
                }
            """)
            create_map_btn.clicked.connect(lambda: self._show_create_data_map_dialog(column_name, unique_values, field_type, row, dialog))
            button_layout.addWidget(create_map_btn)
        
        button_layout.addStretch()
        
        # Close button - more distinct styling
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #6B7280;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #7B8290;
            }
            QPushButton:pressed {
                background-color: #5B6270;
            }
        """)
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        dialog.exec()

    def _show_set_data_map_dialog(self, column_name: str, parent_dialog: QDialog):
        """Show dialog to select and assign a data map to the field"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QPushButton, QHBoxLayout
        
        dialog = QDialog(parent_dialog)
        dialog.setWindowTitle(f"Set Data Map - {column_name}")
        dialog.setMinimumWidth(350)
        dialog.setMinimumHeight(400)
        
        layout = QVBoxLayout(dialog)
        
        # Header
        header = QLabel(f"Select a data map for: {column_name}")
        header.setStyleSheet("font-weight: bold; font-size: 13px; padding: 10px;")
        layout.addWidget(header)
        
        # Tree widget showing folders and data maps
        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #1E3A8A;
                color: white;
            }
        """)
        
        # Add "None" option at top
        none_item = QTreeWidgetItem(tree)
        none_item.setText(0, "(None) - Remove assignment")
        none_item.setData(0, Qt.ItemDataRole.UserRole, None)
        
        # Load folders and data maps
        all_folders = self.data_map_repo.get_all_folders()
        all_maps = self.data_map_repo.get_all_data_maps()
        
        # Organize maps by folder
        maps_by_folder = {}
        for data_map in all_maps:
            folder_id = data_map.get('folder_id')
            if folder_id not in maps_by_folder:
                maps_by_folder[folder_id] = []
            maps_by_folder[folder_id].append(data_map)
        
        # Add folders with their maps
        for folder in all_folders:
            folder_id = folder['folder_id']
            folder_maps = maps_by_folder.get(folder_id, [])
            
            if folder_maps:
                folder_item = QTreeWidgetItem(tree)
                folder_item.setText(0, f"📁 {folder['folder_name']}")
                folder_item.setData(0, Qt.ItemDataRole.UserRole, "folder")
                folder_item.setExpanded(True)
                
                for data_map in folder_maps:
                    map_item = QTreeWidgetItem(folder_item)
                    map_item.setText(0, data_map['map_name'])
                    map_item.setData(0, Qt.ItemDataRole.UserRole, data_map['data_map_id'])
        
        layout.addWidget(tree)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        assign_btn = QPushButton("Assign")
        assign_btn.setStyleSheet("""
            QPushButton {
                background-color: #1E3A8A;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2E4A9A; }
        """)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6B7280;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #7B8290; }
        """)
        
        def do_assign():
            selected = tree.currentItem()
            if not selected:
                return
            
            data_map_id = selected.data(0, Qt.ItemDataRole.UserRole)
            if data_map_id == "folder":
                return  # Can't select a folder
            
            try:
                if data_map_id is None:
                    # Remove assignment (set to None)
                    self.data_map_repo.assign_data_map_to_field(
                        self.current_connection_id,
                        self.current_table_name,
                        column_name,
                        self.current_schema_name,
                        None
                    )
                    logger.info(f"Removed data map assignment from {column_name}")
                else:
                    # Assign selected data map
                    self.data_map_repo.assign_data_map_to_field(
                        self.current_connection_id,
                        self.current_table_name,
                        column_name,
                        self.current_schema_name,
                        data_map_id
                    )
                    logger.info(f"Assigned data map {data_map_id} to {column_name}")
                
                # Refresh the schema table to show updated assignment
                self._refresh_data_map_button(column_name, data_map_id)
                
                dialog.accept()
                parent_dialog.accept()  # Close the unique values dialog too
            except Exception as e:
                logger.error(f"Error assigning data map: {e}")
                QMessageBox.critical(dialog, "Error", f"Failed to assign data map:\n{str(e)}")
        
        assign_btn.clicked.connect(do_assign)
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(assign_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        dialog.exec()

    def _refresh_data_map_button(self, column_name: str, data_map_id: int = None):
        """Refresh the data map button in schema table for a specific column"""
        # Find the row for this column
        for row in range(self.schema_table.rowCount()):
            field_item = self.schema_table.item(row, 0)
            if field_item and field_item.text() == column_name:
                # Get the button widget in column 4
                widget = self.schema_table.cellWidget(row, 4)
                if widget and isinstance(widget, QPushButton):
                    if data_map_id:
                        data_map = self.data_map_repo.get_data_map(data_map_id)
                        widget.setText(data_map['map_name'] if data_map else "(None)")
                    else:
                        widget.setText("(None)")
                break

    def _show_data_map_from_unique_dialog(self, data_map_id: int, parent_dialog: QDialog):
        """Show the data map editor in the right panel and close the unique values dialog"""
        parent_dialog.accept()
        self._show_data_map_editor_in_panel(data_map_id)

    def _show_create_data_map_dialog(self, column_name: str, unique_values: list, field_type: str, row: int, parent_dialog: QDialog):
        """Show dialog to create a new data map pre-populated with unique values"""
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                                     QLineEdit, QComboBox, QTextEdit, QTableWidget, 
                                     QTableWidgetItem, QPushButton, QHeaderView)
        
        dialog = QDialog(parent_dialog)
        dialog.setWindowTitle(f"Create Data Map from {column_name}")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(550)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Title
        title = QLabel(f"Create Data Map: {column_name}")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1E3A8A;")
        layout.addWidget(title)
        
        # Map name
        name_layout = QHBoxLayout()
        name_label = QLabel("Map Name:")
        name_label.setStyleSheet("font-weight: bold;")
        name_layout.addWidget(name_label)
        name_input = QLineEdit()
        name_input.setText(column_name)  # Default to column name
        name_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                padding: 6px;
                background: #E8F0FF;
            }
            QLineEdit:focus {
                border: 2px solid #1E3A8A;
            }
        """)
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)
        
        # Data types
        types_layout = QHBoxLayout()
        
        key_type_label = QLabel("Key Data Type:")
        key_type_label.setStyleSheet("font-weight: bold;")
        types_layout.addWidget(key_type_label)
        
        key_type_combo = QComboBox()
        key_type_combo.addItems(['string', 'integer', 'decimal', 'date', 'boolean'])
        # Try to infer key type from field type
        inferred_type = self._infer_data_type(field_type)
        key_type_combo.setCurrentText(inferred_type)
        key_type_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                padding: 4px 8px;
                background: #E8F0FF;
            }
        """)
        types_layout.addWidget(key_type_combo)
        
        types_layout.addSpacing(30)
        
        value_type_label = QLabel("Value Data Type:")
        value_type_label.setStyleSheet("font-weight: bold;")
        types_layout.addWidget(value_type_label)
        
        value_type_combo = QComboBox()
        value_type_combo.addItems(['string', 'integer', 'decimal', 'date', 'boolean'])
        value_type_combo.setCurrentText('string')  # Default to string
        value_type_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                padding: 4px 8px;
                background: #E8F0FF;
            }
        """)
        types_layout.addWidget(value_type_combo)
        types_layout.addStretch()
        layout.addLayout(types_layout)
        
        # Notes
        notes_label = QLabel("Notes / Description:")
        notes_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(notes_label)
        
        notes_input = QTextEdit()
        notes_input.setPlaceholderText("Enter notes or description...")
        notes_input.setMaximumHeight(60)
        notes_input.setStyleSheet("""
            QTextEdit {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        layout.addWidget(notes_input)
        
        # Key-Value table label
        kv_label = QLabel("Key-Value Mappings:")
        kv_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(kv_label)
        
        # Buttons above table
        table_btn_layout = QHBoxLayout()
        
        add_row_btn = QPushButton("➕ Add Row")
        add_row_btn.setStyleSheet("""
            QPushButton {
                background-color: #059669;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #06B67A; }
        """)
        table_btn_layout.addWidget(add_row_btn)
        
        delete_btn = QPushButton("🗑️ Delete Selected")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #DC2626;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #EF4444; }
        """)
        table_btn_layout.addWidget(delete_btn)
        table_btn_layout.addStretch()
        layout.addLayout(table_btn_layout)
        
        # Table with Key and Value columns
        entries_table = QTableWidget()
        entries_table.setColumnCount(3)
        entries_table.setHorizontalHeaderLabels(['Key', 'Value', 'Comment'])
        entries_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        entries_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        
        # Allow user to resize columns - Interactive mode
        header = entries_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        
        # Set initial column widths
        entries_table.setColumnWidth(0, 80)
        entries_table.setColumnWidth(1, 200)
        entries_table.setColumnWidth(2, 150)
        
        # Enable word wrap for cells
        entries_table.setWordWrap(True)
        
        # Style the table - clean cells with NO padding, subtle selection
        entries_table.setStyleSheet("""
            QHeaderView::section {
                background-color: #1E3A8A;
                color: white;
                padding: 6px;
                border: 1px solid #0E2A7A;
                font-weight: bold;
            }
            QTableWidget {
                gridline-color: #d0d0d0;
                selection-background-color: #E0E7F1;
                selection-color: #000000;
            }
            QTableWidget::item {
                padding: 0px;
                margin: 0px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #E0E7F1;
                color: #000000;
            }
            QLineEdit {
                padding: 0px;
                margin: 0px;
                border: none;
                background: white;
            }
        """)
        
        # Pre-populate with unique values
        entries_table.setRowCount(len(unique_values))
        for i, value in enumerate(unique_values):
            # Key (from unique value)
            key_text = str(value) if value is not None else ""
            key_item = QTableWidgetItem(key_text)
            entries_table.setItem(i, 0, key_item)
            
            # Value (blank - ready for user input)
            value_item = QTableWidgetItem("")
            entries_table.setItem(i, 1, value_item)
            
            # Comment (blank)
            comment_item = QTableWidgetItem("")
            entries_table.setItem(i, 2, comment_item)
        
        layout.addWidget(entries_table)
        
        # Connect table button handlers
        def add_empty_row():
            row_idx = entries_table.rowCount()
            entries_table.insertRow(row_idx)
            entries_table.setItem(row_idx, 0, QTableWidgetItem(''))
            entries_table.setItem(row_idx, 1, QTableWidgetItem(''))
            entries_table.setItem(row_idx, 2, QTableWidgetItem(''))
        
        def delete_selected_rows():
            selected_rows = set()
            for item in entries_table.selectedItems():
                selected_rows.add(item.row())
            for row_idx in sorted(selected_rows, reverse=True):
                entries_table.removeRow(row_idx)
        
        add_row_btn.clicked.connect(add_empty_row)
        delete_btn.clicked.connect(delete_selected_rows)
        
        # Bottom buttons
        bottom_btn_layout = QHBoxLayout()
        bottom_btn_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Data Map")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFD700;
                color: #1E3A8A;
                border: none;
                border-radius: 4px;
                padding: 10px 24px;
                font-weight: bold;
                font-size: 13px;
                min-width: 140px;
            }
            QPushButton:hover { background-color: #FFE033; }
            QPushButton:pressed { background-color: #E6C200; }
        """)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6B7280;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 24px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #7B8290; }
        """)
        
        def save_new_data_map():
            map_name = name_input.text().strip()
            if not map_name:
                QMessageBox.warning(dialog, "Validation Error", "Please enter a map name")
                return
            
            # Check for unique name
            if not self.data_map_repo.is_map_name_unique(map_name):
                QMessageBox.warning(dialog, "Duplicate Name", 
                    f"A data map named '{map_name}' already exists.\n"
                    "Data map names must be unique across all groups.")
                return
            
            try:
                # Create the data map
                data_map_id = self.data_map_repo.create_data_map(
                    map_name=map_name,
                    key_data_type=key_type_combo.currentText(),
                    value_data_type=value_type_combo.currentText(),
                    notes=notes_input.toPlainText().strip() or None
                )
                
                # Add all entries
                for row_idx in range(entries_table.rowCount()):
                    key = entries_table.item(row_idx, 0).text().strip()
                    value = entries_table.item(row_idx, 1).text().strip()
                    comment = entries_table.item(row_idx, 2).text().strip() or None
                    
                    if key:  # Only add entries with non-empty keys
                        self.data_map_repo.add_map_entry(
                            data_map_id,
                            key_value=key,
                            mapped_value=value or None,
                            comment=comment
                        )
                
                # Assign the new data map to the field
                self.data_map_repo.assign_data_map_to_field(
                    self.current_connection_id,
                    self.current_table_name,
                    column_name,
                    self.current_schema_name,
                    data_map_id
                )
                
                # Refresh UI
                self._refresh_data_map_button(column_name, data_map_id)
                self._load_data_maps()  # Refresh data maps tree
                
                QMessageBox.information(dialog, "Success", 
                    f"Data map '{map_name}' created and assigned to {column_name}!")
                
                dialog.accept()
                parent_dialog.accept()  # Close unique values dialog
                
                logger.info(f"Created and assigned data map '{map_name}' to {column_name}")
                
            except Exception as e:
                logger.error(f"Error creating data map: {e}")
                QMessageBox.critical(dialog, "Error", f"Failed to create data map:\n{str(e)}")
        
        save_btn.clicked.connect(save_new_data_map)
        cancel_btn.clicked.connect(dialog.reject)
        
        bottom_btn_layout.addWidget(save_btn)
        bottom_btn_layout.addWidget(cancel_btn)
        layout.addLayout(bottom_btn_layout)
        
        dialog.exec()

    def _infer_data_type(self, field_type: str) -> str:
        """Infer a data map key type from a database field type"""
        field_type_lower = field_type.lower()
        
        if any(t in field_type_lower for t in ['int', 'smallint', 'bigint', 'tinyint']):
            return 'integer'
        elif any(t in field_type_lower for t in ['decimal', 'numeric', 'float', 'double', 'real']):
            return 'decimal'
        elif any(t in field_type_lower for t in ['date', 'time', 'timestamp']):
            return 'date'
        elif any(t in field_type_lower for t in ['bool', 'bit']):
            return 'boolean'
        else:
            return 'string'

    def preview_table(self):
        """Preview table data (first 100 rows)"""
        if not self.current_connection_id or not self.current_table_name:
            return

        try:
            from suiteview.ui.dialogs.preview_dialog import PreviewDialog

            # Get preview data
            display_name = f"{self.current_schema_name}.{self.current_table_name}" if self.current_schema_name else self.current_table_name
            logger.info(f"Fetching preview data for {display_name}")

            columns, data = self.schema_discovery.get_preview_data(
                self.current_connection_id,
                self.current_table_name,
                self.current_schema_name,
                limit=10000
            )
            
            # Debug logging to check data structure
            logger.info(f"Preview data retrieved: {len(columns)} columns, {len(data)} rows")
            if data and len(data) > 0:
                logger.info(f"First row type: {type(data[0])}, length: {len(data[0]) if hasattr(data[0], '__len__') else 'N/A'}")
                logger.info(f"First row sample: {data[0][:5] if hasattr(data[0], '__getitem__') else data[0]}")

            # Show preview dialog with connection info for reloading capability
            dialog = PreviewDialog(
                display_name, 
                data, 
                columns, 
                self,
                connection_id=self.current_connection_id,
                schema_name=self.current_schema_name,
                schema_discovery=self.schema_discovery
            )
            dialog.show()  # Modeless - allows interaction with main app

        except Exception as e:
            logger.error(f"Error previewing table: {e}")
            QMessageBox.critical(self, "Error", f"Failed to preview table:\n{str(e)}")

    def on_common_checkbox_changed(self, row: int, column_name: str, state: int):
        """Handle common checkbox state change"""
        is_common = (state == Qt.CheckState.Checked.value)
        
        # Get metadata_id for the current table
        metadata_id = self.metadata_cache_repo.get_or_create_metadata(
            self.current_connection_id,
            self.current_table_name,
            self.current_schema_name
        )
        
        # Update the database
        self.metadata_cache_repo.update_column_common_flag(metadata_id, column_name, is_common)
        
        logger.info(f"Set common flag for {column_name} to {is_common}")

    def on_type_changed(self, row: int, column_name: str, new_type: str):
        """Handle data type change for CSV columns"""
        # Get metadata_id for the current table
        metadata_id = self.metadata_cache_repo.get_or_create_metadata(
            self.current_connection_id,
            self.current_table_name,
            self.current_schema_name
        )
        
        # Update the column type in the cache
        self.metadata_cache_repo.update_column_type(metadata_id, column_name, new_type)
        
        logger.info(f"Changed type for {column_name} to {new_type}")

    def show_datasource_context_menu(self, position):
        """Show context menu for data source tree items (left panel)"""
        item = self.my_data_tree.itemAt(position)
        if not item:
            return

        # Check if this is a connection item (not a category header)
        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        
        if item_type == "connection":
            conn_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            conn_name = item.text(0)
            
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { border: 2px solid #555; }")
            remove_action = QAction("Remove Database", self)
            remove_action.triggered.connect(lambda: self._remove_connection_from_mydata(conn_id, conn_name))
            menu.addAction(remove_action)
            
            menu.exec(self.my_data_tree.viewport().mapToGlobal(position))
    
    def _remove_connection_from_mydata(self, conn_id: int, conn_name: str):
        """Remove all saved tables for a connection from My Data"""
        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Remove Database",
            f"Remove all tables from '{conn_name}' from My Data?\n\nThis will remove all saved tables for this database.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Get all saved tables for this connection
                saved_tables = self.saved_table_repo.get_saved_tables_by_connection(conn_id)
                
                # Delete each saved table
                for table in saved_tables:
                    self.saved_table_repo.delete_saved_table(
                        conn_id, 
                        table['table_name'], 
                        table.get('schema_name', '')
                    )
                
                logger.info(f"Removed {len(saved_tables)} tables from connection: {conn_name}")
                
                # Reload My Data tree
                self.load_my_data()
                
                # Clear right panel if this was the selected connection
                if self.current_connection_id == conn_id:
                    self._clear_right_panel()
                    self.right_panel_layout.addWidget(self.default_label)
                    self.current_connection_id = None
                    self.current_table_name = None
                
                QMessageBox.information(
                    self,
                    "Database Removed",
                    f"All tables from '{conn_name}' have been removed from My Data."
                )

            except Exception as e:
                logger.error(f"Error removing connection tables: {e}")
                QMessageBox.critical(self, "Error", f"Failed to remove database:\n{str(e)}")

    def show_context_menu(self, position):
        """Show context menu for tree items"""
        item = self.tables_tree.itemAt(position)
        if not item:
            return

        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        menu = QMenu()

        if item_type == "table":
            # Context menu for saved tables
            remove_action = QAction("Remove from My Data", self)
            remove_action.triggered.connect(lambda: self.remove_saved_table(item))
            menu.addAction(remove_action)

        elif item_type == "db_query" or item_type == "xdb_query":
            # Context menu for saved queries (Phase 4/5)
            edit_action = QAction("Edit Query", self)
            menu.addAction(edit_action)

            delete_action = QAction("Delete Query", self)
            menu.addAction(delete_action)

        if not menu.isEmpty():
            menu.exec(self.tables_tree.viewport().mapToGlobal(position))

    def remove_saved_table(self, item: QTreeWidgetItem):
        """Remove a table from My Data"""
        conn_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        table_name = item.data(0, Qt.ItemDataRole.UserRole + 2)
        schema_name = item.data(0, Qt.ItemDataRole.UserRole + 3)

        # Confirm deletion
        display_name = f"{schema_name}.{table_name}" if schema_name else table_name
        reply = QMessageBox.question(
            self,
            "Remove Table",
            f"Remove '{display_name}' from My Data?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.saved_table_repo.delete_saved_table(conn_id, table_name, schema_name)
                logger.info(f"Removed saved table: {display_name}")

                # Reload tables for current connection
                if self.current_connection_id == conn_id:
                    self.load_tables_for_connection(conn_id)

                # Reload My Data tree
                self.load_my_data()

                # Clear right panel if this was the selected table
                if self.current_table_name == table_name:
                    self._clear_right_panel()
                    self.right_panel_layout.addWidget(self.default_label)

            except Exception as e:
                logger.error(f"Error removing saved table: {e}")
                QMessageBox.critical(self, "Error", f"Failed to remove table:\n{str(e)}")

    def _clear_right_panel(self):
        """Clear all widgets from right panel"""
        while self.right_panel_layout.count():
            child = self.right_panel_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def _show_context_menu(self, position):
        """Show context menu for tree items"""
        item = self.my_data_tree.itemAt(position)
        if not item:
            return
        
        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { border: 2px solid #555; }")
        
        # Context menu for DB Queries section header - REMOVED (Handled by button context menu now)
        # if item == self.db_queries_item:
        #     add_folder_action = menu.addAction("➕ New Folder")
        #     add_folder_action.triggered.connect(lambda: self._create_new_folder('DB'))
        
        # Context menu for query folders
        if item_type == "query_folder":
            folder_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            folder_name = item.text(0).replace("📁 ", "")
            
            # Don't allow deleting or renaming the General folder
            if folder_name != "General":
                rename_action = menu.addAction("✏️ Rename Folder")
                rename_action.triggered.connect(lambda: self._rename_folder(folder_id, item))
                
                menu.addSeparator()
                
                delete_action = menu.addAction("🗑️ Delete Folder")
                delete_action.triggered.connect(lambda: self._delete_folder(folder_id))
        
        # Context menu for queries
        elif item_type == "db_query":
            rename_action = menu.addAction("✏️ Rename Query")
            rename_action.triggered.connect(lambda: self._rename_query_item(item))
            
            menu.addSeparator()
            
            delete_action = menu.addAction("�️ Delete Query")
            delete_action.triggered.connect(lambda: self._delete_query_item(item))
        
        if not menu.isEmpty():
            menu.exec(self.my_data_tree.viewport().mapToGlobal(position))
    
    def _show_data_map_context_menu(self, position):
        """Show context menu for data mapping tree items"""
        item = self.data_mapping_tree.itemAt(position)
        if not item:
            # Right-click on empty space - show "New Folder" and "New Data Map" options
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { border: 2px solid #555; }")
            
            add_folder_action = menu.addAction("➕ New Folder")
            add_folder_action.triggered.connect(lambda: self._create_new_data_map_folder())
            
            menu.addSeparator()
            
            add_map_action = menu.addAction("📊 New Data Map")
            add_map_action.triggered.connect(lambda: self._create_new_data_map())
            
            menu.exec(self.data_mapping_tree.mapToGlobal(position))
            return
        
        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { border: 2px solid #555; }")
        
        # Context menu for data map folders
        if item_type == "data_map_folder":
            folder_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            folder_name = item.text(0).replace("📁 ", "")
            
            add_map_action = menu.addAction("� New Data Map")
            add_map_action.triggered.connect(lambda: self._create_new_data_map(folder_id))
            
            menu.addSeparator()
            
            # Don't allow deleting or renaming the General folder
            if folder_name != "General":
                rename_action = menu.addAction("✏️ Rename Folder")
                rename_action.triggered.connect(lambda: self._rename_data_map_folder(folder_id, item))
                
                menu.addSeparator()
                
                delete_action = menu.addAction("🗑️ Delete Folder")
                delete_action.triggered.connect(lambda: self._delete_data_map_folder(folder_id))
        
        # Context menu for data maps
        elif item_type == "data_map":
            data_map_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            
            delete_action = menu.addAction("🗑️ Delete Data Map")
            delete_action.triggered.connect(lambda: self._delete_data_map(data_map_id))
        
        if not menu.isEmpty():
            menu.exec(self.data_mapping_tree.viewport().mapToGlobal(position))
    
    def _show_header_context_menu(self, position, query_type: str):
        """Show context menu for DB Queries header label"""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { border: 2px solid #555; }")

        add_folder_action = menu.addAction("➕ New Folder")
        add_folder_action.triggered.connect(lambda: self._create_new_folder(query_type))

        # Get the header widget to map position correctly
        header = self.sender()
        menu.exec(header.mapToGlobal(position))

    def _show_data_mapping_header_context_menu(self, position):
        """Show context menu for Data Mapping header label"""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { border: 2px solid #555; }")

        add_folder_action = menu.addAction("➕ New Folder")
        add_folder_action.triggered.connect(lambda: self._create_new_data_map_folder())

        menu.addSeparator()

        add_map_action = menu.addAction("📊 New Data Map")
        add_map_action.triggered.connect(lambda: self._create_new_data_map())

        # Get the header widget to map position correctly
        header = self.sender()
        menu.exec(header.mapToGlobal(position))
    
    def _show_db_query_context_menu_mydata(self, position):
        """Show context menu for DB Query tree items in My Data screen"""
        # For now, just show a simple context menu
        # The full query management is in the DB Query screen
        item = self.db_queries_tree.itemAt(position)
        if not item:
            return
        
        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        
        if item_type == "query_folder":
            # Folder context menu
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { border: 2px solid #555; }")
            
            rename_action = menu.addAction("✏️ Rename Folder")
            delete_action = menu.addAction("🗑️ Delete Folder")
            
            menu.exec(self.db_queries_tree.viewport().mapToGlobal(position))
        elif item_type == "db_query":
            # Query context menu
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { border: 2px solid #555; }")
            
            delete_action = menu.addAction("🗑️ Delete Query")
            
            menu.exec(self.db_queries_tree.viewport().mapToGlobal(position))
    
    def on_data_map_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on data map item - show editor in right panel"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        
        # Only handle data map clicks, not folder clicks
        if item_type != "data_map":
            return
        
        data_map_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        self._show_data_map_editor_in_panel(data_map_id)
    
    def _create_new_folder(self, query_type: str):
        """Create a new query folder"""
        from PyQt6.QtWidgets import QInputDialog
        
        folder_name, ok = QInputDialog.getText(
            self,
            "New Folder",
            "Enter folder name:"
        )
        
        if ok and folder_name.strip():
            try:
                self.query_repo.create_folder(folder_name.strip(), query_type)
                self._load_db_queries()  # Reload to show new folder
                self.queries_changed.emit()  # Notify other screens
                logger.info(f"Created new folder: {folder_name}")
            except Exception as e:
                logger.error(f"Error creating folder: {e}")
                QMessageBox.critical(self, "Error", f"Failed to create folder:\n{str(e)}")
    
    def _rename_folder(self, folder_id: int, item: QTreeWidgetItem):
        """Rename a folder"""
        from PyQt6.QtWidgets import QInputDialog
        
        current_name = item.text(0).replace("📁 ", "")
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Folder",
            "Enter new folder name:",
            text=current_name
        )
        
        if ok and new_name.strip() and new_name.strip() != current_name:
            try:
                self.query_repo.rename_folder(folder_id, new_name.strip())
                item.setText(0, f"📁 {new_name.strip()}")
                self.queries_changed.emit()  # Notify other screens
                logger.info(f"Renamed folder {folder_id} to: {new_name}")
            except Exception as e:
                logger.error(f"Error renaming folder: {e}")
                QMessageBox.critical(self, "Error", f"Failed to rename folder:\n{str(e)}")
    
    def _delete_folder(self, folder_id: int):
        """Delete a folder"""
        # Count queries in folder
        query_count = self.query_repo.count_queries_in_folder(folder_id)
        
        # Build confirmation message based on query count
        if query_count > 0:
            message = (
                f"This folder contains {query_count} quer{'y' if query_count == 1 else 'ies'}.\n\n"
                f"Are you sure you want to delete this folder?\n"
                f"All queries in this folder will be moved to the General folder."
            )
        else:
            message = "Are you sure you want to delete this empty folder?"
        
        reply = QMessageBox.question(
            self,
            "Delete Folder",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.query_repo.delete_folder(folder_id)
                self._load_db_queries()  # Reload to reflect deletion
                self.queries_changed.emit()  # Notify other screens
                logger.info(f"Deleted folder {folder_id}")
            except Exception as e:
                logger.error(f"Error deleting folder: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete folder:\n{str(e)}")
    
    def _rename_query_item(self, item: QTreeWidgetItem):
        """Rename a query from tree context menu"""
        from PyQt6.QtWidgets import QInputDialog
        
        query_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        current_name = item.text(0)
        
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Query",
            "Enter new query name:",
            text=current_name
        )
        
        if ok and new_name.strip() and new_name.strip() != current_name:
            try:
                self.query_repo.update_query_name(query_id, new_name.strip())
                item.setText(0, new_name.strip())
                self.queries_changed.emit()  # Notify other screens
                logger.info(f"Renamed query {query_id} to: {new_name}")
            except Exception as e:
                logger.error(f"Error renaming query: {e}")
                QMessageBox.critical(self, "Error", f"Failed to rename query:\n{str(e)}")
    
    def _delete_query_item(self, item: QTreeWidgetItem):
        """Delete a query from tree context menu"""
        query_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        query_name = item.text(0)
        
        reply = QMessageBox.question(
            self,
            "Delete Query",
            f"Are you sure you want to delete '{query_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.query_repo.delete_query(query_id)
                self._load_db_queries()  # Reload to reflect deletion
                self.queries_changed.emit()  # Notify other screens
                logger.info(f"Deleted query {query_id}")
            except Exception as e:
                logger.error(f"Error deleting query: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete query:\n{str(e)}")
    
    def _on_query_moved(self, query_id: int, folder_id: int):
        """Handle query being moved to a different folder"""
        try:
            self.query_repo.move_query_to_folder(query_id, folder_id)
            # Reload while preserving user's folder expand/collapse state
            self._load_db_queries()
            self.queries_changed.emit()  # Notify other screens
            logger.info(f"Moved query {query_id} to folder {folder_id}")
        except Exception as e:
            logger.error(f"Error moving query: {e}")
            QMessageBox.critical(self, "Error", f"Failed to move query:\n{str(e)}")
            # Reload to revert visual change
            self._load_db_queries()

    def _on_data_map_moved(self, data_map_id: int, folder_id: int):
        """Handle data map being moved to a different folder"""
        try:
            self.data_map_repo.move_data_map_to_folder(data_map_id, folder_id)
            # Reload while preserving user's folder expand/collapse state
            self._load_data_maps()
            logger.info(f"Moved data map {data_map_id} to folder {folder_id}")
        except Exception as e:
            logger.error(f"Error moving data map: {e}")
            QMessageBox.critical(self, "Error", f"Failed to move data map:\n{str(e)}")
            # Reload to revert visual change
            self._load_data_maps()

    def _create_new_data_map_folder(self):
        """Create a new data map folder"""
        from PyQt6.QtWidgets import QInputDialog
        
        folder_name, ok = QInputDialog.getText(
            self,
            "New Folder",
            "Enter folder name:"
        )
        
        if ok and folder_name.strip():
            try:
                self.data_map_repo.create_folder(folder_name.strip())
                self._load_data_maps()  # Reload to show new folder
                logger.info(f"Created new data map folder: {folder_name}")
            except Exception as e:
                logger.error(f"Error creating data map folder: {e}")
                QMessageBox.critical(self, "Error", f"Failed to create folder:\n{str(e)}")

    def _rename_data_map_folder(self, folder_id: int, item: QTreeWidgetItem):
        """Rename a data map folder"""
        from PyQt6.QtWidgets import QInputDialog
        
        current_name = item.text(0).replace("📁 ", "")
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Folder",
            "Enter new folder name:",
            text=current_name
        )
        
        if ok and new_name.strip() and new_name.strip() != current_name:
            try:
                self.data_map_repo.rename_folder(folder_id, new_name.strip())
                item.setText(0, f"📁 {new_name.strip()}")
                logger.info(f"Renamed data map folder {folder_id} to: {new_name}")
            except Exception as e:
                logger.error(f"Error renaming data map folder: {e}")
                QMessageBox.critical(self, "Error", f"Failed to rename folder:\n{str(e)}")

    def _delete_data_map_folder(self, folder_id: int):
        """Delete a data map folder"""
        # Count maps in folder
        map_count = self.data_map_repo.count_maps_in_folder(folder_id)
        
        # Build confirmation message based on map count
        if map_count > 0:
            message = (
                f"This folder contains {map_count} data map{'s' if map_count != 1 else ''}.\n\n"
                f"Are you sure you want to delete this folder?\n"
                f"All data maps in this folder will be moved to the General folder."
            )
        else:
            message = "Are you sure you want to delete this empty folder?"
        
        reply = QMessageBox.question(
            self,
            "Delete Folder",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.data_map_repo.delete_folder(folder_id)
                self._load_data_maps()  # Reload to reflect deletion
                logger.info(f"Deleted data map folder {folder_id}")
            except Exception as e:
                logger.error(f"Error deleting data map folder: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete folder:\n{str(e)}")

    def _create_new_data_map(self, folder_id: int = None):
        """Create a new data map"""
        dialog = DataMapEditorDialog(self, folder_id=folder_id)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_data_maps()  # Reload to show new map
            logger.info("Created new data map")

    def _edit_data_map(self, data_map_id: int):
        """Edit an existing data map"""
        dialog = DataMapEditorDialog(self, data_map_id=data_map_id)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_data_maps()  # Reload to show changes
            logger.info(f"Edited data map {data_map_id}")

    def _delete_data_map(self, data_map_id: int):
        """Delete a data map"""
        # Get data map details
        data_map = self.data_map_repo.get_data_map(data_map_id)
        if not data_map:
            return
        
        reply = QMessageBox.question(
            self,
            "Delete Data Map",
            f"Are you sure you want to delete the data map '{data_map['map_name']}'?\n\n"
            f"This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.data_map_repo.delete_data_map(data_map_id)
                self._load_data_maps()  # Reload to reflect deletion
                self._clear_right_panel()  # Clear the editor from right panel
                logger.info(f"Deleted data map {data_map_id}")
            except Exception as e:
                logger.error(f"Error deleting data map: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete data map:\n{str(e)}")

    def _show_data_map_editor_in_panel(self, data_map_id: int):
        """Show data map editor in the right panel instead of a dialog"""
        # Clear right panel
        self._clear_right_panel()
        
        try:
            # Get data map details
            data_map = self.data_map_repo.get_data_map(data_map_id)
            if not data_map:
                QMessageBox.warning(self, "Error", "Data map not found")
                return
            
            # Get folder/group name
            folder = self.data_map_repo.get_folder(data_map.get('folder_id'))
            group_name = folder['folder_name'] if folder else "General"
            
            # Create editor widget with clean styling
            editor_widget = QWidget()
            editor_widget.setStyleSheet("""
                QWidget {
                    background-color: #F8FAFC;
                }
                QLabel {
                    background-color: transparent;
                }
                QLineEdit, QComboBox, QTextEdit {
                    background-color: white;
                    border: 1px solid #CBD5E1;
                    border-radius: 4px;
                    padding: 6px 10px;
                    font-size: 12px;
                }
                QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                    border: 2px solid #2563EB;
                }
                QComboBox {
                    padding: 4px 8px;
                }
            """)
            editor_layout = QVBoxLayout(editor_widget)
            editor_layout.setContentsMargins(16, 16, 16, 16)
            editor_layout.setSpacing(16)
            
            # === HEADER SECTION ===
            header_widget = QWidget()
            header_widget.setStyleSheet("""
                QWidget {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                stop:0 #1E3A8A, stop:1 #2563EB);
                    border-radius: 8px;
                }
                QLabel {
                    color: white;
                    background: transparent;
                }
            """)
            header_layout = QVBoxLayout(header_widget)
            header_layout.setContentsMargins(16, 12, 16, 12)
            header_layout.setSpacing(4)
            
            # Title
            title = QLabel(data_map['map_name'])
            title.setStyleSheet("font-size: 18px; font-weight: bold;")
            header_layout.addWidget(title)
            
            # Group subtitle
            group_subtitle = QLabel(f"📁 {group_name}")
            group_subtitle.setStyleSheet("font-size: 12px; color: #FFD700;")
            header_layout.addWidget(group_subtitle)
            
            editor_layout.addWidget(header_widget)
            
            # === DETAILS CARD ===
            details_card = QWidget()
            details_card.setStyleSheet("""
                QWidget#details_card {
                    background-color: white;
                    border: 1px solid #E2E8F0;
                    border-radius: 8px;
                }
                QLabel {
                    background: transparent;
                }
            """)
            details_card.setObjectName("details_card")
            details_layout = QVBoxLayout(details_card)
            details_layout.setContentsMargins(16, 16, 16, 16)
            details_layout.setSpacing(12)
            
            # Section title
            details_title = QLabel("Details")
            details_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #1E3A8A;")
            details_layout.addWidget(details_title)
            
            # Map name row
            name_row = QHBoxLayout()
            name_label = QLabel("Name:")
            name_label.setFixedWidth(100)
            name_label.setStyleSheet("font-weight: 500; color: #64748B;")
            name_row.addWidget(name_label)
            name_input = QLineEdit()
            name_input.setText(data_map['map_name'])
            name_row.addWidget(name_input)
            details_layout.addLayout(name_row)
            
            # Data types row
            types_row = QHBoxLayout()
            
            key_label = QLabel("Key Type:")
            key_label.setFixedWidth(100)
            key_label.setStyleSheet("font-weight: 500; color: #64748B;")
            types_row.addWidget(key_label)
            key_type_combo = QComboBox()
            key_type_combo.addItems(['string', 'integer', 'decimal', 'date', 'boolean'])
            key_type_combo.setCurrentText(data_map['key_data_type'])
            key_type_combo.setFixedWidth(100)
            types_row.addWidget(key_type_combo)
            
            types_row.addSpacing(20)
            
            value_label = QLabel("Value Type:")
            value_label.setStyleSheet("font-weight: 500; color: #64748B;")
            types_row.addWidget(value_label)
            value_type_combo = QComboBox()
            value_type_combo.addItems(['string', 'integer', 'decimal', 'date', 'boolean'])
            value_type_combo.setCurrentText(data_map['value_data_type'])
            value_type_combo.setFixedWidth(100)
            types_row.addWidget(value_type_combo)
            types_row.addStretch()
            details_layout.addLayout(types_row)
            
            # Notes row
            notes_label = QLabel("Notes:")
            notes_label.setStyleSheet("font-weight: 500; color: #64748B;")
            details_layout.addWidget(notes_label)
            notes_input = QTextEdit()
            notes_input.setPlaceholderText("Optional description or notes...")
            notes_input.setMaximumHeight(60)
            notes_input.setStyleSheet("QTextEdit { background-color: white; }")
            if data_map['notes']:
                notes_input.setPlainText(data_map['notes'])
            details_layout.addWidget(notes_input)
            
            editor_layout.addWidget(details_card)
            
            # === MAPPINGS CARD ===
            mappings_card = QWidget()
            mappings_card.setStyleSheet("""
                QWidget#mappings_card {
                    background-color: white;
                    border: 1px solid #E2E8F0;
                    border-radius: 8px;
                }
                QLabel {
                    background: transparent;
                }
            """)
            mappings_card.setObjectName("mappings_card")
            mappings_layout = QVBoxLayout(mappings_card)
            mappings_layout.setContentsMargins(16, 16, 16, 16)
            mappings_layout.setSpacing(12)
            
            # Section header with buttons
            mappings_header = QHBoxLayout()
            mappings_title = QLabel("Key-Value Mappings")
            mappings_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #1E3A8A;")
            mappings_header.addWidget(mappings_title)
            mappings_header.addStretch()
            
            add_row_btn = QPushButton("+ Add")
            add_row_btn.setStyleSheet("""
                QPushButton {
                    background-color: #10B981;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #059669; }
            """)
            mappings_header.addWidget(add_row_btn)
            
            delete_rows_btn = QPushButton("Delete")
            delete_rows_btn.setStyleSheet("""
                QPushButton {
                    background-color: #EF4444;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover { background-color: #DC2626; }
            """)
            mappings_header.addWidget(delete_rows_btn)
            mappings_layout.addLayout(mappings_header)
            
            # Table
            entries_table = QTableWidget()
            entries_table.setColumnCount(4)
            entries_table.setHorizontalHeaderLabels(['Key', 'Value', 'Comment', 'Last Updated'])
            entries_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            entries_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
            
            # Allow user to resize columns
            header = entries_table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(True)
            entries_table.setColumnWidth(0, 70)
            entries_table.setColumnWidth(1, 140)
            entries_table.setColumnWidth(2, 100)
            entries_table.setColumnWidth(3, 130)
            
            entries_table.setWordWrap(True)
            entries_table.setStyleSheet("""
                QTableWidget {
                    border: 1px solid #E2E8F0;
                    border-radius: 4px;
                    gridline-color: #E2E8F0;
                    selection-background-color: #EFF6FF;
                    selection-color: #1E3A8A;
                    background-color: white;
                }
                QHeaderView::section {
                    background-color: #1E3A8A;
                    color: white;
                    padding: 8px 4px;
                    border: none;
                    font-weight: bold;
                    font-size: 11px;
                }
                QTableWidget::item {
                    padding: 0px;
                    margin: 0px;
                }
                QTableWidget::item:selected {
                    background-color: #EFF6FF;
                    color: #1E3A8A;
                }
                QLineEdit {
                    border: none;
                    padding: 0px;
                    margin: 0px;
                    background: white;
                }
            """)
            
            # Load entries
            entries = self.data_map_repo.get_map_entries(data_map_id)
            for entry in entries:
                row = entries_table.rowCount()
                entries_table.insertRow(row)
                
                # Key
                key_item = QTableWidgetItem(entry['key_value'])
                entries_table.setItem(row, 0, key_item)
                
                # Value
                value_item = QTableWidgetItem(entry['mapped_value'] or '')
                entries_table.setItem(row, 1, value_item)
                
                # Comment
                comment_item = QTableWidgetItem(entry['comment'] or '')
                entries_table.setItem(row, 2, comment_item)
                
                # Last Updated
                last_updated_item = QTableWidgetItem(entry['last_updated'] or '')
                last_updated_item.setFlags(last_updated_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                entries_table.setItem(row, 3, last_updated_item)
                
                # Store entry_id
                entries_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, entry['entry_id'])
            
            mappings_layout.addWidget(entries_table, 1)  # Give table stretch priority
            editor_layout.addWidget(mappings_card, 1)  # Give mappings card stretch priority
            
            # Connect cell changed handler to update Last Updated timestamp
            def on_cell_changed(row, column):
                # Only update if it's not the Last Updated column being changed
                if column != 3:  # Last Updated is column 3
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    last_updated_item = entries_table.item(row, 3)
                    if last_updated_item:
                        last_updated_item.setText(timestamp)
            
            entries_table.cellChanged.connect(on_cell_changed)
            
            # Connect button handlers
            def add_empty_row():
                row = entries_table.rowCount()
                entries_table.insertRow(row)
                
                # Temporarily disconnect to avoid triggering cellChanged
                entries_table.cellChanged.disconnect(on_cell_changed)
                
                entries_table.setItem(row, 0, QTableWidgetItem(''))
                entries_table.setItem(row, 1, QTableWidgetItem(''))
                entries_table.setItem(row, 2, QTableWidgetItem(''))
                last_updated_item = QTableWidgetItem('')
                last_updated_item.setFlags(last_updated_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                entries_table.setItem(row, 3, last_updated_item)
                
                # Reconnect
                entries_table.cellChanged.connect(on_cell_changed)
            
            def delete_selected_rows():
                selected_rows = set()
                for item in entries_table.selectedItems():
                    selected_rows.add(item.row())
                
                if not selected_rows:
                    QMessageBox.information(self, "No Selection", "Please select rows to delete")
                    return
                
                for row in sorted(selected_rows, reverse=True):
                    entries_table.removeRow(row)
            
            add_row_btn.clicked.connect(add_empty_row)
            delete_rows_btn.clicked.connect(delete_selected_rows)
            
            # === ACTION BUTTONS ===
            buttons_layout = QHBoxLayout()
            buttons_layout.addStretch()
            
            cancel_btn = QPushButton("Cancel")
            cancel_btn.setStyleSheet("""
                QPushButton {
                    background-color: #F1F5F9;
                    color: #475569;
                    border: 1px solid #CBD5E1;
                    border-radius: 6px;
                    padding: 10px 24px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #E2E8F0;
                    border-color: #94A3B8;
                }
            """)
            buttons_layout.addWidget(cancel_btn)
            
            save_btn = QPushButton("💾 Save Changes")
            save_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                stop:0 #FFD700, stop:1 #F59E0B);
                    color: #1E3A8A;
                    border: none;
                    border-radius: 6px;
                    padding: 10px 24px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                                stop:0 #FDE047, stop:1 #FFD700);
                }
            """)
            buttons_layout.addWidget(save_btn)
            
            editor_layout.addLayout(buttons_layout)
            
            # Connect save button
            def save_data_map():
                try:
                    map_name = name_input.text().strip()
                    if not map_name:
                        QMessageBox.warning(self, "Validation Error", "Please enter a map name")
                        return
                    
                    # Check for unique name (excluding current data map)
                    if not self.data_map_repo.is_map_name_unique(map_name, exclude_data_map_id=data_map_id):
                        QMessageBox.warning(self, "Duplicate Name", 
                            f"A data map named '{map_name}' already exists.\n"
                            "Data map names must be unique across all groups.")
                        return
                    
                    # Update data map
                    self.data_map_repo.update_data_map(
                        data_map_id,
                        map_name=map_name,
                        key_data_type=key_type_combo.currentText(),
                        value_data_type=value_type_combo.currentText(),
                        notes=notes_input.toPlainText().strip() or None
                    )
                    
                    # Get existing entries
                    existing_entries = self.data_map_repo.get_map_entries(data_map_id)
                    existing_entry_ids = {e['entry_id'] for e in existing_entries}
                    kept_entry_ids = set()
                    
                    # Save all entries
                    for row in range(entries_table.rowCount()):
                        key = entries_table.item(row, 0).text().strip()
                        value = entries_table.item(row, 1).text().strip()
                        comment = entries_table.item(row, 2).text().strip() or None
                        entry_id = entries_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                        
                        if not key:  # Skip empty keys
                            continue
                        
                        if entry_id and entry_id in existing_entry_ids:
                            # Update existing entry
                            self.data_map_repo.update_map_entry(
                                entry_id,
                                key_value=key,
                                mapped_value=value or None,
                                comment=comment
                            )
                            kept_entry_ids.add(entry_id)
                        else:
                            # Add new entry
                            new_entry_id = self.data_map_repo.add_map_entry(
                                data_map_id,
                                key_value=key,
                                mapped_value=value or None,
                                comment=comment
                            )
                            kept_entry_ids.add(new_entry_id)
                    
                    # Delete entries that were removed
                    deleted_ids = existing_entry_ids - kept_entry_ids
                    if deleted_ids:
                        self.data_map_repo.delete_map_entries(list(deleted_ids))
                    
                    QMessageBox.information(self, "Success", f"Data map '{map_name}' saved successfully!")
                    self._load_data_maps()  # Reload tree
                    self._show_data_map_editor_in_panel(data_map_id)  # Refresh panel
                    
                except Exception as e:
                    logger.error(f"Error saving data map: {e}")
                    QMessageBox.critical(self, "Error", f"Failed to save data map:\n{str(e)}")
            
            def cancel_edit():
                self._clear_right_panel()
            
            save_btn.clicked.connect(save_data_map)
            cancel_btn.clicked.connect(cancel_edit)
            
            # Add to right panel
            self.right_panel_layout.addWidget(editor_widget)
            
        except Exception as e:
            logger.error(f"Error showing data map editor: {e}")
            QMessageBox.critical(self, "Error", f"Failed to load data map:\n{str(e)}")

    def refresh(self):
        """Refresh My Data (called when tables are saved/removed)"""
        self.load_my_data()

