"""Main Window - SuiteView Data Manager"""

import logging
from pathlib import Path
from PyQt6.QtWidgets import (QMainWindow, QTabWidget, QWidget, QVBoxLayout, 
                              QMessageBox, QLabel, QStatusBar, QSplitter, QTextEdit,
                              QHBoxLayout, QPushButton, QToolBar)
from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtGui import QIcon, QAction

from suiteview.ui.connections_screen import ConnectionsScreen
from suiteview.ui.mydata_screen import MyDataScreen
from suiteview.ui.dbquery_screen import DBQueryScreen
from suiteview.ui.xdbquery_screen import XDBQueryScreen
from suiteview.ui.mainframe_nav_screen import MainframeNavScreen

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window with tab navigation"""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.init_ui()
        logger.info("Main window initialized")

    def init_ui(self):
        """Initialize the UI"""
        # Set window properties
        self.setWindowTitle(self.config.app_name)
        self.resize(self.config.window_width, self.config.window_height)
        self.setMinimumSize(self.config.window_min_width, self.config.window_min_height)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create main layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create tab widget (ribbon navigation)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.tab_widget.setDocumentMode(True)

        # Create and add screens as tabs
        self.connections_screen = ConnectionsScreen()
        self.mydata_screen = MyDataScreen()
        self.dbquery_screen = DBQueryScreen()
        self.xdbquery_screen = XDBQueryScreen()
        self.mainframe_nav_screen = MainframeNavScreen(self.connections_screen.conn_manager)

        # Add tabs in order
        self.tab_widget.addTab(self.mydata_screen, "My Data")
        self.tab_widget.addTab(self.dbquery_screen, "DB Query")
        self.tab_widget.addTab(self.xdbquery_screen, "XDB Query")
        self.tab_widget.addTab(self.mainframe_nav_screen, "Mainframe Nav")
        self.tab_widget.addTab(self.connections_screen, "Connections")

        # Connect signals between screens
        # When saved tables change in Connections, refresh both My Data and DB Query
        self.connections_screen.saved_tables_changed.connect(self.mydata_screen.refresh)
        self.connections_screen.saved_tables_changed.connect(self.dbquery_screen.load_data_sources)
        
        # When connections are added/edited/deleted, refresh all screens
        self.connections_screen.connections_changed.connect(self.mydata_screen.load_my_data)
        self.connections_screen.connections_changed.connect(self.dbquery_screen.load_data_sources)
        self.connections_screen.connections_changed.connect(self.xdbquery_screen.load_data_sources)
        
        # Synchronize query folders between My Data and DB Query screens
        self.mydata_screen.queries_changed.connect(self.dbquery_screen._load_db_queries_tree)
        self.dbquery_screen.queries_changed.connect(self.mydata_screen._load_db_queries)
        
        # When mainframe FTP connection is selected, switch to Mainframe Nav tab and load it
        self.connections_screen.mainframe_connection_selected.connect(self.on_mainframe_connection_selected)

        # Add tab widget to layout
        layout.addWidget(self.tab_widget)

        # Load and apply stylesheet
        self.load_stylesheet()

        logger.info("UI initialized successfully")

    def on_mainframe_connection_selected(self, connection_id: int):
        """Handle mainframe FTP connection selection - switch to Mainframe Nav tab"""
        # Find the index of the Mainframe Nav tab
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Mainframe Nav":
                # Switch to Mainframe Nav tab
                self.tab_widget.setCurrentIndex(i)
                
                # Load the connection in the Mainframe Nav screen
                self.mainframe_nav_screen.set_connection(connection_id)
                break

    def load_stylesheet(self):
        """Load and apply Qt stylesheet"""
        try:
            # Get path to styles.qss
            ui_dir = Path(__file__).parent
            style_file = ui_dir / 'styles.qss'

            if style_file.exists():
                with open(style_file, 'r') as f:
                    stylesheet = f.read()
                    self.setStyleSheet(stylesheet)
                    logger.info(f"Stylesheet loaded from: {style_file}")
            else:
                logger.warning(f"Stylesheet not found: {style_file}")
        except Exception as e:
            logger.error(f"Error loading stylesheet: {e}")

