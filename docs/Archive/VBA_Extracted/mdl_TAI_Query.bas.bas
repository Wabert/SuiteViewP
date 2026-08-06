' Module: mdl_TAI_Query.bas
' Type: Standard Module
' Stream Path: VBA/mdl_TAI_Query
' =========================================================

Attribute VB_Name = "mdl_TAI_Query"



Public Function TAI_Quick_Policy_Data(ValDate As String, CompanyCode As String, PolicyNumber As String)
Dim sqlstring  As String
Dim dataArray

    sqlstring = sqlstring & "SELECT "
        sqlstring = sqlstring & " [_MonthEnd] "
        sqlstring = sqlstring & ",[_Co] "
        sqlstring = sqlstring & ",[_pol] "
        sqlstring = sqlstring & ",[_Cov] "
        sqlstring = sqlstring & ",[_CessSeq] "
        sqlstring = sqlstring & ",[_TransSeq] "
        sqlstring = sqlstring & ",[_ReinsCo] "
        sqlstring = sqlstring & ",[_RepCo] "
        sqlstring = sqlstring & ",[_TranTyp] "
        sqlstring = sqlstring & ",[_FromDt] "
        sqlstring = sqlstring & ",[_ToDt] "
        sqlstring = sqlstring & ",[_RepDt] "
        sqlstring = sqlstring & ",[_Mode] "
        sqlstring = sqlstring & ",[_PolStatus] "
        sqlstring = sqlstring & ",[_Treaty] "
        sqlstring = sqlstring & ",[_TreatyRef] "
        sqlstring = sqlstring & ",[_ReinsTyp] "
        sqlstring = sqlstring & ",[_Plan] "
        sqlstring = sqlstring & ",[_SrchPlan] "
        sqlstring = sqlstring & ",[_ProdCD] "
        sqlstring = sqlstring & ",[_Face] "
        sqlstring = sqlstring & ",[_Retn] "
        sqlstring = sqlstring & ",[_Ceded] "
        sqlstring = sqlstring & ",[_NAR] "
        sqlstring = sqlstring & ",[_CstCntr] "
        sqlstring = sqlstring & ",[_LOB] "
    sqlstring = sqlstring & "FROM [TAICession] "
    sqlstring = sqlstring & "WHERE "
        sqlstring = sqlstring & "1 = 1 "
        sqlstring = sqlstring & "AND ([_pol] Like  '%" & PolicyNumber & "%') "
        sqlstring = sqlstring & "AND ([_MonthEnd] = '" & ValDate & "' ) "
        'sqlstring = sqlstring & "AND ([_ReinsCo] <> 'AN' ) "
    
    Debug.Print sqlstring
    
    dataArray = FetchTable(sqlstring, "UL_Rates", True)
    TAI_Quick_Policy_Data = dataArray

End Function

