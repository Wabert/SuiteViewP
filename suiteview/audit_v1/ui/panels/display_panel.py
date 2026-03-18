"""
Display Columns Panel
=======================
Checkboxes controlling which optional columns appear in the result set.
Grouped logically; Select-All / Clear-All for convenience.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QPushButton, QLabel, QFrame,
)

from .panel_widgets import CriteriaPanel, CollapsibleSection


# ── Display groups  (attr_name on AuditCriteria, label for checkbox) ──
DISPLAY_GROUPS: dict[str, list[tuple[str, str]]] = {
    "Policy Info": [
        ("show_tch_pol_id", "TCH Policy ID"),
        ("show_product_line_code", "Product Line Code"),
        ("show_current_duration", "Current Duration"),
        ("show_current_attained_age", "Attained Age"),
        ("show_sex_and_rateclass", "Sex & Rate Class"),
        ("show_sex_02", "Sex 02"),
        ("show_substandard", "Substandard"),
        ("show_market_org_code", "Market Org Code"),
    ],
    "Values / Amounts": [
        ("show_specified_amount", "Specified Amount"),
        ("show_accumulation_value", "Accumulation Value"),
        ("show_premium_ptd", "Premium PTD"),
        ("show_shadow_av", "Shadow AV"),
        ("show_policy_debt", "Policy Debt"),
        ("show_cost_basis", "Cost Basis"),
        ("show_account_value_02_75", "Account Value 02/75"),
    ],
    "Death Benefit / UL": [
        ("show_db_option", "DB Option"),
        ("show_ul_def_of_life_ins", "UL Def of Life Ins"),
        ("show_mec_status", "MEC Status"),
        ("show_trad_overloan_ind", "Trad Overloan Indicator"),
    ],
    "Billing": [
        ("show_billing_mode", "Billing Mode"),
        ("show_billing_form", "Billing Form"),
        ("show_slr_billing_form", "SLR Billing Form"),
        ("show_billing_control_number", "Billing Control #"),
        ("show_billable_premium", "Billable Premium"),
    ],
    "Guideline Premiums / TAMRA": [
        ("show_glp", "GLP"),
        ("show_gsp", "GSP"),
        ("show_gpe_date", "GPE Date"),
        ("show_tamra", "TAMRA (7-Pay)"),
        ("show_ctp", "CTP"),
        ("show_monthly_mtp", "Monthly MTP"),
        ("show_accum_monthly_mtp", "Accum Monthly MTP"),
        ("show_accum_glp", "Accum GLP"),
    ],
    "Premiums / Withdrawals": [
        ("show_premium_paid_ytd", "Premium Paid YTD"),
        ("show_accum_withdrawals", "Accum Withdrawals"),
        ("show_nsp", "NSP"),
    ],
    "Dates": [
        ("show_paid_to_date", "Paid-To Date"),
        ("show_bill_to_date", "Bill-To Date"),
        ("show_last_account_date", "Last Account Date"),
        ("show_last_financial_date", "Last Financial Date"),
        ("show_next_notification_date", "Next Notification Date"),
        ("show_next_year_end_date", "Next Year-End Date"),
        ("show_application_date", "Application Date"),
        ("show_next_monthliversary_date", "Next Monthliversary Date"),
        ("show_next_statement_date", "Next Statement Date"),
        ("show_termination_date", "Termination Date"),
    ],
    "Codes / IDs": [
        ("show_converted_policy_number", "Converted Policy #"),
        ("show_replacement_policy", "Replacement Policy"),
        ("show_last_entry_code", "Last Entry Code"),
        ("show_original_entry_code", "Original Entry Code"),
        ("show_mdo_indicator", "MDO Indicator"),
        ("show_reinsured_code", "Reinsured Code"),
        ("show_cirf_key", "CIRF Key"),
    ],
    "Term / Conversion": [
        ("show_initial_term_period", "Initial Term Period"),
        ("show_conversion_period_info", "Conversion Period Info"),
        ("show_conversion_credit_info", "Conversion Credit Info"),
        ("show_within_conversion_period", "Within Conversion Period"),
        ("show_subseries", "Subseries"),
    ],
    "Other": [
        ("show_short_pay_fields", "Short-Pay Fields"),
        ("show_prem_calc_rules", "Premium Calc Rules"),
        ("show_trad_cv", "Trad Cash Value"),
    ],
}


class DisplayPanel(CriteriaPanel):
    """Check-boxes that control which optional columns appear in the results."""

    def _build_ui(self):
        # ── Select All / Clear All bar ──────────────────────────────────
        bar = QFrame()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(6)

        lbl = QLabel("Toggle display columns:")
        lbl.setStyleSheet("font-weight: bold; font-size: 9pt;")
        bar_layout.addWidget(lbl)

        btn_all = QPushButton("Select All")
        btn_all.setFixedWidth(80)
        btn_all.clicked.connect(self._select_all)
        bar_layout.addWidget(btn_all)

        btn_clear = QPushButton("Clear All")
        btn_clear.setFixedWidth(80)
        btn_clear.clicked.connect(self._clear_all)
        bar_layout.addWidget(btn_clear)

        bar_layout.addStretch()
        self.main_layout.addWidget(bar)

        # ── Build checkbox groups ───────────────────────────────────────
        self._checkboxes: dict[str, QCheckBox] = {}

        for group_name, items in DISPLAY_GROUPS.items():
            sec = CollapsibleSection(group_name)
            for attr, label in items:
                cb = QCheckBox(label)
                self._checkboxes[attr] = cb
                sec.add_widget(cb)
            self.main_layout.addWidget(sec)

    # ── helpers ─────────────────────────────────────────────────────────
    def _select_all(self):
        for cb in self._checkboxes.values():
            cb.setChecked(True)

    def _clear_all(self):
        for cb in self._checkboxes.values():
            cb.setChecked(False)

    # ── CriteriaPanel interface ─────────────────────────────────────────
    def write_to_criteria(self, criteria):
        for attr, cb in self._checkboxes.items():
            setattr(criteria, attr, cb.isChecked())

    def reset(self):
        self._clear_all()
