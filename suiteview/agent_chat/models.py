"""Persistent chat session models for SuiteView Agent Chat."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class AgentMessage:
    role: str
    content: str
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":
        role = str(data.get("role", "assistant"))
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported chat message role: {role}")
        return cls(
            role=role,
            content=str(data.get("content", "")),
            timestamp=str(data.get("timestamp", _now())),
        )


@dataclass
class AgentConversation:
    id: str
    sdk_session_id: str
    title: str = "New chat"
    folder: str = ""
    model: str = "auto"
    sdk_session_started: bool = False
    messages: list[AgentMessage] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(cls, folder: str = "", model: str = "auto") -> "AgentConversation":
        conversation_id = uuid4().hex
        return cls(
            id=conversation_id,
            sdk_session_id=f"suiteview-{conversation_id}",
            folder=str(Path(folder).resolve()) if folder else "",
            model=model,
        )

    def touch(self) -> None:
        self.updated_at = _now()

    def add_message(self, role: str, content: str) -> AgentMessage:
        message = AgentMessage(role=role, content=content)
        self.messages.append(message)
        self.touch()
        if role == "user" and self.title == "New chat":
            compact = " ".join(content.split())
            self.title = compact[:52] + ("..." if len(compact) > 52 else "")
        return message

    @property
    def folder_name(self) -> str:
        return Path(self.folder).name if self.folder else "No folder"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sdk_session_id": self.sdk_session_id,
            "title": self.title,
            "folder": self.folder,
            "model": self.model,
            "sdk_session_started": self.sdk_session_started,
            "messages": [message.to_dict() for message in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConversation":
        conversation_id = str(data["id"])
        return cls(
            id=conversation_id,
            sdk_session_id=str(
                data.get("sdk_session_id", f"suiteview-{conversation_id}")
            ),
            title=str(data.get("title", "New chat")),
            folder=str(data.get("folder", "")),
            model=str(data.get("model", "auto")),
            sdk_session_started=bool(data.get("sdk_session_started", False)),
            messages=[
                AgentMessage.from_dict(message) for message in data.get("messages", [])
            ],
            created_at=str(data.get("created_at", _now())),
            updated_at=str(data.get("updated_at", _now())),
        )
