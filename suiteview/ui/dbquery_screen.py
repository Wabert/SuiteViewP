"""DB Query Screen - Single-database query builder"""

import logging
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
                              QTreeWidget, QTreeWidgetItem, QTabWidget, QPushButton,
                              QScrollArea, QFrame, QLineEdit, QComboBox, QCheckBox,
                              QMessageBox, QInputDialog, QToolBar, QDateEdit, QSizePolicy,
                              QMenu, QToolButton, QLayout, QProgressDialog, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QDate, QRect, QSize, QPoint
from PyQt6.QtGui import QDrag, QAction

from suiteview.data.repositories import (SavedTableRepository, ConnectionRepository,
                                         get_metadata_cache_repository, get_query_repository)
from suiteview.core.schema_discovery import SchemaDiscovery
from suiteview.core.query_builder import QueryBuilder, Query
from suiteview.core.query_executor import QueryExecutor
from suiteview.ui.dialogs.query_results_dialog import QueryResultsDialog
from suiteview.ui.mydata_screen import QueryTreeWidget
from suiteview.ui.widgets import CascadingMenuWidget
from suiteview.ui.helpers import TreeStateManager
from suiteview.ui import theme

logger = logging.getLogger(__name__)


class FlowLayout(QLayout):
    """Custom flow layout that arranges widgets in rows with wrapping"""
    
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        
        self.setSpacing(spacing)
        self._item_list = []
        
    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)
    
    def addItem(self, item):
        self._item_list.append(item)
    
    def count(self):
        return len(self._item_list)
    
    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None
    
    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None
    
    def insertWidget(self, index, widget):
        """Insert widget at specific index"""
        from PyQt6.QtWidgets import QWidgetItem
        item = QWidgetItem(widget)
        if 0 <= index <= len(self._item_list):
            self._item_list.insert(index, item)
        else:
            self._item_list.append(item)
        self.invalidate()
    
    def expandingDirections(self):
        return Qt.Orientation(0)
    
    def hasHeightForWidth(self):
        return True
    
    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height
    
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)
    
    def sizeHint(self):
        return self.minimumSize()
    
    def minimumSize(self):
        size = QSize()
        
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size
    
    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        
        for item in self._item_list:
            widget = item.widget()
            space_x = spacing
            space_y = spacing
            
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        
        return y + line_height - rect.y()


