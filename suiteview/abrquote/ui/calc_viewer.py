"""
ABR Quote — Calculation Viewer (modeless, frameless window).

Shows up to five tabs:
    1. Policy Info      — policy details (mirrors Print Detail sheet)
    2. Assessment       — medical assessment inputs and derived values
    3. Mortality Table  — all intermediate values in the mortality derivation
    4. Life Expectancy  — curtate/complete LE development
    5. APV Table        — all intermediate values in the present-value calculation

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
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QApplication,
    QMessageBox, QScrollArea, QGridLayout,
)

from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_BG, CRIMSON_SUBTLE,
    SLATE_PRIMARY, SLATE_TEXT, SLATE_LIGHT,
    WHITE, GRAY_DARK, ABR_HEADER_COLORS, ABR_BORDER_COLOR,
    RESULTS_TABLE_STYLE, SCROLL_AREA_STYLE,
    BUTTON_SLATE_STYLE,
)
from ...ui.widgets.frameless_window import FramelessWindowBase
from .view_models import CalcViewerModel

logger = logging.getLogger(__name__)


class CalcViewerDialog(FramelessWindowBase):
    """Modeless frameless window showing detailed month-by-month calculation tables."""

    def __init__(self, model: CalcViewerModel, parent=None):
        self._model = model
        self._mort_rows = model.mortality_rows
        self._apv_rows = model.apv_rows
        self._apv_summary = model.apv_summary
        self._policy_info = model.policy_info
        self._policy = model.policy
        self._assessment = model.assessment
        self._result = model.result
        self._derived_values = model.derived_values
        self._after_partial_override = model.acceleration.after_partial_override
        self._warnings = model.acceleration.warnings
        self._accel_amount_input = model.acceleration.acceleration_amount
        self._min_face_amount_input = model.acceleration.min_face_amount

        title = (
            f"SuiteView:  Calculation Detail — {self._policy_info}"
            if self._policy_info
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

        # Tab: Policy Info (if data available)
        if self._policy:
            pi_tab = self._build_policy_info_tab()
            self.tabs.addTab(pi_tab, "Policy Info")

        # Tab: Assessment (if data available)
        if self._assessment:
            assess_tab = self._build_assessment_tab()
            self.tabs.addTab(assess_tab, "Assessment")

        # Tab: Mortality
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

    # ── Policy Info tab ─────────────────────────────────────────────────

    def _build_policy_info_tab(self) -> QWidget:
        """Build a read-only display of policy details matching Print Detail."""
        scroll, container, grid = self._new_policy_info_tab()
        fonts = self._policy_info_fonts()
        row = 0
        row = self._add_policy_detail_fields(grid, row, fonts)
        row = self._add_quote_parameter_fields(grid, row, fonts)
        row = self._add_rider_fields(grid, row, fonts)
        grid.setRowStretch(row, 1)
        scroll.setWidget(container)
        return scroll

    def _new_policy_info_tab(self) -> tuple[QScrollArea, QWidget, QGridLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(SCROLL_AREA_STYLE)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setSpacing(4)
        grid.setColumnMinimumWidth(0, 180)
        grid.setColumnMinimumWidth(1, 280)
        return scroll, container, grid

    def _policy_info_fonts(self) -> tuple[QFont, QFont, QFont]:
        return (
            QFont("Segoe UI", 11, QFont.Weight.Bold),
            QFont("Segoe UI", 10, QFont.Weight.Bold),
            QFont("Segoe UI", 10),
        )

    def _policy_info_section(
        self,
        grid: QGridLayout,
        row: int,
        title: str,
        font: QFont,
    ) -> int:
        if row > 0:
            row += 1
        label = QLabel(title)
        label.setFont(font)
        label.setStyleSheet(
            f"color: {WHITE}; background: {CRIMSON_DARK}; "
            f"padding: 3px 8px; border-radius: 3px;"
        )
        grid.addWidget(label, row, 0, 1, 2)
        return row + 1

    def _policy_info_field(
        self,
        grid: QGridLayout,
        row: int,
        label: str,
        value,
        fonts: tuple[QFont, QFont, QFont],
    ) -> int:
        _section_font, label_font, value_font = fonts
        label_widget = QLabel(label)
        label_widget.setFont(label_font)
        label_widget.setStyleSheet(f"color: {CRIMSON_DARK};")
        label_widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(label_widget, row, 0)
        value_widget = QLabel(str(value))
        value_widget.setFont(value_font)
        value_widget.setStyleSheet(f"color: {GRAY_DARK};")
        value_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(value_widget, row, 1)
        return row + 1

    def _add_policy_detail_fields(
        self,
        grid: QGridLayout,
        row: int,
        fonts: tuple[QFont, QFont, QFont],
    ) -> int:
        from ..models.abr_constants import MODAL_LABELS, PLAN_CODE_INFO

        p = self._policy
        row = self._policy_info_section(grid, row, "Policy Details", fonts[0])
        row = self._policy_info_field(grid, row, "Policy Number:", p.policy_number, fonts)
        row = self._policy_info_field(grid, row, "Insured:", p.insured_name or "—", fonts)
        plan_info = PLAN_CODE_INFO.get(p.plan_code.upper(), None) if p.plan_code else None
        plan_desc = f"{plan_info[1]} ({plan_info[0]}-Year Level)" if plan_info else "—"
        row = self._policy_info_field(grid, row, "Plancode:", p.plan_code or "—", fonts)
        row = self._policy_info_field(grid, row, "Plan Description:", plan_desc, fonts)
        sex_display = {"M": "Male", "F": "Female", "U": "Unisex"}.get(p.sex, p.sex or "—")
        fields = [
            ("Sex:", sex_display),
            ("Rate Sex:", p.rate_sex or "—"),
            ("Issue Age:", str(p.issue_age)),
            ("Attained Age:", str(p.attained_age)),
            ("Rate Class:", p.rate_class or "—"),
            ("Face Amount:", f"${p.face_amount:,.2f}" if p.face_amount else "—"),
            ("Min Face:", f"${p.min_face_amount:,.0f}"),
            ("Issue State:", p.issue_state or "—"),
            ("Issue Date:", p.issue_date.strftime("%m/%d/%Y") if p.issue_date else "—"),
            ("Policy Year:", str(p.policy_year)),
            ("Month of Year:", str(p.policy_month)),
            ("Base Plancode:", p.base_plancode or "—"),
            ("Billing Mode:", MODAL_LABELS.get(p.billing_mode, str(p.billing_mode))),
            ("Modal Premium:", f"${p.modal_premium:,.2f}" if p.modal_premium else "—"),
            ("Table Rating:", str(p.table_rating)),
            ("Annual Flat Extra:", f"${p.flat_extra:.2f}" if p.flat_extra > 0 else "None"),
            (
                "Flat Cease Date:",
                p.flat_cease_date.strftime("%m/%d/%Y") if p.flat_cease_date else "—",
            ),
            ("Reinsurers:", p.reinsurers or "(none)"),
        ]
        for label, value in fields:
            row = self._policy_info_field(grid, row, label, value, fonts)
        return row

    def _add_quote_parameter_fields(
        self,
        grid: QGridLayout,
        row: int,
        fonts: tuple[QFont, QFont, QFont],
    ) -> int:
        r = self._result
        if not r:
            return row
        row = self._policy_info_section(grid, row, "Quote Parameters", fonts[0])
        fields = [
            ("Quote Date:", r.quote_date.strftime("%m/%d/%Y") if r.quote_date else "—"),
            ("ABR Interest Rate:", f"{r.abr_interest_rate * 100:.2f}%"),
            ("Per Diem (Daily):", f"${r.per_diem_daily:,.2f}"),
            ("Per Diem (Annual):", f"${r.per_diem_annual:,.2f}"),
        ]
        for label, value in fields:
            row = self._policy_info_field(grid, row, label, value, fonts)
        return row

    def _add_rider_fields(
        self,
        grid: QGridLayout,
        row: int,
        fonts: tuple[QFont, QFont, QFont],
    ) -> int:
        p = self._policy
        row = self._policy_info_section(grid, row, "Riders / Coverages", fonts[0])
        if not p.riders:
            return self._policy_info_field(grid, row, "No riders.", "", fonts)
        for rider in p.riders:
            rider_desc = f"{rider.plancode} ({rider.rider_type})"
            if rider.benefit_type:
                rider_desc += f" — BNF {rider.benefit_type}{rider.benefit_subtype or ''}"
            row = self._policy_info_field(
                grid,
                row,
                rider_desc,
                f"${rider.fallback_premium:,.2f}/yr",
                fonts,
            )
        return row

    # ── Assessment tab ──────────────────────────────────────────────────

    def _build_assessment_tab(self) -> QWidget:
        """Build a read-only display of assessment inputs and derived values."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(SCROLL_AREA_STYLE)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setSpacing(4)
        grid.setColumnMinimumWidth(0, 200)
        grid.setColumnMinimumWidth(1, 250)
        fonts = (
            QFont("Segoe UI", 11, QFont.Weight.Bold),
            QFont("Segoe UI", 10, QFont.Weight.Bold),
            QFont("Segoe UI", 10),
        )
        row = 0
        row = self._add_assessment_inputs(grid, row, fonts)
        row = self._add_derived_assessment_values(grid, row, fonts)
        if self._result:
            row = self._add_result_summary(grid, row, fonts)
        row = self._add_assessment_warnings(grid, row, fonts[0])
        grid.setRowStretch(row, 1)
        scroll.setWidget(container)
        return scroll

    def _assessment_section(self, grid, row: int, title: str, font: QFont) -> int:
        if row > 0:
            row += 1
        label = QLabel(title)
        label.setFont(font)
        label.setStyleSheet(
            f"color: {WHITE}; background: {CRIMSON_DARK}; "
            f"padding: 3px 8px; border-radius: 3px;"
        )
        grid.addWidget(label, row, 0, 1, 2)
        return row + 1

    def _assessment_field(self, grid, row: int, label: str, value, fonts, col: int = 0) -> int:
        _section_font, label_font, value_font = fonts
        label_widget = QLabel(label)
        label_widget.setFont(label_font)
        label_widget.setStyleSheet(f"color: {CRIMSON_DARK};")
        label_widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(label_widget, row, col)
        value_widget = QLabel(str(value))
        value_widget.setFont(value_font)
        value_widget.setStyleSheet(f"color: {GRAY_DARK};")
        value_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(value_widget, row, col + 1)
        return row + 1

    def _add_assessment_inputs(self, grid, row: int, fonts) -> int:
        a = self._assessment
        row = self._assessment_section(grid, row, "Rider Configuration", fonts[0])
        row = self._assessment_field(grid, row, "Rider Type:", a.rider_type, fonts)
        row = self._assessment_section(grid, row, "Assessment Inputs", fonts[0])
        for label, value in self._assessment_input_rows(a):
            row = self._assessment_field(grid, row, label, value, fonts)
        return row

    def _assessment_input_rows(self, a) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        if a.use_five_year:
            rows += [("5-Year Survival Rate:", f"{a.five_year_survival}"),
                     ("  Return to Normal:", "Yes" if a.use_return_5yr else "No")]
        if a.use_ten_year:
            rows += [("10-Year Survival Rate:", f"{a.ten_year_survival}"),
                     ("  Return to Normal:", "Yes" if a.use_return_10yr else "No")]
        if a.use_le:
            rows.append(("Life Expectancy:", f"{a.life_expectancy_years} years"))
        if a.use_increased_decrement:
            rows += [("Increased Decrement:", f"{a.direct_increased_decrement:.0f}%"),
                     ("  Start/Stop Year:", f"{a.incr_decrement_start_year} — {a.incr_decrement_stop_year}")]
        if a.use_table:
            rows += [("Table (rating):", f"{a.direct_table_rating}"),
                     ("  Start/Stop Year:", f"{a.table_start_year} — {a.table_stop_year}")]
        if a.use_flat:
            rows += [("Flat ($/1000):", f"${a.direct_flat_extra:.2f}"),
                     ("  Start/Stop Year:", f"{a.flat_start_year} — {a.flat_stop_year}")]
        if a.use_table_2:
            rows += [("Table 2 (rating):", f"{a.direct_table_rating_2}"),
                     ("  Start/Stop Year:", f"{a.table_2_start_year} — {a.table_2_stop_year}")]
        if a.use_flat_2:
            rows += [("Flat 2 ($/1000):", f"${a.direct_flat_extra_2:.2f}"),
                     ("  Start/Stop Year:", f"{a.flat_2_start_year} — {a.flat_2_stop_year}")]
        rows.append(("In Lieu Of:", "Yes" if a.in_lieu_of else "No (In Addition To)"))
        return rows

    def _add_derived_assessment_values(self, grid, row: int, fonts) -> int:
        a = self._assessment
        row = self._assessment_section(grid, row, "Derived Substandard Values", fonts[0])
        if not self._derived_values:
            row = self._assessment_field(grid, row, "Derived Table Rating:", f"{a.derived_table_rating:.4f}", fonts)
            if a.use_five_year and a.use_ten_year:
                row = self._assessment_field(grid, row, "  5yr Table Rating:", f"{a.derived_table_rating_5yr:.4f}", fonts)
                row = self._assessment_field(grid, row, "  10yr Table Rating:", f"{a.derived_table_rating_10yr:.4f}", fonts)
            return self._assessment_field(grid, row, "Life Expectancy (rounded):", f"{a.life_expectancy_rounded}", fonts)
        grid.setColumnMinimumWidth(2, 16)
        grid.setColumnMinimumWidth(3, 200)
        grid.setColumnMinimumWidth(4, 250)
        self._derived_headers(grid, row, fonts[1])
        row += 1
        for labels in self._derived_value_rows():
            self._derived_value_row(grid, row, labels, fonts)
            row += 1
        return row

    def _derived_headers(self, grid, row: int, font: QFont) -> None:
        for text, col in (("Current (Unmodified)", 0), ("Modified (Substandard Applied)", 3)):
            label = QLabel(text)
            label.setFont(font)
            label.setStyleSheet(f"color: {CRIMSON_DARK}; text-decoration: underline;")
            grid.addWidget(label, row, col, 1, 2, Qt.AlignmentFlag.AlignCenter)

    def _derived_value_rows(self):
        return [
            ("5-Year Survival:", "std_survival_5yr", "5-Year Survival:", "mod_survival_5yr"),
            ("10-Year Survival:", "std_survival_10yr", "10-Year Survival:", "mod_survival_10yr"),
            ("Life Expectancy:", "std_le", "Life Expectancy:", "mod_le"),
            ("Table Rating:", "std_table_rating", "Table Ratings:", "table_rating"),
            ("Flat Extra:", "std_flat_extra", "Flat Extras:", "flat_extra"),
        ]

    def _derived_value_row(self, grid, row: int, labels, fonts) -> None:
        dv = self._derived_values
        std_label, std_key, mod_label, mod_key = labels
        self._assessment_field(grid, row, std_label, dv.get(std_key, "—"), fonts, col=0)
        self._assessment_field(grid, row, mod_label, dv.get(mod_key, "—"), fonts, col=3)

    def _add_result_summary(self, grid, row: int, fonts) -> int:
        r = self._result
        p = self._policy
        is_ul = p and p.product_type in ("UL", "IUL", "ISWL")
        row = self._assessment_section(grid, row, "Results Summary", fonts[0])
        grid.setColumnMinimumWidth(3, 100)
        grid.setColumnMinimumWidth(4, 150)
        row = self._add_full_acceleration_summary(grid, row, fonts)
        row = self._add_partial_acceleration_summary(grid, row, fonts)
        return self._add_premium_impact_summary(grid, row, fonts, is_ul)

    def _add_full_acceleration_summary(self, grid, row: int, fonts) -> int:
        r = self._result
        p = self._policy
        row = self._assessment_field(grid, row, "", "FULL ACCELERATION", fonts)
        accel_display = self._accel_amount_input if self._accel_amount_input > 0 else (p.face_amount if p else 0)
        row = self._assessment_field(grid, row, "Acceleration Amount Input:", f"${accel_display:,.2f}" if accel_display else "—", fonts)
        apv_start = row
        for label, value in [
            ("Eligible Death Benefit:", f"${r.full_eligible_db:,.2f}"),
            ("Actuarial Discount:", f"${r.full_actuarial_discount:,.2f}"),
            ("Administrative Fee:", f"${r.full_admin_fee:,.2f}"),
            ("Calculated Benefit:", f"${max(0.0, r.full_accel_benefit):,.2f}"),
            ("Benefit Ratio:", f"{r.full_benefit_ratio * 100:.2f}%"),
        ]:
            row = self._assessment_field(grid, row, label, value, fonts)
        self._add_apv_side_labels(grid, apv_start, [r.apv_fb, r.apv_fp, r.apv_fd], fonts)
        return row

    def _add_partial_acceleration_summary(self, grid, row: int, fonts) -> int:
        r = self._result
        p = self._policy
        row = self._assessment_field(grid, row, "", "", fonts)
        if r.partial_eligible_db <= 0:
            return self._assessment_field(grid, row, "Partial Acceleration:", "NOT ALLOWED — At Minimum Face", fonts)
        row = self._assessment_field(grid, row, "", "MAX PARTIAL ACCELERATION", fonts)
        min_face_display = self._min_face_amount_input if self._min_face_amount_input > 0 else (p.min_face_amount if p else 0)
        row = self._assessment_field(grid, row, "Min Face Amount Input:", f"${min_face_display:,.0f}" if min_face_display else "—", fonts)
        apv_start = row
        for label, value in [
            ("Eligible Death Benefit:", f"${r.partial_eligible_db:,.2f}"),
            ("Actuarial Discount:", f"${r.partial_actuarial_discount:,.2f}"),
            ("Administrative Fee:", f"${r.partial_admin_fee:,.2f}"),
            ("Calculated Benefit:", f"${max(0.0, r.partial_accel_benefit):,.2f}"),
            ("Benefit Ratio:", f"{r.partial_benefit_ratio * 100:.2f}%"),
        ]:
            row = self._assessment_field(grid, row, label, value, fonts)
        ratio = r.partial_eligible_db / r.full_eligible_db if r.full_eligible_db > 0 else 0.0
        self._add_apv_side_labels(grid, apv_start, [r.apv_fb * ratio, r.apv_fp * ratio, r.apv_fd * ratio], fonts)
        return row

    def _add_apv_side_labels(self, grid, start_row: int, values: list[float], fonts) -> None:
        for offset, (label, value) in enumerate(zip(("APV_FB:", "APV_FP:", "APV_FD:"), values)):
            self._assessment_field(grid, start_row + offset, label, f"${value:,.2f}", fonts, col=3)

    def _add_premium_impact_summary(self, grid, row: int, fonts, is_ul: bool) -> int:
        r = self._result
        row = self._assessment_field(grid, row, "", "", fonts)
        row = self._assessment_field(
            grid, row,
            "Last Monthly Deduction:" if is_ul else "Premium Before:",
            r.premium_before,
            fonts,
        )
        row = self._assessment_field(grid, row, "After (Full Accel):", f"${r.premium_after_full:,.2f}", fonts)
        if r.partial_eligible_db <= 0:
            return self._assessment_field(grid, row, "After (Partial):", "NOT ALLOWED", fonts)
        value = self._after_partial_override if is_ul and self._after_partial_override else r.premium_after_partial
        return self._assessment_field(grid, row, "After (Partial):", value, fonts)

    def _add_assessment_warnings(self, grid, row: int, font: QFont) -> int:
        warnings = list(self._result.messages) if self._result else []
        warnings.extend(self._warnings)
        if not warnings:
            return row
        row = self._assessment_section(grid, row, "Messages", font)
        for message in warnings:
            label = QLabel(f"• {message}")
            label.setWordWrap(True)
            label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            label.setStyleSheet("color: #C62828; padding: 2px 0;")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(label, row, 0, 1, 5)
            row += 1
        return row

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
            ("Table\nRating", 72),
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
                self._set_decimal(table, r, 7, tbl_val, 4)
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
            ("Death\nBenefit", 90),
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
            self._set_money(table, r, 7, row.get("death_benefit", 0.0))
            self._set_money(table, r, 8, row["pvdb_t"])
            self._set_money(table, r, 9, row["pvdb_cum"])
            if row["prem_rate"] > 0:
                self._set_decimal(table, r, 10, row["prem_rate"], 4)
            else:
                self._set_text(table, r, 10, "")
            self._set_money(table, r, 11, row["pvfp_t"])
            self._set_money(table, r, 12, row["pvfp_cum"])
            self._set_pct(table, r, 13, row["tp_x_end"])

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
            table.setItem(row_idx, 8, item_label)
            if fmt == "money":
                self._set_money(table, row_idx, 9, value)
            elif fmt == "rate":
                self._set_decimal(table, row_idx, 9, value, 10)
            item_val = table.item(row_idx, 9)
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
        """Export full detail workbook to a new unsaved Excel workbook via COM."""
        if not self._policy or not self._result:
            QMessageBox.warning(self, "Export", "No results available to export.")
            return

        try:
            from ..core.output_spec import build_detail_workbook_spec, write_excel_com

            spec = build_detail_workbook_spec(
                self._policy,
                self._result,
                self._assessment,
                self._mort_rows,
                self._apv_rows,
                self._apv_summary,
                derived_values=self._derived_values,
                accel_amount=self._accel_amount_input or self._policy.face_amount,
                min_face_amount=self._min_face_amount_input or self._policy.min_face_amount,
                after_partial_override=self._after_partial_override,
                apv_sheet_name="APV Present Value",
                messages=self._warnings or self._result.messages,
            )
            write_excel_com(spec)
        except ImportError:
            QMessageBox.warning(
                self,
                "Error",
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
            "v_benefit", "v_premium", "DeathBenefit", "PVDB_t", "PVDB_cum",
            "PremRate", "PVFP_t", "PVFP_cum", "tpx_end",
        ]
        lines = ["\t".join(headers)]
        for row in self._apv_rows:
            lines.append("\t".join([
                str(row["month"]), str(row["t"]),
                f'{row["qx_monthly"]:.8f}', f'{row["px_monthly"]:.8f}',
                f'{row["tp_x"]:.8f}', f'{row["v_benefit"]:.10f}',
                f'{row["v_premium"]:.10f}', f'{row.get("death_benefit", 0.0):.2f}',
                f'{row["pvdb_t"]:.6f}',
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
