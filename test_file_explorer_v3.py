"""
Test File Explorer V3 - Custom Model with OneDrive at Top Level
Run this standalone without importing suiteview.main
"""

if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication
    from suiteview.ui.file_explorer_v3 import FileExplorerV3

    app = QApplication(sys.argv)
    
    # Create and show file explorer
    explorer = FileExplorerV3()
    explorer.setWindowTitle("File Explorer V3 - OneDrive at Top Level")
    explorer.resize(1200, 700)
    explorer.show()
    
    sys.exit(app.exec())
