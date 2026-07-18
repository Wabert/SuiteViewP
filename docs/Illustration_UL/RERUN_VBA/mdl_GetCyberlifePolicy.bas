Attribute VB_Name = "mdl_GetCyberlifePolicy"
Const CONST_TERM_RIDER_MAX = 3

Sub GetPolicyFromCyberlife()

    Dim Pol As cls_PolicyInformation
    Dim Policynumber  As String
    Dim Region As String
    
    Dim CalcStatus
    CalcStatus = Application.Calculation
    Application.Calculation = xlCalculationManual
    
    Region = Range("sQueryRegion")
    Policynumber = Range("sCyberlifePolicyNumber")
    Set Pol = New cls_PolicyInformation
    Pol.Add Policynumber, , "I", Region
    
    Dim dct As Dictionary
    Set dct = Pol.InforceDictionary
    
    Range("sUID") = Application.UserName
    
    PopulateInputSheet dct
    
    PopulateReportData dct
    
    'Clear any manually entered plancodes so they arent queried every time a policy is pulled up.
    Range("vPlancodesAddedManually").ClearContents
    
    Application.Calculation = CalcStatus

End Sub


Private Sub PopulateInputSheet(dctInforce As Dictionary)
Dim dct As Dictionary
Set dct = dctInforce

Range("sBaseCovCount") = ""
Range("sTermRiderCount") = ""
Range("sINPUT_RGA_Indicator") = ""


Range("sINPUT_RGA_Indicator") = dct("Policy")("ReinPartner")

Range("sblnPrintMode").Value = False
Range("sCompany") = dct("Policy")("CompanyCode")
Range("sStatus") = dct("Policy")("StatusCode")
Range("sFormNumber") = Trim(dct("BaseCovs")(1)("FormNumber"))

Range("sPlancode").NumberFormat = "@"
Range("sPlancode") = Trim(dct("BaseCovs")(1)("Plancode"))
Range("sINPUT_CaseDescription") = ""
Range("sINPUT_CaseID") = dct("Policy")("Policynumber")
Range("sINPUT_DOB") = dct("BaseCovs")(1)("PersonDOB")
Range("sINPUT_DialToPremium") = dct("Policy")("DialToPrem")
Range("sINPUT_DialToAge") = dct("Policy")("DialToAge")
Range("sINPUT_Issue_Date") = dct("BaseCovs")(1)("IssueDate")
Range("sINPUT_Issue_Age") = dct("BaseCovs")(1)("IssueAge")
Range("sMD_From_Cyberlife") = dct("Policy")("COICharge") + dct("Policy")("ExpenseCharge") + dct("Policy")("OtherCharge")

If dct("BaseCovs")(1)("Plancode") = "1U135900" Then
    Range("sINPUT_Rate_Sex") = "X" 'The rates for 1U135900 where stored in the ratedata base with sex code X even thought the sex code in Cyberlife is U
Else
    Range("sINPUT_Rate_Sex") = dct("BaseCovs")(1)("Sex")
End If

Range("sINPUT_State") = dct("Policy")("IssueState")
Range("sINPUT_Rateclass") = dct("BaseCovs")(1)("Rateclass")
Range("sINPUT_Table_Rating") = dct("BaseCovs")(1)("TableRating")
Range("sINPUT_Flat_1_Amount") = dct("BaseCovs")(1)("Flat1Annual")
Range("sINPUT_Flat_1_CeaseAge") = dct("BaseCovs")(1)("Flat1CeaseAge")
Range("sINPUT_Flat_2_Amount") = dct("BaseCovs")(1)("Flat2Annual")
Range("sINPUT_Flat_2_CeaseAge") = dct("BaseCovs")(1)("Flat2CeaseAge")


Range("sINPUT_1035_Exchange_Amount") = 0
Range("sINPUT_1035_Exchange_Loan") = 0
Range("sINPUT_1035_Exchange_CostBasis") = 0





Range("sINPUT_PreflLn_Principle") = 0
Range("sINPUT_PreflLn_Accrued") = 0
Range("sINPUT_FixedLn_Principle") = 0
Range("sINPUT_FixedLn_Accrued") = 0
Range("sINPUT_VblLn_Principle") = 0
Range("sINPUT_VblLn_Accrued") = 0


