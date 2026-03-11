# Cyberlife Audit Tool - Criteria Input Classification

This document categorizes all the input types across the first 8 tabs (Policy through Transaction) of the Cyberlife Audit Tool based on the provided screenshots and corresponding VBA source code `frmAudit.frm.bas`.

## Input Categories Identified

1. **Range (Min/Max):** Two separate text inputs placed side by side to specify a lower numerical or chronological bound and an upper bound. Example: Ages, Amounts, Dates.
2. **Combobox (Dropdown):** A single-selection dropdown menu list. 
3. **Checkbox:** A basic boolean toggle for turning a filtering rule on or off.
4. **Text Input:** A single text field for manual text entry. Some are quite small, representing single-character fields.
5. **Checkbox + Multi-select Listbox:** A prevalent pattern where a checkbox is attached to a listbox. The checkbox toggles the inclusion of the rule, and the listbox allows the user to select one or more specific matching values.
6. **Dual-Input (Combobox + Text Input):** A more advanced input where a dropdown specifies the "type" of the input, and an accompanying text box captures the value (e.g., Policy Number Criteria).
7. **Multi-select Listbox:** A standalone listbox allowing the selection of multiple values, differing from category 5 by the absence of a dedicated enabling checkbox.

---

## Fields by Tab (VBA ExcelTool)

### 1. Policy Tab
*   **Plancode:** Text Input (`TextBox_PlancodeAllCovs`)
*   **RGA (52):** Checkbox (`CheckBox_RGA`)
*   **Company:** Combobox (`ComboBox_Company`)
*   **Market:** Combobox (`ComboBox_MarketOrg`)
*   **Form number like:** Text Input (`TextBox_FormNumberLikeAllCovs`)
*   **3 digit Branch #:** Text Input (`TextBox_BranchNumber`)
*   **Policynumber criteria:** Dual-Input (`ComboBox_PolicynumberCriteria` and `TextBox_PolicyNumberContains`)
*   **Issue Age Range:** Range (`TextBox_LowIssueAge` to `TextBox_HighIssueAge`)
*   **Current Age Range:** Range (`TextBox_LowCurrentAge` to `TextBox_HighCurrentAge`)
*   **Current Policy Year:** Range (`TextBox_LowCurrentPolicyYear` to `TextBox_HighCurrentPolicyYear`)
*   **Issue Month Range:** Range (`TextBox_LowIssueMonth` to `TextBox_HighIssueMonth`)
*   **Issue Day Range:** Range (`TextBox_LowIssueDay` to `TextBox_HighIssueDay`)
*   **Issued date Range:** Range (`TextBox_IssuedBefore` to `TextBox_IssuedAfter`)
*   **Paid To Date Range:** Range (`TextBox_LowPaidToDate` to `TextBox_HighPaidToDate`)
*   **GPE Date Range (51 or 66):** Range (`TextBox_LowGPEDate` to `TextBox_HighGPEDate`)
*   **Application Date (01):** Range (`TextBox_LowAppDate` to `TextBox_HighAppDate`)
*   **Billing Prem Amt (01):** Range (`TextBox_LowBillingPrem` to `TextBox_HighBillingPrem`)
*   **Status Code (01):** Checkbox + Listbox (`CheckBox_SpecifyStatusCodes` and `ListBox_StatusCode`)
*   **Product Line Code (02):** Checkbox + Listbox (`CheckBox_SpecifyProductLineCodeAllCovs` and `ListBox_ProductLineCodeAllCovs`)
*   **State:** Checkbox + Listbox (`CheckBox_SpecifyState` and `ListBox_State`)
*   **Bill Mode (01):** Checkbox + Listbox (`CheckBox_SpecifyBillingModes` and `ListBox_BillMode`)
*   **Last Entry Code (01):** Checkbox + Listbox (`CheckBox_SpecifyLastEntryCode` and `ListBox_LastEntryCodes`)
*   **Product Indicator (02) - All covs:** Checkbox + Listbox (`CheckBox_SpecifyProductIndicatorAllCovs` and `ListBox_ProductIndicatorAllCovs`)
*   **Billing Form (01):** Checkbox + Listbox (`CheckBox_SpecifyBillingForm` and `ListBox_BillingForm`)
*   **Grace Indicator (51 or 66):** Checkbox + Listbox (`CheckBox_GraceIndicator` and `ListBox_GraceIndicator`)
*   **Is MDO (59):** Checkbox (`CheckBox_ShowMDOIndicator`)
*   **Multiple Base Covs (02):** Checkbox (`CheckBox_MultiplePlancodes` or `CheckBox_BaseSearchShowPolicies`)
*   **In conversion period (Calc):** Checkbox (`CheckBox_SpecifyWithinConversionPeriod`)
*   **Suspense Code (01):** Checkbox + Listbox (`CheckBox_SuspenseCode` and `ListBox_SuspenseCode`)

