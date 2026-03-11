"""
TaskTracker Storage — JSON-backed persistence for tasks, contacts, and ID sequence.

File location: ``~/.suiteview/tasktracker.json``

Structure::

    {
        "next_id": 7,
        "contacts": [{"name": "...", "email": "..."}, ...],
        "tasks": [
            {
                "id": 1,
                "task_id": "TSK-001",
                "title": "...",
                "status": "open",
                "created_date": "2026-02-08",
                "assignees": [{"name": "...", "email": "..."}],
                "email_sent": false,
                "last_activity": null,
                "last_activity_sort": 999,
                "last_activity_from": null,
                "emails": [
                    {
                        "from_addr": "You",
                        "to_addr": "...",
                        "date": "Feb 8, 10:00 AM",
                        "date_sort": 20260208.1000,
                        "subject": "[TSK-001] ...",
                        "body": "...",
                        "type": "sent",
                        "has_attachment": false,
                        "outlook_entry_id": ""
                    }
                ]
            }
        ]
    }

All mutations call ``_save()`` immediately so data is never lost.
Writes are atomic (write to .tmp then rename).
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from suiteview.tasktracker.constants import (
    SEED_CONTACTS, STATUS_OPEN, TASK_ID_PREFIX,
)
from suiteview.tasktracker.models import Task, Email, Contact

logger = logging.getLogger(__name__)

_DATA_DIR = Path.home() / ".suiteview"
_DATA_FILE = _DATA_DIR / "tasktracker.json"


class Storage:
    """JSON-backed store for TaskTracker data.

    Data is loaded once into memory and saved after every mutation.
    Thread-safety note: this class is NOT thread-safe — it should only be
    called from the main (UI) thread.  Background threads communicate via
    signals.
    """

    def __init__(self, path: Path = _DATA_FILE):
        self._path = path
        self._data: Dict[str, Any] = {}
        self._load()

    # ── File I/O ────────────────────────────────────────────────────

    def _load(self):
        """Load data from disk (or create with seed data on first run)."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"TaskTracker: loaded {len(self._data.get('tasks', []))} tasks from {self._path}")
                return
            except Exception as e:
                logger.error(f"TaskTracker: failed to load {self._path}: {e}")

        # First run — seed
        self._data = {
            "next_id": 1,
            "contacts": [dict(c) for c in SEED_CONTACTS],
            "tasks": [],
        }
        self._save()
        logger.info("TaskTracker: created new data file with seed contacts")

    def _save(self):
        """Atomic write: write to .tmp then rename."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            # On Windows, target must not exist for os.rename
            if self._path.exists():
                os.replace(str(tmp), str(self._path))
            else:
                os.rename(str(tmp), str(self._path))
        except Exception as e:
            logger.error(f"TaskTracker: failed to save: {e}")

    # ── Task ID generation ──────────────────────────────────────────

    def next_task_id(self) -> str:
        """Return the next ``TSK-NNN`` string and bump the counter."""
        n = self._data.get("next_id", 1)
        tid = f"{TASK_ID_PREFIX}-{n:03d}"
        self._data["next_id"] = n + 1
        self._save()
        return tid

    # ── Task CRUD ───────────────────────────────────────────────────

    def create_task(self, title: str) -> Task:
        """Create a new open task with the given title."""
        task_id = self.next_task_id()
        task_num = self._data["next_id"] - 1  # the id we just used
        now = datetime.now().strftime("%Y-%m-%d")
        task_dict: Dict[str, Any] = {
            "id": task_num,
            "task_id": task_id,
            "title": title,
            "status": STATUS_OPEN,
            "created_date": now,
            "assignees": [],
            "email_sent": False,
            "last_activity": None,
            "last_activity_sort": 999,
            "last_activity_from": None,
            "emails": [],
        }
        self._data["tasks"].insert(0, task_dict)  # newest first
        self._save()
        return self._dict_to_task(task_dict)

    def update_task(self, task: Task):
        """Replace the stored task dict matching ``task.task_id``."""
        tasks = self._data["tasks"]
        for i, t in enumerate(tasks):
            if t["task_id"] == task.task_id:
                tasks[i] = self._task_to_dict(task)
                self._save()
                return
        logger.warning(f"update_task: {task.task_id} not found")

    def delete_task(self, task_id: str):
        """Permanently remove a task by its display ID (e.g. 'TSK-001')."""
        before = len(self._data["tasks"])
        self._data["tasks"] = [
            t for t in self._data["tasks"] if t["task_id"] != task_id
        ]
        if len(self._data["tasks"]) < before:
            self._save()
            logger.info(f"Deleted task {task_id}")
        else:
            logger.warning(f"delete_task: {task_id} not found")

    def get_task(self, task_id: str) -> Optional[Task]:
        """Return a single task by display ID, or None."""
        for t in self._data["tasks"]:
            if t["task_id"] == task_id:
                return self._dict_to_task(t)
        return None

    def get_all_tasks(self) -> List[Task]:
        """Return all tasks as model objects."""
        return [self._dict_to_task(t) for t in self._data["tasks"]]

    # ── Assignee helpers ────────────────────────────────────────────

    def add_assignee(self, task_id: str, contact: Contact):
        """Add a contact as assignee to a task (no-op if already assigned)."""
        for t in self._data["tasks"]:
            if t["task_id"] == task_id:
                existing = {a["email"] for a in t["assignees"] if a.get("email")}
                if contact.email and contact.email in existing:
                    return
                t["assignees"].append({"name": contact.name, "email": contact.email})
                self._save()
                return

    def remove_assignee(self, task_id: str, email: str = "", name: str = ""):
        """Remove an assignee by email (preferred) or name."""
        for t in self._data["tasks"]:
            if t["task_id"] == task_id:
                if email:
                    t["assignees"] = [a for a in t["assignees"] if a.get("email") != email]
                elif name:
                    t["assignees"] = [a for a in t["assignees"] if a.get("name") != name]
                self._save()
                return

    # ── Email helpers ───────────────────────────────────────────────

    def add_email(self, task_id: str, email: Email):
        """Append an email to a task's thread."""
        for t in self._data["tasks"]:
            if t["task_id"] == task_id:
                t["emails"].append(self._email_to_dict(email))
                self._save()
                return

    def get_all_entry_ids(self) -> set:
        """Return a set of all stored Outlook EntryIDs across all tasks."""
        ids = set()
        for t in self._data["tasks"]:
            for e in t.get("emails", []):
                eid = e.get("outlook_entry_id", "")
                if eid:
                    ids.add(eid)
        return ids

    def get_task_ids_with_email(self) -> List[str]:
        """Return task_ids that have email_sent == True (candidates for scanning)."""
        return [
            t["task_id"] for t in self._data["tasks"]
            if t.get("email_sent") and t.get("status") == STATUS_OPEN
        ]

    # ── Contact helpers ─────────────────────────────────────────────

    def get_contacts(self) -> List[Contact]:
        """Return all contacts."""
        return [
            Contact(name=c["name"], email=c["email"])
            for c in self._data.get("contacts", [])
        ]

    def add_contact(self, name: str, email: str):
        """Add a new contact if the email doesn't already exist."""
        existing = {c["email"] for c in self._data.get("contacts", []) if c.get("email")}
        if email and email in existing:
            return
        self._data.setdefault("contacts", []).append({"name": name, "email": email})
        self._save()

    # ── Serialisation helpers ───────────────────────────────────────

    @staticmethod
    def _dict_to_task(d: dict) -> Task:
        assignees = [Contact(name=a["name"], email=a.get("email", "")) for a in d.get("assignees", [])]
        emails = [
            Email(
                from_addr=e.get("from_addr", ""),
                to_addr=e.get("to_addr", ""),
                date=e.get("date", ""),
                date_sort=e.get("date_sort", 0),
                subject=e.get("subject", ""),
                body=e.get("body", ""),
                type=e.get("type", "sent"),
                has_attachment=e.get("has_attachment", False),
                outlook_entry_id=e.get("outlook_entry_id", ""),
            )
            for e in d.get("emails", [])
        ]
        return Task(
            id=d.get("id", 0),
            task_id=d.get("task_id", ""),
            title=d.get("title", ""),
            status=d.get("status", "open"),
            created_date=d.get("created_date", ""),
            assignees=assignees,
            email_sent=d.get("email_sent", False),
            last_activity=d.get("last_activity"),
            last_activity_sort=d.get("last_activity_sort", 999),
            last_activity_from=d.get("last_activity_from"),
            emails=emails,
        )

    @staticmethod
    def _task_to_dict(task: Task) -> dict:
        return {
            "id": task.id,
            "task_id": task.task_id,
            "title": task.title,
            "status": task.status,
            "created_date": task.created_date,
            "assignees": [{"name": a.name, "email": a.email} for a in task.assignees],
            "email_sent": task.email_sent,
            "last_activity": task.last_activity,
            "last_activity_sort": task.last_activity_sort,
            "last_activity_from": task.last_activity_from,
            "emails": [Storage._email_to_dict(e) for e in task.emails],
        }

    @staticmethod
    def _email_to_dict(email: Email) -> dict:
        return {
            "from_addr": email.from_addr,
            "to_addr": email.to_addr,
            "date": email.date,
            "date_sort": email.date_sort,
            "subject": email.subject,
            "body": email.body,
            "type": email.type,
            "has_attachment": email.has_attachment,
            "outlook_entry_id": email.outlook_entry_id,
        }
