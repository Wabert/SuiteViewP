' Module: cls_FilterBox.cls
' Type: Class Module
' Stream Path: VBA/cls_FilterBox
' =========================================================

Attribute VB_Name = "cls_FilterBox"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Option Explicit
'RJH - 1/14/2025
'Added event handling with clsListBoxEvents
'This allows events on the listbox to be handled outside this class

Private WithEvents mParent As MSForms.frame
Attribute mParent.VB_VarHelpID = -1
Private WithEvents mLB As MSForms.Listbox
Attribute mLB.VB_VarHelpID = -1
Private dctHeaders As Dictionary        'key starts at 1
Private dctColumnWidths As Dictionary   'key starts at 1
Private mColumnWidth As String
Private mInternalWidth As Single
Private mInternalHeight As Single

Private HEADERGAP As Single
Private SIDEMARGINS As Single
Private TOP_MARGIN As Single
Private BOTTOM_MARGIN As Single
Private HEADER_OFFSET As Single
Private SCROLLBAR_WIDTH As Single


'6/14/2016 - RJH
'Variables below are used for the Array Filter. Applies filters to a 2D array
Private mArrayData() As Variant
Private mArrayHeadings() As Variant
Private mColumnUpperBound As Integer
Private mColumnLowerBound As Integer
Private mRowUpperBound As Long
Private mRowLowerBound As Long
Private mFilteredArray() As Variant
Private dctFilters As Dictionary
Private dctUniqueValues As Dictionary
Private blnFiltersModified As Boolean
Private mDeSelect As Boolean


Public Sub classInitialize(UserFormFrame As MSForms.frame, vntSourceArray As Variant)
    HEADERGAP = 1
    SIDEMARGINS = 10
    TOP_MARGIN = 0
    BOTTOM_MARGIN = 8
    HEADER_OFFSET = 1
    SCROLLBAR_WIDTH = 15
    
    FilterArrayInitialize vntSourceArray
  
    Set mParent = UserFormFrame
    Set mLB = mParent.Controls.Add("Forms.Listbox.1", "DataLB")
    
   
    CreateControls
    EvalulateWidths
    EvalulateHeights
    mLB.List = mFilteredArray
    mLB.MultiSelect = fmMultiSelectMulti
End Sub
Private Sub CreateControls()
    Dim aryIndex As Integer, xcount As Integer, xLeft As Double
    Dim Heading As cls_FilterHeading
    xLeft = 0
    Set dctHeaders = New Dictionary
    Set dctColumnWidths = New Dictionary
    xcount = 0
    For aryIndex = LBound(mArrayHeadings) To UBound(mArrayHeadings)
         xcount = xcount + 1
        Set Heading = New cls_FilterHeading
        Heading.classInitialize Me, mParent.Controls.Add("Forms.Label.1", "HeadingButton" & xcount), mParent.Controls.Add("Forms.Listbox.1", "HeadingDropdown" & xcount), xcount
        With Heading
            .caption = mArrayHeadings(aryIndex)
            .SpecialEffect = fmSpecialEffectEtched
            .TextAlign = fmTextAlignCenter
            
            'Dont add the HEADERGAP to the last label.  The GAP is only for in between labels
            If aryIndex < UBound(mArrayHeadings) Then
                dctColumnWidths(xcount) = .width + HEADERGAP
            Else
                dctColumnWidths(xcount) = .width
            End If
        End With
        xLeft = xLeft + dctColumnWidths(xcount)
        dctHeaders.Add xcount, Heading
    Next

    
    'You must set the IntegralHeight to False to avoid bugs at runtime (the Height.Width resets upon every appearance change).
    'I found this article with the solution: https://support.microsoft.com/en-us/kb/191858
    mLB.IntegralHeight = False
    
    mLB.ColumnCount = dctHeaders.Count
