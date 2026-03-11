' Module: mdlDataItemSupport.bas
' Type: Standard Module
' Stream Path: VBA/mdlDataItemSupport
' =========================================================

Attribute VB_Name = "mdlDataItemSupport"
Option Explicit



Public Function MakePolicyKey(strPolicyNumber As String, strDataSource As String, Optional strCompanyCode As String = "01", Optional strSystemCode As String = "I") As String
    MakePolicyKey = strCompanyCode & "_" & UCase(Application.WorksheetFunction.Trim(strPolicyNumber)) & "_" & strDataSource & "_" & strSystemCode
End Function

Public Function TranslateFunctionCodeToText(vntCode As Variant) As String
Dim tempValue As Variant

Select Case CStr(vntCode)
  Case "0": tempValue = "Curtate"
  Case "1": tempValue = "Semicontinuous"
  Case "2": tempValue = "Fully continuous"
  Case "3": tempValue = "Discounted continuous"
  Case Else: tempValue = vntCode
End Select
TranslateFunctionCodeToText = tempValue
End Function

Public Function RenewalRateTypeDictionary(vntCode As Variant) As String
Dim tempValue As Variant

Select Case CStr(vntCode)
  Case "M": tempValue = "MinTarg"
  Case "T": tempValue = "CommTarg"
  Case "W": tempValue = "SurrTarg"
  Case "L": tempValue = "PremTarg"
  Case "C": tempValue = "CovCOI"
  Case "B": tempValue = "BenCOI"
  Case Else: tempValue = vntCode
End Select

RenewalRateTypeDictionary = tempValue
End Function

Public Function MarketDictionary() As Dictionary
Dim dct As Dictionary
Dim subdct As Dictionary

Set dct = New Dictionary
Set subdct = New Dictionary

Set subdct = New Dictionary
subdct.Add "FFL", "1"
dct.Add "FFL", subdct

Set subdct = New Dictionary
subdct.Add "MLM", "1"
subdct.Add "IMG", "7"
subdct.Add "DIRECT", "D"
dct.Add "ANICO NY", subdct

Set subdct = New Dictionary
subdct.Add "MLM", "1"
subdct.Add "CSSD", "2"
subdct.Add "IMG", "7"
subdct.Add "DIRECT", "D"
dct.Add "ANICO", subdct

Set subdct = New Dictionary
subdct.Add "GSL", "GSL"
dct.Add "GSL", subdct

Set subdct = New Dictionary
subdct.Add "ANTEX", "1"
dct.Add "ANTEX", subdct

Set subdct = New Dictionary
subdct.Add "SLAICO", "1"
dct.Add "SLAICO", subdct


Set MarketDictionary = dct

Set dct = Nothing
Set subdct = Nothing
End Function

Public Function CompanyMarketOrgsDictionary() As Dictionary

Dim dctMain As Dictionary
Dim dct As Dictionary

Set dctMain = New Dictionary
Set dct = New Dictionary


'Market Orgs available for company ANICO
dct.Add "MLM", "1"
dct.Add "CSSD", "2"
dct.Add "IMG", "7"
dct.Add "DIRECT", "D"
dctMain.Add "01", dct

'Market Orgs available for company ANICONY
dct.RemoveAll
dct.Add "MLM", "1"
dct.Add "IMG", "7"
dct.Add "DIRECT", "D"
dctMain.Add "30", dct

dct.RemoveAll
dct.Add "ANTEX1", "1"
dct.Add "ANTEX6", "6"
dctMain.Add "04", dct

dct.RemoveAll
dct.Add "SLAICO", "1"
dctMain.Add "06", dct

dct.RemoveAll
dct.Add "GSL", "GSL"
dctMain.Add "08", dct

dct.RemoveAll
dct.Add "FFL", "1"
dctMain.Add "26", dct


Set CompanyMarketOrgsDictionary = dctMain


End Function

Public Function DetermineMarketOrgCode(MarketOrgAbbr As String)
Dim tempValue As String

Select Case MarketOrgAbbr
    Case "MLM": tempValue = "1"
    Case "CSSD": tempValue = "2"
    Case "IMG": tempValue = "7"
    Case "DIRECT": tempValue = "D"
    Case "ANTEX":    tempValue = "1"  ' or "6"
    Case "SLAICO":    tempValue = "1"
    Case "GSL":    tempValue = "1" ' or "2" or "7"
    Case "FFL":    tempValue = "1"
End Select
DetermineMarketOrgCode = tempValue
End Function

Public Function DetermineMarketOrg(CompanyCode As String, AgentCode As String)
Dim tempValue As String

Select Case CompanyCode
  Case "01":
                Select Case AgentCode
                    Case "1": tempValue = "MLM"
                    Case "2": tempValue = "CSSD"
                    Case "7": tempValue = "IMG"
                    Case "D": tempValue = "DIRECT"
                    Case Else: tempValue = AgentCode
                End Select
  Case "04":    tempValue = "ANTEX"
  Case "06":    tempValue = "SLAICO"
  Case "08":    tempValue = "GSL"
  Case "26":    tempValue = "FFL"
  Case "30":
                Select Case AgentCode
                    Case "1": tempValue = "MLM"
                    Case "7": tempValue = "IMG"
                    Case "D": tempValue = "DIRECT"
                    Case Else: tempValue = AgentCode
                End Select
  Case Else:    tempValue = AgentCode
End Select
DetermineMarketOrg = tempValue
End Function
Public Function TranslateDivTypeCode(vntDivTypeCode As Variant) As String
Dim tempValue As String
Select Case CStr(vntDivTypeCode)
  Case "D": tempValue = "Dividend"
  Case "C": tempValue = "Coupon"
  Case Else: tempValue = vntDivTypeCode
End Select
TranslateDivTypeCode = tempValue
End Function

Public Function TranslateNonForfeitureOptionCodeToText(vntNFO_Code As Variant) As String
Dim tempValue As String
Select Case CStr(vntNFO_Code)
  Case "0": tempValue = "The contract has no value; lapse it"
  Case "1": tempValue = "Apply APLs until the limit is reached and convert to ETI"
  Case "2": tempValue = "Apply APLs until the limit is reached and convert to RPU"
  Case "3": tempValue = "Apply APLs until no value remains"
  Case "4":  tempValue = "Convert to ETI"
  Case "5": tempValue = "Convert to RPU"
  Case "9": tempValue = "See policy for special loan or termination agreement"
  Case Else: tempValue = vntNFO_Code
End Select
TranslateNonForfeitureOptionCodeToText = tempValue
End Function

Public Function DivOptionCodeDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "1", "Cash"
dct.Add "2", "Premium Reduction"
dct.Add "3", "Deposit at interest"
dct.Add "4", "Paid-up additions"
dct.Add "5", "O additions, unlimited"
dct.Add "6", "OYT Limit CV" 'One year term additions, limit cash value"
dct.Add "7", "OYT Limit Face" '"One year term additions, limit face amount"
dct.Add "8", "Loan Reduction" '"Loan reduction"

Set DivOptionCodeDictionary = dct
Set dct = Nothing
End Function

