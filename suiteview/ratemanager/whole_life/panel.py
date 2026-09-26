"""Whole Life source review and read-only database browsing.

Every repository is opened and closed inside its worker thread. No database
connection (or DDL) is attempted while constructing either screen.
"""

from __future__ import annotations

import logging
from functools import partial
from pathlib import Path
from typing import Callable

import pandas as pd
from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from suiteview.core.build_env import guard_data_writable, is_data_read_only
from suiteview.ratemanager.database_panel import _FunctionWorker
from suiteview.ratemanager.package import TableData
from suiteview.ratemanager.rm_styles import BG_DARK, TEXT, TEXT_MID, body_stylesheet
from suiteview.ratemanager.whole_life.service import (
    BROWSE_TABLES, SOURCE_KINDS, WholeLifeRepository, parse_workup,
)
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.ui.widgets.uppercase_input import UpperCaseValidator, force_uppercase

logger = logging.getLogger(__name__)

_IDENTIFIER_COLUMNS = frozenset({
    "USERID", "USERCODE", "USERKEY", "COMPANY", "COMPANYCODE",
    "PLANCODE", "PLANKEY", "PLANOPTION", "SEX", "RATECLASS", "BAND",
    "SOURCEKEY", "RATEKEY", "CVKEY", "NSPKEY", "PUIKEY", "DIVKEY", "CVDIVKEY",
    "HEADERID", "CLASS", "BASESERIES", "SUBSERIES",
})


def _is_identifier_column(column: str) -> bool:
    return column.replace("_", "").upper() in _IDENTIFIER_COLUMNS


def _logged_job(function: Callable, args: tuple):
    try:
        return function(*args)
    except Exception:
        name = function.func.__name__ if isinstance(function, partial) else function.__name__
        logger.exception("Whole Life %s failed", name)
        raise


def _analyze_job(package):
    with WholeLifeRepository() as repo:
        return repo.analyze(package)


def _apply_job(analysis, replace_tables):
    guard_data_writable("load Whole Life rates")
    with WholeLifeRepository() as repo:
        return repo.apply(analysis, replace_tables)


def _create_tables_job():
    guard_data_writable("create Whole Life tables")
    with WholeLifeRepository() as repo:
        return repo.create_tables()


def _columns_job(table):
    with WholeLifeRepository() as repo:
        return repo.columns(table)


def _browse_job(table, filters, limit):
    with WholeLifeRepository() as repo:
        return repo.columns(table), repo.browse(table, filters=filters, limit=limit)


def _label(text: str, *, note: bool = False) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("Subtitle" if note else "SectionLabel")
    return label


def _button(text, callback) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("SecondaryBtn")
    button.clicked.connect(callback)
    return button


def _grid(parent=None) -> FilterTableView:
    table = FilterTableView(parent)
    table.search_bar.setStyleSheet(f"QLabel {{ color: {TEXT_MID}; }}")
    table.info_label.setStyleSheet(
        f"color: {TEXT_MID}; font-size: 10px; padding: 2px;")
    for view in (table.table_view, table.frozen_table_view):
        view.setShowGrid(False)
        view.setAlternatingRowColors(False)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.verticalHeader().hide()
        view.verticalHeader().setMinimumSectionSize(16)
        view.verticalHeader().setDefaultSectionSize(16)
        view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        view.horizontalHeader().setFixedHeight(18)
        view.setStyleSheet(
            "QTableView { background: white; color: #202020; }"
            "QTableView::item { padding: 0px; border: none; }"
        )
    return table


def _show_rows(table: FilterTableView, rows, columns=None):
    table.set_dataframe(pd.DataFrame(rows, columns=columns), limit_rows=False)
    table.table_view.resizeColumnsToContents()
    header = table.table_view.horizontalHeader()
    header.setStretchLastSection(True)
    header.setFixedHeight(18)


