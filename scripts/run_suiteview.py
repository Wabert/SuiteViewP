"""
SuiteView - Main Application Launcher
The unified SuiteView experience with File Navigator, system tray, and access to all tools.

``main(local_data=False)`` launches the full taskbar.  When ``local_data=True`` it
sets ``SUITEVIEW_LOCAL_DATA=1`` (offline SQLite fixtures) and uses a DISTINCT
single-instance mutex + window title, so a LOCAL-DATA instance is independent of a
live one and never silently refocuses it.  ``scripts/run_suiteview_local.py`` is the
thin local-mode entry point.
"""


def main(local_data: bool = False):
    import sys
    from pathlib import Path
    import traceback

    # Add parent directory to path so we can import suiteview
    _root = Path(__file__).parent.parent
    sys.path.insert(0, str(_root))

    # Local-data mode must be enabled BEFORE any policy/DB lookup happens.
    if local_data:
        import os
        os.environ["SUITEVIEW_LOCAL_DATA"] = "1"

    # Distinct identity so a LOCAL instance never collides with / refocuses a live one.
    app_title = "SuiteView (LOCAL DATA)" if local_data else "SuiteView"
    mutex_name = ("SuiteView_Local_SingleInstance_Mutex" if local_data
                  else "SuiteView_SingleInstance_Mutex")
    appusermodel_id = "SuiteView.LocalData.1" if local_data else "SuiteView.FileExplorer.1"

    # Custom exception handler to catch Qt crashes
    def exception_hook(exctype, value, tb):
        print("UNHANDLED EXCEPTION:")
        traceback.print_exception(exctype, value, tb)
        sys.__excepthook__(exctype, value, tb)

    sys.excepthook = exception_hook

    try:
        from suiteview.taskbar_launcher.single_instance import acquire_or_activate

        titles = (app_title,)
        if not acquire_or_activate(mutex_name, titles):
            sys.exit(0)

        from suiteview.core.profile_maintenance import initialize_profile
        from suiteview.core.profile_paths import profile_path
        initialize_profile()
        _crash_log = profile_path(
            "suiteview_local_crash.log" if local_data else "suiteview_crash.log"
        )
        if sys.executable.lower().endswith("pythonw.exe"):
            _crash_log.parent.mkdir(parents=True, exist_ok=True)
            _crash_fh = open(_crash_log, "a", encoding="utf-8")
            sys.stderr = _crash_fh
            sys.stdout = _crash_fh

        # Set Windows AppUserModelID for proper taskbar icon display
        # This must be done before creating QApplication
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appusermodel_id)
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

        from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar

        # Create application - don't quit when last window closes (we have tray)
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        # Create and show the main SuiteView window
        suiteview = SuiteViewTaskbar()

        # Set application-level icon for taskbar
        app.setWindowIcon(suiteview._build_suiteview_icon(64))

        suiteview.setWindowTitle(app_title)
        # Window starts in compact mini-bar mode at bottom-right corner
        # (positioning is handled inside SuiteViewTaskbar.__init__)

        suiteview.show()
        suiteview.raise_()
        suiteview.activateWindow()

        sys.exit(app.exec())

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        from PyQt6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Cannot Start SuiteView", str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
