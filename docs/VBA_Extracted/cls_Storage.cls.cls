' Module: cls_Storage.cls
' Type: Class Module
' Stream Path: VBA/cls_Storage
' =========================================================

Attribute VB_Name = "cls_Storage"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False



'The Value property has been made the default property of this class
Private aryMain()               'nested 2D array
Private dctIndex As Dictionary  'Maps column names to column index in aryMain
Private mPointer As Long
Private mRowCount As Long
Private IndexDictionary As Dictionary


Public Enum eSumType
    Inclusive_Inclusive
    Inclusive_Exclusive
    Exclusive_Inclusive
    Exclusive_Exclusive
End Enum
Public Enum eInsertLocation
    InsertBefore
    InsertAfter
End Enum

'For Filtering
Private dctFilters As Dictionary
Private mFilteredArray()
Private blnFiltersModified As Boolean


Private Sub Class_Initialize()
    Set dctIndex = New Dictionary
    Set dctKeys = New Dictionary
    mRowCount = 0
    
End Sub


Public Sub AddColumn(ColumnKey As String, Optional NextToKey As String = "", Optional InsertLocation As eInsertLocation = InsertAfter)

If DuplicateKey(ColumnKey) Then Exit Sub

If NextToKey <> "" Then
    If Not KeyExists(NextToKey) Then Exit Sub
End If


ReDim Preserve aryMain(dctIndex.Count)
Dim X As Long
Dim Location As Long
Dim tempary
Dim ary()
ReDim ary(mRowCount)

If Not NextToKey = "" Then
    If InsertLocation = InsertAfter Then
        Location = dctIndex(NextToKey) + 1
    Else
        Location = dctIndex(NextToKey)
    End If
    For X = dctIndex.Count - 1 To Location Step -1
        aryMain(X + 1) = aryMain(X)
        dctIndex(aryMain(X)(0)) = X + 1
    Next
Else
    Location = dctIndex.Count
End If

dctIndex.Add ColumnKey, Location
ReDim ary(mRowCount)
ary(0) = ColumnKey
aryMain(Location) = ary


End Sub

Public Property Get ColumnDictionary() As Dictionary
Dim dctCopy As Dictionary
Dim skey

For Each skey In dctIndex.Keys
    dctCopy.Add skey, dctIndex(skey)
Next
Set FullIndex = dctCopy
Set dctCopy = Nothing
End Property
Public Property Get rowCount()
    rowCount = mRowCount
End Property

Public Property Let value(ColumnKey As Variant, vntValue As Variant)
Attribute value.VB_UserMemId = 0
If TypeName(ColumnKey) = "String" Then
    If Not (dctIndex.exists(ColumnKey)) Then
        MsgBox "Cannot write to key '" & ColumnKey & "'. Key does not exist."
        Stop
    End If
    aryMain(dctIndex(ColumnKey))(mPointer) = vntValue
Else
    If ColumnKey > UBound(aryMain) Then
        MsgBox "Request out of range."
        Stop
    End If
    aryMain(ColumnKey)(mPointer) = vntValue
End If
End Property

Public Property Get value(ColumnKey As Variant) As Variant
Attribute value.VB_UserMemId = 0
If TypeName(ColumnKey) = "String" Then
    If Not (dctIndex.exists(ColumnKey)) Then
        MsgBox "Cannot read from key '" & ColumnKey & "'. Key does not exist."
        Stop
     End If
     value = aryMain(dctIndex(ColumnKey))(mPointer)
Else
     If ColumnKey > UBound(aryMain) Then
        MsgBox "Request out of range."
        Stop
     End If
     value = aryMain(ColumnKey)(mPointer)
End If
End Property

Public Property Get ValueOffset(ColumnKey As String, RowOffset As Long) As Variant
 If Not (dctIndex.exists(ColumnKey)) Then
    MsgBox "Cannot read from key '" & ColumnKey & "'. Key does not exist."
    Stop
 End If
 ValueOffset = aryMain(dctIndex(ColumnKey))(mPointer + RowOffset)
End Property

Public Sub DumpValuesInExcel()
  DumpArrayValuesIntoExcel WriteTo2DArray
End Sub

Public Function GetArrayOfValues() As Variant
 GetArrayOfValues = WriteTo2DArray
End Function

Public Function GetNestedArray(Optional blnIncludeHeaders As Boolean = True) As Variant
        TrimArray
        GetNestedArray = aryMain
End Function

Public Function MoveNext()
If mPointer + 1 > mRowCount Then
    MsgBox "Requesting row past end of storage."
    Exit Function
End If
mPointer = mPointer + 1
End Function
Public Property Let CurrentRow(row As Long)
If row > mRowCount Or row < 0 Then
    MsgBox "Requestecd row '" & row & "' not in storage."
    Exit Property
End If
mPointer = row
End Property
Public Property Get CurrentRow() As Long
    CurrentRow = mPointer
End Property
Public Function MoveLast()
    mPointer = mRowCount
End Function
Public Function MoveFirst()
    mPointer = 1