class _AsyncPanel(QWidget):
    """Own workers until finished, and veto host-window close while they run."""

    busy_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._outcome = None
        self._on_success = None
        self._close_host = None
        self.setObjectName("RateManagerBody")
        self.setStyleSheet(body_stylesheet())

    @property
    def is_busy(self) -> bool:
        return self._worker is not None

    def _start_job(self, function, args, on_success, message):
        if self.is_busy:
            return
        self._outcome = None
        self._on_success = on_success
        worker = _FunctionWorker(_logged_job, function, args)
        worker.setParent(self)
        self._worker = worker
        worker.result_ready.connect(self._remember_result)
        worker.failed.connect(self._remember_error)
        worker.finished.connect(self._job_finished)
        self._close_host = self.window()
        if self._close_host is not self:
            self._close_host.installEventFilter(self)
        self.status.setText(message)
        self._update_controls()
        self.busy_changed.emit(True)
        worker.start()

    def _remember_result(self, result):
        self._outcome = (True, result)

    def _remember_error(self, error):
        self._outcome = (False, error)

    def _job_finished(self):
        worker = self._worker
        # QThread.finished can precede thread-local teardown. Keep ownership
        # and the close veto until wait() establishes that teardown completed.
        worker.wait()
        outcome = self._outcome
        callback = self._on_success
        self._worker = None
        self._on_success = None
        self._outcome = None
        if self._close_host is not self:
            self._close_host.removeEventFilter(self)
        self._close_host = None
        worker.deleteLater()
        try:
            if outcome is None:
                self._report_error("The background operation returned no result.")
            elif outcome[0]:
                callback(outcome[1])
            else:
                self._report_error(outcome[1])
        except Exception as exc:
            logger.exception("Could not display Whole Life operation result")
            self._report_error(str(exc))
        finally:
            self._update_controls()
            self.busy_changed.emit(False)

    def _report_error(self, message: str):
        self._invalidate_result_on_error()
        logger.error("Whole Life: %s", message)
        self.status.setText(f"Error: {message}")
        self._update_controls()
        QMessageBox.warning(self, "Whole Life", message)

    def _invalidate_result_on_error(self):
        pass

    def _update_controls(self):
        raise NotImplementedError

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Close and self.is_busy:
            self.status.setText("An operation is running. Wait before closing.")
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        if self.is_busy:
            self.status.setText("An operation is running. Wait before closing.")
            event.ignore()
            return
        super().closeEvent(event)


