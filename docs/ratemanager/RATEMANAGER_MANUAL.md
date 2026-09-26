# RateManager manual

RateManager product-line workflows, including Whole Life and Term rate loading rules.

> Source: moved from the former long-form `Agent.md` so that the canonical standards file can stay concise.


## Whole Life rate loading

Whole Life has its own Rate Manager choice and source-keyed loader in
`suiteview/ratemanager/whole_life/`. It is intentionally separate from the
UL/Term pointer-index compiler: preserve the CyberLife keys, versions, date
ranges, age-use codes and premium options rather than inventing illustration
rates. See [`docs/RATEMANAGER_WL.md`](../RATEMANAGER_WL.md) for supported
sources and query semantics.

The Workup screen has separate CVF, IAF, DIV and PUI file rows, plus optional
NSP CSV and DIV map rows. Any combination can be parsed/reviewed/loaded as one
package via `parse_workup`; an invalid selected file blocks the whole workup.
The explicit company/user code is required only when IAF files are selected.

CVF `NO ZERO DUR` headers mean absent duration-zero metadata (SQL NULL).
Their grid indexes begin at FIRST DUR, not duration zero; map each cell to
FIRST plus its offset from the first printed decade, retaining only FIRST..LAST.
The first decade contains FIRST-1: FIRST 121's `120-129` begins at duration 121.
Do not invent a
duration-zero row or infer negatives without a signed header. D11 printed
page 110 defines the contiguous array; company `00 / 2EBF00 / age 1` has
`1000.00` at duration 59 (printed offset 58).

CVF imports floor every negative cash value to `0.00`, in both `RATE` and
`DURATION_ZERO_VALUE`. Resolve the signed duration-zero header and validate
raw source conflicts/padding before flooring; never let normalization hide
malformed source data. Existing negative rows are corrected by a reviewed reload.
The print grid loses signs. The user approved **optional** early-negative
inference: with a negative duration-zero header and a strict initial decline
followed by a rise, zero unsigned values before the first minimum and retain
the minimum as positive. For `08 / 1WL511 / age 59`, this changes `22.27` to
zero but retains `0.94`. It is an assumption, not recovered signs. The option
`infer_cvf_negatives` defaults off; skip plateaus/unfinished declines, never
override explicit `+` signs, and preserve raw validation. The rule version and
per-row adjustments must remain in source metadata and load receipts.

PolView's Rates > Coverages view routes traditional `WL` policies to cash values
through `PolicyInformation.rates_wl_cv()` and `Rates.get_wl_cash_values()`.
The key is coverage `INS_CLS_CD` + `PLN_BSE_SRE_CD` + `LIF_PLN_SUB_SRE_CD`
(1/3/2 characters), plus the CyberLife rate-file user (company 01 shares user
00; 04/06/08 are their own; others raise) and coverage issue age. Select only the
blank `USER_DEFINED` variant unless its mapping is explicitly known; never
fall back to another user or variant. Keep duration zero and source duration
labels intact. NSP/PUI/dividend lookups in this view remain future work.
ISWL and WL policies also get a Rates **Fixed Premium** branch (ISWL cash
values, `WL_RATE_PREM` premium rates, and the `RATE_MODEFACT` modal premium
beside `POL_PRM_AMT`), while ISWL coverages keep the UL view (current-scale
COI only) plus GINT, CVR, premium rate, loan rates and cease ages. See `docs/POLVIEW_CLAUDE.md` § "ISWL / WL
fixed-premium rates".
For ETI/RPU policies (premium-paying status 44/45), the Rates view shows
"Cash value file is not available for policies on ETI or RPU." without querying
rates or substituting an original Whole Life basis. Other paid-up statuses are
not excluded.

The four new tables are `WL_RATE_CV`, `WL_RATE_NSP`, `WL_RATE_PUI` and
`WL_RATE_PREM`. Dividend imports reuse the existing `WL_DIV_HEADER`,
`WL_RATE_DIV` and `WL_DIV_PLANKEY_MAP` schemas, not an external script at
runtime. Loading previews differences, inserts new keys, skips unchanged
values, and requires explicit per-table approval to update existing values.
It never deletes rows absent from an input file. Updates are backed up before
the transaction; source hashes and verified load receipts are retained under
`~/.suiteview/backups/rate_manager/whole_life/`. Shared-database write guards
apply to both table creation and loading.