### 2. Policy (2) Tab
*   **1035 Amt (59):** Checkbox (`CheckBox_Has1035Amount`)
*   **MEC (59):** Checkbox (`CheckBox_ShowMECStatus`)
*   **Failed Guideline or TAMRA (66):** Checkbox (`CheckBox_HasFailedGuidelineOrTAMRA`)
*   **TAMRA 7-Pay Premium (59):** Range (`TextBox_7PayLessThan` to `TextBox_7PayGreaterThan`)
*   **TAMRA 7-Pay Starting AV (59):** Range (`TextBox_7PayAVLessThan` to `TextBox_7PayAVGreaterThan`)
*   **Total Additional Prem (60):** Range (`TextBox_AdditionalPremLessThan` to `TextBox_AdditionalPremGreaterThan`)
*   **Total Prem (Additional + Reg):** Range (`TextBox_TotalPremLessThan` to `TextBox_TotalPremGreaterThan`)
*   **Accum WD (60):** Range (`TextBox_AccumWDLessThan` to `TextBox_AccumWDGreaterThan`)
*   **Premium Year To Date (63):** Range (`TextBox_PremYTDLessThan` to `TextBox_PremYTDGreaterThan`)
*   **Definition of Life Insurance (66):** Checkbox + Listbox (`CheckBox_SpecifyDefinitionOfLifeInsurance` and `ListBox_DefinitionOfLifeInsurance`)
*   **Reinsurance Code:** Checkbox + Listbox (`CheckBox_ReinsuranceCode` and `ListBox_ReinsuranceCode`)
*   **Termination Entry Date (69):** Range (`TextBox_TerminationLowDate` to `TextBox_TerminationHighDate`)
*   **BIL_COMMENCE_DT(66):** Range (`TextBox_LowBillCommenceDate` to `TextBox_HighBillCommenceDate`)
*   **Billing suspended (66):** Checkbox (`CheckBox_ShowBillingControlNumber` / varies)
*   **Last Financial Date (01):** Range (`TextBox_LowLastFinancialDate` to `TextBox_HighLastFinancialDate`)
*   **Loan Type (01):** Checkbox + Listbox (`CheckBox_SpecifyLoanType` and `ListBox_LoanType`)
*   **Loan charge Rate (01):** Text Input (`TextBox_LoanChargeRate`)
*   **Has Loan (77):** Checkbox (`CheckBox_HasLoan`)
    *   **Has Preferred Loan:** Checkbox (`CheckBox_HasPreferredLoan`)
    *   **Total Loan Principle (77):** Range (`TextBox_LoanPrincipleLessThan` to `TextBox_LoanPrincipleGreaterThan`)
    *   **Total Accured Loan Int:** Range (`TextBox_LoanAccruedIntLessThan` to `TextBox_LoanAccruedIntGreaterThan`)
*   **Trad Overloan Ind (01):** Checkbox + Listbox (`CheckBox_OverloanIndicator` and `ListBox_OverloanIndicator`)
*   **Standard Loan Payment (20):** Checkbox + Listbox (`CheckBox_SpecifySLRBillingForm` and `ListBox_SLRBillingForm`)
*   **Non Trad Indicator (02):** Checkbox + Listbox (`CheckBox_NonTradIndicator` and `ListBox_NonTradIndicator`)
*   **Has converted policy (52):** Checkbox (`CheckBox_SpecifyHasConvertedPolicyNumber`)
*   **Is a replacement (52-R):** Checkbox (`CheckBox_SpecifyIsAReplacement`)
*   **Has a replacement pol (52-R):** Checkbox (`CheckBox_ShowReplacementPolicy`)
*   **Cov has GIO ind (02):** Checkbox (`CheckBox_CovHasGIOInd`)
*   **Cov has COLA ind (02):** Checkbox (`CheckBox_CovHasCOLAInd`)
*   **Skipped Cov Rein (09):** Checkbox (`CheckBox_SkippedCoverageReinstatement`)
*   **Has Change Seq (68):** Checkbox + Listbox (`CheckBox_HasChangeSegment` and `ListBox_68SegmentChangeCodes`)
*   **Init Term Period (02):** Checkbox + Listbox (`CheckBox_SpecifyInitialTermPeriod` and `ListBox_InitialTermPeriod`)

### 3. Coverages Tab
**Base Coverage Section:**
*   **Plancode:** Text Input (`TextBox_Cov1Plancode`)
*   **Product Line Code (02):** Combobox (`ComboBox_Cov1ProductLineCode`)
*   **Product Indicator (02):** Combobox (`ComboBox_Cov1ProductIndicator`)
*   **Table:** Checkbox (`CheckBox_TableRating`)
*   **Flat:** Checkbox (`CheckBox_FlatExtra`)
*   **Sex Code (02):** Checkbox + Listbox (`CheckBox_SpecifyCov1SexcodeFrom02` and `ListBox_Cov1SexCodeFrom02`)
*   **Class:** Text Input (`TextBox_ValuationClass`)
*   **Base:** Text Input (`TextBox_ValuationBase`)
*   **Sub:** Text Input (`TextBox_ValuationSubseries`)
*   **Val:** Text Input (`TextBox_ValuationMortalityTable`)
*   **RPU:** Text Input (`TextBox_RPUMortalityTable`)
*   **ETI:** Text Input (`TextBox_ETIMortalityTable`)
*   **NFO Int Rate:** Text Input (`TextBox_NFOInterestRate`)
*   **Rateclass Code (67):** Checkbox + Listbox (`CheckBox_SpecifyCov1Rateclass` and `ListBox_Cov1Rateclass`)
*   **Sex Code (67):** Checkbox + Listbox (`CheckBox_SpecifyCov1Sexcode` and `ListBox_Cov1SexCode`)
*   **Valuation Class <> PlanDescription class code:** Checkbox (`CheckBox_ValuationClassNotPlanDescriptionClass`)
*   **Mortality Table Codes:** Checkbox + Listbox (`CheckBox_ShowMortalityTable` and `ListBox_MortalityTableCodes`)

