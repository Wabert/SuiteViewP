Attribute VB_Name = "mdl_BatchRun"
Dim dictNames As Dictionary
Dim ws As Worksheet
Sub BatchMain()
'processes the rows specified one by one from the batch table

Dim StartTime, TotalTime, StopTime

Set ws = ActiveSheet

With ws


StartTime = Now()
CreateNamedRangeDictionary

'Establish starting and stopping rows.  Either use defaults or inputs
Dim xStart As Long
Dim xStop As Long
xStart = 1
xStop = 2000000
If .Range("sRes_StartRow") <> "" Then xStart = .Range("sRes_StartRow") - .Range("sRes_NamedRanges").row
If .Range("sRes_StopRow") <> "" Then xStop = .Range("sRes_StopRow") - .Range("sRes_NamedRanges").row


'=============== Read in INPUT/OUTPUT indicator and the corresponding NamedRange =================
Dim dctIO As Dictionary
Set dctIO = New Dictionary

Dim dct As Dictionary
Dim x As Integer
x = 0
'Identify input/output until a blank is found
Do While UCase(.Range("sRes_IO_Indicator").Offset(0, x)) <> ""
    Set dct = New Dictionary
    
    If .Range("sRes_IO_Indicator").Offset(0, x) <> "" And .Range("sRes_NamedRanges").Offset(0, x) <> "" Then
    
        dct("IO") = .Range("sRes_IO_Indicator").Offset(0, x)
        dct("NamedRange") = .Range("sRes_NamedRanges").Offset(0, x)
        dctIO.Add dctIO.count + 1, dct
        x = x + 1
    Else
        Exit Do
    End If
Loop

'===================================== Main batch loop ============================================
Dim SetCount As Integer
Dim ProcedureName As String
Dim DestinationRange As String
Dim ReadFromRange As String
Dim p As String
Dim xRow As Long
Dim col As Long

xRow = xStart

Do While .Range("sRes_NamedRanges").Offset(xRow) <> "" And xRow < xStop
        
        'Get policy data and rates first
        
        'Pull policy data from the specified source
        Select Case dctIO(1)("NamedRange")
            Case "sCyberlifePolicyNumber":      'p = Trim(.Range("sRes_NamedRanges").Offset(xRow)) 'First range is as workbook range
                                                Range("sCyberlifePolicyNumber").Value = "'" & Trim(.Range("sRes_NamedRanges").Offset(xRow))
                                                
                                                GetPolicyFromCyberlife
                                                If Range("sRes_GetRates") Then MainGetRates
                                                'if the next column is OUTPUT then go ahead and calcluate workbook so output values are ready
                                                If dctIO(2)("IO") = "OUTPUT" Then Application.Calculate
            
            Case "sStorageNumber":                 Range("sStorageNumber") = Trim(.Range("sRes_NamedRanges").Offset(xRow)) 'First range is as workbook range
                                                RetrieveCase
                                                If Range("sRes_GetRates") Then MainGetRates
            
            
            Case Else: 'Do nothing.
        End Select
        
        col = 2
        'After each set of inputs are updated, calcluations are triggered and outputs are collected.  Then the process continues if more inputs and outputs are defined (ie SetCount > 1)
        Do While col <= dctIO.count
            Select Case dctIO(col)("IO")
                Case "INPUT":   ProcessBatchINPUT col, xRow, dctIO
                                Application.Calculate 'Calculate after INPUTs are populated
                Case "OUTPUT": ProcessBatchOUTPUT col, xRow, dctIO
                Case "MACRO": ProcessBatchMACRO col, xRow, dctIO
            End Select
        Loop
        xRow = xRow + 1
Loop

StopTime = Now()
TotalTime = StopTime - StartTime
.Range("sTotalRunTime") = TotalTime

End With

End Sub

Sub ProcessBatchINPUT(ByRef col As Long, xRow As Long, dctIO As Dictionary)
'Copies values from the batch table an populates the named range indicated (ie DestinationRange)
Dim DestinationRange As String
Dim InputValue As Variant
Dim NamedRangeForInput As String

    Do While dctIO(col)("IO") = "INPUT"
        
        DestinationRange = dctIO(col)("NamedRange")
        If DestinationRange <> "" Then
                        
            InputValue = ws.Range("sRes_NamedRanges").Offset(xRow, col - 1)
                                            
            'If the input is in the form of "ValueOf(...)" then extract the named range and get its value
            If Left(InputValue, 8) = "ValueOf(" Then
                NamedRangeForInput = Mid(InputValue, 9, Len(InputValue) - 8 - 1)
                InputValue = ws.Range(NamedRangeForInput)
            End If
            
            'Populate the target range with the InputValue.  This range is scoped to the workbook
            Range(DestinationRange) = InputValue
        
        End If
        col = col + 1
        If col > dctIO.count Then Exit Do
    Loop

End Sub
Sub ProcessBatchOUTPUT(ByRef col As Long, xRow As Long, dctIO As Dictionary)
'Copies values specified by ReadFromRange and pastes them into the batch table
Dim ReadFromRange As String
Do While dctIO(col)("IO") = "OUTPUT"
    ReadFromRange = dctIO(col)("NamedRange")
    If ReadFromRange <> "" Then
        ws.Range("sRes_NamedRanges").Offset(xRow, col - 1).Value = Range(ReadFromRange).Value 'this last range is scoped to workbook
    End If
    col = col + 1
    If col > dctIO.count Then Exit Do
Loop
End Sub
Sub ProcessBatchMACRO(ByRef col As Long, xRow As Long, dctIO As Dictionary)
'Run each Macro that is idenified by name
Dim ProcedureName As String
Dim StartTime, StopTime

