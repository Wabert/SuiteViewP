# PolView — Sub-App Documentation for AI Assistants

**Last Updated:** September 8, 2026

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
- **Extracted VBA Code:** `docs/vba_reference/` folder

#### Key VBA Files
| File | Lines | Purpose |
|------|-------|---------|
| `frmPolicyMasterTV.frm` | 6,370 | Main policy display form |
| `cls_PolicyInformation.cls` | 4,624 | Business layer wrapping raw DB2 data |
| `cls_PolicyData.cls` | 916 | Raw DB2 table data access and caching |
| `cls_Rates.cls` | 518 | Rate lookup and calculation |
| `cls_Storage.cls` | 660 | Persistent data storage |
| `frmAudit.frm` | 6,744 | Cyber Audit query tool |
| `mdlDataItemSupport.bas` | 5,864 | Data translation dictionaries |
| `mdlDataSourceConnections.bas` | 466 | ADODB database connectivity |
| `mdlGlobals.bas` | 546 | Global enums, types, constants |
| `mdlPolicyHandler.bas` | 192 | Policy form management and caching |
| `mdlDataMap.bas` | 1,420 | Data mapping utilities |
| `mdlDataSegment.bas` | 1,626 | Segment data handling |
| `mdlUtilities.bas` | 1,192 | General utility functions |

---

## Architecture

### Progressive background loading

`GetPolicyWindow.load_policy()` queues work and returns without database access.
The native window can display a loading state immediately. A dedicated worker
loads identity and Coverages first, then prepares Policy, Targets, Persons,
Activity, Dividends, Loans, Advanced Values, Reinsurance and Support eligibility.
Ready pages remain usable while other data loads. Selecting a pending page moves
it ahead of queued work; it does not interrupt an active database call.

`ui/policy_load_controller.py` owns the serial QThread scheduler.
`services/policy_prefetch.py` owns data-only preparation, including the existing
illustration-based surrender calculation and Reinsurance lookup. Never move a
widget's `load_data_from_policy()` into a worker. Widgets render prepared data
on the GUI thread, once per displayed policy, under `cached_reads_only()`.
Advanced Values and Reinsurance receive their prepared payloads explicitly.
Hidden pages are prepared but not populated until selected.

Advanced Values' **policy data is not conditional on illustration support**.
If optional surrender calculation encounters missing rates/configuration,
invalid illustration inputs or unavailable calculation dependencies, only the calculated
Surrender Charge / Surrender Value show `N/A`, with an explanatory notice and
tooltips; AV, fund history, allocations and monthliversary data still render.
Validate and snapshot the record data **before** attempting the optional calculation;
failed illustration-only table reads must not contaminate that snapshot. Expected
calculation failures are logged with their traceback and shown beside the affected
fields, never as a whole-tab error/Retry. Required policy-record read failures
still fail explicitly, rather than displaying blank/zero values as retrieved data.
Never invent a plan configuration or substitute zero. Switching to a supported
plan clears the notice and restores calculated fields. Calculation-dependent
tools such as RERUN retain their existing validation.
Live regressions: N0100046 / 01 / FN2VN300 (no configuration) and S1360299 / 01 /
1S134F00 (missing surrender rates); use the native profiling helper with
`--all-tabs --expect-surrender-unavailable --expect-surrender-reason
"Missing surrender rates" --screenshot <path>` for the latter.
UL045809 continues to verify supported-plan calculations.

The worker owns its database connections and private policy cache. Cross-thread
results are detached data snapshots, never live connections or mutable shared
cache dictionaries. Merging snapshots preserves the GUI policy's identity.
The shared policy service still handles company choice, pending policies and
cross-app cache reuse; worker calculations use their own scoped instance.
Removing history invalidates shared aliases.

Tab suffixes/tooltips identify pending and failed loads. Opaque loading/error
overlays cover old-policy contents and disable underlying controls, including
keyboard actions. Failures remain explicit and offer Retry without blocking
other pages. Every request has a generation token: switching policies ignores
old results and cancels queued work. In-flight ODBC calls finish on their owning
thread before connections close. Window destruction requests nonblocking
cleanup; application exit waits for orderly worker shutdown.
Connections request a 15-second login timeout. The DB2 provider probes query
timeout support before querying: CyberLife's DV driver rejects
`SQL_ATTR_QUERY_TIMEOUT` with HYC00, so only that specific unsupported feature
is logged and disabled. In-flight DV queries cannot be forcibly timed out by
this mechanism; shutdown waits for the driver to finish. Other connection/query
errors remain failures. Worker-scoped rate connections close on the worker,
including helper-local instances created by the illustration calculation.

Dividends/Loans appear pending until their availability checks finish; the
existing final availability and advanced-product rules are unchanged. Block
`currentChanged` while rebuilding optional tabs. Other Data retains per-policy
inputs/results restoration. External Other Data queries, raw-table/rate browsing,
support-folder browsing, GLP and Forecast remain explicit user actions, not
automatic background scans.

Read-only native verification:
`venv\Scripts\python.exe tools\app\profile_polview_load.py --policy UL045809
--company 01 --all-tabs --output <report.json> [--screenshot <path>]`.
It uses an isolated profile and reports request-return, shell-visible,
Coverages-ready and background-complete timings separately. It checks GUI timer
heartbeats (maximum gap below 0.5 seconds), off-GUI connections/table fetching,
unique table reads, all visible page states, cache identity and surrender fields.
Screenshots include both loading and completed views. `--profile-load` profiles
initial preparation on the worker; `--profile-construction` profiles native widget
construction. `--compare-warm` repeats without policy caches and reports the
complete second background load, not a cache-hit timing.

The first use still pays module/window construction and initial ODBC startup.
Background loading avoids freezing the GUI during data access; it does not
eliminate network latency. Historical synchronous measurements were 9.76s /
56 table reads originally, then approximately 2.1s / 15 initial reads after
deferring hidden tabs. That policy-only timer excluded imports/construction:
the latter synchronous version took 3.45s overall in a fresh standalone run,
including 1.23s for its first DB2 connection. Do not present those historical
measurements as current async click-to-display timings or latency guarantees.