Public Function TranslateDivOptionCode(vntDivOptionCode As Variant) As String
Dim tempValue As String
Select Case CStr(vntDivOptionCode)
  Case "1", 1: tempValue = "Cash"
  Case "2", 2: tempValue = "Prem Reduce" '"Premium reduction"
  Case "3", 3: tempValue = "Deposit at interest" '"Deposit at interest"
  Case "4", 4: tempValue = "Paid-up additions"
  Case "5", 5: tempValue = "One year term additions, unlimited"
  Case "6", 6: tempValue = "OYT Limit CV" 'One year term additions, limit cash value"
  Case "7", 7: tempValue = "OYT Limit Face" '"One year term additions, limit face amount"
  Case "8", 8: tempValue = "Loan Reduction" '"Loan reduction"
  Case Else: tempValue = vntDivOptionCode
End Select
TranslateDivOptionCode = tempValue
End Function

Public Function ProductLineCodeDictionary()
Dim dct As Dictionary
Set dct = New Dictionary
dct.Add "0", "Traditional (Indeterm Term not included)"
'dct.Add "A", "First-to-die rider"
dct.Add "B", "Blended insurance rider"
dct.Add "C", "Additional payment paid-up additions rider"
'dct.Add "D", "Dread disease rider"
dct.Add "F", "Annuity or Annuity Rider"
dct.Add "I", "Interest sensitive life"
'dct.Add "L", "Long term care"
dct.Add "N", "Indeterminate premium"
dct.Add "U", "Universal or variable universal life"
'dct.Add "P", "Paid-up whole life or paid-up deferred whole life"
dct.Add "S", "Disability income"
'dct.Add "X", "Excess interest life"


Set ProductLineCodeDictionary = dct
Set dct = Nothing
End Function
Public Function IsIUL(strPlancode As String) As Boolean
'Takes in Plancode and strProductLineCode and ANICOProduct Indicator and returns one of these product mnemonics
'UL, IUL, JTUL, ISWL, ParWL, WL, Term, DI,
Select Case strPlancode
 Case "1U145500", "1U145900", "1U145800", "1U145600": IsIUL = True
 Case "1U144600", "1U144600", "1U144600": IsIUL = True
 Case Else: IsIUL = False
End Select
End Function
Public Function GetProductType(strProductLineCode As String, strPlancode As String)
Dim tempType As Variant

If IsIUL(strPlancode) Then
 tempType = "Index UL"
Else
 Select Case strProductLineCode
   Case "U":  tempType = "Universal Life"
   Case "I": tempType = "Interest Sensitive WL"
   Case "S":
   Case "S":
   Case "S":
   Case "S":
   
   Case Else: tempType = strProductLineCode
End Select
End If
GetProductType = tempType

End Function
Public Function TranslateNonStandardModeToText(vntMode As Variant) As String
Dim tempMode As String
Select Case CStr(vntMode)
 Case "1": tempMode = "Weekly"
 Case "2": tempMode = "Biweekly"
 Case "4": tempMode = "13thly (every 4 weeks)"
 Case "9": tempMode = "9thly"
 Case "A": tempMode = "10thly"
 Case "S": tempMode = "SemiMonthly"
 Case Else: tempMode = vntMode
End Select
TranslateNonStandardModeToText = tempMode
End Function
Public Function TranslateFundIDToName(strFundID As String) As String
Dim tempFundName As String
Select Case strFundID
    Case "IX":   tempFundName = "Index 1 yr PTP with Cap"
    Case "IC":   tempFundName = "Index 1 yr PTP with 1.5% and Cap"
    Case "IF":   tempFundName = "Index 1 yr PTP uncapped with fee"
    Case "IS":   tempFundName = "Index 1 yr PTP with Specified Rate"
    Case "SW":   tempFundName = "Sweep Fund"
    Case "GP":   tempFundName = "Grace Fund"
    Case "U1":   tempFundName = "General Fund"
    Case Else:   tempFundName = strFundID
End Select
TranslateFundIDToName = tempFundName
End Function
Public Function TranslateDBOptionCode(vntDBOptCode As Variant) As String
Dim tempDBOpt As String
vntDBOptCode = CStr(vntDBOptCode)
Select Case vntDBOptCode
 Case "A", "1": tempDBOpt = "A - Level"
 Case "B", "2": tempDBOpt = "B - Increasing"
 Case "C", "3": tempDBOpt = "C - Returen Of Premium"
 Case Else: tempDBOpt = vntDBOptCode
End Select
TranslateDBOptionCode = tempDBOpt
End Function
Public Function TranslateStateCodeToText(intStateCode As Integer) As String
'These are the state code in Cyberlife, not to be confused with the state filing codes used for filed forms - which are different
Dim tempState As Variant

Select Case intStateCode
 Case 1:      tempState = "AL"
 Case 2:      tempState = "AZ"
 Case 3:      tempState = "AR"
 Case 4:      tempState = "CA"
 Case 5:      tempState = "CO"
 Case 6:      tempState = "CT"
 Case 7:      tempState = "DE"
 Case 8:      tempState = "DC"
 Case 9:      tempState = "FL"
 Case 10:      tempState = "GA"
 Case 11:      tempState = "ID"
 Case 12:      tempState = "IL"
 Case 13:      tempState = "IN"
 Case 14:      tempState = "IA"
 Case 15:      tempState = "KS"
 Case 16:      tempState = "KY"
 Case 17:      tempState = "LA"
 Case 18:      tempState = "ME"
 Case 19:      tempState = "MD"
 Case 20:      tempState = "MA"
 Case 21:      tempState = "MI"
 Case 22:      tempState = "MN"
 Case 23:      tempState = "MS"
 Case 24:      tempState = "MO"
 Case 25:      tempState = "MT"
 Case 26:      tempState = "NE"
 Case 27:      tempState = "NV"
 Case 28:      tempState = "NH"
 Case 29:      tempState = "NJ"
 Case 30:      tempState = "NM"
 Case 31:      tempState = "NY"
 Case 32:      tempState = "NC"
 Case 33:      tempState = "ND"
 Case 34:      tempState = "OH"
 Case 35:      tempState = "OK"
 Case 36:      tempState = "OR"
 Case 37:      tempState = "PA"
 Case 38:      tempState = "RI"
 Case 39:      tempState = "SC"
 Case 40:      tempState = "SD"
 Case 41:      tempState = "TN"
 Case 42:      tempState = "TX"
 Case 43:      tempState = "UT"
 Case 44:      tempState = "VT"
 Case 45:      tempState = "VA"
 Case 46:      tempState = "WA"
 Case 47:      tempState = "WV"
 Case 48:      tempState = "WI"
 Case 49:      tempState = "WY"
 Case 50:      tempState = "AK"
 Case 51:      tempState = "HI"
 Case 52:      tempState = "PR"
 Case 55:      tempState = "AS"
 Case 60:      tempState = "MP"
 Case 65:      tempState = "VI"
 Case 66:      tempState = "GU"
