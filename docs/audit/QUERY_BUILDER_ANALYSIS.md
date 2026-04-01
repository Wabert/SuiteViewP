# Audit Query Builder — VBA Analysis & Implementation Proposal

## 1. VBA Code Structure Overview

The VBA query builder in `frmAudit.frm` (3,061 lines) is a single monolithic form that handles UI population, user interaction, and SQL generation all in one place. The query-building logic is split across four main functions:

| VBA Function | Lines | Purpose |
|---|---|---|
| `BuildSQLString()` | ~1,320 lines (L1871–L3191) | Main audit query — builds the full SELECT/FROM/JOIN/WHERE |
| `BuildWithClause()` | ~570 lines (L1240–L1866) | Builds all WITH (CTE) sub-queries |
| `BuildRiderTable()` | ~240 lines (L1000–L1238) | Builds INNER JOIN clauses for up to 3 rider searches |
| `BuildSQLStringToFindBase()` | ~30 lines | Utility: find base plancodes for a given rider |
| `BuildSQLStringToFindRiders()` | ~30 lines | Utility: find riders attached to a given base |
| `BuildSQLStringToFindValues()` | ~10 lines | Utility: count distinct values for a table/field |

### How It Works

The VBA code builds a SQL string via string concatenation, conditionally adding clauses based on which UI controls have values. The overall pattern is:

```
1. Build WITH clause (CTEs)           ← BuildWithClause()
2. Build SELECT columns               ← BuildSQLString() first section
3. Build FROM + JOINs                  ← BuildSQLString() middle section + BuildRiderTable()
4. Build WHERE conditions              ← BuildSQLString() final section
5. Add FETCH FIRST N ROWS ONLY
6. Replace "DB2TAB" with region schema ← SQLStringForRegion()
```

---

## 2. Database Tables Referenced

The query touches **~30 DB2 tables** (referred to by Cyberlife "segment" numbers):

### Core Tables (always or nearly always joined)

| Alias | DB2 Table | Segment | Purpose |
|---|---|---|---|
| POLICY1 | LH_BAS_POL | 01 | Base policy record — the anchor table |
| COVERAGE1 | LH_COV_PHA (CTE, COV_PHA_NBR=1) | 02 | Base coverage (always via CTE) |
| USERDEF_52G | TH_USER_GENERIC | 52-G | User-defined fields (Partner, exchange, shortpay) |
| UPDF | TH_USER_PDF | 52-1 | Plan Definition File (conversion data) |
| TAMRA | LH_TAMRA_7_PY_PER | 59 | TAMRA/7-pay test data |
| POLICY_TOTALS | LH_POL_TOTALS | 60 | Accumulated policy totals |
| LH_POL_YR_TOT | LH_POL_YR_TOT (two CTEs) | 63 | Year-to-date totals |

### Conditionally Joined Tables

| Alias | DB2 Table | Segment | Triggered By |
|---|---|---|---|
| COVSALL | LH_COV_PHA | 02 | Multiple plancodes, all-coverage search |
| MODCOV1 / MODCOVSALL | TH_COV_PHA | 02-mod | Product indicator, GIO, COLA |
| RIDER1/2/3 | LH_COV_PHA (COV_PHA_NBR > 1) | 02 | Rider search criteria |
| RIDER*COVMOD | TH_COV_PHA | 02-mod | Rider product indicator/COLA/GIO |
| TABLE_RATING1 | LH_SST_XTR_CRG (type 0/1/3) | 03 | Table rating filter or display |
| FLAT_EXTRA1 | LH_SST_XTR_CRG (type 2/4) | 03 | Flat extra filter or display |
| COV1_RENEWALS | LH_COV_INS_RNL_RT | 67 | Rateclass / sex code |
| RIDER*_RENEWALS | LH_COV_INS_RNL_RT | 67 | Rider rateclass / sex code |
| BEN1/2/3 | LH_SPM_BNF | — | Benefit search |
| NONTRAD | LH_NON_TRD_POL | 66 | UL/Advanced product fields |
| NEWBUS | LH_NEW_BUS_POL | 00 | New business / pending policies |
| BILL_CONTROL | LH_BIL_FRM_CTL | 33 | Billing control number |
| SLR_BILL_CONTROL | LH_LN_RPY_TRM | 20 | SLR billing form |
| REINSTATEMENT | LH_COV_SKIPPED_PER | 09 | Skipped coverage reinstatement |
| USERDEF_52R | TH_USER_REPLACEMENT | 52-R | Replacement policy data |
| FFC | LH_COV_FXD_FND_CTL | 55 | CIRF key |
| FIXPREM | LH_FXD_PRM_POL | — | Premium calc rules |
| POLICY1_MOD | TH_BAS_POL | 01-mod | Overloan indicator |
| TR1 | FH_FIXED | 69 | Transaction history search |
| COMMTARGET | LH_COM_TARGET | 58 | Commission target premium |
| MTP / ACCUMMTP | LH_POL_TARGET | 58 | Monthly/Accumulated MTP |
| ACCUMGLP | LH_POL_TARGET | 58 | Accumulated GLP |
| SHORTPAY_PRM | LH_POL_TARGET | 58 | Short-pay premium |
| SHADOWAV | LH_COV_TARGET | 58 | Shadow account value |
| NSPTARGET | LH_POL_TARGET | 58 | NSP target |

