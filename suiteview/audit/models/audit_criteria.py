"""
Audit Criteria Data Classes
=============================
Dataclasses capturing all form state for audit query building.

These are pure data containers — no UI dependencies. The AuditQueryBuilder
reads these to construct the dynamic SQL.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RiderCriteria:
    """Criteria for a single rider slot (up to 3 riders supported)."""
    enabled: bool = False
    plancode: str = ""
    person_code: str = ""          # e.g. "00", "40", "50", "60", "01"
    product_line_code: str = ""    # e.g. "U", "0", "I"
    product_indicator: str = ""    # e.g. "09", "11"
    sex_code_67: str = ""          # Rate class sex code on 67 segment
    sex_code_02: str = ""          # Sex code on 02 segment
    rateclass_code_67: str = ""
    change_type: str = ""          # "0"=Terminated, "1"=Paid Up, "2"=Prem paying
    additional_plancode_criteria: str = ""  # "1"=Same as base, "2"=Different
    cola_indicator: str = ""       # "", "0", "1"
    gio_fio_indicator: str = ""    # "", "blank", "N", "Y"
    lives_covered_code: str = ""
    post_issue: bool = False       # Issue date > base coverage issue date
    table_rating: bool = False
    flat_extra: bool = False
    low_issue_date: str = ""
    high_issue_date: str = ""
    low_change_date: str = ""
    high_change_date: str = ""


@dataclass
class BenefitCriteria:
    """Criteria for a single benefit slot (up to 3 benefits)."""
    enabled: bool = False
    benefit_type: str = ""         # benefit code from BenefitDictionary
    subtype: str = ""
    post_issue: bool = False
    cease_date_status: str = ""    # "1"=Equal, "2"=Less, "3"=Greater
    low_cease_date: str = ""
    high_cease_date: str = ""
    # A&H specific
    elimination_period_accident: List[str] = field(default_factory=list)
    elimination_period_sickness: List[str] = field(default_factory=list)
    benefit_period_accident: List[str] = field(default_factory=list)
    benefit_period_sickness: List[str] = field(default_factory=list)


@dataclass
class TransactionCriteria:
    """Criteria for transaction filtering."""
    enabled: bool = False
    transaction_type: str = ""             # Single transaction type combo
    transaction_types: List[str] = field(default_factory=list)  # Multi-select
    low_entry_date: str = ""
    high_entry_date: str = ""
    low_effective_date: str = ""
    high_effective_date: str = ""
    low_effective_month: str = ""
    high_effective_month: str = ""
    low_effective_day: str = ""
    high_effective_day: str = ""
    low_gross_amount: str = ""
    high_gross_amount: str = ""
    origin_of_transaction: str = ""
    on_issue_day: bool = False
    on_issue_month: bool = False
    # 68 segment change codes
    has_change_segment: bool = False
    change_codes_68: List[str] = field(default_factory=list)


@dataclass
class AuditCriteria:
    """
    Complete audit criteria snapshot — captures all form state.
    
    The AuditQueryBuilder reads this to construct the dynamic SQL query.
    All fields default to empty/disabled so only active criteria affect the query.
    """
    
    # ── Connection ──────────────────────────────────────────────────────
    region: str = "CKPR"
    
    # ── Policy-level filters ────────────────────────────────────────────
    company: str = ""              # Company code ("01", "04", etc.) or ""
    market_org: str = ""           # "MLM", "CSSD", "IMG", "DIRECT", or ""
    system_code: str = "I"         # "I"=Individual, "P"=Pension, ""=Any
    branch_number: str = ""
    
    # Max results
    max_count: int = 25
    show_all: bool = False         # If True, no FETCH FIRST N ROWS
    
    # Display mode
    show_all_coverages: bool = False  # True = all covs, False = base only
    
    # ── Multi-select list filters (empty list = no filter) ──────────────
    status_codes: List[str] = field(default_factory=list)
    states: List[str] = field(default_factory=list)
    billing_forms: List[str] = field(default_factory=list)
    slr_billing_forms: List[str] = field(default_factory=list)
    billing_modes: List[str] = field(default_factory=list)
    nfo_options: List[str] = field(default_factory=list)
    loan_types: List[str] = field(default_factory=list)
    primary_div_options: List[str] = field(default_factory=list)
    secondary_div_options: List[str] = field(default_factory=list)
    db_options: List[str] = field(default_factory=list)
    def_of_life_ins: List[str] = field(default_factory=list)
    initial_term_periods: List[str] = field(default_factory=list)
    product_line_codes_all: List[str] = field(default_factory=list)
    product_indicators_all: List[str] = field(default_factory=list)
    cov1_rateclass: List[str] = field(default_factory=list)
    cov1_sex_code: List[str] = field(default_factory=list)
    cov1_sex_code_02: List[str] = field(default_factory=list)
    grace_indicators: List[str] = field(default_factory=list)
    overloan_indicators: List[str] = field(default_factory=list)
    suspense_codes: List[str] = field(default_factory=list)
    grace_period_rules: List[str] = field(default_factory=list)
    reinsurance_codes: List[str] = field(default_factory=list)
    last_entry_codes: List[str] = field(default_factory=list)
    non_trad_indicators: List[str] = field(default_factory=list)
    premium_allocation_funds: List[str] = field(default_factory=list)
    mortality_table_codes: List[str] = field(default_factory=list)
    
    # ── Coverage-level filters ──────────────────────────────────────────
    cov1_plancode: str = ""
    plancode_all_covs: str = ""
    form_number_like: str = ""
    cov1_product_line_code: str = ""
    cov1_product_indicator: str = ""
    
    # Multiple plancodes
    multiple_plancodes: List[str] = field(default_factory=list)
    
    # ── Policy number search ────────────────────────────────────────────
    policy_number_pattern: str = ""     # The search text
    policy_number_criteria: str = ""    # "1"=starts, "2"=ends, "3"=contains
    
    # ── Date ranges (format: "yyyy-mm-dd" or empty) ─────────────────────
    low_issue_date: str = ""
    high_issue_date: str = ""
    low_issue_month: str = ""
    high_issue_month: str = ""
    low_issue_day: str = ""
    high_issue_day: str = ""
    low_paid_to_date: str = ""
    high_paid_to_date: str = ""
    low_last_financial_date: str = ""
    high_last_financial_date: str = ""
    low_app_date: str = ""
    high_app_date: str = ""
    low_gpe_date: str = ""
    high_gpe_date: str = ""
    low_last_change_date: str = ""
    high_last_change_date: str = ""
    low_bill_commence_date: str = ""
    high_bill_commence_date: str = ""
    low_termination_date: str = ""
    high_termination_date: str = ""
    
    # ── Numeric ranges ──────────────────────────────────────────────────
    low_issue_age: str = ""
    high_issue_age: str = ""
    low_current_age: str = ""
    high_current_age: str = ""
    low_current_policy_year: str = ""
    high_current_policy_year: str = ""
    low_billing_prem: str = ""
    high_billing_prem: str = ""
    
    # ── Financial ranges ────────────────────────────────────────────────
    av_greater_than: str = ""
    av_less_than: str = ""
    current_sa_greater_than: str = ""
    current_sa_less_than: str = ""
    shadow_av_greater_than: str = ""
    shadow_av_less_than: str = ""
    accum_mtp_greater_than: str = ""
    accum_mtp_less_than: str = ""
    accum_glp_greater_than: str = ""
    accum_glp_less_than: str = ""
    loan_principal_greater_than: str = ""
    loan_principal_less_than: str = ""
    loan_accrued_int_greater_than: str = ""
    loan_accrued_int_less_than: str = ""
    loan_charge_rate: str = ""
    seven_pay_greater_than: str = ""
    seven_pay_less_than: str = ""
    seven_pay_av_greater_than: str = ""
    seven_pay_av_less_than: str = ""
    accum_wd_greater_than: str = ""
    accum_wd_less_than: str = ""
    prem_ytd_greater_than: str = ""
    prem_ytd_less_than: str = ""
    additional_prem_greater_than: str = ""
    additional_prem_less_than: str = ""
    total_prem_greater_than: str = ""
    total_prem_less_than: str = ""
    type_p_count_greater_than: str = ""
    type_p_count_less_than: str = ""
    type_v_count_greater_than: str = ""
    type_v_count_less_than: str = ""
    fund_ids: str = ""
    fund_id_greater_than: str = ""
    fund_id_less_than: str = ""
    fund_id_list: str = ""
    
    # ── Valuation fields ────────────────────────────────────────────────
    valuation_class: str = ""
    valuation_base: str = ""
    valuation_subseries: str = ""
    valuation_mortality_table: str = ""
    eti_mortality_table: str = ""
    rpu_mortality_table: str = ""
    nfo_interest_rate: str = ""
    
    # ── Boolean criteria checkboxes ─────────────────────────────────────
    table_rating: bool = False
    flat_extra: bool = False
    has_loan: bool = False
    has_preferred_loan: bool = False
    mec: bool = False
    amount_1035: bool = False
    glp_negative: bool = False
    ul_in_corridor: bool = False
    av_gt_premium: bool = False
    current_sa_gt_original: bool = False
    current_sa_lt_original: bool = False
    iswl_gcv_gt_curr_cv: bool = False
    iswl_gcv_lt_curr_cv: bool = False
    multiple_base_coverages: bool = False
    failed_tamra_or_gp: bool = False
    billing_suspended: bool = False
    skipped_coverage_reinstatement: bool = False
    is_mdo: bool = False
    is_rga: bool = False
    has_converted_policy_number: bool = False
    has_replacement_policy_number: bool = False
    cv_rate_gt_zero_on_base: bool = False
    valuation_class_not_plan_description: bool = False
    include_ap_as_base: bool = False
    gio_indicator: bool = False
    cola_indicator: bool = False
    rpu_original_amt: bool = False
    within_conversion_period: bool = False
    
    # ── Rider criteria (up to 3) ────────────────────────────────────────
    rider1: RiderCriteria = field(default_factory=RiderCriteria)
    rider2: RiderCriteria = field(default_factory=RiderCriteria)
    rider3: RiderCriteria = field(default_factory=RiderCriteria)
    
    # ── Benefit criteria (up to 3) ──────────────────────────────────────
    benefit1: BenefitCriteria = field(default_factory=BenefitCriteria)
    benefit2: BenefitCriteria = field(default_factory=BenefitCriteria)
    benefit3: BenefitCriteria = field(default_factory=BenefitCriteria)
    
    # ── Transaction criteria ────────────────────────────────────────────
    transaction: TransactionCriteria = field(default_factory=TransactionCriteria)
    
    # ── Display columns ("Show" checkboxes) ─────────────────────────────
    show_tch_pol_id: bool = False
    show_product_line_code: bool = False
    show_current_duration: bool = False
    show_current_attained_age: bool = False
    show_sex_and_rateclass: bool = False
    show_sex_02: bool = False
    show_substandard: bool = False
    show_specified_amount: bool = False
    show_accumulation_value: bool = False
    show_premium_ptd: bool = False
    show_db_option: bool = False
    show_billing_mode: bool = False
    show_billing_form: bool = False
    show_slr_billing_form: bool = False
    show_billing_control_number: bool = False
    show_billable_premium: bool = False
    show_policy_debt: bool = False
    show_glp: bool = False
    show_gsp: bool = False
    show_gpe_date: bool = False
    show_tamra: bool = False
    show_cost_basis: bool = False
    show_ctp: bool = False
    show_monthly_mtp: bool = False
    show_accum_monthly_mtp: bool = False
    show_accum_glp: bool = False
    show_shadow_av: bool = False
    show_accum_withdrawals: bool = False
    show_premium_paid_ytd: bool = False
    show_mec_status: bool = False
    show_ul_def_of_life_ins: bool = False
    show_trad_overloan_ind: bool = False
    show_converted_policy_number: bool = False
    show_replacement_policy: bool = False
    show_last_entry_code: bool = False
    show_original_entry_code: bool = False
    show_mdo_indicator: bool = False
    show_paid_to_date: bool = False
    show_bill_to_date: bool = False
    show_last_account_date: bool = False
    show_last_financial_date: bool = False
    show_nsp: bool = False
    show_next_notification_date: bool = False
    show_next_year_end_date: bool = False
    show_application_date: bool = False
    show_next_monthliversary_date: bool = False
    show_next_statement_date: bool = False
    show_short_pay_fields: bool = False
    show_reinsured_code: bool = False
    show_cirf_key: bool = False
    show_initial_term_period: bool = False
    show_conversion_period_info: bool = False
    show_conversion_credit_info: bool = False
    show_within_conversion_period: bool = False
    show_subseries: bool = False
    show_prem_calc_rules: bool = False
    show_termination_date: bool = False
    show_trad_cv: bool = False
    show_account_value_02_75: bool = False
    show_market_org_code: bool = False
    
    @property
    def any_rider_active(self) -> bool:
        """Check if any rider criteria is active."""
        return self.rider1.enabled or self.rider2.enabled or self.rider3.enabled
    
    @property
    def any_benefit_active(self) -> bool:
        """Check if any benefit criteria is active."""
        return self.benefit1.enabled or self.benefit2.enabled or self.benefit3.enabled
    
    @property
    def needs_nontrad_join(self) -> bool:
        """Check if the non-traditional policy table join is needed."""
        return (self.show_db_option or self.show_accumulation_value or
                self.show_premium_ptd or self.show_ul_def_of_life_ins or
                self.show_shadow_av or self.show_mec_status or
                self.failed_tamra_or_gp or self.billing_suspended or
                self.ul_in_corridor or self.av_gt_premium or
                bool(self.db_options) or bool(self.def_of_life_ins) or
                bool(self.non_trad_indicators))
    
    @property
    def needs_mvval(self) -> bool:
        """Check if monthliversary value CTE is needed."""
        return (self.show_accumulation_value or self.show_premium_ptd or
                self.ul_in_corridor or self.av_gt_premium or
                self.iswl_gcv_gt_curr_cv or self.iswl_gcv_lt_curr_cv or
                self.av_greater_than != "" or self.av_less_than != "")
    
    @property
    def needs_loan_join(self) -> bool:
        """Check if loan CTE is needed."""
        return (self.has_loan or self.has_preferred_loan or
                self.show_policy_debt or bool(self.loan_types) or
                self.loan_principal_greater_than != "" or
                self.loan_principal_less_than != "")
    
    @property 
    def needs_grace_table(self) -> bool:
        """Check if grace period CTE is needed."""
        return (self.show_gpe_date or
                self.low_gpe_date != "" or self.high_gpe_date != "")
    
    @property
    def needs_covsummary(self) -> bool:
        """Check if COVSUMMARY CTE is needed."""
        return (self.multiple_base_coverages or
                self.current_sa_gt_original or self.current_sa_lt_original or
                self.show_specified_amount or self.ul_in_corridor or
                self.iswl_gcv_gt_curr_cv or self.iswl_gcv_lt_curr_cv)
    
    @property
    def needs_interpolation_months(self) -> bool:
        """Check if INTERPOLATION_MONTHS CTE is needed."""
        return (self.iswl_gcv_gt_curr_cv or self.iswl_gcv_lt_curr_cv or
                self.show_trad_cv or self.show_account_value_02_75)
    
    @property
    def needs_termination_dates(self) -> bool:
        """Check if termination date CTE is needed."""
        return (self.show_termination_date or
                self.low_termination_date != "" or
                self.high_termination_date != "")
    
    @property
    def main_table(self) -> str:
        """Get the main coverage table alias based on display mode."""
        return "COVSALL" if self.show_all_coverages else "COVERAGE1"
    
    def get_active_criteria_summary(self) -> List[str]:
        """Return a list of human-readable strings describing active criteria."""
        active = []
        if self.company:
            from .audit_constants import COMPANY_CODES
            name = COMPANY_CODES.get(self.company, self.company)
            active.append(f"Company: {name}")
        if self.system_code:
            active.append(f"System: {self.system_code}")
        if self.status_codes:
            active.append(f"Status: {', '.join(self.status_codes)}")
        if self.states:
            active.append(f"States: {', '.join(self.states)}")
        if self.cov1_plancode:
            active.append(f"Plancode: {self.cov1_plancode}")
        if self.multiple_plancodes:
            active.append(f"Plancodes: {len(self.multiple_plancodes)}")
        if self.low_issue_date or self.high_issue_date:
            active.append(f"Issue: {self.low_issue_date or '...'} — {self.high_issue_date or '...'}")
        if self.low_issue_age or self.high_issue_age:
            active.append(f"Age: {self.low_issue_age or '...'} — {self.high_issue_age or '...'}")
        if self.has_loan:
            active.append("Has Loan")
        if self.mec:
            active.append("MEC")
        if self.rider1.enabled:
            active.append(f"Rider 1: {self.rider1.plancode or 'any'}")
        if self.rider2.enabled:
            active.append(f"Rider 2: {self.rider2.plancode or 'any'}")
        if self.rider3.enabled:
            active.append(f"Rider 3: {self.rider3.plancode or 'any'}")
        if self.benefit1.enabled:
            active.append(f"Benefit 1: {self.benefit1.benefit_type or 'any'}")
        if self.transaction.enabled:
            active.append("Transaction filter")
        return active