End Select
TranslateStateCodeToText = tempState
End Function
Public Function StateDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "AL", 1
dct.Add "AZ", 2
dct.Add "AR", 3
dct.Add "CA", 4
dct.Add "CO", 5
dct.Add "CT", 6
dct.Add "DE", 7
dct.Add "DC", 8
dct.Add "FL", 9
dct.Add "GA", 10
dct.Add "ID", 11
dct.Add "IL", 12
dct.Add "IN", 13
dct.Add "IA", 14
dct.Add "KS", 15
dct.Add "KY", 16
dct.Add "LA", 17
dct.Add "ME", 18
dct.Add "MD", 19
dct.Add "MA", 20
dct.Add "MI", 21
dct.Add "MN", 22
dct.Add "MS", 23
dct.Add "MO", 24
dct.Add "MT", 25
dct.Add "NE", 26
dct.Add "NV", 27
dct.Add "NH", 28
dct.Add "NJ", 29
dct.Add "NM", 30
dct.Add "NY", 31
dct.Add "NC", 32
dct.Add "ND", 33
dct.Add "OH", 34
dct.Add "OK", 35
dct.Add "OR", 36
dct.Add "PA", 37
dct.Add "RI", 38
dct.Add "SC", 39
dct.Add "SD", 40
dct.Add "TN", 41
dct.Add "TX", 42
dct.Add "UT", 43
dct.Add "VT", 44
dct.Add "VA", 45
dct.Add "WA", 46
dct.Add "WV", 47
dct.Add "WI", 48
dct.Add "WY", 49
dct.Add "AK", 50
dct.Add "HI", 51
dct.Add "PR", 52
dct.Add "AS", 53
dct.Add "MP", 54
dct.Add "VI", 55
dct.Add "GU", 56

Set StateDictionary = dct

End Function
Public Function TranslateMECIndicatorToText(vntMECIndicator As Variant) As String
Dim tempstr As String
Dim tempValue As String
tempValue = CStr(vntMECIndicator)
Select Case vntMECIndicator
  Case "0":  tempstr = "Not a MEC"
  Case "1":  tempstr = "Policy is a MEC."
  Case "2":  tempstr = "Plan is subject to the 7-pay test"
  Case "4":  tempstr = "Plan is CVAT and subject to the 7-pay test"
  Case Else: tempstr = vntMECIndicator
End Select
TranslateMECIndicatorToText = tempstr
End Function
Public Function TranslateBillModeCodeToText(vntBillModeCode As String, Optional NonStandardMode As String = "") As String
Dim tempMode As String
vntBillModeCode = CStr(vntBillModeCode)
Select Case vntBillModeCode
 Case "1":
            tempMode = "M - Monthly"
            If NonStandardMode = "2" Then tempMode = "B - BiWeekly"
            If NonStandardMode = "S" Then tempMode = "SM - SemiMonthly"
            
 Case "3": tempMode = "Q - Quarterly"
 Case "6": tempMode = "S - SemiAnnually"
 Case "12": tempMode = "A - Annually"
 Case Else: tempMode = vntBillModeCode
End Select
TranslateBillModeCodeToText = tempMode
End Function

Public Function TranslatePersonCodeToText(strCode As String) As String
Dim tempText As String
Select Case strCode
 Case "00": tempText = "Primary Insured"
 Case "01": tempText = "Joint insured"
 Case "10": tempText = "Owner"
 Case "20": tempText = "Payor"
 Case "30": tempText = "Beneficiary"
 Case "40": tempText = "Spouse"
 Case "50": tempText = "Dependent"
 Case "60": tempText = "Other"
 Case "70": tempText = "Assignee"
 Case "A0": tempText = "Power of attorney"
 Case "A1": tempText = "Financial advisor"
 Case "A2": tempText = "Third party administrator (TPA)"
 Case "A3": tempText = "Certified public accountant (CPA)"
 Case "A4": tempText = "Plan sponsor"
 Case "A5": tempText = "Conservator"
 Case "A6": tempText = "Domestic partner"
 Case "A7": tempText = "Legal guardian"
 Case "A8": tempText = "Trustee"
 Case "A9": tempText = "Settlement Broker"
 Case Else: tempText = strCode
End Select
TranslatePersonCodeToText = tempText
End Function

Public Function GracePeriodRuleDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "C", "Unloaned CV < 0."
dct.Add "S", "SV < 0."
dct.Add "N", "Adjusted Prem < MAP.  Then Rule S."
dct.Add "R", "Adjusted Prem < MAP AND Unloaned CV < 0.  Then rule C."
dct.Add "T", "Adjusted Prem < MAP AND SV < 0.  Then Rule S."

Set GracePeriodRuleDictionary = dct
Set dct = Nothing
End Function

Public Function BenefitDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "ADB", "1"
dct.Add "ADnD", "2"
dct.Add "PWoC", "3"
dct.Add "PWoT", "4"
dct.Add "ADB2", "5"
dct.Add "GIO", "7"
dct.Add "PPB", "9"
dct.Add "ABR", "#"
dct.Add "CCV", "A"
dct.Add "COLA", "U"
dct.Add "LTC", "B"
dct.Add "SMKR", "X"
dct.Add "GCO", "V"

Set BenefitDictionary = dct
Set dct = Nothing
End Function

Public Function TranslateBenefitCodeToType(vntBenefitType As Variant)
Dim tempType As String

Select Case CStr(vntBenefitType)
 Case "1": tempType = "ADB"     'Accidental Death Benefit
 Case "2": tempType = "ADnD"    'Accidental Death and Dismemberment
 Case "3": tempType = "PWoC"    'Premium Waiver of Cost
 Case "4": tempType = "PWoT"    'Premium Wavier of Target
 Case "7": tempType = "GIO"     'Guaranteed Increase Option
 Case "9": tempType = "PPB"     'Premium Payor Benefit
  Case "#": tempType = "ABR"    'Accelerated Benefit Rider
 Case "A": tempType = "CCV"     'Coverage Continuation Rider (aka shadow account)
 Case "U": tempType = "COLA"    'Cost of Living Adjustment
 Case "B": tempType = "LTC"     'Long Term Care
 Case "V": tempType = "GCO"     'Guaranteed Cash Out Rider
 Case Else: tempType = vntBenefitType
End Select
TranslateBenefitCodeToType = tempType
 
End Function
Public Function TranslateBenefitTypeToCode(vntBenefitType As Variant)
Dim tempType As String

Select Case CStr(vntBenefitType)
 Case "ADB": tempType = "1"
 Case "ADD": tempType = "2"
 Case "PWoC": tempType = "3"
 Case "PWoT": tempType = "4"
 Case "GIO": tempType = "7"
 Case "PPB": tempType = "9"
 Case "ABR": tempType = "#"
 Case "CCV": tempType = "A"
 Case "COLA": tempType = "U"
 Case "LTC": tempType = "B"
 Case Else: tempType = vntBenefitType
End Select
TranslateBenefitTypeToCode = tempType
 
End Function

Public Function TranslateTable(vntCode As Variant) As Variant

If IsNull(vntCode) Then
  TranslateTable = ""
  Exit Function
End If
Dim tempValue As Variant
Select Case CStr(Application.WorksheetFunction.Trim(vntCode))
 Case "0": tempValue = 0
 Case "A", "1": tempValue = 1
 Case "B", "2": tempValue = 2
 Case "C", "3": tempValue = 3
 Case "D", "4": tempValue = 4
 Case "E", "5": tempValue = 5
 Case "F", "6": tempValue = 6
 Case "G", "7": tempValue = 7
 Case "H", "8": tempValue = 8
 Case "I", "9": tempValue = 9
 Case "J", "10": tempValue = 10
 Case "K", "11": tempValue = 11
 Case "L", "12": tempValue = 12
 Case "M", "13": tempValue = 13
 Case "N", "14": tempValue = 14
 Case "O", "15": tempValue = 15
 Case "P", "16": tempValue = 16
 Case "X", "999": tempValue = "Unins"
 Case Else: tempValue = vntCode
End Select

