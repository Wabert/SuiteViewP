' Module: mdlGlobals.bas
' Type: Standard Module
' Stream Path: VBA/mdlGlobals
' =========================================================

Attribute VB_Name = "mdlGlobals"
Public Enum pdDataSource
   ULRates
   CKPR
   CKMO
   CKAS
   CKCS
   CKSR
End Enum
 

 
Public Enum eTransactionType
    Withdrawals
    LoanPayments
    Premiums
    Loans
    DBOptChange
    FaceChange
    RateclassChange
    TableChange
    FlatChange
    FlatCeaseDateChange
    AllocationChange
    [_Last]
End Enum

Public Enum eCovType
    Base
    Rider
    Benefit
End Enum

Public Enum eBenefitType
    PWoC
    PWoT
    GIO
    CCV
    ADnD
    ADB
End Enum


Public Enum eMode
    Lumpsum
    BiWeekly
    SemiMonthly
    Monthly
    Quarterly
    SemiAnnually
    Annually
End Enum

Public Enum ePeriodicTransactionParameters
    TransactionType
    StartDate
    StopDate
    Mode
    value
End Enum

Public Enum ePolicyChangeTypes
    DBOption
    SpecifiedAmount
    Rateclass
    TableRating
    Flat1
    Flat1Cease
    Flat2
    Flat2Cease
End Enum

 '======================================  Start InforceFile ===========================================
'Type udtFunds
'    U1 As udtFund   'General Fund
'    IC As udtFund   'Point to Point with 1.5% floor
'    IS As udtFund   'Point to Point with specified rate
'    IX As udtFund   'Point to Point with Cap
'    IF As udtFund   'Point to Point no Cap, with fee
'    SW As udtFund   'Sweep account
'    LN As udtFund   'Loan collateral from Index funds
'End Type
'Type udtBenefits
'    PWoC As udtBenefit
'    PWoT As udtBenefit
'    GIO As udtBenefit
'    ADnD As udtBenefit
'    ADB As udtBenefit
'    CCV As udtBenefit
'End Type

Type udtTransactions
    TransactionType() As eTransactionType
    StartDate() As Date
    StopDate() As Date
    Mode() As String
    value() As Variant
    CovType() As Variant
    CovIndex() As Variant
End Type

Type udtBenefit
    Mnemonic As String
    Plancode As String 'This is the Type and Subtype code
    IssueAge As Integer
    IssueDate As Date
    CeaseDate As Date
    Amount As Double
    TableRating As Integer
    OriginalCeaseDate As Date
End Type



Type udtCalculationSettings
    Plus1DayInt As Boolean
    ExactDays As Boolean
    PremiumCap As String
    CreditLeapDay As Boolean
End Type

Type udtCoverage
    IncreaseCode As String
    Plancode As String
    IssueDate As Date
    MaturityDate As Date
    Amount As Double
    OrigAmount As Double
    IssueAge As Integer
    Sex As String
    Rateclass As String
    TableRating As Integer
    Flat As Double
    FlatAnnual As Double
    FlatCeaseDate As Date
    Flat2 As Double
    Flat2Annual As Double
    Flat2CeaseDate As Date
    Qualified As Boolean
    PersonCoveredCode As String
    InsuredName As String
    TerminationDate As Variant
End Type

Type udtFund
    FundID As String
    FundName As String
    IsIndexed As Boolean
    value As Double
    CreditRate As Single
    AllocationPercent As Single
    Cap As Single
    Floor As Single
    SpecifedRate As Single
End Type

