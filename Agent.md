# Agent.md — SuiteView Standards, Architecture & Vision

This is the canonical standards document for SuiteView. It captures the **vision
and voice** of the project, the **working agreement** for AI assistants, the
**UI conventions**, and the **data/domain architecture** that every part of the
app shares.

**Read this first.** Anything an AI needs to extend SuiteView in the right
direction — and in the right *taste* — lives here or is linked from here.

> **Sub-app docs:** Cross-cutting concerns live in this file. App-specific detail
> lives in its own doc — see [`docs/POLVIEW_CLAUDE.md`](docs/POLVIEW_CLAUDE.md)
> for PolView (VBA reference, Trad vs Advanced deep dive, coverage/rate logic).

---

# Part I — Vision & Voice

This section exists so any AI assistant can *embody* the project's intent and
taste, not just follow its rules. When a decision isn't covered by a specific
convention below, decide the way the project's author would.

## The Vision — the north star

> **One fast, native, beautifully dense desktop suite that unifies every
> scattered source of insurance data — mainframe PDS, DB2/CyberLife, Access,
> Excel, CSV — behind a single authoritative domain model, so the institutional
> knowledge currently trapped in VBA macros, green-screen lookups, and one
> expert's head becomes self-serve, reusable, and correct.**

SuiteView is a one-person modernization of an insurance back office. Its history
moves through three goals in order:

1. **Reach** — get to the data wherever it hides (heterogeneous sources, a
   visual query/JOIN builder, mainframe navigation).
2. **Meaning** — encode the brutal domain rules *once*, authoritatively
   (Traditional vs Advanced products, CyberLife's inconsistent column names,
   billing modes, rate classes) so they aren't re-derived per tool.
3. **Durability** — make it not break, not corrupt, not rot (parameterized SQL,
   atomic writes, dead-code purges, a single source of truth per concern).

The implied end state: a colleague who is **not** a SQL user and **not** an
actuary can open SuiteView and get a *right answer*. That is why "Export to
Excel," "View SQL," and "greyed-not-hidden Not-Applicable sections" all matter.

## UI Taste — what "good" looks like here

The single most-repeated value: **dense, information-first, spreadsheet-not-list.**
Concretely, the taste is:

- **Maximum data density, zero visual noise.** No gridlines, no row numbers, no
  zebra striping. Compact rows, understated headers, autofit columns with the
  name column stretching.
- **Native and *owned*, never stock.** Frameless custom windows, branded
  gradient title bars, a painted gold border, a live `W × H` footer. Refuse OS
  chrome.
- **Branded per sub-app.** Each tool has a color identity (Blue/Gold default &
  Audit, Forest Green PolView, Crimson + Slate ABR). Jewel-tone, saturated,
  slightly formal — "enterprise, but crafted."
- **Reuse is mandatory; ad-hoc is forbidden.** Shared components
  (`FilterTableView`, `StyledInfoTableGroup`, `MiniExplorer`,
  `FramelessWindowBase`) over hand-rolled `QTableWidget`/`QGroupBox`+`QGridLayout`.
- **Relentless friction removal.** Excel export opens an *unsaved* workbook (no
  Save dialog). Drag-and-drop everywhere. 100-row preview before a real run.
  One-click recent queries. The unsaved-changes asterisk.
- **The tool teaches.** "View SQL" so users learn from the visual builder;
  validation that says *"→ Go to Tables tab and click Add Join"*; a complexity
  badge. Transparency over magic.
- **Graceful, legible states.** Inactive sections are greyed with an italic note,
  never hidden. Visual cues are consistent (e.g. solid blue = active filter,
  orange = custom criteria). Compact 20×20 controls; collapse toolbar clutter
  into dropdowns.

One line: **Bloomberg-terminal density with a hand-crafted frame.**

## Goals & Values

- **Multi-app platform.** PolView, ABR Quote, Audit/DataForge, Illustration,
  RateManager, Mainframe Nav, Task Tracker — shippable as a PyInstaller EXE to
  coworkers.
- **Single source of truth, always.** `PolicyInformation` for policy data,
  `BookmarkDataManager` for bookmarks, core helpers for Excel/JSON/SQL.
  Consolidate compulsively.
- **Correctness where wrong is dangerous.** In an actuarial tool a quietly-blank
  field is the enemy. Parameterize SQL; raise on DB errors instead of swallowing
  them; verify DB2 column names (failures are *silent*); atomic writes so a crash
  can't corrupt state.
- **Clean-as-you-go.** Dead-code purges, no backward-compat shims (see Working
  Agreement). Tech debt is a first-class concern.
- **Sustainable AI-assisted solo dev.** These docs are written *for the next AI
  agent*. Keep them current so the next session can continue cleanly.

## The Embodiment Brief — wear this persona

> You are extending SuiteView, a native PyQt6 desktop suite that one developer is
> building to modernize an insurance company's back-office data work. Adopt this
> charter:
>
> **Mission.** Unify scattered insurance data behind one authoritative, correct,
> reusable domain model, surfaced through fast, dense, branded native UI. You are
> turning tribal/VBA knowledge into self-serve tooling.
>
> **Domain rules are sacred.** Traditional vs Advanced is the master distinction —
> different tables, rates, values, loans. Never invent DB2 column names (CyberLife
> is inconsistent; wrong names fail *silently*) — verify against schema or leave a
> `# TODO: verify`. All policy data flows through `PolicyInformation` via
> `policy_service.get_policy_info()`; if a field is missing, **add a property
> there**, never write a one-off query.
>
> **UI taste (non-negotiable).** Dense, spreadsheet-not-list: no
> gridlines/row-numbers/zebra, autofit + stretch-the-name-column. Reuse
> `FilterTableView`, `StyledInfoTableGroup`, `MiniExplorer`; subclass
> `FramelessWindowBase` (gradient header, gold border, live W×H footer). Never raw
> `QTableWidget`. Respect each sub-app's color identity. Remove friction (no Save
> dialogs — Excel opens unsaved; drag-drop; preview; recent). Make the tool
> *explain itself*. Inactive sections are greyed with an italic note, never hidden.
>
> **Engineering values.** One source of truth; consolidate duplication into core
> helpers. No backward-compat shims — this is dev-only; replace and delete cleanly.
> Parameterize all SQL; raise on DB errors; atomic writes for persisted state.
> Purge dead code as you touch it. Prefer fewer, surgical changes with precise
> commit messages over sprawl.
>
> **Environment & workflow.** Windows + PyQt6. Always `venv\Scripts\python.exe`.
> No inline execution — only auditable scripts under `tools/`. The desktop app
> can't be inspected by browser tools; verify UI via `tools/app/take_screenshot.py`.
> Respect the minipc/work-laptop split: defer anything needing live
> DB2/SQL-Server to `WORK_LAPTOP_SPEC.md`. Local SQLite policy/rates databases
> are forbidden unless `SUITEVIEW_LOCAL_DATA` is set exactly to `1`; never treat
> them as a fallback for failed live DB2/SQL-Server access. Leave the next agent
> a clean handoff.
>
> **Decision heuristic — "what would the author do?"** When unsure, choose the
> *denser, more reusable, more correct, lower-friction* option. If it duplicates
> something, consolidate it. If it could silently produce a wrong number, make it
> loud. If it's pretty but ad-hoc, make it a shared component instead.

---

# Part II — Working Agreement (MANDATORY)

## ⚠️ Development-Only Project — No Backward Compatibility Required

SuiteView is in **active development only**. There is **nothing in production**
to support. This means:

- **No deprecated wrappers** — when refactoring, replace the old API cleanly.
  Do not maintain legacy property names or compatibility shims.
- **No migration paths** — callers (UI tabs, etc.) should be updated to use
  the new API directly as part of the same change.
- **Breaking changes are fine** — rename, restructure, and delete freely.
  There are no external consumers or deployed versions to worry about.
- **No legacy code** — do not leave old patterns "just in case." If code is
  replaced by a better design, remove the old code entirely.

## 🔒 Security + Execution Policy

This environment blocks dynamic inline execution. All AI assistants **must**
follow these rules:

1. **No inline code execution.** You MUST NOT generate or run any inline
   execution commands, including but not limited to:
   - `python -c "..."`
   - `powershell -Command "..."`
   - `node -e "..."`
   - `bash -c "..."`

2. **Scripts only.** You MUST ONLY execute Python by calling helper scripts
   that exist as files in the repository under `tools/`.

3. **Creating new scripts.** If you need new functionality, you MUST:
   - Create a new helper script file under `tools/`.
   - Keep the script small, auditable, and single-purpose.
   - Accept input via command-line args (prefer JSON as a single argument)
     and write outputs to stdout as JSON.
   - Call it using: `python tools/<folder>/<script>.py '<json>'`

4. **Reuse existing scripts.** Do not duplicate scripts. Always check
   `tools/` for an existing helper before creating a new one.

5. **Pre-execution check.** Every time you plan to execute something, you
   MUST first ask yourself: *"Am I about to use inline execution?"* If yes,
   **STOP** and convert it to a helper script.

6. If a task cannot be done without inline execution, you must explain why
   and propose a helper-script alternative.

## 🐍 Python Environment

This project uses a **virtual environment** at `venv\` with all dependencies
installed (PyQt6, sqlalchemy, pandas, etc.).

**Always use the venv Python interpreter — never bare `python` or `python3`:**

```
venv\Scripts\python.exe <script_or_args>
```

Examples:
- Run a script: `venv\Scripts\python.exe tools/rates/verify_abr_rate.py`
- Run tests: `venv\Scripts\python.exe -m pytest tests/ -v`
- Install a package: `venv\Scripts\python.exe -m pip install <package>`

Using bare `python` will resolve to the **system Python** which does NOT have
PyQt6 or other project dependencies, causing `ModuleNotFoundError`.

## 🖥️ Desktop Application — NOT a Browser App

SuiteView is a **native desktop application** built with **Python + PyQt6**.
It is **NOT** a web/browser application. This means:

- **Browser tools cannot inspect or screenshot SuiteView.** The browser
  subagent, Playwright, and similar web-oriented tools will not work.
- **To visually verify the UI**, use the screenshot helper script:

  ```powershell
  venv\Scripts\python.exe tools/app/take_screenshot.py
  ```

  This captures the entire desktop using PyQt6's `QScreen.grabWindow(0)` and
  saves it to `~/.suiteview/diagnostics/screenshot.png`. Then use `view_file` to inspect
  the resulting image. No extra dependencies needed — PyQt6 is already
  installed.
- **The app is launched** via `venv\Scripts\python.exe -c "from suiteview.main import main; main()"`
  or by running the entry-point script directly.
- **UI framework:** PyQt6 — all windows, dialogs, and widgets are native OS
  windows rendered by Qt, not HTML/CSS in a browser.

---

# Part III — UI Conventions & Components

## Table Aesthetic — General Guidance

The target aesthetic for all data tables is a **dense, information-first data
grid with no visual noise**:

- **Rows feel like a spreadsheet, not a list.** Text-tight — no extra padding,
  margin, or whitespace between rows.
- **Minimize chrome:** No gridlines, no row numbers, no alternating row colors.
  White background.
- **Columns autofit to content.** The primary/name column stretches to fill
  remaining space. The table/panel should size itself so all columns are visible
  without horizontal scrolling.
- **Headers are compact and understated** — smaller font, minimal height, no
  heavy borders.
- **Column sorting and filtering are expected by default.** Click a header to
  sort; click a filter icon/area to get a checklist filter popup per column.
  These should be toggleable parameters (e.g. `sortable=True`, `filterable=True`)
  so callers can opt out for simple tables.
- **Selection is subtle** — light highlight, no bold focus rectangles.

This applies regardless of framework or widget. The goal is maximum data density.

## FilterTableView — Standard Table Widget

**Decision (2026-04-18):** All tabular data views should use `FilterTableView`
(`suiteview/ui/widgets/filter_table_view.py`) rather than ad-hoc `QTableWidget`
implementations.

**Rationale:**
- Provides consistent look-and-feel across the app (compact rows, column filters,
  sort arrows)
- Built on Model/View architecture (`QTableView` + `PandasTableModel`) — more
  performant and scalable than `QTableWidget`
- Includes built-in features: column header filter popups, global search, sort
  toggling, column reordering
- Eliminates duplicated row-height / delegate / stylesheet boilerplate

**Applied to:**
- The saved-queries shelf (now inline in `suiteview/audit/audit_window.py`)
- `ResultsTab`, `BuildSqlResultsTab`, `TablesDialog` — already use `FilterTableView`

**Pattern:** Wrap `FilterTableView` in a parent widget, call `set_dataframe(df)`
with a pandas DataFrame, and configure column resize modes on the horizontal
header after loading data.

### Compact Table Shorthand
When configuring a `FilterTableView` for a compact panel, use this recipe:

> FilterTableView, compact: 16px fixed rows, 18px header, no grid/alternating/row
> numbers, white background, zero-padding items, autofit columns then stretch the
> name column. Auto-size panel width to fit all columns.

### Learnings — FilterTableView QObject lifetime

Header/scrollbar signals that call back into `FilterTableView` must use
QObject-bound `@pyqtSlot` handlers, not self-capturing lambdas such as
`lambda *_args: self.group_bar.update()`. Those closures created cycles that
could invoke callbacks during native/cyclic-GC teardown, causing Windows access
violations when repeatedly creating and destroying result grids. Keep optional
hidden widgets parented, and test both native destruction and Python-wrapper
collection rather than retaining leaked widgets or disabling GC.
Regression: `tests/test_audit_other_queries_ui.py`.

## StyledInfoTableGroup — Default UI Container

**Location:** `suiteview/polview/ui/widgets.py`

`StyledInfoTableGroup` is the **standard widget** for displaying **field/value
pairs**, **table data**, or **both** across all sub-apps. Unless you are
explicitly told to use a different approach, **always use this class** instead
of building raw `QTableWidget`, `QGroupBox` + `QGridLayout`, or other ad-hoc
containers.

> **FilterTableView vs StyledInfoTableGroup:** use `FilterTableView` for a
> filterable/sortable model-backed *data grid*; use `StyledInfoTableGroup` for
> label/value info panels (and small tables) with the PolView styling, copy, and
> autofit built in. They're complementary, not competing.

### Why

- **Consistent look** — rounded corners, styled blue/gold headers, compact
  row spacing, and themed scrollbars that match the PolView design.
- **Built-in features** — right-click copy on all values and cells,
  auto-fit columns, optional Excel-style column filtering.
- **Less code** — replaces 30-40 lines of manual styling with 3-4 lines.

### Usage modes

```python
from suiteview.polview.ui.widgets import StyledInfoTableGroup

# Info fields only (label/value pairs)
info = StyledInfoTableGroup("Policy Info", columns=3, show_table=False)
info.add_field("Policy", "policy_val", 80, 80)
info.set_value("policy_val", "U0532652")

# Table only
table = StyledInfoTableGroup("Premium Schedule", show_info=False)
table.table.setColumnCount(3)
table.table.setHorizontalHeaderLabels(["Year", "Age", "Annual Premium"])
# ... populate with table.table.setItem(row, col, QTableWidgetItem(...))
table.table.autoFitAllColumns()

# Both info fields and table
hybrid = StyledInfoTableGroup("TAMRA Values", columns=1)
hybrid.add_field("7 Pay Prem", "seven_pay", 100, 80)
hybrid.setup_table(["Year", "Premium", "Withdrawal"])
```

### Rules for AI assistants

1. **Default to `StyledInfoTableGroup`** for any new container that displays
   field/value pairs or tabular data — in **any** sub-app (PolView, ABR Quote,
   Audit, TaskTracker, etc.).
2. **Do not use raw `QTableWidget`** with manual header/row styling.
3. **Do not build custom `QGroupBox` + `QGridLayout`** containers for
   label/value pairs — use `add_field()` instead.
4. Only deviate from this convention if the user **explicitly** requests a
   different approach for a specific case.

## Custom Window Frame — FramelessWindowBase

All SuiteView windows use a **frameless custom window frame** — no native OS
title bar. Every top-level window subclasses `FramelessWindowBase`
(`suiteview/ui/widgets/frameless_window.py`).

### The Look
- **Frameless** — `Qt.FramelessWindowHint`. No native chrome.
- **Header bar** — fixed 38px tall with a diagonal 3-stop linear gradient (dark
  left → darker right). Title text is white, bold italic, 18px.
- **Gold border** — 2px painted border around the entire window (default `#D4A017`).
- **Control buttons** — minimize (`–`), maximize/restore (`□`/`❏`), close (`✕`)
  as Unicode glyphs in the header. Text color matches the border color. Close
  button goes red on hover.

### Behavior
- Drag-to-move on the header bar. Double-click header to maximize/restore.
- 8-edge resize handles. Snap-to-edge (left/right half-screen) with translucent
  preview.
- De-maximize on drag — dragging from maximized restores to normal size.

### Resizing — Native (DWM), NOT manual `setGeometry` (MANDATORY)
**On Windows, resizing is handed to the OS via native hit-testing — never a
per-mouse-move `setGeometry` loop.** Resizing a frameless window by calling
`setGeometry()` on every `mouseMoveEvent` bypasses DWM's GPU-composited resize,
so the content lags the frame → **glitchy "repeating artifacts at the bottom"
and non-smooth resizing.** This has regressed before; keep the native path.

How it works (`FramelessWindowBase._install_native_frame` + `nativeEvent`):
- On first `showEvent` we add a native sizing frame (`WS_THICKFRAME | WS_CAPTION`
  …) via `SetWindowLongPtr`, then reclaim the whole client area by handling
  `WM_NCCALCSIZE` (so the native title bar/borders are invisible — our gradient
  header + gold border remain).
- `WM_NCHITTEST` returns `HT*` edge codes near the borders so **Windows/DWM does
  the resize** — smooth and artifact-free. `WM_GETMINMAXINFO` clamps maximize to
  the monitor work area (respects the taskbar / mini-bar).
- When native resize is active (`self._native_resize`), the manual `_ResizeEdge`
  overlay widgets + `QSizeGrip` resizer are **not** created and the mouse-resize
  branches are skipped, so there's no double-handling. The manual path only runs
  as a non-Windows fallback.

Pitfalls (do not reintroduce):
- **Declare `argtypes`/`restype`** for every `ctypes.windll.user32` call —
  otherwise 64-bit handles truncate → `STATUS_STACK_BUFFER_OVERRUN` crash.
- In `nativeEvent`, **never call `super().nativeEvent(...)`** — it crashes under
  PyQt6. Return `(False, 0)` for unhandled messages; `(True, result)` when handled.
- Don't call `raise_()` on child widgets inside `resizeEvent` (z-order/repaint
  storm) — raise grips once at creation.
- **Don't clamp the maximized client rect while the window is iconic.** The
  `WM_NCCALCSIZE` handler must check `is_iconic()` before overwriting `rgrc[0]`
  with the monitor work area.

### Minimize / restore — go through the OS, not `showMinimized()` (MANDATORY)

`QWidget.showMinimized()` opens with `if (isMinimized() && isVisible()) return;`
and afterwards only talks to the OS when *Qt* believes the state changed. Our
frameless windows make that cached state easy to desync — they carry a native
sizing frame, swallow `WM_NCCALCSIZE`, get hidden/re-shown instead of closed,
and are restored by raw Win32 calls from the taskbar. When Qt and Windows
disagree, **clicking minimize silently does nothing and a maximized window just
keeps filling the screen.**