**Rider Rows Section (Repeats for Rider 1, 2, and 3):**
*   **Plancode:** Text Input (`TextBox_Rider1Plancode`, etc.)
*   **Product Line Code (02):** Combobox (`ComboBox_Rider1ProductLineCode`, etc.)
*   **Product Indicator (02):** Combobox (`ComboBox_Rider1ProductIndicator`, etc.)
*   **Post Issue:** Checkbox (`CheckBox_PostIssue`, etc.)
*   **Issue Date Range:** Range (`TextBox_Rider1LowIssueDate` to `TextBox_Rider1HighIssueDate`)
*   **Additional Plancode Criteria:** Combobox (`ComboBox_Rider1AdditionalPlancodeCriteria`)
*   **Rateclass Code (67):** Combobox (`ComboBox_Rider1RateclassCode67`)
*   **Sex Code (67):** Combobox (`ComboBox_Rider1SexCode67`)
*   **Sex Code (02):** Combobox (`ComboBox_Rider1SexCode02`)
*   **Covered Person:** Combobox (`ComboBox_Rider1Person`)
*   **COLA Ind:** Combobox (`ComboBox_Rider1COLAIndicator`)
*   **GIO/FIO:** Combobox (`ComboBox_Rider1GIOFIOIndicator`)
*   **Change Type (02):** Combobox (`ComboBox_Rider1ChangeType`)
*   **Change Date Range:** Range (`TextBox_Rider1LowChangeDate` to `TextBox_Rider1HighChangeDate`)
*   **Lives Covered Code (02):** Combobox (`ComboBox_Rider1LivesCoveredCode`)

### 4. ADV Tab
*   **CV * CORR% > Specified Amount + OPTDB:** Checkbox (`CheckBox_ULInCorridor`)
*   **Accumulation Value > Premiums Paid:** Checkbox (`CheckBox_ShowAccumValGTPrem`)
*   **GLP is negative:** Checkbox (`CheckBox_ShowGLPIsNegative`)
*   **Current SA < Original SA:** Checkbox (`CheckBox_ShowCurrentSALTOriginal`)
*   **Current SA > Original SA:** Checkbox (`CheckBox_ShowCurrentSAGTOriginal`)
*   **Include APB Rider as Base Coverage:** Checkbox (`CheckBox_IncludeAPBRiderAsBase`)
*   **GCV > Current CV (02 and 75) (ISWL):** Checkbox (`CheckBox_ShowGCVGTCurrentCV`)
*   **GCV < Current CV (02 and 75) (ISWL):** Checkbox (`CheckBox_ShowGCVLTCVT`)
*   **Fund ID (Under Current Fund Value):** Text Input (`TextBox_FundIDs`)
*   **Fund Value Range (Under Current Fund Value):** Range (`TextBox_FundIDLessThan` to `TextBox_FundIDGreaterThan`)
*   **Accumulation Value range (75):** Range (`TextBox_AVLessThan` to `TextBox_AVGreaterThan`)
*   **Shadow Account Value (58):** Range (`TextBox_ShadowAVLessThan` to `TextBox_ShadowAVGreaterThan`)
*   **Current Specified Amount (02):** Range (`TextBox_CurrentSALessThan` to `TextBox_CurrentSAGreaterThan`)
*   **Accum MTP (58):** Range (`TextBox_AccumMTPLessThan` to `TextBox_AccumMTPGreaterThan`)
*   **Accum GLP (58):** Range (`TextBox_AccumGLPLessThan` to `TextBox_AccumGLPGreaterThan`)
*   **Grace Period Rule Code (66):** Checkbox + Listbox (`CheckBox_GracePeriodRuleCode` and `ListBox_GracePeriodRuleCode`)
*   **Death Benefit Option (66):** Checkbox + Listbox (`CheckBox_SpecifyDBOption` and `ListBox_DBOption`)
*   **IUL Only - Premium Allocation funds (57):** Checkbox + Listbox (`CheckBox_PremiumAllocationFunds` and `ListBox_PremiumAllocationFunds`)
*   **Type P Sequence (57) (Under IUL Only Sequence Count):** Range (`TextBox_TypePCountLessThan` to `TextBox_TypePCountGreaterThan`)
*   **Type V Sequence (57) (Under IUL Only Sequence Count):** Range (`TextBox_TypeVCountLessThan` to `TextBox_TypeVCountGreaterThan`)

