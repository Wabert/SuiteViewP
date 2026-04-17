# IllustrationPolicyData — Class Specification

**Module:** `suiteview.illustration.models.policy_data`  
**Version:** 1.0 (Milestone 1)  
**Date:** 2026-04-12  

---

## 1. Purpose

`IllustrationPolicyData` is the primary input to the UL illustration engine. It is a **mutable Python dataclass** that can be:

1. **Loaded from DB2** via `build_illustration_data(policy_number)` — populates all fields from CyberLife policy records
2. **Modified by the caller** — override any field for what-if analysis (premium, face, crediting rate, etc.)
3. **Passed to `IllustrationEngine.project()`** — produces month-by-month projection results

### 1.1 API Usage

```python
from suiteview.illustration import build_illustration_data, IllustrationEngine

# Load from DB2
policy = build_illustration_data("UE000576")

# Override for what-if scenarios
policy.modal_premium = 200.00             # higher premium
policy.current_interest_rate = 0.045      # different crediting rate
policy.segments[0].face_amount = 75_000   # reduced face

# Project
engine = IllustrationEngine()
results = engine.project(policy, months=12)   # → List[MonthlyState]
```

### 1.2 Design Principles

- **Mutable by design** — callers modify fields after loading. No frozen dataclass.
- **Defaults for everything** — gracefully handles missing DB2 fields. Every field has a sensible default.
- **Pure data** — no methods with business logic. Logic lives in `core/` modules.
- **Serializable** — all fields are standard Python types (str, int, float, date, list). No ORM objects.
- **Single source of truth** — all policy inputs consumed by the engine come from this object. No side-channel data.

---

## 2. Class Definitions

### 2.1 `CoverageSegment`

Represents one base coverage segment on the policy. A policy always has at least one segment (the original base coverage). Increase segments are additional base coverages with their own demographics and rate parameters.

```python
@dataclass
class CoverageSegment:
    """A single base coverage segment."""
    
    # Identity
    coverage_phase: int = 1           # 1 = original base, 2+ = increase segments
    is_base: bool = True              # Always True for base coverages (False reserved for future rider coverages)
    
    # Demographics (per-segment — may differ from policy-level)
    issue_date: Optional[date] = None
    issue_age: int = 0
    rate_sex: str = ""                # "M", "F", "U" — from LH_COV_INS_RNL_RT.RT_SEX_CD (rate sex, not admin sex)
    rate_class: str = ""              # "N", "S", "P", "Q", "R", "T"
    
    # Face / Units
    face_amount: float = 0.0          # Current specified amount
    original_face_amount: float = 0.0 # Original specified amount at issue
    units: float = 0.0                # face_amount / 1000
    vpu: float = 1000.0               # Value per unit (always 1000 for UL)
    
    # Band
    band: int = 1                     # Rate band (1-5) based on face amount
    original_band: int = 1            # Band at issue (for band-locked products)
    
    # Substandard
    table_rating: int = 0             # 0 = standard, 1-16 = table A-P
    flat_extra: float = 0.0           # Per $1000 annual flat extra
    flat_cease_date: Optional[date] = None
    
    # Coverage status
    status: str = "A"                 # "A" = active, "T" = terminated
    maturity_date: Optional[date] = None
    months_since_terminated: int = 0  # For SCR on terminated segments
    
    # COI
    coi_renewal_rate: Optional[float] = None  # Current COI rate from DB2 (for reference/validation)
```

**DB2 Source Mapping:**

