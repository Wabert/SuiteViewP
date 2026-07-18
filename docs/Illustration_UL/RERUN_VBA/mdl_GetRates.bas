Attribute VB_Name = "mdl_GetRates"
Private Cmd As ADODB.Command
Private cn As ADODB.Connection

'These dictionaries will identify plancodes that need each ratetype
Dim dctTargets As Dictionary
Dim dctPremLoad As Dictionary
Dim dctCCOI As Dictionary
Dim dctGCOI As Dictionary
Dim dctSCR As Dictionary
Dim dctEPU As Dictionary
Dim dctMFEE As Dictionary
Dim dctSNET As Dictionary
Dim dctSHDINT As Dictionary

Public Sub MainGetRates()
'This procedure finds all rider plancodes and the base plancode on this policy and
'gets the rates for each from the UL_Rates database and pastes them into this workbook
'All rates are retrieved for each plancode, meaning all sex, rateclass, band, issueage and duration
'However, as of now only the guaranteed and most current scale are retrieved

'All the Benefit rates are already stored in the worksheet so no database query is needed for them

ThisWorkbook.Activate
Application.Calculate

Dim CalcStatus
CalcStatus = Application.Calculation
Application.Calculation = xlCalculationManual

EstablishSQLConnection Range("sSQLDataBase"), Range("sSQLServer")

Dim tblname As String, RateType As String
Dim PlancodeCriteria As String
Dim dctTables As Dictionary
Set dctTables = New Dictionary

Dim StateCode As String
StateCode = Range("sQueryWithStateCode")

'Get base and rider plancodes
Dim dctPlancodes As Dictionary 'Keeps track of all the plancodes needed for the policy
Dim dctQueryList As Dictionary 'Will be used to build the SQL string to query rates

Set dctPlancodes = New Dictionary
Set dctQueryList = New Dictionary

Dim BasePlancode As String
Range("sPlancode").Worksheet.Select

Set dctTargets = New Dictionary
Set dctPremLoad = New Dictionary
Set dctCCOI = New Dictionary
Set dctGCOI = New Dictionary
Set dctSCR = New Dictionary
Set dctEPU = New Dictionary
Set dctMFEE = New Dictionary
Set dctSNET = New Dictionary
Set dctSHDINT = New Dictionary

Dim Plancode As String

'BASE RATES NEEDED
Plancode = Range("sPlancode")
dctPlancodes(Plancode) = Plancode
AddBaseRateTypes Plancode


'RIDER RATES NEEDED
If Range("sINPUT_R1_Boolean") Then
    Plancode = Range("sINPUT_R1_Plancode")
    dctPlancodes(Plancode) = Plancode
    AddTermRiderRateTypes Plancode
End If

If Range("sINPUT_R2_Boolean") Then
    Plancode = Range("sINPUT_R2_Plancode")
    dctPlancodes(Plancode) = Plancode
    AddTermRiderRateTypes Plancode
End If

If Range("sINPUT_R3_Boolean") Then
    Plancode = Range("sINPUT_R3_Plancode")
    dctPlancodes(Plancode) = Plancode
    AddTermRiderRateTypes Plancode
End If

If Range("sINPUT_APB_Boolean") Then
    Plancode = Range("sINPUT_APB_Plancode")
    dctPlancodes(Plancode) = Plancode
    AddAPBRiderRateTypes Plancode
End If

'ADDITONAL PLANCODES
'Add additional plancodes that are manually specified
'Checkt to see if plancode is a rider plancode or base plancode and add corresponding ratetypes
Dim RiderType As String
Dim CanIllustrate As Variant
For x = 1 To Range("vPlancodesAddedManually").count
    Plancode = Range("vPlancodesAddedManually")(x).Value
    If Plancode <> "0" And Plancode <> "" Then
        If Not dctPlancodes.Exists(Plancode) Then
            dctPlancodes(Plancode) = Plancode
            RiderType = GetRiderData(Plancode, "CovType")
            'A value of "" means the plancode was not found in the RiderDefinitionFile table
            If RiderType <> "" And RiderType <> "0" Then
                Select Case RiderType
                    Case "STR", "LTR", "SIGTERM": AddTermRiderRateTypes Plancode
                    Case "APB": AddAPBRiderRateTypes Plancode
                End Select
            Else
                'If plancode is not a rider, check to see if its a base plancode
                'A value of "" means the plancode was not found in the BasePlancodeTable table
                CanIllustrate = GetPlancodeData(Plancode, "CanIllustrate")
                If CanIllustrate <> "" Then
                    AddBaseRateTypes Plancode
                End If
            End If
        End If
    End If