### 5. WL (Whole Life) Tab
*   **Primary Dividend Option (01):** Checkbox + Listbox (`CheckBox_SpecifyPrimaryDivOpt` and `ListBox_PrimaryDivOption`)
*   **Secondary Dividend Option (01):** Checkbox + Listbox (`CheckBox_SpecifySecondaryDivOpt` and `ListBox_SecondaryDivOption`)
*   **NFO code (01):** Checkbox + Listbox (`CheckBox_SpecifyNFO` and `ListBox_NFO`)
*   **Current CV rate > 0 on base cov (02):** Checkbox (`CheckBox_SpecifyCashValueRateGTzeroOnBaseCov`)

### 6. DI (Disability Income) Tab
*   **Benefit Period Code (02) - Accident:** Checkbox + Listbox (`CheckBox_BenefitPeriodCodeForAccident` and `ListBox_BenefitPeriodCodeForAccident`)
*   **Benefit Period Code (02) - Sickness:** Checkbox + Listbox (`CheckBox_BenefitPeriodCodeForSickness` and `ListBox_BenefitPeriodCodeForSickness`)
*   **Elimination Period Code (02) - Accident:** Checkbox + Listbox (`CheckBox_EliminationPeriodCodeForAccident` and `ListBox_EliminationPeriodCodeForAccident`)
*   **Elimination Period Code (02) - Sickness:** Checkbox + Listbox (`CheckBox_EliminationPeriodCodeForSickness` and `ListBox_EliminationPeriodCodeForSickness`)

### 7. Benefits Tab
*(Contains 3 identical rows connected by "and" logical conditions)*
*   **Benefit:** Combobox (`ComboBox_Benefit1`, `ComboBox_Benefit2`, `ComboBox_Benefit3`)
*   **Sub Type:** Text Input (`TextBox_Benefit1SubType`, `TextBox_Benefit2SubType`, `TextBox_Benefit3SubType`)
*   **Post Issue:** Checkbox (`CheckBox_PostIssue1`, etc.)
*   **Cease Dt Range:** Range (`TextBox_Benefit1LowCeaseDate` to `TextBox_Benefit1HighCeaseDate`, etc.)
*   **Cease Date Status:** Combobox (`ComboBox_Benefit1CeaseDateStatus`, `ComboBox_Benefit2CeaseDateStatus`, `ComboBox_Benefit3CeaseDateStatus`)

### 8. Transaction Tab
*   **Transaction Type and Subtype (Top large box):** Multi-select Listbox (`ListBox_TransactionTypeAndSubtype`)
*   **Effective day = Issue day:** Checkbox (`CheckBox_Transaction1OnIssueDay`)
*   **Effective month = Issue month:** Checkbox (`CheckBox_Transaction1OnIssueMonth`)
*   **Eff Month Range:** Range (`TextBox_Transaction1EffMonthLow` to `TextBox_Transaction1EffMonthHigh`)
*   **Eff Day Range:** Range (`TextBox_Transaction1EffDayLow` to `TextBox_Transaction1EffDayHigh`)
*   **Transaction 1 Type and Subtype:** Combobox (`ComboBox_Transaction1`)
*   **Entry Date Range:** Range (`TextBox_Transaction1LowEntryDate` to `TextBox_Transaction1HighEntryDate`)
*   **Effective Date Range:** Range (`TextBox_Transaction1LowEffectiveDate` to `TextBox_Transaction1HighEffectiveDate`)
*   **Gross Amount range:** Range (`TextBox_Transaction1GrossAmtLow` to `TextBox_Transaction1GrossAmtHigh`)
*   **ORIGIN_OF_TRANS:** Text Input (`TextBox_Origin_of_Trans`)
*   **Fund ID List:** Text Input (`TextBox_FundIDList`)

### 9. Display Tab
*All fields on this tab are Checkboxes.*

**Column 1:**
*   **Paid To Date (01):** Checkbox (`CheckBox_ShowPaidToDate`)
*   **Bill To Date (01):** Checkbox (`CheckBox_ShowBillToDate`)
*   **GPE Date (51 or 66):** Checkbox (`CheckBox_ShowGPEDate`)
*   **Current Duration (Calc):** Checkbox (`CheckBox_ShowCurrentDuration`)
*   **Current Attained Age(Calc):** Checkbox (`CheckBox_ShowCurrentAttainedAge`)
*   **Last Accounting Date (01):** Checkbox (`CheckBox_LastAccountDate`)
*   **Last Financial Date (01):** Checkbox (`CheckBox_LastFinancialDate`)
*   **Application Date:** Checkbox (`CheckBox_ShowApplicationDate`)
*   **Next Scheduled Notification Date:** Checkbox (`CheckBox_ShowNextScheduledNotificationDate`)
*   **Next Year-End Date Date:** Checkbox (`CheckBox_ShowNextYearEndDate`)
*   **Next Scheduled Statement Date:** Checkbox (`CheckBox_ShowNextScheduledStatementDate`)
*   **Termination Date (69):** Checkbox (`CheckBox_ShowTerminationDate_from_69`)
*   **Converted policy info (52):** Checkbox (`CheckBox_ShowConvertedPolicyNumber`)
*   **Conversion Credit Info (52 - PDF):** Checkbox (`CheckBox_ShowConversionCreditInfo`)
*   **Initial Term Period (02):** Checkbox (`CheckBox_ShowInitialTermPeriod`)
*   **Display if within Conversion Period (Calc):** Checkbox (`CheckBox_ShowIfWithinConversionPeriod`)
*   **Display Conversion Period (Calc):** Checkbox (`CheckBox_ShowConversionPeriodInfo`)

