# `suiteview/mainframe_nav`

## Purpose

TN3270 terminal/navigation windows and mainframe content search.

## Layer

App UI/service layer for mainframe navigation; keep terminal parsing isolated.

## Main entry points

`mainframe_window.py`, `mainframe_nav_screen.py`, `mainframe_terminal_screen.py`, `tn3270.py`.

## Key modules

`content_search.py`, `search_content_window.py`, `styles.py`.

## Tests

`tests/test_tn3270*.py` when parser behavior changes.

## Docs

`docs/TN3270.md`.
