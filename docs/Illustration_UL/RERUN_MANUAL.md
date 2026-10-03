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


## RERUN ☰ header menu and Plancode Table

The ☰ button at the left edge of the RERUN title bar (before the title) holds
reference views. **Plancode Table…** opens a read-only, non-modal window
(`suiteview/illustration/ui/plancode_table_view.py`) over
`suiteview/illustration/plancodes/plancode_table.json` — the same rows
`load_plancode` reads, through `plancode_table_rows()`. The rows hold product
rules and the illustration age overrides only; plan facts and rates come from
schema `rates` (see "Plancode configuration: plan facts from schema `rates`"
below). It is a dense sortable/filterable ledger with Plancode frozen; keys a row
does not carry show blank (never zero), and **Dump to Excel** opens the displayed
rows in a new unsaved workbook. A load failure shows an error box instead of an
empty table. Regression: `tests/test_illustration_plancode_table.py`.


## Plancode configuration: plan facts from schema `rates`

`load_plancode` (`illustration/models/plancode_config.py`) takes every plan fact
from UL_Rates schema `rates` through `illustration/models/plan_facts.py` (Robert
Haessly, 10/2/2026); the plancode table supplies product rules only:

| Field | Schema source | Not loaded |
| --- | --- | --- |
| `product_family` | `PLAN_DEF.PRODUCT_FAMILY` (UL and IUL -> engine `UL`; `ISWL`) | plan not loaded: error |
| `maturity_age`, `premium_cease_age` | `PLAN_DEF` | error |
| `cint_key` | `PLAN_DEF.CIRF_KEY`; a multi-fund IUL key (`FIXLNIUL,IUL`) names the fixed account in `PLAN_ATTR FUND_KEYS` (`FIXLNIUL,IULFIX09,IULINDEX09` -> `IULFIX09`) | blank |
| `gint` | PLAN `GINT` (one rate for every duration) | error |
| `dbd` | base `DB_DISCOUNT` (CELL, scale G) | GINT |
| regular loan rates | PLAN `LOAN_REG_CHG` (`loan_charge_rate_guar`), `LOAN_REG_CRD` (`loan_charge_rate_curr`) | error |
| preferred loan rates | PLAN `LOAN_PREF_CHG`, `LOAN_PREF_CRD` | no preferred loan option (0) |
| safety-net period | PLAN `SNET_PERIOD` by issue age (`safety_net_years(issue_age)`) | no safety net |
| corridor | PLAN `CORR` by attained age (`corridor_by_age`; `core/corridor_rates.corridor_factor`) | no GPT corridor (factor 1.0) |
| `shadow_plancode` | `PLAN_ATTR SHADOW_LEGACY_PLANCODE` | blank |

EPU, MFEE, the premium loads and the shadow account's rates are always the
schema rates in `IllustrationRates`, on the schema's own C/G scales; none loaded
means no charge. The shadow account requires scale S COI, `SHADOW_INT` and
`DB_DISCOUNT` (`RateLookupError` otherwise); scale S EPU, premium loads and the
target rate are optional. A table row that still carries a plan fact
(`plancode_config.DATABASE_KEYS`) fails `load_plancode` loudly.

**Corridor.** UL plans without `CORR` are CVAT-only plans (their minimum death
benefit is the deemed-cash-value test): no GPT corridor. The 27 GPT ISWL plans
carry the standard 7702 `CORR` in schema `rates` (loaded October 2026; in-force
CyberLife NAR matches it at attained age on 290/290 in-corridor policies). The two
CVAT ISWL plans (80136200, B11SB600) have no `CORR`. `tRates_CORR.json` is retired.
A GPT policy on a plan without `CORR` shows a RERUN load notice
(`rate_validation.plan_basis_warnings`).

**Illustration age override.** `IllustrationMaturityAgeOverride` /
`IllustrationPremiumCeaseAgeOverride` replace the `PLAN_DEF` ages on 16 rows where
the table had a different age (mostly 100 against 120/121); pending Robert's
decision whether they are intentional illustration caps. The RERUN load shows a
notice, and ISWL rejects an override.

`tools/rates/plancode_db_coverage.py --report <json> [--write]` reports what the
schema lacks per plancode (errors, "none" by product rule, changed values) and
strips plan facts from the table; rerun it after rate loads.
`ULRates.clear_cache()` also clears resolved configurations.


## RERUN rate source: UL_Rates schema `rates`

RERUN reads every UL/IUL rate from UL_Rates schema **`rates`** through
`suiteview/illustration/core/ul_rates.py` (`ULRates`); the legacy dbo
`Select_RATE_*` / `BANDSPECS` / `POINT_*` views are never read (Robert Haessly,
9/30/2026: where dbo and `rates` disagree, `rates` is the reference). ISWL, par WL
and term already had their own schema loaders. `ULRates` keeps the engine's rate
names and 1-indexed shapes: COI/BENCOI -> CELL `COI`; EPU, MFEE; TPP -> `PREMLOAD_PCT`;
EPP -> `PREMLOAD_EXS` (else `PREMLOAD_PCT` when the scale has no excess load); SCR
(issue-state cell first, else `**`); MTP/CTP (+ benefit type for BENMTP/BENCTP);
TBL1MTP/TBL1CTP -> `MTP_TBL1`/`CTP_TBL1` (not loaded = unavailable, never zero);
GINT and DBD -> PLAN `GINT`/`DB_DISCOUNT`.

- **Scales**: 1 = C, 0 = G. The shadow account reads scale **S on the base
  plancode** (`SHADOW`), including `SHADOW_INT` and `DB_DISCOUNT`; the legacy CCV
  plancode (`PLAN_ATTR SHADOW_LEGACY_PLANCODE`) is only a label.
- **Shadow target and premium timing**: LTGUL/LTGUL08 shadow targets use the
  scale-S CTP target and APS205's target-relief load rule. SGUL-family products
  use the product flag `ShadowLatePaymentForgiveness`: premiums exactly on a
  monthliversary are applied before shadow COI; premiums received strictly
  between monthliversaries are credited to the prior month after that month's
  deduction and earn a full month of shadow interest. Shadow net premiums are
  rounded to cents. With forgiveness the shadow keeps its own premiums YTD/to
  date (`MonthlyState.shadow_premiums_ytd/_to_date`), because a premium counts in
  the month the shadow credits it, not its account-value bucket month. Other
  shadow products credit a dated premium with receipt-to-monthliversary interest
  in rollback/from-issue replays (FPUL2 U0436543 -164.46 -> -0.28 vs XP).
