"""CyberLife SQL joins section builders."""
from __future__ import annotations

from suiteview.audit.cyberlife_sql.helpers import (
    cease_code_predicate,
)
from suiteview.audit.cyberlife_sql.state import QueryContext, SqlParts
from suiteview.audit.sql_helpers import (
    esc,
)


def add_core_joins(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.has_shadow_av or ctx.disp_shadow_av:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_COV_TARGET SHADOWAV')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = SHADOWAV.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = SHADOWAV.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = SHADOWAV.TCH_POL_ID')
        parts.sql_parts.append("    AND SHADOWAV.TAR_TYP_CD = 'XP'")
    if ctx.has_accum_mtp or ctx.disp_accum_mtp:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_POL_TARGET ACCUMMTP')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = ACCUMMTP.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = ACCUMMTP.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = ACCUMMTP.TCH_POL_ID')
        parts.sql_parts.append("    AND ACCUMMTP.TAR_TYP_CD = 'MA'")
    if ctx.has_accum_glp_range or ctx.disp_accum_glp:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_POL_TARGET ACCUMGLP')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = ACCUMGLP.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = ACCUMGLP.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = ACCUMGLP.TCH_POL_ID')
        parts.sql_parts.append("    AND ACCUMGLP.TAR_TYP_CD = 'TA'")
    if ctx.disp_commission_target:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_COM_TARGET COMMTARGET')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = COMMTARGET.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = COMMTARGET.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = COMMTARGET.TCH_POL_ID')
        parts.sql_parts.append("    AND COMMTARGET.TAR_TYP_CD = 'CT'")
    if ctx.disp_monthly_mtp:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_POL_TARGET MTP')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = MTP.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = MTP.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = MTP.TCH_POL_ID')
        parts.sql_parts.append("    AND MTP.TAR_TYP_CD = 'MT'")
    if ctx.disp_nsp:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_POL_TARGET NSPTARGET')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = NSPTARGET.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = NSPTARGET.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = NSPTARGET.TCH_POL_ID')
        parts.sql_parts.append("    AND NSPTARGET.TAR_TYP_CD = 'NS'")
    if ctx.disp_short_pay:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_POL_TARGET SHORTPAY_PRM')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = SHORTPAY_PRM.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = SHORTPAY_PRM.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = SHORTPAY_PRM.TCH_POL_ID')
        parts.sql_parts.append("    AND SHORTPAY_PRM.TAR_TYP_CD = 'VS'")
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.TH_USER_GENERIC USERDEF_52G')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = USERDEF_52G.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = USERDEF_52G.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = USERDEF_52G.TCH_POL_ID')
    if ctx.disp_gsp or ctx.has_gsp_range:
        gsp_join = 'INNER JOIN' if ctx.has_gsp_range else 'LEFT OUTER JOIN'
        parts.sql_parts.append(f'  {gsp_join} GSP')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = GSP.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = GSP.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = GSP.TCH_POL_ID')
    if ctx.disp_bill_ctrl_num:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_BIL_FRM_CTL BILL_CONTROL')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = BILL_CONTROL.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = BILL_CONTROL.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = BILL_CONTROL.TCH_POL_ID')
    if ctx.disp_orig_face_rpu:
        parts.sql_parts.append('  LEFT OUTER JOIN CHANGE_TYPE9')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = CHANGE_TYPE9.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = CHANGE_TYPE9.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = CHANGE_TYPE9.TCH_POL_ID')
    if ctx.disp_prem_calc_rules:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_FXD_PRM_POL FIXPREM')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = FIXPREM.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = FIXPREM.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = FIXPREM.TCH_POL_ID')
    if ctx.disp_cirf_key:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_COV_FXD_FND_CTL FFC')
        parts.sql_parts.append('    ON POLICY1.CK_SYS_CD = FFC.CK_SYS_CD')
        parts.sql_parts.append('    AND POLICY1.CK_CMP_CD = FFC.CK_CMP_CD')
        parts.sql_parts.append('    AND POLICY1.TCH_POL_ID = FFC.TCH_POL_ID')
