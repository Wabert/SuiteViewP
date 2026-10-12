"""Plancode Table viewer — read-only RERUN window over ``dbo.SV_RERUN_Adv_Plancodes``
(product rules) and ``dbo.SV_RERUN_Plancode_Control`` (which plancodes may be illustrated).

Opened from the RERUN header's ☰ menu, for every RERUN user. Each tab shows one row per plancode as stored in the
UL_Rates table (the Adv tab is the same rows ``load_plancode`` reads): the product rules and the
explicit illustration age overrides. Rates the database supplies are not in the
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.core.plancode_control import clear_control_cache, control_rows
from suiteview.illustration.models.plancode_config import (
    clear_plancode_cache,
    plancode_table_name,
    plancode_table_rows,
)
from suiteview.illustration.models.rerun_plancode_tables import CONTROL_TABLE
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

WINDOW_TITLE = "SuiteView:  Plancode Tables"
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


def control_table_rows() -> list[dict]:
    """Every ``SV_RERUN_Plancode_Control`` row, ordered by plancode, freshly read."""
    clear_control_cache()
    return [
        {"Plancode": row.plancode, "ProductType": row.product_type,
         "CanIllustrate": row.can_illustrate}
        for _, row in sorted(control_rows().items())
    ]


class _TablePanel(QWidget):
    """One read-only, filterable table with its summary line and Dump to Excel."""

    def __init__(self, sheet_name: str, table_name: str, noun: str, load_rows, parent=None):
        super().__init__(parent)
        self._sheet_name = sheet_name
        self._table_name = table_name
        self._noun = noun
        self._load_rows = load_rows
        self._df = pd.DataFrame()
        self._text_columns: set[str] = set()
        self._build()

    def _build(self) -> None:
        body = self
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 6, 0, 0)
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

    def reload(self) -> None:
        """(Re)read the table from UL_Rates and show it.

        Raises the loader's error (database unavailable) so the caller can
        surface it — a blank table would look like "no plancodes".
        """
        df, text_columns = plancode_table_frame(self._load_rows())
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
            f"{len(df):,} {self._noun}   ·   {len(df.columns)} columns   ·   "
            f"{self._table_name}")

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
                headers, data, sheet_name=self._sheet_name, text_col_indexes=text_cols)
        except ExcelExportError as exc:
            QMessageBox.warning(self, "Export Error", f"Could not export to Excel:\n{exc}")
        except Exception as exc:  # pragma: no cover - UI guard
            logger.error("Plancode table export failed: %s", exc, exc_info=True)
            QMessageBox.warning(self, "Export Error", f"Could not export to Excel:\n{exc}")


def adv_table_rows() -> list[dict]:
    clear_plancode_cache()
    return plancode_table_rows()


class PlancodeTableWindow(FramelessWindowBase):
    """Read-only views of the two RERUN plancode tables: Adv_Plancodes (product
    rules) and Plancode_Control (which plancodes may be illustrated)."""

    def __init__(self, parent=None):
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
        layout.setContentsMargins(8, 0, 8, 14)
        self.adv_panel = _TablePanel(
            "Adv Plancodes", plancode_table_name(), "plancodes", adv_table_rows, body)
        self.control_panel = _TablePanel(
            "Plancode Control", CONTROL_TABLE, "plancodes", control_table_rows, body)
        self.tabs = QTabWidget(body)
        self.tabs.addTab(self.adv_panel, "Adv_Plancodes")
        self.tabs.addTab(self.control_panel, "Plancode_Control")
        layout.addWidget(self.tabs, 1)
        return body

    @property
    def grid(self):
        return self.adv_panel.grid

    @property
    def summary_label(self):
        return self.adv_panel.summary_label

    def reload(self) -> None:
        """Reread both tables; a failure propagates so the caller can surface it."""
        self.adv_panel.reload()
        self.control_panel.reload()
