# Cyberlife Audit Tool - Criteria Input Classification

This document categorizes all the input types across the first 8 tabs (Policy through Transaction) of the Cyberlife Audit Tool based on the provided screenshots and corresponding VBA source code `frmAudit.frm`.

## Input Categories Identified

1. **Range (Min/Max):** Two separate text inputs placed side by side to specify a lower numerical or chronological bound and an upper bound. Example: Ages, Amounts, Dates.
2. **Combobox (Dropdown):** A single-selection dropdown menu list. 
3. **Checkbox:** A basic boolean toggle for turning a filtering rule on or off.
4. **Text Input:** A single text field for manual text entry. Some are quite small, representing single-character fields.
5. **Checkbox + Multi-select Listbox:** A prevalent pattern where a checkbox is attached to a listbox. The checkbox toggles the inclusion of the rule, and the listbox allows the user to select one or more specific matching values.
6. **Dual-Input (Combobox + Text Input):** A more advanced input where a dropdown specifies the "type" of the input, and an accompanying text box captures the value (e.g., Policy Number Criteria).
7. **Multi-select Listbox:** A standalone listbox allowing the selection of multiple values, differing from category 5 by the absence of a dedicated enabling checkbox.

---

## Native Cyberlife additions: 52-G and conversion dates (2026-09-08)

The **52 Segment** page supports criteria and individual display checkboxes for
these `TH_USER_GENERIC` columns:

| Input | Columns |
|-------|---------|
| Inclusive date range | `APP_RECEIVED_DATE`, `SRC_CONV_EXP_DT`, `SOURCE_PLAN_EFF_DATE`, `SOURCE_ISSUE_DATE` |
| Text match (Exact, Contains, Begins with, Ends with) | `SOURCE_PLAN_CODE`, `SOURCE_CNV_CREDIT_IND` |
| Decimal amount range | `SOURCE_FACE_AMT`, `CONV_CREDIT_AMT`, `CONV_FACE_AMT` |
| Whole-number range | `CONV_CREDIT_PERIOD`, `CONV_TO_TRM_PERIOD` |

Either range endpoint may be blank. Dates accept MM/DD/YYYY or YYYY-MM-DD.
Invalid or inverted ranges block SQL generation with a field-specific message.
Text inputs uppercase in the field; comparisons ignore case and surrounding spaces.
Criteria automatically include the corresponding column in results.
**Display all 52-G fields** on the page, or **Application / conversion fields
(52-G)** on Display, selects all eleven without requiring criteria.

These fields reuse the existing `USERGEN` left join on `CK_SYS_CD`, `CK_CMP_CD`,
and `TCH_POL_ID`; display-only selections do not remove policies with no segment.
No arbitrary `TYPE_SEQUENCE` is selected: if a policy has multiple distinct
52-G records, their displayed values can produce multiple result rows.
These are policy user fields, not the similarly named conversion rules in
`TH_USER_PDF`; the existing conversion/PDF displays remain available separately.
Page selections and criteria participate in Save, reopen, and New/clear.

Checking **Display > Converted policy info (52)** or **Policy (2) > Has
converted policy (52)** also includes `TH_USER_GENERIC.SOURCE_CMP_CODE` as
`SOURCE_CMP_CODE` in results. Checking both includes it only once. The display
option remains display-only; Has converted policy retains its existing
`EXCH_POL_NUMBER IS NOT NULL` filter. The source-company field was verified
against live CKPR metadata.

**Display > Show post conversion policy (link)** adds `POST_CONV_POLICY` and
`POST_CONV_COMPANY`. For an original policy with `LST_ETR_CD = 'O'`, the
optional `POST_CONVERSION` CTE reverses destination `TH_USER_GENERIC` records:
`SOURCE_CMP_CODE` and `EXCH_POL_NUMBER` identify the original company and
`LH_BAS_POL.CK_POLICY_NBR`, within the same system. The destination's own full
system/company/technical-policy key joins its master record to obtain its actual
policy number and company. Never derive that number from `TCH_POL_ID` or assume
source and destination companies are equal. Blank/NULL source keys do not match.

