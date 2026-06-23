# File Sources — Design & Build Plan

**Living document.** The reference for reworking how flat files (CSV / delimited
text / fixed-width / Excel) are modeled and queried in the Audit tool. Update as
decisions change. Status: **Phase 1 built + unit-tested on the minipc
(2026-06-22); Phases 2–3 deferred to the app (see `WORK_LAPTOP_SPEC.md` §3c).**

---

## 1. The problem

Today a flat file **is** a query: a `QueryObject` with `kind="adhoc_source"`
(`suiteview/audit/query_object.py`, `adhoc_source_intake.py`). That single object
conflates two different things and points at exactly **one** file:

1. the file *type* — parsing spec (delimiter / fixed-width / header / encoding) +
   column names & types;
2. a *query* over it — `query_adhoc_object()` does pick-columns + one pandas
   filter + a row limit.

That breaks down the moment you have several files of the same type (e.g.
`CLAIMS.txt` and a sibling `RGACLAIMS.txt`) or want real queries (joins,
aggregation, UNION) over them. `replace_adhoc_source_path()` (swap the file, keep
the spec) is the existing code straining against this conflation.

## 2. The model (decided 2026-06-22)

Split the file *type* from the *query*. A file becomes a **data source**, a peer
of a DSN — everywhere else in SuiteView a *data source* (a DSN like `NEON_DSN`)
is separate from the queries run against it; files now match.

**`FileDataSource`** (`suiteview/audit/file_source.py`) — its own id-keyed store
at `~/.suiteview/file_sources/` (`file_source_store.py`, atomic via
`core/json_store.py`):

- **`source_type`** — `csv` (delimited) / `fixed_width` / `excel` (the same
  dispatch keys `adhoc_source_intake` already uses).
- **`parse_spec`** — the parsing metadata, intentionally the *same dict shape*
  the `adhoc_source_intake` readers consume, so loading a member is just
  `{**parse_spec, "path": member.path}` — no parallel parsing logic. Lets you
  declare column names when the file has no header.
- **`columns`** — `FileColumn[]` (name + type), the schema defined once and
  applied to **every** member file. The builder uses this for field listing with
  no file read.
- **`members`** — `FileMember[]` (`path`, `table_name`, `label`). **Each member
  is its own table** (decision below): `CLAIMS.txt` → table `CLAIMS`,
  `RGACLAIMS.txt` → table `RGACLAIMS`.

### Key decisions
- **Each file is its own table** (not auto-unioned). A query references
  `"CLAIMS"` and `"RGACLAIMS"` separately and **UNIONs them in SQL** to combine.
  This keeps the source a transparent catalog of tables, mirroring a DSN.
- **One query engine, no new query type.** A query targets a File Source by
  setting `dsn = <file_source_id>` and `dialect = "DUCKDB"`. The existing Visual
  Query designer and Manual SQL editor both gain it as a selectable source. The
  answer to "do we need a third query type for txt/csv?" is **no** — we
  generalize the *data source*, so one engine serves DB2, SQL Server, and files,
  and a file query can later join a DB2 query inside DataForge for free.

## 3. The engine (reuse, don't rebuild)

