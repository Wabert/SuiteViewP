"""
Coverages tab – Policy Info header, Coverages table, and Benefits table.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidgetItem,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from ..formatting import format_date, format_amount
from ..styles import WHITE, GRAY_DARK, GRAY_TEXT, GOLD_DARK
from ..widgets import StyledInfoTableGroup
from ...models.cl_polrec.policy_translations import translate_benefit_type

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation

logger = logging.getLogger(__name__)


# LH_COV_PHA.NXT_CHG_TYP_CD, shown as words (the code is in the cell tooltip).
_COVERAGE_STATUS_TEXT = {"0": "Terminated", "1": "Paid Up", "2": "Prem Paying"}


_VAL_STYLE = f"font-size: 11px; color: {GRAY_DARK}; background: transparent; border: none;"
_VAL_STYLE_CORRIDOR = (
    f"font-size: 11px; color: {GOLD_DARK}; font-weight: bold; "
    "background: transparent; border: none;"
)
_VAL_STYLE_NA = (
    f"font-size: 11px; color: {GRAY_TEXT}; font-style: italic; "
    "background: transparent; border: none;"
)


class CoveragesTab(QWidget):
    """Tab for Coverages view - matches VBA PopulateCoverges layout."""

    annuity_rider_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cov_data = []
        self._bnf_data = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.setStyleSheet(f"background-color: {WHITE};")

        # Policy Info Header — 4 columns
        self.info_group = StyledInfoTableGroup("Policy Info", columns=4, show_table=False)
        self.info_group.setMaximumWidth(1040)
        self.info_group.setMaximumHeight(180)

        # Column layout requested by business users, defined row-wise for the grid.
        self.info_group.add_field("Policy", "policy_label", 80, 80)
        self.info_group.add_field("Suspense Code", "suspense_label", 80, 80)
        self.info_group.add_field("Valuation Date", "eff_date_label", 80, 100)
        self.info_group.add_field("Billing Mode", "billing_mode_label", 80, 80)

        self.info_group.add_field("Company", "company_label", 80, 80)
        self.info_group.add_field("Grace Indicator", "grace_label", 90, 80)
        self.info_group.add_field("Policy Year", "policy_year_label", 80, 100)
        self.info_group.add_field("Billable Premium", "premium_label", 100, 80)

        self.info_group.add_field("Market Org", "market_org_label", 80, 80)
        self.info_group.add_field("Single/Joint", "joint_label", 80, 120)
        self.info_group.add_field("Attained Age", "att_age_label", 80, 100)
        self.info_group.add_field("Corridor", "corridor_label", 80, 80)

        self.info_group.add_field("Status", "status_label", 80, 100)
        self.info_group.add_field("Issue State", "issue_state_label", 80, 80)
        self.info_group.add_field("Total Death Benefit", "total_death_benefit_label", 110, 100)
        self.info_group.add_field("System Cd", "system_cd_label", 80, 80)

        self.info_group.add_field("Reins Partner", "reins_partner_label", 80, 80)
        self.info_group.add_field("Definition of Life", "definition_of_life_label", 110, 80)
        self.info_group.add_field("DB Option", "db_option_label", 80, 80)
        self.info_group.add_field("Region", "region_label", 80, 80)
        self.info_group.set_field_sources({
            "suspense_label": "LH_BAS_POL.SUS_CD",
            "billing_mode_label": "LH_BAS_POL.PMT_FQY_PER + NSD_MD_CD",
            "grace_label": "LH_NON_TRD_POL / LH_TRD_POL.IN_GRA_PER_IND",
            "premium_label": "LH_BAS_POL.POL_PRM_AMT",
            "market_org_label": "LH_BAS_POL.SVC_AGC_NBR (first character)",
            "joint_label": "LH_COV_PHA.NBR_OF_LIVES_CD (base phase 1)",
            "status_label": "LH_BAS_POL.PRM_PAY_STA_REA_CD",
            "reins_partner_label": "TH_USER_GENERIC.FUZGREIN_IND",
            "db_option_label": "LH_NON_TRD_POL.DTH_BNF_PLN_OPT_CD",
            "system_cd_label": "LH_BAS_POL.CK_SYS_CD",
        })

        # Backward-compat aliases
        self.policy_label = self.info_group.policy_label
        self.company_label = self.info_group.company_label
        self.market_org_label = self.info_group.market_org_label
        self.issue_state_label = self.info_group.issue_state_label
        self.definition_of_life_label = self.info_group.definition_of_life_label
        self.billing_mode_label = self.info_group.billing_mode_label
        self.premium_label = self.info_group.premium_label
        self.region_label = self.info_group.region_label
        self.system_cd_label = self.info_group.system_cd_label
        self.joint_label = self.info_group.joint_label
        self.suspense_label = self.info_group.suspense_label
        self.grace_label = self.info_group.grace_label
        self.eff_date_label = self.info_group.eff_date_label
        self.total_death_benefit_label = self.info_group.total_death_benefit_label
        self.corridor_label = self.info_group.corridor_label
        self.policy_year_label = self.info_group.policy_year_label
        self.att_age_label = self.info_group.att_age_label
        self.status_label = self.info_group.status_label
        self.reins_partner_label = self.info_group.reins_partner_label
        self.db_option_label = self.info_group.db_option_label

        layout.addWidget(self.info_group)

        # Coverages table
        self.cov_group = StyledInfoTableGroup("Coverages", show_info=False)
        self.cov_table = self.cov_group.table
        self.cov_table._data_table.itemDoubleClicked.connect(self._on_coverage_double_clicked)
        self.cov_table.set_empty_message("No coverages on this policy.")
        self.cov_table.set_column_settings_key("polview.coverages")
        layout.addWidget(self.cov_group, 2)

        # Benefits table
        self.bnf_group = StyledInfoTableGroup("Benefits", show_info=False)
        self.bnf_table = self.bnf_group.table
        self.bnf_table._data_table.itemDoubleClicked.connect(self._on_benefit_double_clicked)
        self.cov_table.setToolTip("Double-click a coverage for every field, interpreted and raw")
        self.bnf_table.setToolTip("Double-click a benefit for every field, interpreted and raw")
        self.bnf_table.set_empty_message("No supplemental benefits on this policy.")
        self.bnf_table.set_column_settings_key("polview.benefits")
        layout.addWidget(self.bnf_group, 1)
        self._layout = layout

    def _balance_sections(self, coverage_rows: int, benefit_rows: int):
        """Share vertical space in proportion to the rows each table holds."""
        self._layout.setStretchFactor(self.cov_group, max(2, min(coverage_rows, 12) + 1))
        self._layout.setStretchFactor(self.bnf_group, max(1, min(benefit_rows, 12) + 1))

    # ── helpers ───────────────────────────────────────────────────────────

    def _make_label(self, text: str, style: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(style)
        return lbl

    def _set_item(self, row: int, col: int, value):
        text = str(value) if value is not None else ""
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.cov_table.setItem(row, col, item)

    def _set_bnf_item(self, row: int, col: int, value):
        text = str(value) if value is not None else ""
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.bnf_table.setItem(row, col, item)

    def _format_vpu(self, value) -> str:
        if value is None:
            return ""
        try:
            v = float(value)
            if v == 1000:
                return "1,000"
            return f"{v:,.3f}"
        except Exception:
            return str(value)

    @staticmethod
    def _format_percent(value) -> str:
        """Format a corridor percentage — '250%' / '182.5%'."""
        if value is None:
            return ""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{v:,.0f}%" if v == int(v) else f"{v:,.3f}".rstrip("0").rstrip(".") + "%"

    def _on_coverage_double_clicked(self, item):
        row = item.row()
        if row < 0 or row >= len(self._cov_data):
            return
        coverage = self._cov_data[row]
        if str(getattr(coverage, "plancode", "")).strip().upper() == "0699830R":
            self.annuity_rider_requested.emit(coverage)
            return
        self._open_record_card(
            f"Coverage {coverage.cov_pha_nbr} · {getattr(coverage, 'plancode', '')}", coverage)

    def _on_benefit_double_clicked(self, item):
        row = item.row()
        if 0 <= row < len(self._bnf_data):
            benefit = self._bnf_data[row]
            self._open_record_card(
                f"Benefit {benefit.benefit_code} · phase {benefit.cov_pha_nbr}", benefit)

    def _open_record_card(self, title: str, record):
        from PyQt6 import sip
        from ..polview_dialogs import RecordCardDialog

        # Closed cards delete themselves; drop their dead wrappers before touching them.
        self._record_cards = [d for d in getattr(self, "_record_cards", []) if not sip.isdeleted(d)]
        dialog = RecordCardDialog(title, record, self.window())
        offset = 24 * (len(self._record_cards) % 8)
        dialog.show()
        dialog.move(dialog.pos().x() + offset, dialog.pos().y() + offset)
        self._record_cards.append(dialog)

    # ── data loading ─────────────────────────────────────────────────────

    def load_data_from_policy(self, policy: 'PolicyInformation'):
        """Load coverage data using PolicyInformation object."""
        # Clear old data first so stale values never remain when switching policies
        self._cov_data = []
        self._bnf_data = []
        self.info_group.clear_info()
        for lbl in (self.total_death_benefit_label, self.corridor_label):
            lbl.setStyleSheet(_VAL_STYLE)
            lbl.setToolTip("")
        self.cov_table.setRowCount(0)
        self.bnf_table.setRowCount(0)

        try:
            if not policy.identity.exists:
                return
            self._populate_status_labels_from_policy(policy)
            coverages = policy.coverages.get_coverages()
            self._cov_data = list(coverages)
            self._populate_coverages_from_policy(policy, coverages)
            benefits = policy.benefits.get_benefits()
            self._bnf_data = list(benefits)
            self._populate_benefits_from_policy(benefits)
            self._balance_sections(len(coverages), len(benefits))
        except Exception:
            logger.exception("CoveragesTab failed to load policy data")
            raise

    def _populate_status_labels_from_policy(self, policy: 'PolicyInformation'):
        self.policy_label.setText(policy.identity.policy_number)
        self.company_label.setText(policy.identity.company_code)
        self.market_org_label.setText(policy.agents.servicing_market_org)
        self.issue_state_label.setText(policy.product.issue_state)
        self.definition_of_life_label.setText(policy.product.gpt_cvat)
        self.billing_mode_label.setText(policy.billing.billing_mode)
        self.premium_label.setText(format_amount(policy.billing.modal_premium))
        self.region_label.setText(policy.identity.region)
        self.system_cd_label.setText(policy.identity.system_code)

        self.joint_label.setText(policy.coverages.insured_lives_description)

        self.suspense_label.setText(f"{policy.status.suspense_code} - {policy.status.suspense_description}")

        if policy.status.in_grace:
            self.grace_label.setText("In Grace")
            self.grace_label.setStyleSheet("font-size: 10px; color: #C00000; font-weight: bold;")
        else:
            self.grace_label.setText("Not in Grace")
            self.grace_label.setStyleSheet("font-size: 10px;")

        if policy.values.valuation_date:
            self.eff_date_label.setText(policy.values.valuation_date.strftime("%m/%d/%Y"))
        else:
            self.eff_date_label.setText("")

        self.policy_year_label.setText(str(policy.activity.policy_year))

        self._populate_death_benefit(policy)

        att_age = policy.coverages.attained_age
        if att_age is not None:
            self.att_age_label.setText(str(att_age))
        else:
            self.att_age_label.setText("")

        status_code = policy.status.premium_pay_status_code
        self.status_label.setText(f"{status_code} - {policy.status.premium_pay_status_description}")

        try:
            if status_code and int(status_code) >= 40:
                self.status_label.setStyleSheet("font-size: 10px; color: #C00000; font-weight: bold;")
            else:
                self.status_label.setStyleSheet("font-size: 10px;")
        except Exception:
            self.status_label.setStyleSheet("font-size: 10px;")

        # Reinsurance partner code — from TH_USER_GENERIC.FUZGREIN_IND
        rein_raw = (policy.support.reins_partner or "").strip()
        self.reins_partner_label.setText("RGA" if rein_raw == "R" else "ANICO" if rein_raw else "(none)")

        # Death Benefit Option — UL products only
        _DB_OPT_DISPLAY = {"1": "A-Level", "2": "B-Increasing", "3": "C-ROP"}
        if policy.product.is_advanced_product:
            self.db_option_label.setText(_DB_OPT_DISPLAY.get(policy.product.db_option_code, ""))
        else:
            self.db_option_label.setText("")

    def _populate_death_benefit(self, policy: 'PolicyInformation'):
        """Show the total death benefit and whether the 7702 corridor drives it.

        The corridor death benefit (account value × corridor %) replaces the
        standard face + DB-option amount whenever it is larger; the Corridor
        field says so and the tooltip shows the full comparison.
        """
        standard_db = policy.coverages.standard_death_benefit
        corridor_db = policy.coverages.corridor_death_benefit
        total_db = policy.coverages.total_death_benefit
        in_corridor = corridor_db is not None and corridor_db > standard_db

        self.total_death_benefit_label.setText(format_amount(total_db))
        self.total_death_benefit_label.setStyleSheet(
            _VAL_STYLE_CORRIDOR if in_corridor else _VAL_STYLE)

        db_option_note = {
            "2": " + account value", "3": " + premiums paid",
        }.get(str(policy.product.db_option_code or "").strip(), "")
        lines = [f"Standard DB (face{db_option_note}): {format_amount(standard_db)}"]

        if corridor_db is None:
            self.corridor_label.setText("N/A")
            self.corridor_label.setStyleSheet(_VAL_STYLE_NA)
            reason = ("traditional product" if not policy.product.is_advanced_product
                      else "no account value on file")
            lines.append(f"Corridor: not applicable ({reason})")
        else:
            account_value = policy.coverages.current_account_value
            percent_text = self._format_percent(policy.product.corridor_percent)
            lines.append(
                f"Corridor DB ({format_amount(account_value)} AV × {percent_text}): "
                f"{format_amount(corridor_db)}"
            )
            if in_corridor:
                self.corridor_label.setText("In Corridor")
                self.corridor_label.setStyleSheet(_VAL_STYLE_CORRIDOR)
                lines.append(
                    f"Corridor adds {format_amount(policy.coverages.corridor_amount)} "
                    "over the standard DB")
            else:
                self.corridor_label.setText("Not in Corridor")
                self.corridor_label.setStyleSheet(_VAL_STYLE)

        lines.append(f"Total DB: {format_amount(total_db)}")
        tooltip = "\n".join(lines)
        self.total_death_benefit_label.setToolTip(tooltip)
        self.corridor_label.setToolTip(tooltip)

    def _populate_coverages_from_policy(self, policy: 'PolicyInformation', coverages: list):
        if not coverages:
            self.cov_table.setRowCount(0)
            return

        is_ul_product = policy.product.product_line_code == "U"
        columns = self._coverage_columns(is_ul_product)
        self.cov_table.setColumnCount(len(columns))
        self.cov_table.setHorizontalHeaderLabels(columns)
        for c in range(len(columns)):
            h = self.cov_table._data_table.horizontalHeaderItem(c)
            if h:
                h.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.cov_table.setRowCount(len(coverages))

        base_issue_date = coverages[0].issue_date if coverages else None
        val_date = policy.values.valuation_date
        years_base_to_val = 0
        if base_issue_date and val_date:
            years_base_to_val = policy.activity._completed_date_parts_years(base_issue_date, val_date)

        for row_idx, cov in enumerate(coverages):
            self._populate_coverage_row(
                row_idx, cov, policy, is_ul_product,
                base_issue_date, val_date, years_base_to_val,
            )

        self.cov_table.autoFitAllColumns()

    @staticmethod
    def _coverage_columns(is_ul_product: bool) -> list[str]:
        columns = ["Phs", "Form", "COLA", "GIO", "Plancode", "IssueDate", "Mat Date", "Amount"]
        if is_ul_product:
            columns.append("Orig Amt")
        columns.extend([
            "IssAge", "Gender", "Class", "Tbl", "Tbl Cease Date", "Flat",
            "Flat Cease", "Status", "CeaseDate", "Rate", "AttAge", "PRS", "LIV", "VPU",
        ])
        return columns

    def _coverage_rate_class(self, policy, cov) -> str:
        rate_class = cov.rate_class
        if not rate_class:
            rnl_idx = policy.rates.cov_renewal_index(cov.cov_pha_nbr, "C", "0")
            if rnl_idx >= 0:
                rate_class = policy.rates.renewal_cov_rateclass(rnl_idx)
        return rate_class

    def _coverage_attained_age(
        self, policy, cov, base_issue_date, val_date, years_base_to_val: int
    ):
        if not (val_date and base_issue_date and cov.issue_age is not None):
            return ""
        years_base_to_cov = 0
        if cov.issue_date and base_issue_date:
            years_base_to_cov = policy.activity._completed_date_parts_years(base_issue_date, cov.issue_date)
        return cov.issue_age + years_base_to_val - years_base_to_cov

    def _set_coverage_status_item(self, row_idx: int, col: int, status) -> None:
        self._set_item(row_idx, col, _COVERAGE_STATUS_TEXT.get(str(status).strip(), status))
        status_item = self.cov_table.item(row_idx, col)
        if status_item is not None:
            status_item.setToolTip(f"Next change type {status} (LH_COV_PHA.NXT_CHG_TYP_CD)")
            if str(status).strip() == "0":
                status_item.setForeground(QColor("#B71C1C"))

    def _populate_coverage_row(
        self,
        row_idx: int,
        cov,
        policy,
        is_ul_product: bool,
        base_issue_date,
        val_date,
        years_base_to_val: int,
    ) -> None:
        values = [
            cov.cov_pha_nbr,
            getattr(cov, 'form_number', ""),
            "COLA" if getattr(cov, 'cola_indicator', '') == "1" else "",
            "GIO" if getattr(cov, 'gio_indicator', '') == "Y" else "",
            cov.plancode,
            format_date(cov.issue_date),
            format_date(getattr(cov, 'maturity_date', None)),
            format_amount(cov.face_amount),
        ]
        if is_ul_product:
            values.append(format_amount(getattr(cov, 'orig_amount', None)))
        values.extend([
            cov.issue_age if cov.issue_age is not None else "",
            cov.sex_desc[:1] if cov.sex_desc else cov.sex_code,
            self._coverage_rate_class(policy, cov),
        ])
        tbl = getattr(cov, 'table_rating', None)
        flat = getattr(cov, 'flat_extra', None)
        values.extend([
            tbl if tbl and tbl != 0 else "",
            format_date(getattr(cov, 'table_cease_date', None)) if tbl and tbl != 0 else "",
            format_amount(flat),
            format_date(getattr(cov, 'flat_cease_date', None)) if flat else "",
        ])
        for col, value in enumerate(values):
            self._set_item(row_idx, col, value)
        col = len(values)
        status = getattr(cov, 'nxt_chg_typ_cd', '') or getattr(cov, 'cov_status', '')
        self._set_coverage_status_item(row_idx, col, status)
        col += 1
        self._set_item(
            row_idx,
            col,
            format_date(getattr(cov, 'nxt_chg_dt', None)) if status == "0" else "",
        )
        col += 1
        rate_val = cov.rate
        self._set_item(row_idx, col, str(rate_val) if rate_val is not None else "")
        col += 1
        self._set_item(
            row_idx, col,
            self._coverage_attained_age(policy, cov, base_issue_date, val_date, years_base_to_val),
        )
        col += 1
        self._set_item(row_idx, col, getattr(cov, 'person_code', ""))
        col += 1
        self._set_item(row_idx, col, getattr(cov, 'lives_cov_cd', ""))
        col += 1
        self._set_item(row_idx, col, self._format_vpu(cov.vpu))

    def _populate_benefits_from_policy(self, benefits: list):
        columns = ["Code", "Name", "Phs", "Type", "Form", "IssueDate", "PayUpDate", "CeaseDate", "OrigCease", "Units", "VPU", "IssAge", "Rating", "Renew", "Rate", "RenewRate"]

        self.bnf_table.setColumnCount(len(columns))
        self.bnf_table.setHorizontalHeaderLabels(columns)
        if not benefits:
            self.bnf_table.setRowCount(0)
            self.bnf_table.autoFitAllColumns()
            return
        # Right-align all headers
        for c in range(len(columns)):
            h = self.bnf_table._data_table.horizontalHeaderItem(c)
            if h:
                h.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.bnf_table.setRowCount(len(benefits))

        for row_idx, bnf in enumerate(benefits):
            rating = getattr(bnf, 'rating_factor', None)
            renew_ind = str(getattr(bnf, 'renewal_indicator', "") or "").strip()
            # Renewal rate (67 segment) — only shown when the benefit renews
            # (Renew indicator = 1) and a renewal rate exists; otherwise blank.
            renewal_rate = getattr(bnf, 'renewal_rate', None)
            name = translate_benefit_type(str(bnf.benefit_type_cd or "").strip(),
                                          str(getattr(bnf, 'benefit_subtype_cd', "") or "").strip())
            values = [
                bnf.benefit_code,
                name,
                bnf.cov_pha_nbr,
                bnf.benefit_type_cd,
                getattr(bnf, 'form_number', ""),
                format_date(getattr(bnf, 'issue_date', None)),
                format_date(getattr(bnf, 'pay_up_date', None)),
                format_date(bnf.cease_date),
                format_date(getattr(bnf, 'orig_cease_date', None)),
                format_amount(getattr(bnf, 'units', None)),
                self._format_vpu(getattr(bnf, 'vpu', None)),
                getattr(bnf, 'issue_age', None),
                f"{rating:.0%}" if rating is not None else "",
                renew_ind,
                getattr(bnf, 'coi_rate', None),
                str(renewal_rate) if (renew_ind == "1" and renewal_rate is not None) else "",
            ]
            for col, value in enumerate(values):
                self._set_bnf_item(row_idx, col, value)
            description = str(getattr(bnf, 'benefit_desc', "") or "").strip()
            name_item = self.bnf_table.item(row_idx, 1)
            if name_item is not None and description:
                name_item.setToolTip(description)

        self.bnf_table.autoFitAllColumns()
