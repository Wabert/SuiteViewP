"""CyberLife SQL ctes policy section builders."""
from __future__ import annotations

from suiteview.audit.cyberlife_sql.ctes import (
    _conversion_sc_cte,
    _post_conversion_cte,
)
from suiteview.audit.cyberlife_sql.state import QueryContext, SqlParts
from suiteview.audit.sql_helpers import (
    normalize_date,
)


def collect_coverage_context(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.needs_pol_yr_tot:
        parts.sql_parts.append(f', LH_POL_YR_TOT_withMaxDuration AS')
        parts.sql_parts.append(f'  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, MAX(POL_YR_DUR) MAX_DURATION')
        parts.sql_parts.append(f'   FROM {ctx.schema}.LH_POL_YR_TOT')
        parts.sql_parts.append(f'   GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)')
        parts.sql_parts.append(f', LH_POL_YR_TOT_at_MaxDuration AS')
        parts.sql_parts.append(f'  (SELECT YEARTOTS.*')
        parts.sql_parts.append(f'   FROM {ctx.schema}.LH_POL_YR_TOT YEARTOTS')
        parts.sql_parts.append(f'   INNER JOIN LH_POL_YR_TOT_withMaxDuration')
        parts.sql_parts.append(f'     ON YEARTOTS.CK_SYS_CD = LH_POL_YR_TOT_withMaxDuration.CK_SYS_CD')
        parts.sql_parts.append(f'    AND YEARTOTS.CK_CMP_CD = LH_POL_YR_TOT_withMaxDuration.CK_CMP_CD')
        parts.sql_parts.append(f'    AND YEARTOTS.TCH_POL_ID = LH_POL_YR_TOT_withMaxDuration.TCH_POL_ID')
        parts.sql_parts.append(f'    AND YEARTOTS.POL_YR_DUR = LH_POL_YR_TOT_withMaxDuration.MAX_DURATION)')
    if ctx.needs_grace_table:
        parts.sql_parts.append(f', GRACE_TABLE AS')
        parts.sql_parts.append(f'  (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND')
        parts.sql_parts.append(f'   FROM {ctx.schema}.LH_NON_TRD_POL')
        parts.sql_parts.append(f'   UNION')
        parts.sql_parts.append(f'   SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND')
        parts.sql_parts.append(f'   FROM {ctx.schema}.LH_TRD_POL)')
    if ctx.disp_conversion_dates:
        parts.sql_parts.append(', ' + _conversion_sc_cte(ctx.schema))
    if ctx.disp_post_conversion:
        parts.sql_parts.append(', ' + _post_conversion_cte(ctx.schema))


def add_policy_and_coverage_ctes(ctx: QueryContext, parts: SqlParts) -> None:
    if ctx.has_term_entry or ctx.disp_term_date or ctx.has_term_both:
        parts.sql_parts.append(f', TERMINATION_TRANS AS')
        parts.sql_parts.append(f'  (SELECT FH.CK_CMP_CD, FH.TCH_POL_ID,')
        parts.sql_parts.append(f'    FH.ENTRY_DT, FH.ASOF_DT, FH.TRANS')
        parts.sql_parts.append(f'   FROM {ctx.schema}.FH_FIXED AS FH')
        parts.sql_parts.append(f"   WHERE FH.TRANS IN ('SC', 'SI', 'SF', 'TD', 'TM', 'TN', 'TL', 'TO')")
        parts.sql_parts.append(f"   AND FH.FCB0_REV_IND = '0'")
        parts.sql_parts.append(f"   AND FH.FCB2_REV_APPL_IND = '0')")
        parts.sql_parts.append(f', PRE_TERMINATION_DATES AS')
        parts.sql_parts.append(f'  (SELECT TT.CK_CMP_CD, TT.TCH_POL_ID,')
        parts.sql_parts.append(f'   MAX(TT.ENTRY_DT) AS TERM_ENTRY_DT')
        parts.sql_parts.append(f'   FROM TERMINATION_TRANS AS TT')
        parts.sql_parts.append(f'   GROUP BY TT.CK_CMP_CD, TT.TCH_POL_ID)')
        parts.sql_parts.append(f', TERMINATION_ENTRY_EFFECTIVE_DATES AS')
        parts.sql_parts.append(f'  (SELECT CK_CMP_CD, TCH_POL_ID, ENTRY_DT,')
        parts.sql_parts.append(f'    MAX(ASOF_DT) AS TERM_EFFECTIVE_DT')
        parts.sql_parts.append(f'   FROM TERMINATION_TRANS')
        parts.sql_parts.append(f'   GROUP BY CK_CMP_CD, TCH_POL_ID, ENTRY_DT)')
        parts.sql_parts.append(f', TERMINATION_ENTRY_TRANS_TYPES AS')
        parts.sql_parts.append(f'  (SELECT CK_CMP_CD, TCH_POL_ID, ENTRY_DT,')
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'SC' THEN 1 ELSE 0 END) AS HAS_SC,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'SI' THEN 1 ELSE 0 END) AS HAS_SI,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'SF' THEN 1 ELSE 0 END) AS HAS_SF,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TD' THEN 1 ELSE 0 END) AS HAS_TD,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TM' THEN 1 ELSE 0 END) AS HAS_TM,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TN' THEN 1 ELSE 0 END) AS HAS_TN,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TL' THEN 1 ELSE 0 END) AS HAS_TL,")
        parts.sql_parts.append(f"    MAX(CASE WHEN TRANS = 'TO' THEN 1 ELSE 0 END) AS HAS_TO")
        parts.sql_parts.append(f'   FROM TERMINATION_TRANS')
        parts.sql_parts.append(f'   GROUP BY CK_CMP_CD, TCH_POL_ID, ENTRY_DT)')
        parts.sql_parts.append(f', TERMINATION_ENTRY_DETAILS AS')
        parts.sql_parts.append(f'  (SELECT PTD.CK_CMP_CD, PTD.TCH_POL_ID, PTD.TERM_ENTRY_DT,')
        parts.sql_parts.append(f'    TED.TERM_EFFECTIVE_DT,')
        parts.sql_parts.append(f'    SUBSTR(')
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_SC = 1 THEN ', SC' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_SI = 1 THEN ', SI' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_SF = 1 THEN ', SF' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_TD = 1 THEN ', TD' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_TM = 1 THEN ', TM' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_TN = 1 THEN ', TN' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_TL = 1 THEN ', TL' ELSE '' END ||")
        parts.sql_parts.append(f"      CASE WHEN TTT.HAS_TO = 1 THEN ', TO' ELSE '' END,")
        parts.sql_parts.append(f'      3) AS TERM_TRANS_TYPES')
        parts.sql_parts.append(f'   FROM PRE_TERMINATION_DATES AS PTD')
        parts.sql_parts.append(f'   INNER JOIN TERMINATION_ENTRY_EFFECTIVE_DATES AS TED')
        parts.sql_parts.append(f'     ON PTD.CK_CMP_CD = TED.CK_CMP_CD')
        parts.sql_parts.append(f'    AND PTD.TCH_POL_ID = TED.TCH_POL_ID')
        parts.sql_parts.append(f'    AND PTD.TERM_ENTRY_DT = TED.ENTRY_DT')
        parts.sql_parts.append(f'   INNER JOIN TERMINATION_ENTRY_TRANS_TYPES AS TTT')
        parts.sql_parts.append(f'     ON PTD.CK_CMP_CD = TTT.CK_CMP_CD')
        parts.sql_parts.append(f'    AND PTD.TCH_POL_ID = TTT.TCH_POL_ID')
        parts.sql_parts.append(f'    AND PTD.TERM_ENTRY_DT = TTT.ENTRY_DT)')
        term_lo = normalize_date(ctx.p2t.txt_term_entry_date_lo) or ''
        term_hi = normalize_date(ctx.p2t.txt_term_entry_date_hi) or ''
        if term_lo or term_hi:
            term_where = 'WHERE 1=1'
            if term_lo:
                term_where += f" AND TERMINATION_ENTRY_DETAILS.TERM_ENTRY_DT >= '{term_lo}'"
            if term_hi:
                term_where += f" AND TERMINATION_ENTRY_DETAILS.TERM_ENTRY_DT <= '{term_hi}'"
            parts.sql_parts.append(f', TERMINATION_DATES AS')
            parts.sql_parts.append(f'  (SELECT * FROM TERMINATION_ENTRY_DETAILS {term_where})')
        else:
            parts.sql_parts.append(f', TERMINATION_DATES AS')
            parts.sql_parts.append(f'  (SELECT * FROM TERMINATION_ENTRY_DETAILS)')
        if ctx.has_term_both:
            parts.sql_parts.append(', TERMINATION_BOTH_DATES AS')
            parts.sql_parts.append('  (SELECT CK_CMP_CD, TCH_POL_ID, MAX(ENTRY_DT) AS TERM_ENTRY_DT')
            parts.sql_parts.append('   FROM TERMINATION_TRANS')
            parts.sql_parts.append("   WHERE ENTRY_DT < DATE('9999-12-31')")
            parts.sql_parts.append('   GROUP BY CK_CMP_CD, TCH_POL_ID)')
    if ctx.has_77_segment or ctx.disp_policy_debt:
        parts.sql_parts.append(f', ALL_LOANS AS (')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PRF_LN_IND, LN_PRI_AMT,')
        parts.sql_parts.append(f"    (CASE LN_ITS_AMT_TYP_CD WHEN '2' THEN POL_LN_ITS_AMT ELSE 0 END) LN_INT")
        parts.sql_parts.append(f"  FROM {ctx.schema}.LH_FND_VAL_LOAN WHERE MVRY_DT = '9999-12-31'")
        parts.sql_parts.append(f'  UNION')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PRF_LN_IND, LN_PRI_AMT,')
        parts.sql_parts.append(f"    (CASE LN_ITS_AMT_TYP_CD WHEN '2' THEN POL_LN_ITS_AMT ELSE 0 END) LN_INT")
        parts.sql_parts.append(f"  FROM {ctx.schema}.LH_CSH_VAL_LOAN WHERE MVRY_DT = '9999-12-31')")
        parts.sql_parts.append(f', POLICYDEBT AS (')
        parts.sql_parts.append(f'  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID,')
        parts.sql_parts.append(f'    SUM(ALL_LOANS.LN_PRI_AMT) LOAN_PRINCIPLE,')
        parts.sql_parts.append(f'    SUM(ALL_LOANS.LN_INT) LOAN_ACCRUED,')
        parts.sql_parts.append(f"    SUM(CASE WHEN COALESCE(ALL_LOANS.PRF_LN_IND, '0') <> '1'")
        parts.sql_parts.append(f'      THEN ALL_LOANS.LN_PRI_AMT ELSE 0 END) REG_LOAN_PRINCIPLE,')
        parts.sql_parts.append(f"    SUM(CASE WHEN COALESCE(ALL_LOANS.PRF_LN_IND, '0') <> '1'")
        parts.sql_parts.append(f'      THEN ALL_LOANS.LN_INT ELSE 0 END) REG_LOAN_ACCRUED,')
        parts.sql_parts.append(f"    SUM(CASE WHEN ALL_LOANS.PRF_LN_IND = '1'")
        parts.sql_parts.append(f'      THEN ALL_LOANS.LN_PRI_AMT ELSE 0 END) PREF_LOAN_PRINCIPLE,')
        parts.sql_parts.append(f"    SUM(CASE WHEN ALL_LOANS.PRF_LN_IND = '1'")
        parts.sql_parts.append(f'      THEN ALL_LOANS.LN_INT ELSE 0 END) PREF_LOAN_ACCRUED')
        parts.sql_parts.append(f'  FROM ALL_LOANS')
        parts.sql_parts.append(f'  GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID)')
