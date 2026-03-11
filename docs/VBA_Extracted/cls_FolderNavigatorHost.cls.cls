' Module: cls_FolderNavigatorHost.cls
' Type: Class Module
' Stream Path: VBA/cls_FolderNavigatorHost
' =========================================================

Attribute VB_Name = "cls_FolderNavigatorHost"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Option Explicit

Private WithEvents txtPath As MSForms.textBox
Attribute txtPath.VB_VarHelpID = -1
Private WithEvents lstContent As MSForms.Listbox
Attribute lstContent.VB_VarHelpID = -1
Private navigator As cls_FolderNavigator

Public Sub Initialize(ByRef textBox As MSForms.textBox, ByRef Listbox As MSForms.Listbox, ByVal baseFolder As String, Optional ByVal ShowFullPath As Boolean = True)
    Set txtPath = textBox
    Set lstContent = Listbox
    Set navigator = New cls_FolderNavigator
    navigator.Initialize txtPath, lstContent, baseFolder, ShowFullPath
End Sub
Public Property Get CurrentPath() As String
    CurrentPath = navigator.CurrentPath
End Property
'Private Sub txtPath_MouseUp(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
'    If Button = 2 Then  ' 2 represents right mouse button
'        navigator.NavigateUp
'    End If
'End Sub

Private Sub txtPath_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    OpenFolder (CurrentPath)
End Sub

Private Sub lstContent_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    navigator.NavigateToSelected
End Sub

Private Sub lstContent_MouseUp(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
    If Button = 2 Then  ' 2 represents right mouse button
        navigator.NavigateUp
    End If
End Sub

Public Property Get ShowFullPath() As Boolean
    ShowFullPath = navigator.ShowFullPath
End Property

Public Property Let ShowFullPath(ByVal value As Boolean)
    navigator.ShowFullPath = value
End Property

Private Sub Class_Terminate()
    Set navigator = Nothing
    Set txtPath = Nothing
    Set lstContent = Nothing
End Sub


