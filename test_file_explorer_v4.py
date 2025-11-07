"""
Test File Explorer V4 - Multi-Tab with Breadcrumb Navigation
"""

if __name__ == '__main__':
    import sys
    from pathlib import Path
    from PyQt6.QtWidgets import QApplication
    from suiteview.ui.file_explorer_v4 import FileExplorerV4

    app = QApplication(sys.argv)
    
    # Create and show file explorer with tabs
    explorer = FileExplorerV4()
    explorer.setWindowTitle("File Explorer V4 - Multi-Tab Edition")
    explorer.resize(1400, 800)
    explorer.show()
    
    sys.exit(app.exec())
