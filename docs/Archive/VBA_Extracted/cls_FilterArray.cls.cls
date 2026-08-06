' Module: cls_FilterArray.cls
' Type: Class Module
' Stream Path: VBA/cls_FilterArray
' =========================================================

Attribute VB_Name = "cls_FilterArray"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False

Dim mArrayData() As Variant
Dim mArrayHeadings() As Variant
Dim mFilteredArray() As Variant
Dim dctMaxChar As Dictionary
Dim dctFilters As Dictionary
Dim dctUniqueValues As Dictionary
Dim mColumnUpperBound As Long
Dim mColumnLowerBound As Long
Dim mRowUpperBound As Long
Dim mRowLowerBound As Long
Dim blnFiltersModified As Boolean
Dim mblnFilterOn As Boolean

'Code for Array Filter
'==============================================================================================================================

Public Sub Initialize(vntSourceArray As Variant, Optional FilterOn As Boolean = False)
'First row of vntSourceArray must contains headers
  Set dctFilters = New Dictionary
  Set dctUniqueValues = New Dictionary
  Set dctMaxChar = New Dictionary
  mblnFilterOn = FilterOn
  SourceArray vntSourceArray
End Sub
Public Property Get UniqueValues(xColumnIndex As Integer) As Dictionary
 If Not dctUniqueValues.exists(xColumnIndex) Then Exit Property
 Set UniqueValues = dctUniqueValues(xColumnIndex)
End Property
Private Sub SourceArray(vntSourceArray As Variant)
'This procedure assumes that the first row of vntSourceArray contains headers
'vntSourceArray is then split into a header array and data array
 
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
   
    If mblnFilterOn Then FindUniqueValues mArrayData, True
    
   'mFilteredArray is always the array thats displayed.  Set this array to the new data array
    mFilteredArray = mArrayData
  
End Sub
Public Property Get ColumnUB()
    ColumnUB = mColumnUpperBound
End Property
Public Property Get ColumnLB()
    ColumnLB = mColumnLowerBound
End Property
Public Property Get RowUB()
    RowUB = mRowUpperBound
End Property
Public Property Get RowLB()
    RowLB = mRowLowerBound
End Property
Public Function ArrayHeadings()
    ArrayHeadings = mArrayHeadings
End Function
Public Function MaxChar(ColumnIndex As Integer, Optional blnIncludeHeader = True)
    
    If blnIncludeHeader Then
        MaxChar = fmax(Len(mArrayHeadings(ColumnIndex)) + IIf(mblnFilterOn, 5, 0), dctMaxChar(ColumnIndex))
    Else
        MaxChar = dctMaxChar(ColumnIndex)
    End If
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
                blnFieldMatch = blnFieldMatch Or CStr(mArrayData(xRow, skey)) = CStr(dctFilters(skey)(valueKey))
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
        FindUniqueValues mFilteredArray
    End If
    
    'Update dictionary with unique values of the new filtered array
    
    blnFiltersModified = False
End Sub

Private Sub FindUniqueValues(dataArray As Variant, Optional blnFindMaxChar As Boolean = False)
'This procedure creates a dictionary for each column that will be
'displayed in the selection drop down from the header labels.
'The keys to this dictionary are all the unique values in that column

    dctUniqueValues.RemoveAll
    
    Dim xMaxChar As Integer
    Dim xRow As Long
    Dim xColumn As Integer
    
    For xColumn = mColumnLowerBound To mColumnUpperBound
        'Create a dictionary for each column
        Set dctUniqueValues(xColumn) = New Dictionary
    Next
    
    Dim TestValue As Variant
    
    For xColumn = mColumnLowerBound To mColumnUpperBound
        xMaxChar = 0
        For xRow = LBound(dataArray) To UBound(dataArray)
            'Add value to dictionary key.  Only the unique values will remain in the key
            dctUniqueValues(xColumn)(dataArray(xRow, xColumn)) = dataArray(xRow, xColumn)
            If blnFindMaxChar Then xMaxChar = fmax(xMaxChar, Len(dataArray(xRow, xColumn)))
        Next
        If blnFindMaxChar Then dctMaxChar(xColumn) = xMaxChar
    Next
End Sub

