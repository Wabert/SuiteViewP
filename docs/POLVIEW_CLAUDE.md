# PolView — Sub-App Documentation for AI Assistants

**Last Updated:** February 20, 2026

> **Shared architecture** (PolicyInformation, DB2 connectivity, translation
> dictionaries, bookmarks) is documented in [`Agent.md`](../Agent.md).
> This file covers PolView-specific details only.

---

## Overview

PolView is the policy viewer app — it displays life insurance policy data
from DB2 in a tabbed PyQt6 interface. It is a Python port of a VBA/Excel
application (`SuiteView v2.2`).

### Original VBA Application
- **Location:** `SuiteView (v2.2).xlsm`
- **Extracted VBA Code:** `VBA_Extracted/` folder

#### Key VBA Files
| File | Lines | Purpose |
|------|-------|---------|
| `frmPolicyMasterTV.frm.bas` | 6,370 | Main policy display form |
| `cls_PolicyInformation.cls.cls` | 4,624 | Business layer wrapping raw DB2 data |
| `cls_PolicyData.cls.cls` | 916 | Raw DB2 table data access and caching |
| `cls_Rates.cls.cls` | 518 | Rate lookup and calculation |
| `cls_Storage.cls.cls` | 660 | Persistent data storage |
| `frmAudit.frm.bas` | 6,744 | Cyber Audit query tool |
| `mdlDataItemSupport.bas.bas` | 5,864 | Data translation dictionaries |
| `mdlDataSourceConnections.bas.bas` | 466 | ADODB database connectivity |
| `mdlGlobals.bas.bas` | 546 | Global enums, types, constants |
| `mdlPolicyHandler.bas.bas` | 192 | Policy form management and caching |
| `mdlDataMap.bas.bas` | 1,420 | Data mapping utilities |
| `mdlDataSegment.bas.bas` | 1,626 | Segment data handling |
| `mdlUtilities.bas.bas` | 1,192 | General utility functions |

---

## Architecture

### VBA Architecture (for reference)
```
Form (frmPolicyMasterTV)
    └── mPolicy (cls_PolicyInformation) - Business layer with meaningful properties
            └── DB2 (cls_PolicyData) - Raw table data access
                    └── DB2TAB.* tables - Actual DB2 tables
```

### Python Architecture
```
suiteview/polview/
├── main.py                              # Entry point for standalone run
├── models/
│   ├── policy_information.py            # PolicyInformation class (THE data layer, 4100+ lines)
│   └── cl_polrec/
│       ├── policy_data_classes.py       # CoverageInfo, BenefitInfo, LoanInfo, etc.
│       ├── policy_translations.py       # Code-to-text translation dictionaries
│       ├── cyberlife_base.py            # PolicyDataAccessor protocol + parse_date
│       ├── CL_POLREC_01_51_66.py        # Policy base records (01, 51, 66)
│       ├── CL_POLREC_02_03_09_67.py     # Coverage, substandard, renewal rate records
│       ├── CL_POLREC_04.py             # Benefit records
│       ├── CL_POLREC_05_06_07_08_68.py  # Change schedules
│       ├── CL_POLREC_12_13_14_15_18_19_74.py  # Dividends (applied, unapplied, PUA, OYT)
│       ├── CL_POLREC_20_77.py           # Loans (traditional + fund-value)
│       ├── CL_POLREC_32_33_35.py        # Billing
│       ├── CL_POLREC_38_48.py           # Agents
│       ├── CL_POLREC_52.py             # User generic fields
│       ├── CL_POLREC_55_57_65.py        # Fund values
│       ├── CL_POLREC_58_59.py           # Targets (policy & coverage level)
│       ├── CL_POLREC_60_62_63_64_75.py  # Totals & monthliversary values
│       ├── CL_POLREC_69.py             # Financial transactions (FH_FIXED)
│       └── CL_POLREC_89_90.py           # Persons & addresses
├── ui/
│   ├── main_window.py                   # Main PyQt6 window
│   ├── tree_panel.py                    # Left-side policy records tree
│   ├── widgets.py                       # StyledInfoTableGroup, FixedHeaderTableWidget, etc.
│   ├── styles.py                        # PolView Blue & Gold color constants + stylesheets
│   ├── formatting.py                    # Date/amount formatting utilities
│   └── tabs/
│       ├── coverages_tab.py             # Coverages & Benefits
│       ├── policy_tab.py               # Policy details
│       ├── targets_tab.py              # Targets & Accumulators (TEFRA/DEFRA, TAMRA, CommTarget, MTP)
│       ├── adv_prod_tab.py             # Advanced Product Values (UL/IUL monthliversary)
│       ├── persons_tab.py             # Policy persons & addresses
│       ├── activity_tab.py            # Activity/transaction history
│       ├── dividends_tab.py           # Dividends (applied, unapplied, PUA, OYT, deposits)
│       ├── policy_support_tab.py      # Policy Support — file management (MiniExplorer)
│       ├── policy_list_tab.py         # Multi-policy list (PolicyListWindow)
│       └── raw_table_tab.py           # Raw DB2 table viewer
└── data/
    ├── policy_record_db2_tables.json    # Policy Record → DB2 table mappings
    └── field_tooltips.json              # Tooltip text for field labels
```

