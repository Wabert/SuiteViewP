# Whole Life rates in Rate Manager

Whole Life uses the same live **UL_Rates** SQL Server database as UL and Term.
Its rates retain their original CyberLife search keys instead of being forced
into UL/Term's generated index conventions. This is a rate-source library, not
a completed Whole Life illustration engine.

## Workflow

1. Open **Rate Manager > Whole Life > Workup**.
2. Fill the separate **CVF**, **IAF**, **DIV** and **PUI** source rows, just like
   the UL workup. Any combination is allowed; leave unused rows blank.
   Each Browse button accepts multiple files. You can also paste a path,
   or separate multiple paths with `|`. NSP CSV and DIV map have their own
   optional rows. For IAF premiums, supply the company/user code: it is not
   present in that print and applies to all selected IAF files.
3. Parse once and inspect the first 100 rows of each resulting table. All
   selected sources form one combined package. A failure in any file blocks
   the entire preview/load rather than silently omitting that source.
4. Use **Create missing tables** once for the four new WL tables. This is
   additive; it never drops, recreates or alters an existing table.
5. Analyze against the database. Review new, unchanged and changed row counts.
6. Explicitly approve each table whose existing values may be updated, then
   confirm the load. All selected tables commit together. Changing any file
   row, the IAF company or the inference option clears the preview, comparison
   and approvals.

The **Database** view browses the rates, existing dividend tables and
`CYBERLIFE_PDF` with bound, exact-match column filters. The row limit is a
preview limit, not evidence that a source/table contains no further rows.

## Data ownership and safety

- New tables: `WL_RATE_CV`, `WL_RATE_NSP`, `WL_RATE_PUI`, `WL_RATE_PREM`.
- Existing dividend tables: `WL_DIV_HEADER`, `WL_RATE_DIV`,
  `WL_DIV_PLANKEY_MAP`. Their live schemas and existing key conventions are
  retained. Importing does not require the separate Cyberlife_Rates project.
- Natural keys are defined centrally in
  [`schema.py`](../suiteview/ratemanager/whole_life/schema.py).
- Rate precision in the four new tables uses SQL `decimal`, not binary float.
  Existing dividend `float` columns are preserved as they exist.
- Exact duplicate source rows are deduplicated. Conflicting duplicate keys,
  malformed numbers, missing data and incompatible schemas stop the load.
- An import inserts absent keys and updates approved changed values. It never
  deletes database rows missing from the source, and never replaces a whole
  database table. CV/dividend range contractions that would leave stale
  out-of-range durations are blocked.
- Before applying, the service rechecks the reviewed database state under
  serializable locks. A changed source package or database requires a fresh
  analysis. All selected table writes commit together.
- Existing values selected for update are backed up atomically before writing.
  Load receipts include source paths, SHA-256 hashes, counts and commit status
  under `~/.suiteview/rate_manager_backups/whole_life/`. A **prepared** receipt
  alone is not proof of a successful commit.
- The service verifies equality against the staged source before and after
  committing. Repeating the same import is a no-op.
- SuiteView Light cannot create tables or load rates. There is no fallback
  from failed live access to local SQLite.

### Table keys

| Table | Selection dimensions |
|---|---|
| `WL_RATE_CV` | `USER_CODE`, `RATE_KEY` (class/base/subseries), `USER_DEFINED`, `ISSUE_AGE`, `DURATION` |
| `WL_RATE_PUI` | `USER_CODE`, `PLANCODE`, `SEX`, `RATECLASS`, `ATTAINED_AGE`, `TABLE_RATING` |
| `WL_RATE_PREM` | Source plan/version/date, search-alias plan/version/date, first/last age, age-use code, rate type, scale start, full premium identifier |
| `WL_RATE_NSP` | `USER_CODE`, `RATE_KEY`, `BASIS_ID`, `SEX`, `RATECLASS`, `ISSUE_AGE`, `DURATION`, `EFFECTIVE_DATE` |

`WL_RATE_PREM` preserves both source ownership (`SOURCE_*`) and each searchable
alias. It does not expand duration-zero rates into policy years. Blank stop
dates remain SQL NULL; blank version/sex/class identifiers remain blank strings.
CV has no effective-date column because the supplied print does not provide one.
Use the load receipt to identify the source snapshot.

