' Module: cls_PolicyData.cls
' Type: Class Module
' Stream Path: VBA/cls_PolicyData
' =========================================================

Attribute VB_Name = "cls_PolicyData"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Option Explicit
Private dctTables As Dictionary
Private dctDataRequested As Dictionary  'Key is the Table.Field name of data requested and the value is True/False depending on if the Table.Field name is found
Private dctDataItems As Dictionary
Private mPolicyID As String
Private mSystemCode As String
Private mPolicyNumber As String
Private mCompanyCode As String
Private mRegion As String
Private dctSourceInfo As Dictionary
Private mPolicyExists As Boolean


Public Sub classInitialize(sPolicynumber As String, Optional sRegion As String = "CKPR", Optional sCompanycode As Variant, Optional sSystemCode As String = "I")
    Set dctTables = New Dictionary
    Set dctDataItems = New Dictionary
    Set dctSourceInfo = New Dictionary
    sPolicynumber = WorksheetFunction.Trim(sPolicynumber)
    mPolicyExists = ValidatePolicyRequest(sPolicynumber, sRegion, sCompanycode, sSystemCode)
End Sub
Public Property Get PolicyNotFound() As Boolean
    PolicyNotFound = Not mPolicyExists
End Property
Property Get PolicyKey()
    PolicyKey = MakePolicyKey(mPolicyNumber, mRegion, mSystemCode)
End Property
Private Function ValidatePolicyRequest(sPolicynumber As String, sRegion As String, Optional sCompanycode As Variant, Optional sSystemCode As String = "I") As Boolean

ValidatePolicyRequest = False
Dim PolTable As Variant
PolTable = QueryPolicy(sPolicynumber, sRegion, sCompanycode, sSystemCode)

'If no records are found then policy does not exist.
'Notify and then exit function

If IsEmpty(PolTable) Then
'   If Not IsMissing(sCompanycode) Then
'     MsgBox "Cannot find policy " & sPolicynumber & " in " & sRegion & " for Company " & sCompanycode
'   Else
'     MsgBox "Cannot find policy " & sPolicynumber & " in " & sRegion
'   End If
   Exit Function
End If

'There are a small number of policynumbers used by more than one company.
'If more than one record is found for a policy then the company needs
'to be specified.  Display InputBox showing the company codes available.
'When one is selected call this Function again with the compnay code
'included.

If UBound(PolTable) > 1 Then
    'CK_CMP_CD = 0
    'CK_POLICY_NBR = 1
    'CK_SYS_CD = 2
    'TCH_POL_ID = 3
        
    
    Dim strCompanyCode As String
    Dim strAvailableCompanyCodes As String
    strAvailableCompanyCodes = PolTable(1, 0)

    
    Dim X
    For X = 2 To UBound(PolTable)
        strAvailableCompanyCodes = strAvailableCompanyCodes & ", " & PolTable(X, 0)
    Next
    'strCompanyCode = Format(InputBox("Need to specify company code for policy " & mPolicyNumber & ".  Company codes available are " & strAvailableCompanyCodes), "00")
    strCompanyCode = PolTable(2, 0)
    
    PolTable = QueryPolicy(sPolicynumber, sRegion, strCompanyCode, sSystemCode)
    
    'If there are no records or still more than one record then exit function without success
    If UBound(PolTable) = 0 Then Exit Function
    If UBound(PolTable) > 1 Then Exit Function

End If
  
