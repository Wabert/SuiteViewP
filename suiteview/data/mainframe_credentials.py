"""The one saved mainframe sign-on shared by every SuiteView tool.

The user ID and password live, encrypted with the profile key, in the
``MAINFRAME_USER`` row of the profile ``connections`` table. The Switch
terminals, Mainframe Terminal and Mainframe Nav (FTP) all read it from here,
and the Passwords dialog is the one place that writes it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from suiteview.core.credential_manager import get_credential_manager
from suiteview.data.repositories import get_connection_repository

MAINFRAME_USER_CONNECTION = "MAINFRAME_USER"


@dataclass(frozen=True)
class MainframeCredentials:
    """Saved mainframe user ID and password; the password never appears in repr."""

    userid: str = ""
    password: str = field(default="", repr=False)

    @property
    def complete(self) -> bool:
        return bool(self.userid and self.password)


def _find_row() -> dict | None:
    for row in get_connection_repository().get_all_connections():
        if row.get("connection_name") == MAINFRAME_USER_CONNECTION:
            return row
    return None


def load_mainframe_credentials() -> MainframeCredentials:
    """Return the saved sign-on, or empty credentials when none is saved.

    A saved value that cannot be decrypted raises: it means the profile key
    does not match, and silently treating that as "no password" would send a
    blank password to the mainframe.
    """
    row = _find_row()
    if row is None:
        return MainframeCredentials()
    cipher = get_credential_manager()
    userid = cipher.decrypt(row.get("encrypted_username")) or ""
    password = cipher.decrypt(row.get("encrypted_password")) or ""
    return MainframeCredentials(userid=userid, password=password)


def save_mainframe_credentials(userid: str, password: str) -> None:
    """Encrypt and save the shared sign-on; both values are required."""
    userid = (userid or "").strip()
    if not userid or not password:
        raise ValueError("Both a mainframe user ID and a password are required.")
    cipher = get_credential_manager()
    encrypted_userid = cipher.encrypt(userid)
    encrypted_password = cipher.encrypt(password)
    repo = get_connection_repository()
    row = _find_row()
    if row is not None:
        repo.update_connection(
            row["connection_id"],
            encrypted_username=encrypted_userid,
            encrypted_password=encrypted_password,
        )
        return
    repo.create_connection(
        connection_name=MAINFRAME_USER_CONNECTION,
        connection_type="Generic",
        server_name="",
        database_name="",
        auth_type="SQL_AUTH",
        encrypted_username=encrypted_userid,
        encrypted_password=encrypted_password,
    )
