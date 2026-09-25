"""Atomic JSON persistence for SuiteView Agent Chat sessions."""

from __future__ import annotations

from suiteview.core.profile_paths import profile_path

import json
from pathlib import Path
from typing import Iterable

from suiteview.core.json_store import write_json
from .models import AgentConversation


class ConversationStoreError(RuntimeError):
    """Raised when saved conversations cannot be read or written."""


class ConversationStore:
    def __init__(self, root: Path | None = None):
        self.root = root or profile_path('agent_chat')
        self.path = self.root / "sessions.json"

    def load(self) -> list[AgentConversation]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            conversations = [
                AgentConversation.from_dict(item)
                for item in payload.get("conversations", [])
            ]
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ConversationStoreError(
                f"Could not load agent chat history from {self.path}: {exc}"
            ) from exc
        return sorted(conversations, key=lambda item: item.updated_at, reverse=True)

    def save(self, conversations: Iterable[AgentConversation]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "conversations": [item.to_dict() for item in conversations],
        }
        try:
            write_json(self.path, payload)
        except OSError as exc:
            raise ConversationStoreError(
                f"Could not save agent chat history to {self.path}: {exc}"
            ) from exc
