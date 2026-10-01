"""Policy tab for the Illustration app."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from suiteview.illustration.models.policy_data import JointLives
from suiteview.polview.ui.formatting import format_amount, format_currency, format_date
from suiteview.polview.ui.widgets import FixedHeaderTableWidget, StyledInfoTableGroup
from suiteview.polview.models.cl_polrec.policy_translations import PREMIUM_PAY_STATUS_CODES
from suiteview.ui.signals import muted_signals

from .record_editing import FundValueDelegate, RecordDateInput

from .styles import (
    FUND_TABLE_STYLE,
    GROUP_STYLE,
    GRAY_DARK,
    PURPLE_BG,
    PURPLE_DARK,
    VALUE_BUTTON_MATURED_STYLE,
    VALUE_BUTTON_STYLE,
)
from suiteview.polview.models.policy_sections.lookup import policy_attr, policy_hasattr

# The CVAT deemed cash value lives on CyberLife's 93 segment, not in DB2; the
# user enters it on the Input tab next to Conform to TAMRA.
_DCV_NOT_IN_DB2 = "Not in DB2 — Input tab"


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


def show_detail_dialog(parent: QWidget, title: str, rows) -> None:
    """Modal "Coverage Detail" / "Benefit Detail" card: bold labels, selectable values.

    Shared by the UL Policy tab's coverage/benefit buttons and the par WL Policy page.
    """
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(420)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    grid = QGridLayout()
    grid.setHorizontalSpacing(14)
    grid.setVerticalSpacing(4)
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


class IllustrationPolicyTab(QWidget):
    """Initial Illustration Policy tab."""

    rollback_amount_requested = pyqtSignal(str, object, float)
    rollback_dbo_requested = pyqtSignal(str)
    rollback_shadow_requested = pyqtSignal(float)
    rollback_account_requested = pyqtSignal(float)
    record_value_requested = pyqtSignal(str, object)
    record_funds_requested = pyqtSignal(object)
    record_drafts_changed = pyqtSignal(bool)

    # Fund mini-tables grow with their row count up to this many visible rows,
    # then scroll. Local IUL policies top out around 8 index strategies
    # (UE209026), so 10 covers real plans without reserving empty space.
    _FUND_TABLE_MAX_VISIBLE_ROWS = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._policy = None
        self._coverages = []
        self._benefits = []
        self._rollback_editing = False
        self._rollback_editor = None
        self._record_editors = {}
        self._record_snapshot = None
        self._record_key = None
        self._fund_drafts = {}
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
        self.rollback_dbo_combo = QComboBox()
        for code, label in (("A", "A - Level"), ("B", "B - Increasing"), ("C", "C - Return of Premium")):
            self.rollback_dbo_combo.addItem(label, code)
        self.rollback_dbo_combo.setFixedHeight(20)
        self.rollback_dbo_combo.setEnabled(False)
        self.rollback_dbo_combo.setToolTip(
            "Death-benefit option for this illustration only; does not change the policy record.")
        self.rollback_dbo_combo.activated.connect(
            lambda: self.rollback_dbo_requested.emit(self.rollback_dbo_combo.currentData()))
        self.policy_info.set_field_editor("db_option_label", self.rollback_dbo_combo)
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
        self.rollback_edit_note = QLabel("Click a coverage or benefit to edit its Amount for this illustration.")
        self.rollback_edit_note.setWordWrap(True)
        cov_layout.addWidget(self.rollback_edit_note)
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
        from .value_rollback import ScenarioAmountInput
        self.account_value_input = ScenarioAmountInput(signed=True)
        self.shadow_value_input = ScenarioAmountInput(signed=True)
        self.account_value_input.setToolTip(
            "Defaults to the selected valuation's account value. Enter an illustration "
            "assumption and press Enter or leave the field to apply it.")
        self.shadow_value_input.setToolTip(
            "Shadow account value for this illustration. If a historical value cannot "
            "be recovered, enter it explicitly; zero is a valid entry.")
        self.account_value_input.amount_committed.connect(self.rollback_account_requested.emit)
        self.shadow_value_input.amount_committed.connect(self.rollback_shadow_requested.emit)
        self.fund_values.set_field_editor("fund_account_value", self.account_value_input)
        self.fund_values.set_field_editor("shadow_account_value", self.shadow_value_input)

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
        self.historical_funds_notice = QLabel(
            "Historical total AV only; fund/bucket balances are not reconstructed. "
            "Allocations remain forward-projection assumptions.")
        self.historical_funds_notice.setWordWrap(True)
        self.historical_funds_notice.setStyleSheet(
            "color: #777777; font-style: italic; font-size: 10px;")
        self.historical_funds_notice.setVisible(False)
        self.fund_values.layout().insertWidget(2, self.historical_funds_notice)
        self.fund_edit_controls = QWidget()
        fund_edit_row = QHBoxLayout(self.fund_edit_controls)
        fund_edit_row.setContentsMargins(0, 0, 0, 0)
        fund_edit_row.setSpacing(4)
        self.fund_edit_note = QLabel("Double-click values to edit; fund IDs are locked.")
        self.fund_edit_note.setWordWrap(True)
        self.fund_edit_note.setStyleSheet("color: #60368B; font-size: 10px;")
        self.fund_edit_note.setToolTip(
            "Fund balances, Account Value and loan principal are independent assumptions. "
            "Edit Account Value separately to change the projection's starting total; "
            "impaired fund edits do not change loan principal.")
        fund_edit_row.addWidget(self.fund_edit_note, 1)
        self.apply_funds_button = QPushButton("Apply")
        self.reset_funds_button = QPushButton("Reset")
        for button in (self.apply_funds_button, self.reset_funds_button):
            button.setStyleSheet(VALUE_BUTTON_STYLE + (
                "QPushButton:disabled { background: #EEEEEE; color: #888888; "
                "border: 1px solid #BBBBBB; }"))
            button.setFixedHeight(22)
            fund_edit_row.addWidget(button)
        self.apply_funds_button.clicked.connect(self._apply_fund_edits)
        self.reset_funds_button.clicked.connect(self.reset_fund_edits)
        self.fund_values.layout().insertWidget(3, self.fund_edit_controls)
        self._fund_tables = {
            "fund_values": self.unimpaired_table,
            "impaired_fund_values": self.impaired_table,
            "premium_allocations": self.allocation_table,
        }
        for name, table in self._fund_tables.items():
            inner = table._data_table
            inner.setItemDelegateForColumn(
                1, FundValueDelegate(percent=name == "premium_allocations", parent=inner))
            inner.cellChanged.connect(
                lambda row, col, key=name: self._fund_cell_changed(key, row, col))

        self.premium_values = self._make_value_group("Premiums and Targets", [
            ("Premium YTD", "premium_ytd"),
            ("Premium TD", "premium_td"),
            ("Withdrawal TD", "withdrawal_td"),
            ("Accum Minimum", "accum_minimum"),
            ("MAP Cease Date", "map_cease_date"),
            ("Monthly MTP", "monthly_mtp"),
            ("Commission Target Premium", "commission_target_premium"),
        ])
        self.loan_values = StyledInfoTableGroup("Loans", columns=2, show_table=False)
        self.loan_values.setStyleSheet(GROUP_STYLE)
        for label, attr, rate_attr in [
            ("Reg fixed loan Princ", "regular_loan_principal", "fixed_loan_rate"),
            ("Reg fixed loan Int", "regular_loan_accrued", None),
            ("Pref fixed loan Princ", "preferred_loan_principal", "pref_loan_rate"),
            ("Pref fixed loan Int", "preferred_loan_accrued", None),
            ("Var loan Princ", "variable_loan_principal", "vbl_loan_rate"),
            ("Var loan Int", "variable_loan_accrued", None),
        ]:
            self.loan_values.add_field(label, attr, 128, 95)
            if rate_attr:
                self.loan_values.add_field("Rate", rate_attr, 28, 55)
            else:
                spacer = attr + "_spacer"
                self.loan_values.add_field("", spacer, 1, 1)
                self._set_group_field_visible(self.loan_values, spacer, False)
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
            ("Deemed Cash Value", "deemed_cash_value"),
            ("NSP", "nsp"),
            ("Guideline Single", "guideline_single"),
            ("Guideline Level", "guideline_level"),
            ("Accum GLP", "accum_glp"),
        ])
        tax_row.addWidget(self.tax_values, 2)
        tax_row.addWidget(self.mec_values, 1)
        layout.addLayout(tax_row)
        self._setup_record_editors()
        self.set_value_editors_enabled(False)

        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _setup_record_editors(self):
        from .value_rollback import ScenarioAmountInput

        fields = [
            (self.policy_info, "status_label", "premium_pay_status_code", "status"),
            (self.premium_values, "premium_ytd", "premiums_ytd", "amount"),
            (self.premium_values, "premium_td", "premiums_paid_to_date", "amount"),
            (self.premium_values, "withdrawal_td", "withdrawals_to_date", "amount"),
            (self.premium_values, "accum_minimum", "accumulated_mtp", "amount"),
            (self.premium_values, "map_cease_date", "map_cease_date", "date"),
            (self.premium_values, "monthly_mtp", "mtp", "amount"),
            (self.premium_values, "commission_target_premium", "ctp", "amount"),
            (self.tax_values, "is_mec", "is_mec", "bool"),
            (self.tax_values, "cost_basis", "cost_basis", "amount"),
            (self.tax_values, "seven_pay_start_date", "tamra_7pay_start_date", "date"),
            (self.tax_values, "seven_pay_cash_value", "tamra_7pay_cash_value", "amount"),
            (self.tax_values, "seven_pay_premium", "tamra_7pay_level", "amount"),
            (self.tax_values, "seven_yr_lowest_db", "tamra_7year_lowest_db", "amount"),
            (self.mec_values, "guideline_single", "gsp", "amount"),
            (self.mec_values, "guideline_level", "glp", "amount"),
            (self.mec_values, "accum_glp", "accumulated_glp", "amount"),
            (self.loan_values, "fixed_loan_rate", "regular_loan_charge_rate", "rate"),
            (self.loan_values, "pref_loan_rate", "preferred_loan_charge_rate", "rate"),
            (self.loan_values, "vbl_loan_rate", "variable_loan_charge_rate", "rate"),
        ]
        for field in (
            "regular_loan_principal", "regular_loan_accrued",
            "preferred_loan_principal", "preferred_loan_accrued",
            "variable_loan_principal", "variable_loan_accrued",
        ):
            fields.append((self.loan_values, field, field, "amount"))
        for index in range(7):
            fields.append((self.tax_values, f"tamra_y{index + 1}",
                           f"tamra_7year_contributions.{index}", "amount"))
        for group, attr, name, kind in fields:
            if kind in ("bool", "status"):
                editor = QComboBox()
                editor.setFixedHeight(20)
                editor.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                editor.setMinimumContentsLength(8)
                choices = (
                    [(False, "No"), (True, "Yes")] if kind == "bool" else
                    [(key, f"{key} - {value}") for key, value in PREMIUM_PAY_STATUS_CODES.items()])
                for value, label in choices:
                    editor.addItem(label, value)
                editor.activated.connect(
                    lambda _index, key=name, control=editor:
                    self.record_value_requested.emit(key, control.currentData()))
            elif kind == "date":
                editor = RecordDateInput()
                editor.value_committed.connect(
                    lambda value, key=name: self.record_value_requested.emit(key, value))
            else:
                editor = ScenarioAmountInput(signed=True)
                if kind == "rate":
                    editor.setPrefix("")
                    editor.setSuffix("%")
                    editor.setDecimals(4)
                    editor.setMinimumWidth(65)
                    editor.setSpecialValueText("Not set")
                editor.amount_committed.connect(
                    lambda value, key=name, rate=kind == "rate":
                    self.record_value_requested.emit(key, value / 100 if rate else value))
            editor.setToolTip("Edit this starting-record value for the illustration only.")
            group.set_field_editor(attr, editor)
            self._record_editors[name] = (group, attr, kind, editor)

    def set_record_values(self, policy):
        values = getattr(policy, "values", policy)
        key = (
            policy.policy_number,
            policy.company_code,
            policy.region,
            values.valuation_date,
        )
        if key != self._record_key:
            self._fund_drafts.clear()
        self._record_key = key
        self._record_snapshot = policy
        for name, (group, attr, kind, editor) in self._record_editors.items():
            value = (
                policy.tamra_7year_contributions[int(name.rsplit(".", 1)[1])]
                if name.startswith("tamra_7year_contributions.") else getattr(policy, name))
            if kind == "date":
                editor.set_value(value)
                text = format_date(value)
            elif kind in ("bool", "status"):
                index = editor.findData(value)
                if index < 0 and value is not None:
                    editor.addItem(str(value), value)
                    index = editor.count() - 1
                editor.setCurrentIndex(index)
                text = editor.currentText()
            else:
                editor.set_amount(value * 100 if kind == "rate" and value is not None else value)
                text = self._format_rate(value) if kind == "rate" else format_currency(value, "$")
            group.set_value(attr, text)
        self._render_record_funds()
        definition = "GP" if policy.def_of_life_ins == "GPT" else policy.def_of_life_ins
        for attr in ("guideline_single", "guideline_level", "accum_glp"):
            self._set_group_field_visible(self.mec_values, attr, definition == "GP")

    def _render_record_funds(self):
        if self._record_snapshot is None:
            return
        for name, table in self._fund_tables.items():
            values = dict(getattr(self._record_snapshot, name))
            values.update(self._fund_drafts.get(name, {}))
            inner = table._data_table
            with muted_signals(inner):
                table.setRowCount(len(values))
                for row, (fund, value) in enumerate(sorted(values.items())):
                    self._set_table_item(table, row, 0, fund)
                    number = value * 100 if name == "premium_allocations" else value
                    self._set_table_item(table, row, 1, f"{number:,.2f}" + (
                        "%" if name == "premium_allocations" else ""))
                    table.item(row, 1).setData(Qt.ItemDataRole.UserRole, number)
            self._fit_fund_table(table)
        self._equalize_fund_tables()
        self._set_fund_editability()
        self._refresh_fund_drafts()

    def _set_fund_editability(self):
        for table in self._fund_tables.values():
            inner = table._data_table
            with muted_signals(inner):
                inner.setEditTriggers(
                    QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
                    if self._rollback_editing else QAbstractItemView.EditTrigger.NoEditTriggers)
                for row in range(table.rowCount()):
                    item = table.item(row, 1)
                    if item is not None:
                        flags = item.flags() & ~Qt.ItemFlag.ItemIsEditable
                        item.setFlags(flags | Qt.ItemFlag.ItemIsEditable if self._rollback_editing else flags)

    def _fund_cell_changed(self, name, row, column):
        if not self._rollback_editing or column != 1 or self._record_snapshot is None:
            return
        table = self._fund_tables[name]
        fund = table.item(row, 0).text()
        value = table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        if value is None:
            return
        value = value / 100 if name == "premium_allocations" else value
        original = getattr(self._record_snapshot, name)[fund]
        draft = self._fund_drafts.setdefault(name, {})
        if value == original:
            draft.pop(fund, None)
        else:
            draft[fund] = value
        if not draft:
            self._fund_drafts.pop(name, None)
        self._refresh_fund_drafts()

    def has_pending_record_changes(self):
        return bool(self._fund_drafts)

    def _refresh_fund_drafts(self):
        dirty = self.has_pending_record_changes()
        self.apply_funds_button.setEnabled(dirty and self._rollback_editing)
        self.reset_funds_button.setEnabled(dirty and self._rollback_editing)
        self.fund_edit_note.setText(
            "Unapplied values - Apply or Reset before Run/Save. Allocations must total 100%."
            if dirty else "Double-click values; IDs locked. AV and loans are edited separately.")
        self.record_drafts_changed.emit(dirty)

    def _apply_fund_edits(self):
        values = {}
        for name, draft in self._fund_drafts.items():
            values[name] = {**getattr(self._record_snapshot, name), **draft}
        self.record_funds_requested.emit(values)

    def reset_fund_edits(self):
        self._fund_drafts.clear()
        self._render_record_funds()

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
            ("Joint Insured", "joint_insured_label"),
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
            ("COI Basis", "coi_basis_label"),
        ]
        for label, attr in fields:
            self.policy_info.add_field(label, attr, 110, 120 if attr == "joint_label" else 100)
        for attr in self._JOINT_ONLY_FIELDS:
            self._set_group_field_visible(self.policy_info, attr, False)

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
        self.set_rollback_editing(False)
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

        self._coverages = list(policy.coverages.get_coverages())
        self._benefits = list(policy.benefits.get_benefits())
        self._as_of = policy_attr(policy, "valuation_date", None) or date.today()
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
    _JOINT_ONLY_FIELDS = ("joint_insured_label", "coi_basis_label")

    def _show_joint_lives(self, lives) -> None:
        """Second-to-die: the joint insured and each insured's own extras.

        ``lives`` is a JointLives, or an error message when the policy's joint
        data could not be read (shown, never hidden).
        """
        info = self.policy_info
        for attr in self._JOINT_ONLY_FIELDS:
            self._set_group_field_visible(info, attr, True)
        info.set_value("coi_basis_label", "Joint (VP/MS)")
        if isinstance(lives, str):
            info.set_value("joint_insured_label", lives)
            return
        joint = lives.joint
        info.set_value(
            "joint_insured_label",
            f"{self._sex_desc(joint.sex)} / {joint.rate_class} / age {joint.issue_age}")

        def extras(flat: bool) -> str:
            return "; ".join(
                f"{r.person}: {r.description}" for r in lives.ratings
                if (r.type_code in ("2", "4")) == flat) or "None"

        info.set_value("table_rating", extras(flat=False))
        info.set_value("flat_extra", extras(flat=True))
        info.set_value("flat_cease_date", "")

    def load_data_from_snapshot(self, snapshot):
        """Populate the Policy tab from a saved case's frozen policy data.

        The grey 'unavailable' overlay is retired for snapshots — the tab is
        fully rendered from what was captured. The caller shows the red
        `set_snapshot_banner(...)` statement so frozen data is never mistaken
        for live."""
        self.set_snapshot_notice(None)
        self.set_rollback_editing(False)
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

    def set_rollback_editing(
        self, enabled: bool, db_option: str | None = None, *,
        account_value: float | None = None, shadow_value: float | None = None,
        historical: bool = False,
    ):
        self.set_value_editors_enabled(enabled)
        self.account_value_input.set_amount(account_value)
        self.shadow_value_input.set_amount(shadow_value)
        self._close_rollback_editor()
        if db_option is not None:
            self.rollback_dbo_combo.setCurrentIndex(
                self.rollback_dbo_combo.findData(db_option))
        self.rollback_edit_note.setText(
            "Click a coverage or benefit to edit its Amount for this illustration. "
            + ("Historical amounts and DB option are not automatically recovered."
               if historical else "The loaded policy record is not changed."))
        self.rollback_edit_note.setStyleSheet(
            "color: #60368B; font-weight: bold;" if historical else
            "color: #777777; font-style: italic;")

    def set_value_editors_enabled(self, enabled: bool):
        from suiteview.illustration.models.app_settings import get_illustration_settings

        visible = get_illustration_settings().rollback_enabled
        enabled = enabled and visible
        self._rollback_editing = enabled
        self.rollback_dbo_combo.setEnabled(enabled)
        self.account_value_input.setEnabled(enabled)
        self.shadow_value_input.setEnabled(enabled)
        self.policy_info.set_field_editable("db_option_label", visible)
        self.fund_values.set_field_editable("fund_account_value", visible)
        self.fund_values.set_field_editable("shadow_account_value", visible)
        self.rollback_edit_note.setVisible(visible)
        for _name, (group, attr, _kind, editor) in self._record_editors.items():
            editor.setEnabled(enabled)
            group.set_field_editable(attr, visible)
        self.fund_edit_controls.setVisible(visible)
        self._set_fund_editability()
        if not visible:
            self._fund_drafts.clear()
        self._refresh_fund_drafts()
        if not enabled:
            self._close_rollback_editor()

    def _close_rollback_editor(self):
        editor = self._rollback_editor
        self._rollback_editor = None
        if editor is not None:
            editor.close()

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
        self.rollback_dbo_combo.setCurrentIndex(self.rollback_dbo_combo.findData(s.db_option))
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
            if base_seg.joint_lives is not None:
                info.set_value("joint_label", "Joint Second to Die")
                self._show_joint_lives(base_seg.joint_lives)
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
        self.account_value_input.set_amount(s.account_value)
        self.shadow_value_input.set_amount(
            None if s.rollback_requires_shadow_value else s.shadow_account_value)
        self.fund_values.set_value("sweep_account_min", "—")
        self.fund_values.set_value(
            "guaranteed_int_rate", self._format_rate(s.guaranteed_interest_rate))

        # CVAT-only values. The deemed cash value is not in DB2 (93 segment,
        # CyberLife Online) — it is entered on the Input tab, never shown as the
        # account value. NSP was not captured, so it stays blank.
        self.mec_values.set_value("deemed_cash_value", _DCV_NOT_IN_DB2)
        self.mec_values.set_value("nsp", "")
        for attr in ["deemed_cash_value", "nsp"]:
            self._set_group_field_visible(self.mec_values, attr, definition == "CVAT")

        self.premium_values.set_value("premium_ytd", format_currency(s.premiums_ytd, "$"))
        self.premium_values.set_value("premium_td", format_currency(s.premiums_paid_to_date, "$"))
        self.premium_values.set_value("withdrawal_td", format_currency(s.withdrawals_to_date, "$"))
        self.premium_values.set_value("accum_minimum", format_currency(s.accumulated_mtp, "$"))
        self.premium_values.set_value("map_cease_date", format_date(s.map_cease_date))
        self.premium_values.set_value("monthly_mtp", format_currency(s.mtp, "$"))
        self.premium_values.set_value("commission_target_premium", format_currency(s.ctp, "$"))

        vbl = Decimal(str(s.variable_loan_principal or 0)) + Decimal(str(s.variable_loan_accrued or 0))
        for field in (
            "regular_loan_principal", "regular_loan_accrued",
            "preferred_loan_principal", "preferred_loan_accrued",
            "variable_loan_principal", "variable_loan_accrued",
        ):
            self.loan_values.set_value(field, format_currency(getattr(s, field), "$"))
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
        self.tax_values.set_value("seven_pay_cash_value", format_currency(s.tamra_7pay_cash_value, "$"))
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
        self._fill_fund_table(self.impaired_table, s.impaired_fund_values)
        self._fill_allocation_from_dict(dict(s.premium_allocations or {}))
        self.historical_funds_notice.setText(
            "Manually entered total AV; fund balances are not reconstructed. "
            "Allocations remain forward-projection assumptions."
            if s.starting_account_value_is_manual else
            "Historical total AV only; fund/bucket balances are not reconstructed. "
            "Allocations remain forward-projection assumptions.")
        self.historical_funds_notice.setVisible(
            (s.rollback_date is not None or s.starting_account_value_is_manual)
            and not s.fund_values)
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
                cola_indicator="1" if seg.is_cola else "0",
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
        benefit type code stands in for the button label when no form number
        was captured."""
        views = []
        for b in snapshot.benefits:
            views.append(SimpleNamespace(
                benefit_code=b.benefit_type or "",
                cov_pha_nbr=b.coverage_phase,
                benefit_type_cd=b.benefit_type,
                benefit_subtype_cd=b.benefit_subtype,
                benefit_desc="",
                form_number=b.form_number or "",
                issue_date=b.issue_date,
                pay_up_date=b.pay_up_date,
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
        self.historical_funds_notice.setVisible(False)
        for group in [
            self.policy_info,
            self.premium_values,
            self.loan_values,
            self.tax_values,
            self.mec_values,
            self.fund_values,
        ]:
            group.clear_info()
        for attr in self._JOINT_ONLY_FIELDS:
            self._set_group_field_visible(self.policy_info, attr, False)
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
        self.policy_info.set_value("plancode_label", policy.coverages.base_plancode)
        self.policy_info.set_value("market_org_label", policy.agents.servicing_market_org)
        self.policy_info.set_value("issue_state_label", policy.product.issue_state)
        self.policy_info.set_value("billing_mode_label", policy.billing.billing_mode)
        self.policy_info.set_value("premium_label", format_currency(policy.billing.modal_premium, "$"))
        self.policy_info.set_value("joint_label", policy.coverages.insured_lives_description)
        self.policy_info.set_value("suspense_label", f"{policy.status.suspense_code} - {policy.status.suspense_description}")
        self.policy_info.set_value("grace_label", "In Grace" if policy.status.in_grace else "Not in Grace")
        self.policy_info.set_value("eff_date_label", format_date(policy.values.valuation_date))
        self.policy_info.set_value("policy_year_label", policy.activity.policy_year)
        self.policy_info.set_value("att_age_label", policy.coverages.attained_age)
        self.policy_info.set_value("maturity_age", policy.coverages.age_at_maturity or "")
        self.policy_info.set_value("insured_dob", format_date(policy.persons.primary_insured_birth_date))
        self.policy_info.set_value("cyberlife_md", format_currency(self._policy_cyberlife_monthly_deduction(policy), "$"))
        self.policy_info.set_value("policy_debt_label", format_currency(policy.loans.policy_debt, "$"))
        self.policy_info.set_value("total_face_label", format_amount(policy.coverages.base_total_face_amount))
        self.policy_info.set_value("total_death_benefit_label", format_amount(policy.coverages.total_death_benefit))
        status_code = policy.status.premium_pay_status_code
        self.policy_info.set_value("status_label", f"{status_code} - {policy.status.premium_pay_status_description}")
        db_option = {"1": "A-Level", "2": "B-Increasing", "3": "C-ROP"}.get(str(policy.product.db_option_code or ""), "")
        self.policy_info.set_value("db_option_label", db_option if policy.product.is_advanced_product else "")
        self.rollback_dbo_combo.setCurrentIndex(
            self.rollback_dbo_combo.findData(
                {"1": "A", "2": "B", "3": "C"}.get(str(policy.product.db_option_code or ""))))
        self.policy_info.set_value(
            "guar_int_rate_label", self._format_rate(policy.product.guaranteed_interest_rate))

        if not base_cov:
            return

        self.policy_info.set_value("issue_date", format_date(base_cov.issue_date or policy.activity.issue_date))
        self.policy_info.set_value("maturity_date", format_date(base_cov.maturity_date))
        self.policy_info.set_value("issue_age", base_cov.issue_age)
        self.policy_info.set_value("sex", base_cov.sex_desc or base_cov.sex_code)
        self.policy_info.set_value("rateclass", base_cov.rate_class)
        self.policy_info.set_value("table_rating", base_cov.table_rating if base_cov.table_rating else "")
        self.policy_info.set_value("flat_extra", format_currency(base_cov.flat_extra, "$"))
        self.policy_info.set_value("flat_cease_date", format_date(base_cov.flat_cease_date) if base_cov.flat_extra else "")
        if base_cov.number_of_lives_code == "3":
            try:
                index = policy.coverages.cov_index_for_phase(base_cov.cov_pha_nbr)
                primary, joint = policy.rates.cov_joint_insureds(index)
                lives = JointLives(primary, joint, list(policy.rates.cov_joint_ratings(index)))
            except Exception as exc:
                lives = f"Unavailable: {exc}"
            self._show_joint_lives(lives)

    @staticmethod
    def _policy_cyberlife_monthly_deduction(policy):
        if policy_hasattr(policy, "mv_monthly_deduction"):
            mv_monthly_deduction = policy_attr(policy, "mv_monthly_deduction")
            try:
                return mv_monthly_deduction(0)
            except TypeError:
                return mv_monthly_deduction()
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
        definition = "GP" if policy.product.gpt_cvat == "GPT" else policy.product.gpt_cvat
        self.fund_values.set_value("fund_account_value", format_currency(policy.values.mv_av(0), "$"))
        self.account_value_input.set_amount(policy.values.mv_av(0))
        self.shadow_value_input.set_amount(policy.targets.shadow_account_value)
        self.fund_values.set_value(
            "shadow_account_value",
            format_currency(policy.targets.shadow_account_value, "$"),
        )
        # Sweep Account Min: DB2 source still unknown (work laptop item) — the
        # Input tab carries an editable override meanwhile. "—" = not loaded.
        self.fund_values.set_value("sweep_account_min", "—")
        self.fund_values.set_value(
            "guaranteed_int_rate", self._format_rate(policy.product.guaranteed_interest_rate))
        # The deemed cash value is not in DB2 — entered on the Input tab.
        self.mec_values.set_value("deemed_cash_value", _DCV_NOT_IN_DB2)
        self.mec_values.set_value("nsp", format_currency(self._nsp_total(policy), "$"))
        for attr in ["deemed_cash_value", "nsp"]:
            self._set_group_field_visible(self.mec_values, attr, definition == "CVAT")

        self.premium_values.set_value("premium_ytd", format_currency(policy.billing.premium_ytd, "$"))
        self.premium_values.set_value("premium_td", format_currency(policy.billing.premium_td, "$"))
        self.premium_values.set_value("withdrawal_td", format_currency(policy.values.total_withdrawals, "$"))
        self.premium_values.set_value("accum_minimum", format_currency(policy.targets.accumulated_mtp_target, "$"))
        self.premium_values.set_value("map_cease_date", format_date(policy.targets.map_date))
        self.premium_values.set_value("monthly_mtp", format_currency(policy.targets.mtp, "$"))
        self.premium_values.set_value("commission_target_premium", format_currency(policy.targets.ctp, "$"))

        # Loan balances = principal + accrued; the charge rate shows only
        # when the loan exists.
        def _balance(principal, accrued):
            total = Decimal(str(principal or 0)) + Decimal(str(accrued or 0))
            return total

        def _rate_text(rate, has_loan: bool) -> str:
            return self._format_rate(rate) if has_loan else ""

        fixed = _balance(policy.loans.total_regular_loan_principal, policy.loans.total_regular_loan_accrued)
        pref = _balance(policy.loans.total_preferred_loan_principal, policy.loans.total_preferred_loan_accrued)
        for field in (
            "regular_loan_principal", "regular_loan_accrued",
            "preferred_loan_principal", "preferred_loan_accrued",
            "variable_loan_principal", "variable_loan_accrued",
        ):
            self.loan_values.set_value(field, format_currency(getattr(policy.loans, "total_" + field), "$"))
        self.loan_values.set_value(
            "fixed_loan_rate", _rate_text(policy.loans.fixed_loan_interest_rate, fixed > 0))
        self.loan_values.set_value(
            "pref_loan_rate", _rate_text(policy.loans.preferred_loan_interest_rate, pref > 0))
        self.loan_values.set_value("vbl_loan_rate", "")

        self.tax_values.set_value("cost_basis", format_currency(policy.values.cost_basis, "$"))
        self.tax_values.set_value("seven_pay_start_date", format_date(policy.values.tamra_7pay_start_date))
        for year in range(1, 8):
            self.tax_values.set_value(f"tamra_y{year}", format_currency(policy.values.tamra_7pay_premium_paid(year), "$"))
        self.tax_values.set_value("seven_pay_cash_value", format_currency(policy.values.tamra_7pay_av, "$"))
        self.tax_values.set_value("seven_pay_premium", format_currency(policy.values.tamra_7pay_level, "$"))
        self.tax_values.set_value("seven_yr_lowest_db", format_currency(policy.values.tamra_7pay_specified_amount, "$"))
        self.tax_values.set_value("is_mec", "Yes" if policy.values.is_mec else "No")

        self.mec_values.set_value("policy_definition", definition)
        self.mec_values.set_value("guideline_single", format_currency(policy.targets.gsp, "$"))
        self.mec_values.set_value("guideline_level", format_currency(policy.targets.glp, "$"))
        self.mec_values.set_value("accum_glp", format_currency(policy.targets.accumulated_glp_target, "$"))
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
        values = getattr(policy, "values", policy)
        try:
            allocations = values.get_premium_allocation_dict()
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
        values = getattr(policy, "values", policy)
        try:
            return values.get_loan_values_dict()
        except Exception:
            return {}

    def _current_fund_values_by_fund(self, policy):
        values = getattr(policy, "values", policy)
        fund_values = {}
        try:
            buckets = values.get_fund_buckets(current_only=True)
            for bucket in buckets:
                fund_id = str(getattr(bucket, "fund_id", "") or "").strip()
                if not fund_id:
                    continue
                amount = getattr(bucket, "csv_amount", None) or Decimal("0")
                fund_values[fund_id] = fund_values.get(fund_id, Decimal("0")) + Decimal(str(amount))
        except Exception:
            try:
                fund_values = values.get_fund_values_dict()
            except Exception:
                fund_values = {}
        return fund_values

    def _nsp_total(self, policy):
        values = [policy.targets.nsp_base, policy.targets.nsp_other]
        return sum((Decimal(str(value)) for value in values if value is not None), Decimal("0"))

    def _set_group_field_visible(self, group, attr_name: str, visible: bool):
        if hasattr(group, "_labels") and attr_name in group._labels:
            group._labels[attr_name].setVisible(visible)
        if hasattr(group, "_fields") and attr_name in group._fields:
            editors = getattr(group, "_field_editors", {})
            if attr_name in editors:
                editor = editors[attr_name]
                editing = group._info_layout.indexOf(editor) >= 0
                editor.setVisible(visible and editing)
                group._fields[attr_name].setVisible(visible and not editing)
            else:
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
                widget.hide()
                widget.deleteLater()

    def _show_detail_dialog(self, kind: str, item):
        if self._rollback_editing:
            from .value_rollback import RollbackAmountEditor

            self._close_rollback_editor()
            rows = self._coverage_detail_rows(item) if kind == "coverage" else self._benefit_detail_rows(item)
            key = (
                item.cov_pha_nbr if kind == "coverage" else
                (item.cov_pha_nbr, item.benefit_type_cd, item.benefit_subtype_cd))
            amount = item.face_amount if kind == "coverage" else item.benefit_amount
            editor = RollbackAmountEditor(
                "Coverage Detail" if kind == "coverage" else "Benefit Detail",
                rows, amount, parent=self.window())
            editor.amount_applied.connect(
                lambda value: self.rollback_amount_requested.emit(kind, key, value))
            editor.closed.connect(lambda: self._rollback_editor_closed(editor))
            self._rollback_editor = editor
            editor.move(self.window().frameGeometry().center() - editor.rect().center())
            editor.show()
            editor.raise_()
            editor.activateWindow()
            return
        rows = self._coverage_detail_rows(item) if kind == "coverage" else self._benefit_detail_rows(item)
        show_detail_dialog(self, "Coverage Detail" if kind == "coverage" else "Benefit Detail", rows)

    def _rollback_editor_closed(self, editor):
        if editor is self._rollback_editor:
            self._rollback_editor = None

    def _coverage_detail_rows(self, cov):
        return [
            ("Phase:", cov.cov_pha_nbr),
            ("Form:", cov.form_number),
            ("Plancode:", cov.plancode),
            ("Added by COLA:", "Yes" if str(getattr(cov, "cola_indicator", "")).strip() == "1" else "No"),
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
            ("Pay Up Date:", format_date(benefit.pay_up_date)),
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