---

## ⚠️ Traditional vs Advanced Products — Deep Dive

> **Summary** table and detection code are in [`Agent.md`](../Agent.md)
> § "Key Domain Concepts". This section documents the implementation details.

### CoverageInfo Rate Fields

The `CoverageInfo` dataclass (`policy_data_classes.py`) has **two separate rate
fields** and a convenience property:

| Field | Source | Used for |
|-------|--------|----------|
| `premium_rate` | `LH_COV_PHA.ANN_PRM_UNT_AMT` | Traditional products — annual premium rate per unit |
| `coi_rate` | `LH_COV_INS_RNL_RT.RNL_RT` (type "C", ÷ divisor) | Advanced products — cost-of-insurance rate |
| `rate` (property) | Returns `coi_rate` if `is_advanced_product`, else `premium_rate` | Display — automatically picks the right value |

**Rate divisor for Advanced products:**
- Product line `"I"` (Interest Sensitive Life): divide `RNL_RT` by **100**
- All other product lines: divide `RNL_RT` by **100,000**

**VBA equivalent:**
```vba
If mPolicy.AdvancedProductIndicator = "1" Then
    ' Advanced: rate from renewal rate table
    If mPolicy.ProductLineCode = "I" Then
        Rate = mPolicy.RenewalCovRate(xcount, "C") / 100
    Else
        Rate = mPolicy.RenewalCovRate(xcount, "C") / 100000
    End If
Else
    ' Traditional: rate from coverage phase
    Rate = mPolicy.DB2Data.DataItem("LH_COV_PHA", "ANN_PRM_UNT_AMT").value(xcount)
End If
```

### Renewal Rate Table (`LH_COV_INS_RNL_RT`) Reference

This table stores per-coverage renewal rates keyed by type:

| `PRM_RT_TYP_CD` | Meaning | Used for |
|-----------------|---------|----------|
| `"C"` | COI (Cost of Insurance) | Coverage rate display |
| `"T"` | Target | Minimum premium calculations |
| `"M"` | Minimum | Minimum premium calculations |

**Composite key:** `COV_PHA_NBR` + `PRM_RT_TYP_CD` + `JT_INS_IND`

**Lookup pattern:**
```python
# Using PolicyInformation:
idx = policy.cov_renewal_index(cov_pha_nbr=1, rate_type="C", joint_ind="0")
if idx >= 0:
    raw_rate = policy.data_item("LH_COV_INS_RNL_RT", "RNL_RT", idx)
    rate_class = policy.data_item("LH_COV_INS_RNL_RT", "RT_CLS_CD", idx)
```

**Important fields:** `RNL_RT` (rate amount), `RT_CLS_CD` (rate class),
`RT_SEX_CD` (sex code), `ISS_AGE` (issue age)

> ⚠️ **Corrected field names:** Previous versions of this document listed
> `TBL_RT_CD` and `FLT_XTR_AMT` as fields on `LH_COV_INS_RNL_RT`. This is
> **wrong**. Table ratings and flat extras come exclusively from
> `LH_SST_XTR_CRG` (Record 03), not from the renewal rate table. The actual
> DB2 column names are `SST_XTR_RT_TBL_CD` and `XTR_PER_1000_AMT`.

### Policy Form Number

The policy form number comes from the **first coverage** (`COV_PHA_NBR = 1`):
- Field: `LH_COV_PHA.POL_FRM_NBR`
- Access: `coverages[0].form_number`
- Display: Appended to policy number, e.g., `"UIP00203 - EXEC-UL"`

