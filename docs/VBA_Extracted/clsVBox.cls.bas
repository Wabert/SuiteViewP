' Module: clsVBox.cls
' Type: Standard Module
' Stream Path: VBA/clsVBox
' =========================================================

Attribute VB_Name = "clsVBox"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False

'RJH - 1/23/2017
'This class creates a GUI to interact with object cls_FilterArray
'It requires a frame and a source array.  The Array must be populated and have headers defined
'All the controls are created in the frame

Private mLBEvents As cls_ListBoxEvents

Private dctFH As Dictionary            'Items are of type clsVBoxHeader
Private moFrame As MSForms.frame
Private mSizeLabel As MSForms.Label     'This label is only used to determine the height of a given font size and font name.
                                        'The label is set to AutoSize and the label font is adjusted, and then the label height is read.  This was a trick i learned form JPK-ADS
                                        
Private dctColumnWidths As Dictionary   'Column widths can be adjusted at any time.  they are stored in this diction.  Default value is set with DEFAULT_WIDTH constant
Private dctHeaderTextAlign As Dictionary
Private mHeaderBackColor As Single
Private mDataArray As Variant
Private WithEvents mlbxData As MSForms.Listbox
Attribute mlbxData.VB_VarHelpID = -1
Private mDataBackColor As Single
Private dctDataTextAlign As Dictionary
Dim mbMarginOnLastColumn As Boolean


Private mbFilterOn As Boolean   'Will enable or disable filter operations
Dim moFilterArray As cls_FilterArray
Dim dctFilters As Dictionary
Dim mDeSelect As Boolean
Dim mUserFormcolor As Variant
Const DEFAULT_WIDTH As Single = 20
Const LISTBOXMARGIN As Single = 3
Const TEXT_MARGIN_IN_LISTBOX As Single = 5
Const SCROLLBARWIDTH As Single = 15

Event ListBoxDoubleClick(lbx As MSForms.Listbox)
Private mbRaiseDoubleClick As Boolean



Public Sub Initialize(oFrame As MSForms.frame, Optional Backgroundcolor)
    mbRaiseDoubleClick = RaiseDoubleClick
    mbFilterOn = True
    mDataBackColor = oFrame.Backcolor

    If Not IsMissing(Backgroundcolor) Then
        mUserFormcolor = Backgroundcolor
    Else
        mUserFormcolor = mDataBackColor
    End If
    
    Set moFrame = oFrame
    With moFrame
        .caption = ""
        .SpecialEffect = fmSpecialEffectSunken
        .Backcolor = mDataBackColor
    End With
    
    Set mlbxData = moFrame.Controls.Add("Forms.Listbox.1", "DataListbox")
    With mlbxData
        .BorderStyle = fmBorderStyleSingle
        .SpecialEffect = fmSpecialEffectRaised
        .Backcolor = vbWhite
        .TextAlign = fmTextAlignRight
        .IntegralHeight = False
    End With
    
    Set mSizeLabel = moFrame.Controls.Add("forms.label.1", "SizeLabel")
    mSizeLabel.Visible = False
    
    ' Create and connect the events handler
    Set mLBEvents = New cls_ListBoxEvents
    Set mLBEvents.Listbox = mlbxData
    
    
    Set dctFH = New Dictionary
    
End Sub

Public Property Let HeaderBackColor(sColor As Single)
    mHeaderBackColor = sColor
    Dim X
    For Each X In dctFH.Keys
        dctFH(X).Backcolor = mHeaderBackColor
    Next
End Property
Public Property Let headerHeight(sHeight As Single)
    Dim skey
    For Each skey In dctFH.Keys
        dctFH(skey).height = sHeight
    Next
        
    If dctFH.Count > 0 Then
        mlbxData.top = dctFH(1).headerHeight
        mlbxData.height = moFrame.height - mlbxData.top
    End If
End Property
Public Property Let DataBackColor(sColor As Single)
    mDataBackColor = sColor
    moFrame.Backcolor = mDataBackColor
    mlbxData.Backcolor = mDataBackColor
End Property
Public Function Listbox() As MSForms.Listbox
  Set Listbox = mlbxData
End Function
Public Property Get ListCount()
    ListCount = mlbxData.ListCount
End Property
Public Property Get TableData() As Variant
    TableData = mDataArray
