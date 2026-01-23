"""
Standalone Launcher Script
Run the SuiteView Launcher window directly
"""

if __name__ == '__main__':
    import sys
    from pathlib import Path
    
    # Add parent directory to path so we can import suiteview
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from PyQt6.QtWidgets import QApplication
    from suiteview.ui.launcher import LauncherWindow
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Don't quit when launcher closes to tray
    
    launcher = LauncherWindow()
    launcher.show()
    
    sys.exit(app.exec())
