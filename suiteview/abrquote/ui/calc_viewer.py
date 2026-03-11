"""
ABR Quote — Calculation Viewer (modeless, frameless window).

Shows two tabs:
    1. Mortality Table — all intermediate values in the mortality derivation
    2. APV Table — all intermediate values in the present-value calculation

Designed for Business Analysts to inspect and verify every step of the
ABR quote calculation on a month-by-month basis.

Uses FramelessWindowBase for consistent Crimson Slate theming.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QApplication,
    QMessageBox,
)

from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_RICH, CRIMSON_BG, CRIMSON_SUBTLE,
    SLATE_PRIMARY, SLATE_TEXT, SLATE_DARK, SLATE_LIGHT,
    WHITE, GRAY_DARK, GRAY_TEXT,
    ABR_HEADER_COLORS, ABR_BORDER_COLOR,
    RESULTS_TABLE_STYLE, SCROLL_AREA_STYLE,
    BUTTON_PRIMARY_STYLE, BUTTON_SLATE_STYLE,
)
from ...ui.widgets.frameless_window import FramelessWindowBase

logger = logging.getLogger(__name__)


class CalcViewerDialog(FramelessWindowBase):
    """Modeless frameless window showing detailed month-by-month calculation tables."""

    def __init__(
        self,
        mortality_rows: list[dict],
        apv_rows: list[dict],
        apv_summary: dict,
        policy_info: str = "",
        parent=None,
    ):
        self._mort_rows = mortality_rows
        self._apv_rows = apv_rows
        self._apv_summary = apv_summary
        self._policy_info = policy_info

        title = (
            f"SuiteView:  Calculation Detail — {policy_info}"
            if policy_info
            else "SuiteView:  Calculation Detail"
        )

        super().__init__(
            title=title,
            default_size=(1380, 750),
            min_size=(900, 500),
            parent=parent,
            header_colors=ABR_HEADER_COLORS,
            border_color=ABR_BORDER_COLOR,
        )

    # ── FramelessWindowBase override ──────────────────────────────────

    def build_content(self) -> QWidget:
        """Build the body: tabs for mortality / APV + footer buttons."""
        body = QWidget()
        body.setObjectName("cvBody")
        body.setStyleSheet(f"""
            QWidget#cvBody {{
                background-color: {CRIMSON_BG};
            }}
        """)

        root = QVBoxLayout(body)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Tab widget ──────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 2px solid {CRIMSON_PRIMARY};
                border-radius: 4px;
                background: {WHITE};
            }}
            QTabBar::tab {{
                background: {CRIMSON_SUBTLE};
                color: {CRIMSON_DARK};
                font-weight: bold;
                font-size: 12px;
                padding: 8px 24px;
                border: 1px solid {CRIMSON_PRIMARY};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
                color: {SLATE_TEXT};
                border-color: {SLATE_PRIMARY};
            }}
            QTabBar::tab:hover:!selected {{
                background: {CRIMSON_BG};
            }}
        """)

        # Tab 1: Mortality
        mort_tab = self._build_mortality_tab()
        self.tabs.addTab(mort_tab, "Mortality Derivation")

        # Tab 2: Life Expectancy
        le_tab = self._build_le_tab()
        self.tabs.addTab(le_tab, "Life Expectancy")

        # Tab 3: APV
        apv_tab = self._build_apv_tab()
        self.tabs.addTab(apv_tab, "APV — Present Value")

        root.addWidget(self.tabs, 1)

        # ── Bottom buttons ──────────────────────────────────────────────
        btn_row = QHBoxLayout()

        row_count_label = QLabel(
            f"Mortality: {len(self._mort_rows):,} months  |  "
            f"APV: {len(self._apv_rows):,} months"
        )
        row_count_label.setStyleSheet(f"color: {GRAY_DARK}; font-size: 11px;")
        btn_row.addWidget(row_count_label)

        btn_row.addStretch()

        export_btn = QPushButton("Export to Excel")
        export_btn.setStyleSheet(BUTTON_SLATE_STYLE)
        export_btn.clicked.connect(self._on_export)
        btn_row.addWidget(export_btn)

        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
        copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {CRIMSON_PRIMARY};
                border: 1px solid {CRIMSON_PRIMARY}; border-radius: 6px;
                padding: 8px 20px; font-size: 12px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {CRIMSON_SUBTLE}; }}
        """)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

        return body

    # ── Mortality tab ───────────────────────────────────────────────────

    def _build_mortality_tab(self) -> QTableWidget:
        columns = [
            ("Quote Month", 70),
            ("Policy Year", 72),
            ("Mo in Yr", 58),
            ("Att Age", 55),
            ("qx VBT\n(annual)", 90),
            ("qx × Mult\n(annual)", 90),
            ("qx Improved\n(annual)", 90),
            ("Table\nRating", 55),
            ("qx + Table\n(annual)", 90),
            ("Flat Extra\n($/1000)", 65),
            ("qx + Flat\n(annual)", 90),
            ("qx Capped\n(annual)", 90),
            ("qx Monthly", 90),
            ("px Monthly", 90),
            ("Cum Surv", 90),
        ]

        table = self._create_table(columns, len(self._mort_rows))

        for r, row in enumerate(self._mort_rows):
            self._set_int(table, r, 0, row["quote_month"])
            self._set_int(table, r, 1, row["duration_year"])
            self._set_int(table, r, 2, row["month_in_year"])
            self._set_int(table, r, 3, row["attained_age"])
            self._set_rate(table, r, 4, row["qx_vbt"])
            self._set_rate(table, r, 5, row["qx_multiplied"])
            self._set_rate(table, r, 6, row["qx_improved"])
            # Table Rating applied
            tbl_val = row.get("table_rating_applied", 0.0)
            if tbl_val > 0:
                self._set_decimal(table, r, 7, tbl_val, 2)
            else:
                self._set_text(table, r, 7, "")
            self._set_rate(table, r, 8, row["qx_table_rated"])
            # Flat Extra applied
            flat_val = row.get("flat_extra_applied", 0.0)
            if flat_val > 0:
                self._set_decimal(table, r, 9, flat_val, 3)
            else:
                self._set_text(table, r, 9, "")
            self._set_rate(table, r, 10, row["qx_flat_extra"])
            self._set_rate(table, r, 11, row["qx_capped"])
            self._set_rate(table, r, 12, row["qx_monthly"])
            self._set_rate(table, r, 13, row["px_monthly"])
            self._set_pct(table, r, 14, row["cum_survival"])

            # Highlight year boundaries
            if row["month_in_year"] == 1 and r > 0:
                for c in range(len(columns)):
                    item = table.item(r, c)
                    if item:
                        item.setBackground(QColor(SLATE_LIGHT))

        return table

    # ── Life Expectancy tab ──────────────────────────────────────────────

    def _build_le_tab(self) -> QTableWidget:
        """Build the LE development table.

        Shows month-by-month accumulation of curtate life expectancy:
            - tPx (cumulative survival to start of month)
            - qx_monthly (monthly mortality rate)
            - px_monthly (monthly survival = 1 - qx_monthly)
            - tPx_end (cumulative survival to end of month)
            - running_sum_tPx (sum of tPx_end, in months)
            - cum_LE_years (running_sum / 12)

        Final LE = curtate LE + 0.5 (UDD complete LE approximation).
        """
        columns = [
            ("Quote Month", 70),
            ("Policy Year", 72),
            ("Att Age", 55),
            ("qx Monthly", 90),
            ("px Monthly", 90),
            ("tPx\n(cum surv)", 95),
            ("Sum tPx\n(months)", 95),
            ("Curtate LE\n(years)", 95),
        ]

        # Compute LE development from mortality rows
        le_rows = []
        tp_x = 1.0
        sum_tpx = 0.0

        for row in self._mort_rows:
            qx_m = row["qx_monthly"]
            px_m = 1.0 - qx_m
            tp_x *= px_m
            sum_tpx += tp_x
            curtate_years = sum_tpx / 12.0

            le_rows.append({
                "quote_month": row["quote_month"],
                "duration_year": row["duration_year"],
                "attained_age": row["attained_age"],
                "qx_monthly": qx_m,
                "px_monthly": px_m,
                "tp_x": tp_x,
                "sum_tpx": sum_tpx,
                "curtate_years": curtate_years,
            })

        # Final LE values
        curtate_le = sum_tpx / 12.0 if le_rows else 0.0
        complete_le = curtate_le + 0.5

        # Extra rows for summary
        n_data = len(le_rows)
        n_summary = 3
        table = self._create_table(columns, n_data + n_summary + 1)

        for r, row in enumerate(le_rows):
            self._set_int(table, r, 0, row["quote_month"])
            self._set_int(table, r, 1, row["duration_year"])
            self._set_int(table, r, 2, row["attained_age"])
            self._set_rate(table, r, 3, row["qx_monthly"])
            self._set_rate(table, r, 4, row["px_monthly"])
            self._set_pct(table, r, 5, row["tp_x"])
            self._set_decimal(table, r, 6, row["sum_tpx"], 4)
            self._set_decimal(table, r, 7, row["curtate_years"], 4)

            # Highlight year boundaries
            if row["quote_month"] % 12 == 1 and r > 0:
                for c in range(len(columns)):
                    item = table.item(r, c)
                    if item:
                        item.setBackground(QColor(SLATE_LIGHT))

        # ── Summary rows ────────────────────────────────────────────────
        summary_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        summary_color = QColor(CRIMSON_DARK)
        sr = n_data + 1  # skip a blank separator row

        def _summary_row(row_idx, label, value, fmt_str=".4f"):
            item_label = QTableWidgetItem(label)
            item_label.setFont(summary_font)
            item_label.setForeground(summary_color)
            item_label.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 5, item_label)
            item_val = QTableWidgetItem(f"{value:{fmt_str}}")
            item_val.setFont(summary_font)
            item_val.setForeground(summary_color)
            item_val.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 7, item_val)

        _summary_row(sr, "Sum tPx (months):", sum_tpx)
        _summary_row(sr + 1, "Curtate LE (years):", curtate_le)
        _summary_row(sr + 2, "Complete LE (+ 0.5):", complete_le)

        # Highlight summary rows
        for row_idx in range(sr, sr + 3):
            for c in range(len(columns)):
                item = table.item(row_idx, c)
                if item:
                    item.setBackground(QColor(CRIMSON_SUBTLE))

        # Store for export/copy
        self._le_rows = le_rows
        self._le_summary = {
            "sum_tpx": sum_tpx,
            "curtate_le": curtate_le,
            "complete_le": complete_le,
        }

        return table

    # ── APV tab ─────────────────────────────────────────────────────────

    def _build_apv_tab(self) -> QTableWidget:
        columns = [
            ("Month", 55),
            ("t", 40),
            ("qx Monthly", 85),
            ("px Monthly", 85),
            ("tpx\n(cum surv)", 85),
            ("v^(t+1)\n(benefit)", 90),
            ("v^t\n(premium)", 90),
            ("PVDB(t)\n(this mo)", 95),
            ("PVDB Cum", 100),
            ("Prem Rate\n(per $1K)", 82),
            ("PVFP(t)\n(this mo)", 95),
            ("PVFP Cum", 100),
            ("tpx End", 85),
        ]

        # Extra rows for summary
        n_data = len(self._apv_rows)
        n_summary = 6
        table = self._create_table(columns, n_data + n_summary + 1)

        for r, row in enumerate(self._apv_rows):
            self._set_int(table, r, 0, row["month"])
            self._set_int(table, r, 1, row["t"])
            self._set_rate(table, r, 2, row["qx_monthly"])
            self._set_rate(table, r, 3, row["px_monthly"])
            self._set_pct(table, r, 4, row["tp_x"])
            self._set_decimal(table, r, 5, row["v_benefit"], 10)
            self._set_decimal(table, r, 6, row["v_premium"], 10)
            self._set_money(table, r, 7, row["pvdb_t"])
            self._set_money(table, r, 8, row["pvdb_cum"])
            if row["prem_rate"] > 0:
                self._set_decimal(table, r, 9, row["prem_rate"], 4)
            else:
                self._set_text(table, r, 9, "")
            self._set_money(table, r, 10, row["pvfp_t"])
            self._set_money(table, r, 11, row["pvfp_cum"])
            self._set_pct(table, r, 12, row["tp_x_end"])

            # Highlight year boundaries (rows where premium is applied)
            if row["prem_rate"] > 0:
                for c in range(len(columns)):
                    item = table.item(r, c)
                    if item:
                        item.setBackground(QColor(SLATE_LIGHT))

        # ── Summary rows ────────────────────────────────────────────────
        s = self._apv_summary
        sr = n_data + 1  # skip a blank separator row

        summary_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        summary_color = QColor(CRIMSON_DARK)

        def _summary_row(row_idx, label, value, fmt="money"):
            item_label = QTableWidgetItem(label)
            item_label.setFont(summary_font)
            item_label.setForeground(summary_color)
            item_label.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, 7, item_label)
            if fmt == "money":
                self._set_money(table, row_idx, 8, value)
            elif fmt == "rate":
                self._set_decimal(table, row_idx, 8, value, 10)
            item_val = table.item(row_idx, 8)
            if item_val:
                item_val.setFont(summary_font)
                item_val.setForeground(summary_color)

        _summary_row(sr, "PVFB (raw sum):", s["pvfb_raw"])
        _summary_row(sr + 1, "Cont Mort Adj:", s["cont_mort_adj"], "rate")
        _summary_row(sr + 2, "PVFB (adj × 1000):", s["pvfb_adjusted"])
        _summary_row(sr + 3, "PVFP:", s["pvfp"])
        _summary_row(sr + 4, "Actuarial Discount:", s["actuarial_discount"])

        # Highlight summary rows
        for row_idx in range(sr, sr + 5):
            for c in range(len(columns)):
                item = table.item(row_idx, c)
                if item:
                    item.setBackground(QColor(CRIMSON_SUBTLE))

        return table

    # ── Table factory ───────────────────────────────────────────────────

    def _create_table(self, columns: list[tuple], row_count: int) -> QTableWidget:
        table = QTableWidget(row_count, len(columns))
        table.setStyleSheet(RESULTS_TABLE_STYLE + SCROLL_AREA_STYLE)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        headers = [c[0] for c in columns]
        table.setHorizontalHeaderLabels(headers)

        hh = table.horizontalHeader()
        for i, (_, width) in enumerate(columns):
            hh.resizeSection(i, width)
        hh.setStretchLastSection(True)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        vh = table.verticalHeader()
        vh.setDefaultSectionSize(22)
        vh.setVisible(False)

        return table

    # ── Cell helpers ────────────────────────────────────────────────────

    @staticmethod
    def _set_int(table: QTableWidget, row: int, col: int, value: int):
        item = QTableWidgetItem(str(value))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, col, item)

    @staticmethod
    def _set_text(table: QTableWidget, row: int, col: int, text: str):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, col, item)

    @staticmethod
    def _set_rate(table: QTableWidget, row: int, col: int, value: float):
        """Display a mortality rate with 8 decimal places."""
        item = QTableWidgetItem(f"{value:.8f}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row, col, item)

    @staticmethod
    def _set_pct(table: QTableWidget, row: int, col: int, value: float):
        """Display a percentage/survival with 6 decimals + %."""
        item = QTableWidgetItem(f"{value * 100:.6f}%")
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row, col, item)

    @staticmethod
    def _set_money(table: QTableWidget, row: int, col: int, value: float):
        """Display a money/PV value."""
        if abs(value) < 0.005:
            text = ""
        else:
            text = f"{value:,.6f}"
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row, col, item)

    @staticmethod
    def _set_decimal(table: QTableWidget, row: int, col: int, value: float, places: int = 6):
        item = QTableWidgetItem(f"{value:.{places}f}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row, col, item)

    # ── Export ──────────────────────────────────────────────────────────

    def _on_export(self):
        """Export both tables to a new unsaved Excel workbook via COM."""
        try:
            from win32com.client import dynamic

            excel = dynamic.Dispatch("Excel.Application")
            excel.Visible = True
            excel.ScreenUpdating = False

            wb = excel.Workbooks.Add()

            # ── Sheet 1: Mortality ──────────────────────────────────────
            ws1 = wb.Worksheets(1)
            ws1.Name = "Mortality Derivation"

            mort_headers = (
                "Quote Month", "Policy Year", "Mo in Yr", "Att Age",
                "qx VBT", "qx × Mult", "qx Improved",
                "Table Rating", "qx + Table",
                "Flat Extra", "qx + Flat", "qx Capped",
                "qx Monthly", "px Monthly", "Cum Survival",
            )
            mort_col_count = len(mort_headers)

            # Build all rows as tuples for bulk write
            mort_data = [mort_headers]
            mort_year_boundary_rows = []  # 1-based Excel rows
            for i, row in enumerate(self._mort_rows):
                tbl_val = row.get("table_rating_applied", 0.0)
                flat_val = row.get("flat_extra_applied", 0.0)
                mort_data.append((
                    row["quote_month"], row["duration_year"],
                    row["month_in_year"], row["attained_age"],
                    row["qx_vbt"], row["qx_multiplied"],
                    row["qx_improved"],
                    tbl_val if tbl_val > 0 else "",
                    row["qx_table_rated"],
                    flat_val if flat_val > 0 else "",
                    row["qx_flat_extra"], row["qx_capped"],
                    row["qx_monthly"], row["px_monthly"],
                    row["cum_survival"],
                ))
                if row["month_in_year"] == 1 and i > 0:
                    mort_year_boundary_rows.append(i + 2)  # +2: 1-based + header

            # Bulk write
            total_mort = len(mort_data)
            rng1 = ws1.Range(ws1.Cells(1, 1), ws1.Cells(total_mort, mort_col_count))
            rng1.Value = mort_data

            # Format header row
            hdr1 = ws1.Range(ws1.Cells(1, 1), ws1.Cells(1, mort_col_count))
            hdr1.Font.Bold = True
            hdr1.Font.Color = 0xFFFFFF
            hdr1.Interior.Color = 0x404D00  # Teal dark (BGR: 004D40)
            hdr1.HorizontalAlignment = -4108  # xlCenter

            # Number formats for rate columns and pct column
            if total_mort > 1:
                # qx VBT, qx Improved, qx × Mult (cols 5-7)
                ws1.Range(ws1.Cells(2, 5), ws1.Cells(total_mort, 7)).NumberFormat = "0.00000000"
                # Table Rating (col 8) — keep default
                # qx + Table (col 9)
                ws1.Range(ws1.Cells(2, 9), ws1.Cells(total_mort, 9)).NumberFormat = "0.00000000"
                # Flat Extra (col 10) — keep default
                # qx + Flat, qx Capped, qx Monthly, px Monthly (cols 11-14)
                ws1.Range(ws1.Cells(2, 11), ws1.Cells(total_mort, 14)).NumberFormat = "0.00000000"
                # Cum Survival (col 15)
                ws1.Range(ws1.Cells(2, 15), ws1.Cells(total_mort, 15)).NumberFormat = "0.000000%"

            # Year boundary highlighting
            for yr_row in mort_year_boundary_rows:
                ws1.Range(
                    ws1.Cells(yr_row, 1), ws1.Cells(yr_row, mort_col_count)
                ).Interior.Color = 0xD0F3FF  # FFF3D0 in BGR

            # Freeze top row + auto-filter + auto-fit
            ws1.Range("A2").Select()
            excel.ActiveWindow.FreezePanes = True
            if total_mort > 1:
                ws1.Range(ws1.Cells(1, 1), ws1.Cells(total_mort, mort_col_count)).AutoFilter()
            ws1.Columns.AutoFit()

            # ── Sheet 2: APV ────────────────────────────────────────────
            ws2 = wb.Worksheets.Add(After=ws1)
            ws2.Name = "APV Present Value"

            apv_headers = (
                "Month", "t", "qx Monthly", "px Monthly", "tpx (cum surv)",
                "v^(t+1)", "v^t", "PVDB(t)", "PVDB Cum",
                "Prem Rate", "PVFP(t)", "PVFP Cum", "tpx End",
            )
            apv_col_count = len(apv_headers)

            apv_data = [apv_headers]
            apv_prem_rows = []
            for i, row in enumerate(self._apv_rows):
                apv_data.append((
                    row["month"], row["t"],
                    row["qx_monthly"], row["px_monthly"],
                    row["tp_x"], row["v_benefit"], row["v_premium"],
                    row["pvdb_t"], row["pvdb_cum"],
                    row["prem_rate"], row["pvfp_t"], row["pvfp_cum"],
                    row["tp_x_end"],
                ))
                if row["prem_rate"] > 0:
                    apv_prem_rows.append(i + 2)

            total_apv = len(apv_data)
            rng2 = ws2.Range(ws2.Cells(1, 1), ws2.Cells(total_apv, apv_col_count))
            rng2.Value = apv_data

            # Format header row
            hdr2 = ws2.Range(ws2.Cells(1, 1), ws2.Cells(1, apv_col_count))
            hdr2.Font.Bold = True
            hdr2.Font.Color = 0xFFFFFF
            hdr2.Interior.Color = 0x404D00
            hdr2.HorizontalAlignment = -4108

            # Number formats for data area
            if total_apv > 1:
                ws2.Range(ws2.Cells(2, 3), ws2.Cells(total_apv, 4)).NumberFormat = "0.00000000"
                ws2.Range(ws2.Cells(2, 5), ws2.Cells(total_apv, 5)).NumberFormat = "0.000000%"
                ws2.Range(ws2.Cells(2, 6), ws2.Cells(total_apv, 7)).NumberFormat = "0.0000000000"
                ws2.Range(ws2.Cells(2, 8), ws2.Cells(total_apv, 9)).NumberFormat = "#,##0.000000"
                ws2.Range(ws2.Cells(2, 10), ws2.Cells(total_apv, 10)).NumberFormat = "0.0000"
                ws2.Range(ws2.Cells(2, 11), ws2.Cells(total_apv, 12)).NumberFormat = "#,##0.000000"
                ws2.Range(ws2.Cells(2, 13), ws2.Cells(total_apv, 13)).NumberFormat = "0.000000%"

            # Premium-row highlighting
            for pr_row in apv_prem_rows:
                ws2.Range(
                    ws2.Cells(pr_row, 1), ws2.Cells(pr_row, apv_col_count)
                ).Interior.Color = 0xD0F3FF

            # Summary rows below data
            s = self._apv_summary
            sr = total_apv + 2
            summaries = [
                ("PVFB (raw sum):", s["pvfb_raw"], "#,##0.000000"),
                ("Continuous Mort Adj:", s["cont_mort_adj"], "0.0000000000"),
                ("PVFB (adjusted × 1000):", s["pvfb_adjusted"], "#,##0.00"),
                ("PVFP:", s["pvfp"], "#,##0.000000"),
                ("Actuarial Discount:", s["actuarial_discount"], "#,##0.00"),
            ]
            for i, (label, value, fmt) in enumerate(summaries):
                ws2.Cells(sr + i, 8).Value = label
                ws2.Cells(sr + i, 8).Font.Bold = True
                ws2.Cells(sr + i, 9).Value = value
                ws2.Cells(sr + i, 9).Font.Bold = True
                ws2.Cells(sr + i, 9).NumberFormat = fmt

            # Freeze + filter + fit
            ws2.Activate()
            ws2.Range("A2").Select()
            excel.ActiveWindow.FreezePanes = True
            if total_apv > 1:
                ws2.Range(ws2.Cells(1, 1), ws2.Cells(total_apv, apv_col_count)).AutoFilter()
            ws2.Columns.AutoFit()

            # ── Sheet 3: Life Expectancy ────────────────────────────────
            if hasattr(self, '_le_rows') and self._le_rows:
                ws3 = wb.Worksheets.Add(After=ws2)
                ws3.Name = "Life Expectancy"

                le_headers = (
                    "Quote Month", "Policy Year", "Att Age",
                    "qx Monthly", "px Monthly", "tPx (cum surv)",
                    "Sum tPx (months)", "Curtate LE (years)",
                )
                le_col_count = len(le_headers)

                le_data = [le_headers]
                le_year_rows = []
                for i, row in enumerate(self._le_rows):
                    le_data.append((
                        row["quote_month"], row["duration_year"],
                        row["attained_age"],
                        row["qx_monthly"], row["px_monthly"],
                        row["tp_x"], row["sum_tpx"],
                        row["curtate_years"],
                    ))
                    if row["quote_month"] % 12 == 1 and i > 0:
                        le_year_rows.append(i + 2)

                total_le = len(le_data)
                rng3 = ws3.Range(ws3.Cells(1, 1), ws3.Cells(total_le, le_col_count))
                rng3.Value = le_data

                # Format header
                hdr3 = ws3.Range(ws3.Cells(1, 1), ws3.Cells(1, le_col_count))
                hdr3.Font.Bold = True
                hdr3.Font.Color = 0xFFFFFF
                hdr3.Interior.Color = 0x404D00
                hdr3.HorizontalAlignment = -4108

                # Number formats
                if total_le > 1:
                    ws3.Range(ws3.Cells(2, 4), ws3.Cells(total_le, 5)).NumberFormat = "0.00000000"
                    ws3.Range(ws3.Cells(2, 6), ws3.Cells(total_le, 6)).NumberFormat = "0.000000%"
                    ws3.Range(ws3.Cells(2, 7), ws3.Cells(total_le, 8)).NumberFormat = "0.0000"

                # Year boundary highlighting
                for yr_row in le_year_rows:
                    ws3.Range(
                        ws3.Cells(yr_row, 1), ws3.Cells(yr_row, le_col_count)
                    ).Interior.Color = 0xD0F3FF

                # Summary rows
                s = self._le_summary
                sr = total_le + 2
                summaries = [
                    ("Sum tPx (months):", s["sum_tpx"], "0.0000"),
                    ("Curtate LE (years):", s["curtate_le"], "0.0000"),
                    ("Complete LE (+ 0.5):", s["complete_le"], "0.0000"),
                ]
                for i, (label, value, fmt) in enumerate(summaries):
                    ws3.Cells(sr + i, 6).Value = label
                    ws3.Cells(sr + i, 6).Font.Bold = True
                    ws3.Cells(sr + i, 8).Value = value
                    ws3.Cells(sr + i, 8).Font.Bold = True
                    ws3.Cells(sr + i, 8).NumberFormat = fmt

                # Freeze + filter + fit
                ws3.Activate()
                ws3.Range("A2").Select()
                excel.ActiveWindow.FreezePanes = True
                if total_le > 1:
                    ws3.Range(ws3.Cells(1, 1), ws3.Cells(total_le, le_col_count)).AutoFilter()
                ws3.Columns.AutoFit()

            # Activate the first sheet and select A1
            ws1.Activate()
            ws1.Range("A1").Select()
            excel.ScreenUpdating = True

        except ImportError:
            QMessageBox.warning(
                self, "Error",
                "win32com is not available. Cannot export to Excel.",
            )
        except Exception as e:
            logger.error(f"Export error: {e}", exc_info=True)
            QMessageBox.warning(self, "Export Error", f"Could not export:\n{e}")

    def _on_copy(self):
        """Copy currently visible tab's data as TSV to clipboard."""
        current = self.tabs.currentIndex()
        if current == 0:
            lines = self._mort_to_tsv()
        elif current == 1:
            lines = self._le_to_tsv()
        else:
            lines = self._apv_to_tsv()

        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(lines))

    def _mort_to_tsv(self) -> list[str]:
        headers = [
            "QuoteMonth", "PolicyYear", "MoInYr", "AttAge",
            "qx_VBT", "qx_Multiplied", "qx_Improved",
            "TableRating", "qx_TableRated",
            "FlatExtra", "qx_FlatExtra", "qx_Capped",
            "qx_Monthly", "px_Monthly", "CumSurvival",
        ]
        lines = ["\t".join(headers)]
        for row in self._mort_rows:
            tbl_val = row.get("table_rating_applied", 0.0)
            flat_val = row.get("flat_extra_applied", 0.0)
            lines.append("\t".join([
                str(row["quote_month"]), str(row["duration_year"]),
                str(row["month_in_year"]), str(row["attained_age"]),
                f'{row["qx_vbt"]:.8f}', f'{row["qx_multiplied"]:.8f}',
                f'{row["qx_improved"]:.8f}',
                f'{tbl_val:.2f}' if tbl_val > 0 else '',
                f'{row["qx_table_rated"]:.8f}',
                f'{flat_val:.3f}' if flat_val > 0 else '',
                f'{row["qx_flat_extra"]:.8f}', f'{row["qx_capped"]:.8f}',
                f'{row["qx_monthly"]:.8f}', f'{row["px_monthly"]:.8f}',
                f'{row["cum_survival"]:.8f}',
            ]))
        return lines

    def _apv_to_tsv(self) -> list[str]:
        headers = [
            "Month", "t", "qx_Monthly", "px_Monthly", "tpx",
            "v_benefit", "v_premium", "PVDB_t", "PVDB_cum",
            "PremRate", "PVFP_t", "PVFP_cum", "tpx_end",
        ]
        lines = ["\t".join(headers)]
        for row in self._apv_rows:
            lines.append("\t".join([
                str(row["month"]), str(row["t"]),
                f'{row["qx_monthly"]:.8f}', f'{row["px_monthly"]:.8f}',
                f'{row["tp_x"]:.8f}', f'{row["v_benefit"]:.10f}',
                f'{row["v_premium"]:.10f}', f'{row["pvdb_t"]:.6f}',
                f'{row["pvdb_cum"]:.6f}', f'{row["prem_rate"]:.4f}',
                f'{row["pvfp_t"]:.6f}', f'{row["pvfp_cum"]:.6f}',
                f'{row["tp_x_end"]:.8f}',
            ]))

        # Summary
        s = self._apv_summary
        lines.append("")
        lines.append(f"PVFB (raw sum):\t{s['pvfb_raw']:.6f}")
        lines.append(f"Cont Mort Adj:\t{s['cont_mort_adj']:.10f}")
        lines.append(f"PVFB (adjusted):\t{s['pvfb_adjusted']:.2f}")
        lines.append(f"PVFP:\t{s['pvfp']:.6f}")
        lines.append(f"Actuarial Discount:\t{s['actuarial_discount']:.2f}")

        return lines

    def _le_to_tsv(self) -> list[str]:
        headers = [
            "QuoteMonth", "PolicyYear", "AttAge",
            "qx_Monthly", "px_Monthly", "tPx",
            "SumTPx", "CurtateLE_Yrs",
        ]
        lines = ["\t".join(headers)]
        for row in getattr(self, '_le_rows', []):
            lines.append("\t".join([
                str(row["quote_month"]), str(row["duration_year"]),
                str(row["attained_age"]),
                f'{row["qx_monthly"]:.8f}', f'{row["px_monthly"]:.8f}',
                f'{row["tp_x"]:.8f}',
                f'{row["sum_tpx"]:.4f}', f'{row["curtate_years"]:.4f}',
            ]))

        # Summary
        s = getattr(self, '_le_summary', {})
        if s:
            lines.append("")
            lines.append(f"Sum tPx (months):\t{s['sum_tpx']:.4f}")
            lines.append(f"Curtate LE (years):\t{s['curtate_le']:.4f}")
            lines.append(f"Complete LE (+ 0.5):\t{s['complete_le']:.4f}")

        return lines
