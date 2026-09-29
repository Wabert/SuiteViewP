"""
Raw Table tab – transposed/normal data view with column filtering & Excel export.
"""

from datetime import datetime

import pandas as pd

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget, QMessageBox,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, QItemSelectionModel, QModelIndex, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor

from suiteview.core.db2_connection import DB2Connection
from suiteview.ui.widgets.filter_table_view import FilterTableView
from ...services.table_search import TableSearchResult
from ..styles import (
    BLUE_LIGHT, BLUE_DARK, BLUE_PRIMARY, GOLD_LIGHT, GOLD_PRIMARY,
    GREEN_SUBTLE, GREEN_DARK, GREEN_PRIMARY,
)
from ..widgets import CopyableLabel

SEARCH_COLUMNS = ["Match", "Record", "Table", "Field", "Row", "Value"]
# Light blue, distinct from the gold selected cell and the green header.
ROW_HIGHLIGHT = "#E6F0FA"
# Rate column groups (Current / Guaranteed / Shadow / each dividend type) alternate light
# green, slightly darker green, left to right; both light enough for black text
# (Robert Haessly, 9/28/2026: alternation instead of a shade per scale).
GROUP_TINTS = ("#EEF7EE", "#DCEEDD")


def alternating_group_tints(groups) -> dict:
    """``{group label: tint}`` alternating ``GROUP_TINTS`` over ``(label, columns)`` groups in order."""
    tints: dict = {}
    for label, _columns in groups or []:
        if label not in tints:
            tints[label] = GROUP_TINTS[len(tints) % len(GROUP_TINTS)]
    return tints


# FilterTableView's "Export to Excel" button colors (the Excel green).
EXCEL_GREEN = "#217346"
EXCEL_GREEN_DARK = "#1a5c38"


