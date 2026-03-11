' Module: clsLinkHandler.cls
' Type: Standard Module
' Stream Path: VBA/clsLinkHandler
' =========================================================

Attribute VB_Name = "clsLinkHandler"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Option Explicit

Private mLinkMode As String
Private LinkInfoArray As Variant
Private linklabels As Dictionary
Private WithEvents lstLinks As MSForms.Listbox
Attribute lstLinks.VB_VarHelpID = -1
Private WithEvents lblAddLink As MSForms.Label
Attribute lblAddLink.VB_VarHelpID = -1
Private WithEvents lblView As MSForms.Label
Attribute lblView.VB_VarHelpID = -1
Private mTB_Top As Single
Private mfrm As TB_Links
Private FormHeightNeeded As Single
Private FormWidthNeeded As Single
Private Const LINK_FRM_MAX_HEIGHT = 600
Private Const LINK_FRM_MAX_WIDTH = 400
Private Const LINK_FRM_MIN_WIDTH = 110

Public Sub Initialization(taskbarTop As Single)
    
    Set linklabels = New Dictionary
    
    Set mfrm = New TB_Links
    mfrm.Initialize mTB_Top
    Load mfrm
    WAPI_SetWindowTopMost mfrm
    WAPI_RemoveTitleBar mfrm
    WAPI_MakeFormResizable mfrm
    
    Me.LinkMode = "List"
    LinkInfoArray = GetLinkTable
    mTB_Top = taskbarTop
    
    Set lstLinks = mfrm.ListBox_Links
    Set lblAddLink = mfrm.Label_AddLinks
    Set lblView = mfrm.Label_View
    
    mfrm.height = 200
    mfrm.width = 110
    LoadLinks
End Sub
Public Property Get LinkMode() As String
    LinkMode = mLinkMode
End Property
Public Property Let LinkMode(LinkMode As String)
'LinkMode = 'List' or 'Label'
    
       
    mLinkMode = LinkMode
    LoadLinks
    Debug.Print "LinkMode: " & mfrm.Visible
End Property
Public Sub ShowLinks(left As Single, taskbarTop As Single)
    If Not mfrm.Visible Then mfrm.Show vbModeless
    
    mfrm.left = left - 10
    mfrm.top = mTB_Top - mfrm.height + 8
End Sub
Public Sub HideLinks()
    mfrm.Hide
End Sub
Public Function LinkFormIsVisible() As Boolean
    LinkFormIsVisible = mfrm.Visible
End Function

Public Sub RemoveLink(removeID As Long)
    If IsArrayEmpty(LinkInfoArray) Then Exit Sub
    If removeID <= 0 Then Exit Sub
    
    Dim bln_remove As Boolean
    
    bln_remove = MsgBox("Would you like to remove " & LinkInfoArray(removeID, 2) & " your links?", vbYesNo)
    If bln_remove = vbNo Then Exit Sub
    
    If UBound(LinkInfoArray, 1) = 1 Then
        'If there is only one line and its being removed then set the array to empty
        LinkInfoArray = Empty
    Else
        Dim deleterow As Integer, X As Integer
        
        deleterow = DeleteRowFromArray(LinkInfoArray, removeID)
        
        'renumber the IDs
        For X = LBound(LinkInfoArray, 1) To UBound(LinkInfoArray, 1)
            LinkInfoArray(X, 1) = X
        Next
    End If
    WriteToLinkTable LinkInfoArray
    LoadLinks
    
    'Save now otherwise the user will close the workbook with out saving and lose these link changes
    ThisWorkbook.Save
    
    
 End Sub

Private Sub LoadLinks()
    If IsArrayEmpty(LinkInfoArray) Then
        Exit Sub
    End If
    
    Select Case mLinkMode
        Case "Label":
                    BuildLinkLabels
                    mfrm.ListBox_Links.Visible = False
        Case "List":
                    PopulateListBox
                    LinkLabelsVisible False
    End Select
    
    AdjustFormSize
End Sub
Private Sub AdjustFormSize()
    '------------------ Adjust the form size to fit link space needed  ----------------------------
    mfrm.height = FormHeightNeeded
    mfrm.top = mTB_Top - FormHeightNeeded + 5
    mfrm.width = FormWidthNeeded
    
 End Sub
