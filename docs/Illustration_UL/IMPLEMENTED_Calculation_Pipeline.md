# UL Illustration - Implemented Calculation Pipeline

**Purpose:** describe the calculation pipeline that is implemented in code today, using the current Python engine as the source of truth.

**Primary control path:** `suiteview.illustration.core.calc_engine.IllustrationEngine`

**Key observation:** the implementation is materially ahead of the older M1-only spec. The live engine currently includes:

- inforce monthly-deduction reconciliation
- loan capitalization and loan interest accrual
- projected cash-flow inputs (premium overrides, loans, repayments, withdrawals)
- rider and benefit charges inside monthly deduction
- shadow account / CCV calculation
- safety net and shadow-based lapse protection
- end-of-month surrender charge and lapse testing

This document is intended to show the pipeline that exists now so the next round of work can focus on the remaining gaps instead of re-documenting already-implemented pieces.

## 1. Source Modules

The pipeline is distributed across these modules:

- `suiteview/illustration/core/calc_engine.py` - month orchestration, inforce row, surrender charge, lapse logic
- `suiteview/illustration/core/premium_handler.py` - premium split, premium loads, net premium
- `suiteview/illustration/core/monthly_deduction.py` - death benefit, NAR, COI, EPU, fees, rider and benefit charges
- `suiteview/illustration/core/interest_calc.py` - credited interest, bonus interest, impaired interest on loaned AV
- `suiteview/illustration/core/loan_handler.py` - anniversary capitalization and in-arrears loan accrual
- `suiteview/illustration/core/input_compiler.py` - converts future inputs into per-month buckets
- `suiteview/illustration/core/input_applier.py` - applies early cash flows before premium/deduction, excluding fixed new-loan allocation
- `suiteview/illustration/core/shadow_calc.py` - parallel CCV / shadow account calculation
- `suiteview/illustration/debug/excel_export.py` - exposes the pipeline field order used for debug export

## 2. High-Level Flow

The engine runs in two phases:

1. Build an inforce snapshot row from current policy values.
2. Project forward one month at a time until the requested duration or lapse.

At a high level, each projected month runs this sequence:

```text
0. Advance counters
0b. Capitalize loans at anniversary
0c. Apply external cash-flow inputs
1. Apply premium
2. Calculate monthly deduction
2b. Allocate new fixed loan between preferred and regular buckets
3. Credit interest
3b. Accrue loan interest
3c. Calculate shadow account
3d. Update safety net / lapse-protection values
4. Calculate surrender value and lapse status
```

That sequence is the controlling implementation path in `IllustrationEngine.process_month()`.

## 3. Inforce Snapshot Row

Before any projected month is processed, the engine builds a month-0 row representing the current inforce state.

### 3.1 Purpose

The inforce row is not just a copy of database values. It recalculates the current month's deduction and interest so the projection starts from a consistent end-of-month state.

### 3.2 Inforce Inputs

The row uses current policy data from `IllustrationPolicyData`, especially:

- `account_value`
- `system_monthly_deduction`
- `system_coi_charge`
- `system_expense_charge`
- `system_other_charge`
- current loan balances
- `premiums_ytd`, `premiums_paid_to_date`, `withdrawals_to_date`
- `accumulated_mtp`
- shadow account starting value

### 3.3 Inforce Reconciliation Logic

The engine treats the current account value as an after-deduction value from CyberLife and reconstructs the pre-deduction balance:

```text
md_check_av_before_deduction = account_value + system_monthly_deduction
```

It then reruns monthly deduction against that reconstructed balance:

```text
ded0 = calculate_deduction(md_check_av_before_deduction, ...)
```

It separately credits interest to the actual after-deduction AV:

```text
intr0 = credit_interest(account_value, ...)
```

The row also stores audit values so the calculated deduction can be compared to the system deduction:

- `md_check_calculated_deduction`
- `md_check_deduction_variance`
- `md_check_calculated_av_after_deduction`
- `md_check_av_variance`

### 3.4 Inforce-Only Companion Calculations

The inforce row also performs:

- loan accrual for the current month
- initial shadow-account calculation using `is_inforce=True`
- safety-net evaluation
- surrender charge and surrender value calculation

This means the inforce row already contains almost the full post-deduction, post-interest state needed for forward projection.

## 4. Monthly Projection Pipeline

### 4.1 Step 0 - Advance Counters

The engine advances policy counters before any dollar calculations.

Implemented logic:

```text
if policy_month == 12:
    next_year = policy_year + 1
    next_month = 1
else:
    next_year = policy_year
    next_month = policy_month + 1

duration = previous_duration + 1
attained_age = issue_age + (duration - 1) // 12
month_date = issue_date + relativedelta(months=duration - 1)
is_anniversary = (next_month == 1)
```