| Field | DB2 Table | DB2 Column | Notes |
|---|---|---|---|
| `coverage_phase` | LH_COV_PHA | COV_PHA_NBR | Sequential: 1, 2, 3, ... |
| `issue_date` | LH_COV_PHA | ISSUE_DT | Per-coverage issue date |
| `issue_age` | LH_COV_PHA | INS_ISS_AGE | Age at coverage issue |
| `rate_sex` | LH_COV_INS_RNL_RT | RT_SEX_CD | Rate sex: 1→M, 2→F (via `pi.renewal_cov_sex_code()`) |
| `rate_class` | LH_COV_INS_RNL_RT | RT_CLS_CD | From segment 67 (renewal rate record) |
| `face_amount` | LH_COV_PHA | COV_UNT_QTY × COV_VPU_AMT | Current coverage amount |
| `original_face_amount` | LH_COV_PHA | OGN_SPC_UNT_QTY × COV_VPU_AMT | Original at issue |
| `units` | LH_COV_PHA | COV_UNT_QTY | Coverage units |
| `band` | Derived | `Rates.get_band(plancode, face)` | Based on BANDSPECS table |
| `table_rating` | LH_SST_XTR_CRG | Numeric A=1..P=16 | Type "T" substandard records |
| `flat_extra` | LH_SST_XTR_CRG | Per $1000/year | Type "F" substandard records |
| `flat_cease_date` | LH_SST_XTR_CRG | SST_XTR_CEA_DT | When flat extra expires |
| `status` | LH_COV_PHA | COV_STA_CD | Translated to A/T/etc. |
| `maturity_date` | LH_COV_PHA | COV_MT_EXP_DT | Coverage maturity/expiry |
| `coi_renewal_rate` | LH_COV_INS_RNL_RT | RNL_RT | Type "C" rate ÷ scale factor |

---

### 2.2 `BenefitInfo`

Represents one active benefit on the policy (CCV, GCO, PW, ADB, GIO, etc.). **Not used in M1** but defined here for completeness — the engine ignores benefits when the list is empty.

```python
@dataclass
class BenefitInfo:
    """A single benefit/rider on a coverage."""
    
    coverage_phase: int = 1           # Which coverage this benefit belongs to
    benefit_type: str = ""            # SPM_BNF_TYP_CD (e.g., "W"=waiver, "C"=CCV, "#"=ABR)
    benefit_subtype: str = ""         # SPM_BNF_SBY_CD
    benefit_amount: float = 0.0       # units × VPU
    units: float = 0.0
    vpu: float = 0.0
    issue_date: Optional[date] = None
    issue_age: int = 0
    cease_date: Optional[date] = None
    rating_factor: float = 0.0       # BNF_RT_FCT — multiplier applied to benefit COI
    coi_rate: Optional[float] = None  # Annual per-unit from DB2 (BNF_ANN_PPU_AMT)
    is_active: bool = True
```

---

### 2.3 `IllustrationPolicyData`

The top-level policy data object passed to the illustration engine.

