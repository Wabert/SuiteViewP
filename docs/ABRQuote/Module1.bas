Attribute VB_Name = "Module1"
Public mdlConn As ADODB.Connection

Sub GetPolicyInfo()

  Application.Calculate
  
  Dim tempRange As String
  Dim CurrPolicyNumber As String
  Dim PolicyNumberWS As Worksheet
  Dim Row As Integer
    
  ThisWorkbook.Activate
  Set PolicyNumberWS = Range("sPolicyNumber").Worksheet

    
    AuditTab.Activate
    AuditTab.Range(Cells(4, 1), Cells(65536, 230)).ClearContents
        
    TestPolicyCoverageHeadings = fncPolicyCoverageHeadings()
    TestPolicyValuesHeadings = fncPolicyValuesHeadings()
    TestPolicyBenefitsHeadings = fncPolicyBenefitsHeadings()
    TestPolicyTargetsHeadings = fncPolicyTargetsHeadings()
    TestPolicyStatusHeadings = fncPolicyStatusHeadings()
    TestPolicyNamesHeadings = fncPolicyNamesHeadings()
    TestPolicyDividendsHeadings = fncPolicyDividendsHeadings()
    
    Range("sAUDIT_Illustrate_Test").Value = ""
    Range("sAUDIT_Error_Message").Value = ""
    AuditTab.Activate
    
    tempRange = Range(Cells(4, 1), Cells(4, 1 + UBound(TestPolicyCoverageHeadings, 2))).Address
    Range(tempRange) = TestPolicyCoverageHeadings
    tempRange = Range(Cells(4, 16), Cells(4, 16 + UBound(TestPolicyValuesHeadings, 2))).Address
    Range(tempRange) = TestPolicyValuesHeadings
    tempRange = Range(Cells(4, 26), Cells(4, 26 + UBound(TestPolicyBenefitsHeadings, 2))).Address
    Range(tempRange) = TestPolicyBenefitsHeadings
    tempRange = Range(Cells(4, 45), Cells(4, 45 + UBound(TestPolicyTargetsHeadings, 2))).Address
    Range(tempRange) = TestPolicyTargetsHeadings
    tempRange = Range(Cells(4, 54), Cells(4, 54 + UBound(TestPolicyStatusHeadings, 2))).Address
    Range(tempRange) = TestPolicyStatusHeadings
    tempRange = Range(Cells(4, 63), Cells(4, 63 + UBound(TestPolicyNamesHeadings, 2))).Address
    Range(tempRange) = TestPolicyNamesHeadings
    tempRange = Range(Cells(4, 69), Cells(4, 69 + UBound(TestPolicyDividendsHeadings, 2))).Address
    Range(tempRange) = TestPolicyDividendsHeadings
  
    PolicyNumberWS.Activate
    Range("sPolicyNumber").Select
    
    For Each C In ActiveCell
        CurrPolicyNumber = C.Value
        
        
        l = ActiveCell.CurrentRegion.Address
        TestPolicyCoverage = fncPolicyCoverage(CurrPolicyNumber)
        TestPolicyValues = fncPolicyValues(CurrPolicyNumber)
        TestPolicyBenefits = fncPolicyBenefits(CurrPolicyNumber)
        TestPolicyTargets = fncPolicyTargets(CurrPolicyNumber)
        TestPolicyStatus = fncPolicyStatus(CurrPolicyNumber)
        TestPolicyNames = fncPolicyNames(CurrPolicyNumber)
        TestPolicyDividends = fncPolicyDividends(CurrPolicyNumber)
    
        AuditTab.Activate
        Cells(4, 1).Select
      ' Selection.End(xlDown).Select
    
        If ActiveCell.Row = 65536 Then
            Row = 4
        Else
            Row = ActiveCell.Row + 1
        End If
    
        Cells(4, 1).Select
    
        tempRange = Range(Cells(Row, 1), Cells(Row + UBound(TestPolicyCoverage), 1 + UBound(TestPolicyCoverage, 2))).Address
        Range(tempRange) = TestPolicyCoverage
        tempRange = Range(Cells(Row, 16), Cells(Row + UBound(TestPolicyValues), 16 + UBound(TestPolicyValues, 2))).Address
        Range(tempRange) = TestPolicyValues
        tempRange = Range(Cells(Row, 26), Cells(Row + UBound(TestPolicyBenefits), 26 + UBound(TestPolicyBenefits, 2))).Address
        Range(tempRange) = TestPolicyBenefits
        tempRange = Range(Cells(Row, 45), Cells(Row + UBound(TestPolicyTargets), 45 + UBound(TestPolicyTargets, 2))).Address
        Range(tempRange) = TestPolicyTargets
        tempRange = Range(Cells(Row, 54), Cells(Row + UBound(TestPolicyStatus), 54 + UBound(TestPolicyStatus, 2))).Address
        Range(tempRange) = TestPolicyStatus
        tempRange = Range(Cells(Row, 63), Cells(Row + UBound(TestPolicyNames), 63 + UBound(TestPolicyNames, 2))).Address
        Range(tempRange) = TestPolicyNames
        tempRange = Range(Cells(Row, 69), Cells(Row + UBound(TestPolicyDividends), 69 + UBound(TestPolicyDividends, 2))).Address
        Range(tempRange) = TestPolicyDividends
    
    Next
Worksheets("Inputs").Activate
End Sub

Function fncPolicyCoverageHeadings()

  Dim aryHeadings(0, 14)
  
    aryHeadings(0, 0) = "Policy Number"
    aryHeadings(0, 1) = "Plancode"
    aryHeadings(0, 2) = "Form Number"
    aryHeadings(0, 3) = "Issue Date"
    aryHeadings(0, 4) = "Cease Date"
    aryHeadings(0, 5) = "Units"
    aryHeadings(0, 6) = "Value per Unit"
    aryHeadings(0, 7) = "Issue Age"
    aryHeadings(0, 8) = "Sex"
    aryHeadings(0, 9) = "Rateclass"
    aryHeadings(0, 10) = "Table Rating"
    aryHeadings(0, 11) = "Flat Extra (Monthly)"
    aryHeadings(0, 12) = "Flat Extra (Monthly)"
    aryHeadings(0, 13) = "Flat Cease Date"
    aryHeadings(0, 14) = "Flat Cease Date"

  fncPolicyCoverageHeadings = aryHeadings
  
End Function

Function fncPolicyValuesHeadings()

  Dim aryHeadings(0, 9)
  
    aryHeadings(0, 0) = "Policy Number"
    aryHeadings(0, 1) = "Last Monthliversary"
    aryHeadings(0, 2) = "Account Value"
    aryHeadings(0, 3) = "Reg Loan Principal"
    aryHeadings(0, 4) = "Reg Loan Accr Int"
    aryHeadings(0, 5) = "Pref Loan Principal"
    aryHeadings(0, 6) = "Pref Loan Accr Int"
    aryHeadings(0, 7) = "Total Prem Paid"
    aryHeadings(0, 8) = "YTD Prem Paid"
    aryHeadings(0, 9) = "CCV Value"

  fncPolicyValuesHeadings = aryHeadings
  
End Function

Function fncPolicyNamesHeadings()

  Dim aryHeadings(0, 5)
  
    aryHeadings(0, 0) = "Policy Number"
    aryHeadings(0, 1) = "Name"
    aryHeadings(0, 2) = "Address 1"
    aryHeadings(0, 3) = "Address 2"
    aryHeadings(0, 4) = "Address 3"
    aryHeadings(0, 5) = "Agent Name"

  fncPolicyNamesHeadings = aryHeadings
  
End Function

Function fncPolicyDividendsHeadings()

  Dim aryHeadings(0, 4)
  
    aryHeadings(0, 0) = "Policy Number"
    aryHeadings(0, 1) = "Curr Div Option"
    aryHeadings(0, 2) = "Total PUA"
    aryHeadings(0, 3) = "Total Div on Deposit"
    aryHeadings(0, 4) = "Int Rate - Div on Deposit"

  fncPolicyDividendsHeadings = aryHeadings
  
