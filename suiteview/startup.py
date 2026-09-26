"""Canonical SuiteView application startup."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from datetime import datetime
import logging
import os
from pathlib import Path
import shutil
import sys
import traceback

from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
from PyQt6.QtWidgets import QApplication, QMessageBox

from suiteview.core.profile_maintenance import initialize_profile
from suiteview.core.profile_paths import profile_path
from suiteview.core.single_instance import acquire_or_activate

logger = logging.getLogger(__name__)
_REDIRECT_HANDLES = []


@dataclass(frozen=True)
class StartupOptions:
    """Identity and mode for a SuiteView process."""

    local_data: bool = False
    title: str | None = None
    mutex_name: str | None = None
    app_user_model_id: str | None = None
    crash_log_name: str | None = None
    redirect_pythonw_stdio: bool = True

    def __post_init__(self) -> None:
        local_title = "SuiteView (LOCAL DATA)" if self.local_data else "SuiteView"
        local_mutex = (
            "SuiteView_Local_SingleInstance_Mutex"
            if self.local_data
            else "SuiteView_SingleInstance_Mutex"
        )
        local_app_id = (
            "SuiteView.LocalData.1" if self.local_data else "SuiteView.FileExplorer.1"
        )
        local_log = (
            "suiteview_local_crash.log" if self.local_data else "suiteview_crash.log"
        )
        if self.title is None:
            object.__setattr__(self, "title", local_title)
        if self.mutex_name is None:
            object.__setattr__(self, "mutex_name", local_mutex)
        if self.app_user_model_id is None:
            object.__setattr__(self, "app_user_model_id", local_app_id)
        if self.crash_log_name is None:
            object.__setattr__(self, "crash_log_name", local_log)


def _crash_log_path(options: StartupOptions) -> Path:
    return profile_path(options.crash_log_name or "suiteview_crash.log")


def _setup_crash_log(options: StartupOptions) -> Path:
    crash_log = _crash_log_path(options)
    crash_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        if crash_log.exists() and crash_log.stat().st_size > 500_000:
            text = crash_log.read_text(encoding="utf-8", errors="replace")
            crash_log.write_text(text[-250_000:], encoding="utf-8")
    except OSError:
        logger.debug("Could not rotate SuiteView crash log", exc_info=True)

    if not any(getattr(h, "_suiteview_startup_log", False) for h in logging.root.handlers):
        handler = logging.FileHandler(crash_log, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
        )
        handler._suiteview_startup_log = True
        logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)

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
    return crash_log


def _redirect_pythonw_stdio(crash_log: Path) -> None:
    if not sys.executable.lower().endswith("pythonw.exe"):
        return
    stream = crash_log.open("a", encoding="utf-8")
    _REDIRECT_HANDLES.append(stream)
    sys.stderr = stream
    sys.stdout = stream


def _set_app_user_model_id(app_user_model_id: str | None) -> None:
    if not app_user_model_id:
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_user_model_id)
    except (AttributeError, OSError):
        logger.debug("Could not set AppUserModelID", exc_info=True)


def _clear_win32com_cache() -> None:
    try:
        import win32com

        cache_root = getattr(win32com, "__gen_path__", None)
        if cache_root:
            cache_path = Path(cache_root) / "win32com" / "gen_py"
            if cache_path.exists():
                shutil.rmtree(cache_path, ignore_errors=True)
    except (ImportError, OSError):
        logger.debug("Could not clear win32com gen_py cache", exc_info=True)


def _install_qt_message_handler() -> None:
    def qt_message_handler(mode, context, message):
        qt_logger = logging.getLogger("Qt")
        if mode == QtMsgType.QtCriticalMsg:
            qt_logger.critical(message)
        elif mode == QtMsgType.QtFatalMsg:
            qt_logger.critical("FATAL: %s", message)

    qInstallMessageHandler(qt_message_handler)


def run_suiteview(options: StartupOptions | None = None) -> int:
    """Start SuiteView and return the Qt event-loop exit code."""

    options = options or StartupOptions()
    if options.local_data:
        os.environ["SUITEVIEW_LOCAL_DATA"] = "1"
    if not acquire_or_activate(options.mutex_name or "", (options.title or "SuiteView",)):
        logger.info("Another instance already running — exiting")
        return 0

    try:
        initialize_profile()
    except Exception as exc:
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Profile needs attention", str(exc))
        raise

    crash_log = _setup_crash_log(options)
    if options.redirect_pythonw_stdio:
        _redirect_pythonw_stdio(crash_log)
    logger.info("Single-instance check passed")

    _clear_win32com_cache()
    _install_qt_message_handler()
    _set_app_user_model_id(options.app_user_model_id)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    logger.info("QApplication created")

    try:
        from suiteview.taskbar_launcher.app_launchers import register_default_launchers
        from suiteview.taskbar_launcher.taskbar_window import SuiteViewTaskbar

        register_default_launchers()
        logger.info("Creating SuiteViewTaskbar...")
        suiteview = SuiteViewTaskbar()
        logger.info("SuiteViewTaskbar created successfully")
        app.setWindowIcon(suiteview._build_suiteview_icon(64))
        suiteview.setWindowTitle(options.title or "SuiteView")
        suiteview.show()
        suiteview.raise_()
        suiteview.activateWindow()
        logger.info("SuiteView launcher displayed")
    except Exception as exc:
        logger.error("Failed to create SuiteView window: %s", exc, exc_info=True)
        QMessageBox.critical(None, "Cannot Start SuiteView", str(exc))
        return 1

    exit_code = app.exec()
    logger.info("Application exiting with code: %s", exit_code)
    return exit_code
