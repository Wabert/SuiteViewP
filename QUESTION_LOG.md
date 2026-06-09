# Illustration Engine vs RERUN — Overnight Work Log & Questions

**For Robert to review in the morning.** Started 2026-06-08 evening. I'm working
autonomously through the calc-engine validation + policy-change development you
asked for. This file holds (1) questions for you, (2) decisions/assumptions I made
without you, and (3) a running progress log. I'll append as I go.

---

## A. Questions for you (actuarial / product / scope)

> None blocking yet — I'll add here as they come up and proceed under a stated
> assumption so the work doesn't stall.

1. **U0492070 shadow/CCV current value — where does it live in DB2?** RERUN injects
   the current shadow AV (`sInput_CurrentShadowAV` = 4872.53) at the valuation date.
   In the local fixture BOTH `pi.gav` (IX target) and `pi.ccv_target` (LH_COV_TARGET
   'CV') are **null**, so the engine seeds the shadow at 0 and the CCV/shadow
   projection can't be validated locally. (a) What DB2 table/field holds the *current
   CCV account value* (the running value, not a target/required premium)? Is
   `ccv_target` it, or is it in `LH_POL_MVRY_VAL` / a CCV accumulator? (b) **Work
   laptop:** please re-export U0492070 (and U0656998 if it has a shadow) including
   that value so the shadow path can be validated. Engine seeds shadow from `gav`
   today (the GPT GAV) — conceptually wrong for a CCV policy.

2. **TAMRA 7-pay basis** (I built `calculate_7pay_premium` in `guideline_calc.py`):
   I used the GLP/GSP-style numerator (SA·A_{x:n} + PV of expense loads) over a
   7-year annuity at the 4% §7702 interest floor. Two things to confirm: (a) does
   the 7-pay premium include the expense loads the way GLP does, or is it a *net*
   premium (no expense load)? (b) interest floor 4% (I assumed) vs something else?
   RERUN computes its 7-pay on the `Guideline_Premiums` sheet (CalcEngine `KY` ←
   col 6) — penny-validation needs the guaranteed-COI mortality table (live
   UL_Rates), so this is a work-laptop check. You said my method may differ from
   RERUN's and that's OK — flagging for confirmation.

3. **GSP $0.05 rounding** — confirm RERUN's `KS = INT(GSP/12*100)*12/100` (floor
   GSP to a monthly-divisible cent) is the intended admin convention. It's cosmetic
   where TEFRA is off (all 4 current cases), but it'll matter once force-out is
   active (the policy-change cases). I deferred matching it until then; easy to add.

4. **Face-change processing detail** (from the RERUN reference I built, see §D): on a
   face INCREASE, RERUN recalcs GLP/GSP at the *anniversary* of the increase year,
   then the new segment appears the *following month*. Confirm: (a) new-segment
   issue age = attained age at the increase (so it gets its own COI rate row)? (b)
   the ~1-month lag between the anniversary guideline recalc and the segment taking
   effect — intended, or a RERUN timing quirk?

---

## B. Decisions / assumptions I made autonomously

- **Per-case option toggles** (TEFRA/TAMRA/exception/exact-days) are read from each
  RERUN Saved Case's `sINPUT_*` inputs so the engine run mirrors RERUN exactly.
- **Policy-change test cases** (face decrease, face increase, DBO change): I'll
  CONSTRUCT these by taking an already-validated inforce policy and modifying its
  future specified-amount / DBO input vectors — in RERUN (via the COM tool writing
  the input vectors) and in the engine (via `PolicyChangeEvent` / the projection
  inputs) — then comparing. I'm not creating brand-new policies.
- **GSP $0.05 difference** (found on U0688012): RERUN floors GSP to a
  monthly-divisible cent (`KS = INT(GSP/12*100)*12/100`). Harmless where TEFRA is
  off (force-out = 0). I'll resolve it when I hit a force-out-active (policy-change)
  case where it actually binds.
- **"Values tab column order/grouping/expand-collapse":** I'm building the
  RERUN-style column grouping + ordering + a detail-level selector into the
  comparison tooling first (verifiable offline). I'll also align the live PyQt
  `values_tab.py` column order to RERUN where low-risk, but interactive
  expand/collapse in the live UI I can't fully verify on the minipc — flagged for
  the work-laptop AI.

---

## C. Progress log

- **Done before tonight:** RERUN COM bridge (`tools/rerun_com.py`), engine dump
  (`tools/run_engine_case.py`), aligned diff (`tools/compare_case.py`); validated
  **U0688012** (table-2 + PW) to sub-penny after fixing the ExactDays interest
  day-count bug in `interest_calc.py`.