End Function

Function fncPolicyBenefitsHeadings()

  Dim aryHeadings(0, 18)
  
    aryHeadings(0, 0) = "Policy Number"
    aryHeadings(0, 1) = "CCV"
    aryHeadings(0, 2) = "CCV Issue Date"
    aryHeadings(0, 3) = "CCV Cease Date"
    aryHeadings(0, 4) = "PW"
    aryHeadings(0, 5) = "PW Issue Date"
    aryHeadings(0, 6) = "PW Cease Date"
    aryHeadings(0, 7) = "PWSTP"
    aryHeadings(0, 8) = "PWSTP Units"
    aryHeadings(0, 9) = "PWSTP Issue Date"
    aryHeadings(0, 10) = "PWSTP Cease Date"
    aryHeadings(0, 11) = "GIO"
    aryHeadings(0, 12) = "GIO Units"
    aryHeadings(0, 13) = "GIO Issue Date"
    aryHeadings(0, 14) = "GIO Cease Date"
    aryHeadings(0, 15) = "ADB"
    aryHeadings(0, 16) = "ADB Units"
    aryHeadings(0, 17) = "ADB Issue Date"
    aryHeadings(0, 18) = "ADB Cease Date"

  fncPolicyBenefitsHeadings = aryHeadings
  
End Function

Function fncPolicyTargetsHeadings()

  Dim aryHeadings(0, 8)
  
    aryHeadings(0, 0) = "Policy Number"
    aryHeadings(0, 1) = "Comm Target"
    aryHeadings(0, 2) = "Monthly MAP"
    aryHeadings(0, 3) = "Accum MAP"
    aryHeadings(0, 4) = "GSP"
    aryHeadings(0, 5) = "Accum GLP"
    aryHeadings(0, 6) = "GLP"
    aryHeadings(0, 7) = "7-Pay Level"
    aryHeadings(0, 8) = "7-Pay Start"

  fncPolicyTargetsHeadings = aryHeadings
  
End Function

Function fncPolicyStatusHeadings()

  Dim aryHeadings(0, 8)
  
    aryHeadings(0, 0) = "Policy Number"
    aryHeadings(0, 1) = "Issue State"
    aryHeadings(0, 2) = "Status"
    aryHeadings(0, 3) = "Suspense"
    aryHeadings(0, 4) = "Mode"
    aryHeadings(0, 5) = "Premium"
    aryHeadings(0, 6) = "Paid-to Date"
    aryHeadings(0, 7) = "DB Option"
    aryHeadings(0, 8) = "Grace Ind"
  
  fncPolicyStatusHeadings = aryHeadings
  
End Function

Function fncPolicyCoverage(PolicyNumber As String)
    'PolicyCoverage returns the following fields: Policy Number, Form, Plancode, Issue Date, Cease Date, Units, Value per Unit,
    ' Issue Age, Sex, Rateclass, Table Rating, Net Monthly Flat 1, Net Monthly Flat 2, Flat 1 Cease Date, Flat 2 Cease Date
  
  Dim tempArray(2, 10), aryQuery()
  Dim ConsolidatedFields As Integer, TotalConsolidatedFields As Integer

    tempArray(0, 0) = "Get_Coverages.PolicyNumber"
    tempArray(1, 0) = 1
    tempArray(2, 0) = "Get_Coverages"
    tempArray(0, 1) = "Get_Coverages.Plancode"
    tempArray(1, 1) = 1
    tempArray(2, 1) = "Get_Coverages"
    tempArray(0, 2) = "Get_Coverages.FormNumber"
    tempArray(1, 2) = 1
    tempArray(2, 2) = "Get_Coverages"
    tempArray(0, 3) = "Get_Coverages.IssueDate"
    tempArray(1, 3) = 1
    tempArray(2, 3) = "Get_Coverages"
    tempArray(0, 4) = "Get_Coverages.CeaseDate"
    tempArray(1, 4) = 1
    tempArray(2, 4) = "Get_Coverages"
    tempArray(0, 5) = "Get_Coverages.Units"
    tempArray(1, 5) = 1
    tempArray(2, 5) = "Get_Coverages"
    tempArray(0, 6) = "Get_Coverages.ValuePerUnit"
    tempArray(1, 6) = 1
    tempArray(2, 6) = "Get_Coverages"
    tempArray(0, 7) = "Get_Coverages.IssueAge"
    tempArray(1, 7) = 1
    tempArray(2, 7) = "Get_Coverages"
    tempArray(0, 8) = "Get_Coverages.Sex"
    tempArray(1, 8) = 1
    tempArray(2, 8) = "Get_Coverages"
    tempArray(0, 9) = "Get_Rateclass.Rateclass"
    tempArray(1, 9) = 1
    tempArray(2, 9) = "Get_Rateclass"
    tempArray(0, 10) = "Get_Substandard.*"
    tempArray(1, 10) = 5
    tempArray(2, 10) = "Get_Substandard"
    
    
    TotalConsolidatedFields = 0
    For i = 0 To UBound(tempArray, 2) - 1
        If tempArray(2, i) = tempArray(2, i + 1) Then
            TotalConsolidatedFields = TotalConsolidatedFields + 1
        End If
    Next
    
    ReDim aryQuery(UBound(tempArray, 1), UBound(tempArray, 2) - TotalConsolidatedFields)
    
    aryQuery(0, 0) = tempArray(0, 0)
    aryQuery(1, 0) = tempArray(1, 0)
    aryQuery(2, 0) = tempArray(2, 0)
   
    ConsolidatedFields = 0
    For i = 1 To UBound(tempArray, 2)
        If tempArray(2, i) = tempArray(2, i - 1) Then
            aryQuery(0, i - 1 - ConsolidatedFields) = "" & aryQuery(0, i - 1 - ConsolidatedFields) & ", " & tempArray(0, i)
            aryQuery(1, i - 1 - ConsolidatedFields) = aryQuery(1, i - 1 - ConsolidatedFields) + tempArray(1, i)
            ConsolidatedFields = ConsolidatedFields + 1
        Else
            aryQuery(0, i - ConsolidatedFields) = tempArray(0, i)
            aryQuery(1, i - ConsolidatedFields) = tempArray(1, i)
            aryQuery(2, i - ConsolidatedFields) = tempArray(2, i)
        End If
    Next
    
    
    'Setup all SQLstatements for aryQuery
    For i = 0 To UBound(aryQuery, 2)
        aryQuery(0, i) = "Select " & aryQuery(0, i) & " FROM " & aryQuery(2, i) & " WHERE " & aryQuery(2, i) & ".PolicyNumber='"
    Next
    
    
    fncPolicyCoverage = fncRunQueries(PolicyNumber, aryQuery)

End Function