- The fix lives in
  [`suiteview/ui/widgets/window_state.py`](suiteview/ui/widgets/window_state.py)
  → `NativeMinimizeMixin`, which drives `ShowWindow(SW_MINIMIZE)` (falling back
  to `WM_SYSCOMMAND`/`SC_MINIMIZE`, then to Qt) and verifies with `IsIconic`.
- **Any new frameless top-level window must mix it in**:
  `class MyWindow(NativeMinimizeMixin, QWidget)`. `FramelessWindowBase` already
  does, as do Screen Shot Manager, Email Attachments and FileNav.
- **Never restore with `showNormal()`** — it throws away a maximized/snapped
  layout and desyncs the cached flags, so the maximize button then appears
  dead. Call `restore_window()`, which returns the window to its pre-minimize
  state. `SuiteViewTaskbar._bring_to_front()` uses it when available.
- `FramelessWindowBase.changeEvent` re-syncs `_is_maximized`/`_is_snapped` and
  the max-button glyph from the real window state, so OS-driven maximize
  (Win+Up, Aero snap) can't leave the header button lying.
- **Regression check:**
  `venv\Scripts\python.exe tools/app/test_window_minimize.py` must report
  `all_ok: true`.

### Theme
Each module can override `header_colors` (3-stop gradient) and `border_color` to
brand its windows:

| Module | Header Gradient | Border |
|---|---|---|
| Default / Audit / RateManager | Blue `#1E5BA8 → #0D3A7A → #082B5C` | Gold `#D4A017` |
| PolView | Green `#0A3D0A → #1B5E20 → #2E7D32` | Gold `#D4A017` |
| ABR Quote | Crimson `#5C0A14 → #8B1A2A → #A52535` | Slate `#4A6FA5` |

### Pattern
Subclass `FramelessWindowBase`, override `build_content() → QWidget` to provide
the body. Pass `title`, `default_size`, `header_colors`, `border_color`, and
optional `header_widgets` (extra widgets placed in the title bar).

### Window Footer — Size Display
All windows built on `FramelessWindowBase` **must** display the current window
dimensions (`W × H`) in the bottom-right corner of the footer area. This is
implemented in the base class itself, so every sub-app window (PolView, ABR Quote,
Audit, TaskTracker, RateManager, etc.) gets it automatically. No sub-app code is
needed — just inherit from `FramelessWindowBase`.

- The label updates live on every resize.
- It uses a semi-transparent style so it doesn't distract from the main content
  but is always visible for layout/debugging reference.

### ScratchPad
**Location:** `suiteview/scratchpad/scratchpad_panel.py`

Every `FramelessWindowBase` window includes a **ScratchPad** button (📝) in the
header bar. Clicking it opens a persistent text area for notes.

- **Timestamp button** — inserts a timestamped header (e.g., `[2026-02-19 14:30]`)
  followed by a newline and 4-space indentation.
- **Auto-indent** — pressing Enter auto-indents the new line with 4 spaces
  (except timestamp lines).
- Notes persist per-window instance during the session.

## MiniExplorer — Reusable File Browser Widget

**Location:** `suiteview/ui/widgets/mini_explorer.py`

`MiniExplorer` is a **generic, reusable file browser** widget used in both
PolView's Policy Support tab and ABR Quote's Output panel.

### Key classes

| Class | Purpose |
|-------|---------|
| `MiniExplorer` | Main widget — nav buttons (Home/Up), path label, file list |
| `DraggableToolsList` | `QListWidget` subclass that supports **drag** operations |
| `DropTargetSubfolderList` | `QListWidget` subclass that accepts **drop** operations |
| `DoubleClickablePathLabel` | `QLabel` that opens the displayed path in Explorer on double-click |

### Usage

```python
from suiteview.ui.widgets.mini_explorer import (
    MiniExplorer, DraggableToolsList, DropTargetSubfolderList
)

# Drag source
tools = MiniExplorer(
    title="Available Tools",
    list_widget_class=DraggableToolsList,
    root_path=r"C:\path\to\tools"
)

# Drop target
subfolders = MiniExplorer(
    title="Policy Subfolders",
    list_widget_class=DropTargetSubfolderList,
    root_path=r"C:\path\to\policy\folder"
)

# Access the internal list widget
subfolders.list_widget.file_dropped.connect(on_file_dropped)
```

### Styling override
MiniExplorer ships with PolView's green/gold default style. To match ABR Quote's
Crimson Slate theme, call `_apply_abr_style(explorer)` which overrides the
group box, nav buttons, path label, and list widget stylesheets.

## Compact Mini-Bar

SuiteView can dock as a **compact mini-bar** at the bottom of the screen,
overlapping the Windows taskbar region. Desktop space is reserved by
registering the bar as a shell **AppBar** (`SHAppBarMessage`) — the same
mechanism the Windows taskbar uses — not the fragile `SPI_SETWORKAREA`.

- Contains a policy number input field and company combobox.
- No timer-based solutions — uses OS-level window management.
- Maximized windows respect the reserved space and don't cover the bar.

### AppBar docking rules (MANDATORY)

The system-tray context menu contains only **Quit SuiteView**. Single- and
double-clicking the tray icon still restore the launcher; app shortcuts remain
in the launcher, not the tray menu. Regression: `tests/test_taskbar_tray_menu.py`.

**Quit** first closes the other visible windows. If one stays open (e.g. a busy
or unsaved-change guard), the quit is cancelled with the tray icon and launcher
intact and that window brought forward. Only then does it hide the tray and call
`QApplication.exit(0)` — never `QApplication.quit()`, which Qt 6 cancels when a
window rejects its close event, leaving an invisible process that holds the
single-instance mutex so the SuiteView shortcut silently does nothing.
Regression: `tests/test_taskbar_quit.py`.

The Win32 dance lives in
[`suiteview/taskbar_launcher/appbar.py`](suiteview/taskbar_launcher/appbar.py).
Never re-declare `APPBARDATA` / `SHAppBarMessage` calls elsewhere.

- **Always `ABM_REMOVE` before `ABM_NEW`.** `ABM_NEW` returns *false* for an
  HWND the shell already knows, and the failure is silent — the work area is
  simply never reserved. `register_bottom()` does the remove for you.
- **Verify the reservation.** `SHAppBarMessage` can report success while
  leaving the work area untouched, so `_register_appbar()` reads the monitor
  work area back via `appbar.space_reserved()` and retries once with a clean
  remove/add before giving up.
- **Reserve space only while the bar is on screen.** `_hidden_to_tray` gates
  registration: hiding to the tray releases the reservation
  (`_unregister_appbar(force=True)`) and showing from the tray re-docks via
  `_redock_appbar()`. A screen/work-area change arriving while hidden must not
  re-register a bar nobody can see.
- **Shortcut activation must use the Qt restore path.** Both launchers share
  `taskbar_launcher/single_instance.py`: a second process posts the registered
  restore message to the existing launcher, rather than calling `ShowWindow`
  alone. `SuiteViewTaskbar.nativeEvent` queues `_show_from_tray`, also reconciling
  native show/restore requests while hidden. This clears the tray state and
  re-docks after Qt maps the window. Never kill other Python processes when a
  mutex exists but the launcher window is not ready.
- **Failed verification is not success.** AppBar Win32 declarations are
  pointer-safe and private (do not overwrite other widgets' ctypes structure
  prototypes). Missing monitor information or a failed reservation triggers
  one retry, then a tray warning rather than claiming the bar is docked.
- **Regression check:**
  `venv\Scripts\python.exe tools/app/test_taskbar_tray_cycle.py` drives the real
  taskbar through launch → hide → refresh-while-hidden → show → redundant
  register, native restore, cross-process shortcut activation, and floating/full
  restores. It checks Qt/native visibility and the exact reserved height.
  It must report `all_ok: true` and exit zero; `--output <path>` saves the JSON.
  `tests/test_taskbar_restore.py` covers activation identities and failure paths.

## Identifier Inputs — Case-Insensitive Entry (MANDATORY)

Policy numbers, region codes and company codes are stored **upper-case** in DB2,
so a lower-case entry must never be the difference between a hit and a silent
"policy not found". Every field a user types an identifier into upper-cases the
text *in the field itself* — what the user sees is exactly what gets queried.

```python
from suiteview.ui.widgets.uppercase_input import force_uppercase

force_uppercase(self.region_input, self.company_input, self.policy_input)
```

- `force_uppercase()` installs an `UpperCaseValidator`, so typing, pasting and
  `setText()` (cross-app hand-offs) are all folded.
- **Read sites still `.strip().upper()`** — belt and braces, because the failure
  mode is silent.
- **Applied to:** the PolView `PolicyLookupBar` (shared with RERUN and the Audit
  hand-off), ABR Quote's `PolicyPanel`, the PolView/RERUN policy-list panels,
  the compact taskbar bar, Mainframe Nav, and the Audit Policy tab's
  policy-number criterion.
- **Regression check:**
  `venv\Scripts\python.exe tools/app/test_policy_input_uppercase.py` must report
  `all_ok: true`.

## Not-Applicable Sections — UI Preference (MANDATORY)

When a section of a UI tab **does not apply** to the current product/data type:

- ✅ **Keep sections visible** — never call `setVisible(False)` to hide them
- ✅ **Grey out the section** with `GRAY_LIGHT` background and muted borders
- ✅ **Show a centered italic note**: *"Not applicable for product type"*
- ❌ **Never leave the background white** when a section is inactive
- ❌ **Never remove the widget** from the layout

Use the `_NotApplicableOverlay` pattern (see `targets_tab.py` for the reference
implementation) — a transparent `QWidget` overlay with a centered label that is
parented and sized to cover the target widget exactly. Call
`widget.set_not_applicable(True/False)` to toggle the state.

## Excel Export — "Dump to Excel" Convention

**Decision:** All "Excel" / "Export" buttons in SuiteView open a **new unsaved
workbook** in a visible Excel instance via COM automation
(`win32com.client.dynamic`). They do **not** save a file to disk.

**Rationale:** The common use case is quick visual inspection of data in Excel and
then discarding it. Forcing a Save-As dialog adds friction. The user can save the
workbook themselves if they want to keep it.

**Shared helper:** the fragile win32com lifecycle is owned by
`suiteview/core/excel_export.py` (dynamic dispatch, screen-updating, bulk write,
bold/freeze/autofilter/autofit, error handling). Prefer the shared helper over
re-implementing the COM dance; each call site keeps only its own data extraction.

### Key principles

1. **No save dialog** — do NOT prompt the user to pick a file path.
2. **No temp files** — do NOT write to disk; the workbook lives only in memory
   until the user explicitly saves it.
3. **Bulk writes** — build all data as a list of tuples, then write the entire
   block in one `Range.Value = data` call per sheet. Never write cell-by-cell.
4. **Formatted headers** — bold, white text on a dark fill, centered.
5. **Freeze panes** — freeze the header row so it stays visible while scrolling.
6. **Auto-filter** — add auto-filters to the data range.
7. **Auto-fit columns** — call `ws.Columns.AutoFit()` after writing data.
8. **ScreenUpdating** — set `excel.ScreenUpdating = False` before writing, then
   `True` when done, so the workbook appears fully rendered.
9. Convert non-primitive types (datetime, Decimal, etc.) to `str` before writing
   to avoid COM type errors. Set `ws.Name` to something meaningful (max 31 chars).

### Reference implementation

```python
def _on_export(self):
    """Export data to a new unsaved Excel workbook via COM."""
    try:
        from win32com.client import dynamic

        excel = dynamic.Dispatch("Excel.Application")
        excel.Visible = True
        excel.ScreenUpdating = False

        wb = excel.Workbooks.Add()
        ws = wb.ActiveSheet
        ws.Name = "My Data"

        headers = ("Col A", "Col B", "Col C")
        col_count = len(headers)

        # Build all rows as tuples for bulk write
        all_data = [headers]
        for row in self._rows:
            all_data.append((row["a"], row["b"], row["c"]))

        total_rows = len(all_data)
        rng = ws.Range(ws.Cells(1, 1), ws.Cells(total_rows, col_count))
        rng.Value = all_data

        # Format header row
        hdr = ws.Range(ws.Cells(1, 1), ws.Cells(1, col_count))
        hdr.Font.Bold = True
        hdr.Font.Color = 0xFFFFFF
        hdr.Interior.Color = 0x404D00   # Teal dark (BGR for #004D40)
        hdr.HorizontalAlignment = -4108  # xlCenter

        # Number formats (apply to ranges, not individual cells)
        # ws.Range(ws.Cells(2, 2), ws.Cells(total_rows, 2)).NumberFormat = "0.00"

        # Freeze top row + auto-filter + auto-fit
        ws.Range("A2").Select()
        excel.ActiveWindow.FreezePanes = True
        if total_rows > 1:
            ws.Range(ws.Cells(1, 1), ws.Cells(total_rows, col_count)).AutoFilter()
        ws.Columns.AutoFit()

        ws.Range("A1").Select()
        excel.ScreenUpdating = True

    except ImportError:
        QMessageBox.warning(self, "Error",
                            "win32com is not available. Cannot export to Excel.")
    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        QMessageBox.warning(self, "Export Error", f"Could not export:\n{e}")
```

### Rules for AI assistants

1. **Always use this pattern** for any new "Export to Excel" feature; prefer the
   `suiteview/core/excel_export.py` helper.
2. **Never use openpyxl + file save** for interactive exports; openpyxl is only
   appropriate for batch/headless file generation.
3. **Use `dynamic.Dispatch`** (not `gencache.EnsureDispatch`) to avoid gen_py
   cache corruption issues.
4. **Apply number formats to ranges**, not individual cells.
5. **Colors are BGR** in COM — `0x404D00` is `#004D40` (teal dark).
6. **Handle ImportError** gracefully with a user-facing message box.

### Existing implementations

| Location | Description |
|----------|-------------|
| `suiteview/core/excel_export.py` | Shared COM-lifecycle helper (canonical) |
| `polview/ui/widgets.py` → `FixedHeaderTableWidget._dump_to_excel()` | Context-menu "Dump to Excel" on any PolView table |
| `abrquote/ui/calc_viewer.py` → `CalcViewerDialog._on_export()` | Calculation detail viewer (Mortality + APV sheets) |

---

# Part IV — Data & Domain Architecture

## Data Abstraction — Query Design / Query Definition / Data Snapshot

- **Query Design** — A reusable, parameterized template that defines the structure
  of a query (tables, joins, columns) while leaving specific filter values and
  inputs to be supplied at execution time.

- **Query Definition** — A fully-specified, executable query that captures the
  exact SQL, bound parameter values, target database, connection, and expected
  result schema (field names and types), produced by applying specific inputs to
  a Query Design.

- **Data Snapshot** — The materialized rows and columns of data returned by
  executing a Query Definition at a specific point in time.

## ⚠️ PolicyInformation — THE Central Data Layer

**Location:** `suiteview/polview/models/policy_information.py`
**Shared service:** `suiteview/core/policy_service.py`

`PolicyInformation` is the **single most important class in SuiteView**.
Every application that needs policy data — PolView, ABR Quote, Audit, and
every future tool — **must** access that data through this class. It is the
canonical, authoritative interface to DB2 policy records.

### Why this matters

- **One source of truth.** All DB2 queries for policy-level data live inside
  `PolicyInformation`. No app should write its own raw SQL against
  `LH_BAS_POL`, `LH_COV_PHA`, etc.
- **Constantly evolving.** New properties are added regularly as we expose
  more policy data to feed more apps. When you need a field that doesn't
  exist yet, **add a property to PolicyInformation** — do not work around it
  with one-off queries elsewhere.
- **Cached & shared.** The `policy_service.py` wrapper caches instances by
  `(policy_number, region)` so multiple widgets displaying the same policy
  never hit DB2 twice.

### How to use it (any app)

```python
from suiteview.core.policy_service import get_policy_info

pi = get_policy_info("E0213651", region="CKPR")
if pi:
    name  = pi.primary_insured_name
    face  = pi.base_face_amount
    age   = pi.attained_age
    plan  = pi.base_plancode
    # ... hundreds of properties available
```

### Key property groups

| Category | Examples |
|----------|----------|
| Identifiers | `policy_number`, `policy_id`, `company_code`, `company_name` |
| Status | `status_code`, `status_description`, `is_active`, `is_terminated` |
| Dates | `issue_date`, `paid_to_date`, `next_anniversary_date` |
| Duration | `policy_year`, `policy_month` |
| Billing | `billing_frequency`, `billing_mode`, `non_standard_mode_code`, `state_code` |
| Premiums | `modal_premium`, `annual_premium`, `regular_premium`, `total_premiums_paid` |
| Base coverage | `base_plancode`, `base_face_amount`, `base_issue_age`, `base_sex_code`, `base_rate_class`, `attained_age`, `age_at_maturity` |
| Substandard | `get_substandard_ratings(cov)`, `cov_table_rating(cov)`, `cov_flat_extra(cov)`, `cov_flat_cease_date(cov)` |
| Coverages | `coverage_count`, `get_coverages()` → `List[CoverageInfo]` |
| Benefits | `benefit_count`, `get_benefits()` → `List[BenefitInfo]` |
| Persons | `primary_insured_name`, `is_joint_insured` |
| Agents | `writing_agent`, `writing_agent_name`, `servicing_agent_number` |
| Loans | `total_loan_balance`, `total_loan_principal`, `total_loan_interest` |
| Values | `cash_surrender_value`, `accumulation_value`, `death_benefit`, `net_amount_at_risk` |
| Product type | `is_advanced_product`, `product_type`, `product_line_code` |

### Data access API (for raw table/field lookups)

| Method | Purpose |
|--------|---------|
| `data_item(table, field, index=0)` | Single value from any DB2 table/field/row |
| `data_item_array(table, field)` | All values for a field across rows |
| `data_item_count(table)` | Row count for a table |
| `fetch_table(table)` | Entire table as `List[Dict]` |
| `cached_table(table)` | `(columns, rows)` already loaded, or `None`; never queries DB2 (safe on the GUI thread) |
| `data_item_where(table, return_field, filter_field, filter_value)` | Filtered single value |
| `data_items_where(table, return_field, filter_field, filter_value)` | All matching values |

`PolicyData.data_item()` returns `None` for a missing row, but a loaded table
that lacks the requested column now raises
`suiteview.core.data_access.errors.UnknownColumnError`. Optional scalar columns
must be declared in `suiteview.polview.models.policy_fields.FIELD_SPECS`; update
that registry and regenerate `docs/polview/POLICY_FIELDS.md` rather than relying
on silent blanks.

### Rules for AI assistants

1. **Never use `pi.get_value()`** — that method does not exist. Use named
   properties directly (e.g. `pi.base_issue_age`).
2. **Never pass a DB2Connection to the constructor** — `PolicyInformation`
   manages its own connections internally. Constructor signature:
   `PolicyInformation(policy_number, company_code=None, system_code="I", region="CKPR")`
3. **Check existence with `pi.exists`**, not `pi.policy_found`.
4. **When a new property is needed**, add it to `PolicyInformation` with a
   `@property` decorator following the existing pattern — query via
   `self.data_item(table, field)`.
5. **Always go through `policy_service.get_policy_info()`** from app code so
   caching works.

## 🗄️ DB2 Database Configuration

