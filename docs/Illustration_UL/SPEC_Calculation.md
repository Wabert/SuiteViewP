# UL Illustration — Calculation Specification

**Module:** `suiteview.illustration.core`  
**Version:** 1.1 (Milestone 1)  
**Date:** 2026-04-13  

---

## 1. Scope

This spec covers the **M1 calculation pipeline** — monthly projection for a single policy with one base coverage, no riders, no loans. Supports DBO A, B, and C with corridor segmentation. The engine runs Steps 6, 8, 9, and 11 of the full 15-step pipeline defined in REQUIREMENTS.md.

### 1.1 M1 Pipeline (Simplified)

Follows the RERUN CalcEngine column order:

```
┌─────────────────────────────────────────────────────────┐
│  For each projected month:                              │
│                                                         │
│  0. Advance Counters      (CalcEngine cols 2-21)        │
│     ├─ date, policy_year, policy_month                  │
│     ├─ duration (months from issue)                     │
│     └─ attained_age                                     │
│                                                         │
│  1. Apply Premium         (CalcEngine cols 367-403)     │
│     ├─ gross premium                                    │
│     ├─ target/excess split vs CTP                       │
│     ├─ premium load (TPP / EPP)                         │
│     └─ net premium → AV after premium                   │
│                                                         │
│  2. Monthly Deduction     (CalcEngine cols 405-516)     │
│     ├─ NAR AV = max(0, AV_after_premium)                │
│     ├─ Standard DB (by DBO A/B/C)                       │
│     ├─ Gross DB (corridor check)                        │
│     ├─ Discounted DB per segment (cov1, corridor)       │
│     ├─ NAR per segment — FIFO (cov1 first, corr last)   │
│     ├─ COI charge per segment (corr uses cov1 rate)     │
│     ├─ EPU charge (round-near to 2 dp)                  │
│     ├─ Monthly fee, AV charge                           │
│     └─ AV after deduction                               │
│                                                         │
│  3. Interest Credit       (CalcEngine cols 548-585)     │
│     ├─ Declared rate + bonus                            │
│     └─ End-of-month AV                                  │
│                                                         │
│  4. End-of-Month Values   (CalcEngine cols 524-546,     │
│     │                       594-600)                    │
│     ├─ Surrender value (AV − surrender charge)          │
│     ├─ Ending AV, ending DB                             │
│     └─ Lapse check                                      │
└─────────────────────────────────────────────────────────┘
```

### 1.2 What M1 Does NOT Include

| Feature | Milestone | Pipeline Step |
|---|---|---|
| Policy changes (face, DBO, withdrawals) | M6 | Step 1 |
| Riders and benefits | M8 | Step 2 |
| MTP / CTP target calculations | M2 | Steps 3-4 |
| Guideline premium / TAMRA | M7 | Step 5 |
| Requested premium logic (complex) | M2 | Step 6 |
| Loan capitalization / repayment | M5 | Step 7 |
| Exception premium | M12 | Step 10 |
| Shadow account | M12 | Step 12 |
| Deemed cash value (CVAT) | M12 | Step 13 |
| GCO rider | M8 | Step 14 |
| Full lapse / MEC testing | M7 | Step 15 |
| What-if mid-projection changes | M6 | Step 1 |
| Multiple assumption scenarios | M2 | — |
| Multiple coverage segments | M4 | — |

---

## 2. Data Inputs

### 2.1 From `IllustrationPolicyData`

| Input | Field | Example (UE000576) |
|---|---|---|
| Starting account value | `account_value` | $11,936.84 |
| Monthly premium | `modal_premium` | $150.00 |
| DBO | `db_option` | "A" (Level) |
| Face amount | `face_amount` | $90,000 |
| Units | `units` | 90.0 |
| Issue date | `issue_date` | 2016-10-27 |
| Issue age | `issue_age` | 50 |
| Attained age | `attained_age` | 59 |
| Sex | `rate_sex` | "M" |
| Rate class | `rate_class` | "N" |
| Band | `band` | 2 |
| Policy year | `policy_year` | 10 |
| Policy month | `policy_month` | 6 |
| Duration (months) | `duration` | 114 |
| Valuation date | `valuation_date` | 2026-03-27 |
| Current crediting rate | `current_interest_rate` | from plancode or override |
| Guaranteed interest rate | `guaranteed_interest_rate` | 0.03 |
| Maturity age | `maturity_age` | 121 |
| Definition of life ins | `def_of_life_ins` | "GPT" |
| Premiums YTD | `premiums_ytd` | $750.00 (from PI `premium_ytd`) |
| Premiums paid to date | `premiums_paid_to_date` | $10,800.00 |
| CTP (commission target) | `ctp` | ~$1,242.00 (annual, calculated at issue) |
| Cost basis | `cost_basis` | $10,800.00 |

### 2.2 From `PlancodeConfig` (JSON)

| Input | Field | Example (1U143900) |
|---|---|---|
| Interest method | `IntCalcMethod` | "Declared" |
| Interest day-count | `Interest Method` | "ExactDays" |
| Premium load source | `PremiumLoad` | "Table" |
| Flat premium load | `PremFlatLoad` | 0 |
| EPU source | `EPU_Code` | "Table" |
| EPU basis | `EPU SA_Basis` | "CurrentSA" |
| MFEE source | `MFEE` | 5 (or "Table") |
| Bonus type | `Bonus` | \"Table\" (rates from tRates_IntBonus.json) |\n| Table rating factor | `Table Rating Factor` | 0.25 |", "oldString": "| Bonus type | `Bonus` | \"Table\" |\n| Table rating factor | `Table Rating Factor` | 0.25 |
| Corridor code | `CorridorCode` | 1 |
| Maturity age | `PremiumCeaseAge` | 121 |
| Dynamic banding | `Dynamic Banding` | 3 |