Function fncPolicyValues(PolicyNumber As String)
    'PolicyValues returns the following fields: Policy Number, Last Monthliversary, Account Value, Reg Loan Principal,
    ' Reg Loan Interest, Pref Loan Principal, Pref Loan Interest, Total Premiums Paid, YTD Premiums Paid, CCV Value
  
  Dim tempArray(2, 6), aryQuery()
  Dim ConsolidatedFields As Integer, TotalConsolidatedFields As Integer

    tempArray(0, 0) = "Get_Account_Value.PolicyNumber"
    tempArray(1, 0) = 1
    tempArray(2, 0) = "Get_Account_Value"
    tempArray(0, 1) = "Get_Account_Value.Date"
    tempArray(1, 1) = 1
    tempArray(2, 1) = "Get_Account_Value"
    tempArray(0, 2) = "Get_Account_Value.AccountValue"
    tempArray(1, 2) = 1
    tempArray(2, 2) = "Get_Account_Value"
    tempArray(0, 3) = "Get_Loan.Loan, Get_Loan.LoanInt, Get_Loan.LoanType, Get_Loan.IntType"
    tempArray(1, 3) = 4
    tempArray(2, 3) = "Get_Loan"
    tempArray(0, 4) = "Get_Premiums.RegPrem, Get_Premiums.AddPrem"
    tempArray(1, 4) = 1
    tempArray(2, 4) = "Get_Premiums"
    tempArray(0, 5) = "Get_Premiums.YTDPrem"
    tempArray(1, 5) = 1
    tempArray(2, 5) = "Get_Premiums"
    tempArray(0, 6) = "Get_CCV.CCV"
    tempArray(1, 6) = 1
    tempArray(2, 6) = "Get_CCV"
       
       
    TotalConsolidatedFields = 0
    For i = 0 To UBound(tempArray, 2) - 1
        If tempArray(2, i) = tempArray(2, i + 1) Then
            TotalConsolidatedFields = TotalConsolidatedFields + 1
        End If
    Next
    
    ReDim aryQuery(UBound(tempArray, 1), UBound(tempArray, 2) - TotalConsolidatedFields)
    
    aryQuery(0, 0) = tempArray(0, 0)
    aryQuery(1, 0) = tempArray(1, 0)
    aryQuery(2, 0) = tempArray(2, 0)
   
    ConsolidatedFields = 0
    For i = 1 To UBound(tempArray, 2)
        If tempArray(2, i) = tempArray(2, i - 1) Then
            aryQuery(0, i - 1 - ConsolidatedFields) = "" & aryQuery(0, i - 1 - ConsolidatedFields) & ", " & tempArray(0, i)
            aryQuery(1, i - 1 - ConsolidatedFields) = aryQuery(1, i - 1 - ConsolidatedFields) + tempArray(1, i)
            ConsolidatedFields = ConsolidatedFields + 1
        Else
            aryQuery(0, i - ConsolidatedFields) = tempArray(0, i)
            aryQuery(1, i - ConsolidatedFields) = tempArray(1, i)
            aryQuery(2, i - ConsolidatedFields) = tempArray(2, i)
        End If
    Next
    
    
    'Setup all SQLstatements for aryQuery
    For i = 0 To UBound(aryQuery, 2)
        aryQuery(0, i) = "Select " & aryQuery(0, i) & " FROM " & aryQuery(2, i) & " WHERE " & aryQuery(2, i) & ".PolicyNumber='"
    Next
    
    
    fncPolicyValues = fncRunQueries(PolicyNumber, aryQuery)

End Function

Function fncPolicyNames(PolicyNumber As String)
    'PolicyNames returns the following fields: Policy Number, Policyholder Name, Policyholder Address Line 1,
    ' Address Line 2, Address Line 3 (City, State, Zip Code), Agent Name
  
  Dim tempArray(2, 3), aryQuery()
  Dim ConsolidatedFields As Integer, TotalConsolidatedFields As Integer

    tempArray(0, 0) = "Get_Agent.PolicyNumber"
    tempArray(1, 0) = 1
    tempArray(2, 0) = "Get_Agent"
    tempArray(0, 1) = "Get_Name.Prefix, Get_Name.FirstName, Get_Name.MiddleInit, Get_Name.LastName, Get_Name.Suffix"
    tempArray(1, 1) = 1
    tempArray(2, 1) = "Get_Name"
    tempArray(0, 2) = "Get_Address.Address1, Get_Address.Address2, Get_Address.City, Get_Address.State, Get_Address.ZipCode"
    tempArray(1, 2) = 3
    tempArray(2, 2) = "Get_Address"
    tempArray(0, 3) = "Get_Agent.AgentName"
    tempArray(1, 3) = 1
    tempArray(2, 3) = "Get_Agent"
       
       
    TotalConsolidatedFields = 0
    For i = 0 To UBound(tempArray, 2) - 1
        If tempArray(2, i) = tempArray(2, i + 1) Then
            TotalConsolidatedFields = TotalConsolidatedFields + 1
        End If
    Next
    
    ReDim aryQuery(UBound(tempArray, 1), UBound(tempArray, 2) - TotalConsolidatedFields)
    
    aryQuery(0, 0) = tempArray(0, 0)
    aryQuery(1, 0) = tempArray(1, 0)
    aryQuery(2, 0) = tempArray(2, 0)
   
    ConsolidatedFields = 0
    For i = 1 To UBound(tempArray, 2)
        If tempArray(2, i) = tempArray(2, i - 1) Then
            aryQuery(0, i - 1 - ConsolidatedFields) = "" & aryQuery(0, i - 1 - ConsolidatedFields) & ", " & tempArray(0, i)
            aryQuery(1, i - 1 - ConsolidatedFields) = aryQuery(1, i - 1 - ConsolidatedFields) + tempArray(1, i)
            ConsolidatedFields = ConsolidatedFields + 1
        Else
            aryQuery(0, i - ConsolidatedFields) = tempArray(0, i)
            aryQuery(1, i - ConsolidatedFields) = tempArray(1, i)
            aryQuery(2, i - ConsolidatedFields) = tempArray(2, i)
        End If
    Next
    
    
    'Setup all SQLstatements for aryQuery
    For i = 0 To UBound(aryQuery, 2)
        aryQuery(0, i) = "Select " & aryQuery(0, i) & " FROM " & aryQuery(2, i) & " WHERE " & aryQuery(2, i) & ".PolicyNumber='"
    Next
    
    
    fncPolicyNames = fncRunQueries(PolicyNumber, aryQuery)

End Function

Function fncPolicyDividends(PolicyNumber As String)
    'PolicyNames returns the following fields: Policy Number, Policyholder Name, Policyholder Address Line 1,
    ' Address Line 2, Address Line 3 (City, State, Zip Code), Agent Name
  
  Dim tempArray(2, 4), aryQuery()
  Dim ConsolidatedFields As Integer, TotalConsolidatedFields As Integer

    tempArray(0, 0) = "Get_BaseInfo.PolicyNumber"
    tempArray(1, 0) = 1
    tempArray(2, 0) = "Get_BaseInfo"
    tempArray(0, 1) = "Get_BaseInfo.DivOption"
    tempArray(1, 1) = 1
    tempArray(2, 1) = "Get_BaseInfo"
    tempArray(0, 2) = "Get_PUA.PUATotal"
    tempArray(1, 2) = 1
    tempArray(2, 2) = "Get_PUA"
    tempArray(0, 3) = "Get_Dividends_on_Deposit.Amount"
    tempArray(1, 3) = 1
    tempArray(2, 3) = "Get_Dividends_on_Deposit"
    tempArray(0, 4) = "Get_Dividends_on_Deposit.IntRate"
    tempArray(1, 4) = 1
    tempArray(2, 4) = "Get_Dividends_on_Deposit"
       
       
    TotalConsolidatedFields = 0
    For i = 0 To UBound(tempArray, 2) - 1
        If tempArray(2, i) = tempArray(2, i + 1) Then
            TotalConsolidatedFields = TotalConsolidatedFields + 1
        End If
    Next
    
    ReDim aryQuery(UBound(tempArray, 1), UBound(tempArray, 2) - TotalConsolidatedFields)
    
    aryQuery(0, 0) = tempArray(0, 0)
    aryQuery(1, 0) = tempArray(1, 0)
    aryQuery(2, 0) = tempArray(2, 0)
   
    ConsolidatedFields = 0
    For i = 1 To UBound(tempArray, 2)
        If tempArray(2, i) = tempArray(2, i - 1) Then
            aryQuery(0, i - 1 - ConsolidatedFields) = "" & aryQuery(0, i - 1 - ConsolidatedFields) & ", " & tempArray(0, i)
            aryQuery(1, i - 1 - ConsolidatedFields) = aryQuery(1, i - 1 - ConsolidatedFields) + tempArray(1, i)
            ConsolidatedFields = ConsolidatedFields + 1
        Else
            aryQuery(0, i - ConsolidatedFields) = tempArray(0, i)
            aryQuery(1, i - ConsolidatedFields) = tempArray(1, i)
            aryQuery(2, i - ConsolidatedFields) = tempArray(2, i)
        End If
    Next
    
    
    'Setup all SQLstatements for aryQuery
    For i = 0 To UBound(aryQuery, 2)
        aryQuery(0, i) = "Select " & aryQuery(0, i) & " FROM " & aryQuery(2, i) & " WHERE " & aryQuery(2, i) & ".PolicyNumber='"
    Next
    
    
    fncPolicyDividends = fncRunQueries(PolicyNumber, aryQuery)