`file_query_runner.py` loads each referenced member into a DataFrame using the
proven `adhoc_source_intake` readers (so delimited, fixed-width, and Excel all
work — DuckDB has no clean native fixed-width reader, so we parse with pandas and
register the frame), then runs the SQL through **`forge_engine.run_manual_sql`**
(DataForge's DuckDB-over-registered-DataFrames engine). `run_query()` returns an
ODBC-shaped `(columns, rows, column_types)` so file queries flow through the same
result-rendering paths as a DB2/SQL Server query.

`dynamic_query.py` gained a **`DUCKDB`** dialect: double-quote identifiers (like
DB2) and `LIMIT n` row caps. The visual builders were already dialect-aware, so
this was a small, additive change.

## 4. Phased build plan

- **Phase 1 — Backbone:** ✅ *built + unit-tested on the minipc (2026-06-22).*
  `file_source.py` (pure model), `file_source_store.py` (id-keyed atomic store),
  `file_query_runner.py` (member load → DuckDB run), `DUCKDB` dialect in
  `dynamic_query.py`. Tests: `tests/test_file_source.py` (17) — model/store
  round-trip, each-file-its-own-table + UNION, fixed-width, headerless+declared
  columns, DUCKDB quoting/LIMIT, ODBC-shaped result, limit cap.
- **Phase 2a — File Source editor:** ✅ *built + screenshot-verified on the
  minipc (2026-06-22).* `file_source_intake.py` (infer a source from a first
  file; validate/add later files against its format+schema — the drag-drop
  engine), `tabs/file_source_editor.py` (the new editor: format+columns set by
  the first file, member-file list with **OS drag-and-drop** + Add/Remove, per-
  file DuckDB preview, "Save File Source"), and `audit_window.py` wiring (New
  Query → **File Source** opens the new editor; build-mode selector; legacy
  adhoc editor kept only for opening old objects until Phase 3 migration). Tests:
  `tests/test_file_source_intake.py` (9). The minipc can render the app + grab
  screenshots, so this was verified visually here.
- **Phase 2b — Manual SQL over a File Source:** ✅ *built + screenshot-verified
  in-app on the minipc (2026-06-22).* The File Source editor has a **Query in
  SQL →** button (`query_requested` signal) that saves the source and opens the
  Manual SQL editor targeted at it. `FieldPickerPanel.load_local_source()` adds a
  no-ODBC "local mode": member tables + schema columns are served from the stored
  schema (cache pre-fill), so the assist works without a DB. `ManualSqlObjectEditor.
  set_file_source()` wires that up; Run routes through `file_query_runner`
  (`AuditWindow._run_manual_sql_preview` branches on a `file:<id>` token); Save
  stamps `dialect="DUCKDB"` + `config["file_source_id"]`. Verified end-to-end: a
  cross-file `UNION ALL` + `GROUP BY` over CLAIMS+RGACLAIMS returns correct
  aggregates.
- **Phase 2c — Visual builder over a File Source:** ✅ *built + screenshot-
  verified in-app on the minipc (2026-06-22).* `detect_dialect()` returns
  `DUCKDB` for a `file:<id>` pseudo-DSN, so a `DynamicQuery` built on a file
  token compiles via the DUCKDB dialect. `DynamicQuery._run_audit` / `_run_build_sql`
  branch to `file_query_runner`. `AuditWindow._open_visual_query_on_file_source`
  creates the query with `tables=[]` (the table is inferred from the dragged
  fields, so a multi-file source with identical columns can't silently pick the
  wrong member); `_bind_picker_to_file_source` fills the SQL Assist picker from
  the stored schema (reusing `FieldPickerPanel.load_local_source`). Entry point:
  a **Visual Query →** button on the File Source editor. Verified: the designer
  runs SELECT over a member table through DuckDB.
- **Phase 3 — Discoverability + migration:** ✅ *built + verified on the minipc
  (2026-06-22).* A dedicated **File Source browser** (`dialogs/file_source_browser.py`)
  lists saved sources (name, format, file/column counts) with Open/Delete; the
  File Source editor gained an **Open…** button to reopen a saved source for
  editing. Migration: `file_source_intake.migrate_adhoc_to_file_source()` +
  `tools/migrate_adhoc_sources.py` (dry-run by default; `apply=true` converts
  every legacy `adhoc_source` QueryObject to a FileDataSource and removes the
  original). Tests: `test_file_source_intake.py` (+2 migration). A dedicated
  browser was chosen over shoehorning a new entity into the 3,300-line
  QueryObject browser.
  - **Deferred (needs interactive app verification, `WORK_LAPTOP_SPEC.md` §3c):**
    run the migration with `apply=true` on the work laptop (no adhoc objects on
    the minipc), then remove the now-dead legacy `adhoc_source` code paths
    (`csv_excel_object_editor.py`, the adhoc branches in
    `query_object_viewer_window.py`, the adhoc factories in `query_object.py` /
    `adhoc_source_intake.py`) once the browser is confirmed clean. Optionally
    fold the File Source browser into the unified Object Browser.

- **Phase 4 — Data Sources tab as a source registry:** 🚧 *steps 1–2 + 3a built
  (2026-06-22); step 3b deferred.* The Object Browser's Data Sources tab was a
  read-only side-effect view that borrowed the QueryObject detail canvas. Rework
  it into the place you **add, configure, test, and inspect** data sources (File
  Source, ODBC/DB2, SQL Server, MS Access). Full design in **§6**.
  - **Step 1 (done):** removed `File Source` from the Audit Build-Mode dropdown
    and the New-Query chooser; `+ New File Source` button backed by public
    `AuditWindow.new_file_source()`.
  - **Step 2 (done):** the §6 spec.
  - **Step 3a (done, screenshot-verified):** the **source dashboard** —
    `_SourceDashboard` (a new page in `_browser_canvas_stack`) replaces the
    borrowed query tabs for source nodes. Header = name + type badge + health
    pill + actions (Test / Edit Setup / New Query▾ / Open Folder / Delete);
    body = `StyledInfoTableGroup` panels Setup / Tables / Columns / Used-by,
    re-skinned to Audit Blue/Gold (`_DASHBOARD_GROUP_STYLE`, since the shared
    widget carries PolView green). First-class File Sources (`file_data_source`)
    now have a real detail view (they previously showed nothing on single-click);
    health = member-file existence; Edit Setup → `FileSourceEditor`; New Query →
    `AuditWindow.new_query_on_file_source(id, mode)`; Delete →
    `file_source_store.delete_file_source_by_id`. ODBC + legacy `file_source` are
    routed to the dashboard read-only (Setup + Used-by; health from
    `get_dsn_details` / file existence). Removed the dead
    `_configure_data_source_tables` + four source-row helpers. Harness:
    `tools/show_source_dashboard.py`.
  - **Step 3b — ODBC registry (done, screenshot-verified):** registered ODBC
    sources are now first-class. New `data_source.py` (`RegisteredDataSource` —
    pure model, kind=odbc|access) + `data_source_store.py` (id-keyed atomic JSON
    at `~/.suiteview/data_sources/`, mirrors `file_source_store`; env override
    `SUITEVIEW_DATA_SOURCES_DIR`). `core/odbc_utils` gained `list_installed_dsns()`
    and a dialect-agnostic `probe_dsn_connection()`. The `+ New File Source`
    button became a typed `+ Add Data Source ▾` chooser (File Source… / ODBC
    DSN…); `_RegisterOdbcDialog` picks an installed DSN (or types one), names it,
    and Tests it. Registered DSNs are **pinned** in the tree (shown gold, even
    with no query) with their own dashboard (Setup + live Test health + Edit /
    Delete); discovered DSNs get a **Register** action to promote them. Tests:
    `tests/test_data_source.py` (9). Harness: `tools/show_odbc_data_source.py`.
  - **Step 3b — MS Access (done, screenshot-verified):** "Add Data Source → MS
    Access" picks a `.accdb`/`.mdb` file (`_RegisterAccessDialog`, with Browse +
    Test), registered as `RegisteredDataSource(kind=access)`. Access connects
    DSN-less (driver + `DBQ=<path>`); `odbc_utils` gained `access_driver()`,
    `access_connection_string()`, `probe_access_connection()`, and
    `list_access_tables()`. New "MS Access" tree group (pinned, gold) with a
    dashboard (Setup incl. driver/path, file-existence + live Test health,
    Tables = the file's user tables when the driver can read it, Edit / Open
    Folder / Delete). Delete generalized to `_delete_registered_source` for both
    kinds. Tests: `test_data_source.py` (+3). Harness:
    `tools/show_access_data_source.py`.
  - **Step 3b — remaining:** "New Query on a DSN / Access source" from the
    dashboard (needs builder wiring — File Sources already have it), and folding
    away the legacy `Files` tree group (§6.6).