'Set default fund allocations
Range("sINPUT_PremAllocationU1") = 0
Range("sINPUT_PremAllocationIS") = 0
Range("sINPUT_PremAllocationIX") = 0
Range("sINPUT_PremAllocationIC") = 0
Range("sINPUT_PremAllocationIF") = 0
Range("sINPUT_PremAllocationIP") = 0
Range("sINPUT_PremAllocationIR") = 0
Range("sINPUT_PremAllocationNX") = 0
Range("sINPUT_PremAllocationM1") = 0


Range("sInput_RestrictLoansToSV").Value = True


If dctInforce("Policy")("ProductType") = "IUL" Then
    
    Dim Fund
    For Each FundID In dct("PremAllocation").Keys
        If FundID = "U1" Then Range("sINPUT_PremAllocationU1") = dct("PremAllocation")(FundID) / 100
        If FundID = "IS" Then Range("sINPUT_PremAllocationIS") = dct("PremAllocation")(FundID) / 100
        If FundID = "IX" Then Range("sINPUT_PremAllocationIX") = dct("PremAllocation")(FundID) / 100
        If FundID = "IC" Then Range("sINPUT_PremAllocationIC") = dct("PremAllocation")(FundID) / 100
        If FundID = "IF" Then Range("sINPUT_PremAllocationIF") = dct("PremAllocation")(FundID) / 100
        If FundID = "IP" Then Range("sINPUT_PremAllocationIP") = dct("PremAllocation")(FundID) / 100
        If FundID = "IR" Then Range("sINPUT_PremAllocationIR") = dct("PremAllocation")(FundID) / 100
        If FundID = "NX" Then Range("sINPUT_PremAllocationNX") = dct("PremAllocation")(FundID) / 100
        If FundID = "M1" Then Range("sINPUT_PremAllocationM1") = dct("PremAllocation")(FundID) / 100
    Next

Else
    Range("sINPUT_PremAllocationU1") = 1
End If
    
Dim VarLn
Dim FixLn
VarLn = dct("Policy")("VarLoanPrinciple") + dct("Policy")("VarLoanAccrued")
FixLn = dct("Policy")("RegLoanPrinicple") + dct("Policy")("RegLoanAccrued") + dct("Policy")("PrefLoanPriniciple") + dct("Policy")("PrefLoanAccrued")
If VarLn > 0 Then
    Range("sINPUT_Loan_Type") = "Variable"
Else
    If FixLn > 0 Then Range("sINPUT_Loan_Type") = "Fixed"
End If
Range("sINPUT_VblLn_Principle") = dct("Policy")("VarLoanPrinciple")
Range("sINPUT_VblLn_Accrued") = dct("Policy")("VarLoanAccrued")
Range("sINPUT_FixedLn_Principle") = dct("Policy")("RegLoanPrinicple") + dct("Policy")("PrefLoanPriniciple")
Range("sINPUT_FixedLn_Accrued") = dct("Policy")("RegLoanAccrued") + dct("Policy")("PrefLoanAccrued")


Range("sINPUT_PreflLn_Principle") = dct("Policy")("PrefLoanPriniciple")
Range("sINPUT_PreflLn_Accrued") = dct("Policy")("PrefLoanAccrued")
Range("sINPUT_FixedLn_Principle") = dct("Policy")("RegLoanPrinicple")
Range("sINPUT_FixedLn_Accrued") = dct("Policy")("RegLoanAccrued")


'=====================================================================================
'BASE COVERAGES


Range("sINPUT_OriginalSA1") = dct("BaseCovs")(1)("OrigAmount")
Range("sINPUT_CurrentSA1") = dct("BaseCovs")(1)("Amount")
Range("sINPUT_Original_Band_Cov_1") = dct("BaseCovs")(1)("BandAtIssue")


'Set Defaults for second coverage
Range("sINPUT_OriginalSA2") = 0
Range("sINPUT_Original_Band_Cov_2") = 0
Range("sINPUT_CurrentSA2") = 0
Range("sINPUT_IssueDateSA2") = 0
Range("sINPUT_Rateclass_Cov_2") = ""
Range("sINPUT_TableRatingSA2") = 0
Range("sINPUT_IssueAgeSA2") = 0

