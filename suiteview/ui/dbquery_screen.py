"""DB Query Screen - Single-database query builder"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSplitter
from PyQt6.QtCore import Qt


class DBQueryScreen(QWidget):
    """DB Query screen with four-panel layout"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create horizontal splitter for four panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel 1 - Data Sources
        panel1 = self.create_panel("DATA SOURCES")
        splitter.addWidget(panel1)

        # Left Panel 2 - Tables
        panel2 = self.create_panel("TABLES")
        splitter.addWidget(panel2)

        # Left Panel 3 - Fields
        panel3 = self.create_panel("FIELDS")
        splitter.addWidget(panel3)

        # Right Panel - Query Builder
        right_panel = self.create_panel("QUERY BUILDER")
        splitter.addWidget(right_panel)

        # Set initial sizes (200px, 200px, 200px, remaining)
        splitter.setSizes([200, 200, 200, 600])

        layout.addWidget(splitter)

    def create_panel(self, title: str) -> QWidget:
        """Create a placeholder panel with title"""
        panel = QWidget()
        panel.setObjectName("panel")

        layout = QVBoxLayout(panel)

        # Header
        header = QLabel(title)
        header.setObjectName("panel_header")
        layout.addWidget(header)

        # Content placeholder
        content = QLabel(f"{title}\n\n(Under Construction)")
        content.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.setStyleSheet("font-size: 16px; color: #D4AF37; font-weight: 600; padding: 40px;")
        layout.addWidget(content)

        return panel
