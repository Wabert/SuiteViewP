"""CyberLife SQL context section builders."""
from __future__ import annotations

from types import MappingProxyType

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
    normalize_date,
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
    collect_advanced_coverage_context(scratch)
    values = {
        key: value
        for key, value in scratch.__dict__.items()
        if key not in {"criteria", "derived"}
    }
    return DerivedAuditContext(
        criteria=criteria,
        values=MappingProxyType(dict(values)),
        initial_ctes=tuple(parts.sql_parts),
    )


def collect_policy2_and_flag_context(ctx: QueryContext, parts: SqlParts) -> None:
    _collect_display2_flags(ctx)
    _collect_policy2_flags(ctx, parts)
    _collect_people_and_adv_flags(ctx)


def _collect_display2_flags(ctx: QueryContext) -> None:
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


def _collect_policy2_flags(ctx: QueryContext, parts: SqlParts) -> None:
    ctx.needs_grace_table = ctx.has_gpe_date or ctx.grace_indicator or ctx.disp_gpe_date
    parts.sql_parts = ['WITH COVERAGE1 AS', f'  (SELECT * FROM {ctx.schema}.LH_COV_PHA C1 WHERE C1.COV_PHA_NBR = 1)']
    _collect_target_total_flags(ctx)
    _collect_policy2_join_flags(ctx)
    _collect_termination_flags(ctx)


def _collect_target_total_flags(ctx: QueryContext) -> None:
    ctx.has_tamra = bool(ctx.p2t.txt_tamra_7pay_prem_lo.strip() or ctx.p2t.txt_tamra_7pay_prem_hi.strip() or ctx.p2t.txt_tamra_7pay_av_lo.strip() or ctx.p2t.txt_tamra_7pay_av_hi.strip() or ctx.p2t.chk_1035_amt or ctx.p2t.chk_mec)
    ctx.has_pol_totals = bool(ctx.p2t.txt_total_addl_prem_lo.strip() or ctx.p2t.txt_total_addl_prem_hi.strip() or ctx.p2t.txt_total_prem_addl_reg_lo.strip() or ctx.p2t.txt_total_prem_addl_reg_hi.strip() or ctx.p2t.txt_accum_wd_lo.strip() or ctx.p2t.txt_accum_wd_hi.strip() or ctx.disp_accum_wd or ctx.disp_cost_basis or ctx.at.chk_prem_wd_gt_face)
    ctx.needs_pol_yr_tot = bool(ctx.p2t.txt_prem_ytd_lo.strip() or ctx.p2t.txt_prem_ytd_hi.strip() or ctx.disp_prem_ytd)


def _collect_policy2_join_flags(ctx: QueryContext) -> None:
    ctx.has_nontrad = bool(ctx.p2t.txt_bil_commence_dt_lo.strip() or ctx.p2t.txt_bil_commence_dt_hi.strip() or ctx.p2t.chk_billing_suspended or ctx.p2t.chk_failed_guideline or ctx.p2t.chk_def_life or (ctx.at.chk_grace_rule and ctx.at.list_grace_rule) or (ctx.at.chk_db_option and ctx.at.list_db_option))
    ctx.has_modcovsall = bool(ctx.p2t.chk_cov_gio or ctx.p2t.chk_cov_cola or ctx.policy_has_product_indicator)
    ctx.has_52r = bool(ctx.p2t.chk_is_replacement or ctx.p2t.chk_has_replacement_pol)
    ctx.has_skipped_rein = ctx.p2t.chk_skipped_cov_rein
    ctx.has_slr = bool(ctx.p2t.chk_std_loan_payment and ctx.p2t.list_std_loan_payment)
    ctx.has_overloan = bool(ctx.p2t.chk_trad_overloan and ctx.p2t.list_trad_overloan)
    _collect_loan_and_change_flags(ctx)


def _collect_loan_and_change_flags(ctx: QueryContext) -> None:
    ctx.has_77_segment = bool(ctx.p2t.chk_has_loan or ctx.p2t.txt_total_loan_prin_lo.strip() or ctx.p2t.txt_total_loan_prin_hi.strip() or ctx.p2t.txt_total_accured_lint_lo.strip() or ctx.p2t.txt_total_accured_lint_hi.strip())
    ctx.has_preferred_loan = ctx.p2t.chk_has_preferred_loan
    if ctx.has_77_segment or ctx.has_preferred_loan:
        ctx.disp_policy_debt = True
    ctx.has_change_seq = bool(ctx.p2t.chk_change_seq and ctx.p2t.list_change_seq)


