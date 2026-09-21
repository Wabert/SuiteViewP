"""Compact standalone base/rider and field-value lookups."""
from __future__ import annotations

import logging
from typing import Callable

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from suiteview.core.excel_export import ExcelExportError, dump_to_new_workbook
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.ui.widgets.uppercase_input import force_uppercase
from ..other_queries import LookupKind, OtherQuery, build_other_query, execute_other_query
from ..query_runner import format_query_error, run_query_async
from ._styles import make_checkbox

logger = logging.getLogger(__name__)
_FONT = QFont("Segoe UI", 9)


class OtherQueryPanel(QWidget):
    sql_requested = pyqtSignal(str)

    def __init__(self, kind: LookupKind, region: Callable[[], str], parent=None):
        super().__init__(parent)
        self.kind = kind
        self._region = region
        self._revision = 0
        self._active_query_worker = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)
        title = QLabel({
            "riders": "Riders on a Base Plan", "bases": "Base Plans with a Rider",
            "values": "Field Values",
        }[kind])
        title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title.setStyleSheet("color: #1E5BA8;")
        root.addWidget(title)

        self.controls = QWidget()
        form = QHBoxLayout(self.controls)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(5)
        self.inputs: dict[str, QLineEdit] = {}
        fields = (("table", "Table"), ("field", "Field")) if kind == "values" else (
            ("plancode", "Base Plancode" if kind == "riders" else "Rider Plancode"),
        )
        for name, text in fields:
            label = QLabel(text)
            label.setFont(_FONT)
            entry = QLineEdit()
            entry.setFont(_FONT)
            entry.setFixedHeight(22)
            entry.setMinimumWidth(70)
            entry.setMaximumWidth(160 if kind == "values" else 100)
            force_uppercase(entry)
            entry.textChanged.connect(self.invalidate)
            entry.returnPressed.connect(self.run)
            form.addWidget(label)
            form.addWidget(entry, 1)
            self.inputs[name] = entry
        self.show_policies = make_checkbox("Show policies")
        self.show_policies.setParent(self.controls)
        self.show_policies.toggled.connect(self.invalidate)
        if kind != "values":
            form.addWidget(self.show_policies)
        else:
            self.show_policies.hide()
            self.inputs["table"].setToolTip("Policy-record table name, without a schema (e.g. LH_BAS_POL).")
            self.inputs["field"].setToolTip("Column to group by. The table must have TCH_POL_ID.")
        form.addStretch()
        root.addWidget(self.controls)

        buttons = QHBoxLayout()
        buttons.setSpacing(5)
        self.btn_find = QPushButton({
            "riders": "Find all riders", "bases": "Find all base", "values": "Find all values",
        }[kind])
        self.btn_sql = QPushButton("View SQL")
        self.btn_excel = QPushButton("Excel")
        for button in (self.btn_find, self.btn_sql, self.btn_excel):
            button.setFont(_FONT)
            button.setFixedHeight(22)
            buttons.addWidget(button)
        buttons.addStretch()
        self.status = QLabel("")
        self.status.setFont(_FONT)
        root.addLayout(buttons)
        root.addWidget(self.status)

        self.table = FilterTableView(self)
        self.table.search_bar.hide()
        self.table.info_label.hide()
        self.table.layout().setSpacing(0)
        view = self.table.table_view
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.frozen_table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.setShowGrid(False)
        view.setAlternatingRowColors(False)
        view.verticalHeader().hide()
        view.verticalHeader().setMinimumSectionSize(16)
        view.verticalHeader().setDefaultSectionSize(16)
        view.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        view.horizontalHeader().setFixedHeight(20)
        view.horizontalHeader().setFont(QFont("Segoe UI", 8))
        view.setStyleSheet(
            "QTableView { background: white; border: 1px solid #A0C4E8; font-size: 9pt;"
            " selection-background-color: #D4E4F7; selection-color: black; outline: none; }"
            "QTableView::item { padding: 0px; border: none; }"
            "QTableView::item:selected { background-color: #D4E4F7; color: black; }"
            "QHeaderView::section { background: #E8E8E8; font-size: 8pt;"
            " padding: 0px 16px 0px 3px; border: none; }"
        )
        root.addWidget(self.table, 1)
        self.btn_find.clicked.connect(self.run)
        self.btn_sql.clicked.connect(self.view_sql)
        self.btn_excel.clicked.connect(self.export)
        self.btn_excel.setEnabled(False)
        if kind == "values":
            self.status.setToolTip(
                "Record Count counts records with a non-NULL TCH_POL_ID, not distinct policies."
            )
        else:
            self.status.setToolTip(
                "Rider Count includes every matching rider coverage occurrence, active or inactive."
            )
        self.invalidate()

    def query(self) -> OtherQuery:
        return build_other_query(
            self.kind, self._region(),
            show_policies=self.show_policies.isChecked(),
            **{name: entry.text().strip().upper() for name, entry in self.inputs.items()},
        )

    def invalidate(self, *_args):
        self._revision += 1
        columns = (
            ("Field Value", "Record Count") if self.kind == "values" else
            (("Base Plancode", "Base Form", "Rider Plancode", "Rider Form")
             if self.kind == "riders" else
             ("Rider Plancode", "Rider Form", "Base Plancode", "Base Form"))
            + (("Policy Number", "Company") if self.show_policies.isChecked() else ("Rider Count",))
        )
        self._set_results(pd.DataFrame(columns=columns))
        self.status.setText("Enter criteria, then Find.")
        self.btn_excel.setEnabled(False)

    def _set_results(self, df: pd.DataFrame):
        self.table.set_dataframe(df, limit_rows=False)
        header = self.table.table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.autofit_columns_to_data()
        for index, column in enumerate(df.columns):
            minimum = header.fontMetrics().horizontalAdvance(str(column)) + 24
            self.table.table_view.setColumnWidth(index, max(header.sectionSize(index), minimum))
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.btn_excel.setEnabled(not df.empty)

    def view_sql(self):
        try:
            query = self.query()
        except ValueError as exc:
            QMessageBox.warning(self, "Other Queries", str(exc))
            return
        self.sql_requested.emit(query.display_sql())

    def run(self):
        if self._active_query_worker is not None:
            return
        try:
            query = self.query()
        except ValueError as exc:
            QMessageBox.warning(self, "Other Queries", str(exc))
            return
        region = self._region()
        self.invalidate()
        revision = self._revision
        self.status.setText(f"Running in {region}...")

        def success(df):
            if revision != self._revision:
                self.status.setText("Criteria or region changed; run again.")
                return
            self._set_results(df)
            self.status.setText(f"{region}: {len(df):,} rows" if not df.empty else f"{region}: No matches.")

        def failure(exc):
            logger.error("Other Queries %s failed: %s", self.kind, exc)
            self.status.setText(f"{region}: Query failed.")
            QMessageBox.warning(self, "Other Queries Error", format_query_error(exc))

        run_query_async(
            owner=self, work=lambda: execute_other_query(query, region),
            on_success=success, on_error=failure, btn=self.btn_find,
            restore_text=self.btn_find.text(),
            on_busy=lambda busy: self.controls.setEnabled(not busy),
        )

    def export(self):
        df = self.table.get_filtered_dataframe()
        if df.empty:
            QMessageBox.information(self, "Export to Excel", "There is no data to export.")
            return
        rows = [
            tuple(None if pd.isna(value) else value if isinstance(value, (str, int, float, bool)) else str(value)
                  for value in row)
            for row in df.itertuples(index=False, name=None)
        ]
        try:
            dump_to_new_workbook(
                list(df.columns), rows, sheet_name=f"Other Queries - {self.kind}",
                text_col_indexes=[i + 1 for i, col in enumerate(df.columns)
                                  if col not in ("Rider Count", "Record Count")],
            )
        except ExcelExportError as exc:
            logger.exception("Other Queries Excel export failed")
            QMessageBox.warning(self, "Excel Error", str(exc))

    def get_state(self) -> dict:
        return {**{name: entry.text() for name, entry in self.inputs.items()},
                "show_policies": self.show_policies.isChecked()}

    def set_state(self, state: dict):
        for name, entry in self.inputs.items():
            entry.setText(state.get(name, ""))
        self.show_policies.setChecked(state.get("show_policies", False))
        self.invalidate()


