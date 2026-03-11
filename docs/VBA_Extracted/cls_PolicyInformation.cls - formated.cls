' Module: cls_PolicyInformation.cls
' Type: Class Module
' Stream Path: VBA/cls_PolicyInformation
' =========================================================
Attribute VB_Name = "cls_PolicyInformation"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
    Option Explicit
Private mCovCTP() As Double
Private mCovCTPhase() As String
Private mCTP As Double
Private mCovCTPCount As Integer
Private mCovCTDate() As Date
Private mNSP_Basic As Double
Private mNSP_Other As Double
Private blnLoadComTargets As Boolean
Private mSubstandardCovPhases As Variant
Private mSubstandardTypes As Variant
Private blnLoadSubstandard As Boolean
Private mdctAllocationPercent As Dictionary
Private blnLoadFundAllocation As Boolean
Private mFundBucketCount As Integer
Private mFundBucketID() As String
Private mFundBucketMVDate() As Date
Private mFundBucketStartDate() As Date
Private mFundBucketEndDate() As Date
Private mFundBucketValue() As Double
Private mdctFundValues As Dictionary
Private mFundBucketPhaseCode() As String
Private blnLoadFundBucketValues As Boolean
Private blnNoTAMRAValues As Boolean
Private mTempBASArray As Variant
Private oRates As cls_Rates
Private DB2 As cls_PolicyData
Private mDctBaseIndices As Dictionary
Private mDctRiderIndices As Dictionary
Private mBaseMatrix
Private mRiderMatrx
Private mBenefitMatrix
Private blnLoadIndices As Boolean
Private dctBand As Dictionary

Public Sub classInitialize(sPolicynumber As String, Optional sRegion As String = "CKPR", Optional sCompanycode As Variant, Optional sSystemCode As String = "I", Optional objRates As cls_Rates)
  Set DB2 = New cls_PolicyData
  Set dctBand = New Dictionary
  DB2.classInitialize sPolicynumber, sRegion, sCompanycode, sSystemCode
    If objRates Is Nothing Then
        Set oRates = New cls_Rates
        oRates.Class_Initialize
    Else
        Set oRates = objRates
    End If
End Sub

Property Get ValuationDate() As Variant
'Valuation date should be last MV date.  but trad doesnt have MV, so use NextMonthliversary
If Me.ProductLineCode = "U" Or Me.ProductLineCode = "I" Then
  If Me.MVCount = 0 Then
    ValuationDate = "Null"
  Else
    ValuationDate = Me.MVDate
  End If
  Exit Property
End If
If Me.NextMonthliversary = "Null" Then
    ValuationDate = "Null"
    Exit Property
End If
If Me.NextMonthliversary = 0 Then
     ValuationDate = Me.LastFinancialDate
Else
     ValuationDate = DateAdd("m", -1, Me.NextMonthliversary)
End If
End Property

Property Get InGrace()
    If Me.AdvancedProductIndicator = "1" Then
        InGrace = DB2.DataItem("LH_NON_TRD_POL", "IN_GRA_PER_IND").NullZ(1, "")
    Else
        InGrace = DB2.DataItem("LH_TRD_POL", "IN_GRA_PER_IND").NullZ(1, "")
    End If
End Property

Property Get GPEDate()
If Me.AdvancedProductIndicator = "1" Then
    GPEDate = DB2.DataItem("LH_NON_TRD_POL", "GRA_PER_EXP_DT").NullZ(1, "")
Else
    GPEDate = DB2.DataItem("LH_TRD_POL", "GRA_PER_EXP_DT").NullZ(1, "")
End If
End Property

Property Get AttainedAge()
    AttainedAge = CovIssueAge(1) + PolicyYear - 1
End Property

Property Get PolicyYear()
 PolicyYear = CompletedDateParts("YYYY", CovIssueDate(1), Me.ValuationDate) + 1
End Property

Property Get PolicyMonth()
  PolicyMonth = MonthOfYear(Month(CovIssueDate(1)), Month(Me.ValuationDate))
End Property

Property Get AgeAtMaturity()
Dim Yrs As Integer
 Yrs = CompletedDateParts("YYYY", Me.CovIssueDate(1), Me.CovMaturityDate(1))
 AgeAtMaturity = Me.CovIssueAge(1) + Yrs
End Property

Property Get PolicyNotFound()
 PolicyNotFound = DB2.PolicyNotFound
End Property

Property Get PolicyNumber()
 PolicyNumber = DB2.PolicyNumber
End Property

Property Get region()
  region = DB2.region
End Property

Property Get SystemCode()
  SystemCode = DB2.SystemCode
End Property

Property Get PolicyKey()
PolicyKey = MakePolicyKey(PolicyNumber, region, CompanyCode, SystemCode)
End Property

Property Get DB2Data() As cls_PolicyData
  Set DB2Data = DB2
End Property

'====================================================================================================================================================================================
'LH_BAS_POL

'====================================================================================================================================================================================

Property Get AdvancedProductIndicator() As Variant
  AdvancedProductIndicator = DB2.DataItem("LH_BAS_POL", "NON_TRD_POL_IND").value
End Property

Property Get NonForfeitureOption() As Variant
  NonForfeitureOption = DB2.DataItem("LH_BAS_POL", "NFO_OPT_TYP_CD").value
End Property

Property Get LastAnniversary() As Variant
   LastAnniversary = DB2.DataItem("LH_BAS_POL", "LST_ANV_DT").value
End Property

Property Get NextMonthliversary() As Variant
   NextMonthliversary = DB2.DataItem("LH_BAS_POL", "NXT_MVRY_PRC_DT").value
End Property

Property Get LastFinancialDate() As Variant
  LastFinancialDate = DB2.DataItem("LH_BAS_POL", "LST_FIN_DT").value
End Property

Property Get NextBillDate() As Variant
   NextBillDate = DB2.DataItem("LH_BAS_POL", "NXT_BIL_DT").value
End Property

Property Get PremiumDatePaidTo() As Variant
   PremiumDatePaidTo = DB2.DataItem("LH_BAS_POL", "PRM_PAID_TO_DT").value
End Property

Property Get PremiumDateBillTo() As Variant
   PremiumDatePaidTo = DB2.DataItem("LH_BAS_POL", "PRM_BILL_TO_DT").value
End Property
'Property Get PolicyPremiumAmount() As Variant
'   PolicyPremiumAmount = mPolicyPremiumAmount
'End Property

Property Get Indicator1035() As Variant
   Indicator1035 = DB2.DataItem("LH_BAS_POL", "POL_1035_XCG_IND").value
End Property

Property Get DividendOptionCode() As Variant
 DividendOptionCode = DB2.DataItem("LH_BAS_POL", "PRI_DIV_OPT_CD").value
End Property

Property Get SecondardyDividendOptionCode() As Variant
  SecondardyDividendOptionCode = DB2.DataItem("LH_BAS_POL", "DIV_2ND_OPT_CD").value
End Property

Property Get MDO() As Variant
  MDO = DB2.DataItem("LH_BAS_POL", "USR_RES_CD").value
End Property

Property Get NonStandardModeCode() As Variant
  NonStandardModeCode = DB2.DataItem("LH_BAS_POL", "NSD_MD_CD").value
End Property

Property Get SuspenseText() As Variant
 SuspenseText = TranslateSuspenseCodeToText(Me.SuspenseCode)
End Property

Property Get SuspenseCode() As Variant
 SuspenseCode = DB2.DataItem("LH_BAS_POL", "SUS_CD").value
End Property

Property Get OriginalEntryText() As Variant
 OriginalEntryText = TranslateOriginalEntryCodeToText(Me.OriginalEntryCode)
End Property

Property Get OriginalEntryCode() As Variant
 OriginalEntryCode = DB2.DataItem("LH_BAS_POL", "OGN_ETR_CD").value
End Property

Property Get LastEntryText() As Variant
 LastEntryText = TranslateLastEntryCodeToText(Me.LastEntryCode)
End Property

Property Get LastEntryCode() As Variant
 LastEntryCode = DB2.DataItem("LH_BAS_POL", "LST_ETR_CD").value
End Property

Property Get StatusCode() As Variant
 StatusCode = DB2.DataItem("LH_BAS_POL", "PRM_PAY_STA_REA_CD").value
End Property

Property Get StatusText() As Variant
 StatusText = TranslateStatusCodeToText(Me.StatusCode)
End Property

Property Get IssueStateCode() As Variant
 IssueStateCode = DB2.DataItem("LH_BAS_POL", "POL_ISS_ST_CD").value
End Property

Property Get IssueStateAbbr() As Variant
 IssueStateAbbr = TranslateStateCodeToText(CInt(Me.IssueStateCode))
End Property

Property Get ResidentStateCode() As Variant
 ResidentStateCode = DB2.DataItem("LH_BAS_POL", "PRM_PAY_ST_CD").value
End Property

Property Get ResidentStateAbbr() As Variant
 ResidentStateAbbr = TranslateStateCodeToText(CInt(Me.ResidentStateCode))
End Property

Property Get PolicyID() As Variant
 PolicyID = DB2.PolicyID
End Property

Property Get CompanyCode() As Variant
 CompanyCode = DB2.CompanyCode
End Property

Property Get Company() As Variant
 Company = TranslateCompanyCodeToText(Me.CompanyCode)
End Property

Property Get BillMode() As Variant
 BillMode = TranslateBillModeCodeToText(Me.BillModeCode)
End Property

Property Get BillModeCode() As Variant
 BillModeCode = DB2.DataItem("LH_BAS_POL", "PMT_FQY_PER").value
End Property

Property Get BillPremium() As Variant
 BillPremium = DB2.DataItem("LH_BAS_POL", "POL_PRM_AMT").value
End Property

Property Get BillFormCode() As Variant
 BillFormCode = DB2.DataItem("LH_BAS_POL", "BIL_FRM_CD").value
End Property

Property Get NonStandardMode() As Variant
 NonStandardMode = DB2.DataItem("LH_BAS_POL", "NSD_MD_CD").value
End Property

Property Get PremiumPayingResidentStateAbbr() As Variant
 PremiumPayingResidentStateAbbr = TranslateStateCodeToText(CInt(DB2.DataItem("LH_BAS_POL", "PRM_PAY_ST_CD").value))
End Property

Property Get AgencyBranch()
    AgencyBranch = DetermineMarketOrg(Me.CompanyCode, Mid(Me.ServicingBranchOrAgencyCode, 2, 3))
End Property

Property Get ServicingMarketOrganization() As Variant
  ServicingMarketOrganization = DetermineMarketOrg(Me.CompanyCode, left(Me.ServicingBranchOrAgencyCode, 1))
End Property

Property Get PolicyLoanChargeRate() As Variant
 PolicyLoanChargeRate = DB2.DataItem("LH_BAS_POL", "LN_PLN_ITS_RT").value
End Property

Property Get LoanInterestTypeCode() As Variant
 LoanInterestTypeCode = DB2.DataItem("LH_BAS_POL", "LN_TYP_CD").value
End Property

Property Get ServicingAgentNumber() As Variant
  ServicingAgentNumber = DB2.DataItem("LH_BAS_POL", "SVC_AGT_NBR").value
End Property

Property Get ServicingBranchOrAgencyCode() As Variant
 ServicingBranchOrAgencyCode = DB2.DataItem("LH_BAS_POL", "SVC_AGC_NBR").value
End Property

Property Get ForcedPremiumIndicator() As Variant
    ForcedPremiumIndicator = DB2.DataItem("TH_BAS_POL", "FORCED_PREM_IND").value
End Property

'====================================================================================================================================================================================
'LH_COV_PHA

'====================================================================================================================================================================================

Property Get ProductType() As String
Dim tempValue As String
If ProductIndicator = "X" Then
    tempValue = "IUL"
Else
  tempValue = "Non UL"
  If CovProductLineCode(1) = "U" Then tempValue = "UL"
  If CovProductLineCode(1) = "I" Then tempValue = "ISWL"
  If CovValuationClass(1) = "1" Then tempValue = "WL"
  If CovValuationClass(1) = "5" Or CovValuationClass(1) = "8" Then tempValue = "TERM"
 End If
ProductType = tempValue
End Property

Property Get TradCashValue()
'RJH - add 4/9/2024
Dim tempAV As Double, tempNSP As Double
Dim totalAV As Double
Dim X As Integer
For X = 1 To CovCount
    If CovProductLineCode(X) <> "U" Then
        'Either the CSV amounts or used and the NSP amoutns are 0 or vice verse (if policy is RPU).  So just add both to always get the CSV for a policy
        tempAV = CovCVAmount1(X) * (12 - CovMonthOfYear(X)) + CovMonthOfYear(X) * CovCVAmount2(X)
        tempAV = WorksheetFunction.Round(tempAV / 12, 3)
        tempAV = WorksheetFunction.Round(tempAV * CovUnits(X), 2)
        tempNSP = CovNSPRate1(X) * (12 - CovMonthOfYear(X)) + CovMonthOfYear(X) * CovNSPRate2(X)
        tempNSP = WorksheetFunction.Round(tempNSP / 12, 5)
        tempNSP = WorksheetFunction.Round(tempNSP * CovUnits(X), 2)
    End If
    totalAV = totalAV + tempAV + tempNSP
Next
TradCashValue = totalAV
End Property

Private Sub LoadIndices()
Set mDctBaseIndices = New Dictionary
Set mDctRiderIndices = New Dictionary
Dim X As Integer
For X = 1 To Me.CovCount
    If CovStatus(X) <> "0" Then 'Staus of "0" means the coverage is terminated
        If Me.CovIsBase(X) Then
            mDctBaseIndices.Add mDctBaseIndices.Count + 1, X
        Else
            mDctRiderIndices.Add mDctRiderIndices.Count + 1, X
        End If
    End If
