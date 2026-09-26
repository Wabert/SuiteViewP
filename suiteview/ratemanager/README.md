# `suiteview/ratemanager`

## Purpose

UL, Term and Whole Life rate workups, parser review, database comparison/loading and backups.

## Layer

Rate-domain service/UI layer; database writes must use shared permission/backup guards.

## Main entry points

`product_chooser.py`, `ratemanager_window.py`, `package.py`, `database_panel.py`.

## Key modules

`workup/`, `whole_life/`, parsers/exporters/loaders at package root.

## Tests

`tests/test_rate*.py`, `tests/test_*workup*.py`, `tests/test_term*.py`.

## Docs

`docs/ratemanager/RATEMANAGER_MANUAL.md`, `docs/RATEMANAGER_RATE_TABLES.md`, `docs/RATEMANAGER_WL.md`, `docs/PARSER_LAYOUTS.md`.
