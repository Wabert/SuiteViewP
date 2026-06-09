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
  - **Still TODO tonight:** per-coverage (cov1..N) + rate columns in the harness;
    policy-change cases (face dec/inc, DBO change) + TAMRA 7-pay calc; commit+push.
