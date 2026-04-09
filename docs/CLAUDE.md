# SuiteView — Key Architecture Notes for AI Assistants

This document captures critical architectural patterns that AI assistants
**must** follow when working on any part of SuiteView.

**Last Updated:** February 20, 2026

---

## ⚠️  Development-Only Project — No Backward Compatibility Required

SuiteView is in **active development only**. There is **nothing in production**
to support. This means:

- **No deprecated wrappers** — when refactoring, replace the old API cleanly.
  Do not maintain legacy property names or compatibility shims.
- **No migration paths** — callers (UI tabs, etc.) should be updated to use
  the new API directly as part of the same change.
- **Breaking changes are fine** — rename, restructure, and delete freely.
  There are no external consumers or deployed versions to worry about.
- **No legacy code** — do not leave old patterns "just in case."  If code is
  replaced by a better design, remove the old code entirely.

---

## 🔒 Security + Execution Policy (MANDATORY)

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
   - Call it using: `python tools/<script>.py '<json>'`

4. **Reuse existing scripts.** Do not duplicate scripts. Always check
   `tools/` for an existing helper before creating a new one.

5. **Pre-execution check.** Every time you plan to execute something, you
   MUST first ask yourself: *"Am I about to use inline execution?"*  If yes,
   **STOP** and convert it to a helper script.

6. If a task cannot be done without inline execution, you must explain why
   and propose a helper-script alternative.

---

## 🐍 Python Environment (MANDATORY)

This project uses a **virtual environment** at `venv\` with all dependencies
installed (PyQt6, sqlalchemy, pandas, etc.).

**Always use the venv Python interpreter — never bare `python` or `python3`:**

```
venv\Scripts\python.exe <script_or_args>
```

Examples:
- Run a script: `venv\Scripts\python.exe tools/verify_abr_rate.py`
- Run tests: `venv\Scripts\python.exe -m pytest tests/ -v`
- Install a package: `venv\Scripts\python.exe -m pip install <package>`

Using bare `python` will resolve to the **system Python** which does NOT have
PyQt6 or other project dependencies, causing `ModuleNotFoundError`.

---

## 🖥️ Desktop Application — NOT a Browser App (IMPORTANT)

SuiteView is a **native desktop application** built with **Python + PyQt6**.
It is **NOT** a web/browser application. This means:

- **Browser tools cannot inspect or screenshot SuiteView.** The browser
  subagent, Playwright, and similar web-oriented tools will not work.
- **To visually verify the UI**, use the screenshot helper script:

  ```powershell
  venv\Scripts\python.exe tools/take_screenshot.py
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

## 🪟 Window Footer — Size Display

All windows built on `FramelessWindowBase` **must** display the current
window dimensions (`W × H`) in the bottom-right corner of the footer area.
This is implemented in the base class itself, so every sub-app window
(PolView, ABR Quote, Audit, TaskTracker, RateManager, etc.) gets it
automatically. No sub-app code is needed — just inherit from
`FramelessWindowBase` as usual.

- The label updates live on every resize.
- It uses a semi-transparent style so it doesn't distract from the main
  content but is always visible for layout/debugging reference.

---

## 📝 ScratchPad

**Location:** `suiteview/ui/widgets/scratchpad_panel.py`

Every `FramelessWindowBase` window includes a **ScratchPad** button (📝) in
the header bar. Clicking it opens a persistent text area for notes.

- **Timestamp button** — inserts a timestamped header (e.g., `[2026-02-19 14:30]`)
  followed by a newline and 4-space indentation.
- **Auto-indent** — pressing Enter auto-indents the new line with 4 spaces
  (except timestamp lines).
- Notes persist per-window instance during the session.

---

## 🔧 MiniExplorer — Reusable File Browser Widget

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

---

## 🖥️ Compact Mini-Bar

SuiteView can dock as a **compact mini-bar** at the bottom of the screen,
overlapping the Windows taskbar region. This bar stays always-on-top by
adjusting the desktop's "work area" via Win32 API (`SystemParametersInfoW`).

- Contains a policy number input field and company combobox.
- No timer-based solutions — uses OS-level window management.
- Maximized windows respect the reserved space and don't cover the bar.

## 📋 StyledInfoTableGroup — Default UI Container

**Location:** `suiteview/polview/ui/widgets.py`

`StyledInfoTableGroup` is the **standard widget** for displaying **field/value
pairs**, **table data**, or **both** across all sub-apps.  Unless you are
explicitly told to use a different approach, **always use this class** instead
of building raw `QTableWidget`, `QGroupBox` + `QGridLayout`, or other ad-hoc
containers.

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

---

## 🚫 Not-Applicable Sections — UI Preference (MANDATORY)

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

## 📁 Sub-App Documentation

SuiteView is a multi-app platform. Each sub-app has its own detailed
documentation file. This `CLAUDE.md` covers **cross-cutting concerns** shared
across all apps. For app-specific details, see the relevant doc:

| Sub-App | Doc File | Purpose |
|---------|----------|---------|
| **PolView** | [`POLVIEW_CLAUDE.md`](POLVIEW_CLAUDE.md) | Policy viewer — VBA reference, Trad vs Advanced deep dive, coverage/rate logic, VBA property mappings, Cyber Audit |
| **ABR Quote** | *(see sections below)* | Accelerated Death Benefit quoting tool — 3-step wizard, dedicated SQLite DB, Crimson Slate theme |
| **Task Manager** | *(future)* | Task management |

---

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
- `scripts/import_state_forms.py` — imports `StateForms.xlsx` → `state_forms` table
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
- Uses the reusable `MiniExplorer` widget (see above)
- Styled with Crimson Slate theme via `_apply_abr_style()` to override MiniExplorer defaults

---

## ⚠️  PolicyInformation — THE Central Data Layer

**Location:** `suiteview/polview/models/policy_information.py`
**Shared service:** `suiteview/core/policy_service.py`

`PolicyInformation` is the **single most important class in SuiteView**.
Every application that needs policy data — PolView, ABR Quote, Audit, and
every future tool — **must** access that data through this class.  It is the
canonical, authoritative interface to DB2 policy records.

### Why this matters

- **One source of truth.** All DB2 queries for policy-level data live inside
  `PolicyInformation`.  No app should write its own raw SQL against
  `LH_BAS_POL`, `LH_COV_PHA`, etc.
- **Constantly evolving.** New properties are added regularly as we expose
  more policy data to feed more apps.  When you need a field that doesn't
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

1. **Never use `pi.get_value()`** — that method does not exist.  Use named
   properties directly (e.g. `pi.base_issue_age`).
2. **Never pass a DB2Connection to the constructor** — `PolicyInformation`
   manages its own connections internally.  Constructor signature:
   `PolicyInformation(policy_number, company_code=None, system_code="I", region="CKPR")`
3. **Check existence with `pi.exists`**, not `pi.policy_found`.
4. **When a new property is needed**, add it to `PolicyInformation` with a
   `@property` decorator following the existing pattern — query via
   `self.data_item(table, field)`.
5. **Always go through `policy_service.get_policy_info()`** from app code so
   caching works.

---

## 🗄️ DB2 Database Configuration

All sub-apps share the same DB2 connectivity layer.

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
> [`POLVIEW_CLAUDE.md`](POLVIEW_CLAUDE.md) and `config/policy_records.py`.

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

---

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
> equivalents: see [`POLVIEW_CLAUDE.md`](POLVIEW_CLAUDE.md) § "CoverageInfo Rate Fields"

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
The premium in `LH_BAS_POL.POL_PRM_AMT` is still a **monthly** premium.  Bi-weekly
(and other non-standard) payments are collected into a **Premium Depositor Fund (PDF)**,
and once a month money is moved from that fund to pay the monthly policy premium.
Therefore, for all ABR and other premium-based calculations, we treat the premium
as monthly and use the PAC Monthly modal factor (`0.0864`).  The billing mode label
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

---

## Bookmark Data Format

### File Location
`~/.suiteview/bookmarks.json`

### Structure
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

### Key Points
- **Bar 0** = Horizontal bookmark bar (top)
- **Bar 1** = Vertical sidebar (Quick Links)
- **Categories are items** with nested `items` array (NOT a separate `categories` dict)
- Every item has a unique `id` generated by `BookmarkDataManager.generate_item_id()`
- URLs start with `http://` or `https://`

### ❌ DEPRECATED (Do Not Use)
```json
// OLD FORMAT - DO NOT USE
{
    "categories": {"Work": [...], "Personal": [...]},
    "category_colors": {"Work": "#ff0000"}
}
```

The legacy `categories` dict format is auto-cleaned on load.

---

## File Responsibilities (Bookmarks)

### `file_explorer_core.py`
Base class with helper methods that delegate to BookmarkDataManager:

| Method | Purpose |
|--------|---------|
| `is_path_in_quick_links(path)` | Check if path in sidebar (bar 1) |
| `add_bookmark_to_quick_links(path)` | Add to sidebar |
| `remove_bookmark_from_quick_links(path)` | Remove from sidebar |
| `add_category_to_quick_links(name)` | Add category to sidebar |
| `remove_category_from_quick_links(name)` | Remove category from sidebar |
| `save_quick_links()` | Calls `_bookmark_manager.save()` |

### `suiteview_taskbar.py`
Main application taskbar (in `suiteview/taskbar_launcher/`) that uses:
- `self.bookmark_container` - BookmarkContainer for sidebar (bar_id=1)
- `self.bookmark_bar` - BookmarkContainer for top bar (bar_id=0)
- `self._bookmark_manager` - Reference to singleton

### `shortcuts_dialog.py`
Bookmark management dialogs. Uses helper methods:
- `_get_category_names()` - Get category names from items
- `_find_category_item(name)` - Find category in items
- `_category_name_exists(name)` - Check if category exists

---

## Bookmark Best Practices