'If record count = 1 then data is good; set mCompanyCode to CK_CMP_CD and set ValidatePolicyRequest to true
mCompanyCode = PolTable(1, 0)
mPolicyID = PolTable(1, 3)
mSystemCode = PolTable(1, 2)
mRegion = sRegion
mPolicyNumber = sPolicynumber
dctSourceInfo.Add "System", "Cyberlife"
dctSourceInfo.Add "SystemCode", mSystemCode
dctSourceInfo.Add "Region", mRegion
dctSourceInfo.Add "Policy", mPolicyNumber
dctSourceInfo.Add "CompanyCode", mCompanyCode
ValidatePolicyRequest = True
End Function
Private Function QueryPolicy(sPolicynumber As String, sRegion As String, Optional sCompanycode As Variant, Optional sSystemCode As String = "I") As Variant
    
    Dim aryWhereClause As Variant
    If IsMissing(sCompanycode) Then
        aryWhereClause = Array("CK_SYS_CD='" & sSystemCode & "' ", "CK_POLICY_NBR='" & sPolicynumber & "' ")
    Else
        aryWhereClause = Array("CK_SYS_CD='" & sSystemCode & "' ", "CK_POLICY_NBR='" & sPolicynumber & "' ", "CK_CMP_CD='" & sCompanycode & "' ")
    End If
 
    Dim sqlstring As String
 
    sqlstring = "SELECT  CK_CMP_CD, CK_POLICY_NBR, CK_SYS_CD, TCH_POL_ID FROM DB2TAB.LH_BAS_POL  WHERE " & Join(aryWhereClause, " AND ")
    sqlstring = SQLStringForRegion(sqlstring, sRegion)
 
    'Get query results

    QueryPolicy = FetchTable(sqlstring, sRegion)


End Function


Public Property Get PolicyNumber()
  PolicyNumber = mPolicyNumber
End Property
Public Property Get PolicyID()
  PolicyID = mPolicyID
End Property
Public Property Get System()
  System = dctSourceInfo("System")
End Property
Public Property Get region()
  region = mRegion
End Property
Public Property Get CompanyCode()
  CompanyCode = mCompanyCode
End Property
Public Property Get SystemCode()
  SystemCode = mSystemCode
End Property

Public Property Get DataItemDirect(strFullDesignation As String) As cls_PolicyDataItem
Dim ary As Variant
 ary = Split(strFullDesignation, ".")
 Set DataItemDirect = DataItem((ary(0)), (ary(1)))
End Property
Public Property Get DataItem(sTable As String, sField As String) As cls_PolicyDataItem
'This procedure checks the dataItem dictionary to see if dataitem has been requested before.  If yes, then the requested DataItem is found
'and returned. If no then data is queried, added to dctDataItems and then returned

'This procedure DOES NOT validate if sTable and sField are valid Table name or Field name or valid combination within DB2.
'Anything can be requested and if its not found in DB2, then a dataitem set to Nothing is returned

'If sTable.sField is in dctDataItem then return DataItem and exit funciton
'Finding sTable, sField in dctDataItem simply means this table, field has been requested
'before. But if its not found inthe DB2 tables its added to dctDataItem as Nothing
'So finding sTable.sField in dctDataItems does not guarantee there is data for that sTable.sField

Dim TblFld As String
TblFld = sTable & "." & sField
If dctDataItems.exists(TblFld) Then
  Set DataItem = dctDataItems(TblFld)
  Exit Property
End If


'The code below will execute only if sTable.sField has not been requested before

'First check to see if the table has already been queried,if not, query table.
If Not dctTables.exists(sTable) Then LoadDB2Table sTable

'Check to see if field exists in sTable by referencing field and checking to see if error results.
Dim blnsuccess As Boolean
Dim vntValue As Variant
blnsuccess = False
On Error GoTo ErrorHandler

Dim colIndex As Integer
colIndex = GetFieldIndex(dctTables(sTable), sField)
If colIndex = -1 Then GoTo ErrorHandler

'Field is found in table so create new data with valid parameters
Set dctDataItems(TblFld) = NewDataItem(dctTables(sTable), sTable, sField)
blnsuccess = True

ErrorHandler:
If Not (blnsuccess) Then
  'If there was an error referencing Field then add requested item to dictionary
  'but set it to Nothing
  Set dctDataItems(TblFld) = FieldNotFound(sTable, sField)
End If

Set DataItem = dctDataItems(TblFld)

End Property