---

## Policy Record → DB2 Table Mapping

| Policy Record | DB2 Tables |
|--------------|------------|
| 01 | LH_BAS_POL, TH_BAS_POL |
| 02 | LH_COV_PHA, LH_NEW_BUS_COV_PHA, TH_COV_PHA |
| 03 | LH_SST_XTR_CRG, LH_XTR_CRG_REQ, TH_SST_XTR_CRG |
| 04 | LH_ALL_COV_BNF_REQ, LH_SPM_BNF, TH_SPM_BNF |
| 05 | LH_COV_NOT_SCH, LH_POL_NOT_SCH |
| 06 | LH_ITS_CHG_SCH |
| 07 | LH_BNF_PPU_CHG_SCH, LH_COV_PPU_CHG_SCH |
| 08 | LH_BNF_VPU_CHG_SCH, LH_COV_VPU_CHG_SCH |
| 10 | LH_COV_REINSURANCE, TH_COV_REINSURANCE |
| 14 | LH_PAID_UP_ADD, LH_ONE_YR_TRM_ADD |
| 15 | LH_APPLIED_PTP, LH_UNAPPLIED_PTP |
| 89 | VH_POL_HAS_LOC_CLT (changed from LH_ in v2.0) |

The full mapping is in `data/policy_record_db2_tables.json` and `config/policy_records.py`.

---

## Data Access Patterns (PolView-specific)

> **Core API** (`data_item`, `fetch_table`, etc.) is documented in
> [`Agent.md`](../Agent.md) § "PolicyInformation". These are PolView-specific
> usage patterns.

### Pattern 1: Filtered Data Access (Type Codes)

Many tables store multiple record types distinguished by a type code:

```python
# Get MTP (Minimum Target Premium) from LH_POL_TARGET where TAR_TYP_CD = "MT"
mtp = policy.data_item_where("LH_POL_TARGET", "TAR_PRM_AMT", "TAR_TYP_CD", "MT")

# Get GLP (Guideline Level Premium) where PRM_RT_TYP_CD = "A"
glp = policy.data_item_where("LH_COV_INS_GDL_PRM", "GDL_PRM_AMT", "PRM_RT_TYP_CD", "A")
```

### Pattern 2: Multi-Table Join by Coverage Phase

When displaying coverage-level data, combine data from multiple tables
using `COV_PHA_NBR` as the join key:

```python
# Build lookup for rates by coverage phase (filter by type)
rate_by_cov = {}
for rnl in rnl_data:
    if str(rnl.get("PRM_RT_TYP_CD", "")).strip() == "M":
        cov_phs = rnl.get("COV_PHA_NBR")
        rate_by_cov[cov_phs] = rnl.get("RNL_RT", 0)
```

**Common Join Keys:**
| Key Field | Tables Using It |
|-----------|-----------------|
| `COV_PHA_NBR` | LH_COV_PHA, LH_COV_INS_RNL_RT, LH_SPM_BNF |
| `AGT_COM_PHA_NBR` | LH_COM_TARGET |
| `PLN_DES_SER_CD` | LH_COV_PHA (plancode) |
| `CK_POLICY_NBR` + `CK_CMP_CD` + `CK_SYS_CD` | All policy tables |

### Pattern 3: Multi-Condition Filter

```python
rate = policy.data_item_where_multi(
    "LH_COV_INS_RNL_RT",
    "RT_CLS_CD",
    {"COV_PHA_NBR": 1, "PRM_RT_TYP_CD": "C", "JT_INS_IND": 0}
)
```

### Pattern 4: Get Full Rows by Filter

```python
# Get all MTP rows as full dictionaries
mtp_rows = policy.get_rows_where("LH_POL_TARGET", "TAR_TYP_CD", "MT")

# Find row index for manual iteration
idx = policy.find_row_index("LH_POL_TARGET", "TAR_TYP_CD", "MT")
if idx >= 0:
    amt = policy.data_item("LH_POL_TARGET", "TAR_PRM_AMT", idx)
```

### Complete Data Access API

