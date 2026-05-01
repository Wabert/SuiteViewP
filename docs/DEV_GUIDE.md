# SuiteView Development Guide

This document outlines UI design principles for SuiteView development.

## Development Status

**This project is in active development only - there is no production deployment.**

Guidelines:
- **No backward compatibility needed** - we can freely change data formats, APIs, and structures
- **No migration code** - when formats change, just update the code directly
- **Remove legacy code** - delete code we've moved past rather than keeping it "just in case"
- **Clean as we go** - keep the codebase lean and focused on current functionality

## UI Design Principles

### Performance First
- **Fast & responsive UI** is the top priority - minimize latency on all interactions
- Use async loading, database caching, and deferred operations to keep UI snappy
- Avoid blocking operations on the main thread

### Layout & Spacing
- Compact, space-efficient layouts preferred throughout the application
- Tight padding on menu items and buttons
- Minimal whitespace while maintaining readability

### Table Styling Preferences
- **No alternating row colors** — all table rows should have a uniform white background. Do not use `setAlternatingRowColors(True)` or `QTableWidget::item:alternate` styles.
- **Compact rows** — use small row heights (16–18px default section size) and minimal cell padding (`0px 4px`) to fit more data on screen.
- **No visible grid lines** — use `gridline-color: transparent` for a cleaner look; let spacing/borders provide visual separation.

### Compact QListWidget (Tight Row Spacing)

Qt's `QListWidget` has internal row padding that **cannot be removed via stylesheet alone** — even `padding: 0px; margin: 0px` on `::item` leaves significant gaps because Qt computes row height from font metrics plus an internal constant.

**The fix: use a `QStyledItemDelegate` to override `sizeHint`.**

```python
from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtCore import QSize

class _TightItemDelegate(QStyledItemDelegate):
    """Forces a fixed compact row height on QListWidget items."""
    ROW_H = 16  # pixels — adjust if font size changes

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(sh.width(), self.ROW_H)
```

Apply it alongside `setUniformItemSizes(True)` and a zero-padding stylesheet:

```python
MY_LIST_STYLE = """
    QListWidget {
        font-size: 11px;
        border: none;
        background-color: white;
        outline: none;
        padding: 0px;
        margin: 0px;
    }
    QListWidget::item {
        padding: 0px 4px;
        margin: 0px;
        border: none;
        min-height: 0px;
    }
    QListWidget::item:hover   { background-color: <GREEN_SUBTLE>; }
    QListWidget::item:selected { background-color: <GOLD_LIGHT>; font-weight: bold; }
"""

list_widget = QListWidget()
list_widget.setStyleSheet(MY_LIST_STYLE)
list_widget.setItemDelegate(_TightItemDelegate(list_widget))
list_widget.setUniformItemSizes(True)
```

> **Note:** `ROW_H = 16` works well for 11px font. Increase to 18 for 12px font.

### Styled Context Menus

To distinguish right-click context menus from the main window (which uses the OS default), apply a stylesheet directly to the `QMenu` instance:

```python
CONTEXT_MENU_STYLE = f"""
    QMenu {{
        background-color: #F0F0F0;
        border: 1px solid {GRAY_DARK};
        padding: 2px;
        font-size: 11px;
    }}
    QMenu::item {{
        padding: 3px 20px 3px 8px;
        color: #1a1a1a;
    }}
    QMenu::item:selected {{
        background-color: {GOLD_LIGHT};
        color: {GREEN_DARK};
    }}
    QMenu::item:disabled {{ color: #999999; }}
    QMenu::separator {{
        height: 1px;
        background: {GRAY_MID};
        margin: 2px 4px;
    }}
"""

menu = QMenu(self)
menu.setStyleSheet(CONTEXT_MENU_STYLE)
menu.addAction("Do something...")
menu.exec(widget.viewport().mapToGlobal(pos))
```

> Apply the style **per-instance** (not globally) so it only affects right-click menus, not the main menu bar.