def _collect_termination_flags(ctx: QueryContext) -> None:
    ctx.has_term_entry = bool(ctx.p2t.txt_term_entry_date_lo.strip() or ctx.p2t.txt_term_entry_date_hi.strip())
    ctx.term_fin_date = termination_financial_date()
    ctx.term_both_date = f'COALESCE(TDB.TERM_ENTRY_DT, {ctx.term_fin_date})'
    ctx.term_fin_predicates = strict_range_predicates(ctx.term_fin_date, ctx.p2t.txt_term_last_fin_date_lo, ctx.p2t.txt_term_last_fin_date_hi, 'date', 'Termination Last Financial Date (01)')
    ctx.term_both_predicates = strict_range_predicates(ctx.term_both_date, ctx.p2t.txt_term_date_both_lo, ctx.p2t.txt_term_date_both_hi, 'date', 'Termination Date (both)')
    ctx.has_term_fin = bool(ctx.term_fin_predicates)
    ctx.has_term_both = bool(ctx.term_both_predicates)


def _collect_people_and_adv_flags(ctx: QueryContext) -> None:
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


def collect_advanced_coverage_context(ctx: QueryContext) -> None:
    """Derive ADV and coverage flags before SQL fragments are assembled."""
    _collect_advanced_search_context(ctx)
    _collect_coverage_value_context(ctx)
    _collect_base_coverage_context(ctx)
    _collect_rider_coverage_context(ctx)
    _collect_coverage_dependency_flags(ctx)


def _collect_advanced_search_context(ctx: QueryContext) -> None:
    """Collect ADV tab filter and display dependencies."""
    ctx.adv_gcv_lt_cv = ctx.at.chk_gcv_lt_cv
    ctx.adv_prem_wd_gt_face = ctx.at.chk_prem_wd_gt_face
    ctx.adv_grace_rule = bool(ctx.at.chk_grace_rule and ctx.at.list_grace_rule)
    ctx.adv_db_option = bool(ctx.at.chk_db_option and ctx.at.list_db_option)
    ctx.adv_orig_entry = bool(ctx.at.chk_orig_entry and ctx.at.list_orig_entry)
    ctx.adv_prem_alloc = bool(ctx.at.chk_prem_alloc and ctx.at.list_prem_alloc)
    ctx.adv_fund_id = ctx.at.txt_fund_id.strip()
    ctx.adv_fund_lo = ctx.at.txt_fund_lo.strip()
    ctx.adv_fund_hi = ctx.at.txt_fund_hi.strip()
    ctx.has_fund_values = bool(ctx.adv_fund_id or ctx.adv_fund_lo or ctx.adv_fund_hi)
    ctx.adv_cirf_match = ctx.at.cbo_cirf_match.strip()
    ctx.adv_cirf_val = ctx.at.txt_cirf.strip()
    ctx.has_accum_val = bool(ctx.at.rng_accum_val[0].strip() or ctx.at.rng_accum_val[1].strip())
    ctx.has_shadow_av = bool(ctx.at.rng_shadow_acct[0].strip() or ctx.at.rng_shadow_acct[1].strip())
    ctx.has_curr_spec_amt = bool(ctx.at.rng_curr_spec_amt[0].strip() or ctx.at.rng_curr_spec_amt[1].strip())
    ctx.has_accum_mtp = bool(ctx.at.rng_accum_mtp[0].strip() or ctx.at.rng_accum_mtp[1].strip())
    ctx.has_accum_glp_range = bool(ctx.at.rng_accum_glp[0].strip() or ctx.at.rng_accum_glp[1].strip())
    ctx.has_glp_range = bool(ctx.at.rng_glp[0].strip() or ctx.at.rng_glp[1].strip())
    ctx.has_gsp_range = bool(ctx.at.rng_gsp[0].strip() or ctx.at.rng_gsp[1].strip())
    ctx.has_type_p = bool(ctx.at.rng_type_p[0].strip() or ctx.at.rng_type_p[1].strip())
    ctx.has_type_v = bool(ctx.at.rng_type_v[0].strip() or ctx.at.rng_type_v[1].strip())
    ctx.multi_base_covs = ctx.pt.chk_multiple_base_covs
    ctx.is_mdo = ctx.pt.chk_is_mdo
    ctx.in_conversion = ctx.pt.chk_in_conversion