On anniversary, premium year-to-date resets to zero:

```text
premiums_ytd = 0.0 if is_anniversary else state.premiums_ytd
```

The account value entering the month is the prior month's end-of-month AV:

```text
av = state.av_end_of_month
```

### 4.2 Step 0b - Loan Capitalization

This step is implemented before any new cash flow or premium is applied.

At policy anniversary only:

```text
principal += accrued_interest
accrued_interest = 0
```

Outside anniversary months, balances carry through unchanged.

Notes:

- regular, preferred, and variable loan buckets are carried separately
- capitalization is handled by `capitalize_loans()`
- the projection reads prior month end balances and converts them into beginning-of-month balances for the new month

### 4.3 Step 0c - External Cash-Flow Inputs

This is implemented for projected months through `compile_month_inputs()` and `apply_cash_flow_inputs()`.

Supported projected cash flows:

- scheduled premiums by policy year and modal frequency
- unscheduled dated premiums
- fixed loans
- variable loans
- loan repayments
- withdrawals

This step occurs before premium and deduction.

Implemented formulas:

```text
vbl_loan_princ += month_inputs.variable_loan
```

Loan repayments are applied in this bucket order:

1. regular accrued
2. regular principal
3. preferred accrued
4. preferred principal
5. variable accrued
6. variable principal

Withdrawals are limited to available AV:

```text
applied_withdrawal = min(max(requested_withdrawal, 0), max(av, 0))
av = av - applied_withdrawal
withdrawals_to_date += applied_withdrawal
```

These future cash-flow inputs affect projected months only. They do not alter the inforce snapshot row.

Fixed new-loan requests are deferred to the post-deduction policy-values slice so the engine can determine how much qualifies as preferred loan.

### 4.4 Step 1 - Apply Premium

Premium processing is handled by `apply_premium()`.

The month's gross premium is:

- `policy.modal_premium`, unless a compiled input overrides it
- if no premium is due and no override exists, the step becomes a pass-through

Target versus excess split:

```text
prem_ytd_before = premiums_ytd
prem_ytd_after = prem_ytd_before + gross_premium

prem_under_target = max(min(ctp - prem_ytd_before, gross_premium), 0)
prem_over_target = max(min(gross_premium, prem_ytd_after - ctp), 0)
```

Premium loads:

If premium load is table-driven:

```text
target_load = prem_under_target * TPP[rate_year]
excess_load = prem_over_target * EPP[rate_year]
```

If premium load is a flat configured percentage:

```text
target_load = gross_premium * flat_pct
excess_load = 0
```

If `prem_flat_load > 0`, that flat dollar load is added whenever gross premium is positive.

```text
total_premium_load = target_load + excess_load + flat_load
net_premium = gross_premium - total_premium_load
av_after_premium = av_beginning + net_premium
```

Tracking updates:

- `premiums_ytd`
- `premiums_to_date`
- `cost_basis`

All three are increased by gross premium, not net premium.

### 4.5 Step 2 - Monthly Deduction

Monthly deduction is handled by `calculate_deduction()` and is the densest part of the pipeline.

NAR AV:

```text
nar_av = max(0, av_after_premium)
```

Standard death benefit:

```text
DBO A: standard_db = total_face
DBO B: standard_db = total_face + nar_av
DBO C: standard_db = total_face + max(0, premiums_to_date - withdrawals_to_date)
```

Corridor test and gross death benefit:

```text
gross_db = max(standard_db, corridor_rate * nar_av)
corr_amount = gross_db - standard_db
```

Discounted death benefit by coverage:

```text
discount_factor = round((1 + guaranteed_interest_rate) ** (1 / 12), 7)
discounted_db_segment = segment_db / discount_factor
discounted_db_corr = corr_amount / discount_factor
```

Implementation details:

- multiple base segments are supported
- DBO B or C additions are applied to the first segment
- corridor is treated as a separate coverage component

NAR allocation is FIFO:

1. base coverage 1
2. each additional base segment
3. corridor segment last

Implemented formula per segment:

```text
segment_nar = max(0, discounted_db_segment - remaining_av)
remaining_av = max(0, remaining_av - discounted_db_segment)
```

Corridor NAR is then:

```text
nar_corr = max(0, discounted_db_corr - remaining_av)
```

COI charges:

- coverage segments, riders, and benefits can use anniversary logic tied to their own issue dates
- raw COI is adjusted for table ratings and flat extras when active

```text
adjusted_coi_rate = raw_rate * (1 + table_rating_factor * table_rating) + flat_extra / 12
segment_coi_charge = (segment_nar / 1000) * adjusted_segment_coi_rate
coi_charge_corr = (nar_corr / 1000) * adjusted_base_coi_rate
coi_charge = sum(segment_coi_charges) + coi_charge_corr
```

