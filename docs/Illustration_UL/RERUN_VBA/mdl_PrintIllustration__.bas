Attribute VB_Name = "mdl_PrintIllustration__"
'
'Sub CopyCurrentDistributions()
'    'Calculates ledger values using Current assumptions, then copies the AppliedNetWithdrawal
'    'and AppliedLoan values to the Distribution sheet.  These values will be used by
'    'Alternative and Guaranteed assumptions
'
'    Range("sAssumption") = "Current"
'    Application.Calculate
'    Range("vAppliedTotalPremium").Copy
'    Range("vCurrentAppliedTotalPremium").PasteSpecial (xlPasteValues)
'    Range("vAppliedNetWithdrawal").Copy
'    Range("vCurrentAppliedNetWD").PasteSpecial (xlPasteValues)
'    Range("vAppliedLoan").Copy
'    Range("vCurrentAppliedLoan").PasteSpecial (xlPasteValues)
'
'    'Commented out on 6/14/2021
'    'Range("vCurrentSA1").Copy
'    'Range("vCurrentCurrentSA1").PasteSpecial (xlPasteValues)
'
'    'Added on 1/21/2022
'    Range("vGP_Exception_Prem").Copy
'    Range("vCurrentGP_Exception_Prem").PasteSpecial (xlPasteValues)
'
'End Sub
'
'Sub ProduceAllLedgerValues()
'    'Calculates values in the ledger then copies to the ReportValues sheet.
'    'This must be done 3 times, once for Current, Alternative and Guarateed
'    'Current must be done first because it determines the distributions that
'    'all the assumpitions must use
'
'    CurrentCalcMode = Application.Calculation
'
'    Application.Calculation = xlCalculationManual
'
'    Range("sblnPrintMode").Value = True
'
'    Dim StartingAssumption As String
'    StartingAssumption = Range("sAssumption")
'
'    CopyCurrentDistributions
'
'    Range("mLedgerValues").Copy
'    Range("mLedgerValuesCurrent").PasteSpecial (xlPasteValues)
'
'    Range("mLedgerIdentification").Copy
'    Range("mLedgerKey").PasteSpecial (xlPasteValues)
'
'
'    Range("sAssumption") = "Guaranteed"
'    Application.Calculate
'
'    Range("mLedgerValues").Copy
'    Range("mLedgerValuesGuaranteed").PasteSpecial (xlPasteValues)
'
'    Range("sAssumption") = "Alternative"
'    Application.Calculate
'
'    Range("mLedgerValues").Copy
'    Range("mLedgerValuesAlternative").PasteSpecial (xlPasteValues)
'
'    Range("sAssumption") = StartingAssumption
'    Application.Calculate
'
'    Range("sblnPrintMode").Value = False
'
'
'    Application.Calculation = CurrentCalcMode
'
'End Sub
'
'Sub printIllustration()
'    If Left(Range("sReportPathNameDefault"), 4) = "http" Then
'        printIllustrationToSharePoint
'    Else
'        printIllustrationToFolder
'    End If
'End Sub
'
'Sub printIllustrationToFolder()
''This procedure will ProduceAllLedgerValues then print the illustration report in PDF format to a folder specified by the user
'    Dim CalcStatus
'    CalcStatus = Application.Calculation
'
'    Application.Calculate
'    Application.Calculation = xlCalculationManual
'
'    Dim rptPathName As String, rptFileName As String, rptFullPath As String
'    rptFileName = IIf(Range("sReportFileName") <> "", Range("sReportFileName"), Range("sReportFileNameDefault"))
'
'
'    'Check to see if file name is valid
'    If Not IsValidFileName(rptFileName) Then
'        Call MsgBox("Filename has invalid characters.  File not saved")
'        Exit Sub
'    End If
'
'    'Build full path of new filename.  If none was entered by user use the default values
'    rptFullPath = Range("sReportPathNameDefault") & "\" & rptFileName & ".pdf"
'
'   'Check to see if document already exists (still need code to see if its open)
'    Dim strFileExists As String
'    Dim PrintFile As Boolean
'    strFileExists = Dir(rptFullPath)
'
'    'if strFileExists <> "" then the document already exists
'    If strFileExists <> "" Then
'        Dim Replace
'        Replace = MsgBox("This file already exists.  Do you want to replace it?", vbYesNo)
'        If Replace = vbYes Then
'            If IsFileOpen(rptFullPath) Then
'                MsgBox "That file is currently open.  It must be close before it can be overwritten"
'                Exit Sub
'            End If
'        Else
'            Call MsgBox("File not saved.", vbOKOnly)
'            Exit Sub
'        End If
'    End If
'
'
'    'Calculate all and copy all ledger values
'    ProduceAllLedgerValues
'
'    Dim ReportType As String
'    ReportType = Range("sReportData_ReportTemplate")
'
'    Select Case ReportType
'        Case "IUL": IULPrint
'        Case "UL": ULPrint
'        Case "SGUL": SGULPrint
'    End Select
'
''    'Determine which Illustraion Pages will need to print (it depends on if the number of pages is 5 or 6)
''    If (Range("sReportData_NumberOfPages") = "5") Then
''            Sheets(Array("Illustration Page 1", "Illustration Page 2", _
''            "Illustration Page 4", "Illustration Page 5", "Illustration Page 6")).Select
''    Else
''        Sheets(Array("Illustration Page 1", "Illustration Page 2", "Illustration Page 3", _
''            "Illustration Page 4", "Illustration Page 5", "Illustration Page 6")).Select
''    End If
''    Sheets("Illustration Page 1").Activate
'
'
'    'The code below will overwrite the existing document automatically unless the document is open - in that case you will get an error message
'
'    'Export to .pdf
'    ActiveSheet.ExportAsFixedFormat Type:=xlTypePDF, fileName:=rptFullPath _
'    , Quality:=xlQualityStandard, IncludeDocProperties:=True, IgnorePrintAreas _
'    :=False, OpenAfterPublish:=False
'
'
'    'Unhide any columns that may have been hidden to print report
'    Columns("A:CZ").Select
'    Selection.EntireColumn.Hidden = False
'
'
'    'Return to INPUT sheet
'    Sheets("INPUT").Select
'
'    Application.Calculation = CalcStatus
'End Sub
'
'Sub IULPrint()
'        Dim sheetname As String
'        sheetname = "IUL - Illustration Pages"
'        Sheets(sheetname).Select
'
'        'Unhide everything, then hide columns as needed
'        ThisWorkbook.Sheets(sheetname).Activate
'        Columns("O:DZ").Select
'        Selection.EntireColumn.Hidden = False
''
''        'Hide the "Premium To Reduce Loan" column if needed
''        If Not Range("sReportData_PremiumReducedLoan") Then
''            Range("dPremToReduceLoan_Report_Columns").Select
''            Selection.EntireColumn.Hidden = True
''        End If
''
'
'        '4/1/2024 - RH: Hide the "Loan Repayment" column if needed
'        If Not Range("sReportData_LoanRepayment") Then
'            Range("dPremToReduceLoan_Report_Columns").Select
'            Selection.EntireColumn.Hidden = True
'        End If
'
'        'Hide the "Weighted Ave Int rate" column if needed
'        If Not Range("sReportData_UseWAIR") Then
'            Range("dWAIR_Report_Columns").Select
'            Selection.EntireColumn.Hidden = True
'        End If
'
'
'    ThisWorkbook.Sheets(sheetname).Select
'    RngRoot = "sIULSubRange"
'    MaxPages = 6
'    Dim dctPrnt As Dictionary
'    Set dctPrnt = New Dictionary
'    For x = 1 To MaxPages
'        'If the named range is empty then we dont want to print that sheet
'        If Range(RngRoot & x) <> "" Then
'            dctPrnt.Add Range(RngRoot & x), Range(RngRoot & x)
'        End If
'    Next
'    Dim PrintRangetxt As String
'    PrintRangetxt = Join(dctPrnt.Keys, ",")
'    ActiveSheet.PageSetup.PrintArea = PrintRangetxt
'
''    'Restore print range
''    For x = 1 To MaxPages
''        PrintRangetxt = PrintRangetxt & Range(RngRoot & x)
''    Next
''    Debug.Print PrintRangetxt
''    ActiveSheet.PageSetup.PrintArea = PrintRangetxt
'
'
'End Sub
'
'Sub ULPrint()
'    Dim sheetname As String
'    sheetname = "UL - Illustration Pages"
'    Sheets(sheetname).Select
'
'
'    ThisWorkbook.Sheets(sheetname).Activate
'    Selection.Activate
'    RngRoot = "sULSubRange"
'    MaxPages = 6
'    Dim dctPrnt As Dictionary
'    Set dctPrnt = New Dictionary
'    For x = 1 To MaxPages
'        'If the named range is empty then we dont want to print that sheet
'        If Range(RngRoot & x) <> "" Then
'            dctPrnt.Add Range(RngRoot & x), Range(RngRoot & x)
'        End If
'    Next
'    Dim PrintRangetxt As String
'    PrintRangetxt = Join(dctPrnt.Keys, ",")
'    Debug.Print PrintRangetxt
'    ActiveSheet.PageSetup.PrintArea = PrintRangetxt
'
'End Sub
'Sub SGULPrint()
'    Dim sheetname As String
'    sheetname = "SGUL - Illustration Pages"
'    Sheets(sheetname).Select
'
'
'    ThisWorkbook.Sheets(sheetname).Activate
'    Selection.Activate
'    RngRoot = "sSGULSubRange"
'    MaxPages = 6
'    Dim dctPrnt As Dictionary
'    Set dctPrnt = New Dictionary
'    For x = 1 To MaxPages
'        'If the named range is empty then we dont want to print that sheet
'        If Range(RngRoot & x) <> "" Then
'            dctPrnt.Add Range(RngRoot & x), Range(RngRoot & x)
'        End If
'    Next
'    Dim PrintRangetxt As String
'    PrintRangetxt = Join(dctPrnt.Keys, ",")
'    Debug.Print PrintRangetxt
'    ActiveSheet.PageSetup.PrintArea = PrintRangetxt
'
'
'End Sub
'
'Private Function CheckFileExists(sFullPath As String)
'
'Dim strFileExists As String
'
'    strFileExists = Dir(sFullPath)
'
'   If strFileExists = "" Then
'        MsgBox "The selected file doesn't exist"
'    Else
'        MsgBox "The selected file exists"
'    End If
'
'End Function
'
'Function IsValidFileName(ByVal fileName As String) As Boolean
''Checks each character in the string 'FileName' to see if its an invalid character for a file name.
''FileName should not be the full path, only the file name
'
'Dim dctInvalid As Dictionary
'Set dctInvalid = New Dictionary
'dctInvalid.Add "*", "*"
'dctInvalid.Add "|", "|"
'dctInvalid.Add "\", "\"
'dctInvalid.Add "/", "/"
'dctInvalid.Add ":", ":"
'dctInvalid.Add """", """"
'dctInvalid.Add "<", "<"
'dctInvalid.Add ">", ">"
'
'tempIsValid = True
'
'For x = 1 To Len(fileName)
'    substring = Mid(fileName, x, 1)
'    If dctInvalid.Exists(substring) Then
'        tempInvalid = False
'        Exit For
'    End If
'Next
'IsValidFileName = tempIsValid
'End Function
'
'Function IsFileOpen(fileName As String)
''From https://exceloffthegrid.com/vba-find-file-already-open/
'Dim fileNum As Integer
'Dim errNum As Integer
'
''Allow all errors to happen
'On Error Resume Next
'fileNum = FreeFile()
'
''Try to open and close the file for input.
''Errors mean the file is already open
'Open fileName For Input Lock Read As #fileNum
'Close fileNum
'
''Get the error number
'errNum = Err
'
''Do not allow errors to happen
'On Error GoTo 0
'
''Check the Error Number
'Select Case errNum
'
'    'errNum = 0 means no errors, therefore file closed
'    Case 0
'    IsFileOpen = False
'
'    'errNum = 70 means the file is already open
'    Case 70
'    IsFileOpen = True
'
'    'Something else went wrong
'    Case Else
'    IsFileOpen = errNum
'
'End Select
'
'End Function
'
''------------------------------------------------------------------
'' printIllustrationToSharePoint
'' Exports the active sheet to PDF and copies it to a SharePoint Document
'' Library using a WebDAV/UNC path. This requires the user's machine to have
'' WebClient enabled or the library synced/mapped (OneDrive for Business).
'' If the UNC path is not accessible, the routine will show an informative
'' message and leave the PDF in the temp folder.
''
'' Assumptions/Notes:
'' - Site URL example: https://anico.sharepoint.com/sites/Life_Product/Process_Control
'' - Document library name example: IllTest
'' - The UNC form used is: \\anico.sharepoint.com@SSL\sites\Life_Product\Process_Control\IllTest\file.pdf
'' - If your environment requires modern OAuth for SharePoint Online, a more
''   advanced upload (REST API with OAuth tokens) will be required.
''------------------------------------------------------------------
'Sub printIllustrationToSharePoint()
'    Dim CalcStatus
'    CalcStatus = Application.Calculation
'
'    Application.Calculate
'    Application.Calculation = xlCalculationManual
'
'    Dim rptFileName As String, rptLocalTemp As String, rptLocalFull As String
'    rptFileName = IIf(Range("sReportFileName") <> "", Range("sReportFileName"), Range("sReportFileNameDefault"))
'
'    ' Sanitize file name for SharePoint/UNC compatibility
'    rptFileName = SanitizeFileName(rptFileName)
'
'    'Check to see if file name is valid
'    If Not IsValidFileName(rptFileName) Then
'        Call MsgBox("Filename has invalid characters.  File not saved")
'        Exit Sub
'    End If
'
'    ' Build a temporary local file path first
'    rptLocalTemp = Environ("TEMP")
'    If Right(rptLocalTemp, 1) <> "\" Then rptLocalTemp = rptLocalTemp & "\"
'    rptLocalFull = rptLocalTemp & rptFileName & ".pdf"
'
'    ' Calculate and prepare report data
'    ProduceAllLedgerValues
'
'    Dim ReportType As String
'    ReportType = Range("sReportData_ReportTemplate")
'
'    Select Case ReportType
'        Case "IUL": IULPrint
'        Case "UL": ULPrint
'        Case "SGUL": SGULPrint
'    End Select
'
'    ' Export to local temp .pdf
'    On Error GoTo Err_Export
'    ActiveSheet.ExportAsFixedFormat Type:=xlTypePDF, fileName:=rptLocalFull _
'        , Quality:=xlQualityStandard, IncludeDocProperties:=True, IgnorePrintAreas _
'        :=False, OpenAfterPublish:=False
'
'    ' Build UNC path for SharePoint site and document library
'    Dim siteUrl As String, docLib As String, rptUNC As String
'    siteUrl = "https://anico.sharepoint.com/sites/Life_Product/Process_Control"
'    docLib = "IllTest"
'    rptUNC = BuildSharePointUNC(siteUrl, docLib, rptFileName & ".pdf")
'
'    ' Quick check: confirm destination folder appears reachable before attempting FileCopy
'    Dim destFolder As String
'    destFolder = Left(rptUNC, Len(rptUNC) - Len(rptFileName & ".pdf") - 1)
'    If Dir(destFolder, vbDirectory) = "" Then
'        ' Try to detect a per-user OneDrive sync folder and copy there instead
'        Dim oneDriveFolder As String
'        oneDriveFolder = FindOneDriveFolderForDocLib(docLib)
'        If oneDriveFolder <> "" Then
'            Dim targetPath As String
'            targetPath = oneDriveFolder & "\" & rptFileName & ".pdf"
'            On Error GoTo Err_Copy
'            FileCopy rptLocalFull, targetPath
'
'            MsgBox "File saved to OneDrive sync folder: " & targetPath, vbInformation
'
'            ' Clean up local temp file
'            On Error Resume Next
'            Kill rptLocalFull
'            On Error GoTo 0
'
'            'Unhide any columns that may have been hidden to print report
'            Columns("A:CZ").Select
'            Selection.EntireColumn.Hidden = False
'
'            'Return to INPUT sheet
'            Sheets("INPUT").Select
'
'            Application.Calculation = CalcStatus
'            Exit Sub
'        End If
'
'        ' Dir may fail for some remote WebDAV locations; give actionable info to the user
'        MsgBox "Destination path not reachable via UNC: " & destFolder & vbCrLf & _
'               "This usually means the WebClient (WebDAV) is not available or the library is not accessible via UNC. " & _
'               "Try syncing the library with OneDrive or mapping it as a network location, then try again. The PDF is in: " & rptLocalFull, vbExclamation
'        Application.Calculation = CalcStatus
'        Exit Sub
'    End If
'
'    ' Attempt to copy the file to SharePoint UNC path
'    On Error GoTo Err_Copy
'    FileCopy rptLocalFull, rptUNC
'
'    MsgBox "File saved to SharePoint: " & rptUNC, vbInformation
'
'    ' Clean up local temp file
'    On Error Resume Next
'    Kill rptLocalFull
'    On Error GoTo 0
'
'    'Unhide any columns that may have been hidden to print report
'    Columns("A:CZ").Select
'    Selection.EntireColumn.Hidden = False
'
'    'Return to INPUT sheet
'    Sheets("INPUT").Select
'
'    Application.Calculation = CalcStatus
'    Exit Sub
'
'Err_Export:
'    MsgBox "Failed to export PDF to local temp folder. Error: " & Err.Number & " - " & Err.Description, vbExclamation
'    Application.Calculation = CalcStatus
'    Exit Sub
'
'Err_Copy:
'    MsgBox "Failed to copy the file to SharePoint path. Error: " & Err.Number & " - " & Err.Description & vbCrLf & vbCrLf & _
'        "If you see a UNC path failure, try syncing the library with OneDrive or mapping it as a network location. The PDF is in: " & rptLocalFull, vbExclamation
'
'    ' Leave the local temp file for user to manually upload if needed
'    Application.Calculation = CalcStatus
'    Exit Sub
'End Sub
'
'
'' Sanitize a filename for use with SharePoint/UNC (replace invalid characters and trim trailing spaces/dots)
'Function SanitizeFileName(s As String) As String
'    Dim invalidChars As Variant, ch As Variant
'    invalidChars = Array("*", "|", "\", "/", ":", """", "<", ">", "?", "#", "%", "&", "{", "}", "$", "!", "+", "`", "@", "~")
'    For Each ch In invalidChars
'        s = Replace(s, ch, "-")
'    Next
'    ' Also replace multiple consecutive spaces with single space
'    Do While InStr(s, "  ") > 0
'        s = Replace(s, "  ", " ")
'    Loop
'    ' Remove trailing spaces or dots
'    Do While Len(s) > 0 And (Right(s, 1) = " " Or Right(s, 1) = ".")
'        s = Left(s, Len(s) - 1)
'    Loop
'    If Len(s) = 0 Then s = "Report"
'    ' Limit length to avoid path length issues (leave margin for UNC prefix and folders)
'    If Len(s) > 120 Then s = Left(s, 120)
'    SanitizeFileName = s
'End Function
'
'
'' Build a UNC/WebDAV path for a SharePoint site and document library
'Function BuildSharePointUNC(siteUrl As String, docLib As String, fileName As String) As String
'    Dim s As String, host As String, rest As String, pos As Long
'
'    s = Trim(siteUrl)
'    If LCase(Left(s, 8)) = "https://" Then s = Mid(s, 9)
'    If LCase(Left(s, 7)) = "http://" Then s = Mid(s, 8)
'
'    pos = InStr(s, "/")
'    If pos > 0 Then
'        host = Left(s, pos - 1)
'        rest = Mid(s, pos + 1)
'    Else
'        host = s
'        rest = ""
'    End If
'
'    rest = Replace(rest, "/", "\")
'
'    If rest <> "" Then
'        BuildSharePointUNC = "\\" & host & "@SSL\" & rest & "\" & docLib & "\" & fileName
'    Else
'        BuildSharePointUNC = "\\" & host & "@SSL\" & docLib & "\" & fileName
'    End If
'End Function
'
'