class DBQueryScreen(QWidget):
    """DB Query screen with visual query builder"""
    
    # Signal when queries or folders change
    queries_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.saved_table_repo = SavedTableRepository()
        self.conn_repo = ConnectionRepository()
        self.schema_discovery = SchemaDiscovery()
        self.metadata_cache_repo = get_metadata_cache_repository()
        self.query_repo = get_query_repository()
        self.query_builder = QueryBuilder()
        self.query_executor = QueryExecutor()

        # Track current query state
        self.current_connection_id = None
        self.current_database_name = None
        self.current_table_name = None
        self.current_schema_name = None
        self.current_query_name = None  # Track the query name

        # Track query components
        self.criteria_widgets = []  # List of filter widgets in Criteria tab
        self.display_fields = []    # List of fields in Display tab
        self.display_widgets = []   # List of DisplayFieldWidget instances
        self.tables_involved = set()  # Set of table names involved in query
        self.joins = []  # List of join configurations
        
        # Track unsaved query states (query_id -> query_state_dict)
        self.unsaved_query_states = {}
        self.current_query_id = None  # Track which query is currently loaded

        # Track dirty state for change detection (#15)
        self._original_query_definition = None  # Store loaded query state
        self._is_dirty = False  # Track if query has unsaved changes

        self.init_ui()
        self.load_data_sources()

    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter for four panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Allow panels to be resized down to very small widths
        splitter.setChildrenCollapsible(False)  # Prevent complete collapse

        # Left Panel 1 - Data Sources
        panel1 = self._create_data_sources_panel()
        panel1.setMinimumWidth(20)  # Allow resizing down to 20px
        splitter.addWidget(panel1)

        # Left Panel 2 - Tables
        panel2 = self._create_tables_panel()
        panel2.setMinimumWidth(20)  # Allow resizing down to 20px
        splitter.addWidget(panel2)

        # Left Panel 3 - Fields
        panel3 = self._create_fields_panel()
        panel3.setMinimumWidth(20)  # Allow resizing down to 20px
        splitter.addWidget(panel3)

        # Right Panel - Query Builder
        right_panel = self._create_query_builder_panel()
        right_panel.setMinimumWidth(200)  # Keep minimum width for usability
        splitter.addWidget(right_panel)

        # Set initial sizes (200px, 200px, 200px, remaining)
        splitter.setSizes([200, 200, 200, 600])

        layout.addWidget(splitter)

    def _create_data_sources_panel(self) -> QWidget:
        """Create left panel with three sections: Databases, Recent Queries, and DB Queries"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)
        panel_layout.setSpacing(10)

        # Databases section
        databases_header = QLabel("DATABASES")
        theme.apply_panel_header(databases_header)
        panel_layout.addWidget(databases_header)

        # Create custom widget for database cascading menus
        self.data_sources_list = CascadingMenuWidget(self)
        panel_layout.addWidget(self.data_sources_list, stretch=1)

        # Recent Queries section (#1)
        recent_header = QLabel("RECENT QUERIES")
        theme.apply_panel_header(recent_header)
        panel_layout.addWidget(recent_header)

        # Recent queries list
        self.recent_queries_list = QTreeWidget()
        self.recent_queries_list.setHeaderHidden(True)
        self.recent_queries_list.setMaximumHeight(150)  # Compact list
        self.recent_queries_list.itemClicked.connect(self._on_recent_query_clicked)
        panel_layout.addWidget(self.recent_queries_list)

        # DB Queries section
        queries_header = QLabel("DB QUERIES")
        theme.apply_panel_header(queries_header)
        queries_header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        queries_header.customContextMenuRequested.connect(self._show_db_queries_header_context_menu)
        panel_layout.addWidget(queries_header)

        # Create tree widget for DB Queries list with folder support
        self.db_queries_tree = QueryTreeWidget()
        self.db_queries_tree.setHeaderHidden(True)
        self.db_queries_tree.itemClicked.connect(self._on_db_query_clicked)
        self.db_queries_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.db_queries_tree.customContextMenuRequested.connect(self._show_db_query_context_menu)
        self.db_queries_tree.query_moved.connect(self._on_query_moved)
        panel_layout.addWidget(self.db_queries_tree, stretch=1)

        return panel

    def _create_tables_panel(self) -> QWidget:
        """Create middle panel with tables list"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        # Panel header (will be updated dynamically)
        self.tables_header = QLabel("TABLES")
        theme.apply_panel_header(self.tables_header)
        panel_layout.addWidget(self.tables_header)

        # Database name label - prominent display
        self.database_name_label = QLabel("")
        self.database_name_label.setStyleSheet("""
            QLabel {
                background: #1976d2;
                color: white;
                padding: 8px;
                font-size: 13px;
                font-weight: bold;
                border-radius: 4px;
                margin: 5px 0px;
            }
        """)
        self.database_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.database_name_label.setVisible(False)  # Hidden until database selected
        panel_layout.addWidget(self.database_name_label)

        # Search box for filtering tables
        self.tables_search_box = QLineEdit()
        self.tables_search_box.setPlaceholderText("Search tables...")
        self.tables_search_box.textChanged.connect(self._filter_tables)
        panel_layout.addWidget(self.tables_search_box)

        # Tables tree
        self.tables_tree = QTreeWidget()
        self.tables_tree.setHeaderLabel("Tables")
        self.tables_tree.setHeaderHidden(True)
        self.tables_tree.setIndentation(15)
        
        # Connect signals
        self.tables_tree.itemClicked.connect(self.on_table_clicked)

        panel_layout.addWidget(self.tables_tree)

        # Info label
        self.table_info_label = QLabel("Select a database to view tables")
        self.table_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px; padding: 5px;")
        panel_layout.addWidget(self.table_info_label)

        return panel

    def _create_fields_panel(self) -> QWidget:
        """Create fields panel with column list"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        # Panel header (will be updated dynamically)
        self.fields_header = QLabel("FIELDS")
        theme.apply_panel_header(self.fields_header)
        panel_layout.addWidget(self.fields_header)

        # Search box for filtering fields
        search_layout = QHBoxLayout()
        search_layout.setSpacing(3)
        search_layout.setContentsMargins(0, 5, 0, 5)

        self.field_search_input = QLineEdit()
        self.field_search_input.setPlaceholderText("🔍 Search fields...")
        self.field_search_input.setMaximumHeight(26)
        self.field_search_input.setStyleSheet("""
            QLineEdit {
                padding: 4px 8px;
                border: 1px solid #B0C8E8;
                border-radius: 3px;
                background: white;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 2px solid #6BA3E8;
            }
        """)
        self.field_search_input.textChanged.connect(self._filter_fields_tree)
        search_layout.addWidget(self.field_search_input)

        clear_search_btn = QPushButton("×")
        clear_search_btn.setFixedSize(24, 24)
        clear_search_btn.setToolTip("Clear search")
        clear_search_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #6c757d;
                border: none;
                font-size: 16px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                color: #dc3545;
                background: #f8f9fa;
                border-radius: 3px;
            }
        """)
        clear_search_btn.clicked.connect(lambda: self.field_search_input.clear())
        search_layout.addWidget(clear_search_btn)

        panel_layout.addLayout(search_layout)

        # Add All and Add Common buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(5)
        buttons_layout.setContentsMargins(0, 5, 0, 5)

        self.add_all_btn = QPushButton("Add All")
        self.add_all_btn.setObjectName("gold_button")
        self.add_all_btn.setMinimumHeight(30)
        self.add_all_btn.clicked.connect(self.add_all_fields_to_display)
        buttons_layout.addWidget(self.add_all_btn)

        self.add_common_btn = QPushButton("Add Common")
        self.add_common_btn.setObjectName("gold_button")
        self.add_common_btn.setMinimumHeight(30)
        self.add_common_btn.clicked.connect(self.add_common_fields_to_display)
        buttons_layout.addWidget(self.add_common_btn)

        panel_layout.addLayout(buttons_layout)

        # Fields tree (with drag support) - use custom subclass
        self.fields_tree = DraggableFieldsTree()
        self.fields_tree.setHeaderLabel("Fields")
        self.fields_tree.setHeaderHidden(True)
        self.fields_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #E8F0FF;
                border: 1px solid #B0C8E8;
                border-radius: 0px;
            }
            QTreeWidget::item {
                height: 18px;
                padding: 0px;
                background-color: #E8F0FF;
            }
            QTreeWidget::item:hover {
                background-color: #C8DFFF;
            }
            QTreeWidget::item:selected {
                background-color: #6BA3E8;
            }
        """)
        self.fields_tree.setIndentation(15)
        
        # Connect double-click to show unique values inline
        self.fields_tree.itemDoubleClicked.connect(self.on_field_double_clicked)

        panel_layout.addWidget(self.fields_tree)

        # Info label
        self.field_info_label = QLabel("Select a table to view fields")
        self.field_info_label.setStyleSheet("color: #7f8c8d; font-size: 10px; padding: 5px;")
        panel_layout.addWidget(self.field_info_label)

        return panel

    def _create_query_builder_panel(self) -> QWidget:
        """Create right panel with query builder tabs"""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)

        # Toolbar with action buttons
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        toolbar_layout.setSpacing(10)

        # ==== PRIMARY ACTIONS GROUP ====
        # Run Query button with dropdown
        self.run_query_btn = QPushButton("▶ Run Query")
        self.run_query_btn.setMinimumWidth(100)
        self.run_query_btn.setMinimumHeight(32)
        self.run_query_btn.clicked.connect(self.run_query)
        self.run_query_btn.setEnabled(False)
        self.run_query_btn.setStyleSheet("""
            QPushButton {
                background: #1976d2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #1565c0;
            }
            QPushButton:disabled {
                background: #bdc3c7;
                color: #ecf0f1;
            }
        """)
        toolbar_layout.addWidget(self.run_query_btn)

        # Dropdown menu button for run options
        run_options_btn = QToolButton()
        run_options_btn.setText("▼")
        run_options_btn.setToolTip("More run options")
        run_options_btn.setMinimumHeight(32)
        run_options_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        run_options_btn.setStyleSheet("""
            QToolButton {
                background: #1976d2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 10px;
                font-weight: bold;
            }
            QToolButton:hover {
                background: #1565c0;
            }
            QToolButton:disabled {
                background: #bdc3c7;
                color: #ecf0f1;
            }
            QToolButton::menu-indicator {
                image: none;
            }
        """)

        # Create dropdown menu
        run_menu = QMenu(run_options_btn)

        # Preview action
        self.preview_action = QAction("👁 Preview (100 rows)", self)
        self.preview_action.setToolTip("Run query with 100 row limit")
        self.preview_action.triggered.connect(self._preview_query)
        self.preview_action.setEnabled(False)
        run_menu.addAction(self.preview_action)

        # View SQL action
        self.view_sql_action = QAction("📄 View SQL", self)
        self.view_sql_action.setToolTip("View generated SQL query")
        self.view_sql_action.triggered.connect(self._show_sql_dialog)
        self.view_sql_action.setEnabled(False)
        run_menu.addAction(self.view_sql_action)

        run_options_btn.setMenu(run_menu)
        run_options_btn.setEnabled(False)
        self.run_options_btn = run_options_btn
        toolbar_layout.addWidget(run_options_btn)

        # Save button
        self.save_query_btn = QPushButton("💾 Save")
        self.save_query_btn.setMinimumWidth(80)
        self.save_query_btn.setMinimumHeight(32)
        self.save_query_btn.setToolTip("Save query")
        self.save_query_btn.clicked.connect(self.save_query)
        self.save_query_btn.setEnabled(False)
        self.save_query_btn.setStyleSheet("""
            QPushButton {
                background: #1976d2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #1565c0;
            }
            QPushButton:disabled {
                background: #bdc3c7;
                color: #ecf0f1;
            }
        """)
        toolbar_layout.addWidget(self.save_query_btn)

        # Reset button
        self.reset_query_btn = QPushButton("🔄 Reset")
        self.reset_query_btn.setMinimumWidth(75)
        self.reset_query_btn.setMinimumHeight(32)
        self.reset_query_btn.setToolTip("Reset to last saved version")
        self.reset_query_btn.setStyleSheet("""
            QPushButton {
                background: #e3f2fd;
                color: #1976d2;
                border: 1px solid #1976d2;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #bbdefb;
            }
            QPushButton:disabled {
                background: #f5f5f5;
                color: #bdc3c7;
                border-color: #bdc3c7;
            }
        """)
        self.reset_query_btn.clicked.connect(self.reset_query)
        self.reset_query_btn.setEnabled(False)
        toolbar_layout.addWidget(self.reset_query_btn)

        # New Query button
        self.new_query_btn = QPushButton("✨ New")
        self.new_query_btn.setMinimumWidth(75)
        self.new_query_btn.setMinimumHeight(32)
        self.new_query_btn.setToolTip("Start a new query")
        self.new_query_btn.clicked.connect(self.new_query)
        self.new_query_btn.setStyleSheet("""
            QPushButton {
                background: #e3f2fd;
                color: #1976d2;
                border: 1px solid #1976d2;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #bbdefb;
            }
        """)
        toolbar_layout.addWidget(self.new_query_btn)
        toolbar_layout.addWidget(self.new_query_btn)

        # Add stretch to push query name to center
        toolbar_layout.addStretch()

        # Center: Query name label
        self.query_name_label = QLabel("unnamed")
        self.query_name_label.setStyleSheet("""
            QLabel {
                color: #1976d2;
                font-size: 13px;
                font-style: italic;
                font-weight: 600;
                padding: 5px 15px;
            }
        """)
        toolbar_layout.addWidget(self.query_name_label)

        # Add stretch to push labels to center
        toolbar_layout.addStretch()

        # Add toolbar layout to panel
        toolbar_container = QWidget()
        toolbar_container.setLayout(toolbar_layout)
        toolbar_container.setStyleSheet("""
            QWidget {
                background: #f8f9fa;
                border-bottom: 1px solid #ddd;
            }
        """)
        panel_layout.addWidget(toolbar_container)

        # Tab widget for Criteria, Display, Tables
        self.query_tabs = QTabWidget()
        self.query_tabs.setUsesScrollButtons(True)  # Enable scroll buttons if tabs don't fit
        self.query_tabs.setElideMode(Qt.TextElideMode.ElideNone)  # Don't elide tab text
        self.query_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #B0C8E8;
                background-color: #E8F0FF;
            }
            QTabBar {
                background-color: #E8F0FF;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
                margin-left: 0px;
                background-color: #D8E8FF;
                color: #0A1E5E;
                font-weight: 600;
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
            QTabBar::tab:last {
                margin-left: 0px;
            }
        """)

        # Display tab (FIRST)
        self.display_tab = self._create_display_tab()
        self.query_tabs.addTab(self.display_tab, "Display")

        # Criteria tab (SECOND)
        self.criteria_tab = self._create_criteria_tab()
        self.query_tabs.addTab(self.criteria_tab, "Criteria")

        # Tables tab
        self.tables_tab = self._create_tables_tab()
        self.query_tabs.addTab(self.tables_tab, "Tables")

        # Connect tab change signal to update field indicators
        self.query_tabs.currentChanged.connect(self._on_query_tab_changed)

        panel_layout.addWidget(self.query_tabs)

        return panel

    def _create_criteria_tab(self) -> QWidget:
        """Create Criteria tab with drop zone for filters - using tile layout"""
        tab = QWidget()
        tab.setAcceptDrops(True)
        tab.dragEnterEvent = lambda e: self._tab_drag_enter(e, 'criteria')
        tab.dropEvent = lambda e: self._tab_drop(e, 'criteria')
        
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Instructions
        instructions = QLabel("Drag fields here to add filter criteria")
        instructions.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 10px;")
        layout.addWidget(instructions)

        # Scroll area for criteria widgets
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        # Container for criteria widgets with FLOW LAYOUT
        self.criteria_container = QWidget()
        self.criteria_layout = FlowLayout(self.criteria_container, margin=5, spacing=5)

        scroll.setWidget(self.criteria_container)
        layout.addWidget(scroll)

        return tab

    def _create_display_tab(self) -> QWidget:
        """Create Display tab with drop zone for fields - using tile layout"""
        tab = QWidget()
        tab.setAcceptDrops(True)
        tab.dragEnterEvent = lambda e: self._tab_drag_enter(e, 'display')
        tab.dropEvent = lambda e: self._tab_drop(e, 'display')
        
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Instructions
        instructions = QLabel("Drag fields here to add to SELECT list")
        instructions.setStyleSheet("color: #7f8c8d; font-style: italic; padding: 10px;")
        layout.addWidget(instructions)

        # Scroll area for display fields
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        # Container for display fields with FLOW LAYOUT
        self.display_container = QWidget()
        self.display_layout = FlowLayout(self.display_container, margin=10, spacing=10)

        scroll.setWidget(self.display_container)
        layout.addWidget(scroll)

        return tab
    
    def _tab_drag_enter(self, event, tab_type):
        """Handle drag enter for tabs"""
        if event.mimeData().hasText():
            event.acceptProposedAction()
    
    def _tab_drop(self, event, tab_type):
        """Handle drop on entire tab area"""
        try:
            import json
            field_data = json.loads(event.mimeData().text())
            
            if tab_type == 'display':
                self.add_display_field(field_data)
            elif tab_type == 'criteria':
                self.add_criteria_filter(field_data)
                
            event.acceptProposedAction()
        except Exception as e:
            logger.error(f"Error handling tab drop: {e}")

    def _create_tables_tab(self) -> QWidget:
        """Create Tables tab with FROM and JOIN configuration"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Tables involved section
        tables_label = QLabel("Tables Involved:")
        tables_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(tables_label)

        self.tables_involved_label = QLabel("(None)")
        self.tables_involved_label.setStyleSheet("color: #7f8c8d; padding: 5px 5px 15px 20px;")
        layout.addWidget(self.tables_involved_label)

        # FROM clause section
        from_layout = QHBoxLayout()
        from_label = QLabel("FROM:")
        from_label.setStyleSheet("font-weight: bold;")
        from_layout.addWidget(from_label)

        self.from_table_combo = QComboBox()
        self.from_table_combo.setMinimumWidth(200)
        self.from_table_combo.currentTextChanged.connect(self._on_from_table_changed)
        from_layout.addWidget(self.from_table_combo)
        from_layout.addStretch()

        layout.addLayout(from_layout)

        # JOIN section
        layout.addSpacing(10)
        join_header_layout = QHBoxLayout()
        join_label = QLabel("JOINS:")
        join_label.setStyleSheet("font-weight: bold;")
        join_header_layout.addWidget(join_label)
        join_header_layout.addStretch()

        self.add_join_btn = QPushButton("+ Add Join")
        self.add_join_btn.setObjectName("gold_button")
        self.add_join_btn.clicked.connect(self.add_join)
        join_header_layout.addWidget(self.add_join_btn)

        layout.addLayout(join_header_layout)

        # Scroll area for joins - expands to fill available space
        join_scroll = QScrollArea()
        join_scroll.setWidgetResizable(True)
        join_scroll.setMinimumHeight(300)  # Set minimum height for better visibility
        join_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)

        self.joins_container = QWidget()
        self.joins_layout = QVBoxLayout(self.joins_container)
        self.joins_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.joins_layout.setSpacing(10)

        join_scroll.setWidget(self.joins_container)
        layout.addWidget(join_scroll, 1)  # Add stretch factor to expand

        return tab

    def load_data_sources(self):
        """Load all data sources into cascading menu list and populate DB Queries tree"""
        self.data_sources_list.clear()
        self.db_queries_tree.clear()

        try:
            # Load connections into databases section
            self._load_my_connections()

            # Load recent queries (#1)
            self._load_recent_queries()

            # Load DB Queries into tree widget
            self._load_db_queries_tree()

            logger.info("Data sources loaded with cascading menus and DB queries tree")

        except Exception as e:
            logger.error(f"Error loading data sources: {e}")

    def _load_recent_queries(self):
        """Load and display recently executed queries (#1)"""
        try:
            self.recent_queries_list.clear()

            # Get recent queries from repository
            recent_queries = self.query_repo.get_recent_queries(query_type='DB', limit=10)

            if not recent_queries:
                # Show empty state
                empty_item = QTreeWidgetItem(self.recent_queries_list)
                empty_item.setText(0, "No recent queries")
                empty_item.setForeground(0, Qt.GlobalColor.gray)
                empty_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Not clickable
                return

            # Display each recent query
            from datetime import datetime
            for query in recent_queries:
                item = QTreeWidgetItem(self.recent_queries_list)

                # Format: "Query Name (2m ago, 1.2k rows)"
                last_executed = query.get('last_executed')
                record_count = query.get('record_count', 0)

                # Calculate time ago
                if last_executed:
                    try:
                        exec_time = datetime.fromisoformat(last_executed)
                        now = datetime.now()
                        delta = now - exec_time

                        if delta.days > 0:
                            time_ago = f"{delta.days}d ago"
                        elif delta.seconds >= 3600:
                            time_ago = f"{delta.seconds // 3600}h ago"
                        elif delta.seconds >= 60:
                            time_ago = f"{delta.seconds // 60}m ago"
                        else:
                            time_ago = "just now"
                    except:
                        time_ago = "recently"
                else:
                    time_ago = "unknown"

                # Format record count
                if record_count >= 1000:
                    count_str = f"{record_count/1000:.1f}k rows"
                else:
                    count_str = f"{record_count} rows"

                # Set display text
                item.setText(0, f"⏱ {query['query_name']} ({time_ago}, {count_str})")
                item.setData(0, Qt.ItemDataRole.UserRole, query['query_id'])
                item.setToolTip(0, f"{query['query_name']}\nLast run: {last_executed}\nRows: {record_count}")

            logger.info(f"Loaded {len(recent_queries)} recent queries")

        except Exception as e:
            logger.error(f"Error loading recent queries: {e}")

    def _on_recent_query_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle clicking on a recent query item (#1)"""
        query_id = item.data(0, Qt.ItemDataRole.UserRole)
        if query_id:
            # Load the query (reuse existing logic)
            query_record = self.query_repo.get_query(query_id)
            if query_record:
                self.load_saved_query(query_id, query_record['query_definition'])

    def _load_my_connections(self):
        """Create cascading menu items for each connection type"""
        try:
            # Get ALL connections (not just those with saved tables)
            all_connections = self.conn_repo.get_all_connections()

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
                'FIXED_WIDTH': 'FIXED_WIDTH'
            }

            # Group connections by normalized type
            types_dict = {}
            for conn in all_connections:
                conn_id = conn['connection_id']
                conn_type = conn.get('connection_type', 'Unknown')
                
                # Normalize the connection type
                normalized_type = type_mapping.get(conn_type, conn_type)
                
                if normalized_type not in types_dict:
                    types_dict[normalized_type] = []
                types_dict[normalized_type].append((conn_id, conn))

            # Define the display order
            type_order = ['DB2', 'SQL_SERVER', 'ACCESS', 'EXCEL', 'CSV', 'FIXED_WIDTH']
            
            # Create a menu item for each connection type with cascading menu
            for conn_type in type_order:
                if conn_type not in types_dict:
                    continue
                
                # Create cascading menu for connections of this type
                type_menu = QMenu(self)
                type_menu.setStyleSheet("QMenu { border: 2px solid #555; }")
                
                for conn_id, conn in sorted(types_dict[conn_type], key=lambda x: x[1]['connection_name']):
                    conn_action = QAction(conn['connection_name'], self)
                    conn_action.triggered.connect(
                        lambda checked, cid=conn_id, db=conn['database_name']: 
                        self.load_tables_for_connection(cid, db)
                    )
                    type_menu.addAction(conn_action)
                
                # Add to list
                self.data_sources_list.add_menu_item(conn_type, type_menu)

            logger.info(f"Loaded {len(all_connections)} connections in {len(types_dict)} type groups")

        except Exception as e:
            logger.error(f"Error loading connections: {e}")

    def _load_db_queries_tree(self):
        """Populate the DB Queries tree widget with folders
        
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
                item = QTreeWidgetItem()
                item.setText(0, query['query_name'])
                item.setData(0, Qt.ItemDataRole.UserRole, "db_query")
                item.setData(0, Qt.ItemDataRole.UserRole + 1, query['query_id'])
                item.setData(0, Qt.ItemDataRole.UserRole + 2, query['query_definition'])
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                
                # Add to appropriate folder
                folder_id = query.get('folder_id')
                if folder_id and folder_id in folder_items:
                    folder_items[folder_id].addChild(item)
                else:
                    # If no folder or folder doesn't exist, add to first folder (General)
                    if folder_items:
                        list(folder_items.values())[0].addChild(item)
            
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
            
            logger.info(f"Loaded {len(queries)} DB queries in {len(folders)} folders into tree")
            
        except Exception as e:
            logger.error(f"Error loading DB queries tree: {e}")
    
    def _on_db_query_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on DB Query item to load it"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        
        # Ignore folder clicks, only handle query clicks
        if item_type != "db_query":
            return
        
        query_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
        query_definition = item.data(0, Qt.ItemDataRole.UserRole + 2)
        
        if query_id and query_definition:
            # Save current state first if needed
            if self.current_query_id:
                self._save_current_query_state()
            
            self.load_saved_query(query_id, query_definition)
    
    def _show_db_query_context_menu(self, position):
        """Show context menu for DB Query tree items"""
        item = self.db_queries_tree.itemAt(position)
        if not item:
            # Right-click on empty space - show "New Folder" option
            menu = QMenu(self)
            menu.setStyleSheet("QMenu { border: 2px solid #555; }")
            add_folder_action = menu.addAction("➕ New Folder")
            action = menu.exec(self.db_queries_tree.mapToGlobal(position))
            if action == add_folder_action:
                self._create_new_folder('DB')
            return
        
        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { border: 2px solid #555; }")
        
        # Context menu for query folders
        if item_type == "query_folder":
            folder_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            folder_name = item.text(0).replace("📁 ", "")
            
            add_folder_action = menu.addAction("➕ New Folder")
            menu.addSeparator()
            
            # Don't allow deleting or renaming the General folder
            if folder_name != "General":
                rename_action = menu.addAction("✏️ Rename Folder")
                delete_action = menu.addAction("🗑️ Delete Folder")
            else:
                rename_action = None
                delete_action = None
            
            action = menu.exec(self.db_queries_tree.mapToGlobal(position))
            
            if action == add_folder_action:
                self._create_new_folder('DB')
            elif action == rename_action:
                self._rename_folder(folder_id, item)
            elif action == delete_action:
                self._delete_folder(folder_id)
        
        # Context menu for queries
        elif item_type == "db_query":
            query_id = item.data(0, Qt.ItemDataRole.UserRole + 1)
            query_name = item.text(0)
            
            rename_action = menu.addAction("✏️ Rename")
            copy_action = menu.addAction("📋 Copy")
            delete_action = menu.addAction("🗑️ Delete")
            
            action = menu.exec(self.db_queries_tree.mapToGlobal(position))
            
            if action == rename_action:
                self._rename_query(query_id, query_name, 'DB')
            elif action == copy_action:
                self._copy_query(query_id, query_name, 'DB')
            elif action == delete_action:
                self._delete_query(query_id, query_name, 'DB')

    def _populate_db_queries_menu(self, menu: QMenu):
        """Populate the DB Queries cascading menu"""
        try:
            queries = self.query_repo.get_all_queries(query_type='DB')
            
            for query in queries:
                # Create submenu for each query with Load/Rename/Copy/Delete
                query_submenu = QMenu(query['query_name'], self)
                
                # Load action
                load_action = QAction("📂 Load Query", self)
                load_action.triggered.connect(
                    lambda checked, qid=query['query_id'], qdef=query['query_definition']: 
                    self._load_query_from_menu(qid, qdef)
                )
                query_submenu.addAction(load_action)
                
                query_submenu.addSeparator()
                
                # Rename action
                rename_action = QAction("✏️ Rename", self)
                rename_action.triggered.connect(
                    lambda checked, qid=query['query_id'], qname=query['query_name']: 
                    self._rename_query(qid, qname, 'DB')
                )
                query_submenu.addAction(rename_action)
                
                # Copy action
                copy_action = QAction("📋 Copy", self)
                copy_action.triggered.connect(
                    lambda checked, qid=query['query_id'], qname=query['query_name']: 
                    self._copy_query(qid, qname, 'DB')
                )
                query_submenu.addAction(copy_action)
                
                # Delete action
                delete_action = QAction("🗑️ Delete", self)
                delete_action.triggered.connect(
                    lambda checked, qid=query['query_id'], qname=query['query_name']: 
                    self._delete_query(qid, qname, 'DB')
                )
                query_submenu.addAction(delete_action)
                
                menu.addMenu(query_submenu)
            
            logger.info(f"Loaded {len(queries)} DB queries into menu")
            
        except Exception as e:
            logger.error(f"Error loading DB queries: {e}")
    
    def _load_query_from_menu(self, query_id: int, query_definition: str):
        """Load a saved query from menu selection"""
        # Save current state first if needed
        if self.current_query_id:
            self._save_current_query_state()
        
        self.load_saved_query(query_id, query_definition)

    def _save_current_query_state(self):
        """Save the current query state to memory (not to database)"""
        if self.current_query_id is None:
            return  # Don't save state for unsaved queries
        
        # Capture current UI state
        state = {
            'connection_id': self.current_connection_id,
            'database_name': self.current_database_name,
            'schema_name': self.current_schema_name,
            'from_table': self.from_table_combo.currentText() if self.from_table_combo.currentText() else None,
            'display_fields': self.display_fields.copy(),
            'criteria': [],
            'joins': []
        }
        
        # Capture criteria widget states
        for i in range(self.criteria_layout.count()):
            widget = self.criteria_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'get_filter_value') and hasattr(widget, 'field_data'):
                filter_value = widget.get_filter_value()
                if filter_value:  # Only save if there's a value
                    state['criteria'].append({
                        'field_data': widget.field_data,
                        'filter_config': filter_value
                    })
        
        # Capture join widget states
        for i in range(self.joins_layout.count()):
            widget = self.joins_layout.itemAt(i).widget()
            if widget and hasattr(widget, 'get_join_config'):
                join_config = widget.get_join_config()
                if join_config:  # Only save if configured
                    state['joins'].append(join_config)
        
        # Store in memory
        self.unsaved_query_states[self.current_query_id] = state
        logger.debug(f"Saved state for query {self.current_query_id}: {state}")

    def _rename_query(self, query_id: int, query_name: str, query_type: str):
        """Rename a saved query"""
        try:
            # Prompt for new name
            new_name, ok = QInputDialog.getText(
                self, "Rename Query", 
                f"Enter a new name for '{query_name}':",
                text=query_name
            )
            
            if not ok or not new_name.strip():
                return
            
            new_name = new_name.strip()
            
            # Don't update if name hasn't changed
            if new_name == query_name:
                return
            
            # Update the query name
            self.query_repo.update_query_name(query_id, new_name)
            
            # If this is the currently loaded query, update the label
            if self.current_query_id == query_id:
                self.current_query_name = new_name
                self.query_name_label.setText(new_name)
            
            QMessageBox.information(
                self,
                "Query Renamed",
                f"Query renamed successfully to '{new_name}'!"
            )
            
            # Refresh data sources
            self.load_data_sources()
            self.queries_changed.emit()  # Notify other screens
            
            logger.info(f"Renamed query {query_id} from '{query_name}' to '{new_name}'")
            
        except Exception as e:
            logger.error(f"Error renaming query: {e}")
            QMessageBox.critical(
                self,
                "Rename Failed",
                f"Failed to rename query:\n{str(e)}"
            )

    def _copy_query(self, query_id: int, query_name: str, query_type: str = 'DB'):
        """Copy a saved query"""
        try:
            # Prompt for new name
            new_name, ok = QInputDialog.getText(
                self, "Copy Query", 
                f"Enter a name for the copy of '{query_name}':",
                text=f"{query_name} (Copy)"
            )
            
            if not ok or not new_name.strip():
                return
            
            new_name = new_name.strip()
            
            # Check if a query with this name already exists
            existing_queries = self.query_repo.get_all_queries(query_type='DB')
            existing_names = [q['query_name'] for q in existing_queries]
            
            if new_name in existing_names:
                reply = QMessageBox.question(
                    self,
                    "Query Name Exists",
                    f"A query named '{new_name}' already exists.\n\n"
                    f"Do you want to overwrite it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.No:
                    return
                
                # Find and delete the existing query
                existing_query = next((q for q in existing_queries if q['query_name'] == new_name), None)
                if existing_query:
                    self.query_repo.delete_query(existing_query['query_id'])
                    logger.info(f"Deleted existing query '{new_name}' to overwrite")
            
            # Get the original query
            query_record = self.query_repo.get_query(query_id)
            if not query_record:
                raise Exception("Query not found")
            
            # Save expanded state of folders before refreshing
            expanded_folders = TreeStateManager.save_expanded_folders(self.db_queries_tree)
            
            # Save as new query with new name in the same folder as original
            new_query_id = self.query_repo.save_query(
                query_name=new_name,
                query_type=query_type,
                query_definition=query_record['query_definition'],
                category=query_record.get('category', 'User Queries'),
                folder_id=query_record.get('folder_id')  # Keep in same folder
            )
            
            QMessageBox.information(
                self,
                "Query Copied",
                f"Query copied successfully as '{new_name}'!"
            )
            
            # Refresh data sources
            self.load_data_sources()
            
            # Restore expanded state of folders
            TreeStateManager.restore_expanded_folders(self.db_queries_tree, expanded_folders)
            
            self.queries_changed.emit()  # Notify other screens
            
        except Exception as e:
            logger.error(f"Error copying query: {e}")
            QMessageBox.critical(
                self,
                "Copy Failed",
                f"Failed to copy query:\n{str(e)}"
            )

    def _delete_query(self, query_id: int, query_name: str, query_type: str = 'DB'):
        """Delete a saved query"""
        try:
            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Delete Query",
                f"Are you sure you want to delete the query '{query_name}'?\n\n"
                f"This action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                return
            
            # Save expanded state of folders before refreshing
            expanded_folders = TreeStateManager.save_expanded_folders(self.db_queries_tree)
            
            # Delete from database
            self.query_repo.delete_query(query_id)
            
            # If this was the currently loaded query, clear it
            if self.current_query_id == query_id:
                self.new_query()
            
            # Remove from unsaved states if present
            if query_id in self.unsaved_query_states:
                del self.unsaved_query_states[query_id]
            
            QMessageBox.information(
                self,
                "Query Deleted",
                f"Query '{query_name}' has been deleted."
            )
            
            # Refresh data sources
            self.load_data_sources()
            
            # Restore expanded state of folders
            TreeStateManager.restore_expanded_folders(self.db_queries_tree, expanded_folders)
            
            self.queries_changed.emit()  # Notify other screens
            
        except Exception as e:
            logger.error(f"Error deleting query: {e}")
            QMessageBox.critical(
                self,
                "Delete Failed",
                f"Failed to delete query:\n{str(e)}"
            )
    
    def _show_db_queries_header_context_menu(self, position):
        """Show context menu for DB Queries header label"""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { border: 2px solid #555; }")

        add_folder_action = menu.addAction("➕ New Folder")
        add_folder_action.triggered.connect(lambda: self._create_new_folder('DB'))

        # Get the header widget to map position correctly
        header = self.sender()
        menu.exec(header.mapToGlobal(position))

    def _create_new_folder(self, query_type: str):
        """Create a new query folder"""
        folder_name, ok = QInputDialog.getText(
            self,
            "New Folder",
            "Enter folder name:"
        )
        
        if ok and folder_name.strip():
            try:
                self.query_repo.create_folder(folder_name.strip(), query_type)
                self._load_db_queries_tree()  # Reload to show new folder
                self.queries_changed.emit()  # Notify other screens
                logger.info(f"Created new folder: {folder_name}")
            except Exception as e:
                logger.error(f"Error creating folder: {e}")
                QMessageBox.critical(self, "Error", f"Failed to create folder:\n{str(e)}")
    
    def _rename_folder(self, folder_id: int, item: QTreeWidgetItem):
        """Rename a folder"""
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
                self._load_db_queries_tree()  # Reload to reflect deletion
                self.queries_changed.emit()  # Notify other screens
                logger.info(f"Deleted folder {folder_id}")
            except Exception as e:
                logger.error(f"Error deleting folder: {e}")
                QMessageBox.critical(self, "Error", f"Failed to delete folder:\n{str(e)}")
    
    def _on_query_moved(self, query_id: int, folder_id: int):
        """Handle query being moved to a different folder"""
        try:
            self.query_repo.move_query_to_folder(query_id, folder_id)
            # Reload while preserving user's folder expand/collapse state
            self._load_db_queries_tree()
            self.queries_changed.emit()  # Notify other screens
            logger.info(f"Moved query {query_id} to folder {folder_id}")
        except Exception as e:
            logger.error(f"Error moving query: {e}")
            QMessageBox.critical(self, "Error", f"Failed to move query:\n{str(e)}")
            # Reload to revert visual change
            self._load_db_queries_tree()

    def load_tables_for_connection(self, connection_id: int, database_name: str = None):
        """Load tables for selected connection"""
        self.current_connection_id = connection_id
        
        # Get connection details to determine type and actual database name
        try:
            connection = self.conn_repo.get_connection(connection_id)
            if not connection:
                logger.error(f"Connection {connection_id} not found")
                return
            
            conn_type = connection.get('connection_type', '')
            
            # Use provided database_name or get from connection
            if database_name is None:
                database_name = connection.get('database_name', '') or connection.get('connection_name', 'Unknown')
            
            self.current_database_name = database_name
            
        except Exception as e:
            logger.error(f"Error getting connection details: {e}")
            self.current_database_name = database_name or "Unknown"
            conn_type = ''
        
        # Clear current display
        self.tables_tree.clear()
        self.fields_tree.clear()

        # Update header to show database name
        self.tables_header.setText(f"TABLES")
        
        # For file-based connections (CSV, Excel), show the connection name instead
        if conn_type in ('CSV', 'EXCEL'):
            display_name = connection.get('connection_name', database_name)
            self.database_name_label.setText(f"📄 {display_name}")
        else:
            self.database_name_label.setText(database_name)
        
        self.database_name_label.setVisible(True)

        # Reset fields header
        self.fields_header.setText("FIELDS")

        try:
            # Hide Tables tab for CSV/Excel connections (no JOINs supported)
            if conn_type in ('CSV', 'EXCEL'):
                # Find the Tables tab index and remove it
                for i in range(self.query_tabs.count()):
                    if self.query_tabs.tabText(i) == "Tables":
                        # Store the current tab before removing
                        current_index = self.query_tabs.currentIndex()
                        # Remove the Tables tab
                        self.query_tabs.removeTab(i)
                        # If we were on the Tables tab, switch to Display
                        if current_index == i:
                            self.query_tabs.setCurrentIndex(0)  # Switch to Display
                        break
            else:
                # Show Tables tab for database connections if it's not already there
                tables_exists = False
                for i in range(self.query_tabs.count()):
                    if self.query_tabs.tabText(i) == "Tables":
                        tables_exists = True
                        break
                
                # Add it back if it doesn't exist (it was removed for CSV/Excel)
                if not tables_exists and hasattr(self, 'tables_tab'):
                    self.query_tabs.addTab(self.tables_tab, "Tables")

            # Get saved tables for this connection
            saved_tables = self.saved_table_repo.get_saved_tables(connection_id)

            if not saved_tables:
                self.table_info_label.setText("No saved tables for this connection")
                return

            # Add tables to tree
            for table in saved_tables:
                table_item = QTreeWidgetItem()
                table_name = table['table_name']
                schema_name = table.get('schema_name', '')

                # Display name
                display_name = f"{schema_name}.{table_name}" if schema_name else table_name
                table_item.setText(0, display_name)
                table_item.setData(0, Qt.ItemDataRole.UserRole, "table")
                table_item.setData(0, Qt.ItemDataRole.UserRole + 1, table_name)
                table_item.setData(0, Qt.ItemDataRole.UserRole + 2, schema_name)

                self.tables_tree.addTopLevelItem(table_item)

            self.table_info_label.setText(f"{len(saved_tables)} table(s)")
            logger.info(f"Loaded {len(saved_tables)} tables for connection {connection_id}")

        except Exception as e:
            logger.error(f"Error loading tables: {e}")
            self.table_info_label.setText(f"Error: {str(e)}")

    def _filter_tables(self, search_text: str):
        """Filter tables based on search text"""
        search_text = search_text.lower()
        
        for i in range(self.tables_tree.topLevelItemCount()):
            item = self.tables_tree.topLevelItem(i)
            item_type = item.data(0, Qt.ItemDataRole.UserRole)
            
            if item_type == "table":
                table_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
                schema_name = item.data(0, Qt.ItemDataRole.UserRole + 2)
                
                # Build searchable text (without indicator)
                base_name = f"{schema_name}.{table_name}" if schema_name else table_name
                searchable_text = base_name.lower()
                
                # Show/hide based on search text
                if search_text in searchable_text:
                    item.setHidden(False)
                else:
                    item.setHidden(True)

    def on_table_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle click on table"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        if item_type == "table":
            table_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            schema_name = item.data(0, Qt.ItemDataRole.UserRole + 2)
            self.load_fields_for_table(table_name, schema_name)

    def load_fields_for_table(self, table_name: str, schema_name: str):
        """Load fields for selected table"""
        self.current_table_name = table_name
        self.current_schema_name = schema_name
        self.fields_tree.clear()

        # Keep header simple - no table name
        self.fields_header.setText("Fields")

        try:
            # Get or create metadata
            metadata_id = self.metadata_cache_repo.get_or_create_metadata(
                self.current_connection_id, table_name, schema_name
            )

            # Try cached columns first
            cached_columns = self.metadata_cache_repo.get_cached_columns(metadata_id)

            if cached_columns:
                columns = cached_columns
            else:
                # Load from database
                columns = self.schema_discovery.get_columns(
                    self.current_connection_id, table_name, schema_name
                )

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

                field_item = QTreeWidgetItem()
                field_item.setText(0, f"{col_name} ({col_type})")
                field_item.setData(0, Qt.ItemDataRole.UserRole, "field")
                field_item.setData(0, Qt.ItemDataRole.UserRole + 1, col_name)
                field_item.setData(0, Qt.ItemDataRole.UserRole + 2, col_type)
                field_item.setData(0, Qt.ItemDataRole.UserRole + 3, table_name)
                field_item.setData(0, Qt.ItemDataRole.UserRole + 4, schema_name)

                self.fields_tree.addTopLevelItem(field_item)

            # Update field indicators based on current tab
            self._update_field_indicators()

            self.field_info_label.setText(f"{len(columns)} field(s)")
            logger.info(f"Loaded {len(columns)} fields for table {table_name}")

        except Exception as e:
            logger.error(f"Error loading fields: {e}")
            self.field_info_label.setText(f"Error: {str(e)}")

    def on_field_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double-click on field to add to active tab"""
        item_type = item.data(0, Qt.ItemDataRole.UserRole)

        if item_type != "field":
            return

        # Get field data
        col_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
        col_type = item.data(0, Qt.ItemDataRole.UserRole + 2)
        table_name = item.data(0, Qt.ItemDataRole.UserRole + 3)
        schema_name = item.data(0, Qt.ItemDataRole.UserRole + 4)
        
        field_data = {
            'field_name': col_name,
            'data_type': col_type,
            'table_name': table_name,
            'schema_name': schema_name
        }
        
        # Get the active tab (0=Display, 1=Criteria, 2=Tables)
        active_tab_index = self.query_tabs.currentIndex()
        
        if active_tab_index == 0:  # Display tab
            self.add_display_field(field_data)
        elif active_tab_index == 1:  # Criteria tab
            self.add_criteria_filter(field_data)
        # Tables tab doesn't support adding fields this way

    def add_criteria_filter(self, field_data: dict):
        """Add a filter widget to criteria tab"""
        # Create filter widget based on data type
        filter_widget = CriteriaFilterWidget(field_data, self)
        filter_widget.remove_requested.connect(lambda: self.remove_criteria_filter(filter_widget))

        # Add to the end (bottom) of the layout
        self.criteria_layout.addWidget(filter_widget)
        self.criteria_widgets.append(filter_widget)

        # Update tables involved
        self.update_tables_involved()

        # Enable query buttons
        self.update_query_buttons()

        # Update field indicators
        self._update_field_indicators()

        # Mark query as dirty
        self._mark_query_dirty()

        logger.info(f"Added criteria filter for {field_data['field_name']}")

    def remove_criteria_filter(self, widget):
        """Remove a filter widget from criteria tab"""
        self.criteria_widgets.remove(widget)
        self.criteria_layout.removeWidget(widget)
        widget.deleteLater()

        # Update tables involved
        self.update_tables_involved()

        # Update query buttons
        self.update_query_buttons()

        # Update field indicators
        self._update_field_indicators()

        # Mark query as dirty
        self._mark_query_dirty()

    def add_display_field(self, field_data: dict):
        """Add a field to display tab"""
        # Create display field widget
        display_widget = DisplayFieldWidget(field_data, self)
        display_widget.remove_requested.connect(lambda: self.remove_display_field(display_widget))

        # Add to the end (bottom) of the layout
        self.display_layout.addWidget(display_widget)
        self.display_fields.append(field_data)
        self.display_widgets.append(display_widget)

        # Update tables involved
        self.update_tables_involved()

        # Enable query buttons
        self.update_query_buttons()

        # Update field indicators
        self._update_field_indicators()

        # Mark query as dirty
        self._mark_query_dirty()

        logger.info(f"Added display field: {field_data['field_name']}")

    def remove_display_field(self, widget):
        """Remove a field from display tab"""
        # Find and remove from tracking
        for field_data in self.display_fields:
            if (field_data['field_name'] == widget.field_data['field_name'] and
                field_data['table_name'] == widget.field_data['table_name']):
                self.display_fields.remove(field_data)
                break

        # Remove from widget list
        if widget in self.display_widgets:
            self.display_widgets.remove(widget)

        # Remove widget
        self.display_layout.removeWidget(widget)
        widget.deleteLater()

        # Update tables involved
        self.update_tables_involved()

        # Update query buttons
        self.update_query_buttons()

        # Update field indicators
        self._update_field_indicators()

        # Mark query as dirty
        self._mark_query_dirty()

    def update_tables_involved(self):
        """Update the list of tables involved in the query"""
        tables = set()

        # From criteria filters
        for widget in self.criteria_widgets:
            tables.add(widget.field_data['table_name'])

        # From display fields
        for field_data in self.display_fields:
            tables.add(field_data['table_name'])

        # Include JOIN tables so they are not dropped when user edits criteria/display
        for join_widget in getattr(self, 'joins', []):
            try:
                jt = getattr(join_widget, 'join_table', None) or join_widget.join_table_combo.currentText()
                if jt:
                    tables.add(jt)
            except Exception:
                pass

        self.tables_involved = tables

        # Update visual indicators in tables tree
        self.update_table_indicators()

        # Update Tables tab
        if tables:
            table_list = ", ".join(sorted(tables))
            self.tables_involved_label.setText(table_list)

            # Update FROM combo - PRESERVE current selection
            current_from = self.from_table_combo.currentText()
            print(f"  [update_tables_involved] Current FROM before rebuild: '{current_from}'")
            print(f"  [update_tables_involved] Tables in query: {sorted(tables)}")
            self.from_table_combo.blockSignals(True)  # Block to prevent _on_from_table_changed
            self.from_table_combo.clear()
            for table in sorted(tables):
                self.from_table_combo.addItem(table)

            # Restore the previous selection if it still exists
            if current_from and current_from in tables:
                index = self.from_table_combo.findText(current_from)
                if index >= 0:
                    self.from_table_combo.setCurrentIndex(index)
                    print(f"  [update_tables_involved] Restored FROM to: '{current_from}'")
            else:
                print(f"  [update_tables_involved] Could not restore '{current_from}' - not in tables or empty")
                print(f"  [update_tables_involved] FROM combo now shows: '{self.from_table_combo.currentText()}'")
            self.from_table_combo.blockSignals(False)
        else:
            self.tables_involved_label.setText("(None)")
            self.from_table_combo.clear()
        
        # Update all JOIN widgets with new table list
        self._update_join_widgets_table_list()
    
    def _update_join_widgets_table_list(self):
        """Update the table list and field dropdowns in all JOIN widgets"""
        # Skip during query loading to prevent clearing restored values
        if hasattr(self, '_loading_query') and self._loading_query:
            print("    [_update_join_widgets_table_list] Skipping - query is being loaded")
            return
            
        # Update each JOIN widget
        for join_widget in self.joins:
            # Update the join table combo with available tables
            current_selection = join_widget.join_table_combo.currentText()
            
            # Rebuild the join table combo but preserve current selection even
            # if it is no longer part of tables_involved
            new_items = sorted(self.tables_involved)
            if current_selection and current_selection not in new_items:
                new_items = [current_selection] + new_items
            # Block signals during dropdown rebuild to avoid triggering
            # _on_join_table_changed (which would reload without preservation)
            prev_block = join_widget.join_table_combo.blockSignals(True)
            join_widget.join_table_combo.clear()
            join_widget.join_table_combo.addItems(new_items)
            
            # Try to restore the previous selection if it still exists
            index = join_widget.join_table_combo.findText(current_selection)
            if index >= 0:
                join_widget.join_table_combo.setCurrentIndex(index)
            # Restore original signal blocking state
            join_widget.join_table_combo.blockSignals(prev_block)
            
            # Update the field lists in ON conditions
            join_widget._load_field_lists(preserve_selections=True)
    
    def update_table_indicators(self):
        """Update green dot indicators next to tables that are in use"""
        # Iterate through all table items in the tree
        for i in range(self.tables_tree.topLevelItemCount()):
            item = self.tables_tree.topLevelItem(i)
            item_type = item.data(0, Qt.ItemDataRole.UserRole)
            
            if item_type == "table":
                table_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
                schema_name = item.data(0, Qt.ItemDataRole.UserRole + 2)
                
                # Base display name (without indicator)
                base_name = f"{schema_name}.{table_name}" if schema_name else table_name
                
                # Check if this table is in use
                if table_name in self.tables_involved:
                    # Add green dot indicator
                    item.setText(0, f"🟢 {base_name}")
                    # Make it bold
                    font = item.font(0)
                    font.setBold(True)
                    item.setFont(0, font)
                else:
                    # No indicator
                    item.setText(0, base_name)
                    # Regular font
                    font = item.font(0)
                    font.setBold(False)
                    item.setFont(0, font)

    def _on_query_tab_changed(self, index: int):
        """Handle tab change to update field indicators"""
        self._update_field_indicators()

    def _update_field_indicators(self):
        """Update green dot indicators next to fields based on current tab"""
        # Get current tab index (0=Display, 1=Criteria, 2=Tables)
        current_tab = self.query_tabs.currentIndex()
        
        # Determine which fields to highlight
        if current_tab == 0:  # Display tab
            fields_in_use = {
                (f['field_name'], f['table_name']) 
                for f in self.display_fields
            }
        elif current_tab == 1:  # Criteria tab
            fields_in_use = {
                (w.field_data['field_name'], w.field_data['table_name']) 
                for w in self.criteria_widgets
            }
        else:  # Tables tab or other
            fields_in_use = set()
        
        # Update indicators for all fields in the fields tree
        for i in range(self.fields_tree.topLevelItemCount()):
            item = self.fields_tree.topLevelItem(i)
            field_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
            field_type = item.data(0, Qt.ItemDataRole.UserRole + 2)
            table_name = item.data(0, Qt.ItemDataRole.UserRole + 3)
            
            # Base display name (without indicator)
            base_name = f"{field_name} ({field_type})"
            
            # Check if this field is in use for the current tab
            if (field_name, table_name) in fields_in_use:
                # Add green dot indicator
                item.setText(0, f"🟢 {base_name}")
                # Make it bold
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
            else:
                # No indicator
                item.setText(0, base_name)
                # Regular font
                font = item.font(0)
                font.setBold(False)
                item.setFont(0, font)

    def add_all_fields_to_display(self):
        """Add all fields from current table to Display tab"""
        if not self.current_table_name:
            QMessageBox.information(self, "No Table Selected", 
                                   "Please select a table first.")
            return

        # Get all fields from the fields tree
        field_count = self.fields_tree.topLevelItemCount()
        if field_count == 0:
            QMessageBox.information(self, "No Fields", 
                                   "No fields available for this table.")
            return

        # Add each field to display
        for i in range(field_count):
            item = self.fields_tree.topLevelItem(i)
            field_data = {
                'field_name': item.data(0, Qt.ItemDataRole.UserRole + 1),
                'data_type': item.data(0, Qt.ItemDataRole.UserRole + 2),
                'table_name': item.data(0, Qt.ItemDataRole.UserRole + 3),
                'schema_name': item.data(0, Qt.ItemDataRole.UserRole + 4)
            }
            
            # Check if field already in display
            already_added = any(
                f['field_name'] == field_data['field_name'] and 
                f['table_name'] == field_data['table_name']
                for f in self.display_fields
            )
            
            if not already_added:
                self.add_display_field(field_data)

        logger.info(f"Added all {field_count} fields to display")

    def add_common_fields_to_display(self):
        """Add only common fields from current table to Display tab"""
        if not self.current_table_name:
            QMessageBox.information(self, "No Table Selected", 
                                   "Please select a table first.")
            return

        try:
            # Get metadata
            metadata_id = self.metadata_cache_repo.get_or_create_metadata(
                self.current_connection_id,
                self.current_table_name,
                self.current_schema_name
            )

            # Get cached columns
            cached_columns = self.metadata_cache_repo.get_cached_columns(metadata_id)
            
            if not cached_columns:
                QMessageBox.information(self, "No Cached Data", 
                                       "No cached column data available. Please view this table in My Data first.")
                return

            # Filter for common fields only
            common_fields = [col for col in cached_columns if col.get('is_common', False)]
            
            if not common_fields:
                QMessageBox.information(self, "No Common Fields", 
                                       "No fields are marked as common. Mark fields as common in My Data.")
                return

            # Add each common field to display
            added_count = 0
            for col in common_fields:
                field_data = {
                    'field_name': col['name'],
                    'data_type': col['type'],
                    'table_name': self.current_table_name,
                    'schema_name': self.current_schema_name
                }
                
                # Check if field already in display
                already_added = any(
                    f['field_name'] == field_data['field_name'] and 
                    f['table_name'] == field_data['table_name']
                    for f in self.display_fields
                )
                
                if not already_added:
                    self.add_display_field(field_data)
                    added_count += 1

            logger.info(f"Added {added_count} common fields to display")

        except Exception as e:
            logger.error(f"Error adding common fields: {e}")
            QMessageBox.critical(self, "Error", f"Failed to add common fields:\n{str(e)}")

    def update_query_buttons(self):
        """Enable/disable query buttons based on query state"""
        has_display_fields = len(self.display_fields) > 0
        self.run_query_btn.setEnabled(has_display_fields)
        self.run_options_btn.setEnabled(has_display_fields)
        self.preview_action.setEnabled(has_display_fields)
        self.view_sql_action.setEnabled(has_display_fields)
        self.save_query_btn.setEnabled(has_display_fields)

        # Update complexity indicator (#22)
        self._update_complexity_indicator()

    # ========== Query Complexity Indicator (#22) ==========

    def _calculate_query_complexity(self) -> tuple[str, str, str]:
        """Calculate query complexity level and return (level, color, emoji)

        Returns:
            tuple: (level_name, color_hex, emoji)
                - level_name: "Simple", "Moderate", or "Complex"
                - color_hex: "#28a745" (green), "#ffc107" (yellow), or "#dc3545" (red)
                - emoji: "🟢", "🟡", or "🔴"
        """
        complexity_score = 0

        # Count display fields (1 point each)
        complexity_score += len(self.display_fields)

        # Count criteria filters (2 points each - filters add complexity)
        complexity_score += len(self.criteria_widgets) * 2

        # Count JOIN operations (5 points each - joins significantly increase complexity)
        complexity_score += len(self.joins) * 5

        # Count tables involved (3 points each)
        complexity_score += len(self.tables_involved) * 3

        # Determine complexity level
        if complexity_score <= 10:
            return ("Simple", "#28a745", "🟢")
        elif complexity_score <= 25:
            return ("Moderate", "#ffc107", "🟡")
        else:
            return ("Complex", "#dc3545", "🔴")

    def _update_complexity_indicator(self):
        """Update the query complexity indicator badge (#22)"""
        # Complexity indicator removed - feature disabled
        pass

    # ========== Query Change Detection Methods (#15) ==========

    def _mark_query_dirty(self):
        """Mark query as having unsaved changes"""
        if not self._is_dirty and self.current_query_id:
            self._is_dirty = True
            self._update_window_title()
            logger.debug(f"Query {self.current_query_id} marked as dirty")

    def _has_unsaved_changes(self) -> bool:
        """Check if current query differs from saved version"""
        if not self.current_query_id or not self._original_query_definition:
            return False  # New query or no saved state to compare

        try:
            # Build current query from UI
            current_query = self._build_query_object()
            current_dict = current_query.to_dict()

            # Compare with original
            return current_dict != self._original_query_definition
        except Exception as e:
            logger.error(f"Error checking unsaved changes: {e}")
            return False

    def _update_window_title(self):
        """Update window title to show dirty state"""
        query_name = self.query_name_label.text()

        # Get the main window
        main_window = self.window()
        if main_window:
            if self._is_dirty:
                main_window.setWindowTitle(f"SuiteView - {query_name}*")
            else:
                main_window.setWindowTitle(f"SuiteView - {query_name}")

    def _clear_dirty_state(self):
        """Clear dirty state after save"""
        self._is_dirty = False
        self._update_window_title()
        logger.debug("Query dirty state cleared")

    # ========== End Query Change Detection Methods ==========

    def add_join(self):
        """Add a new JOIN configuration widget"""
        if len(self.tables_involved) < 2:
            QMessageBox.warning(
                self, "Need Multiple Tables",
                "You need at least 2 tables in your query to add a JOIN.\n\n"
                "Add fields from multiple tables to the Criteria or Display tabs first."
            )
            return

        join_widget = JoinWidget(list(self.tables_involved), self)
        join_widget.remove_requested.connect(lambda: self.remove_join(join_widget))

        self.joins_layout.addWidget(join_widget)
        self.joins.append(join_widget)

        # Mark query as dirty
        self._mark_query_dirty()

        logger.info("Added JOIN widget")
        # Update debug panel
        if hasattr(self, '_update_join_debug_panel'):
            self._update_join_debug_panel()

    def remove_join(self, widget):
        """Remove a JOIN widget"""
        self.joins.remove(widget)
        self.joins_layout.removeWidget(widget)
        widget.deleteLater()

        # Mark query as dirty
        self._mark_query_dirty()

        # Update debug panel
        if hasattr(self, '_update_join_debug_panel'):
            self._update_join_debug_panel()

    def _on_from_table_changed(self, table_name):
        """Handle FROM table selection change - update all join widgets' left fields"""
        # Skip if we're loading a query to prevent interference
        if hasattr(self, '_loading_query') and self._loading_query:
            print(f"    [_on_from_table_changed] SKIPPED - Query is being loaded")
            return

        print(f"    [_on_from_table_changed] FROM table changed to: '{table_name}'")

        # Update all existing join widgets to refresh their left field dropdowns
        for join_widget in self.joins:
            if hasattr(join_widget, '_load_field_lists'):
                # Store the from_table on the join widget
                join_widget.from_table = table_name
                # Reload field lists, preserving current selections
                join_widget._load_field_lists(preserve_selections=True)
                print(f"    [_on_from_table_changed] Updated join widget fields")

        # Update debug panel
        if hasattr(self, '_update_join_debug_panel'):
            self._update_join_debug_panel()

    def _preview_query(self):
        """Execute query with 100 row limit for preview"""
        try:
            # Build query object
            query = self._build_query_object()

            # Validate query
            validation_errors = self._validate_query(query)
            if validation_errors:
                QMessageBox.warning(
                    self,
                    "Query Validation Failed",
                    "Please fix the following issues:\n\n" + "\n".join(validation_errors)
                )
                return

            # Show progress dialog
            progress = QProgressDialog("Previewing first 100 rows...", None, 0, 100, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            progress.setAutoClose(True)
            progress.setAutoReset(True)
            progress.setCancelButton(None)  # No cancel button
            progress.setRange(0, 0)  # Indeterminate/busy indicator
            progress.setMinimumWidth(300)
            progress.show()
            QApplication.processEvents()

            try:
                # Execute query with 100 row limit
                logger.info("Executing preview query (100 rows)...")
                df = self._execute_query_with_limit(query, limit=100)
                logger.info(f"Preview query executed successfully, returned {len(df)} rows")

                # Get execution metadata
                metadata = self.query_executor.get_execution_metadata()
                logger.info(f"Retrieved metadata: {metadata}")

                # Close progress
                progress.close()

                # Show results dialog with preview indicator
                logger.info("Creating preview results dialog...")
                results_dialog = QueryResultsDialog(
                    df,
                    metadata['sql'],
                    metadata['execution_time_ms'],
                    self
                )
                # Add preview indicator to window title
                results_dialog.setWindowTitle(f"Query Results - PREVIEW (First 100 Rows) - {self.query_name_label.text()}")
                logger.info("Showing preview results dialog...")
                results_dialog.exec()
                logger.info("Preview results dialog closed")

            except Exception as e:
                progress.close()
                logger.error(f"Error during preview execution or display: {e}", exc_info=True)
                raise

        except Exception as e:
            logger.error(f"Preview query execution failed: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Preview Query Failed",
                f"Failed to execute preview query:\n\n{str(e)}"
            )

    def _execute_query_with_limit(self, query: Query, limit: int = 100):
        """Execute query with row limit"""
        import pandas as pd
        import time

        start_time = time.time()

        # Get connection info
        connection = self.conn_manager.repo.get_connection(query.connection_id)
        connection_type = connection.get('connection_type') if connection else None

        # Build SQL with limit
        sql = self.query_executor._build_sql(query)

        # Add LIMIT clause based on database type
        if connection_type == 'SQL_SERVER':
            # SQL Server uses TOP - insert after SELECT
            if 'SELECT DISTINCT' in sql.upper():
                sql = sql.replace('SELECT DISTINCT', f'SELECT DISTINCT TOP {limit}', 1)
            else:
                sql = sql.replace('SELECT', f'SELECT TOP {limit}', 1)
        elif connection_type == 'DB2':
            # DB2 uses FETCH FIRST
            sql = f"{sql}\nFETCH FIRST {limit} ROWS ONLY"
        elif connection_type == 'ORACLE':
            # Oracle uses ROWNUM or FETCH FIRST (12c+)
            sql = f"{sql}\nFETCH FIRST {limit} ROWS ONLY"
        else:
            # Most others (PostgreSQL, MySQL, SQLite) use LIMIT
            sql = f"{sql}\nLIMIT {limit}"

        # Store the modified SQL
        self.query_executor.last_sql = sql
        logger.info(f"Executing preview query with limit:\n{sql}")

        # Execute based on connection type
        if connection_type == 'DB2':
            df = self.query_executor._execute_db2_query(sql, connection)
        elif connection_type == 'CSV':
            df = self.query_executor._execute_csv_query(query, connection)
            # For CSV, manually limit to 100 rows
            df = df.head(limit)
        else:
            from sqlalchemy import text
            engine = self.conn_manager.get_engine(query.connection_id)
            with engine.connect() as conn:
                df = pd.read_sql_query(text(sql), conn)

        # Update metadata
        self.query_executor.last_execution_time = int((time.time() - start_time) * 1000)
        self.query_executor.last_record_count = len(df)

        return df

    def _filter_fields_tree(self, search_text: str):
        """Filter fields tree based on search text"""
        search_text = search_text.lower().strip()

        # If search is empty, show all items
        if not search_text:
            for i in range(self.fields_tree.topLevelItemCount()):
                table_item = self.fields_tree.topLevelItem(i)
                table_item.setHidden(False)
                for j in range(table_item.childCount()):
                    field_item = table_item.child(j)
                    field_item.setHidden(False)
            return

        # Filter based on search text
        for i in range(self.fields_tree.topLevelItemCount()):
            table_item = self.fields_tree.topLevelItem(i)
            has_matching_child = False

            # Check each field under the table
            for j in range(table_item.childCount()):
                field_item = table_item.child(j)
                field_name = field_item.text(0).lower()

                # Show/hide based on match
                matches = search_text in field_name
                field_item.setHidden(not matches)

                if matches:
                    has_matching_child = True

            # Show table if it has matching children, or hide if no matches
            table_item.setHidden(not has_matching_child)

            # Expand tables that have matches to show the matching fields
            if has_matching_child:
                table_item.setExpanded(True)

    def run_query(self):
        """Execute the query"""
        try:
            # Build query object
            query = self._build_query_object()
            
            # Validate query
            validation_errors = self._validate_query(query)
            if validation_errors:
                QMessageBox.warning(
                    self,
                    "Query Validation Failed",
                    "Please fix the following issues:\n\n" + "\n".join(validation_errors)
                )
                return
            
            # Show progress dialog (#23)
            progress = QProgressDialog("Executing query...", None, 0, 100, self)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)  # Show immediately
            progress.setAutoClose(True)
            progress.setAutoReset(True)
            progress.setCancelButton(None)  # No cancel button
            progress.setRange(0, 0)  # Indeterminate/busy indicator
            progress.setMinimumWidth(300)
            progress.show()
            QApplication.processEvents()

            try:
                # Execute query
                logger.info("Executing query...")
                df = self.query_executor.execute_db_query(query)
                logger.info(f"Query executed successfully, returned {len(df)} rows")

                # Get execution metadata
                metadata = self.query_executor.get_execution_metadata()
                logger.info(f"Retrieved metadata: {metadata}")

                # Update execution stats if this is a saved query
                if self.current_query_id:
                    self.query_repo.update_execution_stats(
                        self.current_query_id,
                        metadata['execution_time_ms'],
                        len(df)
                    )
                    # Refresh recent queries list
                    self._load_recent_queries()

                # Close progress dialog
                progress.close()

                # Show results dialog
                logger.info("Creating results dialog...")
                results_dialog = QueryResultsDialog(
                    df,
                    metadata['sql'],
                    metadata['execution_time_ms'],
                    self
                )
                logger.info("Showing results dialog...")
                results_dialog.exec()
                logger.info("Results dialog closed")

            except Exception as e:
                progress.close()
                logger.error(f"Error during query execution or display: {e}", exc_info=True)
                raise

        except Exception as e:
            logger.error(f"Query execution failed: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Query Execution Failed",
                f"Failed to execute query:\n\n{str(e)}"
            )

    def _show_sql_dialog(self):
        """Show generated SQL in a dialog with copy functionality"""
        try:
            # Build query object from current UI state
            query = self._build_query_object()

            # Validate query has minimum requirements
            if not query.display_fields:
                QMessageBox.warning(
                    self,
                    "Cannot Generate SQL",
                    "Please add at least one display field to generate SQL."
                )
                return

            # Generate SQL using the query executor
            sql = self.query_executor._build_sql(query)

            # Create dialog
            from PyQt6.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QHBoxLayout, QPushButton, QApplication
            from PyQt6.QtGui import QFont

            dialog = QDialog(self)
            dialog.setWindowTitle(f"Generated SQL - {self.query_name_label.text()}")
            dialog.setMinimumSize(700, 500)

            layout = QVBoxLayout(dialog)

            # SQL display with monospace font
            sql_text = QTextEdit()
            sql_text.setPlainText(sql)
            sql_text.setReadOnly(True)
            sql_text.setFont(QFont("Courier New", 10))
            sql_text.setStyleSheet("""
                QTextEdit {
                    background: #2d2d2d;
                    color: #f8f8f2;
                    border: 1px solid #555;
                    padding: 10px;
                }
            """)
            layout.addWidget(sql_text)

            # Buttons
            button_layout = QHBoxLayout()
            button_layout.addStretch()

            copy_btn = QPushButton("📋 Copy to Clipboard")
            copy_btn.setMinimumWidth(150)
            copy_btn.setStyleSheet("""
                QPushButton {
                    background: #28a745;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #218838;
                }
            """)
            copy_btn.clicked.connect(lambda: self._copy_sql_to_clipboard(sql, copy_btn))
            button_layout.addWidget(copy_btn)

            close_btn = QPushButton("Close")
            close_btn.setMinimumWidth(100)
            close_btn.setStyleSheet("""
                QPushButton {
                    background: #6c757d;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #5a6268;
                }
            """)
            close_btn.clicked.connect(dialog.accept)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

            # Show dialog
            dialog.exec()

        except Exception as e:
            logger.error(f"Error generating SQL: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "SQL Generation Failed",
                f"Failed to generate SQL:\n\n{str(e)}"
            )

    def _copy_sql_to_clipboard(self, sql: str, button: QPushButton):
        """Copy SQL to clipboard and show feedback"""
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(sql)

        # Temporarily change button text to show success
        original_text = button.text()
        button.setText("✓ Copied!")
        button.setStyleSheet("""
            QPushButton {
                background: #218838;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
        """)

        # Reset button after 2 seconds
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self._reset_copy_button(button, original_text))

    def _reset_copy_button(self, button: QPushButton, original_text: str):
        """Reset copy button to original state"""
        button.setText(original_text)
        button.setStyleSheet("""
            QPushButton {
                background: #28a745;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #218838;
            }
        """)

    def _build_query_object(self) -> Query:
        """Build Query object from current UI state"""
        query = Query()
        
        # Connection info
        query.connection_id = self.current_connection_id
        
        # Display fields - collect current state from widgets
        display_fields_with_config = []
        for widget in self.display_widgets:
            field_config = widget.field_data.copy()
            # Add UI state
            field_config['alias'] = widget.alias_input.text()
            field_config['aggregation'] = widget.agg_combo.currentText()
            field_config['order'] = widget.order_combo.currentText()
            field_config['having'] = widget.having_input.text()
            field_config['is_expanded'] = widget.is_expanded
            display_fields_with_config.append(field_config)
        
        query.display_fields = display_fields_with_config
        
        # FROM clause
        query.from_table = self.from_table_combo.currentText()
        query.from_schema = self.current_schema_name
        
        # Criteria
        query.criteria = []
        for widget in self.criteria_widgets:
            filter_value = widget.get_filter_value()
            if filter_value:
                criterion = {
                    'table_name': widget.field_data['table_name'],
                    'field_name': widget.field_data['field_name'],
                    'data_type': widget.field_data['data_type'],
                    'schema_name': widget.field_data.get('schema_name', ''),
                }
                
                # Add filter-specific fields based on type
                filter_type = filter_value.get('type')
                
                if filter_type == 'string':
                    criterion['match_type'] = filter_value.get('match_type', 'contains')
                    criterion['value'] = filter_value.get('value', '')
                
                elif filter_type == 'expression':
                    # Expression mode - user provides the entire condition (e.g., "> 100", "LIKE 'A%'")
                    criterion['operator'] = 'EXPRESSION'
                    criterion['value'] = filter_value.get('value', '')
                    
                elif filter_type == 'checkbox_list':
                    # Handle checkbox list - convert to IN clause
                    selected = filter_value.get('selected_values', [])
                    if selected:
                        criterion['operator'] = 'IN'
                        criterion['value'] = selected
                        
                elif filter_type == 'numeric_exact':
                    criterion['operator'] = '='
                    criterion['value'] = filter_value.get('value', '')
                    
                elif filter_type == 'numeric_range':
                    low = filter_value.get('low', '')
                    high = filter_value.get('high', '')
                    if low and high:
                        criterion['operator'] = 'BETWEEN'
                        criterion['value'] = (low, high)
                    elif low:
                        criterion['operator'] = '>='
                        criterion['value'] = low
                    elif high:
                        criterion['operator'] = '<='
                        criterion['value'] = high
                        
                elif filter_type == 'date_exact':
                    criterion['operator'] = '='
                    criterion['value'] = filter_value.get('value', '')
                    
                elif filter_type == 'date_range':
                    start = filter_value.get('start', '')
                    end = filter_value.get('end', '')
                    if start and end:
                        criterion['operator'] = 'BETWEEN'
                        criterion['value'] = (start, end)
                    elif start:
                        criterion['operator'] = '>='
                        criterion['value'] = start
                    elif end:
                        criterion['operator'] = '<='
                        criterion['value'] = end
                
                # Only add if we have a value
                if 'value' in criterion and criterion['value']:
                    query.criteria.append(criterion)
        
        # JOINs
        query.joins = []
        print("\n" + "="*80)
        print("SAVING JOIN CONFIGURATIONS:")
        print("="*80)
        for idx, join_widget in enumerate(self.joins, 1):
            join_config = join_widget.get_join_config()
            print(f"\nJOIN #{idx}:")
            print(f"  Join Type: {join_config['join_type']}")
            print(f"  Join Table: {join_config['join_table']}")
            print(f"  Schema: {self.current_schema_name}")
            print(f"  ON Conditions ({len(join_config['on_conditions'])} total):")
            for cond_idx, condition in enumerate(join_config['on_conditions'], 1):
                print(f"    Condition #{cond_idx}:")
                print(f"      Left Field:  {condition.get('left_field', 'EMPTY')}")
                print(f"      Operator:    {condition.get('operator', 'EMPTY')}")
                print(f"      Right Field: {condition.get('right_field', 'EMPTY')}")
            
            # Save join even if on_conditions is empty (allows saving incomplete joins)
            join_data = {
                'join_type': join_config['join_type'],
                'table_name': join_config['join_table'],
                'schema_name': self.current_schema_name,
                'on_conditions': join_config['on_conditions']
            }
            query.joins.append(join_data)
        print("="*80 + "\n")
        
        return query

    def _validate_query(self, query: Query) -> list:
        """Validate query and return list of error messages with actionable guidance"""
        errors = []
        warnings = []

        # === CRITICAL ERRORS (prevent execution) ===

        if not query.connection_id:
            errors.append("❌ No database connection selected")

        if not query.display_fields:
            errors.append("❌ No display fields selected\n   → Go to Display tab and drag fields to add them")

        if not query.from_table:
            errors.append("❌ No FROM table selected\n   → Go to Tables tab and select a FROM table")

        # Check for multiple tables without JOINs
        tables_in_query = set()
        for field in query.display_fields:
            tables_in_query.add(field['table_name'])
        for criterion in query.criteria:
            tables_in_query.add(criterion['table_name'])

        if len(tables_in_query) > 1 and not query.joins:
            errors.append(
                f"❌ Multiple tables used ({', '.join(sorted(tables_in_query))}) but no JOINs defined\n"
                f"   → Go to Tables tab and click 'Add Join' to define how tables relate"
            )

        # Validate JOIN configurations
        for idx, join in enumerate(query.joins, 1):
            if not join.get('table_name'):
                errors.append(f"❌ JOIN #{idx}: No table selected")

            if not join.get('on_conditions') or len(join['on_conditions']) == 0:
                errors.append(
                    f"❌ JOIN #{idx} ({join.get('table_name', 'unknown')}): No ON conditions defined\n"
                    f"   → Add at least one ON condition to specify how tables join"
                )
            else:
                # Validate each ON condition
                for cond_idx, condition in enumerate(join['on_conditions'], 1):
                    if not condition.get('left_field'):
                        errors.append(f"❌ JOIN #{idx}, Condition #{cond_idx}: Left field is empty")
                    if not condition.get('right_field'):
                        errors.append(f"❌ JOIN #{idx}, Condition #{cond_idx}: Right field is empty")

        # === WARNINGS (query can run but may have issues) ===

        # Check for criteria with no values
        empty_criteria_count = 0
        for criterion in query.criteria:
            if criterion.get('filter_type') in ['text', 'numeric_exact', 'numeric_range', 'date_range']:
                value = criterion.get('value')
                if not value or (isinstance(value, str) and not value.strip()):
                    empty_criteria_count += 1

        if empty_criteria_count > 0:
            warnings.append(
                f"⚠️ {empty_criteria_count} filter(s) have no value set\n"
                f"   → These filters will be ignored. Remove them or set values."
            )

        # Check if query has no criteria (SELECT * warning)
        if not query.criteria:
            warnings.append(
                "⚠️ No filters applied - query will return ALL rows\n"
                "   → Consider adding filters in Criteria tab to limit results"
            )

        # Combine errors and warnings
        messages = []
        if errors:
            messages.append("🚫 ERRORS (must fix before running):\n")
            messages.extend(errors)

        if warnings:
            if errors:
                messages.append("\n")  # Spacing between sections
            messages.append("⚠️  WARNINGS (query can run but check these):\n")
            messages.extend(warnings)

        # Return only errors (warnings are informational)
        # If you want to show warnings too, return messages instead
        return errors

    def save_query(self):
        """Save the query definition"""
        try:
            # Build query object first
            query = self._build_query_object()
            
            # Validate query
            validation_errors = self._validate_query(query)
            if validation_errors:
                QMessageBox.warning(
                    self,
                    "Query Validation Failed",
                    "Please fix the following issues before saving:\n\n" + "\n".join(validation_errors)
                )
                return
            
            # Prompt for query name if not already named
            if not self.current_query_name:
                query_name, ok = QInputDialog.getText(
                    self, "Save Query", "Enter a name for this query:"
                )
                
                if not ok or not query_name.strip():
                    return
                
                query_name = query_name.strip()
            else:
                query_name = self.current_query_name
            
            # Convert Query object to dictionary for storage
            query_dict = {
                'connection_id': query.connection_id,
                'from_table': query.from_table,
                'from_schema': query.from_schema,
                'display_fields': query.display_fields,
                'criteria': query.criteria,
                'joins': query.joins
            }
            
            # Save to database
            query_id = self.query_repo.save_query(
                query_name=query_name,
                query_type='DB',
                query_definition=query_dict,
                category='User Queries'
            )
            
            # Set current query ID and name
            self.current_query_id = query_id
            self.current_query_name = query_name
            
            # Clear unsaved state since we just saved
            if query_id in self.unsaved_query_states:
                del self.unsaved_query_states[query_id]

            # Store new original definition and clear dirty state (#15)
            self._original_query_definition = query.to_dict()
            self._clear_dirty_state()

            # Update display
            self._update_query_name_display()

            QMessageBox.information(
                self,
                "Query Saved",
                f"Query '{query_name}' has been saved successfully!"
            )
            
            # Refresh data sources to show new query (commented out to prevent hang)
            # self.load_data_sources()
            
        except Exception as e:
            logger.error(f"Error saving query: {e}")
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to save query:\n{str(e)}"
            )

    def load_saved_query(self, query_id: int, query_definition_json: str):
        """Load a saved query into the query builder"""
        try:
            import json
            
            # Check if there's an unsaved state for this query
            if query_id in self.unsaved_query_states:
                logger.info(f"Loading unsaved state for query {query_id}")
                self._restore_query_state(query_id, self.unsaved_query_states[query_id])
                return
            
            # Get the full query record to get the name
            query_record = self.query_repo.get_query(query_id)
            if not query_record:
                raise Exception("Query not found")
            
            # Parse the query definition (handle both string and dict)
            if isinstance(query_definition_json, str):
                query_dict = json.loads(query_definition_json)
            elif isinstance(query_definition_json, dict):
                query_dict = query_definition_json
            else:
                raise Exception(f"Invalid query_definition type: {type(query_definition_json)}")
            
            # Clear current query (without confirmation for saved queries)
            self._clear_query_ui()
            
            # Set the current query ID and name
            self.current_query_id = query_id
            self.current_query_name = query_record['query_name']
            self._update_query_name_display()
            
            # Load connection and tables
            connection_id = query_dict.get('connection_id')
            if connection_id:
                # Get connection info
                conn = self.conn_repo.get_connection(connection_id)
                if conn:
                    self.current_connection_id = connection_id
                    # Get database name from connection - handle different connection types
                    db_name = conn.get('database_name') or conn.get('connection_name', 'Unknown')
                    self.current_database_name = db_name
                    self.current_schema_name = query_dict.get('from_schema', '')
                    
                    # Load tables for this connection - this will update the Tables panel UI
                    # Pass the database name explicitly
                    self.load_tables_for_connection(connection_id, db_name)
                    
                    # Force UI update
                    QApplication.processEvents()
                else:
                    logger.warning(f"Connection {connection_id} not found in database")
            
            # NOTE: FROM table will be set AFTER display/criteria/joins are loaded
            # to prevent update_tables_involved() from overwriting it
            saved_from_table = query_dict.get('from_table')

            # Load display fields
            display_fields = query_dict.get('display_fields', [])
            for field in display_fields:
                self.display_fields.append(field)
                # Create the display widget
                display_widget = DisplayFieldWidget(field, self)
                display_widget.remove_requested.connect(lambda w=display_widget: self.remove_display_field(w))
                self.display_layout.addWidget(display_widget)
                self.display_widgets.append(display_widget)
                
                # Restore widget state
                if 'alias' in field:
                    display_widget.alias_input.setText(field['alias'])
                if 'aggregation' in field:
                    index = display_widget.agg_combo.findText(field['aggregation'])
                    if index >= 0:
                        display_widget.agg_combo.setCurrentIndex(index)
                if 'order' in field:
                    index = display_widget.order_combo.findText(field['order'])
                    if index >= 0:
                        display_widget.order_combo.setCurrentIndex(index)
                if 'having' in field:
                    display_widget.having_input.setText(field['having'])
                if 'is_expanded' in field and field['is_expanded']:
                    display_widget.toggle_details()  # Expand if it was expanded
            
            # Load criteria filters
            criteria = query_dict.get('criteria', [])
            for criterion in criteria:
                # Convert saved criterion format back to field_data and filter_config
                field_data = {
                    'table_name': criterion.get('table_name', ''),
                    'field_name': criterion.get('field_name', ''),
                    'data_type': criterion.get('data_type', ''),
                    'schema_name': criterion.get('schema_name', '')
                }
                
                # Convert criterion to filter_config format
                filter_config = self._criterion_to_filter_config(criterion)
                
                if filter_config:
                    # Recreate the filter widget
                    filter_widget = CriteriaFilterWidget(field_data, self)
                    filter_widget.remove_requested.connect(lambda w=filter_widget: self.remove_criteria_filter(w))
                    self.criteria_layout.addWidget(filter_widget)
                    self.criteria_widgets.append(filter_widget)
                    
                    # Restore the filter configuration
                    self._restore_filter_config(filter_widget, filter_config)
            
            # Load JOINs
            joins = query_dict.get('joins', [])
            print("\n" + "="*80)
            print("LOADING JOIN CONFIGURATIONS:")
            print("="*80)
            print(f"Found {len(joins)} JOIN(s) to restore")
            
            # Set flag to prevent field list reloading during restoration
            self._loading_query = True
            
            # Ensure join tables are considered "involved" so dropdowns include them
            try:
                for j in joins:
                    jt = j.get('table_name') or j.get('join_table')
                    if jt:
                        if not hasattr(self, 'tables_involved') or self.tables_involved is None:
                            self.tables_involved = set()
                        self.tables_involved.add(jt)
                # Reflect in UI combos/labels without triggering join widget updates
                self.update_table_indicators()
                if self.tables_involved:
                    table_list = ", ".join(sorted(self.tables_involved))
                    self.tables_involved_label.setText(table_list)
                    # Refill FROM combo but preserve current selection
                    # IMPORTANT: Block signals to prevent _on_from_table_changed during restoration
                    current_from = self.from_table_combo.currentText()
                    self.from_table_combo.blockSignals(True)
                    self.from_table_combo.clear()
                    for table in sorted(self.tables_involved):
                        self.from_table_combo.addItem(table)
                    if current_from:
                        idx = self.from_table_combo.findText(current_from)
                        if idx >= 0:
                            self.from_table_combo.setCurrentIndex(idx)
                    self.from_table_combo.blockSignals(False)
                else:
                    self.tables_involved_label.setText("(None)")
            except Exception as _e:
                # Non-fatal: continue restoration
                print(f"    [RESTORE] Warning: could not pre-add join tables: {_e}")

            for idx, join_config in enumerate(joins, 1):
                print(f"\nJOIN #{idx} from saved data:")
                print(f"  Join Type: {join_config.get('join_type', 'MISSING')}")
                print(f"  Table Name: {join_config.get('table_name', 'MISSING')}")
                print(f"  Schema: {join_config.get('schema_name', 'MISSING')}")
                on_conds = join_config.get('on_conditions', [])
                print(f"  ON Conditions ({len(on_conds)} total):")
                for cond_idx, condition in enumerate(on_conds, 1):
                    print(f"    Condition #{cond_idx}:")
                    print(f"      Left Field:  {condition.get('left_field', 'MISSING')}")
                    print(f"      Operator:    {condition.get('operator', 'MISSING')}")
                    print(f"      Right Field: {condition.get('right_field', 'MISSING')}")
                
                # Update tables_involved first (needed by JoinWidget)
                self.update_tables_involved()
                
                # Create the JOIN widget
                join_widget = JoinWidget(list(self.tables_involved), self)
                join_widget.remove_requested.connect(lambda w=join_widget: self.remove_join(w))
                self.joins_layout.addWidget(join_widget)
                self.joins.append(join_widget)
                
                # Restore the JOIN configuration
                print(f"  Restoring JOIN #{idx}...")
                self._restore_join_config(join_widget, join_config)
            print("="*80 + "\n")

            # Update tables involved and buttons BEFORE clearing the loading flag
            # This prevents _on_from_table_changed from firing during the FROM combo update
            self.update_tables_involved()
            self.update_query_buttons()

            # NOW set the FROM table (AFTER update_tables_involved has run)
            # This ensures it doesn't get overwritten
            if saved_from_table:
                print(f"  [FINAL] Setting FROM table to saved value: '{saved_from_table}'")
                self.from_table_combo.blockSignals(True)
                index = self.from_table_combo.findText(saved_from_table)
                if index >= 0:
                    self.from_table_combo.setCurrentIndex(index)
                    print(f"  [FINAL] FROM table set successfully to: '{self.from_table_combo.currentText()}'")
                else:
                    print(f"  [FINAL] WARNING: Could not find '{saved_from_table}' in FROM combo")
                self.from_table_combo.blockSignals(False)

            # NOW clear the loading flag (after all updates are complete)
            self._loading_query = False

            # Refresh debug panel
            if hasattr(self, '_update_join_debug_panel'):
                self._update_join_debug_panel()
            
            # Enable reset button since we have a loaded query
            self.reset_query_btn.setEnabled(True)

            # Store original query definition for change detection (#15)
            try:
                current_query = self._build_query_object()
                self._original_query_definition = current_query.to_dict()
                self._is_dirty = False
                self._update_window_title()
                logger.debug(f"Stored original query definition for change detection")
            except Exception as e:
                logger.warning(f"Could not store original query definition: {e}")

            logger.info(f"Loaded query {query_id}: {query_record['query_name']}")

        except Exception as e:
            logger.error(f"Error loading saved query: {e}")
            QMessageBox.critical(
                self,
                "Load Failed",
                f"Failed to load query:\n{str(e)}"
            )
    
    def _restore_query_state(self, query_id: int, state: dict):
        """Restore query UI from saved state"""
        try:
            # Get the query name from database
            query_record = self.query_repo.get_query(query_id)
            if not query_record:
                raise Exception("Query not found")
            
            # Clear current query UI
            self._clear_query_ui()
            
            # Set query ID and name
            self.current_query_id = query_id
            self.current_query_name = query_record['query_name']
            self._update_query_name_display()
            
            # Restore connection info
            self.current_connection_id = state.get('connection_id')
            self.current_database_name = state.get('database_name')
            self.current_schema_name = state.get('schema_name')
            
            # Load tables if we have connection info
            if self.current_connection_id and self.current_database_name:
                self.load_tables_for_connection(self.current_connection_id, self.current_database_name)
            
            # Restore FROM table (block signals to prevent premature join widget updates)
            from_table = state.get('from_table')
            if from_table:
                self.from_table_combo.blockSignals(True)
                index = self.from_table_combo.findText(from_table)
                if index >= 0:
                    self.from_table_combo.setCurrentIndex(index)
                self.from_table_combo.blockSignals(False)
            
            # Restore display fields
            for field in state.get('display_fields', []):
                self.display_fields.append(field)
                # Create the display widget
                display_widget = DisplayFieldWidget(field, self)
                display_widget.remove_requested.connect(lambda w=display_widget: self.remove_display_field(w))
                self.display_layout.addWidget(display_widget)
                self.display_widgets.append(display_widget)
                
                # Restore widget state
                if 'alias' in field:
                    display_widget.alias_input.setText(field['alias'])
                if 'aggregation' in field:
                    index = display_widget.agg_combo.findText(field['aggregation'])
                    if index >= 0:
                        display_widget.agg_combo.setCurrentIndex(index)
                if 'order' in field:
                    index = display_widget.order_combo.findText(field['order'])
                    if index >= 0:
                        display_widget.order_combo.setCurrentIndex(index)
                if 'having' in field:
                    display_widget.having_input.setText(field['having'])
                if 'is_expanded' in field and field['is_expanded']:
                    display_widget.toggle_details()  # Expand if it was expanded
            
            # Restore criteria filters
            for criterion in state.get('criteria', []):
                # Recreate the filter widget
                filter_widget = CriteriaFilterWidget(criterion['field_data'], self)
                filter_widget.remove_requested.connect(lambda w=filter_widget: self.remove_criteria_filter(w))
                self.criteria_layout.addWidget(filter_widget)
                self.criteria_widgets.append(filter_widget)
                
                # Restore the filter configuration
                self._restore_filter_config(filter_widget, criterion['filter_config'])
            
            # Restore JOINs
            join_state_list = state.get('joins', [])
            # Make sure join tables are included before creating widgets
            try:
                for j in join_state_list:
                    jt = j.get('table_name') or j.get('join_table')
                    if jt:
                        if not hasattr(self, 'tables_involved') or self.tables_involved is None:
                            self.tables_involved = set()
                        self.tables_involved.add(jt)
                self.update_table_indicators()
                if self.tables_involved:
                    table_list = ", ".join(sorted(self.tables_involved))
                    self.tables_involved_label.setText(table_list)
                    # IMPORTANT: Block signals to prevent _on_from_table_changed during restoration
                    current_from = self.from_table_combo.currentText()
                    self.from_table_combo.blockSignals(True)
                    self.from_table_combo.clear()
                    for table in sorted(self.tables_involved):
                        self.from_table_combo.addItem(table)
                    if current_from:
                        idx = self.from_table_combo.findText(current_from)
                        if idx >= 0:
                            self.from_table_combo.setCurrentIndex(idx)
                    self.from_table_combo.blockSignals(False)
                else:
                    self.tables_involved_label.setText("(None)")
            except Exception as _e:
                print(f"    [RESTORE] Warning: could not pre-add join tables (state): {_e}")

            for join_config in join_state_list:
                # Update tables_involved first (needed by JoinWidget)
                self.update_tables_involved()
                
                # Create the JOIN widget
                join_widget = JoinWidget(list(self.tables_involved), self)
                join_widget.remove_requested.connect(lambda w=join_widget: self.remove_join(w))
                self.joins_layout.addWidget(join_widget)
                self.joins.append(join_widget)
                
                # Restore the JOIN configuration
                self._restore_join_config(join_widget, join_config)
            
            # Update tables involved and buttons
            self.update_tables_involved()
            self.update_query_buttons()

            # Refresh debug panel
            if hasattr(self, '_update_join_debug_panel'):
                self._update_join_debug_panel()
            
            logger.info(f"Restored unsaved state for query {query_id}")
            
        except Exception as e:
            logger.error(f"Error restoring query state: {e}")
            QMessageBox.critical(
                self,
                "Restore Failed",
                f"Failed to restore query state:\n{str(e)}"
            )
    
    def _clear_query_ui(self):
        """Clear the query builder UI without confirmation"""
        # Clear all criteria widgets
        for widget in self.criteria_widgets.copy():
            self.remove_criteria_filter(widget)
        
        # Clear all display fields
        for field_data in self.display_fields.copy():
            # Find the widget
            for i in range(self.display_layout.count()):
                widget = self.display_layout.itemAt(i).widget()
                if isinstance(widget, DisplayFieldWidget) and widget.field_data == field_data:
                    self.remove_display_field(widget)
                    break
        
        # Ensure display_widgets is cleared
        self.display_widgets.clear()
        
        # Clear all joins
        for widget in self.joins.copy():
            self.remove_join(widget)
        
        # Reset FROM table
        self.from_table_combo.clear()
        
        # Note: We don't clear tables_tree or database_name_label here
        # Those will be updated when loading the new query's connection

    def _update_join_debug_panel(self):
        """Populate the green JOIN debug panel with available fields and selections."""
        # Only proceed if the panel exists
        if not hasattr(self, 'join_debug_text') or self.join_debug_text is None:
            return

        try:
            lines = []
            # Header context
            tables = sorted(list(self.tables_involved)) if hasattr(self, 'tables_involved') and self.tables_involved else []
            from_table = self.from_table_combo.currentText() if hasattr(self, 'from_table_combo') else ''
            lines.append(f"Tables Involved: {', '.join(tables) if tables else '(none)'}")
            lines.append(f"FROM: {from_table or '(none)'}")

            if not self.joins:
                lines.append("No JOIN widgets.")
            else:
                for j_idx, jw in enumerate(self.joins, 1):
                    # Determine tables for this join
                    jw_from = jw.from_table or from_table or ''
                    jw_join = jw.join_table or (jw.join_table_combo.currentText() if hasattr(jw, 'join_table_combo') else '')
                    lines.append(f"\nJOIN #{j_idx}: FROM={jw_from or '(none)'} JOIN={jw_join or '(none)'}")

                    # Get fields using the widget's accessor (safe with try/except)
                    try:
                        left_fields = jw._get_table_fields(jw_from) if jw_from else []
                    except Exception as _e:
                        left_fields = []
                        lines.append(f"  Left fields error: {_e}")
                    try:
                        right_fields = jw._get_table_fields(jw_join) if jw_join else []
                    except Exception as _e:
                        right_fields = []
                        lines.append(f"  Right fields error: {_e}")

                    # Show counts and sample
                    lines.append(f"  Left fields ({len(left_fields)}): " + (", ".join(left_fields[:10]) if left_fields else '(none)'))
                    lines.append(f"  Right fields ({len(right_fields)}): " + (", ".join(right_fields[:10]) if right_fields else '(none)'))

                    # Current ON selections
                    for r_idx, row in enumerate(jw.on_condition_rows, 1):
                        lf = row['left_field_combo'].currentText()
                        op = row.get('operator_combo').currentText() if row.get('operator_combo') else '='
                        rf = row['right_field_combo'].currentText()
                        lines.append(f"  ON[{r_idx}]: {lf or '(empty)'} {op} {rf or '(empty)'}")

            self.join_debug_text.setPlainText("\n".join(lines))
        except Exception as e:
            self.join_debug_text.setPlainText(f"[Debug error] {e}")
    
    def _criterion_to_filter_config(self, criterion: dict) -> dict:
        """Convert saved criterion format to filter_config format"""
        operator = criterion.get('operator', '')
        value = criterion.get('value')
        match_type = criterion.get('match_type', '')
        
        # String filters (have match_type)
        if match_type:
            return {
                'type': 'string',
                'match_type': match_type,
                'value': value or ''
            }
        
        # IN operator means checkbox list
        elif operator == 'IN':
            return {
                'type': 'checkbox_list',
                'selected_values': value if isinstance(value, list) else []
            }
        
        # BETWEEN operator
        elif operator == 'BETWEEN':
            if isinstance(value, (tuple, list)) and len(value) == 2:
                # Check if it's a date or numeric based on data_type
                data_type = criterion.get('data_type', '').upper()
                if any(t in data_type for t in ['DATE', 'TIME', 'TIMESTAMP']):
                    return {
                        'type': 'date_range',
                        'start': value[0],
                        'end': value[1]
                    }
                else:
                    return {
                        'type': 'numeric_range',
                        'low': str(value[0]),
                        'high': str(value[1])
                    }
        
        # Comparison operators for numeric/date
        elif operator in ('=', '>=', '<=', '>', '<'):
            data_type = criterion.get('data_type', '').upper()
            
            # Date types
            if any(t in data_type for t in ['DATE', 'TIME', 'TIMESTAMP']):
                if operator == '=':
                    return {
                        'type': 'date_exact',
                        'value': value or ''
                    }
                elif operator == '>=':
                    return {
                        'type': 'date_range',
                        'start': value or '',
                        'end': ''
                    }
                elif operator == '<=':
                    return {
                        'type': 'date_range',
                        'start': '',
                        'end': value or ''
                    }
            
            # Numeric types
            else:
                if operator == '=':
                    return {
                        'type': 'numeric_exact',
                        'value': str(value) if value else ''
                    }
                elif operator == '>=':
                    return {
                        'type': 'numeric_range',
                        'low': str(value) if value else '',
                        'high': ''
                    }
                elif operator == '<=':
                    return {
                        'type': 'numeric_range',
                        'low': '',
                        'high': str(value) if value else ''
                    }
        
        # Default fallback
        return {
            'type': 'text',
            'value': str(value) if value else ''
        }
    
    def _restore_filter_config(self, filter_widget: 'CriteriaFilterWidget', filter_config: dict):
        """Restore filter widget configuration from saved state"""
        if not filter_config:
            return
        
        filter_type = filter_config.get('type')
        
        try:
            if filter_type == 'string':
                if hasattr(filter_widget, 'match_type_combo') and hasattr(filter_widget, 'filter_input'):
                    # Map match_type back to display text
                    match_type_map = {
                        'exact': 'Exact',
                        'starts_with': 'Starts',
                        'ends_with': 'Ends',
                        'contains': 'Contains'
                    }
                    display_text = match_type_map.get(filter_config.get('match_type', 'exact'), 'Exact')
                    filter_widget.match_type_combo.setCurrentText(display_text)
                    filter_widget.filter_input.setText(filter_config.get('value', ''))
            
            elif filter_type == 'numeric_exact':
                if hasattr(filter_widget, 'exact_input'):
                    filter_widget.exact_input.setText(str(filter_config.get('value', '')))
            
            elif filter_type == 'numeric_range':
                if hasattr(filter_widget, 'range_low_input') and hasattr(filter_widget, 'range_high_input'):
                    filter_widget.range_low_input.setText(str(filter_config.get('low', '')))
                    filter_widget.range_high_input.setText(str(filter_config.get('high', '')))
            
            elif filter_type == 'date_exact':
                if hasattr(filter_widget, 'exact_date_input'):
                    from PyQt6.QtCore import QDate
                    date_str = filter_config.get('value', '')
                    if date_str:
                        date = QDate.fromString(date_str, 'yyyy-MM-dd')
                        filter_widget.exact_date_input.setDate(date)
            
            elif filter_type == 'date_range':
                if hasattr(filter_widget, 'date_range_start') and hasattr(filter_widget, 'date_range_end'):
                    from PyQt6.QtCore import QDate
                    start_str = filter_config.get('start', '')
                    end_str = filter_config.get('end', '')
                    if start_str:
                        start_date = QDate.fromString(start_str, 'yyyy-MM-dd')
                        filter_widget.date_range_start.setDate(start_date)
                    if end_str:
                        end_date = QDate.fromString(end_str, 'yyyy-MM-dd')
                        filter_widget.date_range_end.setDate(end_date)
            
            elif filter_type == 'checkbox_list':
                selected_values = filter_config.get('selected_values', [])
                # Store selected values directly (no checkboxes anymore)
                if hasattr(filter_widget, 'selected_values'):
                    filter_widget.selected_values = selected_values
                else:
                    filter_widget.selected_values = selected_values
                
                # Update list button style to reflect loaded state
                if hasattr(filter_widget, '_update_list_button_style'):
                    filter_widget._update_list_button_style()
                
                # IMPORTANT: Update the combobox and input box state to show "List" and disabled styling
                if hasattr(filter_widget, '_update_selected_values') and hasattr(filter_widget, 'unique_values'):
                    # Call the update method to apply the UI state
                    filter_widget._update_selected_values(selected_values)
                
                # Also restore text filter if present
                if 'text_value' in filter_config and hasattr(filter_widget, 'filter_input'):
                    filter_widget.filter_input.setText(filter_config.get('text_value', ''))
                if 'text_match' in filter_config and hasattr(filter_widget, 'match_type_combo'):
                    filter_widget.match_type_combo.setCurrentText(filter_config.get('text_match', 'Exact'))
            
            elif filter_type == 'text':
                if hasattr(filter_widget, 'filter_input'):
                    filter_widget.filter_input.setText(filter_config.get('value', ''))
            
            # Check for custom criteria and restore it
            if 'custom_criteria' in filter_config:
                custom_text = filter_config.get('custom_criteria', '').strip()
                if hasattr(filter_widget, 'custom_criteria_text'):
                    filter_widget.custom_criteria_text = custom_text
        
        except Exception as e:
            logger.warning(f"Could not fully restore filter config: {e}")
    
    def _restore_join_config(self, join_widget: 'JoinWidget', join_config: dict):
        """Restore JOIN widget configuration from saved state"""
        if not join_config:
            print("    [RESTORE] No join_config provided!")
            return
        
        try:
            print("    [RESTORE] Starting restoration...")
            
            # Disconnect the signal that triggers field list reload
            if hasattr(join_widget, 'join_table_combo'):
                try:
                    join_widget.join_table_combo.currentTextChanged.disconnect()
                    print("    [RESTORE] Disconnected join_table_combo signal")
                except:
                    pass  # Already disconnected or no connections
            
            # Set join type
            if hasattr(join_widget, 'join_type_combo'):
                join_type = join_config.get('join_type', 'INNER JOIN')
                join_widget.join_type_combo.setCurrentText(join_type)
                print(f"    [RESTORE] Set join type: {join_type}")
            
            # Set join table - handle both 'table_name' (saved format) and 'join_table' (legacy)
            if hasattr(join_widget, 'join_table_combo'):
                table_name = join_config.get('table_name') or join_config.get('join_table', '')
                if table_name:
                    index = join_widget.join_table_combo.findText(table_name)
                    print(f"    [RESTORE] Looking for table '{table_name}' - found at index {index}")
                    if index < 0:
                        # If the table isn't present (e.g., not yet in tables_involved), add it
                        join_widget.join_table_combo.addItem(table_name)
                        index = join_widget.join_table_combo.findText(table_name)
                        print(f"    [RESTORE] Added missing table '{table_name}' to dropdown at index {index}")
                        # Also ensure parent knows about this table to prevent later clearing
                        if getattr(join_widget, 'parent_screen', None) is not None:
                            try:
                                if not hasattr(join_widget.parent_screen, 'tables_involved') or join_widget.parent_screen.tables_involved is None:
                                    join_widget.parent_screen.tables_involved = set()
                                join_widget.parent_screen.tables_involved.add(table_name)
                            except Exception as _e:
                                print(f"    [RESTORE] Warning: couldn't add '{table_name}' to tables_involved: {_e}")
                    if index >= 0:
                        # Block signals temporarily to prevent premature field list reload
                        join_widget.join_table_combo.blockSignals(True)
                        join_widget.join_table_combo.setCurrentIndex(index)
                        join_widget.join_table_combo.blockSignals(False)
                        
                        # Manually set the join_table attribute
                        join_widget.join_table = table_name
                        
                        print(f"    [RESTORE] Set join table to: {table_name}")
                        
                        # Manually load field lists for all rows WITHOUT triggering the normal change handler
                        if hasattr(join_widget, 'parent_screen') and join_widget.parent_screen:
                            from_table = join_widget.parent_screen.from_table_combo.currentText()
                            print(f"    [RESTORE] Manually loading fields - FROM: {from_table}, JOIN: {table_name}")
                            
                            for row_idx, row_data in enumerate(join_widget.on_condition_rows):
                                # Load FROM table fields
                                if from_table and hasattr(join_widget, '_get_table_fields'):
                                    fields = join_widget._get_table_fields(from_table)
                                    row_data['left_field_combo'].clear()
                                    row_data['left_field_combo'].addItems(fields)
                                    print(f"    [RESTORE]   Row {row_idx+1}: Loaded {len(fields)} left fields")
                                
                                # Load JOIN table fields
                                if table_name and hasattr(join_widget, '_get_table_fields'):
                                    fields = join_widget._get_table_fields(table_name)
                                    row_data['right_field_combo'].clear()
                                    row_data['right_field_combo'].addItems(fields)
                                    print(f"    [RESTORE]   Row {row_idx+1}: Loaded {len(fields)} right fields")
                    else:
                        print(f"    [RESTORE] WARNING: Table '{table_name}' not found in dropdown!")
            
            # Restore ON conditions - AFTER field lists are loaded
            on_conditions = join_config.get('on_conditions', [])
            print(f"    [RESTORE] Restoring {len(on_conditions)} ON condition(s)")
            
            # The first condition row already exists, populate it
            if on_conditions and hasattr(join_widget, 'on_condition_rows') and join_widget.on_condition_rows:
                first_row = join_widget.on_condition_rows[0]
                first_condition = on_conditions[0]
                print(f"    [RESTORE] Condition #1:")
                
                if 'left_field_combo' in first_row:
                    left_field = first_condition.get('left_field', '')
                    left_combo = first_row['left_field_combo']
                    print(f"      Left combo has {left_combo.count()} items")
                    idx = left_combo.findText(left_field)
                    print(f"      Looking for left field '{left_field}' - found at index {idx}")
                    if idx >= 0:
                        left_combo.blockSignals(True)  # Block auto-populate signal
                        left_combo.setCurrentIndex(idx)
                        left_combo.blockSignals(False)
                        print(f"      [OK] Set left field to: {left_field}")
                    else:
                        print(f"      [ERROR] Left field '{left_field}' not found in dropdown!")

                if 'operator_combo' in first_row:
                    operator = first_condition.get('operator', '=')
                    idx = first_row['operator_combo'].findText(operator)
                    if idx >= 0:
                        first_row['operator_combo'].setCurrentIndex(idx)
                        print(f"      [OK] Set operator to: {operator}")
                    else:
                        print(f"      [ERROR] Operator '{operator}' not found!")

                if 'right_field_combo' in first_row:
                    right_field = first_condition.get('right_field', '')
                    right_combo = first_row['right_field_combo']
                    print(f"      Right combo has {right_combo.count()} items")
                    idx = right_combo.findText(right_field)
                    print(f"      Looking for right field '{right_field}' - found at index {idx}")
                    if idx >= 0:
                        right_combo.setCurrentIndex(idx)
                        print(f"      [OK] Set right field to: {right_field}")
                    else:
                        print(f"      [ERROR] Right field '{right_field}' not found in dropdown!")
            
            # Add and populate additional condition rows
            for i in range(1, len(on_conditions)):
                print(f"    [RESTORE] Condition #{i+1}:")
                condition = on_conditions[i]

                # Add new row
                if hasattr(join_widget, '_add_on_condition_row'):
                    join_widget._add_on_condition_row()
                    print(f"      Added new ON condition row")

                    # CRITICAL: Load fields into the new row BEFORE setting values
                    if i < len(join_widget.on_condition_rows):
                        row = join_widget.on_condition_rows[i]

                        # Populate left field combo (FROM table)
                        if from_table and hasattr(join_widget, '_get_table_fields'):
                            fields = join_widget._get_table_fields(from_table)
                            row['left_field_combo'].clear()
                            row['left_field_combo'].addItems(fields)
                            print(f"      Loaded {len(fields)} left fields into row {i+1}")

                        # Populate right field combo (JOIN table)
                        if table_name and hasattr(join_widget, '_get_table_fields'):
                            fields = join_widget._get_table_fields(table_name)
                            row['right_field_combo'].clear()
                            row['right_field_combo'].addItems(fields)
                            print(f"      Loaded {len(fields)} right fields into row {i+1}")

                        # NOW set the saved values
                        if 'left_field_combo' in row:
                            left_field = condition.get('left_field', '')
                            left_combo = row['left_field_combo']
                            print(f"      DEBUG: Before setting - combo has {left_combo.count()} items, current='{left_combo.currentText()}'")
                            idx = left_combo.findText(left_field)
                            if idx >= 0:
                                left_combo.blockSignals(True)  # Block auto-populate signal
                                left_combo.setCurrentIndex(idx)
                                left_combo.blockSignals(False)
                                print(f"      [OK] Set left field to: {left_field}, now current='{left_combo.currentText()}'")
                            else:
                                print(f"      [ERROR] Left field '{left_field}' not found!")

                        if 'operator_combo' in row:
                            operator = condition.get('operator', '=')
                            idx = row['operator_combo'].findText(operator)
                            if idx >= 0:
                                row['operator_combo'].setCurrentIndex(idx)
                                print(f"      [OK] Set operator to: {operator}")
                            else:
                                print(f"      [ERROR] Operator '{operator}' not found!")

                        if 'right_field_combo' in row:
                            right_field = condition.get('right_field', '')
                            idx = row['right_field_combo'].findText(right_field)
                            if idx >= 0:
                                row['right_field_combo'].setCurrentIndex(idx)
                                print(f"      [OK] Set right field to: {right_field}")
                            else:
                                print(f"      [ERROR] Right field '{right_field}' not found!")
            
            # Reconnect the signal after restoration is complete
            if hasattr(join_widget, 'join_table_combo') and hasattr(join_widget, '_on_join_table_changed'):
                join_widget.join_table_combo.currentTextChanged.connect(join_widget._on_join_table_changed)
                print("    [RESTORE] Reconnected join_table_combo signal")
        
        except Exception as e:
            print(f"    [RESTORE] ERROR: {e}")
            logger.warning(f"Could not fully restore JOIN config: {e}")
        
        # Update debug panel if available
        try:
            if self and hasattr(self, 'joins') and hasattr(self, '_update_join_debug_panel'):
                self._update_join_debug_panel()
        except Exception:
            pass

    def new_query(self):
        """Clear current query and start fresh"""
        # Save current query state if it's a saved query with changes
        if self.current_query_id is not None:
            self._save_current_query_state()
        
        # Confirm if there are unsaved changes
        if self.display_fields or self.criteria_widgets or self.joins:
            reply = QMessageBox.question(
                self,
                "New Query",
                "Are you sure you want to start a new query?\n\n"
                "All unsaved changes will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                return
        
        # Clear the UI
        self._clear_query_ui()
        
        # Reset tables involved
        self.tables_involved = set()
        self.tables_involved_label.setText("(None)")
        
        # Clear fields panel
        self.fields_tree.clear()
        self.field_info_label.setText("Select a table to view fields")
        
        # Reset current state
        self.current_table_name = None
        self.current_schema_name = None
        self.current_query_name = None
        self.current_query_id = None
        
        # Update query name display and reset button
        self._update_query_name_display()
        self.reset_query_btn.setEnabled(False)
        
        logger.info("Started new query - cleared all previous state")
    
    def reset_query(self):
        """Reset current query to last saved version from disk"""
        if self.current_query_id is None:
            QMessageBox.information(
                self,
                "No Query Loaded",
                "There is no saved query to reset to.\n\n"
                "Please load a saved query first."
            )
            return
        
        # Confirm reset
        reply = QMessageBox.question(
            self,
            "Reset Query",
            f"Are you sure you want to reset to the last saved version of '{self.current_query_name}'?\n\n"
            "All unsaved changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.No:
            return
        
        # Get the query from database
        query_record = self.query_repo.get_query(self.current_query_id)
        if not query_record:
            QMessageBox.critical(
                self,
                "Error",
                "Failed to load query from database."
            )
            return
        
        # Clear any unsaved state for this query
        if self.current_query_id in self.unsaved_query_states:
            del self.unsaved_query_states[self.current_query_id]
        
        # Reload the query from disk
        self.load_saved_query(self.current_query_id, query_record['query_definition'])
        
        logger.info(f"Reset query {self.current_query_id} to last saved version")

    def _update_query_name_display(self):
        """Update the query name label"""
        if self.current_query_name:
            self.query_name_label.setText(self.current_query_name)
            self.query_name_label.setStyleSheet("""
                QLabel {
                    color: #2c3e50;
                    font-size: 18px;
                    font-weight: bold;
                    padding: 5px 20px;
                }
            """)
        else:
            self.query_name_label.setText("unnamed")
            self.query_name_label.setStyleSheet("""
                QLabel {
                    color: #95a5a6;
                    font-size: 16px;
                    font-style: italic;
                    padding: 5px 20px;
                }
            """)


class DropZoneWidget(QWidget):
    """Drop zone widget for drag-and-drop fields"""

    field_dropped = pyqtSignal(dict)  # Emits field data when dropped

    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        self.message = message
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setAcceptDrops(True)
        self.setMinimumHeight(100)
        self.setStyleSheet("""
            DropZoneWidget {
                border: 2px dashed #ccc;
                border-radius: 4px;
                background: #f8f9fa;
            }
        """)

        layout = QVBoxLayout(self)
        label = QLabel(self.message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #7f8c8d; font-style: italic;")
        layout.addWidget(label)

    def dragEnterEvent(self, event):
        """Handle drag enter"""
        if event.mimeData().hasText():
            event.acceptProposedAction()
            self.setStyleSheet("""
                DropZoneWidget {
                    border: 2px dashed #667eea;
                    border-radius: 4px;
                    background: #e8eaf6;
                }
            """)

    def dragLeaveEvent(self, event):
        """Handle drag leave"""
        self.setStyleSheet("""
            DropZoneWidget {
                border: 2px dashed #ccc;
                border-radius: 4px;
                background: #f8f9fa;
            }
        """)

    def dropEvent(self, event):
        """Handle drop"""
        try:
            # Parse field data from mime data
            import json
            field_data = json.loads(event.mimeData().text())
            self.field_dropped.emit(field_data)

            # Reset styling
            self.setStyleSheet("""
                DropZoneWidget {
                    border: 2px dashed #ccc;
                    border-radius: 4px;
                    background: #f8f9fa;
                }
            """)

        except Exception as e:
            logger.error(f"Error handling drop: {e}")


class CriteriaFilterWidget(QFrame):
    """Widget for a single filter criterion"""

    remove_requested = pyqtSignal()

    def __init__(self, field_data: dict, parent=None):
        super().__init__(parent)
        self.field_data = field_data
        self.parent_screen = parent
        self.unique_values = None
        self.value_checkboxes = []
        self.setAcceptDrops(True)
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            CriteriaFilterWidget {
                border: 2px solid #3498db;
                border-radius: 6px;
                background: white;
            }
        """)
        
        # Fixed width for tile layout - match DisplayFieldWidget width
        self.setFixedWidth(200)
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(2)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Header row: Field name and remove button only (no other buttons)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(4)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # Field name (bold, prominent)
        self.field_label = QLabel(self.field_data['field_name'])
        self.field_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #2c3e50; background: transparent;")
        self.field_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.field_label.customContextMenuRequested.connect(self._show_field_context_menu)
        header_layout.addWidget(self.field_label)
        
        header_layout.addStretch()

        # Placeholder for buttons (will be added later next to controls)
        self.list_button = None
        self.custom_criteria_button = None
        self.custom_criteria_text = ""  # Store custom criteria

        # Reset button (clears filter values but keeps widget)
        reset_btn = QPushButton("↻")
        reset_btn.setFixedSize(18, 18)
        reset_btn.setToolTip("Reset filter values")
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 13px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background: #2980b9;
            }
        """)
        reset_btn.clicked.connect(self._reset_filter_values)
        header_layout.addWidget(reset_btn)

        # Remove button with X (subtle)
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(14, 14)
        remove_btn.setToolTip("Remove this filter")
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #999;
                border: none;
                font-size: 16px;
                font-weight: normal;
                padding: 0px;
            }
            QPushButton:hover {
                color: #e74c3c;
            }
        """)
        remove_btn.clicked.connect(self.remove_requested.emit)
        header_layout.addWidget(remove_btn)
        
        main_layout.addLayout(header_layout)
        
        # Table name and type row (compact info)
        info_layout = QHBoxLayout()
        info_layout.setSpacing(6)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        table_label = QLabel(f"📋 {self.field_data['table_name']}")
        table_label.setStyleSheet("color: #7f8c8d; font-size: 9px; background: transparent;")
        info_layout.addWidget(table_label)
        
        type_label = QLabel(f"({self.field_data['data_type']})")
        type_label.setStyleSheet("color: #95a5a6; font-size: 9px; background: transparent;")
        info_layout.addWidget(type_label)
        
        info_layout.addStretch()
        main_layout.addLayout(info_layout)
        
        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #ecf0f1; max-height: 1px;")
        main_layout.addWidget(separator)

        # Filter controls container
        self.controls_container = QWidget()
        self.controls_container.setStyleSheet("background: transparent;")
        self.controls_layout = QVBoxLayout(self.controls_container)
        self.controls_layout.setContentsMargins(0, 2, 0, 0)
        self.controls_layout.setSpacing(3)
        main_layout.addWidget(self.controls_container)

        # Add filter controls
        self._add_filter_controls()

    def _add_filter_controls(self):
        """Add type-specific filter controls"""
        data_type = self.field_data['data_type'].upper()

        # Check if we have cached unique values
        self._load_unique_values()

        # Determine if string type
        is_string = any(t in data_type for t in ['CHAR', 'VARCHAR', 'TEXT', 'STRING'])
        is_numeric = any(t in data_type for t in ['INT', 'DECIMAL', 'NUMERIC', 'FLOAT', 'DOUBLE', 'REAL', 'NUMBER'])
        is_date = any(t in data_type for t in ['DATE', 'TIME', 'TIMESTAMP'])

        # Add the appropriate filter type (buttons are now integrated into each method)
        if is_string:
            self._add_string_filter_compact()
        elif is_numeric:
            self._add_numeric_filter_compact()
        elif is_date:
            self._add_date_filter_compact()
        else:
            self._add_default_filter_compact()

    def _load_unique_values(self):
        """Try to load cached unique values for this field"""
        try:
            logger.info(f"Loading unique values for field: {self.field_data['field_name']}, table: {self.field_data['table_name']}")
            
            metadata_id = self.parent_screen.metadata_cache_repo.get_or_create_metadata(
                self.parent_screen.current_connection_id,
                self.field_data['table_name'],
                self.field_data.get('schema_name', '')
            )
            
            logger.info(f"Got metadata_id: {metadata_id}")
            
            cached_unique = self.parent_screen.metadata_cache_repo.get_cached_unique_values(
                metadata_id,
                self.field_data['field_name']
            )
            
            if cached_unique:
                self.unique_values = cached_unique['unique_values']
                logger.info(f"Loaded {len(self.unique_values)} unique values from cache")
            else:
                logger.info(f"No cached unique values found for {self.field_data['field_name']}")
                self.unique_values = None
        except Exception as e:
            logger.warning(f"Could not load unique values: {e}")
            self.unique_values = None

    def _update_list_button_style(self):
        """Update list button style based on selection state"""
        if not self.list_button:
            return
        
        # Check if any values are deselected
        all_selected = len(self.selected_values) == len(self.unique_values)
        
        if all_selected:
            # Blue border only (not all selected means some filtering)
            self.list_button.setStyleSheet("""
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
            # Solid blue (some values are filtered)
            self.list_button.setStyleSheet("""
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
    
    def _open_value_selection_popup(self):
        """Open the value selection dialog in a larger window"""
        # Get currently selected values (stored separately since we don't have visible checkboxes)
        currently_selected = getattr(self, 'selected_values', self.unique_values[:])  # Default: all selected
        
        # Create and show the dialog
        dialog = ValueSelectionDialog(
            self.field_data['field_name'],
            self.unique_values,
            currently_selected,
            self
        )
        
        # Connect the signal to update stored selections when dialog closes
        dialog.values_selected.connect(self._update_selected_values)
        
        # Show the dialog
        dialog.show()
    
    def _update_selected_values(self, selected_values):
        """Update the stored selected values from popup dialog"""
        # Store the selected values for later use in query building
        self.selected_values = selected_values
        # Update button style to reflect selection state
        self._update_list_button_style()
        
        # Enable/disable combobox and input based on whether list values are being used
        all_selected = len(selected_values) == len(self.unique_values)
        
        # If not all values are selected (some filtering), disable combo and input (mutually exclusive)
        if hasattr(self, 'match_type_combo'):
            self.match_type_combo.setEnabled(all_selected)
            if not all_selected:
                # Store original value and show "List"
                if not hasattr(self, '_original_combo_text'):
                    self._original_combo_text = self.match_type_combo.currentText()
                # Temporarily add "List" option and select it
                if self.match_type_combo.findText("List") == -1:
                    self.match_type_combo.addItem("List")
                self.match_type_combo.setCurrentText("List")
                # Set light grey background for disabled state
                self.match_type_combo.setStyleSheet("""
                    QComboBox {
                        background-color: #E0E0E0;
                        color: #808080;
                        font-size: 10px;
                        padding: 2px 4px;
                    }
                """)
            else:
                # Remove "List" option and restore original
                list_index = self.match_type_combo.findText("List")
                if list_index != -1:
                    self.match_type_combo.removeItem(list_index)
                if hasattr(self, '_original_combo_text'):
                    self.match_type_combo.setCurrentText(self._original_combo_text)
                    delattr(self, '_original_combo_text')
                # Restore normal styling
                self.match_type_combo.setStyleSheet("""
                    QComboBox {
                        font-size: 10px;
                        padding: 2px 4px;
                        background: white;
                    }
                """)
        
        if hasattr(self, 'filter_input'):
            self.filter_input.setEnabled(all_selected)
            if not all_selected:
                # Set light grey background for disabled state
                self.filter_input.setStyleSheet("""
                    QLineEdit {
                        background-color: #E0E0E0;
                        color: #808080;
                        font-size: 10px;
                        padding: 2px 4px;
                    }
                """)
            else:
                # Restore normal styling
                self.filter_input.setStyleSheet("""
                    QLineEdit {
                        font-size: 10px;
                        padding: 2px 4px;
                        background: white;
                    }
                """)
    
    def _open_custom_criteria_dialog(self):
        """Open dialog to enter custom criteria - works for all combo box modes"""
        from PyQt6.QtWidgets import QDialog, QTextEdit
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit - {self.field_data['field_name']}")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(200)
        
        layout = QVBoxLayout(dialog)
        
        # Instructions - simpler for all modes
        instructions = QLabel("Enter your criteria below. This gives you more space to type.")
        instructions.setStyleSheet("font-size: 10px; color: #666; background: transparent;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Text input - use content from filter_input for all modes
        text_edit = QTextEdit()
        text_edit.setPlaceholderText("Type your filter criteria here...")
        
        # Load current content from the input box
        if hasattr(self, 'filter_input') and self.filter_input.text():
            text_edit.setPlainText(self.filter_input.text())
        
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
        
        # Show dialog and process result - update filter_input for all modes
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_text = text_edit.toPlainText().strip()
            if hasattr(self, 'filter_input'):
                self.filter_input.setText(new_text)
    
    def _on_select_all_changed(self, state):
        """Handle Select All checkbox - No longer used with button-only interface"""
        pass
    
    def _on_select_none_changed(self, state):
        """Handle Select None checkbox - No longer used with button-only interface"""
        pass
    
    def _on_value_checkbox_changed(self):
        """Handle individual value checkbox changes - No longer used with button-only interface"""
        pass

    def _add_string_filter_compact(self):
        """Add compact string filter controls"""
        # First row: Match type dropdown with list button
        combo_row = QHBoxLayout()
        combo_row.setSpacing(4)
        combo_row.setContentsMargins(0, 0, 0, 0)
        
        # Match type dropdown (compact with reduced height)
        self.match_type_combo = QComboBox()
        self.match_type_combo.addItems(["None", "Exact", "Starts", "Ends", "Contains", "Expression"])
        self.match_type_combo.setCurrentText("Exact")  # Default to Exact, not None
        self.match_type_combo.setMinimumWidth(80)
        self.match_type_combo.setMaximumWidth(90)
        self.match_type_combo.setMaximumHeight(22)
        self.match_type_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        self.match_type_combo.currentTextChanged.connect(self._on_match_type_changed)
        combo_row.addWidget(self.match_type_combo)
        
        # List button next to combobox (will be added if unique values exist)
        if self.unique_values:
            # Initialize with all values selected by default
            self.selected_values = self.unique_values[:]
            
            self.list_button = QPushButton("☰")
            self.list_button.setFixedSize(20, 20)
            self.list_button.setToolTip(f"Select Values ({len(self.unique_values)} available)")
            self._update_list_button_style()
            self.list_button.clicked.connect(self._open_value_selection_popup)
            combo_row.addWidget(self.list_button)
        
        combo_row.addStretch()
        
        # Add combo row to layout
        combo_widget = QWidget()
        combo_widget.setStyleSheet("background: transparent;")
        combo_widget.setLayout(combo_row)
        self.controls_layout.addWidget(combo_widget)

        # Second row: Text input with custom criteria button
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        input_row.setContentsMargins(0, 0, 0, 0)
        
        # Text input (compact with reduced height)
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Enter text...")
        self.filter_input.setMinimumWidth(120)
        self.filter_input.setMaximumWidth(260)
        self.filter_input.setMaximumHeight(22)
        self.filter_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        self.filter_input.textChanged.connect(self._on_filter_input_changed)
        input_row.addWidget(self.filter_input)
        
        # Custom criteria button next to input box (orange pen) - always visible, always outline style
        self.custom_criteria_button = QPushButton("🖊")
        self.custom_criteria_button.setFixedSize(20, 20)
        self.custom_criteria_button.setToolTip("Open larger editor for more space")
        # Always use outline style (never solid)
        self.custom_criteria_button.setStyleSheet("""
            QPushButton {
                background: white;
                color: #ff9800;
                border: 2px solid #ff9800;
                border-radius: 3px;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                background: #fff3e0;
            }
        """)
        self.custom_criteria_button.clicked.connect(self._open_custom_criteria_dialog)
        input_row.addWidget(self.custom_criteria_button)
        
        input_row.addStretch()
        
        # Add input row to layout
        input_widget = QWidget()
        input_widget.setStyleSheet("background: transparent;")
        input_widget.setLayout(input_row)
        self.controls_layout.addWidget(input_widget)
    
    def _on_match_type_changed(self, text):
        """Handle match type combobox changes"""
        if not hasattr(self, 'filter_input'):
            return
        
        # Update placeholder text based on mode
        if text == "Expression":
            self.filter_input.setPlaceholderText("Enter custom criteria (e.g., >100, LIKE 'A%')...")
        else:
            self.filter_input.setPlaceholderText("Enter text...")
        
        # Pen button is always visible now - removed visibility toggle
    
    def _on_filter_input_changed(self, text):
        """Handle filter input text changes - sync with custom_criteria_text in Expression mode"""
        if hasattr(self, 'match_type_combo') and self.match_type_combo.currentText() == 'Expression':
            # In Expression mode, sync the filter input with custom_criteria_text
            self.custom_criteria_text = text

    def _add_numeric_filter_compact(self):
        """Add compact numeric filter controls in horizontal layout"""
        # Create horizontal layout for the range inputs
        range_layout = QHBoxLayout()
        range_layout.setSpacing(4)
        range_layout.setContentsMargins(0, 0, 0, 0)

        # Exact value input at the top
        exact_layout = QHBoxLayout()
        exact_layout.setSpacing(4)
        exact_layout.setContentsMargins(0, 0, 0, 0)

        # If we have unique values, use a combobox instead of line edit
        if self.unique_values:
            # Initialize with all values selected by default
            self.selected_values = self.unique_values[:]

            # Sort numeric values properly
            sorted_values = sorted(self.unique_values, key=lambda x: float(x) if str(x).replace('.','',1).replace('-','',1).isdigit() else 0)

            self.exact_input = QComboBox()
            self.exact_input.setEditable(True)
            self.exact_input.addItem("None")  # Default option
            for val in sorted_values:
                self.exact_input.addItem(str(val))
            self.exact_input.setCurrentText("None")
            self.exact_input.setMaximumHeight(22)
            self.exact_input.setMinimumWidth(120)
            self.exact_input.setMaximumWidth(260)
            self.exact_input.setStyleSheet("""
                QComboBox {
                    font-size: 10px;
                    padding: 2px 4px;
                    background: white;
                }
            """)
            exact_layout.addWidget(self.exact_input)

            # Add list button for value selection
            self.list_button = QPushButton("☰")
            self.list_button.setFixedSize(20, 20)
            self.list_button.setToolTip(f"Select Values ({len(self.unique_values)} available)")
            self._update_list_button_style()
            self.list_button.clicked.connect(self._open_value_selection_popup)
            exact_layout.addWidget(self.list_button)
        else:
            # No unique values - use regular line edit
            self.exact_input = QLineEdit()
            self.exact_input.setPlaceholderText("Exact value")
            self.exact_input.setMaximumHeight(22)
            self.exact_input.setStyleSheet("""
                QLineEdit {
                    font-size: 10px;
                    padding: 2px 4px;
                    background: white;
                }
            """)
            exact_layout.addWidget(self.exact_input)

        exact_widget = QWidget()
        exact_widget.setStyleSheet("background: transparent;")
        exact_widget.setLayout(exact_layout)
        self.controls_layout.addWidget(exact_widget)
        
        # Or label
        # or_label = QLabel("or")
        # or_label.setStyleSheet("font-size: 9px; color: #7f8c8d; background: transparent;")
        # self.controls_layout.addWidget(or_label)
        
        # Range inputs in one line: Min [____] to [____] Max
        self.range_low_input = QLineEdit()
        self.range_low_input.setPlaceholderText("Min")
        self.range_low_input.setMaximumHeight(22)
        self.range_low_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        range_layout.addWidget(self.range_low_input)

        # To label
        to_label = QLabel("to")
        to_label.setStyleSheet("font-size: 9px; color: #7f8c8d; background: transparent;")
        range_layout.addWidget(to_label)

        # Range high
        self.range_high_input = QLineEdit()
        self.range_high_input.setPlaceholderText("Max")
        self.range_high_input.setMaximumHeight(22)
        self.range_high_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        range_layout.addWidget(self.range_high_input)
        
        # Add range layout as a widget
        range_widget = QWidget()
        range_widget.setStyleSheet("background: transparent;")
        range_widget.setLayout(range_layout)
        self.controls_layout.addWidget(range_widget)

    def _add_date_filter_compact(self):
        """Add compact date filter controls"""
        # Exact date (reduced height)
        self.exact_date_input = QDateEdit()
        self.exact_date_input.setCalendarPopup(True)
        self.exact_date_input.setDate(QDate.currentDate())
        self.exact_date_input.setMinimumWidth(100)
        self.exact_date_input.setMaximumWidth(120)
        self.exact_date_input.setMaximumHeight(22)
        self.exact_date_input.setDisplayFormat("MM/dd/yyyy")
        self.exact_date_input.setStyleSheet("""
            QDateEdit {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        self.controls_layout.addWidget(self.exact_date_input)

        # Or label
        or_label = QLabel("or")
        or_label.setStyleSheet("font-size: 10px; color: #7f8c8d; background: transparent;")
        self.controls_layout.addWidget(or_label)

        # Date range start (reduced height)
        self.date_range_start = QDateEdit()
        self.date_range_start.setCalendarPopup(True)
        self.date_range_start.setDate(QDate.currentDate())
        self.date_range_start.setMinimumWidth(100)
        self.date_range_start.setMaximumWidth(120)
        self.date_range_start.setMaximumHeight(22)
        self.date_range_start.setDisplayFormat("MM/dd/yyyy")
        self.date_range_start.setStyleSheet("""
            QDateEdit {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        self.controls_layout.addWidget(self.date_range_start)

        # To label
        to_label = QLabel("to")
        to_label.setStyleSheet("font-size: 10px; color: #7f8c8d; background: transparent;")
        self.controls_layout.addWidget(to_label)

        # Date range end (reduced height)
        self.date_range_end = QDateEdit()
        self.date_range_end.setCalendarPopup(True)
        self.date_range_end.setDate(QDate.currentDate())
        self.date_range_end.setMinimumWidth(100)
        self.date_range_end.setMaximumWidth(120)
        self.date_range_end.setMaximumHeight(22)
        self.date_range_end.setDisplayFormat("MM/dd/yyyy")
        self.date_range_end.setStyleSheet("""
            QDateEdit {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        self.controls_layout.addWidget(self.date_range_end)

    def _add_default_filter_compact(self):
        """Add simple text input for unknown types"""
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Enter value...")
        self.filter_input.setMinimumWidth(150)
        self.filter_input.setMaximumWidth(200)
        self.filter_input.setMaximumHeight(22)
        self.filter_input.setStyleSheet("""
            QLineEdit {
                font-size: 10px;
                padding: 2px 4px;
                background: white;
            }
        """)
        self.controls_layout.addWidget(self.filter_input)
        self.date_range_end.setCalendarPopup(True)
        self.date_range_end.setDate(QDate.currentDate())
        self.date_range_end.setMinimumWidth(100)
        self.date_range_end.setMaximumWidth(120)
        self.date_range_end.setStyleSheet("font-size: 10px;")
        self.date_range_end.setDisplayFormat("MM/dd/yyyy")
        self.controls_layout.addWidget(self.date_range_end)

    def _add_default_filter_compact(self):
        """Add compact default text input filter"""
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Enter value...")
        self.filter_input.setMinimumWidth(150)
        self.filter_input.setMaximumWidth(250)
        self.filter_input.setStyleSheet("font-size: 10px;")
        self.controls_layout.addWidget(self.filter_input)

    def get_filter_value(self):
        """Get the current filter configuration"""
        data_type = self.field_data['data_type'].upper()
        result = None

        # Check if "None" is selected - return None to skip this filter
        if hasattr(self, 'match_type_combo') and self.match_type_combo.currentText() == "None":
            return None

        # Checkbox list mode - only include if "List" is showing in combobox (meaning actively filtering)
        # OR if we have list_button (numeric with unique values) and not all are selected
        if hasattr(self, 'selected_values') and self.selected_values is not None:
            # Check if we're using a list button (numeric unique values) AND not all are selected
            if hasattr(self, 'list_button') and len(self.selected_values) < len(self.unique_values):
                result = {
                    'type': 'checkbox_list',
                    'selected_values': self.selected_values
                }
            # Only return list filter if combobox shows "List" (indicating active filtering)
            elif hasattr(self, 'match_type_combo') and self.match_type_combo.currentText() == "List":
                result = {
                    'type': 'checkbox_list',
                    'selected_values': self.selected_values
                }
            # If "List" is not showing, check for text input instead
            elif hasattr(self, 'filter_input') and self.filter_input.text():
                if hasattr(self, 'match_type_combo'):
                    match_types = {
                        'Exact': 'exact',
                        'Starts': 'starts_with',
                        'Ends': 'ends_with',
                        'Contains': 'contains',
                        'Expression': 'expression'
                    }
                    match_type = self.match_type_combo.currentText()
                    
                    if match_type == 'Expression':
                        result = {
                            'type': 'expression',
                            'value': self.filter_input.text()
                        }
                    else:
                        result = {
                            'type': 'string',
                            'match_type': match_types.get(match_type, 'exact'),
                            'value': self.filter_input.text()
                        }

        # String mode
        elif hasattr(self, 'match_type_combo'):
            match_types = {
                'Exact': 'exact',
                'Starts': 'starts_with',
                'Ends': 'ends_with',
                'Contains': 'contains',
                'Expression': 'expression'
            }
            match_type = self.match_type_combo.currentText()
            
            # If Expression mode, treat the filter_input as custom criteria
            if match_type == 'Expression':
                result = {
                    'type': 'expression',
                    'value': self.filter_input.text() if hasattr(self, 'filter_input') else ''
                }
            else:
                result = {
                    'type': 'string',
                    'match_type': match_types.get(match_type, 'exact'),
                    'value': self.filter_input.text() if hasattr(self, 'filter_input') else ''
                }

        # Numeric mode (check which input has value)
        elif hasattr(self, 'exact_input'):
            # Handle both QLineEdit (text()) and QComboBox (currentText())
            if isinstance(self.exact_input, QComboBox):
                exact_val = self.exact_input.currentText().strip()
            else:
                exact_val = self.exact_input.text().strip()

            low_val = self.range_low_input.text().strip() if hasattr(self, 'range_low_input') else ''
            high_val = self.range_high_input.text().strip() if hasattr(self, 'range_high_input') else ''

            # Skip if exact value is "None"
            if exact_val and exact_val != "None":
                result = {
                    'type': 'numeric_exact',
                    'value': exact_val
                }
            elif low_val or high_val:
                result = {
                    'type': 'numeric_range',
                    'low': low_val,
                    'high': high_val
                }

        # Date mode (check which input to use)
        elif hasattr(self, 'exact_date_input'):
            # Check if range inputs have been modified from default
            if hasattr(self, 'date_range_start') and hasattr(self, 'date_range_end'):
                start_date = self.date_range_start.date().toString('yyyy-MM-dd')
                end_date = self.date_range_end.date().toString('yyyy-MM-dd')
                exact_date = self.exact_date_input.date().toString('yyyy-MM-dd')
                
                # If range dates differ from current date, use range
                if start_date != exact_date or end_date != exact_date:
                    result = {
                        'type': 'date_range',
                        'start': start_date,
                        'end': end_date
                    }
            
            # Otherwise use exact date
            if not result:
                result = {
                    'type': 'date_exact',
                    'value': self.exact_date_input.date().toString('yyyy-MM-dd')
                }

        # Default mode
        elif hasattr(self, 'filter_input'):
            result = {
                'type': 'text',
                'value': self.filter_input.text()
            }
        
        # Add custom criteria if present
        if result and hasattr(self, 'custom_criteria_text') and self.custom_criteria_text:
            result['custom_criteria'] = self.custom_criteria_text

        return result

    def _show_field_context_menu(self, position):
        """Show context menu for field label"""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { border: 2px solid #555; }")
        
        find_unique_action = QAction("Find Unique Values", self)
        find_unique_action.triggered.connect(self._find_unique_values)
        menu.addAction(find_unique_action)
        
        # Show menu at the global position
        menu.exec(self.field_label.mapToGlobal(position))

    def _find_unique_values(self):
        """Find unique values for this field and update the widget"""
        try:
            # Get metadata
            metadata_id = self.parent_screen.metadata_cache_repo.get_or_create_metadata(
                self.parent_screen.current_connection_id,
                self.field_data['table_name'],
                self.field_data.get('schema_name', '')
            )
            
            # Query unique values from database
            unique_values = self.parent_screen.schema_discovery.get_unique_values(
                self.parent_screen.current_connection_id,
                self.field_data['table_name'],
                self.field_data['field_name'],
                self.field_data.get('schema_name', '')
            )
            
            # Cache them in database
            self.parent_screen.metadata_cache_repo.cache_unique_values(
                metadata_id,
                self.field_data['field_name'],
                unique_values
            )
            
            # Update the widget to show the unique values
            self.unique_values = unique_values
            
            # Clear existing controls and rebuild
            while self.controls_layout.count():
                child = self.controls_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            # Rebuild controls with the new unique values
            self._add_filter_controls()
            
            logger.info(f"Found {len(unique_values)} unique values for {self.field_data['field_name']}")
            
            # Show success message
            QMessageBox.information(
                self,
                "Success",
                f"Found {len(unique_values)} unique values for {self.field_data['field_name']}"
            )
            
        except Exception as e:
            logger.error(f"Error finding unique values: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to find unique values:\n{str(e)}"
            )

    def _reset_filter_values(self):
        """Reset all filter values to defaults"""
        # Reset string filter
        if hasattr(self, 'match_type_combo'):
            self.match_type_combo.setCurrentText("Exact")
        if hasattr(self, 'filter_input'):
            if isinstance(self.filter_input, QLineEdit):
                self.filter_input.clear()

        # Reset numeric filter
        if hasattr(self, 'exact_input'):
            if isinstance(self.exact_input, QComboBox):
                self.exact_input.setCurrentText("None")
            elif isinstance(self.exact_input, QLineEdit):
                self.exact_input.clear()

        if hasattr(self, 'range_low_input'):
            self.range_low_input.clear()
        if hasattr(self, 'range_high_input'):
            self.range_high_input.clear()

        # Reset date filter
        if hasattr(self, 'exact_date_input'):
            self.exact_date_input.setDate(QDate.currentDate())
        if hasattr(self, 'date_range_start'):
            self.date_range_start.setDate(QDate.currentDate())
        if hasattr(self, 'date_range_end'):
            self.date_range_end.setDate(QDate.currentDate())

        # Reset selected values to all (if unique values exist)
        if hasattr(self, 'unique_values') and self.unique_values:
            self.selected_values = self.unique_values[:]
            if hasattr(self, 'list_button'):
                self._update_list_button_style()

        # Clear custom criteria
        self.custom_criteria_text = ""

        logger.info(f"Reset filter values for {self.field_data['field_name']}")

    def mousePressEvent(self, event):
        """Handle mouse press for drag initiation"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, 'drag_start_position'):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < 10:
            return
        
        if not self.parent_screen or not hasattr(self.parent_screen, 'criteria_widgets'):
            return
        
        source_index = self.parent_screen.criteria_widgets.index(self)
        
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"CriteriaFilterWidget:{source_index}")
        drag.setMimeData(mime_data)
        
        # Create a semi-transparent pixmap of the widget for drag visualization
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())
        
        drag.exec(Qt.DropAction.MoveAction)
    
    def dragEnterEvent(self, event):
        """Handle drag enter"""
        if event.mimeData().hasText() and event.mimeData().text().startswith("CriteriaFilterWidget:"):
            event.acceptProposedAction()
            # Add visual feedback - highlight border
            self.setStyleSheet(self.styleSheet().replace("border: 2px solid #3498db", "border: 3px solid #5dade2"))
    
    def dragLeaveEvent(self, event):
        """Handle drag leave"""
        # Remove visual feedback
        self.setStyleSheet(self.styleSheet().replace("border: 3px solid #5dade2", "border: 2px solid #3498db"))
    
    def dropEvent(self, event):
        """Handle drop"""
        # Remove visual feedback
        self.setStyleSheet(self.styleSheet().replace("border: 3px solid #5dade2", "border: 2px solid #3498db"))
        
        if event.mimeData().hasText() and event.mimeData().text().startswith("CriteriaFilterWidget:"):
            source_text = event.mimeData().text()
            source_index = int(source_text.split(":")[1])
            
            if self.parent_screen and hasattr(self.parent_screen, 'criteria_widgets'):
                # Find target index
                target_index = self.parent_screen.criteria_widgets.index(self)
                
                if source_index != target_index:
                    # Remove source widget
                    source_widget = self.parent_screen.criteria_widgets.pop(source_index)
                    self.parent_screen.criteria_layout.removeWidget(source_widget)
                    
                    # Adjust target index if source was before target
                    if source_index < target_index:
                        target_index -= 1
                    
                    # Insert at new position
                    self.parent_screen.criteria_widgets.insert(target_index, source_widget)
                    self.parent_screen.criteria_layout.insertWidget(target_index, source_widget)
                    
                    # Show the widget again
                    source_widget.show()
                    
            event.acceptProposedAction()



class DisplayFieldWidget(QFrame):
    """Widget for a single display field"""

    remove_requested = pyqtSignal()

    def __init__(self, field_data: dict, parent=None):
        super().__init__(parent)
        self.field_data = field_data
        self.is_expanded = False  # Start collapsed
        self.setAcceptDrops(True)
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        
        # Store default background for toggling
        self.default_bg = "white"
        self.aggregated_bg = "#FFE5CC"  # Light orange
        self.aggregated_having_bg = "#FFB366"  # Darker orange (with HAVING clause)
        
        self.setStyleSheet(f"""
            DisplayFieldWidget {{
                border: 2px solid #27ae60;
                border-radius: 6px;
                background: {self.default_bg};
                padding: 0px;
            }}
        """)
        
        # Fixed width for tile layout - compact but readable
        self.setFixedWidth(200)
        # Dynamic height based on expanded state
        self.collapsed_height = 50
        self.expanded_height = 115  # Increased for Having field
        self.setFixedHeight(self.collapsed_height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setSpacing(1)
        layout.setContentsMargins(4, 2, 4, 2)

        # Header row: Field name, data type, and remove button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(3)
        
        # Field name (bold, prominent)
        field_label = QLabel(self.field_data['field_name'])
        field_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #2c3e50; background: transparent;")
        field_label.setWordWrap(True)
        header_layout.addWidget(field_label)
        
        # Data type (subtle, in header)
        type_label = QLabel(f"({self.field_data['data_type']})")
        type_label.setStyleSheet("color: #999; font-size: 8px; background: transparent;")
        header_layout.addWidget(type_label)
        
        header_layout.addStretch()
        
        # Subtle remove button with X
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(14, 14)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #999;
                border: none;
                font-size: 16px;
                font-weight: normal;
                padding: 0px;
            }
            QPushButton:hover {
                color: #e74c3c;
            }
        """)
        remove_btn.clicked.connect(self.remove_requested.emit)
        header_layout.addWidget(remove_btn, alignment=Qt.AlignmentFlag.AlignTop)
        
        layout.addLayout(header_layout)
        
        # Table name row with expand/collapse button
        table_row_layout = QHBoxLayout()
        table_row_layout.setSpacing(2)
        
        table_label = QLabel(f"📋 {self.field_data['table_name']}")
        table_label.setStyleSheet("color: #7f8c8d; font-size: 9px; background: transparent;")
        table_row_layout.addWidget(table_label)
        
        table_row_layout.addStretch()
        
        # Toggle button (arrow icon)
        self.toggle_btn = QPushButton("▼")
        self.toggle_btn.setFixedSize(16, 16)
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                font-size: 10px;
                font-weight: bold;
                padding: 0px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: #229954;
            }
        """)
        self.toggle_btn.clicked.connect(self.toggle_details)
        table_row_layout.addWidget(self.toggle_btn)
        
        layout.addLayout(table_row_layout)
        layout.addLayout(table_row_layout)
        
        # Collapsible details container
        self.details_container = QWidget()
        self.details_container.setStyleSheet("background: transparent;")
        details_layout = QVBoxLayout(self.details_container)
        details_layout.setSpacing(1)
        details_layout.setContentsMargins(0, 2, 0, 0)
        
        # Alias input field (editable)
        alias_layout = QHBoxLayout()
        alias_layout.setSpacing(2)
        alias_label = QLabel("Alias:")
        alias_label.setStyleSheet("font-size: 9px; color: #7f8c8d; background: transparent;")
        alias_layout.addWidget(alias_label)
        
        self.alias_input = QLineEdit()
        self.alias_input.setText(self.field_data['field_name'])  # Default to field name
        self.alias_input.setStyleSheet("""
            QLineEdit {
                font-size: 9px;
                padding: 1px 2px;
                background: white;
                border: 1px solid #ddd;
                border-radius: 2px;
            }
        """)
        self.alias_input.setMaximumHeight(16)
        alias_layout.addWidget(self.alias_input)
        
        details_layout.addLayout(alias_layout)
        details_layout.addLayout(alias_layout)
        
        # Bottom row: Agg and Order on same line
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(4)
        
        # Aggregation combobox
        agg_label = QLabel("Agg:")
        agg_label.setStyleSheet("font-size: 9px; color: #7f8c8d; background: transparent;")
        controls_layout.addWidget(agg_label)
        
        self.agg_combo = QComboBox()
        # Populate based on data type
        data_type_lower = self.field_data['data_type'].lower()
        if any(t in data_type_lower for t in ['char', 'varchar', 'text', 'string', 'clob']):
            # String types
            self.agg_combo.addItems(["None", "First", "Last", "Count"])
        else:
            # Numeric types (int, decimal, float, double, etc.)
            self.agg_combo.addItems(["None", "Sum", "Max", "Min", "Avg", "First", "Last", "Count"])
        
        self.agg_combo.setStyleSheet("""
            QComboBox {
                font-size: 9px;
                padding: 1px;
                background: white;
                border: 1px solid #ddd;
                border-radius: 2px;
            }
        """)
        self.agg_combo.setMaximumHeight(16)
        self.agg_combo.setMaximumWidth(60)
        self.agg_combo.currentTextChanged.connect(self.on_agg_changed)
        controls_layout.addWidget(self.agg_combo)
        
        # Order combobox
        order_label = QLabel("Order:")
        order_label.setStyleSheet("font-size: 9px; color: #7f8c8d; background: transparent;")
        controls_layout.addWidget(order_label)
        
        self.order_combo = QComboBox()
        self.order_combo.addItems(["None", "Ascend", "Descend"])
        self.order_combo.setStyleSheet("""
            QComboBox {
                font-size: 9px;
                padding: 1px;
                background: white;
                border: 1px solid #ddd;
                border-radius: 2px;
            }
        """)
        self.order_combo.setMaximumHeight(16)
        self.order_combo.setMaximumWidth(60)
        controls_layout.addWidget(self.order_combo)
        
        details_layout.addLayout(controls_layout)
        
        # Having clause input (for filtering aggregated results)
        having_layout = QHBoxLayout()
        having_layout.setSpacing(2)
        having_label = QLabel("Having:")
        having_label.setStyleSheet("font-size: 9px; color: #7f8c8d; background: transparent;")
        having_label.setToolTip("Filter aggregated results (e.g., > 100, BETWEEN 10 AND 50)")
        having_layout.addWidget(having_label)
        
        self.having_input = QLineEdit()
        self.having_input.setPlaceholderText("e.g., > 100")
        self.having_input.setStyleSheet("""
            QLineEdit {
                font-size: 9px;
                padding: 1px 2px;
                background: white;
                border: 1px solid #ddd;
                border-radius: 2px;
            }
        """)
        self.having_input.setMaximumHeight(16)
        self.having_input.textChanged.connect(self.on_having_changed)
        having_layout.addWidget(self.having_input)
        
        details_layout.addLayout(having_layout)
        
        # Add details container to main layout and hide initially
        layout.addWidget(self.details_container)
        self.details_container.hide()
    
    def toggle_details(self):
        """Toggle the visibility of alias and controls"""
        self.is_expanded = not self.is_expanded
        
        if self.is_expanded:
            # Expand
            self.details_container.show()
            self.setFixedHeight(self.expanded_height)
            self.toggle_btn.setText("▲")
        else:
            # Collapse
            self.details_container.hide()
            self.setFixedHeight(self.collapsed_height)
            self.toggle_btn.setText("▼")
    
    def update_background_color(self):
        """Update background color based on aggregation and having state"""
        has_agg = self.agg_combo.currentText() != "None"
        has_having = self.having_input.text().strip() != ""
        
        if has_agg and has_having:
            # Darker orange when both aggregation and having are present
            bg_color = self.aggregated_having_bg
        elif has_agg:
            # Light orange when only aggregation is present
            bg_color = self.aggregated_bg
        else:
            # White background when no aggregation
            bg_color = self.default_bg
        
        self.setStyleSheet(f"""
            DisplayFieldWidget {{
                border: 2px solid #27ae60;
                border-radius: 6px;
                background: {bg_color};
                padding: 0px;
            }}
        """)
    
    def on_agg_changed(self, text):
        """Handle aggregation selection change"""
        self.update_background_color()
    
    def on_having_changed(self):
        """Handle having input change"""
        self.update_background_color()
    
    def mousePressEvent(self, event):
        """Handle mouse press for drag initiation"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, 'drag_start_position'):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < 10:
            return
        
        # Get parent screen
        parent_screen = self.parent()
        while parent_screen and not hasattr(parent_screen, 'display_widgets'):
            parent_screen = parent_screen.parent()
        
        if not parent_screen or not hasattr(parent_screen, 'display_widgets'):
            return
        
        source_index = parent_screen.display_widgets.index(self)
        
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"DisplayFieldWidget:{source_index}")
        drag.setMimeData(mime_data)
        
        # Create a semi-transparent pixmap of the widget for drag visualization
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())
        
        drag.exec(Qt.DropAction.MoveAction)
    
    def dragEnterEvent(self, event):
        """Handle drag enter"""
        if event.mimeData().hasText() and event.mimeData().text().startswith("DisplayFieldWidget:"):
            event.acceptProposedAction()
            # Add visual feedback - highlight border
            self.setStyleSheet(self.styleSheet().replace("border: 2px solid #27ae60", "border: 3px solid #2ecc71"))
    
    def dragLeaveEvent(self, event):
        """Handle drag leave"""
        # Remove visual feedback
        self.setStyleSheet(self.styleSheet().replace("border: 3px solid #2ecc71", "border: 2px solid #27ae60"))
    
    def dropEvent(self, event):
        """Handle drop"""
        # Remove visual feedback
        self.setStyleSheet(self.styleSheet().replace("border: 3px solid #2ecc71", "border: 2px solid #27ae60"))
        
        if event.mimeData().hasText() and event.mimeData().text().startswith("DisplayFieldWidget:"):
            source_text = event.mimeData().text()
            source_index = int(source_text.split(":")[1])
            
            # Get parent screen
            parent_screen = self.parent()
            while parent_screen and not hasattr(parent_screen, 'display_widgets'):
                parent_screen = parent_screen.parent()
            
            if parent_screen and hasattr(parent_screen, 'display_widgets'):
                # Find target index
                target_index = parent_screen.display_widgets.index(self)
                
                if source_index != target_index:
                    # Remove source widget
                    source_widget = parent_screen.display_widgets.pop(source_index)
                    source_data = parent_screen.display_fields.pop(source_index)
                    parent_screen.display_layout.removeWidget(source_widget)
                    
                    # Adjust target index if source was before target
                    if source_index < target_index:
                        target_index -= 1
                    
                    # Insert at new position
                    parent_screen.display_widgets.insert(target_index, source_widget)
                    parent_screen.display_fields.insert(target_index, source_data)
                    parent_screen.display_layout.insertWidget(target_index, source_widget)
                    
                    # Show the widget again
                    source_widget.show()
                    
            event.acceptProposedAction()


class JoinWidget(QFrame):
    """Widget for configuring a single JOIN"""

    remove_requested = pyqtSignal()

    def __init__(self, tables: list, parent=None):
        super().__init__(parent)
        self.tables = tables
        self.parent_screen = parent
        self.from_table = None
        self.join_table = None
        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            JoinWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
                padding: 10px;
            }
        """)

        layout = QVBoxLayout(self)

        # First row: JOIN type and table
        top_layout = QHBoxLayout()

        # JOIN type
        self.join_type_combo = QComboBox()
        self.join_type_combo.addItems(["INNER JOIN", "LEFT OUTER JOIN", "RIGHT OUTER JOIN", "FULL OUTER JOIN"])
        self.join_type_combo.setMinimumWidth(150)
        self.join_type_combo.setMaximumHeight(22)
        self.join_type_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        top_layout.addWidget(self.join_type_combo)

        # Table selection
        self.join_table_combo = QComboBox()
        self.join_table_combo.addItems(self.tables)
        self.join_table_combo.setMinimumWidth(150)
        self.join_table_combo.setMaximumHeight(22)
        self.join_table_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        self.join_table_combo.currentTextChanged.connect(self._on_join_table_changed)
        top_layout.addWidget(self.join_table_combo)

        top_layout.addStretch()

        # Remove button with white X, right-justified
        remove_btn = QPushButton("X")
        remove_btn.setFixedSize(25, 25)
        remove_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #c0392b;
            }
        """)
        remove_btn.clicked.connect(self.remove_requested.emit)
        top_layout.addWidget(remove_btn)

        layout.addLayout(top_layout)

        # Container for ON conditions (can have multiple)
        self.on_conditions_container = QWidget()
        self.on_conditions_layout = QVBoxLayout(self.on_conditions_container)
        self.on_conditions_layout.setContentsMargins(0, 0, 0, 0)
        self.on_conditions_layout.setSpacing(5)
        
        # Store ON condition rows
        self.on_condition_rows = []
        
        # Add first ON condition row
        self._add_on_condition_row()
        
        layout.addWidget(self.on_conditions_container)
        
        # Add button for additional ON conditions
        add_on_btn = QPushButton("+ Add ON Condition")
        add_on_btn.setObjectName("gold_button")
        add_on_btn.setMaximumWidth(150)
        add_on_btn.clicked.connect(self._add_on_condition_row)
        layout.addWidget(add_on_btn)
        
        # Load initial field lists
        self._load_field_lists(preserve_selections=False)

    def _add_on_condition_row(self):
        """Add a new ON condition row"""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)
        
        # ON label (only on first row)
        if len(self.on_condition_rows) == 0:
            on_label = QLabel("ON:")
            on_label.setStyleSheet("font-weight: bold; font-size: 10px;")
            on_label.setMinimumWidth(30)
            row_layout.addWidget(on_label)
        else:
            # AND label for additional conditions
            and_label = QLabel("AND:")
            and_label.setStyleSheet("font-weight: bold; font-size: 10px; color: #7f8c8d;")
            and_label.setMinimumWidth(30)
            row_layout.addWidget(and_label)
        
        # Left table name label
        left_table_label = QLabel("")
        left_table_label.setStyleSheet("color: #7f8c8d; font-size: 9px; font-style: italic;")
        left_table_label.setMinimumWidth(80)
        row_layout.addWidget(left_table_label)
        
        # Left field dropdown (FROM table fields)
        left_field_combo = QComboBox()
        left_field_combo.setMinimumWidth(180)
        left_field_combo.setMaximumHeight(22)
        left_field_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        row_layout.addWidget(left_field_combo)
        
        # Connect signal to auto-populate right field
        left_field_combo.currentTextChanged.connect(lambda: self._on_left_field_changed(left_field_combo, right_field_combo))

        # Operator dropdown
        operator_combo = QComboBox()
        operator_combo.addItems(["=", "<>", "<", ">", "<=", ">="])
        operator_combo.setMaximumWidth(60)
        operator_combo.setMaximumHeight(22)
        operator_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        row_layout.addWidget(operator_combo)
        
        # Right table name label
        right_table_label = QLabel("")
        right_table_label.setStyleSheet("color: #7f8c8d; font-size: 9px; font-style: italic;")
        right_table_label.setMinimumWidth(80)
        row_layout.addWidget(right_table_label)

        # Right field dropdown (JOIN table fields)
        right_field_combo = QComboBox()
        right_field_combo.setMinimumWidth(180)
        right_field_combo.setMaximumHeight(22)
        right_field_combo.setStyleSheet("""
            QComboBox {
                font-size: 10px;
                padding: 2px 4px;
            }
        """)
        row_layout.addWidget(right_field_combo)
        
        # Remove button (only for additional rows)
        if len(self.on_condition_rows) > 0:
            remove_on_btn = QPushButton("×")
            remove_on_btn.setFixedSize(22, 22)
            remove_on_btn.setStyleSheet("""
                QPushButton {
                    background: #95a5a6;
                    color: white;
                    border: none;
                    border-radius: 3px;
                    font-size: 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: #7f8c8d;
                }
            """)
            remove_on_btn.clicked.connect(lambda: self._remove_on_condition_row(row_widget))
            row_layout.addWidget(remove_on_btn)
        
        row_layout.addStretch()
        
        # Store references
        row_data = {
            'widget': row_widget,
            'left_table_label': left_table_label,
            'left_field_combo': left_field_combo,
            'operator_combo': operator_combo,
            'right_table_label': right_table_label,
            'right_field_combo': right_field_combo
        }
        self.on_condition_rows.append(row_data)
        
        # Add to layout
        self.on_conditions_layout.addWidget(row_widget)
        
        # Update labels and populate fields for the new row
        self._update_on_condition_labels()
        
        # Populate the field combos for the new row
        if self.from_table and self.join_table:
            # Populate left field combo (FROM table)
            fields = self._get_table_fields(self.from_table)
            left_field_combo.addItems(fields)
            
            # Populate right field combo (JOIN table)
            fields = self._get_table_fields(self.join_table)
            right_field_combo.addItems(fields)

    def _remove_on_condition_row(self, row_widget):
        """Remove an ON condition row"""
        # Find and remove from list
        for i, row_data in enumerate(self.on_condition_rows):
            if row_data['widget'] == row_widget:
                self.on_condition_rows.pop(i)
                break
        
        # Remove widget
        self.on_conditions_layout.removeWidget(row_widget)
        row_widget.deleteLater()

    def _update_on_condition_labels(self):
        """Update table name labels for all ON condition rows"""
        from_table = self.from_table or ""
        join_table = self.join_table or ""
        
        for row_data in self.on_condition_rows:
            if from_table:
                row_data['left_table_label'].setText(f"({from_table})")
            if join_table:
                row_data['right_table_label'].setText(f"({join_table})")

    def _on_join_table_changed(self, table_name):
        """Handle join table selection change"""
        # Skip if parent screen is loading a query
        if self.parent_screen and hasattr(self.parent_screen, '_loading_query') and self.parent_screen._loading_query:
            print(f"      [_on_join_table_changed] SKIPPED - Parent is loading query")
            return
            
        self.join_table = table_name
        # When user explicitly changes the JOIN table, rebuild lists without preserving
        self._load_field_lists(preserve_selections=False)

    def _load_field_lists(self, preserve_selections: bool = True):
        """Load fields for FROM and JOIN tables.
        If preserve_selections is True, keep the currently displayed values and
        only refresh the dropdown contents. Signals are blocked during the
        refresh to avoid unintended auto-matching.
        """
        print(f"      [_load_field_lists] Called (preserve={preserve_selections}) - FROM: {self.from_table}, JOIN: {self.join_table}")
        
        # Skip if parent screen is loading a query
        if self.parent_screen and hasattr(self.parent_screen, '_loading_query') and self.parent_screen._loading_query:
            print(f"      [_load_field_lists] SKIPPED - Parent is loading query")
            return
            
        if not self.parent_screen:
            print(f"      [_load_field_lists] No parent_screen!")
            return
        
        # Get FROM table from parent
        from_table = self.parent_screen.from_table_combo.currentText()
        join_table = self.join_table_combo.currentText()
        
        self.from_table = from_table
        self.join_table = join_table
        
        # Update table labels
        self._update_on_condition_labels()
        
        # Load fields for all ON condition rows
        print(f"      [_load_field_lists] Loading fields for {len(self.on_condition_rows)} row(s)")
        for idx, row_data in enumerate(self.on_condition_rows, 1):
            left_combo = row_data['left_field_combo']
            right_combo = row_data['right_field_combo']
            # Save current selections if preserving
            left_current = left_combo.currentText() if preserve_selections else ''
            right_current = right_combo.currentText() if preserve_selections else ''
            print(f"      [_load_field_lists] Row {idx} - Before clear: left='{left_current}', right='{right_current}'")
            
            # Load FROM table fields (left side)
            prev_left_block = left_combo.blockSignals(True)
            left_combo.clear()
            if from_table:
                fields = self._get_table_fields(from_table)
                left_combo.addItems(fields)
                print(f"      [_load_field_lists] Row {idx} - Loaded {len(fields)} left fields from {from_table}")
                
                # Restore selection if it still exists
                if preserve_selections and left_current in fields:
                    index = left_combo.findText(left_current)
                    if index >= 0:
                        left_combo.setCurrentIndex(index)
                        print(f"      [_load_field_lists] Row {idx} - Restored left field: '{left_current}'")
            left_combo.blockSignals(prev_left_block)
            
            # Load JOIN table fields (right side)
            prev_right_block = right_combo.blockSignals(True)
            right_combo.clear()
            if join_table:
                fields = self._get_table_fields(join_table)
                right_combo.addItems(fields)
                print(f"      [_load_field_lists] Row {idx} - Loaded {len(fields)} right fields from {join_table}")
                
                # Restore selection if it still exists
                if preserve_selections and right_current in fields:
                    index = right_combo.findText(right_current)
                    if index >= 0:
                        right_combo.setCurrentIndex(index)
                        print(f"      [_load_field_lists] Row {idx} - Restored right field: '{right_current}'")
            right_combo.blockSignals(prev_right_block)

        # Update debug panel on parent
        if self.parent_screen and hasattr(self.parent_screen, '_update_join_debug_panel'):
            try:
                self.parent_screen._update_join_debug_panel()
            except Exception as _e:
                print(f"      [_load_field_lists] Debug panel update error: {_e}")

    def _get_table_fields(self, table_name):
        """Get list of fields for a table"""
        if not self.parent_screen or not hasattr(self.parent_screen, 'schema_discovery'):
            return []
        
        try:
            connection_id = self.parent_screen.current_connection_id
            schema_name = self.parent_screen.current_schema_name or ''
            
            columns = self.parent_screen.schema_discovery.get_columns(
                connection_id, table_name, schema_name
            )
            return [col['column_name'] for col in columns]
        except Exception as e:
            logger.error(f"Error loading fields for {table_name}: {e}")
            return []
    
    def _on_left_field_changed(self, left_field_combo, right_field_combo):
        """Auto-populate right field to match left field when user changes it.

        Only triggers on REAL user changes, not during:
        - Query restoration (_loading_query flag)
        - Programmatic updates (blocked signals)

        If the matching field exists in the right combo, set it.
        Otherwise, leave the right combo unchanged.
        """
        # Skip if we're loading a query (restoration in progress)
        if self.parent_screen and hasattr(self.parent_screen, '_loading_query'):
            if self.parent_screen._loading_query:
                return

        # Skip if signals are blocked (programmatic change)
        if left_field_combo.signalsBlocked():
            return

        selected_field = left_field_combo.currentText()
        if not selected_field:
            return

        # Try to match the right field to the left field
        index = right_field_combo.findText(selected_field)
        if index >= 0:
            right_field_combo.setCurrentIndex(index)
            print(f"      [AUTO-MATCH] Set right field to match left: '{selected_field}'")

    def get_join_config(self):
        """Get JOIN configuration as dict"""
        on_conditions = []
        for row_data in self.on_condition_rows:
            left_field = row_data['left_field_combo'].currentText()
            right_field = row_data['right_field_combo'].currentText()
            operator = row_data.get('operator_combo', None)
            operator_text = operator.currentText() if operator else '='
            
            if left_field and right_field:
                on_conditions.append({
                    'left_field': left_field,
                    'right_field': right_field,
                    'operator': operator_text
                })
        
        return {
            'join_type': self.join_type_combo.currentText(),
            'join_table': self.join_table_combo.currentText(),
            'on_conditions': on_conditions
        }