class RawTableTab(QWidget):
    """Tab for viewing raw table data with transpose and export functionality."""

    # record, table, field ("" for a table-name hit), row (1-based; 0 = all rows)
    search_hit_activated = pyqtSignal(str, str, str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_transposed = True  # Default to transposed view (fields as rows)
        self._current_cols = []
        self._current_rows = []
        self._current_table_name = ""
        self._header_labels: dict = {}
        self._column_groups: list = []
        self._search_result: TableSearchResult | None = None
        # Cached DataFrames per orientation so repeated transposing never
        # rebuilds the frame or recomputes each grid's unique-value filters.
        self._df_normal = None
        self._df_transposed = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header row with label and buttons
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 4, 4, 0)

        self.table_label = CopyableLabel("Select a table from the left panel")
        self.table_label.setStyleSheet("font-weight: bold;")
        self.table_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.table_label.setCursor(Qt.CursorShape.IBeamCursor)
        header_layout.addWidget(self.table_label)

        header_layout.addStretch()

        # Transpose button
        self.transpose_btn = QPushButton("⇄ Transpose")
        self.transpose_btn.setToolTip("Toggle between transposed and normal view")
        self.transpose_btn.setFixedSize(90, 24)
        self.transpose_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {BLUE_LIGHT};
                color: {BLUE_DARK};
                border: 1px solid {BLUE_PRIMARY};
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {GOLD_LIGHT};
                border-color: {GOLD_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {GOLD_PRIMARY};
            }}
        """)
        self.transpose_btn.clicked.connect(self._toggle_transpose)
        header_layout.addWidget(self.transpose_btn)

        # Export button: the Excel green, opens the export in Excel without a file dialog.
        self.export_btn = QPushButton("E")
        self.export_btn.setToolTip("Export to Excel")
        self.export_btn.setFixedSize(28, 24)
        self.export_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {EXCEL_GREEN};
                color: white;
                border: 1px solid {EXCEL_GREEN_DARK};
                border-radius: 3px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {EXCEL_GREEN_DARK};
            }}
            QPushButton:pressed {{
                background-color: {EXCEL_GREEN_DARK};
            }}
        """)
        self.export_btn.clicked.connect(self._export_to_excel)
        header_layout.addWidget(self.export_btn)

        layout.addLayout(header_layout)

        # Two Excel-style filter grids (the same widget used by the Query
        # results view) — one per orientation. Only the active one is shown;
        # toggling transpose swaps the stacked page so each grid keeps its own
        # column filters and cached unique values with no recompute.
        self._stack = QStackedWidget()
        self._normal_grid = self._make_grid()
        self._transposed_grid = self._make_grid()
        self._search_grid = self._make_grid()
        self._search_grid.set_full_row_selection(True)
        self._search_grid.table_view.setToolTip("Double-click a match to open its table")
        self._search_grid.table_view.doubleClicked.connect(self._on_search_hit_double_clicked)
        # Rates grids load in the normal orientation: tint the clicked row; each rate
        # column group is shaded down the body (see ``alternating_group_tints``).
        self._normal_grid.set_current_row_highlight(ROW_HIGHLIGHT)
        self._stack.addWidget(self._normal_grid)      # index 0 – normal
        self._stack.addWidget(self._transposed_grid)  # index 1 – transposed
        self._stack.addWidget(self._search_grid)      # index 2 – Tables search matches
        layout.addWidget(self._stack)

        self._update_active_grid()

    def _make_grid(self) -> FilterTableView:
        """Create a FilterTableView themed to match the PolView tabs."""
        grid = FilterTableView(self)
        # The tab's own E button exports without asking for a file name.
        grid.set_export_visible(False)
        grid.apply_ledger_style(
            header_bg=GREEN_SUBTLE,
            header_fg=GREEN_DARK,
            border=GREEN_PRIMARY,
            selection_bg=GOLD_LIGHT,
            selection_fg=GREEN_DARK,
        )
        grid.show_cell_highlights()  # current-policy-year highlight in rate views
        return grid

    # ── clear / reset ────────────────────────────────────────────────────

    def clear(self):
        """Reset the tab to its initial empty state."""
        self._current_cols = []
        self._current_rows = []
        self._current_table_name = ""
        self._df_normal = None
        self._df_transposed = None
        self._set_column_layout(None, None)
        self._leave_search_mode()
        self.table_label.setText("Select a table from the left panel")
        empty = pd.DataFrame()
        self._normal_grid.set_dataframe(empty, limit_rows=False)
        self._transposed_grid.set_dataframe(empty, limit_rows=False)
        self._search_grid.set_dataframe(empty, limit_rows=False)
        self._update_active_grid()

    # ── view toggling ────────────────────────────────────────────────────

    def _toggle_transpose(self):
        """Toggle between transposed and normal view."""
        self._is_transposed = not self._is_transposed
        self._update_active_grid()

    def _update_active_grid(self):
        """Show the grid for the current orientation (no recompute)."""
        if self._search_result is not None:
            self._stack.setCurrentWidget(self._search_grid)
            return
        self._stack.setCurrentWidget(
            self._transposed_grid if self._is_transposed else self._normal_grid
        )

    def _leave_search_mode(self):
        self._search_result = None
        self.transpose_btn.setEnabled(True)

    def _display_data(self):
        """Build (and cache) both orientation frames, then show the active one.

        Each frame is built once per loaded table and handed to its own grid,
        so toggling transpose only swaps the visible page — the per-column
        unique-value filters for each orientation are never recomputed.
        """
        if not self._current_cols or not self._current_rows:
            return

        if self._df_normal is None:
            self._df_normal = self._build_normal_df()
            self._normal_grid.set_dataframe(self._df_normal, limit_rows=False)
            self._normal_grid.set_header_labels(self._header_labels)
            self._normal_grid.set_column_groups(self._column_groups)
            self._normal_grid.set_group_backgrounds(alternating_group_tints(self._column_groups))
            self._normal_grid.autofit_columns_to_data()
            self._normal_grid.fit_column_groups_to_labels()

        if self._df_transposed is None:
            self._df_transposed = self._build_transposed_df()
            self._transposed_grid.set_dataframe(self._df_transposed, limit_rows=False)
            self._transposed_grid.autofit_columns_to_data()

        self._update_active_grid()

    def _build_normal_df(self) -> pd.DataFrame:
        """Normal orientation: DB2 fields as columns, records as rows."""
        return pd.DataFrame(list(self._current_rows), columns=list(self._current_cols))

    def _build_transposed_df(self) -> pd.DataFrame:
        """Transposed orientation: a 'Field' column plus one column per record."""
        data = {"Field": list(self._current_cols)}
        for rec_idx, row in enumerate(self._current_rows):
            data[f"Row {rec_idx + 1}"] = [
                row[field_idx] if field_idx < len(row) else None
                for field_idx in range(len(self._current_cols))
            ]
        return pd.DataFrame(data)

    def show_message(self, message: str, table_name: str = None):
        """Show a single-cell placeholder (no data / error) in both grids."""
        if table_name is not None:
            self._current_table_name = table_name
            self.table_label.setText(table_name)
        self._leave_search_mode()
        self._current_cols = []
        self._current_rows = []
        self._df_normal = None
        self._df_transposed = None
        self._set_column_layout(None, None)
        df = pd.DataFrame({"Result": [message]})
        for grid in (self._normal_grid, self._transposed_grid):
            grid.set_dataframe(df, limit_rows=False)
            grid.autofit_columns_to_data(max_width=1000)
        self._update_active_grid()

    def set_data(self, cols, rows, table_name: str = None, transposed: bool = None,
                 header_labels: dict = None, column_groups: list = None):
        """Load column/row data directly (e.g. the Rates view builds a matrix).

        Unlike setting the internal attributes by hand, this resets the cached
        orientation frames so a new selection always rebuilds and displays
        instead of re-showing the previously cached grids. ``header_labels`` and
        ``column_groups`` give the normal orientation a two-level header (a group
        band over each run of columns, e.g. the rate scale over its rate types).
        """
        self._current_cols = list(cols)
        self._current_rows = [tuple(r) for r in rows]
        self._leave_search_mode()
        if table_name is not None:
            self._current_table_name = table_name
            self.table_label.setText(table_name)
        if transposed is not None:
            self._is_transposed = transposed
        self._df_normal = None
        self._df_transposed = None
        self._set_column_layout(header_labels, column_groups)
        if self._current_cols and self._current_rows:
            self._display_data()
        else:
            self.show_message("No data")

    def _set_column_layout(self, header_labels, column_groups):
        self._header_labels = dict(header_labels or {})
        self._column_groups = list(column_groups or [])
        if not self._column_groups:
            self._normal_grid.set_column_groups(None)
            self._normal_grid.set_group_backgrounds(None)

    # ── Tables search results ────────────────────────────────────────────

    @property
    def showing_search_results(self) -> bool:
        return self._search_result is not None

    def show_search_results(self, result: TableSearchResult):
        """List Tables-panel search matches; double-click one to open its table."""
        self._search_result = result
        self.transpose_btn.setEnabled(False)
        self._current_table_name = "Table Search"
        hits = result.hits
        tables = len({hit.table for hit in hits})
        summary = (
            f"Search: “{result.term}” — {len(hits):,} match{'es' if len(hits) != 1 else ''}"
            f" in {tables} of {result.tables_searched} table"
            f"{'s' if result.tables_searched != 1 else ''}"
        )
        if result.truncated:
            summary += f" (first {len(hits):,} shown — refine the search)"
        if result.not_searched:
            summary += f"  ⚠ not searched (not loaded): {', '.join(result.not_searched)}"
        self.table_label.setText(summary)
        if hits:
            df = pd.DataFrame(
                [(h.match, h.record, h.table, h.field, h.row or None, h.value) for h in hits],
                columns=SEARCH_COLUMNS,
            )
            df["Row"] = df["Row"].astype("Int64")
        else:
            df = pd.DataFrame({"Result": [f"No table, field or value contains “{result.term}”"]})
        self._search_grid.set_dataframe(df, limit_rows=False)
        self._search_grid.autofit_columns_to_data(max_width=420)
        self._update_active_grid()

    def search_hits_frame(self) -> pd.DataFrame:
        """The displayed matches (after any grid filter/sort)."""
        model = self._search_grid.model
        return model.get_display_data() if model is not None else pd.DataFrame()

    @pyqtSlot(QModelIndex)
    def _on_search_hit_double_clicked(self, index: QModelIndex):
        self.activate_search_hit(index.row())

    def activate_search_hit(self, view_row: int):
        if self._search_result is None:
            return
        frame = self.search_hits_frame()
        if "Table" not in frame.columns or not 0 <= view_row < len(frame):
            return
        hit = frame.iloc[view_row]
        row = hit["Row"]
        self.search_hit_activated.emit(
            str(hit["Record"]), str(hit["Table"]), str(hit["Field"]),
            0 if pd.isna(row) else int(row),
        )

    def focus_field(self, field: str, row: int = 0):
        """After a search hit opens its table, select and scroll to the match.

        Selection (not a BackgroundRole tint) marks the cells: the ledger QSS
        suppresses model background brushes on unselected items.
        """
        if not field or field not in self._current_cols:
            return
        field_index = self._current_cols.index(field)
        row_count = len(self._current_rows)
        rows = [row] if 1 <= row <= row_count else list(range(1, row_count + 1))
        cells = {
            self._transposed_grid: [(field_index, 0)] + [(field_index, r) for r in rows],
            self._normal_grid: [(r - 1, field_index) for r in rows],
        }
        for grid, targets in cells.items():
            model, selection = grid.model, grid.table_view.selectionModel()
            if model is None or selection is None:
                continue
            indexes = [model.index(*t) for t in targets]
            indexes = [i for i in indexes if i.isValid()]
            if not indexes:
                continue
            anchor = indexes[-1] if row else indexes[0]
            selection.setCurrentIndex(anchor, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            for index in indexes:
                selection.select(index, QItemSelectionModel.SelectionFlag.Select)
            grid.table_view.scrollTo(anchor, grid.table_view.ScrollHint.PositionAtCenter)

    def highlight_row(self, row: int, color: str):
        """Tint one data row (a column in the transposed view), e.g. the current policy year."""
        if not 0 <= row < len(self._current_rows):
            return
        brush = QColor(color)
        self._normal_grid.set_highlighted_cells(
            {(row, str(col)): brush for col in self._current_cols})
        self._transposed_grid.set_highlighted_cells(
            {(field, f"Row {row + 1}"): brush for field in range(len(self._current_cols))})
        for grid, target_row, column in ((self._normal_grid, row, 0),
                                         (self._transposed_grid, 0, row + 1)):
            if grid.model is not None and column < grid.model.columnCount():
                grid.table_view.scrollTo(
                    grid.model.index(target_row, column),
                    QAbstractItemView.ScrollHint.PositionAtCenter,
                )

    # ── Excel export ─────────────────────────────────────────────────────

    def _export_to_excel(self):
        """Export current table data (or the search matches) to a new Excel file."""
        cols, rows, transposed = self._export_rows()
        if not cols or not rows:
            QMessageBox.information(self, "Export", "No data to export")
            return

        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Border, Side
        except ImportError:
            QMessageBox.warning(
                self, "Export",
                "openpyxl is required for Excel export.\nInstall with: pip install openpyxl",
            )
            return

        # Create workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = self._current_table_name[:31] if self._current_table_name else "Data"

        # Define styles
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        self._write_export_sheet(ws, cols, rows, transposed, header_font, header_fill, thin_border)
        self._autofit_export_sheet(ws)
        filepath = self._save_export_workbook(wb)
        self._open_export_workbook(filepath)
        self.status_message = f"Exported to {filepath}"

    def _export_rows(self):
        if self._search_result is None:
            return self._current_cols, self._current_rows, self._is_transposed
        frame = self.search_hits_frame()
        cols = [] if "Table" not in frame.columns else list(frame.columns)
        rows = [
            tuple(None if pd.isna(value) else value for value in row)
            for row in frame.itertuples(index=False)
        ] if cols else []
        return cols, rows, False

    def _write_export_sheet(
        self, ws, cols, rows, transposed: bool, header_font, header_fill, thin_border
    ) -> None:
        if transposed:
            self._write_transposed_export(ws, cols, rows, header_font, header_fill, thin_border)
            return
        self._write_normal_export(ws, cols, rows, header_font, header_fill, thin_border)

    @staticmethod
    def _write_transposed_export(ws, cols, rows, header_font, header_fill, thin_border) -> None:
        ws.cell(row=1, column=1, value="Field").font = header_font
        ws.cell(row=1, column=1).fill = header_fill
        ws.cell(row=1, column=1).border = thin_border
        for col_idx in range(len(rows)):
            cell = ws.cell(row=1, column=col_idx + 2, value=f"Row {col_idx + 1}")
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
        for row_idx, field_name in enumerate(cols):
            ws.cell(row=row_idx + 2, column=1, value=field_name).border = thin_border
            for col_idx, row_data in enumerate(rows):
                value = row_data[row_idx] if row_idx < len(row_data) else ""
                ws.cell(row=row_idx + 2, column=col_idx + 2, value=value).border = thin_border

    @staticmethod
    def _write_normal_export(ws, cols, rows, header_font, header_fill, thin_border) -> None:
        for col_idx, col_name in enumerate(cols):
            cell = ws.cell(row=1, column=col_idx + 1, value=col_name)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
        for row_idx, row_data in enumerate(rows):
            for col_idx, value in enumerate(row_data):
                ws.cell(row=row_idx + 2, column=col_idx + 1, value=value).border = thin_border

    @staticmethod
    def _autofit_export_sheet(ws) -> None:
        from openpyxl.utils import get_column_letter

        for column_cells in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column_cells[0].column)
            for cell in column_cells:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except Exception:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width

    def _save_export_workbook(self, wb) -> str:
        import tempfile
        import os

        temp_dir = tempfile.gettempdir()
        filename = f"{self._current_table_name or 'Export'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(temp_dir, filename)
        wb.save(filepath)
        return filepath

    @staticmethod
    def _open_export_workbook(filepath: str) -> None:
        import os
        import subprocess

        try:
            os.startfile(filepath)
        except Exception:
            subprocess.Popen(["start", filepath], shell=True)

    # ── data loading ─────────────────────────────────────────────────────

    def load_table(self, db: DB2Connection, table_name: str, where_clause: str,
                   policy_id: str = None, company_code: str = None):
        """Load a specific table.

        Args:
            db: Database connection
            table_name: Name of the table to load
            where_clause: Standard WHERE clause (with CK_SYS_CD)
            policy_id: Policy ID for FH_ tables (no CK_SYS_CD)
            company_code: Company code for FH_ tables
        """
        self.table_label.setText(f"Table: {table_name}")
        self._current_table_name = table_name
        self._leave_search_mode()

        try:
            # FH_ tables don't have CK_SYS_CD column
            if table_name.startswith("FH_") and policy_id and company_code:
                fh_where_clause = f"TCH_POL_ID = '{policy_id}' AND CK_CMP_CD = '{company_code}'"
                sql = f"SELECT * FROM DB2TAB.{table_name} WHERE {fh_where_clause}"
            else:
                sql = f"SELECT * FROM DB2TAB.{table_name} WHERE {where_clause}"

            cols, rows = db.execute_query_with_headers(sql)

            if rows:
                self._current_cols = list(cols)
                # fetchall() yields pyodbc.Row objects; pandas treats those as
                # scalars (→ "Shape of passed values" error), so normalize to
                # plain tuples before building the DataFrames.
                self._current_rows = [tuple(r) for r in rows]
                self._df_normal = None
                self._df_transposed = None
                self._display_data()
            else:
                self.show_message("No data found")

        except Exception as e:
            self.show_message(f"Error: {e}")