def add_policy_value_joins(ctx: QueryContext, parts: SqlParts) -> None:
    benefit_tab = ctx.benefits_tab
    cease_ops = {'1': '=', '2': '<', '3': '>'}
    for index in range(3):
        ben_type = benefit_tab.benefit_combos[index].strip()
        if not ben_type:
            continue
        ben_code = ben_type[0]
        alias = f'BEN{index + 1}'
        sub_type = benefit_tab.subtype_edits[index].strip()
        post_issue = benefit_tab.post_issue_chks[index]
        cease_lo = benefit_tab.cease_lo_edits[index].strip()
        cease_hi = benefit_tab.cease_hi_edits[index].strip()
        cease_status = benefit_tab.cease_status_combos[index].strip()
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_SPM_BNF {alias}')
        parts.sql_parts.append(f'    ON POLICY1.CK_SYS_CD = {alias}.CK_SYS_CD')
        parts.sql_parts.append(f'    AND POLICY1.CK_CMP_CD = {alias}.CK_CMP_CD')
        parts.sql_parts.append(f'    AND POLICY1.TCH_POL_ID = {alias}.TCH_POL_ID')
        parts.sql_parts.append(f"    AND {alias}.SPM_BNF_TYP_CD = '{esc(ben_code)}'")
        if sub_type:
            parts.sql_parts.append(f"    AND {alias}.SPM_BNF_SBY_CD = '{esc(sub_type)}'")
        if post_issue:
            parts.sql_parts.append(f'    AND {alias}.BNF_ISS_DT > COVERAGE1.ISSUE_DT')
        if cease_lo:
            parts.sql_parts.append(f"    AND {alias}.BNF_CEA_DT >= '{esc(cease_lo)}'")
        if cease_hi:
            parts.sql_parts.append(f"    AND {alias}.BNF_CEA_DT <= '{esc(cease_hi)}'")
        if cease_status:
            op = cease_ops.get(cease_status[0])
            if op:
                parts.sql_parts.append(f'    AND {alias}.BNF_CEA_DT {op} {alias}.BNF_OGN_CEA_DT')
    if ctx.cov_needs_modcov1:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.TH_COV_PHA MODCOV1')
        parts.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = MODCOV1.CK_SYS_CD')
        parts.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = MODCOV1.CK_CMP_CD')
        parts.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = MODCOV1.TCH_POL_ID')
        parts.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = MODCOV1.COV_PHA_NBR')
    if ctx.cov_needs_renewals:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_COV_INS_RNL_RT COV1_RENEWALS')
        parts.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = COV1_RENEWALS.CK_SYS_CD')
        parts.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = COV1_RENEWALS.CK_CMP_CD')
        parts.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = COV1_RENEWALS.TCH_POL_ID')
        parts.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = COV1_RENEWALS.COV_PHA_NBR')
        parts.sql_parts.append("    AND COV1_RENEWALS.PRM_RT_TYP_CD = 'C'")
    if ctx.disp_sex_rateclass and ctx.coverage_level:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_COV_INS_RNL_RT RESULTCOV_RENEWALS')
        parts.sql_parts.append('    ON RESULTCOV.CK_SYS_CD = RESULTCOV_RENEWALS.CK_SYS_CD')
        parts.sql_parts.append('    AND RESULTCOV.CK_CMP_CD = RESULTCOV_RENEWALS.CK_CMP_CD')
        parts.sql_parts.append('    AND RESULTCOV.TCH_POL_ID = RESULTCOV_RENEWALS.TCH_POL_ID')
        parts.sql_parts.append('    AND RESULTCOV.COV_PHA_NBR = RESULTCOV_RENEWALS.COV_PHA_NBR')
        parts.sql_parts.append("    AND RESULTCOV_RENEWALS.PRM_RT_TYP_CD = 'C'")
    elif ctx.disp_sex_rateclass and (not ctx.cov_needs_renewals):
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_COV_INS_RNL_RT COV1_RENEWALS')
        parts.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = COV1_RENEWALS.CK_SYS_CD')
        parts.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = COV1_RENEWALS.CK_CMP_CD')
        parts.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = COV1_RENEWALS.TCH_POL_ID')
        parts.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = COV1_RENEWALS.COV_PHA_NBR')
        parts.sql_parts.append("    AND COV1_RENEWALS.PRM_RT_TYP_CD = 'C'")
    if ctx.cov_base_table03:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_SST_XTR_CRG TABLE_RATING1')
        parts.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = TABLE_RATING1.CK_SYS_CD')
        parts.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = TABLE_RATING1.CK_CMP_CD')
        parts.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = TABLE_RATING1.TCH_POL_ID')
        parts.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = TABLE_RATING1.COV_PHA_NBR')
        parts.sql_parts.append("    AND (TABLE_RATING1.SST_XTR_TYP_CD = '0' OR TABLE_RATING1.SST_XTR_TYP_CD = '1' OR TABLE_RATING1.SST_XTR_TYP_CD = '3')")
    if ctx.disp_substandard and ctx.coverage_level:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_SST_XTR_CRG RESULTCOV_TABLE_RATING')
        parts.sql_parts.append('    ON RESULTCOV.CK_SYS_CD = RESULTCOV_TABLE_RATING.CK_SYS_CD')
        parts.sql_parts.append('    AND RESULTCOV.CK_CMP_CD = RESULTCOV_TABLE_RATING.CK_CMP_CD')
        parts.sql_parts.append('    AND RESULTCOV.TCH_POL_ID = RESULTCOV_TABLE_RATING.TCH_POL_ID')
        parts.sql_parts.append('    AND RESULTCOV.COV_PHA_NBR = RESULTCOV_TABLE_RATING.COV_PHA_NBR')
        parts.sql_parts.append("    AND (RESULTCOV_TABLE_RATING.SST_XTR_TYP_CD = '0' OR RESULTCOV_TABLE_RATING.SST_XTR_TYP_CD = '1' OR RESULTCOV_TABLE_RATING.SST_XTR_TYP_CD = '3')")
    elif ctx.disp_substandard:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_SST_XTR_CRG TABLE_RATING1')
        parts.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = TABLE_RATING1.CK_SYS_CD')
        parts.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = TABLE_RATING1.CK_CMP_CD')
        parts.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = TABLE_RATING1.TCH_POL_ID')
        parts.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = TABLE_RATING1.COV_PHA_NBR')
        parts.sql_parts.append("    AND (TABLE_RATING1.SST_XTR_TYP_CD = '0' OR TABLE_RATING1.SST_XTR_TYP_CD = '1' OR TABLE_RATING1.SST_XTR_TYP_CD = '3')")


