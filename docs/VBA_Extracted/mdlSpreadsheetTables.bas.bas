' Module: mdlSpreadsheetTables.bas
' Type: Standard Module
' Stream Path: VBA/mdlSpreadsheetTables
' =========================================================

Attribute VB_Name = "mdlSpreadsheetTables"
Dim mFA_Plancode As cls_FilterArray
Dim mFA_Mortality As cls_FilterArray
Dim blnInitialized As Boolean
Const DefaultValue = "---"

Public Enum ePlancodeTable
    Plancode = 1
    ProductClass
    ProductType
    ProductSubType
    ProductSubType2
    CommonName
    Group
End Enum

Private Sub Initialize()
    Dim TableRange As String
    Dim ary As Variant
    
    Set mFA_Plancode = New cls_FilterArray
        
    TableRange = OfficialPlancodeTable.Range("sPlancodeTableRange").value
    ary = OfficialPlancodeTable.Range(TableRange).value
    mFA_Plancode.Initialize ary
    
    Set mFA_Mortality = New cls_FilterArray
    TableRange = CKAPTB32.Range("sCKAPTB32TableRange").value
    ary = CKAPTB32.Range(TableRange).value
    mFA_Mortality.Initialize ary
    
    blnInitialized = True
    
End Sub

Public Function GetPlancodeDescription(strPlancode As String, ReturnValue As ePlancodeTable) As String
If Not blnInitialized Then Initialize

mFA_Plancode.ClearFilter
mFA_Plancode.AddFilterCriteria ePlancodeTable.Plancode, strPlancode
mFA_Plancode.ApplyFilter

Dim temparray As Variant
temparray = mFA_Plancode.FilteredArray(False)

If IsArrayEmpty(temparray) Then
    GetPlancodeDescription = "Not Found"
Else
    GetPlancodeDescription = temparray(1, ReturnValue)
End If
End Function


Public Function GetMortalityTableDescription(strMortalityCode As String, Optional ReturnValue As Integer = 5) As String
If Not blnInitialized Then Initialize

mFA_Mortality.ClearFilter
mFA_Mortality.AddFilterCriteria 1, strMortalityCode
mFA_Mortality.ApplyFilter

Dim temparray As Variant
temparray = mFA_Mortality.FilteredArray(False)

If IsArrayEmpty(temparray) Then
    GetMortalityTableDescription = "Not Found"
Else
    GetMortalityTableDescription = temparray(1, ReturnValue)
End If
End Function




