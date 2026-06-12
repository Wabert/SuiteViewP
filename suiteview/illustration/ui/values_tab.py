"""Values tab for monthly illustration output."""

from __future__ import annotations

from typing import Iterable

import pandas as pd
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.policy_data import IllustrationPolicyData
from suiteview.ui.widgets.filter_table_view import FilterTableView

from .styles import PURPLE_BG, PURPLE_DARK, TAB_WIDGET_STYLE
from .values_inspector import MonthInspector
from .values_overview import (
    AccumulatedChargesChart,
    PolicyValueChart,
    ValuesOverview,
    build_chart_series,
    build_charge_bands,
)


# Double-clicking an Overview ledger cell drills into the detail tab where
# that value is calculated, pinned to the same month.
LEDGER_DRILL_TABS = {
    "Premium": "Apply Premium",
    "Withdrawals": "Summary",
    "Interest": "Accumulation",
    "Charges": "Monthly Deduction",
    "AV": "Policy Values",
    "SV": "Policy Values",
    "Death Benefit": "Ending Values",
    "GP Room": "TEFRA and TAMRA",
    "Status": "Testing",
}


# Display-only relabels applied to EVERY grid: compact, wrap-friendly forms of
# the long RERUN-derived names (DataFrame keys are unchanged — comparisons and
# exports still see the originals). Spaces let the wrapped headers break at
# word boundaries instead of letter stacks.
COMPACT_HEADER_LABELS = {
    # TEFRA and TAMRA
    "AccumGLP": "Accum GLP",
    "TEFRA_Limit": "TEFRA Limit",
    "Prem-WD": "Prem − WD",
    "ForceOut": "Force Out",
    "7PayPrem": "7Pay Prem",
    "New TAMRA Period": "New TAMRA Per",
    "7PayStartDate": "7Pay Start",
    "TAMRAMonth": "TAMRA Mth",
    "TAMRA_MonthOfYear": "TAMRA Mth of Yr",
    "TAMRA_Year": "TAMRA Yr",
    "Amount In 7-Pay": "Amt in 7Pay",
    "Lowest7YearFace": "Lowest 7Yr Face",
    "Value_for_NPT": "NPT Value",
    "NPT_NSP": "NPT NSP",
    "NPT_Premium": "NPT Prem",
    # Requested Premium
    "1035_Amount": "1035 Amt",
    "PlannedPremium": "Planned Prem",
    "PlannedPremiumMode": "Planned Mode",
    "Premium Frequency": "Prem Freq",
    "Premium Period": "Prem Period",
    "Scheduled Premium Due": "Sched Prem Due",
    "Scheduled Premium": "Sched Prem",
    "Payment Count For Policy Year": "Pmt Cnt Policy Yr",
    "Payment Count for TAMRA Year": "Pmt Cnt TAMRA Yr",
    # Loan Capitalize and Repay
    "Advance - Rg Ln Princ/Total": "Adv Reg Princ",
    "Advance - Rg Ln Int Accrued": "Adv Reg Accr",
    "Advance - Pf Ln Princ/Total": "Adv Pref Princ",
    "Advance - Pf Ln Int Accrued": "Adv Pref Accr",
    "Advance - Var Ln Princ/Total": "Adv Vbl Princ",
    "Advance - Var Ln Int Accrued": "Adv Vbl Accr",
    "Advance - Adv Reg LN Payoff": "Adv Reg Payoff",
    "Advance - Adv Pref LN Payoff": "Adv Pref Payoff",
    "Advance - LoanPayoff": "Adv Loan Payoff",
    "Arrears - PremToPayLoanInterest": "Prem to Pay Ln Int",
    "Arrears - From Lumpsum": "Repay fr Lumpsum",
    "Arrears - From Scheduled Prem": "Repay fr Sched Prem",
    "Arrears - LoanRepayFromForceout": "Repay fr Force Out",
    "Arrears - LoanRepayFromPremAndForceout": "Repay fr Prem & FO",
    "Arrears - Requested Loan Repayment": "Req Loan Repay",
    "Arrears - Total Loan Repayment Attempted": "Tot Repay Attempt",
    "Advance - Adv Reg LN Repay": "Adv Reg Repay",
    "Advance - Adv Pref LN Repay": "Adv Pref Repay",
    "Advance - Adv Total Loan Repayment": "Adv Tot Repay",
    "LNRepayLeftOver": "Repay Left Over",
    "TotalLoanReduction": "Tot Loan Reduction",
    "PolicyDebtDisplay": "Policy Debt",
    # Apply Premium
    "GP_Allowance0": "GP Alw 0",
    "NPT Allowance0": "NPT Alw 0",
    "TAMRA_Allowance0": "TAMRA Alw 0",
    "Annual Cap0": "Annual Cap 0",
    "Applied1035": "Applied 1035",
    "GP_Allowance1": "GP Alw 1",
    "NPT Allowance 1": "NPT Alw 1",
    "TAMRA_Allowance1": "TAMRA Alw 1",
    "Annual Cap1": "Annual Cap 1",
    "Lumpsum Remaining": "Lumpsum Remain",
    "vAppliedLumpsum": "Applied Lumpsum",
    "GP_Allowance2": "GP Alw 2",
    "NPT Allowance 2": "NPT Alw 2",
    "TAMRA_Allowance2": "TAMRA Alw 2",
    "Annual Cap2": "Annual Cap 2",
    "TAMRA_Level_Allowance_BOY": "TAMRA Lvl Alw BOY",
    "TAMRA_Level_Allowance_EOY": "TAMRA Lvl Alw EOY",
    "NPT_Level_Allowance": "NPT Lvl Alw",
    "GP_Level_Allowance": "GP Lvl Alw",
    "Scheduled Prem Cap": "Sched Prem Cap",
    "Levelized Max Premium": "Lvlized Max Prem",
    "Apply Levelized Premium": "Apply Lvlized Prem",
    "Scheduled Premium less Loan Repay": "Sched Prem less Repay",
    "AppliedScheduledPremium": "Applied Sched Prem",
    "AppliedTotalPremium": "Applied Total Prem",
    "PremTD": "Prem TD",
    "PremYTD": "Prem YTD",
    "CostBasis": "Cost Basis",
    "TotalPremLoad": "Total Prem Load",
    "NetPremium": "Net Premium",
    # Exception Premiums
    "Guideline Limit Reached": "GP Limit Reached",
    "vExceptionPremMode": "Exc Prem Mode",
    "GP_Exception_Prem_Gross": "Exc Prem Gross",
    "Exception_Prem_Discount": "Exc Prem Discount",
    "vGP_Exception_Prem": "Exception Prem",
    # Policy Values
    "Requested Loan": "Req Loan",
    "Loan Mode Effective": "Loan Mode Eff",
    "Scheduled Loan Amount": "Sched Loan Amt",
    "Remaining Distribution": "Remain Distrib",
    "vAppliedLoan": "Applied Loan",
    "AdvRegLNInt": "Adv Reg Ln Int",
    "PrefRegLNInt": "Pref Ln Int",
    "Total Rg Ln Princ": "Tot Reg Princ",
    "Total Pref Ln Princ": "Tot Pref Princ",
    "Total Vbl Ln Princ": "Tot Vbl Princ",
    # Accumulation
    "Fixed Ln Prinicple": "Fixed Ln Princ",
    "PolicyBonus": "Policy Bonus",
    "Declared Rate + Policy Bonus": "Declared + Bonus",
    "Blended Index Rate": "Blend Index Rate",
    "BlendedCreditingRate": "Blend Cred Rate",
    "BlendInterest": "Blend Interest",
    "Accrued Reg Ln Int": "Accr Reg Ln Int",
    "Accrued Pref Ln Int": "Accr Pref Ln Int",
    "Accured Vbl Ln Int": "Accr Vbl Ln Int",
    # Ending Values
    "EDBwoCORR": "EDB wo Corr",
    "EDB_CORR": "EDB Corr",
    "EDBwLNs": "EDB w Lns",
    "IllustrationAV": "Illus AV",
    "IllustrationInterestRate": "Illus Int Rate",
    "IllustrationLN": "Illus Loan",
    "IllustrationSV": "Illus SV",
    "IllustrationDB": "Illus DB",
    "PremiumOutlay": "Prem Outlay",
    "ForceOutDisplay": "Force Out",
    "LoanRepayFromPremDisplay": "Repay fr Prem",
    "LoanRepayDisplay": "Loan Repay",
    "DistributionFromPolicy": "Distrib fr Policy",
    "IllustrationGCO": "Illus GCO",
    # Testing
    "ScheduledPremLimitedByGP": "Sched Prem Ltd by GP",
    # Shadow Account (the Shadow prefix is redundant on its own tab)
    "Shadow_BAV": "BAV",
    "WD, Charges and ForceOuts": "WD Chg & FO",
    "Shadow SA": "SA",
    "Shadow_TPR": "TPR",
    "Shadow_TBL1TPR": "TBL1 TPR",
    "Shadow_TP": "Target Prem",
    "Applied Total Premium": "Applied Tot Prem",
    "Premium YTD": "Prem YTD",
    "Target Percent Prem": "TPP",
    "Excess Precent Prem": "EPP",
    "Target Prem Load": "Target Load",
    "Excess Prem Load": "Excess Load",
    "Shadow Premium Load": "Prem Load",
    "Shadow Net Prem": "Net Prem",
    "Shadow_NARAV": "NAR AV",
    "Shadow DB": "DB",
    "Shadow COIR": "COIR",
    "Shadow COIR + Sub": "COIR + Sub",
    "Shadow DBD Rate": "DBD Rate",
    "Shadow NAR": "NAR",
    "Shadow COI": "COI",
    "Shadow EPUR": "EPUR",
    "Shadow EPU": "EPU",
    "Shadow MFEE": "MFEE",
    "Shadow MD": "MD",
    "Shadow AV": "AV",
    "Shadow Int Rate": "Int Rate",
    "Shadow Interest": "Interest",
    "ShadowEAV": "EAV",
    "ShadowEAV_less_Debt": "EAV less Debt",
}


