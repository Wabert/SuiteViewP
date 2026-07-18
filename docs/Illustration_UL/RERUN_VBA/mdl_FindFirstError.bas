Attribute VB_Name = "mdl_FindFirstError"


Sub findfirsterror()
'4/29/2022 - RJH
'Searches all cells in the relevant range (from Calc sheet) to find the first error.
'The search is from left to right and top to bottom.  The search range starts
'at the row with the forecast date and ends at the row with the the maturity date

Dim blnErrorFound As Boolean
Dim xRow As Long, xCol As Long, xLastRow As Long

Sheets("CalcEngine").Activate

'If running inforce illustration start the search at the forecast date row, otherwise start at the top
If Range("sINPUT_InforceIndicator") = "N" Then
    xRow = 0
Else
    xRow = Range("sForecastDateIndex")
End If
xRow = xRow + Range("sStartLegder").row - 1

'Dont check rows past the policy maturity age
xLastRow = Range("sMaturityIndex") + Range("sStartLegder").row - 1

'Row will be increased at the beginning of the loop so is needs to be decreased right before
xRow = xRow - 1

'Search each row starting at the top and searching from left to right until you find the first error or until the last row is searched
Do
    xRow = xRow + 1
    xCol = 0
    Do
        xCol = xCol + 1
        If IsError(Cells(xRow, xCol)) Then blnErrorFound = True
    Loop Until blnErrorFound Or xCol = 700
Loop Until blnErrorFound Or xRow > 1500

'If an error is found jump right to the error.  Also print the error cell address
If blnErrorFound Then
    Cells(xRow, xCol).Select
    Range("sErrorFound") = "=Hyperlink(""#" & Cells(xRow, xCol).Address & """)"
Else
    Range("sErrorFound") = "None"
End If

End Sub


