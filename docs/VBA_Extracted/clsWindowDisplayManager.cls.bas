' Module: clsWindowDisplayManager.cls
' Type: Standard Module
' Stream Path: VBA/clsWindowDisplayManager
' =========================================================

Attribute VB_Name = "clsWindowDisplayManager"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
'––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
' clsWindowDisplayManager  –  manages windows either via ListBox
'                      or via a Frame filled with Labels
'––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
Option Explicit

'====================  mode enum  =============================
'– LIST mode ––––––––––––––––––––––––––––––––––––––––––––––––
Private mHidden          As Collection         'handles we hid

'– FRAME mode –––––––––––––––––––––––––––––––––––––––––––––––
Private mFrame           As MSForms.frame
Private mMinHeight       As Single
Private mMinWidth        As Single
Private mColLabels       As Collection         'clsWindowLabel objects
Private mLblH            As Single             'label height
Private mLblGap          As Single             'vertical gap
Private Const cNormCol   As Long = &HFFFFFF           'white
Private Const cHideCol   As Long = &HC0C0C0           'light-grey
Private mLabelCount As Long
Private mMainFormCaption As String
Private mTotalLabelStackHeight As Single
Private mThisWB_hwnd As LongPtr


'===========================================  INITIALIZE  ==========================================
Public Sub Initialize(frame As MSForms.frame, frmCaption As String)
    mMainFormCaption = frmCaption
    
    'Store windows handle for this workbook to identify it later
    mThisWB_hwnd = WAPI_WindowHandleFromCaption(ThisWorkbook.name & " - Excel", "XLMAIN")
    
    Set mFrame = frame
    Set mColLabels = New Collection
    
    mLblH = 14
    mLblGap = 1
    mMinHeight = 160
    mMinWidth = 200

   

End Sub


'========================================  PUBLIC ACTIONS  ========================================

Public Sub Refresh()
    RefreshFrame mMainFormCaption
End Sub

Public Function ThisWorkbookIsVisible() As Boolean
    Dim o As clsWindowLabel
    For Each o In mColLabels
        If o.Handle = mThisWB_hwnd Then
            ThisWorkbookIsVisible = o.IsVisible
            Exit Function
        End If
    Next o
End Function

Public Sub HideThisWorkbook()
    Dim o As clsWindowLabel
    For Each o In mColLabels
        If o.Handle = mThisWB_hwnd Then
            o.HideIfVisible
            Exit Sub
        End If
    Next o
End Sub
Public Sub ShowThisWorkbook()
    Dim o As clsWindowLabel
    For Each o In mColLabels
        If o.Handle = mThisWB_hwnd Then
            o.RestoreIfHidden
            Exit Sub
        End If
    Next o
End Sub

Public Sub RestoreAll()
        Dim o As clsWindowLabel
        For Each o In mColLabels
            o.RestoreIfHidden
        Next o
End Sub
Public Sub ShowSelected()
        Dim o As clsWindowLabel
        For Each o In mColLabels
            If Not o.SelectedBlock Then o.RestoreIfHidden
        Next o
End Sub
Public Sub hideAll()
        Dim o As clsWindowLabel
        For Each o In mColLabels
            o.HideIfVisible
        Next o
End Sub

Private Sub CheckForScrollbars()
    With mFrame
    If mTotalLabelStackHeight > .InsideWidth Then
        .ScrollBars = fmScrollBarsVertical
        .ScrollHeight = mTotalLabelStackHeight + 20   ' Adjust this value as needed
    Else
        .ScrollBars = fmScrollBarsNone
    End If
    End With
End Sub

'Call on form close *or* in the form’s QueryClose
Public Sub CloseObject()
    RestoreAll
    'tidy-up
    Set mFrame = Nothing
    Set mColLabels = Nothing
End Sub

'Resize labels to frame width – call this from the UserForm’s Resize
Public Sub AdjustLayout(form_height As Single, form_width As Single)
    Dim newheight As Single, newwidth As Single
    
    newheight = IIf(mMinHeight > form_height - mFrame.top, mMinHeight, form_height - mFrame.top)
    newwidth = IIf(mMinWidth > form_width - mFrame.left, mMinWidth, form_width - mFrame.left)
    mFrame.height = newheight - 20
    mFrame.width = newwidth - 5
    Dim newW As Single: newW = mFrame.InsideWidth
    Dim o As clsWindowLabel
    For Each o In mColLabels
        o.ResizeToWidth newW
    Next o


End Sub

Private Sub RemoveHidden(ByVal hWnd As LongPtr)
    Dim i As Long
    For i = mHidden.Count To 1 Step -1
        If mHidden(i) = hWnd Then
            mHidden.Remove i
            Exit For
        End If
    Next i
End Sub

