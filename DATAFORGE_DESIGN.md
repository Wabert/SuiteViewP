# DataForge — Design & Build Plan

**Living document.** The shared reference for designing and building DataForge,
the Audit-tool utility for joining and querying saved Queries. Update as
decisions change. Status: **design agreed, not yet built on.**

DataForge already exists as a partial implementation under
`suiteview/audit/dataforge/`. This doc records what we keep, what we change, the
agreed vocabulary, the data model, and a phased build plan — so the effort
doesn't drift the way the abandoned `database_manager` "XDB Query" attempt did
(that one is considered a dead end; do not build on it).

---

## 1. Vocabulary

One clean vocabulary, replacing the overlapping internal names
(`QueryObject` / `QDefinition` / "qdef" / `SavedQuery`).

| Concept | Term | Notes |
|---|---|---|
| A reusable saved query from the Audit tool (Cyberlife / Visual / Manual / Flat File) | **Query** | user-facing name for the unified `QueryObject` |
| Cached point-in-time result data (parquet on disk) | **Snapshot** | pairs with **Refresh** |
| Executable compiled form (rendered SQL + schema) | *(internal only)* | this is "qdef" — demote it, never show the term to users |
| The tool / workspace for combining Queries | **DataForge** | |
| A *saved* combination — its own first-class object | **Forge** | parallel to a Query |
| One Query included inside a Forge | **Source** | an editable copy (see §2) |

Plain-English: *"A **Forge** combines several **Queries** as **Sources**; each
Source has a **Snapshot** you can **Refresh**."*

---

## 2. Data model

### A Forge is a first-class saved object
Parallel to a Query. Self-contained and reproducible: opening a Forge tomorrow
gives the same result as today unless the user explicitly refreshes.

### A Source is an editable copy (decided 2026-06-06)
When a Query is added to a Forge, the Forge stores its **own editable copy of
the definition AND its Snapshot data**. Edits to a Source inside the Forge do
**not** touch the shared Query. This keeps a Forge stable — it never silently
shifts because someone edited the upstream Query.

### Two distinct actions (name them clearly in the UI)
- **Refresh** — re-run this Source's (Forge-local) query to pull fresh data →
  updates its Snapshot. *Data* changes; definition does not.
- **Re-sync** — explicitly pull the latest *definition* from the original shared
  Query (when it has been edited upstream). Opt-in, so the Forge never changes
  under the user.

---

## 3. Filter model (defined once, applied once — nothing "moves")

There are two filter **scopes**; the user picks by intent. A filter is never
"defined at one level and pushed to another."

- **Source filter** — narrows *one dataset* (e.g. reinsurance Source →
  `reinsurer = 'XYZ'`). Lives on the Source. Whether the engine runs it inside
  the DB pull or in DuckDB is an **invisible performance optimization** the user
  does not manage.
- **Result filter** — applies to the *joined* output. Lives on the Forge's
  filter tab.

**One visible consequence:** a Source filter shrinks what gets pulled, so it is
baked into that Source's Snapshot. Changing a Source filter marks the Snapshot
**stale** → the badge prompts a **Refresh** ("Refresh to apply"). No
duplication, no removing it elsewhere.

---

## 4. Engine — DuckDB over Snapshots (decided 2026-06-06)

Replace the current sequential `pd.merge` execution with **DuckDB**:
- Register each Source's Snapshot (parquet/DataFrame) as a virtual table.
- Compile the Forge's joins + filters + output selection into **one SQL
  statement** DuckDB runs.

