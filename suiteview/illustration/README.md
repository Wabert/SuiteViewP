# `suiteview/illustration`

## Purpose

RERUN/Illustration engine, policy scenarios, plancode config, UI and debug/export flows.

## Layer

Calculation engine/services and app UI above domain models and rates.

## Main entry points

`main.py`, `api.py`, `core/calc_engine.py`, `ui/`, `models/`. Participating whole
life has its own monthly engine in `core/parwl/` (service façade `core/parwl/service.py`,
report pages `core/parwl/report.py`, models in `models/parwl.py`, RERUN workspace
`ui/parwl_workspace.py`); indeterminate premium term the same in `core/term/`
(`models/term.py`, `ui/term_workspace.py`). Both share `core/fixed_premium.py` (plan,
band and mode-factor lookups), `core/inforce_check.py`, `core/ledger_report.py` (UL-style
ledger pages) and the `ui/illustration_pages_view.py` / `ui/policy_snapshot_widgets.py`
pages. Illustration reports print through `ui/report_pages.py` (landscape PDF, preview
sheets) with text layout from `core/report_text.py`.

## Key modules

`core/`, `models/`, `plancodes/`, `debug/`, `scripts/`.

## Tests

`tests/test_illustration_*.py`, `tests/test_value_rollback_*.py`, `tests/test_glp_target_engine.py`.

## Docs

`docs/Illustration_UL/ENGINE_STEPS.md`, `docs/Illustration_UL/RUN_VALUES_FLOW.md`, `docs/Illustration_UL/RERUN_MANUAL.md`.