The main query **left joins** this mapping with the `O` condition in the join,
not the WHERE clause. Non-`O` and unmatched policies remain with blank destination
columns. The lookup is not restricted by the original policy's company, plan,
status or other criteria. Duplicate reference records collapse to distinct
source/destination pairs; multiple destinations produce separate result rows.
Only the immediate destination is shown, not a recursive conversion chain.
Unchecked adds no reverse lookup. The checkbox saves/reopens and clears with New.
The columns use the existing results grid and Excel export.

Live CKPR master-field inspection found no destination-policy field on the
original policy; five sampled conversion links existed on the destination's
52 record, with no forward exchange reference on those original policies.
Read-only result verification: `tools/audit/verify_post_conversion_link.py`.

**Display > Latest SC conversion dates (69)** adds `CONV_SC_ENTRY_DT` and
`CONV_SC_EFFECTIVE_DT`. It considers only policies with
`LH_BAS_POL.LST_ETR_CD = 'O'` (Termination - Conversion), and only `FH_FIXED`
rows with `TRANS = 'SC'`, `FCB0_REV_IND = '0'`, and `FCB2_REV_APPL_IND = '0'`.
It takes one row per policy, ordered by `ENTRY_DT`, `ENTRY_TIME`, then `SEQ_NO`,
descending (null dates/times last). Both dates come from that same row:
entry = `ENTRY_DT`, effective = `ASOF_DT`. Missing or ineligible data stays
blank; the display itself never filters policies out. This is independent of
the Transaction tab criteria and the existing termination-date display.

Live CKPR metadata and the complete generated SQL were verified with zero-row
queries. **Important:** `FH_FIXED` has no `CK_SYS_CD`; join it by company/policy
and carry the system from `LH_BAS_POL`. The physical time column is
`ENTRY_TIME`, not `TIME` as the older translation workbook suggests.

Regression checks:

```powershell
venv\Scripts\python.exe -m pytest tests\test_audit_segment52.py tests\test_audit_transaction_tab.py -q
venv\Scripts\python.exe tools\audit\verify_conversion_segments.py --verify-live
venv\Scripts\python.exe tools\audit\verify_conversion_schema.py
```

The UI verifier accepts `--screenshots DIR`; omit `--verify-live` for offline
UI/state checks. The schema verifier only reads column metadata and compiles
the conversion CTE; neither verifier exports policy rows.

## Fields by Tab (VBA ExcelTool)

