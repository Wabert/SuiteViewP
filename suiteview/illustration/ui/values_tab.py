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
from .values_overview import PolicyValueChart, ValuesOverview, build_chart_series


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
        "Accum MTP less Prem": "AccumMTP_less_PremTD",
        "SNET Active": "SNET",
        "Positive SV": "PositiveSV",
        "Exception Protection": "GP Exception Prem Protection",
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
        self._tab_grids: dict[str, FilterTableView] = {}
        self._setup_ui()
        self.clear_results()

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {PURPLE_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"color: {PURPLE_DARK}; background: transparent; font-size: 11px; font-weight: bold;"
        )
        layout.addWidget(self.status_label)

        self.tabs = QTabWidget(self)
        self.tabs.setStyleSheet(TAB_WIDGET_STYLE)
        self.overview = ValuesOverview(self.tabs)
        self.tabs.addTab(self.overview, "Overview")
        self.chart = PolicyValueChart(self.tabs)
        self.chart.yearClicked.connect(self._on_chart_year_clicked)
        self.tabs.addTab(self.chart, "Chart")
        for title in self.TAB_ORDER:
            grid = FilterTableView(self.tabs)
            grid.set_search_visible(False)
            grid.apply_ledger_style()
            self._tab_grids[title] = grid
            self.tabs.addTab(grid, title)
        layout.addWidget(self.tabs)

    def _on_chart_year_clicked(self, year: int):
        """Chart click-through: jump the Overview ledger to that policy year."""
        self.tabs.setCurrentWidget(self.overview)
        self.overview.jump_to_year(year)

    def _post_lead_columns(self, title: str) -> list[str]:
        """Columns shown on ``title`` after the shared Date/Year/Month/Age lead."""
        return {
            self.SUMMARY_GROUP: self.SUMMARY_COLUMNS,
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
        if title == self.SUMMARY_GROUP:
            return self.SUMMARY_HEADER_LABELS
        if title == self.SHADOW_ACCOUNT_GROUP:
            return self.SHADOW_ACCOUNT_HEADER_LABELS
        if title == self.TESTING_GROUP:
            return self.TESTING_HEADER_LABELS
        return {}

    def clear_results(self, message: str = "Load a policy, then click Run Values."):
        self.status_label.setText(message)
        self.overview.clear()
        self.chart.clear()
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
        for title, grid in self._tab_grids.items():
            ordered = self.LEAD_COLUMNS + list(self._post_lead_columns(title))
            seen: set[str] = set()
            tab_columns = []
            for column_name in ordered:
                if column_name in frame.columns and column_name not in seen:
                    seen.add(column_name)
                    tab_columns.append(column_name)
            grid.set_dataframe(frame.loc[:, tab_columns], limit_rows=False)
            grid.set_numeric_formatting(default_decimals=2, column_decimals=column_decimals)
            grid.set_header_labels(self._header_labels_for_tab(title))
            grid.set_highlighted_cells(
                {(0, column_name): self.LIGHT_PURPLE for column_name in injected if column_name in seen}
            )
            if grid.model is not None:
                grid.model._left_align_columns = {0}
        self.overview.display(policy, result_list)
        self.chart.set_data(build_chart_series(result_list[1:]), policy.issue_age)
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
            "PremiumOutlay": 0.0,
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