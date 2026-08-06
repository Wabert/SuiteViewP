"""Illustration Regression tab: portable suites, batch runs, and baselines."""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.core.regression_runner import (
    PreparedRegressionCase,
    RegressionRun,
    recompare_run,
    run_regression,
)
from suiteview.illustration.core.summary_results import ALL_COLUMNS
from suiteview.illustration.models import case_store
from suiteview.illustration.models.regression_suite import (
    RESULT_SUFFIX,
    SUITE_SUFFIX,
    RegressionSuite,
    create_suite,
    load_suite,
    save_run_result,
    save_suite,
    undo_baseline_update,
    update_baseline,
)
from suiteview.ui.widgets.filter_table_view import FilterTableView

from .saved_case_scenario import materialize_saved_case
from .styles import (
    PURPLE_BG,
    PURPLE_DARK,
    PURPLE_PRIMARY,
    PURPLE_SUBTLE,
    VALUE_BUTTON_STYLE,
    WHITE,
)

logger = logging.getLogger(__name__)

_SECONDARY_BUTTON_STYLE = (
    "QPushButton { background: #F3ECFC; color: #4B2383; border: 1px solid #7E57C2;"
    " border-radius: 4px; font-size: 10px; font-weight: bold; padding: 3px 9px;"
    " min-height: 22px; }"
    "QPushButton:hover { background: #E6DAF8; }"
    "QPushButton:disabled { color: #9A8FB0; border-color: #C9B8E4; }"
)


class _RegressionWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_run = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, prepared, baseline, *, runner=run_regression, parent=None):
        super().__init__(parent)
        self._prepared = prepared
        self._baseline = baseline
        self._runner = runner
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):  # pragma: no cover - runner tests own the calculation path
        try:
            result = self._runner(
                self._prepared,
                self._baseline,
                progress=lambda index, total, name:
                    self.progress.emit(index, total, name),
                should_cancel=lambda: self._cancelled,
            )
            self.finished_run.emit(result)
        except Exception as exc:
            logger.error("Regression run failed: %s", exc, exc_info=True)
            self.failed.emit(str(exc) or type(exc).__name__)