Next
blnLoadIndices = True
End Sub

Property Get CovCount()
  CovCount = DB2.DataItem("LH_COV_PHA", "COV_PHA_NBR").Count
End Property

Property Get CovMonthOfYear(Cov As Integer)
'RJH - add 4/9/2024
    Dim IssMonth As Integer, CurrMonth As Integer
    IssMonth = Month(CovIssueDate(Cov))
    CurrMonth = Month(Now())
    CovMonthOfYear = CurrMonth - IssMonth + IIf(Day(CurrMonth) >= Day(IssMonth), 1, 0) + IIf(CurrMonth < IssMonth, 12, 0)
End Property

Property Get DctBaseIndices()
    If Not blnLoadIndices Then LoadIndices
    Set DctBaseIndices = mDctBaseIndices
End Property

Property Get DctRiderIndices()
    If Not blnLoadIndices Then LoadIndices
    Set DctRiderIndices = mDctRiderIndices
End Property

Property Get BaseCoveragesHaveSameAttainedAge() As Boolean
Dim X As Integer, AttainedAge1 As Integer, blnSame As Boolean
blnSame = True
AttainedAge1 = CovIssueAge(1) + CompletedDateParts("YYYY", CovIssueDate(1), Now())
For X = 2 To Me.CovCount
    If CovIsBase(X) Then
        blnSame = blnSame And (AttainedAge1 = CovIssueAge(X) + CompletedDateParts("YYYY", CovIssueDate(X), Now()))
    End If
Next
BaseCoveragesHaveSameAttainedAge = blnSame
End Property

Property Get CovValuationClass(Cov As Integer) As String
    CovValuationClass = DB2.DataItem("LH_COV_PHA", "INS_CLS_CD").value(Cov)
End Property

Property Get CovStatus(Cov As Integer)
    CovStatus = DB2.DataItem("LH_COV_PHA", "NXT_CHG_TYP_CD").value(Cov)
End Property

Property Get CovValuationBase(Cov As Integer) As String
    CovValuationBase = DB2.DataItem("LH_COV_PHA", "PLN_BSE_SRE_CD").value(Cov)
End Property

Property Get CovValuationSubseries(Cov As Integer) As String
    CovValuationSubseries = DB2.DataItem("LH_COV_PHA", "LIF_PLN_SUB_SRE_CD").value(Cov)
End Property

Property Get ProductLineCode()
 ProductLineCode = DB2.DataItem("LH_COV_PHA", "PRD_LIN_TYP_CD").value
End Property

Property Get ProductIndicator()
 ProductIndicator = DB2.DataItem("TH_COV_PHA", "AN_PRD_ID").value
End Property

Property Get CovValueType() As String
  If Me.ProductLineCode = "U" Then
   CovValueType = "NA"
 Else
   CovValueType = IIf(left(Me.StatusCode, 1) = "4", "NSP", "CV")
 End If
End Property

Property Get CovIsBase(Cov As Integer) As Boolean
  CovIsBase = (CovPlancode(Cov) = CovPlancode(1))
End Property

Property Get CovCOLAIndicator(Cov As Integer) As String
  CovCOLAIndicator = DB2.DataItem("TH_COV_PHA", "COLA_INCR_IND").value(Cov)
End Property

Property Get CovGIOIndicator(Cov As Integer) As String
  CovGIOIndicator = DB2.DataItem("TH_COV_PHA", "OPT_EXER_IND").value(Cov)
End Property

Property Get CovPhase(Cov As Integer) As Variant
  CovPhase = DB2.DataItem("LH_COV_PHA", "COV_PHA_NBR").value(Cov)
End Property

Property Get CovRateclass(Cov As Integer, Optional JtIndicator As Integer = 0) As Variant
    CovRateclass = RenewalCovRateclass(Cov, , JtIndicator)
End Property

Property Get CovSex(Cov As Integer, Optional JtIndicator As Integer = 0) As Variant
Dim tempSex As Variant
tempSex = RenewalCovSexCode(Cov, , JtIndicator)
Select Case tempSex
  Case "1": tempSex = "M"
  Case "2": tempSex = "F"
  Case Else: tempSex = tempSex
End Select
CovSex = tempSex
End Property

Property Get ClassCode(Cov As Integer) As Variant
  ClassCode = DB2.DataItem("LH_COV_PHA", "INS_CLS_CD").value(Cov)
End Property

Property Get BaseCode(Cov As Integer) As Variant
  BaseCode = DB2.DataItem("LH_COV_PHA", "PLN_BSE_SRE_CD").value(Cov)
End Property

Property Get SubseriesCode(Cov As Integer) As Variant
  SubseriesCode = DB2.DataItem("LH_COV_PHA", "LIF_PLN_SUB_SRE_CD").value(Cov)
End Property

Property Get CovUnits(Cov As Integer) As Variant
  CovUnits = DB2.DataItem("LH_COV_PHA", "COV_UNT_QTY").value(Cov)
End Property

Property Get CovCOI(Cov As Integer) As Variant
    CovCOI = DB2.DataItem("LH_COV_PHA", "ANN_PRM_UNT_AMT").value(Cov)
End Property

Property Get CovOrinUnits(Cov As Integer) As Variant
   CovOrinUnits = DB2.DataItem("LH_COV_PHA", "OGN_SPC_UNT_QTY").value(Cov)
End Property

Property Get CovVPU(Cov As Integer) As Variant
  CovVPU = DB2.DataItem("LH_COV_PHA", "COV_VPU_AMT").value(Cov)
End Property

Property Get CovAmount(Cov As Integer) As Variant
  CovAmount = CovUnits(Cov) * CovVPU(Cov)
End Property

Property Get CovOrigAmount(Cov As Integer) As Variant
   CovOrigAmount = IIf(CovOrinUnits(Cov) = "Null", 0, CovOrinUnits(Cov)) * CovVPU(Cov)
End Property

Property Get CovIssueAge(Cov As Integer, Optional JtIndicator As Integer = 0) As Variant
If JtIndicator = 0 Then
    CovIssueAge = DB2.DataItem("LH_COV_PHA", "INS_ISS_AGE").value(Cov)
Else
    CovIssueAge = DB2.DataItem("LH_COV_PHA", "JNT_ISU_ISS_AGE").value(Cov)
End If
End Property

Property Get CovIssueDate(Cov As Integer) As Variant
  CovIssueDate = DB2.DataItem("LH_COV_PHA", "ISSUE_DT").value(Cov)
End Property

Property Get CovMaturityDate(Cov As Integer) As Variant
  CovMaturityDate = DB2.DataItem("LH_COV_PHA", "COV_MT_EXP_DT").value(Cov)
End Property
'Property Get CovOffsetMonths(cov As Integer) As Variant
''For post issue coverages, this calculates the number of months a coverage was added after the policy issue date.
''If subsequent coveage is added on anniversary this value is 0.
'   CovOffsetMonths = Month(CovIssueDate(cov)) - Month(CovIssueDate(1)) + IIf(Month(CovIssueDate(cov)) < Month(CovIssueDate(1)), 12, 0)
'End Property

Property Get CovFormNumber(Cov As Integer) As Variant
  CovFormNumber = DB2.DataItem("LH_COV_PHA", "POL_FRM_NBR").value(Cov)
End Property

Property Get CovPlancode(Cov As Integer) As Variant
  CovPlancode = Application.WorksheetFunction.Trim(DB2.DataItem("LH_COV_PHA", "PLN_DES_SER_CD").value(Cov))
End Property

Property Get CovPlancodeList(Optional Delimiter As String = ",") As String
    Dim X As Integer
    Dim str As String
    For X = 1 To CovCount
        str = str & CovPlancode(X)
        If X < CovCount Then str = str & Delimiter
    Next
    CovPlancodeList = str
End Property

Property Get CovCeaseDate(Cov As Integer) As Variant
    If Me.CovStatus(Cov) = "0" Then
        CovCeaseDate = DB2.DataItem("LH_COV_PHA", "NXT_CHG_DT").value(Cov)
    Else
        CovCeaseDate = " "
    End If
End Property

Property Get CovDuration(Cov As Integer) As Variant
  Dim CovAdjustedIssueDate As Date
  CovAdjustedIssueDate = DateSerial(Year(CovIssueDate(Cov)), Month(CovIssueDate(1)), Day(CovIssueDate(1)))
  CovDuration = CompletedDateParts("YYYY", CovIssueDate(0), CovAdjustedIssueDate) + 1
End Property

Property Get CovAgeCalcCode(Cov As Integer) As Variant
  CovAgeCalcCode = DB2.DataItem("LH_COV_PHA", "AGE_CLC_RLE_CD").value(Cov)
End Property

Property Get CovProductLineCode(Cov As Integer) As Variant
  CovProductLineCode = DB2.DataItem("LH_COV_PHA", "PRD_LIN_TYP_CD").value(Cov)
End Property

Property Get CovMortalityTableCode(Cov As Integer) As Variant
  CovMortalityTableCode = DB2.DataItem("LH_COV_PHA", "MTL_FCT_TBL_CD").value(Cov)
End Property

Property Get CovPersonCode(Cov As Integer) As String
    CovPersonCode = DB2.DataItem("LH_COV_PHA", "PRS_CD").value(Cov)
End Property

Property Get CovPersonSequenceCode(Cov As Integer) As String
    CovPersonSequenceCode = DB2.DataItem("LH_COV_PHA", "PRS_SEQ_NBR").value(Cov)
End Property

Property Get CovQualified(Cov As Integer) As Boolean
    CovQualified = (CovPersonCode(Cov) = "00" Or CovPersonCode(Cov) = "40" Or CovPersonCode(Cov) = "50")
End Property

Property Get CovInsuredName(Cov As Integer) As String
CovInsuredName = ""
Dim X As Integer
For X = 1 To Me.PersonCount
    If Me.PersonCode(X) = CovPersonCode(Cov) And Me.PersonSequenceCode(X) = CovPersonSequenceCode(Cov) Then
        CovInsuredName = Me.PersonFirstName(X) & " " & Me.PersonLastName(X)
        Exit For
    End If
Next
End Property

Property Get TotalSpecifiedAmount() As Variant
Dim Cov As Integer
Dim tempValue As Double
tempValue = 0
 For Cov = 1 To CovCount
   If CovPlancode(Cov) = CovPlancode(1) Then tempValue = tempValue + CovAmount(Cov)
 Next
TotalSpecifiedAmount = tempValue
End Property

Property Get TotalOrinSpecifiedAmount() As Variant
Dim Cov As Integer
Dim tempValue As Double
tempValue = 0
 For Cov = 1 To CovCount
   If CovPlancode(Cov) = CovPlancode(1) Then tempValue = tempValue + CovOrigAmount(Cov)
 Next
TotalOrinSpecifiedAmount = tempValue
End Property

Property Get CovETITable(Cov As Integer)
  CovETITable = DB2.DataItem("LH_COV_PHA", "NSP_EI_TBL_CD").value(Cov)
End Property

Property Get CovRPUTable(Cov As Integer)
  CovRPUTable = DB2.DataItem("LH_COV_PHA", "NSP_RPU_TBL_CD").value(Cov)
End Property

Property Get CovNFOIntRate(Cov As Integer)
  CovNFOIntRate = DB2.DataItem("LH_COV_PHA", "NSP_ITS_RT").value(Cov)
End Property

Property Get CovAPU(Cov As Integer)
  CovAPU = DB2.DataItem("LH_COV_PHA", "ANN_PRM_UNT_AMT").value(Cov)
End Property

Property Get CalcFunctionCode(Cov As Integer)
  CalcFunctionCode = DB2.DataItem("LH_COV_PHA", "MTL_FUN_CD").value(Cov)
End Property

Property Get CovLowDuration(Cov As Integer)
  CovLowDuration = DB2.DataItem("LH_COV_PHA", "LOW_DUR_PER").NullZ(Cov, 0)
End Property

Property Get CovCVAmount0(Cov As Integer)
 'This is the cash value as of the CovLowDuration
  CovCVAmount0 = DB2.DataItem("LH_COV_PHA", "LOW_DUR_CSV_AMT").NullZ(Cov, 0)
End Property

Property Get CovCVAmount1(Cov As Integer)
  CovCVAmount1 = DB2.DataItem("LH_COV_PHA", "LOW_DUR_1_CSV_AMT").NullZ(Cov, 0)
End Property

Property Get CovCVAmount2(Cov As Integer)
  CovCVAmount2 = DB2.DataItem("LH_COV_PHA", "LOW_DUR_2_CSV_AMT").NullZ(Cov, 0)
End Property

Property Get CovCVAmount3(Cov As Integer)
  CovCVAmount3 = DB2.DataItem("LH_COV_PHA", "LOW_DUR_3_CSV_AMT").NullZ(Cov, 0)
End Property

Property Get CovNSPRate0(Cov As Integer)
'This is the NSP as the CovLowDuraiton
  CovNSPRate0 = DB2.DataItem("LH_COV_PHA", "LOW_DUR_NSP_AMT").NullZ(Cov, 0)
End Property

Property Get CovNSPRate1(Cov As Integer)
  CovNSPRate1 = DB2.DataItem("LH_COV_PHA", "LOW_DUR_1_NSP_AMT").NullZ(Cov, 0)
End Property

Property Get CovNSPRate2(Cov As Integer)
  CovNSPRate2 = DB2.DataItem("LH_COV_PHA", "LOW_DUR_2_NSP_AMT").NullZ(Cov, 0)
End Property

'====================================================================================================================================================================================
'LH_POL_TARGET

'====================================================================================================================================================================================