Next
        

'See if rates need already exist in the workbook
Dim plcd As Variant
Dim blnGetRates As Boolean
blnGetRates = False

'Only get rates if needed
'For Each plcd In dctTargets.Items
'    If Not (IsPlancodePresent((plcd))) Then blnGetRates = True
'Next

'Always get rates.  It can be confusing otherwise
blnGetRates = True
    
    
If blnGetRates Then
    'Query all rates identified above
    If dctTargets.count > 0 Then LoadRatesIntoWorkbook "Span_Targets", "Targets", Join(dctTargets.Keys, " or "), StateCode
    If dctPremLoad.count > 0 Then LoadRatesIntoWorkbook "Span_PremiumLoad", "PremiumLoad", Join(dctPremLoad.Keys, " or "), StateCode
    If dctCCOI.count > 0 Then LoadRatesIntoWorkbook "Span_Select_CCOI", "Select_CCOI", Join(dctCCOI.Keys, " or "), StateCode
    If dctGCOI.count > 0 Then LoadRatesIntoWorkbook "Span_Ultimate_GCOI", "Ultimate_GCOI", Join(dctGCOI.Keys, " or "), StateCode
    If dctSCR.count > 0 Then LoadRatesIntoWorkbook "Span_SCR", "SCR", Join(dctSCR.Keys, " or "), StateCode
    If dctEPU.count > 0 Then LoadRatesIntoWorkbook "Span_EPU", "EPU", Join(dctEPU.Keys, " or "), StateCode
    If dctMFEE.count > 0 Then LoadRatesIntoWorkbook "Span_MFEE", "MFEE", Join(dctMFEE.Keys, " or "), StateCode
    If dctSNET.count > 0 Then LoadRatesIntoWorkbook "Span_SNET", "SNETPERIOD", Join(dctSNET.Keys, " or "), StateCode
    If dctSHDINT.count > 0 Then LoadRatesIntoWorkbook "Span_ShadowInt", "Select_ShadowINT", Join(dctSHDINT.Keys, " or "), StateCode
 
    'Clear the list of present plancodes and then print them out for this recent rate down load.
    'This just serves to indicate which plancodes are associated with the current rate set
    Dim vKey
    x = 0
    Range("vPlancodesPresent").ClearContents
    For Each vKey In dctTargets
        x = x + 1
        Range("vPlancodesPresent").Rows(x) = dctTargets(vKey)
    Next
End If

'Return to INPUT sheet
Worksheets("INPUT").Select

'If product is IUL, copy over the illustrated rates
Dim ProdType As String
ProdType = GetPlancodeData(Range("sPlancode"), "ReportTemplate")
If ProdType = "IUL" Then
    Range("vINPUT_Available_Rates").Select
    Selection.Copy
    Range("vINPUT_Illustrated_Rates").Rows(1).Select
            Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
            :=False, Transpose:=False
End If

'If product is IUL, copy over the variable loan rate [RJH - 12/1/2022]
If ProdType = "IUL" Then
    Range("sINPUT_Variable_Loan_Rate").Value = Range("sVariableLoanRateLookup").Value
End If

'Reset Calculation status back to starting calculation status
Application.Calculation = CalcStatus

End Sub

