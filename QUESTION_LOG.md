# Illustration Engine vs RERUN — Overnight Work Log & Questions

**For Robert to review in the morning.** Started 2026-06-08 evening. I'm working
autonomously through the calc-engine validation + policy-change development you
asked for. This file holds (1) questions for you, (2) decisions/assumptions I made
without you, and (3) a running progress log. I'll append as I go.

> **2026-06-09 STATUS — see §E at the bottom.** The full policy-change pipeline
> (MTP/CTP recompute, guideline recalc, TAMRA reset) is implemented and validated
> EXACT vs RERUN on U0688012 for base, face increase, face decrease, and DBO A→B.
> Q3, Q5, and Q6 below are RESOLVED; Q4's timing is validated as implemented.

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

5. **Face-decrease COI basis — SOLVED.** The residual was a **re-banding** effect:
   CyberLife/RERUN band the COI by the CURRENT specified amount, so 100k→75k moves the
   base segment from Band 3 (SA≥100k) to Band 2 (50k≤SA<100k), a higher per-unit rate
   (0.44943 vs 0.39447). The engine kept the issue band. Fixed via `_reband_segment`
   (reloads COI/EPU at the new band; SCR is band-independent so it's left alone). COI
   now matches RERUN **exactly** after a decrease.
   - **Remaining small residual (~$0.67/mo):** the **Premium-Waiver charge** diverges
     only after a decrease (the base case PW matches to ~1e-15 at the same year). It's
     the PW *rate* (engine 0.7251 vs RERUN 0.7130), not the band (benefit re-band was a
     no-op). Open Q: how does CyberLife adjust the PW after a face decrease — does the
     PW rate/basis change with the decreased coverage? Decrease AV chain now matches to
     **~$8 over 30 months** (was $740). Also unverified: whether benefit COI rates
     re-band with the base band (`_reband_benefits` is principled but a no-op here).

6. **MTP recompute on a face change (drives the PW residual on BOTH inc/dec).** The
   engine keeps a single `policy.mtp` (150.13/mo for U0688012, from DB) constant across
   face changes, so the Premium-Waiver charge (benefit_amount = max(MTP, base_deduction),
   MTP-dominated) doesn't respond. RERUN recomputes MTP per the new coverage: increase
   100k→150k → MTP ratio **1.734** (the new segment's age-58 MTP rate 15.45/unit is
   higher than Cov1's age-50 10.53), decrease → **0.983**. But the DB MTP (150.13)
   ≠ `rate×units/12` (87.75) — the gap is the **PW's own target premium**, which scales
   recursively with the MTP, so a clean recompute isn't obvious. **Question:** what's the
   exact MTP formula on a face change (per-segment base MTP at issue-age+band, plus the
   benefit/PW target-premium contribution)? I left MTP constant rather than guess
   (no quietly-wrong numbers). Only residual on the COI-exact face increase (PW ~$29/mo)
   and the last bit of the decrease (~$0.67/mo).

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

**STATUS — machinery IMPLEMENTED (2026-06-08 late).** `calc_engine` now consumes
`IllustrationInputSet.policy_changes`: `project()` deep-copies the policy when changes
exist (base cases untouched — verified byte-for-byte), compiles changes by duration,
and `process_month` applies them at step 3-7 (`_apply_policy_change`). `run_engine_case.py`
takes a `"changes":[{"kind":"face_amount"|"db_option","date":...,"value":...}]` arg.
- **Face DECREASE — validated** on U0688012 (100k→75k at the year-9 anniversary):
  reduces segment face + units, and deducts the decreased coverage's surrender charge
  from AV. AV chain now matches RERUN to **~$5–20** (was ~$740 before the surrender-
  charge deduction). **Residual:** a persistent **~$5.6 COI difference** — RERUN's COI
  basis after a decrease stays higher than a pure 75k NAR (see Q5). Timing: RERUN
  applies the COI/DB/surrender effect at the **anniversary** (the specified-amount
  *display* lags one month).
- **DBO change** — wired (`db_option` flip) + compared vs a RERUN reference (A→B at
  year 9, `vINPUT_DBO`=INPUT!K6:K126). Found the missing mechanic: RERUN keeps the death
  benefit **level** at the change (DB stays ≈ face = 99,822), i.e. **A→B reduces the
  specified amount by the current AV** so DB = (face−AV)+AV. The engine just flips the
  option → DB jumps to face+AV (107,454, +7,631). Needs: on A→B reduce the base face by
  AV (then re-band); B→A the inverse. Plus the MTP/PW residual (Q6) and DBO-B NAR
  details. NOT implemented (more involved than the face changes).
- **Face INCREASE — implemented; COI exact.** On the increase, a new coverage segment
  is appended at the current attained age, its COI/EPU/SCR loaded on the fly
  (`_load_segment_rates`), and ALL segments are re-banded to the new TOTAL specified
  amount (CyberLife bands by total SA, so the increase's COI uses the total-face band,
  not the increment's band). COI/EPU/MFee now match RERUN to **sub-penny** (U0688012
  100k→150k). **Residual: PW (~$29/mo)** — same root cause as the decrease PW (Q6):
  the MTP isn't recomputed on a face change.
- **Guideline recalc on change** — NOT wired; RERUN recalcs GLP/GSP at the change
  (engine keeps loaded values → Guideline group diverges, but TEFRA-off so no AV
  effect; reported only). Use `glp_on_change` + the guaranteed-COI rates.

Original plan (still the roadmap for increase + guideline/TAMRA recalc) below.

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

---

## E. 2026-06-09 — Policy-change pipeline COMPLETE & EXACT (minipc session)

**Headline: U0688012 vs RERUN, all 10 comparison groups at literal 0.0 delta over
40 months, for ALL FOUR scenarios** — base, face increase 100k→150k, face
decrease 100k→75k, DBO A→B (all changes at the year-9 anniversary 2027-11-09).
U0492070 and U0656998 base cases also re-validated at 0.0 (previously sub-penny).
Guideline recalc values were INJECTED from RERUN (`metadata` on the change event)
to validate the mechanics independently of guideline-calc calibration — see
"Remaining" below.

### Resolved questions
- **Q3 (GSP $0.05)** — RESOLVED. RERUN floors GSP **and GLP** to a
  monthly-divisible cent everywhere, including the loaded inforce values
  (`KS/KT = INT(x/12*100)*12/100`). Engine now applies `floor_monthly_cent()`
  (Decimal-based — binary-float floor dropped a cent on exact values).
- **Q5 (decrease COI basis)** — fully closed; with re-banding + the fixes below
  the decrease matches exactly.
- **Q6 (MTP recompute)** — SOLVED. It is NOT recursive: PW target premium =
  `BENMTP rate × (MTP w/o PW) × (1 + factor × table)` (CalcEngine IV), and
  `vMTP = Σ cov targets + Σ benefit targets + IV` (JG). Each cov target =
  `ROUND(SA·rate/1000,2) + ROUND(table·tblRate·SA/1000,2) + flat term` with
  rates from Select_RATE_MTP / TBL1MTP at the segment's own issue age and the
  **current total-SA band** (no band lock, current-SA basis for this product —
  validated against the observed 1.734 / 0.983 ratios). vCTP identical from
  CTP/TBL1CTP with `MIN(6, tblRate)` and its PW term = `ROUND(IV, 2)` (KP=IV).
  `vMonthlyMTP = TRUNC(vMTP/12, 2)`; the PW waive basis uses `ROUND(vMTP/12,2)`.
  New module: `suiteview/illustration/core/target_premium.py`. The PW residuals
  on increase ($29/mo) and decrease ($0.67/mo) are GONE.
- **Q4 (timing)** — validated as implemented: the engine applies segment change +
  guideline recalc at the change-anniversary month and matches RERUN exactly
  (RERUN's 1-month "lag" is display-only, as suspected for the decrease).

### New mechanics discovered & implemented (all validated exact)
- **Leap-day interest (ENGINE BUG, all cases):** RERUN/CyberLife exclude Feb 29
  from ExactDays interest (`UB = C13−C12 − LeapDayRemoval`; 365-day year). The
  engine credited 29 days in leap Februaries → +$0.61/mo drift from 2028-02.
  Prior validations missed it because they ended before Feb 2028.
- **COI rate display rounding:** cov 1's substandard-adjusted COI rate is
  `ROUND(...,5)` (OY); cov 2/3 are NOT rounded (OZ/PA).
- **EPU rounds per coverage:** each cov's table-EPU charge is `ROUND(SA·rate/1000,2)`
  (SB-SE).
- **Stale rate alias (ENGINE BUG):** after a mid-projection re-band, the
  displayed cov-1 COI rate and the corridor-COI basis still read the load-time
  `rates.coi` alias (issue band). Now reads the segment's own schedule.
- **DBO A→B level-DB mechanic:** reduce base SA by **INT(AV entering the month)**
  (7,312.75 → 7,312; SA 100,000→92,688), processed like a face decrease
  **including the decreased units' surrender-charge deduction from AV** (215.78
  = 7.312 units × 29.51). Then re-band (→ band 2), recompute MTP/CTP
  (JE 150.13→182.43 exact), recalc guideline. B→A implemented as the inverse
  (in-place face += INT(AV), material change) but NOT yet validated vs RERUN.
- **7-pay recalc fires on ANY coverage change** (KY on vPolicyChangeIndicator),
  capped at `sMax7702RecalcsAllowed = 1`; only the PERIOD RESTART (KZ/LA new
  start date, contribution buckets reset) is material-change-gated (face
  increase or B→A).
- **Ending DB (WB):** recomputed at END of month — face + EOM AV (DBO B) +
  corridor on EOM AV − policy debt. Engine previously reported deduction-time
  gross DB (equal only for DBO A, no loans).
- **Increase-segment SCR:** the new segment DOES carry its own surrender charge
  (TI; vFullSC=TK sums all coverages). Earlier confusion was a column-mapping
  artifact (TH is cov-1 only).
- **TAMRA inforce fields now loaded** from LH_TAMRA_7_PY_PER/_YR (7-pay level
  6,721.24, start date, per-year contributions) — present in the local fixtures.

### Remaining gaps (next sessions)
1. **Guideline own-calc calibration** — with no injected values the engine
   computes the recalc via commutation + guaranteed COI: deltas ~15-18% low
   (GSP after increase 48,946 vs RERUN 52,004; GLP delta 1,695 vs 2,077) and
   7-pay ~4% high (12,033 vs 11,578). RERUN's Guideline_Premiums calculator
   (228 cols, named results sGSP_Before1/After1 etc.) is the reference to
   reverse-engineer — likely a monthly AV-projection method, not commutation.
   The injectable `metadata` path keeps mechanics validatable meanwhile.
2. **TEFRA/TAMRA-binding scenario** — force-out / premium-cap firing with
   recalculated limits has no reference yet (all saved cases are TEFRA-off,
   premiums far below limits). Construct an over-funded scenario (premium
   override) with TEFRA/TAMRA ON in both RERUN + engine.
3. **B→A DBO change** — implemented, unvalidated (no reference captured).
4. **PWST / rider / CCV target premiums** — `check_target_premium.py` on the
   other cases shows the gap concretely: U0688012 exact / U0492070 MTP exact
   but CTP −95.00/yr (the CCV rider's CTP — sourced from
   `tRates_Rider_CCV_Targets`, NOT Select_RATE_BENMTP; not in the local export)
   / U0656998 MTP −40.00/mo, CTP −525.75/yr (the LTR rider's target premium —
   RERUN's generic rider target tables are dead refs, so it comes from
   somewhere else; find it). Harmless for base projections (RERUN carries the
   DB value forward), but a policy change on those cases would recompute wrong.
5. **U0492070 shadow/CCV value** — still blocked on the fixture export (Q1).
6. **Mid-year (non-anniversary) changes** — Guideline_Premiums column K
   (AccumAdjust) pro-rates the year-of-change GLP accumulation by months;
   not implemented (all validated scenarios were anniversary-dated).

---

## F. 2026-06-10 — Guideline calcs owned by the engine; Values Overview UI

**The engine now computes its own GLP/GSP/7-pay** — `monthly_guideline.py`, a
monthly accumulated-value endowment solve (fund is linear in premium → exact
solve, no compression, unlimited recalcs). Penny-matches the workbook's
Guideline_Premiums calculator: at issue (2,921.60 / 32,114.05 / 6,868.90 for
U0688012 — admin's 2,880.33 / 31,311.53 / 6,721.24 is the known 1.4-2.6%
workbook↔admin calibration gap) and EXACT at every captured policy-change
before/after. All four projection scenarios are `all_ok` vs RERUN with the
engine's own recalcs.

### Workbook intent decoded (and where it was "fragile")
- **Q2 ANSWERED — 7-pay is a NET premium**: the 7-pay block's MFEE, EPU, and
  premium-load columns are simply EMPTY. Guaranteed COI + benefit/rider
  charges only.
- **GSP and 7-pay always solve on LEVEL-DB mechanics** — their blocks hardcode
  DBO "A" (AW21/EB21 literals); only the GLP block reads the contract's option
  (BQ21=C21). Deliberate, not fragile: a true DBO-B single-premium endowment
  is degenerate (engine reproduced the absurd 142k GSP before pinning A).
- **7-pay recalc start**: non-material changes re-solve from the ORIGINAL
  7-pay period start with that period's starting AV (CH24, =SVPY_BEG_CSV_AMT,
  new policy field `tamra_7pay_start_av`); material changes restart at the
  change date with the current AV.
- **Benefits cease at payup** (vPW_Active gates on age) — U0688012's PW stops
  at the age-60 anniversary; the monthly-deduction loop now gates on
  `ben.cease_date` too (it previously charged PW forever; was outside the
  40-month comparison windows).
- The 7-pay load treatment in the workbook is internally inconsistent with
  GSP/GLP ((1−TPP) header vs empty cells) — moot since the cells are blank.

### Search routine (Find GP/TAMRA by Search Routine, default OFF)
`guideline_calc.search_guideline_premiums` — premium binary-search on the real
engine (guaranteed COI, statutory rate, current expenses, no bonus, machinery
off), GSP/7-pay forced level-DB like the formula. Face-increase check vs the
formula: GLP within $1.56 (0.03%), GSP $46.68 (0.09%); **7-pay ~7% higher BY
DESIGN** (the search includes current expenses per spec; the formula 7-pay is
net). Multi-base-coverage policies are the known divergence case (formula uses
one COI stream on total SA; the search runs true per-segment NAR/COI).

### Values Overview UI (new default sub-tab)
KPI chips (horizon, ending AV/SV/DB, lapse year/age, GP room, premiums in) →
hand-painted chart (AV/SV/DB/cum-premium/guideline-limit; hover crosshair
readout; click a year to jump the ledger; legend toggles; no dependencies) →
annual⇄monthly drill-down ledger (year rows expand to the 12 monthliversaries;
status flags SNET/Shadow/ForceOut/PremCap/ExcPrem/LAPSED; right-click → Dump
to Excel via the shared COM helper). Deep per-column grids unchanged on their
own sub-tabs. **Laptop:** click-test interactions; consider next: per-coverage
columns in the ledger, scenario-compare overlay (two runs side by side on the
chart), force-out markers on the chart.

---

## G. 2026-06-10 (minipc, later) — TEFRA/TAMRA-binding + B→A all EXACT

**Headline: the three remaining validation gaps (§E items 2/3) are CLOSED — all
at literal 0.0 delta vs RERUN over 90 months on U0688012.** Three new scenarios,
all over-funded (premium vector → 25,000/yr annual, mode A) so the 7702
machinery actually fires for the first time:

- **T0 — TEFRA acceptance cap** (`sINPUT_TEFRA_Force=TRUE`, no change): year-8
  anniversary pays the partial 18,889.80 (= GSP 31,311.48 − premTD 12,421.68),
  years 9-10 capped to 0, year-11 crossover pays 371.79 (AccumGLP passes GSP),
  then the 2,880.24/yr GLP trickle. EXACT with no engine change.
- **T1 — force-out** (T0 + face decrease 100k→75k at year 9): guideline recalc
  drops the limit to AccumGLP 25,045.11 → **force-out 6,266.37** (KX) fires at
  the change month. EXACT after engine fix #1 below.
- **T2 — TAMRA cap** (T0 + face increase 100k→150k at year 9): material change
  restarts the 7-pay (new level 8,871.12); TAMRA cap binds years 9-10, guideline
  cap takes over year 11 (2,950.56), zeros, then crossover trickle. EXACT.
- **B→A DBO change** (A→B year 9, B→A year 11, normal premiums, TEFRA off):
  face += INT(AV) in place, material change (7-pay restart), re-band. EXACT
  after engine fix #2 below. §E "B→A implemented but unvalidated" is now
  validated.

**Engine bug #1 — premium loads don't re-band (engine wrong, RERUN right):**
RERUN keys TPP/EPP (premium loads), MFEE, and PoAV on the month's
**CurrentBand** (PolicyRates EC/ED/FE/FF all VLOOKUP on CalcEngine FD) — this
plancode's band-3 target load steps 8%→4% at year 11 while bands 1-2 stay 8%,
so the year-9 decrease (re-band 3→2) must flip the load schedule. The engine
loaded tpp/epp/mfee/poav once at the issue band. New
`_reload_policy_band_rates()` in `calc_engine.py`, called on
`outcome.coverage_changed`. (Guideline solves were unaffected — they use the
guaranteed scale, where TPP is 8% flat across bands.)

**Engine bug #2 — benefit cease gate in targets is inclusive (engine wrong):**
`compute_target_premiums` included a benefit when `as_of <= cease_date`; the
deduction loop (and RERUN vPW_Active) are STRICT — a benefit contributes
nothing from its payup anniversary on. Exposed because the B→A change landed
exactly on U0688012's PW age-60 payup anniversary: RERUN's recomputed
vMTP/vCTP (132.37/1,832.00) exclude PW; engine had 151.04/2,055.98. Segment
table/flat cease stays inclusive (matches `_charge_active`).

**Tooling:** `run_engine_case.py` now takes
`"premiums":[{"year":1,"amount":25000,"mode":"A"}]` (scheduled premiums that
REPLACE the billed premium — the RERUN premium-vector-override equivalent) and
dumps `premium_cap`/`premium_capped`. RERUN diagnostic columns worth adding to
captures: LN (planned prem), NV (sched prem cap), NZ (applied sched prem), SX
(limit reached). References: `tmp_compare/rerun_tefra_t0/t1_facedec/t2_faceinc.csv`,
`rerun_dbo_ba.csv` (+ engine_* counterparts).

**Regression:** all four §E scenarios + U0492070/U0656998 base re-validated
`all_ok` after both fixes. **Flag gotcha:** match each saved case's
sINPUT_TEFRA_Force/TAMRA_Force — running U0656998 with TEFRA defaulted ON caps
its premium at the guideline (its premTD sits at the limit) and the comparison
fails spuriously.

**Remaining (updated §E list):** PWST/rider/CCV target premiums (#4), U0492070
shadow fixture export (#5, laptop), mid-year non-anniversary change
AccumAdjust pro-rating (#6), UE000576 local export (laptop), Overview UI
click-test (laptop).
