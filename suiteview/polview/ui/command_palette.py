"""PolView command box — a VS Code-style command palette in the title bar.

Type to filter every available action (with its shortcut), then Enter or
click to run it. Commands live here rather than in the policy-number box, so
policy lookups are never mistaken for commands. The window supplies the
commands; availability is re-checked each time the list opens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from PyQt6.QtCore import QModelIndex, QSize, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QCompleter, QLineEdit, QListView, QStyledItemDelegate

COMMAND_ROLE = Qt.ItemDataRole.UserRole + 1


@dataclass(frozen=True)
class Command:
    key: str
    title: str
    handler: Callable[[], None]
    shortcut: str = ""
    category: str = ""
    keywords: str = ""
    available: Callable[[], bool] = field(default=lambda: True)

    @property
    def label(self) -> str:
        prefix = f"{self.category}: " if self.category else ""
        return f"{prefix}{self.title}"

    def matches(self, text: str) -> bool:
        haystack = f"{self.label} {self.keywords} {self.shortcut}".lower()
        return all(word in haystack for word in text.lower().split())


_BOX_STYLE = """
    QLineEdit {
        background: rgba(0, 0, 0, 70);
        border: 1px solid rgba(212, 160, 23, 160);
        border-radius: 4px;
        color: #FFFFFF;
        font-size: 11px;
        padding: 2px 8px;
        min-height: 20px; max-height: 20px;
        selection-background-color: #D4A017;
    }
    QLineEdit:focus {
        background: #FFFFFF;
        color: #0A3D0A;
        border: 1px solid #D4A017;
    }
"""

_POPUP_STYLE = """
    QListView {
        background: #FFFFFF; color: #1A202C; font-size: 11px;
        border: 1px solid #D4A017; outline: none;
    }
    QListView::item { padding: 1px 6px; }
    QListView::item:selected { background: #FFF3D0; color: #0A3D0A; }
"""

SHORTCUT_ROLE = Qt.ItemDataRole.UserRole + 2


class _CommandDelegate(QStyledItemDelegate):
    """Command label on the left, its shortcut right-aligned in grey."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        shortcut = index.data(SHORTCUT_ROLE)
        if shortcut:
            painter.save()
            painter.setPen(QColor("#718096"))
            painter.drawText(option.rect.adjusted(0, 0, -8, 0),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, shortcut)
            painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), 20)


class CommandPaletteBox(QLineEdit):
    """Search-and-run box for window commands (Ctrl+Shift+P)."""

    command_run = pyqtSignal(str)

    def __init__(self, commands_provider: Callable[[], Iterable[Command]], parent=None):
        super().__init__(parent)
        self._provider = commands_provider
        self._commands: dict[str, Command] = {}
        self.setPlaceholderText("🔍  Search commands & help…   Ctrl+Shift+P")
        self.setToolTip("Every PolView action in one place. Type to filter, Enter to run.")
        self.setStyleSheet(_BOX_STYLE)
        self.setFixedWidth(300)
        self.setClearButtonEnabled(True)
        # Click (or Ctrl+Shift+P) to use; never grab focus at startup or via Tab.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        palette = self.palette()
        palette.setColor(palette.ColorRole.PlaceholderText, QColor("#A0AEC0"))
        self.setPalette(palette)

        self._model = QStandardItemModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self._completer.setMaxVisibleItems(16)
        self._completer.setWidget(self)
        popup = QListView()
        popup.setUniformItemSizes(True)
        popup.setStyleSheet(_POPUP_STYLE)
        popup.setMinimumWidth(420)
        self._completer.setPopup(popup)
        # setPopup installs Qt's own delegate, so ours must come after it.
        self._delegate = _CommandDelegate(popup)
        popup.setItemDelegate(self._delegate)
        self._completer.activated[QModelIndex].connect(self._on_activated)
        self.textEdited.connect(self._refresh)
        self.returnPressed.connect(self._run_best_match)

    # -- behaviour -------------------------------------------------------------

    def open_palette(self):
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.selectAll()
        self._refresh(self.text())

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self._refresh_if_focused)

    @pyqtSlot()
    def _refresh_if_focused(self):
        if self.hasFocus():
            self._refresh(self.text())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._completer.popup().hide()
            self.clear()
            self.clearFocus()
            return
        super().keyPressEvent(event)

    @pyqtSlot(str)
    def _refresh(self, text: str = ""):
        self._commands = {}
        self._model.clear()
        for command in self._provider():
            try:
                if not command.available():
                    continue
            except Exception:
                continue
            if text and not command.matches(text):
                continue
            item = QStandardItem(command.label)
            item.setData(command.key, COMMAND_ROLE)
            item.setData(command.shortcut, SHORTCUT_ROLE)
            item.setEditable(False)
            self._model.appendRow(item)
            self._commands[command.key] = command
        if self._model.rowCount():
            self._completer.complete(self.rect())
            popup = self._completer.popup()
            popup.setCurrentIndex(self._model.index(0, 0))
        else:
            self._completer.popup().hide()

    def visible_command_keys(self) -> list[str]:
        return [self._model.item(r).data(COMMAND_ROLE) for r in range(self._model.rowCount())]

    @pyqtSlot(QModelIndex)
    def _on_activated(self, index):
        key = index.data(COMMAND_ROLE)
        if key:
            self.run(key)

    @pyqtSlot()
    def _run_best_match(self):
        popup = self._completer.popup()
        index = popup.currentIndex() if popup.isVisible() else None
        if index is not None and index.isValid():
            key = index.data(COMMAND_ROLE)
        elif self._model.rowCount():
            key = self._model.item(0).data(COMMAND_ROLE)
        else:
            return
        self.run(key)

    def run(self, key: str):
        command = self._commands.get(key) or next(
            (c for c in self._provider() if c.key == key), None)
        if command is None:
            return
        self._completer.popup().hide()
        self.clear()
        self.clearFocus()
        # Defer so the popup closes before a dialog or reload starts.
        QTimer.singleShot(0, command.handler)
        self.command_run.emit(key)