End Property
Public Property Let TableData(InputArray As Variant)
'InputArray must be a 2D array (rows,columns) with the first row being column header names
Dim FH As clsVBoxHeader
Dim FA As cls_FilterArray
Dim lbl As MSForms.Label
Dim lbox As MSForms.Listbox
Dim X As Integer

    
    Set dctColumnWidths = New Dictionary
    Set dctHeaderTextAlign = New Dictionary
    Set dctDataTextAlign = New Dictionary
      dctFH.RemoveAll
    
    mDataArray = InputArray
       
    
    Dim LCol As Integer
    Dim UCol As Integer
    
    Set moFilterArray = New cls_FilterArray
    moFilterArray.Initialize mDataArray, mbFilterOn
    Set FA = moFilterArray
    LCol = FA.ColumnLB
    UCol = FA.ColumnUB
    
    For X = LCol To UCol
        Set FH = New clsVBoxHeader
        
        Set lbl = moFrame.Controls.Add("Forms.Label.1", "Header" & X)
        Set lbox = moFrame.Controls.Add("Forms.Listbox.1", "DropDown" & X)
        FH.classInitialize Me, lbl, lbox, mlbxData, X, mbFilterOn
        Set lbl = Nothing
        Set lbox = Nothing
        
        FH.caption = FA.ArrayHeadings(X)
        FH.SpecialEffect = fmSpecialEffectRaised
        FH.Backcolor = mUserFormcolor
        FH.TextAlign = fmTextAlignRight
        FH.height = 12
    
        dctFH.Add X, FH
        Set FH = Nothing
    Next
    
    mlbxData.ColumnCount = dctFH.Count
    mlbxData.top = dctFH.items(0).height
    If mbFilterOn Then AutoWidths
    'AutoWidths
End Property

Public Function GetWidth(sngFontSize As Single, strFontName As String, str As String) As Single
'This function uses a hidden lable (mSizeLabel) to find the true width of a string given its font size and font type
'This was a trick i picked up from the JKP-ADS website
    mSizeLabel.AutoSize = False
    mSizeLabel.width = 200
    mSizeLabel.Font.Size = sngFontSize
    mSizeLabel.Font.name = strFontName
    mSizeLabel.caption = str
    mSizeLabel.AutoSize = True
    GetWidth = mSizeLabel.width
End Function
Public Function GetHeight(sngFontSize As Single, strFontName As String) As Single
    mSizeLabel.Font.Size = sngFontSize
    mSizeLabel.Font.name = strFontName
    mSizeLabel.caption = "M"
    GetHeight = mSizeLabel.height
End Function

Public Property Let ColumnWidths(strWidths As String)
'strWidths must be a ";" delimited string
Dim ary
Dim Index As Integer
    
    ary = Split(strWidths, ";")
    Index = LBound(ary)
    For Each skey In dctColumnWidths.Keys
        If Index > UBound(ary) Then Exit For
        dctColumnWidths(skey) = ary(Index)
        Index = Index + 1
    Next
    
    SetWidths dctColumnWidths

End Property
Public Function SumOfColumnWidths() As Double
Dim subtotal As Double
Dim item
For Each item In dctColumnWidths.items
    subtotal = subtotal + item
Next
SumOfColumnWidths = subtotal
End Function
Public Property Get ColumnWidths() As String
    ColumnWidths = Join(dctColumnWidths.items, ";")
End Property
Public Property Let ColumnWidth(ColumnIndex As Integer, sWidth As Single)
'Allows the user to specify the width of any column.
    
    dctColumnWidths(ColumnIndex) = sWidth
    'Update the headers and listbox widths, heights and Left positions
    SetWidths dctColumnWidths
End Property
Public Property Get ColumnWidth(ColumnIndex As Integer) As Single
    ColumnWidth = dctColumnWidths(ColumnIndex)
End Property
Private Function ListBoxDataHeight(dataArray As Variant)
    Dim ItemCount As Long
    ItemCount = (UBound(dataArray, 1) - LBound(dataArray) + 1) 'Header row is not counted
    ListBoxDataHeight = (GetHeight(mlbxData.Font.Size, mlbxData.Font.name)) * (ItemCount + 1) + 4
