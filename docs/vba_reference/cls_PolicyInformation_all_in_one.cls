VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "cls_PolicyInformation"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
'CHANGE LOG
'----------------------------------------------------------------------
'11/08/2023 RJH:    Added SkippedReinPolicyMonthsTerminated
'02/14/2022 RJH:    Added scheduled Loan Repay information to the Inforce dictionary
'11/09/2020 RJH:    Fixed FundAllocationPrctDictionary to look at only the latest set of premium allocation percentages
'11/09/2020 RJH:    Added PremiumAllocations to InforceDictionary
'05/18/2020 RJH:    Added table LH_LOC_CLT_ADR to get Insured Address information
'05/13/2020 RJH:    Replaced "LH_POL_HAS_LOC_CLT" with "VH_POL_HAS_LOC_CLT"
'01/11/2019 RJH:    Added FundValueImpaired to the Funds dictionary
'11/30/2018 RJH:    Added ForcedPremiumIndicator
'11/27/2018 RJH:    Added CovCeaseDate.  Fixed LastFinancialDate.
'11/16/2018 RJH:    Fixed some Property calls that returned the wrong propery name - this was on the loan repay properties
'11/09/2018 RJH:    Change ValidPolicyRequest to FindAndAddPolicy. Cleaned up the Add code so that it doesnt look for existing key.  This was already done in FindAndAddPolicy
'                   The dctPolicies place holder for CommTarget, FundAllocations, FundValues, BaseIndices, RiderIndices is initialized with Nothing.  Later that are added only if requested
'                   Added CovTableRatingCode which will return the letter of the table rating.  CovTableRating now just translates CovTableRatingCode into the table rating number

'11/6/2018  RJH:    Added BenefitPeriodCode, EliminationPeriodCode, CovBaseDct, CovRiderDct
'
'10/19/2018 RJH:    Added properties for data in LH_LN_RPY_TRM  (loan repayment billing)

'10/17/2018 RJH:    Added AgeCalcCode to InforceDictionary

'10/03/2018 RJH:    Modified CovRateBand to take the RateType argument.  That way we can get the band at issue for IUL14 plans (its the band for the target premium rate type)
'
'09/26/2018 RJH:    Added CovBandStructureCode and CovRateBand
'
'09/21/2018 RJH:    Added IsFFS property
'
'09/04/2018 RJH:    Added PersonIndex, CovPersonDOB and CovFlatCeaseAge
'                   cls_PolicyInformation(v1.1)

'08/30/2018 RJH:    created cls_PolicyInformation(v1.0)
'                   This class module is made up of 4 sections.
'                   1] Connect to DB2 data base with ODBC.  frmLogin may be launched to gather UserID and password if so needed
'                   2] Query builder to get data from DB2 tables for policy data
'                   3] Translation functions that translate DB2 data to more meaningful information (example DBOption 1 = "A - Level Death Benefit")
'                   4] Provides helpful interface to retrieve values for a policy.  Example: instead of requesting the value from field TAR_PRM_AMT from table LH_POL_TARGET where the TAR_TYP_CD = 'MT', this class has a property called MTP which will return that value
     



'----------------------------------
'DATA SOURCE AND ADD POLICY
'----------------------------------
Private dctPolicies As Dictionary
Private mCurrentPolicy As Dictionary
Private mCurrentKey As String
Private dctODBC As Dictionary
Private mblnConnectionProblems As Boolean 'This flag is set if there are problems connecting to the DB2 database

Public Property Get Cancelled()
    Cancelled = mblnConnectionProblems
End Property
Private Sub Class_Initialize()
    Set dctPolicies = New Dictionary
    Set mCurrentPolicy = New Dictionary
    Set dctODBC = New Dictionary
End Sub
Private Function MakePolicyKey(sPolicynumber As String, sCompanyCode As String, sSystemCode As String, sRegion As String) As String
    MakePolicyKey = UCase(Application.WorksheetFunction.Trim(sPolicynumber)) & "_" & sCompanyCode & "_" & sSystemCode & "_" & sRegion
End Function
Public Function Add(sPolicynumber As String, Optional sCompanyCode, Optional sSystemCode As String = "I", Optional sRegion As String = "CKPR") As Boolean
    
    mblnConnectionProblems = False
    
    Add = FindAndAddPolicy(sPolicynumber, sCompanyCode, sSystemCode, sRegion)
End Function
Private Function FindAndAddPolicy(sPolicynumber As String, sCompanyCode, sSystemCode As String, sRegion As String) As Boolean
    
    Dim PolicyList As Variant       'Matrix of polices with the following columns:  0 = CK_CMP_CD, 1 = CK_POLICY_NBR, 2 = CK_SYS_CD, 3 = TCH_POL_ID
                                    'First row of PolicyList is the field names
                                    
    PolicyList = QueryPolicy(sPolicynumber, sRegion, sCompanyCode, sSystemCode)

    'If no records are found then policy does not exist.
    'Notify and then exit function
    
    If mblnConnectionProblems Then
        FindAndAddPolicy = False
        MsgBox "Problems connecting to DB2 database"
        Exit Function
    End If
    
    If IsEmpty(PolicyList) Then
        If Not sCompanyCode = "" Then
            MsgBox "Cannot find policy " & sPolicynumber & " in " & sRegion & " for Company " & sCompanyCode
        Else
            MsgBox "Cannot find policy " & sPolicynumber & " in " & sRegion
        End If
        FindAndAddPolicy = False
        Exit Function
    End If

    'There are a small number of policynumbers used by more than one company.
    'If more than one record is found for a policy then the company needs
    'to be specified.  Display InputBox showing the company codes available.
    'When one is selected call this Function again with the compnay code
    'included.

    If UBound(PolicyList) > 1 Then
        Dim AvailableCompanyCodes As String
        AvailableCompanyCodes = PolicyList(1, 0)
        
        Dim x As Integer
        For x = 2 To UBound(PolicyList)
            AvailableCompanyCodes = AvailableCompanyCodes & ", " & PolicyList(x, 0)
        Next
        sCompanyCode = Format(InputBox("Need to specify company code for policy " & sPolicynumber & ".  Company codes available are " & AvailableCompanyCodes), "00")

        PolicyList = QueryPolicy(sPolicynumber, sRegion, sCompanyCode, sSystemCode)
    
        'If there are no records or still more than one record then exit function without success
        If UBound(PolicyList) <> 1 Then
            FindAndAddPolicy = False
            Exit Function
        End If
        
    End If
  
  
    
    'If you get to this point then the record count = 1 and the data is good.  Add policy
    
    FindAndAddPolicy = True
    
    Dim sPolicyID As String
    sPolicyID = PolicyList(1, 3)
    sCompanyCode = PolicyList(1, 0)
    Dim key As String
    key = MakePolicyKey(sPolicynumber, (sCompanyCode), sSystemCode, sRegion)
    
    If Not dctPolicies.Exists(key) Then
        Dim dct As Dictionary
        Set dct = New Dictionary
        
        dctPolicies.Add key, dct
        
        Set dct = New Dictionary
        dct.Add "Policynumber", sPolicynumber
        dct.Add "CompanyCode", sCompanyCode
        dct.Add "PolicyID", sPolicyID
        dct.Add "SystemCode", sSystemCode
        dct.Add "Region", sRegion
        dctPolicies(key).Add "Source", dct
        
        Set dct = New Dictionary
        dctPolicies(key).Add "Tables", dct
        
        Set dct = New Dictionary
        dctPolicies(key).Add "CommTargets", Nothing
        
        Set dct = New Dictionary
        dctPolicies(key).Add "FundAllocations", Nothing
        
        Set dct = New Dictionary
        dctPolicies(key).Add "FundValues", Nothing
        
        Set dct = New Dictionary
        dctPolicies(key).Add "BaseIndices", Nothing
    
        Set dct = New Dictionary
        dctPolicies(key).Add "RiderIndices", Nothing
        
    End If
        
      Set mCurrentPolicy = dctPolicies(key)
      mCurrentKey = key
        
End Function
Private Function QueryPolicy(sPolicynumber As String, sRegion As String, Optional sCompanyCode As Variant, Optional sSystemCode As String = "I") As Variant
    
    Dim aryWhereClause As Variant
    If IsMissing(sCompanyCode) Then
        aryWhereClause = Array("CK_SYS_CD='" & sSystemCode & "' ", "CK_POLICY_NBR='" & sPolicynumber & "' ")
    Else
        aryWhereClause = Array("CK_SYS_CD='" & sSystemCode & "' ", "CK_POLICY_NBR='" & sPolicynumber & "' ", "CK_CMP_CD='" & sCompanyCode & "' ")
    End If
 
    Dim SQLString As String
 
    SQLString = "SELECT  CK_CMP_CD, CK_POLICY_NBR, CK_SYS_CD, TCH_POL_ID FROM DB2TAB.LH_BAS_POL  WHERE " & Join(aryWhereClause, " AND ")
    SQLString = SQLStringForRegion(SQLString, sRegion)
 
    'Get query results

    QueryPolicy = FetchTable(SQLString, sRegion)


End Function

Public Property Get Policynumber()
    Policynumber = mCurrentPolicy("Source")("Policynumber")
End Property
Public Property Get PolicyID()
    PolicyID = mCurrentPolicy("Source")("PolicyID")
End Property
Public Property Get Region()
    Region = mCurrentPolicy("Source")("Region")
End Property
Public Property Get CompanyCode()
    CompanyCode = mCurrentPolicy("Source")("CompanyCode")
End Property
Public Property Get SystemCode()
    SystemCode = mCurrentPolicy("Source")("SystemCode")
End Property
Public Property Get index() As Integer
    If dctPolicies.count = 0 Then Exit Property
    index = FindIndex(dctPolicies.Keys, mCurrentKey) + 1
End Property
Public Property Let index(x As Integer)
    Dim KeysArrayIndex As Integer
    KeysArrayIndex = x - 1
    If KeysArrayIndex < LBound(dctPolicies.Keys) Or KeysArrayIndex > UBound(dctPolicies.Keys) Then
        MsgBox "Index out of bounds"
    Else
        mCurrentKey = dctPolicies.Keys(KeysArrayIndex)
        Set mCurrentPolicy = dctPolicies(mCurrentKey)
    End If
End Property
Public Property Get count()
    count = dctPolicies.count
End Property

Public Function DataItem(sTable As String, sField As String, Optional index As Integer = 1) As Variant
    Dim aryValues As Variant
    aryValues = DataItemArray(sTable, sField)
    If IsEmpty(aryValues) Then
        DataItem = Empty
    Else
        If IsNull(aryValues(index)) Then
            DataItem = Empty
        Else
            DataItem = aryValues(index)
        End If
    End If
End Function
Public Function DataItemCount(sTable As String, sField As String) As Integer
    Dim aryValues As Variant
    aryValues = DataItemArray(sTable, sField)
    If IsEmpty(aryValues) Then
        DataItemCount = 0
    Else
        DataItemCount = UBound(aryValues) - LBound(aryValues) + 1
    End If
End Function

Public Function DataItemArray(sTable As String, sField As String) As Variant
'This procedure checks the dataItem dictionary to see if dataitem has been requested before.  If yes, then the requested DataItem is found
'and returned. No then data is queried, added to dctDataItems and then returned

'This procedure DOES NOT validate if sTable and sField are valid Table name or Field name or valid combination within
'Anything can be requested and if its not found in DB2, then a dataitem set to Nothing is returned

Dim dctTable As Dictionary

If Not mCurrentPolicy("Tables").Exists(sTable) Then LoadDB2Table sTable

If IsEmpty(mCurrentPolicy("Tables")(sTable)) Then
    DataItemArray = Empty
    Exit Function
End If

If mCurrentPolicy("Tables")(sTable).Exists(sField) Then
    DataItemArray = mCurrentPolicy("Tables")(sTable)(sField)
Else
    DataItemArray = Empty
End If

End Function

Private Sub LoadDB2Table(Tablename As String)

Dim Source As Dictionary
Dim aryTable As Variant
Dim aryWhereClause As Variant
Dim aryOrderClause As Variant

Set Source = mCurrentPolicy("Source")

'This is used as an argument for most table lookups
aryWhereClause = Array("CK_SYS_CD='" & Source("SystemCode") & "' ", "TCH_POL_ID='" & Source("PolicyID") & "' ", "CK_CMP_CD='" & Source("CompanyCode") & "' ")
 
