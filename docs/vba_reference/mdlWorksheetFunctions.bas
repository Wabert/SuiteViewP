' Module: mdlWorksheetFunctions.bas
' Type: Standard Module
' Stream Path: VBA/mdlWorksheetFunctions
' =========================================================

Attribute VB_Name = "mdlWorksheetFunctions"
Option Explicit

Private dctSpreadsheetPolicies As Dictionary
Private blnInitialized As Boolean
Private mSpreadsheetFunctionsActive As Boolean

Private Sub InitalizeSpreadsheetPolicies()
 Set dctSpreadsheetPolicies = New Dictionary
 blnInitialized = True
 mSpreadsheetFunctionsActive = True
 
End Sub
Private Function GetSpreadsheetPolicy(strPolicyNumber As String, strDataSource As String, Optional strCompanyCode As String = "01", Optional strSystemCode As String = "I")
Dim skey As String
skey = MakePolicyKey(strPolicyNumber, strDataSource, strCompanyCode, strSystemCode)
  If Not dctSpreadsheetPolicies.exists(skey) Then
    Dim NewPolicy As cls_PolicyInformation
    Set NewPolicy = New cls_PolicyInformation
    NewPolicy.classInitialize strPolicyNumber, strDataSource, strCompanyCode, strSystemCode
    dctSpreadsheetPolicies.Add skey, NewPolicy
    Set NewPolicy = Nothing
  End If
Set GetSpreadsheetPolicy = dctSpreadsheetPolicies(skey)
End Function
'Public Sub SpreadsheetFunctionsActiveToggle(Optional blnActive As Variant)
'  'If blnActive is missing then just toggle mSpreadsheetFunctionsActive to opposite of what it currently is
'  If IsMissing(blnActive) Then
'    mSpreadsheetFunctionsActive = Not mSpreadsheetFunctionsActive
'  Else
'    mSpreadsheetFunctionsActive = blnActive
'  End If
'
'  'Update icon based on value of mSpreadsheetFunctionsActive
'  If mSpreadsheetFunctionsActive Then
'     SetSpreadsheetFunctionButtonFaceID 2087
'  Else
'     SetSpreadsheetFunctionButtonFaceID 477
'  End If
'
'End Sub
Public Function ClearSpreadsheetPolicies() As Variant
   Set dctSpreadsheetPolicies = Nothing
   blnInitialized = False
  ClearSpreadsheetPolicies = "Complete"
End Function
Private Function SpreadsheetPolicies() As Dictionary
    Set SpreadsheetPolicies = dctSpreadsheetPolicies