If dct("BaseCovs").count >= 2 Then
    If dct("BaseCovs")(2)("Status") <> 0 Then   '"Status" of 0 means terminated
        Range("sINPUT_OriginalSA2") = dct("BaseCovs")(2)("OrigAmount")
        Range("sINPUT_CurrentSA2") = dct("BaseCovs")(2)("Amount")
        Range("sINPUT_Original_Band_Cov_2") = dct("BaseCovs")(2)("BandAtIssue")
        Range("sINPUT_IssueDateSA2") = dct("BaseCovs")(2)("IssueDate")
        Range("sINPUT_Rateclass_Cov_2") = dct("BaseCovs")(2)("Rateclass")
        Range("sINPUT_TableRatingSA2") = dct("BaseCovs")(2)("TableRating")
        Range("sINPUT_IssueAgeSA2") = dct("BaseCovs")(2)("IssueAge")
    End If
End If


'Set Defaults for thrid coverage
Range("sINPUT_OriginalSA3") = 0
Range("sINPUT_CurrentSA3") = 0
Range("sINPUT_IssueDateSA3") = 0
Range("sINPUT_Rateclass_Cov_3") = ""
Range("sINPUT_TableRatingSA3") = 0
Range("sINPUT_IssueAgeSA3") = 0

If dct("BaseCovs").count >= 3 Then
    If dct("BaseCovs")(3)("Status") <> 0 Then   '"Status" of 0 means terminated
        Range("sINPUT_OriginalSA3") = dct("BaseCovs")(3)("OrigAmount")
        Range("sINPUT_CurrentSA3") = dct("BaseCovs")(3)("Amount")
        Range("sINPUT_Original_Band_Cov_3") = dct("BaseCovs")(3)("BandAtIssue")
        Range("sINPUT_IssueDateSA3") = dct("BaseCovs")(3)("IssueDate")
        Range("sINPUT_Rateclass_Cov_3") = dct("BaseCovs")(3)("Rateclass")
        Range("sINPUT_TableRatingSA3") = dct("BaseCovs")(3)("TableRating")
        Range("sINPUT_IssueAgeSA3") = dct("BaseCovs")(3)("IssueAge")
    End If
End If

If dct("BaseCovs").count > CONST_MAX_BASE_COV_COUNT Then
    'MsgBox "This policy more then 3 base coverages."
End If


Dim TotalSpecifiedAmount As Double
Dim Cov
For Each Cov In dct("BaseCovs").Items
    If Cov("Status") <> 0 Then      'status of 0 means terminated
        TotalSpecifiedAmount = TotalSpecifiedAmount + Cov("Amount")
    End If
Next

Range("sINPUT_TrueSex") = dct("BaseCovs")(1)("TrueSex")



'=====================================================================================
'BENEFITS

'Set default benefits
Range("sINPUT_PW_Boolean") = False
Range("sINPUT_PWST_Boolean") = False
Range("sINPUT_CCV_Boolean") = False
Range("sINPUT_ShadowBenefit_Active") = False
Range("sINPUT_GIR_Boolean ") = False
Range("sINPUT_ADB_Boolean") = False
Range("sInput_CurrentShadowAV") = 0
Range("sINPUT_ADB_Units") = 0
Range("sINPUT_PW_BenefitCode") = ""
Range("sINPUT_PWST_BenefitCode") = ""
Range("sINPUT_CCV_BenefitCode") = ""
Range("sINPUT_GIR_BenefitCode") = ""
Range("sINPUT_ADB_BenefitCode") = ""
Range("sINPUT_ABRTM_Active") = False
Range("sINPUT_ABRCH_Active") = False
Range("sINPUT_ABRCT_Active") = False
Range("sINPUT_GCO15_Active") = False
Range("sINPUT_GCO20_Active") = False
Range("sINPUT_GCO25_Active") = False
Range("sINPUT_COLA_Active") = False

