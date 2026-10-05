# IUL segment ("bucket") crediting — development only

`IllustrationOptions.iul_segment_crediting` replaces the single blended
crediting rate with CyberLife's account structure, so a blended run and a
segment run of the same policy can be compared. It is a development-only
option: the Inputs tab shows the **Segment Buckets (dev)** radio only when
SuiteView runs from source, and `core/iul_segments.build_segment_context`
refuses the option in the packaged EXE. Version 1 supports the IUL14 product
family only (no multiplier strategies).

Code: `suiteview/illustration/core/iul_segments.py` (accounts and rules),
the hooks in `core/calc_engine.py`, the debug views in
`ui/iul_segment_views.py`, and the comparison tool
`tools/engine/compare_iul_segment_crediting.py`.

## Sources

* Product Specification [IUL14 Series] (Spec Library, Universal Life):
  sweep account, Sweep Account Minimum, Sweep Date, Fixed and Indexed Accounts,
  Deduction Hierarchy.
* Robert Haessly's decisions, 2026-10-05 (local task
  `ZZTaskRepo\IUL-Segment-Bucket-Crediting-2026-10-05`).
* DB2 `LH_POL_FND_VAL_TOT` (CKPR, 2026-10-05): each index segment is a current
  fund value phase opened on `VAL_STR_DT` (the 1st of the month); matured phases
  stay with no value; `SW` is a single row.

## Monthly mechanics

| Step | Rule |
| --- | --- |
| Sweep minimum | 12 x **last month's** monthly deduction. The first month from issue has none, so it uses that month's deduction. Inforce opens with the policy's sweep minimum (12 x the valuation month's MD when blank). |
| Maturity (start of month) | Segments whose one-year maturity date falls on or before the monthliversary are credited `value x (locked rate + plan bonus)`. The matured value refills the sweep to its minimum (hierarchy order across strategies); the rest renews in the same strategy as a new segment dated this monthliversary. |
| Cash flows | Net premium, exception premium and released loan collateral go to the sweep. Withdrawals, force-outs, the monthly deduction, new fixed loans and capitalized fixed-loan interest (collateral increases) are drawn Sweep -> Fixed -> IS -> IC -> IF -> IX, newest segment first (LIFO). With every account exhausted the sweep goes negative. |
| Sweep | After the month's cash flows, sweep value above the minimum moves to Fixed and to new segments by the premium allocation. It joins the same new segment as that month's renewals. The sweep happens on the monthliversary, not CyberLife's 1st-of-month sweep date (a deliberate simplification). |
| Interest | Sweep and Fixed earn the declared (fixed-strategy) rate plus bonus on the engine's day basis. Loan collateral interest (the engine's impaired interest) is paid to the sweep. Segments earn nothing until maturity. |
| Rates | A segment locks the strategy's illustrated rate on its start date; inforce segments take today's illustrated rate. The guaranteed run credits 0% to segments and GINT to sweep/fixed. |
| Asset charge | The monthly AV asset charge is off; a multiplier strategy's charge would come off each new segment (not used by IUL14). |

NAR, COI, monthly deduction, surrender charge, loan interest, guideline and
lapse calculations are unchanged; they read the account total, which always
equals the engine AV (`Difference` on the Accounts view).

## Debug views (Values tab, segment runs only)

* **IUL Accounts** — one row per month: begin/end balances of Sweep, Fixed,
  Collateral and Index; maturity interest, refill, renewal, deposits, draws by
  step and by account, sweep out, interest, sweep minimum; account total vs
  engine AV. Overview drill-downs for Interest/EAV open this view.
* **IUL Segment Grid** — one row per month; per strategy, twelve columns
  `M01..M12` (the policy month the segment matures/renews in) holding each open
  segment's value, plus a strategy total.
* **IUL Segment Ledger** — one row per account event (maturity credit, refill,
  renewal, sweep in, LIFO draws, collateral moves, interest, seeding notes).

## Known limits

* IUL14 family only; other products need their hierarchy validated first.
* Sweeps on the monthliversary, not the 1st of the calendar month.
* No interim opening value; a value rollback opens with all value in the sweep
  (current segments are not rolled back) and reports the seeding difference.
* Cumulative Interest Guarantee is not modelled.
* Collateral interest to the sweep is a modelling assumption, not yet
  verified against CyberLife.