### 2.3 From `IllustrationRates` (UL_Rates DB)

All rate arrays are 1-indexed by **policy year** (not monthly duration), looked up via the `Rates` class.

| Rate | Lookup | Indexed By | M1 Usage |
|---|---|---|---|
| COI | `get_rates('COI', plancode, issue_age, rate_sex, rateclass, scale=1, band)` | policy year | NAR-based charge |
| EPU | `get_rates('EPU', plancode, issue_age, rate_sex, rateclass, scale=1, band)` | policy year | Per-unit charge |
| SCR | `get_rates('SCR', plancode, issue_age, rate_sex, rateclass, scale=1, band)` | policy year | Surrender value |
| MFEE | `get_rates('MFEE', plancode, issue_age, rate_sex, rateclass, scale=1, band)` | policy year | Flat monthly fee |
| CORR | `get_rates('CORR', plancode, issue_age)` | attained age | Corridor factor |
| GINT | `get_rates('GINT', plancode)` | policy year | Guaranteed rate |
| TPP | `get_rates('TPP', plancode, rate_sex, rateclass, scale=1, band)` | policy year | Target prem load % |
| EPP | `get_rates('EPP', plancode, rate_sex, rateclass, scale=1, band)` | policy year | Excess prem load % |
| MTP | `get_mtp(plancode, issue_age, rate_sex, rateclass, band)` | — | Target premium (single value) |

**Rate indexing:** Arrays are 1-based by **policy year**. For a policy at year 10 month 6, the first projected month uses `rate_year = 10` (same year), and after anniversary rolls to `rate_year = 11`. Corridor is the exception — it is indexed by attained age.

### 2.4 From `BonusConfig` (tRates_IntBonus.json)

Bonus interest rates are stored in a locally-maintained JSON table at `plancodes/tRates_IntBonus.json`, keyed by `(Plancode, EffectiveDate)`. This replaces the UL_Rates DB tables BONUSDUR / BONUSAV / SCALE_BONUSDUR / SCALE_BONUSAV.

At projection start, `load_bonus_config(plancode, valuation_date)` resolves the latest effective entry on or before the valuation date.

| Field | Type | Example (1U143900, pre-2018) |
|---|---|---|
| `bonus_dur_rate` | float | 0.005 (0.5%) |
| `bonus_dur_threshold` | int | 10 (applied after year 10) |
| `bonus_av_rate` | float | 0.0025 (0.25%) |
| `bonus_av_threshold` | float | 100000 |

**Example entries for EXECUL:**

```json
[
    {
        "Plancode": "1U143900",
        "EffectiveDate": "1900-01-01",
        "BonusDurRate": 0.005,
        "BonusDurThreshold": 10,
        "BonusAVRate": 0.0025,
        "BonusAVThreshold": 100000
    },
    {
        "Plancode": "1U143900",
        "EffectiveDate": "2018-01-18",
        "BonusDurRate": 0.0,
        "BonusDurThreshold": 0,
        "BonusAVRate": 0.0,
        "BonusAVThreshold": 0
    }
]
```

The second entry (effective 2018-01-18) zeroes out all bonuses, so any policy with a valuation date on or after 2018-01-18 gets no bonus. This approach avoids the problem of DB scale tables not being updated — the JSON table is under our control.

---

## 3. Calculation Details

### 3.0 Advance Counters

**CalcEngine cols 2-21.** Counters are computed **first**, before any dollar calculations.

```
# Advance month
if policy_month == 12:
    policy_year += 1
    policy_month = 1
else:
    policy_month += 1

duration += 1
attained_age = issue_age + (duration - 1) // 12

# Rate arrays indexed by policy year (NOT monthly duration)
rate_year = policy_year

# Calendar date — note (duration - 1) to keep months consecutive
date = issue_date + relativedelta(months=duration - 1)

# Flags
is_anniversary = (policy_month == 1)
```

On anniversary (`policy_month == 1`), year-to-date accumulators reset:

```
if is_anniversary:
    premiums_ytd = 0.0
```

---

### 3.1 Apply Premium

**Module:** `core/premium_handler.py`  
**Function:** `apply_premium(state, policy_data, plancode_config, rates) → MonthlyState`

#### 3.1.1 Determine Premium Amount

For M1, premium is applied every month at the modal premium amount:

```
gross_premium = policy_data.modal_premium
```

(M2+ will handle annual/quarterly/semi-annual modes, premium schedules, and guideline restrictions.)

#### 3.1.2 Target vs. Excess Premium (CTP Split)

Premium is split into **target** and **excess** portions by comparing premiums paid year-to-date against the **Commission Target Premium (CTP)**. The CTP is a policy-level annual premium calculated once at issue — it does not accumulate or change over time.

**From CalcEngine cols 395-396:**

```
# prem_ytd_before = premiums already paid this year BEFORE applying this month's premium
prem_ytd_before = premiums_ytd

# After applying this premium
prem_ytd_after = prem_ytd_before + gross_premium

# Target vs excess split
prem_under_target = max(min(CTP - prem_ytd_before, gross_premium), 0)
prem_over_target  = max(min(gross_premium, prem_ytd_after - CTP), 0) if prem_ytd_after > CTP else 0
```

**Logic:** As the policyholder pays premiums throughout the year, they get the TPP (target premium percentage) load rate until the premiums paid year-to-date exceed the CTP, at which point they get the EPP (excess premium percentage) load rate. When a single premium straddles the CTP boundary, it is split — the portion under CTP gets TPP, the portion over gets EPP.