Why DuckDB over pandas (at ~500k rows it's not a speed *necessity*, but):
- Makes the "query" half first-class (future GROUP BY / aggregation / window fns).
- Handles N-way joins and **column-name collisions** via SQL aliasing instead of
  pandas suffix hacks (two datasets both have `company_code`, `policy_number`…).
- Reads parquet Snapshots directly (snapshot-caching synergy).
- Unifies the two build modes (see §5).

---

## 5. UI design

Mirrors the **Visual Query** designer so it feels familiar.

### Two build modes
- **Visual Builder** — the canvas/tabs below. *Compiles to* DuckDB SQL.
- **Manual** — user types DuckDB SQL directly against the Source tables.
- Because Visual compiles to the same SQL Manual uses, the user can flip Visual →
  Manual to hand-tweak the generated SQL.

### Layout
- **Left rail — Sources:** the "Tables" list, but it lists the **Queries** added
  to this Forge. Click a Source → its field list (name + type) shows below.
  Each Source shows a **Snapshot badge**: cached? when was it pulled? + a
  one-click **Refresh**, and stale indication when a Source filter changed.
- **Center — Joins canvas (MS-Access style):** **rebuild target.** Each Source is
  a box listing its fields; drag a field from one box onto a field in another to
  draw a **join line**; click a line to set inner/left/right/outer; multiple
  lines between two boxes = multi-key join. (Replaces today's card metaphor; the
  underlying join model — left/right/keys/how — is unchanged.)
- **Filter tab** and **Display (output columns) tab** — reuse the Visual Query
  widgets. Source filters vs Result filters per §3.

### Performance / freshness model
- **Snapshot-centric:** pull once, iterate instantly against Snapshots.
- **No live pulls on open** (decided 2026-06-06) — opening a Forge loads from
  Snapshots and shows staleness; pulls happen only on explicit Refresh.
- Source filters push down into the source pull when the Source is SQL-backed.

---

## 6. What exists today

Foundation to **keep** (it's sound):
- `dataforge_model.py` — `DataForge` / `DataForgeSource` dataclasses + JSON
  persistence. Right shape; extend for editable-copy + per-Source filters.
- `dataforge_store.py` — list/load/save/delete. Keep.
- `forge_joins_tab.py` — sophisticated card-canvas join UI (drag/resize/multi-key/
  auto-match/state migration). **Join model kept; visual layer rebuilt** to the
  MS-Access style.
- `dataforge_group.py` — the designer widget + current execution path
  (`_run_forge`, pandas merges). **Execution swapped to DuckDB.**
- `query_object.py` / `query_object_store.py` — the unified **Query** model +
  registry. Keep; this is the backbone.
- Parquet **Snapshot** machinery in `qdef_store.py` (save/load/has snapshot) —
  wire into DataForge (not currently used there).

Underlying access: Queries execute via ODBC to pandas DataFrames; DB2 via the
canonical `core/db2_connection.py`, SQL Server via `core/connection_manager.py`.

---

## 7. Phased build plan

- **Phase 1 — Backbone:** ✅ *engine + model + runtime built and unit-tested on
  the minipc (2026-06-06).* New modules:
  - `forge_engine.py` — pure, no-PyQt. `compile_forge_sql()` / `run_forge()`
    turn (Source schemas + `JoinSpec`s + `FilterSpec`s + `OutputColumn`s) into
    ONE DuckDB statement. Sources become CTEs (Source filters apply before the
    join → correct outer-join semantics); Result filters wrap the join in an
    outer SELECT against output names; collision-safe aliasing; N-way left-deep
    join ordering with disconnected-graph detection. Tests: `test_forge_engine.py`.
  - `dataforge_model.py` — `DataForgeSource` now holds the **editable copy**
    (`definition` + `filters` + `SourceSnapshot`), backward-compatible with the
    old `{query_name, alias}` JSON.
  - `dataforge_store.py` — per-Source parquet Snapshot I/O
    (`save/load/has/delete_source_snapshot`, `snapshot_mtime`); atomic JSON via
    `json_store`; `delete_forge` now also removes the Snapshot dir.
  - `forge_runtime.py` — orchestration: `add_query_as_source`, `resync_source`,
    `refresh_source` (Refresh; data pull behind a pluggable `fetch_fn`),
    `set_source_filters` (marks Snapshot stale), `run_saved_forge`. Tests:
    `test_forge_runtime.py`.
  - **Remaining (needs work laptop):** point the designer's `_run_forge`
    (`dataforge_group.py`, pandas) at `forge_runtime.run_saved_forge`, and wire
    the real `default_fetch` against live DB2/SQL. See `WORK_LAPTOP_SPEC.md`.
- **Phase 2 — MS-Access join canvas:** ✅ *built + unit-tested on the minipc
  (2026-06-06).* New modules:
  - `forge_canvas_model.py` — pure, no-Qt `JoinCanvasModel`: Source boxes +
    relationships (multi-key, per-relationship join type), reconcile-on-update,
    `to_join_specs()` / `to_config_joins()` / `get_merge_ops()` conversions,
    state round-trip, and `from_legacy_cards` / `from_legacy_merges` importers.
  - `forge_canvas_view.py` — PyQt6 QGraphics layer: `ForgeJoinCanvas` (drop-in
    for `ForgeJoinsTab`) with movable Source boxes, drag-a-field-onto-a-field to
    draw join lines, click/right-click a line to set inner/left/right/outer or
    delete, collapse boxes. Logic lives in the model; this only renders/edits it.
  - `dataforge_group.py` — designer now imports `ForgeJoinCanvas as ForgeJoinsTab`
    (API-compatible; `set_state` migrates the old `{"cards": …}` format, so saved
    Forges still load). Old `forge_joins_tab.py` kept for rollback.
  - Tests: `test_forge_canvas.py` — 11 headless model tests + 1 offscreen-Qt view
    smoke test (boxes/lines/specs/state round-trip/remove).
  - **Remaining (needs work laptop):** interactive verification of the canvas
    (drag-to-join, line editing, save/reload, legacy-Forge migration). See
    `WORK_LAPTOP_SPEC.md`.
- **Phase 3 — Manual mode:** ✅ *built + unit-tested on the minipc (2026-06-11);
  in-app click-through pending on the laptop.*
  - `forge_engine.run_manual_sql()` — registers each Source DataFrame under its
    user-facing name (spaces/brackets/dots all work, double-quoted in SQL) and
    executes hand-written DuckDB SQL; `prepare_manual_statement()` strips
    trailing semicolons and wraps an outer LIMIT. Errors surface as
    `ForgeEngineError` naming the available Source tables.
  - **Visual→Manual flip:** `compile_forge_sql` with default physical names
    produces SQL that runs *unchanged* through `run_manual_sql` (a non-recursive
    CTE may shadow the registered table it reads from — verified). The designer's
    SQL tab gained a **Forge (DuckDB)** view showing the live-compiled visual
    design; ticking **Manual mode** prefills the editor with it, makes it
    editable (orange border = custom), and Run Forge executes it via DuckDB over
    the loaded Source tables instead of the pandas merge path. The Code tab
    generates a matching duckdb-based Python script.
  - `forge_runtime.compile_saved_forge_sql()` (schemas from Snapshot metadata,
    no pull needed) + `run_saved_forge` honors `config["sql_mode"]/"manual_sql"`;
    `validate_forge` skips join checks in Manual mode (empty editor = error).
  - The designer's `get_config()` now also stores engine-shaped
    `joins`/`outputs`/`limit` (the §1.5 ask) so a saved Forge is runnable
    headless by `forge_runtime` without the canvas.
- **Phase 4 — Aggregation / GROUP BY:** ⏳ *engine landed (2026-06-07); live
  run-path swap pending on the laptop.* `forge_engine.OutputColumn` now carries
  an `agg` (count/sum/min/max/avg, or group/display = plain key);
  `compile_forge_sql` emits a GROUP BY over the non-aggregated outputs and the
  engine accepts the Display tab's vocabulary (`"display"`, uppercase `"COUNT"`).
  `forge_runtime.outputs_from_config` reads the `agg` key. The designer's live
  pandas `_run_forge` *already* aggregates (`groupby().agg()`), as does Visual
  mode's `build_dynamic_sql` (GROUP BY) — so the toggles are functional today;
  this brings the DuckDB engine to parity so the deferred pandas→DuckDB swap
  won't regress aggregation. Tests: `test_forge_engine.py` (+8 aggregation).

---

## 8. Constraints
- DB2 / SQL Server can only be exercised on the **work laptop**, not the home
  minipc (see `WORK_LAPTOP_SPEC.md`). DuckDB + Snapshot + UI logic is testable
  on the minipc with local parquet/flat-file Sources; live source Refresh is not.

## Changelog
- **2026-06-06** — Created. Decisions: build on existing `audit/dataforge`;
  DuckDB engine; editable-copy Sources; no live pulls on open; link+filter first,
  aggregation later; MS-Access-style join canvas as the main UI rebuild.
- **2026-06-06** — Phase 1 backbone built + unit-tested on the minipc:
  `forge_engine.py`, extended `dataforge_model.py`/`dataforge_store.py`, and
  `forge_runtime.py`; `test_forge_engine.py` (12) + `test_forge_runtime.py` (4)
  green. Added Source-vs-Result filter scopes to the engine. `pyarrow` added to
  `requirements.txt`. Created a project `venv` (Python 3.11) — the minipc had
  none. Remaining Phase 1 work (UI `_run_forge` swap + live `default_fetch`)
  deferred to the work laptop.
- **2026-06-06** — Phase 2 MS-Access join canvas built + unit-tested on the
  minipc: `forge_canvas_model.py` (pure) + `forge_canvas_view.py` (QGraphics) +
  `test_forge_canvas.py` (12 tests, incl. offscreen-Qt smoke). Designer swapped
  to `ForgeJoinCanvas` via API-compatible alias with backward-compatible
  `set_state` migration of old card state. Interactive UI verification deferred
  to the work laptop (see `WORK_LAPTOP_SPEC.md` §1.4).
- **2026-06-07** — Code-review pass over the laptop's finished DataForge work
  (`fix/dataforge-review`). Fixed the reported "Save As drops added visual
  queries" bug — Sources now auto-appear on the join canvas (a query added to a
  Forge is visible + saved immediately), while "Delete Table" removals are
  tracked and persisted so they survive reload. Also fixed: a duplicate "View"
  button + duplicate signal in the Queries & Fields dialog, a field-loader
  `QThread` GC/crash risk on fast Source switching, and an engine join-ordering
  bug (RIGHT/LEFT joins attached the wrong side; multi-path outer joins now
  raise instead of silently downgrading). Tests: canvas 13 / engine 14 /
  runtime 10 / query_object 51, all green. The live pandas `_run_forge`
  execution path + its outer-join filter semantics remain deferred to the
  laptop (`WORK_LAPTOP_SPEC.md` §1.5).
- **2026-06-11** — Phase 3 Manual mode built + unit-tested on the minipc:
  `run_manual_sql` in the engine, `compile_saved_forge_sql` + manual-aware
  `run_saved_forge`/`validate_forge` in the runtime, and the designer SQL tab
  rebuilt around a "Forge (DuckDB)" compiled view with a Manual-mode toggle
  (prefill-from-visual, editable editor, manual Run path, duckdb Code-tab
  generation, `sql_mode`/`manual_sql` persisted in the config). `get_config`
  also gained engine-shaped `joins`/`outputs`/`limit`. Drive-by fixes:
  `qdef_store` no longer crashes when `~/.suiteview/qdefinitions` doesn't exist
  yet. Tests: engine 27, runtime 25 (incl. an offscreen-Qt designer
  flip/run/round-trip), canvas 13 — all green. In-app click-through deferred
  to the laptop (`WORK_LAPTOP_SPEC.md` §1.9).
- **2026-06-07** — Phase 4 aggregation landed in the DuckDB engine (minipc):
  `OutputColumn.agg` + GROUP BY compilation in `forge_engine.py`, `agg` parsing
  in `forge_runtime.outputs_from_config`, and acceptance of the Display tab's
  `"display"`/uppercase vocabulary. The live pandas `_run_forge` and Visual
  `build_dynamic_sql` already aggregated, so this is parity for the deferred
  run-path swap, not new user-facing behavior. Also added the cross-cutting
  `suiteview/core/field_dictionary.py` (friendly DB2 column labels) consumed by
  the upcoming field-picker/filter-chip work. Tests: `test_forge_engine.py` 22,
  `test_field_dictionary.py` 22, runtime/canvas/query_object green (one
  pre-existing `query_object` created_at timing assertion flagged separately).