class WholeLifeWorkupPanel(_AsyncPanel):
    """Parse → preview → compare → explicitly approve changed-row updates."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._package = None
        self._analysis = None
        self._revision = 0
        self._approvals: dict[str, QCheckBox] = {}
        self.preview_tables: dict[str, FilterTableView] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)
        root.addWidget(_label(
            "Whole Life source workup · UL_Rates"))
        root.addWidget(_label(
            "Raw source rows, not a completed illustration engine. CV/NSP source "
            "keys and IAF option fields are preserved. CVF sign inference is an "
            "optional assumption, off by default.", note=True))

        self.source_controls = QWidget()
        source_layout = QVBoxLayout(self.source_controls)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(5)
        source_row = QHBoxLayout()
        source_row.addWidget(_label("Source files"), 1)
        self.infer_cvf_negatives_check = QCheckBox("Infer early negative CVs (assumption)")
        self.infer_cvf_negatives_check.setObjectName("BenefitCheck")
        self.infer_cvf_negatives_check.setStyleSheet(f"color: {TEXT}; font-size: 11px;")
        self.infer_cvf_negatives_check.setToolTip(
            "Assumption: requires a signed negative duration-zero header and a "
            "strict initial decline followed by a rise. Zero positive magnitudes "
            "BEFORE the first minimum; keep the minimum positive. Do not guess "
            "flat or unfinished declines, and never override explicit '+' values.")
        source_row.addWidget(self.infer_cvf_negatives_check)
        source_row.addWidget(_label("IAF company / user"))
        self.user_code_edit = QLineEdit()
        self.user_code_edit.setMaximumWidth(150)
        self.user_code_edit.setPlaceholderText("Required for IAF")
        self.user_code_edit.setToolTip(
            "Type the company/user code explicitly: it is not printed in the IAF.")
        force_uppercase(self.user_code_edit)
        source_row.addWidget(self.user_code_edit)
        source_layout.addLayout(source_row)
        self.source_edits: dict[str, QLineEdit] = {}
        self.source_buttons: dict[str, QPushButton] = {}
        for kind, label in (
            ("CVF", "CVF"), ("IAF", "IAF"), ("Dividend", "DIV"), ("PUI", "PUI"),
            ("NSP", "NSP CSV"), ("Dividend map", "DIV map"),
        ):
            row = QHBoxLayout()
            row.setSpacing(6)
            title = _label(label)
            title.setFixedWidth(64)
            title.setToolTip(SOURCE_KINDS[kind])
            row.addWidget(title)
            edit = QLineEdit()
            edit.setAccessibleName(f"{label} source files")
            edit.setPlaceholderText(f"{SOURCE_KINDS[kind]} (optional)")
            edit.setToolTip(
                f"{SOURCE_KINDS[kind]}\nPaste a path, or separate multiple paths with |. "
                "Browse can select multiple files. Leave blank to omit this source.")
            edit.setClearButtonEnabled(True)
            title.setBuddy(edit)
            row.addWidget(edit, 1)
            browse = _button("Browse…", lambda _checked=False, source=kind: self._select_files(source))
            browse.setAccessibleName(f"Browse {label} files")
            row.addWidget(browse)
            self.source_edits[kind] = edit
            self.source_buttons[kind] = browse
            edit.textChanged.connect(self._invalidate_source)
            source_layout.addLayout(row)
        source_layout.addWidget(_label(
            "Choose any combination of CVF, IAF, DIV and PUI; all selected files "
            "are reviewed and loaded together. NSP CSV and DIV map are optional.",
            note=True))
        root.addWidget(self.source_controls)

        actions = QHBoxLayout()
        self.parse_btn = _button("1  Parse / preview", self._parse)
        self.analyze_btn = _button("2  Analyze database", self._analyze)
        self.load_btn = _button("3  Load approved rows", self._load)
        self.load_btn.setObjectName("PrimaryBtn")
        for button in (self.parse_btn, self.analyze_btn, self.load_btn):
            actions.addWidget(button)
        actions.addStretch()
        root.addLayout(actions)
        self.counts_label = _label("Preview: first 100 rows of each parsed table.", note=True)
        root.addWidget(self.counts_label)
        self.preview_tabs = QTabWidget()
        root.addWidget(self.preview_tabs, 3)
        root.addWidget(_label(
            "Database comparison · new rows insert; unchanged rows skip; "
            "changed rows need approval for every affected table.", note=True))
        self.analysis_table = _grid()
        self.analysis_table.search_bar.hide()
        self.analysis_table.setMinimumHeight(85)
        self.analysis_table.setMaximumHeight(150)
        root.addWidget(self.analysis_table, 1)
        self.approval_area = QScrollArea()
        self.approval_area.setWidgetResizable(True)
        self.approval_area.setMaximumHeight(100)
        self.approval_area.setMinimumHeight(32)
        self.approval_area.setStyleSheet(
            f"QScrollArea {{ border: none; background: {BG_DARK}; }}")
        self.approval_content = QWidget()
        self.approval_content.setStyleSheet(f"background: {BG_DARK};")
        self.approval_layout = QVBoxLayout(self.approval_content)
        self.approval_layout.setContentsMargins(3, 2, 3, 2)
        self.approval_layout.setSpacing(2)
        self.approval_area.setWidget(self.approval_content)
        root.addWidget(self.approval_area)
        footer = QHBoxLayout()
        self.create_btn = _button("Create missing WL tables…", self._create_tables)
        self.create_btn.setToolTip(
            "Explicit setup only: the four new Whole Life rate tables. "
            "Existing dividend tables and CYBERLIFE_PDF are never recreated. "
            "Does not run automatically.")
        footer.addWidget(self.create_btn)
        footer.addWidget(_label(
            "CanUpdateDatabase permission is required to load or create tables."
            if is_data_read_only() else
            "Updates are backed up transactionally. No rows are deleted.",
            note=True), 1)
        root.addLayout(footer)
        self.status = _label("Select source files in one or more rows.", note=True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.status)
        self.user_code_edit.textChanged.connect(self._invalidate_source)
        self.infer_cvf_negatives_check.toggled.connect(self._invalidate_source)
        self._update_controls()

    def _selected_files(self) -> dict[str, list[str]]:
        return {
            kind: list(dict.fromkeys(
                path.strip().strip('"') for path in edit.text().split("|")
                if path.strip().strip('"')
            ))
            for kind, edit in self.source_edits.items()
        }

    def set_paths(self, kind: str, paths: list[str]):
        self.source_edits[kind].setText(" | ".join(dict.fromkeys(str(path) for path in paths)))

    def _select_files(self, kind: str):
        file_filter = (
            "Plan-key map workbooks (*.xlsx *.xlsm);;All files (*)"
            if kind == "Dividend map"
            else "Verified NSP CSV (*.csv);;All files (*)" if kind == "NSP"
            else "Source files (*.txt *.csv *.iaf *.dat *.prn);;All files (*)"
        )
        paths = self._selected_files()[kind]
        folder = str(Path(paths[0]).parent) if paths else ""
        paths, _ = QFileDialog.getOpenFileNames(
            self, f"Whole Life {kind} source files", folder, file_filter)
        if paths:
            self.set_paths(kind, paths)

    def _clear_analysis(self):
        self._analysis = None
        _show_rows(self.analysis_table, [])
        self._approvals.clear()
        while self.approval_layout.count():
            item = self.approval_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_preview(self):
        self._package = None
        self.preview_tables.clear()
        while self.preview_tabs.count():
            widget = self.preview_tabs.widget(0)
            self.preview_tabs.removeTab(0)
            widget.deleteLater()
        self.counts_label.setText("Preview: first 100 rows of each parsed table.")

    def _invalidate_source(self):
        self._revision += 1
        self._clear_preview()
        self._clear_analysis()
        self.status.setText("Inputs changed. Parse and analyze again before loading.")
        self._update_controls()

    def _invalidate_result_on_error(self):
        self._clear_analysis()

    def _update_controls(self):
        busy = self.is_busy
        self.source_controls.setEnabled(not busy)
        files = self._selected_files()
        self.user_code_edit.setEnabled(bool(files["IAF"]) and not busy)
        self.infer_cvf_negatives_check.setEnabled(bool(files["CVF"]) and not busy)
        ready = any(files.values()) and (
            not files["IAF"] or bool(self.user_code_edit.text().strip()))
        self.parse_btn.setEnabled(not busy and ready)
        self.analyze_btn.setEnabled(not busy and self._package is not None)
        approved = all(check.isChecked() for check in self._approvals.values())
        changes = self._analysis is not None and any(
            table.inserted or table.changed for table in self._analysis.tables)
        self.load_btn.setEnabled(
            not busy and not is_data_read_only() and bool(changes) and approved)
        self.create_btn.setEnabled(not busy and not is_data_read_only())
        self.approval_area.setEnabled(not busy and not is_data_read_only())

    def _parse(self):
        if self.is_busy:
            return
        self._clear_preview()
        self._clear_analysis()
        files = self._selected_files()
        code = self.user_code_edit.text().strip().upper()
        if not any(files.values()) or (files["IAF"] and not code):
            self._report_error(
                "Select source files. IAF premiums also require an explicit "
                "company/user code, which is not printed in the source.")
            return
        revision = self._revision
        infer_cvf_negatives = bool(files["CVF"]) and self.infer_cvf_negatives_check.isChecked()

        def parsed(package):
            if revision != self._revision:
                return
            self._package = package
            for name, data in package.tables.items():
                table = _grid()
                preview = TableData(data.spec, data.rows[:100])
                _show_rows(table, preview.to_records(), data.spec.columns)
                self.preview_tables[name] = table
                self.preview_tabs.addTab(table, f"{name} ({len(data.rows):,})")
            inferred_count = 0
            inference_enabled = False
            adjustments = []
            for source in package.sources:
                inference = source.get("cvf_inference", {})
                inference_enabled |= inference.get("enabled", False)
                inferred_count += inference.get("adjusted_rows", 0)
                adjustments.extend(
                    {"Source file": source["path"], **adjustment, "Rule": inference["rule"]}
                    for adjustment in inference.get("adjustments", ())
                )
            if adjustments:
                table = _grid()
                leading_columns = (
                    "USER_CODE", "RATE_KEY", "ISSUE_AGE", "DURATION",
                    "printed_rate", "loaded_rate", "minimum_duration", "minimum_rate",
                )
                metadata_columns = dict.fromkeys(
                    column for row in adjustments for column in row
                    if column not in leading_columns and column not in ("Source file", "Rule")
                )
                _show_rows(table, adjustments, [
                    *leading_columns, *metadata_columns, "Source file", "Rule",
                ])
                self.preview_tables["CVF inference"] = table
                index = self.preview_tabs.addTab(
                    table, f"CVF inference ({inferred_count:,})")
                self.preview_tabs.setTabToolTip(
                    index, "All inferred adjustments (not limited to 100 rows). "
                    "CVF sign inference is an assumption; review printed and loaded rates.")
            self.counts_label.setText(
                "First 100 rows / table · "
                + " · ".join(f"{name}: {count:,}" for name, count
                             in package.row_counts.items())
                + f" · CVF inferred rows: {inferred_count:,}"
                + (" (assumption; audit shows all)" if inference_enabled else " (off)"))
            self.status.setText(
                f"Parsed {len(package.sources)} source(s). Review the previews, "
                "then analyze the database.")

        self._start_job(
            partial(parse_workup, infer_cvf_negatives=infer_cvf_negatives),
            (files, code), parsed,
            "Parsing all selected source files…")

    def _analyze(self):
        if self.is_busy or self._package is None:
            return
        self._clear_analysis()
        revision = self._revision

        def analyzed(analysis):
            if revision != self._revision:
                return
            self._analysis = analysis
            _show_rows(self.analysis_table, analysis.summary_records())
            for table in analysis.tables:
                if not table.changed:
                    continue
                check = QCheckBox(
                    f"Approve updating {table.changed:,} changed row(s) in {table.table}")
                check.setObjectName("BenefitCheck")
                check.setStyleSheet(f"color: {TEXT}; font-size: 11px;")
                check.toggled.connect(self._update_controls)
                self._approvals[table.table] = check
                self.approval_layout.addWidget(check)
            self.status.setText(
                "Comparison ready. Approve each changed table before loading; "
                "new rows insert and unchanged rows are skipped.")

        self._start_job(_analyze_job, (self._package,), analyzed,
                        "Comparing against UL_Rates…")

    def _load(self):
        if self.is_busy:
            return
        if is_data_read_only():
            self._report_error("CanUpdateDatabase permission is required to load rates.")
            return
        analysis = self._analysis
        if analysis is None:
            self._report_error("Analyze the current inputs before loading.")
            return
        approved = {name for name, check in self._approvals.items()
                    if check.isChecked()}
        changed = {table.table for table in analysis.tables if table.changed}
        if not changed <= approved:
            self._report_error("Approve changed-row updates for every affected table.")
            return
        insert_count = sum(table.inserted for table in analysis.tables)
        update_count = sum(table.changed for table in analysis.tables)
        if not insert_count and not update_count:
            return
        inferences = [
            source["cvf_inference"] for source in analysis.package.sources
            if source.get("cvf_inference", {}).get("enabled")
        ]
        inference_warning = (
            "\nCVF sign inference is an assumption: "
            f"{sum(item['adjusted_rows'] for item in inferences):,} inferred row(s) "
            "will be loaded as 0.00. Review the CVF inference audit before proceeding.\n"
            if inferences else ""
        )
        answer = QMessageBox.question(
            self, "Confirm Whole Life load",
            f"Write to UL_Rates?\n\nInsert {insert_count:,} new row(s).\n"
            f"Update {update_count:,} explicitly approved changed row(s).\n"
            + ("Approved tables: " + ", ".join(sorted(approved)) + "\n"
               if approved else "")
            + inference_warning
            + "\nUnchanged rows are skipped. No rows are deleted. Existing "
            "rows are backed up before updates; the comparison is rechecked.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._clear_analysis()

        def loaded(result):
            inserted = sum(result["inserted"].values())
            updated = sum(result["updated"].values())
            self.status.setText(
                f"Loaded: {inserted:,} inserted, {updated:,} updated. "
                f"Receipt: {result['receipt']}. Analyze again before another load.")

        self._start_job(_apply_job, (analysis, approved), loaded,
                        "Loading approved rows in one transaction…")

    def _create_tables(self):
        if self.is_busy:
            return
        if is_data_read_only():
            self._report_error("CanUpdateDatabase permission is required to create tables.")
            return
        answer = QMessageBox.question(
            self, "Create missing Whole Life tables",
            "Create any missing Whole Life rate tables in UL_Rates?\n\n"
            "WL_RATE_CV · WL_RATE_NSP · WL_RATE_PUI · WL_RATE_PREM\n\n"
            "Existing tables and rows are left intact. Dividend tables, the "
            "plan-key map and CYBERLIFE_PDF are not created or modified. "
            "This is an explicit database schema change.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._clear_analysis()
        self._start_job(
            _create_tables_job, (),
            lambda tables: self.status.setText(
                "Created: " + ", ".join(tables) if tables
                else "All four Whole Life rate tables already exist; no schema changes."),
            "Creating missing Whole Life rate tables…")


class WholeLifeDatabasePanel(_AsyncPanel):
    """Read-only exact-filter browser, including CYBERLIFE_PDF metadata."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._revision = 0
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)
        root.addWidget(_label("Whole Life database · read-only"))
        root.addWidget(_label(
            "Browse raw Whole Life source rows or select CYBERLIFE_PDF for "
            "product metadata lookup. Read fields, then choose a column and "
            "an exact value (for example company or plan). No arbitrary SQL "
            "and no edits. These rows are not a completed illustration engine.",
            note=True))
        self.query_controls = QWidget()
        controls = QVBoxLayout(self.query_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        table_row = QHBoxLayout()
        table_row.addWidget(_label("Table"))
        self.table_combo = QComboBox()
        self.table_combo.addItems(BROWSE_TABLES)
        table_row.addWidget(self.table_combo, 1)
        self.columns_btn = _button("Read fields", self._read_columns)
        table_row.addWidget(self.columns_btn)
        table_row.addWidget(_label("Limit"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 10000)
        self.limit_spin.setValue(1000)
        table_row.addWidget(self.limit_spin)
        self.browse_btn = _button("Browse", self._browse)
        table_row.addWidget(self.browse_btn)
        controls.addLayout(table_row)
        self.filter_fields = []
        self.filter_values = []
        for index in range(2):
            row = QHBoxLayout()
            row.addWidget(_label("Exact filter" if index == 0 else "And"))
            field = QComboBox()
            field.addItem("No filter", "")
            value = QLineEdit()
            value.setPlaceholderText("Exact value (bound parameter, not SQL)")
            row.addWidget(field, 1)
            row.addWidget(value, 2)
            self.filter_fields.append(field)
            self.filter_values.append(value)
            field.currentIndexChanged.connect(self._filter_field_changed)
            value.textChanged.connect(self._invalidate_query)
            controls.addLayout(row)
        root.addWidget(self.query_controls)
        self.results = _grid()
        root.addWidget(self.results, 1)
        self.status = _label(
            "No database query has run. Choose a table, then Read fields or Browse.",
            note=True)
        root.addWidget(self.status)
        self.table_combo.currentIndexChanged.connect(self._table_changed)
        self.limit_spin.valueChanged.connect(self._invalidate_query)

    def _invalidate_query(self):
        self._revision += 1
        _show_rows(self.results, [])
        self.status.setText("Query changed. Click Browse to fetch current results.")

    def _sync_filter_validators(self):
        for field, value in zip(self.filter_fields, self.filter_values):
            validator = value.validator()
            if _is_identifier_column(field.currentData() or ""):
                if not isinstance(validator, UpperCaseValidator):
                    force_uppercase(value)
            elif isinstance(validator, UpperCaseValidator):
                value.setValidator(None)
                validator.deleteLater()

    def _filter_field_changed(self):
        self._sync_filter_validators()
        self._invalidate_query()

    def _table_changed(self):
        self._set_columns(())
        for value in self.filter_values:
            value.blockSignals(True)
            value.clear()
            value.blockSignals(False)
        self._invalidate_query()

    def _set_columns(self, columns):
        for field in self.filter_fields:
            selected = field.currentData()
            field.blockSignals(True)
            field.clear()
            field.addItem("No filter", "")
            for column in columns:
                field.addItem(column, column)
            index = field.findData(selected)
            field.setCurrentIndex(max(0, index))
            field.blockSignals(False)
        self._sync_filter_validators()

    def _update_controls(self):
        self.query_controls.setEnabled(not self.is_busy)

    def _invalidate_result_on_error(self):
        _show_rows(self.results, [])

    def _read_columns(self):
        if self.is_busy:
            return
        revision = self._revision

        def received(columns):
            if revision != self._revision:
                return
            self._set_columns(columns)
            self.status.setText(
                f"{len(columns)} fields available. Choose exact filters or "
                "browse without filters.")

        self._start_job(_columns_job, (self.table_combo.currentText(),), received,
                        "Reading table fields…")

    def _browse(self):
        if self.is_busy:
            return
        filters = {}
        for field, value in zip(self.filter_fields, self.filter_values):
            column = field.currentData()
            text = value.text()
            if not column:
                if text:
                    self._report_error("Choose a field for each entered filter value.")
                    return
                continue
            if column in filters:
                self._report_error("Choose different fields for the two filters.")
                return
            filters[column] = text.strip().upper() if _is_identifier_column(column) else text
        table = self.table_combo.currentText()
        limit = self.limit_spin.value()
        revision = self._revision
        _show_rows(self.results, [])

        def received(result):
            if revision != self._revision:
                return
            columns, rows = result
            self._set_columns(columns)
            _show_rows(self.results, rows, columns)
            self.status.setText(
                f"{table}: {len(rows):,} row(s) returned · limit {limit:,}"
                + (" reached; narrow the exact filters for more specific results."
                   if len(rows) == limit else "."))

        self._start_job(_browse_job, (table, filters, limit), received,
                        f"Reading {table}…")