def add_transaction_and_people_joins(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.cov_base_flat03 or ctx.cov_base_active_flat03:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_SST_XTR_CRG FLAT_EXTRA1')
        parts.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = FLAT_EXTRA1.CK_SYS_CD')
        parts.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = FLAT_EXTRA1.CK_CMP_CD')
        parts.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = FLAT_EXTRA1.TCH_POL_ID')
        parts.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = FLAT_EXTRA1.COV_PHA_NBR')
        parts.sql_parts.append("    AND (FLAT_EXTRA1.SST_XTR_TYP_CD = '2' OR FLAT_EXTRA1.SST_XTR_TYP_CD = '4')")
        if ctx.cov_base_active_flat03:
            parts.sql_parts.append('    AND (FLAT_EXTRA1.SST_XTR_CEA_DT IS NULL OR FLAT_EXTRA1.SST_XTR_CEA_DT > CURRENT DATE)')
    if ctx.disp_substandard and ctx.coverage_level:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_SST_XTR_CRG RESULTCOV_FLAT_EXTRA')
        parts.sql_parts.append('    ON RESULTCOV.CK_SYS_CD = RESULTCOV_FLAT_EXTRA.CK_SYS_CD')
        parts.sql_parts.append('    AND RESULTCOV.CK_CMP_CD = RESULTCOV_FLAT_EXTRA.CK_CMP_CD')
        parts.sql_parts.append('    AND RESULTCOV.TCH_POL_ID = RESULTCOV_FLAT_EXTRA.TCH_POL_ID')
        parts.sql_parts.append('    AND RESULTCOV.COV_PHA_NBR = RESULTCOV_FLAT_EXTRA.COV_PHA_NBR')
        parts.sql_parts.append("    AND (RESULTCOV_FLAT_EXTRA.SST_XTR_TYP_CD = '2' OR RESULTCOV_FLAT_EXTRA.SST_XTR_TYP_CD = '4')")
    elif ctx.disp_substandard:
        parts.sql_parts.append(f'  LEFT OUTER JOIN {ctx.schema}.LH_SST_XTR_CRG FLAT_EXTRA1')
        parts.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = FLAT_EXTRA1.CK_SYS_CD')
        parts.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = FLAT_EXTRA1.CK_CMP_CD')
        parts.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = FLAT_EXTRA1.TCH_POL_ID')
        parts.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = FLAT_EXTRA1.COV_PHA_NBR')
        parts.sql_parts.append("    AND (FLAT_EXTRA1.SST_XTR_TYP_CD = '2' OR FLAT_EXTRA1.SST_XTR_TYP_CD = '4')")




def emit_rider_joins(ctx: QueryContext, parts: SqlParts, info: dict, alias: str, idx: int) -> None:
    if not info['active']:
        return
    _emit_rider_base_join(ctx, parts, alias)
    _emit_rider_identity_filters(parts, info, alias)
    _emit_rider_date_amount_filters(parts, info, alias)
    _emit_rider_mod_join(ctx, parts, info, alias)
    _emit_rider_renewal_join(ctx, parts, info, alias)
    _emit_rider_rating_joins(ctx, parts, info, alias)


def _emit_rider_base_join(ctx: QueryContext, parts: SqlParts, alias: str) -> None:
    parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_COV_PHA {alias}')
    parts.sql_parts.append(f'    ON POLICY1.CK_SYS_CD = {alias}.CK_SYS_CD')
    parts.sql_parts.append(f'    AND POLICY1.CK_CMP_CD = {alias}.CK_CMP_CD')
    parts.sql_parts.append(f'    AND POLICY1.TCH_POL_ID = {alias}.TCH_POL_ID')
    parts.sql_parts.append(f'    AND {alias}.COV_PHA_NBR > 1')


def _emit_rider_identity_filters(parts: SqlParts, info: dict, alias: str) -> None:
    pc = info['plancode']
    if pc:
        parts.sql_parts.append(f"    AND {alias}.PLN_DES_SER_CD = '{esc(pc)}'")
    pl = info['prod_line']
    if pl:
        code = pl[0]
        parts.sql_parts.append(f"    AND {alias}.PRD_LIN_TYP_CD = '{esc(code)}'")
    sex02 = info['sex_code_02']
    if sex02:
        code = sex02[0]
        parts.sql_parts.append(f"    AND {alias}.INS_SEX_CD = '{esc(code)}'")
    person = info['person']
    if person:
        code = person[:2]
        parts.sql_parts.append(f"    AND {alias}.PRS_CD = '{esc(code)}'")
    if info['post_issue']:
        parts.sql_parts.append(f'    AND {alias}.ISSUE_DT > COVERAGE1.ISSUE_DT')


def _emit_rider_date_amount_filters(parts: SqlParts, info: dict, alias: str) -> None:
    issue_lo = info['issue_date_lo']
    if issue_lo:
        parts.sql_parts.append(f"    AND {alias}.ISSUE_DT >= '{esc(issue_lo)}'")
    issue_hi = info['issue_date_hi']
    if issue_hi:
        parts.sql_parts.append(f"    AND {alias}.ISSUE_DT <= '{esc(issue_hi)}'")
    ct_val = info['change_type']
    if ct_val:
        code = ct_val[0]
        parts.sql_parts.append(f"    AND {alias}.NXT_CHG_TYP_CD = '{esc(code)}'")
    cease_pred = cease_code_predicate(f'{alias}.CEA_REA_CD', info['cease_code'])
    if cease_pred:
        parts.sql_parts.append(f'    AND {cease_pred}')
    change_lo = info['change_date_lo']
    if change_lo:
        parts.sql_parts.append(f"    AND {alias}.NXT_CHG_DT >= '{esc(change_lo)}'")
    change_hi = info['change_date_hi']
    if change_hi:
        parts.sql_parts.append(f"    AND {alias}.NXT_CHG_DT <= '{esc(change_hi)}'")
    vpu_lo = info['vpu_lo']
    if vpu_lo:
        try:
            parts.sql_parts.append(f'    AND {alias}.COV_VPU_AMT >= {float(vpu_lo)}')
        except ValueError:
            pass
    vpu_hi = info['vpu_hi']
    if vpu_hi:
        try:
            parts.sql_parts.append(f'    AND {alias}.COV_VPU_AMT <= {float(vpu_hi)}')
        except ValueError:
            pass
    sa_lo = info['spec_amt_lo']
    if sa_lo:
        try:
            parts.sql_parts.append(f'    AND (REAL({alias}.COV_UNT_QTY) * REAL({alias}.COV_VPU_AMT)) >= {float(sa_lo)}')
        except ValueError:
            pass
    sa_hi = info['spec_amt_hi']
    if sa_hi:
        try:
            parts.sql_parts.append(f'    AND (REAL({alias}.COV_UNT_QTY) * REAL({alias}.COV_VPU_AMT)) <= {float(sa_hi)}')
        except ValueError:
            pass
    lives = info['lives_cov']
    if lives:
        code = lives[0]
        parts.sql_parts.append(f"    AND {alias}.LIVES_COV_CD = '{esc(code)}'")
    addl = info['addl_plancode']
    if addl:
        c = addl[0]
        if c == '1':
            parts.sql_parts.append(f'    AND {alias}.PLN_DES_SER_CD = COVERAGE1.PLN_DES_SER_CD')
        elif c == '2':
            parts.sql_parts.append(f'    AND {alias}.PLN_DES_SER_CD <> COVERAGE1.PLN_DES_SER_CD')


def _emit_rider_mod_join(ctx: QueryContext, parts: SqlParts, info: dict, alias: str) -> None:
    covmod_alias = f'{alias}COVMOD'
    if info['needs_covmod']:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.TH_COV_PHA {covmod_alias}')
        parts.sql_parts.append(f'    ON {alias}.CK_SYS_CD = {covmod_alias}.CK_SYS_CD')
        parts.sql_parts.append(f'    AND {alias}.CK_CMP_CD = {covmod_alias}.CK_CMP_CD')
        parts.sql_parts.append(f'    AND {alias}.TCH_POL_ID = {covmod_alias}.TCH_POL_ID')
        parts.sql_parts.append(f'    AND {alias}.COV_PHA_NBR = {covmod_alias}.COV_PHA_NBR')
        pi = info['prod_ind']
        if pi:
            code = pi[0]
            parts.sql_parts.append(f"    AND {covmod_alias}.AN_PRD_ID = '{esc(code)}'")
        cola = info['cola_ind']
        if cola:
            parts.sql_parts.append(f"    AND {covmod_alias}.COLA_INCR_IND = '{esc(cola)}'")
        gio = info['gio_fio']
        if gio:
            if gio.lower() == 'blank':
                parts.sql_parts.append(f"    AND {covmod_alias}.OPT_EXER_IND = ''")
            else:
                parts.sql_parts.append(f"    AND {covmod_alias}.OPT_EXER_IND = '{esc(gio)}'")


def _emit_rider_renewal_join(ctx: QueryContext, parts: SqlParts, info: dict, alias: str) -> None:
    rnl_alias = f'{alias}_RENEWALS'
    if info['needs_renewals']:
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_COV_INS_RNL_RT {rnl_alias}')
        parts.sql_parts.append(f'    ON {alias}.CK_SYS_CD = {rnl_alias}.CK_SYS_CD')
        parts.sql_parts.append(f'    AND {alias}.CK_CMP_CD = {rnl_alias}.CK_CMP_CD')
        parts.sql_parts.append(f'    AND {alias}.TCH_POL_ID = {rnl_alias}.TCH_POL_ID')
        parts.sql_parts.append(f'    AND {alias}.COV_PHA_NBR = {rnl_alias}.COV_PHA_NBR')
        parts.sql_parts.append(f"    AND {rnl_alias}.PRM_RT_TYP_CD = 'C'")
        rc = info['rateclass']
        if rc:
            code = rc[0]
            parts.sql_parts.append(f"    AND {rnl_alias}.RT_CLS_CD = '{esc(code)}'")
        sx67 = info['sex_code_67']
        if sx67:
            code = sx67[0]
            parts.sql_parts.append(f"    AND {rnl_alias}.RT_SEX_CD = '{esc(code)}'")


def _emit_rider_rating_joins(ctx: QueryContext, parts: SqlParts, info: dict, alias: str) -> None:
    if info['table_03']:
        tr_alias = f'{alias}_TABLE_RATING'
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_SST_XTR_CRG {tr_alias}')
        parts.sql_parts.append(f'    ON {alias}.CK_SYS_CD = {tr_alias}.CK_SYS_CD')
        parts.sql_parts.append(f'    AND {alias}.CK_CMP_CD = {tr_alias}.CK_CMP_CD')
        parts.sql_parts.append(f'    AND {alias}.TCH_POL_ID = {tr_alias}.TCH_POL_ID')
        parts.sql_parts.append(f'    AND {alias}.COV_PHA_NBR = {tr_alias}.COV_PHA_NBR')
        parts.sql_parts.append(f"    AND ({tr_alias}.SST_XTR_TYP_CD = '0' OR {tr_alias}.SST_XTR_TYP_CD = '1' OR {tr_alias}.SST_XTR_TYP_CD = '3')")
    if info['flat_03'] or info['active_flat_03']:
        fe_alias = f'{alias}_FLAT_EXTRA'
        parts.sql_parts.append(f'  INNER JOIN {ctx.schema}.LH_SST_XTR_CRG {fe_alias}')
        parts.sql_parts.append(f'    ON {alias}.CK_SYS_CD = {fe_alias}.CK_SYS_CD')
        parts.sql_parts.append(f'    AND {alias}.CK_CMP_CD = {fe_alias}.CK_CMP_CD')
        parts.sql_parts.append(f'    AND {alias}.TCH_POL_ID = {fe_alias}.TCH_POL_ID')
        parts.sql_parts.append(f'    AND {alias}.COV_PHA_NBR = {fe_alias}.COV_PHA_NBR')
        parts.sql_parts.append(f"    AND ({fe_alias}.SST_XTR_TYP_CD = '2' OR {fe_alias}.SST_XTR_TYP_CD = '4')")
        if info['active_flat_03']:
            parts.sql_parts.append(f'    AND ({fe_alias}.SST_XTR_CEA_DT IS NULL OR {fe_alias}.SST_XTR_CEA_DT > CURRENT DATE)')

def add_rider_and_custom_joins(ctx: QueryContext, parts: SqlParts) -> None:
    return
