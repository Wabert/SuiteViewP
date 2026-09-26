# Rate Manager rate-table families

Rate Manager loads reviewed source packages into the shared `UL_Rates` SQL Server
database. It never drops or recreates rate data as part of normal imports:
packages are analyzed, reviewed, backed up when needed, written in one
transaction and verified after commit.

## UL workup tables

The UL workup uses two independent pointer groups. A package may contain either
group or both, but every table in a present group is required.

| Group | Pointer table | Rate tables | Natural ownership |
| --- | --- | --- | --- |
| Base | `POINT_PVSRB` | `RATE_COI`, `RATE_TRGPREM`, `RATE_SCR`, `RATE_EPU` | `Plancode`, `IssueVersion`, `Sex`, `Rateclass`, `Band`, `State` |
| Benefits | `POINT_BENEFIT` | `RATE_BENCOI`, `RATE_BENTRG` | `Plancode`, `BenefitType`, `Benefit`, `IssueVersion`, `Sex`, `Rateclass`, `Band` |

Rate rows are keyed by their physical `Index(...)` column plus scale, age and
duration dimensions. A replacement may update an index only when every pointer
reference belongs to the same plancode scope being replaced; cross-plancode
collisions are blocked.

## Term tables

Term uses varchar index identifiers, not numbers. Suffixes keep independent
spaces from colliding, for example `1001_PL` and `1001_30`.

| Pointer table | Rate tables |
| --- | --- |
| `TERM_POINT_PV` | `TERM_RATE_MODEFACT`, `TERM_RATE_BANDSPECS` |
| `TERM_POINT_PVSRB` | `TERM_RATE_PREM` |
| `TERM_POINT_BENEFIT` | `TERM_RATE_BEN` |

## Whole Life tables

Whole Life preserves CyberLife source keys instead of compiling pointer indexes.

| Table | Key dimensions |
| --- | --- |
| `WL_RATE_CV` | `USER_CODE`, `RATE_KEY`, `USER_DEFINED`, `ISSUE_AGE`, `DURATION` |
| `WL_RATE_NSP` | `USER_CODE`, `RATE_KEY`, `BASIS_ID`, `SEX`, `RATECLASS`, `ISSUE_AGE`, `DURATION`, `EFFECTIVE_DATE` |
| `WL_RATE_PUI` | `USER_CODE`, `PLANCODE`, `SEX`, `RATECLASS`, `ATTAINED_AGE`, `TABLE_RATING` |
| `WL_RATE_PREM` | source plan/version/date, alias plan/version/date, age-use fields, rate type, scale and premium identifier |
| `WL_DIV_HEADER` | `HEADER_ID` |
| `WL_RATE_DIV` | `HEADER_ID`, `DURATION` |
| `WL_DIV_PLANKEY_MAP` | `PLANCODE`, `SEX`, `RATECLASS` |

## Loader phases

1. **Package validation** (`ratemanager.package`): CSV headers, natural keys,
   numeric coercion and duplicate detection.
2. **Analysis** (`ratemanager.analysis`): compare reviewed package rows with
   current database rows and compute a digest of the reviewed state.
3. **Plan** (`ratemanager.plan`): normalize requested actions, block unsafe
   replacements and identify rows to insert, delete and back up.
4. **Repository transaction** (`ratemanager.repository`): re-analyze under a
   serializable transaction, write a backup receipt, apply changes and verify.
5. **Backup** (`ratemanager.backup`): preserve removed/replaced rows with a
   manifest. A prepared backup is not proof of a committed load.

SQL identifiers are quoted through `suiteview.core.sql_identifiers`; data values
are always parameters. Live connection opening goes through the shared
`suiteview.core.data_access` factory.
