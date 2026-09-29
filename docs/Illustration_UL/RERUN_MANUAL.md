# RERUN and Illustration manual

RERUN input, engine, regulatory-premium, rollback and output behavior. Engine internals stay in the adjacent architecture docs.

> Source: moved from the former long-form `Agent.md` so that the canonical standards file can stay concise.


## RERUN Tips button

The header **Tips** button opens a non-modal cheat-sheet of hidden-ish features:
right-click menus, the hidden **Grid Inputs** tab (dated transactions; right-click
the Illustration Inputs tab bar to show it), double-click drill-downs, drag/drop
and the Options menu. The content lives in `RERUN_TIPS` in
`suiteview/illustration/ui/tips.py`; when you add a right-click, double-click,
drag/drop, shortcut or hidden-by-default feature, add a tip there too.
Regression: `tests/test_illustration_tips.py`.


## RERUN guideline calculation maturity

GLP calculations end at **min(policy maturity age, 100)**, not an unconditional
age 100. The policy's loaded `maturity_age` is authoritative; premium-cease age
is a separate charge rule, not the endowment horizon. The shared monthly
GLP/GSP/7-pay basis, policy-derived commutation inputs, optional engine search
and PV drill-downs use `monthly_guideline.guideline_maturity_age()`.
Age-95 policies have charge months only through age 94 and their terminal
endowment at 95; age-100/121 policies retain the age-100 cap. Midyear monthly
bases retain the partial-year offset.

The search's pre-anniversary seed uses the prior attained age so the engine's
contract-maturity clamp does not cut eleven months off an age-95 calculation.
Loaded inforce GLP/GSP/7-pay values are not overwritten; recalculations and
from-issue scenarios use the corrected basis. Source snapshots remain unchanged.
Regression: `tests/test_illustration_guideline_maturity.py`.
Read-only C19 / U0394137 verification:
`tools/engine/verify_guideline_maturity.py <bundle.cases.json> --case "C19 Batch"
--output <report.json>` reconciles before/after GLP/GSP drill-downs at both
changes to the solver, with all terminal endowment rows at age 95.

## RERUN renewal-rated benefit adjustments

Riders & Benefits must not infer adjustability from a benefit's stored issue
COI rate. Active non-administrative benefits load separate rate schedules;
NULL/zero issue rates do not mean free coverage. Live and saved-snapshot cards
use the same type-based eligibility. Administrative `#` benefits and already
matured/inactive benefits stay inspectable but their adjustment controls are
disabled. Existing rider coverage eligibility is unchanged.

U0416030's Benefit 39 (ULDW91) has a NULL issue rate and a 2028-02-15 cease
date. Verified Drop on 2026-10-15 with Prem to Maturity: current and guaranteed
charges stop, and saved-case Compare matches native Run Values. No snapshot
rate substitution or live-record change is needed.
Regression: `tests/test_illustration_rider_buttons.py`.
Read-only native verification:
`tools/app/verify_benefit_drop.py <c43b.cases.json> --output <report.json>
--screenshot <image.png>`.

## RERUN guideline substandard cease dates

Monthly guideline GLP/GSP/7-pay bases apply table ratings and flat extras using
each actual projection-month date and the same adjusted-COI helper as monthly
deductions. Charges stop on the recorded cease date, including midyear dates.
Never add the absolute policy year to the recalculation year: that counts
elapsed policy years twice and drops a lifelong rating decades early.

U0416030 / 01, Table 2 through 2063-02-15, reproduced the erroneous age-68
drop in the 2030-02-15 face-decrease recalculation. Corrected GLP Before is
6,519.52 instead of 5,624.62; month 73 q'x is 0.00378750 instead of 0.00252819.
The earlier table-drop scenario was not leaking into subsequent runs.
Regression: `tests/test_illustration_guideline_substandard.py`.
Read-only saved-snapshot/native check:
`tools/engine/verify_guideline_substandard.py <c43b.cases.json> --case C43B
--output <report.json> --screenshot <image.png>` recreates the screenshot inputs
in memory, checks explicit removal and rerun isolation, and leaves saved work
unchanged.

## RERUN monthly MEC detection