End Function
Public Function DB2ValueCount(strPolicyNumber As String, sTable As String, sField As String, Optional strCompanyCode, Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I") As Variant
'    If Not mSpreadsheetFunctionsActive Then
'     DB2ValueCount = "Functions not active"
'     Exit Function
'    End If
   
    If Not blnInitialized Then InitalizeSpreadsheetPolicies
    Dim pol As cls_PolicyInformation
    Set pol = GetSpreadsheetPolicy(strPolicyNumber, strDataSource, strCompanyCode, strSystemCode)
    DB2ValueCount = pol.DB2Data.DataItem(sTable, sField).Count
End Function
Public Function DB2Value(strPolicyNumber As String, sTable As String, sField As String, Optional Indx As Integer = 1, Optional strCompanyCode, Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I") As Variant
'    If Not mSpreadsheetFunctionsActive Then
'     DB2Value = "Functions not active"
'     Exit Function
'    End If
   
    If Not blnInitialized Then InitalizeSpreadsheetPolicies
    Dim pol As cls_PolicyInformation
    Set pol = GetSpreadsheetPolicy(strPolicyNumber, strDataSource, strSystemCode)
    DB2Value = pol.DB2Data.DataItem(sTable, sField).value(Indx)
End Function
Public Function DB2IndexSearch(strPolicyNumber As String, sTable As String, sField As String, SearchValue As Variant, Optional strCompanyCode, Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I") As Variant
    
'    If Not mSpreadsheetFunctionsActive Then
'     DB2IndexSearch = "Functions not active"
'     Exit Function
'    End If

    If Not blnInitialized Then InitalizeSpreadsheetPolicies
    Dim pol As cls_PolicyInformation
    Set pol = GetSpreadsheetPolicy(strPolicyNumber, strDataSource, strCompanyCode, strSystemCode)
    
    Dim xIndx As Integer
    xIndx = -1
    Dim X As Integer
    For X = 1 To pol.DB2Data.DataItem(sTable, sField).Count
        If pol.DB2Data.DataItem(sTable, sField).value(X) = SearchValue Then
            xIndx = X
            Exit For
        End If
    Next
    
    
    DB2IndexSearch = xIndx
End Function




'==============================  GetPolicyData  =================================================

Public Function GetPolicyData(strData As String, strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I", Optional JtIndicator As Integer = 0)

'If Not mSpreadsheetFunctionsActive Then
' GetPolicyData = "Functions not active"
' Exit Function
'End If
Dim dI As cls_PolicyDataItem

strPolicyNumber = UCase(strPolicyNumber)

If Not blnInitialized Then InitalizeSpreadsheetPolicies

Dim pol As cls_PolicyInformation
Set pol = GetSpreadsheetPolicy(strPolicyNumber, strDataSource, strCompanyCode, strSystemCode)
 
                             
 
'If there is no data for the policy (ie the policy does not exist in the region) then return error message
If dctSpreadsheetPolicies(pol.PolicyKey).PolicyNotFound Then
    GetPolicyData = "Error:  Policy " & strPolicyNumber & " does not exist in " & strDataSource
    Exit Function
End If

Select Case strData
 Case "FundBucketCount": GetPolicyData = pol.FundBucketCount
 Case "ValuationDate": GetPolicyData = pol.ValuationDate
 Case "TotalSpecifiedAmount": GetPolicyData = pol.TotalSpecifiedAmount
 Case "TotalOrinSpecifiedAmount": GetPolicyData = pol.TotalOrinSpecifiedAmount
 'Case "SweepAV": GetPolicyData = Pol.SweepAV
 Case "Suspense": GetPolicyData = pol.SuspenseText
 Case "Status": GetPolicyData = pol.StatusCode

 Case "PremiumYTD": GetPolicyData = pol.PremiumYTD
 Case "PremiumTD": GetPolicyData = pol.PremiumTD
 
 Case "PrefLnPrinciple": GetPolicyData = pol.TotalPrefLnPrinciple
 Case "PrefLnAccrued": GetPolicyData = pol.TotalPrefLnAccrued
 
 Case "RegLnPrinciple": GetPolicyData = pol.TotalRegLnPrinciple
 Case "RegLnAccrued": GetPolicyData = pol.TotalRegLnAccrued
  
 Case "VarLnPrinciple": GetPolicyData = pol.TotalFundVarLnPrinciple
 Case "VarLnAccrued": GetPolicyData = pol.TotalFundVarLnAccrued
 
 Case "PolicyDebt": GetPolicyData = pol.PolicyDebt  'Policy debt is all the loans added together in one amount.  This will return total outstanding loan on a UL or tradional policy
 
 Case "PolicyID": GetPolicyData = pol.PolicyID
 Case "OtherChrg": GetPolicyData = pol.MVOtherChrg
 Case "NAR": GetPolicyData = pol.MVNAR
 Case "MTP": GetPolicyData = pol.MTP
 Case "IssueState": GetPolicyData = pol.IssueStateAbbr
 Case "ResidentState": GetPolicyData = pol.ResidentStateAbbr
 Case "InGrace": GetPolicyData = pol.InGrace
 'Case "IndexAV": GetPolicyData = Pol.IndexAV
 'Case "IndexAllocationPercent": GetPolicyData = Pol.IndexAllocationPercent
 Case "GSP": GetPolicyData = pol.GSP
 'Case "GraceAV": GetPolicyData = Pol.GraceAV
 Case "GLP": GetPolicyData = pol.GLP
 'Case "GeneralAV": GetPolicyData = Pol.GeneralAV
 'Case "FixedAllocationPercent": GetPolicyData = Pol.FixedAllocationPercent
 Case "ExpChrg": GetPolicyData = pol.MVExpChrg
 Case "DBOption": GetPolicyData = pol.DBOption
 Case "CTP": GetPolicyData = pol.CTP
 Case "CovVPU": GetPolicyData = pol.CovVPU(Indx)
 Case "CovCOI": GetPolicyData = pol.CovCOI(Indx)
 Case "CovUnits": GetPolicyData = pol.CovUnits(Indx)
 Case "CovTable": GetPolicyData = pol.CovTable(Indx, JtIndicator)
 Case "CovSex": GetPolicyData = pol.CovSex(Indx, JtIndicator)
 Case "CovRateclass": GetPolicyData = pol.CovRateclass(Indx, JtIndicator)
 Case "CovPlancode": GetPolicyData = pol.CovPlancode(Indx)
 Case "CovPlancodeList": GetPolicyData = pol.CovPlancodeList
 Case "CovOrinUnits": GetPolicyData = pol.CovOrinUnits(Indx)
 Case "CovOrigAmount": GetPolicyData = pol.CovOrigAmount(Indx)
 Case "CovIssueDate": GetPolicyData = pol.CovIssueDate(Indx)
 Case "CovIssueAge": GetPolicyData = pol.CovIssueAge(Indx, JtIndicator)

 'Case "CovPersonSuffix": GetPolicyData = Pol.CovPersonSuffix(indx)
 'Case "CovPersonPrefix": GetPolicyData = Pol.CovPersonPrefix(indx)
 'Case "CovPersonLastName": GetPolicyData = Pol.CovPersonLastName(indx)
 'Case "CovPersonFirstName": GetPolicyData = Pol.CovPersonFirstName(indx)
 Case "CovGrossFlat2": GetPolicyData = pol.CovFlat(Indx, 2)
 Case "CovGrossFlat1": GetPolicyData = pol.CovFlat(Indx, 1)
 'Case "CovBand":        GetPolicyData = Pol.CovBand(indx)
 'Case "CovBandAmount":        GetPolicyData = Pol.CovBandAmount(indx)
 Case "CovFormNumber": GetPolicyData = pol.CovFormNumber(Indx)
 Case "CovFlat2CeaseDate": GetPolicyData = pol.CovFlatCeaseDate(Indx, 2)
 Case "CovFlat2": GetPolicyData = pol.CovFlat(Indx, 2)
 Case "CovFlat1CeaseDate": GetPolicyData = pol.CovFlatCeaseDate(Indx, 1)
 Case "CovFlat1": GetPolicyData = pol.CovFlat(Indx, 1)
 Case "CovCTP": GetPolicyData = pol.CovCTP(Indx)
 Case "CovCount": GetPolicyData = pol.CovCount
 Case "CovMaturityDate": GetPolicyData = pol.CovMaturityDate(Indx)
 Case "CovAmount": GetPolicyData = pol.CovAmount(Indx)
 'Case "CovDuration": GetPolicyData = Pol.CovDuration(indx)
 Case "CovAgeCalcCode": GetPolicyData = pol.CovAgeCalcCode(Indx)
 Case "CovProductLineCode": GetPolicyData = pol.CovProductLineCode(Indx)
 Case "CovMortalityTableCode": GetPolicyData = pol.CovMortalityTableCode(Indx)
 Case "CostBasis": GetPolicyData = pol.CostBasis
 Case "BenVPU": GetPolicyData = pol.BenVPU(Indx)
 Case "BenUnits": GetPolicyData = pol.BenUnits(Indx)
 Case "BenPlancode": GetPolicyData = pol.BenPlancode(Indx)
 Case "BenIssueDate": GetPolicyData = pol.BenIssueDate(Indx)
 Case "BenIssueAge": GetPolicyData = pol.BenIssueAge(Indx)
 Case "BenFormNumber": GetPolicyData = pol.BenFormNumber(Indx)
 Case "BenCount": GetPolicyData = pol.BenCount
 Case "BenCeaseDate": GetPolicyData = pol.BenCeaseDate(Indx)
 Case "BenAmount": GetPolicyData = pol.BenAmount(Indx)
 Case "BenRatingFactor": GetPolicyData = pol.BenRatingFactor(Indx)
 Case "BenPlancodeList": GetPolicyData = pol.BenList
 Case "AV": GetPolicyData = pol.MVAV
 Case "TradCV": GetPolicyData = pol.TradCashValue
 Case "Agent": GetPolicyData = pol.Agent
 Case "AccumMTP": GetPolicyData = pol.AccumMTP
 Case "AccumGLP": GetPolicyData = pol.AccumGLP
 Case "CCV":  GetPolicyData = pol.CCV
 Case "BillMode": GetPolicyData = pol.BillMode
 Case "BillPremium": GetPolicyData = pol.BillPremium
 Case "BillModeCode": GetPolicyData = pol.BillModeCode
 Case "MonthlyDeduction": GetPolicyData = pol.MVMonthlyDeduction
 Case "CovCOLA": GetPolicyData = pol.CovCOLAIndicator(Indx)
 Case "CompanyCode": GetPolicyData = pol.CompanyCode
 Case "SurrenderTarget": GetPolicyData = pol.SurrenderTarget(Indx)
 Case "PolicyYear": GetPolicyData = pol.PolicyYear
 Case "ForcedPremiumIndicator": GetPolicyData = pol.ForcedPremiumIndicator
 Case "PaidToDate": GetPolicyData = pol.PremiumDatePaidTo
 Case "BillToDate": GetPolicyData = pol.PremiumDateBillTo
 Case "BillFormCode": GetPolicyData = pol.BillFormCode
 Case "CovRenewalRate": GetPolicyData = pol.RenewalCovRate(Indx)
 Case "BenCOIRate": GetPolicyData = pol.BenCOIRate(Indx)
 Case "ServicingBranchOrAgencyCode": GetPolicyData = pol.ServicingBranchOrAgencyCode
 Case "ServicingAgentNumber": GetPolicyData = pol.ServicingAgentNumber
 Case "ServicingMarketOrganization": GetPolicyData = pol.ServicingMarketOrganization
 Case "AgencyBranch": GetPolicyData = pol.AgencyBranch
 Case "LastEntryCode": GetPolicyData = pol.LastEntryCode
 Case "OriginalEntryCode": GetPolicyData = pol.OriginalEntryCode
 Case "LastFinancialDate": GetPolicyData = pol.LastFinancialDate
 Case "Rein_Partner": GetPolicyData = pol.Rein_Partner
 Case "ExchangePolicy":
                            Set dI = pol.DB2Data.DataItem("TH_USER_GENERIC", "EXCH_POL_NUMBER")
                            GetPolicyData = Trim(dI.value)
 Case "ExchangeCode":
                            Set dI = pol.DB2Data.DataItem("TH_USER_GENERIC", "EXCHANGE")
                            GetPolicyData = Trim(dI.value)

 Case "CovCeaseDate": GetPolicyData = pol.CovCeaseDate(Indx)
 Case "MDO": GetPolicyData = pol.MDO
 Case "LastAnniversary": GetPolicyData = pol.LastAnniversary
 Case Else: GetPolicyData = "Not working"
End Select


Set pol = Nothing

End Function


'=================================================================================================================================================================
'  Policy Data
'=================================================================================================================================================================
Public Function Rein_Partner(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
Rein_Partner = GetPolicyData("Rein_Partner", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function

Public Function LastEntryCode(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
LastEntryCode = GetPolicyData("LastEntryCode", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function OriginalEntryCode(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
OriginalEntryCode = GetPolicyData("OriginalEntryCode", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function LastFinancialDate(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
LastFinancialDate = GetPolicyData("LastFinancialDate", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function ServicingMarketOrganization(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 ServicingMarketOrganization = GetPolicyData("ServicingMarketOrganization", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function AgencyBranch(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 AgencyBranch = GetPolicyData("AgencyBranch", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function ServicingAgentNumber(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 ServicingAgentNumber = GetPolicyData("ServicingAgentNumber", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function ServicingBranchOrAgencyCode(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 ServicingBranchOrAgencyCode = GetPolicyData("ServicingBranchOrAgencyCode", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function PolicyYear(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 PolicyYear = GetPolicyData("PolicyYear", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CompanyCode(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CompanyCode = GetPolicyData("CompanyCode", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovCOLA(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovCOLA = GetPolicyData("CovCOLA", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function Status(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  Status = GetPolicyData("Status", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function Suspense(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 Suspense = GetPolicyData("Suspense", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function IssueState(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 IssueState = GetPolicyData("IssueState", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function ResidentState(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 ResidentState = GetPolicyData("ResidentState", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function PolicyID(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 PolicyID = GetPolicyData("PolicyID", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function MTP(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  MTP = GetPolicyData("MTP", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function AccumMTP(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
   AccumMTP = GetPolicyData("AccumMTP", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function GSP(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
   GSP = GetPolicyData("GSP", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function AccumGLP(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  AccumGLP = GetPolicyData("AccumGLP", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovSex(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I", Optional JtIndicator As Integer = 0)
   CovSex = GetPolicyData("CovSex", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode, JtIndicator)
End Function
Public Function CovUnits(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovUnits = GetPolicyData("CovUnits", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovOrinUnits(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovOrinUnits = GetPolicyData("CovOrinUnits", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovVPU(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovVPU = GetPolicyData("CovVPU", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovAmount(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovAmount = GetPolicyData("CovAmount", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovCOI(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovCOI = GetPolicyData("CovCOI", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovOrigAmount(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovOrigAmount = GetPolicyData("CovOrigAmount", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovIssueAge(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I", Optional JtIndicator As Integer = 0)
 CovIssueAge = GetPolicyData("CovIssueAge", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode, JtIndicator)
End Function
Public Function CovIssueDate(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovIssueDate = GetPolicyData("CovIssueDate", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovAgeCalcCode(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovAgeCalcCode = GetPolicyData("CovAgeCalcCode", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovMaturityDate(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovMaturityDate = GetPolicyData("CovMaturityDate", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovCeaseDate(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovCeaseDate = GetPolicyData("CovCeaseDate", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovFormNumber(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovFormNumber = GetPolicyData("CovFormNumber", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovProductLineCode(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovProductLineCode = GetPolicyData("CovProductLineCode", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovPlancode(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovPlancode = GetPolicyData("CovPlancode", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovPlancodeList(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovPlancodeList = GetPolicyData("CovPlancodeList", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function TotalSpecifiedAmount(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  TotalSpecifiedAmount = GetPolicyData("TotalSpecifiedAmount", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function TotalOrinSpecifiedAmount(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 TotalOrinSpecifiedAmount = GetPolicyData("TotalOrinSpecifiedAmount", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovCount(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovCount = GetPolicyData("CovCount", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovMortalityTableCode(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovMortalityTableCode = GetPolicyData("CovMortalityTableCode", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenUnits(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  BenUnits = GetPolicyData("BenUnits", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenVPU(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  BenVPU = GetPolicyData("BenVPU", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenAmount(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 BenAmount = GetPolicyData("BenAmount", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenRatingFactor(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 BenRatingFactor = GetPolicyData("BenRatingFactor", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenIssueAge(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  BenIssueAge = GetPolicyData("BenIssueAge", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenIssueDate(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  BenIssueDate = GetPolicyData("BenIssueDate", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenCeaseDate(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  BenCeaseDate = GetPolicyData("BenCeaseDate", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenFormNumber(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  BenFormNumber = GetPolicyData("BenFormNumber", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenPlancode(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 BenPlancode = GetPolicyData("BenPlancode", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenPlancodeList(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 BenPlancodeList = GetPolicyData("BenPlancodeList", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenCount(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 BenCount = GetPolicyData("BenCount", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BenCOIRate(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
    BenCOIRate = GetPolicyData("BenCOIRate", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function GLP(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  GLP = GetPolicyData("GLP", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function AV(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 AV = GetPolicyData("AV", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function TradCV(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 TradCV = GetPolicyData("TradCV", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function ExpChrg(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 ExpChrg = GetPolicyData("ExpChrg", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function OtherChrg(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 OtherChrg = GetPolicyData("OtherChrg", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function NAR(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 NAR = GetPolicyData("NAR", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function ValuationDate(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 ValuationDate = GetPolicyData("ValuationDate", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovRateclass(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I", Optional JtIndicator As Integer = 0)
  CovRateclass = GetPolicyData("CovRateclass", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode, JtIndicator)
End Function
Public Function InGrace(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  InGrace = GetPolicyData("InGrace", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function DBOption(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  DBOption = GetPolicyData("DBOption", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CostBasis(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CostBasis = GetPolicyData("CostBasis", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function PremiumYTD(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 PremiumYTD = GetPolicyData("PremiumYTD", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function PremiumTD(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  PremiumTD = GetPolicyData("PremiumTD", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function PrefLnPrinciple(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  PrefLnPrinciple = GetPolicyData("PrefLnPrinciple", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function PrefLnAccrued(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  PrefLnAccrued = GetPolicyData("PrefLnAccrued", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function RegLnPrinciple(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 RegLnPrinciple = GetPolicyData("RegLnPrinciple", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function RegLnAccrued(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 RegLnAccrued = GetPolicyData("RegLnAccrued", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function VarLnPrinciple(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 VarLnPrinciple = GetPolicyData("VarLnPrinciple", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function VarLnAccrued(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 VarLnAccrued = GetPolicyData("VarLnAccrued", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function

Public Function PolicyDebt(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  PolicyDebt = GetPolicyData("PolicyDebt", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CTP(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CTP = GetPolicyData("CTP", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovCTP(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovCTP = GetPolicyData("CovCTP", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovRenewalRate(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovRenewalRate = GetPolicyData("CovRenewalRate", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovTable(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I", Optional JtIndicator As Integer = 0)
 CovTable = GetPolicyData("CovTable", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode, JtIndicator)
End Function
Public Function CovFlat1(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovFlat1 = GetPolicyData("CovFlat1", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovGrossFlat1(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
CovGrossFlat1 = GetPolicyData("CovGrossFlat1", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovFlat1CeaseDate(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovFlat1CeaseDate = GetPolicyData("CovFlat1CeaseDate", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovFlat2(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovFlat2 = GetPolicyData("CovFlat2", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovGrossFlat2(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovGrossFlat2 = GetPolicyData("CovGrossFlat2", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovFlat2CeaseDate(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovFlat2CeaseDate = GetPolicyData("CovFlat2CeaseDate", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function FixedAllocationPercent(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  FixedAllocationPercent = GetPolicyData("FixedAllocationPercent", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function IndexAllocationPercent(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 IndexAllocationPercent = GetPolicyData("IndexAllocationPercent", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function GeneralAV(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 GeneralAV = GetPolicyData("GeneralAV", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function IndexAV(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 IndexAV = GetPolicyData("IndexAV", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function SweepAV(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 SweepAV = GetPolicyData("IndexAV", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function GraceAV(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 GraceAV = GetPolicyData("GraceAV", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovPersonPrefix(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovPersonPrefix = GetPolicyData("CovPersonPrefix", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovPersonSuffix(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovPersonSuffix = GetPolicyData("CovPersonSuffix", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovPersonFirstName(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CovPersonFirstName = GetPolicyData("CovPersonFirstName", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CovPersonLastName(strPolicyNumber As String, Optional Indx As Integer = 1, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
  CovPersonLastName = GetPolicyData("CovPersonLastName", strPolicyNumber, Indx, strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function Agent(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 Agent = GetPolicyData("Agent", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function CCV(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 CCV = GetPolicyData("CCV", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BillMode(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 BillMode = GetPolicyData("BillMode", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BillPremium(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 BillPremium = GetPolicyData("BillPremium", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BillModeCode(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 BillModeCode = GetPolicyData("BillModeCode", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function BillFormCode(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 BillFormCode = GetPolicyData("BillFormCode", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function MonthlyDeduction(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 MonthlyDeduction = GetPolicyData("MonthlyDeduction", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function SurrenderTarget(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 SurrenderTarget = GetPolicyData("SurrenderTarget", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function ForcedPremiumIndicator(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 ForcedPremiumIndicator = GetPolicyData("ForcedPremiumIndicator", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function PaidToDate(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 PaidToDate = GetPolicyData("PaidToDate", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function ExchangePolicy(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 ExchangePolicy = GetPolicyData("ExchangePolicy", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function ExchangeCode(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 ExchangeCode = GetPolicyData("ExchangeCode", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function MDO(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 MDO = GetPolicyData("MDO", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
Public Function LastAnniversary(strPolicyNumber As String, Optional strCompanyCode As String = "01", Optional strDataSource As String = "CKPR", Optional strSystemCode As String = "I")
 LastAnniversary = GetPolicyData("LastAnniversary", strPolicyNumber, , strCompanyCode, strDataSource, strSystemCode)
End Function