```python
@dataclass
class IllustrationPolicyData:
    """Complete policy data for UL illustration projection.
    
    Mutable by design — load from DB2 via build_illustration_data(),
    then override any field for what-if analysis before projecting.
    """
    
    # ── Identity ──────────────────────────────────────────────
    policy_number: str = ""
    region: str = "CKPR"
    company_code: str = ""
    insured_name: str = ""
    
    # ── Plan / Product ────────────────────────────────────────
    plancode: str = ""                    # Base plancode (e.g., "1U143900")
    product_type: str = ""                # "UL", "IUL", "SGUL"
    form_number: str = ""                 # Policy form number
    issue_state: str = ""                 # 2-letter state code
    company_sub: str = ""                 # "ANICO", "EMC", etc.
    
    # ── Demographics (policy-level = base coverage) ───────────
    issue_date: Optional[date] = None
    issue_age: int = 0
    attained_age: int = 0
    rate_sex: str = ""                      # "M", "F", "U" — rate sex from LH_COV_INS_RNL_RT.RT_SEX_CD (via pi.base_sex_code)
    rate_class: str = ""                  # "N", "S", "P", "Q", "R", "T"
    
    # ── Face / Death Benefit ──────────────────────────────────
    face_amount: float = 0.0             # Total base face (sum of all base segments)
    units: float = 0.0                   # Total units (face / 1000)
    db_option: str = "A"                 # "A" (Level), "B" (Increasing), "C" (ROP)
    band: int = 1                        # Current band based on total base face
    
    # ── Account Value ─────────────────────────────────────────
    account_value: float = 0.0           # Current total fund value (from LH_POL_MVRY_VAL.CSV_AMT via pi.mv_av())
    cost_basis: float = 0.0              # Tax cost basis
    
    # ── Premium ───────────────────────────────────────────────
    modal_premium: float = 0.0           # Premium per billing period
    annual_premium: float = 0.0          # Annual total premium
    billing_frequency: int = 1           # Months between payments (1=monthly, 3=quarterly, 6=semi, 12=annual)
    premiums_paid_to_date: float = 0.0   # Cumulative premiums
    premiums_ytd: float = 0.0            # Premiums this policy year
    
    # ── Interest / Crediting ──────────────────────────────────
    guaranteed_interest_rate: float = 0.0   # e.g., 0.03 (3%)
    current_interest_rate: float = 0.0      # Current declared rate (overridable for what-if)
    
    # ── Duration / Timing ─────────────────────────────────────
    policy_year: int = 1                  # Calculated from valuation_date and issue_date (via pi.policy_year)
    policy_month: int = 1                 # Month within policy year 1-12 — calculated from valuation_date and issue_date (via pi.policy_month)
    duration: int = 1                     # Total months since issue (policy_year-1)*12 + policy_month
    valuation_date: Optional[date] = None # Last monthly valuation date (LH_POL_MVRY_VAL.MVRY_DT)
    maturity_age: int = 121               # From plancode PremiumCeaseAge
    
    # ── 7702 / Guideline ──────────────────────────────────────
    def_of_life_ins: str = "GPT"           # "GPT" or "CVAT" — derived from pi.def_of_life_ins_code (1/2/4→GPT, 3/5→CVAT)
    glp: float = 0.0                     # Guideline Level Premium
    gsp: float = 0.0                     # Guideline Single Premium
    accumulated_glp: float = 0.0         # Running total of GLP allowance
    corridor_percent: float = 100.0      # Current GP corridor % (e.g., 134.0 at age 59)
    
    # ── Targets ───────────────────────────────────────────────
    mtp: float = 0.0                     # Minimum Target Premium (annual per $1000)
    accumulated_mtp: float = 0.0         # Accumulated MTP target
    ctp: float = 0.0                     # Commission Target Premium (annual per $1000)
    
    # ── TAMRA / MEC ───────────────────────────────────────────
    is_mec: bool = False
    tamra_7pay_level: float = 0.0        # Maximum annual premium in 7-pay period
    tamra_7pay_start_date: Optional[date] = None
    tamra_7pay_cash_value: float = 0.0
    tamra_7year_lowest_db: float = 0.0   # Lowest DB in 7-pay window
    tamra_7year_contributions: List[float] = field(default_factory=lambda: [0.0] * 7)
    
    # ── Loans ─────────────────────────────────────────────────
    regular_loan_principal: float = 0.0
    regular_loan_accrued: float = 0.0
    preferred_loan_principal: float = 0.0
    preferred_loan_accrued: float = 0.0
    variable_loan_principal: float = 0.0
    variable_loan_accrued: float = 0.0
    
    # ── Withdrawals ───────────────────────────────────────────
    withdrawals_to_date: float = 0.0
    
    # ── Shadow Account (Day 1 in scope) ───────────────────────
    shadow_account_value: float = 0.0    # Current shadow AV (from LH_POL_TARGET WHERE TAR_TYP_CD='IX' via pi.gav)
    swam: float = 0.0                    # Sweep Account Minimum
    
    # ── CVAT / DCV (if applicable) ────────────────────────────
    deemed_cash_value: float = 0.0       # Manual entry for CVAT policies
    
    # ── Base Coverage Segments ───────────────────────────────
    # Base coverages ONLY (original + increase segments with same plancode).
    # Built from pi.get_base_coverages() which filters is_base=True.
    segments: List[CoverageSegment] = field(default_factory=list)
    
    # ── Benefits / Riders (future milestones) ───────────────
    # Riders and benefits are in a SEPARATE list from base segments.
    # Built from pi.get_benefits() for benefit records (CCV, PW, ADB, etc.)
    # and pi.get_riders() for rider coverages (CTR, STR, LTR, APBR).
    # Rider coverages (M8+) will get their own RiderSegment type.
    benefits: List[BenefitInfo] = field(default_factory=list)
    
    # ── Computed Properties ───────────────────────────────────
    
    @property
    def total_face(self) -> float:
        """Sum of all base segment face amounts."""
        return sum(s.face_amount for s in self.segments) if self.segments else self.face_amount
    
    @property
    def total_units(self) -> float:
        """Sum of all base segment units."""
        return sum(s.units for s in self.segments) if self.segments else self.units
    
    @property
    def total_loan_balance(self) -> float:
        """Total outstanding loan balance (all types, principal + accrued)."""
        return (self.regular_loan_principal + self.regular_loan_accrued +
                self.preferred_loan_principal + self.preferred_loan_accrued +
                self.variable_loan_principal + self.variable_loan_accrued)
    
    @property
    def is_gpt(self) -> bool:
        """True if policy uses Guideline Premium Test."""
        return self.def_of_life_ins == "GPT"
    
    @property
    def is_cvat(self) -> bool:
        """True if policy uses Cash Value Accumulation Test."""
        return self.def_of_life_ins == "CVAT"
    
    @property
    def has_loans(self) -> bool:
        return self.total_loan_balance > 0
    
    @property
    def is_smoker(self) -> bool:
        return self.rate_class.upper() in ("S", "Q", "T")
    
    # ── Debug / Reference (not used by engine) ────────────────
    # cash_surrender_value is NOT an input field — CSV is calculated by the engine.
    # It can be stored after projection for validation/debug purposes only.
    _debug_csv: float = 0.0              # Calculated CSV (AV - surrender charges - loans). Not injected from DB2.
    
    @property
    def base_segment(self) -> Optional[CoverageSegment]:
        """The first (original) base coverage segment."""
        return self.segments[0] if self.segments else None
```