End Sub
Private Sub EvalulateWidths()
'Ajust the Width and Left property of controls within the Parent frame and the parent frame itself

    Dim X As Integer, CummulativeWidth As Double
    CummulativeWidth = 0
    For X = 1 To dctColumnWidths.Count
        With dctHeaders(X)
            
            .left = SIDEMARGINS + CummulativeWidth
            .width = dctColumnWidths(X)
            CummulativeWidth = CummulativeWidth + dctColumnWidths(X)
        End With
    Next
    mLB.left = SIDEMARGINS
    mLB.width = CummulativeWidth + SCROLLBAR_WIDTH
    mLB.ColumnWidths = ColumnWidths
    mInternalWidth = mLB.width + SIDEMARGINS * 2
    'mParent.Width = CummulativeWidth + SIDEMARGINS * 2 + SCROLLBAR_WIDTH
End Sub
Private Sub EvalulateHeights()
'Ajust the Top and Height of controls within the Parent frame and the parent frame itself

    Dim item
    For Each item In dctHeaders.items
        item.top = TOP_MARGIN
    Next
    mLB.top = TOP_MARGIN + dctHeaders(1).height + HEADER_OFFSET
    mLB.height = mParent.height - mLB.TopIndex - BOTTOM_MARGIN
End Sub
Public Property Let ColumnWidths(strWidths As String)
    Dim WidthsArray, X As Integer
    strWidths = Replace(strWidths, "pt", "")
    WidthsArray = Split(strWidths, ";")
    For X = 0 To UBound(WidthsArray)
      If X + 1 <= dctColumnWidths.Count Then dctColumnWidths(X + 1) = CDbl(WidthsArray(X))
    Next
    EvalulateWidths
End Property
Public Property Get ColumnWidths() As String
    Dim strWidths As String
    Dim item
    For Each item In dctColumnWidths.items
        If strWidths = "" Then
            strWidths = item & " pt;"
        Else
            strWidths = strWidths & item & " pt;"
        End If
    Next
    ColumnWidths = strWidths
End Property
Property Get InternalWidth() As Double
    InternalWidth = mInternalWidth
End Property
Property Let topMargin(sngTopMargin As Single)
    TOP_MARGIN = sngTopMargin
    EvalulateHeights
End Property
Property Let BottonMargin(sngBottomMargin As Single)
    BOTTOM_MARGIN = sngBottomMargin
    EvalulateHeights
End Property
Public Function Listbox() As MSForms.Listbox
    Set Listbox = mLB
End Function











'Code for Array Filter
'==============================================================================================================================

Private Sub FilterArrayInitialize(vntSourceArray As Variant)
  Set dctFilters = New Dictionary
  Set dctUniqueValues = New Dictionary
  SourceArray vntSourceArray
End Sub
Public Property Get UniqueValues(xColumnIndex As Integer) As Dictionary
 If Not dctUniqueValues.exists(xColumnIndex) Then Exit Property
 Set UniqueValues = dctUniqueValues(xColumnIndex)
End Property
Private Sub SourceArray(vntSourceArray As Variant)
'This procedure assumes that the first row of vntSourceArray contains headers
'vntSourceArray is split into a header array and data array
 
    'Get Header array
    If Not GetRow(vntSourceArray, mArrayHeadings, LBound(vntSourceArray)) Then
        MsgBox "Problem loading Headings for arrayfilter"
        Exit Sub
    End If
    
    'Remove first row to get data array
    mArrayData = vntSourceArray
    Call DeleteRowFromArray(mArrayData, LBound(vntSourceArray))
    
    'Identify the bounds of the data array
    mColumnUpperBound = UBound(mArrayData, 2)
    mColumnLowerBound = LBound(mArrayData, 2)
    mRowUpperBound = UBound(mArrayData, 1)
    mRowLowerBound = LBound(mArrayData, 1)
   
    FindUniqueValues mArrayData
    
   'mFilteredArray is always the array thats displayed.  Set this array to the new data array
    mFilteredArray = mArrayData
  
End Sub
Public Function ArrayHeadings()
    ArrayHeadings = mArrayHeadings
