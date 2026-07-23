"""Policy tab for the Illustration app."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

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

from suiteview.illustration.core.illustration_policy_service import coverage_or_benefit_matured
from suiteview.polview.ui.formatting import format_amount, format_currency, format_date
from suiteview.polview.ui.widgets import FixedHeaderTableWidget, StyledInfoTableGroup

from .styles import (
    FUND_TABLE_STYLE,
    GROUP_STYLE,
    GRAY_DARK,
    PURPLE_BG,
    PURPLE_DARK,
    VALUE_BUTTON_MATURED_STYLE,
    VALUE_BUTTON_STYLE,
)


RATE_WARNING_STYLE = """
    QLabel {
        background-color: #FFF0B3;
        color: #5C2B00;
        border: 2px solid #B85C00;
        border-radius: 5px;
        padding: 6px 10px;
        font-size: 12px;
        font-weight: bold;
    }
"""

# Saved-case (frozen snapshot) mode: a red statement across the top of the
# Policy tab. Legible, not garish — dark-red text on a pale red wash with a
# red left accent — so the user can never mistake frozen data for live.
SNAPSHOT_BANNER_STYLE = """
    QLabel {
        background-color: #FDECEC;
        color: #B00020;
        border: 1px solid #E0A0A0;
        border-left: 4px solid #B00020;
        border-radius: 4px;
        padding: 6px 12px;
        font-size: 12px;
        font-weight: bold;
    }