---

## 3. DB2-to-Field Mapping

> **Note:** All fields are sourced through `PolicyInformation` properties (`suiteview.polview.models.policy_information`), not via direct DB2 queries. The DB2 table/column references below show the *underlying* source for documentation purposes. In code, always use the corresponding `pi.*` property.

### 3.1 Policy-Level Fields

| Field | DB2 Table | DB2 Column | Transform |
|---|---|---|---|
| `policy_number` | LH_BAS_POL | POL_NBR | strip |
| `company_code` | LH_BAS_POL | CK_CMP_CD | strip |
| `plancode` | LH_COV_PHA | PLN_DES_SER_CD | Coverage 1 |
| `product_type` | Derived | — | pi.product_type |
| `issue_state` | LH_BAS_POL | ISS_GOV_CD | strip, translate |
| `issue_date` | LH_COV_PHA | ISSUE_DT | Coverage 1 issue date |
| `issue_age` | LH_COV_PHA | INS_ISS_AGE | Coverage 1 |
| `attained_age` | Derived | — | issue_age + policy_year − 1 |
| `rate_sex` | LH_COV_INS_RNL_RT | RT_SEX_CD | Rate sex via `pi.base_sex_code` (already translated: M/F) |
| `rate_class` | LH_COV_INS_RNL_RT | RT_CLS_CD | Coverage 1 renewal rate record |
| `face_amount` | LH_COV_PHA | COV_UNT_QTY × COV_VPU_AMT | Sum of base coverages |
| `units` | Derived | — | face_amount / 1000 |
| `db_option` | LH_NON_TRD_POL | DTH_BNF_PLN_OPT_CD | 1→A, 2→B, 3→C |
| `account_value` | LH_POL_MVRY_VAL | CSV_AMT | Current AV via `pi.mv_av()` or `pi.total_fund_value` |
| `cost_basis` | LH_POL_TOTALS | POL_CST_BSS_AMT | |
| `modal_premium` | LH_BAS_POL | POL_PRM_AMT | |
| `annual_premium` | Derived | — | modal × (12 / billing_frequency) |
| `billing_frequency` | LH_BAS_POL | PMT_FQY_PER | Months between payments |
| `premiums_paid_to_date` | LH_POL_TOTALS | TOT_REG_PRM_AMT + TOT_ADD_PRM_AMT | |
| `premiums_ytd` | LH_POL_YR_TOT | Current year total | |
| `guaranteed_interest_rate` | LH_NON_TRD_POL | POL_GUA_ITS_RT | |
| `current_interest_rate` | LH_POL_MVRY_VAL | Current declared rate | Or from plancode config |
| `policy_year` | Derived | — | Years since issue to valuation |
| `policy_month` | Derived | — | Months within current year |
| `duration` | Derived | — | (policy_year − 1) × 12 + policy_month |
| `valuation_date` | LH_POL_MVRY_VAL | MVRY_DT | UL monthly valuation |
| `maturity_age` | Plancode JSON | PremiumCeaseAge | e.g., 121 |
| `def_of_life_ins` | LH_NON_TRD_POL | TFDF_CD | `pi.def_of_life_ins_code`: 1/2/4→"GPT", 3/5→"CVAT" |
| `glp` | LH_COV_INS_GDL_PRM | PRM_RT_TYP_CD='A' | |
| `gsp` | LH_COV_INS_GDL_PRM | PRM_RT_TYP_CD='S' | |
| `accumulated_glp` | LH_POL_TARGET | TAR_TYP_CD='TA' | |
| `corridor_percent` | LH_NON_TRD_POL | CDR_PCT | Default 100 |
| `mtp` | LH_POL_TARGET | TAR_TYP_CD='MT' | |
| `accumulated_mtp` | LH_POL_TARGET | TAR_TYP_CD='MA' | |
| `ctp` | LH_COM_TARGET | TAR_TYP_CD='CT' | Sum |
| `is_mec` | LH_TAMRA_7_PY_PER | MEC_STA_CD | Derived boolean |
| `tamra_7pay_level` | LH_TAMRA_7_PY_PER | SVPY_LVL_PRM_AMT | |
| `tamra_7pay_start_date` | LH_TAMRA_7_PY_PER | SVPY_PER_STR_DT | |
| `regular_loan_principal` | LH_POL_LOAN | LN_PRI_AMT | Non-preferred loans |
| `preferred_loan_principal` | LH_POL_LOAN | LN_PRI_AMT | Where PRF_LN_IND=1 |
| `variable_loan_principal` | LH_UL_FND_BAL | Fund LZ | |
| `withdrawals_to_date` | LH_POL_TOTALS | TOT_WTD_AMT | |
| `shadow_account_value` | LH_POL_TARGET | TAR_TYP_CD='IX' | Via `pi.gav` |
| `band` | Derived | — | Rates.get_band(plancode, total_face) |

