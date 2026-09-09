# Dedicated ABR Quote automation

This is **SuiteView ABR Quote**, not the Illustration application's ABR projection.
It calls the existing medical-assessment and quote orchestration methods and
the exact `EmailPrintDialog` clipboard HTML/text builders. It constructs no Qt
widgets, application, dialogs or clipboard objects. PyQt6 must still be installed
because those existing methods live in UI modules.

## API and command

`suiteview.abrquote.automation.quote_abr(request)` returns a JSON-safe dictionary.
It performs read-only live CyberLife policy, TAICession and UL_Rates lookups.
Callers own authorization; the library never prompts and never sends email.
No production writes, rate loads or source refreshes are performed.

For offline fixtures or a trusted injected data source:
`calculate_quote(request, policy, database=..., policy_provenance=..., eligible_riders=...)`.
The policy is copied. The caller must supply verified identity and eligibility.

Run from the SuiteViewP root, using the existing virtual environment:

```powershell
.\venv\Scripts\python.exe -B tools\abrquote\quote.py --request C:\case\request.json --validate-only
.\venv\Scripts\python.exe -B tools\abrquote\quote.py --request C:\case\request.json
```

Validation-only does not retrieve policy/rates. A full command is a live read,
not a preview. stdout is one JSON response; diagnostics go to stderr.
Exit code 1 means an error, with `status`, `error_type`, and `message`.
Persist the response in the caller's case folder, not in SuiteView sources.

## Request contract (schema version 1)

```json
{
  "policy_number": "SYNTHETIC",
  "company_code": "01",
  "region": "CKPR",
  "quote_date": "2026-09-03",
  "effective_date": "2026-09-03",
  "assessment": {"rider_type": "Terminal"},
  "options": {"min_face_amount": 50000},
  "input_provenance": {"source": "original request reference, not response benchmark"}
}
```

All fields except `effective_date` and `input_provenance` are required.
This example is synthetic, not authorization or defaults for a real case.
Unknown fields, non-finite numbers, unsupported products and unverified active
ABR riders fail explicitly. Live policies must be active. Supported products:
TERM, UL, IUL, ISWL; WL/VUL/DI are not silently approximated.

Assessment:

- `Terminal` has only `rider_type`; the app uses fixed 50% annual mortality.
- `Chronic` or `Critical` requires `five_year_survival`, `ten_year_survival`,
  `life_expectancy_years`, `table`, or `increased_decrement`.
- Survival probabilities are fractions strictly between 0 and 1.
  Five/ten-year targets can be combined; LE cannot be combined with survival.
- Optional booleans: `return_after_5yr`, `return_after_10yr`.
  Dual survival supports the latter, not a contradictory five-year return.
- Direct `table`, `flat`, `table_2`, `flat_2`, `increased_decrement` inputs each
  require `{"value": number, "start_year": integer, "stop_year": integer}`.
  Start is inclusive, stop exclusive, relative to the app's policy duration.
  Decrement value is a percentage (200 means 200%), flat is annual per $1,000.
- Existing UI assessment semantics are **in lieu of** policy substandards.
  No unsupported in-addition flag is silently accepted.

Options:

- `min_face_amount` is explicitly required; obtain it from the request/data page
  or an explicitly approved rule, never infer it from a benchmark response.
- UL/IUL/ISWL additionally require explicit `level_annual_premium`,
  `loan_payoff`, `surrender_value`, even when an amount is zero.
- Optional `interest_rate_override` is a decimal (0.05 means 5%).
- Optional `after_partial_deduction` is retained in provenance. The canonical
  clipboard summary does not display it. `numbers.premium_after_partial` is the
  engine's raw display value, not a claim that a user-entered deduction was calculated.

## Date semantics and limits

The dedicated app has **one quote date**. A distinct requested effective date
is rejected, not silently mapped. Quote date selects the effective interest
month, per-diem year, reinsurance prior-month-end cutoff, and premium duration.
Mortality/APV and clipboard time-in-force retain the **loaded policy duration**,
just as the app does. Automation does not change this algorithm, reset dates
to today, or pretend current CyberLife retrieval is a historical snapshot.
Record/review valuation date versus requested quote date before relying on output.

