"""
Audit Tool - Main Window
==========================
AuditWindow(FramelessWindowBase) — Silver & Blue themed.

Layout:
  ┌─ Header (silver gradient) ─────────────────────────────────────┐
  │ ● Audit Tool — Region: [CKPR▼]    Co: [▼]   System: [▼]      │
  ├──────────────────────────────────────┬──────────────────────────┤
  │  Criteria Tabs                      │  Results Panel           │
  │  ┌─────┬────────┬───────┬─────┐     │  ┌────────────────────┐  │
  │  │ Pol │ Cov    │ Rider │ ... │     │  │ SQL / Table / Log  │  │
  │  ├─────┴────────┴───────┴─────┤     │  ├────────────────────┤  │
  │  │ Criterion form fields      │     │  │ FilterTableView    │  │
  │  │                            │     │  │                    │  │
  │  │                            │     │  │                    │  │
  │  └────────────────────────────┘     │  └────────────────────┘  │
  ├──────────────────────────────────────┴──────────────────────────┤
  │  Status bar                                                     │
  └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import time
import traceback
from typing import Optional, List, Tuple

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QComboBox, QPushButton, QFrame, QMessageBox,
    QApplication, QProgressBar, QTextEdit, QToolButton,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.core.db2_connection import DB2Connection, DB2ConnectionError, db_connection
from suiteview.core.db2_constants import REGIONS, DEFAULT_REGION

from ..models.audit_criteria import AuditCriteria
from ..models.audit_query_builder import AuditQueryBuilder
from ..models.audit_constants import (
    COMPANY_CODES, COMPANY_LIST, SYSTEM_CODES, MARKET_ORG_CODES,
)
from .styles import (
    AUDIT_HEADER_COLORS, AUDIT_BORDER_COLOR,
    audit_window_stylesheet, results_panel_stylesheet,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Background query worker
# =============================================================================
class QueryWorker(QThread):
    """Run an audit query on a background thread."""
    finished = pyqtSignal(list, list, float)  # columns, rows, elapsed_secs
    error = pyqtSignal(str)
    sql_ready = pyqtSignal(str)  # emits generated SQL

    def __init__(self, criteria: AuditCriteria, parent=None):
        super().__init__(parent)
        self.criteria = criteria

    def run(self):
        try:
            builder = AuditQueryBuilder(self.criteria)
            sql = builder.build_query()
            self.sql_ready.emit(sql)

            t0 = time.perf_counter()
            db = db_connection(self.criteria.region)
            columns, rows = db.execute_query_with_headers(sql)
            elapsed = time.perf_counter() - t0
            self.finished.emit(columns, rows, elapsed)
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")


# =============================================================================
# Main Window
# =============================================================================
class AuditWindow(FramelessWindowBase):
    """
    Audit Tool main window.

    Uses FramelessWindowBase with Silver header gradient and Blue border.
    """

    def __init__(self, region: str = DEFAULT_REGION, parent=None):
        # State initialised *before* super().__init__() which calls build_content()
        self.region = region
        self.criteria = AuditCriteria(region=region)
        self._worker: Optional[QueryWorker] = None
        self._last_sql = ""
        self._result_columns: List[str] = []
        self._result_rows: List[list] = []

        super().__init__(
            title="Audit Tool",
            default_size=(1440, 900),
            min_size=(900, 600),
            parent=parent,
            header_colors=AUDIT_HEADER_COLORS,
            border_color=AUDIT_BORDER_COLOR,
        )
        self.setStyleSheet(audit_window_stylesheet())

    # ── build_content (FramelessWindowBase override) ────────────────────
    def build_content(self) -> QWidget:
        body = QWidget()
        body.setObjectName("CentralWidget")
        root = QVBoxLayout(body)
        root.setContentsMargins(4, 0, 4, 4)
        root.setSpacing(4)

        # Toolbar
        root.addWidget(self._build_toolbar())

        # All tabs in one bar (criteria + results + SQL)
        self.criteria_tabs = self._build_all_tabs()
        root.addWidget(self.criteria_tabs, stretch=1)

        # Status bar (footer in theme blue)
        self.status_bar = QFrame()
        self.status_bar.setObjectName("StatusBarFrame")
        self.status_bar.setFixedHeight(24)
        sb_layout = QHBoxLayout(self.status_bar)
        sb_layout.setContentsMargins(8, 2, 8, 2)
        self.status_label = QLabel("Ready")
        sb_layout.addWidget(self.status_label)
        sb_layout.addStretch()
        self.timing_label = QLabel("")
        sb_layout.addWidget(self.timing_label)
        root.addWidget(self.status_bar)

        return body

    # ── All tabs (criteria + results + SQL in one tab bar) ────────────
    def _build_all_tabs(self) -> QTabWidget:
        """Build a single tab bar with criteria tabs, then Results and SQL."""
        tabs = QTabWidget()

        # -- Criteria panels --
        from .panels.policy_panel import PolicyPanel
        from .panels.coverage_panel import CoveragePanel
        from .panels.rider_panel import RiderPanel
        from .panels.benefits_panel import BenefitsPanel
        from .panels.financial_panel import FinancialPanel
        from .panels.display_panel import DisplayPanel
        from .panels.transactions_panel import TransactionsPanel
        from .panels.loan_panel import LoanPanel

        self.policy_panel = PolicyPanel(self.criteria)
        self.coverage_panel = CoveragePanel(self.criteria)
        self.rider_panel = RiderPanel(self.criteria)
        self.benefits_panel = BenefitsPanel(self.criteria)
        self.financial_panel = FinancialPanel(self.criteria)
        self.display_panel = DisplayPanel(self.criteria)
        self.transactions_panel = TransactionsPanel(self.criteria)
        self.loan_panel = LoanPanel(self.criteria)

        tabs.addTab(self.policy_panel, "Policy")
        tabs.addTab(self.coverage_panel, "Coverage")
        tabs.addTab(self.rider_panel, "Riders")
        tabs.addTab(self.benefits_panel, "Benefits")
        tabs.addTab(self.financial_panel, "Financial")
        tabs.addTab(self.loan_panel, "Loan")
        tabs.addTab(self.display_panel, "Display")
        tabs.addTab(self.transactions_panel, "Transactions")

        # -- Results tab (inline) --
        results_widget = self._build_results_tab()
        self._results_tab_index = tabs.count()
        tabs.addTab(results_widget, "Results")

        # -- SQL tab (inline) --
        self.sql_preview = QTextEdit()
        self.sql_preview.setReadOnly(True)
        self.sql_preview.setObjectName("SqlPreview")
        self.sql_preview.setFont(QFont("Consolas", 10))
        self.sql_preview.setPlaceholderText(
            "Generated SQL will appear here after running a query\u2026"
        )
        self._sql_tab_index = tabs.count()
        tabs.addTab(self.sql_preview, "SQL")

        return tabs

    # ── Toolbar ─────────────────────────────────────────────────────────
    def _build_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ToolbarFrame")
        frame.setFixedHeight(42)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        # Region combo
        layout.addWidget(QLabel("Region:"))
        self.region_combo = QComboBox()
        self.region_combo.addItems(REGIONS)
        self.region_combo.setCurrentText(self.region)
        self.region_combo.setFixedWidth(80)
        self.region_combo.currentTextChanged.connect(self._on_region_changed)
        layout.addWidget(self.region_combo)

        # Company combo
        layout.addWidget(QLabel("Company:"))
        self.company_combo = QComboBox()
        self.company_combo.addItem("", "")
        for code, name in COMPANY_CODES.items():
            self.company_combo.addItem(f"{code} — {name}", code)
        self.company_combo.setFixedWidth(200)
        self.company_combo.currentIndexChanged.connect(self._on_company_changed)
        layout.addWidget(self.company_combo)

        # System combo
        layout.addWidget(QLabel("System:"))
        self.system_combo = QComboBox()
        self.system_combo.addItem("Any", "")
        for code, name in SYSTEM_CODES.items():
            self.system_combo.addItem(f"{code} — {name}", code)
        self.system_combo.setCurrentIndex(1)  # Default "I" Individual
        self.system_combo.setFixedWidth(140)
        self.system_combo.currentIndexChanged.connect(self._on_system_changed)
        layout.addWidget(self.system_combo)

        # Market Org combo
        layout.addWidget(QLabel("Market Org:"))
        self.market_org_combo = QComboBox()
        self.market_org_combo.addItem("", "")
        for code, name in MARKET_ORG_CODES.items():
            self.market_org_combo.addItem(f"{code} — {name}", code)
        self.market_org_combo.setFixedWidth(200)
        self.market_org_combo.currentIndexChanged.connect(self._on_market_org_changed)
        layout.addWidget(self.market_org_combo)

        layout.addStretch()

        # Max results
        layout.addWidget(QLabel("Max:"))
        self.max_combo = QComboBox()
        self.max_combo.addItems(["25", "50", "100", "250", "500", "1000", "All"])
        self.max_combo.setFixedWidth(70)
        self.max_combo.currentTextChanged.connect(self._on_max_changed)
        layout.addWidget(self.max_combo)

        # Run button
        self.run_btn = QPushButton("Run Audit")
        self.run_btn.setFixedWidth(100)
        self.run_btn.clicked.connect(self.run_audit)
        layout.addWidget(self.run_btn)

        # Clear button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("SecondaryButton")
        self.clear_btn.setFixedWidth(60)
        self.clear_btn.clicked.connect(self.clear_criteria)
        layout.addWidget(self.clear_btn)

        # Export button
        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.setFixedWidth(60)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_results)
        layout.addWidget(self.export_btn)

        return frame

    # ── Results tab (inline in tab bar) ──────────────────────────────
    def _build_results_tab(self) -> QWidget:
        """Build the results tab content (summary bar + progress + table)."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Summary / filter chips bar
        self.summary_bar = QFrame()
        self.summary_bar.setObjectName("SummaryBar")
        self.summary_bar.setFixedHeight(28)
        sb_layout = QHBoxLayout(self.summary_bar)
        sb_layout.setContentsMargins(8, 2, 8, 2)
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("StatusLabel")
        sb_layout.addWidget(self.summary_label)
        sb_layout.addStretch()
        layout.addWidget(self.summary_bar)

        # Progress bar (hidden until query runs)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Results table
        try:
            from suiteview.ui.widgets.filter_table_view import FilterTableView
            self.results_table = FilterTableView()
            layout.addWidget(self.results_table, stretch=1)
        except ImportError:
            self.results_table = None
            layout.addWidget(QLabel("Results will appear here"), stretch=1)

        container.setStyleSheet(results_panel_stylesheet())
        return container

    # ── Collect criteria from all panels ────────────────────────────────
    def _collect_criteria(self):
        """Read current state from all panels back into self.criteria."""
        self.criteria.region = self.region_combo.currentText()
        self.criteria.company = self.company_combo.currentData() or ""
        self.criteria.system_code = self.system_combo.currentData() or ""
        self.criteria.market_org = self.market_org_combo.currentData() or ""

        max_text = self.max_combo.currentText()
        if max_text == "All":
            self.criteria.show_all = True
            self.criteria.max_count = 0
        else:
            self.criteria.show_all = False
            self.criteria.max_count = int(max_text)

        # Each panel writes its fields to self.criteria
        self.policy_panel.write_to_criteria(self.criteria)
        self.coverage_panel.write_to_criteria(self.criteria)
        self.rider_panel.write_to_criteria(self.criteria)
        self.benefits_panel.write_to_criteria(self.criteria)
        self.financial_panel.write_to_criteria(self.criteria)
        self.loan_panel.write_to_criteria(self.criteria)
        self.display_panel.write_to_criteria(self.criteria)
        self.transactions_panel.write_to_criteria(self.criteria)

    # ── Run audit query ─────────────────────────────────────────────────
    def run_audit(self):
        """Collect criteria, build query, run on background thread."""
        if self._worker and self._worker.isRunning():
            self._show_status("Query already running…")
            return

        self._collect_criteria()

        # Show progress
        self.run_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._show_status("Building query…")

        # Update summary bar with active filters
        summary_parts = self.criteria.get_active_criteria_summary()
        if summary_parts:
            self.summary_label.setText(" | ".join(summary_parts))
        else:
            self.summary_label.setText("No filters — returning all policies")

        self._worker = QueryWorker(self.criteria)
        self._worker.sql_ready.connect(self._on_sql_ready)
        self._worker.finished.connect(self._on_query_finished)
        self._worker.error.connect(self._on_query_error)
        self._worker.start()

    def _on_sql_ready(self, sql: str):
        """SQL generated — show it in the SQL tab."""
        self._last_sql = sql
        self.sql_preview.setPlainText(sql)
        self._show_status("Executing query…")

    def _on_query_finished(self, columns: list, rows: list, elapsed: float):
        """Query completed — display results."""
        self._result_columns = columns
        self._result_rows = rows

        self.progress_bar.setVisible(False)
        self.run_btn.setEnabled(True)
        self.export_btn.setEnabled(len(rows) > 0)

        self.timing_label.setText(f"{len(rows):,} rows in {elapsed:.2f}s")
        self._show_status(f"Query returned {len(rows):,} rows in {elapsed:.2f}s")

        # Load into FilterTableView
        if self.results_table is not None and columns:
            try:
                import pandas as pd
                df = pd.DataFrame(rows, columns=columns)
                self.results_table.load_dataframe(df)
            except Exception as e:
                logger.error(f"Error loading results: {e}")
                self._show_status(f"Error loading results: {e}")

        # Switch to results tab
        self.criteria_tabs.setCurrentIndex(self._results_tab_index)

    def _on_query_error(self, error_msg: str):
        """Query failed — show error."""
        self.progress_bar.setVisible(False)
        self.run_btn.setEnabled(True)
        self._show_status(f"Error: {error_msg.splitlines()[0]}")
        self.sql_preview.setPlainText(
            f"-- ERROR --\n{error_msg}\n\n-- SQL --\n{self._last_sql}"
        )
        self.criteria_tabs.setCurrentIndex(self._sql_tab_index)  # Switch to SQL tab

    # ── Toolbar callbacks ───────────────────────────────────────────────
    def _on_region_changed(self, region: str):
        self.region = region
        self.criteria.region = region
        self._show_status(f"Region changed to {region}")

    def _on_company_changed(self, idx: int):
        self.criteria.company = self.company_combo.currentData() or ""

    def _on_system_changed(self, idx: int):
        self.criteria.system_code = self.system_combo.currentData() or ""

    def _on_market_org_changed(self, idx: int):
        self.criteria.market_org = self.market_org_combo.currentData() or ""

    def _on_max_changed(self, text: str):
        if text == "All":
            self.criteria.show_all = True
        else:
            self.criteria.show_all = False
            self.criteria.max_count = int(text)

    def clear_criteria(self):
        """Reset all criteria to defaults."""
        self.criteria = AuditCriteria(region=self.region)
        # Reset toolbar combos
        self.company_combo.setCurrentIndex(0)
        self.system_combo.setCurrentIndex(1)  # default "I"
        self.market_org_combo.setCurrentIndex(0)
        self.max_combo.setCurrentIndex(0)  # 25

        # Tell each panel to reset
        self.policy_panel.reset(self.criteria)
        self.coverage_panel.reset(self.criteria)
        self.rider_panel.reset(self.criteria)
        self.benefits_panel.reset(self.criteria)
        self.financial_panel.reset(self.criteria)
        self.loan_panel.reset(self.criteria)
        self.display_panel.reset(self.criteria)
        self.transactions_panel.reset(self.criteria)

        self.summary_label.setText("")
        self.timing_label.setText("")
        self._show_status("Criteria cleared")

    def _export_results(self):
        """Export results to Excel."""
        if not self._result_rows:
            return
        try:
            import pandas as pd
            from PyQt6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(
                self, "Export Audit Results", "audit_results.xlsx",
                "Excel Files (*.xlsx);;CSV Files (*.csv)"
            )
            if not path:
                return

            df = pd.DataFrame(self._result_rows, columns=self._result_columns)
            if path.endswith(".csv"):
                df.to_csv(path, index=False)
            else:
                df.to_excel(path, index=False, sheet_name="Audit Results")
            self._show_status(f"Exported {len(df):,} rows to {path}")
        except Exception as e:
            self._show_status(f"Export error: {e}")

    # ── Status display ──────────────────────────────────────────────────
    def _show_status(self, msg: str):
        self.status_label.setText(msg)
        logger.info(msg)
