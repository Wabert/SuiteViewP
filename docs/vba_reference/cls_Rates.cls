' Module: cls_Rates.cls
' Type: Class Module
' Stream Path: VBA/cls_Rates
' =========================================================

Attribute VB_Name = "cls_Rates"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Private dctRates As Dictionary
Private mDataSource As String

Public Sub Class_Initialize()
    Set dctRates = New Dictionary
    
End Sub
Property Get Rates(RateType, Plancode, Optional IssueAge, Optional Sex, Optional Rateclass, Optional Ratescale = 1, Optional intBand, Optional SpecifiedAmount = 0, Optional BenefitType = "") As Variant
    Dim RtKey As String
    If Not IsMissing(Plancode) Then Plancode = Application.WorksheetFunction.Trim(Plancode)
    If Not IsMissing(IssueAge) Then IssueAge = CInt(IssueAge)
    If Not IsMissing(intBand) Then intBand = CInt(intBand)
    If Not IsMissing(Rateclass) Then
        If Rateclass = "0" Then Rateclass = "N"
    End If
    
    RtKey = GetRateKey(RateType, Plancode, IssueAge, Sex, Rateclass, intBand, Ratescale, BenefitType)

    If Not (dctRates.exists(RtKey)) Then
        Load_Rates_From_Database_Into_Dictionary RtKey, RateType, Plancode, IssueAge, Sex, Rateclass, intBand, Ratescale, SpecifiedAmount, BenefitType
    End If
    Rates = dctRates(RtKey)
End Property
Private Sub Load_Rates_From_Database_Into_Dictionary(RtKey, RateType, Plancode, IssueAge, Sex, Rateclass, Band, Ratescale, Optional SpecifiedAmount = 0, Optional Benefit)
    Dim sqlstring As String
    sqlstring = CreateServerSQLString(RateType, Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Benefit)
    ary = FetchTable(sqlstring, "UL_Rates", False)
    If Not IsEmpty(ary) Then
        Select Case RateType
            Case "BANDSPECS":  dctRates(RtKey) = Transpose2DArray_to_2DArray(ary)
            Case "COI_SCALE":  dctRates(RtKey) = ary
            Case "RATESPACE":  dctRates(RtKey) = Transpose2DArray_to_2DArray(ary)
            Case Else:         dctRates(RtKey) = Array2to1(Transpose2DArray_to_2DArray(ary))
        End Select
    Else
        dctRates(RtKey) = Empty
    End If
End Sub
Private Function Array2to1(ary) As Variant
    'FetchTable always returns a 2D array, but most rates are easier to handle in a 1D array.
    Dim temparray
    If IsEmpty(ary) Then
        temparray = Empty
    Else

        ReDim temparray(LBound(ary, 2) + 1 To UBound(ary, 2) + 1)
        For X = LBound(ary, 2) To UBound(ary, 2)
            temparray(X + 1) = ary(0, X)  'tempArray index is changed to Duration by the "+ 1"
        Next
    End If
    Array2to1 = temparray
End Function
Private Function FindBand(BANDSPECS As Variant, SpecifiedAmount) As Variant
    If IsEmpty(BANDSPECS) Then
        FindBand = Empty
    Else
        BandCount = UBound(BANDSPECS, 2)
        Do While SpecifiedAmount < BANDSPECS(0, BandCount)
            BandCount = BandCount - 1
        Loop
        FindBand = BANDSPECS(1, BandCount)
    End If
End Function

