# Plan: Integrate PolView into SuiteView

**Status: Phase 1–2 COMPLETE ✓**

**TL;DR:** PolView lives as a self-contained package at `suiteview/polview/` (like TaskTracker), with three pieces promoted to shared infrastructure: DB2Connection → `suiteview/core/db2_connection.py`, Rates → `suiteview/core/rates.py`, and DB2 constants → `suiteview/core/db2_constants.py`. This enables the future **Inforce Illustration** app to share database and rate access. PolView launches from a green "P" button in the header bar, the Tools menu, and the system tray. It will use a **green & gold** theme (rich casino poker-table green) to distinguish it from SuiteView's blue & gold.

---

## What's Done ✓

### Phase 1: Package Structure & Shared Infrastructure

1. ✅ **Created `suiteview/polview/`** — self-contained package preserving PolView's internal structure:
   ```
   suiteview/polview/
   ├── __init__.py          # exports PolicyInformation, DB2Connection, launch_viewer
   ├── main.py              # standalone entry point
   ├── config/              # policy_records.py, field_tooltips.json
   ├── data/                # lookup.py + 4 JSON reference files
   ├── models/              # policy_information.py (4,251 lines), translations, constants, dataclasses
   └── ui/                  # main_window.py, widgets.py, formatting.py, tree_panel.py, styles.py, tabs/
   ```

2. ✅ **Promoted DB2Connection to `suiteview/core/db2_connection.py`** — shared DB2 infrastructure with:
   - Office 365 WITH clause injection
   - Region-to-DSN mapping
   - Class-level connection pooling
   - Auto-retry on `08S01` link failures
   - Full query API (`execute_query`, `execute_query_with_headers`, `execute_query_as_dict`, `execute_scalar`)

3. ✅ **Promoted Rates to `suiteview/core/rates.py`** — shared insurance rate lookup with:
   - UL_Rates SQL Server connection (via ODBC DSN)
   - Class-level rate caching
   - 20+ rate type query builders (COI, MTP, CTP, EPU, SCR, CORR, etc.)
   - Singleton pattern via `get_rates_instance()`

4. ✅ **Moved DB2 constants to `suiteview/core/db2_constants.py`** — `REGION_DSN_MAP`, `REGIONS`, `DEFAULT_REGION`

5. ✅ **Updated all imports** — 18 import statements across 11 files updated to use shared core paths

### Phase 2: Wire Up Launch Points

6. ✅ **Registered in `SuiteViewTaskbar`**:
   - `self.polview_window = None` attribute
   - `_open_polview()` method with lazy import + `_setup_child_window()`
   - Green "P" button in header bar (next to screenshot button) — green background `#2E7D32`, gold border `#D4A017`, gold "P" text
   - "PolView" in Tools dropdown menu
   - "📋 PolView" in system tray menu
   - Added to `_quit_application()` cleanup list

7. ✅ **Created `scripts/run_polview.py`** — standalone launcher with argparse (policy number + region)

---

## What's Next

### Phase 3: Theme — Green & Gold

8. **Extend SuiteView's theme system** — Add a green & gold palette to `suiteview/ui/theme.py`:
   - `green_dark = "#1B5E20"` — deep poker-table green
   - `green_primary = "#2E7D32"` — rich casino green
   - `green_light = "#43A047"` — hover/accent green
   - Paired with existing gold accents (`#D4A017`, `#FFD700`)

9. **Add PolView-specific QSS selectors** to `suiteview/ui/styles.qss` — target PolView widgets via objectName with green variants of existing blue selectors. Same spacing, fonts, structure — just green where blue would be.

10. **Strip PolView's inline styling** — Remove per-widget `setStyleSheet()` calls in PolView tabs. Replace with objectName assignments so the global QSS targets them.

11. **Use `FramelessWindowBase`** — Change `GetPolicyWindow` from `QMainWindow` to `FramelessWindowBase`. Green gradient header bar with gold title text. Add color parameter to `FramelessWindowBase` if needed.

### Phase 4: Cross-Feature Communication

12. **Define Qt signals on PolView** — `policy_loaded(str, str)`, `data_exported(str)` for future inter-app communication.

13. **Accept optional SuiteView context** — `GetPolicyWindow.__init__` accepts optional policy number + region for auto-loading when launched from another feature.

14. **Design shared data access for Inforce Illustration**:
    - `from suiteview.core.rates import Rates` — shared rate lookups
    - `from suiteview.polview.models import PolicyInformation` — inforce policy values
    - `from suiteview.core.db2_connection import DB2Connection` — shared DB2 access

### Phase 5: Polish & Package

15. **Update `requirements.txt`** — verify `python-dateutil` is listed
16. **Update PyInstaller spec** — add `suiteview/polview/` to hidden imports, include JSON data files
17. **Create `docs/guides/POLVIEW_GUIDE.md`**
18. **Add tests** — `tests/test_polview_*.py`
19. **Delete `PolView/` source folder** once integration is verified

---

## Key Decisions

- **Self-contained package** (`suiteview/polview/`) — matches TaskTracker pattern, clear ownership boundary, minimal refactoring risk
- **Three modules promoted to shared core** — DB2Connection, Rates, DB2 constants — enables future Inforce Illustration app
- **PolicyInformation is a public API** — `from suiteview.polview.models import PolicyInformation` — Inforce app imports it directly
- **Green & gold theme** — rich casino poker-table green (`#2E7D32`) with gold accents, consistent structure with SuiteView's blue & gold
- **`FramelessWindowBase` with green header** — consistent chrome, distinctive color identity
- **Qt signals for hooks** — PolView remains independently runnable while enabling inter-app communication