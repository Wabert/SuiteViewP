# Illustration Engine — Baseline Testing (auditor-facing)

This folder is the evidence trail showing that the SuiteView illustration
calculation engine has been **baselined against RERUN** (`RERUN (v20.0)`), the
actuarial source-of-truth workbook for inforce UL/IUL illustrations.

## Contents

| Item | What it is |
|---|---|
| `TEST_MATRIX.xlsx` | The baseline test matrix — one row per test case with per-quantity results. **Generated; never edit by hand.** |
| `test_matrix.json` | Source of truth for the matrix. Edit this, then regenerate. |
| `details/` | Per-case detailed comparison workbooks (`rerun_vs_app_*.xlsx`) — the month-by-month RERUN vs engine evidence behind each matrix row. |
| `archive/` | Stale generated outputs (old batch captures, debug dumps, superseded reports) moved out of `docs/Illustration_UL/` — retained, not deleted. |

## Regenerating the matrix

```powershell
venv\Scripts\python.exe tools/build_test_matrix.py
```

The script reads `test_matrix.json`, writes `TEST_MATRIX.xlsx` (frozen header,
autofilter, autofit, color-coded statuses), then re-reads the file and asserts
row/column counts as a self-check.

## Adding a test case

1. Add the case to the RERUN workbook's **Saved Cases** sheet (or capture a
   constructed override scenario) and run the comparison
   (`tools/compare_rerun_vs_app.py`); put the resulting detail workbook in
   `details/`.
2. Append a row object to `rows` in `test_matrix.json` — the `_readme` block
   at the top of the JSON documents every field.
3. Rerun the build script.

## Status vocabulary

**PASS/FAIL column (whole case):**

| Status | Meaning |
|---|---|
| `PASS` (green) | All compared quantities match RERUN within tolerance; evidence cited in Comments. |
| `PARTIAL` (amber) | Core quantities verified; named residuals remain, each classified in Comments. |
| `FAIL` (red) | Material unexplained mismatch, or the case is unrunnable as stored. |
| `PENDING` (grey) | Not yet compared, or the comparison artifact was not retained on this machine. |

**Per-quantity columns** — GLP/GSP (guideline limits), Contributions (premiums
applied), Distributions (withdrawals / loans disbursed / force-outs), Policy
Debt (loan balance), EAV (ending account value), ESV (ending surrender value):

| Cell | Meaning |
|---|---|
| `EXACT` (green) | Zero delta vs RERUN within tolerance across the comparison horizon. |
| `Δ <n>` (amber) | Maximum absolute delta observed across the horizon; the cause is classified in Comments. |
| `FAIL` (red) | Material unexplained mismatch. |
| `—` (grey) | Not applicable to the case, or not yet compared. |

## Honesty rules

- A cell may only say `EXACT` when there is a retained artifact in `details/`
  **or** a documented validation record (cited in Comments — e.g.
  `QUESTION_LOG.md`, `WORK_LAPTOP_SPEC.md`, or a pass annotation stored in the
  RERUN Saved Case itself).
- Cases whose historical validation artifacts were not retained are marked
  with "detail workbook to be regenerated" — the documented record is cited,
  but per-quantity cells stay `—` until the artifact exists.
- RERUN is the calculation reference but not gospel: where the engine
  deliberately matches the admin system instead of RERUN (e.g. benefit cease
  dates), the divergence is classified in Comments rather than hidden.

## Where the cases come from

- **Saved Cases 1–27** are enumerated from
  `docs/Illustration_UL/RERUN (v20.0) local IUL.xlsm` (Saved Cases sheet — the
  authoritative current copy; one case per column). Form / DB Option come from
  the local policy DB (`tools/list_local_policies.py`).
- **Constructed scenarios (S-\*)** are override runs (face/DBO changes,
  TEFRA/TAMRA-binding premiums, withdrawals, loans) built on validated
  baselines via `tools/rerun_com.py` overrides — the 2026-06 validation
  campaign documented in `QUESTION_LOG.md` §E–§H.