### 1. Policy Tab
*   **Plancode:** Uppercased text input with exact matching only; no match-mode dropdown. Blank text applies no filter. Preserves the Plans and Policies tab's Cov1-only setting and coverage-level scope; the separate multi-plancode list remains an exact IN filter.
*   **Identifier layout:** Plancode, Company, Market, Form number like, Branch and Policy number use compact aligned rows. The Plancode input is left-aligned with the other controls, with RGA immediately to its right. Existing Company/Market, form prefix, branch and policy-number semantics are unchanged.
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
*   **Participating (02):** Checkbox + three-row multi-select list below Failed Guideline/TAMRA. Uses the **base coverage only** (`LH_COV_PHA.COV_PHA_NBR = 1`, `DIV_PTP_TYP_CD`), including in coverage-level queries. Options: **Participating** (A-H), **Participating but divs are paid up** (9), **Nonparticipating** (blank or 0-8). Codes are trimmed; SQL NULL/unrecognized values are not nonparticipating. Checking adds `ParticipationCode` and `Participation` result columns; selecting categories ORs them together, ANDed with other criteria. Checked without selections displays only (unknowns labeled `Unknown`); unchecked adds nothing. Save/reopen and New/reset include the checkbox and selections. Source: CyberLife D20 pp.117-118; do not apply the base mapping to rider codes.
*   The three termination ranges are consecutive compact single-line rows: Entry Date, Last Fin Date, and Date (both). Their existing date/filter semantics are unchanged; the shortened financial label retains its full meaning in the input tooltip.
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
*   **Termination Entry Date (69):** Range (`TextBox_TerminationLowDate` to `TextBox_TerminationHighDate`). Uses unreversed SC, SI, SF, TD, TM, TN, TL, and TO transactions only when the current policy record has `PRM_PAY_STA_REA_CD >= '97'` and a termination last-entry code (`J, L, M, N, O, P, Q, R, X`). A rider surrender on an active policy does not count. The Termination Date (69) display uses the same gate: active policies remain in display-only results, but their termination columns are blank.
*   **BIL_COMMENCE_DT(66):** Range (`TextBox_LowBillCommenceDate` to `TextBox_HighBillCommenceDate`)
*   **Billing suspended (66):** Checkbox (`CheckBox_ShowBillingControlNumber` / varies)
*   **Last Financial Date (01):** Range (`TextBox_LowLastFinancialDate` to `TextBox_HighLastFinancialDate`)
*   **Termination Last Financial Date (01):** Inclusive low/high date range (`txt_term_last_fin_date_lo` / `txt_term_last_fin_date_hi`). Uses `LH_BAS_POL.LST_FIN_DT` only where `PRM_PAY_STA_REA_CD >= '97'` and `LST_ETR_CD` is `J, L, M, N, O, P, Q, R, X` (the termination entries in the Last Entry Code picker). Null and `9999-12-31` dates cannot match. Adds `TERM_LAST_FIN_DT`, status and last-entry context to results.
*   **Termination Date (both):** Inclusive low/high date range (`txt_term_date_both_lo` / `txt_term_date_both_hi`). Requires the same current-policy status/code gate as the financial method for **both** sources. Uses the latest usable unreversed transaction **ENTRY_DT**, with the same SC/SI/SF/TD/TM/TN/TL/TO codes and both reversal flags equal to `'0'` as the (69) method. Only if no such date exists, falls back to the qualified Last Financial Date method above. Selects the source **before** applying the range: a transaction outside the range never permits fallback. Adds `TERM_DATE_BOTH`, `TERM_DATE_SOURCE`, status and last-entry context. Rider termination transactions on active policies cannot qualify. This is not an effective-date or historical-inforce reconstruction; the gate prevents active-policy false positives but does not classify every rider transaction within the history of an already-terminated policy.
    * Both new ranges accept MM/DD/YYYY or YYYY-MM-DD with either bound optional. Invalid/reversed bounds raise a query-build error. Blank ranges leave existing behavior unchanged. Saved profiles, query-object criteria, and New/reset include these fields. Other selected criteria remain AND filters; no status selection is silently cleared.
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
    Selected codes filter the union of `LH_NT_COV_CHG`,
    `LH_NT_COV_CHG_SCH`, `LH_SPM_BNF_CHG_SCH`, and termination detail
    `LH_COV_TMN`, joined on system/company/technical policy ID. The first
    three tables supply `CHG_TYP_CD`; live-verified `LH_COV_TMN` has no such
    column and contributes literal `'9' AS CHG_TYP_CD` (termination data).
    Disabled or empty selections add no filter. Regression:
    `tests/test_audit_change_segment.py`. Read-only live verification:
    `tools/audit/verify_change_segment.py --sample` compiles the generated SQL
    and retrieves at most one result for type 4, type 9 and both together.
*   **Init Term Period (02):** Checkbox + Listbox (`CheckBox_SpecifyInitialTermPeriod` and `ListBox_InitialTermPeriod`)

### 3. Coverages Tab
Layout: Valuation / Policy-Level / Non Trad / **Total Curr Specified Amt (Sum 02)**
on the left, the Init Term list and the reference-only Mortality Table Codes,
then the **Base Coverage Criteria (02)** and **Rider 1 Criteria** columns. Rider 2
is optional: a **[+]** beside Rider 1 adds it, and its **[x]** removes it and
clears its criteria so hidden values never reach the SQL. Restoring a saved query
that uses Rider 2 shows it again; New hides it. Coverage columns share one grid,
so rows line up across Base and Riders, and every range sits on one line
(`Label [Min] to [Max]`). Native no-DB check:
`tools/app/verify_coverages_tab.py --screenshot <path>`; regression:
`tests/test_audit_coverages_class_rider2.py`.

