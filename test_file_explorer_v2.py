"""
Test the new File Explorer V2
Based on proaddy's PyQt-File-Explorer
"""

import sys
from PyQt6.QtWidgets import QApplication, QMainWindow
from suiteview.ui.file_explorer_v2 import FileExplorerV2


def main():
    app = QApplication(sys.argv)
    
    # Create a simple window to hold the file explorer
    window = QMainWindow()
    window.setWindowTitle("SuiteView - Enhanced File Explorer Test")
    window.resize(1200, 700)
    
    # Add the file explorer as central widget
    explorer = FileExplorerV2()
    window.setCentralWidget(explorer)
    
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
