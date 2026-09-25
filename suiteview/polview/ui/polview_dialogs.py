"""Small PolView companion dialogs: policy notes, shortcut help, field finder.

All use the shared ``FramelessDialog`` chrome in PolView's green/gold theme and
are shown non-modally so the user can keep working in the policy.
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QWidget,
)

from suiteview.ui.widgets.frameless_window import FramelessDialog

from ..services.policy_notes import PolicyNotesStore
from .styles import (
    GOLD_LIGHT, GOLD_PRIMARY, GRAY_DARK, GRAY_TEXT, GREEN_DARK, GREEN_PRIMARY,
    GREEN_SUBTLE, POLVIEW_BORDER_COLOR, POLVIEW_HEADER_COLORS,
)

_BUTTON_STYLE = f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {GREEN_PRIMARY}, stop:1 {GREEN_DARK});
        color: #FFFFFF; border: 1px solid {GREEN_DARK}; border-radius: 4px;
        font-size: 11px; font-weight: bold; padding: 3px 12px;
    }}
    QPushButton:hover {{ color: #FFD54F; }}
    QPushButton:disabled {{ background: #E1E5EB; color: #9AA5B1; border-color: #CBD5E0; }}
"""
_LIST_STYLE = f"""
    QListWidget {{ border: 1px solid {GREEN_PRIMARY}; border-radius: 4px; font-size: 11px; }}
    QListWidget::item {{ padding: 2px 4px; border-bottom: 1px solid #EEF1F4; }}
    QListWidget::item:selected {{ background: {GOLD_LIGHT}; color: {GREEN_DARK}; }}
"""
_EDIT_STYLE = f"""
    QLineEdit, QPlainTextEdit {{
        border: 1px solid #CBD5E0; border-radius: 4px; font-size: 11px; padding: 3px;
        background: #FFFFFF; color: {GRAY_DARK};
    }}
    QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {GOLD_PRIMARY}; }}
"""


def _dialog(title: str, parent) -> FramelessDialog:
    dialog = FramelessDialog(title, parent, header_colors=POLVIEW_HEADER_COLORS,
                             border_color=POLVIEW_BORDER_COLOR)
    dialog.setModal(False)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    return dialog


# =============================================================================
# Policy notes
# =============================================================================

