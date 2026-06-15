# Forge Source Rename — Unification Spec (work-laptop task)

**Status:** deferred to the work laptop (needs live DB2 + interactive PyQt UI to
verify). Authored on the minipc 2026-06-15 alongside the query rename/copy fixes
(see Changelog / commit "Fix DataForge & Object Browser query rename/copy").

**Audience:** the next agent on the work laptop. This is detailed enough to
implement and verify end-to-end.

---

## 1. Why this exists

A DataForge "Source" is an independent, editable **copy** of a query, stored as a
`QueryObject` named `"<source> [<forge>]"` and tagged
`config["dataforge"] = {forge_name, source_name, query_object_id}`, plus a
per-forge `QDefinition` and (optionally) cached parquet snapshots.

Renaming a Source can happen from **three different places**, and each
re-implements the cross-store rename with **different rules**. That divergence is
what makes renames feel "glitchy / don't always stick" inside a DataForge. The
minipc pass fixed the worst data-loss bug (a renamed visual Source orphaning its
SavedQuery design — fixed in all paths) but the paths still **disagree** on
naming, snapshots, collision rules, and live refresh. This spec unifies them onto
one core.

### The three rename paths

| # | Path | File / function | Trigger (UI) | Live refresh of the open builder |
|---|------|-----------------|--------------|----------------------------------|
| 1 | Standalone query | `query_object_store.rename_object()` (`query_object_store.py:340`), called by `_rename_query_object` + `_on_save_changes` in `query_object_viewer_window.py` | Object Browser → a **non-forge** query → Rename / editor Save | n/a (not a forge source) |
| 2 | Browser forge-source | `query_object_viewer_window._rename_forge_source_records()` (`query_object_viewer_window.py:2033`), called by `_rename_forge_query_object` (`:2018`) | Object Browser → a Source **under a forge node** → "Rename Source…" | **No** — only `_notify_forge_list_changed()` (forge-name list) + `self.refresh()` (browser tree) |
| 3 | In-builder Forge Assist | `query_field_picker._rename_qdef()` (`query_field_picker.py:1026`), from `_on_query_context_menu` (`:796`) | DataForge builder → Forge Assist "Queries" list → right-click → Rename | **Yes** — emits `source_refreshed` → `audit_window._on_forge_picker_source_refreshed` (`audit_window.py:950`) does the full update |

Path 1 is the standalone case and is already clean (it's the new shared core for
the *object*-level rename). The unification target is **paths 2 and 3**, which
both rename a *forge Source* but inconsistently.

---

## 2. What each forge path actually does today

### Path 3 — `_rename_qdef` (in-builder, the "good" one)
1. Resolves the `QDefinition` (`self._sources` → qdef_store fallback).
2. Computes a **display name** (strips `" [forge]"`) and a **storage name** that
   *re-applies* the `" [forge]"` suffix via `_storage_name_for_source_label()`
   (`query_field_picker.py:594`). → storage stays `"<source> [<forge>]"`.
3. Resolves `query_object_id`; **collision check is by object_id**
   (`_qdefinition_matches_object_id`, `:622`) — lets you "rename to a stale
   target that is the same source id".
4. Updates `config["dataforge"]` (forge_name/source_name/query_object_id),
   `save_qdef(new)`, renames the **qdef** snapshot
   (`qdef_store.snapshot_path`), deletes the old qdef file.
5. Updates the `QueryObject` (name, config, `field.source` refs), `save_object`.
6. Moves the visual SavedQuery design (added in the minipc pass —
   `saved_query_store.rename_query`, no-op if none).
7. Updates `self._sources`, rebuilds the list, emits **`source_refreshed`**.
8. `_on_forge_picker_source_refreshed` then updates the live group: renames join
   /filter/display references (`dataforge_group._rename_join_sources` `:1553`,
   `_rename_filter_sources` `:1567`, `_rename_display_sources` `:1585`), rebuilds
   the canvas (`joins_tab.update_queries`), persists, refreshes picker + browser.

### Path 2 — `_rename_forge_source_records` (browser)
1. Loads the forge (**requires it to be saved**; raises otherwise).
2. Finds the `DataForgeSource` by name/alias/`definition["id"]`.
3. Sets `obj.name = new_name` **verbatim** — *no `" [forge]"` suffix logic*.
4. **Collision check is by name/alias only** (different rule than Path 3).
5. `save_object(obj)`; moves the visual SavedQuery (minipc pass); deletes the old
   qdef file (`_delete_forge_qdef_file_only` → `qdef_store.delete_qdef_files`);
   `save_qdef(new)`.