- **Shadow withdrawals**: the accepted net withdrawal is subtracted from the
  shadow account (with receipt-to-monthliversary interest when the transaction
  carries an actual receipt date); the withdrawal fee and partial surrender
  charge are not (U0591866: +2.22 vs XP; the AV's gross amount gives -37.80).
  This does not change the existing option-B shadow NAR basis.
- **Dates**: `CALENDAR` rates (current COI, EPU, MFEE, loads) take each coverage
  year's rate from the scale window in effect on that year's start, so historical
  years of from-issue/rollback runs use the scale then in force; `ISSUE` rates use
  the window on the coverage issue date. Several windows and no date raise.
- **Cells**: PolView's `schema_rates.choose_cell` (exact, then unisex, class
  `0`/`*`, band `0`, state `**`); a unisex policy on a plan loaded under one sex
  uses that sex. The approved preferred-class COI fallback (R/P/T -> N, Q -> S)
  is unchanged.
- **Bands**: `PLAN_BAND` (latest spec on/before the POLICY issue date, lowest upper
  limit at or above the amount; riders on their own issue date). Unbanded plans are
  band 0; the ratchet break is band 1's upper limit. Issue-date band sets replace
  the old CZ $1 shift.
- **Not loaded**: a plancode missing from `PLAN_DEF` has no rates, so a required
  COI raises `RateLookupError` naming the lookup and saying the plan is not loaded.
- **IUL**: crediting parameters are the current-scale `IDX_*` fund rates on the
  illustration date (reinsurance block `R` for RGA). Illustrated rates,
  benchmark min/max and market returns also come from schema `rates` FUND rows:
  `IDX_ILL`, `IDX_BENCH_MIN`, `IDX_BENCH_MAX` and `MKT_RETURN`
  (`suiteview/core/index_rates.py`, `IndexAssumptionTables`).
- **Not from UL_Rates**: PoAV and interest bonuses stay in the
  plancode JSON tables; loan rates come from the plancode table.

Verified 9/30/2026 (live CKPR, one premium-paying policy per RERUN plancode, 168
policies; month-0 monthly deduction check plus a 10-year current projection, dbo
build vs `rates` build): 117 identical, 21 changed only where `rates` carries different data
(surrender-charge tables and state cells, COI tables, band limits such as
50,000 being band 1 on 1U130N2X/1U132100), 9 that failed on dbo now run, and the monthly-deduction
variance to CyberLife improved on 2 (1S134D00 -10.20 -> 0, 1S134I29 -3.40 -> 0) and
worsened on none. IUL strategy parameters equal the legacy indexed-account
source on 32 of 34 plan/reinsurance-block pairs (1U144800 is not loaded).
Rate-by-rate comparison:
`tools/rates/compare_rerun_rates_dbo_schema.py`.

**Data gaps (loud until loaded in `rates`)**: 36 plancode-table plancodes are not in
`PLAN_DEF` (08126100/200, 08228400-700, 1A130600, 1A130G29, 1G130A00,
1S133729/C29/E29/J2X/L2X, 1S134400/G29/J2X/K29, 1S135N00, 1U131400, 1U132300/500,
1U133400/600/900, 1U134300/800, 1U135600/I00/Q00, 1U144800, 1X130100/200,
NU1L2C00, NU1LAK00, NU1LAM00) and the CTR rider 1S534900; 1U135200, 1U135L00,
1U146000 and 1U146300 have no scale S (shadow account) rates; 1U135K00 has no
`MTP_TBL1` for table-rated coverages.
Tests: `tests/test_illustration_ul_rates.py` (with `tests/schema_rates_fake.py`)
and `tests/test_null_table_target_rates.py`.


## RERUN policy badge strip

Under the lookup bar RERUN shows PolView's badge strip (`PolicySummaryStrip`):
the same status chips, and Timeline / Notes / Copy, so the policy looks the same
in both apps. Notes are the same per-policy notes PolView keeps. The frame is
RERUN purple and PolView's Suggested actions are omitted. Facts are read live
(`build_policy_summary(..., live_reads=True)`); a saved case clears the strip
with a note until the policy is fetched live. Details: `docs/POLVIEW_CLAUDE.md`
"Usability layer". Regression: `tests/test_policy_badge_strip_shared.py`.


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

## RERUN CVAT deemed cash value and Necessary Premium Test

After TAMRA year 7 a **CVAT** policy with **Conform to TAMRA** on accepts each
premium only up to the Necessary Premium Test premium (RERUN `vNPT_Premium` →
`NPT Allowance0`): the gross premium that lifts the lower of the deemed cash
value (DCV) and the account value up to the NSP. The DCV is **not in the DB2
tables** — look it up on the **93 segment in CyberLife Online** and type it in
**Deemed Cash Value** on the Input panel, next to Conform to TAMRA (negative
values are allowed). The field is enabled only for CVAT with Conform to TAMRA
on; otherwise it stays visible, greyed, with an italic "Not applicable" note.
It is the DCV as of the projection's starting valuation date (the Edit Record
date for a historical run; a run from issue starts at 0), it rides in saved
cases, and a freshly loaded policy starts blank.

If the projection reaches a month where the NPT limits a requested premium and
no DCV was entered, Run Values stops with **Deemed Cash Value Required** — the
engine never assumes 0 or the account value. Before TAMRA year 8 the NPT is
unlimited and the DCV is not required. The Policy tab's "Deemed Cash Value"
reads "Not in DB2 — Input tab". The Values tab's **TEFRA and TAMRA** group shows
`Value_for_NPT`, `NPT_NSP`, `NPT_Premium` and the DCV roll (BDCV …
vEDCV) when they were computed. Prem to Maturity / Prem to Shadow Maturity still
solve CVAT policies with Conform to TAMRA off. The CyberLife history harness
(`tools/rerun/baseline_history_compare.py`) has no DCV source: a selection row
may supply `deemed_cash_value`, otherwise an NPT-bound replay is reported as
`blocked-dcv`. Formulas: `IMPLEMENTED_Calculation_Pipeline.md` Step 19.
Regression: `tests/test_illustration_deemed_cash_value.py`.

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

**FFL waivers are re-derived on a change.** When a policy change or a
withdrawal's face decrease recomputes the targets on an FFL plan, every active
type-4 waiver gets units = TRUNC(12 x TRUNC(monthly MTP, 2) / VPU, 3) and the
matching amount, as CyberLife does; RERUN keeps the recorded `vPWST_Units`.
This drives basis-1 charges (units x rate) and the guideline after-basis.
Non-FFL waivers keep their recorded units, because their target is built
from them. Verified on live CKMO face decreases of 2026-09 (company 26):
000335000, 000336209 and 000341289 reproduce admin's 4M units
(11.508 / 9.746 / 14.600), MTP and CTP exactly, and 000336209's post-decrease
monthly deduction (13.17). Type-3 PWoC charges and COI already matched.

Open items from that comparison (not changed):
- NU1F3 plans: admin's MT for 000292112 reconciles with the **CTP** rate
  table (73.12 before, 58.31 after), not `Select_RATE_MTP`. In a 30-policy
  NU1F3 sample, 9 matched CTP, 6 matched MTP and 15 matched neither, so the
  product rule needs business confirmation.