class PolicyNotesDialog(FramelessDialog):
    """Timestamped private notes for one policy, stored in the local profile."""

    notes_changed = pyqtSignal(int)

    def __init__(self, company_code: str, policy_number: str, parent=None,
                 store: Optional[PolicyNotesStore] = None):
        super().__init__(f"Notes · {company_code} - {policy_number}", parent,
                         header_colors=POLVIEW_HEADER_COLORS, border_color=POLVIEW_BORDER_COLOR)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._company = company_code
        self._policy = policy_number
        self._store = store or PolicyNotesStore()
        self.resize(460, 420)

        hint = QLabel("Private to you — saved in your SuiteView profile, never in CyberLife.")
        hint.setStyleSheet(f"color: {GRAY_TEXT}; font-size: 10px; font-style: italic;")
        self.body_layout.addWidget(hint)
        self.list = QListWidget()
        self.list.setStyleSheet(_LIST_STYLE)
        self.list.setWordWrap(True)
        self.body_layout.addWidget(self.list, 1)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("Type a note… (Ctrl+Enter to add)")
        self.editor.setStyleSheet(_EDIT_STYLE)
        self.editor.setFixedHeight(80)
        self.body_layout.addWidget(self.editor)
        row = QHBoxLayout()
        self.delete_button = QPushButton("Delete selected")
        self.delete_button.setStyleSheet(_BUTTON_STYLE)
        self.delete_button.clicked.connect(self._delete)
        row.addWidget(self.delete_button)
        row.addStretch(1)
        self.add_button = QPushButton("Add note")
        self.add_button.setStyleSheet(_BUTTON_STYLE)
        self.add_button.clicked.connect(self._add)
        row.addWidget(self.add_button)
        self.body_layout.addLayout(row)
        from PyQt6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence("Ctrl+Return"), self.editor, activated=self._add)
        self._reload()

    def _reload(self):
        self.list.clear()
        notes = self._store.notes(self._company, self._policy)
        for note in notes:
            item = QListWidgetItem(f"{note.created}\n{note.text}")
            self.list.addItem(item)
        if not notes:
            empty = QListWidgetItem("No notes yet for this policy.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
        self.delete_button.setEnabled(bool(notes))
        self.notes_changed.emit(len(notes))

    @pyqtSlot()
    def _add(self):
        text = self.editor.toPlainText().strip()
        if not text:
            return
        self._store.add(self._company, self._policy, text)
        self.editor.clear()
        self._reload()

    @pyqtSlot()
    def _delete(self):
        row = self.list.currentRow()
        if row < 0 or row >= self._store.count(self._company, self._policy):
            return
        self._store.delete(self._company, self._policy, row)
        self._reload()


# =============================================================================
# Shortcut & command help
# =============================================================================

SHORTCUTS = (
    ("Ctrl+Shift+P", "Command box — search and run any PolView action"),
    ("Ctrl+L", "Jump to the policy number box"),
    ("Enter", "Get the typed policy"),
    ("Ctrl+1 … Ctrl+9", "Switch to tab 1–9"),
    ("Ctrl+Tab / Ctrl+Shift+Tab", "Next / previous tab"),
    ("Alt+← / Alt+→", "Back / forward through viewed policies"),
    ("F5", "Reload the current policy fresh from DB2"),
    ("Ctrl+F", "Find a field anywhere in PolView"),
    ("Ctrl+Shift+C", "Copy the policy summary"),
    ("Ctrl+N", "Open your notes for this policy"),
    ("Ctrl+D", "Timeline of every key policy date"),
    ("Ctrl+T", "Show / hide the Tables & Rates panel"),
    ("F1", "This help"),
    ("", ""),
    ("Paste", "“CKPR - 01 - U0613620”, “01_13034048” or a TCH_POL_ID fills every field"),
    ("Type a name", "Recent policies match by number or insured name"),
    ("Tables", "Select cells to see Σ / Avg / Min / Max; right-click a header to hide columns"),
    ("Double-click", "A coverage or benefit row shows every field, interpreted and raw"),
    ("Right-click", "A sourced value (hover shows “Source:”) jumps to its DB2 rows"),
)


def shortcut_help_html() -> str:
    rows = []
    for key, text in SHORTCUTS:
        if not key and not text:
            rows.append('<tr><td colspan="2" style="padding:2px;"></td></tr>')
            continue
        rows.append(
            f'<tr><td style="padding:1px 12px 1px 0; color:{GREEN_DARK};"><b>{key}</b></td>'
            f'<td style="padding:1px 0; color:{GRAY_DARK};">{text}</td></tr>'
        )
    return '<table cellspacing="0">' + "".join(rows) + "</table>"


def show_message_dialog(parent, title: str, html: str, width: int = 480) -> FramelessDialog:
    dialog = _dialog(title, parent)
    label = QLabel(html)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setWordWrap(True)
    label.setStyleSheet("font-size: 11px; background: transparent;")
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    dialog.body_layout.addWidget(label)
    close = QPushButton("Close")
    close.setStyleSheet(_BUTTON_STYLE)
    close.clicked.connect(dialog.accept)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(close)
    dialog.body_layout.addLayout(row)
    dialog.resize(width, dialog.sizeHint().height())
    dialog.show()
    return dialog


# =============================================================================
# Field finder
# =============================================================================

class FieldFinderDialog(FramelessDialog):
    """Search every PolView field label and table column; jump to the match.

    *entries_provider* returns ``[(tab_index, tab_title, group, label, value, widget)]``.
    *jump* is called with the chosen entry.
    """

    def __init__(self, entries_provider: Callable[[], list], jump: Callable[[tuple], None],
                 parent=None):
        super().__init__("Find a field", parent, header_colors=POLVIEW_HEADER_COLORS,
                         border_color=POLVIEW_BORDER_COLOR)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._entries = entries_provider()
        self._jump = jump
        self.resize(560, 420)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type part of a field name, e.g. “paid to”, “MTP”, “loan”…")
        self.search.setStyleSheet(_EDIT_STYLE)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._choose_current)
        self.body_layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setStyleSheet(_LIST_STYLE)
        self.list.itemActivated.connect(self._choose)
        self.body_layout.addWidget(self.list, 1)
        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {GRAY_TEXT}; font-size: 10px;")
        self.body_layout.addWidget(self.count_label)
        self._filter("")
        self.search.setFocus()

    @staticmethod
    def _matches(entry, words) -> bool:
        haystack = f"{entry[1]} {entry[2]} {entry[3]} {entry[4]}".lower()
        return all(word in haystack for word in words)

    @pyqtSlot(str)
    def _filter(self, text: str):
        words = [w for w in text.lower().split() if w]
        self.list.clear()
        shown = 0
        for entry in self._entries:
            if words and not self._matches(entry, words):
                continue
            value = f"  =  {entry[4]}" if entry[4] else ""
            item = QListWidgetItem(f"{entry[3]}{value}      ·  {entry[1]} › {entry[2]}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list.addItem(item)
            shown += 1
            if shown >= 300:
                break
        if self.list.count():
            self.list.setCurrentRow(0)
        self.count_label.setText(f"{shown} match{'es' if shown != 1 else ''} · Enter to jump")

    @pyqtSlot()
    def _choose_current(self):
        item = self.list.currentItem()
        if item is not None:
            self._choose(item)

    @pyqtSlot(QListWidgetItem)
    def _choose(self, item: QListWidgetItem):
        entry = item.data(Qt.ItemDataRole.UserRole)
        if entry:
            self._jump(entry)


def flash_widget(widget: QWidget, times: int = 3):
    """Briefly highlight a widget so the eye finds it after a jump."""
    if widget is None:
        return
    original = widget.styleSheet()
    highlight = original + f" background: {GOLD_PRIMARY}; color: #FFFFFF; border-radius: 3px;"
    steps = []
    for _ in range(times):
        steps += [highlight, original]

    def step(index=0):
        try:
            widget.setStyleSheet(steps[index])
        except RuntimeError:
            return
        if index + 1 < len(steps):
            QTimer.singleShot(220, lambda: step(index + 1))

    step()


# =============================================================================
# Record card (coverage / benefit detail)
# =============================================================================

def _display(value) -> str:
    from datetime import date as _date
    from decimal import Decimal as _Decimal

    if value is None:
        return ""
    if isinstance(value, _date):
        return f"{value.month}/{value.day:02d}/{value.year}"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (_Decimal, float)):
        return f"{value:,.6f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value):,}"
    return str(value).strip()