**Conform to TAMRA** controls premium capping, not MEC detection. After each
projected month, the engine tests accepted seven-pay contributions against the
active **TAMRA year**, independent of the policy anniversary. The first excess
or failed decrease back-test permanently sets `is_mec` and `mec_year`; later
anniversaries, withdrawals or recalculations cannot clear or redate that status.
Projection-private policy state prevents a MEC result from contaminating the
loaded snapshot, another solve or the guaranteed run. Values, Report and Compare
share the detection rule; both projection timings carry the permanent status.

C19 Batch / U0394137 verified read-only with TAMRA off: B-to-A starts a new
period on 2026-10-01, accepting $10,897.44. The next annual payment on 2027-09-01
is still in TAMRA year 1, so $21,794.88 exceeds the recalculated $10,920.96
limit (after the maturity-95 horizon correction) and establishes MEC in
**policy year 28**, not at the later year-32 face decrease. TAMRA on caps the
year-28 payment; the separate year-32 decrease can still fail its back-test.
Regression: `tests/test_illustration_mec_detection.py` and
`tests/test_illustration_tamra_recalc_sheets.py`. Native saved-case verification:
`tools/app/verify_saved_case_mec.py <bundle.cases.json> --case "C19 Batch"
--tamra off --expect-year 28 --native --output <report.json>`.

## RERUN face decrease before B-to-A option change — pending implementation

**Business/compliance decision (2026-09-21): recorded for future minimum non-MEC
face options; calculation behavior is not changed by this note.**

When a policyholder requests a face decrease together with a death-benefit option
change from B to A, process the **decrease first, then the option change**.
This is the adopted conservative business rule, not a claim that the engine
already implements it or an independent interpretation of regulations.

For a policy in an existing 7-pay period where the objective is to avoid MEC
status:

1. Determine the maximum permissible decrease (minimum remaining face) on the
   **pre-option-change basis**, with the recalculated 7-pay premium still passing
   backtesting against the existing period's premium history.
2. Apply and evaluate that decrease before allowing the B-to-A change to start
   another 7-pay period. A later reset must not erase a failed decrease backtest.
3. Then process B-to-A, including its increase in specified amount and applicable
   material-change / new 7-pay-period treatment.

Do not solve the minimum face after first resetting the period through B-to-A:
that could allow a much larger decrease and lower face than the adopted rule.
An absolute face input for the decrease is the **post-decrease, pre-option-change
face**, not the final face after B-to-A. The subsequent option-change increase
must not be overwritten by reapplying that absolute target. Preserve this
distinction when accepting a target face rather than a decrease amount.

**Known implementation gap:** `illustration/core/calc_engine.py` currently
orders `DB_OPTION` before `FACE_AMOUNT` through `_POLICY_CHANGE_ORDER`, used by
both `_compile_policy_changes()` and the monthly processing loop. That loop
combines changes for guideline/7-pay recalculation and material-change reset.
A future implementation must preserve the intermediate decrease/backtest stage;
swapping sort priorities alone is not sufficient evidence of compliance.
Revisit this with minimum non-MEC face options, with regressions for an active
7-pay period, a decrease failing before but passing after a reset, and equivalent
absolute-target/decrease-amount inputs. Verify shared solver, Run Values and
saved-case/Compare behavior; do not silently extend this decision to unrelated
option-change combinations.

## RERUN target-based benefit amounts

Primary-insured **Table Rating Change** inputs also replace every type-3/type-4
premium waiver's rating multiplier with `1 + TableRatingFactor * new_table`
on the change date (table zero means multiplier 1). Apply this to the private
projection policy before target and guideline recalculation, so monthly charges,
displayed adjusted rates and GLP/GSP/7-pay after-bases all agree. Before-bases and
unchanged runs retain the recorded benefit factors; other benefit types, riders
and the loaded snapshot remain unchanged. Regression:
`tests/test_illustration_waiver_rating_changes.py`.

Target-based stipulated-premium waiver (type 4) charges use the plan's explicit
`PWoT_COI_Basis`: 2 is current annual MTP (`policy.mtp * 12`), 3 is current annual
CTP, and 1 retains recorded units. `1U14L400` (UFF90022 / 26, benefit 4M) uses
**basis 2**, per the business correction of 2026-09-21; its previously omitted
setting incorrectly froze the benefit at $913.20 after a face change.
Do not infer a target basis from an amount coincidentally matching MTP/CTP or
change all FFL plans. Existing policy-change recalculation updates the targets
before monthly deduction; both displayed amounts and actual charges consume
them without mutating the loaded benefit.
Read-only verification: `tools/engine/verify_target_benefit_amounts.py --policy
UFF90022 --company 26 --date 2027-01-04 --face 100000` verifies a hypothetical
decrease: annual MTP and 4M amount become $610.31, and its charge becomes $1.10
instead of $1.64. Tests: `tests/test_illustration_pwot_coi_basis.py`.

