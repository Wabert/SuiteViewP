VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "cls_PolicyInformation"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
'===============================================================================================
' cls_PolicyInformation - Self-Contained Policy Data Access Module
'===============================================================================================
' PURPOSE:      Single, robust module for accessing DB2 policy record data.
'               Designed for use by multiple applications (SuiteView, ABR Quote, etc.)
'
' USAGE:
'   Dim pol As New cls_PolicyInformation
'   If pol.Add("1234567", "01", "I", "CKPR") Then
'       Debug.Print pol.CovPlancode(1)           ' High-level property
'       Debug.Print pol.DataItem("LH_BAS_POL", "SUS_CD")  ' Direct DB2 access
'   End If
'
' PUBLIC API:
'   - Add(Policynumber, [CompanyCode], [SystemCode], [Region]) - Load a policy
'   - SetRates(oRates As cls_Rates) - Inject rates object for rate lookups
'   - DataItem(Table, Field, [Index]) - Get single value from DB2 table
'   - DataItemArray(Table, Field) - Get all values for a field as 1-based array
'   - DataItemCount(Table, Field) - Get count of records for a table/field
'   - FetchTable(SQL, DataSource) - Execute raw SQL and return 2D array
'   - Index [Get/Let] - Switch between cached policies (1-based)
'   - Count - Number of cached policies
'   - Cancelled - True if connection problems occurred
'   - LastErrorMessage - Description of last error
'
' CHANGE LOG:
'   01/30/2026 RJH: Refactored into single self-contained module with explicit error handling
'                   Added SetRates() method, LastErrorMessage property
'                   Organized sections: Core API, Policy Properties, Translations, Utilities
'===============================================================================================
Option Explicit

'===============================================================================================
' SECTION 1: PRIVATE VARIABLES & CONSTANTS
'===============================================================================================
Private dctPolicies As Dictionary       ' Cache of loaded policies (keyed by policy+company+sys+region)
Private mCurrentPolicy As Dictionary    ' Reference to currently active policy
Private mCurrentKey As String           ' Key of current policy in dctPolicies
Private dctODBC As Dictionary           ' Connection pool by region
Private mRates As cls_Rates             ' Optional rates object for rate lookups
Private mblnConnectionProblems As Boolean
Private mLastErrorMessage As String

' ODBC DSN names by region
Private Const DSN_CKPR = "NEON_DSN"     ' Production
Private Const DSN_CKMO = "NEON_DSNM"    ' Model Office
Private Const DSN_CKAS = "NEON_DSNT"    ' Acceptance/Staging
Private Const DSN_CKCS = "NEON_DSNT"    ' Cybertek/Test

'===============================================================================================
' SECTION 2: CLASS LIFECYCLE
'===============================================================================================
Private Sub Class_Initialize()
    Set dctPolicies = New Dictionary
    Set mCurrentPolicy = New Dictionary
    Set dctODBC = New Dictionary
    mblnConnectionProblems = False
    mLastErrorMessage = ""
End Sub

Private Sub Class_Terminate()
    ' Clean up ODBC connections
    Dim key As Variant
    For Each key In dctODBC.Keys
        On Error Resume Next
        dctODBC(key).Close
        On Error GoTo 0
    Next
    Set dctODBC = Nothing
    Set dctPolicies = Nothing
    Set mCurrentPolicy = Nothing
    Set mRates = Nothing
End Sub

'===============================================================================================
' SECTION 3: CORE PUBLIC API
'===============================================================================================

'-----------------------------------------------------------------------------------------------
' Add - Load a policy into the cache and make it the current policy
' Returns: True if policy was found and loaded successfully
'-----------------------------------------------------------------------------------------------
Public Function Add(sPolicynumber As String, _
                    Optional sCompanyCode As Variant, _
                    Optional sSystemCode As String = "I", _
                    Optional sRegion As String = "CKPR") As Boolean
    
    mblnConnectionProblems = False
    mLastErrorMessage = ""
    
    Add = FindAndAddPolicy(sPolicynumber, sCompanyCode, sSystemCode, sRegion)
End Function

'-----------------------------------------------------------------------------------------------
' SetRates - Inject rates object for rate lookups
'-----------------------------------------------------------------------------------------------
Public Sub SetRates(oRates As cls_Rates)
    Set mRates = oRates
End Sub

'-----------------------------------------------------------------------------------------------
' Cancelled - True if there were connection or query problems
'-----------------------------------------------------------------------------------------------
Public Property Get Cancelled() As Boolean
    Cancelled = mblnConnectionProblems
End Property

'-----------------------------------------------------------------------------------------------
' LastErrorMessage - Description of last error that occurred
'-----------------------------------------------------------------------------------------------
Public Property Get LastErrorMessage() As String
    LastErrorMessage = mLastErrorMessage
End Property

'-----------------------------------------------------------------------------------------------
' Index - Get/Set current policy index (1-based) for multi-policy scenarios
'-----------------------------------------------------------------------------------------------
Public Property Get Index() As Integer
    If dctPolicies.Count = 0 Then Exit Property
    Index = FindIndex(dctPolicies.Keys, mCurrentKey) + 1
End Property

Public Property Let Index(x As Integer)
    Dim KeysArrayIndex As Integer
    KeysArrayIndex = x - 1
    If KeysArrayIndex < LBound(dctPolicies.Keys) Or KeysArrayIndex > UBound(dctPolicies.Keys) Then
        mLastErrorMessage = "Index out of bounds: " & x
    Else
        mCurrentKey = dctPolicies.Keys(KeysArrayIndex)
        Set mCurrentPolicy = dctPolicies(mCurrentKey)
    End If
End Property

'-----------------------------------------------------------------------------------------------
' Count - Number of policies in cache
'-----------------------------------------------------------------------------------------------
Public Property Get Count() As Integer
    Count = dctPolicies.Count
End Property

'-----------------------------------------------------------------------------------------------
' Core identification properties
'-----------------------------------------------------------------------------------------------
Public Property Get Policynumber() As Variant
    If mCurrentPolicy.Exists("Source") Then Policynumber = mCurrentPolicy("Source")("Policynumber")
End Property

Public Property Get PolicyID() As Variant
    If mCurrentPolicy.Exists("Source") Then PolicyID = mCurrentPolicy("Source")("PolicyID")
End Property

Public Property Get Region() As Variant
    If mCurrentPolicy.Exists("Source") Then Region = mCurrentPolicy("Source")("Region")
End Property

Public Property Get CompanyCode() As Variant
    If mCurrentPolicy.Exists("Source") Then CompanyCode = mCurrentPolicy("Source")("CompanyCode")
End Property

Public Property Get SystemCode() As Variant
    If mCurrentPolicy.Exists("Source") Then SystemCode = mCurrentPolicy("Source")("SystemCode")
End Property

'===============================================================================================
' SECTION 4: DIRECT DB2 DATA ACCESS API
'===============================================================================================

'-----------------------------------------------------------------------------------------------
' DataItem - Get a single value from a DB2 table field
' Parameters:
'   sTable - DB2 table name (e.g., "LH_BAS_POL", "LH_COV_PHA")
'   sField - Field name (e.g., "SUS_CD", "COV_UNT_QTY")
'   index  - 1-based row index (default 1)
' Returns: Value or Empty if not found
'-----------------------------------------------------------------------------------------------
Public Function DataItem(sTable As String, sField As String, Optional Index As Integer = 1) As Variant
    Dim aryValues As Variant
    aryValues = DataItemArray(sTable, sField)
    
    If IsEmpty(aryValues) Then
        DataItem = Empty
    ElseIf Index < LBound(aryValues) Or Index > UBound(aryValues) Then
        DataItem = Empty
    ElseIf IsNull(aryValues(Index)) Then
        DataItem = Empty
    Else
        DataItem = aryValues(Index)
    End If
End Function

'-----------------------------------------------------------------------------------------------
' DataItemArray - Get all values for a field as a 1-based array
' Returns: 1-based Variant array or Empty if table/field not found
'-----------------------------------------------------------------------------------------------
Public Function DataItemArray(sTable As String, sField As String) As Variant
    If mCurrentPolicy Is Nothing Then
        DataItemArray = Empty
        Exit Function
    End If
    
    If Not mCurrentPolicy.Exists("Tables") Then
        DataItemArray = Empty
        Exit Function
    End If
    
    ' Load table if not already cached
    If Not mCurrentPolicy("Tables").Exists(sTable) Then LoadDB2Table sTable
    
    ' Check if table loaded successfully
    If IsEmpty(mCurrentPolicy("Tables")(sTable)) Then
        DataItemArray = Empty
        Exit Function
    End If
    
    ' Return field data
    If mCurrentPolicy("Tables")(sTable).Exists(sField) Then
        DataItemArray = mCurrentPolicy("Tables")(sTable)(sField)
    Else
        DataItemArray = Empty
    End If
End Function

'-----------------------------------------------------------------------------------------------
' DataItemCount - Get count of records for a table/field
' Returns: Integer count (0 if not found)
'-----------------------------------------------------------------------------------------------
Public Function DataItemCount(sTable As String, sField As String) As Integer
    Dim aryValues As Variant
    aryValues = DataItemArray(sTable, sField)
    
    If IsEmpty(aryValues) Then
        DataItemCount = 0
    Else
        DataItemCount = UBound(aryValues) - LBound(aryValues) + 1
    End If
End Function

