"""Main Window - SuiteView Data Manager"""

import logging
from pathlib import Path
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from suiteview.ui.connections_screen import ConnectionsScreen
from suiteview.ui.mydata_screen import MyDataScreen
from suiteview.ui.dbquery_screen import DBQueryScreen
from suiteview.ui.xdbquery_screen import XDBQueryScreen

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

        self.tab_widget.addTab(self.connections_screen, "Connections")
        self.tab_widget.addTab(self.mydata_screen, "My Data")
        self.tab_widget.addTab(self.dbquery_screen, "DB Query")
        self.tab_widget.addTab(self.xdbquery_screen, "XDB Query")

        # Connect signals between screens
        # When saved tables change in Connections, refresh My Data
        self.connections_screen.saved_tables_changed.connect(self.mydata_screen.refresh)
        
        # When connections are added/edited/deleted, refresh all screens
        self.connections_screen.connections_changed.connect(self.mydata_screen.load_my_data)
        self.connections_screen.connections_changed.connect(self.dbquery_screen.load_data_sources)

        # Add tab widget to layout
        layout.addWidget(self.tab_widget)

        # Load and apply stylesheet
        self.load_stylesheet()

        logger.info("UI initialized successfully")

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
