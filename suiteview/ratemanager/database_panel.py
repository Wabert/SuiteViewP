"""Rate Manager screen for loading workups and maintaining UL_Rates data."""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any, Callable, Optional

import pandas as pd
from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from suiteview.ratemanager.database_loader import (
    LoadAction,
    PackageAnalysis,
    TABLE_SPECS,
    TableAnalysis,
    TableData,
    ULRatesRepository,
    WorkupPackage,
    analyze_package,
    create_execution_plan,
    delete_pointer_rows,
    delete_rate_index,
    display_value,
    execute_package,
    load_pointer_rows,
    load_rate_index,
    update_pointer_row,
)
from suiteview.ratemanager.rm_styles import (
    BG_INPUT,
    BORDER,
    GOLD_TEXT,
    TEXT,
    TEXT_MID,
    body_stylesheet,
)
from suiteview.ui.widgets.filter_table_view import FilterTableView


_STATUS_OK = "#8ED081"
_STATUS_WARN = "#FFD166"
_STATUS_BAD = "#FF7B7B"


class _FunctionWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, function: Callable, *args, with_progress: bool = False):
        super().__init__()
        self._function = function
        self._args = args
        self._with_progress = with_progress

    def run(self) -> None:
        try:
            args = self._args
            if self._with_progress:
                args = (*args, self.progress.emit)
            self.result_ready.emit(self._function(*args))
        except Exception as exc:
            self.failed.emit(str(exc))


def _analyze_job(folder: str, dsn: str):
    package = WorkupPackage.load(folder)
    repository = ULRatesRepository(dsn)
    try:
        database_name = repository.test_connection()
        analysis = analyze_package(package, repository)
        return package, analysis, database_name
    finally:
        repository.close()


def _test_connection_job(dsn: str) -> str:
    repository = ULRatesRepository(dsn)
    try:
        return repository.test_connection()
    finally:
        repository.close()


def _records_dataframe(data: TableData) -> pd.DataFrame:
    return pd.DataFrame(data.to_records(), columns=data.spec.columns)


def _configure_table(table: FilterTableView, *, multi_row: bool = False) -> None:
    for view in (table.table_view, table.frozen_table_view):
        view.setShowGrid(False)
        view.setAlternatingRowColors(False)
        view.verticalHeader().setVisible(False)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
            if multi_row else QAbstractItemView.SelectionMode.SingleSelection
        )
    table.search_bar.setVisible(True)


class _TableLoadControl:
    def __init__(self, table_name: str):
        self.table_name = table_name
        spec = TABLE_SPECS[table_name]

        self.include = QCheckBox()
        self.include.setObjectName("BenefitCheck")
        self.include.setToolTip(f"Include {table_name} in this transaction.")

        self.name = QLabel(table_name)
        self.name.setStyleSheet(
            f"color: {GOLD_TEXT}; font-weight: bold; font-size: 12px;"
        )

        self.action = QComboBox()
        self.action.addItem("Insert New", LoadAction.INSERT.value)
        self.action.addItem(
            "Replace Plancode" if spec.is_pointer else "Replace Owned Indexes",
            LoadAction.REPLACE.value,
        )
        self.action.setMinimumWidth(165)

        self.rows = QLabel("—")
        self.rows.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.rows.setStyleSheet(f"color: {TEXT};")
        self.rows.setMinimumWidth(80)

        self.status = QLabel("Not analyzed")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {TEXT_MID};")

    def selected_action(self) -> LoadAction:
        if not self.include.isChecked():
            return LoadAction.SKIP
        return LoadAction(self.action.currentData())

    def set_status(self, text: str, color: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color};")