'-----------------------------------------------------------------------------------------------
' FetchTable - Execute raw SQL and return results as 2D array (field names in row 0)
' Parameters:
'   QueryStatements - SQL query string
'   DataSource - Region code (CKPR, CKMO, CKAS, CKCS)
' Returns: 2D Variant array with field names in first row, or Empty on error
'-----------------------------------------------------------------------------------------------
Public Function FetchTable(QueryStatements As String, DataSource As String) As Variant
    On Error GoTo ErrorHandler
    
    Dim DataSet As ADODB.Recordset
    Set DataSet = New ADODB.Recordset
    
    ' Office 365 workaround - queries need WITH clause
    If Left(QueryStatements, 4) <> "WITH" Then
        QueryStatements = "WITH DUMBY AS (SELECT 1 FROM DB2TAB.LH_COV_PHA) " & QueryStatements
    End If
    
    Dim cn As ADODB.Connection
    Set cn = GetConnection(DataSource)
    
    If cn Is Nothing Then
        FetchTable = Empty
        Exit Function
    End If
    
    DataSet.Open QueryStatements, cn
    DataSet.MoveFirst
    
    ' Get recordset data into array
    Dim DataArray As Variant
    DataArray = DataSet.GetRows
    DataArray = Transpose2DArray(DataArray)
    
    ' Build array of field names
    Dim dctFlds As Dictionary
    Dim fld As Variant
    Set dctFlds = New Dictionary
    For Each fld In DataSet.Fields
        dctFlds.Add fld.Name, fld.Name
    Next
    
    ' Insert field names as first row
    Call InsertRowIntoArray(DataArray, LBound(DataArray), dctFlds.Keys)
    
    FetchTable = DataArray
    DataSet.Close
    Set DataSet = Nothing
    Exit Function
    
ErrorHandler:
    mLastErrorMessage = "FetchTable error: " & Err.Description
    Set DataSet = Nothing
    FetchTable = Empty
End Function

'===============================================================================================
' SECTION 5: PRIVATE DATA ACCESS METHODS
'===============================================================================================

Private Function FindAndAddPolicy(sPolicynumber As String, sCompanyCode As Variant, _
                                   sSystemCode As String, sRegion As String) As Boolean
    
    Dim PolicyList As Variant
    PolicyList = QueryPolicy(sPolicynumber, sRegion, sCompanyCode, sSystemCode)
    
    ' Check for connection problems
    If mblnConnectionProblems Then
        FindAndAddPolicy = False
        mLastErrorMessage = "Problems connecting to DB2 database"
        Exit Function
    End If
    
    ' Check if policy found
    If IsEmpty(PolicyList) Then
        If Not IsMissing(sCompanyCode) And sCompanyCode <> "" Then
            mLastErrorMessage = "Cannot find policy " & sPolicynumber & " in " & sRegion & " for Company " & sCompanyCode
        Else
            mLastErrorMessage = "Cannot find policy " & sPolicynumber & " in " & sRegion
        End If
        FindAndAddPolicy = False
        Exit Function
    End If
    
    ' Handle multiple company codes
    If UBound(PolicyList) > 1 Then
        Dim AvailableCompanyCodes As String
        AvailableCompanyCodes = PolicyList(1, 0)
        
        Dim x As Integer
        For x = 2 To UBound(PolicyList)
            AvailableCompanyCodes = AvailableCompanyCodes & ", " & PolicyList(x, 0)
        Next
        
        sCompanyCode = Format(InputBox("Need to specify company code for policy " & sPolicynumber & _
                                        ". Company codes available are " & AvailableCompanyCodes), "00")
        
        PolicyList = QueryPolicy(sPolicynumber, sRegion, sCompanyCode, sSystemCode)
        
        If UBound(PolicyList) <> 1 Then
            mLastErrorMessage = "Invalid company code selected"
            FindAndAddPolicy = False
            Exit Function
        End If
    End If
    
    ' Add policy to cache
    FindAndAddPolicy = True
    
    Dim sPolicyID As String
    sPolicyID = PolicyList(1, 3)
    sCompanyCode = PolicyList(1, 0)
    
    Dim key As String
    key = MakePolicyKey(sPolicynumber, CStr(sCompanyCode), sSystemCode, sRegion)
    
    If Not dctPolicies.Exists(key) Then
        Dim dct As Dictionary
        Set dct = New Dictionary
        dctPolicies.Add key, dct
        
        ' Source info
        Set dct = New Dictionary
        dct.Add "Policynumber", sPolicynumber
        dct.Add "CompanyCode", sCompanyCode
        dct.Add "PolicyID", sPolicyID
        dct.Add "SystemCode", sSystemCode
        dct.Add "Region", sRegion
        dctPolicies(key).Add "Source", dct
        
        ' Tables cache
        Set dct = New Dictionary
        dctPolicies(key).Add "Tables", dct
        
        ' Lazy-loaded caches
        dctPolicies(key).Add "CommTargets", Nothing
        dctPolicies(key).Add "FundAllocations", Nothing
        dctPolicies(key).Add "FundValues", Nothing
        dctPolicies(key).Add "BaseIndices", Nothing
        dctPolicies(key).Add "RiderIndices", Nothing
    End If
    
    Set mCurrentPolicy = dctPolicies(key)
    mCurrentKey = key
End Function

Private Function QueryPolicy(sPolicynumber As String, sRegion As String, _
                              Optional sCompanyCode As Variant, _
                              Optional sSystemCode As String = "I") As Variant
    
    Dim aryWhereClause As Variant
    If IsMissing(sCompanyCode) Or sCompanyCode = "" Then
        aryWhereClause = Array("CK_SYS_CD='" & sSystemCode & "' ", "CK_POLICY_NBR='" & sPolicynumber & "' ")
    Else
        aryWhereClause = Array("CK_SYS_CD='" & sSystemCode & "' ", "CK_POLICY_NBR='" & sPolicynumber & "' ", _
                               "CK_CMP_CD='" & sCompanyCode & "' ")
    End If
    
    Dim SQLString As String
    SQLString = "SELECT CK_CMP_CD, CK_POLICY_NBR, CK_SYS_CD, TCH_POL_ID FROM DB2TAB.LH_BAS_POL WHERE " & _
                Join(aryWhereClause, " AND ")
    SQLString = SQLStringForRegion(SQLString, sRegion)
    
    QueryPolicy = FetchTable(SQLString, sRegion)
End Function

Private Function MakePolicyKey(sPolicynumber As String, sCompanyCode As String, _
                                sSystemCode As String, sRegion As String) As String
    MakePolicyKey = UCase(Application.WorksheetFunction.Trim(sPolicynumber)) & "_" & _
                    sCompanyCode & "_" & sSystemCode & "_" & sRegion
End Function

Private Sub LoadDB2Table(Tablename As String)
    Dim Source As Dictionary
    Dim aryTable As Variant
    Dim aryWhereClause As Variant
    Dim aryOrderClause As Variant
    
    Set Source = mCurrentPolicy("Source")
    
    ' Default WHERE clause for most tables
    aryWhereClause = Array("CK_SYS_CD='" & Source("SystemCode") & "' ", _
                           "TCH_POL_ID='" & Source("PolicyID") & "' ", _
                           "CK_CMP_CD='" & Source("CompanyCode") & "' ")
    
    ' Table-specific query configurations
    Select Case Tablename
        Case "LH_BAS_POL", "TH_BAS_POL", "LH_FXD_PRM_POL", "LH_TRD_POL"
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
        
        Case "LH_COV_PHA", "LH_NEW_BUS_COV_PHA", "TH_COV_PHA"
            aryOrderClause = Array("COV_PHA_NBR")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_SPM_BNF", "TH_SPM_BNF", "LH_SST_XTR_CRG", "TH_SST_XTR_CRG"
            aryOrderClause = Array("COV_PHA_NBR")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_COV_INS_RNL_RT"
            aryOrderClause = Array("COV_PHA_NBR")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "TH_COV_INS_RNL_RT"
            aryOrderClause = Array("COV_PHA_NBR", "PRS_CD", "PRS_SEQ_NBR", "SEG_IDX_NBR")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_BNF_INS_RNL_RT", "LH_SST_XTR_RNL_RT"
            aryOrderClause = Array("COV_PHA_NBR")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_COM_TARGET"
            aryOrderClause = Array("AGT_COM_PHA_NBR")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_COV_TARGET"
            aryOrderClause = Array("COV_PHA_NBR")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_POL_TARGET", "LH_POL_TOTALS", "LH_POL_YR_TOT", "LH_POL_CAL_YR_TOT"
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
        
        Case "LH_COV_INS_GDL_PRM", "LH_BNF_INS_GDL_PRM"
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
        
        Case "LH_POL_MVRY_VAL"
            aryOrderClause = Array("MVRY_DT DESC")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_POL_FND_VAL_TOT"
            aryOrderClause = Array("MVRY_DT DESC", "FND_ID_CD DESC", "FND_VAL_PHA_NBR DESC")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_FND_VAL_LOAN"
            aryOrderClause = Array("MVRY_DT DESC", "FND_VAL_PHA_NBR DESC")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_CSH_VAL_LOAN"
            aryOrderClause = Array("MVRY_DT DESC")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_NON_TRD_POL", "TH_NON_TRD_POL"
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
        
        Case "LH_FND_ALC", "LH_FND_TRS_ALC_SET"
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
        
        Case "LH_CTT_COM_PHA_WA"
            aryOrderClause = Array("AGT_ITS_EFF_DT DESC")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "VH_POL_HAS_LOC_CLT", "LH_CTT_CLIENT", "LH_LOC_CLT_ADR"
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
        
        Case "LH_TAMRA_7_PY_PER", "LH_TAMRA_7_PY_YR", "LH_TAMRA_MEC_PRM"
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
        
        Case "LH_LN_RPY_TRM"
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
        
        Case "LH_COV_SKIPPED_PER"
            aryOrderClause = Array("COV_PHA_NBR", "LAP_DT")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "FH_FIXED"
            aryWhereClause = Array("TCH_POL_ID='" & Source("PolicyID") & "' ", _
                                   "CK_CMP_CD='" & Source("CompanyCode") & "' ")
            aryOrderClause = Array("ASOF_DT DESC")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_UNAPPLIED_PTP", "LH_APPLIED_PTP"
            aryOrderClause = Array("ERN_DT_MO_YR_NBR DESC")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "LH_PAID_UP_ADD", "LH_ONE_YR_TRM_ADD", "LH_PTP_ON_DEP"
            aryOrderClause = Array("MVRY_DT DESC")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
        Case "TH_USER_GENERIC"
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
        
        Case Else
            ' Generic fallback - try with PolicyID and CompanyCode only
            aryWhereClause = Array("TCH_POL_ID='" & Source("PolicyID") & "' ", _
                                   "CK_CMP_CD='" & Source("CompanyCode") & "' ")
            aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
    End Select
    
    ' Store results
    If IsEmpty(aryTable) Then
        mCurrentPolicy("Tables").Add Tablename, Empty
    ElseIf UBound(aryTable, 1) = 0 Then
        mCurrentPolicy("Tables").Add Tablename, Empty
    Else
        Dim dct As Dictionary
        Set dct = New Dictionary
        mCurrentPolicy("Tables").Add Tablename, dct
        LoadFieldData mCurrentPolicy("Tables")(Tablename), aryTable
    End If
