"""Private, persistent per-policy notes and the recently viewed policy list.

Both live in the user's local SuiteView profile (never shared, never DB2):
notes under ``data/notes/polview_notes.json`` and recents under
``settings/polview_recent.json``. Writes are atomic via ``core.json_store``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from suiteview.core.json_store import JsonStore
from suiteview.core.profile_paths import profile_path

MAX_RECENT = 40


def policy_key(company_code: str, policy_number: str) -> str:
    return f"{(company_code or '').strip().upper()}|{(policy_number or '').strip().upper()}"


@dataclass(frozen=True)
class PolicyNote:
    created: str
    text: str


class PolicyNotesStore:
    """Timestamped notes keyed by company + policy number (region-independent)."""

    def __init__(self, path=None):
        self._store = JsonStore(path or profile_path("polview_notes.json"), default={})

    def notes(self, company_code: str, policy_number: str) -> list[PolicyNote]:
        rows = self._store.load().get(policy_key(company_code, policy_number), [])
        return [PolicyNote(str(r.get("created", "")), str(r.get("text", ""))) for r in rows
                if isinstance(r, dict)]

    def count(self, company_code: str, policy_number: str) -> int:
        return len(self.notes(company_code, policy_number))

    def add(self, company_code: str, policy_number: str, text: str,
            now: Optional[datetime] = None) -> PolicyNote:
        text = (text or "").strip()
        if not text:
            raise ValueError("A note cannot be empty.")
        note = PolicyNote((now or datetime.now()).strftime("%Y-%m-%d %H:%M"), text)
        data = self._store.load()
        data.setdefault(policy_key(company_code, policy_number), []).append(
            {"created": note.created, "text": note.text}
        )
        self._store.save(data)
        return note

    def delete(self, company_code: str, policy_number: str, index: int):
        data = self._store.load()
        key = policy_key(company_code, policy_number)
        rows = data.get(key, [])
        if not 0 <= index < len(rows):
            raise IndexError("No such note.")
        del rows[index]
        if rows:
            data[key] = rows
        else:
            data.pop(key, None)
        self._store.save(data)


class RecentPoliciesStore:
    """Most-recently viewed policies with enough context to recognise them."""

    def __init__(self, path=None):
        self._store = JsonStore(path or profile_path("polview_recent.json"), default=[])

    def entries(self) -> list[dict]:
        rows = self._store.load()
        return [r for r in rows if isinstance(r, dict) and r.get("policy")] if isinstance(rows, list) else []

    def record(self, *, policy: str, company: str, region: str,
               insured: str = "", plancode: str = "", now: Optional[datetime] = None):
        policy = (policy or "").strip().upper()
        if not policy:
            return
        company = (company or "").strip().upper()
        region = (region or "").strip().upper()
        entries = [
            r for r in self.entries()
            if not (r.get("policy") == policy and r.get("company") == company
                    and r.get("region") == region)
        ]
        previous = next((r for r in self.entries() if r.get("policy") == policy
                         and r.get("company") == company and r.get("region") == region), {})
        entries.insert(0, {
            "policy": policy, "company": company, "region": region,
            "insured": insured or previous.get("insured", ""),
            "plancode": plancode or previous.get("plancode", ""),
            "viewed": (now or datetime.now()).strftime("%Y-%m-%d %H:%M"),
        })
        self._store.save(entries[:MAX_RECENT])
