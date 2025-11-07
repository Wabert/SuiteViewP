"""
Test script for Bookmarks Dialog
"""

import sys
from PyQt6.QtWidgets import QApplication
from suiteview.ui.dialogs.shortcuts_dialog import BookmarksDialog

def main():
    app = QApplication(sys.argv)
    
    dialog = BookmarksDialog()
    dialog.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
