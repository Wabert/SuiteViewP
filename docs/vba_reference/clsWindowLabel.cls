' Module: clsWindowLabel.cls
' Type: Standard Module
' Stream Path: VBA/clsWindowLabel
' =========================================================

Attribute VB_Name = "clsWindowLabel"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
'––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
' clsWindowLabel – wraps a dynamically-created Label
'––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
Option Explicit

Private WithEvents mLbl As MSForms.Label   'the actual label control
Attribute mLbl.VB_VarHelpID = -1
Private mHWnd        As LongPtr            'handle of the window
Private mHiddenColor As Long               'colour when hidden
Private mNormalColor As Long               'colour when shown
Private mListOrder As Long                 'Specifies the order in which the label appears in the list
Private mSelectedBlock As Boolean
Private mTitle As String

'parent manager (allows manager-wide actions if ever needed)
Private mMgr As clsWindowDisplayManager

'==========  initialiser  ====================================
Friend Sub Init( _
        ByRef targetLabel As MSForms.Label, _
        ByVal ListOrder As Long, _
        ByVal hWnd As LongPtr, _
        ByVal title As String, _
        ByRef manager As clsWindowDisplayManager, _
        ByVal normalColour As Long, _
        ByVal hiddenColour As Long, _
        ByVal IsSelected As Boolean, _
        ByVal Displayname As String)

    mSelectedBlock = IsSelected
    Set mLbl = targetLabel
    mListOrder = ListOrder
    mHWnd = hWnd
    mTitle = title
    mLbl.caption = Displayname
    mLbl.Tag = CStr(hWnd)
    mLbl.AutoSize = False
    mLbl.WordWrap = False
    mLbl.BackStyle = fmBackStyleOpaque
    mLbl.SpecialEffect = fmSpecialEffectBump
    
    mNormalColor = &H80FF80
    mHiddenColor = hiddenColour
    
    If mSelectedBlock Then
        mLbl.Backcolor = mHiddenColor
    Else
        mLbl.Backcolor = mNormalColor
    End If
    
    Set mMgr = manager
End Sub
Property Get IsVisible() As Boolean
    IsVisible = Window_IsVisible(mHWnd)
End Property
Property Get ListOrder() As Long
    ListOrder = mListOrder
End Property

Property Get Handle() As LongPtr
    Handle = mHWnd
End Property
Property Get title() As String
    title = mTitle
End Property
Property Get Label() As MSForms.Label
    Set Label = mLbl
End Property

Property Get SelectedBlock() As Boolean
'mSelectedBlock is set to true if the user clicks the label to hide the app, as opposed to just clicking the "hide all" button
'That way, when the show button is clicked it will show everything except those that were selected to be hiddedn by the user
'This will allow the user to block some of the window noise that can pop up
    SelectedBlock = mSelectedBlock
    If mLbl.caption = "File Explorer - Coinsurance Agreement" Then Debug.Print mLbl.caption & "-SelectedBlock | " & mSelectedBlock
End Property
'==========  public helpers  =================================
Friend Sub ResizeToWidth(ByVal newwidth As Single)
    mLbl.width = newwidth
End Sub

Friend Sub RestoreIfHidden()
    If Not Window_IsVisible(mHWnd) Then
        Window_Show mHWnd, SW_SHOW
        mLbl.Backcolor = mNormalColor
        DoEvents
    End If
End Sub

Friend Sub HideIfVisible()
    If Window_IsVisible(mHWnd) Then
        Window_Show mHWnd, SW_HIDE
        mLbl.Backcolor = mHiddenColor
        DoEvents
    End If
End Sub


'==========  label click  ====================================
Private Sub mLbl_Click()
    If Window_IsVisible(mHWnd) Then          'show ? hide
        Window_Show mHWnd, SW_HIDE
        mLbl.Backcolor = mHiddenColor
        mSelectedBlock = True
    Else                                      'hide ? show
        Window_Show mHWnd, SW_SHOW
        mLbl.Backcolor = mNormalColor
        mSelectedBlock = False
    End If
    
    Debug.Print mLbl.caption & " | " & mSelectedBlock
    
End Sub

Private Sub Class_Terminate()
    Set mLbl = Nothing    'Label WithEvents
    Set mMgr = Nothing   'Back-reference

End Sub