GLP/GSP/7-pay monthly bases and their Before/After PV detail use the same
`target_waiver_charge()` helper as monthly deductions for PWoT basis 2/3.
Use each side's annual MTP/CTP and the base coverage's active table rating;
do not use recorded benefit units or its independent rating factor. Charges
are cent-rounded and ratings stop on their actual cease date. Basis 1 and
type-3 waiver rules are unchanged. The earlier face-change fix covered monthly
deductions but missed this guideline path.
Read-only verified `000239324 / 26 / NU1F3L00`, face 50,000 on 2026-09-24:
annual MTP 217.83, first After 4M charge 0.81 (not 1.36), GLP After 1,397.26
(not 1,402.75). The verifier above now checks GLP/GSP After against monthly
charges; regressions also cover 7-pay, current/guaranteed projections, increases,
decreases, zero targets, rating cessation and source immutability.

## RERUN Policy calculated monthly deduction

RERUN's live Policy refresh retains the load-time calculated monthly deduction
and validation warnings for that exact `PolicyInformation` instance. The
post-load Edit Record/basis refresh must not clear Calculated MD or hide failed
MD/rate checks. A refresh reuses the check without rerunning the engine; a new
Get replaces it, and saved/edited snapshots never inherit the live result.
Regression: `tests/test_illustration_session_state.py`.
Read-only native verification: `tools/app/verify_policy_calculated_md.py
--policy UFF90022 --company 26 --screenshot <path>` uses an isolated temporary
profile and the real Get/refresh path. Verified both MD fields display $18.70.

## RERUN corridor COI rate

Corridor COI uses the **latest active base segment's adjusted COI rate**, not
coverage 1's rate. Reuse that segment's current duration, rate band, table rating
and active flat extra. Skip depleted, matured, terminated and not-yet-issued
segments; a stored zero rate remains zero, not a reason to select an older
segment. Segment order is the engine's existing oldest-to-newest order.
Ratchet-banded plans select the same segment for both corridor band rates,
retaining their band-split charges.

`coi_rate_corr` carries the corridor rate separately from the existing
coverage-1 `coi_rate`, through the inforce row, both projection timings, Values
and Excel/debug exports. Ratchet's single display rate remains its band-1
representative; charges still use both bands. No COI rate tables are changed.
Regression: `tests/test_illustration_corridor_coi.py` and
`tests/test_illustration_values_tab.py` include the 2.39 / 2.55 distinction.

## RERUN waiver target rate units

UL_Rates stores benefit **39 / 3#** target rates as percentages, not decimal
multipliers: 5.5 means 5.5%, not 550%. `compute_target_premiums()` converts
these rates only for calculation, retaining the raw rate in Values/export
detail. Never infer units from the rate's magnitude or divide all type-3 rates:
FFL **3F** retains its existing cost-basis units. CTP continues to use the
rounded MTP-basis waiver component. No shared rate-table values are changed.

UIP45890 / 01's $50,000 to $100,000 face increase on 2026-09-26 exposed
the issue: waiver MTP was overstated 100-fold. The corrected annual target is
689 + (689 x 0.055 x 1.5) = 745.8425, giving Monthly MTP **62.15**, not
531.10. The loaded basis independently reconciles to **40.86**.
Regression: `tests/test_illustration_waiver_target_units.py` and
`tests/test_illustration_ffl_waiver_targets.py`. Read-only live verification:
`tools/engine/verify_face_increase_targets.py --policy UIP45890 --company 01
--date 2026-09-26 --face 100000 --expect-monthly 62.15 --expect-loaded-match`.
It checks the face-change illustration, unchanged control/source and Values/Summary
export mappings without changing live records.

## RERUN plan interest bonuses

Illustration bonuses use `illustration/plancodes/tRates_IntBonus.json`, selected
by plancode and latest effective date on or before the valuation date.
`1U135P00` has an unconditional 0.90% duration bonus effective 2023-02-01,
starting in policy year 11, with zero AV and guaranteed bonuses. Store its
`BonusDurThreshold` as 10 because the engine applies the bonus strictly after
the threshold year. Earlier effective entries remain intact.
Regression: `tests/test_illustration_bonus_rates.py`.