### CVF reports without duration zero

`NO ZERO DUR` is an absent value, not a numeric zero. Store
`DURATION_ZERO_VALUE = NULL` and do not synthesize a duration-zero rate.
In this format, printed grid `000-009` starts at **FIRST DUR**, rather than at
policy duration zero. The first printed decade contains FIRST-1; subsequent
cells advance from FIRST. Thus FIRST 121's first grid is `120-129`, and its
first value belongs to duration 121, not 241. D11's CKCRECCV definition
(printed page 110) describes
contiguous values beginning at FIRST and ending at LAST. For example, company
00 / `2EBF00` / age 1 has FIRST 1, LAST 59, and its `1000.00` at printed
offset 58 belongs to duration **59**. Validate the complete range and zero
padding after LAST. These schedules cannot trigger negative-header inference.

New tables allow NULL in this metadata column. For the existing development
database, `tools/rates/configure_wl_cv_zero_null.py` performs an explicit,
guarded nullability-only schema change; it never changes rate rows. Normal
parsing/loading does not automatically alter an existing schema.

### Cash-value zero floor

All explicitly negative CVF cash values are loaded as **0.00**, for every duration.
This applies to both `WL_RATE_CV.RATE` and `DURATION_ZERO_VALUE`, so previews,
comparisons and database loads use the same nonnegative values. Printed zeros
and positive values are unchanged unless the optional inference below is enabled.
The signed duration-zero header remains
authoritative when the grid omits its sign.

Source validation runs before flooring: inconsistent header/grid magnitudes,
conflicting duplicate source keys and nonzero padding still block loading.
Original source files are not modified; their hashes and update before-images
remain available in load receipts. Reloading older negative rows requires the
normal explicit approval to update `WL_RATE_CV`.

**Print sign limitation:** the CKCVDVPC grid does not reliably preserve signs.
For company 08, key `1WL511`, issue age 59, the header says duration zero is
`42.85-`, but the grid starts `42.85, 22.27, 0.94, 21.08`. The historical
`CVF - 2014.xlsx` GSL sheet, row 1591, also contains those unsigned values.
The signs of durations 1 and 2 cannot be established from these sources.
Do not claim that matching the print establishes the original signs.

### Optional early-negative CVF inference

User-approved assumption: enable **Infer early negative CVs (assumption)**
in Workup, or set `"infer_cvf_negatives": true` in the CLI configuration.
The option defaults **off** and applies only to CVF files.

Rule `negative-header-initial-decline-v1`:

1. Require FIRST duration **0** and an explicitly **negative duration-zero header**.
2. Starting with that header's magnitude, follow a **strict initial decrease**
   until the first increase establishes a local minimum.
3. Infer unsigned positive values **before** that minimum as negative and load
   them as zero. Keep the minimum positive; explicit negative signs still floor.
4. Leave later values alone. Skip inference if the initial decline has a plateau,
   never turns upward within the source range, or would override an explicit `+`.
   Do not use padding beyond LAST duration as evidence of a turn.

For `08 / 1WL511 / 59`, `-42.85, 22.27, 0.94, 21.08` becomes
**0.00, 0.00, 0.94, 21.08**. This is a conservative user-selected assumption,
not mathematical proof or recovered source signs. It does not repair every
possible unsigned negative or require all cash-value schedules to be monotonic.

Raw validation still runs before inference. Preview shows an assumptions table
with each key, duration, printed magnitude, loaded value, source line, signed
header and retained minimum. Per-file counts and the full rule/audit details
travel in `WholeLifePackage.sources` to the saved load receipt. Updates still
require table approval and a before-image backup. Keep this option consistent
when reloading the same source; an explicitly approved reload with it off can
restore the literal unsigned magnitudes.

### NSP CSV contract

Use the header-only
[`wl_nsp_template.csv`](../tools/rates/wl_nsp_template.csv) for independently
verified NSP values. This is a **SuiteView interchange format**, not a CyberLife
report format. All columns must be present, in template order:

```text
USER_CODE,RATE_KEY,BASIS_ID,BASIS_DESCRIPTION,SEX,RATECLASS,ISSUE_AGE,DURATION,EFFECTIVE_DATE,RATE_PER,RATE
```