| Method | Purpose |
|--------|---------|
| `data_item(table, field, index=0)` | Single value from any DB2 table/field/row |
| `data_item_array(table, field)` | All values for a field across rows |
| `data_item_count(table)` | Row count for a table |
| `fetch_table(table)` | Entire table as `List[Dict]` |
| `data_item_where(table, return_field, filter_field, filter_value)` | Filtered single value |
| `data_items_where(table, return_field, filter_field, filter_value)` | All matching values |
| `data_item_where_multi(table, return_field, filters_dict)` | Multi-condition filter |
| `find_row_index(table, filter_field, filter_value)` | Find row index by type code |
| `get_rows_where(table, filter_field, filter_value)` | Full row dicts matching filter |
| `if_empty(value, default)` | Return default if value is None or empty |

---

## 📦 Policy Data Classes

All structured data objects are defined in `policy_data_classes.py`.
These are used by `PolicyInformation` and the `CL_POLREC_*` modules.

| Class | Source Table(s) | Records |
|-------|----------------|---------|
| `CoverageInfo` | LH_COV_PHA, TH_COV_PHA, LH_COV_INS_RNL_RT, LH_SST_XTR_CRG | 02, 03, 67 |
| `SubstandardRatingInfo` | LH_SST_XTR_CRG | 03 |
| `SkippedPeriodInfo` | LH_COV_SKIPPED_PER | 09 |
| `RenewalCovRateInfo` | LH_COV_INS_RNL_RT | 67 |
| `CoverageTargetInfo` | LH_COV_TARGET | 67 |
| `BenefitInfo` | LH_SPM_BNF | 04 |
| `RenewalBenRateInfo` | LH_BNF_INS_RNL_RT | 04 |
| `AppliedDividendInfo` | LH_APPLIED_PTP | 15 |
| `UnappliedDividendInfo` | LH_UNAPPLIED_PTP | 15 |
| `DivOYTInfo` | LH_ONE_YR_TRM_ADD | 14 |
| `DivPUAInfo` | LH_PAID_UP_ADD | 14 |
| `DivDepositInfo` | LH_PTP_ON_DEP | 19 |
| `LoanInfo` | LH_CSH_VAL_LOAN / LH_FND_VAL_LOAN | 20, 77 |
| `TradLoanInfo` | LH_CSH_VAL_LOAN | 20 |
| `LoanRepayInfo` | LH_LN_RPY_TRM | 20 |
| `AgentInfo` | LH_AGT_COM_AMT | 38 |
| `FundBucketInfo` | LH_POL_FND_VAL_TOT | 55 |
| `TransactionInfo` | FH_FIXED | 69 |
| `PersonInfo` | LH_CTT_CLIENT / VH_POL_HAS_LOC_CLT | 89 |
| `AddressInfo` | LH_LOC_CLT_ADR | 90 |
| `PolicyTargetInfo` | LH_POL_TARGET / LH_COM_TARGET | 58, 59 |
| `GuidelinePremiumInfo` | LH_COV_INS_GDL_PRM | 58 |
| `MVValueInfo` | TH_POL_MVRY_VAL / LH_POL_MVRY_VAL | 75 |
| `ActivityInfo` | (aggregated) | — |
| `UserFieldInfo` | TH_USER_GENERIC | 52 |
| `BillingInfo` | LH_BAS_POL (billing fields) | 32, 33, 35 |
| `PolicyChangeInfo` | (change schedules) | 05–08, 68 |
| `PolicyNotFoundError` | Exception | — |

### ⚠️ Field Naming Convention

Data class field names are **lowercase snake_case** (e.g., `cov_pha_nbr`,
`coverage_phase`). However, constructor calls in some `CL_POLREC_*` modules
use uppercase DB2 column-style names as keyword arguments (e.g., `COV_PHA_NBR=phase`
or `PRS_SEQ_NBR=1`). Both forms work because the dataclass constructor
accepts both.

**Access** always uses the lowercase field name:
```python
cov.cov_pha_nbr     # ✅ Coverage phase number
cov.plancode        # ✅ Plan designation code
cov.premium_rate    # ✅ ANN_PRM_UNT_AMT
cov.rate            # ✅ Property — auto-picks coi_rate or premium_rate
```

---

## VBA Property Mappings