*   **Total Curr Specified Amt (Sum 02):** Range (`txt_spec_amt_lo`/`txt_spec_amt_hi`) on
    `COVSUMMARY.TOTAL_SA` — the sum of units × VPU over every base coverage
    (`ALL_BASE_COVS`), not coverage 1 alone.

**Base Coverage Section:**
*   **Plancode:** Text Input (`TextBox_Cov1Plancode`)
*   **Class (02):** Multi-select (`val_class`; was `TextBox_ValuationClass` in the Valuation group) —
    `COVERAGE1.INS_CLS_CD IN (...)`; saved queries keep the `val_class` key.
*   **Product Line Code (02):** Combobox (`ComboBox_Cov1ProductLineCode`)
*   **Product Indicator (02):** Combobox (`ComboBox_Cov1ProductIndicator`)
*   **Issue Date / Change Date / VPU / Cov Amount:** One-line ranges. **Cov Amount** is this
    coverage's units × VPU (`spec_amt_lo`/`spec_amt_hi`).
*   **Table:** Checkbox (`CheckBox_TableRating`)
*   **Flat:** Checkbox (`CheckBox_FlatExtra`) — matches any flat extra regardless of whether it has expired
*   **Active Flat:** Checkbox (`active_flat_03`) — matches only flat extras that are still active (cease date null/in the future)
*   **Sex Code (02):** Checkbox + Listbox (`CheckBox_SpecifyCov1SexcodeFrom02` and `ListBox_Cov1SexCodeFrom02`)
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

**Rider Columns (Rider 1, optional Rider 2):**
*   **Plancode:** Text Input (`TextBox_Rider1Plancode`, etc.)
*   **Class (02):** Multi-select (`class_code`) — `RIDERn.INS_CLS_CD IN (...)` on the rider join;
    shown as `RidernClass` at coverage level.
*   **Product Line Code (02):** Combobox (`ComboBox_Rider1ProductLineCode`, etc.)
*   **Product Indicator (02):** Combobox (`ComboBox_Rider1ProductIndicator`, etc.)
*   **Post Issue:** Checkbox (`CheckBox_PostIssue`, etc.)
*   **Issue Date Range:** Range (`TextBox_Rider1LowIssueDate` to `TextBox_Rider1HighIssueDate`)
*   **VPU / Cov Amount Range:** Ranges (`vpu_*`, `spec_amt_*`; Cov Amount = units × VPU)
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
    These two criteria use strict `<` and `>` comparisons respectively between
    `COVSUMMARY.TOTAL_SA` and `COVSUMMARY.TOTAL_ORIGINAL_SA`; equal amounts do
    not match either. Each checkbox controls its own predicate, including after
    saved-query restore. Checking both retains the usual AND semantics (no
    matching amounts). Unchecking both adds neither predicate.
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
*   **GLP (58):** Range (`TextBox_GLPLessThan` to `TextBox_GLPGreaterThan`)
*   **GSP (58):** Range (`TextBox_GSPLessThan` to `TextBox_GSPGreaterThan`)
*   **Grace Period Rule Code (66):** Checkbox + Listbox (`CheckBox_GracePeriodRuleCode` and `ListBox_GracePeriodRuleCode`)
*   **Death Benefit Option (66):** Checkbox + Listbox (`CheckBox_SpecifyDBOption` and `ListBox_DBOption`)
*   **Decrease Charge Rule (66):** Checkbox + Listbox (`chk_decr_chrg_rule` / `list_decr_chrg_rule`; SuiteView addition).
    Filters live-verified `TH_NON_TRD_POL.DECR_CHRG_ALLOW` through an `EXISTS` on the
    full system/company/technical-policy key (no join, no row multiplication).
    Items list every live value: `0 - No charge on decrease`, `1 - Charge on decrease`,
    `Blank - Not set` (space/NUL/NULL rows, matched as "not 0 or 1" to avoid a NUL
    literal). Selections are ORed; policies with no TH_NON_TRD_POL row never match.
    Unchecked or no selection adds nothing. State saves with the query and clears with New.