Private Sub PopulateListBox()
    Dim i As Integer
    Dim LinkID As Integer, filename As String
    Dim filepath As String, fileAbbr As String
    
    
    With lstLinks
    .Clear
    .ColumnCount = 4                            'how many visible columns
    .ColumnWidths = "60 pt;0 pt;0 pt;0 pt"      'optional – semicolon-separated
        For i = 1 To UBound(LinkInfoArray, 1)
            LinkID = CInt(LinkInfoArray(i, 1))
            filename = LinkInfoArray(i, 2)
            filepath = LinkInfoArray(i, 3)
            fileAbbr = LinkInfoArray(i, 4)
            .AddItem filename
            .List(.ListCount - 1, 1) = filepath
            .List(.ListCount - 1, 2) = fileAbbr
            .List(.ListCount - 1, 3) = LinkID
        Next
        .Visible = True
    End With
    FormWidthNeeded = fmin(LINK_FRM_MAX_WIDTH, mfrm.ListBox_Links.left + 150 + mfrm.ListBox_Links.left)
    FormHeightNeeded = fmin(LINK_FRM_MAX_HEIGHT, mfrm.ListBox_Links.top + GetApproxListBoxHeight_InPoints(mfrm.ListBox_Links) + 10)
End Sub

Private Sub LinkLabelsVisible(bln As Boolean)
    Dim item
    ' Loop backwards to safely remove controls
    For Each item In linklabels.items
        item.lbl.Visible = bln
    Next
End Sub
Private Sub ClearLinkLabels()
    Dim ctrl As Control
    Dim i As Long

    ' Loop backwards to safely remove controls
    With mfrm
    For i = .Controls.Count - 1 To 0 Step -1
        Set ctrl = .Controls(i)
        If TypeName(ctrl) = "Label" Then
            If ctrl.name Like "lblLink*" Then
                .Controls.Remove ctrl.name
            End If
        End If
    Next i
    End With
    
    ' Optionally clear the linklabels collection if used
    If Not linklabels Is Nothing Then
        Set linklabels = Nothing
    End If
End Sub