End Sub

Private Sub LoadFieldData(dctTable As Dictionary, aryData As Variant)
    Dim RowLB As Integer, RowUB As Integer, ColLB As Integer, ColUB As Integer
    
    RowLB = LBound(aryData, 1)
    RowUB = UBound(aryData, 1)
    ColLB = LBound(aryData, 2)
    ColUB = UBound(aryData, 2)
    
    Dim col As Integer, row As Integer
    Dim FieldName As String
    
    If RowLB = RowUB Then
        ' No data rows, only headers
        For col = ColLB To ColUB
            FieldName = aryData(0, col)
            dctTable.Add FieldName, Empty
        Next
    Else
        ' Convert columns to 1-based vectors
        Dim Vector As Variant
        For col = ColLB To ColUB
            FieldName = aryData(0, col)
            ReDim Vector(1 To RowUB)
            For row = 1 To RowUB
                Vector(row) = aryData(row, col)
            Next
            dctTable.Add FieldName, Vector
        Next
    End If
End Sub

Private Function GetTableFromDB2(sTableName As String, aryWhereClause As Variant, _
                                  Optional aryOrderClause As Variant, _
                                  Optional sRegion As String = "CKPR") As Variant
    
    Dim SQLString As String
    SQLString = "SELECT * FROM DB2TAB." & sTableName
    SQLString = SQLString & " WHERE " & Join(aryWhereClause, " AND ")
    If Not IsMissing(aryOrderClause) Then
        SQLString = SQLString & " ORDER BY " & Join(aryOrderClause, ", ")
    End If
    
    SQLString = SQLStringForRegion(SQLString, sRegion)
    GetTableFromDB2 = FetchTable(SQLString, sRegion)
End Function

Private Function SQLStringForRegion(SQLString As String, DB2_Source As String) As String
    Select Case DB2_Source
        Case "CKAS": SQLStringForRegion = Replace(SQLString, "DB2TAB.", "UNIT.", , , vbTextCompare)
        Case "CKCS": SQLStringForRegion = Replace(SQLString, "DB2TAB.", "CYBERTEK.", , , vbTextCompare)
        Case Else: SQLStringForRegion = SQLString
    End Select
End Function

'===============================================================================================
' SECTION 6: ODBC CONNECTION MANAGEMENT
'===============================================================================================

Private Function GetConnection(sRegion As String) As ADODB.Connection
    If dctODBC.Exists(sRegion) Then
        Set GetConnection = dctODBC(sRegion)
        Exit Function
    End If
    
    Dim cn As ADODB.Connection
    Set cn = New ADODB.Connection
    cn.ConnectionString = GetConnectionString(sRegion)
    
    On Error Resume Next
    cn.Open
    
    Dim TryCount As Integer
    Do While Err.Number <> 0
        Err.Clear
        
        ' Show login form
        Dim frm As frmLogin
        Dim PWD As String
        Dim UserID As String
        Dim dctData As Dictionary
        
        Set frm = New frmLogin
        Set dctData = New Dictionary
        Set frm.DataDictionary = dctData
        frm.StartUpPosition = 0
        frm.Left = 300
        frm.Top = 200
        frm.Show vbModal
        
        UserID = dctData("UserID")
        PWD = dctData("PWD")
        
        If PWD = "" Then
            mblnConnectionProblems = True
            mLastErrorMessage = "Login cancelled"
            Set GetConnection = Nothing
            Exit Function
        End If
        
        Set cn = New ADODB.Connection
        cn.Open GetConnectionString(sRegion), UserID, PWD
        
        TryCount = TryCount + 1
        If TryCount > 2 Then
            mblnConnectionProblems = True
            mLastErrorMessage = "Connection failed after " & TryCount & " attempts"
            Set GetConnection = Nothing
            Exit Function
        End If
    Loop
    
    On Error GoTo 0
    
    dctODBC.Add sRegion, cn
    Set GetConnection = cn
End Function

Private Function GetConnectionString(strDataSource As String) As String
    Select Case strDataSource
        Case "CKPR": GetConnectionString = "Data Source=" & DSN_CKPR
        Case "CKMO": GetConnectionString = "Data Source=" & DSN_CKMO
        Case "CKAS": GetConnectionString = "Data Source=" & DSN_CKAS
        Case "CKCS": GetConnectionString = "Data Source=" & DSN_CKCS
        Case Else: GetConnectionString = "Data Source=" & DSN_CKPR
    End Select
End Function

'===============================================================================================
' SECTION 7: POLICY PROPERTIES - Classification & Status
'===============================================================================================

Public Property Get AdvancedProductIndicator() As Variant
    AdvancedProductIndicator = DataItem("LH_BAS_POL", "NON_TRD_POL_IND")
End Property

Public Property Get IsAdvancedProduct() As Boolean
    IsAdvancedProduct = (AdvancedProductIndicator = "1")
End Property

Public Property Get ProductType() As String
    Dim tempValue As String
    If ProductIndicator = "X" Then
        tempValue = "IUL"
    Else
        tempValue = "Non UL"
        If CovProductLineCode(1) = "U" Then tempValue = "UL"
        If CovProductLineCode(1) = "I" Then tempValue = "ISWL"
        If CovValuationClass(1) = "1" Then tempValue = "WL"
        If CovValuationClass(1) = "5" Or CovValuationClass(1) = "8" Then tempValue = "TERM"
    End If
    ProductType = tempValue
End Property

Public Property Get ProductLineCode() As Variant
    ProductLineCode = DataItem("LH_COV_PHA", "PRD_LIN_TYP_CD")
End Property

Public Property Get ProductIndicator() As Variant
    ProductIndicator = DataItem("TH_COV_PHA", "AN_PRD_ID")
End Property

Public Property Get StatusCode() As Variant
    StatusCode = DataItem("LH_BAS_POL", "PRM_PAY_STA_REA_CD")
End Property

Public Property Get StatusText() As Variant
    StatusText = TranslateStatusCodeToText(CStr(Me.StatusCode))
End Property

Public Property Get IsTerminated() As Boolean
    IsTerminated = (Left(CStr(StatusCode), 1) = "9")
End Property

Public Property Get IsPaidUp() As Boolean
    IsPaidUp = (Left(CStr(StatusCode), 1) = "4")
End Property

Public Property Get IsPremiumPaying() As Boolean
    IsPremiumPaying = (Left(CStr(StatusCode), 1) = "2")
End Property

Public Property Get SuspenseCode() As Variant
    SuspenseCode = DataItem("LH_BAS_POL", "SUS_CD")
End Property

Public Property Get SuspenseText() As Variant
    SuspenseText = TranslateSuspenseCodeToText(CStr(Me.SuspenseCode))
End Property

'===============================================================================================
' SECTION 8: POLICY PROPERTIES - Dates
'===============================================================================================

Public Property Get ValuationDate() As Variant
    If Me.ProductLineCode = "U" Or Me.ProductLineCode = "I" Then
        If Me.MVCount = 0 Then
            ValuationDate = Empty
        Else
            ValuationDate = Me.MVDate
        End If
        Exit Property
    End If
    
    If IsEmpty(Me.NextMonthliversary) Or Me.NextMonthliversary = 0 Then
        ValuationDate = Me.LastFinancialDate
    Else
        ValuationDate = DateAdd("m", -1, Me.NextMonthliversary)
    End If
End Property

Public Property Get LastAnniversary() As Variant
    LastAnniversary = DataItem("LH_BAS_POL", "LST_ANV_DT")
End Property

Public Property Get NextMonthliversary() As Variant
    NextMonthliversary = DataItem("LH_BAS_POL", "NXT_MVRY_PRC_DT")
End Property

Public Property Get LastFinancialDate() As Variant
    LastFinancialDate = DataItem("LH_BAS_POL", "LST_FIN_DT")
End Property

Public Property Get NextBillDate() As Variant
    NextBillDate = DataItem("LH_BAS_POL", "NXT_BIL_DT")
End Property

Public Property Get PremiumDatePaidTo() As Variant
    PremiumDatePaidTo = DataItem("LH_BAS_POL", "PRM_BILL_TO_DT")
End Property

Public Property Get PolicyYear() As Variant
    If IsEmpty(ValuationDate) Then Exit Property
    PolicyYear = CompletedDateParts("YYYY", CovIssueDate(1), Me.ValuationDate) + 1
End Property

'===============================================================================================
' SECTION 9: POLICY PROPERTIES - Company & Location
'===============================================================================================

Public Property Get Company() As Variant
    Company = TranslateCompanyCodeToText(CStr(Me.CompanyCode))
End Property

Public Property Get IssueStateCode() As Variant
    IssueStateCode = DataItem("LH_BAS_POL", "POL_ISS_ST_CD")
End Property

Public Property Get IssueStateAbbr() As Variant
    If IsEmpty(IssueStateCode) Then Exit Property
    IssueStateAbbr = TranslateStateCodeToAbbr(CInt(Me.IssueStateCode))
End Property

Public Property Get ResidentStateCode() As Variant
    ResidentStateCode = DataItem("LH_BAS_POL", "PRM_PAY_ST_CD")