Dim Ben
For Each Ben In dct("Benefits").Items
    If Ben("CeaseDate") > dctInforce("Policy")("ValuationDate") Then
        If Ben("Name") = "GIO" Then
            Range("sINPUT_GIR_Boolean ") = True
            Range("sINPUT_GIR_Units") = Ben("Amount") / 1000
            Range("sINPUT_GIR_BenefitCode") = Ben("Plancode")
        End If
        If Ben("Name") = "PWoT" Then
            Range("sINPUT_PWST_Boolean") = True
            Range("sINPUT_PWST_Premium") = Ben("Amount")
            Range("sINPUT_PWST_BenefitCode") = Ben("Plancode")
        End If
        If Ben("Name") = "PWoC" Then
            Range("sINPUT_PW_Boolean") = True
            Range("sINPUT_PW_BenefitCode") = Ben("Plancode")
        End If
        
        'Accidential Death Benefit
        If Ben("Name") = "ADB" Then
            Range("sINPUT_ADB_Boolean") = True
            Range("sINPUT_ADB_BenefitCode") = Ben("Plancode")
            'Its possible to have more than one ADB on a policy, so the units are added up
            Range("sINPUT_ADB_Units") = Ben("Amount") / 1000 + Range("sINPUT_ADB_Units")
        End If
        
        'Shadow Account
        If Ben("Name") = "CCV" Then
            Range("sInput_CurrentShadowAV") = dct("Policy")("CCVAV")
            
            ShadowAvailablity = GetPlancodeData(Range("sPlancode"), "ShadowAvailablity")
            
            If ShadowAvailablity = "Rider" Then
                Range("sINPUT_CCV_Boolean") = True
                Range("sINPUT_CCV_BenefitCode") = Ben("Plancode")
                
                'Only populate the amount field if CCV units are different than base.  If this field is blank
                'the spreadsheet defaults to using Base units.  Very few policies have CCV units different than base
                If Ben("Amount") / 1000 <> TotalSpecifiedAmount / 1000 Then
                    Range("sINPUT_CCV_Units") = Ben("Amount") / 1000
                End If
            End If
            
            Range("sINPUT_ShadowBenefit_Active") = True
            
            
        End If
        
        'Accelerated Death Benefit
        If Ben("Name") = "ABRTM" Or Ben("Name") = "ABRLN" Then
            Range("sINPUT_ABRTM_Active") = True
        End If
        If Ben("Name") = "ABRCT" Then
            Range("sINPUT_ABRCT_Active") = True
        End If
        If Ben("Name") = "ABRCH" Then
            Range("sINPUT_ABRCH_Active") = True
        End If
        
        'COLA (which as of 5/12/2022 is only on some FFL ULs)
        If Ben("Name") = "COLA" Then
            Range("sINPUT_COLA_Active") = True
        End If
        
        'Guaranteed Cash Out Rider
        If Ben("Name") = "GCO15" Then
            Range("sINPUT_GCO15_Active") = True
        End If
        If Ben("Name") = "GCO20" Then
            Range("sINPUT_GCO20_Active") = True
        End If
        If Ben("Name") = "GCO25" Then
            Range("sINPUT_GCO25_Active") = True
        End If
    End If
Next



'=====================================================================================
'RIDERS

'Set default rider booleans
Range("sINPUT_R1_Boolean") = False
Range("sINPUT_R2_Boolean") = False
Range("sINPUT_R3_Boolean") = False
Range("sINPUT_R1_SigTerm_Boolean") = False
Range("sINPUT_R2_SigTerm_Boolean") = False
Range("sINPUT_R3_SigTerm_Boolean") = False
Range("sINPUT_APB_Boolean") = False
Range("sINPUT_CTR_Boolean") = False
Range("sINPUT_APB_Face") = 0
Range("sINPUT_Original_APB_SA") = 0
Dim SigTermCount As Integer, TermRiderCount As Integer, CTRCount As Integer
Dim Rdr, RiderRng, RiderCeaseAge As Variant, CeaseAgeDur As Integer, CeaseUseCode As String
Dim RiderType As String
Dim CTRUnits As Double
        
