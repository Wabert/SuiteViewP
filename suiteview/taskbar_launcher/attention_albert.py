"""Task-bar entry for Attention Albert action items (AAI).

The button shows how many AAIs need Robert, runs the maintained AAI service
(``Email Manager\\attention-albert\\aai.py tick``) on a timer, raises tray
alerts, and opens the AAI list. Right-click to turn inbox watching on/off,
change the scan interval, or scan now. No mail logic lives in SuiteView.

Only the AAI owner (``access_control.AAI_BUTTON_OWNER``) gets the button in the
packaged app; source runs show it to whoever runs them. The ATTENTIONALBERT
app grant is separate: it only decides whose emails Albert will process.

The feature starts closed whenever SuiteView opens. Tools > Attention Albert
opens it (button shown, inbox polling on); "Close Attention Albert" on the
button's menu, the Tools switch, or the list window's Close button closes it.
"""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess, QRectF, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QPainter, QPen
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QPushButton

from suiteview.core.access_control import AccessDeniedError, AccessUnavailableError, guard_aai_button
from suiteview.core.build_env import app_unavailable_reason
from suiteview.taskbar_launcher.albert_launcher import (
    ALBERT_BUTTON_DISABLED, ALBERT_BUTTON_GRADIENT, ALBERT_BUTTON_HOVER,
)
from suiteview.ui import tokens

logger = logging.getLogger(__name__)
_AAI_RELATIVE = Path("Email Manager") / "attention-albert"
TICK_MS = 60_000
INTERVALS = (1, 2, 5, 10, 15, 30, 60)
_USER = os.environ.get("USERNAME", "user")
# Must match Email Manager\attention-albert\aai_window.py.
WINDOW_SERVER = "SuiteView-AttentionAlbert-" + _USER
CONTROL_SERVER = "SuiteView-AAI-Control-" + _USER


def _find_home(start: Path) -> Path:
    """Locate the AAI service beside a SuiteView checkout or worktree."""
    for folder in start.parents:
        candidate = folder / _AAI_RELATIVE
        if (candidate / "aai.py").is_file():
            return candidate
    return start.parents[3] / _AAI_RELATIVE


AAI_HOME = _find_home(Path(__file__).resolve())


def _live() -> bool:
    """False for offscreen (test/headless) Qt: never touch the mailbox or real windows there."""
    return QApplication.platformName() != "offscreen"