- `1U14L200` UL_Rates data: every CTP and TBL1 row is 0 and the MTP rows are
  about 2.4x admin (000336960; 0 of 33 in-force match). Admin's MT and CT
  both use one rate, as on sibling `1U14L100/300/400`. `1U1F4N00`'s zero CTP
  rows are only at issue ages 0-15/19, where admin also has no base target.
- 2026-09-29 UL_Rates target survey (live CKPR, up to 6 policies per in-force
  advanced plancode, plus larger samples for suspect plans):
  - `1U146700` shares `1U146600`'s `Index(TRGPREM)`. In all 66 sampled
    policies admin is about 12% above it for MTP and 8% above for CTP;
    `1U146600` matches exactly with the same benefits.
  - `1U147200` has no `RATE_BANDSPECS` rows. `get_band` returns None and
    the loader falls back to band 1, so policies with a face amount of at
    least 100,000 use band-1 rates. That affects 30 of 65 sampled targets
    and probably COI too.
  - `NU1L2A00/2B00/2C00`, `NU1LA100/AB00/AC00/AD00/AL00` (and `NB1LM100/200`)
    have `BANDSPECS` but no `POINT_PVSRB`/rate rows. `get_mtp()/get_ctp() or 0.0`
    therefore turns admin's CTP into a silent zero.
  - NU1F1/NU1F2/NU1FU plans have MTP rates but admin carries MT = 0.
    `1U135300`/`1U135E00` (+5.83/month) and `1U132100` (+2.00/month) differ
    from admin MT by a flat amount, while CTP matches exactly. That points to
    a formula difference, not a table error. Zero MTP rows on older 1S/1A plans,
    and the all-zero VUL/other rows, match admin's zero targets.
- Guideline recalc: after the decreases, the engine's GLP/GSP are 16-30 and
  310-510 below admin. Admin falls between after-solves that use the new and old
  MTP for the PWoC guideline charge.

GLP/GSP/7-pay monthly bases and their Before/After PV detail use the same
`target_waiver_charge()` helper as monthly deductions for PWoT basis 2/3.
Use each side's annual MTP/CTP; do not use recorded benefit units or any
table factor. CyberLife applies no table factor to the target-based charge
(Albert F06 on 26/000272626 and 26/000299857; approved 2026-10-01, fix E13),
although the RERUN workbook multiplied it by `1 + factor x base table`.
Charges are cent-rounded. Basis 1 and type-3 waiver rules are unchanged. The
earlier face-change fix covered monthly deductions but missed this guideline path.
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

IUL14 `1U145800` and IUL14NY `1U145900` both pay a 1.00% duration bonus from
policy year 11 (`BonusDurThreshold` 10). The New York plan sets
`BonusDurCapToExcessOverGuar: true`. Following RERUN v21
(`Rates_Control!ES73/ET73 = MIN(1%, PolicyRates!FO5 - PolicyRates!GJ5)`, i.e.
`sINPUT_Fixed_Int_Rate - sRates_GINT`), its bonus is one scalar per run:
`min(BonusDurRate, max(0, fixed account rate - GINT))`, with GINT 2.50%. That one
bonus is added to every crediting rate: the declared/fixed rate (WAIR UK) and
the indexed blend (UP) alike. The fixed account rate is the IUL fixed-strategy
illustrated rate (`iul_declared_rate`, defaulting to GINT exactly like the WAIR
declared rate), or the declared current rate for a non-IUL plan
(`BonusConfig.capped_for` / `fixed_account_rate` in `core/bonus_rates.py`,
applied by `calc_engine.resolve_bonus_config`). At a 3.10% fixed rate IUL14NY
credits 3.10% + 0.60% = 3.70% (IUL14: 4.10%). At 3.80% both add the full 1.00%
(4.80%). At or below 2.50%, including the GINT default, IUL14NY adds nothing.
The guaranteed projection uses the zero guaranteed bonus and caps it at GINT -
GINT, so it is zero. RERUN instead sets IUL14NY's guaranteed bonus to the
current-basis formula. The notes page adds "(THE LESSER OF 1.000% AND THE
EXCESS OF THE FIXED ACCOUNT RATE OVER THE GUARANTEED RATE)" after the bonus
amount.
Regression: `tests/test_illustration_bonus_rates.py`.

