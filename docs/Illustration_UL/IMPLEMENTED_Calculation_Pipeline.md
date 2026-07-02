# UL Illustration - Implemented Calculation Pipeline

**Purpose:** describe the calculation pipeline that is implemented in code today, using the current Python engine as the source of truth.

**Primary control path:** `suiteview.illustration.core.calc_engine.IllustrationEngine`

**Last reviewed:** 2026-06-21

**Key observation:** the implementation is materially ahead of the older M1-only spec. The live engine currently includes:

- inforce monthly-deduction reconciliation
- loan capitalization (arrears AND interest-in-advance) and loan interest accrual
- the full premium-acceptance allowance chain (CalcEngine NC..NZ) with guideline / 7-pay caps, lumpsum handling, and optional premium levelizing
- **Apply Premium to Loan First** (`sInput_ApplyPremToLoan`): the requested premium repays the loan before funding the account value
- a full withdrawal stage (CalcEngine AX..BU — max-net, corridor, partial surrender charge, gross/net trackers)
- projected cash-flow inputs (premium overrides, loans, repayments, withdrawals)
- future policy-change inputs: face amount changes, DB option flips (A↔B level-DB mechanics), rate class / table-rating changes, rider keep/change/drop
- per-component MTP / CTP (target-premium) detail snapshots, recomputed on coverage change
- guideline premium accumulation, force-out, and GP exception premium
- standalone GLP/GSP/7-pay calculation utilities and a Min-Level-to-Exception premium solver
- rider and benefit charges inside monthly deduction (incl. NAR-split / ratchet-banding COI)
- shadow account / CCV calculation
- safety net, shadow, AV, exception, and SV lapse-protection paths
- end-of-month surrender charge, ending death benefit, and lapse testing
- CyberLife monthliversary timing used by PolView GLP forecasts
- RERUN comparison tooling for validating engine output against the workbook CalcEngine

This document is intended to show the pipeline that exists now so the next round of work can focus on the remaining gaps instead of re-documenting already-implemented pieces.

> **Recent changes (2026-06):** advance (interest-in-advance) loans are now fully
> modeled (capitalization + repayment gross-up, cents-rounded); the full NC..NZ
> premium-acceptance chain replaced the old single guideline cap; Apply-Premium-to-Loan,
> the real withdrawal stage, the GP exception premium, corridor-DB whole-dollar
> truncation, and the loan surrender-value cap all landed. The "advance loans out of
> scope" and "surrender value floored at 0" statements in older revisions are obsolete.

## 1. Source Modules

The pipeline is distributed across these modules:

- `suiteview/illustration/core/calc_engine.py` - month orchestration, inforce row, surrender charge, lapse logic
- `suiteview/illustration/core/guideline_calc.py` - standalone GLP/GSP calculators and attained-age policy-change delta logic
- `suiteview/illustration/core/commutation.py` - commutation functions, mortality table helpers, substandard adjustments, and Fackler reserve utilities
- `suiteview/illustration/core/rate_loader.py` - current and guaranteed COI/rate loading into `IllustrationRates`
- `suiteview/illustration/core/premium_handler.py` - premium split, premium loads, net premium
- `suiteview/illustration/core/premium_allowance.py` - the NC..NZ premium-acceptance allowance chain (guideline/7-pay caps, lumpsum, levelizing, loan-repay diversion)
- `suiteview/illustration/core/target_premium.py` - MTP / CTP per-component target-premium computation and display snapshots
- `suiteview/illustration/core/withdrawal_handler.py` - the AX..BU withdrawal stage (max-net, corridor, partial surrender charge, gross/net trackers, SA-reducing decreases)
- `suiteview/illustration/core/monthly_deduction.py` - death benefit, NAR, COI (incl. NAR-split/ratchet banding), EPU, fees, rider and benefit charges
- `suiteview/illustration/core/interest_calc.py` - credited interest, bonus interest, impaired interest on loaned AV
- `suiteview/illustration/core/loan_handler.py` - anniversary capitalization (arrears roll-in AND advance gross-up), in-arrears accrual, advance payoff/repayment gross-up
- `suiteview/illustration/core/input_compiler.py` - converts future inputs into per-month buckets
- `suiteview/illustration/core/input_applier.py` - applies early cash flows (variable loans, repayments, Apply-Prem-to-Loan diversion) before premium/deduction, excluding fixed new-loan allocation
- `suiteview/illustration/core/solve_level_to_exception.py` - solves the minimum level premium that keeps a GPT policy in force to maturity (riding the GLP exception period); loan-capable via Apply-Prem-to-Loan
- `suiteview/illustration/core/shadow_calc.py` - parallel CCV / shadow account calculation
- `suiteview/polview/services/glp_exception.py` - PolView GLP exception and policy-support premium forecast consumer
- `suiteview/illustration/debug/excel_export.py` - exposes the pipeline field order used for debug export
- `tools/rerun_com.py`, `tools/run_engine_case.py`, `tools/compare_case.py`, and `tools/calc_compare_map.py` - RERUN workbook dump, engine dump, and grouped comparison harness

