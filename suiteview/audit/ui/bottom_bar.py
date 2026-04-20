"""
AuditBottomBar — reusable bottom bar with All/MaxCount, timing labels,
and Run button.  Used by Cyberlife, Dynamic Query, and DataForge groups.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QLineEdit,
)

_FONT_SM = QFont("Segoe UI", 8)


class AuditBottomBar(QWidget):
    """Common bottom bar: [left…] stretch [All/MaxCount/ResultCount] [timing] [actions…] [Run]."""

    def __init__(
        self,
        bg_color: str,
        run_label: str = "Run\nAudit",
        run_style: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setFixedHeight(50)
        self.setStyleSheet(f"QWidget {{ background-color: {bg_color}; }}")

        layout = QHBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(4, 2, 4, 2)

        # Left zone — caller adds widgets here
        self.left_layout = QHBoxLayout()
        self.left_layout.setSpacing(4)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.left_layout)

        layout.addStretch()

        # ── All / Max Count / Result Count ──────────────────────
        count_stack = QVBoxLayout()
        count_stack.setSpacing(2)
        count_stack.setContentsMargins(0, 0, 0, 0)

        mc_row = QHBoxLayout()
        mc_row.setSpacing(3)
        mc_row.setContentsMargins(0, 0, 0, 0)

        self.btn_all = QPushButton("All")
        self.btn_all.setFont(_FONT_SM)
        self.btn_all.setFixedSize(28, 18)
        self.btn_all.clicked.connect(lambda: self.txt_max_count.setText(""))
        mc_row.addWidget(self.btn_all)

        self.txt_max_count = QLineEdit("25")
        self.txt_max_count.setFont(_FONT_SM)
        self.txt_max_count.setFixedSize(36, 18)
        self.txt_max_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mc_row.addWidget(self.txt_max_count)

        lbl_mc = QLabel("Max Count")
        lbl_mc.setFont(_FONT_SM)
        mc_row.addWidget(lbl_mc)
        count_stack.addLayout(mc_row)

        self.lbl_result_count = QLabel("Result count:")
        self.lbl_result_count.setFont(_FONT_SM)
        count_stack.addWidget(self.lbl_result_count)

        layout.addLayout(count_stack)
        layout.addSpacing(12)

        # ── Timing labels ───────────────────────────────────────
        time_stack = QVBoxLayout()
        time_stack.setSpacing(0)
        time_stack.setContentsMargins(0, 0, 0, 0)

        self.lbl_query_time = QLabel("Query time:")
        self.lbl_print_time = QLabel("Print time:")
        self.lbl_total_time = QLabel("Total time:")
        for lbl in (self.lbl_query_time, self.lbl_print_time, self.lbl_total_time):
            lbl.setFont(_FONT_SM)
            time_stack.addWidget(lbl)

        layout.addLayout(time_stack)
        layout.addSpacing(12)

        # Action zone — caller adds Save/Delete/etc. here
        self.action_layout = QHBoxLayout()
        self.action_layout.setSpacing(4)
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.action_layout)

        # ── Run button ──────────────────────────────────────────
        _default_run_style = (
            "QPushButton { background-color: #C00000; color: white;"
            " border: 1px solid #900; border-radius: 3px; }"
            "QPushButton:hover { background-color: #E00000; }"
        )
        self.btn_run = QPushButton(run_label)
        self.btn_run.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_run.setFixedSize(60, 36)
        self.btn_run.setStyleSheet(run_style or _default_run_style)
        layout.addWidget(self.btn_run)

    def reset_timing(self):
        """Clear all timing/result labels to defaults."""
        self.lbl_query_time.setText("Query time:")
        self.lbl_print_time.setText("Print time:")
        self.lbl_total_time.setText("Total time:")
        self.lbl_result_count.setText("Result count:")