PolView's in-force paths (Account Values Interim AV Quote and surrender values,
GLP Exception forecast) set `iul_declared_rate` to the policy's current IUL
fixed-account rate excluding bonus (`polview/services/iul_fixed_rate.py`; see
the PolView manual's Account Values section), so IUL14NY's capped bonus is
measured against the rate CyberLife credits rather than GINT. The RERUN Inputs
tab is unchanged: its fixed strategy still defaults to GINT. Home-office
reinstatement rejects IUL (`IntCalcMethod` Blend) before any crediting.

## RERUN declared current interest rate

A declared-rate UL (not ISWL or IUL) loads its current crediting rate from the CIRF
fund for its plancode-table `CINT_Key` in UL_Rates schema `rates`: the latest
current-scale `CINT` rate on or before the illustration date (new-money plans
use `CINT_NEW`/`CINT_ROLL` only when the two agree), floored at GINT. With no usable
CIRF rate the plan GINT remains. The Input tab's Illustrated Rate defaults to this
sourced rate (ISWL's declared rate included); the provenance is
`IllustrationPolicyData.current_interest_rate_source`. For example, the 1U14 series
is credited 3.50% (FL4RPORT, effective 2024-04-01) against a 3.00% GINT.
Regression: `tests/test_illustration_declared_rate.py`.

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

A table-rating target rate (`MTP_TBL1` / `CTP_TBL1` in schema `rates`) that is not
loaded is unavailable, not zero: `ULRates.get_tbl1_mtp/ctp` return `None` and a
stored numeric zero stays zero. Unrated
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

**Principal-first option (fix E03, approved 2026-10-01).** CyberLife applies a
PL repayment to loan principal while `POL_LN_ITS_AMT` keeps accruing
(26/000289723: `LN_PRI_AMT` falls 149.01 a month). Illustration Control's
**Loan Repayments Pay Principal First** checkbox
(`IllustrationOptions.loan_repay_principal_first`) reorders arrears repayments
to preferred principal, regular principal, preferred accrued, regular accrued,
then variable principal and accrued. It is off by default because paying
interest first is conservative; it is saved with the case (`controls.
loan_principal_first`) and preserved on the guaranteed side. The CyberLife
history harness (`tools/rerun/baseline_history_compare.py`) turns it on.
Advance loans are unaffected.

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
Historical replay cash flows keep their actual receipt/effective date even when
bucketed to the next monthliversary. Rollback and from-issue runs credit dated
premiums from receipt through the bucket monthliversary (receipt and MV days
included), and apply the matching negative/loan-credit adjustment for
withdrawals, loans and loan repayments. This receipt-date adjustment is not used
for ordinary inforce forecasts or modal premiums assumed on monthliversaries.
CyberLife monthliversary replays also credit the base AV over the prior
monthliversary-to-current-monthliversary day span; monthly-compounding plans
retain the `(1 + i) ** (1/12) - 1` monthly factor. Loan interest still accrues
over the forward span to the next monthliversary (`InterestResult.
loan_accrual_days`); sharing the crediting span broke exact loan matches on
about 30 policies in the 304-policy baseline.
Projected monthliversary dates are always issue-date anchored and clamped to the
target month end, so day-31 policies project 4/30, 5/31, 6/30, 7/31 rather than
drifting permanently to the 30th after April. The policy loader counts a clamped
monthliversary as a completed month (issue 7/31, valuation 2/29 = 7 months), and
the CyberLife-timing projection steps from the prior row's date, so the
valuation month is never repeated.

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

**OriginalSA** uses each coverage's original amount for EPU,
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

## RERUN joint survivor ULs

RERUN illustrates the 12 FFL joint survivor plans (see the PolView manual's
"Joint survivor UL rates") with the normal engine: guideline/TAMRA caps and
recalcs, GEP, loans, withdrawals, face/DB option changes, solves and the Policy
Support GLP Exception tab. The FFL illustration workbooks (Estate Advantage,
Estate Pro 2) informed the rules, but CyberLife is the reference: they
approximate the joint COI and type in 7702 values.

- **Loading**: a lives-3 phase must be on a `PLAN_ATTR` LIVES=3 plan and vice
  versa (either mismatch raises). Each segment carries `JointLives` (both
  insureds and per-insured extras) and its `LH_COV_TARGET` ST target
  (`pi.targets.cov_surrender_target`); the single-life table/flat stay 0.
- **COI**: `rate_loader.load_segment_coi()` returns the JointCOI (scale 1
  current, 0 guaranteed); every COI path uses it. Face increases get both lives
  aged in step with still-active ratings restated.
- **Other rates**: `ULRates` reads MFEE, TPP/EPP (PREMLOAD_PCT), SCR, GINT and
  BENCOI from the plans' band-0, all-state cells like any UL; the plans load no
  MTP/CTP or EPU, so targets are held at the record (below).
- **Plan rows**: loads, fees, loans, GINT and maturity (N91/N71EP 100,
  N71EMR/EMJ 117, B11 121) come from `rates`. N91 SCR is the IAF per-unit table;
  B11/N71 use `SCR_PctOfSurrenderTarget` x ST (converted per unit at load).
  Corridor set 4 is standard to 94 and 1.00 from 95 (the plans' IAF CORR and
  CyberLife's negative NAR at 95); the corridor COI rate follows
  "RERUN corridor COI rate" above.
- **Targets**: MTP/CTP are VP/MS. `compute_target_premiums` and from-issue
  scenarios hold the record values (`held_at_record`).
- **7702/TAMRA/GEP**: the guaranteed joint COI is the mortality basis (approved;
  as single-life UL uses guaranteed COI). At issue it reproduces CyberLife's
  GLP/GSP to a median 0.01% (N71) and 0.09% (B11). N91 runs about 5% low (the
  year-1 87.5% PREMLOAD rule 5 is not modeled) and some rated policies differ
  2-20%; in-force runs start from the record values.
- **UI/report**: the Policy tab adds the joint insured, per-insured extras and
  COI basis; the report adds the joint insured.
- **Rate class / table changes** (Robert Haessly, 9/29/2026): on a joint policy
  the Rate Class Change and Table Rating Change dropdowns name the insured
  ("Primary: S", "Joint: B (150%)") and offer the plan's own JS_Q classes
  (`ULRates.joint_survivor_rate_classes`) and `JS_TABLE_PCT` codes; the change
  carries `metadata["person"]` ("00"/"01") and a joint change without it raises.
  The engine re-rates that insured in every joint phase (`JointLives` class, or
  its percent/table ratings replaced by `joint_survivor_coi.ratings_with_table`
  with flats kept) and reloads the phase's JointCOI. The blended COI is annual
  by coverage year, so a table applies from the coverage year starting on or
  after the change date. Before this, a joint rate class change had no effect
  and a table change added a single-life table on top of the blended COI.
- **Values > Joint COI** (joint policies only; the group sits after Shadow
  Account): per joint phase and month, the JSURVCOI year behind the COI on the
  run's scale (current, or guaranteed on the Guaranteed view): both lives'
  JS_Q, rated q, tpx/tpy/tpxy/tqxy, monthly p and the joint COI, beside the
  charged `COI Rate` (`MonthlyState.joint_coi_detail`, from
  `IllustrationRates.segment_joint`).
- **TEFRA/TAMRA Recalc > Joint COI sheet** (joint policies only): when the
  change re-rates a phase (rate class, table, or a face increase's new phase) it
  lists what changed and, from the coverage year of the change to the horizon,
  each life's guaranteed rated q (the 7702 basis) and the guaranteed and current
  joint COI before and after (`guideline_recalc["joint_coi"]`,
  `calc_engine.joint_coi_recalc_detail`). Other changes grey the sheet with a
  note: they keep both insureds' classes, ratings and ages, and the plans are
  unbanded, so a band change never moves the joint COI.
- **Known limitation**: a face increase on B11/N71 (percent-of-ST surrender
  charges) raises because the new phase's ST target is VP/MS-calculated.

Verified 9/28/2026 (87 in-force joint policies): month-0 COI/MD match CyberLife
to the cent for 77, the rest within $0.22 (stored rates differing slightly from
VP/MS). Current and guaranteed projections run to maturity for all. B11 surrender
charges are not DB-verifiable (UL `LH_POL_MVRY_VAL.CSV_AMT` is the AV).
Verified 9/29/2026 on 000335148 (B11) and 000231979 (N91, four phases): the Joint
COI group equals the charged COI rate every month of every scenario; rate class,
table and face-increase changes produce the recalc sheet.
Tests: `tests/test_illustration_joint_survivor.py`,
`tests/test_illustration_joint_coi_changes.py` and the RERUN cases in
`tests/test_joint_survivor_live.py`. Read-only tools:
`tools/rates/verify_rerun_joint_survivor.py '{}'`,
`tools/rates/exercise_rerun_joint_features.py` and
`tools/app/verify_rerun_joint_window.py`.

## RERUN Interest Sensitive Whole Life (ISWL)

ISWL (CyberLife advanced product line `I`; `PlancodeConfig.product_family =
"ISWL"`, from schema `PLAN_DEF.PRODUCT_FAMILY`) is illustrated in force with the
UL account-value mechanics (Robert Haessly, 9/29/2026). The fixed premium's
load, policy fee and benefit/rider premiums come out of the **gross premium**;
only the net goes into the account. The monthly deduction is the base COI only.
Rules are in `illustration/core/iswl_rates.py`:

- **Rates** come from UL_Rates schema `rates` only, never the dbo views
  (`rate_loader.load_rates` routes ISWL to `load_iswl_rates`; cells via PolView's
  `schema_rates` lookup). COI is the IAF annual rate per $1,000 / 12 (calendar
  windows by policy year), unrated: table ratings and flat extras are in the
  fixed premium (CyberDoc B10 makes substandard COI optional). NAR discounts at
  GINT (`DBD`). No MFEE, EPU, bands, UL targets (MTP/CTP) or benefit/rider COI.
- **Net premium** (CyberDoc D10 premium load rule 4, the only rule accepted):
  per billed payment `round(units x round((1 - PREMLOAD_PCT) x premium per unit, 2)
  x months/12, 2)`, using the coverage's stored `ANN_PRM_UNT_AMT` (schema `PREM`
  is the cross-check; a difference is noted). It ignores mode factors, fee and
  benefits.
- **Gross premium** is the billed `POL_PRM_AMT`, less each benefit/rider's modal
  premium (stored per-unit premium x units x `PLAN_MODEFACT` factor) from its
  cease date, as in B10's sample (1,557 -> 1,512 -> 1,362). A requested premium
  must be a whole number of billed premiums; partial, excess or guideline-capped
  premiums raise. With no schedule the premium bills in billing months only.
- **Guaranteed cash value**: the surrender value is `max(AV - surrender charge,
  guaranteed CV) - debt`, with the schema `CV` per unit interpolated monthly
  (`MonthlyState.guaranteed_cash_value`); the endowment value per unit is used
  at maturity. The COI never takes the AV below zero, so a premium-paying ISWL
  stays in force on its guaranteed values (B10 p. 402).
- **Surrender charge** follows `PLAN_DEF.SCR_RULES` (CyberDoc D10 p. 177 full
  surrender rules). `00`: none. Rule 6 (`60`): the dollar-per-unit schema `SCR`
  x units. Rule 5 (`50`): CKULTB04 percentage x the account value in excess of a
  free amount. For tables I2 and I3 the free percentage and flat charge are zero
  (allow code P), so the charge is `SCR_PCT(policy year) x AV`
  (`ISWLRateBasis.surrender_charge_pct`), 100% in years 1-2 grading to 6% in
  year 19 and 0 from year 20. CyberLife `FH_FIXED` SF history agrees: year-19 full
  surrenders were charged exactly 6.00% of the fund value, year-20 surrenders
  nothing. The charge is taken on the AV that the value is reported against: the
  monthliversary AV in force and the ending AV in the ledger, with the lapse test
  on its own AV. Tables I2, I3, I5 and 58 are verified (CKULTB04 print 08/12/2026:
  FREE_PCT 0, CHARGE_AMOUNT 0; table 58 also matches 54 company-01 `FH_FIXED` full
  surrenders to the cent; I5 rests on the print). Company 26 raises: CyberLife
  grades its rule-5 percentage monthly between policy years (44 surrenders on C9/58:
  `pct(d) + (pct(d-1) - pct(d)) x (12 - months since anniversary) / 12`), which is not
  modelled. Rule 5 on table C9 (all company 26), rule 5 combined with another rule, a
  plan with both `SCR` and `SCR_PCT`, and a withdrawal or charged face decrease inside
  a rule-5 charge period (the partial surrender charge is not modelled) raise.
- **COI rate basis** (`COI_RateBasis` row key from CKDRECUL `DULCVCRU`): `Annual`
  (calc rules 0/1, the default) divides the IAF rate by 12; `Monthly` (rule 2, the UL
  convention; e.g. B11SP400/40J/500, B11SB*, N61SB*) charges it as stored. B11SP400
  E0080318: CyberLife MD 4.14 = 12 x the annual-basis 0.35.
- **Corridor**: a non-CVAT ISWL (GPT or pre-TEFRA) needs schema `CORR`; without it the
  loader raises instead of dropping the corridor (F12S2N00 N8620667: AV 106,332.58 on a
  44,449 face, CyberLife MD 28.89, 0 without the corridor).
- **Single premium** (premium pay status 42, `IllustrationPolicyData.is_single_premium`):
  the single premium was paid at issue and CyberLife stores it as the modal premium. No
  premium is billed (`_split_requested_premium`), the premium load rules, `PREM`,
  `PREMLOAD_PCT` and `PLAN_MODEFACT` are not read (`ISWLRateBasis.single_premium`), and
  a requested premium raises. A premium-paying policy on such a plan still stops at its
  premium load rules.
- **Current interest** is the schema declared fixed-fund rate (`CINT_NEW`/
  `CINT_ROLL`) on the illustration date, floored at GINT; for plans with none
  loaded, the rate credited to the current fund buckets
  (`LH_POL_FND_VAL_TOT.VAL_PHA_ITS_RT`, value-weighted if they differ). Rows flagged
  `IMPAIRED_IND` 1 are used when no other bucket exists: they hold the fund's unloaned
  value, the collateral being in `LH_FND_VAL_LOAN` (B11SB200 26/000321893: AV 21,077.73
  = F1 12,752.46 + loan 8,325.27). The
  source is `IllustrationPolicyData.current_interest_rate_source`.
- **Guaranteed side** keeps the billed premium and locks the requested billed
  payments (`lock_values(..., iswl=True)`).
- **Not supported (loud errors)**: CVAT ISWL (80136200's NSP corridor), more
  than one base phase, limited-pay, premium load rules other than `400` on a
  premium-paying policy, unknown
  bill forms, schema facts that disagree with the plancode row, and missing
  schema rates. Nonforfeiture (ETI/RPU/APL) after stopped premiums is not
  modelled. CyberLife's per-premium interest buckets are credited as one account.

Plancode rows are generated from schema `PLAN_DEF` and plan rates by
`tools/rerun/build_iswl_plancode_rows.py`; the loader re-validates maturity,
premium cease age, GINT/DBD and loan rates at run time. All 28 in-force ISWL
plancodes have rows (`CanIllustrate` true: only IUL is blocked). Reconciled to
CyberLife: 81335200, 81335100, 80334900, 80335000 (CEIL88) and 81335600,
81335500, 80335400, 80335300 (CEIL97). The rule-5 surrender charge plans 80333729,
80333829, 80334729, 80334829, 81333529, 81333629, 81334529, 81334629, 80110429 and
81110229 now run: on 10/1/2026, 102 test-matrix policies on them that had stopped
at the missing `SCR` cell all calculated, and 75 matched CyberLife's valuation MD
to the cent. The other 27 are ETI/RPU (status 44/45, not modelled) except
10497580 ($0.02). The rest stop at rate loading with the exact missing item until
schema `rates` loads it:
- COI past age 100 for 80110529 and 81110329, which mature at 103.
- `PLAN_MODEFACT` rows for the 56070 series (FN2VN*/MN2VN*), which have no
  surrender charge.
- The CVAT corridor for 80136200 (also missing its F/N `CV` cells).

October 3, 2026 added rows for the premium-paying 56070 plans FS2VN200, MN2VN400 and
MS2VN200, and for 46 single-premium plans (`--single-premium`; B11S*, B71S*, F*2S*,
M*2S*, N61SB*, NA1SP900, NB1S*; B11SB600 is CVAT). `AgeCalc` now follows
`CYBERLIFE_PDF` `DBSAGCAL` (0 = ANB) and `COI_RateBasis` follows `DULCVCRU`. Of the
275 single-premium test-matrix policies, 30 (B11SP400/40J/500, CVAT) match CyberLife's
valuation MD to the cent once the CVAT corridor ships. The rest stop loudly: company-26
graded rule-5 charges (76), missing `CORR` (102: the F/M pre-TEFRA plans, NA1SP900,
NB1S*, FS2VN200, MN2VN400, MS2VN200), missing `CV` (50: B71SP*) and COI past the loaded
ages (16).

**Verification** (live, read-only): `tools/rerun/verify_iswl_rollforward.py`
restarts each of the last six months from CyberLife's recorded AV
(`LH_POL_MVRY_VAL`), feeds the processed PR receipts as whole payments and
compares the net premium, COI, interest and AV. On 9/29/2026, 93 sampled
in-force policies across all 28 plancodes gave 32 runnable policies (nine
plancodes, every billing mode and form). All 190 checked months passed: net
premium and COI to the cent, AV within $0.10 after the receipt-date interest
stub. The remaining cents are CyberLife rounding each bucket's interest; the
six-month drift is at most $0.47 where no month was excluded. Months with loans,
surrenders or premiums paid from the AV (`SA`/`PQ`) are excluded and listed.
13034048 is a record anomaly: its record shows issue age 32 and 25.982 units,
but CyberLife charges the issue-age-33 COI (67-segment C rate 8.72) on a
$25,000 NAR and credits a 25-unit, 11.76 net. The check reports it.
`tools/rerun/run_iswl_illustration.py <policy>` runs Run Values end to end and
prints the B10-style ledger. Supporting read-only probes: `find_iswl_policies.py`,
`sample_iswl_receipts.py`, `probe_iswl_history.py`, `probe_rerun_load.py`,
`count_iswl_riders.py` (tools/rerun) and `tools/rates/inspect_schema_plan.py`.
Tests: `tests/test_illustration_iswl.py`.

## RERUN participating whole life (par WL)

A traditional policy whose base coverage participates in dividends
(`is_par_whole_life`: not an advanced product, `DIV_PTP_TYP_CD` not blank/0) opens
in RERUN's **par WL workspace** instead of the UL/ISWL tabs (Robert Haessly,
9/29/2026): **Policy** (the in-force snapshot), **Illustration Inputs** (a par WL
input screen), **Values** (monthly debug pages), **Report** (the illustration pages,
printed to a landscape PDF) and
**In-force Check** (CyberLife's current values against SuiteView's). Run Values
projects monthly from the valuation date; the ledger is annual. Code:
`suiteview/illustration/core/parwl/` (engine, rates, NSP, premiums, loader, checks),
`models/parwl.py` and `ui/parwl_*.py`. NY blended insurance riders (product line B)
and policies on extended term (status 44) are refused with an explanation; saved
cases are not available for par WL yet.

**Data** comes through PolicyInformation. The dividends section reads the real
segment 14/15/13/19 columns (`LH_PAID_UP_ADD.PUA_AMT`, `LH_ONE_YR_TRM_ADD.OYT_ADD_AMT`,
`LH_PTP_ON_DEP.PTP_DEP_AMT`, `LH_APPLIED_PTP`/`LH_UNAPPLIED_PTP` per-unit `CSH_AMT`/
`PUA_AMT`/`OYT_AMT`, `PUA_UNT_QTY`, `DIR_RCG_DIV_IND`); rows dated 12/31/9999 are
current, rows dated at an anniversary with `ANV_PRC_CRN_IND` 1 are the values going
into it. Month-year numbers count months from January 1900. Coverages add
`traditional_facts` (pay-up date, dividend key = class + base series + sub-series,
NSP basis, stored `LOW_DUR_*` values, cease reason), substandard ratings add the
annual extra premium per unit (`SST_XTR_UNT_AMT`), trad loans add the advance /
arrears code and interest paid-to date, and `LoansSection.get_loans` now counts only
the current `LH_CSH_VAL_LOAN` row (anniversary rows are history).

**Rates** come from UL_Rates schema `rates` only: `CV` (scale G, sub-series cells),
`PREM` (cross-check), the dividend structure (`D`/`R` records, or `L`/`P` when the
placed values carry `DIR_RCG_DIV_IND`; the coverage's own dividend key when schema
rates holds it, e.g. converted 14456194), `PUI` for PUA riders, `LOAN_REG_CHG` and
`RATE_MODEFACT`. Term riders need no rates. PUA/RPU net single premiums are calculated
from the bundled CyberLife mortality tables (`plancodes/cyberlife_mortality.json`,
built from `Mortality Tables (Cyberlife).xlsx` by `tools/rerun/build_cyberlife_mortality.py`):
curtate whole life to the table's last age, times `i / ln(1 + i)` for age-last-birthday
tables.

**Rules reproduced from the record** (each is a test in `tests/test_illustration_parwl.py`):

- Modal premium: each coverage's premium plus its benefits modalized together, each
  substandard extra on its own, plus `round(fee x fee factor, 2)`. `MULTIPLY_ORDER` 2
  modalizes the per-unit rate first (`round(units x round(rate x factor, 2), 2)`).
  `POLICY_FEE_RULE` Z (B711E100, B111A100) adds the annual fee to the annual premiums
  and rounds once (`round((premiums + extras + fee) x factor, 2)`; the cent this moves
  shows as rounding). Bill forms H and F use the PAC factors; the fee band is chosen by
  base units. The billed premium is compared as of the valuation date (a rider expiring
  at the paid-to date is still billed). A billed premium that still differs (a forced
  premium) is kept, the difference carried with the base.
- Dividends at the anniversary ending policy year `t`: `round(units x rate(t), 2)` on the
  coverage and `round(round(additions / 1000, 3) x PUA rate, 2)` on its additions held
  going in; the PUA/OYT face per $1,000 of additions is
  `trunc4(PUA cash x trunc7(base PUA / base cash))` (the base value when the additions
  earn the base rate). A PUA rider's premium-bought additions earn as units; whether
  its dividend additions earn on that day's purchase is read from the record (NY riders
  NB1PU300/NB1PUA00 do, 08129700/08129800 do not). No dividend at maturity. The base
  coverage earns its dividend only while its premiums are paid to the anniversary, once
  it is paid up or on reduced paid-up (status 41 14762446, paid to 2023, was paid only its
  additions' dividend).
- Options: 1 cash, 2 premium reduction (applied to the next premiums, the rest to the
  secondary option), 3 deposit (interest `round(balance x rate, 2)` credited before
  the new dividend), 4 paid-up additions, 5/6/7 OYT (6: the total OYT is limited to the
  base coverage's next-anniversary cash value, the additions' OYT bought first, the
  coverage's unused dividend to the secondary option), 8 loan reduction. The NY PUA
  riders' dividends always buy additions (CyberLife applies them as option 4 under
  options 2 and 6); 08129700 follows the policy's option. Read from the rider's applied
  dividends.
- Values on a monthliversary `k` months into a year: base cash value
  `units x round((CV(t-1) x (12 - k) + CV(t) x k) / 12, 2)`, additions
  `round(additions / 1000 x (NSP(x) x (12 - k) + NSP(x+1) x k) / 12, 2)` (the 62Q1 quote).
  Reduced paid-up coverages are valued at their NSP basis.
- Loans: in advance, `principal / (1 - r)` at each anniversary, the unearned part
  refunded in the payoff; in arrears, `principal x r` accrued monthly and capitalized.
- Reduced paid-up: premiums stop and the net value (base, additions and deposits with
  NFO codes 3-5, less the loan payoff) buys `net / NSP` units; dividends switch to
  the RPU record. A paid-up status (e.g. 41) whose placed base dividend carries
  `RPU_VAL_IND` is reduced paid-up too (8O1C1000 12197587/12197588: fractional units,
  stored RPU NSPs, paid on the P record); kept PUA rider additions still earn.

**Policy** page (RERUN purple, sized to its content): the policy facts, the coverages
table in PolView's columns (phase, form, plancode, type, dates, amount, units, issue age,
gender, class, table rating) plus the par WL premium per unit, annual premium, dividend
key and NSP basis, and the supplemental benefits as form-number buttons that open the
same Benefit Detail card as RERUN's UL Policy tab (`policy_tab.show_detail_dialog`).

**Inputs**: current dividend scale on/off; dividend option, secondary option and dated
option changes; deposit interest; convert to reduced paid-up at a policy year or date;
new loans and repayments; pay loan interest in cash; PUA rider payments (bought at PUI
rates; greyed when the rider has ceased); illustrate to age. Transactions are entered
as a policy year (its anniversary) or a monthliversary date. The guaranteed columns
are a second run with no dividends. **Values** pages: Summary, Premiums, Dividends,
Paid-Up Additions, Cash Value, Loans, Deposits & OYT, Death Benefit, with a Current /
Guaranteed switch and an Anniversaries-only filter. Each anniversary's dividend buys
the next year's OYT as the previous year's expires.

**Report** (Robert Haessly, 9/29/2026: "a PDF in the same style as the UL reports,
except landscape"): `core/parwl/report.py` builds the pages and `ui/parwl_workspace.py`
(`ParWLReportView`) shows them as print-preview sheets with **Print to PDF** (Letter
landscape, the shared output folder) and **Ledger to Excel**. The page style is the UL
report's (`ui/report_pages.py` is the shared printer, sheet and settings code; the
text layout helpers are `core/report_text.py`): a header on every page (run date,
company, page x of y, title, prepared-for), a cover with the disclaimer, the policy
block and "THIS ILLUSTRATION ASSUMES THE FOLLOWING" (premiums, the dividend option and
its changes, deposit interest, the current loan and its payoff, new loans, repayments
and payoffs, PUA rider premiums, the reduced paid-up conversion), annual ledger pages
in five-row blocks under GUARANTEED / NON-GUARANTEED VALUES banners, and a notes page
(the guaranteed and non-guaranteed lapse or maturity statement, dividend and value
disclosures, loan interest, other coverage). The ledger columns follow the illustration
team's par WL illustrations (samples of 000253762, 000282131, 14561998, 41056071 and
E0017960): age, year, premium outlay (premiums plus PUA rider premiums), loan payments,
new loans, guaranteed cash value and death benefit, annual dividend, PUA cash value,
cash value, death benefit, total loan, dividends on deposit, base and rider paid-up
additions and one year term. A column the illustration never uses (no loans, deposits,
rider or OYT) is left out; the page is as wide as the ledger (at least the UL's 112
characters) and the PDF font shrinks from 9pt to fit it (159 characters at 7.2pt).
Values are end of year, net of the loan payoff (advance interest for the following
year is not in the loan column).

**Verification** (live, read-only, 9/29/2026): `tools/rerun/find_parwl_policies.py`
samples the six most common plancodes with CV and dividends loaded (B711E100,
NB1XSL00, B111A100, 8L1F1500, 8O1C1000, 8X1D1500: about 44,000 in-force policies) by
dividend option, RPU, waiver, paid-up, loans, riders, benefits and mode;
`tools/rerun/verify_parwl_inforce.py` runs every in-force check and a projection.
On the 78-policy sample and a second 221-policy sample (three per category: about 4,300 checks) every premium, cash value, per-unit dividend, dividend dollar, addition
roll-forward and advance-loan check matched CyberLife except: RPU NSPs, within 0.11
per $1,000 on some policies (two L5 4.5% policies store 357.67 and 357.70 at the same
age 54, so the difference is policy-specific, not the formula); one billed premium
(8X1D1500 14121291, 34.17 against 34.50) that is kept as billed. The par WL workbook
(`Par WL Inforce Illustration v2.3.xlsx`) was used for its NSP table and 62Q1 notes;
it values the first row's dividend on the additions after that anniversary, which
CyberLife does not. Other tools: `run_parwl_illustration.py` (ledger in the console;
`--pages` prints the report pages, `--pdf` writes the landscape PDF and reports how
much of the page width the text fills) and `tools/app/verify_rerun_parwl_window.py`
(the live window).

**Known limits**: direct recognition's L/P scales are used as placed; CyberLife pays
loaned direct recognition policies those values with no further loan adjustment
(14763679, 12795388, 13483291, 14110388); OYT cash value is taken as zero; APL, ETI and vanishing
premium are not illustrated; PUA rider planned premiums are not on the record and must
be entered as payments; plancodes without `CV` or dividends in schema `rates` (e.g.
B711G100 has no CV) stop at loading with the missing item named.

## RERUN indeterminate premium term (IPT)

A traditional term policy with indeterminate premiums (`is_indeterminate_term`:
`LH_BAS_POL.IDT_PRM_IND = 1`, base product line N; about 169,000 in-force policies, almost
all B15/B75 ART plans) opens in RERUN's **term workspace** (Robert Haessly, 9/30/2026):
**Policy** (the in-force snapshot: facts, coverages in PolView's columns, benefits as
detail buttons), **Illustration Inputs** (the premium mode to illustrate, riders and
benefits to drop, illustrate to age), **Values** (every premium due date and each element
of it, current and guaranteed), **Report** (the illustration pages, landscape PDF) and
**In-force Check**. Code: `suiteview/illustration/core/term/` (loader, rates, engine,
checks, report), `models/term.py` and `ui/term_workspace.py`; shared with par WL:
`core/fixed_premium.py`, `core/inforce_check.py`, `core/ledger_report.py`,
`ui/illustration_pages_view.py` and `ui/policy_snapshot_widgets.py`. Saved cases are not
available for term yet.

**Template and corrections.** CyberLife's own term illustration (TERM - D0194819.pdf,
B15TG100 "ART12", issue age 62, 100 units, monthly 202.00) prints the right current
premiums but a wrong guaranteed column; the illustration team's review ("Re: D0194819 -
ART Policy Illustration", 8/27/2026) asked for the level-period guaranteed premium to be
the current premium (808.00, not 2,396) and for guaranteed renewal premiums at the
policy's own mode (year 11: 14,076, not CyberLife's annual-mode 14,052). SuiteView does
both, and also corrects CyberLife's last year (it repeats year 32's current premium,
79,512; age 94's 843.06 rate gives 84,384).