For UE000576: CTP = ~$1,242/year (example). Monthly premium of $150 × 12 = $1,800 > CTP, so month 9 or 10 will cross the CTP boundary and require a split.

> **Note:** M1 bypasses the MTP (minimum target premium) and CTP **calculations** — these values are pre-loaded from `IllustrationPolicyData.ctp` (originally from `LH_COM_TARGET`). The MTP accumulation logic (M2) and CTP rate calculation (M2) are not part of M1.

#### 3.1.3 Premium Load Calculation

Premium load is deducted before crediting to account value:

```
If PremiumLoad = "Table":
    target_load = prem_under_target × TPP_rate[duration]
    excess_load = prem_over_target  × EPP_rate[duration]
    total_premium_load = target_load + excess_load
Else:
    total_premium_load = gross_premium × PremiumLoad_flat_rate

If PremFlatLoad > 0 and gross_premium > 0:
    total_premium_load += PremFlatLoad    (flat dollar amount per premium)

net_premium = gross_premium - total_premium_load
```

#### 3.1.4 Apply to Account Value

```
AV_after_premium = AV_beginning + net_premium
```

#### 3.1.5 Update Tracking Fields

```
premiums_ytd += gross_premium
premiums_paid_to_date += gross_premium
cost_basis += gross_premium
```

---

### 3.2 Monthly Deduction

**Module:** `core/monthly_deduction.py`  
**Function:** `calculate_deduction(state, policy_data, plancode_config, rates) → MonthlyState`

Follows the RERUN CalcEngine cols 405-516 exactly.

#### 3.2.1 AV After Premium and NAR AV

```
mAV = AV_after_premium                    # CalcEngine col 405: starting point for deduction
nar_av = max(0, mAV)                      # CalcEngine col 406: floored at 0 for DB/NAR calcs
```

#### 3.2.2 Standard Death Benefit

```
# CalcEngine col 407
if db_option == "A":
    standard_db = face_amount
elif db_option == "B":
    standard_db = face_amount + nar_av
elif db_option == "C":
    standard_db = face_amount + max(0, premiums_to_date - withdrawals_to_date)
```

#### 3.2.3 Gross Death Benefit (Corridor Check)

```
# CalcEngine cols 408-411
corridor_rate = CORR_rates[attained_age]         # e.g., 1.34 at age 59
gross_db = max(standard_db, corridor_rate * nar_av)
corr_amount = gross_db - standard_db              # amount DB was raised for corridor
```

For GPT policies the corridor factor comes from the CORR rate table. For CVAT policies it uses the MDBR (minimum death benefit ratio) factor instead — same formula structure, different rate source.

For UE000576 (DBO A, GPT): gross_db = max($90,000, 1.34 × $12,086.84) = max($90,000, $16,196.37) = $90,000. Corridor does not apply (AV too low).

#### 3.2.4 Discounted Death Benefit — Per Segment

The death benefit is discounted for one month of guaranteed interest. Each coverage segment (including corridor) is discounted separately:

```
# CalcEngine cols 418-422
guaranteed_rate = guaranteed_interest_rate         # e.g., 0.03
discount_factor = (1 + guaranteed_rate) ** (1/12)  # NOT rounded

# Cov1: base coverage (DBO-adjusted)
# DBO A: discounted_db_cov1 = face / discount_factor
# DBO B: discounted_db_cov1 = (face + nar_av) / discount_factor
# DBO C: discounted_db_cov1 = (face + premiums_to_date) / discount_factor

if dbo == "A":
    discounted_db_cov1 = face / discount_factor
elif dbo == "B":
    discounted_db_cov1 = (face + nar_av) / discount_factor
elif dbo == "C":
    discounted_db_cov1 = (face + max(0, premiums_to_date - withdrawals)) / discount_factor

# Corridor segment (only when corridor raises DB)
discounted_db_corr = corr_amount / discount_factor  if corr_amount > 0 else 0

# Total
discounted_db = discounted_db_cov1 + discounted_db_corr
```

#### 3.2.5 Net Amount at Risk (NAR) — FIFO Per Segment

NAR is calculated on the **discounted** death benefit, with account value subtracted FIFO — oldest segment first, corridor always last:

```
# CalcEngine cols 423-426 — FIFO allocation

# Cov1 absorbs AV first
nar_cov1 = max(0, discounted_db_cov1 - nar_av)
remaining_av = max(0, nar_av - discounted_db_cov1)

# Corridor absorbs any leftover AV
nar_corr = max(0, discounted_db_corr - remaining_av)

# Total NAR
nar = nar_cov1 + nar_corr
```

**Multi-segment (M4+):** AV is subtracted from segments in FIFO order (oldest to newest), with corridor always last:

```
For each segment i (oldest to newest, then corridor):
    nar_i = max(0, discounted_db_i - remaining_av)
    remaining_av = max(0, remaining_av - discounted_db_i)
```

#### 3.2.6 Cost of Insurance (COI) Charge — Per Segment

COI is calculated per segment. The corridor segment uses the **newest coverage segment's** COI rate (in M1, that's cov1):

```
# CalcEngine col 427
COI_rate = COI_rates[rate_year]       # monthly per $1000 of NAR, indexed by policy year
```

**Substandard adjustment (if table_rating > 0):**

```
table_factor = plancode_config.table_rating_factor    (e.g., 0.25)
flat_extra_monthly = flat_extra / 12                   (per $1000/month)
adjusted_COI_rate = COI_rate × (1 + table_factor × table_rating) + flat_extra_monthly
```

**Per-segment COI charges (no rounding):**

```
coi_charge_cov1 = (nar_cov1 / 1000) × adjusted_COI_rate
coi_charge_corr = (nar_corr / 1000) × adjusted_COI_rate   # uses cov1's rate
coi_charge = coi_charge_cov1 + coi_charge_corr
```

