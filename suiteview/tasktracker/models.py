"""
TaskTracker Models — Data classes for Task, Email, Contact.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Contact:
    """A team member / assignable person."""
    name: str
    email: str


@dataclass
class Email:
    """An email in a task's thread."""
    from_addr: str            # "You" or person display name
    to_addr: str              # Recipient email/name
    date: str                 # Human-readable ("Feb 3, 2:15 PM")
    date_sort: float          # Numeric for sorting (e.g. 20260203.1415)
    subject: str
    body: str
    type: str                 # "sent" or "received"
    has_attachment: bool = False
    outlook_entry_id: str = ""  # Outlook EntryID for reopening


@dataclass
class Task:
    """A tracked task."""
    id: int                          # Internal numeric id (sequence key)
    task_id: str                     # Display id, e.g. "TSK-001"
    title: str
    status: str = "open"             # "open" or "closed"
    created_date: str = ""           # ISO "YYYY-MM-DD"
    assignees: List[Contact] = field(default_factory=list)
    email_sent: bool = False
    last_activity: Optional[str] = None        # "2h ago", "Just now", "—"
    last_activity_sort: float = 999.0          # hours since activity
    last_activity_from: Optional[str] = None   # "You" or assignee name
    emails: List[Email] = field(default_factory=list)