End Function

Function fncPolicyBenefits(PolicyNumber As String)
    'PolicyBenefits returns the following fields: Policy Number, CCVR Type/Subtype, CCVR Issue Date, CCVR Cease Date,
    ' PW Type/Subtype, PW Issue Date, PW Cease Date, PWSTP Type/Subtype, PWSTP Units, PWSTP Issue Date, PWSTP Cease Date,
    ' GIO Type/Subtype, GIO Units, GIO Issue Date, GIO Cease Date, ADB Type/Subtype, ADB Units, ADB Issue Date, ADB Cease Date
  
  Dim tempArray(2, 1), aryQuery()
  Dim ConsolidatedFields As Integer, TotalConsolidatedFields As Integer

    tempArray(0, 0) = "Get_Benefits.PolicyNumber"
    tempArray(1, 0) = 1
    tempArray(2, 0) = "Get_Benefits"
    tempArray(0, 1) = "Get_Benefits_Sorted.*"
    tempArray(1, 1) = 18
    tempArray(2, 1) = "Get_Benefits_Sorted"
       
       
    TotalConsolidatedFields = 0
    For i = 0 To UBound(tempArray, 2) - 1
        If tempArray(2, i) = tempArray(2, i + 1) Then
            TotalConsolidatedFields = TotalConsolidatedFields + 1
        End If
    Next
    
    ReDim aryQuery(UBound(tempArray, 1), UBound(tempArray, 2) - TotalConsolidatedFields)
    
    aryQuery(0, 0) = tempArray(0, 0)
    aryQuery(1, 0) = tempArray(1, 0)
    aryQuery(2, 0) = tempArray(2, 0)
   
    ConsolidatedFields = 0
    For i = 1 To UBound(tempArray, 2)
        If tempArray(2, i) = tempArray(2, i - 1) Then
            aryQuery(0, i - 1 - ConsolidatedFields) = "" & aryQuery(0, i - 1 - ConsolidatedFields) & ", " & tempArray(0, i)
            aryQuery(1, i - 1 - ConsolidatedFields) = aryQuery(1, i - 1 - ConsolidatedFields) + tempArray(1, i)
            ConsolidatedFields = ConsolidatedFields + 1
        Else
            aryQuery(0, i - ConsolidatedFields) = tempArray(0, i)
            aryQuery(1, i - ConsolidatedFields) = tempArray(1, i)
            aryQuery(2, i - ConsolidatedFields) = tempArray(2, i)
        End If
    Next
    
    
    'Setup all SQLstatements for aryQuery
    For i = 0 To UBound(aryQuery, 2)
        aryQuery(0, i) = "Select " & aryQuery(0, i) & " FROM " & aryQuery(2, i) & " WHERE " & aryQuery(2, i) & ".PolicyNumber='"
    Next
    
    
    fncPolicyBenefits = fncRunQueries(PolicyNumber, aryQuery)

End Function

Function fncPolicyTargets(PolicyNumber As String)
    'PolicyTargets returns the following fields: Policy Number, Commission Target, MAP, Accumulated MAP,
    ' GSP, Accumulated GLP, GLP, 7-Pay
  
  Dim tempArray(2, 5), aryQuery()
  Dim ConsolidatedFields As Integer, TotalConsolidatedFields As Integer

    tempArray(0, 0) = "Get_7Pay.PolicyNumber"
    tempArray(1, 0) = 1
    tempArray(2, 0) = "Get_7Pay"
    tempArray(0, 1) = "Get_Comm_Target.CommTarget"
    tempArray(1, 1) = 1
    tempArray(2, 1) = "Get_Comm_Target"
    tempArray(0, 2) = "Get_MAPs.Type, Get_MAPs.MAP"
    tempArray(1, 2) = 4
    tempArray(2, 2) = "Get_MAPs"
    tempArray(0, 3) = "Get_GLP.GLP"
    tempArray(1, 3) = 1
    tempArray(2, 3) = "Get_GLP"
    tempArray(0, 4) = "Get_7Pay.SevenPay"
    tempArray(1, 4) = 1
    tempArray(2, 4) = "Get_7Pay"
    tempArray(0, 5) = "Get_7Pay.SevenStartDate"
    tempArray(1, 5) = 1
    tempArray(2, 5) = "Get_7Pay"
       
       
    TotalConsolidatedFields = 0
    For i = 0 To UBound(tempArray, 2) - 1
        If tempArray(2, i) = tempArray(2, i + 1) Then
            TotalConsolidatedFields = TotalConsolidatedFields + 1
        End If
    Next
    
    ReDim aryQuery(UBound(tempArray, 1), UBound(tempArray, 2) - TotalConsolidatedFields)
    
    aryQuery(0, 0) = tempArray(0, 0)
    aryQuery(1, 0) = tempArray(1, 0)
    aryQuery(2, 0) = tempArray(2, 0)
   
    ConsolidatedFields = 0
    For i = 1 To UBound(tempArray, 2)
        If tempArray(2, i) = tempArray(2, i - 1) Then
            aryQuery(0, i - 1 - ConsolidatedFields) = "" & aryQuery(0, i - 1 - ConsolidatedFields) & ", " & tempArray(0, i)
            aryQuery(1, i - 1 - ConsolidatedFields) = aryQuery(1, i - 1 - ConsolidatedFields) + tempArray(1, i)
            ConsolidatedFields = ConsolidatedFields + 1
        Else
            aryQuery(0, i - ConsolidatedFields) = tempArray(0, i)
            aryQuery(1, i - ConsolidatedFields) = tempArray(1, i)
            aryQuery(2, i - ConsolidatedFields) = tempArray(2, i)
        End If
    Next
    
    
    'Setup all SQLstatements for aryQuery
    For i = 0 To UBound(aryQuery, 2)
        aryQuery(0, i) = "Select " & aryQuery(0, i) & " FROM " & aryQuery(2, i) & " WHERE " & aryQuery(2, i) & ".PolicyNumber='"
    Next
    
    
    fncPolicyTargets = fncRunQueries(PolicyNumber, aryQuery)

End Function