**Multi-segment (M4):** Each segment has its own COI rate based on its demographics (issue_age, rate_sex, rate_class, band). Corridor always uses the newest segment's rate. Total COI = sum of all segment COI charges.

#### 3.2.7 Expense Per Unit (EPU) Charge

**Rounding:** EPU is the only charge that is rounded — using `round_near` (ROUND_HALF_UP via Decimal) to 2 decimal places. All other charges (COI, premium loads, interest, etc.) are left unrounded.

```
If EPU_Code = "Table":
    EPU_rate = EPU_rates[rate_year]    (monthly per $1000, indexed by policy year)
    
    If EPU_SA_Basis = "CurrentSA":
        EPU_charge = round_near((face_amount / 1000) × EPU_rate, 2)
    Elif EPU_SA_Basis = "OriginalSA":
        EPU_charge = round_near((original_face_amount / 1000) × EPU_rate, 2)
Else:
    EPU_charge = round_near(EPU_Code_value × units, 2)    (flat rate from plancode config)
```

From CalcEngine col 496: `=ROUND(CHOOSE(sEPU_SA_Basis, EP7, EU7) * RX7/1000, 2)`

For UE000576: EPU = rate × 90 units.

#### 3.2.8 Monthly Fee (MFEE)

```
If MFEE = "Table":
    MFEE_charge = MFEE_rates[rate_year]
Else:
    MFEE_charge = MFEE_value    (flat dollar from plancode config)
```

For UE000576: MFEE = $5.00.

#### 3.2.9 Percent of Account Value Charge

Some products have an AV-based charge. **Note:** This rate varies by duration and is already stored as a **monthly** rate — do NOT divide by 12.

```
# CalcEngine col 503: =MAX(0, OO7 * SH7)  — no /12
AV_charge_rate = PoAV_rates[rate_year]     # monthly rate, already annualized in table
AV_charge = max(0, mAV × AV_charge_rate)
```

For EXECUL (1U143900): This product does not have an AV charge rate (rate = 0).

#### 3.2.10 Total Monthly Deduction

```
# CalcEngine col 515
total_deduction = COI_charge + EPU_charge + MFEE_charge + AV_charge
# (M8+ adds: rider charges, benefit charges, PW39 waiver charge)

# CalcEngine col 516
AV_after_deduction = mAV - total_deduction
```

---

### 3.3 Interest Credit

**Module:** `core/interest_calc.py`  
**Function:** `credit_interest(state, policy_data, plancode_config, rates) → MonthlyState`

#### 3.3.1 Determine Crediting Rate

For M1, only the **Declared** method is supported (IUL Blend is M9):

```
annual_rate = policy_data.current_interest_rate
```

#### 3.3.2 Bonus Interest

Bonus interest rates are resolved at projection start from `tRates_IntBonus.json` via `load_bonus_config(plancode, valuation_date)` → `BonusConfig`. The resolved config contains flat rate values (not array lookups).

**Duration bonus** — added after a threshold year:

```
if bonus.bonus_dur_threshold > 0 and bonus.bonus_dur_rate > 0:
    if rate_year > bonus.bonus_dur_threshold:
        annual_rate += bonus.bonus_dur_rate
```

For EXECUL (1U143900) with valuation before 2018-01-18: bonus_dur_rate = 0.005 (0.5%) added after year 10.
For EXECUL with valuation on/after 2018-01-18: bonus_dur_rate = 0.0 (bonus turned off).

**AV bonus** — added when AV exceeds a threshold:

```
if bonus.bonus_av_threshold > 0 and bonus.bonus_av_rate > 0:
    if AV_after_deduction >= bonus.bonus_av_threshold:
        annual_rate += bonus.bonus_av_rate
```

For EXECUL (pre-2018): bonus_av_rate = 0.0025 (0.25%) when AV > $100,000.

#### 3.3.3 Monthly Interest Calculation

**Method: ExactDays** (used by 1U143900) — **daily compound**:

```
days_in_month = actual calendar days in this policy month
days_in_year = 365 (or 366 for leap year)
monthly_rate = (1 + effective_annual_rate) ** (days_in_month / days_in_year) - 1
```

**Method: Monthly Compounding** (alternative, see plancode config):

```
monthly_rate = (1 + effective_annual_rate) ** (1/12) - 1
```

> **Important:** ExactDays uses **daily compound** `(1+r)^(d/Y) - 1`, NOT simple interest `r × d/Y`.

#### 3.3.4 Interest on Account Value

For M1 (no loans — all AV is unimpaired):

```
interest = AV_after_deduction × monthly_rate
```

**M5+ with loans:** AV is split into loan collateral (earns collateral rate) and unimpaired AV (earns full rate):

```
loan_collateral = total_loan_balance
unimpaired_AV = AV_after_deduction - loan_collateral
impaired_interest = loan_collateral × collateral_monthly_rate
unimpaired_interest = unimpaired_AV × monthly_rate
interest = impaired_interest + unimpaired_interest
```

#### 3.3.5 End-of-Month Account Value

```
end_of_month_AV = AV_after_deduction + interest
```

---

### 3.4 Surrender Value

Calculated at end of each month for reporting (does not affect AV):

```
SCR_rate = SCR_rates[rate_year]    (per $1000, indexed by policy year)
surrender_charge = SCR_rate × units
surrender_value = max(end_of_month_AV - surrender_charge - total_loan_balance, 0)
```

For UE000576 at duration 114 (year 10): SCR = 28.76 × 90 = $2,588.40. SV = $11,936.84 − $2,588.40 = $9,348.44.

---

### 3.5 Lapse Check (Simplified for M1)

