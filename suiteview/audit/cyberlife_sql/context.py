"""CyberLife SQL context section builders."""
from __future__ import annotations

from suiteview.audit.cyberlife_sql.custom_display import build_custom_display
from suiteview.audit.cyberlife_sql.helpers import (
    name_match_predicate,
    termination_financial_date,
)
from suiteview.audit.cyberlife_sql.segment52 import build_segment52
from suiteview.audit.cyberlife_criteria import AuditCriteria
from suiteview.audit.cyberlife_sql.state import (
    DerivedAuditContext,
    QueryContext,
    SqlParts,
)
from suiteview.audit.sql_helpers import (
    selected_codes,
    strict_range_predicates,
)


def collect_base_display_context(ctx: QueryContext, parts: SqlParts) -> None:
    """Build the CyberLife audit SQL from widget-free audit criteria."""
    ctx.schema = ctx.criteria.schema
    ctx.sys_code = ctx.criteria.sys_code
    ctx.max_count_text = ctx.criteria.max_count_text
    ctx.coverage_level = ctx.criteria.coverage_level
    ctx.coverage_scope = ctx.criteria.coverage_scope
    ctx.custom_display_tab = ctx.criteria.custom_display
    ctx.segment52_tab = ctx.criteria.segment52
    ctx.transaction_tab = ctx.criteria.transaction
    ctx.wl_tab = ctx.criteria.wl
    ctx.pt = ctx.criteria.policy
    ctx.dt = ctx.criteria.display
    ctx.p2t = ctx.criteria.policy2
    ctx.at = ctx.criteria.adv
    ctx.covt = ctx.criteria.coverages
    ctx.plancode_tab = ctx.criteria.plancode
    ctx.benefits_tab = ctx.criteria.benefits
    ctx.ppl = ctx.criteria.people
    ctx.result_cov_alias = 'RESULTCOV' if ctx.coverage_level else 'COVERAGE1'
    ctx.result_rnw_alias = 'RESULTCOV_RENEWALS' if ctx.coverage_level else 'COV1_RENEWALS'
    ctx.result_table_alias = 'RESULTCOV_TABLE_RATING' if ctx.coverage_level else 'TABLE_RATING1'
    ctx.result_flat_alias = 'RESULTCOV_FLAT_EXTRA' if ctx.coverage_level else 'FLAT_EXTRA1'
    ctx.custom_select_lines, ctx.custom_join_lines, ctx.custom_where_lines = build_custom_display(ctx.custom_display_tab, ctx.result_cov_alias, ctx.schema)
    ctx.segment52_select_lines, ctx.segment52_where_lines = build_segment52(ctx.segment52_tab, ctx.dt.chk_segment52)
    ctx.has_current_age = bool(ctx.pt.txt_current_age_lo.strip() or ctx.pt.txt_current_age_hi.strip())
    ctx.has_val_age = bool(ctx.pt.txt_val_age_lo.strip() or ctx.pt.txt_val_age_hi.strip())
    ctx.has_pol_year = bool(ctx.pt.txt_pol_year_lo.strip() or ctx.pt.txt_pol_year_hi.strip())
    ctx.has_issue_month = bool(ctx.pt.txt_issue_month_lo.strip() or ctx.pt.txt_issue_month_hi.strip())
    ctx.has_issue_day = bool(ctx.pt.txt_issue_day_lo.strip() or ctx.pt.txt_issue_day_hi.strip())
    ctx.has_paid_to = bool(ctx.pt.txt_paid_to_lo.strip() or ctx.pt.txt_paid_to_hi.strip())
    ctx.has_gpe_date = bool(ctx.pt.txt_gpe_date_lo.strip() or ctx.pt.txt_gpe_date_hi.strip())
    ctx.grace_indicator = bool(ctx.pt.chk_grace_indicator and ctx.pt.list_grace_indicator)
    ctx.has_app_date = bool(ctx.pt.txt_app_date_lo.strip() or ctx.pt.txt_app_date_hi.strip())
    ctx.has_billing_prem = bool(ctx.pt.txt_billing_prem_lo.strip() or ctx.pt.txt_billing_prem_hi.strip())
    ctx.policy_product_indicator_codes = []
    if ctx.pt.chk_product_indicator:
        ctx.policy_product_indicator_codes = selected_codes(ctx.pt.list_product_indicator)
    ctx.policy_has_product_indicator = bool(ctx.policy_product_indicator_codes)
    ctx.disp_paid_to = ctx.dt.chk_paid_to_date
    ctx.disp_bill_to = ctx.dt.chk_bill_to_date
    ctx.disp_duration = ctx.dt.chk_val_duration
    ctx.disp_attained_age = ctx.dt.chk_val_attained_age
    ctx.disp_last_acct = ctx.dt.chk_last_acct_date
    ctx.disp_last_fin = ctx.dt.chk_last_fin_date
    ctx.disp_bill_prem = ctx.dt.chk_billable_prem
    ctx.disp_bill_mode = ctx.dt.chk_billable_mode
    ctx.disp_bill_form = ctx.dt.chk_billable_form
    ctx.disp_mkt_org = ctx.dt.chk_disp_mkt_org
    ctx.disp_reinsured = ctx.dt.chk_reinsured_code
    ctx.disp_last_entry = ctx.dt.chk_last_entry_code
    ctx.disp_orig_entry = ctx.dt.chk_orig_entry_code
    ctx.disp_spec_amt = ctx.dt.chk_disp_orig_curr_sa
    ctx.disp_tch_pol_id = ctx.dt.chk_tch_pol_id
    ctx.disp_mod_indicator = ctx.dt.chk_mod_indicator
    ctx.disp_prod_line = ctx.dt.chk_prod_line_code
    ctx.disp_sex_02 = ctx.dt.chk_disp_sex_02
    ctx.disp_subseries = ctx.dt.chk_subseries_code
    ctx.disp_mec_status = ctx.dt.chk_mec_status
    ctx.disp_app_date = ctx.dt.chk_application_date
    ctx.disp_next_notif = ctx.dt.chk_next_sched_notif
    ctx.disp_next_year_end = ctx.dt.chk_next_year_end
    ctx.disp_next_stmt = ctx.dt.chk_next_sched_stmt
    ctx.disp_next_change = ctx.dt.chk_next_change_cov1
    ctx.disp_init_term = ctx.dt.chk_init_term_period
    ctx.disp_commission_target = ctx.dt.chk_commission_target
    ctx.disp_monthly_mtp = ctx.dt.chk_monthly_min_target
    ctx.disp_accum_mtp = ctx.dt.chk_accum_monthly_min
    ctx.disp_accum_glp = ctx.dt.chk_accum_glp
    ctx.disp_nsp = ctx.dt.chk_nsp
    ctx.disp_shadow_av = ctx.dt.chk_shadow_av
    ctx.disp_db_option = ctx.dt.chk_death_benefit_opt
    ctx.disp_def_life_ins = ctx.dt.chk_def_life_ins
    ctx.disp_short_pay = ctx.dt.chk_short_pay
    ctx.disp_gpe_date = ctx.dt.chk_gpe_date
    ctx.disp_term_date = ctx.dt.chk_termination_date
    ctx.disp_conversion_dates = ctx.dt.chk_conversion_dates
    ctx.disp_accum_wd = ctx.dt.chk_accum_withdrawals
    ctx.disp_cost_basis = ctx.dt.chk_cost_basis
    ctx.disp_prem_ptd = ctx.dt.chk_premiums_ptd
    ctx.disp_prem_ytd = ctx.dt.chk_premiums_paid_ytd
    ctx.disp_accum_value = ctx.dt.chk_accum_value
    ctx.disp_policy_debt = ctx.dt.chk_policy_debt
    ctx.disp_substandard = ctx.dt.chk_disp_substandard