Function fncPolicyStatus(PolicyNumber As String)
    'PolicyStatus returns the following fields: Policy Number, Issue State, Status, Suspense, Mode, Non-Standard Mode, Paid-to Date, DB Option, Grace Indicator, Billable Premium
  
  Dim tempArray(2, 9), aryQuery()
  Dim ConsolidatedFields As Integer, TotalConsolidatedFields As Integer

    tempArray(0, 0) = "Get_BaseInfo.PolicyNumber"
    tempArray(1, 0) = 1
    tempArray(2, 0) = "Get_BaseInfo"
    tempArray(0, 1) = "Get_BaseInfo.IssueState"
    tempArray(1, 1) = 1
    tempArray(2, 1) = "Get_BaseInfo"
    tempArray(0, 2) = "Get_BaseInfo.Status"
    tempArray(1, 2) = 1
    tempArray(2, 2) = "Get_BaseInfo"
    tempArray(0, 3) = "Get_BaseInfo.Suspense"
    tempArray(1, 3) = 1
    tempArray(2, 3) = "Get_BaseInfo"
    tempArray(0, 4) = "Get_BaseInfo.PymtFreq"
    tempArray(1, 4) = 1
    tempArray(2, 4) = "Get_BaseInfo"
    tempArray(0, 5) = "Get_BaseInfo.NonStdMode"
    tempArray(1, 5) = 1
    tempArray(2, 5) = "Get_BaseInfo"
    tempArray(0, 6) = "Get_BaseInfo.BillPrem"
    tempArray(1, 6) = 1
    tempArray(2, 6) = "Get_BaseInfo"
    tempArray(0, 7) = "Get_BaseInfo.PaidToDate"
    tempArray(1, 7) = 1
    tempArray(2, 7) = "Get_BaseInfo"
    tempArray(0, 8) = "Get_DB_Option.DBOption"
    tempArray(1, 8) = 1
    tempArray(2, 8) = "Get_DB_Option"
    tempArray(0, 9) = "Get_DB_Option.GraceInd"
    tempArray(1, 9) = 1
    tempArray(2, 9) = "Get_DB_Option"
       
       
    TotalConsolidatedFields = 0
    For i = 0 To UBound(tempArray, 2) - 1
        If tempArray(2, i) = tempArray(2, i + 1) Then
            TotalConsolidatedFields = TotalConsolidatedFields + 1
        End If
    Next
    
    ReDim aryQuery(UBound(tempArray, 1), UBound(tempArray, 2) - TotalConsolidatedFields)
    
    aryQuery(0, 0) = tempArray(0, 0)
    aryQuery(1, 0) = tempArray(1, 0)
    aryQuery(2, 0) = tempArray(2, 0)
   
    ConsolidatedFields = 0
    For i = 1 To UBound(tempArray, 2)
        If tempArray(2, i) = tempArray(2, i - 1) Then
            aryQuery(0, i - 1 - ConsolidatedFields) = "" & aryQuery(0, i - 1 - ConsolidatedFields) & ", " & tempArray(0, i)
            aryQuery(1, i - 1 - ConsolidatedFields) = aryQuery(1, i - 1 - ConsolidatedFields) + tempArray(1, i)
            ConsolidatedFields = ConsolidatedFields + 1
        Else
            aryQuery(0, i - ConsolidatedFields) = tempArray(0, i)
            aryQuery(1, i - ConsolidatedFields) = tempArray(1, i)
            aryQuery(2, i - ConsolidatedFields) = tempArray(2, i)
        End If
    Next
    
    
    'Setup all SQLstatements for aryQuery
    For i = 0 To UBound(aryQuery, 2)
        aryQuery(0, i) = "Select " & aryQuery(0, i) & " FROM " & aryQuery(2, i) & " WHERE " & aryQuery(2, i) & ".PolicyNumber='"
    Next
    
    
    fncPolicyStatus = fncRunQueries(PolicyNumber, aryQuery)

End Function

Function fncRunQueries(PolicyNumber As String, aryQuery As Variant)
  Dim DataBaseReference As String
  Dim Cmd As ADODB.Command
  Dim DataSet As ADODB.Recordset
  Dim tempArray As Variant
  Dim tempRange As String
  Dim FinalArray()
  
  Dim PolicyCount As Integer, Row As Integer, QueryNumber As Integer, Column As Integer, SumColumns As Integer
  Dim QueryType As String
  
  
  DataBaseReference = Range("sAUDIT_Queries").Value
  
  'Create connection to the PolicyInfo Access database if needed
  If mdlConn Is Nothing Then
    Set mdlConn = New ADODB.Connection
    'RJH 20170802.  Updated provider to work with 64 bit.
    mdlConn.Open "Provider=Microsoft.ACE.OLEDB.12.0;Data Source=" & DataBaseReference & ";"
    'cn.Open "Provider=Microsoft.Jet.OLEDB.4.0;Data Source=" & DataBaseReference & ";"
    mdlConn.CommandTimeout = 0
  End If
  
  'Define command
  'Set Cmd = New ADODB.Command
  'Set Cmd.ActiveConnection = cn
      
  SumColumns = 0
  For i = 0 To UBound(aryQuery, 2)
    SumColumns = SumColumns + aryQuery(1, i)
  Next
      
  ReDim FinalArray(0, 0)
    
  For j = 0 To UBound(aryQuery, 2)
    QueryNumber = j + 1
    QueryStatement = aryQuery(0, j) & PolicyNumber & "'"
    If j = 0 Then
        Column = aryQuery(1, j) - 1             'Accounts for the fact the first subscript is 0.
    Else
        Column = aryQuery(1, j)
    End If
    QueryType = aryQuery(2, j)
    ReDim Preserve FinalArray(UBound(FinalArray, 1), UBound(FinalArray, 2) + Column)
        
    'Open Recordset
    Set DataSet = New ADODB.Recordset
    'Cmd.CommandText = QueryStatement
    DataSet.Open QueryStatement, mdlConn, adOpenStatic, adLockReadOnly
  
    If Not (DataSet.BOF) Or Not (DataSet.EOF) Then
        DataSet.MoveLast
        DataSet.MoveFirst
        tempArray = DataSet.GetRows(CLng(DataSet.RecordCount))  'RJH 20101206,   'RJH 20170802.  Updated with CLng for 64 bit.
        tempArray = fncTransposeArray(tempArray)
        FinalArray = TranslateQueryResults(tempArray, FinalArray, QueryType, Column)
    End If
            
    DataSet.Close
    Set DataSet = Nothing

  Next
    
    'Clean up not needed since connect is modular level variable.  Closing connection and trying to open it again causes an error
    'mdlConn.Close
    'Set mdlConn = Nothing
  
  
  fncRunQueries = FinalArray
    
End Function
Function SetupResults() As Variant

Dim tempArray(2, 26), tempArray2(), aryQuery()
Dim ExcludedFields As Integer, ConsolidatedFields As Integer, TotalConsolidatedFields As Integer

Dim PolicyNumber As Integer, CovPhase As Integer, Plancode As Integer, FormNumber As Integer, IssueDate As Integer
Dim CeaseDate As Integer, Units As Integer, ValuePerUnit As Integer, IssueAge As Integer, Sex As Integer
Dim RateClass As Integer, DBOption As Integer, Status As Integer, Suspense As Integer, Monthliversary As Integer
Dim AccountValue As Integer, CCVAccountValue As Integer, MAPsAndGuidelines As Integer, SevenPay As Integer, SevenStartDate As Integer

Dim CommTarget As Integer, TotalPremiums As Integer, YTDPremiums As Integer, LoanInfo As Integer
Dim SubstandardInfo As Integer, BenefitInfoNotSorted As Integer, BenefitInfoSorted As Integer