Layout: three top-aligned columns fitted to content — comparison checkboxes over
a **Value Ranges** group; the four code lists (Grace Period Rule, Death Benefit
Option, Decrease Charge Rule, Orig Entry Code) each showing every row; and the
IUL/fund criteria (CIRF Key, Premium Allocation funds, Allocation Sequence Count,
Current Fund Value). Native no-DB check: `tools/app/verify_adv_tab.py --screenshot <path>`;
read-only live filter check: `tools/audit/verify_decrease_charge_rule_filter.py`.
Regression: `tests/test_audit_adv_decrease_charge_rule.py`.
*   **IUL Only - Premium Allocation funds (57):** Checkbox + Listbox (`CheckBox_PremiumAllocationFunds` and `ListBox_PremiumAllocationFunds`)
*   **Type P Sequence (57) (Under IUL Only Sequence Count):** Range (`TextBox_TypePCountLessThan` to `TextBox_TypePCountGreaterThan`)
*   **Type V Sequence (57) (Under IUL Only Sequence Count):** Range (`TextBox_TypeVCountLessThan` to `TextBox_TypeVCountGreaterThan`)

### 5. WL (Whole Life) Tab
The page uses compact standard checkbox/listbox selectors, sized to their text
and exact row counts rather than checkable group boxes. All controls participate
in generated SQL, saved-query/profile state and New/reset.

*   **Participation Type (02):** Full base-coverage code list, **Blank, 0-9 and A-H**, with descriptions from CyberLife D20 pp.117-118. **Par** enables the selector and replaces its selection with exactly **A-H** (not 9). Uses phase 1 `LH_COV_PHA.DIV_PTP_TYP_CD` even in coverage-level mode. Blank matches stored spaces/empty strings, not NULL; unknowns are not silently nonparticipating. Selected codes are ORed within this list and ANDed with Policy (2)'s grouped participation selection. Checking displays `ParticipationCode`, grouped `Participation`, and detailed `ParticipationType`; no selection is display-only. The first two columns are not duplicated when both tabs are enabled.
*   **Primary Dividend Option (01):** Checkbox + Listbox (`CheckBox_SpecifyPrimaryDivOpt` and `ListBox_PrimaryDivOption`)
*   **Secondary Dividend Option (01):** Checkbox + Listbox (`CheckBox_SpecifySecondaryDivOpt` and `ListBox_SecondaryDivOption`)
*   **NFO code (01):** Checkbox + Listbox (`CheckBox_SpecifyNFO` and `ListBox_NFO`)
*   **Current CV rate > 0 on base cov (02):** Checkbox (`CheckBox_SpecifyCashValueRateGTzeroOnBaseCov`)

SQL sources: primary/secondary/NFO use `LH_BAS_POL.PRI_DIV_OPT_CD`,
`DIV_2ND_OPT_CD`, and `NFO_OPT_TYP_CD`; CV uses the existing Coverages-tab
predicate for positive `LOW_DUR_1_CSV_AMT` or `LOW_DUR_2_CSV_AMT` on phase 1.
Regression: `tests/test_audit_wl.py`. Native verification:
`tools/app/verify_policy2_participating.py --screenshot <policy2.png>
--wl-screenshot <wl.png>` (no DB2 access).

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
The left list is a read-only transaction type/subtype reference. On the right,
**Transaction 1** and **Transaction 2** are stacked, with aligned compact rows:

* **Transaction Type:** multi-select dropdown; selected codes are ORed within the section.
* **Entry Dt:** inclusive From / To date inputs.
* **Eff Dt:** inclusive From / To date inputs.
* **Transaction 2 date comparisons:** one dropdown beside Entry Dt and another
  beside Eff Dt. Both offer `none`, `After Trans1 Entry Date`,
  `Before Trans1 Entry Date`, `Equal Trans1 Entry Date`, `After Trans1 Eff Date`,
  `Before Trans1 Eff Date`, and `Equal Trans1 Eff Date`.
* **Eff Mth / Eff Day:** separate compact rows with 40px numeric range inputs;
  **Eff Mth = Issue Mth** and **Eff Day = Issue Day** sit beside their respective ranges.
* **Gross Amt:** inclusive From / To amounts below the month/day rows.
* **Origin / Fund ID List:** beside the reversal controls below Gross Amt.
  Origin matches exact `ORIGIN_OF_TRANS`; fund IDs are comma-separated and ORed.
