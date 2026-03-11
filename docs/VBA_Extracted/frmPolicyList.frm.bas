' Module: frmPolicyList.frm
' Type: Standard Module
' Stream Path: VBA/frmPolicyList
' =========================================================

Attribute VB_Name = "frmPolicyList"
Attribute VB_Base = "0{74BE6240-48EA-4525-A4AD-ED240B33D1FE}{953D298C-5601-49B0-B57E-9CE98154306F}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False

Option Explicit

Const MIN_HEIGHT = 100
Const MAX_HEIGHT = 500



Private Sub Label_GetPolicy_Click()
    Dim NewPolicy As cls_PolicyInformation
     CreatePolicyForm GetPolicy(Me.TextBox_Policy, Me.ComboBox_Region, Me.ComboBox_SysCd, Me.ComboBox_CompanyCode)
     Set NewPolicy = Nothing
     PopulatePolicies
End Sub

Private Sub CommandButton1_Click()
 ClearPolicyList
 Me.ListBox_Policies.Clear
 PopulatePolicies
End Sub

Private Sub ListBox_Policies_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
Dim ErrorOccured As Boolean
  
  ErrorOccured = True
  
  'Sometime the ListIndex gets stuck at -1 even when its clear an item has
  'been selected.  Not sure why but the only way i know to fix it is to close excel and open again
  If ListBox_Policies.ListIndex < 0 Then
    MsgBox "A policy has not been selected.  If you've tried this a few times are you are still getting this message, you may need to close Excel and open it again."
    Exit Sub
  End If
 
  On Error GoTo ErrorHandler
  
  CreatePolicyForm GetPolicy(ListBox_Policies.Column(1, ListBox_Policies.ListIndex), ListBox_Policies.Column(2, ListBox_Policies.ListIndex), ListBox_Policies.Column(4, ListBox_Policies.ListIndex), ListBox_Policies.Column(0, ListBox_Policies.ListIndex))

  ErrorOccured = False
  
ErrorHandler:
 Dim strError As String
 strError = Err.Number
 If ErrorOccured Then MsgBox "Sorry, there is a problem loading this policy"

On Error GoTo 0
End Sub

Private Sub ListBox_Policies_MouseUp(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
Dim blnClear

    If Button = 2 Then  ' 2 represents right mouse button
        blnClear = MsgBox("Do you want to clear all policies?", vbYesNo)
        If blnClear = vbYes Then
            ClearPolicyList
            PopulatePolicies
        End If
    End If
End Sub

Private Sub TextBox_Policy_Change()
  TextBox_Policy.value = UCase(TextBox_Policy.value)  'CID0001: Any change to policy input box will automatically be uppercase
End Sub

Private Sub UserForm_Initialize()
 PopulateControls
 PopulatePolicies
End Sub

Private Sub PopulateControls()
With Me.ComboBox_Region
  .List = Array("CKPR", "CKMO", "CKAS", "CKCS", "CKSR")
  .value = "CKPR"
  .Font.Size = 8
End With
With Me.ComboBox_SysCd
  .List = Array("I", "P")
  .value = "I"
  .Font.Size = 8
End With

With Me.ComboBox_CompanyCode
  .List = Array("01", "04", "06", "08", "26")
  .value = "01"
  .Font.Size = 8
End With


End Sub

Public Sub PopulatePolicies()
Dim Pols As Dictionary
Set Pols = GetPolicyList

ListBox_Policies.Clear

If Pols.Count = 0 Then Exit Sub

'Fill ListBox_Policies with PolicyNumbers and Region
Dim ItemCount As Integer
Dim pol As cls_PolicyInformation
Dim skey As Variant
With ListBox_Policies
    For Each skey In Pols
    Set pol = Pols(skey)
     If Not pol.PolicyNotFound Then
         ItemCount = ItemCount + 1
         .AddItem pol.CompanyCode
         .Column(1, ItemCount - 1) = pol.PolicyNumber
         .Column(2, ItemCount - 1) = pol.region
         .Column(3, ItemCount - 1) = pol.CovFormNumber(1)
         .Column(4, ItemCount - 1) = pol.SystemCode
         
     End If
    Next
End With
ListBox_Policies.SetFocus
ListBox_Policies.height = WorksheetFunction.Max(MIN_HEIGHT, WorksheetFunction.Min((ListBox_Policies.Font.Size + 2) * ListBox_Policies.ListCount, MAX_HEIGHT))
Me.height = ListBox_Policies.height + 100

End Sub