6. Updates `source.query_name`/`alias`/`definition`.
7. Renames the **dataforge source** snapshot
   (`_rename_forge_source_snapshot` → `dataforge_store.source_snapshot_path`,
   keyed by **alias**) — only when the alias changed.
8. Rewrites `forge.config` source-name strings generically
   (`_rename_forge_config_sources` `:2125` / `_replace_forge_source_name`),
   `save_forge`.
9. Refresh: `_notify_forge_list_changed()` (forge-name list only) + `self.refresh()`.

---

## 3. The divergences / bugs to fix

1. **Naming convention disagreement (highest impact).** Path 3 keeps the storage
   name as `"<source> [<forge>]"` and shows a stripped display name; Path 2
   stores the **raw typed string** as the name. Rename the same Source from the
   builder vs. the browser → **different stored names** and different display.
   This is the core "inconsistent / doesn't stick the way I expect" feeling.
   → Pick ONE convention (recommend: storage name always carries `" [<forge>]"`,
   display always strips it) and apply it in the shared core.

2. **Two snapshot systems, each path renames only one.** There are two parquet
   caches: the **qdef snapshot** (`qdef_store.snapshot_path(name, forge)`, keyed
   by name) and the **dataforge source snapshot**
   (`dataforge_store.source_snapshot_path(forge, alias)`, keyed by alias). Path 3
   renames only the qdef snapshot; Path 2 renames only the source snapshot. After
   a rename the *other* snapshot is orphaned → stale/empty data on next Run until
   a Refresh. → The shared core must rename **both** (and key the source snapshot
   on the alias, the qdef on the name).

3. **Different live-refresh fidelity.** Renaming from the **builder** (Path 3)
   fully updates the open canvas/joins/filters/picker via `source_refreshed`.
   Renaming the same Source from the **browser** (Path 2) while the builder is
   open leaves the canvas/join cards showing the **old** name until reload. →
   Route Path 2 through the same live-refresh seam when that forge is open as a
   group (find it via `audit_window._dataforge_groups`).

4. **Collision rules differ.** Path 3 = by object_id (allows same-id stale
   target); Path 2 = by name/alias. A rename accepted in one path may be rejected
   in the other. → Use one rule in the core (recommend object_id-based, matching
   Path 3, which is the more correct identity check).

5. **Join/filter/display reference updates use two mechanisms.** Path 3 updates
   live group state (`_rename_*_sources`) *and* the handler persists; Path 2
   rewrites persisted `forge.config` strings generically. They can diverge (e.g.
   Path 2's generic `old.`-prefix string replace vs. Path 3's structured update).
   → The core should update references once, structurally, then persist.

6. **Minor:** Path 3's no-forge branch still calls the cascading
   `qdef_store.delete_qdef` (name-keyed `delete_object` footgun); Path 2 already
   uses the file-only `delete_qdef_files`. → Core should always use file-only.

---

## 4. Already fixed on the minipc (baseline you're building on)

These shipped in the same commit; do **not** redo them, but know they exist:
- `query_object_store.rename_object()` — atomic object rename: moves the
  QueryObject (id-keyed), moves the visual SavedQuery cascade-free
  (`saved_query_store.rename_query`), clears stale QDefinition files
  (`qdef_store.delete_qdef_files`). Standalone rename paths route through it.
- Both forge paths (2 and 3) now call `saved_query_store.rename_query(old, new)`
  so a visual Source's design no longer orphans on rename.
- `query_object_store.is_forge_owned()` is the single forge-owned predicate;
  forge copies are filtered out of the "add a query" lists (selector +
  `queries_dialog`). The dead `query_field_picker._list_query_sources` was removed.

---

## 5. Proposed unified design

Create **one** canonical forge-source rename and have paths 2 and 3 call it.

### 5a. Where it lives
Put the cross-store core on **`DataForgeGroup`** (it already owns the live state
and the `_rename_*_sources` helpers and the snapshot/forge plumbing):

```python
# dataforge_group.py
def rename_source(self, source_storage_name: str, new_display_name: str) -> str:
    """Rename a Forge Source across every store and update the live builder.

    Returns the new storage name. Single source of truth for Source renames —
    the Object Browser and Forge Assist both call this.
    """
```

Responsibilities (consolidating §2 + fixing §3):
1. Resolve the Source by **query_object_id** (canonical identity), fall back to
   name. Compute `new_storage_name` with the **one** naming convention
   (`"<display> [<forge>]"`).
2. Collision check by object_id (reuse `_qdefinition_matches_object_id` logic;
   lift it to a shared location).
3. Rename the `QueryObject` + visual SavedQuery + stale qdef files — reuse
   `query_object_store.rename_object()` for the object/design/qdef-file part,
   then `save_qdef(new)` for the per-forge definition with the updated
   `config["dataforge"]`.