Select Case Tablename

  Case "LH_BAS_POL", "TH_BAS_POL", "LH_FXD_PRM_POL":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
                       
  Case "LH_SST_XTR_CRG", "TH_SST_XTR_CRG":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_XTR_CRG_REQ", "TH_XTR_CRG_REQ":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))

  Case "LH_COM_TARGET":
    aryOrderClause = Array("AGT_COM_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
    
  Case "LH_COV_TARGET":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_POL_TARGET":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
            
  Case "LH_COV_INS_GDL_PRM":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
            
  Case "LH_COV_INS_RNL_RT":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
  Case "LH_COV_PHA":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
  Case "LH_NEW_BUS_COV_PHA":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
  
  Case "TH_COV_PHA":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_COV_TARGET":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
             
  Case "LH_CTT_COM_PHA_WA":
    aryOrderClause = Array("AGT_ITS_EFF_DT DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_FND_ALC":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
            
  Case "LH_FND_TRS_ALC_SET":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
            
  Case "LH_FND_VAL_LOAN":
    aryOrderClause = Array("MVRY_DT DESC", "FND_VAL_PHA_NBR DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
        
  Case "LH_CSH_VAL_LOAN":
    aryOrderClause = Array("MVRY_DT DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_NON_TRD_POL", "TH_NON_TRD_POL":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
            
  Case "LH_POL_FND_VAL_TOT":
    aryOrderClause = Array("MVRY_DT DESC", "FND_ID_CD DESC", "FND_VAL_PHA_NBR DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))

  'Case "LH_POL_HAS_LOC_CLT":       This table is now restricted do to PII protection because it contains SSN
  '  aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
             
  Case "VH_POL_HAS_LOC_CLT":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
             
  Case "LH_POL_MVRY_VAL":
    aryOrderClause = Array("MVRY_DT DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_POL_TARGET":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
            
  Case "LH_POL_TOTALS":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
            
  Case "LH_POL_YR_TOT":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
            
  Case "LH_SPM_BNF", "TH_SPM_BNF":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_SST_XTR_CRG":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_TAMRA_7_PY_PER":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
            
  Case "LH_TAMRA_7_PY_YR":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
            
  Case "LH_CTT_CLIENT":
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
 
  Case "FH_FIXED":
    aryWhereClause = Array("TCH_POL_ID='" & Source("PolicyID") & "' ", "CK_CMP_CD='" & Source("CompanyCode") & "' ")
    aryOrderClause = Array("ASOF_DT DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
 
  Case "LH_UNAPPLIED_PTP":
    aryOrderClause = Array("ERN_DT_MO_YR_NBR DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
 
  Case "LH_APPLIED_PTP":
    aryOrderClause = Array("ERN_DT_MO_YR_NBR DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
 
  Case "LH_PAID_UP_ADD":
    aryOrderClause = Array("MVRY_DT DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
 
  Case "LH_ONE_YR_TRM_ADD"
    aryOrderClause = Array("MVRY_DT DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_PTP_ON_DEP":
    aryOrderClause = Array("MVRY_DT DESC")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_BNF_INS_RNL_RT":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_SST_XTR_RNL_RT":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
            
  Case "LH_TAMRA_MEC_PRM"  'as of 11/21/2016 there were no entries in this table in Production
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
  
  Case "LH_MO_ADD_PMT"  'as of 11/21/2016 there were no entries in this table in Production
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
  
  Case "LH_POL_MO_ITS_TOT"   'as of 11/21/2016 there were no entries in this table in Production
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
  
  Case "LH_POL_CAL_YR_TOT"
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))
  
  Case "TH_COV_INS_RNL_RT"
    aryOrderClause = Array("COV_PHA_NBR", "PRS_CD", "PRS_SEQ_NBR", "SEG_IDX_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
  
  Case "LH_BNF_INS_GDL_PRM" 'as of 11/21/2016 there were no entries in this table in Production
    aryOrderClause = Array("COV_PHA_NBR", "PRS_CD", "PRS_SEQ_NBR", "SEG_IDX_NBR")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
  
  Case "LH_COV_SKIPPED_PER"
    aryOrderClause = Array("COV_PHA_NBR", "LAP_DT")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, aryOrderClause, Source("Region"))
  
  Case Else:
    aryWhereClause = Array("TCH_POL_ID='" & Source("PolicyID") & "' ", "CK_CMP_CD='" & Source("CompanyCode") & "' ")
    aryTable = GetTableFromDB2(Tablename, aryWhereClause, , Source("Region"))

End Select


If IsEmpty(aryTable) Then
  mCurrentPolicy("Tables").Add Tablename, Empty
  Exit Sub
End If
 

If UBound(aryTable, 1) = 0 Then
    mCurrentPolicy("Tables").Add Tablename, Empty
Else
    Dim dct As Dictionary
    Set dct = New Dictionary
    mCurrentPolicy("Tables").Add Tablename, dct
    
    Set dct = mCurrentPolicy("Tables")(Tablename)
    LoadFieldData dct, aryTable
End If

End Sub



Private Sub LoadFieldData(dctTable As Dictionary, aryData As Variant)
'This sub reads in a 2D matrix of data where the first row is the field name
'Each field of data is put into a 1 based array and stored in the Tables dictionary


Dim RowLB As Integer, RowUB As Integer, ColLB As Integer, ColUB As Integer

RowLB = LBound(aryData, 1)
RowUB = UBound(aryData, 1)
ColLB = LBound(aryData, 2)
ColUB = UBound(aryData, 2)

Dim col As Integer, row As Integer
Dim FieldName As String

'If there are no rows of data then set each field reference to Empty
If RowLB = RowUB Then
    For col = ColLB To ColUB
        FieldName = aryData(0, col)
        dctTable.Add FieldName, Empty
    Next
Else
    Dim Vector As Variant
    For col = ColLB To ColUB
        FieldName = aryData(0, col)
        'The new vector for field data should start at index 1
        ReDim Vector(1 To RowUB)
        For row = 1 To RowUB
            Vector(row) = aryData(row, col)
        Next
        dctTable.Add FieldName, Vector
    Next
End If

End Sub

Private Function GetTableFromDB2(sTableName As String, aryWhereClause, Optional aryOrderClause, Optional sRegion As String = "CKPR") As Variant
'This procedure returns an 2D array for the requested table.  Field names are in the first row of the array

Dim SQLString As String
SQLString = "SELECT * FROM DB2TAB." & sTableName
SQLString = SQLString & " WHERE " & Join(aryWhereClause, " AND ")
If Not IsMissing(aryOrderClause) Then SQLString = SQLString & " ORDER BY " & Join(aryOrderClause, ", ")

'If the region is CKAS or CKCS then some substitutions are needed.  These are carried out in SQLStringForRegion
SQLString = SQLStringForRegion(SQLString, sRegion)

GetTableFromDB2 = FetchTable(SQLString, sRegion)

End Function




'==================================================================================================================================
'ODBC AND QUERY RESULTS
'==================================================================================================================================
Private Function GetConnection(sRegion As String) As ADODB.Connection
'This function returns an ADODB.Connection for the specified datasource
'It first checks the connection dictionary to see if a connection for the requested region is already established.

'If there is no connection then a connection is attempted using NEON ODBC setup on the computer.
'If this doesnt work the UserID and Password are requested and another attempt is made

    
    If Not dctODBC.Exists(sRegion) Then
        Dim cn As ADODB.Connection
        Set cn = New ADODB.Connection
        cn.ConnectionString = GetConnectionString(sRegion)
        
        Err.Clear
        
        On Error Resume Next
        cn.Open
     
        Dim TryCount As Integer
        
        Do While Err.Number <> 0
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
                Exit Function
            End If
            
            Set cn = New ADODB.Connection
            cn.Open GetConnectionString(sRegion), UserID, PWD
            Err.Clear
            If Err.Number <> 0 Then
                TryCount = TryCount + 1
                frm.Comment = "Connection Failed.  " & TryCount & IIf(TryCount = 1, " attempt.", " attempts.")
            End If
            
        Loop
        
        On Error GoTo 0
        
        'If you get to this point the connection is good. Add it to the dictinary
        dctODBC.Add sRegion, cn
    End If
            
    'Return the conneicton
    Set GetConnection = dctODBC(sRegion)

End Function

Private Function GetConnectionString(strDataSource As String)
Dim tempString As String

Select Case strDataSource
'  Case enumDataSource.SQLServer: tempString = "Provider=SQLOLEDB; " + "Data Source=" + mServerReference + "; " + "Initial Catalog=" + mDataBaseReference + "; " + "Integrated Security = SSPI;"
'  Case enumDataSource.MSAccess:    tempString = "Provider=Microsoft.Jet.OLEDB.4.0;Data Source=" & mDataBaseReference & ";"
'   Case "CKPR":    tempString = "DRIVER={DataDirect Shadow Client 7.3}; APNA=ADHOCUSER; APPL=ODBC; CPFX=SHADOW; DBTY=DB2; HOST=prodesa; LINK=TCPIP; PLAN=SDBC1010; PORT=1200; PWD=" & strPWD & "; SUBSYS=DSN; TSCH=Yes; UID=" & strUID & "; USERPARM=DRDA;"
'  Case enumDataSource.DB2_CKMO:    tempString = "DRIVER={NEON Client 32-bit (thread-safe)}; APNA=ADHOCUSER; APPL=ODBC; BYDB=Yes; CPFX=SHADOW; DBTY=DB2; DTCH=Yes; HOST=devlesa; LINK=TCPIP; NEONTRACE=INFO LOG=c:\neonlog.txt; PLAN=SDBC1010; PORT=1200; PWD=" & strPWD & "; SUBSYS=DSN; TSCH=Yes; UID=" & strUID & "; USERPARM=DRDA; WATR=No;"
'  Case enumDataSource.DB2_CKAS:    tempString = "DRIVER={NEON Client 32-bit (thread-safe)}; APNA=ADHOCUSER; APPL=ODBC; BYDB=Yes; CPFX=SHADOW; DBTY=DB2; DTCH=Yes; HOST=devlesa; LINK=TCPIP; NEONTRACE=INFO LOG=c:\neonlog.txt; PLAN=SDBC1010; PORT=1200; PWD=" & strPWD & "; SUBSYS=DSNT; TSCH=Yes; UID=" & strUID & "; USERPARM=DRDA; WATR=No;"
  
'  Case "ULRates":  tempString = "Provider=SQLOLEDB; Data Source='dsul_ratesdev'; Initial Catalog='ul_rates'; Integrated Security = SSPI;"
  Case "CKPR":    tempString = "Data Source=" + "NEON_DSN"
  Case "CKMO":    tempString = "Data Source=" + "NEON_DSNM"
  Case "CKAS":    tempString = "Data Source=" + "NEON_DSNT"
  Case "CKCS":    tempString = "Data Source=" + "NEON_DSNT"
End Select

GetConnectionString = tempString
End Function

Public Function FetchTable(QueryStatements As String, DataSource As String) As Variant
    'Open Recordset
    Dim DataSet As ADODB.Recordset
    Set DataSet = New ADODB.Recordset
 
    On Error GoTo EmptySetErrorHandler
       
       
        '10/6/2021 - RJH.    I got a new computer with MS Office 365; my old computer had Office 2016.
        '                   For some reason the query wouldn't run and I kept getting an "Automation Error".
        '                   I was able to figure out that the query would run only if it contained a "WITH" statement.
        '                   I have no idea why this works but it does.
        '                   So to every query that does not contain a "WITH" statement I add a benign "WITH" clause.
        If Left(QueryStatements, 4) <> "WITH" Then QueryStatements = "WITH DUMBY AS (SELECT 1 FROM DB2TAB.LH_COV_PHA) " & QueryStatements
        
    
        DataSet.Open QueryStatements, GetConnection(DataSource)
        DataSet.MoveFirst
    
        'Get recordset data into array
        Dim DataArray As Variant
        DataArray = DataSet.GetRows
        DataArray = Transpose2DArray(DataArray)
        
        'Create a dictionary of field names.  this will be used to easily get an array of field names
        Dim dctFlds As Dictionary
        Dim fld As Variant
        Set dctFlds = New Dictionary
        For Each fld In DataSet.Fields
            dctFlds.Add fld.Name, fld.Name
        Next
    
        'Add Field names to the top of the DataArray
        Call InsertRowIntoArray(DataArray, LBound(DataArray), dctFlds.Keys)
    
        FetchTable = DataArray
        
        Set DataSet = Nothing
    On Error GoTo 0
    
    Exit Function
  
EmptySetErrorHandler:
    Set DataSet = Nothing
    On Error GoTo 0
End Function

Public Function SQLStringForRegion(SQLString As String, DB2_Source As String)
Dim tempStr As String
 Select Case DB2_Source
   Case "CKAS": tempStr = Replace(SQLString, "DB2TAB.", "UNIT.", , , vbTextCompare)
   Case "CKCS": tempStr = Replace(SQLString, "DB2TAB.", "CYBERTEK.", , , vbTextCompare)
   Case Else: tempStr = SQLString
 End Select
 SQLStringForRegion = tempStr
End Function



'==================================================================================================================================
'POLICY INFORMATION
'==================================================================================================================================

Property Get ValuationDate() As Variant
'Valuation date should be last MV date.  but trad doesnt have MV, so use NextMonthliversary
If Me.ProductLineCode = "U" Or Me.ProductLineCode = "I" Then
  If Me.MVCount = 0 Then
    ValuationDate = "Null"
  Else
    ValuationDate = Me.MVDate
  End If
  Exit Property
End If

If Me.NextMonthliversary = "Null" Then
    ValuationDate = "Null"
    Exit Property
End If

If Me.NextMonthliversary = 0 Then
     ValuationDate = Me.LastFinancialDate
Else
     ValuationDate = DateAdd("m", -1, Me.NextMonthliversary)
End If
End Property
Property Get InGrace()
    If Me.AdvancedProductIndicator = "1" Then
        InGrace = IfEmpty(DataItem("LH_NON_TRD_POL", "IN_GRA_PER_IND", 1), "")
    Else
        InGrace = IfEmpty(DataItem("LH_TRD_POL", "IN_GRA_PER_IND", 1), "")
    End If
End Property
Property Get GPEDate()
If Me.AdvancedProductIndicator = "1" Then
    GPEDate = IfEmpty(DataItem("LH_NON_TRD_POL", "GRA_PER_EXP_DT", 1), "")
Else
    GPEDate = IfEmpty(DataItem("LH_TRD_POL", "GRA_PER_EXP_DT", 1), "")
End If
End Property
Property Get PolicyYear()
 PolicyYear = CompletedDateParts("YYYY", CovIssueDate(1), Me.ValuationDate) + 1
End Property
Property Get PolicyMonth()
  PolicyMonth = MonthOfYear(Month(CovIssueDate(1)), Month(Me.ValuationDate))
End Property
Property Get AgeAtMaturity()
Dim Yrs As Integer
 Yrs = CompletedDateParts("YYYY", Me.CovIssueDate(1), Me.CovMaturityDate(1))
 AgeAtMaturity = Me.CovIssueAge(1) + Yrs
End Property

'====================================================================================================================================================================================
'Inforce Dictionary
'====================================================================================================================================================================================

Public Function InforceDictionary() As Dictionary

Dim dctInforce As Dictionary
Set dctInforce = New Dictionary

Dim dct As Dictionary

Set dct = New Dictionary
dctInforce.Add "BaseCovs", dct

Set dct = New Dictionary
dctInforce.Add "RiderCovs", dct

Dim x As Integer
For x = 1 To CovCount
    If CovPlancode(x) = CovPlancode(1) Then
        dctInforce("BaseCovs").Add dctInforce("BaseCovs").count + 1, CoverageDictionary(x)
    Else
        dctInforce("RiderCovs").Add dctInforce("RiderCovs").count + 1, CoverageDictionary(x)
    End If
Next

Set dct = New Dictionary
dctInforce.Add "Benefits", dct
For x = 1 To BenCount
    dctInforce("Benefits").Add dctInforce("Benefits").count + 1, CreateBenefitDictionary(x)
Next

dctInforce.Add "Policy", CreatePolicyDataDictionary

dctInforce.Add "Funds", CreateFundDictionary

dctInforce.Add "PremAllocation", PremiumAllocationPercentages

Dim TotalAV As Double
Dim FundID
For Each FundID In dctInforce("Funds").Keys
    TotalAV = TotalAV + dctInforce("Funds")(FundID)("FundValue") + dctInforce("Funds")(FundID)("FundValueImpaired")
Next
dctInforce("Policy").Add "MVAV", Me.MVAV
dctInforce("Policy").Add "TotalAV", TotalAV
dctInforce("Policy").Add "SWAM", MVMonthlyDeduction * 12


Set InforceDictionary = dctInforce
Set dctInforce = Nothing
End Function

Private Function CoverageDictionary(xCov As Integer) As Dictionary
    Dim dct As Dictionary
    Set dct = New Dictionary
    
    dct.Add "Plancode", CovValueByName("Plancode", xCov)
    dct.Add "FormNumber", CovValueByName("FormNumber", xCov)
    dct.Add "IssueDate", CovValueByName("IssueDate", xCov)
    dct.Add "MaturityDate", CovValueByName("MaturityDate", xCov)
    dct.Add "Amount", CovValueByName("Amount", xCov)
    dct.Add "OrigAmount", CovValueByName("OrigAmount", xCov)
    dct.Add "IssueAge", CovValueByName("IssueAge", xCov)
    dct.Add "Sex", CovValueByName("Sex", xCov)
    dct.Add "TrueSex", CovValueByName("TrueSex", xCov)
    dct.Add "Rateclass", CovValueByName("Rateclass", xCov)
    dct.Add "TableRating", CovValueByName("TableRating", xCov)
    dct.Add "Flat1", CovValueByName("Flat1", xCov)
    dct.Add "Flat1Annual", CovValueByName("Flat1Annual", xCov)
    dct.Add "Flat1CeaseDate", CovValueByName("Flat1CeaseDate", xCov)
    dct.Add "Flat1CeaseAge", CovValueByName("Flat1CeaseAge", xCov)
    dct.Add "Flat2", CovValueByName("Flat2", xCov)
    dct.Add "Flat2CeaseDate", CovValueByName("Flat2CeaseDate", xCov)
    dct.Add "Flat2CeaseAge", CovValueByName("Flat2CeaseAge", xCov)
    dct.Add "Flat2Annual", CovValueByName("Flat2Annual", xCov)
    dct.Add "Status", CovValueByName("Status", xCov)
    dct.Add "PersonCode", CovValueByName("PersonCode", xCov)
    
    If CovValueByName("Status", xCov) = "0" Then
        dct.Add "PersonDOB", CovValueByName("PersonDOB", xCov)
    Else
        dct.Add "PersonDOB", CovValueByName("PersonDOB", xCov)
    End If
    
    dct.Add "AgeCalcCode", CovValueByName("AgeCalcCode", xCov)
    dct.Add "Qualified", CovValueByName("Qualified", xCov)
    dct.Add "CeaseDate", CovValueByName("CeaseDate", xCov)
    dct.Add "EliminationPeriodCode", CovValueByName("EliminationPeriodCode", xCov)
    dct.Add "BenefitPeriodCode", CovValueByName("BenefitPeriodCode", xCov)
    dct.Add "BandAtIssue", CovValueByName("BandAtIssue", xCov)
    
    Set CoverageDictionary = dct
    Set dct = Nothing

End Function

Private Function CreateBenefitDictionary(xBen As Integer) As Dictionary
    Dim dct As Dictionary
    Set dct = New Dictionary
    
    dct.Add "Name", BenValueByName("Name", xBen)
    dct.Add "Plancode", BenValueByName("Plancode", xBen)
    dct.Add "FormNumber", BenValueByName("FormNumber", xBen)
    dct.Add "IssueDate", BenValueByName("IssueDate", xBen)
    dct.Add "CeaseDate", BenValueByName("CeaseDate", xBen)
    dct.Add "OriginalCeaseDate", BenValueByName("OriginalCeaseDate", xBen)
    dct.Add "Amount", BenValueByName("Amount", xBen)
    dct.Add "IssueAge", BenValueByName("IssueAge", xBen)
    dct.Add "Rateclass", BenValueByName("Rateclass", xBen)
    dct.Add "RatingFactor", BenValueByName("RatingFactor", xBen)
        
    Set CreateBenefitDictionary = dct
    Set dct = Nothing
    
End Function

Private Function CreatePolicyDataDictionary() As Dictionary
    Dim dct As Dictionary
    Set dct = New Dictionary
    dct.Add "GPEDate", Me.GPEDate
    dct.Add "StatusCode", Me.StatusCode
    dct.Add "MarketOrg", Me.ServicingMarketOrganization
    dct.Add "ProductType", ProductType
    dct.Add "IsFFS", Me.IsFFS
    dct.Add "CompanyCode", Me.CompanyCode
    dct.Add "Company", Me.Company
    dct.Add "BillablePremium", Me.BillPremium
    dct.Add "BillingMode", Me.BillMode
    dct.Add "DialToPrem", DialToPrem
    dct.Add "DialToAge", DataItem("TH_USER_GENERIC", "DIAL_TO_PREM_AGE")
    
    'Policies can have scheduled loan repayments
    dct.Add "LoanRepayAmount", Me.LoanRepayAmount
    dct.Add "LoanRepayMode", TranslateBillModeCodeToText(Me.LoanRepayFrequency)
    
    dct.Add "Policynumber", Me.Policynumber
    dct.Add "InsuredName", Me.CovInsuredName(1)
    dct.Add "InsuredAddress1", Trim(Me.AddressStreet1(Me.AddressPersonCodeCount)) & " " & Trim(Me.AddressStreet2(Me.AddressPersonCodeCount))
    dct.Add "InsuredAddress2", Trim(Me.AddressCity(Me.AddressPersonCodeCount)) & ", " & Trim(Me.AddressState(Me.AddressPersonCodeCount)) & " " & Trim(Me.AddressZip(Me.AddressPersonCodeCount))
    dct.Add "AgentName", Trim(Me.Agent)
    dct.Add "ValuationDate", Me.ValuationDate
    dct.Add "COICharge", Me.MVCOICharge
    dct.Add "ExpenseCharge", Me.MVExpChrg
    dct.Add "OtherCharge", Me.MVOtherChrg
    dct.Add "IssueState", IssueStateAbbr
    dct.Add "DBOption", Left(DBOption, 1)
    dct.Add "RegLoanPrinicple", TotalRegLnPrinciple
    dct.Add "RegLoanAccrued", TotalRegLnAccrued
    dct.Add "PrefLoanPriniciple", TotalPrefLnPrinciple
    dct.Add "PrefLoanAccrued", TotalPrefLnAccrued
    dct.Add "VarLoanPrinciple", TotalVarLnPrinciple
    dct.Add "VarLoanAccrued", TotalVarLnAccrued
    dct.Add "GLP", GLP
    dct.Add "GSP", GSP
    dct.Add "GPT_CVAT", GPT_CVAT
    dct.Add "AccumGLP", AccumGLP
    dct.Add "AccumMTP", AccumMTP
    dct.Add "MAP_CeaseDate", MAPDate  'This is also known as the SafetyNet Cease Date (SNET)
    dct.Add "AccumWDs", AccumWithdrawals
    dct.Add "MTP", MTP
    dct.Add "CTP", CTP
    dct.Add "PremTD", PremiumTD
    dct.Add "PremYTD", PremiumYTD
    dct.Add "CostBasis", CostBasis
    dct.Add "PolicyMonthsTerminated", SkippedReinPolicyMonthsTerminated
    If IsError(CCV) Then
        dct.Add "CCVAV", 0
    Else
        dct.Add "CCVAV", CCV
    End If
    
    If MEC_Indicator = "" Then
        dct.Add "IsMEC", False
    Else
        dct.Add "IsMEC", IIf(CInt(MEC_Indicator) = 1, True, False)
    End If
    
    dct.Add "TAMRA_StateDate", TAMRA_7PayStartDate
    dct.Add "TAMRA_AV", TAMRA_7PayAV
    dct.Add "TAMRA_7PayLevel", Me.TAMRA_7PayLevel
    dct.Add "TAMRA_7PaySpecifiedAmount", Me.TAMRA_7PaySpecifiedAmount
    
    'l = IIf(CInt(MEC_Indicator) = 1, True, False)
    
    Dim dctTam As Dictionary
    Set dctTam = New Dictionary
    
    dctTam.Add 1, TAMRA_7PayPremiumsPaid(1)
    dctTam.Add 2, TAMRA_7PayPremiumsPaid(2)
    dctTam.Add 3, TAMRA_7PayPremiumsPaid(3)
    dctTam.Add 4, TAMRA_7PayPremiumsPaid(4)
    dctTam.Add 5, TAMRA_7PayPremiumsPaid(5)
    dctTam.Add 6, TAMRA_7PayPremiumsPaid(6)
    dctTam.Add 7, TAMRA_7PayPremiumsPaid(7)
    Set dct("TAMRA_7PayPremiumsPaid") = dctTam
    
    Set dctTam = New Dictionary
    dctTam.Add 1, TAMRA_7PayWithdrawals(1)
    dctTam.Add 2, TAMRA_7PayWithdrawals(2)
    dctTam.Add 3, TAMRA_7PayWithdrawals(3)
    dctTam.Add 4, TAMRA_7PayWithdrawals(4)
    dctTam.Add 5, TAMRA_7PayWithdrawals(5)
    dctTam.Add 6, TAMRA_7PayWithdrawals(6)
    dctTam.Add 7, TAMRA_7PayWithdrawals(7)
    Set dct("TAMRA_7PayWithdrawals") = dctTam
            
    l = dct("ProductType")
            
    Set CreatePolicyDataDictionary = dct
    Set dct = Nothing
    
End Function

Private Function CreateFundDictionary() As Dictionary
    Dim FundType
    Dim dctFunds As Dictionary
    Set dctFunds = New Dictionary
    Dim dct As Dictionary
    Dim FundID As Variant
    For Each FundID In FundValuesDictionary.Keys
    
        Set dct = New Dictionary
           
        dct.Add "PremiumAllocationPercent", PremiumAllocationPercentages(FundID)
        dct.Add "FundValue", FundValuesDictionary(FundID)
        dct.Add "FundID", CStr(FundID)
        
        'Impaired Values (ie loan principle) are not in the FundValuesDictionary, they're in LoanValuesDictionary
        If LoanValuesDictionary.Exists(FundID) Then
            ImpairedValue = LoanValuesDictionary(FundID)
        Else
            ImpairedValue = 0
        End If
        dct.Add "FundValueImpaired", ImpairedValue
                
        
        
        Select Case FundID
            Case "IX", "IC", "IX", "IS", "IP", "IR": FundType = "Indexed"
            Case Else:  FundType = "Fixed"
        End Select
        dct.Add "FundType", FundType
        Dim dctBuckets As Dictionary
        Set dctBuckets = New Dictionary
        
        Dim dctBucket As Dictionary
        Dim x As Integer
        For x = 1 To FundBucketCount
            If FundBucketMVDate(x) = "12/31/9999" And FundBucketID(x) = FundID Then
                Set dctBucket = New Dictionary
                dctBucket.Add "Value", FundBucketValue(x)
                dctBucket.Add "StartDate", FundBucketStartDate(x)
                dctBucket.Add "EndDate", FundBucketEndDate(x)
                dctBucket.Add "PhaseCode", FundBucketPhaseCode(x)
                dctBuckets.Add dctBuckets.count + 1, dctBucket
                
            End If
        Next
        dct.Add "Buckets", dctBuckets
    
        dctFunds.Add FundID, dct
        
    Next
    Set CreateFundDictionary = dctFunds
    Set dctFunds = Nothing
    
End Function

Private Function CreateImpairedValueDictionary() As Dictionary
    Dim FundType
    Dim dctFunds As Dictionary
    Set dctFunds = New Dictionary
    Dim dct As Dictionary
    Dim FundID As Variant
    
    For Each FundID In LoanValuesDictionary.Keys
        dctFunds.Add CStr(FundID), LoanValuesDictionary(FundID) 'This is the impaired value for policy funds (except for fundID LZ)
    Next
    Set CreateLoanDictionary = dctFunds
    Set dctFunds = Nothing
End Function





'====================================================================================================================================================================================
'LH_BAS_POL & TH_BAS_POL
'====================================================================================================================================================================================
Property Get AdvancedProductIndicator() As Variant
  AdvancedProductIndicator = DataItem("LH_BAS_POL", "NON_TRD_POL_IND")
End Property

Property Get NonForfeitureOption() As Variant
  NonForfeitureOption = DataItem("LH_BAS_POL", "NFO_OPT_TYP_CD")
End Property
Property Get LastAnniversary() As Variant
   LastAnniversary = DataItem("LH_BAS_POL", "LST_ANV_DT")
End Property
Property Get NextMonthliversary() As Variant
   NextMonthliversary = DataItem("LH_BAS_POL", "NXT_MVRY_PRC_DT")
End Property
Property Get LastFinancialDate() As Variant
  LastFinancialDate = DataItem("LH_BAS_POL", "LST_FIN_DT")
End Property
Property Get NextBillDate() As Variant
   NextBillDate = DataItem("LH_BAS_POL", "NXT_BIL_DT")
End Property
Property Get PremiumDatePaidTo() As Variant
   PremiumDatePaidTo = DataItem("LH_BAS_POL", "PRM_BILL_TO_DT")
End Property
'Property Get PolicyPremiumAmount() As Variant
'   PolicyPremiumAmount = mPolicyPremiumAmount
'End Property
Property Get Indicator1035() As Variant
   Indicator1035 = DataItem("LH_BAS_POL", "POL_1035_XCG_IND")
End Property
Property Get DividendOptionCode() As Variant
 DividendOptionCode = DataItem("LH_BAS_POL", "PRI_DIV_OPT_CD")
End Property
Property Get SecondardyDividendOptionCode() As Variant
  SecondardyDividendOptionCode = DataItem("LH_BAS_POL", "DIV_2ND_OPT_CD")
End Property

Property Get MDO() As Variant
  MDO = DataItem("LH_BAS_POL", "USR_RES_CD")
End Property
Property Get NonStandardModeCode() As Variant
  NonStandardModeCode = DataItem("LH_BAS_POL", "NSD_MD_CD")
End Property
Property Get SuspenseText() As Variant
 SuspenseText = TranslateSuspenseCodeToText(Me.SuspenseCode)
End Property
Property Get SuspenseCode() As Variant
 SuspenseCode = DataItem("LH_BAS_POL", "SUS_CD")
End Property
Property Get OriginalEntryText() As Variant
 OriginalEntryText = TranslateEntryCodeToText(Me.OriginalEntryCode)
End Property
Property Get OriginalEntryCode() As Variant
 OriginalEntryCode = DataItem("LH_BAS_POL", "OGN_ETR_CD")
End Property
Property Get LastEntryText() As Variant
 LastEntryText = TranslateLastEntryCodeToText(Me.LastEntryCode)
End Property
Property Get LastEntryCode() As Variant
 LastEntryCode = DataItem("LH_BAS_POL", "LST_ETR_CD")
End Property
Property Get StatusCode() As Variant
 StatusCode = DataItem("LH_BAS_POL", "PRM_PAY_STA_REA_CD")
End Property
Property Get StatusText() As Variant
 StatusText = TranslateStatusCodeToText(Me.StatusCode)
End Property
Property Get IssueStateCode() As Variant
 IssueStateCode = DataItem("LH_BAS_POL", "POL_ISS_ST_CD")
End Property
Property Get IssueStateAbbr() As Variant
 IssueStateAbbr = Me.TranslateStateCodeToAbbr(CInt(Me.IssueStateCode))
End Property
Property Get ResidentStateCode() As Variant
 ResidentStateCode = DataItem("LH_BAS_POL", "PRM_PAY_ST_CD")
End Property
Property Get ResidentStateAbbr() As Variant
 ResidentStateAbbr = Me.TranslateStateCodeToAbbr(CInt(Me.ResidentStateCode))
End Property
Property Get Company() As Variant
 Company = Me.TranslateCompanyCodeToText(Me.CompanyCode)
End Property
Property Get BillMode() As Variant
 BillMode = TranslateBillModeCodeToText(Me.BillModeCode)
End Property
Property Get BillModeCode() As Variant
 BillModeCode = DataItem("LH_BAS_POL", "PMT_FQY_PER")
End Property
Property Get BillPremium() As Variant
 BillPremium = DataItem("LH_BAS_POL", "POL_PRM_AMT")
End Property
Property Get BillFormCode() As Variant
 BillFormCode = DataItem("LH_BAS_POL", "BIL_FRM_CD")
End Property
Property Get NonStandardMode() As Variant
 NonStandardMode = DataItem("LH_BAS_POL", "NSD_MD_CD")
End Property
Property Get PremiumPayingResidentStateAbbr() As Variant
 PremiumPayingResidentStateAbbr = Me.TranslateStateCodeToAbbr(CInt(DataItem("LH_BAS_POL", "PRM_PAY_ST_CD")))
End Property
Property Get ServicingMarketOrganization() As Variant
  ServicingMarketOrganization = DetermineMarketOrg(Me.CompanyCode, Left(Me.ServicingBranchOrAgencyCode, 1))
End Property
Property Get AgencyBranchCode()
    AgencyBranchCode = Mid(Me.ServicingBranchOrAgencyCode, 2, 4)
End Property
Property Get ServicingAgentNumber() As Variant
  ServicingAgentNumber = DataItem("LH_BAS_POL", "SVC_AGT_NBR")
End Property
Property Get ServicingBranchOrAgencyCode() As Variant
 ServicingBranchOrAgencyCode = DataItem("LH_BAS_POL", "SVC_AGC_NBR")
End Property
Property Get IsFFS()
    IsFFS = (ServicingMarketOrganization = "IMG" And AgencyBranchCode = "0B4Q")
End Property
Property Get PolicyLoanChargeRate() As Variant
 PolicyLoanChargeRate = DataItem("LH_BAS_POL", "LN_PLN_ITS_RT")
End Property
Property Get LoanInterestTypeCode() As Variant
 LoanInterestTypeCode = DataItem("LH_BAS_POL", "LN_TYP_CD")
End Property
Property Get ForcedPremiumIndicator() As Variant
    ForcedPremiumIndicator = DataItem("TH_BAS_POL", "FORCED_PREM_IND")
End Property


'====================================================================================================================================================================================
'LH_COV_PHA
'====================================================================================================================================================================================
Property Get ProductType() As String
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

Property Get CovCount()
    CovCount = DataItemCount("LH_COV_PHA", "COV_PHA_NBR")
End Property
Property Get CovBaseCount()
    Dim x As Integer
    Dim count As Integer
    For x = 1 To CovCount
        If CovPlancode(x) = CovPlancode(1) Then
            count = count + 1
        End If
    Next
    CovBaseCount = count
End Property
Property Get CovRiderCount()
    Dim x As Integer
    Dim count As Integer
    For x = 1 To CovCount
        If CovPlancode(x) <> CovPlancode(1) Then
            count = count + 1
        End If
    Next
    CovRiderCount = count
End Property
Property Get CovBaseArray(FieldName As String) As Variant
Dim xCov As Integer
Dim xcount As Integer
Dim ary() As Variant

ReDim ary(1 To Me.CovBaseCount)
For xCov = 1 To CovCount
    If CovPlancode(xCov) = CovPlancode(1) Then
        xcount = xcount + 1
        ary(xcount) = CovValueByName(FieldName, xCov)
    End If
Next
CovBaseArray = ary
End Property
Property Get CovRiderArray(FieldName As String) As Variant
Dim xCov As Integer
Dim xcount As Integer
Dim ary() As Variant

If Me.CovRiderCount > 0 Then
    ReDim ary(1 To Me.CovRiderCount)
    For xCov = 1 To CovCount
        If CovPlancode(xCov) <> CovPlancode(1) Then
            xcount = xcount + 1
            ary(xcount) = CovValueByName(FieldName, xCov)
        End If
    Next
    CovRiderArray = ary
Else
    CovRiderArray = Empty
End If

End Property
Property Get CovBaseIndex() As Dictionary
'Returns a dictionary with the index associated with Base coverages
If mCurrentPolicy("BaseIndices") Is Nothing Then
    Dim dct As Dictionary
    Set dct = New Dictionary
    Dim xCov As Integer
    For xCov = 1 To CovCount
        If CovPlancode(xCov) = CovPlancode(1) Then dct.Add dct.count + 1, xCov
    Next
    Set mCurrentPolicy("BaseIndices") = dct
End If
Set CovBaseIndex = mCurrentPolicy("BaseIndices")
End Property
Property Get CovRiderIndex() As Dictionary
'Returns a dictionary with the index associated with Base coverages
If mCurrentPolicy("RiderIndices") Is Nothing Then
    Dim dct As Dictionary
    Set dct = New Dictionary
    Dim xCov As Integer
    For xCov = 1 To CovCount
        If CovPlancode(xCov) <> CovPlancode(1) Then dct.Add dct.count + 1, xCov
    Next
    Set mCurrentPolicy("RiderIndices") = dct
End If
Set CovRiderIndex = mCurrentPolicy("RiderIndices")
End Property
Property Get CovValueByName(FieldName As String, Optional index As Integer = 1)
    Dim tempValue As Variant
    Select Case FieldName
        Case "Plancode": tempValue = CovPlancode(index)
        Case "FormNumber": tempValue = CovFormNumber(index)
        Case "IssueDate": tempValue = CovIssueDate(index)
        Case "MaturityDate": tempValue = Me.CovMaturityDate(index)
        Case "Amount": tempValue = CovAmount(index)
        Case "OrigAmount": tempValue = CovOrigAmount(index)
        Case "IssueAge": tempValue = CovIssueAge(index)
        Case "Sex": tempValue = CovSex(index)
        Case "TrueSex": tempValue = CovTrueSex(index)
        Case "Rateclass": tempValue = CovRateclass(index)
        Case "TableRating": tempValue = CovTableRating(index)
        Case "Flat1": tempValue = CovFlat(index, 1)
        Case "Flat1CeaseDate": tempValue = CovFlatCeaseDate(index, 1)
        Case "Flat1CeaseAge": tempValue = CovFlatCeaseAge(index, 1)
        Case "Flat1Annual": tempValue = Me.CovFlatAnnual(index, 1)
        Case "Flat2": tempValue = CovFlat(index, 2)
        Case "Flat2CeaseDate": tempValue = CovFlatCeaseDate(index, 2)
        Case "Flat2CeaseAge": tempValue = CovFlatCeaseAge(index, 2)
        Case "Flat2Annual": tempValue = Me.CovFlatAnnual(index, 2)
        Case "Status": tempValue = CovStatus(index)
        Case "PersonCode": tempValue = CovPersonCode(index)
        Case "PersonDOB": tempValue = CovPersonDOB(index)
        Case "AgeCalcCode": tempValue = CovAgeCalcCode(index)
        Case "Qualified": tempValue = CovQualified(index)
        Case "CeaseDate":
                            If CovStatus(index) = "0" Then
                                tempValue = DataItem("LH_COV_PHA", "NXT_CHG_DT", index)
                            Else
                                tempValue = 0
                            End If
                            
        Case "BandAtIssue": tempValue = CovRateBand(index, "M")
        Case "EliminationPeriodCode": tempValue = CovAccEliminationPeriodCode(index)
        Case "BenefitPeriodCode": tempValue = CovAccBenefitPeriodCode(index)
                            
    End Select
    CovValueByName = tempValue
End Property
Property Get BaseCoveragesHaveSameAttainedAge() As Boolean
Dim x As Integer, AttainedAge1 As Integer, blnSame As Boolean
blnSame = True
AttainedAge1 = CovIssueAge(1) + CompletedDateParts("YYYY", CovIssueDate(1), Now())
For x = 2 To Me.CovCount
    If CovIsBase(x) Then
        blnSame = blnSame And (AttainedAge1 = CovIssueAge(x) + CompletedDateParts("YYYY", CovIssueDate(x), Now()))
    End If
Next
BaseCoveragesHaveSameAttainedAge = blnSame
End Property
Property Get CovValuationClass(Cov As Integer) As String
    CovValuationClass = DataItem("LH_COV_PHA", "INS_CLS_CD", Cov)
End Property
Property Get CovStatus(Cov As Integer)
    '0 = Terminated/Expired
    '1 = Paid-Up Coverage
    '2 = Premium Paying Coverage
    CovStatus = DataItem("LH_COV_PHA", "NXT_CHG_TYP_CD", Cov)
End Property
Property Get CovValuationBase(Cov As Integer) As String
    CovValuationBase = DataItem("LH_COV_PHA", "PLN_BSE_SRE_CD", Cov)
End Property
Property Get CovValuationSubseries(Cov As Integer) As String
    CovValuationSubseries = DataItem("LH_COV_PHA", "LIF_PLN_SUB_SRE_CD", Cov)
End Property
Property Get CovBandStructureCode(Cov As Integer) As String
    CovBandStructureCode = DataItem("LH_COV_PHA", "BAN_STRUCTURE_CD", Cov)
End Property
Property Get CovRateBand(Cov As Integer, Optional RateType As String = "C") As Integer
Dim tempValue As Integer
'All but one banding structure have band "A","B","C"... meaning 1,2,3...
'For band structure 6, however the band "X","Y","A","B","C" means 1,2,3,4,5.  Today (9/26/2018) this code is only used by ExecuUL.
'
If Trim(CovBandStructureCode(Cov)) = "" Or Trim(CovBandStructureCode(Cov)) = "00" Then
    tempValue = 0
Else
    If Trim(CovBandStructureCode(Cov)) = "6" Then
        tempValue = InStr(1, "XYABCDEFGHIJK", RenewalCovBandCode(Cov, RateType))
    Else
        tempValue = InStr(1, "ABCDEFGHIJK", Trim(RenewalCovBandCode(Cov, RateType)))
    End If
End If
CovRateBand = tempValue
End Property

Property Get ProductLineCode()
 ProductLineCode = DataItem("LH_COV_PHA", "PRD_LIN_TYP_CD")
End Property
Property Get ProductIndicator()
 ProductIndicator = DataItem("TH_COV_PHA", "AN_PRD_ID")
End Property
Property Get CovValueType() As String
  If Me.ProductLineCode = "U" Then
   CovValueType = "NA"
 Else
   CovValueType = IIf(Left(Me.StatusCode, 1) = "4", "NSP", "CV")
 End If
End Property
Property Get CovIsBase(Cov As Integer) As Boolean
  CovIsBase = (CovPlancode(Cov) = CovPlancode(1))
End Property
Property Get CovCOLAIndicator(Cov As Integer) As String
  CovCOLAIndicator = DataItem("TH_COV_PHA", "COLA_INCR_IND", Cov)
End Property
Property Get CovPhase(Cov As Integer) As Variant
  CovPhase = DataItem("LH_COV_PHA", "COV_PHA_NBR", Cov)
End Property
Property Get CovRateclass(Cov As Integer, Optional JtIndicator As Integer = 0) As Variant
    CovRateclass = RenewalCovRateclass(Cov, , JtIndicator)
End Property
Property Get CovPersonDOB(Cov As Integer, Optional JtIndicator As Integer = 0)
    Dim index As Integer
    If JtIndicator = 1 Then
        index = PersonIndex("01", CovPersonSequenceCode(Cov))
    Else
        index = PersonIndex(CovPersonCode(Cov), CovPersonSequenceCode(Cov))
    End If
    
    'If Index = 0 that means the person code was not found in the 89 segment even thought the person code was on the 02 segment.
    'This can happen if the coverage on the 02 segment has terminated and that insured is removed from the 89 segment (since the person code remains on the terminated 02 segment)
    'For example a spouse term rider could have been added at issue (person code = 40) but the rider could be terminated later and the spouse inforamation removed from the 89 segment
    If index = 0 Then
        CovPersonDOB = 0
    Else
        CovPersonDOB = PersonBirthDate(index)
    End If
End Property
Property Get CovTrueSex(Cov As Integer, Optional JtIndicator As Integer = 0) As Variant
'CovSex is really the RateSex, meaning is the sex code used to look up the rates.
'That can be different from TrueSex which is the real sex of the insured. For example, we have a unisex product where
'all the rates are loaded as male rates.  But the policy is issue to both males and females.  So in this case the sex on the
'89 segment could be Female while the rate sex (67 segment) could be male

    Dim index As Integer
    If JtIndicator = 1 Then
        index = PersonIndex("01", CovPersonSequenceCode(Cov))
    Else
        index = PersonIndex(CovPersonCode(Cov), CovPersonSequenceCode(Cov))
    End If
    
    If index = 0 Then
        CovTrueSex = 0
    Else
        CovTrueSex = PersonGender(index)
    End If


End Property
Property Get CovSex(Cov As Integer, Optional JtIndicator As Integer = 0) As Variant
Dim tempSex As Variant
tempSex = RenewalCovSexCode(Cov, , JtIndicator)
Select Case tempSex
  Case "1": tempSex = "M"
  Case "2": tempSex = "F"
  Case Else: tempSex = tempSex
End Select
CovSex = tempSex
End Property
Property Get CovUnits(Cov As Integer) As Variant
  CovUnits = DataItem("LH_COV_PHA", "COV_UNT_QTY", Cov)
End Property
Property Get CovOrinUnits(Cov As Integer) As Variant
   CovOrinUnits = DataItem("LH_COV_PHA", "OGN_SPC_UNT_QTY", Cov)
End Property
Property Get CovVPU(Cov As Integer) As Variant
  CovVPU = DataItem("LH_COV_PHA", "COV_VPU_AMT", Cov)
End Property
Property Get CovAmount(Cov As Integer) As Variant
  CovAmount = CovUnits(Cov) * CovVPU(Cov)
End Property
Property Get CovOrigAmount(Cov As Integer) As Variant
   CovOrigAmount = IIf(CovOrinUnits(Cov) = "Null", 0, CovOrinUnits(Cov)) * CovVPU(Cov)
End Property
Property Get CovIssueAge(Cov As Integer, Optional JtIndicator As Integer = 0) As Variant
If JtIndicator = 0 Then
    CovIssueAge = DataItem("LH_COV_PHA", "INS_ISS_AGE", Cov)
Else
    CovIssueAge = DataItem("LH_COV_PHA", "JNT_ISU_ISS_AGE", Cov)
End If
End Property
Property Get CovIssueDate(Cov As Integer) As Variant
  CovIssueDate = DataItem("LH_COV_PHA", "ISSUE_DT", Cov)
End Property
Property Get CovMaturityDate(Cov As Integer) As Variant
  CovMaturityDate = DataItem("LH_COV_PHA", "COV_MT_EXP_DT", Cov)
End Property
'Property Get CovOffsetMonths(cov As Integer) As Variant
''For post issue coverages, this calculates the number of months a coverage was added after the policy issue date.
''If subsequent coveage is added on anniversary this value is 0.
'   CovOffsetMonths = Month(CovIssueDate(cov)) - Month(CovIssueDate(1)) + IIf(Month(CovIssueDate(cov)) < Month(CovIssueDate(1)), 12, 0)
'End Property
Property Get CovFormNumber(Cov As Integer) As Variant
  CovFormNumber = DataItem("LH_COV_PHA", "POL_FRM_NBR", Cov)
End Property
Property Get CovPlancode(Cov As Integer) As Variant
  CovPlancode = Application.WorksheetFunction.Trim(DataItem("LH_COV_PHA", "PLN_DES_SER_CD", Cov))
End Property
Property Get CovDuration(Cov As Integer) As Variant
  Dim CovAdjustedIssueDate As Date
  CovAdjustedIssueDate = DateSerial(Year(CovIssueDate(Cov)), Month(CovIssueDate(1)), Day(CovIssueDate(1)))
  CovDuration = CompletedDateParts("YYYY", CovIssueDate(0), CovAdjustedIssueDate) + 1
End Property
Property Get CovAgeCalcCode(Cov As Integer) As Variant
  CovAgeCalcCode = TranslateAgeCalculationRuleToDescription(DataItem("LH_COV_PHA", "AGE_CLC_RLE_CD", Cov))
End Property
Property Get CovProductLineCode(Cov As Integer) As Variant
  CovProductLineCode = DataItem("LH_COV_PHA", "PRD_LIN_TYP_CD", Cov)
End Property
Property Get CovMortalityTableCode(Cov As Integer) As Variant
  CovMortalityTableCode = DataItem("LH_COV_PHA", "MTL_FCT_TBL_CD", Cov)
End Property
Property Get CovPersonCode(Cov As Integer) As String
    CovPersonCode = DataItem("LH_COV_PHA", "PRS_CD", Cov)
End Property
Property Get CovPersonSequenceCode(Cov As Integer) As String
    CovPersonSequenceCode = DataItem("LH_COV_PHA", "PRS_SEQ_NBR", Cov)
End Property
Property Get CovQualified(Cov As Integer) As Boolean
    CovQualified = (CovPersonCode(Cov) = "00" Or CovPersonCode(Cov) = "40" Or CovPersonCode(Cov) = "50")
End Property
Property Get CovInsuredName(Cov As Integer) As String
CovInsuredName = ""
Dim x As Integer
For x = 1 To Me.PersonCount
    If Me.PersonCode(x) = CovPersonCode(Cov) And Me.PersonSequenceCode(x) = CovPersonSequenceCode(Cov) Then
        CovInsuredName = Me.PersonFirstName(x) & " " & Me.PersonLastName(x)
        Exit For
    End If
Next
End Property
Property Get TotalSpecifiedAmount() As Variant
Dim Cov As Integer
Dim tempValue As Double
tempValue = 0
 For Cov = 1 To CovCount
   If CovPlancode(Cov) = CovPlancode(1) Then tempValue = tempValue + CovAmount(Cov)
 Next
TotalSpecifiedAmount = tempValue
End Property
Property Get TotalOrinSpecifiedAmount() As Variant
Dim Cov As Integer
Dim tempValue As Double
tempValue = 0
 For Cov = 1 To CovCount
   If CovPlancode(Cov) = CovPlancode(1) Then tempValue = tempValue + CovOrigAmount(Cov)
 Next
TotalOrinSpecifiedAmount = tempValue
End Property
Property Get CovETITable(Cov As Integer)
  CovETITable = DataItem("LH_COV_PHA", "NSP_EI_TBL_CD", Cov)
End Property
Property Get CovRPUTable(Cov As Integer)
  CovRPUTable = DataItem("LH_COV_PHA", "NSP_RPU_TBL_CD", Cov)
End Property
Property Get CovNFOIntRate(Cov As Integer)
  CovNFOIntRate = DataItem("LH_COV_PHA", "NSP_ITS_RT", Cov)
End Property
Property Get CovAPU(Cov As Integer)
  CovAPU = DataItem("LH_COV_PHA", "ANN_PRM_UNT_AMT", Cov)
End Property
Property Get CalcFunctionCode(Cov As Integer)
  CalcFunctionCode = DataItem("LH_COV_PHA", "MTL_FUN_CD", Cov)
End Property
Property Get CovLowDuration(Cov As Integer)
  CovLowDuration = IfEmpty(DataItem("LH_COV_PHA", "LOW_DUR_PER", Cov), 0)
End Property
Property Get CovCVAmount0(Cov As Integer)
 'This is the cash value as of the CovLowDuration
  CovCVAmount0 = IfEmpty(DataItem("LH_COV_PHA", "LOW_DUR_CSV_AMT", Cov), 0)
End Property
Property Get CovCVAmount1(Cov As Integer)
  CovCVAmount1 = IfEmpty(DataItem("LH_COV_PHA", "LOW_DUR_1_CSV_AMT", Cov), 0)
End Property
Property Get CovCVAmount2(Cov As Integer)
  CovCVAmount2 = IfEmpty(DataItem("LH_COV_PHA", "LOW_DUR_2_CSV_AMT", Cov), 0)
End Property
Property Get CovCVAmount3(Cov As Integer)
  CovCVAmount3 = IfEmpty(DataItem("LH_COV_PHA", "LOW_DUR_3_CSV_AMT", Cov), 0)
End Property
Property Get CovNSPRate0(Cov As Integer)
'This is the NSP as the CovLowDuraiton
  CovNSPRate0 = IfEmpty(DataItem("LH_COV_PHA", "LOW_DUR_NSP_AMT", Cov), 0)
End Property
Property Get CovNSPRate1(Cov As Integer)
  CovNSPRate1 = IfEmpty(DataItem("LH_COV_PHA", "LOW_DUR_1_NSP_AMT", Cov), 0)
End Property
Property Get CovNSPRate2(Cov As Integer)
  CovNSPRate2 = IfEmpty(DataItem("LH_COV_PHA", "LOW_DUR_2_NSP_AMT", Cov), 0)
End Property
Property Get CovAccEliminationPeriodCode(Cov As Integer) As String
    'Accident Elimination Period Code
    CovAccEliminationPeriodCode = IfEmpty(DataItem("LH_COV_PHA", "AH_ACC_ELM_PER_CD", Cov), "")
End Property
Property Get CovAccBenefitPeriodCode(Cov As Integer)
    'Accident Benefit Period Code
    CovAccBenefitPeriodCode = IfEmpty(DataItem("LH_COV_PHA", "AH_ACC_BNF_PER_CD", Cov), "")
End Property
Property Get CovSicEliminationPeriodCode(Cov As Integer)
    'Sickness Elimination Period Code
    CovSicEliminationPeriodCode = IfEmpty(DataItem("LH_COV_PHA", "AH_SIC_ELM_PER_CD", Cov), "")
End Property
Property Get CovSicBenefitPeriodCode(Cov As Integer)
    'Sickness Benefit Period Code
    CovSicBenefitPeriodCode = IfEmpty(DataItem("LH_COV_PHA", "AH_SIC_BNF_PER_CD", Cov), "")
End Property
Property Get CovNextChangeDate(Cov As Integer)
    'If the cov has terminated, this date is the termination date
    CovNextChangeDate = IfEmpty(DataItem("LH_COV_PHA", "NXT_CHG_DT", Cov), "")
End Property
Property Get CovCeaseDate(Cov As Integer)
'If the cov has already terminated then this date is the termination date, otherwise its the MaturityDate
If CovStatus(index) = "0" Then
    tempValue = CovNextChangeDate(Cov)
Else
    tempValue = CovMaturityDate(Cov)
End If
CovCeaseDate = tempValue
End Property

'====================================================================================================================================================================================
'LH_COV_SKIPPED_PER
'====================================================================================================================================================================================
Property Get SkippedReinCount()
  SkippedReinCount = DataItemCount("LH_COV_SKIPPED_PER", "TCH_POL_ID")
End Property
Property Get SkippedReinPolicyMonthsTerminated()
Dim x As Integer
Dim subtotal As Integer
If Me.SkippedReinCount = 0 Then
    subtotal = 0
Else
    For x = 1 To SkippedReinCount
        lapdt = SkippedReinLapseDate(x)
        reindt = SkippedReinReinstatementDate(x)
        monthcount = CompletedDateParts("m", lapdt, reindt)
        subtotal = subtotal + monthcount
    Next
End If
SkippedReinPolicyMonthsTerminated = subtotal
End Property
Property Get SkippedReinLapseDate(index As Integer) As Date
  SkippedReinLapseDate = DataItem("LH_COV_SKIPPED_PER", "LAP_DT", index)
End Property
Property Get SkippedReinReinstatementDate(index As Integer) As Date
  SkippedReinReinstatementDate = DataItem("LH_COV_SKIPPED_PER", "REN_DT", index)
End Property



'====================================================================================================================================================================================
'LH_POL_TARGET
'====================================================================================================================================================================================
Property Get NSP_Base()
Dim x As Integer
   For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
     If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "NS" Then
       NSP_Base = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
       Exit Property
     End If
   Next

End Property
Property Get NSP_Other()
Dim x As Integer
   For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
     If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "NT" Then
       NSP_Other = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
       Exit Property
     End If
   Next
End Property
Property Get MTP()
Dim x As Integer
   For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
     If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "MT" Then
       MTP = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
       Exit Property
     End If
   Next
End Property
Property Get AccumMTP()
AccumMTP = 0
Dim x As Integer
   For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
     If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "MA" Then
       AccumMTP = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
       Exit Property
     End If
   Next
End Property
Property Get MAPDate()
MAPDate = 0
Dim x As Integer
   For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
     If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "MA" Then
       MAPDate = DataItem("LH_POL_TARGET", "TAR_DT", x)
       Exit Property
     End If
   Next
End Property
Property Get AccumGLP()
Dim x As Integer
   For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
     If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "TA" Then
       AccumGLP = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
       Exit Property
     End If
   Next
End Property
Property Get PLT()
Dim x As Integer, TargetType As String
   For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
     TargetType = DataItem("LH_POL_TARGET", "TAR_TYP_CD", x)
     If TargetType = "LT" Then
       PLT = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
       Exit Property
     End If
   Next
End Property
Property Get GAV() As Variant
Dim x As Integer
   For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
     If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "IX" Then
       GAV = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
       Exit Property
     End If
   Next
End Property
Property Get DialToPrem() As Variant
Dim x As Integer
   For x = 1 To DataItemCount("LH_POL_TARGET", "TAR_TYP_CD")
     If DataItem("LH_POL_TARGET", "TAR_TYP_CD", x) = "DT" Then
       DialToPrem = DataItem("LH_POL_TARGET", "TAR_PRM_AMT", x)
       Exit Property
     End If
   Next
End Property
'====================================================================================================================================================================================
'LH_SPM_BNF
'====================================================================================================================================================================================
Public Function GetBenIndex(strTypeSubType As String) As Integer
Dim xIndex As Integer
Dim TargetIndex As Integer
TargetIndex = -1
For xIndex = 0 To BenCount
 If BenPlancode(xIndex) = strTypeSubType Then TargetIndex = xIndex
Next
GetBenIndex = TargetIndex
End Function


'Property Get BenRenewalIndicator(BenefitIndex As Integer) As Variant
'   BenRenewalIndicator = DataItem("LH_SPM_BNF", "",BenefitIndex)
'End Property

Property Get BenRenewalIndicator(BenefitIndex As Integer) As Variant
   BenRenewalIndicator = DataItem("LH_SPM_BNF", "RNL_RT_IND", BenefitIndex)
End Property
Property Get BenValueByName(FieldName As String, Optional index As Integer = 1)
    Dim tempValue As Variant
    Select Case FieldName
        Case "Name": tempValue = BenType(index)
        Case "Plancode": tempValue = BenPlancode(index)
        Case "FormNumber": tempValue = Me.BenFormNumber(index)
        Case "IssueDate": tempValue = BenIssueDate(index)
        Case "CeaseDate": tempValue = BenCeaseDate(index)
        Case "OriginalCeaseDate": tempValue = BenOriginalCeaseDate(index)
        Case "Amount": tempValue = BenAmount(index)
        Case "IssueAge": tempValue = BenIssueAge(index)
        Case "Rateclass": tempValue = BenRateclass(index)
        Case "RatingFactor": tempValue = BenRatingFactor(index)
    End Select
    BenValueByName = tempValue
End Property
Property Get BenRatingFactor(BenefitIndex As Integer) As Variant
   BenRatingFactor = DataItem("LH_SPM_BNF", "BNF_RT_FCT", BenefitIndex)
End Property
Property Get BenCOIRate(BenefitIndex As Integer) As Double
   BenCOIRate = DataItem("LH_SPM_BNF", "BNF_ANN_PPU_AMT", BenefitIndex)
End Property
Property Get BenUnits(BenefitIndex As Integer)
   BenUnits = DataItem("LH_SPM_BNF", "BNF_UNT_QTY", BenefitIndex)
End Property
Property Get BenVPU(BenefitIndex As Integer)
   BenVPU = DataItem("LH_SPM_BNF", "BNF_VPU_AMT", BenefitIndex)
End Property
Property Get BenAmount(BenefitIndex As Integer)
    BenAmount = BenUnits(BenefitIndex) * BenVPU(BenefitIndex)
End Property
Property Get BenTypeCode(BenefitIndex As Integer) As String
  BenTypeCode = Left(BenPlancode(BenefitIndex), 1)
End Property
Property Get BenSubTypeCode(BenefitIndex As Integer) As String
  BenSubTypeCode = Mid(BenPlancode(BenefitIndex), 2, 1)
End Property
Property Get BenType(BenefitIndex As Integer) As String
  BenType = Me.TranslateBenefitTypeToText(BenTypeCode(BenefitIndex), BenSubTypeCode(BenefitIndex))
End Property
Property Get BenIssueAge(BenefitIndex As Integer)
   BenIssueAge = DataItem("LH_SPM_BNF", "BNF_ISS_AGE", BenefitIndex)
End Property
Property Get BenIssueDate(BenefitIndex As Integer)
   BenIssueDate = DataItem("LH_SPM_BNF", "BNF_ISS_DT", BenefitIndex)
End Property
Property Get BenCeaseDate(BenefitIndex As Integer)
   BenCeaseDate = DataItem("LH_SPM_BNF", "BNF_CEA_DT", BenefitIndex)
End Property
Property Get BenOriginalCeaseDate(BenefitIndex As Integer)
   BenOriginalCeaseDate = DataItem("LH_SPM_BNF", "BNF_OGN_CEA_DT", BenefitIndex)
End Property
Property Get BenFormNumber(BenefitIndex As Integer)
   BenFormNumber = DataItem("LH_SPM_BNF", "BNF_FRM_NBR", BenefitIndex)
End Property
Property Get BenRateclass(BenefitIndex As Integer)
    Dim RenewalIndex As Integer
    RenewalIndex = BenRenewalIndex(BenefitIndex)
    If RenewalIndex = -1 Then
        BenRateclass = 0
    Else
        BenRateclass = RenewalBenRateclass(BenRenewalIndex(BenefitIndex))
    End If
End Property
Property Get BenPlancode(BenefitIndex As Integer)
   BenPlancode = DataItem("LH_SPM_BNF", "SPM_BNF_TYP_CD", BenefitIndex) & DataItem("LH_SPM_BNF", "SPM_BNF_SBY_CD", BenefitIndex)
End Property
Property Get BenCovPhase(BenefitIndex As Integer)
    BenCovPhase = DataItem("LH_SPM_BNF", "COV_PHA_NBR", BenefitIndex)
End Property
Property Get BenCount()
   BenCount = DataItemCount("LH_SPM_BNF", "SPM_BNF_TYP_CD")
End Property



'====================================================================================================================================================================================
'LH_COV_INS_GDL_PRM
'====================================================================================================================================================================================
Property Get GLP() As Variant
Dim x As Integer, TargetType As String, TargetValue As Variant
   For x = 1 To DataItemCount("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD")
     TargetType = DataItem("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD", x)
     If TargetType = "A" Then
       GLP = DataItem("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", x)
       Exit Property
     End If
   Next
End Property
Property Get GSP() As Variant
Dim x As Integer, TargetType As String, TargetValue As Variant
   For x = 1 To DataItemCount("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD")
     TargetType = DataItem("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD", x)
     If TargetType = "S" Then
       GSP = DataItem("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", x)
       Exit Property
     End If
   Next
End Property


'====================================================================================================================================================================================
'LH_POL_MVRY_VAL
'====================================================================================================================================================================================
Property Get MVAV(Optional DtIndex As Integer = 1)
    MVAV = DataItem("LH_POL_MVRY_VAL", "CSV_AMT", DtIndex)
End Property
Property Get MVCOICharge(Optional DtIndex As Integer = 1)
    MVCOICharge = IfEmpty(DataItem("LH_POL_MVRY_VAL", "CINS_AMT", DtIndex), 0)
End Property
Property Get MVExpChrg(Optional DtIndex As Integer = 1)
    MVExpChrg = IfEmpty(DataItem("LH_POL_MVRY_VAL", "EXP_CRG_AMT", DtIndex), 0)
End Property
Property Get MVOtherChrg(Optional DtIndex As Integer = 1)
    MVOtherChrg = IfEmpty(DataItem("LH_POL_MVRY_VAL", "OTH_PRM_AMT", DtIndex), 0)
End Property
Property Get MVMonthlyDeduction(Optional DtIndex As Integer = 1)
    MVMonthlyDeduction = MVCOICharge(DtIndex) + MVExpChrg(DtIndex) + MVOtherChrg(DtIndex)
End Property
Property Get MVCurrentInterest(Optional DtIndex As Integer = 1) As Double
    MVCurrentInterest = IfEmpty(DataItem("LH_POL_MVRY_VAL", "TOT_CRE_ITS_AMT", DtIndex), 0)
End Property
Property Get MVGuaranteedInterest(Optional DtIndex As Integer = 1) As Double
    MVGuaranteedInterest = IfEmpty(DataItem("LH_POL_MVRY_VAL", "GUA_RT_ERN_ITS_AMT", DtIndex), 0)
End Property
Property Get MVCount()
    MVCount = DataItemCount("LH_POL_MVRY_VAL", "MVRY_DT")
End Property
Property Get MVDate(Optional DtIndex As Integer = 1)
    MVDate = DataItem("LH_POL_MVRY_VAL", "MVRY_DT", DtIndex)
End Property
Property Get MVPolicyYear(Optional DtIndex As Integer = 1)
    MVPolicyYear = DataItem("LH_POL_MVRY_VAL", "POL_DUR_NBR", DtIndex)
End Property
Property Get MVMonthOfYear(Optional DtIndex As Integer = 1)
Dim ValMonth As Date, IssueMonth As Date, mth As Integer
  ValMonth = Month(MVDate(DtIndex))
  IssueMonth = Month(Me.CovIssueDate(1))
  'Determine month of the year for valuation date.  This assumes all valuation dates are on monthliversary
  mth = Abs(IssueMonth - ValMonth)
  If IssueMonth > ValMonth Then mth = 12 - mth
  mth = mth + 1
  MVMonthOfYear = mth
End Property
Property Get MVNAR(Optional DtIndex As Integer = 1)
 MVNAR = IfEmpty(DataItem("LH_POL_MVRY_VAL", "NAR_AMT", DtIndex), 0)
End Property


  
'====================================================================================================================================================================================
'LH_COV_INS_RNL_RT
'====================================================================================================================================================================================
Public Function CovRenewalIndex(Cov As Integer, Optional RtType As String = "C", Optional JtIndicator As Integer = 0) As Integer
Dim index As Integer, x As Integer
index = -1
For x = 1 To RenewalCovCount
      If DataItem("LH_COV_INS_RNL_RT", "PRM_RT_TYP_CD", x) = RtType And _
         DataItem("LH_COV_INS_RNL_RT", "COV_PHA_NBR", x) = CovPhase(Cov) And _
         DataItem("LH_COV_INS_RNL_RT", "JT_INS_IND", x) = JtIndicator Then
        
         index = x
      End If
Next
CovRenewalIndex = index
End Function

Property Get RenewalCovCount()
  RenewalCovCount = DataItemCount("LH_COV_INS_RNL_RT", "COV_PHA_NBR")
End Property
 Property Get RenewalCovPhaseCode(Optional Cov As Integer = 1, Optional RtType As String = "C")
  
 Dim RtIndex As Integer
 RtIndex = CovRenewalIndex(Cov, RtType)
 If RtIndex < 0 Then Exit Property
 
 RenewalCovPhaseCode = DataItem("LH_COV_INS_RNL_RT", "COV_PHA_NBR", RtIndex)
End Property
 Property Get RenewalCovRateclass(Optional Cov As Integer = 1, Optional RtType As String = "C", Optional JtIndicator As Integer = 0)
 
 Dim RtIndex As Integer
 RtIndex = CovRenewalIndex(Cov, RtType, JtIndicator)
 If RtIndex < 0 Then Exit Property
 
 RenewalCovRateclass = DataItem("LH_COV_INS_RNL_RT", "RT_CLS_CD", RtIndex)
 
End Property
 Property Get RenewalCovRate(Optional Cov As Integer = 1, Optional RtType As String = "C")
 
 Dim RtIndex As Integer
 RtIndex = CovRenewalIndex(Cov, RtType)
 If RtIndex < 0 Then Exit Property
    
  RenewalCovRate = DataItem("LH_COV_INS_RNL_RT", "RNL_RT").NullZ(RtIndex, 0)
End Property
 Property Get RenewalCovBandCode(Optional Cov As Integer = 1, Optional RtType As String = "C")
  
 Dim RtIndex As Integer
 RtIndex = CovRenewalIndex(Cov, RtType)
 If RtIndex < 0 Then Exit Property
 
 RenewalCovBandCode = DataItem("LH_COV_INS_RNL_RT", "RT_BAN_CD", RtIndex)
End Property
 Property Get RenewalCovPremiumTypeCode(Optional Cov As Integer = 1, Optional RtType As String = "C")
  
 Dim RtIndex As Integer
 RtIndex = CovRenewalIndex(Cov, RtType)
 If RtIndex < 0 Then Exit Property
 
 RenewalCovPremiumTypeCode = DataItem("LH_COV_INS_RNL_RT", "PRM_RT_TYP_CD", RtIndex)
End Property
 Property Get RenewalCovSexCode(Optional Cov As Integer = 1, Optional RtType As String = "C", Optional JtIndicator As Integer = 0)
  
 Dim RtIndex As Integer
 RtIndex = CovRenewalIndex(Cov, RtType, JtIndicator)
 If RtIndex < 0 Then Exit Property
 
 RenewalCovSexCode = DataItem("LH_COV_INS_RNL_RT", "RT_SEX_CD", RtIndex)
End Property



'====================================================================================================================================================================================
'LH_BNF_INS_RNL_RT
'====================================================================================================================================================================================
Public Function BenRenewalIndex(BenIndex As Integer, Optional RtType As String = "") As Integer
    'Returns the index from the LH_BNF_INS_RNL_RT table that corresponds to the BenIndex from the LH_SPM_BNF table
    Dim index As Integer, x As Integer
    index = -1
    For x = 1 To RenewalBenCount
        If RenewalBenSubTypeCode(x) = BenSubTypeCode(BenIndex) And RenewalBenTypeCode(x) = BenTypeCode(BenIndex) Then
        'If RtType is not specified then use then only Type and Subtype need to match.  But if RtType is specified then
        'Premium Code needs to match the RtType
            If RtType <> "" Then
                If RenewalBenPremiumTypeCode(x) = RtType Then index = x
            Else
                index = x
            End If
        End If
    Next
    BenRenewalIndex = index
End Function
Property Get RenewalBenCount() As Integer
    RenewalBenCount = DataItemCount("LH_BNF_INS_RNL_RT", "SPM_BNF_TYP_CD")
End Property
Property Get RenewalBenPremiumTypeCode(Optional BenefitIndex As Integer = 1)
    RenewalBenPremiumTypeCode = DataItem("LH_BNF_INS_RNL_RT", "PRM_RT_TYP_CD", BenefitIndex)
End Property
Property Get RenewalBenTypeCode(Optional BenefitIndex As Integer = 1)
    RenewalBenTypeCode = DataItem("LH_BNF_INS_RNL_RT", "SPM_BNF_TYP_CD", BenefitIndex)
End Property
Property Get RenewalBenSubTypeCode(Optional BenefitIndex As Integer = 1)
    RenewalBenSubTypeCode = DataItem("LH_BNF_INS_RNL_RT", "SPM_BNF_SBY_CD", BenefitIndex)
End Property
Property Get RenewalBenRateclass(Optional BenefitIndex As Integer = 1)
    RenewalBenRateclass = DataItem("LH_BNF_INS_RNL_RT", "RT_CLS_CD", BenefitIndex)
End Property
Property Get RenewalBenSex(Optional BenefitIndex As Integer = 1)
    RenewalBenSex = DataItem("LH_BNF_INS_RNL_RT", "RT_SEX_CD", BenefitIndex)
End Property
Property Get RenewalBenBand(Optional BenefitIndex As Integer = 1)
    RenewalBenBand = DataItem("LH_BNF_INS_RNL_RT", "RT_BAN_CD", BenefitIndex)
End Property
Property Get RenewalBenRate(Optional BenefitIndex As Integer = 1)
    RenewalBenRate = IfEmpty(DataItem("LH_BNF_INS_RNL_RT", "RNL_RT", BenefitIndex), 0)
End Property
     

'====================================================================================================================================================================================
'LH_SST_XTR_RNL_RT
'====================================================================================================================================================================================
Property Get RenewalSubCount() As Integer
    RenewalSubCount = DataItemCount("LH_BNF_INS_RNL_RT", "COV_PHA_NBR")
End Property
Property Get RenewalSubPhaseCode(Optional Cov As Integer = 1)
    RenewalSubPhaseCode = DataItem("LH_BNF_INS_RNL_RT", "COV_PHA_NBR", Cov)
End Property
Property Get RenewalSubPremiumTypeCode(Optional Cov As Integer = 1)
    RenewalSubPremiumTypeCode = IfEmpty(DataItem("LH_BNF_INS_RNL_RT", "PRM_RT_TYP_CD", Cov), "")
End Property
Property Get RenewalSubTablePercent(Optional Cov As Integer = 1)
    RenewalSubTablePercent = IfEmpty(DataItem("LH_BNF_INS_RNL_RT", "SST_XTR_PCT", Cov), 0)
End Property
Property Get RenewalSubTableCode(Optional Cov As Integer = 1)
    RenewalSubTableCode = IfEmpty(DataItem("LH_BNF_INS_RNL_RT", "SST_XTR_RT_TBL_CD", Cov), "")
End Property
Property Get RenewalSubFlatAmount(Optional Cov As Integer = 1)
    RenewalSubFlatAmount = IfEmpty(DataItem("LH_BNF_INS_RNL_RT", "SST_XTR_UNT_AMT", Cov), 0)
End Property

  


'====================================================================================================================================================================================
'LH_NON_TRD_POL
'====================================================================================================================================================================================
Property Get PreferredLoansAvailable() As Integer
  Dim tempValue
  tempValue = IfEmpty(DataItem("LH_NON_TRD_POL", "PRF_LN_OPT_CD", 1), "0")
  PreferredLoansAvailable = IIf(tempValue = "0", 0, 1)
End Property
Property Get NonTrad_RegLoanCreditCode()
  NonTrad_RegLoanCreditCode = IfEmpty(DataItem("LH_NON_TRD_POL", "LN_CRE_ITS_RT_CD", 1), "")
End Property
Property Get NonTrad_RegLoanCreditRate()
  NonTrad_RegLoanCreditRate = IfEmpty(DataItem("LH_NON_TRD_POL", "LN_CRE_ITS_RT", 1), 0)
End Property
Property Get NonTrad_RegLoanChargeRate()
  NonTrad_RegLoanChargeRate = Me.PolicyLoanChargeRate
End Property
Property Get NonTrad_PrefLoanCreditCode()
  NonTrad_PrefLoanCreditCode = IfEmpty(DataItem("LH_NON_TRD_POL", "PRF_LN_ITS_CRE_CD", 1), "")
End Property
Property Get NonTrad_PrefLoanCreditRate()
  NonTrad_PrefLoanCreditRate = IfEmpty(DataItem("LH_NON_TRD_POL", "PRF_LN_ITS_CRE_RT", 1), 0)
End Property
Property Get NonTrad_PrefLoanChargeRate()
  NonTrad_PrefLoanChargeRate = IfEmpty(DataItem("LH_NON_TRD_POL", "PRF_LN_ITS_CRG_RT", 1), 0)
End Property
Property Get NonTrad_CorridorPercent()
  NonTrad_CorridorPercent = DataItem("LH_NON_TRD_POL", "CDR_PCT").NullZ(1, 100)
End Property
Property Get NonTrad_GracePeriodEndingDate()
  NonTrad_GracePeriodEndingDate = IfEmpty(DataItem("LH_NON_TRD_POL", "GRA_PER_EXP_DT", 1), 0)
End Property
Property Get NonTrad_GraceRuleCode()
 NonTrad_GraceRuleCode = IfEmpty(DataItem("LH_NON_TRD_POL", "GRA_THD_RLE_CD", 1), "")
End Property
Property Get NonTrad_GAVInidicator()
 NonTrad_GAVInidicator = IfEmpty(DataItem("LH_NON_TRD_POL", "PLVL_GAV_RULE", 1), "")
End Property
Property Get GuaranteedInterestRate()
 GuaranteedInterestRate = IfEmpty(DataItem("LH_NON_TRD_POL", "POL_GUA_ITS_RT", 1), 0)
End Property
Property Get TEFRA_DEFRA()
Dim tempValue As Variant
tempValue = IfEmpty(DataItem("LH_NON_TRD_POL", "TFDF_CD", 1), "")
   Select Case tempValue
     Case "1": TEFRA_DEFRA = "TEFRA"
     Case "2": TEFRA_DEFRA = "DEFRA"
     Case "3": TEFRA_DEFRA = "DEFRA"
     Case "5": TEFRA_DEFRA = "DEFRA"
     Case Else: TEFRA_DEFRA = tempValue
   End Select
End Property
Property Get GPT_CVAT()
Dim tempValue As Variant
tempValue = IfEmpty(DataItem("LH_NON_TRD_POL", "TFDF_CD", 1), "")
Select Case tempValue
     Case "1": GPT_CVAT = "GPT"   'Plan is GPT
     Case "2": GPT_CVAT = "GPT"  'Plan is GPT
     Case "3": GPT_CVAT = "CVAT" 'Plan is CVAT
     Case "4": GPT_CVAT = "GPT" 'GPT selected on app
     Case "5": GPT_CVAT = "CVAT" 'CVAT selected on app
     Case Else: GPT_CVAT = tempValue
   End Select
End Property
Property Get DBOptionCode()
 DBOptionCode = IfEmpty(DataItem("LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD", 1), "")
End Property
Property Get DBOption()
 DBOption = Me.TranslateDBOptionCodeToText(DBOptionCode)
End Property

Property Get DBOptionAmount()
Dim tempAmt As Double
If DataItem("LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD").FieldNotFound Then
    DBOptionAmount = 0
    Exit Property
End If
Select Case DataItem("LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD")
    Case "1": tempAmt = 0
    Case "2": tempAmt = MVAV(1)
    Case "3": tempAmt = TotalRegularPremium + TotalAdditionalPremium
    Case Else: tempAmt = 0
End Select
DBOptionAmount = tempAmt
End Property



'====================================================================================================================================================================================
'LH_POL_TOTALS
'====================================================================================================================================================================================
Property Get PolicyTotalsCount()
   PolicyTotalsCount = DataItemCount("LH_POL_TOTALS", "TOT_REG_PRM_AMT")
End Property
Property Get TotalRegularPremium()
   TotalRegularPremium = IfEmpty(DataItem("LH_POL_TOTALS", "TOT_REG_PRM_AMT", 1), 0)
End Property
Property Get TotalAdditionalPremium()
   TotalAdditionalPremium = IfEmpty(DataItem("LH_POL_TOTALS", "TOT_ADD_PRM_AMT", 1), 0)
End Property
Property Get CostBasis()
   CostBasis = IfEmpty(DataItem("LH_POL_TOTALS", "POL_CST_BSS_AMT", 1), 0)
End Property
Property Get PremiumTD()
  PremiumTD = TotalRegularPremium + TotalAdditionalPremium
End Property
Property Get AccumWithdrawals() As Double
   AccumWithdrawals = IfEmpty(DataItem("LH_POL_TOTALS", "TOT_WTD_AMT", 1), 0)
End Property


'====================================================================================================================================================================================
'LH_POL_YR_TOT
'====================================================================================================================================================================================
Property Get PolicyTotalsYTDCount()
   PolicyTotalsYTDCount = DataItemCount("LH_POL_YR_TOT", "YTD_TOT_PMT_AMT")
End Property
Property Get TotalRegularPremiumYTD()
   'These totals are stored by Policy year.  This will return the totals from the last row (current year)
   TotalRegularPremiumYTD = IfEmpty(DataItem("LH_POL_YR_TOT", "YTD_TOT_PMT_AMT", PolicyTotalsYTDCount), 0)
End Property
Property Get TotalAdditionalPremiumYTD()
   'These totals are stored by Policy year.  This will return the totals from the last row (current year)
   TotalAdditionalPremiumYTD = IfEmpty(DataItem("LH_POL_YR_TOT", "YTD_ADD_PRM_AMT", PolicyTotalsYTDCount), 0)
End Property
Property Get PremiumYTD()
   PremiumYTD = TotalRegularPremiumYTD + TotalAdditionalPremiumYTD
End Property






'====================================================================================================================================================================================
'LH_CSH_VAL_LOAN
'====================================================================================================================================================================================

Property Get TradLoanCount() As Integer
  TradLoanCount = DataItemCount("LH_CSH_VAL_LOAN", "LN_PRI_AMT")
End Property
Property Get TradLoanEffectiveDate(index As Integer)
  TradLoanEffectiveDate = DataItem("LH_CSH_VAL_LOAN", "MVRY_DT", index)
End Property
Property Get TradLoanPrefIndicator(index As Integer) As String
  TradLoanPrefIndicator = DataItem("LH_CSH_VAL_LOAN", "PRF_LN_IND", index)
End Property
Property Get TradLoanAccuredInt(index As Integer) As Double
  TradLoanAccuredInt = DataItem("LH_CSH_VAL_LOAN", "POL_LN_ITS_AMT", index)
End Property
Property Get TradLoanLoanPrinciple(index As Integer) As Double
  TradLoanLoanPrinciple = DataItem("LH_CSH_VAL_LOAN", "LN_PRI_AMT", index)
End Property
Property Get TradLoanIntType(index As Integer) As Double
  TradLoanIntType = DataItem("LH_CSH_VAL_LOAN", "LN_ITS_PBL_TYP_CD", index)
End Property
Property Get TradLoanInterestStatusCode(index As Integer) As String
  TradLoanInterestStatusCode = DataItem("LH_CSH_VAL_LOAN", "LN_ITS_AMT_TYP_CD", index)
End Property
Property Get TradLoanChargeRate(index As Integer) As Double
  TradLoanChargeRate = DataItem("LH_CSH_VAL_LOAN", "LN_CRG_ITS_RT", index)
End Property
Property Get TotalTradPrefLnPrinciple()
Dim x As Integer, subtotal As Double
subtotal = 0
For x = 1 To TradLoanCount
 If TradLoanEffectiveDate(x) = "12/31/9999" And TradLoanPrefIndicator(x) = 1 Then subtotal = subtotal + TradLoanLoanPrinciple(x)
Next
TotalTradPrefLnPrinciple = subtotal
End Property
Property Get TotalTradPrefLnAccrued()
Dim x As Integer, subtotal As Double
subtotal = 0
For x = 1 To TradLoanCount
 If TradLoanEffectiveDate(x) = "12/31/9999" And TradLoanPrefIndicator(x) = 1 Then subtotal = subtotal + TradLoanAccuredInt(x)
Next
TotalTradPrefLnAccrued = subtotal
End Property
Property Get TotalTradRegLnPrinciple()
Dim x As Integer, subtotal As Double
subtotal = 0
For x = 1 To TradLoanCount
 If TradLoanEffectiveDate(x) = "12/31/9999" And TradLoanPrefIndicator(x) = 0 Then subtotal = subtotal + TradLoanLoanPrinciple(x)
Next
TotalTradRegLnPrinciple = subtotal
End Property
Property Get TotalTradRegLnAccrued()
Dim x As Integer, subtotal As Double
subtotal = 0
For x = 1 To TradLoanCount
 If TradLoanEffectiveDate(x) = "12/31/9999" And TradLoanPrefIndicator(x) = 0 Then subtotal = subtotal + TradLoanAccuredInt(x)
Next
TotalTradRegLnAccrued = subtotal
End Property



'====================================================================================================================================================================================
'LH_LN_RPY_TRM  (loan repayment billing)
'====================================================================================================================================================================================
Property Get LoanRepayCount() As Integer
  LoanRepayCount = DataItemCount("LH_LN_RPY_TRM", "CK_CMP_CD")
End Property
Property Get LoanRepayAmount()
  LoanRepayAmount = DataItem("LH_LN_RPY_TRM", "LN_RPY_AMT")
End Property
Property Get LoanRepayYears()
'Contains the number of years requested for loan repayment
    LoanRepayYears = DataItem("LH_LN_RPY_TRM", "LN_RPY_TRM")
End Property
Property Get LoanRepayFrequency()
'Contains the billing frequency for loan repayments.
  LoanRepayFrequency = DataItem("LH_LN_RPY_TRM", "LN_BIL_FQY_PER")
End Property
Property Get LoanBillToDate()
'Indicates the effective date that the loan is considered in default.
  LoanBillToDate = DataItem("LH_LN_RPY_TRM", "LN_BIL_TO_DT")
End Property
Property Get LoanPaidToDate()
'Indicates the effective date that the loan is considered in default.
  LoanPaidToDate = DataItem("LH_LN_RPY_TRM", "LN_PAY_TO_DT")
End Property
Property Get LoanDefaultDate()
'Indicates the effective date that the loan is considered in default.
  LoanDefaultDate = DataItem("LH_LN_RPY_TRM", "LN_RPY_SUS_CEA_DT")
End Property
Property Get LoanLeaveOfAbsenceCode()
'Indicates whether the loan is in a leave of absence.
  LoanLeaveOfAbsenceCode = DataItem("LH_LN_RPY_TRM", "LN_RPY_SUS_IND")
End Property
Property Get LoanLeaveOfAbsenceMonths()
'Indicates the number of months the loan has been in leave of absence, not to exceed twelve months.
  LoanLeaveOfAbsenceMonths = DataItem("LH_LN_RPY_TRM", "LN_RPY_SUS_DUR")
End Property



'====================================================================================================================================================================================
'LH_FND_VAL_LOAN
'====================================================================================================================================================================================
Property Get LoanFundCount() As Integer
  LoanFundCount = DataItemCount("LH_FND_VAL_LOAN", "MVRY_DT")
End Property
Property Get LoanEffectiveDate(index As Integer)
  LoanEffectiveDate = DataItem("LH_FND_VAL_LOAN", "MVRY_DT", index)
End Property
Property Get LoanFundPhase(index As Integer)
  LoanFundPhase = DataItem("LH_FND_VAL_LOAN", "FND_VAL_PHA_NBR", index)
End Property
Property Get LoanFundPrefIndicator(index As Integer) As String
  LoanFundPrefIndicator = DataItem("LH_FND_VAL_LOAN", "PRF_LN_IND", index)
End Property
Property Get LoanFundID(index As Integer) As String
  LoanFundID = DataItem("LH_FND_VAL_LOAN", "FND_ID_CD", index)
End Property
Property Get LoanFundAccuredInt(index As Integer) As Double
  LoanFundAccuredInt = DataItem("LH_FND_VAL_LOAN", "POL_LN_ITS_AMT", index)
End Property
Property Get LoanFundPrinciple(index As Integer) As Double
  LoanFundPrinciple = DataItem("LH_FND_VAL_LOAN", "LN_PRI_AMT", index)
End Property
Property Get LoanFundInterestStatusCode(index As Integer) As String
  LoanFundInterestStatusCode = DataItem("LH_FND_VAL_LOAN", "LN_ITS_AMT_TYP_CD", index)
End Property
Property Get LoanFundChargeRate(index As Integer) As Double
  LoanFundChargeRate = DataItem("LH_FND_VAL_LOAN", "LN_CRG_ITS_RT", index)
End Property
Property Get LoanFundIntType(index As Integer) As Double
  LoanFundIntType = DataItem("LH_FND_VAL_LOAN", "LN_ITS_PBL_TYP_CD", index)
End Property
Property Get TotalFundVarLnAccrued()
Dim x As Integer, subtotal As Double
subtotal = 0
For x = 1 To LoanFundCount                                              'Interest is not Capitalized
 If LoanEffectiveDate(x) = "12/31/9999" And LoanFundID(x) = "LZ" And LoanFundInterestStatusCode(x) <> "1" Then subtotal = subtotal + LoanFundAccuredInt(x)
Next
TotalFundVarLnAccrued = subtotal
End Property
Property Get TotalFundVarLnPrinciple()
Dim x As Integer, subtotal As Double
subtotal = 0
For x = 1 To LoanFundCount
 If LoanEffectiveDate(x) = "12/31/9999" And LoanFundID(x) = "LZ" Then subtotal = subtotal + LoanFundPrinciple(x)
Next
TotalFundVarLnPrinciple = subtotal
End Property
Property Get TotalFundPrefLnPrinciple()
Dim x As Integer, subtotal As Double
subtotal = 0
For x = 1 To LoanFundCount
 If LoanEffectiveDate(x) = "12/31/9999" And LoanFundID(x) <> "LZ" And LoanFundPrefIndicator(x) = 1 Then subtotal = subtotal + LoanFundPrinciple(x)
Next
TotalFundPrefLnPrinciple = subtotal
End Property
Property Get TotalFundPrefLnAccrued()
Dim x As Integer, subtotal As Double
subtotal = 0
For x = 1 To LoanFundCount
 If LoanEffectiveDate(x) = "12/31/9999" And LoanFundID(x) <> "LZ" And LoanFundPrefIndicator(x) = 1 And LoanFundInterestStatusCode(x) <> "1" Then subtotal = subtotal + LoanFundAccuredInt(x)
Next
TotalFundPrefLnAccrued = subtotal
End Property
Property Get TotalFundRegLnPrinciple()
Dim x As Integer, subtotal As Double
subtotal = 0
For x = 1 To LoanFundCount
 If LoanEffectiveDate(x) = "12/31/9999" And LoanFundID(x) <> "LZ" And LoanFundPrefIndicator(x) = 0 Then subtotal = subtotal + LoanFundPrinciple(x)
Next
TotalFundRegLnPrinciple = subtotal
End Property
Property Get TotalFundRegLnAccrued()
Dim x As Integer, subtotal As Double
subtotal = 0
For x = 1 To LoanFundCount
 If LoanEffectiveDate(x) = "12/31/9999" And LoanFundID(x) <> "LZ" And LoanFundPrefIndicator(x) = 0 And LoanFundInterestStatusCode(x) <> "1" Then subtotal = subtotal + LoanFundAccuredInt(x)
Next
TotalFundRegLnAccrued = subtotal
End Property

Property Get LoanValuesDictionary() As Dictionary
 Dim dct As Dictionary
 Set dct = New Dictionary
 
 'Create dictionary by summing up loan principle across distinct FundIds only if the bucket is effective on the valuation date
 Dim x As Integer
 For x = 1 To LoanFundCount
    If LoanEffectiveDate(x) = "12/31/9999" Then
        dct(LoanFundID(x)) = dct(LoanFundID(x)) + LoanFundPrinciple(x)
    End If
 Next
   
 Set LoanValuesDictionary = dct
 Set dct = Nothing
 
End Property



'=================================================================================================================================================================================================================================================
'LOANS (ADV or TRAD)
'=================================================================================================================================================================================================================================================
Property Get TotalPrefLnPrinciple()
    Dim tempValue
    If Me.AdvancedProductIndicator = "1" Then
        tempValue = TotalFundPrefLnPrinciple
    Else
        tempValue = TotalTradPrefLnPrinciple
    End If
    TotalPrefLnPrinciple = tempValue
End Property
Property Get TotalPrefLnAccrued()
    Dim tempValue
    If Me.AdvancedProductIndicator = "1" Then
        tempValue = TotalFundPrefLnAccrued
    Else
        tempValue = TotalTradPrefLnAccrued
    End If
    TotalPrefLnAccrued = tempValue
End Property
Property Get TotalRegLnPrinciple()
    Dim tempValue
    If Me.AdvancedProductIndicator = "1" Then
        tempValue = TotalFundRegLnPrinciple
    Else
        tempValue = TotalTradRegLnPrinciple
    End If
    TotalRegLnPrinciple = tempValue
End Property
Property Get TotalRegLnAccrued()
    Dim tempValue
    If Me.AdvancedProductIndicator = "1" Then
        tempValue = TotalFundRegLnAccrued
    Else
        tempValue = TotalTradRegLnAccrued
    End If
    TotalRegLnAccrued = tempValue
End Property
Property Get TotalVarLnPrinciple()
    Dim tempValue
    If Me.AdvancedProductIndicator = "1" Then
        tempValue = Me.TotalFundVarLnPrinciple
    Else
        tempValue = Empty
    End If
    TotalVarLnPrinciple = tempValue
End Property
Property Get TotalVarLnAccrued()
    Dim tempValue
    If Me.AdvancedProductIndicator = "1" Then
        tempValue = Me.TotalFundVarLnAccrued
    Else
        tempValue = Empty
    End If
    TotalVarLnAccrued = tempValue
End Property
Property Get PolicyDebt()
    Dim tempValue
    If Me.AdvancedProductIndicator = "1" Then
        tempValue = TotalPrefLnPrinciple + TotalPrefLnAccrued + TotalRegLnPrinciple + TotalRegLnAccrued + TotalVarLnPrinciple + TotalVarLnAccrued
    Else
        tempValue = TotalRegLnPrinciple + TotalRegLnAccrued
    End If
    PolicyDebt = tempValue
End Property



'=================================================================================================================================================================================================================================================
'LH_COM_TARGET
'=================================================================================================================================================================================================================================================
Private Function ComTargetDictionary() As Dictionary


    If mCurrentPolicy("CommTargets") Is Nothing Then
        Dim dctComTargets As Dictionary
        Set dctComTargets = New Dictionary
        
        Dim CovCTPCount As Integer
        Dim CovCTP() As Variant
        Dim CovCTPhase() As Variant
        Dim CovCTDate() As Variant
        Dim CTP As Double
        
        CovCTPCount = 0
        If DataItemCount("LH_COM_TARGET", "TAR_TYP_CD") > 0 Then
            Dim x As Integer
            Dim TargetType As String
            Dim tempValue As Variant
   
            For x = 1 To DataItemCount("LH_COM_TARGET", "TAR_TYP_CD")
                TargetType = DataItem("LH_COM_TARGET", "TAR_TYP_CD", x)
                Select Case TargetType
                    Case "CT":  ReDim Preserve CovCTP(CovCTPCount)
                                ReDim Preserve CovCTPhase(CovCTPCount)
                                ReDim Preserve CovCTDate(CovCTPCount)
                                CovCTP(CovCTPCount) = IfEmpty(DataItem("LH_COM_TARGET", "TAR_PRM_AMT", x), 0)
                                CovCTPhase(CovCTPCount) = DataItem("LH_COM_TARGET", "AGT_COM_PHA_NBR", x)
                                CovCTDate(CovCTPCount) = DataItem("LH_COM_TARGET", "TAR_DT", x)
                                CTP = CTP + CovCTP(CovCTPCount)
                                CovCTPCount = CovCTPCount + 1
                End Select
            Next
        End If
        
        dctComTargets.Add "CovCTPCount", CovCTPCount
        dctComTargets.Add "CovCTP", CovCTP
        dctComTargets.Add "CovCTPhase", CovCTPhase
        dctComTargets.Add "CovCTDate", CovCTDate
        dctComTargets.Add "CTP", CTP
        Set mCurrentPolicy("CommTargets") = dctComTargets
        Set dctComTargets = Nothing
    End If
    Set ComTargetDictionary = mCurrentPolicy("CommTargets")
End Function
Property Get CTPCount() As Integer
    CTP = ComTargetDictionary("CTPCount")
End Property
Property Get CTP()
    CTP = ComTargetDictionary("CTP")
End Property
Property Get CovCTP(Optional Cov As Integer = 1)
    CovCTP = ComTargetDictionary("CovCTP")(Cov)
End Property
Property Get CovCTPhase(Optional Cov As Integer = 1)
    CovCTP = ComTargetDictionary("CovCTPhase")(Cov)
End Property
Property Get CovCTDate(Optional Cov As Integer = 1)
    CovCTP = ComTargetDictionary("CovCTDate")(Cov)
End Property




'====================================================================================================================================================================================
'LH_SST_XTR_CRG
'====================================================================================================================================================================================
Private Function ActiveSubstandards(Cov As Integer, TypeAbbr As String, Optional JtIndicator As Integer = 0) As Dictionary
'Returns a dictionary with all the active substandards for the specified coverage, substandard type (table or flat) and person code (primary insured or joint insured)

'Personcode is only needed to distinguish between primary and joint insured.  It is not used to identify as spouse, child or other insured rider
Dim PersonCode As String

If CovPlancode(Cov) = CovPlancode(1) Then
    If JtIndicator = 1 Then
        PersonCode = "01"
    Else
        PersonCode = "00"
    End If
Else
    PersonCode = "NA"
End If

Dim dct As Dictionary
Set dct = New Dictionary
Dim x As Integer, CurrentSubTypeCode, CurrentPhase, CurrentPersonCode, CurrentCeaseDate, CurrentAmount, CurrentAnnualFlat

For x = 1 To DataItemCount("LH_SST_XTR_CRG", "SST_XTR_TYP_CD")

    CurrentSubTypeCode = TranslateSubstandardTypeCode(DataItem("LH_SST_XTR_CRG", "SST_XTR_TYP_CD", x)) 'T=Table, F=Flat
    CurrentPhase = DataItem("LH_SST_XTR_CRG", "COV_PHA_NBR", x)
    CurrentPersonCode = DataItem("LH_SST_XTR_CRG", "PRS_CD", x)
    CurrentCeaseDate = DataItem("LH_SST_XTR_CRG", "SST_XTR_CEA_DT", x)
        
    If CurrentSubTypeCode = TypeAbbr Then
        If CurrentPhase = CovPhase(Cov) Then
            If CurrentPersonCode = PersonCode Or PersonCode = "NA" Then
                If ValuationDate < CurrentCeaseDate Then
                    If TypeAbbr = "T" Then
                        CurrentAmount = DataItem("LH_SST_XTR_CRG", "SST_XTR_RT_TBL_CD", x)
                        dct.Add dct.count + 1, CurrentAmount
                    Else
                        CurrentAmount = DataItem("LH_SST_XTR_CRG", "SST_XTR_UNT_AMT", x)
                        CurrentAnnualFlat = DataItem("LH_SST_XTR_CRG", "XTR_PER_1000_AMT", x)
                        dct.Add dct.count + 1, Array(CurrentAmount, CurrentCeaseDate, CurrentAnnualFlat)
                    End If
                End If
            End If
        End If
    End If
Next
Set ActiveSubstandards = dct
Set dct = Nothing
End Function
Property Get CovTableRating(Cov As Integer, Optional JtIndicator As Integer = 0)
    CovTableRating = Me.TranslateTableLetterToNumber(CovTableRatingCode(Cov, JtIndicator))
End Property
Property Get CovTableRatingCode(Cov As Integer, Optional JtIndicator As Integer = 0)
Dim dct As Dictionary
Set dct = ActiveSubstandards(Cov, "T", JtIndicator)
If dct.count > 1 Then
    MsgBox "Insured for " & Me.Policynumber & " has more than one active table rating on the same coverage"
    Exit Property
End If
If dct.count = 1 Then
    CovTableRatingCode = dct(1)
Else
  CovTableRatingCode = 0
End If
End Property
Property Get CovFlatCount(Cov As Integer)
    CovFlatCount = ActiveSubstandards(Cov, "F").count
End Property
Property Get CovFlat(Cov As Integer, Optional RatingIndex As Integer = 1)
'Returns the monthly flat extra amount.
'dct(RatingIndex) is an array - (monthly flat, flat CeaseDate, Annual Flat)
'Right now (6/22/2017) no Joint UL policies have flat extra's, so there is no JtIndicator argument for this property
    Dim dct As Dictionary
    Set dct = ActiveSubstandards(Cov, "F")
    If RatingIndex > dct.count Then
        CovFlat = 0
        Exit Property
    End If
    CovFlat = dct(RatingIndex)(0)

End Property
Property Get CovFlatAnnual(Cov As Integer, Optional RatingIndex As Integer = 1)
'Returns the Annual flat extra amount.
'dct(RatingIndex) is an array - (monthly flat, flat CeaseDate, Annual Flat)
'Right now (6/22/2017) no Joint UL policies have flat extra's, so there is no JtIndicator argument for this property
    Dim dct As Dictionary
    Set dct = ActiveSubstandards(Cov, "F")
    If RatingIndex > dct.count Then
        CovFlatAnnual = 0
        Exit Property
    End If
    CovFlatAnnual = dct(RatingIndex)(2)
End Property
Property Get CovFlatCeaseDate(Cov As Integer, Optional RatingIndex As Integer = 1)
'Returns the flat cease date.
'dct(RatingIndex) is an array - (monthly flat, flat CeaseDate, Annual Flat)
'Right now (6/22/2017) no Joint UL policies have flat extra's, so there is no JtIndicator argument for this property
Dim dct As Dictionary
    Set dct = ActiveSubstandards(Cov, "F")
    If RatingIndex > dct.count Then
        CovFlatCeaseDate = 0
        Exit Property
    End If
    CovFlatCeaseDate = dct(RatingIndex)(1)   'index 0 = Amount, index 1 = CeaseDate
End Property
Property Get CovFlatCeaseAge(Cov As Integer, Optional RatingIndex As Integer = 1)
'Returns the flat cease age.
'dct(RatingIndex) is an array - (monthly flat, flat CeaseDate, Annual Flat)
'Right now (6/22/2017) no Joint UL policies have flat extra's, so there is no JtIndicator argument for this property
Dim dct As Dictionary
    Set dct = ActiveSubstandards(Cov, "F")
    If RatingIndex > dct.count Then
        CovFlatCeaseAge = 0
        Exit Property
    End If
    CovFlatCeaseAge = CovIssueAge(Cov) + CompletedDateParts("YYYY", CovIssueDate(Cov), CovFlatCeaseDate(Cov, RatingIndex))
End Property

'====================================================================================================================================================================================
'LH_FND_ALC
'====================================================================================================================================================================================
Private Function FundAllocationPrctDictionary() As Dictionary
'The allocation information is stored in 2 tables that work together:  LH_FND_TRS_ALC_SET and LH_FND_ALC

    If mCurrentPolicy("FundAllocations") Is Nothing Then
        
        'Find the segment allocation date in effect as of the Valuation Date.  This is found in the LH_FND_TRS_ALC_SET table
        Dim xcount, x As Integer, SegNum As Integer, SegDate As Date, CurrSegDate As Date, CurrTrsType As String
        xcount = DataItemCount("LH_FND_TRS_ALC_SET", "FND_TRS_TYP_CD")
        SegDate = 0
        For x = 1 To xcount
            CurrSegDate = CDate(DataItem("LH_FND_TRS_ALC_SET", "LST_ALC_CHG_DT", x))
            CurrTrsType = DataItem("LH_FND_TRS_ALC_SET", "FND_TRS_TYP_CD", x)
            
            If CurrSegDate > SegDate And CurrSegDate <= Me.ValuationDate And CurrTrsType = "P" Then
                SegDate = CDate(DataItem("LH_FND_TRS_ALC_SET", "LST_ALC_CHG_DT", x))
                SegNum = DataItem("LH_FND_TRS_ALC_SET", "FND_ALC_SEQ_NBR", x)
            End If
        Next
        
        Dim dctFundAllocation  As Dictionary
        Set dctFundAllocation = New Dictionary
        Dim FundID, FundAllocationType, FundAllocationPercent As Variant, FundAllocationSegNum As Integer
        
        'Get the fund allocatoin information effective on the SegDate.  This is found in then LH_FND_ALC table
        xcount = DataItemCount("LH_FND_ALC", "FND_ID_CD")
        If DataItemCount("LH_FND_ALC", "FND_ID_CD") > 0 Then
            For x = 1 To xcount
                FundID = DataItem("LH_FND_ALC", "FND_ID_CD", x)
                'U1, IX, IC, IS, IF, SW
   
                FundAllocationType = DataItem("LH_FND_ALC", "FND_ALC_TYP_CD", x)
                'C = Charge deduction
                'P = Payment allocation
                'V = Indexed Fund Reinvestment
    
                FundAllocationPercent = DataItem("LH_FND_ALC", "FND_ALC_PCT", x)
                FundAllocationSegNum = CDate(DataItem("LH_FND_ALC", "FND_ALC_SEQ_NBR", x))
                If FundAllocationType = "P" And FundAllocationSegNum = SegNum Then
                    dctFundAllocation(FundID) = FundAllocationPercent
                End If
            Next
        End If
        Set mCurrentPolicy("FundAllocations") = dctFundAllocation
        Set dctFundAllocation = Nothing
    End If
    Set FundAllocationPrctDictionary = mCurrentPolicy("FundAllocations")
    

'    If mCurrentPolicy("FundAllocations") Is Nothing Then
'        Dim dctFundAllocation  As Dictionary
'        Set dctFundAllocation = New Dictionary
'
'        Dim xcount As Integer, x As Integer
'        Dim FundID, FundAllocationType, FundAllocationPercent, FundSeqNumber As Variant
'        Dim MaxSeq As Integer
'
'        xcount = DataItemCount("LH_FND_ALC", "FND_ID_CD")
'        If DataItemCount("LH_FND_ALC", "FND_ID_CD") > 0 Then
'            MaxSeq = FindMaxValue("LH_FND_ALC", "FND_ALC_SEQ_NBR", xcount)
'
'            For x = 1 To xcount
'                FundID = DataItem("LH_FND_ALC", "FND_ID_CD", x)
'                'U1, IX, IC, IS, IF, SW
'
'                FundAllocationType = DataItem("LH_FND_ALC", "FND_ALC_TYP_CD", x)
'                'C = Charge deduction
'                'P = Payment allocation
'                'V = Indexed Fund Reinvestment
'
'                FundSeqNumber = DataItem("LH_FND_ALC", "FND_ALC_SEQ_NBR", x)
'
'                FundAllocationPercent = DataItem("LH_FND_ALC", "FND_ALC_PCT", x)
'                If FundAllocationType = "P" And FundSeqNumber = MaxSeq Then dctFundAllocation(FundID) = FundAllocationPercent
'            Next
'        End If
'        Set mCurrentPolicy("FundAllocations") = dctFundAllocation
'        Set dctFundAllocation = Nothing
'    End If
'    Set FundAllocationPrctDictionary = mCurrentPolicy("FundAllocations")
End Function
Property Get PremiumAllocationPercentages() As Dictionary
    Set PremiumAllocationPercentages = FundAllocationPrctDictionary
End Property
Private Function FindMaxValue(strTable As String, strField As String, xcount As Integer) As Variant
Dim tempval
    If xcount = 0 Then
        tempval = Empty
    Else
        'FND_ALC_SEQ_NBR
        tempval = DataItem(strTable, strField, 1)
        Dim x As Integer
        For x = 2 To xcount
            If tempval < DataItem(strTable, strField, x) Then tempval = DataItem(strTable, strField, x)
        Next
    End If
    
    FindMaxValue = tempval
           
End Function


'====================================================================================================================================================================================
'LH_POL_FND_VAL_TOT
'====================================================================================================================================================================================
Private Function FundBucketValuesDictionary() As Dictionary
'Creates a dictionary where the key is field name and the item is an array with values for each bucket.
'This is only used within the class to store the information for different policies.  There are other
'public properties for each field to get access to the values.

If mCurrentPolicy("FundValues") Is Nothing Then
    Dim dctFundValues As Dictionary
    Set dctFundValues = New Dictionary
    Dim xcount As Integer
    Dim BucketIndex As Integer
    Dim BucketID As String
    Dim BucketValue As Double
    Dim BucketStartDate As Date
    Dim BucketMVDate As Date
    
    Dim FundBucketID() As Variant
    Dim FundBucketMVDate() As Variant
    Dim FundBucketStartDate() As Variant
    Dim FundBucketEndDate() As Variant
    Dim FundBucketValue() As Variant
    Dim FundBucketPhaseCode() As Variant
    
    xcount = DataItemCount("LH_POL_FND_VAL_TOT", "FND_ID_CD")
    
    If xcount > 0 Then
        
        Dim x As Integer
        
        For x = 1 To xcount
            BucketID = IfEmpty(DataItem("LH_POL_FND_VAL_TOT", "FND_ID_CD", x), 0)
            BucketValue = IfEmpty(DataItem("LH_POL_FND_VAL_TOT", "CSV_AMT", x), 0)
            BucketStartDate = IfEmpty(DataItem("LH_POL_FND_VAL_TOT", "ITS_PER_STR_DT", x), 0)
            BucketMVDate = IfEmpty(DataItem("LH_POL_FND_VAL_TOT", "MVRY_DT", x), 0)
            
            Select Case BucketID
            'When listing all the current funds, only include the Index funds that havent matured yet and have non-zero value
            
                Case "IX", "IC", "IF", "IC":
                'If maturity date has not occured yet then add bucket to array matrix
                'Assumes index funds mature in one year.
                    If DateAdd("Y", 1, BucketStartDate) > Me.MVDate Or BucketValue <> 0 Then
                        BucketIndex = BucketIndex + 1
                        
                        ReDim Preserve FundBucketID(1 To BucketIndex)
                        ReDim Preserve FundBucketMVDate(1 To BucketIndex)
                        ReDim Preserve FundBucketStartDate(1 To BucketIndex)
                        ReDim Preserve FundBucketEndDate(1 To BucketIndex)
                        ReDim Preserve FundBucketValue(1 To BucketIndex)
                        ReDim Preserve FundBucketPhaseCode(1 To BucketIndex)
                        
                        FundBucketID(BucketIndex) = BucketID
                        FundBucketMVDate(BucketIndex) = BucketMVDate
                        FundBucketStartDate(BucketIndex) = BucketStartDate
                        FundBucketPhaseCode(BucketIndex) = IfEmpty(DataItem("LH_POL_FND_VAL_TOT", "FND_VAL_PHA_NBR", x), 0)
                        FundBucketValue(BucketIndex) = BucketValue
                        
                    End If
                
                Case Else:
                'All non-Index funds are included (U1, LN, SW...)
                    BucketIndex = BucketIndex + 1
                    
                    ReDim Preserve FundBucketID(1 To BucketIndex)
                    ReDim Preserve FundBucketMVDate(1 To BucketIndex)
                    ReDim Preserve FundBucketStartDate(1 To BucketIndex)
                    ReDim Preserve FundBucketEndDate(1 To BucketIndex)
                    ReDim Preserve FundBucketValue(1 To BucketIndex)
                    ReDim Preserve FundBucketPhaseCode(1 To BucketIndex)
                    
                    FundBucketID(BucketIndex) = BucketID
                    FundBucketMVDate(BucketIndex) = BucketMVDate
                    FundBucketStartDate(BucketIndex) = BucketStartDate
                    FundBucketPhaseCode(BucketIndex) = IfEmpty(DataItem("LH_POL_FND_VAL_TOT", "FND_VAL_PHA_NBR", x), 0)
                    FundBucketValue(BucketIndex) = BucketValue
                    
            End Select
        Next
    End If
    dctFundValues.Add "FundBucketCount", BucketIndex
    dctFundValues.Add "FundBucketID", FundBucketID
    dctFundValues.Add "FundBucketMVDate", FundBucketMVDate
    dctFundValues.Add "FundBucketStartDate", FundBucketStartDate
    dctFundValues.Add "FundBucketEndDate", FundBucketEndDate
    dctFundValues.Add "FundBucketValue", FundBucketValue
    dctFundValues.Add "FundBucketPhaseCode", FundBucketPhaseCode
    Set mCurrentPolicy("FundValues") = dctFundValues
    Set dctFundValues = Nothing
End If

Set FundBucketValuesDictionary = mCurrentPolicy("FundValues")

End Function
Property Get FundBucketCount() As Integer
    FundBucketCount = FundBucketValuesDictionary("FundBucketCount")
End Property
Property Get FundBucketPhaseCode(x As Integer) As Integer
    FundBucketPhaseCode = FundBucketValuesDictionary("FundBucketPhaseCode")(x)
End Property
Property Get FundBucketID(x As Integer) As String
    FundBucketID = FundBucketValuesDictionary("FundBucketID")(x)
End Property
Property Get FundBucketMVDate(x As Integer) As Date
    FundBucketMVDate = FundBucketValuesDictionary("FundBucketMVDate")(x)
End Property
Property Get FundBucketStartDate(x As Integer) As Date
    FundBucketStartDate = FundBucketValuesDictionary("FundBucketStartDate")(x)
End Property
Property Get FundBucketEndDate(x As Integer) As Date
    FundBucketEndDate = FundBucketValuesDictionary("FundBucketEndDate")(x)
End Property
Property Get FundBucketValue(x As Integer) As Double
    FundBucketValue = FundBucketValuesDictionary("FundBucketValue")(x)
End Property
Property Get FundValuesDictionary() As Dictionary
    Dim dctFundValues As Dictionary
    Set dctFundValues = New Dictionary
 
    'Create dictionary by summing up fund values across distinct fund ids only if the bucket is effective on the valuation date
    Dim x As Integer
    For x = 1 To Me.FundBucketCount
        If Me.FundBucketMVDate(x) = "12/31/9999" Then
            dctFundValues(Me.FundBucketID(x)) = dctFundValues(Me.FundBucketID(x)) + Me.FundBucketValue(x)
        End If
    Next
   
    Set FundValuesDictionary = dctFundValues
    Set dctFundValues = Nothing
 
End Property

'====================================================================================================================================================================================
'VH_POL_HAS_LOC_CLT & LH_CTT_CLIENT
'====================================================================================================================================================================================
Property Get PersonIndex(Optional PersonCodeString As String = "00", Optional SeqNumber As Integer = 1) As Integer
    Dim x As Integer
    For x = 1 To PersonCount
        If PersonCode(x) = PersonCodeString And PersonSequenceCode(x) = SeqNumber Then
            PersonIndex = x
            Exit Property
        End If
    Next
End Property
Property Get PersonCount()
    PersonCount = DataItemCount("VH_POL_HAS_LOC_CLT", "PRS_CD")
End Property
Property Get PersonPrefix(x As Integer)
    PersonPrefix = Trim(DataItem("VH_POL_HAS_LOC_CLT", "CK_NM_PFX", x))
End Property
Property Get PersonSuffix(x As Integer)
    PersonSuffix = Trim(DataItem("VH_POL_HAS_LOC_CLT", "CK_NM_SFX", x))
End Property
Property Get PersonFirstName(x As Integer)
    PersonFirstName = Trim(DataItem("VH_POL_HAS_LOC_CLT", "CK_FST_NM", x))
End Property
Property Get PersonLastName(x As Integer)
    PersonLastName = Trim(DataItem("VH_POL_HAS_LOC_CLT", "CK_LST_NM", x))
End Property
Property Get PersonEffectiveDate(x As Integer)
    PersonEffectiveDate = DataItem("LH_CTT_CLIENT", "EFF_DT", x)
End Property
Property Get PersonBirthDate(x As Integer)
    PersonBirthDate = DataItem("LH_CTT_CLIENT", "BIR_DT", x)
End Property
Property Get PersonClass(x As Integer)
    PersonClass = DataItem("LH_CTT_CLIENT", "OCP_CLS_CD", x)
End Property
Property Get PersonGender(x As Integer)
    PersonGender = DataItem("LH_CTT_CLIENT", "GENDER_CD", x)
End Property
Property Get PersonAge(x As Integer) As Variant
    PersonAge = DataItem("LH_CTT_CLIENT", "INS_AGE", x)
End Property
Property Get PersonCode(x As Integer)
    PersonCode = DataItem("LH_CTT_CLIENT", "PRS_CD", x)
End Property
Property Get PersonSequenceCode(x As Integer)
  PersonSequenceCode = DataItem("LH_CTT_CLIENT", "PRS_SEQ_NBR", x)
End Property
Property Get IsJointInsured() As Boolean
    Dim tempValue As Boolean
    tempValue = False
    Dim x As Integer
    For x = 1 To PersonCount
        If PersonCode(x) = "01" Then tempValue = True
    Next
    IsJointInsured = tempValue
End Property


'====================================================================================================================================================================================
'LH_LOC_CLT_ADR   (Address Table)
'====================================================================================================================================================================================
Property Get AddressIndex(Optional PersonCodeString As String = "00", Optional SeqNumber As Integer = 1) As Integer
    Dim x As Integer
    For x = 1 To PersonCount
        If AddressPersonCode(x) = PersonCodeString And AddressPersonSequenceCode(x) = SeqNumber Then
            AddressIndex = x
            Exit Property
        End If
    Next
End Property
Property Get AddressCount()
    AddressCount = DataItemCount("LH_LOC_CLT_ADR", "PRS_CD")
End Property
Property Get AddressPersonCodeCount(Optional PersonCodeString As String = "00", Optional SeqNumber As Integer = 1) As Integer
    Dim x As Integer
    Dim count As Integer
    For x = 1 To AddressCount
        If AddressPersonCode(x) = PersonCodeString And AddressPersonSequenceCode(x) = SeqNumber Then
            count = count + 1
        End If
    Next
    AddressPersonCodeCount = count
End Property
Property Get AddressPersonCode(x As Integer)
    AddressPersonCode = DataItem("LH_LOC_CLT_ADR", "PRS_CD", x)
End Property
Property Get AddressPersonSequenceCode(x As Integer)
    AddressPersonSequenceCode = DataItem("LH_LOC_CLT_ADR", "PRS_SEQ_NBR", x)
End Property
Property Get AddressStreet1(x As Integer)
    AddressStreet1 = DataItem("LH_LOC_CLT_ADR", "ADR_LIN_1", x)
End Property
Property Get AddressStreet2(x As Integer)
    AddressStreet2 = DataItem("LH_LOC_CLT_ADR", "ADR_LIN_2", x)
End Property
Property Get AddressCity(x As Integer)
    AddressCity = DataItem("LH_LOC_CLT_ADR", "CIT_TXT", x)
End Property
Property Get AddressState(x As Integer)
    AddressState = DataItem("LH_LOC_CLT_ADR", "CK_ST_CD", x)
End Property
Property Get AddressZip(x As Integer)
    AddressZip = DataItem("LH_LOC_CLT_ADR", "ZIP_CD", x)
End Property




'====================================================================================================================================================================================
'LH_CTT_COM_PHA_WA
'====================================================================================================================================================================================
Property Get AgentCount()
    AgentCount = DataItemCount("LH_CTT_COM_PHA_WA", "WRT_AGT_NM")
End Property
Property Get Agent(Optional x As Integer = 1)
    Agent = IfEmpty(DataItem("LH_CTT_COM_PHA_WA", "WRT_AGT_NM", x), "")
End Property
Property Get ServicingAgent(Optional x As Integer = 1)
    Agent = IfEmpty(DataItem("LH_CTT_COM_PHA_WA", "WRT_AGT_NM", x), "")
End Property



'====================================================================================================================================================================================
'LH_COV_TARGET
'====================================================================================================================================================================================
Property Get CCV() As Variant
Dim subtotal As Variant
Dim x As Integer
   For x = 1 To DataItemCount("LH_COV_TARGET", "TAR_TYP_CD")
     If DataItem("LH_COV_TARGET", "TAR_TYP_CD", x) = "XP" Then
       subtotal = subtotal + DataItem("LH_COV_TARGET", "TAR_PRM_AMT", x)
       Exit For
     End If
   Next
CCV = subtotal
End Property
Property Get SurrenderTarget(Optional CovIndex As Integer = 1) As Variant
Dim tempValue As Variant
tempValue = -1
Dim x As Integer
   For x = 1 To DataItemCount("LH_COV_TARGET", "TAR_TYP_CD")
    If DataItem("LH_COV_TARGET", "COV_PHA_NBR", x) = CovPhase(CovIndex) Then
        If DataItem("LH_COV_TARGET", "TAR_TYP_CD", x) = "ST" Then
            tempValue = DataItem("LH_COV_TARGET", "TAR_PRM_AMT", x)
            Exit For
        End If
     End If
   Next
SurrenderTarget = tempValue
End Property

'Property Get GAV()
' If Not blnLoadCovTarget Then LoadCovTarget
' GAV = mGAV
'End Property


'====================================================================================================================================================================================
'LH_TAMRA_7_PY_PER & LH_TAMRA_7_PY_YR
'====================================================================================================================================================================================
Property Get NoTAMRAValues() As Boolean
    NoTAMRAValues = DataItemCount("LH_TAMRA_7_PY_PER", "SVPY_LVL_PRM_AMT") = 0
End Property
Property Get TAMRA_7PayLevel() As Variant
    TAMRA_7PayLevel = IfEmpty(DataItem("LH_TAMRA_7_PY_PER", "SVPY_LVL_PRM_AMT"), 0)
End Property
Property Get TAMRA_7PayStartDate() As Variant
    TAMRA_7PayStartDate = IfEmpty(DataItem("LH_TAMRA_7_PY_PER", "SVPY_PER_STR_DT"), 0)
End Property
Property Get TAMRA_7PayAV() As Variant
    TAMRA_7PayAV = IfEmpty(DataItem("LH_TAMRA_7_PY_PER", "SVPY_BEG_CSV_AMT"), 0)
End Property
Property Get MEC_Indicator() As String
    MEC_Indicator = IfEmpty(DataItem("LH_TAMRA_7_PY_PER", "MEC_STA_CD"), "")
End Property
Property Get CountOf1035Payments() As Variant
    CountOf1035Payments = IfEmpty(DataItem("LH_TAMRA_7_PY_PER", "XCG_1035_PMT_QTY"), 0)
End Property
Property Get TAMRA_7PaySpecifiedAmount() As Variant
  TAMRA_7PaySpecifiedAmount = IfEmpty(DataItem("LH_TAMRA_7_PY_PER", "SVPY_BEG_FCE_AMT"), 0)
End Property
Property Get TAMRA_7PayPremiumsPaid(Yr As Integer) As Variant
    TAMRA_7PayPremiumsPaid = DataItem("LH_TAMRA_7_PY_YR", "SVPY_PRM_PAY_AMT", Yr)
End Property
Property Get TAMRA_7PayWithdrawals(Yr As Integer) As Variant
    TAMRA_7PayWithdrawals = DataItem("LH_TAMRA_7_PY_YR", "SVPY_WTD_AMT", Yr)
End Property


'====================================================================================================================================================================================
'LH_TRD_POL
'====================================================================================================================================================================================
Property Get TRAD_Count() As Variant
  TRAD_Count = DataItemCount("LH_TRD_POL", "ACU_PRM_AMT")
End Property
Property Get TRAD_AccumulatedPremium() As Variant
  TRAD_AccumulatedPremium = DataItem("LH_TRD_POL", "ACU_PRM_AMT")
End Property


'====================================================================================================================================================================================
'FH_FIXED
'====================================================================================================================================================================================
Property Get TransactionCount()
  TransactionCount = DataItemCount("FH_FIXED", "ASOF_DT")
End Property
Property Get TransactionRevInd(x As Integer)
  TransactionRevInd = DataItem("FH_FIXED", "FCB0_REV_IND", x)
End Property
Property Get TransactionRevApplied(x As Integer)
  TransactionRevApplied = DataItem("FH_FIXED", "FCB2_REV_APPL_IND", x)
End Property
Property Get TransactionFundID(x As Integer)
  TransactionFundID = DataItem("FH_FIXED", "FUND_ID", x)
End Property
Property Get TransactionDate(x As Integer)
  TransactionDate = DataItem("FH_FIXED", "ASOF_DT", x)
End Property
Property Get TransactionFundPhase(x As Integer)
  TransactionFundPhase = DataItem("FH_FIXED", "FNDVAL_PH", x)
End Property
Property Get TransactionType(x As Integer)
  TransactionType = DataItem("FH_FIXED", "TRANS", x)
End Property
Property Get TransactionNetAmount(x As Integer)
  TransactionNetAmount = DataItem("FH_FIXED", "NET_AMT", x)
End Property
Property Get TransactionGrossAmount(x As Integer)
  TransactionGrossAmount = DataItem("FH_FIXED", "GROSS_AMT", x)
End Property
Property Get TransactionEntryDate(x As Integer)
  TransactionEntryDate = DataItem("FH_FIXED", "ENTRY_DT", x)
End Property
Property Get TransactionInterestRate(x As Integer)
  TransactionInterestRate = DataItem("FH_FIXED", "INT_RT", x)
End Property
Property Get TransactionOrigin(x As Integer) As String
  TransactionOrigin = DataItem("FH_FIXED", "ORIGIN_OF_TRANS", x)
End Property


'====================================================================================================================================================================================
'LH_APPLIED_PTP & LH_UNAPPLIED_PTP
'====================================================================================================================================================================================
Property Get AppliedDivCount() As Integer
  AppliedDivCount = DataItemCount("LH_APPLIED_PTP", "CK_PTP_TYP_CD")
End Property
Property Get AppliedDivType(x As Integer) As String
  AppliedDivType = DataItem("LH_APPLIED_PTP", "CK_PTP_TYP_CD", x)
End Property
Property Get AppliedDivAnniversaryIndicator(x As Integer) As String
  AppliedDivAnniversaryIndicator = DataItem("LH_APPLIED_PTP", "PTP_ANV_PRC_IND", x)
End Property
Property Get AppliedDivInterestRate(x As Integer) As String
  AppliedDivInterestRate = DataItem("LH_APPLIED_PTP", "DIV_GRS_ITS_RT", x)
End Property
Property Get AppliedDivCovPhase(x As Integer) As Double
  AppliedDivCovPhase = DataItem("LH_APPLIED_PTP", "COV_PHA_NBR", x)
End Property
Property Get AppliedDivEarnDate(x As Integer) As Double
  AppliedDivEarnDate = DataItem("LH_APPLIED_PTP", "ERN_DT_MO_YR_NBR", x)
End Property
Property Get AppliedDivAppliedOption(x As Integer) As String
  AppliedDivAppliedOption = DataItem("LH_APPLIED_PTP", "APP_OPT_CD", x)
End Property
Property Get AppliedDivFromPUA(x As Integer) As String
  AppliedDivFromPUA = DataItem("LH_APPLIED_PTP", "PTP_SRC_IND", x)
End Property
Property Get AppliedDivPUAUnits(x As Integer) As Double
  AppliedDivPUAUnits = DataItem("LH_APPLIED_PTP", "PUA_UNT_QTY", x)
End Property
Property Get AppliedDivCashAmount(x As Integer) As Double
  AppliedDivCashAmount = DataItem("LH_APPLIED_PTP", "CSH_AMT", x)
End Property
Property Get AppliedDivPUAAmount(x As Integer) As String
  AppliedDivPUAAmount = DataItem("LH_APPLIED_PTP", "PUA_AMT", x)
End Property
Property Get AppliedDivOYTAmount(x As Integer) As String
  AppliedDivOYTAmount = DataItem("LH_APPLIED_PTP", "OYT_AMT", x)
End Property

Property Get UnappliedDivCount() As Integer
  UnappliedDivCount = DataItemCount("LH_UNAPPLIED_PTP", "CK_PTP_TYP_CD")
End Property
Property Get UnappliedDivDate(x As Integer) As String
  UnappliedDivDate = DataItem("LH_UNAPPLIED_PTP", "ERN_DT_MO_YR_NBR", x)
End Property
Property Get UnappliedDivType(x As Integer) As String
  UnappliedDivType = DataItem("LH_UNAPPLIED_PTP", "CK_PTP_TYP_CD", x)
End Property
Property Get UnappliedDivFromPUA(x As Integer) As String
  UnappliedDivFromPUA = DataItem("LH_UNAPPLIED_PTP", "PTP_SRC_IND", x)
End Property
Property Get UnappliedDivOnDepositInterestRate(x As Integer) As Double
  UnappliedDivOnDepositInterestRate = DataItem("LH_UNAPPLIED_PTP", "DEP_ITS_RT", x)
End Property
Property Get UnappliedDivFromRPU(x As Integer) As Double
  UnappliedDivFromRPU = DataItem("LH_UNAPPLIED_PTP", "RPU_VAL_IND", x)
End Property
Property Get UnappliedDivTermination(x As Integer) As String
  UnappliedDivTermination = DataItem("LH_UNAPPLIED_PTP", "TMN_DIV_IND", x)
End Property
Property Get UnappliedDivCovPhase(x As Integer) As String
  UnappliedDivCovPhase = DataItem("LH_UNAPPLIED_PTP", "COV_PHA_NBR", x)
End Property
Property Get UnappliedDivCashRate(x As Integer) As Double
  UnappliedDivCashRate = DataItem("LH_UNAPPLIED_PTP", "CSH_AMT", x)
End Property
Property Get UnappliedDivProjectedCashRate(x As Integer) As Double
  UnappliedDivProjectedCashRate = DataItem("LH_UNAPPLIED_PTP", "PRJ_CSH_AMT", x)
End Property
Property Get UnappliedDivPUAMortality(x As Integer) As String
  UnappliedDivPUAMortality = DataItem("LH_UNAPPLIED_PTP", "PUA_MTL_TBL_CD", x)
End Property
Property Get UnappliedDivPUAInterestRate(x As Integer) As Double
  UnappliedDivPUAInterestRate = DataItem("LH_UNAPPLIED_PTP", "PUA_ITS_RT", x)
End Property
Property Get UnappliedDivPUAUnits(x As Integer) As Double
  UnappliedDivPUAUnits = DataItem("LH_UNAPPLIED_PTP", "PUA_UNT_QTY", x)
End Property
Property Get UnappliedDivPUARate(x As Integer) As Double
  UnappliedDivPUARate = DataItem("LH_UNAPPLIED_PTP", "PUA_AMT", x)
End Property
Property Get UnappliedDivPUAMaturityDuration(x As Integer) As Integer
  UnappliedDivPUAMaturityDuration = DataItem("LH_UNAPPLIED_PTP", "PUA_MT_DUR", x)
End Property
Property Get UnappliedDivOYTRate(x As Integer) As Double
  UnappliedDivOYTRate = DataItem("LH_UNAPPLIED_PTP", "OYT_AMT", x)
End Property
Property Get UnappliedDivOYTMortality(x As Integer) As String
  UnappliedDivOYTMortality = DataItem("LH_UNAPPLIED_PTP", "OYT_MTL_TBL_CD", x)
End Property
Property Get UnappliedDivOYTInterestRate(x As Integer) As Double
  UnappliedDivOYTInterestRate = DataItem("LH_UNAPPLIED_PTP", "OYT_ITS_RT", x)
End Property



     
     
'====================================================================================================================================================================================
'LH_ONE_YR_TRM_ADD
'====================================================================================================================================================================================
Property Get DivOYTCount() As Integer
   DivOYTCount = DataItemCount("LH_ONE_YR_TRM_ADD", "MVRY_DT")
End Property
Property Get DivOYTDate(x As Integer) As Date
   DivOYTDate = DataItem("LH_ONE_YR_TRM_ADD", "MVRY_DT", x)
End Property
Property Get DivOYTMortality(x As Integer) As String
   DivOYTMortality = DataItem("LH_ONE_YR_TRM_ADD", "OYT_MTL_TBL_CD", x)
End Property
Property Get DivOYTInterestRate(x As Integer) As Double
   DivOYTInterestRate = DataItem("LH_ONE_YR_TRM_ADD", "OYT_ITS_RT", x)
End Property
Property Get DivOYTClassCode(x As Integer) As Double
   DivOYTClassCode = DataItem("LH_ONE_YR_TRM_ADD", "OYT_CLS_CD", x) 'FDCINTPW-INTEREST-PREV-WTHDRW
End Property
Property Get DivOYTAmount(x As Integer) As Double
   DivOYTAmount = DataItem("LH_ONE_YR_TRM_ADD", "OYT_ADD_AMT", x)
End Property
Property Get DivOYTExpiryDate(x As Integer) As Integer
 'Function returns number of months from 1/1/1900
   DivOYTExpiryDate = DataItem("LH_ONE_YR_TRM_ADD", "OYT_EXP_MO_YR_NBR", x)
End Property
Property Get DivOYTAnniversaryProcessIndicator(x As Integer) As String
   DivOYTAnniversaryProcessIndicator = DataItem("LH_ONE_YR_TRM_ADD", "ANV_PRC_CRN_IND", x)
End Property
Property Get DivOYTCurrent() As Double
Dim x As Integer, subtotal As Double
For x = 1 To DivOYTCount
   If DivOYTDate(x) = CDate("12/31/9999") Then
        subtotal = subtotal + DivOYTAmount(x)
   End If
Next
   DivOYTCurrent = subtotal
End Property


'====================================================================================================================================================================================
'LH_PAID_UP_ADD
'====================================================================================================================================================================================
Property Get DivPUACount() As Integer
   DivPUACount = DataItemCount("LH_PAID_UP_ADD", "MVRY_DT")
End Property
Property Get DivPUADate(x As Integer) As Date
   DivPUADate = DataItem("LH_PAID_UP_ADD", "MVRY_DT", x)
End Property
Property Get DivPUAMaturityDate(x As Integer) As Integer
'Function returns number of months from 1/1/1900
   DivPUAMaturityDate = DataItem("LH_PAID_UP_ADD", "PUA_MT_MO_YR_NBR", x)
End Property
Property Get DivPUACovPhase(x As Integer) As String
   DivPUACovPhase = DataItem("LH_PAID_UP_ADD", "COV_PHA_NBR", x)
End Property
Property Get DivPUAClassCode(x As Integer) As Double
   DivPUAClassCode = DataItem("LH_PAID_UP_ADD", "PUA_CLS_CD", x)
End Property
Property Get DivPUAMortality(x As Integer) As String
   DivPUAMortality = DataItem("LH_PAID_UP_ADD", "PUA_MTL_TBL_CD", x)
End Property
Property Get DivPUAInterestRate(x As Integer) As Double
   DivPUAInterestRate = DataItem("LH_PAID_UP_ADD", "PUA_ITS_RT", x)
End Property
Property Get DivPUAAmount(x As Integer) As Double
   DivPUAAmount = DataItem("LH_PAID_UP_ADD", "PUA_AMT", x)
End Property
Property Get DivPUAFundingSource(x As Integer) As String
   DivPUAFundingSource = DataItem("LH_PAID_UP_ADD", "PUA_PUR_SRC_CD", x)
End Property
Property Get DivPUACurrent() As Double
Dim x As Integer, subtotal As Double
For x = 1 To DivPUACount
   If DivPUADate(x) = CDate("12/31/9999") Then
        subtotal = subtotal + DivPUAAmount(x)
   End If
Next
   DivPUACurrent = subtotal
End Property


'====================================================================================================================================================================================
'LH_PTP_ON_DEP
'====================================================================================================================================================================================
Property Get DivDepositCount() As Integer
   DivDepositCount = DataItemCount("LH_PTP_ON_DEP", "MVRY_DT")
End Property
Property Get DivDepositLastAnniversary(x As Integer) As Date
   DivDepositLastAnniversary = DataItem("LH_PTP_ON_DEP", "MVRY_DT", x)
End Property
Property Get DivDepositInterestDate(x As Integer) As Integer
   DivDepositInterestDate = DataItem("LH_PTP_ON_DEP", "ITS_APP_MO_YR_NBR", x)
End Property
Property Get DivDepositInterestRate(x As Integer) As Double
   DivDepositInterestRate = DataItem("LH_PTP_ON_DEP", "DEP_ITS_RT", x)
End Property
Property Get DivDepositAmount(x As Integer) As Double
   DivDepositAmount = DataItem("LH_PTP_ON_DEP", "PTP_DEP_AMT", x)
End Property
Property Get DivDepositInterestOnWDs(x As Integer) As Double
   DivDepositInterestOnWDs = DataItem("LH_PTP_ON_DEP", "PRE_WTD_ITS_AMT", x) 'FDCINTPW-INTEREST-PREV-WTHDRW
End Property
Property Get DivDepositAccumInterestWithheld(x As Integer) As Double
   DivDepositAccumInterestWithheld = IfEmpty(DataItem("LH_PTP_ON_DEP", "ACU_ITS_WHD_AMT", 1), 0)
End Property
Property Get DivDepositCurrent() As Double
Dim x As Integer, subtotal As Double
For x = 1 To DivDepositCount
   If DivDepositLastAnniversary(x) = CDate("12/31/9999") Then
        subtotal = subtotal + DivDepositAmount(x)
   End If
Next
   DivDepositCurrent = subtotal
End Property


'======================================================================================
'TRANSLATIONS From Code to Text
'======================================================================================

'ANICO_RateclassOrder
'FFL_RateclassOrder
'MarketDictionary
'CompanyMarketOrgsDictionary
'DetermineMarketOrg
'TranslateMarketOrgToCode
'TranslateFunctionCodeToText
'TranslateRenewalRateTypeCodeToText
'TranslateDivTypeCodeToText
'TranslateNonForfeitureOptionCodeToText
'TranslateDivOptionCodeToText
'TranslateProductLineCodeToText
'TranslateNonStandardModeToText
'TranslateFundIDToName
'TranslateDBOptionCodeToText
'TranslateStateCodeToAbbr
'TranslateStateAbbrToCode
'TranslateMECIndicatorToText
'TranslateBillModeCodeToText
'TranslatePersonCodeToText
'TranslateGracePeriodRuleToText
'TranslateBenefitTypeToText
'TranslateBenefitTextToType
'TranslateTableLetterToNumber
'TranslateCompanyTextToCode
'TranslateCompanyCodeToText
'TranslateEntryCodeToText
'TranslateReinsuranceCodeToText
'TranslateLoanInterestStatusCodeToText
'TranslateLoanInterestTypeCodeToText
'TranslateLoanRecordInterestTypeCodeToText
'TranslateLastEntryCodeToText
'TranslateSuspenseCodeToText
'TranslateANICOProductCodeToText
'TranslateNonForfeitureCodeToText
'TranslateStatusCodeToText
'TranslateTransactionCodeToText
'TranslateTransactionTypeToText
'TranslateMortalityTableCodeToText
'TranslateRateclassCodeToText
'TranslateSexCodeToText
'TranslateBillFormCode
'TranslateLivesCoveredCodeToText
'TranslateModeCodeToFrequency
'TranslateSubstandardTypeCode

'======================================================================================
Public Function ANICO_RateclassOrder(RateclassCode As String) As Integer
    Dim tempValue As Integer
    Select Case RateclassCode
        Case "R": tempValue = 6
        Case "P": tempValue = 5
        Case "T": tempValue = 4
        Case "N": tempValue = 3
        Case "Q": tempValue = 2
        Case "S": tempValue = 1
    End Select
    ANICO_RateclassOrder = tempValue
End Function

Public Function FFL_RateclassOrder(RateclassCode As String) As Integer
    Dim tempValue As Integer
    Select Case RateclassCode
        'Older FFL
        Case "E": tempValue = 6
        Case "F": tempValue = 5
        Case "G": tempValue = 4
        Case "H": tempValue = 3
        Case "I": tempValue = 2
        Case "K": tempValue = 1
    End Select
    FFL_RateclassOrder = tempValue
End Function
Public Function MarketDictionary() As Dictionary
    Dim dct As Dictionary
    Dim subdct As Dictionary
    
    Set dct = New Dictionary
    Set subdct = New Dictionary
    
    Set subdct = New Dictionary
    subdct.Add "FFL", "1"
    dct.Add "FFL", subdct
    
    Set subdct = New Dictionary
    subdct.Add "MLM", "1"
    subdct.Add "IMG", "7"
    subdct.Add "DIRECT", "D"
    dct.Add "ANICO NY", subdct
    
    Set subdct = New Dictionary
    subdct.Add "MLM", "1"
    subdct.Add "CSSD", "2"
    subdct.Add "IMG", "7"
    subdct.Add "DIRECT", "D"
    dct.Add "ANICO", subdct
    
    Set subdct = New Dictionary
    subdct.Add "GSL", "GSL"
    dct.Add "GSL", subdct
    
    Set subdct = New Dictionary
    subdct.Add "ANTEX", "1"
    dct.Add "ANTEX", subdct
    
    Set subdct = New Dictionary
    subdct.Add "SLAICO", "1"
    dct.Add "SLAICO", subdct
        
    Set MarketDictionary = dct
    
    Set dct = Nothing
    Set subdct = Nothing
End Function

Public Function CompanyMarketOrgsDictionary() As Dictionary
    Dim dctMain As Dictionary
    Dim dct As Dictionary
    Set dctMain = New Dictionary
    Set dct = New Dictionary
    
    'Market Orgs available for company ANICO
    dct.Add "MLM", "1"
    dct.Add "CSSD", "2"
    dct.Add "IMG", "7"
    dct.Add "DIRECT", "D"
    dctMain.Add "01", dct
    
    'Market Orgs available for company ANICONY
    dct.RemoveAll
    dct.Add "MLM", "1"
    dct.Add "IMG", "7"
    dct.Add "DIRECT", "D"
    dctMain.Add "30", dct
    
    dct.RemoveAll
    dct.Add "ANTEX1", "1"
    dct.Add "ANTEX6", "6"
    dctMain.Add "04", dct
    
    dct.RemoveAll
    dct.Add "SLAICO", "1"
    dctMain.Add "06", dct
    
    dct.RemoveAll
    dct.Add "GSL", "GSL"
    dctMain.Add "08", dct
    
    dct.RemoveAll
    dct.Add "FFL", "1"
    dctMain.Add "26", dct

    Set CompanyMarketOrgsDictionary = dctMain
End Function
Public Function DetermineMarketOrg(CompanyCode As String, AgentCode As String) As String
    Dim tempValue As String
    Select Case CompanyCode
        Case "01":
                      Select Case AgentCode
                          Case "1": tempValue = "MLM"
                          Case "2": tempValue = "CSSD"
                          Case "7": tempValue = "IMG"
                          Case "D": tempValue = "DIRECT"
                          Case Else: tempValue = AgentCode
                      End Select
        Case "04":    tempValue = "ANTEX"
        Case "06":    tempValue = "SLAICO"
        Case "08":    tempValue = "GSL"
        Case "26":    tempValue = "FFL"
        Case "30":
                      Select Case AgentCode
                          Case "1": tempValue = "MLM"
                          Case "7": tempValue = "IMG"
                          Case "D": tempValue = "DIRECT"
                          Case Else: tempValue = AgentCode
                      End Select
        Case Else:    tempValue = AgentCode
    End Select
    DetermineMarketOrg = tempValue
End Function
Public Function TranslateMarketOrgToCode(MarketOrgAbbr As String)
    Dim tempValue As String
    Select Case MarketOrgAbbr
        Case "MLM": tempValue = "1"
        Case "CSSD": tempValue = "2"
        Case "IMG": tempValue = "7"
        Case "DIRECT": tempValue = "D"
        Case "ANTEX":    tempValue = "1"  ' or "6"
        Case "SLAICO":    tempValue = "1"
        Case "GSL":    tempValue = "1" ' or "2" or "7"
        Case "FFL":    tempValue = "1"
    End Select
    TranslateMarketOrgToCode = tempValue
End Function
Public Function TranslateFunctionCodeToText(Code As String) As String
    Dim tempValue As Variant
    Select Case Code
        Case "0": tempValue = "Curtate"
        Case "1": tempValue = "Semicontinuous"
        Case "2": tempValue = "Fully continuous"
        Case "3": tempValue = "Discounted continuous"
        Case Else: tempValue = Code
    End Select
    TranslateFunctionCodeToText = tempValue
End Function

Public Function TranslateRenewalRateTypeCodeToText(Code As String) As String
    Dim tempValue As Variant
    Select Case Code
        Case "M": tempValue = "MinTarg"
        Case "T": tempValue = "CommTarg"
        Case "W": tempValue = "SurrTarg"
        Case "L": tempValue = "PremTarg"
        Case "C": tempValue = "CovCOI"
        Case "B": tempValue = "BenCOI"
        Case Else: tempValue = Code
    End Select
    TranslateRenewalRateTypeCodeToText = tempValue
End Function
Public Function TranslateDivTypeCodeToText(vntDivTypeCode As Variant) As String
    Dim tempValue As String
    Select Case CStr(vntDivTypeCode)
        Case "D": tempValue = "Dividend"
        Case "C": tempValue = "Coupon"
        Case Else: tempValue = vntDivTypeCode
    End Select
    TranslateDivTypeCodeToText = tempValue
End Function

Public Function TranslateNonForfeitureOptionCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "0": tempValue = "The contract has no value; lapse it"
        Case "1": tempValue = "Apply APLs until the limit is reached and convert to ETI"
        Case "2": tempValue = "Apply APLs until the limit is reached and convert to RPU"
        Case "3": tempValue = "Apply APLs until no value remains"
        Case "4":  tempValue = "Convert to ETI"
        Case "5": tempValue = "Convert to RPU"
        Case "9": tempValue = "See policy for special loan or termination agreement"
        Case Else: tempValue = Code
    End Select
    TranslateNonForfeitureOptionCodeToText = tempValue
End Function


Public Function TranslateDivOptionCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "1", 1: tempValue = "Cash"
        Case "2", 2: tempValue = "Prem Reduce" '"Premium reduction"
        Case "3", 3: tempValue = "Deposit at interest" '"Deposit at interest"
        Case "4", 4: tempValue = "Paid-up additions"
        Case "5", 5: tempValue = "One year term additions, unlimited"
        Case "6", 6: tempValue = "OYT Limit CV" 'One year term additions, limit cash value"
        Case "7", 7: tempValue = "OYT Limit Face" '"One year term additions, limit face amount"
        Case "8", 8: tempValue = "Loan Reduction" '"Loan reduction"
        Case Else: tempValue = Code
    End Select
    TranslateDivOptionCodeToText = tempValue
End Function

Public Function TranslateProductLineCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "0": tempValue = "Traditional"
        Case "A": tempValue = "First-to-die rider"
        Case "B": tempValue = "Blended insurance rider"
        Case "C": tempValue = "Additional payment paid-up additions rider"
        Case "D": tempValue = "Dread disease rider"
        Case "F": tempValue = "Annuity or Annuity Rider"
        Case "I": tempValue = "Interest sensitive life"
        Case "L": tempValue = "Long term care"
        Case "N": tempValue = "Indeterminate premium"
        Case "U": tempValue = "Universal or variable universal life"
        Case "P": tempValue = "Paid-up whole life or paid-up deferred whole life"
        Case "S": tempValue = "Disability income"
        Case "X": tempValue = "Excess interest life"
    End Select
    TranslateProductLineCodeToText = tempValue
End Function
Public Function TranslateNonStandardModeToText(Mode As String) As String
    Dim tempValue As String
    Select Case Mode
        Case "1": tempValue = "Weekly"
        Case "2": tempValue = "Biweekly"
        Case "4": tempValue = "13thly (every 4 weeks)"
        Case "9": tempValue = "9thly"
        Case "A": tempValue = "10thly"
        Case "S": tempValue = "SemiMonthly"
        Case Else: tempValue = Mode
    End Select
    TranslateNonStandardModeToText = tempValue
End Function
Public Function TranslateFundIDToName(strFundID As String) As String
    Dim tempFundName As String
    Select Case strFundID
        Case "IX":   tempFundName = "Index 1 yr PTP with Cap"
        Case "IC":   tempFundName = "Index 1 yr PTP with 1.5% and Cap"
        Case "IF":   tempFundName = "Index 1 yr PTP uncapped with fee"
        Case "IS":   tempFundName = "Index 1 yr PTP with Specified Rate"
        Case "SW":   tempFundName = "Sweep Fund"
        Case "GP":   tempFundName = "Grace Fund"
        Case "U1":   tempFundName = "General Fund"
        Case Else:   tempFundName = strFundID
    End Select
    TranslateFundIDToName = tempFundName
End Function


Public Function TranslateDBOptionCodeToText(vntDBOptCode As Variant) As String
    Dim tempDBOpt As String
    vntDBOptCode = CStr(vntDBOptCode)
    Select Case vntDBOptCode
        Case "A", "1": tempDBOpt = "A - Level"
        Case "B", "2": tempDBOpt = "B - Increasing"
        Case "C", "3": tempDBOpt = "C - Returen Of Premium"
        Case Else: tempDBOpt = vntDBOptCode
    End Select
    TranslateDBOptionCodeToText = tempDBOpt
End Function
Public Function TranslateStateCodeToAbbr(intStateCode As Integer) As String
'These are the state code in Cyberlife, not to be confused with the state filing codes used for filed forms - which are different
    Dim tempValue As Variant
    Select Case intStateCode
        Case 1:      tempValue = "AL"
        Case 2:      tempValue = "AZ"
        Case 3:      tempValue = "AR"
        Case 4:      tempValue = "CA"
        Case 5:      tempValue = "CO"
        Case 6:      tempValue = "CT"
        Case 7:      tempValue = "DE"
        Case 8:      tempValue = "DC"
        Case 9:      tempValue = "FL"
        Case 10:      tempValue = "GA"
        Case 11:      tempValue = "ID"
        Case 12:      tempValue = "IL"
        Case 13:      tempValue = "IN"
        Case 14:      tempValue = "IA"
        Case 15:      tempValue = "KS"
        Case 16:      tempValue = "KY"
        Case 17:      tempValue = "LA"
        Case 18:      tempValue = "ME"
        Case 19:      tempValue = "MD"
        Case 20:      tempValue = "MA"
        Case 21:      tempValue = "MI"
        Case 22:      tempValue = "MN"
        Case 23:      tempValue = "MS"
        Case 24:      tempValue = "MO"
        Case 25:      tempValue = "MT"
        Case 26:      tempValue = "NE"
        Case 27:      tempValue = "NV"
        Case 28:      tempValue = "NH"
        Case 29:      tempValue = "NJ"
        Case 30:      tempValue = "NM"
        Case 31:      tempValue = "NY"
        Case 32:      tempValue = "NC"
        Case 33:      tempValue = "ND"
        Case 34:      tempValue = "OH"
        Case 35:      tempValue = "OK"
        Case 36:      tempValue = "OR"
        Case 37:      tempValue = "PA"
        Case 38:      tempValue = "RI"
        Case 39:      tempValue = "SC"
        Case 40:      tempValue = "SD"
        Case 41:      tempValue = "TN"
        Case 42:      tempValue = "TX"
        Case 43:      tempValue = "UT"
        Case 44:      tempValue = "VT"
        Case 45:      tempValue = "VA"
        Case 46:      tempValue = "WA"
        Case 47:      tempValue = "WV"
        Case 48:      tempValue = "WI"
        Case 49:      tempValue = "WY"
        Case 50:      tempValue = "AK"
        Case 51:      tempValue = "HI"
        Case 52:      tempValue = "PR"
        Case 55:      tempValue = "AS"
        Case 60:      tempValue = "MP"
        Case 65:      tempValue = "VI"
        Case 66:      tempValue = "GU"
    End Select
    TranslateStateCodeToAbbr = tempValue
End Function
Public Function TranslateStateAbbrToCode(StateAbbr As String) As Integer
'These are the state code in Cyberlife, not to be confused with the state filing codes used for filed forms - which are different
    Dim tempValue As Variant
    Select Case StateAbbr
        Case "AL": tempValue = 1
        Case "AZ": tempValue = 2
        Case "AR": tempValue = 3
        Case "CA": tempValue = 4
        Case "CO": tempValue = 5
        Case "CT": tempValue = 6
        Case "DE": tempValue = 7
        Case "DC": tempValue = 8
        Case "FL": tempValue = 9
        Case "GA": tempValue = 10
        Case "ID": tempValue = 11
        Case "IL": tempValue = 12
        Case "IN": tempValue = 13
        Case "IA": tempValue = 14
        Case "KS": tempValue = 15
        Case "KY": tempValue = 16
        Case "LA": tempValue = 17
        Case "ME": tempValue = 18
        Case "MD": tempValue = 19
        Case "MA": tempValue = 20
        Case "MI": tempValue = 21
        Case "MN": tempValue = 22
        Case "MS": tempValue = 23
        Case "MO": tempValue = 24
        Case "MT": tempValue = 25
        Case "NE": tempValue = 26
        Case "NV": tempValue = 27
        Case "NH": tempValue = 28
        Case "NJ": tempValue = 29
        Case "NM": tempValue = 30
        Case "NY": tempValue = 31
        Case "NC": tempValue = 32
        Case "ND": tempValue = 33
        Case "OH": tempValue = 34
        Case "OK": tempValue = 35
        Case "OR": tempValue = 36
        Case "PA": tempValue = 37
        Case "RI": tempValue = 38
        Case "SC": tempValue = 39
        Case "SD": tempValue = 40
        Case "TN": tempValue = 41
        Case "TX": tempValue = 42
        Case "UT": tempValue = 43
        Case "VT": tempValue = 44
        Case "VA": tempValue = 45
        Case "WA": tempValue = 46
        Case "WV": tempValue = 47
        Case "WI": tempValue = 48
        Case "WY": tempValue = 49
        Case "AK": tempValue = 50
        Case "HI": tempValue = 51
        Case "PR": tempValue = 52
        Case "AS": tempValue = 55
        Case "MP": tempValue = 60
        Case "VI": tempValue = 65
        Case "GU": tempValue = 66
    End Select
    TranslateStateAbbrToCode = tempValue
End Function
Public Function TranslateMECIndicatorToText(MECIndicator As String) As String
    Dim tempValue As String
    Select Case MECIndicator
        Case "0":  tempValue = "Not a MEC"
        Case "1":  tempValue = "Policy is a MEC."
        Case "2":  tempValue = "Plan is subject to the 7-pay test"
        Case Else: tempValue = MECIndicator
    End Select
    TranslateMECIndicatorToText = tempValue
End Function

Public Function TranslateBillModeCodeToText(vntBillModeCode As String, Optional NonStandardMode As String = "") As String
    Dim tempMode As String
    vntBillModeCode = CStr(vntBillModeCode)
    Select Case vntBillModeCode
        Case "1":
                   tempMode = "M - Monthly"
                   If NonStandardMode = "2" Then tempMode = "B - BiWeekly"
                   If NonStandardMode = "S" Then tempMode = "SM - SemiMonthly"
                   
        Case "3": tempMode = "Q - Quarterly"
        Case "6": tempMode = "S - SemiAnnually"
        Case "12": tempMode = "A - Annually"
        Case Else: tempMode = vntBillModeCode
    End Select
    TranslateBillModeCodeToText = tempMode
End Function

Public Function TranslatePersonCodeToText(strCode As String) As String
    Dim tempText As String
    Select Case strCode
        Case "00": tempText = "Primary Insured"
        Case "01": tempText = "Joint insured"
        Case "10": tempText = "Owner"
        Case "20": tempText = "Payor"
        Case "30": tempText = "Beneficiary"
        Case "40": tempText = "Spouse"
        Case "50": tempText = "Dependent"
        Case "60": tempText = "Other"
        Case "70": tempText = "Assignee"
        Case "A0": tempText = "Power of attorney"
        Case "A1": tempText = "Financial advisor"
        Case "A2": tempText = "Third party administrator (TPA)"
        Case "A3": tempText = "Certified public accountant (CPA)"
        Case "A4": tempText = "Plan sponsor"
        Case "A5": tempText = "Conservator"
        Case "A6": tempText = "Domestic partner"
        Case "A7": tempText = "Legal guardian"
        Case "A8": tempText = "Trustee"
        Case "A9": tempText = "Settlement Broker"
        Case Else: tempText = strCode
    End Select
    TranslatePersonCodeToText = tempText
End Function

Public Function TranslateGracePeriodRuleToText(GracePeriodRule As String) As String
    Dim tempValue As Variant
    Select Case GracePeriodRule
        Case "C": tempValue = "Unloaned CV < 0"
        Case "S": tempValue = "SV < 0"
        Case "N": tempValue = "Adjusted Prem < MAP, then Rule S"
        Case "R": tempValue = "Adjusted Prem < MAP AND Unloaned CV < 0, then rule C"
        Case "T": tempValue = "Adjusted Prem < MAP AND SV < 0, then Rule S"
    End Select
    TranslateGracePeriodRuleToText = tempValue
End Function

Public Function TranslateBenefitTypeToText(BenefitType As String, Optional subType As String = "")
    Dim tempType As String
    Select Case BenefitType
        Case "1": tempType = "ADB"     'Accidental Death Benefit
        Case "2": tempType = "ADnD"    'Accidental Death and Dismemberment
        Case "3": tempType = "PWoC"    'Premium Waiver of Cost
        Case "4": tempType = "PWoT"    'Premium Wavier of Target
        Case "7": tempType = "GIO"     'Guaranteed Increase Option
        Case "9": tempType = "PPB"     'Premium Payor Benefit
        Case "#":
                    If subType = "" Then
                        tempType = "ABR"    'Accelerated Benefit Rider
                    Else
                        Select Case subType
                            Case "1": tempType = "ABRTM"
                            Case "2": tempType = "ABRCT"
                            Case "3": tempType = "ABRCH"
                            Case "4": tempType = "ABRTM"
                            Case "5": tempType = "ABRCT"
                            Case "6": tempType = "ABRCH"
                            Case "L": tempType = "ABRLN"
                            Case Else: tempType = BenefitType & subType
                        End Select
                    End If
        Case "A": tempType = "CCV"     'Coverage Continuation Rider (aka shadow account)
        Case "U": tempType = "COLA"    'Cost of Living Adjustment
        Case "B": tempType = "LTC"     'Long Term Care
        Case "V":
                        Select Case subType 'Guaranteed Cash Out rider
                            Case "1": tempType = "GCO15"
                            Case "2": tempType = "GCO20"
                            Case "3": tempType = "GCO25"
                            Case Else: tempType = BenefitType & subType
                        End Select
        Case Else: tempType = BenefitType
    End Select
    TranslateBenefitTypeToText = tempType
End Function
Public Function TranslateBenefitTextToType(BenefitText As String)
    Dim tempType As String
    Select Case CStr(BenefitText)
        Case "ADB": tempType = "1"
        Case "ADD": tempType = "2"
        Case "PWoC": tempType = "3"
        Case "PWoT": tempType = "4"
        Case "GIO": tempType = "7"
        Case "PPB": tempType = "9"
        Case "ABR": tempType = "#"
        Case "CCV": tempType = "A"
        Case "COLA": tempType = "U"
        Case "LTC": tempType = "B"
        Case Else: tempType = BenefitText
    End Select
    TranslateBenefitTextToType = tempType
End Function

Public Function TranslateTableLetterToNumber(TableLetter As String) As Variant
    Dim tempValue As Variant
    Select Case CStr(Application.WorksheetFunction.Trim(TableLetter))
        Case "0": tempValue = 0
        Case "A", "1": tempValue = 1
        Case "B", "2": tempValue = 2
        Case "C", "3": tempValue = 3
        Case "D", "4": tempValue = 4
        Case "E", "5": tempValue = 5
        Case "F", "6": tempValue = 6
        Case "G", "7": tempValue = 7
        Case "H", "8": tempValue = 8
        Case "I", "9": tempValue = 9
        Case "J", "10": tempValue = 10
        Case "K", "11": tempValue = 11
        Case "L", "12": tempValue = 12
        Case "M", "13": tempValue = 13
        Case "N", "14": tempValue = 14
        Case "O", "15": tempValue = 15
        Case "P", "16": tempValue = 16
        Case "X", "999": tempValue = "Unins"
        Case Else: tempValue = TableLetter
    End Select
    TranslateTableLetterToNumber = tempValue
End Function
Public Function TranslateCompanyTextToCode(CompanyText As String) As String
    Dim tempValue As String
    Select Case CStr(CompanyText)
        Case "ANICO":  tempValue = "01"
        Case "ANTEX":  tempValue = "04"
        Case "SLAICO":  tempValue = "06"
        Case "GSL":  tempValue = "08"
        Case "ANICO NY":  tempValue = "26"
        Case Else: tempValue = CompanyText
    End Select
    TranslateCompanyTextToCode = tempValue
End Function

Public Function TranslateCompanyCodeToText(Code As String) As Variant
    Dim tempValue As String
    Select Case Code
        Case "01":  tempValue = "ANICO"
        Case "04":  tempValue = "ANTEX"
        Case "06":  tempValue = "SLAICO"
        Case "08":  tempValue = "GSL"
        Case "26":  tempValue = "ANICO NY"
        Case Else: tempValue = Code
    End Select
    TranslateCompanyCodeToText = tempValue
End Function

Public Function TranslateEntryCodeToText(vntCode As Variant) As String
    Dim tempValue As String
    Select Case CStr(vntCode)
        Case "A": tempValue = "New business"
        Case "B": tempValue = "Group conversion."
        Case "C": tempValue = "Block reinsurance."
        Case "D": tempValue = "Reinstatement."
        Case "E": tempValue = "Exchange or conversion with a new policy number assigned."
        Case "F": tempValue = "Exchange or conversion retaining the original policy number."
        Case "G": tempValue = "Policy change."
        Case "H": tempValue = "Advanced product complex change."
        Case "Z": tempValue = "Old life business converted to the system."
    End Select
    TranslateEntryCodeToText = tempValue
End Function



Public Function TranslateReinsuranceCodeToText(ReinsuranceCode As String) As String
    Dim tempValue As String
    Select Case WorksheetFunction.Trim(ReinsuranceCode)
        Case "A": tempValue = "Automatic"
        Case "F": tempValue = "Facultative"
        Case "N": tempValue = "Not reinsured"
        Case "1": tempValue = "Part reinsured"
        Case "2": tempValue = "Multiple policy records"
        Case " ": tempValue = "Not reinsured"
        Case "": tempValue = "Not reinsured"
    End Select
    TranslateReinsuranceCodeToText = tempValue
End Function
Public Function TranslateLoanInterestStatusCodeToText(vntCode As Variant) As Variant
    Dim tempValue As String
    Select Case CStr(vntCode)
        Case "1", 1: tempValue = "Capitalized"
        Case "2", 2: tempValue = "Earned"
        Case Else: tempValue = vntCode
    End Select
    TranslateLoanInterestStatusCodeToText = tempValue
End Function
Public Function TranslateLoanInterestTypeCodeToText(LoanInterestTypeCode As String) As String
    Dim tempValue As String
    Select Case LoanInterestTypeCode
        Case "0": tempValue = "Advance, Fixed Interest"
        Case "1": tempValue = "Arrears, Fixed Interest"
        Case "6": tempValue = "Advance, Variable Interest"
        Case "7": tempValue = "Arrears, Variable Interest"
        Case "9": tempValue = "Loans not allowed"
    End Select
    TranslateLoanInterestTypeCodeToText = tempValue
End Function
Public Function TranslateLoanRecordInterestTypeCodeToText(vntCode As Variant) As String
    Dim tempValue As String
    Select Case CStr(vntCode)
        Case "1", 1: tempValue = "Advance"
        Case "2", 2: tempValue = "Arrears"
        Case Else: tempValue = vntCode
    End Select
    TranslateLoanRecordInterestTypeCodeToText = tempValue
End Function

Public Function TranslateLastEntryCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "A": tempValue = "Entry - New Business, Not Paid For"
        Case "B": tempValue = "Normal Entry to the file"
        Case "C": tempValue = "Active Policy Record"
        Case "D": tempValue = "Correction Entry to Database"
        Case "E": tempValue = "Replacement"
        Case "F": tempValue = "Replacement with Policy Exhibit Transactions"
        Case "J": tempValue = "Termination - Without Policy Exhibit Transactions"
        Case "K": tempValue = "Termination - With Policy Exhibit Transactions"
        Case "L": tempValue = "Termination - Death Claim Settled"
        Case "M": tempValue = "Termination - Maturity"
        Case "N": tempValue = "Termination - Expiration"
        Case "O": tempValue = "Termination - Conversion"
        Case "P": tempValue = "Termination - Surrender"
        Case "Q": tempValue = "Termination - Lapse"
        Case "R": tempValue = "Termination - Conversion to RPU or ETI"
        Case "X": tempValue = "Termination - Free Look Surrender"
        Case Else: tempValue = Code
    End Select
    TranslateLastEntryCodeToText = tempValue
End Function
Public Function TranslateSuspenseCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "0": tempValue = "Active policy record"
        Case "1": tempValue = "Not used"
        Case "2": tempValue = "Suspend processing"
        Case "3": tempValue = "Death claim pending"
        Case Else: tempValue = Code
    End Select
    TranslateSuspenseCodeToText = tempValue
End Function
Public Function TranslateANICOProductCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "A": tempValue = "APB Rider"
        Case "B": tempValue = "ANICO ROP Rider"
        Case "C": tempValue = "ANTEX Modified DB"
        Case "D": tempValue = "ANTEX Graded DB"
        Case "E": tempValue = "ANTEX Level DB"
        Case "G": tempValue = "Graded Benefit Life"
        Case "P": tempValue = "Converted FFL PUAR"
        Case "R": tempValue = "GSL ROP"
        Case "S": tempValue = "Single Premium ISWL"
        Case "U": tempValue = "Converted FFL UL"
        Case "X": tempValue = "Index UL"
    End Select
    TranslateANICOProductCodeToText = tempValue
End Function
Public Function TranslateNonForfeitureCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "0": tempValue = "No cash value"
        Case "1": tempValue = "APL-->ETI"
        Case "2": tempValue = "APL-->RPU"
        Case "3": tempValue = "APL"
        Case "4": tempValue = "ETI"
        Case "5": tempValue = "RPU"
        Case "9": tempValue = "Special Other"
    End Select
    TranslateNonForfeitureCodeToText = tempValue
End Function
Public Function TranslateStatusCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "21": tempValue = "Premium Paying"
        Case "22": tempValue = "Premium Paying"
        Case "31": tempValue = "Payor Death"
        Case "32": tempValue = "Disability"
        Case "33": tempValue = "Disability"
        Case "34": tempValue = "Disability"
        Case "41": tempValue = "Paid Up"
        Case "42": tempValue = "Single Premium"
        Case "43": tempValue = "Single Premium (none)"
        Case "44": tempValue = "ETI"
        Case "45": tempValue = "RPU"
        Case "46": tempValue = "Fully Paid Up"
        Case "47": tempValue = "Paid Up"
        Case "49": tempValue = "Annuitization (none)"
        Case "54": tempValue = "Lapsing (none)"
        Case "97": tempValue = "Reinstatement pending"
        Case "98": tempValue = "Policy not issued"
        Case "99": tempValue = "Terminated"
        Case Else: tempValue = Code
    
'EXPANDED TEXT
'        Case "11": tempValue = "For pending applications"
'        Case "12": tempValue = "Initial premium not processed on other than preliminary term"
'        Case "13": tempValue = "Preliminary term"
'        Case "21": tempValue = "A fixed premium policy for which back premiums have been billed"
'        Case "22": tempValue = "A normal premium paying policy record"
'        Case "31": tempValue = "Payor death (not currently supported)"
'        Case "32": tempValue = "Disability (traditional policies and interest sensitive life policies) or cost of insurance"
'        Case "33": tempValue = "Disability waiver - scheduled amount added to cash value"
'        Case "34": tempValue = "Cost of insurance waiver and disability waiver"
'        Case "41": tempValue = "Paid-up normal"
'        Case "42": tempValue = "Single premium (fixed premium only)"
'        Case "43": tempValue = "Single premium in lieu of matured endowment (net basis)"
'        Case "44": tempValue = "ETI"
'        Case "45": tempValue = "RPU"
'        Case "46": tempValue = "Fully paid-up"
'        Case "47": tempValue = "Multiple coverages that are all paid-up with different paid-up forms"
'        Case "49": tempValue = "Annuitization"
'        Case "54": tempValue = "A policy record lapsing on a daily cost basis"
'        Case "97": tempValue = "Reinstatement pending"
'        Case "98": tempValue = "Initial premium never received (policy was not issued)"
'        Case "99": tempValue = "A terminated policy record that is carried on the policy file for ease in reinstatement"
    End Select
    TranslateStatusCodeToText = tempValue
End Function


Public Function TranslateTransactionCodeToText(vntCode As Variant) As String
    Dim tempValue As String
    Select Case CStr(vntCode)
        Case "A_": tempValue = "Policyowner statement revision"
        Case "AA": tempValue = "Policyowner statement automatic on anniversary"
        Case "AC": tempValue = "Policyowner confirmation"
        Case "AF": tempValue = "Policyowner statement off anniversary"
        Case "AL": tempValue = "Lag/loss accounting"
        Case "AR": tempValue = "Policyowner statement request prior 12 months"
        Case "AS": tempValue = "Split accounting for the fixed fund portion when the exchange includes both fixed and variable funds."
        Case "AY": tempValue = "Policyowner statement request year-to-date"
        Case "B1": tempValue = "Cost of Insurance"
        Case "B2": tempValue = "Expenses"
        Case "B3": tempValue = "Cost of insureance and expenses"
        Case "B4": tempValue = "First year load"
        Case "B5": tempValue = "Cash value"
        Case "B6": tempValue = "Current interest"
        Case "B7": tempValue = "Guaranteed interest"
        Case "BA": tempValue = "Cost of insurance and expense reversal"
        Case "BB": tempValue = "Current interest reversal (retrospective)"
        Case "BC": tempValue = "Guaranteed interest reversal (prospective)"
        Case "CA": tempValue = "Charge allocation (adjustment)"
        Case "CC": tempValue = "Cumulative charge"
        Case "CD": tempValue = "Charge deduction"
        Case "CY": tempValue = "Calendar year expense charge"
        Case "DK": tempValue = "Dread disease, expense charge"
        Case "DP": tempValue = "Dread disease, claim payment"
        Case "EF": tempValue = "Exchange from"
        Case "EK": tempValue = "Exchange charge"
        Case "ET": tempValue = "Exchange to"
        Case "FE": tempValue = "Discounted premium"
        Case "FF": tempValue = "Premium depositor fund"
        Case "GL": tempValue = "Accounting"
        Case "GP": tempValue = "External variable fund purchase"
        Case "GR": tempValue = "External variable fund redemption"
        Case "HB": tempValue = "Beginning payments"
        Case "HE": tempValue = "Ending payment"
        Case "HP": tempValue = "Claim payment"
        Case "HX": tempValue = "Dread disease claim reduction"
        Case "HZ": tempValue = "LTC/HHC claim reduction"
        Case "IA": tempValue = "Dividends on deposit"
        Case "IB": tempValue = "Other forms on deposit"
        Case "IC": tempValue = "Accrued interest, loan payoff"
        Case "ID": tempValue = "Death claims"
        Case "IE": tempValue = "Discounted premiums"
        Case "IF": tempValue = "Premium depositor fund"
        Case "IH": tempValue = "Pro rata"
        Case "IL": tempValue = "Lien payoffs"
        Case "IN": tempValue = "Long term care/dread disease accumulated claims lien amount"
        Case "IP": tempValue = "Loan payoff"
        Case "IR": tempValue = "Accrued interest, lien payoff"
        Case "IT": tempValue = "Dread disease lien interest"
        Case "IV": tempValue = "Interest on discounted premium withdrawal"
        Case "IW": tempValue = "Interest, premium depositor fund withdrawal"
        Case "LA": tempValue = "Automatic premium loan"
        Case "LC": tempValue = "Capitalized accrued loan interest"
        Case "LF": tempValue = "Maximum preferred loan"
        Case "LG": tempValue = "Gross loan request"
        Case "LM": tempValue = "Maximum loan request"
        Case "LN": tempValue = "Net loan request"
        Case "LP": tempValue = "Loan principal reduction"
        Case "LV": tempValue = "Capitalized advance loan interest"
        Case "LZ": tempValue = "Premiums withheld from loans"
        Case "MA": tempValue = "Accounting"
        Case "MS": tempValue = "Moves money from the clearing account to the external clearing suspense account."
        Case "N3": tempValue = "Deposit at interest"
        Case "N4": tempValue = "Interest on dividends on deposit at conversion to ETI/RPU"
        Case "NC": tempValue = "Pro rata interest on new deposits"
        Case "ON": tempValue = "ISL, paid-up additions option not elected"
        Case "OS": tempValue = "Over/short"
        Case "OY": tempValue = "ISL, elect paid-up additions option"
        Case "P6": tempValue = "Current value adjustment for payments and surrenders"
        Case "P7": tempValue = "Annuitization account value adjustment increase"
        Case "P8": tempValue = "Excess interest"
        Case "PA": tempValue = "Additional (or unscheduled) premium payment"
        Case "PB": tempValue = "Reinstatement payment"
        Case "PC": tempValue = "Loan/lien interest (accrued)"
        Case "PD": tempValue = "Automatic payment, PDF"
        Case "PE": tempValue = "Automatic payment, discounted premium"
        Case "PF": tempValue = "Initial internal rollover payment"
        Case "PI": tempValue = "Initial premium payment"
        Case "PK": tempValue = "Premium load"
        Case "PL": tempValue = "Loan/lien payment"
        Case "PM": tempValue = "Payment from dividends and PUAs"
        Case "PN": tempValue = "Premium payment by automatic premium loan"
        Case "PO": tempValue = "Premium or loan/lien payoff overage"
        Case "PP": tempValue = "Loan/lien payoff"
        Case "PQ": tempValue = "Automatic payment, AP fiixed premium"
        Case "PR": tempValue = "Regular (or sscheduled) premium payment"
        Case "PS": tempValue = "Premium or loan/lien payoff shortage"
        Case "PT": tempValue = "Rollover additional"
        Case "PU": tempValue = "Reinstatement value"
        Case "PV": tempValue = "Advance loan interest payment"
        Case "PW": tempValue = "Premium Waiver"
        Case "PX": tempValue = "Loan/lien interest payment"
        Case "PZ": tempValue = "Premium tax calculation"
        Case "QA": tempValue = "Automatic transaction, annuitization"
        Case "QD": tempValue = "Automatic transactions, automatic disbursement"
        Case "QG": tempValue = "Automatic transactions, initial gain"
        Case "QI": tempValue = "Automatic transactions, initial refresh"
        Case "QR": tempValue = "Automatic transactions, automatic refresh"
        Case "QV": tempValue = "Automatic transactions, fund value quote"
        Case "QX": tempValue = "Equity index increase"
        Case "RC": tempValue = "Refund of cash value, face amount decrease"
        Case "RD": tempValue = "Refund of premium, face amount decrease"
        Case "RI": tempValue = "Reinstatement interest"
        Case "RP": tempValue = "RPU refund excess"
        Case "S4": tempValue = "Paid-up additions partial surrender"
        Case "S5": tempValue = "One year term additions partial surrender"
        Case "S6": tempValue = "Current value withdrawal"
        Case "S7": tempValue = "Annuitization account value adjustment decrease"
        Case "S8": tempValue = "Fund optimization fee"
        Case "SA": tempValue = "Excess accumulation withdrawal"
        Case "SB": tempValue = "Fund optimization fee"
        Case "SC": tempValue = "Surrender, conversion"
        Case "SD D": tempValue = "Premiums due on death claim"
        Case "SF": tempValue = "Full surrender"
        Case "SG": tempValue = "Surrenders, gross withdrawal request"
        Case "SH": tempValue = "Surrenders, home/custodial care claim payment"
        Case "SI": tempValue = "Internal surrender"
        Case "SJ": tempValue = "Forced lapse"
        Case "SK": tempValue = "Surrender charge"
        Case "SL": tempValue = "Free look"
        Case "SM": tempValue = "Maximum withdrawal"
        Case "SN": tempValue = "Net withdrawal"
        Case "SP": tempValue = "Purchase paid-up additions"
        Case "SR": tempValue = "Refunded premium on surrender"
        Case "ST": tempValue = "TSA loan repayment surrender"
        Case "SV": tempValue = "Discounted premium withdrawal"
        Case "SW": tempValue = "Premium depositor fund withdrawal"
        Case "SX": tempValue = "Reversal of premium waiver for death claims and surrenders."
        Case "T9": tempValue = "Policy level surrender or termination"
        Case "TB": tempValue = "Beneficiary payout, surrender or termination"
        Case "TD": tempValue = "Death claim, primary insured"
        Case "TE": tempValue = "Extended term"
        Case "TF": tempValue = "Fully paid-up conversion"
        Case "TL": tempValue = "Lapse"
        Case "TM": tempValue = "Maturity"
        Case "TN": tempValue = "Expiry"
        Case "TO": tempValue = "Other insured death claim"
        Case "TR": tempValue = "Reduced paid-up"
        Case "TV": tempValue = "Lapse, daily cost basis"
        Case "TZ": tempValue = "Premium tax"
        Case "TZ": tempValue = "Premium Tax"
        Case "UI R": tempValue = "Unapplied cash in, returned item"
        Case "UI": tempValue = "Unapplied cash suspense in"
        Case "UO": tempValue = "Unapplied cash suspense out"
        Case "UP": tempValue = "Unmatched payment - batch"
        Case "WO": tempValue = "Waiver of premium off"
        Case "WP": tempValue = "Waiver of premium on"
        Case "XB": tempValue = "Long term care, beginning payments"
        Case "XE": tempValue = "Long term care, ending payments"
        Case "XP": tempValue = "Long term care, claim payment"
        Case "Y0": tempValue = "User defined"
        Case "ZA": tempValue = "Forecasts, annual projection"
        Case "ZC": tempValue = "Forecasts, current premium solve for target cash surrender value"
        Case "ZG": tempValue = "Forecasts, guaranteed premium solve for target cash surrender value"
        Case "ZN": tempValue = "Vanishing (offset) premium request - NVP"
        Case "ZP": tempValue = "Forecasts, current projection"
        Case "ZR": tempValue = "Vanishing (offset) premium request - APP"
        Case "ZS": tempValue = "Forecasts, premium solve"
        Case "ZV": tempValue = "Forecasts, vanishing (offset) premium"
        Case "ZZ": tempValue = "Suppress check special accounting. Refer to the accounting descriptions at the end of this section for more information."
        Case Else: tempValue = vntCode
    End Select
    TranslateTransactionCodeToText = tempValue
End Function

Public Function TranslateTransactionTypeToText(TypeCode As String) As String
    Dim tempValue As String
    Select Case TypeCode
        Case "A": tempValue = "Accounting"
        Case "B": tempValue = "Policyowner Reward"
        Case "C": tempValue = "Charge"
        Case "D": tempValue = "Dread Disease"
        Case "E": tempValue = "Exchange"
        Case "F": tempValue = "Premium Fund Addition"
        Case "G": tempValue = "Agent Ledger"
        Case "H": tempValue = "Home health care"
        Case "I": tempValue = "Interest/Internal"
        Case "L": tempValue = "Loans"
        Case "M": tempValue = "Miscellaneous "
        Case "N": tempValue = "Withdrawal interest"
        Case "O": tempValue = "Paid-up additions option"
        Case "P": tempValue = "Premium payments/loan payments"
        Case "Q": tempValue = "Automatic transactions"
        Case "R": tempValue = "Refund"
        Case "S": tempValue = "Surrenders"
        Case "T": tempValue = "Terminations"
        Case "U": tempValue = "Unapplied cash suspense"
        Case "W": tempValue = "Waiver of Premium"
        Case "X": tempValue = "Long term care"
        Case "Y": tempValue = "User defined"
        Case "Z": tempValue = "Forecast (only if subtype is A, C, G, P, S, or V)"
        Case "1": tempValue = "Dividends earned - premium paying policies"
        Case "2": tempValue = "Other forms of participation earned"
        Case "3": tempValue = "Dividend values - on converted policies"
        Case "4": tempValue = "Other participation on converted policies"
        Case "5": tempValue = "Dividend processing - online"
        Case "6": tempValue = "Other participation - online"
        Case "7": tempValue = "Additions PUA and OYT - online"
        Case "8": tempValue = "Pro rata dividends on withdrawal"
        Case "9": tempValue = "Pro rata other forms on withdrawal"
    End Select
    TranslateTransactionTypeToText = tempValue
    'On 6/17/2016 an audit was run against the FH_FIXED table for company "01".  These were the only transaction types found:
    'B,C,E,F,I,L,P,R,S,T,U,W,Z,1,2,3,4,5,6,7
End Function

Public Function TranslateMortalityTableCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "#": tempValue = "2001CSO SM/NS"
        Case "@": tempValue = "80 CSO SMKR/N"
        Case "A": tempValue = "1926 CL 3 AE  A"
        Case "J": tempValue = "PROG ANNUITY  J"
        Case "K": tempValue = "A/E CRAIG     K"
        Case "L": tempValue = "A/E BUTTOLPH  L"
        Case "M": tempValue = "AMERICAN MEN  M"
        Case "N": tempValue = "1941 CSO      N"
        Case "O": tempValue = "1958 CSO MALE O"
        Case "P": tempValue = "1958 CSO FEM  P"
        Case "S": tempValue = "1958 CSO MLX  S"
        Case "T": tempValue = "1958 CSO FLX  T"
        Case "0": tempValue = "OLD JOINT LIF"
        Case "$": tempValue = "2001CSO COMPU"
        Case "*": tempValue = "1949 A FEMALE"
        Case "**": tempValue = "1949 A FEMALE"
        Case "LA": tempValue = "80 CETMNS ALB"
        Case "LC": tempValue = "2001CSOMNS LS"
        Case "LD": tempValue = "2001CSOFNS LS"
        Case "LF": tempValue = "2001CSOMS L S"
        Case "LG": tempValue = "2001CSOFS L S"
        Case "LJ": tempValue = "80 CSOJT ALB"
        Case "LK": tempValue = "2001CSOMNS LU"
        Case "LL": tempValue = "2001CSOFNS LU"
        Case "LN": tempValue = "2001CSOMS L U"
        Case "LO": tempValue = "2001CSOFS L U"
        Case "LP": tempValue = "2001CSOM L  U"
        Case "LQ": tempValue = "2001CSOF L  U"
        Case "L0": tempValue = "80 CSOMNS ALB 0"
        Case "L1": tempValue = "80 CSOFNS ALB 1"
        Case "L2": tempValue = "80 CSOMS ALB  2"
        Case "L3": tempValue = "80 CSOFS ALB  3"
        Case "L4": tempValue = "80 CSOM ALB   4"
        Case "L5": tempValue = "80 CSOF ALB   5"
        Case "L6": tempValue = "80 CETMS ALB  6"
        Case "NC": tempValue = "2001CSOMNS NS"
        Case "ND": tempValue = "2001CSOFNS NS"
        Case "NF": tempValue = "2001CSOMS N S"
        Case "NG": tempValue = "2001CSOFS N S"
        Case "NJ": tempValue = "80 CSOJT ANB"
        Case "NK": tempValue = "2001CSOMNS NU"
        Case "NL": tempValue = "2001CSOFNS NU"
        Case "NN": tempValue = "2001CSOMS N U"
        Case "NO": tempValue = "2001CSOFS N U"
        Case "NP": tempValue = "2001CSOM N  U"
        Case "NQ": tempValue = "2001CSOF N  U"
        Case "NW": tempValue = ""
        Case "NX": tempValue = ""
        Case "N0": tempValue = "80 CSOMNS ANB"
        Case "N1": tempValue = "80 CSOFNS ANB"
        Case "N2": tempValue = "80 CSOMS ANB"
        Case "N3": tempValue = "80 CFOFS ANB"
        Case "N4": tempValue = "80 CSOM ANB"
        Case "N5": tempValue = "80 CSOF ANB"
        Case "P1": tempValue = ""
        Case "UA": tempValue = "80CSO US ALB"
        Case "UC": tempValue = "2001CSO US LS"
        Case "UE": tempValue = "2001CSO UN NS"
        Case "UF": tempValue = "2001CSO US NS"
        Case "UH": tempValue = "2001CSO UN LS"
        Case "UK": tempValue = "2001CSO US LU"
        Case "UM": tempValue = "2001CSO UN NU"
        Case "UN": tempValue = "2001CSO US NU"
        Case "UO": tempValue = "2001CSOC80/20"
        Case "UP": tempValue = "2001CSO UN LU"
        Case "UR": tempValue = "80CSONSU40"
        Case "US": tempValue = "80CSOSKU40"
        Case "UX": tempValue = "2001CSOC40/60"
        Case "U0": tempValue = "80CSO-E ANB"
        Case "U2": tempValue = "80CSO UN ANB"
        Case "U4": tempValue = "80CSO US ANB"
        Case "U6": tempValue = "80CSO U ALB"
        Case "U8": tempValue = "80CSO UN ALB"
        Case "4B": tempValue = "1941 SI ALB"
        Case "4D": tempValue = "41 130%SI ANB"
        Case "4E": tempValue = "1961 CSI  ALB"
        Case "4F": tempValue = "1949 A FEMALE"
        Case "4G": tempValue = "1941 SI ANB"
        Case "4I": tempValue = "1941 SSI ANB"
        Case "4J": tempValue = "1961 CSI ANB"
        Case Else: tempValue = Code
    End Select
    TranslateMortalityTableCodeToText = tempValue
End Function

Public Function TranslateRateclassCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "A": tempValue = "NONSMOKER"
        Case "B": tempValue = "SMOKER"
        Case "D": tempValue = "PREFERRED"
        Case "E": tempValue = "NONTOBACCO PREF BEST"
        Case "F": tempValue = "NONTOBACCO PREF PLUS"
        Case "G": tempValue = "NONTOBACCO PREFERRED"
        Case "H": tempValue = "NON TOBACCO STANDARD"
        Case "I": tempValue = "TOBACCO PREFERRED   "
        Case "J": tempValue = "STANDARD"
        Case "K": tempValue = "NONSMOKER OR TOBACCO STANDARD"
        Case "L": tempValue = "GUARANTEED ISSUE"
        Case "N": tempValue = "Standard Nicotine Non User"
        Case "P": tempValue = "Preferred Nicotine Non User"
        Case "Q": tempValue = "Preferred Nicotine User"
        Case "R": tempValue = "Preferred Plus Nicotine Non User"
        Case "S": tempValue = "Standard Nicotine User"
        Case "T": tempValue = "Standard Plus Nicotine Non User"
        Case "V": tempValue = "STANDARD            "
        Case "X": tempValue = "STANDARD"
        Case "Y": tempValue = "SUBSTANDARD"
        Case "0": tempValue = "RATES DO NOT VARY BY CLASS"
        Case Else: tempValue = Code
    End Select
    TranslateRateclassCodeToText -tempValue
End Function

Public Function TranslateSexCodeToText(Code As String) As String
    Dim tempValue As Integer
    Select Case Code
        Case "T": tempValue = "Unisex 100/0 or 30/70"
        Case "U": tempValue = "Unisex 80/20"
        Case "X": tempValue = "Unisex 30/70"
        Case "1": tempValue = "Male"
        Case "2": tempValue = "Female"
    End Select
    TranslateSexCodeToText = tempValue
End Function

Public Function TranslateBillFormCode(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "0": tempValue = "Direct pay notice"
        Case "1": tempValue = "A": tempValue = "Home office"
        Case "2": tempValue = "B": tempValue = "Permanent APL"
        Case "3": tempValue = "C": tempValue = "Premium depositor fund"
        Case "4": tempValue = "Discounted premium deposit"
        Case "6": tempValue = "F": tempValue = "Government allotment"
        Case "7": tempValue = "G": tempValue = "PAC"
        Case "8": tempValue = "H": tempValue = "Salary deduction"
        Case "9": tempValue = "I": tempValue = "Bank deduction"
        Case "J": tempValue = "Dividend"
        Case "Q ": tempValue = "Permanent APP"
        Case "V": tempValue = "Net vanish (offset) premium"
        Case Else: tempValue = Code
    End Select
    TranslateBillFormCode = tempValue
End Function

Public Function TranslateLivesCoveredCodeToText(Code As String) As String
    Dim tempValue As String
    Select Case Code
        Case "0": tempValue = "Proposed Insured or Joint Insureds"
        Case "1", "Proposed insured, spouse, and dependents"
        Case "2": tempValue = "Spouse and dependents"
        Case "3": tempValue = "Single dependents"
        Case "4", "Proposed insured, spouse, and dependents"
        Case "5": tempValue = "Spouse and dependents"
        Case "6": tempValue = "Dependents only"
        Case "7": tempValue = "Proposed insured and dependents"
        Case "8": tempValue = "Proposed insured and dependents"
        Case "A": tempValue = "Family medical expense"

    End Select
    TranslateLivesCoveredCodeToText = tempValue
End Function

Public Function TranslateModeCodeToFrequency(Code As String) As Integer
    Dim tempValue As Integer
    Select Case Code
        Case "A":   tempValue = 1
        Case "S": tempValue = 2
        Case "Q": tempValue = 4
        Case "M": tempValue = 12
        Case "B": tempValue = 26
    End Select
    TranslateModeCodeToFrequency = tempValue
End Function

Private Function TranslateSubstandardTypeCode(TypeCode As String) As String
  Select Case TypeCode
    Case "0", "1", "3": TranslateSubstandardTypeCode = "T"
    Case "2", "4":  TranslateSubstandardTypeCode = "F"
    Case Else: TranslateSubstandardTypeCode = TypeCode
  End Select
End Function

Private Function TranslateAgeCalculationRuleToDescription(AgeCode As String)
Dim tempValue
Select Case AgeCode
    Case "0":   tempValue = "ANB"
    Case "1":   tempValue = "ALB"
End Select
TranslateAgeCalculationRuleToDescription = tempValue
End Function

Private Function TranslateEliminationPeriodCode(Code As String) As Variant
Dim tempValue 'Number of days
Select Case Code
    Case "0":   tempValue = "0"
    Case "3":   tempValue = "30"
    Case "4":   tempValue = "14"
    Case "5":   tempValue = "180"
    Case "6":   tempValue = "60"
    Case "7":   tempValue = "7"
    Case "9":   tempValue = "90"
    Case Else:   tempValue = Code
End Select
TranslateEliminationPeriodCode = tempValue
End Function

Private Function TranslateBenefitPeriodCode(Code As String)
Dim tempValue   'Number of year or To-Age
Select Case Code
    Case "E":   tempValue = "5"
    Case "B":   tempValue = "2"
    Case "G":   tempValue = "Life"
    Case "L":   tempValue = "1"
    Case "F":   tempValue = "65"    'To age 65
    Case "S":   tempValue = "67"    'To age 67
    Case "R":   tempValue = "1.5"
    Case "J":   tempValue = "10"
    Case "X":   tempValue = "2"
    Case Else:   tempValue = Code
End Select
TranslateBenefitPeriodCode = tempValue
End Function
'=================================================================================================================================
'UTILITIES
'=================================================================================================================================
Public Function Transpose2DArray(OldArray As Variant) As Variant
'The WorksheetFunction.Transpose function will convert a 2D array to a 1D array if input array only has one row.
'This can cause problems later on with functions expecting a 2D array.  So this function is created to
'always transpose a 2D array into another 2D array


Dim NewRowLB As Long
Dim NewRowUB As Long
Dim NewColumnLB As Long
Dim NewColumnUB As Long

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

Public Function InsertRowIntoArray(InputArray As Variant, index As Long, RowArray As Variant) As Variant
'RJH - 6/25/2016
'Copied most of this from cpearson array tool modual

'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
' InsertRowIntoArray
' This function creates a new array from InputArray and inserts RowArray at locatation Index.
' InputArray must be a 2D dynamic array.RowArray must be a 1D array with the same number of
' elements as columns in InputArray. A new array is created with one more row than InputArray.
' All rows upto Index are populated.  Then RowArray is added, then the rest of the rows from
' InputArray are added. The InputArray is then set equal to the new array.  The value of Index
' must be greater than or equal to the LBound of InputArray and less than or equal to UBound+1.
' If Index is UBound+1, the Value is placed at the end of the array.
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''




'''''''''''''''''''''''''''''''''''''''''
' Ensure Index is a valid element index.
' We allow Index to be equal to
' UBound + 1 to facilitate inserting
' a value at the end of the array. E.g.,
' InsertElementIntoArray(Arr,UBound(Arr)+1,123)
' will insert 123 at the end of the array.
'''''''''''''''''''''''''''''''''''''''''
If (index < LBound(InputArray, 1)) Or (index > UBound(InputArray, 1) + 1) Then
    Exit Function
End If

'Make sure RowArray as enough elements to fit into InputArray
If UBound(RowArray) - LBound(RowArray) <> UBound(InputArray, 2) - LBound(InputArray, 2) Then
  Exit Function
End If

'Create new array with one more row than InputArray but the same number of columns
Dim TempArray() As Variant
ReDim TempArray(LBound(InputArray, 1) To UBound(InputArray, 1) + 1, LBound(InputArray, 2) To UBound(InputArray, 2))

Dim Ndx As Long
Dim ColumnNdx As Long

'Add all rows after Index
For Ndx = UBound(InputArray, 1) To index Step -1
 For ColumnNdx = LBound(InputArray, 2) To UBound(InputArray, 2) Step 1
   TempArray(Ndx + 1, ColumnNdx) = InputArray(Ndx, ColumnNdx)
 Next
Next

'Insert the new RowArray
For ColumnNdx = LBound(InputArray, 2) To UBound(InputArray, 2) Step 1
  TempArray(index, ColumnNdx) = RowArray(ColumnNdx)
Next

'Add all rows prior to Index
For Ndx = index - 1 To LBound(InputArray, 1) Step -1
  For ColumnNdx = LBound(InputArray, 2) To UBound(InputArray, 2) Step 1
   TempArray(Ndx, ColumnNdx) = InputArray(Ndx, ColumnNdx)
 Next
Next

InputArray = TempArray

InsertRowIntoArray = True

End Function

Public Function CompletedDateParts(difftype As String, argDate1, argDate2) As Long
'This function is used to calculate number of completed months and years.  I copied
'it from the internet http://www.ozgrid.com/forum/showthread.php?t=37711
    Dim EarlyDate, LateDate As Date
    Dim tempDate, Date1, Date2 As Date
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
Public Function GetNextMonthliversaryDate(IssueDate As Date, dt As Date) As Date
'This function must account for a policy that is issued on the 29, 30 or 31st.
'In that case the next month might have less days and the monthliversay should be the end of the month
'For example if a policy was issued on the 1/31/2017, the monthliversary in in Febrary would be 2/28/2017 and the monthliversary in November would be the 11/30/2017
Dim IssueDay, EndOfThisMonth, EndOfNextMonth, Monthliversary1, Monthliversary2
IssueDay = Day(IssueDate)

EndOfThisMonth = DateSerial(Year(dt), Month(dt) + 1, 0)
EndOfNextMonth = DateSerial(Year(dt), Month(dt) + 2, 0)

Monthliversary1 = DateSerial(Year(dt), Month(dt), WorksheetFunction.Min(IssueDay, Day(EndOfThisMonth)))
Monthliversary2 = DateSerial(Year(dt), Month(dt) + 1, WorksheetFunction.Min(IssueDay, Day(EndOfNextMonth)))

If dt < Monthliversary1 Then
 GetNextMonthliversaryDate = Monthliversary1
Else
  GetNextMonthliversaryDate = Monthliversary2
End If


End Function
Public Function IfEmpty(CheckValue As Variant, AlternateValue As Variant)
    If IsEmpty(CheckValue) Then
        IfEmpty = AlternateValue
    Else
        IfEmpty = CheckValue
    End If
End Function

Public Function FindIndex(ary As Variant, TargetValue As Variant) As Integer
Dim x As Integer
For x = LBound(ary) To UBound(ary)
    If ary(x) = TargetValue Then
        FindIndex = x
        Exit Function
    End If
Next
FindIndex = LBound(ary) - 1

End Function

Public Function MonthOfYear(IssueDate As Date, ValuationDate As Date) As Integer
'This function finds the month of year for any valuation date.  This function returns a value from 1 to 12
Dim IssueDay As Integer, ValuationDay As Integer, MonthOfYear_OffMonthliversary As Integer, EOM_Valuation As Integer
IssueDay = Day(IssueDate)
ValuationDay = Day(ValuationDate)

If ValuationDay >= IssueDay Then
    MonthOfYear_OffMonthliversary = MonthOfYear(Month(IssueDate), Month(ValuationDate))
Else
    If ValuationDay < IssueDay Then
        'If ValuationDay is less than the IssueDay but its the last day of that month, then
        'its a monthliversary.  For example if policy is issued on 1/30/2013 and the valuation date
        'is 2/28/2013, then the valuation date is a monthliversary
        
        'End of Month for the valuation month
        EOM_Valuation = Day(DateSerial(Year(ValuationDate), Month(ValuationDate) + 1, 0))
        If ValuationDay = EOM_Valuation Then
            MonthOfYear_OffMonthliversary = MonthOfYear(Month(IssueDate), Month(ValuationDate))
        Else
            MonthOfYear_OffMonthliversary = MonthOfYear(Month(IssueDate), Month(ValuationDate) - 1)
        End If
    End If
End If
    

End Function