Type udtPolicyValues
    PolicyYear As Integer
    AttainedAge As Integer
    StatusCode As String
    DBOption As String
    IssueState As String
    PlannedPremium As Double
    PlannedMode As String
    InGrace As Boolean
    GPE_Date As Date
    ValuationDate As Date
    MonthsTerminated As Integer
    AV As Double
    AV_Type As String
    CCVAV As Double
    PrefFxLnPrinicple As Double
    PrefFxLnAccrued As Double
    RegFxLnPrinicple As Double
    RegFxLnAccrued As Double
    VarLnPrinicple As Double
    VarLnAccrued As Double
    PremiumsYTD As Double
    PremiumsTD As Double
    CostBasis As Double
    GLP As Double
    GSP As Double
    AccumGLP As Double
    PolicyMTP As Double
    PolicyCTP As Double
    PolicyLTP As Double
    AccumMTP As Double
    AccumWD As Double
    TamraStartDate As Date
    TAMRA_7PayLevel As Double
    MEC_Indicator As String
    TAMRA_Premium_1 As Double
    TAMRA_Premium_2 As Double
    TAMRA_Premium_3 As Double
    TAMRA_Premium_4 As Double
    TAMRA_Premium_5 As Double
    TAMRA_Premium_6 As Double
    TAMRA_Premium_7 As Double
    TAMRA_Withdrawal_1 As Double
    TAMRA_Withdrawal_2 As Double
    TAMRA_Withdrawal_3 As Double
    TAMRA_Withdrawal_4 As Double
    TAMRA_Withdrawal_5 As Double
    TAMRA_Withdrawal_6 As Double
    TAMRA_Withdrawal_7 As Double
End Type
      
Type udtPolicyFile
    PolicyValues As udtPolicyValues
    CalculationSettings As udtCalculationSettings
'    Transactions As udtTransactions
    BaseCovs() As udtCoverage
    RiderCovs() As udtCoverage
    Benefits() As udtBenefit
    Funds() As udtFund
End Type

 '======================================  End InforceFile ===========================================

Dim oRates As cls_Rates
Dim blnInitialized As Boolean
Global glbUnlock As Boolean


Private Sub InitialModule()
    Set oRates = New cls_Rates
End Sub
Public Function GetRatesObject() As cls_Rates
    If Not blnInitialized Then InitialModule
    Set GetRatesObject = oRates
End Function
Public Function eTransactionDescription(TransactionType As eTransactionType) As String
Dim tempval
    Select Case TransactionType
        Case eTransactionType.Premiums:  tempval = "Premium Payments"
        Case eTransactionType.LoanPayments:  tempval = "Loan Payments"
        Case eTransactionType.Loans:  tempval = "Loans"
        Case eTransactionType.Withdrawals:  tempval = "Withdrawals"
        Case Else: tempval = "Cannot find transaction type"
    End Select
    eTransactionDescription = tempval
End Function

Public Function eBenefitMnemonic(BenefitType As eBenefitType) As String
Dim tempval
    Select Case BenefitType
        Case eBenefitType.ADB:  tempval = "ADB"
        Case eBenefitType.ADnD:  tempval = "ADnD"
        Case eBenefitType.CCV:  tempval = "CCV"
        Case eBenefitType.GIO:  tempval = "GIO"
        Case eBenefitType.PWoC:  tempval = "PWoC"
        Case eBenefitType.PWoT:  tempval = "PWoT"
        Case Else: tempval = "Cannot find benefit type"
    End Select
    eBenefitMnemonic = tempval
End Function
Public Function eBenefitDescription(BenefitType As eBenefitType) As String
Dim tempval
    Select Case TransactionType
        Case eBenefitType.ADB:  tempval = "Accidental Death Benefit"
        Case eBenefitType.ADnD:  tempval = "Accidental Death and Dismemberment"
        Case eBenefitType.CCV:  tempval = "Secondary Guarantee Account"
        Case eBenefitType.GIO:  tempval = "Guaranteed Increase Option"
        Case eBenefitType.PWoC:  tempval = "Premium Waiver of Cost"
        Case eBenefitType.PWoT:  tempval = "Premium Waiver of Target"
        Case Else: tempval = "Cannot find benefit type"
    End Select
    eBenefitDescription = tempval
End Function



