Attribute VB_Name = "mdl_LocalData"
Option Explicit

'Absolute repo root baked in at install time (tools/rerun_install_local_vba.py).
Private Const REPO_ROOT_FALLBACK As String = "__REPO_ROOT__"

'=====================================================================
' LOCAL DATA PATH  (installed by tools/rerun_install_local_vba.py)
'
' When INPUT!sDataSource starts with "Local", GetPolicyFromCyberlife and
' MainGetRates branch here instead of hitting DB2 / UL_Rates SQL Server.
' Both subs shell the repo's venv Python bridge (tools/rerun_local_bridge.py),
' which reads bundled_data/dev/*.sqlite and writes a temp .xlsx that is
' pasted onto the same ranges the production path uses.
'
' sDataSource values:  Production | Local | Local (no benefits)
'   "no benefits" suppresses PW/PWST/GIR/ADB booleans - a fallback for the
'   rare benefit whose tBenefitDefinitionFile key is missing (#N/As the run).
'=====================================================================

Public Function IsLocalData() As Boolean
    On Error GoTo NoName
    IsLocalData = (LCase$(Left$(CStr(Range("sDataSource").Value), 5)) = "local")
    Exit Function
NoName:
    IsLocalData = False
End Function

Public Function LocalSkipBenefits() As Boolean
    On Error Resume Next
    LocalSkipBenefits = InStr(1, LCase$(CStr(Range("sDataSource").Value)), "no benefit") > 0
End Function

Private Function RepoRoot() As String
    'Workbook normally lives in <root>\docs\Illustration_UL; if it was copied
    'elsewhere (temp copies, automation), fall back to the installed path.
    RepoRoot = ThisWorkbook.Path & "\..\.."
    If Dir(RepoRoot & "\venv\Scripts\python.exe") = "" Then
        RepoRoot = REPO_ROOT_FALLBACK
    End If
End Function

Private Function TempName(base As String) As String
    TempName = Environ$("TEMP") & "\rerun_local_" & base
End Function

Private Sub WriteTextFile(path As String, text As String)
    Dim f As Integer: f = FreeFile
    Open path For Output As #f
    Print #f, text
    Close #f
End Sub

