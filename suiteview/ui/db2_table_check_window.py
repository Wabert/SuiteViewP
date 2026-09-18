"""DB2 Table Check window.

Runs :func:`suiteview.core.db2_table_access.scan_table_access` for a region
(default CKPR) on a background thread and lists every LH_/TH_ table that was
checked, with the tables the current login *cannot* access pulled to the top.
The full list can be copied to the clipboard.
"""
from __future__ import annotations

import logging

import pandas as pd
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QApplication,
    QProgressBar, QMessageBox,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.core.db2_table_access import scan_table_access
from suiteview.core.access_control import guard_app_access, requires_app_access

logger = logging.getLogger(__name__)

_NO_ACCESS = "❌ NO ACCESS"
_OK = "✅ OK"


class _ScanWorker(QThread):
    """Runs the DB2 table-access scan off the UI thread."""

    progressed = pyqtSignal(int, int, str)   # done, total, table
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, region: str, parent=None):
        super().__init__(parent)
        self._region = region

    def run(self):
        try:
            result = scan_table_access(
                self._region,
                progress=lambda done, total, table: self.progressed.emit(
                    done, total, table
                ),
            )
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            logger.error("DB2 table check failed: %s", exc, exc_info=True)
            self.failed.emit(str(exc).split("\x00", 1)[0].strip())


class DB2TableCheckWindow(FramelessWindowBase):
    """List LH_/TH_ tables and flag the ones the login can't SELECT."""

    def __init__(self, region: str = "CKPR", parent=None):
        guard_app_access("ADMINISTRATOR")
        self._region = region.upper()
        self._result: dict | None = None
        self._worker: _ScanWorker | None = None
        super().__init__(
            title=f"SuiteView:  DB2 Table Check ({self._region})",
            default_size=(760, 720),
            min_size=(560, 480),
            parent=parent,
        )
        # Kick off the scan as soon as the window is constructed.
        self._start_scan()

    # ── FramelessWindowBase override ──────────────────────────────────

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setObjectName("db2CheckBody")
        body.setStyleSheet(
            "QWidget#db2CheckBody { background-color: #EAF2FB; }"
        )
        root = QVBoxLayout(body)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # Header row: summary label + copy button
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self._summary_label = QLabel(
            f"Scanning {self._region} for LH_/TH_ tables…"
        )
        self._summary_label.setStyleSheet(
            "color: #0D3A7A; font-size: 12px; font-weight: 600; background: transparent;"
        )
        top_row.addWidget(self._summary_label, 1)

        self._rescan_btn = QPushButton("Rescan")
        self._rescan_btn.setEnabled(False)
        self._rescan_btn.setStyleSheet(self._button_style())
        self._rescan_btn.clicked.connect(self._start_scan)
        top_row.addWidget(self._rescan_btn)

        self._copy_btn = QPushButton("Copy to Clipboard")
        self._copy_btn.setEnabled(False)
        self._copy_btn.setStyleSheet(self._button_style())
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        top_row.addWidget(self._copy_btn)

        root.addLayout(top_row)

        # Progress bar (hidden once the scan completes)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate until first tick
        self._progress.setTextVisible(True)
        self._progress.setFormat("Connecting…")
        self._progress.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #B7C9E0; border-radius: 3px;
                background: white; height: 16px; text-align: center;
                color: #0D3A7A; font-size: 10px;
            }
            QProgressBar::chunk { background-color: #1E5BA8; }
            """
        )
        root.addWidget(self._progress)

        # Results table
        self._table = FilterTableView()
        root.addWidget(self._table, 1)

        return body

    # ── Scan lifecycle ────────────────────────────────────────────────

    @requires_app_access("ADMINISTRATOR")
    def _start_scan(self):
        if self._worker is not None and self._worker.isRunning():
            return
        self._copy_btn.setEnabled(False)
        self._rescan_btn.setEnabled(False)
        self._summary_label.setText(
            f"Scanning {self._region} for LH_/TH_ tables…"
        )
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._progress.setFormat("Connecting…")

        self._worker = _ScanWorker(self._region, self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done: int, total: int, table: str):
        if self._progress.maximum() != total:
            self._progress.setRange(0, total)
        self._progress.setValue(done)
        self._progress.setFormat(f"Checking {done}/{total}: {table}")

    def _on_finished(self, result: dict):
        self._result = result
        self._progress.setVisible(False)
        self._rescan_btn.setEnabled(True)
        self._copy_btn.setEnabled(True)

        no_access = result.get("no_access_count", 0)
        total = result.get("total", 0)
        schema = result.get("schema", "")
        self._summary_label.setText(
            f"{self._region} · schema {schema} · {total} LH_/TH_ tables · "
            f"{no_access} with NO access, {result.get('accessible_count', 0)} accessible"
        )
        self._populate_table(result)

    def _on_failed(self, message: str):
        self._progress.setVisible(False)
        self._rescan_btn.setEnabled(True)
        self._summary_label.setText(f"Scan failed: {message}")
        QMessageBox.warning(
            self, "DB2 Table Check",
            f"Could not scan {self._region}:\n\n{message}"
        )

    # ── Table + clipboard ─────────────────────────────────────────────

    def _populate_table(self, result: dict):
        rows = []
        # No-access tables first, so they sit at the top of the list.
        for entry in result.get("no_access", []):
            rows.append({
                "Access": _NO_ACCESS,
                "Table": entry.get("table", ""),
                "SQLSTATE": entry.get("sqlstate", ""),
                "Detail": entry.get("error", ""),
            })
        for name in result.get("accessible", []):
            rows.append({
                "Access": _OK,
                "Table": name,
                "SQLSTATE": "",
                "Detail": "",
            })

        df = pd.DataFrame(rows, columns=["Access", "Table", "SQLSTATE", "Detail"])
        self._table.set_dataframe(df, limit_rows=False)

    def _copy_to_clipboard(self):
        if not self._result:
            return
        text = self._build_clipboard_text(self._result)
        QApplication.clipboard().setText(text)
        self._summary_label.setText(
            self._summary_label.text() + "  —  copied to clipboard ✓"
        )

    @staticmethod
    def _build_clipboard_text(result: dict) -> str:
        region = result.get("region", "")
        schema = result.get("schema", "")
        no_access = result.get("no_access", [])
        accessible = result.get("accessible", [])

        lines: list[str] = []
        lines.append(f"DB2 Table Check — {region} (schema {schema})")
        lines.append(
            f"{result.get('total', 0)} LH_/TH_ tables · "
            f"{len(no_access)} with NO access · {len(accessible)} accessible"
        )
        lines.append("")
        lines.append(f"NO ACCESS ({len(no_access)}):")
        if no_access:
            for entry in no_access:
                state = entry.get("sqlstate", "")
                suffix = f"  [{state}]" if state else ""
                lines.append(f"  - {entry.get('table', '')}{suffix}")
        else:
            lines.append("  (none)")
        lines.append("")
        lines.append(f"ACCESSIBLE ({len(accessible)}):")
        for name in accessible:
            lines.append(f"  - {name}")
        return "\n".join(lines)

    # ── Shared button styling ─────────────────────────────────────────

    @staticmethod
    def _button_style() -> str:
        return """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2A5AA4, stop:1 #1E5BA8);
                color: white; border: 1px solid #0D3A7A;
                border-radius: 4px; padding: 5px 14px;
                font-size: 11px; font-weight: 600;
            }
            QPushButton:hover { background: #3A7DC8; }
            QPushButton:disabled { background: #9DB4D4; color: #E4ECF6; border-color: #9DB4D4; }
        """

    # ── Cleanup ───────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)
