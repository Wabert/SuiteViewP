"""
Standalone File Explorer Launcher
Run the File Explorer (Multi-Tab) in its own window
"""

if __name__ == '__main__':
    import sys
    from pathlib import Path
    from PyQt6.QtWidgets import QApplication
    from suiteview.ui.file_explorer_multitab import FileExplorerMultiTab
    from suiteview.utils.logger import setup_logging
    
    # Setup logging
    setup_logging()
    
    # Create Qt application
    app = QApplication(sys.argv)
    
    # Create and show file explorer with multi-tab support
    explorer = FileExplorerMultiTab()
    explorer.setWindowTitle("SuiteView File Explorer")
    explorer.resize(1400, 800)
    explorer.show()
    
    sys.exit(app.exec())