Private Function GetRateKey(RateType, Plancode, Optional IssueAge, Optional Sex, Optional Rateclass, Optional Band, Optional Ratescale, Optional BenefitType)
Dim RateKey As String
 Select Case RateType
    Case "EPP":         GetRateKey = Join(Array(RateType, Plancode, Sex, Rateclass, Band, Ratescale), "_")
    Case "TPP":         GetRateKey = Join(Array(RateType, Plancode, Sex, Rateclass, Band, Ratescale), "_")
    Case "FLATP":       GetRateKey = Join(Array(RateType, Plancode, Sex, Rateclass, Band, Ratescale), "_") ' Server Database Only
    Case "MFEE":        GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, Rateclass, Band, Ratescale), "_")
    Case "DBD":         GetRateKey = Join(Array(RateType, Plancode), "_")
    Case "GINT":        GetRateKey = Join(Array(RateType, Plancode), "_")
    Case "CORR":        GetRateKey = Join(Array(RateType, Plancode, IssueAge), "_")
    Case "BONUSAV":     GetRateKey = Join(Array(RateType, Plancode, Ratescale), "_")
    Case "BONUSDUR":    GetRateKey = Join(Array(RateType, Plancode, Ratescale), "_")
    Case "MTP":         GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, Rateclass, Band), "_")
    Case "CTP":         GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, Rateclass, Band), "_")
    Case "TBL1PREM":    GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, Rateclass, Band), "_") ' Access Database Only
    Case "TBL1CTP":     GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, Rateclass, Band), "_") ' Server Database Only
    Case "TBL1MTP":     GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, Rateclass, Band), "_") ' Server Database Only
    Case "EPU":         GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, Rateclass, Band, Ratescale), "_")
    Case "COI":         GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, Rateclass, Band, Ratescale), "_")
    Case "SCR":         GetRateKey = Join(Array(RateType, Plancode, IssueAge, Sex, Rateclass, Band), "_")
    Case "CEASEAGE":    GetRateKey = Join(Array(RateType, Plancode), "_")
    Case "BENMTP":      GetRateKey = Join(Array(RateType, Plancode, IssueAge, Band, BenefitType), "_")
    Case "BENCTP":      GetRateKey = Join(Array(RateType, Plancode, IssueAge, Band, BenefitType), "_")
    Case "BENCOI":      GetRateKey = Join(Array(RateType, Plancode, IssueAge, Band, BenefitType), "_")
    Case "BANDSPECS":   GetRateKey = Join(Array(RateType, Plancode), "_")
    Case "PLNCRD":      GetRateKey = Join(Array(RateType, Plancode), "_")
    Case "PLNCRG":      GetRateKey = Join(Array(RateType, Plancode), "_")
    Case "RLNCRD":      GetRateKey = Join(Array(RateType, Plancode), "_")
    Case "RLNCRG":      GetRateKey = Join(Array(RateType, Plancode), "_")
    Case "SNETPERIOD":  GetRateKey = Join(Array(RateType, Plancode, IssueAge), "_")
    Case "RATESPACE":   GetRateKey = Join(Array(RateType, Plancode), "_")
    Case "COI_SCALE":   GetRateKey = Join(Array(RateType, Plancode), "_")
 End Select
End Function

