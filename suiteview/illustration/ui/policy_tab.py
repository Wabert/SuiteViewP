"""Policy tab for the Illustration app."""

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from suiteview.polview.ui.formatting import format_amount, format_currency, format_date
from suiteview.polview.ui.widgets import StyledInfoTableGroup

from .styles import FUND_TABLE_STYLE, GROUP_STYLE, GRAY_DARK, PURPLE_BG, PURPLE_DARK, VALUE_BUTTON_STYLE


class IllustrationPolicyTab(QWidget):
    """Initial Illustration Policy tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy = None
        self._coverages = []
        self._benefits = []
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {PURPLE_BG}; border: none; }} "
            f"QScrollArea > QWidget > QWidget {{ background-color: {PURPLE_BG}; }}"
        )
        content = QWidget()
        content.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)

        self.policy_info = StyledInfoTableGroup("Policy Info", columns=4, show_table=False)
        self.policy_info.setStyleSheet(GROUP_STYLE)
        self._setup_policy_info_fields()
        layout.addWidget(self.policy_info)

        self.coverage_group = QGroupBox("Coverages and Benefits")
        self.coverage_group.setStyleSheet(GROUP_STYLE)
        cov_layout = QVBoxLayout(self.coverage_group)
        cov_layout.setContentsMargins(8, 18, 8, 8)
        cov_layout.setSpacing(6)

        self.coverage_buttons = QHBoxLayout()
        self.coverage_buttons.setContentsMargins(0, 0, 0, 0)
        self.coverage_buttons.setSpacing(6)
        cov_layout.addLayout(self.coverage_buttons)
        layout.addWidget(self.coverage_group)

        values_row = QHBoxLayout()
        values_row.setSpacing(8)
        self.account_values = self._make_value_group("Policy Values", [
            ("Shadow Account Value", "shadow_account_value"),
            ("Sweep Account Min", "sweep_account_min"),
            ("Deemed Cash Value", "deemed_cash_value"),
            ("NSP", "nsp"),
        ])
        self.premium_values = self._make_value_group("Premiums and Targets", [
            ("Premium YTD", "premium_ytd"),
            ("Premium TD", "premium_td"),
            ("Withdrawal TD", "withdrawal_td"),
            ("Accum Minimum", "accum_minimum"),
            ("MAP Cease Date", "map_cease_date"),
            ("Monthly MTP", "monthly_mtp"),
            ("Commission Target Premium", "commission_target_premium"),
        ])
        self.loan_values = self._make_value_group("Loans", [
            ("Fixed Loan Principle", "fixed_loan_principal"),
            ("Fixed Loan Accrued", "fixed_loan_accrued"),
            ("Pref Loan Principle", "pref_loan_principal"),
            ("Pref Loan Accrued", "pref_loan_accrued"),
            ("Vbl Loan Principle", "vbl_loan_principal"),
            ("Vbl Loan Accrued", "vbl_loan_accrued"),
        ])
        values_row.addWidget(self.account_values)
        values_row.addWidget(self.premium_values)
        values_row.addWidget(self.loan_values)
        layout.addLayout(values_row)

        tax_row = QHBoxLayout()
        tax_row.setSpacing(8)
        self.tax_values = StyledInfoTableGroup("Tax and TAMRA", columns=2, show_table=False)
        self.tax_values.setStyleSheet(GROUP_STYLE)
        for label, attr in [
            ("Is a MEC?", "is_mec"),
            ("TAMRA Yr 1 Contribution", "tamra_y1"),
            ("Cost Basis", "cost_basis"),
            ("TAMRA Yr 2 Contribution", "tamra_y2"),
            ("7-Pay Cash Value", "seven_pay_cash_value"),
            ("TAMRA Yr 3 Contribution", "tamra_y3"),
            ("7-Pay Premium", "seven_pay_premium"),
            ("TAMRA Yr 4 Contribution", "tamra_y4"),
            ("7-Pay Lowest DB", "seven_yr_lowest_db"),
            ("TAMRA Yr 5 Contribution", "tamra_y5"),
            ("spacer", "tamra_spacer_1"),
            ("TAMRA Yr 6 Contribution", "tamra_y6"),
            ("spacer", "tamra_spacer_2"),
            ("TAMRA Yr 7 Contribution", "tamra_y7"),
        ]:
            if label == "spacer":
                self.tax_values.add_field("-", attr, 1, 1)
                self._set_group_field_visible(self.tax_values, attr, False)
            else:
                self.tax_values.add_field(label, attr, 150, 105)
        self.mec_values = self._make_value_group("TEFRA/DEFRA", [
            ("Definition of Life", "policy_definition"),
            ("Guideline Single", "guideline_single"),
            ("Guideline Level", "guideline_level"),
            ("Accum GLP", "accum_glp"),
        ])
        self.fund_values = StyledInfoTableGroup("Fund Values", columns=1, show_info=True, show_table=True)
        self.fund_values.setStyleSheet(GROUP_STYLE)
        self.fund_values.add_field("Account Value", "fund_account_value", 120, 105)
        self.fund_table = self.fund_values.table
        self.fund_table.setColumnCount(2)
        self.fund_table.setHorizontalHeaderLabels(["Fund", "Fund Value"])
        self.fund_table._data_table.horizontalHeader().setVisible(True)
        self.fund_table._outer_frame.setStyleSheet(FUND_TABLE_STYLE)
        self.fund_table._data_table.setStyleSheet(FUND_TABLE_STYLE)
        tax_row.addWidget(self.tax_values, 2)
        tax_row.addWidget(self.mec_values, 1)
        tax_row.addWidget(self.fund_values, 1)
        layout.addLayout(tax_row)

        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _setup_policy_info_fields(self):
        fields = [
            ("Policy", "policy_label"),
            ("Issue Date", "issue_date"),
            ("Valuation Date", "eff_date_label"),
            ("Billable Premium", "premium_label"),
            ("Company", "company_label"),
            ("Maturity Date", "maturity_date"),
            ("Policy Year", "policy_year_label"),
            ("Billing Mode", "billing_mode_label"),
            ("Plancode", "plancode_label"),
            ("Issue Age", "issue_age"),
            ("Attained Age", "att_age_label"),
            ("Single/Joint", "joint_label"),
            ("Market Org", "market_org_label"),
            ("Sex", "sex"),
            ("Policy Debt", "policy_debt_label"),
            ("spacer", "policy_info_spacer_1"),
            ("Issue State", "issue_state_label"),
            ("Rateclass", "rateclass"),
            ("Total Face", "total_face_label"),
            ("spacer", "policy_info_spacer_2"),
            ("Status", "status_label"),
            ("Table Rating", "table_rating"),
            ("DB Option", "db_option_label"),
            ("spacer", "policy_info_spacer_3"),
            ("Suspense Code", "suspense_label"),
            ("Flat Extra", "flat_extra"),
            ("Total Death Benefit", "total_death_benefit_label"),
            ("spacer", "policy_info_spacer_4"),
            ("Grace Indicator", "grace_label"),
            ("Flat Cease Date", "flat_cease_date"),
            ("spacer", "policy_info_spacer_6"),
            ("spacer", "policy_info_spacer_5"),
        ]
        for label, attr in fields:
            if label == "spacer":
                self.policy_info.add_field("-", attr, 1, 1)
                self._set_group_field_visible(self.policy_info, attr, False)
            else:
                self.policy_info.add_field(label, attr, 110, 100)

    def _make_value_group(self, title: str, fields: list[tuple[str, str]], columns: int = 1):
        group = StyledInfoTableGroup(title, columns=columns, show_table=False)
        group.setStyleSheet(GROUP_STYLE)
        for label, attr in fields:
            group.add_field(label, attr, 150, 105)
        return group

    def load_data_from_policy(self, policy, policy_info: dict | None = None):
        self._policy = policy
        self._clear_all()
        if not policy or not policy.exists:
            return

        if policy_info is None:
            policy_info = {
                "PolicyNumber": policy.policy_number,
                "CompanyCode": policy.company_code,
                "SystemCode": policy.system_code,
                "Region": policy.region,
            }

        self._coverages = list(policy.get_coverages())
        self._benefits = list(policy.get_benefits())
        self._populate_policy_info(policy, policy_info)
        self._populate_value_groups(policy)
        self._populate_fund_values(policy)
        self._populate_coverage_buttons()

    def _clear_all(self):
        for group in [
            self.policy_info,
            self.account_values,
            self.premium_values,
            self.loan_values,
            self.tax_values,
            self.mec_values,
            self.fund_values,
        ]:
            group.clear_info()
        self.fund_table.setRowCount(0)
        self._clear_buttons()

    def _populate_policy_info(self, policy, policy_info: dict):
        base_cov = next((cov for cov in self._coverages if cov.is_base), self._coverages[0] if self._coverages else None)
        self.policy_info.set_value("policy_label", policy_info.get("PolicyNumber", policy.policy_number))
        self.policy_info.set_value("company_label", policy.company_code)
        self.policy_info.set_value("plancode_label", policy.base_plancode)
        self.policy_info.set_value("market_org_label", policy.servicing_market_org)
        self.policy_info.set_value("issue_state_label", policy.issue_state)
        self.policy_info.set_value("billing_mode_label", policy.billing_mode)
        self.policy_info.set_value("premium_label", format_currency(policy.modal_premium, "$"))
        self.policy_info.set_value("joint_label", "Joint" if base_cov and base_cov.lives_cov_cd in ("2", "3") else "Single")
        self.policy_info.set_value("suspense_label", f"{policy.suspense_code} - {policy.suspense_description}")
        self.policy_info.set_value("grace_label", "In Grace" if policy.grace_indicator else "Not in Grace")
        self.policy_info.set_value("eff_date_label", format_date(policy.valuation_date))
        self.policy_info.set_value("policy_year_label", policy.policy_year)
        self.policy_info.set_value("att_age_label", policy.attained_age)
        self.policy_info.set_value("policy_debt_label", format_currency(policy.policy_debt, "$"))
        self.policy_info.set_value("total_face_label", format_amount(policy.base_total_face_amount))
        self.policy_info.set_value("total_death_benefit_label", format_amount(policy.total_death_benefit))
        status_code = policy.premium_pay_status_code
        self.policy_info.set_value("status_label", f"{status_code} - {policy.premium_pay_status_description}")
        db_option = {"1": "A-Level", "2": "B-Increasing", "3": "C-ROP"}.get(str(policy.db_option_code or ""), "")
        self.policy_info.set_value("db_option_label", db_option if policy.is_advanced_product else "")

        if not base_cov:
            return

        self.policy_info.set_value("issue_date", format_date(base_cov.issue_date or policy.issue_date))
        self.policy_info.set_value("maturity_date", format_date(base_cov.maturity_date))
        self.policy_info.set_value("issue_age", base_cov.issue_age)
        self.policy_info.set_value("sex", base_cov.sex_desc or base_cov.sex_code)
        self.policy_info.set_value("rateclass", base_cov.rate_class)
        self.policy_info.set_value("table_rating", base_cov.table_rating if base_cov.table_rating else "")
        self.policy_info.set_value("flat_extra", format_currency(base_cov.flat_extra, "$"))
        self.policy_info.set_value("flat_cease_date", format_date(base_cov.flat_cease_date) if base_cov.flat_extra else "")

    def _populate_value_groups(self, policy):
        definition = "GP" if policy.gpt_cvat == "GPT" else policy.gpt_cvat
        self.account_values.set_value("shadow_account_value", format_currency(policy.gav, "$"))
        self.account_values.set_value("sweep_account_min", "")
        self.account_values.set_value("deemed_cash_value", format_currency(policy.mv_av(0), "$"))
        self.account_values.set_value("nsp", format_currency(self._nsp_total(policy), "$"))
        self.fund_values.set_value("fund_account_value", format_currency(policy.mv_av(0), "$"))
        for attr in ["deemed_cash_value", "nsp"]:
            self._set_group_field_visible(self.account_values, attr, definition == "CVAT")

        self.premium_values.set_value("premium_ytd", format_currency(policy.premium_ytd, "$"))
        self.premium_values.set_value("premium_td", format_currency(policy.premium_td, "$"))
        self.premium_values.set_value("withdrawal_td", format_currency(policy.total_withdrawals, "$"))
        self.premium_values.set_value("accum_minimum", format_currency(policy.accumulated_mtp_target, "$"))
        self.premium_values.set_value("map_cease_date", format_date(policy.map_date))
        self.premium_values.set_value("monthly_mtp", format_currency(policy.mtp, "$"))
        self.premium_values.set_value("commission_target_premium", format_currency(policy.ctp, "$"))

        self.loan_values.set_value("fixed_loan_principal", format_currency(policy.total_regular_loan_principal, "$"))
        self.loan_values.set_value("fixed_loan_accrued", format_currency(policy.total_regular_loan_accrued, "$"))
        self.loan_values.set_value("pref_loan_principal", format_currency(policy.total_preferred_loan_principal, "$"))
        self.loan_values.set_value("pref_loan_accrued", format_currency(policy.total_preferred_loan_accrued, "$"))
        self.loan_values.set_value("vbl_loan_principal", format_currency(policy.total_variable_loan_principal, "$"))
        self.loan_values.set_value("vbl_loan_accrued", format_currency(policy.total_variable_loan_accrued, "$"))

        self.tax_values.set_value("cost_basis", format_currency(policy.cost_basis, "$"))
        for year in range(1, 8):
            self.tax_values.set_value(f"tamra_y{year}", format_currency(policy.tamra_7pay_premium_paid(year), "$"))
        self.tax_values.set_value("seven_pay_cash_value", format_currency(policy.tamra_7pay_av, "$"))
        self.tax_values.set_value("seven_pay_premium", format_currency(policy.tamra_7pay_level, "$"))
        self.tax_values.set_value("seven_yr_lowest_db", format_currency(policy.tamra_7pay_specified_amount, "$"))
        self.tax_values.set_value("is_mec", "Yes" if policy.is_mec else "No")

        self.mec_values.set_value("policy_definition", definition)
        self.mec_values.set_value("guideline_single", format_currency(policy.gsp, "$"))
        self.mec_values.set_value("guideline_level", format_currency(policy.glp, "$"))
        self.mec_values.set_value("accum_glp", format_currency(policy.accumulated_glp_target, "$"))
        for attr in ["guideline_single", "guideline_level", "accum_glp"]:
            self._set_group_field_visible(self.mec_values, attr, definition == "GP")

    def _populate_fund_values(self, policy):
        fund_values = self._current_fund_values_by_fund(policy)
        rows = [(fund, value) for fund, value in sorted(fund_values.items()) if self._is_nonzero(value)]
        self.fund_table.setRowCount(len(rows))
        for row, (fund, value) in enumerate(rows):
            self._set_table_item(row, 0, fund)
            self._set_table_item(row, 1, format_currency(value, "$"))
        self.fund_table.autoFitAllColumns()

    def _current_fund_values_by_fund(self, policy):
        fund_values = {}
        try:
            buckets = policy.get_fund_buckets(current_only=True)
            for bucket in buckets:
                fund_id = str(getattr(bucket, "fund_id", "") or "").strip()
                if not fund_id:
                    continue
                amount = getattr(bucket, "csv_amount", None) or Decimal("0")
                fund_values[fund_id] = fund_values.get(fund_id, Decimal("0")) + Decimal(str(amount))
        except Exception:
            try:
                fund_values = policy.get_fund_values_dict()
            except Exception:
                fund_values = {}
        return fund_values

    def _nsp_total(self, policy):
        values = [policy.nsp_base, policy.nsp_other]
        return sum((Decimal(str(value)) for value in values if value is not None), Decimal("0"))

    def _set_group_field_visible(self, group, attr_name: str, visible: bool):
        if hasattr(group, "_labels") and attr_name in group._labels:
            group._labels[attr_name].setVisible(visible)
        if hasattr(group, "_fields") and attr_name in group._fields:
            group._fields[attr_name].setVisible(visible)

    def _populate_coverage_buttons(self):
        self._clear_buttons()
        items = []
        for cov in self._coverages:
            label = cov.form_number or cov.plancode or f"Coverage {cov.cov_pha_nbr}"
            items.append((label, "coverage", cov))
        for benefit in self._benefits:
            label = benefit.form_number or benefit.benefit_code or f"Benefit {benefit.cov_pha_nbr}"
            items.append((label, "benefit", benefit))

        for label, kind, item in items:
            btn = QPushButton(label)
            btn.setStyleSheet(VALUE_BUTTON_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip("Click for details")
            btn.clicked.connect(lambda checked=False, k=kind, i=item: self._show_detail_dialog(k, i))
            self.coverage_buttons.addWidget(btn)
        self.coverage_buttons.addStretch(1)

    def _clear_buttons(self):
        while self.coverage_buttons.count():
            item = self.coverage_buttons.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _show_detail_dialog(self, kind: str, item):
        dlg = QDialog(self)
        dlg.setWindowTitle("Coverage Detail" if kind == "coverage" else "Benefit Detail")
        dlg.setMinimumWidth(420)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)
        rows = self._coverage_detail_rows(item) if kind == "coverage" else self._benefit_detail_rows(item)
        for row, (label_text, value_text) in enumerate(rows):
            label = QLabel(label_text)
            label.setStyleSheet(f"font-weight: bold; color: {PURPLE_DARK}; font-size: 11px;")
            value = QLabel(str(value_text) if value_text is not None else "")
            value.setStyleSheet(f"color: {GRAY_DARK}; font-size: 11px;")
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(value, row, 1, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(grid)
        layout.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(VALUE_BUTTON_STYLE)
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec()

    def _coverage_detail_rows(self, cov):
        return [
            ("Phase:", cov.cov_pha_nbr),
            ("Form:", cov.form_number),
            ("Plancode:", cov.plancode),
            ("Issue Date:", format_date(cov.issue_date)),
            ("Maturity Date:", format_date(cov.maturity_date)),
            ("Amount:", format_amount(cov.face_amount)),
            ("Original Amount:", format_amount(cov.orig_amount)),
            ("Issue Age:", cov.issue_age),
            ("Gender:", cov.sex_desc or cov.sex_code),
            ("Class:", cov.rate_class),
            ("Table:", cov.table_rating if cov.table_rating else ""),
            ("Table Cease Date:", format_date(cov.table_cease_date) if cov.table_rating else ""),
            ("Flat:", format_currency(cov.flat_extra, "$")),
            ("Flat Cease:", format_date(cov.flat_cease_date) if cov.flat_extra else ""),
            ("Status:", cov.nxt_chg_typ_cd or cov.cov_status),
            ("Cease Date:", format_date(cov.nxt_chg_dt)),
            ("Rate:", cov.rate if cov.rate is not None else ""),
            ("Person:", cov.person_code),
            ("Lives:", cov.lives_cov_cd),
            ("VPU:", format_amount(cov.vpu)),
        ]

    def _benefit_detail_rows(self, benefit):
        rating = benefit.rating_factor
        try:
            rating_text = f"{float(rating):.0%}" if rating else ""
        except Exception:
            rating_text = ""
        return [
            ("Code:", benefit.benefit_code),
            ("Phase:", benefit.cov_pha_nbr),
            ("Type:", benefit.benefit_type_cd),
            ("Description:", benefit.benefit_desc),
            ("Form:", benefit.form_number),
            ("Issue Date:", format_date(benefit.issue_date)),
            ("Cease Date:", format_date(benefit.cease_date)),
            ("Orig Cease:", format_date(benefit.orig_cease_date)),
            ("Units:", format_amount(benefit.units)),
            ("VPU:", format_amount(benefit.vpu)),
            ("Amount:", format_amount(benefit.benefit_amount)),
            ("Issue Age:", benefit.issue_age),
            ("Rating:", rating_text),
            ("Renew:", benefit.renewal_indicator),
            ("Rate:", benefit.coi_rate if benefit.coi_rate else ""),
        ]

    def _set_table_item(self, row: int, col: int, value):
        item = QTableWidgetItem(str(value) if value is not None else "")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.fund_table.setItem(row, col, item)

    @staticmethod
    def _is_nonzero(value) -> bool:
        try:
            return Decimal(str(value or 0)) != 0
        except Exception:
            return bool(value)
