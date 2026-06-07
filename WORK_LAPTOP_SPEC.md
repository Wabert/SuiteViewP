# Work-Laptop Spec & Deferred-Work Log

**Living document.** Maintained across cleanup sessions. Work done on the home
**minipc** cannot reach the live DB2 mainframe, SQL Server (UL_Rates), or run
the full PyQt UI, so anything requiring live data or interactive testing is
recorded here for the next session **on the work laptop**.

How to use this doc (for the laptop LLM):
1. Start with **§1 Must-Verify** — behavior changes already committed that need
   live testing before they're trusted.
2. **§2 Deferred work** — changes intentionally NOT made on the minipc because
   they need live DB2; pick these up here.
3. **§3 Backlog** — safe but unverified consolidations to do incrementally.
4. Update the **Changelog** at the bottom whenever you complete or add an item.

Branch layout:
- `main` — untouched baseline. Restore tag: `pre-cleanup-2026-06-06`.
- `cleanup/tier0-tier1` — Tier 0 (dead code) + Tier 1 (Excel helper, rates.py fix). Pushed to origin.
- `cleanup/tier2` — Tier 2a (DB2Connection hardening) + Tier 2b (JsonStore).

---

## §1 — MUST VERIFY on the work laptop (changes already made)

These are committed behavior changes that compiled clean but were never run
against live data. Test each before relying on them.

### 1.1 `suiteview/core/rates.py` — parameterized SQL + error surfacing (Tier 1a)
- Rate-lookup SQL now uses `?` placeholders for all values; `_fetch_rates` now
  **raises `RatesError`** on a pyodbc failure instead of returning `None`.
- **Test:** run normal rate lookups (every plancode/sex/rateclass/band/scale
  path) and confirm numbers match the pre-change app. Then force a bad query
  (e.g. wrong DSN) and confirm a visible `RatesError`, NOT a silent `0.0`.
- **Risk:** any caller that previously relied on the silent-None→`0.0` behavior
  will now see an exception. Grep callers of `get_rates` and confirm they handle
  `RatesError` (they were expected to `or []` / surface it).

### 1.2 `suiteview/core/db2_connection.py` — internal refactor (Tier 2a)
- `execute_query` / `execute_query_with_headers` now delegate to private
  `_run` (cursor always closed in `finally`) and `_run_with_retry` (single
  08S01 retry path). Public signatures and return types unchanged.
- **Test:** exercise the real query paths — PolView policy loads, Inforce
  Illustration, Audit/DataForge query execution, schema discovery preview — and
  confirm results are identical. Specifically verify the **08S01 retry** still
  recovers (let a connection go stale / sleep the VPN, then re-query).

### 1.3 Excel "Dump to Excel" exports (Tier 1b)
Four export buttons were migrated to `suiteview/core/excel_export.py`. COM/Excel
can't run on the minipc. Click each and confirm the workbook opens correctly
(headers bold/frozen as before, autofilter, column widths, data types):
- Audit results export — `suiteview/audit/tabs/results_tab.py` (also adds the SQL sheet)
- PolView dumps ×2 — `suiteview/polview/ui/widgets.py`
- DataForge preview export — `suiteview/audit/dataforge/_query_preview_window.py`

### 1.4 DataForge Phase 2 — MS-Access join canvas (interactive UI)
The join UI was rebuilt as a field-linked canvas and **swapped into the
designer** (`dataforge_group.py` now imports
`forge_canvas_view.ForgeJoinCanvas as ForgeJoinsTab`). Pure model + offscreen-Qt
smoke tested on the minipc (`tests/test_forge_canvas.py`, 12 green), but the
interactive gestures could not be exercised headless. **Test in the running app:**
- Add 2+ Sources, **drag a field from one Source box onto a field in another** →
  a join line is drawn; drag more pairs between the same two boxes → multi-key.
- **Click / right-click a line** → set inner/left/right/outer, or delete it
  (Delete/Backspace also deletes the selected line). Right-click a box → collapse.
- Move boxes; confirm lines re-route and positions persist on save/reload.
- **Open a Forge saved with the OLD card UI** and confirm it migrates: the
  `set_state` path detects the old `{"cards": …}` format and rebuilds the
  relationships (verify the joins + join types match what the cards had).
- Confirm `_run_forge` still produces the same result — it consumes
  `get_merge_ops()`, which the canvas reproduces (single-key collapses to scalar).
- **Rollback if needed:** the old `forge_joins_tab.py` is untouched; revert the
  import in `dataforge_group.py` to restore the card UI.

