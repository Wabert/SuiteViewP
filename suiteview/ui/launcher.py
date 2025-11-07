"""
SuiteView Launcher - Main always-on-top floating toolbar
Small resizable window with quick access to all SuiteView tools
"""

import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QHBoxLayout, QVBoxLayout,
                              QSystemTrayIcon, QMenu, QLabel)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize
from PyQt6.QtGui import QIcon, QAction, QPainter, QColor, QPen, QCursor, QLinearGradient, QPixmap

import logging
logger = logging.getLogger(__name__)


class LauncherWindow(QWidget):
    """
    Small always-on-top launcher window with tool buttons
    Features:
    - Always on top
    - Resizable from all edges
    - Movable by dragging anywhere in the window
    - System tray integration
    - Closes to tray instead of exiting
    """
    
    def __init__(self):
        super().__init__()
        
        # Remove window frame to create custom borderless window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        # Window state
        self.dragging = False
        self.resizing = False
        self.resize_direction = None
        self.drag_position = QPoint()
        self.resize_margin = 8  # Pixels from edge to trigger resize
        
        # Store references to opened windows
        self.db_window = None
        self.file_nav_window = None
        
        self.init_ui()
        self.setup_system_tray()
        
    def create_database_icon(self):
        """Create a custom database cylinder stack icon"""
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Set pen for outlines - thicker and darker for clarity
        painter.setPen(QPen(QColor("#003366"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Draw three database cylinders stacked with clearer separation
        # Top cylinder
        painter.drawEllipse(5, 2, 18, 6)
        painter.drawLine(5, 5, 5, 10)
        painter.drawLine(23, 5, 23, 10)
        painter.drawArc(5, 7, 18, 6, 180*16, 180*16)  # Bottom arc
        
        # Middle cylinder
        painter.drawLine(5, 10, 5, 15)
        painter.drawLine(23, 10, 23, 15)
        painter.drawArc(5, 12, 18, 6, 180*16, 180*16)  # Bottom arc
        
        # Bottom cylinder
        painter.drawLine(5, 15, 5, 20)
        painter.drawLine(23, 15, 23, 20)
        painter.drawEllipse(5, 17, 18, 6)  # Full bottom
        
        painter.end()
        
        return QIcon(pixmap)
        
    def init_ui(self):
        """Initialize the UI"""
        # Set window properties
        self.setMinimumSize(160, 60)
        self.resize(300, 75)
        
        # Position in bottom right corner of screen
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.width() - 20  # 20px from right edge
        y = screen.height() - self.height() - 60  # 60px from bottom (above taskbar)
        self.move(x, y)
        
        # Create main vertical layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 3, 6, 3)
        main_layout.setSpacing(1)
        
        # Top row: SuiteView label (left) and close button (right)
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(2)
        
        # SuiteView label at the top left in italics
        suiteview_label = QLabel("SuiteView")
        suiteview_label.setStyleSheet("""
            QLabel {
                background: transparent;
                border: none;
                color: #FFD700;
                font-size: 16px;
                font-weight: bold;
                font-style: italic;
                padding: 0px;
            }
        """)
        suiteview_label.setMaximumHeight(20)
        top_layout.addWidget(suiteview_label)
        
        # Add stretch to push close button to the right
        top_layout.addStretch()
        
        # Close button (×) in top right
        self.close_btn = QPushButton("×")
        self.close_btn.setToolTip("Minimize to tray")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #FFD700;
                font-size: 18px;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: #ff5555;
                color: white;
                border-radius: 10px;
            }
            QPushButton:pressed {
                background-color: #cc0000;
            }
        """)
        self.close_btn.clicked.connect(self.hide_to_tray)
        top_layout.addWidget(self.close_btn)
        
        main_layout.addLayout(top_layout)
        
        # Create horizontal layout for buttons (aligned left)
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)
        
        # Database Manager button - smaller size with database icon
        self.db_btn = QPushButton()
        self.db_btn.setIcon(self.create_database_icon())
        self.db_btn.setIconSize(QSize(24, 24))
        self.db_btn.setToolTip("Data Manager")
        self.db_btn.setFixedSize(32, 32)  # 2/3 of original 40x40
        self.db_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 2px solid #0078d4;
                border-radius: 6px;
                font-size: 18px;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
                border-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #bbdefb;
            }
        """)
        self.db_btn.clicked.connect(self.open_data_manager)
        button_layout.addWidget(self.db_btn)
        
        # File Navigator button - smaller size
        self.file_nav_btn = QPushButton("📁")  # Folder icon
        self.file_nav_btn.setToolTip("File Navigator")
        self.file_nav_btn.setFixedSize(32, 32)  # 2/3 of original 40x40
        self.file_nav_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 2px solid #0078d4;
                border-radius: 6px;
                font-size: 18px;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
                border-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #bbdefb;
            }
        """)
        self.file_nav_btn.clicked.connect(self.open_file_navigator)
        button_layout.addWidget(self.file_nav_btn)
        
        # Add stretch to keep buttons on the left
        button_layout.addStretch()
        
        # Add button layout to main vertical layout
        main_layout.addLayout(button_layout)
        
        # No stylesheet needed - we'll paint the background ourselves
        self.setStyleSheet("")
    
    def create_tray_icon(self):
        """Create the circular S icon for system tray"""
        from PyQt6.QtGui import QPixmap, QIcon, QPainter, QColor
        from PyQt6.QtCore import Qt
        
        # Create a 64x64 pixmap
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw blue circle background
        painter.setBrush(QColor(30, 144, 255))  # Dodger blue
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
        
    def setup_system_tray(self):
        """Setup system tray icon and menu"""
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(self)
        
        # Use circular S icon
        self.tray_icon.setIcon(self.create_tray_icon())
        
        # Create tray menu
        tray_menu = QMenu()
        
        show_action = QAction("Show Launcher", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        db_action = QAction("🗄️ Data Manager", self)
        db_action.triggered.connect(self.open_data_manager)
        tray_menu.addAction(db_action)
        
        file_action = QAction("📁 File Navigator", self)
        file_action.triggered.connect(self.open_file_navigator)
        tray_menu.addAction(file_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Quit SuiteView", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
        
        # Set tooltip
        self.tray_icon.setToolTip("SuiteView - Click to show launcher")
        
    def tray_icon_activated(self, reason):
        """Handle tray icon clicks"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Left click - show window
            self.show()
            self.activateWindow()
            
    def hide_to_tray(self):
        """Hide window to system tray"""
        self.hide()
        self.tray_icon.showMessage(
            "SuiteView",
            "Minimized to tray. Click the tray icon to restore.",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
        
    def quit_application(self):
        """Actually quit the application"""
        # Close all child windows
        if self.db_window:
            self.db_window.close()
        if self.file_nav_window:
            self.file_nav_window.close()
            
        self.tray_icon.hide()
        QApplication.quit()
        
    def open_data_manager(self):
        """Open the Data Manager window - maintains state throughout session"""
        if self.db_window is None:
            # Create window only once - first time
            try:
                from suiteview.ui.main_window import MainWindow
                from suiteview.utils.config import load_config
                
                # Load config for the Data Manager
                config = load_config()
                self.db_window = MainWindow(config)
                
                # Override close event to hide instead of closing
                original_close = self.db_window.closeEvent
                def hide_on_close(event):
                    event.ignore()
                    self.db_window.hide()
                self.db_window.closeEvent = hide_on_close
                
                self.db_window.show()
                logger.info("Created Data Manager (persists for session)")
            except Exception as e:
                logger.error(f"Failed to open Data Manager: {e}")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"Could not open Data Manager:\n{e}")
        else:
            # Window already exists - just show and activate it
            self.db_window.show()
            self.db_window.activateWindow()
            self.db_window.raise_()
            
    def open_file_navigator(self):
        """Open the File Navigator window - maintains state throughout session"""
        if self.file_nav_window is None:
            # Create window only once - first time
            try:
                from suiteview.ui.file_explorer_v4 import FileExplorerV4
                self.file_nav_window = FileExplorerV4()
                self.file_nav_window.setWindowTitle("SuiteView - File Navigator")
                self.file_nav_window.resize(1400, 800)
                
                # Override close event to hide instead of closing
                original_close = self.file_nav_window.closeEvent
                def hide_on_close(event):
                    event.ignore()
                    self.file_nav_window.hide()
                self.file_nav_window.closeEvent = hide_on_close
                
                self.file_nav_window.show()
                logger.info("Created File Navigator (persists for session)")
            except Exception as e:
                logger.error(f"Failed to open File Navigator: {e}")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"Could not open File Navigator:\n{e}")
        else:
            # Window already exists - just show and activate it
            self.file_nav_window.show()
            self.file_nav_window.activateWindow()
            self.file_nav_window.raise_()
    
    def paintEvent(self, event):
        """Custom paint to draw rounded background with gradient blue and gold border"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Fill with transparent first
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        
        # Create gradient from light blue → dark blue → light blue
        from PyQt6.QtGui import QLinearGradient
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0, QColor("#2563EB"))    # Light blue
        gradient.setColorAt(0.5, QColor("#1E3A8A"))  # Dark blue (middle)
        gradient.setColorAt(1, QColor("#2563EB"))    # Light blue
        
        # Draw rounded rectangle with gradient
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(self.rect(), 12, 12)
        
        # Draw gold border on top
        painter.setPen(QPen(QColor("#D4AF37"), 3))  # Gold border, 3px thick
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        
    def get_resize_direction(self, pos):
        """Determine which edge/corner the mouse is near for resizing"""
        rect = self.rect()
        margin = self.resize_margin
        
        left = pos.x() < margin
        right = pos.x() > rect.width() - margin
        top = pos.y() < margin
        bottom = pos.y() > rect.height() - margin
        
        if top and left:
            return 'top-left'
        elif top and right:
            return 'top-right'
        elif bottom and left:
            return 'bottom-left'
        elif bottom and right:
            return 'bottom-right'
        elif top:
            return 'top'
        elif bottom:
            return 'bottom'
        elif left:
            return 'left'
        elif right:
            return 'right'
        return None
        
    def update_cursor(self, direction):
        """Update cursor based on resize direction"""
        if direction in ['top', 'bottom']:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif direction in ['left', 'right']:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif direction in ['top-left', 'bottom-right']:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif direction in ['top-right', 'bottom-left']:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
    def mousePressEvent(self, event):
        """Handle mouse press for dragging and resizing"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if near edge for resizing
            direction = self.get_resize_direction(event.pos())
            
            if direction:
                self.resizing = True
                self.resize_direction = direction
                self.drag_position = event.globalPosition().toPoint()
                self.resize_start_geometry = self.geometry()
            else:
                # Start dragging
                self.dragging = True
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                
            event.accept()
        
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging, resizing, and cursor updates"""
        if self.resizing and self.resize_direction:
            # Resize window
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self.drag_position
            
            new_geo = QRect(self.resize_start_geometry)
            
            if 'left' in self.resize_direction:
                new_geo.setLeft(new_geo.left() + delta.x())
            if 'right' in self.resize_direction:
                new_geo.setRight(new_geo.right() + delta.x())
            if 'top' in self.resize_direction:
                new_geo.setTop(new_geo.top() + delta.y())
            if 'bottom' in self.resize_direction:
                new_geo.setBottom(new_geo.bottom() + delta.y())
                
            # Enforce minimum size
            if new_geo.width() >= self.minimumWidth() and new_geo.height() >= self.minimumHeight():
                self.setGeometry(new_geo)
                
        elif self.dragging:
            # Move window
            self.move(event.globalPosition().toPoint() - self.drag_position)
        else:
            # Update cursor based on position
            direction = self.get_resize_direction(event.pos())
            self.update_cursor(direction)
            
    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop dragging/resizing"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.resizing = False
            self.resize_direction = None
            
    def closeEvent(self, event):
        """Override close to hide to tray instead"""
        event.ignore()
        self.hide_to_tray()


def main():
    """Run the launcher"""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Don't quit when window closes
    
    launcher = LauncherWindow()
    launcher.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