'Rank the fields in the order you want them to appear.  A rank of -1 means that field will be omitted
    PolicyNumber = 1            'Policy Number
    CovPhase = 2                'Coverage Phase Number
    Plancode = 3                'Plancode
    FormNumber = 4              'Policy Form Number
    IssueDate = 5               'Issue Date
    CeaseDate = 6               'Cease Date
    Units = 7                   'Number of Units of Coverage
    ValuePerUnit = 8            'Face Amount of One Unit of Coverage
    IssueAge = 9                'Issue Age associated with Coverage
    Sex = 10                     'Sex Code associated with Coverage
    RateClass = 11               'Rateclass associated with Coverage
    DBOption = 12                'Death Benefit Option
    Status = 13                  'Policy Status (e.g. "Premium-Paying")
    Suspense = 14                'Is the policy in suspense? Y/N
    Monthliversary = 15          'Last Monthliversary Date
    AccountValue = 16            'Account Value as of last monthliversary
    CCV = 17                     'CCV Account Value as of last monthliversary
    MAPsAndGuidelines = 18       'Total 4 fields (Monthly MAP, Accum MAP, GSP, Accum GLP)
    SevenPay = 19                'Level Seven-Pay Premium & Date
    CommTarget = 20              'Commission Target Premium
    TotalPremiums = 21           'Total Premiums Paid as of last monthliversary
    YTDPremiums = 22             'Premiums Paid YTD (by policy year) as of last monthliversary
    LoanInfo = 23                'Includes 4 fields (Reg Loan Principal, Reg Loan Int, Pref Loan Principal, Pref Loan Int)
    SubstandardInfo = 24         'Includes 5 fields (Table, Net Monthly Flat1, Net Monthly Flat2, Flat1 Cease Date, Flat2 Cease Date)
    BenefitInfoNotSorted = 25    'Total 12 fields - Benefits are listed in random order - Includes 4 fields each for 3 benefits (Benefit Type/Subtype, Form Number, Face Amount, Cease Date) - Benefits are listed in any order
    BenefitInfoSorted = 26       'Total 18 fields - Benefits will listed in specific order - CCV, PW, PWSTP, GIO, ADB.  Includes 3 or 4 fields per benefit (Type/Subtype, Units (not included for CCV or PW), Issue Date, Cease Date)
    GLP = 27                     'Guideline Level Premium

    tempArray(0, 0) = "Get_Coverages.PolicyNumber"
    tempArray(1, 0) = PolicyNumber
    tempArray(2, 0) = "Get_Coverages"
    tempArray(0, 1) = "Get_Coverages.CovPhase"
    tempArray(1, 1) = CovPhase
    tempArray(2, 1) = "Get_Coverages"
    tempArray(0, 2) = "Get_Coverages.Plancode"
    tempArray(1, 2) = Plancode
    tempArray(2, 2) = "Get_Coverages"
    tempArray(0, 3) = "Get_Coverages.FormNumber"
    tempArray(1, 3) = FormNumber
    tempArray(2, 3) = "Get_Coverages"
    tempArray(0, 4) = "Get_Coverages.IssueDate"
    tempArray(1, 4) = IssueDate
    tempArray(2, 4) = "Get_Coverages"
    tempArray(0, 5) = "Get_Coverages.CeaseDate"
    tempArray(1, 5) = CeaseDate
    tempArray(2, 5) = "Get_Coverages"
    tempArray(0, 6) = "Get_Coverages.Units"
    tempArray(1, 6) = Units
    tempArray(2, 6) = "Get_Coverages"
    tempArray(0, 7) = "Get_Coverages.ValuePerUnit"
    tempArray(1, 7) = ValuePerUnit
    tempArray(2, 7) = "Get_Coverages"
    tempArray(0, 8) = "Get_Coverages.IssueAge"
    tempArray(1, 8) = IssueAge
    tempArray(2, 8) = "Get_Coverages"
    tempArray(0, 9) = "Get_Coverages.Sex"
    tempArray(1, 9) = Sex
    tempArray(2, 9) = "Get_Coverages"
    tempArray(0, 10) = "Get_Rateclass.Rateclass"
    tempArray(1, 10) = RateClass
    tempArray(2, 10) = "Get_Rateclass"
    tempArray(0, 11) = "Get_DB_Option.DBOption"
    tempArray(1, 11) = DBOption
    tempArray(2, 11) = "Get_DB_Option"
    tempArray(0, 12) = "Get_DB_Option.Status"
    tempArray(1, 12) = Status
    tempArray(2, 12) = "Get_DB_Option"
    tempArray(0, 13) = "Get_DB_Option.Suspense"
    tempArray(1, 13) = Suspense
    tempArray(2, 13) = "Get_DB_Option"
    tempArray(0, 14) = "Get_Account_Value.Date"
    tempArray(1, 14) = Monthliversary
    tempArray(2, 14) = "Get_Account_Value"
    tempArray(0, 15) = "Get_Account_Value.AccountValue"
    tempArray(1, 15) = AccountValue
    tempArray(2, 15) = "Get_Account_Value"
    tempArray(0, 16) = "Get_CCV.CCV"
    tempArray(1, 16) = CCV
    tempArray(2, 16) = "Get_CCV"
    tempArray(0, 17) = "Get_MAPs.Type, Get_MAPs.MAP"
    tempArray(1, 17) = MAPsAndGuidelines
    tempArray(2, 17) = "Get_MAPs"
    tempArray(0, 18) = "Get_7Pay.SevenPay, Get_7Pay.SevenStartDate"
    tempArray(1, 18) = SevenPay
    tempArray(2, 18) = "Get_7Pay"
    tempArray(0, 19) = "Get_Comm_Target.CommTarget"
    tempArray(1, 19) = CommTarget
    tempArray(2, 19) = "Get_Comm_Target"
    tempArray(0, 20) = "Get_Premiums.RegPrem, Get_Premiums.AddPrem"
    tempArray(1, 20) = TotalPremiums
    tempArray(2, 20) = "Get_Premiums"
    tempArray(0, 21) = "Get_Premiums.YTDPrem"
    tempArray(1, 21) = YTDPremiums
    tempArray(2, 21) = "Get_Premiums"
    tempArray(0, 22) = "Get_Loan.Loan, Get_Loan.LoanInt, Get_Loan.LoanType, Get_Loan.IntType"
    tempArray(1, 22) = LoanInfo
    tempArray(2, 22) = "Get_Loan"
    tempArray(0, 23) = "Get_Substandard.*"
    tempArray(1, 23) = SubstandardInfo
    tempArray(2, 23) = "Get_Substandard"
    tempArray(0, 24) = "Get_Benefits_Unsorted.*"
    tempArray(1, 24) = BenefitInfoNotSorted
    tempArray(2, 24) = "Get_Benefits_Unsorted"
    tempArray(0, 25) = "Get_Benefits_Sorted.*"
    tempArray(1, 25) = BenefitInfoSorted
    tempArray(2, 25) = "Get_Benefits_Sorted"
    tempArray(0, 26) = "Get_GLP.GLP"
    tempArray(1, 26) = GLP
    tempArray(2, 26) = "Get_GLP"
    
    ExcludedFields = 0
    For i = 0 To UBound(tempArray, 2)
        If tempArray(1, i) < 0 Then
            ExcludedFields = ExcludedFields + 1
        End If
    Next
    
    ReDim tempArray2(2, UBound(tempArray, 2) - ExcludedFields)
    
    For i = 0 To UBound(tempArray, 2)
        If tempArray(1, i) > 0 Then
            tempArray2(2, tempArray(1, i) - 1) = tempArray(2, i)
            tempArray2(0, tempArray(1, i) - 1) = tempArray(0, i)
            Select Case i   '# of Columns required
                Case 17         'MAPs and Guidelines
                    tempArray2(1, tempArray(1, i) - 1) = 4
                Case 22         'LoanInfo
                    tempArray2(1, tempArray(1, i) - 1) = 4
                Case 23         'SubstandardInfo
                    tempArray2(1, tempArray(1, i) - 1) = 5
                Case 24         'BenefitInfoNotSorted
                    tempArray2(1, tempArray(1, i) - 1) = 12
                Case 25         'BenefitInfoSorted
                    tempArray2(1, tempArray(1, i) - 1) = 18
                Case Else
                    tempArray2(1, tempArray(1, i) - 1) = 1
            End Select
        End If
    Next
    
    TotalConsolidatedFields = 0
    For i = 0 To UBound(tempArray2, 2) - 1
        If tempArray2(2, i) = tempArray2(2, i + 1) Then
            TotalConsolidatedFields = TotalConsolidatedFields + 1
        End If
    Next
    
    ReDim aryQuery(UBound(tempArray2, 1), UBound(tempArray2, 2) - TotalConsolidatedFields)
    
    aryQuery(0, 0) = tempArray2(0, 0)
    aryQuery(1, 0) = tempArray2(1, 0)
    aryQuery(2, 0) = tempArray2(2, 0)
   
    ConsolidatedFields = 0
    For i = 1 To UBound(tempArray2, 2)
        If tempArray2(2, i) = tempArray2(2, i - 1) Then
            aryQuery(0, i - 1 - ConsolidatedFields) = "" & aryQuery(0, i - 1 - ConsolidatedFields) & ", " & tempArray2(0, i)
            aryQuery(1, i - 1 - ConsolidatedFields) = aryQuery(1, i - 1 - ConsolidatedFields) + tempArray2(1, i)
            ConsolidatedFields = ConsolidatedFields + 1
        Else
            aryQuery(0, i - ConsolidatedFields) = tempArray2(0, i)
            aryQuery(1, i - ConsolidatedFields) = tempArray2(1, i)
            aryQuery(2, i - ConsolidatedFields) = tempArray2(2, i)
        End If
    Next
    
    
    'Setup all SQLstatements for aryQuery
    For i = 0 To UBound(aryQuery, 2)
        aryQuery(0, i) = "Select " & aryQuery(0, i) & " FROM " & aryQuery(2, i) & " WHERE " & aryQuery(2, i) & ".PolicyNumber='"
    Next
    
    SetupResults = aryQuery
    