Property Get NSP_Base()
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").Count
     If DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").value(X) = "NS" Then
       NSP_Base = DB2.DataItem("LH_POL_TARGET", "TAR_PRM_AMT").value(X)
       Exit Property
     End If
   Next
End Property

Property Get NSP_Other()
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").Count
     If DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").value(X) = "NT" Then
       NSP_Other = DB2.DataItem("LH_POL_TARGET", "TAR_PRM_AMT").value(X)
       Exit Property
     End If
   Next
End Property

Property Get MTP()
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").Count
     If DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").value(X) = "MT" Then
       MTP = DB2.DataItem("LH_POL_TARGET", "TAR_PRM_AMT").value(X)
       Exit Property
     End If
   Next
End Property

Property Get AccumMTP()
AccumMTP = 0
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").Count
     If DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").value(X) = "MA" Then
       AccumMTP = DB2.DataItem("LH_POL_TARGET", "TAR_PRM_AMT").value(X)
       Exit Property
     End If
   Next
End Property

Property Get MAPDate()
MAPDate = 0
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").Count
     If DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").value(X) = "MA" Then
       MAPDate = DB2.DataItem("LH_POL_TARGET", "TAR_DT").value(X)
       Exit Property
     End If
   Next
End Property

Property Get ShortPayPrem()
ShortPayPrem = Empty
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").Count
     If DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").value(X) = "VS" Then
       ShortPayPrem = DB2.DataItem("LH_POL_TARGET", "TAR_PRM_AMT").value(X)
       Exit Property
     End If
   Next
End Property

Property Get ShortPayDate()
ShortPayDate = Empty
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").Count
     If DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").value(X) = "VS" Then
       ShortPayDate = DB2.DataItem("LH_POL_TARGET", "TAR_DT").value(X)
       Exit Property
     End If
   Next
End Property

Property Get AccumGLP()
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").Count
     If DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").value(X) = "TA" Then
       AccumGLP = DB2.DataItem("LH_POL_TARGET", "TAR_PRM_AMT").value(X)
       Exit Property
     End If
   Next
End Property

Property Get PLT()
Dim X As Integer, TargetType As String
   For X = 1 To DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").Count
     TargetType = DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").value(X)
     If TargetType = "LT" Then
       PLT = DB2.DataItem("LH_POL_TARGET", "TAR_PRM_AMT").value(X)
       Exit Property
     End If
   Next
End Property

Property Get GAV() As Variant
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").Count
     If DB2.DataItem("LH_POL_TARGET", "TAR_TYP_CD").value(X) = "IX" Then
       GAV = DB2.DataItem("LH_POL_TARGET", "TAR_PRM_AMT").value(X)
       Exit Property
     End If
   Next
End Property

'====================================================================================================================================================================================
'LH_SPM_BNF

'====================================================================================================================================================================================

Public Function GetBenIndex(strTypeSubType As String) As Integer
Dim xIndex As Integer
Dim TargetIndex As Integer
TargetIndex = -1
For xIndex = 0 To BenCount
 If BenPlancode(xIndex) = strTypeSubType Then TargetIndex = xIndex
Next
GetBenIndex = TargetIndex
End Function
'Property Get BenRenewalIndicator(BenefitIndex As Integer) As Variant
'   BenRenewalIndicator = DB2.DataItem("LH_SPM_BNF", "").Value(BenefitIndex)
'End Property

Property Get BenCount()
   BenCount = DB2.DataItem("LH_SPM_BNF", "SPM_BNF_TYP_CD").Count
End Property

Property Get BenRenewalIndicator(BenefitIndex As Integer) As Variant
   BenRenewalIndicator = DB2.DataItem("LH_SPM_BNF", "RNL_RT_IND").value(BenefitIndex)
End Property

Property Get BenRatingFactor(BenefitIndex As Integer) As Variant
   BenRatingFactor = DB2.DataItem("LH_SPM_BNF", "BNF_RT_FCT").value(BenefitIndex)
End Property

Property Get BenCOIRate(BenefitIndex As Integer) As Double
   BenCOIRate = DB2.DataItem("LH_SPM_BNF", "BNF_ANN_PPU_AMT").value(BenefitIndex)
End Property

Property Get BenUnits(BenefitIndex As Integer)
   BenUnits = DB2.DataItem("LH_SPM_BNF", "BNF_UNT_QTY").value(BenefitIndex)
End Property

Property Get BenVPU(BenefitIndex As Integer)
   BenVPU = DB2.DataItem("LH_SPM_BNF", "BNF_VPU_AMT").value(BenefitIndex)
End Property

Property Get BenAmount(BenefitIndex As Integer)
    BenAmount = BenUnits(BenefitIndex) * BenVPU(BenefitIndex)
End Property

Property Get BenTypeCode(BenefitIndex As Integer) As String
  BenTypeCode = left(BenPlancode(BenefitIndex), 1)
End Property

Property Get BenType(BenefitIndex As Integer) As String
  BenType = TranslateBenefitCodeToType(left(BenPlancode(BenefitIndex), 1))
End Property

Property Get BenSubtypeCode(BenefitIndex As Integer) As String
  BenSubtypeCode = Mid(BenPlancode(BenefitIndex), 2, 1)
End Property

Property Get BenIssueAge(BenefitIndex As Integer)
   BenIssueAge = DB2.DataItem("LH_SPM_BNF", "BNF_ISS_AGE").value(BenefitIndex)
End Property

Property Get BenIssueDate(BenefitIndex As Integer)
   BenIssueDate = DB2.DataItem("LH_SPM_BNF", "BNF_ISS_DT").value(BenefitIndex)
End Property

Property Get BenCeaseDate(BenefitIndex As Integer)
   BenCeaseDate = DB2.DataItem("LH_SPM_BNF", "BNF_CEA_DT").value(BenefitIndex)
End Property

Property Get BenOriginalCeaseDate(BenefitIndex As Integer)
   BenOriginalCeaseDate = DB2.DataItem("LH_SPM_BNF", "BNF_OGN_CEA_DT").value(BenefitIndex)
End Property

Property Get BenFormNumber(BenefitIndex As Integer)
   BenFormNumber = DB2.DataItem("LH_SPM_BNF", "BNF_FRM_NBR").value(BenefitIndex)
End Property

Property Get BenPlancode(BenefitIndex As Integer)
   BenPlancode = DB2.DataItem("LH_SPM_BNF", "SPM_BNF_TYP_CD").value(BenefitIndex) & DB2.DataItem("LH_SPM_BNF", "SPM_BNF_SBY_CD").value(BenefitIndex)
End Property

Property Get BenCovPhase(BenefitIndex As Integer)
    BenCovPhase = DB2.DataItem("LH_SPM_BNF", "COV_PHA_NBR").value(BenefitIndex)
End Property

Property Get BenList() As String
    Dim X As Integer
    Dim str As String
    For X = 1 To BenCount
        str = BenPlancode(X)
        If X < BenCount Then str = str & ","
    Next
    BenList = str
End Property

'====================================================================================================================================================================================
'LH_COV_INS_GDL_PRM

'====================================================================================================================================================================================
'Case "A":  GLP = TargetValue
'Case "B":  mAccumGLP
'Case "C":  mAccumMTP
'Case "D":  mMTP = TargetValue: blnMTP = True
'Case "E":  mLTP = TargetValue: blnLTP = True
'Case "G":  mLTP = TargetValue: blnLTP = True
'Case "J":  mLTP = TargetValue: blnLTP = True
'Case "L":  mLTP = TargetValue: blnLTP = True
'Case "M":  mLTP = TargetValue: blnLTP = True
'Case "S":  mGSP = TargetValue
'Case "T":  mLTP = TargetValue: blnLTP = True
'Case "V":  mLTP = TargetValue: blnLTP = True
'Case "W":  mLTP = TargetValue: blnLTP = True
'Case "X":  mLTP = TargetValue: blnLTP = True
'Case "Y":  mLTP = TargetValue: blnLTP = True

Property Get GLP() As Variant
Dim X As Integer, TargetType As String, TArgetValue As Variant
   For X = 1 To DB2.DataItem("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD").Count
     TargetType = DB2.DataItem("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD").value(X)
     If TargetType = "A" Then
       GLP = DB2.DataItem("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT").value(X)
       Exit Property
     End If
   Next
End Property

Property Get GSP() As Variant
Dim X As Integer, TargetType As String, TArgetValue As Variant
   For X = 1 To DB2.DataItem("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD").Count
     TargetType = DB2.DataItem("LH_COV_INS_GDL_PRM", "PRM_RT_TYP_CD").value(X)
     If TargetType = "S" Then
       GSP = DB2.DataItem("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT").value(X)
       Exit Property
     End If
   Next
End Property

'====================================================================================================================================================================================
'LH_POL_MVRY_VAL

'====================================================================================================================================================================================

Property Get MVAV(Optional DtIndex As Integer = 1)
    MVAV = DB2.DataItem("LH_POL_MVRY_VAL", "CSV_AMT").value(DtIndex)
End Property

Property Get MVCOICharge(Optional DtIndex As Integer = 1)
    MVCOICharge = DB2.DataItem("LH_POL_MVRY_VAL", "CINS_AMT").NullZ(DtIndex, 0)
End Property

Property Get MVExpChrg(Optional DtIndex As Integer = 1)
    MVExpChrg = DB2.DataItem("LH_POL_MVRY_VAL", "EXP_CRG_AMT").NullZ(DtIndex, 0)
End Property

Property Get MVOtherChrg(Optional DtIndex As Integer = 1)
    MVOtherChrg = DB2.DataItem("LH_POL_MVRY_VAL", "OTH_PRM_AMT").NullZ(DtIndex, 0)
End Property

Property Get MVMonthlyDeduction(Optional DtIndex As Integer = 1)
    MVMonthlyDeduction = MVCOICharge(DtIndex) + MVExpChrg(DtIndex) + MVOtherChrg(DtIndex)
End Property

Property Get MVCurrentInterest(Optional DtIndex As Integer = 1) As Double
    MVCurrentInterest = DB2.DataItem("LH_POL_MVRY_VAL", "TOT_CRE_ITS_AMT").NullZ(DtIndex, 0)
End Property

Property Get MVGuaranteedInterest(Optional DtIndex As Integer = 1) As Double
    MVGuaranteedInterest = DB2.DataItem("LH_POL_MVRY_VAL", "GUA_RT_ERN_ITS_AMT").NullZ(DtIndex, 0)
End Property

Property Get MVCount()
    MVCount = DB2.DataItem("LH_POL_MVRY_VAL", "MVRY_DT").Count
End Property

Property Get MVDate(Optional DtIndex As Integer = 1)
    MVDate = DB2.DataItem("LH_POL_MVRY_VAL", "MVRY_DT").value(DtIndex)
End Property

Property Get MVPolicyYear(Optional DtIndex As Integer = 1)
    MVPolicyYear = DB2.DataItem("LH_POL_MVRY_VAL", "POL_DUR_NBR").value(DtIndex)
End Property

Property Get MVMonthOfYear(Optional DtIndex As Integer = 1)
Dim ValMonth As Date, IssueMonth As Date, mth As Integer
  ValMonth = Month(MVDate(DtIndex))
  IssueMonth = Month(Me.CovIssueDate(1))
  'Determine month of the year for valuation date.  This assumes all valuation dates are on monthliversary
  mth = Abs(IssueMonth - ValMonth)
  If IssueMonth > ValMonth Then mth = 12 - mth
  mth = mth + 1
  MVMonthOfYear = mth
End Property

Property Get MVNAR(Optional DtIndex As Integer = 1)
 MVNAR = DB2.DataItem("LH_POL_MVRY_VAL", "NAR_AMT").NullZ(DtIndex, 0)
End Property

'====================================================================================================================================================================================
'LH_COV_INS_RNL_RT

'====================================================================================================================================================================================

Public Function RenewalIndex(Cov As Integer, Optional RtType As String = "C", Optional JtIndicator As Integer = 0) As Integer
Dim Index As Integer, X As Integer
Index = -1
For X = 1 To RenewalCovCount
      If DB2.DataItem("LH_COV_INS_RNL_RT", "PRM_RT_TYP_CD").value(X) = RtType And _
         DB2.DataItem("LH_COV_INS_RNL_RT", "COV_PHA_NBR").value(X) = CovPhase(Cov) And _
         DB2.DataItem("LH_COV_INS_RNL_RT", "JT_INS_IND").value(X) = JtIndicator Then
         Index = X
      End If
Next
RenewalIndex = Index
End Function

Property Get RenewalCovCount()
  RenewalCovCount = DB2.DataItem("LH_COV_INS_RNL_RT", "COV_PHA_NBR").Count
End Property

 Property Get RenewalCovPhaseCode(Optional Index As Integer = 1, Optional RtType As String = "C")
 Dim RtIndex As Integer
 RtIndex = RenewalIndex(Index, RtType)
 If RtIndex < 0 Then Exit Property
 RenewalCovPhaseCode = DB2.DataItem("LH_COV_INS_RNL_RT", "COV_PHA_NBR").value(RtIndex)
End Property

 Property Get RenewalCovRateclass(Optional Index As Integer = 1, Optional RtType As String = "C", Optional JtIndicator As Integer = 0)
 Dim RtIndex As Integer
 RtIndex = RenewalIndex(Index, RtType, JtIndicator)
 If RtIndex < 0 Then Exit Property
 RenewalCovRateclass = DB2.DataItem("LH_COV_INS_RNL_RT", "RT_CLS_CD").value(RtIndex)
End Property

 Property Get RenewalCovRate(Optional Index As Integer = 1, Optional RtType As String = "C")
 Dim RtIndex As Integer
 RtIndex = RenewalIndex(Index, RtType)
 If RtIndex < 0 Then Exit Property
  RenewalCovRate = DB2.DataItem("LH_COV_INS_RNL_RT", "RNL_RT").NullZ(RtIndex, 0)