For Each Rdr In dct("RiderCovs").Items
    plcd = Rdr("Plancode")
    If Rdr("Status") <> 0 Then
       
       CeaseAgeDur = GetRiderData(CStr(Rdr("Plancode")), "CeaseAgeDur")
       CeaseUseCode = GetRiderData(CStr(Rdr("Plancode")), "CeaseUseCode")
       RiderType = GetRiderData(CStr(Rdr("Plancode")), "CovType")
       'A value of 0 means rider plancode was not found
        
        'LTR, STR, SIGTERM and Non-ANICO CTR riders, and Rides that are not found in the GetRiderData table will placed in the individual rider slots
        If RiderType = "0" Or RiderType = "LTR" Or RiderType = "STR" Or RiderType = "SIGTERM" Or (RiderType = "CTR" And dct("Policy")("CompanyCode") <> "01") Then
            TermRiderCount = TermRiderCount + 1
            If TermRiderCount > CONST_TERM_RIDER_MAX Then
                'MsgBox "This policy has more than " & CONST_TERM_RIDER_MAX & " active Term Riders.  The spreadsheet can only handle " & CONST_TERM_RIDER_MAX & " riders,", vbOKOnly
            Else
                Range("sINPUT_R" & TermRiderCount & "_Plancode") = Rdr("Plancode")
                Range("sINPUT_R" & TermRiderCount & "_Boolean") = (Rdr("Status") <> "0")
                Range("sINPUT_R" & TermRiderCount & "_Issue_Age") = Rdr("IssueAge")
                Range("sINPUT_R" & TermRiderCount & "_Gender") = Rdr("Sex")
                Range("sINPUT_R" & TermRiderCount & "_Rateclass") = Rdr("Rateclass")
                Range("sINPUT_R" & TermRiderCount & "_Table_Rating") = Rdr("TableRating")
                Range("sINPUT_R" & TermRiderCount & "_Cease_Year") = IIf(CeaseUseCode = "Dur", Rdr("IssueAge") + CeaseAgeDur, CeaseAgeDur)
                Range("sINPUT_R" & TermRiderCount & "_Face") = Rdr("Amount")
                Range("sINPUT_R" & TermRiderCount & "_Primary_Boolean") = (Rdr("PersonCode") = "00")
                Range("sINPUT_R" & TermRiderCount & "_QAB_Boolean") = Rdr("Qualified")
                Range("sINPUT_R" & TermRiderCount & "_Flat_Extra") = Rdr("Flat1")
                Range("sINPUT_R" & TermRiderCount & "_Flat_CeaseAge") = Rdr("Flat1CeaseAge")
                Range("sINPUT_R" & TermRiderCount & "_IssueDate") = Rdr("IssueDate")
                Range("sINPUT_R" & TermRiderCount & "_CeaseDate") = Rdr("MaturityDate")

            End If
        End If

        'ANCIO CTR will be added together and placed in the CTR slot
        'There could be more than one CTR on a policy (very unlikely but its out there).  In that case just add up the CTR units
        If (RiderType = "CTR" And dct("Policy")("CompanyCode") = "01") Then
            CTRCount = CTRCount + 1
            If Rdr("Status") <> "0" Then
                Range("sINPUT_CTR_Boolean") = True
                CTRUnits = Rdr("Amount") / 1000 + CTRUnits
                Range("sINPUT_CTR_Units") = CTRUnits
            End If
        End If
        
        'APB.  Additional Protection Benefit
        If RiderType = "APB" Then
            Range("sINPUT_APB_Boolean") = True
            Range("sINPUT_APB_Face") = Rdr("Amount")
            Range("sINPUT_Original_APB_SA") = Rdr("OrigAmount")
            Range("sINPUT_APB_Plancode") = Rdr("Plancode")
        End If
        
    End If
Next





Range("sINPUT_MAP_CeaseDate") = ""
Range("sINPUT_MonthsTerminatedCov1") = ""
Range("sINPUT_MonthsTerminatedCov2") = ""
Range("sINPUT_MonthsTerminatedCov3") = ""

Range("sINPUT_InforceIndicator") = "Y"
Range("sINPUT_VaryingAssumeRate") = "FALSE"

Set dct = dctInforce("Policy")
Range("sINPUT_MonthsTerminatedCov1") = dct("PolicyMonthsTerminated")
Range("sINPUT_MonthsTerminatedCov2") = dct("PolicyMonthsTerminated")
Range("sINPUT_MonthsTerminatedCov3") = dct("PolicyMonthsTerminated")
Range("sINPUT_IsMEC") = dct("IsMEC")
Range("sINPUT_DBOption") = dct("DBOption")
Range("sINPUT_ValuationDate") = dct("ValuationDate")


