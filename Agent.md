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
  saves it to `~/.suiteview/screenshot.png`. Then use `view_file` to inspect
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
- **Regression check:**
  `venv\Scripts\python.exe tools/app/test_taskbar_tray_cycle.py` drives the real
  taskbar through launch → hide → refresh-while-hidden → show → redundant
  register and asserts the work area is reserved exactly when the bar is
  visible. It must report `all_ok: true`.

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
| `data_item_where(table, return_field, filter_field, filter_value)` | Filtered single value |
| `data_items_where(table, return_field, filter_field, filter_value)` | All matching values |

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
| **Cyberlife Query / Audit** | [`docs/audit/Audit_Criteria_Input_Types.md`](docs/audit/Audit_Criteria_Input_Types.md) | **52 Segment** page: eleven application/conversion fields from `TH_USER_GENERIC`, with ranges/text criteria and optional display. **Latest SC conversion dates (69)**: `LST_ETR_CD='O'`, both reversal flags zero, one `FH_FIXED` row ordered by `ENTRY_DT`, `ENTRY_TIME`, `SEQ_NO` descending. Live-verified: financial history has no `CK_SYS_CD`, and its time field is `ENTRY_TIME` (not the older workbook's `TIME`). |

> **To add a new sub-app doc:** create `docs/<APPNAME>_CLAUDE.md`, add a row to
> the table above, keep shared concerns (DB2, PolicyInformation) in this file,
> and keep app-specific detail (UI, VBA mappings, business rules) in the sub-app
> doc.

## PolView coverage zero values

Coverage and benefit numeric zero values must remain distinct from missing data
through `PolicyInformation` and the Coverages tab. Zero units/VPU, premiums,
flat extras, benefit ratings and issue ages display as zero, not blank.
See `docs/POLVIEW_CLAUDE.md` for regression tests and the read-only UL054808
verification helper.

## PolView Policy Record segments 55 and 57

The Policy Record viewer shows **only segments with policy data**, using the
canonical record/table mapping through `PolicyInformation`. A populated segment
without a supported screen keeps its tab but shows only "This screen cannot be
reproduced in PolView at this time." No policy, absent segments and loading
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
(1/3/2 characters), plus policy company and coverage issue age. Select only the
blank `USER_DEFINED` variant unless its mapping is explicitly known; never
fall back to another company or variant. Keep duration zero and source duration
labels intact. NSP/PUI/dividend lookups in this view remain future work.
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
`~/.suiteview/rate_manager_backups/whole_life/`. Shared-database write guards
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

**Location:** `~/.suiteview/abr_quote.db` (SQLite)
**Manager:** `suiteview/abrquote/models/abr_database.py` → `ABRDatabase`
**Singleton:** `get_abr_database()` — auto-creates schema on first access.

| Table | Purpose | PK | Editable in Rate Viewer |
|-------|---------|----|-----------------------|
| `term_rates` | Base term premium rates (28K+ rows) | `key` (composite text) | No |
| `interest_rates` | Monthly ABR interest rates | `date` (YYYY-MM) | Yes |
| `per_diem` | Annual per diem limits | `year` (integer) | Yes |
| `state_forms` | Election/disclosure form filenames per state | `state_abbr` | Yes |
| `import_metadata` | Tracks when data was last imported | `table_name` | No |

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

**File Location:** `~/.suiteview/bookmarks.json`

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

- **PolView and ABR Quote** databases are always included (bundled from
  `~/.suiteview/` into the exe's data directory).
- On first launch, `_install_bundled_abr_db()` copies the bundled DB to
  the user's `~/.suiteview/` if it doesn't exist.
- **Developer-only tools** are stripped from the Tools menu in distribution
  builds. Rate Manager is included in the full SuiteView distribution but not
  SuiteView Light.

### SuiteViewLight — the read-only edition

`SuiteViewLight` (`python scripts/build_distribution.py --light`, spec
`SuiteViewLight.spec`) is a trimmed, **read-only** edition for the business area.

- **Included:** PolView, FileNav, ABR Quote, and the **Audit / Query Tool**
  (read-only), plus View Screenshots and App Data Location.
- **Excluded:** LLM Agent (`copilot`, `markdown`), Rate Manager, Mainframe
  Navigator, ScratchPad, Email Attachments, RERUN illustration.
- **Read-only against the shared UL_Rates SQL Server database.** Light must
  never modify shared data — the ABR Rate Viewer's Add/Edit/Delete bar is
  hidden, the Audit "Find & Register Unique Values" actions are hidden, and the
  Unique Value Registry window is view-only (no edit-in-window, non-editable
  cells, no delete).
- **No arbitrary hand-written SQL.** The Audit **Manual SQL build mode** and the
  SQL tab's **"Move to Build"** button are removed in Light (both open an
  editable, runnable SQL surface). This covers the build-mode menu, the New
  Query Object dialog, the source dashboard's New Query menu, and reopening a
  saved Manual SQL object. Gated on `is_light_build()`.

**How the switch works — single source of truth in
[`suiteview/core/build_env.py`](suiteview/core/build_env.py):**

| Function | Meaning |
|----------|---------|
| `is_light_build()` | True in the `SuiteViewLight.exe`, or when `SUITEVIEW_LIGHT=1` (run/test Light from source) |
| `is_data_read_only()` | Gate every shared-DB write on this (currently == `is_light_build()`) |
| `guard_data_writable(action)` | Raises `ReadOnlyDataError` — the last-line safety net beneath the UI gating |

**Enforcement is defense-in-depth:** the UI hides/disables write controls
(taskbar `LIGHT_MODE`, ABR rate viewer, audit field menus, registry window)
**and** the write layers guard themselves — `audit/shared_field_registry.py`
(ABATBL_* registry) and `abrquote/ui/rate_viewer_dialog.py` (SV_ABR_* rate
tables) both refuse writes when `is_data_read_only()`. When you add a new
write path against the shared database, call `guard_data_writable()` at the top
and gate its UI on `not is_data_read_only()`.

### Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `No module named 'PyQt6'` at EXE runtime | Build script was run with system Python instead of venv Python | Run with `venv\Scripts\python.exe scripts/build_distribution.py` |

The build script has a safeguard: it auto-detects `venv/Scripts/python.exe`
and uses it for the PyInstaller subprocess even if the script itself was
launched with the system Python. But to be safe, **always launch with the
venv interpreter**.

## Testing

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
Get-Content "$env:USERPROFILE\.suiteview\bookmarks.json" | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

---

*This file should be updated at the end of each session to help the next agent
continue the work.*