### CTE-Only Tables

| CTE Name | Source Tables | Purpose |
|---|---|---|
| COVERAGE1 | LH_COV_PHA | Base coverage filter |
| ALL_BASE_COVS / COVSUMMARY | LH_COV_PHA self-join | Summed specified amt across all matching covs |
| ISWL_INTERPOLATED_GCV | COVSUMMARY + INTERPOLATION_MONTHS | GCV interpolation for ISWL |
| INTERPOLATION_MONTHS | LH_BAS_POL | Months to/from anniversary |
| BILLMODE_POOL | LH_BAS_POL | Billing mode translation |
| GRACE_TABLE | LH_NON_TRD_POL UNION LH_TRD_POL | Grace period data |
| ALL_LOANS / POLICYDEBT | LH_FND_VAL_LOAN UNION LH_CSH_VAL_LOAN | Combined loan data |
| LASTMV / MVVAL | LH_POL_MVRY_VAL + LH_NON_TRD_POL + LH_POL_TOTALS | Last monthliversary values |
| GLP / GSP | LH_COV_INS_GDL_PRM | Guideline level/single premium |
| TRAD_CV | COVERAGE1 + INTERPOLATION_MONTHS | Traditional cash value interpolation |
| ALLOCATION_FUNDS | LH_FND_ALC | IUL fund allocation filter |
| FUND_VALUES | LH_POL_FND_VAL_TOT | Fund value amounts |
| CHANGE_SEGMENT | LH_COV_TMN UNION LH_NT_COV_CHG UNION others | 68-segment change codes |
| CHANGE_TYPE9 | LH_COV_TMN + LH_NT_COV_CHG | RPU original amount |
| PRE_TERMINATION_DATES / TERMINATION_DATES | FH_FIXED | Termination date from history |
| LH_POL_YR_TOT_withMaxDuration / at_MaxDuration | LH_POL_YR_TOT | Year totals at max duration |

---

## 3. Categorization of Query Logic

The ~200 UI controls that influence the query can be grouped into these functional categories:

### A. Filter Criteria (WHERE / JOIN conditions)
Controls that **restrict** which policies are returned:
- **Policy-level**: system code, company, market org, state, status code, suspense code, policy number, billing form, loan type, NFO, primary div option, reinsurance code, non-trad indicator, last/orig entry code, bill mode, MEC, 1035, MDO, RGA
- **Coverage-level**: plancode(s), form number, product line code, product indicator, sex code, rateclass, issue age range, issue date range, current age, current policy year, valuation class/base/subseries, mortality table, initial term period, cash value rate
- **Rider-specific** (×3): plancode, person code, sex code, product line/indicator, rateclass, post-issue, date ranges, change type, COLA/GIO, lives covered, additional plancode criteria, table rating, flat extra
- **Benefit-specific** (×3): benefit type, subtype, post-issue, cease date range, cease date status
- **Transaction**: transaction type, entry/effective date range, gross amount range, origin, fund ID list, day/month matching
- **Financial**: account value range, specified amount range, shadow AV range, loan principle/accrued range, 7-pay premium/AV range, accumulated withdrawal range, billing premium range, premium YTD, additional premium, total premium, GLP negative, UL in corridor, accum value > prem paid, GCV vs CV comparisons
- **Dates**: paid-to-date range, GPE date range, app date range, termination date range, last financial date, last change date, bill commence date
- **Computed**: attained age, current policy year (calculated from issue date)

### B. Display/Show Columns (SELECT)
Controls that add columns to the output without filtering:
- ~40 "Show" checkboxes on the Display tab
- Plus inline show flags like `CheckBox_ShowCurrentDuration`, `CheckBox_ShowCurrentAttainedAge`, etc.

### C. JOIN Type Selection (INNER vs LEFT OUTER)
A key VBA pattern: when a control is used for **filtering**, the table uses `INNER JOIN`; when it's only for **display**, it uses `LEFT OUTER JOIN`. Examples:
- `TABLE_RATING1`: INNER JOIN if filtering on table rating, LEFT OUTER if just showing substandard info
- `NONTRAD`: INNER JOIN if filtering on DB option, LEFT OUTER if just showing definition of life insurance
- `POLICYDEBT`: INNER JOIN if requiring loan existence, LEFT OUTER if just showing debt amounts

