"""Folder-scoped permission policy for Copilot agent tools."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from copilot.generated.rpc import (
    PermissionDecisionApproveOnce,
    PermissionDecisionReject,
)

_BLOCKED_COMMANDS = {
    "bcdedit",
    "cipher",
    "diskpart",
    "format",
    "reg",
    "regedit",
    "restart-computer",
    "shutdown",
    "stop-computer",
}
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z]:[\\/][^\s\"']+)")


class FolderPermissionPolicy:
    """Approve local agent actions only when they stay in one assigned folder."""

    def __init__(self, folder: str | Path):
        self.folder = Path(folder).expanduser().resolve()
        if not self.folder.is_dir():
            raise ValueError(f"Agent folder does not exist: {self.folder}")

    def _resolve_path(self, value: str) -> Path:
        expanded = os.path.expandvars(os.path.expanduser(value.strip().strip("\"'")))
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = self.folder / candidate
        return candidate.resolve(strict=False)

    def contains(self, value: str) -> bool:
        try:
            self._resolve_path(value).relative_to(self.folder)
            return True
        except (OSError, RuntimeError, ValueError):
            return False

    def _reject(self, feedback: str) -> PermissionDecisionReject:
        return PermissionDecisionReject(feedback=feedback)

    def __call__(self, request: Any, invocation: dict[str, str]):
        del invocation
        kind = getattr(request, "kind", "")

        if getattr(request, "request_sandbox_bypass", False):
            return self._reject("SuiteView does not allow sandbox bypass requests.")

        if kind == "read":
            return (
                PermissionDecisionApproveOnce()
                if self.contains(request.path)
                else self._reject("Read access is limited to the assigned folder.")
            )

        if kind == "write":
            return (
                PermissionDecisionApproveOnce()
                if self.contains(request.file_name)
                else self._reject("Write access is limited to the assigned folder.")
            )

        if kind == "shell":
            if getattr(request, "possible_urls", []):
                return self._reject(
                    "Network commands are not enabled in SuiteView Agent Chat."
                )
            identifiers = {
                command.identifier.lower()
                for command in getattr(request, "commands", [])
            }
            if identifiers & _BLOCKED_COMMANDS:
                return self._reject(
                    "This system-level command is blocked by SuiteView."
                )
            possible_paths = list(getattr(request, "possible_paths", []))
            possible_paths.extend(
                match.group(1)
                for match in _WINDOWS_ABSOLUTE_PATH.finditer(
                    getattr(request, "full_command_text", "")
                )
            )
            if any(not self.contains(path) for path in possible_paths):
                return self._reject("Shell access is limited to the assigned folder.")
            return PermissionDecisionApproveOnce()

        return self._reject(
            f"SuiteView Agent Chat does not enable '{kind or 'unknown'}' permissions."
        )