### 1.5 DataForge code-review fixes (2026-06-07, branch `fix/dataforge-review`)
Reviewed the whole `audit/dataforge` module and fixed the issues below. All are
headless-tested, but the ones touching the live UI/data need a click-through:
- **FIXED — added queries vanished on Save As (the reported bug).** Root cause:
  `forge_canvas_view.update_queries` used `add_missing=False`, so a Source added
  to a Forge never appeared on the join canvas unless you right-clicked → "Add
  Query Table". An empty canvas saved nothing, so the Sources looked lost on
  reload. Now available Sources **auto-appear** on the canvas; "Delete Table"
  still removes one and that removal is tracked + persisted (`removed` in the
  joins state) so it survives save/reload. **Verify in-app:** add visual queries
  → they show on the canvas immediately → Save As → reopen → Sources + joins are
  all there. Also verify Delete Table still sticks across reopen.
- **FIXED — duplicate "View" button** in the Queries & Fields dialog (two were
  built; one is removed) and a duplicate `view_query_requested` signal.
- **FIXED — field-loader thread crash risk:** fast query switching could GC a
  running `_QueryFieldLoaderThread` ("QThread destroyed while running"); loaders
  are now retained until they finish. **Verify:** rapidly click between several
  Sources in the dialog and confirm no crash and fields still load.
- **FIXED — engine join-ordering bug:** in `forge_engine`, a RIGHT/LEFT join
  whose right Source was already in the chain attached the wrong side (inverted
  null-padding); now the keyword is mirrored. Multi-path/cyclic join graphs with
  an outer closing edge now raise instead of silently downgrading to inner.
  (Engine still not wired into `_run_forge` — see below — so verify once swapped.)
- Lint: removed unused imports / empty f-string; the unused `forge_joins_tab.py`
  (old card UI) is kept only as a rollback and is no longer imported.

**STILL DEFERRED — live `_run_forge` execution path (pandas, needs live DB2/SQL):**
`dataforge_group._run_forge` still uses pandas `pd.merge`, not the DuckDB engine.
Two known correctness gaps in that pandas path (confirmed in review):
1. Filters are applied to the **merged** result only — there is no source-scope
   pushdown, so a filter on a left-joined Source drops the null rows and quietly
   collapses the outer join (the exact thing the DuckDB CTE engine fixes).
2. 3-way `pd.merge(..., suffixes=...)` can produce unpredictable column names on
   chained merges, which `_resolve_display_column` then has to guess at.
When wiring the engine swap (still the right fix), also add `config["joins"] =
joins_tab.to_config_joins()` + `limit` to `get_config()` so `run_saved_forge`
has explicit joins to read (today only the canvas `joins_tab` state is saved).

---

## §2 — DEFERRED: DB2 connection consolidation (Tier 2c) — NEEDS LIVE DB2

**Goal:** route every DB2 caller through the canonical `DB2Connection`
(`suiteview/core/db2_connection.py`) so they all get pooling, the Office-365
WITH clause, region schema rewriting, and the 08S01 auto-retry — instead of
hand-rolled `pyodbc.connect`.

**BLOCKING CONSTRAINT — do not ignore:** several callers use a *tuned*
connection string that `DB2Connection` does NOT currently replicate:
```
DSN={dsn};BLOCKSIZE=65535;MAXLOBSIZE=0;DEFERREDPREPARE=1;CURRENTPACKAGESET=NULLID
```
A naive swap to `DB2Connection` (which builds only `DSN={dsn}`) would silently
drop bulk-transfer tuning and regress performance on large fetches.

**Recommended approach:**
1. First extend `DB2Connection` to accept optional extra connection-string
   parameters (e.g. `DB2Connection(region, extra_params="BLOCKSIZE=65535;...")`
   or a dict), threaded into `connect()`'s connection string and the pool key.
2. Then migrate the callers below, preserving each one's existing params.
3. Verify large-fetch performance is unchanged (time a bulk pull before/after).

**DB2 caller sites that bypass `DB2Connection`** (verify line numbers — they
shift as the file changes):
- `suiteview/core/schema_discovery.py:351` — table discovery (`DSN={dsn}`)
- `suiteview/core/schema_discovery.py:416` — column discovery (`DSN={dsn}`)
- `suiteview/core/schema_discovery.py:503` — data preview (`DSN={dsn}`)
- `suiteview/core/schema_discovery.py:564` — perf test (**BLOCKSIZE tuned**)
- `suiteview/core/schema_discovery.py:649` — bulk fetch (**BLOCKSIZE tuned**)
- `suiteview/core/odbc_utils.py:123` — DSN test query
- `suiteview/core/connection_manager.py:129` — DB2 test path (duplicates DB2Connection logic)
- `suiteview/ui/dialogs/preview_dialog.py:41` — preview (**BLOCKSIZE tuned**)
- `suiteview/database_manager/xdb_engine.py:361` — `DSN={dsn}` (in try/finally)
- `suiteview/database_manager/xdb_engine.py:420` — mixed DB2/SQL-Server conn string
- `suiteview/database_manager/xdb_engine.py:870` — `DSN={dsn}` (in try/finally)

