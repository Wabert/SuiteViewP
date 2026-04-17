# UL Illustration Module — Requirements Specification

**Module:** `suiteview/illustration/`  
**Version:** 0.1 (Draft)  
**Last Updated:** 2026-04-12  
**Author:** Robert Haessly / GitHub Copilot  
**Source Workbook:** RERUN (v19.1).xlsm  

---

## 1. Project Overview

### 1.1 Purpose
Migrate the RERUN Excel workbook — a 27-sheet, 20-year-old inforce UL illustration engine — into SuiteView as a native Python/PyQt6 module. The workbook handles monthly policy value calculations, what-if scenario modeling, 7702 compliance testing, and illustration report generation for ANICO's full UL product portfolio.

### 1.2 Users
- Internal only: Actuarial, Business Analyst team, Business Support

### 1.3 Scope — v1
| In Scope | Out of Scope (v1) |
|---|---|
| Inforce illustrations | New business illustrations |
| All 3 product types: UL, IUL, SGUL | PDF report generation |
| Penny-for-penny accuracy (early years) | Batch processing |
| What-if scenario modeling (core) | Annual Qualification Test |
| 7702 compliance (GP, TAMRA, DCV, NSP) | Saved cases (nice-to-have) |
| All riders and benefits | Rate versioning by effective date |
| Shadow account calculations | WAIR interest method (Blend only) |
| Policy changes (face, DBO, withdrawals, loans, rate class, riders) | |
| On-screen value display | |
| Single policy at a time | |

**AG49 Note:** Use the latest (most conservative) AG49 regulation for shadow account calculations.

**Inforce Business Rules:** The inforce illustration will be kept relatively free of strict business rules. The inforce world is messy — policies get issued or processed outside of intended product specifications. The tool should accommodate real-world inforce data rather than reject it.

### 1.4 Accuracy Requirement
- **Penny-for-penny match** to the Excel workbook for the first ~15 years of projection
- Small tolerance (within a few dollars) acceptable beyond 30+ years out
- Test policy **UE000576** (plancode 1U143900) is the primary validation target

---

## 2. Product Portfolio

### 2.1 Product Types
The module must eventually support 200+ plancodes across these product families. Rollout order: **EXECUL → IUL → SGUL → Older UL**. Initial development targets EXECUL plancodes first.

| Family | Product Type | Report Template | Example Plancode | Key Differentiator |
|---|---|---|---|---|
| EXECUL08 | UL | UL | 1U143900 | Declared interest, AV-based bonus |
| EXECUL19 | UL | UL | 1U147000 | Declared interest |
| LTG06 | UL | UL | 1U143800 | Declared interest |
| LTG08 | UL | UL | 1U144500 | Declared interest |
| IUL08 | IUL | IUL | 1U144600 | Blend interest, index strategies |
| IUL14 | IUL | IUL | 1U145500 | Blend interest, bonus version available |
| IUL19 | IUL | IUL | 1U146800 | Blend interest, multiplier strategies |
| IUL21 | IUL | IUL | 1U147500 | Blend interest, NASDAQ/MARC strategies |
| GIUL21 | IUL | IUL | 1U147400 | Guaranteed IUL |
| SGUL15 | SGUL | SGUL | 1U145700 | No loans, simplified |
| SGUL18 | SGUL | SGUL | 1U146600 | No loans |
| SGUL20 | SGUL | SGUL | 1U147200 | No loans |
| SGUL21 | SGUL | SGUL | 1U147600 | No loans |
| Older UL | UL | UL | 1U131300+ | Ratchet banding, flat premium load |

### 2.2 Plancode Configuration Parameters
Each plancode has a configuration record (currently in the Rates_Control "BasePlancodeTable") with 55 fields. This data will be stored as JSON. Key parameters:

| Parameter | Description | Example (1U143900) |
|---|---|---|
| `PremiumCeaseAge` | Age at which premiums stop | 121 |
| `BenefitCeaseAge` | Age at which benefits cease | 121 |
| `MatureEndowValue` | Endowment value type at maturity | SV (Surrender Value) or DB (Death Benefit) |
| `LNCRD` | Current loan charge rate | 0.03 |
| `LNCRG` | Guaranteed loan charge rate | 0.06 |
| `PrefLNCRD` / `PrefLNCRG` | Preferred loan charge rates | 0.06 / 0.06 |
| `Var Ln Available` | Variable loans available | False |
| `LoanType` | Interest in Advance or Arrears | Arrears |
| `GINT` | Guaranteed interest rate | 0.03 |
| `IntCalcMethod` | Interest calculation method | Declared, Blend |
| `Band Table` | Which banding table to use | 10 |
| `LapseTarget` | Lapse protection basis | SV (Surrender Value) |
| `AgeCalc` | Age calculation method | ALB (Age Last Birthday) |
| `ShadowPlancode` | Shadow account plancode | CCV00100 |
| `ShadowAvailablity` | Shadow account type | Rider, Inherent, or NA |
| `InherentGCO` | Has inherent GCO rider | False |
| `MFEE` | Monthly fee amount (or "Table") | 5 |
| `EPU_Code` | Expense per unit source | Table (from UL_Rates DB) |
| `EPU SA_Basis` | EPU applied to current or original SA | CurrentSA |
| `Table Rating Factor` | Substandard rating multiplier | 0.25 |
| `DBD` | Death benefit discount rate | 0.03 |
| `Bonus` | Bonus type | Table (from UL_Rates DB) |
| `PremiumLoad` | Premium load source | Table (from UL_Rates DB) |
| `PremFlatLoad` | Flat premium load (older products) | 0 |
| `SNET` | Safety net period (years) | 10 |
| `Target SA_Basis` | Target premium basis | CurrentSA |
| `Target BandLock` | Band locked at issue | False |
| `PSC` | Partial Surrender Charge applies | True |
| `CanIllustrate` | Plancode supported for illustration | True |
| `CorridorCode` | Which corridor table to use | 1 |
| `Dynamic Banding` | Dynamic banding rule code | 3 |
| `CompanySub` | Company subsidiary | ANICO |
| `Interest Method` | Day count method | ExactDays |

