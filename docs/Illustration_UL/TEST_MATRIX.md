# UL Illustration Test Matrix

Policies used to validate the illustration calculation engine against RERUN.

| Policy   | Plancode  | Issue Age | Sex | Rate Class | Table Rating | Flat Extra | DBO | Face Amount  | Benefit: 39 (PW Cease) | Benefit: A1 (Cease) |
|----------|-----------|-----------|-----|------------|--------------|------------|-----|--------------|------------------------|---------------------|
| UE000576 | 1U143900  | 50        | M   | N          | —            | —          | A   | $90,000      | —                      | —                   |
| UE006826 | 1U143900  | 2         | F   | N          | —            | —          | B   | $100,000     | 2075-03-06             | —                   |
| UE015345 | 1U143900  | 25        | M   | N          | —            | —          | A   | $150,000     | —                      | —                   |
| UIP00143 | 1U143900  | 42        | F   | N          | —            | —          | A   | $50,000      | —                      | 2091-02-10          |

## Notes

- All policies are EXECUL (plancode 1U143900) as of the initial test matrix.
- **Benefit 39** = Premium Waiver. Charge = `pw_coi_rate × max(monthly_mtp, base_deduction)`. Unrounded.
- **Benefit A1** = type `A`, subtype `1`. Charge formula TBD (not yet implemented).
- No riders have been added to the test policies yet.
- All policies are standard rate class (no table rating or flat extra).
- Add rider columns (e.g. CTR, LTR) and additional benefit columns as new test cases are identified.

## Validation Status

| Policy   | M1 Baseline | Benefit Charges | MTP/CTP | Riders |
|----------|-------------|-----------------|---------|--------|
| UE000576 | ✅ Validated | N/A (no benefits) | ⏳       | ⏳      |
| UE006826 | ✅ Validated | ✅ PW ($0.90/mo confirmed) | ⏳  | ⏳      |
| UE015345 | ⏳ Pending  | N/A (no benefits) | ⏳       | ⏳      |
| UIP00143 | ⏳ Pending  | ⏳ A1 (formula TBD) | ⏳     | ⏳      |
