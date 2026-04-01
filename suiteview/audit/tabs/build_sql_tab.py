"""
Build SQL tab — editable SQL workspace for user-modified queries.

Receives SQL from the SQL tab via "Move to Build", allows editing,
and provides a "Run this SQL" button to execute the query.
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

# SQL keywords to highlight (same set as sql_tab)
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
        for m in re.finditer(_SQL_KEYWORDS, text, re.IGNORECASE):
            self.setFormat(m.start(), m.end() - m.start(), self._kw_fmt)
        for m in re.finditer(r"'[^']*'", text):
            self.setFormat(m.start(), m.end() - m.start(), self._str_fmt)
        for m in re.finditer(r"\b\d+\b", text):
            self.setFormat(m.start(), m.end() - m.start(), self._num_fmt)


class BuildSqlTab(QWidget):
    """Build SQL tab — editable SQL with Run button."""

    # Emitted when user clicks "Run this SQL" with the SQL text
    run_sql_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Editable SQL text area
        self.txt_sql = QTextEdit()
        self.txt_sql.setFont(_FONT_MONO)
        self.txt_sql.setReadOnly(False)
        self.txt_sql.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.txt_sql.setStyleSheet(
            "QTextEdit { background-color: #FFFFF8; border: 1px solid #999;"
            " padding: 6px; }"
        )
        self._highlighter = _SqlHighlighter(self.txt_sql.document())
        root.addWidget(self.txt_sql, 1)

        # Footer row with Run button on the right
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)

        hint = QLabel("Edit the SQL above, then click Run this SQL to execute.")
        hint.setFont(_FONT)
        hint.setStyleSheet("color: #333; padding: 4px;")
        footer_row.addWidget(hint, 1)

        self.btn_run_sql = QPushButton("Run this SQL")
        self.btn_run_sql.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_run_sql.setFixedSize(120, 30)
        self.btn_run_sql.setStyleSheet(
            "QPushButton { background-color: #1B7A2B; color: white;"
            " border: 1px solid #156122; border-radius: 3px; }"
            "QPushButton:hover { background-color: #239634; }"
        )
        self.btn_run_sql.clicked.connect(self._on_run_sql)
        footer_row.addWidget(self.btn_run_sql)

        root.addLayout(footer_row)

    def set_sql(self, sql: str):
        """Load SQL text into the editor."""
        self.txt_sql.setPlainText(sql)

    def _on_run_sql(self):
        """Emit the current SQL text for execution."""
        sql = self.txt_sql.toPlainText()
        if sql.strip():
            self.run_sql_requested.emit(sql)
