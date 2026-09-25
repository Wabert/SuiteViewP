"""CyberLife SQL joins section builders."""
from __future__ import annotations

from .common import *


def build_step_016(state: BuildState) -> None:
    if state.has_shadow_av or state.disp_shadow_av:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_COV_TARGET SHADOWAV')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = SHADOWAV.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = SHADOWAV.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = SHADOWAV.TCH_POL_ID')
        state.sql_parts.append("    AND SHADOWAV.TAR_TYP_CD = 'XP'")
    if state.has_accum_mtp or state.disp_accum_mtp:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_POL_TARGET ACCUMMTP')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = ACCUMMTP.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = ACCUMMTP.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = ACCUMMTP.TCH_POL_ID')
        state.sql_parts.append("    AND ACCUMMTP.TAR_TYP_CD = 'MA'")
    if state.has_accum_glp_range or state.disp_accum_glp:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_POL_TARGET ACCUMGLP')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = ACCUMGLP.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = ACCUMGLP.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = ACCUMGLP.TCH_POL_ID')
        state.sql_parts.append("    AND ACCUMGLP.TAR_TYP_CD = 'TA'")
    if state.disp_commission_target:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_COM_TARGET COMMTARGET')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = COMMTARGET.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = COMMTARGET.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = COMMTARGET.TCH_POL_ID')
        state.sql_parts.append("    AND COMMTARGET.TAR_TYP_CD = 'CT'")
    if state.disp_monthly_mtp:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_POL_TARGET MTP')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = MTP.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = MTP.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = MTP.TCH_POL_ID')
        state.sql_parts.append("    AND MTP.TAR_TYP_CD = 'MT'")
    if state.disp_nsp:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_POL_TARGET NSPTARGET')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = NSPTARGET.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = NSPTARGET.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = NSPTARGET.TCH_POL_ID')
        state.sql_parts.append("    AND NSPTARGET.TAR_TYP_CD = 'NS'")
    if state.disp_short_pay:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_POL_TARGET SHORTPAY_PRM')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = SHORTPAY_PRM.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = SHORTPAY_PRM.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = SHORTPAY_PRM.TCH_POL_ID')
        state.sql_parts.append("    AND SHORTPAY_PRM.TAR_TYP_CD = 'VS'")
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.TH_USER_GENERIC USERDEF_52G')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = USERDEF_52G.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = USERDEF_52G.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = USERDEF_52G.TCH_POL_ID')
    if state.disp_gsp or state.has_gsp_range:
        state._gsp_join = 'INNER JOIN' if state.has_gsp_range else 'LEFT OUTER JOIN'
        state.sql_parts.append(f'  {state._gsp_join} GSP')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = GSP.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = GSP.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = GSP.TCH_POL_ID')
    if state.disp_bill_ctrl_num:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_BIL_FRM_CTL BILL_CONTROL')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = BILL_CONTROL.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = BILL_CONTROL.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = BILL_CONTROL.TCH_POL_ID')
    if state.disp_orig_face_rpu:
        state.sql_parts.append('  LEFT OUTER JOIN CHANGE_TYPE9')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = CHANGE_TYPE9.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = CHANGE_TYPE9.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = CHANGE_TYPE9.TCH_POL_ID')
    if state.disp_prem_calc_rules:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_FXD_PRM_POL FIXPREM')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = FIXPREM.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = FIXPREM.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = FIXPREM.TCH_POL_ID')
    if state.disp_cirf_key:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_COV_FXD_FND_CTL FFC')
        state.sql_parts.append('    ON POLICY1.CK_SYS_CD = FFC.CK_SYS_CD')
        state.sql_parts.append('    AND POLICY1.CK_CMP_CD = FFC.CK_CMP_CD')
        state.sql_parts.append('    AND POLICY1.TCH_POL_ID = FFC.TCH_POL_ID')
    state.bt = state.benefits_tab
    state._cease_ops = {'1': '=', '2': '<', '3': '>'}