def _collect_coverage_value_context(ctx: QueryContext) -> None:
    """Collect coverage tab values that become WHERE predicates."""
    ctx.cov_val_classes = ctx.covt.val_class.selected
    ctx.cov_val_class = ctx.covt.val_class.value.strip()
    ctx.cov_val_base = ctx.covt.val_base.strip()
    ctx.cov_val_sub = ctx.covt.val_sub.strip()
    ctx.cov_val_mort = ctx.covt.val_mort_table.strip()
    ctx.cov_rpu_mort = ctx.covt.rpu_mort_table.strip()
    ctx.cov_eti_mort = ctx.covt.eti_mort_table.strip()
    ctx.cov_nfo_rate = ctx.covt.nfo_int_rate.strip()
    ctx.cov_val_class_ne = ctx.covt.chk_val_class_ne_plan
    ctx.cov_multi_base = ctx.covt.chk_multiple_base
    ctx.cov_gio = ctx.covt.chk_cov_gio
    ctx.cov_cola = ctx.covt.chk_cov_cola
    ctx.cov_skipped_rein = ctx.covt.chk_skipped_cov_rein
    ctx.cov_cv_rate = ctx.covt.chk_cv_rate_gt_zero or (ctx.wl_tab is not None and ctx.wl_tab.chk_cv_rate)
    ctx.cov_gcv_gt_cv = ctx.covt.chk_gcv_gt_cv
    ctx.cov_gcv_lt_cv = ctx.covt.chk_gcv_lt_cv
    ctx.cov_non_trad = bool(ctx.covt.chk_non_trad and ctx.covt.list_non_trad)
    ctx.cov_spec_amt_lo = ctx.covt.txt_spec_amt_lo.strip()
    ctx.cov_spec_amt_hi = ctx.covt.txt_spec_amt_hi.strip()
    ctx.cov_has_spec_amt = bool(ctx.cov_spec_amt_lo or ctx.cov_spec_amt_hi)
    ctx.cov_init_term = bool(ctx.covt.chk_init_term and ctx.covt.list_init_term)
    ctx._bw = ctx.covt.base_cov_widgets


def _collect_base_coverage_context(ctx: QueryContext) -> None:
    """Collect base coverage widget values and their direct dependencies."""
    ctx.cov_base_plancode = ctx._bw["plancode"].strip()
    ctx.cov_base_prod_line = ctx._bw["prod_line"].strip()
    ctx.cov_base_prod_ind = ctx._bw["prod_ind"].strip()
    ctx.cov_base_form_number = ctx._bw["form_number"].strip()
    ctx.cov_base_rateclass = ctx._bw["rateclass"].strip()
    ctx.cov_base_sex67 = ctx._bw["sex_code_67"].strip()
    ctx.cov_base_sex02 = ctx._bw["sex_code_02"].strip()
    ctx.cov_base_person = ctx._bw["person"].strip()
    ctx.cov_base_lives_cov = ctx._bw["lives_cov"].strip()
    ctx.cov_base_change_type = ctx._bw["change_type"].strip()
    ctx.cov_base_cease_code = ctx._bw["cease_code"].selected
    ctx.cov_base_cola_ind = ctx._bw["cola_ind"].strip()
    ctx.cov_base_gio_fio = ctx._bw["gio_fio"].strip()
    ctx.cov_base_table03 = ctx._bw["table_03"]
    ctx.cov_base_flat03 = ctx._bw["flat_03"]
    ctx.cov_base_active_flat03 = ctx._bw["active_flat_03"]
    ctx.cov_base_issue_lo = normalize_date(ctx._bw["issue_date_lo"]) or ""
    ctx.cov_base_issue_hi = normalize_date(ctx._bw["issue_date_hi"]) or ""
    ctx.cov_base_change_lo = normalize_date(ctx._bw["change_date_lo"]) or ""
    ctx.cov_base_change_hi = normalize_date(ctx._bw["change_date_hi"]) or ""
    ctx.cov_needs_modcov1 = bool(ctx.cov_base_prod_ind or ctx.cov_base_cola_ind or ctx.cov_base_gio_fio)
    ctx.cov_needs_renewals = bool(ctx.cov_base_rateclass or ctx.cov_base_sex67)


def _collect_rider_coverage_context(ctx: QueryContext) -> None:
    """Collect rider coverage specs shared by join and display builders."""
    ctx.rider1_info = _rider_info(ctx.covt.rider1_widgets)
    ctx.rider2_info = _rider_info(ctx.covt.rider2_widgets)
    ctx.cov_needs_modcovsall = bool(ctx.cov_gio or ctx.cov_cola)
    ctx.has_modcovsall = ctx.has_modcovsall or ctx.cov_needs_modcovsall
    ctx.has_skipped_rein = ctx.has_skipped_rein or ctx.cov_skipped_rein
    ctx.multi_base_covs = ctx.multi_base_covs or ctx.cov_multi_base