End Property

Public Property Get ResidentStateAbbr() As Variant
    If IsEmpty(ResidentStateCode) Then Exit Property
    ResidentStateAbbr = TranslateStateCodeToAbbr(CInt(Me.ResidentStateCode))
End Property

Public Property Get ServicingMarketOrganization() As Variant
    ServicingMarketOrganization = DetermineMarketOrg(CStr(Me.CompanyCode), Left(CStr(Me.ServicingBranchOrAgencyCode), 1))
End Property

Public Property Get ServicingBranchOrAgencyCode() As Variant
    ServicingBranchOrAgencyCode = DataItem("LH_BAS_POL", "SVC_AGC_NBR")
End Property

Public Property Get ServicingAgentNumber() As Variant
    ServicingAgentNumber = DataItem("LH_BAS_POL", "SVC_AGT_NBR")
End Property

Public Property Get AgencyBranchCode() As Variant
    AgencyBranchCode = Mid(CStr(Me.ServicingBranchOrAgencyCode), 2, 4)
End Property

Public Property Get IsFFS() As Boolean
    IsFFS = (ServicingMarketOrganization = "IMG" And AgencyBranchCode = "0B4Q")
End Property

'===============================================================================================
' SECTION 10: POLICY PROPERTIES - Billing
'===============================================================================================

Public Property Get BillMode() As Variant
    BillMode = TranslateBillModeCodeToText(CStr(Me.BillModeCode))
End Property

Public Property Get BillModeCode() As Variant
    BillModeCode = DataItem("LH_BAS_POL", "PMT_FQY_PER")
End Property

Public Property Get BillPremium() As Variant
    BillPremium = DataItem("LH_BAS_POL", "POL_PRM_AMT")
End Property

Public Property Get BillFormCode() As Variant
    BillFormCode = DataItem("LH_BAS_POL", "BIL_FRM_CD")
End Property

Public Property Get NonStandardModeCode() As Variant
    NonStandardModeCode = DataItem("LH_BAS_POL", "NSD_MD_CD")
End Property

'===============================================================================================
' SECTION 11: COVERAGE PROPERTIES
'===============================================================================================

Public Property Get CovCount() As Integer
    CovCount = DataItemCount("LH_COV_PHA", "COV_PHA_NBR")
End Property

Public Property Get CovBaseCount() As Integer
    Dim x As Integer, cnt As Integer
    For x = 1 To CovCount
        If CovPlancode(x) = CovPlancode(1) Then cnt = cnt + 1
    Next
    CovBaseCount = cnt
End Property

Public Property Get CovRiderCount() As Integer
    CovRiderCount = CovCount - CovBaseCount
End Property

Public Property Get CovPlancode(Cov As Integer) As Variant
    CovPlancode = Application.WorksheetFunction.Trim(DataItem("LH_COV_PHA", "PLN_DES_SER_CD", Cov))
End Property

Public Property Get CovFormNumber(Cov As Integer) As Variant
    CovFormNumber = DataItem("LH_COV_PHA", "POL_FRM_NBR", Cov)
End Property

Public Property Get CovPhase(Cov As Integer) As Variant
    CovPhase = DataItem("LH_COV_PHA", "COV_PHA_NBR", Cov)
End Property

Public Property Get CovIssueDate(Cov As Integer) As Variant
    CovIssueDate = DataItem("LH_COV_PHA", "ISSUE_DT", Cov)
End Property

Public Property Get CovMaturityDate(Cov As Integer) As Variant
    CovMaturityDate = DataItem("LH_COV_PHA", "COV_MT_EXP_DT", Cov)
End Property

Public Property Get CovIssueAge(Cov As Integer, Optional JtIndicator As Integer = 0) As Variant
    If JtIndicator = 0 Then
        CovIssueAge = DataItem("LH_COV_PHA", "INS_ISS_AGE", Cov)
    Else
        CovIssueAge = DataItem("LH_COV_PHA", "JNT_ISU_ISS_AGE", Cov)
    End If
End Property

Public Property Get CovUnits(Cov As Integer) As Variant
    CovUnits = DataItem("LH_COV_PHA", "COV_UNT_QTY", Cov)
End Property

Public Property Get CovVPU(Cov As Integer) As Variant
    CovVPU = DataItem("LH_COV_PHA", "COV_VPU_AMT", Cov)
End Property

Public Property Get CovAmount(Cov As Integer) As Variant
    CovAmount = CovUnits(Cov) * CovVPU(Cov)
End Property

Public Property Get CovOrigAmount(Cov As Integer) As Variant
    Dim origUnits As Variant
    origUnits = DataItem("LH_COV_PHA", "OGN_SPC_UNT_QTY", Cov)
    CovOrigAmount = IfEmpty(origUnits, 0) * CovVPU(Cov)
End Property

Public Property Get CovStatus(Cov As Integer) As Variant
    ' 0 = Terminated/Expired, 1 = Paid-Up, 2 = Premium Paying
    CovStatus = DataItem("LH_COV_PHA", "NXT_CHG_TYP_CD", Cov)
End Property

Public Property Get CovIsBase(Cov As Integer) As Boolean
    CovIsBase = (CovPlancode(Cov) = CovPlancode(1))
End Property

Public Property Get CovValuationClass(Cov As Integer) As Variant
    CovValuationClass = DataItem("LH_COV_PHA", "INS_CLS_CD", Cov)
End Property

Public Property Get CovProductLineCode(Cov As Integer) As Variant
    CovProductLineCode = DataItem("LH_COV_PHA", "PRD_LIN_TYP_CD", Cov)
End Property

Public Property Get CovPersonCode(Cov As Integer) As Variant
    CovPersonCode = DataItem("LH_COV_PHA", "PRS_CD", Cov)
End Property

Public Property Get CovPersonSequenceCode(Cov As Integer) As Variant
    CovPersonSequenceCode = DataItem("LH_COV_PHA", "PRS_SEQ_NBR", Cov)
End Property

Public Property Get CovRateclass(Cov As Integer, Optional JtIndicator As Integer = 0) As Variant
    CovRateclass = RenewalCovRateclass(Cov, "C", JtIndicator)
End Property

Public Property Get CovSex(Cov As Integer, Optional JtIndicator As Integer = 0) As Variant
    Dim tempSex As Variant
    tempSex = RenewalCovSexCode(Cov, "C", JtIndicator)
    Select Case tempSex
        Case "1": tempSex = "M"
        Case "2": tempSex = "F"
    End Select
    CovSex = tempSex
End Property

Public Property Get CovMortalityTableCode(Cov As Integer) As Variant
    CovMortalityTableCode = DataItem("LH_COV_PHA", "MTL_FCT_TBL_CD", Cov)
End Property

Public Property Get TotalSpecifiedAmount() As Variant
    Dim Cov As Integer, tempValue As Double
    For Cov = 1 To CovCount
        If CovPlancode(Cov) = CovPlancode(1) Then tempValue = tempValue + CovAmount(Cov)
    Next
    TotalSpecifiedAmount = tempValue
End Property

'===============================================================================================
' SECTION 12: RENEWAL RATE PROPERTIES
'===============================================================================================

Public Property Get RenewalCovCount() As Integer
    RenewalCovCount = DataItemCount("LH_COV_INS_RNL_RT", "COV_PHA_NBR")
End Property

Public Function CovRenewalIndex(Cov As Integer, Optional RtType As String = "C", Optional JtIndicator As Integer = 0) As Integer
    Dim idx As Integer, x As Integer
    idx = -1
    For x = 1 To RenewalCovCount
        If DataItem("LH_COV_INS_RNL_RT", "PRM_RT_TYP_CD", x) = RtType And _
           DataItem("LH_COV_INS_RNL_RT", "COV_PHA_NBR", x) = CovPhase(Cov) And _
           DataItem("LH_COV_INS_RNL_RT", "JT_INS_IND", x) = JtIndicator Then
            idx = x
        End If
    Next
    CovRenewalIndex = idx
End Function

Public Property Get RenewalCovRateclass(Optional Cov As Integer = 1, Optional RtType As String = "C", Optional JtIndicator As Integer = 0) As Variant
    Dim RtIndex As Integer
    RtIndex = CovRenewalIndex(Cov, RtType, JtIndicator)
    If RtIndex < 0 Then Exit Property
    RenewalCovRateclass = DataItem("LH_COV_INS_RNL_RT", "RT_CLS_CD", RtIndex)
End Property

Public Property Get RenewalCovSexCode(Optional Cov As Integer = 1, Optional RtType As String = "C", Optional JtIndicator As Integer = 0) As Variant
    Dim RtIndex As Integer
    RtIndex = CovRenewalIndex(Cov, RtType, JtIndicator)
    If RtIndex < 0 Then Exit Property
    RenewalCovSexCode = DataItem("LH_COV_INS_RNL_RT", "RT_SEX_CD", RtIndex)
End Property

Public Property Get RenewalCovBandCode(Optional Cov As Integer = 1, Optional RtType As String = "C") As Variant
    Dim RtIndex As Integer
    RtIndex = CovRenewalIndex(Cov, RtType)
    If RtIndex < 0 Then Exit Property
    RenewalCovBandCode = DataItem("LH_COV_INS_RNL_RT", "RT_BAN_CD", RtIndex)
End Property

'===============================================================================================
' SECTION 13: BENEFIT PROPERTIES
'===============================================================================================

Public Property Get BenCount() As Integer
    BenCount = DataItemCount("LH_SPM_BNF", "SPM_BNF_TYP_CD")
End Property

Public Property Get BenPlancode(BenefitIndex As Integer) As Variant
    BenPlancode = DataItem("LH_SPM_BNF", "SPM_BNF_TYP_CD", BenefitIndex) & _
                  DataItem("LH_SPM_BNF", "SPM_BNF_SBY_CD", BenefitIndex)
End Property

