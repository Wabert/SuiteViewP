"""Compact regular-expression reference for the Query tool."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from suiteview.polview.ui.widgets import StyledInfoTableGroup
from suiteview.ui.widgets.frameless_window import FramelessWindowBase


REGEX_SECTIONS = (
    ("Expressions", (
        ("^", "Start of string"),
        ("$", "End of string"),
        (".", "Any character"),
        ("*", "0 or more"),
        ("+", "1 or more"),
        ("?", "0 or 1"),
        ("{n}", "Exactly n times"),
        ("{n,m}", "Between n and m times"),
        ("|", "OR"),
        ("()", "Grouping"),
        ("[abc]", "Character set"),
        ("[^abc]", "NOT character set"),
    )),
    ("Character classes", (
        (r"\d", "Any digit (0-9)"),
        (r"\D", "Any non-digit"),
        (r"\w", "Letter, number, or underscore"),
        (r"\W", "Not a letter, number, or underscore"),
        (r"\s", "Whitespace"),
        (r"\S", "Non-whitespace"),
    )),
    ("Useful patterns", (
        ("^[0-9]+$", "Numbers only"),
        ("^[A-Za-z]+$", "Letters only"),
        ("^[A-Za-z0-9]+$", "Letters and numbers only"),
        ("^[^#]*$", "Does NOT contain #"),
        (".*#.*", "Contains #"),
        ("^[^ ]+$", "No spaces"),
        ("^.{0,10}$", "Up to 10 characters"),
        ("^.{5,}$", "At least 5 characters"),
    )),
)


class RegexCheatsheetWindow(FramelessWindowBase):
    """Owned, non-modal reference that stays available while entering criteria."""

    def __init__(self, parent=None):
        super().__init__(
            title="RegEx Cheatsheet",
            default_size=(475, 570),
            min_size=(475, 570),
            parent=parent,
        )
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("RegEx Cheatsheet")

    def build_content(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(6, 4, 6, 18)
        layout.setSpacing(3)
        for title, entries in REGEX_SECTIONS:
            group = StyledInfoTableGroup(title, show_table=False)
            group.setStyleSheet(
                group.styleSheet()
                + "QGroupBox { border-color: #1E5BA8; }"
                + "QGroupBox::title { background-color: #1E5BA8; }"
            )
            group._info_layout.setVerticalSpacing(0)
            for index, (expression, meaning) in enumerate(entries):
                key = f"entry_{index}"
                group.add_field(expression, key, label_width=150, value_width=275)
                group.set_value(key, meaning)
                label = group._labels[key]
                label.setText(expression)
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setStyleSheet(
                    "font: 11px 'Consolas'; color: #0D3A7A;"
                    "background: transparent; border: none;"
                )
                label.setFixedHeight(16)
                value = group._fields[key]
                value.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                value.setFixedHeight(16)
            layout.addWidget(group)
        note = QLabel("RegEx syntax, not SQL LIKE. Dot excludes newlines by default.")
        note.setStyleSheet("font-size: 10px; color: #666;")
        layout.addWidget(note)
        return body