M1 uses a basic lapse check — the full Step 15 logic (safety net, shadow, CCV, exception premium) is M7/M12:

```
if end_of_month_AV <= 0:
    policy_lapsed = True
    # Stop projection
```

---

## 4. `MonthlyState` — Output Per Month

**Module:** `models/calc_state.py`

```python
@dataclass
class MonthlyState:
    """Output for one month of the projection.
    
    Fields are ordered to match the CalcEngine pipeline sequence:
    counters → premium → deduction → interest → surrender → tracking.
    """
    
    # ── 0. Counters (CalcEngine cols 2-21) ────
    date: Optional[date] = None            # Calendar date of this monthiversary
    policy_year: int = 0
    policy_month: int = 0                  # 1-12 within year
    duration: int = 0                      # Total months from issue
    attained_age: int = 0
    is_anniversary: bool = False           # True when policy_month == 1
    
    # ── 1. Apply Premium (cols 367-403) ───────
    gross_premium: float = 0.0
    prem_under_target: float = 0.0         # Portion at TPP rate (under CTP)
    prem_over_target: float = 0.0          # Portion at EPP rate (over CTP)
    target_load: float = 0.0               # prem_under_target × TPP_rate
    excess_load: float = 0.0               # prem_over_target × EPP_rate
    flat_load: float = 0.0                 # Flat per-premium load (if any)
    total_premium_load: float = 0.0
    net_premium: float = 0.0
    av_after_premium: float = 0.0
    
    # ── 2. Monthly Deduction (cols 405-516) ───
    nar_av: float = 0.0                    # max(0, av_after_premium)
    standard_db: float = 0.0               # DB before corridor (DBO A/B/C)
    corridor_rate: float = 0.0             # Corridor factor at attained age
    gross_db: float = 0.0                  # max(standard_db, corridor_rate * nar_av)
    corr_amount: float = 0.0              # gross_db - standard_db (corridor segment)
    
    # Per-segment death benefit discount
    discounted_db_cov1: float = 0.0        # Base coverage discounted
    discounted_db_corr: float = 0.0        # Corridor segment discounted
    discounted_db: float = 0.0             # Total discounted DB
    
    # Per-segment NAR (FIFO: AV → cov1 first, corridor last)
    nar_cov1: float = 0.0                  # NAR for base coverage
    nar_corr: float = 0.0                  # NAR for corridor segment
    nar: float = 0.0                       # Total NAR
    
    # Per-segment COI (corridor uses cov1 rate)
    coi_rate: float = 0.0                  # Adjusted COI rate (cov1)
    coi_charge_cov1: float = 0.0           # COI on cov1 NAR
    coi_charge_corr: float = 0.0           # COI on corridor NAR (uses cov1 rate)
    coi_charge: float = 0.0               # Total COI = cov1 + corridor
    
    epu_rate: float = 0.0
    epu_charge: float = 0.0               # round_near to 2 decimals
    mfee_charge: float = 0.0
    av_charge: float = 0.0                 # % of AV charge (monthly, not /12)
    total_deduction: float = 0.0
    av_after_deduction: float = 0.0
    coi_rate: float = 0.0
    coi_charge: float = 0.0
    epu_rate: float = 0.0
    epu_charge: float = 0.0
    mfee_charge: float = 0.0
    av_charge: float = 0.0                 # % of AV charge (monthly, not /12)
    total_deduction: float = 0.0
    av_after_deduction: float = 0.0
    
    # ── 3. Interest Credit (cols 548-585) ─────
    days_in_month: int = 0                 # Actual calendar days (for ExactDays)
    annual_interest_rate: float = 0.0      # Base declared rate
    bonus_interest_rate: float = 0.0       # Bonus portion only
    effective_annual_rate: float = 0.0     # Base + bonus
    monthly_interest_rate: float = 0.0     # Actual rate applied this month
    interest_credited: float = 0.0
    av_end_of_month: float = 0.0           # AV after interest = ending AV
    
    # ── 4. End-of-Month Values (cols 524-600) ─
    scr_rate: float = 0.0                  # Surrender charge rate (per $1000)
    surrender_charge: float = 0.0
    surrender_value: float = 0.0
    ending_db: float = 0.0                 # Death benefit at end of month
    
    # ── Cumulative Tracking ───────────────────
    premiums_ytd: float = 0.0              # Premiums paid this policy year
    premiums_to_date: float = 0.0          # Cumulative premiums all time
    cost_basis: float = 0.0
    cumulative_interest: float = 0.0
    cumulative_charges: float = 0.0
    
    # ── Status ────────────────────────────────
    lapsed: bool = False
```

---

## 5. `IllustrationEngine` — Orchestrator

**Module:** `core/calc_engine.py`

### 5.1 Public API

```python
class IllustrationEngine:
    """UL illustration projection engine.
    
    Stateless — all inputs come through IllustrationPolicyData.
    Can be reused across multiple projections.
    """
    
    def __init__(self):
        self._rates_cache: Dict[str, IllustrationRates] = {}
    
    def project(
        self,
        policy: IllustrationPolicyData,
        months: Optional[int] = None,
    ) -> List[MonthlyState]:
        """Run monthly projection from current policy state.
        
        Args:
            policy: Populated IllustrationPolicyData (from DB2 or manual/overridden).
            months: Number of months to project. If None, projects to maturity age.
            
        Returns:
            List of MonthlyState. First entry (month 0) is the inforce snapshot
            with interest credited on the valuation date.
        """
    
    def process_month(
        self,
        state: MonthlyState,
        policy: IllustrationPolicyData,
        config: PlancodeConfig,
        rates: IllustrationRates,
        bonus: BonusConfig,
    ) -> MonthlyState:
        """Process a single month of the calculation pipeline.
        
        This is the core loop body. Takes the current state and produces
        the next month's state. Pure function — no side effects.
        """
```

