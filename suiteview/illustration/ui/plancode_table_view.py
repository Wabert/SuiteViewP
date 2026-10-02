"""Plancode Table viewer — a read-only RERUN window over ``plancode_table.json``.

Opened from the RERUN header's ☰ menu. Shows one row per plancode as stored in the
table (the same rows ``load_plancode`` reads): the product rules, plus a rate field
only where it is the fallback for a plan UL_Rates schema ``rates`` lacks it for, and
the explicit illustration age overrides. Rates the database supplies are not in the
table (see ``plancode_config``). A dense sortable/filterable ledger with the Plancode
column frozen, plus a Dump to Excel hand-off.
"""
from __future__ import annotations

import json
import logging
from numbers import Number

import pandas as pd
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models.plancode_config import (
    plancode_table_path,
    plancode_table_rows,
)
from suiteview.ui.widgets.filter_table_view import FilterTableView
from suiteview.ui.widgets.frameless_window import FramelessWindowBase

from .styles import (
    GOLD_TEXT,
    ILLUSTRATION_BORDER_COLOR,
    ILLUSTRATION_HEADER_COLORS,
    PURPLE_BG,
    PURPLE_DARK,
    PURPLE_PRIMARY,
)

logger = logging.getLogger(__name__)

WINDOW_TITLE = "SuiteView:  Plancode Table"
FROZEN_COLUMNS = ("Plancode",)


def _is_number(value) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _display_text(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def plancode_table_frame(rows: list[dict]) -> tuple[pd.DataFrame, set[str]]:
    """Build the viewer frame and the set of text (left-aligned) columns.

    Columns keep first-seen order across rows. A column whose present values
    are all numbers keeps them as-is (so ``100`` stays ``100`` and sorts
    numerically); any other column is rendered as text so mixed types still
    sort. Keys absent from a row stay missing (shown blank), never zero.
    """
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    data: dict[str, list] = {}
    text_columns: set[str] = set()
    for column in columns:
        values = [row.get(column) for row in rows]
        present = [value for value in values if value is not None]
        if present and all(_is_number(value) for value in present):
            data[column] = values
        else:
            data[column] = [_display_text(value) for value in values]
            text_columns.add(column)
    return pd.DataFrame(data, columns=columns, dtype=object), text_columns


class PlancodeTableWindow(FramelessWindowBase):
    """Read-only, filterable view of the illustration plancode table."""

    def __init__(self, parent=None):
        self._df = pd.DataFrame()
        self._text_columns: set[str] = set()
        super().__init__(
            title=WINDOW_TITLE,
            default_size=(1200, 700),
            min_size=(600, 360),
            parent=parent,
            header_colors=ILLUSTRATION_HEADER_COLORS,
            border_color=ILLUSTRATION_BORDER_COLOR,
        )
        self.reload()

    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 6, 8, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.summary_label = QLabel("", body)
        self.summary_label.setStyleSheet(
            f"background-color: {PURPLE_DARK}; color: {GOLD_TEXT};"
            f" border: 1px solid {PURPLE_PRIMARY}; border-radius: 4px;"
            " font-size: 11px; font-weight: bold; padding: 3px 9px;")
        top.addWidget(self.summary_label, 1)

        self.export_btn = QPushButton("Dump to Excel", body)
        self.export_btn.setToolTip(
            "Open the displayed (filtered/sorted) rows in a new unsaved Excel workbook")
        self.export_btn.setStyleSheet(
            f"QPushButton {{ background: {PURPLE_PRIMARY}; color: white; border: none;"
            " border-radius: 4px; padding: 3px 14px; font-size: 11px; font-weight: bold; }"
            f" QPushButton:hover {{ background: {PURPLE_DARK}; }}")
        self.export_btn.clicked.connect(self._on_export)
        top.addWidget(self.export_btn)
        layout.addLayout(top)

        self.grid = FilterTableView(body)
        self.grid.set_export_visible(False)
        self.grid.apply_ledger_style()
        layout.addWidget(self.grid, 1)
        return body

    def reload(self) -> None:
        """(Re)read the plancode table and show it.

        Raises the loader's error (missing/malformed JSON) so the caller can
        surface it — a blank table would look like "no plancodes".
        """
        df, text_columns = plancode_table_frame(plancode_table_rows())
        self._df = df
        self._text_columns = text_columns
        self.grid.set_dataframe(df, limit_rows=False)
        if self.grid.model is not None:
            self.grid.model._left_align_columns = {
                index for index, column in enumerate(df.columns) if column in text_columns
            }
        frozen = 0
        for column in df.columns:
            if column not in FROZEN_COLUMNS:
                break
            frozen += 1
        self.grid.set_frozen_column_count(frozen)
        self.grid.autofit_columns_to_data()
        self.summary_label.setText(
            f"{len(df):,} plancodes   ·   {len(df.columns)} columns   ·   "
            f"{plancode_table_path().name}")

    def _on_export(self):
        df = self.grid.get_filtered_dataframe()
        if df is None or df.empty:
            QMessageBox.information(self, "Dump to Excel", "There are no rows to export.")
            return
        try:
            from suiteview.core.excel_export import ExcelExportError, dump_to_new_workbook

            headers = list(df.columns)
            data = [
                tuple(None if pd.isna(value) else value for value in record)
                for record in df.itertuples(index=False, name=None)
            ]
            text_cols = [i for i, column in enumerate(headers) if column in self._text_columns]
            dump_to_new_workbook(
                headers, data, sheet_name="Plancode Table", text_col_indexes=text_cols)
        except ExcelExportError as exc:
            QMessageBox.warning(self, "Export Error", f"Could not export to Excel:\n{exc}")
        except Exception as exc:  # pragma: no cover - UI guard
            logger.error("Plancode table export failed: %s", exc, exc_info=True)
            QMessageBox.warning(self, "Export Error", f"Could not export to Excel:\n{exc}")