Private Sub Links_MouseDown(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
    '2 = right click
    If Button = 2 Then
        'Optional: move the selection to the row that was under the cursor
        Dim idx As Long
        idx = mfrm.ListBox_Links.ListIndex
        
        If idx < 0 Then Exit Sub
        
        RemoveLink mfrm.ListBox_Links.List(idx, 3)
    End If
End Sub

Private Sub lblAddLink_Click()
    Dim frmPrompt As frmChooseLink
    Set frmPrompt = New frmChooseLink
    
    'Create dct in this main form and pass it to frmChooseLink.  frmChooseLink will populate
    'the dictionary and the values will be aviable in this main form after frmChooseLink closes
    Dim dct As Dictionary
    Set dct = New Dictionary
    Set frmPrompt.DataDictionary = dct
    
    frmPrompt.Show vbModal
   
    If dct("linkpath") <> "" Then
        AddLink (dct("linkpath")), (dct("linkname")), (dct("linktype"))
    End If
   
   Set frmPrompt = Nothing
End Sub

Private Sub AddLink(filepath As String, filename As String, linktype As String)
    'Update the link array with the new link info
    If IsArrayEmpty(LinkInfoArray) Then
        Dim temparray2D(1 To 1, 1 To 4)
        temparray2D(1, 1) = 1
        temparray2D(1, 2) = filename
        temparray2D(1, 3) = filepath
        temparray2D(1, 4) = linktype
        LinkInfoArray = temparray2D
    Else
        Dim temparray(1 To 4)
        Dim Index As Long
        Dim blnsuccess As Boolean
        
        Index = UBound(LinkInfoArray, 1) + 1
        temparray(1) = Index
        temparray(2) = filename
        temparray(3) = filepath
        temparray(4) = linktype
        blnsuccess = InsertRowIntoArray(LinkInfoArray, Index, temparray)
        
        If Not blnsuccess Then
            MsgBox "LinkArry failed to update", vbOKCancel
            Exit Sub
        End If
    End If

    WriteToLinkTable LinkInfoArray
    LoadLinks
    
    'Save now otherwise the user will close the workbook with out saving and lose these link changes
    ThisWorkbook.Save
    
    
End Sub
Private Sub lblView_Click()
    If LinkMode = "Label" Then
        LinkMode = "List"
        
    Else
        LinkMode = "Label"
    End If
End Sub

Private Sub lstLinks_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    Dim selectedIndex As Long
    selectedIndex = lstLinks.ListIndex

    If selectedIndex <> -1 Then
        Dim filename As String, filepath As String, Index As String
        filename = lstLinks.List(selectedIndex, 0) ' Visible column
        filepath = lstLinks.List(selectedIndex, 1) ' Hidden column
        Index = lstLinks.List(selectedIndex, 2) ' Hidden column
    End If
    
    OpenLink filepath
    
End Sub


Private Sub BuildLinkLabels()
'Deletes any existing link labels and then builds them back from scratch.
    Dim i As Integer
    Dim newLabel As MSForms.Label
    Dim linklabel As clsLinkLabel
    Dim LinkID As Integer
    Dim filename As String, filepath As String, fileAbbr As String, filetype As String
    Dim labelSize As Single, labelheight As Single, labelwidth As Single
    Dim colCount As Long
    Dim LBRow As Integer, rowIndex As Long, colIndex As Long
    Dim spacing As Single
    Dim leftMargin As Single
    Dim topMargin As Single
    
    'Clear existing labels
    ClearLinkLabels
      
    If IsArrayEmpty(LinkInfoArray) Then
        Exit Sub
    End If
    
    'Initialize the collection to store label handlers
    Set linklabels = New Dictionary
    
    labelheight = 15
    labelwidth = 40
    spacing = 0
    colCount = 5
    leftMargin = mfrm.Label_AddLinks.left
    topMargin = mfrm.Label_AddLinks.top + mfrm.Label_AddLinks.height + 5
    
    
    'Used in position calculation

    
    LBRow = LBound(LinkInfoArray, 1)
    For i = 1 To UBound(LinkInfoArray, 1) ' Assuming row 1 is headers
        LinkID = CInt(LinkInfoArray(i, 1))
        filename = LinkInfoArray(i, 2)
        filepath = LinkInfoArray(i, 3)
        filetype = LinkInfoArray(i, 4)
        fileAbbr = left(filename, 8) 'LinkInfoArray(I, 4)
        ' Calculate row and column index for postioning
        rowIndex = (i - LBRow) \ colCount
        colIndex = (i - LBRow) Mod colCount

        ' Create a new label.
        Set newLabel = mfrm.Controls.Add("Forms.Label.1", "lblLink" & i, True)
        With newLabel
            .caption = fileAbbr
            .left = leftMargin + colIndex * (labelwidth + spacing)
            .top = topMargin + rowIndex * (labelheight + spacing)
            .width = labelwidth
            .height = labelheight
            .WordWrap = True
            .BackStyle = fmBackStyleOpaque
            .Backcolor = &H80000001
            .BorderStyle = fmBorderStyleSingle
            .SpecialEffect = fmSpecialEffectEtched
            .ForeColor = RGB(128, 128, 128)
        End With
        
        GetColorBasedOnFileType filepath, filetype, newLabel

        ' Create a new handler and assign the label and file path
        Set linklabel = New clsLinkLabel
        
        With linklabel
            .LinkID = LinkID
            .filepath = filepath
            .filename = filename
            .fileAbbr = fileAbbr
            .SetLabel newLabel

            Set .parentForm = mfrm
        End With
        linklabels.Add LinkID, linklabel

    Next i
    
    FormWidthNeeded = fmax(LINK_FRM_MIN_WIDTH, fmin(LINK_FRM_MAX_WIDTH, leftMargin + (colCount) * (labelwidth + spacing) + 15))
    FormHeightNeeded = fmin(LINK_FRM_MAX_HEIGHT, topMargin + (rowIndex + 1) * (labelheight + spacing) + 20)
    
    Debug.Print Join(Array(leftMargin, (colCount), labelwidth, spacing), " | ")
    Debug.Print Join(Array(topMargin, (rowIndex + 1), labelheight, spacing), " | ")
    Debug.Print FormWidthNeeded
    
End Sub

Private Sub Class_Terminate()
    
    
    Dim key
    For Each key In linklabels
        linklabels.Remove (key)
    Next
    
    Set linklabels = Nothing
    Set lstLinks = Nothing
    Set lblAddLink = Nothing
    Set lblView = Nothing
    Unload mfrm
    
End Sub

Private Sub lstLinks_MouseDown(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
If Button = 2 Then  '2 = right click
    RemoveLink lstLinks.ListIndex + 1
End If
End Sub