Supply the actual mortality/interest/maturity/method reference in
`BASIS_DESCRIPTION` and a distinguishing `BASIS_ID`. `RATE` is the NSP premium
amount for `RATE_PER` face amount, in the same currency (e.g. `RATE_PER=1000`
means a premium per 1,000 of face). Units must be positive, rates nonnegative,
dates ISO `YYYY-MM-DD`, and decimals have at most eight places. Sex/rateclass may
be explicitly blank; company and actuarial basis cannot be omitted.

The importer validates structure, precision and identity, **not actuarial
correctness of user-supplied values**. No NSP rates are synthesized.

### Dividend dependencies

Each selected dividend file must include its own unambiguous PUA references;
files are not implicitly stitched into a reference set. Header and complete
rate schedules load together. Range contractions leaving stored rates outside
the new range are blocked. Corrections to shared, denormalized PUA factors
require all affected parents in the package. Because the existing schema does
not retain exact reference-record identity, this check conservatively includes
same-user/type/key parents across historical effective dates.

Maintenance dates are generated only for changed/inserted headers, not counted
as rate differences. Backups preserve SQL NULL, empty strings and fixed-width
spaces distinctly.

## Programmatic access and command-line loading

[`service.py`](../suiteview/ratemanager/whole_life/service.py) exposes
`parse_sources` (one kind), `parse_workup` (a mapping of kinds to file lists),
`WholeLifePackage` and `WholeLifeRepository`. Repository
instances own one connection and should be used inside a `with` block on the
thread performing the work. SQL identifiers are allowlisted and filter values
are parameterized.

For auditable batch work, use
[`wl_rate_workup.py`](../tools/rates/wl_rate_workup.py):

```powershell
venv\Scripts\python.exe tools\rates\wl_rate_workup.py @config.json
```

Example configuration:

```json
{
  "action": "preview",
  "kind": "IAF",
  "paths": ["C:\\Rates\\whole_life_iaf.txt"],
  "user_code": "06",
  "dsn": "UL_Rates"
}
```

For the same combined workup used by the UI, replace `kind`/`paths` with `files`:

```json
{
  "action": "preview",
  "files": {
    "CVF": ["C:\\Rates\\cash_values.txt"],
    "IAF": ["C:\\Rates\\whole_life_iaf.txt"],
    "Dividend": ["C:\\Rates\\dividends.txt"],
    "PUI": ["C:\\Rates\\pui.txt"]
  },
  "user_code": "06"
}
```

Use the actual IAF source company, not the illustrative `06` above. Omit
unneeded kinds or use empty lists. The UI's **DIV** row maps to the
`Dividend` service/configuration key.

Actions are `preview` (no database access), `analyze`, `create`, and `load`.
`load` refuses changed rows unless `replace_tables` explicitly lists those
table names. The optional `output` path saves a JSON verification report.
It also creates a sibling `.progress.json` showing the current phase. Progress
alone is not proof of completion; use the final report's `verified` flag and
the committed receipt. For large sources, run imports sequentially and keep
the process alive through staging, commit and post-commit verification.

[`inspect_wl_database.py`](../tools/rates/inspect_wl_database.py) reports the
live schema. [`verify_wl_database.py`](../tools/rates/verify_wl_database.py)
checks the schema and stages existing sample rows to prove they compare
unchanged, without modifying permanent data.

## Scope

Loading rates is not the same as resolving a policy's rates. Product selection
still requires the PDF's company, plan version/effective dates, search keys and
use codes. Do not infer issue age, premium duration, a cash-value/NSP mapping,
or a dividend scale from filenames or from a superficially similar plan.
`CYBERLIFE_PDF` is the existing source of product metadata; it is not rewritten
by these imports.

ISWL product-specific compilation, policy-level lookup rules, full illustration
calculations and exhaustive reconciliation of all historical rate files remain
separate work. Missing or unverified rate sources must not become zero rates.

### Source distinctions verified against CyberDoc

References are printed page numbers (D11 PDF pages add 10; D10 PDF pages add 8).

