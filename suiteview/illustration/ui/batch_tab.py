"""Illustration Batch tab — run batch forecasts over a pasted policy list.

Business-user surface for the batch forecasts that previously lived only in the
developer CLI tools (``tools/run_glp_forecast_batch.py`` and
``tools/run_min_level_to_exception_batch.py``). Paste a policy list (one per
line, optional two-digit company prefix), pick the forecast type, and Run: the
batch executes on a background thread (the UI stays live), a progress bar shows
"n of N — <policy>", Cancel stops after the in-flight policy, and results land
in a filterable grid — policies as rows, forecast outputs as columns, with loud
Status / Error columns. Excel opens the grid as a new unsaved workbook.

All forecast logic lives in ``suiteview.illustration.core.batch_runner``
(shared with the CLI tools); this tab is a thin Qt shell around ``run_batch``.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.core.batch_runner import (
    FORECAST_TYPES,
    PolicyResult,
    parse_policy_list,
    results_dataframe,
    run_batch,
)
from suiteview.ui.widgets.filter_table_view import FilterTableView

from .styles import (
    INPUT_CAPTION_STYLE,
    INPUT_COMBO_STYLE,
    INPUT_EDIT_STYLE,
    PURPLE_BG,
    PURPLE_DARK,
    PURPLE_PRIMARY,
    PURPLE_SUBTLE,
    VALUE_BUTTON_STYLE,
    WHITE,
)

logger = logging.getLogger(__name__)

_PASTE_STYLE = (
    f"QPlainTextEdit {{ background: {WHITE}; color: {PURPLE_DARK};"
    " border: 1px solid #B79CDE; border-radius: 3px; padding: 2px 4px;"
    " font-size: 11px; font-family: Consolas, monospace; }"
)

_CANCEL_BUTTON_STYLE = (
    "QPushButton { background: #F3ECFC; color: #4B2383; border: 1px solid #7E57C2;"
    " border-radius: 5px; font-size: 10px; font-weight: bold; padding: 3px 12px;"
    " min-height: 22px; }"
    "QPushButton:hover { background: #E6DAF8; }"
    "QPushButton:disabled { color: #9A8FB0; border-color: #C9B8E4; }"
)

_PROGRESS_STYLE = (
    f"QProgressBar {{ background: {PURPLE_SUBTLE}; border: 1px solid {PURPLE_PRIMARY};"
    f" border-radius: 3px; color: {PURPLE_DARK}; font-size: 10px; font-weight: bold;"
    " text-align: center; min-height: 16px; max-height: 16px; }"
    f"QProgressBar::chunk {{ background: {PURPLE_PRIMARY}; }}"
)


class _BatchWorker(QThread):
    """Runs one batch off the UI thread through ``batch_runner.run_batch``."""

    progress = pyqtSignal(int, int, str)   # index (1-based), total, policy
    finished_results = pyqtSignal(list)    # List[PolicyResult]
    failed = pyqtSignal(str)

    def __init__(self, entries: List[Tuple[Optional[str], str]], forecast_key: str,
                 region: str, company: Optional[str], runner=run_batch, parent=None):
        super().__init__(parent)
        self._entries = entries
        self._forecast_key = forecast_key
        self._region = region
        self._company = company
        self._runner = runner
        self._cancelled = False

    def cancel(self):
        """Request a stop after the in-flight policy finishes."""
        self._cancelled = True

    def run(self):  # pragma: no cover - thread body exercised via runner tests
        try:
            results = self._runner(
                self._entries,
                self._forecast_key,
                region=self._region,
                default_company=self._company,
                progress=lambda i, n, p: self.progress.emit(i, n, p),
                should_cancel=lambda: self._cancelled,
            )
            self.finished_results.emit(list(results))
        except Exception as exc:  # defensive — run_batch isolates per policy
            logger.error("Batch run failed: %s", exc, exc_info=True)
            self.failed.emit(str(exc))


class IllustrationBatchTab(QWidget):
    """Batch forecasts: policy list in, results grid + Excel out."""

    def __init__(self, parent=None, *, runner=run_batch):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        self._runner = runner
        self._worker: Optional[_BatchWorker] = None
        self._results: List[PolicyResult] = []
        self._results_df: Optional[pd.DataFrame] = None
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Top: policy list + controls, packed left with end stretch ──
        top = QHBoxLayout()
        top.setSpacing(8)

        # Policy list paste area
        paste_col = QVBoxLayout()
        paste_col.setSpacing(2)
        paste_caption = QLabel("Policies — one per line ('01 UL054426' or 'UL054426')")
        paste_caption.setStyleSheet(INPUT_CAPTION_STYLE)
        paste_col.addWidget(paste_caption)
        self.policy_edit = QPlainTextEdit()
        self.policy_edit.setStyleSheet(_PASTE_STYLE)
        self.policy_edit.setFixedSize(300, 120)
        self.policy_edit.setPlaceholderText("Paste policy numbers here...")
        paste_col.addWidget(self.policy_edit)
        top.addLayout(paste_col)

        # Controls column
        controls = QVBoxLayout()
        controls.setSpacing(4)

        selectors = QHBoxLayout()
        selectors.setSpacing(4)
        region_caption = QLabel("Region")
        region_caption.setStyleSheet(INPUT_CAPTION_STYLE)
        selectors.addWidget(region_caption)
        self.region_input = QLineEdit("CKPR")
        self.region_input.setStyleSheet(INPUT_EDIT_STYLE)
        self.region_input.setFixedWidth(50)
        selectors.addWidget(self.region_input)
        company_caption = QLabel("Co")
        company_caption.setStyleSheet(INPUT_CAPTION_STYLE)
        selectors.addWidget(company_caption)
        self.company_input = QLineEdit()
        self.company_input.setStyleSheet(INPUT_EDIT_STYLE)
        self.company_input.setFixedWidth(30)
        self.company_input.setPlaceholderText("")
        self.company_input.setToolTip(
            "Default company code applied to lines without their own prefix. "
            "Blank = resolve per policy.")
        selectors.addWidget(self.company_input)
        forecast_caption = QLabel("Forecast")
        forecast_caption.setStyleSheet(INPUT_CAPTION_STYLE)
        selectors.addWidget(forecast_caption)
        self.forecast_combo = QComboBox()
        self.forecast_combo.setStyleSheet(INPUT_COMBO_STYLE)
        for key, forecast in FORECAST_TYPES.items():
            self.forecast_combo.addItem(forecast.label, key)
        selectors.addWidget(self.forecast_combo)
        selectors.addStretch(1)
        controls.addLayout(selectors)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        self.run_btn = QPushButton("Run Batch")
        self.run_btn.setStyleSheet(VALUE_BUTTON_STYLE)
        self.run_btn.setFixedHeight(26)
        self.run_btn.clicked.connect(self._on_run)
        buttons.addWidget(self.run_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(_CANCEL_BUTTON_STYLE)
        self.cancel_btn.setFixedHeight(26)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        buttons.addWidget(self.cancel_btn)
        self.excel_btn = QPushButton("Excel")
        self.excel_btn.setStyleSheet(_CANCEL_BUTTON_STYLE)
        self.excel_btn.setFixedHeight(26)
        self.excel_btn.setEnabled(False)
        self.excel_btn.setToolTip("Open the results grid in a new unsaved Excel workbook")
        self.excel_btn.clicked.connect(self._on_export)
        buttons.addWidget(self.excel_btn)
        buttons.addStretch(1)
        controls.addLayout(buttons)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(_PROGRESS_STYLE)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        controls.addWidget(self.progress_bar)

        self.progress_label = QLabel("Paste a policy list and click Run Batch.")
        self.progress_label.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 10px;"
            " font-weight: bold;")
        controls.addWidget(self.progress_label)
        controls.addStretch(1)
        top.addLayout(controls, 1)
        layout.addLayout(top)

        # ── Results grid ──
        self.results_view = FilterTableView(self)
        self.results_view.setStyleSheet(
            f"QWidget {{ background-color: {WHITE}; }}")
        layout.addWidget(self.results_view, 1)

    # ── Run / cancel ─────────────────────────────────────────────────

    def _on_run(self):
        entries = parse_policy_list(self.policy_edit.toPlainText())
        if not entries:
            QMessageBox.information(
                self, "Batch Forecast",
                "Paste at least one policy number (one per line).")
            return
        if self._worker is not None and self._worker.isRunning():
            return

        forecast_key = self.forecast_combo.currentData()
        region = self.region_input.text().strip().upper() or "CKPR"
        company = self.company_input.text().strip() or None

        # Leave any prior results on screen until new ones arrive (resetting
        # FilterTableView to an empty frame triggers a stale-header repaint).
        self._results = []
        self._results_df = None
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.excel_btn.setEnabled(False)
        self.progress_bar.setRange(0, len(entries))
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_label.setText(
            f"Starting batch — {len(entries)} "
            f"{'policy' if len(entries) == 1 else 'policies'}...")

        self._worker = _BatchWorker(
            entries, forecast_key, region, company, runner=self._runner, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_results.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_cancel(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.progress_label.setText(
                "Cancelling — finishing the in-flight policy...")

    def _on_progress(self, index: int, total: int, policy: str):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(index - 1)
        self.progress_label.setText(f"{index} of {total} — {policy}")

    def _on_finished(self, results: list):
        self._worker = None
        self.populate_results(results)

    def _on_failed(self, message: str):
        self._worker = None
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_label.setText(f"Batch failed: {message}")
        QMessageBox.critical(self, "Batch Forecast", f"Batch run failed:\n{message}")

    # ── Results ──────────────────────────────────────────────────────

    def populate_results(self, results: List[PolicyResult]):
        """Fill the grid from a finished batch (also the test seam)."""
        self._results = list(results)
        forecast_key = self.forecast_combo.currentData()
        df = results_dataframe(self._results, forecast_key)
        self._results_df = df
        self.results_view.set_dataframe(df, limit_rows=False)
        try:
            self.results_view.autofit_columns_to_data()
        except Exception:  # empty frame — nothing to autofit
            pass

        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.excel_btn.setEnabled(not df.empty)
        self.progress_bar.setValue(self.progress_bar.maximum())

        counts: dict = {}
        for result in self._results:
            counts[result.status] = counts.get(result.status, 0) + 1
        summary = "  ·  ".join(f"{status}: {count}" for status, count in counts.items())
        self.progress_label.setText(
            f"Done — {len(self._results)} "
            f"{'policy' if len(self._results) == 1 else 'policies'}"
            + (f"  ·  {summary}" if summary else ""))

    # ── Excel export ─────────────────────────────────────────────────

    def _on_export(self):
        df = self._results_df
        if df is None or df.empty:
            return
        try:
            from suiteview.core.excel_export import (
                ExcelExportError, dump_to_new_workbook,
            )

            forecast_key = self.forecast_combo.currentData()
            label = FORECAST_TYPES[forecast_key].label
            headers = list(df.columns)
            data = [tuple("" if v is None else v for v in rec)
                    for rec in df.itertuples(index=False, name=None)]
            text_cols = [i + 1 for i, c in enumerate(headers)
                         if c in ("Policy", "Company")]
            excel, wb, ws = dump_to_new_workbook(
                headers, data, sheet_name=f"Batch {label}"[:31],
                text_col_indexes=text_cols)
            # Header formatting: white on Illustration purple (BGR for #5E35A5).
            hdr = ws.Range(ws.Cells(1, 1), ws.Cells(1, len(headers)))
            hdr.Font.Color = 0xFFFFFF
            hdr.Interior.Color = 0xA5355E
            hdr.HorizontalAlignment = -4108  # xlCenter
        except ExcelExportError as e:
            QMessageBox.warning(self, "Excel Error", str(e))
        except Exception as e:  # pragma: no cover - UI guard
            logger.error("Batch export failed: %s", e, exc_info=True)
            QMessageBox.warning(self, "Export Error", f"Could not export:\n{e}")