class WorkupDatabaseLoadTab(QWidget):
    """Analyze and atomically load one generated workup folder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._package: Optional[WorkupPackage] = None
        self._analysis: Optional[PackageAnalysis] = None
        self._plan = None
        self._workers: set[_FunctionWorker] = set()
        self._controls: dict[str, _TableLoadControl] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        subtitle = QLabel(
            "Review every collision before writing. Existing plancode data and "
            "different rate indexes require an explicit Replace action; indexes "
            "used by another plancode are never replaceable."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        connection_row = QHBoxLayout()
        connection_row.addWidget(self._section_label("UL_Rates DSN"))
        self.dsn_edit = QLineEdit("UL_Rates")
        self.dsn_edit.setFixedWidth(180)
        connection_row.addWidget(self.dsn_edit)
        self.test_btn = self._button("Test Connection", self._test_connection)
        connection_row.addWidget(self.test_btn)
        self.connection_status = QLabel("")
        self.connection_status.setStyleSheet(f"color: {TEXT_MID};")
        connection_row.addWidget(self.connection_status, 1)
        layout.addLayout(connection_row)

        folder_row = QHBoxLayout()
        folder_row.addWidget(self._section_label("Workup Folder"))
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(
            r"Select the generated <Plancode>_Workup CSV folder"
        )
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self._button("Browse...", self._browse_folder))
        self.analyze_btn = self._button("Analyze Database", self._start_analysis)
        self.analyze_btn.setObjectName("PrimaryBtn")
        folder_row.addWidget(self.analyze_btn)
        layout.addLayout(folder_row)

        self.package_status = QLabel("No workup analyzed.")
        self.package_status.setObjectName("FilePreview")
        layout.addWidget(self.package_status)

        action_frame = QFrame()
        action_frame.setStyleSheet(
            f"QFrame {{ background: {BG_INPUT}; border: 1px solid {BORDER}; "
            "border-radius: 4px; }"
        )
        grid = QGridLayout(action_frame)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        for column, heading in enumerate(
            ("Load", "Table", "Action", "File Rows", "Database Analysis")
        ):
            label = QLabel(heading)
            label.setStyleSheet(
                f"color: {TEXT_MID}; font-size: 11px; font-weight: bold;"
            )
            grid.addWidget(label, 0, column)

        for row_number, table_name in enumerate(TABLE_SPECS, start=1):
            control = _TableLoadControl(table_name)
            self._controls[table_name] = control
            grid.addWidget(control.include, row_number, 0)
            grid.addWidget(control.name, row_number, 1)
            grid.addWidget(control.action, row_number, 2)
            grid.addWidget(control.rows, row_number, 3)
            grid.addWidget(control.status, row_number, 4)
            control.include.toggled.connect(self._refresh_plan)
            control.action.currentIndexChanged.connect(self._refresh_plan)
        grid.setColumnStretch(4, 1)
        layout.addWidget(action_frame)

        preview_row = QHBoxLayout()
        preview_row.addWidget(self._section_label("Workup Preview"))
        self.preview_combo = QComboBox()
        self.preview_combo.addItems(TABLE_SPECS.keys())
        self.preview_combo.currentTextChanged.connect(self._refresh_preview)
        preview_row.addWidget(self.preview_combo)
        self.preview_source_combo = QComboBox()
        self.preview_source_combo.addItem("Workup Rows", "workup")
        self.preview_source_combo.addItem("Existing Database Rows", "database")
        self.preview_source_combo.currentIndexChanged.connect(
            self._refresh_preview
        )
        preview_row.addWidget(self.preview_source_combo)
        self.preview_status = QLabel("")
        self.preview_status.setStyleSheet(f"color: {TEXT_MID};")
        preview_row.addWidget(self.preview_status, 1)
        layout.addLayout(preview_row)

        self.preview_table = FilterTableView()
        _configure_table(self.preview_table)
        self.preview_table.set_dataframe(pd.DataFrame())
        layout.addWidget(self.preview_table, 1)

        bottom = QHBoxLayout()
        self.log = QTextEdit()
        self.log.setObjectName("LogArea")
        self.log.setReadOnly(True)
        self.log.setFixedHeight(72)
        bottom.addWidget(self.log, 1)
        self.apply_btn = self._button(
            "Apply Selected Changes", self._confirm_apply
        )
        self.apply_btn.setObjectName("PrimaryBtn")
        self.apply_btn.setEnabled(False)
        bottom.addWidget(self.apply_btn)
        layout.addLayout(bottom)
        self.folder_edit.textChanged.connect(self._invalidate_analysis)
        self.dsn_edit.textChanged.connect(self._invalidate_analysis)

    def set_workup_folder(self, folder: str) -> None:
        if os.path.isdir(folder):
            self.folder_edit.setText(folder)
            self.package_status.setText(
                "Workup ready for database analysis. No database write has occurred."
            )

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def _button(self, text: str, callback: Callable) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("SecondaryBtn")
        button.clicked.connect(callback)
        return button

    def _dsn(self) -> str:
        return self.dsn_edit.text().strip() or "UL_Rates"

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Rate Workup Folder"
        )
        if folder:
            self.set_workup_folder(folder)

    def _set_busy(self, busy: bool) -> None:
        self.analyze_btn.setEnabled(not busy)
        self.test_btn.setEnabled(not busy)
        self.apply_btn.setEnabled(False if busy else self._can_apply())

    def _invalidate_analysis(self) -> None:
        if self._analysis is None:
            self.apply_btn.setEnabled(False)
            return
        self._package = None
        self._analysis = None
        self._plan = None
        self.package_status.setText(
            "Folder or DSN changed. Analyze again before loading."
        )
        for control in self._controls.values():
            control.set_status("Analyze required", _STATUS_WARN)
        self.preview_table.set_dataframe(pd.DataFrame())
        self.preview_status.setText("")
        self.apply_btn.setEnabled(False)

    def _test_connection(self) -> None:
        self._set_busy(True)
        self.connection_status.setText("Connecting...")
        self._run_worker(
            _test_connection_job, (self._dsn(),), self._on_connection_tested
        )

    def _on_connection_tested(self, database_name: str) -> None:
        self._set_busy(False)
        self.connection_status.setText(
            f"Connected to {database_name} through {self._dsn()}."
        )
        self.connection_status.setStyleSheet(f"color: {_STATUS_OK};")

    def _start_analysis(self) -> None:
        folder = self.folder_edit.text().strip()
        if not os.path.isdir(folder):
            QMessageBox.warning(
                self, "Workup Folder Required",
                "Select a generated Rate Workup CSV folder first.",
            )
            return
        self._package = None
        self._analysis = None
        self._plan = None
        self.log.setPlainText("Reading the workup and checking UL_Rates...")
        self.package_status.setText("Analysis in progress...")
        self._set_busy(True)
        self._run_worker(
            _analyze_job, (folder, self._dsn()), self._on_analyzed
        )

    def _on_analyzed(self, result) -> None:
        self._package, self._analysis, database_name = result
        self._set_busy(False)
        self.connection_status.setText(
            f"Connected to {database_name} through {self._dsn()}."
        )
        self.connection_status.setStyleSheet(f"color: {_STATUS_OK};")
        self.package_status.setText(
            f"Plancode {self._package.plancode}  |  IssueVersion "
            f"{self._package.issue_version}  |  Database state captured for review"
        )
        for table_name, control in self._controls.items():
            row_count = len(self._package.tables[table_name].rows)
            control.rows.setText(f"{row_count:,}")
            control.include.blockSignals(True)
            control.include.setChecked(row_count > 0)
            control.include.blockSignals(False)
            control.action.blockSignals(True)
            control.action.setCurrentIndex(0)
            control.action.blockSignals(False)
        self._refresh_preview()
        self._refresh_plan()
        self.log.setPlainText(
            "Analysis complete. Review every status and explicitly select "
            "Replace where required."
        )

    def _actions(self) -> dict[str, LoadAction]:
        return {
            table_name: control.selected_action()
            for table_name, control in self._controls.items()
        }

    def _refresh_plan(self) -> None:
        if self._package is None or self._analysis is None:
            self.apply_btn.setEnabled(False)
            return
        self._plan = create_execution_plan(
            self._package, self._analysis, self._actions()
        )
        issues_by_table: dict[str, list[str]] = defaultdict(list)
        for issue in self._plan.issues:
            issues_by_table[issue.table_name].append(issue.message)

        for table_name, control in self._controls.items():
            action = control.selected_action()
            table_analysis = self._analysis.tables[table_name]
            if action == LoadAction.SKIP:
                if table_analysis.blocked_indexes:
                    control.set_status(
                        "Skipped; cross-plancode index collision exists.",
                        _STATUS_WARN,
                    )
                elif table_analysis.different_indexes:
                    control.set_status(
                        f"Skipped; {len(table_analysis.different_indexes):,} "
                        "index(es) differ from the workup.",
                        _STATUS_WARN,
                    )
                else:
                    control.set_status("Skipped", TEXT_MID)
            elif table_analysis.blocked_indexes:
                details = "; ".join(
                    f"{index}: {', '.join(plancodes)}"
                    for index, plancodes in sorted(
                        table_analysis.blocked_indexes.items()
                    )
                )
                control.set_status(
                    f"BLOCKED cross-plancode collision ({details}).",
                    _STATUS_BAD,
                )
            elif issues_by_table[table_name]:
                control.set_status(
                    "BLOCKED: " + " ".join(issues_by_table[table_name]),
                    _STATUS_BAD,
                )
            else:
                control.set_status(
                    self._ready_status(table_analysis, action), _STATUS_OK
                )
        self.apply_btn.setEnabled(self._can_apply())

    def _ready_status(
        self, analysis: TableAnalysis, action: LoadAction
    ) -> str:
        if analysis.is_pointer:
            if action == LoadAction.REPLACE and analysis.existing_rows:
                return (
                    f"Ready: replace {len(analysis.existing_rows):,} existing "
                    "plancode row(s)."
                )
            return "Ready: insert new pointer rows."

        parts = []
        if analysis.new_indexes:
            parts.append(f"{len(analysis.new_indexes):,} new index(es)")
        if analysis.identical_indexes:
            parts.append(
                f"{len(analysis.identical_indexes):,} identical index(es) reused"
            )
        if action == LoadAction.REPLACE and analysis.replaceable_indexes:
            parts.append(
                f"{len(analysis.replaceable_indexes):,} owned index(es) replaced"
            )
        return "Ready: " + (", ".join(parts) if parts else "no row changes")

    def _can_apply(self) -> bool:
        return bool(
            self._plan
            and self._plan.is_safe
            and any(action != LoadAction.SKIP for action in self._actions().values())
        )

    def _refresh_preview(self) -> None:
        if self._package is None:
            self.preview_table.set_dataframe(pd.DataFrame())
            self.preview_status.setText("")
            return
        table_name = self.preview_combo.currentText()
        data = self._package.tables[table_name]
        source = self.preview_source_combo.currentData()
        if source == "database" and self._analysis is not None:
            data = TableData(
                data.spec, self._analysis.tables[table_name].existing_rows
            )
        self.preview_table.set_dataframe(_records_dataframe(data))
        shown = min(len(data.rows), 50_000)
        suffix = " (display limited to 50,000)" if len(data.rows) > shown else ""
        source_label = (
            "existing matching/colliding database"
            if source == "database"
            else "workup"
        )
        self.preview_status.setText(
            f"{len(data.rows):,} {source_label} row(s){suffix}"
        )

    def _confirm_apply(self) -> None:
        if not self._can_apply() or self._package is None or self._analysis is None:
            return
        typed, accepted = QInputDialog.getText(
            self,
            "Confirm UL_Rates Update",
            "All selected changes run in one transaction and replaced rows are "
            f"backed up first.\n\nType {self._package.plancode} to continue:",
        )
        if not accepted:
            return
        if typed.strip() != self._package.plancode:
            QMessageBox.warning(
                self, "Confirmation Did Not Match",
                "The plancode did not match. No database changes were made.",
            )
            return

        actions = self._actions()
        signature = self._analysis.signature
        self._set_busy(True)
        self.log.setPlainText(
            "Rechecking the database inside the transaction before writing..."
        )
        self._run_worker(
            execute_package,
            (self._package, self._dsn(), actions, signature, None),
            self._on_applied,
            show_progress=True,
        )

    def _on_applied(self, result) -> None:
        self._set_busy(False)
        inserted = sum(result.inserted_rows.values())
        deleted = sum(result.deleted_rows.values())
        backup = result.backup_path or "No rows required backup"
        self.log.setPlainText(
            f"Committed and verified: {inserted:,} row(s) inserted, "
            f"{deleted:,} row(s) removed.\nBackup: {backup}"
        )
        QMessageBox.information(
            self,
            "UL_Rates Update Complete",
            f"The transaction committed successfully.\n\n"
            f"Inserted: {inserted:,} rows\nRemoved: {deleted:,} rows\n"
            f"Backup: {backup}",
        )
        self._start_analysis()

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self.log.setPlainText(f"ERROR: {message}")
        QMessageBox.critical(self, "Rate Database Error", message)

    def _run_worker(
        self,
        function: Callable,
        args: tuple,
        on_result: Callable,
        show_progress: bool = False,
    ) -> None:
        worker = _FunctionWorker(function, *args, with_progress=show_progress)
        self._workers.add(worker)
        worker.result_ready.connect(on_result)
        worker.failed.connect(self._on_error)
        if show_progress:
            worker.progress.connect(self.log.setPlainText)
        worker.finished.connect(
            lambda worker=worker: self._workers.discard(worker)
        )
        worker.start()


class _PointerEditDialog(QDialog):
    def __init__(self, data: TableData, row: tuple[Any, ...], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit {data.spec.name} Row")
        self._edits: list[QLineEdit] = []
        layout = QFormLayout(self)
        for column, value in zip(data.spec.columns, row):
            edit = QLineEdit(str(display_value(value)))
            if column in data.spec.integer_columns:
                edit.setValidator(QIntValidator(0, 2_147_483_647, edit))
            if column in data.spec.key_columns:
                edit.setToolTip("Key field")
            self._edits.append(edit)
            layout.addRow(column, edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[str, ...]:
        return tuple(edit.text() for edit in self._edits)


class ManageExistingTab(QWidget):
    """Edit pointer rows and delete only unreferenced whole rate indexes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers: set[_FunctionWorker] = set()
        self._pointer_data: Optional[TableData] = None
        self._rate_data: Optional[TableData] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        connection_row = QHBoxLayout()
        connection_row.addWidget(self._section_label("UL_Rates DSN"))
        self.dsn_edit = QLineEdit("UL_Rates")
        self.dsn_edit.setFixedWidth(180)
        connection_row.addWidget(self.dsn_edit)
        connection_row.addStretch()
        layout.addLayout(connection_row)

        note = QLabel(
            "Pointer rows can be edited or removed individually. Rate rows are "
            "never edited one-by-one: load an entire index group, and deletion "
            "is allowed only after all pointer references are gone."
        )
        note.setObjectName("Subtitle")
        note.setWordWrap(True)
        layout.addWidget(note)

        tabs = QTabWidget()
        tabs.addTab(self._build_pointer_tab(), "Pointer Rows")
        tabs.addTab(self._build_rate_tab(), "Rate Index Groups")
        layout.addWidget(tabs, 1)

        self.operation_status = QLabel("")
        self.operation_status.setStyleSheet(f"color: {TEXT_MID};")
        self.operation_status.setWordWrap(True)
        layout.addWidget(self.operation_status)

    def _build_pointer_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        controls = QHBoxLayout()
        controls.addWidget(self._section_label("Table"))
        self.pointer_table_combo = QComboBox()
        self.pointer_table_combo.addItems(("POINT_PVSRB", "POINT_BENEFIT"))
        controls.addWidget(self.pointer_table_combo)
        controls.addWidget(self._section_label("Plancode"))
        self.pointer_plan_edit = QLineEdit()
        self.pointer_plan_edit.setFixedWidth(150)
        self.pointer_plan_edit.returnPressed.connect(self._load_pointers)
        controls.addWidget(self.pointer_plan_edit)
        controls.addWidget(self._button("Load", self._load_pointers))
        controls.addStretch()
        self.edit_pointer_btn = self._button(
            "Edit Selected", self._edit_pointer
        )
        self.delete_pointer_btn = self._button(
            "Delete Selected", self._delete_pointers
        )
        self.edit_pointer_btn.setEnabled(False)
        self.delete_pointer_btn.setEnabled(False)
        controls.addWidget(self.edit_pointer_btn)
        controls.addWidget(self.delete_pointer_btn)
        layout.addLayout(controls)

        self.pointer_view = FilterTableView()
        _configure_table(self.pointer_view, multi_row=True)
        self.pointer_view.set_dataframe(pd.DataFrame())
        layout.addWidget(self.pointer_view, 1)
        return tab

    def _build_rate_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        controls = QHBoxLayout()
        controls.addWidget(self._section_label("Rate Table"))
        self.rate_table_combo = QComboBox()
        self.rate_table_combo.addItems(
            name for name, spec in TABLE_SPECS.items() if not spec.is_pointer
        )
        controls.addWidget(self.rate_table_combo)
        controls.addWidget(self._section_label("Index"))
        self.rate_index_edit = QLineEdit()
        self.rate_index_edit.setValidator(
            QIntValidator(1, 2_147_483_647, self.rate_index_edit)
        )
        self.rate_index_edit.setFixedWidth(120)
        self.rate_index_edit.returnPressed.connect(self._load_rate_index)
        controls.addWidget(self.rate_index_edit)
        controls.addWidget(self._button("Load Index", self._load_rate_index))
        controls.addStretch()
        self.delete_rate_btn = self._button(
            "Delete Entire Index", self._delete_rate_index
        )
        self.delete_rate_btn.setEnabled(False)
        controls.addWidget(self.delete_rate_btn)
        layout.addLayout(controls)

        self.rate_view = FilterTableView()
        _configure_table(self.rate_view)
        self.rate_view.set_dataframe(pd.DataFrame())
        layout.addWidget(self.rate_view, 1)
        return tab

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def _button(self, text: str, callback: Callable) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("SecondaryBtn")
        button.clicked.connect(callback)
        return button

    def _dsn(self) -> str:
        return self.dsn_edit.text().strip() or "UL_Rates"

    def _load_pointers(self) -> None:
        plancode = self.pointer_plan_edit.text().strip()
        if not plancode:
            QMessageBox.warning(
                self, "Plancode Required", "Enter a plancode to load."
            )
            return
        table_name = self.pointer_table_combo.currentText()
        self.operation_status.setText(f"Loading {table_name}...")
        self._run_worker(
            load_pointer_rows,
            (self._dsn(), table_name, plancode),
            self._on_pointers_loaded,
        )

    def _on_pointers_loaded(self, data: TableData) -> None:
        self._pointer_data = data
        self.pointer_view.set_dataframe(_records_dataframe(data))
        enabled = bool(data.rows)
        self.edit_pointer_btn.setEnabled(enabled)
        self.delete_pointer_btn.setEnabled(enabled)
        self.operation_status.setText(
            f"Loaded {len(data.rows):,} {data.spec.name} row(s)."
        )

    def _selected_pointer_rows(self) -> tuple[tuple[Any, ...], ...]:
        if self._pointer_data is None or self.pointer_view.model is None:
            return ()
        selection = self.pointer_view.table_view.selectionModel()
        selected = selection.selectedRows() if selection is not None else []
        display_data = self.pointer_view.model.get_display_data()
        source_indices = {
            int(display_data.index[index.row()])
            for index in selected if 0 <= index.row() < len(display_data)
        }
        return tuple(
            self._pointer_data.rows[index] for index in sorted(source_indices)
        )

    def _edit_pointer(self) -> None:
        selected = self._selected_pointer_rows()
        if len(selected) != 1 or self._pointer_data is None:
            QMessageBox.warning(
                self, "Select One Row", "Select exactly one pointer row to edit."
            )
            return
        dialog = _PointerEditDialog(self._pointer_data, selected[0], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        reply = QMessageBox.question(
            self,
            "Save Pointer Change?",
            "The current row will be backed up before this transactional update. "
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._run_worker(
            update_pointer_row,
            (
                self._dsn(),
                self._pointer_data.spec.name,
                selected[0],
                dialog.values(),
            ),
            self._on_pointer_changed,
        )

    def _delete_pointers(self) -> None:
        selected = self._selected_pointer_rows()
        if not selected or self._pointer_data is None:
            QMessageBox.warning(
                self, "Select Rows", "Select one or more pointer rows to delete."
            )
            return
        reply = QMessageBox.question(
            self,
            "Delete Pointer Rows?",
            f"Back up and delete {len(selected):,} selected "
            f"{self._pointer_data.spec.name} row(s)?\n\n"
            "Rate index rows are not deleted automatically.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._run_worker(
            delete_pointer_rows,
            (self._dsn(), self._pointer_data.spec.name, selected),
            self._on_pointer_changed,
        )

    def _on_pointer_changed(self, backup_path: str) -> None:
        self.operation_status.setText(
            f"Pointer transaction committed. Backup: {backup_path}"
        )
        self._load_pointers()

    def _load_rate_index(self) -> None:
        text = self.rate_index_edit.text().strip()
        if not text:
            QMessageBox.warning(
                self, "Index Required", "Enter a rate index to load."
            )
            return
        table_name = self.rate_table_combo.currentText()
        self.operation_status.setText(
            f"Loading {table_name} index {text}..."
        )
        self._run_worker(
            load_rate_index,
            (self._dsn(), table_name, int(text)),
            self._on_rate_loaded,
        )

    def _on_rate_loaded(self, data: TableData) -> None:
        self._rate_data = data
        self.rate_view.set_dataframe(_records_dataframe(data))
        self.delete_rate_btn.setEnabled(bool(data.rows))
        self.operation_status.setText(
            f"Loaded {len(data.rows):,} {data.spec.name} row(s). "
            "Deletion will recheck pointer references inside the transaction."
        )

    def _delete_rate_index(self) -> None:
        if self._rate_data is None or not self._rate_data.rows:
            return
        index = self._rate_data.spec.index_value(self._rate_data.rows[0])
        reply = QMessageBox.question(
            self,
            "Delete Entire Rate Index?",
            f"Back up and delete all {len(self._rate_data.rows):,} row(s) for "
            f"{self._rate_data.spec.name} index {index}?\n\n"
            "The operation is blocked if any pointer row still references it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._run_worker(
            delete_rate_index,
            (
                self._dsn(),
                self._rate_data.spec.name,
                int(index),
                self._rate_data.rows,
            ),
            self._on_rate_deleted,
        )

    def _on_rate_deleted(self, backup_path: str) -> None:
        self.operation_status.setText(
            f"Rate index transaction committed. Backup: {backup_path}"
        )
        self._rate_data = None
        self.rate_view.set_dataframe(pd.DataFrame())
        self.delete_rate_btn.setEnabled(False)

    def _on_error(self, message: str) -> None:
        self.operation_status.setText(f"ERROR: {message}")
        QMessageBox.critical(self, "Rate Database Error", message)

    def _run_worker(
        self, function: Callable, args: tuple, on_result: Callable
    ) -> None:
        worker = _FunctionWorker(function, *args)
        self._workers.add(worker)
        worker.result_ready.connect(on_result)
        worker.failed.connect(self._on_error)
        worker.finished.connect(
            lambda worker=worker: self._workers.discard(worker)
        )
        worker.start()


class RateDatabasePanel(QWidget):
    """Database loading and maintenance screen hosted by Rate Manager."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RateManagerBody")
        self.setStyleSheet(body_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.load_tab = WorkupDatabaseLoadTab()
        self.manage_tab = ManageExistingTab()
        self.load_tab.dsn_edit.textChanged.connect(self.manage_tab.dsn_edit.setText)
        self.manage_tab.dsn_edit.textChanged.connect(self.load_tab.dsn_edit.setText)
        self.tabs.addTab(self.load_tab, "Load Workup")
        self.tabs.addTab(self.manage_tab, "Manage Existing")
        layout.addWidget(self.tabs)

    def set_workup_folder(self, folder: str) -> None:
        self.tabs.setCurrentWidget(self.load_tab)
        self.load_tab.set_workup_folder(folder)
