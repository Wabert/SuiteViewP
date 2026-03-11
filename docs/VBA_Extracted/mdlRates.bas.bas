' Module: mdlRates.bas
' Type: Standard Module
' Stream Path: VBA/mdlRates
' =========================================================

Attribute VB_Name = "mdlRates"
Dim blnInitialized As Boolean
Dim oRates As cls_Rates
Private Sub Initialize()
    Set oRates = New cls_Rates
End Sub

Private Function GetRates(RateType, Plancode, Optional IssueAge, Optional Sex, Optional Rateclass, Optional Ratescale = 1, Optional intBand, Optional SpecifiedAmount = 0, Optional BenefitType = "") As Variant
If Not blnInitialized Then Initialize
    Rates = oRates.Rates(RateType, Plancode, IssueAge, Sex, Rateclass, Ratescale, intBand, SpecifiedAmount, BenefitType)
End Function
Public Function GetRate(RateType, Optional Plancode, Optional IssueAge, Optional Sex, Optional Rateclass, Optional Ratescale, Optional Band, _
                        Optional Duration = 0, Optional SpecifiedAmount, Optional BenefitType)

If Not (blnInitialized) Then Initialize
Dim RateArray As Variant

    RateArray = objRates.Rates(RateType, Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, SpecifiedAmount, BenefitType)
    Dim RateUBound As Long
    RateUBound = UBound(RateArray)
    
    If RateUBound = 1 Then
     GetRate = RateArray(1)
    Else
      If RateUBound < Duration Then
        GetRate = "NA"
      Else
        GetRate = RateArray(Duration)
       End If
    End If

End Function

Public Function GetMaturityAge(Plancode As String, Optional intIssueAge As Integer = 0)

Dim tempAge As Integer
If GetMATURITY_AGE_DURATION_INDICATOR(Plancode) = 1 Then
    tempAge = GetMATURITY_AGE_DURATION(Plancode)
Else
    tempAge = GetMATURITY_AGE_DURATION(Plancode) + intIssueAge
End If
GetMaturityAge = tempAge
End Function

Public Function GetMATURITY_AGE_DURATION(Plancode As String) As Variant
If Not blnInitialized Then Initialize
Dim tempValue As Integer
Select Case Plancode
    Case "1U539300": tempValue = 65
    Case "1U536A00": tempValue = 10
    Case "1U536B00": tempValue = 15
    Case "1U536C00": tempValue = 20
    Case "39": tempValue = 60
    Case "4C": tempValue = 60
    Case Else: tempValue = 100
End Select
GetMATURITY_AGE_DURATION = tempValue
End Function

Public Function GetMATURITY_AGE_DURATION_INDICATOR(Plancode As String) As Variant
If Not blnInitialized Then Initialize
Dim tempValue As Integer
'1 = Age, 2 = Duration
Select Case Plancode
    Case "1U539300": tempValue = 1
    Case "1U536A00": tempValue = 2
    Case "1U536B00": tempValue = 2
    Case "1U536C00": tempValue = 2
    Case "39": tempValue = 1
    Case "4C": tempValue = 1
    Case Else: tempValue = 1
End Select
GetMATURITY_AGE_DURATION_INDICATOR = tempValue
End Function

Public Function GetBAND(Plancode As String, Amount As Double)
If Not blnInitialized Then Initialize
Dim BandMatrix As Variant
 BandMatrix = GetBANDSPECS(Plancode, Amount)
 
 Dim BandPointer
 Dim BandAmount
 Dim FoundBand As Integer
 For BandPointer = UBound(BandMatrix) To LBound(BandMatrix) Step -1
  BandAmount = BandMatrix(0, BandPointer)
  If Amount > BandAmount Then
   FoundBand = BandMatrix(1, BandPointer)
   Exit For
  End If
 Next
 GetBAND = FoundBand
End Function


Public Function GetMTP(Plancode, IssueAge, Sex, Rateclass, Band) As Variant
 If Not blnInitialized Then Initialize
 GetMTP = GetRate("MTP", Plancode, IssueAge, Sex, Rateclass, 1, Band)
End Function

Public Function GetCTP(Plancode, IssueAge, Sex, Rateclass, Band) As Variant
 If Not blnInitialized Then Initialize
 GetCTP = GetRate("CTP", Plancode, IssueAge, Sex, Rateclass, , Band)
End Function

Public Function GetTBL1MTP(Plancode, IssueAge, Sex, Rateclass, Band) As Variant 'SQL Server Only
 If Not blnInitialized Then Initialize
 GetTBL1MTP = GetRate("TBL1MTP", Plancode, IssueAge, Sex, Rateclass, , Band)
End Function

Public Function GetTBL1CTP(Plancode, IssueAge, Sex, Rateclass, Band) As Variant 'SQL Server Only
 If Not blnInitialized Then Initialize
  GetTBL1CTP = GetRate("TBL1CTP", Plancode, IssueAge, Sex, Rateclass, , Band)
