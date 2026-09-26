# PolView data/rate refactor contracts

## FieldSpec registry

`suiteview.polview.models.policy_fields.FIELD_SPECS` is the scalar
`PolicyInformation` source contract. Each entry states table, column, converter
intent, default, product applicability and whether the column is required.

`PolicyData.data_item()` now raises `UnknownColumnError` for a requested column
that is not in a loaded table. A missing row still returns `None`. If a DB2 table
version legitimately omits a scalar column, declare that column optional in the
registry; do not rely on silent `None` or guess a replacement column.

Regenerate the field reference with:

```powershell
venv\Scripts\python.exe -B tools\polview\render_policy_fields.py
```

The generated reference is [`POLICY_FIELDS.md`](POLICY_FIELDS.md).

## ProductRules

`suiteview.polview.models.product_rules` centralizes product-family behavior:

| Strategy | Detection | Value table | Loan tables | Rate family | Support |
| --- | --- | --- | --- | --- | --- |
| `TraditionalRules` | `NON_TRD_POL_IND` not `1` | `TH_COV_PHA` | `LH_CSH_VAL_LOAN` | plancode group | no GLP/reinstatement |
| `WholeLifeRules` | traditional WL group/fallback | `TH_COV_PHA` | `LH_CSH_VAL_LOAN` | `WL` | fixed-premium rates |
| `AdvancedRules` | `NON_TRD_POL_IND = 1` except product line `I` | `LH_POL_MVRY_VAL` | `LH_FND_VAL_LOAN` | `UL` | GLP and UL reinstatement |
| `ISWLRules` | advanced + `PRD_LIN_TYP_CD = I` | `LH_POL_MVRY_VAL` | `LH_FND_VAL_LOAN` | `ISWL` | GLP, fixed-premium rates |
| `DIRules` | traditional + `PRD_LIN_TYP_CD = S` | `TH_COV_PHA` | `LH_CSH_VAL_LOAN` | `DI` | no GLP/reinstatement |

Call `policy.product_rules` for product-specific table choices, display-rate
selection, valuation-date source, support eligibility and rate-family decisions.

## Rate units, divisors and duration indexing

- UL/advanced COI rates come from `LH_COV_INS_RNL_RT.RNL_RT`, type `C`.
  Product line `I` rates are divided by `100`; all other advanced lines are
  divided by `100,000`.
- Traditional displayed rates come from `LH_COV_PHA.ANN_PRM_UNT_AMT`.
  `CoverageInfo.rate` displays `coi_rate` when it has been populated, otherwise
  `premium_rate`.
- UL rate arrays are one-based by policy duration. Matrix year `1` reads index
  `1`; index `0` is intentionally unused.
- Whole Life CVF schedules use actual source durations. Duration `0` is the
  issue date and duration `1` is the first anniversary. Do not apply the UL
  one-based convention to `WL_RATE_CV`.
- Matrix builders use `MatrixColumn`, `duration_rows()` and
  `rate_value_or_na()` so column definitions state the lookup and missing-value
  text in one place.
