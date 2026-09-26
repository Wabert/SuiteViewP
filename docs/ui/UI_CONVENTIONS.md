# UI conventions and shared widgets

Detailed SuiteView UI conventions live here. `Agent.md` keeps the short rules; this file keeps the component-level contracts.

> Source: moved from the former long-form `Agent.md` so that the canonical standards file can stay concise.


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
  [`suiteview/ui/widgets/window_state.py`](../../suiteview/ui/widgets/window_state.py)
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
[`suiteview/taskbar_launcher/appbar.py`](../../suiteview/taskbar_launcher/appbar.py).
Never re-declare `APPBARDATA` / `SHAppBarMessage` calls elsewhere.

**AppBar exception to the frameless-window standard.** The compact taskbar is a
Windows shell AppBar, not a normal `FramelessWindowBase` window. It may use
manual resize grips and direct `setGeometry()` calls while docking, floating or
negotiating work-area space with the shell. Keep those calls inside the
taskbar mode/system collaborators and `appbar.py`; other windows should keep
using shared frameless/window-state helpers.

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