### Power-User Layout Preference (Audit Tool & Similar)
- **Everything always visible** — never hide sections behind checkboxes or collapsible toggles. All filter options, list boxes, and inputs should be visible at all times so users can see what's available at a glance.
- **Checkboxes enable/disable, not show/hide** — checkbox toggles on group boxes should grey-out (disable) the section contents, not collapse or hide them. The user should always know what options exist.
- **Maximize horizontal space** — use side-by-side layouts to show more list boxes and inputs without excessive vertical scrolling. Audit-style tools should feel dense and information-rich.
- **No progressive disclosure** — power users need to see all options readily available. Don't require clicks to reveal functionality.
- **Neat and tidy** — while showing everything, keep layouts organized with clear grouping (group boxes with themed borders), consistent alignment, and logical ordering.

### Not-Applicable Sections (IMPORTANT UI Preference)
When a section of a tab is **not applicable** for the current data/product type:

- ✅ **Keep the section visible** — do NOT hide it with `setVisible(False)`
- ✅ **Match the window background** — use `BLUE_BG` (`#C8E6C9`) as the interior color
- ✅ **Same border and title** — keep the group box border and title label identical to the active state
- ✅ **Show a centered note** — display *"Not applicable for this product"* as italic grey text; nothing else
- ❌ **Do NOT leave a white background** when a section is inactive — blank white looks broken
- ❌ **Do NOT dim/disable or overlay** the widget — that looks wrong and can bleed onto adjacent widgets

**Implementation pattern** (dual-widget approach in `targets_tab.py`):
```python
class MyWidget(QWidget):
    def _build_ui(self):
        outer = QVBoxLayout(self)

        # Active view: StyledInfoTableGroup with fields + table
        self._active = StyledInfoTableGroup("Section Title", columns=1)
        self._active.add_field(...)
        self._active.setup_table([...])

        # N/A view: same title, green interior, centered label only
        self._na = StyledInfoTableGroup("Section Title", columns=1, show_table=False)
        na_content = _NaContentWidget(self._na)   # green bg + italic label
        self._na.layout().addWidget(na_content)
        self._na.hide()

        outer.addWidget(self._active)
        outer.addWidget(self._na)

    def set_not_applicable(self, na: bool):
        self._active.setVisible(not na)
        self._na.setVisible(na)
```
`_NaContentWidget` is a simple `QWidget` with `background-color: BLUE_BG` and a
centered `QLabel("Not applicable for this product")` in italic grey.

### Visual Design

#### Design Philosophy: Modern Skeuomorphism

SuiteView embraces **skeuomorphic design** — making digital UI elements mimic physical objects with depth, shadows, highlights, and tactile qualities. While flat design dominated for years, this approach provides:

- **Visual hierarchy** — Raised elements naturally draw the eye and indicate interactivity
- **Tactile feedback** — Buttons that look "pressable" feel more satisfying to click
- **Professional polish** — Subtle 3D effects signal quality and attention to detail
- **Intuitive affordances** — Users instinctively understand what's clickable vs. static

**Our interpretation:**
- Not full iOS 6-era heavy textures, but **subtle depth cues**
- Gradient backgrounds that simulate light sources
- Beveled borders that create raised/inset appearances
- Contrasting accent borders (gold on blue/green) for definition
- Rounded corners that soften the look while maintaining structure

**Key techniques:**
1. **Beveling/Embossing** — Vertical gradients (light→dark) simulate overhead lighting
2. **Border highlights** — Lighter top/left borders, darker bottom/right borders
3. **Pressed states** — Invert gradients to simulate depression
4. **Drop shadows** — Subtle shadows to lift elements off the background
5. **Accent borders** — High-contrast borders (gold, coral) create visual pop

This philosophy applies to: headers, footers, buttons, category pills, panel frames, and any interactive element that benefits from looking "touchable."

#### Core Visual Elements
- **Rounded corners** on buttons, panels, and popups for a modern, friendly look
- **3D/dimensional effects** (gradients, subtle shadows, beveled borders) to draw attention to key controls
- Panel headers should have depth/dimension to stand out from content areas
- Styled message boxes and dialogs matching the app theme (not default OS style)

#### Beveling / Embossing Technique

A signature SuiteView design element is **beveled headers and footers** that simulate a 3D raised surface. This gives UI elements a high-end, polished feel.

**How it works:**
- Use a vertical gradient (lighter at top → darker at bottom) to simulate light from above
- Accent with a contrasting border color (e.g., gold on green) for definition
- The "pressed" state inverts the gradient to simulate depth

**Example: Green header with gold border (Policy List panel)**
```python
header.setStyleSheet(f"""
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2E7D32,    /* lighter green at top (light source) */
        stop:1 #1B5E20);   /* darker green at bottom (shadow) */
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
""")
```

