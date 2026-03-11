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
            ("Plan Code:", "plan_code"),
            ("Plan Description:", "plan_desc"),
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
        # "Calc Premium" is field index 20 in the fields list (0-based).
        # half = (24+1)//2 = 12, so row = 20 % 12 = 8, group = 20//12 = 1
        calc_prem_row = 8
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
            policy = self._fetch_policy(policy_num, region)
            if policy:
                policy.company = company
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
            else:
                logger.warning(f"Could not retrieve policy {policy_num} from {region}.")
        except Exception as e:
            logger.error(f"Error retrieving policy: {e}")
        finally:
            self.retrieve_btn.setEnabled(True)

    # Billing frequency (months) → ABR billing mode code
    _FREQ_TO_MODE = {12: 1, 6: 2, 3: 3, 1: 4}

    def _fetch_policy(self, policy_num: str, region: str) -> Optional[ABRPolicyData]:
        """Fetch policy data from DB2 via the shared PolicyService.

        Falls back to manual entry if DB2 is unavailable.
        """
        try:
            pi = get_policy_info(policy_num, region=region)
            if pi is None:
                logger.info(f"Policy {policy_num} not found, manual entry mode")
                self._policy_info = None
                return self._create_manual_policy(policy_num, region)

            self._policy_info = pi  # Keep reference for riders/benefits

            # Map billing frequency (months) → ABR mode code
            # Monthly has two modes: 4=Direct Bill (0.0930), 5=PAC/EFT (0.0864)
            # Non-standard modes (NSD_MD_CD) override the standard mapping.
            nsd_code = pi.non_standard_mode_code
            if nsd_code and nsd_code in NON_STANDARD_MODE_MAP:
                billing_mode = NON_STANDARD_MODE_MAP[nsd_code]
            else:
                freq = pi.billing_frequency or 12
                billing_mode = self._FREQ_TO_MODE.get(freq, 1)
                if freq == 1 and pi.is_eft:
                    billing_mode = 5  # PAC/EFT Monthly

            # Table rating numeric (from substandard ratings on base coverage)
            table_numeric = 0
            flat_extra = 0.0
            flat_to_age = 0
            flat_cease_date = None
            try:
                ratings = pi.get_substandard_ratings(1)
                for r in ratings:
                    if r.type_code == "T" and not table_numeric:
                        table_numeric = r.table_rating_numeric or 0
                    if r.type_code == "F":
                        flat_extra = float(r.flat_amount or 0)
                        flat_cease_date = r.flat_cease_date
                        if flat_cease_date and pi.issue_date and pi.base_issue_age is not None:
                            flat_to_age = pi.base_issue_age + (
                                flat_cease_date.year - pi.issue_date.year
                            )
            except Exception as e:
                logger.debug(f"Substandard lookup: {e}")

            # Translate DB2 sex code ("1"->"M", "2"->"F", "3"->"U")
            raw_sex = pi.base_sex_code or ""
            sex = {"1": "M", "2": "F", "3": "U"}.get(raw_sex, raw_sex)

            # Rate sex from 67 segment (LH_COV_INS_RNL_RT.RT_SEX_CD)
            # This is the sex code used for rate table lookups.  For unisex
            # policies the true sex may be F but the rate sex is U.
            raw_rate_sex = pi.renewal_cov_sex_code(1)  # base coverage
            rate_sex = {"1": "M", "2": "F"}.get(raw_rate_sex, raw_rate_sex)
            if not rate_sex:
                rate_sex = sex  # fallback to true sex

            # Maturity age
            maturity = pi.age_at_maturity or 95

            # Build riders list from coverages + benefits
            #
            # Each coverage has its own premium rate (from TERM tables
            # using the coverage's plancode).  Benefits on a coverage
            # add additional rates (looked up by plancode + benefit
            # type/subtype).  If a coverage has no benefits, it has no
            # extra benefit charges to look up.
            riders = []
            rider_annual = 0.0
            try:
                coverages = pi.get_coverages()
                all_benefits = pi.get_benefits()
                base_face = float(pi.base_face_amount or 0)
                today = date.today()

                def _make_benefit_rider(cov, ben, cov_sex_mapped, cov_rc_str):
                    """Create a RiderInfo for a single benefit on a coverage."""
                    pc = (cov.plancode or "").upper()
                    cov_face = float(cov.face_amount or 0)
                    cov_issue_age = int(cov.issue_age or 0)
                    cov_table = int(cov.table_rating or 0)
                    ben_type = (ben.benefit_type_cd or "").strip()
                    ben_sub = (ben.benefit_subtype_cd or "").strip()
                    ben_units = float(ben.units or 0)
                    ben_vpu = float(ben.vpu or 0)
                    ben_face = float(ben.benefit_amount or 0) or cov_face
                    ben_issue_age = int(ben.issue_age or cov_issue_age or 0)
                    fallback = 0.0
                    if ben.coi_rate is not None and ben.units:
                        fallback = float(ben.coi_rate) * float(ben.units)
                    # All benefits use BENEFIT type — rate lookup via
                    # get_benefit_rate(plancode, type, subtype, ...)
                    return RiderInfo(
                        plancode=pc,
                        face_amount=ben_face,
                        issue_age=ben_issue_age,
                        sex=cov_sex_mapped,
                        rate_class=cov_rc_str if cov_rc_str != "0" else rate_class,
                        table_rating=cov_table,
                        rider_type="BENEFIT",
                        fallback_premium=fallback,
                        benefit_type=ben_type,
                        benefit_subtype=ben_sub,
                        benefit_units=ben_units,
                        benefit_vpu=ben_vpu,
                        cease_date=ben.cease_date,
                    )

                for cov in coverages:
                    pc = (cov.plancode or "").upper()
                    cov_sex_mapped = {"1": "M", "2": "F"}.get(
                        cov.sex_code, cov.sex_code or sex
                    )
                    cov_rc = (cov.rate_class or "0").strip()
                    cov_table = int(cov.table_rating or 0)
                    cov_issue_age = int(cov.issue_age or 0)
                    cov_face = float(cov.face_amount or 0)

                    # Base coverage premium is computed by PremiumCalculator
                    # directly — no coverage-level RiderInfo needed.
                    # Non-base coverages need a RiderInfo for their own
                    # premium rate from TERM tables.
                    if not cov.is_base:
                        is_ctr = (cov.person_code == "50")
                        ann = cov.cov_annual_premium
                        if ann is None and cov.premium_rate and cov.units:
                            ann = cov.premium_rate * cov.units
                        fallback = float(ann) if ann else 0.0
                        rider_annual += fallback
                        rtype = "CTR" if is_ctr else "OTHER"
                        riders.append(RiderInfo(
                            plancode=pc,
                            face_amount=cov_face,
                            issue_age=cov_issue_age,
                            sex=cov_sex_mapped,
                            rate_class=cov_rc,
                            table_rating=cov_table,
                            rider_type=rtype,
                            fallback_premium=fallback,
                        ))

                    # Add benefit riders for this coverage
                    # Skip '#' benefits (ABR) — they have no premium charge
                    cov_benefits = [b for b in all_benefits
                                    if b.cov_pha_nbr == cov.cov_pha_nbr]
                    for ben in cov_benefits:
                        if ben.cease_date and ben.cease_date < today:
                            continue
                        ben_type = (ben.benefit_type_cd or "").strip()
                        if ben_type == "#":
                            continue
                        riders.append(
                            _make_benefit_rider(cov, ben, cov_sex_mapped, cov_rc)
                        )

            except Exception as e:
                logger.debug(f"Error building rider list: {e}")

            policy = ABRPolicyData(
                policy_number=policy_num,
                region=region,
                insured_name=pi.primary_insured_name or "",
                issue_age=int(pi.base_issue_age or 0),
                attained_age=int(pi.attained_age or 0),
                sex=sex,
                rate_sex=rate_sex,
                rate_class=pi.base_rate_class or "N",
                face_amount=float(pi.base_face_amount or 0),
                # issue_date: prefer policy-level, fall back to base coverage
                issue_date=(
                    pi.issue_date
                    or (pi.get_coverages()[0].issue_date if pi.get_coverages() else None)
                ),
                maturity_age=maturity,
                issue_state=pi.issue_state or pi.issue_state_code or "",
                plan_code=pi.base_plancode or "",
                base_plancode=str(pi.data_item("LH_COV_PHA", "PLN_BSE_SRE_CD") or "").strip(),
                billing_mode=billing_mode,
                policy_month=pi.policy_month or 1,
                policy_year=pi.policy_year or 1,
                table_rating=table_numeric,
                flat_extra=flat_extra,
                flat_to_age=flat_to_age,
                flat_cease_date=flat_cease_date,
                paid_to_date=pi.paid_to_date,
                modal_premium=float(pi.modal_premium or 0),
                annual_premium=float(pi.annual_premium or 0),
                rider_annual_premium=rider_annual,
                riders=riders,
            )
            return policy

        except Exception as e:
            logger.error(f"DB2 fetch error: {e}")
            return self._create_manual_policy(policy_num, region)

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
        labels["plan_code"].setText(p.plan_code or "—")

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
            # Apply separate modal factors: premium portion + fee portion
            annual_ex_fee = calc_annual - policy_fee
            calc_modal_ex_fee = round(annual_ex_fee * modal_factor, 2)
            calc_modal_fee = round(policy_fee * modal_fee_factor, 2)
            calc_modal = calc_modal_ex_fee + calc_modal_fee
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
                        band = calc.db.get_band(pc, cov_face)
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
                step1 = round(cov_rate * rating_factor, 2)
                step2 = step1 + cov_flat
                cov_premium = round(step2 * cov_units, 2)

                # ── Benefits on this coverage ─────────────────────
                cov_benefits = [b for b in all_bens
                                if b.cov_pha_nbr == cov.cov_pha_nbr]
                benefit_details = []
                # NOTE: For Term products, band is a coverage-level concept
                # determined by the coverage face amount — NOT the individual
                # benefit amount.  Use the same band for all benefit lookups
                # on this coverage.
                cov_band = calc.db.get_band(pc, cov_face)
                for ben in cov_benefits:
                    if ben.cease_date and ben.cease_date < date.today():
                        continue
                    ben_type = (ben.benefit_type_cd or "").strip()
                    ben_sub = (ben.benefit_subtype_cd or "").strip()
                    # Skip '#' benefits (ABR) — no premium charge
                    if ben_type == "#":
                        continue
                    ben_code = f"{ben_type}{ben_sub}"
                    ben_face = float(ben.benefit_amount or 0) or cov_face
                    ben_issue_age = int(ben.issue_age or cov_issue_age or 0)
                    ben_units = ben_face / 1000.0
                    # Look up benefit rate from TERM_POINT_BENEFIT
                    # Key: Plancode + BenefitType + Benefit + Sex + Rateclass + Band
                    ben_rate = None
                    try:
                        # TERM_POINT_BENEFIT stores BenefitType as
                        # combined type+subtype (e.g. "30") and Benefit
                        # as the name (e.g. "PWoC").
                        ben_name = BENEFIT_TYPE_CODES.get(ben_type, ben_code)
                        ben_rate = calc.db.get_benefit_rate(
                            pc, ben_code, ben_name,
                            cov_sex, cov_rc, cov_band,
                            ben_issue_age, cur_yr,
                        )
                        if ben_rate is None:
                            logger.debug(
                                f"Benefit rate lookup MISS — "
                                f"TERM_POINT_BENEFIT: Plancode={pc} "
                                f"BenefitType={ben_code} Benefit={ben_name} "
                                f"Sex={cov_sex} Rateclass={cov_rc} Band={cov_band} | "
                                f"IssueAge={ben_issue_age} Year={cur_yr}"
                            )
                    except Exception as e:
                        logger.debug(f"Error in benefit rate lookup: {e}")
                    # PW factor: benefit types 3/4 are Premium Waiver
                    is_pw = ben_type in ("3", "4")
                    pw_factor = 1.0
                    if is_pw:
                        if cov_table == 1:
                            pw_factor = 1.50
                        elif cov_table == 2:
                            pw_factor = 2.25
                    ben_premium = 0.0
                    if ben_rate is not None:
                        if is_pw:
                            ben_premium = round(round(ben_rate * pw_factor, 2) * ben_units, 2)
                        else:
                            ben_premium = round(ben_rate * ben_units, 2)
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
                    modal_prem = round(full_annual * modal_factor, 2)
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
        bd = self._prem_breakdown
        if not bd:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Premium Calculation Breakdown")
        dlg.setMinimumWidth(380)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # Title
        title = QLabel(f"Premium Breakdown - Policy Year {bd['policy_year']}")
        title.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {CRIMSON_DARK};"
            f" padding-bottom: 4px;"
        )
        layout.addWidget(title)

        # Grid for the breakdown
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(3)
        row = 0

        LBL_STYLE = f"font-size: 11px; color: {GRAY_DARK};"
        VAL_STYLE = f"font-size: 11px; color: {GRAY_DARK}; font-weight: bold;"
        HDR_STYLE = f"font-size: 11px; color: {CRIMSON_DARK}; font-weight: bold;"
        INDENT_STYLE = f"font-size: 11px; color: {GRAY_DARK}; padding-left: 16px;"
        PREM_STYLE = f"font-size: 12px; color: {CRIMSON_DARK}; font-weight: bold;"

        def add_header(text):
            nonlocal row
            lbl = QLabel(text)
            lbl.setStyleSheet(HDR_STYLE + " padding-top: 8px;")
            grid.addWidget(lbl, row, 0, 1, 2)
            row += 1

        def add_line(label_text, value_text, indent=False):
            nonlocal row
            lbl = QLabel(label_text)
            lbl.setStyleSheet(INDENT_STYLE if indent else LBL_STYLE)
            grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignLeft)
            val = QLabel(str(value_text))
            val.setStyleSheet(VAL_STYLE)
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(val, row, 1)
            row += 1

        def add_premium_line(label_text, value_text, indent=False):
            nonlocal row
            lbl = QLabel(label_text)
            lbl.setStyleSheet(INDENT_STYLE if indent else LBL_STYLE)
            grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignLeft)
            val = QLabel(str(value_text))
            val.setStyleSheet(PREM_STYLE)
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(val, row, 1)
            row += 1

        def add_spacer():
            nonlocal row
            spacer = QLabel("")
            spacer.setFixedHeight(6)
            grid.addWidget(spacer, row, 0)
            row += 1

        def add_divider():
            nonlocal row
            div = QFrame()
            div.setFrameShape(QFrame.Shape.HLine)
            div.setStyleSheet(f"color: {CRIMSON_SUBTLE};")
            grid.addWidget(div, row, 0, 1, 2)
            row += 1

        # ── Policy number ─────────────────────────────────────
        add_line("Policy Number", bd.get('policy_number', ''))

        # ── Per-coverage breakdown ────────────────────────────
        for cov_idx, cov in enumerate(bd.get('coverages', [])):
            add_spacer()
            add_header(f"Coverage {cov_idx + 1}")
            add_line("Plan", cov['plancode'], indent=True)
            add_line("Issue age/Sex/Class",
                     f"{cov['issue_age']} / {cov['sex']} / {cov['rate_class']}",
                     indent=True)
            cov_rate = cov.get('rate', 0)
            add_line("Rate",
                     f"{cov_rate:.4f}" if cov_rate else "0", indent=True)
            add_line("Table Rating", str(cov['table_rating']), indent=True)
            add_line("Rating Factor",
                     f"{cov['rating_factor']:.3f}", indent=True)
            flat = cov.get('flat_extra', 0)
            add_line("Flat Extra",
                     f"{flat:.2f}" if flat > 0 else "0", indent=True)
            add_line("Units", f"{cov['units']:.3f}", indent=True)

            # Benefits on this coverage (PW, etc.)
            for ben in cov.get('benefits', []):
                add_spacer()
                lbl = ben.get('label', 'BEN')
                ben_rate = ben.get('rate')
                add_line(f"{lbl} Rate",
                         f"{ben_rate:.4f}" if ben_rate is not None else "—",
                         indent=True)
                ben_factor = ben.get('factor', 1.0)
                add_line(f"{lbl} Factor",
                         f"{ben_factor:.2f}" if ben_factor != 1.0 else "1",
                         indent=True)

            add_spacer()
            add_premium_line("Premium",
                             f"{cov['premium']:,.4f}", indent=True)

        # ── Policy Fee / Premium Mode / Modal / Calculated ────
        add_spacer()
        add_divider()
        add_line("Policy Fee", f"{bd['policy_fee']:,.3f}")
        add_line("Premium Mode", bd.get('modal_label', ''))
        add_line("Modal Factor", f"{bd['modal_factor']:.4f}")
        add_premium_line("Calculated Modal Premium",
                         f"{bd['calc_modal']:,.2f}")

        layout.addLayout(grid)
        layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(BUTTON_PRIMARY_STYLE)
        close_btn.clicked.connect(dlg.accept)
        btn_row_layout = QHBoxLayout()
        btn_row_layout.addStretch()
        btn_row_layout.addWidget(close_btn)
        layout.addLayout(btn_row_layout)

        dlg.exec()

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