## RERUN Monthly MTP truncation

Monthly MTP uses decimal-safe cent truncation via `truncate_monthly_mtp()`.
Never use `math.trunc(mtp * 100) / 100`: an already-recorded 32.66 can multiply
to just below 3266 in binary floating point and incorrectly become 32.65.
UIP12968's annual MAP of 392 gives `TRUNC(392 / 12, 2) = 32.66`.
The initial snapshot, both projection timings, target calculations, guideline
MTP basis and rollback reverse accrual share this rule. Preserve the separate
rounded PW basis in illustration timing. The Values grids and exports consume
the corrected state; do not patch display formatting or replace loaded targets
with recomputed annual targets.
Regression: `tests/test_illustration_monthly_mtp.py` and the recorded-cent case
in `tests/test_value_rollback_data.py`.

## RERUN unavailable table-rating target rates

All-NULL `TBL1MTP` / `TBL1CTP` lookup rows mean the table-rating target rate
is unavailable, not zero. `Rates` returns `None` for that case, retains stored
numeric zero, and rejects mixed NULL/numeric results explicitly. Unrated
coverages and expired table ratings can still calculate their ordinary targets;
active table ratings require both target rates. A shadow target configured as
`Table` also requires its table rate when the base coverage is rated. Never
replace a required missing rate with zero. Run Values logs failure tracebacks.

Read-only live/native verified `000340565 / 26 / 1U14L300`: phases 1 and 7
have table rating zero and NULL table-target rates; Run Values now builds
725 current rows, 523 guaranteed rows and a 61-year report.
Regression: `tests/test_null_table_target_rates.py`.
Repeat with `tools/engine/verify_table_target_rates.py 000340565 --native`;
the helper uses an isolated temporary profile and writes no database records.

## RERUN Values Summary loan columns

Values > Summary separates the beginning-of-month loan buckets into
`Loan_Accr_Int` (all outstanding accrued interest, not just this month's
charge) and `Loan_Princ` (principal only), each summed across regular,
preferred and variable loans. Ending loan columns remain unchanged.
The shared `illustration/core/summary_results.py` mapping also drives debug
exports and regression snapshots.
Regression: `tests/test_illustration_values_tab.py`.

## RERUN Values Summary shadow columns

Summary appends the workbook columns `vShadow_TP`, `Shadow COI`, `Shadow EPU`,
`Rider Charges`, `Shadow MD`, `Shadow Int Rate`, `vShadowEAV` in that order.
They read the existing monthly shadow state, not a UI recalculation.
Rider Charges is the shadow charge total (riders and benefits excluding CCV),
not the regular-side Rider COI. vShadowEAV is ending shadow AV before debt.
Summary's interest rate is a decimal (0.045 = 4.5%), like its regular Interest
Rate; the separate Shadow Account detail retains percentage units and compact
headings. Summary retains the full workbook names to distinguish regular and
shadow COI/EPU/MD. Both current/guaranteed Summary exports and regression
snapshots share these fields; Summary schema version is now 3, and shadow
interest comparisons use rate tolerance rather than money tolerance.
Tests: `tests/test_illustration_summary_shadow.py`,
`tests/test_illustration_values_tab.py`. Native no-DB verification:
`tools/app/verify_summary_shadow.py --screenshot <path>`.

## RERUN Prem to Maturity new loans

Dynamic Inputs permits new loans with **Prem to Maturity**, including forecast
loans and loans before the solved premium's start year. UI enablement and input
export share `_new_loans_allowed()`; **Max Level** and **Prem to Shadow Maturity**
still block new loans, including when mixed with Prem to Maturity. Loan payoff
solve restrictions are unchanged. Explicit one-year annual loan rows emit a
zero cutoff next year, not an indefinitely recurring loan.