class AttentionAlbertButton(QPushButton):
    def __init__(self, parent=None, *, start_timer=True):
        super().__init__("AAI", parent)
        self.setObjectName("attentionAlbertButton")
        self.setAccessibleName("Attention Albert action items")
        self.setFixedSize(36, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.summary: dict = {}
        self.error: str | None = None
        self.last_alert_id: str | None = None
        self._tick_process: QProcess | None = None
        self._action_process: QProcess | None = None
        self._tray_connected = False
        self.unavailable = app_unavailable_reason("ALBERT") or (
            None if (AAI_HOME / "aai.py").is_file()
            else f"Attention Albert was not found:\n{AAI_HOME}")
        self.setEnabled(False)  # enabled by set_allowed() for the AAI owner
        self.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ALBERT_BUTTON_GRADIENT[0]}, stop:1 {ALBERT_BUTTON_GRADIENT[1]});
                border: 2px solid {tokens.GOLD_BORDER};
                border-radius: 4px;
                color: {tokens.ILLUSTRATION_STYLE.menu_hover_text};
                font-family: 'Segoe UI'; font-size: 11px; font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ALBERT_BUTTON_HOVER[0]}, stop:1 {ALBERT_BUTTON_HOVER[1]});
            }}
            QPushButton[watching="false"] {{ color: #9FB8B4; }}
            QPushButton:disabled {{
                background: {ALBERT_BUTTON_DISABLED[0]};
                color: {ALBERT_BUTTON_DISABLED[1]};
                border-color: {ALBERT_BUTTON_DISABLED[2]};
            }}
        """)
        self.setProperty("watching", "false")
        self.clicked.connect(self._open)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self.tick)
        self._start_timer = start_timer
        self.allowed = False
        # Robert's 9/29/2026 request: the feature starts closed each time SuiteView opens and
        # is opened from Tools > Attention Albert. Closed = no polling and no task-bar button.
        self.feature_open = False
        self.tools_action = None
        self._control_server = None
        self.hide()  # shown once permissions confirm the AAI owner and the feature is opened
        self._update_tooltip()

    # ------------------------------------------------------------------ open/closed state
    def bind_tools_action(self, action):
        """Tools > Attention Albert: a checkable on/off switch, visible only to the owner."""
        self.tools_action = action
        action.setCheckable(True)
        action.setToolTip("Open or close Attention Albert (inbox watching and the AAI button)")
        action.toggled.connect(self.set_open)
        self._sync_tools_action()

    def _sync_tools_action(self):
        if self.tools_action is None:
            return
        shown = self.allowed and not app_unavailable_reason("ALBERT")
        self.tools_action.setVisible(shown)
        self.tools_action.setEnabled(shown and not self.unavailable)
        self.tools_action.blockSignals(True)
        self.tools_action.setChecked(self.feature_open)
        self.tools_action.blockSignals(False)

    def set_allowed(self, allowed: bool):
        """Offer Attention Albert only to the AAI owner (or a source run).

        The inbox timer never starts until permissions allow it and the owner opens
        the feature, so another user's SuiteView never runs the AAI service.
        """
        self.allowed = bool(allowed)
        if not self.allowed:
            self.feature_open = False
        self._listen(self.allowed and not self.unavailable)
        self._refresh()

    def set_open(self, open_: bool):
        open_ = bool(open_) and self.allowed and not self.unavailable
        if open_ == self.feature_open:
            self._sync_tools_action()
            return
        self.feature_open = open_
        self._refresh()
        if open_:
            QTimer.singleShot(1000, self.tick)
        else:
            self._close_list_window()

    def close_feature(self):
        self.set_open(False)

    def _refresh(self):
        # Like the Al button, Albert tools don't ship in the packaged EXE: never show a dead button there.
        shown = self.allowed and self.feature_open and not app_unavailable_reason("ALBERT")
        self.setVisible(shown)
        self.setEnabled(shown and not self.unavailable)
        if not self.isEnabled():
            self.timer.stop()
        elif (self._start_timer and not self.timer.isActive() and _live()):
            # Offscreen (test/headless) SuiteView instances never touch the mailbox.
            self.timer.start()
        self._sync_tools_action()

    # ------------------------------------------------------------------ AAI window link
    def _listen(self, enabled: bool):
        """Lets the AAI list window's Close button close the feature in this SuiteView."""
        if not enabled or not _live():
            if self._control_server is not None:
                self._control_server.close()
                self._control_server = None
            return
        if self._control_server is not None:
            return
        server = QLocalServer(self)
        QLocalServer.removeServer(CONTROL_SERVER)
        if not server.listen(CONTROL_SERVER):
            logger.warning("Attention Albert control channel unavailable: %s", server.errorString())
            return
        server.newConnection.connect(self._control_message)
        self._control_server = server

    def _control_message(self):
        connection = self._control_server.nextPendingConnection()
        if connection is None:
            return

        def read():
            if bytes(connection.readAll()).decode(errors="replace").strip() == "close":
                self.close_feature()

        connection.readyRead.connect(read)
        connection.disconnected.connect(connection.deleteLater)
        if connection.bytesAvailable():
            read()

    @staticmethod
    def _close_list_window():
        if not _live():
            return
        socket = QLocalSocket()
        socket.connectToServer(WINDOW_SERVER)
        if socket.waitForConnected(300):
            socket.write(b"__close__")
            socket.waitForBytesWritten(300)
            socket.disconnectFromServer()

    # ------------------------------------------------------------------ processes
    def _process(self, arguments, finished):
        process = QProcess(self)
        process.setWorkingDirectory(str(AAI_HOME))
        process.finished.connect(lambda *_: finished(process))
        process.start(sys.executable, ["-B", str(AAI_HOME / "aai.py"), *arguments])
        return process

    @staticmethod
    def _result(process) -> dict:
        output = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            error = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
            return {"ok": False, "error": (error or output or "no response").strip()[-500:]}

    def tick(self, scan_now=False):
        if (self.unavailable or not self.allowed or not self.isEnabled()
                or self._tick_process is not None):
            return
        self._tick_process = self._process(["tick", "--scan-now"] if scan_now else ["tick"],
                                           self._tick_finished)

    def _tick_finished(self, process):
        result = self._result(process)
        process.deleteLater()
        self._tick_process = None
        self.apply_result(result)

    def apply_result(self, result: dict):
        if result.get("summary"):
            self.summary = result["summary"]
        self.error = None if result.get("ok") else result.get("error")
        if self.error and result.get("type") != "Busy":
            logger.warning("Attention Albert tick: %s", self.error)
        for alert in result.get("alerts", []):
            self._notify(alert)
        self.setProperty("watching", "true" if self.summary.get("enabled") else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self._update_tooltip()
        self.update()

    def _run_action(self, arguments):
        if self._action_process is not None:
            return
        def done(process):
            result = self._result(process)
            process.deleteLater()
            self._action_process = None
            if not result.get("ok"):
                QMessageBox.warning(self, "Attention Albert", result.get("error") or "The change failed.")
            self.tick()
        self._action_process = self._process(arguments, done)

    # ------------------------------------------------------------------ UI
    def _tray(self):
        state = getattr(self.window(), "state", None)
        return getattr(state, "tray_icon", None)

    def _notify(self, alert: dict):
        tray = self._tray()
        self.last_alert_id = alert.get("aai_id") or self.last_alert_id
        if tray is None:
            return
        if not self._tray_connected:
            tray.messageClicked.connect(lambda: self.open_list(self.last_alert_id))
            self._tray_connected = True
        from PyQt6.QtWidgets import QSystemTrayIcon
        icon = (QSystemTrayIcon.MessageIcon.Warning
                if alert.get("kind") in {"unauthorized", "send_uncertain", "send_failed", "handoff_failed",
                                         "time_box"}
                else QSystemTrayIcon.MessageIcon.Information)
        tray.showMessage(f"Attention Albert {alert.get('aai_id') or ''}".strip(), alert.get("text", ""), icon, 10000)

    def _update_tooltip(self):
        if self.unavailable:
            self.setToolTip(self.unavailable)
            return
        summary = self.summary
        lines = ["Attention Albert action items - click to open, right-click for options"]
        if summary:
            lines.append(f"Watching inbox: {'on' if summary.get('enabled') else 'off'}"
                         f" (every {summary.get('interval_minutes')} min"
                         f"{', work hours' if summary.get('work_hours_only') else ''})")
            lines.append(f"{summary.get('needs_attention', 0)} need you, {summary.get('working', 0)} in progress")
            if summary.get("last_scan_result"):
                lines.append(f"Last scan: {summary['last_scan_result']}")
        if self.error:
            lines.append(f"Problem: {self.error}")
        self.setToolTip("\n".join(lines))

    def paintEvent(self, event):
        super().paintEvent(event)
        count = int(self.summary.get("needs_attention") or 0)
        if not count or not self.isEnabled():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = "9+" if count > 9 else str(count)
        diameter = 13
        rect = QRectF(self.width() - diameter - 1, 1, diameter, diameter)
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        painter.setBrush(QColor("#C62828" if self.summary.get("red") else "#E08A00"))
        painter.drawEllipse(rect)
        font = QFont("Segoe UI", 7)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()

    def show_menu(self, position):
        if self.unavailable or not self.allowed:
            return
        menu = QMenu(self)
        menu.addAction("Open action items", self.open_list)
        menu.addSeparator()
        watch = QAction("Watch inbox for \"Attention Albert\"", menu, checkable=True)
        watch.setChecked(bool(self.summary.get("enabled")))
        watch.toggled.connect(lambda on: self._run_action(["settings", "--enabled", "on" if on else "off"]))
        menu.addAction(watch)
        intervals = menu.addMenu("Scan every")
        for minutes in INTERVALS:
            action = QAction(f"{minutes} min", intervals, checkable=True)
            action.setChecked(self.summary.get("interval_minutes") == minutes)
            action.triggered.connect(lambda _=False, m=minutes: self._run_action(["settings", "--interval", str(m)]))
            intervals.addAction(action)
        hours = QAction("Work hours only", menu, checkable=True)
        hours.setChecked(bool(self.summary.get("work_hours_only", True)))
        hours.toggled.connect(lambda on: self._run_action(["settings", "--work-hours", "on" if on else "off"]))
        menu.addAction(hours)
        menu.addSeparator()
        scan = menu.addAction("Scan now", lambda: self.tick(scan_now=True))
        scan.setEnabled(self._tick_process is None)
        menu.addSeparator()
        close = menu.addAction("Close Attention Albert", self.close_feature)
        close.setToolTip("Stop watching the inbox and hide this button; reopen from Tools > Attention Albert")
        self._menu = menu
        menu.popup(self.mapToGlobal(position))

    def _open(self, checked=False):
        try:
            guard_aai_button()
        except (AccessDeniedError, AccessUnavailableError) as error:
            logger.warning("Blocked Attention Albert button: %s", error)
            QMessageBox.warning(self, "SuiteView Access", str(error))
            return
        self.open_list()

    def open_list(self, select=None):
        if self.unavailable:
            return
        arguments = [sys.executable, "-B", str(AAI_HOME / "aai_window.py")]
        if select:
            arguments += ["--select", select]
        try:
            subprocess.Popen(arguments, cwd=str(AAI_HOME),
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            logger.error("Failed to open Attention Albert: %s", exc, exc_info=True)
            QMessageBox.critical(self, "Attention Albert", f"Could not open the action-item list:\n\n{exc}")