End Function

Function TranslateQueryResults(tempArray As Variant, FinalArray(), QueryType As String, Column As Integer)
    
  Dim tempCaseSelect As String, tempPolicyNumber As String
  Dim FinalUpperBound1 As Integer, FinalUpperBound2 As Integer, tempUpperBound1 As Integer, tempUpperBound2 As Integer
  Dim maxCovPhase As Integer
  
    tempUpperBound1 = UBound(tempArray, 1)
    tempUpperBound2 = UBound(tempArray, 2)
    FinalUpperBound1 = UBound(FinalArray, 1)
    FinalUpperBound2 = UBound(FinalArray, 2) - Column       'This is the last subscript already filled
    
    If IsEmpty(FinalArray(0, 0)) Then
        ReDim FinalArray(tempUpperBound1, FinalUpperBound2 + Column)
        FinalUpperBound2 = -1               'For the first set of information, -1 is the actual "last" subscript
    End If
    
    Select Case QueryType
        Case "Get_BaseInfo"
            For k = 0 To tempUpperBound2
                If k < 4 Then
                    FinalArray(0, FinalUpperBound2 + k + 1) = tempArray(0, k)
                ElseIf k = 4 Then
                    tempCaseSelect = tempArray(0, k)
                    Select Case tempCaseSelect
                        Case 12
                            FinalArray(0, FinalUpperBound2 + k + 1) = "A"
                        Case 6
                            FinalArray(0, FinalUpperBound2 + k + 1) = "S"
                        Case 3
                            FinalArray(0, FinalUpperBound2 + k + 1) = "Q"
                        Case 1
                            FinalArray(0, FinalUpperBound2 + k + 1) = "M"
                        Case Else
                            FinalArray(0, FinalUpperBound2 + k + 1) = tempArray(0, k)
                    End Select
                ElseIf k = 5 Then
                    tempCaseSelect = tempArray(0, k)
                    Select Case tempCaseSelect        'Overwriting prior field of "M" for monthly with non-standard mode
                        Case "2"
                            FinalArray(0, FinalUpperBound2 + k) = "B"   'Bi-weekly
                        Case "S"
                            FinalArray(0, FinalUpperBound2 + k) = "SM"  'Semi-Monthly
                        Case "T"
                            FinalArray(0, FinalUpperBound2 + k) = "T"   'Tenthly
                        Case "1"
                            FinalArray(0, FinalUpperBound2 + k) = "W"   'Weekly
                        Case "4", "9"
                            FinalArray(0, FinalUpperBound2 + k) = tempArray(0, k)   'Ninethly or Every 4 weeks
                        Case Else
                    End Select
                ElseIf k > 5 Then
                    FinalArray(0, FinalUpperBound2 + k) = tempArray(0, k)
                End If
            Next