Private Function CreateServerSQLString(RateType, Plancode, Optional IssueAge, Optional Sex, Optional Rateclass, Optional rtscale, Optional Band, Optional BenefitType) As String
Select Case RateType
    Case "EPP":         CreateServerSQLString = "SELECT Rate FROM Select_RATE_EPP WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND Scale=" & rtscale & " AND [Band]=" & Band
    Case "TPP":         CreateServerSQLString = "SELECT Rate FROM Select_RATE_TPP WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND Scale=" & rtscale & " AND [Band]=" & Band
    Case "FLATP":       CreateServerSQLString = "SELECT Rate FROM Select_RATE_FLATPREM WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND Scale=" & rtscale & " AND [Band]=" & Band
    Case "MFEE":        CreateServerSQLString = "SELECT Rate FROM Select_RATE_MFEE WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND Scale=" & rtscale & " AND [Band]=" & Band
    Case "DBD":         CreateServerSQLString = "SELECT Rate FROM Select_RATE_DBD WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
    Case "GINT":        CreateServerSQLString = "SELECT Rate FROM Select_RATE_GINT WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
    Case "CORR":        CreateServerSQLString = "SELECT Rate FROM Select_RATE_CORR WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND AttainedAge>=" & IssueAge
    Case "BONUSAV":     CreateServerSQLString = "SELECT Rate FROM Select_RATE_BONUSAV WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND Scale=" & rtscale
    Case "BONUSDUR":    CreateServerSQLString = "SELECT Rate FROM Select_RATE_BONUSDUR WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND Scale=" & rtscale
    Case "MTP":         CreateServerSQLString = "SELECT Rate FROM Select_RATE_MTP WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND [Band]=" & Band
    Case "CTP":         CreateServerSQLString = "SELECT Rate FROM Select_RATE_CTP WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND [Band]=" & Band
    Case "TBL1CTP":     CreateServerSQLString = "SELECT Rate FROM Select_RATE_TBL1CTP WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND [Band]=" & Band
    Case "TBL1MTP":     CreateServerSQLString = "SELECT Rate FROM Select_RATE_TBL1MTP WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND [Band]=" & Band
    Case "EPU":         CreateServerSQLString = "SELECT Rate FROM Select_RATE_EPU WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND Scale=" & rtscale & " AND [Band]=" & Band
    Case "COI":         CreateServerSQLString = "SELECT Rate FROM Select_RATE_COI WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND Scale=" & rtscale & " AND [Band]=" & Band
    Case "SCR":         CreateServerSQLString = "SELECT Rate FROM Select_RATE_SCR WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND [Band]=" & Band
    'Case "CEASEAGE":   CreateServerSQLString = "SELECT Rate FROM Select_RATE_CEASEAGE WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
    Case "BENMTP":     CreateServerSQLString = "SELECT Rate FROM Select_RATE_BENMTP WHERE Plancode='" & Plancode & "' AND BenefitType='" & BenefitType & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND [Band]=" & Band
    Case "BENCTP":     CreateServerSQLString = "SELECT Rate FROM Select_RATE_BENCTP WHERE Plancode='" & Plancode & "' AND BenefitType='" & BenefitType & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND [Band]=" & Band
    Case "BENCOI":     CreateServerSQLString = "SELECT Rate FROM Select_RATE_BENCOI WHERE Plancode='" & Plancode & "' AND BenefitType='" & BenefitType & "' AND IssueVersion=1 AND IssueAge=" & IssueAge & " AND Sex='" & Sex & "' AND Rateclass='" & Rateclass & "' AND [Band]=" & Band & " AND Scale=" & rtscale
    Case "BANDSPECS":   CreateServerSQLString = "SELECT SpecifiedAmount, [Band] FROM Select_RATE_BANDSPECS WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
    Case "PLNCRD":      CreateServerSQLString = "SELECT Rate FROM Select_RATE_PLNCRD WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
    Case "PLNCRG":      CreateServerSQLString = "SELECT Rate FROM Select_RATE_PLNCRG WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
    Case "RLNCRD":      CreateServerSQLString = "SELECT Rate FROM Select_RATE_RLNCRD WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
    Case "RLNCRG":      CreateServerSQLString = "SELECT Rate FROM Select_RATE_RLNCRG WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
    Case "SNETPERIOD":  CreateServerSQLString = "SELECT Rate FROM Select_RATE_SNETPERIOD WHERE Plancode='" & Plancode & "' AND IssueVersion=1 AND IssueAge=" & IssueAge
    Case "RATESPACE":   CreateServerSQLString = "SELECT POINT_PVSRB.[Sex], POINT_PVSRB.[Rateclass], POINT_PVSRB.[Band] FROM POINT_PVSRB WHERE [Plancode]='" & Plancode & "' AND [IssueVersion]=1"
    Case "COI_SCALE":   CreateServerSQLString = "SELECT Date, Scale FROM Select_SCALE_COI WHERE Plancode='" & Plancode & "' AND IssueVersion=1"
    Case Else:          CreateServerSQLString = ""
End Select

End Function





'===================================================================================================================================================================
'Below are the specific RateTypes which mploy the code above
'===================================================================================================================================================================

Property Get MTP(Plancode, IssueAge, Sex, Rateclass, Band) As Variant
 MTP = Rates("MTP", Plancode, IssueAge, Sex, Rateclass, , Band)(1)
End Property

Property Get CTP(Plancode, IssueAge, Sex, Rateclass, Band) As Variant
 CTP = Rates("CTP", Plancode, IssueAge, Sex, Rateclass, , Band)(1)
End Property

Property Get TBL1PREM(Plancode, IssueAge, Sex, Rateclass, Band) As Variant 'Access Server Only
 TBL1PREM = Rates("TBL1PREM", Plancode, IssueAge, Sex, Rateclass, , Band)(1)
End Property

Property Get TBL1MTP(Plancode, IssueAge, Sex, Rateclass, Band) As Variant 'SQL Server Only
 TBL1MTP = Rates("TBL1MTP", Plancode, IssueAge, Sex, Rateclass, , Band)(1)
