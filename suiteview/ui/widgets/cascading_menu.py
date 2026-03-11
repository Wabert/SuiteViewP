"""
Cascading Menu Widget

A reusable widget that displays vertically stacked buttons with cascading menus.
"""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QFrame
from PyQt6.QtCore import Qt


class CascadingMenuWidget(QWidget):
    """Simple widget with vertically stacked buttons that show cascading menus on click"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Create vertical layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Track currently open menu
        self.current_button = None
        self.current_menu = None
        
        # Style for the container - slightly different light blue
        self.setStyleSheet("""
            QWidget {
                background-color: #D8E8FF;
            }
        """)
        
    def add_menu_item(self, text, menu, enabled=True):
        """Add a button with a cascading menu"""
        btn = QPushButton(text, self)
        btn.setEnabled(enabled)
        
        # Style the button to look like tree items - slightly different light blue
        btn.setStyleSheet("""
            QPushButton {
                background-color: #D8E8FF;
                border: none;
                border-bottom: 1px solid #B0C8E8;
                padding: 2px 8px;
                text-align: left;
                font-size: 11px;
                color: #0A1E5E;
                min-height: 18px;
                max-height: 18px;
            }
            QPushButton:hover {
                background-color: #C8DFFF;
            }
            QPushButton:pressed {
                background-color: #A8C8F0;
            }
        """)
        
        # Style the cascading menu with fine border and light blue background
        menu.setStyleSheet("""
            QMenu {
                background-color: #E8F0FF;
                border: 1px solid #6BA3E8;
                padding: 2px;
            }
            QMenu::item {
                background-color: #E8F0FF;
                color: #0A1E5E;
                padding: 4px 20px 4px 10px;
                border: none;
            }
            QMenu::item:selected {
                background-color: #6BA3E8;
                color: white;
            }
            QMenu::item:disabled {
                color: #7f8c8d;
            }
        """)
        
        # Connect click to show menu to the right
        btn.clicked.connect(lambda: self._show_menu_to_right(btn, menu))
        
        self.layout.addWidget(btn)
        
    def _show_menu_to_right(self, button, menu):
        """Show the menu to the right of the button, or close if already open"""
        # If this button's menu is already open, close it
        if self.current_button == button and self.current_menu and self.current_menu.isVisible():
            self.current_menu.close()
            self.current_button = None
            self.current_menu = None
            return
        
        # Close any previously open menu
        if self.current_menu and self.current_menu.isVisible():
            self.current_menu.close()
        
        # Get the button's geometry
        button_rect = button.rect()
        # Calculate position to the right of the button
        global_pos = button.mapToGlobal(button_rect.topRight())
        
        # Show the menu (non-blocking)
        menu.popup(global_pos)
        
        # Track this as the current menu
        self.current_button = button
        self.current_menu = menu
        
        # Connect to aboutToHide to clear tracking when menu closes
        menu.aboutToHide.connect(lambda: self._on_menu_closed())
    
    def _on_menu_closed(self):
        """Clear tracking when menu closes"""
        self.current_button = None
        self.current_menu = None
        
    def add_separator(self):
        """Add a visual separator"""
        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setMaximumHeight(1)
        separator.setStyleSheet("background: #ddd;")
        self.layout.addWidget(separator)
    
    def clear(self):
        """Remove all items"""
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