End Function
Private Sub SetWidths(dctWidths As Dictionary)
Dim sLeft As Single
    
    For Each skey In dctWidths.Keys
        dctFH(skey).left = sLeft
        sLeft = sLeft + dctWidths(skey)
        
        'If this is the last Field, add LISTBOXMARGIN in order to have that last header go all the way to the end of mlbxData
        If CInt(skey) = moFilterArray.ColumnUB Then
            dctFH(skey).width = dctWidths(skey) + LISTBOXMARGIN
        Else
            dctFH(skey).width = dctWidths(skey)
        End If
    Next
    
    lbxColumnWidths = Join(dctWidths.items, ";")
    
    mlbxData.ColumnWidths = lbxColumnWidths
    
    mlbxData.width = SumOfColumnWidths + LISTBOXMARGIN
  
    PopulateDataListBox moFilterArray.FilteredArray, mlbxData
    
End Sub

Public Sub AutoWidths()
Dim CharWidth As Single
Dim MaxChar As Integer
Dim skey
Dim i As Integer

    For Each skey In dctFH.Keys
            
            MaxChar = moFilterArray.MaxChar(CInt(skey))
            CharWidth = Int(GetWidth(mlbxData.Font.Size, mlbxData.Font.name, String(MaxChar, "M")))
            CharWidth = CharWidth + TEXT_MARGIN_IN_LISTBOX
            dctColumnWidths(CInt(skey)) = CharWidth
    Next
    
    SetWidths dctColumnWidths

End Sub
Public Property Let HeaderTextAlign(intColIndex As Integer, Alignment As fmTextAlign)
    dctHeaderTextAlign(intColIndex) = Alignment
End Property
Public Property Let DataTextAlign(intColIndex As Integer, Alignment As fmTextAlign)
    dctDataTextAlign(intColIndex) = Alignment
End Property

Private Sub PopulateDataListBox(ByVal dataArray As Variant, lb As MSForms.Listbox)
'Populates the Listbox with data in DataArray and makes adjustments for scroll bars

    
    lb.height = moFrame.InsideHeight - lb.top
        
    'Check if vertical scrollbar is needed and make adjustments
    If ListBoxDataHeight(dataArray) > lb.height Then
        Dim ColumnLock, xRow
        ColumnLock = UBound(dataArray, 2)
        For xRow = LBound(dataArray, 1) To UBound(dataArray, 1)
            dataArray(xRow, ColumnLock) = dataArray(xRow, ColumnLock) & String(6, " ")
        Next
        
        'Increase width of mlbxData to account for scrollbar
        lb.width = SumOfColumnWidths + LISTBOXMARGIN + SCROLLBARWIDTH
    Else
        lb.width = SumOfColumnWidths + LISTBOXMARGIN
    End If
    
    'Convert all data to a string before displaying in list box.  Listbox does not appear to display numeric data types
    Dim strDataArray() As String
    
    If 1 = 1 Then
        ReDim strDataArray(LBound(dataArray, 1) To UBound(dataArray, 1), LBound(dataArray, 2) To UBound(dataArray, 2))
        Dim X, Y
        For X = LBound(dataArray, 1) To UBound(dataArray, 1)
            For Y = LBound(dataArray, 2) To UBound(dataArray, 2)
                If IsNull(dataArray(X, Y)) Then
                    strDataArray(X, Y) = "null"
                Else
                    strDataArray(X, Y) = CStr(dataArray(X, Y))
                End If
            Next
        Next
        lb.List = strDataArray
        
        Else
        lb.List = dataArray
    End If
    
    'Add array data to listbox
    lb.AddItem " "
    
    
    'Add a Horizontal scrollbar to the Frame if needed
    Dim blnHScrol As Boolean
    blnHScrol = (lb.width > moFrame.InsideWidth)
    
    If blnHScrol Then
        moFrame.ScrollBars = fmScrollBarsHorizontal
        moFrame.ScrollWidth = lb.width
    Else
        moFrame.ScrollBars = fmScrollBarsNone
    End If
     
End Sub





'=================================================================================================================================================
'Filter Button Controls
'=================================================================================================================================================

Public Property Let FilterOn(blnFilterOn As Boolean)
    mbFilterOn = blnFilterOn
    For Each skey In dctFH.Keys
        dctFH(skey).FilterOn = mbFilterOn
    Next
End Property

Public Sub UpdateFilterDropDowns(LabelDropDown As MSForms.Listbox, ColumnNumber As Integer)
  FilterControl LabelDropDown, ColumnNumber