Range("sINPUT_7PayStartDate") = dct("TAMRA_StateDate")
Range("sInput_CurrentAV") = dct("MVAV")
Range("sINPUT_SWAM") = 0
If dct("ProductType") = "IUL" Then Range("sINPUT_SWAM") = dct("SWAM")
Range("sINPUT_PremiumYTD") = dct("PremYTD")
Range("sINPUT_PremiumTD") = dct("PremTD")
Range("sINPUT_WithdrawalTD") = dct("AccumWDs")
Range("sINPUT_Accum_Min") = dct("AccumMTP")
Range("sINPUT_MonthlyMTP") = dct("MTP")  'the MTP in cyberlife is always monthly
Range("sINPUT_CTP") = dct("CTP")
Range("sINPUT_MAP_CeaseDate") = dct("MAP_CeaseDate")
Range("sINPUT_CostBasis") = dct("CostBasis")
Range("sINPUT_AccumGLP") = dct("AccumGLP")
Range("sINPUT_Guideline") = dct("GPT_CVAT")
Range("sINPUT_GLP") = dct("GLP")
Range("sINPUT_GSP") = dct("GSP")
Range("sINPUT_7PayPremium") = dct("TAMRA_7PayLevel")
Range("sINPUT_7PayCashValue") = dct("TAMRA_AV")
Range("sINPUT_BillablePrem") = dct("BillablePremium")
Range("sINPUT_BillingMode") = Trim(Left(dct("BillingMode"), 2))
Range("sINPUT_LnRepayAmt") = dct("LoanRepayAmount")
Range("sINPUT_LnRepayMode") = Trim(Left(dct("LoanRepayMode"), 2))
Range("sINPUT_TAMRA_Contribution_Yr_1") = dct("TAMRA_7PayPremiumsPaid")(1) - dct("TAMRA_7PayWithdrawals")(1)
Range("sINPUT_TAMRA_Contribution_Yr_2 ") = dct("TAMRA_7PayPremiumsPaid")(2) - dct("TAMRA_7PayWithdrawals")(2)
Range("sINPUT_TAMRA_Contribution_Yr_3 ") = dct("TAMRA_7PayPremiumsPaid")(3) - dct("TAMRA_7PayWithdrawals")(3)
Range("sINPUT_TAMRA_Contribution_Yr_4 ") = dct("TAMRA_7PayPremiumsPaid")(4) - dct("TAMRA_7PayWithdrawals")(4)
Range("sINPUT_TAMRA_Contribution_Yr_5 ") = dct("TAMRA_7PayPremiumsPaid")(5) - dct("TAMRA_7PayWithdrawals")(5)
Range("sINPUT_TAMRA_Contribution_Yr_6 ") = dct("TAMRA_7PayPremiumsPaid")(6) - dct("TAMRA_7PayWithdrawals")(6)
Range("sINPUT_TAMRA_Contribution_Yr_7 ") = dct("TAMRA_7PayPremiumsPaid")(7) - dct("TAMRA_7PayWithdrawals")(7)
Range("sINPUT_7YrLowestDB") = dct("TAMRA_7PaySpecifiedAmount")



'Default the Rider Inforce Changes
Range("sCTR_Change_Units") = ""
Range("sCTR_Change_Date") = ""
Range("sPW_Change_Active") = ""
Range("sPW_Change_Date") = ""
Range("sPWST_Change_Amount") = ""
Range("sPWST_Change_Date") = ""
Range("sADB_Change_Units") = ""
Range("sADB_Change_Date") = ""
Range("sGIR_Change_Units") = ""
Range("sGIR_Change_Date") = ""
Range("sINPUT_R1_Change_Amount") = ""
Range("sINPUT_R1_Change_Date") = ""
Range("sINPUT_R2_Change_Amount") = ""
Range("sINPUT_R2_Change_Date") = ""
Range("sINPUT_R3_Change_Amount") = ""
Range("sINPUT_R3_Change_Date") = ""
Range("sINPUT_CCV_Change_Date") = ""
Range("sINPUT_APB_Change_Amount") = ""
Range("sINPUT_APB_Change_Date") = ""
Range("sINPUT_Rateclass_Change_NewRateclassCode") = ""
Range("sINPUT_Rateclass_Change_Date") = ""