def build_step_017(state: BuildState) -> None:
    for state.i in range(3):
        state.ben_type = state.bt.benefit_combos[state.i].currentText().strip()
        if not state.ben_type:
            continue
        state.ben_code = state.ben_type[0]
        state.alias = f'BEN{state.i + 1}'
        state.sub_type = state.bt.subtype_edits[state.i].text().strip()
        state.post_issue = state.bt.post_issue_chks[state.i].isChecked()
        state.cease_lo = state.bt.cease_lo_edits[state.i].text().strip()
        state.cease_hi = state.bt.cease_hi_edits[state.i].text().strip()
        state.cease_status = state.bt.cease_status_combos[state.i].currentText().strip()
        state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_SPM_BNF {state.alias}')
        state.sql_parts.append(f'    ON POLICY1.CK_SYS_CD = {state.alias}.CK_SYS_CD')
        state.sql_parts.append(f'    AND POLICY1.CK_CMP_CD = {state.alias}.CK_CMP_CD')
        state.sql_parts.append(f'    AND POLICY1.TCH_POL_ID = {state.alias}.TCH_POL_ID')
        state.sql_parts.append(f"    AND {state.alias}.SPM_BNF_TYP_CD = '{esc(state.ben_code)}'")
        if state.sub_type:
            state.sql_parts.append(f"    AND {state.alias}.SPM_BNF_SBY_CD = '{esc(state.sub_type)}'")
        if state.post_issue:
            state.sql_parts.append(f'    AND {state.alias}.BNF_ISS_DT > COVERAGE1.ISSUE_DT')
        if state.cease_lo:
            state.sql_parts.append(f"    AND {state.alias}.BNF_CEA_DT >= '{esc(state.cease_lo)}'")
        if state.cease_hi:
            state.sql_parts.append(f"    AND {state.alias}.BNF_CEA_DT <= '{esc(state.cease_hi)}'")
        if state.cease_status:
            state.cs_code = state.cease_status[0]
            state.op = state._cease_ops.get(state.cs_code)
            if state.op:
                state.sql_parts.append(f'    AND {state.alias}.BNF_CEA_DT {state.op} {state.alias}.BNF_OGN_CEA_DT')
    if state.cov_needs_modcov1:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.TH_COV_PHA MODCOV1')
        state.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = MODCOV1.CK_SYS_CD')
        state.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = MODCOV1.CK_CMP_CD')
        state.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = MODCOV1.TCH_POL_ID')
        state.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = MODCOV1.COV_PHA_NBR')
    if state.cov_needs_renewals:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_COV_INS_RNL_RT COV1_RENEWALS')
        state.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = COV1_RENEWALS.CK_SYS_CD')
        state.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = COV1_RENEWALS.CK_CMP_CD')
        state.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = COV1_RENEWALS.TCH_POL_ID')
        state.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = COV1_RENEWALS.COV_PHA_NBR')
        state.sql_parts.append("    AND COV1_RENEWALS.PRM_RT_TYP_CD = 'C'")
    if state.disp_sex_rateclass and state.coverage_level:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_COV_INS_RNL_RT RESULTCOV_RENEWALS')
        state.sql_parts.append('    ON RESULTCOV.CK_SYS_CD = RESULTCOV_RENEWALS.CK_SYS_CD')
        state.sql_parts.append('    AND RESULTCOV.CK_CMP_CD = RESULTCOV_RENEWALS.CK_CMP_CD')
        state.sql_parts.append('    AND RESULTCOV.TCH_POL_ID = RESULTCOV_RENEWALS.TCH_POL_ID')
        state.sql_parts.append('    AND RESULTCOV.COV_PHA_NBR = RESULTCOV_RENEWALS.COV_PHA_NBR')
        state.sql_parts.append("    AND RESULTCOV_RENEWALS.PRM_RT_TYP_CD = 'C'")
    elif state.disp_sex_rateclass and (not state.cov_needs_renewals):
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_COV_INS_RNL_RT COV1_RENEWALS')
        state.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = COV1_RENEWALS.CK_SYS_CD')
        state.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = COV1_RENEWALS.CK_CMP_CD')
        state.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = COV1_RENEWALS.TCH_POL_ID')
        state.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = COV1_RENEWALS.COV_PHA_NBR')
        state.sql_parts.append("    AND COV1_RENEWALS.PRM_RT_TYP_CD = 'C'")
    if state.cov_base_table03:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_SST_XTR_CRG TABLE_RATING1')
        state.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = TABLE_RATING1.CK_SYS_CD')
        state.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = TABLE_RATING1.CK_CMP_CD')
        state.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = TABLE_RATING1.TCH_POL_ID')
        state.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = TABLE_RATING1.COV_PHA_NBR')
        state.sql_parts.append("    AND (TABLE_RATING1.SST_XTR_TYP_CD = '0' OR TABLE_RATING1.SST_XTR_TYP_CD = '1' OR TABLE_RATING1.SST_XTR_TYP_CD = '3')")
    if state.disp_substandard and state.coverage_level:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_SST_XTR_CRG RESULTCOV_TABLE_RATING')
        state.sql_parts.append('    ON RESULTCOV.CK_SYS_CD = RESULTCOV_TABLE_RATING.CK_SYS_CD')
        state.sql_parts.append('    AND RESULTCOV.CK_CMP_CD = RESULTCOV_TABLE_RATING.CK_CMP_CD')
        state.sql_parts.append('    AND RESULTCOV.TCH_POL_ID = RESULTCOV_TABLE_RATING.TCH_POL_ID')
        state.sql_parts.append('    AND RESULTCOV.COV_PHA_NBR = RESULTCOV_TABLE_RATING.COV_PHA_NBR')
        state.sql_parts.append("    AND (RESULTCOV_TABLE_RATING.SST_XTR_TYP_CD = '0' OR RESULTCOV_TABLE_RATING.SST_XTR_TYP_CD = '1' OR RESULTCOV_TABLE_RATING.SST_XTR_TYP_CD = '3')")
    elif state.disp_substandard:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_SST_XTR_CRG TABLE_RATING1')
        state.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = TABLE_RATING1.CK_SYS_CD')
        state.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = TABLE_RATING1.CK_CMP_CD')
        state.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = TABLE_RATING1.TCH_POL_ID')
        state.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = TABLE_RATING1.COV_PHA_NBR')
        state.sql_parts.append("    AND (TABLE_RATING1.SST_XTR_TYP_CD = '0' OR TABLE_RATING1.SST_XTR_TYP_CD = '1' OR TABLE_RATING1.SST_XTR_TYP_CD = '3')")


