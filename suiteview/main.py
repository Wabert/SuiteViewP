#!/usr/bin/env python3
"""SuiteView Data Manager - Main entry point"""

import sys
import os
import logging
import traceback
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar

logger = logging.getLogger(__name__)

# -- Crash log setup -------------------------------------------------------
_LOG_DIR = Path.home() / ".suiteview"
_CRASH_LOG = _LOG_DIR / "crash.log"


def _setup_crash_log():
    """Configure logging to write to ~/.suiteview/crash.log and install
    a global exception hook so unhandled errors are captured even when
    the exe is launched by double-click (no console)."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(_CRASH_LOG, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
    )
    logging.root.addHandler(file_handler)
    logging.root.setLevel(logging.INFO)

    # Rotate: keep only the last 500 KB
    try:
        if _CRASH_LOG.exists() and _CRASH_LOG.stat().st_size > 500_000:
            text = _CRASH_LOG.read_text(encoding="utf-8", errors="replace")
            _CRASH_LOG.write_text(text[-250_000:], encoding="utf-8")
    except Exception:
        pass

    def _excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.critical(
            "Unhandled exception:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )

    sys.excepthook = _excepthook

    logger.info("=" * 60)
    logger.info("SuiteView starting  %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


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
    _setup_crash_log()

    # Prevent multiple instances
    if not _check_single_instance():
        logger.info("Another instance already running — exiting")
        sys.exit(0)
    logger.info("Single-instance check passed")

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
            logging.getLogger("Qt").critical(message)
        elif mode == QtMsgType.QtFatalMsg:
            logging.getLogger("Qt").critical("FATAL: %s", message)
        # Suppress warnings for cleaner output
    
    qInstallMessageHandler(qt_message_handler)

    # Create Qt application - don't quit when last window closes (we have tray)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    logger.info("QApplication created")

    # Create and show the main SuiteView window
    try:
        logger.info("Creating SuiteViewTaskbar...")
        suiteview = SuiteViewTaskbar()
        logger.info("SuiteViewTaskbar created successfully")
        # Set window title based on executable name
        if getattr(sys, 'frozen', False) and 'SuiteViewLight' in sys.executable:
            suiteview.setWindowTitle("SuiteView Light")
        else:
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
