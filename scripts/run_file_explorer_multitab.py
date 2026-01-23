"""
Standalone File Explorer Multi-Tab Launcher
Run the File Explorer with Multi-Tab and Breadcrumb Navigation directly
"""

if __name__ == '__main__':
    import sys
    from pathlib import Path
    
    # Add parent directory to path so we can import suiteview
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from PyQt6.QtWidgets import QApplication
    from suiteview.ui.file_explorer_multitab import FileExplorerMultiTab

    app = QApplication(sys.argv)
    
    # Create and show file explorer with tabs
    explorer = FileExplorerMultiTab()
    explorer.setWindowTitle("File Explorer - Multi-Tab Edition")
    explorer.resize(1400, 800)
    explorer.show()
    
    sys.exit(app.exec())