End Property

 Property Get RenewalCovBandCode(Optional Index As Integer = 1, Optional RtType As String = "C")
 Dim RtIndex As Integer
 RtIndex = RenewalIndex(Index, RtType)
 If RtIndex < 0 Then Exit Property
 RenewalCovBandCode = DB2.DataItem("LH_COV_INS_RNL_RT", "RT_BAN_CD").value(RtIndex)
End Property

 Property Get RenewalCovPremiumTypeCode(Optional Index As Integer = 1, Optional RtType As String = "C")
 Dim RtIndex As Integer
 RtIndex = RenewalIndex(Index, RtType)
 If RtIndex < 0 Then Exit Property
 RenewalCovPremiumTypeCode = DB2.DataItem("LH_COV_INS_RNL_RT", "PRM_RT_TYP_CD").value(RtIndex)
End Property

 Property Get RenewalCovSexCode(Optional Index As Integer = 1, Optional RtType As String = "C", Optional JtIndicator As Integer = 0)
 Dim RtIndex As Integer
 RtIndex = RenewalIndex(Index, RtType, JtIndicator)
 If RtIndex < 0 Then Exit Property
 RenewalCovSexCode = DB2.DataItem("LH_COV_INS_RNL_RT", "RT_SEX_CD").value(RtIndex)
End Property

'====================================================================================================================================================================================
'LH_BNF_INS_RNL_RT

'====================================================================================================================================================================================

Property Get RenewalBenCount() As Integer
  RenewalBenCount = DB2.DataItem("LH_BNF_INS_RNL_RT", "SPM_BNF_TYP_CD").Count
End Property

Property Get RenewalBenPremiumTypeCode(Optional BenefitIndex As Integer = 1)
  RenewalBenPremiumTypeCode = DB2.DataItem("LH_BNF_INS_RNL_RT", "PRM_RT_TYP_CD").value(BenefitIndex)
End Property

Property Get RenewalBenTypeCode(Optional BenefitIndex As Integer = 1)
  RenewalBenTypeCode = DB2.DataItem("LH_BNF_INS_RNL_RT", "SPM_BNF_TYP_CD").value(BenefitIndex)
End Property

Property Get RenewalBenSubTypeCode(Optional BenefitIndex As Integer = 1)
  RenewalBenSubTypeCode = DB2.DataItem("LH_BNF_INS_RNL_RT", "SPM_BNF_SBY_CD").value(BenefitIndex)
End Property

Property Get RenewalBenRate(Optional BenefitIndex As Integer = 1)
  RenewalBenRate = DB2.DataItem("LH_BNF_INS_RNL_RT", "RNL_RT").NullZ(BenefitIndex, 0)
End Property

'====================================================================================================================================================================================
'LH_BNF_INS_RNL_RT

'====================================================================================================================================================================================
'mRenewalSubBandCode(x) = NullZ(DB2Tables(T)(x, eLH_SST_XTR_RNL_RT.RT_BAN_CD), "")
'mRenewalSubSexCode(x) = NullZ(DB2Tables(T)(x, eLH_SST_XTR_RNL_RT.RT_SEX_CD), "")
'mRenewalSubRateclass(x) = NullZ(DB2Tables(T)(x, eLH_SST_XTR_RNL_RT.RT_CLS_CD), "")

Property Get RenewalSubCount() As Integer
 RenewalSubCount = DB2.DataItem("LH_BNF_INS_RNL_RT", "COV_PHA_NBR").Count
End Property

Property Get RenewalSubPhaseCode(Optional Cov As Integer = 1)
 RenewalSubPhaseCode = DB2.DataItem("LH_BNF_INS_RNL_RT", "COV_PHA_NBR").value(Cov)
End Property

Property Get RenewalSubPremiumTypeCode(Optional Cov As Integer = 1)
 RenewalSubPremiumTypeCode = DB2.DataItem("LH_BNF_INS_RNL_RT", "PRM_RT_TYP_CD").NullZ(Cov, "")
End Property

Property Get RenewalSubTablePercent(Optional Cov As Integer = 1)
 RenewalSubTablePercent = DB2.DataItem("LH_BNF_INS_RNL_RT", "SST_XTR_PCT").NullZ(Cov, 0)
End Property

Property Get RenewalSubTableCode(Optional Cov As Integer = 1)
 RenewalSubTableCode = DB2.DataItem("LH_BNF_INS_RNL_RT", "SST_XTR_RT_TBL_CD").NullZ(Cov, "")
End Property

Property Get RenewalSubFlatAmount(Optional Cov As Integer = 1)
 RenewalSubFlatAmount = DB2.DataItem("LH_BNF_INS_RNL_RT", "SST_XTR_UNT_AMT").NullZ(Cov, 0)
End Property

'====================================================================================================================================================================================
'LH_NON_TRD_POL

'====================================================================================================================================================================================

Property Get PreferredLoansAvailable() As Integer
  Dim tempValue
  tempValue = DB2.DataItem("LH_NON_TRD_POL", "PRF_LN_OPT_CD").NullZ(1, "0")
  PreferredLoansAvailable = IIf(tempValue = "0", 0, 1)
End Property

Property Get NonTrad_RegLoanCreditCode()
  NonTrad_RegLoanCreditCode = DB2.DataItem("LH_NON_TRD_POL", "LN_CRE_ITS_RT_CD").NullZ(1, "")
End Property

Property Get NonTrad_RegLoanCreditRate()
  NonTrad_RegLoanCreditRate = DB2.DataItem("LH_NON_TRD_POL", "LN_CRE_ITS_RT").NullZ(1, 0)
End Property

Property Get NonTrad_RegLoanChargeRate()
  NonTrad_RegLoanChargeRate = Me.PolicyLoanChargeRate
End Property

Property Get NonTrad_PrefLoanCreditCode()
  NonTrad_PrefLoanCreditCode = DB2.DataItem("LH_NON_TRD_POL", "PRF_LN_ITS_CRE_CD").NullZ(1, "")
End Property

Property Get NonTrad_PrefLoanCreditRate()
  NonTrad_PrefLoanCreditRate = DB2.DataItem("LH_NON_TRD_POL", "PRF_LN_ITS_CRE_RT").NullZ(1, 0)
End Property

Property Get NonTrad_PrefLoanChargeRate()
  NonTrad_PrefLoanChargeRate = DB2.DataItem("LH_NON_TRD_POL", "PRF_LN_ITS_CRG_RT").NullZ(1, 0)
End Property

Property Get NonTrad_CorridorPercent()
  NonTrad_CorridorPercent = DB2.DataItem("LH_NON_TRD_POL", "CDR_PCT").NullZ(1, 100)
End Property

Property Get NonTrad_GracePeriodEndingDate()
  NonTrad_GracePeriodEndingDate = DB2.DataItem("LH_NON_TRD_POL", "GRA_PER_EXP_DT").NullZ(1, 0)
End Property

Property Get NonTrad_GraceRuleCode()
 NonTrad_GraceRuleCode = DB2.DataItem("LH_NON_TRD_POL", "GRA_THD_RLE_CD").NullZ(1, "")
End Property

Property Get NonTrad_GAVInidicator()
 NonTrad_GAVInidicator = DB2.DataItem("LH_NON_TRD_POL", "PLVL_GAV_RULE").NullZ(1, "")
End Property

Property Get GuaranteedInterestRate()
 GuaranteedInterestRate = DB2.DataItem("LH_NON_TRD_POL", "POL_GUA_ITS_RT").NullZ(1, 0)
End Property

Property Get TEFRA_DEFRA()
Dim tempValue As Variant
tempValue = DB2.DataItem("LH_NON_TRD_POL", "TFDF_CD").NullZ(1, "")
   Select Case tempValue
     Case "1": TEFRA_DEFRA = "TEFRA"
     Case "2": TEFRA_DEFRA = "DEFRA"
     Case "3": TEFRA_DEFRA = "DEFRA"
     Case "5": TEFRA_DEFRA = "DEFRA"
     Case Else: TEFRA_DEFRA = tempValue
   End Select
End Property

Property Get GP_CVAT()
Dim tempValue As Variant
tempValue = DB2.DataItem("LH_NON_TRD_POL", "TFDF_CD").NullZ(1, "")
Select Case tempValue
     Case "1": GP_CVAT = "GP"       'TEFRA - determined by product definition
     Case "2": GP_CVAT = "GP"       'DEFRA - determined by product definition
     Case "3": GP_CVAT = "CVAT"     'DEFRA - determined by product definition
     Case "4": GP_CVAT = "GP"       '4 means that GP was selected on the app
     Case "5": GP_CVAT = "CVAT"     '5 means that CVAT was select on the app
     Case Else: GP_CVAT = tempValue
   End Select
End Property

Property Get DBOptionCode()
 DBOptionCode = DB2.DataItem("LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD").NullZ(1, "")
End Property

Property Get DBOption()
 DBOption = TranslateDBOptionCode(DBOptionCode)
End Property

Property Get DBOptionAmount()
Dim tempAmt As Double
If DB2.DataItem("LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD").FieldNotFound Then
    DBOptionAmount = 0
    Exit Property
End If
Select Case DB2.DataItem("LH_NON_TRD_POL", "DTH_BNF_PLN_OPT_CD").value
    Case "1": tempAmt = 0
    Case "2":
                    If MVCount = 0 Then
                        tempAmt = 0
                    Else
                        tempAmt = MVAV(1)
                    End If
    Case "3": tempAmt = TotalRegularPremium + TotalAdditionalPremium
    Case Else: tempAmt = 0
End Select
DBOptionAmount = tempAmt
End Property

'====================================================================================================================================================================================
'LH_POL_TOT

'====================================================================================================================================================================================

Property Get PolicyTotalsCount()
   PolicyTotalsCount = DB2.DataItem("LH_POL_TOTALS", "TOT_REG_PRM_AMT").Count
End Property

Property Get TotalRegularPremium()
   'Does not include premium type PA
   TotalRegularPremium = DB2.DataItem("LH_POL_TOTALS", "TOT_REG_PRM_AMT").NullZ(1, 0)
End Property

Property Get TotalAdditionalPremium()
   'Only includes premium type PA
   TotalAdditionalPremium = DB2.DataItem("LH_POL_TOTALS", "TOT_ADD_PRM_AMT").NullZ(1, 0)
End Property

Property Get CostBasis()
   CostBasis = DB2.DataItem("LH_POL_TOTALS", "POL_CST_BSS_AMT").NullZ(1, 0)
End Property

Property Get PremiumTD()
  PremiumTD = TotalRegularPremium + TotalAdditionalPremium
End Property

Property Get AccumWithdrawals() As Double
   AccumWithdrawals = DB2.DataItem("LH_POL_TOTALS", "TOT_WTD_AMT").NullZ(1, 0)
End Property

'====================================================================================================================================================================================
'LH_POL_YR_TOT

'====================================================================================================================================================================================

Property Get PolicyTotalsYTDCount()
   PolicyTotalsYTDCount = DB2.DataItem("LH_POL_YR_TOT", "YTD_TOT_PMT_AMT").Count
End Property

Property Get TotalPremiumYTD()
   'These totals are stored by Policy year.  This will return the totals from the last row (current year)
   'This total amount includes all premiums paid - PR, PI and PA
   TotalPremiumYTD = DB2.DataItem("LH_POL_YR_TOT", "YTD_TOT_PMT_AMT").NullZ(PolicyTotalsYTDCount, 0)
End Property

Property Get TotalAdditionalPremiumYTD()
   'These totals are stored by Policy year.  This will return the totals from the last row (current year)
   'This total only includes premium type PA
   TotalAdditionalPremiumYTD = DB2.DataItem("LH_POL_YR_TOT", "YTD_ADD_PRM_AMT").NullZ(PolicyTotalsYTDCount, 0)
End Property

Property Get PremiumYTD()
   PremiumYTD = TotalPremiumYTD
End Property

'====================================================================================================================================================================================
'LH_CSH_VAL_LOAN

'====================================================================================================================================================================================

Property Get TradLoanCount() As Integer
  TradLoanCount = DB2.DataItem("LH_CSH_VAL_LOAN", "LN_PRI_AMT").Count
End Property

Property Get TradLoanEffectiveDate(xcount As Integer) As Date
  TradLoanEffectiveDate = DB2.DataItem("LH_CSH_VAL_LOAN", "MVRY_DT").value(xcount)
End Property

Property Get TradLoanPrefIndicator(xcount As Integer) As String
  TradLoanPrefIndicator = DB2.DataItem("LH_CSH_VAL_LOAN", "PRF_LN_IND").value(xcount)
End Property

Property Get TradLoanAccuredInt(xcount As Integer) As Double
  TradLoanAccuredInt = DB2.DataItem("LH_CSH_VAL_LOAN", "POL_LN_ITS_AMT").value(xcount)
End Property

Property Get TradLoanLoanPrinciple(xcount As Integer) As Double
  TradLoanLoanPrinciple = DB2.DataItem("LH_CSH_VAL_LOAN", "LN_PRI_AMT").value(xcount)
End Property

Property Get TradLoanIntType(xcount As Integer) As Double
  TradLoanIntType = DB2.DataItem("LH_CSH_VAL_LOAN", "LN_ITS_PBL_TYP_CD").value(xcount)
End Property

Property Get TradLoanInterestStatusCode(xcount As Integer) As String
  TradLoanInterestStatusCode = DB2.DataItem("LH_CSH_VAL_LOAN", "LN_ITS_AMT_TYP_CD").value(xcount)
End Property

