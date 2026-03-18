"""
Audit Window — main container with VBA-faithful tab strip and bottom bar.

Tabs: Policy | Policy (2) | Coverages | ADV | WL | DI | Benefits |
      Transaction | Results | Display | SQL

Bottom bar: Region combo, System Code combo, query/print/total time,
            All button, Max Count field, Result count label, Run Audit button.
"""
from __future__ import annotations

import logging
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QSizePolicy, QFrame,
)

from suiteview.core.db2_constants import DEFAULT_REGION
from .constants import REGION_ITEMS, SYSTEM_CODE_ITEMS
from .tabs.policy_tab import PolicyTab

logger = logging.getLogger(__name__)

_FONT = QFont("Segoe UI", 9)


class AuditWindow(QWidget):
    """Top-level audit window, replicating VBA frmAudit layout."""

    def __init__(self, region: str = DEFAULT_REGION, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Audit")
        self.resize(1050, 500)
        self._region = region
        self._build_ui()
        self._apply_initial_state()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        # ── Tab widget ──────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setFont(_FONT)
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #999; }"
            "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt; }"
            "QTabBar::tab:selected { font-weight: bold; }"
        )

        # Policy tab (fully built)
        self.policy_tab = PolicyTab()
        self.tabs.addTab(self.policy_tab, "Policy")

        # Placeholder tabs (will be built tab-by-tab later)
        for name in ["Policy (2)", "Coverages", "ADV", "WL", "DI",
                      "Benefits", "Transaction", "Results",
                      "Display", "SQL"]:
            placeholder = QWidget()
            lbl = QLabel(f"  {name} — (coming soon)")
            lbl.setFont(_FONT)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay = QVBoxLayout(placeholder)
            lay.addWidget(lbl)
            self.tabs.addTab(placeholder, name)

        root.addWidget(self.tabs, 1)  # stretch=1 so tabs fill

        # ── Bottom bar ──────────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.setContentsMargins(4, 2, 4, 2)

        # Region
        lbl_region = QLabel("Region")
        lbl_region.setFont(_FONT)
        self.cmb_region = QComboBox()
        self.cmb_region.setFont(_FONT)
        self.cmb_region.addItems(REGION_ITEMS)
        self.cmb_region.setFixedHeight(20)
        self.cmb_region.setFixedWidth(70)
        bottom.addWidget(lbl_region)
        bottom.addWidget(self.cmb_region)

        # System Code
        lbl_sys = QLabel("System Code:")
        lbl_sys.setFont(_FONT)
        self.cmb_system = QComboBox()
        self.cmb_system.setFont(_FONT)
        self.cmb_system.addItems(SYSTEM_CODE_ITEMS)
        self.cmb_system.setFixedHeight(20)
        self.cmb_system.setFixedWidth(45)
        bottom.addWidget(lbl_sys)
        bottom.addWidget(self.cmb_system)

        bottom.addStretch()

        # Timing labels
        time_grid = QVBoxLayout()
        time_grid.setSpacing(0)
        self.lbl_query_time = QLabel("Query time:")
        self.lbl_print_time = QLabel("Print time:")
        self.lbl_total_time = QLabel("Total time:")
        for lbl in (self.lbl_query_time, self.lbl_print_time, self.lbl_total_time):
            lbl.setFont(_FONT)
            time_grid.addWidget(lbl)
        bottom.addLayout(time_grid)

        bottom.addSpacing(12)

        # All button + Max Count
        self.btn_all = QPushButton("All")
        self.btn_all.setFont(_FONT)
        self.btn_all.setFixedSize(36, 22)
        bottom.addWidget(self.btn_all)

        self.txt_max_count = QLineEdit("25")
        self.txt_max_count.setFont(_FONT)
        self.txt_max_count.setFixedSize(40, 20)
        self.txt_max_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom.addWidget(self.txt_max_count)

        lbl_mc = QLabel("Max Count")
        lbl_mc.setFont(_FONT)
        bottom.addWidget(lbl_mc)

        bottom.addStretch()

        # Result count
        self.lbl_result_count = QLabel("Result count:")
        self.lbl_result_count.setFont(_FONT)
        bottom.addWidget(self.lbl_result_count)

        bottom.addSpacing(12)

        # Run Audit button
        self.btn_run = QPushButton("Run\nAudit")
        self.btn_run.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_run.setFixedSize(60, 36)
        self.btn_run.setStyleSheet(
            "QPushButton { background-color: #C00000; color: white; border: 1px solid #900; "
            "border-radius: 3px; }"
            "QPushButton:hover { background-color: #E00000; }"
        )
        bottom.addWidget(self.btn_run)

        root.addLayout(bottom)

    # ── Initial state ────────────────────────────────────────────────

    def _apply_initial_state(self):
        idx = self.cmb_region.findText(self._region)
        if idx >= 0:
            self.cmb_region.setCurrentIndex(idx)
        # Default system code = "I"  (inforce)
        idx_sys = self.cmb_system.findText("I")
        if idx_sys >= 0:
            self.cmb_system.setCurrentIndex(idx_sys)