End Function
Public Function ValueOnDate(strKey As String, dt As Date)
Dim CurrentPosistion
Dim MatchFound
    CurrentPosistion = mPointer
    MatchFound = MoveToDate(dt)
    If MatchFound Then
        ValueOnDate = value(strKey)
    End If
    mPointer = CurrentPosistion
End Function

Public Function MoveToDate(dt As Date) As Boolean
Dim FoundDate As Boolean
FoundDate = False
 startPosition = LBound(aryStorage, 2) + 1
 For X = UBound(aryStorage, 2) To startPosition Step -1
  If aryMain(dctIndex("Date"))(X) = dt Then
     mPointer = X
     FoundDate = True
     Exit For
  End If
 Next
MoveToDate = FoundDate
End Function

Public Function SumValues(strKey As String, FirstDate, LastDate, SumType As eSumType)
 startPosition = 1         'The first row (index=0) of aryStorage contains the headers.  So when comparing values, start with second row (index=1)
 Select Case SumType
    Case eSumType.Exclusive_Exclusive:
    For X = startPosition To mRowCount
        If aryMain(dctIndex("Date"))(X) > FirstDate And aryMain(dctIndex("Date"))(X) < LastDate Then
            subtotal = subtotal + aryMain(dctIndex(strKey))(X)
        End If
    Next
    
    Case eSumType.Exclusive_Inclusive:
    For X = startPosition To mRowCount
        If aryMain(X, dctIndex("Date")) > FirstDate And aryMain(X, dctIndex("Date")) <= LastDate Then
            subtotal = subtotal + aryMain(X, dctIndex(strKey))(X)
        End If
     Next
    
    Case eSumType.Inclusive_Exclusive:
    For X = startPosition To mRowCount
        If aryMain(dctIndex("Date")) >= FirstDate And aryMain(dctIndex("Date")) < LastDate Then
            subtotal = subtotal + aryMain(X, dctIndex(strKey))(X)
        End If
    Next
    
    Case eSumType.Inclusive_Inclusive:
    For X = startPosition To mRowCount
        If aryMain(dctIndex("Date"))(X) >= FirstDate And aryMain(dctIndex("Date"))(X) <= LastDate Then
            subtotal = subtotal + aryMain(dctIndex(strKey))(X)
        End If
    Next
End Select
SumValues = subtotal
End Function

Public Property Get EOF()
    EOF = (mPointer = mRowCount)
End Property
Public Property Get BOF()
    BOF = (mPointer = 1)
End Property


Public Sub AddRow()
   
'Rows are added in chunks of 100 so that ReDim is used less
If mRowCount + 1 > UBound(aryMain(1)) Then
    Dim item As Variant, temparray As Variant
    For Each item In dctIndex.items
        temparray = aryMain(item)
        ReDim Preserve temparray(mRowCount + 100)
        aryMain(item) = temparray
    Next
End If

mRowCount = mRowCount + 1
mPointer = rowCount

End Sub

Private Sub TrimArray()
'Since the Nested array is increased in chucks of 100, there are usually lots of empty rows in the array at any time
'This function gets rid of the empty rows

Dim aryNewMain()
Dim ary

ReDim aryNewMain(0 To UBound(aryMain))
Dim xRow As Long, xColumn As Long
For xColumn = 0 To UBound(aryMain)
    ReDim ary(0 To mRowCount)
    For xRow = 0 To mRowCount
        ary(xRow) = aryMain(xColumn)(xRow)
    Next
    aryNewMain(xColumn) = ary
Next
aryMain = aryNewMain
End Sub

Private Function WriteTo2DArray() As Variant
'This function takes the nested array (aryMain) and puts it into a 2 dimensional array.  This makes it easier to use in some applications such as Excel.

Dim temparray, row As Long, Column As Long, skey As Variant

ReDim temparray(mRowCount, dctIndex.Count - 1)

'Write headers
For Each skey In dctIndex.Keys
    temparray(0, dctIndex(skey)) = CStr(skey)
Next

For row = 0 To mRowCount
    For Each skey In dctIndex.Keys
        temparray(row, dctIndex(skey)) = aryMain(dctIndex(skey))(row)
    Next
Next
WriteTo2DArray = temparray
End Function


Private Function DuplicateKey(ColumnKey As Variant)
    If dctIndex.exists(ColumnKey) Then
        MsgBox "Key '" & ColumnKey & "' already exist."
        Stop
    End If
    DuplicateKey = False
End Function
Private Function KeyExists(ColumnKey As Variant)
    If Not dctIndex.exists(ColumnKey) Then
        MsgBox "Key '" & ColumnKey & "' does not exist."
        Stop
    End If
    KeyExists = False
End Function
Private Function ColumnIndex(ColumnKey As Variant) As Integer
If IsNumeric(ColumnKey) Then
     If ColumnKey > UBound(aryMain) Or ColumnKey < 1 Then
        MsgBox "Request out of range."
        Stop
     Else
        ColumnIndex = ColumnKey
     End If
Else
    If Not (dctIndex.exists(ColumnKey)) Then
        MsgBox "Key '" & ColumnKey & "' does not exist."
        Stop
     End If
     ColumnIndex = dctIndex(ColumnKey)
End If
End Function