'====================  FRAME-MODE internals  =================
Private Sub RefreshFrame(ByVal ownerCaption As String)
    Dim data As Variant
    Dim i As Long
    Dim maxOrderIndex As Long
    Dim item As clsWindowLabel
    
    data = GetOpenWindows(ownerCaption)
    
    If IsEmpty(data) Then
        'Remove each label to properly dispose of the object
        For Each item In mColLabels
            Set item = Nothing
        Next
        Set mColLabels = Nothing
        Set mColLabels = New Collection
            
        For i = mFrame.Controls.Count - 1 To 0 Step -1
            mFrame.Controls.Remove mFrame.Controls(i).name
        Next i
        Exit Sub
    Else
        Dim k As Long
        'Debug.Print "RefreshFrame call"
        For k = LBound(data, 1) To UBound(data, 1)
        '    Debug.Print "   " & data(k, 1); " | " & data(k, 2) & " | " & data(k, 3)
        Next
    End If
    
    '3) Rebuild windows array.  Retrieve data on existing windows and add data for new windows (if any).
    'Ensure new windows are ordered after existing ones
        
    'Find max order index
    For Each item In mColLabels
        maxOrderIndex = IIf(item.ListOrder > maxOrderIndex, item.ListOrder, maxOrderIndex)
    Next
        
    Dim orderedWin() As Variant, n As Long, blnMatch As Boolean, r As Long, obj As clsWindowLabel
    For r = LBound(data, 1) To UBound(data, 1)
        
        blnMatch = False
        For Each item In mColLabels
            If item.Handle = data(r, 2) Then
                n = n + 1
                blnMatch = True
                
                'orderedWin is created in transposed form so redim can occur on last dimension
                ReDim Preserve orderedWin(1 To eCount, 1 To n)
                orderedWin(eTitle, n) = data(r, eTitle)
                orderedWin(eHwnd, n) = data(r, eHwnd)
                orderedWin(eListOrder, n) = item.ListOrder
                orderedWin(eIsSelected, n) = item.SelectedBlock
                orderedWin(eDisplayname, n) = data(r, eDisplayname)
                
            End If
        Next
        If Not blnMatch Then
            n = n + 1
            ReDim Preserve orderedWin(1 To eCount, 1 To n)
            orderedWin(eTitle, n) = data(r, eTitle)
            orderedWin(eHwnd, n) = data(r, eHwnd)
            orderedWin(eListOrder, n) = maxOrderIndex + n
            orderedWin(eIsSelected, n) = False
            orderedWin(eDisplayname, n) = data(r, eDisplayname)
        End If
    Next
    
    orderedWin = Transpose2D(orderedWin)
    orderedWin = Sort2D(orderedWin, 3)

    '3) create labels
    Dim newW As Single, topPos As Single, newOrder As Long
    newW = mFrame.InsideWidth
    
    'Remove each label to properly dispose of the object
    For Each item In mColLabels
        Set item = Nothing
    Next
    Set mColLabels = Nothing
    Set mColLabels = New Collection
    
    '1) wipe previous controls/objects
    For i = mFrame.Controls.Count - 1 To 0 Step -1
        mFrame.Controls.Remove mFrame.Controls(i).name
    Next i
    
    'Check to see if there are any new labels to build
    If n > 0 Then
        For r = LBound(orderedWin, 1) To UBound(orderedWin, 1)
            
            'Do not create a window label for MyTaskbar.  The user should not be able to hide it
            If MyTaskbar_Handle <> orderedWin(r, 2) Then
            
                Dim lbl As MSForms.Label
                Set lbl = mFrame.Controls.Add("Forms.Label.1", "lblWin_" & r, True)
        
                lbl.left = 0
                lbl.top = topPos
                lbl.width = newW
                lbl.height = mLblH
                lbl.ForeColor = &H404040
                lbl.Backcolor = &H80FF80
                newOrder = newOrder + 1
                Set obj = New clsWindowLabel
                obj.Init lbl, newOrder, orderedWin(r, eHwnd), orderedWin(r, eTitle), Me, cNormCol, cHideCol, orderedWin(r, eIsSelected), orderedWin(r, eDisplayname)
                mColLabels.Add obj
                topPos = topPos + mLblH + mLblGap
            End If
        Next r
    End If
    
    mTotalLabelStackHeight = topPos + mLblH
    
End Sub

'Transpose a 2-D Variant array of any bounds
Private Function Transpose2D(ByVal src As Variant) As Variant
    Dim rLo As Long, rHi As Long, cLo As Long, cHi As Long
    Dim outArr() As Variant
    Dim r As Long, c As Long
    
    rLo = LBound(src, 1): rHi = UBound(src, 1)
    cLo = LBound(src, 2): cHi = UBound(src, 2)
    
    ReDim outArr(cLo To cHi, rLo To rHi)     'swap dimensions
    
    For r = rLo To rHi
        For c = cLo To cHi
            outArr(c, r) = src(r, c)
        Next c
    Next r
    
    Transpose2D = outArr
End Function

