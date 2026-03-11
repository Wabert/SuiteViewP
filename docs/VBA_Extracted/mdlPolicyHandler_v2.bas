' Module: mdlPolicyHandler.bas
' Type: Standard Module
' =========================================================
' PURPOSE: Policy caching and form management using cls_PolicyInformation (v2)
'
' USAGE:
'   Dim pol As cls_PolicyInformation
'   Set pol = GetPolicy("1234567", "CKPR", "I", "01")
'   If Not pol.Cancelled Then
'       Debug.Print pol.CovPlancode(1)
'   End If
'
' CHANGE LOG:
'   01/30/2026 RJH: Refactored to use new cls_PolicyInformation API
'                   - Changed classInitialize() to Add()
'                   - Removed DB2 layer dependency
'                   - SetRates() called on new policies
' =========================================================
Attribute VB_Name = "mdlPolicyHandler"

Option Explicit

Private dctPolicyList As Dictionary
Private FormCollection As Collection
Private blnInitialized As Boolean
Private PolicyAudit As frmAudit
Private oRates As cls_Rates

'===============================================================================================
' INITIALIZATION
'===============================================================================================

Private Sub Initialize()
    Set dctPolicyList = New Dictionary
    Set FormCollection = New Collection
    Set oRates = New cls_Rates
    blnInitialized = True
End Sub

'===============================================================================================
' PUBLIC API
'===============================================================================================

Public Sub OpenAuditFormFromCommandBar()
    frmAudit.Show vbModeless
    If Not frmAudit.IsPopulated Then frmAudit.PopulateForm
End Sub

Public Sub OpenPolicyFormFromCommandBar()
    If Not blnInitialized Then Initialize
    frmPolicyList.Show vbModeless
End Sub

'-----------------------------------------------------------------------------------------------
' GetPolicy - Get or create a cached policy object
' Parameters:
'   strPolicyNumber - Policy number to retrieve
'   strDataSource   - Region code (CKPR, CKMO, CKAS, CKCS)
'   strSystemCode   - System code (default "I")
'   Company         - Company code (optional, will prompt if multiple)
' Returns: cls_PolicyInformation object (check .Cancelled property for errors)
'-----------------------------------------------------------------------------------------------
Public Function GetPolicy(strPolicyNumber As String, _
                          Optional strDataSource As String = "CKPR", _
                          Optional strSystemCode As String = "I", _
                          Optional Company As String = "") As cls_PolicyInformation

    Dim skey As String
    
    If Not blnInitialized Then Initialize
    
    strPolicyNumber = WorksheetFunction.Trim(strPolicyNumber)
    skey = MakeKey(strPolicyNumber, strDataSource, Company, strSystemCode)
    
    If Not dctPolicyList.Exists(skey) Then
        Dim NewPolicy As cls_PolicyInformation
        Set NewPolicy = New cls_PolicyInformation
        
        ' Inject rates object
        NewPolicy.SetRates oRates
        
        ' Load policy using new Add() method
        Dim success As Boolean
        If Company = "" Then
            success = NewPolicy.Add(strPolicyNumber, , strSystemCode, strDataSource)
        Else
            success = NewPolicy.Add(strPolicyNumber, Company, strSystemCode, strDataSource)
        End If
        
        ' If policy loaded successfully, update key with actual company code
        If success Then
            skey = MakeKey(strPolicyNumber, strDataSource, CStr(NewPolicy.CompanyCode), strSystemCode)
        End If
        
        dctPolicyList.Add skey, NewPolicy
        Set NewPolicy = Nothing
    End If
    
    Set GetPolicy = dctPolicyList(skey)
End Function

'-----------------------------------------------------------------------------------------------
' CreatePolicyForm - Create and show a new policy detail form
'-----------------------------------------------------------------------------------------------
Public Sub CreatePolicyForm(objPolicy As cls_PolicyInformation)
    If Not blnInitialized Then Initialize
    
    ' Check if policy loaded successfully
    If objPolicy.Cancelled Then
        MsgBox "Problem retrieving policy: " & objPolicy.LastErrorMessage
        Exit Sub
    End If
    
    If objPolicy.Count = 0 Then
        MsgBox "No policy loaded."
        Exit Sub
    End If
    
    Dim frm As frmPolicyMasterTV
    Set frm = New frmPolicyMasterTV
    
    If glbUnlock Then WAPI_SetWindowTopMost frm, True
    
    frm.classInitialize objPolicy
    frm.Show vbModeless
    FormCollection.Add frm
    Set frm = Nothing
End Sub

'-----------------------------------------------------------------------------------------------
' GetPolicyList - Get the policy cache dictionary
'-----------------------------------------------------------------------------------------------
Public Function GetPolicyList() As Dictionary
    If Not blnInitialized Then Initialize
    Set GetPolicyList = dctPolicyList
End Function

'-----------------------------------------------------------------------------------------------
' ClearPolicyList - Clear the policy cache
'-----------------------------------------------------------------------------------------------
Public Sub ClearPolicyList()
    Set dctPolicyList = Nothing
    blnInitialized = False
End Sub

'-----------------------------------------------------------------------------------------------
' GetRatesObject - Get the shared rates object
'-----------------------------------------------------------------------------------------------
Public Function GetRatesObject() As cls_Rates
    If Not blnInitialized Then Initialize
    Set GetRatesObject = oRates
End Function

'===============================================================================================
' PRIVATE HELPERS
'===============================================================================================

Private Function MakeKey(strPolicyNumber As String, strDataSource As String, _
                         Optional strCompanyCode As String = "", _
                         Optional strSystemCode As String = "I") As String
    MakeKey = strCompanyCode & "_" & Application.WorksheetFunction.Trim(strPolicyNumber) & _
              "_" & strDataSource & "_" & strSystemCode
End Function
