' Module: mdlUtilities.bas
' Type: Standard Module
' Stream Path: VBA/mdlUtilities
' =========================================================

Attribute VB_Name = "mdlUtilities"
'TypeName() returns string of data type
'VarType()  return vb constant with varaible type

Global Const ColorBlack = &H0
Global Const ColorWhite = &HFFFFFF
Global Const ColorNormalGrey = &H80000000
Global Const ColorFoamGreen = &HC0FFC0
Global Const ColorOffGrey = &HE0E0E0
Global Const DefaultCyberDocFolder = "\\sranico7\data\shared\+++PROCESS CONTROL+++\Implementation Library\Tools\PolicyInfo and Rates\Cyberlife Browser\CyberDoc\1101"

Public Enum eLinkClass
    lcFile = 1
    lcFolder = 2
    lcWeb = 3
End Enum



Public Function GetApproxListBoxHeight_InPoints(lb As MSForms.Listbox)

    'Height of one row (points) – Font.Size is points, add a bit for padding
    Dim rowHt As Single
    rowHt = lb.Font.Size + 3   '˜ 1 pt above + 3 pt below text
    GetApproxListBoxHeight_InPoints = lb.ListCount * rowHt

End Function



'============================================================
' Strip characters that confuse MSForms.Label
'============================================================
Public Function CleanCaption(ByVal s As String) As String
    'remove NULLs, CR, LF, TAB—anything < 32
    Dim i As Long, out As String
    For i = 1 To Len(s)
        Dim ch As Integer: ch = AscW(Mid$(s, i, 1))
        If ch >= 32 Then out = out & Mid$(s, i, 1)
    Next i
    CleanCaption = Trim$(out)
