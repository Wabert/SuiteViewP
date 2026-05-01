"""
Results tab — displays audit query results in FilterTableView.

Compact table with green column headers matching VBA frmAudit Results tab.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
)
from PyQt6.QtGui import QFont

from suiteview.ui.widgets.filter_table_view import FilterTableView

logger = logging.getLogger(__name__)
_FONT = QFont("Segoe UI", 9)


class ResultsTab(QWidget):
    """Results tab — shows query output in a filterable table."""

    # Emitted on double-click: (policy_number, company_code)
    policy_double_clicked = pyqtSignal(str, str)
    # Emitted when the user clicks Pin: carries the current DataFrame
    pin_requested = pyqtSignal(object)  # pd.DataFrame

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._query_context: dict | None = None  # SQL, DSN, columns, types, source_design
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        self.table = FilterTableView(self)

        tv = self.table.table_view
        # Hide row index (vertical header)
        tv.verticalHeader().setVisible(False)
        # Tighter rows
        tv.verticalHeader().setDefaultSectionSize(16)
        tv.verticalHeader().setMinimumSectionSize(14)
        # Full-row selection, no individual cell highlight
        tv.setSelectionBehavior(tv.SelectionBehavior.SelectRows)

        # Compact gray headers, no grid, no alternating, subtle row highlight
        tv.setStyleSheet("""
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
        """)
        root.addWidget(self.table, 1)

        # ── Bottom bar with status label + Export button ─────────────
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

        self.btn_save_qdef = QPushButton("Save QDef")
        self.btn_save_qdef.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_save_qdef.setFixedSize(90, 28)
        self.btn_save_qdef.setStyleSheet(
            "QPushButton { background-color: #7C3AED; color: white;"
            " border: 1px solid #6D28D9; border-radius: 3px; }"
            "QPushButton:hover { background-color: #8B5CF6; }"
            "QPushButton:disabled { background-color: #C4B5FD; }"
        )
        self.btn_save_qdef.setEnabled(False)
        self.btn_save_qdef.setToolTip("Save as a Query Definition")
        self.btn_save_qdef.clicked.connect(self._on_save_qdef)
        bottom.addWidget(self.btn_save_qdef)

        root.addLayout(bottom)

        # Double-click on row → open policy in PolView
        self.table.table_view.setEditTriggers(
            self.table.table_view.EditTrigger.NoEditTriggers)
        self.table.table_view.doubleClicked.connect(self._on_double_click)

    def _on_double_click(self, index):
        """Extract PolicyNumber and CompanyCode from the clicked row."""
        model = self.table.table_view.model()
        if model is None:
            return
        row = index.row()
        # Find column indices by header name
        col_count = model.columnCount()
        headers = {}
        for c in range(col_count):
            name = model.headerData(c, Qt.Orientation.Horizontal,
                                    Qt.ItemDataRole.DisplayRole)
            if name:
                headers[str(name).upper()] = c

        pol_col = headers.get("POLICYNUMBER") or headers.get("POL")
        co_col = headers.get("COMPANYCODE") or headers.get("CO")
        if pol_col is None or co_col is None:
            return

        policy = str(model.data(
            model.index(row, pol_col), Qt.ItemDataRole.DisplayRole) or "")
        company = str(model.data(
            model.index(row, co_col), Qt.ItemDataRole.DisplayRole) or "")
        if policy:
            self.policy_double_clicked.emit(policy, company)

    def set_results(self, df: pd.DataFrame):
        """Load query results into the table."""
        self._df = df
        self.table.set_dataframe(df, limit_rows=False)
        row_count = len(df)
        self.lbl_status.setText(
            f"Showing all {row_count} rows" if row_count else "")
        self.btn_export.setEnabled(row_count > 0)
        self.btn_save_qdef.setEnabled(row_count > 0 and self._query_context is not None)

    def set_query_context(self, *, sql: str, dsn: str, source_design: str = "",
                          result_columns: list[str] = None,
                          column_types: dict[str, str] = None,
                          tables: list[str] = None,
                          display_names: dict[str, str] = None):
        """Store the query metadata needed to create a QDefinition."""
        self._query_context = {
            "sql": sql,
            "dsn": dsn,
            "source_design": source_design,
            "result_columns": result_columns or [],
            "column_types": column_types or {},
            "tables": tables or [],
            "display_names": display_names or {},
        }
        # Re-check enable state
        if self._df is not None and len(self._df) > 0:
            self.btn_save_qdef.setEnabled(True)

    # ── Excel export ─────────────────────────────────────────────────

    def _export_to_excel(self):
        """Open a new unsaved Excel workbook with results + DataDef sheet."""
        if self._df is None or self._df.empty:
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

            # ── Sheet 1: Results ─────────────────────────────────────
            ws_results = wb.Sheets(1)
            ws_results.Name = "Results"

            df = self._df
            headers = list(df.columns)
            col_count = len(headers)
            row_count = len(df)

            # Build data rows, converting numerics
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

            # Bulk-write header + data
            all_rows = [tuple(headers)] + data_rows
            total_rows = len(all_rows)
            rng = ws_results.Range(
                ws_results.Cells(1, 1),
                ws_results.Cells(total_rows, col_count))
            rng.Value = all_rows

            # Bold header
            hdr_rng = ws_results.Range(
                ws_results.Cells(1, 1),
                ws_results.Cells(1, col_count))
            hdr_rng.Font.Bold = True

            # Freeze top row + auto-filter + auto-fit
            ws_results.Range("A2").Select()
            excel.ActiveWindow.FreezePanes = True
            if total_rows > 1:
                ws_results.Range(
                    ws_results.Cells(1, 1),
                    ws_results.Cells(total_rows, col_count)).AutoFilter()
            ws_results.Columns.AutoFit()

            # ── Sheet 2: DataDef ─────────────────────────────────────
            ws_def = wb.Sheets.Add(After=wb.Sheets(wb.Sheets.Count))
            ws_def.Name = "DataDef"
            self._write_datadef_sheet(ws_def, headers)

            # Select Results sheet, cell A1
            ws_results.Activate()
            ws_results.Range("A1").Select()
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
    def _write_datadef_sheet(ws, result_columns: list[str]):
        """Write data definitions only for columns present in the results."""
        from suiteview.polview.models.cl_polrec.policy_translations import (
            COMPANY_CODES,
            PREMIUM_PAY_STATUS_CODES,
            SUSPENSE_CODES,
            LAST_ENTRY_CODES,
            PRODUCT_LINE_CODES,
            REINSURANCE_CODES,
        )

        # (result column name, table.field, column header label, code dict)
        all_sections = [
            ("CompanyCode", "LH_BAS_POL.CK_CMP_CD", "COMPANYCODE",
             "Description", COMPANY_CODES),
            ("StatusCode", "LH_BAS_POL.PRM_PAY_STA_REA_CD", "STATUSCODE",
             "Description", PREMIUM_PAY_STATUS_CODES),
            ("SuspenseCode", "LH_BAS_POL.SUS_CD", "SUSPENSECODE",
             "Description", SUSPENSE_CODES),
            ("LastEntryCode", "LH_BAS_POL.LST_ETR_CD", "LASTENTRYCODE",
             "Description", LAST_ENTRY_CODES),
            ("ProductLineCode", "LH_COV_PHA.PRD_LIN_TYP_CD",
             "PRODUCTLINECODE", "Description", PRODUCT_LINE_CODES),
            ("ReinsuredCode", "LH_BAS_POL.REINSURED_CD", "REINSUREDCODE",
             "Description", REINSURANCE_CODES),
        ]

        # Filter to only sections whose result column is present
        col_set = set(result_columns)
        sections = [(fp, ch, dh, cd) for rc, fp, ch, dh, cd in all_sections
                     if rc in col_set]

        row = 1
        # Main header
        ws.Cells(row, 1).Value = "Data Definitions"
        ws.Cells(row, 1).Font.Bold = True
        ws.Cells(row, 1).Font.Size = 12
        row += 3  # skip 2 blank rows

        for field_path, code_header, desc_header, code_dict in sections:
            # Section header row: TABLE.FIELD in A, code name in B, "Description" in C
            ws.Cells(row, 1).Value = field_path
            ws.Cells(row, 2).Value = code_header
            ws.Cells(row, 3).Value = desc_header
            ws.Cells(row, 1).Font.Bold = True
            ws.Cells(row, 2).Font.Bold = True
            ws.Cells(row, 3).Font.Bold = True
            row += 1

            # Code/description rows in columns B and C
            for code, desc in code_dict.items():
                ws.Cells(row, 2).Value = code
                ws.Cells(row, 3).Value = desc
                row += 1

            row += 4  # blank rows between sections

        # Auto-fit columns
        ws.Columns(1).AutoFit()
        ws.Columns(2).AutoFit()
        ws.Columns(3).AutoFit()

    # ── Save QDefinition ─────────────────────────────────────────────

    def _on_save_qdef(self):
        """Open dialog to save a QDefinition from current results."""
        if not self._query_context or self._df is None:
            return

        from suiteview.audit.tabs.save_qdef_dialog import SaveQDefDialog
        ctx = self._query_context
        suggested = f"{ctx.get('source_design', 'Query')}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        dlg = SaveQDefDialog(suggested_name=suggested, parent=self)
        if dlg.exec():
            from suiteview.audit.qdefinition import QDefinition
            from suiteview.audit import qdef_store

            name = dlg.selected_name()
            forge = dlg.selected_forge()
            if not name:
                return

            # Derive column types from DataFrame if not provided
            col_types = ctx.get("column_types", {})
            if not col_types and self._df is not None:
                col_types = {col: str(self._df[col].dtype) for col in self._df.columns}

            qd = QDefinition(
                name=name,
                forge_name=forge,
                sql=ctx["sql"],
                dsn=ctx["dsn"],
                source_design=ctx.get("source_design", ""),
                result_columns=ctx.get("result_columns", list(self._df.columns)),
                column_types=col_types,
                tables=ctx.get("tables", []),
                display_names=ctx.get("display_names", {}),
            )
            qdef_store.save_qdef(qd)
            QMessageBox.information(self, "Saved", f"QDefinition '{name}' saved to DataForge '{forge}'.")