### Coverage Properties (LH_COV_PHA)
| VBA Property | DB2 Column | Python Field |
|--------------|------------|-------------|
| CovPhase | COV_PHA_NBR | `cov.cov_pha_nbr` |
| CovFormNumber | POL_FRM_NBR | `cov.form_number` |
| CovPlancode | PLN_DES_SER_CD | `cov.plancode` |
| CovIssueDate | ISSUE_DT | `cov.issue_date` |
| CovMaturityDate | COV_MT_EXP_DT | `cov.maturity_date` |
| CovUnits | COV_UNT_QTY | `cov.units` |
| CovVPU | COV_VPU_AMT | `cov.vpu` |
| CovIssueAge | INS_ISS_AGE | `cov.issue_age` |
| CovFaceAmount | COV_UNT_QTY × COV_VPU_AMT | `cov.face_amount` |
| CovStatus | PRM_PAY_STS_CD | `cov.cov_status` |
| CovCeaseDate | NXT_CHG_DT (if NXT_CHG_TYP_CD="0") | `cov.nxt_chg_dt` |
| CovTerminateDate | TMN_DT | `cov.terminate_date` |
| CovCOI/Rate (Trad) | ANN_PRM_UNT_AMT | `cov.premium_rate` |
| CovCOI/Rate (Adv) | LH_COV_INS_RNL_RT.RNL_RT (type "C") | `cov.coi_rate` |
| Rate (auto) | *picks by product type* | `cov.rate` property |
| CovAnnualPremium | ANN_PRM_AMT | `cov.annual_premium` |

### Coverage Properties (LH_COV_INS_RNL_RT)
| VBA Property | DB2 Column | Python Field |
|--------------|------------|-------------|
| CovSex | RT_SEX_CD (1=M, 2=F) | `cov.sex_code` (from LH_COV_PHA) |
| CovRateclass | RT_CLS_CD | `cov.rate_class` |
| RenewalCovRate | RNL_RT | (via `cov_renewal_index()`) |

### Substandard Properties (LH_SST_XTR_CRG)
| VBA Property | DB2 Column | Python Field |
|--------------|------------|-------------|
| CovTableRating | SST_XTR_RT_TBL_CD | `cov.table_rating` (numeric) / `cov.table_rating_code` (letter) |
| CovFlatExtra | XTR_PER_1000_AMT | `cov.flat_extra` |
| CovFlatCeaseDate | SST_XTR_CEA_DT | `cov.flat_cease_date` |

### Benefit Properties (LH_SPM_BNF)
| VBA Property | DB2 Column |
|--------------|------------|
| BenPlancode | SPM_BNF_TYP_CD + SPM_BNF_SBY_CD |
| BenCovPhase | COV_PHA_NBR |
| BenFormNumber | BNF_FRM_NBR |
| BenIssueDate | BNF_ISS_DT |
| BenCeaseDate | BNF_CEA_DT |
| BenOriginalCeaseDate | BNF_OGN_CEA_DT |
| BenUnits | BNF_UNT_QTY |
| BenVPU | BNF_VPU_AMT |
| BenIssueAge | BNF_ISS_AGE |
| BenRatingFactor | BNF_RT_FCT |
| BenRenewalIndicator | RNL_RT_IND |
| BenCOIRate | BNF_ANN_PPU_AMT |

---

## Valuation Date Logic

```
For UL/IUL products (Advanced):
  ValuationDate = Last MVRY_DT from LH_POL_MVRY_VAL

For Traditional products:
  ValuationDate = NextMonthliversary - 1 month
  Where NextMonthliversary = POL_NXT_MNT_DT from LH_BAS_POL
```

### Policy Year & Attained Age
```
PolicyYear = CompletedDateParts("YYYY", CovIssueDate(1), ValuationDate) + 1
AttainedAge = CovIssueAge(1) + PolicyYear - 1
```

---

## UL Product Codes

| Code | Product |
|------|---------|
| IUL08 | Indexed UL 2008 |
| IUL14 | Indexed UL 2014 |
| IUL19 | Indexed UL 2019 |
| EXECUL19 | Executive UL 2019 |
| SGUL15 | Guaranteed UL 2015 |
| SGUL18 | Guaranteed UL 2018 |
| SGUL20 | Guaranteed UL 2020 |

---

## Get Policy Flow (VBA Reference)

```
User enters policy number + selects region
    │
    ▼
mdlPolicyHandler.GetPolicy(policyNum, region, sysCode)
    ├── Check cache (dctPolicyList) → return if cached
    └── Create new cls_PolicyInformation
            │
            ▼
        cls_PolicyData.ValidatePolicyRequest()
            ├── Query LH_BAS_POL for TCH_POL_ID
            └── Handle multiple company codes
            │
            ▼
        frmPolicyMasterTV.PopulatePolicy(oPolicy)
            ├── Display basic policy info in header
            ├── Build TreeView nodes for navigation
            ├── PopulateCoverages() — iterate COV_PHA_NBR
            ├── PopulateBenefits() — LH_SPM_BNF
            └── Populate financials (loans, premiums, MV values)
```