EPU charges:

Table-driven EPU:

```text
segment_epu_charge = (segment_basis / 1000) * segment_epu_rate
```

Flat-configured EPU:

```text
segment_epu_charge = epu_flat * segment_units
```

Monthly fee and AV charge:

```text
if MFEE == "Table":
    mfee_charge = MFEE[rate_year]
else:
    mfee_charge = configured_flat_amount

if POAV == "Table":
    av_charge = max(0, av_after_premium * poav_rate)
else:
    av_charge = 0
```

Riders and benefits are implemented, not just planned.

Rider charges:

```text
rider_charge = rider.units * rider_rate
```

Premium waiver benefits (`benefit_type == "3"`) use:

```text
benefit_amount = max(monthly_mtp, base_deduction + rider_charges + non_pw_benefit_charges)
pw_charge = adjusted_rate * benefit_amount
```

Other benefits use:

```text
charge = benefit.units * adjusted_rate
```

Total deduction:

```text
base_deduction = coi_charge + epu_charge + mfee_charge + av_charge
total_deduction = base_deduction + benefit_charges + rider_charges
av_after_deduction = av_after_premium - total_deduction
```

### 4.5b Step 2b - New Fixed Loan Allocation

After monthly deduction, the engine allocates any fixed new-loan request between preferred and regular loan principal.

Preferred loan capacity is determined using:

```text
preferred_capacity = max(AV_after_MD - current_policy_debt - (PremTD - AccumWDs), 0)
```

Where:

- `AV_after_MD` is the account value after monthly deduction
- `current_policy_debt` is the current loan balance before the new fixed loan is added
- `PremTD` is premiums to date after this month's premium
- `AccumWDs` is withdrawals to date after any applied withdrawal inputs

Allocation rule:

```text
preferred_amount = min(requested_fixed_loan, preferred_capacity)
regular_amount = requested_fixed_loan - preferred_amount
```

If preferred loans are not available on the policy, the full fixed-loan request is added to regular loan principal.

### 4.6 Step 3 - Interest Credit

Interest processing is handled by `credit_interest()`.

Base and bonus annual rate:

```text
annual_rate = policy.current_interest_rate
effective_annual_rate = annual_rate + bonus_rate
```

If the plancode uses `ExactDays`, the current implementation uses a fixed 365/12 convention in the exponent:

```text
monthly_rate = (1 + effective_annual_rate) ** (365 / 12 / 365) - 1
```

Otherwise:

```text
monthly_rate = (1 + effective_annual_rate) ** (1 / 12) - 1
```

The function still records actual calendar `days_in_month`, but those days are not used in the base credited-interest exponent under `ExactDays`.

Loan-impaired interest:

```text
loaned_av = min(total_loaned_balance, av_after_deduction)
free_av = av_after_deduction - loaned_av

interest = free_av * full_monthly_rate
         + reg_loaned_av * reg_credit_monthly
         + pref_loaned_av * pref_credit_monthly
```

If no loans exist, the entire AV receives the standard monthly rate.

End-of-month AV:

```text
av_end_of_month = av_after_deduction + interest_credited
```

### 4.7 Step 3b - Loan Interest Accrual

This is handled by `accrue_loan_interest()` after interest credit.

Only in-arrears loan types accrue monthly charges here. Advance loans pass through unchanged.

```text
regular_accrual = regular_principal * loan_charge_rate_guar * days_in_month / 365
preferred_accrual = preferred_principal * pref_loan_charge_rate_guar * days_in_month / 365
```

Variable loan accrual is currently hard-coded to zero in this function.

The accrued charges are added to the accrued buckets, not principal.

### 4.8 Step 3c - Shadow Account / CCV

The shadow calculation runs as a parallel mini-engine through `calculate_shadow()`.

If `policy.has_shadow_account` is false, the function returns zeros and shadow protection is effectively disabled.

The shadow side calculates its own:

- beginning AV
- target premium split
- premium loads
- net premium
- shadow death benefit
- shadow COI
- shadow EPU
- shadow MFEE
- shadow monthly deduction
- shadow interest
- ending shadow account value
- shadow value less debt

Core formulas:

```text
shadow_nar_av = shadow_bav - shadow_wd_charges + shadow_net_prem

if DBO B:
    shadow_db = shadow_nar_av + shadow_sa
else:
    shadow_db = shadow_sa

shadow_nar = shadow_db / (1 + shadow_dbd_rate) ** (1 / 12) - shadow_nar_av
shadow_coi = round_half_up((shadow_nar / 1000) * shadow_coi_rate, 2)
shadow_md = shadow_coi + shadow_epu + shadow_mfee + shadow_rider_charges

if is_inforce:
    shadow_av = policy.shadow_account_value
else:
    shadow_av = shadow_nar_av - shadow_md

shadow_eff_rate = (1 + shadow_int_rate) ** (days_in_month / 365) - 1
shadow_interest = max(0, shadow_eff_rate * shadow_av)
shadow_eav = round_half_up(shadow_av + shadow_interest, 2)
shadow_eav_less_debt = shadow_eav - policy_debt
```