### ✅ DO
```python
# Use BookmarkDataManager for data operations
manager = get_bookmark_manager()
manager.add_bookmark_to_bar(1, "MyFile", "/path/to/file")
manager.save()

# Use find_category_by_name for category lookup
category = manager.find_category_by_name("Work")
if category:
    category['items'].append(new_bookmark)

# Check existence with is_path_in_bar
if not manager.is_path_in_bar(1, path):
    manager.add_bookmark_to_bar(1, name, path)
```

### ❌ DON'T
```python
# Don't access categories dict (deprecated)
self.bookmarks_data['categories']['Work'].append(...)  # BAD

# Don't create bookmarks without IDs
bookmark = {'name': 'x', 'path': '/x'}  # BAD - missing id

# Don't bypass the manager for saves
with open(file, 'w') as f:
    json.dump(data, f)  # BAD - use manager.save()
```

---

## URL Bookmark Handling

URLs are detected by prefix and opened in browser:

```python
# In StandaloneBookmarkButton.mouseReleaseEvent (bookmark_widgets.py)
if path.startswith('http://') or path.startswith('https://'):
    import webbrowser
    webbrowser.open(path)
    return
```

---

## Adding New Functionality

### To add a new bookmark operation:
1. Add method to `BookmarkDataManager` if it involves data manipulation
2. Use the manager method from UI code
3. Call `manager.save()` after modifications
4. Call `container.refresh_bookmarks()` to update UI

### To add a new bar:
```python
bar_id = manager.create_bar(orientation='horizontal')
container = BookmarkContainer(bar_id=bar_id, orientation='horizontal', parent=self)
```

### To add a new sub-app documentation file:
1. Create `docs/<APPNAME>_CLAUDE.md`
2. Add an entry to the Sub-App Documentation table above
3. Keep shared concerns (DB2, PolicyInformation) in this file
4. Keep app-specific details (UI, VBA mappings, business rules) in the sub-app doc

---

## 📤 Export to Excel — Standard Pattern

**Technology:** `win32com.client.dynamic` (COM automation — Windows only)

All "Export to Excel" features in SuiteView follow a **single pattern**: open a
brand-new, unsaved workbook in Excel via COM, bulk-write the data, and let the
user decide whether to save or discard it.

### Key principles

1. **No save dialog** — do NOT prompt the user to pick a file path.
2. **No temp files** — do NOT write to disk; the workbook lives only in memory
   until the user explicitly saves it.
3. **Bulk writes** — build all data as a list of tuples, then write the entire
   block in one `Range.Value = data` call per sheet.  Never write cell-by-cell.
4. **Formatted headers** — bold, white text on a dark fill, centered.
5. **Freeze panes** — freeze the header row so it stays visible while scrolling.
6. **Auto-filter** — add auto-filters to the data range.
7. **Auto-fit columns** — call `ws.Columns.AutoFit()` after writing data.
8. **ScreenUpdating** — set `excel.ScreenUpdating = False` before writing, then
   `True` when done, so the workbook appears fully rendered.

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

1. **Always use this pattern** for any new "Export to Excel" feature.
2. **Never use openpyxl + file save** for interactive exports; openpyxl is only
   appropriate for batch/headless file generation.
3. **Use `dynamic.Dispatch`** (not `gencache.EnsureDispatch`) to avoid
   gen_py cache corruption issues.
4. **Apply number formats to ranges**, not individual cells.
5. **Colors are BGR** in COM — `0x404D00` is `#004D40` (teal dark).
6. **Handle ImportError** gracefully with a user-facing message box.

### Existing implementations

| Location | Description |
|----------|-------------|
| `polview/ui/widgets.py` → `FixedHeaderTableWidget._dump_to_excel()` | Context-menu "Dump to Excel" on any PolView table |
| `abrquote/ui/calc_viewer.py` → `CalcViewerDialog._on_export()` | Calculation detail viewer (Mortality + APV sheets) |

---

## 📦 Distribution Build

SuiteView can be packaged as a distributable **EXE** (ZIP folder) for
coworkers using PyInstaller. See the workflow: `/build-distribution`.

**Build script:** `scripts/build_distribution.py`

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
  builds: Audit button, Email Attachments, Task Tracker, Audit tool,
  Rate File Converter.

### Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `No module named 'PyQt6'` at EXE runtime | Build script was run with system Python instead of venv Python | Run with `venv\Scripts\python.exe scripts/build_distribution.py` |

The build script has a safeguard: it auto-detects `venv/Scripts/python.exe`
and uses it for the PyInstaller subprocess even if the script itself was
launched with the system Python. But to be safe, **always launch with the
venv interpreter**.

---

## Testing

Run the file explorer to test bookmark functionality:
```powershell
venv\Scripts\python.exe scripts/run_file_explorer_multitab.py
```

Check bookmark data:
```powershell
Get-Content "$env:USERPROFILE\.suiteview\bookmarks.json" | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

---
*This file should be updated at the end of each session to help the next agent continue the work.*