End Sub
Public Sub ButtonUpdate(objButton As MSForms.Label, objListBox As MSForms.Listbox, ColumnIndex As Integer)
'This procedure determines if a button click should show the dropdown listbox or hide the dropdown list box (objListBox)
'If it is to show the dropdown, then the dropdown list box is populated
    
With objListBox
    If Not .Visible Then
        .Visible = True
        PopulateFilterListBox objListBox, moFilterArray.UniqueValues(ColumnIndex).Keys
    Else
        .Visible = False
    End If
End With

End Sub
Private Sub PopulateFilterListBox(objListBox As MSForms.Listbox, ByVal ItemArray As Variant)
'objListbox is the dropdown listbox that will display all the unique items in a column.
'This procedure popultes objListBox with the values in ItemArray and adds "[CLOSE]" and  "[CLEAR]"

   With objListBox
     
     'ItemArray is an array with unique entries for the requested column index
     'Sort array then add the [CLEAR] option to the end
     Call QSortInPlace(ItemArray)
     InsertElementIntoArray ItemArray, 0, "[CLOSE]"
     InsertElementIntoArray ItemArray, 0, "[CLEAR]"
     InsertElementIntoArray ItemArray, 0, "[CLR*]"
     .Clear
     
     'Add items to the list box one at a time. I tried using .List = tempArray
     'but had problems getting it to work when this code was run after clicking "[CLEAR]".
     Dim X As Long
     Dim MaxChar As Integer
     
     For X = 0 To UBound(ItemArray)
       .AddItem ItemArray(X)
       MaxChar = fmax(MaxChar, Len(ItemArray(X)))
     Next
     
     'Resize list box
     Dim intFontsize As Integer
     intFontsize = .Font.Size
     intFontsize = Application.WorksheetFunction.Min(240, (UBound(ItemArray) + 1) * (intFontsize + 2)) + 4
     .height = intFontsize
     .width = fmin(150, .Font.Size / 1.5 * MaxChar + 15)
  End With
End Sub
Private Sub FilterControl(DropDownListBox As Object, ColumnIndex As Integer)
With DropDownListBox
'If APPLY is selected then create filters and set listbox to filtered array
'populate listbox after filters are applied to display the new unique valuess of the filtered array

If .ListIndex < 0 Then Exit Sub

Select Case .Column(0, .ListIndex)
  Case "[CLOSE]": DropDownListBox.Visible = False: NeedDeSelect = True


  Case "[CLEAR]":
                  'If CLEAR is selected then remove filters for column and populate the list box again
                  If .Column(0, .ListIndex) = "[CLEAR]" Then
                    moFilterArray.ClearFilter ColumnIndex
                    PopulateFilterListBox DropDownListBox, moFilterArray.UniqueValues(ColumnIndex).Keys
                  End If
  
  Case "[CLR*]":
                  'If CLR* = Clear all filters
                  If .Column(0, .ListIndex) = "[CLR*]" Then ClearFitlers
  
  Case Else:
                 'Add or clear filter
                 If .Selected(.ListIndex) Then moFilterArray.AddFilterCriteria ColumnIndex, .Column(0, .ListIndex)
                 If Not .Selected(.ListIndex) Then moFilterArray.ClearFilter ColumnIndex, .Column(0, .ListIndex)
End Select
If IsEmpty(moFilterArray.FilteredArray) Then
    mlbxData.List = ""
Else
    PopulateDataListBox moFilterArray.FilteredArray, mlbxData
End If
End With
End Sub
Public Property Get NeedDeSelect() As Boolean
    NeedDeSelect = mDeSelect
End Property
Public Property Let NeedDeSelect(bln As Boolean)
    mDeSelect = bln
End Property

Private Sub ClearFitlers()
    moFilterArray.ClearFilter
    PopulateDataListBox moFilterArray.FilteredArray, mlbxData
End Sub
Private Sub mlbxData_MouseUp(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
 If NeedDeSelect Then
    Dim xcount As Integer
    For xcount = 0 To fmin(2, mlbxData.ListCount)
        mlbxData.Selected(xcount) = False
    Next
    NeedDeSelect = False
 End If
End Sub

Private Sub mlbxData_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    RaiseEvent ListBoxDoubleClick(mlbxData)
End Sub
