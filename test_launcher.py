"""
Test script for SuiteView Launcher
"""

if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication
    from suiteview.ui.launcher import LauncherWindow
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Don't quit when launcher closes to tray
    
    launcher = LauncherWindow()
    launcher.show()
    
    sys.exit(app.exec())
