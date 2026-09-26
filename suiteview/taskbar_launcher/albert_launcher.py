"""Launch the maintained Albert composer without importing Outlook or its UI."""
import logging
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox, QPushButton

from suiteview.core.access_control import guard_app_access
from suiteview.ui.access_control import requires_app_access
from suiteview.core.build_env import app_unavailable_reason
from suiteview.ui import tokens

logger = logging.getLogger(__name__)
BRIDGE = (Path(__file__).resolve().parents[3] / "Email Manager"
          / "outlook-albert" / "bridge.py")
ALBERT_BUTTON_GRADIENT = ("#247C75", "#103F3C")
ALBERT_BUTTON_HOVER = ("#2F9188", "#185B57")
ALBERT_BUTTON_DISABLED = ("#DFE3E8", "#737B85", "#AAB0B7")


def launch_albert():
    guard_app_access("ALBERT")
    if not BRIDGE.is_file():
        raise FileNotFoundError(f"Albert's assignment launcher was not found:\n{BRIDGE}")
    return subprocess.Popen(
        [sys.executable, "-B", str(BRIDGE), "--new-task"],
        cwd=str(BRIDGE.parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class AlbertButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__("Al", parent)
        self.setObjectName("albertTaskButton")
        self.setAccessibleName("Send a task to Albert")
        self.setFixedSize(28, 28)
        unavailable = app_unavailable_reason("ALBERT")
        self.setToolTip(unavailable or "Send a task to Albert - no email required")
        self.setEnabled(not unavailable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Keep the Outlook badge colors in SuiteView's flatter rounded button shape.
        self.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ALBERT_BUTTON_GRADIENT[0]}, stop:1 {ALBERT_BUTTON_GRADIENT[1]});
                border: 2px solid {tokens.GOLD_BORDER};
                border-radius: 4px;
                color: {tokens.ILLUSTRATION_STYLE.menu_hover_text};
                font-family: 'Segoe UI'; font-size: 14px; font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                border-color: {tokens.ILLUSTRATION_STYLE.menu_hover_text};
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ALBERT_BUTTON_HOVER[0]}, stop:1 {ALBERT_BUTTON_HOVER[1]});
            }}
            QPushButton:pressed {{
                background: {ALBERT_BUTTON_GRADIENT[1]};
                border-color: {tokens.GOLD_BORDER};
            }}
            QPushButton:disabled {{
                background: {ALBERT_BUTTON_DISABLED[0]};
                color: {ALBERT_BUTTON_DISABLED[1]};
                border-color: {ALBERT_BUTTON_DISABLED[2]};
            }}
        """)
        self.clicked.connect(self._open)

    @requires_app_access("ALBERT")
    def _open(self, checked=False):
        try:
            launch_albert()
        except OSError as exc:
            logger.error("Failed to open Albert: %s", exc, exc_info=True)
            QMessageBox.critical(self, "Albert needs attention",
                                 f"Could not open Albert's assignment window:\n\n{exc}")
