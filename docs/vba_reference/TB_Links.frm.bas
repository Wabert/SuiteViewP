' Module: TB_Links.frm
' Type: Standard Module
' Stream Path: VBA/TB_Links
' =========================================================

Attribute VB_Name = "TB_Links"
Attribute VB_Base = "0{D55C382B-C6AC-47B2-8F93-392265FBB5E3}{8C5F6916-8D1A-4048-99D4-75A6E8D9EB5F}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Private mTB_Top As Single

Public Sub Initialize(taskbarTop As Single)
    Me.ListBox_Links.height = Me.InsideHeight - Me.ListBox_Links.top - 3
    Me.ListBox_Links.width = Me.InsideWidth - Me.ListBox_Links.left - 3
    mTB_Top = taskbarTop
End Sub


Private Sub Label_Close_Click()
    Me.Hide
End Sub
Private Sub UserForm_Resize()
    
    If Me.width > 25 Then
        Me.Label_Close.left = Me.width - Me.Label_Close.width - 15
        Me.ListBox_Links.height = Me.InsideHeight - Me.ListBox_Links.top - 3
        Me.ListBox_Links.width = Me.InsideWidth - Me.ListBox_Links.left - 3
    Else
        Me.width = 50
    End If
End Sub

Public Sub AdjustSize(listView As String)
'    If listView = "List" Then
'        Dim newheight As Single
'        Dim listbox_height_for_rows
'        listbox_height_for_rows = GetApproxListBoxHeight_InPoints(ListBox_Links)
'
'        newheight = Application.WorksheetFunction.Max(400 - ListBox_Links.top - 3, listbox_height_for_rows)
'        Me.ListBox_Links.height = newheight
'        Me.height = newheight + ListBox_Links.top + 3
'        Me.top = mTB_Top + Me.height
'    End If
    
    
    
End Sub

