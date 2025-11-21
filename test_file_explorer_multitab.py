"""
Test File Explorer Multi-Tab with Breadcrumb Navigation
"""

if __name__ == '__main__':
    import sys
    from pathlib import Path
    from PyQt6.QtWidgets import QApplication
    from suiteview.ui.file_explorer_multitab import FileExplorerMultiTab

    app = QApplication(sys.argv)
    
    # Create and show file explorer with tabs
    explorer = FileExplorerMultiTab()
    explorer.setWindowTitle("File Explorer - Multi-Tab Edition")
    explorer.resize(1400, 800)
    explorer.show()
    
    sys.exit(app.exec())