TranslateTable = tempValue

End Function
Public Function CompanyDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

 dct.Add "ANICO", "01"
 dct.Add "ANTEX", "04"
 dct.Add "SLAICO", "06"
 dct.Add "GSL", "08"
 'dct.Add "FFL", "26"
 dct.Add "ANICO NY", "26"
Set CompanyDictionary = dct
Set dct = Nothing
End Function

Public Function TranslateCompanyCodeToText(vntCode As Variant) As Variant
Dim tempValue As String

Select Case CStr(vntCode)
 Case "01":  tempValue = "ANICO"
 Case "04":  tempValue = "ANTEX"
 Case "06":  tempValue = "SLAICO"
 Case "08":  tempValue = "GSL"
 Case "26":  tempValue = "FFL"
 Case "30":  tempValue = "ANICO NY"
 Case Else: tempValue = vntCode
End Select
TranslateCompanyCodeToText = tempValue
End Function

Public Function TranslateOriginalEntryCodeToText(vntCode As Variant) As String
Dim tempValue As String
Select Case CStr(vntCode)
  Case "A": tempValue = "New business"
  Case "B": tempValue = "Group conversion"
  Case "C": tempValue = "Block reinsurance"
  Case "D": tempValue = "Reinstatement"
  Case "E": tempValue = "Exchange or conversion with a new policy number assigned"
  Case "F": tempValue = "Exchange or conversion retaining the original policy number"
  Case "G": tempValue = "Policy change"
  Case "H": tempValue = "Advanced product complex change"
  Case "Z": tempValue = "Old life business converted to the system"
  Case Else
End Select
TranslateOriginalEntryCodeToText = vntCode & " - " & tempValue
End Function

Public Function EntryCodeDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "A", "New business"
dct.Add "B", "Group conversion."
dct.Add "C", "Block reinsurance."
dct.Add "D", "Reinstatement."
dct.Add "E", "Exchange or conversion with a new policy number assigned."
dct.Add "F", "Exchange or conversion retaining the original policy number."
dct.Add "G", "Policy change."
dct.Add "H", "Advanced product complex change."
dct.Add "Z", "Old life business converted to the system."

Set EntryCodeDictionary = dct
Set dct = Nothing
End Function


Public Function TranslateLoanIntStatusCodeToText(vntCode As Variant) As Variant
Dim tempValue As String
Select Case CStr(vntCode)
  Case "1", 1: tempValue = "Capitalized"
  Case "2", 2: tempValue = "Earned"
  Case Else: tempValue = vntCode
End Select
TranslateLoanIntStatusCodeToText = tempValue
End Function

Public Function ReinsuranceCodeDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "A", "Automatic"
dct.Add "F", "Facultative"
dct.Add "N", "Not reinsured"
dct.Add "1", "Part reinsured"
dct.Add "2", "Multiple policy records"
dct.Add " ", "Not reinsured"

Set ReinsuranceCodeDictionary = dct
Set dct = Nothing
End Function

Public Function LoanInterestTypeCodeDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "0", "Advance, Fixed Interest"
dct.Add "1", "Arrears, Fixed Interest"
dct.Add "6", "Advance, Variable Interest"
dct.Add "7", "Arrears, Variable Interest"
dct.Add "9", "Loans not allowed"

Set LoanInterestTypeCodeDictionary = dct
Set dct = Nothing
End Function

Public Function TranslateLoanIntTypeCodeToText(vntCode As Variant) As String
Dim tempValue As String
Select Case CStr(vntCode)
  Case "1", 1: tempValue = "Advance"
  Case "2", 2: tempValue = "Arrears"
  Case Else: tempValue = vntCode
End Select
TranslateLoanIntTypeCodeToText = tempValue
End Function
Public Function TranslateLastEntryCodeToText(vntCode As Variant) As Variant
Dim tempValue As String
Select Case CStr(vntCode)
  Case "A": tempValue = "A - Entry - New Business, Not Paid For"
  Case "B": tempValue = "B - Normal Entry to the file"
  Case "C": tempValue = "C - Active Policy Record"
  Case "D": tempValue = "D - Correction Entry to Database"
  Case "E": tempValue = "E - Replacement"
  Case "F": tempValue = "F - Replacement with Policy Exhibit Transactions"
  Case "J": tempValue = "J - Termination - Without Policy Exhibit Transactions"
  Case "K": tempValue = "K - Termination - With Policy Exhibit Transactions"
  Case "L": tempValue = "L - Termination - Death Claim Settled"
  Case "M": tempValue = "M - Termination - Maturity"
  Case "N": tempValue = "N - Termination - Expiration"
  Case "O": tempValue = "O - Termination - Conversion"
  Case "P": tempValue = "P - Termination - Surrender"
  Case "Q": tempValue = "Q - Termination - Lapse"
  Case "R": tempValue = "R - Termination - Conversion to RPU or ETI"
  Case "X": tempValue = "X - Termination - Free Look Surrender"
  Case Else: tempValue = vntCode
End Select
TranslateLastEntryCodeToText = tempValue
End Function
Public Function TranslateSuspenseCodeToText(vntCode As Variant) As String
Dim tempValue As String
  Select Case CStr(vntCode)
    Case "0": tempValue = "Active policy record"
    Case "1": tempValue = "Not used"
    Case "2": tempValue = "Suspend processing"
    Case "3": tempValue = "Death claim pending"
    Case Else: tempValue = vntCode
  End Select
  TranslateSuspenseCodeToText = tempValue
End Function
Public Function ANICOProductDictionary()
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "A", "APB Rider"
dct.Add "B", "ANICO ROP Rider"
dct.Add "C", "ANTEX Modified DB"
dct.Add "D", "ANTEX Graded DB"
dct.Add "E", "ANTEX Level DB"
dct.Add "G", "Graded Benefit Life"
dct.Add "P", "Converted FFL PUAR"
dct.Add "R", "GSL ROP"
dct.Add "S", "Single Premium ISWL"
dct.Add "U", "Converted FFL UL"
dct.Add "X", "Index UL"


Set ANICOProductDictionary = dct
Set dct = Nothing

End Function
Public Function NonForfeitureCodeDictionary()
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "0", "No cash value"
dct.Add "1", "APL-->ETI"
dct.Add "2", "APL-->RPU"
dct.Add "3", "APL"
dct.Add "4", "ETI"
dct.Add "5", "RPU"
dct.Add "9", "Special Other"

Set NonForfeitureCodeDictionary = dct
Set dct = Nothing
End Function
Public Function StatusDictionary()
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "11", "Pending applications"
dct.Add "12", "No Init Premium Yet"
dct.Add "21", "Premium Paying"
dct.Add "22", "Premium Paying"
dct.Add "31", "Payor Death"
dct.Add "32", "Disability"
dct.Add "33", "Disability"
dct.Add "34", "Disability"
dct.Add "41", "Paid Up"
dct.Add "42", "Single Premium"
dct.Add "43", "Single Premium (none)"
dct.Add "44", "ETI"
dct.Add "45", "RPU"
dct.Add "46", "Fully Paid Up"
dct.Add "47", "Paid Up"
dct.Add "49", "Annuitization (none)"
dct.Add "54", "Lapsing (none)"
dct.Add "97", "Reinstatement pending"
dct.Add "98", "Policy not issued"
dct.Add "99", "Terminated"

Set StatusDictionary = dct
Set dct = Nothing
End Function

