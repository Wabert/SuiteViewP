"""
Compare Results tab — shows rows unique to each month-end in two sub-tabs.

Each sub-tab contains a FilterTableView with compact styling matching ResultsTab.
Footer has row count labels and a single "Export to Excel" button that writes
both sub-tabs into separate sheets of a new workbook.
"""
from __future__ import annotations

import logging

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QMessageBox,
)
from PyQt6.QtGui import QFont

from suiteview.ui.widgets.filter_table_view import FilterTableView

logger = logging.getLogger(__name__)
_FONT = QFont("Segoe UI", 9)

_TABLE_STYLE = """
    QTableView#filterTableView {
        gridline-color: transparent;
        background-color: white;
        alternate-background-color: white;
        selection-background-color: #e0e8f0;
        selection-color: black;
        font-size: 9pt;
        border: none;
    }
    QTableView#filterTableView::item {
        padding: 0px 2px;
        border: none;
    }
    QTableView#filterTableView::item:selected {
        background-color: #e0e8f0;
        color: black;
    }
    QTableView#filterTableView::item:hover {
        background-color: transparent;
    }
    QHeaderView::section {
        background-color: #e8e8e8;
        color: #000000;
        font-weight: normal;
        font-size: 8pt;
        padding: 1px 16px 1px 4px;
        border: 1px solid #c0c0c0;
    }
    QHeaderView::section:hover {
        background-color: #d8d8d8;
    }
"""


def _make_table_widget(parent) -> tuple[QWidget, FilterTableView]:
    """Create a sub-tab widget containing a styled FilterTableView."""
    w = QWidget(parent)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(2, 2, 2, 2)
    lay.setSpacing(0)
    ftv = FilterTableView(w)
    tv = ftv.table_view
    tv.verticalHeader().setVisible(False)
    tv.verticalHeader().setDefaultSectionSize(16)
    tv.verticalHeader().setMinimumSectionSize(14)
    tv.setSelectionBehavior(tv.SelectionBehavior.SelectRows)
    tv.setEditTriggers(tv.EditTrigger.NoEditTriggers)
    tv.setStyleSheet(_TABLE_STYLE)
    lay.addWidget(ftv, 1)
    return w, ftv