Public Property Get BenTypeCode(BenefitIndex As Integer) As Variant
    BenTypeCode = Left(CStr(BenPlancode(BenefitIndex)), 1)
End Property

Public Property Get BenSubTypeCode(BenefitIndex As Integer) As Variant
    BenSubTypeCode = Mid(CStr(BenPlancode(BenefitIndex)), 2, 1)
End Property

Public Property Get BenType(BenefitIndex As Integer) As Variant
    BenType = TranslateBenefitTypeToText(CStr(BenTypeCode(BenefitIndex)), CStr(BenSubTypeCode(BenefitIndex)))
End Property

Public Property Get BenAmount(BenefitIndex As Integer) As Variant
    BenAmount = BenUnits(BenefitIndex) * BenVPU(BenefitIndex)
End Property

Public Property Get BenUnits(BenefitIndex As Integer) As Variant
    BenUnits = DataItem("LH_SPM_BNF", "BNF_UNT_QTY", BenefitIndex)
End Property

Public Property Get BenVPU(BenefitIndex As Integer) As Variant
    BenVPU = DataItem("LH_SPM_BNF", "BNF_VPU_AMT", BenefitIndex)
End Property

Public Property Get BenIssueAge(BenefitIndex As Integer) As Variant
    BenIssueAge = DataItem("LH_SPM_BNF", "BNF_ISS_AGE", BenefitIndex)
End Property

Public Property Get BenIssueDate(BenefitIndex As Integer) As Variant
    BenIssueDate = DataItem("LH_SPM_BNF", "BNF_ISS_DT", BenefitIndex)
End Property

Public Property Get BenCeaseDate(BenefitIndex As Integer) As Variant
    BenCeaseDate = DataItem("LH_SPM_BNF", "BNF_CEA_DT", BenefitIndex)
End Property

Public Property Get BenFormNumber(BenefitIndex As Integer) As Variant
    BenFormNumber = DataItem("LH_SPM_BNF", "BNF_FRM_NBR", BenefitIndex)
End Property

Public Property Get BenCovPhase(BenefitIndex As Integer) As Variant
    BenCovPhase = DataItem("LH_SPM_BNF", "COV_PHA_NBR", BenefitIndex)
End Property

'===============================================================================================
' SECTION 14: FINANCIAL TARGETS (MTP, CTP, GLP, GSP)
'===============================================================================================

Public Property Get MTP() As Variant
    Dim x As Integer
    For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
        If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "MT" Then
            MTP = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
            Exit Property
        End If
    Next
End Property

Public Property Get CTP() As Variant
    CTP = ComTargetDictionary("CTP")
End Property

Public Property Get GLP() As Variant
    Dim x As Integer
    For x = 1 To DataItemCount("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD")
        If DataItem("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD", x) = "A" Then
            GLP = DataItem("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", x)
            Exit Property
        End If
    Next
End Property

Public Property Get GSP() As Variant
    Dim x As Integer
    For x = 1 To DataItemCount("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD")
        If DataItem("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD", x) = "S" Then
            GSP = DataItem("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", x)
            Exit Property
        End If
    Next
End Property

Public Property Get AccumGLP() As Variant
    Dim x As Integer
    For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
        If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "TA" Then
            AccumGLP = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
            Exit Property
        End If
    Next
End Property

Public Property Get AccumMTP() As Variant
    AccumMTP = 0
    Dim x As Integer
    For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
        If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "MA" Then
            AccumMTP = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
            Exit Property
        End If
    Next
End Property

Public Property Get PLT() As Variant
    Dim x As Integer
    For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
        If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "LT" Then
            PLT = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
            Exit Property
        End If
    Next
End Property

'===============================================================================================
' SECTION 15: FINANCIAL VALUES
'===============================================================================================

Public Property Get PremiumTD() As Variant
    PremiumTD = TotalRegularPremium + TotalAdditionalPremium
End Property

Public Property Get PremiumYTD() As Variant
    PremiumYTD = TotalRegularPremiumYTD + TotalAdditionalPremiumYTD
End Property

Public Property Get TotalRegularPremium() As Variant
    TotalRegularPremium = IfEmpty(DataItem("LH_POL_TOTALS", "TOT_REG_PRM_AMT", 1), 0)
End Property

Public Property Get TotalAdditionalPremium() As Variant
    TotalAdditionalPremium = IfEmpty(DataItem("LH_POL_TOTALS", "TOT_ADD_PRM_AMT", 1), 0)
End Property

Public Property Get TotalRegularPremiumYTD() As Variant
    Dim cnt As Integer
    cnt = DataItemCount("LH_POL_YR_TOT", "YTD_TOT_PMT_AMT")
    TotalRegularPremiumYTD = IfEmpty(DataItem("LH_POL_YR_TOT", "YTD_TOT_PMT_AMT", cnt), 0)
End Property

Public Property Get TotalAdditionalPremiumYTD() As Variant
    Dim cnt As Integer
    cnt = DataItemCount("LH_POL_YR_TOT", "YTD_ADD_PRM_AMT")
    TotalAdditionalPremiumYTD = IfEmpty(DataItem("LH_POL_YR_TOT", "YTD_ADD_PRM_AMT", cnt), 0)
End Property

Public Property Get CostBasis() As Variant
    CostBasis = IfEmpty(DataItem("LH_POL_TOTALS", "POL_CST_BSS_AMT", 1), 0)
End Property

Public Property Get AccumWithdrawals() As Variant
    AccumWithdrawals = IfEmpty(DataItem("LH_POL_TOTALS", "TOT_WTD_AMT", 1), 0)
End Property

'===============================================================================================
' SECTION 16: MONTHLIVERSARY VALUE PROPERTIES
'===============================================================================================

Public Property Get MVCount() As Integer
    MVCount = DataItemCount("LH_POL_MVRY_VAL", "MVRY_DT")
End Property

Public Property Get MVDate(Optional DtIndex As Integer = 1) As Variant
    MVDate = DataItem("LH_POL_MVRY_VAL", "MVRY_DT", DtIndex)
End Property

Public Property Get MVAV(Optional DtIndex As Integer = 1) As Variant
    MVAV = DataItem("LH_POL_MVRY_VAL", "CSV_AMT", DtIndex)
End Property

Public Property Get MVCOICharge(Optional DtIndex As Integer = 1) As Variant
    MVCOICharge = IfEmpty(DataItem("LH_POL_MVRY_VAL", "CINS_AMT", DtIndex), 0)
End Property

Public Property Get MVExpChrg(Optional DtIndex As Integer = 1) As Variant
    MVExpChrg = IfEmpty(DataItem("LH_POL_MVRY_VAL", "EXP_CRG_AMT", DtIndex), 0)
End Property

Public Property Get MVOtherChrg(Optional DtIndex As Integer = 1) As Variant
    MVOtherChrg = IfEmpty(DataItem("LH_POL_MVRY_VAL", "OTH_PRM_AMT", DtIndex), 0)
End Property

Public Property Get MVMonthlyDeduction(Optional DtIndex As Integer = 1) As Variant
    MVMonthlyDeduction = MVCOICharge(DtIndex) + MVExpChrg(DtIndex) + MVOtherChrg(DtIndex)
End Property

Public Property Get MVNAR(Optional DtIndex As Integer = 1) As Variant
    MVNAR = IfEmpty(DataItem("LH_POL_MVRY_VAL", "NAR_AMT", DtIndex), 0)
End Property

'===============================================================================================
' SECTION 17: DEATH BENEFIT OPTION
'===============================================================================================

Public Property Get DBOptionCode() As Variant
    DBOptionCode = IfEmpty(DataItem("LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD", 1), "")
End Property

Public Property Get DBOption() As Variant
    DBOption = TranslateDBOptionCodeToText(CStr(DBOptionCode))
End Property

'===============================================================================================
' SECTION 18: LOAN PROPERTIES
'===============================================================================================

Public Property Get HasLoans() As Boolean
    HasLoans = (TotalRegLnPrinciple + TotalPrefLnPrinciple + TotalVarLnPrinciple) > 0
End Property

Public Property Get PolicyDebt() As Variant
    If IsAdvancedProduct Then
        PolicyDebt = TotalPrefLnPrinciple + TotalPrefLnAccrued + _
                     TotalRegLnPrinciple + TotalRegLnAccrued + _
                     TotalVarLnPrinciple + TotalVarLnAccrued
    Else
        PolicyDebt = TotalRegLnPrinciple + TotalRegLnAccrued
    End If
End Property

Public Property Get TotalRegLnPrinciple() As Variant
    If IsAdvancedProduct Then
        TotalRegLnPrinciple = TotalFundRegLnPrinciple
    Else
        TotalRegLnPrinciple = TotalTradRegLnPrinciple
    End If
End Property

Public Property Get TotalRegLnAccrued() As Variant
    If IsAdvancedProduct Then
        TotalRegLnAccrued = TotalFundRegLnAccrued
    Else
        TotalRegLnAccrued = TotalTradRegLnAccrued
    End If
End Property

Public Property Get TotalPrefLnPrinciple() As Variant
    If IsAdvancedProduct Then
        TotalPrefLnPrinciple = TotalFundPrefLnPrinciple
    Else
        TotalPrefLnPrinciple = TotalTradPrefLnPrinciple
    End If
End Property

Public Property Get TotalPrefLnAccrued() As Variant
    If IsAdvancedProduct Then
        TotalPrefLnAccrued = TotalFundPrefLnAccrued
    Else
        TotalPrefLnAccrued = TotalTradPrefLnAccrued
    End If
End Property

Public Property Get TotalVarLnPrinciple() As Variant
    If IsAdvancedProduct Then
        TotalVarLnPrinciple = TotalFundVarLnPrinciple
    Else
        TotalVarLnPrinciple = Empty
    End If
End Property

Public Property Get TotalVarLnAccrued() As Variant
    If IsAdvancedProduct Then
        TotalVarLnAccrued = TotalFundVarLnAccrued
    Else
        TotalVarLnAccrued = Empty
    End If
