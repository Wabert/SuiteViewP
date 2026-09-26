"""CyberLife SQL context section builders."""
from __future__ import annotations

from .common import (
    PARTICIPATION_CODES,
    PARTICIPATION_TYPE_DESCRIPTIONS,
    QueryContext,
    SqlParts,
    _ISS_STATE_MAP,
    _STATE_ABBR_TO_CODE,
    build_custom_display,
    build_segment52,
    _conversion_sc_cte,
    _post_conversion_cte,
    _valuation_date_sql,
    add_date_range,
    add_decimal_range,
    add_int_range,
    build_bill_mode_where,
    cease_code_predicate,
    esc,
    in_list,
    name_match_predicate,
    normalize_date,
    participation_description,
    participation_predicate,
    selected_codes,
    strict_range_predicates,
    termination_financial_date,
    today_str,
    transaction_predicates,
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
    ctx.segment52_select_lines, ctx.segment52_where_lines = build_segment52(ctx.segment52_tab, ctx.dt.chk_segment52.isChecked())
    ctx.has_current_age = bool(ctx.pt.txt_current_age_lo.text().strip() or ctx.pt.txt_current_age_hi.text().strip())
    ctx.has_val_age = bool(ctx.pt.txt_val_age_lo.text().strip() or ctx.pt.txt_val_age_hi.text().strip())
    ctx.has_pol_year = bool(ctx.pt.txt_pol_year_lo.text().strip() or ctx.pt.txt_pol_year_hi.text().strip())
    ctx.has_issue_month = bool(ctx.pt.txt_issue_month_lo.text().strip() or ctx.pt.txt_issue_month_hi.text().strip())
    ctx.has_issue_day = bool(ctx.pt.txt_issue_day_lo.text().strip() or ctx.pt.txt_issue_day_hi.text().strip())
    ctx.has_paid_to = bool(ctx.pt.txt_paid_to_lo.text().strip() or ctx.pt.txt_paid_to_hi.text().strip())
    ctx.has_gpe_date = bool(ctx.pt.txt_gpe_date_lo.text().strip() or ctx.pt.txt_gpe_date_hi.text().strip())
    ctx.grace_indicator = bool(ctx.pt.chk_grace_indicator.isChecked() and ctx.pt.list_grace_indicator.selectedItems())
    ctx.has_app_date = bool(ctx.pt.txt_app_date_lo.text().strip() or ctx.pt.txt_app_date_hi.text().strip())
    ctx.has_billing_prem = bool(ctx.pt.txt_billing_prem_lo.text().strip() or ctx.pt.txt_billing_prem_hi.text().strip())
    ctx.policy_product_indicator_codes = []
    if ctx.pt.chk_product_indicator.isChecked():
        ctx.policy_product_indicator_codes = selected_codes(ctx.pt.list_product_indicator)
    ctx.policy_has_product_indicator = bool(ctx.policy_product_indicator_codes)
    ctx.disp_paid_to = ctx.dt.chk_paid_to_date.isChecked()
    ctx.disp_bill_to = ctx.dt.chk_bill_to_date.isChecked()
    ctx.disp_duration = ctx.dt.chk_val_duration.isChecked()
    ctx.disp_attained_age = ctx.dt.chk_val_attained_age.isChecked()
    ctx.disp_last_acct = ctx.dt.chk_last_acct_date.isChecked()
    ctx.disp_last_fin = ctx.dt.chk_last_fin_date.isChecked()
    ctx.disp_bill_prem = ctx.dt.chk_billable_prem.isChecked()
    ctx.disp_bill_mode = ctx.dt.chk_billable_mode.isChecked()
    ctx.disp_bill_form = ctx.dt.chk_billable_form.isChecked()
    ctx.disp_mkt_org = ctx.dt.chk_disp_mkt_org.isChecked()
    ctx.disp_reinsured = ctx.dt.chk_reinsured_code.isChecked()
    ctx.disp_last_entry = ctx.dt.chk_last_entry_code.isChecked()
    ctx.disp_orig_entry = ctx.dt.chk_orig_entry_code.isChecked()
    ctx.disp_spec_amt = ctx.dt.chk_disp_orig_curr_sa.isChecked()
    ctx.disp_tch_pol_id = ctx.dt.chk_tch_pol_id.isChecked()
    ctx.disp_mod_indicator = ctx.dt.chk_mod_indicator.isChecked()
    ctx.disp_prod_line = ctx.dt.chk_prod_line_code.isChecked()
    ctx.disp_sex_02 = ctx.dt.chk_disp_sex_02.isChecked()
    ctx.disp_subseries = ctx.dt.chk_subseries_code.isChecked()
    ctx.disp_mec_status = ctx.dt.chk_mec_status.isChecked()
    ctx.disp_app_date = ctx.dt.chk_application_date.isChecked()
    ctx.disp_next_notif = ctx.dt.chk_next_sched_notif.isChecked()
    ctx.disp_next_year_end = ctx.dt.chk_next_year_end.isChecked()
    ctx.disp_next_stmt = ctx.dt.chk_next_sched_stmt.isChecked()
    ctx.disp_next_change = ctx.dt.chk_next_change_cov1.isChecked()
    ctx.disp_init_term = ctx.dt.chk_init_term_period.isChecked()
    ctx.disp_commission_target = ctx.dt.chk_commission_target.isChecked()
    ctx.disp_monthly_mtp = ctx.dt.chk_monthly_min_target.isChecked()
    ctx.disp_accum_mtp = ctx.dt.chk_accum_monthly_min.isChecked()
    ctx.disp_accum_glp = ctx.dt.chk_accum_glp.isChecked()
    ctx.disp_nsp = ctx.dt.chk_nsp.isChecked()
    ctx.disp_shadow_av = ctx.dt.chk_shadow_av.isChecked()
    ctx.disp_db_option = ctx.dt.chk_death_benefit_opt.isChecked()
    ctx.disp_def_life_ins = ctx.dt.chk_def_life_ins.isChecked()
    ctx.disp_short_pay = ctx.dt.chk_short_pay.isChecked()
    ctx.disp_gpe_date = ctx.dt.chk_gpe_date.isChecked()
    ctx.disp_term_date = ctx.dt.chk_termination_date.isChecked()
    ctx.disp_conversion_dates = ctx.dt.chk_conversion_dates.isChecked()
    ctx.disp_accum_wd = ctx.dt.chk_accum_withdrawals.isChecked()
    ctx.disp_cost_basis = ctx.dt.chk_cost_basis.isChecked()
    ctx.disp_prem_ptd = ctx.dt.chk_premiums_ptd.isChecked()
    ctx.disp_prem_ytd = ctx.dt.chk_premiums_paid_ytd.isChecked()
    ctx.disp_accum_value = ctx.dt.chk_accum_value.isChecked()
    ctx.disp_policy_debt = ctx.dt.chk_policy_debt.isChecked()
    ctx.disp_substandard = ctx.dt.chk_disp_substandard.isChecked()


def collect_policy2_and_flag_context(ctx: QueryContext, parts: SqlParts) -> None:
    ctx.disp_sex_rateclass = ctx.dt.chk_disp_sex_rateclass.isChecked()
    ctx.disp_tamra = ctx.dt.chk_tamra.isChecked()
    ctx.disp_gsp = ctx.dt.chk_gsp.isChecked()
    ctx.disp_glp = ctx.dt.chk_glp.isChecked()
    ctx.disp_bill_ctrl_num = ctx.dt.chk_billable_ctrl_num.isChecked()
    ctx.disp_slr_bill_form = ctx.dt.chk_slr_bill_form.isChecked()
    ctx.disp_orig_face_rpu = ctx.dt.chk_orig_face_rpu.isChecked()
    ctx.disp_prem_calc_rules = ctx.dt.chk_prem_calc_rules.isChecked()
    ctx.disp_cirf_key = ctx.dt.chk_cirf_key.isChecked()
    ctx.disp_trad_overloan = ctx.dt.chk_trad_overloan.isChecked()
    ctx.disp_replacement_pol = ctx.dt.chk_replacement_pol.isChecked()
    ctx.disp_converted_pol = ctx.dt.chk_converted_pol.isChecked()
    ctx.disp_post_conversion = ctx.dt.chk_post_conversion.isChecked()
    ctx.disp_conv_credit = ctx.dt.chk_conv_credit.isChecked()
    ctx.disp_within_conv = ctx.dt.chk_disp_conv_period.isChecked()
    ctx.disp_conv_period = ctx.dt.chk_disp_conv_period_calc.isChecked()
    ctx.disp_trad_cv_cov1 = ctx.dt.chk_trad_cv_cov1.isChecked()
    ctx.disp_account_value = ctx.dt.chk_account_value.isChecked()
    ctx.disp_insured1_info = ctx.dt.chk_insured1_info.isChecked()
    ctx.disp_monthly_deduction = ctx.dt.chk_monthly_deduction.isChecked()
    ctx.disp_active_benefits = ctx.dt.chk_active_benefits.isChecked()
    ctx.disp_active_riders = ctx.dt.chk_active_riders.isChecked()
    ctx.needs_grace_table = ctx.has_gpe_date or ctx.grace_indicator or ctx.disp_gpe_date
    parts.sql_parts = ['WITH COVERAGE1 AS', f'  (SELECT * FROM {ctx.schema}.LH_COV_PHA C1 WHERE C1.COV_PHA_NBR = 1)']
    ctx.has_tamra = bool(ctx.p2t.txt_tamra_7pay_prem_lo.text().strip() or ctx.p2t.txt_tamra_7pay_prem_hi.text().strip() or ctx.p2t.txt_tamra_7pay_av_lo.text().strip() or ctx.p2t.txt_tamra_7pay_av_hi.text().strip() or ctx.p2t.chk_1035_amt.isChecked() or ctx.p2t.chk_mec.isChecked())
    ctx.has_pol_totals = bool(ctx.p2t.txt_total_addl_prem_lo.text().strip() or ctx.p2t.txt_total_addl_prem_hi.text().strip() or ctx.p2t.txt_total_prem_addl_reg_lo.text().strip() or ctx.p2t.txt_total_prem_addl_reg_hi.text().strip() or ctx.p2t.txt_accum_wd_lo.text().strip() or ctx.p2t.txt_accum_wd_hi.text().strip() or ctx.disp_accum_wd or ctx.disp_cost_basis or ctx.at.chk_prem_wd_gt_face.isChecked())
    ctx.needs_pol_yr_tot = bool(ctx.p2t.txt_prem_ytd_lo.text().strip() or ctx.p2t.txt_prem_ytd_hi.text().strip() or ctx.disp_prem_ytd)
    ctx.has_nontrad = bool(ctx.p2t.txt_bil_commence_dt_lo.text().strip() or ctx.p2t.txt_bil_commence_dt_hi.text().strip() or ctx.p2t.chk_billing_suspended.isChecked() or ctx.p2t.chk_failed_guideline.isChecked() or ctx.p2t.chk_def_life.isChecked() or (ctx.at.chk_grace_rule.isChecked() and ctx.at.list_grace_rule.selectedItems()) or (ctx.at.chk_db_option.isChecked() and ctx.at.list_db_option.selectedItems()))
    ctx.has_modcovsall = bool(ctx.p2t.chk_cov_gio.isChecked() or ctx.p2t.chk_cov_cola.isChecked() or ctx.policy_has_product_indicator)
    ctx.has_52r = bool(ctx.p2t.chk_is_replacement.isChecked() or ctx.p2t.chk_has_replacement_pol.isChecked())
    ctx.has_skipped_rein = ctx.p2t.chk_skipped_cov_rein.isChecked()
    ctx.has_slr = bool(ctx.p2t.chk_std_loan_payment.isChecked() and ctx.p2t.list_std_loan_payment.selectedItems())
    ctx.has_overloan = bool(ctx.p2t.chk_trad_overloan.isChecked() and ctx.p2t.list_trad_overloan.selectedItems())
    ctx.has_term_entry = bool(ctx.p2t.txt_term_entry_date_lo.text().strip() or ctx.p2t.txt_term_entry_date_hi.text().strip())
    ctx.term_fin_date = termination_financial_date()
    ctx.term_both_date = f'COALESCE(TDB.TERM_ENTRY_DT, {ctx.term_fin_date})'
    ctx.term_fin_predicates = strict_range_predicates(ctx.term_fin_date, ctx.p2t.txt_term_last_fin_date_lo.text(), ctx.p2t.txt_term_last_fin_date_hi.text(), 'date', 'Termination Last Financial Date (01)')
    ctx.term_both_predicates = strict_range_predicates(ctx.term_both_date, ctx.p2t.txt_term_date_both_lo.text(), ctx.p2t.txt_term_date_both_hi.text(), 'date', 'Termination Date (both)')
    ctx.has_term_fin = bool(ctx.term_fin_predicates)
    ctx.has_term_both = bool(ctx.term_both_predicates)
    ctx.has_77_segment = bool(ctx.p2t.chk_has_loan.isChecked() or ctx.p2t.txt_total_loan_prin_lo.text().strip() or ctx.p2t.txt_total_loan_prin_hi.text().strip() or ctx.p2t.txt_total_accured_lint_lo.text().strip() or ctx.p2t.txt_total_accured_lint_hi.text().strip())
    ctx.has_preferred_loan = ctx.p2t.chk_has_preferred_loan.isChecked()
    if ctx.has_77_segment or ctx.has_preferred_loan:
        ctx.disp_policy_debt = True
    ctx.has_change_seq = bool(ctx.p2t.chk_change_seq.isChecked() and ctx.p2t.list_change_seq.selectedItems())
    ctx.person_name_conds = []
    if ctx.ppl is not None:
        ctx._person_first_name = ctx.ppl.txt_first_name.text().strip()
        if ctx._person_first_name:
            ctx.person_name_conds.append(name_match_predicate('PERSONINFO.CK_FST_NM', ctx.ppl.cmb_first_name_match.currentText(), ctx._person_first_name))
        ctx._person_last_name = ctx.ppl.txt_last_name.text().strip()
        if ctx._person_last_name:
            ctx.person_name_conds.append(name_match_predicate('PERSONINFO.CK_LST_NM', ctx.ppl.cmb_last_name_match.currentText(), ctx._person_last_name))
    ctx.has_person_info = bool(ctx.person_name_conds)
    ctx.adv_cv_corr = ctx.at.chk_cv_corr.isChecked()
    ctx.adv_accum_gt_prem = ctx.at.chk_accum_gt_prem.isChecked()
    ctx.adv_glp_neg = ctx.at.chk_glp_neg.isChecked()
    ctx.adv_sa_lt_orig = ctx.at.chk_sa_lt_orig.isChecked()
    ctx.adv_sa_gt_orig = ctx.at.chk_sa_gt_orig.isChecked()
    ctx.adv_apb_rider = ctx.at.chk_apb_rider.isChecked()
    ctx.adv_gcv_gt_cv = ctx.at.chk_gcv_gt_cv.isChecked()