**Column 2:**
*   **TCH POL ID:** Checkbox (`CheckBox_ShowTCH_POL_ID`)
*   **MOD Indicator:** Checkbox (`CheckBox_ShowMDOIndicator`)
*   **Product Line Code (02):** Checkbox (`CheckBox_ShowProductLineCode`)
*   **Billable Premium (01):** Checkbox (`CheckBox_ShowBillablePremium`)
*   **Billable Mode (01):** Checkbox (`CheckBox_ShowBillingMode`)
*   **Billable Form (01):** Checkbox (`CheckBox_ShowBillingForm`)
*   **Billable Control Number (33):** Checkbox (`CheckBox_ShowBillingControlNumber`)
*   **SLR Bill Form (20):** Checkbox (`CheckBox_ShowSLRBillingForm`)
*   **Short pay fields (52 and 58):** Checkbox (`CheckBox_ShowShortPayFields`)
*   **Accum Withdrawals (60):** Checkbox (`CheckBox_ShowAccumWithdrawals`)
*   **Premiums PTD (60):** Checkbox (`CheckBox_ShowPremiumPTD`)
*   **Premiums Paid YTD (63):** Checkbox (`CheckBox_ShowPremiumPaidYTD`)
*   **Policy Debt (77):** Checkbox (`CheckBox_ShowPolicyDebt`)
*   **Cost Basis (60):** Checkbox (`CheckBox_ShowCostBasis`)
*   **Prem Calc Rules (01):** Checkbox (`CheckBox_ShowPremCalcRules`)

**Column 3:**
*   **Display Substandard (03):** Checkbox (`CheckBox_ShowSubstandard`)
*   **Display Sex and Rateclass (67):** Checkbox (`CheckBox_ShowSexAndRateclass`)
*   **Display Sex(02):** Checkbox (`CheckBox_ShowSex02`)
*   **Subseries Code(02):** Checkbox (`CheckBox_ShowSubseries`)
*   **Display Market Org Code (01):** Checkbox (`CheckBox_MarketOrgCode`)
*   **Reinsured Code (01):** Checkbox (`CheckBox_ShowReinsuredCode`)
*   **Last Entry Code (01):** Checkbox (`CheckBox_ShowLastEntryCode`)
*   **Original Entry Code (01):** Checkbox (`CheckBox_ShowOriginalEntryCode`)
*   **MEC Status (01):** Checkbox (`CheckBox_ShowMECStatus`)
*   **Insured1 Info (89):** Checkbox (`CheckBox_ShowInsured1Info`)
*   **Replacement Policy (52-R):** Checkbox (`CheckBox_ShowReplacementPolicy`)

**Column 4:**
*   **Commission Target (58):** Checkbox (`CheckBox_ShowCTP`)
*   **Monthly Min Target (58):** Checkbox (`CheckBox_ShowMonthlyMTP`)
*   **Accum Monthly Min Target (58):** Checkbox (`CheckBox_ShowAccumMonthlyMTP`)
*   **Accum GLP (58):** Checkbox (`CheckBox_ShowAccumGLP`)
*   **NSP (58):** Checkbox (`CheckBox_ShowNSP`)
*   **GSP (67):** Checkbox (`CheckBox_ShowGSP`)
*   **GLP (67):** Checkbox (`CheckBox_ShowGLP`)
*   **TAMRA (59):** Checkbox (`CheckBox_ShowTAMRA`)
*   **Original face for RPU policies (68):** Checkbox (`CheckBox_RPUOriginalAmt`)
*   **Accumulation Value (75):** Checkbox (`CheckBox_ShowAccumulationValue`)
*   **Trad Cash Value Cov1 (02):** Checkbox (`CheckBox_DisplayTradCVCov1`)
*   **Account Value (02 & 75):** Checkbox (`CheckBox_DisplayAccountValue_02_75`)
*   **Shadow AV (58):** Checkbox (`CheckBox_ShowShadowAV`)
*   **Display original and current specified amount (02):** Checkbox (`CheckBox_ShowSpecifiedAmount`)
*   **Death Benefit Option (66):** Checkbox (`CheckBox_ShowDBOption`)
*   **Definition of Life Insurance (66):** Checkbox (`CheckBox_Show_UL_DefinitionOfLifeInsurance`)
*   **CIRF Key (55):** Checkbox (`CheckBox_ShowCIRFKey`)