---

## 4. Problems With the VBA Approach

1. **Monolithic**: 1,300+ lines in `BuildSQLString` checking ~200 individual controls
2. **Repetitive**: Rider 1/2/3 logic is copy-pasted 3 times with alias changes
3. **Fragile**: Adding a new field means editing 3-4 different locations (CTE, SELECT, FROM, WHERE)
4. **Not testable**: SQL is built as an opaque string, impossible to unit-test individual clauses
5. **Schema hardcoded**: Uses `DB2TAB` placeholder, replaced at the end by `SQLStringForRegion()`
6. **No parameterization**: All values are string-interpolated into SQL (though in this case the values come from dropdowns, not free text, so the risk is limited to internal use)

---

## 5. Proposed Python Architecture

### 5.1 Core Design: `AuditQueryBuilder` Class

A single builder class that collects criteria from the UI and produces a finished SQL string. Internally it delegates to focused helper methods.

```
suiteview/audit/
├── query/
│   ├── __init__.py
│   ├── builder.py          # AuditQueryBuilder — orchestrator
│   ├── ctes.py             # CTE definitions (WITH clause builders)
│   ├── columns.py          # SELECT column definitions
│   ├── joins.py            # JOIN clause builders
│   ├── filters.py          # WHERE clause builders
│   ├── riders.py           # Rider 1/2/3 JOIN logic (parameterised)
│   └── constants.py        # Table names, state map, field mappings
```

### 5.2 Data Flow

```
UI Tabs ──collect_criteria()──→ AuditCriteria (dataclass)
                                       │
                                       ▼
                              AuditQueryBuilder
                                ├── _build_ctes()      → WITH clause
                                ├── _build_select()    → SELECT clause
                                ├── _build_from()      → FROM + JOINs
                                ├── _build_where()     → WHERE clause
                                └── _build_limit()     → FETCH FIRST
                                       │
                                       ▼
                                 Final SQL string
```

### 5.3 Key Components

#### `AuditCriteria` — A flat dataclass capturing all form values

```python
@dataclass
class AuditCriteria:
    # Global
    schema: str = ""
    system_code: str = ""
    max_count: int | None = 25

    # Policy-level filters
    company_code: str = ""
    market_org: str = ""
    branch_number: str = ""
    policy_number: str = ""
    policy_number_criteria: str = ""   # starts_with, ends_with, contains

    # Coverage 1 filters
    plancode: str = ""
    plancodes: list[str] = field(default_factory=list)
    form_number: str = ""
    issue_age_lo: str = ""
    issue_age_hi: str = ""
    issued_after: str = ""
    issued_before: str = ""
    # ... (all other filter fields)

    # Rider criteria (list of RiderCriteria, up to 3)
    riders: list[RiderCriteria] = field(default_factory=list)

    # Benefit criteria (list of BenefitCriteria, up to 3)
    benefits: list[BenefitCriteria] = field(default_factory=list)

    # Transaction criteria
    transaction: TransactionCriteria | None = None

    # Display flags (which columns to show)
    show: DisplayFlags = field(default_factory=DisplayFlags)
```

#### `AuditQueryBuilder.build()` — The orchestrator

```python
class AuditQueryBuilder:
    def __init__(self, criteria: AuditCriteria):
        self.c = criteria
        self.schema = criteria.schema

    def build(self) -> str:
        ctes = self._build_ctes()
        select = self._build_select()
        from_clause = self._build_from()
        where = self._build_where()
        limit = self._build_limit()

        parts = []
        if ctes:
            parts.append("WITH " + ",\n".join(ctes))
        parts.append(select)
        parts.append(from_clause)
        parts.append(where)
        if limit:
            parts.append(limit)
        return "\n".join(parts)
```

#### Rider logic — Parameterised instead of copy-pasted

Instead of 3 copies of rider-building code, use a single function called with index:

```python
def build_rider_join(criteria: RiderCriteria, index: int, schema: str) -> str:
    alias = f"RIDER{index}"
    parts = []
    parts.append(f"INNER JOIN {schema}.LH_COV_PHA {alias}")
    parts.append(f"  ON POLICY1.CK_SYS_CD = {alias}.CK_SYS_CD")
    parts.append(f"  AND POLICY1.CK_CMP_CD = {alias}.CK_CMP_CD")
    parts.append(f"  AND POLICY1.TCH_POL_ID = {alias}.TCH_POL_ID")
    parts.append(f"  AND {alias}.COV_PHA_NBR > 1")

    if criteria.plancode:
        parts.append(f"  AND {alias}.PLN_DES_SER_CD = '{criteria.plancode}'")
    # ... etc for each rider field
    return "\n".join(parts)
```