## 5. Constraints
- DuckDB + flat-file logic is fully testable on the minipc; interactive UI
  verification (builder integration, the editor, the browser) is deferred to the
  app on the work laptop (`WORK_LAPTOP_SPEC.md` §3c).

## 6. The Data Sources tab — source registry (Phase 4 design)

### 6.1 The conceptual split

> **A data source is a noun you connect to. A query is a question you ask against
> it.** Build Mode is *how you ask*; the Data Sources tab is *what you ask
> against, and how you manage the connection.*

That sentence is the whole redesign. Once a File Source is a first-class source
(Phases 1–3), defining one through a query "Build Mode" is a category error — it
conflates the source with a query over it. Step 1 fixed the entry point; step 3
fixes the surface it lives on.

### 6.2 Why the current canvas is wrong

`QueryObjectViewerWindow`'s Data Sources tab (`query_object_viewer_window.py`)
reuses the **QueryObject detail canvas**. When a source is selected,
`_show_odbc_source_detail` / `_show_file_source_detail` call
`_configure_data_source_tables`, which only **relabels** the query tabs
(`Object/Sources/Outputs/Inputs/Joins/All Fields/SQL/Config` →
`Source/Setup/Query Objects/Source Uses/Joins/Fields/SQL/Config`) and stuffs a DSN
into fields built for a query (`Object`, `Builder`, `Description`, `Tags`). A DSN
has no "outputs", "joins", or "SQL" of its own. It also reads as a *side-effect
view*: ODBC sources are **discovered** by scanning which DSNs queries reference
(`_odbc_dsns_for_object`), not registered — so it's half registry, half "things my
queries touched". Only File Sources are real registered entities
(`file_source_store`).