Private Sub AddBaseRateTypes(strPlancode As String)
Dim ratemode As String
Dim ShadowPlancode As String

    dctTargets("Plancode='" & strPlancode & "'") = strPlancode
    dctCCOI("Plancode='" & strPlancode & "'") = strPlancode
    dctGCOI("Plancode='" & strPlancode & "'") = strPlancode
    dctSCR("Plancode='" & strPlancode & "'") = strPlancode
    
    AddRateTypeIfNeeded dctPremLoad, strPlancode, "PremiumLoad", strPlancode
    AddRateTypeIfNeeded dctMFEE, strPlancode, "MFEE", strPlancode
    AddRateTypeIfNeeded dctSNET, strPlancode, "SNET", strPlancode
    AddRateTypeIfNeeded dctEPU, strPlancode, "EPU_Code", strPlancode
    
    
    'SHADOW ACCOUNT RATES NEEDED
    'See if the base plancode has an associated shadow account plancode and get gets rates if needed
    ShadowPlancode = CStr(GetPlancodeData(strPlancode, "ShadowPlancode"))
    If ShadowPlancode <> "NA" And ShadowPlancode <> "0" And ShadowPlancode <> "" Then
        dctCCOI("Plancode='" & ShadowPlancode & "'") = ShadowPlancode
        
        AddRateTypeIfNeeded dctTargets, strPlancode, "ShadowTarget", ShadowPlancode
        AddRateTypeIfNeeded dctPremLoad, strPlancode, "ShadowPremLoad", ShadowPlancode
        AddRateTypeIfNeeded dctEPU, strPlancode, "ShadowEPU", ShadowPlancode
        AddRateTypeIfNeeded dctSHDINT, strPlancode, "ShadowInt", ShadowPlancode
        
    End If
    

End Sub
Private Sub AddRateTypeIfNeeded(dctRates As Dictionary, lookupPlancode As String, RateType As String, ratePlancode As String)
        'This procedure looks up the RateType in the BasePlancodeTable in the workbook.  If the value is "TABLE" it indicates the rates should be queried from the database
        'Tehrefore the plancode will be added to the dictionary which will be queried later
        '
        ratemode = GetPlancodeData(lookupPlancode, RateType)
        If UCase(ratemode) = "TABLE" Then dctRates("Plancode='" & ratePlancode & "'") = ratePlancode
End Sub


Private Sub AddTermRiderRateTypes(strPlancode As String)
'Child Term Riders are not considered term riders when getting rates.  The CTR rate structure is very simple and does not need to be queried from the database
'The Addition Protection Benefit (APB) rider has additoinal rates so querying rates for that rider is handled in a differnt procedure
    dctTargets("Plancode='" & strPlancode & "'") = strPlancode
    dctCCOI("Plancode='" & strPlancode & "'") = strPlancode
    dctGCOI("Plancode='" & strPlancode & "'") = strPlancode
End Sub
Private Sub AddAPBRiderRateTypes(strPlancode As String)
    dctTargets("Plancode='" & strPlancode & "'") = strPlancode
    dctEPU("Plancode='" & strPlancode & "'") = strPlancode
    dctCCOI("Plancode='" & strPlancode & "'") = strPlancode
    dctGCOI("Plancode='" & strPlancode & "'") = strPlancode
End Sub


Private Sub LoadRatesIntoWorkbook(tblname As String, RateType As String, Plancodes As String, StateCode As String)
Dim key

    'Clear the range contents of the named range identified by tblname
    Range(tblname).Worksheet.Select
    If Range(tblname)(1, 1).Offset(1, 0) = "" Then
        Range(tblname).Resize(1, 10).ClearContents
    Else
        Range(tblname).Select
        Selection.End(xlDown).Select
        Range(tblname).Resize(Selection.row, Range(tblname).Columns.count).ClearContents
    End If
    
    'Query the rates from UL_Rates database and paste them into the range identified by tblname
    SQLString = CreateServerSQLString(RateType, Plancodes, StateCode)
    Debug.Print SQLString
    Dim ary(), aryPrint()
    Dim Rowlength As Double, ColumnLength As Double
    ary = RunSQLQuery(SQLString)
    If Not IsEmpty(ary) Then
        aryPrint = Traspose2DArray(ary)
        Rowlength = UBound(aryPrint, 1)
        ColumnLength = UBound(aryPrint, 2)
    
        Range(tblname).Resize(Rowlength + 1, ColumnLength + 1).Value = aryPrint
    End If