Public Function TranslateStatusCodeToText(vntCode As Variant) As String
Dim tempValue As String
Select Case CStr(vntCode)
  Case "11": tempValue = "For pending applications"
  Case "12": tempValue = "Initial premium not processed on other than preliminary term"
  Case "13": tempValue = "Preliminary term"
  Case "21": tempValue = "A fixed premium policy for which back premiums have been billed"
  Case "22": tempValue = "A normal premium paying policy record"
  Case "31": tempValue = "Payor death (not currently supported)"
  Case "32": tempValue = "Disability (traditional policies and interest sensitive life policies) or cost of insurance"
  Case "33": tempValue = "Disability waiver - scheduled amount added to cash value"
  Case "34": tempValue = "Cost of insurance waiver and disability waiver"
  Case "41": tempValue = "Paid-up normal"
  Case "42": tempValue = "Single premium (fixed premium only)"
  Case "43": tempValue = "Single premium in lieu of matured endowment (net basis)"
  Case "44": tempValue = "ETI"
  Case "45": tempValue = "RPU"
  Case "46": tempValue = "Fully paid-up"
  Case "47": tempValue = "Multiple coverages that are all paid-up with different paid-up forms"
  Case "49": tempValue = "Annuitization"
  Case "54": tempValue = "A policy record lapsing on a daily cost basis"
  Case "97": tempValue = "Reinstatement pending"
  Case "98": tempValue = "Initial premium never received (policy was not issued)"
  Case "99": tempValue = "A terminated policy record that is carried on the policy file for ease in reinstatement"
  Case Else: tempValue = vntCode
End Select
TranslateStatusCodeToText = tempValue
End Function
Public Function TranslateTransactionCodeToText(vntCode As Variant) As String
Dim tempValue As String
Select Case CStr(vntCode)
 Case "A_": tempValue = "Policyowner statement revision"
 Case "AA": tempValue = "Policyowner statement automatic on anniversary"
 Case "AC": tempValue = "Policyowner confirmation"
 Case "AF": tempValue = "Policyowner statement off anniversary"
 Case "AL": tempValue = "Lag/loss accounting"
 Case "AR": tempValue = "Policyowner statement request prior 12 months"
 Case "AS": tempValue = "Split accounting for the fixed fund portion when the exchange includes both fixed and variable funds."
 Case "AY": tempValue = "Policyowner statement request year-to-date"
 Case "B1": tempValue = "Cost of Insurance"
 Case "B2": tempValue = "Expenses"
 Case "B3": tempValue = "Cost of insureance and expenses"
 Case "B4": tempValue = "First year load"
 Case "B5": tempValue = "Cash value"
 Case "B6": tempValue = "Current interest"
 Case "B7": tempValue = "Guaranteed interest"
 Case "BA": tempValue = "Cost of insurance and expense reversal"
 Case "BB": tempValue = "Current interest reversal (retrospective)"
 Case "BC": tempValue = "Guaranteed interest reversal (prospective)"
 Case "CA": tempValue = "Charge allocation (adjustment)"
 Case "CC": tempValue = "Cumulative charge"
 Case "CD": tempValue = "Charge deduction"
 Case "CY": tempValue = "Calendar year expense charge"
 Case "DK": tempValue = "Dread disease, expense charge"
 Case "DP": tempValue = "Dread disease, claim payment"
 Case "EF": tempValue = "Exchange from"
 Case "EK": tempValue = "Exchange charge"
 Case "ET": tempValue = "Exchange to"
 Case "FE": tempValue = "Discounted premium"
 Case "FF": tempValue = "Premium depositor fund"
 Case "GL": tempValue = "Accounting"
 Case "GP": tempValue = "External variable fund purchase"
 Case "GR": tempValue = "External variable fund redemption"
 Case "HB": tempValue = "Beginning payments"
 Case "HE": tempValue = "Ending payment"
 Case "HP": tempValue = "Claim payment"
 Case "HX": tempValue = "Dread disease claim reduction"
 Case "HZ": tempValue = "LTC/HHC claim reduction"
 Case "IA": tempValue = "Dividends on deposit"
 Case "IB": tempValue = "Other forms on deposit"
 Case "IC": tempValue = "Accrued interest, loan payoff"
 Case "ID": tempValue = "Death claims"
 Case "IE": tempValue = "Discounted premiums"
 Case "IF": tempValue = "Premium depositor fund"
 Case "IH": tempValue = "Pro rata"
 Case "IL": tempValue = "Lien payoffs"
 Case "IN": tempValue = "Long term care/dread disease accumulated claims lien amount"
 Case "IP": tempValue = "Loan payoff"
 Case "IR": tempValue = "Accrued interest, lien payoff"
 Case "IT": tempValue = "Dread disease lien interest"
 Case "IV": tempValue = "Interest on discounted premium withdrawal"
 Case "IW": tempValue = "Interest, premium depositor fund withdrawal"
 Case "LA": tempValue = "Automatic premium loan"
 Case "LC": tempValue = "Capitalized accrued loan interest"
 Case "LF": tempValue = "Maximum preferred loan"
 Case "LG": tempValue = "Gross loan request"
 Case "LM": tempValue = "Maximum loan request"
 Case "LN": tempValue = "Net loan request"
 Case "LP": tempValue = "Loan principal reduction"
 Case "LV": tempValue = "Capitalized advance loan interest"
 Case "LZ": tempValue = "Premiums withheld from loans"
 Case "MA": tempValue = "Accounting"
 Case "MS": tempValue = "Moves money from the clearing account to the external clearing suspense account."
 Case "N3": tempValue = "Deposit at interest"
 Case "N4": tempValue = "Interest on dividends on deposit at conversion to ETI/RPU"
 Case "NC": tempValue = "Pro rata interest on new deposits"
 Case "ON": tempValue = "ISL, paid-up additions option not elected"
 Case "OS": tempValue = "Over/short"
 Case "OY": tempValue = "ISL, elect paid-up additions option"
 Case "P6": tempValue = "Current value adjustment for payments and surrenders"
 Case "P7": tempValue = "Annuitization account value adjustment increase"
 Case "P8": tempValue = "Excess interest"
 Case "PA": tempValue = "Additional (or unscheduled) premium payment"
 Case "PB": tempValue = "Reinstatement payment"
 Case "PC": tempValue = "Loan/lien interest (accrued)"
 Case "PD": tempValue = "Automatic payment, PDF"
 Case "PE": tempValue = "Automatic payment, discounted premium"
 Case "PF": tempValue = "Initial internal rollover payment"
 Case "PI": tempValue = "Initial premium payment"
 Case "PK": tempValue = "Premium load"
 Case "PL": tempValue = "Loan/lien payment"
 Case "PM": tempValue = "Payment from dividends and PUAs"
 Case "PN": tempValue = "Premium payment by automatic premium loan"
 Case "PO": tempValue = "Premium or loan/lien payoff overage"
 Case "PP": tempValue = "Loan/lien payoff"
 Case "PQ": tempValue = "Automatic payment, AP fiixed premium"
 Case "PR": tempValue = "Regular (or sscheduled) premium payment"
 Case "PS": tempValue = "Premium or loan/lien payoff shortage"
 Case "PT": tempValue = "Rollover additional"
 Case "PU": tempValue = "Reinstatement value"
 Case "PV": tempValue = "Advance loan interest payment"
 Case "PW": tempValue = "Premium Waiver"
 Case "PX": tempValue = "Loan/lien interest payment"
 Case "PZ": tempValue = "Premium tax calculation"
 Case "QA": tempValue = "Automatic transaction, annuitization"
 Case "QD": tempValue = "Automatic transactions, automatic disbursement"
 Case "QG": tempValue = "Automatic transactions, initial gain"
 Case "QI": tempValue = "Automatic transactions, initial refresh"
 Case "QR": tempValue = "Automatic transactions, automatic refresh"
 Case "QV": tempValue = "Automatic transactions, fund value quote"
 Case "QX": tempValue = "Equity index increase"
 Case "RC": tempValue = "Refund of cash value, face amount decrease"
 Case "RD": tempValue = "Refund of premium, face amount decrease"
 Case "RI": tempValue = "Reinstatement interest"
 Case "RP": tempValue = "RPU refund excess"
 Case "S4": tempValue = "Paid-up additions partial surrender"
 Case "S5": tempValue = "One year term additions partial surrender"
 Case "S6": tempValue = "Current value withdrawal"
 Case "S7": tempValue = "Annuitization account value adjustment decrease"
 Case "S8": tempValue = "Fund optimization fee"
 Case "SA": tempValue = "Excess accumulation withdrawal"
 Case "SB": tempValue = "Fund optimization fee"
 Case "SC": tempValue = "Surrender, conversion"
 Case "SD D": tempValue = "Premiums due on death claim"
 Case "SF": tempValue = "Full surrender"
 Case "SG": tempValue = "Surrenders, gross withdrawal request"
 Case "SH": tempValue = "Surrenders, home/custodial care claim payment"
 Case "SI": tempValue = "Internal surrender"
 Case "SJ": tempValue = "Forced lapse"
 Case "SK": tempValue = "Surrender charge"
 Case "SL": tempValue = "Free look"
 Case "SM": tempValue = "Maximum withdrawal"
 Case "SN": tempValue = "Net withdrawal"
 Case "SP": tempValue = "Purchase paid-up additions"
 Case "SR": tempValue = "Refunded premium on surrender"
 Case "ST": tempValue = "TSA loan repayment surrender"
 Case "SV": tempValue = "Discounted premium withdrawal"
 Case "SW": tempValue = "Premium depositor fund withdrawal"
 Case "SX": tempValue = "Reversal of premium waiver for death claims and surrenders."
 Case "T9": tempValue = "Policy level surrender or termination"
 Case "TB": tempValue = "Beneficiary payout, surrender or termination"
 Case "TD": tempValue = "Death claim, primary insured"
 Case "TE": tempValue = "Extended term"
 Case "TF": tempValue = "Fully paid-up conversion"
 Case "TL": tempValue = "Lapse"
 Case "TM": tempValue = "Maturity"
 Case "TN": tempValue = "Expiry"
 Case "TO": tempValue = "Other insured death claim"
 Case "TR": tempValue = "Reduced paid-up"
 Case "TV": tempValue = "Lapse, daily cost basis"
 Case "TZ": tempValue = "Premium tax"
 Case "TZ": tempValue = "Premium Tax"
 Case "UI R": tempValue = "Unapplied cash in, returned item"
 Case "UI": tempValue = "Unapplied cash suspense in"
 Case "UO": tempValue = "Unapplied cash suspense out"
 Case "UP": tempValue = "Unmatched payment - batch"
 Case "WO": tempValue = "Waiver of premium off"
 Case "WP": tempValue = "Waiver of premium on"
 Case "XB": tempValue = "Long term care, beginning payments"
 Case "XE": tempValue = "Long term care, ending payments"
 Case "XP": tempValue = "Long term care, claim payment"
 Case "Y0": tempValue = "User defined"
 Case "ZA": tempValue = "Forecasts, annual projection"
 Case "ZC": tempValue = "Forecasts, current premium solve for target cash surrender value"
 Case "ZG": tempValue = "Forecasts, guaranteed premium solve for target cash surrender value"
 Case "ZN": tempValue = "Vanishing (offset) premium request - NVP"
 Case "ZP": tempValue = "Forecasts, current projection"
 Case "ZR": tempValue = "Vanishing (offset) premium request - APP"
 Case "ZS": tempValue = "Forecasts, premium solve"
 Case "ZV": tempValue = "Forecasts, vanishing (offset) premium"
 Case "ZZ": tempValue = "Suppress check special accounting. Refer to the accounting descriptions at the end of this section for more information."
 Case Else: tempValue = vntCode
