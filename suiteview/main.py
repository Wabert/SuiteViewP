#!/usr/bin/env python3
"""SuiteView Data Manager - Main entry point"""

import sys
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
from suiteview.ui.file_explorer_multitab import FileExplorerMultiTab

logger = logging.getLogger(__name__)


def main():
    """Application entry point"""
    # Clear corrupted win32com gen_py cache if it exists (prevents Excel export errors)
    try:
        import win32com
        import shutil
        import os
        if hasattr(win32com, '__gen_path__'):
            cache_path = os.path.join(win32com.__gen_path__, 'win32com', 'gen_py')
            if os.path.exists(cache_path):
                shutil.rmtree(cache_path, ignore_errors=True)
    except Exception:
        pass  # Silently ignore if clearing fails
    
    # Qt message handler (suppress non-critical warnings)
    def qt_message_handler(mode, context, message):
        if mode == QtMsgType.QtCriticalMsg:
            print(f"Qt Critical: {message}")
        elif mode == QtMsgType.QtFatalMsg:
            print(f"Qt Fatal: {message}")
        # Suppress warnings for cleaner output
    
    qInstallMessageHandler(qt_message_handler)

    # Create Qt application - don't quit when last window closes (we have tray)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Create and show the main SuiteView window
    try:
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
        
        logger.info("SuiteView File Navigator displayed")
    except Exception as e:
        logger.error(f"Failed to create SuiteView window: {e}", exc_info=True)
        sys.exit(1)

    # Start event loop
    exit_code = app.exec()
    logger.info(f"Application exiting with code: {exit_code}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
