def build_query(inforce_only=False, exclude_suspended=False, market_org=0, 
                company_code='', partner_code='', policy_number=None, issue_state_abbr=''):
    """
    Build dynamic SQL query for policy coverage data
    
    Args:
        inforce_only: Boolean - Filter to inforce policies only (status 12-96)
        exclude_suspended: Boolean - Exclude suspended policies
        market_org: Integer - Market organization filter (0 = no filter)
        company_code: String - Company code filter
        partner_code: String - Partner code (adds JOIN if provided)
        policy_number: String or List - Policy number(s) to filter
        issue_state_abbr: String - Issue state abbreviation
    
    Returns:
        SQL query string
    """
    
    # Handle PolicyNumber - can be list or string
    if policy_number is not None:
        if isinstance(policy_number, list):
            if len(policy_number) > 0:
                # Join list items with quotes
                policy_nums = ", ".join(f"'{num}'" for num in policy_number)
                policy_number_line = f"AND POL.CK_POLICY_NBR IN ({policy_nums})"
            else:
                policy_number_line = ''
        elif isinstance(policy_number, str) and policy_number != '':
            # String - use LIKE
            policy_number_line = f"AND RTRIM(POL.CK_POLICY_NBR) LIKE '%{policy_number}'"
        else:
            policy_number_line = ''
    else:
        policy_number_line = ''
    
    # Build conditional WHERE clauses
    status_code_line = "AND POL.PRM_PAY_STA_REA_CD < 97 AND POL.PRM_PAY_STA_REA_CD > 11" if inforce_only else ""
    
    market_org_line = f"AND POL.SVC_AGC_NBR LIKE '{market_org}%'" if market_org != 0 else ""
    
    suspense_line = "AND POL.SUS_CD < 2" if exclude_suspended else ""
    
    company_code_line = f"AND POL.CK_CMP_CD = '{company_code}'" if company_code != '' else ""
    
    # Partner code adds an INNER JOIN
    if partner_code != '':
        partner_code_line = """INNER JOIN DB2TAB.TH_USER_GENERIC GEN
            ON POL.TCH_POL_ID = GEN.TCH_POL_ID
            AND POL.CK_CMP_CD = GEN.CK_CMP_CD
            AND POL.CK_SYS_CD = GEN.CK_SYS_CD
            AND GEN.FUZGREIN_IND = 'R'"""
    else:
        partner_code_line = ""
    
    # Note: GetStateMapping() is R-specific - you may need to handle state mapping differently
    # For now, using the abbreviation directly
    issue_state_line = f"AND POL.POL_ISS_ST_CD = '{issue_state_abbr}'" if issue_state_abbr != '' else ""
    
    # Build the complete SQL query
    sql = f"""
SELECT 
    POL.CK_CMP_CD
    ,POL.TCH_POL_ID
    ,POL.CK_POLICY_NBR
    ,POL.PRM_PAY_STA_REA_CD AS POL_STATUS
    ,POL.POL_ISS_ST_CD
    ,LEFT(POL.SVC_AGC_NBR,1) AS MrkOrg
    ,POL.LST_ETR_CD
    ,POL.LST_FIN_DT
    ,POL.LST_ANV_DT
    ,POL.OGN_ETR_CD
    ,POL.SUS_CD
    ,POL.POL_PRM_AMT
    ,POL.BIL_FRM_CD
    ,POL.PMT_FQY_PER
    ,POL.NSD_MD_CD
    ,COV.PLN_DES_SER_CD
    ,COV.COV_PHA_NBR
    ,COV.POL_FRM_NBR
    ,COV.ISSUE_DT
    ,COV.INS_ISS_AGE
    ,COV.INS_SEX_CD
    ,COV.NXT_CHG_TYP_CD
    ,COV.NXT_CHG_DT
    ,ROUND(REAL(COV.COV_UNT_QTY) * REAL(COV.COV_VPU_AMT),0) AS FACE
FROM DB2TAB.LH_BAS_POL POL
INNER JOIN DB2TAB.LH_COV_PHA COV
    ON POL.TCH_POL_ID = COV.TCH_POL_ID
    AND POL.CK_CMP_CD = COV.CK_CMP_CD
    AND POL.CK_SYS_CD = COV.CK_SYS_CD
{partner_code_line}
WHERE
    COV.COV_PHA_NBR = 1
    AND POL.CK_SYS_CD = 'I'
    {status_code_line}
    {market_org_line}
    {suspense_line}
    {company_code_line}
    {policy_number_line}
    {issue_state_line}
LIMIT 10000000
"""
    
    return sql