def build_step_018(state: BuildState) -> None:
    if state.cov_base_flat03 or state.cov_base_active_flat03:
        state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_SST_XTR_CRG FLAT_EXTRA1')
        state.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = FLAT_EXTRA1.CK_SYS_CD')
        state.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = FLAT_EXTRA1.CK_CMP_CD')
        state.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = FLAT_EXTRA1.TCH_POL_ID')
        state.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = FLAT_EXTRA1.COV_PHA_NBR')
        state.sql_parts.append("    AND (FLAT_EXTRA1.SST_XTR_TYP_CD = '2' OR FLAT_EXTRA1.SST_XTR_TYP_CD = '4')")
        if state.cov_base_active_flat03:
            state.sql_parts.append('    AND (FLAT_EXTRA1.SST_XTR_CEA_DT IS NULL OR FLAT_EXTRA1.SST_XTR_CEA_DT > CURRENT DATE)')
    if state.disp_substandard and state.coverage_level:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_SST_XTR_CRG RESULTCOV_FLAT_EXTRA')
        state.sql_parts.append('    ON RESULTCOV.CK_SYS_CD = RESULTCOV_FLAT_EXTRA.CK_SYS_CD')
        state.sql_parts.append('    AND RESULTCOV.CK_CMP_CD = RESULTCOV_FLAT_EXTRA.CK_CMP_CD')
        state.sql_parts.append('    AND RESULTCOV.TCH_POL_ID = RESULTCOV_FLAT_EXTRA.TCH_POL_ID')
        state.sql_parts.append('    AND RESULTCOV.COV_PHA_NBR = RESULTCOV_FLAT_EXTRA.COV_PHA_NBR')
        state.sql_parts.append("    AND (RESULTCOV_FLAT_EXTRA.SST_XTR_TYP_CD = '2' OR RESULTCOV_FLAT_EXTRA.SST_XTR_TYP_CD = '4')")
    elif state.disp_substandard:
        state.sql_parts.append(f'  LEFT OUTER JOIN {state.schema}.LH_SST_XTR_CRG FLAT_EXTRA1')
        state.sql_parts.append('    ON COVERAGE1.CK_SYS_CD = FLAT_EXTRA1.CK_SYS_CD')
        state.sql_parts.append('    AND COVERAGE1.CK_CMP_CD = FLAT_EXTRA1.CK_CMP_CD')
        state.sql_parts.append('    AND COVERAGE1.TCH_POL_ID = FLAT_EXTRA1.TCH_POL_ID')
        state.sql_parts.append('    AND COVERAGE1.COV_PHA_NBR = FLAT_EXTRA1.COV_PHA_NBR')
        state.sql_parts.append("    AND (FLAT_EXTRA1.SST_XTR_TYP_CD = '2' OR FLAT_EXTRA1.SST_XTR_TYP_CD = '4')")