End Function
Public Sub AddFilterCriteria(ColumnIndex As Integer, strFilterCriteria As String)
    
    If ColumnIndex > mColumnUpperBound Or ColumnIndex < mColumnLowerBound Then
        Exit Sub
    End If

    'Create filter dictionary for array column if it doesnt already exist
    If Not dctFilters.exists(ColumnIndex) Then
        Dim dct As Dictionary
        Set dct = New Dictionary
        Set dctFilters(ColumnIndex) = dct
    End If
    
    'Add the filter criteria for this column to the dictionary
    dctFilters(ColumnIndex)(strFilterCriteria) = strFilterCriteria
    
    'Set the boolean to indicate that that filtered array will need to be updated again before its displayed
    blnFiltersModified = True
End Sub
Public Sub ClearFilter(Optional ColumnIndex As Variant, Optional strFilterCriteria As Variant)
'Depending on what arguments are passed this procedure will:
' remove all filter criteria for all columns (ie set mFilteredArray to original data array)
' or remove all filter critiera for one column
' or remove one filter criteria(strFilterCriteria) for one column
    
    'To use the IsMissing function ColumnIndex must be variant
    If IsMissing(ColumnIndex) Then
        mFilteredArray = mArrayData
        dctFilters.RemoveAll
    Else
        'If there are filters for ColumnIndex then remove each filter, otherwise do nothing
        If dctFilters.exists(ColumnIndex) Then
            If IsMissing(strFilterCriteria) Then   'strFilterCriteria is missing
                dctFilters.Remove ColumnIndex
            Else
                If dctFilters(ColumnIndex).exists(strFilterCriteria) Then
                    dctFilters(ColumnIndex).Remove strFilterCriteria
                    If dctFilters(ColumnIndex).Count = 0 Then dctFilters.Remove ColumnIndex
                End If
            End If
        End If
    End If
    ApplyFilter
    mLB.List = FilteredArray
End Sub
Public Property Get FilteredArray(Optional IncludeHeadings As Boolean = False) As Variant
'Reture the current Filtered Array

    'ApplyFilters only if needed
    If blnFiltersModified Then
        ApplyFilter
    End If
    
    'Include heading if requested
    If IncludeHeadings Then
      Dim temparray As Variant
      temparray = mFilteredArray
      Call InsertRowIntoArray(temparray, 0, mArrayHeadings)
      FilteredArray = temparray
    Else
      FilteredArray = mFilteredArray
    End If
End Property
Public Sub ApplyFilter()
'This function walks through each row of data array and checks all the filters for a match
'If the row matches the filter criteria, the row index is stored in dctIndex.  The row indices
'stored in the dictionary are then used to create the final FilteredArray

    If IsEmpty(mArrayData) Then Exit Sub
    
    Erase mFilteredArray
    
    'If there is no filter criteria then return the whole array
    If dctFilters.Count = 0 Then
      mFilteredArray = mArrayData
      FindUniqueValues mFilteredArray
      blnFiltersModified = False
      Exit Sub
    End If
      
    'Create dictionary to store the row index for data that passes the criteria
    Dim dctRowIndex As Dictionary
    Set dctRowIndex = New Dictionary
    
    Dim xRow As Long
    Dim xColumn As Long
    Dim blnRowMatch As Boolean
    Dim blnFieldMatch As Boolean
    
    'variants used in For Each loops
    Dim skey As Variant
    Dim valueKey As Variant
        
    'First row index of filtered array should be the first row index of data array
    For xRow = mRowLowerBound To mRowUpperBound
        blnRowMatch = True
      
        'Check criteria for field values in the row
        For Each skey In dctFilters
           
            'Check to see if field value hits any of the Filter Criteria values
            blnFieldMatch = False
            For Each valueKey In dctFilters(skey).items
                blnFieldMatch = blnFieldMatch Or (mArrayData(xRow, skey) = dctFilters(skey)(valueKey))
            Next
            blnRowMatch = blnRowMatch And blnFieldMatch
        Next
      
        'If all filters are a match, add row to Filtered Array and increase filter array row index
        If blnRowMatch Then
            dctRowIndex(xRow) = xRow
        End If
    Next
    
    xRow = mRowLowerBound
    If dctRowIndex.Count > 0 Then
        ReDim mFilteredArray(mRowLowerBound To dctRowIndex.Count, mColumnLowerBound To mColumnUpperBound)
        For Each skey In dctRowIndex
            For xColumn = mColumnLowerBound To mColumnUpperBound
                mFilteredArray(xRow, xColumn) = mArrayData(skey, xColumn)
            Next
            xRow = xRow + 1
        Next
    End If
    
    'Update dictionary with unique values of the new filtered array
    FindUniqueValues mFilteredArray
    blnFiltersModified = False