**NOT DB2 — leave alone / separate concern (SQL Server UL_Rates or Access MDB):**
- `suiteview/core/rates.py:106,110`, `suiteview/core/reinsurance.py:58`,
  `suiteview/abrquote/models/abr_odbc_database.py:92` — UL_Rates SQL Server.
- `schema_discovery.py:754,990,1165,1319`, `add_connection_dialog_v2.py:869` — MS Access driver.
- `scripts/*`, `tests/*` — out of app scope.

---

## §3 — BACKLOG: JsonStore migration (safe, but verify in-app)

`suiteview/core/json_store.py` now provides `read_json` / `write_json` /
`JsonStore` (atomic temp+rename writes, missing-file & corruption handling,
parent-dir creation). Already migrated: `audit/saved_query_store.py`,
`mainframe_nav/mainframe_terminal_screen.py` (`_save_settings`),
`database_manager/dataset_screen.py` (save path).

Remaining sites to migrate to atomic writes (each is low-risk but should be
clicked through in-app once, since they touch user-visible state). Migrate the
**write** paths first — those are the corruption risk:
- `suiteview/file_nav/file_explorer_core.py` — bookmarks (~4489), hidden OneDrive
  paths (~4609/4622), pinned folders (~4641/4652), column widths (~4688/4699),
  panel widths (~4721/4732). Largest cluster; no atomic writes today.
- `suiteview/mainframe_nav/mainframe_nav_screen.py` — splitter sizes (~1975/1993),
  column widths (~2021/2039).
- `suiteview/messaging/message_service.py` — message/profile/inbox files
  (~172, 189, 284, 344) read via `read_text()+json.loads`; reads already guard
  JSONDecodeError, so migrate writes for atomicity.

Note when migrating: keep `indent=2` (JsonStore default) so on-disk format is
unchanged; don't convert a load path that shows an intentional error dialog to
`read_json` (which silently returns the default) — only convert silent loads.

---

## §3b — DataForge Phase 1: live-data wiring (NEEDS LIVE DB2/SQL)

The Phase 1 backbone (engine + editable-copy Source model + Snapshot store +
Refresh/Re-sync orchestration) is built and unit-tested on the minipc with fake
fetchers and synthetic data. Two pieces could not be exercised here:

1. **`forge_runtime.default_fetch`** (`suiteview/audit/dataforge/forge_runtime.py`)
   — the real data pull for a Source. For non-adhoc Sources it runs
   `execute_odbc_query(obj.dsn, obj.sql)`; for adhoc it uses
   `dataframe_from_adhoc_metadata`. **Verify** a Refresh against a live DB2
   Cyberlife Query and a live SQL Server reinsurance Query actually writes a
   correct parquet Snapshot under `~/.suiteview/saved_dataforges/<forge>/`.
2. **Designer execution swap** — `dataforge_group.py::_run_forge` still does the
   old pandas `pd.merge` path. Point it at `forge_runtime.run_saved_forge`
   (DuckDB over Snapshots) and confirm the typical use case end-to-end in the
   UI: Cyberlife policy data + SQL reinsurance, joined on company code + policy
   number (+ coverage index), Source-filtered to one reinsurer. Compare row
   counts/values against the old pandas result before trusting the swap.

Note: `pyarrow` was added to `requirements.txt` (parquet engine for Snapshots);
`pip install -r requirements.txt` on the laptop to pick it up.

## §4 — FUTURE: Tier 3 (larger refactors, not yet started)
- Decompose `suiteview/taskbar_launcher/suiteview_taskbar.py` (very large).
- Decompose `suiteview/database_manager/dbquery_screen.py`.

---

## Changelog
- **2026-06-06** — Created. Tier 2a (DB2Connection retry/cursor hardening) and
  Tier 2b (JsonStore + 3 migrations) done on `cleanup/tier2`. Tier 2c deferred
  (needs live DB2). §1 items from Tiers 1a/1b/2a still need live verification.
- **2026-06-06** — Added §3b: DataForge Phase 1 backbone built/tested on the
  minipc; live `default_fetch` pull + designer `_run_forge` DuckDB swap deferred
  here.
- **2026-06-06** — Added §1.4: DataForge Phase 2 MS-Access join canvas built +
  swapped into the designer on the minipc (12 headless tests green); interactive
  gesture + legacy-Forge-migration verification deferred to the laptop.
- **2026-06-07** — Added §1.5: pulled the laptop's finished DataForge work from
  `main`, reviewed the whole module, and fixed the Save As "added queries not
  saved" bug (canvas auto-add + persisted removals) plus the duplicate View
  button, the loader-thread crash risk, and the engine join-orientation bug.
  Tests: canvas 13, engine 14, runtime 10, query_object 51 — all green. The
  pandas `_run_forge` execution path and its outer-join filter semantics remain
  deferred (need live DB2/SQL). Work on branch `fix/dataforge-review`.