## 2. High-Level Flow

The engine runs in two phases:

1. Build an inforce snapshot row from current policy values.
2. Project forward one month at a time until the requested duration or lapse.

At a high level, the normal illustration path is being structured to follow the RERUN inforce illustration workbook sequence:

```text
1. Update date, policy year/month, and attained age
2. Gather beginning values: AV, PremTD, coverage amounts, surrender charge context
3. Withdrawal processing (full AX..BU stage: max-net, corridor, partial SC, SA-reducing decreases)
4. DB option change processing (future change wiring + A↔B level-DB mechanics)
5. Face increase processing (future policy-change input)
6. Face decrease processing (future policy-change input)
7. Coverage After Change: active coverages, original/current amount, coverage durations, rate/substandard changes
8. Minimum Target Premium calculation/accumulation
9. Commission Target Premium calculation/accumulation
10. 7702 / 7702A calculations (GLP/GSP accumulation, force-out, and the NC..NZ premium-acceptance chain)
11. Loan capitalization and repayment (arrears roll-in + advance gross-up; Apply-Prem-to-Loan; projected repayments)
12. Apply premium and premium load
13. Monthly deduction
14. GP exception premium (implemented, in-engine)
15. Policy values: account value, surrender value, and new loan processing (with the loan SV cap)
16. Accumulation: interest crediting, loan interest charges, and ending values
17. Shadow account processing
18. Testing: guideline/7-pay caps, lapse via SV/shadow/SNET/AV/exception now; full MEC flagging later
19. Deemed Cash Value (later)
```

That sequence is the controlling implementation path in `IllustrationEngine.process_month()`.

The engine now supports two timing modes:

- `ProjectionTiming.ILLUSTRATION` - normal illustration timing: cash flows and premium are applied before deduction, interest is credited after deduction.
- `ProjectionTiming.CYBERLIFE_MONTHLIVERSARY` - PolView forecast timing: interest is credited from the current value first, then guideline force-out, monthliversary cash flows, premium, deduction, loan allocation, and loan accrual run. This mode also keeps projecting with `stop_on_lapse=False` for GLP forecast views.

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

The normal illustration pipeline below describes `process_month()`. The GLP Exception and Policy Support forecasts use the same state objects and most of the same helper functions, but run through `process_cyberlife_monthliversary()` so the forecast rows line up with CyberLife monthliversary behavior. In that admin-alignment timing mode, accumulation/interest happens at the beginning of the monthly slice rather than near the end.

### 4.1 Step 1 - Update Date, Year, Month, and Attained Age

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

### 4.2 Step 2 - Gather Beginning Values

The beginning values for the month come from the prior `MonthlyState` plus static policy data:

- beginning AV is `state.av_end_of_month`
- beginning premium-to-date is `state.premiums_to_date`
- beginning cost basis is `state.cost_basis`
- beginning loan balances come from prior end-of-month loan buckets
- coverage amounts come from `IllustrationPolicyData.segments`, riders, and benefits
- surrender charge context comes from policy segments plus `segment_scr`/`scr` rate schedules

Surrender charge itself is still calculated near the policy-values/testing stage because it depends on current duration, segment coverage year, ending AV, and policy debt.

### 4.3 Step 3 - Withdrawal Processing

Withdrawals now run through a dedicated stage, `withdrawal_handler.compute_withdrawal()`
(CalcEngine AX..BU), called from `_process_withdrawal()` before the dated policy
changes and the guideline force-out.

Valuation-date injection point:

- `withdrawals_to_date` / WithdrawalTD is injected in this section

The stage models, rather than a simple `min(requested, AV)`:

- the **maximum net withdrawal** allowed (against AV less the MD holdback and a
  minimum-balance floor, or the full AV when loan-payoff-by-WD is allowed)
- the **gross** withdrawal (net plus the withdrawal fee and any corridor add-on)
- whether the withdrawal **reduces the specified amount** (DBO A face decrease) and
  the **partial surrender charge** on that decrease
- net / gross withdrawal-to-date trackers and the cost-basis reduction

A specified-amount-reducing withdrawal also re-solves the guideline premiums for the
month (it moves coverage before the dated changes do), so it wins the "first instance"
tie on the month's guideline recalc.

### 4.4 Step 4 - DB Option Change Processing

Future DB option change events are now consumed from `IllustrationInputSet.policy_changes`.
When a `PolicyChangeEvent(kind=DB_OPTION, ...)` reaches its effective month, the
engine mutates the private projection copy of `policy.db_option` before monthly
deduction reads the death-benefit option.

