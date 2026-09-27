# `suiteview/core`

## Purpose

Cross-cutting infrastructure: access control, data sources, DB2/ODBC helpers, Excel export, profile paths and shared utilities.

## Layer

`core` is the lowest SuiteView application layer; it must not import app UI packages.

## Main entry points

`db2_connection.py`, `data_sources.py`, `excel_export.py`, `access_control.py`, `profile_paths.py`.

## Key modules

`data_access/`, `rates.py`, `local_dev.py`, `sql_permissions.py`, `support_files.py`.

## Tests

`tests/test_layering.py`, `tests/test_db2_connection_errors.py`, `tests/test_profile_layout.py`, `tests/test_runtime_access.py`.

## Docs

`docs/DATA_ACCESS.md`, `docs/LOCAL_DEV_DATA.md`, `docs/PROFILE_STORAGE.md`.
