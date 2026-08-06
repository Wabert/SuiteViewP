# ABR Quote — Calculation Chain Reference

Salvaged from the retired ABR_QUOTE_IMPLEMENTATION_PLAN.md (the conversion
from the VBA workbook is complete — see suiteview/abrquote/). This section
is the surviving reference for the quoting math: 2008 VBT + substandard
modifications → modified mortality → APV → actuarial discount → benefit.

## 1. Complete Calculation Chain

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

### 1.1 Step-by-Step Calculation

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
The VBA used Excel's Goal Seek to derive table ratings and flat extras from medical
assessment inputs (5yr survival, 10yr survival, life expectancy). The Python port
implements this in `suiteview/abrquote/core/goal_seek.py` (scipy `brentq` when
available, with a pure-Python `_bisect_fallback` — scipy is not a hard dependency):

- **Table Rating Goal Seek**: Find `table_rating` (0–25) such that
  `Assessment_Index(table_rating) = target_index` (1–7)
- **Flat Extra Goal Seek**: Find `flat_extra` such that
  `computed_survival_rate = target_survival_rate`
- **Life Expectancy**: Compute curtate future life expectancy from modified qx,
  add 0.5 for complete (UDD approximation)

---