- **CVF**: D11 pp. 106-110 describes cash value per coverage unit, keyed by user,
  life class/base/subseries, user-defined area and issue age. Durations run
  inclusively from FIRST to LAST. Numeric zero-header grids label durations
  directly; `NO ZERO DUR` uses the offset mapping documented above. Out-of-range
  zero padding is not a rate. The supplied Comp06 print loses the sign of some duration-zero values
  in its grid: resolve using the signed header value, then apply the cash-value
  zero floor. The print omits effective dates; its run date must not be treated
  as a rate effective date.
- **IAF**: D11 pp. 1-9, 25-28 and 57-71 distinguishes IAF-record effective
  dates, rate-segment dates, age-use codes, aliases, and the seven-character
  identifier. `**` is a coverage rate; other suffixes can be benefits or plan
  options. A printed zero is not missing data. Types `S` and `Y` are tax-purpose
  single premiums, not automatically nonforfeiture NSP.
- **PDF**: D10 pp. 33-35 and 41-53 covers IAF-version selection and valuation
  class/base/subseries. Live `CYBERLIFE_PDF.FieldName` values verified for
  `851C1000` include `DBSVPLCL-LIFE-CLASS`, `DBSVPLBS-LIFE-BASE-SERIES`,
  `DBSVPLSS-LIFE-SUB-SERIES`, `DRCIAVER-IAF-VERSION-CODE` and
  `DBSCVSRC-CASH-VALUE-SOURCE`. Its `UserID` is `00`; this does not prove the
  company/user of an unlabeled IAF print.
- **PUI**: the CJUDTPUI print explicitly defines its user/plan/sex/class/
  attained-age/table-rating key and six-decimal rate. D10/D11 do not establish
  this custom table's units or equivalence to NSP. Preserve it independently.
- **NSP**: D10 pp. 63-65 and D11 p. 184 describe nonforfeiture mortality/
  interest/plan factors. None of the supplied prints establishes a complete
  NSP calculation basis. The NSP table must not be populated by relabeling
  cash values, dividend factors, PUI prices, or IAF `S`/`Y` premiums.

## Initial verification

The initial supplied sources yielded 1,211,226 CV rows (including 4,048
duration-zero values that are negative in the source and now floor to zero),
89,406 PUI rows and 2,202 IAF premium cells. The
201701 dividend extract's 2,316 headers and 172,866 rate rows matched the
existing database unchanged. All four new tables were created in live UL_Rates;
the CV and PUI rows were loaded and fully re-compared after commit. The IAF
source was previewed only: its printed
company/user identity needs confirmation before loading. NSP requires a
verified source/basis; neither gap is filled with guessed data.

### Cash-value reload with zero flooring (2026-09-07)

The CKAS CVF prints for companies 04, 06 and 08 were loaded together into live
`UL_Rates.dbo.WL_RATE_CV` and fully compared again after commit:

| Company | Stored rows |
|---|---:|
| 04 | 156,920 |
| 06 | 1,211,226 |
| 08 | 420,449 |
| **Total** | **1,788,595** |

The load inserted 577,369 rows and updated 216,590 existing rows. The update
count includes repeated `DURATION_ZERO_VALUE` metadata: 4,048 actual negative
duration-zero rates from the previous company 06 load were floored, along with
that header value on every affected duration row. A separate full-table query
confirmed zero negatives in either cash-value column for every company.
Before-images and the committed/verified receipt were retained by the loader.

### Audited early-negative reload (2026-09-07)

With the explicitly enabled inference rule, 8,298 existing rates were updated:
company 04: 526, company 06: 3,211, company 08: 4,561. No keys or row counts
changed. The full 1,788,595-row source package matched after commit, and PolView
policy `05335420` matched all 42 durations, beginning **0.00, 0.00, 0.94, 21.08**.
The receipt retains every inferred adjustment and its before-image. These
corrections remain assumptions about missing signs, not recovered source signs.

The company-00 classes 2/3/4/5/8 print subsequently inserted **1,814,607** rates,
including **9,399** inferred zeros, with no existing rows changed. Full
post-commit comparison succeeded. The `00 / 2EBF00 / age 1` schedule has all
59 durations, NULL zero metadata and `1000.00` at duration 59.