## 📐 Term Rates — Rules That Are Not Obvious

Term rates are stored **pre-compiled**: every (IssueAge, Duration) cell is
materialized into `TERM_RATE_PREM` / `TERM_RATE_BEN` rather than resolved at
quote time. That is why those two tables hold millions of rows (10.7M and 4.0M
across ~47 plancodes), and why the compile step in
[`term_builder.py`](../../suiteview/ratemanager/workup/term_builder.py) is the heart
of the feature. ABR Quote reads these tables in production — treat them as live.

### Index naming — string identifiers, not numbers

Every `Index(...)` column in the TERM_* tables is **varchar(20)**.

| Table | Index | Form |
|---|---|---|
| `TERM_POINT_PVSRB` → `TERM_RATE_PREM` | `Index(PREM)` | `f"{base + n}_PL"` |
| `TERM_POINT_BENEFIT` → `TERM_RATE_BEN` | `Index(BEN)` | `f"{base + n}_{plan_option}"` |

`n` counts unique (Sex, Rateclass, Band) combos from 1 **and restarts per
suffix**, so `1001_PL` and `1001_30` are different tables, not a collision. The
benefit suffix is the raw 2-character IAF plan_option verbatim and may contain
letters (`3N`, `#0`). Base indexes are free multiples of 1000, so a plancode
owns up to 999 combos.

> ⚠️ `float("1001_30")` returns `100130.0` — Python accepts underscores inside
> numeric literals. Never let an index value reach `float()`/`int()`.

### Maturity comes from ME-AGE, and only caps AGE plans

Read the IAF plan header's **ME-AGE** and its use code (`1` = attained age,
`0` = duration) — *not* PAY-AGE, which is the premium-paying period.
`B155O200` proves the difference: PAY-AGE 020/0 but ME-AGE 095/1.

Apply an **AGE** maturity as a ceiling on attained age. **Never** apply a DUR
maturity — `B155R200` is a 20-year level term (ME-AGE 020/DUR) whose ultimate
rates correctly run to attained age 79. In practice the IAF's own ultimate
table usually runs out first; the cap only truly matters for non-renewable
plans (FIRSTLEVEL ≥ 999), which otherwise have no stopping point at all.

### FIRSTLEVEL / RENLEVEL only bite on compressed data

When the IAF already carries several select durations the level period is baked
in (one duration per policy year) and the user's FIRSTLEVEL/RENLEVEL are
ignored. They apply only to a single compressed select duration. FIRSTLEVEL is
**not** derivable from the IAF — it tracks PAY-AGE for level-term riders but not
for base plans — so it stays a user input.

### Benefit caps are user inputs

`cease_age` and `max_duration` combine as "whichever comes first" (e.g. "level
for 20 years or to age 60"). They are not in the IAF; the retired scripts passed
them ad hoc per run as `--ben-max-age` / `--ben-max-dur`.

### Verifying a change

`tools/rates/term_workup_reference_cases.json` pins seven plancodes covering
every rate shape (single/multi select duration, ART, non-renewable, letter
subtype, dual caps). Run it against the live database — it must report
`all_match: true`, since those rows were loaded by the retired pipeline:

```
venv\Scripts\python.exe tools\rates\verify_term_workup.py @tools\rates\term_workup_reference_cases.json
```

Supporting tools: `inspect_term_iaf.py` (what is in an IAF),
`probe_term_rates_schema.py` (live schema), `check_term_reference.py` (shared
modal-factor/band rows and the next free base index).

### The retired workbook

`Term DB Manager.xlsx` (workspace `..\Term_Rates`) is **not** used by SuiteView.
Its "Index list" allocation, per-plancode settings and reference tables are now
read from, or entered against, the live database. Note its "Band Struct" column
does **not** match `Index(BANDSPEC)` and must not be treated as a source.