Set dct = dctInforce

'Deemed Cash Value Default is 0.  Right now (1/21/2022) the DCV is not availabe in DB2 tables and must be looked up manually in Cyberlife
Range("sInput_DeemedCashValue") = 0

'Default lumpsum
Range("sINPUT_Inforce_Lumpsum") = 0
Range("sLumpsum_Date").Formula = "=sINPUT_ForecastDate"

'Populate default array inputs

Range("vINPUT_Specified_Amount").Rows(1) = TotalSpecifiedAmount + IIf(Range("sINPUT_APB_Boolean"), Range("sINPUT_APB_Face"), 0)
Range("vINPUT_DBO").Rows(1) = Range("sINPUT_DBOption")
Range("vINPUT_Premium_Amount").Rows(1) = Range("sINPUT_BillablePrem")
Range("vINPUT_Premium_Mode").Rows(1) = Left(Range("sINPUT_BillingMode"), 1)
Range("vINPUT_Loans").Rows(1) = 0
Range("vINPUT_Loan_Mode").Rows(1) = "A"
Range("vINPUT_Loan_Repayment").Rows(1) = 0
Range("vINPUT_Withdrawal").Rows(1) = 0
Range("vINPUT_Blended_Rate").Rows(1) = Range("sINPUT_Blended_Effective_Rate")


PopulateInputFormulas

Range("sBaseCovCount") = dct("BaseCovs").count
Range("sTermRiderCount") = TermRiderCount

'Populate the current interst rate with the guarnateed interest rate.  That way if you forget to chagne the rate you arent illustrating anything too high
Range("sINPUT_Fixed_Int_Rate") = GetPlancodeData((CStr(dctInforce("BaseCovs")(1)("Plancode"))), "GINT")

'Clear any PDF file name so it doesnt stick around from the previous policy and potential overwrite and existing PDF
Range("sReportFileName") = ""

Range("sINPUT_PayDuration") = ""
Range("sINPUT_LoanDuration") = ""




End Sub

Sub PopulateInputFormulas()
For x = 2 To 121
    Range("vINPUT_Specified_Amount").Rows(x) = "=" & Range("vINPUT_Specified_Amount").Rows(x - 1).Address(False, False)
    Range("vINPUT_DBO").Rows(x) = "=" & Range("vINPUT_DBO").Rows(x - 1).Address(False, False)
    Range("vINPUT_Premium_Amount").Rows(x) = "=" & Range("vINPUT_Premium_Amount").Rows(x - 1).Address(False, False)
    Range("vINPUT_Premium_Mode").Rows(x) = "=" & Range("vINPUT_Premium_Mode").Rows(x - 1).Address(False, False)
    Range("vINPUT_Loans").Rows(x) = "=" & Range("vINPUT_Loans").Rows(x - 1).Address(False, False)
    Range("vINPUT_Loan_Mode").Rows(x) = "=" & Range("vINPUT_Loan_Mode").Rows(x - 1).Address(False, False)
    Range("vINPUT_Loan_Repayment").Rows(x) = 0
    Range("vINPUT_Withdrawal").Rows(x) = 0
    Range("vINPUT_Blended_Rate").Rows(x) = "=" & Range("vINPUT_Blended_Rate").Rows(x - 1).Address(False, Flase)
Next

End Sub


