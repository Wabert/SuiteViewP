Attribute VB_Name = "mdl_SaveCase"
Const CASE_RANGE_COLUMN = 1 'The column on the Case sheet that contains the named ranges
Const CASE_INDEX_COLUMN = 2 'The column on the CAse sheet that contains the index to use for the corresponding named range
Const CASE_STARTING_ROW = 2 'The row at which the policiy information starts

Sub SaveNewCase()
    SaveCase
    Sheets("INPUT").Select
End Sub
Sub UpdateCase()
    SaveCase Range("sStorageNumber").Value
    Sheets("INPUT").Select
End Sub
Sub RetrieveSpecifiedCase()
    RetrieveCase
    Sheets("INPUT").Select
End Sub
Sub SaveCase(Optional InputCase As Integer = 0)
Attribute SaveCase.VB_ProcData.VB_Invoke_Func = " \n14"
Application.ScreenUpdating = False
CalcMode = Application.Calculation
Application.Calculation = xlCalculationManual
'This procedure copies the current case data so it can be retrieved later.  If InputCase is passed to this
'procedure then the data will overwrite the data for the specified case.  If no InputCase is passed then
'a new case is created in the Case sheet


'Copy the cases data captured by the formulas in the first column of the Cases sheet
'
'Range("A2").Select
'Range(Selection, Selection.End(xlDown)).Select
'Selection.Copy

'If InputCase is 0 then create a new case otherwise overwrite and existing case
CurrentlyVisible = SavedCases.Visible
SavedCases.Visible = True
SavedCases.Select
If InputCase = 0 Then
    'Find the first available slot and number the new case
    ColumnLock = 1
    Do Until Cells(1, ColumnLock).Value = ""
        ColumnLock = ColumnLock + 1
    Loop
Else
    ColumnLock = InputCase + CASE_INDEX_COLUMN
End If

Dim RngName As String
Dim RngIndex As Integer
CurrentRow = CASE_STARTING_ROW
Do While Cells(CurrentRow, CASE_RANGE_COLUMN) <> ""
    RngName = Cells(CurrentRow, CASE_RANGE_COLUMN).Value
    RngIndex = Cells(CurrentRow, CASE_INDEX_COLUMN).Value
    
    'See if TimeStamp is requested, and if so print the date and time when the this case is saved
    If RngName = "TimeStamp" Then
        Cells(CurrentRow, ColumnLock) = Format(Now(), "m/d/yyyy  h:m:ss")
    Else
        
        'if there is a 0 value for a date, just return a blank.  This is simply because it looks cleaner
        If IsDateRange(RngName) And Range(RngName)(RngIndex).Value = 0 Then
            Cells(CurrentRow, ColumnLock) = ""
        Else
            'Range(RngName)(RngIndex).Copy
            'Range(Cells(CurrentRow, ColumnLock).Address).PasteSpecial Paste:=xlPasteFormulasAndNumberFormats
            l = Range(RngName).Formula2R1C1Local
            Cells(CurrentRow, ColumnLock).Value = Range(RngName)(RngIndex).Formula2R1C1Local
        End If
    End If
    CurrentRow = CurrentRow + 1
Loop

'The StorageNumber is the unique number for the case on the Case sheet.
StorageNumber = ColumnLock - CASE_INDEX_COLUMN
Cells(1, ColumnLock) = StorageNumber

'Storage Nubmer is a copied to the INPUT sheet so that it shows the case that was just saved
Range("sStorageNumber") = StorageNumber

SavedCases.Visible = CurrentlyVisible
Application.Calculation = CalcMode
Application.ScreenUpdating = True
End Sub

Sub RetrieveCase()

Application.ScreenUpdating = False
Application.Calculation = xlCalculationManual
Dim CaseNumber As String
CaseNumber = Range("sStorageNumber")

Dim CurrentRow As Integer
CurrentRow = CASE_STARTING_ROW

Dim CaseValue As Variant
Dim RngName As String
Dim RngIndex As Integer
SavedCases.Select
Do While Cells(CurrentRow, CASE_RANGE_COLUMN) <> ""
    RngName = Cells(CurrentRow, CASE_RANGE_COLUMN).Value
    RngIndex = Cells(CurrentRow, CASE_INDEX_COLUMN).Value
    
    'A RngIndex of 0 means that RngName is not really a Named Range and this row should be skipped when retriving a case.  For example RngName might equal "TimeStamp" (see SaveCase sub above)
    If RngIndex = 0 Then
        'Do nothing, skip row
    Else
        'if there is a 0 value for a date, just return a blank.  This is simply because it looks cleaner
        If IsDateRange(RngName) And CaseValue = 0 Then CaseValue = ""
        
        Range(RngName)(RngIndex).Value = Cells(CurrentRow, CaseNumber + CASE_INDEX_COLUMN).Formula2R1C1Local
    End If
    
    CurrentRow = CurrentRow + 1
Loop
        

Application.ScreenUpdating = True
        
End Sub

Private Function IsDateRange(RangeName As String) As Boolean
Dim tempValue As Boolean
Select Case RangeName
Case "sINPUT_Lumpsum_Date", "sINPUT_CTR_Change_Date", "sINPUT_PW_Change_Date", _
    "sINPUT_PWST_Change_Date", "sINPUT_GIR_Change_Date", "sINPUT_CCV_Change_Date", _
    "sINPUT_LTR_Change_Date", "sINPUT_SigTerm1_Change_Date", "sINPUT_OIR_Change_Date", _
    "sINPUT_IssueDateSA2", "sINPUT_MAP_CeaseDate", "sINPUT_MonthlyMTP", " sINPUT_CTP", _
    "sINPUT_IssueDateSA3": tempValue = True
    
Case Else: tempValue = False
End Select

IsDateRange = tempValue

End Function



