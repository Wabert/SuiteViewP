# Illustration UL engine steps

The projection engine emits an opening inforce row followed by one row per
projected month. The canonical projected-month order is:

1. Advance counters and carry beginning values.
2. Capitalize loans. CyberLife monthliversary timing credits interest here.
3. Process withdrawal.
4. Apply policy changes and refresh target/guideline details when supported.
5. Apply guideline force-out.
6. Resolve requested premium and loan cash flows.
7. Compute premium allowances and apply premium.
8. Deduct monthly charges and apply exception premium, if any.
9. Apply new loans.
10. Credit post-deduction interest for illustration timing.
11. Accrue loan interest.
12. Calculate shadow account values when supported. Product flags govern
    approved source-system differences, including SGUL between-monthliversary
    premium forgiveness and APS205 target/load relief for LTGUL/LTGUL08
    (`ShadowAPS205LoadRelief`, `ShadowTargetWaiverUplift`, `ShadowTargetAnnualFlat`,
    `ShadowFrozenAfterCease`), and the option-B
    shadow NAR death benefit (`ShadowDBBasis`; see `RERUN_MANUAL.md`).
13. Evaluate lapse/protection.
14. Build the `MonthlyState` ledger row.

## Timing conventions

| Difference | Illustration | CyberLife monthliversary |
| --- | --- | --- |
| Counter date | Issue-anchored projection month | Calendar monthliversary for inforce runs |
| Interest | After deduction, exception premium and new loans | Before withdrawal |
| Exact-day interest span | Month date to next month date | Previous monthliversary to current monthliversary |
| Monthliversary date | Always derived from the issue day, clamped to month end | Same; never stepped from the previous projected date |
| Historical dated inputs | Forward illustrations assume monthliversary cash flows | Rollback/from-issue dated transactions add receipt-to-monthliversary interest |
| Policy changes | Dated changes allowed | Rejected/skipped |
| Target refresh | Recompute on changes/date-gated actives | Carry prior detail |
| Guideline recalc | Records policy-change recalc and AccumGLP true-up | Simple GLP accumulation |
| WAIR/shadow | Runs both | Skipped |
| Shadow N+1 target relief | Only with the Inputs-tab setting "Shadow N+1 Target Relief" (`IllustrationOptions.shadow_nplus1_relief`, default off) | Always (`TimingConvention.shadow_nplus1_relief`) |
| Lapse | Safety net, shadow, exception, SV/AV basis, no-lapse | Simple `AV <= 0` unless exception/no-lapse |
| 7-pay contribution | Premium less gross withdrawal | Premium only |

Money values are dollars. Rates are documented in the owning modules:
`premium_allowance.py`, `monthly_deduction.py`, `target_premium.py`, and
`monthly_guideline.py`. Golden engine ledgers in `tests/golden/engine` are the
behavior contract for both timing conventions.

The development-only IUL segment crediting option adds account hooks to this
order (maturity after step 2, account postings after each AV-changing step, a
sweep before interest); see [IUL_SEGMENT_CREDITING.md](IUL_SEGMENT_CREDITING.md).