---

## Cyber Audit Feature (Pending — Phase 2)

The Cyber Audit tool allows users to search for policies matching multiple
criteria and export results. It is a complex query builder implemented in VBA
as `frmAudit.frm.bas` (6,744 lines).

### Audit Query Tabs & Criteria
| Tab | Criteria Available |
|-----|-------------------|
| **Policy** | Company, Market org, Status codes, State, Issue dates, Billing form |
| **Coverage** | Plancode, Product line, Product indicator, Issue age, Sex, Rate class, Table rating, Flat extras |
| **Policy(2)** | MTP/GLP/Shadow AV accumulators, Premium YTD ranges, Loan indicators, Grace/Overloan, NFO options, GP/CVAT |
| **Rider** | Up to 3 rider specs: plancode, person code, post-issue, table rating |
| **Benefits** | Benefit type, cease date criteria, COLA indicator |
| **Display** | Select which columns appear in results, export options |

### SQL Construction Pattern (VBA)
```sql
-- Step 1: WITH clauses (CTEs)
WITH DUMBY AS (SELECT 1 FROM DB2TAB.LH_COV_PHA),
     COVERAGE1 AS (SELECT * FROM DB2TAB.LH_COV_PHA WHERE COV_PHA_NBR = 1),
     ...

-- Step 2: SELECT with display columns
SELECT POLICY1.CK_POLICY_NBR, COVERAGE1.PLN_DES_SER_CD, ...

-- Step 3: FROM with JOINs
FROM DB2TAB.LH_BAS_POL POLICY1
INNER JOIN COVERAGE1 ON POLICY1.TCH_POL_ID = COVERAGE1.TCH_POL_ID

-- Step 4: WHERE with criteria
WHERE POLICY1.CK_SYS_CD = 'I'
  AND POLICY1.CK_CMP_CD IN ('01','30')
```

---

## Current Status

### Completed ✅
1. **Coverages Tab** — Policy info header, coverages table, benefits table, substandard ratings
2. **Targets & Accumulators Tab** — TEFRA/DEFRA, accumulators, TAMRA, commission targets, MTP, minimum premium
3. **Policy Tab** — Basic policy details, billing info, agents
4. **Persons Tab** — Policy persons & addresses
5. **AdvProdValues Tab** — Advanced product values, monthliversary history, fund allocations
6. **Activity Tab** — Transaction history (FH_FIXED)
7. **Dividends Tab** — Applied/unapplied dividends, PUA, OYT, deposits on deposit
8. **Policy Support Tab** — File management using MiniExplorer, drag-and-drop tools
9. **Policy List Tab** — Multi-policy comparison window (PolicyListWindow)
10. **Raw Table Tab** — Raw DB2 table viewer with column filtering
11. **FixedHeaderTableWidget** — Excel-style column filtering + right-click copy/export
12. **StyledInfoTableGroup** — Unified info/table container widget
13. **Export to Excel** — COM-based bulk export from any table

### Pending 📋
1. Full cls_PolicyInformation parity — many VBA properties still need porting
2. Cyber Audit feature (Phase 2)
3. Misstatement tab
4. Check Reinsurance button
5. Unit tests

---

## Design Decisions

1. **PyQt6 over tkinter** — Richer widget set, better table support, professional look.
2. **pyodbc over ADODB** — Python uses pyodbc for DB2 ODBC vs VBA's ADODB.
3. **Lazy table loading** — Tables queried from DB2 only when first accessed (matches VBA caching).
4. **StyledInfoTableGroup** — Unified component for info fields and/or data tables.
5. **Tooltip system** — Field tooltips stored in JSON for easy maintenance.
6. **CL_POLREC modules** — Each module handles a group of related policy records and returns typed dataclass objects.
7. **Dual-layer data access** — `PolicyInformation` provides both raw `data_item()` API and high-level methods like `get_coverages()` returning typed objects.
8. **Blue & Gold theme** — PolView uses a classic navy/gold color scheme defined in `ui/styles.py` (distinct from ABR Quote's Crimson Slate).

---
*This file covers PolView-specific details. For shared architecture, see [`Agent.md`](../Agent.md).*