* **Exclude:** per-section checkbox. Checked uses `NOT EXISTS`: the policy must have
  no transaction matching all of that section's criteria. Other nonmatching
  transactions do not let a policy pass. Exclude alone still leaves an empty
  section ignored.
* **Is Reversal / Reversed:** independent enabling checkboxes with two-row
  multi-select lists (`0` = No, `1` = Yes). Is Reversal filters `FCB0_REV_IND`;
  Reversed filters `FCB2_REV_APPL_IND`. Unchecking clears/disables the list.
  Checked with no selections leaves that flag unrestricted. Selecting both
  values accepts either stored value, not NULL. The flags constrain the same
  transaction as the section's other criteria, also when Exclude is checked.

With both date comparisons set to **none**, populated sections are combined with **AND**, using independent correlated
`EXISTS` or `NOT EXISTS` predicates against `FH_FIXED`. All criteria within one section must
match one history row; the two sections can match different rows (or the same
row if it satisfies both). No distinct-transaction or ordering requirement is
implied. Multiple matching transactions do not multiply result rows. Empty
sections are ignored, including Transaction 1 when only Transaction 2 is used.
Any individual field or checkbox activates its section without needing a type.

Selecting either date comparison instead requires a qualifying pair on the same
policy, using nested `EXISTS`. Entry Dt compares `TR2.ENTRY_DT`; Eff Dt compares
`TR2.ASOF_DT`, against the selected `TR1.ENTRY_DT` or `TR1.ASOF_DT`.
After/Before/Equal mean strict `>` / `<` / `=` on dates, not entry times.
Both comparisons and all existing section criteria must hold for the **same
pair**. Any qualifying pair is enough; do not implicitly choose the latest or
earliest Transaction 1. NULL dates do not satisfy a comparison. No distinct-row
requirement is added: equality can match the same transaction if it meets both
sections. With a date link and no Transaction 1 criteria, any policy transaction
can be the reference.

**Transaction 1 Exclude** clears and disables both comparison dropdowns; turning
it off enables them at `none`. Contradictory saved/programmatic criteria fail
explicitly, not silently. With a date link, **Transaction 2 Exclude** requires a
matching Transaction 1 and **no qualifying pair anywhere on that policy**.
An additional Transaction 1 without a matching partner must not let the policy
pass if another pair qualifies.

History correlation uses company and technical policy ID, never `CK_SYS_CD`.
Issue-month/day comparisons continue to use the base coverage issue date,
including in coverage-level queries. There is no implicit reversal exclusion:
reversal flags filter only when enabled with a selection.

Dates accept MM/DD/YYYY or YYYY-MM-DD. Either endpoint may be blank; invalid or
inverted ranges raise a section/field-specific error. Months must be 1-12 and
days 1-31. Amounts accept finite decimals, including zero/negative amounts.
Nonempty fund lists must not contain empty entries.

Both sections, including Exclude, reversal controls and date comparisons, persist with saved queries
and clear with New. The new checkboxes default off. Transaction 1
retains its original saved-state keys; Transaction 2 uses a nested
`transaction2` object. Loading a query without it leaves Transaction 2 empty.
Its `entry_comparison` and `eff_comparison` keys store the selected labels and
default to `none` when absent. New resets both to `none`.
Regression: `tests/test_audit_transaction_tab.py`,
`tests/test_audit_transaction_filters.py`, `tests/test_read_only_generated_sql.py`.
Native no-DB verification:
`tools/app/verify_transaction_tab.py --screenshot <path>`.

### Plans and Policies (identifier lists)

The former **Plancode** tab has side-by-side **Plancode** and **Policies**
sections. Both support Add (or Enter), Remove Selected, Remove All and Paste
from Clipboard. Paste accepts Excel rows/columns, newlines, commas, semicolons
and whitespace; values are trimmed, uppercased and deduplicated in input order,
with leading zeros retained. **Cov1 plancode match only** belongs to Plancode
alone and retains its existing coverage-scope behavior.