### 5.2 Projection Loop

```python
def project(self, policy, months=None):
    config = load_plancode(policy.plancode)
    rates = self._load_rates(policy, config)
    
    # Load bonus config from tRates_IntBonus.json based on valuation date
    val_date = policy.valuation_date or policy.issue_date
    bonus = load_bonus_config(policy.plancode, val_date)
    
    if months is None:
        total_months = (policy.maturity_age - policy.attained_age) * 12 - policy.policy_month + 1
    else:
        total_months = months
    
    # ── Inforce snapshot (month 0) ────────────────────────
    # AV from CyberLife is after-deduction. Credit interest to roll
    # AV to end-of-month before projecting.
    rate_year_inforce = policy.policy_year
    month_date_inforce = policy.valuation_date or policy.issue_date
    
    intr0 = credit_interest(
        policy.account_value, policy, config, rates, bonus,
        rate_year_inforce, policy.attained_age, month_date_inforce,
    )
    
    inforce = MonthlyState(
        date=policy.valuation_date,
        policy_year=policy.policy_year,
        policy_month=policy.policy_month,
        duration=policy.duration,
        attained_age=policy.attained_age,
        av_after_deduction=policy.account_value,
        # Interest
        days_in_month=intr0.days_in_month,
        annual_interest_rate=intr0.annual_interest_rate,
        bonus_interest_rate=intr0.bonus_interest_rate,
        effective_annual_rate=intr0.effective_annual_rate,
        monthly_interest_rate=intr0.monthly_interest_rate,
        interest_credited=intr0.interest_credited,
        av_end_of_month=intr0.av_end_of_month,
        # Tracking
        premiums_ytd=policy.premiums_ytd,
        premiums_to_date=policy.premiums_paid_to_date,
        cost_basis=policy.cost_basis,
        cumulative_interest=intr0.interest_credited,
    )
    
    results = [inforce]
    state = inforce
    for _ in range(total_months):
        state = self.process_month(state, policy, config, rates, bonus)
        results.append(state)
        if state.lapsed:
            break
    
    return results
```

### 5.3 Single Month Processing

```python
def process_month(self, state, policy, config, rates, bonus):
    # ── Step 0: Advance Counters (first!) ──────────────────
    next_year, next_month = advance_month(state.policy_year, state.policy_month)
    duration = state.duration + 1
    attained_age = policy.issue_age + (duration - 1) // 12
    month_date = policy.issue_date + relativedelta(months=duration - 1)
    is_anniversary = (next_month == 1)
    
    # Rate arrays are 1-indexed by policy year (not monthly duration)
    rate_year = next_year
    
    # Reset YTD accumulators on anniversary
    premiums_ytd = 0.0 if is_anniversary else state.premiums_ytd
    
    # Start with end-of-month AV from previous month
    av = state.av_end_of_month
    
    # ── Step 1: Apply Premium ──────────────────────────────
    prem = apply_premium(av, policy, config, rates, rate_year,
                         premiums_ytd, premiums_to_date, cost_basis)
    av = prem.av_after_premium
    
    # ── Step 2: Monthly Deduction (segmented) ──────────────
    ded = calculate_deduction(av, policy, config, rates, rate_year,
                              attained_age, prem.premiums_to_date)
    av = ded.av_after_deduction
    
    # ── Step 3: Interest Credit ────────────────────────────
    intr = credit_interest(av, policy, config, rates, bonus,
                           rate_year, attained_age, month_date)
    av = intr.av_end_of_month
    
    # ── Step 4: End-of-Month Values ────────────────────────
    scr_rate = get_rate(rates, "scr", rate_year)
    surrender_charge = scr_rate * policy.units
    surrender_value = max(av - surrender_charge - policy.total_loan_balance, 0)
    ending_db = ded.gross_db
    lapsed = av <= 0
    
    return MonthlyState(
        # Counters
        date=month_date,
        policy_year=next_year,
        policy_month=next_month,
        duration=duration,
        attained_age=attained_age,
        is_anniversary=is_anniversary,
        # Premium
        gross_premium=prem.gross_premium,
        # ... premium load fields ...
        net_premium=prem.net_premium,
        av_after_premium=prem.av_after_premium,
        # Deduction (segmented)
        nar_av=ded.nar_av,
        standard_db=ded.standard_db,
        corridor_rate=ded.corridor_rate,
        gross_db=ded.gross_db,
        corr_amount=ded.corr_amount,
        discounted_db_cov1=ded.discounted_db_cov1,
        discounted_db_corr=ded.discounted_db_corr,
        discounted_db=ded.discounted_db,
        nar_cov1=ded.nar_cov1,
        nar_corr=ded.nar_corr,
        nar=ded.nar,
        coi_rate=ded.coi_rate,
        coi_charge_cov1=ded.coi_charge_cov1,
        coi_charge_corr=ded.coi_charge_corr,
        coi_charge=ded.coi_charge,
        epu_charge=ded.epu_charge,
        mfee_charge=ded.mfee_charge,
        total_deduction=ded.total_deduction,
        av_after_deduction=ded.av_after_deduction,
        # Interest
        interest_credited=intr.interest_credited,
        av_end_of_month=av,
        # End-of-month
        surrender_charge=surrender_charge,
        surrender_value=surrender_value,
        ending_db=ending_db,
        # Tracking
        premiums_ytd=prem.premiums_ytd,
        premiums_to_date=prem.premiums_to_date,
        cost_basis=prem.cost_basis,
        lapsed=lapsed,
    )
```

---

## 6. `IllustrationRates` — Rate Loader

**Module:** `core/rate_loader.py`