class CompareResultsTab(QWidget):
    """Compare Results tab with EOM1-only and EOM2-only sub-tabs."""

    policy_double_clicked = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df1: pd.DataFrame | None = None
        self._df2: pd.DataFrame | None = None
        self._eom1_label = "EOM1 only"
        self._eom2_label = "EOM2 only"
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        # Sub-tabs
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setFont(_FONT)
        self.sub_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #999; }"
            "QTabBar::tab { padding: 2px 8px; min-height: 20px; font-size: 9pt; }"
            "QTabBar::tab:selected { font-weight: bold; }"
        )

        self._eom1_widget, self.table_eom1 = _make_table_widget(self)
        self.sub_tabs.addTab(self._eom1_widget, self._eom1_label)

        self._eom2_widget, self.table_eom2 = _make_table_widget(self)
        self.sub_tabs.addTab(self._eom2_widget, self._eom2_label)

        root.addWidget(self.sub_tabs, 1)

        # ── Footer ──────────────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setContentsMargins(4, 0, 4, 2)
        bottom.setSpacing(8)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT)
        self.lbl_status.setStyleSheet("color: #888;")
        bottom.addWidget(self.lbl_status)
        bottom.addStretch()

        self.btn_export = QPushButton("Export to Excel")
        self.btn_export.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_export.setFixedSize(110, 28)
        self.btn_export.setStyleSheet(
            "QPushButton { background-color: #2E7D32; color: white;"
            " border: 1px solid #1B5E20; border-radius: 3px; }"
            "QPushButton:hover { background-color: #388E3C; }"
            "QPushButton:disabled { background-color: #A5D6A7; }"
        )
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_to_excel)
        bottom.addWidget(self.btn_export)

        root.addLayout(bottom)

        # Double-click on rows → emit policy signal
        self.table_eom1.table_view.doubleClicked.connect(self._on_double_click)
        self.table_eom2.table_view.doubleClicked.connect(self._on_double_click)

        # Update status when sub-tab changes
        self.sub_tabs.currentChanged.connect(self._update_status)

    def _on_double_click(self, index):
        """Extract Pol and Co from the clicked row and emit signal."""
        model = index.model()
        if model is None:
            return
        row = index.row()
        col_count = model.columnCount()
        headers = {}
        for c in range(col_count):
            name = model.headerData(c, Qt.Orientation.Horizontal,
                                    Qt.ItemDataRole.DisplayRole)
            if name:
                headers[str(name).upper()] = c

        pol_col = headers.get("POL")
        co_col = headers.get("CO")
        if pol_col is None or co_col is None:
            return

        policy = str(model.data(
            model.index(row, pol_col), Qt.ItemDataRole.DisplayRole) or "")
        company = str(model.data(
            model.index(row, co_col), Qt.ItemDataRole.DisplayRole) or "")
        if policy:
            self.policy_double_clicked.emit(policy, company)

    # ── Public API ───────────────────────────────────────────────────

    def set_results(self, df_eom1: pd.DataFrame, df_eom2: pd.DataFrame,
                    eom1_label: str, eom2_label: str):
        """Load compare results into the two sub-tabs."""
        self._df1 = df_eom1
        self._df2 = df_eom2
        self._eom1_label = eom1_label
        self._eom2_label = eom2_label

        self.sub_tabs.setTabText(0, f"{eom1_label} only")
        self.sub_tabs.setTabText(1, f"{eom2_label} only")

        self.table_eom1.set_dataframe(df_eom1, limit_rows=False)
        self.table_eom2.set_dataframe(df_eom2, limit_rows=False)

        has_data = len(df_eom1) > 0 or len(df_eom2) > 0
        self.btn_export.setEnabled(has_data)
        self._update_status()

    def _update_status(self):
        """Update the status label based on the active sub-tab."""
        idx = self.sub_tabs.currentIndex()
        if idx == 0 and self._df1 is not None:
            n = len(self._df1)
            self.lbl_status.setText(f"{self._eom1_label} only: {n:,} rows")
        elif idx == 1 and self._df2 is not None:
            n = len(self._df2)
            self.lbl_status.setText(f"{self._eom2_label} only: {n:,} rows")
        else:
            self.lbl_status.setText("")

    # ── Excel export ─────────────────────────────────────────────────

    def _export_to_excel(self):
        """Export both sub-tab results to separate sheets in a new workbook."""
        if self._df1 is None and self._df2 is None:
            return

        self.btn_export.setEnabled(False)
        self.btn_export.setText("Exporting...")
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            from win32com.client import dynamic
            excel = dynamic.Dispatch("Excel.Application")
            excel.Visible = True
            excel.ScreenUpdating = False

            wb = excel.Workbooks.Add()

            # Sheet 1: EOM1 only
            ws1 = wb.Sheets(1)
            ws1.Name = self._eom1_label + " only"
            self._write_sheet(ws1, self._df1)

            # Sheet 2: EOM2 only
            ws2 = wb.Sheets.Add(After=wb.Sheets(wb.Sheets.Count))
            ws2.Name = self._eom2_label + " only"
            self._write_sheet(ws2, self._df2)

            ws1.Activate()
            ws1.Range("A1").Select()
            excel.ScreenUpdating = True

        except ImportError:
            QMessageBox.warning(
                self, "Error",
                "win32com is not available. Cannot export to Excel.")
        except Exception as e:
            logger.exception("Excel export failed")
            QMessageBox.warning(
                self, "Excel Error",
                f"Failed to export to Excel:\n{e}")
        finally:
            self.btn_export.setEnabled(True)
            self.btn_export.setText("Export to Excel")

    @staticmethod
    def _write_sheet(ws, df: pd.DataFrame | None):
        """Write a DataFrame to an Excel worksheet."""
        if df is None or df.empty:
            ws.Cells(1, 1).Value = "(no rows)"
            return

        headers = list(df.columns)
        col_count = len(headers)
        data_rows = []
        for _, row in df.iterrows():
            row_data = []
            for val in row:
                if pd.isna(val):
                    row_data.append("")
                else:
                    s = str(val)
                    clean = s.replace(",", "").replace("$", "").strip()
                    try:
                        row_data.append(float(clean))
                    except (ValueError, TypeError):
                        row_data.append(s)
            data_rows.append(tuple(row_data))

        all_rows = [tuple(headers)] + data_rows
        total_rows = len(all_rows)
        rng = ws.Range(ws.Cells(1, 1), ws.Cells(total_rows, col_count))
        rng.Value = all_rows

        # Bold header
        hdr = ws.Range(ws.Cells(1, 1), ws.Cells(1, col_count))
        hdr.Font.Bold = True

        # Freeze top row + auto-filter + auto-fit
        ws.Range("A2").Select()
        ws.Application.ActiveWindow.FreezePanes = True
        if total_rows > 1:
            ws.Range(ws.Cells(1, 1),
                     ws.Cells(total_rows, col_count)).AutoFilter()
        ws.Columns.AutoFit()