Property Get TradLoanChargeRate(xcount As Integer) As Double
  TradLoanChargeRate = DB2.DataItem("LH_CSH_VAL_LOAN", "LN_CRG_ITS_RT").value(xcount)
End Property

Property Get TotalTradPrefLnPrinciple()
Dim X As Integer, subtotal As Double
subtotal = 0
For X = 1 To TradLoanCount
 If TradLoanEffectiveDate(X) = CDate("12/31/9999") And TradLoanPrefIndicator(X) = 1 Then subtotal = subtotal + TradLoanLoanPrinciple(X)
Next
TotalTradPrefLnPrinciple = subtotal
End Property

Property Get TotalTradPrefLnAccrued()
Dim X As Integer, subtotal As Double
subtotal = 0
For X = 1 To TradLoanCount
 If TradLoanEffectiveDate(X) = CDate("12/31/9999") And TradLoanPrefIndicator(X) = 1 Then subtotal = subtotal + TradLoanAccuredInt(X)
Next
TotalTradPrefLnAccrued = subtotal
End Property

Property Get TotalTradRegLnPrinciple()
Dim X As Integer, subtotal As Double
subtotal = 0
For X = 1 To TradLoanCount
 If TradLoanEffectiveDate(X) = CDate("12/31/9999") And TradLoanPrefIndicator(X) = 0 Then subtotal = subtotal + TradLoanLoanPrinciple(X)
Next
TotalTradRegLnPrinciple = subtotal
End Property

Property Get TotalTradRegLnAccrued()
Dim X As Integer, subtotal As Double
subtotal = 0
For X = 1 To TradLoanCount
 If TradLoanEffectiveDate(X) = CDate("12/31/9999") And TradLoanPrefIndicator(X) = 0 Then subtotal = subtotal + TradLoanAccuredInt(X)
Next
TotalTradRegLnAccrued = subtotal
End Property

'====================================================================================================================================================================================
'LH_FND_VAL_LOAN

'====================================================================================================================================================================================

Property Get LoanFundCount() As Integer
  LoanFundCount = DB2.DataItem("LH_FND_VAL_LOAN", "MVRY_DT").Count
End Property

Property Get LoanEffectiveDate(xcount As Integer) As Date
  LoanEffectiveDate = DB2.DataItem("LH_FND_VAL_LOAN", "MVRY_DT").value(xcount)
End Property

Property Get LoanFundPhase(xcount As Integer)
  LoanFundPhase = DB2.DataItem("LH_FND_VAL_LOAN", "FND_VAL_PHA_NBR").value(xcount)
End Property

Property Get LoanFundPrefIndicator(xcount As Integer) As String
  LoanFundPrefIndicator = DB2.DataItem("LH_FND_VAL_LOAN", "PRF_LN_IND").value(xcount)
End Property

Property Get LoanFundID(xcount As Integer) As String
  LoanFundID = DB2.DataItem("LH_FND_VAL_LOAN", "FND_ID_CD").value(xcount)
End Property

Property Get LoanFundAccuredInt(xcount As Integer) As Double
  LoanFundAccuredInt = DB2.DataItem("LH_FND_VAL_LOAN", "POL_LN_ITS_AMT").value(xcount)
End Property

Property Get LoanFundPrinciple(xcount As Integer) As Double
  LoanFundPrinciple = DB2.DataItem("LH_FND_VAL_LOAN", "LN_PRI_AMT").value(xcount)
End Property

Property Get LoanFundInterestStatusCode(xcount As Integer) As String
  LoanFundInterestStatusCode = DB2.DataItem("LH_FND_VAL_LOAN", "LN_ITS_AMT_TYP_CD").value(xcount)
End Property

Property Get LoanFundChargeRate(xcount As Integer) As Double
  LoanFundChargeRate = DB2.DataItem("LH_FND_VAL_LOAN", "LN_CRG_ITS_RT").value(xcount)
End Property

Property Get LoanFundIntType(xcount As Integer) As Double
  LoanFundIntType = DB2.DataItem("LH_FND_VAL_LOAN", "LN_ITS_PBL_TYP_CD").value(xcount)
End Property

Property Get TotalFundVarLnAccrued()
Dim X As Integer, subtotal As Double
subtotal = 0
For X = 1 To LoanFundCount                                              'Interest is not Capitalized
 If LoanEffectiveDate(X) = CDate("12/31/9999") And LoanFundID(X) = "LZ" And LoanFundInterestStatusCode(X) <> "1" Then subtotal = subtotal + LoanFundAccuredInt(X)
Next
TotalFundVarLnAccrued = subtotal
End Property

Property Get TotalFundVarLnPrinciple()
Dim X As Integer, subtotal As Double
subtotal = 0
For X = 1 To LoanFundCount
 If LoanEffectiveDate(X) = CDate("12/31/9999") And LoanFundID(X) = "LZ" Then subtotal = subtotal + LoanFundPrinciple(X)
Next
TotalFundVarLnPrinciple = subtotal
End Property

Property Get TotalFundPrefLnPrinciple()
Dim X As Integer, subtotal As Double
subtotal = 0
For X = 1 To LoanFundCount
 If LoanEffectiveDate(X) = CDate("12/31/9999") And LoanFundID(X) <> "LZ" And LoanFundPrefIndicator(X) = 1 Then subtotal = subtotal + LoanFundPrinciple(X)
Next
TotalFundPrefLnPrinciple = subtotal
End Property

Property Get TotalFundPrefLnAccrued()
Dim X As Integer, subtotal As Double
subtotal = 0
For X = 1 To LoanFundCount
 If CDate(LoanEffectiveDate(X)) = CDate("12/31/9999") And LoanFundID(X) <> "LZ" And LoanFundPrefIndicator(X) = 1 And LoanFundInterestStatusCode(X) <> "1" Then subtotal = subtotal + LoanFundAccuredInt(X)
Next
TotalFundPrefLnAccrued = subtotal
End Property

Property Get TotalFundRegLnPrinciple()
Dim X As Integer, subtotal As Double
subtotal = 0
For X = 1 To LoanFundCount
 If CDate(LoanEffectiveDate(X)) = CDate("12/31/9999") And LoanFundID(X) <> "LZ" And LoanFundPrefIndicator(X) = 0 Then subtotal = subtotal + LoanFundPrinciple(X)
Next
TotalFundRegLnPrinciple = subtotal
End Property

Property Get TotalFundRegLnAccrued()
Dim X As Integer, subtotal As Double
subtotal = 0
For X = 1 To LoanFundCount
 If LoanEffectiveDate(X) = CDate("12/31/9999") And LoanFundID(X) <> "LZ" And LoanFundPrefIndicator(X) = 0 And LoanFundInterestStatusCode(X) <> "1" Then subtotal = subtotal + LoanFundAccuredInt(X)
Next
TotalFundRegLnAccrued = subtotal
End Property

Property Get LoanValuesDictionary() As Dictionary
 Dim dct As Dictionary
 Set dct = New Dictionary
 'Create dictionary by summing up loan principle across distinct FundIds only if the bucket is effective on the valuation date
 Dim X As Integer
 For X = 1 To LoanFundCount
    If LoanEffectiveDate(X) = CDate("12/31/9999") Then
        dct(LoanFundID(X)) = dct(LoanFundID(X)) + LoanFundPrinciple(X)
    End If
 Next
 Set LoanValuesDictionary = dct
 Set dct = Nothing
End Property

'=================================================================================================================================================================================================================================================
'LOANS (ADV or TRAD)

'=================================================================================================================================================================================================================================================

Property Get TotalPrefLnPrinciple()
    TotalPrefLnPrinciple = TotalTradPrefLnPrinciple + TotalFundPrefLnPrinciple
'    Dim tempValue
'    If Me.AdvancedProductIndicator = "1" Then
'    'RJH - 4/9/2024:  When an ISWL goes on RPU, the loans are considered trandiation a loans and the cash values are
'    'just the NSP on the 02 segment (no more accumulation value from the 65 segment)
'        If Me.ProductType = "ISWL" And Me.StatusCode = "45" Then
'            tempValue = TotalTradPrefLnPrinciple
'        Else
'            tempValue = TotalFundPrefLnPrinciple
'        End If
'    Else
'        tempValue = TotalTradPrefLnPrinciple
'    End If
'
'    TotalPrefLnPrinciple = tempValue
End Property

Property Get TotalPrefLnAccrued()
    TotalPrefLnAccrued = TotalTradPrefLnAccrued + TotalFundPrefLnAccrued
'    Dim tempValue
'    If Me.AdvancedProductIndicator = "1" Then
'        If Me.ProductType = "ISWL" And Me.StatusCode = "45" Then
'            tempValue = TotalTradPrefLnAccrued
'        Else
'            tempValue = TotalFundPrefLnAccrued
'        End If
'    Else
'        tempValue = TotalTradPrefLnAccrued
'    End If
'    TotalPrefLnAccrued = tempValue
End Property

Property Get TotalRegLnPrinciple()
    TotalRegLnPrinciple = TotalFundRegLnPrinciple + TotalTradRegLnPrinciple
'    Dim tempValue
'    If Me.AdvancedProductIndicator = "1" Then
'        If Me.ProductType = "ISWL" And Me.StatusCode = "45" Then
'            tempValue = TotalTradRegLnPrinciple
'        Else
'            tempValue = TotalFundRegLnPrinciple
'        End If
'    Else
'        tempValue = TotalTradRegLnPrinciple
'    End If
'    TotalRegLnPrinciple = tempValue
End Property

Property Get TotalRegLnAccrued()
    TotalRegLnAccrued = TotalTradRegLnAccrued + TotalFundRegLnAccrued
'    Dim tempValue
'    If Me.AdvancedProductIndicator = "1" Then
'        If Me.ProductType = "ISWL" And Me.StatusCode = "45" Then
'            tempValue = TotalTradRegLnAccrued
'        Else
'            tempValue = TotalFundRegLnAccrued
'        End If
'    Else
'        tempValue = TotalTradRegLnAccrued
'    End If
'    TotalRegLnAccrued = tempValue
End Property

Property Get PolicyDebt()
    Dim tempValue
    If Me.AdvancedProductIndicator = "1" Then
        tempValue = TotalPrefLnPrinciple + TotalPrefLnAccrued + TotalRegLnPrinciple + TotalRegLnAccrued + TotalFundVarLnPrinciple + TotalFundVarLnAccrued
    Else
        tempValue = TotalRegLnPrinciple + TotalRegLnAccrued
    End If
    PolicyDebt = tempValue
End Property

'=================================================================================================================================================================================================================================================
'LH_COM_TARGET

'=================================================================================================================================================================================================================================================

Private Sub LoadComTargets()
 mCovCTPCount = 0
 If DB2.DataItem("LH_COM_TARGET", "TAR_TYP_CD").Count > 0 Then
   Dim X As Integer
   Dim TargetType As String
   Dim tempValue As Variant
   For X = 1 To DB2.DataItem("LH_COM_TARGET", "TAR_TYP_CD").Count
     TargetType = DB2.DataItem("LH_COM_TARGET", "TAR_TYP_CD").value(X)
     Select Case TargetType
        Case "CT":  ReDim Preserve mCovCTP(mCovCTPCount)
                    ReDim Preserve mCovCTPhase(mCovCTPCount)
                    ReDim Preserve mCovCTDate(mCovCTPCount)
                    mCovCTP(mCovCTPCount) = DB2.DataItem("LH_COM_TARGET", "TAR_PRM_AMT").NullZ(X, 0)
                    mCovCTPhase(mCovCTPCount) = DB2.DataItem("LH_COM_TARGET", "AGT_COM_PHA_NBR").value(X)
                    mCovCTDate(mCovCTPCount) = DB2.DataItem("LH_COM_TARGET", "TAR_DT").value(X)
                    mCTP = mCTP + mCovCTP(mCovCTPCount)
                    mCovCTPCount = mCovCTPCount + 1
     End Select
   Next
 End If
 blnLoadComTargets = True
End Sub

Property Get CTPCount() As Integer
  If Not blnLoadComTargets Then LoadComTargets
  CTPCount = mCovCTPCount
End Property

Property Get CTP()
 If Not blnLoadComTargets Then LoadComTargets
 CTP = mCTP
End Property

Property Get CovCTP(Optional Cov As Integer = 1)
 If Not blnLoadComTargets Then LoadComTargets
 CovCTP = mCovCTP(Cov - 1)
End Property

Property Get CovCTPhase(Optional Cov As Integer = 1)
 If Not blnLoadComTargets Then LoadComTargets
 CovCTPhase = mCovCTPhase(Cov - 1)
End Property

Property Get CovCTDate(Optional Cov As Integer = 1)
 If Not blnLoadComTargets Then LoadComTargets
 CovCTDate = mCovCTDate(Cov - 1)
End Property

'====================================================================================================================================================================================
'LH_SST_XTR_CRG

'====================================================================================================================================================================================

Private Function TranslateSubstandardTypeCode(TypeCode As String) As String
  Select Case TypeCode
    Case "0", "1", "3": TranslateSubstandardTypeCode = "T"
    Case "2", "4":  TranslateSubstandardTypeCode = "F"
    Case Else: TranslateSubstandardTypeCode = TypeCode
  End Select
End Function

Private Function ActiveSubstandards(Cov As Integer, TypeAbbr As String, Optional JtIndicator As Integer = 0) As Dictionary
'Returns a dictionary will all the active substandards for the specified coverage, substandard type (table or flat) and person code (primary insured or joint insured)
Dim PersonCode As String
If JtIndicator = 1 Then
    PersonCode = "01"
Else
    PersonCode = "00"
