# `suiteview/ui`

## Purpose

Shared PyQt widgets, dialogs, helpers, workers and visual styles used by multiple apps.

## Layer

Shared UI layer; app windows depend on it, but it should not depend on app windows.

## Main entry points

`widgets/filter_table_view.py`, `widgets/frameless_window.py`, `widgets/mini_explorer.py`, `workers.py`.

## Key modules

`dialogs/`, `helpers/`, `widgets/`, `signals.py`, `access_control.py`.

## Tests

`tests/test_*ui*.py` plus native `tools/app/verify_*.py` helpers.

## Docs

`docs/ui/UI_CONVENTIONS.md`, `docs/WORKERS.md`.