### 6.3 The target: a source dashboard

Replace the borrowed query tabs with a **source dashboard** (its own page in
`_browser_canvas_stack`, shown when a source node is selected — not a relabel of
`self.tabs`). Use `StyledInfoTableGroup` for label/value panels and
`FilterTableView` for the data grids, per Agent.md — never raw `QTableWidget`.

**Header band** — name · type badge · **health pill** · actions:
- Health is the new idea: *is this source reachable right now?* Cached, with a
  manual Refresh. ODBC/Access → Test Connection (Connected / Unreachable). File
  Source → member-file existence (`N files OK` / `N missing`).
- Actions: `Test/Refresh` · `Edit setup` (opens the type's editor — `FileSourceEditor`
  for files; an ODBC/Access connection dialog for the others) · `New query on this
  source` (the bridge that replaces "Build Mode → File Source": select a source,
  then ask a question) · `Rename` · `Remove` · `Open folder` (files).

**Body panels:**
1. **Setup** (label/value) — the connection facts, per type (see §6.4).
2. **Tables** (grid) — the tables the source exposes. File Source: each member →
   `table_name`, path, (row count if cheap). Access: tables in the `.accdb`. ODBC:
   lazy `Browse tables` button — never eagerly enumerate DB2.
3. **Columns** (grid) — columns for the selected table. File Source: the shared
   `columns` schema (no file read). Access/ODBC: from the selected table.
4. **Used by** (grid) — Query Objects targeting this source. Already computed —
   keep `_source_query_rows` / the payload `object_ids`.

Drop Outputs/Inputs/Joins/All Fields/SQL/Config — those are query concepts.

### 6.4 What to show per source type

| Type | Setup panel | Tables | Backing |
|---|---|---|---|
| **File Source** | source_type, parser summary, column count, member count, encoding, updated_at | each member = a table | `FileDataSource` (built) |
| **ODBC / DB2** | DSN, scope (User/System), driver, server, database, host/port, subsystem, **schema qualifier**, region, dialect | lazy browse | `get_dsn_details` + region map; needs a registry (§6.5) |
| **SQL Server** | DSN or server/db, driver, dialect | lazy browse | same ODBC path |
| **MS Access** | file path, driver, dialect, table count | tables in the file | new: file picker → conn string |

The CKPR/CKMO/CKAS… → DSN → schema-qualifier mapping (Agent.md §"DB2 Database
Configuration") is *insurance-domain* source config and belongs in the ODBC Setup
panel.

### 6.5 Add Data Source — the typed chooser

Replace the step-1 `+ New File Source` button with `+ Add Data Source ▾`:
- `File Source…` → `AuditWindow.new_file_source()` (built in step 1).
- `ODBC DSN…` → pick from installed DSNs → register a named source.
- `MS Access…` → file picker → build connection string → register a named source.

This implies ODBC/Access become **registered, stored** entities, not just
discovered. Decision for step 3: introduce a small `DataSource` registry (parallel
to / extending `file_source_store`) so a DSN can be named, health-checked, and
shown **before any query references it** — the user's "come here to add an ODBC
data source." Discovered-from-queries DSNs still appear (union with registered
ones) so nothing currently visible disappears.