class ValueSelectionDialog(QWidget):
    """Popup dialog for selecting values from a larger list"""
    
    values_selected = pyqtSignal(list)  # Emit selected values when dialog closes
    
    def __init__(self, field_name: str, unique_values: list, 
                 currently_selected: list = None, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.field_name = field_name
        self.unique_values = unique_values
        self.currently_selected = currently_selected or []
        self.value_checkboxes = []
        self.init_ui()
        
    def init_ui(self):
        """Initialize the dialog UI"""
        self.setWindowTitle(f"Select Values - {self.field_name}")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        title = QLabel(f"Select values for: {self.field_name}")
        title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        layout.addWidget(title)
        
        # Search box
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Type to filter values...")
        self.search_box.textChanged.connect(self._filter_values)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_box)
        layout.addLayout(search_layout)
        
        # Select All / Deselect All buttons
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self._deselect_all)
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(deselect_all_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Scrollable checkbox area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 1px solid #ccc;
                border-radius: 3px;
                background: white;
            }
        """)
        
        checkbox_widget = QWidget()
        self.checkbox_layout = QVBoxLayout(checkbox_widget)
        self.checkbox_layout.setSpacing(2)
        self.checkbox_layout.setContentsMargins(5, 5, 5, 5)
        
        # Add checkboxes for each value
        for value in self.unique_values:
            cb = QCheckBox(str(value))
            cb.setStyleSheet("padding: 2px;")
            
            # Check if this value was previously selected
            if value in self.currently_selected:
                cb.setChecked(True)
            
            self.value_checkboxes.append(cb)
            self.checkbox_layout.addWidget(cb)
        
        self.checkbox_layout.addStretch()
        scroll.setWidget(checkbox_widget)
        layout.addWidget(scroll)
        
        # OK / Cancel buttons
        ok_cancel_layout = QHBoxLayout()
        ok_cancel_layout.addStretch()
        
        ok_btn = QPushButton("OK")
        ok_btn.setMinimumWidth(80)
        ok_btn.clicked.connect(self._on_ok)
        ok_cancel_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(80)
        cancel_btn.clicked.connect(self.close)
        ok_cancel_layout.addWidget(cancel_btn)
        
        layout.addLayout(ok_cancel_layout)
        
    def _filter_values(self, text):
        """Filter checkboxes based on search text"""
        text = text.lower()
        for cb in self.value_checkboxes:
            value_text = cb.text().lower()
            cb.setVisible(text in value_text)
    
    def _select_all(self):
        """Select all visible checkboxes"""
        for cb in self.value_checkboxes:
            if cb.isVisible():
                cb.setChecked(True)
    
    def _deselect_all(self):
        """Deselect all visible checkboxes"""
        for cb in self.value_checkboxes:
            if cb.isVisible():
                cb.setChecked(False)
    
    def _on_ok(self):
        """Collect selected values and emit signal"""
        selected = []
        for cb in self.value_checkboxes:
            if cb.isChecked():
                # Get original value (not string representation)
                idx = self.value_checkboxes.index(cb)
                selected.append(self.unique_values[idx])
        
        self.values_selected.emit(selected)
        self.close()
    
    def get_selected_values(self):
        """Get currently selected values"""
        selected = []
        for cb in self.value_checkboxes:
            if cb.isChecked():
                idx = self.value_checkboxes.index(cb)
                selected.append(self.unique_values[idx])
        return selected


class DraggableFieldsTree(QTreeWidget):
    """Tree widget with custom drag behavior for fields"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.DragOnly)

    def startDrag(self, supportedActions):
        """Start drag operation with field data"""
        item = self.currentItem()
        if not item:
            logger.warning("No item selected for drag")
            return

        item_type = item.data(0, Qt.ItemDataRole.UserRole)
        
        # If trying to drag a unique value child, get the parent field instead
        if item_type == "unique_value" or item_type is None:
            parent = item.parent()
            if parent and parent.data(0, Qt.ItemDataRole.UserRole) == "field":
                item = parent
                item_type = "field"
            else:
                logger.warning(f"Cannot drag item of type: {item_type}")
                return
        
        if item_type != "field":
            logger.warning(f"Skipping drag for item type: {item_type}")
            return

        # Get field data
        field_name = item.data(0, Qt.ItemDataRole.UserRole + 1)
        data_type = item.data(0, Qt.ItemDataRole.UserRole + 2)
        table_name = item.data(0, Qt.ItemDataRole.UserRole + 3)
        schema_name = item.data(0, Qt.ItemDataRole.UserRole + 4)
        
        # Validate we have the required data
        if not field_name or not table_name:
            logger.error(f"Invalid field data: field_name={field_name}, table_name={table_name}")
            return

        # Create field data dict
        import json
        field_data = {
            'field_name': field_name,
            'data_type': data_type,
            'table_name': table_name,
            'schema_name': schema_name
        }
        
        logger.info(f"Starting drag for field: {table_name}.{field_name}")

        # Create drag
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(json.dumps(field_data))
        drag.setMimeData(mime_data)

        # Execute drag
        drag.exec(Qt.DropAction.CopyAction)