Valuation-date injection point:

- death benefit option is injected at the end of this section

The current engine reads `policy.db_option` from `IllustrationPolicyData` when monthly deduction calculates standard death benefit. The future-change implementation is intentionally minimal: it flips the option code. RERUN's more nuanced A-to-B/B-to-A mechanics, where specified amount may be adjusted so the death benefit stays level at the change, are not fully implemented yet.

### 4.5 Steps 5-6 - Face Increase and Decrease Processing

Future face amount events are now consumed from `IllustrationInputSet.policy_changes`.
When any future policy changes are present, `IllustrationEngine.project()` deep-copies
the policy so the projection can mutate private segment state without changing the
caller-owned `IllustrationPolicyData`. Changes are bucketed by projection duration
and applied before coverage, deduction, surrender, and interest calculations for the
effective month.

Face decreases reduce existing coverage segments newest-first:

- segment `face_amount` and `units` are reduced in place
- the decreased coverage's surrender charge is deducted from AV in the change month
- the segment is re-banded to the remaining current face amount and COI/EPU rates are reloaded
- benefit COI rates are reloaded using the base segment's current band

Face increases append a new base `CoverageSegment`:

- the new segment's issue date is the change date
- issue age is the attained age at the change
- units are based on the increase amount and the base segment's value-per-unit
- banding uses the new total specified amount, matching the CyberLife/RERUN behavior observed so far
- COI, EPU, and SCR schedules for the new segment are loaded on the fly

On any specified-amount change the engine now recomputes the target premiums (vMTP/vCTP) from rates via `target_premium.py`, recalculates GLP/GSP by the attained-age delta method (guaranteed-COI commutation, monthly-cent floor), and on a material change (face increase, DBO B-to-A) restarts the 7-pay period and recomputes the 7-pay level. `PolicyChangeEvent.metadata` can inject RERUN's recalculated guideline values (`new_glp`/`new_gsp`/`new_7pay`) for mechanics-only validation. Validated EXACT vs RERUN on U0688012 (increase, decrease, DBO A-to-B at the year-9 anniversary; all comparison groups 0.0 over 40 months). Still open: the engine's own guideline recalc calibration vs RERUN's Guideline_Premiums calculator, B-to-A validation, and mid-year (non-anniversary) AccumGLP pro-ration.

### 4.6 Step 7 - Coverage After Change

This section shows all active coverages after the face amount and DB option change sections have run.

It owns:

- active coverage rows
- original coverage amount
- current coverage amount
- duration tracked by coverage anniversary
- separate duration tracked by policy anniversary
- rate class changes
- substandard changes

Valuation-date injection point:

- coverage amounts are injected in this section
- rate class and substandard values are injected and updated in this section

The current engine reads already-built or policy-change-mutated coverage state from `IllustrationPolicyData.segments`, riders, benefits, and substandard/rate attributes. The monthly deduction path then uses those coverage-level values for death benefit discounting, NAR allocation, COI, EPU, rider charges, benefit charges, and surrender charge by coverage.

### 4.7 Step 8 - Minimum Target Premium Calculation / Accumulation

Valuation-date injection point:

- AccumMTP is injected in this section

Monthly MTP is currently taken from policy data and truncated to cents:

```text
monthly_mtp = trunc(policy.mtp * 100) / 100
accumulated_mtp = prior_accumulated_mtp + monthly_mtp
```

The final safety-net test still waits until policy debt is known:

```text
accum_mtp_less_prem = (PremTD - withdrawals_to_date - policy_debt) - accumulated_mtp
```

### 4.8 Step 9 - Commission Target Premium Calculation / Accumulation

Valuation-date injection point:

- CTP is injected in this section

CTP is currently used inside `apply_premium()` to split the month's gross premium into target and excess premium portions for premium-load purposes.

```text
prem_under_target = max(min(ctp - prem_ytd_before, gross_premium), 0)
prem_over_target = max(min(gross_premium, prem_ytd_after - ctp), 0)
```

Premium YTD resets on policy anniversary and then accumulates by gross premium.

### 4.9 Step 10 - 7702 / 7702A Currently Implemented Slice

Valuation-date injection points:

- GLP
- GSP
- AccumGLP
- TAMRA premium
- TAMRA start date
- Lowest7YearFace

The monthly projection path consumes loaded policy GLP/GSP values and covers GLP accumulation, force-out tracking, and the full NC..NZ premium-acceptance chain (guideline + 7-pay capping at acceptance). What is still missing is 7702A **MEC determination/flagging** and the CVAT Necessary-Premium Test — the cap enforces the limits but no MEC status is surfaced.

Guideline premium accumulation is separated from force-out application:

