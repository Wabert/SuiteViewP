"""
SuiteView - Main Application Launcher
The unified SuiteView experience with File Navigator, system tray, and access to all tools
"""

if __name__ == '__main__':
    import sys
    from pathlib import Path
    import traceback
    
    # Add parent directory to path so we can import suiteview
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    # Custom exception handler to catch Qt crashes
    def exception_hook(exctype, value, tb):
        print("UNHANDLED EXCEPTION:")
        traceback.print_exception(exctype, value, tb)
        sys.__excepthook__(exctype, value, tb)
    
    sys.excepthook = exception_hook
    
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
        
        # Qt message handler (suppress non-critical warnings)
        def qt_message_handler(mode, context, message):
            if mode == QtMsgType.QtCriticalMsg:
                print(f"Qt Critical: {message}")
            elif mode == QtMsgType.QtFatalMsg:
                print(f"Qt Fatal: {message}")
            # Suppress warnings for cleaner output
        
        qInstallMessageHandler(qt_message_handler)
        
        from suiteview.ui.file_explorer_multitab import FileExplorerMultiTab
        
        # Create application - don't quit when last window closes (we have tray)
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        
        # Create and show the main SuiteView window
        suiteview = FileExplorerMultiTab()
        suiteview.setWindowTitle("SuiteView")
        suiteview.resize(1400, 800)
        
        # Center the window on screen
        screen = app.primaryScreen().geometry()
        x = (screen.width() - suiteview.width()) // 2
        y = (screen.height() - suiteview.height()) // 2
        suiteview.move(x, y)
        
        suiteview.show()
        suiteview.raise_()
        suiteview.activateWindow()
        
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        input("Press Enter to exit...")
        sys.exit(1)