End Select
TranslateTransactionCodeToText = tempValue
End Function

Public Function GetTransactionTypeDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "A", "Accounting"
dct.Add "B", "Policyowner Reward"
dct.Add "C", "Charge"
dct.Add "D", "Dread Disease"
dct.Add "E", "Exchange"
dct.Add "F", "Premium Fund Addition"
dct.Add "G", "Agent Ledger"
dct.Add "H", "Home health care"
dct.Add "I", "Interest/Internal"
dct.Add "L", "Loans"
dct.Add "M", "Miscellaneous "
dct.Add "N", "Withdrawal interest"
dct.Add "O", "Paid-up additions option"
dct.Add "P", "Premium payments/loan payments"
dct.Add "Q", "Automatic transactions"
dct.Add "R", "Refund"
dct.Add "S", "Surrenders"
dct.Add "T", "Terminations"
dct.Add "U", "Unapplied cash suspense"
dct.Add "W", "Waiver of Premium"
dct.Add "X", "Long term care"
dct.Add "Y", "User defined"
dct.Add "Z", "Forecast (only if subtype is A, C, G, P, S, or V)"
dct.Add "1", "Dividends earned - premium paying policies"
dct.Add "2", "Other forms of participation earned"
dct.Add "3", "Dividend values - on converted policies"
dct.Add "4", "Other participation on converted policies"
dct.Add "5", "Dividend processing - online"
dct.Add "6", "Other participation - online"
dct.Add "7", "Additions PUA and OYT - online"
dct.Add "8", "Pro rata dividends on withdrawal"
dct.Add "9", "Pro rata other forms on withdrawal"

Set GetTransactionTypeDictionary = dct
Set dct = Nothing

'On 6/17/2016 an audit was run against the FH_FIXED table for company "01".  These were the only transaction types found:
'B
'C
'E
'F
'I
'L
'P
'R
'S
'T
'U
'W
'Z
'1
'2
'3
'4
'5
'6
'7

End Function

