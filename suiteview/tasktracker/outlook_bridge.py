"""
TaskTracker Outlook Bridge — Thin adapter between TaskTracker and OutlookManager.

All Outlook COM work runs in a background QThread.  The bridge provides:
  - ``OutlookScanWorker`` — QThread that scans for [TSK-XXX] replies
  - Helper functions for sending task emails and searching contacts
"""

import logging
import re
from datetime import datetime
from typing import List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from suiteview.tasktracker.models import Email, Contact, Task
from suiteview.tasktracker.storage import Storage

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════
#  Background email scan worker
# ════════════════════════════════════════════════════════════════════

class OutlookScanWorker(QThread):
    """Scan Outlook for new emails matching tracked task IDs.

    Emits ``results_ready`` with a list of ``(task_id, Email)`` tuples
    representing *new* emails not yet stored.
    """

    results_ready = pyqtSignal(list)   # List[Tuple[str, Email]]

    def __init__(self, task_ids: List[str], known_entry_ids: set,
                 parent=None):
        super().__init__(parent)
        self._task_ids = task_ids
        self._known_ids = known_entry_ids

    def run(self):
        results = []
        try:
            from suiteview.core.outlook_manager import (
                get_outlook_manager, close_thread_outlook_manager,
            )
            om = get_outlook_manager()
            raw_emails = om.scan_for_task_replies(
                self._task_ids, self._known_ids,
            )
            for info in raw_emails:
                # Determine which task_id this email belongs to
                match = re.search(r'\[(TSK-\d{3,})\]', info.subject or "")
                if not match:
                    continue
                task_id = match.group(1)

                # Determine sent vs received
                is_sent = "Sent" in (info.folder_path or "")
                email_type = "sent" if is_sent else "received"
                from_name = "You" if is_sent else (info.sender or "Unknown")

                # Format date
                try:
                    dt = info.received_date
                    date_str = dt.strftime("%b %d, %I:%M %p").replace(" 0", " ")
                    # Build numeric sort key  YYYYMMDD.HHMM
                    date_sort = float(dt.strftime("%Y%m%d")) + float(dt.strftime("%H%M")) / 10000
                except Exception:
                    date_str = str(info.received_date)
                    date_sort = 0

                email = Email(
                    from_addr=from_name,
                    to_addr=info.sender_email if is_sent else "You",
                    date=date_str,
                    date_sort=date_sort,
                    subject=info.subject or "",
                    body=(info.body_preview or "").strip(),
                    type=email_type,
                    has_attachment=info.has_attachments,
                    outlook_entry_id=info.email_id,
                )
                results.append((task_id, email))

        except Exception as e:
            logger.warning(f"OutlookScanWorker failed: {e}")
        finally:
            try:
                from suiteview.core.outlook_manager import close_thread_outlook_manager
                close_thread_outlook_manager()
            except Exception:
                pass

        self.results_ready.emit(results)


# ════════════════════════════════════════════════════════════════════
#  Contact search worker
# ════════════════════════════════════════════════════════════════════

class ContactSearchWorker(QThread):
    """Search Outlook contacts/GAL in the background."""

    results_ready = pyqtSignal(list)  # List[Contact]

    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self._query = query

    def run(self):
        results = []
        try:
            from suiteview.core.outlook_manager import (
                get_outlook_manager, close_thread_outlook_manager,
            )
            om = get_outlook_manager()
            raw = om.search_contacts(self._query)
            results = [Contact(name=c["name"], email=c["email"]) for c in raw]
        except Exception as e:
            logger.warning(f"ContactSearchWorker failed: {e}")
        finally:
            try:
                from suiteview.core.outlook_manager import close_thread_outlook_manager
                close_thread_outlook_manager()
            except Exception:
                pass
        self.results_ready.emit(results)


# ════════════════════════════════════════════════════════════════════
#  Background email-send workers
# ════════════════════════════════════════════════════════════════════

