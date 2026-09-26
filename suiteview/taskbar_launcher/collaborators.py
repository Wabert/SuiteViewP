"""Explicit collaborators for the SuiteView shell window."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PyQt6.QtWidgets import QWidget


class TaskbarHost(Protocol):
    """Window surface required by taskbar collaborators."""

    def layout(self): ...
    def isVisible(self) -> bool: ...
    def setGeometry(self, *args): ...
    def winId(self): ...


@dataclass(slots=True)
class TaskbarState:
    """Mutable state owned by ``SuiteViewTaskbar`` and shared intentionally."""

    compact: bool = False
    floating: bool = False
    appbar_registered: bool = False
    hidden_to_tray: bool = False


class WindowCollaborator:
    """Base for collaborators that operate on an explicit host widget."""

    _local_names = {"host"}

    def __init__(self, host: QWidget) -> None:
        object.__setattr__(self, "host", host)

    def __getattr__(self, name: str):
        return getattr(self.host, name)

    def __setattr__(self, name: str, value) -> None:
        if name in self._local_names or name.startswith("_controller_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self.host, name, value)