def _collect_coverage_dependency_flags(ctx: QueryContext) -> None:
    """Resolve cross-tab CTE/join dependencies after raw flags are collected."""
    ctx.cov_needs_covsummary = any((ctx.cov_has_spec_amt, ctx.cov_multi_base))
    ctx.cov_needs_iswl_gcv = any((ctx.cov_gcv_gt_cv, ctx.cov_gcv_lt_cv))
    ctx.cov_needs_mvval = any((ctx.cov_gcv_gt_cv, ctx.cov_gcv_lt_cv))
    ctx.needs_mvval = any((
        ctx.adv_cv_corr,
        ctx.adv_accum_gt_prem,
        ctx.has_accum_val,
        ctx.adv_gcv_gt_cv,
        ctx.adv_gcv_lt_cv,
        ctx.cov_needs_mvval,
        ctx.disp_accum_value,
        ctx.disp_prem_ptd,
        ctx.disp_account_value,
        ctx.adv_prem_wd_gt_face,
    ))
    ctx.needs_iswl_gcv = any((ctx.adv_gcv_gt_cv, ctx.adv_gcv_lt_cv, ctx.cov_needs_iswl_gcv))
    ctx.needs_interpolation = any((ctx.needs_iswl_gcv, ctx.disp_trad_cv_cov1, ctx.disp_account_value))
    ctx.needs_covsummary = any((
        ctx.disp_spec_amt,
        ctx.multi_base_covs,
        ctx.adv_cv_corr,
        ctx.adv_sa_lt_orig,
        ctx.adv_sa_gt_orig,
        ctx.has_curr_spec_amt,
        ctx.needs_iswl_gcv,
        ctx.cov_needs_covsummary,
    ))
    ctx.needs_premwd_face = ctx.adv_prem_wd_gt_face
    ctx.cov1_plancode_match_only = ctx.plancode_tab.cov1_only
    ctx._any_cov_plancode = bool(
        any((ctx.pt.txt_plancode.strip(), ctx.plancode_tab.plancodes))
        and not ctx.cov1_plancode_match_only
    )
    ctx._any_cov_product_line = bool(ctx.pt.chk_product_line and selected_codes(ctx.pt.list_product_line))
    ctx.show_product_line_code = ctx._any_cov_product_line
    ctx.needs_covsall = any((
        ctx.has_modcovsall,
        not ctx.coverage_level and any((ctx._any_cov_plancode, ctx._any_cov_product_line)),
    ))
    ctx.disp_trad_rates = ctx.dt.Checkbox_DisplayTradRates
    ctx.cov_base_change_set = bool(ctx.cov_base_change_lo or ctx.cov_base_change_hi)
    ctx.cov_base_vpu_set = bool(ctx._bw["vpu_lo"].strip() or ctx._bw["vpu_hi"].strip())
    ctx.cov_base_specamt_set = bool(ctx._bw["spec_amt_lo"].strip() or ctx._bw["spec_amt_hi"].strip())


def _rider_info(widgets: dict) -> dict:
    info = {}
    info["plancode"] = widgets["plancode"].strip()
    info["prod_line"] = widgets["prod_line"].strip()
    info["prod_ind"] = widgets["prod_ind"].strip()
    info["rateclass"] = widgets["rateclass"].strip()
    info["sex_code_67"] = widgets["sex_code_67"].strip()
    info["sex_code_02"] = widgets["sex_code_02"].strip()
    info["person"] = widgets["person"].strip()
    info["lives_cov"] = widgets["lives_cov"].strip()
    info["change_type"] = widgets["change_type"].strip()
    info["cease_code"] = widgets["cease_code"].selected
    info["cola_ind"] = widgets["cola_ind"].strip()
    info["gio_fio"] = widgets["gio_fio"].strip()
    addl_plancode = widgets.get("addl_plancode")
    info["addl_plancode"] = addl_plancode.strip() if addl_plancode is not None else ""
    info["table_03"] = widgets["table_03"]
    info["flat_03"] = widgets["flat_03"]
    info["active_flat_03"] = widgets["active_flat_03"]
    info["post_issue"] = bool(widgets.get("post_issue", False))
    info["issue_date_lo"] = normalize_date(widgets["issue_date_lo"]) or ""
    info["issue_date_hi"] = normalize_date(widgets["issue_date_hi"]) or ""
    info["change_date_lo"] = normalize_date(widgets["change_date_lo"]) or ""
    info["change_date_hi"] = normalize_date(widgets["change_date_hi"]) or ""
    info["vpu_lo"] = widgets["vpu_lo"].strip()
    info["vpu_hi"] = widgets["vpu_hi"].strip()
    info["spec_amt_lo"] = widgets["spec_amt_lo"].strip()
    info["spec_amt_hi"] = widgets["spec_amt_hi"].strip()
    info["active"] = any(info.values())
    info["needs_covmod"] = bool(info["prod_ind"] or info["cola_ind"] or info["gio_fio"])
    info["needs_renewals"] = bool(info["rateclass"] or info["sex_code_67"])
    return info
