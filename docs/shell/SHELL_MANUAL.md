# SuiteView shell, bookmarks and distribution manual

Launcher, AppBar, FileNav/bookmark, profile-storage, packaging and runtime-access behavior.

> Source: moved from the former long-form `Agent.md` so that the canonical standards file can stay concise.


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
See [docs/PROFILE_STORAGE.md](../PROFILE_STORAGE.md) for maintenance, recovery
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

**Taskbar and FileNav bookmark ownership**:
- `suiteview/taskbar_launcher/taskbar_window.py` is a thin shell window.
  It owns `TaskbarState` plus explicit collaborators for chrome, modes, tabs,
  tray/app launching, and AppBar docking.
- Each `FileExplorerTab` owns `NavigationController` and
  `QuickLinksController` collaborators over `FileExplorerCore`.
- `FileExplorerCore` creates `bookmark_bar` (top bar, `bar_id=0`) and the
  tab quick-links controller creates `bookmark_container` (sidebar,
  `bar_id=1`).
- `BookmarkUiState` owns UI-only caches, popup/drag state and the container
  registry. `BookmarkDataManager` remains the only bookmark data source.

See `docs/TASKBAR_ARCHITECTURE.md`, `docs/FILENAV_ARCHITECTURE.md` and
`docs/BOOKMARKS.md` for the current structure and contracts.

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
