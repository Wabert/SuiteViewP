' Module: frmPlancodeSelection.frm
' Type: Standard Module
' Stream Path: VBA/frmPlancodeSelection
' =========================================================

Attribute VB_Name = "frmPlancodeSelection"
Attribute VB_Base = "0{A5DFC0F2-7070-4E49-AD4D-BBCD6B2F494B}{38B5A0F5-BC8C-42AF-917E-63B2B75C4F25}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Private mFB As cls_FilterBox
Private mAudit As frmAudit
Private blnActivate As Boolean

Public Sub classInitialize(UFAudit As MSForms.UserForm)
    Dim ActiveWB As Workbook
    Set mFB = New cls_FilterBox
    Set ActiveWB = ActiveWorkbook
    Set mAudit = UFAudit
    Me.caption = "Plancode Picker"
    ThisWorkbook.Activate
    Dim OfficialPlancodeTableRange As String
    OfficialPlancodeTableRange = Range("sPlancodeTableRange").value
    mFB.classInitialize framePlancodes, Range(OfficialPlancodeTableRange).value
    framePlancodes.caption = ""
    mFB.ColumnWidths = "50;60;110;130;140;180"
    ActiveWB.Activate
    blnActivate = True
End Sub
Public Function IsActive()
    IsActive = blnActivate
End Function

Private Sub Labe_AddPlancodes_Click()
'Add plancodes from filter box to Plancode list box
With mFB.Listbox
    For X = 1 To .ListCount
        ListBox_PlancodesSelected.AddItem .Column(0, X - 1)
    Next
End With
End Sub
Private Sub Label_AddAllPlancodes_Click()
'Adds all plancodes currently in the FilterBox to ListBox_PlancodesSelected
    With mFB.Listbox
    For X = 0 To .ListCount - 1
        ListBox_PlancodesSelected.AddItem .Column(0, X)
    Next
    End With
End Sub
Private Sub Label_AddSelectedPlancodes_Click()
'Adds only selected plancodes from the FilterBox to ListBox_PlancodesSelected
    With mFB.Listbox
        X = 0
        Do Until X >= .ListCount
           If .Selected(X) Then ListBox_PlancodesSelected.AddItem .Column(0, X)
           X = X + 1
        Loop
    End With
End Sub
Private Sub Label_RemoveAllPlancodes_Click()
'Removes all plancodes from ListBox_PlancodesSelected
    ListBox_PlancodesSelected.Clear
End Sub
Private Sub Label_RemoveSelectedPlancodes_Click()
'Removes only selected items from ListBox_PlancodesSelected
    
    
    With ListBox_PlancodesSelected
    X = .ListCount - 1
    Do Until X < 0
       If .Selected(X) Then .RemoveItem (X)
       X = X - 1
    Loop
    End With
End Sub
Private Sub Label_Export_Click()
    Dim temparray
    temparray = mFB.FilteredArray
    If Not InsertRowIntoArray(temparray, LBound(temparray), mFB.ArrayHeadings) Then
        MsgBox "Problem adding header array"
        Stop
    End If
    DumpArrayValuesIntoExcel temparray, 2, 1, True
End Sub

Private Sub Label_MoveToAudit_Click()
'Add plancodes from filter box to Plancode list box
For X = 0 To ListBox_PlancodesSelected.ListCount - 1
    mAudit.ListBox_MultiplePlancodes.AddItem ListBox_PlancodesSelected.Column(0, X)
Next
ListBox_PlancodesSelected.Clear
End Sub
Private Sub Label_ClearFilter_Click()
'Clears all filters from the FilterBox so that all plancodes are displayed
    mFB.ClearFilter
End Sub
