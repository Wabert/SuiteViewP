"""Tests for the Copilot SDK-backed SuiteView Agent Chat."""

import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from copilot.generated.rpc import (
    PermissionDecisionApproveOnce,
    PermissionDecisionReject,
)

from suiteview.agent_chat.models import AgentConversation
from suiteview.agent_chat.permissions import FolderPermissionPolicy
from suiteview.agent_chat.store import ConversationStore, ConversationStoreError
from suiteview.agent_chat.window import ActivityRow, AgentChatWindow
from suiteview.agent_chat.workers import AgentRunWorker
from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar

_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_conversation_store_round_trip(tmp_path):
    store = ConversationStore(tmp_path / "agent-chat")
    conversation = AgentConversation.create(folder=str(tmp_path), model="auto")
    conversation.add_message("user", "Inspect this project")
    conversation.add_message("assistant", "I found three modules.")
    conversation.sdk_session_started = True

    store.save([conversation])
    loaded = store.load()

    assert len(loaded) == 1
    assert loaded[0].sdk_session_id == conversation.sdk_session_id
    assert loaded[0].folder == str(tmp_path.resolve())
    assert loaded[0].sdk_session_started is True
    assert [message.role for message in loaded[0].messages] == ["user", "assistant"]
    assert loaded[0].title == "Inspect this project"


def test_conversation_store_surfaces_corrupt_history(tmp_path):
    store = ConversationStore(tmp_path / "agent-chat")
    store.root.mkdir(parents=True)
    store.path.write_text("not json", encoding="utf-8")

    with pytest.raises(ConversationStoreError, match="Could not load"):
        store.load()


