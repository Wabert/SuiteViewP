# UL Illustration Test Matrix

Policies used to validate the illustration calculation engine against RERUN.

| Policy   | Plancode | Issue Age | Sex | Rate Class | Table Rating | Flat Extra | DBO | Face Amount | Benefit: 39 (PW Cease) | Benefit: A1 (Cease) | Benefit: 4C (PWSTP Cease) | Benefit: 76 (GIO Cease) | Rider Coverages |
|----------|----------|-----------|-----|------------|--------------|------------|-----|-------------|------------------------|---------------------|----------------------------|-------------------------|-----------------|
| UE000576 | 1U143900 | 50        | M   | N          | —            | —          | A   | $90,000     | —                      | —                   | —                          | —                       | —               |
| UE006826 | 1U143900 | 2         | F   | N          | —            | —          | B   | $100,000    | 2075-03-06             | —                   | —                          | —                       | —               |
| UE015345 | 1U143900 | 25        | M   | N          | —            | —          | A   | $150,000    | —                      | —                   | —                          | —                       | —               |
| UIP00143 | 1U143900 | 42        | F   | N          | —            | —          | A   | $50,000     | —                      | 2091-02-10          | —                          | —                       | —               |
| UIP23179 | 1U143900 | 58        | F   | N          | —            | —          | A   | $200,000 (2 x $100,000) | —                    | —                   | —                          | —                       | —               |
| U0930725 | 1U143900 | 23        | M   | N          | —            | —          | B   | $50,000     | —                      | —                   | 2049-12-27                 | 2029-12-27              | —               |
| UE070657 | 1U143900 | 41        | M   | N          | —            | —          | A   | $50,000     | —                      | —                   | —                          | —                       | LTR 1U536C00 $50,000; CTR 1U538F00 $25,000 |

## Notes

- All base policies are EXECUL (plancode 1U143900) as of the initial test matrix.
- **Benefit 39** = Premium Waiver. Charge = `pw_coi_rate × max(monthly_mtp, base_deduction)`. Unrounded.
- **Benefit A1** = type `A`, subtype `1`. Charge formula TBD (not yet implemented).
- **Benefit 4C** = PWSTP/PWoT. Rate is present on `U0930725` (`0.04` from DB2 benefit renewal record).
- **Benefit 76** = GIO. Rate is present on `U0930725` (`0.09` from DB2 benefit renewal record).
- **LTR 1U536C00** = UL Signature Term Rider 20 Yr on `UE070657` (`$50,000`, issue age 35, F/N, matures 2039-08-02).
- **CTR 1U538F00** = UL Child Term Rider on `UE070657` (`$25,000`, issue age 41, M/N, matures 2043-08-02).
- **UIP23179** validates UL increases: coverage phase 1 is `$100,000` issued at age 58; coverage phase 2 is `$100,000` issued at age 62. Account value reduces discounted DB FIFO by coverage phase. DBO B/C additions apply to phase 1 only.
- All listed base coverages are standard rate class (no table rating or flat extra).

## Validation Status

| Policy   | M1 Baseline | Benefit Charges | MTP/CTP | Riders |
|----------|-------------|-----------------|---------|--------|
| UE000576 | ✅ Validated | N/A (no benefits) | ⏳       | ⏳      |
| UE006826 | ✅ Validated | ✅ PW ($0.90/mo confirmed) | ⏳  | ⏳      |
| UE015345 | ⏳ Pending  | N/A (no benefits) | ⏳       | ⏳      |
| UIP00143 | ⏳ Pending  | ⏳ A1 (formula TBD) | ⏳     | ⏳      |
| UIP23179 | ⏳ Pending  | ⏳ Multiple base coverage FIFO NAR | ⏳ | N/A |
| U0930725 | ⏳ Pending  | ⏳ PWSTP/GIO rates present; formulas pending | ⏳ | N/A |
| UE070657 | ⏳ Pending  | N/A | ⏳ | ⏳ LTR/CTR pending |