**Column 5:**
*   **Trad Overloan Indicator (01):** Checkbox (`CheckBox_ShowTradOverloanInd`)

---

## Mapped to CL_POLREC Models (New SuiteView Audit Tool)

### CL_POLREC_01_51_66 (Base Policy Records)

These inputs correspond to fields queried via the 01, 51, and 66 segments (tables `LH_BAS_POL`, `TH_BAS_POL`, `LH_NON_TRD_POL`, `LH_TRD_POL`):

**Policy Criteria (Tab 1 & 2):**
*   **Company:** Combobox (`ComboBox_Company`)
*   **Market:** Combobox (`ComboBox_MarketOrg`)
*   **3 digit Branch #:** Text Input (`TextBox_BranchNumber`)
*   **Paid To Date Range:** Range (`TextBox_LowPaidToDate` to `TextBox_HighPaidToDate`)
*   **GPE Date Range (51 or 66):** Range (`TextBox_LowGPEDate` to `TextBox_HighGPEDate`)
*   **Application Date (01):** Range (`TextBox_LowAppDate` to `TextBox_HighAppDate`)
*   **Billing Prem Amt (01):** Range (`TextBox_LowBillingPrem` to `TextBox_HighBillingPrem`)
*   **Status Code (01):** Checkbox + Listbox (`CheckBox_SpecifyStatusCodes` and `ListBox_StatusCode`)
*   **State:** Checkbox + Listbox (`CheckBox_SpecifyState` and `ListBox_State`)
*   **Bill Mode (01):** Checkbox + Listbox (`CheckBox_SpecifyBillingModes` and `ListBox_BillMode`)
*   **Last Entry Code (01):** Checkbox + Listbox (`CheckBox_SpecifyLastEntryCode` and `ListBox_LastEntryCodes`)
*   **Billing Form (01):** Checkbox + Listbox (`CheckBox_SpecifyBillingForm` and `ListBox_BillingForm`)
*   **Grace Indicator (51 or 66):** Checkbox + Listbox (`CheckBox_GraceIndicator` and `ListBox_GraceIndicator`)
*   **Suspense Code (01):** Checkbox + Listbox (`CheckBox_SuspenseCode` and `ListBox_SuspenseCode`)
*   **Definition of Life Insurance (66):** Checkbox + Listbox (`CheckBox_SpecifyDefinitionOfLifeInsurance` and `ListBox_DefinitionOfLifeInsurance`)
*   **BIL_COMMENCE_DT(66):** Range (`TextBox_LowBillCommenceDate` to `TextBox_HighBillCommenceDate`)
*   **Billing suspended (66):** Checkbox (`CheckBox_ShowBillingControlNumber`)
*   **Last Financial Date (01):** Range (`TextBox_LowLastFinancialDate` to `TextBox_HighLastFinancialDate`)
*   **Loan Type (01):** Checkbox + Listbox (`CheckBox_SpecifyLoanType` and `ListBox_LoanType`)
*   **Loan charge Rate (01):** Text Input (`TextBox_LoanChargeRate`)
*   **Trad Overloan Ind (01):** Checkbox + Listbox (`CheckBox_OverloanIndicator` and `ListBox_OverloanIndicator`)

**Product Specific Criteria (ADV & WL Tabs):**
*   **Grace Period Rule Code (66):** Checkbox + Listbox (`CheckBox_GracePeriodRuleCode` and `ListBox_GracePeriodRuleCode`)
*   **Death Benefit Option (66):** Checkbox + Listbox (`CheckBox_SpecifyDBOption` and `ListBox_DBOption`)
*   **Primary Dividend Option (01):** Checkbox + Listbox (`CheckBox_SpecifyPrimaryDivOpt` and `ListBox_PrimaryDivOption`)
*   **Secondary Dividend Option (01):** Checkbox + Listbox (`CheckBox_SpecifySecondaryDivOpt` and `ListBox_SecondaryDivOption`)
*   **NFO code (01):** Checkbox + Listbox (`CheckBox_SpecifyNFO` and `ListBox_NFO`)

**Display Outputs (Display Tab):**
*   **Paid To Date (01):** Checkbox (`CheckBox_ShowPaidToDate`)
*   **Bill To Date (01):** Checkbox (`CheckBox_ShowBillToDate`)
*   **GPE Date (51 or 66):** Checkbox (`CheckBox_ShowGPEDate`)
*   **Last Accounting Date (01):** Checkbox (`CheckBox_LastAccountDate`)
*   **Last Financial Date (01):** Checkbox (`CheckBox_LastFinancialDate`)
*   **Application Date:** Checkbox (`CheckBox_ShowApplicationDate`)
*   **Billable Premium (01):** Checkbox (`CheckBox_ShowBillablePremium`)
*   **Billable Mode (01):** Checkbox (`CheckBox_ShowBillingMode`)
*   **Billable Form (01):** Checkbox (`CheckBox_ShowBillingForm`)
*   **Prem Calc Rules (01):** Checkbox (`CheckBox_ShowPremCalcRules`)
*   **Display Market Org Code (01):** Checkbox (`CheckBox_MarketOrgCode`)
*   **Reinsured Code (01):** Checkbox (`CheckBox_ShowReinsuredCode`)
*   **Last Entry Code (01):** Checkbox (`CheckBox_ShowLastEntryCode`)
*   **Original Entry Code (01):** Checkbox (`CheckBox_ShowOriginalEntryCode`)
*   **Death Benefit Option (66):** Checkbox (`CheckBox_ShowDBOption`)
*   **Definition of Life Insurance (66):** Checkbox (`CheckBox_Show_UL_DefinitionOfLifeInsurance`)
*   **Trad Overloan Indicator (01):** Checkbox (`CheckBox_ShowTradOverloanInd`)

