---
description: Build SuiteView as a distributable EXE (ZIP folder) for coworkers
---

# Build SuiteView Distribution

This workflow builds SuiteView into a distributable folder + ZIP that coworkers can extract and run.

## Prerequisites
- Virtual environment activated (`venv`)
- PyInstaller installed (`pip install pyinstaller`)
- ABR Quote database populated at `~/.suiteview/abr_quote.db`

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
venv\Scripts\python.exe scripts/build_distribution.py
```

The script automatically:
- Copies `abr_quote.db` from `~/.suiteview/` to `bundled_data/`
- Cleans previous build artifacts
- Runs PyInstaller with `SuiteView.spec`
- Creates `dist/SuiteView.zip`

## Output
- **Folder**: `dist/SuiteView/` — the complete distributable application
- **ZIP**: `dist/SuiteView.zip` — ready to send to coworkers

## Distribution Instructions for Coworkers
1. Extract `SuiteView.zip` to any folder (e.g., Desktop or Documents)
2. Run `SuiteView.exe` from the extracted folder
3. On first launch, the ABR Quote database is automatically installed to `~/.suiteview/`

## What's Included in the Distribution
- SuiteView File Navigator
- PolView (Policy Viewer) — requires DB2 ODBC driver & network access
- ABR Quote Tool — pre-loaded with rate data

## What's NOT Included (dev-only)
- Audit button & Audit Tool
- Email Attachments
- Task Tracker
- Rate File Converter

## Notes
- The `DEV_MODE` flag is automatically `False` in the built exe
- PolView and ABR Quote are always available (not gated by DEV_MODE)
- The `bundled_data/` directory is in `.gitignore`
