"""
Standalone Screenshot Manager Launcher
Run the Screenshot Manager window directly
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import suiteview
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from suiteview.ui.screenshot_manager_window import ScreenShotManagerWindow

def main():
    app = QApplication(sys.argv)
    
    window = ScreenShotManagerWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