All sub-apps share the same DB2 connectivity layer.

For the maintained DSN/region map, connection ownership, read/write boundaries,
local-data gate, error hierarchy and SQL identifier allowlist rule, see
[`docs/DATA_ACCESS.md`](docs/DATA_ACCESS.md).

### Local SQLite Data Is Opt-In Only

Generated local policy-record and rates SQLite files under `bundled_data/dev/`
exist only for deliberate offline development. They must **never** be used as a
fallback when live DB2/SQL-Server access fails or is unavailable.

- The only enabling switch is `SUITEVIEW_LOCAL_DATA=1` exactly.
- Values such as `true`, `yes`, `on`, `dev`, `local`, or a configured local DB
  path do **not** enable local data.
- `SUITEVIEW_LOCAL_POLICY_DB` and `SUITEVIEW_LOCAL_RATES_DB` may only choose the
  file path after `SUITEVIEW_LOCAL_DATA=1` has already enabled local mode.
- Policy data must still flow through `PolicyInformation` / `DB2Connection`;
  rates must still flow through `suiteview.core.rates.Rates`.
- If live data access fails while local mode is disabled, raise the live access
  error. Do not silently fall back to local SQLite.

### DSN Mappings (Regions)

| Region | DSN Name | System Code |
|--------|----------|-------------|
| CKPR (PROD) | NEON_DSN | I |
| CKMO (MODEL) | NEON_DSNM | M |
| CKAS (Acceptance) | NEON_DSNT | A |
| CKCS (Cybertek) | NEON_DSNT | C |
| CKSR (System Region) | NEON_DSNT | S |

### Schema Qualifiers by Region

CKAS, CKCS, and CKSR share the same DSN (`NEON_DSNT`) but use **different DB2 schemas**:

| Region | Schema Qualifier |
|--------|-----------------|
| CKPR | `DB2TAB.` (default) |
| CKMO | `DB2TAB.` (default) |
| CKAS | `UNIT.` |
| CKCS | `CYBERTEK.` |
| CKSR | `CKSR.` |

Schema replacement is handled automatically by `DB2Connection._add_with_clause()`
and `PolicyInformation._add_with_clause()` — callers always write `DB2TAB.<table>`
and the framework rewrites it to the correct schema.

### CRITICAL: TCH_POL_ID Lookup

**TCH_POL_ID is NOT the same as the policy number!**

When running standalone queries, you MUST first look up `TCH_POL_ID` from `LH_BAS_POL`:

```sql
-- TCH_POL_ID format: PolicyNumber + space + 4 random characters
-- Example: 'E0008145  QXXX' (not just 'E0008145')

-- Step 1: Get TCH_POL_ID from LH_BAS_POL using CK_POLICY_NBR
SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL
WHERE TCH_POL_ID LIKE '%E0008145%'

-- Step 2: Use the full TCH_POL_ID in subsequent queries
SELECT * FROM DB2TAB.LH_UNAPPLIED_PTP
WHERE TCH_POL_ID = 'E0008145  QXXX'
```

### DB2 Table Key Structure

All DB2 tables use a composite key:
```
CK_SYS_CD    = System Code ('I' for inforce, 'P' for pending — almost always 'I')
CK_CMP_CD    = Company Code ('01', '04', '06', '08', '26')
TCH_POL_ID   = Technical Policy ID (internal identifier)
COV_PHA_NBR  = Coverage Phase Number (1=base, >1=riders) — some tables only
```

### Key DB2 Tables

| Table | Purpose | Important Fields |
|-------|---------|------------------|
| `LH_BAS_POL` | Basic policy info | CK_POLICY_NBR, PRM_PAY_STA_REA_CD, PAID_TO_DT, NON_TRD_POL_IND |
| `TH_BAS_POL` | Advanced product info | AN_PRD_ID, TFDF_CD |
| `LH_COV_PHA` | Coverage phases | COV_PHA_NBR, PLN_DES_SER_CD, ANN_PRM_UNT_AMT, COV_UNT_QTY, COV_VPU_AMT |
| `LH_COV_INS_RNL_RT` | Renewal rates | RNL_RT, RT_CLS_CD, RT_SEX_CD, PRM_RT_TYP_CD |
| `TH_COV_PHA` | Additional coverage data | COLA_INCR_IND, OPT_EXER_IND, CV_AMT, NSP_AMT |
| `LH_SPM_BNF` | Supplemental benefits | SPM_BNF_TYP_CD, SPM_BNF_SBY_CD |
| `LH_SST_XTR_CRG` | Substandard/flat extras | SST_XTR_TYP_CD, SST_XTR_RT_TBL_CD, XTR_PER_1000_AMT, SST_XTR_CEA_DT |
| `LH_POL_TOTALS` | Accumulators | Premiums paid, withdrawals, cost basis |
| `LH_POL_TARGET` | Policy targets | TAR_TYP_CD: 'MT'=MTP, 'MA'=AccumMTP, 'CT'=CommTarget |
| `LH_POL_MVRY_VAL` | Monthly anniversary values (UL) | CSV_AMT, CINS_AMT |
| `LH_NON_TRD_POL` | Non-traditional policy data | GAV, grace rule |
| `FH_FIXED` | Financial history transactions | ASOF_DT, TRN_TYP_CD, TOT_TRS_AMT |
| `LH_AGT_COM_AMT` | Agent commissions | AGT_ID, COM_PCT |

> **Full table mappings** (Policy Record → DB2 tables) are documented in
> [`docs/POLVIEW_CLAUDE.md`](docs/POLVIEW_CLAUDE.md) and `config/policy_records.py`.

### ⚠️ DB2 Column Name Verification (CRITICAL)

**Never guess or interpolate DB2 column names.** CyberLife's naming conventions
are inconsistent — columns that *should* be named one way often aren't. For
example:

| You might guess | Actual column | Table |
|-----------------|---------------|-------|
| `FLT_XTR_AMT` | `XTR_PER_1000_AMT` | `LH_SST_XTR_CRG` |
| `TBL_RT_CD` | `SST_XTR_RT_TBL_CD` | `LH_SST_XTR_CRG` |
| `XTR_CEA_DT` | `SST_XTR_CEA_DT` | `LH_SST_XTR_CRG` |
| `XTR_DUR_NBR` | `SST_XTR_CEA_DUR` | `LH_SST_XTR_CRG` |

**The failure mode is silent** — `row.get("WRONG_NAME")` returns `None`,
the code runs without errors, and values simply appear as blank/zero in the UI.
You won't know it's broken unless you test with real data.

**Rules:**
1. When adding code that reads a DB2 column, **verify the column name**
   against the actual table schema (e.g., via `SELECT * FROM DB2TAB.table FETCH FIRST 1 ROW ONLY`).
2. If you cannot verify, add a `# TODO: verify column name` comment.
3. When debugging missing data, **always check column names first** —
   it's the most common cause of "data not showing up."

### Company Codes

`"01"` → ANICO, `"04"` → ANTEX, `"06"` → SLAICO, `"08"` → GSL, `"26"` → ANICO NY

### Error Handling

| Error | Description | Solution |
|-------|-------------|----------|
| `-2147467259` | Communication link failure | Refresh connection and retry |
| Automation Error | Office 365 WITH clause issue | Use `SQLStringForRegion()` to prepend WITH clause |
| Type Mismatch | Empty recordset | Check `IsEmpty()` / `None` before processing |

## 🏷️ Key Domain Concepts

These concepts apply across all sub-apps that work with policy data.

### Traditional vs Advanced Products

This is the **most important business logic distinction** in the system.
Nearly every financial field — rates, values, targets, loans — has different
source tables and calculation logic depending on product type.

| Aspect | Traditional (Trad) | Advanced (UL/IUL/VUL) |
|--------|-------------------|----------------------|
| Indicator | `NON_TRD_POL_IND` = `"0"` or blank | `NON_TRD_POL_IND` = `"1"` |
| Product line | `PRD_LIN_TYP_CD` = `"0"` | `"I"` (ISL), `"U"` (UL/VUL), etc. |
| Rate source | `LH_COV_PHA.ANN_PRM_UNT_AMT` | `LH_COV_INS_RNL_RT.RNL_RT` (type "C") |
| Values table | `TH_COV_PHA` (CV_AMT, NSP_AMT) | `LH_POL_MVRY_VAL` |
| Loan table | `LH_CSH_VAL_LOAN` | `LH_FND_VAL_LOAN` |

**Detection:**
```python
policy.is_advanced_product   # bool — from LH_BAS_POL.NON_TRD_POL_IND
policy.product_type          # "Traditional" or "Advanced"
cov.is_advanced_product      # bool — set on each CoverageInfo during construction
```

Implementation-specific branching belongs in `policy.product_rules`
(`TraditionalRules`, `AdvancedRules`, `WholeLifeRules`, `ISWLRules`, `DIRules`).
The strategy exposes value/loan table choices, display rate behavior,
valuation-date source, support eligibility and the rate family. See
`docs/polview/POLVIEW_REFACTOR_CONTRACTS.md`.

> **Deep dive** on rate fields, divisors, renewal rate table, and VBA
> equivalents: see [`docs/POLVIEW_CLAUDE.md`](docs/POLVIEW_CLAUDE.md)
> § "CoverageInfo Rate Fields"

### Translation Dictionaries

Implemented in `models/policy_translations.py` (ported from VBA `mdlDataItemSupport.bas`):

| Dictionary | Examples |
|-----------|----------|
| Status codes | `"0"→"Active"`, `"2"→"Suspended"`, `"3"→"Death Claim"` |
| Product lines | `"0"→"Traditional"`, `"I"→"Interest Sensitive Life"`, `"U"→"Universal/Variable UL"` |
| Sex codes | `"1"→"Male"`, `"2"→"Female"`, `"3"→"Unisex"` |
| Rate classes | `R→Pref+ NS`, `P→Pref NS`, `T→Std+ NS`, `N→NS`, `Q→Pref S`, `S→Smoker` |
| GP/CVAT (`TFDF_CD`) | `1→TEFRA GP`, `2→DEFRA GP`, `3→DEFRA CVAT`, `4→GP Selected`, `5→CVAT Selected` |

### Billing Mode Determination

Billing mode requires **two** DB2 fields from `LH_BAS_POL`:

| Field | Description |
|-------|-------------|
| `PMT_FQY_PER` | Standard payment frequency in months (1=Monthly, 3=Quarterly, 6=Semi-Annual, 12=Annual) |
| `NSD_MD_CD` | Non-standard mode code — overrides `PMT_FQY_PER` when set |

When `NSD_MD_CD` is non-empty, CyberLife forces `PMT_FQY_PER = 01` (monthly).
The actual billing cadence is indicated by the `NSD_MD_CD` code:

| NSD_MD_CD | Mode |
|-----------|------|
| `1` | Weekly |
| `2` | Bi-Weekly |
| `4` | 13thly (every 4 weeks) |
| `9` | 9thly |
| `A` | 10thly |
| `S` | Semi-Monthly |

**Important — Bi-Weekly and other non-standard modes:**
The premium in `LH_BAS_POL.POL_PRM_AMT` is still a **monthly** premium. Bi-weekly
(and other non-standard) payments are collected into a **Premium Depositor Fund (PDF)**,
and once a month money is moved from that fund to pay the monthly policy premium.
Therefore, for all ABR and other premium-based calculations, we treat the premium
as monthly and use the PAC Monthly modal factor (`0.0864`). The billing mode label
should reflect the actual cadence (e.g., "Bi-Weekly") and the modal premium display
should include "(monthly)" to clarify.

**Access:**
```python
pi = get_policy_info(policy_num)
pi.billing_frequency        # PMT_FQY_PER — months between payments
pi.non_standard_mode_code   # NSD_MD_CD — "" if standard, "2" if bi-weekly, etc.
pi.billing_mode             # Human-readable description (combines both fields)
```

---

# Part V — Sub-Apps

SuiteView is a multi-app platform. Each sub-app has its own detailed
documentation file. This `Agent.md` covers **cross-cutting concerns** shared
across all apps. For app-specific details, see the relevant doc:

