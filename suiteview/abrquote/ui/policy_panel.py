"""
ABR Quote — Policy Information Panel (Step 1).

Displays policy lookup bar and policy details retrieved from DB2.
Shows ABR interest rate and per diem limits.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtGui import QCursor
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton,
    QGroupBox, QFrame, QDialog,
    QTableWidgetItem, QDateEdit, QSizePolicy,
    QApplication, QMessageBox,
)

from ..models.abr_data import ABRPolicyData
from ..models.abr_database import get_abr_database
from ..models.abr_constants import (
    MODAL_LABELS, PLAN_CODE_INFO,
)
from suiteview.ui.widgets.uppercase_input import force_uppercase

from suiteview.polview.models.cl_polrec.policy_translations import COMPANY_CODES
from ...core.reinsurance import fetch_reinsurer_list
from ..core.abr_policy_service import build_abr_policy, find_policy_companies
from ...polview.ui.widgets import StyledInfoTableGroup
from .abr_styles import (
    CRIMSON_DARK, CRIMSON_PRIMARY, CRIMSON_SUBTLE, CRIMSON_RICH, WHITE, GRAY_DARK, GROUP_BOX_STYLE, INPUT_STYLE, DATEEDIT_STYLE,
    BUTTON_PRIMARY_STYLE, LABEL_HEADER_STYLE, PREMIUM_TABLE_STYLE, PREMIUM_INNER_TABLE_STYLE, PREMIUM_INNER_FRAME_STYLE,
)

logger = logging.getLogger(__name__)


class CalendarOnlyDateEdit(QDateEdit):
    """QDateEdit that disables scroll-wheel and keyboard step-up/down.
    The only way to change the date is through the calendar popup.
    """

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()

    def stepBy(self, steps: int) -> None:
        pass  # disable all step/increment behaviour


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

        main_hbox = QHBoxLayout()
        main_hbox.setSpacing(12)
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        self._build_lookup_group(left_col)
        self._build_policy_details_group(left_col)
        self._build_ul_inputs(left_col)
        self._build_coverages_group(left_col)
        self._build_rate_group(left_col)
        self._build_premium_warning(left_col)
        self._build_premium_schedule_column(main_hbox, left_col)
        layout.addLayout(main_hbox, 1)

    def _build_lookup_group(self, left_col):
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
        force_uppercase(self.policy_input)
        lookup_grid.addWidget(self.policy_input, 0, 1)

        # Row 0, Col 2-3: Quote Date
        lbl_qd = QLabel("Quote Date:")
        lbl_qd.setStyleSheet(LABEL_HEADER_STYLE)
        lookup_grid.addWidget(lbl_qd, 0, 2)

        self.quote_date_edit = CalendarOnlyDateEdit()
        self.quote_date_edit.setCalendarPopup(True)
        self.quote_date_edit.setDate(QDate.currentDate())
        self.quote_date_edit.setDisplayFormat("M/d/yyyy")
        self.quote_date_edit.setFixedWidth(120)
        self.quote_date_edit.setStyleSheet(DATEEDIT_STYLE)
        self.quote_date_edit.dateChanged.connect(self._on_quote_date_changed)
        lookup_grid.addWidget(self.quote_date_edit, 0, 3)

        # Row 1, Col 3: Get button
        self.retrieve_btn = QPushButton("Get")
        self.retrieve_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
        self.retrieve_btn.setFixedWidth(120)
        self.retrieve_btn.clicked.connect(self._on_retrieve)
        lookup_grid.addWidget(self.retrieve_btn, 1, 3)

        # Row 1, Col 0-2: Company chooser (hidden until multi-company detected)
        self._company_chooser_frame = QFrame()
        self._company_chooser_frame.setVisible(False)
        chooser_layout = QHBoxLayout(self._company_chooser_frame)
        chooser_layout.setContentsMargins(0, 0, 0, 0)
        chooser_layout.setSpacing(6)
        chooser_lbl = QLabel("Select Company:")
        chooser_lbl.setStyleSheet(
            f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;"
        )
        chooser_layout.addWidget(chooser_lbl)
        self._company_btn_layout = QHBoxLayout()
        self._company_btn_layout.setSpacing(4)
        chooser_layout.addLayout(self._company_btn_layout)
        chooser_layout.addStretch()
        lookup_grid.addWidget(self._company_chooser_frame, 1, 0, 1, 3)

        # Don't let the grid stretch — keep controls tight to the left
        lookup_grid.setColumnStretch(4, 1)

        left_col.addWidget(lookup_group)


    def _build_policy_details_group(self, left_col):
        # ── Policy details grid ─────────────────────────────────────────
        self.details_group = QGroupBox("Policy Details")
        self.details_group.setStyleSheet(GROUP_BOX_STYLE)
        details_grid = QGridLayout(self.details_group)
        details_grid.setContentsMargins(12, 20, 12, 8)
        details_grid.setHorizontalSpacing(4)
        details_grid.setVerticalSpacing(6)

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
            ("Total Death Benefit:", "face_amount"),
            ("DB Option:", "db_option"),
            ("Account Value:", "account_value"),
            ("Premiums Paid:", "premiums_paid"),
            ("Issue State:", "issue_state"),
            ("Maturity Date:", "maturity_date"),
            ("Issue Date:", "issue_date"),
            ("Valuation Date:", "valuation_date"),
            ("Policy Year:", "policy_year"),
            ("Month of Year:", "policy_month"),
            ("Maturity Duration:", "maturity_duration"),
            ("Base Plancode:", "base_plancode"),
            ("Billing Mode:", "billing_mode"),
            ("Modal Premium:", "modal_premium"),
            ("Calc Premium:", "calc_premium"),
            ("Table Rating:", "table_rating"),
            ("Annual Flat Extra:", "flat_extra"),
            ("Flat Cease Date:", "flat_cease_date"),
            ("Reinsurers:", "reinsurers"),
        ]

        # Layout as 2 groups of key-value pairs with a gutter between.
        # Grid columns: 0=label1, 1=value1, 2=gutter, 3=label2, 4=value2
        half = (len(fields) + 1) // 2  # rows per column
        self._detail_field_labels = {}  # key -> QLabel (the header label, for show/hide)
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
            self._detail_field_labels[key] = lbl

        # UL-only fields — hidden by default (shown in _populate_details for UL/IUL)
        self._ul_detail_keys = ("db_option", "account_value", "premiums_paid")
        for k in self._ul_detail_keys:
            self._detail_labels[k].setVisible(False)
            self._detail_field_labels[k].setVisible(False)

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
        # "Calc Premium" is field index 20 in the fields list (0-based).
        # half = (25+1)//2 = 13, so row = 20 % 13 = 7, group = 20//13 = 1
        calc_prem_row = 7
        details_grid.addWidget(self._calc_detail_btn, calc_prem_row, 5)

        self.details_group.setVisible(False)
        left_col.addWidget(self.details_group)


    def _build_ul_inputs(self, left_col):
        # ── UL / Advanced Product Inputs ────────────────────────────────
        self.ul_input_frame = QFrame()
        ul_grid = QGridLayout(self.ul_input_frame)
        ul_grid.setContentsMargins(12, 8, 12, 8)
        ul_grid.setHorizontalSpacing(8)
        ul_grid.setVerticalSpacing(6)

        lbl_level_prem = QLabel("Annual Level Prem:")
        lbl_level_prem.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        ul_grid.addWidget(lbl_level_prem, 0, 0)
        self.ul_level_prem_input = QLineEdit()
        self.ul_level_prem_input.setPlaceholderText("0.00")
        self.ul_level_prem_input.setStyleSheet(INPUT_STYLE)
        self.ul_level_prem_input.setFixedWidth(120)
        self.ul_level_prem_input.editingFinished.connect(self._on_ul_level_prem_changed)
        ul_grid.addWidget(self.ul_level_prem_input, 0, 1)

        lbl_loan_payoff = QLabel("Loan Payoff:")
        lbl_loan_payoff.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        ul_grid.addWidget(lbl_loan_payoff, 0, 2)
        self.ul_loan_payoff_input = QLineEdit()
        self.ul_loan_payoff_input.setPlaceholderText("0.00")
        self.ul_loan_payoff_input.setStyleSheet(INPUT_STYLE)
        self.ul_loan_payoff_input.setFixedWidth(120)
        ul_grid.addWidget(self.ul_loan_payoff_input, 0, 3)

        lbl_surrender_value = QLabel("Surrender Value:")
        lbl_surrender_value.setStyleSheet(f"font-weight: bold; color: {CRIMSON_DARK}; font-size: 11px;")
        ul_grid.addWidget(lbl_surrender_value, 0, 4)
        self.ul_surrender_value_input = QLineEdit()
        self.ul_surrender_value_input.setPlaceholderText("0.00")
        self.ul_surrender_value_input.setStyleSheet(INPUT_STYLE)
        self.ul_surrender_value_input.setFixedWidth(120)
        ul_grid.addWidget(self.ul_surrender_value_input, 0, 5)

        ul_grid.setColumnStretch(6, 1)
        self.ul_input_frame.setVisible(False)
        left_col.addWidget(self.ul_input_frame)


    def _build_coverages_group(self, left_col):
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


    def _build_rate_group(self, left_col):
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


    def _build_premium_warning(self, left_col):
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


    def _build_premium_schedule_column(self, main_hbox, left_col):
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


    # ── Actions ─────────────────────────────────────────────────────────

    def _on_retrieve(self, company_code=None):
        """Retrieve policy data from DB2.

        If *company_code* is None, the service will auto-detect the
        company.  When multiple companies are found, company chooser
        buttons are shown and retrieval is deferred until the user picks one.
        """
        # QPushButton.clicked emits a bool; treat that as "no company"
        if isinstance(company_code, bool):
            company_code = None
        policy_num = self.policy_input.text().strip().upper()
        if not policy_num:
            return

        region = "CKPR"  # Always CKPR
        self._hide_company_chooser()
        self.retrieve_btn.setEnabled(False)
        self.retrieve_btn.setText("Loading...")
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        QApplication.processEvents()

        try:
            if company_code is None:
                # Detect which companies hold this policy
                companies = find_policy_companies(policy_num, region)
                if not companies:
                    logger.warning(f"Policy {policy_num} not found in {region}.")
                    QMessageBox.warning(
                        self,
                        "Policy Lookup",
                        f"Policy {policy_num} was not found in {region}.",
                    )
                    return
                if len(companies) > 1:
                    self._show_company_chooser(companies)
                    return
                company_code = companies[0]

            company_display = f"{company_code} - {COMPANY_CODES.get(company_code, company_code)}"

            quote_dt = self.get_quote_date()
            policy, policy_info = build_abr_policy(
                policy_num,
                region,
                company_code=company_code,
                as_of_date=quote_dt,
            )
            if policy:
                policy.company = company_display
                # Fetch reinsurer list from TAICession
                policy.reinsurers = fetch_reinsurer_list(
                    policy_num, company_code, quote_dt
                )
                self._policy = policy
                self._policy_info = policy_info
                self._populate_details(policy)
                self._populate_rate_info()
                self._populate_riders_benefits()
                self.details_group.setVisible(True)
                self.rate_group.setVisible(True)
                self.riders_group.setVisible(True)
                self.premium_group.setVisible(True)

                # For UL/IUL/ISWL: leave Future Premiums blank (user enters level prem)
                is_ul = policy.product_type in ("UL", "IUL", "ISWL")
                if is_ul:
                    self.premium_table.setRowCount(0)
                    self._detail_labels["calc_premium"].setText("N/A")
                    self.ul_level_prem_input.clear()
                    self.ul_loan_payoff_input.clear()
                    self.ul_surrender_value_input.clear()
                else:
                    self._populate_premium_schedule()
                self.policy_loaded.emit(policy)
            else:
                logger.warning(f"Could not retrieve policy {policy_num} from {region}.")
                QMessageBox.warning(
                    self,
                    "Policy Lookup",
                    f"Could not retrieve policy {policy_num} from {region}.",
                )
        except Exception as e:
            logger.error("Error retrieving policy", exc_info=True)
            QMessageBox.critical(
                self,
                "Policy Lookup Failed",
                f"Could not retrieve policy {policy_num}:\n{e}",
            )
        finally:
            QApplication.restoreOverrideCursor()
            self.retrieve_btn.setText("Get")
            self.retrieve_btn.setEnabled(True)

    def _show_company_chooser(self, companies: list[str]):
        """Display company buttons for multi-company policies."""
        # Clear any existing buttons
        while self._company_btn_layout.count():
            item = self._company_btn_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for co_code in companies:
            name = COMPANY_CODES.get(co_code, co_code)
            btn = QPushButton(f"{co_code} - {name}")
            btn.setFixedHeight(24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ font-size: 11px; font-weight: bold;"
                f" color: {WHITE}; border: 1px solid {CRIMSON_DARK};"
                f" border-radius: 3px; padding: 2px 10px;"
                f" background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                f"     stop:0 {CRIMSON_RICH}, stop:1 {CRIMSON_PRIMARY}); }}"
                f"QPushButton:hover {{ background: {CRIMSON_DARK}; }}"
            )
            btn.clicked.connect(lambda checked, cc=co_code: self._on_retrieve(cc))
            self._company_btn_layout.addWidget(btn)

        self._company_chooser_frame.setVisible(True)

    def _hide_company_chooser(self):
        """Hide the company chooser row."""
        self._company_chooser_frame.setVisible(False)

    def _create_manual_policy(self, policy_num: str, region: str) -> ABRPolicyData:
        """Create a stub policy for manual data entry (when DB2 is unavailable)."""
        return ABRPolicyData(
            policy_number=policy_num,
            region=region,
        )

    def _populate_details(self, p: ABRPolicyData):
        """Fill in the detail labels from policy data."""
        self._reset_calc_premium_display()
        self._populate_identity_details(p)
        self._populate_ul_details(p)
        self._populate_duration_and_rating_details(p)
        self._populate_value_and_maturity_details(p)
        self._populate_ul_inputs(p)

    def _reset_calc_premium_display(self) -> None:
        labels = self._detail_labels
        labels["calc_premium"].setText("—")
        labels["calc_premium"].setStyleSheet(f"color: {GRAY_DARK}; font-size: 11px;")
        self._calc_detail_btn.setVisible(False)
        self._prem_breakdown = None

    def _populate_identity_details(self, p: ABRPolicyData) -> None:
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
        death_benefit = p.default_death_benefit
        labels["face_amount"].setText(f"${death_benefit:,.2f}" if death_benefit else "—")

    def _populate_ul_details(self, p: ABRPolicyData) -> None:
        labels = self._detail_labels
        is_ul = p.product_type in ("UL", "IUL", "ISWL")
        db_opt_display = {
            "1": "A (Level)", "2": "B (Increasing)", "3": "C (ROP)"
        }.get(p.db_option, p.db_option or "—")
        labels["db_option"].setText(db_opt_display)
        labels["account_value"].setText(
            f"${p.account_value:,.2f}" if p.account_value else "—"
        )
        labels["premiums_paid"].setText(
            f"${p.premiums_paid_to_date:,.2f}" if p.premiums_paid_to_date else "—"
        )
        for k in self._ul_detail_keys:
            self._detail_labels[k].setVisible(is_ul)
            self._detail_field_labels[k].setVisible(is_ul)

    def _populate_duration_and_rating_details(self, p: ABRPolicyData) -> None:
        labels = self._detail_labels
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

    def _populate_value_and_maturity_details(self, p: ABRPolicyData) -> None:
        labels = self._detail_labels
        is_ul = p.product_type in ("UL", "IUL", "ISWL")
        if is_ul and p.valuation_date:
            labels["valuation_date"].setText(
                f"{p.valuation_date.month}/{p.valuation_date.day}/{p.valuation_date.year}  (last monthliversary)"
            )
        elif p.valuation_date:
            labels["valuation_date"].setText(
                f"{p.valuation_date.month}/{p.valuation_date.day}/{p.valuation_date.year}"
            )
        else:
            today = self.get_quote_date()
            labels["valuation_date"].setText(
                f"{today.month}/{today.day}/{today.year}  (quote date)"
            )
        labels["valuation_date"].setStyleSheet(
            f"color: {CRIMSON_DARK}; font-size: 11px; font-style: italic;"
        )

        # Reinsurers (from TAICession lookup)
        labels["reinsurers"].setText(p.reinsurers or "(none)")

        # Maturity date and duration
        if p.maturity_date:
            labels["maturity_date"].setText(
                f"{p.maturity_date.month}/{p.maturity_date.day}/{p.maturity_date.year}"
            )
        else:
            labels["maturity_date"].setText("—")
        mat_dur = p.maturity_age - p.issue_age if p.maturity_age and p.issue_age else 0
        labels["maturity_duration"].setText(str(mat_dur) if mat_dur > 0 else "—")

    def _populate_ul_inputs(self, p: ABRPolicyData) -> None:
        is_ul = p.product_type in ("UL", "IUL", "ISWL")
        self.ul_input_frame.setVisible(is_ul)
        if is_ul:
            self.ul_surrender_value_input.setText(
                f"{p.surrender_value:,.2f}" if p.surrender_value else ""
            )
        else:
            self.ul_level_prem_input.clear()
            self.ul_loan_payoff_input.clear()
            self.ul_surrender_value_input.clear()

    def get_quote_date(self) -> date:
        """Return the currently selected quote date."""
        qd = self.quote_date_edit.date()
        return date(qd.year(), qd.month(), qd.day())

    def _on_quote_date_changed(self, qdate: QDate):
        """User changed the quote date — refresh rate info and premiums."""
        if self._policy:
            self._populate_rate_info()
            is_ul = self._policy.product_type in ("UL", "IUL", "ISWL")
            if is_ul:
                self._populate_ul_premium_schedule()
            else:
                self._populate_premium_schedule()
            self.quote_date_changed.emit(self.get_quote_date())

    def _on_ul_level_prem_changed(self):
        """User updated the Annual Level Premium — rebuild UL future premiums."""
        if self._policy and self._policy.product_type in ("UL", "IUL", "ISWL"):
            self._populate_ul_premium_schedule()

    def _populate_ul_premium_schedule(self):
        """Build future premium schedule for UL/IUL/ISWL from user-entered level premium.

        Logic:
        - Start year = policy year as of the next monthiversary from Quote Date.
        - If start year == current duration, premium for that year = 0
          (no more payments in the current year).
        - For all subsequent years up to maturity duration, premium = level prem entered.
        """
        p = self._policy
        if not p:
            return

        # Parse the user-entered level premium
        text = self.ul_level_prem_input.text().strip().replace(",", "").replace("$", "")
        try:
            level_prem = float(text) if text else 0.0
        except ValueError:
            level_prem = 0.0

        if level_prem <= 0:
            self.premium_table.setRowCount(0)
            return

        qd = self.get_quote_date()
        max_duration = p.maturity_age - p.issue_age if p.maturity_age and p.issue_age else 0
        if max_duration <= 0 or not p.issue_date:
            self.premium_table.setRowCount(0)
            return

        # Compute current duration (policy year at quote date)
        anniv_month = p.issue_date.month
        anniv_day = p.issue_date.day
        ysi = qd.year - p.issue_date.year
        if (qd.month, qd.day) < (anniv_month, anniv_day):
            ysi -= 1
        current_duration = max(ysi + 1, 1)

        # Next monthiversary: advance to the next month with the issue day
        next_month = qd.month + 1
        next_year = qd.year
        if next_month > 12:
            next_month = 1
            next_year += 1

        # Policy year at that next monthiversary
        ysi_next = next_year - p.issue_date.year
        if (next_month, anniv_day) < (anniv_month, anniv_day):
            ysi_next -= 1
        start_duration = max(ysi_next + 1, 1)

        rows = []
        for dur in range(start_duration, max_duration + 1):
            cal_year = p.issue_date.year + dur - 1
            # Adjust calendar year to align with anniversary
            if anniv_month > 1 or anniv_day > 1:
                cal_year = p.issue_date.year + dur - 1
            att_age = p.issue_age + dur - 1

            if dur == current_duration:
                # Current year: no more payments
                prem = 0.0
            else:
                prem = level_prem

            rows.append((dur, att_age, prem))

        self.premium_table.setRowCount(len(rows))
        for i, (yr, att_age, prem) in enumerate(rows):
            self.premium_table.setItem(i, 0, QTableWidgetItem(str(yr)))
            self.premium_table.setItem(i, 1, QTableWidgetItem(str(att_age)))
            self.premium_table.setItem(i, 2, QTableWidgetItem(f"${prem:,.2f}"))
        self.premium_table.autoFitAllColumns()

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
            coverages = pi.coverages.get_coverages()
            for cov in coverages:
                form = cov.form_number or cov.plancode
                items.append((form, {"type": "coverage", "cov": cov}))
        except Exception as e:
            logger.debug(f"Error loading coverages: {e}")

        # Benefits
        try:
            benefits = pi.benefits.get_benefits()
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

        rows = (
            self._coverage_detail_rows(detail_data["cov"])
            if detail_data["type"] == "coverage"
            else self._benefit_detail_rows(detail_data["bnf"])
        )
        for row, (label, value) in enumerate(rows):
            add_row(row, label, value)

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

    def _coverage_detail_rows(self, cov) -> list[tuple[str, object]]:
        cease = cov.nxt_chg_dt or cov.maturity_date
        rating = (
            f"{cov.table_rating_code} ({(cov.table_rating or 0) * 25}%)"
            if cov.table_rating_code else "Standard"
        )
        return [
            ("Plancode:", cov.plancode),
            ("Phase:", cov.cov_pha_nbr),
            ("Person Code:", f"{cov.person_code} - {cov.person_desc}" if cov.person_desc else cov.person_code),
            ("Person Sequence:", cov.prs_seq_nbr),
            ("Issue Date:", cov.issue_date.strftime("%m/%d/%Y") if cov.issue_date else ""),
            ("Cease Date:", cease.strftime("%m/%d/%Y") if cease else ""),
            ("Cov Status Code:", cov.nxt_chg_typ_cd or ""),
            ("Lives Covered:", cov.lives_cov_cd or ""),
            ("Units:", f"{cov.units:,.2f}" if cov.units else ""),
            ("VPU:", f"{cov.vpu:,.3f}" if cov.vpu else ""),
            ("Issue Age:", cov.issue_age),
            ("Sex:", cov.sex_desc or cov.sex_code),
            ("Rate Class:", f"{cov.rate_class} - {cov.rate_class_desc}" if cov.rate_class_desc else cov.rate_class),
            ("Rating:", rating),
        ]

    def _benefit_detail_rows(self, bnf) -> list[tuple[str, object]]:
        rating = bnf.rating_factor
        try:
            rating_str = f"{float(rating):.0%}" if rating else ""
        except Exception:
            rating_str = ""
        return [
            ("Benefit Code:", bnf.benefit_code),
            ("Phase:", bnf.cov_pha_nbr),
            ("Type:", bnf.benefit_type_cd),
            ("Description:", bnf.benefit_desc),
            ("Form:", bnf.form_number),
            ("Issue Date:", bnf.issue_date.strftime("%m/%d/%Y") if bnf.issue_date else ""),
            ("Cease Date:", bnf.cease_date.strftime("%m/%d/%Y") if bnf.cease_date else ""),
            ("Orig Cease:", bnf.orig_cease_date.strftime("%m/%d/%Y") if bnf.orig_cease_date else ""),
            ("Units:", f"{bnf.units:,.2f}" if bnf.units else ""),
            ("VPU:", f"{bnf.vpu:,.3f}" if bnf.vpu else ""),
            ("Amount:", f"${bnf.benefit_amount:,.2f}" if bnf.benefit_amount else ""),
            ("Issue Age:", bnf.issue_age if bnf.issue_age else ""),
            ("Rating:", rating_str),
            ("Renewal:", bnf.renewal_indicator),
            ("COI Rate:", bnf.coi_rate if bnf.coi_rate else ""),
        ]

    def _populate_premium_schedule(self):
        """Render the core PremiumScheduleResult for the loaded policy."""
        p = self._policy
        if not p or not p.plan_code:
            return

        try:
            from ..core.abr_policy_service import premium_schedule_for_quote
            from ..core.premium_calc import PremiumCalculator

            db = get_abr_database()
            db.reset_query_stats()
            schedule = premium_schedule_for_quote(p, self.get_quote_date())
            if not schedule.premium_schedule:
                self._detail_labels["calc_premium"].setText("(none)")
                return

            calc_modal = schedule.current_modal_premium
            cyberlife_modal = p.modal_premium
            self._detail_labels["calc_premium"].setText(f"${calc_modal:,.2f}")
            self._calc_detail_btn.setVisible(True)
            self._prem_breakdown = PremiumCalculator(p).build_coverage_breakdown(
                policy_year=schedule.start_year,
                prem_result=schedule.premium_result,
                modal_factor=schedule.modal_factor,
            )
            self._render_premium_warning(calc_modal, cyberlife_modal)
            self._render_premium_schedule_rows(schedule)
            db.dump_query_stats()
        except Exception as e:
            logger.error(f"Error building premium schedule: {e}", exc_info=True)
            self._detail_labels["calc_premium"].setText("(none)")

    def _render_premium_warning(self, calc_modal: float, cyberlife_modal: float) -> None:
        """Display the calculated-vs-CyberLife modal premium warning."""
        if cyberlife_modal > 0 and abs(calc_modal - cyberlife_modal) > 0.02:
            diff = calc_modal - cyberlife_modal
            self.premium_warning.setText(
                f"⚠ Premium mismatch: Calculated ${calc_modal:,.2f} "
                f"vs CyberLife ${cyberlife_modal:,.2f} "
                f"(diff ${diff:+,.2f})"
            )
            self.premium_warning.setVisible(True)
            self._detail_labels["calc_premium"].setStyleSheet(
                "color: #CC0000; font-size: 11px; font-weight: bold;"
            )
            logger.warning(
                f"Modal premium mismatch: calculated=${calc_modal:.2f} "
                f"vs CyberLife=${cyberlife_modal:.2f} "
                f"(diff=${diff:+.2f})"
            )
            return
        self.premium_warning.setVisible(False)
        self._detail_labels["calc_premium"].setStyleSheet(
            f"color: {GRAY_DARK}; font-size: 11px;"
        )

    def _render_premium_schedule_rows(self, schedule) -> None:
        """Populate the premium schedule table from a PremiumScheduleResult."""
        p = self._policy
        if not p:
            return
        quote_date = self.get_quote_date()
        current_calendar = quote_date.year
        max_duration = p.maturity_age - p.issue_age
        rows = []
        for year in range(schedule.start_year, max_duration + 1):
            index = year - 1
            if index >= len(schedule.premium_schedule):
                break
            calendar_year = current_calendar + (year - schedule.start_year)
            attained_age = p.issue_age + year - 1
            rows.append((calendar_year, attained_age, schedule.premium_schedule[index]))
        self.premium_table.setRowCount(len(rows))
        for row_index, (calendar_year, attained_age, premium) in enumerate(rows):
            self.premium_table.setItem(row_index, 0, QTableWidgetItem(str(calendar_year)))
            self.premium_table.setItem(row_index, 1, QTableWidgetItem(str(attained_age)))
            self.premium_table.setItem(row_index, 2, QTableWidgetItem(f"${premium:,.2f}"))
        self.premium_table.autoFitAllColumns()

    def _show_premium_breakdown(self):
        """Show a dialog with per-coverage premium calculation breakdown."""
        from .premium_breakdown_dialog import show_premium_breakdown_dialog
        show_premium_breakdown_dialog(self._prem_breakdown, parent=self)

    # ── Public API ──────────────────────────────────────────────────────

    def load_policy(self, policy_number: str):
        """Load *policy_number* through the same path the Retrieve button uses.

        Public entry point reused by the taskbar policy launcher. Region is
        always CKPR and the company is auto-detected, mirroring a user typing
        the policy and pressing Enter.
        """
        policy_number = (policy_number or "").strip()
        if not policy_number:
            return
        self.policy_input.setText(policy_number)
        self._on_retrieve()

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
        is_ul = policy.product_type in ("UL", "IUL", "ISWL")
        if is_ul:
            self.premium_table.setRowCount(0)
            self._detail_labels["calc_premium"].setText("N/A")
        else:
            self._populate_premium_schedule()
        self.policy_loaded.emit(policy)