Existing solver trials, Run Values and saved/Compare materialization carry the
same loan schedules and Apply Premium to Loan option. Guaranteed projections
lock the current side's applied loans and premium-diverted repayments, without
solving another premium or repaying those dollars twice. No rate/model changes
were needed. Regression: `tests/test_illustration_prem_to_maturity_loans.py` and
the dynamic-input level-type tests.
`MonthlyState.applied_loan_repayment` is total applied cash and already includes
`loan_repay_from_prem`; guaranteed `lock_values()` must copy the total alone.
Adding that subset again doubled a $33.25 payment to $66.50 and understated
guaranteed loan balances. Engine-backed regression:
`tests/test_illustration_guaranteed_loan_repayments.py` covers both projection
timings, arrears/advance loans, mixed repayment sources and payoff remainders.
Read-only current-source verification:
`tools/app/verify_prem_to_maturity_loans.py --snapshot <policy-snapshot.json>
--output <report.json>` exercises revised Case9 through native Run Values and
save/export/import, without Excel or modifying the supplied snapshot.
Verified U0389725 / 01: $1,000 once on 2028-04-06, $56 monthly through March
2029, then $23.01 solved monthly from April 2029 ($14.54 in the separate no-loan
control). Both native and saved-case runners match. Existing terminal age-95
rows carry both matured/lapsed flags in both controls; no pre-maturity current
lapse occurred. Guaranteed values stop on lapse in February 2035.

## RERUN loan repayment priority

Loan repayments use the conservative fixed-loan order approved 2026-09-23:
**preferred accrued interest, regular accrued interest, preferred principal,
regular principal**. The shared `loan_handler.repay_loan()` owns this order for
explicit repayments, premium-to-loan diversion and Pay-off solver trials;
current/guaranteed and both projection timings consume it. Variable accrued
interest and principal remain afterward. Advance loans retain preferred-first
payoff and their existing unearned-interest refund; anniversary capitalization,
cash caps and overpayment handling are unchanged. Loaded records are never
mutated. Regression: `tests/test_illustration_loan_repayment_order.py` covers
each bucket boundary, payment sources, guaranteed cash-flow replay and a real
engine-backed payoff solve with unequal charge rates.

## RERUN Prem to Maturity levelizing

The Levelize choice applies even in the first guideline-capped policy year.
`level_to_exception_options()` must not enable the transition-year
dollar-for-dollar override when levelizing is on. Solver trials, Run Values,
saved/Compare runs and the shared target-date solves use this same option
builder. Outstanding loans still disable levelizing; Levelize off retains
dollar-for-dollar acceptance. Whole-cent modal caps remain floored and carried.
The guideline-limit latch uses the recorded guideline cap source and payable
cent cap, not equality with the unrounded allowance; fractional-cent room must
not prevent later GP exception entry or make the maturity solve fail.
With Levelize on, binding the annual guideline cap is sufficient for GEP
eligibility even while there is unspent room for later scheduled payments.
Do not require that all annual room has already been collected before funding
a midyear AV shortfall. Exception permission, safety-net, shadow and maturity
gates still apply; a below-cap request or TAMRA-only cap is not this trigger.
`tests/test_illustration_monthly_deduction_premium.py` exercises actual
month-6 GEP with annual room remaining, both projection timings, off-anniversary
starts, INPUT/Prem-to-Maturity options and negative eligibility controls.
UE006519 year 12 reproduced the override: $37.12 for five months, $18.58,
then six zeros despite Levelize on. With the same requested premium, the fixed
run accepts $17.01 in each of the twelve months.
Regression: `tests/test_illustration_premium_allowance.py` and
`tests/test_illustration_level_to_exception_horizon.py`.
Read-only live check: `tools/engine/check_premium_levelization.py UE006519 37.12
--prem-to-maturity --months 28 --year 12 --expect-level`; add `--solve` to
recalculate the maturity premium on the corrected basis.
Use `--native --year 12 --expect-level` to exercise actual Run Values and
saved-case Compare in an isolated temporary profile. Verified UE006519:
the corrected solve is $21.89 monthly, all twelve year-12 payments are $21.89,
and the current projection reaches age 121 without a pre-maturity lapse.
Guaranteed output is also built; saved Compare exactly matches Run Values.

## RERUN existing GP exception periods

An inforce GPT policy with a known GLP of zero starts in the exception premium
period. RERUN suppresses scheduled, unscheduled and Monthly Deduction premiums,
spends the existing account value, then uses calculated GP exception premiums.
This starting status does not require the Allow GP Exception Premium checkbox;
the existing safety-net, shadow-account and maturity restrictions still apply.
The red Input notice identifies the period and explains the premium treatment.
Unknown GLP is not evidence of zero; `glp_is_known` preserves that distinction
when loading/saving the illustration basis. Current/historical manual GLP edits
are explicit known assumptions. From-issue scenarios do not inherit the period.