Read-only native UL045809 / 01 verification on 2026-09-20: request returned in
0.009s, loading shell displayed in 0.287s, Coverages ready in 1.895s (10 table
reads), and remaining background data ready in 8.141s. All 33 table reads and
database connections ran off the GUI thread; maximum timer heartbeat gap was
0.100s. Imports (1.146s) and widget construction (1.281s) are separate cold costs,
not included in those request-relative timings.

Regressions: `tests/test_polview_lazy_loading.py`,
`tests/test_polview_loading_overlay.py`, `tests/test_policy_prefetch.py`,
`tests/test_policy_service_cache.py`, `tests/test_policy_launcher.py`,
`tests/test_polview_other_data.py` and `tests/test_reinstatement_ui.py`.

### Other Data

The permanent **Other Data** tab follows Policy Support. Its left panel selects
SAP, CLAIMSFILE, TAICyberTAIFd, orion_pcr3_r or CYBERLIFE_PDF; their existing
filterable grids and query controls are embedded in the main panel, not opened
as separate tabs. These five buttons no longer appear on Policy Support.

CLAIMSFILE and CYBERLIFE_PDF query immediately on first selection for a loaded
policy, with a **Refresh** button for another read. SAP, TAICyberTAIFd and
orion_pcr3_r retain their date inputs and explicit query actions. Merely loading
a policy or opening Other Data does not query any of these sources.
Switching sources retains inputs/results. Switching back to a cached policy
restores its selected source, inputs, results and access notices without querying.
A new policy clears the panel and starts with no source selected.

Regression: `tests/test_polview_other_data.py` covers native routing, immediate
versus prompted queries, refresh, errors and policy-state isolation without live
data. `tools/app/verify_other_data_tab.py --output-dir <directory>` captures the
native layout using synthetic results only.

### UL Reinstatement

**Policy Support > UL Reinstatement** opens a single optional **Reinstatement**
tab. A non-UL policy gets an informational popup and no tab. The first row
shows the canonical last entry code/description, termination effective date,
quote date and completed years/months terminated. Only a lapse is eligible;
surrenders and other statuses must never produce a reinstatement premium.
Changing/reloading the policy removes the tab and clears its previous quote.
Reopening or **Recalculate** refreshes the quote date and result.

The two side-by-side sections are **Home Office Reinstatement** (continuous
coverage) and **Skipped Coverage Reinstatement**. Skipped Coverage remains
visible and grey with a note: its calculation rules have not been specified,
so no skipped-coverage premium is manufactured.

The Home Office pay-to date is the latest issue-day monthliversary on or
before the quote date. Funding includes the following monthliversary's
deduction. The service in `suiteview/polview/services/reinstatement.py` owns
eligibility, dates and calculations; the UI must not derive its own financial
rules. The result includes the premium and a reconcilable breakdown:

- Safety net: premiums paid less withdrawals and next-monthliversary debt
  must cover accumulated minimum target premium through that monthliversary.
- Outside safety net, active shadow: shadow value less next-monthliversary
  debt must be positive after the deduction.
- Otherwise: surrender value must be positive after that deduction.

Missing data or an unsupported calculation basis must display **Unavailable**,
not a zero or a previous successful quote. A solved zero remains visible.
Native UI regression tests live in `tests/test_reinstatement_ui.py`.
Real-engine calculation regressions live in `tests/test_reinstatement.py`,
including exact-cent minima, all three funding bases, receipt-date interest,
debt at the next deduction, lapse-only restoration and missing-data rejection.
The breakdown lists premiums paid, withdrawals and accumulated MTP separately
and includes the equation for the selected funding basis.

Quotes preserve regulatory acceptance caps and forceouts, use one premium on
the quote date (never backdated), and restore only coverages explicitly
terminated on the policy's lapse date. Historical transactions after the
opening snapshot, ambiguous benefit termination, missing rates/balances and
indexed-crediting plans currently produce an explicit unavailable reason.
Reinstatement-specific regulatory resets are not assumed.

`tools/app/verify_reinstatement_tab.py --output-dir <directory>` captures an
explicitly synthetic UI demonstration without database access; supplying
`--policy <number> --company <code> --region CKPR` instead checks a live quote
read-only. Synthetic captures are not evidence of a live policy quote.

### Coverage and benefit zero values

`PolicyInformation` preserves DB2 numeric zero separately from missing values
when building coverages and benefits. Zero units, original units or VPU produce
zero amounts when both operands are present; a missing operand still produces
`None`. Premium rates, benefit ratings and flat extras also retain explicit zero.
The Coverages tab displays these zeros, including benefit issue age and rates,
while retaining blank not-applicable fields (such as nonrenewing renewal rates).
Regression: `tests/test_polview_coverage_zero_values.py`.
Read-only live check for UL054808:
`tools/app/verify_coverage_zero_values.py` compares the coverage grid to DB2
amounts and can save a screenshot and JSON report.

### Whole Life Rates view

In the left **Rates > Coverages** tree, selecting a coverage on a traditional
`WL` policy now displays cash values from `UL_Rates.WL_RATE_CV`, not UL COI
tables. `PolicyInformation.build_coverage_rate_matrix()` dispatches to the
separate Whole Life matrix builder; the existing UL/ISWL/Term route is unchanged.
The view reuses the normal filterable/sortable `RawTableTab` grid.

The canonical lookup is `PolicyInformation.rates_wl_cv(coverage_index)` through
`Rates.get_wl_cash_values()`. Coverage indices are 1-based, as in the other
PolView rate methods. Build the six-character key from these **verified**
`LH_COV_PHA` columns, not from the displayed plancode:

| Part | Column | Width |
|---|---|---:|
| Class | `INS_CLS_CD` | 1 |
| Base series | `PLN_BSE_SRE_CD` | 3 |
| Subseries | `LIF_PLN_SUB_SRE_CD` | 2 |

Preserve fixed-width spaces; additionally bind the policy's company code and
the coverage's issue age. PolView selects the **blank `USER_DEFINED` variant
only**. It never falls back to user `00`, another company, another age or a
nonblank variant. A nonblank variant requires an independently established
mapping (the shared API can accept an explicit key).

For Whole Life policies on **ETI or RPU** (`premium_pay_status_code` 44 or 45),
selecting a coverage shows **"Cash value file is not available for policies on
ETI or RPU."** in the Rates grid and status bar. This check precedes the rate/key
lookup and clears previous results; it does not substitute the original Whole
Life basis for the converted policy. Other paid-up statuses still load normally.
Policy `13046235` is the live ETI regression example.