### 6.6 Fold the legacy `Files` group

The source tree has three roots — `ODBC`, `Files`, `File Sources`
(`_refresh_source_tree`). The middle `Files` group is the un-migrated legacy
adhoc-path bucket. After the Phase 3 migration runs with `apply=true`, remove the
`index["files"]` branch in `_build_data_source_index` and its `_add_group("files",
…)` call so flat files live in exactly one place.

### 6.7 Build map (step 3)

All in `query_object_viewer_window.py` unless noted:
- `_build_data_source_panel` — swap the `+ New File Source` button for the
  `Add Data Source ▾` chooser.
- `_configure_data_source_tables` — delete; the dashboard is its own page, not
  relabeled query tabs.
- `_show_odbc_source_detail` / `_show_file_source_detail` — rebuild as the
  dashboard; add `_show_access_source_detail`.
- `_refresh_source_tree` / `_build_data_source_index` — add Access + registered
  ODBC groups; fold `files`.
- New: a `DataSource` registry/store for ODBC + Access (§6.5); a Test-Connection
  helper per type (reuse `core/odbc_utils`).
- `file_source_browser.py` (the standalone dialog) is superseded by this tab once
  step 3 lands — retire it then.

## Changelog
- **2026-06-22 (Phase 4 polish — File Source editor window)** — The File Source
  editor is now its own dedicated frameless window (`FileSourceEditorWindow` in
  `tabs/file_source_editor.py`), not a build mode embedded in the Audit tool. The
  browser's Add/Edit actions open it (`_ensure_file_source_editor_window`); its
  Visual/SQL Query buttons route to `AuditWindow.new_query_on_file_source` via the
  browser. Removed the embedded file-source surface from `audit_window.py`
  (`file_source_tab`, `__file_source__` mode, `_enter_file_source_mode`,
  `new_file_source`, `open_file_source`). The Columns panel became an editable
  table (per-row Type dropdown → `FileColumn.data_type`, persisted on save) and
  list rows were tightened.
- **2026-06-22 (Phase 4, step 3b — MS Access)** — MS Access as an addable source
  kind. `_RegisterAccessDialog` (Browse + Test); `RegisteredDataSource(kind=
  access)`; `odbc_utils` Access helpers (`access_driver`,
  `access_connection_string`, `probe_access_connection`, `list_access_tables`).
  New "MS Access" tree group + dashboard (Setup/driver/path, file + live Test
  health, Tables via the Access driver, Edit/Open Folder/Delete);
  `_delete_registered_source` now covers both registered kinds. Updated
  `..._file_source_keeps_left_width...` for the new group order (0=ODBC, 1=MS
  Access, 2=Files, 3=File Sources). Tests +3; suite 453 passed / 13 pre-existing.
  Harness: `tools/show_access_data_source.py`. Remaining 3b: New-Query-on-a-DSN,
  fold the `Files` group.
- **2026-06-22 (Phase 4, step 3b — ODBC registry)** — Registered ODBC sources
  are first-class. New `data_source.py` (`RegisteredDataSource`) +
  `data_source_store.py` (id-keyed atomic JSON, `SUITEVIEW_DATA_SOURCES_DIR`);
  `odbc_utils.list_installed_dsns()` + `probe_dsn_connection()`. `+ New File
  Source` → typed `+ Add Data Source ▾` (File Source / ODBC DSN) with a
  `_RegisterOdbcDialog` (pick/type DSN, name, Test). Registered DSNs are pinned
  in the tree + get a dashboard (Setup / live Test health / Edit / Delete);
  discovered DSNs get a Register action. Made
  `test_query_object_viewer_initial_selection_populates_detail` hermetic
  (isolate `SUITEVIEW_DATA_SOURCES_DIR`). Tests: `test_data_source.py` (9); suite
  450 passed, 13 pre-existing failures. Remaining 3b: MS Access, New-Query-on-DSN,
  fold the `Files` group.