def derive_audit_flags(criteria: AuditCriteria) -> DerivedAuditContext:
    """Compute the stable CyberLife SQL flags once from collected criteria."""
    scratch = QueryContext(criteria)
    parts = SqlParts()
    collect_base_display_context(scratch, parts)
    collect_policy2_and_flag_context(scratch, parts)
    from suiteview.audit.cyberlife_sql.ctes_policy import add_policy2_ctes

    add_policy2_ctes(scratch, parts)
    values = {
        key: value
        for key, value in scratch.__dict__.items()
        if key not in {"criteria", "derived"}
    }
    return DerivedAuditContext(
        criteria=criteria,
        values=values,
        initial_ctes=tuple(parts.sql_parts),
    )


def collect_policy2_and_flag_context(ctx: QueryContext, parts: SqlParts) -> None:
    ctx.disp_sex_rateclass = ctx.dt.chk_disp_sex_rateclass
    ctx.disp_tamra = ctx.dt.chk_tamra
    ctx.disp_gsp = ctx.dt.chk_gsp
    ctx.disp_glp = ctx.dt.chk_glp
    ctx.disp_bill_ctrl_num = ctx.dt.chk_billable_ctrl_num
    ctx.disp_slr_bill_form = ctx.dt.chk_slr_bill_form
    ctx.disp_orig_face_rpu = ctx.dt.chk_orig_face_rpu
    ctx.disp_prem_calc_rules = ctx.dt.chk_prem_calc_rules
    ctx.disp_cirf_key = ctx.dt.chk_cirf_key
    ctx.disp_trad_overloan = ctx.dt.chk_trad_overloan
    ctx.disp_replacement_pol = ctx.dt.chk_replacement_pol
    ctx.disp_converted_pol = ctx.dt.chk_converted_pol
    ctx.disp_post_conversion = ctx.dt.chk_post_conversion
    ctx.disp_conv_credit = ctx.dt.chk_conv_credit
    ctx.disp_within_conv = ctx.dt.chk_disp_conv_period
    ctx.disp_conv_period = ctx.dt.chk_disp_conv_period_calc
    ctx.disp_trad_cv_cov1 = ctx.dt.chk_trad_cv_cov1
    ctx.disp_account_value = ctx.dt.chk_account_value
    ctx.disp_insured1_info = ctx.dt.chk_insured1_info
    ctx.disp_monthly_deduction = ctx.dt.chk_monthly_deduction
    ctx.disp_active_benefits = ctx.dt.chk_active_benefits
    ctx.disp_active_riders = ctx.dt.chk_active_riders
    ctx.needs_grace_table = ctx.has_gpe_date or ctx.grace_indicator or ctx.disp_gpe_date
    parts.sql_parts = ['WITH COVERAGE1 AS', f'  (SELECT * FROM {ctx.schema}.LH_COV_PHA C1 WHERE C1.COV_PHA_NBR = 1)']
    ctx.has_tamra = bool(ctx.p2t.txt_tamra_7pay_prem_lo.strip() or ctx.p2t.txt_tamra_7pay_prem_hi.strip() or ctx.p2t.txt_tamra_7pay_av_lo.strip() or ctx.p2t.txt_tamra_7pay_av_hi.strip() or ctx.p2t.chk_1035_amt or ctx.p2t.chk_mec)
    ctx.has_pol_totals = bool(ctx.p2t.txt_total_addl_prem_lo.strip() or ctx.p2t.txt_total_addl_prem_hi.strip() or ctx.p2t.txt_total_prem_addl_reg_lo.strip() or ctx.p2t.txt_total_prem_addl_reg_hi.strip() or ctx.p2t.txt_accum_wd_lo.strip() or ctx.p2t.txt_accum_wd_hi.strip() or ctx.disp_accum_wd or ctx.disp_cost_basis or ctx.at.chk_prem_wd_gt_face)
    ctx.needs_pol_yr_tot = bool(ctx.p2t.txt_prem_ytd_lo.strip() or ctx.p2t.txt_prem_ytd_hi.strip() or ctx.disp_prem_ytd)
    ctx.has_nontrad = bool(ctx.p2t.txt_bil_commence_dt_lo.strip() or ctx.p2t.txt_bil_commence_dt_hi.strip() or ctx.p2t.chk_billing_suspended or ctx.p2t.chk_failed_guideline or ctx.p2t.chk_def_life or (ctx.at.chk_grace_rule and ctx.at.list_grace_rule) or (ctx.at.chk_db_option and ctx.at.list_db_option))
    ctx.has_modcovsall = bool(ctx.p2t.chk_cov_gio or ctx.p2t.chk_cov_cola or ctx.policy_has_product_indicator)
    ctx.has_52r = bool(ctx.p2t.chk_is_replacement or ctx.p2t.chk_has_replacement_pol)
    ctx.has_skipped_rein = ctx.p2t.chk_skipped_cov_rein
    ctx.has_slr = bool(ctx.p2t.chk_std_loan_payment and ctx.p2t.list_std_loan_payment)
    ctx.has_overloan = bool(ctx.p2t.chk_trad_overloan and ctx.p2t.list_trad_overloan)
    ctx.has_term_entry = bool(ctx.p2t.txt_term_entry_date_lo.strip() or ctx.p2t.txt_term_entry_date_hi.strip())
    ctx.term_fin_date = termination_financial_date()
    ctx.term_both_date = f'COALESCE(TDB.TERM_ENTRY_DT, {ctx.term_fin_date})'
    ctx.term_fin_predicates = strict_range_predicates(ctx.term_fin_date, ctx.p2t.txt_term_last_fin_date_lo, ctx.p2t.txt_term_last_fin_date_hi, 'date', 'Termination Last Financial Date (01)')
    ctx.term_both_predicates = strict_range_predicates(ctx.term_both_date, ctx.p2t.txt_term_date_both_lo, ctx.p2t.txt_term_date_both_hi, 'date', 'Termination Date (both)')
    ctx.has_term_fin = bool(ctx.term_fin_predicates)
    ctx.has_term_both = bool(ctx.term_both_predicates)
    ctx.has_77_segment = bool(ctx.p2t.chk_has_loan or ctx.p2t.txt_total_loan_prin_lo.strip() or ctx.p2t.txt_total_loan_prin_hi.strip() or ctx.p2t.txt_total_accured_lint_lo.strip() or ctx.p2t.txt_total_accured_lint_hi.strip())
    ctx.has_preferred_loan = ctx.p2t.chk_has_preferred_loan
    if ctx.has_77_segment or ctx.has_preferred_loan:
        ctx.disp_policy_debt = True
    ctx.has_change_seq = bool(ctx.p2t.chk_change_seq and ctx.p2t.list_change_seq)
    ctx.person_name_conds = []
    if ctx.ppl is not None:
        ctx._person_first_name = ctx.ppl.txt_first_name.strip()
        if ctx._person_first_name:
            ctx.person_name_conds.append(name_match_predicate('PERSONINFO.CK_FST_NM', ctx.ppl.cmb_first_name_match, ctx._person_first_name))
        ctx._person_last_name = ctx.ppl.txt_last_name.strip()
        if ctx._person_last_name:
            ctx.person_name_conds.append(name_match_predicate('PERSONINFO.CK_LST_NM', ctx.ppl.cmb_last_name_match, ctx._person_last_name))
    ctx.has_person_info = bool(ctx.person_name_conds)
    ctx.adv_cv_corr = ctx.at.chk_cv_corr
    ctx.adv_accum_gt_prem = ctx.at.chk_accum_gt_prem
    ctx.adv_glp_neg = ctx.at.chk_glp_neg
    ctx.adv_sa_lt_orig = ctx.at.chk_sa_lt_orig
    ctx.adv_sa_gt_orig = ctx.at.chk_sa_gt_orig
    ctx.adv_apb_rider = ctx.at.chk_apb_rider
    ctx.adv_gcv_gt_cv = ctx.at.chk_gcv_gt_cv
