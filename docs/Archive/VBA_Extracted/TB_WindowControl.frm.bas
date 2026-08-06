' Module: TB_WindowControl.frm
' Type: Standard Module
' Stream Path: VBA/TB_WindowControl
' =========================================================

Attribute VB_Name = "TB_WindowControl"
Attribute VB_Base = "0{85868F3B-1A6C-44C9-A889-96AC7D6316BA}{201B5A92-B700-4FBF-B9EE-6955A5D40BB2}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Option Explicit

Private mWinMgr As clsWindowDisplayManager
Private mParentForm As frmHome
'Private mDesktop_height As Single
'Private mstart_form_left As Single
Private Const MinFormWidth = 50
Private taskbarWidth As Single
Private taskbarTop As Single

Public Sub Initialize(parentForm As frmHome, pixelTop As Single, pixelWidth As Single)
    Set mParentForm = parentForm
    Set mWinMgr = New clsWindowDisplayManager
    mWinMgr.Initialize Me.frame_AppLabels, parentForm.caption
    
    taskbarWidth = pixelWidth
    taskbarTop = pixelTop
    
    Me.frame_AppLabels.top = 22
    Me.frame_AppLabels.left = 2
    Me.left = mParentForm.Label_TrackWindows.left - 10
    Me.height = 250
    Me.width = 300
    Me.left = taskbarWidth - Me.width
    Me.top = taskbarTop - Me.height + 8
     
End Sub

Private Sub Label_HideClick()
    Me.Hide
End Sub
Public Sub HideThisWorkbook()
    mWinMgr.HideThisWorkbook
End Sub
Public Sub ShowThisWorkbook()
    mWinMgr.ShowThisWorkbook
End Sub
Public Function ThisWorkbookVisible() As Boolean
    ThisWorkbookVisible = mWinMgr.ThisWorkbookIsVisible
End Function

Public Sub Refresh()
    mWinMgr.Refresh
End Sub

Private Sub Label_Close_Click()
    Me.Hide
End Sub

Private Sub Label_ShowAllWindows_Click()
    mWinMgr.RestoreAll
End Sub

Private Sub Label_HideAll_Click()
    mWinMgr.hideAll
End Sub

Private Sub Label1_Click()
    
End Sub

Private Sub UserForm_Resize()
    Me.width = Application.WorksheetFunction.Max(MinFormWidth, Me.width)
    Me.frame_AppLabels.width = Me.InsideWidth + 2     'Application.WorksheetFunction.Max(Me.width - Me.frame_AppLabels.left - 10, MinFormWidth)
    Me.frame_AppLabels.height = Me.InsideHeight + 16
    Me.Label_Close.left = taskbarWidth - Me.width
    
    mWinMgr.AdjustLayout Me.frame_AppLabels.height, Me.frame_AppLabels.width
End Sub
