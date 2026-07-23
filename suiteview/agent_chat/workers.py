"""Qt workers that isolate Copilot SDK async work from the UI thread."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from copilot import CopilotClient
from copilot.session_events import AssistantMessageDeltaData

from .models import AgentConversation
from .permissions import FolderPermissionPolicy

logger = logging.getLogger(__name__)


class ModelListWorker(QThread):
    models_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def run(self) -> None:
        try:
            models = asyncio.run(self._load_models())
            self.models_ready.emit(models)
        except Exception as exc:
            logger.error("Could not list Copilot models", exc_info=True)
            self.error_occurred.emit(str(exc))

    async def _load_models(self) -> list[dict[str, str]]:
        async with CopilotClient() as client:
            models = await client.list_models()
        return [
            {
                "id": model.id,
                "name": model.name,
            }
            for model in models
        ]


class AgentRunWorker(QThread):
    session_ready = pyqtSignal()
    token_received = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    activity_added = pyqtSignal(str, str)
    response_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, conversation: AgentConversation, prompt: str, parent=None):
        super().__init__(parent)
        self.conversation = conversation
        self.prompt = prompt
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session = None
        self._assembled_text = ""
        self._last_assistant_message = ""
        self._active_tool = ""
        self._response_started = False

    def cancel(self) -> None:
        self.requestInterruption()
        if self._loop is not None and self._session is not None:
            asyncio.run_coroutine_threadsafe(self._session.abort(), self._loop)

    def run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            response = self._loop.run_until_complete(self._run_agent())
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                self.response_complete.emit(response)
        except Exception as exc:
            if self.isInterruptionRequested():
                self.cancelled.emit()
            else:
                logger.error("Copilot agent request failed", exc_info=True)
                self.error_occurred.emit(str(exc))
        finally:
            self._session = None
            self._loop.close()
            self._loop = None

    async def _run_agent(self) -> str:
        folder = Path(self.conversation.folder).resolve()
        if not folder.is_dir():
            raise ValueError(f"Assigned folder does not exist: {folder}")

        permission_policy = FolderPermissionPolicy(folder)
        self._report_activity("starting", "Starting Copilot runtime")

        async with CopilotClient(working_directory=str(folder)) as client:
            session_options = {
                "model": self.conversation.model,
                "working_directory": str(folder),
                "on_permission_request": permission_policy,
                "streaming": True,
                "enable_session_store": True,
                "enable_skills": True,
            }
            if self.conversation.sdk_session_started:
                self._report_activity("session", "Resuming thread context")
                session = await client.resume_session(
                    self.conversation.sdk_session_id,
                    **session_options,
                )
            else:
                self._report_activity("session", "Creating agent session")
                session = await client.create_session(
                    session_id=self.conversation.sdk_session_id,
                    **session_options,
                )
                self.session_ready.emit()

            self._session = session
            session.on(self._on_event)
            try:
                self._report_activity("thinking", "Thinking")
                self._assembled_text = ""
                self._last_assistant_message = ""
                self._response_started = False
                self._active_tool = ""
                response = await session.send_and_wait(
                    self.prompt,
                    agent_mode="autopilot",
                    timeout=600,
                )
            finally:
                await session.disconnect()

        if response is None:
            raise RuntimeError("The Copilot agent finished without a response.")
        content = (
            getattr(response.data, "content", None)
            or self._last_assistant_message
            or self._assembled_text
        )
        if not content:
            raise RuntimeError("The Copilot agent returned an empty response.")
        return content

    def _report_activity(self, kind: str, text: str) -> None:
        self.status_changed.emit(text)
        self.activity_added.emit(kind, text)

    def _on_event(self, event) -> None:
        if self.isInterruptionRequested():
            return
        event_type = getattr(event.type, "value", event.type)
        data = event.data
        if isinstance(data, AssistantMessageDeltaData):
            if data.delta_content:
                if not self._response_started:
                    self._response_started = True
                    self._report_activity("responding", "Writing response")
                self._assembled_text += data.delta_content
                self.token_received.emit(data.delta_content)
        elif event_type == "assistant.message":
            content = getattr(data, "content", "")
            if content:
                self._last_assistant_message = content
        elif event_type == "tool.execution_start":
            self._active_tool = getattr(data, "tool_name", "tool")
            self._report_activity("tool", f"Using {self._active_tool}")
        elif event_type == "tool.execution_complete":
            tool_name = self._active_tool or "Tool"
            self._report_activity("tool_complete", f"{tool_name} finished")
            self._report_activity("waiting", "Waiting for model")
        elif event_type == "assistant.message_start" and not self._response_started:
            self._response_started = True
            self._report_activity("responding", "Writing response")
        elif event_type == "session.compaction_start":
            self._report_activity("context", "Compacting thread context")
