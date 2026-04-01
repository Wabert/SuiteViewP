"""
Standalone File Explorer Multi-Tab Launcher
Run the File Explorer with Multi-Tab and Breadcrumb Navigation directly
"""

if __name__ == '__main__':
    import sys
    from pathlib import Path
    import traceback
    
    # Add parent directory to path so we can import suiteview
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    # Set Windows App User Model ID - MUST be done before QApplication is created
    # This allows the taskbar to show the correct icon instead of Python's icon
    try:
        import ctypes
        myappid = 'anico.suiteview.fileexplorer.1'  # Arbitrary string
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass  # Non-Windows or other issue
    
    # Custom exception handler to catch Qt crashes
    def exception_hook(exctype, value, tb):
        print("UNHANDLED EXCEPTION:")
        traceback.print_exception(exctype, value, tb)
        sys.__excepthook__(exctype, value, tb)
    
    sys.excepthook = exception_hook
    
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
        
        # Qt message handler
        def qt_message_handler(mode, context, message):
            if mode == QtMsgType.QtWarningMsg:
                print(f"Qt Warning: {message}")
            elif mode == QtMsgType.QtCriticalMsg:
                print(f"Qt Critical: {message}")
            elif mode == QtMsgType.QtFatalMsg:
                print(f"Qt Fatal: {message}")
        
        qInstallMessageHandler(qt_message_handler)
        
        # Setup logging
        from suiteview.utils.logger import setup_logging
        setup_logging(log_level="INFO")
        
        from suiteview.file_nav.file_explorer_multitab import FileExplorerMultiTab

        app = QApplication(sys.argv)
        
        # Create and show file explorer with tabs
        print("Creating FileExplorerMultiTab...")
        explorer = FileExplorerMultiTab()
        
        # Set the application-level icon (helps Windows taskbar)
        app.setWindowIcon(explorer._build_suiteview_icon(64))
        
        print("Setting window title...")
        explorer.setWindowTitle("File Explorer - Multi-Tab Edition")
        print("Setting size...")
        explorer.resize(1400, 800)
        
        # Center the window on screen
        print("Centering window...")
        screen = app.primaryScreen().geometry()
        x = (screen.width() - explorer.width()) // 2
        y = (screen.height() - explorer.height()) // 2
        explorer.move(x, y)
        
        print("Showing window...")
        explorer.show()
        explorer.raise_()  # Bring to front
        explorer.activateWindow()  # Make active
        print("Starting event loop...")
        
        sys.exit(app.exec())
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        input("Press Enter to exit...")
        sys.exit(1)