def record_card_rows(record) -> list[tuple[str, str, str]]:
    """(section, field, value) rows: interpreted dataclass fields, then raw DB2 columns."""
    from dataclasses import fields, is_dataclass

    rows = []
    if is_dataclass(record):
        for item in fields(record):
            if item.name != "raw_data":
                rows.append(("Interpreted", item.name, _display(getattr(record, item.name))))
    for column, value in sorted((getattr(record, "raw_data", None) or {}).items()):
        rows.append(("DB2 column", column, _display(value)))
    return rows


class RecordCardDialog(FramelessDialog):
    """Every field of one coverage/benefit — interpreted values and the raw row."""

    def __init__(self, title: str, record, parent=None):
        from .widgets import FixedHeaderTableWidget

        super().__init__(title, parent, header_colors=POLVIEW_HEADER_COLORS,
                         border_color=POLVIEW_BORDER_COLOR)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(520, 620)
        hint = QLabel("Click a header to filter · select cells to total · right-click to copy or export")
        hint.setStyleSheet(f"color: {GRAY_TEXT}; font-size: 10px; font-style: italic;")
        self.body_layout.addWidget(hint)
        self.table = FixedHeaderTableWidget(filterable=True)
        rows = record_card_rows(record)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Section", "Field", "Value"])
        self.table.align_headers_left({"Section", "Field", "Value"})
        self.table.setRowCount(len(rows))
        left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        from PyQt6.QtWidgets import QTableWidgetItem
        for row, values in enumerate(rows):
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value), alignment=left)
        self.table.autoFitAllColumns()
        self.body_layout.addWidget(self.table, 1)


# =============================================================================
# Timeline
# =============================================================================

class TimelineDialog(FramelessDialog):
    """Key policy dates in order, with a TODAY marker and relative times."""

    def __init__(self, title: str, events, today, parent=None):
        from PyQt6.QtGui import QColor, QFont
        from PyQt6.QtWidgets import QTableWidgetItem
        from ..services.policy_timeline import relative_text
        from .widgets import FixedHeaderTableWidget

        super().__init__(title, parent, header_colors=POLVIEW_HEADER_COLORS,
                         border_color=POLVIEW_BORDER_COLOR)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.resize(720, 560)
        self.table = FixedHeaderTableWidget(filterable=True)
        headers = ["Date", "When", "Event", "Category", "Source"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.align_headers_left({"When", "Event", "Category", "Source"})
        self.table.set_empty_message("No dated events are available yet.")
        rows = []
        marker_done = False
        for event in events:
            if not marker_done and event.when >= today:
                rows.append(None)
                marker_done = True
            rows.append(event)
        if not marker_done:
            rows.append(None)
        self.table.setRowCount(len(rows))
        left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        past = QColor("#8A94A6")
        for row, event in enumerate(rows):
            if event is None:
                values = (f"{today.month}/{today.day:02d}/{today.year}", "── today ──", "", "", "")
            else:
                d = event.when
                values = (f"{d.month}/{d.day:02d}/{d.year}", relative_text(d, today),
                          event.label, event.category, event.source)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if event is None:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(QColor(GOLD_LIGHT))
                elif event.when < today:
                    item.setForeground(past)
                self.table.setItem(row, col, item, alignment=None if col == 0 else left)
        self.table.autoFitAllColumns()
        self.body_layout.addWidget(self.table, 1)
        self.today_row = rows.index(None)
