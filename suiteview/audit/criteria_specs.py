"""Declarative criteria tab specifications and state helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from PyQt6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QListWidget

from suiteview.audit import profile_manager


@dataclass(frozen=True, slots=True)
class FieldSpec:
    key: str
    label: str
    widget_kind: str
    criteria_key: str | None = None
    state_key: str | None = None
    layout_hints: Mapping[str, Any] = field(default_factory=dict)

    @property
    def state_name(self) -> str:
        return self.state_key or self.key

    @property
    def criteria_name(self) -> str:
        return self.criteria_key or self.key


@dataclass(frozen=True, slots=True)
class TabSpec:
    key: str
    label: str
    fields: tuple[FieldSpec, ...]


def checkbox_field(key: str, label: str, **layout_hints: Any) -> FieldSpec:
    return FieldSpec(key, label, "checkbox", layout_hints=layout_hints)


def lineedit_field(key: str, label: str = "") -> FieldSpec:
    return FieldSpec(key, label, "lineedit")


def combo_field(key: str, label: str = "") -> FieldSpec:
    return FieldSpec(key, label, "combo")


def listbox_field(key: str, label: str = "") -> FieldSpec:
    return FieldSpec(key, label, "listbox")


def widget_state(widget: Any, kind: str) -> Any:
    if kind == "checkbox":
        return profile_manager.get_checkbox_checked(widget)
    if kind == "lineedit":
        return profile_manager.get_lineedit_text(widget)
    if kind == "combo":
        return profile_manager.get_combo_text(widget)
    if kind == "listbox":
        return profile_manager.get_listbox_selected(widget)
    raise ValueError(f"Unsupported criteria widget kind: {kind}")


def apply_widget_state(widget: Any, kind: str, value: Any) -> None:
    if kind == "checkbox":
        profile_manager.set_checkbox_checked(widget, bool(value))
    elif kind == "lineedit":
        profile_manager.set_lineedit_text(widget, value or "")
    elif kind == "combo":
        profile_manager.set_combo_text(widget, value or "")
    elif kind == "listbox":
        profile_manager.set_listbox_selected(widget, value or [])
    else:
        raise ValueError(f"Unsupported criteria widget kind: {kind}")


def tab_state(tab: Any, spec: TabSpec) -> dict[str, Any]:
    return {
        field.state_name: widget_state(getattr(tab, field.key), field.widget_kind)
        for field in spec.fields
    }


def apply_tab_state(tab: Any, spec: TabSpec, state: Mapping[str, Any]) -> None:
    for field in spec.fields:
        apply_widget_state(
            getattr(tab, field.key),
            field.widget_kind,
            state.get(field.state_name, _default_value(field.widget_kind)),
        )


def _default_value(kind: str) -> Any:
    if kind == "checkbox":
        return False
    if kind == "listbox":
        return []
    return ""


def assert_tab_spec_matches_widgets(tab: Any, spec: TabSpec) -> None:
    for field in spec.fields:
        widget = getattr(tab, field.key)
        if field.widget_kind == "checkbox" and not isinstance(widget, QCheckBox):
            raise AssertionError(f"{spec.key}.{field.key} is not a QCheckBox")
        if field.widget_kind == "lineedit" and not isinstance(widget, QLineEdit):
            raise AssertionError(f"{spec.key}.{field.key} is not a QLineEdit")
        if field.widget_kind == "combo" and not isinstance(widget, QComboBox):
            raise AssertionError(f"{spec.key}.{field.key} is not a QComboBox")
        if field.widget_kind == "listbox" and not isinstance(widget, QListWidget):
            raise AssertionError(f"{spec.key}.{field.key} is not a QListWidget")


DISPLAY_TAB_SPEC = TabSpec(
    key="display",
    label="Display",
    fields=(
        checkbox_field("chk_paid_to_date", "Paid To Date (01)", column=1, group=1),
        checkbox_field("chk_bill_to_date", "Bill To Date (01)", column=1, group=1),
        checkbox_field("chk_gpe_date", "GPE Date (51 or 66)", column=1, group=1),
        checkbox_field("chk_val_duration", "Val Duration (Calc)", column=1, group=1),
        checkbox_field("chk_val_attained_age", "Val Attained Age (Calc)", column=1, group=1),
        checkbox_field("chk_last_acct_date", "Last Accounting Date (01)", column=1, group=2),
        checkbox_field("chk_last_fin_date", "Last Financial Date (01)", column=1, group=2),
        checkbox_field("chk_next_change_cov1", "Display Next Change (02)", column=1, group=2),
        checkbox_field("chk_application_date", "Application Date", column=1, group=3),
        checkbox_field("chk_next_sched_notif", "Next Scheduled Notification Date", column=1, group=3),
        checkbox_field("chk_next_year_end", "Next Year-End Date", column=1, group=3),
        checkbox_field("chk_next_sched_stmt", "Next Scheduled Statement Date", column=1, group=3),
        checkbox_field("chk_termination_date", "Termination Date (69)", column=1, group=3),
        checkbox_field("chk_converted_pol", "Converted policy info (52)", column=1, group=4),
        checkbox_field("chk_post_conversion", "Show post conversion policy (link)", column=1, group=4),
        checkbox_field("chk_segment52", "Application / conversion fields (52-G)", column=1, group=4),
        checkbox_field("chk_conversion_dates", "Latest SC conversion dates (69)", column=1, group=4),
        checkbox_field("chk_conv_credit", "Conversion Credit Info (52 - PDF)", column=1, group=4),
        checkbox_field("chk_init_term_period", "Initial Term Period (02)", column=1, group=4),
        checkbox_field("chk_disp_conv_period", "Display if within Conversion Period (Calc)", column=1, group=4),
        checkbox_field("chk_disp_conv_period_calc", "Display Conversion Period (Calc)", column=1, group=4),
        checkbox_field("chk_tch_pol_id", "TCH_POL_ID", column=2, group=1),
        checkbox_field("chk_mod_indicator", "MOD Indicator", column=2, group=1),
        checkbox_field("chk_prod_line_code", "Product Line Code (02)", column=2, group=2),
        checkbox_field("chk_billable_prem", "Billable Premium (01)", column=2, group=2),
        checkbox_field("chk_billable_mode", "Billable Mode (01)", column=2, group=2),
        checkbox_field("chk_billable_form", "Billable Form (01)", column=2, group=2),
        checkbox_field("chk_billable_ctrl_num", "Billable Control Number (33)", column=2, group=2),
        checkbox_field("chk_slr_bill_form", "SLR Bill Form (20)", column=2, group=2),
        checkbox_field("chk_short_pay", "Short pay fields (52 and 58)", column=2, group=2),
        checkbox_field("chk_accum_withdrawals", "Accum Withdrawals (60)", column=2, group=2),
        checkbox_field("chk_premiums_ptd", "Premiums PTD (60)", column=2, group=2),
        checkbox_field("chk_premiums_paid_ytd", "Premiums Paid YTD (63)", column=2, group=2),
        checkbox_field("chk_policy_debt", "Policy Debt (77)", column=2, group=2),
        checkbox_field("chk_cost_basis", "Cost Basis (60)", column=2, group=2),
        checkbox_field("chk_prem_calc_rules", "Prem Calc Rules (01)", column=2, group=3),
        checkbox_field("chk_disp_substandard", "Display Substandard (03)", column=3, group=1),
        checkbox_field("chk_disp_sex_rateclass", "Display Sex and Rateclass and Band (67)", column=3, group=1),
        checkbox_field("chk_disp_sex_02", "Display Sex(02)", column=3, group=1),
        checkbox_field("chk_subseries_code", "Subseries Code(02)", column=3, group=1),
        checkbox_field("chk_disp_mkt_org", "Display Market Org Code (01)", column=3, group=1),
        checkbox_field("chk_reinsured_code", "Reinsured Code  (01)", column=3, group=1),
        checkbox_field("chk_last_entry_code", "Last Entry Code  (01)", column=3, group=1),
        checkbox_field("chk_orig_entry_code", "Original Entry Code  (01)", column=3, group=1),
        checkbox_field("chk_mec_status", "MEC Status (01)", column=3, group=1),
        checkbox_field("chk_insured1_info", "Insured1 Info (89)", column=3, group=1),
        checkbox_field("chk_replacement_pol", "Replacement Policy (52-R)", column=3, group=1),
        checkbox_field("chk_active_benefits", "Display active benefits list", column=3, group=2),
        checkbox_field("chk_active_riders", "Display active rider list", column=3, group=2),
        checkbox_field("chk_commission_target", "Commission Target (58)", column=4, group=1),
        checkbox_field("chk_monthly_min_target", "Monthly Min Target (58)", column=4, group=1),
        checkbox_field("chk_accum_monthly_min", "Accum Monthly Min Target (58)", column=4, group=1),
        checkbox_field("chk_accum_glp", "Accum GLP (58)", column=4, group=1),
        checkbox_field("chk_nsp", "NSP (58)", column=4, group=1),
        checkbox_field("chk_gsp", "GSP (67)", column=4, group=1),
        checkbox_field("chk_glp", "GLP (67)", column=4, group=1),
        checkbox_field("chk_tamra", "TAMRA (59)", column=4, group=1),
        checkbox_field("chk_orig_face_rpu", "Original face for RPU policies (68)", column=4, group=2),
        checkbox_field("chk_accum_value", "Accumulation Value (75)", column=4, group=2),
        checkbox_field("chk_trad_cv_cov1", "Trad Cash Value Cov1 (02)", column=4, group=2),
        checkbox_field("chk_account_value", "Account Value  (02 & 75)", column=4, group=2),
        checkbox_field("chk_shadow_av", "Shadow AV (58)", column=4, group=2),
        checkbox_field("chk_disp_orig_curr_sa", "Display original and current specified amount (02)", column=4, group=2),
        checkbox_field("chk_death_benefit_opt", "Death Benefit Option (66)", column=4, group=2),
        checkbox_field("chk_def_life_ins", "Definition of Life Insurance (66)", column=4, group=2),
        checkbox_field("chk_cirf_key", "CIRF Key (55)", column=4, group=3),
        checkbox_field("chk_trad_overloan", "Trad Overloan Indicator  (01)", column=5, group=1),
        checkbox_field("Checkbox_DisplayTradRates", "Trad rates - cov 1\n   Poll Fee (01), Modal Factors (01),\n   Prem Rate (02), Premium (01)", column=5, group=2),
        checkbox_field("chk_monthly_deduction", "Monthly Deduction (75)", column=5, group=3),
    ),
)


POLICY_TAB_STATE_SPEC = TabSpec(
    key="policy",
    label="Policy",
    fields=(
        lineedit_field("txt_plancode"),
        checkbox_field("chk_rga", "RGA (52)"),
        combo_field("cmb_company"),
        combo_field("cmb_market"),
        lineedit_field("txt_form_number"),
        lineedit_field("txt_branch"),
        combo_field("cmb_polnum_criteria"),
        lineedit_field("txt_polnum_value"),
        lineedit_field("txt_issue_age_lo"),
        lineedit_field("txt_issue_age_hi"),
        lineedit_field("txt_current_age_lo"),
        lineedit_field("txt_current_age_hi"),
        lineedit_field("txt_val_age_lo"),
        lineedit_field("txt_val_age_hi"),
        lineedit_field("txt_pol_year_lo"),
        lineedit_field("txt_pol_year_hi"),
        lineedit_field("txt_issue_month_lo"),
        lineedit_field("txt_issue_month_hi"),
        lineedit_field("txt_issue_day_lo"),
        lineedit_field("txt_issue_day_hi"),
        lineedit_field("txt_issued_date_lo"),
        lineedit_field("txt_issued_date_hi"),
        lineedit_field("txt_paid_to_lo"),
        lineedit_field("txt_paid_to_hi"),
        lineedit_field("txt_gpe_date_lo"),
        lineedit_field("txt_gpe_date_hi"),
        lineedit_field("txt_app_date_lo"),
        lineedit_field("txt_app_date_hi"),
        lineedit_field("txt_billing_prem_lo"),
        lineedit_field("txt_billing_prem_hi"),
        checkbox_field("chk_is_mdo", "Is MDO (59)"),
        checkbox_field("chk_multiple_base_covs", "Multiple Base Covs (02)"),
        checkbox_field("chk_in_conversion", "In conversion period (Calc)"),
        checkbox_field("chk_status_code", "Status Code (01)"),
        listbox_field("list_status"),
        checkbox_field("chk_product_line", "Product Line Code"),
        listbox_field("list_product_line"),
        checkbox_field("chk_product_indicator", "Product Indicator"),
        listbox_field("list_product_indicator"),
        checkbox_field("chk_state", "State"),
        listbox_field("list_state"),
        checkbox_field("chk_last_entry", "Last Entry Code"),
        listbox_field("list_last_entry"),
        checkbox_field("chk_suspense", "Suspense Code"),
        listbox_field("list_suspense"),
        checkbox_field("chk_grace_indicator", "Grace Indicator"),
        listbox_field("list_grace_indicator"),
        checkbox_field("chk_bill_mode", "Bill Mode"),
        listbox_field("list_bill_mode"),
        checkbox_field("chk_billing_form", "Billing Form"),
        listbox_field("list_billing_form"),
    ),
)


POLICY2_TAB_STATE_SPEC = TabSpec(
    key="policy2",
    label="Policy (2)",
    fields=(
        lineedit_field("txt_tamra_7pay_prem_lo"),
        lineedit_field("txt_tamra_7pay_prem_hi"),
        lineedit_field("txt_tamra_7pay_av_lo"),
        lineedit_field("txt_tamra_7pay_av_hi"),
        lineedit_field("txt_total_addl_prem_lo"),
        lineedit_field("txt_total_addl_prem_hi"),
        lineedit_field("txt_total_prem_addl_reg_lo"),
        lineedit_field("txt_total_prem_addl_reg_hi"),
        lineedit_field("txt_accum_wd_lo"),
        lineedit_field("txt_accum_wd_hi"),
        lineedit_field("txt_prem_ytd_lo"),
        lineedit_field("txt_prem_ytd_hi"),
        lineedit_field("txt_term_entry_date_lo"),
        lineedit_field("txt_term_entry_date_hi"),
        lineedit_field("txt_bil_commence_dt_lo"),
        lineedit_field("txt_bil_commence_dt_hi"),
        checkbox_field("chk_billing_suspended", "Billing suspended (66)"),
        lineedit_field("txt_last_fin_date_lo"),
        lineedit_field("txt_last_fin_date_hi"),
        lineedit_field("txt_term_last_fin_date_lo"),
        lineedit_field("txt_term_last_fin_date_hi"),
        lineedit_field("txt_term_date_both_lo"),
        lineedit_field("txt_term_date_both_hi"),
        checkbox_field("chk_has_converted", "Has converted policy (52)"),
        checkbox_field("chk_is_replacement", "Is a replacement (52-R)"),
        checkbox_field("chk_has_replacement_pol", "Has a replacement pol (52-R)"),
        checkbox_field("chk_cov_gio", "Cov has GIO ind (02)"),
        checkbox_field("chk_cov_cola", "Cov has COLA ind (02)"),
        checkbox_field("chk_skipped_cov_rein", "Skipped Cov Rein (09)"),
        checkbox_field("chk_1035_amt", "1035 Amt (59)"),
        checkbox_field("chk_mec", "MEC (59)"),
        checkbox_field("chk_failed_guideline", "Failed Guideline or TAMRA (66)"),
        checkbox_field("chk_participating", "Participating (02)"),
        listbox_field("list_participating"),
        checkbox_field("chk_loan_type", "Loan Type (01)"),
        listbox_field("list_loan_type"),
        lineedit_field("txt_loan_charge_rate"),
        checkbox_field("chk_has_loan", "Has Loan (77)"),
        checkbox_field("chk_has_preferred_loan", "Has Preferred Loan (77)"),
        lineedit_field("txt_total_loan_prin_lo"),
        lineedit_field("txt_total_loan_prin_hi"),
        lineedit_field("txt_total_accured_lint_lo"),
        lineedit_field("txt_total_accured_lint_hi"),
        checkbox_field("chk_trad_overloan", "Trad Overloan Indicator"),
        listbox_field("list_trad_overloan"),
        checkbox_field("chk_non_trad", "Non Trad Indicator"),
        listbox_field("list_non_trad"),
        checkbox_field("chk_std_loan_payment", "Standard Loan Payment"),
        listbox_field("list_std_loan_payment"),
        checkbox_field("chk_def_life", "Definition of Life"),
        listbox_field("list_def_life"),
        checkbox_field("chk_reinsurance", "Reinsurance"),
        listbox_field("list_reinsurance"),
        checkbox_field("chk_change_seq", "Has Change Seq (68)"),
        listbox_field("list_change_seq"),
    ),
)