Sub PopulateReportData(dctInforce As Dictionary)
    Range("sReportData_InsuredName") = dctInforce("Policy")("InsuredName")
    Range("sReportData_Address1") = dctInforce("Policy")("InsuredAddress1")
    Range("sReportData_Address2") = dctInforce("Policy")("InsuredAddress2")
    Range("sReportData_AgentName") = dctInforce("Policy")("AgentName")
    Range("sReportData_AgentAddress1") = ""
    Range("sReportData_AgentAddress2") = ""
    
    'Set default Values
    Range("sReportData_SW_AV") = 0
    Range("sReportData_U1_AV") = 0
    Range("sReportData_IS_AV") = 0
    Range("sReportData_IX_AV") = 0
    Range("sReportData_IC_AV") = 0
    Range("sReportData_IF_AV") = 0
    Range("sReportData_IP_AV") = 0
    Range("sReportData_IR_AV") = 0
    Range("sReportData_NX_AV") = 0
    Range("sReportData_M1_AV") = 0
   
    For Each Fund In dctInforce("Funds").Items
        If Fund("FundID") = "SW" Then Range("sReportData_SW_AV") = Fund("FundValue")
        If Fund("FundID") = "U1" Then Range("sReportData_U1_AV") = Fund("FundValue")
        If Fund("FundID") = "IS" Then Range("sReportData_IS_AV") = Fund("FundValue")
        If Fund("FundID") = "IX" Then Range("sReportData_IX_AV") = Fund("FundValue")
        If Fund("FundID") = "IC" Then Range("sReportData_IC_AV") = Fund("FundValue")
        If Fund("FundID") = "IF" Then Range("sReportData_IF_AV") = Fund("FundValue")
        If Fund("FundID") = "IP" Then Range("sReportData_IP_AV") = Fund("FundValue")
        If Fund("FundID") = "IR" Then Range("sReportData_IR_AV") = Fund("FundValue")
        If Fund("FundID") = "NX" Then Range("sReportData_NX_AV") = Fund("FundValue")
        If Fund("FundID") = "M1" Then Range("sReportData_M1_AV") = Fund("FundValue")
        
    Next
    
    Range("sReportData_U1_pct") = Range("sINPUT_PremAllocationU1")
    Range("sReportData_IS_pct") = Range("sINPUT_PremAllocationIS")
    Range("sReportData_IX_pct") = Range("sINPUT_PremAllocationIX")
    Range("sReportData_IC_pct") = Range("sINPUT_PremAllocationIC")
    Range("sReportData_IF_pct") = Range("sINPUT_PremAllocationIF")
    Range("sReportData_IP_pct") = Range("sINPUT_PremAllocationIP")
    Range("sReportData_IR_pct") = Range("sINPUT_PremAllocationIR")
    Range("sReportData_NX_pct") = Range("sINPUT_PremAllocationNX")
    Range("sReportData_M1_pct") = Range("sINPUT_PremAllocationM1")
       
    
End Sub


Public Function IsPlancodePresent(Plancode As String) As Boolean
Dim x As Integer
Dim tempValue As Boolean
tempValue = False

For x = 0 To 7
    If Range("sPlancodesPresent").Offset(x, 0)(1, 1).Value = Plancode Then tempValue = True
Next
IsPlancodePresent = tempValue
End Function


Public Function Traspose2DArray(ary) As Variant
'The WorksheetFunction.Transpose function will convert a 2D array to a 1D array if there is only one row.
'This can cause problems later on with functions expecting a 2D array.  So this function is created to
'always transpose a 2D array into another 2D array

Dim TempArray() As Variant
ReDim TempArray(LBound(ary, 2) To UBound(ary, 2), LBound(ary, 1) To UBound(ary, 1))

For x = LBound(ary, 1) To UBound(ary, 1)
 For y = LBound(ary, 2) To UBound(ary, 2)
    TempArray(y, x) = ary(x, y)
 Next
Next

Traspose2DArray = TempArray

End Function

Public Function GetRiderData(Plancode As String, Header As String) As Variant
Dim col As Integer
Dim rng As Range
    
    Set rng = Range("tRiderDefinitionFile")
    
    col = -1
    'Find what column the header is located
    For x = 1 To rng.Columns.count
        If Header = rng(0, x) Then
            col = x
            Exit For
        End If
    Next

    If col = -1 Then Exit Function
    
    For x = 1 To rng.Rows.count
         If Plancode = Trim(rng(x, 1)) Then
            GetRiderData = rng(x, col)
            Exit Function
        End If
    Next
    GetRiderData = "0"
End Function


Public Function GetPlancodeData(Plancode As String, Header As String) As Variant
Dim col As Integer
Dim rng As Range
    Set rng = Range("tPlancodeTable")

    col = -1
    'Find what column the header is located
    For x = 1 To rng.Columns.count
        If Header = rng(0, x) Then
            col = x
            Exit For
        End If
    Next
    If col = -1 Then Exit Function
    
    'Find the row for the plancode and return the data
    For x = 1 To rng.Rows.count
         If Plancode = Trim(rng(x, 1)) Then
            GetPlancodeData = rng(x, col)
            Exit Function
        End If
    Next
    
End Function