Canonical product rules remain unchanged, including IssueVersion=1, current
rates with guaranteed-scale fallback, latest applicable interest/per-diem,
and existing premium-cessation schedule behavior. Missing required state fees,
TERM product pointers/bands/modal factors and rates are rejected rather than
using UI placeholder defaults. UL's unused TERM-display lookups can still lack
rates; its APV uses the explicit level-premium input.

## Response and evidence

Success contains `schema_version`, `status: "calculated"`, `html`, `text`,
`numbers` (the `ABRQuoteResult` fields), `assessment`, `policy`, and `provenance`.
Calculated is **not** approved/issued/emailed.

Provenance records the complete submitted input, policy identity/valuation,
verified rider set, UTC retrieval/calculation timestamps, canonical source-file
SHA-256 hashes, rate lookup arguments/results, and live rate SQL/parameters
with row counts/result SHA-256 fingerprints. Rate connections are request-local,
ODBC read-only, and guarded against non-SELECT statements.
Reinsurance connection/query failures cannot masquerade as `(none)`.
Policy/rate snapshots and input provenance may contain private data; keep local.
Policy lookup failures and unexplained goal-seek failures/residuals are rejected
(survival tolerance 0.0001; LE 0.001 years). A verified dual-survival zero-extra
boundary instead produces an explicit requested-versus-attained review condition,
not a generic numerical-bug claim. The default API does not issue new calculation
HTML for that condition. Algorithms and source targets are unchanged.

## Read-only input discovery

`tools\abrquote\inspect_policy.py --policy ... --region CKPR --quote-date YYYY-MM-DD
--assessment-request <json-file> --output <new-json-file>` resolves the company
through canonical lookup and preserves policy/rate observations outside the source
tree. The assessment-request object contains `assessment` plus source attribution.
It may compute medical-only diagnostics; it never invents financial inputs or
issues a quote. Failed numerical fitting and policy diagnostics are blockers.
Output creation is exclusive: an existing evidence file is never overwritten.

## Agent-facing financial input resolver

Do not substitute the policy's modal or annual billed premium for the theoretical
ABR funding premium. `tools\abrquote\resolve_inputs.py` bridges the two existing
subsystems: the Illustration **ABR funding solver** derives the financial input,
then the dedicated **ABR Quote application** supplies payout/clipboard output.
Neither engine is changed.

```powershell
.\venv\Scripts\python.exe -B tools\abrquote\resolve_inputs.py --input original-inputs.json --output ..\WorkOps_Manager\workspace\albert\independent-case
```

Resolver input:

```json
{
  "policy_number": "SYNTHETIC",
  "quote_date": "2026-09-03",
  "survival_5yr": 0.6,
  "survival_10yr": 0.4,
  "rider": "CT",
  "input_provenance": {"source": "original request"}
}
```

The dual-survival resolver supports CT/Critical UL-family cases. Optional `region`
otherwise uses the dedicated app's CKPR production region and verifies a unique
company through canonical lookup. It derives:

