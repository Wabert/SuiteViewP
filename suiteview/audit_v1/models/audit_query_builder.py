"""
Audit Query Builder
=====================
Dynamic SQL generation engine for the Audit tool.

Translates AuditCriteria into a full DB2 SQL query with:
- WITH clause (CTEs) for complex derived tables
- SELECT DISTINCT with conditional columns
- FROM clause with conditional JOINs (INNER vs LEFT OUTER)
- WHERE clause with conditional filters
- FETCH FIRST N ROWS ONLY

Port of VBA functions: BuildWithClause, BuildSQLString, BuildRiderTable,
BuildSQLStringToFindBase, BuildSQLStringToFindRiders, BuildSQLStringToFindValues.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from .audit_criteria import AuditCriteria, RiderCriteria

from .audit_constants import (
    DB2_SCHEMA,
    STATE_CODES,
    COMPANY_MARKET_ORG_MAP,
    MARKET_ORG_AGENT_CODES,
    build_state_case_expression,
)

# Schema mapping per region
REGION_SCHEMA_MAP = {
    "CKAS": "UNIT",
    "CKCS": "CYBERTEK",
}


def _schema(region: str) -> str:
    """Return the DB2 schema for the given region."""
    return REGION_SCHEMA_MAP.get(region, DB2_SCHEMA)


def _tbl(table: str, region: str) -> str:
    """Return fully-qualified table name: SCHEMA.TABLE."""
    return f"{_schema(region)}.{table}"


def _today() -> str:
    """Current date as yyyy-mm-dd string."""
    return datetime.now().strftime("%Y-%m-%d")


def _duration_calc() -> str:
    """SQL expression for current policy duration (years)."""
    return (
        f"TRUNCATE(MONTHS_BETWEEN('{_today()}',COVERAGE1.ISSUE_DT)/12,0)"
    )


def _attained_age_calc() -> str:
    """SQL expression for attained age."""
    return f"COVERAGE1.INS_ISS_AGE + {_duration_calc()}"


class AuditQueryBuilder:
    """
    Builds a dynamic DB2 SQL query from AuditCriteria.
    
    Usage::
    
        builder = AuditQueryBuilder(criteria)
        sql = builder.build_query()
    """

    def __init__(self, criteria: AuditCriteria):
        self.c = criteria
        self._ctes: OrderedDict[str, str] = OrderedDict()  # name -> SQL body
        self._region = criteria.region

    # ─── Public API ──────────────────────────────────────────────────────

    def build_query(self) -> str:
        """Build the complete audit SQL query."""
        self._ctes.clear()
        
        # Phase 1: Build CTEs
        self._build_with_clause()
        
        # Phase 2: Build main query
        parts = []
        
        # WITH clause
        if self._ctes:
            cte_parts = []
            for name, body in self._ctes.items():
                cte_parts.append(f"{name} AS ({body})")
            parts.append("WITH " + ",\n".join(cte_parts))
        
        # SELECT
        parts.append(self._build_select())
        
        # FROM
        parts.append(self._build_from())
        
        # WHERE
        parts.append(self._build_where())
        
        # FETCH FIRST
        if not self.c.show_all:
            parts.append(f"FETCH FIRST {self.c.max_count} ROWS ONLY")
        
        return " ".join(parts)

    def build_find_base_query(self, rider_plancode: str,
                               show_policies: bool = False) -> str:
        """Build query to find base plancodes for a given rider plancode."""
        s = _tbl("LH_COV_PHA", self._region)
        select_col = "SUBSTR(RIDERS.TCH_POL_ID,1,10)" if show_policies else "COUNT(RIDERS.PLN_DES_SER_CD)"
        sql = (
            f"SELECT RIDERS.PLN_DES_SER_CD, RIDERS.POL_FRM_NBR,"
            f" POL_ISSUE.PLN_DES_SER_CD, POL_ISSUE.POL_FRM_NBR, {select_col}"
            f" FROM {s} RIDERS"
            f" INNER JOIN {s} POL_ISSUE"
            f" ON RIDERS.CK_SYS_CD = POL_ISSUE.CK_SYS_CD"
            f" AND RIDERS.CK_CMP_CD = POL_ISSUE.CK_CMP_CD"
            f" AND RIDERS.TCH_POL_ID = POL_ISSUE.TCH_POL_ID"
            f" AND POL_ISSUE.COV_PHA_NBR = 1"
            f" WHERE RIDERS.PLN_DES_SER_CD = '{rider_plancode}'"
            f" AND RIDERS.COV_PHA_NBR > 1"
        )
        if not show_policies:
            sql += (" GROUP BY RIDERS.PLN_DES_SER_CD, RIDERS.POL_FRM_NBR,"
                     " POL_ISSUE.PLN_DES_SER_CD, POL_ISSUE.POL_FRM_NBR")
        return sql

    def build_find_riders_query(self, base_plancode: str,
                                 show_policies: bool = False) -> str:
        """Build query to find rider plancodes for a given base plancode."""
        s = _tbl("LH_COV_PHA", self._region)
        select_col = "SUBSTR(RIDERS.TCH_POL_ID,1,10)" if show_policies else "COUNT(RIDERS.PLN_DES_SER_CD)"
        sql = (
            f"SELECT POL_ISSUE.PLN_DES_SER_CD, POL_ISSUE.POL_FRM_NBR,"
            f" RIDERS.PLN_DES_SER_CD, RIDERS.POL_FRM_NBR, {select_col}"
            f" FROM {s} RIDERS"
            f" INNER JOIN {s} POL_ISSUE"
            f" ON RIDERS.CK_SYS_CD = POL_ISSUE.CK_SYS_CD"
            f" AND RIDERS.CK_CMP_CD = POL_ISSUE.CK_CMP_CD"
            f" AND RIDERS.TCH_POL_ID = POL_ISSUE.TCH_POL_ID"
            f" AND POL_ISSUE.COV_PHA_NBR = 1"
            f" AND POL_ISSUE.PLN_DES_SER_CD = '{base_plancode}'"
            f" WHERE RIDERS.PLN_DES_SER_CD <> '{base_plancode}'"
            f" AND RIDERS.COV_PHA_NBR > 1"
        )
        if not show_policies:
            sql += (" GROUP BY POL_ISSUE.PLN_DES_SER_CD, POL_ISSUE.POL_FRM_NBR,"
                     " RIDERS.PLN_DES_SER_CD, RIDERS.POL_FRM_NBR")
        return sql

    def build_value_search_query(self, table_name: str, field_name: str) -> str:
        """Build query to count distinct values for a table.field."""
        return (
            f"SELECT VALUES_TBL.{field_name}, COUNT(VALUES_TBL.TCH_POL_ID)"
            f" FROM {_tbl(table_name, self._region)} VALUES_TBL"
            f" GROUP BY VALUES_TBL.{field_name}"
        )

    # ─── WITH (CTE) Clause ──────────────────────────────────────────────

    def _build_with_clause(self):
        """Build the WITH clause CTEs based on criteria."""
        c = self.c
        T = lambda t: _tbl(t, self._region)  # noqa: E731

        # ── COVERAGE1 (always needed) ───────────────────────────────────
        self._ctes["COVERAGE1"] = (
            f"SELECT * FROM {T('LH_COV_PHA')} C1 WHERE C1.COV_PHA_NBR = 1"
        )

        # ── CHANGE_TYPE9 (RPU original amount) ──────────────────────────
        if c.rpu_original_amt:
            self._ctes["CHANGE_TYPE9"] = (
                f"SELECT TMN.CK_SYS_CD, TMN.CK_CMP_CD, TMN.TCH_POL_ID"
                f",SUM(TMN.OGN_COV_UNT_QTY) TOTALORIGUNITS"
                f" FROM {T('LH_COV_TMN')} TMN"
                f" INNER JOIN {T('LH_NT_COV_CHG')} COVCHG"
                f" ON COVCHG.CK_SYS_CD = TMN.CK_SYS_CD"
                f" AND COVCHG.CK_CMP_CD = TMN.CK_CMP_CD"
                f" AND COVCHG.TCH_POL_ID = TMN.TCH_POL_ID"
                f" AND COVCHG.COV_PHA_NBR = TMN.COV_PHA_NBR"
                f" AND COVCHG.CHG_TYP_CD = '9'"
                f" GROUP BY TMN.CK_SYS_CD, TMN.CK_CMP_CD, TMN.TCH_POL_ID"
            )

        # ── GRACE_TABLE ─────────────────────────────────────────────────
        if c.needs_grace_table or bool(c.grace_indicators):
            self._ctes["GRACE_TABLE"] = (
                f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND"
                f" FROM {T('LH_NON_TRD_POL')}"
                f" UNION"
                f" SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND"
                f" FROM {T('LH_TRD_POL')}"
            )

        # ── INTERPOLATION_MONTHS ────────────────────────────────────────
        if c.needs_interpolation_months or c.show_account_value_02_75:
            self._ctes["INTERPOLATION_MONTHS"] = (
                f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
                f",REAL(12 - MONTHS_BETWEEN(BASPOL.NXT_MVRY_PRC_DT, BASPOL.LST_ANV_DT)) MONTHS_TO_NEXT_ANN"
                f",REAL(MONTHS_BETWEEN(BASPOL.NXT_MVRY_PRC_DT, BASPOL.LST_ANV_DT)) MONTHS_YTD"
                f" FROM {T('LH_BAS_POL')} BASPOL"
            )

        # ── ALL_BASE_COVS + COVSUMMARY + ISWL_INTERPOLATED_GCV ─────────
        needs_covsummary = (
            c.needs_covsummary or
            c.current_sa_greater_than or c.current_sa_less_than or
            c.av_gt_premium
        )
        if needs_covsummary:
            # ALL_BASE_COVS
            iswl = c.iswl_gcv_gt_curr_cv or c.iswl_gcv_lt_curr_cv
            iswl_cols = ""
            if iswl:
                iswl_cols = (
                    ",ROUND(TEMPCOVALL.LOW_DUR_CSV_AMT * TEMPCOVALL.COV_UNT_QTY) CV0"
                    ",ROUND(TEMPCOVALL.LOW_DUR_1_CSV_AMT * TEMPCOVALL.COV_UNT_QTY) CV1"
                    ",ROUND(TEMPCOVALL.LOW_DUR_2_CSV_AMT * TEMPCOVALL.COV_UNT_QTY) CV2"
                )

            include_ap = ""
            if c.include_ap_as_base:
                include_ap = "AND (TEMPCOVALL.PLN_DES_SER_CD = TEMPCOV1.PLN_DES_SER_CD OR TEMPCOVALL.PLN_DES_SER_CD = '1U144A00')"
            else:
                include_ap = "AND (TEMPCOVALL.PLN_DES_SER_CD = TEMPCOV1.PLN_DES_SER_CD)"

            self._ctes["ALL_BASE_COVS"] = (
                f"SELECT TEMPCOV1.CK_SYS_CD, TEMPCOV1.TCH_POL_ID, TEMPCOV1.CK_CMP_CD"
                f",TEMPCOVALL.COV_PHA_NBR, TEMPCOVALL.PLN_DES_SER_CD"
                f"{iswl_cols}"
                f",ROUND(REAL(TEMPCOVALL.COV_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT),2) SPECAMT"
                f",ROUND(REAL(TEMPCOVALL.OGN_SPC_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT),2) ORIGSPECAMT"
                f" FROM {T('LH_COV_PHA')} TEMPCOV1"
                f" INNER JOIN {T('LH_COV_PHA')} TEMPCOVALL"
                f" ON TEMPCOV1.COV_PHA_NBR = 1"
                f" AND TEMPCOV1.CK_SYS_CD = TEMPCOVALL.CK_SYS_CD"
                f" AND TEMPCOV1.CK_CMP_CD = TEMPCOVALL.CK_CMP_CD"
                f" AND TEMPCOV1.TCH_POL_ID = TEMPCOVALL.TCH_POL_ID"
                f" {include_ap}"
            )

            # COVSUMMARY
            iswl_sum_cols = ""
            if iswl:
                iswl_sum_cols = (
                    ",SUM(ALL_BASE_COVS.CV0) TOTAL_CV0"
                    ",SUM(ALL_BASE_COVS.CV1) TOTAL_CV1"
                    ",SUM(ALL_BASE_COVS.CV2) TOTAL_CV2"
                )
            self._ctes["COVSUMMARY"] = (
                f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
                f",SUM(ALL_BASE_COVS.SPECAMT) TOTAL_SA"
                f",SUM(ALL_BASE_COVS.ORIGSPECAMT) TOTAL_ORIGINAL_SA"
                f",COUNT(ALL_BASE_COVS.COV_PHA_NBR) BASECOVCOUNT"
                f"{iswl_sum_cols}"
                f" FROM ALL_BASE_COVS"
                f" GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
            )

            # ISWL_INTERPOLATED_GCV
            if iswl:
                self._ctes["ISWL_INTERPOLATED_GCV"] = (
                    f"SELECT COVSUMMARY.CK_SYS_CD, COVSUMMARY.CK_CMP_CD, COVSUMMARY.TCH_POL_ID"
                    f",ROUND((INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN * COVSUMMARY.TOTAL_CV2"
                    f" + INTERPOLATION_MONTHS.MONTHS_YTD * COVSUMMARY.TOTAL_CV1)/12, 2) ISWL_GCV"
                    f" FROM COVSUMMARY"
                    f" INNER JOIN INTERPOLATION_MONTHS"
                    f" ON COVSUMMARY.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD"
                    f" AND COVSUMMARY.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD"
                    f" AND COVSUMMARY.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID"
                )

        # ── BILLMODE_POOL ───────────────────────────────────────────────
        if c.billing_modes or c.show_billing_mode:
            bill_mode_conditions = []
            non_standard_conditions = []
            mode_map = {
                "Weekly": "NSD_MD_CD = '1'",
                "9thly": "NSD_MD_CD = '9'",
                "10thly": "NSD_MD_CD = 'A'",
                "BiWeekly": "NSD_MD_CD = '2'",
                "SemiMonthly": "NSD_MD_CD = 'S'",
            }
            standard_map = {
                "Monthly": "PMT_FQY_PER = 1",
                "Quarterly": "PMT_FQY_PER = 3",
                "Semiannual": "PMT_FQY_PER = 6",
                "Annual": "PMT_FQY_PER = 12",
            }
            for mode in c.billing_modes:
                if mode in mode_map:
                    ns = mode_map[mode]
                    non_standard_conditions.append(f"{T('LH_BAS_POL')}.{ns}")
                elif mode in standard_map:
                    bill_mode_conditions.append(f"{T('LH_BAS_POL')}.{standard_map[mode]}")

            where_parts = []
            if non_standard_conditions:
                where_parts.append(
                    f"({T('LH_BAS_POL')}.PMT_FQY_PER = 1"
                    f" AND ({' OR '.join(non_standard_conditions)}))"
                )
            if bill_mode_conditions:
                where_parts.append(f"({' OR '.join(bill_mode_conditions)})")

            if where_parts:
                where_clause = " OR ".join(where_parts)
            else:
                where_clause = "1=1"

            self._ctes["BILLMODE_POOL"] = (
                f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PMT_FQY_PER, NSD_MD_CD"
                f" FROM {T('LH_BAS_POL')}"
                f" WHERE {where_clause}"
            )

        # ── ALLOCATION_FUNDS ────────────────────────────────────────────
        if c.premium_allocation_funds:
            intersect_parts = []
            for fund_id in c.premium_allocation_funds:
                intersect_parts.append(
                    f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
                    f" FROM {T('LH_FND_ALC')}"
                    f" WHERE FND_ID_CD = '{fund_id[:2]}'"
                    f" AND FND_ALC_PCT > 0 AND FND_ALC_TYP_CD = 'P'"
                )
            self._ctes["ALLOCATION_FUNDS"] = " INTERSECT ".join(intersect_parts)

        # ── FUND_VALUES ─────────────────────────────────────────────────
        if c.fund_ids:
            self._ctes["FUND_VALUES"] = (
                f"SELECT CK_CMP_CD, CK_SYS_CD, TCH_POL_ID, FND_ID_CD"
                f", SUM(CSV_AMT) FUNDAMT"
                f" FROM {T('LH_POL_FND_VAL_TOT')}"
                f" WHERE MVRY_DT = '9999-12-31'"
                f" GROUP BY CK_CMP_CD, CK_SYS_CD, TCH_POL_ID, FND_ID_CD"
            )

        # ── CHANGE_SEGMENT ──────────────────────────────────────────────
        if c.transaction.has_change_segment:
            self._ctes["CHANGE_SEGMENT"] = (
                f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID FROM {T('LH_COV_TMN')}"
                f" UNION SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID FROM {T('LH_NT_COV_CHG')}"
                f" UNION SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID FROM {T('LH_NT_COV_CHG_SCH')}"
                f" UNION SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID FROM {T('LH_SPM_BNF_CHG_SCH')}"
            )

        # ── ALL_LOANS + POLICYDEBT ──────────────────────────────────────
        needs_loan = c.needs_loan_join
        if needs_loan:
            self._ctes["ALL_LOANS"] = (
                f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PRF_LN_IND, LN_PRI_AMT"
                f",(CASE LN_ITS_AMT_TYP_CD WHEN '2' THEN POL_LN_ITS_AMT ELSE 0 END) LN_INT"
                f" FROM {T('LH_FND_VAL_LOAN')}"
                f" WHERE MVRY_DT = '9999-12-31'"
                f" UNION"
                f" SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PRF_LN_IND, LN_PRI_AMT"
                f",(CASE LN_ITS_AMT_TYP_CD WHEN '2' THEN POL_LN_ITS_AMT ELSE 0 END) LN_INT"
                f" FROM {T('LH_CSH_VAL_LOAN')}"
                f" WHERE MVRY_DT = '9999-12-31'"
            )
            self._ctes["POLICYDEBT"] = (
                f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
                f",SUM(ALL_LOANS.LN_PRI_AMT) LOAN_PRINCIPLE"
                f",SUM(ALL_LOANS.LN_INT) LOAN_ACCRUED"
                f" FROM ALL_LOANS"
                f" GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
            )

        # ── LASTMV + MVVAL ──────────────────────────────────────────────
        if c.needs_mvval or c.show_account_value_02_75:
            self._ctes["LASTMV"] = (
                f"SELECT DISTINCT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
                f", MAX(MVRY_DT) LASTMVDT"
                f" FROM {T('LH_POL_MVRY_VAL')}"
                f" GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
            )
            self._ctes["MVVAL"] = (
                f"SELECT MVRVAL.CK_SYS_CD, MVRVAL.CK_CMP_CD, MVRVAL.TCH_POL_ID"
                f",LASTMV.LASTMVDT"
                f",MVRVAL.CSV_AMT"
                f",MVRVAL.DTH_BNF_AMT DB"
                f",NONTRAD.DTH_BNF_PLN_OPT_CD"
                f",ROUND(REAL(MVRVAL.DTH_BNF_AMT) / CASE WHEN MVRVAL.CVAT_COR_PCT = 0 THEN 1 ELSE REAL(MVRVAL.CVAT_COR_PCT)/100 END, 2) OPTDB"
                f",MVRVAL.CVAT_COR_PCT CORRPCT"
                f",POLTOTALS.TOT_REG_PRM_AMT + POLTOTALS.TOT_ADD_PRM_AMT TOTALPREM"
                f" FROM {T('LH_POL_MVRY_VAL')} MVRVAL"
                f" INNER JOIN LASTMV"
                f" ON MVRVAL.CK_SYS_CD = LASTMV.CK_SYS_CD"
                f" AND MVRVAL.CK_CMP_CD = LASTMV.CK_CMP_CD"
                f" AND MVRVAL.TCH_POL_ID = LASTMV.TCH_POL_ID"
                f" AND MVRVAL.MVRY_DT = LASTMV.LASTMVDT"
                f" LEFT OUTER JOIN {T('LH_NON_TRD_POL')} NONTRAD"
                f" ON MVRVAL.CK_SYS_CD = NONTRAD.CK_SYS_CD"
                f" AND MVRVAL.CK_CMP_CD = NONTRAD.CK_CMP_CD"
                f" AND MVRVAL.TCH_POL_ID = NONTRAD.TCH_POL_ID"
                f" LEFT OUTER JOIN {T('LH_POL_TOTALS')} POLTOTALS"
                f" ON MVRVAL.CK_SYS_CD = POLTOTALS.CK_SYS_CD"
                f" AND MVRVAL.CK_CMP_CD = POLTOTALS.CK_CMP_CD"
                f" AND MVRVAL.TCH_POL_ID = POLTOTALS.TCH_POL_ID"
            )

        # ── GLP ─────────────────────────────────────────────────────────
        if c.glp_negative or c.show_glp:
            self._ctes["GLP"] = (
                f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
                f",SVPY_LVL_PRM_AMT GLP_VALUE"
                f" FROM {T('LH_COV_INS_GDL_PRM')}"
                f" WHERE PRM_TYP_CD = 'G' AND COV_PHA_NBR = 1"
            )

        # ── GSP ─────────────────────────────────────────────────────────
        if c.show_gsp:
            self._ctes["GSP"] = (
                f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
                f",SVPY_LVL_PRM_AMT GSP_VALUE"
                f" FROM {T('LH_COV_INS_GDL_PRM')}"
                f" WHERE PRM_TYP_CD = 'S' AND COV_PHA_NBR = 1"
            )

        # ── TRAD_CV ─────────────────────────────────────────────────────
        if c.show_account_value_02_75:
            self._ctes["TRAD_CV"] = (
                f"SELECT COVERAGE1.CK_SYS_CD, COVERAGE1.CK_CMP_CD, COVERAGE1.TCH_POL_ID"
                f",ROUND((CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN 0 ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END)"
                f"*COVERAGE1.COV_UNT_QTY*INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN"
                f" + (CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN 0 ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END)"
                f"*COVERAGE1.COV_UNT_QTY*INTERPOLATION_MONTHS.MONTHS_YTD,2) INTERP_CV"
                f",ROUND((CASE WHEN COVERAGE1.NSP_CV_AMT IS NULL THEN 0 ELSE COVERAGE1.NSP_CV_AMT END)"
                f"*COVERAGE1.COV_UNT_QTY,2) INTERP_NSP"
                f" FROM COVERAGE1"
                f" LEFT OUTER JOIN INTERPOLATION_MONTHS"
                f" ON COVERAGE1.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD"
                f" AND COVERAGE1.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD"
                f" AND COVERAGE1.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID"
            )

        # ── LH_POL_YR_TOT CTEs ─────────────────────────────────────────
        # Always include year totals (used for premium paid YTD, etc.)
        self._ctes["LH_POL_YR_TOT_withMaxDuration"] = (
            f"SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, MAX(POL_YR_NBR) MAX_DUR"
            f" FROM {T('LH_POL_YR_TOT')}"
            f" GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID"
        )
        self._ctes["LH_POL_YR_TOT_at_MaxDuration"] = (
            f"SELECT POLYR.CK_SYS_CD, POLYR.CK_CMP_CD, POLYR.TCH_POL_ID"
            f",POLYR.YTD_TOT_PMT_AMT"
            f" FROM {T('LH_POL_YR_TOT')} POLYR"
            f" INNER JOIN LH_POL_YR_TOT_withMaxDuration MAXDUR"
            f" ON POLYR.CK_SYS_CD = MAXDUR.CK_SYS_CD"
            f" AND POLYR.CK_CMP_CD = MAXDUR.CK_CMP_CD"
            f" AND POLYR.TCH_POL_ID = MAXDUR.TCH_POL_ID"
            f" AND POLYR.POL_YR_NBR = MAXDUR.MAX_DUR"
        )

        # ── TERMINATION_DATES ───────────────────────────────────────────
        if c.needs_termination_dates:
            term_filter = ""
            if c.low_termination_date:
                term_filter += f" AND PRE_TERMINATION_DATES.TERM_ENTRY_DT >= '{c.low_termination_date}'"
            if c.high_termination_date:
                term_filter += f" AND PRE_TERMINATION_DATES.TERM_ENTRY_DT <= '{c.high_termination_date}'"

            self._ctes["PRE_TERMINATION_DATES"] = (
                f"SELECT CK_CMP_CD, TCH_POL_ID, ENTRY_DT TERM_ENTRY_DT, TRANS, SEQ_NO"
                f" FROM {T('FH_FIXED')}"
                f" WHERE TRANS IN ('TM','LA','MA','SU','EX')"
            )
            self._ctes["TERMINATION_DATES"] = (
                f"SELECT PRE_TERMINATION_DATES.CK_CMP_CD, PRE_TERMINATION_DATES.TCH_POL_ID"
                f",PRE_TERMINATION_DATES.TERM_ENTRY_DT"
                f" FROM PRE_TERMINATION_DATES"
                f" WHERE NOT EXISTS ("
                f"SELECT 1 FROM {T('FH_FIXED')} RV"
                f" WHERE RV.CK_CMP_CD = PRE_TERMINATION_DATES.CK_CMP_CD"
                f" AND RV.TCH_POL_ID = PRE_TERMINATION_DATES.TCH_POL_ID"
                f" AND RV.TRANS = 'RV'"
                f" AND RV.SEQ_NO > PRE_TERMINATION_DATES.SEQ_NO"
                f"){term_filter}"
            )

    # ─── SELECT Clause ──────────────────────────────────────────────────

    def _build_select(self) -> str:
        """Build the SELECT DISTINCT clause."""
        c = self.c
        mt = c.main_table  # "COVERAGE1" or "COVSALL"
        dur = _duration_calc()
        att = _attained_age_calc()
        today = _today()
        cols: List[str] = []

        # Always-present columns
        cols.append("CURRENT_DATE RunDate")
        cols.append("POLICY1.CK_POLICY_NBR PolicyNumber")
        if c.show_tch_pol_id:
            cols.append("POLICY1.TCH_POL_ID TCH_POL_ID")
        if c.show_product_line_code:
            cols.append("COVERAGE1.PRD_LIN_TYP_CD")
        cols.append("POLICY1.CK_CMP_CD CompanyCode")
        cols.append("POLICY1.PRM_PAY_STA_REA_CD StatusCode")

        # Duration & attained age
        if (c.show_current_duration or c.low_current_policy_year or
                c.high_current_policy_year or c.within_conversion_period or
                c.show_within_conversion_period):
            cols.append(f"{dur} AS Duration")

        if (c.show_current_attained_age or c.low_current_age or
                c.high_current_age or c.show_conversion_credit_info or
                c.within_conversion_period or c.show_within_conversion_period):
            cols.append(f"{att} AS AttainedAge")

        cols.append("POLICY1.SUS_CD SuspenseCode")
        cols.append("SUBSTR(POLICY1.SVC_AGC_NBR,1,1) AgentCode")

        # State CASE expression
        cols.append(f"({build_state_case_expression()}) IssueState")

        # Main table columns
        cols.append(f"{mt}.PLN_DES_SER_CD Plancode")
        cols.append(f"{mt}.POL_FRM_NBR FormNumber")
        cols.append(f"{mt}.ISSUE_DT IssueDt")
        cols.append(f"{mt}.INS_ISS_AGE IssueAge")
        cols.append("USERDEF_52G.FUZGREIN_IND PARTNER")

        if c.show_market_org_code:
            cols.append("SUBSTR(POLICY1.SVC_AGC_NBR,1,1) MarkOrg")

        # Cash value rate / Trad CV Cov1
        if c.cv_rate_gt_zero_on_base or c.show_trad_cv:
            cols.append("(CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN '0' ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END) BCVR_COV1")
            cols.append("(CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN '0' ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END) ECVR_COV1")
            cols.append("INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN")
            cols.append("INTERPOLATION_MONTHS.MONTHS_YTD")
            cols.append(
                "(CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN '0' ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END)"
                "*COVERAGE1.COV_UNT_QTY*INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN"
                " + (CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN '0' ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END)"
                "*COVERAGE1.COV_UNT_QTY*INTERPOLATION_MONTHS.MONTHS_YTD CV_COV1"
            )

        # Account value 02/75
        if c.show_account_value_02_75:
            cols.append("MVVAL.CSV_AMT")
            cols.append("TRAD_CV.INTERP_NSP")
            cols.append("TRAD_CV.INTERP_CV")
            cols.append("COVERAGE1.ADV_PRD_IND")

        # Sex & rateclass
        if c.show_sex_and_rateclass:
            cols.append("COV1_RENEWALS.RT_CLS_CD RenewalClass")
            cols.append("COV1_RENEWALS.RT_SEX_CD RenewalSex")
        if c.show_sex_02:
            cols.append("COVERAGE1.INS_SEX_CD SEX_CD")

        # Substandard
        if c.show_substandard:
            cols.append("(CASE WHEN TABLE_RATING1.SST_XTR_RT_TBL_CD IS NULL THEN ' ' ELSE TABLE_RATING1.SST_XTR_RT_TBL_CD END) TableRating")
            cols.append("(CASE WHEN FLAT_EXTRA1.SST_XTR_UNT_AMT IS NULL THEN '0' ELSE FLAT_EXTRA1.SST_XTR_UNT_AMT END) Flat")

        # RPU original
        if c.rpu_original_amt:
            cols.append("CHANGE_TYPE9.TOTALORIGUNITS")

        # ISWL GCV
        if c.iswl_gcv_gt_curr_cv or c.iswl_gcv_lt_curr_cv:
            cols.append("ISWL_INTERPOLATED_GCV.ISWL_GCV")

        # Specified amount / face
        if (c.multiple_base_coverages or c.ul_in_corridor or
                c.show_specified_amount or c.current_sa_greater_than or c.current_sa_less_than):
            cols.append("COVSUMMARY.TOTAL_SA TotalFace")
            cols.append("COVSUMMARY.TOTAL_ORIGINAL_SA TotalOriginalFace")

        # Accumulation value / premium
        if (c.av_greater_than or c.av_less_than or c.ul_in_corridor or
                c.av_gt_premium or c.iswl_gcv_gt_curr_cv or c.iswl_gcv_lt_curr_cv or
                c.show_accumulation_value or c.show_premium_ptd):
            cols.append("MVVAL.LASTMVDT LastMonthliverary")
            cols.append("MVVAL.CSV_AMT CurrCV")
            cols.append("MVVAL.TOTALPREM")

        # DB option
        if c.show_db_option:
            cols.append("NONTRAD.DTH_BNF_PLN_OPT_CD DBOpt")

        # UL corridor
        if c.ul_in_corridor or c.av_gt_premium:
            cols.append("MVVAL.DB DB")
            cols.append("MVVAL.CORRPCT CorrPct")
            cols.append("MVVAL.OPTDB")
            cols.append("ROUND(MVVAL.DB - COVSUMMARY.TOTAL_SA,2) CORRAMT")

        # Various display fields
        if c.glp_negative:
            cols.append("GLP.GLP_VALUE")
        if c.show_last_account_date:
            cols.append("POLICY1.LST_ACT_TRS_DT LST_ACC_DT")
        if c.show_last_financial_date:
            cols.append("POLICY1.LST_FIN_DT")
        if c.show_bill_to_date:
            cols.append("POLICY1.PRM_BILL_TO_DT BILL_TO_DT")
        if c.show_paid_to_date:
            cols.append("POLICY1.PRM_PAID_TO_DT PAID_TO_DT")

        if c.show_billable_premium or c.low_billing_prem or c.high_billing_prem:
            cols.append("IFNULL(POLICY1.POL_PRM_AMT,0) BILL_PREM")

        # Billing mode
        if c.show_billing_mode:
            cols.append(self._billing_mode_case("BILL_MODE"))
            cols.append(self._billing_freq_case("BILL_FREQ"))
            cols.append(
                f"IFNULL(POLICY1.POL_PRM_AMT,0) * {self._billing_freq_case_expr()} ANN_PREM"
            )

        if c.show_billing_form:
            cols.append("POLICY1.BIL_FRM_CD BillForm")
        if c.show_slr_billing_form:
            cols.append("SLR_BILL_CONTROL.BIL_FRM_CD SLRBillForm")
        if c.show_billing_control_number:
            cols.append("BILL_CONTROL.BIL_CTL_NBR BillControl")

        if c.show_gsp:
            cols.append("GSP.GSP_VALUE")
        if c.show_glp:
            cols.append("GLP.GLP_VALUE")
        if c.show_tamra:
            cols.append("TAMRA.SVPY_LVL_PRM_AMT TAMRA7PAY")
        if c.show_cost_basis:
            cols.append("POLICY_TOTALS.POL_CST_BSS_AMT COSTBASIS")
        if c.show_gpe_date:
            cols.append("GRACE_TABLE.GRA_PER_EXP_DT GPE_DT")
        if c.show_ctp:
            cols.append("COMMTARGET.TAR_PRM_AMT CTP")
        if c.show_monthly_mtp:
            cols.append("MTP.TAR_PRM_AMT MonthlyMTP")
        if c.show_accum_monthly_mtp:
            cols.append("ACCUMMTP.TAR_PRM_AMT ACCUMMTP")
        if c.show_accum_glp:
            cols.append("ACCUMGLP.TAR_PRM_AMT ACCUMGLP")
        if c.show_shadow_av:
            cols.append("SHADOWAV.TAR_PRM_AMT ShadowAV")

        # Policy debt / loans
        if c.show_policy_debt or c.has_loan:
            cols.append("POLICYDEBT.LOAN_PRINCIPLE")
            cols.append("POLICYDEBT.LOAN_ACCRUED")
            cols.append(
                "(CASE"
                " WHEN POLICY1.LN_TYP_CD = '0' THEN 'FIX'"
                " WHEN POLICY1.LN_TYP_CD = '1' THEN 'FIX'"
                " WHEN POLICY1.LN_TYP_CD = '6' THEN 'VAR'"
                " WHEN POLICY1.LN_TYP_CD = '7' THEN 'VAR'"
                " WHEN POLICY1.LN_TYP_CD = '9' THEN 'NA'"
                " ELSE POLICY1.LN_TYP_CD"
                " END) LOAN_TYPE"
            )
            cols.append(
                "(CASE"
                " WHEN POLICY1.LN_TYP_CD = '0' THEN 'ADVANCE'"
                " WHEN POLICY1.LN_TYP_CD = '1' THEN 'ARREARS'"
                " WHEN POLICY1.LN_TYP_CD = '6' THEN 'ADVANCE'"
                " WHEN POLICY1.LN_TYP_CD = '7' THEN 'ARREARS'"
                " WHEN POLICY1.LN_TYP_CD = '9' THEN 'NA'"
                " ELSE POLICY1.LN_TYP_CD"
                " END) LOAN_TIMING"
            )

        if c.show_accum_withdrawals:
            cols.append("POLICY_TOTALS.TOT_WTD_AMT")
        if c.show_premium_paid_ytd:
            cols.append("LH_POL_YR_TOT_at_MaxDuration.YTD_TOT_PMT_AMT")

        if c.show_trad_overloan_ind or bool(c.overloan_indicators):
            cols.append("POLICY1_MOD.OVERLOAN_IND")

        # Short pay
        if c.show_short_pay_fields:
            cols.append("SHORTPAY_PRM.TAR_PRM_AMT SHORTPAY_AMT")
            cols.append("SHORTPAY_PRM.TAR_DT SHORTPAY_CEASEDT")
            cols.append("USERDEF_52G.INITIAL_PAY_DUR SHORTPAY_DUR")
            cols.append("USERDEF_52G.INITIAL_MODE SHORTPAY_MODE")
            cols.append("USERDEF_52G.DIAL_TO_PREM_AGE SHORTPAY_DBAGE")

        # Reinsurance
        if bool(c.reinsurance_codes) or c.show_reinsured_code:
            cols.append("POLICY1.REINSURED_CD REINSURED_CD")

        # Application date
        if c.low_app_date or c.high_app_date:
            cols.append("POLICY1.APP_WRT_DT APP_DT")

        # Last entry code
        if (c.show_last_entry_code or bool(c.last_entry_codes) or
                c.low_last_financial_date or c.high_last_financial_date):
            cols.append("POLICY1.LST_ETR_CD LAST_CD")
            cols.append("POLICY1.LST_FIN_DT LAST_DT")

        if c.show_original_entry_code:
            cols.append("POLICY1.OGN_ETR_CD ORIG_CD")

        # MEC status
        if c.show_mec_status:
            cols.append(
                "(CASE"
                " WHEN POLICY1.MEC_STATUS_CD = '0' THEN '0 - NO'"
                " WHEN POLICY1.MEC_STATUS_CD = '1' THEN '1 - YES'"
                " WHEN POLICY1.MEC_STATUS_CD = '2' THEN '2 - NO'"
                " ELSE POLICY1.MEC_STATUS_CD"
                " END) MEC_INDICATOR_01"
            )

        # UL Definition of Life Insurance
        if c.show_ul_def_of_life_ins:
            cols.append(
                "(CASE"
                " WHEN NONTRAD.TFDF_CD = '1' THEN '1 - GPT TEFRA'"
                " WHEN NONTRAD.TFDF_CD = '2' THEN '2 - GPT DEFRA'"
                " WHEN NONTRAD.TFDF_CD = '3' THEN '3 - CVAT DEFRA'"
                " WHEN NONTRAD.TFDF_CD = '4' THEN '4 - GPT Selected'"
                " WHEN NONTRAD.TFDF_CD = '5' THEN '5 - CVAT Selected'"
                " ELSE NONTRAD.TFDF_CD"
                " END) DefOfLifeIns"
            )

        # Converted policy
        if c.has_converted_policy_number or c.show_converted_policy_number:
            cols.append("USERDEF_52G.EXCH_POL_NUMBER EXCHANGE_POL")
            cols.append("USERDEF_52G.EXCHANGE EXCHANGE_CD")
            cols.append("USERDEF_52G.SOURCE_COV_PHASE CONV_COV")
            cols.append("USERDEF_52G.SOURCE_ISSUE_DATE CONV_ISSDT")
            cols.append("USERDEF_52G.SOURCE_PLAN_CODE CONV_PLAN")
            cols.append("USERDEF_52G.SOURCE_FACE_AMT CONV_FACE")

        # Replacement policy
        if c.show_replacement_policy or c.has_replacement_policy_number:
            cols.append("USERDEF_52R.REPLACED_POLICY REPLACED_POL")

        # NSP
        if c.show_nsp:
            cols.append("NSPTARGET.TAR_PRM_AMT NSP")

        # Date displays
        if c.show_next_notification_date:
            cols.append("POLICY1.NXT_SCH_NOT_DT NextNotifyDt")
        if c.show_next_year_end_date:
            cols.append("POLICY1.NXT_YR_END_PRC_DT NextYearEndDt")
        if c.show_application_date:
            cols.append("POLICY1.APP_WRT_DT AppDt")
        if c.show_next_monthliversary_date:
            cols.append("POLICY1.NXT_MVRY_PRC_DT NextMVDt")
        if c.show_next_statement_date:
            cols.append("POLICY1.NXT_SCH_STT_DT NextStatementDt")
        if c.show_mdo_indicator or c.is_mdo:
            cols.append("SUBSTR(POLICY1.USR_RES_CD,1,1) MDO")

        # Last change date
        if c.low_last_change_date or c.high_last_change_date:
            cols.append("NEWBUS.LST_CHG_DT")

        # Bill commence
        if c.low_bill_commence_date or c.high_bill_commence_date or c.billing_suspended:
            cols.append("NONTRAD.BIL_STA_CD")
            cols.append("NONTRAD.BIL_COMMENCE_DT")

        # CIRF key
        if c.show_cirf_key:
            cols.append("FFC.CUR_ITS_RT_SER_NBR CIRF_Key")

        # Fund values
        if c.fund_ids:
            cols.append(f"FUND_VALUES.FUNDAMT {c.fund_ids}_AMT")

        # Termination date
        if c.low_termination_date or c.high_termination_date or c.show_termination_date:
            cols.append("TERMINATION_DATES.TERM_ENTRY_DT")

        # Initial term period
        if c.show_initial_term_period or bool(c.initial_term_periods):
            cols.append("COVERAGE1.INT_RNL_PER")
            cols.append("COVERAGE1.SBQ_RNL_STR_DUR")
            cols.append("COVERAGE1.SBQ_RNL_PER")

        # Conversion period info
        if c.show_conversion_period_info or c.within_conversion_period:
            cols.append("UPDF.CONVERSION_PERIOD CN_PERIOD")
            cols.append("UPDF.CONVERSION_AGE CN_AGE")
            cols.append("UPDF.CONV_TO_TRM_PERIOD CN_TO_TERM_PERIOD")

        # Within conversion period flag
        if c.within_conversion_period or c.show_within_conversion_period:
            cols.append(
                f"(CASE"
                f" WHEN (UPDF.CONVERSION_PERIOD = 0"
                f" AND COVERAGE1.INS_ISS_AGE + TRUNCATE(MONTHS_BETWEEN(DATE('{today}'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_AGE)"
                f" OR (UPDF.CONVERSION_PERIOD > 0"
                f" AND TRUNCATE(MONTHS_BETWEEN(DATE('{today}'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_PERIOD"
                f" AND COVERAGE1.INS_ISS_AGE + TRUNCATE(MONTHS_BETWEEN(DATE('{today}'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_AGE)"
                f" THEN 'TRUE' ELSE 'FALSE'"
                f" END) AS WITHIN_CONV_PERIOD"
            )

        # Conversion credit info
        if c.show_conversion_credit_info:
            cols.append("UPDF.CONV_CREDIT_IND CN_CRED_IND")
            cols.append("UPDF.CONV_CREDIT_RULE CN_CRED_RULE")
            cols.append("UPDF.CONV_CREDIT_PERIOD CN_CRED_PERIOD")

        # Subseries
        if c.show_subseries:
            cols.append("COVERAGE1.LIF_PLN_SUB_SRE_CD SUBSERIES")

        # Premium calc rules
        if c.show_prem_calc_rules:
            cols.append("FIXPREM.MD_PRM_MUL_ORD_CD")
            cols.append("FIXPREM.RT_FCT_ORD_CD")
            cols.append("FIXPREM.ROU_RLE_CD")

        return "SELECT DISTINCT " + ",".join(cols)

    # ─── FROM Clause ────────────────────────────────────────────────────

    def _build_from(self) -> str:
        """Build FROM clause with all conditional JOINs."""
        c = self.c
        T = lambda t: _tbl(t, self._region)  # noqa: E731
        parts: List[str] = []

        parts.append(f"FROM {T('LH_BAS_POL')} POLICY1")

        # ── All coverages ───────────────────────────────────────────────
        needs_all_covs = (
            c.show_all_coverages or
            bool(c.multiple_plancodes) or
            c.gio_indicator or c.cola_indicator or
            c.plancode_all_covs or c.form_number_like or
            bool(c.product_line_codes_all) or bool(c.product_indicators_all)
        )
        if needs_all_covs:
            join_cond = (
                "INNER JOIN {tbl} COVSALL"
                " ON POLICY1.CK_SYS_CD = COVSALL.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = COVSALL.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = COVSALL.TCH_POL_ID"
            ).format(tbl=T("LH_COV_PHA"))

            # Plancode filter on all covs
            pc_conditions = []
            for pc in c.multiple_plancodes:
                pc_conditions.append(f"COVSALL.PLN_DES_SER_CD ='{pc}'")
            if c.plancode_all_covs:
                if "%" in c.plancode_all_covs:
                    pc_conditions.append(f"COVSALL.PLN_DES_SER_CD Like '{c.plancode_all_covs}'")
                else:
                    pc_conditions.append(f"COVSALL.PLN_DES_SER_CD ='{c.plancode_all_covs}'")
            if pc_conditions:
                join_cond += f" AND ({' OR '.join(pc_conditions)})"

            if c.product_line_codes_all:
                join_cond += self._in_clause("COVSALL.PRD_LIN_TYP_CD", c.product_line_codes_all, 1)

            parts.append(join_cond)

            # Modified coverage fields (MODCOVSALL)
            if c.product_indicators_all or c.gio_indicator or c.cola_indicator:
                mod_join = (
                    f"INNER JOIN {T('TH_COV_PHA')} MODCOVSALL"
                    f" ON MODCOVSALL.CK_SYS_CD = COVSALL.CK_SYS_CD"
                    f" AND MODCOVSALL.CK_CMP_CD = COVSALL.CK_CMP_CD"
                    f" AND MODCOVSALL.TCH_POL_ID = COVSALL.TCH_POL_ID"
                    f" AND MODCOVSALL.COV_PHA_NBR = COVSALL.COV_PHA_NBR"
                )
                if c.product_indicators_all:
                    mod_join += self._in_clause("MODCOVSALL.AN_PRD_ID", c.product_indicators_all, 1)
                if c.gio_indicator:
                    mod_join += " AND (MODCOVSALL.OPT_EXER_IND = 'Y')"
                if c.cola_indicator:
                    mod_join += " AND (MODCOVSALL.COLA_INCR_IND = '1')"
                parts.append(mod_join)

        # ── New business table ──────────────────────────────────────────
        if c.low_last_change_date or c.high_last_change_date:
            parts.append(
                f"INNER JOIN {T('LH_NEW_BUS_POL')} NEWBUS"
                f" ON POLICY1.CK_SYS_CD = NEWBUS.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = NEWBUS.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = NEWBUS.TCH_POL_ID"
            )

        # ── Fixed premium rules ─────────────────────────────────────────
        if c.show_prem_calc_rules:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_FXD_PRM_POL')} FIXPREM"
                f" ON POLICY1.CK_SYS_CD = FIXPREM.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = FIXPREM.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = FIXPREM.TCH_POL_ID"
            )

        # ── TH_BAS_POL (overloan) ───────────────────────────────────────
        if c.show_trad_overloan_ind or bool(c.overloan_indicators):
            parts.append(
                f"LEFT OUTER JOIN {T('TH_BAS_POL')} POLICY1_MOD"
                f" ON POLICY1.CK_SYS_CD = POLICY1_MOD.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = POLICY1_MOD.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = POLICY1_MOD.TCH_POL_ID"
            )

        # ── COVERAGE1 (base coverage, always) ───────────────────────────
        cov1_join = (
            "INNER JOIN COVERAGE1"
            " ON POLICY1.CK_SYS_CD = COVERAGE1.CK_SYS_CD"
            " AND POLICY1.CK_CMP_CD = COVERAGE1.CK_CMP_CD"
            " AND POLICY1.TCH_POL_ID = COVERAGE1.TCH_POL_ID"
        )
        if c.valuation_class:
            cov1_join += f" AND (COVERAGE1.INS_CLS_CD = '{c.valuation_class}')"
        if c.valuation_base:
            cov1_join += f" AND (COVERAGE1.PLN_BSE_SRE_CD = '{c.valuation_base}')"
        if c.valuation_subseries:
            cov1_join += f" AND (COVERAGE1.LIF_PLN_SUB_SRE_CD = '{c.valuation_subseries}')"
        if c.valuation_class_not_plan_description:
            cov1_join += " AND (COVERAGE1.INS_CLS_CD <> SUBSTR(COVERAGE1.PLN_DES_SER_CD,3,1))"
        if c.valuation_mortality_table:
            cov1_join += f" AND COVERAGE1.MTL_FCT_TBL_CD = '{c.valuation_mortality_table}'"
        if c.eti_mortality_table:
            cov1_join += f" AND COVERAGE1.NSP_EI_TBL_CD = '{c.eti_mortality_table}'"
        if c.nfo_interest_rate:
            cov1_join += f" AND COVERAGE1.NSP_ITS_RT = {float(c.nfo_interest_rate)}"
        if c.rpu_mortality_table:
            cov1_join += f" AND COVERAGE1.NSP_RPU_TBL_CD = '{c.rpu_mortality_table}'"
        if c.cov1_product_line_code:
            cov1_join += f" AND COVERAGE1.PRD_LIN_TYP_CD = '{c.cov1_product_line_code}'"
        if c.cov1_plancode:
            cov1_join += f" AND COVERAGE1.PLN_DES_SER_CD = '{c.cov1_plancode}'"
        if c.cov1_sex_code_02:
            cov1_join += self._in_clause("COVERAGE1.INS_SEX_CD", c.cov1_sex_code_02, 1)
        if c.initial_term_periods:
            cov1_join += self._in_clause("COVERAGE1.INT_RNL_PER", c.initial_term_periods, 3)
        if c.cv_rate_gt_zero_on_base:
            cov1_join += " AND (COVERAGE1.LOW_DUR_1_CSV_AMT > 0 or COVERAGE1.LOW_DUR_2_CSV_AMT > 0)"
        if c.low_issue_age:
            cov1_join += f" AND (COVERAGE1.INS_ISS_AGE >= {c.low_issue_age})"
        if c.high_issue_age:
            cov1_join += f" AND (COVERAGE1.INS_ISS_AGE <= {c.high_issue_age})"
        if c.low_issue_date:
            cov1_join += f" AND COVERAGE1.ISSUE_DT >= '{c.low_issue_date}'"
        if c.high_issue_date:
            cov1_join += f" AND COVERAGE1.ISSUE_DT <= '{c.high_issue_date}'"
        if c.low_issue_month:
            cov1_join += f" AND MONTH(COVERAGE1.ISSUE_DT) >= {c.low_issue_month}"
        if c.high_issue_month:
            cov1_join += f" AND MONTH(COVERAGE1.ISSUE_DT) <= {c.high_issue_month}"
        if c.low_issue_day:
            cov1_join += f" AND DAY(COVERAGE1.ISSUE_DT) >= {c.low_issue_day}"
        if c.high_issue_day:
            cov1_join += f" AND DAY(COVERAGE1.ISSUE_DT) <= {c.high_issue_day}"
        parts.append(cov1_join)

        # ── MODCOV1 (product indicator for cov1) ────────────────────────
        if c.cov1_product_indicator or c.show_product_line_code:
            join_type = "LEFT OUTER JOIN" if c.show_product_line_code and not c.cov1_product_indicator else "INNER JOIN"
            modcov1 = (
                f"{join_type} {T('TH_COV_PHA')} MODCOV1"
                f" ON COVERAGE1.CK_SYS_CD = MODCOV1.CK_SYS_CD"
                f" AND COVERAGE1.CK_CMP_CD = MODCOV1.CK_CMP_CD"
                f" AND COVERAGE1.TCH_POL_ID = MODCOV1.TCH_POL_ID"
                f" AND COVERAGE1.COV_PHA_NBR = MODCOV1.COV_PHA_NBR"
            )
            if c.cov1_product_indicator:
                modcov1 += f" AND (MODCOV1.AN_PRD_ID = '{c.cov1_product_indicator[:1]}')"
            parts.append(modcov1)

        # ── Table rating (cov1) ─────────────────────────────────────────
        if c.table_rating or c.show_substandard:
            jt = "INNER JOIN" if c.table_rating else "LEFT OUTER JOIN"
            parts.append(
                f"{jt} {T('LH_SST_XTR_CRG')} TABLE_RATING1"
                f" ON COVERAGE1.CK_SYS_CD = TABLE_RATING1.CK_SYS_CD"
                f" AND COVERAGE1.CK_CMP_CD = TABLE_RATING1.CK_CMP_CD"
                f" AND COVERAGE1.TCH_POL_ID = TABLE_RATING1.TCH_POL_ID"
                f" AND COVERAGE1.COV_PHA_NBR = TABLE_RATING1.COV_PHA_NBR"
                f" AND (TABLE_RATING1.SST_XTR_TYP_CD ='0' Or TABLE_RATING1.SST_XTR_TYP_CD ='1' Or TABLE_RATING1.SST_XTR_TYP_CD ='3')"
            )

        # ── Flat extra (cov1) ───────────────────────────────────────────
        if c.flat_extra or c.show_substandard:
            jt = "INNER JOIN" if c.flat_extra else "LEFT OUTER JOIN"
            parts.append(
                f"{jt} {T('LH_SST_XTR_CRG')} FLAT_EXTRA1"
                f" ON COVERAGE1.CK_SYS_CD = FLAT_EXTRA1.CK_SYS_CD"
                f" AND COVERAGE1.CK_CMP_CD = FLAT_EXTRA1.CK_CMP_CD"
                f" AND COVERAGE1.TCH_POL_ID = FLAT_EXTRA1.TCH_POL_ID"
                f" AND COVERAGE1.COV_PHA_NBR = FLAT_EXTRA1.COV_PHA_NBR"
                f" AND (FLAT_EXTRA1.SST_XTR_TYP_CD ='2' Or FLAT_EXTRA1.SST_XTR_TYP_CD ='4')"
            )

        # ── Rate class / sex code for cov1 ──────────────────────────────
        if c.cov1_rateclass or c.cov1_sex_code or c.show_sex_and_rateclass:
            jt = "INNER JOIN" if (c.cov1_rateclass or c.cov1_sex_code) else "LEFT OUTER JOIN"
            rnl = (
                f"{jt} {T('LH_COV_INS_RNL_RT')} COV1_RENEWALS"
                f" ON COVERAGE1.CK_SYS_CD = COV1_RENEWALS.CK_SYS_CD"
                f" AND COVERAGE1.CK_CMP_CD = COV1_RENEWALS.CK_CMP_CD"
                f" AND COVERAGE1.TCH_POL_ID = COV1_RENEWALS.TCH_POL_ID"
                f" AND COVERAGE1.COV_PHA_NBR = COV1_RENEWALS.COV_PHA_NBR"
                f" AND COV1_RENEWALS.PRM_RT_TYP_CD = 'C'"
            )
            if c.cov1_rateclass:
                rnl += self._in_clause("COV1_RENEWALS.RT_CLS_CD", c.cov1_rateclass, 1)
            if c.cov1_sex_code:
                rnl += self._in_clause("COV1_RENEWALS.RT_SEX_CD", c.cov1_sex_code, 1)
            parts.append(rnl)

        # ── Riders ──────────────────────────────────────────────────────
        parts.append(self._build_rider_joins())

        # ── TRAD_CV ─────────────────────────────────────────────────────
        if c.show_account_value_02_75:
            parts.append(
                "LEFT OUTER JOIN TRAD_CV"
                " ON COVERAGE1.CK_SYS_CD = TRAD_CV.CK_SYS_CD"
                " AND COVERAGE1.CK_CMP_CD = TRAD_CV.CK_CMP_CD"
                " AND COVERAGE1.TCH_POL_ID = TRAD_CV.TCH_POL_ID"
            )

        # ── Benefits ────────────────────────────────────────────────────
        for idx, ben in enumerate([c.benefit1, c.benefit2, c.benefit3], start=1):
            if ben.enabled:
                alias = f"BEN{idx}"
                ben_join = (
                    f"INNER JOIN {T('LH_SPM_BNF')} {alias}"
                    f" ON POLICY1.CK_SYS_CD = {alias}.CK_SYS_CD"
                    f" AND POLICY1.CK_CMP_CD = {alias}.CK_CMP_CD"
                    f" AND POLICY1.TCH_POL_ID = {alias}.TCH_POL_ID"
                )
                if ben.benefit_type:
                    ben_join += f" AND ({alias}.SPM_BNF_TYP_CD = '{ben.benefit_type[:1]}')"
                if ben.subtype:
                    ben_join += f" AND ({alias}.SPM_BNF_SBY_CD = '{ben.subtype}')"
                if ben.post_issue:
                    ben_join += f" AND ({alias}.BNF_ISS_DT > COVERAGE1.ISSUE_DT)"
                if ben.low_cease_date:
                    ben_join += f" AND ({alias}.BNF_CEA_DT >= '{ben.low_cease_date}')"
                if ben.high_cease_date:
                    ben_join += f" AND ({alias}.BNF_CEA_DT <= '{ben.high_cease_date}')"
                if ben.cease_date_status:
                    if ben.cease_date_status.startswith("1"):
                        ben_join += f" AND ({alias}.BNF_CEA_DT = {alias}.BNF_OGN_CEA_DT)"
                    elif ben.cease_date_status.startswith("2"):
                        ben_join += f" AND ({alias}.BNF_CEA_DT < {alias}.BNF_OGN_CEA_DT)"
                    elif ben.cease_date_status.startswith("3"):
                        ben_join += f" AND ({alias}.BNF_CEA_DT > {alias}.BNF_OGN_CEA_DT)"
                parts.append(ben_join)

        # ── CIRF key ────────────────────────────────────────────────────
        if c.show_cirf_key:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_COV_FXD_FND_CTL')} FFC"
                f" ON POLICY1.CK_SYS_CD = FFC.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = FFC.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = FFC.TCH_POL_ID"
            )

        # ── Fund values ─────────────────────────────────────────────────
        if c.fund_ids:
            fv_join = (
                "INNER JOIN FUND_VALUES"
                " ON POLICY1.CK_SYS_CD = FUND_VALUES.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = FUND_VALUES.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = FUND_VALUES.TCH_POL_ID"
                f" AND FUND_VALUES.FND_ID_CD = '{c.fund_ids}'"
            )
            if c.fund_id_greater_than:
                fv_join += f" AND FUND_VALUES.FUNDAMT >= {c.fund_id_greater_than}"
            if c.fund_id_less_than:
                fv_join += f" AND FUND_VALUES.FUNDAMT <= {c.fund_id_less_than}"
            parts.append(fv_join)

        # ── Non-traditional policy ──────────────────────────────────────
        needs_nontrad = c.needs_nontrad_join or bool(c.grace_period_rules) or c.billing_suspended
        if needs_nontrad:
            is_filter = (
                bool(c.db_options) or bool(c.def_of_life_ins) or
                c.failed_tamra_or_gp or bool(c.grace_period_rules)
            )
            jt = "INNER JOIN" if is_filter else "LEFT OUTER JOIN"
            nt_join = (
                f"{jt} {T('LH_NON_TRD_POL')} NONTRAD"
                f" ON POLICY1.CK_SYS_CD = NONTRAD.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = NONTRAD.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = NONTRAD.TCH_POL_ID"
            )
            if c.db_options:
                nt_join += self._in_clause("NONTRAD.DTH_BNF_PLN_OPT_CD", c.db_options, 1)
            if c.def_of_life_ins:
                nt_join += self._in_clause("NONTRAD.TFDF_CD", c.def_of_life_ins, 1)
            if c.grace_period_rules:
                nt_join += self._in_clause("NONTRAD.GRA_THD_RLE_CD", c.grace_period_rules, 1)
            if c.failed_tamra_or_gp:
                nt_join += " AND (NONTRAD.PR_LIMIT_EXC_ONL = '1')"
            if c.billing_suspended:
                nt_join += " AND (NONTRAD.BIL_STA_CD = '1')"
            parts.append(nt_join)

        # ── Premium allocation funds ────────────────────────────────────
        if c.premium_allocation_funds:
            parts.append(
                "INNER JOIN ALLOCATION_FUNDS"
                " ON POLICY1.CK_SYS_CD = ALLOCATION_FUNDS.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = ALLOCATION_FUNDS.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = ALLOCATION_FUNDS.TCH_POL_ID"
            )

        # ── Type P allocation count ─────────────────────────────────────
        if c.type_p_count_greater_than or c.type_p_count_less_than:
            ap = (
                f"INNER JOIN {T('LH_FND_TRS_ALC_SET')} ALLOCATION_P_COUNT"
                f" ON POLICY1.CK_SYS_CD = ALLOCATION_P_COUNT.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = ALLOCATION_P_COUNT.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = ALLOCATION_P_COUNT.TCH_POL_ID"
                f" AND ALLOCATION_P_COUNT.FND_TRS_TYP_CD = 'P'"
            )
            if c.type_p_count_greater_than:
                ap += f" AND ALLOCATION_P_COUNT.FND_ALC_SEQ_NBR >= {c.type_p_count_greater_than}"
            if c.type_p_count_less_than:
                ap += f" AND ALLOCATION_P_COUNT.FND_ALC_SEQ_NBR <= {c.type_p_count_less_than}"
            parts.append(ap)

        # ── Skipped coverage reinstatement ──────────────────────────────
        if c.skipped_coverage_reinstatement:
            parts.append(
                f"INNER JOIN {T('LH_COV_SKIPPED_PER')} REINSTATEMENT"
                f" ON POLICY1.CK_SYS_CD = REINSTATEMENT.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = REINSTATEMENT.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = REINSTATEMENT.TCH_POL_ID"
            )

        # ── SLR billing form ────────────────────────────────────────────
        if c.show_slr_billing_form or c.slr_billing_forms:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_LN_RPY_TRM')} SLR_BILL_CONTROL"
                f" ON POLICY1.CK_SYS_CD = SLR_BILL_CONTROL.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = SLR_BILL_CONTROL.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = SLR_BILL_CONTROL.TCH_POL_ID"
            )

        # ── Billing control ─────────────────────────────────────────────
        if c.show_billing_control_number:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_BIL_FRM_CTL')} BILL_CONTROL"
                f" ON POLICY1.CK_SYS_CD = BILL_CONTROL.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = BILL_CONTROL.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = BILL_CONTROL.TCH_POL_ID"
            )

        # ── TH_USER_GENERIC (52G) ──────────────────────────────────────
        jt_52g = "INNER JOIN" if (c.has_converted_policy_number or c.is_rga) else "LEFT OUTER JOIN"
        userdef_join = (
            f"{jt_52g} {T('TH_USER_GENERIC')} USERDEF_52G"
            f" ON POLICY1.CK_SYS_CD = USERDEF_52G.CK_SYS_CD"
            f" AND POLICY1.CK_CMP_CD = USERDEF_52G.CK_CMP_CD"
            f" AND POLICY1.TCH_POL_ID = USERDEF_52G.TCH_POL_ID"
        )
        if c.has_converted_policy_number:
            userdef_join += " AND USERDEF_52G.EXCH_POL_NUMBER IS NOT NULL"
        parts.append(userdef_join)

        # ── TH_USER_PDF (52-1) ──────────────────────────────────────────
        parts.append(
            f"LEFT OUTER JOIN {T('TH_USER_PDF')} UPDF"
            f" ON POLICY1.CK_SYS_CD = UPDF.CK_SYS_CD"
            f" AND POLICY1.CK_CMP_CD = UPDF.CK_CMP_CD"
            f" AND POLICY1.TCH_POL_ID = UPDF.TCH_POL_ID"
            f" AND UPDF.TYPE_SEQUENCE = 1"
        )

        # ── TH_USER_REPLACEMENT (52R) ───────────────────────────────────
        if c.show_replacement_policy or c.has_replacement_policy_number:
            jt_52r = "INNER JOIN" if c.has_replacement_policy_number else "LEFT OUTER JOIN"
            rep_join = (
                f"{jt_52r} {T('TH_USER_REPLACEMENT')} USERDEF_52R"
                f" ON POLICY1.CK_SYS_CD = USERDEF_52R.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = USERDEF_52R.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = USERDEF_52R.TCH_POL_ID"
            )
            if c.has_replacement_policy_number:
                rep_join += " AND USERDEF_52R.REPLACED_POLICY IS NOT NULL"
            parts.append(rep_join)

        # ── Type V allocation count ─────────────────────────────────────
        if c.type_v_count_greater_than or c.type_v_count_less_than:
            av = (
                f"INNER JOIN {T('LH_FND_TRS_ALC_SET')} ALLOCATION_V_COUNT"
                f" ON POLICY1.CK_SYS_CD = ALLOCATION_V_COUNT.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = ALLOCATION_V_COUNT.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = ALLOCATION_V_COUNT.TCH_POL_ID"
                f" AND ALLOCATION_V_COUNT.FND_TRS_TYP_CD = 'V'"
            )
            if c.type_v_count_greater_than:
                av += f" AND ALLOCATION_V_COUNT.FND_ALC_SEQ_NBR >= {c.type_v_count_greater_than}"
            if c.type_v_count_less_than:
                av += f" AND ALLOCATION_V_COUNT.FND_ALC_SEQ_NBR <= {c.type_v_count_less_than}"
            parts.append(av)

        # ── TAMRA ───────────────────────────────────────────────────────
        parts.append(
            f"LEFT OUTER JOIN {T('LH_TAMRA_7_PY_PER')} TAMRA"
            f" ON POLICY1.CK_SYS_CD = TAMRA.CK_SYS_CD"
            f" AND POLICY1.CK_CMP_CD = TAMRA.CK_CMP_CD"
            f" AND POLICY1.TCH_POL_ID = TAMRA.TCH_POL_ID"
        )

        # ── Policy totals ──────────────────────────────────────────────
        parts.append(
            f"LEFT OUTER JOIN {T('LH_POL_TOTALS')} POLICY_TOTALS"
            f" ON POLICY1.CK_SYS_CD = POLICY_TOTALS.CK_SYS_CD"
            f" AND POLICY1.CK_CMP_CD = POLICY_TOTALS.CK_CMP_CD"
            f" AND POLICY1.TCH_POL_ID = POLICY_TOTALS.TCH_POL_ID"
        )

        # ── Year totals ────────────────────────────────────────────────
        parts.append(
            "LEFT OUTER JOIN LH_POL_YR_TOT_at_MaxDuration"
            " ON POLICY1.CK_SYS_CD = LH_POL_YR_TOT_at_MaxDuration.CK_SYS_CD"
            " AND POLICY1.CK_CMP_CD = LH_POL_YR_TOT_at_MaxDuration.CK_CMP_CD"
            " AND POLICY1.TCH_POL_ID = LH_POL_YR_TOT_at_MaxDuration.TCH_POL_ID"
        )

        # ── Target tables ──────────────────────────────────────────────
        if c.show_ctp:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_COM_TARGET')} COMMTARGET"
                f" ON POLICY1.CK_SYS_CD = COMMTARGET.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = COMMTARGET.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = COMMTARGET.TCH_POL_ID"
                f" AND COMMTARGET.TAR_TYP_CD = 'CT'"
            )
        if c.show_monthly_mtp:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_POL_TARGET')} MTP"
                f" ON POLICY1.CK_SYS_CD = MTP.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = MTP.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = MTP.TCH_POL_ID"
                f" AND MTP.TAR_TYP_CD = 'MT'"
            )
        if c.show_accum_monthly_mtp or c.accum_mtp_greater_than or c.accum_mtp_less_than:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_POL_TARGET')} ACCUMMTP"
                f" ON POLICY1.CK_SYS_CD = ACCUMMTP.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = ACCUMMTP.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = ACCUMMTP.TCH_POL_ID"
                f" AND ACCUMMTP.TAR_TYP_CD = 'MA'"
            )
        if c.show_accum_glp or c.accum_glp_greater_than or c.accum_glp_less_than:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_POL_TARGET')} ACCUMGLP"
                f" ON POLICY1.CK_SYS_CD = ACCUMGLP.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = ACCUMGLP.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = ACCUMGLP.TCH_POL_ID"
                f" AND ACCUMGLP.TAR_TYP_CD = 'TA'"
            )
        if c.show_short_pay_fields:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_POL_TARGET')} SHORTPAY_PRM"
                f" ON POLICY1.CK_SYS_CD = SHORTPAY_PRM.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = SHORTPAY_PRM.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = SHORTPAY_PRM.TCH_POL_ID"
                f" AND SHORTPAY_PRM.TAR_TYP_CD = 'VS'"
            )
        if c.show_shadow_av or c.shadow_av_greater_than or c.shadow_av_less_than:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_COV_TARGET')} SHADOWAV"
                f" ON POLICY1.CK_SYS_CD = SHADOWAV.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = SHADOWAV.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = SHADOWAV.TCH_POL_ID"
                f" AND SHADOWAV.TAR_TYP_CD = 'XP'"
            )
        if c.show_nsp:
            parts.append(
                f"LEFT OUTER JOIN {T('LH_POL_TARGET')} NSPTARGET"
                f" ON POLICY1.CK_SYS_CD = NSPTARGET.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = NSPTARGET.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = NSPTARGET.TCH_POL_ID"
                f" AND NSPTARGET.TAR_TYP_CD = 'NS'"
            )

        # ── Termination dates ───────────────────────────────────────────
        if c.needs_termination_dates:
            jt_td = "INNER JOIN" if (c.low_termination_date or c.high_termination_date) else "LEFT OUTER JOIN"
            parts.append(
                f"{jt_td} TERMINATION_DATES AS TD"
                f" ON POLICY1.CK_CMP_CD = TD.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = TD.TCH_POL_ID"
            )

        # ── Change segment ──────────────────────────────────────────────
        if c.transaction.has_change_segment:
            parts.append(
                "INNER JOIN CHANGE_SEGMENT"
                " ON POLICY1.CK_SYS_CD = CHANGE_SEGMENT.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = CHANGE_SEGMENT.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = CHANGE_SEGMENT.TCH_POL_ID"
            )

        # ── Loans ───────────────────────────────────────────────────────
        has_77 = (
            c.has_loan or c.has_preferred_loan or
            c.loan_principal_greater_than or c.loan_principal_less_than or
            c.loan_accrued_int_greater_than or c.loan_accrued_int_less_than
        )
        if has_77:
            loan_join = (
                "INNER JOIN ALL_LOANS"
                " ON POLICY1.CK_SYS_CD = ALL_LOANS.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = ALL_LOANS.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = ALL_LOANS.TCH_POL_ID"
            )
            if c.has_preferred_loan:
                loan_join += " AND (ALL_LOANS.PRF_LN_IND = '1')"
            parts.append(loan_join)

        if c.show_policy_debt or has_77:
            jt_pd = "INNER JOIN" if has_77 else "LEFT OUTER JOIN"
            pd_join = (
                f"{jt_pd} POLICYDEBT"
                f" ON POLICY1.CK_SYS_CD = POLICYDEBT.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = POLICYDEBT.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = POLICYDEBT.TCH_POL_ID"
            )
            if c.loan_principal_greater_than:
                pd_join += f" AND POLICYDEBT.LOAN_PRINCIPLE >= {c.loan_principal_greater_than}"
            if c.loan_principal_less_than:
                pd_join += f" AND POLICYDEBT.LOAN_PRINCIPLE <= {c.loan_principal_less_than}"
            if c.loan_accrued_int_greater_than:
                pd_join += f" AND POLICYDEBT.LOAN_ACCRUED >= {c.loan_accrued_int_greater_than}"
            if c.loan_accrued_int_less_than:
                pd_join += f" AND POLICYDEBT.LOAN_ACCRUED <= {c.loan_accrued_int_less_than}"
            parts.append(pd_join)

        # ── MVVAL ───────────────────────────────────────────────────────
        if c.needs_mvval or c.show_account_value_02_75:
            parts.append(
                "LEFT OUTER JOIN MVVAL"
                " ON POLICY1.CK_SYS_CD = MVVAL.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = MVVAL.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = MVVAL.TCH_POL_ID"
            )

        # ── COVSUMMARY ──────────────────────────────────────────────────
        if needs_covsummary:
            cs_join = (
                "INNER JOIN COVSUMMARY"
                " ON COVSUMMARY.TCH_POL_ID = POLICY1.TCH_POL_ID"
                " AND COVSUMMARY.CK_CMP_CD = POLICY1.CK_CMP_CD"
                " AND COVSUMMARY.CK_SYS_CD = POLICY1.CK_SYS_CD"
            )
            if c.multiple_base_coverages:
                cs_join += " AND (COVSUMMARY.BASECOVCOUNT > 1)"
            if c.current_sa_greater_than:
                cs_join += f" AND (COVSUMMARY.TOTAL_SA >= {c.current_sa_greater_than})"
            if c.current_sa_less_than:
                cs_join += f" AND (COVSUMMARY.TOTAL_SA <= {c.current_sa_less_than})"
            parts.append(cs_join)

        # ── BILLMODE_POOL ───────────────────────────────────────────────
        if c.billing_modes or c.show_billing_mode:
            parts.append(
                "INNER JOIN BILLMODE_POOL"
                " ON POLICY1.CK_SYS_CD = BILLMODE_POOL.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = BILLMODE_POOL.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = BILLMODE_POOL.TCH_POL_ID"
            )

        # ── GRACE_TABLE ─────────────────────────────────────────────────
        if c.needs_grace_table or bool(c.grace_indicators):
            gt_join = (
                "INNER JOIN GRACE_TABLE"
                " ON POLICY1.CK_SYS_CD = GRACE_TABLE.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = GRACE_TABLE.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = GRACE_TABLE.TCH_POL_ID"
            )
            if c.low_gpe_date:
                gt_join += f" AND (GRACE_TABLE.GRA_PER_EXP_DT >= '{c.low_gpe_date}')"
            if c.high_gpe_date:
                gt_join += f" AND (GRACE_TABLE.GRA_PER_EXP_DT <= '{c.high_gpe_date}')"
            parts.append(gt_join)

        # ── GLP ─────────────────────────────────────────────────────────
        if c.glp_negative or c.show_glp:
            parts.append(
                "INNER JOIN GLP"
                " ON POLICY1.CK_SYS_CD = GLP.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = GLP.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = GLP.TCH_POL_ID"
            )

        # ── GSP ─────────────────────────────────────────────────────────
        if c.show_gsp:
            parts.append(
                "LEFT OUTER JOIN GSP"
                " ON POLICY1.CK_SYS_CD = GSP.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = GSP.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = GSP.TCH_POL_ID"
            )

        # ── ISWL_INTERPOLATED_GCV ──────────────────────────────────────
        if c.iswl_gcv_gt_curr_cv or c.iswl_gcv_lt_curr_cv:
            parts.append(
                "INNER JOIN ISWL_INTERPOLATED_GCV"
                " ON POLICY1.CK_SYS_CD = ISWL_INTERPOLATED_GCV.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = ISWL_INTERPOLATED_GCV.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = ISWL_INTERPOLATED_GCV.TCH_POL_ID"
            )

        # ── Interpolation months ────────────────────────────────────────
        if c.show_trad_cv:
            parts.append(
                "LEFT OUTER JOIN INTERPOLATION_MONTHS"
                " ON POLICY1.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID"
            )

        # ── RPU CHANGE_TYPE9 ────────────────────────────────────────────
        if c.rpu_original_amt:
            parts.append(
                "LEFT OUTER JOIN CHANGE_TYPE9"
                " ON POLICY1.CK_SYS_CD = CHANGE_TYPE9.CK_SYS_CD"
                " AND POLICY1.CK_CMP_CD = CHANGE_TYPE9.CK_CMP_CD"
                " AND POLICY1.TCH_POL_ID = CHANGE_TYPE9.TCH_POL_ID"
            )

        # ── Transaction (FH_FIXED) ──────────────────────────────────────
        if c.transaction.enabled:
            t = c.transaction
            tr_join = (
                f"INNER JOIN {T('FH_FIXED')} TR1"
                f" ON POLICY1.CK_CMP_CD = TR1.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = TR1.TCH_POL_ID"
            )
            if t.transaction_type:
                tr_join += f" AND (TR1.TRANS = '{t.transaction_type[:2]}')"
            if t.low_entry_date:
                tr_join += f" AND TR1.ENTRY_DT >= '{t.low_entry_date}'"
            if t.high_entry_date:
                tr_join += f" AND TR1.ENTRY_DT <= '{t.high_entry_date}'"
            if t.low_effective_date:
                tr_join += f" AND TR1.ASOF_DT >= '{t.low_effective_date}'"
            if t.high_effective_date:
                tr_join += f" AND TR1.ASOF_DT <= '{t.high_effective_date}'"
            if t.on_issue_day:
                tr_join += " AND DAY(TR1.ASOF_DT) = DAY(COVERAGE1.ISSUE_DT)"
            if t.on_issue_month:
                tr_join += " AND MONTH(TR1.ASOF_DT) = MONTH(COVERAGE1.ISSUE_DT)"
            if t.low_effective_month:
                tr_join += f" AND MONTH(TR1.ASOF_DT) >= {t.low_effective_month}"
            if t.high_effective_month:
                tr_join += f" AND MONTH(TR1.ASOF_DT) <= {t.high_effective_month}"
            if t.low_effective_day:
                tr_join += f" AND DAY(TR1.ASOF_DT) >= {t.low_effective_day}"
            if t.high_effective_day:
                tr_join += f" AND DAY(TR1.ASOF_DT) <= {t.high_effective_day}"
            if t.low_gross_amount:
                tr_join += f" AND TR1.GROSS_AMT >= {t.low_gross_amount}"
            if t.high_gross_amount:
                tr_join += f" AND TR1.GROSS_AMT <= {t.high_gross_amount}"
            if t.origin_of_transaction:
                tr_join += f" AND TR1.ORIGIN_OF_TRANS ='{t.origin_of_transaction}'"
            if c.fund_id_list:
                fund_list = ",".join(f"'{f.strip()}'" for f in c.fund_id_list.split(","))
                tr_join += f" AND TR1.FUND_ID IN({fund_list})"
            parts.append(tr_join)

        return " ".join(parts)

    # ─── WHERE Clause ───────────────────────────────────────────────────

    def _build_where(self) -> str:
        """Build WHERE clause with all conditional filters."""
        c = self.c
        today = _today()
        dur = _duration_calc()
        att = _attained_age_calc()
        clauses: List[str] = ["WHERE 1 = 1"]

        # System code
        if c.system_code:
            clauses.append(f"AND POLICY1.CK_SYS_CD='{c.system_code}'")

        # Company / Market Org
        if c.market_org and not c.company:
            # Market org without specific company — infer valid companies
            company_codes = COMPANY_MARKET_ORG_MAP.get(c.market_org, [])
            if company_codes:
                cc_or = " OR ".join(f"POLICY1.CK_CMP_CD ='{cc}'" for cc in company_codes)
                clauses.append(f"AND ({cc_or})")
        elif c.company:
            clauses.append(f"AND POLICY1.CK_CMP_CD ='{c.company}'")

        if c.market_org:
            agent_code = MARKET_ORG_AGENT_CODES.get(c.market_org, "")
            if agent_code:
                clauses.append(f"AND SUBSTR(POLICY1.SVC_AGC_NBR,1,1)='{agent_code}'")

        if c.branch_number:
            clauses.append(f"AND SUBSTR(POLICY1.SVC_AGC_NBR,2,3)='{c.branch_number}'")

        # Loan charge rate
        if c.loan_charge_rate:
            clauses.append(f"AND POLICY1.LN_PLN_ITS_RT = {c.loan_charge_rate}")

        # TAMRA (59 segment)
        if c.mec:
            clauses.append("AND TAMRA.MEC_STA_CD = '1'")
        if c.amount_1035:
            clauses.append("AND TAMRA.XCG_1035_PMT_QTY > 0")
        if c.seven_pay_greater_than:
            clauses.append(f"AND TAMRA.SVPY_LVL_PRM_AMT >= {c.seven_pay_greater_than}")
        if c.seven_pay_less_than:
            clauses.append(f"AND TAMRA.SVPY_LVL_PRM_AMT <= {c.seven_pay_less_than}")
        if c.seven_pay_av_greater_than:
            clauses.append(f"AND TAMRA.SVPY_BEG_CSV_AMT >= {c.seven_pay_av_greater_than}")
        if c.seven_pay_av_less_than:
            clauses.append(f"AND TAMRA.SVPY_BEG_CSV_AMT <= {c.seven_pay_av_less_than}")

        # Policy totals
        if c.accum_wd_greater_than:
            clauses.append(f"AND POLICY_TOTALS.TOT_WTD_AMT >= {c.accum_wd_greater_than}")
        if c.accum_wd_less_than:
            clauses.append(f"AND POLICY_TOTALS.TOT_WTD_AMT <= {c.accum_wd_less_than}")
        if c.prem_ytd_greater_than:
            clauses.append(f"AND POLICY_TOTALS_YTD.YTD_TOT_PMT_AMT >= {c.prem_ytd_greater_than}")
        if c.prem_ytd_less_than:
            clauses.append(f"AND POLICY_TOTALS_YTD.YTD_TOT_PMT_AMT <= {c.prem_ytd_less_than}")
        if c.additional_prem_greater_than:
            clauses.append(f"AND POLICY_TOTALS.TOT_ADD_PRM_AMT >= {float(c.additional_prem_greater_than)}")
        if c.additional_prem_less_than:
            clauses.append(f"AND POLICY_TOTALS.TOT_ADD_PRM_AMT <= {float(c.additional_prem_less_than)}")
        if c.total_prem_greater_than:
            clauses.append(f"AND (POLICY_TOTALS.TOT_ADD_PRM_AMT + POLICY_TOTALS.TOT_REG_PRM_AMT) >= {float(c.total_prem_greater_than)}")
        if c.total_prem_less_than:
            clauses.append(f"AND (POLICY_TOTALS.TOT_ADD_PRM_AMT + POLICY_TOTALS.TOT_REG_PRM_AMT) <= {float(c.total_prem_less_than)}")

        # Date ranges
        if c.low_paid_to_date:
            clauses.append(f"AND POLICY1.PRM_PAID_TO_DT >= '{c.low_paid_to_date}'")
        if c.high_paid_to_date:
            clauses.append(f"AND POLICY1.PRM_PAID_TO_DT <= '{c.high_paid_to_date}'")
        if c.low_last_financial_date:
            clauses.append(f"AND POLICY1.LST_FIN_DT >= '{c.low_last_financial_date}'")
        if c.high_last_financial_date:
            clauses.append(f"AND POLICY1.LST_FIN_DT <= '{c.high_last_financial_date}'")
        if c.low_app_date:
            clauses.append(f"AND POLICY1.APP_WRT_DT >= '{c.low_app_date}'")
        if c.high_app_date:
            clauses.append(f"AND POLICY1.APP_WRT_DT <= '{c.high_app_date}'")

        # Attained age
        if c.low_current_age:
            clauses.append(
                f"AND COVERAGE1.INS_ISS_AGE >= ({int(c.low_current_age)}"
                f" - TRUNCATE(MONTHS_BETWEEN('{today}',COVERAGE1.ISSUE_DT)/12,0))"
            )
        if c.high_current_age:
            clauses.append(
                f"AND COVERAGE1.INS_ISS_AGE <= ({int(c.high_current_age)}"
                f" - TRUNCATE(MONTHS_BETWEEN('{today}',COVERAGE1.ISSUE_DT)/12,0))"
            )

        # Policy year
        if c.low_current_policy_year:
            clauses.append(
                f"AND (TRUNCATE(MONTHS_BETWEEN('{today}',COVERAGE1.ISSUE_DT)/12,0) +1) >= {int(c.low_current_policy_year)}"
            )
        if c.high_current_policy_year:
            clauses.append(
                f"AND (TRUNCATE(MONTHS_BETWEEN('{today}',COVERAGE1.ISSUE_DT)/12,0) +1) <= {int(c.high_current_policy_year)}"
            )

        # Change dates
        if c.low_last_change_date:
            clauses.append(f"AND NEWBUS.LST_CHG_DT >= '{c.low_last_change_date}'")
        if c.high_last_change_date:
            clauses.append(f"AND NEWBUS.LST_CHG_DT <= '{c.high_last_change_date}'")

        # Bill commence dates
        if c.low_bill_commence_date:
            clauses.append(f"AND NONTRAD.BIL_COMMENCE_DT >= '{c.low_bill_commence_date}'")
        if c.high_bill_commence_date:
            clauses.append(f"AND NONTRAD.BIL_COMMENCE_DT <= '{c.high_bill_commence_date}'")

        # Policy number pattern
        if c.policy_number_pattern:
            pn = c.policy_number_pattern
            criterion = c.policy_number_criteria
            if criterion == "1":
                clauses.append(f"AND (TRIM(TRAILING FROM POLICY1.CK_POLICY_NBR) Like '{pn}%')")
            elif criterion == "2":
                clauses.append(f"AND (TRIM(TRAILING FROM POLICY1.CK_POLICY_NBR) Like '%{pn}')")
            elif criterion == "3":
                clauses.append(f"AND (TRIM(TRAILING FROM POLICY1.CK_POLICY_NBR) Like '%{pn}%')")

        # Form number
        if c.form_number_like:
            clauses.append(f"AND (COVERAGE1.POL_FRM_NBR Like '{c.form_number_like}%')")

        # Billing premium
        if c.low_billing_prem:
            clauses.append(f"AND POLICY1.POL_PRM_AMT >= {float(c.low_billing_prem)}")
        if c.high_billing_prem:
            clauses.append(f"AND POLICY1.POL_PRM_AMT <= {float(c.high_billing_prem)}")

        # States
        if c.states:
            state_conditions = []
            for st in c.states:
                cyberlife_code = STATE_CODES.get(st, "")
                if cyberlife_code:
                    state_conditions.append(f"POLICY1.POL_ISS_ST_CD = '{cyberlife_code:>02}'")
            if state_conditions:
                clauses.append(f"AND ({' OR '.join(state_conditions)})")

        # Multi-select list filters
        if c.billing_forms:
            clauses.append(self._in_clause("POLICY1.BIL_FRM_CD", c.billing_forms, 1))
        if c.slr_billing_forms:
            clauses.append(self._in_clause("SLR_BILL_CONTROL.BIL_FRM_CD", c.slr_billing_forms, 1))
        if c.nfo_options:
            clauses.append(self._in_clause("POLICY1.NFO_OPT_TYP_CD", c.nfo_options, 1))
        if c.loan_types:
            clauses.append(self._in_clause("POLICY1.LN_TYP_CD", c.loan_types, 1))
        if c.primary_div_options:
            clauses.append(self._in_clause("POLICY1.PRI_DIV_OPT_CD", c.primary_div_options, 1))
        if c.status_codes:
            clauses.append(self._in_clause("POLICY1.PRM_PAY_STA_REA_CD", c.status_codes, 2))
        if c.grace_indicators:
            clauses.append(self._in_clause("SUBSTR(GRACE_TABLE.IN_GRA_PER_IND,1,1)", c.grace_indicators, 1))
        if c.overloan_indicators:
            clauses.append(self._in_clause("POLICY1_MOD.OVERLOAN_IND", c.overloan_indicators, 1))
        if c.suspense_codes:
            clauses.append(self._in_clause("POLICY1.SUS_CD", c.suspense_codes, 1))
        if c.reinsurance_codes:
            clauses.append(self._in_clause("POLICY1.REINSURED_CD", c.reinsurance_codes, 1))
        if c.non_trad_indicators:
            clauses.append(self._in_clause("POLICY1.NON_TRD_POL_IND", c.non_trad_indicators, 1))
        if c.last_entry_codes:
            clauses.append(self._in_clause("POLICY1.LST_ETR_CD", c.last_entry_codes, 1))

        # Boolean comparison filters
        if c.ul_in_corridor:
            clauses.append("AND (MVVAL.DB > COVSUMMARY.TOTAL_SA + MVVAL.OPTDB)")
        if c.av_gt_premium:
            clauses.append("AND (MVVAL.CSV_AMT >= MVVAL.TOTALPREM)")
        if c.glp_negative:
            clauses.append("AND (GLP.GLP_VALUE < 0)")
        if c.current_sa_lt_original:
            clauses.append("AND (COVSUMMARY.TOTAL_SA <= COVSUMMARY.TOTAL_ORIGINAL_SA)")
        if c.current_sa_gt_original:
            clauses.append("AND (COVSUMMARY.TOTAL_SA >= COVSUMMARY.TOTAL_ORIGINAL_SA)")
        if c.iswl_gcv_gt_curr_cv:
            clauses.append("AND (ISWL_INTERPOLATED_GCV.ISWL_GCV >= MVVAL.CSV_AMT)")
        if c.iswl_gcv_lt_curr_cv:
            clauses.append("AND (ISWL_INTERPOLATED_GCV.ISWL_GCV <= MVVAL.CSV_AMT)")
        if c.av_greater_than:
            clauses.append(f"AND (MVVAL.CSV_AMT > {float(c.av_greater_than)})")
        if c.av_less_than:
            clauses.append(f"AND (MVVAL.CSV_AMT < {float(c.av_less_than)})")
        if c.shadow_av_greater_than:
            clauses.append(f"AND (SHADOWAV.TAR_PRM_AMT >= {float(c.shadow_av_greater_than)})")
        if c.shadow_av_less_than:
            clauses.append(f"AND (SHADOWAV.TAR_PRM_AMT <= {float(c.shadow_av_less_than)})")
        if c.accum_mtp_greater_than:
            clauses.append(f"AND (ACCUMMTP.TAR_PRM_AMT >= {float(c.accum_mtp_greater_than)})")
        if c.accum_mtp_less_than:
            clauses.append(f"AND (ACCUMMTP.TAR_PRM_AMT <= {float(c.accum_mtp_less_than)})")
        if c.accum_glp_greater_than:
            clauses.append(f"AND (ACCUMGLP.TAR_PRM_AMT >= {float(c.accum_glp_greater_than)})")
        if c.accum_glp_less_than:
            clauses.append(f"AND (ACCUMGLP.TAR_PRM_AMT <= {float(c.accum_glp_less_than)})")
        if c.is_mdo:
            clauses.append("AND SUBSTR(POLICY1.USR_RES_CD,1,1) = 'Y'")
        if c.is_rga:
            clauses.append("AND USERDEF_52G.FUZGREIN_IND = 'R'")

        # Change segment codes
        if c.transaction.has_change_segment and c.transaction.change_codes_68:
            clauses.append(self._in_clause("CHANGE_SEGMENT.CHG_TYP_CD", c.transaction.change_codes_68, 1))

        # Conversion period
        if c.within_conversion_period:
            clauses.append(
                f"AND (CASE"
                f" WHEN (UPDF.CONVERSION_PERIOD = 0"
                f" AND COVERAGE1.INS_ISS_AGE + TRUNCATE(MONTHS_BETWEEN(DATE('{today}'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_AGE)"
                f" OR (UPDF.CONVERSION_PERIOD > 0"
                f" AND TRUNCATE(MONTHS_BETWEEN(DATE('{today}'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_PERIOD"
                f" AND COVERAGE1.INS_ISS_AGE + TRUNCATE(MONTHS_BETWEEN(DATE('{today}'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_AGE)"
                f" THEN 'TRUE' ELSE 'FALSE'"
                f" END) = 'TRUE'"
            )

        return " ".join(clauses)

    # ─── Rider JOINs ────────────────────────────────────────────────────

    def _build_rider_joins(self) -> str:
        """Build rider JOIN clauses for all 3 rider slots."""
        c = self.c
        T = lambda t: _tbl(t, self._region)  # noqa: E731
        parts: List[str] = []

        for idx, rider in enumerate([c.rider1, c.rider2, c.rider3], start=1):
            if not rider.enabled:
                continue
            alias = f"RIDER{idx}"
            rj = (
                f"INNER JOIN {T('LH_COV_PHA')} {alias}"
                f" ON POLICY1.CK_SYS_CD = {alias}.CK_SYS_CD"
                f" AND POLICY1.CK_CMP_CD = {alias}.CK_CMP_CD"
                f" AND POLICY1.TCH_POL_ID = {alias}.TCH_POL_ID"
                f" AND {alias}.COV_PHA_NBR > 1"
            )
            if rider.plancode:
                rj += f" AND {alias}.PLN_DES_SER_CD = '{rider.plancode}'"
            if rider.person_code:
                rj += f" AND {alias}.PRS_CD = '{rider.person_code[:2]}'"
            if rider.sex_code_02:
                rj += f" AND {alias}.INS_SEX_CD = '{rider.sex_code_02[:1]}'"
            if rider.post_issue:
                rj += f" AND {alias}.ISSUE_DT > COVERAGE1.ISSUE_DT"
            if rider.low_issue_date:
                rj += f" AND {alias}.ISSUE_DT >= '{rider.low_issue_date}'"
            if rider.high_issue_date:
                rj += f" AND {alias}.ISSUE_DT <= '{rider.high_issue_date}'"
            if rider.product_line_code:
                rj += f" AND {alias}.PRD_LIN_TYP_CD = '{rider.product_line_code[:1]}'"
            if rider.change_type:
                rj += f" AND {alias}.NXT_CHG_TYP_CD = '{rider.change_type[:1]}'"
            if rider.low_change_date:
                rj += f" AND {alias}.NXT_CHG_DT >= '{rider.low_change_date}'"
            if rider.high_change_date:
                rj += f" AND {alias}.NXT_CHG_DT <= '{rider.high_change_date}'"
            if rider.lives_covered_code:
                rj += f" AND {alias}.LIVES_COV_CD = '{rider.lives_covered_code[:1]}'"
            if rider.additional_plancode_criteria:
                if rider.additional_plancode_criteria.startswith("1"):
                    rj += f" AND {alias}.PLN_DES_SER_CD = COVERAGE1.PLN_DES_SER_CD"
                elif rider.additional_plancode_criteria.startswith("2"):
                    rj += f" AND {alias}.PLN_DES_SER_CD <> COVERAGE1.PLN_DES_SER_CD"
            parts.append(rj)

            # Table rating for rider
            if rider.table_rating:
                parts.append(
                    f"INNER JOIN {T('LH_SST_XTR_CRG')} {alias}_TABLE_RATING"
                    f" ON {alias}.CK_SYS_CD = {alias}_TABLE_RATING.CK_SYS_CD"
                    f" AND {alias}.CK_CMP_CD = {alias}_TABLE_RATING.CK_CMP_CD"
                    f" AND {alias}.TCH_POL_ID = {alias}_TABLE_RATING.TCH_POL_ID"
                    f" AND {alias}.COV_PHA_NBR = {alias}_TABLE_RATING.COV_PHA_NBR"
                    f" AND ({alias}_TABLE_RATING.SST_XTR_TYP_CD ='0'"
                    f" Or {alias}_TABLE_RATING.SST_XTR_TYP_CD ='1'"
                    f" Or {alias}_TABLE_RATING.SST_XTR_TYP_CD ='3')"
                )

            # Flat extra for rider
            if rider.flat_extra:
                parts.append(
                    f"INNER JOIN {T('LH_SST_XTR_CRG')} {alias}_FLAT_EXTRA"
                    f" ON {alias}.CK_SYS_CD = {alias}_FLAT_EXTRA.CK_SYS_CD"
                    f" AND {alias}.CK_CMP_CD = {alias}_FLAT_EXTRA.CK_CMP_CD"
                    f" AND {alias}.TCH_POL_ID = {alias}_FLAT_EXTRA.TCH_POL_ID"
                    f" AND {alias}.COV_PHA_NBR = {alias}_FLAT_EXTRA.COV_PHA_NBR"
                    f" AND ({alias}_FLAT_EXTRA.SST_XTR_TYP_CD ='2'"
                    f" Or {alias}_FLAT_EXTRA.SST_XTR_TYP_CD ='4')"
                )

            # Product indicator / COLA / GIO for rider
            if rider.product_indicator or rider.cola_indicator or rider.gio_fio_indicator:
                mod_alias = f"{alias}COVMOD"
                mod_join = (
                    f"INNER JOIN {T('TH_COV_PHA')} {mod_alias}"
                    f" ON {mod_alias}.CK_SYS_CD = {alias}.CK_SYS_CD"
                    f" AND {mod_alias}.CK_CMP_CD = {alias}.CK_CMP_CD"
                    f" AND {mod_alias}.TCH_POL_ID = {alias}.TCH_POL_ID"
                    f" AND {mod_alias}.COV_PHA_NBR = {alias}.COV_PHA_NBR"
                )
                if rider.product_indicator:
                    mod_join += f" AND ({mod_alias}.AN_PRD_ID = '{rider.product_indicator[:1]}')"
                if rider.cola_indicator:
                    mod_join += f" AND {mod_alias}.COLA_INCR_IND = '{rider.cola_indicator}'"
                if rider.gio_fio_indicator:
                    if rider.gio_fio_indicator == "blank":
                        mod_join += f" AND {mod_alias}.OPT_EXER_IND = ''"
                    else:
                        mod_join += f" AND {mod_alias}.OPT_EXER_IND = '{rider.gio_fio_indicator}'"
                parts.append(mod_join)

            # Rate class / sex code for rider
            if rider.rateclass_code_67 or rider.sex_code_67:
                rnl_alias = f"{alias}_RENEWALS"
                rnl = (
                    f"INNER JOIN {T('LH_COV_INS_RNL_RT')} {rnl_alias}"
                    f" ON {alias}.CK_SYS_CD = {rnl_alias}.CK_SYS_CD"
                    f" AND {alias}.CK_CMP_CD = {rnl_alias}.CK_CMP_CD"
                    f" AND {alias}.TCH_POL_ID = {rnl_alias}.TCH_POL_ID"
                    f" AND {alias}.COV_PHA_NBR = {rnl_alias}.COV_PHA_NBR"
                    f" AND {rnl_alias}.PRM_RT_TYP_CD = 'C'"
                )
                if rider.rateclass_code_67:
                    rnl += f" AND ({rnl_alias}.RT_CLS_CD = '{rider.rateclass_code_67[:1]}')"
                if rider.sex_code_67:
                    rnl += f" AND ({rnl_alias}.RT_SEX_CD = '{rider.sex_code_67[:1]}')"
                parts.append(rnl)

        return " ".join(parts)

    # ─── Helper methods ─────────────────────────────────────────────────

    @staticmethod
    def _in_clause(field: str, values: list, left_len: int) -> str:
        """
        Build an AND (...OR...) clause from a list of values.
        
        Matches the VBA AddListBoxEntriesToSQL pattern.
        Each value is trimmed to left_len characters.
        """
        if not values:
            return ""
        conditions = []
        for val in values:
            trimmed = str(val)[:left_len] if left_len else str(val)
            if trimmed.upper() == "NULL":
                conditions.append(f"{field} IS NULL")
            else:
                conditions.append(f"{field} ='{trimmed}'")
        return f" AND ({' OR '.join(conditions)})"

    @staticmethod
    def _billing_mode_case(alias: str) -> str:
        """Build the billing mode CASE expression."""
        return (
            f"(CASE BILLMODE_POOL.PMT_FQY_PER"
            f" WHEN 1 THEN"
            f" (CASE BILLMODE_POOL.NSD_MD_CD"
            f" WHEN '2' THEN 'BiWeekly'"
            f" WHEN 'S' THEN 'SemiMonthly'"
            f" WHEN '9' THEN '9thly'"
            f" WHEN 'A' THEN '10thly'"
            f" ELSE 'Monthly'"
            f" End)"
            f" WHEN 3 THEN 'Quarterly'"
            f" WHEN 6 THEN 'SemiAnnually'"
            f" WHEN 12 THEN 'Annually'"
            f" ELSE ' '"
            f" End) {alias}"
        )

    @staticmethod
    def _billing_freq_case(alias: str) -> str:
        """Build the billing frequency CASE expression."""
        return (
            f"(CASE BILLMODE_POOL.PMT_FQY_PER"
            f" WHEN 1 THEN"
            f" (CASE BILLMODE_POOL.NSD_MD_CD"
            f" WHEN '2' THEN 26"
            f" WHEN 'S' THEN 24"
            f" WHEN '9' THEN 9"
            f" WHEN 'A' THEN 10"
            f" ELSE 12"
            f" End)"
            f" WHEN 3 THEN 4"
            f" WHEN 6 THEN 2"
            f" WHEN 12 THEN 1"
            f" ELSE ' '"
            f" End) {alias}"
        )

    @staticmethod
    def _billing_freq_case_expr() -> str:
        """Billing frequency CASE expression without alias (for computation)."""
        return (
            "(CASE BILLMODE_POOL.PMT_FQY_PER"
            " WHEN 1 THEN"
            " (CASE BILLMODE_POOL.NSD_MD_CD"
            " WHEN '2' THEN 26"
            " WHEN 'S' THEN 24"
            " WHEN '9' THEN 9"
            " WHEN 'A' THEN 10"
            " ELSE 12"
            " End)"
            " WHEN 3 THEN 4"
            " WHEN 6 THEN 2"
            " WHEN 12 THEN 1"
            " ELSE ' '"
            " End)"
        )
