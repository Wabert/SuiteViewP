"""
Coverages tab – Policy Info header, Coverages table, and Benefits table.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidgetItem
from PyQt6.QtCore import Qt, pyqtSignal

from ..formatting import format_date, format_amount, is_numeric
from ..styles import WHITE
from ..widgets import StyledInfoTableGroup

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ...models.policy_information import PolicyInformation


class CoveragesTab(QWidget):
    """Tab for Coverages view - matches VBA PopulateCoverges layout."""

    # Emitted when the user double-clicks the "Policy Info" header
    policy_support_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cov_data = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.setStyleSheet(f"background-color: {WHITE};")

        # Policy Info Header — 4 columns; col 4 is reserved for Reins Partner (row 3 only)
        self.info_group = StyledInfoTableGroup("Policy Info", columns=4, show_table=False)
        self.info_group.setMaximumWidth(900)
        self.info_group.setMaximumHeight(140)

        # Row 0 (3 fields; skip col 4 by advancing the counter manually)
        self.info_group.add_field("Policy", "policy_label", 80, 80)
        self.info_group.add_field("System Cd", "system_cd_label", 80, 80)
        self.info_group.add_field("Eff Date", "eff_date_label", 80, 100)
        self.info_group._current_col = 0; self.info_group._current_row += 1  # skip col 4
        # Row 1 (3 fields; skip col 4)
        self.info_group.add_field("Type", "type_label", 80, 80)
        self.info_group.add_field("Single/Joint", "joint_label", 80, 80)
        self.info_group.add_field("Policy Year", "policy_year_label", 80, 100)
        self.info_group._current_col = 0; self.info_group._current_row += 1  # skip col 4
        # Row 2 (3 fields; skip col 4)
        self.info_group.add_field("Company", "company_label", 80, 80)
        self.info_group.add_field("Suspense Code", "suspense_label", 80, 80)
        self.info_group.add_field("Att Age", "att_age_label", 80, 100)
        self.info_group._current_col = 0; self.info_group._current_row += 1  # skip col 4
        # Row 3 (4 fields — Reins Partner fills the 4th column)
        self.info_group.add_field("Region", "region_label", 80, 80)
        self.info_group.add_field("Grace Indicator", "grace_label", 80, 80)
        self.info_group.add_field("Status", "status_label", 80, 100)
        self.info_group.add_field("Reins Partner", "reins_partner_label", 80, 80)

        # Backward-compat aliases
        self.policy_label = self.info_group.policy_label
        self.type_label = self.info_group.type_label
        self.company_label = self.info_group.company_label
        self.region_label = self.info_group.region_label
        self.system_cd_label = self.info_group.system_cd_label
        self.joint_label = self.info_group.joint_label
        self.suspense_label = self.info_group.suspense_label
        self.grace_label = self.info_group.grace_label
        self.eff_date_label = self.info_group.eff_date_label
        self.policy_year_label = self.info_group.policy_year_label
        self.att_age_label = self.info_group.att_age_label
        self.status_label = self.info_group.status_label
        self.reins_partner_label = self.info_group.reins_partner_label

        # Make the "Policy Info" header double-clickable to open Policy Support
        self.info_group.setToolTip("Double-click to open Policy Support")
        self.info_group.setCursor(Qt.CursorShape.PointingHandCursor)
        self.info_group.installEventFilter(self)

        layout.addWidget(self.info_group)

        # Coverages table
        self.cov_group = StyledInfoTableGroup("Coverages", show_info=False)
        self.cov_table = self.cov_group.table
        layout.addWidget(self.cov_group)

        # Benefits table
        self.bnf_group = StyledInfoTableGroup("Benefits", show_info=False)
        self.bnf_table = self.bnf_group.table
        layout.addWidget(self.bnf_group)

        layout.addStretch()

    def eventFilter(self, obj, event):
        """Intercept double-click on the Policy Info group to emit signal."""
        from PyQt6.QtCore import QEvent
        if obj is self.info_group and event.type() == QEvent.Type.MouseButtonDblClick:
            self.policy_support_requested.emit()
            return True
        return super().eventFilter(obj, event)

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

    # ── data loading ─────────────────────────────────────────────────────

    def load_data_from_policy(self, policy: 'PolicyInformation'):
        """Load coverage data using PolicyInformation object."""
        # Clear old data first so stale values never remain when switching policies
        self.info_group.clear_info()
        self.cov_table.setRowCount(0)
        self.bnf_table.setRowCount(0)

        try:
            if not policy.exists:
                return
            self._populate_status_labels_from_policy(policy)
            coverages = policy.get_coverages()
            self._populate_coverages_from_policy(policy, coverages)
            benefits = policy.get_benefits()
            self._populate_benefits_from_policy(benefits)
        except Exception as e:
            import traceback, sys
            print(f"[CoveragesTab] Error loading data: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    def _populate_status_labels_from_policy(self, policy: 'PolicyInformation'):
        # Show policy number with form number from first coverage (the policy form)
        coverages = policy.get_coverages()
        form_number = coverages[0].form_number if coverages else ""
        pol_text = policy.policy_number
        if form_number:
            pol_text += f" - {form_number}"
        self.policy_label.setText(pol_text)
        self.type_label.setText(policy.product_type)
        self.company_label.setText(policy.company_code)
        self.region_label.setText(policy.region)
        self.system_cd_label.setText(policy.system_code)

        base_cov = next((c for c in coverages if c.is_base), None)
        if base_cov and base_cov.lives_cov_cd in ("2", "3"):
            self.joint_label.setText("Joint")
        else:
            self.joint_label.setText("Single")

        self.suspense_label.setText(f"{policy.suspense_code} - {policy.suspense_description}")

        if policy.grace_indicator:
            self.grace_label.setText("In Grace")
            self.grace_label.setStyleSheet("font-size: 10px; color: #C00000; font-weight: bold;")
        else:
            self.grace_label.setText("Not in Grace")
            self.grace_label.setStyleSheet("font-size: 10px;")

        if policy.valuation_date:
            self.eff_date_label.setText(policy.valuation_date.strftime("%m/%d/%Y"))
        else:
            self.eff_date_label.setText("")

        self.policy_year_label.setText(str(policy.policy_year))

        att_age = policy.attained_age
        if att_age is not None:
            self.att_age_label.setText(str(att_age))
        else:
            self.att_age_label.setText("")

        status_code = policy.premium_pay_status_code
        self.status_label.setText(f"{status_code} - {policy.premium_pay_status_description}")

        try:
            if status_code and int(status_code) >= 40:
                self.status_label.setStyleSheet("font-size: 10px; color: #C00000; font-weight: bold;")
            else:
                self.status_label.setStyleSheet("font-size: 10px;")
        except Exception:
            self.status_label.setStyleSheet("font-size: 10px;")

        # Reinsurance partner code — from TH_USER_GENERIC.FUZGREIN_IND
        self.reins_partner_label.setText(policy.reins_partner)

    def _populate_coverages_from_policy(self, policy: 'PolicyInformation', coverages: list):
        if not coverages:
            self.cov_table.setRowCount(0)
            return

        is_ul_product = policy.product_line_code == "U"

        columns = ["Phs", "Form", "COLA", "GIO", "Plancode", "IssueDate", "Mat Date", "Amount"]
        if is_ul_product:
            columns.append("Orig Amt")
        columns.extend(["IssAge", "Gender", "Class", "Tbl", "Flat", "Flat Cease", "Status", "CeaseDate", "Rate", "AttAge", "PRS", "LIV", "VPU"])

        self.cov_table.setColumnCount(len(columns))
        self.cov_table.setHorizontalHeaderLabels(columns)
        # Right-align all headers
        for c in range(len(columns)):
            h = self.cov_table._data_table.horizontalHeaderItem(c)
            if h:
                h.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.cov_table.setRowCount(len(coverages))

        # Pre-compute values for per-coverage attained age (VBA formula):
        # AA = CovIssueAge(x) + CompletedDateParts("YYYY", CovIssueDate(1), ValuationDate)
        #      - CompletedDateParts("YYYY", CovIssueDate(1), CovIssueDate(x))
        base_issue_date = coverages[0].issue_date if coverages else None
        val_date = policy.valuation_date
        # Completed years from base issue date to valuation date
        years_base_to_val = 0
        if base_issue_date and val_date:
            years_base_to_val = policy._completed_date_parts_years(base_issue_date, val_date)

        for row_idx, cov in enumerate(coverages):
            col = 0
            self._set_item(row_idx, col, cov.cov_pha_nbr); col += 1
            self._set_item(row_idx, col, getattr(cov, 'form_number', "")); col += 1
            self._set_item(row_idx, col, "COLA" if getattr(cov, 'cola_indicator', '') == "1" else ""); col += 1
            self._set_item(row_idx, col, "GIO" if getattr(cov, 'gio_indicator', '') == "Y" else ""); col += 1
            self._set_item(row_idx, col, cov.plancode); col += 1
            self._set_item(row_idx, col, format_date(cov.issue_date)); col += 1
            self._set_item(row_idx, col, format_date(getattr(cov, 'maturity_date', None))); col += 1
            self._set_item(row_idx, col, format_amount(cov.face_amount)); col += 1
            if is_ul_product:
                self._set_item(row_idx, col, format_amount(getattr(cov, 'orig_amount', None))); col += 1
            self._set_item(row_idx, col, cov.issue_age or ""); col += 1
            self._set_item(row_idx, col, (cov.sex_desc[:1] if cov.sex_desc else cov.sex_code)); col += 1
            # Rate class: prefer renewal rate record, fall back to LH_COV_PHA
            rate_class = cov.rate_class
            if not rate_class:
                rnl_idx = policy.cov_renewal_index(cov.cov_pha_nbr, "C", "0")
                if rnl_idx >= 0:
                    rate_class = policy.renewal_cov_rateclass(rnl_idx)
            self._set_item(row_idx, col, rate_class); col += 1
            tbl = getattr(cov, 'table_rating', None)
            self._set_item(row_idx, col, tbl if tbl and tbl != 0 else ""); col += 1
            flat = getattr(cov, 'flat_extra', None)
            try:
                flat_val = float(flat) if flat else 0
            except Exception:
                flat_val = 0
            self._set_item(row_idx, col, format_amount(flat) if flat_val > 0 else ""); col += 1
            self._set_item(row_idx, col, format_date(getattr(cov, 'flat_cease_date', None)) if flat_val > 0 else ""); col += 1
            # Status, CeaseDate, Rate
            status = getattr(cov, 'nxt_chg_typ_cd', '') or getattr(cov, 'cov_status', '')
            self._set_item(row_idx, col, status); col += 1
            self._set_item(row_idx, col, format_date(getattr(cov, 'nxt_chg_dt', None)) if status == "0" else ""); col += 1
            # Rate: cov.rate picks the right value automatically:
            #   Advanced products → coi_rate  (from LH_COV_INS_RNL_RT.RNL_RT)
            #   Traditional products → premium_rate (from LH_COV_PHA.ANN_PRM_UNT_AMT)
            rate_val = cov.rate
            self._set_item(row_idx, col, str(rate_val) if rate_val is not None else ""); col += 1
            # Per-coverage attained age (AA)
            if val_date and base_issue_date and cov.issue_age is not None:
                # Completed years from base issue date to this coverage's issue date
                years_base_to_cov = 0
                if cov.issue_date and base_issue_date:
                    years_base_to_cov = policy._completed_date_parts_years(base_issue_date, cov.issue_date)
                att_age = cov.issue_age + years_base_to_val - years_base_to_cov
                self._set_item(row_idx, col, att_age)
            else:
                self._set_item(row_idx, col, "")
            col += 1
            # PRS, LIV, VPU
            self._set_item(row_idx, col, getattr(cov, 'person_code', "")); col += 1
            self._set_item(row_idx, col, getattr(cov, 'lives_cov_cd', "")); col += 1
            self._set_item(row_idx, col, self._format_vpu(cov.vpu))

        self.cov_table.autoFitAllColumns()

    def _populate_benefits_from_policy(self, benefits: list):
        if not benefits:
            self.bnf_table.setRowCount(0)
            return

        columns = ["Code", "Phs", "Type", "Form", "IssueDate", "CeaseDate", "OrigCease", "Units", "VPU", "IssAge", "Rating", "Renew", "Rate"]

        self.bnf_table.setColumnCount(len(columns))
        self.bnf_table.setHorizontalHeaderLabels(columns)
        # Right-align all headers
        for c in range(len(columns)):
            h = self.bnf_table._data_table.horizontalHeaderItem(c)
            if h:
                h.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.bnf_table.setRowCount(len(benefits))

        for row_idx, bnf in enumerate(benefits):
            self._set_bnf_item(row_idx, 0, bnf.benefit_code)
            self._set_bnf_item(row_idx, 1, bnf.cov_pha_nbr)
            self._set_bnf_item(row_idx, 2, bnf.benefit_type_cd)
            self._set_bnf_item(row_idx, 3, getattr(bnf, 'form_number', ""))
            self._set_bnf_item(row_idx, 4, format_date(getattr(bnf, 'issue_date', None)))
            self._set_bnf_item(row_idx, 5, format_date(bnf.cease_date))
            self._set_bnf_item(row_idx, 6, format_date(getattr(bnf, 'orig_cease_date', None)))
            self._set_bnf_item(row_idx, 7, format_amount(getattr(bnf, 'units', None)))
            self._set_bnf_item(row_idx, 8, self._format_vpu(getattr(bnf, 'vpu', None)))
            self._set_bnf_item(row_idx, 9, getattr(bnf, 'issue_age', "") or "")
            rating = getattr(bnf, 'rating_factor', None)
            try:
                rating_str = f"{float(rating):.0%}" if rating else ""
            except Exception:
                rating_str = ""
            self._set_bnf_item(row_idx, 10, rating_str)
            self._set_bnf_item(row_idx, 11, getattr(bnf, 'renewal_indicator', ""))
            self._set_bnf_item(row_idx, 12, getattr(bnf, 'coi_rate', "") or "")

        self.bnf_table.autoFitAllColumns()