**Data** comes through PolicyInformation: the coverage's stored rate for the current
premium period (`ANN_PRM_UNT_AMT`), the renewal structure (`TraditionalCoverageFacts`:
`INT_RNL_PER`, `SBQ_RNL_STR_DUR`, `SBQ_RNL_PER`, `RENEWABLE_PRM_CD`, `IDT_PRM_GUA_PER`),
the next period's rate on the renewal rates segment (67, `LH_COV_INS_RNL_RT` type C,
`RNL_RT` in cents: 13063 = 130.63), substandard extras (`SST_XTR_UNT_AMT`, `SST_XTR_PCT`,
cease dates) and benefits (`BNF_ANN_PPU_AMT`, rating factor, pay-up and cease dates).
**Rates** come from UL_Rates schema `rates` only: the coverage's `PREM` cell on scale C
(the window in effect on the valuation date) and G (at issue), benefit `PREM` cells
(waiver `30`, `3G`...; a benefit with no G scale uses its C rates, noted), and the base
plancode's mode factors. Riders not loaded (children's term B1582000) keep their stored
level rate, noted.

**Rules reproduced from the record** (each a test in `tests/test_illustration_term.py`):

- Premium periods come from the renewal structure: the initial period of `INT_RNL_PER`
  years (repeated to `SBQ_RNL_STR_DUR`), then periods of `SBQ_RNL_PER` years
  (D0194819: 1-10, then yearly; one-year-level B75TL500: yearly). `NXT_CHG_DT` is not
  reliable (E0243681: 2044 on a yearly-renewing plan).
