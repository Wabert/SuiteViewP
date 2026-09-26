"""Mainframe tools window."""

import logging

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.core.connection_manager import ConnectionManager
from suiteview.core.credential_manager import CredentialManager
from suiteview.mainframe_nav.mainframe_nav_screen import MainframeNavScreen
from suiteview.mainframe_nav.mainframe_terminal_screen import DualTerminalScreen
from suiteview.mainframe_nav.styles import (
    MAINFRAME_BORDER_COLOR,
    MAINFRAME_HEADER_COLORS,
    c,
)
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

logger = logging.getLogger(__name__)


class MainframeWindow(FramelessWindowBase):
    """Dedicated frameless window for Mainframe tools."""

    def __init__(self):
        from suiteview.core.access_control import guard_app_access

        guard_app_access("MAINFRAMENAV")
        self.conn_manager = ConnectionManager()
        self.cred_manager = CredentialManager()
        self.mainframe_nav_screen = None
        self.mainframe_terminal_screen = None
        self.user_button = None
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
        self.mainframe_terminal_screen.terminal_left.parent_screen = self
        self.mainframe_terminal_screen.terminal_right.parent_screen = self

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
        self.user_button = QPushButton("👤 User")
        self.user_button.setStyleSheet(
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
        self.user_button.clicked.connect(self.show_user_credentials_dialog)
        self.user_button.setFixedHeight(20)
        footer_layout.addWidget(self.user_button)
        footer_layout.addStretch()
        hint = QLabel("Mainframe tools")
        hint.setStyleSheet(f"color: {c('muted')}; font-size: 11px; padding-right: 8px;")
        footer_layout.addWidget(hint)
        return footer

    def show_user_credentials_dialog(self):
        """Show dialog to set user credentials."""
        dialog = QDialog(self)
        dialog.setWindowTitle("User Credentials")
        dialog.setModal(True)
        dialog.resize(400, 200)

        layout = QFormLayout(dialog)
        info_label = QLabel("Enter your mainframe credentials.\nThese will be used for both Terminal and Navigation.")
        info_label.setStyleSheet(
            f"color: {c('secondary_text')}; font-style: italic; margin-bottom: 10px;"
        )
        layout.addRow(info_label)

        existing_conn = self._find_user_connection()
        username_input = QLineEdit()
        username_input.setPlaceholderText("Enter username (e.g., ab7y02)")
        if existing_conn:
            encrypted_user = existing_conn.get("encrypted_username")
            if encrypted_user:
                try:
                    username_input.setText(self.cred_manager.decrypt(encrypted_user))
                except Exception:
                    logger.debug("Could not decrypt saved mainframe username", exc_info=True)
        layout.addRow("Username:", username_input)

        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_input.setPlaceholderText("Enter password")
        if existing_conn:
            encrypted_pw = existing_conn.get("encrypted_password")
            if encrypted_pw:
                try:
                    password_input.setText(self.cred_manager.decrypt(encrypted_pw))
                except Exception:
                    logger.debug("Could not decrypt saved mainframe password", exc_info=True)
        layout.addRow("Password:", password_input)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(
            lambda: self.save_user_credentials(dialog, username_input.text(), password_input.text())
        )
        button_box.rejected.connect(dialog.reject)
        layout.addRow(button_box)
        dialog.exec()

    def _find_user_connection(self):
        for conn in self.conn_manager.get_connections():
            if conn.get("connection_name") == "MAINFRAME_USER":
                return conn
        return None

    def save_user_credentials(self, dialog, username, password):
        """Save user credentials."""
        if not username or not password:
            QMessageBox.warning(dialog, "Missing Information", "Please enter both username and password.")
            return

        try:
            existing_conn = self._find_user_connection()
            conn_id = existing_conn.get("connection_id") if existing_conn else None
            encrypted_password = self.cred_manager.encrypt(password)
            encrypted_username = self.cred_manager.encrypt(username)

            if existing_conn:
                self.conn_manager.repo.update_connection(
                    conn_id,
                    encrypted_username=encrypted_username,
                    encrypted_password=encrypted_password,
                )
                logger.info(f"Updated MAINFRAME_USER credentials for: {username}")
            else:
                self.conn_manager.repo.create_connection(
                    connection_name="MAINFRAME_USER",
                    connection_type="Generic",
                    server_name="",
                    database_name="",
                    auth_type="SQL_AUTH",
                    encrypted_username=encrypted_username,
                    encrypted_password=encrypted_password,
                )
                logger.info(f"Created MAINFRAME_USER credentials for: {username}")

            QMessageBox.information(
                dialog,
                "Credentials Saved",
                "Your credentials have been saved successfully.\n\n"
                "They will be used for mainframe connections in both Terminal and Navigation.",
            )
            dialog.accept()
            logger.info(f"User credentials saved for: {username}")
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            QMessageBox.critical(dialog, "Save Error", f"Failed to save credentials:\n{str(e)}")

    def closeEvent(self, event):
        """Disconnect terminal sessions before closing."""
        if self.mainframe_terminal_screen is not None:
            if hasattr(self.mainframe_terminal_screen, "disconnect_all"):
                self.mainframe_terminal_screen.disconnect_all()
            elif hasattr(self.mainframe_terminal_screen, "disconnect_from_mainframe"):
                self.mainframe_terminal_screen.disconnect_from_mainframe()
        super().closeEvent(event)