Public Function TransactionTypeAndSubtypeDictionary() As Dictionary
'These are all the transaction types and subtypes that were found in Cyberlife on 12/17/2061.  There are more in CyberDoc

Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "BC", "Guaranteed interest reversal (prospective)"
dct.Add "CA", "Charge allocation (adjustment)"
dct.Add "CC", "Cumulative charge"
dct.Add "CD", "Charge deduction"
dct.Add "EF", "Exchange from"
dct.Add "ET", "Exchange to"
dct.Add "FE", "Discounted premium"
dct.Add "FF", "Premium depositor fund"
dct.Add "IA", "Dividends on deposit"
dct.Add "IB", "Other forms on deposit"
dct.Add "ID", "Death claims"
dct.Add "IE", "Discounted premiums"
dct.Add "IF", "Premium depositor fund"
dct.Add "LA", "Automatic premium loan"
dct.Add "LC", "Capitalized accrued loan interest"
dct.Add "LG", "Gross loan request"
dct.Add "LM", "Maximum loan request"
dct.Add "LN", "Net loan request"
dct.Add "LP", "Loan principal reduction"
dct.Add "LV", "Capitalized advance loan interest"
dct.Add "PA", "Additional (or unscheduled) premium payment"
dct.Add "PB", "Reinstatement payment"
dct.Add "PD", "Automatic payment, PDF"
dct.Add "PE", "Automatic payment, discounted premium"
dct.Add "PF", "Initial internal rollover payment"
dct.Add "PI", "Initial premium payment"
dct.Add "PL", "Loan/lien payment"
dct.Add "PN", "Premium payment by automatic premium loan"
dct.Add "PP", "Loan/lien payoff"
dct.Add "PQ", "Automatic payment, AP fiixed premium"
dct.Add "PR", "Regular (or sscheduled) premium payment"
dct.Add "PT", "Rollover additional"
dct.Add "PU", "Reinstatement value"
dct.Add "PW", "Premium Waiver"
dct.Add "PX", "Loan/lien interest payment"
dct.Add "P7", "Annuitization account value adjustment increase"
dct.Add "P8", "Excess interest"
dct.Add "RC", "Refund of cash value, face amount decrease"
dct.Add "RD", "Refund of premium, face amount decrease"
dct.Add "RP", "RPU refund excess"
dct.Add "SA", "Excess accumulation withdrawal"
dct.Add "SC", "Surrender, conversion"
dct.Add "SF", "Full surrender"
dct.Add "SG", "Surrenders, gross withdrawal request"
dct.Add "SI", "Internal surrender"
dct.Add "SJ", "Forced lapse"
dct.Add "SK", "Surrender charge"
dct.Add "SL", "Free look"
dct.Add "SM", "Maximum withdrawal"
dct.Add "SN", "Net withdrawal"
dct.Add "SV", "Discounted premium withdrawal"
dct.Add "SW", "Premium depositor fund withdrawal"
dct.Add "S4", "Paid-up additions partial surrender"
dct.Add "S5", "One year term additions partial surrender"
dct.Add "S7", "Annuitization account value adjustment decrease"
dct.Add "TD", "Death claim, primary insured"
dct.Add "TE", "Extended term"
dct.Add "TL", "Lapse"
dct.Add "TM", "Maturity"
dct.Add "TN", "Expiry"
dct.Add "TO", "Other insured death claim"
dct.Add "TR", "Reduced paid-up"
dct.Add "TV", "Lapse, daily cost basis"
dct.Add "UI", "Unapplied cash suspense in"
dct.Add "UO", "Unapplied cash suspense out"
dct.Add "WO", "Waiver of premium off"
dct.Add "WP", "Waiver of premium on"
dct.Add "ZR", "Vanishing (offset) premium request - APP"
dct.Add "11", "Cash"
dct.Add "13", "Deposit at interest"
dct.Add "14", "Paid-up additions"
dct.Add "15", "One year term additions, unlimited"
dct.Add "16", "One year term additions, limit CV"
dct.Add "18", "L"
dct.Add "21", "Cash"
dct.Add "23", "Deposit at interest"
dct.Add "24", "Paid-up additions"
dct.Add "33", "Deposit at interest"
dct.Add "34", "Paid-up additions"
dct.Add "35", "One year term additions, unlimited"
dct.Add "43", "Deposit at interest"


Set TransactionTypeAndSubtypeDictionary = dct
Set dct = Nothing

End Function

Public Function MortalityTableDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "#", "2001CSO SM/NS"
dct.Add "@", "80 CSO SMKR/N"
dct.Add "A", "1926 CL 3 AE  A"
dct.Add "J", "PROG ANNUITY  J"
dct.Add "K", "A/E CRAIG     K"
dct.Add "L", "A/E BUTTOLPH  L"
dct.Add "M", "AMERICAN MEN  M"
dct.Add "N", "1941 CSO      N"
dct.Add "O", "1958 CSO MALE O"
dct.Add "P", "1958 CSO FEM  P"
dct.Add "S", "1958 CSO MLX  S"
dct.Add "T", "1958 CSO FLX  T"
dct.Add "0", "OLD JOINT LIF"
dct.Add "$", "2001CSO COMPU"
dct.Add "*", "1949 A FEMALE"
dct.Add "**", "1949 A FEMALE"
dct.Add "LA", "80 CETMNS ALB"
dct.Add "LC", "2001CSOMNS LS"
dct.Add "LD", "2001CSOFNS LS"
dct.Add "LF", "2001CSOMS L S"
dct.Add "LG", "2001CSOFS L S"
dct.Add "LJ", "80 CSOJT ALB"
dct.Add "LK", "2001CSOMNS LU"
dct.Add "LL", "2001CSOFNS LU"
dct.Add "LN", "2001CSOMS L U"
dct.Add "LO", "2001CSOFS L U"
dct.Add "LP", "2001CSOM L  U"
dct.Add "LQ", "2001CSOF L  U"
dct.Add "L0", "80 CSOMNS ALB 0"
dct.Add "L1", "80 CSOFNS ALB 1"
dct.Add "L2", "80 CSOMS ALB  2"
dct.Add "L3", "80 CSOFS ALB  3"
dct.Add "L4", "80 CSOM ALB   4"
dct.Add "L5", "80 CSOF ALB   5"
dct.Add "L6", "80 CETMS ALB  6"
dct.Add "NC", "2001CSOMNS NS"
dct.Add "ND", "2001CSOFNS NS"
dct.Add "NF", "2001CSOMS N S"
dct.Add "NG", "2001CSOFS N S"
dct.Add "NJ", "80 CSOJT ANB"
dct.Add "NK", "2001CSOMNS NU"
dct.Add "NL", "2001CSOFNS NU"
dct.Add "NN", "2001CSOMS N U"
dct.Add "NO", "2001CSOFS N U"
dct.Add "NP", "2001CSOM N  U"
dct.Add "NQ", "2001CSOF N  U"
dct.Add "NW", ""
dct.Add "NX", ""
dct.Add "N0", "80 CSOMNS ANB"
dct.Add "N1", "80 CSOFNS ANB"
dct.Add "N2", "80 CSOMS ANB"
dct.Add "N3", "80 CFOFS ANB"
dct.Add "N4", "80 CSOM ANB"
dct.Add "N5", "80 CSOF ANB"
dct.Add "P1", ""
dct.Add "UA", "80CSO US ALB"
dct.Add "UC", "2001CSO US LS"
dct.Add "UE", "2001CSO UN NS"
dct.Add "UF", "2001CSO US NS"
dct.Add "UH", "2001CSO UN LS"
dct.Add "UK", "2001CSO US LU"
dct.Add "UM", "2001CSO UN NU"
dct.Add "UN", "2001CSO US NU"
dct.Add "UO", "2001CSOC80/20"
dct.Add "UP", "2001CSO UN LU"
dct.Add "UR", "80CSONSU40"
dct.Add "US", "80CSOSKU40"
dct.Add "UX", "2001CSOC40/60"
dct.Add "U0", "80CSO-E ANB"
dct.Add "U2", "80CSO UN ANB"
dct.Add "U4", "80CSO US ANB"
dct.Add "U6", "80CSO U ALB"
dct.Add "U8", "80CSO UN ALB"
dct.Add "4B", "1941 SI ALB"
dct.Add "4D", "41 130%SI ANB"
dct.Add "4E", "1961 CSI  ALB"
dct.Add "4F", "1949 A FEMALE"
dct.Add "4G", "1941 SI ANB"
dct.Add "4I", "1941 SSI ANB"
dct.Add "4J", "1961 CSI ANB"