Policies matches `LH_BAS_POL.CK_POLICY_NBR` exactly, not `TCH_POL_ID`, with
an IN list. Entries within a list are alternatives; populated plan/policy lists
combine with each other and all other query criteria using AND. An empty list
adds no filter or join. Region, company, system, coverage scope and Max Count
still apply, so clear other filters or increase Max Count when appropriate.
Both lists save with queries and clear with New; results are not guaranteed
to contain every requested policy when other criteria exclude them.

Regression: `tests/test_audit_plans_policies.py`.
Native no-DB check: `tools/app/verify_plans_policies.py --screenshot <path>`.

### Other Queries (standalone lookups)

This replaces the **CyberLife Common Tables** tab, not the separate visual query
builder's common-table features. It restores the three functions from
`docs/vba_reference/frmAudit.frm` (`BuildSQLStringToFindRiders`,
`BuildSQLStringToFindBase`, `BuildSQLStringToFindValues`).

* **Base Plancode / Find all riders:** exact uppercase plancode of coverage
  phase 1. Lists later phases with a different plancode, grouped by base plan/form
  and rider plan/form. **Rider Count** uses `COUNT(*)` for all matching coverage
  occurrences, active or inactive, not distinct policies or distinct plancodes.
* **Rider Plancode / Find all base:** exact uppercase rider plancode on phases
  greater than 1, grouped by rider plan/form and the phase-1 base plan/form.
* Each **Show policies** checkbox independently replaces the count with
  **Policy Number** and **Company**, one row per matched coverage. Repeated policies
  are intentional when multiple matching coverages exist. The policy number
  comes from `LH_BAS_POL.CK_POLICY_NBR`, not a truncated technical ID.
* **Table / Field / Find all values:** enter unqualified DB2 names. Groups the
  field and counts records with non-NULL `TCH_POL_ID`, retaining NULL/blank field
  groups. This is **Record Count**, not distinct policies. The table
  must expose `TCH_POL_ID`; unknown tables/fields fail explicitly.

These are independent lookups: only **Region** applies. The main tab filters,
system selector, coverage scope and Max Count do not limit these results, matching
the old Excel actions. There is no implicit inforce/active-coverage filter.
Base/rider joins use system, company and technical policy ID together.
Both Show policies controls work independently (fixing the original VBA's
FindRiders SELECT referencing the wrong checkbox).

Each panel runs asynchronously with its own **Find**, **View SQL**, sortable/
filterable result table and **Excel** button. Excel opens a new unsaved workbook
containing the displayed rows; policy/company/form codes retain leading zeros.
Cells are read-only: clicks may select for copying, but cannot open an editor
or blank/change a value.
SQL previews show escaped literal values for copying; execution binds plancodes
as parameters on isolated DB2 connections. Table/field identifiers are strictly
validated, not arbitrary SQL expressions.

The live Data Virtualization driver gives distinct-value counts for
`COUNT(column)`, so it must not implement occurrence counts. Rider/base lookups
use `COUNT(*)`; field frequencies use
`SUM(CASE WHEN V.TCH_POL_ID IS NOT NULL THEN 1 ELSE 0 END)` to preserve
non-NULL-record semantics. The driver rejects `COUNT(ALL column)`.
Read-only live verification reconciles against detail rows:
`tools/audit/verify_other_query_counts.py --plancode 1U143900`;
use `--kind bases --plancode 1U535A00` for the reverse lookup.

Inputs and checkboxes persist with the query; results are not saved. New clears
inputs and results. Editing inputs or changing region clears affected results;
late responses to older criteria are discarded. Errors are reported rather than
shown as an empty success. The main footer Run explains that these lookups use
their own Find buttons.

Regression: `tests/test_audit_other_queries.py`, `tests/test_audit_other_queries_ui.py`.
Native integration check with synthetic results only:
`tools/app/verify_other_queries.py --screenshot <path>`.

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
*   **Monthly Min Target (58):** Checkbox (`CheckBox_ShowMonthlyMTP`) — also displays `MAPCeaseDt` (MAP cease date, `LH_POL_TARGET.TAR_DT` where `TAR_TYP_CD = 'MA'`)
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