Public Function GetTable(sTableName As String) As Variant
  If Not dctTables.exists(sTableName) Then LoadDB2Table sTableName
  GetTable = dctTables(sTableName)

End Function

Private Sub LoadDB2Table(sTableName As String)
If dctTables.exists(sTableName) Then Exit Sub
Dim aryTable As Variant

Dim aryWhereClause As Variant
Dim aryOrderClause As Variant

'This is used as an argument for most table lookups
aryWhereClause = Array("CK_SYS_CD='" & mSystemCode & "' ", "TCH_POL_ID='" & mPolicyID & "' ", "CK_CMP_CD='" & mCompanyCode & "' ")
 
Select Case sTableName

  Case "LH_BAS_POL", "TH_BAS_POL", "LH_FXD_PRM_POL":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
                       
  Case "LH_SST_XTR_CRG", "TH_SST_XTR_CRG":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_XTR_CRG_REQ", "TH_XTR_CRG_REQ":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)

  Case "LH_COM_TARGET":
    aryOrderClause = Array("AGT_COM_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
    
  Case "LH_COV_TARGET":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_POL_TARGET":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
            
  Case "LH_COV_INS_GDL_PRM":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
            
  Case "LH_COV_INS_RNL_RT":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
        
  Case "LH_COV_PHA":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
        
  Case "LH_NEW_BUS_COV_PHA":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
  
  Case "TH_COV_PHA":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_COV_TARGET":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
             
  Case "LH_CTT_COM_PHA_WA":
    aryOrderClause = Array("AGT_ITS_EFF_DT DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_FND_ALC":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
            
  Case "LH_FND_TRS_ALC_SET":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
            
  Case "LH_FND_VAL_LOAN":
    aryOrderClause = Array("MVRY_DT DESC", "FND_VAL_PHA_NBR DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
        
  Case "LH_CSH_VAL_LOAN":
    aryOrderClause = Array("MVRY_DT DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_NON_TRD_POL", "TH_NON_TRD_POL":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
            
  Case "LH_POL_FND_VAL_TOT":
    aryOrderClause = Array("MVRY_DT DESC", "FND_ID_CD DESC", "FND_VAL_PHA_NBR DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "VH_POL_HAS_LOC_CLT":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
             
  Case "LH_POL_MVRY_VAL":
    aryOrderClause = Array("MVRY_DT DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_POL_TARGET":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
            
  Case "LH_POL_TOTALS":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
            
  Case "LH_POL_YR_TOT":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
            
  Case "LH_SPM_BNF", "TH_SPM_BNF":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_SST_XTR_CRG":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_TAMRA_7_PY_PER":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
            
  Case "LH_TAMRA_7_PY_YR":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
            
  Case "LH_CTT_CLIENT":
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
 
  Case "FH_FIXED":
    aryWhereClause = Array("TCH_POL_ID='" & mPolicyID & "' ", "CK_CMP_CD='" & mCompanyCode & "' ")
    aryOrderClause = Array("ASOF_DT DESC, SEQ_NO DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
 
  Case "LH_UNAPPLIED_PTP":
    aryOrderClause = Array("ERN_DT_MO_YR_NBR DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
 
  Case "LH_APPLIED_PTP":
    aryOrderClause = Array("ERN_DT_MO_YR_NBR DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
 
  Case "LH_PAID_UP_ADD":
    aryOrderClause = Array("MVRY_DT DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
 
  Case "LH_ONE_YR_TRM_ADD"
    aryOrderClause = Array("MVRY_DT DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_PTP_ON_DEP":
    aryOrderClause = Array("MVRY_DT DESC")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_BNF_INS_RNL_RT":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_SST_XTR_RNL_RT":
    aryOrderClause = Array("COV_PHA_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
            
  Case "LH_TAMRA_MEC_PRM"  'as of 11/21/2016 there were no entries in this table in Production
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
  
  Case "LH_MO_ADD_PMT"  'as of 11/21/2016 there were no entries in this table in Production
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
  
  Case "LH_POL_MO_ITS_TOT"   'as of 11/21/2016 there were no entries in this table in Production
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
  
  Case "LH_POL_CAL_YR_TOT"
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
  
  Case "TH_COV_INS_RNL_RT"
    aryOrderClause = Array("COV_PHA_NBR", "PRS_CD", "PRS_SEQ_NBR", "SEG_IDX_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
  
  Case "LH_BNF_INS_GDL_PRM" 'as of 11/21/2016 there were no entries in this table in Production
    aryOrderClause = Array("COV_PHA_NBR", "PRS_CD", "PRS_SEQ_NBR", "SEG_IDX_NBR")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, aryOrderClause, mRegion)
  
  Case "TH_USER_GENERIC" '11/13/2024 - added
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)
    
  Case Else:
    aryWhereClause = Array("TCH_POL_ID='" & mPolicyID & "' ", "CK_CMP_CD='" & mCompanyCode & "' ")
    aryTable = GetTableFromDB2(sTableName, aryWhereClause, , mRegion)

End Select


If IsEmpty(aryTable) Then
  Set dctTables(sTableName) = Empty
  Exit Sub
End If
 

If UBound(aryTable, 1) = 0 Then
  Set dctTables(sTableName) = Empty
Else
  Set dctTables(sTableName) = aryTable
End If

End Sub

Private Function FieldNotFound(sTableName As String, sFieldName As String) As cls_PolicyDataItem
  
Dim DataItem As cls_PolicyDataItem
Set DataItem = New cls_PolicyDataItem
  
DataItem.classInitialize sTableName, sFieldName, Empty, dctSourceInfo
Set FieldNotFound = DataItem
End Function

Private Function NewDataItem(PolTable As Variant, sTableName As String, sFieldName As String) As cls_PolicyDataItem
  
Dim DataItem As cls_PolicyDataItem
Set DataItem = New cls_PolicyDataItem
  
DataItem.classInitialize sTableName, sFieldName, GetFieldValuesArray(PolTable, sFieldName), dctSourceInfo

Set NewDataItem = DataItem
End Function

Private Function GetFieldValuesArray(PolTable As Variant, Fieldname As String) As Variant
Dim colIndex As Integer
colIndex = GetFieldIndex(PolTable, Fieldname)

If colIndex = -1 Then
    MsgBox "Error: can find field " & Fieldname & " in table."
    Stop
End If

'Put the data into a base 0 vector array.  Do not include the first row with the field name
Dim aryData, X As Integer
ReDim aryData(0 To UBound(PolTable, 1) - 1)
For X = 0 To UBound(PolTable, 1) - 1
 aryData(X) = NullZ(PolTable(X + 1, colIndex), "Null")
Next

GetFieldValuesArray = aryData
End Function

Private Function GetTableFromDB2(sTableName As String, aryWhereClause, Optional aryOrderClause, Optional sRegion As String = "CKPR") As Variant
'This procedure returns an 2D array for the requested table.  Field names are in the first row of the array

Dim sqlstring As String
sqlstring = "SELECT * FROM DB2TAB." & sTableName
sqlstring = sqlstring & " WHERE " & Join(aryWhereClause, " AND ")
If Not IsMissing(aryOrderClause) Then sqlstring = sqlstring & " ORDER BY " & Join(aryOrderClause, ", ")

'If the region is CKAS or CKCS or CKSR then some substitutions are needed.  These are carried out in SQLStringForRegion
sqlstring = SQLStringForRegion(sqlstring, sRegion)

GetTableFromDB2 = FetchTable(sqlstring, sRegion)

End Function

Public Function GetFieldIndex(ByRef PolTable As Variant, sFieldName As String)
Dim X As Integer, xLock As Integer
xLock = -1
For X = LBound(PolTable, 2) To UBound(PolTable, 2)
    If PolTable(0, X) = sFieldName Then
        xLock = X
        Exit For
    End If
Next
GetFieldIndex = xLock
End Function