Set MortalityTableDictionary = dct
Set dct = Nothing
End Function

'Public Function RateclassDictionary() As Dictionary
'Dim dct As Dictionary
'Set dct = New Dictionary
'
'dct.ADD "A", "NONSMOKER"
'dct.ADD "B", "SMOKER"
'dct.ADD "D", "PREFERRED"
'dct.ADD "E", "NONTOBACCO PREF BEST"
'dct.ADD "F", "NONTOBACCO PREF PLUS"
'dct.ADD "G", "NONTOBACCO PREFERRED"
'dct.ADD "H", "NON TOBACCO STANDARD"
'dct.ADD "I", "TOBACCO PREFERRED   "
'dct.ADD "J", "STANDARD"
'dct.ADD "K", "NONSMOKER OR TOBACCO STANDARD"
'dct.ADD "L", "GUARANTEED ISSUE"
'dct.ADD "N", "NONSMOKER"
'dct.ADD "P", "PREFERRED NON-SMOKER"
'dct.ADD "Q", "PREFERRED SMOKER"
'dct.ADD "R", "PREFERRED PLUS NONSMOKER"
'dct.ADD "S", "SMOKER"
'dct.ADD "T", "STANDARD PLUS NONSMOKER"
'dct.ADD "V", "STANDARD            "
'dct.ADD "X", "STANDARD"
'dct.ADD "Y", "SUBSTANDARD"
'dct.ADD "0", "RATES DO NOT VARY BY CLASS"
'
'Set RateclassDictionary = dct
'Set dct = Nothing
'End Function
Public Function RateclassDictionary() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

dct.Add "A", "NONSMOKER"
dct.Add "B", "SMOKER"
dct.Add "D", "PREFERRED"
dct.Add "E", "NONTOBACCO PREF BEST"
dct.Add "F", "NONTOBACCO PREF PLUS"
dct.Add "G", "NONTOBACCO PREFERRED"
dct.Add "H", "NON TOBACCO STANDARD"
dct.Add "I", "TOBACCO PREFERRED   "
dct.Add "J", "STANDARD"
dct.Add "K", "NONSMOKER OR TOBACCO STANDARD"
dct.Add "L", "GUARANTEED ISSUE"
dct.Add "N", "Standard Nicotine Non User"
dct.Add "P", "Preferred Nicotine Non User"
dct.Add "Q", "Preferred Nicotine User"
dct.Add "R", "Preferred Plus Nicotine Non User"
dct.Add "S", "Standard Nicotine User"
dct.Add "T", "Standard Plus Nicotine Non User"
dct.Add "V", "STANDARD            "
dct.Add "X", "STANDARD"
dct.Add "Y", "SUBSTANDARD"
dct.Add "0", "RATES DO NOT VARY BY CLASS"

Set RateclassDictionary = dct
Set dct = Nothing
End Function

Public Function ANICO_RateclassOrder() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

'ANICO
dct.Add "R", 6
dct.Add "P", 5
dct.Add "T", 4
dct.Add "N", 3
dct.Add "Q", 2
dct.Add "S", 1


Set ANICO_RateclassOrder = dct
End Function
Public Function FFL_RateclassOrder() As Dictionary
Dim dct As Dictionary
Set dct = New Dictionary

'Older FFL
dct.Add "E", 6
dct.Add "F", 5
dct.Add "G", 4
dct.Add "H", 3
dct.Add "I", 2
dct.Add "K", 1

Set FFL_RateclassOrder = dct
End Function
Public Function SexCodeDictionary()
Dim dct As Dictionary
Set dct = New Dictionary


dct.Add "T", "Unisex 100/0 or 30/70"
dct.Add "U", "Unisex 80/20"
dct.Add "X", "Unisex 30/70"
dct.Add "Y", "Unisex 20/80"
dct.Add "1", "Male"
dct.Add "2", "Female"

Set SexCodeDictionary = dct
Set dct = Nothing
End Function

Public Function TranslateBillFormCode(vntCode As Variant) As String
Dim tempValue As String

Select Case CStr(vntCode)
  Case "0": tempValue = "Direct pay notice"
  Case "1", "A": tempValue = "Home office"
  Case "2", "B": tempValue = "Permanent APL"
  Case "3", "C": tempValue = "Premium depositor fund"
  Case "4": tempValue = "Discounted premium deposit"
  Case "6", "F": tempValue = "Government allotment"
  Case "7", "G": tempValue = "PAC"
  Case "8", "H": tempValue = "Salary deduction"
  Case "9", "I": tempValue = "Bank deduction"
  Case "J": tempValue = "Dividend"
  Case "Q ": tempValue = "Permanent APP"
  Case "V": tempValue = "Net vanish (offset) premium"
  Case Else: tempValue = vntCode
End Select
TranslateBillFormCode = tempValue
End Function

Public Function LivesCoveredDictionary()
Dim dct As Dictionary
Set dct = New Dictionary


dct.Add "0", "Proposed Insured or Joint Insureds"
dct.Add "1", "Proposed insured, spouse, and dependents"
dct.Add "2", "Spouse and dependents"
dct.Add "3", "Single dependents"
dct.Add "4", "Proposed insured, spouse, and dependents"
dct.Add "5", "Spouse and dependents"
dct.Add "6", "Dependents only"
dct.Add "7", "Proposed insured and dependents"
dct.Add "8", "Proposed insured and dependents"
dct.Add "A", "Family medical expense"


Set LivesCoveredDictionary = dct
Set dct = Nothing

End Function

Public Function GetFrequency(ModeCode As String) As Integer
Dim tempValue As Integer
Select Case ModeCode
    Case "A":   tempValue = 1
    Case "S": tempValue = 2
    Case "Q": tempValue = 4
    Case "M": tempValue = 12
    Case "B": tempValue = 26
End Select
GetFrequency = tempValue
End Function
'PolicyRecord 58 segment
'LH_POL_TARGET
'AL Additional level premium amount
'AP Total additional premiums in the first plan defined number of policy years
'AS Additional single premium amount.
'AT Planned 1035 exchange premium.
'IP Initial net annual premium surrender target.
'IX Guaranteed accumulation value.
'LT Premium target
'MA Accumulative minimum premium.
'MT Minimum annual premium target (MAP).
'NS DEFRA net single premium, basic insured.
'NT DEFRA net single premium, other coverages.
'PR Pro rata premium.
'RE Re-entry premium.
'RP Return of premium
'SA
'SV
'TA Total TEFRA/DEFRA guideline level premium (GLP).
'TD Target death benefit.
'TS Total TEFRA/DEFRA guideline single premium (GSP).
'XP Policy protection account 1.


'LH_COV_TARGET
'TAR_TYP_CD
'IP Initial net annual premium surrender target.
'OI Option charge increase.
'PE
'ST Surrender target premium.
'TB Adjusted premium.
'XP Policy protection account 1.
'XQ Policy protection account 2.

'LH_COM_TARGET
'TAR_TYP_CD
'CA Total commissionable premiums paid toward target.
'CP Total commissionable premium paid.
'CT Commission target premium.
'VC