Pre-loads all rate arrays for a given policy's plancode and segment demographics. Wraps the `Rates` class to provide convenience access.

```python
@dataclass
class IllustrationRates:
    """Pre-loaded rate arrays for a single policy segment.
    
    All arrays are 1-indexed by policy year. Access: rates.coi[rate_year].
    """
    
    # Policy-year-based arrays
    coi: List[float] = field(default_factory=list)       # COI per $1000 of NAR
    epu: List[float] = field(default_factory=list)       # EPU per $1000 of face
    scr: List[float] = field(default_factory=list)       # Surrender charge per $1000
    mfee: List[float] = field(default_factory=list)      # Monthly fee (flat $)
    gint: List[float] = field(default_factory=list)      # Guaranteed interest rate
    tpp: List[float] = field(default_factory=list)       # Target premium load %
    epp: List[float] = field(default_factory=list)       # Excess premium load %
    poav: List[float] = field(default_factory=list)      # Percent of AV charge
    
    # Attained-age-based arrays
    corridor: List[float] = field(default_factory=list)  # Corridor factors by attained age
    
    # Single values
    mtp: float = 0.0                                     # Minimum target premium (annual per $1000)
    ctp: float = 0.0                                     # Commission target premium (annual per $1000)

def load_rates(
    policy: IllustrationPolicyData,
    config: PlancodeConfig,
) -> IllustrationRates:
    """Load all rate arrays for the policy's base segment.
    
    Uses the Rates class to fetch from UL_Rates SQL Server database.
    Rates are cached at the Rates class level.
    
    NOTE: Bonus rates (BONUSDUR, BONUSAV) are NOT loaded from the DB.
    They come from tRates_IntBonus.json via load_bonus_config().
    """
    rates_db = Rates()
    seg = policy.base_segment
    
    return IllustrationRates(
        coi=rates_db.get_rates('COI', policy.plancode, seg.issue_age, seg.rate_sex,
                               seg.rate_class, scale=1, band=seg.band) or [],
        epu=rates_db.get_rates('EPU', policy.plancode, seg.issue_age, seg.rate_sex,
                               seg.rate_class, scale=1, band=seg.band) or [],
        scr=rates_db.get_rates('SCR', policy.plancode, seg.issue_age, seg.rate_sex,
                               seg.rate_class, scale=1, band=seg.band) or [],
        mfee=rates_db.get_rates('MFEE', policy.plancode, seg.issue_age, seg.rate_sex,
                                seg.rate_class, scale=1, band=seg.band) or [],
        gint=rates_db.get_rates('GINT', policy.plancode) or [],
        tpp=rates_db.get_rates('TPP', policy.plancode, seg.rate_sex, seg.rate_class,
                               scale=1, band=seg.band) or [],
        epp=rates_db.get_rates('EPP', policy.plancode, seg.rate_sex, seg.rate_class,
                               scale=1, band=seg.band) or [],
        corridor=rates_db.get_rates('CORR', policy.plancode, seg.issue_age) or [],
        mtp=rates_db.get_mtp(policy.plancode, seg.issue_age, seg.rate_sex,
                             seg.rate_class, seg.band) or 0.0,
        ctp=rates_db.get_ctp(policy.plancode, seg.issue_age, seg.rate_sex,
                             seg.rate_class, seg.band) or 0.0,
    )
```

---

## 7. Worked Example — UE000576, Month 1 of Projection

Starting state: policy year 10 month 6, duration 114, attained age 59, AV = $11,936.84, valuation date = 2026-03-27.

**Inforce snapshot (month 0):** Interest is credited on the valuation date to roll AV to end-of-month:
```
AV = $11,936.84
interest = AV × ((1 + 0.03)^(31/365) - 1) ≈ $30.00   (March has 31 days)
av_end_of_month = $11,966.84
```

We then project **month 115** (year 10, month 7):

### Step 0: Advance Counters

```
policy_year = 10, policy_month = 7 (was 6)
duration = 115 (was 114)
attained_age = 50 + (115 - 1) // 12 = 50 + 9 = 59
rate_year = 10  (policy year for rate lookups)
date = 2016-10-27 + relativedelta(months=114) = 2026-04-27
is_anniversary = False (month 7 ≠ 1)
premiums_ytd = (carried from previous month, not reset)
```

### Step 1: Apply Premium

```
gross_premium = $150.00

# CTP split (compare against premiums YTD)
prem_ytd_before = premiums_ytd  (e.g., $900.00 after 6 months)
prem_ytd_after = $900.00 + $150.00 = $1,050.00
CTP = ~$1,242.00 (from policy data, calculated at issue)

# $1,050 < $1,242, so 100% is under target
prem_under_target = max(min($1,242 - $900, $150), 0) = $150.00
prem_over_target  = 0  (prem_ytd_after $1,050 < CTP $1,242)

# Premium load (from TPP rate table at duration 115)
target_load = $150.00 × TPP_rate[115]
excess_load = $0.00
total_load = target_load
net_premium = $150.00 - total_load

# Apply
AV_after_premium = $11,936.84 + net_premium
premiums_ytd = $1,050.00
```

### Step 2: Monthly Deduction

