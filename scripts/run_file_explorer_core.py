"""
Standalone File Explorer Core Launcher
Run the File Explorer Core (Custom Model with OneDrive at Top Level) directly
"""

if __name__ == '__main__':
    import sys
    from pathlib import Path
    
    # Add parent directory to path so we can import suiteview
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from PyQt6.QtWidgets import QApplication
    from suiteview.ui.file_explorer_core import FileExplorerCore

    app = QApplication(sys.argv)
    
    # Create and show file explorer
    explorer = FileExplorerCore()
    explorer.setWindowTitle("File Explorer Core - OneDrive at Top Level")
    explorer.resize(1200, 700)
    explorer.show()
    
    sys.exit(app.exec())