def build_step_019(state: BuildState) -> None:

    def _emit_rider_joins(info: dict, alias: str, idx: int):
        if not info['active']:
            return
        state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_COV_PHA {alias}')
        state.sql_parts.append(f'    ON POLICY1.CK_SYS_CD = {alias}.CK_SYS_CD')
        state.sql_parts.append(f'    AND POLICY1.CK_CMP_CD = {alias}.CK_CMP_CD')
        state.sql_parts.append(f'    AND POLICY1.TCH_POL_ID = {alias}.TCH_POL_ID')
        state.sql_parts.append(f'    AND {alias}.COV_PHA_NBR > 1')
        pc = info['plancode']
        if pc:
            state.sql_parts.append(f"    AND {alias}.PLN_DES_SER_CD = '{esc(pc)}'")
        pl = info['prod_line']
        if pl:
            code = pl[0]
            state.sql_parts.append(f"    AND {alias}.PRD_LIN_TYP_CD = '{esc(code)}'")
        sex02 = info['sex_code_02']
        if sex02:
            code = sex02[0]
            state.sql_parts.append(f"    AND {alias}.INS_SEX_CD = '{esc(code)}'")
        person = info['person']
        if person:
            code = person[:2]
            state.sql_parts.append(f"    AND {alias}.PRS_CD = '{esc(code)}'")
        if info['post_issue']:
            state.sql_parts.append(f'    AND {alias}.ISSUE_DT > COVERAGE1.ISSUE_DT')
        issue_lo = info['issue_date_lo']
        if issue_lo:
            state.sql_parts.append(f"    AND {alias}.ISSUE_DT >= '{esc(issue_lo)}'")
        issue_hi = info['issue_date_hi']
        if issue_hi:
            state.sql_parts.append(f"    AND {alias}.ISSUE_DT <= '{esc(issue_hi)}'")
        ct_val = info['change_type']
        if ct_val:
            code = ct_val[0]
            state.sql_parts.append(f"    AND {alias}.NXT_CHG_TYP_CD = '{esc(code)}'")
        cease_pred = _cease_code_predicate(f'{alias}.CEA_REA_CD', info['cease_code'])
        if cease_pred:
            state.sql_parts.append(f'    AND {cease_pred}')
        change_lo = info['change_date_lo']
        if change_lo:
            state.sql_parts.append(f"    AND {alias}.NXT_CHG_DT >= '{esc(change_lo)}'")
        change_hi = info['change_date_hi']
        if change_hi:
            state.sql_parts.append(f"    AND {alias}.NXT_CHG_DT <= '{esc(change_hi)}'")
        vpu_lo = info['vpu_lo']
        if vpu_lo:
            try:
                state.sql_parts.append(f'    AND {alias}.COV_VPU_AMT >= {float(vpu_lo)}')
            except ValueError:
                pass
        vpu_hi = info['vpu_hi']
        if vpu_hi:
            try:
                state.sql_parts.append(f'    AND {alias}.COV_VPU_AMT <= {float(vpu_hi)}')
            except ValueError:
                pass
        sa_lo = info['spec_amt_lo']
        if sa_lo:
            try:
                state.sql_parts.append(f'    AND (REAL({alias}.COV_UNT_QTY) * REAL({alias}.COV_VPU_AMT)) >= {float(sa_lo)}')
            except ValueError:
                pass
        sa_hi = info['spec_amt_hi']
        if sa_hi:
            try:
                state.sql_parts.append(f'    AND (REAL({alias}.COV_UNT_QTY) * REAL({alias}.COV_VPU_AMT)) <= {float(sa_hi)}')
            except ValueError:
                pass
        lives = info['lives_cov']
        if lives:
            code = lives[0]
            state.sql_parts.append(f"    AND {alias}.LIVES_COV_CD = '{esc(code)}'")
        addl = info['addl_plancode']
        if addl:
            c = addl[0]
            if c == '1':
                state.sql_parts.append(f'    AND {alias}.PLN_DES_SER_CD = COVERAGE1.PLN_DES_SER_CD')
            elif c == '2':
                state.sql_parts.append(f'    AND {alias}.PLN_DES_SER_CD <> COVERAGE1.PLN_DES_SER_CD')
        covmod_alias = f'{alias}COVMOD'
        if info['needs_covmod']:
            state.sql_parts.append(f'  INNER JOIN {state.schema}.TH_COV_PHA {covmod_alias}')
            state.sql_parts.append(f'    ON {alias}.CK_SYS_CD = {covmod_alias}.CK_SYS_CD')
            state.sql_parts.append(f'    AND {alias}.CK_CMP_CD = {covmod_alias}.CK_CMP_CD')
            state.sql_parts.append(f'    AND {alias}.TCH_POL_ID = {covmod_alias}.TCH_POL_ID')
            state.sql_parts.append(f'    AND {alias}.COV_PHA_NBR = {covmod_alias}.COV_PHA_NBR')
            pi = info['prod_ind']
            if pi:
                code = pi[0]
                state.sql_parts.append(f"    AND {covmod_alias}.AN_PRD_ID = '{esc(code)}'")
            cola = info['cola_ind']
            if cola:
                state.sql_parts.append(f"    AND {covmod_alias}.COLA_INCR_IND = '{esc(cola)}'")
            gio = info['gio_fio']
            if gio:
                if gio.lower() == 'blank':
                    state.sql_parts.append(f"    AND {covmod_alias}.OPT_EXER_IND = ''")
                else:
                    state.sql_parts.append(f"    AND {covmod_alias}.OPT_EXER_IND = '{esc(gio)}'")
        rnl_alias = f'{alias}_RENEWALS'
        if info['needs_renewals']:
            state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_COV_INS_RNL_RT {rnl_alias}')
            state.sql_parts.append(f'    ON {alias}.CK_SYS_CD = {rnl_alias}.CK_SYS_CD')
            state.sql_parts.append(f'    AND {alias}.CK_CMP_CD = {rnl_alias}.CK_CMP_CD')
            state.sql_parts.append(f'    AND {alias}.TCH_POL_ID = {rnl_alias}.TCH_POL_ID')
            state.sql_parts.append(f'    AND {alias}.COV_PHA_NBR = {rnl_alias}.COV_PHA_NBR')
            state.sql_parts.append(f"    AND {rnl_alias}.PRM_RT_TYP_CD = 'C'")
            rc = info['rateclass']
            if rc:
                code = rc[0]
                state.sql_parts.append(f"    AND {rnl_alias}.RT_CLS_CD = '{esc(code)}'")
            sx67 = info['sex_code_67']
            if sx67:
                code = sx67[0]
                state.sql_parts.append(f"    AND {rnl_alias}.RT_SEX_CD = '{esc(code)}'")
        if info['table_03']:
            tr_alias = f'{alias}_TABLE_RATING'
            state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_SST_XTR_CRG {tr_alias}')
            state.sql_parts.append(f'    ON {alias}.CK_SYS_CD = {tr_alias}.CK_SYS_CD')
            state.sql_parts.append(f'    AND {alias}.CK_CMP_CD = {tr_alias}.CK_CMP_CD')
            state.sql_parts.append(f'    AND {alias}.TCH_POL_ID = {tr_alias}.TCH_POL_ID')
            state.sql_parts.append(f'    AND {alias}.COV_PHA_NBR = {tr_alias}.COV_PHA_NBR')
            state.sql_parts.append(f"    AND ({tr_alias}.SST_XTR_TYP_CD = '0' OR {tr_alias}.SST_XTR_TYP_CD = '1' OR {tr_alias}.SST_XTR_TYP_CD = '3')")
        if info['flat_03'] or info['active_flat_03']:
            fe_alias = f'{alias}_FLAT_EXTRA'
            state.sql_parts.append(f'  INNER JOIN {state.schema}.LH_SST_XTR_CRG {fe_alias}')
            state.sql_parts.append(f'    ON {alias}.CK_SYS_CD = {fe_alias}.CK_SYS_CD')
            state.sql_parts.append(f'    AND {alias}.CK_CMP_CD = {fe_alias}.CK_CMP_CD')
            state.sql_parts.append(f'    AND {alias}.TCH_POL_ID = {fe_alias}.TCH_POL_ID')
            state.sql_parts.append(f'    AND {alias}.COV_PHA_NBR = {fe_alias}.COV_PHA_NBR')
            state.sql_parts.append(f"    AND ({fe_alias}.SST_XTR_TYP_CD = '2' OR {fe_alias}.SST_XTR_TYP_CD = '4')")
            if info['active_flat_03']:
                state.sql_parts.append(f'    AND ({fe_alias}.SST_XTR_CEA_DT IS NULL OR {fe_alias}.SST_XTR_CEA_DT > CURRENT DATE)')
    state._emit_rider_joins = _emit_rider_joins