class SendTaskEmailWorker(QThread):
    """Send initial task email in a background thread to avoid UI freeze."""

    def __init__(self, task: Task, body: str, parent=None):
        super().__init__(parent)
        self._task = task
        self._body = body
        self.success = False

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        try:
            recipients = [a.email for a in self._task.assignees if a.email]
            if not recipients:
                logger.warning("SendTaskEmailWorker: no recipients")
                return

            subject = f"[{self._task.task_id}] {self._task.title[:60]}"

            from suiteview.core.outlook_manager import (
                get_outlook_manager, close_thread_outlook_manager,
            )
            om = get_outlook_manager()
            self.success = om.send_task_email(recipients, subject, self._body)
        except Exception as e:
            logger.error(f"SendTaskEmailWorker failed: {e}")
        finally:
            try:
                from suiteview.core.outlook_manager import close_thread_outlook_manager
                close_thread_outlook_manager()
            except Exception:
                pass
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


class SendReplyWorker(QThread):
    """Send a reply email in a background thread to avoid UI freeze."""

    send_complete = pyqtSignal(bool)

    def __init__(self, task: Task, reply_body: str,
                 reply_to_email: Email, parent=None):
        super().__init__(parent)
        self._task = task
        self._reply_body = reply_body
        self._reply_to = reply_to_email

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        success = False
        try:
            email = self._reply_to
            to_addr = email.to_addr if email.type == "received" else email.from_addr
            if to_addr == "You":
                to_addr = email.from_addr if email.type == "received" else email.to_addr

            if to_addr and "@" not in to_addr:
                for a in self._task.assignees:
                    if a.name == to_addr and a.email:
                        to_addr = a.email
                        break

            if not to_addr or "@" not in to_addr:
                logger.warning(f"SendReplyWorker: bad recipient '{to_addr}'")
                return

            subject = f"Re: [{self._task.task_id}] {self._task.title[:60]}"

            from suiteview.core.outlook_manager import (
                get_outlook_manager, close_thread_outlook_manager,
            )
            om = get_outlook_manager()
            success = om.send_task_email([to_addr], subject, self._reply_body)
        except Exception as e:
            logger.error(f"SendReplyWorker failed: {e}")
        finally:
            try:
                from suiteview.core.outlook_manager import close_thread_outlook_manager
                close_thread_outlook_manager()
            except Exception:
                pass
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self.send_complete.emit(success)


# ════════════════════════════════════════════════════════════════════
#  Synchronous helpers (kept for backward compatibility)
# ════════════════════════════════════════════════════════════════════

def send_task_email(task: Task, body: str) -> bool:
    """Send the initial task email via Outlook.

    Builds the recipient list from the task's assignees and sends
    a plain-text email with ``[TSK-XXX]`` in the subject.
    Returns True on success.
    """
    recipients = [a.email for a in task.assignees if a.email]
    if not recipients:
        logger.warning("send_task_email: no recipients")
        return False

    subject = f"[{task.task_id}] {task.title[:60]}"

    try:
        from suiteview.core.outlook_manager import get_outlook_manager
        om = get_outlook_manager()
        return om.send_task_email(recipients, subject, body)
    except Exception as e:
        logger.error(f"send_task_email failed: {e}")
        return False


def send_reply(task: Task, reply_body: str,
               reply_to_email: Email) -> bool:
    """Send a reply email for a task thread."""
    to_addr = reply_to_email.to_addr if reply_to_email.type == "received" else reply_to_email.from_addr
    if to_addr == "You":
        # Original was sent by us; reply goes back to the sender of the received email
        to_addr = reply_to_email.from_addr if reply_to_email.type == "received" else reply_to_email.to_addr

    # If to_addr still looks like a name, try to find the email in assignees
    if to_addr and "@" not in to_addr:
        for a in task.assignees:
            if a.name == to_addr and a.email:
                to_addr = a.email
                break

    if not to_addr or "@" not in to_addr:
        logger.warning(f"send_reply: could not determine recipient from '{to_addr}'")
        return False

    subject = f"Re: [{task.task_id}] {task.title[:60]}"

    try:
        from suiteview.core.outlook_manager import get_outlook_manager
        om = get_outlook_manager()
        return om.send_task_email([to_addr], subject, reply_body)
    except Exception as e:
        logger.error(f"send_reply failed: {e}")
        return False


def open_email_in_outlook(entry_id: str) -> bool:
    """Open an email in Outlook by its EntryID."""
    if not entry_id:
        return False
    try:
        from suiteview.core.outlook_manager import get_outlook_manager
        om = get_outlook_manager()
        return om.open_email(entry_id)
    except Exception as e:
        logger.error(f"open_email_in_outlook failed: {e}")
        return False