End Sub

Private Function CreateServerSQLString(RateType, Plancode, StateCode) As String
 Select Case RateType
    
    Case "Ultimate_CCOI":   CreateServerSQLString = "SELECT  REPLACE([Plancode],' ',''), [Sex], [Rateclass], [Band], [IssueAge]+[Duration]-1 , CONCAT(REPLACE([Plancode],' ',''),[Sex], [Rateclass],[Band],RIGHT(CONCAT('000', [IssueAge]+[Duration]-1), 3)) AS [Key], max(Rate) FROM Select_RATE_COI WHERE (" & Plancode & ") AND IssueVersion=1 AND Scale = 1 AND [Duration] > 40 GROUP BY [Plancode], [Sex], [Rateclass], [Band], [IssueAge]+[Duration]-1 ORDER BY [Key]"
    
    
    Case "Ultimate_GCOI":   CreateServerSQLString = "SELECT  REPLACE([Plancode],' ',''), [Sex], [Rateclass], [IssueAge]+[Duration]-1 As [AttainedAge], CONCAT(REPLACE([Plancode],' ',''),[Sex], [Rateclass],RIGHT(CONCAT('000', [IssueAge]+[Duration]-1), 3)) AS [Key], Max([Rate]) FROM Select_RATE_COI WHERE (" & Plancode & ") AND IssueVersion=1 AND Scale = 0 AND [Duration] > 0 GROUP BY [Plancode], [Sex], [Rateclass], [IssueAge]+[Duration]-1 ORDER BY [Key]"
    Case "MFEE":            CreateServerSQLString = "SELECT  REPLACE([Plancode],' ',''), [Scale], [Band], [IssueAge], [Duration], CONCAT(REPLACE([Plancode],' ',''),[Scale],[Band],RIGHT(CONCAT('000', [IssueAge]), 3), RIGHT(CONCAT('000', [Duration]), 3)) AS [Key], [Rate] FROM Select_RATE_MFEE GROUP BY Plancode, IssueVersion, Scale, [Band], IssueAge, Duration, Rate Having ((" & Plancode & ") AND IssueVersion=1 AND (Scale = 0 OR Scale = 1) AND [Duration] <= 11) ORDER BY [Key]"
    Case "Targets":         CreateServerSQLString = "SELECT  REPLACE([Plancode],' ',''), [Sex], [Rateclass], [Band], [IssueAge], CONCAT(REPLACE([Plancode],' ',''),[Sex], [Rateclass],[Band], RIGHT(CONCAT('000', [IssueAge]), 3)) AS [Key], [Rate(MTP)], [Rate(TBL1MTP)], [Rate(CTP)], [Rate(TBL1CTP)] FROM Select_RATE_TRGPREM GROUP BY Plancode, IssueVersion, Sex, Rateclass, [Band], IssueAge, [Rate(MTP)], [Rate(TBL1MTP)], [Rate(CTP)], [Rate(TBL1CTP)] Having ((" & Plancode & ") AND IssueVersion=1) ORDER BY [Key]"
    Case "PremiumLoad":     CreateServerSQLString = "SELECT  REPLACE([Plancode],' ',''), [Scale], [Band], [Duration], CONCAT(REPLACE([Plancode],' ',''),[Scale],[Band], RIGHT(CONCAT('000', [Duration]), 3)) AS [Key], [Rate(TPP)], [Rate(EPP)] FROM Select_RATE_PREMLOAD GROUP BY Plancode, IssueVersion, Scale, [Band], Duration, [Rate(TPP)], [Rate(EPP)] Having ((" & Plancode
                            CreateServerSQLString = CreateServerSQLString & ") AND IssueVersion=1 AND (Scale = 0 OR Scale = 1) AND [Duration] <= 11) ORDER BY [Key]"
    Case "SNETPERIOD":      CreateServerSQLString = "SELECT  REPLACE([Plancode],' ',''), [IssueAge], CONCAT(REPLACE([Plancode],' ',''), RIGHT(CONCAT('000', [IssueAge]), 3)) AS [Key], Rate FROM Select_RATE_SNETPERIOD GROUP BY Plancode, IssueAge, Rate HAVING (" & Plancode & ") ORDER BY [Key]"
    Case "EPU":             CreateServerSQLString = "SELECT REPLACE([Plancode],' ',''), [Scale], [Sex], [Rateclass], [Band], [IssueAge], CONCAT(REPLACE([Plancode],' ',''),[Scale],[Sex],[Rateclass],[Band],RIGHT(CONCAT('000', [IssueAge]), 3)) AS [Key] "
                            For x = 1 To 21
                                CreateServerSQLString = CreateServerSQLString & ", max(CASE WHEN [Duration] = " & x & " THEN [Rate] END) as Dur" & x & " "
                            Next
                            CreateServerSQLString = CreateServerSQLString & " FROM Select_RATE_EPU GROUP BY Plancode, IssueVersion, Scale, [Sex], [Rateclass], [Band], [IssueAge] Having ((" & Plancode & ") AND IssueVersion=1 AND (Scale = 0 OR Scale = 1)) ORDER BY [Key]"
    
    
    Case "Select_CCOI":     CreateServerSQLString = "SELECT REPLACE([Plancode],' ',''), [Sex], [Rateclass], [Band], [IssueAge], CONCAT(REPLACE([Plancode],' ',''),[Sex],[Rateclass],[Band],RIGHT(CONCAT('000', [IssueAge]), 3)) AS [Key] "
                            For x = 1 To 121
                                CreateServerSQLString = CreateServerSQLString & ", max(CASE WHEN [Duration] = " & x & " THEN [Rate] END) as Dur" & x & " "
                            Next
                            CreateServerSQLString = CreateServerSQLString & " FROM Select_RATE_COI GROUP BY Plancode, IssueVersion, Scale, [Sex], [Rateclass], [Band], [IssueAge] Having ((" & Plancode & ") AND IssueVersion=1 AND Scale = 1) ORDER BY [Key]"
    
    
    Case "SCR":         CreateServerSQLString = "SELECT REPLACE([Plancode],' ',''), [Sex], [Rateclass], [IssueAge], CONCAT(REPLACE([Plancode],' ',''),[Sex],[Rateclass],RIGHT(CONCAT('000', [IssueAge]), 3)) AS [Key] "
                        For x = 1 To 20
                            CreateServerSQLString = CreateServerSQLString & ", max(CASE WHEN [Duration] = " & x & " THEN [Rate] END) as Dur" & x & " "
                        Next
                        CreateServerSQLString = CreateServerSQLString & " FROM Select_RATE_SCR GROUP BY Plancode, IssueVersion, [Sex], [Rateclass], [State], [IssueAge] Having ((" & Plancode & ") AND IssueVersion=1 AND State = '" & StateCode & "') ORDER BY [Key]"
    
    
    Case "Select_ShadowCOI":    CreateServerSQLString = "SELECT REPLACE([Plancode],' ',''), [Sex], [Rateclass], [Band], [IssueAge], CONCAT(REPLACE([Plancode],' ',''),[Sex],[Rateclass],[Band],RIGHT(CONCAT('000', [IssueAge]), 3)) AS [Key] "
                                For x = 1 To 103
                                    CreateServerSQLString = CreateServerSQLString & ", max(CASE WHEN [Duration] = " & x & " THEN [Rate] END) as Dur" & x & " "
                                Next
                                CreateServerSQLString = CreateServerSQLString & " FROM Select_RATE_COI GROUP BY Plancode, IssueVersion, Scale, [Sex], [Rateclass], [Band], [IssueAge] Having ((" & Plancode & ") AND IssueVersion=1 AND Scale = 0 AND State = " & StateCode & " ) ORDER BY [Key]"
    
    Case "Select_ShadowINT":    CreateServerSQLString = "SELECT REPLACE([Plancode],' ',''), [Sex], [Rateclass], [Band], [IssueAge], CONCAT(REPLACE([Plancode],' ',''),[Sex],[Rateclass],[Band],RIGHT(CONCAT('000', [IssueAge]), 3)) AS [Key] "
                                For x = 1 To 103
                                    CreateServerSQLString = CreateServerSQLString & ", max(CASE WHEN [Duration] = " & x & " THEN [Rate] END) as Dur" & x & " "
                                Next
                                CreateServerSQLString = CreateServerSQLString & " FROM Select_RATE_SHDINT GROUP BY Plancode, IssueVersion, Scale, [Sex], [Rateclass], [Band], [IssueAge] Having ((" & Plancode & ") AND IssueVersion=1 AND Scale = 0) ORDER BY [Key]"
    
    
    Case Else:          CreateServerSQLString = ""
 End Select

