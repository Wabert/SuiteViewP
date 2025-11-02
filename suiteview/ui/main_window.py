"""Main Window - SuiteView Data Manager"""

import logging
from pathlib import Path
from PyQt6.QtWidgets import QMainWindow, QTabWidget, QWidget, QVBoxLayout, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor

from suiteview.ui.connections_screen import ConnectionsScreen
from suiteview.ui.mydata_screen import MyDataScreen
from suiteview.ui.dbquery_screen import DBQueryScreen
from suiteview.ui.xdbquery_screen import XDBQueryScreen
from suiteview.ui.mainframe_nav_screen import MainframeNavScreen
from suiteview.ui.file_explorer_screen import FileExplorerScreen

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window with tab navigation"""

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.tray_icon = None
        self.is_closing = False  # Flag to track real close vs minimize to tray
        self.init_ui()
        self.init_system_tray()
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
        self.file_explorer_screen = FileExplorerScreen()

        # Add tabs in order - Connections LAST
        self.tab_widget.addTab(self.mydata_screen, "My Data")
        self.tab_widget.addTab(self.dbquery_screen, "DB Query")
        self.tab_widget.addTab(self.xdbquery_screen, "XDB Query")
        self.tab_widget.addTab(self.mainframe_nav_screen, "Mainframe Nav")
        self.tab_widget.addTab(self.file_explorer_screen, "Text File Explorer")
        self.tab_widget.addTab(self.connections_screen, "Connections")

        # Connect signals between screens
        # When saved tables change in Connections, refresh both My Data and DB Query
        self.connections_screen.saved_tables_changed.connect(self.mydata_screen.refresh)
        self.connections_screen.saved_tables_changed.connect(self.dbquery_screen.load_data_sources)
        
        # When connections are added/edited/deleted, refresh all screens
        self.connections_screen.connections_changed.connect(self.mydata_screen.load_my_data)
        self.connections_screen.connections_changed.connect(self.dbquery_screen.load_data_sources)
        self.connections_screen.connections_changed.connect(self.xdbquery_screen.load_data_sources)
        
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

    def create_tray_icon(self):
        """Create a simple icon for the system tray"""
        # Create a 64x64 icon with a blue background and white 'S'
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw blue circle background
        painter.setBrush(QColor(25, 118, 210))  # Material Blue
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 60, 60)
        
        # Draw white 'S' letter
        painter.setPen(QColor(255, 255, 255))
        font = painter.font()
        font.setPointSize(36)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "S")
        
        painter.end()
        
        return QIcon(pixmap)

    def init_system_tray(self):
        """Initialize the system tray icon"""
        # Create tray icon
        icon = self.create_tray_icon()
        self.tray_icon = QSystemTrayIcon(icon, self)
        
        # Create tray menu
        tray_menu = QMenu()
        
        # Show/Restore action
        show_action = QAction("Show SuiteView", self)
        show_action.triggered.connect(self.show_from_tray)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        # Quit action
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        # Set menu to tray icon
        self.tray_icon.setContextMenu(tray_menu)
        
        # Connect double-click to show window
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
        # Show the tray icon
        self.tray_icon.show()
        
        # Show message on first run
        self.tray_icon.showMessage(
            "SuiteView Data Manager",
            "Application is running in system tray",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
        
        logger.info("System tray icon initialized")

    def tray_icon_activated(self, reason):
        """Handle tray icon activation (click/double-click)"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger or \
           reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_from_tray()

    def show_from_tray(self):
        """Show and restore the window from system tray"""
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.activateWindow()
        self.raise_()
        logger.info("Window restored from system tray")

    def closeEvent(self, event):
        """Override close event to minimize to tray instead of closing"""
        if not self.is_closing:
            # Minimize to tray instead of closing
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "SuiteView Data Manager",
                "Application minimized to tray. Right-click the tray icon to quit.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
            logger.info("Window minimized to system tray")
        else:
            # Actually closing the application
            if self.tray_icon:
                self.tray_icon.hide()
            event.accept()
            logger.info("Application closing")

    def quit_application(self):
        """Quit the application for real"""
        reply = QMessageBox.question(
            self,
            "Quit SuiteView",
            "Are you sure you want to quit SuiteView Data Manager?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.is_closing = True
            self.close()