#### CTE Management — Declare-on-demand

CTEs are only added when needed. A registry tracks which CTEs have been requested:

```python
class CTERegistry:
    """Tracks which CTEs are needed and builds them on demand."""

    def __init__(self, schema: str, criteria: AuditCriteria):
        self._schema = schema
        self._criteria = criteria
        self._ctes: dict[str, str] = {}  # name → SQL

    def require(self, name: str):
        """Mark a CTE as needed. Build it if not already built."""
        if name not in self._ctes:
            builder = getattr(self, f"_build_{name.lower()}", None)
            if builder:
                builder()

    def get_all(self) -> list[str]:
        """Return all CTE definitions in dependency order."""
        return list(self._ctes.values())
```

#### JOIN Type Intelligence

The VBA pattern of INNER vs LEFT OUTER JOIN is preserved by checking intent:

```python
def _join_type(self, filter_active: bool) -> str:
    """INNER JOIN when filtering, LEFT OUTER JOIN when just displaying."""
    return "INNER JOIN" if filter_active else "LEFT OUTER JOIN"
```

### 5.4 Collecting Criteria from the UI

Each tab provides a `collect()` method that returns its portion of the criteria:

```python
# In audit_window.py
def _collect_criteria(self) -> AuditCriteria:
    c = AuditCriteria()
    c.schema = REGION_SCHEMA_MAP.get(self.cmb_region.currentText(), DEFAULT_SCHEMA)
    c.system_code = self.cmb_system.currentText().strip()
    c.max_count = int(self.txt_max_count.text()) if self.txt_max_count.text().isdigit() else None

    self.policy_tab.collect(c)
    self.policy2_tab.collect(c)
    self.coverages_tab.collect(c)
    self.adv_tab.collect(c)
    self.wl_tab.collect(c)
    self.di_tab.collect(c)
    self.benefits_tab.collect(c)
    self.transaction_tab.collect(c)
    self.display_tab.collect(c)
    return c
```

### 5.5 Implementation Order

Given the complexity, I recommend building the query builder incrementally:

**Phase 1 — Core skeleton + Policy tab filters**
- `AuditCriteria` dataclass with policy-level fields
- `AuditQueryBuilder` with COVERAGE1 CTE, basic SELECT, FROM POLICY1, JOIN COVERAGE1
- WHERE clause: system code, company, market org, plancode, state, status, issue date/age
- `FETCH FIRST N ROWS ONLY`
- Wire `Run Audit` button to use the new builder

**Phase 2 — Display columns + simple joins**
- All "Show" checkboxes → SELECT column additions
- LEFT OUTER JOINs for display-only tables (TAMRA, POLICY_TOTALS, LH_POL_YR_TOT, USERDEF_52G, UPDF)
- State code CASE expression

**Phase 3 — Coverage/Rider tab filters**
- Coverages tab: rateclass, sex code, table rating, flat extra, valuation fields
- Rider logic: parameterised `build_rider_join()` for 1-3 riders
- Product line/indicator, multiple plancodes

**Phase 4 — Advanced CTEs**
- Billing mode (BILLMODE_POOL)
- Loan tables (ALL_LOANS, POLICYDEBT)
- UL values (LASTMV, MVVAL)
- Coverage summary (ALL_BASE_COVS, COVSUMMARY)
- Grace table, GLP, GSP, TRAD_CV, Interpolation

**Phase 5 — Benefits, Transactions, remaining filters**
- Benefits 1-3 JOINs
- Transaction (FH_FIXED) JOINs
- Financial filters (AV ranges, shadow AV, corridor check, etc.)
- Termination dates, change segment

**Phase 6 — Utility queries**
- `BuildSQLStringToFindBase` → Find base for a rider plancode
- `BuildSQLStringToFindRiders` → Find riders on a base plancode
- `BuildSQLStringToFindValues` → Distinct value search

---

## 6. Summary of Key Design Decisions

| VBA Pattern | Python Approach | Rationale |
|---|---|---|
| String concatenation in one function | Builder class with delegated methods | Maintainability, testability |
| Copy-paste for Rider 1/2/3 | Parameterised loop over rider criteria | DRY principle |
| `If CheckBox Then AddSQL` scattered everywhere | Criteria dataclass → builder reads it | Separation of UI/logic |
| `DB2TAB` replaced at end | Schema passed into builder upfront | Cleaner, no string replacement |
| `AddListBoxEntriesToSQL` helper | `add_in_clause(field, values)` helper | Same concept, Pythonic |
| INNER vs LEFT OUTER per checkbox | `_join_type(filter_active)` helper | Pattern preserved, explicit |
| No unit tests possible | Builder can be tested with mock criteria | Quality assurance |