```text
accumulated_glp = prior_accumulated_glp + (policy.glp if is_anniversary else 0)
```

Before cash-flow inputs and premium are applied, the engine compares the existing premium basis to the guideline limit, which is the **greater of GSP and accumulated GLP** (CalcEngine `KV = MAX(KS, KU)`):

```text
guideline_limit = max(gsp, accumulated_glp)
forceout = min(max(0, account_value_before_premium),
               max(0, (premiums_to_date - withdrawals_to_date) - guideline_limit))
withdrawals_after_forceout = withdrawals_to_date + forceout
account_value_after_forceout = account_value_before_premium - forceout
```

The force-out is capped by available account value (`KX`), disabled when TEFRA conformance is off, for CVAT policies, or once exception mode is on (so an exception premium is not immediately clawed back). Accumulated GLP stops growing at attained age ≥ 100 (`KU`). This happens before projected cash-flow inputs and before the premium stage in both normal illustration timing and CyberLife monthliversary timing.

**Premium capping at acceptance** is now the full CalcEngine `NC..NZ` allowance
chain in `premium_allowance.compute_premium_allowances()` (replacing the old
single-cap helper). For each month it computes, column-for-column:

- GP / NPT / TAMRA allowances *before any premium* (NC/ND/NE) and the Annual Cap (NF)
- the post-1035 allowances (NG..NK; the 1035 exchange itself is not yet modeled, so
  the "1" allowances equal the "0" allowances)
- the **lumpsum / unscheduled** premium applied first against the annual cap, reducing
  the room left for the scheduled premium (NL/NM), and the post-lumpsum allowances (NN..NQ)
- the per-mode **level** allowances (NR BOY / NS EOY / NT NPT / NU GP) and the
  **Scheduled Prem Cap** (NV), locked at the start of each policy year and carried forward
- **levelizing** (NW/NX, `IllustrationOptions.levelizing_premium`): when a cap binds,
  spread the allowed premium evenly across the year's modal payments instead of billing
  each in full until the annual room runs out mid-year — off when the policy carries a loan
- the scheduled premium less any loan repayment (NY) and the final accepted scheduled
  premium (NZ)

The chain is gated by `IllustrationOptions.conform_to_tefra` / `conform_to_tamra`, honors
the TAMRA 7-pay window with a **material-change reset** (a face increase or B→A restarts
the period) and an inforce-MEC bypass, and handles the BOY/EOY split when the 7-pay
anniversary falls mid-policy-year. The loan-repay diversion (MH/MI/leftover) from
Apply-Premium-to-Loan feeds NL/NY here. Still stubbed: the 1035 exchange and the CVAT
Necessary-Premium (vNPT_Premium / LI).

Currently implemented:

- GLP accumulation with the attained-age-100 stop
- GSP-floored guideline limit and AV-capped force-out
- the full NC..NZ premium-acceptance chain (guideline / 7-pay caps, lumpsum, levelizing), with TEFRA / TAMRA toggles
- accumulated GLP, guideline limit, force-out, and the per-column allowance fields on monthly rows (surfaced in the Values tab "Apply Premium" group)

Separately, `guideline_calc.py` implements the standalone GLP/GSP calculation surface:

- `calculate_glp()` and `calculate_gsp()` use commutation / present-value formulas for level death benefit policies, including premium loads, per-policy fees, per-unit charges, additional benefit charges, substandard mortality adjustments, and the statutory interest floors supplied by the caller.
- `glp_on_change()` applies the attained-age policy-change delta method: current GLP plus GLP-after-change minus GLP-before-change.
- `calculate_7pay_premium()` calculates a TAMRA 7-pay style annual premium using the same present-value/commutation basis as GLP over a configurable pay period (default 7 years).
- `calculate_glp_iterative()` binary-searches the level annual premium that endows the policy at the 7702 maturity age using the real `IllustrationEngine`, guaranteed COI rates supplied by the caller, zero bonus interest, and guideline/exception machinery turned off.
- `load_rates(policy, config, coi_scale=0)` supplies guaranteed COI rates for guideline/TAMRA calculations; `coi_scale=1` remains the illustrated/current scale used by the normal projection.