End Function

Public Sub EstablishSQLConnection(DataBaseReference, ServerReference)
    'Open a connection to SQL Server
    Set cn = New ADODB.Connection
    cn.Open _
        "Provider=SQLOLEDB; " + _
        "Data Source=" + ServerReference + "; " + _
        "Initial Catalog=" + DataBaseReference + "; " + _
        "Integrated Security = SSPI;"
    cn.CommandTimeout = 0
    
End Sub

Public Function RunSQLQuery(QueryStatements) As Variant
    'Open Recordset
    Set DataSet = New ADODB.Recordset
    Debug.Print QueryStatements
    DataSet.Open QueryStatements, cn
    
    RunSQLQuery = DataSet.GetRows(DataSet.RecordCount)
    DataSet.Close
End Function
'Private Function CreateAccessSQLString(RateType, Plancode, Optional IssueAge, Optional Sex, Optional RateClass, Optional rtscale, Optional band, Optional Benefit) As String
' Select Case RateType
'    Case "EPP":        CreateAccessSQLString = "SELECT Rate FROM Select_RATE_EPP WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "' AND Scale=" & rtscale & " AND [Band]=" & band
'    Case "TPP":        CreateAccessSQLString = "SELECT Rate FROM Select_RATE_TPP WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "' AND Scale=" & rtscale & " AND [Band]=" & band
'    Case "MFEE":       CreateAccessSQLString = "SELECT Rate FROM Select_RATE_MFEE WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "' AND Scale=" & rtscale & " AND [Band]=" & band
'    Case "DBD":        CreateAccessSQLString = "SELECT Rate FROM Select_RATE_DBD WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
'    Case "GINT":       CreateAccessSQLString = "SELECT Rate FROM Select_RATE_GINT WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
'    Case "CORR":       CreateAccessSQLString = "SELECT Rate FROM Select_RATE_CORR WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
'    Case "BONUSAV":    CreateAccessSQLString = "SELECT Rate FROM Select_RATE_BONUSAV WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND Scale=" & rtscale
'    Case "BONUSDUR":   CreateAccessSQLString = "SELECT Rate FROM Select_RATE_BONUSDUR WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND Scale=" & rtscale
'    Case "MTP":        CreateAccessSQLString = "SELECT Rate FROM Select_RATE_MTP WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "' AND [Band]=" & band
'    Case "CTP":        CreateAccessSQLString = "SELECT Rate FROM Select_RATE_CTP WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "' AND [Band]=" & band
'    Case "TBL1PREM":   CreateAccessSQLString = "SELECT Rate FROM Select_RATE_TBL1PREM WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "' AND [Band]=" & band
'    Case "EPU":        CreateAccessSQLString = "SELECT Rate FROM Select_RATE_EPU WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "' AND Scale=" & rtscale & "AND [Band]=" & band
'    Case "COI":        CreateAccessSQLString = "SELECT Rate FROM Select_RATE_COI WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "' AND Scale=" & rtscale & "AND [Band]=" & band
'    Case "SCR":        CreateAccessSQLString = "SELECT Rate FROM Select_RATE_SCR WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "' AND [Band]=" & band
'    Case "CEASEAGE":   CreateAccessSQLString = "SELECT Rate FROM Select_RATE_CEASEAGE WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
'    Case "BENMTP":     CreateAccessSQLString = "SELECT Rate FROM Select_RATE_BENMTP WHERE Plancode='" & Plancode & "' AND Benefit='" & Benefit & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "'"
'    Case "BENCTP":     CreateAccessSQLString = "SELECT Rate FROM Select_RATE_BENCTP WHERE Plancode='" & Plancode & "' AND Benefit='" & Benefit & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "'"
'    Case "BENCOI":     CreateAccessSQLString = "SELECT Rate FROM Select_RATE_BENCOI WHERE Plancode='" & Plancode & "' AND Benefit='" & Benefit & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & RateClass & "' AND Scale=" & rtscale
'    Case "BANDSPECS":  CreateAccessSQLString = "SELECT SpecifiedAmount, [Band] FROM Select_RATE_BANDSPECS WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
'    Case "PLNCRD":     CreateAccessSQLString = "SELECT Rate FROM Select_RATE_PLNCRD WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
'    Case "PLNCRG":     CreateAccessSQLString = "SELECT Rate FROM Select_RATE_PLNCRG WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
'    Case "RLNCRD":     CreateAccessSQLString = "SELECT Rate FROM Select_RATE_RLNCRD WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
'    Case "RLNCRG":     CreateAccessSQLString = "SELECT Rate FROM Select_RATE_RLNCRG WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
'    Case "SNETPERIOD": CreateAccessSQLString = "SELECT Rate FROM Select_RATE_SNETPERIOD WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge
'    Case "RATESPACE":  CreateAccessSQLString = "SELECT Sex, Rateclass, [Band] FROM POINT_PVSRB WHERE [Plancode]='" & Plancode & "' AND [IssueVersion]=1"
'    Case Else:         CreateAccessSQLString = ""
' End Select
'End Function
'Private Function FindBand(BandSpecs As Variant, SpecifiedAmount) As Variant
'
' BandCount = UBound(BandSpecs, 2)
' Do While SpecifiedAmount < BandSpecs(0, BandCount)
'  BandCount = BandCount - 1
' Loop
' FindBand = BandSpecs(1, BandCount)
'
'End Function

