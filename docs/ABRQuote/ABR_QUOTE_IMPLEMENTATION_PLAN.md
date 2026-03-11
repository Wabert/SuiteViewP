# ABR Quote Tool — Python Implementation Plan

## 1. Executive Summary

Convert the **ABR Quote System Signature Term (v5.6)** Excel/VBA workbook to a Python
application integrated into SuiteView. The tool calculates **Accelerated Benefit Rider (ABR)**
quotes for term life insurance policies — determining how much a policyholder can accelerate
(receive early) from their death benefit based on actuarial present value calculations.

**What it does in plain English:**
1. User enters a policy number → system retrieves policy data from DB2
2. User enters medical assessment (life expectancy, survival rates)
3. System calculates modified mortality rates using 2008 VBT + substandard adjustments
4. System computes the Actuarial Present Value of future benefits and premiums
5. System outputs: `Accelerated Benefit = Death_Benefit - Actuarial_Discount - Admin_Fee`
6. Results exported to Excel workbook with Full and Max Partial acceleration sheets

---

## 2. Complete Calculation Chain

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ABR QUOTE CALCULATION FLOW                          │
│                                                                            │
│  ┌──────────────┐    ┌──────────────────┐    ┌─────────────────────────┐   │
│  │ Policy Data  │───>│ Term Premium     │───>│ Mortality Calculation   │   │
│  │ (DB2/PolView)│    │ Calculation      │    │ (calc.monthly)          │   │
│  │              │    │ - Rate lookup    │    │ - 2008 VBT lookup      │   │
│  │ • Policy #   │    │ - Table rating   │    │ - Table rating mult    │   │
│  │ • Issue Age  │    │ - Flat extra     │    │ - Flat extra add       │   │
│  │ • Sex/Class  │    │ - Modal premium  │    │ - Mortality improvement│   │
│  │ • Face Amt   │    │ - Policy fee     │    │ - UDD monthly convert  │   │
│  │ • State      │    └────────┬─────────┘    └──────────┬──────────────┘   │
│  │ • Plan Code  │             │                         │                  │
│  └──────────────┘             │    ┌─────────────────────┘                  │
│                               ▼    ▼                                       │
│  ┌──────────────┐    ┌──────────────────┐    ┌─────────────────────────┐   │
│  │ Medical      │───>│ APV Engine       │───>│ Output                  │   │
│  │ Assessment   │    │ (ABA monthly)    │    │                         │   │
│  │              │    │                  │    │ Full Acceleration:      │   │
│  │ • 5yr Surv.  │    │ PVFB = Σ(DB×v×  │    │  = Face - Discount     │   │
│  │ • 10yr Surv. │    │   tp'x×q'x)×adj │    │    - Fee               │   │
│  │ • Life Exp.  │    │                  │    │                         │   │
│  │ • Table Rtg  │    │ PVFP = Σ(Prem×  │    │ Max Partial:            │   │
│  │ • Flat Extra │    │   v×tp'x)       │    │  = (Face-MinFace)       │   │
│  └──────────────┘    │                  │    │    - Proportional Disc  │   │
│                      │ Disc = Face -    │    │    - Fee               │   │
│                      │  (PVFB - PVFP)  │    │                         │   │
│                      └──────────────────┘    └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Step-by-Step Calculation

#### Step 1: Policy Data Retrieval
- Input: Policy number + region
- Source: PolView's `PolicyInformation` (DB2 via ODBC)
- Extracted fields:
  - `issue_age`, `sex` (M/F/U), `rate_class` (N/S/P/Q/R/T)
  - `face_amount` (in thousands × 1000), `issue_date`, `maturity_age` (95)
  - `issue_state`, `billing_mode` (1=A, 2=SA, 3=Q, 4=M, 5=PAC)
  - `plan_code` (e.g., B75TL400), `table_rating` (A-G → 1-7)
  - `flat_extra`, `flat_to_age`, `paid_to_date`
  - `policy_month`, `policy_year`, `attained_age`

#### Step 2: Term Premium Calculation
- **Lookup KEY** = `"{plancode} {sex} {class} {band} {issue_age}"` (e.g., "B75TL400 F N 4 33")
- **Band** from face amount:
  | Face Range | Band |
  |---|---|
  | 50,000 – 99,999 | 1 |
  | 100,000 – 249,999 | 2 |
  | 250,000 – 499,999 | 3 |
  | 500,000 – 999,999 | 4 |
  | 1,000,000+ | 5 |
- **Rate lookup**: `INDEX(BaseTermPremiumRates, MATCH(KEY, col_A), MATCH(policy_year, header_row))`
  → Returns annual premium rate per $1,000
- **Policy fee**: $60 (all plan codes per lookup table)
- **Annual premium** = `ROUND(base_rate + table_rate + flat_rate, 2) × face/1000 + policy_fee`
  - `table_rate = base_rate × table_rating × 0.25`
  - `flat_rate = flat_extra if attained_age < flat_to_age else 0`
- **Modal premium** = `annual_premium × modal_factor`
  | Mode | Factor |
  |---|---|
  | Annual (1) | 1.000 |
  | Semi-Annual (2) | 0.515 |
  | Quarterly (3) | 0.265 |
  | Direct Monthly (4) | 0.093 |
  | PAC Monthly (5) | 0.0864 |

#### Step 3: Mortality Calculation (calc.monthly engine)
For each month from current policy month to maturity (up to 1,460 months ≈ 121 years):
1. **VBT Lookup**: Select 2008 VBT block by Sex+Class:
   - MN = Male Non-smoker, FN = Female Non-smoker
   - MS = Male Smoker, FS = Female Smoker
   - Look up `qx_annual = VBT[duration_year][issue_age]` (rates per 1,000 → divide by 1,000)
2. **Mortality Improvement**:
   `qx_improved = mort_mult × qx × (1 - improvement_rate)^(min(cap, attained_age) - base_age)`
3. **Table Rating**: `qx_rated = min(1, qx_improved × table_factor)` within applicable month range
4. **Flat Extra**: `qx_flat = min(1, qx_rated + flat/1000)` within applicable duration range
5. **UDD Monthly Conversion**:
   `qx_monthly = qx_annual/12 / (1 - (month_in_year - 1) × (qx_annual/12))`
   (Uniform Distribution of Deaths assumption)

#### Step 4: APV Calculation (ABA monthly calc engine)
- **Monthly interest rate** = `(1 + annual_rate)^(1/12) - 1`
- **Continuous mortality adjustment** = `monthly_rate / ln(1 + monthly_rate)`
- For each month `t` (rows 7–1466, up to 1,460 months):
  - `q'x_t` = monthly mortality from Step 3 (or 1.0 if duration ≥ 121)
  - `p'x_t` = `1 - q'x_t` (monthly survival probability)
  - `tp'x` = cumulative survival = product of all previous p'x
  - `v^(t+1)` = `1 / (1 + monthly_rate)^(future_month - current_month)` (discount factor)
  - `PVDB_t` = `(face/1000) × q'x × tp'x × v^(t+1)` (PV of death benefit if death in month t)
  - `PVFP_t` = `premium_rate × v^t × tp'x` (PV of premium, only at year boundaries)
- **Summation**:
  - `PVFB = SUM(all PVDB_t) × continuous_mort_adj × 1000`
  - `PVFP = SUM(all PVFP_t)` (set to 0 for FL + Terminal)
  - `PVFD = 0` (no dividends for term products)

#### Step 5: Actuarial Discount & Benefit
- `Actuarial_Discount = ROUND(Face + PUA - (PVFB + PVFD - PVFP), 2)`
  Simplifies to: `ROUND(Face - PVFB + PVFP, 2)` (since PUA=0, PVFD=0 for term)
- `Admin_Fee = $100 if state == "FL" else $250`

**Full Acceleration:**
| Component | Formula |
|---|---|
| Eligible DB | Face |
| Actuarial Discount | from APV calc |
| Admin Fee | $100 (FL) or $250 |
| **Accelerated Benefit** | **Eligible - Discount - Fee** |
| Benefit Ratio | Benefit / Eligible |

**Max Partial Acceleration:**
| Component | Formula |
|---|---|
| Eligible DB | Face - Min_Face ($50,000) |
| Actuarial Discount | (Eligible_Partial / Eligible_Full) × Full_Discount |
| Admin Fee | same as Full |
| **Accelerated Benefit** | **Eligible - Discount - Fee** |

#### Step 6: Goal Seek (for medical assessment → substandard)
The VBA uses Excel's Goal Seek to derive table ratings and flat extras from medical
assessment inputs (5yr survival, 10yr survival, life expectancy). In Python, we'll use
`scipy.optimize.brentq` or `scipy.optimize.bisect`:

- **Table Rating Goal Seek**: Find `table_rating` (0–25) such that
  `Assessment_Index(table_rating) = target_index` (1–7)
- **Flat Extra Goal Seek**: Find `flat_extra` such that
  `computed_survival_rate = target_survival_rate`
- **Life Expectancy**: Compute curtate future life expectancy from modified qx,
  add 0.5 for complete (UDD approximation)

---

## 3. Data Storage Strategy

### 3.1 Embedded in Code (Python dict/numpy array)
**2008 VBT Mortality Table** — 4 blocks × 121 durations × 100 issue ages = ~48,400 rates
- Store as `dict[str, numpy.ndarray]` keyed by `"MN"`, `"FN"`, `"MS"`, `"FS"`
- Each value is a 2D array `[duration][issue_age]` with rates per 1,000
- Extract once from workbook → serialize to Python source file
- Reason: Static regulatory table, never changes, fast lookup needed

### 3.2 Separate SQLite Database (`~/.suiteview/abr_quote.db`)

Rate data is stored in a **dedicated** SQLite database, separate from the main
`suiteview.db` (which holds personal/connection data). This keeps actuarial
rate tables cleanly isolated.

**Database path:** `~/.suiteview/abr_quote.db`

**BaseTermPremiumRates** — 28,646 rows × 83 duration columns
- Table: `term_rates`
- Columns: `key TEXT PRIMARY KEY, plancode TEXT, sex TEXT, rate_class TEXT, band INTEGER, issue_age INTEGER, rate_1 REAL, rate_2 REAL, ... rate_82 REAL`
- Or normalized: `term_rates(key, duration, rate)` with composite PK
- Reason: Large dataset, efficient key-based lookup, updatable

**ABR Interest Rate** — ~200 rows of monthly Moody's rates
- Table: `interest_rates`
- Columns: `date TEXT, rate REAL, iul_var_loan_rate REAL`
- Reason: Updated periodically, date-based lookup

**Per Diem Limits** — ~10 rows
- Table: `per_diem`
- Columns: `year INTEGER PRIMARY KEY, per_diem_limit REAL, annual_limit REAL`

### 3.3 Config Constants (Python)
```python
# Plan code → policy fee mapping
PLAN_CODE_FEES = {
    "B15TD100": 60, "B15TD200": 60, "B15TD300": 60, "B15TD400": 60, "B15TD500": 60,
    "B75TL100": 60, "B75TL200": 60, "B75TL300": 60, "B75TL400": 60, "B75TL500": 60,
}

# Band breakpoints
BAND_BREAKPOINTS = [(50_000, 1), (100_000, 2), (250_000, 3), (500_000, 4), (1_000_000, 5)]

# Modal factors
MODAL_FACTORS = {1: 1.0, 2: 0.515, 3: 0.265, 4: 0.093, 5: 0.0864}

# Table rating letter → numeric mapping
TABLE_RATING_MAP = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7}

# Plan code lookup by plancode → (level_period, description)
PLAN_CODE_INFO = {
    "B15TD100": ("10", "Signature Term 2012"), "B15TD200": ("15", "Signature Term 2012"),
    "B15TD300": ("20", "Signature Term 2012"), "B15TD400": ("30", "Signature Term 2012"),
    "B15TD500": ("1",  "Signature Term 2012"),
    "B75TL100": ("10", "Signature Term 2018"), "B75TL200": ("15", "Signature Term 2018"),
    "B75TL300": ("20", "Signature Term 2018"), "B75TL400": ("30", "Signature Term 2018"),
    "B75TL500": ("1",  "Signature Term 2018"),
}
```

---

## 4. Module Structure

```
suiteview/
├── abrquote/
│   ├── __init__.py              # Package init, launch_abrquote(), version
│   ├── main.py                  # Factory: create_abrquote_window()
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── abr_constants.py     # All constants, lookup tables, plan codes, bands, modal factors
│   │   ├── abr_data.py          # Data classes: ABRQuoteInput, ABRQuoteResult, MortalityParams
│   │   ├── vbt_2008.py          # 2008 VBT mortality table (embedded data + lookup functions)
│   │   └── term_rates.py        # BaseTermPremiumRates SQLite access, interest rate lookup
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── mortality_engine.py  # calc.monthly equivalent: VBT lookup, adjustments, UDD
│   │   ├── apv_engine.py        # ABA monthly calc equivalent: PVFB, PVFP, discount
│   │   ├── premium_calc.py      # Term premium calculation: rate lookup, modal factors
│   │   └── goal_seek.py         # scipy.optimize wrappers for table rating & flat extra
│   │
│   └── ui/
│       ├── __init__.py
│       ├── abr_window.py        # Main window (FramelessWindowBase), wizard flow
│       ├── policy_panel.py      # Policy info display panel
│       ├── assessment_panel.py  # Medical assessment input panel
│       ├── results_panel.py     # Quote results display panel
│       └── abr_styles.py        # Teal & gold theme constants
│
scripts/
├── run_abrquote.py              # Standalone launcher
│
data/
├── abr_term_rates.csv           # (optional) CSV export of BaseTermPremiumRates for import
```

### 4.1 File Descriptions

| File | Lines (est.) | Purpose |
|---|---|---|
| `__init__.py` | ~40 | Package exports, `launch_abrquote()` with deferred UI import |
| `main.py` | ~30 | `create_abrquote_window()` factory |
| `abr_constants.py` | ~80 | All static constants: bands, modal factors, plan codes, fees, table ratings |
| `abr_data.py` | ~120 | `@dataclass` definitions for inputs, outputs, intermediate results |
| `vbt_2008.py` | ~500 | Embedded 2008 VBT data + `get_qx(sex, smoker, issue_age, duration)` |
| `term_rates.py` | ~200 | SQLite CRUD for term rates + interest rates + band lookup |
| `mortality_engine.py` | ~250 | Monthly mortality calculation: VBT → improvement → table → flat → UDD |
| `apv_engine.py` | ~300 | Monthly APV loop: discount factors, PVFB, PVFP, actuarial discount |
| `premium_calc.py` | ~150 | Premium rate lookup, annual/modal premium computation |
| `goal_seek.py` | ~200 | `find_table_rating()`, `find_flat_extra()` using scipy.optimize |
| `abr_window.py` | ~500 | Main wizard window with stacked panels |
| `policy_panel.py` | ~200 | Policy data display using StyledInfoTableGroup |
| `assessment_panel.py` | ~300 | Medical assessment input form with validation |
| `results_panel.py` | ~350 | Quote results display + Export to Excel button |
| `abr_styles.py` | ~60 | Teal/gold theme: `TEAL_PRIMARY`, `TEAL_DARK`, `GOLD_ACCENT` |
| `run_abrquote.py` | ~40 | CLI launcher matching `run_polview.py` pattern |

**Total estimated**: ~3,300 lines

---

## 5. Data Classes

```python
@dataclass
class ABRPolicyData:
    """Policy data extracted from PolView PolicyInformation."""
    policy_number: str
    region: str
    issue_age: int
    attained_age: int
    sex: str              # "M", "F", "U"
    rate_class: str       # "N", "S", "P", "Q", "R", "T"
    face_amount: float
    issue_date: date
    maturity_age: int     # typically 95
    issue_state: str      # 2-letter state code
    plan_code: str        # e.g., "B75TL400"
    billing_mode: int     # 1=A, 2=SA, 3=Q, 4=DM, 5=PAC
    policy_month: int
    policy_year: int
    table_rating: str     # "A"-"G" or "" for standard
    flat_extra: float     # per $1000
    flat_to_age: int
    paid_to_date: date
    modal_premium: float

@dataclass
class MedicalAssessment:
    """Medical assessment inputs from the user."""
    rider_type: str                     # "Terminal" or "Chronic"
    assessment_format: str              # "Table Rating and or Flat Extra"
    five_year_survival: float           # e.g., 0.018
    ten_year_survival: float            # e.g., 0.5
    life_expectancy_years: float        # e.g., 4.9
    life_expectancy_rounded: int        # rounded to nearest integer
    derived_table_rating: int           # 0-25, from goal seek
    derived_increased_decrement: float  # e.g., 200

@dataclass
class MortalityParams:
    """Parameters for the mortality calculation engine."""
    issue_age: int
    sex: str
    rate_class: str          # determines VBT block (N→Non-smoker, S→Smoker, etc.)
    policy_month: int        # current policy month
    maturity_age: int
    table_rating_1: int      # first table rating value (0-25)
    table_1_start_month: int
    table_1_last_month: int
    table_rating_2: int      # second table rating (for changes mid-policy)
    table_2_start_month: int
    table_2_last_month: int
    flat_extra_1: float      # monthly flat extra (per $1000)
    flat_1_duration: int     # duration in months
    flat_extra_2: float
    flat_2_duration: int
    mortality_multiplier: float   # typically 1.0
    improvement_rate: float       # mortality improvement factor
    improvement_cap: int          # cap age for improvement
    is_terminal: bool             # if True, bypass substandard for VBT lookup path

@dataclass
class APVResult:
    """Results from the APV calculation."""
    pvfb: float              # Present Value of Future Benefits
    pvfp: float              # Present Value of Future Premiums
    pvfd: float              # Present Value of Future Dividends (always 0 for term)
    actuarial_discount: float
    monthly_interest_rate: float
    continuous_mort_adj: float

@dataclass
class ABRQuoteResult:
    """Final ABR quote output."""
    # Full Acceleration
    full_eligible_db: float
    full_actuarial_discount: float
    full_admin_fee: float
    full_accel_benefit: float
    full_benefit_ratio: float

    # Max Partial Acceleration
    partial_eligible_db: float
    partial_actuarial_discount: float
    partial_admin_fee: float
    partial_accel_benefit: float
    partial_benefit_ratio: float

    # Premium info
    premium_before: str      # e.g., "59.18 Monthly"
    premium_after_full: float    # 0 for full acceleration
    premium_after_partial: str   # min face premium for partial

    # Supporting details
    plan_description: str
    abr_interest_rate: float
    quote_date: date
```

---

## 6. Core Engine Pseudocode

### 6.1 Mortality Engine (`mortality_engine.py`)

```python
class MortalityEngine:
    def __init__(self, vbt: VBT2008, params: MortalityParams):
        self.vbt = vbt
        self.params = params

    def compute_monthly_rates(self) -> list[float]:
        """Compute monthly qx for all months from current to maturity.
        Returns list of monthly qx values (up to ~1460 entries).
        Replicates 'calc.monthly' sheet logic."""
        monthly_rates = []
        vbt_block = self._select_vbt_block()  # MN/FN/MS/FS based on sex+class

        for month_idx in range(len_months):
            duration_month = month_idx + 1
            duration_year = (duration_month - 1) // 12 + 1
            month_in_year = ((duration_month - 1) % 12) + 1
            attained_age = self.params.issue_age + duration_year - 1

            if duration_year >= 121:
                monthly_rates.append(1.0)
                continue

            # Step 1: VBT lookup
            qx_annual = self.vbt.get_qx(vbt_block, self.params.issue_age, duration_year)
            qx = qx_annual / 1000.0

            # Step 2: Mortality improvement
            qx = self._apply_improvement(qx, attained_age)

            # Step 3: Table rating
            qx = self._apply_table_rating(qx, duration_month)

            # Step 4: Flat extra
            qx = self._apply_flat_extra(qx, duration_month)

            # Step 5: UDD monthly conversion
            qx_monthly = self._udd_monthly(qx, month_in_year)

            monthly_rates.append(qx_monthly)

        return monthly_rates

    def _udd_monthly(self, qx_annual: float, month_in_year: int) -> float:
        """Uniform Distribution of Deaths: convert annual to monthly qx."""
        frac = qx_annual / 12
        return frac / (1 - (month_in_year - 1) * frac)
```

### 6.2 APV Engine (`apv_engine.py`)

```python
class APVEngine:
    def __init__(self, annual_interest_rate: float, policy_data: ABRPolicyData):
        self.annual_rate = annual_interest_rate
        self.monthly_rate = (1 + annual_interest_rate) ** (1/12) - 1
        self.cont_mort_adj = self.monthly_rate / math.log(1 + self.monthly_rate)
        self.policy = policy_data

    def compute(self, monthly_qx: list[float], premium_schedule: list[float]) -> APVResult:
        """Compute Present Values.
        monthly_qx: from MortalityEngine
        premium_schedule: annual premium per $1000 at each policy year boundary
        """
        face_units = self.policy.face_amount / 1000
        current_month = self.policy.policy_month
        maturity_duration = (self.policy.maturity_age - self.policy.issue_age) * 12

        pvfb_sum = 0.0
        pvfp_sum = 0.0
        tp_x = 1.0  # cumulative survival

        for t, qx in enumerate(monthly_qx):
            duration_month = t + 1
            future_month = current_month + t
            month_in_year_boundary = (future_month % 12 == 1)  # start of policy year

            # Survival
            p_x = 1 - qx
            # Discount factor
            months_ahead = t + 1
            v_t1 = 1 / (1 + self.monthly_rate) ** months_ahead if months_ahead > 0 else 1

            # PVDB component
            if duration_month < maturity_duration:
                pvdb_t = face_units * qx * tp_x * v_t1
                pvfb_sum += pvdb_t

            # PVFP component (premium at year boundaries only)
            if month_in_year_boundary and duration_month < maturity_duration:
                year_idx = (duration_month - 1) // 12
                if year_idx < len(premium_schedule):
                    prem_rate = premium_schedule[year_idx]
                    v_t = 1 / (1 + self.monthly_rate) ** t if t > 0 else 1
                    pvfp_sum += prem_rate * v_t * tp_x

            # Update cumulative survival
            tp_x *= p_x

        pvfb = pvfb_sum * self.cont_mort_adj * 1000

        # FL + Terminal → no premium credit
        is_fl_terminal = (self.policy.issue_state == "FL" and
                          self.policy.rider_type.startswith("T"))
        pvfp = 0 if is_fl_terminal else pvfp_sum

        actuarial_discount = round(self.policy.face_amount - (pvfb - pvfp), 2)

        return APVResult(
            pvfb=pvfb, pvfp=pvfp, pvfd=0,
            actuarial_discount=actuarial_discount,
            monthly_interest_rate=self.monthly_rate,
            continuous_mort_adj=self.cont_mort_adj
        )
```

### 6.3 Goal Seek (`goal_seek.py`)

```python
from scipy.optimize import brentq

def find_table_rating_for_assessment(
    mortality_engine_factory,  # callable(table_rating) → MortalityEngine
    target_assessment_index: int,  # 1-7
    assessment_function,  # callable(mortality_rates) → float (assessment index)
) -> int:
    """Find table rating that produces desired assessment index.
    Replaces Excel Goal Seek for table rating."""

    def objective(table_rating):
        engine = mortality_engine_factory(int(table_rating))
        rates = engine.compute_monthly_rates()
        return assessment_function(rates) - target_assessment_index

    result = brentq(objective, 0, 25, xtol=0.5)
    return round(result)

def find_flat_extra_for_survival(
    mortality_engine_factory,  # callable(flat_extra) → MortalityEngine
    target_survival: float,    # target 5-year survival rate
    survival_function,         # callable(mortality_rates) → float
) -> float:
    """Find flat extra that produces target survival rate."""

    def objective(flat_extra):
        engine = mortality_engine_factory(flat_extra)
        rates = engine.compute_monthly_rates()
        return survival_function(rates) - target_survival

    result = brentq(objective, 0, 100, xtol=0.001)
    return round(result, 3)
```

---

## 7. UI Design

### 7.1 Theme: "Coastal Gold" (Teal & Gold)

```python
# abr_styles.py
TEAL_PRIMARY  = "#00897B"   # Main headers, buttons
TEAL_DARK     = "#00695C"   # Darker accent, pressed states
TEAL_LIGHT    = "#4DB6AC"   # Hover states, highlights
TEAL_BG       = "#E0F2F1"   # Light background panels
GOLD_ACCENT   = "#D4A017"   # Border accents, active indicators
GOLD_TEXT      = "#FFC107"   # Gold text on dark backgrounds
SURFACE_DARK  = "#1A2332"   # Dark surface background
SURFACE_MID   = "#243447"   # Mid surface
TEXT_PRIMARY   = "#FFFFFF"   # Primary text on dark
TEXT_SECONDARY = "#B0BEC5"   # Secondary/muted text
```

### 7.2 Window Layout — Wizard Flow

The main window follows SuiteView's `FramelessWindowBase` pattern with a **3-panel wizard**:

```
┌─────────────────────────────────────────────────────────────────┐
│ ⬛ ABR Quote Tool                                    _ □ ✕     │  ← Custom title bar
├─────────────────────────────────────────────────────────────────┤
│ ┌─── Step 1 ───┐  ┌─── Step 2 ───┐  ┌─── Step 3 ───┐         │  ← Step indicator
│ │ Policy Info  │──│  Assessment  │──│   Results    │         │
│ └──────────────┘  └──────────────┘  └──────────────┘         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   ACTIVE PANEL                           │  │
│  │                                                          │  │
│  │  (Content depends on current step)                       │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌────────────┐                    ┌─────────┐ ┌────────────┐  │
│  │  ◄ Back    │                    │  Next ► │ │ Export XLSX │  │
│  └────────────┘                    └─────────┘ └────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Step 1 — Policy Information:**
```
┌─────────────────────────────────────────────────┐
│  Policy Number: [____________] Region: [▼ CKPR] │
│  [Retrieve Policy]                              │
│                                                 │
│  ┌─ Policy Details ─────────────────────────┐   │
│  │ Insured:  John Doe        Face: $500,000 │   │
│  │ Sex:      Female          State: MD      │   │
│  │ Issue Age: 33             Class: N       │   │
│  │ Att. Age:  44             Mode: Monthly  │   │
│  │ Plan:     B75TL400        Premium: $59.18│   │
│  │ Table:    None            Flat: $0.00    │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  ABR Interest Rate: 5.45%  (as of 2024-01)      │
│  Per Diem Limit: $420  Annual Limit: $153,300   │
└─────────────────────────────────────────────────┘
```

**Step 2 — Medical Assessment:**
```
┌─────────────────────────────────────────────────┐
│  Rider Type:    [▼ Terminal     ]               │
│                                                 │
│  Assessment Format: [▼ Table Rating + Flat Extra]│
│                                                 │
│  ┌─ Survival Inputs ──────────────────────┐     │
│  │ 5-Year Survival Rate:  [0.018    ]  %  │     │
│  │ 10-Year Survival Rate: [0.500    ]  %  │     │
│  │ Life Expectancy:       [4.9      ] yrs │     │
│  └────────────────────────────────────────┘     │
│                                                 │
│  ┌─ Derived Substandard ──────────────────┐     │
│  │ Table Rating:           25             │     │
│  │ Increased Decrement:    200%           │     │
│  │ Assessment Index:       7              │     │
│  └────────────────────────────────────────┘     │
│                                                 │
│  [Calculate]                                    │
└─────────────────────────────────────────────────┘
```

**Step 3 — Results:**
```
┌─────────────────────────────────────────────────────┐
│  ┌─ Full Acceleration ──────────────────────────┐   │
│  │ Eligible Death Benefit:     $500,000.00      │   │
│  │ Actuarial Discount:          $37,290.68      │   │
│  │ Administrative Fee:             $250.00      │   │
│  │ ─────────────────────────────────────────     │   │
│  │ Accelerated Benefit:        $462,459.32      │   │
│  │ Benefit Ratio:                  92.49%       │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ┌─ Max Partial Acceleration ───────────────────┐   │
│  │ Eligible Death Benefit:     $450,000.00      │   │
│  │ Actuarial Discount:          $33,561.61      │   │
│  │ Administrative Fee:             $250.00      │   │
│  │ ─────────────────────────────────────────     │   │
│  │ Accelerated Benefit:        $416,188.39      │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ┌─ Premium Impact ─────────────────────────────┐   │
│  │ Before: $59.18 Monthly  After (Full): $0.00  │   │
│  │ After (Partial): $XX.XX Monthly              │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  [Export to Excel]  [Copy Summary]  [New Quote]     │
└─────────────────────────────────────────────────────┘
```

### 7.3 Messages & Validation

Following DEV_GUIDE.md's "friendly messaging" principle:
- Premium mismatch: *"Hmm, the premiums don't match up. Please double-check with Actuarial."*
- Life expectancy warning: *"Life expectancy is under 2.1 years — you may want to confirm
  with Medical Directors if this qualifies for a Terminal rider."*
- Large payout: *"Heads up! Payout exceeds $100,000 — Medical Directors should review."*
- High face: *"Face amount over $1M — check the Data Page for the maximum acceleration amount."*
- Interest rate missing: *"The ABR Interest Rate tab needs updating before we can calculate."*

---

## 8. Excel Output Generation

Using `openpyxl` to create a workbook matching the current output format:

### Sheet: "Output - Full"
```
Section 4: EFFECT ON COVERAGE
─────────────────────────────────────────────────────────
Coverages       | Death Benefit   | Accelerated  | DB After
                | Before          | Benefit      | Acceleration
─────────────────────────────────────────────────────────
Sig Term 2018   | $500,000        | $500,000     | $0
─────────────────────────────────────────────────────────

Premium (all coverages):
Before: 59.18 Monthly    After: 0

Cash Surrender Value: Before: 0    After: 0
Policy Debt:          Before: 0    After: 0

Section 5: ACCELERATED BENEFIT PAYMENT
─────────────────────────────────────────────────────────
Total Eligible Death Benefit:       $500,000.00
An Actuarial Discount:              ($37,290.68)
An Administrative Charge:              ($250.00)
Any Policy Debt:                         $0.00
─────────────────────────────────────────────────────────
Total Accelerated Benefit Payment:  $462,459.32
```

### Sheet: "Output - Max Partial"
Same structure with partial values (Face - $50,000 minimum face).

---

## 9. Data Import Pipeline

### One-time extraction from workbook:

```python
# scripts/import_abr_data.py
"""One-time script to extract data from Excel workbook into SQLite + Python source."""

def extract_vbt_2008(wb_path: str) -> dict:
    """Extract 2008 VBT → generate vbt_2008.py source file."""
    # Read 4 blocks (MN/FN/MS/FS) from '2008 VBT' sheet
    # Each: 121 rows (durations) × 100 cols (issue ages 0-99)
    # Write as Python dict literal

def extract_term_rates(wb_path: str, db_path: str):
    """Extract BaseTermPremiumRates → SQLite abr_term_rates table."""
    # Read 28,646 rows × 83 cols
    # Parse key column: "B75TL400 F S 1 43"
    # Store rate schedule by key

def extract_interest_rates(wb_path: str, db_path: str):
    """Extract ABR Interest Rate → SQLite abr_interest_rates table."""
    # Read monthly rates, Per Diem limits

def extract_per_diem(wb_path: str, db_path: str):
    """Extract Per Diem limits → SQLite abr_per_diem table."""
```

---

## 10. Dependencies

### New packages needed:
```
scipy          # For optimize.brentq (Goal Seek replacement)
numpy          # For VBT array operations
openpyxl       # Already in requirements.txt (Excel output generation)
```

### Existing SuiteView dependencies used:
```
PyQt6          # UI framework
pyodbc         # DB2 connection (via PolicyInformation)
```

---

## 11. Implementation Order

### Phase 1: Data Foundation (Est. 2-3 hours)
1. Create `suiteview/abrquote/` package structure
2. Write `abr_constants.py` with all lookup tables
3. Write `abr_data.py` with all dataclasses
4. Create `import_abr_data.py` script to extract VBT + rates from workbook
5. Generate `vbt_2008.py` with embedded mortality data
6. Create SQLite tables and import term rates + interest rates

### Phase 2: Calculation Engines (Est. 3-4 hours)
7. Implement `mortality_engine.py` — VBT lookup, adjustments, UDD conversion
8. Implement `premium_calc.py` — rate lookup, premium computation
9. Implement `apv_engine.py` — monthly APV loop, PVFB/PVFP/discount
10. Implement `goal_seek.py` — scipy.optimize wrappers
11. Write unit tests to validate against known Excel values

### Phase 3: UI (Est. 3-4 hours)
12. Create `abr_styles.py` — teal/gold theme
13. Create `abr_window.py` — main wizard window
14. Create `policy_panel.py` — policy info display + PolicyInformation integration
15. Create `assessment_panel.py` — medical input form
16. Create `results_panel.py` — results display + export
17. Create `run_abrquote.py` launcher

### Phase 4: Integration & Testing (Est. 2 hours)
18. Excel output generation (openpyxl template)
19. End-to-end test with known policy data
20. Validate results match Excel workbook output
21. Clean up temp extraction scripts

**Total estimated effort: 10-13 hours**

---

## 12. Validation Strategy

### Known Test Case (from current workbook):
- **Policy**: Female, Age 33, Non-smoker, Face $500,000, MD, Plan B75TL400
- **Assessment**: Terminal, 5yr=0.018, 10yr=0.5, LE=4.9yrs, Table=25, Decrement=200
- **Interest Rate**: 5.45%
- **Expected Output**:
  - Full Eligible DB: $500,000
  - Full Accelerated Benefit: $462,459.32
  - Benefit Ratio: 92.49%
  - Premium Before: $59.18 Monthly
  - Premium After (Full): $0

### Validation Steps:
1. VBT lookup: verify `qx` values for FN block at issue age 33, durations 1-10
2. Monthly mortality: verify first 12 monthly qx values match `calc.monthly!R` column
3. Premium rate: verify base rate lookup for `"B75TL400 F N 4 33"` at year 1
4. APV: verify PVFB, PVFP match `ABA monthly calc!B25, B26`
5. Actuarial discount matches `ABA monthly calc!B30`
6. Final benefit = Face - Discount - Fee

---

## 13. Key Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| VBT storage | Embedded Python dict | Static data, fast access, no external dependency |
| Term rates storage | SQLite (`abr_quote.db`) | Separate DB — rate data isolated from personal data |
| Goal Seek | `scipy.optimize.brentq` | Robust root-finding, faster than bisection, handles edge cases |
| Monthly calculation | NumPy arrays | ~1,460 monthly iterations × multiple columns = vectorizable |
| APV loop | Pure Python loop | Clear logic mapping to Excel, ~1,460 iterations is fast enough |
| UI framework | PyQt6 wizard panels | Matches SuiteView pattern, 3-step flow is natural |
| Output format | openpyxl Excel | Matches existing workflow, preserves formatting |
| Policy data source | PolView PolicyInformation | Already built, DB2 integration proven |
| Interest rate | Latest from SQLite table | User confirmed: "ABR Interest Rate = IUL Variable Loan Rate" |

---

## 14. Risk Areas & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| VBT select format complexity | Wrong mortality rates | Validate against 10+ known issue age/duration combos from Excel |
| UDD monthly conversion edge cases | Slightly wrong monthly qx at high ages | Test with qx near 1.0 (terminal ages), cap at 1.0 |
| Goal Seek convergence | Can't find table rating | Use brentq with wide bracket [0,25], add fallback bisection |
| Benefit Rates sheet (PW18 ART data) | Missing ART premium data | Scope to base term only initially; ART/PW18 is separate feature |
| FL Terminal special case | Wrong PVFP | Explicit check: `if FL + Terminal → PVFP = 0` |
| Partial acceleration proportionality | Wrong partial discount | Use ratio: `partial_discount = (partial_eligible / full_eligible) × full_discount` |
| Large face amounts (>$1M) | Different max acceleration rules | Add validation message per Excel's existing check |

---

*Document generated from deep-dive analysis of ABR Quote System Signature Term (v5.6) workbook.
All formulas verified by programmatic extraction using openpyxl.*