**Example: Blue header with gold accents (TaskTracker)**
```python
header.setStyleSheet(f"""
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {C.BLUE},       /* #1A3A7A - lighter blue */
        stop:1 {C.BLUE_LIGHT}); /* #2A5AAA - can go darker for more depth */
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
""")
```

**Key principles:**
1. **Light source consistency** - Always assume light comes from top/top-left
2. **Gradient direction** - Use `x1:0, y1:0, x2:0, y2:1` for vertical (most common)
3. **Color delta** - The darker stop should be ~30-40% darker than the lighter stop
4. **Border contrast** - Gold (`#D4A017`) on blue/green creates visual pop
5. **Corner radius** - Match the parent container's radius (typically 12px)

**Footer variation (recessed/inset look):**
For footers, you can reverse the gradient (darker at top) to create an "inset" appearance that grounds the panel visually.

This technique is used on:
- `DockableToolPanel` headers (Policy List, TaskTracker Details)
- `FramelessWindowBase` title bars
- Category buttons in bookmark widgets (themed styles)

### Color Scheme
- Primary theme: Royal blue & gold
- Context menu borders: Blue (`#0078d4`) for item menus
- Category menus: Dynamic color matching the category's assigned color (darkened)

### Application Personality & Messaging Style

SuiteView should feel **friendly, approachable, and occasionally witty** - like a helpful coworker who happens to be really good with computers.

**Guidelines:**
- **Lighthearted over corporate** - Avoid stiff, formal language. "Oops! Something went wrong" beats "An error has occurred"
- **Explain tech in plain English** - When users encounter technical concepts, translate them into everyday terms with a touch of humor
- **Celebrate small wins** - "Nice! All done." feels better than "Operation completed successfully"
- **Self-aware humor** - The app can poke fun at itself or technical jargon (within reason)
- **Helpful, not sarcastic** - Keep humor warm and inclusive, never condescending

**Examples:**
| Instead of... | Try... |
|---------------|--------|
| "Connection failed" | "Couldn't reach the server. It might be napping 💤" |
| "Service unavailable" | "The AI is having a coffee break. Try again in a moment!" |
| "Authentication required" | "We need to borrow VS Code's brain for this one" |
| "Loading..." | "Thinking really hard..." or "Crunching numbers..." |
| "No results found" | "Came up empty! Try a different search?" |

**When to dial it back:**
- Error messages that could cause data loss should be clear first, friendly second
- Don't joke about serious operations (deleting data, security warnings)
- Keep critical confirmation dialogs straightforward

## Code Organization

### File Structure Philosophy
- **Prefer fewer, larger files** over many small files
- Group related classes together in single files (e.g., all bookmark-related widgets in one file)
- A file with multiple related classes is easier to navigate than jumping between many small files
- Use clear section comments (`# ===== Section Name =====`) to organize within large files