The schedule maps actual source duration to `Decimal` rate. Duration zero is
the issue date, duration one the first anniversary; do not apply the UL
one-based-array convention or truncate to an inferred maturity. CV is shown
**per unit**, alongside the coverage's value per unit, not as a policy surrender
value. Missing schedules display the lookup keys; missing inputs, incomplete
schedules and database failures display errors and clear previous results.
Stored cash values can include Rate Manager's explicitly enabled early-negative
CVF inference. Its signed-header/initial-minimum rule is an assumption, recorded
in the load receipt; PolView displays the stored values without re-inferring
signs. For `08 / 1WL511 / 59`, that rule zeros duration 1's `22.27` and retains
duration 2's `0.94`.

NSP, PUI and dividend rates remain explicitly **not yet available** in this
Rates view. Add independent family accessors and schedule columns to the WL
builder when their selection rules are verified; do not manufacture zero rates
or reuse cash values as NSP.

Live regression example: policy **05335420**, company **08**, coverage 1,
plancode `201WL500`, key **1WL511**, issue age **59** has 42 durations, **0-41**.
Duration 26 is **610.86** per unit; duration 41 is **1,000.00**. The auditable
`tools/rates/verify_polview_wl_rates.py` helper compares the entire displayed
schedule with the database and can capture the actual native Rates surface.

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
| 53 | LH_ASSET_RAL_SCH, LH_ATM_TRS_SCH, LH_AWD_PYE_ALC, LH_AWD_SCH, LH_DCA_SCH, LH_MKT_TM_AUT, LH_SWF_SCH |
| 56 | LH_GEN_FND_RLE, LH_MKT_VAL_ADJ_RLE |
| 59 | LH_TAMRA_7_PY_PER, LH_TAMRA_7_PY_YR, LH_TAMRA_MEC_PRM |
| 89 | VH_POL_HAS_LOC_CLT (changed from LH_ in v2.0) |

The full mapping is in `data/policy_record_db2_tables.json` and `config/policy_records.py`.
The left-hand Policy Record table sweep checks every table in that mapping.
Tables with policy rows are shown normally; a table that cannot be queried is
shown under its Policy Record as an **unavailable** warning with the DB2 error
in its tooltip, rather than being silently omitted as though it were empty.

### Policy Record Viewer (green-screen segment display)

**Button:** "📟 Record" in the PolView header bar (`GetPolicyWindow`) opens
`PolicyRecordViewerWindow` (`suiteview/polview/ui/policy_record_viewer.py`).

Purpose: show a policy record segment exactly as staff see it on the CyberLife
mainframe terminal (black screen, green monospace), but **every value is
hover-aware** — hovering a value shows its field name and, where known, the
COBOL / DB2 source mapping. This turns an intimidating wall of codes into
something self-explanatory.

- **Implemented, policy-backed tabs only; never sample-screen fallbacks.** Tabs are discovered
  from the canonical `POLICY_RECORD_TABLES` mapping through
  `PolicyInformation.fetch_table()` and `table_error()`. Segments with no rows
  are omitted, including segment 56 on UL045809. Populated segments whose screen
  is not implemented are also omitted: screens will be built out one by one.
  Segments without screen metadata do not query their unimplemented tables.
  No policy means
  no segment tabs. DB2/build failures show an explicit **LIVE DATA ERROR** and
  the empty unavailable state, never captured values or an assumption of absence.
  Supported screens retain their green **LIVE** badge. The live path
  is: `PolicyRecordViewerWindow` → `build_screen(segment, pi)` →
  `policy_record_builder.build_segment_lines(segment, pi, screen)`. The builder
  only rebuilds `lines`; the static `fields` map and `layout_html` still come
  from the bundled `seg_<n>.json`.
  Segment 69 discovery uses the explicitly verified 24 financial-history tables:
  all have policy/company keys and no `CK_SYS_CD`. `PolicyData` retains the system
  filter for other tables and binds these character keys with `SQL_VARCHAR`
  input sizes; DataDirect rejects inferred Unicode parameter types with HY004.
  Schema verification: `tools\policyrecord\probe_history_schema.py`.
  Regression: `tests/test_policy_record_history_keys.py`.
- **Right-click Copy on every value.** `_MainframeToken` reuses `CopyableLabel`,
  preserving exact displayed text, including zeros, signs, padding and dim/amber
  values. Consecutive same-field runs (independently colored flag bits) copy as
  one complete value. Hover/source tooltips remain unchanged.
  Regression: `tests/test_policy_record_viewer.py`.
- **Segment 04 Benefits (6204).** The live 81-byte layout is documented in
  **D20** printed pp.159-175 and diagram p.374 (not D202). All four supplied
  U0566833 / 01 / CKPR capture lines match, including PPA `4.500`, premium-waiver
  `.01`, both eight-bit flags, renewable blank versus nonrenewable `X`, and the
  local automatic-rate-deny `N`. U0633187 also verifies the ABR11-TM benefit.
  `policy_record_benefits.py` reads only through `PolicyInformation`, joining
  `LH_SPM_BNF` to `TH_SPM_BNF` by policy/company/system, phase, benefit
  type/subtype, person/sequence, status and issue date. It preserves source
  order within each phase; never sort the screenshot's A0/39 alphabetically.
  All 16 bits have verified DB2 mappings; none are illustrative zeros.
  Type U reads the use-code byte from `COL_ICE_FQY_CD`; other benefits use
  `BNF_STA_CD`. Zero values remain real; NULL numeric slots are dim and annotated.
  Missing TH rows show an unavailable deny slot, not an assumed `N`.
  Option/inflation/CPI data, all-coverage request records and nonblank frequency/
  ABR qualification user fields require further screen verification and report
  explicit errors rather than silently discarding data. The old HTML sheets
  disagree on rate-deny/frequency bytes 76/77; the layout reference discloses
  that ambiguity. Do not invent reserved/user bytes or an 80-byte variant.
  Segment 04 metadata contains field specs and layout only, with no captured
  policy values; its dedicated builder supplies every terminal line.
  - Regenerate metadata: `venv\Scripts\python.exe tools\policyrecord\build_seg04_screen.py`.
  - Regression: `tests/test_policy_record_segment04.py`.
  - Read-only capture comparison:
    `venv\Scripts\python.exe tools\policyrecord\probe_segment04.py
    --expect-u0566833 --output <report.json>`.
  - Native preview:
    `venv\Scripts\python.exe tools\policyrecord\preview_policy_record.py @<config.json>`,
    with `policy: "U0566833"`, `company: "01"`, `tab: "04"`,
    `expect_live: ["04"]`, `expect_absent: ["03", "69", "75"]`,
    `expect_no_errors: true` and `copy_field: "Policy Protection Interest Rate"`.
