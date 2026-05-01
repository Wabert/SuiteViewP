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
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QApplication,
    QMessageBox, QScrollArea, QGridLayout,
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
        policy=None,
        assessment=None,
        result=None,
        derived_values: dict | None = None,
        after_partial_override: str = "",
        warnings: list[str] | None = None,
        accel_amount_input: float = 0.0,
        min_face_amount_input: float = 0.0,
        parent=None,
    ):
        self._mort_rows = mortality_rows
        self._apv_rows = apv_rows
        self._apv_summary = apv_summary
        self._policy_info = policy_info
        self._policy = policy
        self._assessment = assessment
        self._result = result
        self._derived_values = derived_values or {}
        self._after_partial_override = after_partial_override
        self._warnings = warnings or []
        self._accel_amount_input = accel_amount_input
        self._min_face_amount_input = min_face_amount_input

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
        from ..models.abr_constants import PLAN_CODE_INFO, MODAL_LABELS

        p = self._policy
        r = self._result

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(SCROLL_AREA_STYLE)

        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setSpacing(4)
        grid.setColumnMinimumWidth(0, 180)
        grid.setColumnMinimumWidth(1, 280)

        section_font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        label_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        value_font = QFont("Segoe UI", 10)
        section_color = QColor(CRIMSON_DARK)

        row = 0

        def _section(title):
            nonlocal row
            if row > 0:
                row += 1
            lbl = QLabel(title)
            lbl.setFont(section_font)
            lbl.setStyleSheet(
                f"color: {WHITE}; background: {CRIMSON_DARK}; "
                f"padding: 3px 8px; border-radius: 3px;"
            )
            grid.addWidget(lbl, row, 0, 1, 2)
            row += 1

        def _field(label, value):
            nonlocal row
            lbl = QLabel(label)
            lbl.setFont(label_font)
            lbl.setStyleSheet(f"color: {CRIMSON_DARK};")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, row, 0)
            val = QLabel(str(value))
            val.setFont(value_font)
            val.setStyleSheet(f"color: {GRAY_DARK};")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(val, row, 1)
            row += 1

        _section("Policy Details")
        _field("Policy Number:", p.policy_number)
        _field("Insured:", p.insured_name or "—")

        plan_info = PLAN_CODE_INFO.get(p.plan_code.upper(), None) if p.plan_code else None
        plan_desc = f"{plan_info[1]} ({plan_info[0]}-Year Level)" if plan_info else "—"
        _field("Plancode:", p.plan_code or "—")
        _field("Plan Description:", plan_desc)

        sex_display = {"M": "Male", "F": "Female", "U": "Unisex"}.get(p.sex, p.sex or "—")
        _field("Sex:", sex_display)
        _field("Rate Sex:", p.rate_sex or "—")
        _field("Issue Age:", str(p.issue_age))
        _field("Attained Age:", str(p.attained_age))
        _field("Rate Class:", p.rate_class or "—")
        _field("Face Amount:", f"${p.face_amount:,.2f}" if p.face_amount else "—")
        _field("Min Face:", f"${p.min_face_amount:,.0f}")
        _field("Issue State:", p.issue_state or "—")
        _field("Issue Date:", p.issue_date.strftime("%m/%d/%Y") if p.issue_date else "—")
        _field("Policy Year:", str(p.policy_year))
        _field("Month of Year:", str(p.policy_month))
        _field("Base Plancode:", p.base_plancode or "—")
        _field("Billing Mode:", MODAL_LABELS.get(p.billing_mode, str(p.billing_mode)))
        _field("Modal Premium:", f"${p.modal_premium:,.2f}" if p.modal_premium else "—")
        _field("Table Rating:", str(p.table_rating))
        _field("Annual Flat Extra:", f"${p.flat_extra:.2f}" if p.flat_extra > 0 else "None")
        _field("Flat Cease Date:", p.flat_cease_date.strftime("%m/%d/%Y") if p.flat_cease_date else "—")
        _field("Reinsurers:", p.reinsurers or "(none)")

        if r:
            _section("Quote Parameters")
            _field("Quote Date:", r.quote_date.strftime("%m/%d/%Y") if r.quote_date else "—")
            _field("ABR Interest Rate:", f"{r.abr_interest_rate * 100:.2f}%")
            _field("Per Diem (Daily):", f"${r.per_diem_daily:,.2f}")
            _field("Per Diem (Annual):", f"${r.per_diem_annual:,.2f}")

        _section("Riders / Coverages")
        if p.riders:
            for rider in p.riders:
                rider_desc = f"{rider.plancode} ({rider.rider_type})"
                if rider.benefit_type:
                    rider_desc += f" — BNF {rider.benefit_type}{rider.benefit_subtype or ''}"
                _field(rider_desc, f"${rider.fallback_premium:,.2f}/yr")
        else:
            _field("No riders.", "")

        grid.setRowStretch(row, 1)
        scroll.setWidget(container)
        return scroll

    # ── Assessment tab ──────────────────────────────────────────────────

    def _build_assessment_tab(self) -> QWidget:
        """Build a read-only display of assessment inputs and derived values."""
        a = self._assessment
        r = self._result

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(SCROLL_AREA_STYLE)

        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setSpacing(4)
        grid.setColumnMinimumWidth(0, 200)
        grid.setColumnMinimumWidth(1, 250)

        section_font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        label_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        value_font = QFont("Segoe UI", 10)

        row = 0

        def _section(title):
            nonlocal row
            if row > 0:
                row += 1
            lbl = QLabel(title)
            lbl.setFont(section_font)
            lbl.setStyleSheet(
                f"color: {WHITE}; background: {CRIMSON_DARK}; "
                f"padding: 3px 8px; border-radius: 3px;"
            )
            grid.addWidget(lbl, row, 0, 1, 2)
            row += 1

        def _field(label, value, col=0):
            nonlocal row
            lbl = QLabel(label)
            lbl.setFont(label_font)
            lbl.setStyleSheet(f"color: {CRIMSON_DARK};")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, row, col)
            val = QLabel(str(value))
            val.setFont(value_font)
            val.setStyleSheet(f"color: {GRAY_DARK};")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(val, row, col + 1)
            row += 1

        _section("Rider Configuration")
        _field("Rider Type:", a.rider_type)

        _section("Assessment Inputs")
        if a.use_five_year:
            _field("5-Year Survival Rate:", f"{a.five_year_survival}")
            _field("  Return to Normal:", "Yes" if a.use_return_5yr else "No")
        if a.use_ten_year:
            _field("10-Year Survival Rate:", f"{a.ten_year_survival}")
            _field("  Return to Normal:", "Yes" if a.use_return_10yr else "No")
        if a.use_le:
            _field("Life Expectancy:", f"{a.life_expectancy_years} years")
        if a.use_increased_decrement:
            _field("Increased Decrement:", f"{a.direct_increased_decrement:.0f}%")
            _field("  Start/Stop Year:", f"{a.incr_decrement_start_year} — {a.incr_decrement_stop_year}")
        if a.use_table:
            _field("Table (rating):", f"{a.direct_table_rating}")
            _field("  Start/Stop Year:", f"{a.table_start_year} — {a.table_stop_year}")
        if a.use_flat:
            _field("Flat ($/1000):", f"${a.direct_flat_extra:.2f}")
            _field("  Start/Stop Year:", f"{a.flat_start_year} — {a.flat_stop_year}")
        if a.use_table_2:
            _field("Table 2 (rating):", f"{a.direct_table_rating_2}")
            _field("  Start/Stop Year:", f"{a.table_2_start_year} — {a.table_2_stop_year}")
        if a.use_flat_2:
            _field("Flat 2 ($/1000):", f"${a.direct_flat_extra_2:.2f}")
            _field("  Start/Stop Year:", f"{a.flat_2_start_year} — {a.flat_2_stop_year}")
        _field("In Lieu Of:", "Yes" if a.in_lieu_of else "No (In Addition To)")

        _section("Derived Substandard Values")
        dv = self._derived_values
        if dv:
            # Side-by-side: Current vs Modified
            grid.setColumnMinimumWidth(2, 16)
            grid.setColumnMinimumWidth(3, 200)
            grid.setColumnMinimumWidth(4, 250)

            hdr_left = QLabel("Current (Unmodified)")
            hdr_left.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            hdr_left.setStyleSheet(f"color: {CRIMSON_DARK}; text-decoration: underline;")
            grid.addWidget(hdr_left, row, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)

            hdr_right = QLabel("Modified (Substandard Applied)")
            hdr_right.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            hdr_right.setStyleSheet(f"color: {CRIMSON_DARK}; text-decoration: underline;")
            grid.addWidget(hdr_right, row, 3, 1, 2, Qt.AlignmentFlag.AlignCenter)
            row += 1

            pairs = [
                ("5-Year Survival:", "std_survival_5yr", "5-Year Survival:", "mod_survival_5yr"),
                ("10-Year Survival:", "std_survival_10yr", "10-Year Survival:", "mod_survival_10yr"),
                ("Life Expectancy:", "std_le", "Life Expectancy:", "mod_le"),
                ("Table Rating:", "std_table_rating", "Table Ratings:", "table_rating"),
                ("Flat Extra:", "std_flat_extra", "Flat Extras:", "flat_extra"),
            ]
            for std_lbl, std_key, mod_lbl, mod_key in pairs:
                lf = QLabel(std_lbl)
                lf.setFont(label_font)
                lf.setStyleSheet(f"color: {CRIMSON_DARK};")
                lf.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(lf, row, 0)
                lv = QLabel(dv.get(std_key, "—"))
                lv.setFont(value_font)
                lv.setStyleSheet(f"color: {GRAY_DARK};")
                lv.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(lv, row, 1)

                rf = QLabel(mod_lbl)
                rf.setFont(label_font)
                rf.setStyleSheet(f"color: {CRIMSON_DARK};")
                rf.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(rf, row, 3)
                rv = QLabel(dv.get(mod_key, "—"))
                rv.setFont(value_font)
                rv.setStyleSheet(f"color: {GRAY_DARK};")
                rv.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(rv, row, 4)
                row += 1
        else:
            _field("Derived Table Rating:", f"{a.derived_table_rating:.4f}")
            if a.use_five_year and a.use_ten_year:
                _field("  5yr Table Rating:", f"{a.derived_table_rating_5yr:.4f}")
                _field("  10yr Table Rating:", f"{a.derived_table_rating_10yr:.4f}")
            _field("Life Expectancy (rounded):", f"{a.life_expectancy_rounded}")

        if r:
            _section("Results Summary")
            p = self._policy
            is_ul = p and p.product_type in ("UL", "IUL", "ISWL")

            # Ensure columns 3-4 are wide enough for APV labels
            grid.setColumnMinimumWidth(3, 100)
            grid.setColumnMinimumWidth(4, 150)

            # Full Acceleration breakdown
            _field("", "FULL ACCELERATION")
            accel_display = self._accel_amount_input if self._accel_amount_input > 0 else (p.face_amount if p else 0)
            _field("Acceleration Amount Input:", f"${accel_display:,.2f}" if accel_display else "—")
            full_start_row = row  # track for APV placement
            _field("Eligible Death Benefit:", f"${r.full_eligible_db:,.2f}")
            _field("Actuarial Discount:", f"${r.full_actuarial_discount:,.2f}")
            _field("Administrative Fee:", f"${r.full_admin_fee:,.2f}")
            if r.full_loan_repayment > 0:
                _field("Loan Repayment:", f"${r.full_loan_repayment:,.2f}")
            _field("Accelerated Benefit:", f"${r.full_accel_benefit:,.2f}")
            _field("Benefit Ratio:", f"{r.full_benefit_ratio * 100:.2f}%")

            # Full APV — columns 3-4 beside Full Acceleration
            for j, (apv_lbl, apv_val) in enumerate([
                ("APV_FB:", f"${r.apv_fb:,.2f}"),
                ("APV_FP:", f"${r.apv_fp:,.2f}"),
                ("APV_FD:", f"${r.apv_fd:,.2f}"),
            ]):
                al = QLabel(apv_lbl)
                al.setFont(label_font)
                al.setStyleSheet(f"color: {CRIMSON_DARK};")
                al.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(al, full_start_row + j, 3)
                av = QLabel(apv_val)
                av.setFont(value_font)
                av.setStyleSheet(f"color: {GRAY_DARK};")
                av.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(av, full_start_row + j, 4)

            # Max Partial Acceleration breakdown
            _field("", "")
            if r.partial_eligible_db > 0:
                _field("", "MAX PARTIAL ACCELERATION")
                min_face_display = self._min_face_amount_input if self._min_face_amount_input > 0 else (p.min_face_amount if p else 0)
                _field("Min Face Amount Input:", f"${min_face_display:,.0f}" if min_face_display else "—")
                partial_start_row = row
                _field("Eligible Death Benefit:", f"${r.partial_eligible_db:,.2f}")
                _field("Actuarial Discount:", f"${r.partial_actuarial_discount:,.2f}")
                _field("Administrative Fee:", f"${r.partial_admin_fee:,.2f}")
                if r.partial_loan_repayment > 0:
                    _field("Loan Repayment:", f"${r.partial_loan_repayment:,.2f}")
                _field("Accelerated Benefit:", f"${r.partial_accel_benefit:,.2f}")
                _field("Benefit Ratio:", f"{r.partial_benefit_ratio * 100:.2f}%")

                # Partial APV — proportionally scaled, columns 3-4
                if r.full_eligible_db > 0:
                    ratio = r.partial_eligible_db / r.full_eligible_db
                else:
                    ratio = 0.0
                for j, (apv_lbl, apv_val) in enumerate([
                    ("APV_FB:", f"${r.apv_fb * ratio:,.2f}"),
                    ("APV_FP:", f"${r.apv_fp * ratio:,.2f}"),
                    ("APV_FD:", f"${r.apv_fd * ratio:,.2f}"),
                ]):
                    al = QLabel(apv_lbl)
                    al.setFont(label_font)
                    al.setStyleSheet(f"color: {CRIMSON_DARK};")
                    al.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    grid.addWidget(al, partial_start_row + j, 3)
                    av = QLabel(apv_val)
                    av.setFont(value_font)
                    av.setStyleSheet(f"color: {GRAY_DARK};")
                    av.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    grid.addWidget(av, partial_start_row + j, 4)
            else:
                _field("Partial Acceleration:", "NOT ALLOWED — At Minimum Face")

            # Premium Impact / Monthly Deduction Impact
            _field("", "")
            if is_ul:
                # UL: premium_before already contains just the amount (no mode)
                _field("Last Monthly Deduction:", r.premium_before)
            else:
                _field("Premium Before:", r.premium_before)
            _field("After (Full Accel):", f"${r.premium_after_full:,.2f}")
            if r.partial_eligible_db > 0:
                if is_ul and self._after_partial_override:
                    _field("After (Partial):", self._after_partial_override)
                else:
                    _field("After (Partial):", r.premium_after_partial)
            else:
                _field("After (Partial):", "NOT ALLOWED")

        # Messages / Warnings — combine result.messages with UI-generated warnings
        all_warnings = list(r.messages) if r else []
        all_warnings.extend(self._warnings)
        if all_warnings:
            _section("Messages")
            for msg in all_warnings:
                msg_lbl = QLabel(f"\u2022 {msg}")
                msg_lbl.setWordWrap(True)
                msg_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                msg_lbl.setStyleSheet("color: #C62828; padding: 2px 0;")
                msg_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(msg_lbl, row, 0, 1, 5)
                row += 1

        grid.setRowStretch(row, 1)
        scroll.setWidget(container)
        return scroll

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
        """Export full 5-sheet detail workbook to a new unsaved Excel workbook via COM."""
        p = self._policy
        r = self._result
        a = self._assessment

        if not p or not r:
            QMessageBox.warning(self, "Export", "No results available to export.")
            return

        try:
            from win32com.client import dynamic
            from ..models.abr_constants import PLAN_CODE_INFO, MODAL_LABELS

            excel = dynamic.Dispatch("Excel.Application")
            excel.Visible = True
            excel.ScreenUpdating = False

            wb = excel.Workbooks.Add()

            # Helper: write a label+value pair into cells
            def _field(ws, row, label, value, col=1):
                ws.Cells(row, col).Value = label
                ws.Cells(row, col).Font.Bold = True
                ws.Cells(row, col + 1).Value = value
                return row + 1

            def _section(ws, row, title, col_span=2):
                ws.Cells(row, 1).Value = title
                ws.Cells(row, 1).Font.Bold = True
                ws.Cells(row, 1).Font.Color = 0xFFFFFF
                ws.Cells(row, 1).Interior.Color = 0x00008B  # BGR for #8B0000
                if col_span > 1:
                    ws.Range(ws.Cells(row, 1), ws.Cells(row, col_span)).Merge()
                    ws.Range(ws.Cells(row, 1), ws.Cells(row, col_span)).Interior.Color = 0x00008B
                return row + 1

            # ── Sheet 1: Policy Info ────────────────────────────────────
            ws1 = wb.Worksheets(1)
            ws1.Name = "Policy Info"

            row = 1
            ws1.Cells(row, 1).Value = "ABR Quote — Policy Information"
            ws1.Cells(row, 1).Font.Bold = True
            ws1.Cells(row, 1).Font.Size = 12
            row = 3

            row = _section(ws1, row, "Policy Details")
            row = _field(ws1, row, "Policy Number:", p.policy_number)
            row = _field(ws1, row, "Insured:", p.insured_name or "—")

            plan_info = PLAN_CODE_INFO.get(p.plan_code.upper(), None) if p.plan_code else None
            plan_desc = f"{plan_info[1]} ({plan_info[0]}-Year Level)" if plan_info else "—"
            row = _field(ws1, row, "Plancode:", p.plan_code or "—")
            row = _field(ws1, row, "Plan Description:", plan_desc)

            sex_display = {"M": "Male", "F": "Female", "U": "Unisex"}.get(p.sex, p.sex or "—")
            row = _field(ws1, row, "Sex:", sex_display)
            row = _field(ws1, row, "Rate Sex:", p.rate_sex or "—")
            row = _field(ws1, row, "Issue Age:", p.issue_age)
            row = _field(ws1, row, "Attained Age:", p.attained_age)
            row = _field(ws1, row, "Rate Class:", p.rate_class or "—")
            row = _field(ws1, row, "Face Amount:", f"${p.face_amount:,.2f}" if p.face_amount else "—")
            row = _field(ws1, row, "Min Face:", f"${p.min_face_amount:,.0f}")
            row = _field(ws1, row, "Issue State:", p.issue_state or "—")
            row = _field(ws1, row, "Issue Date:", p.issue_date.strftime("%m/%d/%Y") if p.issue_date else "—")
            row = _field(ws1, row, "Policy Year:", p.policy_year)
            row = _field(ws1, row, "Month of Year:", p.policy_month)
            row = _field(ws1, row, "Base Plancode:", p.base_plancode or "—")
            row = _field(ws1, row, "Billing Mode:", MODAL_LABELS.get(p.billing_mode, str(p.billing_mode)))
            row = _field(ws1, row, "Modal Premium:", f"${p.modal_premium:,.2f}" if p.modal_premium else "—")
            row = _field(ws1, row, "Table Rating:", p.table_rating)
            row = _field(ws1, row, "Annual Flat Extra:", f"${p.flat_extra:.2f}" if p.flat_extra > 0 else "None")
            row = _field(ws1, row, "Flat Cease Date:", p.flat_cease_date.strftime("%m/%d/%Y") if p.flat_cease_date else "—")
            row = _field(ws1, row, "Reinsurers:", p.reinsurers or "(none)")

            row += 1
            row = _section(ws1, row, "Quote Parameters")
            row = _field(ws1, row, "Quote Date:", r.quote_date.strftime("%m/%d/%Y") if r.quote_date else "—")
            row = _field(ws1, row, "ABR Interest Rate:", f"{r.abr_interest_rate * 100:.2f}%")
            row = _field(ws1, row, "Per Diem (Daily):", f"${r.per_diem_daily:,.2f}")
            row = _field(ws1, row, "Per Diem (Annual):", f"${r.per_diem_annual:,.2f}")

            row += 1
            row = _section(ws1, row, "Riders / Coverages")
            if p.riders:
                for rider in p.riders:
                    rider_desc = f"{rider.plancode} ({rider.rider_type})"
                    if rider.benefit_type:
                        rider_desc += f" — BNF {rider.benefit_type}{rider.benefit_subtype or ''}"
                    row = _field(ws1, row, rider_desc, f"${rider.fallback_premium:,.2f}/yr")
            else:
                row = _field(ws1, row, "No riders.", "")

            ws1.Columns("A:A").ColumnWidth = 22
            ws1.Columns("B:B").ColumnWidth = 35

            # ── Sheet 2: Assessment ─────────────────────────────────────
            ws2 = wb.Worksheets.Add(After=ws1)
            ws2.Name = "Assessment"

            row = 1
            ws2.Cells(row, 1).Value = "ABR Quote — Assessment"
            ws2.Cells(row, 1).Font.Bold = True
            ws2.Cells(row, 1).Font.Size = 12
            row = 3

            row = _section(ws2, row, "Rider Configuration")
            row = _field(ws2, row, "Rider Type:", a.rider_type if a else "—")

            row += 1
            row = _section(ws2, row, "Assessment Inputs")
            if a:
                if a.use_five_year:
                    row = _field(ws2, row, "5-Year Survival Rate:", f"{a.five_year_survival}")
                    row = _field(ws2, row, "  Return to Normal:", "Yes" if a.use_return_5yr else "No")
                if a.use_ten_year:
                    row = _field(ws2, row, "10-Year Survival Rate:", f"{a.ten_year_survival}")
                    row = _field(ws2, row, "  Return to Normal:", "Yes" if a.use_return_10yr else "No")
                if a.use_le:
                    row = _field(ws2, row, "Life Expectancy:", f"{a.life_expectancy_years} years")
                if hasattr(a, 'use_increased_decrement') and a.use_increased_decrement:
                    row = _field(ws2, row, "Increased Decrement:", f"{a.direct_increased_decrement:.0f}%")
                    row = _field(ws2, row, "  Start/Stop Year:", f"{a.incr_decrement_start_year} — {a.incr_decrement_stop_year}")
                if a.use_table:
                    row = _field(ws2, row, "Table (rating):", f"{a.direct_table_rating}")
                    row = _field(ws2, row, "  Start/Stop Year:", f"{a.table_start_year} — {a.table_stop_year}")
                if a.use_flat:
                    row = _field(ws2, row, "Flat ($/1000):", f"${a.direct_flat_extra:.2f}")
                    row = _field(ws2, row, "  Start/Stop Year:", f"{a.flat_start_year} — {a.flat_stop_year}")
                if a.use_table_2:
                    row = _field(ws2, row, "Table 2 (rating):", f"{a.direct_table_rating_2}")
                    row = _field(ws2, row, "  Start/Stop Year:", f"{a.table_2_start_year} — {a.table_2_stop_year}")
                if a.use_flat_2:
                    row = _field(ws2, row, "Flat 2 ($/1000):", f"${a.direct_flat_extra_2:.2f}")
                    row = _field(ws2, row, "  Start/Stop Year:", f"{a.flat_2_start_year} — {a.flat_2_stop_year}")
                row = _field(ws2, row, "In Lieu Of:", "Yes" if a.in_lieu_of else "No (In Addition To)")
            else:
                row = _field(ws2, row, "No assessment data.", "")

            row += 1
            row = _section(ws2, row, "Derived Substandard Values")
            dv = self._derived_values
            if dv:
                ws2.Cells(row, 1).Value = "Current (Unmodified)"
                ws2.Cells(row, 1).Font.Bold = True
                ws2.Cells(row, 1).Font.Underline = True
                ws2.Cells(row, 3).Value = "Modified (Substandard Applied)"
                ws2.Cells(row, 3).Font.Bold = True
                ws2.Cells(row, 3).Font.Underline = True
                row += 1

                field_pairs = [
                    ("5-Year Survival:", "std_survival_5yr", "5-Year Survival:", "mod_survival_5yr"),
                    ("10-Year Survival:", "std_survival_10yr", "10-Year Survival:", "mod_survival_10yr"),
                    ("Life Expectancy:", "std_le", "Life Expectancy:", "mod_le"),
                    ("Table Rating:", "std_table_rating", "Table Ratings:", "table_rating"),
                    ("Flat Extra:", "std_flat_extra", "Flat Extras:", "flat_extra"),
                ]
                for std_label, std_key, mod_label, mod_key in field_pairs:
                    ws2.Cells(row, 1).Value = std_label
                    ws2.Cells(row, 1).Font.Bold = True
                    ws2.Cells(row, 2).Value = str(dv.get(std_key, "—"))
                    ws2.Cells(row, 3).Value = mod_label
                    ws2.Cells(row, 3).Font.Bold = True
                    ws2.Cells(row, 4).Value = str(dv.get(mod_key, "—"))
                    row += 1
            elif a:
                row = _field(ws2, row, "Derived Table Rating:", f"{a.derived_table_rating:.4f}")
                if a.use_five_year and a.use_ten_year:
                    row = _field(ws2, row, "  5yr Table Rating:", f"{a.derived_table_rating_5yr:.4f}")
                    row = _field(ws2, row, "  10yr Table Rating:", f"{a.derived_table_rating_10yr:.4f}")
                row = _field(ws2, row, "Life Expectancy (rounded):", f"{a.life_expectancy_rounded}")

            row += 1
            is_ul = p and p.product_type in ("UL", "IUL", "ISWL")

            row = _section(ws2, row, "Results Summary", col_span=4)

            # Full Acceleration breakdown
            ws2.Cells(row, 1).Value = "FULL ACCELERATION"
            ws2.Cells(row, 1).Font.Bold = True
            ws2.Cells(row, 1).Font.Underline = True
            row += 1
            accel_display = self._accel_amount_input or (p.face_amount if p else 0.0)
            row = _field(ws2, row, "Acceleration Amount Input:", f"${accel_display:,.2f}" if accel_display else "—")
            full_start_row = row
            row = _field(ws2, row, "Eligible Death Benefit:", f"${r.full_eligible_db:,.2f}")
            row = _field(ws2, row, "Actuarial Discount:", f"${r.full_actuarial_discount:,.2f}")
            row = _field(ws2, row, "Administrative Fee:", f"${r.full_admin_fee:,.2f}")
            if r.full_loan_repayment > 0:
                row = _field(ws2, row, "Loan Repayment:", f"${r.full_loan_repayment:,.2f}")
            row = _field(ws2, row, "Accelerated Benefit:", f"${r.full_accel_benefit:,.2f}")
            row = _field(ws2, row, "Benefit Ratio:", f"{r.full_benefit_ratio * 100:.2f}%")

            # Full APV — columns C-D beside Full Acceleration
            for j, (apv_lbl, apv_val) in enumerate([
                ("APV_FB:", f"${r.apv_fb:,.2f}"),
                ("APV_FP:", f"${r.apv_fp:,.2f}"),
                ("APV_FD:", f"${r.apv_fd:,.2f}"),
            ]):
                ws2.Cells(full_start_row + j, 3).Value = apv_lbl
                ws2.Cells(full_start_row + j, 3).Font.Bold = True
                ws2.Cells(full_start_row + j, 4).Value = apv_val

            row += 1

            # Max Partial Acceleration breakdown
            if r.partial_eligible_db > 0:
                ws2.Cells(row, 1).Value = "MAX PARTIAL ACCELERATION"
                ws2.Cells(row, 1).Font.Bold = True
                ws2.Cells(row, 1).Font.Underline = True
                row += 1
                min_face_display = self._min_face_amount_input or (p.min_face_amount if p else 0.0)
                row = _field(ws2, row, "Min Face Amount Input:", f"${min_face_display:,.0f}")
                partial_start_row = row
                row = _field(ws2, row, "Eligible Death Benefit:", f"${r.partial_eligible_db:,.2f}")
                row = _field(ws2, row, "Actuarial Discount:", f"${r.partial_actuarial_discount:,.2f}")
                row = _field(ws2, row, "Administrative Fee:", f"${r.partial_admin_fee:,.2f}")
                if r.partial_loan_repayment > 0:
                    row = _field(ws2, row, "Loan Repayment:", f"${r.partial_loan_repayment:,.2f}")
                row = _field(ws2, row, "Accelerated Benefit:", f"${r.partial_accel_benefit:,.2f}")
                row = _field(ws2, row, "Benefit Ratio:", f"{r.partial_benefit_ratio * 100:.2f}%")

                # Partial APV — proportionally scaled, columns C-D
                if r.full_eligible_db > 0:
                    pratio = r.partial_eligible_db / r.full_eligible_db
                else:
                    pratio = 0.0
                for j, (apv_lbl, apv_val) in enumerate([
                    ("APV_FB:", f"${r.apv_fb * pratio:,.2f}"),
                    ("APV_FP:", f"${r.apv_fp * pratio:,.2f}"),
                    ("APV_FD:", f"${r.apv_fd * pratio:,.2f}"),
                ]):
                    ws2.Cells(partial_start_row + j, 3).Value = apv_lbl
                    ws2.Cells(partial_start_row + j, 3).Font.Bold = True
                    ws2.Cells(partial_start_row + j, 4).Value = apv_val
            else:
                row = _field(ws2, row, "Partial Acceleration:", "NOT ALLOWED — At Minimum Face")

            row += 1

            # Premium Impact
            if is_ul:
                row = _field(ws2, row, "Last Monthly Deduction:", r.premium_before)
            else:
                row = _field(ws2, row, "Premium Before:", r.premium_before)
            row = _field(ws2, row, "After (Full Accel):", f"${r.premium_after_full:,.2f}")
            if r.partial_eligible_db > 0:
                after_partial = self._after_partial_override or r.premium_after_partial
                row = _field(ws2, row, "After (Partial):", after_partial)
            else:
                row = _field(ws2, row, "After (Partial):", "NOT ALLOWED")

            # Messages / Warnings
            warnings = self._warnings or (r.messages if r.messages else [])
            if warnings:
                row += 1
                row = _section(ws2, row, "Messages")
                for msg in warnings:
                    ws2.Cells(row, 1).Value = f"\u2022 {msg}"
                    ws2.Cells(row, 1).Font.Bold = True
                    ws2.Cells(row, 1).Font.Color = 0x2828C6  # BGR for C62828
                    row += 1

            ws2.Columns("A:A").ColumnWidth = 28
            ws2.Columns("B:B").ColumnWidth = 35
            ws2.Columns("C:C").ColumnWidth = 20
            ws2.Columns("D:D").ColumnWidth = 25

            # ── Sheet 3: Mortality Derivation ───────────────────────────
            ws3 = wb.Worksheets.Add(After=ws2)
            ws3.Name = "Mortality Derivation"

            mort_headers = (
                "Quote Month", "Policy Year", "Mo in Yr", "Att Age",
                "qx VBT", "qx × Mult", "qx Improved",
                "Table Rating", "qx + Table",
                "Flat Extra", "qx + Flat", "qx Capped",
                "qx Monthly", "px Monthly", "Cum Survival",
            )
            mort_col_count = len(mort_headers)

            mort_data = [mort_headers]
            mort_year_boundary_rows = []
            for i, mrow in enumerate(self._mort_rows):
                tbl_val = mrow.get("table_rating_applied", 0.0)
                flat_val = mrow.get("flat_extra_applied", 0.0)
                mort_data.append((
                    mrow["quote_month"], mrow["duration_year"],
                    mrow["month_in_year"], mrow["attained_age"],
                    mrow["qx_vbt"], mrow["qx_multiplied"],
                    mrow["qx_improved"],
                    tbl_val if tbl_val > 0 else "",
                    mrow["qx_table_rated"],
                    flat_val if flat_val > 0 else "",
                    mrow["qx_flat_extra"], mrow["qx_capped"],
                    mrow["qx_monthly"], mrow["px_monthly"],
                    mrow["cum_survival"],
                ))
                if mrow["month_in_year"] == 1 and i > 0:
                    mort_year_boundary_rows.append(i + 2)

            total_mort = len(mort_data)
            ws3.Range(ws3.Cells(1, 1), ws3.Cells(total_mort, mort_col_count)).Value = mort_data

            hdr3 = ws3.Range(ws3.Cells(1, 1), ws3.Cells(1, mort_col_count))
            hdr3.Font.Bold = True
            hdr3.Font.Color = 0xFFFFFF
            hdr3.Interior.Color = 0x404D00
            hdr3.HorizontalAlignment = -4108

            if total_mort > 1:
                ws3.Range(ws3.Cells(2, 5), ws3.Cells(total_mort, 7)).NumberFormat = "0.00000000"
                ws3.Range(ws3.Cells(2, 9), ws3.Cells(total_mort, 9)).NumberFormat = "0.00000000"
                ws3.Range(ws3.Cells(2, 11), ws3.Cells(total_mort, 14)).NumberFormat = "0.00000000"
                ws3.Range(ws3.Cells(2, 15), ws3.Cells(total_mort, 15)).NumberFormat = "0.000000%"

            for yr_row in mort_year_boundary_rows:
                ws3.Range(ws3.Cells(yr_row, 1), ws3.Cells(yr_row, mort_col_count)).Interior.Color = 0xD0F3FF

            ws3.Range("A2").Select()
            excel.ActiveWindow.FreezePanes = True
            if total_mort > 1:
                ws3.Range(ws3.Cells(1, 1), ws3.Cells(total_mort, mort_col_count)).AutoFilter()
            ws3.Columns.AutoFit()

            # ── Sheet 4: Life Expectancy ────────────────────────────────
            ws4 = wb.Worksheets.Add(After=ws3)
            ws4.Name = "Life Expectancy"

            le_headers = (
                "Quote Month", "Policy Year", "Att Age",
                "qx Monthly", "px Monthly", "tPx (cum surv)",
                "Sum tPx (months)", "Curtate LE (years)",
            )
            le_col_count = len(le_headers)

            # Compute LE development from mortality data
            tp_x = 1.0
            sum_tpx = 0.0
            le_data = [le_headers]
            le_year_rows = []
            for i, mrow in enumerate(self._mort_rows):
                qx_m = mrow["qx_monthly"]
                px_m = 1.0 - qx_m
                tp_x *= px_m
                sum_tpx += tp_x
                curtate_years = sum_tpx / 12.0
                le_data.append((
                    mrow["quote_month"], mrow["duration_year"],
                    mrow["attained_age"],
                    qx_m, px_m, tp_x,
                    sum_tpx, curtate_years,
                ))
                if mrow["quote_month"] % 12 == 1 and i > 0:
                    le_year_rows.append(i + 2)

            total_le = len(le_data)
            ws4.Range(ws4.Cells(1, 1), ws4.Cells(total_le, le_col_count)).Value = le_data

            hdr4 = ws4.Range(ws4.Cells(1, 1), ws4.Cells(1, le_col_count))
            hdr4.Font.Bold = True
            hdr4.Font.Color = 0xFFFFFF
            hdr4.Interior.Color = 0x404D00
            hdr4.HorizontalAlignment = -4108

            if total_le > 1:
                ws4.Range(ws4.Cells(2, 4), ws4.Cells(total_le, 5)).NumberFormat = "0.00000000"
                ws4.Range(ws4.Cells(2, 6), ws4.Cells(total_le, 6)).NumberFormat = "0.000000%"
                ws4.Range(ws4.Cells(2, 7), ws4.Cells(total_le, 8)).NumberFormat = "0.0000"

            for yr_row in le_year_rows:
                ws4.Range(ws4.Cells(yr_row, 1), ws4.Cells(yr_row, le_col_count)).Interior.Color = 0xD0F3FF

            # Summary rows
            curtate_le = sum_tpx / 12.0 if self._mort_rows else 0.0
            complete_le = curtate_le + 0.5
            sr = total_le + 2
            for i, (label, value, fmt) in enumerate([
                ("Sum tPx (months):", sum_tpx, "0.0000"),
                ("Curtate LE (years):", curtate_le, "0.0000"),
                ("Complete LE (+ 0.5):", complete_le, "0.0000"),
            ]):
                ws4.Cells(sr + i, 6).Value = label
                ws4.Cells(sr + i, 6).Font.Bold = True
                ws4.Cells(sr + i, 8).Value = value
                ws4.Cells(sr + i, 8).Font.Bold = True
                ws4.Cells(sr + i, 8).NumberFormat = fmt

            ws4.Activate()
            ws4.Range("A2").Select()
            excel.ActiveWindow.FreezePanes = True
            if total_le > 1:
                ws4.Range(ws4.Cells(1, 1), ws4.Cells(total_le, le_col_count)).AutoFilter()
            ws4.Columns.AutoFit()

            # ── Sheet 5: APV — Present Value ────────────────────────────
            ws5 = wb.Worksheets.Add(After=ws4)
            ws5.Name = "APV Present Value"

            apv_headers = (
                "Month", "t", "qx Monthly", "px Monthly", "tpx (cum surv)",
                "v^(t+1)", "v^t", "PVDB(t)", "PVDB Cum",
                "Prem Rate", "PVFP(t)", "PVFP Cum", "tpx End",
            )
            apv_col_count = len(apv_headers)

            apv_data = [apv_headers]
            apv_prem_rows = []
            for i, arow in enumerate(self._apv_rows):
                apv_data.append((
                    arow["month"], arow["t"],
                    arow["qx_monthly"], arow["px_monthly"],
                    arow["tp_x"], arow["v_benefit"], arow["v_premium"],
                    arow["pvdb_t"], arow["pvdb_cum"],
                    arow["prem_rate"], arow["pvfp_t"], arow["pvfp_cum"],
                    arow["tp_x_end"],
                ))
                if arow["prem_rate"] > 0:
                    apv_prem_rows.append(i + 2)

            total_apv = len(apv_data)
            ws5.Range(ws5.Cells(1, 1), ws5.Cells(total_apv, apv_col_count)).Value = apv_data

            hdr5 = ws5.Range(ws5.Cells(1, 1), ws5.Cells(1, apv_col_count))
            hdr5.Font.Bold = True
            hdr5.Font.Color = 0xFFFFFF
            hdr5.Interior.Color = 0x404D00
            hdr5.HorizontalAlignment = -4108

            if total_apv > 1:
                ws5.Range(ws5.Cells(2, 3), ws5.Cells(total_apv, 4)).NumberFormat = "0.00000000"
                ws5.Range(ws5.Cells(2, 5), ws5.Cells(total_apv, 5)).NumberFormat = "0.000000%"
                ws5.Range(ws5.Cells(2, 6), ws5.Cells(total_apv, 7)).NumberFormat = "0.0000000000"
                ws5.Range(ws5.Cells(2, 8), ws5.Cells(total_apv, 9)).NumberFormat = "#,##0.000000"
                ws5.Range(ws5.Cells(2, 10), ws5.Cells(total_apv, 10)).NumberFormat = "0.0000"
                ws5.Range(ws5.Cells(2, 11), ws5.Cells(total_apv, 12)).NumberFormat = "#,##0.000000"
                ws5.Range(ws5.Cells(2, 13), ws5.Cells(total_apv, 13)).NumberFormat = "0.000000%"

            for pr_row in apv_prem_rows:
                ws5.Range(ws5.Cells(pr_row, 1), ws5.Cells(pr_row, apv_col_count)).Interior.Color = 0xD0F3FF

            # Summary rows below data
            s = self._apv_summary
            sr = total_apv + 2
            for i, (label, value, fmt) in enumerate([
                ("PVFB (raw sum):", s["pvfb_raw"], "#,##0.000000"),
                ("Continuous Mort Adj:", s["cont_mort_adj"], "0.0000000000"),
                ("PVFB (adjusted × 1000):", s["pvfb_adjusted"], "#,##0.00"),
                ("PVFP:", s["pvfp"], "#,##0.000000"),
                ("Actuarial Discount:", s["actuarial_discount"], "#,##0.00"),
            ]):
                ws5.Cells(sr + i, 8).Value = label
                ws5.Cells(sr + i, 8).Font.Bold = True
                ws5.Cells(sr + i, 9).Value = value
                ws5.Cells(sr + i, 9).Font.Bold = True
                ws5.Cells(sr + i, 9).NumberFormat = fmt

            ws5.Activate()
            ws5.Range("A2").Select()
            excel.ActiveWindow.FreezePanes = True
            if total_apv > 1:
                ws5.Range(ws5.Cells(1, 1), ws5.Cells(total_apv, apv_col_count)).AutoFilter()
            ws5.Columns.AutoFit()

            # Activate the first sheet
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