**Decision:** Store the plancode table as JSON, with an editor UI for updates/additions. Migrate to database later.

---

## 3. Data Sources

### 3.1 Policy Data — DB2 (Existing)
SuiteView's `PolicyInformation` class already retrieves all needed policy data from DB2 via ODBC. Key fields used by the illustration:

**Policy-Level:**
- Policy number, company, region, issue date, issue state
- Plan code, form number, product type
- Death benefit option (A/B/C)
- Definition of life insurance (GPT vs CVAT)
- Premium mode, modal premium, annual premium
- Account value, cash surrender value, cost basis
- Loan balances (fixed principal/accrued, preferred principal/accrued, variable principal/accrued)
- Total premiums paid, premiums YTD, withdrawals to date
- GLP, GSP, accumulated GLP target, accumulated MTP target
- TAMRA 7-pay level, 7-pay start date, 7-year lowest DB, is MEC
- Policy year, policy month, valuation date, attained age
- Guaranteed interest rate, corridor percent
- MTP, CTP target premium values

**Coverage-Level (per segment):**
- Plancode, face amount, original face amount, units
- Issue date, issue age, sex, rate class
- Table rating, flat extra, flat cease date
- COI rate (current renewal), form number
- Coverage status, maturity date
- Is base coverage indicator, coverage phase number

**Benefit-Level:**
- Benefit type code, subtype code, form number
- Benefit amount, units, VPU
- Issue date, issue age, cease date
- Rating factor, renewal indicator

### 3.2 Inforce Injection Values
When running an inforce illustration, the following values are injected at the policy's current duration (past values are not replayed):

| Value | Source |
|---|---|
| Current Account Value | DB2 (total_fund_value) |
| Current Shadow Account Value | DB2 or manual |
| Deemed Cash Value | Manual entry (CVAT only) |
| GLP, GSP | DB2 |
| Accumulated GLP | DB2 |
| CTP, Monthly MTP | DB2 |
| Accumulated Minimum Target Premium | DB2 |
| TAMRA 7-year contributions (years 1-7) | DB2 |
| TAMRA 7-pay premium, 7-pay cash value | DB2 |
| TAMRA 7-pay start date, 7-year lowest DB | DB2 |
| Is MEC | DB2 |
| Cost basis | DB2 |
| Premium to date, Premium YTD | DB2 |
| Withdrawals to date | DB2 |
| Loan balances (fixed/preferred/variable principal + accrued) | DB2 |
| SWAM (Sweep Account Minimum) | DB2 or manual |
| Current SA per segment (all base segments) | DB2 (coverage records) |
| Original SA per segment (all base segments) | DB2 (coverage records) |
| Current APB SA | DB2 |
| Original APB SA | DB2 |
| Original band per segment (all base segments) | DB2 or derived |
| Rate class per segment (all base segments) | DB2 (coverage records) |
| Issue date per segment (all base segments) | DB2 (coverage records) |
| Issue age per segment (all base segments) | DB2 (coverage records) |
| Table rating per segment (all base segments) | DB2 (coverage records) |
| Months since terminated (per coverage, all segments) | DB2 or derived |
| DB Option | DB2 |
| Valuation date | DB2 |
| COLA active, Shadow Benefit active | DB2 benefit records |
| ABR benefits active (CH, CT, TM) | DB2 benefit records |
| GCO active (15, 20, 25) | DB2 benefit records |
| MAP cease date | DB2 |

### 3.3 UL Rates — SQL Server (Existing)
SuiteView's `Rates` class retrieves rates from the UL_Rates SQL Server database. Confirmed working rate types:

| Rate Type | Description | Varies By | Example Value |
|---|---|---|---|
| COI | Cost of Insurance (monthly per $1000) | plancode, age, sex, rateclass, band, duration | 0.19981 at dur 1 |
| EPU | Expense Per Unit (monthly per $1000) | plancode, band, duration | 0.08 |
| TPP | Target Percent of Premium load | plancode, duration | varies |
| EPP | Excess Percent of Premium load | plancode, duration | varies |
| SCR | Surrender Charge (per $1000) | plancode, age, sex, rateclass (S/NS only), duration | 35.09 at dur 1 |
| MFEE | Monthly Fee (flat dollar) | plancode, duration | $5.00 |
| CORR | Corridor factors (by attained age) | plancode, attained age | 1.34 at age 59 |
| GINT | Guaranteed Interest Rate | plancode, duration | 0.03 |
| MTP | Minimum Target Premium (annual per $1000) | plancode, age, sex, rateclass, band | 13.80 |
| CTP | Commission Target Premium (annual per $1000) | plancode, age, sex, rateclass, band | 16.99 |
| BONUSAV | Interest bonus (AV threshold trigger) | plancode, duration | 0.0025 |
| BONUSDUR | Interest bonus (duration trigger) | plancode, duration | 0.005 after dur 10 |
| DBD | Death benefit discount rate | plancode, duration | 0.03 |
| BANDSPECS | Face amount band breakpoints | plancode | [[0,1],[50K,2],[100K,3],[500K,4],[1M,5]] |
| SNETPERIOD | Safety net period | plancode | 10 years |
| EPU | Extended Paid-Up rate | plancode, age, sex, rateclass, band, duration | 0.05417 |

### 3.4 Rates_Control Data — JSON (New)
The Rates_Control sheet contains rate tables and parameters that are NOT in the UL_Rates database. These will be exported to JSON files. Tables that ARE in the UL_Rates database will be retrieved via the existing `Rates` class and do NOT need JSON storage.

**Tables stored as JSON (not in UL_Rates DB):**

| Table Name | Description | Approximate Size |
|---|---|---|
| `tPlancodeTable` | Plancode configuration (55 fields × 200+ plancodes) | 200+ rows |
| `tRiderDefinitionFile` | Rider definitions | 135 rows |
| `tBenefitDefinitionFile` | Benefit definitions | 877 rows |
| `tValid_IndexFundIDs` | Valid index fund IDs by plancode | 63 rows |
| `tRates_IssueAgeRange` | Issue age ranges by plancode | 22 rows |
| `tRates_IntBonus` | Interest bonus schedule | 62 rows |
| `tRates_Rider_CCV_Targets` | CCV rider target rates | varies |
| `tRates_Rider_CCV_COI` | CCV rider COI rates | varies |
| `tRates_Benefit_COI` | Benefit COI rates (by sex/class/band/age) | varies |
| `tRates_Benefit_Targets` | Benefit target rates | varies |
| `tRates_Benefit_GCO` | GCO benefit rates | varies |
| `tRates_Premium_Load` | Premium load rates (TPP target/EPP excess) | 110 rows |
| `tRates_MDBR` | Minimum death benefit ratios | ~1938 rows |

**Tables sourced from UL_Rates DB (no JSON needed):**

| Table Name | Description | Retrieved Via |
|---|---|---|
| `tRates_CORR` | GP Corridor rates | `Rates.get_rates('CORR', ...)` |
| `tRates_SNET_Period` | Safety net period by plancode | `Rates.get_rates('SNETPERIOD', ...)` |
| `tRates_Base_EPU` | Expense per unit rates | `Rates.get_rates('EPU', ...)` |
| `tRates_Shadow_Interest` | Shadow account interest rates | `Rates.get_rates(...)` |
| `tRates_Targets` | Base target rates (MTP/CTP) | `Rates.get_mtp()` / `Rates.get_ctp()` |
| `tRates_Ultimate_GCOI` | Guaranteed COI rates | `Rates.get_rates('COI', ..., scale=guaranteed)` |
| `tRates_Select_CCOI` | Select current COI rates | `Rates.get_rates('COI', ..., scale=current)` |
| `tRates_Base_SCR` | Surrender charge rates | `Rates.get_rates('SCR', ...)` |
| `tRates_MFEE` | Monthly fee rates | `Rates.get_rates('MFEE', ...)` |

**Not needed:**

| Table Name | Reason |
|---|---|
| `tRates_StratIntBonus` | Not needed for illustration |

---

## 4. Calculation Pipeline

### 4.1 Overview
The calculation engine processes each month sequentially from the inforce injection point through the projection end age (varies by plancode: age 95, 100, or 121). The pipeline is strictly ordered — each step depends on results from prior steps.

### 4.2 Monthly Processing Pipeline (in order)

#### Step 1: Policy Changes
Process any scheduled changes for this month:
1. **Withdrawals** — reduce account value, apply partial surrender charge if applicable
2. **Death Benefit Option Change** — switch between DBO A/B/C
3. **Increase/Decrease to Specified Amount** — add or remove coverage segments
4. **Policy Duration** — update policy year/month counters
5. **Policy Banding** — recalculate band based on total base face amount
6. **Rate Class Change** — update rate class and rerate if applicable
7. **Flat Extra** — net flat extra from CyberLife, no adjustment factor applied

#### Step 2: Riders and Benefits
1. Add/Drop/Modify benefits (CCV, GCO, PW, ADB, GIO)
2. Add/Drop/Modify term riders (CTR, STR, LTR, APBR)

#### Step 3: Minimum Target Premium (MTP)
1. Calculate base coverage MTP
2. Calculate rider/benefit MTP
3. Calculate accumulated MTP

#### Step 4: Commission Target Premium (CTP)
1. Calculate base coverage CTP
2. Calculate rider/benefit CTP

