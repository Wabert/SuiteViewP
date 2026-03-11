' Module: mdl_WorksheetDataTables.bas
' Type: Standard Module
' Stream Path: VBA/mdl_WorksheetDataTables
' =========================================================

Attribute VB_Name = "mdl_WorksheetDataTables"
'This module is dedictated to reading and writing data to this workbook

Public Function GetLinkTable()
GetLinkTable = GetWorksheetTable(Environ("Username"))
End Function
Public Function WriteToLinkTable(dataArray)
    If IsArrayEmpty(dataArray) Then
        Exit Function
    End If
    WriteWorksheetTable Environ("Username"), (dataArray)
End Function

Private Function GetWorksheetTable(dataSheetName As String) As Variant
'This code assumes that the data starts in cell A1 and the first row contains the headers

    Dim ws As Worksheet
    Dim lastRow As Long, lastCol As Long
    Dim dataRange As Range
    Dim wasHidden As Boolean
    
    ' Check if the worksheet exists
    On Error Resume Next
    Set ws = ThisWorkbook.Worksheets(dataSheetName)
    On Error GoTo 0

    If ws Is Nothing Then
        Set ws = ThisWorkbook.Worksheets.Add
        ws.name = Environ("Username")
        AddLinkTableHeaders ws
    End If
    
  
    
    ' Unhide the sheet if it's hidden
    wasHidden = (ws.Visible <> xlSheetVisible)
    If wasHidden Then ws.Visible = xlSheetVisible

    ' Find the last row and column with data starting from A1
    With ws
        lastRow = .Cells(.rows.Count, 1).End(xlUp).row
        lastCol = .Cells(1, .Columns.Count).End(xlToLeft).Column
        ' Define the data range
   
        
    If lastRow = 1 Then
        GetWorksheetTable = Empty
    Else
        Set dataRange = .Range(.Cells(2, 1), .Cells(lastRow, lastCol))
        GetWorksheetTable = dataRange.value
    End If
     End With
    'Always hide ws
    ws.Visible = xlSheetHidden

End Function
Private Sub AddLinkTableHeaders(ws)
    With ws
        .Cells(1, 1) = "LinkID"
        .Cells(1, 2) = "LinkFilename"
        .Cells(1, 3) = "LinkFilepath"
        .Cells(1, 4) = "LinkType"
    End With
End Sub

Private Sub WriteWorksheetTable(dataSheetName As String, dataArray As Variant)
    Dim ws As Worksheet
    Dim wasHidden As Boolean
    Dim rowCount As Long, colCount As Long

    ' Check if the worksheet exists
    On Error Resume Next
    Set ws = ThisWorkbook.Worksheets(dataSheetName)
    On Error GoTo 0

    If ws Is Nothing Then
        ' Create the worksheet if it doesn't exist
        Set ws = ThisWorkbook.Worksheets.Add
        ws.name = dataSheetName
    End If

    ' Unhide the sheet if it's hidden
    wasHidden = (ws.Visible <> xlSheetVisible)
    If wasHidden Then ws.Visible = xlSheetVisible

    ' Clear existing content except for the first row (leave the headers alone)
    With ws
        lastRow = .Cells(.rows.Count, 1).End(xlUp).row
        lastCol = .Cells(1, .Columns.Count).End(xlToLeft).Column
        If lastRow > 1 Then
            .Range(.Cells(2, 1), .Cells(lastRow, lastCol)).ClearContents
        End If
    End With
        
    ' Get dimensions of the array
    On Error Resume Next
    rowCount = UBound(dataArray, 1)
    colCount = UBound(dataArray, 2)
    On Error GoTo 0
    
    If rowCount > 0 And colCount > 0 Then
        ' Write the array to the worksheet starting at A2 (row 2, column 1)
        ws.Range(ws.Cells(2, 1), ws.Cells(rowCount + 1, colCount)).value = dataArray
    End If


    ' Optional: Re-hide the sheet if it was originally hidden
    If wasHidden Then ws.Visible = xlSheetHidden
End Sub