End Property

Property Get TBL1CTP(Plancode, IssueAge, Sex, Rateclass, Band) As Variant 'SQL Server Only
 TBL1CTP = Rates("TBL1CTP", Plancode, IssueAge, Sex, Rateclass, , Band)(1)
End Property

Property Get COI(Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Duration) As Variant
 COI = Rates("COI", Plancode, IssueAge, Sex, Rateclass, Ratescale, Band)(Duration)
End Property

Property Get MFEE(Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Duration) As Variant
 MFEE = Rates("MFEE", Plancode, IssueAge, Sex, Rateclass, Ratescale, Band)(Duration)
End Property

Property Get EPU(Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Duration) As Variant
 EPU = Rates("EPU", Plancode, IssueAge, Sex, Rateclass, Ratescale, Band)(Duration)
End Property

Property Get CORR(Plancode, IssueAge, Duration) As Variant
 CORR = Rates("CORR", Plancode, IssueAge)(Duration)
End Property

Property Get TPP(Plancode, Sex, Rateclass, Ratescale, Band, Duration) As Variant
 TPP = Rates("TPP", Plancode, , Sex, Rateclass, Ratescale, Band)(Duration)
End Property

Property Get EPP(Plancode, Sex, Rateclass, Ratescale, Band, Duration) As Variant
 EPP = Rates("EPP", Plancode, , Sex, Rateclass, Ratescale, Band)(Duration)
End Property

Property Get FLATP(Plancode, Sex, Rateclass, Ratescale, Band, Duration) As Variant 'SQL Server Only
 FLATP = Rates("FLATP", Plancode, , Sex, Rateclass, Ratescale, Band)(Duration)
End Property

Property Get SCR(Plancode, IssueAge, Sex, Rateclass, Band, Duration) As Variant
 SCR = Rates("SCR", Plancode, IssueAge, Sex, Rateclass, , Band)(Duration)
End Property

Property Get SNETPERIOD(Plancode, IssueAge) As Variant
 SNETPERIOD = Rates("SNETPERIOD", Plancode, IssueAge)
End Property
Property Get DBD(Plancode, Duration) As Variant
 DBD = Rates("DBD", Plancode)(Duration)
End Property

Property Get GINT(Plancode, Duration) As Variant
 GINT = Rates("GINT", Plancode)(Duration)
End Property

Property Get BENCOI(Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Duration, BenefitType)
 BENCOI = Rates("BENCOI", Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, , BenefitType)(Duration)
End Property

Property Get BENMTP(Plancode, IssueAge, Sex, Rateclass, Band, BenefitType)
 BENMTP = Rates("BENMTP", Plancode, IssueAge, Sex, Rateclass, , Band, , BenefitType)(1)
End Property

Property Get BENCTP(Plancode, IssueAge, Sex, Rateclass, Band, BenefitType)
 BENCTP = Rates("BENCTP", Plancode, IssueAge, Sex, Rateclass, , Band, , BenefitType)(1)
End Property

Property Get BONUSAV(Plancode, Ratescale, Duration)
 BONUSAV = Rates("BONUSAV", Plancode, , , , Ratescale)(Duration)
End Property

Property Get BONUSDUR(Plancode, Ratescale, Duration)
 BONUSDUR = Rates("BONUSDUR", Plancode, , , , Ratescale)(Duration)
End Property

Property Get BANDSPECS(Plancode, Amount, Optional Benefit = "")
If Benefit = "" Then
 BANDSPECS = Rates("BANDSPECS", Plancode, , , , , , , Amount)
Else
 BANDSPECS = 0
End If
End Property

Property Get Band(Plancode As String, Amount As Double, Optional Benefit)
Plancode = Application.WorksheetFunction.Trim(Plancode)
 If IsMissing(Benefit) Then
  Band = FindBand(BANDSPECS(Plancode, Amount), Amount)
 Else
  Band = 0
 End If
End Property

Property Get COI_SCALE(Plancode, Ratescale)
 COI_SCALE = Rates("COI_SCALE", Plancode, , , , Ratescale)
End Property

Property Get RATESPACE(Plancode) As Variant
  RATESPACE = Rates("RATESPACE", Plancode)
End Property