Guaranteed projections still use the current side's locked cash flows, not
newly calculated guaranteed exception premiums. PolView's GLP-adjustment
what-ifs explicitly disable starting-period recognition: their hypothetical
GLP=0 funding comparison is not an assertion of existing exception status.
Regression coverage is in `tests/test_illustration_monthly_deduction_premium.py`
and the red-notice test in `tests/test_illustration_inputs_dynamic.py`.
Read-only live/native verification:
`tools/app/verify_inforce_exception_period.py --policy U0307077 --output-dir <directory>`.
Verified 2026-09-15: GPT, GLP=0, starting AV=-605.20; no regular premiums,
calculated exception premiums from the first projected month, zero regular
premium solved to maturity, and the red notice visible.

## RERUN new-business / from-issue scenarios

The policy-scoped **Inforce | New Business - From Issue** toggle on Illustration
Inputs selects a hypothetical issue illustration, not a historical replay.
The issue mode has a blue window header, persistent mode notice and an
**At-Issue Conditions** tab. The Policy tab always retains the loaded inforce
snapshot. Changing mode or issue assumptions invalidates old Values/Report.

Default to original issue-date base segments (exclude later increases/COLA),
using their original face amounts where available. The user can edit the total
issue face and death-benefit option and exclude original-issue riders/benefits;
there is no add-new-rider workflow. Current DB option, underwriting and billing/
allocation defaults are not evidence of original policy history: review them.
Later additions remain visible as excluded in the issue editor.

Issue scenarios reset balances/loans/accumulators and start the full monthly
pipeline at the original issue date and age. Current-side rates use scale 1;
current illustrated interest assumptions are applied from issue, while the
guaranteed side remains guaranteed. Issue targets and regulatory premiums are
recalculated on the edited coverage basis. Never mutate the source snapshot.
Each mode retains separate input schedules; historical transactions are not
copied into the new-business scenario. Saved/imported cases persist the issue
conditions and mode input states; Compare uses the same scenario builder.
ABR Quote is an inforce-only mode and cannot be combined with from-issue mode.
Grid Inputs > Unscheduled Premiums can explicitly populate the policy's
unreversed PR/PI/PA/PF/PT/PB/PW premium transactions from issue, including the
transaction type; this is user-triggered and is never automatic replay.

**No Lapse Period** on At-Issue Conditions selects an AV-less-loans lapse basis
for that many years from issue, rounded to the nearest projection month. It does
not permit unfunded AV to run negative: other existing protections still apply.
Afterward, the normal plan lapse basis resumes. Zero disables this convenience
override, not the contractual safety net. Default to the recorded minimum-premium
cease date's covered period when present, otherwise the configured
`PlancodeConfig.snet_period`, otherwise zero. Never change surrender charges,
minimum-premium targets, regulatory limits or shared plancode configuration.
The saved issue assumptions, solves, current/guaranteed projections and exported
basis notices carry the same period; it is not a contractual guarantee.
Regression: `tests/test_illustration_issue_no_lapse_period.py`.

Regression coverage: `tests/test_illustration_run_from_issue.py`,
`tests/test_illustration_issue_conditions.py` and
`tests/test_illustration_issue_outputs.py`. Native UI verification without DB
access: `tools/app/verify_issue_illustration.py --output-dir <directory>` uses
a synthetic policy and captures both themes. Month-end issue dates stay anchored
to the original issue day, including the Illustration-to-Date cutoff.

## RERUN Value Rollback

**Options > Edit Record** enables the entire valuation-editing feature. This
app-wide, session-only option defaults off. Off means the original read-only
Policy view: no valuation selector, inline value editors, or coverage-edit note.
Disabling restores loaded values for every open policy and invalidates their
valuation-specific results. Saved valuation cases require the option before
loading or comparing; never silently run their historical assumptions while off.

When enabled, the policy-level **Valuation Date / Update** strip defaults to the loaded
valuation date and includes recorded monthliversary values within six calendar
months before it; missing months are never invented. There is no Rollback toggle.
Selecting a date alone does nothing: **Update** applies it. Updating the current
date restores the loaded basis and clears manual value/coverage assumptions.
Historical selection is a scenario basis, not a change to the live policy.
Value editing is separate from New Business - From Issue and ABR Quote.