'Public Sub EstablishAccessConnection(DataBaseReference)
''Open a connection to Access.
'  Set cn = New ADODB.Connection
'  cn.Open "Provider=Microsoft.Jet.OLEDB.4.0;Data Source=" & DataBaseReference & ";"
'  cn.CommandTimeout = 0
'
'  'Define command
'  Set Cmd = New ADODB.Command
'  Set Cmd.ActiveConnection = cn
'
'End Sub
'Public Function RunAccessQuery(QueryStatements) As Variant
'  Dim DataSet As ADODB.Recordset
'
'  'Open Recordset
'  Set DataSet = New ADODB.Recordset
'  Cmd.CommandText = QueryStatements
'  DataSet.Open Cmd, , adOpenStatic, adLockReadOnly
'
'  RunAccessQuery = DataSet.GetRows(DataSet.RecordCount)
'
'  DataSet.Close
'  Set DataSet = Nothing
'
'End Function
'Private Function Rate(RateType, Plancode, Optional IssueAge, Optional Sex, Optional RateClass, Optional Ratescale = 1, Optional band = 0, Optional Duration = 1, Optional SpecifiedAmount = 0, Optional BenefitType = "") As Variant
'Dim tempRate As Variant
'tempRate = Rates(RateType, Plancode, IssueAge, Sex, RateClass, Ratescale, band, SpecifiedAmount, Benefit)
'
'Select Case RateType
'  Case "EPP":        Rate = tempRate(Duration)
'  Case "TPP":        Rate = tempRate(Duration)
'  Case "MFEE":       Rate = tempRate(Duration)
'  Case "DBD":        Rate = tempRate(Duration)
'  Case "GINT":       Rate = tempRate(Duration)
'  Case "CORR":       Rate = tempRate(Duration)
'  Case "BONUSAV":    Rate = tempRate(Duration)
'  Case "BONUSDUR":   Rate = tempRate(Duration)
'  Case "MTP":        Rate = tempRate
'  Case "CTP":        Rate = tempRate
'  Case "TBL1PREM":   Rate = tempRate
'  Case "EPU":        Rate = tempRate(Duration)
'  Case "COI":        Rate = tempRate(Duration)
'  Case "CEASEAGE":   Rate = tempRate
'  Case "BENMTP":     Rate = tempRate
'  Case "BENCTP":     Rate = tempRate
'  Case "BENCOI":     Rate = tempRate(Duration)
'  Case "BANDSPECS":  Rate = FindBand(tempRate, SpecifiedAmount)
'  Case "PLNCRD":     Rate = tempRate
'  Case "PLNCRG":     Rate = tempRate
'  Case "RLNCRD":     Rate = tempRate
'  Case "RLNCRG":     Rate = tempRate
'  Case "SNETPERIOD": Rate = tempRate
'  Case "RATESPACE":  Rate = tempRate
'End Select
'End Function