'            If tempUpperBound2 > 1 Then
'                tempCaseSelect = tempArray(0, 1)
'                Select Case tempCaseSelect
'                    Case 11, 12, 13
'                        FinalArray(0, FinalUpperBound2 + 3) = "Pending"
'                    Case 21, 22
'                        FinalArray(0, FinalUpperBound2 + 3) = "Premium-Paying"
'                    Case 31, 32, 33, 34
'                        FinalArray(0, FinalUpperBound2 + 3) = "PW Active"
'                    Case 41, 42, 43, 46
'                        FinalArray(0, FinalUpperBound2 + 3) = "Paid-up"
'                    Case 44
'                        FinalArray(0, FinalUpperBound2 + 3) = "ETI"
'                    Case 45
'                        FinalArray(0, FinalUpperBound2 + 3) = "RPU"
'                    Case 47
'                        FinalArray(0, FinalUpperBound2 + 3) = "Coverages on both ETI and RPU"
'                    Case 49
'                        FinalArray(0, FinalUpperBound2 + 3) = "Annuitization"
'                    Case 97
'                        FinalArray(0, FinalUpperBound2 + 3) = "Reinstatement Pending"
'                    Case 98
'                        FinalArray(0, FinalUpperBound2 + 3) = "Policy Never Issued"
'                    Case 99
'                        FinalArray(0, FinalUpperBound2 + 3) = "Terminated"
'                    Case Else
'                        FinalArray(0, FinalUpperBound2 + 3) = "Unknown"
'                End Select
'            End If
'            If tempUpperBound2 > 1 Then
'                If tempArray(0, 2) = 2 Then
'                    FinalArray(0, FinalUpperBound2 + 4) = "Yes"
'                Else
'                    FinalArray(0, FinalUpperBound2 + 4) = "No"
'                End If
'            End If
        Case "Get_CCV"
            For j = 0 To tempUpperBound1
                For k = 0 To tempUpperBound2
                    FinalArray(j, FinalUpperBound2 + k + 1) = tempArray(j, k)
                Next
            Next
        Case "Get_MAPs"
            For j = 0 To tempUpperBound1
                tempCaseSelect = tempArray(j, 0)
                Select Case tempCaseSelect
                    Case "MA"
                        FinalArray(0, FinalUpperBound2 + 2) = tempArray(j, 1)
                    Case "MT"
                        FinalArray(0, FinalUpperBound2 + 1) = tempArray(j, 1)
                    Case "TS"
                        FinalArray(0, FinalUpperBound2 + 3) = tempArray(j, 1)
                    Case "TA"
                        FinalArray(0, FinalUpperBound2 + 4) = tempArray(j, 1)
                    Case Else
                End Select
            Next
        Case "Get_Premiums"
            Select Case tempUpperBound2
                Case 0
                    FinalArray(0, FinalUpperBound2 + 1) = tempArray(0, 0)
                Case 1
                    FinalArray(0, FinalUpperBound2 + 1) = tempArray(0, 0) + tempArray(0, 1)
                Case 2
                    FinalArray(0, FinalUpperBound2 + 1) = tempArray(0, 0) + tempArray(0, 1)
                    FinalArray(0, FinalUpperBound2 + 2) = tempArray(0, 2)
            End Select
        Case "Get_Loan"
            If tempArray(0, 2) = 1 Then
                FinalArray(0, FinalUpperBound2 + 3) = tempArray(0, 0)
                FinalArray(0, FinalUpperBound2 + 4) = tempArray(0, 1)
                If tempUpperBound1 > 0 Then
                    If tempArray(1, 2) = 0 Then
                        FinalArray(0, FinalUpperBound2 + 1) = tempArray(1, 0)
                        FinalArray(0, FinalUpperBound2 + 2) = tempArray(1, 1)
                    End If
                End If
            Else
                FinalArray(0, FinalUpperBound2 + 1) = tempArray(0, 0)
                FinalArray(0, FinalUpperBound2 + 2) = tempArray(0, 1)
                If tempUpperBound1 > 0 Then
                    If tempArray(1, 2) = 1 Then
                        FinalArray(0, FinalUpperBound2 + 3) = tempArray(1, 0)
                        FinalArray(0, FinalUpperBound2 + 4) = tempArray(1, 1)
                    End If
                End If
            End If
            If tempArray(0, 3) = 1 Then
                FinalArray(0, FinalUpperBound2 + 2) = 0
                FinalArray(0, FinalUpperBound2 + 4) = 0
            End If
        Case "Get_Substandard"
            For i = 0 To tempUpperBound1
                If tempArray(i, 2) = "  " Then
                    If FinalArray(tempArray(i, 1) - 1, FinalUpperBound2 + 2) = "" Then
                        FinalArray(tempArray(i, 1) - 1, FinalUpperBound2 + 2) = tempArray(i, 4)
                        FinalArray(tempArray(i, 1) - 1, FinalUpperBound2 + 4) = tempArray(i, 5)
                    Else
                        FinalArray(tempArray(i, 1) - 1, FinalUpperBound2 + 3) = tempArray(i, 4)
                        FinalArray(tempArray(i, 1) - 1, FinalUpperBound2 + 5) = tempArray(i, 5)
                    End If
                Else
                    FinalArray(tempArray(i, 1) - 1, FinalUpperBound2 + 1) = tempArray(i, 2)
                End If
            Next
        Case "Get_Benefits_Unsorted"
            For i = 0 To tempUpperBound1
                If FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 5) = "" Then
                    If FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 1) = "" Then
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 1) = tempArray(i, 1) & tempArray(i, 2)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 2) = tempArray(i, 3)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 3) = tempArray(i, 6) * tempArray(i, 7)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 4) = tempArray(i, 5)
                    Else
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 5) = tempArray(i, 1) & tempArray(i, 2)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 6) = tempArray(i, 3)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 7) = tempArray(i, 6) * tempArray(i, 7)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 8) = tempArray(i, 5)
                    End If
                Else
                    FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 9) = tempArray(i, 1) & tempArray(i, 2)
                    FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 10) = tempArray(i, 3)
                    FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 11) = tempArray(i, 6) * tempArray(i, 7)
                    FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 12) = tempArray(i, 5)
                End If
            Next
        Case "Get_Benefits_Sorted"
            maxCovPhase = FinalUpperBound1
            For i = 0 To tempUpperBound1
                If tempArray(i, 0) - 1 > maxCovPhase Then
                    maxCovPhase = tempArray(i, 0) - 1
                End If
            Next
            If maxCovPhase > FinalUpperBound1 Then
                tempPolicyNumber = FinalArray(0, 0)
                ReDim FinalArray(maxCovPhase, FinalUpperBound2 + Column)
                For i = 0 To UBound(FinalArray, 1)
                    FinalArray(i, 0) = tempPolicyNumber
                Next
            End If
            For i = 0 To tempUpperBound1
                tempCaseSelect = tempArray(i, 1)
                Select Case tempCaseSelect
                    Case "A"                'CCV
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 1) = tempArray(i, 1) & tempArray(i, 2)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 2) = tempArray(i, 4)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 3) = tempArray(i, 5)
                    Case "1"                'ADB
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 15) = tempArray(i, 1) & tempArray(i, 2)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 16) = tempArray(i, 6)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 17) = tempArray(i, 4)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 18) = tempArray(i, 5)
                    Case "3"                'PW
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 4) = tempArray(i, 1) & tempArray(i, 2)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 5) = tempArray(i, 4)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 6) = tempArray(i, 5)
                    Case "4"                'PWSTP
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 7) = tempArray(i, 1) & tempArray(i, 2)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 8) = tempArray(i, 6)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 9) = tempArray(i, 4)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 10) = tempArray(i, 5)
                    Case "7"                'GIO
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 11) = tempArray(i, 1) & tempArray(i, 2)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 12) = tempArray(i, 6)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 13) = tempArray(i, 4)
                        FinalArray(tempArray(i, 0) - 1, FinalUpperBound2 + 14) = tempArray(i, 5)
                    Case Else
                End Select
            Next
        Case "Get_Name"
            For i = 0 To tempUpperBound1
                For j = 0 To 4
                    tempArray(i, j) = Replace(tempArray(i, j), " ", "", 1, -1, vbTextCompare)
                Next
                
                FinalArray(i, FinalUpperBound2 + 1) = tempArray(i, 0) & " " & tempArray(i, 1) & " " & tempArray(i, 2) & " " & tempArray(i, 3) & " " & tempArray(i, 4)
            Next
        Case "Get_Address"
            For i = 0 To tempUpperBound1
                For j = 0 To 4
                    tempArray(i, j) = Replace(tempArray(i, j), "  ", "", 1, -1, vbTextCompare)
                Next
                
                FinalArray(i, FinalUpperBound2 + 1) = tempArray(i, 0)
                FinalArray(i, FinalUpperBound2 + 2) = tempArray(i, 1)
                FinalArray(i, FinalUpperBound2 + 3) = tempArray(i, 2) & ", " & tempArray(i, 3) & " " & tempArray(i, 4)
            Next
        Case "Get_Agent"
            FinalArray(0, FinalUpperBound2 + 1) = Replace(tempArray(0, 0), "   ", "", 1, -1, vbTextCompare)
        Case Else
            For j = 0 To tempUpperBound1
                For k = 0 To tempUpperBound2
                    FinalArray(j, FinalUpperBound2 + k + 1) = tempArray(j, k)
                Next
            Next
     End Select
     
    TranslateQueryResults = FinalArray
    
End Function

Function fncTransposeArray(tempArray As Variant) As Variant
'RJH 20110110:      Transposes a one or two dimensional array and replaces any NULL
'                   values with zero length string.
Dim NewArray()
Dim currentUpperBound1 As Long
Dim currentLowerBound1 As Long
Dim currentUpperBound2 As Long
Dim currentLowerBound2 As Long

currentUpperBound1 = UBound(tempArray, 1)
currentLowerBound1 = LBound(tempArray, 1)
currentUpperBound2 = UBound(tempArray, 2)
currentLowerBound2 = LBound(tempArray, 2)

ReDim NewArray(currentUpperBound2 - currentLowerBound2, currentUpperBound1 - currentLowerBound1)

For i = currentLowerBound1 To currentUpperBound1
    For j = currentLowerBound2 To currentUpperBound2
        NewArray(j, i) = Nz(tempArray(i, j), "")
    Next
Next

fncTransposeArray = NewArray

End Function


Sub Goal_Seek_Table_Rating()

    'Application.MaxChange = 1E-20
    Range("Table_1") = 0
    Range("Table_2") = 0
       
    If Range("Assessment_Index") = 1 Or Range("Assessment_Index") = 2 Then
            If Range("B34") < 1 Then
                Range("Five_Year_Surv_Dif").GoalSeek _
                    Goal:=0#, _
                    ChangingCell:=Range("Table_1")
            End If
    Else
        If Range("Assessment_Index") = 3 Or Range("Assessment_Index") = 4 Then
            Range("Ten_Year_Surv_Dif").GoalSeek _
                Goal:=0#, _
                ChangingCell:=Range("Table_1")
        Else
            If Range("Assessment_Index") = 5 Then
            Range("Life_Ex_Dif").GoalSeek _
                Goal:=0#, _
                ChangingCell:=Range("Table_1")
            End If
        End If
    End If
    If Range("Assessment_Index") = 6 Then
        Range("Table_1") = Range("Table_Rating_Input")
    End If
    If Range("Assessment_Index") = 7 Then
        Range("Table_1") = Range("B39") / 25
    End If

End Sub

Private Sub Worksheet_Change(ByVal Target As Range)
j = Target.Address
Stop

End Sub

Sub OpenElectionForm()
    Dim strElectionForm As String
    strElectionForm = Range("ElectionFormPath")
    ActiveWorkbook.FollowHyperlink strElectionForm
    Worksheets("Output - Full").Activate
End Sub


Sub OpenDisclosureForm()
    Dim strDiclosureForm As String
    strDiclosureForm = Range("DisclosureFormPath")
    ActiveWorkbook.FollowHyperlink strDiclosureForm
    
End Sub




Sub SaveFile()
Dim path_ As String
    path_ = Range("K7")

Dim name_ As String
    name_ = Range("K8")

With CreateObject("Scripting.FileSystemObject")
    If Not .FolderExists(path_) Then .CreateFolder path_
End With

ThisWorkbook.SaveAs Filename:=path_ & "\" & name_

End Sub