End Function

Public Function GetCOI(Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Duration) As Variant
  If Not blnInitialized Then Initialize
  GetCOI = GetRate("COI", Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Duration)
End Function

Public Function GetMFEE(Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Duration) As Variant
  If Not blnInitialized Then Initialize
 GetMFEE = GetRate("MFEE", Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Duration)
End Function

Public Function GetEPU(Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Duration) As Variant
  If Not blnInitialized Then Initialize
 GetEPU = GetRate("EPU", Plancode, IssueAge, Sex, Rateclass, Ratescale, Band, Duration)
End Function

Public Function GetCORR(Plancode, IssueAge, Duration) As Variant
  If Not blnInitialized Then Initialize
 GetCORR = GetRate("CORR", Plancode, IssueAge, , , , , Duration)
End Function

Public Function GetTPP(Plancode, Sex, Rateclass, Ratescale, Band, Duration) As Variant
  If Not blnInitialized Then Initialize
 GetTPP = GetRate("TPP", Plancode, , Sex, Rateclass, Ratescale, Band, Duration)
End Function

Public Function GetEPP(Plancode, Sex, Rateclass, Ratescale, Band, Duration) As Variant
  If Not blnInitialized Then Initialize
 GetEPP = GetRate("EPP", Plancode, , Sex, Rateclass, Ratescale, Band, Duration)
End Function

Public Function GetFLATP(Plancode, Rateclass, Ratescale, Band, Duration) As Variant 'SQL Server Only
  If Not blnInitialized Then Initialize
 GetFLATP = GetRate("FLATP", Plancode, , , Rateclass, Ratescale, Band, Duration)
End Function

Public Function GetSCR(Plancode, IssueAge, Sex, Rateclass, Band, Duration) As Variant
  If Not blnInitialized Then Initialize
 GetSCR = GetRate("SCR", Plancode, IssueAge, Sex, Rateclass, , Band, Duration)
End Function

Public Function GetSNETPERIOD(Plancode, IssueAge) As Variant
  If Not blnInitialized Then Initialize
 GetSNETPERIOD = GetRate("SNETPERIOD", Plancode, IssueAge)
End Function
Public Function GetDBD(Plancode, Duration) As Variant
  If Not blnInitialized Then Initialize
 GetDBD = GetRate("DBD", , , , , , , Duration)
End Function

Public Function GetGINT(Plancode, Duration) As Variant
  If Not blnInitialized Then Initialize
 GetGINT = GetRate("GINT", , , , , , , Duration)
End Function

Public Function GetPLNCRD(Plancode, Amount)
  If Not blnInitialized Then Initialize
 GetPLNCRD = GetRate("PLNCRD", Plancode)
End Function
Public Function GetPLNCRG(Plancode, Amount)
  If Not blnInitialized Then Initialize
 GetPLNCRG = GetRate("PLNCRG", Plancode)
End Function
Public Function GetRLNCRD(Plancode, Amount)
  If Not blnInitialized Then Initialize
 GetRLNCRD = GetRate("RLNCRD", Plancode)
End Function
Public Function GetRLNCRG(Plancode, Amount)
  If Not blnInitialized Then Initialize
 GetRLNCRG = GetRate("RLNCRG", Plancode)
End Function

Public Function GetBENCOI(Plancode, IssueAge, Sex, Rateclass, Ratescale, Duration, Benefit)
  If Not blnInitialized Then Initialize
 GetBENCOI = GetRate("BENCOI", Plancode, IssueAge, Sex, Rateclass, Ratescale, , Duration, , Benefit)
End Function

Public Function GetBENMTP(Plancode, IssueAge, Sex, Rateclass, Benefit)
  If Not blnInitialized Then Initialize
 GetBENMTP = GetRate("BENMTP", Plancode, IssueAge, Sex, Rateclass, , , , , Benefit)
End Function

Public Function GetBENCTP(Plancode, IssueAge, Sex, Rateclass, Benefit)
  If Not blnInitialized Then Initialize
 GetBENCTP = GetRate("BENCTP", Plancode, IssueAge, Sex, Rateclass, , , , , Benefit)
End Function

Public Function GetBONUSAV(Plancode, Ratescale, Duration)
  If Not blnInitialized Then Initialize
 GetBONUSAV = GetRate("BONUSAV", Plancode, , , , Ratescale, , Duration)
End Function

Public Function GetBONUSDUR(Plancode, Ratescale, Duration)
  If Not blnInitialized Then Initialize
 GetBONUSDUR = GetRate("BONUSDUR", Plancode, , , , Ratescale, , Duration)
End Function

Public Function GetBANDSPECS(Plancode, Amount)
  If Not blnInitialized Then Initialize
 GetBANDSPECS = objRates.BANDSPECS(Plancode, Amount)
End Function



