"""
ABR Quote — Policy Information Panel (Step 1).

Displays policy lookup bar and policy details retrieved from DB2.
Shows ABR interest rate and per diem limits.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QGroupBox, QFrame, QMessageBox, QDialog,
    QTableWidgetItem, QDateEdit, QSizePolicy,
)

from ..models.abr_data import ABRPolicyData, RiderInfo
from ..models.abr_database import get_abr_database
from ..models.abr_constants import (
    MODAL_LABELS, PLAN_CODE_INFO,
    NON_STANDARD_MODE_MAP,
)
from ..core.premium_calc import PremiumCalculator

# Benefit name mapping for TERM_POINT_BENEFIT.Benefit column
from suiteview.polview.models.cl_polrec.policy_translations import BENEFIT_TYPE_CODES
from ...core.policy_service import get_policy_info
from ..core.abr_policy_service import build_abr_policy
from ...polview.ui.widgets import StyledInfoTableGroup
from .abr_styles import (
    CRIMSON_BG, CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_SUBTLE, CRIMSON_RICH, CRIMSON_SCROLL,
    SLATE_PRIMARY, SLATE_TEXT, SLATE_DARK,
    WHITE, GRAY_DARK, GRAY_LIGHT, GRAY_MID,
    GROUP_BOX_STYLE, INPUT_STYLE, COMBOBOX_STYLE, DATEEDIT_STYLE,
    BUTTON_PRIMARY_STYLE, LABEL_HEADER_STYLE, LABEL_VALUE_STYLE,
    PREMIUM_TABLE_STYLE, PREMIUM_INNER_TABLE_STYLE, PREMIUM_INNER_FRAME_STYLE,
)

logger = logging.getLogger(__name__)


class PolicyPanel(QWidget):
    """Step 1 panel — policy number entry and policy data display.

    Signals:
        policy_loaded(ABRPolicyData): Emitted when policy data is ready.
    """

    policy_loaded = pyqtSignal(object)  # ABRPolicyData
    quote_date_changed = pyqtSignal(object)  # date

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy: Optional[ABRPolicyData] = None
        self._policy_info = None  # PolicyInformation object
        self._prem_breakdown = None  # dict with premium breakdown details
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Two-column layout: left (groups) / right (premium schedule)
        main_hbox = QHBoxLayout()
        main_hbox.setSpacing(12)
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # ── Lookup bar (2×2 grid) ────────────────────────────────────────
        lookup_group = QGroupBox("Policy Lookup")
        lookup_group.setStyleSheet(GROUP_BOX_STYLE)
        lookup_grid = QGridLayout(lookup_group)
        lookup_grid.setContentsMargins(12, 20, 12, 8)
        lookup_grid.setHorizontalSpacing(8)
        lookup_grid.setVerticalSpacing(6)

        # Row 0, Col 0-1: Policy Number
        lbl_pol = QLabel("Policy Number:")
        lbl_pol.setStyleSheet(LABEL_HEADER_STYLE)
        lookup_grid.addWidget(lbl_pol, 0, 0)

        self.policy_input = QLineEdit()
        self.policy_input.setPlaceholderText("Enter policy number...")
        self.policy_input.setStyleSheet(INPUT_STYLE)
        self.policy_input.setFixedWidth(120)
        self.policy_input.returnPressed.connect(self._on_retrieve)
        lookup_grid.addWidget(self.policy_input, 0, 1)

        # Row 0, Col 2-3: Company
        lbl_company = QLabel("Company:")
        lbl_company.setStyleSheet(LABEL_HEADER_STYLE)
        lookup_grid.addWidget(lbl_company, 0, 2)

        self.company_combo = QComboBox()
        self.company_combo.addItems([
            "01 - ANICO",
            "04 - ANTEX",
            "06 - SLAICO",
            "08 - Garden State",
            "26 - ANICONY",
        ])
        self.company_combo.setCurrentIndex(0)
        self.company_combo.setStyleSheet(COMBOBOX_STYLE)
        self.company_combo.setFixedWidth(120)
        lookup_grid.addWidget(self.company_combo, 0, 3)

        # Row 1, Col 0-1: Quote Date
        lbl_qd = QLabel("Quote Date:")
        lbl_qd.setStyleSheet(LABEL_HEADER_STYLE)
        lookup_grid.addWidget(lbl_qd, 1, 0)

        self.quote_date_edit = QDateEdit()
        self.quote_date_edit.setCalendarPopup(True)
        self.quote_date_edit.setDate(QDate.currentDate())
        self.quote_date_edit.setDisplayFormat("M/d/yyyy")
        self.quote_date_edit.setFixedWidth(120)
        self.quote_date_edit.setStyleSheet(DATEEDIT_STYLE)
        self.quote_date_edit.dateChanged.connect(self._on_quote_date_changed)
        lookup_grid.addWidget(self.quote_date_edit, 1, 1)

        # Row 1, Col 3: Get button (aligned with Company combo)
        self.retrieve_btn = QPushButton("Get")
        self.retrieve_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
        self.retrieve_btn.setFixedWidth(120)
        self.retrieve_btn.clicked.connect(self._on_retrieve)
        lookup_grid.addWidget(self.retrieve_btn, 1, 3)

        # Don't let the grid stretch — keep controls tight to the left
        lookup_grid.setColumnStretch(4, 1)

        left_col.addWidget(lookup_group)

        # ── Policy details grid ─────────────────────────────────────────
        self.details_group = QGroupBox("Policy Details")
        self.details_group.setStyleSheet(GROUP_BOX_STYLE)
        details_grid = QGridLayout(self.details_group)
        details_grid.setContentsMargins(12, 20, 12, 8)
        details_grid.setHorizontalSpacing(4)
        details_grid.setVerticalSpacing(4)

        # Create label pairs
        self._detail_labels = {}
        fields = [
            ("Insured:", "insured_name"),
            ("Policy #:", "policy_number"),
            ("Plancode:", "plancode"),
            ("Plan Description:", "plan_desc"),
            ("Sex:", "sex"),
            ("Rate Sex:", "rate_sex"),
            ("Issue Age:", "issue_age"),
            ("Attained Age:", "attained_age"),
            ("Rate Class:", "rate_class"),
            ("Face Amount:", "face_amount"),
            ("Min Face:", "min_face"),
            ("Issue State:", "issue_state"),
            ("Issue Date:", "issue_date"),
            ("Valuation Date:", "valuation_date"),
            ("Policy Year:", "policy_year"),
            ("Month of Year:", "policy_month"),
            ("Base Plancode:", "base_plancode"),
            ("Billing Mode:", "billing_mode"),
            ("Modal Premium:", "modal_premium"),
            ("Calc Premium:", "calc_premium"),
            ("Table Rating:", "table_rating"),
            ("Annual Flat Extra:", "flat_extra"),
            ("Flat Cease Date:", "flat_cease_date"),
        ]

        # Layout as 2 groups of key-value pairs with a gutter between.
        # Grid columns: 0=label1, 1=value1, 2=gutter, 3=label2, 4=value2
        half = (len(fields) + 1) // 2  # rows per column
        for i, (label_text, key) in enumerate(fields):
            row = i % half
            group = i // half  # 0 = left group, 1 = right group
            # Left group uses cols 0,1 — right group uses cols 3,4
            label_col = group * 3
            value_col = group * 3 + 1

            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
            lbl.setFixedWidth(95 if group == 0 else 110)
            details_grid.addWidget(lbl, row, label_col, Qt.AlignmentFlag.AlignLeft)

            val = QLabel("—")
            val.setStyleSheet(f"color: {GRAY_DARK}; font-size: 11px;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setFixedWidth(110 if group == 0 else 160)
            details_grid.addWidget(val, row, value_col)
            self._detail_labels[key] = val

        # Gutter column (col 2) for spacing between the two groups
        details_grid.setColumnMinimumWidth(2, 20)
        # Push everything left — stretch on the last column
        details_grid.setColumnStretch(5, 1)

        # Add a small detail button next to "Calc Premium"
        self._calc_detail_btn = QPushButton("🔎")
        self._calc_detail_btn.setFixedSize(22, 20)
        self._calc_detail_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._calc_detail_btn.setToolTip("View premium calculation breakdown")
        self._calc_detail_btn.setStyleSheet(
            f"QPushButton {{ font-size: 11px; border: 1px solid {CRIMSON_PRIMARY};"
            f" border-radius: 3px; background: {WHITE}; padding: 0; }}"
            f"QPushButton:hover {{ background: {CRIMSON_SUBTLE}; }}"
        )
        self._calc_detail_btn.clicked.connect(self._show_premium_breakdown)
        self._calc_detail_btn.setVisible(False)
        # Calc Premium is in the right-group.  Find its position.
        # "Calc Premium" is field index 19 in the fields list (0-based).
        # half = (23+1)//2 = 12, so row = 19 % 12 = 7, group = 19//12 = 1
        calc_prem_row = 7
        details_grid.addWidget(self._calc_detail_btn, calc_prem_row, 5)

        self.details_group.setVisible(False)
        left_col.addWidget(self.details_group)

        # ── Coverages ─────────────────────────────────────────────
        self.riders_group = QGroupBox("Coverages")
        self.riders_group.setStyleSheet(GROUP_BOX_STYLE)
        self._riders_layout = QVBoxLayout(self.riders_group)
        self._riders_layout.setContentsMargins(12, 20, 12, 8)
        self._riders_flow = QHBoxLayout()
        self._riders_flow.setSpacing(6)
        self._riders_flow.setContentsMargins(0, 0, 0, 0)
        self._riders_layout.addLayout(self._riders_flow)
        self._riders_placeholder = QLabel("No riders or benefits.")
        self._riders_placeholder.setStyleSheet(
            f"color: {GRAY_DARK}; font-size: 11px; font-style: italic;"
        )
        self._riders_layout.addWidget(self._riders_placeholder)
        self.riders_group.setVisible(False)
        left_col.addWidget(self.riders_group)

        # ── ABR Rate Info ───────────────────────────────────────────────
        self.rate_group = QGroupBox("ABR Rate Information")
        self.rate_group.setStyleSheet(GROUP_BOX_STYLE)
        rate_vbox = QVBoxLayout(self.rate_group)
        rate_vbox.setContentsMargins(12, 20, 12, 8)
        rate_vbox.setSpacing(6)

        # Row 1: Rate info labels (quote date, interest rate, per diem)
        rate_layout = QHBoxLayout()
        rate_layout.setSpacing(0)

        self.quote_date_label = QLabel("Quote Date: —")
        self.quote_date_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {CRIMSON_DARK};")
        rate_layout.addWidget(self.quote_date_label)

        rate_layout.addSpacing(30)

        self.interest_label = QLabel("ABR Interest Rate: —")
        self.interest_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {CRIMSON_DARK};")
        rate_layout.addWidget(self.interest_label)

        rate_layout.addSpacing(30)

        self.perdiem_label = QLabel("Per Diem: —")
        self.perdiem_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {CRIMSON_DARK};")
        rate_layout.addWidget(self.perdiem_label)

        rate_layout.addStretch()
        rate_vbox.addLayout(rate_layout)

        # Row 2: Override toggle + input (positioned below the interest rate)
        override_row = QHBoxLayout()
        override_row.setSpacing(6)
        # Left indent to align below the "ABR Interest Rate:" label
        override_row.setContentsMargins(170, 0, 0, 0)
        self._rate_override_btn = QPushButton("Override")
        self._rate_override_btn.setCheckable(True)
        self._rate_override_btn.setChecked(False)
        self._rate_override_btn.setFixedSize(70, 22)
        self._rate_override_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rate_override_btn.setToolTip("Toggle to manually override the ABR interest rate")
        self._rate_override_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {WHITE};
                color: {GRAY_DARK};
                border: 1px solid {CRIMSON_PRIMARY};
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                background-color: {CRIMSON_SUBTLE};
            }}
            QPushButton:checked {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {CRIMSON_RICH}, stop:1 {CRIMSON_PRIMARY});
                color: {WHITE};
                border-color: {CRIMSON_DARK};
            }}
        """)
        self._rate_override_btn.toggled.connect(self._on_rate_override_toggled)
        override_row.addWidget(self._rate_override_btn)

        self._rate_override_input = QLineEdit()
        self._rate_override_input.setPlaceholderText("e.g. 5.20")
        self._rate_override_input.setFixedWidth(80)
        self._rate_override_input.setStyleSheet(INPUT_STYLE)
        self._rate_override_input.setVisible(False)
        self._rate_override_input.editingFinished.connect(self._on_rate_override_changed)
        override_row.addWidget(self._rate_override_input)

        self._rate_override_pct = QLabel("%")
        self._rate_override_pct.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {CRIMSON_DARK};")
        self._rate_override_pct.setVisible(False)
        override_row.addWidget(self._rate_override_pct)

        override_row.addStretch()
        rate_vbox.addLayout(override_row)

        self.rate_group.setVisible(False)
        left_col.addWidget(self.rate_group)

        # ── Premium mismatch warning ────────────────────────────────────
        self.premium_warning = QLabel("")
        self.premium_warning.setStyleSheet(
            f"color: #CC0000; font-size: 11px; font-weight: bold;"
            f" padding: 4px 8px;"
        )
        self.premium_warning.setWordWrap(True)
        self.premium_warning.setVisible(False)
        left_col.addWidget(self.premium_warning)
        left_col.addStretch()

        # ── Premium schedule (right column) ─────────────────────────────
        right_col = QVBoxLayout()
        right_col.setSpacing(0)
        self.premium_group = StyledInfoTableGroup(
            "Future Premiums for Acceleration", show_info=False, show_table=True
        )
        # Override the default PolView green/gold theme with Crimson Slate
        self.premium_group.setStyleSheet(PREMIUM_TABLE_STYLE)
        self.premium_table = self.premium_group.table
        # Force-override the green PolView header on the inner widgets
        self.premium_table._data_table.setStyleSheet(PREMIUM_INNER_TABLE_STYLE)
        self.premium_table._outer_frame.setStyleSheet(PREMIUM_INNER_FRAME_STYLE)
        self.premium_table.setColumnCount(3)
        self.premium_table.setHorizontalHeaderLabels(["Year", "Age", "Annual Premium"])
        self.premium_group.setVisible(False)
        # Make the premium group expand to fill available vertical space
        self.premium_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        right_col.addWidget(self.premium_group, 1)

        # Wire two-column layout
        main_hbox.addLayout(left_col)
        main_hbox.addLayout(right_col)
        main_hbox.setStretchFactor(left_col, 0)
        main_hbox.setStretchFactor(right_col, 1)
        layout.addLayout(main_hbox, 1)

    # ── Actions ─────────────────────────────────────────────────────────

    def _on_retrieve(self):
        """Retrieve policy data from DB2."""
        policy_num = self.policy_input.text().strip()
        if not policy_num:
            return

        region = "CKPR"  # Always CKPR
        company = self.company_combo.currentText()
        self.retrieve_btn.setEnabled(False)

        try:
            policy, policy_info = build_abr_policy(policy_num, region)
            if policy:
                policy.company = company
                self._policy = policy
                self._policy_info = policy_info
                self._populate_details(policy)
                self._populate_rate_info()
                self._populate_riders_benefits()
                self.details_group.setVisible(True)
                self.rate_group.setVisible(True)
                self.riders_group.setVisible(True)
                self.premium_group.setVisible(True)
                self._populate_premium_schedule()
                self.policy_loaded.emit(policy)
            else:
                logger.warning(f"Could not retrieve policy {policy_num} from {region}.")
        except Exception as e:
            logger.error(f"Error retrieving policy: {e}")
        finally:
            self.retrieve_btn.setEnabled(True)

    def _create_manual_policy(self, policy_num: str, region: str) -> ABRPolicyData:
        """Create a stub policy for manual data entry (when DB2 is unavailable)."""
        return ABRPolicyData(
            policy_number=policy_num,
            region=region,
        )

    def _populate_details(self, p: ABRPolicyData):
        """Fill in the detail labels from policy data."""
        labels = self._detail_labels

        labels["insured_name"].setText(p.insured_name or "—")
        labels["policy_number"].setText(p.policy_number)
        labels["plancode"].setText(p.plan_code or "—")
        sex_display = {"M": "Male", "F": "Female", "U": "Unisex"}.get(p.sex, p.sex or "—")
        labels["sex"].setText(sex_display)
        # Rate sex — show just the code letter (F, M, U)
        rate_sex_display = p.rate_sex or "—"
        if p.rate_sex and p.rate_sex != p.sex:
            rate_sex_display += f"  ⚠"
        labels["rate_sex"].setText(rate_sex_display)
        labels["issue_age"].setText(str(p.issue_age) if p.issue_age else "—")
        labels["attained_age"].setText(str(p.attained_age) if p.attained_age else "—")
        labels["rate_class"].setText(p.rate_class or "—")
        labels["face_amount"].setText(f"${p.face_amount:,.2f}" if p.face_amount else "—")
        labels["min_face"].setText(f"${p.min_face_amount:,.0f}")
        labels["issue_state"].setText(p.issue_state if p.issue_state else "—")
        if p.issue_date:
            labels["issue_date"].setText(
                f"{p.issue_date.month}/{p.issue_date.day}/{p.issue_date.year}"
            )
        else:
            labels["issue_date"].setText("—")
        labels["policy_year"].setText(str(p.policy_year) if p.policy_year else "—")
        labels["policy_month"].setText(str(p.policy_month) if p.policy_month else "—")
        labels["base_plancode"].setText(p.base_plancode if p.base_plancode else "—")

        # Plan description
        info = PLAN_CODE_INFO.get(p.plan_code.upper(), None) if p.plan_code else None
        if info:
            labels["plan_desc"].setText(f"{info[1]} ({info[0]}-Year Level)")
        else:
            labels["plan_desc"].setText("—")

        labels["billing_mode"].setText(MODAL_LABELS.get(p.billing_mode, str(p.billing_mode)))
        labels["modal_premium"].setText(
            f"${p.modal_premium:,.2f} (monthly)" if p.modal_premium else "—"
        )
        if p.table_rating_2 > 0:
            labels["table_rating"].setText(f"{p.table_rating}  |  {p.table_rating_2}")
        else:
            labels["table_rating"].setText(str(p.table_rating))
        labels["flat_extra"].setText(
            f"${p.flat_extra:.2f}" if p.flat_extra > 0 else "None"
        )
        labels["flat_cease_date"].setText(
            f"{p.flat_cease_date.month}/{p.flat_cease_date.day}/{p.flat_cease_date.year}"
            if p.flat_cease_date else "—"
        )

        # Valuation Date — always current date regardless of quote date
        today = date.today()
        labels["valuation_date"].setText(
            f"{today.month}/{today.day}/{today.year}  (as of today)"
        )
        labels["valuation_date"].setStyleSheet(
            f"color: {CRIMSON_DARK}; font-size: 11px; font-style: italic;"
        )

    def get_quote_date(self) -> date:
        """Return the currently selected quote date."""
        qd = self.quote_date_edit.date()
        return date(qd.year(), qd.month(), qd.day())

    def _on_quote_date_changed(self, qdate: QDate):
        """User changed the quote date — refresh rate info and premiums."""
        if self._policy:
            self._populate_rate_info()
            self._populate_premium_schedule()
            self.quote_date_changed.emit(self.get_quote_date())

    def _on_rate_override_toggled(self, checked: bool):
        """Show/hide the override input field."""
        self._rate_override_input.setVisible(checked)
        self._rate_override_pct.setVisible(checked)
        if not checked:
            self._rate_override_input.clear()
        self._populate_rate_info()
        # Also trigger recalculation if policy & assessment available
        if self._policy:
            self.quote_date_changed.emit(self.get_quote_date())

    def _on_rate_override_changed(self):
        """User finished editing the override rate — update display."""
        self._populate_rate_info()
        if self._policy:
            self.quote_date_changed.emit(self.get_quote_date())

    def get_interest_rate_override(self) -> Optional[float]:
        """Return the overridden interest rate as a decimal, or None if not overriding.

        Returns:
            float: e.g. 0.052 for 5.20%, or None if override is not active.
        """
        if self._rate_override_btn.isChecked():
            text = self._rate_override_input.text().strip()
            if text:
                try:
                    return float(text) / 100.0  # user enters %, we return decimal
                except ValueError:
                    pass
        return None

    def _populate_rate_info(self):
        """Populate quote date, ABR interest rate, and per diem from database."""
        db = get_abr_database()

        # Use the quote date from the date picker
        qd = self.get_quote_date()
        self.quote_date_label.setText(
            f"Quote Date: {qd.month}/{qd.day}/{qd.year}"
        )

        # Interest rate — check for override first
        override_rate = self.get_interest_rate_override()
        if override_rate is not None:
            self.interest_label.setText(
                f"ABR Interest Rate: {override_rate*100:.2f}%  (override)"
            )
            self.interest_label.setStyleSheet(
                f"font-size: 12px; font-weight: bold; color: #CC0000;"
            )
        else:
            # Look up the effective rate from the database
            quote_month_str = qd.strftime("%Y-%m")  # e.g. "2026-02"
            rate_info = db.get_effective_interest_rate(quote_month_str)
            if rate_info:
                dt, rate = rate_info
                self.interest_label.setText(
                    f"ABR Interest Rate: {rate*100:.2f}%  (eff. {dt})"
                )
            else:
                self.interest_label.setText("ABR Interest Rate: Not available")
            self.interest_label.setStyleSheet(
                f"font-size: 12px; font-weight: bold; color: {CRIMSON_DARK};"
            )

        # Per diem — based on the quote date year
        perdiem = db.get_per_diem(qd.year)
        if perdiem:
            daily, annual = perdiem
            self.perdiem_label.setText(
                f"Per Diem: ${daily:,.0f}/day  |  Annual Limit: ${annual:,.0f}"
            )
        else:
            self.perdiem_label.setText("Per Diem: Not available")

    @staticmethod
    def _is_primary_insured_coverage(cov) -> bool:
        """Return True if coverage covers the primary insured and is not a premium waiver.

        Excludes:
          - Coverages with person_code != '00' (e.g. CTR has '50' for children)
          - Premium waiver coverages (plancode containing 'WP' or 'PW')
        """
        # Person code '00' = primary insured
        if cov.person_code not in ("00", ""):
            return False
        # Exclude premium waiver coverages
        pc = (cov.plancode or "").upper()
        form = (cov.form_number or "").upper()
        if "WP" in pc or "PW" in pc or "WP" in form or "PW" in form:
            return False
        return True

    def _populate_riders_benefits(self):
        """Populate coverage buttons from PolicyInformation (base + riders + benefits)."""
        # Clear previous buttons
        while self._riders_flow.count():
            item = self._riders_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        pi = self._policy_info
        if pi is None:
            self._riders_placeholder.setVisible(True)
            return

        items = []  # list of (label_text, detail_data_dict)

        # All coverages — base first, then riders
        try:
            coverages = pi.get_coverages()
            for cov in coverages:
                form = cov.form_number or cov.plancode
                items.append((form, {"type": "coverage", "cov": cov}))
        except Exception as e:
            logger.debug(f"Error loading coverages: {e}")

        # Benefits
        try:
            benefits = pi.get_benefits()
            for bnf in benefits:
                form = bnf.form_number or bnf.benefit_code
                items.append((form, {"type": "benefit", "bnf": bnf}))
        except Exception as e:
            logger.debug(f"Error loading benefits: {e}")

        if not items:
            self._riders_placeholder.setVisible(True)
            return

        self._riders_placeholder.setVisible(False)

        RIDER_BTN_STYLE = (
            f"QPushButton {{"
            f"  background-color: {WHITE}; color: {CRIMSON_DARK};"
            f"  border: 1px solid {CRIMSON_PRIMARY}; border-radius: 3px;"
            f"  font-size: 10px; font-weight: bold;"
            f"  padding: 3px 8px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {CRIMSON_SUBTLE};"
            f"}}"
        )

        for label_text, detail_data in items:
            btn = QPushButton(label_text)
            btn.setStyleSheet(RIDER_BTN_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip("Click for details")
            # Capture detail_data in the lambda
            btn.clicked.connect(lambda checked, d=detail_data: self._show_rider_detail(d))
            self._riders_flow.addWidget(btn)

        self._riders_flow.addStretch()

    def _show_rider_detail(self, detail_data: dict):
        """Show a dialog with coverage/benefit detail (mirrors PolView Coverages tab)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Rider / Benefit Detail")
        dlg.setMinimumWidth(340)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)

        def add_row(row, label_text, value_text):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
            grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignLeft)
            val = QLabel(str(value_text) if value_text is not None else "")
            val.setStyleSheet(f"color: {GRAY_DARK}; font-size: 11px;")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(val, row, 1, Qt.AlignmentFlag.AlignRight)

        if detail_data["type"] == "coverage":
            cov = detail_data["cov"]
            row = 0
            add_row(row, "Phase:", cov.cov_pha_nbr); row += 1
            add_row(row, "Form:", cov.form_number); row += 1
            add_row(row, "Plancode:", cov.plancode); row += 1
            add_row(row, "Issue Date:", cov.issue_date.strftime("%m/%d/%Y") if cov.issue_date else ""); row += 1
            add_row(row, "Maturity Date:", cov.maturity_date.strftime("%m/%d/%Y") if cov.maturity_date else ""); row += 1
            add_row(row, "Face Amount:", f"${cov.face_amount:,.2f}" if cov.face_amount else ""); row += 1
            add_row(row, "Issue Age:", cov.issue_age); row += 1
            add_row(row, "Gender:", cov.sex_desc or cov.sex_code); row += 1
            add_row(row, "Rate Class:", f"{cov.rate_class} - {cov.rate_class_desc}" if cov.rate_class_desc else cov.rate_class); row += 1
            tbl = cov.table_rating or 0
            add_row(row, "Table Rating:", str(tbl)); row += 1
            flat = cov.flat_extra
            add_row(row, "Annual Flat Extra:", f"${flat:,.2f}" if flat and float(flat) > 0 else "None"); row += 1
            add_row(row, "Flat Cease:", cov.flat_cease_date.strftime("%m/%d/%Y") if cov.flat_cease_date else ""); row += 1
            add_row(row, "Status:", cov.cov_status_desc or cov.cov_status); row += 1
            add_row(row, "Person Code:", f"{cov.person_code} - {cov.person_desc}" if cov.person_desc else cov.person_code); row += 1
            from suiteview.audit.models.audit_constants import LIVES_COVERED_CODES
            lives_desc = LIVES_COVERED_CODES.get(cov.lives_cov_cd, "")
            lives_display = f"{cov.lives_cov_cd} - {lives_desc}" if lives_desc else cov.lives_cov_cd
            add_row(row, "Lives Covered:", lives_display); row += 1
            add_row(row, "VPU:", f"{cov.vpu:,.3f}" if cov.vpu else ""); row += 1
            rate_val = cov.rate
            add_row(row, "Rate:", str(rate_val) if rate_val is not None else ""); row += 1
            if cov.cola_indicator == "1":
                add_row(row, "COLA:", "Yes"); row += 1
            if cov.gio_indicator == "Y":
                add_row(row, "GIO:", "Yes"); row += 1

        elif detail_data["type"] == "benefit":
            bnf = detail_data["bnf"]
            row = 0
            add_row(row, "Benefit Code:", bnf.benefit_code); row += 1
            add_row(row, "Phase:", bnf.cov_pha_nbr); row += 1
            add_row(row, "Type:", bnf.benefit_type_cd); row += 1
            add_row(row, "Description:", bnf.benefit_desc); row += 1
            add_row(row, "Form:", bnf.form_number); row += 1
            add_row(row, "Issue Date:", bnf.issue_date.strftime("%m/%d/%Y") if bnf.issue_date else ""); row += 1
            add_row(row, "Cease Date:", bnf.cease_date.strftime("%m/%d/%Y") if bnf.cease_date else ""); row += 1
            add_row(row, "Orig Cease:", bnf.orig_cease_date.strftime("%m/%d/%Y") if bnf.orig_cease_date else ""); row += 1
            add_row(row, "Units:", f"{bnf.units:,.2f}" if bnf.units else ""); row += 1
            add_row(row, "VPU:", f"{bnf.vpu:,.3f}" if bnf.vpu else ""); row += 1
            add_row(row, "Amount:", f"${bnf.benefit_amount:,.2f}" if bnf.benefit_amount else ""); row += 1
            add_row(row, "Issue Age:", bnf.issue_age if bnf.issue_age else ""); row += 1
            rating = bnf.rating_factor
            try:
                rating_str = f"{float(rating):.0%}" if rating else ""
            except Exception:
                rating_str = ""
            add_row(row, "Rating:", rating_str); row += 1
            add_row(row, "Renewal:", bnf.renewal_indicator); row += 1
            add_row(row, "COI Rate:", bnf.coi_rate if bnf.coi_rate else ""); row += 1

        layout.addLayout(grid)
        layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dlg.exec()

    def _populate_premium_schedule(self):
        """Populate premium schedule table from current year to maturity.

        Follows Signature Term Product Spec calculation order:
            Step 1-2: per-$1000 rate (from get_premium_schedule)
            Step 3: round(rate × face/1000, 2)
            Step 4: + rider annual premiums
            Step 5: + $60 policy fee

        Prorates the first year based on remaining modal payments
        until the next policy anniversary.
        """
        p = self._policy
        if not p or not p.plan_code:
            return

        try:
            t_total = time.perf_counter()
            db = get_abr_database()
            db.reset_query_stats()

            calc = PremiumCalculator(p)

            t0 = time.perf_counter()
            rate_schedule = calc.get_premium_schedule()       # per-$1000 rates (Steps 1+2)
            t_rate = time.perf_counter() - t0

            t0 = time.perf_counter()
            annual_schedule = calc.get_annual_premium_schedule()  # full annual $ (Steps 1-5, with riders)
            t_annual = time.perf_counter() - t0

            t0 = time.perf_counter()
            base_annual_schedule = calc.get_base_annual_premium_schedule()  # base only (no riders/CTR)
            t_base = time.perf_counter() - t0

            if not rate_schedule or not annual_schedule:
                return

            policy_fee = db.get_policy_fee(p.plan_code)

            # Compute cur_yr early — needed for rider_annual proration below
            qd = self.get_quote_date()
            if p.issue_date:
                _ysi = qd.year - p.issue_date.year
                if (qd.month, qd.day) < (p.issue_date.month, p.issue_date.day):
                    _ysi -= 1
                cur_yr = max(_ysi + 1, 1)
            else:
                cur_yr = max(p.policy_year, 1)

            # rider_annual is now computed per-year inside get_annual_premium_schedule
            # For the proration below, compute rider total for the current year
            rider_annual = calc._compute_all_riders_premium(cur_yr) if hasattr(calc, '_compute_all_riders_premium') else p.rider_annual_premium

            # ── Billing mode → payments per year ────────────────────────
            payments_per_year = {1: 1, 2: 2, 3: 4, 4: 12, 5: 12}.get(
                p.billing_mode, 12
            )
            months_per_payment = 12 // payments_per_year

            # ── Remaining payments in current policy year ───────────────
            # Recompute policy_month based on the quote date so that
            # backdating the quote date properly reduces remaining payments.
            # policy_month = month within the current policy year (1-12).
            qd_for_remaining = self.get_quote_date()
            if p.issue_date:
                # Months from the most recent anniversary to the quote date.
                # The anniversary month/day repeats each year from issue_date.
                anniv_month = p.issue_date.month
                anniv_day = p.issue_date.day
                # Which anniversary year are we in?
                ysi = qd_for_remaining.year - p.issue_date.year
                if (qd_for_remaining.month, qd_for_remaining.day) < (anniv_month, anniv_day):
                    ysi -= 1
                # Most recent anniversary
                anniv_year = p.issue_date.year + ysi
                # Months elapsed since that anniversary
                months_elapsed = (
                    (qd_for_remaining.year - anniv_year) * 12
                    + qd_for_remaining.month - anniv_month
                )
                # If we haven't reached the anniversary day within this month,
                # we're still in the previous month of the policy year.
                if qd_for_remaining.day < anniv_day:
                    months_elapsed -= 1
                effective_policy_month = max(months_elapsed + 1, 1)  # 1-based
            else:
                effective_policy_month = p.policy_month

            # A payment is due at months 1, 1+interval, 1+2*interval, ...
            # The payment on the quote date is considered already paid,
            # so we count it as made.
            payments_made = (effective_policy_month - 1) // months_per_payment + 1
            remaining_payments = max(payments_per_year - payments_made, 0)

            # ── Modal factor ────────────────────────────────────────────
            modal_factor = db.get_modal_factor(p.plan_code, p.billing_mode)
            modal_fee_factor = db.get_modal_fee_factor(p.plan_code, p.billing_mode)

            # ── Validation: compare calculated vs. CyberLife modal ──────
            # cur_yr already computed above
            if cur_yr - 1 < len(annual_schedule):
                calc_annual = annual_schedule[cur_yr - 1]
            else:
                calc_annual = 0.0
            # Apply single modal factor to the total annual premium
            from ..core.premium_calc import arithmetic_round
            calc_modal = arithmetic_round(calc_annual * modal_factor, 2)
            cyberlife_modal = p.modal_premium

            # ── Display calculated premium in details grid ──────────────
            self._detail_labels["calc_premium"].setText(f"${calc_modal:,.2f}")
            self._calc_detail_btn.setVisible(True)

            # ── Store coverage-centric breakdown for the detail dialog ────
            # Build one entry per coverage (base + riders).  Each entry
            # contains the coverage's own rate info plus any benefits.
            pi = self._policy_info
            cov_breakdowns = []
            try:
                all_coverages = pi.get_coverages() if pi else []
                all_bens = pi.get_benefits() if pi else []
            except Exception:
                all_coverages = []
                all_bens = []

            for cov_idx, cov in enumerate(all_coverages):
                pc = (cov.plancode or "").upper()
                cov_sex = {"1": "M", "2": "F"}.get(
                    cov.sex_code, cov.sex_code or p.sex
                )
                cov_rc = (cov.rate_class or "0").strip()
                if cov_rc == "0" and cov.is_base:
                    cov_rc = p.rate_class
                cov_table = int(cov.table_rating or 0)
                cov_issue_age = int(cov.issue_age or 0)
                cov_face = float(cov.face_amount or 0)
                cov_units = cov_face / 1000.0
                cov_flat = 0.0

                # Band lookup (needed for rate lookup and display)
                cov_band_code = ""
                try:
                    cov_band_code = calc.db.get_band(pc, cov_face, p.issue_date) or ""
                except Exception:
                    pass

                # Rate lookup
                if cov.is_base:
                    # Base coverage: use the pre-computed raw rate
                    raw_schedule = calc.get_rate_schedule()
                    cov_rate = raw_schedule[cur_yr - 1] if raw_schedule and cur_yr - 1 < len(raw_schedule) else 0.0
                    cov_flat = p.flat_extra if (p.flat_extra > 0 and p.flat_to_age > 0 and p.attained_age < p.flat_to_age) else 0.0
                    cov_sex = p.rate_sex or p.sex  # use rate sex for base
                    cov_rc = p.rate_class
                else:
                    # Non-base: look up from TERM tables
                    try:
                        band = cov_band_code
                        cov_rate = calc.db.get_term_rate(
                            pc, cov_sex, cov_rc, band, cov_issue_age, cur_yr,
                        )
                        if cov_rate is None:
                            logger.debug(
                                f"No TERM rate for coverage {pc}: "
                                f"sex={cov_sex} rc={cov_rc} band={band} "
                                f"age={cov_issue_age} yr={cur_yr}"
                            )
                            cov_rate = 0.0
                    except Exception as e:
                        logger.debug(f"Error looking up TERM rate for {pc}: {e}")
                        cov_rate = 0.0

                rating_factor = 1.0 + cov_table * 0.25
                step1 = arithmetic_round(cov_rate * rating_factor, 2)
                step2 = step1 + cov_flat
                cov_premium = arithmetic_round(step2 * cov_units, 2)

                # ── Benefits on this coverage ─────────────────────
                cov_benefits = [b for b in all_bens
                                if b.cov_pha_nbr == cov.cov_pha_nbr]
                benefit_details = []
                # NOTE: For Term products, band is a coverage-level concept
                # determined by the coverage face amount — NOT the individual
                # benefit amount.  Use the same band for all benefit lookups
                # on this coverage.
                cov_band = calc.db.get_band(pc, cov_face, p.issue_date)
                for ben in cov_benefits:
                    if ben.cease_date and ben.cease_date < date.today():
                        continue
                    ben_type = (ben.benefit_type_cd or "").strip()
                    ben_sub = (ben.benefit_subtype_cd or "").strip()

                    # NOTE: We must skip '#' benefits (ABR) since they have no premium charge.
                    # As discussed before, DO NOT REMOVE THIS CHECK! Including them causes
                    # the display calculation to incorrectly fall back to the base rate and
                    # wildly inflate the displayed coverage premium sum!
                    if ben_type == "#":
                        continue

                    # Recreate the RiderInfo object that the PremiumEngine expects
                    ben_face = float(ben.benefit_amount or 0) or cov_face
                    ben_issue_age = int(ben.issue_age or cov_issue_age or 0)
                    ben_units = ben_face / 1000.0
                    ben_rating = float(ben.rating_factor) if ben.rating_factor else 0.0
                    
                    ben_rider = RiderInfo(
                        plancode=pc,
                        face_amount=ben_face,
                        issue_age=ben_issue_age,
                        sex=cov_sex,
                        rate_class=cov_rc,
                        table_rating=cov_table,
                        rider_type="BENEFIT",
                        fallback_premium=0.0,
                        benefit_type=ben_type,
                        benefit_subtype=ben_sub,
                        benefit_units=float(ben.units or 0),
                        benefit_vpu=float(ben.vpu or 0),
                        benefit_rating_factor=ben_rating,
                        cease_date=ben.cease_date,
                    )

                    # Use the PremiumCalculator to compute the exact rider premium
                    ben_premium = calc.compute_rider_annual_premium(ben_rider, cur_yr)

                    # For display purposes only, figure out the rate and PW factor
                    is_pw = ben_type in ("3", "4")
                    pw_factor = ben_rating if ben_rating > 0 else (
                        1.50 if cov_table == 1 else (2.25 if cov_table == 2 else 1.0)
                    )
                    
                    # Try to look up the base rate for display in the grid
                    ben_rate = None
                    try:
                        ben_code = f"{ben_type}{ben_sub}"
                        ben_name = BENEFIT_TYPE_CODES.get(ben_type, ben_code)
                        ben_rate = calc.db.get_benefit_rate(
                            pc, ben_code, ben_name,
                            cov_sex, cov_rc, cov_band,
                            ben_issue_age, cur_yr,
                        )
                    except Exception:
                        pass
                        
                    # Label includes benefit code for clarity
                    if is_pw:
                        lbl = f"PW (Ben {ben_code})"
                    else:
                        lbl = f"Ben {ben_code}"
                        
                    benefit_details.append({
                        "type": ben_type,
                        "subtype": ben_sub,
                        "label": lbl,
                        "rate": ben_rate,
                        "factor": pw_factor,
                        "premium": ben_premium,
                    })
                    cov_premium += ben_premium

                cov_breakdowns.append({
                    "plancode": pc,
                    "issue_age": cov_issue_age,
                    "sex": cov_sex,
                    "rate_class": cov_rc,
                    "band": cov_band_code,
                    "rate": cov_rate,
                    "table_rating": cov_table,
                    "rating_factor": rating_factor,
                    "flat_extra": cov_flat,
                    "units": cov_units,
                    "benefits": benefit_details,
                    "premium": cov_premium,
                })

            self._prem_breakdown = {
                "policy_number": p.policy_number,
                "policy_year": cur_yr,
                "coverages": cov_breakdowns,
                "policy_fee": policy_fee,
                "billing_mode": p.billing_mode,
                "modal_label": MODAL_LABELS.get(p.billing_mode, "Annual"),
                "modal_factor": modal_factor,
                "calc_modal": calc_modal,
            }

            # ── Show/hide mismatch warning ───────────────────────────────
            if cyberlife_modal > 0 and abs(calc_modal - cyberlife_modal) > 0.02:
                diff = calc_modal - cyberlife_modal
                self.premium_warning.setText(
                    f"⚠ Premium mismatch: Calculated ${calc_modal:,.2f} "
                    f"vs CyberLife ${cyberlife_modal:,.2f} "
                    f"(diff ${diff:+,.2f})"
                )
                self.premium_warning.setVisible(True)
                # Also highlight the calc premium label in red
                self._detail_labels["calc_premium"].setStyleSheet(
                    f"color: #CC0000; font-size: 11px; font-weight: bold;"
                )
                logger.warning(
                    f"Modal premium mismatch: calculated=${calc_modal:.2f} "
                    f"vs CyberLife=${cyberlife_modal:.2f} "
                    f"(diff=${diff:+.2f})"
                )
            else:
                self.premium_warning.setVisible(False)
                self._detail_labels["calc_premium"].setStyleSheet(
                    f"color: {GRAY_DARK}; font-size: 11px;"
                )

            # ── Build schedule rows ─────────────────────────────────────
            max_duration = p.maturity_age - p.issue_age

            # Use the quote date to compute the policy year at that date
            # so that backdating the quote date shifts Year & Age.
            quote_date = self.get_quote_date()
            current_calendar = quote_date.year
            if p.issue_date:
                # Compute policy year at the quote date
                years_since_issue = quote_date.year - p.issue_date.year
                # If we haven't reached the anniversary month/day yet, subtract one
                if (quote_date.month, quote_date.day) < (p.issue_date.month, p.issue_date.day):
                    years_since_issue -= 1
                start_year = max(years_since_issue + 1, 1)
            else:
                start_year = max(p.policy_year, 1)

            rows = []
            for yr in range(start_year, max_duration + 1):
                if yr - 1 >= len(base_annual_schedule):
                    break
                full_annual = base_annual_schedule[yr - 1]

                if yr == start_year and remaining_payments < payments_per_year:
                    # First year: only the remaining modal payments
                    modal_prem = arithmetic_round(full_annual * modal_factor, 2)
                    display_prem = modal_prem * remaining_payments
                else:
                    display_prem = full_annual

                cal_year = current_calendar + (yr - start_year)
                attained_age = p.issue_age + yr - 1
                rows.append((cal_year, attained_age, display_prem))

            self.premium_table.setRowCount(len(rows))
            for i, (cal_year, att_age, prem) in enumerate(rows):
                self.premium_table.setItem(i, 0, QTableWidgetItem(str(cal_year)))
                self.premium_table.setItem(i, 1, QTableWidgetItem(str(att_age)))
                self.premium_table.setItem(i, 2, QTableWidgetItem(f"${prem:,.2f}"))

            self.premium_table.autoFitAllColumns()

            t_total_elapsed = time.perf_counter() - t_total
            # Write section timings to file
            timing_path = Path.home() / ".suiteview" / "timing.log"
            timing_path.parent.mkdir(parents=True, exist_ok=True)
            with open(timing_path, "a", encoding="utf-8") as f:
                f.write(f"\n[TIMING] Policy {p.policy_number} — Section Timings:\n")
                f.write(f"  get_premium_schedule:          {t_rate:.4f}s\n")
                f.write(f"  get_annual_premium_schedule:    {t_annual:.4f}s\n")
                f.write(f"  get_base_annual_premium_schedule: {t_base:.4f}s\n")
                f.write(f"  TOTAL _populate_premium_schedule: {t_total_elapsed:.4f}s\n")
            db.dump_query_stats()

        except Exception as e:
            logger.error(f"Error building premium schedule: {e}", exc_info=True)

    def _show_premium_breakdown(self):
        """Show a dialog with per-coverage premium calculation breakdown."""
        from .premium_breakdown_dialog import show_premium_breakdown_dialog
        show_premium_breakdown_dialog(self._prem_breakdown, parent=self)

    # ── Public API ──────────────────────────────────────────────────────

    def get_policy(self) -> Optional[ABRPolicyData]:
        """Return the currently loaded policy data."""
        return self._policy

    def set_policy(self, policy: ABRPolicyData):
        """Programmatically set policy data (for testing or external load)."""
        self._policy = policy
        self._populate_details(policy)
        self._populate_rate_info()
        self._populate_riders_benefits()
        self.details_group.setVisible(True)
        self.rate_group.setVisible(True)
        self.riders_group.setVisible(True)
        self.premium_group.setVisible(True)
        self._populate_premium_schedule()
        self.policy_loaded.emit(policy)
