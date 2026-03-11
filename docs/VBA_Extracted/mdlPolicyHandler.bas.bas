' Module: mdlPolicyHandler.bas
' Type: Standard Module
' Stream Path: VBA/mdlPolicyHandler
' =========================================================

Attribute VB_Name = "mdlPolicyHandler"
Option Explicit
Private dctPolicyList As Dictionary
Private FormCollection As Collection
Private blnInitialized As Boolean
Private PolicyAudit As frmAudit
Private oRates As cls_Rates
Public Sub OpenAuditFormFromCommandBar()
  frmAudit.Show vbModeless
  If Not frmAudit.IsPopulated Then frmAudit.PopulateForm
End Sub
Private Function Initialize()
  Set dctPolicyList = New Dictionary
  Set FormCollection = New Collection
  Set oRates = New cls_Rates
  blnInitialized = True
End Function
Public Sub OpenPolicyFormFromCommandBar()
 If Not blnInitialized Then Initialize
 frmPolicyList.Show vbModeless
End Sub
Public Function GetPolicy(strPolicyNumber As String, Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I", Optional Company As String = "") As cls_PolicyInformation
Dim skey As String
If Not (blnInitialized) Then Initialize
strPolicyNumber = WorksheetFunction.Trim(strPolicyNumber)
skey = MakeKey(Company, strPolicyNumber, strDataSource, strSystemCode)
  If Not dctPolicyList.exists(skey) Then
    Dim NewPolicy As cls_PolicyInformation
    Set NewPolicy = New cls_PolicyInformation
                        
'    'If attempting to get the policy fails, refresh connection and try one more time
'    Dim attempt_count As Integer
'    Err.Clear
'
'    Debug.Print "Err: " & Err.Number & "  " & Err.Description
'    On Error Resume Next
'    Do
'        attempt_count = attempt_count + 1
        If Company = "" Then
            NewPolicy.classInitialize strPolicyNumber, strDataSource, , strSystemCode, oRates
        Else
            NewPolicy.classInitialize strPolicyNumber, strDataSource, Company, strSystemCode, oRates
        End If
        
'        Debug.Print Err.Number & "  " & Err.Description
'
'        If Err.Number = 0 Then Exit Do
'
'        If attempt_count > 1 Then Exit Do
'
'        LoadNewConnection strDataSource
'
'    Loop
    
'    On Error GoTo 0
    
    dctPolicyList.Add skey, NewPolicy
    Set NewPolicy = Nothing
  End If
Set GetPolicy = dctPolicyList(skey)

End Function
Public Sub CreatePolicyForm(objPolicy As cls_PolicyInformation)
'Creates a new PolicyMaster form and adds it to the collection.  This means more than
'one form can be open for the same policy.
If Not blnInitialized Then Initialize
  Dim frm As frmPolicyMasterTV
  Set frm = New frmPolicyMasterTV
  If objPolicy.PolicyNotFound Then
    MsgBox "Problem retrieving policy."
     Exit Sub
  End If
  
  
  If glbUnlock Then WAPI_SetWindowTopMost frm, True
  
  frm.classInitialize objPolicy
  frm.Show vbModeless
  FormCollection.Add frm
  Set frm = Nothing
End Sub
Public Function GetPolicyList() As Dictionary
  If Not blnInitialized Then Initialize
  Set GetPolicyList = dctPolicyList
End Function
Public Sub ClearPolicyList()
  Set dctPolicyList = Nothing
  blnInitialized = False
End Sub
Public Function MakeKey(strPolicyNumber As String, strDataSource As String, Optional strCompanyCode, Optional strSystemCode As String = "I") As String
  MakeKey = strCompanyCode & "_" & Application.WorksheetFunction.Trim(strPolicyNumber) & "_" & strDataSource & "_" & strSystemCode
End Function