"""


class IllustrationPolicyTab(QWidget):
    """Initial Illustration Policy tab."""

    # Fund mini-tables grow with their row count up to this many visible rows,
    # then scroll. Local IUL policies top out around 8 index strategies
    # (UE209026), so 10 covers real plans without reserving empty space.
    _FUND_TABLE_MAX_VISIBLE_ROWS = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy = None
        self._coverages = []
        self._benefits = []
        self.rate_warning_label = None
        self._setup_ui()
        self._build_snapshot_overlay()

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Saved-case red statement — pinned above the scroll area so it stays
        # visible while the frozen policy data scrolls beneath it. Hidden in
        # live mode.
        self.snapshot_banner = QLabel("")
        self.snapshot_banner.setStyleSheet(SNAPSHOT_BANNER_STYLE)
        self.snapshot_banner.setWordWrap(True)
        self.snapshot_banner.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.snapshot_banner.setContentsMargins(12, 8, 12, 0)
        self.snapshot_banner.setVisible(False)
        outer.addWidget(self.snapshot_banner)

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

        self.rate_warning_label = QLabel("")
        self.rate_warning_label.setStyleSheet(RATE_WARNING_STYLE)
        self.rate_warning_label.setWordWrap(True)
        self.rate_warning_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.rate_warning_label.setVisible(False)
        layout.addWidget(self.rate_warning_label)

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
        # Fund Values leads the row: total AV, the shadow/sweep figures that
        # used to live in Policy Values, the policy's guaranteed rate, and — inside
        # the same group — the per-fund breakdown split into Unimpaired (free) and
        # Impaired (loan-collateralized) tables. The two together reconcile to AV.
        self.fund_values = StyledInfoTableGroup("Fund Values", columns=1, show_info=True, show_table=False)
        self.fund_values.setStyleSheet(GROUP_STYLE)
        self.fund_values.add_field("Account Value", "fund_account_value", 120, 105)
        self.fund_values.add_field("Shadow Account Value", "shadow_account_value", 120, 105)
        self.fund_values.add_field("Sweep Account Min", "sweep_account_min", 120, 105)
        self.fund_values.add_field("Guaranteed Int Rate", "guaranteed_int_rate", 120, 105)

        unimpaired_block, self.unimpaired_table = self._make_fund_subtable("Unimpaired Funds")
        impaired_block, self.impaired_table = self._make_fund_subtable("Impaired Funds")
        allocation_block, self.allocation_table = self._make_fund_subtable(
            "Premium Allocations", value_header="Alloc %")
        fund_tables_row = QHBoxLayout()
        fund_tables_row.setContentsMargins(0, 4, 0, 0)
        fund_tables_row.setSpacing(8)
        # Top-align so tables with different fund counts pack to the top edge
        # instead of centering in the tallest sibling's slot.
        fund_tables_row.addWidget(unimpaired_block, 0, Qt.AlignmentFlag.AlignTop)
        fund_tables_row.addWidget(impaired_block, 0, Qt.AlignmentFlag.AlignTop)
        fund_tables_row.addWidget(allocation_block, 0, Qt.AlignmentFlag.AlignTop)
        fund_tables_row.addStretch(1)
        # Nest the tables inside the Fund Values group, just below the info fields
        # (before the trailing stretch added when show_table=False).
        self.fund_values.layout().insertLayout(1, fund_tables_row)

        self.premium_values = self._make_value_group("Premiums and Targets", [
            ("Premium YTD", "premium_ytd"),
            ("Premium TD", "premium_td"),
            ("Withdrawal TD", "withdrawal_td"),
            ("Accum Minimum", "accum_minimum"),
            ("MAP Cease Date", "map_cease_date"),
            ("Monthly MTP", "monthly_mtp"),
            ("Commission Target Premium", "commission_target_premium"),
        ])
        # Balances only (principal + accrued combined); the charge rate sits
        # alongside each balance and only shows when the loan exists.
        self.loan_values = StyledInfoTableGroup("Loans", columns=2, show_table=False)
        self.loan_values.setStyleSheet(GROUP_STYLE)
        for label, attr, rate_label, rate_attr in [
            ("Fixed Loan Balance", "fixed_loan_balance", "Rate", "fixed_loan_rate"),
            ("Pref Loan Balance", "pref_loan_balance", "Rate", "pref_loan_rate"),
            ("Vbl Loan Balance", "vbl_loan_balance", "Rate", "vbl_loan_rate"),
        ]:
            self.loan_values.add_field(label, attr, 120, 95)
            self.loan_values.add_field(rate_label, rate_attr, 40, 60)
        # Fund Values needs the widest slot — it hosts the three fund tables.
        values_row.addWidget(self.fund_values, 2)
        values_row.addWidget(self.premium_values, 1)
        values_row.addWidget(self.loan_values, 1)
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
            ("7-Pay Start Date", "seven_pay_start_date"),
            ("TAMRA Yr 3 Contribution", "tamra_y3"),
            ("7-Pay Cash Value", "seven_pay_cash_value"),
            ("TAMRA Yr 4 Contribution", "tamra_y4"),
            ("7-Pay Premium", "seven_pay_premium"),
            ("TAMRA Yr 5 Contribution", "tamra_y5"),
            ("7-Pay Lowest DB", "seven_yr_lowest_db"),
            ("TAMRA Yr 6 Contribution", "tamra_y6"),
            ("spacer", "tamra_spacer_1"),
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
        # Policy Values swapped into Fund Values' old slot — what remains here
        # are the CVAT-only figures.
        self.account_values = self._make_value_group("Policy Values", [
            ("Deemed Cash Value", "deemed_cash_value"),
            ("NSP", "nsp"),
        ])
        tax_row.addWidget(self.tax_values, 2)
        tax_row.addWidget(self.mec_values, 1)
        tax_row.addWidget(self.account_values, 1)
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
            ("Maturity Age", "maturity_age"),
            ("Issue Age", "issue_age"),
            ("Attained Age", "att_age_label"),
            ("Single/Joint", "joint_label"),
            ("Market Org", "market_org_label"),
            ("Sex", "sex"),
            ("Policy Debt", "policy_debt_label"),
            ("Insured DOB", "insured_dob"),
            ("Issue State", "issue_state_label"),
            ("Rateclass", "rateclass"),
            ("Total Face", "total_face_label"),
            ("spacer", "policy_info_spacer_2"),
            ("Status", "status_label"),
            ("Table Rating", "table_rating"),
            ("DB Option", "db_option_label"),
            ("Cyberlife MD", "cyberlife_md"),
            ("Suspense Code", "suspense_label"),
            ("Flat Extra", "flat_extra"),
            ("Total Death Benefit", "total_death_benefit_label"),
            ("Calculated MD", "calculated_md"),
            ("Grace Indicator", "grace_label"),
            ("Flat Cease Date", "flat_cease_date"),
            ("Guaranteed Int Rate", "guar_int_rate_label"),
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

    def _make_fund_subtable(self, title: str, value_header: str = "Fund Value"):
        """A captioned, compact Fund ID / value table for nesting inside the
        Fund Values group. Returns (container_widget, table)."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        box = QVBoxLayout(container)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)
        caption = QLabel(title)
        caption.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;")
        box.addWidget(caption)
        table = FixedHeaderTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Fund", value_header])
        table._data_table.horizontalHeader().setVisible(True)
        table._outer_frame.setStyleSheet(FUND_TABLE_STYLE)
        table._data_table.setStyleSheet(FUND_TABLE_STYLE)
        self._fit_fund_table(table)
        box.addWidget(table)
        return container, table

    @classmethod
    def _fit_fund_table(cls, table):
        """Autofit columns, then pin the table's size to its content: width so
        all columns show without a horizontal scrollbar, height to header +
        actual fund rows so a one-fund UL doesn't reserve IUL-sized empty
        space. Past _FUND_TABLE_MAX_VISIBLE_ROWS rows the height caps and the
        vertical scrollbar takes over."""
        table.autoFitAllColumns()
        total = sum(table.columnWidth(col) for col in range(table.columnCount()))
        table.setFixedWidth(total + 20)
        cls._pin_fund_table_height(table, table.rowCount())

    @classmethod
    def _pin_fund_table_height(cls, table, row_count: int):
        """Fix the table's height to header + row_count rows (at least one so
        an empty table still reads as one, at most the visible-row cap)."""
        inner = table._data_table
        header_height = inner.horizontalHeader().minimumHeight()
        row_height = inner.verticalHeader().defaultSectionSize()
        visible_rows = max(1, min(row_count, cls._FUND_TABLE_MAX_VISIBLE_ROWS))
        table.setFixedHeight(header_height + visible_rows * row_height + 6)

    def _equalize_fund_tables(self):
        """Give all three fund mini-tables one shared height — the tallest
        table's content (capped) — so the row reads as a unit instead of
        ragged blocks of different heights."""
        tables = (self.unimpaired_table, self.impaired_table, self.allocation_table)
        shared_rows = max(table.rowCount() for table in tables)
        for table in tables:
            self._pin_fund_table_height(table, shared_rows)

    # ── saved-case snapshot overlay ───────────────────────────────────
    #
    # The Policy tab renders from live PolicyInformation (DB2). When the
    # window shows a saved case's frozen IllustrationPolicyData instead,
    # there is no live surface to render — per the house Not-Applicable
    # convention the tab greys out with a centered italic note rather than
    # going blank or silently showing stale data.

    def _build_snapshot_overlay(self):
        self._snapshot_overlay = QWidget(self)
        self._snapshot_overlay.setStyleSheet(
            "background-color: rgba(233, 231, 237, 235);")
        overlay_layout = QVBoxLayout(self._snapshot_overlay)
        overlay_layout.setContentsMargins(40, 40, 40, 40)
        self._snapshot_overlay_label = QLabel("")
        self._snapshot_overlay_label.setWordWrap(True)
        self._snapshot_overlay_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snapshot_overlay_label.setStyleSheet(
            f"color: {GRAY_DARK}; background: transparent;"
            " font-size: 13px; font-style: italic; font-weight: bold;")
        overlay_layout.addStretch(1)
        overlay_layout.addWidget(self._snapshot_overlay_label)
        overlay_layout.addStretch(1)
        self._snapshot_overlay.hide()

    def set_snapshot_notice(self, text: str | None):
        """Grey the tab with an italic note (saved-case view), or restore."""
        if text:
            self._snapshot_overlay_label.setText(text)
            self._snapshot_overlay.setGeometry(self.rect())
            self._snapshot_overlay.show()
            self._snapshot_overlay.raise_()
        else:
            self._snapshot_overlay.hide()

    def snapshot_notice(self) -> str | None:
        """The visible overlay note, or None when live data is shown."""
        if self._snapshot_overlay.isVisibleTo(self):
            return self._snapshot_overlay_label.text() or None
        return None

    def set_snapshot_banner(self, text: str | None):
        """Show/hide the red 'not retrieved live' statement across the top.

        Set while a saved case's frozen policy data populates the tab; cleared
        the moment live data returns (Get). Independent of the grey overlay —
        in saved-case mode the tab is fully populated, not greyed out."""
        if text:
            self.snapshot_banner.setText(text)
            self.snapshot_banner.setVisible(True)
        else:
            self.snapshot_banner.clear()
            self.snapshot_banner.setVisible(False)

    def snapshot_banner_text(self) -> str | None:
        """The visible red banner text, or None when live data is shown."""
        if self.snapshot_banner.isVisibleTo(self):
            return self.snapshot_banner.text() or None
        return None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._snapshot_overlay.isVisibleTo(self):
            self._snapshot_overlay.setGeometry(self.rect())

    def load_data_from_policy(self, policy, policy_info: dict | None = None, md_check=None):
        # Live data on screen — never wear the saved-case red statement.
        self.set_snapshot_banner(None)
        self.set_snapshot_notice(None)
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
        self._as_of = getattr(policy, "valuation_date", None) or date.today()
        self._populate_policy_info(policy, policy_info)
        self.set_monthly_deduction_check(md_check)
        self._populate_value_groups(policy)
        self._populate_fund_values(policy)
        self._populate_coverage_buttons()

    # ── saved-case snapshot population ────────────────────────────────
    #
    # A saved case carries a frozen IllustrationPolicyData (no live DB2). It
    # is a *different shape* from live PolicyInformation, so instead of the old
    # grey overlay we populate every Policy-tab section directly from the
    # snapshot's captured fields. Fields the snapshot never captured (see the
    # session report) are left blank rather than guessed.

    _DB_OPTION_LABELS = {"A": "A-Level", "B": "B-Increasing", "C": "C-ROP"}
    _BILLING_MODE_LABELS = {1: "Monthly", 3: "Quarterly", 6: "Semi-Annual",
                            12: "Annual"}
    _SEX_DESCS = {"M": "Male", "F": "Female", "U": "Unisex"}

    def load_data_from_snapshot(self, snapshot):
        """Populate the Policy tab from a saved case's frozen policy data.

        The grey 'unavailable' overlay is retired for snapshots — the tab is
        fully rendered from what was captured. The caller shows the red
        `set_snapshot_banner(...)` statement so frozen data is never mistaken
        for live."""
        self.set_snapshot_notice(None)
        self._policy = None
        self._clear_all()
        if snapshot is None:
            return

        self._coverages = self._snapshot_coverage_views(snapshot)
        self._benefits = self._snapshot_benefit_views(snapshot)
        self._as_of = snapshot.valuation_date or date.today()
        base_seg = next((s for s in snapshot.segments if s.is_base),
                        snapshot.segments[0] if snapshot.segments else None)

        self._populate_policy_info_from_snapshot(snapshot, base_seg)
        self._populate_value_groups_from_snapshot(snapshot)
        self._populate_fund_values_from_snapshot(snapshot)
        self._populate_coverage_buttons()

    def _populate_policy_info_from_snapshot(self, s, base_seg):
        info = self.policy_info
        info.set_value("policy_label", s.policy_number)
        info.set_value("company_label", s.company_code)
        info.set_value("plancode_label", s.plancode)
        info.set_value("issue_state_label", s.issue_state)
        info.set_value("billing_mode_label", self._billing_mode_label(s.billing_frequency))
        info.set_value("premium_label", format_currency(s.modal_premium, "$"))
        info.set_value("eff_date_label", format_date(s.valuation_date))
        info.set_value("policy_year_label", s.policy_year)
        info.set_value("att_age_label", s.attained_age)
        info.set_value("maturity_age", s.maturity_age or "")
        info.set_value("insured_dob", format_date(s.insured_birth_date))
        info.set_value("cyberlife_md", format_currency(s.system_monthly_deduction, "$"))
        info.set_value("policy_debt_label", format_currency(s.total_loan_balance, "$"))
        info.set_value("total_face_label", format_amount(s.total_face))
        info.set_value("db_option_label", self._DB_OPTION_LABELS.get(str(s.db_option or ""), ""))
        info.set_value("guar_int_rate_label", self._format_rate(s.guaranteed_interest_rate))

        if base_seg is not None:
            info.set_value("issue_date", format_date(base_seg.issue_date or s.issue_date))
            info.set_value("maturity_date", format_date(base_seg.maturity_date))
            info.set_value("issue_age", base_seg.issue_age if base_seg.issue_age else s.issue_age)
            info.set_value("sex", self._sex_desc(base_seg.rate_sex or s.rate_sex))
            info.set_value("rateclass", base_seg.rate_class or s.rate_class)
            info.set_value("table_rating", base_seg.table_rating or "")
            info.set_value("flat_extra", format_currency(base_seg.flat_extra, "$"))
            info.set_value(
                "flat_cease_date",
                format_date(base_seg.flat_cease_date) if base_seg.flat_extra else "")
        else:
            info.set_value("issue_date", format_date(s.issue_date))
            info.set_value("issue_age", s.issue_age)
            info.set_value("sex", self._sex_desc(s.rate_sex))
            info.set_value("rateclass", s.rate_class)
        # Fields the snapshot never captured stay blank (not guessed):
        # Market Org, Single/Joint, Status, Suspense, Grace, Total Death
        # Benefit, and Calculated MD.

    def _populate_value_groups_from_snapshot(self, s):
        definition = "GP" if s.def_of_life_ins == "GPT" else s.def_of_life_ins

        self.fund_values.set_value("fund_account_value", format_currency(s.account_value, "$"))
        self.fund_values.set_value("shadow_account_value", format_currency(s.shadow_account_value, "$"))
        self.fund_values.set_value("sweep_account_min", "—")
        self.fund_values.set_value(
            "guaranteed_int_rate", self._format_rate(s.guaranteed_interest_rate))

        # CVAT-only Policy Values — deemed cash value mirrors the account value
        # (as live does); NSP was not captured, so it stays blank.
        self.account_values.set_value("deemed_cash_value", format_currency(s.account_value, "$"))
        self.account_values.set_value("nsp", "")
        for attr in ["deemed_cash_value", "nsp"]:
            self._set_group_field_visible(self.account_values, attr, definition == "CVAT")

        self.premium_values.set_value("premium_ytd", format_currency(s.premiums_ytd, "$"))
        self.premium_values.set_value("premium_td", format_currency(s.premiums_paid_to_date, "$"))
        self.premium_values.set_value("withdrawal_td", format_currency(s.withdrawals_to_date, "$"))
        self.premium_values.set_value("accum_minimum", format_currency(s.accumulated_mtp, "$"))
        self.premium_values.set_value("map_cease_date", format_date(s.map_cease_date))
        self.premium_values.set_value("monthly_mtp", format_currency(s.mtp, "$"))
        self.premium_values.set_value("commission_target_premium", format_currency(s.ctp, "$"))

        fixed = Decimal(str(s.regular_loan_principal or 0)) + Decimal(str(s.regular_loan_accrued or 0))
        pref = Decimal(str(s.preferred_loan_principal or 0)) + Decimal(str(s.preferred_loan_accrued or 0))
        vbl = Decimal(str(s.variable_loan_principal or 0)) + Decimal(str(s.variable_loan_accrued or 0))
        self.loan_values.set_value("fixed_loan_balance", format_currency(fixed, "$"))
        self.loan_values.set_value("pref_loan_balance", format_currency(pref, "$"))
        self.loan_values.set_value("vbl_loan_balance", format_currency(vbl, "$"))
        # Regular/preferred loan charge rates were not captured — leave blank.
        # The variable-loan charge rate is captured, so show it when a variable
        # loan exists.
        self.loan_values.set_value("fixed_loan_rate", "")
        self.loan_values.set_value("pref_loan_rate", "")
        self.loan_values.set_value(
            "vbl_loan_rate",
            self._format_rate(s.variable_loan_charge_rate)
            if (vbl > 0 and s.variable_loan_charge_rate is not None) else "")

        self.tax_values.set_value("cost_basis", format_currency(s.cost_basis, "$"))
        self.tax_values.set_value("seven_pay_start_date", format_date(s.tamra_7pay_start_date))
        contributions = list(s.tamra_7year_contributions or [])
        for year in range(1, 8):
            value = contributions[year - 1] if year - 1 < len(contributions) else 0.0
            self.tax_values.set_value(f"tamra_y{year}", format_currency(value, "$"))
        self.tax_values.set_value("seven_pay_cash_value", format_currency(s.tamra_7pay_start_av, "$"))
        self.tax_values.set_value("seven_pay_premium", format_currency(s.tamra_7pay_level, "$"))
        # 7-Pay Lowest DB is a snapshot field but the DB2 loader does not yet
        # populate it — it rides through as 0.
        self.tax_values.set_value("seven_yr_lowest_db", format_currency(s.tamra_7year_lowest_db, "$"))
        self.tax_values.set_value("is_mec", "Yes" if s.is_mec else "No")

        self.mec_values.set_value("policy_definition", definition)
        self.mec_values.set_value("guideline_single", format_currency(s.gsp, "$"))
        self.mec_values.set_value("guideline_level", format_currency(s.glp, "$"))
        self.mec_values.set_value("accum_glp", format_currency(s.accumulated_glp, "$"))
        for attr in ["guideline_single", "guideline_level", "accum_glp"]:
            self._set_group_field_visible(self.mec_values, attr, definition == "GP")

    def _populate_fund_values_from_snapshot(self, s):
        # Unimpaired = free fund value by fund. The snapshot captures only the
        # combined fund_values dict (no separate loan-collateralized split), so
        # the Impaired table is empty.
        self._fill_fund_table(self.unimpaired_table, dict(s.fund_values or {}))
        self._fill_fund_table(self.impaired_table, {})
        self._fill_allocation_from_dict(dict(s.premium_allocations or {}))
        self._equalize_fund_tables()

    def _billing_mode_label(self, frequency) -> str:
        try:
            freq = int(frequency or 0)
        except (TypeError, ValueError):
            return ""
        if freq <= 0:
            return ""
        return self._BILLING_MODE_LABELS.get(freq, f"Every {freq} months")

    def _sex_desc(self, code) -> str:
        code = (str(code or "")).strip().upper()
        return self._SEX_DESCS.get(code, code)

    def _snapshot_coverage_views(self, snapshot):
        """Adapt frozen base segments + riders into the attribute surface the
        coverage buttons and detail dialog read from live CoverageInfo."""
        views = []
        for seg in snapshot.segments:
            views.append(SimpleNamespace(
                is_base=seg.is_base,
                cov_pha_nbr=seg.coverage_phase,
                form_number=snapshot.form_number if seg.is_base else "",
                plancode=snapshot.plancode,
                issue_date=seg.issue_date,
                maturity_date=seg.maturity_date,
                face_amount=seg.face_amount,
                orig_amount=seg.original_face_amount,
                issue_age=seg.issue_age,
                sex_code=seg.rate_sex,
                sex_desc=self._sex_desc(seg.rate_sex),
                rate_class=seg.rate_class,
                table_rating=seg.table_rating or "",
                table_cease_date=seg.table_cease_date,
                flat_extra=seg.flat_extra,
                flat_cease_date=seg.flat_cease_date,
                cov_status=seg.status,
                nxt_chg_typ_cd="",
                nxt_chg_dt=None,
                rate=seg.coi_renewal_rate,
                person_code="",
                lives_cov_cd="",
                vpu=seg.vpu,
                cease_date=None,
                terminate_date=None,
            ))
        for rider in snapshot.riders:
            views.append(SimpleNamespace(
                is_base=False,
                cov_pha_nbr=rider.coverage_phase,
                form_number="",
                plancode=rider.plancode,
                issue_date=rider.issue_date,
                maturity_date=rider.maturity_date,
                face_amount=rider.face_amount,
                orig_amount=rider.face_amount,
                issue_age=rider.issue_age,
                sex_code=rider.rate_sex,
                sex_desc=self._sex_desc(rider.rate_sex),
                rate_class=rider.rate_class,
                table_rating=rider.table_rating or "",
                table_cease_date=None,
                flat_extra=rider.flat_extra,
                flat_cease_date=None,
                cov_status=rider.status,
                nxt_chg_typ_cd="",
                nxt_chg_dt=None,
                rate=rider.coi_rate if rider.coi_rate is not None else rider.premium_rate,
                person_code="",
                lives_cov_cd="",
                vpu=rider.vpu,
                cease_date=None,
                terminate_date=None,
            ))
        return views

    def _snapshot_benefit_views(self, snapshot):
        """Adapt frozen benefits into the attribute surface the benefit buttons
        and detail dialog read from live BenefitInfo. Benefit description /
        form / renewal / orig-cease were not captured, so they stay blank; the
        benefit type code stands in for the button label."""
        views = []
        for b in snapshot.benefits:
            views.append(SimpleNamespace(
                benefit_code=b.benefit_type or "",
                cov_pha_nbr=b.coverage_phase,
                benefit_type_cd=b.benefit_type,
                benefit_desc="",
                form_number="",
                issue_date=b.issue_date,
                cease_date=b.cease_date,
                orig_cease_date=None,
                units=b.units,
                vpu=b.vpu,
                benefit_amount=b.benefit_amount,
                issue_age=b.issue_age,
                rating_factor=b.rating_factor,
                renewal_indicator="",
                coi_rate=b.coi_rate,
                maturity_date=None,
                terminate_date=None,
            ))
        return views

    def set_rate_warnings(self, warnings: list[str] | None):
        text = "\n".join(warnings or [])
        self.rate_warning_label.setText(text)
        self.rate_warning_label.setVisible(bool(text))

    def set_monthly_deduction_check(self, md_check):
        if md_check is None:
            return

        cyberlife_md = getattr(md_check, "system_monthly_deduction", None)
        calculated_md = getattr(md_check, "md_check_calculated_deduction", None)
        self.policy_info.set_value("cyberlife_md", format_currency(cyberlife_md, "$"))
        self.policy_info.set_value("calculated_md", format_currency(calculated_md, "$"))

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
        self.set_rate_warnings([])
        self.unimpaired_table.setRowCount(0)
        self.impaired_table.setRowCount(0)
        self.allocation_table.setRowCount(0)
        self._equalize_fund_tables()
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
        self.policy_info.set_value("grace_label", "In Grace" if policy.in_grace else "Not in Grace")
        self.policy_info.set_value("eff_date_label", format_date(policy.valuation_date))
        self.policy_info.set_value("policy_year_label", policy.policy_year)
        self.policy_info.set_value("att_age_label", policy.attained_age)
        self.policy_info.set_value("maturity_age", policy.age_at_maturity or "")
        self.policy_info.set_value("insured_dob", format_date(policy.primary_insured_birth_date))
        self.policy_info.set_value("cyberlife_md", format_currency(self._policy_cyberlife_monthly_deduction(policy), "$"))
        self.policy_info.set_value("policy_debt_label", format_currency(policy.policy_debt, "$"))
        self.policy_info.set_value("total_face_label", format_amount(policy.base_total_face_amount))
        self.policy_info.set_value("total_death_benefit_label", format_amount(policy.total_death_benefit))
        status_code = policy.premium_pay_status_code
        self.policy_info.set_value("status_label", f"{status_code} - {policy.premium_pay_status_description}")
        db_option = {"1": "A-Level", "2": "B-Increasing", "3": "C-ROP"}.get(str(policy.db_option_code or ""), "")
        self.policy_info.set_value("db_option_label", db_option if policy.is_advanced_product else "")
        self.policy_info.set_value(
            "guar_int_rate_label", self._format_rate(policy.guaranteed_interest_rate))

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

    @staticmethod
    def _policy_cyberlife_monthly_deduction(policy):
        if hasattr(policy, "mv_monthly_deduction"):
            try:
                return policy.mv_monthly_deduction(0)
            except TypeError:
                return policy.mv_monthly_deduction()
            except Exception:
                return None
        return getattr(policy, "system_monthly_deduction", None)

    @staticmethod
    def _format_rate(rate) -> str:
        """CyberLife stores some rates percent-form (3.0) and some decimal
        (0.06) — values above 1 are already percentages."""
        if rate is None:
            return ""
        value = float(rate)
        return f"{value:.2f}%" if value > 1 else f"{value * 100:.2f}%"

    def _populate_value_groups(self, policy):
        definition = "GP" if policy.gpt_cvat == "GPT" else policy.gpt_cvat
        self.fund_values.set_value("fund_account_value", format_currency(policy.mv_av(0), "$"))
        self.fund_values.set_value("shadow_account_value", format_currency(policy.gav, "$"))
        # Sweep Account Min: DB2 source still unknown (work laptop item) — the
        # Input tab carries an editable override meanwhile. "—" = not loaded.
        self.fund_values.set_value("sweep_account_min", "—")
        self.fund_values.set_value(
            "guaranteed_int_rate", self._format_rate(policy.guaranteed_interest_rate))
        self.account_values.set_value("deemed_cash_value", format_currency(policy.mv_av(0), "$"))
        self.account_values.set_value("nsp", format_currency(self._nsp_total(policy), "$"))
        for attr in ["deemed_cash_value", "nsp"]:
            self._set_group_field_visible(self.account_values, attr, definition == "CVAT")

        self.premium_values.set_value("premium_ytd", format_currency(policy.premium_ytd, "$"))
        self.premium_values.set_value("premium_td", format_currency(policy.premium_td, "$"))
        self.premium_values.set_value("withdrawal_td", format_currency(policy.total_withdrawals, "$"))
        self.premium_values.set_value("accum_minimum", format_currency(policy.accumulated_mtp_target, "$"))
        self.premium_values.set_value("map_cease_date", format_date(policy.map_date))
        self.premium_values.set_value("monthly_mtp", format_currency(policy.mtp, "$"))
        self.premium_values.set_value("commission_target_premium", format_currency(policy.ctp, "$"))

        # Loan balances = principal + accrued; the charge rate shows only
        # when the loan exists.
        def _balance(principal, accrued):
            total = Decimal(str(principal or 0)) + Decimal(str(accrued or 0))
            return total

        def _rate_text(rate, has_loan: bool) -> str:
            return self._format_rate(rate) if has_loan else ""

        fixed = _balance(policy.total_regular_loan_principal, policy.total_regular_loan_accrued)
        pref = _balance(policy.total_preferred_loan_principal, policy.total_preferred_loan_accrued)
        vbl = _balance(policy.total_variable_loan_principal, policy.total_variable_loan_accrued)
        self.loan_values.set_value("fixed_loan_balance", format_currency(fixed, "$"))
        self.loan_values.set_value("pref_loan_balance", format_currency(pref, "$"))
        self.loan_values.set_value("vbl_loan_balance", format_currency(vbl, "$"))
        self.loan_values.set_value(
            "fixed_loan_rate", _rate_text(policy.fixed_loan_interest_rate, fixed > 0))
        self.loan_values.set_value(
            "pref_loan_rate", _rate_text(policy.preferred_loan_interest_rate, pref > 0))
        self.loan_values.set_value("vbl_loan_rate", "")

        self.tax_values.set_value("cost_basis", format_currency(policy.cost_basis, "$"))
        self.tax_values.set_value("seven_pay_start_date", format_date(policy.tamra_7pay_start_date))
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
        # Unimpaired = free fund value (CSV); Impaired = loan-collateralized
        # portion. The two together reconcile to Account Value.
        self._fill_fund_table(self.unimpaired_table, self._current_fund_values_by_fund(policy))
        self._fill_fund_table(self.impaired_table, self._impaired_fund_values_by_fund(policy))
        self._fill_allocation_table(policy)
        self._equalize_fund_tables()

    def _fill_allocation_table(self, policy):
        """Premium allocation % by fund (IUL — empty on declared-rate plans)."""
        try:
            allocations = policy.get_premium_allocation_dict()
        except Exception:
            allocations = {}
        self._fill_allocation_from_dict(allocations)

    def _fill_allocation_from_dict(self, allocations: dict):
        rows = [(fund, pct) for fund, pct in sorted(allocations.items())
                if self._is_nonzero(pct)]
        # DB2 FND_ALC_PCT arrives percent- or decimal-form; normalize by total.
        total = sum(float(pct) for _, pct in rows)
        scale = 1.0 if total > 1.5 else 100.0
        self.allocation_table.setRowCount(len(rows))
        for row, (fund, pct) in enumerate(rows):
            self._set_table_item(self.allocation_table, row, 0, self._fund_label(fund))
            self._set_table_item(self.allocation_table, row, 1, f"{float(pct) * scale:.2f}%")
        self._fit_fund_table(self.allocation_table)

    def _fill_fund_table(self, table, fund_values):
        rows = [(fund, value) for fund, value in sorted(fund_values.items()) if self._is_nonzero(value)]
        table.setRowCount(len(rows))
        for row, (fund, value) in enumerate(rows):
            self._set_table_item(table, row, 0, self._fund_label(fund))
            self._set_table_item(table, row, 1, format_currency(value, "$"))
        self._fit_fund_table(table)

    def _fund_label(self, fund_id: str) -> str:
        """The bare fund ID — descriptions live in the Index Allocations
        dialog, not these compact tables."""
        return str(fund_id or "").strip()

    def _impaired_fund_values_by_fund(self, policy):
        try:
            return policy.get_loan_values_dict()
        except Exception:
            return {}

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

        as_of = getattr(self, "_as_of", None)
        for label, kind, item in items:
            matured = coverage_or_benefit_matured(item, as_of)
            btn = QPushButton(label)
            # Matured coverages/benefits get a paler look but stay clickable.
            btn.setStyleSheet(VALUE_BUTTON_MATURED_STYLE if matured else VALUE_BUTTON_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip("Already matured — click for details" if matured else "Click for details")
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

    def _set_table_item(self, table, row: int, col: int, value):
        item = QTableWidgetItem(str(value) if value is not None else "")
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        table.setItem(row, col, item)

    @staticmethod
    def _is_nonzero(value) -> bool:
        try:
            return Decimal(str(value or 0)) != 0
        except Exception:
            return bool(value)
