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
        # Set Windows AppUserModelID for proper taskbar icon display
        # This must be done before creating QApplication
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SuiteView.FileExplorer.1')
        except:
            pass  # Not on Windows or failed
        
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
        
        from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar
        
        # Create application - don't quit when last window closes (we have tray)
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        
        # Create and show the main SuiteView window
        suiteview = SuiteViewTaskbar()
        
        # Set application-level icon for taskbar
        app.setWindowIcon(suiteview._build_suiteview_icon(64))
        
        suiteview.setWindowTitle("SuiteView")
        # Window starts in compact mini-bar mode at bottom-right corner
        # (positioning is handled inside SuiteViewTaskbar.__init__)
        
        suiteview.show()
        suiteview.raise_()
        suiteview.activateWindow()
        
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        input("Press Enter to exit...")
        sys.exit(1)
