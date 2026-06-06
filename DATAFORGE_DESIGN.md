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
- **Phase 2 — MS-Access join canvas:** rebuild the join UI as field-linked Source
  boxes with drawn join lines.
- **Phase 3 — Manual mode:** raw DuckDB SQL editor against Source tables; Visual→
  Manual SQL generation.
- **Phase 4 — Aggregation / GROUP BY** (deferred; link+filter first).

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
