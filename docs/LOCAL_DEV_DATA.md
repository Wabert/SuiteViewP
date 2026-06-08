# Local Dev Data Mode

Local dev data mode lets PolView and Illustration/Forecasting run without the
work network, DB2, or the `UL_Rates` ODBC data source.

## Generate Local Databases

```powershell
venv\Scripts\python.exe tools\create_local_dev_data.py
```

This creates ignored local files under `bundled_data/dev/`:

- `policy_records.sqlite` - DB2-shaped policy record tables, attached as the
  `DB2TAB` schema in local mode.
- `rates.sqlite` - one-plancode UL rate tables using the same `Select_RATE_*`
  names queried by `suiteview.core.rates.Rates`.

The current synthetic fixture set uses plancode `1U144600` and these policies:

| Policy | Company | Notes |
| --- | --- | --- |
| `DEV10001` | `AA` | Base UL policy |
| `DEV10002` | `AA` | Regular loan balance |
| `DEV10003` | `AA` | Variable loan balance |
| `DEV10004` | `BB` | Different company |
| `DEV10005` | `BB` | Older issue-age policy with loan |

## Run In Local Mode

Set the switch before launching PolView, Illustration, tests, or helper scripts:

```powershell
$env:SUITEVIEW_LOCAL_DATA = "1"
venv\Scripts\python.exe scripts\run_polview.py DEV10001 --region CKPR
```

The same switch also routes Illustration/Forecasting rate lookups to the local
SQLite rates file:

```powershell
$env:SUITEVIEW_LOCAL_DATA = "1"
venv\Scripts\python.exe tools\check_local_dev_data.py
```

## Export A Real Policy From The Work Network

On a machine that can reach DB2, export the same data-bearing policy record
tables shown in PolView's Tables panel:

```powershell
venv\Scripts\python.exe tools\export_local_policy_data.py UE000576 --region CKPR
```

If the policy exists in multiple companies, rerun with the company code PolView
shows:

```powershell
venv\Scripts\python.exe tools\export_local_policy_data.py UE000576 --region CKPR --company AA
```

The exporter writes `bundled_data/dev/policy_records.sqlite` by default.  It
copies only mapped tables with policy rows, creates empty placeholders for the
rest of the mapped policy-record tables, and redacts:

- DOB/birth-date fields from `LH_CTT_CLIENT`.
- Name, phone, and taxpayer identifier fields from `VH_POL_HAS_LOC_CLT`.

Then move or keep that SQLite file on the offline computer and launch with:

```powershell
$env:SUITEVIEW_LOCAL_DATA = "1"
venv\Scripts\python.exe scripts\run_polview.py UE000576 --region CKPR
```

## Export Real UL Rates From The Work Network

On a machine with the `UL_Rates` ODBC DSN, export the common base plancode,
shadow-account plancode, benefit rates, and LTR rider rates needed for offline
Forecasting:

```powershell
venv\Scripts\python.exe tools\export_local_rate_data.py
```

Validate the exported local rate database with:

```powershell
venv\Scripts\python.exe tools\check_local_rate_data.py
```

By default this writes `bundled_data/dev/rates.sqlite` with:

- Base plancode `1U143900`.
- Shadow-account plancode `CCV00100`.
- LTR rider plancode `1U536C00`.
- Benefit rates for `1U143900` benefit types `76` and `39`.

You can override the defaults if needed:

```powershell
venv\Scripts\python.exe tools\export_local_rate_data.py `
  --plancodes 1U143900,CCV00100,1U536C00 `
  --base-plancode 1U143900 `
  --benefit-types 76,39
```

## Optional Path Overrides

By default the app reads from `bundled_data/dev/`.  You can point at another
fixture set with:

```powershell
$env:SUITEVIEW_LOCAL_POLICY_DB = "C:\path\policy_records.sqlite"
$env:SUITEVIEW_LOCAL_RATES_DB = "C:\path\rates.sqlite"
```

## Design Notes

- The production table and field names stay the same.
- The app code still uses `PolicyInformation`, `PolicyData`, and `Rates`.
- Local mode only swaps the underlying connection objects to SQLite.
- The checked-in generator uses synthetic, non-sensitive values.  A future work
  laptop export can add masked real-ish fixtures as long as it preserves table
  names and column names.