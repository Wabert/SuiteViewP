# ABR Quote manual

ABR Quote UI, theme, rate-source and output-panel behavior.

> Source: moved from the former long-form `Agent.md` so that the canonical standards file can stay concise.


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
