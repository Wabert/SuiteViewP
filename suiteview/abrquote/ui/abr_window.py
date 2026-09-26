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
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtCore import QMimeData
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QPushButton, QMenu, QMessageBox,
)

from suiteview.ui.widgets.frameless_window import FramelessWindowBase
from ..models.abr_data import ABRPolicyData, MedicalAssessment
from ..core.quote_service import ABRQuoteInputs, calculate_abr_quote
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

    def __init__(self, parent=None, initial_policy: str = "",
                 initial_region: str = "CKPR", initial_company: str = ""):
        from suiteview.core.access_control import guard_app_access
        guard_app_access("ABR")
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

        # Optionally pull in a policy on open (e.g. launched from the taskbar).
        if initial_policy:
            self.load_policy(initial_policy, region=initial_region,
                             company_code=initial_company)

    def load_policy(self, policy_number: str, region: str = "CKPR",
                    company_code: str = ""):
        """Load *policy_number* through Step 1's existing retrieve path.

        Public entry point reused by the taskbar policy launcher. ABR always
        uses region CKPR and auto-detects the company, so *region* /
        *company_code* are accepted for a uniform launcher signature but not
        used. Returns to Step 1 so the loaded policy is visible.
        """
        if not (policy_number or "").strip():
            return
        self._set_step(0)
        self.policy_panel.load_policy(policy_number)

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

    def _get_current_accel_inputs(self) -> tuple[float, float]:
        """Return the current (accel_amount, min_face_amount) from assessment inputs."""
        raw = self.assessment_panel._face_input.text().replace("$", "").replace(",", "").strip()
        try:
            accel = float(raw)
        except ValueError:
            accel = self._policy.face_amount if self._policy else 0.0
        min_face = self.assessment_panel.get_min_face_amount()
        return (accel, min_face)

    # ── Full calculation pipeline ───────────────────────────────────────

    def _run_calculation(self):
        """Execute the full ABR quote calculation pipeline."""
        self.status_label.setText("Calculating ABR quote...")

        try:
            p = self._policy
            a = self._assessment
            if p is None or a is None:
                self.status_label.setText("Calculation error: policy or assessment missing")
                return

            def _money_input(widget, default: float = 0.0) -> float:
                text = widget.text().strip().replace(",", "").replace("$", "")
                try:
                    return float(text) if text else default
                except ValueError:
                    return default

            is_ul = p.product_type in ("UL", "IUL", "ISWL")
            level_prem = (
                _money_input(self.policy_panel.ul_level_prem_input)
                if is_ul else None
            )
            loan_amount = (
                _money_input(self.policy_panel.ul_loan_payoff_input)
                if is_ul else 0.0
            )
            surrender_value = (
                _money_input(
                    self.policy_panel.ul_surrender_value_input,
                    float(p.surrender_value or 0.0),
                )
                if is_ul else None
            )

            snapshot = calculate_abr_quote(ABRQuoteInputs(
                policy=p,
                assessment=a,
                quote_date=self.policy_panel.get_quote_date(),
                min_face_amount=self.assessment_panel.get_min_face_amount(),
                interest_rate_override=self.policy_panel.get_interest_rate_override(),
                level_annual_premium=level_prem,
                loan_payoff=loan_amount,
                surrender_value=surrender_value,
            ))

            self._mort_detail = snapshot.mortality_detail
            self._apv_detail = snapshot.apv_detail
            self._apv_summary = snapshot.apv_summary
            result = snapshot.result

            self.results_panel.display_results(result)
            self.results_panel.set_calc_data(
                self._mort_detail, self._apv_detail, self._apv_summary,
                snapshot.policy_info,
            )

            self.assessment_panel.display_results(result)
            self.assessment_panel.set_calc_data(
                self._mort_detail, self._apv_detail, self._apv_summary,
                snapshot.policy_info,
            )
            self.assessment_panel.set_partial_premium_breakdown(
                snapshot.partial_premium_breakdown
            )

            self.output_panel.set_result(result)
            self.output_panel.set_assessment(self._assessment)
            self.output_panel.set_calc_data(
                self._mort_detail, self._apv_detail, self._apv_summary,
            )
            self.output_panel.set_derived_values(
                self.assessment_panel.get_derived_display_values()
            )
            self.output_panel.set_accel_inputs_fn(self._get_current_accel_inputs)
            self.output_panel.set_after_partial_deduction_fn(
                self.assessment_panel.get_after_partial_deduction
            )

            self.status_label.setText("ABR Quote calculated successfully.")
            self._email_print_btn.setEnabled(True)

        except Exception as e:
            logger.error(f"Calculation error: {e}", exc_info=True)
            self.status_label.setText(f"Calculation error: {e}")

    def _generate_messages(self, p: ABRPolicyData, full: dict, partial: dict,
                           per_diem_annual: float = 0.0) -> list:
        """Generate validation/warning messages."""
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

        # Read the user-entered UL annual level premium (used to fund the
        # policy to maturity) so the explanation can reference it.
        level_prem = None
        try:
            txt = self.policy_panel.ul_level_prem_input.text().strip()
            txt = txt.replace(",", "").replace("$", "")
            if txt:
                level_prem = float(txt)
        except (AttributeError, ValueError):
            level_prem = None

        # Read the user-entered Eligible Death Benefit from the Assessment
        # panel's Full Acceleration input (may differ from the quoted value,
        # e.g. Option B policies).
        eligible_override = None
        try:
            raw = self.assessment_panel._face_input.text()
            raw = raw.replace(",", "").replace("$", "").strip()
            if raw:
                eligible_override = float(raw)
        except (AttributeError, ValueError):
            eligible_override = None

        dlg = ResourcesDialog(
            parent=self,
            policy=self._policy,
            result=getattr(self.results_panel, '_result', None),
            assessment=getattr(self.assessment_panel, '_assessment', None),
            level_annual_premium=level_prem,
            eligible_db_override=eligible_override,
        )
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