End If
Dim dct As Dictionary
Set dct = New Dictionary
Dim X As Integer, CurrentSubTypeCode, CurrentPhase, CurrentPersonCode, CurrentCeaseDate, CurrentAmount, CurrentAnnualFlat
For X = 1 To DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_TYP_CD").Count
    CurrentSubTypeCode = TranslateSubstandardTypeCode(DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_TYP_CD").value(X))  'T=Table, F=Flat
    CurrentPhase = DB2.DataItem("LH_SST_XTR_CRG", "COV_PHA_NBR").value(X)
    CurrentPersonCode = DB2.DataItem("LH_SST_XTR_CRG", "PRS_CD").value(X)
    CurrentCeaseDate = DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_CEA_DT").value(X)
    If CurrentSubTypeCode = TypeAbbr Then
        If CurrentPhase = CovPhase(Cov) Then
            If CurrentPersonCode = PersonCode Then
                If ValuationDate < CurrentCeaseDate Then
                    If TypeAbbr = "T" Then
                        CurrentAmount = TranslateTable(DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_RT_TBL_CD").value(X))
                        dct.Add dct.Count + 1, CurrentAmount
                    Else
                        CurrentAmount = DB2.DataItem("LH_SST_XTR_CRG", "SST_XTR_UNT_AMT").value(X)
                        CurrentAnnualFlat = DB2.DataItem("LH_SST_XTR_CRG", "XTR_PER_1000_AMT").value(X)
                        dct.Add dct.Count + 1, Array(CurrentAmount, CurrentCeaseDate, CurrentAnnualFlat)
                    End If
                End If
            End If
        End If
    End If
Next
Set ActiveSubstandards = dct
Set dct = Nothing
End Function

Property Get CovTable(Cov As Integer, Optional JtIndicator As Integer = 0)
Dim dct As Dictionary
Set dct = ActiveSubstandards(Cov, "T", JtIndicator)
If dct.Count > 1 Then
    MsgBox "Insured for " & Me.PolicyNumber & " has more than one active table rating on the same coverage"
    Exit Property
End If
If dct.Count = 1 Then
    CovTable = dct(1)
Else
  CovTable = 0
End If
End Property

Property Get CovFlatCount(Cov As Integer)
    CovFlatCount = ActiveSubstandards(Cov, "F").Count
End Property

Property Get CovFlat(Cov As Integer, Optional RatingIndex As Integer = 1)
'Returns the monthly flat extra amount.
'dct(RatingIndex) is an array - (monthly flat, flat CeaseDate, Annual Flat)
'Right now (6/22/2017) no Joint UL policies have flat extra's, so there is no JtIndicator argument for this property
    Dim dct As Dictionary
    Set dct = ActiveSubstandards(Cov, "F")
    If RatingIndex > dct.Count Then
        CovFlat = 0
        Exit Property
    End If
    CovFlat = dct(RatingIndex)(0)
End Property

Property Get CovFlatAnnual(Cov As Integer, Optional RatingIndex As Integer = 1)
'Returns the Annual flat extra amount.
'dct(RatingIndex) is an array - (monthly flat, flat CeaseDate, Annual Flat)
'Right now (6/22/2017) no Joint UL policies have flat extra's, so there is no JtIndicator argument for this property
Dim dct As Dictionary
    Set dct = ActiveSubstandards(Cov, "F")
    If RatingIndex > dct.Count Then
        CovFlatAnnual = 0
        Exit Property
    End If
    CovFlatAnnual = dct(RatingIndex)(2)
End Property

Property Get CovFlatCeaseDate(Cov As Integer, Optional RatingIndex As Integer = 1)
'Returns the flat cease date.
'dct(RatingIndex) is an array - (monthly flat, flat CeaseDate, Annual Flat)
'Right now (6/22/2017) no Joint UL policies have flat extra's, so there is no JtIndicator argument for this property
Dim dct As Dictionary
    Set dct = ActiveSubstandards(Cov, "F")
    If RatingIndex > dct.Count Then
        CovFlatCeaseDate = 0
        Exit Property
    End If
    CovFlatCeaseDate = dct(RatingIndex)(1)   'index 0 = Amount, index 1 = CeaseDate
End Property

'====================================================================================================================================================================================
'LH_FND_ALC

'====================================================================================================================================================================================

Private Sub LoadFundAllocation()
 Dim xcount As Integer, X As Integer, MaxSeq As Integer
 Dim FundID, FundAllocationType, FundAllocationPercent As Variant, FundSeqNumber As Variant
 Set mdctAllocationPercent = New Dictionary
 xcount = DB2.DataItem("LH_FND_ALC", "FND_ID_CD").Count
     If xcount > 0 Then
        MaxSeq = FindMaxValue("LH_FND_ALC", "FND_ALC_SEQ_NBR", xcount)
        For X = 1 To xcount
            FundID = DB2.DataItem("LH_FND_ALC", "FND_ID_CD").value(X)
            'U1, IX, IC, IS, IF, SW
            FundAllocationType = DB2.DataItem("LH_FND_ALC", "FND_ALC_TYP_CD").value(X)
            'C = Charge deduction
            'P = Payment allocation
            'V = Indexed Fund Reinvestment
            FundSeqNumber = DB2.DataItem("LH_FND_ALC", "FND_ALC_SEQ_NBR").value(X)
            FundAllocationPercent = DB2.DataItem("LH_FND_ALC", "FND_ALC_PCT").value(X)
            If FundAllocationType = "P" And FundSeqNumber = MaxSeq Then mdctAllocationPercent(FundID) = FundAllocationPercent
        Next
    End If
blnLoadFundAllocation = True
End Sub

Property Get PremiumAllocationPercentages() As Dictionary
 If Not blnLoadFundAllocation Then LoadFundAllocation
 Set PremiumAllocationPercentages = mdctAllocationPercent
End Property

Private Function FindMaxValue(strTable As String, strField As String, xcount As Integer) As Variant
Dim tempval
    If xcount = 0 Then
        tempval = Empty
    Else
        'FND_ALC_SEQ_NBR
        tempval = DB2.DataItem(strTable, strField).value(1)
        Dim X As Integer
        For X = 2 To xcount
            If tempval < DB2.DataItem(strTable, strField).value(X) Then tempval = DB2.DataItem(strTable, strField).value(X)
        Next
    End If
    FindMaxValue = tempval
End Function
'Property Get FixedReallocationPercent()
' If Not blnLoadFundAllocation Then LoadFundAllocation
' FixedReallocationPercent = mFixedReallocationPercent
'End Property
'Property Get IndexReallocationPercent()
' If Not blnLoadFundAllocation Then LoadFundAllocation
' IndexReallocationPercent = mIndexReallocationPercent
'End Property
'Property Get SweepReallocationPercent()
' If Not blnLoadFundAllocation Then LoadFundAllocation
' SweepReallocationPercent = mSweepReallocationPercent
'End Property

'====================================================================================================================================================================================
'LH_POL_FND_VAL_TOT

'====================================================================================================================================================================================

Private Sub LoadFundBucketValues()
 Set mdctFundValues = New Dictionary
 If DB2.DataItem("LH_POL_FND_VAL_TOT", "FND_ID_CD").Count Then
   Dim xcount As Integer
   xcount = DB2.DataItem("LH_POL_FND_VAL_TOT", "FND_ID_CD").Count
   Dim BucketIndex As Integer
   Dim BucketID As String
   Dim BucketValue As Double
   Dim BucketStartDate As Date
   Dim BucketMVDate As Date
   BucketIndex = 0
   Dim X As Integer
   For X = 1 To xcount
     ReDim Preserve mFundBucketID(BucketIndex)
     ReDim Preserve mFundBucketMVDate(BucketIndex)
     ReDim Preserve mFundBucketStartDate(BucketIndex)
     ReDim Preserve mFundBucketEndDate(BucketIndex)
     ReDim Preserve mFundBucketValue(BucketIndex)
     ReDim Preserve mFundBucketPhaseCode(BucketIndex)
     BucketID = DB2.DataItem("LH_POL_FND_VAL_TOT", "FND_ID_CD").NullZ(X, 0)
     BucketValue = DB2.DataItem("LH_POL_FND_VAL_TOT", "CSV_AMT").NullZ(X, 0)
     BucketStartDate = DB2.DataItem("LH_POL_FND_VAL_TOT", "ITS_PER_STR_DT").NullZ(X, 0)
     BucketMVDate = DB2.DataItem("LH_POL_FND_VAL_TOT", "MVRY_DT").NullZ(X, 0)
     Select Case BucketID
     'When listing all the current funds, only include the Index funds that havent matured yet and have non-zero value
       Case "IX", "IC", "IF", "IC":
       'If maturity date has not occured yet then add bucket to array matrix
       'Assumes index funds mature in one year.
         If DateAdd("Y", 1, BucketStartDate) > Me.MVDate Or BucketValue <> 0 Then
           mFundBucketID(BucketIndex) = BucketID
           mFundBucketMVDate(BucketIndex) = BucketMVDate
           mFundBucketStartDate(BucketIndex) = BucketStartDate
           mFundBucketPhaseCode(BucketIndex) = DB2.DataItem("LH_POL_FND_VAL_TOT", "FND_VAL_PHA_NBR").NullZ(X, 0)
           mFundBucketValue(BucketIndex) = BucketValue
           BucketIndex = BucketIndex + 1
         End If
       Case Else:
       'All non-Index funds are included (U1, LN, SW...)
         mFundBucketID(BucketIndex) = BucketID
         mFundBucketMVDate(BucketIndex) = BucketMVDate
         mFundBucketStartDate(BucketIndex) = BucketStartDate
         mFundBucketPhaseCode(BucketIndex) = DB2.DataItem("LH_POL_FND_VAL_TOT", "FND_VAL_PHA_NBR").NullZ(X, 0)
         mFundBucketValue(BucketIndex) = BucketValue
         BucketIndex = BucketIndex + 1
     End Select
   Next
 End If
mFundBucketCount = BucketIndex
blnLoadFundBucketValues = True
End Sub

Property Get FundBucketCount() As Integer
 If Not blnLoadFundBucketValues Then LoadFundBucketValues
 FundBucketCount = mFundBucketCount
End Property

Property Get FundBucketPhaseCode(X As Integer) As Integer
 If Not blnLoadFundBucketValues Then LoadFundBucketValues
 FundBucketPhaseCode = mFundBucketPhaseCode(X - 1)
End Property

Property Get FundBucketID(X As Integer) As String
 If Not blnLoadFundBucketValues Then LoadFundBucketValues
 FundBucketID = mFundBucketID(X - 1)
End Property

Property Get FundBucketMVDate(X As Integer) As Date
 If Not blnLoadFundBucketValues Then LoadFundBucketValues
 FundBucketMVDate = mFundBucketMVDate(X - 1)
End Property

Property Get FundBucketStartDate(X As Integer) As Date
 If Not blnLoadFundBucketValues Then LoadFundBucketValues
 FundBucketStartDate = mFundBucketStartDate(X - 1)
End Property

Property Get FundBucketEndDate(X As Integer) As Date
 If Not blnLoadFundBucketValues Then LoadFundBucketValues
 FundBucketEndDate = mFundBucketEndDate(X - 1)
End Property

Property Get FundBucketValue(X As Integer) As Double
 If Not blnLoadFundBucketValues Then LoadFundBucketValues
 FundBucketValue = mFundBucketValue(X - 1)
End Property

Property Get FundValuesDictionary() As Dictionary
 If Not blnLoadFundBucketValues Then LoadFundBucketValues
 Dim dctFundValues As Dictionary
 Set dctFundValues = New Dictionary
 'Create dictionary by summing up fund values across distinct fund ids only if the bucket is effective on the valuation date
 Dim X As Integer
 Dim l
 For X = 1 To mFundBucketCount
    If CDate(Me.FundBucketMVDate(X)) = CDate("12/31/9999") Then
        dctFundValues(Me.FundBucketID(X)) = dctFundValues(Me.FundBucketID(X)) + Me.FundBucketValue(X)    'Fixed on 05/17/2019 RJH
    End If
 Next
 Set FundValuesDictionary = dctFundValues
 Set dctFundValues = Nothing
End Property

'====================================================================================================================================================================================
'TH_USER_GENERIC

'====================================================================================================================================================================================

Property Get GenericCount()
  GenericCount = DB2.DataItem("TH_USER_GENERIC", "CK_CMP_CD").Count
End Property

Property Get Rein_Partner(Optional X As Integer = 1)
'11/13/2024 - This field was created originally to identify the policies in Cyberlife that were part of the RGA Orion deal
  Rein_Partner = Trim(DB2.DataItem("TH_USER_GENERIC", "FUZGREIN_IND").value(X))
End Property

'====================================================================================================================================================================================
'VH_POL_HAS_LOC_CLT & LH_CTT_CLIENT

'====================================================================================================================================================================================

Property Get PersonCount()
  PersonCount = DB2.DataItem("VH_POL_HAS_LOC_CLT", "PRS_CD").Count
End Property

Property Get PersonPrefix(X As Integer)
  PersonPrefix = Trim(DB2.DataItem("VH_POL_HAS_LOC_CLT", "CK_NM_PFX").value(X))
End Property

Property Get PersonSuffix(X As Integer)
  PersonSuffix = Trim(DB2.DataItem("VH_POL_HAS_LOC_CLT", "CK_NM_SFX").value(X))
End Property

Property Get PersonFirstName(X As Integer)
  PersonFirstName = Trim(DB2.DataItem("VH_POL_HAS_LOC_CLT", "CK_FST_NM").value(X))
End Property

Property Get PersonLastName(X As Integer)
  PersonLastName = Trim(DB2.DataItem("VH_POL_HAS_LOC_CLT", "CK_LST_NM").value(X))
End Property

Property Get PersonEffectiveDate(X As Integer)
  PersonEffectiveDate = DB2.DataItem("LH_CTT_CLIENT", "EFF_DT").value(X)
End Property

Property Get PersonBirthDay(X As Integer)
  PersonBirthDay = DB2.DataItem("LH_CTT_CLIENT", "BIR_DT").value(X)
End Property

Property Get PersonClass(X As Integer)
  PersonClass = DB2.DataItem("LH_CTT_CLIENT", "OCP_CLS_CD").value(X)
End Property

Property Get PersonGender(X As Integer)
  PersonGender = DB2.DataItem("LH_CTT_CLIENT", "GENDER_CD").value(X)
End Property

Property Get PersonAge(X As Integer)
  PersonAge = DB2.DataItem("LH_CTT_CLIENT", "INS_AGE").value(X)
End Property

Property Get PersonCode(X As Integer)
  PersonCode = DB2.DataItem("LH_CTT_CLIENT", "PRS_CD").value(X)
End Property

Property Get OwnerCode(X As Integer)
  OwnerCode = DB2.DataItem("LH_CTT_CLIENT", "OWN_CD").value(X)
End Property

Property Get PersonSequenceCode(X As Integer)
  PersonSequenceCode = DB2.DataItem("LH_CTT_CLIENT", "PRS_SEQ_NBR").value(X)
End Property

Property Get IsJointInsured() As Boolean
  Dim tempValue As Boolean
  tempValue = False
  Dim X As Integer
  For X = 1 To PersonCount
    If PersonCode(X) = "01" Then tempValue = True
  Next
  IsJointInsured = tempValue
End Property

'====================================================================================================================================================================================
'LH_CTT_COM_PHA_WA

'====================================================================================================================================================================================

Property Get AgentCount()
  AgentCount = DB2.DataItem("LH_CTT_COM_PHA_WA", "WRT_AGT_NM").Count
End Property

Property Get Agent(Optional X As Integer = 1)
  Agent = DB2.DataItem("LH_CTT_COM_PHA_WA", "WRT_AGT_NM").NullZ(X, "")
End Property

'====================================================================================================================================================================================
'LH_COV_TARGET

'====================================================================================================================================================================================

Property Get CCV() As Variant
Dim subtotal As Variant
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_COV_TARGET", "TAR_TYP_CD").Count
     If DB2.DataItem("LH_COV_TARGET", "TAR_TYP_CD").value(X) = "XP" Then
       subtotal = subtotal + DB2.DataItem("LH_COV_TARGET", "TAR_PRM_AMT").value(X)
     End If
   Next
CCV = subtotal
End Property

Property Get SurrenderTarget(Optional CovIndex As Integer = 1) As Variant
Dim tempValue As Variant
tempValue = -1
Dim X As Integer
   For X = 1 To DB2.DataItem("LH_COV_TARGET", "TAR_TYP_CD").Count
    If DB2.DataItem("LH_COV_TARGET", "COV_PHA_NBR").value(X) = CovPhase(CovIndex) Then
        If DB2.DataItem("LH_COV_TARGET", "TAR_TYP_CD").value(X) = "ST" Then
            tempValue = DB2.DataItem("LH_COV_TARGET", "TAR_PRM_AMT").value(X)
            Exit For
        End If
     End If
   Next
SurrenderTarget = tempValue
End Property
'Property Get GAV()
' If Not blnLoadCovTarget Then LoadCovTarget
' GAV = mGAV
'End Property

'====================================================================================================================================================================================
'LH_TAMRA_7_PY_PER & LH_TAMRA_7_PY_YR

'====================================================================================================================================================================================

Property Get NoTAMRAValues() As Boolean
 NoTAMRAValues = DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_LVL_PRM_AMT").FieldNotFound
End Property

Property Get TAMRA_7PayLevel() As Variant
   TAMRA_7PayLevel = DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_LVL_PRM_AMT").NullZ(1, 0)
End Property

Property Get TAMRA_7PayStartDate() As Variant
   TAMRA_7PayStartDate = DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_PER_STR_DT").NullZ(1, 0)
End Property

Property Get MEC_Indicator() As String
   MEC_Indicator = DB2.DataItem("LH_TAMRA_7_PY_PER", "MEC_STA_CD").NullZ(1, "")
End Property

Property Get CountOf1035Payments() As Variant
   CountOf1035Payments = DB2.DataItem("LH_TAMRA_7_PY_PER", "XCG_1035_PMT_QTY").NullZ(1, 0)
End Property

Property Get TAMRA_7PayAV() As Variant
  TAMRA_7PayAV = DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_BEG_CSV_AMT").value
End Property

Property Get TAMRA_7PaySpecifiedAmount() As Variant
  TAMRA_7PaySpecifiedAmount = DB2.DataItem("LH_TAMRA_7_PY_PER", "SVPY_BEG_FCE_AMT").NullZ(1, 0)
End Property

Property Get TAMRA_7PayPremiumPaid(Yr As Integer) As Variant
  TAMRA_7PayPremiumPaid = DB2.DataItem("LH_TAMRA_7_PY_YR", "SVPY_PRM_PAY_AMT").value(Yr)
End Property

Property Get TAMRA_7PayWithdrawal(Yr As Integer) As Variant
  TAMRA_7PayWithdrawal = DB2.DataItem("LH_TAMRA_7_PY_YR", "SVPY_WTD_AMT").value(Yr)
End Property

'====================================================================================================================================================================================
'LH_TRD_POL

'====================================================================================================================================================================================

Property Get TRAD_Count() As Variant
  TRAD_Count = DB2.DataItem("LH_TRD_POL", "ACU_PRM_AMT").Count
End Property

Property Get TRAD_AccumulatedPremium() As Variant
  TRAD_AccumulatedPremium = DB2.DataItem("LH_TRD_POL", "ACU_PRM_AMT").value
End Property

'====================================================================================================================================================================================
'FH_FIXED

'====================================================================================================================================================================================

Property Get TransactionCount()
  TransactionCount = DB2.DataItem("FH_FIXED", "ASOF_DT").Count
End Property

Property Get TransactionRevInd(X As Integer)
  TransactionRevInd = DB2.DataItem("FH_FIXED", "FCB0_REV_IND").value(X)
End Property

Property Get TransactionRevApplied(X As Integer)
  TransactionRevApplied = DB2.DataItem("FH_FIXED", "FCB2_REV_APPL_IND").value(X)
End Property

Property Get TransactionFundID(X As Integer)
  TransactionFundID = DB2.DataItem("FH_FIXED", "FUND_ID").value(X)
End Property

Property Get TransactionSequence(X As Integer)
  TransactionSequence = DB2.DataItem("FH_FIXED", "SEQ_NO").value(X)
End Property

Property Get TransactionDate(X As Integer)
  TransactionDate = DB2.DataItem("FH_FIXED", "ASOF_DT").value(X)
End Property

Property Get TransactionFundPhase(X As Integer)
  TransactionFundPhase = DB2.DataItem("FH_FIXED", "FNDVAL_PH").value(X)
End Property

Property Get TransactionType(X As Integer)
  TransactionType = DB2.DataItem("FH_FIXED", "TRANS").value(X)
End Property

Property Get TransactionNetAmount(X As Integer)
  TransactionNetAmount = DB2.DataItem("FH_FIXED", "NET_AMT").value(X)
End Property

Property Get TransactionGrossAmount(X As Integer)
  TransactionGrossAmount = DB2.DataItem("FH_FIXED", "GROSS_AMT").value(X)
End Property

Property Get TransactionEntryDate(X As Integer)
  TransactionEntryDate = DB2.DataItem("FH_FIXED", "ENTRY_DT").value(X)
End Property

Property Get TransactionInterestRate(X As Integer)
  TransactionInterestRate = DB2.DataItem("FH_FIXED", "INT_RT").value(X)
End Property

Property Get TransactionOrigin(X As Integer) As String
  TransactionOrigin = DB2.DataItem("FH_FIXED", "ORIGIN_OF_TRANS").value(X)
End Property

'====================================================================================================================================================================================
'LH_APPLIED_PTP & LH_UNAPPLIED_PTP

'====================================================================================================================================================================================

Property Get AppliedDivCount() As Integer
  AppliedDivCount = DB2.DataItem("LH_APPLIED_PTP", "CK_PTP_TYP_CD").Count
End Property

Property Get AppliedDivCovPhase(X As Integer) As String
  AppliedDivCovPhase = DB2.DataItem("LH_APPLIED_PTP", "COV_PHA_NBR").value(X)
End Property

Property Get AppliedDivType(X As Integer) As String
  AppliedDivType = DB2.DataItem("LH_APPLIED_PTP", "CK_PTP_TYP_CD").value(X)
End Property

Property Get AppliedDivAnniversaryIndicator(X As Integer) As String
  AppliedDivAnniversaryIndicator = DB2.DataItem("LH_APPLIED_PTP", "PTP_ANV_PRC_IND").value(X)
End Property

Property Get AppliedDivInterestRate(X As Integer) As String
  AppliedDivInterestRate = DB2.DataItem("LH_APPLIED_PTP", "DIV_GRS_ITS_RT").value(X)
End Property

Property Get AppliedDivEarnDate(X As Integer) As Double
  AppliedDivEarnDate = DB2.DataItem("LH_APPLIED_PTP", "ERN_DT_MO_YR_NBR").value(X)
End Property

Property Get AppliedDivAppliedOption(X As Integer) As String
  AppliedDivAppliedOption = DB2.DataItem("LH_APPLIED_PTP", "APP_OPT_CD").value(X)
End Property

Property Get AppliedDivFromPUA(X As Integer) As String
  AppliedDivFromPUA = DB2.DataItem("LH_APPLIED_PTP", "PTP_SRC_IND").value(X)
End Property

Property Get AppliedDivPUAUnits(X As Integer) As Double
  AppliedDivPUAUnits = DB2.DataItem("LH_APPLIED_PTP", "PUA_UNT_QTY").value(X)
End Property

Property Get AppliedDivCashAmount(X As Integer) As Double
  AppliedDivCashAmount = DB2.DataItem("LH_APPLIED_PTP", "CSH_AMT").value(X)
End Property

Property Get AppliedDivPUAAmount(X As Integer) As String
  AppliedDivPUAAmount = DB2.DataItem("LH_APPLIED_PTP", "PUA_AMT").value(X)
End Property

Property Get AppliedDivOYTAmount(X As Integer) As String
  AppliedDivOYTAmount = DB2.DataItem("LH_APPLIED_PTP", "OYT_AMT").value(X)
End Property

Property Get UnappliedDivCount() As Integer
  UnappliedDivCount = DB2.DataItem("LH_UNAPPLIED_PTP", "CK_PTP_TYP_CD").Count
End Property

Property Get UnappliedDivCovPhase(X As Integer) As String
  UnappliedDivCovPhase = DB2.DataItem("LH_UNAPPLIED_PTP", "COV_PHA_NBR").value(X)
End Property

Property Get UnappliedDivDate(X As Integer) As String
  UnappliedDivDate = DB2.DataItem("LH_UNAPPLIED_PTP", "ERN_DT_MO_YR_NBR").value(X)
End Property

Property Get UnappliedDivType(X As Integer) As String
  UnappliedDivType = DB2.DataItem("LH_UNAPPLIED_PTP", "CK_PTP_TYP_CD").value(X)
End Property

Property Get UnappliedDivFromPUA(X As Integer) As String
  UnappliedDivFromPUA = DB2.DataItem("LH_UNAPPLIED_PTP", "PTP_SRC_IND").value(X)
End Property

Property Get UnappliedDivOnDepositInterestRate(X As Integer) As Double
  UnappliedDivOnDepositInterestRate = DB2.DataItem("LH_UNAPPLIED_PTP", "DEP_ITS_RT").value(X)
End Property

Property Get UnappliedDivFromRPU(X As Integer) As Double
  UnappliedDivFromRPU = DB2.DataItem("LH_UNAPPLIED_PTP", "RPU_VAL_IND").value(X)
End Property

Property Get UnappliedDivTermination(X As Integer) As String
  UnappliedDivTermination = DB2.DataItem("LH_UNAPPLIED_PTP", "TMN_DIV_IND").value(X)
End Property

Property Get UnappliedDivCashRate(X As Integer) As Double
  UnappliedDivCashRate = DB2.DataItem("LH_UNAPPLIED_PTP", "CSH_AMT").value(X)
End Property

Property Get UnappliedDivProjectedCashRate(X As Integer) As Double
  UnappliedDivProjectedCashRate = DB2.DataItem("LH_UNAPPLIED_PTP", "PRJ_CSH_AMT").value(X)
End Property

Property Get UnappliedDivPUAMortality(X As Integer) As String
  UnappliedDivPUAMortality = DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_MTL_TBL_CD").value(X)
End Property

Property Get UnappliedDivPUAInterestRate(X As Integer) As Double
  UnappliedDivPUAInterestRate = DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_ITS_RT").value(X)
End Property

Property Get UnappliedDivPUAUnits(X As Integer) As Double
  UnappliedDivPUAUnits = DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_UNT_QTY").value(X)
End Property

Property Get UnappliedDivPUARate(X As Integer) As Double
  UnappliedDivPUARate = DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_AMT").value(X)
End Property

Property Get UnappliedDivPUAMaturityDuration(X As Integer) As Integer
  UnappliedDivPUAMaturityDuration = DB2.DataItem("LH_UNAPPLIED_PTP", "PUA_MT_DUR").value(X)
End Property

Property Get UnappliedDivOYTRate(X As Integer) As Double
  UnappliedDivOYTRate = DB2.DataItem("LH_UNAPPLIED_PTP", "OYT_AMT").value(X)
End Property

Property Get UnappliedDivOYTMortality(X As Integer) As String
  UnappliedDivOYTMortality = DB2.DataItem("LH_UNAPPLIED_PTP", "OYT_MTL_TBL_CD").value(X)
End Property

Property Get UnappliedDivOYTInterestRate(X As Integer) As Double
  UnappliedDivOYTInterestRate = DB2.DataItem("LH_UNAPPLIED_PTP", "OYT_ITS_RT").value(X)
End Property

'====================================================================================================================================================================================
'LH_ONE_YR_TRM_ADD

'====================================================================================================================================================================================

Property Get DivOYTCount() As Integer
   DivOYTCount = DB2.DataItem("LH_ONE_YR_TRM_ADD", "MVRY_DT").Count
End Property

Property Get DivOYTDate(X As Integer) As Date
   DivOYTDate = DB2.DataItem("LH_ONE_YR_TRM_ADD", "MVRY_DT").value(X)
End Property

Property Get DivOYTMortality(X As Integer) As String
   DivOYTMortality = DB2.DataItem("LH_ONE_YR_TRM_ADD", "OYT_MTL_TBL_CD").value(X)
End Property

Property Get DivOYTInterestRate(X As Integer) As Double
   DivOYTInterestRate = DB2.DataItem("LH_ONE_YR_TRM_ADD", "OYT_ITS_RT").value(X)
End Property

Property Get DivOYTClassCode(X As Integer) As Double
   DivOYTClassCode = DB2.DataItem("LH_ONE_YR_TRM_ADD", "OYT_CLS_CD").value(X)  'FDCINTPW-INTEREST-PREV-WTHDRW
End Property

Property Get DivOYTAmount(X As Integer) As Double
   DivOYTAmount = DB2.DataItem("LH_ONE_YR_TRM_ADD", "OYT_ADD_AMT").value(X)
End Property

Property Get DivOYTExpiryDate(X As Integer) As Integer
 'Function returns number of months from 1/1/1900
   DivOYTExpiryDate = DB2.DataItem("LH_ONE_YR_TRM_ADD", "OYT_EXP_MO_YR_NBR").value(X)
End Property

Property Get DivOYTAnniversaryProcessIndicator(X As Integer) As String
   DivOYTAnniversaryProcessIndicator = DB2.DataItem("LH_ONE_YR_TRM_ADD", "ANV_PRC_CRN_IND").value(X)
End Property

Property Get DivOYTCurrent() As Double
Dim X As Integer, subtotal As Double
For X = 1 To DivOYTCount
   If DivOYTDate(X) = CDate("12/31/9999") Then
        subtotal = subtotal + DivOYTAmount(X)
   End If
Next
   DivOYTCurrent = subtotal
End Property

'====================================================================================================================================================================================
'LH_PAID_UP_ADD

'====================================================================================================================================================================================

Property Get DivPUACount() As Integer
   DivPUACount = DB2.DataItem("LH_PAID_UP_ADD", "MVRY_DT").Count
End Property

Property Get DivPUADate(X As Integer) As Date
   DivPUADate = DB2.DataItem("LH_PAID_UP_ADD", "MVRY_DT").value(X)
End Property

Property Get DivPUAMaturityDate(X As Integer) As Integer
'Function returns number of months from 1/1/1900
   DivPUAMaturityDate = DB2.DataItem("LH_PAID_UP_ADD", "PUA_MT_MO_YR_NBR").value(X)
End Property

Property Get DivPUACovPhase(X As Integer) As String
   DivPUACovPhase = DB2.DataItem("LH_PAID_UP_ADD", "COV_PHA_NBR").value(X)
End Property

Property Get DivPUAClassCode(X As Integer) As Double
   DivPUAClassCode = DB2.DataItem("LH_PAID_UP_ADD", "PUA_CLS_CD").value(X)
End Property

Property Get DivPUAMortality(X As Integer) As String
   DivPUAMortality = DB2.DataItem("LH_PAID_UP_ADD", "PUA_MTL_TBL_CD").value(X)
End Property

Property Get DivPUAInterestRate(X As Integer) As Double
   DivPUAInterestRate = DB2.DataItem("LH_PAID_UP_ADD", "PUA_ITS_RT").value(X)
End Property

Property Get DivPUAAmount(X As Integer) As Double
   DivPUAAmount = DB2.DataItem("LH_PAID_UP_ADD", "PUA_AMT").value(X)
End Property

Property Get DivPUAFundingSource(X As Integer) As String
   DivPUAFundingSource = DB2.DataItem("LH_PAID_UP_ADD", "PUA_PUR_SRC_CD").value(X)
End Property

Property Get DivPUACurrent() As Double
Dim X As Integer, subtotal As Double
For X = 1 To DivPUACount
   If DivPUADate(X) = CDate("12/31/9999") Then
        subtotal = subtotal + DivPUAAmount(X)
   End If
Next
   DivPUACurrent = subtotal
End Property

'====================================================================================================================================================================================
'LH_PTP_ON_DEP

'====================================================================================================================================================================================

Property Get DivDepositCount() As Integer
   DivDepositCount = DB2.DataItem("LH_PTP_ON_DEP", "MVRY_DT").Count
End Property

Property Get DivDepositLastAnniversary(X As Integer) As Date
   DivDepositLastAnniversary = DB2.DataItem("LH_PTP_ON_DEP", "MVRY_DT").value(X)
End Property

Property Get DivDepositInterestDate(X As Integer) As Integer
   DivDepositInterestDate = DB2.DataItem("LH_PTP_ON_DEP", "ITS_APP_MO_YR_NBR").value(X)
End Property

Property Get DivDepositInterestRate(X As Integer) As Double
   DivDepositInterestRate = DB2.DataItem("LH_PTP_ON_DEP", "DEP_ITS_RT").value(X)
End Property

Property Get DivDepositAmount(X As Integer) As Double
   DivDepositAmount = DB2.DataItem("LH_PTP_ON_DEP", "PTP_DEP_AMT").value(X)
End Property

Property Get DivDepositInterestOnWDs(X As Integer) As Double
   DivDepositInterestOnWDs = DB2.DataItem("LH_PTP_ON_DEP", "PRE_WTD_ITS_AMT").value(X) 'FDCINTPW-INTEREST-PREV-WTHDRW
End Property

Property Get DivDepositAccumInterestWithheld(X As Integer) As Double
   DivDepositAccumInterestWithheld = DB2.DataItem("LH_PTP_ON_DEP", "ACU_ITS_WHD_AMT").NullZ(1, 0)
End Property

Property Get DivDepositCurrent() As Double
Dim X As Integer, subtotal As Double
For X = 1 To DivDepositCount
   If DivDepositLastAnniversary(X) = CDate("12/31/9999") Then
        subtotal = subtotal + DivDepositAmount(X)
   End If
Next
   DivDepositCurrent = subtotal
End Property

'====================================================================================================================================================================================
'Rates

'====================================================================================================================================================================================

Public Function RATES_COI(CovIndex As Integer, Optional intScale As Integer = 1) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(CovIndex)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(CovIndex)
    End Select
    If IsEmpty(CovBand(CovIndex)) Then
        RATES_COI = Empty
    Else
        RATES_COI = oRates.Rates("COI", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), intScale, CovBand(CovIndex))
    End If
End Function

Public Function RATES_MTP(CovIndex As Integer) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(CovIndex)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(CovIndex)
    End Select
    If IsEmpty(CovBand(CovIndex)) Then
        RATES_MTP = Empty
    Else
        Dim temp
        temp = oRates.Rates("MTP", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), , CovBand(CovIndex))
        If IsEmpty(temp) Then
            RATES_MTP = "NA"
        Else
            RATES_MTP = oRates.Rates("MTP", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), , CovBand(CovIndex))(1)
        End If
    End If
