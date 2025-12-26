"""
Mainframe Window - Dedicated window for Mainframe Navigation and Terminal
"""

import logging
from PyQt6.QtWidgets import (QMainWindow, QTabWidget, QWidget, QVBoxLayout, QStatusBar, QLabel)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize

from suiteview.ui.mainframe_nav_screen import MainframeNavScreen
from suiteview.ui.mainframe_terminal_screen import DualTerminalScreen
from suiteview.core.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

class MainframeWindow(QMainWindow):
    """Dedicated window for Mainframe tools"""

    def __init__(self):
        super().__init__()
        self.conn_manager = ConnectionManager()
        self.init_ui()
        logger.info("Mainframe window initialized")

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("SuiteView - Mainframe Tools")
        self.resize(1400, 800)
        # Allow window to be resized quite small
        self.setMinimumSize(600, 400)

        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create main layout
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.tab_widget.setDocumentMode(True)

        # Create screens
        self.mainframe_nav_screen = MainframeNavScreen(self.conn_manager)
        self.mainframe_terminal_screen = DualTerminalScreen()

        # Add tabs - Terminal first
        self.tab_widget.addTab(self.mainframe_terminal_screen, "Mainframe Terminal")
        self.tab_widget.addTab(self.mainframe_nav_screen, "Mainframe Nav")

        # Add tab widget to layout
        layout.addWidget(self.tab_widget)
        
        # Add status bar with size display
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.size_label = QLabel()
        self.size_label.setStyleSheet("color: #888; font-size: 11px; padding: 2px 5px;")
        self.statusBar.addPermanentWidget(self.size_label)
        self._update_size_label()
    
    def resizeEvent(self, event):
        """Handle window resize to update size display"""
        super().resizeEvent(event)
        self._update_size_label()
    
    def _update_size_label(self):
        """Update the size label with current window dimensions"""
        size = self.size()
        self.size_label.setText(f"{size.width()} x {size.height()}")
        
    def closeEvent(self, event):
        """Handle window close"""
        # Disconnect terminals if connected
        if hasattr(self.mainframe_terminal_screen, 'disconnect_all'):
            self.mainframe_terminal_screen.disconnect_all()
        elif hasattr(self.mainframe_terminal_screen, 'disconnect_from_mainframe'):
            self.mainframe_terminal_screen.disconnect_from_mainframe()
            
        super().closeEvent(event)