class OtherQueriesTab(QWidget):
    sql_requested = pyqtSignal(str)

    def __init__(self, region: Callable[[], str], parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 4)
        root.setSpacing(5)
        note = QLabel(
            "Standalone lookups use Region only, not main criteria, Sys Code or Max Count. "
            "Use each panel's Find button."
        )
        note.setFont(_FONT)
        note.setWordWrap(True)
        root.addWidget(note)
        content = QHBoxLayout()
        content.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(10)
        self.panels: dict[LookupKind, OtherQueryPanel] = {
            kind: OtherQueryPanel(kind, region) for kind in ("riders", "bases", "values")
        }
        left.addWidget(self.panels["riders"], 1)
        left.addWidget(self.panels["bases"], 1)
        content.addLayout(left, 3)
        content.addWidget(self.panels["values"], 2)
        root.addLayout(content, 1)
        for panel in self.panels.values():
            panel.sql_requested.connect(self.sql_requested)

    def is_busy(self) -> bool:
        return any(panel._active_query_worker is not None for panel in self.panels.values())

    def invalidate(self, *_args):
        for panel in self.panels.values():
            panel.invalidate()

    def get_state(self) -> dict:
        return {kind: panel.get_state() for kind, panel in self.panels.items()}

    def set_state(self, state: dict):
        for kind, panel in self.panels.items():
            panel.set_state(state.get(kind, {}))