- Remaining-face rule from the **same helper used by AssessmentPanel**:
  $25,000 for UL/IUL/ISWL; $50,000 for TERM (TERM is not this resolver's scope).
- Net surrender from the canonical funding projection's **inforce**
  `surrender_value`, after its current-loan retirement and surrender charge.
  The loaded `LH_POL_MVRY_VAL.CSV_AMT`/generic `cash_surrender_value` is gross
  account value, not this net value. Do not use `ending_sv`, which includes
  forecast interest. Gross value, charge, and retired debt are retained in provenance.
  The dedicated payout engine passes this supplied net value directly through to
  `full_surrender_value`; it does **not** deduct debt/charges from that input again.
  Separately, raw calculated benefit deducts `loan_payoff`, and final payable
  benefit is the maximum of zero, raw benefit, and the supplied net surrender floor.
- Funding premium from `illustration.core.abr_quote.run_abr_quote`: monthly
  policy forecast conventions, next-anniversary annual payments, effective ABR
  interest, retirement of current debt, Option B→A, and existing $1,000 maturity
  surrender/shadow rules.
- Debt from that canonical funding run's `loan_retired`, using the Illustration
  policy's current LoanRecords buckets. **Do not use the generic policy
  `total_loan_balance` aggregate without checking dates**: its `get_loans()` path
  can sum historical fund-loan snapshots as well as current rows.

The command writes `request.json`, `output.json`, `live-inputs-resolved.json`,
`funding.json` (full diagnostic projection/rate cache), and `manifest.json`.
Files are exclusive-create and constrained to `WorkOps_Manager\workspace\albert`.
Exit 0 means calculated; exit 2 means pinned but blocked; exit 1 means an error.
Input/lookup exceptions also create `output.json` with `status: "error"`,
`needs_review: true`, `error_type`, `message`, `blockers`, null HTML/results,
and `quote_issued: false`; unresolved sidecars are JSON null. The manifest still
hashes every sidecar. Invalid output destinations, existing evidence, and
filesystem failures cannot guarantee a new error file: callers must also handle
nonzero subprocess exits and absent output without treating either as success.
Blocked output has `html: null`, `results: null`, and explicit blockers: it is
not a draft-ready quote. `request.json` may remain incomplete if derivation failed.
All current-value versus requested-date limitations remain explicit.

### Retrieval and solver diagnostics

The agent activity resolver does not equate a blank legacy `POL_STS_CD` with
termination. When that legacy field is absent, it conservatively verifies only
explicit `PRM_PAY_STA_REA_CD` 21/22 (maintained “Premium Paying” translations)
combined with actual `SUS_CD` 0 (“Active”). Missing suspense is not defaulted.
Other unverified status combinations remain blocked. This does not reconstruct
historical in-force status or approve medical eligibility.

The dedicated policy loader now reads the existing
`LH_POL_MVRY_VAL.CSV_AMT` first, avoiding the generic accessor's undefined
`TH_POL_MVRY_VAL` probe when the actual source value exists. Zero remains a
valid value, not a reason to fall back. This legacy field is gross account value;
the resolver supplies the net-surrender override described above. No financial
formula is changed.

`tools\abrquote\diagnose_inputs.py` accepts the resolver's same arguments and
adds `provenance.medical_root_cause` to its output. It traces the unchanged UI
dual-survival solver and projects period-two boundary ratings. UI semantics are
cumulative survival over 60/120 months from the loaded current policy month;
the second period starts 60 months later. The existing mortality engine ignores
negative table ratings. Consequently some physician-supplied survival pairs
cannot be fitted by this nonnegative-extra-mortality model: a target above the
zero-rating ceiling is a model-domain incompatibility, not a date correction.
The existing UI logs a failed root search and falls back to table zero; automation
must not describe that fallback as an exact fit or silently change formulas.
The UI does continue: it sets “Substandard values computed successfully” and emits
`assessment_ready`, while displaying attained survival separately from input.
That is evidence the application permits calculation at the boundary, not proof
of a documented claims-approval policy. The maintained CT actuarial memorandum
(pages 2–3, “Expected Future Mortality”) assigns the company responsibility for
evaluating health and selecting table ratings/flat extras; it does not prescribe
automatic acceptance of an infeasible survival pair. Automated draft handling
therefore receives `needs_review: true`, `status: "blocked"`, and null HTML/results.
The API deliberately does not inherit the UI's implicit boundary acceptance.
Previously pinned diagnostic calculation artifacts are not approved new quotes.
For this condition, resolver output includes `needs_review: true` and a structured
`warnings` entry with `kind: "nonnegative_mortality_boundary"`, original requested
and attained five-/ten-year survival, `period_2_extra_table: 0`,
`ui_permits_continuation: true`, and `exact_fit: false`. It is classified separately
from missing rates or a generic numerical failure. No physician input is replaced.

There is no boundary-reproduction override in the final API/CLI. Historical-source
reproduction is a separate caller workflow; previously pinned diagnostic outputs
must not be presented as newly approved calculations.

## Isolated validation

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\venv\Scripts\python.exe -B -m pytest tests\test_abr_automation.py -q -p no:cacheprovider
```

Tests use synthetic policies and in-memory rate interfaces, exercise the real
ABR assessment/mortality/premium/APV path and canonical renderer, and never
retrieve this work item's live policy or access response benchmarks.