- **2026-06-22 (Phase 4, step 3a)** — The source-dashboard canvas. New
  `_SourceDashboard` widget (own page in `_browser_canvas_stack`) replaces the
  borrowed QueryObject detail tabs for Data Source nodes: header (name + type
  badge + health pill + Test/Edit Setup/New Query▾/Open Folder/Delete) over
  `StyledInfoTableGroup` Setup/Tables/Columns/Used-by panels, re-skinned to Audit
  Blue/Gold. First-class File Sources got a real single-click detail view +
  member-file health; `AuditWindow.new_query_on_file_source(id, mode)` powers the
  New Query action. Removed dead `_configure_data_source_tables` and four
  now-unused source-row helpers. `tools/show_source_dashboard.py`. Suite: 441
  passed, 13 pre-existing live-DB2/illustration failures (unrelated). Remaining:
  step 3b (Add Data Source chooser + registered ODBC/Access + fold `Files`).
- **2026-06-22 (Phase 4, step 1 + spec)** — Started the Data Sources tab →
  source registry rework (§6). Step 1 (built, screenshot-verified): removed
  `File Source` from the Audit Build-Mode dropdown and the New-Query chooser
  (`audit_window.py`); replaced the orphaned `_start_file_source` with a public
  `new_file_source()`; added a `+ New File Source` button on the Object Browser's
  Data Sources tab (`query_object_viewer_window.py`) wired to it — so defining a
  source no longer routes through a query build mode. Step 2: §6 spec (conceptual
  split, source-dashboard canvas, per-type Setup, the `Add Data Source` typed
  chooser, folding the legacy `Files` group, step-3 build map). Step 3 (the
  dashboard + registered ODBC/Access sources) deferred.
- **2026-06-22 (Phase 3)** — Discoverability + migration. `dialogs/file_source_browser.py`
  (list/open/delete saved sources) + an "Open…" button on the editor;
  `migrate_adhoc_to_file_source` + `tools/migrate_adhoc_sources.py` (dry-run
  default). Tests +2 (migration). Legacy adhoc code removal + unified-browser
  fold deferred to the laptop (needs interactive verification).
- **2026-06-22 (2c)** — Visual builder over a File Source. `DUCKDB` dialect from
  `detect_dialect("file:…")`; `DynamicQuery` run paths branch to
  `file_query_runner`; `AuditWindow._open_visual_query_on_file_source` (+
  `_bind_picker_to_file_source`) and a "Visual Query →" button. Verified in-app;
  suite 439 passed (13 pre-existing failures, unrelated). Remaining: Phase 3.
- **2026-06-22 (later still)** — Phase 2b: Manual SQL over a File Source.
  `FieldPickerPanel` local (no-ODBC) mode (`load_local_source`), Manual editor
  `set_file_source`, AuditWindow run/save routing on a `file:<id>` token +
  `_open_manual_sql_on_file_source`, and a "Query in SQL →" button on the File
  Source editor. Verified in-app: cross-file `UNION ALL` + `GROUP BY` via DuckDB.
  Suite: 439 passed (13 pre-existing live-DB2/illustration failures, unrelated).
  Remaining 2c = Visual builder over a File Source.
- **2026-06-22 (later)** — Phase 2a: File Source editor + drag-drop intake.
  `file_source_intake.py` (infer/validate/add-member, the drag-drop validation
  engine), `tabs/file_source_editor.py` (member-file list with OS file drop,
  schema panel, per-file DuckDB preview, Save File Source), `audit_window.py`
  wiring (New Query → File Source → new editor; `open_file_source`). Added a
  `nrows` sample option to `adhoc_source_intake.dataframe_from_adhoc_metadata`.
  Screenshot-verified standalone and in-app on the minipc. Tests:
  `test_file_source_intake.py` 9 green (66 total across file-source + dialect +
  forge). Remaining Phase 2b = Visual/Manual builder integration.
- **2026-06-22** — Created. Phase 1 backbone built + unit-tested on the minipc:
  `file_source.py` / `file_source_store.py` / `file_query_runner.py`, a `DUCKDB`
  dialect in `dynamic_query.py`, and `tests/test_file_source.py` (17 green; the
  `dynamic_query`/`forge_engine` suites stayed green). Decisions: file = data
  source (peer of a DSN); each member file its own table (UNION in SQL); one
  query engine via the `DUCKDB` dialect + `forge_engine.run_manual_sql`.
