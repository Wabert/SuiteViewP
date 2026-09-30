"""Mainframe tools window."""

import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.core.connection_manager import ConnectionManager
from suiteview.mainframe_nav.mainframe_nav_screen import MainframeNavScreen
from suiteview.mainframe_nav.mainframe_terminal_screen import DualTerminalScreen
from suiteview.mainframe_nav.styles import (
    MAINFRAME_BORDER_COLOR,
    MAINFRAME_HEADER_COLORS,
    c,
)
from suiteview.ui.dialogs.passwords_dialog import can_manage_passwords, open_passwords_dialog
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

logger = logging.getLogger(__name__)


class MainframeWindow(FramelessWindowBase):
    """Dedicated frameless window for Mainframe tools."""

    def __init__(self):
        from suiteview.core.access_control import guard_app_access

        guard_app_access("MAINFRAMENAV")
        self.conn_manager = ConnectionManager()
        self.mainframe_nav_screen = None
        self.mainframe_terminal_screen = None
        self.passwords_button = None
        super().__init__(
            title="SuiteView - Mainframe Tools",
            default_size=(1400, 800),
            min_size=(600, 400),
            header_colors=MAINFRAME_HEADER_COLORS,
            border_color=MAINFRAME_BORDER_COLOR,
        )
        logger.info("Mainframe window initialized")

    def build_content(self) -> QWidget:
        """Build the mainframe terminal/nav tab set."""
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.tab_widget.setDocumentMode(True)

        self.mainframe_nav_screen = MainframeNavScreen(self.conn_manager)
        self.mainframe_terminal_screen = DualTerminalScreen()

        self.tab_widget.addTab(self.mainframe_terminal_screen, "Mainframe Terminal")
        self.tab_widget.addTab(self.mainframe_nav_screen, "Mainframe Nav")
        layout.addWidget(self.tab_widget, 1)
        layout.addWidget(self._build_footer())
        return central_widget

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setMaximumHeight(24)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(4, 1, 80, 1)
        footer_layout.setSpacing(0)
        self.passwords_button = QPushButton("🔑 Passwords")
        self.passwords_button.setToolTip(
            "Enter your mainframe user ID and password once for every SuiteView tool")
        self.passwords_button.setStyleSheet(
            f"QPushButton {{"
            "background-color: transparent;"
            f"color: {c('note_text')};"
            "padding: 2px 8px;"
            f"border: 1px solid {c('dialog_border')};"
            "border-radius: 3px;"
            "font-size: 9pt;"
            "}"
            "QPushButton:hover {"
            f"background-color: {c('dialog_hover_bg')};"
            f"color: {c('dialog_hover_text')};"
            f"border: 1px solid {c('dialog_hover_border')};"
            "}"
        )
        self.passwords_button.clicked.connect(self.show_passwords_dialog)
        self.passwords_button.setFixedHeight(20)
        footer_layout.addWidget(self.passwords_button)
        # Password Manager is a role-granted app (PASSWORDMANAGER).
        self.passwords_button.setVisible(can_manage_passwords())
        footer_layout.addStretch()
        hint = QLabel("Mainframe tools")
        hint.setStyleSheet(f"color: {c('muted')}; font-size: 11px; padding-right: 8px;")
        footer_layout.addWidget(hint)
        return footer

    def show_passwords_dialog(self):
        """Edit the shared mainframe sign-on."""
        open_passwords_dialog(self)

    def open_policy_in_switch(self, side: str, policy_number: str,
                              company_code: str, region: str) -> None:
        """Show the terminal tab and bring *policy_number* up on Switch *side*.

        The sign-on/navigation runs on the next event-loop turn so this window
        paints before the (event-loop-pumping) terminal sequence starts.
        """
        terminal = self.mainframe_terminal_screen.terminal_for(side)
        self.tab_widget.setCurrentWidget(self.mainframe_terminal_screen)
        QTimer.singleShot(
            0, lambda: terminal.open_policy(policy_number, company_code, region))

    def closeEvent(self, event):
        """Disconnect terminal sessions before closing."""
        if self.mainframe_terminal_screen is not None:
            if hasattr(self.mainframe_terminal_screen, "disconnect_all"):
                self.mainframe_terminal_screen.disconnect_all()
            elif hasattr(self.mainframe_terminal_screen, "disconnect_from_mainframe"):
                self.mainframe_terminal_screen.disconnect_from_mainframe()
        super().closeEvent(event)