Do While dctIO(col)("IO") = "MACRO"
    ProcedureName = dctIO(col)("NamedRange")
    If ProcedureName <> "" Then
        StartTime = Now()
        Run ProcedureName
        StopTime = Now()
        ws.Range("sRes_NamedRanges").Offset(xRow, col - 1).Value = StopTime - StartTime
    End If
    col = col + 1
    If col > dctIO.count Then Exit Do
Loop
End Sub


Function IsNamedRange(R As String) As Boolean
'Tests to see if a string is a named range in the workbook
    Dim test As Range
    On Error Resume Next
    nm = ThisWorkbook.Names(R)
    IsNamedRange = (Err.Number = 0)
    On Error GoTo 0
End Function

Sub CreateNamedRangeDictionary()
'Creates a dictionary of valid named ranges in this workbook
'https://stackoverflow.com/questions/12611900/test-if-range-exists-in-vba


'    'Initially, check whether names dictionary has already been created
'    If Not dictNames Is Nothing Then
'        'if so, dictNames is set to nothing
'        Set dictNames = Nothing
'    End If

    'Set to new dictionary and set compare mode to text
    Set dictNames = New Dictionary
    dictNames.CompareMode = TextCompare

    'For each Named Range
    Dim nm As Name
    For Each nm In ThisWorkbook.Names
        'Check if it refers to an existing cell (bad references point to "#REF!" errors)
        If Not (Strings.Right(nm.RefersTo, 5) = "#REF!") Then
            'Only in that case, create a Dictionary entry
            'The key will be the name of the range and the item will be the address, worksheet included
            dictNames(nm.Name) = nm.RefersTo
        End If
    Next

    'You now have a dictionary of valid named ranges that can be checked
End Sub


Sub ResetPrem()
    Sheets("INPUT").Range("L124").AutoFill Destination:=Sheets("INPUT").Range("L5:L124")
End Sub


Sub MinFaceByGLP()
'This procedure sets up the Bisection Search box and Target Value box to solve for minimum face amount to get the GLP = first year premium
    Range("sSearch_Type") = "Face"
    
    Range("sSearch_Independent_Range").Value = "sFirst_Face_Value"
    Range("sSearch_Independent_Index").Value = 1

    Range("sSearch_Dependent_Range").Value = "sGLP_Issue"
    Range("sSearch_Dependent_Index").Value = 1
    Range("sSearch_Dependent_GoalValue").Value = Range("sFirst_Premium")

    Range("sSearch_MaxIteration").Value = 40
    Range("sSearch_Independent_Tolerance").Value = 1
    
    BisectionSearch
End Sub


Sub SetupLoanSearch()
    Range("sSearch_Type").Value = "Loan"
    Range("sSearch_Independent_Range").Value = "vINPUT_Loans"
    Range("sSearch_Independent_Index").Value = Range("sINPUT_PayDuration") + 1
    
    Range("sSearch_Dependent_Range").Value = "sMinESV_AfterLoans"
    Range("sSearch_Dependent_Index").Value = 1
    Range("sSearch_Dependent_GoalValue").Value = 1000
    
    Range("sSearch_MaxIteration").Value = 40
    Range("sSearch_Independent_Tolerance").Value = 1

End Sub

Sub SetupPremiumPayments()
'Assumes Premium Start Year is 1 then populates each cell underneath it with a refernce to the cell above for the specified duration
'all other cells in this loan column  are set to 0

Dim PremiumStartYear As Integer
Dim PayDuration As Integer
Dim x As Integer

PremiumStartYear = 1
PayDuration = Range("sINPUT_PayDuration")
For x = 2 To Range("vINPUT_Premium_Amount").Rows.count
    If x > PremiumStartYear And x < PremiumStartYear + PayDuration Then
        Range("vINPUT_Premium_Amount").Rows(x) = "=" & Range("vINPUT_Premium_Amount").Rows(x - 1).Address(False, False)
    Else
        Range("vINPUT_Premium_Amount").Rows(x) = 0
    End If
Next

End Sub


Sub SetupLoanDistributions()
'Finds the Loan Start Year in the vINPUT_Loans column and populates each cell underneath it with a refernce to the cell above for the specified duration
'all other cells in this loan column  are set to 0

Dim LoanStartYear As Integer
Dim LoanDuration As Integer
Dim x As Integer

LoanStartYear = Range("sINPUT_LoanStartYear")
LoanDuration = Range("sINPUT_LoanDuration")
For x = 1 To Range("vINPUT_Loans").Rows.count
    If x > LoanStartYear And x < LoanStartYear + LoanDuration Then
        Range("vINPUT_Loans").Rows(x) = "=" & Range("vINPUT_Loans").Rows(x - 1).Address(False, False)
    Else
        Range("vINPUT_Loans").Rows(x) = 0
    End If
Next

End Sub


Sub SetupDBOChange()
'Finds the Year of DBO change and pastes in the new specified DBO in the vINPUT_DBO column
'This assumes that the first year DBO is already specifed and the change will occur sometime after year 1

Dim NewDBO As String
Dim DBOChangeYear As Integer
Dim x As Integer

NewDBO = Range("sINPUT_NewDBO")
DBOChangeYear = Range("sINPUT_DBOChangeDuration")
For x = 2 To Range("vINPUT_DBO").Rows.count
    If x = DBOChangeYear Then
        Range("vINPUT_DBO").Rows(x) = NewDBO
    Else
        Range("vINPUT_DBO").Rows(x) = "=" & Range("vINPUT_DBO").Rows(x - 1).Address(False, False)
    End If
Next

End Sub

Sub SetupB2AandLoansAfterPremium()

    SetupPremiumPayments

    SetupDBOChange

    SetupLoanDistributions
                        
End Sub