End Property

' Traditional loan detail
Public Property Get TradLoanCount() As Integer
    TradLoanCount = DataItemCount("LH_CSH_VAL_LOAN", "LN_PRI_AMT")
End Property

Private Property Get TotalTradRegLnPrinciple() As Variant
    Dim x As Integer, subtotal As Double
    For x = 1 To TradLoanCount
        If DataItem("LH_CSH_VAL_LOAN", "MVRY_DT", x) = "12/31/9999" And _
           DataItem("LH_CSH_VAL_LOAN", "PRF_LN_IND", x) = 0 Then
            subtotal = subtotal + DataItem("LH_CSH_VAL_LOAN", "LN_PRI_AMT", x)
        End If
    Next
    TotalTradRegLnPrinciple = subtotal
End Property

Private Property Get TotalTradRegLnAccrued() As Variant
    Dim x As Integer, subtotal As Double
    For x = 1 To TradLoanCount
        If DataItem("LH_CSH_VAL_LOAN", "MVRY_DT", x) = "12/31/9999" And _
           DataItem("LH_CSH_VAL_LOAN", "PRF_LN_IND", x) = 0 Then
            subtotal = subtotal + DataItem("LH_CSH_VAL_LOAN", "POL_LN_ITS_AMT", x)
        End If
    Next
    TotalTradRegLnAccrued = subtotal
End Property

Private Property Get TotalTradPrefLnPrinciple() As Variant
    Dim x As Integer, subtotal As Double
    For x = 1 To TradLoanCount
        If DataItem("LH_CSH_VAL_LOAN", "MVRY_DT", x) = "12/31/9999" And _
           DataItem("LH_CSH_VAL_LOAN", "PRF_LN_IND", x) = 1 Then
            subtotal = subtotal + DataItem("LH_CSH_VAL_LOAN", "LN_PRI_AMT", x)
        End If
    Next
    TotalTradPrefLnPrinciple = subtotal
End Property

Private Property Get TotalTradPrefLnAccrued() As Variant
    Dim x As Integer, subtotal As Double
    For x = 1 To TradLoanCount
        If DataItem("LH_CSH_VAL_LOAN", "MVRY_DT", x) = "12/31/9999" And _
           DataItem("LH_CSH_VAL_LOAN", "PRF_LN_IND", x) = 1 Then
            subtotal = subtotal + DataItem("LH_CSH_VAL_LOAN", "POL_LN_ITS_AMT", x)
        End If
    Next
    TotalTradPrefLnAccrued = subtotal
End Property

' Fund-based loan detail
Public Property Get LoanFundCount() As Integer
    LoanFundCount = DataItemCount("LH_FND_VAL_LOAN", "MVRY_DT")
End Property

Private Property Get TotalFundRegLnPrinciple() As Variant
    Dim x As Integer, subtotal As Double
    For x = 1 To LoanFundCount
        If DataItem("LH_FND_VAL_LOAN", "MVRY_DT", x) = "12/31/9999" And _
           DataItem("LH_FND_VAL_LOAN", "FND_ID_CD", x) <> "LZ" And _
           DataItem("LH_FND_VAL_LOAN", "PRF_LN_IND", x) = 0 Then
            subtotal = subtotal + DataItem("LH_FND_VAL_LOAN", "LN_PRI_AMT", x)
        End If
    Next
    TotalFundRegLnPrinciple = subtotal
End Property

Private Property Get TotalFundRegLnAccrued() As Variant
    Dim x As Integer, subtotal As Double
    For x = 1 To LoanFundCount
        If DataItem("LH_FND_VAL_LOAN", "MVRY_DT", x) = "12/31/9999" And _
           DataItem("LH_FND_VAL_LOAN", "FND_ID_CD", x) <> "LZ" And _
           DataItem("LH_FND_VAL_LOAN", "PRF_LN_IND", x) = 0 And _
           DataItem("LH_FND_VAL_LOAN", "LN_ITS_AMT_TYP_CD", x) <> "1" Then
            subtotal = subtotal + DataItem("LH_FND_VAL_LOAN", "POL_LN_ITS_AMT", x)
        End If
    Next
    TotalFundRegLnAccrued = subtotal
End Property

Private Property Get TotalFundPrefLnPrinciple() As Variant
    Dim x As Integer, subtotal As Double
    For x = 1 To LoanFundCount
        If DataItem("LH_FND_VAL_LOAN", "MVRY_DT", x) = "12/31/9999" And _
           DataItem("LH_FND_VAL_LOAN", "FND_ID_CD", x) <> "LZ" And _
           DataItem("LH_FND_VAL_LOAN", "PRF_LN_IND", x) = 1 Then
            subtotal = subtotal + DataItem("LH_FND_VAL_LOAN", "LN_PRI_AMT", x)
        End If
    Next
    TotalFundPrefLnPrinciple = subtotal
End Property

Private Property Get TotalFundPrefLnAccrued() As Variant
    Dim x As Integer, subtotal As Double
    For x = 1 To LoanFundCount
        If DataItem("LH_FND_VAL_LOAN", "MVRY_DT", x) = "12/31/9999" And _
           DataItem("LH_FND_VAL_LOAN", "FND_ID_CD", x) <> "LZ" And _
           DataItem("LH_FND_VAL_LOAN", "PRF_LN_IND", x) = 1 And _
           DataItem("LH_FND_VAL_LOAN", "LN_ITS_AMT_TYP_CD", x) <> "1" Then
            subtotal = subtotal + DataItem("LH_FND_VAL_LOAN", "POL_LN_ITS_AMT", x)
        End If
    Next
    TotalFundPrefLnAccrued = subtotal
End Property

Private Property Get TotalFundVarLnPrinciple() As Variant
    Dim x As Integer, subtotal As Double
    For x = 1 To LoanFundCount
        If DataItem("LH_FND_VAL_LOAN", "MVRY_DT", x) = "12/31/9999" And _
           DataItem("LH_FND_VAL_LOAN", "FND_ID_CD", x) = "LZ" Then
            subtotal = subtotal + DataItem("LH_FND_VAL_LOAN", "LN_PRI_AMT", x)
        End If
    Next
    TotalFundVarLnPrinciple = subtotal
End Property

Private Property Get TotalFundVarLnAccrued() As Variant
    Dim x As Integer, subtotal As Double
    For x = 1 To LoanFundCount
        If DataItem("LH_FND_VAL_LOAN", "MVRY_DT", x) = "12/31/9999" And _
           DataItem("LH_FND_VAL_LOAN", "FND_ID_CD", x) = "LZ" And _
           DataItem("LH_FND_VAL_LOAN", "LN_ITS_AMT_TYP_CD", x) <> "1" Then
            subtotal = subtotal + DataItem("LH_FND_VAL_LOAN", "POL_LN_ITS_AMT", x)
        End If
    Next
    TotalFundVarLnAccrued = subtotal
End Property

'===============================================================================================
' SECTION 19: PERSON PROPERTIES
'===============================================================================================

Public Property Get PersonCount() As Integer
    PersonCount = DataItemCount("VH_POL_HAS_LOC_CLT", "PRS_CD")
End Property

Public Property Get PersonCode(x As Integer) As Variant
    PersonCode = DataItem("LH_CTT_CLIENT", "PRS_CD", x)
End Property

Public Property Get PersonSequenceCode(x As Integer) As Variant
    PersonSequenceCode = DataItem("LH_CTT_CLIENT", "PRS_SEQ_NBR", x)
End Property

Public Property Get PersonFirstName(x As Integer) As Variant
    PersonFirstName = Trim(DataItem("VH_POL_HAS_LOC_CLT", "CK_FST_NM", x))
End Property

Public Property Get PersonLastName(x As Integer) As Variant
    PersonLastName = Trim(DataItem("VH_POL_HAS_LOC_CLT", "CK_LST_NM", x))
End Property

Public Property Get PersonBirthDate(x As Integer) As Variant
    PersonBirthDate = DataItem("LH_CTT_CLIENT", "BIR_DT", x)
End Property

Public Property Get PersonGender(x As Integer) As Variant
    PersonGender = DataItem("LH_CTT_CLIENT", "GENDER_CD", x)
End Property

Public Function PersonIndex(Optional PersonCodeString As String = "00", Optional SeqNumber As Integer = 1) As Integer
    Dim x As Integer
    For x = 1 To PersonCount
        If PersonCode(x) = PersonCodeString And PersonSequenceCode(x) = SeqNumber Then
            PersonIndex = x
            Exit Function
        End If
    Next
End Function

Public Property Get CovInsuredName(Cov As Integer) As Variant
    Dim x As Integer
    For x = 1 To PersonCount
        If PersonCode(x) = CovPersonCode(Cov) And PersonSequenceCode(x) = CovPersonSequenceCode(Cov) Then
            CovInsuredName = PersonFirstName(x) & " " & PersonLastName(x)
            Exit Property
        End If
    Next
    CovInsuredName = ""
End Property

Public Property Get IsJointInsured() As Boolean
    Dim x As Integer
    For x = 1 To PersonCount
        If PersonCode(x) = "01" Then
            IsJointInsured = True
            Exit Property
        End If
    Next
    IsJointInsured = False
End Property

'===============================================================================================
' SECTION 20: AGENT PROPERTIES
'===============================================================================================

Public Property Get AgentCount() As Integer
    AgentCount = DataItemCount("LH_CTT_COM_PHA_WA", "WRT_AGT_NM")
End Property

Public Property Get Agent(Optional x As Integer = 1) As Variant
    Agent = IfEmpty(DataItem("LH_CTT_COM_PHA_WA", "WRT_AGT_NM", x), "")
End Property

'===============================================================================================
' SECTION 21: COMMISSION TARGET DICTIONARY (Private Cache)
'===============================================================================================