---

## 4. Test Policy Validation (UE000576)

After `build_illustration_data("UE000576")`, the object should contain:

| Field | Expected Value |
|---|---|
| `policy_number` | "UE000576" |
| `plancode` | "1U143900" |
| `product_type` | "UL" |
| `issue_date` | 2016-10-27 |
| `issue_age` | 50 |
| `attained_age` | 59 |
| `rate_sex` | "M" |
| `rate_class` | "N" |
| `face_amount` | 90,000.00 |
| `units` | 90.0 |
| `db_option` | "A" |
| `band` | 2 |
| `account_value` | 11,936.84 |
| `modal_premium` | 150.00 |
| `billing_frequency` | 1 (monthly) |
| `annual_premium` | 1,800.00 |
| `guaranteed_interest_rate` | 0.03 |
| `policy_year` | 10 |
| `policy_month` | 6 |
| `duration` | 114 |
| `def_of_life_ins` | "GPT" |
| `issue_state` | "FL" |
| `maturity_age` | 121 |
| `is_mec` | False |
| `has_loans` | False |
| `segments` | 1 segment (base, phase 1) |
| `segments[0].issue_age` | 50 |
| `segments[0].rate_sex` | "M" |
| `segments[0].rate_class` | "N" |
| `segments[0].face_amount` | 90,000.00 |
| `segments[0].band` | 2 |
| `segments[0].table_rating` | 0 (standard) |
| `segments[0].flat_extra` | 0.0 |
| `benefits` | 3 ABR benefits (type "#") — present but ignored by M1 engine |

---

## 5. Overridable Fields for What-If

Any field on `IllustrationPolicyData` or its `CoverageSegment` entries can be modified before projection. Common what-if overrides:

