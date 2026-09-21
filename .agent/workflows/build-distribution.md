---
description: Build SuiteView as a distributable EXE (ZIP folder) for coworkers
---

# Build SuiteView Distribution

This workflow builds SuiteView into a distributable folder + ZIP that coworkers can extract and run.

## Prerequisites
- Virtual environment activated (`venv`)
- PyInstaller installed (`pip install pyinstaller`)
- UL_Rates access-control tables provisioned, with intended recipients enabled
- Reviewed reference data only; never bundle the developer's personal profile

## Version Bump (do this FIRST, every build)

The version lives in `suiteview/__init__.py` (`__version__`) and is shown in
the taskbar header (e.g. `SuiteView (2.0)`).

1. Read the current `__version__` from `suiteview/__init__.py`.
2. Tell the user the **current version** and ask for the **new version**.
   Wait for confirmation before building.
3. Update `__version__` to the agreed value.

## Build Steps

// turbo
1. Run the build script (must use venv Python so PyInstaller finds all packages):
```
venv\Scripts\python.exe tools\app\build_distribution.py
```

The script automatically:
- Cleans previous build artifacts
- Runs PyInstaller with `SuiteView.spec`
- Creates `dist/SuiteView-<version>.zip` and verifies its contents and embedded version

## Output
- **Folder**: `dist/SuiteView/` — the complete distributable application
- **ZIP**: `dist/SuiteView-<version>.zip` — ready to send to coworkers

## Distribution Instructions for Coworkers
1. Extract `SuiteView-<version>.zip` to any folder (e.g., `C:\Apps\SuiteView`)
2. Run `SuiteView.exe` from the extracted folder
3. The packaged app verifies their native Windows identity against UL_Rates.
   Missing or disabled users cannot start it; configure their roles before rollout.

## What's Included in the Distribution
- All SuiteView modules in one build, enabled according to runtime app grants
- PolView requires the DB2 ODBC driver and network access
- Runtime authorization and shared rates require the UL_Rates ODBC DSN

## Notes
- Source runs always have developer access; packaged apps never inherit that bypass
- `AllApps` controls app entry, not Administrator or database/support-file write bits
- SQL Server grants and filesystem permissions remain separate requirements
- The `bundled_data/` directory is in `.gitignore`
