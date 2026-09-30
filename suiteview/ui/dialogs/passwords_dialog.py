"""SuiteView Passwords: enter the mainframe sign-on once for every tool.

The dialog edits the single shared sign-on in
:mod:`suiteview.data.mainframe_credentials`. Anything that needs the
mainframe user ID/password (Switch A/B, Mainframe Terminal, Mainframe Nav)
reads it from there, so the user never re-types it per app.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
)

from suiteview.core import access_control
from suiteview.core.access_control import AccessDeniedError, AccessUnavailableError
from suiteview.data.mainframe_credentials import (
    MainframeCredentials, load_mainframe_credentials, save_mainframe_credentials,
)
from suiteview.ui import tokens
from suiteview.ui.widgets.frameless_window import FramelessDialog

logger = logging.getLogger(__name__)

PASSWORD_MANAGER_APP = "PASSWORDMANAGER"
USED_BY = ("Switch A / Switch B terminals", "Mainframe Terminal", "Mainframe Nav (FTP)")


def can_manage_passwords() -> bool:
    """UI visibility for Password Manager entry points (snapshot, never raises)."""
    try:
        return access_control.can_access_app(PASSWORD_MANAGER_APP)
    except (AccessDeniedError, AccessUnavailableError):
        return False

_EDIT_STYLE = f"""
    QLineEdit {{
        border: 1px solid {tokens.BORDER_MUTED}; border-radius: {tokens.RADIUS_MD}px;
        padding: 3px 6px; font-size: {tokens.FONT_SIZE_LABEL_PX}px;
        background: {tokens.SURFACE}; color: {tokens.TEXT};
    }}
    QLineEdit:focus {{ border-color: {tokens.GOLD_BORDER}; background: {tokens.INPUT_FOCUS_SURFACE}; }}
"""
_BUTTON_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {tokens.BRAND_BLUE_LIGHT}, stop:1 {tokens.BRAND_BLUE_DARK});
        color: {tokens.SURFACE}; border: 1px solid {tokens.BRAND_BLUE_DEEP};
        border-radius: {tokens.RADIUS_MD}px; font-size: {tokens.FONT_SIZE_BODY_PX}px;
        font-weight: bold; padding: 4px 16px;
    }}
    QPushButton:hover {{ color: {tokens.GOLD_TEXT}; }}
"""


class PasswordsDialog(FramelessDialog):
    """Modal editor for the shared mainframe user ID and password."""

    def __init__(self, parent=None, reason: str = ""):
        super().__init__("🔑 SuiteView Passwords", parent)
        self.setModal(True)
        self.setMinimumWidth(380)

        if reason:
            why = QLabel(reason)
            why.setWordWrap(True)
            why.setStyleSheet(
                f"color: {tokens.STATUS_WARN}; background: {tokens.SURFACE_WARNING};"
                f" border-radius: {tokens.RADIUS_MD}px; padding: 4px 6px;"
                f" font-size: {tokens.FONT_SIZE_BODY_PX}px; font-weight: bold;")
            self.body_layout.addWidget(why)

        intro = QLabel(
            "Your mainframe sign-on. Enter it once here; it is saved encrypted in "
            "your SuiteView profile and used by:\n  • " + "\n  • ".join(USED_BY))
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_SIZE_BODY_PX}px;")
        self.body_layout.addWidget(intro)

        form = QFormLayout()
        form.setHorizontalSpacing(tokens.SPACE_MD)
        form.setVerticalSpacing(tokens.SPACE_SM)
        self.userid_input = QLineEdit()
        self.userid_input.setPlaceholderText("Mainframe user ID")
        self.userid_input.setStyleSheet(_EDIT_STYLE)
        form.addRow("User ID:", self.userid_input)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Mainframe password")
        self.password_input.setStyleSheet(_EDIT_STYLE)
        form.addRow("Password:", self.password_input)
        self.show_password = QCheckBox("Show password")
        self.show_password.toggled.connect(self._toggle_echo)
        form.addRow("", self.show_password)
        self.body_layout.addLayout(form)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            f"color: {tokens.TEXT_MUTED}; font-size: {tokens.FONT_SIZE_BODY_PX}px;"
            " font-style: italic;")
        self.body_layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet(_BUTTON_STYLE)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        self.save_button = QPushButton("Save")
        self.save_button.setStyleSheet(_BUTTON_STYLE)
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        buttons.addWidget(self.save_button)
        self.body_layout.addLayout(buttons)

        self._load()

    def _load(self):
        try:
            saved = load_mainframe_credentials()
        except Exception as exc:  # noqa: BLE001 - shown to the user, then re-entered
            logger.error("Could not read the saved mainframe sign-on: %s", exc)
            saved = MainframeCredentials()
            self._set_status(
                "The saved sign-on could not be decrypted with this profile's key. "
                "Enter it again and Save to replace it.", error=True)
        else:
            self._set_status("Saved." if saved.complete else "Nothing saved yet.")
        self.userid_input.setText(saved.userid)
        self.password_input.setText(saved.password)
        (self.password_input if saved.userid else self.userid_input).setFocus()

    def _toggle_echo(self, visible: bool):
        self.password_input.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)

    def _set_status(self, text: str, error: bool = False):
        self.status_label.setText(text)
        color = tokens.STATUS_ERROR if error else tokens.TEXT_MUTED
        self.status_label.setStyleSheet(
            f"color: {color}; font-size: {tokens.FONT_SIZE_BODY_PX}px; font-style: italic;")

    def save(self) -> bool:
        userid = self.userid_input.text().strip()
        password = self.password_input.text()
        if not userid or not password:
            self._set_status("Enter both a user ID and a password.", error=True)
            return False
        try:
            save_mainframe_credentials(userid, password)
        except Exception as exc:  # noqa: BLE001 - a failed save must be visible
            logger.error("Could not save the mainframe sign-on: %s", exc)
            self._set_status(f"Could not save: {exc}", error=True)
            return False
        logger.info("Saved mainframe sign-on for %s", userid)
        self.accept()
        return True

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.save()
            return
        super().keyPressEvent(event)


def open_passwords_dialog(parent=None, reason: str = "") -> bool:
    """Show the Passwords dialog; True when the user saved a sign-on.

    The Password Manager is a role-granted app (``PASSWORDMANAGER``); a user
    without it is told so and nothing opens.
    """
    try:
        access_control.guard_app_access(PASSWORD_MANAGER_APP)
    except (AccessDeniedError, AccessUnavailableError) as error:
        logger.warning("Blocked %s: %s", PASSWORD_MANAGER_APP, error)
        message = str(error)
        if reason:
            message = f"{reason}\n\n{message}"
        QMessageBox.warning(parent, "Password Manager", message)
        return False
    return PasswordsDialog(parent, reason=reason).exec() == PasswordsDialog.DialogCode.Accepted