| Sub-App | Doc File | Purpose |
|---------|----------|---------|
| **PolView** | [`docs/POLVIEW_CLAUDE.md`](docs/POLVIEW_CLAUDE.md) | Policy viewer — VBA reference, Trad vs Advanced deep dive, coverage/rate logic, VBA property mappings, Cyber Audit |
| **ABR Quote** | *(see section below)* | Accelerated Death Benefit quoting tool — 3-step wizard, dedicated SQLite DB, Crimson Slate theme |
| **RateManager** | *(module docstrings in `suiteview/ratemanager/`)* | Opens on a **product-line chooser** (`product_chooser.py`): UL, Term or Whole Life rates. The header then shows Workup / Database (/ Converters, UL only) for the chosen line, plus a control to switch back.<br><br>**UL** — single-pass multi-file load of one plancode into UL_Rates-ready CSVs (POINT_PVSRB, RATE_COI, RATE_TRGPREM, RATE_SCR, RATE_EPU, POINT_BENEFIT, RATE_BENCOI, RATE_BENTRG). Generated headers use exact physical UL_Rates names such as `Index(COI)` and `Rate(MTP)`. Base Index is required with no default. Every benefit requires a cease age and emits charges only through the preceding attained age. Sparse MPF benefit rates fill forward through omitted ages. Output codes: sex 1→M/2→F (unisex unchanged), band letters→1,2,3… (X,Y first). Rate files load as two independent **groups** keyed by their pointer file — the base group (POINT_PVSRB + RATE_COI/TRGPREM/SCR/EPU) and the benefit group (POINT_BENEFIT + RATE_BENCOI/BENTRG). Either group can stand alone: `WorkupPackage.load` participates a group only when its pointer CSV is present (all files in a present group are still required). Verify against the `1U1F4M00_DB` reference CSVs (work-laptop archive `..\SuiteViewP_archived_docs`) via `tools/rates/run_rate_workup.py` + `tools/rates/compare_workup_to_reference.py`.<br><br>**Term** (`workup/term_spec.py`, `term_builder.py`, `term_window.py`) — one IAF in, seven TERM_* CSVs out (TERM_POINT_PV, TERM_POINT_PVSRB, TERM_POINT_BENEFIT, TERM_RATE_MODEFACT, TERM_RATE_BANDSPECS, TERM_RATE_PREM, TERM_RATE_BEN). No MPF/CKULTB04/CKULTB01. See **§ Term Rates** below.<br><br>The UL/Term **Database** view (parameterized by `RateSchema`) validates all CSV schemas, compares complete index groups, blocks cross-plancode collisions, requires explicit per-table replacement, backs up removed rows, commits selected changes atomically, and supports pointer editing plus unreferenced whole-index deletion.<br><br>**Whole Life** has source-keyed CVF/PUI/IAF imports, explicit-basis NSP CSV imports, integrated dividend loading and read-only PDF/rate browsing. See **§ Whole Life rate loading** below. |
| **Task Manager** | *(future)* | Task management |
| **Administrator** | `suiteview/administrator/` | Users / Roles & Apps maintenance of the three `SV_Access*` tables in UL_Rates. Packaged builds require enabled ADMIN access; source developer runs bypass access-table restrictions. See Testing below. |
| **Cyberlife Query / Audit** | [`docs/audit/Audit_Criteria_Input_Types.md`](docs/audit/Audit_Criteria_Input_Types.md) | **52 Segment** page: eleven application/conversion fields from `TH_USER_GENERIC`, with ranges/text criteria and optional display. **Latest SC conversion dates (69)**: `LST_ETR_CD='O'`, both reversal flags zero, one `FH_FIXED` row ordered by `ENTRY_DT`, `ENTRY_TIME`, `SEQ_NO` descending. Live-verified: financial history has no `CK_SYS_CD`, and its time field is `ENTRY_TIME` (not the older workbook's `TIME`). |

> **To add a new sub-app doc:** create `docs/<APPNAME>_CLAUDE.md`, add a row to
> the table above, keep shared concerns (DB2, PolicyInformation) in this file,
> and keep app-specific detail (UI, VBA mappings, business rules) in the sub-app
> doc.

## Query conversion source company

Query's **Converted policy info (52)** display and **Has converted policy (52)**
criterion each include the live-verified `TH_USER_GENERIC.SOURCE_CMP_CODE`
as `SOURCE_CMP_CODE` in results, once when both are checked. Existing display
and filtering semantics are unchanged. Regression:
`tests/test_audit_segment52.py`; read-only live verification:
`tools/audit/verify_conversion_segments.py --verify-live`.

**Show post conversion policy (link)** on Display reverses destination 52
records into `POST_CONV_POLICY` / `POST_CONV_COMPANY`. Match the original's
system, company and `CK_POLICY_NBR` to the destination record's system,
`SOURCE_CMP_CODE` and `EXCH_POL_NUMBER`; resolve the destination's number
through its full-key `LH_BAS_POL` join. Gate `LST_ETR_CD = 'O'` in the outer
left join, never WHERE, so non-`O` and unmatched policies stay visible with
blanks. Preserve distinct multiple destinations and cross-company conversions;
do not pick an arbitrary latest policy or traverse a chain. No lookup when
unchecked. See the Audit criteria doc; regression:
`tests/test_audit_segment52.py`; read-only live result check:
`tools/audit/verify_post_conversion_link.py`.

## Query SQL Assist source toggle

SQL Assist's source label is an **ODBC / Files** toggle button. ODBC lists
saved connections and system/user DSNs; Files lists saved File Sources
(`file:<id>` tokens) with their stored member tables and schema, no ODBC.
**Manual SQL** (single-source picker): choosing a file makes the SQL run
through DuckDB via the existing `file:` routing; +Table is disabled in Files
mode; `FieldPickerPanel.show_file_source()` is its single entry for file-backed
SQL. **Visual Query** uses `FieldPickerPanel(multi_source=True)`: the toggle
only chooses what **+Table** browses (database tables, or file datasets via
`dialogs/add_file_tables_dialog.py`), and the Tables list always shows every
query table — database tables, then file datasets (file icon). Changing the
ODBC DSN drops the old DSN's tables but keeps file datasets. Toggling with no
file sources shows a placeholder and leaves the active query's source intact.
Regression: `tests/test_dynamic_query.py`, `tests/test_visual_query_joins_ui.py`;
native no-DB check: `tools/app/verify_sql_assist_source_toggle.py --screenshot <dir>`.

## Query Visual Query joins and mixed sources

One Visual Query may join **database tables with File Source datasets**.
`DynamicQuery.table_sources` maps file tables to `file:<id>`; every other
table belongs to the query DSN (`source_for()`); `query_sources.py` owns the
token helpers. Persisted as config `table_sources`; the published Query Object
records each table's own source. Same-named tables from two sources are refused.

The Joins tab (`tabs/visual_joins_tab.py` over `dataforge/join_canvas_view.py`)
shows only tables placed on it: drag tables (or fields) from SQL Assist or
double-click a table there, use
right-click **Add Table** (SQL Assist tables plus **Browse database tables… /
Browse file datasets…**), or place a field on Filter/Display (its table is
added automatically). File boxes carry a format badge (CSV, EXCEL…). Drag a
field onto a field to join; key fields are bolded with a dot; **click a line or
its INNER/LEFT/RIGHT/FULL pill** for Access-style join types and delete. Append
Tables stay DataForge-only (not offered in Visual Query). Missing/unconnected
joins are explicit errors that open the Joins tab.

`build_join_sql` orders joins outward from the FROM table
(`order_join_infos`); a join drawn toward the in-scope table flips LEFT/RIGHT
so the preserved side is the one the user chose. Cycles become extra ON
conditions. The FROM table comes from the join graph (a table never on an outer
join's optional side), not field order. A table on an optional side that is
also Inner-joined onward (`A LEFT B`, `B INNER C`) has no single meaning and is
refused with an explanation (`find_outer_join_ambiguity`); accepted suggestions
extend such chains with a Left join instead. `split_field_key` uses the longest
known table prefix — file column names may contain dots (`SLR Output[Source.Name]`).

Mixed or file-only designs run federated (`federated_query.py`): file tables
load; each database table is staged by its own read-only SELECT with its
filters pushed down and, only where rows removed could never reach the result
(INNER, or null-supplying side of LEFT/RIGHT), `KEY IN (...)` from a staged
neighbour's keys, chunked by 1,000; then the same design compiles to DuckDB.
Database filters become `IS NOT NULL` in DuckDB (exactly equivalent; keeps WHERE
semantics). Cross-source keys compare through hidden `__svk…` helper columns
(dropped from results; the user's columns are never rewritten): numerically when
either side is a database numeric column, else as trimmed text; file keys are
re-read as text so identifiers keep leading zeros. A database table with no filter and no safe
restriction asks before downloading it whole. The SQL tab shows the staging
plan as comments; edited Build SQL is refused for mixed-source queries.
Regression: `tests/test_visual_query_federated.py`,
`tests/test_visual_query_joins_ui.py`; native no-DB end-to-end check (real CSV
reader + DuckDB, stand-in DB2 fetch): `tools/app/verify_visual_query_joins.py
--screenshot <dir>`. Live DB2 verification is tracked in WORK_LAPTOP_SPEC.md.

**Paste List** (Joins toolbar, Add Table menu, or Ctrl+V on the canvas) turns
rows copied from Excel into an in-query table (`list:<name>` in `table_sources`;
its data in config `inline_tables`). The dialog only shows the pasted data: columns
are `C1`, `C2` … (or the pasted header names); a column that is clearly a policy
number or company code (header alias, or policy-shaped values) is named
`PolicyNumber`/`CompanyCode` and normalized (trim/upper; one-digit companies regain
the leading zero). Nothing else is assumed — no system code, no automatic join, no
de-duplication; use Suggest Joins. Double-click a heading to rename a column.
Double-click the list's canvas box (or right-click › Edit Pasted List) to reopen it
and rename columns (joins follow; columns on Display/Filter are locked). Deleting
the box (right-click › Delete Table, or select + Delete) removes the list from the
query. `policy_list.py` owns parsing; `add_policy_list` remains for programmatic
lists left-joined to `DB2TAB.LH_BAS_POL`. Pasted lists run federated like file
datasets.

**Table View**: right-click a table in SQL Assist or a box on the canvas ›
**Open Table View…** opens a separate window (`tables_dialog.open_table_view`) with
the first 1000 rows; change **Rows** and Reload. Works for database tables, file
datasets and pasted lists.

**Join suggestions** (`join_suggestions.py`): each canvas table not yet joined
gets one best partner, drawn as dashed gold `+ JOIN?` lines with a banner
(Accept / Dismiss; **Suggest Joins** looks again). CyberLife pairs get the full
`CK_SYS_CD`+`CK_CMP_CD`+`TCH_POL_ID` key (+`COV_PHA_NBR` when both have it);
lists/files match policy/company/system names (bracketed file names use the
inner name); otherwise identical key-like names. A company or system match
alone is never suggested. Dismissals persist with the query.

**Plan badges**: for designs with files/lists, a strip under each database box
says how it will be fetched — `✓ Only rows matching <table>` (key pushdown),
`✓ Narrowed by its filters`, or `⚠ Downloads the whole table`; unused boxes say
so; lists show their row count (details in the tooltip). Pushdown prefers
identifier keys over broad codes (company/system/phase).
Column loaders are unparented and kept alive until finished: closing a query
while a loader waits on ODBC must not destroy a running `QThread` (abort 0xC0000409).
Regression: `tests/test_visual_query_policy_list.py`; native check using the real
clipboard: `tools/app/verify_policy_list_paste.py --screenshot <dir>`.

## Query tool RegEx reference

The header's **RegEx Cheatsheet** button opens a compact, non-modal blue/gold
reference with expressions, character classes and useful patterns. It reuses
one owned window for users with Query access. This is regular-expression
syntax, not SQL LIKE; the existing field-row SQL LIKE help remains separate.
Regression: `tests/test_audit_regex_cheatsheet.py` (use `QT_QPA_PLATFORM=windows`
to also check text fit with native fonts).

## Query ADV specified-amount comparisons

ADV's **Current SA < Original SA** and **Current SA > Original SA** emit strict
`<` and `>` comparisons of `COVSUMMARY.TOTAL_SA` with `TOTAL_ORIGINAL_SA`.
Equal amounts are excluded; the independent checkboxes retain AND semantics
if both are selected. Saved-state keys and coverage-summary scope are unchanged.
Regression: `tests/test_audit_adv_glp_gsp_ranges.py` checks generated operators,
switching selections, saved-state restore, and less/equal/greater/NULL outcomes.

## Query change sequence (68)

Policy (2)'s **Has Change Seq (68)** unions four source tables. Live
`LH_COV_TMN` has no `CHG_TYP_CD`: termination rows contribute literal
`'9' AS CHG_TYP_CD`. The other three change/schedule tables retain their
stored codes. Never select a nonexistent change-type column from termination
detail; the Rocket DV driver can obscure that SQL error as a pyodbc SystemError.
Full policy-key joins, selected-code filtering and saved state are unchanged.
Regression: `tests/test_audit_change_segment.py`. Read-only live CKPR type 4,
type 9 and combined queries passed via
`tools/audit/verify_change_segment.py --sample` (Max Count 1).

## Query participation filter

Policy's identifier controls use aligned compact rows. Plancode is exact-only,
with its input left-aligned and RGA immediately beside it; there is no match-mode
dropdown. Existing all-coverage/Cov1/coverage-level scope is unchanged; the
Plancode tab's list stays exact. Regression:
`tests/test_audit_policy_tab_defaults.py`, `tests/test_audit_covsall_join.py`.
Native no-DB check: `tools/app/verify_policy_identifiers.py --screenshot <path>`.

Query's **Policy (2) > Participating (02)** uses base phase 1
`LH_COV_PHA.DIV_PTP_TYP_CD`, even in coverage-level mode: A-H participating,
9 participating with dividends paid up, blank/0-8 nonparticipating.
NULL/unrecognized codes remain unknown. The three-choice multi-select follows
the compact termination-date group and other left-column criteria. Checked
adds the raw code and description; selections filter, no selection displays
only. State persists through saved queries and clears with New. See
`tests/test_audit_participating.py` and the Audit criteria documentation.
Native no-DB verification: `tools/app/verify_policy2_participating.py
--screenshot <path>` checks compact rows, three visible options and saved-query/New behavior.

The **WL** page uses standard checkbox/listbox controls, fitted to text and row
counts. Its full **Participation Type (02)** list shows Blank, 0-9 and A-H with
descriptions; **Par** replaces the selection with exactly A-H, not 9. It shares
base-code definitions with Policy (2), combines with that tab using AND, and adds
the detailed type description without duplicate grouped columns. WL dividend,
NFO and CV criteria are also wired to SQL. Existing saved dividend/NFO keys remain
unchanged. Regression: `tests/test_audit_wl.py`; add `--wl-screenshot <path>` to
the native participation verifier to check both pages.

## Query Plans and Policies

The former Plancode tab now contains two shared identifier-list panels:
Plancode and Policies. Both support Add/Enter, multi-select removal, clearing
and clipboard paste (Excel rows/columns, commas, semicolons or whitespace).
Normalize to uppercase, preserve leading zeros and deduplicate in input order.
Only Plancode has the existing Cov1-only option. Policies filters the canonical
`LH_BAS_POL.CK_POLICY_NBR`, never `TCH_POL_ID`, using exact IN matching without
adding a coverage join. Empty lists are ignored; populated lists AND with
each other and all other criteria. Region/company/system/Max Count still apply.
Both lists persist in the existing `plancode` saved-state section and clear with
New. Regression: `tests/test_audit_plans_policies.py`; native no-DB verification:
`tools/app/verify_plans_policies.py --screenshot <path>`.

## Query Other Queries

CyberLife's **Other Queries** replaces its Common Tables tab. The separate visual
query builder's common-table functionality remains. Three standalone lookups
restore `frmAudit.frm`'s Other queries functions: base plan to riders, rider plan
to bases, and table/field value frequencies. They use the selected Region only,
not the main criteria, system selector or Max Count. Each panel has its own Find,
View SQL, compact `FilterTableView` and unsaved Excel export.

Counts represent occurrences, not distinct policies, including active/inactive
policies and coverages. **Use `COUNT(*)` for rider coverage rows.** Live CKPR's
Data Virtualization driver returns distinct-value counts for `COUNT(column)`:
`COUNT(R.PLN_DES_SER_CD)` produced 1 per group. Field **Record Count** uses
`SUM(CASE WHEN V.TCH_POL_ID IS NOT NULL THEN 1 ELSE 0 END)` to count non-NULL
record occurrences, not distinct technical IDs. Do not use `COUNT(ALL column)`:
the live driver rejects that syntax. Keep result grids explicitly read-only
(`NoEditTriggers` for both normal/frozen views); clicking must not open blank editors.
Read-only flags alone do not prevent the native blank-cell appearance: overriding
the table stylesheet must retain explicit selected foreground/background colors.
Use black text on light blue for active/inactive selections. The native verifier
and UI tests compare rendered text pixels before/after clicks, not only model data.
Base-to-rider excludes later phases with the base's own plancode. Joins use the
complete system/company/technical-policy key. Show policies uses `CK_POLICY_NBR`
plus company, not a substring of `TCH_POL_ID`; each checkbox controls only its own
panel. Inputs save/reset with the query; changing inputs/region clears results,
and stale async responses cannot repopulate them. Plancodes are bound with DB2
VARCHAR parameter types; table/field inputs permit unqualified identifiers only.
Failures remain explicit. Read-only live verification of base `1U143900` and
rider `1U535A00` reconciles counts against Show policies detail rows using
`tools/audit/verify_other_query_counts.py --plancode <plan> [--kind bases]`.
Remaining live checks are tracked in WORK_LAPTOP_SPEC.md.
Tests: `tests/test_audit_other_queries.py`, `tests/test_audit_other_queries_ui.py`.
Native synthetic/no-DB check: `tools/app/verify_other_queries.py --screenshot <path>`.

## Query Transaction criteria

Transaction has two compact stacked sections, **Transaction 1 AND Transaction 2**.
With no date comparisons, each populated section requires one matching `FH_FIXED` row via independent
`EXISTS`, or no matching row via `NOT EXISTS` when **Exclude** is checked.
Blank sections are ignored, even with Exclude checked. Types and fund IDs are ORed within their
section, while all fields in that section constrain the same row. Both sections
may match different rows or the same row; do not require distinct transactions
or multiply results with history joins. Correlate on company/technical policy ID,
never `CK_SYS_CD`. Issue-month/day checkboxes retain the base issue date.
The original optional month/day ranges remain in both sections. Dates/ranges
are validated with section-specific errors. Transaction 1 retains its saved-state
keys; `transaction2` holds the second set. New clears both.
Each section also has checkbox-enabled **Is Reversal** (`FCB0_REV_IND`) and
**Reversed** (`FCB2_REV_APPL_IND`) 0/1 multi-select lists. Flags constrain the
same row as the other criteria. Unchecking clears/disables its list; checked
without selections is unrestricted. NULL is not zero. Exclude and both flag
controls save/reset with their section and default off.
Both sections place compact 40px Eff Mth and Eff Day ranges on separate rows,
each beside its existing Issue-month/day checkbox. Gross Amt follows those
rows; Origin and Fund ID List sit beside the reversal controls below it.
Transaction 2 has Entry Dt / Eff Dt comparison dropdowns: none, or strict
After/Before/Equal to Transaction 1 Entry/Eff Date. Nested `EXISTS` requires one
qualifying pair satisfying both comparisons and all section criteria; never
combine different anchors or pick an implicit latest transaction. Empty
Transaction 1 means any reference row when linked; equality may use the same
row, and NULL dates do not compare. Transaction 1 Exclude clears/disables the
dropdowns. Linked Transaction 2 Exclude requires an anchor and no qualifying
pair anywhere, not merely an anchor without a partner. Invalid combinations
raise explicitly. Both comparison labels save under `transaction2` and default
to none on missing keys/New. No joins that multiply policies are introduced.
See the Audit criteria documentation and `tests/test_audit_transaction_{tab,filters}.py`.
Native no-DB check: `tools/app/verify_transaction_tab.py --screenshot <path>`.

## Audit file-source text encodings

File-source intake detects UTF-8, UTF-16 and UTF-32 byte-order marks before
delimiter detection and persists the resolved encoding with the parse spec.
BOM-less text remains strict UTF-8; explicit encodings are honored, never
silently replaced or guessed. Delimited and fixed-width intake, member
validation, preview and DuckDB querying share the same readers in
`audit/adhoc_source_intake.py`. Delimiter sniffing reads only 8192 characters,
not the whole file. Regression: `tests/test_text_source_encoding.py`.
Read-only verification: `tools/audit/verify_text_file_source.py <path>
--output <report.json>` checks an isolated saved-source round trip, preview
and full SQL row count against an independent CSV reader without printing
records or changing the original file or the user's saved sources.

## PolView usability layer

A **badge strip** under the lookup bar shows status badges (non-production
region code, grace, MEC, loan, reinsurance, product, GPT/CVAT, joint) and
context-aware suggested support actions — no text summary. It is built from
named `PolicyInformation` properties read under per-fact `cached_reads_only()`
guards (`polview/services/policy_insights.py`): facts not yet prefetched stay
pending, never a GUI-thread query or a guess. Show the definition of life as
**GPT**, never "GP" (reads as Grace Period). Optional tabs keep a fixed
position and grey out with the reason instead of disappearing. The lookup bar
(shared with RERUN) accepts pasted references and completes recent policies by
number or insured name; it never runs commands. A **Shortcuts** button in the
title bar lists the only shortcuts, Ctrl+F (field finder) and F1 (help); there
is no command box for now.
Private per-policy notes (local profile only), a field finder, Timeline and a
Copy summary (HTML table + aligned text; no insured name or face) complete the
toolkit. Grids gain selection totals, column choosers and empty-state notes;
`StyledInfoTableGroup.set_field_sources()` documents field lineage. The Tables
panel is filled by a background loader stage with PolicyData's verified keys.

**Tooltips:** Qt styles a tooltip with the showing widget's style sheets, so
`background: transparent` label rules made PolView tooltips dark-on-black.
`polview/ui/tooltip_style.py` restyles tips shown over registered windows with
*bare* declarations on the tip itself (a `QLabel { }` rule does not win).
Native check: `tools/app/verify_polview_tooltips.py --output-dir <dir>`.
**Dialog references:** dialogs with `WA_DeleteOnClose` must be checked with
`sip.isdeleted()` before reuse; calling a method on a deleted wrapper inside a
slot aborts the process.
See `docs/POLVIEW_CLAUDE.md` § "Usability layer"; regression
`tests/test_polview_ux.py`; native live check `tools/app/tour_polview.py`.

## PolView initial loading

Each policy/region/company first opened in a PolView session defaults to
**Coverages**. Returning to a previously viewed policy preserves the existing
tab-selection behavior. Regression: `tests/test_polview_lazy_loading.py`.

PolView queues initial identity/Coverages lookup on a dedicated worker, then
prepares remaining data pages (including Reinsurance and the Advanced Values
calculation) while the user interacts with ready pages. Selecting a queued page
prioritizes it after the active query. Tab overlays show loading/errors and Retry,
covering and disabling old-policy controls. Generation tokens reject stale
results after policy switches. Optional tab availability is checked in background.

PolView retries a read-only stage once on communication failures such as
`08S01` / DB2 `-30081`, using a fresh worker-owned connection. Persistent failures
retain explicit error overlays and manual Retry. Never label transport failures
as expired passwords: only explicit authentication diagnostics trigger the ODBC
credentials prompt (the shared classification also serves RERUN). Strip NUL-padded
driver-buffer garbage before displaying errors. Cancellation still suppresses
stale retries/results. Regressions: `tests/test_db2_connection_errors.py`,
`tests/test_polview_lazy_loading.py`, `tests/test_policy_prefetch.py`.
Read-only native checks of S1362723 and UIP00108 / 01 passed with all tabs ready.

PolView's worker identifies Rocket DV `rdvodbc64.dll` before configuring query
timeouts. Never probe its unsupported `SQL_ATTR_QUERY_TIMEOUT`: the driver can
return malformed UTF-16 diagnostics and a pyodbc `SystemError` during app
handoffs. Keep the login timeout and genuine communication-failure retry.
Diagnostic cleanup must preserve separately supplied SQLSTATE codes so those
retries and authentication handling still work when the message omits the code.
Missing monthliversary AV remains unavailable; both account-value accessors use
`LH_POL_MVRY_VAL.CSV_AMT`, never the nonexistent `TH_POL_MVRY_VAL` fallback.
The loading/error heading shows the requested policy, not the prior one.
Read-only native U0613620 / U0482811 repeated Query/RERUN handoffs passed with
all tabs ready via `tools/app/profile_polview_load.py --policy U0613620
--company 01 --all-tabs --handoff-policy U0482811 --output <report.json>`.

SuiteView disables pyodbc's process-wide ODBC Driver Manager pooling at package
startup, before the first ODBC environment is created. Otherwise a closed
Query/PolView connection can be recycled into another worker or into the same
failed-session retry; bypassing `DB2Connection._connections` alone is not physical
isolation. Application-owned live connection caches remain unchanged. The ODBC
setting necessarily applies to all pyodbc DSNs and requires a full application
restart, not another Get. Never toggle it lazily in a worker after connections
already exist. Regression tests model failed physical-handle recycling and
verify startup performs no database I/O. `profile_polview_load.py --prime-query`
adds a real isolated source query on a retiring worker before native handoffs;
`--odbc-pooling on|off` is a fresh-process diagnostic override only.
Read-only 000226237 / 26 and 000239324 / 26 native checks passed. The intermittent
live Permanent Agent Error / Host communication failure also occurred in logs,
but did not recur in fresh-process pooled baseline checks; do not claim those
checks conclusively establish pooling as the cause of every transport failure.

`polview/services/policy_prefetch.py` owns data preparation and worker-private
connections/cache; `ui/policy_load_controller.py` owns scheduling and shutdown.
Only detached snapshots cross threads. GUI rendering is cache-only and preserves
the shared GUI policy identity; never share worker ODBC handles or render widgets
off-thread. Company selection/pending behavior remains in the shared policy
service. Other Data, raw/rate browsing and support tools remain explicit actions.
See `docs/POLVIEW_CLAUDE.md` for architecture, read-only native profiling and
responsiveness/cancellation/retry regressions. Cold module/widget initialization
still costs time; do not confuse queue-return time with usable policy data.

Policy-record pages must not depend on optional illustration calculations.
Advanced Values snapshots validated record data before calculating surrender
values. Missing rates/configuration or failed calculation dependencies leave only
Surrender Charge / Value `N/A`, with a local notice/tooltips and logged diagnostics,
never a full-tab error. Required record retrieval failures still remain explicit;
never invent values or guessed plan/rate settings. RERUN validation is unchanged.
Regressions: N0100046 / FN2VN300 and S1360299 / 1S134F00,
`tests/test_policy_prefetch.py`; native profiler supports
`--expect-surrender-unavailable` and `--expect-surrender-reason` with `--all-tabs`.

## PolView stored CV/NSP rates and Guaranteed Cash Value

The Policy tab shows the base coverage's stored 02-segment per-unit window
(`LH_COV_PHA.LOW_DUR_*_CSV_AMT`, else `LOW_DUR_*_NSP_AMT` for ETI/RPU/paid-up),
keyed from `LOW_DUR_PER`. Targets & Accumulators interpolates **Guaranteed Cash
Value** from it through `PolicyInformation.guaranteed_cash_value()`; this serves
ISWL, where CyberLife 62Q1 errors. Any unvaluable active coverage yields N/A
with a reason, never a partial total. NSP-basis values are labelled `(NSP)` and
are not reconciled to a CyberLife nonforfeiture quote. See `docs/POLVIEW_CLAUDE.md`,
`tests/test_polview_guaranteed_cash_value.py` and the read-only live check
`tools/app/verify_guaranteed_cash_value.py @tools/app/guaranteed_cash_value_cases.json`.

## PolView Other Data

PolView's permanent **Other Data** tab now owns SAP, CLAIMSFILE, TAICyberTAIFd,
orion_pcr3_r and CYBERLIFE_PDF, formerly on Policy Support. Left-panel buttons
select embedded viewers. Claims/PDF load on first selection; the others retain
date inputs and explicit queries. Per-policy inputs/results/selection are
restored without querying; new policies start empty. CLAIMSFILE's editable File
Location persists in the profile's `settings/polview_other_data.json`. See
`docs/POLVIEW_CLAUDE.md` and `tests/test_polview_other_data.py`.

## PolView Single/Joint insured display

PolView Coverages and RERUN's live Policy Single/Joint labels share
`PolicyInformation.insured_lives_description`, using base phase 1's
`LH_COV_PHA.NBR_OF_LIVES_CD` / `FCVLIVES-LIVES`: 1 = Single,
2 = Joint First to Die, 3 = Joint Second to Die. `number_of_lives_code`
and `is_joint_insured` use this same source; never infer from person roles
or `LIVES_COV_CD`. Missing/invalid codes remain explicit errors.
Initial Coverages prefetch validates the description for cache-only rendering.
Live-verified 000321709 / 26 has code 3 and shows Joint Second to Die; see
`docs/POLVIEW_CLAUDE.md` and `tools/app/verify_joint_insured.py`.

## PolView / RERUN Decrease Charge Rule

`PolicyInformation.decrease_charge_rule` reads live-verified
`TH_NON_TRD_POL.DECR_CHRG_ALLOW` (CyberLife FULDRRUL, segment 66):
`1` = specified decreases assess a partial surrender charge, `0` = they do not.
Blank/NUL-padded rows are unset (`""`); `decrease_charge_allowed` returns
True/False/None. PolView's Policy tab shows **Decrease Charge Rule** below
TEFRA/DEFRA only when the code exists. RERUN carries it as
`IllustrationPolicyData.decrease_charge_allowed`: `False` removes the specified
face-decrease PSC, even on CurrentSA plans (e.g. FFL/FIUL plans such as
`1U14L400`, `NU1F3H00`). `True`/unset keep `PlancodeConfig.partial_surrender_charge`;
the policy rule never adds a charge to OriginalSA plans. Withdrawals and
A→B option-change decreases are unchanged. Regression:
`tests/test_polview_decrease_charge_rule.py` and
`tests/test_illustration_policy_change_guidelines.py`. Read-only live probe:
`tools/policyrecord/probe_decrease_charge_rule.py [--by-plancode --summary-only]
[--policy <n> --company <cc>]`.

Query's ADV tab has a gated **Decrease Charge Rule (66)** list (0, 1, Blank)
filtering through a full-key `EXISTS` on `TH_NON_TRD_POL`; Blank means not 0/1
(space/NUL/NULL), never a missing row. The ADV page is three top-aligned,
content-fitted columns (checks + Value Ranges; code lists; IUL/fund criteria).
Regression: `tests/test_audit_adv_decrease_charge_rule.py`; native no-DB check:
`tools/app/verify_adv_tab.py --screenshot <path>`; read-only live check:
`tools/audit/verify_decrease_charge_rule_filter.py`.

## PolView coverage zero values

Coverage and benefit numeric zero values must remain distinct from missing data
through `PolicyInformation` and the Coverages tab. Zero units/VPU, premiums,
flat extras, benefit ratings and issue ages display as zero, not blank.
See `docs/POLVIEW_CLAUDE.md` for regression tests and the read-only UL054808
verification helper.

## PolView Policy Record segments 55 and 57

The Policy Record viewer shows **only implemented screens with policy data**, using
the canonical record/table mapping through `PolicyInformation`. Populated segments
without a supported screen have no tab; build them out one by one. Supported
screens with data/build failures retain an explicit error tab. No policy, absent segments and loading
failures must never display captured screens. Data-access errors remain explicit,
not assumed empty. Every displayed value supports right-click Copy through
`CopyableLabel`; independently colored bits copy their complete flag value.
Regression: `tests/test_policy_record_viewer.py`.
Segment 69's 24 mapped FH tables have verified policy/company keys but no
`CK_SYS_CD`; `PolicyData` keeps an explicit verified set, not a blanket prefix
exception. Bind string keys as `SQL_VARCHAR` with `setinputsizes`: DataDirect
rejects inferred Unicode parameter types with HY004. Preserve `FH_FIXED` date/
sequence ordering. See `tests/test_policy_record_history_keys.py`.

Individual Fund Control (6255) joins the common `LH_COV_IVM_FND_CTL` header
to `LH_COV_FXD_FND_CTL` by the complete policy/phase/fund key. Non-tiered
fixed records are 79 bytes; High Phase occupies 60-61, not the archived
HTML's single byte. All four UL045809 GP/U1 lines match the supplied capture.
Variable-fund and tiered variants remain explicitly unavailable until live
verification; never silently discard their extensions. NULL slots are
annotated and only verified flag bits are live.

Fund Allocation (6257) is live through `PolicyInformation`, retaining every
allocation type/sequence. Both source tables join on `FND_ALC_SEQ_NBR`;
`LH_FND_ALC.SEG_IDX_NBR` orders the entries, despite swapped workbook
descriptions. Header length is 30 plus 16 bytes per allocation. P/D/U values
use separate percent/dollar/unit columns; C dates use `CRG_DED_ALC_EFF_DT`.
Never turn NULL amounts into zero. Only verified flag bits are live.
UL045809 matches the supplied capture; U0633187 verifies multiple C/P/V sets.
Regression: `tests/test_policy_record_segment55.py` and
`tests/test_policy_record_segment57.py`. See `docs/POLVIEW_CLAUDE.md` for
read-only/native checks.

## PolView Policy Record segment 04

Benefits (6204) is live through `PolicyInformation`, including all 16 flag bits,
PPA interest rates, renewal indicators and the local automatic-rate-deny field.
The 81-byte layout is in **D20** pp.159-175/374, not D202. U0566833's four
captured benefit lines match live data; U0633187 also verifies an ABR benefit.
Join LH/TH benefit rows by complete policy/company/system, phase, type/subtype,
person/sequence, status and issue date; keep source order within each phase.
Never replace NULL with a stored zero or assume a missing TH row means `N`.
Unverified option/inflation and user-area variants raise explicit errors.
Archived layouts disagree on the frequency/rate-deny byte positions: retain
the verified displayed values without claiming those physical positions.
Regression: `tests/test_policy_record_segment04.py`. Read-only verification:
`tools/policyrecord/probe_segment04.py --expect-u0566833 --output <report.json>`.
Native preview/copy verification uses `tools/policyrecord/preview_policy_record.py`;
see `docs/POLVIEW_CLAUDE.md`.

## PolView Policy Record segment 67

Renewal Rates (6267) is live through `PolicyInformation`, grouped by
phase/person/sequence and ordered across the five rate/guideline entry tables
by `SEG_IDX_NBR`. The renewal-period header is 22 bytes plus 11 per entry.
Ordinary `RNL_RT` already holds packed digits; A/S guideline amounts instead
need cents and preserve negative `D` signs. Never replace NULL amounts with
zero or count `TH_COV_INS_RNL_RT` extension rows as additional entries.
UL045809 matches the supplied CyberLife screen; U0633187 exercises multiple
phases, extras and benefits. See `docs/POLVIEW_CLAUDE.md` for the live probe,
native screenshot helper and `tests/test_policy_record_segment67.py`.

## PolView Payment Accumulation (60)

The supplied 6260 capture is **segment 60**, not 61. It is live through
`PolicyInformation` and matches UL045809's three rows. The current 139-byte
layout includes `LH_POL_TOTALS.TOT_LTC_CST_OF_INS` before the used-accumulator
counter; the old HTML mislabels these final values. NULL numeric slots retain
CyberLife's `.00` display but are dim and explicitly labeled NULL; reserved
flags remain amber examples. Nonzero monthly extensions require further
verification. Segment **61 is user-reserved** in CyberDoc and has no supplied
DB2 mapping; do not invent a standard 61. See `docs/POLVIEW_CLAUDE.md`.

## PolView Annual Totals (63/64)

Policy-year (6263) and calendar-year (6264) screens read stored totals through
`PolicyInformation`; never recalculate their history from current values.
Preserve policy-year bucket 0, numeric/date ordering, negative amounts and the
one-decimal life factor. Known flag bits come from DB2; reserved bits stay
amber examples. NULL slots remain dim and explicitly annotated. UL045809's
nine rows per segment match all 36 supplied capture lines. Regression and
read-only/native verification commands are in `docs/POLVIEW_CLAUDE.md`.

## PolView UL Reinstatement

Policy Support's **UL Reinstatement** button opens an optional **Reinstatement**
tab, with a non-UL popup instead of a tab for other products. Only lapsed
policies may be quoted, never surrendered policies. **Home Office
Reinstatement** is continuous coverage; its pay-to date is the latest
monthliversary and funding includes the next month's deduction. The shared
`polview/services/reinstatement.py` service owns safety-net, shadow and
surrender-value quote bases, dates and explanatory breakdowns. Do not perform
financial calculations in the UI or substitute missing data with zero.
**Skipped Coverage Reinstatement** remains visibly unavailable until its
rules are specified. Reloading/switching policies clears prior quotes.
See `docs/POLVIEW_CLAUDE.md` for UI and verification details.

## GLP Exception target-date quotes

Negative opening AV is funded with a **one-time lump sum plus a separately
solved ongoing modal premium**, never by repeating the catch-up amount.
First solve gross initial funding through the next modal collection (or the
target if sooner), then hold that first-payment floor while minimizing the
ongoing premium. The extra above any first-month scheduled premium is a dated
transaction; use `level_to_exception_inputs()` in both solver and display.
All three scenarios retain loads, caps and exception rules. Show the lump sum,
date and ongoing amount in the summary, clipboard, tooltips and workbook.
Ordinary funding stays on the positive-value side of the lapse boundary, so
cent rounding can leave a few cents rather than exactly zero.
Read-only verified UL045809 / 01 to 2026-12-15: $131.31 once plus $185.49 monthly,
giving $316.80 on October 15 and $185.49 on November 15, with displayed ESV $0.01.
Regression: `tests/test_glp_target_engine.py`; the native verification helper
also accepts `--screenshot <path>`.

GP exception entry must also recognize **actual exhausted guideline room**
after ordinary premiums, not just the annual scheduled-premium flag. For
off-cycle quarterly starts that flag can remain false after a later payment
uses the last available room. The shared `_compute_exception_premium()` checks
the enforced GPT limit against paid premiums less withdrawals (floating-point
tolerance only); allowance, safety-net, shadow, maturity and prior-lapse gates
remain unchanged. U0148463 / 01 to 2027-05-25 is the read-only regression case:
$233.75 initial lump sum, $296.03 quarterly level, a capped February payment,
then a $32.68 April exception and ending value zero. All three GLP tabs and the
workbook must calculate, not report "No level premium".
`tools/glp/diagnose_target_funding.py --policy U0148463 --target 2027-05-25`
traces initial/level solve brackets read-only.

PolView Policy Support > GLP Exception solves minimum premium only for monthly
deductions **strictly before** the target date. A solved zero must remain an
explicit zero-premium schedule: empty inputs restore the policy's billed premium.
Finite-horizon solves check lapse flags (the engine includes the terminal lapse
row) and positive ending surrender value, or zero-value GP exception protection.
All three tabs are always available: **Min Prem To Target** retains current GLP;
**Min Prem To Target (GLP=0)** independently solves a copy with starting GLP=0.
They share one solve/project helper, preserve current accumulated GP/GSP and
applicable TEFRA/TAMRA caps, forceouts and engine exception premiums. Neither
uses the retired TEFRA-off INPUT-to-MD alternative.
**Min Prem to Target (no forceout)** independently solves the GLP=0 policy with
`IllustrationOptions.guideline_forceouts=False` in both solver and display.
It suppresses only forceout distributions; premium acceptance caps,
TEFRA/TAMRA, targets and exception behavior remain unchanged. This third tab
is comparison-only: the regular GLP=0 scenario still sizes the adjustment.

Only an exception requirement in the original scenario warrants adjustment.
Size that adjustment from the GLP=0 scenario's total outlay before the target,
against valuation-date AccumGLP, accumulated withdrawals and premiums paid.
Never add later financial-history receipts to the valuation-date starting AV,
premium accumulator or cost basis. Opening AV is already post-deduction.
All three solves and displayed projections explicitly use monthly compounding
(`exact_days_interest=False`), matching RERUN's unchecked Exact Days Interest
control. Count **Prem + Exception Prem** once, excluding loan
repayments. If the original needs no exceptions, show **DO NOT ADJUST** while
keeping the GLP=0 comparison visible.

All three tables, clipboard cells and workbook export use the RERUN Values Overview
`LEDGER_COLUMNS` and `monthly_ledger_cells()` mapping, backed by full monthly
states. AV/SV are pre-interest; EAV/ESV are ending values. Prem excludes exception
premiums; withdrawals exclude forceouts, so rollups do not double-count.
Regression coverage: `tests/test_glp_target_engine.py` uses the real engine;
`tools/app/verify_glp_exception_tab.py --policy UL003587 --company 01
--target 2027-01-15 --expect-zero` exercises all three tabs and export through the live
Calculate action read-only (optional `--output` writes the verification JSON).
`--expect-opening-av` checks the starting post-deduction AV; `--reference` can
compare displayed ledger cells against a supplied JSON list keyed by Date.

## RERUN guideline calculation maturity

GLP calculations end at **min(policy maturity age, 100)**, not an unconditional
age 100. The policy's loaded `maturity_age` is authoritative; premium-cease age
is a separate charge rule, not the endowment horizon. The shared monthly
GLP/GSP/7-pay basis, policy-derived commutation inputs, optional engine search
and PV drill-downs use `monthly_guideline.guideline_maturity_age()`.
Age-95 policies have charge months only through age 94 and their terminal
endowment at 95; age-100/121 policies retain the age-100 cap. Midyear monthly
bases retain the partial-year offset.

The search's pre-anniversary seed uses the prior attained age so the engine's
contract-maturity clamp does not cut eleven months off an age-95 calculation.
Loaded inforce GLP/GSP/7-pay values are not overwritten; recalculations and
from-issue scenarios use the corrected basis. Source snapshots remain unchanged.
Regression: `tests/test_illustration_guideline_maturity.py`.
Read-only C19 / U0394137 verification:
`tools/engine/verify_guideline_maturity.py <bundle.cases.json> --case "C19 Batch"
--output <report.json>` reconciles before/after GLP/GSP drill-downs at both
changes to the solver, with all terminal endowment rows at age 95.

## RERUN renewal-rated benefit adjustments

Riders & Benefits must not infer adjustability from a benefit's stored issue
COI rate. Active non-administrative benefits load separate rate schedules;
NULL/zero issue rates do not mean free coverage. Live and saved-snapshot cards
use the same type-based eligibility. Administrative `#` benefits and already
matured/inactive benefits stay inspectable but their adjustment controls are
disabled. Existing rider coverage eligibility is unchanged.

U0416030's Benefit 39 (ULDW91) has a NULL issue rate and a 2028-02-15 cease
date. Verified Drop on 2026-10-15 with Prem to Maturity: current and guaranteed
charges stop, and saved-case Compare matches native Run Values. No snapshot
rate substitution or live-record change is needed.
Regression: `tests/test_illustration_rider_buttons.py`.
Read-only native verification:
`tools/app/verify_benefit_drop.py <c43b.cases.json> --output <report.json>
--screenshot <image.png>`.

## RERUN guideline substandard cease dates

Monthly guideline GLP/GSP/7-pay bases apply table ratings and flat extras using
each actual projection-month date and the same adjusted-COI helper as monthly
deductions. Charges stop on the recorded cease date, including midyear dates.
Never add the absolute policy year to the recalculation year: that counts
elapsed policy years twice and drops a lifelong rating decades early.

U0416030 / 01, Table 2 through 2063-02-15, reproduced the erroneous age-68
drop in the 2030-02-15 face-decrease recalculation. Corrected GLP Before is
6,519.52 instead of 5,624.62; month 73 q'x is 0.00378750 instead of 0.00252819.
The earlier table-drop scenario was not leaking into subsequent runs.
Regression: `tests/test_illustration_guideline_substandard.py`.
Read-only saved-snapshot/native check:
`tools/engine/verify_guideline_substandard.py <c43b.cases.json> --case C43B
--output <report.json> --screenshot <image.png>` recreates the screenshot inputs
in memory, checks explicit removal and rerun isolation, and leaves saved work
unchanged.

## RERUN monthly MEC detection

**Conform to TAMRA** controls premium capping, not MEC detection. After each
projected month, the engine tests accepted seven-pay contributions against the
active **TAMRA year**, independent of the policy anniversary. The first excess
or failed decrease back-test permanently sets `is_mec` and `mec_year`; later
anniversaries, withdrawals or recalculations cannot clear or redate that status.
Projection-private policy state prevents a MEC result from contaminating the
loaded snapshot, another solve or the guaranteed run. Values, Report and Compare
share the detection rule; both projection timings carry the permanent status.

C19 Batch / U0394137 verified read-only with TAMRA off: B-to-A starts a new
period on 2026-10-01, accepting $10,897.44. The next annual payment on 2027-09-01
is still in TAMRA year 1, so $21,794.88 exceeds the recalculated $10,920.96
limit (after the maturity-95 horizon correction) and establishes MEC in
**policy year 28**, not at the later year-32 face decrease. TAMRA on caps the
year-28 payment; the separate year-32 decrease can still fail its back-test.
Regression: `tests/test_illustration_mec_detection.py` and
`tests/test_illustration_tamra_recalc_sheets.py`. Native saved-case verification:
`tools/app/verify_saved_case_mec.py <bundle.cases.json> --case "C19 Batch"
--tamra off --expect-year 28 --native --output <report.json>`.

## RERUN face decrease before B-to-A option change — pending implementation

**Business/compliance decision (2026-09-21): recorded for future minimum non-MEC
face options; calculation behavior is not changed by this note.**

When a policyholder requests a face decrease together with a death-benefit option
change from B to A, process the **decrease first, then the option change**.
This is the adopted conservative business rule, not a claim that the engine
already implements it or an independent interpretation of regulations.

For a policy in an existing 7-pay period where the objective is to avoid MEC
status:

1. Determine the maximum permissible decrease (minimum remaining face) on the
   **pre-option-change basis**, with the recalculated 7-pay premium still passing
   backtesting against the existing period's premium history.
2. Apply and evaluate that decrease before allowing the B-to-A change to start
   another 7-pay period. A later reset must not erase a failed decrease backtest.
3. Then process B-to-A, including its increase in specified amount and applicable
   material-change / new 7-pay-period treatment.

Do not solve the minimum face after first resetting the period through B-to-A:
that could allow a much larger decrease and lower face than the adopted rule.
An absolute face input for the decrease is the **post-decrease, pre-option-change
face**, not the final face after B-to-A. The subsequent option-change increase
must not be overwritten by reapplying that absolute target. Preserve this
distinction when accepting a target face rather than a decrease amount.

**Known implementation gap:** `illustration/core/calc_engine.py` currently
orders `DB_OPTION` before `FACE_AMOUNT` through `_POLICY_CHANGE_ORDER`, used by
both `_compile_policy_changes()` and the monthly processing loop. That loop
combines changes for guideline/7-pay recalculation and material-change reset.
A future implementation must preserve the intermediate decrease/backtest stage;
swapping sort priorities alone is not sufficient evidence of compliance.
Revisit this with minimum non-MEC face options, with regressions for an active
7-pay period, a decrease failing before but passing after a reset, and equivalent
absolute-target/decrease-amount inputs. Verify shared solver, Run Values and
saved-case/Compare behavior; do not silently extend this decision to unrelated
option-change combinations.

## RERUN target-based benefit amounts

Primary-insured **Table Rating Change** inputs also replace every type-3/type-4
premium waiver's rating multiplier with `1 + TableRatingFactor * new_table`
on the change date (table zero means multiplier 1). Apply this to the private
projection policy before target and guideline recalculation, so monthly charges,
displayed adjusted rates and GLP/GSP/7-pay after-bases all agree. Before-bases and
unchanged runs retain the recorded benefit factors; other benefit types, riders
and the loaded snapshot remain unchanged. Regression:
`tests/test_illustration_waiver_rating_changes.py`.

Target-based stipulated-premium waiver (type 4) charges use the plan's explicit
`PWoT_COI_Basis`: 2 is current annual MTP (`policy.mtp * 12`), 3 is current annual
CTP, and 1 retains recorded units. `1U14L400` (UFF90022 / 26, benefit 4M) uses
**basis 2**, per the business correction of 2026-09-21; its previously omitted
setting incorrectly froze the benefit at $913.20 after a face change.
Do not infer a target basis from an amount coincidentally matching MTP/CTP or
change all FFL plans. Existing policy-change recalculation updates the targets
before monthly deduction; both displayed amounts and actual charges consume
them without mutating the loaded benefit.
Read-only verification: `tools/engine/verify_target_benefit_amounts.py --policy
UFF90022 --company 26 --date 2027-01-04 --face 100000` verifies a hypothetical
decrease: annual MTP and 4M amount become $610.31, and its charge becomes $1.10
instead of $1.64. Tests: `tests/test_illustration_pwot_coi_basis.py`.

GLP/GSP/7-pay monthly bases and their Before/After PV detail use the same
`target_waiver_charge()` helper as monthly deductions for PWoT basis 2/3.
Use each side's annual MTP/CTP and the base coverage's active table rating;
do not use recorded benefit units or its independent rating factor. Charges
are cent-rounded and ratings stop on their actual cease date. Basis 1 and
type-3 waiver rules are unchanged. The earlier face-change fix covered monthly
deductions but missed this guideline path.
Read-only verified `000239324 / 26 / NU1F3L00`, face 50,000 on 2026-09-24:
annual MTP 217.83, first After 4M charge 0.81 (not 1.36), GLP After 1,397.26
(not 1,402.75). The verifier above now checks GLP/GSP After against monthly
charges; regressions also cover 7-pay, current/guaranteed projections, increases,
decreases, zero targets, rating cessation and source immutability.

## RERUN Policy calculated monthly deduction

RERUN's live Policy refresh retains the load-time calculated monthly deduction
and validation warnings for that exact `PolicyInformation` instance. The
post-load Edit Record/basis refresh must not clear Calculated MD or hide failed
MD/rate checks. A refresh reuses the check without rerunning the engine; a new
Get replaces it, and saved/edited snapshots never inherit the live result.
Regression: `tests/test_illustration_session_state.py`.
Read-only native verification: `tools/app/verify_policy_calculated_md.py
--policy UFF90022 --company 26 --screenshot <path>` uses an isolated temporary
profile and the real Get/refresh path. Verified both MD fields display $18.70.

## RERUN corridor COI rate

Corridor COI uses the **latest active base segment's adjusted COI rate**, not
coverage 1's rate. Reuse that segment's current duration, rate band, table rating
and active flat extra. Skip depleted, matured, terminated and not-yet-issued
segments; a stored zero rate remains zero, not a reason to select an older
segment. Segment order is the engine's existing oldest-to-newest order.
Ratchet-banded plans select the same segment for both corridor band rates,
retaining their band-split charges.

`coi_rate_corr` carries the corridor rate separately from the existing
coverage-1 `coi_rate`, through the inforce row, both projection timings, Values
and Excel/debug exports. Ratchet's single display rate remains its band-1
representative; charges still use both bands. No COI rate tables are changed.
Regression: `tests/test_illustration_corridor_coi.py` and
`tests/test_illustration_values_tab.py` include the 2.39 / 2.55 distinction.

## RERUN waiver target rate units

UL_Rates stores benefit **39 / 3#** target rates as percentages, not decimal
multipliers: 5.5 means 5.5%, not 550%. `compute_target_premiums()` converts
these rates only for calculation, retaining the raw rate in Values/export
detail. Never infer units from the rate's magnitude or divide all type-3 rates:
FFL **3F** retains its existing cost-basis units. CTP continues to use the
rounded MTP-basis waiver component. No shared rate-table values are changed.

UIP45890 / 01's $50,000 to $100,000 face increase on 2026-09-26 exposed
the issue: waiver MTP was overstated 100-fold. The corrected annual target is
689 + (689 x 0.055 x 1.5) = 745.8425, giving Monthly MTP **62.15**, not
531.10. The loaded basis independently reconciles to **40.86**.
Regression: `tests/test_illustration_waiver_target_units.py` and
`tests/test_illustration_ffl_waiver_targets.py`. Read-only live verification:
`tools/engine/verify_face_increase_targets.py --policy UIP45890 --company 01
--date 2026-09-26 --face 100000 --expect-monthly 62.15 --expect-loaded-match`.
It checks the face-change illustration, unchanged control/source and Values/Summary
export mappings without changing live records.

## RERUN plan interest bonuses

Illustration bonuses use `illustration/plancodes/tRates_IntBonus.json`, selected
by plancode and latest effective date on or before the valuation date.
`1U135P00` has an unconditional 0.90% duration bonus effective 2023-02-01,
starting in policy year 11, with zero AV and guaranteed bonuses. Store its
`BonusDurThreshold` as 10 because the engine applies the bonus strictly after
the threshold year. Earlier effective entries remain intact.
Regression: `tests/test_illustration_bonus_rates.py`.

## RERUN Monthly MTP truncation

Monthly MTP uses decimal-safe cent truncation via `truncate_monthly_mtp()`.
Never use `math.trunc(mtp * 100) / 100`: an already-recorded 32.66 can multiply
to just below 3266 in binary floating point and incorrectly become 32.65.
UIP12968's annual MAP of 392 gives `TRUNC(392 / 12, 2) = 32.66`.
The initial snapshot, both projection timings, target calculations, guideline
MTP basis and rollback reverse accrual share this rule. Preserve the separate
rounded PW basis in illustration timing. The Values grids and exports consume
the corrected state; do not patch display formatting or replace loaded targets
with recomputed annual targets.
Regression: `tests/test_illustration_monthly_mtp.py` and the recorded-cent case
in `tests/test_value_rollback_data.py`.

## RERUN unavailable table-rating target rates

All-NULL `TBL1MTP` / `TBL1CTP` lookup rows mean the table-rating target rate
is unavailable, not zero. `Rates` returns `None` for that case, retains stored
numeric zero, and rejects mixed NULL/numeric results explicitly. Unrated
coverages and expired table ratings can still calculate their ordinary targets;
active table ratings require both target rates. A shadow target configured as
`Table` also requires its table rate when the base coverage is rated. Never
replace a required missing rate with zero. Run Values logs failure tracebacks.

Read-only live/native verified `000340565 / 26 / 1U14L300`: phases 1 and 7
have table rating zero and NULL table-target rates; Run Values now builds
725 current rows, 523 guaranteed rows and a 61-year report.
Regression: `tests/test_null_table_target_rates.py`.
Repeat with `tools/engine/verify_table_target_rates.py 000340565 --native`;
the helper uses an isolated temporary profile and writes no database records.

## RERUN Values Summary loan columns

Values > Summary separates the beginning-of-month loan buckets into
`Loan_Accr_Int` (all outstanding accrued interest, not just this month's
charge) and `Loan_Princ` (principal only), each summed across regular,
preferred and variable loans. Ending loan columns remain unchanged.
The shared `illustration/core/summary_results.py` mapping also drives debug
exports and regression snapshots.
Regression: `tests/test_illustration_values_tab.py`.

## RERUN Values Summary shadow columns

Summary appends the workbook columns `vShadow_TP`, `Shadow COI`, `Shadow EPU`,
`Rider Charges`, `Shadow MD`, `Shadow Int Rate`, `vShadowEAV` in that order.
They read the existing monthly shadow state, not a UI recalculation.
Rider Charges is the shadow charge total (riders and benefits excluding CCV),
not the regular-side Rider COI. vShadowEAV is ending shadow AV before debt.
Summary's interest rate is a decimal (0.045 = 4.5%), like its regular Interest
Rate; the separate Shadow Account detail retains percentage units and compact
headings. Summary retains the full workbook names to distinguish regular and
shadow COI/EPU/MD. Both current/guaranteed Summary exports and regression
snapshots share these fields; Summary schema version is now 3, and shadow
interest comparisons use rate tolerance rather than money tolerance.
Tests: `tests/test_illustration_summary_shadow.py`,
`tests/test_illustration_values_tab.py`. Native no-DB verification:
`tools/app/verify_summary_shadow.py --screenshot <path>`.

## RERUN Prem to Maturity new loans

Dynamic Inputs permits new loans with **Prem to Maturity**, including forecast
loans and loans before the solved premium's start year. UI enablement and input
export share `_new_loans_allowed()`; **Max Level** and **Prem to Shadow Maturity**
still block new loans, including when mixed with Prem to Maturity. Loan payoff
solve restrictions are unchanged. Explicit one-year annual loan rows emit a
zero cutoff next year, not an indefinitely recurring loan.

Existing solver trials, Run Values and saved/Compare materialization carry the
same loan schedules and Apply Premium to Loan option. Guaranteed projections
lock the current side's applied loans and premium-diverted repayments, without
solving another premium or repaying those dollars twice. No rate/model changes
were needed. Regression: `tests/test_illustration_prem_to_maturity_loans.py` and
the dynamic-input level-type tests.
`MonthlyState.applied_loan_repayment` is total applied cash and already includes
`loan_repay_from_prem`; guaranteed `lock_values()` must copy the total alone.
Adding that subset again doubled a $33.25 payment to $66.50 and understated
guaranteed loan balances. Engine-backed regression:
`tests/test_illustration_guaranteed_loan_repayments.py` covers both projection
timings, arrears/advance loans, mixed repayment sources and payoff remainders.
Read-only current-source verification:
`tools/app/verify_prem_to_maturity_loans.py --snapshot <policy-snapshot.json>
--output <report.json>` exercises revised Case9 through native Run Values and
save/export/import, without Excel or modifying the supplied snapshot.
Verified U0389725 / 01: $1,000 once on 2028-04-06, $56 monthly through March
2029, then $23.01 solved monthly from April 2029 ($14.54 in the separate no-loan
control). Both native and saved-case runners match. Existing terminal age-95
rows carry both matured/lapsed flags in both controls; no pre-maturity current
lapse occurred. Guaranteed values stop on lapse in February 2035.

## RERUN loan repayment priority

Loan repayments use the conservative fixed-loan order approved 2026-09-23:
**preferred accrued interest, regular accrued interest, preferred principal,
regular principal**. The shared `loan_handler.repay_loan()` owns this order for
explicit repayments, premium-to-loan diversion and Pay-off solver trials;
current/guaranteed and both projection timings consume it. Variable accrued
interest and principal remain afterward. Advance loans retain preferred-first
payoff and their existing unearned-interest refund; anniversary capitalization,
cash caps and overpayment handling are unchanged. Loaded records are never
mutated. Regression: `tests/test_illustration_loan_repayment_order.py` covers
each bucket boundary, payment sources, guaranteed cash-flow replay and a real
engine-backed payoff solve with unequal charge rates.

## RERUN Prem to Maturity levelizing

The Levelize choice applies even in the first guideline-capped policy year.
`level_to_exception_options()` must not enable the transition-year
dollar-for-dollar override when levelizing is on. Solver trials, Run Values,
saved/Compare runs and the shared target-date solves use this same option
builder. Outstanding loans still disable levelizing; Levelize off retains
dollar-for-dollar acceptance. Whole-cent modal caps remain floored and carried.
The guideline-limit latch uses the recorded guideline cap source and payable
cent cap, not equality with the unrounded allowance; fractional-cent room must
not prevent later GP exception entry or make the maturity solve fail.
With Levelize on, binding the annual guideline cap is sufficient for GEP
eligibility even while there is unspent room for later scheduled payments.
Do not require that all annual room has already been collected before funding
a midyear AV shortfall. Exception permission, safety-net, shadow and maturity
gates still apply; a below-cap request or TAMRA-only cap is not this trigger.
`tests/test_illustration_monthly_deduction_premium.py` exercises actual
month-6 GEP with annual room remaining, both projection timings, off-anniversary
starts, INPUT/Prem-to-Maturity options and negative eligibility controls.
UE006519 year 12 reproduced the override: $37.12 for five months, $18.58,
then six zeros despite Levelize on. With the same requested premium, the fixed
run accepts $17.01 in each of the twelve months.
Regression: `tests/test_illustration_premium_allowance.py` and
`tests/test_illustration_level_to_exception_horizon.py`.
Read-only live check: `tools/engine/check_premium_levelization.py UE006519 37.12
--prem-to-maturity --months 28 --year 12 --expect-level`; add `--solve` to
recalculate the maturity premium on the corrected basis.
Use `--native --year 12 --expect-level` to exercise actual Run Values and
saved-case Compare in an isolated temporary profile. Verified UE006519:
the corrected solve is $21.89 monthly, all twelve year-12 payments are $21.89,
and the current projection reaches age 121 without a pre-maturity lapse.
Guaranteed output is also built; saved Compare exactly matches Run Values.

## RERUN existing GP exception periods

An inforce GPT policy with a known GLP of zero starts in the exception premium
period. RERUN suppresses scheduled, unscheduled and Monthly Deduction premiums,
spends the existing account value, then uses calculated GP exception premiums.
This starting status does not require the Allow GP Exception Premium checkbox;
the existing safety-net, shadow-account and maturity restrictions still apply.
The red Input notice identifies the period and explains the premium treatment.
Unknown GLP is not evidence of zero; `glp_is_known` preserves that distinction
when loading/saving the illustration basis. Current/historical manual GLP edits
are explicit known assumptions. From-issue scenarios do not inherit the period.

Guaranteed projections still use the current side's locked cash flows, not
newly calculated guaranteed exception premiums. PolView's GLP-adjustment
what-ifs explicitly disable starting-period recognition: their hypothetical
GLP=0 funding comparison is not an assertion of existing exception status.
Regression coverage is in `tests/test_illustration_monthly_deduction_premium.py`
and the red-notice test in `tests/test_illustration_inputs_dynamic.py`.
Read-only live/native verification:
`tools/app/verify_inforce_exception_period.py --policy U0307077 --output-dir <directory>`.
Verified 2026-09-15: GPT, GLP=0, starting AV=-605.20; no regular premiums,
calculated exception premiums from the first projected month, zero regular
premium solved to maturity, and the red notice visible.

## RERUN new-business / from-issue scenarios

The policy-scoped **Inforce | New Business - From Issue** toggle on Illustration
Inputs selects a hypothetical issue illustration, not a historical replay.
The issue mode has a blue window header, persistent mode notice and an
**At-Issue Conditions** tab. The Policy tab always retains the loaded inforce
snapshot. Changing mode or issue assumptions invalidates old Values/Report.

Default to original issue-date base segments (exclude later increases/COLA),
using their original face amounts where available. The user can edit the total
issue face and death-benefit option and exclude original-issue riders/benefits;
there is no add-new-rider workflow. Current DB option, underwriting and billing/
allocation defaults are not evidence of original policy history: review them.
Later additions remain visible as excluded in the issue editor.

Issue scenarios reset balances/loans/accumulators and start the full monthly
pipeline at the original issue date and age. Current-side rates use scale 1;
current illustrated interest assumptions are applied from issue, while the
guaranteed side remains guaranteed. Issue targets and regulatory premiums are
recalculated on the edited coverage basis. Never mutate the source snapshot.
Each mode retains separate input schedules; historical transactions are not
copied into the new-business scenario. Saved/imported cases persist the issue
conditions and mode input states; Compare uses the same scenario builder.
ABR Quote is an inforce-only mode and cannot be combined with from-issue mode.
Grid Inputs > Unscheduled Premiums can explicitly populate the policy's
unreversed PR/PI/PA/PF/PT/PB/PW premium transactions from issue, including the
transaction type; this is user-triggered and is never automatic replay.

**No Lapse Period** on At-Issue Conditions selects an AV-less-loans lapse basis
for that many years from issue, rounded to the nearest projection month. It does
not permit unfunded AV to run negative: other existing protections still apply.
Afterward, the normal plan lapse basis resumes. Zero disables this convenience
override, not the contractual safety net. Default to the recorded minimum-premium
cease date's covered period when present, otherwise the configured
`PlancodeConfig.snet_period`, otherwise zero. Never change surrender charges,
minimum-premium targets, regulatory limits or shared plancode configuration.
The saved issue assumptions, solves, current/guaranteed projections and exported
basis notices carry the same period; it is not a contractual guarantee.
Regression: `tests/test_illustration_issue_no_lapse_period.py`.

Regression coverage: `tests/test_illustration_run_from_issue.py`,
`tests/test_illustration_issue_conditions.py` and
`tests/test_illustration_issue_outputs.py`. Native UI verification without DB
access: `tools/app/verify_issue_illustration.py --output-dir <directory>` uses
a synthetic policy and captures both themes. Month-end issue dates stay anchored
to the original issue day, including the Illustration-to-Date cutoff.

## RERUN Value Rollback

**Options > Edit Record** enables the entire valuation-editing feature. This
app-wide, session-only option defaults off. Off means the original read-only
Policy view: no valuation selector, inline value editors, or coverage-edit note.
Disabling restores loaded values for every open policy and invalidates their
valuation-specific results. Saved valuation cases require the option before
loading or comparing; never silently run their historical assumptions while off.

When enabled, the policy-level **Valuation Date / Update** strip defaults to the loaded
valuation date and includes recorded monthliversary values within six calendar
months before it; missing months are never invented. There is no Rollback toggle.
Selecting a date alone does nothing: **Update** applies it. Updating the current
date restores the loaded basis and clears manual value/coverage assumptions.
Historical selection is a scenario basis, not a change to the live policy.
Value editing is separate from New Business - From Issue and ABR Quote.

Keep the loaded `IllustrationPolicyData` immutable. Historical data flows through
`PolicyInformation` into captured rollback snapshots; scenario construction
applies a snapshot to a copy before projection inputs. Saved/imported cases
must retain both the source snapshot and the applied rollback selection and
manual edits. Policy-list switching retains that policy's applied basis;
explicit Get resets inputs. A failed rollback must leave the prior applied
basis intact, with an actionable error.

**Account Value** and **Shadow Account Value** are inline inputs beside their
Fund Values labels. They default to the selected basis's values; Enter or leaving
the field applies an edit. **DB Option** is an inline combo beside its Policy Info
label. **Coverages and Benefits** open detail windows with an editable **Amount**
row and an **Apply** button. These controls work for every applied current or historical
inforce date while **Options > Edit Record** is selected. All edits are explicit scenario
assumptions, never live policy edits.

Edit Record also exposes premium-paying Status, the six regular/preferred/variable
loan principal/accrued-interest amounts, loan charge rates, premium/withdrawal
accumulators, MTP/GLP/GSP/commission targets, MAP cease date, cost basis, MEC
status, 7-pay date/cash value/premium/lowest DB and all seven TAMRA contributions.
These edits share the same saved-case/Compare scenario path as AV and shadow.
Fund and allocation tables allow only numeric value edits for existing fund IDs;
there are no add/remove/rename controls. Their edits are staged with Apply/Reset;
allocation percentages must total 100%. Unapplied fund edits block Run/Save and
Compare rather than silently projecting or saving the previous values.
Account Value, fund balances and loan principal are independent manual assumptions.
Editing fund balances does not recalculate AV or loans; edit those fields separately.
Current-date AV edits retain existing fund IDs and balances. Historical total-only
AV never invents a fund breakdown.

Coverage/benefit editors are owned, non-modal top-level tool windows, not widgets
confined inside RERUN. Clear their reference on the explicit `closed` signal
before deferred deletion; `destroyed` sender identity is not a reliable reopening
guard under PyQt. Header Close, Cancel and Apply must all allow reopening.
The date label/combo/Update have aligned 26px heights. Only an applied date
different from the loaded valuation date activates the two-tone purple-to-white
header and notice gradient; current-date edits retain the normal header theme.

Historical specified amounts and death-benefit option are not reconstructed.
Changing to a different rollback date resets those date-specific edits; review
them again. The title, persistent
mode notice, Policy tab and output/export basis must identify rollback so
historical values cannot be mistaken for current inforce values.

`illustration/core/value_rollback.py` owns recovery and validation. U1MV AV is
already post-deduction. Ordinary unreversed PR receipts are reversed from the
current paid/cost-basis totals, including processed receipts after the loaded
valuation date; same-day ordering uses the recorded CD sequence. Pending
premiums are excluded only after exact reconciliation to the current paid total.
TAMRA contributions are matched by year keys, not row order. Loans use exact-date
fund/phase/preferred/interest-status buckets, never current/sentinel rows.

AccumMTP/AccumGLP are **derived, not archived**: reverse monthly MTP and
anniversary GLP on an explicitly unchanged target/coverage basis (GLP stops
accruing at age 100). `LH_POL_TARGET.TAR_DT` is not a snapshot date. CVAT's
AccumGLP is not applicable. Current support is single-base UL/IUL with
no detected target-affecting changes or unverified transaction effects;
unsupported or ambiguous essential data blocks Update rather than guessing.
Manual face edits re-resolve current rate bands at the existing rate-loading
boundary, preserving the original surrender-charge band.

**IUL uses historical total AV only.** Do not require or reconstruct individual
historical fund/bucket balances for rollback. Clear the historical fund detail;
retain loaded premium allocations and illustrated crediting assumptions as
forward assumptions, not historical holdings. The Policy tab explicitly labels
this aggregate-only basis, and report/export limitations carry it. Current and
guaranteed projections work without historical buckets, including WAIR crediting.
Recovery failures identify the actual historical blocker rather than cascading
"missing" accumulator errors when the current amounts are present.

The current XP target does **not** recover historical shadow balances.
Rollback can display the other recovered values while showing shadow as
**Unavailable**. Enter an explicit historical amount (including zero) directly in
**Shadow Account Value** to persist a manual assumption and unlock projection.
There is no separate Historical Shadow button.
Until then Run Values is disabled; scenario construction and the engine also
refuse the incomplete basis. Never use the current shadow amount as historical.
Historical NSP and tax-test recalculation are not reconstructed.

Regression coverage: `tests/test_value_rollback_{data,scenario,ui,outputs}.py`
and the rollback rate-band test in
`tests/test_illustration_band_specified_amount.py`. Read-only live/native check:
`tools/app/verify_value_rollback.py --policy UE055782 --company 01 --output-dir
<directory>` captures the screenshot policy's six prior dates, recovered values
and shadow gate. `--policy UE000576 --project` also exercises the real engine on
a complete historical basis. Both preserve the loaded policy and write no DB
changes. Full basis limitations accompany reports/exports and the Policy
banner's tooltip.
For IUL, `--policy UE215622 --company 01 --date 2026-08-10 --project
--output-dir <directory>` verifies the selected historical basis and native
AV/AccumMTP/AccumGLP display without requiring bucket data. `--date` validates
only that recorded date; older dates can still have genuine target-change or
unverified-transaction blockers. IUL current/guaranteed engine regression:
`tests/test_illustration_iul_crediting.py`.
Add `--exercise-edits` to verify inline current/historical AV, shadow, DB option
and coverage edits through the native controls and Run Values without saving
or modifying the loaded policy.
Add `--exercise-record` to exercise every scalar/loan/TAMRA editor plus native
fund-cell editing, Apply and pending-draft guards on current and historical bases.
Expanded regression coverage: `tests/test_edit_record_scenario.py` and
`tests/test_edit_record_ui.py`.

## Illustration specified-amount basis

`illustration/plancodes/plancode_table.json` uses **SA_Basis** (specified amount),
exposed as `PlancodeConfig.sa_basis`. It replaces Expense_Basis and consolidates
the workbook's Target SA_Basis, EPU SA_Basis and Target BandLock controls.
Every plancode row explicitly specifies `CurrentSA` or `OriginalSA`; do not infer
it from SkippedCovRein or accept the retired keys.

**OriginalSA** uses each coverage's original amount for EPU (table or flat),
MTP, CTP and full surrender charges. Only MTP/MTP table-rating rates are locked
to that coverage's issue band. CTP, COI, EPU and premium-load bands follow current
combined specified amount; SCR is unbanded. Coverage increases capture their
own issue band; later increases/decreases must not overwrite it. Policy-change
rate refresh updates every active segment's COI/EPU band, not just the changed
segment. CurrentSA retains current amounts and unlocked target bands.

Live issue bands come from `PolicyInformation.cov_mtp_band(coverage_phase)`:
the primary-person type-M renewal `RT_BAN_CD`, interpreted with the coverage's
`BAN_STRUCTURE_CD` (structure 6 orders X/Y before A). This mirrors the workbook's
BandAtIssue source, not a reconstruction from current face. Missing/ambiguous
bands or missing original amounts block OriginalSA loading explicitly. Reload
live policies and resave older illustration snapshots whose original-band field
was populated with the current band.

OriginalSA still has no partial surrender charge. Its withdrawal fee reduces
AV but not specified amount, matching the workbook's Target SA_Basis fee gate.
Shadow-account basis remains a separate contractual setting.
Regression: `tests/test_illustration_sa_basis.py`,
`tests/test_policy_mtp_band.py`, and the policy-service/withdrawal tests.

## Illustration COLA coverages and surrender charges

Illustration base segments retain `CoverageSegment.is_cola` from the canonical
`CoverageInfo.cola_indicator` (`TH_COV_PHA.COLA_INCR_IND == "1"`). The Policy
coverage detail shows **Added by COLA: Yes/No**, including newly saved snapshots.
Reload live policy data before resaving older snapshots that lack this flag.

For company **26** FFL UL plans (`PlancodeConfig.is_ffl`, not the company display
name), COLA-added segments have zero effective surrender rates and charges.
The shared engine helper applies this to full surrender, loan availability,
withdrawals and elective coverage reductions; other coverages remain unchanged.
Values > Policy Values builds SCR/SC columns for **every** base segment, retaining
zero-charge columns. Live verification: `000289393 / 26 / NU1F3H00` has seven
segments (phase 1 non-COLA; phases 5-10 COLA). Use
`tools/engine/verify_cola_surrender.py` for a read-only live check and UI captures.

## Whole Life rate loading

Whole Life has its own Rate Manager choice and source-keyed loader in
`suiteview/ratemanager/whole_life/`. It is intentionally separate from the
UL/Term pointer-index compiler: preserve the CyberLife keys, versions, date
ranges, age-use codes and premium options rather than inventing illustration
rates. See [`docs/RATEMANAGER_WL.md`](docs/RATEMANAGER_WL.md) for supported
sources and query semantics.

The Workup screen has separate CVF, IAF, DIV and PUI file rows, plus optional
NSP CSV and DIV map rows. Any combination can be parsed/reviewed/loaded as one
package via `parse_workup`; an invalid selected file blocks the whole workup.
The explicit company/user code is required only when IAF files are selected.

CVF `NO ZERO DUR` headers mean absent duration-zero metadata (SQL NULL).
Their grid indexes begin at FIRST DUR, not duration zero; map each cell to
FIRST plus its offset from the first printed decade, retaining only FIRST..LAST.
The first decade contains FIRST-1: FIRST 121's `120-129` begins at duration 121.
Do not invent a
duration-zero row or infer negatives without a signed header. D11 printed
page 110 defines the contiguous array; company `00 / 2EBF00 / age 1` has
`1000.00` at duration 59 (printed offset 58).

CVF imports floor every negative cash value to `0.00`, in both `RATE` and
`DURATION_ZERO_VALUE`. Resolve the signed duration-zero header and validate
raw source conflicts/padding before flooring; never let normalization hide
malformed source data. Existing negative rows are corrected by a reviewed reload.
The print grid loses signs. The user approved **optional** early-negative
inference: with a negative duration-zero header and a strict initial decline
followed by a rise, zero unsigned values before the first minimum and retain
the minimum as positive. For `08 / 1WL511 / age 59`, this changes `22.27` to
zero but retains `0.94`. It is an assumption, not recovered signs. The option
`infer_cvf_negatives` defaults off; skip plateaus/unfinished declines, never
override explicit `+` signs, and preserve raw validation. The rule version and
per-row adjustments must remain in source metadata and load receipts.

PolView's Rates > Coverages view routes traditional `WL` policies to cash values
through `PolicyInformation.rates_wl_cv()` and `Rates.get_wl_cash_values()`.
The key is coverage `INS_CLS_CD` + `PLN_BSE_SRE_CD` + `LIF_PLN_SUB_SRE_CD`
(1/3/2 characters), plus the CyberLife rate-file user (company 01 shares user
00; 04/06/08 are their own; others raise) and coverage issue age. Select only the
blank `USER_DEFINED` variant unless its mapping is explicitly known; never
fall back to another user or variant. Keep duration zero and source duration
labels intact. NSP/PUI/dividend lookups in this view remain future work.
ISWL and WL policies also get a Rates **Fixed Premium** branch (ISWL cash
values, `WL_RATE_PREM` premium rates, and the `RATE_MODEFACT` modal premium
beside `POL_PRM_AMT`), while ISWL coverages keep the UL view (current-scale
COI only) plus GINT, CVR, premium rate, loan rates and cease ages. See `docs/POLVIEW_CLAUDE.md` § "ISWL / WL
fixed-premium rates".
For ETI/RPU policies (premium-paying status 44/45), the Rates view shows
"Cash value file is not available for policies on ETI or RPU." without querying
rates or substituting an original Whole Life basis. Other paid-up statuses are
not excluded.

The four new tables are `WL_RATE_CV`, `WL_RATE_NSP`, `WL_RATE_PUI` and
`WL_RATE_PREM`. Dividend imports reuse the existing `WL_DIV_HEADER`,
`WL_RATE_DIV` and `WL_DIV_PLANKEY_MAP` schemas, not an external script at
runtime. Loading previews differences, inserts new keys, skips unchanged
values, and requires explicit per-table approval to update existing values.
It never deletes rows absent from an input file. Updates are backed up before
the transaction; source hashes and verified load receipts are retained under
`~/.suiteview/backups/rate_manager/whole_life/`. Shared-database write guards
apply to both table creation and loading.

## 📐 Term Rates — Rules That Are Not Obvious

Term rates are stored **pre-compiled**: every (IssueAge, Duration) cell is
materialized into `TERM_RATE_PREM` / `TERM_RATE_BEN` rather than resolved at
quote time. That is why those two tables hold millions of rows (10.7M and 4.0M
across ~47 plancodes), and why the compile step in
[`term_builder.py`](suiteview/ratemanager/workup/term_builder.py) is the heart
of the feature. ABR Quote reads these tables in production — treat them as live.

### Index naming — string identifiers, not numbers

Every `Index(...)` column in the TERM_* tables is **varchar(20)**.

| Table | Index | Form |
|---|---|---|
| `TERM_POINT_PVSRB` → `TERM_RATE_PREM` | `Index(PREM)` | `f"{base + n}_PL"` |
| `TERM_POINT_BENEFIT` → `TERM_RATE_BEN` | `Index(BEN)` | `f"{base + n}_{plan_option}"` |

`n` counts unique (Sex, Rateclass, Band) combos from 1 **and restarts per
suffix**, so `1001_PL` and `1001_30` are different tables, not a collision. The
benefit suffix is the raw 2-character IAF plan_option verbatim and may contain
letters (`3N`, `#0`). Base indexes are free multiples of 1000, so a plancode
owns up to 999 combos.

> ⚠️ `float("1001_30")` returns `100130.0` — Python accepts underscores inside
> numeric literals. Never let an index value reach `float()`/`int()`.

### Maturity comes from ME-AGE, and only caps AGE plans

Read the IAF plan header's **ME-AGE** and its use code (`1` = attained age,
`0` = duration) — *not* PAY-AGE, which is the premium-paying period.
`B155O200` proves the difference: PAY-AGE 020/0 but ME-AGE 095/1.

Apply an **AGE** maturity as a ceiling on attained age. **Never** apply a DUR
maturity — `B155R200` is a 20-year level term (ME-AGE 020/DUR) whose ultimate
rates correctly run to attained age 79. In practice the IAF's own ultimate
table usually runs out first; the cap only truly matters for non-renewable
plans (FIRSTLEVEL ≥ 999), which otherwise have no stopping point at all.

### FIRSTLEVEL / RENLEVEL only bite on compressed data

When the IAF already carries several select durations the level period is baked
in (one duration per policy year) and the user's FIRSTLEVEL/RENLEVEL are
ignored. They apply only to a single compressed select duration. FIRSTLEVEL is
**not** derivable from the IAF — it tracks PAY-AGE for level-term riders but not
for base plans — so it stays a user input.

### Benefit caps are user inputs

`cease_age` and `max_duration` combine as "whichever comes first" (e.g. "level
for 20 years or to age 60"). They are not in the IAF; the retired scripts passed
them ad hoc per run as `--ben-max-age` / `--ben-max-dur`.

### Verifying a change

`tools/rates/term_workup_reference_cases.json` pins seven plancodes covering
every rate shape (single/multi select duration, ART, non-renewable, letter
subtype, dual caps). Run it against the live database — it must report
`all_match: true`, since those rows were loaded by the retired pipeline:

```
venv\Scripts\python.exe tools\rates\verify_term_workup.py @tools\rates\term_workup_reference_cases.json
```

Supporting tools: `inspect_term_iaf.py` (what is in an IAF),
`probe_term_rates_schema.py` (live schema), `check_term_reference.py` (shared
modal-factor/band rows and the next free base index).

### The retired workbook

`Term DB Manager.xlsx` (workspace `..\Term_Rates`) is **not** used by SuiteView.
Its "Index list" allocation, per-plancode settings and reference tables are now
read from, or entered against, the live database. Note its "Band Struct" column
does **not** match `Index(BANDSPEC)` and must not be treated as a source.

## 🎨 ABR Quote — Architecture & Theme

### Overview

ABR Quote is a **3-step wizard** for quoting Accelerated Death Benefits:

| Step | Panel | Purpose |
|------|-------|---------|
| 1. Policy Info | `PolicyPanel` | Enter policy number, load from DB2 |
| 2. Assessment | `AssessmentPanel` | Medical assessment / substandard ratings |
| 3. Output | `OutputPanel` | File management — policy folders + drag-and-drop tools |

**Main window:** `suiteview/abrquote/ui/abr_window.py` (`ABRQuoteWindow`)

### Crimson Slate Theme

ABR Quote uses a **completely different color scheme** from PolView's Blue & Gold.
All ABR-specific colors and stylesheets live in `suiteview/abrquote/ui/abr_styles.py`.

| Alias (kept for compat) | Actual Color | Purpose |
|------------------------|--------------|----------|
| `TEAL_DARK` | `#5C0A14` | Darkest crimson |
| `TEAL_PRIMARY` | `#8B1A2A` | Main crimson |
| `TEAL_RICH` | `#A52535` | Rich crimson |
| `TEAL_LIGHT` | `#C96070` | Light crimson-rose |
| `TEAL_BG` | `#EDD8DA` | Main background |
| `GOLD_PRIMARY` | `#4A6FA5` | Slate-blue accent |
| `GOLD_TEXT` | `#B8D0F0` | Slate-blue text on dark |

> **Important:** The variable names (`TEAL_*`, `GOLD_*`) are kept from the
> original theme for compatibility, but they map to **crimson/slate** colors.
> When working on ABR Quote UI, always import from `abr_styles.py`, never from
> PolView's color constants.

### ABR Quote Database

**Current source:** the shared `UL_Rates` ODBC DSN, through
`suiteview/abrquote/models/abr_database.py` → `get_abr_database()` and
`ABROdbcDatabase`. Premium tables use the `TERM_*` pointer/index architecture;
interest, per diem, state variations and mortality use `SV_ABR_*` tables.
An old local `abr_quote.db`, if present, is historical import material, not the
normal runtime rate source or an automatic live-data fallback.

**Rate Viewer** (`suiteview/abrquote/ui/rate_viewer_dialog.py`):
- Accessible from ABR Quote header menu
- Default view: **ABR Interest Rates** (not Term Rates)
- Editable tables show Add / Edit / Delete buttons
- All tables support Excel-style column filtering and right-click copy/export

**Data import scripts:**
- `tools/rates/import_state_forms.py` — imports `StateForms.xlsx` → `state_forms` table
- Term rates, interest rates, and per diem are imported via bulk insert methods on `ABRDatabase`

### Output Panel (Step 3)

The Output panel provides **file management** for ABR policies, similar to
PolView's Policy Support tab. Layout is **two columns**:

**Left column (stacked):**
1. **Policy Subfolders** (drop target, compact) — rooted at
   `...\Process_Control\Task\Accelerated Death Benefit (ABR11 & ABR14)\Policies\<PolicyNumber>`
2. **Recommended Files** — state-specific election/disclosure forms looked up
   from the `state_forms` table based on the policy's `issue_state`. These
   files are draggable into Policy Subfolders.

**Right column:**
3. **Resources** (drag source, formerly "Available Tools") — rooted at
   `...\Process_Control\Task\Accelerated Death Benefit (ABR11 & ABR14)`

Key features:
- Auto-detects whether the policy folder exists; offers a "Create" button if not
- Drag files from Resources or Recommended Files → Policy Subfolders to copy (prepends policy number)
- Recommended Files queries the `state_forms` DB table and searches for matching
  files under `Forms/ABR Election Forms` and `Forms/ABR Disclosure Forms/ABR14`
- Uses the reusable `MiniExplorer` widget (see Part III)
- Styled with Crimson Slate theme via `_apply_abr_style()` to override MiniExplorer defaults

---

# Part VI — Subsystems

## Local profile storage and cleanup

`~/.suiteview` remains local. `core/profile_paths.py` is the single source of
truth: use `profile_path(name)`, not independent home-directory constructions.
The root separates `settings`, `data`, `auth`, `assets`, `screenshots`, `backups`,
`logs` and `diagnostics`. Saved queries/snapshots live in `data/query`, cases in
`data/illustration`, notes in `data/notes`, and bookmarks in `data/bookmarks.json`.
The mixed-purpose `data/suiteview.db` is not a disposable cache. Its saved
credentials require `auth/.key`; SharePoint's token cache uses Windows DPAPI.

Launchers initialize the layout before importing persistent-state modules.
`core/profile_maintenance.py` moves known data without overwriting conflicts,
verifies file hashes, rewrites moved JSON path references and repairs desktop
icon references. Running real-profile launchers block maintenance. Normal
startup migrates but never opts into deleting old work.
`tools/app/maintain_profile.py --cleanup` previews the reviewed retired items;
`--apply --cleanup` applies only after SuiteView exits. Unknown data is retained.
Tests/tools can isolate storage with absolute `SUITEVIEW_PROFILE_DIR` set before
imports; this does not enable local policy data or alter access permissions.

The retired TaskTracker no longer creates new database tables. Audit retains
widget-state helpers but no unused profile-file API; live picker settings use
`settings/audit_ui_settings.json`. Agent Chat remains disconnected from the
launcher (Albert uses its external bridge). The live registry uses SQL Server,
not the retired local SQLite registry. Backup output remains enabled under
`backups/rate_manager`; developer previews go to `diagnostics`, not the root.
No OneDrive backup or automatic retention/deletion schedule is implied.
See [docs/PROFILE_STORAGE.md](docs/PROFILE_STORAGE.md) for maintenance, recovery
and distribution boundaries. Regression: `tests/test_profile_layout.py`.

## Bookmark Architecture

### BookmarkDataManager (Singleton)
**Location:** `suiteview/ui/widgets/bookmark_data_manager.py`

The **single source of truth** for all bookmark data. All bookmark operations should go through this manager.

```python
from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager

manager = get_bookmark_manager()
```

**Key Methods:**
- `create_bookmark(name, path)` - Creates a bookmark dict with unique ID
- `create_category(name, items=[])` - Creates a category dict with unique ID
- `add_bookmark_to_bar(bar_id, name, path)` - Add bookmark to a bar
- `add_bookmark_to_category_by_name(category_name, name, path)` - Add to category
- `remove_bookmark_by_path(bar_id, path)` - Remove bookmark by path
- `remove_bookmark_from_category_by_name(category_name, path)` - Remove from category
- `find_category_by_name(name)` - Find category anywhere in tree
- `is_path_in_bar(bar_id, path)` - Check if path exists in bar (including categories)
- `get_category_names_in_bar(bar_id)` - Get category names for a bar
- `get_all_category_names()` - Get all category names across all bars
- `save()` - Persist to disk

### BookmarkContainer (UI Widget)
**Location:** `suiteview/ui/widgets/bookmark_widgets.py`

Unified UI widget for displaying bookmark bars. Uses `bar_id` to identify which data to display.

```python
from suiteview.ui.widgets.bookmark_widgets import BookmarkContainer

# Horizontal top bar
bookmark_bar = BookmarkContainer(bar_id=0, orientation='horizontal', parent=self)

# Vertical sidebar
sidebar = BookmarkContainer(bar_id=1, orientation='vertical', parent=self)
```

**Key Methods:**
- `add_bookmark(bookmark_data, insert_at=None)`
- `add_category(category_name, items=None, color=None, insert_at=None)`
- `remove_category(category_name)`
- `rename_category(old_name, new_name)`
- `refresh_bookmarks()` - Rebuild UI from data

**Signals:**
- `item_clicked(path)` - Single click on bookmark
- `item_double_clicked(path)` - Double click on bookmark
- `bookmark_dropped(bookmark_data)` - Bookmark dropped onto container
- `category_dropped(category_data)` - Category dropped onto container

### Bookmark Data Format

**File Location:** `~/.suiteview/data/bookmarks.json`

```json
{
    "next_bar_id": 2,
    "next_item_id": 100,
    "bars": {
        "0": {
            "orientation": "horizontal",
            "items": [
                {"id": 1, "type": "bookmark", "name": "Google", "path": "https://google.com"},
                {"id": 2, "type": "category", "name": "Work", "color": "theme:navy_silver", "items": [
                    {"id": 3, "type": "bookmark", "name": "Jira", "path": "https://jira.example.com"}
                ]}
            ]
        },
        "1": {
            "orientation": "vertical",
            "items": [...]
        }
    }
}
```

**Key Points:**
- **Bar 0** = Horizontal bookmark bar (top)
- **Bar 1** = Vertical sidebar (Quick Links)
- **Categories are items** with nested `items` array (NOT a separate `categories` dict)
- Every item has a unique `id` generated by `BookmarkDataManager.generate_item_id()`
- URLs start with `http://` or `https://`

**❌ DEPRECATED (Do Not Use):** the legacy `categories` dict format
(`{"categories": {...}, "category_colors": {...}}`) is auto-cleaned on load.

### File Responsibilities (Bookmarks)

**`file_explorer_core.py`** — base class with helper methods that delegate to BookmarkDataManager:

| Method | Purpose |
|--------|---------|
| `is_path_in_quick_links(path)` | Check if path in sidebar (bar 1) |
| `add_bookmark_to_quick_links(path)` | Add to sidebar |
| `remove_bookmark_from_quick_links(path)` | Remove from sidebar |
| `add_category_to_quick_links(name)` | Add category to sidebar |
| `remove_category_from_quick_links(name)` | Remove category from sidebar |
| `save_quick_links()` | Calls `_bookmark_manager.save()` |

**`suiteview_taskbar.py`** (in `suiteview/taskbar_launcher/`) uses:
- `self.bookmark_container` - BookmarkContainer for sidebar (bar_id=1)
- `self.bookmark_bar` - BookmarkContainer for top bar (bar_id=0)
- `self._bookmark_manager` - Reference to singleton

### Bookmark Best Practices

✅ **DO** — use `BookmarkDataManager` for data operations, `find_category_by_name`
for lookup, and `is_path_in_bar` for existence checks; always `manager.save()`
after modifications and `container.refresh_bookmarks()` to update the UI.

❌ **DON'T** — access the deprecated `categories` dict, create bookmarks without
IDs, or bypass the manager with a raw `json.dump`.

### URL Bookmark Handling

URLs are detected by prefix and opened in browser:

```python
# In StandaloneBookmarkButton.mouseReleaseEvent (bookmark_widgets.py)
if path.startswith('http://') or path.startswith('https://'):
    import webbrowser
    webbrowser.open(path)
    return
```

## 📦 Distribution Build

SuiteView can be packaged as a distributable **EXE** (ZIP folder) for
coworkers using PyInstaller. See the workflow: `/build-distribution`.

**Build script:** `scripts/build_distribution.py`

Release preflight/build entry point:
`venv\Scripts\python.exe tools\app\build_distribution.py`.
It uses the canonical builder, produces `dist/SuiteView-<version>.zip`, and
verifies the embedded version, required modules, ZIP integrity and every
archived file against the output folder. `--verify-only` rechecks an existing
build. This is a one-folder EXE distribution, not an installer.

**Albert is source-only in 4.0.** Its external Python bridge is not packaged.
The EXE hides its unavailable badge; ADMIN,
AllApps, explicit grants and permission refresh cannot enable it. The shared
build-capability check also rejects direct ALBERT entry before querying access
tables or launching a process. Source/developer access remains unrestricted.

### Versioning (REQUIRED for every release)

Every distribution carries a **version number** so users can tell builds
apart. The version is displayed in the taskbar header (e.g. `SuiteView (2.0)`).

- **Single source of truth:** `suiteview/__init__.py` → `__version__`.
- The taskbar label reads this value, and `build_distribution.py` prints it
  in the build banner.

**Agent workflow — do this EVERY time a distribution is requested:**

1. Read the current version from `suiteview/__init__.py`.
2. Tell the user the **current version** and ask what the **new version**
   should be. Do not build until they confirm.
3. Update `__version__` in `suiteview/__init__.py` to the agreed value.
4. Run the build.

Versions are simple `MAJOR.MINOR` strings (e.g. `2.0`, `2.1`, `3.0`) —
bump MINOR for routine releases, MAJOR for significant changes.

### How to build

```powershell
venv\Scripts\python.exe scripts/build_distribution.py
```

> ⚠️ **You MUST use `venv\Scripts\python.exe`**, not bare `python`.
> The build script internally invokes PyInstaller as a subprocess.
> PyInstaller needs to run under the venv interpreter to discover
> venv-installed packages (PyQt6, sqlalchemy, pyodbc, etc.).

### Key decisions

- Bundle repository-owned reference assets only. Never include a developer's
  personal `.suiteview` database, key, tokens, saved work or screenshots.
- First launch initializes the user's categorized local profile. Existing
  personal data is moved safely; live policy/rate access remains separate.
- **One distribution:** all apps ship in `SuiteView.spec`. Runtime permissions,
  not separate editions or executable filenames, control access.

### Runtime access permissions

`suiteview/core/access_control.py` resolves the current native Windows identity
against live `SV_AccessUser`, `SV_AccessRole` and `SV_AccessRoleApp` in UL_Rates.
Missing/disabled users and missing roles are denied. Connection failures are
explicit errors, never unrestricted or stale-permission fallbacks.

| Rule / helper | Meaning |
|---------------|---------|
| `has_developer_access()` | Source runs are unrestricted; every packaged EXE is checked |
| `guard_app_access(code)` | Recheck enabled user and `AllApps`/whitelist before app entry |
| `is_data_read_only()` | Cached UI state of `CanUpdateDatabase` |
| `guard_data_writable(action)` | Fresh authorization before shared-database mutation |
| `can_write_support_files()` | Cached UI state of `CanWriteSupportFiles` |
| `guard_support_files_writable(action)` | Fresh authorization before policy-support file mutation |

App entry includes taskbar/tray actions, direct constructors and cross-app
handoffs. Administrator and the experimental DB2 Table Check require the ADMIN
role; `AllApps` is not an administrative grant. Write bits are independent of
`AllApps`. Missing grants hide app buttons and Tools/tray entries; direct-entry
guards still enforce authorization. Floating/docked transitions and permission
refresh preserve visibility rules. **Tools > Refresh Permissions** reloads launcher state.
Role changes are checked again on app entry and protected writes; existing
windows are not forcibly closed and unsaved work is not discarded.

Normal startup verifies access before constructing the launcher. UI reads share
a permission snapshot, but app-entry and write guards query live permissions.
Database-write UI gating covers rate/registry editors and arbitrary Manual SQL.
Each actual mutation must also use its guard, even if its UI is disabled.
`core/sql_permissions.py` also guards SQL execution in Audit, DB2 and rate
read helpers: read-only roles may execute a conservative single SELECT/CTE with
recognized built-ins, not batches, SELECT INTO, DML/DDL/EXEC or external/custom
functions. Unsupported SQL fails explicitly rather than being assumed safe.
Arbitrary mutation/batch/EXEC SQL requires both ADMIN and CanUpdateDatabase in
packaged runs. Non-ADMIN database writers retain controlled rate/registry editors
and conservative SELECT/CTE reads; their write bit cannot grant access-table
administration through Manual SQL. SQL Server ACLs must enforce the same separation.
Registry schema initialization is lazy and write-guarded, never an import-time
side effect. UL/Term/WL loaders and ABR save dialogs recheck before mutation.
Personal settings, notes and unsaved Excel exports are not shared-database or
policy-support mutations. SQL Server and filesystem ACLs remain essential;
application permissions do not replace server-side authorization.

Support browsers opt into `MiniExplorer(..., support_files=True)` and guarded
workbook-copy helpers. `core/support_files.py` owns canonical PolView/ABR support
roots and path-aware checks for FileNav paste/drop/cut, rename (including batch),
delete, folder creation and SharePoint downloads. A copy checks its destination;
a move/rename checks both source and destination. Copying out is allowed,
moving/deleting protected content is not. Resolved aliases, root ancestors and
descendants are protected; unrelated personal folders remain writable.
Outlook attachment-save and preview destinations use the same path guard before
directory creation or `SaveAsFile`; ordinary local previews remain available.

Regression: `tests/test_runtime_access.py`, `tests/test_app_entry_access.py`,
`tests/test_support_file_access.py`, `tests/test_filenav_support_access.py`,
`tests/test_database_write_permissions.py`, `tests/test_audit_rate_app_access.py`.
`tests/test_read_only_generated_sql.py` checks real PolicyInformation, rates,
ABR viewer and Audit-generated queries under restricted permissions.
Native verification: `tools/app/verify_runtime_access.py --output-dir <directory>`
uses synthetic roles and an isolated temporary profile, checks hidden launcher
controls, denied direct entry, permission refresh and FileNav without ScratchPad.
`tools/admin/verify_access_repository.py --runtime` verifies the real packaged
authorization query read-only, even when the helper runs from source.

### Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `No module named 'PyQt6'` at EXE runtime | Build script was run with system Python instead of venv Python | Run with `venv\Scripts\python.exe scripts/build_distribution.py` |

The build script has a safeguard: it auto-detects `venv/Scripts/python.exe`
and uses it for the PyInstaller subprocess even if the script itself was
launched with the system Python. But to be safe, **always launch with the
venv interpreter**.

## Testing

### Layering guard

SuiteView imports are ordered from lower-level infrastructure to shell:

`core` → `data` → domain models (`*/models`, `polview/data`) → engines/services
(`illustration/core`, `polview/services`, app logic) → shared UI (`suiteview/ui`)
→ app UIs/windows (`*/ui`, Audit, RateManager, Mainframe, Administrator, etc.)
→ shell/startup (`taskbar_launcher`, `suiteview.startup`, `suiteview.main`).

Lower layers must not import higher layers. `tests/test_layering.py` parses
module-level and function-level imports and fails on new upward imports. Existing
exceptions are documented in that test with a removal reason; the allowlist may
only shrink.

### SuiteView access-control tables and Administrator

`tools/admin/create_access_control.py` provisions `dbo.SV_AccessRole`,
`dbo.SV_AccessRoleApp` and `dbo.SV_AccessUser` in live `UL_Rates`.
Default invocation previews the initial seed offline; `--check` compares live
rows read-only; `--apply` creates/seeds the three tables in one transaction and
verifies every value after reconnecting. It never overwrites existing tables or
permissions; later administrative edits intentionally make the seed check fail.
Regression: `tests/test_access_control_setup.py`.

Roles carry `AllApps`, `CanUpdateDatabase`, `CanWriteSupportFiles`, and
`Description`; users carry network ID, display-only `Name`, `Enabled`, and one
role. ADMIN includes current/future apps without whitelist rows; other roles use
explicit app codes in `SV_AccessRoleApp`. Permission bits default off.
Administrator checkboxes reuse the Query tool's `audit/tabs/_styles.make_checkbox`
factory (square blue indicators with white checkmarks), including app grants.
The **Administrator** app (`suiteview/administrator/window.py`) uses the shared
frameless blue/gold frame, compact `FilterTableView` grids, and Users / Roles &
Apps editors. In packaged builds, Tools > Administrator is shown only after an enabled ADMIN check;
ADMINISTRATOR is not an app-whitelist grant. `AllApps` or database-write permission
alone never grants administration. Native Windows `GetUserName()` supplies the
network ID, not a user-editable field or an environment variable.

**Source developer access is independent of the access tables.**
`core/build_env.py` owns `has_developer_access()`: ordinary source runs bypass
role/user restrictions, including a missing, disabled or non-ADMIN user record.
The Administrator menu is immediately available without an identity/database
probe, and its status reads **Developer access (source)** rather than claiming
stored ADMIN membership. No hard-coded developer ID or environment-variable
grant is used; a packaged EXE never receives this bypass. Runtime access checks
honor this shared helper before querying access tables.
It does not grant Windows/SQL Server credentials,
hide connection/schema errors, or bypass data-integrity safeguards.

`administrator/service.py` checks source developer access or reauthorizes each
packaged read/write against live UL_Rates.
Writes use parameterized SQL, shared transaction lock ordering, optimistic
original-value checks, and atomic role-plus-whitelist saves. Keep at least one
enabled ADMIN; ADMIN cannot be deleted, nor can a role assigned to any user
(including disabled users). Existing keys cannot be renamed. Unknown existing
app codes are preserved, but unknown new grants are rejected. AllApps ignores
the explicit whitelist without deleting it.

**Permissions are enforced at runtime across the packaged suite.**
Source developer access is unaffected by table edits. SQL Server grants are not changed:
database-update permission must
never imply permission to edit access-control tables, and SQL Server must
protect these tables from direct external writes separately.

Regression: `tests/test_runtime_access.py`, `tests/test_administrator_service.py`,
`tests/test_administrator_launcher.py`, `tests/test_administrator_ui.py`.
`tools/admin/verify_access_repository.py` checks native identity and live table
loading read-only. `tools/admin/verify_access_crud.py` exercises real SQL Server
CRUD, conflicts and rollback using connection-local temporary tables and checks
the live tables remain unchanged. `tools/app/verify_administrator.py` captures
the native UI with synthetic data; no live access rows are changed.

Run the test suite:
```powershell
venv\Scripts\python.exe -m pytest tests/ -v
```

Run the file explorer to test bookmark functionality:
```powershell
venv\Scripts\python.exe scripts/run_file_explorer_multitab.py
```

Check bookmark data:
```powershell
Get-Content "$env:USERPROFILE\.suiteview\data\bookmarks.json" | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

---

*This file should be updated at the end of each session to help the next agent
continue the work.*
