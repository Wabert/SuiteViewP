"""
ABR Quote — Main Application Window.

3-step wizard in a FramelessWindowBase:
    Step 1: Policy Information (policy_panel.py)
    Step 2: Medical Assessment (assessment_panel.py)
    Step 3: Results (results_panel.py)

Theme: "Crimson Slate" (Crimson & Slate-Blue)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtCore import QMimeData
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QPushButton, QFrame, QMenu, QMessageBox,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from ..models.abr_data import ABRPolicyData, MedicalAssessment, MortalityParams, ABRQuoteResult
from ..models.abr_constants import (
    MORTALITY_IMPROVEMENT_RATE, MORTALITY_IMPROVEMENT_CAP,
    MORTALITY_MULTIPLIER, MORTALITY_MULTIPLIER_TERMINAL,
    MATURITY_AGE, MODAL_LABELS,
)
from ..models.abr_database import get_abr_database
from ..core.mortality_engine import MortalityEngine
from ..core.premium_calc import PremiumCalculator
from ..core.apv_engine import APVEngine
from .abr_styles import (
    ABR_HEADER_COLORS, ABR_BORDER_COLOR,
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_RICH, CRIMSON_BG, CRIMSON_LIGHT,
    SLATE_PRIMARY, SLATE_TEXT, SLATE_DARK,
    WHITE, GRAY_DARK, GRAY_MID,
    STEP_BAR_STYLE, STATUS_BAR_STYLE,
)
from .policy_panel import PolicyPanel
from .assessment_panel import AssessmentPanel
from .results_panel import ResultsPanel
from .output_panel import OutputPanel

logger = logging.getLogger(__name__)


class ABRQuoteWindow(FramelessWindowBase):
    """Main ABR Quote Tool window — 3-step wizard with inline results."""

    STEP_TITLES = [
        "1. Policy Info",
        "2. Assessment",
        "3. Output",
    ]

    def __init__(self, parent=None):
        # State
        self._policy: Optional[ABRPolicyData] = None
        self._assessment: Optional[MedicalAssessment] = None
        self._current_step = 0

        # Detailed calculation tables (populated on calculate)
        self._mort_detail: list[dict] = []
        self._apv_detail: list[dict] = []
        self._apv_summary: dict = {}

        super().__init__(
            title="SuiteView:  ABR Quote",
            default_size=(1250, 875),
            min_size=(600, 500),
            parent=parent,
            header_colors=ABR_HEADER_COLORS,
            border_color=ABR_BORDER_COLOR,
        )

        # Insert hamburger menu button into header bar (before the title)
        self._add_header_menu()

        # Policy label will be placed in the step bar (built in build_content)

    def build_content(self) -> QWidget:
        """Build the main body widget with step indicator and stacked panels."""
        body = QWidget()
        body.setObjectName("abrBody")
        body.setStyleSheet(f"QWidget#abrBody {{ background-color: {CRIMSON_BG}; }}")

        main_layout = QVBoxLayout(body)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Step indicator bar ──────────────────────────────────────────
        self.step_bar = self._build_step_bar()
        main_layout.addWidget(self.step_bar)

        # ── Stacked panels ──────────────────────────────────────────────
        self.stack = QStackedWidget()

        self.policy_panel = PolicyPanel()
        self.policy_panel.policy_loaded.connect(self._on_policy_loaded)
        self.policy_panel.quote_date_changed.connect(self._on_quote_date_changed)
        self.stack.addWidget(self.policy_panel)

        self.assessment_panel = AssessmentPanel()
        self.assessment_panel.assessment_ready.connect(self._on_assessment_ready)
        self.assessment_panel.min_face_calc_requested.connect(self._on_min_face_recalc)
        self.stack.addWidget(self.assessment_panel)

        self.output_panel = OutputPanel()
        self.stack.addWidget(self.output_panel)

        self.results_panel = ResultsPanel()
        self.results_panel.new_quote_requested.connect(self._on_new_quote)
        self.stack.addWidget(self.results_panel)

        main_layout.addWidget(self.stack, 1)


        # ── Status bar ──────────────────────────────────────────────────
        self.status_label = QLabel("Ready — Enter a policy number to begin")
        self.status_label.setObjectName("statusBar")
        self.status_label.setStyleSheet(STATUS_BAR_STYLE)
        main_layout.addWidget(self.status_label)

        # Initialize step display
        self._set_step(0)

        return body

    # ── Step indicator ──────────────────────────────────────────────────

    # Single stylesheet covering all three states via custom property selectors.
    # Qt re-evaluates property selectors on every polish cycle, so changing
    # the property + calling unpolish/polish is guaranteed to update the look.
    _STEP_BTN_STYLE = f"""
        QPushButton[stepState="active"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {CRIMSON_DARK}, stop:1 {CRIMSON_PRIMARY});
            color: {SLATE_TEXT};
            font-weight: bold;
            font-size: 12px;
            border-radius: 5px;
            padding: 5px 18px 3px 18px;
            border-top:    2px solid rgba(0,0,0,0.55);
            border-left:   2px solid rgba(0,0,0,0.45);
            border-bottom: 2px solid rgba(255,255,255,0.28);
            border-right:  2px solid rgba(255,255,255,0.22);
        }}
        QPushButton[stepState="done"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {CRIMSON_LIGHT}, stop:1 {CRIMSON_PRIMARY});
            color: {WHITE};
            font-weight: bold;
            font-size: 12px;
            border-radius: 5px;
            padding: 3px 18px 5px 18px;
            border-top:    2px solid rgba(255,255,255,0.42);
            border-left:   2px solid rgba(255,255,255,0.32);
            border-bottom: 2px solid rgba(0,0,0,0.42);
            border-right:  2px solid rgba(0,0,0,0.36);
        }}
        QPushButton[stepState="done"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {CRIMSON_RICH}, stop:1 {CRIMSON_PRIMARY});
        }}
        QPushButton[stepState="future"] {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.28), stop:1 rgba(255,255,255,0.10));
            color: rgba(255,255,255,0.75);
            font-size: 12px;
            border-radius: 5px;
            padding: 3px 18px 5px 18px;
            border-top:    2px solid rgba(255,255,255,0.36);
            border-left:   2px solid rgba(255,255,255,0.26);
            border-bottom: 2px solid rgba(0,0,0,0.36);
            border-right:  2px solid rgba(0,0,0,0.30);
        }}
        QPushButton[stepState="future"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.40), stop:1 rgba(255,255,255,0.20));
            color: {WHITE};
        }}
    """

    def _build_step_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("stepBar")
        bar.setStyleSheet(STEP_BAR_STYLE)
        bar.setFixedHeight(44)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 4, 20, 4)
        layout.setSpacing(4)

        # Policy label (left-justified)
        self._header_policy_label = QLabel("")
        self._header_policy_label.setStyleSheet(f"""
            QLabel {{
                color: {WHITE};
                font-size: 14px;
                font-weight: bold;
                background: transparent;
            }}
        """)
        layout.addWidget(self._header_policy_label)

        layout.addStretch()

        self._step_labels = []
        for i, title in enumerate(self.STEP_TITLES):
            btn = QPushButton(title)
            btn.setFixedHeight(32)
            btn.setMinimumWidth(110)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # Set the stylesheet ONCE — state changes are driven by the property
            btn.setStyleSheet(self._STEP_BTN_STYLE)
            btn.setProperty("stepState", "future")
            btn.clicked.connect(lambda checked, idx=i: self._on_step_clicked(idx))
            self._step_labels.append(btn)
            layout.addWidget(btn)

            if i < len(self.STEP_TITLES) - 1:
                arrow = QLabel("  ►  ")
                arrow.setStyleSheet(f"color: {SLATE_PRIMARY}; font-size: 14px; background: transparent;")
                layout.addWidget(arrow)

        # ── Copy to Clipboard button (right side of step bar) ────────
        self._email_print_btn = QPushButton("📋 Copy to Clipboard")
        self._email_print_btn.setFixedHeight(32)
        self._email_print_btn.setMinimumWidth(120)
        self._email_print_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._email_print_btn.setEnabled(False)
        self._email_print_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {SLATE_TEXT}, stop:1 {SLATE_PRIMARY});
                color: {WHITE};
                border: 1px solid {SLATE_DARK};
                border-radius: 5px;
                padding: 3px 14px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {SLATE_PRIMARY}, stop:1 {SLATE_DARK});
            }}
            QPushButton:disabled {{
                background: rgba(255,255,255,0.15);
                color: rgba(255,255,255,0.45);
                border-color: rgba(255,255,255,0.18);
            }}
        """)
        self._email_print_btn.clicked.connect(self._on_email_print)
        layout.addWidget(self._email_print_btn)

        # ── Resources button (right side of step bar) ────────────────
        self._resources_btn = QPushButton("📖 Resources")
        self._resources_btn.setFixedHeight(32)
        self._resources_btn.setMinimumWidth(100)
        self._resources_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._resources_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {SLATE_TEXT}, stop:1 {SLATE_PRIMARY});
                color: {WHITE};
                border: 1px solid {SLATE_DARK};
                border-radius: 5px;
                padding: 3px 14px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {SLATE_PRIMARY}, stop:1 {SLATE_DARK});
            }}
        """)
        self._resources_btn.clicked.connect(self._on_resources)
        layout.addWidget(self._resources_btn)

        return bar

    def _update_step_indicators(self):
        """Update visual state of step indicator buttons via property selectors."""
        for i, btn in enumerate(self._step_labels):
            if i == self._current_step:
                state = "active"
            elif i < self._current_step:
                state = "done"
            else:
                state = "future"

            btn.setProperty("stepState", state)
            # unpolish + polish forces Qt to re-evaluate the property selector
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()



    # ── Navigation ──────────────────────────────────────────────────────

    def _set_step(self, step: int):
        """Switch to the given step (0-2)."""
        self._current_step = max(0, min(2, step))
        # Map step index to stack index
        # 0 -> 0 (Policy)
        # 1 -> 1 (Assessment)
        # 2 -> 2 (Output) — because we inserted it before ResultsPanel
        self.stack.setCurrentIndex(self._current_step)
        self._update_step_indicators()

    def _on_step_clicked(self, idx: int):
        """Allow clicking any step tab to navigate freely."""
        self._set_step(idx)

    def _on_new_quote(self):
        """Reset to Step 1."""
        self._policy = None
        self._assessment = None
        self.output_panel.set_policy(None)
        self._set_step(0)
        self.status_label.setText("Ready — Enter a policy number to begin")
        self._header_policy_label.setText("")

    # ── Signal handlers ─────────────────────────────────────────────────

    def _on_policy_loaded(self, policy: ABRPolicyData):
        """Called when policy data is successfully retrieved."""
        self._policy = policy
        self.assessment_panel.set_policy(policy)
        self.results_panel.set_policy(policy)
        self.output_panel.set_policy(policy)

        # Extract ABR rider subtypes from the policy benefits and pass to
        # assessment panel for rider-type validation.
        abr_subtypes = set()
        pi = self.policy_panel._policy_info
        if pi:
            try:
                for ben in pi.get_benefits():
                    bt = (ben.benefit_type_cd or "").strip()
                    bs = (ben.benefit_subtype_cd or "").strip()
                    if bt == "#" and bs:
                        abr_subtypes.add(bs)
            except Exception:
                pass
        self.assessment_panel.set_policy_abr_riders(abr_subtypes)

        self.status_label.setText(f"Policy {policy.policy_number} loaded.")

        # Update header policy label
        co = (policy.company or "").split(" ")[0].strip()
        pn = policy.policy_number or ""
        display = f"Policy:  {co}-{pn}" if co else f"Policy:  {pn}"
        self._header_policy_label.setText(display)

    def _on_quote_date_changed(self, new_date):
        """Re-run calculation when user changes the quote date."""
        if self._policy and self._assessment:
            self._run_calculation()

    def _on_assessment_ready(self, assessment: MedicalAssessment):
        """Called when substandard values are computed."""
        self._assessment = assessment
        self.results_panel.set_assessment(assessment)
        # Run the full ABR calculation immediately so results appear
        # inline on the assessment panel.
        self._run_calculation()

    def _on_min_face_recalc(self):
        """Re-run calculation when user changes the min face amount."""
        if self._policy and self._assessment:
            self._run_calculation()

    # ── Full calculation pipeline ───────────────────────────────────────

    def _run_calculation(self):
        """Execute the full ABR quote calculation pipeline."""
        self.status_label.setText("Calculating ABR quote...")

        try:
            p = self._policy
            a = self._assessment
            db = get_abr_database()

            # ── 1. Get interest rate ────────────────────────────────────
            quote_date = self.policy_panel.get_quote_date()

            # Check for user override first
            override_rate = self.policy_panel.get_interest_rate_override()
            if override_rate is not None:
                annual_rate = override_rate
            else:
                quote_month = quote_date.strftime("%Y-%m")
                rate_info = db.get_effective_interest_rate(quote_month)
                if rate_info is None:
                    self.status_label.setText("Error: No ABR interest rate data available.")
                    return
                _, annual_rate = rate_info

            # ── 2. Build mortality params ───────────────────────────────
            is_terminal = a.rider_type == "Terminal"

            # Mortality multiplier and improvement from rider type
            # Excel: mort_mult = IF(B28="C", 75%, 100%)
            #        MI        = IF(B28="C", 0.01, 0)
            if is_terminal:
                mort_mult = MORTALITY_MULTIPLIER_TERMINAL   # 100%
                mi_rate = 0.0                                # no improvement
            else:
                mort_mult = MORTALITY_MULTIPLIER            # 75%
                mi_rate = MORTALITY_IMPROVEMENT_RATE         # 1%

            # Convert month-within-year to absolute policy month since issue
            abs_policy_month = (p.policy_year - 1) * 12 + p.policy_month

            # Determine primary table periods from assessment
            # All month boundaries anchored to abs_policy_month
            has_survival_solve = a.use_five_year or a.use_ten_year or a.use_le
            is_dual = a.use_five_year and a.use_ten_year
            if is_dual:
                # Dual-solve: period 1 = 5yr, period 2 = 6-10yr
                t1_rating = a.derived_table_rating_5yr
                t1_start = abs_policy_month
                t1_last = abs_policy_month + 59
                t2_rating = a.derived_table_rating_10yr
                t2_start = abs_policy_month + 60
                t2_last = (abs_policy_month + 119) if a.use_return_10yr else 9999
            elif a.use_five_year and a.use_return_5yr:
                # Single 5yr solve with Return → bounded to 60 months
                t1_rating = a.derived_table_rating
                t1_start = abs_policy_month
                t1_last = abs_policy_month + 59
                t2_rating = 0.0
                t2_start = 0
                t2_last = 0
            elif a.use_ten_year and a.use_return_10yr:
                # Single 10yr solve with Return → bounded to 120 months
                t1_rating = a.derived_table_rating
                t1_start = abs_policy_month
                t1_last = abs_policy_month + 119
                t2_rating = 0.0
                t2_start = 0
                t2_last = 0
            elif has_survival_solve:
                # Single solve or LE solve — standard behavior
                t1_rating = a.derived_table_rating
                t1_start = abs_policy_month
                t1_last = 9999
                t2_rating = 0.0
                t2_start = 0
                t2_last = 0
            else:
                # No survival solve — direct table is the primary rating
                # Start/stop years are relative to quote date
                # Stop year is exclusive: drops off at beginning of stop year
                t1_rating = a.derived_table_rating
                t1_start = abs_policy_month + (a.table_start_year - 1) * 12 if a.use_table else abs_policy_month
                t1_last = abs_policy_month + (a.table_stop_year - 1) * 12 - 1 if a.use_table else 9999
                t2_rating = 0.0
                t2_start = 0
                t2_last = 0

            # Build additional tables/flats from direct user inputs
            # IMPORTANT: When there is NO survival solve, the direct Table 1
            # rating is already in t1_rating.  Do NOT also add it to
            # additional_tables, or it gets applied twice.
            additional_tables = []
            additional_flats = []

            # "In Addition To" — carry the policy's existing substandards
            # as additional layers so they are applied alongside the
            # assessment-derived values.
            if not a.in_lieu_of:
                if p.table_rating > 0:
                    additional_tables.append(
                        (float(p.table_rating), 1, 9999)
                    )
                if p.flat_extra > 0:
                    flat_last = 9999
                    if p.flat_to_age > 0:
                        remaining = max(0, p.flat_to_age - p.attained_age) * 12
                        flat_last = abs_policy_month + remaining
                    additional_flats.append(
                        (p.flat_extra, 1, flat_last)
                    )

            if a.use_table and a.direct_table_rating > 0 and has_survival_solve:
                # Only add as additional when a survival solve owns the primary slot
                # Start/stop years are relative to quote date, not policy issue
                # Stop year is exclusive: drops off at beginning of stop year
                ts = abs_policy_month + (a.table_start_year - 1) * 12
                te = abs_policy_month + (a.table_stop_year - 1) * 12 - 1
                additional_tables.append((a.direct_table_rating, ts, te))

            if a.use_flat and a.direct_flat_extra > 0:
                # Start/stop years are relative to quote date, not policy issue
                # Stop year is exclusive: drops off at beginning of stop year
                fs = abs_policy_month + (a.flat_start_year - 1) * 12
                fe = abs_policy_month + (a.flat_stop_year - 1) * 12 - 1
                additional_flats.append((a.direct_flat_extra, fs, fe))

            if a.use_table_2 and a.direct_table_rating_2 > 0:
                ts2 = abs_policy_month + (a.table_2_start_year - 1) * 12
                te2 = abs_policy_month + (a.table_2_stop_year - 1) * 12 - 1
                additional_tables.append((a.direct_table_rating_2, ts2, te2))

            if a.use_flat_2 and a.direct_flat_extra_2 > 0:
                fs2 = abs_policy_month + (a.flat_2_start_year - 1) * 12
                fe2 = abs_policy_month + (a.flat_2_stop_year - 1) * 12 - 1
                additional_flats.append((a.direct_flat_extra_2, fs2, fe2))

            # Increased Decrement → convert to equivalent table rating
            if a.use_increased_decrement and a.direct_increased_decrement > 0:
                id_table_rating = a.direct_increased_decrement / 25.0
                id_start = abs_policy_month + (a.incr_decrement_start_year - 1) * 12
                id_stop = abs_policy_month + (a.incr_decrement_stop_year - 1) * 12 - 1
                additional_tables.append((id_table_rating, id_start, id_stop))

            mort_params = MortalityParams(
                issue_age=p.issue_age,
                sex=p.rate_sex or p.sex,  # rate_sex from 67 segment
                rate_class=p.rate_class,
                policy_month=abs_policy_month,
                maturity_age=p.maturity_age or MATURITY_AGE,
                table_rating_1=t1_rating,
                table_1_start_month=t1_start,
                table_1_last_month=t1_last,
                table_rating_2=t2_rating,
                table_2_start_month=t2_start,
                table_2_last_month=t2_last,
                flat_extra_1=0.0,
                flat_1_start_month=1,
                flat_1_duration=9999,
                additional_tables=additional_tables,
                additional_flats=additional_flats,
                mortality_multiplier=mort_mult,
                improvement_rate=mi_rate,
                improvement_cap=MORTALITY_IMPROVEMENT_CAP,
                is_terminal=is_terminal,
            )

            # ── 3. Compute monthly mortality ────────────────────────────
            mort_engine = MortalityEngine(mort_params)
            self._mort_detail = mort_engine.compute_detailed_table()
            monthly_qx = [row["qx_monthly"] for row in self._mort_detail]

            # ── 4. Compute premiums ─────────────────────────────────────
            # Determine the effective policy year from the quote date
            # (not CyberLife's valuation-based policy_year) so the
            # rate lookup uses the correct duration.
            if p.issue_date:
                anniv_month = p.issue_date.month
                anniv_day = p.issue_date.day
                ysi = quote_date.year - p.issue_date.year
                if (quote_date.month, quote_date.day) < (anniv_month, anniv_day):
                    ysi -= 1
                start_yr = max(ysi + 1, 1)
                anniv_year = p.issue_date.year + ysi
                months_elapsed = (
                    (quote_date.year - anniv_year) * 12
                    + quote_date.month - anniv_month
                )
                if quote_date.day < anniv_day:
                    months_elapsed -= 1
                effective_policy_month = max(months_elapsed + 1, 1)
            else:
                effective_policy_month = p.policy_month
                start_yr = max(p.policy_year, 1)

            prem_calc = PremiumCalculator(p)
            prem_result = prem_calc.compute(policy_year=start_yr)

            is_ul = p.product_type in ("UL", "IUL", "ISWL")

            if is_ul:
                # UL/IUL/ISWL: build premium schedule from user-entered
                # level premium (same logic as policy_panel's
                # _populate_ul_premium_schedule).  TERM rate tables don't
                # exist for these products.
                level_text = self.policy_panel.ul_level_prem_input.text().strip().replace(",", "").replace("$", "")
                try:
                    level_prem = float(level_text) if level_text else 0.0
                except ValueError:
                    level_prem = 0.0

                max_duration = (p.maturity_age - p.issue_age) if p.maturity_age and p.issue_age else 0
                premium_schedule = [0.0] * max(max_duration, 0)
                # Fill future years with the level premium
                for yr_idx in range(start_yr - 1, len(premium_schedule)):
                    premium_schedule[yr_idx] = level_prem
                # Current year = 0 (no more payments in the current year)
                if start_yr - 1 < len(premium_schedule):
                    premium_schedule[start_yr - 1] = 0.0
            else:
                premium_schedule = list(prem_calc.get_base_annual_premium_schedule())

            # Pre-prorate the first year to match Future Premiums table.
            # The APV engine uses these values as-is (no internal proration).
            payments_per_year = {1: 1, 2: 2, 3: 4, 4: 12, 5: 12}.get(
                p.billing_mode, 12
            )
            months_per_payment = 12 // payments_per_year
            modal_factor = db.get_modal_factor(p.plan_code, p.billing_mode)
            modal_fee_factor = db.get_modal_fee_factor(p.plan_code, p.billing_mode)

            payments_made = (effective_policy_month - 1) // months_per_payment + 1
            remaining_payments = max(payments_per_year - payments_made, 0)

            # Prorate the current year entry in the schedule
            # Apply single modal_factor to the total annual premium
            policy_fee_for_proration = db.get_policy_fee(p.plan_code)
            yr_idx = start_yr - 1
            if not is_ul and yr_idx < len(premium_schedule) and remaining_payments < payments_per_year:
                full_annual = premium_schedule[yr_idx]
                modal_total = round(full_annual * modal_factor, 2)
                premium_schedule[yr_idx] = modal_total * remaining_payments

            # ── 5. Compute APV ──────────────────────────────────────────
            apv_engine = APVEngine(annual_rate, p)
            self._apv_detail, self._apv_summary = apv_engine.compute_detailed_table(
                monthly_qx, premium_schedule, is_terminal=is_terminal,
            )

            admin_fee = db.get_admin_fee(p.issue_state)
            min_face = self.assessment_panel.get_min_face_amount()
            p.min_face_amount = min_face

            # Read loan payoff from Policy Info (UL/IUL/ISWL only)
            loan_amount = 0.0
            surrender_value = 0.0
            if p.product_type in ("UL", "IUL", "ISWL"):
                loan_text = self.policy_panel.ul_loan_payoff_input.text().strip().replace(",", "").replace("$", "")
                try:
                    loan_amount = float(loan_text) if loan_text else 0.0
                except ValueError:
                    loan_amount = 0.0
                sv_text = self.policy_panel.ul_surrender_value_input.text().strip().replace(",", "").replace("$", "")
                try:
                    surrender_value = float(sv_text) if sv_text else 0.0
                except ValueError:
                    surrender_value = 0.0

            full = apv_engine.compute_full_acceleration(
                admin_fee=admin_fee,
                apv_summary=self._apv_summary,
                loan_repayment=loan_amount,
                surrender_value=surrender_value,
            )

            partial = apv_engine.compute_partial_acceleration(
                full,
                min_face=min_face,
                admin_fee=admin_fee,
            )

            # ── 6. Compute partial premium ──────────────────────────────
            min_face_prem = prem_calc.compute_min_face_premium(min_face, policy_year=start_yr)

            # Build partial-premium breakdown using PremiumCalculator
            from dataclasses import replace as _replace
            reduced_policy = _replace(p, face_amount=min_face)
            mf_calc = PremiumCalculator(reduced_policy)
            partial_prem_breakdown = mf_calc.build_coverage_breakdown(
                policy_year=start_yr,
                prem_result=min_face_prem,
                modal_factor=modal_factor,
            )

            # ── 7. Per diem ─────────────────────────────────────────────
            perdiem = db.get_per_diem(quote_date.year)
            pd_daily = perdiem[0] if perdiem else 0.0
            pd_annual = perdiem[1] if perdiem else 0.0

            # ── 8. Build result ─────────────────────────────────────────
            modal_label = MODAL_LABELS.get(p.billing_mode, "")
            messages = self._generate_messages(p, full, partial, pd_annual)

            result = ABRQuoteResult(
                # Full
                full_eligible_db=full["eligible_db"],
                full_actuarial_discount=full["actuarial_discount"],
                full_admin_fee=full["admin_fee"],
                full_loan_repayment=full.get("loan_repayment", 0.0),
                full_accel_benefit=full["accelerated_benefit"],
                full_benefit_ratio=full["benefit_ratio"],
                full_surrender_value=full.get("surrender_value", 0.0),
                # Partial
                partial_eligible_db=partial["eligible_db"],
                partial_actuarial_discount=partial["actuarial_discount"],
                partial_admin_fee=partial["admin_fee"],
                partial_loan_repayment=partial.get("loan_repayment", 0.0),
                partial_accel_benefit=partial["accelerated_benefit"],
                partial_benefit_ratio=partial["benefit_ratio"],
                partial_surrender_value=partial.get("surrender_value", 0.0),
                # Premium
                premium_before=(
                    f"${p.monthly_deduction:,.2f}"
                    if p.product_type in ("UL", "IUL", "ISWL")
                    else f"${prem_result.modal_premium:,.2f} {modal_label}"
                ),
                premium_after_full=0.0,
                premium_after_partial=(
                    f"${min_face_prem.modal_premium:,.2f}"
                    if p.product_type in ("UL", "IUL", "ISWL")
                    else f"${min_face_prem.modal_premium:,.2f} {modal_label}"
                ),
                # Details
                plan_description=PremiumCalculator.get_plan_description(p.plan_code),
                abr_interest_rate=annual_rate,
                quote_date=quote_date,
                # APV components
                apv_fb=self._apv_summary.get("pvfb_adjusted", 0.0),
                apv_fp=self._apv_summary.get("pvfp", 0.0),
                apv_fd=0.0,
                per_diem_daily=pd_daily,
                per_diem_annual=pd_annual,
                messages=messages,
            )

            # ── 9. Display results ──────────────────────────────────────
            policy_info_str = f"{p.policy_number} — {p.insured_name}"

            self.results_panel.display_results(result)
            self.results_panel.set_calc_data(
                self._mort_detail, self._apv_detail, self._apv_summary,
                policy_info_str,
            )

            # Also show results inline on the assessment panel
            self.assessment_panel.display_results(result)
            self.assessment_panel.set_calc_data(
                self._mort_detail, self._apv_detail, self._apv_summary,
                policy_info_str,
            )
            self.assessment_panel.set_partial_premium_breakdown(
                partial_prem_breakdown
            )

            # Pass data to output panel for Print Detail
            self.output_panel.set_result(result)
            self.output_panel.set_assessment(self._assessment)
            self.output_panel.set_calc_data(
                self._mort_detail, self._apv_detail, self._apv_summary,
            )
            self.output_panel.set_derived_values(
                self.assessment_panel.get_derived_display_values()
            )

            self.status_label.setText("ABR Quote calculated successfully.")
            self._email_print_btn.setEnabled(True)

        except Exception as e:
            logger.error(f"Calculation error: {e}", exc_info=True)
            self.status_label.setText(f"Calculation error: {e}")

    def _generate_messages(self, p: ABRPolicyData, full: dict, partial: dict,
                           per_diem_annual: float = 0.0) -> list:
        """Generate validation/warning messages."""
        db = get_abr_database()
        messages = []

        if full["accelerated_benefit"] > 100_000:
            messages.append(
                "Heads up! Payout exceeds $100,000 — "
                "Medical Directors should review."
            )

        if p.face_amount > 2_000_000:
            messages.append(
                "Face amount over $2M — check the Data Page "
                "for the maximum acceleration amount."
            )

        min_face = self.assessment_panel.get_min_face_amount()
        if p.face_amount < min_face:
            messages.append(
                f"Face amount (${p.face_amount:,.0f}) is below the "
                f"minimum of ${min_face:,.0f} for partial acceleration."
            )

        if (self._assessment
                and self._assessment.life_expectancy_years <= 2.0
                and self._assessment.rider_type != "Terminal"):
            messages.append(
                "Life expectancy is \u2264 2 years \u2014 confirm with "
                "Medical Directors if this qualifies for a Terminal rider."
            )

        if (self._assessment
                and self._assessment.rider_type == "Chronic"
                and per_diem_annual > 0
                and full["accelerated_benefit"] > per_diem_annual):
            messages.append(
                f"Full acceleration (${full['accelerated_benefit']:,.2f}) exceeds "
                f"the Chronic annual limit (${per_diem_annual:,.2f})."
            )

        return messages

    # ── Header menu ─────────────────────────────────────────────────────

    def _add_header_menu(self):
        """Insert a hamburger menu button into the title bar."""
        bar_layout = self.header_bar.layout()
        if bar_layout is None:
            return

        # Create the menu button — sits before everything in the header
        menu_btn = QPushButton("☰")
        menu_btn.setObjectName("headerMenuBtn")
        menu_btn.setFixedSize(34, 28)
        menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu_btn.setToolTip("Tools")
        menu_btn.setStyleSheet(f"""
            QPushButton#headerMenuBtn {{
                background: transparent;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
                color: {SLATE_TEXT};
            }}
            QPushButton#headerMenuBtn:hover {{
                background-color: rgba(255, 255, 255, 0.15);
                border-color: {SLATE_PRIMARY};
            }}
            QPushButton#headerMenuBtn:pressed {{
                background-color: rgba(255, 255, 255, 0.25);
            }}
        """)
        menu_btn.clicked.connect(self._show_header_menu)

        # Insert at position 0 (before the title label)
        bar_layout.insertWidget(0, menu_btn)

    def _show_header_menu(self):
        """Show the tools popup menu."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {WHITE};
                border: 2px solid {CRIMSON_PRIMARY};
                border-radius: 6px;
                padding: 4px 0px;
                font-size: 12px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
                color: {GRAY_DARK};
            }}
            QMenu::item:selected {{
                background-color: {CRIMSON_PRIMARY};
                color: {WHITE};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {GRAY_MID};
                margin: 4px 8px;
            }}
        """)

        rate_action = menu.addAction("📊  Rate Viewer…")
        rate_action.triggered.connect(self._open_rate_viewer)

        # Position the menu below the button
        btn = self.sender()
        if btn:
            pos = btn.mapToGlobal(btn.rect().bottomLeft())
            menu.exec(pos)
        else:
            menu.exec(self.mapToGlobal(self.header_bar.pos()))

    def _on_resources(self):
        """Open the Resources reference dialog."""
        from .resources_dialog import ResourcesDialog
        dlg = ResourcesDialog(parent=self)
        dlg.exec()

    def _on_email_print(self):
        """Copy the ABR Quote summary directly to clipboard as HTML + plain text."""
        from .email_print_dialog import EmailPrintDialog
        dlg = EmailPrintDialog(
            policy=self._policy,
            result=getattr(self.results_panel, '_result', None),
            assessment=getattr(self.assessment_panel, '_assessment', None),
            parent=self,
        )
        sections = dlg._build_summary_sections()
        html = dlg._build_clipboard_html(sections)
        plain = dlg._build_clipboard_text(sections)

        mime = QMimeData()
        mime.setHtml(html)
        mime.setText(plain)
        QGuiApplication.clipboard().setMimeData(mime)
        QMessageBox.information(self, "Copied", "ABR Quote Summary copied to clipboard.")

    def _open_rate_viewer(self):
        """Open the Rate Viewer window."""
        from .rate_viewer_dialog import RateViewerDialog
        viewer = RateViewerDialog(parent=None)
        viewer.show()
        # Keep a reference so the window isn't garbage-collected
        self._rate_viewer = viewer
