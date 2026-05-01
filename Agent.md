# Agent.md — Design Choices & Architecture Notes

## UI Component Reuse

### FilterTableView as Standard Table Widget
**Decision (2026-04-18):** All tabular data views should use `FilterTableView` (`suiteview/ui/widgets/filter_table_view.py`) rather than ad-hoc `QTableWidget` implementations.

**Rationale:**
- Provides consistent look-and-feel across the app (compact rows, column filters, sort arrows)
- Built on Model/View architecture (`QTableView` + `PandasTableModel`) — more performant and scalable than `QTableWidget`
- Includes built-in features: column header filter popups, global search, sort toggling, column reordering
- Eliminates duplicated row-height / delegate / stylesheet boilerplate

**Applied to:**
- `SavedQueriesShelf` (`suiteview/audit/ui/saved_queries_shelf.py`) — converted from `QTableWidget` to `FilterTableView`
- `ResultsTab`, `BuildSqlResultsTab`, `TablesDialog` — already use `FilterTableView`

**Pattern:** Wrap `FilterTableView` in a parent widget, call `set_dataframe(df)` with a pandas DataFrame, and configure column resize modes on the horizontal header after loading data.

### Compact Table Shorthand
When configuring a `FilterTableView` for a compact panel, use this recipe:

> FilterTableView, compact: 16px fixed rows, 18px header, no grid/alternating/row numbers, white background, zero-padding items, autofit columns then stretch the name column. Auto-size panel width to fit all columns.

---

## Table Aesthetic — General Guidance

The target aesthetic for all data tables is a **dense, information-first data grid with no visual noise**:

- **Rows feel like a spreadsheet, not a list.** Text-tight — no extra padding, margin, or whitespace between rows.
- **Minimize chrome:** No gridlines, no row numbers, no alternating row colors. White background.
- **Columns autofit to content.** The primary/name column stretches to fill remaining space. The table/panel should size itself so all columns are visible without horizontal scrolling.
- **Headers are compact and understated** — smaller font, minimal height, no heavy borders.
- **Column sorting and filtering are expected by default.** Click a header to sort; click a filter icon/area to get a checklist filter popup per column. These should be toggleable parameters (e.g. `sortable=True`, `filterable=True`) so callers can opt out for simple tables.
- **Selection is subtle** — light highlight, no bold focus rectangles.

This applies regardless of framework or widget. The goal is maximum data density with padding or marge.

---

## Custom Window Frame

All SuiteView windows use a **frameless custom window frame** — no native OS title bar. Every top-level window subclasses `FramelessWindowBase` (`suiteview/ui/widgets/frameless_window.py`).

### The Look
- **Frameless** — `Qt.FramelessWindowHint`. No native chrome.
- **Header bar** — fixed 38px tall with a diagonal 3-stop linear gradient (dark left → darker right). Title text is white, bold italic, 18px.
- **Gold border** — 2px painted border around the entire window (default `#D4A017`).
- **Control buttons** — minimize (`–`), maximize/restore (`□`/`❏`), close (`✕`) as Unicode glyphs in the header. Text color matches the border color. Close button goes red on hover.

### Behavior
- Drag-to-move on the header bar. Double-click header to maximize/restore.
- 8-edge resize handles. Snap-to-edge (left/right half-screen) with translucent preview.
- De-maximize on drag — dragging from maximized restores to normal size.

### Theme
Each module can override `header_colors` (3-stop gradient) and `border_color` to brand its windows:

| Module | Header Gradient | Border |
|---|---|---|
| Default / Audit / RateManager | Blue `#1E5BA8 → #0D3A7A → #082B5C` | Gold `#D4A017` |
| PolView | Green `#0A3D0A → #1B5E20 → #2E7D32` | Gold `#D4A017` |
| ABR Quote | Crimson `#5C0A14 → #8B1A2A → #A52535` | Slate `#4A6FA5` |

### Pattern
Subclass `FramelessWindowBase`, override `build_content() → QWidget` to provide the body. Pass `title`, `default_size`, `header_colors`, `border_color`, and optional `header_widgets` (extra widgets placed in the title bar).

---

## Excel Export Convention — "Dump to Excel"

**Decision:** All "Excel" / "Export" buttons in SuiteView open a **new unsaved workbook** in a visible Excel instance via COM automation (`win32com.client`). They do **not** save a file to disk.

**Rationale:** The common use case is quick visual inspection of data in Excel and then discarding it. Forcing a Save-As dialog adds friction. The user can save the workbook themselves if they want to keep it.

**Pattern:**
```python
import win32com.client
xl = win32com.client.Dispatch("Excel.Application")
xl.Visible = True
wb = xl.Workbooks.Add()
ws = wb.ActiveSheet
# Write headers in row 1, data starting at row 2 (bulk Range.Value assignment)
# Autofit columns, bold headers
```

**Key details:**
- Use `Dispatch("Excel.Application")` — connects to an existing instance or starts a new one.
- Write data in bulk via `ws.Range(...).Value = list_of_lists` for performance.
- Convert non-primitive types (datetime, Decimal, etc.) to `str` before writing to avoid COM type errors.
- Set `ws.Name` to something meaningful (max 31 chars — Excel sheet name limit).
- Do **not** call `wb.SaveAs()` — leave the workbook unsaved.

---

## Data Abstraction — Query Design / Query Definition / Data Snapshot

- **Query Design** — A reusable, parameterized template that defines the structure of a query (tables, joins, columns) while leaving specific filter values and inputs to be supplied at execution time.

- **Query Definition** — A fully-specified, executable query that captures the exact SQL, bound parameter values, target database, connection, and expected result schema (field names and types), produced by applying specific inputs to a Query Design.

- **Data Snapshot** — The materialized rows and columns of data returned by executing a Query Definition at a specific point in time.