End Function

Public Function RATES_CTP(CovIndex As Integer) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(CovIndex)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(CovIndex)
    End Select
    If IsEmpty(CovBand(CovIndex)) Then
        RATES_CTP = Empty
    Else
        Dim temp
        temp = oRates.Rates("CTP", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), , CovBand(CovIndex))
        If IsEmpty(temp) Then
            RATES_CTP = "NA"
        Else
            RATES_CTP = oRates.Rates("CTP", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), , CovBand(CovIndex))(1)
        End If
    End If
End Function

Public Function RATES_TBL1MTP(CovIndex As Integer) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(CovIndex)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(CovIndex)
    End Select
    If IsEmpty(CovBand(CovIndex)) Then
        RATES_TBL1MTP = Empty
    Else
        Dim temp
        temp = oRates.Rates("TBL1MTP", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), , CovBand(CovIndex))
        If IsEmpty(temp) Then
            RATES_TBL1MTP = "NA"
        Else
            RATES_TBL1MTP = oRates.Rates("TBL1MTP", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), , CovBand(CovIndex))(1)
        End If
    End If
End Function

Public Function RATES_TBL1CTP(CovIndex As Integer) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(CovIndex)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(CovIndex)
    End Select
    If IsEmpty(CovBand(CovIndex)) Then
        RATES_TBL1CTP = Empty
    Else
        Dim temp
        temp = oRates.Rates("TBL1CTP", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), , CovBand(CovIndex))
        If IsEmpty(temp) Then
            RATES_TBL1CTP = "NA"
        Else
            RATES_TBL1CTP = oRates.Rates("TBL1CTP", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), , CovBand(CovIndex))(1)
        End If
    End If