Private Function ComTargetDictionary() As Dictionary
    If mCurrentPolicy("CommTargets") Is Nothing Then
        Dim dctComTargets As Dictionary
        Set dctComTargets = New Dictionary
        
        Dim CovCTPCount As Integer
        Dim CovCTP() As Variant
        Dim CovCTPhase() As Variant
        Dim CovCTDate() As Variant
        Dim CTPTotal As Double
        
        CovCTPCount = 0
        If DataItemCount("LH_COM_TARGET", "TAR_TYP_CD") > 0 Then
            Dim x As Integer
            Dim TargetType As String
            
            For x = 1 To DataItemCount("LH_COM_TARGET", "TAR_TYP_CD")
                TargetType = DataItem("LH_COM_TARGET", "TAR_TYP_CD", x)
                If TargetType = "CT" Then
                    ReDim Preserve CovCTP(CovCTPCount)
                    ReDim Preserve CovCTPhase(CovCTPCount)
                    ReDim Preserve CovCTDate(CovCTPCount)
                    CovCTP(CovCTPCount) = IfEmpty(DataItem("LH_COM_TARGET", "TAR_PRM_AMT", x), 0)
                    CovCTPhase(CovCTPCount) = DataItem("LH_COM_TARGET", "AGT_COM_PHA_NBR", x)
                    CovCTDate(CovCTPCount) = DataItem("LH_COM_TARGET", "TAR_DT", x)
                    CTPTotal = CTPTotal + CovCTP(CovCTPCount)
                    CovCTPCount = CovCTPCount + 1
                End If
            Next
        End If
        
        dctComTargets.Add "CovCTPCount", CovCTPCount
        dctComTargets.Add "CovCTP", CovCTP
        dctComTargets.Add "CovCTPhase", CovCTPhase
        dctComTargets.Add "CovCTDate", CovCTDate
        dctComTargets.Add "CTP", CTPTotal
        Set mCurrentPolicy("CommTargets") = dctComTargets
    End If
    
    Set ComTargetDictionary = mCurrentPolicy("CommTargets")
End Function

'===============================================================================================
' SECTION 22: INFORCE DICTIONARY EXPORT
'===============================================================================================

Public Function InforceDictionary() As Dictionary
    Dim dctInforce As Dictionary
    Set dctInforce = New Dictionary
    
    Dim dct As Dictionary
    
    ' Base coverages
    Set dct = New Dictionary
    dctInforce.Add "BaseCovs", dct
    
    ' Rider coverages
    Set dct = New Dictionary
    dctInforce.Add "RiderCovs", dct
    
    Dim x As Integer
    For x = 1 To CovCount
        If CovPlancode(x) = CovPlancode(1) Then
            dctInforce("BaseCovs").Add dctInforce("BaseCovs").Count + 1, CreateCoverageDictionary(x)
        Else
            dctInforce("RiderCovs").Add dctInforce("RiderCovs").Count + 1, CreateCoverageDictionary(x)
        End If
    Next
    
    ' Benefits
    Set dct = New Dictionary
    dctInforce.Add "Benefits", dct
    For x = 1 To BenCount
        dctInforce("Benefits").Add dctInforce("Benefits").Count + 1, CreateBenefitDictionary(x)
    Next
    
    ' Policy data
    dctInforce.Add "Policy", CreatePolicyDataDictionary()
    
    Set InforceDictionary = dctInforce
End Function

Private Function CreateCoverageDictionary(xCov As Integer) As Dictionary
    Dim dct As Dictionary
    Set dct = New Dictionary
    
    dct.Add "Plancode", CovPlancode(xCov)
    dct.Add "FormNumber", CovFormNumber(xCov)
    dct.Add "IssueDate", CovIssueDate(xCov)
    dct.Add "MaturityDate", CovMaturityDate(xCov)
    dct.Add "Amount", CovAmount(xCov)
    dct.Add "OrigAmount", CovOrigAmount(xCov)
    dct.Add "IssueAge", CovIssueAge(xCov)
    dct.Add "Sex", CovSex(xCov)
    dct.Add "Rateclass", CovRateclass(xCov)
    dct.Add "Status", CovStatus(xCov)
    dct.Add "PersonCode", CovPersonCode(xCov)
    
    Set CreateCoverageDictionary = dct
End Function

Private Function CreateBenefitDictionary(xBen As Integer) As Dictionary
    Dim dct As Dictionary
    Set dct = New Dictionary
    
    dct.Add "Name", BenType(xBen)
    dct.Add "Plancode", BenPlancode(xBen)
    dct.Add "FormNumber", BenFormNumber(xBen)
    dct.Add "IssueDate", BenIssueDate(xBen)
    dct.Add "CeaseDate", BenCeaseDate(xBen)
    dct.Add "Amount", BenAmount(xBen)
    dct.Add "IssueAge", BenIssueAge(xBen)
    
    Set CreateBenefitDictionary = dct
End Function

Private Function CreatePolicyDataDictionary() As Dictionary
    Dim dct As Dictionary
    Set dct = New Dictionary
    
    dct.Add "Policynumber", Me.Policynumber
    dct.Add "CompanyCode", Me.CompanyCode
    dct.Add "Company", Me.Company
    dct.Add "StatusCode", Me.StatusCode
    dct.Add "ProductType", Me.ProductType
    dct.Add "IsFFS", Me.IsFFS
    dct.Add "MarketOrg", Me.ServicingMarketOrganization
    dct.Add "IssueState", Me.IssueStateAbbr
    dct.Add "DBOption", Left(CStr(DBOption), 1)
    dct.Add "BillablePremium", Me.BillPremium
    dct.Add "BillingMode", Me.BillMode
    dct.Add "ValuationDate", Me.ValuationDate
    dct.Add "InsuredName", Me.CovInsuredName(1)
    dct.Add "AgentName", Trim(CStr(Me.Agent))
    dct.Add "GLP", Me.GLP
    dct.Add "GSP", Me.GSP
    dct.Add "MTP", Me.MTP
    dct.Add "CTP", Me.CTP
    dct.Add "AccumGLP", Me.AccumGLP
    dct.Add "AccumMTP", Me.AccumMTP
    dct.Add "PremTD", Me.PremiumTD
    dct.Add "PremYTD", Me.PremiumYTD
    dct.Add "CostBasis", Me.CostBasis
    dct.Add "AccumWDs", Me.AccumWithdrawals
    dct.Add "MVAV", Me.MVAV
    dct.Add "RegLoanPrinciple", Me.TotalRegLnPrinciple
    dct.Add "RegLoanAccrued", Me.TotalRegLnAccrued
    dct.Add "PrefLoanPrinciple", Me.TotalPrefLnPrinciple
    dct.Add "PrefLoanAccrued", Me.TotalPrefLnAccrued
    dct.Add "COICharge", Me.MVCOICharge
    dct.Add "ExpenseCharge", Me.MVExpChrg
    
    Set CreatePolicyDataDictionary = dct
End Function

'===============================================================================================
' SECTION 23: TRANSLATION FUNCTIONS
'===============================================================================================

Public Function TranslateCompanyCodeToText(Code As String) As String
    Select Case Code
        Case "01": TranslateCompanyCodeToText = "ANICO"
        Case "04": TranslateCompanyCodeToText = "ANTEX"
        Case "06": TranslateCompanyCodeToText = "SLAICO"
        Case "08": TranslateCompanyCodeToText = "GSL"
        Case "26": TranslateCompanyCodeToText = "ANICO NY"
        Case Else: TranslateCompanyCodeToText = Code
    End Select
End Function

Public Function TranslateStateCodeToAbbr(intStateCode As Integer) As String
    Select Case intStateCode
        Case 1: TranslateStateCodeToAbbr = "AL"
        Case 2: TranslateStateCodeToAbbr = "AZ"
        Case 3: TranslateStateCodeToAbbr = "AR"
        Case 4: TranslateStateCodeToAbbr = "CA"
        Case 5: TranslateStateCodeToAbbr = "CO"
        Case 6: TranslateStateCodeToAbbr = "CT"
        Case 7: TranslateStateCodeToAbbr = "DE"
        Case 8: TranslateStateCodeToAbbr = "DC"
        Case 9: TranslateStateCodeToAbbr = "FL"
        Case 10: TranslateStateCodeToAbbr = "GA"
        Case 11: TranslateStateCodeToAbbr = "ID"
        Case 12: TranslateStateCodeToAbbr = "IL"
        Case 13: TranslateStateCodeToAbbr = "IN"
        Case 14: TranslateStateCodeToAbbr = "IA"
        Case 15: TranslateStateCodeToAbbr = "KS"
        Case 16: TranslateStateCodeToAbbr = "KY"
        Case 17: TranslateStateCodeToAbbr = "LA"
        Case 18: TranslateStateCodeToAbbr = "ME"
        Case 19: TranslateStateCodeToAbbr = "MD"
        Case 20: TranslateStateCodeToAbbr = "MA"
        Case 21: TranslateStateCodeToAbbr = "MI"
        Case 22: TranslateStateCodeToAbbr = "MN"
        Case 23: TranslateStateCodeToAbbr = "MS"
        Case 24: TranslateStateCodeToAbbr = "MO"
        Case 25: TranslateStateCodeToAbbr = "MT"
        Case 26: TranslateStateCodeToAbbr = "NE"
        Case 27: TranslateStateCodeToAbbr = "NV"
        Case 28: TranslateStateCodeToAbbr = "NH"
        Case 29: TranslateStateCodeToAbbr = "NJ"
        Case 30: TranslateStateCodeToAbbr = "NM"
        Case 31: TranslateStateCodeToAbbr = "NY"
        Case 32: TranslateStateCodeToAbbr = "NC"
        Case 33: TranslateStateCodeToAbbr = "ND"
        Case 34: TranslateStateCodeToAbbr = "OH"
        Case 35: TranslateStateCodeToAbbr = "OK"
        Case 36: TranslateStateCodeToAbbr = "OR"
        Case 37: TranslateStateCodeToAbbr = "PA"
        Case 38: TranslateStateCodeToAbbr = "RI"
        Case 39: TranslateStateCodeToAbbr = "SC"
        Case 40: TranslateStateCodeToAbbr = "SD"
        Case 41: TranslateStateCodeToAbbr = "TN"
        Case 42: TranslateStateCodeToAbbr = "TX"
        Case 43: TranslateStateCodeToAbbr = "UT"
        Case 44: TranslateStateCodeToAbbr = "VT"
        Case 45: TranslateStateCodeToAbbr = "VA"
        Case 46: TranslateStateCodeToAbbr = "WA"
        Case 47: TranslateStateCodeToAbbr = "WV"
        Case 48: TranslateStateCodeToAbbr = "WI"
        Case 49: TranslateStateCodeToAbbr = "WY"
        Case 50: TranslateStateCodeToAbbr = "AK"
        Case 51: TranslateStateCodeToAbbr = "HI"
        Case 52: TranslateStateCodeToAbbr = "PR"
        Case Else: TranslateStateCodeToAbbr = CStr(intStateCode)
    End Select
