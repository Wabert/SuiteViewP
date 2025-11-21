"""
Test File Explorer Core - Custom Model with OneDrive at Top Level
Run this standalone without importing suiteview.main
"""

if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication
    from suiteview.ui.file_explorer_core import FileExplorerCore

    app = QApplication(sys.argv)
    
    # Create and show file explorer
    explorer = FileExplorerCore()
    explorer.setWindowTitle("File Explorer Core - OneDrive at Top Level")
    explorer.resize(1200, 700)
    explorer.show()
    
    sys.exit(app.exec())
