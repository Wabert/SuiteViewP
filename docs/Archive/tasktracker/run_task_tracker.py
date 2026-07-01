"""
Standalone Task Tracker Launcher
Run the Task Tracker window directly without the full SuiteView app
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import suiteview
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from suiteview.tasktracker import TaskTrackerWindow


def main():
    app = QApplication(sys.argv)
    
    window = TaskTrackerWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