- The stored rate is the rate of the period containing the last processed anniversary
  (NLP00116, paid only to 10/2025, still stores year 11's rate); it bills on both scales
  in that period. The next period's current rate is the renewal rate on the record;
  later years the C schedule; the guaranteed scale uses G after the current period.
- Modal premium per element at the illustrated mode: `MULTIPLY_ORDER` 2 `units x
  round(rate x factor, 2)` plus `round(fee x fee factor, 2)` (D0194819 202.00);
  `MULTIPLY_ORDER` 1 with the fee at the premium factor (fee rule 3) or fee rule Z rounds
  the annual total once, fee included, each element's annual premium in cents
  (E0000485 (335 + 60) x 0.0864 = 34.13; E0041873 round(500.019 x 1.84, 2)).
- Table extras are the coverage rate x (`SST_XTR_PCT` - 1) per unit, re-rated with the
  coverage rate after the current period; flat extras keep their amount to their cease
  date. Benefit premiums stop at the benefit's pay-up date; a benefit that does not renew
  (`RNL_RT_IND` 0, e.g. FF902782's ADB) keeps its stored rate, a renewing one (the
  premium waiver) follows its own `PREM` schedule.
- A plan with no `RATE_MODEFACT` rows (`MODE_PREM_TABLE` 0: CyberLife takes its modal
  factors from the plan description, not in schema `rates` - B15TI300/B15TI200 "SIGTERM")
  uses the first factor set of its plancode family (the first four characters, most
  common first, the policy's bill form before the other) that reproduces the policy's
  billed premium, noted (FF905195: (300 x 0.55 + 300 x 0.39 + 60) x 0.0864 = 29.55, mode
  table 352; company 26 monthly direct 000332291 bills at the PAC 0.0864). When none
  reproduces, the In-force Check shows why and Run Values refuses.
- The billed premium is the premium due at the paid-to date. CyberLife bills a renewal
  at the new rate once it has rerated the policy (15044388, E0243681) and at the stored
  rate until then (E0096685, E0166485, IP054194): the check accepts either and says
  which; the projection charges the new rate from the renewal anniversary.
- Due dates run every mode period from the paid-to date to maturity; premiums in arrears
  are not illustrated (noted). The first ledger year holds only the premiums still due.

**Report**: the UL page style (`core/ledger_report.py`), CyberLife's columns: age at the
end of the year, year, NON-GUAR CONTRACT PREMIUM, and under GUARANTEED VALUES the
contract premium, cash value (none) and death benefit, plus rider coverage when riders
are kept. The cover shows the plan, form, premium class, the premium structure (level
years, then annual renewal), extras and illustration choices; the notes page explains
indeterminate premiums and lists other coverage.

**Verification** (live, read-only, 9/30/2026): `tools/rerun/find_term_policies.py` samples
the most common TERM plancodes with PREM C and G loaded by level period, level period
ending, ART period, children's term and other riders, premium waiver and other benefits,
table ratings, flat extras, substandard types 2 and 4, waiver status, every mode and
bill forms H/F; `tools/rerun/verify_term_inforce.py` runs every check and a projection.
On 247 policies (the ten most common plancodes and D0194819) 815 checks match; the one
difference left is E0124485, an annual bill paid to April on a May anniversary whose
billed premium blends two years' rates (kept as billed, noted). A second sample of 160
policies over the next 18 plancodes (B15TA/TB/TE/TF/TG/TI, B75TN; companies 01, 06 and
26) matches 516 checks; three company 26 SIGTERM policies are refused with the reason
shown (two carry the B1582800 rider below; 000329562 bills at the PAC factor with the fee
rounded apart, 130.46 + 5.18 = 135.64, a combination no loaded plan uses). Other tools:
`run_term_illustration.py` (ledger, `--pages`, `--pdf`) and
`tools/app/verify_rerun_term_window.py` (the live window).

**Known limits**: premiums in arrears are not illustrated; off-anniversary annual bills are
kept as billed for their period; riders not loaded in schema `rates` bill their stored
rate every year; company 26 SIGTERM policies with the NY children's rider B1582800 are
refused (that rider has no mode factors in schema `rates` and bills at 0.085 monthly:
000341291 (290 + 60) x 0.0864 + 50 x 0.085 = 34.49); saved cases are not available.