def test_folder_permission_policy_limits_file_actions(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.txt"
    policy = FolderPermissionPolicy(project)

    inside_read = SimpleNamespace(kind="read", path=str(project / "app.py"))
    outside_write = SimpleNamespace(
        kind="write",
        file_name=str(outside),
        request_sandbox_bypass=False,
    )

    assert isinstance(policy(inside_read, {}), PermissionDecisionApproveOnce)
    assert isinstance(policy(outside_write, {}), PermissionDecisionReject)


def test_folder_permission_policy_rejects_network_and_outside_shell(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    policy = FolderPermissionPolicy(project)

    safe_shell = SimpleNamespace(
        kind="shell",
        possible_urls=[],
        possible_paths=[str(project / "tests")],
        commands=[SimpleNamespace(identifier="python", read_only=False)],
        full_command_text="python -m pytest tests",
        request_sandbox_bypass=False,
    )
    network_shell = SimpleNamespace(
        kind="shell",
        possible_urls=[SimpleNamespace(url="https://example.com")],
        possible_paths=[],
        commands=[SimpleNamespace(identifier="curl", read_only=False)],
        full_command_text="curl https://example.com",
        request_sandbox_bypass=False,
    )

    assert isinstance(policy(safe_shell, {}), PermissionDecisionApproveOnce)
    assert isinstance(policy(network_shell, {}), PermissionDecisionReject)


def test_agent_chat_window_is_orange_frameless_and_starts_with_session(tmp_path):
    _app()
    store = ConversationStore(tmp_path / "agent-chat")
    with patch.object(AgentChatWindow, "_load_models"):
        window = AgentChatWindow(store=store)

    assert window._header_colors[0] == "#F97316"
    assert window.session_list.topLevelItemCount() == 1
    assert window.session_list.topLevelItem(0).childCount() == 1
    assert window.current_conversation is not None
    assert window.current_conversation.title == "New chat"
    assert window.prompt_edit.isEnabled() is False
    window.close()


def test_taskbar_reuses_agent_chat_window(monkeypatch):
    _app()
    import suiteview.agent_chat as agent_chat_package

    class FakeWindow:
        def isVisible(self):
            return True

    created = []
    window = FakeWindow()
    monkeypatch.setattr(
        agent_chat_package,
        "AgentChatWindow",
        lambda: created.append(window) or window,
    )

    bar = SuiteViewTaskbar.__new__(SuiteViewTaskbar)
    bar.agent_chat_window = None
    setup = []
    shown = []
    bar._setup_child_window = lambda child, title: setup.append((child, title))
    bar._bring_to_front = lambda child: shown.append(child)

    bar._open_agent_chat()
    bar._open_agent_chat()

    assert created == [window]
    assert setup == [(window, "LLM Agent")]
    assert shown == [window, window]


def test_agent_worker_captures_autopilot_assistant_message(tmp_path):
    conversation = AgentConversation.create(folder=str(tmp_path))
    worker = AgentRunWorker(conversation, "hello")
    event = SimpleNamespace(
        type="assistant.message",
        data=SimpleNamespace(content="Agent finished"),
    )

    worker._on_event(event)

    assert worker._last_assistant_message == "Agent finished"


def test_bottom_model_selector_tracks_selected_thread(tmp_path):
    _app()
    store = ConversationStore(tmp_path / "agent-chat")
    first = AgentConversation.create(folder=str(tmp_path), model="claude-opus-4.8")
    first.title = "Opus thread"
    first.updated_at = "2026-07-23T03:00:00-05:00"
    second = AgentConversation.create(folder=str(tmp_path), model="gpt-5.6-sol")
    second.title = "GPT thread"
    second.updated_at = "2026-07-23T02:00:00-05:00"
    store.save([first, second])

    with patch.object(AgentChatWindow, "_load_models"):
        window = AgentChatWindow(store=store)

    assert window.model_combo.currentData() == "claude-opus-4.8"
    root = window.session_list.topLevelItem(0)
    window.session_list.setCurrentItem(root.child(1))
    assert window.current_conversation.id == second.id
    assert window.model_combo.currentData() == "gpt-5.6-sol"
    assert window.model_combo.parentWidget().objectName() == "composerPanel"
    window.close()


def test_session_rows_show_title_and_folder_is_in_bottom_bar(tmp_path):
    _app()
    store = ConversationStore(tmp_path / "agent-chat")
    project = tmp_path / "my-project"
    project.mkdir()
    conversation = AgentConversation.create(folder=str(project))
    conversation.title = "Refactor billing"
    store.save([conversation])

    with patch.object(AgentChatWindow, "_load_models"):
        window = AgentChatWindow(store=store)

    root = window.session_list.topLevelItem(0)
    assert root.text(0) == "my-project"
    assert root.child(0).text(0) == "Refactor billing"
    assert window.folder_label.text() == "my-project"
    assert window.folder_label.toolTip() == str(project.resolve())
    assert window.folder_label.parentWidget().objectName() == "composerPanel"
    window.close()


def test_threads_are_grouped_under_folder_sessions(tmp_path):
    _app()
    store = ConversationStore(tmp_path / "agent-chat")
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    alpha.mkdir()
    beta.mkdir()
    first = AgentConversation.create(folder=str(alpha))
    first.title = "First alpha thread"
    second = AgentConversation.create(folder=str(alpha))
    second.title = "Second alpha thread"
    third = AgentConversation.create(folder=str(beta))
    third.title = "Beta thread"
    store.save([first, second, third])

    with patch.object(AgentChatWindow, "_load_models"):
        window = AgentChatWindow(store=store)

    assert window.session_list.topLevelItemCount() == 2
    groups = {
        window.session_list.topLevelItem(index).text(
            0
        ): window.session_list.topLevelItem(index)
        for index in range(window.session_list.topLevelItemCount())
    }
    assert [groups["alpha"].child(index).text(0) for index in range(2)] == [
        "First alpha thread",
        "Second alpha thread",
    ]
    assert groups["beta"].child(0).text(0) == "Beta thread"
    window.close()


def test_delete_selected_thread_preserves_other_folder_threads(tmp_path):
    _app()
    store = ConversationStore(tmp_path / "agent-chat")
    project = tmp_path / "project"
    project.mkdir()
    first = AgentConversation.create(folder=str(project))
    first.title = "Keep me"
    second = AgentConversation.create(folder=str(project))
    second.title = "Delete me"
    store.save([first, second])

    with patch.object(AgentChatWindow, "_load_models"):
        window = AgentChatWindow(store=store)

    root = window.session_list.topLevelItem(0)
    window.session_list.setCurrentItem(root.child(1))
    with patch(
        "suiteview.agent_chat.window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        window.delete_current()

    assert [conversation.title for conversation in window.conversations] == ["Keep me"]
    assert window.session_list.topLevelItem(0).childCount() == 1
    window.close()


def test_activity_events_append_distinct_timeline_rows(tmp_path):
    _app()
    store = ConversationStore(tmp_path / "agent-chat")
    conversation = AgentConversation.create(folder=str(tmp_path))
    store.save([conversation])

    with patch.object(AgentChatWindow, "_load_models"):
        window = AgentChatWindow(store=store)

    window._on_activity("thinking", "Thinking")
    window._on_activity("tool", "Using view")
    window._on_activity("waiting", "Waiting for model")
    window._on_activity("complete", "Completed")

    rows = window.messages_widget.findChildren(ActivityRow)
    labels = [
        label.text()
        for row in rows
        for label in row.findChildren(QLabel)
        if label.objectName() == "activityText"
    ]
    assert labels[-4:] == [
        "Thinking",
        "Using view",
        "Waiting for model",
        "Completed",
    ]
    window.close()


def test_agent_worker_emits_discrete_tool_activity(tmp_path):
    conversation = AgentConversation.create(folder=str(tmp_path))
    worker = AgentRunWorker(conversation, "hello")
    activity = []
    worker.activity_added.connect(lambda kind, text: activity.append((kind, text)))

    worker._on_event(
        SimpleNamespace(
            type="tool.execution_start",
            data=SimpleNamespace(tool_name="view"),
        )
    )
    worker._on_event(
        SimpleNamespace(type="tool.execution_complete", data=SimpleNamespace())
    )

    assert activity == [
        ("tool", "Using view"),
        ("tool_complete", "view finished"),
        ("waiting", "Waiting for model"),
    ]


def test_taskbar_source_exposes_agent_only_through_tools_menu():
    source_path = (
        os.path.dirname(__file__)
        + os.sep
        + ".."
        + os.sep
        + "suiteview"
        + os.sep
        + "taskbar_launcher"
        + os.sep
        + "suiteview_taskbar.py"
    )
    source = open(source_path, encoding="utf-8").read()

    assert 'self.tools_menu.addAction("LLM Agent", self._open_agent_chat)' in source
    assert "agent_chat_btn" not in source
    assert "_agent_chat_action" not in source
