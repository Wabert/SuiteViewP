' Module: mdl_Command_Bar_Build.bas
' Type: Standard Module
' Stream Path: VBA/mdl_Command_Bar_Build
' =========================================================

Attribute VB_Name = "mdl_Command_Bar_Build"
Option Explicit

' Constants for command bar names used throughout the module
Const COMMANDBAR_NAME1 = "MyTaskBar"  ' Primary command bar name

Private frm As frmHome


'===========================================================================
' Purpose: Automatically runs when the workbook opens
' Actions: Creates the custom command bars and UI elements
'===========================================================================
Sub Auto_Open()
    CreateCommandBar  ' Creates the custom command bars
End Sub

'===========================================================================
' Purpose: Automatically runs when the workbook closes
' Actions: Removes the primary command bar to clean up Excel's UI
'===========================================================================
Sub Auto_Close()
  RemoveCommandBar COMMANDBAR_NAME1
End Sub

'===========================================================================
' Purpose: Checks if a command bar with the specified name already exists
' Params:  strCommandBarName - Name of the command bar to check for
' Returns: Boolean - True if command bar exists, False if not
'===========================================================================
Private Function CommandBarExists(strCommandBarName As String) As Boolean
Dim blnExists As Boolean
blnExists = False
Dim cb As CommandBar
  ' Loop through all command bars in Excel
  For Each cb In CommandBars
    If cb.name = COMMANDBAR_NAME1 Then  ' Note: This only checks for COMMANDBAR_NAME1, not the parameter
      blnExists = True
    End If
  Next cb
CommandBarExists = blnExists
End Function

'===========================================================================
' Purpose: Removes a command bar with the specified name if it exists
' Params:  strCommandBarName - Name of the command bar to remove
'===========================================================================
Sub RemoveCommandBar(strCommandBarName As String)
  Dim cb As CommandBar
  ' Loop through all command bars in Excel
  For Each cb In CommandBars
    If cb.name = strCommandBarName Then
      cb.Delete  ' Delete the command bar if found
      Exit Sub   ' Exit the subroutine once deleted
    End If
  Next cb
End Sub

'===========================================================================
' Purpose: Creates custom command bar with single control to open the MyTaskBar
' Creates:
'   1. CyberConnect1 - Contains MyTaskBar
'===========================================================================
Private Sub CreateCommandBar()
Dim cbMyCommandBar As CommandBar
Dim cbList As CommandBarButton
Dim cbQuery As CommandBarButton
Dim cbFormulas As CommandBarButton
Dim cbGetPolicy As CommandBarButton
Dim cbcboPolicyNumber As CommandBarComboBox
Dim cbcboRegion As CommandBarComboBox
   
    ' Remove any existing command bars with the same names to prevent duplicates
    RemoveCommandBar COMMANDBAR_NAME1

    
    ' Create the first command bar (CyberConnect1)
    Set cbMyCommandBar = Application.CommandBars.Add(name:=COMMANDBAR_NAME1, Temporary:=True)
    
    ' Configure the first command bar's appearance
    With cbMyCommandBar
    .Visible = True
    .position = msoBarTop
    .rowIndex = msoBarRowLast
    End With
        
    ' Add button
    Dim cbFake As CommandBarButton
    Set cbFake = cbMyCommandBar.Controls.Add(Type:=msoControlButton, id:=2)
    With cbFake
        .style = msoButtonCaption
        .OnAction = "LaunchMyTaskbar"  ' Action to execute when clicked
        .caption = "Launch Taskbar"
    End With

End Sub

Public Sub LaunchMyTaskbar()
  If frm Is Nothing Then
    Set frm = New frmHome
    frm.Show vbModeless
    frm.SetTaskBarPosition
  End If

End Sub

Public Sub CloseMyTaskbar()
    If Not frm Is Nothing Then
        frm.CloseMe
        Set frm = Nothing
    End If
End Sub