### CL_POLREC_02_03_09_67 (Coverage & Rider Records)

These inputs correspond to fields related to phase coverages, ratings, skipped periods, and renewal rates/targets (tables `LH_COV_PHA`, `TH_COV_PHA`, `LH_SST_XTR_CRG`, `LH_COV_SKIPPED_PER`, `LH_COV_INS_RNL_RT`, `LH_COV_TARGET`):

**Policy Criteria (Tab 1 & 2):**
*   **Product Line Code (02):** Checkbox + Listbox (`CheckBox_SpecifyProductLineCodeAllCovs` and `ListBox_ProductLineCodeAllCovs`)
*   **Product Indicator (02) - All covs:** Checkbox + Listbox (`CheckBox_SpecifyProductIndicatorAllCovs` and `ListBox_ProductIndicatorAllCovs`)
*   **Multiple Base Covs (02):** Checkbox (`CheckBox_MultiplePlancodes` or `CheckBox_BaseSearchShowPolicies`)
*   **Init Term Period (02):** Checkbox + Listbox (`CheckBox_SpecifyInitialTermPeriod` and `ListBox_InitialTermPeriod`)
*   **Non Trad Indicator (02):** Checkbox + Listbox (`CheckBox_NonTradIndicator` and `ListBox_NonTradIndicator`)
*   **Cov has GIO ind (02):** Checkbox (`CheckBox_CovHasGIOInd`)
*   **Cov has COLA ind (02):** Checkbox (`CheckBox_CovHasCOLAInd`)
*   **Skipped Cov Rein (09):** Checkbox (`CheckBox_SkippedCoverageReinstatement`)

**Coverage Specific Criteria (Coverages & DI Tabs):**
*   **Product Line Code (02):** Combobox (`ComboBox_Cov1ProductLineCode`, `ComboBox_Rider1ProductLineCode`, etc.)
*   **Product Indicator (02):** Combobox (`ComboBox_Cov1ProductIndicator`, `ComboBox_Rider1ProductIndicator`, etc.)
*   **Sex Code (02):** Checkbox + Listbox (`CheckBox_SpecifyCov1SexcodeFrom02` and `ListBox_Cov1SexCodeFrom02`), Combobox (`ComboBox_Rider1SexCode02`)
*   **Rateclass Code (67):** Checkbox + Listbox (`CheckBox_SpecifyCov1Rateclass` and `ListBox_Cov1Rateclass`), Combobox (`ComboBox_Rider1RateclassCode67`)
*   **Sex Code (67):** Checkbox + Listbox (`CheckBox_SpecifyCov1Sexcode` and `ListBox_Cov1SexCode`), Combobox (`ComboBox_Rider1SexCode67`)
*   **Change Type (02):** Combobox (`ComboBox_Rider1ChangeType`)
*   **Lives Covered Code (02):** Combobox (`ComboBox_Rider1LivesCoveredCode`)
*   **Benefit Period Code (02) - Accident:** Checkbox + Listbox (`CheckBox_BenefitPeriodCodeForAccident` and `ListBox_BenefitPeriodCodeForAccident`)
*   **Benefit Period Code (02) - Sickness:** Checkbox + Listbox (`CheckBox_BenefitPeriodCodeForSickness` and `ListBox_BenefitPeriodCodeForSickness`)
*   **Elimination Period Code (02) - Accident:** Checkbox + Listbox (`CheckBox_EliminationPeriodCodeForAccident` and `ListBox_EliminationPeriodCodeForAccident`)
*   **Elimination Period Code (02) - Sickness:** Checkbox + Listbox (`CheckBox_EliminationPeriodCodeForSickness` and `ListBox_EliminationPeriodCodeForSickness`)

**Product Specific Criteria (ADV & WL Tabs):**
*   **GCV > Current CV (02 and 75) (ISWL):** Checkbox (`CheckBox_ShowGCVGTCurrentCV`)
*   **GCV < Current CV (02 and 75) (ISWL):** Checkbox (`CheckBox_ShowGCVLTCVT`)
*   **Current Specified Amount (02):** Range (`TextBox_CurrentSALessThan` to `TextBox_CurrentSAGreaterThan`)
*   **Current CV rate > 0 on base cov (02):** Checkbox (`CheckBox_SpecifyCashValueRateGTzeroOnBaseCov`)