Private Function JsonPath(path As String) As String
    JsonPath = Replace(path, "\", "/")
End Function

Private Sub RunBridge(argsJson As String, statusPath As String)
'Run the Python bridge synchronously; raise on failure.
    Dim argsPath As String: argsPath = TempName("args.json")
    On Error Resume Next
    Kill statusPath
    On Error GoTo 0
    WriteTextFile argsPath, argsJson

    Dim cmd As String
    cmd = """" & RepoRoot() & "\venv\Scripts\python.exe"" """ & _
          RepoRoot() & "\tools\rerun_local_bridge.py"" """ & argsPath & """"
    Trace "bridge: exec " & cmd

    Dim sh As Object: Set sh = CreateObject("WScript.Shell")
    Dim rc As Long
    rc = sh.Run(cmd, 0, True)      'hidden window, wait for exit
    Trace "bridge: exit code " & rc

    If Dir(statusPath) = "" Then
        Err.Raise vbObjectError + 513, , _
            "Local bridge wrote no status file (exit " & rc & ")." & vbCrLf & cmd
    End If
    Dim f As Integer, status As String
    f = FreeFile
    Open statusPath For Input As #f
    status = Input$(LOF(f), #f)
    Close #f
    If InStr(1, status, """ok"": true") = 0 Then
        Err.Raise vbObjectError + 514, , "Local bridge failed:" & vbCrLf & status
    End If
End Sub

Private Sub Notify(msg As String)
    'MsgBox only when a human is driving; automation reads silently.
    If Application.UserControl Then MsgBox msg, vbInformation, "Local Data"
End Sub

Private Sub Trace(step As String)
    'Breadcrumbs for debugging automation stalls: %TEMP%\rerun_local_trace.log
    On Error Resume Next
    Dim f As Integer: f = FreeFile
    Open TempName("trace.log") For Append As #f
    Print #f, Format$(Now, "hh:nn:ss") & "  " & step
    Close #f
End Sub

'---------------------------------------------------------------------
' POLICY PULL (local replacement for GetPolicyFromCyberlife)
'---------------------------------------------------------------------
Public Sub GetPolicyFromLocal()
    Dim CalcStatus
    CalcStatus = Application.Calculation
    Application.Calculation = xlCalculationManual
    Application.ScreenUpdating = False

    Dim outPath As String, statusPath As String
    outPath = TempName("policy.xlsx")
    statusPath = TempName("status.txt")
    On Error Resume Next
    Kill outPath
    On Error GoTo 0

    Trace "policy: bridge start " & Range("sCyberlifePolicyNumber")
    RunBridge "{""mode"": ""policy"", ""policy"": """ & Range("sCyberlifePolicyNumber") & _
              """, ""region"": """ & Range("sQueryRegion") & _
              """, ""skip_benefits"": " & LCase$(CStr(LocalSkipBenefits())) & _
              ", ""out"": """ & JsonPath(outPath) & _
              """, ""status"": """ & JsonPath(statusPath) & """}", statusPath
    Trace "policy: bridge done, opening " & outPath

    Dim wbData As Workbook, arr As Variant, meta As String
    Set wbData = Workbooks.Open(outPath, ReadOnly:=True)
    Trace "policy: data workbook open"
    arr = wbData.Worksheets("INPUTS").UsedRange.Value
    On Error Resume Next
    meta = CStr(wbData.Worksheets("META").Range("A1").Value)
    On Error GoTo 0
    wbData.Close False
    Trace "policy: writing " & UBound(arr, 1) - 1 & " inputs"

    ThisWorkbook.Activate
    Dim i As Long, nOK As Long, failures As String
    For i = 2 To UBound(arr, 1)          'row 1 = header
        On Error Resume Next
        Err.Clear
        If CStr(arr(i, 3)) = "vector1" Then
            Range(CStr(arr(i, 1))).Rows(1).Value = arr(i, 2)
        Else
            Range(CStr(arr(i, 1))).Value = arr(i, 2)
        End If
        If Err.Number <> 0 Then
            failures = failures & arr(i, 1) & "; "
        Else
            nOK = nOK + 1
        End If
        On Error GoTo 0
    Next

    Trace "policy: inputs written (" & nOK & " ok), running PopulateInputFormulas"
    Range("sUID") = Application.UserName & " (local)"
    Range("vPlancodesAddedManually").ClearContents
    PopulateInputFormulas
    Trace "policy: done"

    Application.ScreenUpdating = True
    Application.Calculation = CalcStatus

    Dim msg As String
    msg = "Local policy loaded: " & Range("sCyberlifePolicyNumber") & "  (" & nOK & " inputs)"
    If failures <> "" Then msg = msg & vbCrLf & "Unmatched names: " & failures
    If meta <> "" Then msg = msg & vbCrLf & "Notes: " & meta
    msg = msg & vbCrLf & "Now click Get Rates to load this plancode's rates locally."
    Notify msg
End Sub

'---------------------------------------------------------------------
' RATES PULL (local replacement for the UL_Rates queries in MainGetRates)
'---------------------------------------------------------------------
Public Sub GetRatesLocal()
    Dim CalcStatus
    CalcStatus = Application.Calculation
    Application.Calculation = xlCalculationManual
    Application.ScreenUpdating = False

    'Collect plancodes exactly like MainGetRates: base + active riders + APB + manual
    Dim pcs As String
    pcs = """" & Range("sPlancode") & """"
    If Range("sINPUT_R1_Boolean") Then pcs = pcs & ", """ & Range("sINPUT_R1_Plancode") & """"
    If Range("sINPUT_R2_Boolean") Then pcs = pcs & ", """ & Range("sINPUT_R2_Plancode") & """"
    If Range("sINPUT_R3_Boolean") Then pcs = pcs & ", """ & Range("sINPUT_R3_Plancode") & """"
    If Range("sINPUT_APB_Boolean") Then pcs = pcs & ", """ & Range("sINPUT_APB_Plancode") & """"
    Dim x As Long, pc As String
    For x = 1 To Range("vPlancodesAddedManually").Count
        pc = Trim$(CStr(Range("vPlancodesAddedManually")(x).Value))
        If pc <> "" And pc <> "0" Then pcs = pcs & ", """ & pc & """"
    Next

    Dim outPath As String, statusPath As String
    outPath = TempName("rates.xlsx")
    statusPath = TempName("status.txt")
    On Error Resume Next
    Kill outPath
    On Error GoTo 0

    Trace "rates: bridge start [" & pcs & "]"
    RunBridge "{""mode"": ""rates"", ""plancodes"": [" & pcs & _
              "], ""state"": """ & Range("sQueryWithStateCode") & _
              """, ""out"": """ & JsonPath(outPath) & _
              """, ""status"": """ & JsonPath(statusPath) & """}", statusPath
    Trace "rates: bridge done, opening " & outPath

    Dim wbData As Workbook, ws As Worksheet, meta As String
    Set wbData = Workbooks.Open(outPath, ReadOnly:=True)

    'Unqualified Range(name) below must resolve against RERUN, not the
    'freshly-opened data workbook.
    ThisWorkbook.Activate

    Dim pasted As String
    For Each ws In wbData.Worksheets
        If Left$(ws.Name, 5) = "Span_" Then
            Trace "rates: pasting " & ws.Name
            PasteBlockLocal ws
            pasted = pasted & ws.Name & " (" & ws.UsedRange.Rows.Count & ")  "
        End If
    Next
    On Error Resume Next
    meta = CStr(wbData.Worksheets("META").Range("A1").Value)
    On Error GoTo 0

    'vPlancodesPresent <- target-family plancodes from META col A (rows 2+)
    ThisWorkbook.Activate
    Range("vPlancodesPresent").ClearContents
    Dim r As Long
    r = 2
    Do While CStr(wbData.Worksheets("META").Cells(r, 1).Value) <> ""
        Range("vPlancodesPresent").Rows(r - 1) = wbData.Worksheets("META").Cells(r, 1).Value
        r = r + 1
    Loop
    wbData.Close False

    'IUL steps - mirrors the tail of MainGetRates (recalc first so the
    'workbook-computed Available Rates reflect the freshly pasted rates).
    Trace "rates: pasted, recalculating"
    Application.Calculate
    Trace "rates: recalc done"
    Dim ProdType As String
    ProdType = GetPlancodeData(CStr(Range("sPlancode")), "ReportTemplate")
    If ProdType = "IUL" Then
        Range("vINPUT_Illustrated_Rates").Rows(1).Value = Range("vINPUT_Available_Rates").Value
        Range("sINPUT_Variable_Loan_Rate").Value = Range("sVariableLoanRateLookup").Value
    End If

    Application.ScreenUpdating = True
    Application.Calculation = CalcStatus

    Dim msg As String
    msg = "Local rates loaded: " & pasted
    If meta <> "" Then msg = msg & vbCrLf & "Notes: " & meta
    Notify msg
End Sub

Private Sub PasteBlockLocal(wsData As Worksheet)
'Clear the existing Span_* block, paste the bridge rows onto its anchor.
    Dim tgt As Range
    Set tgt = Range(wsData.Name)         'resolves INDIRECT-defined names too
    Dim wsTgt As Worksheet
    Set wsTgt = tgt.Worksheet

    Dim arr As Variant, nRows As Long, nCols As Long
    arr = wsData.UsedRange.Value
    If IsEmpty(arr) Then
        nRows = 0
    ElseIf Not IsArray(arr) Then         'single cell
        nRows = 1: nCols = 1
    Else
        nRows = UBound(arr, 1): nCols = UBound(arr, 2)
    End If

    'Clear from the anchor row down to the last used row in the anchor column.
    Dim lastRow As Long, clearRows As Long
    lastRow = wsTgt.Cells(wsTgt.Rows.Count, tgt.Column).End(xlUp).Row
    clearRows = lastRow - tgt.Row + 1
    If clearRows < 1 Then clearRows = 1
    If nCols < tgt.Columns.Count Then nCols = tgt.Columns.Count
    wsTgt.Range(wsTgt.Cells(tgt.Row, tgt.Column), _
                wsTgt.Cells(tgt.Row + clearRows - 1, tgt.Column + nCols - 1)).ClearContents

    If nRows > 0 Then
        If IsArray(arr) Then
            wsTgt.Range(wsTgt.Cells(tgt.Row, tgt.Column), _
                        wsTgt.Cells(tgt.Row + nRows - 1, tgt.Column + UBound(arr, 2) - 1)).Value = arr
        Else
            wsTgt.Cells(tgt.Row, tgt.Column).Value = arr
        End If
    End If
End Sub