End Function

Public Function TranslateBillModeCodeToText(vntBillModeCode As String, Optional NonStandardMode As String = "") As String
    Select Case vntBillModeCode
        Case "1":
            TranslateBillModeCodeToText = "M - Monthly"
            If NonStandardMode = "2" Then TranslateBillModeCodeToText = "B - BiWeekly"
            If NonStandardMode = "S" Then TranslateBillModeCodeToText = "SM - SemiMonthly"
        Case "3": TranslateBillModeCodeToText = "Q - Quarterly"
        Case "6": TranslateBillModeCodeToText = "S - SemiAnnually"
        Case "12": TranslateBillModeCodeToText = "A - Annually"
        Case Else: TranslateBillModeCodeToText = vntBillModeCode
    End Select
End Function

Public Function TranslateDBOptionCodeToText(vntDBOptCode As String) As String
    Select Case vntDBOptCode
        Case "A", "1": TranslateDBOptionCodeToText = "A - Level"
        Case "B", "2": TranslateDBOptionCodeToText = "B - Increasing"
        Case "C", "3": TranslateDBOptionCodeToText = "C - Return Of Premium"
        Case Else: TranslateDBOptionCodeToText = vntDBOptCode
    End Select
End Function

Public Function TranslateStatusCodeToText(Code As String) As String
    Select Case Code
        Case "21", "22": TranslateStatusCodeToText = "Premium Paying"
        Case "31": TranslateStatusCodeToText = "Payor Death"
        Case "32", "33", "34": TranslateStatusCodeToText = "Disability"
        Case "41", "47": TranslateStatusCodeToText = "Paid Up"
        Case "42", "43": TranslateStatusCodeToText = "Single Premium"
        Case "44": TranslateStatusCodeToText = "ETI"
        Case "45": TranslateStatusCodeToText = "RPU"
        Case "46": TranslateStatusCodeToText = "Fully Paid Up"
        Case "54": TranslateStatusCodeToText = "Lapsing"
        Case "97": TranslateStatusCodeToText = "Reinstatement pending"
        Case "98": TranslateStatusCodeToText = "Policy not issued"
        Case "99": TranslateStatusCodeToText = "Terminated"
        Case Else: TranslateStatusCodeToText = Code
    End Select
End Function

Public Function TranslateSuspenseCodeToText(Code As String) As String
    Select Case Code
        Case "0": TranslateSuspenseCodeToText = "Active policy record"
        Case "1": TranslateSuspenseCodeToText = "Not used"
        Case "2": TranslateSuspenseCodeToText = "Suspend processing"
        Case "3": TranslateSuspenseCodeToText = "Death claim pending"
        Case Else: TranslateSuspenseCodeToText = Code
    End Select
End Function

Public Function TranslateBenefitTypeToText(BenefitType As String, Optional subType As String = "") As String
    Select Case BenefitType
        Case "1": TranslateBenefitTypeToText = "ADB"
        Case "2": TranslateBenefitTypeToText = "ADnD"
        Case "3": TranslateBenefitTypeToText = "PWoC"
        Case "4": TranslateBenefitTypeToText = "PWoT"
        Case "7": TranslateBenefitTypeToText = "GIO"
        Case "9": TranslateBenefitTypeToText = "PPB"
        Case "#":
            If subType = "" Then
                TranslateBenefitTypeToText = "ABR"
            Else
                Select Case subType
                    Case "1": TranslateBenefitTypeToText = "ABRTM"
                    Case "2": TranslateBenefitTypeToText = "ABRCT"
                    Case "3": TranslateBenefitTypeToText = "ABRCH"
                    Case "L": TranslateBenefitTypeToText = "ABRLN"
                    Case Else: TranslateBenefitTypeToText = "ABR" & subType
                End Select
            End If
        Case "A": TranslateBenefitTypeToText = "CCV"
        Case "U": TranslateBenefitTypeToText = "COLA"
        Case "B": TranslateBenefitTypeToText = "LTC"
        Case Else: TranslateBenefitTypeToText = BenefitType
    End Select
End Function

Public Function DetermineMarketOrg(CompanyCode As String, AgentCode As String) As String
    Select Case CompanyCode
        Case "01":
            Select Case AgentCode
                Case "1": DetermineMarketOrg = "MLM"
                Case "2": DetermineMarketOrg = "CSSD"
                Case "7": DetermineMarketOrg = "IMG"
                Case "D": DetermineMarketOrg = "DIRECT"
                Case Else: DetermineMarketOrg = AgentCode
            End Select
        Case "04": DetermineMarketOrg = "ANTEX"
        Case "06": DetermineMarketOrg = "SLAICO"
        Case "08": DetermineMarketOrg = "GSL"
        Case "26": DetermineMarketOrg = "FFL"
        Case "30":
            Select Case AgentCode
                Case "1": DetermineMarketOrg = "MLM"
                Case "7": DetermineMarketOrg = "IMG"
                Case "D": DetermineMarketOrg = "DIRECT"
                Case Else: DetermineMarketOrg = AgentCode
            End Select
        Case Else: DetermineMarketOrg = AgentCode
    End Select
End Function

'===============================================================================================
' SECTION 24: UTILITY FUNCTIONS
'===============================================================================================

Public Function IfEmpty(CheckValue As Variant, AlternateValue As Variant) As Variant
    If IsEmpty(CheckValue) Or IsNull(CheckValue) Then
        IfEmpty = AlternateValue
    Else
        IfEmpty = CheckValue
    End If
End Function

Public Function CompletedDateParts(difftype As String, argDate1 As Variant, argDate2 As Variant) As Long
    If IsEmpty(argDate1) Or IsEmpty(argDate2) Then Exit Function
    
    Dim EarlyDate As Date, LateDate As Date
    Dim tempDate As Date, Date1 As Date, Date2 As Date
    Dim k As Long
    
    Date1 = CDate(argDate1)
    Date2 = CDate(argDate2)
    
    If Date1 <= Date2 Then
        EarlyDate = Date1
        LateDate = Date2
    Else
        EarlyDate = Date2
        LateDate = Date1
    End If
    
    tempDate = EarlyDate
    k = 0
    Do While tempDate <= LateDate
        k = k + 1
        tempDate = DateAdd(difftype, k, EarlyDate)
    Loop
    CompletedDateParts = k - 1
End Function

Private Function FindIndex(ary As Variant, TargetValue As Variant) As Integer
    Dim x As Integer
    For x = LBound(ary) To UBound(ary)
        If ary(x) = TargetValue Then
            FindIndex = x
            Exit Function
        End If
    Next
    FindIndex = LBound(ary) - 1
End Function

Private Function Transpose2DArray(OldArray As Variant) As Variant
    Dim NewRowLB As Long, NewRowUB As Long, NewColumnLB As Long, NewColumnUB As Long
    
    NewRowLB = LBound(OldArray, 2)
    NewRowUB = UBound(OldArray, 2)
    NewColumnLB = LBound(OldArray, 1)
    NewColumnUB = UBound(OldArray, 1)
    
    Dim newArray() As Variant
    Dim x As Long, y As Long
    ReDim newArray(NewRowLB To NewRowUB, NewColumnLB To NewColumnUB)
    
    For x = NewRowLB To NewRowUB
        For y = NewColumnLB To NewColumnUB
            newArray(x, y) = OldArray(y, x)
        Next
    Next
    
    Transpose2DArray = newArray
End Function

Private Function InsertRowIntoArray(InputArray As Variant, Index As Long, RowArray As Variant) As Boolean
    If (Index < LBound(InputArray, 1)) Or (Index > UBound(InputArray, 1) + 1) Then Exit Function
    If UBound(RowArray) - LBound(RowArray) <> UBound(InputArray, 2) - LBound(InputArray, 2) Then Exit Function
    
    Dim TempArray() As Variant
    ReDim TempArray(LBound(InputArray, 1) To UBound(InputArray, 1) + 1, LBound(InputArray, 2) To UBound(InputArray, 2))
    
    Dim Ndx As Long, ColumnNdx As Long
    
    ' Add rows after Index
    For Ndx = UBound(InputArray, 1) To Index Step -1
        For ColumnNdx = LBound(InputArray, 2) To UBound(InputArray, 2)
            TempArray(Ndx + 1, ColumnNdx) = InputArray(Ndx, ColumnNdx)
        Next
    Next
    
    ' Insert new row
    For ColumnNdx = LBound(InputArray, 2) To UBound(InputArray, 2)
        TempArray(Index, ColumnNdx) = RowArray(ColumnNdx)
    Next
    
    ' Add rows before Index
    For Ndx = Index - 1 To LBound(InputArray, 1) Step -1
        For ColumnNdx = LBound(InputArray, 2) To UBound(InputArray, 2)
            TempArray(Ndx, ColumnNdx) = InputArray(Ndx, ColumnNdx)
        Next
    Next
    
    InputArray = TempArray
    InsertRowIntoArray = True
End Function