**Display Outputs (Display Tab):**
*   **Initial Term Period (02):** Checkbox (`CheckBox_ShowInitialTermPeriod`)
*   **Product Line Code (02):** Checkbox (`CheckBox_ShowProductLineCode`)
*   **Display Substandard (03):** Checkbox (`CheckBox_ShowSubstandard`)
*   **Display Sex and Rateclass (67):** Checkbox (`CheckBox_ShowSexAndRateclass`)
*   **Display Sex(02):** Checkbox (`CheckBox_ShowSex02`)
*   **Subseries Code(02):** Checkbox (`CheckBox_ShowSubseries`)
*   **GSP (67):** Checkbox (`CheckBox_ShowGSP`)
*   **GLP (67):** Checkbox (`CheckBox_ShowGLP`)
*   **Trad Cash Value Cov1 (02):** Checkbox (`CheckBox_DisplayTradCVCov1`)
*   **Account Value (02 & 75):** Checkbox (`CheckBox_DisplayAccountValue_02_75`)
*   **Display original and current specified amount (02):** Checkbox (`CheckBox_ShowSpecifiedAmount`)

### CL_POLREC_04 (Benefit Records)

These inputs correspond to fields from the benefit/supplemental rider records (tables `LH_SPM_BNF`, `LH_BNF_INS_RNL_RT`).

The original VBA tool had a **Benefits Tab** (Tab 7) with 3 identical benefit-row "slots" connected by AND logic. Each slot allows filtering on a specific supplemental benefit. The SuiteView audit tool replicates this as a Benefits criteria panel.

**Benefits Criteria Panel (3 rows, "AND" logic between rows):**
*   **Benefit Type:** Combobox — selects the benefit type code (`SPM_BNF_TYP_CD`). Values are two-character codes from `LH_SPM_BNF` (e.g., WP, ADB, GIO, COLA, CI, etc.)
*   **Benefit Subtype:** Text Input — optional subtype code (`SPM_BNF_SBY_CD`) for finer filtering within a type.
*   **Post Issue:** Checkbox — flag to filter only benefits added post-issue (issue date differs from policy issue date).
*   **Cease Date Range:** Range — filter on benefit cease date (`BNF_CEA_DT`): Min to Max.
*   **Cease Date Status:** Combobox — filter on relationship between cease date and original cease date (`BNF_CEA_DT` vs `BNF_OGN_CEA_DT`): 1 = equal, 2 = cease < orig, 3 = cease > orig.

**Additional Benefit-Level Criteria (New — not in original VBA tool):**
*   **Benefit Amount Range:** Range — filter on computed benefit amount (`BNF_UNT_QTY × BNF_VPU_AMT`): Min to Max.
*   **Has Any Benefit:** Checkbox — simple toggle to require at least one row in `LH_SPM_BNF`.

**Display Outputs:**
*   Benefit type, subtype, issue date, cease date, original cease date, and benefit amount are displayable columns in the results grid.

### CL_POLREC_12_13_14_15_18_19_74 (Dividend Records)

These inputs correspond to fields from the dividend-related records (tables `LH_APPLIED_PTP`, `LH_UNAPPLIED_PTP`, `LH_ONE_YR_TRM_ADD`, `LH_PAID_UP_ADD`, `LH_PTP_ON_DEP`).

The original VBA tool did not have a dedicated Dividends criteria tab — dividend option filtering was on the WL (Whole Life) tab via Primary/Secondary Dividend Option (covered by `CL_POLREC_01_51_66`). The SuiteView audit tool adds new dividend-level criteria for deeper filtering.

**Dividend Criteria:**
*   **Dividend Type (12/13):** Checkbox + Listbox — filter on participation type code (`CK_PTP_TYP_CD`) from applied/unapplied dividend records.
*   **Has Applied Dividends (12):** Checkbox — require at least one row in `LH_APPLIED_PTP`.
*   **Has Unapplied Dividends (13):** Checkbox — require at least one row in `LH_UNAPPLIED_PTP`.
*   **Has OYT Additions (14):** Checkbox — require at least one row in `LH_ONE_YR_TRM_ADD`.
*   **Has PUA Additions (15):** Checkbox — require at least one row in `LH_PAID_UP_ADD`.
*   **Has Dividends on Deposit (18/19):** Checkbox — require at least one row in `LH_PTP_ON_DEP`.
*   **Total OYT Face Range (14):** Range — filter on total OYT face amount (sum of `OYT_ADD_AMT`): Min to Max.
*   **Total PUA Face Range (15):** Range — filter on total PUA face amount (sum of `PUA_AMT`): Min to Max.
*   **Total Div Deposit Range (18/19):** Range — filter on total dividend deposit amount (sum of `PTP_DEP_AMT`): Min to Max.
*   **Total Div Interest Range (18/19):** Range — filter on total dividend interest (sum of `DEP_ITS_AMT`): Min to Max.

**Display Outputs:**
*   Dividend type, year, OYT/PUA face amounts, deposit amounts, and interest amounts are displayable columns in the results grid.


