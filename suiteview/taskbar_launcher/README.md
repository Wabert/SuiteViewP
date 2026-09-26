# `suiteview/taskbar_launcher`

## Purpose

SuiteView launcher/taskbar shell, AppBar docking, app launchers, tabs, tray handling and FileNav integration.

## Layer

Shell/startup layer; it may depend on app entry points but lower layers must not import it.

## Main entry points

`taskbar_window.py`, `appbar.py`, `app_launchers.py`, `file_explorer_tab.py`, `single_instance.py`.

## Key modules

`collaborators.py`, `taskbar_modes.py`, `taskbar_system.py`, `taskbar_tabs.py`, `taskbar_ui.py`.

## Tests

`tests/test_taskbar_*.py`, `tools/app/test_taskbar_tray_cycle.py`.

## Docs

`docs/TASKBAR_ARCHITECTURE.md`, `docs/shell/SHELL_MANUAL.md`, `docs/FILENAV_ARCHITECTURE.md`.
