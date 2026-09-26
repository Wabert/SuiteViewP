from __future__ import annotations


def _conversion_sc_cte(schema: str) -> str:
    """Keep both dates from one eligible SC row, never independent MAX dates."""
    return f"CONVERSION_SC AS\n  (SELECT CONVERTED_POLICY.CK_SYS_CD, FH.CK_CMP_CD, FH.TCH_POL_ID,\n    FH.ENTRY_DT AS CONV_SC_ENTRY_DT, FH.ASOF_DT AS CONV_SC_EFFECTIVE_DT,\n    ROW_NUMBER() OVER (\n      PARTITION BY CONVERTED_POLICY.CK_SYS_CD, FH.CK_CMP_CD, FH.TCH_POL_ID\n      ORDER BY FH.ENTRY_DT DESC NULLS LAST, FH.ENTRY_TIME DESC NULLS LAST,\n               FH.SEQ_NO DESC) AS SC_ROW\n   FROM {schema}.FH_FIXED FH\n   INNER JOIN {schema}.LH_BAS_POL CONVERTED_POLICY\n     ON CONVERTED_POLICY.CK_CMP_CD = FH.CK_CMP_CD\n    AND CONVERTED_POLICY.TCH_POL_ID = FH.TCH_POL_ID\n    AND CONVERTED_POLICY.LST_ETR_CD = 'O'\n   WHERE FH.TRANS = 'SC'\n     AND FH.FCB0_REV_IND = '0'\n     AND FH.FCB2_REV_APPL_IND = '0')"

def _post_conversion_cte(schema: str) -> str:
    """Reverse the destination's source reference; keep every distinct destination."""
    return f"POST_CONVERSION AS\n  (SELECT DISTINCT G.CK_SYS_CD,\n    TRIM(G.SOURCE_CMP_CODE) AS SOURCE_CMP_CODE,\n    TRIM(G.EXCH_POL_NUMBER) AS SOURCE_POLICY_NBR,\n    DEST.CK_CMP_CD AS POST_CONV_COMPANY,\n    DEST.CK_POLICY_NBR AS POST_CONV_POLICY\n   FROM {schema}.TH_USER_GENERIC G\n   INNER JOIN {schema}.LH_BAS_POL DEST\n     ON G.CK_SYS_CD = DEST.CK_SYS_CD\n    AND G.CK_CMP_CD = DEST.CK_CMP_CD\n    AND G.TCH_POL_ID = DEST.TCH_POL_ID\n   WHERE TRIM(G.SOURCE_CMP_CODE) <> ''\n     AND TRIM(G.EXCH_POL_NUMBER) <> '')"

def _valuation_date_sql(schema: str) -> str:
    """SQL expression for the policy valuation date.

    Mirrors PolView's ``PolicyInformation.valuation_date`` across product
    types:
      • advanced products (``NON_TRD_POL_IND='1'``) → most recent
        monthliversary (``LH_POL_MVRY_VAL.MVRY_DT``);
      • otherwise → last processed monthliversary
        (``NXT_MVRY_PRC_DT − 1 month``);
      • otherwise → last financial date (``LST_FIN_DT``).
    ``9999`` sentinel dates are excluded at every step.
    """
    return f"COALESCE(CASE WHEN POLICY1.NON_TRD_POL_IND = '1' THEN (SELECT MAX(MV.MVRY_DT) FROM {schema}.LH_POL_MVRY_VAL MV WHERE MV.CK_SYS_CD = POLICY1.CK_SYS_CD AND MV.CK_CMP_CD = POLICY1.CK_CMP_CD AND MV.TCH_POL_ID = POLICY1.TCH_POL_ID AND YEAR(MV.MVRY_DT) < 9999) END, CASE WHEN POLICY1.NXT_MVRY_PRC_DT IS NOT NULL AND YEAR(POLICY1.NXT_MVRY_PRC_DT) < 9999 THEN POLICY1.NXT_MVRY_PRC_DT - 1 MONTH END, CASE WHEN POLICY1.LST_FIN_DT IS NOT NULL AND YEAR(POLICY1.LST_FIN_DT) < 9999 THEN POLICY1.LST_FIN_DT END)"