- **Tonight:**
  - **U0492070 (CCV/shadow + flat extra):** base AV chain, full deduction breakdown,
    interest, and values match RERUN to **sub-penny**. **Engine fix:**
    `monthly_deduction.py` added `flat_extra/12` at full precision; RERUN truncates the
    monthly flat to cents (`TRUNC(flat/12,2)`) — added `_trunc2()` and applied it
    (closed a constant ~$0.08 base-COI gap). Remaining: shadow BLOCKED (CCV value
    missing from fixture, see Q1); GSP $0.05 rounding (cosmetic, TEFRA off).
  - **U0656998 (LTR rider + GIO):** base AV chain, deduction, interest, values now
    match RERUN to **sub-penny**. **Engine fix:** the rider COI ignored the rider's
    substandard table rating — the LTR rider carries table 'D' (=4) in DB
    (`LH_SST_XTR_CRG` cov 2), so RERUN charged `rate*(1+0.25*4)=2x` while the engine
    used the raw rate (undercharged 2x: 18.4 vs 36.8). Now applies
    `rate*(1+factor*table)+TRUNC(flat/12,2)` to riders too. The "GIO" was a red
    herring: the policy's GIO (type 7, ULGIO86) **ceased 2023-08-22**, so it's
    correctly excluded by both engine and RERUN — no separate GIO charge. GSP $0.05
    remains (cosmetic).
  - **Three engine bugs found+fixed tonight (all "engine wrong, RERUN right"):**
    (1) ExactDays interest used 365/12 instead of actual `days/365`
    (`interest_calc.py`); (2) base-COI flat extra not truncated to cents
    (`monthly_deduction.py` `_trunc2`); (3) rider COI ignored rider substandard
    (`monthly_deduction.py`). No test regressions (3 `md_check` failures are
    pre-existing — need live DB2).
  - **Comparison harness extended:** `tools/calc_compare_map.py` (grouped,
    RERUN-ordered column map + detail levels), `compare_case.py` rewritten for
    group/detail/collapse + drill-down, `query_local_fixture.py` (policy & rates DB),
    `inspect_illustration_inputs.py`. All four cases' base calc validated; only
    cosmetic GSP rounding + data-gap shadow remain.
  - **Rates group added** to the harness (`calc_compare_map.py`) and validated on
    U0688012: COI rate, corridor, EPU, SCR, interest all match (COI rate to 5e-6 =
    RERUN's `ROUND(rate,5)` vs engine full precision — cosmetic).
  - **TAMRA 7-pay calc built** — `calculate_7pay_premium` in `guideline_calc.py`
    (PV/commutation method; the GLP numerator over a 7-year annuity). Unit-tested
    against actuarial identities (`tools/test_commutation_glp.py`, now 25 green:
    `7pay*ä7 == GLP*än`, `7pay > GLP`, `pay_years=n → GLP`, composes with
    `glp_on_change`). Penny-validation vs RERUN needs live mortality (work laptop).
  - **Committed + pushed** the foundation to branch
    `feat/illustration-rerun-validation` (3 fixes + harness). TAMRA + override
    tooling + this plan in a follow-up commit.

---

## C.1 CORRECTION — guaranteed COI IS in the local DB (2026-06-08, later)

My earlier claim that guideline/TAMRA validation "needs live rates" was **wrong**
(Robert caught it). The local `rates.sqlite` `Select_RATE_COI` has a `Scale` column:
**Scale 1 = current** (illustrated, what the engine charges, matches RERUN — confirmed
by `Select_SCALE_COI`), **Scale 0 = guaranteed** COI. So the guideline/TAMRA calc is
fully computable **offline**. Wired `coi_scale` into `rate_loader.load_rates`
(`coi_scale=0` → guaranteed) and added `tools/validate_guideline.py`.

Robert confirmed: GLP mortality = the guaranteed COI (scale 0), 7702 maturity = 100.

**Local GLP/GSP vs admin (issue-age, endow 100):** the two methods **bracket** admin —
commutation (closed-form, no corridor) ~17-37% LOW; iterative (full engine, includes
corridor) ~19-38% HIGH. U0656998 worst on commutation (omits the LTR rider's QAB
charge in the GLP). So: data unblocked, but matching admin *precisely* needs
calibration (corridor treatment, rider QAB charges, exact expense allowances) — this
is the "a little different, reasonably well" Robert flagged. **All 4 cases are
TEFRA-off**, so GLP/GSP don't drive AV (force-out disabled) — they're reported values,
and the policy-change AV/segment/MD machinery is validatable vs RERUN regardless.

## D. Policy changes — RERUN reference + implementation plan (HANDOFF)

The engine has **no** policy-change handling yet (`PolicyChangeEvent` is modeled in
`input_set.py` but consumed nowhere). I built the RERUN reference and the tooling to
construct/validate these, but did **not** implement the engine side — it's net-new,
multi-hour, and the guideline recalc needs live mortality to validate, so I'm handing
it off rather than committing something unverifiable.

**RERUN face-increase reference (captured):** I added `overrides` to
`tools/rerun_com.py` and built a face increase on U0688012 (100k→150k at policy
year 9) — `rerun_U0688012_faceinc.csv`. RERUN behavior:
- At the **year-9 anniversary** (mo 97): GSP 31,311 → 52,004 and AccGLP jumps by the
  change delta (attained-age delta method = `glp_on_change`). MD steps 102 → 172.
- The **following month** (mo 98): a new segment **Cov2 = 50,000** (the increase)
  appears (CalcEngine cols AH=Cov1, AI=Cov2, AJ=Cov3); Cov1 stays 100k; Total SA
  150k. The new segment carries its own COI (issue age = attained age at increase).

**RERUN face-DECREASE reference (captured):** 100k→75k at year 9 — RERUN **reduces
the existing Cov1 in place** (Cov1 100000→75000, no new/negative segment), and the
**surrender charge stays on the ORIGINAL face** (it doesn't drop on a decrease — the
year-9 SCR step is duration-based, independent of the change). Same 1-month lag,
guideline recalcs at the anniversary. So: decrease → reduce `CoverageSegment.face_amount`
but keep `original_face_amount` (surrender charge basis); increase → append a new
segment. The `CoverageSegment` model already carries both `face_amount` and
`original_face_amount`.

**Engine hook (mapped):** `calc_engine.process_month()` **step 3–7 (line ~405–408)**
is the designated, currently-no-op spot for "policy changes / coverage after change".
Cleanest wiring: in `project()`, if `future_inputs.policy_changes` is non-empty,
`deepcopy` the policy (so the projection mutates a private copy, never the caller's),
compile changes by duration like `compile_month_inputs`, and at the change month
mutate the copied policy's segments / `db_option`. Base cases (no changes) are
unaffected and stay on the fast path (no copy).

**Reproduce a scenario:** `rerun_com.py` run-mode now takes
`"overrides":[{"target":"INPUT!J14:J126","value":150000}]` (J6:J126 =
`vINPUT_Specified_Amount`, year 1..121; J14 = year 9). Face DECREASE = lower value;
DBO change = override `vINPUT_DBO` (CalcEngine input) similarly.

**Engine implementation plan:**
1. Consume `IllustrationInputSet.policy_changes` in `calc_engine.process_month()` at
   the change date. (Per the RERUN reference, recalc guideline at the *anniversary*
   of the change year; apply the segment change the following month — confirm Q4.)
2. **Face increase** → append a `CoverageSegment` for the increase amount, issue
   age = attained age at change, and **load its COI/EPU/SCR rates** at that issue age
   (needs `rate_loader` to load rates for a mid-projection segment — today it loads
   all segments up front). The multi-segment deduction/NAR-FIFO path already exists.
3. **Face decrease** → reduce the existing segment(s) (and surrender-charge basis).
4. **DBO change (A↔B)** → flip `policy.db_option` at the change date (the deduction
   already branches on DBO).
5. **Guideline recalc** → use `glp_on_change(current, before, after, method=...)`
   (built) for GLP, GSP, and **7-pay** (`calculate_7pay_premium`). A face **increase
   restarts the TAMRA 7-pay period** (RERUN `KZ` material-change flag → new
   `v7PayStartDate`, re-accumulate `XZ..YF` vs `KY`). Needs the guaranteed-COI
   mortality table (live UL_Rates) to penny-match; locally you can inject RERUN's
   recalculated GLP/GSP/7-pay to validate the AV/segment mechanics independently.
6. **Validate** with the harness: `rerun_com.py` (overrides) → reference; extend
   `run_engine_case.py` to take change inputs; add per-coverage groups (Cov1/Cov2…)
   to `calc_compare_map.py` (engine already dumps `*_cov2` via `_get_projection_value`;
   RERUN cols AH/AI/AJ for SA, and the per-segment NAR/COI columns).
