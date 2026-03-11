' Module: frmHome.frm
' Type: Standard Module
' Stream Path: VBA/frmHome
' =========================================================

Attribute VB_Name = "frmHome"
Attribute VB_Base = "0{E9AA9CAA-6313-4E55-8C25-5C187989EBB8}{7ED1551A-1350-4E3C-AF04-B99CA3F650BF}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Option Explicit

'-------------------------------------------------------------------------
'Private Const FORM_MINHEIGHT As Single = 35
'Private Const FORM_MINWIDTH As Single = 125
'Private Const FORM_INIT_HEIGHT As Single = 210
'Private Const FORM_INIT_WIDTH As Single = 82
'Private Const FORM_MIDDLE_WIDTH As Single = 130

'Private Const FORM_SMALLVIEW_WIDTH As Single = 82
'Private Const FORM_MEDIUMVIEW_WIDTH As Single = 180
'Private Const FORM_LARGEVIEW_WIDTH As Single = 620

'Adjustments used when docking form
'Private Const TOP_ADJUST = 5
'Private Const BOTTOM_ADJUST = 15
'Private Const LEFT_ADJUST = 5

'Public isDragging As Boolean
'Public dragOffsetX As Single
'Public dragOffsetY As Single
'Public dragLabel As MSForms.Label

'Public isCustomizeMode As Boolean
'Dim isMinimized As Boolean
'Private dragEnabled As Boolean
'Private mViewSize As String

'Private Timer As clsHiResTimer
'Private holdActive As Boolean
'Private mouseDownX As Single, mouseDownY As Single
'Private Const HOLD_THRESHOLD As Double = 3 ' seconds
'Private Const MOVE_TOLERANCE As Single = 5 ' pixels


Dim originalTop As Single, originalLeft As Single
Dim originalWidth As Single, originalHeight As Single
Dim origTextBox_Policy_Top As Single, origTextBox_Policy_Left As Single
Dim origLabel_CloseForm_Left As Single, origLabel_GetPolicy_Top As Single
Dim origLabel_GetPolicy_Left As Single, origLabel_GetPolicy_width As Single
Dim origLabel_GetPolicy_caption As String

Private blnInit As Boolean
Private blnWBVisible As Boolean

Private fHWnd As LongPtr

Private mDctForms As Dictionary
Private mColForms As Collection
Private mMyLinks As clsLinkHandler
Private frmWindows As TB_WindowControl
Private frmLinks As TB_Links

Private blnTaskbarLock As Boolean
Private blnWindowsVisisble As Boolean
Public wbWindowLabel As clsWindowLabel
Public mTB_Width_pixels As Single, mTB_Height_pixels As Single
Public mTB_Top_pixels As Single, mTB_Left_pixels As Single

Public CompanyList


Private Sub ComboBox_Region_Change()

End Sub

Private Sub UserForm_Initialize()
    Set mDctForms = New Dictionary
    Set mColForms = New Collection
    
    '------------- frmHome Init ------------------
    Me.caption = ThisWorkbook.name
    
    ComboBox_Region.AddItem "CKPR"
    ComboBox_Region.AddItem "CKMO"
    ComboBox_Region.AddItem "CKAS"
    ComboBox_Region.AddItem "CKSR"
    ComboBox_Region.value = "CKPR"
    
    Me.ComboBox_SnapDestination.AddItem "Word"
    Me.ComboBox_SnapDestination.AddItem "Outlook"
    Me.ComboBox_SnapDestination.value = "Word"
    
    ComboBox_Region.Visible = True
    
    ComboBox_CompanyCode.List = Array("", "", "01", "04", "06", "08", "26")
    
    UserForm_Activate

End Sub

Private Sub UserForm_Activate()
    
    'Code in this block should only be called once but it couldnt run effectivily in the UserForm_Initialize sub so it was put here
    If Not blnInit Then
        
        '--------------------------  Main Form setup -----------------------------
            'helper in modWindowManagerEnum
        MyTaskbar_Handle = WAPI_WindowHandleFromCaption(Me.caption)
        WAPI_SetWindowTopMost Me, True
        PrimeDragDropSystem Me
        WAPI_RemoveTitleBar Me
        
        
        
        '------------------  Allocate desktop space for new taskbar ----------------------------
        Dim NewTaskBar_HeightPixels As Long
        Dim WindowsTaskBar_HeightPixels As Long
        Dim Taskbar_pixel_width As Single, Taskbar_pixel_height As Single, Taskbar_pixel_top As Single, Taskbar_pixel_left As Single

        NewTaskBar_HeightPixels = 37
        WindowsTaskBar_HeightPixels = GetSystemTaskbarThickness

        CreateCustomTaskbarSpace Me, WindowsTaskBar_HeightPixels + NewTaskBar_HeightPixels, Taskbar_pixel_width, Taskbar_pixel_height, Taskbar_pixel_top, Taskbar_pixel_left
        
        '------------------ Define Postion for new taskbar above windows taskbar --------------
        mTB_Width_pixels = Taskbar_pixel_width
        mTB_Height_pixels = NewTaskBar_HeightPixels
        mTB_Left_pixels = Taskbar_pixel_left
        mTB_Top_pixels = Taskbar_pixel_top
               
                
                
        '--------------------------  Windows form setup -----------------------------
        Set frmWindows = New TB_WindowControl
        Load frmWindows
        frmWindows.Initialize Me, PixelsToPointsY(mTB_Top_pixels), PixelsToPointsY(mTB_Width_pixels)
        WAPI_SetWindowTopMost frmWindows
        WAPI_RemoveTitleBar frmWindows
        WAPI_MakeFormResizable frmWindows
        frmWindows.Refresh
        

        '--------------------------  Links form setup -----------------------------
        Set mMyLinks = New clsLinkHandler
        mMyLinks.Initialization PixelsToPointsY(mTB_Top_pixels)
       

        blnInit = True
    End If
    
