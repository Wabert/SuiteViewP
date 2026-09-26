"""CyberLife SQL where policy section builders."""
from __future__ import annotations

from suiteview.audit.constants import PARTICIPATION_CODES
from suiteview.audit.cyberlife_sql.ctes import (
    _valuation_date_sql,
)
from suiteview.audit.cyberlife_sql.helpers import (
    _STATE_ABBR_TO_CODE,
    build_bill_mode_where,
    participation_predicate,
)
from suiteview.audit.cyberlife_sql.state import QueryContext, SqlParts, ctx_set
from suiteview.audit.sql_helpers import (
    add_date_range,
    add_decimal_range,
    add_int_range,
    esc,
    in_list,
    selected_codes,
)
from suiteview.audit.transaction_filters import transaction_predicates


def add_base_where(ctx: QueryContext, parts: SqlParts) -> None:
    ctx._emit_rider_joins(ctx.rider1_info, 'RIDER1', 1)
    ctx._emit_rider_joins(ctx.rider2_info, 'RIDER2', 2)
    parts.sql_parts.extend(ctx.custom_join_lines)
    parts.wheres = []
    parts.wheres.extend(ctx.custom_where_lines)
    parts.wheres.extend(ctx.segment52_where_lines)
    if ctx.transaction_tab is not None:
        ctx.first_transaction, ctx.second_transaction = ctx.transaction_tab.criteria()
        parts.wheres.extend(transaction_predicates(ctx.first_transaction, ctx.second_transaction, ctx.schema))
    if ctx.sys_code:
        parts.wheres.append(f"POLICY1.CK_SYS_CD = '{esc(ctx.sys_code)}'")
    ctx_set(ctx, "plancode", ctx.pt.txt_plancode.strip().upper())
    if ctx.plancode:
        ctx_set(ctx, "cov_filter_alias", 'COVERAGE1' if ctx.cov1_plancode_match_only else ctx.result_cov_alias if ctx.coverage_level else 'COVSALL')
        parts.wheres.append(f"{ctx.cov_filter_alias}.PLN_DES_SER_CD = '{esc(ctx.plancode)}'")
    ctx_set(ctx, "plancode_list", ctx.plancode_tab.get_plancodes())
    if ctx.plancode_list:
        ctx_set(ctx, "cov_filter_alias", 'COVERAGE1' if ctx.cov1_plancode_match_only else ctx.result_cov_alias if ctx.coverage_level else 'COVSALL')
        parts.wheres.append(f'{ctx.cov_filter_alias}.PLN_DES_SER_CD IN ({in_list(ctx.plancode_list)})')
    ctx_set(ctx, "policy_list", ctx.plancode_tab.get_policies())
    if ctx.policy_list:
        parts.wheres.append(f'POLICY1.CK_POLICY_NBR IN ({in_list(ctx.policy_list)})')
    ctx_set(ctx, "_mkt_org_map", {'MLM': '1', 'CSSD': '2', 'IMG': '7', 'DIRECT': 'D'})
    ctx_set(ctx, "_mkt_company_map", {'CSSD': ['01'], 'IMG': ['01', '26'], 'MLM': ['01', '26'], 'DIRECT': ['01', '26']})
    ctx_set(ctx, "market_org", ctx.pt.cmb_market.strip())
    if ctx.market_org and ctx.market_org in ctx._mkt_org_map:
        parts.wheres.append(f"SUBSTR(POLICY1.SVC_AGC_NBR,1,1) = '{ctx._mkt_org_map[ctx.market_org]}'")
    ctx_set(ctx, "company", ctx.pt.cmb_company.strip())
    if ctx.company:
        ctx_set(ctx, "co_code", ctx.company.split(' - ')[0].strip() if ' - ' in ctx.company else ctx.company)
        parts.wheres.append(f"POLICY1.CK_CMP_CD = '{esc(ctx.co_code)}'")
    elif ctx.market_org and ctx.market_org in ctx._mkt_company_map:
        ctx_set(ctx, "co_codes", ctx._mkt_company_map[ctx.market_org])
        if len(ctx.co_codes) == 1:
            parts.wheres.append(f"POLICY1.CK_CMP_CD = '{ctx.co_codes[0]}'")
        else:
            company_conditions = ' OR '.join((f"POLICY1.CK_CMP_CD = '{c}'" for c in ctx.co_codes))
            parts.wheres.append(f'({company_conditions})')
    ctx_set(ctx, "form_num", ctx.pt.txt_form_number.strip())
    if ctx.form_num:
        parts.wheres.append(f"{ctx.result_cov_alias}.POL_FRM_NBR LIKE '{esc(ctx.form_num)}%'")
    ctx_set(ctx, "branch", ctx.pt.txt_branch.strip())
    if ctx.branch:
        parts.wheres.append(f"SUBSTR(POLICY1.SVC_AGC_NBR, 2, 3) = '{esc(ctx.branch)}'")
    ctx_set(ctx, "polnum", ctx.pt.txt_polnum_value.strip())
    if ctx.polnum:
        ctx_set(ctx, "criteria", ctx.pt.cmb_polnum_criteria)
        if ctx.criteria == 'Starts with':
            parts.wheres.append(f"POLICY1.CK_POLICY_NBR LIKE '{esc(ctx.polnum)}%'")
        elif ctx.criteria == 'Ends with':
            parts.wheres.append(f"POLICY1.CK_POLICY_NBR LIKE '%{esc(ctx.polnum)}'")
        else:
            parts.wheres.append(f"POLICY1.CK_POLICY_NBR LIKE '%{esc(ctx.polnum)}%'")
    if ctx.pt.chk_rga:
        parts.wheres.append("USERGEN.FUZGREIN_IND = 'R'")
    if ctx.pt.chk_status_code:
        codes = selected_codes(ctx.pt.list_status)
        if codes:
            parts.wheres.append(f'POLICY1.PRM_PAY_STA_REA_CD IN ({in_list(codes)})')
    if ctx.pt.chk_product_line:
        codes = selected_codes(ctx.pt.list_product_line)
        if codes:
            ctx_set(ctx, "cov_filter_alias", ctx.result_cov_alias if ctx.coverage_level else 'COVSALL')
            parts.wheres.append(f'{ctx.cov_filter_alias}.PRD_LIN_TYP_CD IN ({in_list(codes)})')
    if ctx.pt.chk_state:
        ctx_set(ctx, "abbrevs", [item for item in ctx.pt.list_state])
        if ctx.abbrevs:
            ctx_set(ctx, "st_codes", [_STATE_ABBR_TO_CODE.get(a) for a in ctx.abbrevs])
            ctx_set(ctx, "st_codes", [c for c in ctx.st_codes if c])
            if ctx.st_codes:
                parts.wheres.append(f'POLICY1.POL_ISS_ST_CD IN ({in_list(ctx.st_codes)})')
    if ctx.pt.chk_last_entry:
        codes = selected_codes(ctx.pt.list_last_entry)
        if codes:
            parts.wheres.append(f'POLICY1.LST_ETR_CD IN ({in_list(codes)})')
    if ctx.pt.chk_suspense:
        codes = selected_codes(ctx.pt.list_suspense)
        if codes:
            parts.wheres.append(f'POLICY1.SUS_CD IN ({in_list(codes)})')
    if ctx.pt.chk_billing_form:
        codes = selected_codes(ctx.pt.list_billing_form)
        if codes:
            parts.wheres.append(f'POLICY1.BIL_FRM_CD IN ({in_list(codes)})')


