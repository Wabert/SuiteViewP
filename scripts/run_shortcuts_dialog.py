"""
Standalone Shortcuts/Bookmarks Dialog Launcher
Run the Bookmarks Dialog directly for testing
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import suiteview
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from suiteview.ui.dialogs.shortcuts_dialog import BookmarksDialog

def main():
    app = QApplication(sys.argv)
    
    dialog = BookmarksDialog()
    dialog.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