class IllustrationValuesTab(QWidget):
    """Tab that displays monthly illustration values in a filterable grid.

    Each group of columns lives on its own tab. Every tab leads with the four
    locator columns (Date / Year / Month / Attained Age) followed by that
    group's columns.
    """

    LIGHT_PURPLE = QColor("#E8DDF8")
    LEAD_COLUMNS = ["Date", "Year", "Month", "Attained Age"]
    SUMMARY_GROUP = "Summary"
    SUMMARY_COLUMNS = [
        "Monthly MTP",
        "Accum MTP",
        "GLP",
        "GSP",
        "AccumGLP",
        "Loan Int",
        "PolicyDebt",
        "Premium",
        "Premium Load",
        "mAV",
        "Face Amount",
        "Death Benefit",
        "COI Charge",
        "Rider Charge",
        "Benefit Charges",
        "EPU Fee",
        "Monthly Fee",
        "Monthly Deduction",
        "AV",
        "vGP_Exception_Prem",
        "FullSC",
        "Surrender Value",
        "New Loan",
        "Interest",
        "EA",
        "ES",
        "ELN",
    ]
    SUMMARY_HEADER_LABELS = {
        "Monthly MTP": "MTP",
        "Accum MTP": "AccumMTP",
        "PolicyDebt": "Loan Balance",
        "COI Charge": "Base COI",
        "Rider Charge": "Rider COI",
        "Benefit Charges": "Benefit COI",
        "EPU Fee": "EPU",
        "Monthly Fee": "MFEE",
        "Monthly Deduction": "MD",
        "vGP_Exception_Prem": "Exception Prem",
        "FullSC": "SC",
        "Surrender Value": "SV",
        "EA": "EAV",
        "ES": "ESV",
    }
    TESTING_GROUP = "Testing"
    TESTING_COLUMNS = [
        "7-Pay Yr 1",
        "7-Pay Yr 2",
        "7-Pay Yr 3",
        "7-Pay Yr 4",
        "7-Pay Yr 5",
        "7-Pay Yr 6",
        "7-Pay Yr 7",
        "MEC",
        "CVAT MEC",
        "7Pay MEC",
        "TEFRA Violation",
        "ScheduledPremLimitedByGP",
        "Accum MTP less Prem",
        "SNET Active",
        "Shadow Protection",
        "Positive SV",
        "AV-Loans > 0",
        "Exception Protection",
        "Termination ID",
        "Inforce?",
    ]
    TESTING_HEADER_LABELS = {
        "SNET Active": "SNET",
        "Exception Protection": "Exc Prem Protect",
    }
    MONTHLY_DEDUCTION_GROUP = "Monthly Deduction"
    APPLY_PREMIUM_GROUP = "Apply Premium"
    APPLY_PREMIUM_COLUMNS = [
        "GP_Allowance0",
        "NPT Allowance0",
        "TAMRA_Allowance0",
        "Annual Cap0",
        "Applied1035",
        "GP_Allowance1",
        "NPT Allowance 1",
        "TAMRA_Allowance1",
        "Annual Cap1",
        "Lumpsum Remaining",
        "vAppliedLumpsum",
        "GP_Allowance2",
        "NPT Allowance 2",
        "TAMRA_Allowance2",
        "Annual Cap2",
        "TAMRA_Level_Allowance_BOY",
        "TAMRA_Level_Allowance_EOY",
        "NPT_Level_Allowance",
        "GP_Level_Allowance",
        "Scheduled Prem Cap",
        "Levelized Max Premium",
        "Apply Levelized Premium",
        "Scheduled Premium less Loan Repay",
        "AppliedScheduledPremium",
        "AppliedTotalPremium",
        "PremTD",
        "PremYTD",
        "CostBasis",
        "Prem Under Target",
        "Prem Over Target",
        "TPP Rate",
        "EPP Rate",
        "Under Load",
        "Over Load",
        "Flat Load",
        "TotalPremLoad",
        "NetPremium",
    ]
    EXCEPTION_PREMIUM_GROUP = "Exception Premiums"
    EXCEPTION_PREMIUM_COLUMNS = [
        "Guideline Limit Reached",
        "vExceptionPremMode",
        "GP_Exception_Prem_Gross",
        "Exception_Prem_Discount",
        "vGP_Exception_Prem",
    ]
    POLICY_VALUES_GROUP = "Policy Values"
    POLICY_VALUES_COLUMNS = [
        "AV",
        "SCR Cov 1",
        "SCR Cov 2",
        "SCR Cov 3",
        "SC Cov 1",
        "SC Cov 2",
        "SC Cov 3",
        "FullSC",
        "LapseSV",
        "Requested Loan",
        "Loan Mode Effective",
        "Scheduled Loan Amount",
        "Remaining Distribution",
        "vAppliedLoan",
        "Gain",
        "New Reg LN",
        "New Pref LN",
        "AdvRegLNInt",
        "PrefRegLNInt",
        "Total Rg Ln Princ",
        "Total Pref Ln Princ",
        "Total Vbl Ln Princ",
        "AV Display",
    ]
    ACCUMULATION_GROUP = "Accumulation"
    ACCUMULATION_COLUMNS = [
        "# of Days",
        "PolicyBonus",
        "Fixed Ln Prinicple",
        "Reg Impaired Int",
        "Pref Impaired Int",
        "Declared Rate",
        "Declared Rate + Policy Bonus",
        "Unimpaired Int",
        "Declared Interest",
        "Blended Index Rate",
        "BlendedCreditingRate",
        "BlendInterest",
        "Reg Ln Princ",
        "Accrued Reg Ln Int",
        "Pref Ln Princ",
        "Accrued Pref Ln Int",
        "Vbl Ln Princ",
        "Accured Vbl Ln Int",
    ]
    SHADOW_ACCOUNT_GROUP = "Shadow Account"
    # Three columns collide with existing group columns ("# of Days",
    # "Prem Under Target", "Prem Over Target"); they carry unique DataFrame keys
    # here and are shown under their RERUN labels via SHADOW_ACCOUNT_HEADER_LABELS.
    SHADOW_ACCOUNT_COLUMNS = [
        "Shadow_BAV",
        "WD, Charges and ForceOuts",
        "Shadow SA",
        "Shadow_TPR",
        "Shadow_TBL1TPR",
        "Shadow_TP",
        "Applied Total Premium",
        "Premium YTD",
        "Shadow Prem Under Target",
        "Shadow Prem Over Target",
        "Target Percent Prem",
        "Excess Precent Prem",
        "Target Prem Load",
        "Excess Prem Load",
        "Shadow Premium Load",
        "Shadow Net Prem",
        "Shadow_NARAV",
        "Shadow DB",
        "Shadow COIR",
        "Shadow COIR + Sub",
        "Shadow DBD Rate",
        "Shadow NAR",
        "Shadow COI",
        "Shadow EPUR",
        "Shadow EPU",
        "Shadow MFEE",
        "Rider Charges",
        "Shadow MD",
        "Shadow AV",
        "Shadow # of Days",
        "Shadow Int Rate",
        "Eff Rate",
        "Shadow Interest",
        "ShadowEAV",
        "ShadowEAV_less_Debt",
    ]
    SHADOW_ACCOUNT_HEADER_LABELS = {
        "Shadow Prem Under Target": "Prem Under Target",
        "Shadow Prem Over Target": "Prem Over Target",
        "Shadow # of Days": "# of Days",
    }
    ENDING_VALUES_GROUP = "Ending Values"
    ENDING_VALUES_COLUMNS = [
        "EA",
        "ELN",
        "ES",
        "EDBwoCORR",
        "EDB_CORR",
        "EDBwLNs",
        "EDB",
        "IllustrationAV",
        "IllustrationInterestRate",
        "IllustrationLN",
        "IllustrationSV",
        "IllustrationDB",
        "PremiumOutlay",
        "ForceOutDisplay",
        "LoanRepayFromPremDisplay",
        "LoanRepayDisplay",
        "DistributionFromPolicy",
        "IllustrationGCO",
    ]
    # Withdrawals / DB Option Change / Increase-Decrease / Cov After Change /
    # MTP / CTP columns are built per projection by the _*_column_names()
    # builders — the Cov 1..3 / APB slots only appear for coverages that are
    # actually active somewhere in the run (same convention as the Monthly
    # Deduction per-coverage columns).
    WITHDRAWALS_GROUP = "Withdrawals"
    DBO_CHANGE_GROUP = "DB Option Change"
    FACE_CHANGE_GROUP = "Increase/Decrease"
    MTP_GROUP = "MTP"
    CTP_GROUP = "CTP"
    COV_AFTER_CHANGE_GROUP = "Cov After Change"
    TEFRA_TAMRA_GROUP = "TEFRA and TAMRA"
    TEFRA_TAMRA_COLUMNS = [
        "GSP",
        "GLP",
        "AccumGLP",
        "TEFRA_Limit",
        "Prem-WD",
        "ForceOut",
        "7PayPrem",
        "New TAMRA Period",
        "7PayStartDate",
        "TAMRAMonth",
        "TAMRA_MonthOfYear",
        "TAMRA_Year",
        "Amount In 7-Pay",
        "Lowest7YearFace",
        "Value_for_NPT",
        "NPT_NSP",
        "NPT_Premium",
    ]
    REQUESTED_PREMIUM_GROUP = "Requested Premium"
    REQUESTED_PREMIUM_COLUMNS = [
        "1035_Amount",
        "Lumpsum",
        "PlannedPremium",
        "PlannedPremiumMode",
        "Premium Frequency",
        "Premium Period",
        "Scheduled Premium Due",
        "Scheduled Premium",
        "Payment Count For Policy Year",
        "Payment Count for TAMRA Year",
    ]
    LOAN_CAPITALIZE_GROUP = "Loan Capitalize and Repay"
    LOAN_CAPITALIZE_COLUMNS = [
        "Advance - Rg Ln Princ/Total",
        "Advance - Rg Ln Int Accrued",
        "Advance - Pf Ln Princ/Total",
        "Advance - Pf Ln Int Accrued",
        "Advance - Var Ln Princ/Total",
        "Advance - Var Ln Int Accrued",
        "Advance - Adv Reg LN Payoff",
        "Advance - Adv Pref LN Payoff",
        "Advance - LoanPayoff",
        "Arrears - PremToPayLoanInterest",
        "Arrears - From Lumpsum",
        "Arrears - From Scheduled Prem",
        "Arrears - LoanRepayFromForceout",
        "Arrears - LoanRepayFromPremAndForceout",
        "Arrears - Requested Loan Repayment",
        "Arrears - Total Loan Repayment Attempted",
        "Advance - Adv Reg LN Repay",
        "Advance - Adv Pref LN Repay",
        "Advance - Adv Total Loan Repayment",
        "Rg Ln Princ",
        "Rg Ln Int",
        "Pf Ln Princ",
        "Pf Ln Int",
        "Var Ln Princ",
        "Var Ln Int",
        "LNRepayLeftOver",
        "TotalLoanReduction",
        "PolicyDebtDisplay",
    ]
    TAB_ORDER = [
        SUMMARY_GROUP,
        WITHDRAWALS_GROUP,
        DBO_CHANGE_GROUP,
        FACE_CHANGE_GROUP,
        COV_AFTER_CHANGE_GROUP,
        MTP_GROUP,
        CTP_GROUP,
        TEFRA_TAMRA_GROUP,
        REQUESTED_PREMIUM_GROUP,
        LOAN_CAPITALIZE_GROUP,
        APPLY_PREMIUM_GROUP,
        MONTHLY_DEDUCTION_GROUP,
        EXCEPTION_PREMIUM_GROUP,
        POLICY_VALUES_GROUP,
        ACCUMULATION_GROUP,
        ENDING_VALUES_GROUP,
        SHADOW_ACCOUNT_GROUP,
        TESTING_GROUP,
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_columns: list[str] = []
        self._coverage_columns: list[str] = []
        self._rate_columns: list[str] = []
        self._benefit_columns: list[str] = []
        self._rider_columns: list[str] = []
        self._monthly_deduction_columns: list[str] = []
        # Per-projection slot-driven groups (single coverage until a run shows more).
        self._withdrawals_columns = self._withdrawals_column_names([1])
        self._dbo_change_columns = self._dbo_change_column_names([1])
        self._face_change_columns = self._face_change_column_names([1])
        self._mtp_columns = self._mtp_column_names([1], False)
        self._ctp_columns = self._ctp_column_names([1], False)
        self._cov_after_change_columns = self._cov_after_change_column_names([1], False)
        self._tab_grids: dict[str, FilterTableView] = {}
        self._results: list[MonthlyState] = []
        self._inspected_row: int | None = None
        self._setup_ui()
        self.clear_results()

    def _setup_ui(self):
        from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QSplitter, QTreeWidget

        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        toggle_style = (
            f"QPushButton {{ background-color: #F3ECFC; color: {PURPLE_DARK};"
            " border: 1px solid #7E57C2; border-radius: 4px; padding: 1px 10px;"
            " min-height: 18px; font-size: 10px; font-weight: bold; }"
            "QPushButton:checked { background-color: #5E35A5; color: #FFD54F; }"
        )
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;"
        )
        top_row.addWidget(self.status_label)
        top_row.addStretch(1)
        self.nav_toggle = QPushButton("☰ Find Value")
        self.nav_toggle.setCheckable(True)
        self.nav_toggle.setStyleSheet(toggle_style)
        self.nav_toggle.setToolTip("Search every column across the value tabs and jump to it.")
        self.nav_toggle.toggled.connect(lambda on: self.navigator.setVisible(on))
        top_row.addWidget(self.nav_toggle)
        self.inspector_toggle = QPushButton("Inspect Month")
        self.inspector_toggle.setCheckable(True)
        self.inspector_toggle.setStyleSheet(toggle_style)
        self.inspector_toggle.setToolTip(
            "Explain the selected month: the full premium → deduction → interest waterfall."
        )
        self.inspector_toggle.toggled.connect(self._on_inspector_toggled)
        top_row.addWidget(self.inspector_toggle)
        layout.addLayout(top_row)

        self.body = QSplitter(Qt.Orientation.Horizontal, self)
        self.body.setHandleWidth(4)

        # ── Navigator rail: searchable stage → column tree ──
        self.navigator = QWidget(self)
        nav_layout = QVBoxLayout(self.navigator)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(4)
        self.nav_search = QLineEdit(self.navigator)
        self.nav_search.setPlaceholderText("Find a value…")
        self.nav_search.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #B79CDE; border-radius: 4px;"
            " padding: 2px 6px; font-size: 11px; color: #2A1458; }"
        )
        self.nav_search.textChanged.connect(self._filter_navigator)
        nav_layout.addWidget(self.nav_search)
        self.nav_tree = QTreeWidget(self.navigator)
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setUniformRowHeights(True)
        self.nav_tree.setIndentation(12)
        self.nav_tree.setStyleSheet(
            "QTreeWidget { background: white; border: 1px solid #B79CDE; font-size: 11px; }"
            "QTreeWidget::item { height: 16px; }"
            "QTreeWidget::item:selected { background: #E8DDF8; color: #2A1458; }"
        )
        self.nav_tree.itemClicked.connect(self._on_navigator_clicked)
        nav_layout.addWidget(self.nav_tree, 1)
        self.navigator.setVisible(False)
        self.body.addWidget(self.navigator)

        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)
        self.overview = ValuesOverview(self.tabs)
        self.overview.monthSelected.connect(self._inspect_month)
        self.overview.cellActivated.connect(self._drill_down)
        self.tabs.addTab(self.overview, "Overview")
        self.chart = PolicyValueChart(self.tabs)
        self.chart.yearClicked.connect(self._on_chart_year_clicked)
        self.tabs.addTab(self.chart, "Chart")
        self.charges_chart = AccumulatedChargesChart(self.tabs)
        self.tabs.addTab(self.charges_chart, "Charges")
        for title in self.TAB_ORDER:
            grid = FilterTableView(self.tabs)
            grid.set_search_visible(False)
            grid.apply_ledger_style()
            # Chronological ledger — no sort toggle; reclaiming the icon zone
            # keeps the columns tight.
            grid.set_sort_enabled(False)
            self._tab_grids[title] = grid
            self.tabs.addTab(grid, title)
        self.body.addWidget(self.tabs)

        # ── Month Inspector: the per-month waterfall ──
        self.inspector = MonthInspector(self)
        self.inspector.setVisible(False)
        self.body.addWidget(self.inspector)

        self.body.setStretchFactor(0, 0)
        self.body.setStretchFactor(1, 1)
        self.body.setStretchFactor(2, 0)
        self.body.setSizes([180, 760, 270])
        layout.addWidget(self.body, 1)

    def _on_chart_year_clicked(self, year: int):
        """Chart click-through: jump the Overview ledger to that policy year."""
        self.tabs.setCurrentWidget(self.overview)
        self.overview.jump_to_year(year)

    # ── Drill-down plumbing ───────────────────────────────────

    def _on_inspector_toggled(self, on: bool):
        self.inspector.setVisible(on)
        if on and self._results and self._inspected_row is not None:
            self._show_inspector_row(self._inspected_row)

    def _inspect_month(self, result_row: int):
        """Pin the inspector to a month (selection in the ledger or any grid)."""
        self._inspected_row = result_row
        if self.inspector.isVisible():
            self._show_inspector_row(result_row)

    def _show_inspector_row(self, result_row: int):
        if not self._results or not (0 <= result_row < len(self._results)):
            return
        prior = self._results[result_row - 1] if result_row > 0 else None
        self.inspector.show_month(self._results[result_row], prior)

    def _drill_down(self, result_row: int, ledger_column: str):
        """Overview double-click: open the detail tab for that value at that month."""
        title = LEDGER_DRILL_TABS.get(ledger_column, self.SUMMARY_GROUP)
        grid = self._tab_grids.get(title)
        if grid is None:
            return
        self.tabs.setCurrentWidget(grid)
        self._select_grid_row(grid, result_row)
        if not self.inspector_toggle.isChecked():
            self.inspector_toggle.setChecked(True)
        self._inspect_month(result_row)

    @staticmethod
    def _select_grid_row(grid: FilterTableView, result_row: int):
        if grid.model is None:
            return
        display = grid.model.get_display_data()
        try:
            position = display.index.get_loc(result_row)
        except KeyError:
            return
        grid.table_view.selectRow(position)
        grid.table_view.scrollTo(
            grid.table_view.model().index(position, 0),
            grid.table_view.ScrollHint.PositionAtCenter,
        )

    def _on_grid_cursor(self, grid: FilterTableView, current):
        if not current.isValid() or grid.model is None:
            return
        display = grid.model.get_display_data()
        if current.row() >= len(display.index):
            return
        self._inspect_month(int(display.index[current.row()]))

    # ── Navigator ─────────────────────────────────────────────

    def _rebuild_navigator(self, tab_columns_by_title: dict[str, list[str]]):
        from PyQt6.QtWidgets import QTreeWidgetItem

        self.nav_tree.clear()
        # Overview and the charts lead the rail so the user can always jump back.
        for title in ("Overview", "Chart", "Charges"):
            jump = QTreeWidgetItem([title])
            jump.setData(0, Qt.ItemDataRole.UserRole, (title, None))
            self.nav_tree.addTopLevelItem(jump)
        for title, columns in tab_columns_by_title.items():
            labels = self._header_labels_for_tab(title)
            stage = QTreeWidgetItem([title])
            stage.setData(0, Qt.ItemDataRole.UserRole, (title, None))
            for column_name in columns:
                if column_name in self.LEAD_COLUMNS:
                    continue
                leaf = QTreeWidgetItem([labels.get(column_name, column_name)])
                leaf.setData(0, Qt.ItemDataRole.UserRole, (title, column_name))
                stage.addChild(leaf)
            self.nav_tree.addTopLevelItem(stage)

    def _filter_navigator(self, text: str):
        needle = text.strip().lower()
        for stage_index in range(self.nav_tree.topLevelItemCount()):
            stage = self.nav_tree.topLevelItem(stage_index)
            any_visible = False
            for leaf_index in range(stage.childCount()):
                leaf = stage.child(leaf_index)
                match = not needle or needle in leaf.text(0).lower()
                leaf.setHidden(not match)
                any_visible = any_visible or match
            stage.setHidden(bool(needle) and not any_visible)
            stage.setExpanded(bool(needle) and any_visible)

    def _on_navigator_clicked(self, item, _column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        title, column_name = data
        if title == "Overview":
            self.tabs.setCurrentWidget(self.overview)
            return
        if title == "Chart":
            self.tabs.setCurrentWidget(self.chart)
            return
        if title == "Charges":
            self.tabs.setCurrentWidget(self.charges_chart)
            return
        grid = self._tab_grids.get(title)
        if grid is None:
            return
        self.tabs.setCurrentWidget(grid)
        if column_name is None or grid.model is None:
            return
        columns = list(grid.model.get_original_data().columns)
        if column_name in columns:
            column_index = columns.index(column_name)
            grid.table_view.selectColumn(column_index)
            grid.table_view.scrollTo(
                grid.table_view.model().index(0, column_index),
                grid.table_view.ScrollHint.PositionAtCenter,
            )

    def _post_lead_columns(self, title: str) -> list[str]:
        """Columns shown on ``title`` after the shared Date/Year/Month/Age lead."""
        return {
            self.SUMMARY_GROUP: self.SUMMARY_COLUMNS,
            self.WITHDRAWALS_GROUP: self._withdrawals_columns,
            self.DBO_CHANGE_GROUP: self._dbo_change_columns,
            self.FACE_CHANGE_GROUP: self._face_change_columns,
            self.COV_AFTER_CHANGE_GROUP: self._cov_after_change_columns,
            self.MTP_GROUP: self._mtp_columns,
            self.CTP_GROUP: self._ctp_columns,
            self.TEFRA_TAMRA_GROUP: self.TEFRA_TAMRA_COLUMNS,
            self.REQUESTED_PREMIUM_GROUP: self.REQUESTED_PREMIUM_COLUMNS,
            self.LOAN_CAPITALIZE_GROUP: self.LOAN_CAPITALIZE_COLUMNS,
            self.APPLY_PREMIUM_GROUP: self.APPLY_PREMIUM_COLUMNS,
            self.MONTHLY_DEDUCTION_GROUP: self._monthly_deduction_columns,
            self.EXCEPTION_PREMIUM_GROUP: self.EXCEPTION_PREMIUM_COLUMNS,
            self.POLICY_VALUES_GROUP: self.POLICY_VALUES_COLUMNS,
            self.ACCUMULATION_GROUP: self.ACCUMULATION_COLUMNS,
            self.ENDING_VALUES_GROUP: self.ENDING_VALUES_COLUMNS,
            self.SHADOW_ACCOUNT_GROUP: self.SHADOW_ACCOUNT_COLUMNS,
            self.TESTING_GROUP: self.TESTING_COLUMNS,
        }.get(title, [])

    def _header_labels_for_tab(self, title: str) -> dict[str, str]:
        tab_specific = {
            self.SUMMARY_GROUP: self.SUMMARY_HEADER_LABELS,
            self.SHADOW_ACCOUNT_GROUP: self.SHADOW_ACCOUNT_HEADER_LABELS,
            self.TESTING_GROUP: self.TESTING_HEADER_LABELS,
        }.get(title, {})
        return {**COMPACT_HEADER_LABELS, **tab_specific}

    def clear_results(self, message: str = "Load a policy, then click Run Values."):
        self.status_label.setText(message)
        self.overview.clear()
        self.chart.clear()
        self.charges_chart.clear()
        self.inspector.clear()
        self.nav_tree.clear()
        self._results = []
        self._inspected_row = None
        for grid in self._tab_grids.values():
            grid.set_dataframe(pd.DataFrame(), limit_rows=False)

    def display_projection(
        self,
        policy: IllustrationPolicyData,
        results: Iterable[MonthlyState],
        months: int = 24,
        injected_first_row_columns: set[str] | None = None,
    ):
        result_list = list(results)
        coverage_keys = self._coverage_keys(result_list)
        benefit_keys = self._detail_keys(result_list, "benefit_amounts", "benefit_rates", "benefit_charge_detail")
        rider_keys = self._detail_keys(result_list, "rider_amounts", "rider_rates", "rider_charge_detail")
        self._coverage_columns = self._coverage_column_names(coverage_keys)
        self._benefit_columns = self._benefit_column_names(benefit_keys)
        self._rider_columns = self._rider_column_names(rider_keys)
        self._rate_columns = self._rate_column_names(coverage_keys, benefit_keys, rider_keys)
        self._monthly_deduction_columns = self._monthly_deduction_column_names(
            coverage_keys,
            benefit_keys,
            rider_keys,
        )
        cov_slots, show_apb = self._cov_slots(result_list)
        self._withdrawals_columns = self._withdrawals_column_names(cov_slots)
        self._dbo_change_columns = self._dbo_change_column_names(cov_slots)
        self._face_change_columns = self._face_change_column_names(cov_slots)
        self._mtp_columns = self._mtp_column_names(cov_slots, show_apb)
        self._ctp_columns = self._ctp_column_names(cov_slots, show_apb)
        self._cov_after_change_columns = self._cov_after_change_column_names(cov_slots, show_apb)
        rows = [self._state_to_row(policy, state, coverage_keys, benefit_keys, rider_keys) for state in result_list]
        frame = pd.DataFrame(rows)
        self._all_columns = list(frame.columns)
        column_decimals = {"Face Amount": 0, "Year": 0, "Month": 0, "Attained Age": 0, "EPU Rate": 6}
        column_decimals.update({column: 6 for column in self._rate_columns})
        column_decimals.update({column: 6 for column in self._benefit_columns if " Rate " in column})
        column_decimals.update({column: 6 for column in self._rider_columns if " Rate " in column})
        column_decimals.update({f"SCR Cov {index}": 6 for index in (1, 2, 3)})
        column_decimals.update({column: 6 for column in ("Shadow COIR", "Shadow COIR + Sub", "Shadow DBD Rate", "Shadow EPUR")})
        injected = injected_first_row_columns or set()
        navigator_columns: dict[str, list[str]] = {}
        for title, grid in self._tab_grids.items():
            ordered = self.LEAD_COLUMNS + list(self._post_lead_columns(title))
            seen: set[str] = set()
            tab_columns = []
            for column_name in ordered:
                if column_name in frame.columns and column_name not in seen:
                    seen.add(column_name)
                    tab_columns.append(column_name)
            navigator_columns[title] = tab_columns
            grid.set_dataframe(frame.loc[:, tab_columns], limit_rows=False)
            grid.set_numeric_formatting(default_decimals=2, column_decimals=column_decimals)
            grid.set_header_labels(self._header_labels_for_tab(title))
            grid.set_highlighted_cells(
                {(0, column_name): self.LIGHT_PURPLE for column_name in injected if column_name in seen}
            )
            if grid.model is not None:
                grid.model._left_align_columns = {0}
            grid.autofit_columns_to_data()
            selection = grid.table_view.selectionModel()
            if selection is not None:
                selection.currentChanged.connect(
                    lambda current, _previous, g=grid: self._on_grid_cursor(g, current))
        self._results = result_list
        self._inspected_row = None
        self.inspector.clear()
        self._rebuild_navigator(navigator_columns)
        self.overview.display(policy, result_list)
        self.chart.set_data(build_chart_series(result_list[1:]), policy.issue_age)
        self.charges_chart.set_data(build_charge_bands(result_list[1:]), policy.issue_age)
        self.tabs.setCurrentIndex(0)
        self.status_label.setText(f"Showing valuation snapshot plus {months} projected months.")

    def _state_to_row(
        self,
        policy: IllustrationPolicyData,
        state: MonthlyState,
        coverage_keys: list[str],
        benefit_keys: list[str],
        rider_keys: list[str],
    ) -> dict:
        row = {
            "Date": state.date,
            "Year": state.policy_year,
            "Month": state.policy_month,
            "Attained Age": state.attained_age,
            "Premium Cap": state.premium_cap,
            "Premium Capped": state.premium_capped,
            "RegLn Total": state.end_rg_loan_princ + state.end_rg_loan_accrued,
            "PrefLn Total": state.end_pf_loan_princ + state.end_pf_loan_accrued,
            "Varln Total": state.end_vbl_loan_princ + state.end_vbl_loan_accrued,
            "Premium": state.gross_premium,
            "Premium Load": state.total_premium_load,
        }
        row.update(self._apply_premium_values(state))
        row.update({
            "mAV": self._av_before_md(state),
            "NAAR AV": state.nar_av,
            "Face Amount": policy.total_face,
            "Standard DB": state.standard_db,
            "Corridor Rate": state.corridor_rate,
            "Death Benefit": self._death_benefit(state),
            "Corridor Amount": state.corr_amount,
        })
        row.update(self._monthly_deduction_values(state, coverage_keys))
        row.update({
            "Monthly Fee": state.mfee_charge,
            "AV Charge": state.av_charge,
            "PW Charge": state.pw_charge,
        })
        row.update(self._benefit_values(state, benefit_keys))
        row.update({
            "Benefit Charges": state.benefit_charges,
        })
        row.update(self._rider_values(state, rider_keys))
        row.update({
            "Rider Charge": state.rider_charges,
            "Monthly Deduction": state.total_deduction,
            "AV after MD": state.av_after_deduction,
        })
        row.update(self._exception_premium_values(state))
        policy_values = self._policy_values(state, coverage_keys)
        row.update(policy_values)
        row.update(self._accumulation_values(state))
        row.update(self._shadow_account_values(state))
        row.update(self._ending_values(state))
        row.update({
            "Exception Protection": state.exception_protection,
            "Interest Days": state.days_in_month,
            "Interest Rate": state.annual_interest_rate * 100.0,
            "Effective Interest Rate": state.effective_annual_rate * 100.0,
            "Monthly Interest Rate": state.monthly_interest_rate * 100.0,
            "Interest": state.interest_credited,
            "RegLn Int": state.reg_loan_charge,
            "PrefLn Int": state.pref_loan_charge,
            "VarLn Int": state.vbl_loan_charge,
            "Account Value": state.av_end_of_month,
            "PolicyDebt": state.policy_debt,
            "Monthly MTP": state.monthly_mtp,
            "Accum MTP": state.accumulated_mtp,
            "Accum MTP less Prem": state.accum_mtp_less_prem,
            "SNET Active": state.snet_active,
            "Shadow Protection": state.shadow_protection,
            "Positive SV": state.positive_sv,
            "AV less Loans": state.av_less_loans,
            "Surrender Value": state.surrender_value,
            "Lapsed": state.lapsed,
        })
        row.update(self._tefra_tamra_values(state))
        row.update(self._requested_premium_values(state))
        row.update(self._withdrawal_values(state))
        row.update(self._dbo_change_values(state))
        row.update(self._face_change_values(state))
        row.update(self._cov_after_change_values(state))
        row.update(self._target_premium_values(state))
        loan_capitalize = self._loan_capitalize_values(state)
        row.update(loan_capitalize)
        row.update(self._surrender_values(state, coverage_keys))
        # Summary-tab composites derived from group columns above.
        row["Loan Int"] = (
            loan_capitalize["Advance - Rg Ln Int Accrued"]
            + loan_capitalize["Advance - Pf Ln Int Accrued"]
            + loan_capitalize["Advance - Var Ln Int Accrued"]
        )
        row["New Loan"] = policy_values["New Reg LN"] + policy_values["New Pref LN"]
        row.update(self._testing_values(state))
        return row

    @staticmethod
    def _testing_values(state: MonthlyState) -> dict:
        # 7-pay-by-year premiums and the MEC/violation flags are display columns
        # the engine does not yet compute and render as placeholders.
        return {
            "7-Pay Yr 1": 0.0,
            "7-Pay Yr 2": 0.0,
            "7-Pay Yr 3": 0.0,
            "7-Pay Yr 4": 0.0,
            "7-Pay Yr 5": 0.0,
            "7-Pay Yr 6": 0.0,
            "7-Pay Yr 7": 0.0,
            "MEC": False,
            "CVAT MEC": False,
            "7Pay MEC": False,
            "TEFRA Violation": False,
            "ScheduledPremLimitedByGP": False,
            "AV-Loans > 0": state.av_less_loans > 0,
            "Termination ID": "",
            "Inforce?": not state.lapsed,
        }


    def _detail_keys(cls, results: list[MonthlyState], *attribute_names: str) -> list[str]:
        keys: set[str] = set()
        for state in results:
            for attribute_name in attribute_names:
                keys.update(getattr(state, attribute_name).keys())
        return sorted(keys, key=cls._detail_sort_key)

    @staticmethod
    def _detail_sort_key(key: str) -> tuple[int, int | str, str]:
        digit_text = "".join(character for character in key if character.isdigit())
        if digit_text:
            prefix = key[:key.find(digit_text)]
            return (0, int(digit_text), prefix)
        return (1, key.upper(), key)

    @classmethod
    def _coverage_keys(cls, results: list[MonthlyState]) -> list[str]:
        keys: set[str] = set()
        for state in results:
            for mapping in (
                state.db_by_coverage,
                state.discounted_db_by_coverage,
                state.nar_by_coverage,
                state.coi_rates_by_coverage,
                state.coi_charges_by_coverage,
                state.epu_rates_by_coverage,
                state.epu_charges_by_coverage,
                state.scr_rates_by_coverage,
                state.surrender_charges_by_coverage,
            ):
                keys.update(mapping.keys())
        if not keys:
            keys.add("cov1")
        return sorted(keys, key=cls._coverage_sort_key)

    @staticmethod
    def _coverage_sort_key(key: str) -> tuple[int, int | str]:
        if key.startswith("cov") and key[3:].isdigit():
            return (0, int(key[3:]))
        return (1, key)

    @staticmethod
    def _coverage_label(key: str) -> str:
        if key.startswith("cov") and key[3:].isdigit():
            return f"Cov{key[3:]}"
        return key.upper()

    @staticmethod
    def _cov_slots(results: list[MonthlyState]) -> tuple[list[int], bool]:
        """RERUN coverage slots (1..3) ever active in the run, plus the APB flag.

        Read from the engine's Cov After Change snapshots — a slot created
        mid-projection (face increase) appears once its "Cov n Active" flips.
        Slot 1 always shows.
        """
        slots = {1}
        show_apb = False
        for state in results:
            snap = state.coverage_after_change
            for index in (2, 3):
                if snap.get(f"Cov {index} Active"):
                    slots.add(index)
            show_apb = show_apb or bool(snap.get("APB Active"))
        return sorted(slots), show_apb

    @staticmethod
    def _withdrawals_column_names(slots: list[int]) -> list[str]:
        return [
            "Input Withdrawal",
            "Max Net Allowed",
            "CostBasis before WD",
            "Applied Net WD",
            "Remaining Distribution",
            "CostBasis after WD",
            "WithdrawalTD",
            "WD YTD",
            "Corridor Amount",
            "WD Reduces SA",
            *[f"WD SA Change Cov {i}" for i in slots],
            "Partial SC",
            "GrossWD",
            "AV post WD",
            "WD Face Decrease",
        ]

    @staticmethod
    def _dbo_change_column_names(slots: list[int]) -> list[str]:
        return [
            "Prev DBO",
            "Input DBO",
            "DBO Changed",
            "Change Type",
            "DBO Change Allowed",
            "DBO Face Decrease",
            *[f"DBO Decrease Cov {i}" for i in slots],
            *[f"DBO PSC Cov {i}" for i in slots],
            "Total PSC DBO",
            "DBO Face Increase",
            *[f"DBO Increase Cov {i}" for i in slots],
            "DBO",
            "Total SA",
        ]

    @staticmethod
    def _face_change_column_names(slots: list[int]) -> list[str]:
        return [
            "Input Face",
            "Change in Input Face",
            "Specified Face Decrease",
            *[f"Spec Decrease Cov {i}" for i in slots],
            *[f"Spec PSC Cov {i}" for i in slots],
            "Total PSC Spec Dec",
            "Specified Face Increase",
            *[f"Spec Increase Cov {i}" for i in slots],
            "Total SA",
        ]

    @staticmethod
    def _mtp_column_names(slots: list[int], show_apb: bool) -> list[str]:
        return [
            *[f"MTP Rate Cov {i}" for i in slots],
            *[f"MTP Rate Cov {i} Tbl" for i in slots],
            *[f"MTP Cov {i}" for i in slots],
            *(["MTP APB"] if show_apb else []),
            "CCV MTP",
            "GIR MTP",
            "Other Benefits MTP",
            "MTP w/o PW",
            "PW MTPR",
            "PW MTP",
            "vMTP",
            "vMonthlyMTP",
            "vAccumMTP",
        ]

    @staticmethod
    def _ctp_column_names(slots: list[int], show_apb: bool) -> list[str]:
        return [
            *[f"CTP Rate Cov {i}" for i in slots],
            *[f"CTP Rate Cov {i} Tbl" for i in slots],
            *[f"CTP Cov {i}" for i in slots],
            *(["CTP APB"] if show_apb else []),
            "CCV CTP",
            "GIR CTP",
            "Other Benefits CTP",
            "CTP w/o PW",
            "CTP PW",
            "Target Band",
            "vCTP",
        ]

    @staticmethod
    def _cov_after_change_column_names(slots: list[int], show_apb: bool) -> list[str]:
        return [
            *[f"Cov {i} Active" for i in slots],
            *(["APB Active"] if show_apb else []),
            *[f"Cov {i} Issue Date" for i in slots],
            *[f"Cov {i} Months from Issue" for i in slots],
            *[f"Cov {i} Months from Issue w setback" for i in slots],
            *[f"Year by Pol Ann Cov {i}" for i in slots],
            *[f"Year by Pol Ann w setback Cov {i}" for i in slots],
            *[f"Year by Cov Ann Cov {i}" for i in slots],
            *[f"Year by Cov Ann w setback Cov {i}" for i in slots],
            *[f"Original SA Cov {i}" for i in slots],
            *(["Original SA APB"] if show_apb else []),
            "LastActiveSegment",
            *[f"Current SA Cov {i}" for i in slots],
            *(["Current SA APB"] if show_apb else []),
            *[f"Band Lock Cov {i}" for i in slots],
            *(["Band APB"] if show_apb else []),
            "CurrentSA",
            "CurrentBand",
            *[f"Issue Age Cov {i}" for i in slots],
            *[f"Rateclass Cov {i}" for i in slots],
            *[f"Table Rating Cov {i}" for i in slots],
            "Base Flat1",
            "Base Flat2",
            "Coverage_Change",
            "PolicyChangeAVReduction",
        ]

    @classmethod
    def _coverage_column_names(cls, coverage_keys: list[str]) -> list[str]:
        columns: list[str] = []
        for key in coverage_keys:
            label = cls._coverage_label(key)
            columns.extend([
                f"DB {label}",
                f"Disc DB {label}",
                f"NAR {label}",
                f"COI Charge {label}",
                f"EPU Charge {label}",
                f"Surr Charge {label}",
            ])
        columns.extend(["DB Corr", "Disc DB Corr", "NAR Corr", "COI Charge Corr"])
        return columns

    @classmethod
    def _rate_column_names(cls, coverage_keys: list[str], benefit_keys: list[str], rider_keys: list[str]) -> list[str]:
        columns = ["Corridor Rate"]
        for key in coverage_keys:
            label = cls._coverage_label(key)
            columns.extend([f"COI Rate {label}", f"EPU Rate {label}", f"SCR Rate {label}"])
        columns.extend(["COI Rate Corr", "EPU Rate"])
        columns.extend([f"Benefit Rate {cls._detail_label(key)}" for key in benefit_keys])
        columns.extend([f"Rider Rate {cls._detail_label(key)}" for key in rider_keys])
        columns.extend(["Effective Interest Rate", "Monthly Interest Rate"])
        return columns

    @classmethod
    def _benefit_column_names(cls, benefit_keys: list[str]) -> list[str]:
        columns: list[str] = []
        for key in benefit_keys:
            label = cls._detail_label(key)
            columns.extend([f"Benefit Amount {label}", f"Benefit Rate {label}", f"Benefit Charge {label}"])
        return columns

    @classmethod
    def _rider_column_names(cls, rider_keys: list[str]) -> list[str]:
        columns: list[str] = []
        for key in rider_keys:
            label = cls._detail_label(key)
            columns.extend([f"Rider Amount {label}", f"Rider Rate {label}", f"Rider Charge {label}"])
        return columns

    @classmethod
    def _monthly_deduction_column_names(
        cls,
        coverage_keys: list[str],
        benefit_keys: list[str],
        rider_keys: list[str],
    ) -> list[str]:
        columns = [
            "mAV",
            "NAAR AV",
            "Face Amount",
            "Standard DB",
            "Corridor Rate",
            "Death Benefit",
            "Corridor Amount",
        ]
        columns.extend(cls._monthly_deduction_detail_column_names(coverage_keys))
        columns.extend([
            "Monthly Fee",
            "AV Charge",
            "PW Charge",
        ])
        columns.extend(cls._benefit_column_names(benefit_keys))
        columns.extend(["Benefit Charges"])
        columns.extend(cls._rider_column_names(rider_keys))
        columns.extend(["Rider Charge", "Monthly Deduction", "AV after MD"])
        return columns

    @staticmethod
    def _detail_label(key: str) -> str:
        return key.upper() if key else "UNSPECIFIED"

    @classmethod
    def _monthly_deduction_detail_column_names(cls, coverage_keys: list[str]) -> list[str]:
        columns: list[str] = []
        columns.extend([f"DB {cls._coverage_label(key)}" for key in coverage_keys])
        columns.append("DB Corr")
        columns.extend([f"Disc DB {cls._coverage_label(key)}" for key in coverage_keys])
        columns.append("Disc DB Corr")
        columns.append("Total Discounted DB")
        columns.extend([f"NAR {cls._coverage_label(key)}" for key in coverage_keys])
        columns.append("NAR Corr")
        columns.append("NAR")
        columns.extend([f"COI Rate {cls._coverage_label(key)}" for key in coverage_keys])
        columns.append("COI Rate Corr")
        columns.extend([f"COI Charge {cls._coverage_label(key)}" for key in coverage_keys])
        columns.append("COI Charge Corr")
        columns.extend(["Total Base COI Charge", "COI Charge"])
        for key in coverage_keys:
            label = cls._coverage_label(key)
            columns.extend([f"EPU Rate {label}", f"EPU Charge {label}"])
        columns.extend(["EPU Rate", "EPU Fee"])
        return columns

    @classmethod
    def _monthly_deduction_values(cls, state: MonthlyState, coverage_keys: list[str]) -> dict:
        values: dict[str, float] = {}
        for key in coverage_keys:
            label = cls._coverage_label(key)
            values[f"DB {label}"] = state.db_by_coverage.get(key, 0.0)
        values["DB Corr"] = state.corr_amount
        for key in coverage_keys:
            label = cls._coverage_label(key)
            values[f"Disc DB {label}"] = state.discounted_db_by_coverage.get(key, 0.0)
        values["Disc DB Corr"] = state.discounted_db_corr
        values["Total Discounted DB"] = state.total_discounted_db
        for key in coverage_keys:
            label = cls._coverage_label(key)
            values[f"NAR {label}"] = state.nar_by_coverage.get(key, 0.0)
        values["NAR Corr"] = state.nar_corr
        values["NAR"] = state.total_nar or state.nar
        for key in coverage_keys:
            label = cls._coverage_label(key)
            values[f"COI Rate {label}"] = state.coi_rates_by_coverage.get(key, 0.0)
        values["COI Rate Corr"] = state.coi_rate
        for key in coverage_keys:
            label = cls._coverage_label(key)
            values[f"COI Charge {label}"] = state.coi_charges_by_coverage.get(key, 0.0)
        values["COI Charge Corr"] = state.coi_charge_corr
        total_coi_charge = state.total_coi_charge or state.coi_charge
        values["Total Base COI Charge"] = total_coi_charge
        values["COI Charge"] = total_coi_charge
        for key in coverage_keys:
            label = cls._coverage_label(key)
            values[f"EPU Rate {label}"] = state.epu_rates_by_coverage.get(key, 0.0)
            values[f"EPU Charge {label}"] = state.epu_charges_by_coverage.get(key, 0.0)
        values["EPU Rate"] = state.epu_rate
        values["EPU Fee"] = state.epu_charge
        return values

    @classmethod
    def _surrender_values(cls, state: MonthlyState, coverage_keys: list[str]) -> dict:
        values: dict[str, float] = {}
        for key in coverage_keys:
            label = cls._coverage_label(key)
            values[f"SCR Rate {label}"] = state.scr_rates_by_coverage.get(key, 0.0)
            values[f"Surr Charge {label}"] = state.surrender_charges_by_coverage.get(key, 0.0)
        return values

    @staticmethod
    def _exception_premium_values(state: MonthlyState) -> dict:
        return {
            "Guideline Limit Reached": state.guideline_limit_reached,
            "vExceptionPremMode": state.exception_prem_mode,
            "GP_Exception_Prem_Gross": state.gp_exception_prem_gross,
            # Engine does not yet compute the exception-premium COI discount (CalcEngine TA).
            "Exception_Prem_Discount": 0.0,
            "vGP_Exception_Prem": state.gp_exception_prem,
        }

    @staticmethod
    def _apply_premium_values(state: MonthlyState) -> dict:
        # The engine tracks the net-premium split and loads (CalcEngine cols
        # 367-403); the per-year allowance/cap, levelized-premium, and 1035/
        # lumpsum schedule columns are not yet computed and render as placeholders.
        return {
            "GP_Allowance0": 0.0,
            "NPT Allowance0": 0.0,
            "TAMRA_Allowance0": 0.0,
            "Annual Cap0": 0.0,
            "Applied1035": 0.0,
            "GP_Allowance1": 0.0,
            "NPT Allowance 1": 0.0,
            "TAMRA_Allowance1": 0.0,
            "Annual Cap1": 0.0,
            "Lumpsum Remaining": 0.0,
            "vAppliedLumpsum": 0.0,
            "GP_Allowance2": 0.0,
            "NPT Allowance 2": 0.0,
            "TAMRA_Allowance2": 0.0,
            "Annual Cap2": 0.0,
            "TAMRA_Level_Allowance_BOY": 0.0,
            "TAMRA_Level_Allowance_EOY": 0.0,
            "NPT_Level_Allowance": 0.0,
            "GP_Level_Allowance": 0.0,
            "Scheduled Prem Cap": 0.0,
            "Levelized Max Premium": 0.0,
            "Apply Levelized Premium": False,
            "Scheduled Premium less Loan Repay": 0.0,
            "AppliedScheduledPremium": 0.0,
            "AppliedTotalPremium": state.gross_premium,
            "PremTD": state.premiums_to_date,
            "PremYTD": state.premiums_ytd,
            "CostBasis": state.cost_basis,
            "Prem Under Target": state.prem_under_target,
            "Prem Over Target": state.prem_over_target,
            # TPP/EPP load rates are not surfaced on the state (only the dollar loads are).
            "TPP Rate": 0.0,
            "EPP Rate": 0.0,
            "Under Load": state.target_load,
            "Over Load": state.excess_load,
            "Flat Load": state.flat_load,
            "TotalPremLoad": state.total_premium_load,
            "NetPremium": state.net_premium,
        }

    @staticmethod
    def _tefra_tamra_values(state: MonthlyState) -> dict:
        return {
            "GSP": state.gsp,
            "GLP": state.glp,
            "AccumGLP": state.accumulated_glp,
            "TEFRA_Limit": state.guideline_limit,
            # Premiums-less-withdrawals and monthly 7-pay premium are not yet tracked.
            "Prem-WD": 0.0,
            "ForceOut": state.guideline_forceout,
            "7PayPrem": 0.0,
            "New TAMRA Period": False,
            "7PayStartDate": None,
            "TAMRAMonth": 0,
            "TAMRA_MonthOfYear": 0,
            "TAMRA_Year": state.tamra_year,
            "Amount In 7-Pay": state.accumulated_7pay,
            # Lowest-7-year face and NPT (necessary premium test) are not yet computed.
            "Lowest7YearFace": 0.0,
            "Value_for_NPT": 0.0,
            "NPT_NSP": 0.0,
            "NPT_Premium": 0.0,
        }

    @staticmethod
    def _requested_premium_values(state: MonthlyState) -> dict:
        # The engine projects from a single gross premium; the planned-premium
        # schedule inputs (1035, lump sum, frequency, payment counts) are not
        # yet surfaced per-month, so these render as placeholders for now.
        return {
            "1035_Amount": 0.0,
            "Lumpsum": 0.0,
            "PlannedPremium": state.requested_premium,
            "PlannedPremiumMode": "",
            "Premium Frequency": "",
            "Premium Period": 0,
            "Scheduled Premium Due": False,
            "Scheduled Premium": 0.0,
            "Payment Count For Policy Year": 0,
            "Payment Count for TAMRA Year": 0,
        }

    @staticmethod
    def _cov_after_change_values(state: MonthlyState) -> dict:
        # Per-month "Cov After Change" snapshot built by the engine
        # (CalcEngine cols DQ..FQ), keyed by the RERUN display names.
        return dict(state.coverage_after_change)

    @staticmethod
    def _withdrawal_values(state: MonthlyState) -> dict:
        # Withdrawal block (CalcEngine AX..BU). Rows carry every cov slot;
        # the per-tab column list trims to the coverages active in the run.
        row = {
            "Input Withdrawal": state.input_withdrawal,
            "Max Net Allowed": state.max_net_withdrawal,
            "CostBasis before WD": state.cost_basis_before_wd,
            "Applied Net WD": state.applied_net_withdrawal,
            "Remaining Distribution": state.remaining_distribution,
            "CostBasis after WD": state.cost_basis_after_wd,
            "WithdrawalTD": state.withdrawals_to_date,
            "WD YTD": state.withdrawals_ytd,
            "Corridor Amount": state.wd_corridor_amount,
            "WD Reduces SA": state.wd_reduces_sa,
            "Partial SC": state.wd_partial_sc,
            "GrossWD": state.gross_withdrawal,
            "AV post WD": state.av_post_withdrawal,
            "WD Face Decrease": state.wd_face_decrease,
        }
        cuts = sorted(state.wd_sa_change_by_cov.items())
        for i in (1, 2, 3):
            row[f"WD SA Change Cov {i}"] = cuts[i - 1][1] if i - 1 < len(cuts) else 0.0
        return row

    @classmethod
    def _dbo_change_values(cls, state: MonthlyState) -> dict:
        # DB Option Change block (CalcEngine BW..CU) — zeros on no-change
        # months. Rows always carry every slot; the per-tab column list trims
        # to the coverages active in the run.
        row = {col: 0.0 for col in cls._dbo_change_column_names([1, 2, 3])}
        row.update({
            "Prev DBO": "", "Input DBO": "", "DBO Changed": False,
            "Change Type": "", "DBO Change Allowed": "", "DBO": "",
        })
        row.update(state.dbo_change_detail)
        return row

    @classmethod
    def _face_change_values(cls, state: MonthlyState) -> dict:
        # Specified Increase/Decrease block (CalcEngine CW..DO).
        row = {col: 0.0 for col in cls._face_change_column_names([1, 2, 3])}
        row.update(state.face_change_detail)
        return row

    @staticmethod
    def _target_premium_values(state: MonthlyState) -> dict:
        # MTP / CTP detail (CalcEngine HO..JG / JI..KQ) — engine snapshots,
        # recomputed on coverage changes, carried forward between. The headline
        # vMTP/vMonthlyMTP/vAccumMTP/vCTP come from the projection state.
        row = {}
        row.update(state.mtp_detail)
        row.update(state.ctp_detail)
        row["vMTP"] = state.mtp_annual
        row["vMonthlyMTP"] = state.monthly_mtp
        row["vAccumMTP"] = state.accumulated_mtp
        row["vCTP"] = state.ctp
        return row

    @staticmethod
    def _loan_capitalize_values(state: MonthlyState) -> dict:
        # The engine tracks the beginning-of-month loan buckets (after cap/repay,
        # CalcEngine cols 336-341); the advance/arrears repayment detail columns
        # are not yet computed and render as placeholders.
        return {
            "Advance - Rg Ln Princ/Total": 0.0,
            "Advance - Rg Ln Int Accrued": 0.0,
            "Advance - Pf Ln Princ/Total": 0.0,
            "Advance - Pf Ln Int Accrued": 0.0,
            "Advance - Var Ln Princ/Total": 0.0,
            "Advance - Var Ln Int Accrued": 0.0,
            "Advance - Adv Reg LN Payoff": 0.0,
            "Advance - Adv Pref LN Payoff": 0.0,
            "Advance - LoanPayoff": 0.0,
            "Arrears - PremToPayLoanInterest": 0.0,
            "Arrears - From Lumpsum": 0.0,
            "Arrears - From Scheduled Prem": 0.0,
            "Arrears - LoanRepayFromForceout": 0.0,
            "Arrears - LoanRepayFromPremAndForceout": 0.0,
            "Arrears - Requested Loan Repayment": 0.0,
            "Arrears - Total Loan Repayment Attempted": 0.0,
            "Advance - Adv Reg LN Repay": 0.0,
            "Advance - Adv Pref LN Repay": 0.0,
            "Advance - Adv Total Loan Repayment": 0.0,
            "Rg Ln Princ": state.rg_loan_princ,
            "Rg Ln Int": state.rg_loan_accrued,
            "Pf Ln Princ": state.pf_loan_princ,
            "Pf Ln Int": state.pf_loan_accrued,
            "Var Ln Princ": state.vbl_loan_princ,
            "Var Ln Int": state.vbl_loan_accrued,
            "LNRepayLeftOver": 0.0,
            "TotalLoanReduction": 0.0,
            "PolicyDebtDisplay": (
                state.rg_loan_princ
                + state.rg_loan_accrued
                + state.pf_loan_princ
                + state.pf_loan_accrued
                + state.vbl_loan_princ
                + state.vbl_loan_accrued
            ),
        }

    @classmethod
    def _policy_values(cls, state: MonthlyState, coverage_keys: list[str]) -> dict:
        ordered_keys = list(coverage_keys)

        def coverage_value(mapping: dict, index: int) -> float:
            position = index - 1
            if position < len(ordered_keys):
                return mapping.get(ordered_keys[position], 0.0)
            return 0.0

        return {
            "AV": state.av_end_of_month,
            "SCR Cov 1": coverage_value(state.scr_rates_by_coverage, 1),
            "SCR Cov 2": coverage_value(state.scr_rates_by_coverage, 2),
            "SCR Cov 3": coverage_value(state.scr_rates_by_coverage, 3),
            "SC Cov 1": coverage_value(state.surrender_charges_by_coverage, 1),
            "SC Cov 2": coverage_value(state.surrender_charges_by_coverage, 2),
            "SC Cov 3": coverage_value(state.surrender_charges_by_coverage, 3),
            "FullSC": state.surrender_charge,
            "LapseSV": state.surrender_value,
            # Loan distribution columns are not yet computed by the engine (CalcEngine TM-TU).
            "Requested Loan": 0.0,
            "Loan Mode Effective": False,
            "Scheduled Loan Amount": 0.0,
            "Remaining Distribution": 0.0,
            "vAppliedLoan": 0.0,
            "Gain": 0.0,
            "New Reg LN": 0.0,
            "New Pref LN": 0.0,
            "AdvRegLNInt": state.reg_loan_charge,
            "PrefRegLNInt": state.pref_loan_charge,
            "Total Rg Ln Princ": state.end_rg_loan_princ,
            "Total Pref Ln Princ": state.end_pf_loan_princ,
            "Total Vbl Ln Princ": state.end_vbl_loan_princ,
            "AV Display": 0.0,
        }

    @staticmethod
    def _accumulation_values(state: MonthlyState) -> dict:
        # The engine tracks days, impaired interest, credited interest and the
        # beginning-of-month loan buckets; declared/blended index-rate detail and
        # policy bonus are not yet computed and render as placeholders.
        return {
            "# of Days": state.days_in_month,
            "PolicyBonus": state.bonus_interest_rate * 100.0,
            "Fixed Ln Prinicple": 0.0,
            "Reg Impaired Int": state.reg_impaired_int,
            "Pref Impaired Int": state.pref_impaired_int,
            "Declared Rate": state.annual_interest_rate * 100.0,
            "Declared Rate + Policy Bonus": state.effective_annual_rate * 100.0,
            "Unimpaired Int": 0.0,
            "Declared Interest": state.interest_credited,
            "Blended Index Rate": 0.0,
            "BlendedCreditingRate": 0.0,
            "BlendInterest": 0.0,
            "Reg Ln Princ": state.rg_loan_princ,
            "Accrued Reg Ln Int": state.rg_loan_accrued,
            "Pref Ln Princ": state.pf_loan_princ,
            "Accrued Pref Ln Int": state.pf_loan_accrued,
            "Vbl Ln Princ": state.vbl_loan_princ,
            "Accured Vbl Ln Int": state.vbl_loan_accrued,
        }

    @staticmethod
    def _shadow_account_values(state: MonthlyState) -> dict:
        # The shadow (CCV) account is computed by the engine (CalcEngine cols
        # 614-648). A few RERUN display columns (alternate target-premium bases,
        # applied-premium echo, percent-of-premium splits, substandard COI) are
        # not separately surfaced on the state and render as placeholders.
        return {
            "Shadow_BAV": state.shadow_bav,
            "WD, Charges and ForceOuts": state.shadow_wd_charges,
            "Shadow SA": state.shadow_sa,
            "Shadow_TPR": 0.0,
            "Shadow_TBL1TPR": 0.0,
            "Shadow_TP": state.shadow_target_prem,
            "Applied Total Premium": 0.0,
            "Premium YTD": 0.0,
            "Shadow Prem Under Target": state.shadow_prem_under_target,
            "Shadow Prem Over Target": state.shadow_prem_over_target,
            "Target Percent Prem": 0.0,
            "Excess Precent Prem": 0.0,
            "Target Prem Load": state.shadow_target_load,
            "Excess Prem Load": state.shadow_excess_load,
            "Shadow Premium Load": state.shadow_prem_load,
            "Shadow Net Prem": state.shadow_net_prem,
            "Shadow_NARAV": state.shadow_nar_av,
            "Shadow DB": state.shadow_db,
            "Shadow COIR": state.shadow_coi_rate,
            "Shadow COIR + Sub": 0.0,
            "Shadow DBD Rate": state.shadow_dbd_rate,
            "Shadow NAR": state.shadow_nar,
            "Shadow COI": state.shadow_coi,
            "Shadow EPUR": state.shadow_epu_rate,
            "Shadow EPU": state.shadow_epu,
            "Shadow MFEE": state.shadow_mfee,
            "Rider Charges": state.shadow_rider_charges,
            "Shadow MD": state.shadow_md,
            "Shadow AV": state.shadow_av,
            "Shadow # of Days": state.shadow_days,
            "Shadow Int Rate": state.shadow_int_rate * 100.0,
            "Eff Rate": state.shadow_eff_rate * 100.0,
            "Shadow Interest": state.shadow_interest,
            "ShadowEAV": state.shadow_eav,
            "ShadowEAV_less_Debt": state.shadow_eav_less_debt,
        }

    @staticmethod
    def _ending_values(state: MonthlyState) -> dict:
        # Ending account value, debt, surrender value and death benefit are
        # tracked; the per-component illustration display columns (EA/ELN/ES,
        # corridor split, outlay, distributions, GCO) are not yet computed.
        return {
            "EA": state.av_end_of_month,
            "ELN": state.policy_debt,
            "ES": state.surrender_value,
            "EDBwoCORR": 0.0,
            "EDB_CORR": 0.0,
            "EDBwLNs": 0.0,
            "EDB": state.ending_db,
            "IllustrationAV": state.av_end_of_month,
            "IllustrationInterestRate": state.annual_interest_rate * 100.0,
            "IllustrationLN": state.policy_debt,
            "IllustrationSV": state.surrender_value,
            "IllustrationDB": state.ending_db,
            "PremiumOutlay": state.premium_outlay,
            "ForceOutDisplay": state.guideline_forceout,
            "LoanRepayFromPremDisplay": 0.0,
            "LoanRepayDisplay": 0.0,
            "DistributionFromPolicy": 0.0,
            "IllustrationGCO": 0.0,
        }

    @classmethod
    def _benefit_values(cls, state: MonthlyState, benefit_keys: list[str]) -> dict:
        values: dict[str, float] = {}
        for key in benefit_keys:
            label = cls._detail_label(key)
            values[f"Benefit Amount {label}"] = state.benefit_amounts.get(key, 0.0)
            values[f"Benefit Rate {label}"] = state.benefit_rates.get(key, 0.0)
            values[f"Benefit Charge {label}"] = state.benefit_charge_detail.get(key, 0.0)
        return values

    @classmethod
    def _rider_values(cls, state: MonthlyState, rider_keys: list[str]) -> dict:
        values: dict[str, float] = {}
        for key in rider_keys:
            label = cls._detail_label(key)
            values[f"Rider Amount {label}"] = state.rider_amounts.get(key, 0.0)
            values[f"Rider Rate {label}"] = state.rider_rates.get(key, 0.0)
            values[f"Rider Charge {label}"] = state.rider_charge_detail.get(key, 0.0)
        return values

    @staticmethod
    def _av_before_md(state: MonthlyState) -> float:
        return state.md_check_av_before_deduction or state.av_after_premium

    @staticmethod
    def _death_benefit(state: MonthlyState) -> float:
        return state.ending_db or state.total_db or state.gross_db