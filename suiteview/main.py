#!/usr/bin/env python3
"""SuiteView Data Manager - Main entry point"""

import sys
import logging
import traceback
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
from suiteview.taskbar_launcher.single_instance import acquire_or_activate
from suiteview.core.profile_maintenance import initialize_profile
from suiteview.core.profile_paths import profile_path

logger = logging.getLogger(__name__)

# -- Crash log setup -------------------------------------------------------
def _setup_crash_log():
    """Configure logging to write to the profile logs directory and install
    a global exception hook so unhandled errors are captured even when
    the exe is launched by double-click (no console)."""
    _CRASH_LOG = profile_path("crash.log")
    _CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)

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
    except OSError:
        logger.debug("Could not rotate SuiteView crash log", exc_info=True)

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


def main():
    """Application entry point"""
    # Prevent multiple instances
    if not acquire_or_activate():
        logger.info("Another instance already running — exiting")
        sys.exit(0)
    try:
        initialize_profile()
    except Exception as exc:
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Profile needs attention", str(exc))
        raise
    _setup_crash_log()
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
    except (ImportError, OSError):
        logger.debug("Could not clear win32com gen_py cache", exc_info=True)
    
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
        from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar

        logger.info("Creating SuiteViewTaskbar...")
        suiteview = SuiteViewTaskbar()
        logger.info("SuiteViewTaskbar created successfully")
        suiteview.setWindowTitle("SuiteView")
        # Window starts in compact mini-bar mode at bottom-right corner
        # (positioning is handled inside SuiteViewTaskbar.__init__)
        
        suiteview.show()
        suiteview.raise_()
        suiteview.activateWindow()
        
        logger.info("SuiteView File Navigator displayed")
    except Exception as e:
        logger.error(f"Failed to create SuiteView window: {e}", exc_info=True)
        QMessageBox.critical(None, "Cannot Start SuiteView", str(e))
        sys.exit(1)

    # Start event loop
    exit_code = app.exec()
    logger.info(f"Application exiting with code: {exit_code}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
