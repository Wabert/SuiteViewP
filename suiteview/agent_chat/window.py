"""Orange-branded native SuiteView window for Copilot agent sessions."""

from __future__ import annotations

import html
import logging
from pathlib import Path

import markdown
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase

from .models import AgentConversation, AgentMessage
from .store import ConversationStore, ConversationStoreError
from .workers import AgentRunWorker, ModelListWorker

logger = logging.getLogger(__name__)

ORANGE = "#F97316"
ORANGE_DARK = "#C2410C"
ORANGE_DEEP = "#7C2D12"
INK = "#241A14"
MUTED = "#75665D"
CREAM = "#FFF9F2"
PANEL = "#FFF3E6"
BORDER = "#F2C49F"


class PromptEdit(QTextEdit):
    send_requested = pyqtSignal()

    def keyPressEvent(self, event):
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.send_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MessageBubble(QFrame):
    def __init__(self, message: AgentMessage, model: str = "", parent=None):
        super().__init__(parent)
        self.message = message
        self.model = model
        self.setObjectName(
            "userBubble" if message.role == "user" else "assistantBubble"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 8)
        layout.setSpacing(3)

        heading = QHBoxLayout()
        role = "You" if message.role == "user" else (model or "Copilot Agent")
        role_label = QLabel(role)
        role_label.setObjectName("bubbleRole")
        heading.addWidget(role_label)
        heading.addStretch()
        time_label = QLabel(
            message.timestamp[11:16] if len(message.timestamp) >= 16 else ""
        )
        time_label.setObjectName("bubbleTime")
        heading.addWidget(time_label)
        layout.addLayout(heading)

        self.content_label = QLabel()
        self.content_label.setObjectName("bubbleContent")
        self.content_label.setWordWrap(True)
        self.content_label.setTextFormat(Qt.TextFormat.RichText)
        self.content_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.content_label.setOpenExternalLinks(True)
        layout.addWidget(self.content_label)
        self.set_content(message.content)

    def set_content(self, content: str) -> None:
        self.message.content = content
        escaped = html.escape(content)
        if self.message.role == "assistant":
            rendered = markdown.markdown(
                escaped,
                extensions=["fenced_code", "tables", "sane_lists"],
            )
        else:
            rendered = escaped.replace("\n", "<br>")
        self.content_label.setText(rendered or "<i>Working...</i>")