4. Rename **both** snapshots: `qdef_store.snapshot_path` (by name) **and**
   `dataforge_store.source_snapshot_path` (by alias).
5. Update the `DataForgeSource` (`query_name`, `alias`, `definition`,
   `query_object_id`) and the join/filter/display references via the existing
   `_rename_join_sources` / `_rename_filter_sources` / `_rename_display_sources`.
6. Persist (`_persist_source_roster_if_saved` / `save_forge`) and refresh the
   live builder + Forge Assist + browser (the body of
   `_on_forge_picker_source_refreshed` — extract it into a reusable
   `apply_source_rename(old_key, qd)` so both the signal handler and this method
   share it).

### 5b. Rewire the callers
- **Path 3** (`_rename_qdef`): keep the dialog/validation, but delegate the
  cross-store work to `group.rename_source(...)` instead of doing it inline. The
  picker reaches the group via the existing `source_refreshed` signal OR a direct
  reference — prefer keeping the signal so the picker stays decoupled.
- **Path 2** (`_rename_forge_source_records`): when the target forge is open as a
  group (`audit_window._dataforge_groups`), call `group.rename_source(...)` for
  the full live update; when it is **not** open, fall back to a headless
  store-only variant (rename QueryObject + SavedQuery + qdef files + snapshots +
  `forge.config`, then `save_forge`) so a closed forge still renames correctly.
  Factor the store-only part so both share it.

### 5c. Keep the convention in ONE helper
Move `_storage_name_for_source_label` + the `" [forge]"` strip/apply logic to a
shared module (e.g. `dataforge_model` or a small `forge_naming.py`) and use it in
the core and any display code. Today the suffix logic exists only in the picker.

---

## 6. Implementation order

1. Lift the naming helpers (`_storage_name_for_source_label`, the display-strip)
   and `_qdefinition_matches_object_id` to a shared spot; add unit tests.
2. Add `DataForgeGroup.rename_source()` implementing §5a; extract
   `apply_source_rename(old_key, qd)` from `_on_forge_picker_source_refreshed`
   and have both use it.
3. Make `rename_source` rename **both** snapshots (the §3.2 bug).
4. Delegate `_rename_qdef` to the core (remove its inline cross-store block).
5. Delegate `_rename_forge_source_records` to the core (open-forge path) + a
   shared store-only fallback (closed-forge path); delete the now-duplicated
   `_rename_forge_source_snapshot` / `_rename_forge_config_sources` if fully
   replaced, or keep only the store-only fallback's use of them.
6. Delete dead code left behind; run the suite.

---

## 7. Test plan

### Headless (works on minipc and laptop) — add to `tests/`
- Rename a forge Source via the core: assert the QueryObject moved (id stable),
  the qdef moved, **both** snapshots moved, `config["dataforge"]` updated,
  `forge.config` join/filter/display refs updated, visual SavedQuery moved.
- Rename the **same** source via the "browser" entry and the "builder" entry and
  assert **identical** resulting storage name + on-disk state (the convergence
  guarantee — this is the regression test for §3.1).
- Closed-forge rename (forge not loaded as a group) still updates all stores.
- Collision: renaming to an existing *different* source id is rejected; renaming
  to a stale target with the *same* id is allowed.
- Use the temp-dir pattern from `tests/test_query_object.py` /
  `tests/test_query_organizer.py` (`SUITEVIEW_QUERY_OBJECTS_DIR`,
  `qdef_store._QDEFS_DIR`, `dataforge_store._FORGES_DIR`,
  `saved_query_store._QUERIES_DIR`).

### Live UI (laptop only)
With a saved DataForge open in the builder and a real DB2-backed Source:
1. Rename a Source from **Forge Assist** → name updates in the queries list, on
   the canvas Source box, in any join cards/filters/display referencing it; Run
   still works (snapshot not orphaned).
2. Rename the **same** Source from the **Object Browser** while the builder is
   open → the open builder updates immediately (canvas/joins), and the stored
   name matches what path 1 produced.
3. Rename a **visual** Source, reopen it in the visual designer → design loads
   under the new name (no orphaned old-name design).
4. Run the forge after each rename → no empty/stale columns (both snapshots
   followed the rename).

---

## 8. Risks & rollback
- Touches persisted query/forge state across four stores. Take a restore point of
  `~/.suiteview/` (query_objects, saved_queries, qdefinitions, saved_dataforges)
  before live testing.
- Keep the change behind small commits per §6 step so a bad step is easy to
  revert. No production consumers — breaking changes are fine (replace cleanly,
  per the no-back-compat working agreement).