def add_policy_where(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.pt.chk_bill_mode:
        ctx_set(ctx, "modes", [item for item in ctx.pt.list_bill_mode])
        if ctx.modes:
            ctx_set(ctx, "mode_clause", build_bill_mode_where(ctx.modes))
            if ctx.mode_clause:
                parts.wheres.append(f'({ctx.mode_clause})')
    add_int_range(parts.wheres, f'{ctx.result_cov_alias}.INS_ISS_AGE', ctx.pt.txt_issue_age_lo, ctx.pt.txt_issue_age_hi)
    ctx_set(ctx, "duration_expr", "TRUNCATE(MONTHS_BETWEEN('" + ctx.criteria.as_of_sql + f"', {ctx.result_cov_alias}.ISSUE_DT) / 12, 0)")
    add_int_range(parts.wheres, f'({ctx.result_cov_alias}.INS_ISS_AGE + {ctx.duration_expr})', ctx.pt.txt_current_age_lo, ctx.pt.txt_current_age_hi)
    ctx_set(ctx, "val_duration_expr", f'TRUNCATE(MONTHS_BETWEEN({_valuation_date_sql(ctx.schema)}, {ctx.result_cov_alias}.ISSUE_DT) / 12, 0)')
    add_int_range(parts.wheres, f'({ctx.result_cov_alias}.INS_ISS_AGE + {ctx.val_duration_expr})', ctx.pt.txt_val_age_lo, ctx.pt.txt_val_age_hi)
    add_int_range(parts.wheres, f'({ctx.duration_expr} + 1)', ctx.pt.txt_pol_year_lo, ctx.pt.txt_pol_year_hi)
    add_int_range(parts.wheres, f'MONTH({ctx.result_cov_alias}.ISSUE_DT)', ctx.pt.txt_issue_month_lo, ctx.pt.txt_issue_month_hi)
    add_int_range(parts.wheres, f'DAY({ctx.result_cov_alias}.ISSUE_DT)', ctx.pt.txt_issue_day_lo, ctx.pt.txt_issue_day_hi)
    add_date_range(parts.wheres, f'{ctx.result_cov_alias}.ISSUE_DT', ctx.pt.txt_issued_date_lo, ctx.pt.txt_issued_date_hi)
    add_date_range(parts.wheres, 'POLICY1.PRM_PAID_TO_DT', ctx.pt.txt_paid_to_lo, ctx.pt.txt_paid_to_hi)
    add_date_range(parts.wheres, 'POLICY1.APP_WRT_DT', ctx.pt.txt_app_date_lo, ctx.pt.txt_app_date_hi)
    add_decimal_range(parts.wheres, 'POLICY1.POL_PRM_AMT', ctx.pt.txt_billing_prem_lo, ctx.pt.txt_billing_prem_hi)
    if ctx.has_gpe_date:
        add_date_range(parts.wheres, 'GRACE_TABLE.GRA_PER_EXP_DT', ctx.pt.txt_gpe_date_lo, ctx.pt.txt_gpe_date_hi)
    if ctx.grace_indicator:
        codes = selected_codes(ctx.pt.list_grace_indicator)
        if codes:
            grace_conditions = ' OR '.join((f"SUBSTR(GRACE_TABLE.IN_GRA_PER_IND,1,1) = '{esc(c)}'" for c in codes))
            parts.wheres.append(f'({grace_conditions})')
    add_decimal_range(parts.wheres, 'TAMRA.SVPY_LVL_PRM_AMT', ctx.p2t.txt_tamra_7pay_prem_lo, ctx.p2t.txt_tamra_7pay_prem_hi)
    add_decimal_range(parts.wheres, 'TAMRA.SVPY_BEG_CSV_AMT', ctx.p2t.txt_tamra_7pay_av_lo, ctx.p2t.txt_tamra_7pay_av_hi)
    if ctx.p2t.chk_1035_amt:
        parts.wheres.append('TAMRA.XCG_1035_PMT_QTY > 0')
    if ctx.p2t.chk_mec:
        parts.wheres.append("TAMRA.MEC_STA_CD = '1'")
    add_decimal_range(parts.wheres, 'POLICY_TOTALS.TOT_ADD_PRM_AMT', ctx.p2t.txt_total_addl_prem_lo, ctx.p2t.txt_total_addl_prem_hi)
    add_decimal_range(parts.wheres, '(POLICY_TOTALS.TOT_ADD_PRM_AMT + POLICY_TOTALS.TOT_REG_PRM_AMT)', ctx.p2t.txt_total_prem_addl_reg_lo, ctx.p2t.txt_total_prem_addl_reg_hi)
    add_decimal_range(parts.wheres, 'POLICY_TOTALS.TOT_WTD_AMT', ctx.p2t.txt_accum_wd_lo, ctx.p2t.txt_accum_wd_hi)
    add_decimal_range(parts.wheres, 'LH_POL_YR_TOT_at_MaxDuration.YTD_TOT_PMT_AMT', ctx.p2t.txt_prem_ytd_lo, ctx.p2t.txt_prem_ytd_hi)
    add_date_range(parts.wheres, 'NONTRAD.BIL_COMMENCE_DT', ctx.p2t.txt_bil_commence_dt_lo, ctx.p2t.txt_bil_commence_dt_hi)
    if ctx.p2t.chk_billing_suspended:
        parts.wheres.append("NONTRAD.BIL_STA_CD = '1'")
    if ctx.p2t.chk_failed_guideline:
        parts.wheres.append("NONTRAD.PR_LIMIT_EXC_ONL = '1'")
    if ctx.p2t.chk_participating:
        codes = []
        for item in ctx.p2t.list_participating:
            label = item
            if label not in PARTICIPATION_CODES:
                raise ValueError(f'Unknown participation category: {label}')
            codes.extend(PARTICIPATION_CODES[label])
        if codes:
            parts.wheres.append(participation_predicate(codes))
    if ctx.wl_tab is not None:
        for checkbox, listbox, column in ((ctx.wl_tab.chk_pri_div, ctx.wl_tab.list_pri_div, 'POLICY1.PRI_DIV_OPT_CD'), (ctx.wl_tab.chk_sec_div, ctx.wl_tab.list_sec_div, 'POLICY1.DIV_2ND_OPT_CD'), (ctx.wl_tab.chk_nfo, ctx.wl_tab.list_nfo, 'POLICY1.NFO_OPT_TYP_CD')):
            if checkbox:
                codes = selected_codes(listbox)
                if codes:
                    parts.wheres.append(f'{column} IN ({in_list(codes)})')
        if ctx.wl_tab.chk_participation_type:
            codes = ctx.wl_tab.selected_participation_codes()
            if codes:
                parts.wheres.append(participation_predicate(codes))


def add_coverage_and_benefit_where(ctx: QueryContext, parts: SqlParts) -> None:
    add_date_range(parts.wheres, 'POLICY1.LST_FIN_DT', ctx.p2t.txt_last_fin_date_lo, ctx.p2t.txt_last_fin_date_hi)
    parts.wheres.extend(ctx.term_fin_predicates)
    parts.wheres.extend(ctx.term_both_predicates)
    if ctx.p2t.chk_has_converted:
        parts.wheres.append('USERGEN.EXCH_POL_NUMBER IS NOT NULL')
    if ctx.p2t.chk_has_replacement_pol:
        parts.wheres.append('USERDEF_52R.REPLACED_POLICY IS NOT NULL')
    if ctx.p2t.chk_cov_gio:
        parts.wheres.append("MODCOVSALL.OPT_EXER_IND = 'Y'")
    if ctx.p2t.chk_cov_cola:
        parts.wheres.append("MODCOVSALL.COLA_INCR_IND = '1'")
    if ctx.p2t.chk_loan_type:
        codes = selected_codes(ctx.p2t.list_loan_type)
        if codes:
            parts.wheres.append(f'POLICY1.LN_TYP_CD IN ({in_list(codes)})')
    ctx_set(ctx, "loan_rate", ctx.p2t.txt_loan_charge_rate.strip())
    if ctx.loan_rate:
        try:
            parts.wheres.append(f'POLICY1.LN_PLN_ITS_RT = {float(ctx.loan_rate)}')
        except ValueError:
            pass
    add_decimal_range(parts.wheres, 'POLICYDEBT.LOAN_PRINCIPLE', ctx.p2t.txt_total_loan_prin_lo, ctx.p2t.txt_total_loan_prin_hi)
    add_decimal_range(parts.wheres, 'POLICYDEBT.LOAN_ACCRUED', ctx.p2t.txt_total_accured_lint_lo, ctx.p2t.txt_total_accured_lint_hi)
    if ctx.p2t.chk_trad_overloan:
        codes = selected_codes(ctx.p2t.list_trad_overloan)
        if codes:
            parts.wheres.append(f'POLICY1_MOD.OVERLOAN_IND IN ({in_list(codes)})')
    if ctx.p2t.chk_non_trad:
        codes = selected_codes(ctx.p2t.list_non_trad)
        if codes:
            parts.wheres.append(f'POLICY1.NON_TRD_POL_IND IN ({in_list(codes)})')
    if ctx.p2t.chk_std_loan_payment:
        codes = selected_codes(ctx.p2t.list_std_loan_payment)
        if codes:
            parts.wheres.append(f'SLR_BILL_CONTROL.BIL_FRM_CD IN ({in_list(codes)})')
    if ctx.p2t.chk_def_life:
        codes = selected_codes(ctx.p2t.list_def_life)
        if codes:
            parts.wheres.append(f'NONTRAD.TFDF_CD IN ({in_list(codes)})')
    if ctx.p2t.chk_reinsurance:
        codes = selected_codes(ctx.p2t.list_reinsurance)
        if codes:
            parts.wheres.append(f'POLICY1.REINSURED_CD IN ({in_list(codes)})')
    if ctx.has_change_seq:
        codes = selected_codes(ctx.p2t.list_change_seq)
        if codes:
            parts.wheres.append(f'CHANGE_SEGMENT.CHG_TYP_CD IN ({in_list(codes)})')
    if ctx.adv_cv_corr:
        parts.wheres.append('(MVVAL.DB > COVSUMMARY.TOTAL_SA + MVVAL.OPTDB)')
    if ctx.adv_accum_gt_prem:
        parts.wheres.append('(MVVAL.CSV_AMT >= MVVAL.TOTALPREM)')
    if ctx.adv_glp_neg:
        parts.wheres.append('(GLP.GLP_VALUE < 0)')
    if ctx.adv_sa_lt_orig:
        parts.wheres.append('(COVSUMMARY.TOTAL_SA < COVSUMMARY.TOTAL_ORIGINAL_SA)')
    if ctx.adv_sa_gt_orig:
        parts.wheres.append('(COVSUMMARY.TOTAL_SA > COVSUMMARY.TOTAL_ORIGINAL_SA)')
    if ctx.adv_gcv_gt_cv:
        parts.wheres.append('(ISWL_INTERPOLATED_GCV.ISWL_GCV >= MVVAL.CSV_AMT)')
    if ctx.adv_gcv_lt_cv:
        parts.wheres.append('(ISWL_INTERPOLATED_GCV.ISWL_GCV <= MVVAL.CSV_AMT)')
    if ctx.adv_prem_wd_gt_face:
        parts.wheres.append('((POLICY_TOTALS.TOT_REG_PRM_AMT + POLICY_TOTALS.TOT_ADD_PRM_AMT - POLICY_TOTALS.TOT_WTD_AMT) > PREMWD_FACE.TOTAL_FACE)')
    if ctx.adv_grace_rule:
        codes = selected_codes(ctx.at.list_grace_rule)
        if codes:
            parts.wheres.append(f'NONTRAD.GRA_THD_RLE_CD IN ({in_list(codes)})')
    if ctx.adv_db_option:
        codes = selected_codes(ctx.at.list_db_option)
        if codes:
            parts.wheres.append(f'NONTRAD.DTH_BNF_PLN_OPT_CD IN ({in_list(codes)})')
    if ctx.at.chk_decr_chrg_rule and ctx.at.list_decr_chrg_rule:
        codes = selected_codes(ctx.at.list_decr_chrg_rule)
        rule_preds = []
        known = [code for code in codes if code in ('0', '1')]
        if known:
            rule_preds.append(f'DECRCHG.DECR_CHRG_ALLOW IN ({in_list(known)})')
        if 'Blank' in codes:
            rule_preds.append("(DECRCHG.DECR_CHRG_ALLOW IS NULL OR DECRCHG.DECR_CHRG_ALLOW NOT IN ('0', '1'))")
        parts.wheres.append(f"EXISTS (SELECT 1 FROM {ctx.schema}.TH_NON_TRD_POL DECRCHG WHERE DECRCHG.CK_SYS_CD = POLICY1.CK_SYS_CD AND DECRCHG.CK_CMP_CD = POLICY1.CK_CMP_CD AND DECRCHG.TCH_POL_ID = POLICY1.TCH_POL_ID AND ({' OR '.join(rule_preds)}))")