### Naming Conventions
- **Be consistent with terminology** - pick one term and use it everywhere
- Avoid synonyms that mean the same thing (e.g., don't mix "Quick Links" and "Bookmarks")
- Class names should clearly indicate their purpose
- Use `_private_method` naming for internal methods

### Module Organization
```
suiteview/
├── core/           # Business logic, data access, external integrations
├── data/           # Database and data models
├── models/         # Data structures and types
├── ui/
│   ├── dialogs/    # Modal dialogs and popups
│   └── widgets/    # Reusable UI components (can be large files with related classes)
└── utils/          # Shared utilities
```

### Example: Bookmark Widgets
All bookmark-related UI classes live in `bookmark_widgets.py`:
- `BookmarkDataManager` - Data storage singleton
- `BookmarkContainerRegistry` - Cross-bar communication
- `BookmarkContainer` - Main container widget
- `CategoryButton`, `CategoryPopup` - Category UI
- `StandaloneBookmarkButton`, `CategoryBookmarkButton` - Bookmark buttons
- Style constants, color utilities, icon caching

This keeps related code together and makes it easy to understand the full bookmark system.

---

## PolView UI Reference

*Merged from PolView/DEV_GUIDE.md — PolView-specific UI/UX guidelines and component details.*

### PolView Color Scheme
- **Primary Blue**: `#1565C0` (BLUE_RICH) - Main headers, borders
- **Dark Blue**: `#0D47A1` (BLUE_DARK) - Gradient tops, text
- **Light Blue**: `#BBDEFB` (BLUE_BG) - Backgrounds
- **Gold Primary**: `#FFC107` (GOLD_PRIMARY) - Accents, borders
- **Gold Text**: `#FFD54F` (GOLD_TEXT) - Text on dark backgrounds

### PolView Layout Principles

#### Field Spacing (IMPORTANT)
- **Pack fields to the top** of containers with consistent spacing
- **Pack fields to the left** within their container - do not distribute horizontally to fill space
- **Do NOT spread fields** evenly to fill container height or width
- White space at the right and bottom of containers is acceptable and preferred over even distribution
- Use `addStretch(1)` at the end of layouts to push content to top/left

#### Horizontal Layout Preference
When laying out label/value pairs or info fields:
- **Do NOT** evenly distribute items across available width
- Items should be placed as close together as their defined spacing allows
- Extra space goes to the right (or a stretch column), not between items
- Only use even distribution if explicitly requested by the user

For `QGridLayout` info sections, add a stretch column at the end:
```python
# Pack fields left by adding stretch to the last column
self._info_layout.setColumnStretch(self._columns * 2, 1)
```

#### StyledInfoTableGroup Usage
When using `StyledInfoTableGroup` with `show_table=False` (info-only mode):
- Fields automatically pack to the top and left
- Consistent 2px vertical spacing between rows
- 8px horizontal spacing between label/value pairs
- Extra horizontal space goes to the right (not distributed between fields)

Example:
```python
# Info-only widget with fields packed to top
widget = StyledInfoTableGroup("Title", columns=1, show_info=True, show_table=False)
widget.add_field("Label", "attr_name", 110, 120)
# Fields will be at top with whitespace below
```

### Tooltip System

#### Overview
Field labels can have clickable tooltips that display help text when clicked.
Tooltip text is stored in `config/field_tooltips.json` for easy maintenance.

#### Adding Tooltips to Fields
Use the `tooltip_section` and `tooltip_key` parameters in `add_field()`:

```python
# Add field with tooltip from JSON file
widget.add_field("Total AV", "total_av", 100, 80, 
                 tooltip_section="AdvProdValues", 
                 tooltip_key="total_av")
```

#### Tooltip JSON Structure
The `config/field_tooltips.json` file is organized by sections:

```json
{
  "AdvProdValues": {
    "total_av": {
      "label": "Total AV",
      "tooltip": "Total Account Value - The sum of all fund values..."
    }
  },
  "MonthliversaryValues": {
    "eff_date": {
      "label": "Eff Date",
      "tooltip": "Effective Date - The monthliversary date..."
    }
  }
}
```

#### ClickableTooltipLabel
Labels with tooltips:
- Display with underline to indicate clickability
- Show cursor change on hover
- Display tooltip popup on left-click
- Support right-click menu with "Show Info" option

#### TooltipManager
Singleton class that loads and provides tooltip text:

```python
from ui.main_window import get_tooltip_manager

# Get tooltip text
tip = get_tooltip_manager().get_tooltip("AdvProdValues", "total_av")

# Reload tooltips (for maintenance screen)
get_tooltip_manager().reload()
```

### PolView Tab Design

#### PolicyTab Layout
- Three columns: Policy Information, Billing & Valuation, Marketing & Loan
- No header section (removed per user preference)
- Policy Number, Company, and Plancode shown at top of Policy Information column
- All columns pack fields to top with consistent spacing

#### AdvProdValuesTab Layout
Five sections matching VBA SuiteView:
1. **Policy Info** (left) - Info fields with clickable tooltips
2. **Monthliversary Values** (center) - Table with MV history
3. **Fund Value History** (right top) - Bucket detail table
4. **Unimpaired Fund Values** (right middle) - Fund summary
5. **Impaired Fund Values** (right bottom) - Loan collateral

#### PersonsTab Layout
Single transposed table showing person data:
- **Columns**: Data Type, Person 1, Person 2, Person 3, ... (based on NUM_PERS)
- **Rows**: SSN, First Name, Last Name, Middle Initial, Sex, Birth Date, Age
- Uses PERSON_CODES dictionary to translate person type codes to labels

#### ActivityTab Layout
Two-panel horizontal layout:
1. **Transaction Type Index** (left, 320px fixed width):
   - Uses StyledInfoTableGroup (table-only mode)
   - Single column table with header "Transaction Type"
   - Uses TRANSACTION_CODES dictionary (from VBA TransactionTypeAndSubtypeDictionary)
   - Sorted alphabetically by code
   
2. **Policy Transactions (FH_FIXED)** (right, fills remaining space):
   - Uses StyledInfoTableGroup (table-only mode)
   - Table with FH_FIXED data
   - Columns: Eff Date, SeqNo, Code, Gross Amt, Net Amt, Fund, Phs, Int Rate, Reversal, Entry Date, Origin
   - Reversal indicator logic: "Rev" if RevInd=1, "RV" if RevApplied=1, "RR" if both
   - Sorted by ASOF_DT DESC, SEQ_NO DESC

### PolView Translation Functions
All code lookups use translation dictionaries matching VBA mdlDataItemSupport.bas:
- STATE_CODES: Cyberlife state codes (1-66) → state abbreviations
- DIV_OPTIONS: Dividend option codes → descriptions
- NFO_OPTIONS: Non-forfeiture option codes → descriptions
- BILL_FORM_CODES: Billing form codes → descriptions
- ENTRY_CODES: Original entry codes → descriptions
- LAST_ENTRY_CODES: Last entry codes → descriptions
- MEC_STATUS: MEC status codes → descriptions
- LOAN_TYPES: Loan type codes → descriptions
- REINSURANCE_CODES: Reinsurance codes → descriptions

### PolView Data Sources

#### Policy Tab Tables
- `LH_BAS_POL`: Main policy data
- `TH_COV_PHA`: Coverage phase (plancode, class/base/sub, mortality tables)
- `LH_BIL_FRM_CTL`: Billing control number
- `TH_USER_REPLACEMENT`: Replaced policy info
- `TH_USER_GENERIC`: Converted policy info
- `LH_FXD_PRM_POL`: Fixed premium factors (traditional products only)

#### AdvProdValues Tab Tables
- `LH_POL_MVRY_VAL`: Monthliversary values (MV history)
- `LH_POL_FND_VAL_TOT`: Fund values (unimpaired)
- `LH_NON_TRD_POL`: Non-traditional policy data (GAV, grace rule, etc.)
- `LH_POL_LN`: Policy loan data (impaired values)
- `TH_USER_GENERIC`: Short pay data

#### Activity Tab Tables
- `FH_FIXED`: Financial history transactions
  - Key fields: ASOF_DT, SEQ_NO, TRANS (transaction code)
  - Amount fields: GROSS_AMT, NET_AMT
  - Fund fields: FUND_ID, FNDVAL_PH (phase)
  - Rate field: INT_RT
  - Reversal indicators: FCB0_REV_IND, FCB2_REV_APPL_IND
  - Tracking fields: ENTRY_DT, ORIGIN_OF_TRANS

### PolView Component Reference

#### StyledInfoTableGroup
Unified container for displaying info fields and/or tables.

Parameters:
- `title`: GroupBox title
- `columns`: Number of columns for info field layout (default: 1)
- `show_info`: Show info fields section (default: True)
- `show_table`: Show table section (default: True)

Methods:
- `add_field(label_text, attr_name, label_width, value_width, tooltip_section, tooltip_key)`: Add label/value pair with optional tooltip
- `set_value(attr_name, value)`: Set field value
- `set_field_tooltip(attr_name, tooltip_text)`: Set/update tooltip for a field
- `setup_table(headers)`: Setup table columns
- `load_table_data(rows)`: Load data into table
- `clear_all()`: Clear all fields and table

#### CopyableLabel
QLabel with right-click copy functionality.

#### ClickableTooltipLabel
QLabel that shows tooltip popup when clicked. Used for field labels with help text.

#### TooltipManager
Singleton class that loads tooltips from `config/field_tooltips.json`.

Methods:
- `get_tooltip(section, field)`: Get tooltip text
- `get_all_fields(section)`: Get all tooltips for a section
- `reload()`: Reload tooltips from file

### VBA Reference Files
- `frmPolicyMasterTV.frm.bas`: Main form with PopulatePolicy(), PopulateCoverages(), etc.
- `cls_PolicyInformation.cls.cls`: Policy object properties and data loading
- `mdlDataItemSupport.bas.bas`: Translation functions and lookup dictionaries

---

## Export to Excel

All "Export to Excel" features use **win32com COM automation** to open a new,
unsaved workbook directly in Excel.  The user decides whether to save or discard.

### Requirements

| Requirement | Detail |
|-------------|--------|
| No save dialog | Do NOT prompt for a file path before exporting |
| No temp files | Do NOT write to disk — the workbook is in-memory only |
| Bulk writes | Build data as a list of tuples, write via `Range.Value = data` (one call per sheet) |
| Header formatting | Bold, white text on dark fill, centered alignment |
| Freeze panes | Freeze the header row (`ws.Range("A2").Select()` → `FreezePanes = True`) |
| Auto-filter | Apply auto-filters to the full data range |
| Auto-fit columns | `ws.Columns.AutoFit()` after writing |
| ScreenUpdating | Disable before writing, re-enable when done |

### Pattern

```python
from win32com.client import dynamic

excel = dynamic.Dispatch("Excel.Application")
excel.Visible = True
excel.ScreenUpdating = False

wb = excel.Workbooks.Add()
ws = wb.ActiveSheet
ws.Name = "Sheet Title"

# Build header + data as list of tuples
all_data = [("Col A", "Col B", "Col C")]
for row in rows:
    all_data.append((row["a"], row["b"], row["c"]))

# Bulk write in a single COM call
total = len(all_data)
col_count = len(all_data[0])
ws.Range(ws.Cells(1, 1), ws.Cells(total, col_count)).Value = all_data

# Format headers
hdr = ws.Range(ws.Cells(1, 1), ws.Cells(1, col_count))
hdr.Font.Bold = True
hdr.Font.Color = 0xFFFFFF
hdr.Interior.Color = 0x404D00  # BGR for #004D40 (teal dark)
hdr.HorizontalAlignment = -4108  # xlCenter

# Apply number formats to ranges (not individual cells)
# ws.Range(ws.Cells(2, 2), ws.Cells(total, 2)).NumberFormat = "0.00"

# Freeze + filter + fit
ws.Range("A2").Select()
excel.ActiveWindow.FreezePanes = True
ws.Range(ws.Cells(1, 1), ws.Cells(total, col_count)).AutoFilter()
ws.Columns.AutoFit()

ws.Range("A1").Select()
excel.ScreenUpdating = True
```

### Notes

- Use `dynamic.Dispatch` (not `gencache.EnsureDispatch`) to avoid gen_py cache
  corruption issues that have bitten this project before.
- Colors in COM use **BGR** byte order — `0x404D00` renders as `#004D40`.
- Always wrap in `try/except ImportError` with a user-facing `QMessageBox`.
- `openpyxl` is reserved for **batch/headless** file generation only, never for
  interactive "Export to Excel" buttons.

---

## Build & Distribution

SuiteView ships as **two distributions** built with PyInstaller:

| Distribution | Spec File | Description |
|---|---|---|
| **SuiteView** | `SuiteView.spec` | Full suite — all tools and modules |
| **SuiteViewLight** | `SuiteViewLight.spec` | Lightweight — core tools only |

### SuiteView (Full)

Includes everything:

**Taskbar buttons:** PolView (P), FileNav (F), ABR Quote (A), Audit/QueryTool (Q), ScratchPad (📝), File History (H)

**Tools menu:** View Screenshots, PolView, ABR Quote, Mainframe Navigator, Audit Tool, Email Attachments (dev), Task Tracker (dev), Rate File Converter (dev), App Data Location

### SuiteViewLight

Stripped-down build for users who only need the essentials:

**Taskbar buttons:** PolView (P), FileNav (F), ABR Quote (A)

**Tools menu:** View Screenshots, App Data Location

**Excluded from Light:** Audit Tool, ScratchPad, File History, Mainframe Navigator, Email Attachments, Task Tracker, Rate File Converter, messaging badge

### How Light Mode Works

The app detects its own executable name at startup. If the exe is named `SuiteViewLight`, it sets `LIGHT_MODE = True` in `suiteview_taskbar.py`, which hides the extra buttons and menu items. Both builds share the same source code — only the spec file and exe name differ.

### Building

```bash
# Full build
python scripts/build_distribution.py

# Light build
python scripts/build_distribution.py --light
```

Both produce a folder + ZIP in `dist/`.