End Sub

Private Sub FindUniqueValues(dataArray As Variant)
'This procedure creates a dictionary for each column that will be
'displayed in the selection drop down from the header labels.
'The keys to this dictionary are all the unique values in that column

    dctUniqueValues.RemoveAll
    
    Dim xRow As Long
    Dim xColumn As Integer
    
    For xColumn = mColumnLowerBound To mColumnUpperBound
        'Create a dictionary for each column
        Set dctUniqueValues(xColumn) = New Dictionary
    Next
    
    Dim TestValue As Variant
    
    For xColumn = mColumnLowerBound To mColumnUpperBound
        For xRow = LBound(dataArray) To UBound(dataArray)
            'Add value to dictionary key.  Only the unique values will remain in the key
            dctUniqueValues(xColumn)(dataArray(xRow, xColumn)) = dataArray(xRow, xColumn)
        Next
    Next
End Sub





Public Sub UpdateFilterDropDowns(LabelDropDown As MSForms.Listbox, ColumnNumber As Integer)
  FilterControl LabelDropDown, ColumnNumber
End Sub
Public Sub ButtonUpdate(objButton As MSForms.Label, objListBox As MSForms.Listbox, ColumnIndex As Integer)
'This procedure determines if a button click should show the dropdown listbox or hide the dropdown list box (objListBox)
'If it is to show the dropdown, then the dropdown list box is populated
    
With objListBox
    If Not .Visible Then
        .Visible = True
        PopulateFilterListBox objListBox, Me.UniqueValues(ColumnIndex).Keys
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
     
     .Clear
     
     'Add items to the list box one at a time. I tried using .List = tempArray
     'but had problems getting it to work when this code was run after clicking "[CLEAR]".
     Dim X As Integer
     For X = 0 To UBound(ItemArray)
       .AddItem ItemArray(X)
     Next
     
     'Resize list box
     Dim intFontsize As Integer
     intFontsize = .Font.Size
     intFontsize = Application.WorksheetFunction.Min(240, (UBound(ItemArray) + 1) * (intFontsize + 2)) + 4
     .height = intFontsize
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
                    Me.ClearFilter ColumnIndex
                    mLB.List = Me.FilteredArray
                    PopulateFilterListBox DropDownListBox, Me.UniqueValues(ColumnIndex).Keys
                  End If
  Case Else:
                 'Add or clear filter
                 If .Selected(.ListIndex) Then Me.AddFilterCriteria ColumnIndex, .Column(0, .ListIndex)
                 If Not .Selected(.ListIndex) Then Me.ClearFilter ColumnIndex, .Column(0, .ListIndex)
End Select
mLB.List = IIf(IsEmpty(Me.FilteredArray), "", Me.FilteredArray)
End With
End Sub
Public Property Get NeedDeSelect() As Boolean
    NeedDeSelect = mDeSelect
End Property
Public Property Let NeedDeSelect(bln As Boolean)
    mDeSelect = bln
End Property
Private Sub ListBox_TypeFilterDropDown_Click()
'The Click event doesnt work for ListBoxes that are set to MultiSelect
End Sub


Private Sub mLB_MouseUp(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
 If NeedDeSelect Then
    For X = 0 To fmin(2, mLB.ListCount)
        mLB.Selected(X) = False
    Next
    NeedDeSelect = False
 End If
End Sub