class IllustrationRegressionTab(QWidget):
    """Create, run, inspect, and rebaseline portable regression suites."""

    def __init__(self, window=None, parent=None, *, runner=run_regression):
        super().__init__(parent)
        self._window = window
        self._runner = runner
        self._suite: Optional[RegressionSuite] = None
        self._run: Optional[RegressionRun] = None
        self._audit_run: Optional[RegressionRun] = None
        self._worker: Optional[_RegressionWorker] = None
        self._build_ui()
        self._sync_actions()

    def _button(self, text: str, *, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setStyleSheet(VALUE_BUTTON_STYLE if primary else _SECONDARY_BUTTON_STYLE)
        button.setFixedHeight(26)
        return button

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self.new_btn = self._button("New from Selected Cases")
        self.open_btn = self._button("Open Suite")
        self.run_btn = self._button("Run", primary=True)
        self.cancel_btn = self._button("Cancel")
        self.update_btn = self._button("Update Baseline")
        self.undo_btn = self._button("Undo Baseline Update")
        self.result_btn = self._button("Export Result")
        self.excel_btn = self._button("Excel")
        for button in (
            self.new_btn, self.open_btn, self.run_btn, self.cancel_btn,
            self.update_btn, self.undo_btn, self.result_btn, self.excel_btn,
        ):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.new_btn.clicked.connect(self._on_new_suite)
        self.open_btn.clicked.connect(self._on_open_suite)
        self.run_btn.clicked.connect(self._on_run)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.update_btn.clicked.connect(self._on_update_baseline)
        self.undo_btn.clicked.connect(self._on_undo_baseline)
        self.result_btn.clicked.connect(self._on_export_result)
        self.excel_btn.clicked.connect(self._on_excel)

        self.suite_label = QLabel("No regression suite open.")
        self.suite_label.setStyleSheet(
            f"background: {PURPLE_SUBTLE}; color: {PURPLE_DARK};"
            f" border: 1px solid {PURPLE_PRIMARY}; padding: 4px 7px;"
            " font-size: 10px; font-weight: bold;"
        )
        layout.addWidget(self.suite_label)

        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setFixedHeight(17)
        self.progress.setTextVisible(True)
        self.progress_label = QLabel("Open or create a suite to begin.")
        self.progress_label.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 10px;"
        )
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_label, 2)
        layout.addLayout(progress_row)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Vertical)
        self.case_grid = FilterTableView()
        self.case_grid.set_search_visible(False)
        self.case_grid.set_full_row_selection(True)
        self.case_grid.table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.case_grid.setStyleSheet(f"QWidget {{ background: {WHITE}; }}")
        self.diff_grid = FilterTableView()
        self.diff_grid.set_search_visible(False)
        self.diff_grid.setStyleSheet(f"QWidget {{ background: {WHITE}; }}")
        splitter.addWidget(self.case_grid)
        splitter.addWidget(self.diff_grid)
        splitter.setSizes([360, 240])
        layout.addWidget(splitter, 1)

    def _sync_actions(self):
        running = self._worker is not None and self._worker.isRunning()
        has_suite = self._suite is not None
        has_run = self._run is not None
        has_candidate = bool(self._run and self._run.candidate_rows)
        self.new_btn.setEnabled(not running)
        self.open_btn.setEnabled(not running)
        self.run_btn.setEnabled(has_suite and not running)
        self.cancel_btn.setEnabled(running)
        self.update_btn.setEnabled(has_candidate and not running)
        self.undo_btn.setEnabled(
            bool(has_suite and self._suite.previous) and not running)
        self.result_btn.setEnabled(bool(self._audit_run) and not running)
        self.excel_btn.setEnabled(has_run and not running)

    def _refresh_suite_label(self):
        if self._suite is None:
            self.suite_label.setText("No regression suite open.")
            return
        active = self._suite.active
        baseline = (
            f"Baseline r{active.revision} · {active.approved_at}"
            if active else "No approved baseline"
        )
        undo = " · Undo available" if self._suite.previous else ""
        self.suite_label.setText(
            f"{self._suite.name} · {len(self._suite.cases)} cases · "
            f"{baseline}{undo} · {self._suite.path}"
        )

    def _confirm_discard_run(self) -> bool:
        if not self._run or not any(
            result.current.status in {"FAIL", "NO BASELINE"}
            or result.guaranteed.status in {"FAIL", "NO BASELINE"}
            for result in self._run.cases
        ):
            return True
        answer = QMessageBox.question(
            self, "Leave Regression Run",
            "The latest run contains unapproved differences. Open another suite?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _selected_saved_cases(self):
        if self._window is None or not hasattr(self._window, "policy_list_window"):
            return []
        view = self._window.policy_list_window.cases_view
        names = view.selected_case_names()
        return [
            case_store.load_case(name, directory=view.cases_directory)
            for name in names
        ]

    def _on_new_suite(self):
        if not self._confirm_discard_run():
            return
        try:
            cases = self._selected_saved_cases()
        except Exception as exc:
            QMessageBox.warning(self, "Regression Suite", str(exc))
            return
        if not cases:
            QMessageBox.information(
                self, "Regression Suite",
                "Select one or more rows in Saved Cases first.")
            return
        name, accepted = QInputDialog.getText(
            self, "New Regression Suite", "Suite name:")
        if not accepted or not name.strip():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Regression Suite", f"{name.strip()}{SUITE_SUFFIX}",
            f"SuiteView Regression Suite (*{SUITE_SUFFIX})")
        if not path:
            return
        try:
            suite = create_suite(name, cases)
            self.set_suite(save_suite(suite, path))
        except Exception as exc:
            QMessageBox.warning(self, "Regression Suite", str(exc))

    def _on_open_suite(self):
        if not self._confirm_discard_run():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Regression Suite", "",
            f"SuiteView Regression Suite (*{SUITE_SUFFIX})")
        if not path:
            return
        try:
            self.set_suite(load_suite(path))
        except Exception as exc:
            QMessageBox.warning(self, "Regression Suite", str(exc))

    def set_suite(self, suite: RegressionSuite):
        """Set the active suite; public for tests and future launch actions."""
        self._suite = suite
        self._run = None
        self._audit_run = None
        self.case_grid.set_dataframe(pd.DataFrame(), limit_rows=False)
        self.diff_grid.set_dataframe(pd.DataFrame(), limit_rows=False)
        self.progress.setRange(0, len(suite.cases))
        self.progress.setValue(0)
        self.progress_label.setText("Ready to run.")
        self._refresh_suite_label()
        self._sync_actions()

    def _prepare_cases(self) -> list[PreparedRegressionCase]:
        prepared = []
        for entry in self._suite.cases:
            try:
                spec = materialize_saved_case(entry.case, strict=True)
                prepared.append(PreparedRegressionCase(
                    entry.case_id, entry.case.name,
                    entry.case.policy_number, spec=spec))
            except Exception as exc:
                prepared.append(PreparedRegressionCase(
                    entry.case_id, entry.case.name, entry.case.policy_number,
                    preparation_error=str(exc) or type(exc).__name__))
        return prepared

    def _on_run(self):
        if self._suite is None or self._worker is not None:
            return
        prepared = self._prepare_cases()
        self.progress.setRange(0, len(prepared))
        self.progress.setValue(0)
        self.progress_label.setText(f"Starting {len(prepared)} cases...")
        self._worker = _RegressionWorker(
            prepared, self._suite.active, runner=self._runner, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_run.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        self._sync_actions()

    def _on_cancel(self):
        if self._worker is not None:
            self._worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.progress_label.setText("Cancelling after the current case...")

    def _on_progress(self, index: int, total: int, name: str):
        self.progress.setRange(0, total)
        self.progress.setValue(index - 1)
        self.progress_label.setText(f"{index} of {total} · {name}")

    def _on_finished(self, run: RegressionRun):
        self._worker = None
        self._audit_run = run
        self._run = run
        self.progress.setValue(len(run.cases))
        self.progress_label.setText(
            "Cancelled." if run.cancelled else f"Completed {len(run.cases)} cases.")
        self._populate_run()
        self._sync_actions()

    def _on_failed(self, message: str):
        self._worker = None
        self.progress_label.setText(f"Run failed: {message}")
        QMessageBox.critical(self, "Regression Run", message)
        self._sync_actions()

    def _summary_frame(self) -> pd.DataFrame:
        rows = []
        for result in self._run.cases if self._run else []:
            numeric_deltas = [
                abs(diff.delta) for diff in result.diffs
                if diff.delta is not None
            ]
            rows.append({
                "Case": result.name,
                "Policy": result.policy_number,
                "Current": result.current.status,
                "Guaranteed": result.guaranteed.status,
                "Diff Count": len(result.diffs),
                "Largest Delta": max(numeric_deltas, default=0.0),
                "Error": result.error,
            })
        return pd.DataFrame(rows, columns=(
            "Case", "Policy", "Current", "Guaranteed", "Diff Count",
            "Largest Delta", "Error"))

    @staticmethod
    def _diff_frame(diffs) -> pd.DataFrame:
        return pd.DataFrame([{
            "Case": diff.case_name,
            "Basis": diff.basis.title(),
            "Date": diff.date,
            "Year": diff.year,
            "Month": diff.month,
            "Field": diff.field,
            "Expected": diff.expected,
            "Actual": diff.actual,
            "Delta": diff.delta,
            "Tolerance": diff.tolerance,
        } for diff in diffs], columns=(
            "Case", "Basis", "Date", "Year", "Month", "Field",
            "Expected", "Actual", "Delta", "Tolerance"))

    def _populate_run(self):
        frame = self._summary_frame()
        self.case_grid.set_dataframe(frame, limit_rows=False)
        self.case_grid.set_numeric_formatting(
            default_decimals=2, column_decimals={"Diff Count": 0})
        self.case_grid.autofit_columns_to_data()
        selection_model = self.case_grid.table_view.selectionModel()
        if selection_model is not None:
            selection_model.selectionChanged.connect(self._on_case_selection)
        self.diff_grid.set_dataframe(
            self._diff_frame(self._run.diffs if self._run else []),
            limit_rows=False)
        self.diff_grid.set_numeric_formatting(default_decimals=6)
        self.diff_grid.autofit_columns_to_data()

    def _on_case_selection(self, selected=None, deselected=None):
        names = self._selected_case_names()
        diffs = [
            diff for result in self._run.cases for diff in result.diffs
            if not names or result.name in names
        ] if self._run else []
        self.diff_grid.set_dataframe(self._diff_frame(diffs), limit_rows=False)
        self.diff_grid.set_numeric_formatting(default_decimals=6)
        self.diff_grid.autofit_columns_to_data()

    def _selected_case_names(self) -> set[str]:
        model = self.case_grid.table_view.selectionModel()
        if model is None or self.case_grid.df is None:
            return set()
        return {
            str(self.case_grid.df.iloc[index.row()]["Case"])
            for index in model.selectedRows()
            if 0 <= index.row() < len(self.case_grid.df)
        }

    def _on_update_baseline(self):
        if self._suite is None or self._run is None:
            return
        candidates = self._run.candidate_rows
        selected_names = self._selected_case_names()
        eligible = [
            result.case_id for result in self._run.cases
            if result.case_id in candidates
            and (not selected_names or result.name in selected_names)
        ]
        if not eligible:
            QMessageBox.information(
                self, "Update Baseline",
                "No selected cases have complete current and guaranteed results.")
            return
        diff_count = sum(
            len(result.diffs) for result in self._run.cases
            if result.case_id in eligible)
        action = "Create" if self._suite.active is None else "Replace"
        answer = QMessageBox.question(
            self, "Update Baseline",
            f"{action} the baseline from the latest run for "
            f"{len(eligible)} case(s)?\n\n{diff_count} displayed differences "
            "will be accepted for those cases.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._suite = update_baseline(
                self._suite, candidates, eligible,
                provenance=self._audit_run.provenance)
            self._run = recompare_run(self._run, self._suite.active)
            self._populate_run()
            self._refresh_suite_label()
            self.progress_label.setText(
                f"Baseline updated to revision {self._suite.active.revision}.")
        except Exception as exc:
            QMessageBox.warning(self, "Update Baseline", str(exc))
        self._sync_actions()

    def _on_undo_baseline(self):
        if self._suite is None or self._suite.previous is None:
            return
        answer = QMessageBox.question(
            self, "Undo Baseline Update",
            f"Restore baseline revision {self._suite.previous.revision}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._suite = undo_baseline_update(self._suite)
            if self._run is not None:
                self._run = recompare_run(self._run, self._suite.active)
                self._populate_run()
            self._refresh_suite_label()
            self.progress_label.setText(
                f"Restored baseline revision {self._suite.active.revision}.")
        except Exception as exc:
            QMessageBox.warning(self, "Undo Baseline Update", str(exc))
        self._sync_actions()

    def _on_export_result(self):
        if self._suite is None or self._audit_run is None:
            return
        suggested = f"{self._suite.name} {self._audit_run.completed_at[:10]}{RESULT_SUFFIX}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Regression Result", suggested,
            f"SuiteView Regression Result (*{RESULT_SUFFIX})")
        if not path:
            return
        try:
            saved = save_run_result(self._suite, self._audit_run, path)
            self.progress_label.setText(f"Exported result: {saved}")
        except Exception as exc:
            QMessageBox.warning(self, "Export Regression Result", str(exc))

    def _on_excel(self):
        if self._run is None:
            return
        try:
            from suiteview.core.excel_export import (
                ExcelExportError, dump_to_new_workbook, write_table,
            )
            summary = self._summary_frame()
            excel, workbook, sheet = dump_to_new_workbook(
                list(summary.columns), summary.itertuples(index=False, name=None),
                sheet_name="Run Summary", text_col_indexes=(1, 2))
            differences = self._diff_frame(self._run.diffs)
            diff_sheet = workbook.Worksheets.Add(After=workbook.Worksheets(workbook.Worksheets.Count))
            diff_sheet.Name = "Differences"
            write_table(
                diff_sheet, list(differences.columns),
                differences.itertuples(index=False, name=None),
                text_col_indexes=(1, 2))
            for basis in ("current", "guaranteed"):
                rows = []
                for result in self._run.cases:
                    basis_result = getattr(result, basis)
                    rows.extend((result.name, result.policy_number, *(
                        row[column] for column in ALL_COLUMNS))
                        for row in basis_result.rows)
                values_sheet = workbook.Worksheets.Add(
                    After=workbook.Worksheets(workbook.Worksheets.Count))
                values_sheet.Name = f"{basis.title()} Values"
                write_table(
                    values_sheet, ["Case", "Policy", *ALL_COLUMNS], rows,
                    text_col_indexes=(1, 2))
            sheet.Activate()
            excel.ScreenUpdating = True
        except ExcelExportError as exc:
            QMessageBox.warning(self, "Excel Error", str(exc))
        except Exception as exc:
            logger.error("Regression Excel export failed: %s", exc, exc_info=True)
            QMessageBox.warning(self, "Excel Error", str(exc))
