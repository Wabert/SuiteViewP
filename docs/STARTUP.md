# SuiteView startup

`suiteview.startup` is the canonical startup path for the desktop suite.

## Entry points

| Entry point | Purpose | Options |
| --- | --- | --- |
| `suiteview/main.py` | PyInstaller/source package entry | live data, title `SuiteView`, mutex `SuiteView_SingleInstance_Mutex`, crash log `crash.log` |
| `scripts/run_suiteview.py` | source script launcher | live data, title `SuiteView`, mutex `SuiteView_SingleInstance_Mutex`, crash log `suiteview_crash.log` |
| `scripts/run_suiteview_local.py` | offline development launcher | `SUITEVIEW_LOCAL_DATA=1`, title `SuiteView (LOCAL DATA)`, mutex `SuiteView_Local_SingleInstance_Mutex`, crash log `suiteview_local_crash.log` |

Both script entry points build a `StartupOptions` instance and call
`run_suiteview(options)`. The PyInstaller spec still points at
`suiteview/main.py`, which delegates to the same startup module.

## Startup ownership

`run_suiteview` owns, in order:

1. local-data environment selection;
2. single-instance activation through `suiteview.core.single_instance`;
3. profile initialization and maintenance checks;
4. crash-log handler installation and `sys.excepthook` setup;
5. `pythonw.exe` stdout/stderr redirection to the selected crash log;
6. stale `win32com` generated-cache cleanup;
7. Qt message handling;
8. Windows AppUserModelID registration;
9. `QApplication` creation and taskbar launcher construction.

The exception hook logs unhandled exceptions to the crash log. It leaves
`KeyboardInterrupt` on Python's default hook so development runs still stop in
the ordinary way.

## Local-data mode

Only `StartupOptions(local_data=True)` or `scripts/run_suiteview_local.py` sets
`SUITEVIEW_LOCAL_DATA=1`. This mode uses its own title, mutex and AppUserModelID,
so it cannot refocus or block a live-data SuiteView instance. Local data remains
opt-in only; the ordinary launchers never set the variable.

## Cross-app launch registration

Shell-owned factories are registered through
`suiteview.taskbar_launcher.app_launchers.register_default_launchers()`. Lower
layers request app launches with `suiteview.core.app_launcher.launch_app(app_id)`
instead of importing another app's window class.
