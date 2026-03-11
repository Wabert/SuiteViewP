"""
Test the new browser-style bookmark bar with drag and drop support
"""

import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
from suiteview.ui.dialogs.shortcuts_dialog import BookmarkBar

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bookmark Bar Test - Drag & Drop Enabled")
        self.resize(1000, 300)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Add bookmark bar
        self.bookmark_bar = BookmarkBar()
        self.bookmark_bar.navigate_to_path.connect(self.on_navigate)
        layout.addWidget(self.bookmark_bar)
        
        # Add instructions
        instructions = QLabel(
            "<h3>Bookmark Bar Test</h3>"
            "<ul>"
            "<li>⭐ Click the star to add a bookmark</li>"
            "<li>🗂️ Drag files/folders from File Navigator onto the bar to add them</li>"
            "<li>📁 Drag onto category buttons to add to that category</li>"
            "<li>↔️ Drag bookmark buttons to reorder them</li>"
            "<li>🖱️ Right-click bookmarks to edit or delete</li>"
            "</ul>"
        )
        instructions.setStyleSheet("padding: 20px; background-color: #F0F0F0;")
        layout.addWidget(instructions)
        
        layout.addStretch()
        
    def on_navigate(self, path):
        print(f"Navigate to: {path}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())