Keep the loaded `IllustrationPolicyData` immutable. Historical data flows through
`PolicyInformation` into captured rollback snapshots; scenario construction
applies a snapshot to a copy before projection inputs. Saved/imported cases
must retain both the source snapshot and the applied rollback selection and
manual edits. Policy-list switching retains that policy's applied basis;
explicit Get resets inputs. A failed rollback must leave the prior applied
basis intact, with an actionable error.

**Account Value** and **Shadow Account Value** are inline inputs beside their
Fund Values labels. They default to the selected basis's values; Enter or leaving
the field applies an edit. **DB Option** is an inline combo beside its Policy Info
label. **Coverages and Benefits** open detail windows with an editable **Amount**
row and an **Apply** button. These controls work for every applied current or historical
inforce date while **Options > Edit Record** is selected. All edits are explicit scenario
assumptions, never live policy edits.

Edit Record also exposes premium-paying Status, the six regular/preferred/variable
loan principal/accrued-interest amounts, loan charge rates, premium/withdrawal
accumulators, MTP/GLP/GSP/commission targets, MAP cease date, cost basis, MEC
status, 7-pay date/cash value/premium/lowest DB and all seven TAMRA contributions.
These edits share the same saved-case/Compare scenario path as AV and shadow.
Fund and allocation tables allow only numeric value edits for existing fund IDs;
there are no add/remove/rename controls. Their edits are staged with Apply/Reset;
allocation percentages must total 100%. Unapplied fund edits block Run/Save and
Compare rather than silently projecting or saving the previous values.
Account Value, fund balances and loan principal are independent manual assumptions.
Editing fund balances does not recalculate AV or loans; edit those fields separately.
Current-date AV edits retain existing fund IDs and balances. Historical total-only
AV never invents a fund breakdown.

Coverage/benefit editors are owned, non-modal top-level tool windows, not widgets
confined inside RERUN. Clear their reference on the explicit `closed` signal
before deferred deletion; `destroyed` sender identity is not a reliable reopening
guard under PyQt. Header Close, Cancel and Apply must all allow reopening.
The date label/combo/Update have aligned 26px heights. Only an applied date
different from the loaded valuation date activates the two-tone purple-to-white
header and notice gradient; current-date edits retain the normal header theme.

Historical specified amounts and death-benefit option are not reconstructed.
Changing to a different rollback date resets those date-specific edits; review
them again. The title, persistent
mode notice, Policy tab and output/export basis must identify rollback so
historical values cannot be mistaken for current inforce values.

`illustration/core/value_rollback.py` owns recovery and validation. U1MV AV is
already post-deduction. Ordinary unreversed PR receipts are reversed from the
current paid/cost-basis totals, including processed receipts after the loaded
valuation date; same-day ordering uses the recorded CD sequence. Pending
premiums are excluded only after exact reconciliation to the current paid total.
TAMRA contributions are matched by year keys, not row order. Loans use exact-date
fund/phase/preferred/interest-status buckets, never current/sentinel rows.

AccumMTP/AccumGLP are **derived, not archived**: reverse monthly MTP and
anniversary GLP on an explicitly unchanged target/coverage basis (GLP stops
accruing at age 100). `LH_POL_TARGET.TAR_DT` is not a snapshot date. CVAT's
AccumGLP is not applicable. Current support is single-base UL/IUL with
no detected target-affecting changes or unverified transaction effects;
unsupported or ambiguous essential data blocks Update rather than guessing.
Manual face edits re-resolve current rate bands at the existing rate-loading
boundary, preserving the original surrender-charge band.

**IUL uses historical total AV only.** Do not require or reconstruct individual
historical fund/bucket balances for rollback. Clear the historical fund detail;
retain loaded premium allocations and illustrated crediting assumptions as
forward assumptions, not historical holdings. The Policy tab explicitly labels
this aggregate-only basis, and report/export limitations carry it. Current and
guaranteed projections work without historical buckets, including WAIR crediting.
Recovery failures identify the actual historical blocker rather than cascading
"missing" accumulator errors when the current amounts are present.

The current XP target does **not** recover historical shadow balances.
Rollback can display the other recovered values while showing shadow as
**Unavailable**. Enter an explicit historical amount (including zero) directly in
**Shadow Account Value** to persist a manual assumption and unlock projection.
There is no separate Historical Shadow button.
Until then Run Values is disabled; scenario construction and the engine also
refuse the incomplete basis. Never use the current shadow amount as historical.
Historical NSP and tax-test recalculation are not reconstructed.