```
# NAR AV
nar_av = max(0, AV_after_premium)  (e.g., $12,104.84)

# Standard DB (DBO A)
standard_db = $90,000   (face amount)

# Gross DB (corridor check)
corridor_rate = CORR[attained_age=59]  (1.01 for GPT)
gross_db = max($90,000, 1.01 × $12,104.84) = max($90,000, $12,225.89) = $90,000
corr_amount = $0  (corridor does not apply — AV too low)

# Discounted DB — per segment
guaranteed_rate = 0.03
discount_factor = (1.03)^(1/12) = 1.002466...  (NOT rounded)

discounted_db_cov1 = $90,000 / 1.002466 = $89,778.40
discounted_db_corr = $0  (no corridor)
discounted_db = $89,778.40

# NAR — FIFO
nar_cov1 = max(0, $89,778.40 - $12,104.84) = $77,673.56
nar_corr = 0  (no corridor)
nar = $77,673.56

# COI (no rounding)
COI_rate = COI_rates[rate_year=10]
coi_charge_cov1 = ($77,673.56 / 1000) × COI_rate ≈ $38.28
coi_charge_corr = $0
coi_charge = $38.28

# EPU (round_near to 2 dp)
EPU_rate = EPU_rates[rate_year=10]
EPU_charge = round_near(90 × EPU_rate, 2) = $4.88

# MFEE
MFEE_charge = $5.00

# AV charge (EXECUL = 0)
AV_charge = 0

# Total
total_deduction = COI_charge + EPU_charge + MFEE_charge
AV_after_deduction = AV_after_premium - total_deduction
```

### Step 3: Interest Credit

```
# Base rate
annual_rate = current_interest_rate  (e.g., 0.0425)

# Bonus (from BonusConfig, resolved at projection start)
# EXECUL 1U143900 valuation 2026-03-27 → effective 1900-01-01 entry (bonus ON)
# bonus_dur_rate = 0.005 (duration ≥ bonus_dur_threshold)
# bonus_av_rate = 0.0025 (AV ≥ bonus_av_threshold)
# At year 10+: bonus_dur applies → annual_rate += 0.005 → 0.0475
# AV $12,000 < $100,000 threshold → bonus_av does NOT apply

# Daily compound (ExactDays method)
month_date = issue_date + relativedelta(months=duration - 1)
days = days_in_month(month_date)
days_in_year = 366 if leap_year else 365
monthly_rate = (1 + annual_rate)^(days / days_in_year) - 1

# Interest
interest = AV_after_deduction × monthly_rate
AV_end = AV_after_deduction + interest
```

### Step 4: Surrender Value

```
SCR_rate = SCR[rate_year=10]
surrender_charge = SCR_rate × 90  (units = face / 1000)
surrender_value = max(AV_end - surrender_charge, 0)
```

---

## 8. Validation Strategy

### 8.1 Source of Truth

The RERUN workbook's **CalcEngine** sheet contains month-by-month calculated values for loaded policies. For UE000576, the row at duration 115 (or the equivalent policy year 10 month 7) provides expected values for every intermediate calculation.

### 8.2 Validation Points

| Value | Source Column | Tolerance |
|---|---|---|
| Net premium | CalcEngine | ± $0.01 |
| Premium load | CalcEngine | ± $0.01 |
| Death benefit | CalcEngine | ± $0.01 |
| NAR (total) | CalcEngine | ± $0.01 |
| COI charge (total) | CalcEngine | ± $0.01 |
| EPU charge | CalcEngine | ± $0.01 |
| MFEE | CalcEngine | ± $0.01 |
| Total deduction | CalcEngine | ± $0.01 |
| Interest credited | CalcEngine | ± $0.05 (daily compound rounding) |
| End-of-month AV | CalcEngine | ± $0.10 |
| Surrender value | CalcEngine | ± $0.10 |

### 8.3 Validation Script

`scripts/run_m1.py` will:

1. Load UE000576 via `build_illustration_data()`
2. Run `engine.project(policy, months=12)`
3. Print every `MonthlyState` field in a formatted table (with segmented breakdown)
4. Export debug Excel with pipeline-ordered columns and section headers
5. Compare against expected values from the workbook
6. Supports `--dbo` (A/B/C), `--av` (override), `--rate` (override) CLI arguments

---

## 9. Edge Cases (M1 Scope)

| Case | Handling |
|---|---|
| AV goes negative after deduction | Lapse at end of month |
| NAR is negative (AV > DB) | Set NAR = 0, COI = 0 for that segment |
| Corridor raises DB | Corridor segment gets its own discounted DB, NAR, and COI |
| Corridor does not trigger | `corr_amount = 0`, all NAR allocated to cov1, `coi_charge_corr = 0` |
| All NAR in corridor (AV > face) | `nar_cov1 = 0` via FIFO, all NAR in `nar_corr` |
| Rate array shorter than needed year | Use last available rate (`_safe_rate` clamps index) |
| Premium = 0 (zero premium what-if) | Skip premium step, proceed to deduction |
| Bonus config: all zeros | No bonus applied (e.g., post-2018 effective date for EXECUL) |
| Bonus config: not found | Raises error — plancode must have entry in tRates_IntBonus.json |
| SCR at 0 (past surrender charge period) | Surrender charge = 0, SV = AV |
| Duration exceeds maturity age | Stop projection |

---

## 10. Module Dependencies

```
suiteview.illustration.core.calc_engine
├── suiteview.illustration.core.premium_handler
├── suiteview.illustration.core.monthly_deduction
├── suiteview.illustration.core.interest_calc
├── suiteview.illustration.core.bonus_rates.BonusConfig
│   └── suiteview.illustration.core.bonus_rates.load_bonus_config()
│       └── suiteview.illustration.plancodes.tRates_IntBonus.json
├── suiteview.illustration.core.rate_loader
│   └── suiteview.core.rates.Rates          (existing)
├── suiteview.illustration.models.calc_state.MonthlyState
├── suiteview.illustration.models.policy_data.IllustrationPolicyData
└── suiteview.illustration.models.constants.PlancodeConfig

suiteview.illustration.core.illustration_policy_service
└── suiteview.core.policy_service.get_policy_info   (existing)
    └── suiteview.polview.models.PolicyInformation   (existing)
```