End Sub

Public Sub SetTaskBarPosition()
    WAPI_FormResizeMove Me, "Pixels", mTB_Width_pixels, mTB_Height_pixels, mTB_Top_pixels, mTB_Left_pixels
    Label_CloseForm.left = PixelsToPointsX(mTB_Width_pixels - mTB_Height_pixels)
    Label_TrackWindows.left = Label_CloseForm.left - Label_TrackWindows.width - 2
    blnTaskbarLock = True
    MakeFormTopLevel Me
    


End Sub

Public Function MyHWnd() As LongPtr
    MyHWnd = fHWnd
End Function

Private Sub Label_TrackWindows_Click()
    If glbUnlock Then
        'Flip form visibility
        If frmWindows.Visible Then
            frmWindows.Refresh
            frmWindows.Hide                 'quicker than Unload: keeps its state
        Else
            frmWindows.Refresh
            frmWindows.Show vbModeless
        End If
    End If
End Sub

Private Sub Label_SnapShot_Click()
    Select Case Me.ComboBox_SnapDestination
        Case "Word": CaptureDesktopToWord_APPEND
        Case "Outlook": CaptureDesktopToOutlook_APPEND
    End Select
End Sub

Private Sub Label_Badge_MouseDown(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)

    If Button = 2 Then
        glbUnlock = True
        MsgBox "Unlocked!"
        Label_TAIAudit.Visible = True
        'Label_TrackWindows.Visible = True
    End If
    

End Sub
Private Sub Label_Badge_Click()
    ToggleExcelVisibilityWithZOrder
End Sub

Private Sub ToggleExcelVisibilityWithZOrder()
    Static isHidden As Boolean
    Static workbookOrder As Collection

    Dim wb As Workbook
    Dim i As Long

    If isHidden Then
        ' --- Unhide Excel ---
        Application.Visible = True
        DoEvents

        ' --- Restore workbook activation order (reverse to simulate Z-order) ---
        If Not workbookOrder Is Nothing Then
            For i = workbookOrder.Count To 1 Step -1
                On Error Resume Next
                Set wb = Application.Workbooks(workbookOrder(i))
                If Not wb Is Nothing Then wb.Activate
                DoEvents
                On Error GoTo 0
            Next i
        End If

        isHidden = False

    Else
        ' --- Store current workbook Z-order ---
        Set workbookOrder = New Collection
        For Each wb In Application.Workbooks
            workbookOrder.Add wb.name
        Next wb

        ' --- Hide Excel ---
        Application.Visible = False
        isHidden = True
    End If

   
End Sub

'==================================== Buttons/Labels ==========================================

Private Sub TextBox_Policy_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    'If glbUnlock Then TextBox_Policy.value = ""
End Sub

Private Sub Label_CloseForm_Click()
    CloseMe
    CloseMyTaskbar
End Sub
Private Sub Label_CyberlifeAudit_Click()
    OpenAuditForm
End Sub
Private Sub Label_GetPolicy_Click()
    If Me.TextBox_Policy.value = "" Then Exit Sub
    Dim NewPolicy As cls_PolicyInformation
    CreatePolicyForm GetPolicy(Me.TextBox_Policy, Me.ComboBox_Region, "I", Me.ComboBox_CompanyCode.value)
    Set NewPolicy = Nothing
End Sub

Private Sub Label_TAIAudit_Click()
    OpenTAIAuditForm
End Sub


Public Sub BringToTop()
    WAPI_SetWindowTopMost Me
End Sub

'===================================== Open other forms ======================================
Public Sub OpenAuditForm()
    Dim frm As frmAudit
    Set frm = New frmAudit
    mColForms.Add frm
    
    frm.Show vbModeless
    If Not frm.IsPopulated Then frm.PopulateForm
        
    'Set frm = Nothing
  
End Sub


Public Sub OpenTAIAuditForm()
    Dim frm As frmAuditTAI
    Set frm = New frmAuditTAI
    mColForms.Add frm
    
    frm.Show vbModeless
    If Not frm.IsPopulated Then frm.PopulateForm
End Sub

Public Sub OpenPolicyListForm()
    frmPolicyList.Show vbModeless
    
    'All the controls in the Audit form were not rendering correctly upon adlfrm"Audit.show.
    'In order to help render all the controls correclty I've added a DoEvents then moved the audit form a bit
    DoEvents
    frmPolicyList.left = frmPolicyList.left + 10
End Sub

Private Sub UserForm_MouseDown(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
    
    '2 = right click
    If Button = 2 Then
        If mMyLinks.LinkFormIsVisible Then
            mMyLinks.HideLinks
        Else
            mMyLinks.ShowLinks X - 35, PixelsToPointsY(mTB_Top_pixels)
        End If
    End If
End Sub

Private Sub UserForm_QueryClose(Cancel As Integer, CloseMode As Integer)
    WAPI_CleanupAll
    'StopRefreshTimer
    Dim i As Long
    For i = mColForms.Count To 1 Step -1
        mColForms.Remove i
    Next
    Set mColForms = Nothing
    RemoveAppBar Me
    Unload frmWindows
    
End Sub


Public Sub CloseMe()
    Dim key
    For Each key In mDctForms.Keys
        Unload mDctForms(key)
    Next
    Unload Me
End Sub
Private Sub UserForm_Terminate()
    CloseMe
    CloseMyTaskbar
End Sub
