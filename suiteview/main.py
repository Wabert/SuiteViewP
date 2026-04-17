#!/usr/bin/env python3
"""SuiteView Data Manager - Main entry point"""

import sys
import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar

logger = logging.getLogger(__name__)


def _check_single_instance():
    """Ensure only one instance of SuiteView is running.
    
    Returns True if this is the first instance, False if another is already running.
    """
    try:
        import ctypes
        import ctypes.wintypes as wt
        # Use use_last_error=True so ctypes captures GetLastError reliably
        _kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        _kernel32.CreateMutexW.argtypes = [wt.LPVOID, wt.BOOL, wt.LPCWSTR]
        _kernel32.CreateMutexW.restype = wt.HANDLE
        mutex = _kernel32.CreateMutexW(None, True, "SuiteView_SingleInstance_Mutex")
        ERROR_ALREADY_EXISTS = 183
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            # Try to find and activate the existing SuiteView window
            hwnd = ctypes.windll.user32.FindWindowW(None, "SuiteView")
            if hwnd:
                SW_RESTORE = 9
                ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            return False
        # Keep a reference so the mutex isn't garbage-collected
        _check_single_instance._mutex = mutex
        return True
    except Exception:
        # If mutex check fails (non-Windows), allow launch
        return True


def main():
    """Application entry point"""
    # Prevent multiple instances
    if not _check_single_instance():
        sys.exit(0)

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
        suiteview = SuiteViewTaskbar()
        suiteview.setWindowTitle("SuiteView")
        # Window starts in compact mini-bar mode at bottom-right corner
        # (positioning is handled inside SuiteViewTaskbar.__init__)
        
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