End Function
'====================================================================
'   helper – last path component  (C:\Foo\Bar.txt -> Bar.txt)
'====================================================================
Public Function LastComponent(ByVal fullPath As String) As String
    Dim p As Long: p = InStrRev(fullPath, "\")
    If p = 0 Then
        LastComponent = fullPath
    Else
        LastComponent = Mid$(fullPath, p + 1)
    End If
End Function

'Sort a 2-D Variant array in-place and return it.
'  arr        – the array to sort (any lower/upper bounds)
'  sortCol    – column index to sort on (same base as arr, e.g. 1, 2, …)
'  ascending  – True = A-Z / small-to-large; False = Z-A / large-to-small
Public Function Sort2D(ByVal arr As Variant, _
                ByVal sortCol As Long, _
                Optional ByVal ascending As Boolean = True) As Variant
    
    Dim rLo As Long, rHi As Long, cLo As Long, cHi As Long
    Dim i As Long, j As Long, c As Long
    Dim tmp As Variant
    
    rLo = LBound(arr, 1): rHi = UBound(arr, 1)
    cLo = LBound(arr, 2): cHi = UBound(arr, 2)
    
    For i = rLo To rHi - 1
        For j = i + 1 To rHi
            
            If (ascending And arr(i, sortCol) > arr(j, sortCol)) _
            Or (Not ascending And arr(i, sortCol) < arr(j, sortCol)) Then
                
                'swap whole rows
                For c = cLo To cHi
                    tmp = arr(i, c)
                    arr(i, c) = arr(j, c)
                    arr(j, c) = tmp
                Next c
            End If
        Next j
    Next i
    
    Sort2D = arr
End Function
Function Convert2DTo1D(arr As Variant) As Variant
    ' Takes a 2D array and converts it to 1D array
    ' Input: 2D array of any data type
    ' Output: 1D array with zero-based indexing containing all elements
    
    ' Declare counter variables and dimensions
    Dim i As Long, j As Long, k As Long
    Dim rows As Long, cols As Long
    Dim result() As Variant
    
    ' Get dimensions of input array
    rows = UBound(arr, 1)
    cols = UBound(arr, 2)
    ' Size result array to hold all elements (rows * cols)
    ReDim result(0 To (rows * cols) - 1)
    
    ' Loop through each element of 2D array and copy to 1D array
    k = 0
    For i = 1 To rows
        For j = 1 To cols
            result(k) = arr(i, j)
            k = k + 1
        Next j
    Next i
    
    Convert2DTo1D = result
End Function
Public Function QuickSearch(ary2D As Variant, dctCriteria As Dictionary, Optional StartingRow) As Long
'The function will return the first row index from ary2D that matches all the criteria found in dctCriteria
'ary2D is a 2 dimensional array (cannot be nested).
'dctFilters has column index as the key and the items are the values to match

Dim LCol, UCol, LRow, URow
Dim NumOfDim As Integer


QuickSearch = -1

If IsArrayEmpty(ary2D) Then
    Exit Function
End If

NumOfDim = NumberOfArrayDimensions(ary2D)
If NumOfDim <> 2 Then
    MsgBox "FindOccuranceInArray requires a 2D array", vbOKOnly
    Exit Function
End If


If NumOfDim = 2 Then
    Dim xRow As Long, xCol As Long, xtrigger
    Dim blnFound As Boolean
    Dim tempBln As Boolean
    Dim skey
    
    LRow = LBound(ary2D, 1): URow = UBound(ary2D, 1)
    LCol = LBound(ary2D, 2): UCol = UBound(ary2D, 2)

    If IsMissing(StartingRow) Then StartingRow = LRow
    
    For xRow = StartingRow To URow
        xtrigger = 0
        For Each skey In dctCriteria.Keys
            If CInt(skey) <= UCol And CInt(skey) >= LCol Then
                If xtrigger = 0 Then
                    tempBln = (dctCriteria(skey) = ary2D(xRow, CInt(skey)))
                    xtrigger = 1
                Else
                    tempBln = (tempBln And (dctCriteria(skey) = ary2D(xRow, CInt(skey))))
                End If
            End If
        Next
        If tempBln Then
            QuickSearch = xRow
            Exit Function
        End If
    Next
End If



End Function




Public Sub ModifyArrayBase(ByRef TargetArray As Variant, Optional intIndexBase = 1)
'This procedure adjusts the base of a single array to start at intIndexBase

Dim ary()
Dim lb As Integer, ub As Integer
Dim NewLB As Integer, NewUB As Integer
Dim ItemCount As Integer, X As Integer

lb = LBound(TargetArray)

'If base of array already equal to intIndexBase then no change needed
If lb = intIndexBase Then Exit Sub

ub = UBound(TargetArray)
ItemCount = ub - lb + 1

NewLB = intIndexBase
NewUB = intIndexBase + ItemCount - 1
ReDim ary(NewLB To NewUB)

For X = 0 To ItemCount - 1
    ary(NewLB + X) = TargetArray(lb + X)
Next

TargetArray = ary

End Sub

Public Function KeyExists(mCol As Collection, key As String) As Boolean
'6/10/2016 - RJH - there is not easy way to check if a key exists in collection.  This function comes from http://www.devx.com/tips/Tip/14490
    Dim V As Variant
    On Error Resume Next
    V = mCol(key)
    If Err.Number = 450 Or Err.Number = 0 Then
        KeyExists = True
    Else
        KeyExists = False
    End If
End Function
Public Function GetNextMonthliversaryDate(IssueDate As Date, dt As Date) As Date
'This function must account for a policy that is issued on the 29, 30 or 31st.
'In that case the next month might have less days and the monthliversay should be the end of the month
'For example if a policy was issued on the 1/31/2017, the monthliversary in in Febrary would be 2/28/2017 and the monthliversary in November would be the 11/30/2017
IssueDay = Day(IssueDate)

EndOfThisMonth = DateSerial(Year(dt), Month(dt) + 1, 0)
EndOfNextMonth = DateSerial(Year(dt), Month(dt) + 2, 0)

Monthliversary1 = DateSerial(Year(dt), Month(dt), fmin(IssueDay, Day(EndOfThisMonth)))
Monthliversary2 = DateSerial(Year(dt), Month(dt) + 1, fmin(IssueDay, Day(EndOfNextMonth)))

If dt < Monthliversary1 Then
 GetNextMonthliversaryDate = Monthliversary1
Else
  GetNextMonthliversaryDate = Monthliversary2
End If


End Function
Public Sub DisableControls(dct As Dictionary, Optional Backcolor As Variant)
'dct contains the control Textboxes form a single periodic transaction
Dim skey
For Each skey In dct.Keys
    DisableControl dct(skey), Backcolor
Next
End Sub
Public Sub EnableControls(dct As Dictionary, Optional Backcolor As Variant)
'dct contains the control Textboxes form a single periodic transaction
Dim skey
For Each skey In dct.Keys
    EnableControl dct(skey), Backcolor
Next
End Sub
Public Sub DisableControl(ctl As MSForms.Control, Optional Backcolor As Variant)
Dim vBackcolor
Dim vTextColor
Dim strType As String

If IsMissing(Backcolor) Then Backcolor = ctl.Parent.Backcolor

strType = TypeName(ctl)
Select Case strType
    Case "Frame": Exit Sub
    Case Else:
            vBackcolor = Backcolor
            vTextColor = vbGrayText
End Select

With ctl
  .Enabled = False
  .Backcolor = vBackcolor
  .ForeColor = vTextColor
End With
End Sub
Public Sub EnableControl(ctl As MSForms.Control, Optional Backcolor As Variant)
Dim vBackcolor
Dim vTextColor

If IsMissing(Backcolor) Then Backcolor = ctl.Parent.Backcolor

Select Case TypeName(ctl)
'    Case "TextBox", "ComboBox", "ComboBox": vBackcolor = vbHighlight: vTextColor = vbButtonText
    Case "Frame": Exit Sub
    Case "OptionButton", "Label": vBackcolor = Backcolor: vTextColor = vbButtonText
    Case Else: vBackcolor = &H80000005: vTextColor = vbButtonText
End Select


With ctl
  .Enabled = True
  .Backcolor = vBackcolor
  .ForeColor = vTextColor
End With
End Sub

Public Function StringFormat(StringLenth As Integer, vntValue, Optional Justification As Integer = 1) As String

vntValue = CStr(vntValue)
vntValue = left(vntValue, StringLenth)

If Justification = 0 Then
  'Left justified
  StringFormat = vntValue & String(StringLenth - Len(vntValue), " ")
Else
  'Right justified
  StringFormat = String(StringLenth - Len(vntValue), " ") & vntValue
End If


End Function

Public Function fmin(X As Variant, Y As Variant) As Variant
  fmin = Application.WorksheetFunction.Min(X, Y)
End Function
Public Function fmax(X As Variant, Y As Variant) As Variant
  fmax = Application.WorksheetFunction.Max(X, Y)
End Function
Public Function CDecimal(strValue As String) As Double
If Not IsNumeric(Replace(strValue, "%", "")) Then
    CDecimal = 0#
Else
   CDecimal = CDec(Replace(strValue, "%", ""))
End If

End Function


Public Function FieldsExistsInRS(rs As ADODB.Recordset, fldname As String) As Boolean
Dim fld As ADODB.Field
Dim blnExists As Boolean
blnExists = False
For Each fld In rs.Fields
    If fld.name = fldname Then
        blnExists = True
        Exit For
    End If
Next
FieldsExistsInRS = blnExists
End Function


Public Sub SpeakNow(TextToSay As String)
 Application.Speech.Speak TextToSay
End Sub

Public Function GetDataFromExcel(ByVal workbookPath As String, ByVal sheetName As String) As Variant
    Dim wb As Workbook
    Dim ws As Worksheet
    Dim dataRange As Range
    Dim lastRow As Long
    Dim lastCol As Long
    Dim dataArray As Variant
    
    On Error GoTo ErrorHandler
    
    ' Open workbook
    Set wb = Workbooks.Open(workbookPath, ReadOnly:=True)
    Set ws = wb.Worksheets(sheetName)
    
    ' Find last used row and column
    lastRow = ws.Cells(ws.rows.Count, "A").End(xlUp).row
    lastCol = ws.Cells(1, ws.Columns.Count).End(xlToLeft).Column
    
    ' Get the range containing data
    Set dataRange = ws.Range(ws.Cells(1, 1), ws.Cells(lastRow, lastCol))
    
    ' Read data into array
    dataArray = dataRange.value
    
    ' Close workbook
    wb.Close SaveChanges:=False
    
    ' Return the array
    GetDataFromExcel = dataArray
    
    Exit Function

ErrorHandler:
    ' Clean up on error
    If Not wb Is Nothing Then
        wb.Close SaveChanges:=False
    End If
    
    ' Return empty array on error
    GetDataFromExcel = Empty
    
    ' Display error message
    MsgBox "Error reading Excel file: " & Err.Description, vbExclamation
End Function

' Example usage:
Public Sub TestGetDataFromExcel()
    Dim dataArray As Variant
    Dim i As Long, j As Long
    
    ' Get data from Excel
    dataArray = GetDataFromExcel("C:\Path\To\Your\Workbook.xlsx", "Sheet1")
    
    ' Check if we got data
    If Not IsEmpty(dataArray) Then
        ' Print array dimensions to immediate window
        Debug.Print "Array Dimensions: " & LBound(dataArray, 1) & " to " & UBound(dataArray, 1) & _
                   ", " & LBound(dataArray, 2) & " to " & UBound(dataArray, 2)
        
        ' Print first row as example
        Dim firstRowContent As String
        firstRowContent = "First Row: "
        For j = LBound(dataArray, 2) To UBound(dataArray, 2)
            firstRowContent = firstRowContent & dataArray(1, j) & " | "
        Next j
        Debug.Print firstRowContent
    End If
End Sub

Public Sub DumpArrayValuesIntoExcel(ary2D As Variant, Optional FreezeRow, Optional FreezeColumn, Optional blnAllText As Boolean = False)
'ary2D must be a two dimensional array:  ary(x,y)

If IsEmpty(ary2D) Then
 MsgBox "No values to export"
 Exit Sub
End If

Dim xlApp As Excel.Application
Dim wb As Workbook
 Set xlApp = Excel.Application
 Set wb = xlApp.Workbooks.Add
 wb.Activate
 Dim NewRange As Range
 Set NewRange = wb.Sheets(1).Range("A1").Resize(UBound(ary2D, 1) - LBound(ary2D, 1) + 1, UBound(ary2D, 2) - LBound(ary2D, 2) + 1)
 NewRange.Select
 If blnAllText Then Selection.NumberFormat = "@"
 NewRange.value = ary2D
 NewRange.AutoFilter
 rows("1:1").Select
 With Selection
    .HorizontalAlignment = xlCenter
    .VerticalAlignment = xlBottom
    .WrapText = False
    .Orientation = 0
    .AddIndent = False
    .IndentLevel = 0
    .ShrinkToFit = False
    .ReadingOrder = xlContext
    .MergeCells = False
 End With
 Selection.Font.Bold = True
 
 If Not IsMissing(FreezeRow) And Not IsMissing(FreezeColumn) Then
  Cells(FreezeRow, FreezeColumn).Select
  ActiveWindow.FreezePanes = True
 End If
 

 Cells.EntireColumn.AutoFit
 xlApp.Visible = True
 Set wb = Nothing
 Set NewRange = Nothing
 Set xlApp = Nothing
End Sub
Public Function GetColorBasedOnFileType(filepath As String, filetype As String, lbl As Object)

    Dim ext As String
    Dim targetPath As String
    Dim fAttr As Long

    ' Check if it's a shortcut
    If LCase(Right(filepath, 4)) = ".lnk" Then
        On Error Resume Next
        Dim shell As Object
        Dim shortcut As Object
        Set shell = CreateObject("WScript.Shell")
        Set shortcut = shell.CreateShortcut(filepath)
        targetPath = shortcut.targetPath
        Set shortcut = Nothing
        Set shell = Nothing
        On Error GoTo 0

        If targetPath <> "" Then
            filepath = targetPath
        End If
    End If

    ' Extract extension
    If InStrRev(filepath, ".") > 0 Then
        ext = LCase(Mid(filepath, InStrRev(filepath, ".") + 1))
    Else
        ext = ""
    End If

'    On Error Resume Next
'    fAttr = GetAttr(filepath)
'    On Error GoTo 0
'
'    ' Determine filetype if not provided
'    If filetype = "" Then
'        If (fAttr And vbDirectory) = vbDirectory Then
'            filetype = "Folder"
'        Else
'            filetype = "File"
'        End If
'    End If

    With lbl
        Select Case filetype
            Case "Web"
                .Backcolor = RGB(0, 100, 255)
                .ForeColor = RGB(255, 255, 255)
            Case "Folder"
                .Backcolor = RGB(230, 230, 0)
                .ForeColor = RGB(50, 50, 50)
            Case "File"
                Select Case ext
                    Case "xls", "xlsx", "xlsm", "xlsb"
                        .Backcolor = RGB(0, 150, 0)
                        .ForeColor = RGB(255, 255, 255)
                    Case "doc", "docx", "docm", "dot", "dotm", "dotx"
                        .Backcolor = RGB(0, 80, 150)
                        .ForeColor = RGB(255, 255, 255)
                    Case "mdb", "accdb"
                        .Backcolor = RGB(200, 0, 0)
                        .ForeColor = RGB(255, 255, 255)
                    Case "pdf"
                        .Backcolor = RGB(180, 0, 130)
                        .ForeColor = RGB(255, 255, 255)
                    Case Else
                        .Backcolor = RGB(200, 200, 200)
                        .ForeColor = RGB(50, 50, 50)
                End Select
            Case Else
                .Backcolor = RGB(200, 200, 200)
                .ForeColor = RGB(50, 50, 50)
        End Select
    End With

End Function



'DATA TYPES
'vbEmpty             0       Uninitialized (Default)
'vbNull              1       Contains no valid data
'vbInteger           2       Integer
'vbLong              3       Long integer
'vbSingle            4       Single-precision floating-point number
'vbDouble            5       Double-precision floating-point number
'vbCurrency          6       Currency
'vbDate              7       Date
'vbString            8       String
'vbObject            9       Object
'vbError             10      Error
'vbBoolean           11      Boolean
'vbVariant           12      Variant (used only for arrays of variants)
'vbDataObject        13      Data access object
'vbDecimal           14      Decimal
'vbByte              17      Byte
'vbLongLong          20      LongLong integer (Valid on 64-bit platforms only.)
'vbUserDefinedType   36      Variants that contain user-defined types
'vbArray             8192    Array
Public Function ConvertToType(vntValue As Variant, vbConstType As Integer) As Variant
Select Case vbConstType
    Case 2: tempValue = CInt(vntValue)
    Case 3: tempValue = CLng(vntValue)
    Case 4: tempValue = CSng(expression)
    Case 5: tempValue = CDbl(expression)
    'Case 6: tempValue = vntValue
    Case 7: tempValue = CDate(expression)
    Case 8: tempValue = CStr(expression)
    'Case 9: tempValue =
    'Case 10: tempValue =
    Case 11: tempValue = CBool(expression)
    'Case 12: tempValue =
    'Case 13: tempValue =
    Case 14: tempValue = CDec(expression)
    Case 17: tempValue = CByte(expression)
End Select
ConvertToType = tempValue
End Function






Public Function ListOfStringValuesSQL(strDelimitedList As String, Optional strDelimiter = ",")
Dim X As Integer
Dim ary
Dim strInList As String
ary = Split(Trim(strDelimitedList), strDelimiter)

'remove all leading or trail spaces for each element in the array
For X = LBound(ary) To UBound(ary)
    ary(X) = Trim(ary(X))
Next

strInList = Join(ary, "','")
    
strInList = "'" & strInList & "'"
ListOfStringValuesSQL = strInList

End Function