The normal projection still seeds from the loaded policy GLP/GSP/7-pay values, but on a
specified-amount change the engine **does** now recompute them via the attained-age delta
method (`glp_on_change`, monthly-cent floor) and restarts the 7-pay period on a material
change (see Step 4.5). That recalc is wired but not yet calibrated to RERUN's
Guideline_Premiums calculator (deltas ~15-18% low; `PolicyChangeEvent.metadata` can inject
RERUN's `new_glp`/`new_gsp`/`new_7pay` for mechanics-only validation).

Deferred:

- full integrated 7702A / MEC *flagging* in the monthly projection path (the cap enforces the 7-pay limit but does not report MEC status)
- Necessary Premium Test (CVAT) and the 1035 exchange
- force-out reduction of cost basis (CalcEngine `OD`)
- RERUN-calibrated guideline/GSP/7-pay recalc on face or DB option changes (mechanics wired; values not yet matched), and mid-year AccumGLP pro-ration

### 4.10 Step 11 - Loan Capitalization and Repayment Processing

Valuation-date injection points:

- preferred loan principal
- preferred loan accrued interest
- regular loan principal
- regular loan accrued interest
- variable loan principal
- variable loan accrued interest

Loans appear in many downstream calculations, but this is the section where the source loan buckets are injected.

This step is implemented before any new cash flow or premium is applied, and now
handles BOTH loan types.

**Arrears loans** — at policy anniversary only, accrued interest rolls into principal:

```text
principal += accrued_interest
accrued_interest = 0
```

**Advance (interest-in-advance) loans** — the loan *total* carries a year of prepaid
interest, so the total ≠ the payoff. At anniversary the next year's interest is grossed
onto the principal (CalcEngine AA/AC):

```text
principal += round2(principal * X / (1 - X))      # total grosses up toward principal/(1-X)
```

where `X = charge_rate * days_to_next_anniversary / 365` is the unearned-interest factor.
The gross-up is **rounded to whole cents** (CyberLife carries the loan in cents — a
deliberate divergence from RERUN's unrounded AA/AC; without it a fully-repaid advance loan
strands a sub-penny of debt and a negative surrender value). The payoff value is
`round2(principal * (1 - X))`, and a cash repayment reduces the principal by the
grossed-up `round2(repay / (1 - X))` (also rounded), so paying $X clears $X plus the
interest on $X for the rest of the year.

Outside anniversary months, balances carry through unchanged.

Notes:

- regular, preferred, and variable loan buckets are carried separately
- capitalization is handled by `capitalize_loans()`; advance payoff / repayment by `repay_loan()`
- the projection reads prior month end balances and converts them into beginning-of-month balances for the new month
- projected loan repayments are handled by `apply_cash_flow_inputs()` after capitalization
- a repayment larger than the loan payoff leaves an excess (RERUN vLNRepayLeftOver / MY).
  RERUN always returns it to the premium pool; SuiteView gates that behind the
  "Apply excess as premium" toggle (`IllustrationOptions.apply_excess_repayment_as_premium`,
  Loan Repayments group on the Input tab). Off (default): repayments stop at the payoff and
  the excess is discarded. On: the excess loads as lumpsum premium (with the premium load).

### 4.11 Step 11b - External Cash-Flow Inputs

This is implemented for projected months through `compile_month_inputs()` and `apply_cash_flow_inputs()`.

Supported projected cash flows:

- scheduled premiums by policy year and modal frequency
- unscheduled dated premiums
- fixed loans
- variable loans
- loan repayments
- withdrawals

This step occurs after GLP force-out and before premium and deduction.
(Withdrawals are processed earlier, in the dedicated withdrawal stage — Step 3.)

A new variable loan is added before the repayment, so the repayment sees the larger
balance:

```text
vbl_loan_princ += month_inputs.variable_loan
```

**Apply Premium to Loan First** (`IllustrationOptions.apply_prem_to_loan`,
`sInput_ApplyPremToLoan`): when on, the requested premium repays the loan *before*
funding the account value. The lumpsum repays first, then the scheduled premium, each
capped at the remaining loan payoff (CalcEngine MH/MI):

```text
MH = min(payoff, requested_lumpsum)
MI = min(payoff - MH, requested_scheduled)
```

MH + MI are added to any scheduled loan-repayment input (MN) to form the total
attempted repayment (MO). MH, MI, and the over-repayment leftover are handed to the
premium-acceptance chain (NL/NY) so only what remains loads onto the AV.

Loan repayment honors the loan type:

- **arrears** — the cash reduces the buckets directly (interest already lives in the
  accrued buckets) in order: regular accrued, regular principal, preferred accrued,
  preferred principal, variable accrued, variable principal
- **advance** — preferred payoff first then regular, each capped at its payoff, with the
  principal reduced by the grossed-up `round2(repay / (1 - factor))` and the result
  rounded to whole cents

These future cash-flow inputs affect projected months only. They do not alter the inforce snapshot row.

Fixed new-loan requests are deferred to the post-deduction policy-values slice so the engine can determine how much qualifies as preferred loan.

### 4.12 Step 12 - Apply Premium

Valuation-date injection points:

- PremTD
- PremYTD
- cost basis

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

### 4.13 Step 13 - Monthly Deduction

Valuation-date injection point:

- Account Value is injected in the account value after monthly deduction field

AV appears in many places, but this is the injection point that matters for the RERUN-style pipeline.

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

Corridor test and gross death benefit. The corridor product is **truncated to a whole
dollar** (CyberLife rule — a deliberate divergence from RERUN's col OT, which multiplies
without truncating). The standard DB itself is not truncated:

```text
gross_db = max(standard_db, trunc(corridor_rate * nar_av))
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
- the annual flat extra is converted to a monthly amount with `TRUNC(flat_extra / 12, 2)`, matching RERUN's cent truncation rather than ordinary rounding

```text
adjusted_coi_rate = raw_rate * (1 + table_rating_factor * table_rating) + TRUNC(flat_extra / 12, 2)
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
adjusted_rider_rate = raw_rider_rate * (1 + table_rating_factor * rider_table_rating) + TRUNC(rider_flat_extra / 12, 2)
rider_charge = rider.units * adjusted_rider_rate
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

### 4.14 Step 14 - Exception Premium Calculations

The GP exception premium is now implemented in-engine (CalcEngine `SY/SZ/TA/TB/TD`), gated by `IllustrationOptions.allow_exception_prems`. Once the policy is past the safety-net period, has no CCV protection, has reached the guideline limit (`SX`), and account value after charges has gone negative, the engine injects the exception premium that brings after-charge AV back to zero:

```text
gross   = max(0, -av_after_charge)
discount = gross / 1000 * coi_rate
exception_prem = (gross - discount + flat_prem_load) / (1 - target_load_rate)
av = av_after_charge + (exception_prem * (1 - target_load_rate) - flat_prem_load + discount)   # -> ~0
```

Exception mode latches on for the remainder of the projection, disables guideline force-out, and adds an exception-premium lapse protection (`YQ`) to the lapse test. The exception mechanic gates only on the safety-net, CCV/shadow, guideline-limit, and inforce conditions — **a policy loan does not block it** (the UI now allows Allow-GP-Exception for loan policies, since premium is applied to the loan first; only an active shadow account still blocks). The separate PolView GLP Exception workflow still solves a level premium in `suiteview/polview/services/glp_exception.py` and projects with the in-engine exception mechanic disabled (it computes its own).

### 4.15 Step 15 - Policy Values / New Fixed Loan Allocation

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

The requested loan is first **capped at the lapse surrender value** when
`IllustrationOptions.restrict_loans_to_sv` is on (the workbook default — CalcEngine TQ
`vAppliedLoan` with `sInput_RestrictLoansToSV`): you cannot borrow past the surrender
value, `AV - full surrender charge - existing debt - MD holdback`.

Allocation rule:

```text
applied_loan = min(requested_fixed_loan, max(0, lapse_sv_cap))   # when restrict_loans_to_sv
preferred_amount = min(applied_loan, preferred_capacity)
regular_amount = applied_loan - preferred_amount
```

If preferred loans are not available on the policy, the full applied fixed-loan amount is added to regular loan principal.

### 4.16 Step 16 - Accumulation: Interest Credit

Interest processing is handled by `credit_interest()`.

Base and bonus annual rate:

```text
annual_rate = policy.current_interest_rate
effective_annual_rate = annual_rate + bonus_rate
```

If the plancode uses `ExactDays`, the implementation now uses actual calendar days in the month:

```text
days = days_in_month(month_date)
monthly_rate = (1 + effective_annual_rate) ** (days / 365) - 1
```

Otherwise:

```text
monthly_rate = (1 + effective_annual_rate) ** (1 / 12) - 1
```

The same actual-day exponent is also used for regular and preferred loan-credit rates when ExactDays is active.

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

### 4.17 Step 16b - Accumulation: Loan Interest Charges

This is handled by `accrue_loan_interest()` after interest credit.

Only in-arrears loan types accrue monthly charges here. Advance (interest-in-advance)
loans do not accrue monthly — their interest is prepaid and grossed onto the principal at
the anniversary instead (Step 11), so they correctly pass through this accrual step.

```text
regular_accrual = regular_principal * loan_charge_rate_guar * days_in_month / 365
preferred_accrual = preferred_principal * pref_loan_charge_rate_guar * days_in_month / 365
variable_accrual = variable_principal * variable_loan_charge_rate * days_in_month / 365
```

The variable loan charge rate is loaded from the most recent `LH_FND_VAL_LOAN.LN_CRG_ITS_RT` row when the base policy loan type is variable (`LN_TYP_CD` 6 or 7). If the policy has no applicable variable loan rate, variable loan accrual remains zero.

Variable loans do not participate in the collateral/impaired interest-crediting split; variable-loan-backed value is treated as unimpaired AV for interest crediting. Advance loans are modeled by the anniversary capitalization + repayment gross-up (Step 11 / `loan_handler`), not by this monthly accrual path.

The accrued charges are added to the accrued buckets, not principal.

### 4.18 Step 17 - Shadow Account / CCV

Valuation-date injection point:

- Shadow account value is injected in this section right after shadow monthly deduction

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

`shadow_rider_charges` uses the regular-side rider and benefit charges calculated in monthly deduction, less any CCV benefit charge. Premium waiver and all other regular-side rider/benefit charges therefore come straight out of the shadow account using the same regular-side charge basis.

### 4.19 Step 18 - Testing: Safety Net / Lapse Protection Tracking

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

### 4.20 Step 18b - End-of-Month Values and Lapse Test

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

Surrender value is the AV-after-exception less the surrender charge and policy debt, and
is **not floored at zero** — it can be negative (the Values tab floors only the
display-facing `IllustrationSV`, not the raw `ESV`):

```text
surrender_value = av_after_exception - surrender_charge - policy_debt
```

Ending death benefit is recomputed from the END-of-month AV (CalcEngine VY/VZ/WB), not
just carried from the deduction-time gross DB:

```text
edb_wo_corr = total_face
            + (db_option == "B": max(0, av_end))
            + (db_option == "C": max(0, premiums_to_date - withdrawals_to_date))
edb_corr  = max(0, trunc(av_end * corridor_rate) - edb_wo_corr)   # corridor truncated to whole dollar
ending_db = edb_wo_corr + edb_corr - policy_debt + primary_insured_rider_face
```

Lapse test (the protections are the safety net, shadow account, positive SV, AV-less-loans,
and exception mode):

```text
positive_sv = (lapse_value == "SV" and surrender_value > 0)
av_loans_test = (lapse_value == "AV" and av_after_exception - policy_debt > 0)
exception_protection = (exception_mode and surrender_value > -0.0001)
any_protection = snet_active or shadow_protection or positive_sv or av_loans_test or exception_protection
lapsed = prior_lapsed or not any_protection
```

Once `lapsed` becomes true, later states remain lapsed. (The `-0.0001` tolerance on the
exception protection is why the advance-loan sub-penny residual — since fixed by
cents-rounding the loan — could otherwise tip a fully-funded policy into a false lapse.)

### 4.21 Step 19 - Deemed Cash Value

Deemed Cash Value is not implemented yet.

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

## 6. PolView GLP Forecast Consumers

The GLP Exception and Policy Support workflows now use this illustration pipeline rather than a separate forecast math path.

### 6.1 Availability Gate

`check_forecast_availability()` builds `IllustrationPolicyData`, loads plancode config and rates, then verifies the policy can support forecasting before the UI enables the workflow.

Eligibility and availability checks include:

- policy must be a UL-style product using Guideline Premium definition of life insurance
- each active base segment must have COI rates
- table EPU products must have segment EPU rates
- active riders and benefits must have required rate schedules
- table monthly fee and table premium load products must have those schedules loaded

### 6.2 GLP Exception Premium Solver

`calculate_glp_exception()` projects from the current valuation date to a target inforce date using `ProjectionTiming.CYBERLIFE_MONTHLIVERSARY`.

The flow is:

1. Pull post-valuation premium transactions from `FH_FIXED` and adjust starting account value, premium-to-date, and cost basis by gross/net premium.
2. Project a no-premium baseline to the target month.
3. If the policy survives with positive account value, report that no additional required premium is needed.
4. Otherwise, binary-search a level monthly premium that leaves ending AV at least `1.00`.
5. Reproject with dated premium inputs and summarize required net premium, target/excess loads, flat loads, and gross premium.
6. Recalculate accumulated GLP needs and possible force-out/new accumulated GLP values for the target date.

Important implementation details:

- the forecast horizon excludes the target date itself; there must be at least one monthly deduction before the target
- projections use `stop_on_lapse=False` so the forecast can continue through weak or negative AV months
- if starting account value is below `1.00`, the solver inserts a one-time catch-up premium to bring AV to `1.00` before level premiums begin
- negative current GLP is treated specially when an adjustment is needed: `new_glp` becomes `0.0`, and the adjustment basis can use current accumulated GLP

### 6.3 Policy Support Premium Forecast

`calculate_policy_support_forecast()` uses the same CyberLife monthliversary engine path, but instead of solving for a required premium it compiles a user-entered premium schedule.

Supported premium modes are:

- Monthly
- Quarterly
- Semi-Annual
- Annual

The forecast rows expose the fields the Policy Support tab needs to audit the force-out path:

- interest credited
- current GLP
- accumulated GLP
- premiums paid to date
- accumulated withdrawals
- guideline force-out
- entered premium
- account value before monthly deduction
- monthly deduction
- ending account value

## 7. What Appears Implemented Versus Still Incomplete

### 7.1 Clearly Implemented in Code

- inforce reconciliation row
- premium split and premium loads
- the full NC..NZ premium-acceptance allowance chain (guideline/7-pay caps, lumpsum, levelizing, TAMRA BOY/EOY + material-change reset + MEC bypass)
- Apply Premium to Loan First (`sInput_ApplyPremToLoan`)
- the AX..BU withdrawal stage (max-net, corridor, partial surrender charge, gross/net trackers, SA-reducing decreases)
- DBO A, B, and C handling, with A↔B level-DB change mechanics
- future policy-change events: DB option flips, face increases/decreases, rate class / table-rating changes, rider keep/change/drop
- per-component MTP / CTP target-premium detail snapshots, recomputed on coverage change
- multi-segment base coverage support in deduction and surrender charge logic
- COI (incl. NAR-split / ratchet-banding for ~1983 UL plancodes), EPU, MFEE, AV charge
- corridor death benefit truncated to a whole dollar
- rider and benefit charges during deduction and shadow account processing, excluding the CCV benefit charge from shadow rider charges
- rider substandard table ratings and flat extras in rider COI charges
- loan capitalization — arrears roll-in AND advance (interest-in-advance) gross-up, cents-rounded — plus in-arrears and variable-loan accrual when a policy variable rate is available
- advance loan payoff and repayment gross-up (`repay_loan`), with the loan surrender-value cap (`restrict_loans_to_sv`)
- projected loans, repayments, withdrawals, and premium overrides
- guideline premium force-out, accumulated GLP tracking, and the GP exception premium (available for loan policies)
- CyberLife monthliversary timing mode for PolView GLP forecasts
- GLP Exception level-premium solver, Min-Level-to-Exception solver (loan-capable), and Policy Support premium forecast consumer
- standalone commutation GLP/GSP calculators, TAMRA 7-pay calculator, attained-age GLP change delta, and iterative GLP solver utility
- current-vs-guaranteed COI scale selection for normal projection vs guideline/TAMRA calculations
- bonus interest logic
- ExactDays credited interest using actual `days / 365`
- shadow account / CCV calculation
- safety net, shadow, AV, exception, and SV lapse protection
- surrender value (unfloored), ending death benefit (recomputed from EOM AV), and lapse determination

### 7.2 Explicitly Incomplete or Partial in Current Code

- the engine's OWN guideline recalc (commutation on guaranteed COI) runs when no injected values are supplied, but is not yet calibrated to RERUN's Guideline_Premiums calculator (deltas ~15-18% low); DBO B after-states need the iterative method or injection
- DBO B-to-A is implemented (inverse level-DB mechanic, material change) but not yet validated against a RERUN reference
- mid-year (non-anniversary) changes do not pro-rate the year-of-change AccumGLP (Guideline_Premiums col K AccumAdjust)
- the 1035 exchange (allowance row "1") and the CVAT Necessary-Premium Test (vNPT_Premium) are stubbed at zero in the premium chain
- TAMRA/MEC *flagging* is not surfaced (the cap enforces the 7-pay limit but no MEC status is reported); deemed cash value, GCO logic, and full integrated 7702A determination remain out of this monthly path
- advance loans are validated penny-exact at current/early durations; the cents-rounding divergence from RERUN (unrounded AA/AC) is intentional and still wants a long-horizon RERUN-saved-case confirmation

## 8. Recommended Next Review Questions

Based on the current implementation, the next useful review questions are:

1. What is the exact monthly MTP / premium-waiver target-premium recomputation basis after face increases and decreases?
2. Should DB option changes adjust specified amount to preserve death benefit the way RERUN appears to do for A-to-B changes?
3. Should `guideline_calc.py` remain a standalone/offline calculator for GLP review, or should policy-build and policy-change flows start deriving GLP/GSP/7-pay from it instead of relying only on loaded values?
4. Should future face and DB option changes trigger automatic GLP/GSP/7-pay recalculation in the projection month, and if so should that timing follow RERUN's anniversary/new-segment lag exactly?
5. Do we want projected withdrawals and loans to trigger any additional business rules beyond simple AV and debt movement?
6. Should GLP force-out continue to be modeled as a withdrawal accumulator movement in all forecast contexts, or should the GLP Exception result distinguish actual withdrawals from force-outs more explicitly?
7. Should the older `SPEC_Calculation.md` be revised to match the current engine, or kept as milestone history?

## 9. Bottom Line

The current engine is no longer just a basic monthly AV projection. It already behaves like a broader inforce illustration pipeline with support for deduction detail, loans, cash-flow inputs, simple future policy changes, guideline force-outs, shadow values, multiple lapse-protection paths, and PolView GLP forecast consumers. The main next-step work looks less like building the basic pipeline and more like closing the remaining edge cases, validating formulas against RERUN/CyberLife, and deciding which partial areas need to be promoted to full production behavior.
