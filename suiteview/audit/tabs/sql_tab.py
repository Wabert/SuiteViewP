"""
SQL tab — displays the generated SQL statement with nice formatting.

Shows the full SQL in a read-only text area with keyword highlighting,
plus a note about the free online SQL formatter link (matching VBA).
"""
from __future__ import annotations

import re
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
)
from PyQt6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor


_FONT_MONO = QFont("Consolas", 10)
_FONT = QFont("Segoe UI", 9)

# SQL keywords to highlight
_SQL_KEYWORDS = (
    r"\b(SELECT|FROM|WHERE|AND|OR|NOT|IN|ON|AS|JOIN|INNER|LEFT|RIGHT|OUTER|"
    r"FULL|CROSS|WITH|CASE|WHEN|THEN|ELSE|END|DISTINCT|GROUP|BY|ORDER|"
    r"HAVING|UNION|ALL|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|SET|VALUES|"
    r"INTO|NULL|IS|LIKE|BETWEEN|EXISTS|FETCH|FIRST|ROWS|ONLY|MAX|MIN|"
    r"COUNT|SUM|AVG|SUBSTR|CURRENT_DATE|CURRENT_TIMESTAMP)\b"
)


class _SqlHighlighter(QSyntaxHighlighter):
    """Simple SQL keyword highlighter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._kw_fmt = QTextCharFormat()
        self._kw_fmt.setForeground(QColor("#0000CC"))
        self._kw_fmt.setFontWeight(QFont.Weight.Bold)

        self._str_fmt = QTextCharFormat()
        self._str_fmt.setForeground(QColor("#A31515"))

        self._num_fmt = QTextCharFormat()
        self._num_fmt.setForeground(QColor("#098658"))

    def highlightBlock(self, text: str):  # noqa: N802
        # Keywords
        for m in re.finditer(_SQL_KEYWORDS, text, re.IGNORECASE):
            self.setFormat(m.start(), m.end() - m.start(), self._kw_fmt)
        # String literals
        for m in re.finditer(r"'[^']*'", text):
            self.setFormat(m.start(), m.end() - m.start(), self._str_fmt)
        # Numbers
        for m in re.finditer(r"\b\d+\b", text):
            self.setFormat(m.start(), m.end() - m.start(), self._num_fmt)


def _format_sql(raw: str) -> str:
    """Apply basic formatting to a raw SQL string for readability."""
    # Split on real newlines first to preserve intentional blank lines
    raw_lines = raw.split("\n")
    # Track which raw lines are blank (intentional separators)
    blank_indices = set()
    rebuilt = []
    for i, line in enumerate(raw_lines):
        stripped = line.strip()
        if not stripped:
            blank_indices.add(len(rebuilt))
            rebuilt.append("\n")  # placeholder
        else:
            rebuilt.append(stripped)

    # Rejoin non-blank parts and normalise whitespace within them
    sql = " ".join(part for part in rebuilt if part != "\n")

    # Insert newlines before major keywords
    for kw in ("SELECT", "FROM", "WHERE", "AND", "OR", "INNER JOIN",
               "LEFT JOIN", "LEFT OUTER JOIN", "RIGHT JOIN",
               "ORDER BY", "GROUP BY", "HAVING", "UNION",
               "FETCH FIRST", "WITH"):
        sql = re.sub(rf"(?i)\s+({kw})\b", rf"\n\1", sql)

    # Indent continuation lines
    lines = sql.split("\n")
    formatted = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"(?i)^(WITH|SELECT|FROM|WHERE|GROUP BY|ORDER BY|HAVING|UNION|FETCH)", stripped):
            formatted.append(stripped)
        elif re.match(r"(?i)^(AND|OR)\b", stripped):
            formatted.append("  " + stripped)
        elif re.match(r"(?i)^(INNER|LEFT|RIGHT|FULL|CROSS)\b", stripped):
            formatted.append("  " + stripped)
        else:
            formatted.append("    " + stripped)

    # Re-insert blank lines at the positions they appeared in the raw input
    # We do this by finding which formatted line corresponds to the SELECT
    # after CTEs and inserting a blank line before it when the raw had one.
    result = "\n".join(formatted)

    # If original had blank lines, insert them before SELECT DISTINCT
    # (the main query after CTEs)
    if blank_indices:
        result = re.sub(r"\n(SELECT DISTINCT)", r"\n\n\1", result, count=1)

    return result


class SqlTab(QWidget):
    """SQL tab — shows the formatted SQL statement."""

    # Emitted when user clicks "Move to Build" with current SQL text
    move_to_build = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # SQL text area
        self.txt_sql = QTextEdit()
        self.txt_sql.setFont(_FONT_MONO)
        self.txt_sql.setReadOnly(True)
        self.txt_sql.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.txt_sql.setStyleSheet(
            "QTextEdit { background-color: #FFFFF8; border: 1px solid #999;"
            " padding: 6px; }"
        )
        self._highlighter = _SqlHighlighter(self.txt_sql.document())
        root.addWidget(self.txt_sql, 1)

        # Footer row: link on the left, button on the right
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)

        foot = QLabel(
            'For a better format, copy the text above and click on this link '
            'to a free online sql parser:  '
            '<a href="https://www.freeformatter.com/sql-formatter.html">'
            'https://www.freeformatter.com/sql-formatter.html</a>'
        )
        foot.setFont(_FONT)
        foot.setOpenExternalLinks(True)
        foot.setStyleSheet("color: #333; padding: 4px;")
        footer_row.addWidget(foot, 1)

        self.btn_move_to_build = QPushButton("Move to Build")
        self.btn_move_to_build.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_move_to_build.setFixedSize(120, 30)
        self.btn_move_to_build.setStyleSheet(
            "QPushButton { background-color: #1E5BA8; color: white;"
            " border: 1px solid #164888; border-radius: 3px; }"
            "QPushButton:hover { background-color: #2970C4; }"
        )
        self.btn_move_to_build.clicked.connect(self._on_move_to_build)
        footer_row.addWidget(self.btn_move_to_build)

        root.addLayout(footer_row)

    def set_sql(self, raw_sql: str):
        """Format and display the SQL statement."""
        self.txt_sql.setPlainText(_format_sql(raw_sql))

    def _on_move_to_build(self):
        """Emit the current SQL text for the Build SQL tab."""
        sql = self.txt_sql.toPlainText()
        if sql.strip():
            self.move_to_build.emit(sql)