#### Step 5: Guideline and TAMRA Premium
1. Update GLP and GSP for any policy change
2. Accumulate GLP
3. Calculate any force-outs (premium that must come out to stay within guideline limits)
4. Update TAMRA for any policy change (recalculate and start new 7-pay period if necessary)
5. Calculate necessary premium for CVAT cases

#### Step 6: Requested Premium
1. Determine total premium being requested (scheduled premium + 1035 amounts + lump sum)

#### Step 7: Loan Capitalization and Repay
1. Capitalize loan interest (at beginning of year)
2. Determine total loan payoff amount
   - **Arrears:** Regular principal + interest + Preferred principal + interest + Variable principal + interest
   - **Advance:** Reduced by advance interest factor (charge rate × days_left / days_in_year)
3. Determine effective loan repayment
4. Handle "Add Interest To Loan" option
5. Handle "Prem Must Apply To Loan" option
6. Calculate total loan repayment from premium + scheduled repayments
7. Apply repayments in priority order:
   - **Advance:** Preferred → Regular (with day-count interest adjustment)
   - **Arrears:** Preferred accrued → Preferred principal → Regular accrued → Regular principal → Variable accrued → Variable principal
8. Identify any remaining repayment to apply as premium
9. **SGUL:** Loans ARE available for inforce illustrations (though not available for new business illustration on SGUL)

#### Step 8: Apply Premium
1. Restrict premium per guideline, TAMRA, or CVAT NPT limits
2. Determine actual premium to apply (may differ from requested)
3. Calculate premium load: `premium × premium_load_rate` (rate from plancode config or rate table)
4. Update cost basis, premium to date, premium YTD