- **Three value kinds (color-coded).** Every rendered value is one of:
  - **real** (green) — the field has a DB2 source; the value comes from
    `pi.data_item(table, column)`, formatted to match the mainframe (dates
    `MM/DD/YYYY`, the `12/31/9999` high-date sentinel shown as the null date
    `00/00/1900`, factors/amounts with a dropped leading zero e.g. `.08640`,
    a null real field shown as its format-appropriate empty `00/00/1900` /
    `.00000` / `0` / blank).
  - **example** (amber) — the field has **no** DB2 source (packed flag bytes,
    extract date, PerformancePlus indicators, etc.), so a clearly-labelled value
    is shown. Its tooltip leads with **"⚠ EXAMPLE DATA — NOT REAL POLICY DATA"**
    and explains the value isn't stored in DB2. Runs carry `"example": true`. For
    a **template** segment the example text is the realistic archive sample value
    (dates normalised to `00/00/1900`); Segment 58's Flag Byte A uses the same
    amber `example` treatment.
  - **structural** (dim green) — `"dim": true` runs are still supported by the
    viewer, but the current builders don't emit them (null reals now render as a
    format-appropriate empty in normal green, matching the terminal, and the
    template simply omits reserved bytes the mainframe never displays).
- **Segment 01 live mapping (template-accurate).** Screen 6201 ("Basic Policy")
  is a **flat fixed layout** (~115 fields, mostly `LH_BAS_POL` / `TH_BAS_POL` /
  `LH_FXD_PRM_POL`) whose on-screen arrangement is reproduced from a **real
  terminal capture**. `seg_01.json` is a `template` screen: its `lines` are the
  authentic mainframe layout (from `docs/Policy Record/Archive/Policy Record 01
  - BKUP 20161205.htm`), and each value token is annotated with its DB2 source
  and byte-ordered field name **bridged from the Sample 6201 mapping** (the
  archive layout and the Sample `field_specs` proceed in the same byte order —
  validated as a 1:1 alignment). `_build_templated_segment` walks the template
  verbatim (preserving line breaks + spacing) and fills each token: chrome roles
  (`screen_name`→`6201,`, `policy`, `seg_id`, `seg_len` kept at `0292`,
  `current_date`, `user`, `region`) resolve to live values; `db2` tokens read
  live and format like their sample (`_format_like` / `_infer_fmt`), with **date
  rendering driven by the authoritative CyberDoc format** (see the packed-date
  bullet below); tokens with no `db2` render as amber example data. Regenerate the
  JSON with `tools/policyrecord/build_seg01_json.py` (merges the archive template + a fresh
  Sample mapping). Probe live values with `tools/policyrecord/probe_segment01.py '{"policy":
  "UL040023"}'`; verified against a real 6201 screenshot for UL040023.
  - **Billing-area mapping corrections (verified vs U0175443, per CyberDoc D20).**
    The CyberLife *Mode* field (`FBRBMODE-MODE`, 2 bytes, byte 145-146 →
    `PMT_FQY_PER`) **precedes** *Nonstandard Mode* (`FBRMDNST-NONSTD-MODE`, 1 byte,
    byte 147 → `NSD_MD_CD`) — so the screen reads `G 1 0 0` (Billing Form / Mode /
    Nonstandard / Currency). *Other Kind* (`FBRKIND-OTHER-KIND`, byte 166, "policy
    change report type") is what carries **`POL_CHG_RPT_TYP_CD`** — it shows the
    change-report code (e.g. `2` = activity register) *between the Other Date and
    Billing Date*; the *Change Pending Code* byte (`FBRPEND`, 152) is genuinely
    **Reserved** with no DB2 source. (The COBOL↔DB2 Translation sheet maps
    `POL_CHG_RPT_TYP_CD → FBRPEND`, but the live screen and CyberDoc semantics put
    the value at `FBRKIND` — a Translation-sheet slip; trust the screen.) The tail
    *New Business* / *Premium-as-Loan-Payment* indicators (bytes 235-236) are blank
    on the real screen, so they render blank (never fabricated). Locked by
    `TestSegment01Mapping` in `tests/test_policy_record_formatting.py`; re-verify
    with `tools/policyrecord/dump_seg01_live.py '{"policy": "U0175443", "region": "CKPR"}'`.
- **Segment 58 live mapping (verified).** Screen 6258 ("Target Premiums") is the
  **union of three DB2 tables, laid out by `SEG_IDX_NBR`**:
  `LH_COM_TARGET` (phase=`AGT_COM_PHA_NBR`, rule=`TAR_DT_RLE_CD`; codes CA/CP/CT/VC),
  `LH_COV_TARGET` (phase=`COV_PHA_NBR`, rule=`PRM_RLE_CD`; code ST),
  `LH_POL_TARGET` (phase→`0`, rule=`PRM_RLE_CD`; codes IX/MA/MT/TA/TS). Each entry
  is `code(2) flag(8) phase(1) rule(1) date(MM/DD/YYYY) amount(2dp)`; the header is
  seg id `58`, length `6 + 15*N` (4-digit), and entry count `N`. **Flag Byte A**
  (byte 9) has no DB2 source — it's a packed COBOL byte — so it renders as the
  amber `00000000` *example* placeholder. Probe with `tools/policyrecord/probe_segment58.py`.
- **Segment 53 Sweep Fund live mapping (verified against UE142109).** Screen
  6253 ("Automatic Transaction Control") reads the fixed record from
  `LH_ATM_TRS_SCH` and the type-B variable data from optional `LH_SWF_SCH`.
  CyberLife MOYR fields are decoded as a one-based month count from January
  1900 (`0` -> `00/1900`; `1460` -> `08/2021`). The live UE142109 values match
  the supplied terminal capture exactly: type/sequence, start/suspend/restart,
  cease and maintenance dates, activity dates/day, `SWEEP` origin, status,
  frequency, and fixed-width blank event/error fields. `LH_SWF_SCH` supplies
  minimum balance, sweep frequency/day/month when a matching type+sequence row
  is available. A SQLCODE `-551` on that table now blocks the screen with an
  explicit data-load error, rather than substituting captured sweep values.
  The six packed flag bytes remain amber because DB2 exposes only
  selected bits, and charge override/amount remain amber because the supplied
  Translation sheet has no verified DB2 source. Only the screenshot-verified
  Sweep Fund redefine (type `B`) is live; policies containing another Segment
  53 redefine show the blank unavailable message rather than receiving
  a speculative layout. The other Segment 53 tables are separate CyberDoc
  redefines and are never used as fallback sources for type-B sweep values.
  A consolidated UE142109 probe found one `LH_ATM_TRS_SCH` row, no rows in the
  five unrelated redefine tables, and SQLCODE `-551` for `LH_SWF_SCH`.
  Multiple type-B records are sorted by type/sequence.
  Probe with `tools/policyrecord/probe_segment53.py UE142109 CKPR`; the shipped screen and
  complete Record Layout are built by `tools/policyrecord/build_seg53_screen.py`.
- **Segment 56 live mapping (verified against UE142109).** Screen 6256
  ("Multiple Fund Control") reads the required `LH_GEN_FND_RLE` plan-rule row
  and the optional `LH_MKT_VAL_ADJ_RLE` row. It preserves the captured terminal
  spacing from the supplied UE142109 capture and `Sample 6256 screen.htm`.
  UE142109's live row reproduces `1 00 0 0 .00 999 1 1 07/01/2026 2`,
  `999 999 0 .00 0`, and the final index-loan indicator `1` exactly. This
  policy has no optional MVA row, so the screen keeps its captured blank/zero
  MVA values visible in amber with a specific `LH_MKT_VAL_ADJ_RLE`-missing
  warning rather than presenting them as policy data. Flag bytes also remain
  amber because DB2 does not expose each complete packed byte. The shipped
  reference screen is now the UE142109 capture. Probe with
  `tools/policyrecord/probe_segment56.py UE142109 CKPR`.
- **Segment 59 Type 1 live mapping (verified token-by-token).** Screen 6259
  ("TAMRA") reads one `LH_TAMRA_7_PY_PER` period row and seven
  `LH_TAMRA_7_PY_YR` accumulation rows, ordered by `SVPY_YR_SEQ_NBR`. Its four
  display lines match the real **U0633187** 6259 capture (`img_018.png`) in
  `Policy Segments seg.doc`: the first two accumulation years follow the period
  fields, then years 3-7 and the 1035 counter wrap to the last line. Flag Byte A
  is reconstructed from the six documented indicator columns plus two reserved
  zero bits, while reserved Flag Bytes B/U are amber examples.
  `XCG_1035_PMT_QTY` comes from `LH_TAMRA_7_PY_PER` (correcting a stale workbook
  table reference). The historical screenshot values have since changed in live
  DB2, but both the frozen screenshot fixture and current U0633187 values are
  regression-tested in the same verified positions. CyberDoc's Type 2 search-key
  redefine remains unavailable until a live Type 2 policy is available for
  verification. Probe with `tools/policyrecord/probe_segment59.py`.
- **Segment 66 live mapping (verified token-by-token).** Screen 6266 ("Advanced
  Product") is present only for **non-traditional products (UL/IUL/VUL)** and maps
  almost 1:1 onto a single `LH_NON_TRD_POL` row (~97 live fields). `_build_segment_66`
  reads that row once and streams the body in screen order, with three segment-66
  specifics the generic template can't express: (a) the null/blank/high-date
  sentinel renders `**/**/****` (not seg 01's `00/00/1900`); (b) each amount field
  carries its own `int` vs `dec2`/`dec3` format (the same underlying `0.00` shows as
  `0` for some fields and `.00` for others); and (c) the mainframe **concatenates
  several adjacent bytes into one display token** — e.g. the six full-surrender
  subfields render as `0N15601`, partial-surrender table+charges as `0910`, rule
  triplets as `120`/`300`, loan min-balance table+rule as `002` — modelled as
  consecutive runs with no separator. The six bit-packed **flag bytes** (Flag Byte
  A–E + User Flag Byte) and a handful of tail fields with no DB2 column render as
  amber `example` data. Returns `None` for traditional policies (no such row) →
  the viewer omits the segment if all its mapped tables are empty. The mapping is verified
  token-by-token against the real 6266 screen for U0361148 by
  `tools/policyrecord/probe_segment66.py` (diff the live token stream vs the screenshot); the
  `fields` map (COBOL + DB2 hovers) is regenerated by `tools/policyrecord/update_seg66_fields.py`
  from the "Translation" sheet of `docs/COBOLDB2translation.xls`. A frozen copy of
  the U0361148 record locks the whole mapping in
  `tests/test_policy_record_formatting.py::TestSegment66LiveBuild`.
- **Segment 02 live mapping (verified token-by-token).** Screen 6202
  ("Coverage") **repeats once per coverage phase** — unlike the single-row
  segments (01/58/66), it emits one 5-line block per `LH_COV_PHA` row.
  `_build_segment_02` loops those rows (via `_safe_rows(pi, "LH_COV_PHA")`),
  emitting one top `6202, <policy>` line then a per-coverage block whose fields
  wrap at four fixed screen positions. Its ordered field map is generated by
  `tools/policyrecord/gen_seg02_fields.py` → `data/policy_record_screens/seg_02_coverage_fields.json`
  (101 entries), built from the segment's byte-ordered record layout, cross-checked
  against the "Translation" sheet, and **value-verified token-by-token against the
  real 6202 screen for U0361148** (`docs/Policy Record/Example screen shots_extract/img_002.png`).
  Segment-02 specifics: (a) the base plan's **subseries abuts its base token**
  (`35D` + `MP` → `35DMP`) but stays two separately-hoverable runs; (b)
  **blank-collapse** — a blank char field is skipped (the mainframe collapses it)
  while numeric zeros are shown; a few fields carry `blank_if_zero` (a stored `0`
  that means "not applicable" and shows blank). Five mapping corrections live in
  the generator's `OVERRIDES` (e.g. Orig Spec Amount Units → `OGN_SPC_UNT_QTY`,
  Production Control Data: **Percent** → `PRD_PCT`, Participation Type →
  `DIV_PTP_TYP_CD`). The four bit-packed **flag bytes** (A–D) render amber
  `example`; fields whose value lives in a *different* table (e.g. ANICO Product
  Indicator in `TH_COV_PHA`) are skipped rather than fabricated. Returns `None`
  when the policy has no coverage rows; the viewer omits an absent segment or
  shows the unavailable message if only extension rows exist.
  The `fields` map (COBOL + DB2 hovers) is populated by
  `tools/policyrecord/update_seg02_fields.py`; a frozen two-coverage U0361148 fixture locks the
  whole mapping in
  `tests/test_policy_record_formatting.py::TestSegment02LiveBuild`.
- **Native, not a browser.** The green-screen is rendered with `QLabel` tokens
  in a `_TerminalScreen`; hover styling and per-value tooltips are precise. The
  **Record Layout** reference table below the screen is rendered with a
  `QTextBrowser` (Qt rich text — *not* Chromium/WebEngine) fed the source table's
  HTML, which faithfully reproduces its rowspans/colors with almost no code.
  No `QWebEngineView` is used.
- **One scroll per tab.** Each tab is a `QScrollArea`: green-screen on top,
  Record Layout below — scroll down to read the byte/COBOL/DB2 layout.
- **Readable tooltips.** Tooltips are styled (`_TOOLTIP_QSS`: dark-green card,
  light text, gold border) so they're legible over the terminal. The field name
  and each COBOL/DB2 source mapping stay on **one line** (`<nobr>`) — e.g.
  "Valuation Code: Base" never wraps; only the amber not-real-data warning and
  its explanatory note are allowed to wrap.
- **Footer chrome is normalized for display.** `build_screen` routes every
  live screen through `_normalize_footer`, which shows **today's date** in the
  completion-line `Current Date` token and clears the
  `field` on the user-id / region-company tokens so those carry **no hover
  popup** — they're terminal chrome, not policy data.
- **Data-driven.** Each segment is a JSON file under
  `data/policy_record_screens/seg_<n>.json` with `lines` (rows of
  `{text, field, example?, dim?, note?}` runs — empty for a layout-only screen),
  a `fields` map (`field -> [COBOL:/DB2: ...]`), an ordered `field_specs` list
  (`{name, byte, db2, cobol}`), and a `layout_html` string (the Record Layout
  table). A **`template` screen** (e.g. seg 01) additionally sets `template:
  true` and annotates each `lines` token with its `field`, `db2` source and (for
  chrome) a `role`, so the builder can fill live values into the authentic
  layout. `_SEGMENTS` is derived from the shared record/table mapping, not a
  hand-maintained screen list. Implement a mapped segment by producing its JSON
  and adding a branch to `build_segment_lines` or a `template` screen.
- **Segment 55 live mapping (verified against UL045809 and U0633187).**
  Screen **6255** joins the common `LH_COV_IVM_FND_CTL` header with
  `LH_COV_FXD_FND_CTL` by the full policy/company/system/phase/fund key.
  The common table is not an alternative variable-only table. All four lines
  for UL045809's GP/U1 funds match the supplied capture, including 4.000,
  `ANICO1983`, 6.000 and 12/14/2000. U0633187 additionally verifies IX/LN/SW/U1.

  Non-tiered fixed records are **79 bytes**: 45 common plus 34 fixed.
  The archived HTML's one-byte High Phase is stale; it occupies **60-61**,
  followed by the rate search key 62-72, initial rate 73-75 and end date 76-79.
  Three-decimal rates are displayed as stored (4.000 is not .040).
  Numeric NULL slots retain CyberLife's zero-shaped display but are dim and
  explicitly annotated; NULL flags/codes remain unknown. All eight Flag A bits
  have verified DB2 sources; reserved B/U bytes remain amber examples.

  Variable-fund and tiered amount/duration variants remain **explicitly
  unavailable pending live verification**, not rendered as ordinary fixed
  records. `LH_AMT_TIERED_ITS`/`LH_DUR_TIERED_ITS`, the subtype and tier counter
  are checked so extensions cannot be silently dropped. Any DB error,
  duplicate/orphan key or missing fixed extension produces a visible live-data
  error with no captured values. A genuinely absent segment is omitted.
  Sources: CyberDoc D202 printed pp.63-77/600, translation workbook, live DB2.
  Metadata generator: `tools\policyrecord\build_seg55_screen.py`.
  Regression: `tests/test_policy_record_segment55.py`.
  Read-only check:
  `tools\policyrecord\probe_segment55.py --expect-ul045809 --output <json-path>`.
  Native capture:
  `tools\policyrecord\preview_policy_record.py UL045809 CKPR 55 <directory>`.
- **Segment 57 live mapping (verified against UL045809 and U0633187).**
  Screen **6257** reads every `LH_FND_TRS_ALC_SET` and its `LH_FND_ALC`
  entries through `PolicyInformation`, not just the most recent payment set.
  Join on transaction/allocation type and **`FND_ALC_SEQ_NBR`**; sort entries
  by **`SEG_IDX_NBR`**. Live multi-entry C/P/V sets confirm that the workbook
  has these two entry-column descriptions swapped. Duplicate/orphan keys,
  missing indexes, missing columns and DB errors block live rendering.

  The fixed header is **30 bytes**, plus **16 per allocation** (maximum 99).
  The archived HTML is one byte too long from the allocation count onward:
  count is 29-30, first entry 31-46, and value 40-46. Dollar (40-45) and
  percent (40-42) values redefine the units area; use `FND_ALC_AMT` (2 decimals),
  `FND_ALC_PCT` (2) or `FND_ALC_UNT_QTY` (4) according to `ALC_VAL_TYP_CD`.
  Never replace a missing amount with zero or round an invalid source value.
  Charge-deduction (`C`) dates use `CRG_DED_ALC_EFF_DT`; other types use
  `LST_ALC_CHG_DT`. NULLs and DB2 character low-values are explicitly annotated.

  Flag A bits 0-2 are live (`ALC_SRC_CD`, `AUTOCLOS_PROC_IND`,
  `MTHLVRSY_PROC_IND`). Bit 2 = 1 means monthliversary processing has **not**
  occurred since addition. Reserved bits, unmapped group-control bit 7 and
  the user byte remain amber examples, not reconstructed facts.
  UL045809 matches the supplied line exactly; U0633187 verifies C/P/V sets,
  fund-order entries, sweep-from, direction and exclusion fields.
  Sources: CyberDoc D202 printed pp.90-96/602, translation workbook, live DB2.
  Metadata generator: `tools\policyrecord\build_seg57_screen.py`.
  Regression: `tests/test_policy_record_segment57.py`.
  Read-only check:
  `tools\policyrecord\probe_segment57.py --expect-ul045809 --output <json-path>`.
  Native capture:
  `tools\policyrecord\preview_policy_record.py UL045809 CKPR 57 <directory>`.
- **Segment 60 live mapping (verified against UL045809).** Screen **6260**
  ("Payment Accumulation") reads one `LH_POL_TOTALS` row and checks
  `LH_MO_ADD_PMT` through `PolicyInformation`. All three body rows match the
  supplied 2026-09-15 capture, including regular premiums 46726.00, additional
  premiums 1365.25, withdrawals 13987.30 and cost basis 34103.95. The fixed
  length is **139 bytes**. The old HTML mislabeled its last `.00` and `0`:
  they are **LTC Cost of Insurance Since Issue** and **Used Accumulators**.
  The current CyberDoc D202 pp.120-126/606 puts LTC at bytes112-117
  (`TOT_LTC_CST_OF_INS`, verified live), reserved bytes118-138, the counter at
  byte139 and optional monthly amounts at bytes140-211.

  DB2 NULL numeric slots display `.00`, matching this CyberLife capture, but
  remain dim with an explicit NULL tooltip; stored zero is not dim. Dates use
  the `**/**/****` sentinel. Both reserved flag bytes remain amber examples,
  since DB2 does not expose their complete contents. Missing columns/table
  errors are explicit failures, never silently filled from the reference.
  The zero-counter/no-monthly-row case is verified; nonzero or inconsistent
  monthly extensions are blocked until the counter/array correspondence is
  verified, rather than inventing twelve amounts.
  Regression: `tests/test_policy_record_segment60.py`; read-only live check:
  `tools\policyrecord\probe_segment60.py --expect-ul045809 --output <json-path>`.
  Regenerate the corrected schema/reference with
  `tools\policyrecord\build_seg60_screen.py`.

- **Segment 61 is user-reserved, not a standard totals segment.** CyberDoc
  D20 printed p.2/PDF p.20 lists 61 among the user-reserved segments. The
  supplied translation workbook contains no segment61 mappings, and the
  supplied first capture is explicitly **6260 / 60**, not 61. No speculative
  61 tab or DB2 mapping is created; a company-specific layout/live capture
  is required to implement an actual custom 61.

- **Segments 63/64 live mapping (verified against UL045809).** Screen **6263**
  reads every `LH_POL_YR_TOT` row in numeric `POL_YR_DUR` order, retaining the
  prior-years bucket **0**. Screen **6264** reads every `LH_POL_CAL_YR_TOT` row
  in `CAL_YR_END_DT` order. UL045809 has nine rows in each: policy years 0 and
  35-42; calendar years 2018-2026. All **36 wrapped data lines** match the
  supplied 2026-09-15 captures, including negative yearly values and the
  2024 withdrawal of 2450.00. These are stored historical totals, not values
  recalculated from current policy data.

  Lengths are **108** and **74** bytes. CyberDoc D202 pp.129-138/608-609
  corrects archive offsets: segment63's final percentage occupies bytes106-108,
  and segment64's last two amounts occupy bytes63-68 and69-74.
  The life-expectancy factor retains **one** decimal place (`.0`), while
  monetary fields use two. NULL slots preserve the captured display format
  but are dim and explicitly labeled NULL; stored zero remains distinct.
  Both builders reuse the terminal wrapper with 81 total columns (79 after
  the two-space inset), preserving the captured year0/year40 line breaks.

  Verified Flag A bits come from `REVS_PRC_GEN_IND` for 63 and
  `YR_END_ACT_BAL_IND`, `RMD_NOT_IND`, `RMD_REMINDER_IND`, `RMD_CLC_IND`,
  `RMD_DEFERRED_IND` for 64. The actual-balance bit is read from DB2, never
  inferred from today's date. Unknown/reserved/user bits remain amber
  examples, not claimed as live data. Missing columns, invalid precision,
  invalid/duplicate year keys and DB2 errors block partial live output.

  Regression: `tests/test_policy_record_annual_totals.py`. Read-only live
  comparison: `tools\policyrecord\probe_annual_totals.py --reference
  tools\policyrecord\annual_totals_capture.json --output <json-path>`.
  Native captures: `tools\policyrecord\preview_policy_record.py UL045809
  CKPR 63 <output-dir>` (use 64 for the calendar-year view).
  After extracting the source HTML, apply the verified metadata using
  `tools\policyrecord\build_annual_totals_metadata.py`. This updates both hovers
  and the Record Layout sources, including the archive's missing
  `POL_YR_MVA_CSV_AMT` mapping.

- **Segment 67 live mapping (verified against UL045809).** Screen **6267**
  ("Renewal Rates") reads `LH_COV_INS_RNL_PER` headers and combines
  `LH_COV_INS_RNL_RT`, `LH_BNF_INS_RNL_RT`, `LH_SST_XTR_RNL_RT`,
  `LH_COV_INS_GDL_PRM` and `LH_BNF_INS_GDL_PRM` through `PolicyInformation`.
  Group by phase/person/person-sequence, then sort the combined entries by
  `SEG_IDX_NBR`, **not rate type**. `TH_COV_INS_RNL_RT` is extension metadata,
  not another set of entries. Length is **22 + 11 x entry count**, including
  guideline A/S entries. CyberDoc D202 printed pp.193-202 and 612 document the
  fixed header and entry redefines; the translation workbook plus live DB2
  confirm the physical columns.

  Ordinary `RNL_RT` is already an integer containing the nine packed digits:
  **do not multiply it by a rate divisor**. Guideline A/S uses
  `GDL_PRM_AMT` in cents (eleven digits); guideline adjustment types 1/2 use
  `GDL_PRM_UNT_QTY` with three decimals. Packed `C` means positive/zero and `D`
  negative. Keep zero distinct from DB2 NULL: an unavailable amount is shown
  as question marks with a NULL tooltip, never fabricated as zero.
  System-calculated guideline keys are blank; coverage `*`/`J` markers are
  reconstructed, not printed as raw numeric indicator flags.

  UL045809's three body rows match the supplied 2026-09-15 CyberLife capture:
  `67 0110`, eight entries, COI digits `000337971C` / `000282184C`, four
  `000006430C` rates, A `00000000000C` and S **`00002194914D`**.
  Single-space fields, padded plan keys and 80-column wrapping retain that
  layout, including entries split between lines without splitting rate keys.
  U0633187 also verifies two phases and interleaved extra/benefit entries;
  its current NULL benefit rate is explicitly unavailable, not the older
  captured zero. Table errors, missing columns, duplicate/orphan entries and
  index gaps block a partial live screen and surface a **LIVE DATA ERROR**
  badge above the empty unavailable screen.

  Percentage extras use five decimals. Nonzero dollar extras remain explicitly
  unsupported until their phase-specific fixed/flexible premium basis and DB2
  storage interpretation are verified (CyberDoc requires two versus five
  decimals). Zero extras are safe at either scale. Benefit guideline NULL or
  low-value keys without a verified system-calculation indicator are also
  blocked, not silently converted to blank keys.

  Regression: `tests/test_policy_record_segment67.py`. Read-only live check:
  `venv\Scripts\python.exe tools\policyrecord\probe_segment67.py
  --expect-ul045809 --output <json-path>`. Native capture:
  `tools\policyrecord\preview_policy_record.py UL045809 CKPR 67 <output-dir>`.
  The shipped `seg_67.json` retains the historical reference/Record Layout and
  enriched live field hovers; it is not used as a live-value template.
- **Status:** Segments **01**, **02**, **53 Sweep Fund**, **55 fixed funds**,
  **56**, **57**, **58**,
  **59 Type 1**, **60**, **63**, **64**, **66**, and **67** are **live**.
  Other Segment 53 redefines and
  Segment 59 Type 2 remain blank/unavailable until verified. Mapped, populated
  segments already get tabs even before their builders/screens are implemented.
- **Extraction:** the sample HTML screens under `docs/Policy Record/` are
  converted to JSON with `tools/policyrecord/extract_policy_record_screen.py`. It classifies
  each `<table>` by **content** (terminal vs record-layout) — so it handles files
  with both tables (6258) or only the layout table (6201) — reproduces browser
  whitespace handling, pulls field→COBOL/DB2 mappings, emits the ordered
  `field_specs`, and keeps the raw Record Layout table. Verify rendering with
  `tools/policyrecord/preview_policy_record.py '{"policy": "U0633187"}'` (writes screen /
  tooltip / layout PNGs and a `policy_record_state.json` manifest; supports `tab`
  and `tooltip_field` selectors; empty policy renders the no-policy state).
  The helper also accepts `@config.json` with `expect_absent` and
  `expect_unavailable` segment lists and `copy_field` to exercise the real native
  Copy menu on the selected tab. A missing requested tab is an error, not a
  screenshot of a different tab. Clipboard contents are restored after verification.
- **Packed `MMDDYY` "activity" dates (CyberDoc-driven).** Most policy dates show
  slashed `MM/DD/YYYY`, but a handful of activity dates are stored on the
  mainframe as a **packed integer** and shown *unslashed* — e.g. Accounting Date
  `07/10/2026` → `71026` (month has no leading zero; day + 2-digit year are
  zero-padded). The four such seg-01 fields are Accounting Date (`FBRPAYDT`), Last
  Financial Date (`FBRFINDT`), Other Date (`FBRCHGDT`) and Billing Date
  (`FBRBILDT`). Which fields pack is decided **authoritatively from the CyberDoc**,
  not guessed: `_field_kind_map` joins each `field_spec`'s `cobol` name to
  `data/policy_record_screens/cyberdoc_field_formats.json` to get a display
  `kind`; a date value whose kind is `date_packed`/`packed_num`/`int` renders via
  `_packed_mmddyy`, everything else stays slashed. (Billing Date is documented as
  a bare "4 bytes packed" number, so the "date value + single-packed field ⇒
  packed MMDDYY" rule is what catches it.) Covered by
  `tests/test_policy_record_formatting.py`.
- **CyberDoc / DB2-COBOL mapping toolkit (build-out aid).** The official
  CyberLife docs (`docs/CyberDoc/*.pdf`) are the source of truth for every policy
  record field's format + COBOL name + redefines. Workflow to map any field:
  1. **DB2 column → COBOL name** — `docs/COBOLDB2translation.xls` ("Translation"
     sheet: `SEG #`, `COBOL Name`, `Table`, `Field Name`). Query it with
     `tools/office/read_xls.py '{"path":"docs/COBOLDB2translation.xls","sheet":"Translation","find":"LST_ACT_TRS_DT"}'`.
  2. **COBOL name → format** — the CyberDoc PDFs, extracted to searchable text by
     `tools/office/extract_pdf_text.py` (→ `docs/CyberDoc/text/*.txt`; `D20.txt` is the
     Policy Record doc). `tools/policyrecord/build_cyberdoc_index.py` distils every field's
     `Format:` line into `cyberdoc_field_formats.json` (COBOL → `{name, format,
     kind}`), which the builder loads at runtime. Regenerate after re-extracting.
  3. `seg_<n>.json` `field_specs` already carry the `cobol` name, so the builder
     needs only the CyberDoc index (step 2) at runtime; the xls (step 1) is for
     mapping *new* fields whose COBOL name isn't yet recorded.
- **Note (Segment 01 fidelity).** The live 6201 screen is matched against a real
  terminal capture (UL040023): header `6201, UL040023`, the `01 0292 1 1 1 0`
  control row, amber flag bytes, all slashed dates, and the packed activity dates
  (`71026 71026 110520 … 101325`) all match. Fields with **no** DB2 source (flag
  bytes, Other Kind, Extract Date, etc.) show clearly-labelled amber *example*
  data — their exact value is illustrative, not the live policy's. All displayed
  **data** is the policy's real DB2 value; only no-DB2 example fields are
  synthetic.

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
as `frmAudit.frm` (6,744 lines).

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
3. **Policy Tab** — Basic policy details, billing info, agents, and the traditional-product monthly policy fee from `LH_FXD_PRM_POL.POL_FEE_AMT`
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
