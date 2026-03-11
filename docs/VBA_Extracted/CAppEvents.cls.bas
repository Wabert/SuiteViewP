' Module: CAppEvents.cls
' Type: Standard Module
' Stream Path: VBA/CAppEvents
' =========================================================

Attribute VB_Name = "CAppEvents"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Option Explicit
Public WithEvents App As Application
Attribute App.VB_VarHelpID = -1

'prevent re-entrance when we close the workbook programmatically
Private mBusy As Boolean

Private Sub App_WorkbookBeforeClose( _
        ByVal wb As Workbook, Cancel As Boolean)

    'Ignore our own forced close
    If mBusy Then Exit Sub
    
    Debug.Print "App_WorkbookBeforeClose:  " & wb.name
    
    'Skip if the main (task-bar) workbook itself is closing
    If wb Is ThisWorkbook Then Exit Sub
    
    'Will there be **no** visible windows after this workbook is gone?
    If VisibleWorkbookWindows = 2 Then
        
        '1) keep Excel alive
        Cancel = True                       'stop Excel completing its shutdown
        
        '2) unhide (or create) one window for our hidden main workbook
        EnsureMainWorkbookWindow            'code below
        
        '3) re-close the user’s workbook for real
        mBusy = True
        wb.Close SaveChanges:=False
        mBusy = False
    End If
End Sub

'Count workbook windows that are currently visible
Private Function VisibleWorkbookWindows() As Long
    Dim w As Window
    For Each w In Application.Windows
        If w.Visible Then VisibleWorkbookWindows = VisibleWorkbookWindows + 1
    Next w
End Function

'Guarantee that ThisWorkbook owns at least one visible window
Private Sub EnsureMainWorkbookWindow()
    Dim w As Window
    
    '– if ThisWorkbook already has a visible window, we’re done
    For Each w In ThisWorkbook.Windows
        If w.Visible Then Exit Sub
    Next w
    
    Debug.Print "App_WorkbookBeforeClose:  " & w.caption
    
    '– else un-hide the first hidden window, or create a new one
    If ThisWorkbook.Windows.Count > 0 Then
        Set w = ThisWorkbook.Windows(1)
    Else
        Set w = ThisWorkbook.NewWindow
    End If
    
    w.Visible = True               'make sure it is on screen
    w.WindowState = xlMinimized    'but keep it unobtrusive
End Sub


'Returns the count of windows that will remain visible
'after wb closes (ignores all windows owned by wb)
Private Function RemainingVisibleWindows(ByVal wb As Workbook) As Long
    Dim w As Window
    For Each w In Application.Windows
        If w.Visible Then                           'must be showing
            If Not (w.Parent Is wb) Then            'and not owned by closing wb
                RemainingVisibleWindows = RemainingVisibleWindows + 1
            End If
        End If
    Next w
End Function


