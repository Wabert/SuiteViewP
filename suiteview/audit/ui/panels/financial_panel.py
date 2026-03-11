"""
Financial Criteria Panel
==========================
Financial ranges: AV, SA, loans, premiums, funds, 7-pay, TAMRA, etc.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QCheckBox, QHBoxLayout

from .panel_widgets import (
    CriteriaPanel, CollapsibleSection, CheckableListBox,
    NumericRangeRow, SingleValueRow,
)
from ...models.audit_constants import (
    IUL_FUND_CODES,
)


class FinancialPanel(CriteriaPanel):
    """Financial filters: AV, SA, loans, premiums, fund allocations, etc."""

    def _build_ui(self):
        # ── Accumulation / Account Values ───────────────────────────────
        sec = CollapsibleSection("Account Values")
        self.av_range = NumericRangeRow("Accum Value")
        sec.add_widget(self.av_range)
        self.current_sa_range = NumericRangeRow("Current SA")
        sec.add_widget(self.current_sa_range)
        self.shadow_av_range = NumericRangeRow("Shadow AV")
        sec.add_widget(self.shadow_av_range)
        self.main_layout.addWidget(sec)

        # ── Loan Fields ─────────────────────────────────────────────────
        sec2 = CollapsibleSection("Loan")
        self.loan_principal_range = NumericRangeRow("Loan Principal")
        sec2.add_widget(self.loan_principal_range)
        self.loan_interest_range = NumericRangeRow("Loan Accrued Int")
        sec2.add_widget(self.loan_interest_range)
        self.loan_charge_rate = SingleValueRow("Loan Charge Rate", "", 80)
        sec2.add_widget(self.loan_charge_rate)
        self.main_layout.addWidget(sec2)

        # ── Premium Fields ──────────────────────────────────────────────
        sec3 = CollapsibleSection("Premiums")
        self.prem_ytd_range = NumericRangeRow("Premium YTD")
        sec3.add_widget(self.prem_ytd_range)
        self.additional_prem_range = NumericRangeRow("Additional Prem")
        sec3.add_widget(self.additional_prem_range)
        self.total_prem_range = NumericRangeRow("Total Premium")
        sec3.add_widget(self.total_prem_range)
        self.main_layout.addWidget(sec3)

        # ── 7-Pay / TAMRA ──────────────────────────────────────────────
        sec4 = CollapsibleSection("7-Pay / TAMRA / MTP")
        self.seven_pay_range = NumericRangeRow("7-Pay Premium")
        sec4.add_widget(self.seven_pay_range)
        self.seven_pay_av_range = NumericRangeRow("7-Pay AV")
        sec4.add_widget(self.seven_pay_av_range)
        self.accum_mtp_range = NumericRangeRow("Accum MTP")
        sec4.add_widget(self.accum_mtp_range)
        self.accum_glp_range = NumericRangeRow("Accum GLP")
        sec4.add_widget(self.accum_glp_range)
        self.accum_wd_range = NumericRangeRow("Accum Withdrawals")
        sec4.add_widget(self.accum_wd_range)
        self.main_layout.addWidget(sec4)

        # ── Fund Allocations ────────────────────────────────────────────
        sec5 = CollapsibleSection("Fund Allocations")
        self.fund_id = SingleValueRow("Fund ID", "e.g. IC, IX", 80)
        sec5.add_widget(self.fund_id)
        self.fund_id_range = NumericRangeRow("Fund Value")
        sec5.add_widget(self.fund_id_range)
        self.fund_id_list = SingleValueRow("Fund ID List", "IC,IX,IF", 120)
        sec5.add_widget(self.fund_id_list)
        self.prem_alloc_list = CheckableListBox(
            IUL_FUND_CODES, "Premium Allocation Funds", max_height=200
        )
        sec5.add_widget(self.prem_alloc_list)
        self.type_p_count_range = NumericRangeRow("Type P Fund Cnt")
        sec5.add_widget(self.type_p_count_range)
        self.type_v_count_range = NumericRangeRow("Type V Fund Cnt")
        sec5.add_widget(self.type_v_count_range)
        self.main_layout.addWidget(sec5)

        # ── Boolean financial flags ─────────────────────────────────────
        sec6 = CollapsibleSection("Financial Flags")
        self.glp_negative_cb = QCheckBox("GLP Negative")
        self.ul_corridor_cb = QCheckBox("UL in Corridor")
        self.av_gt_prem_cb = QCheckBox("AV > Premium")
        self.iswl_gcv_gt_cb = QCheckBox("ISWL GCV > Current CV")
        self.iswl_gcv_lt_cb = QCheckBox("ISWL GCV < Current CV")
        self.failed_tamra_cb = QCheckBox("Failed TAMRA or GP")
        self.skipped_reinstate_cb = QCheckBox("Skipped Coverage Reinstatement")
        self.within_conversion_cb = QCheckBox("Within Conversion Period")
        for cb in [self.glp_negative_cb, self.ul_corridor_cb, self.av_gt_prem_cb,
                    self.iswl_gcv_gt_cb, self.iswl_gcv_lt_cb, self.failed_tamra_cb,
                    self.skipped_reinstate_cb, self.within_conversion_cb]:
            sec6.add_widget(cb)
        self.main_layout.addWidget(sec6)

    def write_to_criteria(self, criteria):
        # Account values
        criteria.av_greater_than, criteria.av_less_than = self.av_range.get_range()
        criteria.current_sa_greater_than, criteria.current_sa_less_than = self.current_sa_range.get_range()
        criteria.shadow_av_greater_than, criteria.shadow_av_less_than = self.shadow_av_range.get_range()

        # Loans
        criteria.loan_principal_greater_than, criteria.loan_principal_less_than = self.loan_principal_range.get_range()
        criteria.loan_accrued_int_greater_than, criteria.loan_accrued_int_less_than = self.loan_interest_range.get_range()
        criteria.loan_charge_rate = self.loan_charge_rate.value()

        # Premiums
        criteria.prem_ytd_greater_than, criteria.prem_ytd_less_than = self.prem_ytd_range.get_range()
        criteria.additional_prem_greater_than, criteria.additional_prem_less_than = self.additional_prem_range.get_range()
        criteria.total_prem_greater_than, criteria.total_prem_less_than = self.total_prem_range.get_range()

        # 7-Pay / TAMRA
        criteria.seven_pay_greater_than, criteria.seven_pay_less_than = self.seven_pay_range.get_range()
        criteria.seven_pay_av_greater_than, criteria.seven_pay_av_less_than = self.seven_pay_av_range.get_range()
        criteria.accum_mtp_greater_than, criteria.accum_mtp_less_than = self.accum_mtp_range.get_range()
        criteria.accum_glp_greater_than, criteria.accum_glp_less_than = self.accum_glp_range.get_range()
        criteria.accum_wd_greater_than, criteria.accum_wd_less_than = self.accum_wd_range.get_range()

        # Funds
        criteria.fund_ids = self.fund_id.value()
        criteria.fund_id_greater_than, criteria.fund_id_less_than = self.fund_id_range.get_range()
        criteria.fund_id_list = self.fund_id_list.value()
        criteria.premium_allocation_funds = self.prem_alloc_list.selected_codes()
        criteria.type_p_count_greater_than, criteria.type_p_count_less_than = self.type_p_count_range.get_range()
        criteria.type_v_count_greater_than, criteria.type_v_count_less_than = self.type_v_count_range.get_range()

        # Booleans
        criteria.glp_negative = self.glp_negative_cb.isChecked()
        criteria.ul_in_corridor = self.ul_corridor_cb.isChecked()
        criteria.av_gt_premium = self.av_gt_prem_cb.isChecked()
        criteria.iswl_gcv_gt_curr_cv = self.iswl_gcv_gt_cb.isChecked()
        criteria.iswl_gcv_lt_curr_cv = self.iswl_gcv_lt_cb.isChecked()
        criteria.failed_tamra_or_gp = self.failed_tamra_cb.isChecked()
        criteria.skipped_coverage_reinstatement = self.skipped_reinstate_cb.isChecked()
        criteria.within_conversion_period = self.within_conversion_cb.isChecked()

    def reset(self, criteria):
        super().reset(criteria)
        for rng in [self.av_range, self.current_sa_range, self.shadow_av_range,
                     self.loan_principal_range, self.loan_interest_range,
                     self.prem_ytd_range, self.additional_prem_range, self.total_prem_range,
                     self.seven_pay_range, self.seven_pay_av_range,
                     self.accum_mtp_range, self.accum_glp_range, self.accum_wd_range,
                     self.fund_id_range, self.type_p_count_range, self.type_v_count_range]:
            rng.clear()
        self.loan_charge_rate.clear()
        self.fund_id.clear()
        self.fund_id_list.clear()
        self.prem_alloc_list.clear_selection()
        for cb in [self.glp_negative_cb, self.ul_corridor_cb, self.av_gt_prem_cb,
                    self.iswl_gcv_gt_cb, self.iswl_gcv_lt_cb, self.failed_tamra_cb,
                    self.skipped_reinstate_cb, self.within_conversion_cb]:
            cb.setChecked(False)