`shadow_rider_charges` is explicitly marked as not yet implemented and currently stays at zero.

### 4.9 Step 3d - Safety Net / Lapse Protection Tracking

This step determines whether lapse protection is keeping the policy alive even when account value is weak.

Monthly MTP is currently taken from policy data and truncated to cents before accumulation:

```text
monthly_mtp = trunc(policy.mtp * 100) / 100
accumulated_mtp = prior_accumulated_mtp + monthly_mtp
accum_mtp_less_prem = (premiums_to_date - withdrawals_to_date - policy_debt) - accumulated_mtp
```

Safety net is active when both are true:

- accumulated premiums less withdrawals and debt are at least accumulated MTP
- the policy is still within the safety-net period or MAP cease date

After the safety-net period, shadow protection can keep the policy alive if:

- the policy has a shadow account
- the policy is past the safety-net period
- `shadow_eav_less_debt > 0`

### 4.10 Step 4 - End-of-Month Values and Lapse Test

The engine closes each month with surrender and lapse calculations.

Surrender charge is calculated by coverage segment when segments exist:

```text
segment_surrender_charge = segment_scr_rate * segment.units
surrender_charge = sum(segment_surrender_charges)
```

If no segment list exists, the fallback is:

```text
surrender_charge = scr_rate * policy.units
```

Surrender value:

```text
surrender_value = max(av_end_of_month - surrender_charge - policy_debt, 0)
```

Ending death benefit:

```text
ending_db = deduction_result.gross_db
```

Lapse test:

```text
positive_sv = (lapse_value == "SV" and surrender_value > 0)
av_loans_test = (lapse_value == "AV" and av_end_of_month - policy_debt > 0)
any_protection = snet_active or shadow_protection or positive_sv or av_loans_test
lapsed = prior_lapsed or not any_protection
```

Once `lapsed` becomes true, later states remain lapsed.

## 5. Output State Produced Each Month

Each month returns a `MonthlyState` carrying:

- counters and dates
- beginning-of-month loan set
- premium-stage values
- deduction-stage values
- interest-stage values
- end-of-month loan balances
- surrender values and ending death benefit
- cumulative premium, withdrawal, cost basis, interest, and charge tracking
- shadow-account fields
- safety-net status
- final lapse flag

The pipeline order used for debug export is also encoded in `suiteview/illustration/debug/excel_export.py`.

## 6. What Appears Implemented Versus Still Incomplete

### 6.1 Clearly Implemented in Code

- inforce reconciliation row
- premium split and premium loads
- DBO A, B, and C handling
- multi-segment base coverage support in deduction and surrender charge logic
- COI, EPU, MFEE, AV charge
- rider and benefit charges during deduction
- loan capitalization and in-arrears accrual
- projected loans, repayments, withdrawals, and premium overrides
- bonus interest logic
- shadow account / CCV calculation
- safety net and shadow-based lapse protection
- surrender value and lapse determination

### 6.2 Explicitly Incomplete or Partial in Current Code

- shadow rider charges are marked not implemented and remain zero
- variable loan accrual is not implemented in `accrue_loan_interest()`
- base interest `ExactDays` mode records actual month days but uses a fixed 365/12 exponent for the credited-interest rate calculation
- some spec-era items such as full 7702, TAMRA, deemed cash value, GCO logic, and broader policy change processing are not part of this monthly path

## 7. Recommended Next Review Questions

Based on the current implementation, the next useful review questions are:

1. Is the current `ExactDays` interest implementation intentional, or should credited interest use actual `days_in_month` like the shadow side does?
2. Do we want projected withdrawals and loans to trigger any additional business rules beyond simple AV and debt movement?
3. Should shadow rider charges now be implemented, or is zero still acceptable for the products currently in scope?
4. Is variable-loan accrual needed for any active plancodes in the first rollout set?
5. Should the older `SPEC_Calculation.md` be revised to match the current engine, or kept as milestone history?

## 8. Bottom Line

The current engine is no longer just a basic monthly AV projection. It already behaves like a broader inforce illustration pipeline with support for deduction detail, loans, cash-flow inputs, shadow values, and multiple lapse-protection paths. The main next-step work looks less like building the basic pipeline and more like closing the remaining edge cases, validating formulas against RERUN, and deciding which partial areas need to be promoted to full production behavior.