#### Step 9: Monthly Deduction
1. Calculate corridor amount (GP Corridor or CVAT Corridor) — ensure death benefit meets minimum ratio to AV
2. **For each coverage segment:**
   a. Find COI rates (from rate table by segment's own issue age, sex, rateclass, band, duration)
   b. Adjust for substandard rating if applicable
   c. Calculate death benefit for this segment
   d. Calculate Net Amount at Risk (NAR) per segment
      - **CRITICAL: Account value is applied FIFO (first-in-first-out) across base coverage segments when calculating NAR.** For multi-segment policies this is essential — AV offsets the oldest segment first before reducing NAR on subsequent segments. This significantly affects COI charges when segments have different issue ages and rate classes.
      - DBO A: NAR = Death Benefit − Account Value (AV applied FIFO across base segments)
      - DBO B: NAR = Face Amount (death benefit = face + AV, so NAR = face)
      - DBO C: NAR = Face + Cumulative Premium − AV
   e. Calculate COI charge: `NAR / 1000 × COI_rate`
3. Calculate rider and benefit charges for each active rider/benefit (except PW39)
4. Calculate expenses: EPU charge + monthly fee + percent of account value charge
5. Calculate PW39 benefit charge (waiver of greater of: all charges OR minimum target premium)
6. Calculate asset fees if applicable (IUL)
7. Total monthly deduction = sum of all charges above
8. `AV_after_charge = AV − total_monthly_deduction`

**Ratchet Method:** For 5 plancodes of UL products from the mid-1980s, COI is calculated using a ratchet method instead of standard NAR-based COI.

#### Step 10: Exception Premium
Only applies when "Allow Guideline Exception Premium" option is enabled AND:
- Policy is beyond safety net period
- CCV is NOT protecting the policy
- Guideline limit is reached
- Exception premium mode is TRUE

Calculation:
1. `GP_Exception_Prem_Gross = −AV_after_charge` (only if AV_after_charge < 0)
2. `Exception_Prem_Discount = GP_Exception_Prem_Gross / 1000 × COI_rate`
3. `GP_Exception_Prem = (GP_Exception_Prem_Gross − Exception_Prem_Discount + FlatPremLoad) / (1 − TPP_rate)`
4. Apply exception premium to AV (adjusted for loads)

#### Step 11: Accumulation (Interest Calculation)
Calculate end-of-month account value:

**If method = Declared or Blend:**
1. Calculate impaired interest (interest on loan collateral at collateral rate)
2. Add bonus interest to rate if applicable:
   - **Duration bonus:** Added after BONUSDUR threshold year (e.g., after year 10)
   - **AV bonus:** Added when AV exceeds threshold (e.g., AV > $100,000 for EXECUL plans)
3. Calculate unimpaired interest on remaining AV at declared/blended rate

**If method = Blend (IUL):**
- Blend illustrated rates for index and fixed funds according to allocation percentages
- Single blended rate applied to all years of the projection
- **Note:** WAIR method exists in the spec but is NOT used — Blend is the method for all IUL products

**Loan charges:**
- Calculate loan charge accrued for each loan type (fixed and variable)

#### Step 12: Shadow Account Values (if applicable)
1. Calculate shadow target premium
2. Calculate shadow premium load
3. Add net premium and remove WD/SCR/force-outs from shadow AV
4. Calculate shadow NAR and COI charge
5. Calculate shadow monthly deduction (shadow COI + shadow EPU + rider/benefit charges)
6. Calculate shadow interest → end-of-month shadow AV

#### Step 13: Deemed Cash Value (if applicable — CVAT only, ~1% of policies)
1. Add net premium and remove WD/SCR/force-outs from DCV
2. Calculate DCV NAR and COI charge
3. Calculate DCV monthly deduction (DCV COI + EPU + fees + AV charge + rider/benefit + PW39)
4. Calculate DCV interest → end-of-month DCV

#### Step 14: GCO Rider (if applicable)
1. Calculate Qualification Test A for current year
2. Calculate Qualification Test B for current year
3. Look up applicable enhancement rate and eligible premium percent
4. Calculate GCO benefit if year is 15, 20, or 25

#### Step 15: Testing / Lapse Determination
1. Calculate accumulated premium for each year in the 7-pay period
2. Determine if policy is MEC due to 7-pay test
3. Determine if policy is MEC due to CVAT NPT test (if applicable)
4. Check safety net protection (minimum premium / no-lapse guarantee)
5. Check shadow account protection
6. Check positive surrender value
7. Check positive account value
8. Check exception premium protection
9. **Determine if the policy should lapse**

### 4.3 Coverage Segments

**Terminology note:** In the illustration tool, "coverage" refers exclusively to **base coverages** (the insured life's UL coverage segments). Riders (CTR = Life CTR, STR = Sig Term Rider, LTR = Level Term Rider, APBR = Additional Purchase Benefit Rider, etc.) are tracked separately under the rider/benefit framework, NOT as coverage segments. This differs from the Cyberlife admin system where both base and rider coverages appear in the same coverage file.

- A policy can have multiple base coverage segments on the same plancode
- The first coverage is always the base coverage (coverage phase 1)
- Subsequent base coverages are **increase segments** — same plancode as base, treated as additional base coverage with their own issue age, sex, rate class
- Each segment has its own: issue age, sex, rate class, COI rates, surrender charges
- Base coverage segments are summed for total face / band determination
- **FIFO NAR Rule (Critical):** Account value is applied **first-in-first-out** against base coverage segments when calculating NAR. The oldest segment's NAR is reduced first. This is very important for multi-segment policies because it determines how COI charges are distributed across segments with potentially different rate structures.
- Each segment tracks: current SA, original SA, original band

### 4.4 Assumption Scenarios
The illustration produces three sets of projected values:

| Scenario | What Varies |
|---|---|
| **Current** | Current scale COI rates, current expense rates, current declared/illustrated interest rate |
| **Midpoint** | Midpoint between current and guaranteed for COI, expenses, and interest |
| **Guaranteed** | Guaranteed COI rates, guaranteed expense rates, guaranteed interest rate |

Charges that may vary: COI rates, expense per unit, percent of AV charge, monthly fee, premium load, and interest crediting rate.

---

## 5. Illustration Options (User-Configurable)

These are per-illustration settings the user can toggle:

| Option | Description | Default |
|---|---|---|
| Switch to Loans at CB | Withdrawals from cost basis first, then excess as loan | Typically ON |
| Prevent MEC | Restrict premium to 7-pay level | OFF (disabled if already MEC) |
| Allow Loan Payoff with WD | Withdrawal amount can pay off loans | varies |
| Prem Must Apply to Loan | Premium applied as loan repayment first | ON for IUL08 only |
| Allow Guideline Exception Premium | Allow premium beyond guideline when AV < 0 | GPT only |
| Repay Loan with Force Out | Guideline force-outs applied as loan repayment | varies |
| Restrict Loans to Surrender Value | Loan cannot exceed surrender value | varies |
| Cease Loan Repay at Payoff | Stop repayments once loan is fully repaid | varies |

---

## 6. What-If Scenario Inputs

The user can specify year-by-year changes (this is a core feature):

| Input | Per-Year | Description |
|---|---|---|
| Premium Amount | ✓ | Override scheduled premium |
| Premium Mode | ✓ | A (Annual), S (Semi), Q (Quarterly), M (Monthly) |
| Face Amount | ✓ | Change specified amount (increase/decrease) |
| Death Benefit Option | ✓ | Switch DBO A/B/C |
| Loan Amount | ✓ | New loan amount |
| Loan Repayment | ✓ | Repay existing loan |
| Withdrawal Amount | ✓ | Partial withdrawal/surrender |
| Illustrated Interest Rate | ✓ | Override interest rate (IUL per-fund per-month) |
| Rate Class Change | ✓ | Change rate class |
| Rider/Benefit Changes | ✓ | Add/drop/modify riders and benefits |
| Lump Sum Premium | ✓ | One-time additional premium |

---

## 7. Output Values

### 7.1 Annual Summary (Illustration Values)
For each projection year, under each assumption scenario (Current, Midpoint, Guaranteed):

| Field | Description |
|---|---|
| End of Year Age | Attained age at year end |
| Policy Year | Year number |
| Premium Outlay | Total premium paid in year |
| Loan Repayments | Total loan repayments in year |
| Accumulation Value | End-of-year account value |
| Surrender Value | AV minus surrender charge minus loans |
| Death Benefit | Total death benefit |
| Loan Balance | Outstanding loan balance |
| Distributions | Withdrawals, surrenders, loan amounts taken |
| Interest Rate | Credited interest rate |
| MEC indicator | Whether policy became MEC this year |
| GP Cap indicator | Whether guideline premium limit was hit |
| Force Out amount | Premium forced out by guideline limits |

### 7.2 Monthly Detail (CalcEngine)
For debugging and validation, the engine should expose monthly-level values across all 729+ calculation columns. Key monthly values include:
- Beginning/ending AV, surrender value, death benefit
- COI charge (per segment), total monthly deduction
- Premium applied (gross and net of load)
- Interest credited
- Loan balances and charges
- NAR per segment
- All intermediate calculation values

---

## 8. Riders and Benefits

### 8.1 Benefits (enhancements to existing coverage — all must-have for v1)
| Code | Name | Description |
|---|---|---|
| CCV | Continuous Coverage | Shadow account no-lapse guarantee |
| GCO | Guaranteed Crediting Option | Enhancement at years 15/20/25 |
| PW | Premium Waiver | Waiver of charges (PW39 = waiver of greater of all charges or MTP) |
| ADB | Accelerated Death Benefit | ABR benefit (#4=TM, #5=CT, #6=CH) |
| GIO | Guaranteed Insurability Option | Option to increase coverage without evidence |

### 8.2 Riders (coverage on insured for face amount — all must-have for v1)
| Code | Name | Description |
|---|---|---|
| CTR | Children's Term Rider | Term coverage on children, ceases at age 65 |
| STR | Spouse Term Rider | Term coverage on spouse |
| LTR | Level Term Rider | Level term on primary insured |
| APBR | Additional Premium Benefit Rider | Additional coverage rider |

### 8.3 Rider/Benefit Configuration
- **Rider definitions** stored in `tRiderDefinitionFile` (135 rows)
- **Benefit definitions** stored in `tBenefitDefinitionFile` (877 rows)
- Each has its own rate tables for COI and targets

---

## 9. 7702 Compliance (Critical for v1)

### 9.1 Guideline Premium Test (GPT) — ~99% of policies
- **Guideline Single Premium (GSP):** Maximum single premium allowed
- **Guideline Level Premium (GLP):** Maximum annual level premium allowed
- **Accumulated GLP:** Running total of GLP allowance
- Recalculated on policy changes (face changes, DBO changes)
- Maximum 6 guideline recalculations allowed
- Force-outs required when premium exceeds guideline limits

**Calculation approach:** Guideline premium calculations will be performed on a **monthly basis** (similar to the NSP tab approach in the workbook), NOT using annual geometric summation formulas. Monthly calculation is more transparent and auditable — each month's contribution to the guideline premium is visible, making validation straightforward.

### 9.2 TAMRA / MEC Testing
- **7-Pay Premium:** Maximum annual premium over 7-year testing period
- **7-Pay Start Date:** Resets on material changes
- **7-Year Contributions:** Track premium minus withdrawals for each year in window
- **7-Year Lowest DB:** Lowest death benefit in the 7-pay window
- Policy is MEC if cumulative contributions exceed 7-pay premium × years

### 9.3 Cash Value Accumulation Test (CVAT) — ~1% of policies
- **Deemed Cash Value:** Manually entered for CVAT policies
- **Plan_Exceptions:** CVAT-specific override data (~78 rows)
- **NSP (Net Single Premium):** Required for CVAT corridor testing

### 9.4 7702 Settings
- `s7702_MaturityAge`: 100 (default)
- `7702 GLP Rate`: 0.04 (default, with override option)
- `blnEPU_OrigAmt`: Whether EPU uses original or current amount

---

## 10. Interest Crediting

### 10.1 Declared (UL Products)
- Simple declared rate applied to account value monthly
- `monthly_rate = (1 + annual_rate)^(1/12) − 1` (or exact days method)
- Loan collateral earns separate rate
- Bonus interest may apply:
  - **Duration bonus:** After threshold year (typically year 10)
  - **AV bonus (EXECUL):** When AV > $100,000

### 10.2 Blend (IUL Products)
- User inputs illustrated rates per fund per month
- Fixed and index fund rates blended by allocation percentage
- Single blended rate applied to account value
- **Decision:** IUL rates are user inputs for v1; database storage is future

### 10.3 Interest Method: ExactDays
- Interest calculation uses exact day count for the policy month
- `interest = AV × rate × days_in_month / days_in_year`

---

## 11. Technical Architecture

### 11.1 Module Structure (Planned)
Following the ABRQuote module pattern:

```
suiteview/illustration/
├── __init__.py              # Public API
├── main.py                  # UI entry point / launcher
├── core/                    # Calculation engines
│   ├── calc_engine.py       # Monthly processing pipeline
│   ├── monthly_deduction.py # Step 9: COI, expenses, charges
│   ├── premium_handler.py   # Steps 6-8: premium logic
│   ├── loan_handler.py      # Step 7: loan capitalization/repay
│   ├── policy_change.py     # Step 1: withdrawals, face changes
│   ├── guideline_calc.py    # Step 5: GLP, GSP, TAMRA, 7702
│   ├── interest_calc.py     # Step 11: interest crediting
│   ├── shadow_calc.py       # Step 12: shadow account
│   ├── dcv_calc.py          # Step 13: deemed cash value
│   ├── gco_calc.py          # Step 14: GCO rider
│   ├── lapse_test.py        # Step 15: lapse determination
│   ├── target_calc.py       # Steps 3-4: MTP, CTP
│   └── segment_handler.py   # Coverage segment management
├── models/                  # Data classes
│   ├── policy_data.py       # IllustrationPolicyData
│   ├── calc_state.py        # Monthly calculation state
│   ├── assumptions.py       # Current/Midpoint/Guaranteed
│   ├── illustration_input.py # User inputs / what-if
│   └── constants.py         # Product constants
├── data/                    # Static configuration (JSON)
│   ├── plancode_table.json
│   ├── rider_definitions.json
│   ├── benefit_definitions.json
│   └── ... (rate tables from Rates_Control)
└── ui/                      # PyQt6 UI (later)
    ├── illustration_window.py
    ├── input_panel.py
    ├── results_panel.py
    └── whatif_editor.py
```

### 11.2 Key Design Decisions
1. **Stateless computation per month** — each month's calculation takes state in, produces state out
2. **Dataclasses for all state** — `MonthlyState` passed through each pipeline step
3. **Rate lookups via existing `Rates` class** — no new DB connections needed
4. **JSON for Rates_Control data** — plancode table, rider/benefit definitions, and rate tables not in UL_Rates DB
5. **FIFO segment ordering** — account value applied first-in-first-out across base coverage segments for NAR calculation (critical for multi-segment COI accuracy)
6. **Three-pass calculation** — run pipeline once each for Current, Midpoint, and Guaranteed assumptions

### 11.3 Existing Infrastructure to Leverage
| Component | Module | Status |
|---|---|---|
| Policy data retrieval | `suiteview.core.policy_service` | ✅ Ready |
| UL rate lookups (20+ types) | `suiteview.core.rates` | ✅ Ready |
| DB2 connectivity | `suiteview.core.db2_connection` | ✅ Ready |
| PyQt6 UI framework | `suiteview.ui.*` | ✅ Ready |
| ABR calculation pattern | `suiteview.abrquote.core.*` | ✅ Reference |

---

## 12. First Milestone

### 12.1 Goal
**Simple monthly processing for a single policy with one base coverage and no benefits.**

### 12.2 Test Policy: UE000576
| Field | Value |
|---|---|
| Plancode | 1U143900 (ANICO EXECUTIVE UNIVERSAL LIFE) |
| Issue Date | 2016-10-27 |
| Issue Age | 50 |
| Attained Age | 59 |
| Sex | M |
| Rate Class | N (nicotine non-user) |
| Face Amount | $90,000 |
| Death Benefit Option | A (Level) |
| Premium | $150/month ($1,800/year) |
| Account Value | $11,936.84 |
| Cash Surrender Value | $11,936.84 |
| GPT Policy | Yes (def_of_life_ins = 2) |
| Issue State | FL |
| Policy Year | 10, Month 6 |
| No loans | ✓ |
| No table rating | ✓ |
| Band | 2 ($90K face) |
| Guaranteed Interest | 3% |
| Benefits | 3 ABR benefits (#4, #5, #6) — ignore for milestone 1 |

**Validated Surrender Charge Data (Duration 10):**
| Field | Value | Source |
|---|---|---|
| SCR Rate (dur 10) | 28.76 per $1,000 | `Rates.get_rates('SCR', ...)` |
| Units | 90 | $90,000 face ÷ $1,000 |
| Surrender Charge | $2,588.40 | 28.76 × 90 |
| Account Value (PolView) | $11,936.84 | DB2 |
| Cash Surrender Value (PolView) | $11,936.84 | DB2 (= AV, because past SCR period) |
| Calculated SV | $9,348.44 | $11,936.84 − $2,588.40 |

**Note:** PolView shows CSV = AV ($11,936.84) because the policy may be past the surrender charge period or the admin system applies different SCR logic. The illustration engine will calculate SV using the SCR rate × units method as shown above.

### 12.3 Milestone 1 Deliverables
1. **Data model:** `IllustrationPolicyData` dataclass populated from `PolicyInformation`
2. **Plancode config:** JSON file with at least the 1U143900 plancode record
3. **Rate loading:** Load COI, EPP, SCR, MFEE, CORR, GINT, BONUSAV, BONUSDUR from `Rates` class
4. **Single monthly processing:** Implement one month of:
   - Apply premium ($150) minus premium load
   - Calculate COI charge (NAR-based, single segment)
   - Calculate EPU charge
   - Calculate monthly fee
   - Credit interest (declared method)
   - Produce end-of-month AV
5. **Validation:** Compare output month-by-month against RERUN workbook CalcEngine values for UE000576

---

## 13. Phased Delivery Plan

| Phase | Scope | Dependencies |
|---|---|---|
| **M1: Single Month** | Monthly deduction for 1 base coverage, no benefits, no loans | Data model, rates, plancode config |
| **M2: Full Projection** | Loop months to maturity, annual summary, 3 assumption scenarios | M1 |
| **M3: Inforce Injection** | Pull policy from DB2, inject inforce values, project forward | M2 |
| **M4: Segments** | Multiple coverage segments with FIFO NAR | M3 |
| **M5: Loans** | Loan capitalization, repayment, collateral interest | M3 |
| **M6: What-If** | Year-by-year premium/face/DBO/withdrawal changes | M3 |
| **M7: 7702 Compliance** | GLP, GSP, TAMRA, force-outs, MEC testing | M3 |
| **M8: Riders & Benefits** | All riders (CTR, STR, LTR, APBR) and benefits (CCV, GCO, PW, ADB, GIO) | M4 |
| **M9: IUL** | Blend interest method, index fund inputs, AG49 | M6 |
| **M10: SGUL** | SGUL-specific rules (no loans, etc.) | M6 |
| **M11: UI** | Input panel, results display, what-if editor | M6 |
| **M12: Polish** | DCV/CVAT, exception premium, shadow account, ratchet COI, edge cases | All |

---

## Appendix A: Rates_Control Named Tables

> **Note:** Tables marked with ‡ are sourced from the UL_Rates database at runtime via the `Rates` class and do NOT need JSON export. They are listed here for reference only.

| Table | Named Range | Rows | Description |
|---|---|---|---|
| Plancode Configuration | `tPlancodeTable` | C12:BE206 | 55 fields × 200+ plancodes |
| Rider Definitions | `tRiderDefinitionFile` | BG12:BN146 | Rider config |
| Benefit Definitions | `tBenefitDefinitionFile` | BU12:CC888 | Benefit config |
| ‡ GP Corridor Rates | `tRates_CORR` | DJ12:DK350 | Corridor by attained age |
| ‡ Safety Net Period | `tRates_SNET_Period` | DO12:DP74 | By plancode |
| Valid Index Fund IDs | `tValid_IndexFundIDs` | EC12:EC74 | By plancode |
| Issue Age Range | `tRates_IssueAgeRange` | EH12:EJ33 | By plancode |
| Interest Bonus | `tRates_IntBonus` | EO12:EU73 | By duration |
| ~~Strategy Interest Bonus~~ | ~~`tRates_StratIntBonus`~~ | ~~EZ12:FC13~~ | ~~Not needed for illustration~~ |
| CCV Target Rates | `tRates_Rider_CCV_Targets` | varies | Rider targets |
| CCV COI Rates | `tRates_Rider_CCV_COI` | varies | Rider COI |
| Benefit COI Rates | `tRates_Benefit_COI` | varies | By sex/class/band/age |
| Benefit Target Rates | `tRates_Benefit_Targets` | varies | By benefit |
| GCO Benefit Rates | `tRates_Benefit_GCO` | varies | GCO-specific |
| ‡ EPU Rates | `tRates_Base_EPU` | HK12:IF6275 | Monthly expense per unit |
| Premium Load | `tRates_Premium_Load` | IO12:IQ121 | % of premium (TPP target/EPP excess) |
| ‡ Monthly Fee | `tRates_MFEE` | JA12:JB3595 | Flat monthly fee |
| ‡ Shadow Interest | `tRates_Shadow_Interest` | JL12:NK4091 | Shadow account rates |
| ‡ Target Rates | `tRates_Targets` | NU12:NY3143 | MTP/CTP |
| ‡ Guaranteed COI | `tRates_Ultimate_GCOI` | OG12:OH1287 | Ultimate guaranteed COI |
| ‡ Current COI | `tRates_Select_CCOI` | OQ12:TH6135 | Select current COI |
| ‡ Surrender Charges | `tRates_Base_SCR` | TP12:UJ883 | By plancode/age/sex/rc/dur |
| Min Death Benefit Ratios | `tRates_MDBR` | UR11:VP1948 | Corridor/CVAT ratios |

## Appendix B: IUL Index Strategies by Product

| Product | Fund Code | Description |
|---|---|---|
| IUL08 | IX | S&P500 with CAP |
| IUL14 | IX, IC, IS, IF | S&P500 CAP / CAP+floor / specified / no-CAP+fee |
| IUL19 | IX, IF, IP, IR | S&P500 CAP / no-CAP+fee / multiplier / high-multiplier |
| IUL21 | IX, IF, IP, IR, NX, M1 | + NASDAQ100 CAP + S&P MARC5 participation |
| GIUL21 | IX, IF, NX, M1 | S&P500 CAP / no-CAP+fee / NASDAQ / MARC5 |

## Appendix C: Death Benefit Option Rules

| DBO | Death Benefit | Net Amount at Risk |
|---|---|---|
| A (Level) | max(Face, AV × Corridor) | DB − AV |
| B (Increasing) | Face + AV | Face |
| C (Return of Premium) | Face + Cumulative Premium | Face + CumPrem − AV |

## Appendix D: Illustration Options Summary

| Option | Default | Applies To |
|---|---|---|
| Switch to Loans at CB | ON | All |
| Prevent MEC | OFF | All (disabled if MEC) |
| Allow Loan Payoff with WD | varies | All except SGUL |
| Prem Must Apply to Loan | ON=IUL08, OFF=others | All except SGUL |
| Allow GP Exception Premium | OFF | GPT only |
| Repay Loan with Force Out | varies | All except SGUL |
| Restrict Loans to SV | varies | All except SGUL |
| Cease Loan Repay at Payoff | varies | All except SGUL |
