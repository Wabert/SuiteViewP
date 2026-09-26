# Taskbar architecture

`SuiteViewTaskbar` is the shell window. It owns the Qt window and a
`TaskbarState`; behavior is grouped into explicit collaborators:

| Collaborator | Responsibility |
| --- | --- |
| `TaskbarChrome` | Header, app buttons, tools menu, tab widget and footer construction. |
| `TaskbarModes` | Full, compact, floating, resize and AppBar geometry transitions. |
| `TaskbarTabs` | FileNav tab creation, closing, title updates and splitter sharing. |
| `SystemTray` | Tray menu, activation, permissions and child-window setup. |
| `AppLauncher` | Named app-launching collaborator sharing the tray/window setup seam. |

Collaborators receive the window, `TaskbarState`, `TaskbarChrome` widgets and a
typed callback surface explicitly. They do not use `__getattr__`/`__setattr__`
forwarding and do not write attributes onto the window. Shared mutable shell
state, including child-window references, lives in `TaskbarState`; widgets built
by the chrome live on `TaskbarChrome`.

The shell still exposes the public method names used by tests, shortcuts and
launcher scripts through named delegates, but new code should add behavior to
the collaborator that owns the concern instead of adding more state to the
window.

## AppBar exception

The compact bar is a Windows shell AppBar. Unlike normal SuiteView windows it is
allowed to use manual resize grips and direct `setGeometry()` while it negotiates
reserved screen space. Keep Win32 AppBar calls in `taskbar_launcher/appbar.py`
and docking/floating geometry in `TaskbarModes`/`SystemTray`.

## Verification

Guard tests:

- `tests/test_taskbar_import_smoke.py`
- `tests/test_taskbar_restore.py`
- `tests/test_taskbar_quit.py`
- `tests/test_taskbar_tray_menu.py`