'Private Function GetRateKey(RateType, Plancode, Optional IssueAge, Optional Sex, Optional RateClass, Optional band, Optional Ratescale, Optional BenefitType)
'Dim RateKey As String
' Select Case RateType
'    Case "EPP":         GetRateKey = Join(Array(RateType, Plancode, Sex, RateClass, band, Ratescale), "_")
'    Case "TPP":         GetRateKey = Join(Array(RateType, Plancode, Sex, RateClass, band, Ratescale), "_")
'    Case "FLATP":       GetRateKey = Join(Array(RateType, Plancode, Sex, RateClass, band, Ratescale), "_") ' Server Database Only
'    Case "MFEE":        GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band, Ratescale), "_")
'    Case "DBD":         GetRateKey = Join(Array(RateType, Plancode), "_")
'    Case "GINT":        GetRateKey = Join(Array(RateType, Plancode), "_")
'    Case "CORR":        GetRateKey = Join(Array(RateType, Plancode, IssueAge), "_")
'    Case "BONUSAV":     GetRateKey = Join(Array(RateType, Plancode, Ratescale), "_")
'    Case "BONUSDUR":    GetRateKey = Join(Array(RateType, Plancode, Ratescale), "_")
'    Case "MTP":         GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band), "_")
'    Case "CTP":         GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band), "_")
'    Case "TBL1PREM":    GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band), "_") ' Access Database Only
'    Case "TBL1CTP":     GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band), "_") ' Server Database Only
'    Case "TBL1MTP":     GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band), "_") ' Server Database Only
'    Case "EPU":         GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band, Ratescale), "_")
'    Case "COI":         GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band, Ratescale), "_")
'    Case "SCR":         GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band), "_")
'    Case "CEASEAGE":    GetRateKey = Join(Array(RateType, Plancode), "_")
'    Case "BENMTP":      GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band, BenefitType), "_")
'    Case "BENCTP":      GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band, BenefitType), "_")
'    Case "BENCOI":      GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, RateClass, band, BenefitType), "_")
'    Case "BANDSPECS":   GetRateKey = Join(Array(RateType, Plancode), "_")
'    Case "PLNCRD":      GetRateKey = Join(Array(RateType, Plancode), "_")
'    Case "PLNCRG":      GetRateKey = Join(Array(RateType, Plancode), "_")
'    Case "RLNCRD":      GetRateKey = Join(Array(RateType, Plancode), "_")
'    Case "RLNCRG":      GetRateKey = Join(Array(RateType, Plancode), "_")
'    Case "SNETPERIOD":  GetRateKey = Join(Array(RateType, Plancode, IssueAge), "_")
'    Case "RATESPACE":   GetRateKey = Join(Array(RateType, Plancode), "_")
'    Case "COI_SCALE":   GetRateKey = Join(Array(RateType, Plancode), "_")
' End Select
'End Function

Public Sub CloseAccessConnection()
 Set cn = Nothing
End Sub

Private Sub Class_Terminate()
 CloseAccessConnection
End Sub