class ActivityRow(QFrame):
    ICONS = {
        "starting": "...",
        "session": "->",
        "thinking": "...",
        "tool": ">",
        "tool_complete": "+",
        "waiting": "...",
        "responding": ">",
        "context": "...",
        "complete": "+",
        "cancelled": "x",
        "error": "!",
    }

    def __init__(self, kind: str, text: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.text = text
        self.setObjectName("activityRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 10, 3)
        layout.setSpacing(7)

        icon = QLabel(self.ICONS.get(kind, "-"))
        icon.setObjectName(f"activityIcon_{kind}")
        icon.setFixedWidth(18)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        label = QLabel(text)
        label.setObjectName("activityText")
        label.setWordWrap(True)
        layout.addWidget(label, 1)


class AgentChatWindow(FramelessWindowBase):
    def __init__(self, parent=None, store: ConversationStore | None = None):
        self.store = store or ConversationStore()
        self.conversations: list[AgentConversation] = []
        self.current_conversation: AgentConversation | None = None
        self.worker: AgentRunWorker | None = None
        self.models_worker: ModelListWorker | None = None
        self.streaming_bubble: MessageBubble | None = None
        self.streaming_text = ""
        self._session_load_error = ""
        super().__init__(
            title="SuiteView LLM Agent",
            default_size=(1050, 680),
            min_size=(720, 500),
            parent=parent,
            header_colors=(ORANGE, ORANGE_DARK, ORANGE_DEEP),
            border_color="#FFB36B",
        )
        self.setWindowTitle("SuiteView LLM Agent")
        self._load_conversations()
        self._load_models()

    def build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("agentChatRoot")
        content.setStyleSheet(self._stylesheet())

        layout = QHBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_chat_panel())
        splitter.setSizes([215, 835])
        splitter.setHandleWidth(1)
        layout.addWidget(splitter)
        return content

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(185)
        sidebar.setMaximumWidth(280)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        eyebrow = QLabel("LLM WORKSPACE")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)

        title = QLabel("Sessions")
        title.setObjectName("sidebarTitle")
        layout.addWidget(title)

        new_button = QPushButton("+  New thread")
        new_button.setObjectName("primaryButton")
        new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        new_button.clicked.connect(self.new_conversation)
        layout.addWidget(new_button)

        self.session_list = QTreeWidget()
        self.session_list.setObjectName("sessionList")
        self.session_list.setHeaderHidden(True)
        self.session_list.setIndentation(14)
        self.session_list.setRootIsDecorated(True)
        self.session_list.setUniformRowHeights(True)
        self.session_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.session_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.session_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.session_list.currentItemChanged.connect(self._on_session_selected)
        self.session_list.customContextMenuRequested.connect(
            self._show_thread_context_menu
        )
        layout.addWidget(self.session_list, 1)

        session_actions = QHBoxLayout()
        self.rename_button = QPushButton("Rename")
        self.delete_button = QPushButton("Delete thread")
        for button in (self.rename_button, self.delete_button):
            button.setObjectName("quietButton")
            session_actions.addWidget(button)
        self.rename_button.clicked.connect(self.rename_current)
        self.delete_button.clicked.connect(self.delete_current)
        layout.addLayout(session_actions)

        safety = QLabel("Agent access stays inside the assigned folder.")
        safety.setObjectName("safetyNote")
        safety.setWordWrap(True)
        layout.addWidget(safety)
        return sidebar

    def _build_chat_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("chatPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("chatHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 14, 8)
        header_layout.setSpacing(8)

        self.chat_title = QLabel("New chat")
        self.chat_title.setObjectName("chatTitle")
        header_layout.addWidget(self.chat_title, 1)

        self.access_badge = QLabel("AGENT ACCESS")
        self.access_badge.setObjectName("accessBadge")
        header_layout.addWidget(self.access_badge)
        layout.addWidget(header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("messageScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.messages_widget = QWidget()
        self.messages_widget.setObjectName("messagesWidget")
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(18, 12, 18, 10)
        self.messages_layout.setSpacing(8)
        self.messages_layout.addStretch()
        self.scroll_area.setWidget(self.messages_widget)
        layout.addWidget(self.scroll_area, 1)

        composer = QFrame()
        composer.setObjectName("composerPanel")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(16, 8, 16, 9)
        composer_layout.setSpacing(5)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.prompt_edit = PromptEdit()
        self.prompt_edit.setObjectName("promptEdit")
        self.prompt_edit.setPlaceholderText(
            "Ask the agent to explain, investigate, build, test, or update this folder..."
        )
        self.prompt_edit.setMinimumHeight(62)
        self.prompt_edit.setMaximumHeight(105)
        self.prompt_edit.send_requested.connect(self.send_message)
        input_row.addWidget(self.prompt_edit, 1)

        button_column = QVBoxLayout()
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.setMinimumSize(76, 34)
        self.send_button.clicked.connect(self.send_message)
        button_column.addWidget(self.send_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setMinimumSize(76, 30)
        self.stop_button.setVisible(False)
        self.stop_button.clicked.connect(self.stop_agent)
        button_column.addWidget(self.stop_button)
        button_column.addStretch()
        input_row.addLayout(button_column)
        composer_layout.addLayout(input_row)

        footer_row = QHBoxLayout()
        footer_row.setSpacing(8)
        folder_prefix = QLabel("FOLDER")
        folder_prefix.setObjectName("folderPrefix")
        footer_row.addWidget(folder_prefix)
        self.folder_label = QLabel("Not assigned")
        self.folder_label.setObjectName("folderLabel")
        self.folder_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        footer_row.addWidget(self.folder_label)
        self.folder_button = QPushButton("Choose")
        self.folder_button.setObjectName("outlineButton")
        self.folder_button.clicked.connect(self.choose_folder)
        footer_row.addWidget(self.folder_button)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusLabel")
        footer_row.addWidget(self.status_label, 1)

        model_label = QLabel("THREAD MODEL")
        model_label.setObjectName("activeModelLabel")
        footer_row.addWidget(model_label)
        self.model_combo = QComboBox()
        self.model_combo.setObjectName("modelCombo")
        self.model_combo.setMinimumWidth(175)
        self.model_combo.setMaximumWidth(260)
        self.model_combo.addItem("Auto", "auto")
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        footer_row.addWidget(self.model_combo)
        composer_layout.addLayout(footer_row)
        layout.addWidget(composer)
        return panel

    def _stylesheet(self) -> str:
        return f"""
            QWidget#agentChatRoot {{ background: {CREAM}; color: {INK}; font-family: 'Segoe UI'; }}
            QFrame#sidebar {{ background: #211B17; border-right: 1px solid #4B3527; }}
            QLabel#eyebrow {{ color: #FB923C; font-size: 9px; font-weight: 700; letter-spacing: 2px; }}
            QLabel#sidebarTitle {{ color: #FFF7ED; font-size: 20px; font-weight: 650; padding-bottom: 2px; }}
            QPushButton#primaryButton {{ background: {ORANGE}; color: white; border: none; border-radius: 6px; padding: 7px 10px; font-size: 11px; font-weight: 700; text-align: left; }}
            QPushButton#primaryButton:hover {{ background: #FB923C; }}
            QTreeWidget#sessionList {{ background: transparent; color: #E7DDD6; border: none; outline: none; font-size: 11px; }}
            QTreeWidget#sessionList::item {{ padding: 0 4px; margin: 0; min-height: 21px; border-radius: 4px; }}
            QTreeWidget#sessionList::item:hover {{ background: #352A23; }}
            QTreeWidget#sessionList::item:selected {{ background: #4A2A18; color: #FDBA74; border-left: 3px solid {ORANGE}; }}
            QPushButton#quietButton {{ background: transparent; color: #C8B9AF; border: 1px solid #59483D; border-radius: 5px; padding: 4px; font-size: 12px; }}
            QPushButton#quietButton:hover {{ color: #FDBA74; border-color: {ORANGE}; }}
            QLabel#fieldLabel {{ color: #A99A90; font-size: 9px; font-weight: 700; letter-spacing: 1px; }}
            QComboBox#modelCombo {{ background: #FFFFFF; color: #7C2D12; border: 1px solid #F4A261; border-radius: 5px; padding: 4px 7px; font-size: 10px; font-weight: 650; }}
            QComboBox#modelCombo QAbstractItemView {{ background: #FFFFFF; color: {INK}; selection-background-color: #FFE2CC; selection-color: {ORANGE_DEEP}; }}
            QLabel#safetyNote {{ color: #C8B9AF; background: #2A211C; border: 1px solid #4B3A30; border-radius: 5px; padding: 6px; font-size: 10px; }}
            QFrame#chatPanel {{ background: {CREAM}; }}
            QFrame#chatHeader {{ background: #FFFDF9; border-bottom: 1px solid {BORDER}; }}
            QLabel#chatTitle {{ color: {INK}; font-size: 17px; font-weight: 650; }}
            QLabel#folderPrefix {{ color: {ORANGE_DARK}; font-size: 8px; font-weight: 800; letter-spacing: 1px; }}
            QLabel#folderLabel {{ color: {INK}; font-size: 10px; font-weight: 650; }}
            QPushButton#outlineButton {{ background: white; color: {ORANGE_DARK}; border: 1px solid #F4A261; border-radius: 5px; padding: 3px 7px; font-size: 10px; font-weight: 600; }}
            QPushButton#outlineButton:hover {{ background: #FFF1E5; border-color: {ORANGE}; }}
            QPushButton#outlineButton:disabled {{ color: #A89A91; border-color: #D8CEC7; background: #F5F1EE; }}
            QLabel#accessBadge {{ background: #FFF0E3; color: {ORANGE_DARK}; border: 1px solid #FDBA74; border-radius: 8px; padding: 3px 7px; font-size: 8px; font-weight: 800; }}
            QScrollArea#messageScroll {{ border: none; background: {CREAM}; }}
            QWidget#messagesWidget {{ background: {CREAM}; }}
            QFrame#userBubble {{ background: #FFE9D6; border: 1px solid #FBC79F; border-radius: 8px; margin-left: 55px; }}
            QFrame#assistantBubble {{ background: #FFFFFF; border: 1px solid #E8D8CC; border-radius: 8px; margin-right: 45px; }}
            QFrame#activityRow {{ background: transparent; border: none; margin-right: 45px; }}
            QLabel#activityText {{ color: {MUTED}; font-size: 10px; }}
            QLabel#activityIcon_starting, QLabel#activityIcon_session, QLabel#activityIcon_thinking, QLabel#activityIcon_waiting, QLabel#activityIcon_context {{ color: #C86B2C; font-size: 9px; font-weight: 800; }}
            QLabel#activityIcon_tool, QLabel#activityIcon_responding {{ color: {ORANGE_DARK}; font-size: 11px; font-weight: 800; }}
            QLabel#activityIcon_tool_complete, QLabel#activityIcon_complete {{ color: #278347; font-size: 11px; font-weight: 800; }}
            QLabel#activityIcon_cancelled, QLabel#activityIcon_error {{ color: #B42318; font-size: 11px; font-weight: 800; }}
            QLabel#bubbleRole {{ color: {ORANGE_DARK}; font-size: 10px; font-weight: 750; }}
            QLabel#bubbleTime {{ color: #A29186; font-size: 9px; }}
            QLabel#bubbleContent {{ color: {INK}; font-size: 11px; line-height: 1.25; }}
            QFrame#composerPanel {{ background: #FFFDF9; border-top: 1px solid {BORDER}; }}
            QLabel#statusLabel {{ color: {MUTED}; font-size: 9px; }}\n            QLabel#activeModelLabel {{ color: {ORANGE_DARK}; font-size: 8px; font-weight: 800; letter-spacing: 1px; }}
            QTextEdit#promptEdit {{ background: white; color: {INK}; border: 1px solid #DCC8B8; border-radius: 7px; padding: 7px; font-size: 11px; selection-background-color: #FDBA74; }}
            QTextEdit#promptEdit:focus {{ border: 2px solid {ORANGE}; }}
            QPushButton#sendButton {{ background: {ORANGE}; color: white; border: none; border-radius: 7px; font-size: 11px; font-weight: 750; }}
            QPushButton#sendButton:hover {{ background: #FB923C; }}
            QPushButton#sendButton:disabled {{ background: #D7CCC4; color: #8E8178; }}
            QPushButton#stopButton {{ background: white; color: #B42318; border: 1px solid #E4A09A; border-radius: 7px; font-weight: 650; }}
            QPushButton#stopButton:hover {{ background: #FFF0EE; }}
            QLabel#hintLabel {{ color: #9B8B81; font-size: 9px; }}
            QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: #D9B99F; border-radius: 4px; min-height: 24px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QSplitter::handle {{ background: #4B3527; }}
        """

    def _load_conversations(self) -> None:
        try:
            self.conversations = self.store.load()
        except ConversationStoreError as exc:
            self._session_load_error = str(exc)
            self.conversations = []
            error_message = str(exc)
            QTimer.singleShot(
                0,
                lambda message=error_message: QMessageBox.warning(
                    self, "Chat History Error", message
                ),
            )

        if not self.conversations:
            self.conversations.append(AgentConversation.create())
        self._refresh_session_list(select_id=self.conversations[0].id)

    def _save(self) -> None:
        try:
            self.conversations.sort(key=lambda item: item.updated_at, reverse=True)
            self.store.save(self.conversations)
        except ConversationStoreError as exc:
            logger.error("Could not save Agent Chat history", exc_info=True)
            QMessageBox.warning(self, "Chat History Error", str(exc))

    def _refresh_session_list(self, select_id: str | None = None) -> None:
        self.session_list.blockSignals(True)
        self.session_list.clear()
        folder_items: dict[str, QTreeWidgetItem] = {}
        selected_item: QTreeWidgetItem | None = None
        first_thread: QTreeWidgetItem | None = None
        for conversation in self.conversations:
            folder_key = (
                str(Path(conversation.folder).resolve()).casefold()
                if conversation.folder
                else ""
            )
            folder_item = folder_items.get(folder_key)
            if folder_item is None:
                folder_item = QTreeWidgetItem([conversation.folder_name])
                folder_item.setToolTip(0, conversation.folder or "No folder assigned")
                folder_item.setData(0, Qt.ItemDataRole.UserRole, "folder")
                folder_item.setFlags(
                    folder_item.flags() & ~Qt.ItemFlag.ItemIsSelectable
                )
                folder_items[folder_key] = folder_item
                self.session_list.addTopLevelItem(folder_item)

            item = QTreeWidgetItem([conversation.title])
            item.setData(0, Qt.ItemDataRole.UserRole, "thread")
            item.setData(0, Qt.ItemDataRole.UserRole + 1, conversation.id)
            item.setToolTip(0, conversation.title)
            folder_item.addChild(item)
            first_thread = first_thread or item
            if conversation.id == select_id:
                selected_item = item

        self.session_list.expandAll()
        self.session_list.setCurrentItem(selected_item or first_thread)
        self.session_list.blockSignals(False)
        current_item = self.session_list.currentItem()
        if current_item is not None:
            self._select_conversation_by_id(
                current_item.data(0, Qt.ItemDataRole.UserRole + 1)
            )

    def _on_session_selected(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current is not None:
            self._select_conversation_by_id(
                current.data(0, Qt.ItemDataRole.UserRole + 1)
            )

    def _show_thread_context_menu(self, position) -> None:
        item = self.session_list.itemAt(position)
        if item is None or item.data(0, Qt.ItemDataRole.UserRole) != "thread":
            return
        self.session_list.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("Rename thread", self.rename_current)
        menu.addAction("Delete thread", self.delete_current)
        menu.exec(self.session_list.viewport().mapToGlobal(position))

    def _select_conversation_by_id(self, conversation_id: str) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        conversation = next(
            (item for item in self.conversations if item.id == conversation_id),
            None,
        )
        if conversation is None:
            return
        self.current_conversation = conversation
        self.chat_title.setText(conversation.title)
        self._update_folder_display()
        self._select_model(conversation.model)
        self._render_messages()
        self.prompt_edit.setFocus()

    def _update_folder_display(self) -> None:
        conversation = self.current_conversation
        if conversation is None or not conversation.folder:
            self.folder_label.setText("Not assigned")
            self.folder_label.setToolTip("")
            self.folder_button.setText("Choose")
            self.folder_button.setEnabled(True)
            self.prompt_edit.setEnabled(False)
            self.send_button.setEnabled(False)
            self.status_label.setText("Assign a folder before chatting")
            return

        self.folder_label.setText(conversation.folder_name)
        self.folder_label.setToolTip(conversation.folder)
        locked = conversation.sdk_session_started
        self.folder_button.setText("Locked" if locked else "Change")
        self.folder_button.setEnabled(not locked)
        self.prompt_edit.setEnabled(True)
        self.send_button.setEnabled(True)
        self.status_label.setText("Ready - agent actions are scoped to this folder")

    def _render_messages(self) -> None:
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        conversation = self.current_conversation
        if conversation is None or not conversation.messages:
            empty = QLabel(
                "Start with a goal, not just a question.\n\n"
                "Examples:\n"
                "- Explore this codebase and explain its architecture\n"
                "- Fix the failing tests and verify the result\n"
                "- Add a feature, update the docs, and run the test suite"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            empty.setStyleSheet(
                "color: #8A776B; font-size: 13px; padding: 50px; line-height: 1.5;"
            )
            self.messages_layout.insertWidget(0, empty)
            return
        for message in conversation.messages:
            self._add_bubble(message)
        self._scroll_to_bottom()

    def _add_bubble(self, message: AgentMessage) -> MessageBubble:
        model = self.current_conversation.model if self.current_conversation else ""
        bubble = MessageBubble(message, model=model)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        return bubble

    def _add_activity(self, kind: str, text: str) -> ActivityRow:
        row = ActivityRow(kind, text)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, row)
        self._scroll_to_bottom()
        return row

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(
            0,
            lambda: self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            ),
        )

    def new_conversation(self) -> None:
        start = (
            self.current_conversation.folder
            if self.current_conversation
            else str(Path.home())
        )
        folder = QFileDialog.getExistingDirectory(self, "Choose agent folder", start)
        if not folder:
            return
        conversation = AgentConversation.create(folder=folder)
        self.conversations.insert(0, conversation)
        self._save()
        self._refresh_session_list(select_id=conversation.id)

    def choose_folder(self) -> None:
        conversation = self.current_conversation
        if conversation is None or conversation.sdk_session_started:
            return
        start = conversation.folder or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose agent folder", start)
        if not folder:
            return
        conversation.folder = str(Path(folder).resolve())
        conversation.touch()
        self._save()
        self._refresh_session_list(select_id=conversation.id)

    def rename_current(self) -> None:
        conversation = self.current_conversation
        if conversation is None:
            return
        title, accepted = QInputDialog.getText(
            self,
            "Rename Thread",
            "Thread name:",
            text=conversation.title,
        )
        title = title.strip()
        if accepted and title:
            conversation.title = title
            self._save()
            self._refresh_session_list(select_id=conversation.id)

    def delete_current(self) -> None:
        conversation = self.current_conversation
        if conversation is None or self.worker is not None:
            return
        result = QMessageBox.question(
            self,
            "Delete Thread",
            f'Delete the thread "{conversation.title}" and its chat history?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.conversations = [
            item for item in self.conversations if item.id != conversation.id
        ]
        if not self.conversations:
            self.conversations.append(AgentConversation.create())
        self._save()
        self._refresh_session_list(select_id=self.conversations[0].id)

    def _load_models(self) -> None:
        self.status_label.setText("Loading Copilot models...")
        self.models_worker = ModelListWorker(self)
        self.models_worker.models_ready.connect(self._on_models_ready)
        self.models_worker.error_occurred.connect(self._on_models_error)
        self.models_worker.finished.connect(self._models_finished)
        self.models_worker.start()

    def _on_models_ready(self, models: list[dict[str, str]]) -> None:
        selected = (
            self.current_conversation.model if self.current_conversation else "auto"
        )
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for model in models:
            self.model_combo.addItem(model["name"], model["id"])
        self.model_combo.blockSignals(False)
        self._select_model(selected)
        self.status_label.setText("Ready")

    def _on_models_error(self, error: str) -> None:
        self.status_label.setText(f"Could not load model list: {error}")

    def _models_finished(self) -> None:
        if self.models_worker is not None:
            self.models_worker.deleteLater()
            self.models_worker = None

    def _select_model(self, model_id: str) -> None:
        index = self.model_combo.findData(model_id)
        if index < 0:
            self.model_combo.addItem(model_id, model_id)
            index = self.model_combo.count() - 1
        self.model_combo.blockSignals(True)
        self.model_combo.setCurrentIndex(index)
        self.model_combo.blockSignals(False)

    def _on_model_changed(self) -> None:
        conversation = self.current_conversation
        model = self.model_combo.currentData()
        if conversation is None or not model:
            return
        conversation.model = str(model)
        self._save()

    def send_message(self) -> None:
        conversation = self.current_conversation
        prompt = self.prompt_edit.toPlainText().strip()
        if conversation is None or not prompt or self.worker is not None:
            return
        if not conversation.folder or not Path(conversation.folder).is_dir():
            QMessageBox.warning(
                self,
                "Agent Folder Required",
                "Choose an existing folder before sending a message.",
            )
            return

        conversation.model = str(self.model_combo.currentData() or "auto")
        conversation.add_message("user", prompt)
        self.prompt_edit.clear()
        self._save()
        self._refresh_session_list(select_id=conversation.id)
        self._render_messages()

        self.streaming_text = ""
        self.streaming_bubble = None
        self._set_busy(True)

        self.worker = AgentRunWorker(conversation, prompt, self)
        self.worker.session_ready.connect(self._on_session_ready)
        self.worker.token_received.connect(self._on_token)
        self.worker.status_changed.connect(self.status_label.setText)
        self.worker.activity_added.connect(self._on_activity)
        self.worker.response_complete.connect(self._on_response)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.finished.connect(self._worker_finished)
        self.worker.start()
        self._scroll_to_bottom()

    def _on_session_ready(self) -> None:
        if self.current_conversation is not None:
            self.current_conversation.sdk_session_started = True
            self._save()
            self._update_folder_display()

    def _on_token(self, token: str) -> None:
        self.streaming_text += token
        if self.streaming_bubble is None:
            self.streaming_bubble = self._add_bubble(
                AgentMessage(role="assistant", content=self.streaming_text)
            )
        else:
            self.streaming_bubble.set_content(self.streaming_text)
        self._scroll_to_bottom()

    def _on_activity(self, kind: str, text: str) -> None:
        self._add_activity(kind, text)

    def _on_response(self, response: str) -> None:
        conversation = self.current_conversation
        if conversation is None:
            return
        if self.streaming_bubble is None:
            self.streaming_bubble = self._add_bubble(
                AgentMessage(role="assistant", content=response)
            )
        else:
            self.streaming_bubble.set_content(response)
        conversation.add_message("assistant", response)
        self._save()
        self.status_label.setText("Complete")
        self._add_activity("complete", "Completed")
        self._scroll_to_bottom()

    def _on_error(self, error: str) -> None:
        self._add_activity("error", f"Request failed: {error}")
        self.status_label.setText("Agent request failed")
        QMessageBox.warning(self, "Copilot Agent Error", error)

    def _on_cancelled(self) -> None:
        if self.streaming_bubble is not None:
            content = self.streaming_text or "Request stopped."
            self.streaming_bubble.set_content(content)
        self._add_activity("cancelled", "Stopped")
        self.status_label.setText("Stopped")

    def _worker_finished(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()
        self.worker = None
        self.streaming_bubble = None
        self.streaming_text = ""
        self._set_busy(False)
        self._update_folder_display()

    def _set_busy(self, busy: bool) -> None:
        self.stop_button.setEnabled(True)
        self.send_button.setVisible(not busy)
        self.stop_button.setVisible(busy)
        self.prompt_edit.setEnabled(not busy)
        self.session_list.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self.rename_button.setEnabled(not busy)
        self.delete_button.setEnabled(not busy)
        self.folder_button.setEnabled(
            not busy
            and bool(self.current_conversation)
            and not self.current_conversation.sdk_session_started
        )

    def stop_agent(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status_label.setText("Stopping agent...")
            self.stop_button.setEnabled(False)
            self.worker.cancel()

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(5000):
                logger.warning("Agent worker did not stop before window close")
        if self.models_worker is not None and self.models_worker.isRunning():
            self.models_worker.wait(3000)
        event.accept()
