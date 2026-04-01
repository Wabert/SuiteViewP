"""
SuiteView Messaging Service — file-drop messaging over a shared network folder.

Each user gets a subfolder under the shared root.  Sending a message writes
a small JSON file into the recipient's folder.  A QTimer polls the local
user's folder for new messages.

Shared folder structure:
    \\\\server\\share\\suiteview_msgs\\
        <username>/
            msg_<timestamp>_<from>.json   ← incoming messages
            .profile.json                 ← display name / status
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger(__name__)

# Network path for the shared message drop
SHARED_MSG_ROOT = Path(r"\\sranico7\Actuarial\UDA\BusSys2\suiteview_msgs")

# Poll interval in milliseconds (5 seconds)
_POLL_INTERVAL_MS = 5_000


def _username() -> str:
    """Return the current Windows login name (lowercase)."""
    return os.environ.get("USERNAME", os.getlogin()).lower()


def _portable_path(file_path: str) -> str:
    """Replace the sender's user-profile prefix with ``~`` so the path is
    portable across machines.  E.g.
    ``C:\\Users\\ab7y02\\OneDrive ...`` → ``~\\OneDrive ...``
    UNC / non-profile paths are returned unchanged.
    """
    home = str(Path.home())                # e.g. C:\Users\ab7y02
    if file_path.startswith(home + "\\") or file_path.startswith(home + "/"):
        return "~" + file_path[len(home):]
    # Also handle case-insensitive match on Windows
    if file_path.lower().startswith(home.lower() + "\\"):
        return "~" + file_path[len(home):]
    return file_path


def _resolve_path(stored_path: str) -> str:
    """Expand a ``~``-prefixed portable path back to the local user profile.
    Non-portable paths are returned unchanged.
    """
    if stored_path.startswith("~\\" ) or stored_path.startswith("~/"):
        return str(Path.home()) + stored_path[1:]
    return stored_path


class Message:
    """A single incoming/outgoing message."""

    __slots__ = ("sender", "sender_display", "timestamp", "msg_type",
                 "path", "note", "filename")

    def __init__(self, sender: str, sender_display: str, timestamp: str,
                 msg_type: str, path: str, note: str, filename: str = ""):
        self.sender = sender
        self.sender_display = sender_display
        self.timestamp = timestamp
        self.msg_type = msg_type
        self.path = path
        self.note = note
        self.filename = filename

    def to_dict(self) -> dict:
        return {
            "from": self.sender,
            "from_display": self.sender_display,
            "timestamp": self.timestamp,
            "type": self.msg_type,
            "path": self.path,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict, filename: str = "") -> "Message":
        return cls(
            sender=d.get("from", ""),
            sender_display=d.get("from_display", ""),
            timestamp=d.get("timestamp", ""),
            msg_type=d.get("type", "file_link"),
            path=_resolve_path(d.get("path", "")),
            note=d.get("note", ""),
            filename=filename,
        )


class MessageService(QObject):
    """Handles sending and receiving messages via shared network folder.

    Signals
    -------
    new_messages(list[Message])
        Emitted when the poller finds unread messages.
    users_changed(list[tuple[str, str]])
        Emitted when the available-user list changes.  Each tuple is
        (username, display_name).
    """

    new_messages = pyqtSignal(list)
    users_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user = _username()
        self._display_name = self._user  # updated from profile
        self._inbox: Path = SHARED_MSG_ROOT / self._user
        self._known_files: set[str] = set()
        self._known_users: list[tuple[str, str]] = []
        self._available = False

        # ── Ensure our own inbox folder + profile exist ──────────
        try:
            self._inbox.mkdir(parents=True, exist_ok=True)
            self._write_profile()
            self._available = True
            # Seed known files so the poller doesn't re-emit them as new
            self._known_files = {
                f.name for f in self._inbox.iterdir()
                if f.suffix == ".json" and f.name.startswith("msg_")
            }
        except OSError:
            logger.warning("Messaging: shared folder unavailable (%s)",
                           SHARED_MSG_ROOT)

        # ── Polling timer ────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        if self._available:
            self._timer.start(_POLL_INTERVAL_MS)

    # ── Public API ───────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """True when the shared network folder is reachable."""
        return self._available

    @property
    def username(self) -> str:
        return self._user

    @property
    def display_name(self) -> str:
        return self._display_name

    def set_display_name(self, name: str):
        self._display_name = name
        if self._available:
            self._write_profile()

    def get_online_users(self) -> list[tuple[str, str]]:
        """Return [(username, display_name), ...] excluding self."""
        users: list[tuple[str, str]] = []
        if not self._available:
            return users
        try:
            for entry in SHARED_MSG_ROOT.iterdir():
                if not entry.is_dir():
                    continue
                uname = entry.name.lower()
                profile = entry / ".profile.json"
                display = uname
                if profile.exists():
                    try:
                        data = json.loads(profile.read_text(encoding="utf-8"))
                        display = data.get("display_name", uname)
                    except (json.JSONDecodeError, OSError):
                        pass
                users.append((uname, display))
        except OSError:
            logger.debug("Messaging: cannot list shared folder")
        users.sort(key=lambda u: u[1].lower())
        return users

    def send_file_link(self, recipient: str, file_path: str,
                       note: str = "") -> bool:
        """Send a file-link message to *recipient*."""
        if not self._available:
            return False
        dest = SHARED_MSG_ROOT / recipient.lower()
        if not dest.is_dir():
            return False
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"msg_{ts}_{self._user}.json"
        msg = Message(
            sender=self._user,
            sender_display=self._display_name,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            msg_type="file_link",
            path=_portable_path(file_path),
            note=note,
        )
        try:
            (dest / fname).write_text(
                json.dumps(msg.to_dict(), indent=2),
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            logger.error("Messaging: failed to send to %s: %s",
                         recipient, exc)
            return False

    def acknowledge(self, msg: Message):
        """Delete (acknowledge) a received message file."""
        if not msg.filename:
            return
        try:
            (self._inbox / msg.filename).unlink(missing_ok=True)
        except OSError:
            pass

    def stop(self):
        """Stop the polling timer."""
        self._timer.stop()

    def load_existing(self) -> list[Message]:
        """Return all message files currently in the inbox (for session restore)."""
        msgs: list[Message] = []
        if not self._available:
            return msgs
        for fname in sorted(self._known_files):
            try:
                data = json.loads(
                    (self._inbox / fname).read_text(encoding="utf-8"))
                msgs.append(Message.from_dict(data, filename=fname))
            except (json.JSONDecodeError, OSError):
                pass
        return msgs

    # ── Private ──────────────────────────────────────────────────

    def _write_profile(self):
        profile = self._inbox / ".profile.json"
        data = {
            "display_name": self._display_name,
            "last_seen": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            profile.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _poll(self):
        """Check inbox for new message files."""
        if not self._available:
            return
        # Refresh profile heartbeat every poll
        self._write_profile()

        new_msgs: list[Message] = []
        try:
            current_files = {
                f.name for f in self._inbox.iterdir()
                if f.suffix == ".json" and f.name.startswith("msg_")
            }
        except OSError:
            return

        arrivals = current_files - self._known_files
        for fname in sorted(arrivals):
            try:
                data = json.loads(
                    (self._inbox / fname).read_text(encoding="utf-8"))
                new_msgs.append(Message.from_dict(data, filename=fname))
            except (json.JSONDecodeError, OSError):
                pass
        self._known_files = current_files

        if new_msgs:
            self.new_messages.emit(new_msgs)

        # Check for user-list changes
        users = self.get_online_users()
        if users != self._known_users:
            self._known_users = users
            self.users_changed.emit(users)
