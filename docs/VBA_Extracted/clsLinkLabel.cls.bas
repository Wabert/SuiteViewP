' Module: clsLinkLabel.cls
' Type: Standard Module
' Stream Path: VBA/clsLinkLabel
' =========================================================

Attribute VB_Name = "clsLinkLabel"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
' =======================================================================
'  clsLabelHandler – minimal, 64-bit-safe link label
'  Action: left-click ? open the file with the default application.
'  Last updated: 26-May-2025
' =======================================================================
Private Const SW_SHOWNORMAL As Long = 1

' ---------- Public state (same names frmHome expects) ------------------
Public WithEvents lbl As MSForms.Label
Attribute lbl.VB_VarHelpID = -1
Public LinkID     As Long
Public filepath   As String
Public filename   As String
Public fileAbbr   As String
Public fileclass  As eLinkClass
Public parentForm As Object ' keeps customise/drag logic intact
Attribute parentForm.VB_VarHelpID = -1
Private Const HOLD_MS As Long = 500  '1000 ms = 1 sec
Private INIT_WIDTH As Long
Private INIT_HEIGHT As Long
Private tooltipForm As frmLinkTip
Private mDownTick As Long
Private blnLongHoldTrigger As Boolean  'This is used to avoid the click action and only do the long hold action

Public Sub SetLabel(newlbl As Object)
Set lbl = newlbl

End Sub

Private Sub lbl_Click()
    Debug.Print "Click1, trigger = " & blnLongHoldTrigger
    If Not blnLongHoldTrigger Then OpenLink filepath
    blnLongHoldTrigger = False
    Debug.Print "Click1, trigger = " & blnLongHoldTrigger
End Sub

Private Sub lbl_MouseUp(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
    Select Case Button
        Case 1:
            If GetTimePunch - mDownTick >= HOLD_MS Then
            'right button – delete link
                blnLongHoldTrigger = True
                Debug.Print "Mouse Down, trigger = " & blnLongHoldTrigger
                If MsgBox("Delete this link?", vbYesNo + vbQuestion) = vbYes Then parentForm.RemoveLinkLabel LinkID
            End If
       Case 2:
            If Not tooltipForm Is Nothing Then
                Unload tooltipForm
                Set tooltipForm = Nothing
            End If
    
    End Select
End Sub
Private Sub lbl_MouseDown(ByVal Button As Integer, ByVal Shift As Integer, _
                          ByVal X As Single, ByVal Y As Single)
    Select Case Button
        Case 1:
            mDownTick = GetTimePunch          'store time stamp
        
        Case 2:
            If tooltipForm Is Nothing Then
                Dim fHWnd As LongPtr
                INIT_HEIGHT = 30
                INIT_WIDTH = 500
                
                Set tooltipForm = New frmLinkTip
                tooltipForm.Label_Linkname.caption = filename
                tooltipForm.Label_Linkname.Font.Bold = True
                tooltipForm.Label_Linkname.width = INIT_WIDTH - 5
                tooltipForm.Label_Linkname.height = INIT_HEIGHT
                
                tooltipForm.Label_Linkpath.caption = filepath   ' Set your custom text
                tooltipForm.Label_Linkpath.width = INIT_WIDTH - 5
                tooltipForm.Label_Linkpath.height = INIT_HEIGHT
                               
                WAPI_RemoveTitleBar tooltipForm
                
                ' Position the tooltip near the button
                tooltipForm.Show vbModeless
                
                WAPI_FormResizeMove tooltipForm, "Points", INIT_WIDTH, INIT_HEIGHT, parentForm.top - INIT_HEIGHT, parentForm.left + 5

            End If
    End Select
End Sub

Private Sub Class_Terminate()
    Set tooltipForm = Nothing
End Sub

'----------------- Button Drag logic for Customize Mode --------------------
'Private Sub lbl_MouseDown(ByVal Button As Integer, ByVal Shift As Integer, _
'                          ByVal X As Single, ByVal Y As Single)
'    Select Case Button
'        Case 1      ' left button – drag in customise mode
'            If ParentForm.isCustomizeMode Then
'                Set ParentForm.dragLabel = lbl
'                ParentForm.isDragging = True
'                ParentForm.dragOffsetX = X
'                ParentForm.dragOffsetY = Y
'            End If
'        Case 2      ' right button – delete link
'            If MsgBox("Delete this link?", vbYesNo + vbQuestion) = vbYes Then _
'                ParentForm.RemoveLinkLabel LinkID
'    End Select
'End Sub
'Private Sub lbl_MouseMove(ByVal Button As Integer, ByVal Shift As Integer, _
'                          ByVal X As Single, ByVal Y As Single)
'    If ParentForm.isDragging And lbl Is ParentForm.dragLabel Then
'        lbl.Left = lbl.Left + X - ParentForm.dragOffsetX
'        lbl.Top = lbl.Top + Y - ParentForm.dragOffsetY
'    End If
'End Sub
'
'Private Sub lbl_MouseUp(ByVal Button As Integer, ByVal Shift As Integer, _
'                        ByVal X As Single, ByVal Y As Single)
'    If Button = 1 Then
'        ParentForm.isDragging = False
'        Set ParentForm.dragLabel = Nothing
'    End If
'End Sub


