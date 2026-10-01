# SuiteView data access

This is the shared map for live data sources, local development data and core
adapter rules.

## Data sources and regions

| Name | Meaning |
| --- | --- |
| `UL_Rates` | SQL Server DSN for UL/Term/WL rates, ABR tables, access-control tables and PolView auxiliary policy sources. |
| `VRD Prod` | SQL Server DSN for SAP/VRD production ledger and reporting tables. |
| `NEON_DSN` | DB2/CyberLife production DSN for region `CKPR`. |
| `NEON_DSNM` | DB2/CyberLife model-office DSN for region `CKMO`. |
| `NEON_DSNT` | DB2/CyberLife test/acceptance DSN shared by `CKAS`, `CKCS` and `CKSR`. |
| `NEON_DSNS` | Optional secondary/system DB2 DSN when configured on a workstation. |

DB2 region mapping remains centralized in `suiteview.core.db2_constants` and is
surfaced through `suiteview.core.data_sources`:

| Region | DSN | Schema | Meaning |
| --- | --- | --- | --- |
| `CKPR` | `NEON_DSN` | `DB2TAB` | Production; default region. |
| `CKMO` | `NEON_DSNM` | `DB2TAB` | Model office. |
| `CKAS` | `NEON_DSNT` | `UNIT` | Acceptance. |
| `CKCS` | `NEON_DSNT` | `CYBERTEK` | Cybertek/test. |
| `CKSR` | `NEON_DSNT` | `CKSR` | System region. |

Use constants from `suiteview.core.data_sources`; do not redeclare DSN strings in
tabs, loaders or services.

## Ownership and lifetime

- `suiteview.core.data_access.ConnectionFactory` owns live connection opening for
  named sources (`policy_db2`, `ul_rates`) and ODBC/Access files.
- `DB2Connection` may cache policy DB2 connections by region for existing
  PolView/Illustration behavior, but it opens them through the factory.
- `Rates` (the legacy dbo views, still used by PolView, ABR and RateManager),
  RateManager repositories and schema discovery open their ODBC handles through
  the same factory.
- `suiteview.core.rates_schema.RatesSchemaRepository` reads UL_Rates schema
  `rates` (the four-structure rate tables owned by `Cyberlife_Rates\Rates_Database`)
  read-only through the same factory. Local development data has no `rates`
  schema, so it raises `ConnectionUnavailable` when `SUITEVIEW_LOCAL_DATA=1`.
  RERUN reads all of its UL/IUL rates this way (`suiteview.illustration.core.ul_rates.ULRates`);
  joint survivor plan lookups shared with PolView are
  `suiteview.core.joint_survivor_rates.JointSurvivorRateSource`.
- `suiteview.core.index_rates.IndexAssumptionTables` reads IUL illustrated
  rates, benchmark min/max and market returns from UL_Rates schema `rates`
  FUND rows (`IDX_ILL`, `IDX_BENCH_MIN`, `IDX_BENCH_MAX`, `MKT_RETURN`) through
  `RatesSchemaRepository`.
- `suiteview.data.database` and `suiteview.data.repositories` are only local
  profile SQLite storage (`~/.suiteview/data/suiteview.db`): saved connections,
  cached metadata, bookmarks and email helper data. They are not live-source
  connection factories.

## Read-only vs write

- Reads use explicit `autocommit`/`readonly` options where the driver supports
  them.
- Shared database writes must call the relevant guard immediately before the
  mutation (`guard_data_writable(...)`) and commit/rollback explicitly.
- RateManager loaders use transactions and verification; a prepared receipt is
  not proof of a committed load.

## Local-data gate

Local policy/rate SQLite data is enabled only by:

```text
SUITEVIEW_LOCAL_DATA=1
```

The comparison is exact. Values such as `true`, `yes`, `on`, `dev`, a database
path, or a missing variable do not enable local data. `SUITEVIEW_LOCAL_POLICY_DB`
and `SUITEVIEW_LOCAL_RATES_DB` only choose paths after the exact gate is already
enabled. Failed live access must raise the live error; it must not silently fall
back to local SQLite.

## Error hierarchy

`suiteview.core.data_access.errors` is the common model:

- `SuiteViewDataError` — base data-layer error.
- `ConnectionUnavailable` — a configured local or live source cannot be reached.
- `QueryFailed` — a connection was available, but a query/command failed.
- `ReadOnlyViolation` — a write was requested where SuiteView is read-only.
- `SourceValidationError` — source data, schema or allowlisted identifiers are invalid.
- `ExternalServiceUnavailable` — non-database service unavailable.

Adapters/repositories raise these. UI slots, worker boundaries and command
entrypoints catch them, log diagnostics and show an explicit message. Do not
catch them in lower layers to return blank rows, zeros or `None` as if data were
absent.

## Identifier rule

Values belong in parameters. Schema, table and column names must come from a
known source and be formatted through `suiteview.core.sql_identifiers`:

- `quote_identifier(name, dialect)`
- `qualified_name(schema, table, dialect)`
- `IdentifierCatalog` for table/column allowlists
- `top_clause(...)` / `limit_clause(...)` for validated row limits

Do not write f-strings that splice raw table or column names into SQL. If a UI or
file supplies an identifier, validate it against an allowlist before quoting it.