| Override | Field(s) to Modify | Example |
|---|---|---|
| Change premium | `modal_premium`, `annual_premium` | `policy.modal_premium = 200.00` |
| Change crediting rate | `current_interest_rate` | `policy.current_interest_rate = 0.045` |
| Change face amount | `segments[0].face_amount`, `face_amount`, `units`, `band` | Must recalculate band/units |
| Change sex for rating | `rate_sex`, `segments[0].rate_sex` | `policy.rate_sex = "F"` |
| Change DBO | `db_option` | `policy.db_option = "B"` |
| Inject different AV | `account_value` | `policy.account_value = 15000.00` |
| Test different rate class | `rate_class`, `segments[0].rate_class` | `policy.rate_class = "S"` |
| Override CSV (debug only) | `_debug_csv` | For validation against admin system |
| Add substandard | `segments[0].table_rating` | `policy.segments[0].table_rating = 4` |

**Note:** When overriding face amount, the caller should also update `units` (face/1000) and `band` (via `Rates.get_band()`). A future helper method `update_face(new_face)` will handle this automatically.

---

## 6. Future Extensions (Not M1)

### 6.1 `IllustrationInput` — Mid-Projection Changes (M6)

For year-by-year scheduled changes (face decrease at age 65, premium changes, recurring loans), a separate `IllustrationInput` object will be passed alongside `IllustrationPolicyData`:

```python
@dataclass
class IllustrationInput:
    """Scheduled mid-projection changes (M6+)."""
    premium_schedule: Dict[int, float] = field(default_factory=dict)    # year → annual premium
    face_changes: Dict[int, float] = field(default_factory=dict)        # year → new face amount
    dbo_changes: Dict[int, str] = field(default_factory=dict)           # year → new DBO
    withdrawals: Dict[int, float] = field(default_factory=dict)         # year → withdrawal amount
    loan_schedule: Dict[int, float] = field(default_factory=dict)       # year → loan amount
    rate_class_changes: Dict[int, str] = field(default_factory=dict)    # year → new rate class
```

### 6.2 Rider Coverage Segments

Rider coverages (CTR, STR, LTR, APBR) will be tracked as `RiderSegment` objects — separate from base `CoverageSegment` entries. These are banded independently and have their own COI rate structures.

---

## 7. `build_illustration_data()` — Service Function

```python
def build_illustration_data(
    policy_number: str,
    region: str = "CKPR",
    company_code: Optional[str] = None,
) -> IllustrationPolicyData:
    """Load policy data from DB2 and return a ready-to-project IllustrationPolicyData.
    
    Uses the shared PolicyInformation class (suiteview.core.policy_service)
    to fetch all tables from DB2, then maps fields into the illustration
    data model.
    
    Args:
        policy_number: CyberLife policy number (e.g., "UE000576")
        region: DB2 region code (default "CKPR")
        company_code: Optional company filter
        
    Returns:
        IllustrationPolicyData with all fields populated from DB2.
        Segments and benefits lists are populated from coverage/benefit records.
        
    Raises:
        ValueError: If policy not found in DB2.
    """
```

### 7.1 Mapping Logic (follows ABRQuote `build_abr_policy` pattern)

1. Call `get_policy_info(policy_number, region, company_code)`
2. Validate `pi.exists` — raise `ValueError` if not found
3. Map policy-level fields (see Section 3.1 table)
4. Translate codes: rate_sex (from `pi.base_sex_code`), DBO (1→A, 2→B, 3→C), rate class, def_of_life_ins (`pi.def_of_life_ins_code`: 1/2/4→"GPT", 3/5→"CVAT")
5. Build `CoverageSegment` list from `pi.get_base_coverages()` — base coverages only (is_base=True, same plancode as coverage 1)
6. Build `BenefitInfo` list from `pi.get_benefits()` — filter to active benefits (cease_date is None or > today)
7. Calculate derived fields: `units`, `band`, `duration`, `attained_age`, `annual_premium`
8. Load substandard ratings via `pi.get_substandard_ratings()` for each coverage
9. Return populated `IllustrationPolicyData`