End Function

Public Function RATES_EPU(CovIndex As Integer, Optional intScale As Integer = 1) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(CovIndex)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(CovIndex)
    End Select
    If IsEmpty(CovBand(CovIndex)) Then
        RATES_EPU = Empty
    Else
        RATES_EPU = oRates.Rates("EPU", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), intScale, CovBand(CovIndex))
    End If
End Function

Public Function RATES_SCR(CovIndex As Integer, Optional intScale As Integer = 1) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(CovIndex)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(CovIndex)
    End Select
    If IsEmpty(CovBand(CovIndex)) Then
        RATES_SCR = Empty
    Else
        RATES_SCR = oRates.Rates("SCR", CovPlancode(CovIndex), CovIssueAge(CovIndex), sSex, CovRateclass(CovIndex), intScale, CovBand(CovIndex))
    End If
End Function

Public Function CovBand(CovIndex As Integer) As Variant
    If Not dctBand.exists(CovIndex) Then dctBand(CovIndex) = oRates.Band(CovPlancode(CovIndex), Me.TotalSpecifiedAmount)
    CovBand = dctBand(CovIndex)
End Function

Public Function RATES_CORR() As Variant
    RATES_CORR = oRates.Rates("CORR", CovPlancode(1), CovIssueAge(1))
End Function

Public Function RATES_GINT() As Variant
    RATES_GINT = oRates.Rates("GINT", CovPlancode(1))
End Function

Public Function RATES_EPP(intScale As Integer) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(1)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(1)
    End Select
    If IsEmpty(CovBand(1)) Then
        RATES_EPP = Empty
    Else
        RATES_EPP = oRates.Rates("EPP", CovPlancode(1), CovIssueAge(1), sSex, CovRateclass(1), intScale, CovBand(1))
    End If
End Function

Public Function RATES_TPP(intScale As Integer) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(1)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(1)
    End Select
    If IsEmpty(CovBand(1)) Then
        RATES_TPP = Empty
    Else
        RATES_TPP = oRates.Rates("TPP", CovPlancode(1), CovIssueAge(1), sSex, CovRateclass(1), intScale, CovBand(1))
    End If
End Function

Public Function RATES_MFEE(intScale As Integer) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(1)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(1)
    End Select
    If IsEmpty(CovBand(1)) Then
        RATES_MFEE = Empty
    Else
        RATES_MFEE = oRates.Rates("MFEE", CovPlancode(1), CovIssueAge(1), sSex, CovRateclass(1), intScale, CovBand(1))
    End If
End Function

Public Function RATES_BENCOI(BenIndex As Integer, Optional intScale As Integer = 1) As Variant
    Dim sSex As String
    Select Case Me.RenewalCovSexCode(1)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(1)
    End Select
    If IsEmpty(CovBand(1)) Then
        RATES_BENCOI = Empty
    Else
       RATES_BENCOI = oRates.Rates("BENCOI", CovPlancode(1), BenIssueAge(BenIndex), sSex, Me.CovRateclass(1), intScale, CovBand(1), , Me.BenPlancode(BenIndex))
    End If
End Function

Public Function RATES_BENCTP(BenIndex As Integer) As Variant
    Dim sSex As String, temparray
    Select Case Me.RenewalCovSexCode(1)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(1)
    End Select
    If IsEmpty(CovBand(1)) Then
        RATES_BENCTP = Empty
    Else
        temparray = oRates.Rates("BENCTP", CovPlancode(1), Me.BenIssueAge(BenIndex), sSex, CovRateclass(1), , CovBand(1), , Me.BenPlancode(BenIndex))
        If IsEmpty(temparray) Then
          RATES_BENCTP = Empty
        Else
            RATES_BENCTP = temparray(1)
        End If
    End If
End Function

Public Function RATES_BENMTP(BenIndex As Integer) As Variant
    Dim sSex As String, temparray
    Select Case Me.RenewalCovSexCode(1)
        Case "1": sSex = "M"
        Case "2": sSex = "F"
        Case Else: sSex = Me.RenewalCovSexCode(1)
    End Select
    If IsEmpty(CovBand(1)) Then
        RATES_BENMTP = Empty
    Else
        temparray = oRates.Rates("BENMTP", CovPlancode(1), Me.BenIssueAge(BenIndex), sSex, CovRateclass(1), , CovBand(1), , Me.BenPlancode(BenIndex))
        If IsEmpty(temparray) Then
          RATES_BENMTP = Empty
        Else
            RATES_BENMTP = temparray(1)
        End If
    End If
End Function