Regression coverage: `tests/test_value_rollback_{data,scenario,ui,outputs}.py`
and the rollback rate-band test in
`tests/test_illustration_band_specified_amount.py`. Read-only live/native check:
`tools/app/verify_value_rollback.py --policy UE055782 --company 01 --output-dir
<directory>` captures the screenshot policy's six prior dates, recovered values
and shadow gate. `--policy UE000576 --project` also exercises the real engine on
a complete historical basis. Both preserve the loaded policy and write no DB
changes. Full basis limitations accompany reports/exports and the Policy
banner's tooltip.
For IUL, `--policy UE215622 --company 01 --date 2026-08-10 --project
--output-dir <directory>` verifies the selected historical basis and native
AV/AccumMTP/AccumGLP display without requiring bucket data. `--date` validates
only that recorded date; older dates can still have genuine target-change or
unverified-transaction blockers. IUL current/guaranteed engine regression:
`tests/test_illustration_iul_crediting.py`.
Add `--exercise-edits` to verify inline current/historical AV, shadow, DB option
and coverage edits through the native controls and Run Values without saving
or modifying the loaded policy.
Add `--exercise-record` to exercise every scalar/loan/TAMRA editor plus native
fund-cell editing, Apply and pending-draft guards on current and historical bases.
Expanded regression coverage: `tests/test_edit_record_scenario.py` and
`tests/test_edit_record_ui.py`.

## Illustration specified-amount basis

`illustration/plancodes/plancode_table.json` uses **SA_Basis** (specified amount),
exposed as `PlancodeConfig.sa_basis`. It replaces Expense_Basis and consolidates
the workbook's Target SA_Basis, EPU SA_Basis and Target BandLock controls.
Every plancode row explicitly specifies `CurrentSA` or `OriginalSA`; do not infer
it from SkippedCovRein or accept the retired keys.

**OriginalSA** uses each coverage's original amount for EPU (table or flat),
MTP, CTP and full surrender charges. Only MTP/MTP table-rating rates are locked
to that coverage's issue band. CTP, COI, EPU and premium-load bands follow current
combined specified amount; SCR is unbanded. Coverage increases capture their
own issue band; later increases/decreases must not overwrite it. Policy-change
rate refresh updates every active segment's COI/EPU band, not just the changed
segment. CurrentSA retains current amounts and unlocked target bands.

Live issue bands come from `PolicyInformation.cov_mtp_band(coverage_phase)`:
the primary-person type-M renewal `RT_BAN_CD`, interpreted with the coverage's
`BAN_STRUCTURE_CD` (structure 6 orders X/Y before A). This mirrors the workbook's
BandAtIssue source, not a reconstruction from current face. Missing/ambiguous
bands or missing original amounts block OriginalSA loading explicitly. Reload
live policies and resave older illustration snapshots whose original-band field
was populated with the current band.

OriginalSA still has no partial surrender charge. Its withdrawal fee reduces
AV but not specified amount, matching the workbook's Target SA_Basis fee gate.
Shadow-account basis remains a separate contractual setting.
Regression: `tests/test_illustration_sa_basis.py`,
`tests/test_policy_mtp_band.py`, and the policy-service/withdrawal tests.

## Illustration COLA coverages and surrender charges

Illustration base segments retain `CoverageSegment.is_cola` from the canonical
`CoverageInfo.cola_indicator` (`TH_COV_PHA.COLA_INCR_IND == "1"`). The Policy
coverage detail shows **Added by COLA: Yes/No**, including newly saved snapshots.
Reload live policy data before resaving older snapshots that lack this flag.

For company **26** FFL UL plans (`PlancodeConfig.is_ffl`, not the company display
name), COLA-added segments have zero effective surrender rates and charges.
The shared engine helper applies this to full surrender, loan availability,
withdrawals and elective coverage reductions; other coverages remain unchanged.
Values > Policy Values builds SCR/SC columns for **every** base segment, retaining
zero-charge columns. Live verification: `000289393 / 26 / NU1F3H00` has seven
segments (phase 1 non-COLA; phases 5-10 COLA). Use
`tools/engine/verify_cola_surrender.py` for a read-only live check and UI captures.
