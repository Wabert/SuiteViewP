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
- `minipc-handoff-2026-06-07` — **START HERE (see §0).** DataForge "intuitive
  tooling" logic + standards consolidation + a checkpoint of the in-flight
  Illustration 7702/GLP work (§1.6–1.7). Pushed to origin.

---

## §0 — START HERE: 2026-06-07 minipc handoff (branch `minipc-handoff-2026-06-07`)

This branch bundles two bodies of work pushed from the minipc: (a) a DataForge /
Audit "intuitive tooling" pass + a standards-doc consolidation, and (b) a
checkpoint of the in-progress Illustration 7702/GLP work (already detailed in
§1.6–1.7). Everything below is headless-tested on the minipc; the UI and
live-data pieces are for you.

**Get started on the laptop:**
1. `git fetch origin && git checkout minipc-handoff-2026-06-07`
2. `venv\Scripts\python.exe -m pip install -r requirements.txt` (picks up duckdb/pyarrow if missing)
3. `venv\Scripts\python.exe -m pytest tests/ -q` — the suite is now runnable headless. A new
   root `conftest.py` excludes 3 standalone Qt/connection scripts (`test_checkbox_list`,
   `test_ui_display`, `test_connection`) that ran `app.exec()`/live lookups at import and stalled
   collection, and *conditionally* skips the 4 Office/COM tests when `win32com` is missing (on the
   laptop win32com is present, so those run). **Known failures to expect / re-check here:** 4×
   `test_db2_query_performance` (need live DB2) and 5× `test_illustration_*` (the (b) WIP — verify
   per §1.6–1.7). Everything else was green on the minipc.

**What landed this session (verify the UI/live items):**
- **DataForge engine aggregation (#9)** — `forge_engine` compiles `GROUP BY` (`OutputColumn.agg`);
  `forge_runtime.outputs_from_config` reads the `agg` key; the engine accepts the Display tab's
  `"display"`/uppercase `"COUNT"` vocabulary. The live pandas `_run_forge` and Visual
  `build_dynamic_sql` already aggregate — this is **parity** for the DuckDB swap (§3b / §1.5), no
  new UI. (Aggregate toggles were already functional; the "gate them" idea was dropped as wrong.)
- **DataForge pre-flight validation + preview (#4)** — `forge_runtime.validate_forge()` returns
  actionable `ForgeIssue(severity, message, hint)` for: no Sources, duplicate handles, missing
  Snapshot ("→ Refresh"), stale Snapshot (warning), malformed/unknown joins, disconnected Source
  graph ("→ draw a join line"). `preview_saved_forge(limit=100)` runs the engine capped over
  Snapshots. **UI WIRING TODO (laptop):** add a Preview button + surface validation as a banner
  before Run in `dataforge_group.py`.
- **Preview window chrome (#3)** — `_query_preview_window.py` is now a `FramelessWindowBase`
  (purple header, gold border, live W×H footer). **Verify it renders correctly in-app.**
- **Friendly-field dictionary (#6)** — new `suiteview/core/field_dictionary.py` maps cryptic DB2
  columns to human labels (`XTR_PER_1000_AMT` → "Flat Extra per $1,000"; `RT_SEX_CD` → "Sex
  (rate)") with a mechanical humanizer fallback + a `register_labels()` runtime hook. Pure/tested,
  **not yet wired into any UI** — consume it in the field pickers / filter chips (#5/#8) so
  analysts see the friendly name with the technical name in the tooltip.
- **Standards consolidation** — `Agent.md` is now the single standards doc (it absorbed the old
  `docs/CLAUDE.md`, which is deleted) and opens with a **Vision & Voice / Embodiment Brief**. A
  tiny root `CLAUDE.md` `@`-imports `Agent.md` so Claude Code auto-loads it.
- **`query_object` copy fix** — copying a Query now stamps a guaranteed-distinct `created_at`
  (was a microsecond-collision flake in `test_query_object`).

**Remaining "intuitive tooling" roadmap — mostly UI, do in the running app:**
The minipc built/tested the logic cores; these need the app and/or live data:
- **#1 Unify the join canvas** *(biggest; not started)* — generalize the DataForge MS-Access
  canvas (`forge_canvas_model`/`forge_canvas_view`) so **Visual Query mode** uses it too (it still
  uses the legacy card UI `tabs/joins_tab.py`). Needs: schema-qualified DB tables, per-table
  aliases, multi-row ON pairs, arbitrary extra ON expressions, common-table CTEs, FULL joins; a
  converter to the Visual SQL builder's `get_join_infos()` shape; and `{"cards": …}` → canvas
  state migration. Then retire `tabs/joins_tab.py` + `forge_joins_tab.py`. Model work is
  minipc-safe; the drag/ODBC behaviour must be click-tested here.
- **#5 One field picker** — consolidate `FieldPickerPanel` / `QueryFieldPicker` / the
  `queries_dialog` field tree into one, with global field search + inline cached unique-value
  previews, showing `field_dictionary` friendly names.
- **#7 Smart join suggestions** — ghost a suggested join line when two Sources share a column or a
  known composite key (`CK_CMP_CD`/`TCH_POL_ID`, policy_number); click to accept.
- **#8 Friendly filter chips** — lead with is / is not / contains / between / in-list backed by
  cached unique values; demote regex + raw SQL behind "Advanced".
- **#10 Results summary strip + result-scope filter zone + save-result-as-Source** (forge-of-forges).
- **#11 Unify Query/Forge/Source/Snapshot vocabulary** — demote `QDefinition` to an internal
  compiled form; one user-facing `Query` with kinds. Refactor is minipc-safe; left for a focused pass.

---

## §1 — MUST VERIFY on the work laptop (changes already made)

These are committed behavior changes that compiled clean but were never run
against live data. Test each before relying on them.

### 1.15 Illustration — Max Level Allowed is now an engine solve (2026-07-17, minipc)
"Max Level Allowed" no longer schedules the Input tab's closed-form estimate;
Run Values solves the largest level premium the guideline acceptance chain
never caps (`core/solve_max_level_allowed.py`, bisection like Min to Maturity)
so illustrated **Face Amount / DB Option changes** move the answer through the
GLP/GSP recalc. Face/DBO sections are now unlocked under Max Level (same as
Min to Maturity). Verified offline on local data (U0356726: no change
249.29/mo vs closed-form est 242.93; face→25k @yr31 → 124.82; DBO B→A @yr31 →
87.34). RERUN has no Max Level equivalent (only the manual BisectionSearch
macro), so there is no saved-case comparison.
- **Live check:** pick a live GPT UL policy, select Max Level Allowed + a face
  decrease, Run Values, and confirm the projection never shows Premium Capped
  and the final-year AccumGLP/GSP is (nearly) exhausted.

### 1.14 Illustration — IUL input UI: illustrated rates, sweep min (2026-07-08, minipc)
IUL groundwork UI finished on the minipc; three items need live IUL data:
- **Sweep Account Minimum DB2 source** — NOT in the extracted VBA (searched
  cls_PolicyInformation/mdlDataMap/mdlWorksheetFunctions: only fund-ID
  translation + LH_POL_FND_VAL_TOT / LH_FND_ALC / LH_FND_TRS_ALC_SET reads;
  RERUN has no sweep-min named input either). RERUN's "Value Mapping
  (Inforce)" sheet row 52: *"If this amount is different vs E.I., check the
  53 segment"* — i.e. CyberLife screen segment 53; find the backing DB2
  table/column, add a `PolicyInformation` property + load into
  `IllustrationPolicyData.sweep_account_min`. Meanwhile the Input tab's
  Allocations panel carries an editable "Sweep Acct Min $" override →
  `InforceOverrideSet.sweep_account_min` → applied by `scenario_builder`.
- **FND_ALC_PCT scale** — verify percent- vs decimal-form on a live IUL
  policy (`allocations_panel._normalized_allocations` TODO normalizes by
  total > 1.5 heuristic).
- **Fund Values display** — load a live IUL policy and confirm the Policy
  tab's Unimpaired/Impaired/Allocations tables show the index buckets with
  strategy labels ("IX  1 Yr PtP w/ Cap"), and that maturing index buckets
  (VBA: matured + zero-value buckets excluded) don't clutter the list.
- Illustrated-rate defaults are a **6.25% placeholder** for index strategies
  (capped at AG49 max; `DEFAULT_INDEX_ILLUSTRATED_RATE`) and plan GINT for the
  fixed strategy + sweep display row — replace with the illustrated-rate
  table when Robert supplies it.

### 1.13 Illustration — FFL premium waiver targets (2026-07-08, minipc) — VALIDATE vs RERUN
`target_premium.py` now implements the RERUN CalcEngine **IW..JD "FFL Premium
Waivers"** basis: for plancodes with `CompanySub = "FFL"` (new column merged
into `plancode_table.json` from RERUN Rates_Control C12:BE206 via
`tools/merge_plancode_company_sub.py`; `PlancodeConfig.is_ffl` = RERUN
`sblnFFL`), PWoC (benefit type 3, IV=JB) and PWoT/PWSTP (benefit type 4,
IK=JD, CTP KE=JC·vMTP) are computed from cost bases. The non-FFL PWoT target
(units·rate·(1+factor·table)) was implemented in the same change (was a TODO).
- **Headless:** 4 unit tests vs hand-computed formulas
  (`tests/test_illustration_ffl_waiver_targets.py`); full illustration suite
  green (222 passed, only the 3 pre-existing minipc fixture failures).
- **VALIDATE on laptop:** run `rerun_com → run_engine_case → compare_case` on a
  real FFL policy (plancodes like `NU1F3A00`, `1U14I100`) carrying a PWoC
  and/or PWoT benefit — confirm vMTP/vCTP and the IW/IZ/JA/JC columns match
  RERUN row-for-row, including after a face change (IW re-snapshots at the
  change month's COI durations). Also confirm the local rates DB has
  `Select_RATE_BENMTP/BENCTP` rows for the type-4 benefit keys ("49" etc.) on
  FFL plancodes, and export an FFL policy + rates locally for a saved case.
- **Flagged RERUN quirk:** IY (`vMin_Base_Flat`) = TotalSA·flat1 with **no
  /1000 and no /12** — replicated exactly for lockstep, but looks like a
  workbook bug; ask/verify before trusting a flat-extra FFL case.

### 1.12 Illustration — Apply Premium NC..NZ allowance chain (2026-06-20, minipc) — VALIDATE vs RERUN
New `core/premium_allowance.py` (`compute_premium_allowances`) implements the full
RERUN CalcEngine **NC..NZ** premium-acceptance chain, replacing the single-cap
`_guideline_premium_cap`. Adds GP/NPT/TAMRA Alw 0/1/2, Annual Caps, lumpsum
(unscheduled) handling, the per-mode **level allowances** (NR BOY / NS EOY / NT /
NU), Scheduled Prem Cap (NV, locked at BOY), and **levelizing**
(`IllustrationOptions.levelizing_premium`, default False = RERUN INPUT!B35) which
spreads a capped premium level across the year's modal payments instead of
dollar-for-dollar. TAMRA BOY/EOY handles a 7-pay anniversary mid-policy-year.
- **Headless:** 12 pure unit tests pass (`tests/test_illustration_premium_allowance.py`);
  `tools/test_guideline_helpers.py` updated to the new API (32 checks pass).
  Proved (algebra + test) that with levelizing OFF the applied TOTAL premium is
  identical to the prior behavior → the 11 validated scenarios are unchanged.
- **VALIDATE on laptop:** run the `rerun_com → run_engine_case → compare_case`
  loop. Pick/build a case with a **mid-year premium cap + monthly or quarterly
  mode** so the levelized path (NV/NW/NX/NZ) actually exercises; confirm the
  Values-tab "Apply Premium" columns match RERUN's NC..NZ row-for-row. Also spot
  a case where the TAMRA anniversary falls mid-policy-year (NR vs NS).
- **Stubbed (0):** 1035 exchange (Alw 1), loan-repay-from-premium (MH/MI/MJ),
  CVAT `vNPT_Premium` (LI). Re-validate if a case needs any of those.
- **UI (2026-06-20):** Run Controls now has a "Levelized capped premiums (off for
  loans)" checkbox, **checked by default** (`inputs_tab.export_options` →
  `IllustrationOptions.levelizing_premium`). The dataclass default stays **False**
  (RERUN INPUT!B35) — so the **app UI default now diverges** from a bare
  `IllustrationOptions()`. The `run_engine_case` harness must set
  `levelizing_premium` explicitly to mirror each RERUN case's sINPUT flag, or it
  inherits False. Confirm the checkbox renders + drives the Values tab in the UI.

### 1.11 Audit query rename/copy fixes (2026-06-15, minipc) — VERIFY IN UI
Fixes for "renames don't stick" + "a phantom copy shows up in the queries list."
- New `query_object_store.rename_object()` renames a query across **all** stores
  (QueryObject + visual SavedQuery + stale QDefinition files) so it can't revert.
  Standalone Browser rename + editor Save now route through it. Both forge-source
  rename paths now also move a visual Source's design.
- `query_object_store.is_forge_owned()` is the one forge-owned predicate; forge
  `"<q> [<forge>]"` copies are filtered out of the "add a query" selector and the
  Queries dialog (they were appearing as phantom duplicates). Dead
  `query_field_picker._list_query_sources` removed.
- **Headless tests pass** (`tests/test_query_object.py`, `test_query_organizer.py`).
- **Verify in UI:** rename a query in the Object Browser → name sticks after
  reopen (no revert, no duplicate). Add a query to a DataForge → no extra copy in
  the "Select queries…" list. Rename a visual query → reopen its designer (design
  follows the rename).
- **Follow-up (NOT done):** the three forge-rename paths still diverge — see
  **[`docs/FORGE_RENAME_UNIFICATION.md`](docs/FORGE_RENAME_UNIFICATION.md)** for the
  full scope + implementation/test plan. This is the laptop task.

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

### 1.6 Illustration — guideline pipeline completion (2026-06-07, branch `fix/dataforge-review`)
Reverse-engineered the RERUN **CalcEngine** formulas (full column map dumped to
`docs/Illustration_UL/calcengine_map.tsv` via the new `tools/extract_calcengine.py`)
and completed the 7702 guideline machinery in the Python engine. Pure logic is
unit-tested headless (`tools/test_guideline_helpers.py`, 32 green), but nothing
was run against **live UL_Rates / DB2** or in the **UI**. Verify on the laptop:

- **Force-out now floored by GSP (the real bug).** `_apply_guideline_forceout`
  limit is now `MAX(GSP, AccumGLP)` (CalcEngine `KV`), capped by available AV,
  and AccumGLP stops at attained age ≥ 100 (`KU`). Previously it used AccumGLP
  only, forcing money out far too early. **Penny-check** force-outs for an
  over-funded GPT policy against the workbook `vForceOut` (KX) column.
- **Premium capping at acceptance** (`vAppliedScheduledPremium`): applied premium
  is now capped to the guideline room and/or 7-pay room, gated by new toggles
  `IllustrationOptions.conform_to_tefra` / `conform_to_tamra`. The TAMRA cap is a
  **simplified single-cumulative version** (no MEC-status side effects, no
  material-change 7-pay reset, no NPT/CVAT) — adequate for as-is GPT inforce
  (mostly past year 7) but **verify against workbook `NV`/`NZ` for a year-1-7
  policy** if you have one.
- **GP exception premium** (`SY/SZ/TA/TB/TD`) now runs in-engine, gated by
  `IllustrationOptions.allow_exception_prems`. Past safety-net, no CCV, at the
  guideline limit and AV<0 → it pays the premium that brings after-charge AV to
  0, latches on, disables force-out, and protects against lapse (`YQ`).
  **Verify** against the workbook for a guideline-maxed, post-SNET policy with
  the option ON, and confirm it does NOT trigger for a normal underfunded policy.
- **New fixed-loan split** now always routes the gain portion to preferred for
  fixed loans (`TR/TW/TX`); the `preferred_loans_available` gate was removed.
  Set up a loan scenario via INPUT rows 127/128 (Fixed Loan Principle/Accrued —
  keep ≤ AV/SV at valuation) and compare loan buckets to the workbook.
- **PolView ripple (intended):** `polview/services/glp_exception.py` projects
  with `cap_premiums_at_acceptance=False` (no acceptance cap, preserves the
  solver) but force-out is still on, so it now gets the **GSP-floored** force-out
  — GLP-exception and Policy-Support force-out/AV numbers will shift slightly
  (more correct). Re-verify those two PolView tabs against the workbook.

**UI wiring still TODO (no UI testing on minipc):** add three checkboxes
(Conform to TEFRA, Conform to TAMRA, Allow GP Exception Premium) to the
Illustration run controls and build an `IllustrationOptions` to pass at
`suiteview/illustration/ui/main_window.py:263` (`engine.project(..., options=...)`).
The engine + service layer already accept `options`; only the UI control is left.

**Possible follow-up:** force-out does not yet reduce cost basis (CalcEngine
`OD` subtracts force-out); irrelevant until MEC/gain (out of scope) is built.

### 1.7 Illustration — guideline premium (GLP) routines (2026-06-07, branch `fix/dataforge-review`)
New actuarial GLP/GSP module, two independent methods. New files:
`suiteview/illustration/core/commutation.py` (commutation-function engine) and
`suiteview/illustration/core/guideline_calc.py` (GLP/GSP + Fackler reserves).

- **Commutation / PV method** (`calculate_glp` / `calculate_gsp`):
  GLP = (SA·A_{x:n} + PV expenses) / ((1−load)·ä_{x:n}); GSP single-premium form.
  Fully self-contained (pass a `MortalityTable`), **already unit-tested headless**
  — `tools/test_commutation_glp.py`, 21 green, validated against the standard
  identities (A = 1 − d·ä, term+PE = endowment, P = A/ä) and exact no-mortality
  hand values, plus the **Fackler reserve roll** (forward/backward, prospective
  reserve match). Parameterized by age, sex/table, substandard (table mult + flat
  extra), specified amount, DBO (A now; B/C → use the iterative method),
  endowment age, GLP/GSP interest floors, expense loads/fees, and rider/QAB
  charge streams. **Verify on the laptop** against a couple of admin GLP values
  with a real CSO/guaranteed-COI mortality table; tune the expense inputs
  (per-policy fee, per-unit, target/excess load split) to match admin.
- **Iterative / account-value method** (`calculate_glp_iterative`): binary-search
  the level annual premium that endows the contract (AV = face at the 7702
  maturity age) running the real CalcEngine with **guaranteed COI + current
  loads/fees + 4% interest, no bonus, guideline machinery off**. The engine now
  accepts `bonus_override` and `rates_override` for this. **NEEDS LIVE RATES** —
  the caller must build an `IllustrationRates` with the **guaranteed COI scale**
  (UL_Rates `tRates_Ultimate_GCOI` / `get_rates('COI', ..., scale=guaranteed)`);
  that scale id isn't known on the minipc. Verify: (1) build guaranteed-COI rates,
  (2) call `calculate_glp_iterative(policy, guaranteed_rates, glp_rate=0.04,
  endowment_age=100)`, (3) compare to admin GLP and to the commutation method
  (they should be close; differences come from monthly vs annual mechanics and
  corridor). Also confirm the premium-search start alignment (AV=0 at attained
  age, annual premium at anniversary) matches how admin runs it.
- **Policy-change recalc** (`glp_on_change`): new GLP = current + (GLPa − GLPb),
  both at current attained age; works with either method (pass the method in).

Open questions to confirm while testing: exact 7702 maturity age (95–100; default
100), the GLP/GSP interest floors for the in-scope issue years (pre-2021 = 4%/6%;
2021+ contracts use the lower AFR-based floors), and which mortality basis to feed
the commutation method (prevailing CSO vs the contract's guaranteed-COI-implied qx).

---

### 1.8 Illustration — RERUN comparison harness + calc validation (2026-06-08, branch `feat/illustration-rerun-validation`)

Built a fully-offline harness that drives the **RERUN** workbook via Excel COM and
diffs it against the SuiteView engine, using the local SQLite fixtures. Found and
fixed **three** engine bugs; **all four** local inforce cases now match RERUN to
**sub-penny** on the base AV chain, deduction breakdown, interest, values, and
rates. Branch pushed to origin. See `QUESTION_LOG.md` (root) for open questions and
the policy-change plan.

**Harness (all offline, minipc-safe — Excel IS available here now):**
- `tools/rerun_com.py` — load a RERUN Saved Case into an **isolated** Excel
  instance (`DispatchEx`), recalc, dump CalcEngine columns. Run-mode `overrides`
  build face-change/DBO scenarios. **Gotchas baked in:** pywin32 needed
  (`pip install pywin32`, now in requirements); set `Calculation=manual` before
  writing inputs (else a recalc storm hangs Excel); block-write vectors.
- `tools/run_engine_case.py` — engine on a local policy → MonthlyState CSV, with
  per-case TEFRA/TAMRA/exception/exact-days toggles (read from the Saved Case).
- `tools/compare_case.py` + `calc_compare_map.py` — align by valuation date, diff a
  RERUN-ordered grouped column map with detail levels + collapse/drill-down.
- `tools/query_local_fixture.py`, `tools/inspect_illustration_inputs.py` — data-gap
  diagnostics. `extract_calcengine.py` gained names/props/dump modes.
- **JSON arg gotcha:** PowerShell mangles the single-JSON-arg; run these via **Bash**
  with `MSYS_NO_PATHCONV=1`.

**Verify on the laptop (live rates/DB2):**
- Re-run the 3 engine fixes against live UL_Rates / DB2 to confirm they hold with
  real rate scales (they're validated vs RERUN locally): ExactDays interest
  `days/365` (`interest_calc.py`); base-COI flat `TRUNC(flat/12,2)` and **rider
  substandard** now applied (`monthly_deduction.py`).
- **Data gaps to re-export** (block full validation locally):
  (a) U0492070 current **CCV/shadow value** is absent from the fixture (`gav` &
  `ccv_target` both null) — the shadow path can't be validated until exported, and
  the engine seeds shadow from `gav` (GPT GAV), wrong for a CCV policy (see
  QUESTION_LOG Q1). (b) The simple base case **UE000576** never made it into the
  local policy SQLite — `export_local_policy_data.py UE000576 --region CKPR --append`.
  Now also blocks RERUN **Saved Cases 5 and 6** (UE000576 clones: case 5 =
  withdrawal yr 11 + DBO A→B at age 65; case 6 = 3,000 loans yrs 12-15). The
  scenario SHAPES are validated EXACT on U0688012 (QUESTION_LOG §H), so once
  the export lands the cases should run as-is via the standard harness loop.
- **NEW engine change kinds need RERUN references** (QUESTION_LOG §I): the
  dynamic Input tab exports RATE_CLASS / SUBSTANDARD (table rating) /
  RIDER_DROP policy changes and the engine applies them, but none is
  validated. The workbook has `sINPUT_Rateclass_Change_NewRateclassCode/_Date`
  and per-rider change inputs — build references via `rerun_com.py overrides`
  and compare like the face/DBO changes were.
- **Report tab spot-checks on live data**: insured/agent names + address on
  the cover (blank in fixtures), the '#4/#5/#6' benefit → ABR rider-name
  mapping, suspended-policy banner against a real suspended policy, and the
  Input tab's rider buttons' premium-paying heuristic (coi_rate/premium).
- **UI click-tests** (no UI on the minipc beyond render mocks): dynamic Input
  rows (year↔age sync feel, ＋/− behavior, overlap warning), rider
  keep/change/drop dialog, Charges chart hover, Report tab scrolling.
- **TAMRA 7-pay** (`calculate_7pay_premium`, `guideline_calc.py`) — penny-validate
  against RERUN's `Guideline_Premiums` (CalcEngine `KY`) with the guaranteed-COI
  table; confirm the expense/interest basis (QUESTION_LOG Q2).
- **GSP $0.05** — replicate RERUN `KS = INT(GSP/12*100)*12/100` once force-out is
  active (QUESTION_LOG Q3).

**Policy changes (NOT implemented — full plan + RERUN reference in QUESTION_LOG §D):**
face increase/decrease + DBO change create/modify coverage segments and trigger a
guideline + 7-pay recalc (building blocks `glp_on_change` + `calculate_7pay_premium`
are ready). Reference captured: RERUN creates a new segment (Cov2) at a face
increase and recalcs guideline at the change anniversary.

### 1.9 DataForge Phase 3 — Manual mode + Forge SQL view (2026-06-11, minipc)

The SQL tab in the DataForge designer was rebuilt (`dataforge_group.py` →
`ForgeSqlTab`): a **Forge (DuckDB)** button shows the single DuckDB statement
compiled live from the visual design; a **Manual mode** checkbox makes it
editable (prefilled from the compiled SQL — the Visual→Manual flip) and Run
Forge then executes the hand-written SQL via DuckDB over the loaded Source
tables instead of the pandas merge path. All engine/runtime/designer logic is
headless-tested (engine 27 / runtime 25 / canvas 13 green), but **click-test
in the running app**:

- Open a Forge with 2+ Sources → SQL tab → **Forge (DuckDB)** shows compiled
  SQL; per-Source buttons still show each Source's pull SQL; switching tabs
  recompiles (edit a join/filter and re-check).
- Tick **Manual mode** → editor prefills with the compiled SQL, goes editable
  (white bg, orange border), hint text changes. Run Forge → results match the
  visual run for the same design (compiled SQL semantics: Source filters apply
  *before* outer joins — the pandas path's known post-merge filter bug means
  outer-join + filter cases may legitimately differ; the SQL result is the
  correct one).
- Hand-edit the SQL (e.g. add a WHERE) → Run → results reflect the edit; the
  Code tab shows a duckdb-based script; Save → reopen → Manual mode + SQL are
  restored (config `sql_mode`/`manual_sql`).
- Untick Manual mode → visual design runs again (pandas path unchanged).
- Run with Manual on + empty editor → friendly warning, no run.
- Saved-Forge config now also carries engine-shaped `joins`/`outputs`/`limit`
  (from `get_config`) — spot-check a saved Forge's JSON under
  `~/.suiteview/saved_dataforges/`.

### 1.10 Query Browser groups/IDs/colors + Append Tables backbone (2026-06-11, minipc)

The Query Object browser was rebuilt on a bookmark-style organizer
(`audit/query_organizer.py`; design in `DATAFORGE_DESIGN.md` §8) and queries
got permanent unique ids (`QueryObject.id`, id-keyed store files with
in-place legacy migration — the first browser open MIGRATES
`~/.suiteview/query_objects/*.json` to `name__id8.json`; verify it's clean).
All headless-tested (227 green); **click-test in the running app:**

- **First open:** old kind-categories appear as seeded GROUPS (Cyberlife,
  Visual Queries, Manual SQL, File Sources); every query shows `Name [DSN]`
  with its build-mode color chip + tint; Forges appear as heavier orange
  ⚙ nodes with their Source copies under them.
- **Groups:** right-click background → New Query Group; rename/clone/delete
  (delete keeps queries, they fall to root). Clone Group deep-copies every
  query inside (same names, new ids — verify both copies open/run).
- **Drag-drop:** query → group / root / another group (position respected);
  query → Forge prompts Move in / Copy in (Move consumes the standalone
  query); Source dragged out of a Forge prompts Copy out / Move out; groups
  and forges reorder at root level. After every drop the tree must match
  `~/.suiteview/query_organizer.json`.
- **Forge ops from the browser:** Clone DataForge (Sources + Snapshots —
  run the clone immediately, no Refresh needed), Remove from DataForge
  (Source + Snapshot + forge-local copy records gone).
- **Duplicate names:** copy a query into two groups, rename one — confirm
  the other is untouched (ids, not names). DataForge Re-sync against a
  duplicated name resolves to the newest — acceptable until the identity
  pass (#11) — but confirm nothing crashes.
- **Build-mode selector:** dropdown entries show mode chips; the button
  takes the active mode's color (Cyberlife blue, Visual teal, Manual SQL
  violet, File moss). Confirm legibility against the navy header.
- **Append Tables (engine/model only so far):** `config["appends"]` runs
  through both the pandas path and the compiled DuckDB SQL. The canvas
  VIEW (the group box with stacked member header bars per design §9) is NOT
  built yet — next minipc session; do not expect to see appends on the
  canvas, but a hand-edited saved-forge config with appends should run.

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

## §3c — File Sources: legacy cleanup + interactive confirmation (NEEDS APP)

Phases 1, 2a, 2b, 2c, and 3 are all built and verified on the minipc (the app
runs + screenshots here). What's left for the laptop is migration-apply on real
data and removing the now-dead legacy code. See the bottom of this section.

Phase 1 backbone built + unit-tested on the minipc (2026-06-22): flat files
become a first-class **File Data Source** (peer of a DSN, each member file its
own table), queried by the existing builders compiled to **DuckDB**. See
`docs/FILE_SOURCES.md` for the full design. New, pure/headless modules:
- `suiteview/audit/file_source.py` — `FileDataSource`/`FileColumn`/`FileMember`
  (format + parse_spec + column schema + member-file list; parse_spec is the
  same dict shape `adhoc_source_intake` consumes).
- `suiteview/audit/file_source_store.py` — id-keyed, atomic JSON store at
  `~/.suiteview/file_sources/` (`SUITEVIEW_FILE_SOURCES_DIR` override).
- `suiteview/audit/file_query_runner.py` — loads members via the existing
  intake readers, registers each as a DuckDB table, runs SQL through
  `forge_engine.run_manual_sql`; `run_query` returns ODBC-shaped
  `(columns, rows, column_types)`.
- `dynamic_query.py` gained a `DUCKDB` dialect (double-quote idents + `LIMIT`).
- Tests: `tests/test_file_source.py` (17, green); `test_dynamic_query` +
  `test_forge_engine` still green (40).

**Built + verified on the minipc (2026-06-22) — re-confirm interactively, then
proceed with the cleanup below:**
> **Update (2026-06-22):** the standalone editor below was later **consolidated
> into the Data Sources dashboard** — `tabs/file_source_editor.py` is deleted; the
> dashboard (`_SourceDashboard` in `query_object_viewer_window.py`) is now the one
> editable add/edit/view screen. Format prompts live in
> `file_source_format_dialogs.py`; column-name logic in `file_source_intake.py`.
- **2a** Editor (now the dashboard): format/columns from the first file,
  member-file list with **OS drag-and-drop** add + schema validation, per-file
  DuckDB preview, Save File Source. Reached via the Data Sources tab.
- **2b** Manual SQL over a File Source: `FieldPickerPanel.load_local_source`
  (no-ODBC), `set_file_source`, run/save routing on a `file:<id>` token,
  "SQL Query →" button. (Verified: cross-file `UNION ALL`+`GROUP BY`.)
- **2c** Visual builder over a File Source: `detect_dialect` → `DUCKDB`,
  `DynamicQuery` run paths branch to `file_query_runner`,
  `_open_visual_query_on_file_source` (tables inferred from dragged fields),
  "Visual Query →" button.
- **3** `dialogs/file_source_browser.py` (open/delete saved sources) + an
  "Open…" button on the editor; `migrate_adhoc_to_file_source` +
  `tools/migrate_adhoc_sources.py`.

**Remaining (laptop):**
1. **Run the migration on real data.** The minipc has no legacy `adhoc_source`
   objects. On the laptop: `venv\Scripts\python.exe tools/migrate_adhoc_sources.py`
   (dry run) to review, then `'{"apply": true}'` to convert + remove originals.
2. **Remove the dead legacy adhoc code** once #1 is done and the browser is
   confirmed clean: `tabs/csv_excel_object_editor.py`, the `OBJECT_KIND_ADHOC_SOURCE`
   branches in `query_object_viewer_window.py`, and the adhoc factories in
   `query_object.py` / `adhoc_source_intake.py` (the `*_adhoc_*` /
   `query_object_from_file` QueryObject path — keep the pure readers used by
   `file_source_intake`). Drop the legacy `_start_csv_excel_object` /
   `open_csv_excel_object` wiring in `audit_window.py`.
3. **Optional:** fold the File Source browser into the unified Object Browser
   (DataForge design §8) instead of a standalone dialog.

## §4 — FUTURE: Tier 3 (larger refactors, not yet started)
- Decompose `suiteview/taskbar_launcher/suiteview_taskbar.py` (very large).
- Decompose `suiteview/database_manager/dbquery_screen.py`.

---

## §5 — Local rate-export gaps found by the offline RERUN pipeline (2026-07-16)

The offline RERUN tooling (`tools/rerun_load_local_rates.py` +
`tools/rerun_build_case_inputs.py`) surfaced three gaps that need a laptop
export session (`tools/export_local_rate_data.py` on the UL_Rates DSN):

1. **`Select_RATE_SHDINT` missing from `bundled_data/dev/rates.sqlite`** — the
   Span_ShadowINT block cannot be loaded offline. Only matters for plancodes
   with `ShadowIntRateCode = "Table"`: 1U145700, 1U146000, 1U146100,
   1U146200, 1U146300. (1U146600/UE050703 uses a flat 0.045 — unaffected;
   verified clean offline 2026-07-16.) Add SHDINT to the export script if a
   test policy on those five plancodes is ever needed.
2. **Plancode `1U144600` (IUL08) has no rates in the local export** — all five
   DEV1000x offline IUL test policies use it. Export its COI/SCR/EPU/targets.
3. ~~RERUN `tBenefitDefinitionFile` has no 1U plancodes~~ — **RETRACTED
   2026-07-16 (later)**: a proper scan found 492 `1U*` keys; benefit
   definitions ARE fully hard-coded in the workbook. The case-7 #N/A was a
   builder bug (blank benefit code), fixed the same day. `skip_benefits`
   remains available but is not normally needed.
4. **Benefit-TARGET-index rates (`tRates_Benefit_Targets`) not mirrored
   locally (2026-07-17)** — RERUN looks the PW target rate up by the
   Rates_Control TARGET index (key `sRates_PW_TargetIndex`&Sex&"0"&"0"&IssueAge,
   e.g. `300M00024` → 0.044 for 1U135100) while the app's
   `Rates.get_ben_mtp` keys `Select_RATE_BENMTP` by benefit code `39`/sex/
   rateclass/band (→ 0.042). The 2-bp PW-rate difference makes the recomputed
   vMTP after a policy change land ~0.8/yr low (36.04 vs 35.97 monthly on
   U0356726-DBO), which ripples pennies into the PW charge inside the
   guideline recalc (GLP/GSP/7-pay ~0.12–0.68 off after the change; before-
   change solves are exact). Laptop: export the target-index keyed rows
   (Select_RATE_BENTRG or equivalent) and point the PW/PWST target lookups at
   them. Repro: `tools/repro_pw_target_rate_gap.py` — patching the PW rate to
   0.044 makes the recalc'd 7-pay exact and GSP/GLP land within one
   monthly-cent floor step of RERUN.
5. **IUL AG49/WAIR engine crediting — RERUN comparison (2026-07-18)** —
   the engine-side asset charge (SS–SX), variable-loan credit spread (VV), and
   WAIR crediting (US–VL) are implemented in
   `suiteview/illustration/core/iul_crediting.py` and unit-tested
   (`tests/test_illustration_iul_crediting.py`).
   **RAN LOCALLY (2026-07-18 evening, minipc)** on Saved Cases 9
   (UE013383/1U145500) and 12 (UE209026/1U147500) — case 7 is unusable as
   stored (the pre-fix build with a blank PW benefit code; every CalcEngine
   month #N/As; case 9 is its same-day fixed rebuild). Workbook:
   `docs/Illustration_UL/RERUN (v20.0) local IUL.xlsm` — a rate-loaded copy of
   the local workbook (Span blocks now hold 1U143900 + 1U135100 + 1U146600 +
   1U145500 + 1U147500 together, so cases 1–6 still run; created as a copy
   because the user's Excel held `RERUN (v20.0) local.xlsm` open read-only).
   Comparison workbooks in `docs/Illustration_UL/`:
   `rerun_vs_app_iul_blend_*.xlsx` (blend, cases 7/9/12, 900 mo),
   `rerun_vs_app_iul_wair_*.xlsx` (WAIR, 9/12), `rerun_vs_app_iul_blend_ip_*`
   (constructed IP-allocation asset-charge run), `rerun_vs_app_iul_vbl_loan_*`
   / `rerun_vs_app_iul_wair_vbl_*` (constructed variable-loan runs).

   **VERIFIED (engine == RERUN):** blended crediting rate — the effective
   (multiplier-inclusive) TRUNC4 blend — exact (1e-6) for all 900 months both
   cases, and the IP-variant proves RERUN UO/PolicyRates!CH4 is the effective
   blend; AG49 regime resolution (case 9 issue 2017 → index 2, case 12 issue
   2022 → index 3 with the asset charge correctly gated to zero on both
   sides); asset charge — SU (Debug J) exact every month, SV (Debug K)
   bit-identical at month 1 (6.865697519812322 both sides), residuals =
   SU/12 × ΔAV drift; WAIR — VI exact on the valuation row (0.053 / 0.0047),
   VJ beginning-of-year recompute + hold matches structurally with onset
   deltas 7e-5–9e-5 fully explained by the deduction-input drift below;
   variable-loan spread — both sides accrue at exactly UO − 0.01 = 0.043
   (spread branch beating the 0.02 input rate), identical 17.9167/mo; the
   documented RERUN TAV VB typo (UG for UO) is **inert** in all these runs
   because VB only feeds VC under sInput_ApplyPremToLoan, which is FALSE.

   **ENGINE BUGS FOUND (not IUL-crediting; (a) fixed, (b) open):**
   (a) *Band boundary* — **FIXED 2026-07-18 (same day).** The true rule
   (RERUN Rates_Control column CZ "Use Band Table 2 by Issue Date", the ONLY
   issue-date-dependent banding in the product line): thresholds are always
   INCLUSIVE (`face >= threshold`, RERUN's approximate VLOOKUP), but for the
   14 plancodes in CZ12:CZ32 (1U145500..1U146700, 1U536A00–C00) band 3
   starts at 250,001 (mBandTable1) when the policy issue date is BEFORE
   CZ9 = 2018-10-01 and at 250,000 (mBandTable2 = the UL_Rates BANDSPECS
   thresholds) on/after. UE013383 (issued 2017, face exactly 250,000) →
   band 2, proven by the system's own LH_POL_MVRY_VAL CINS 24.12 = band-2
   dur-9 rate 0.0967 × NAR/1000. Fix: `Rates.get_band(..., issue_date=)` +
   `BandTable2IssueDate` in the plancode table (merged by
   `tools/merge_band_table2_date.py`); unit tests `tests/test_rates_band.py`;
   re-run evidence
   `Testing/details/rerun_vs_app_iul_blend_bandfix_20260718_200353.xlsx`
   (COI exact through mo 528; residual AV drift 30,714 → 998.24 = bug (b)
   + PW-cease/MTP-mapping divergences below).
   (b) *PoAV charge missing* — plancode_table PoAV_Table is a table code
   ("1"/"2"/"3") on the IUL plans, but `monthly_deduction.py:559` and
   `rate_loader.py:181` gate on `poav_code == "Table"` → av_charge silently 0.
   RERUN charges SI = MAX(0, OO × SH) inside vTotalFees; the system's
   EXP_CRG_AMT confirms (~7–17/mo, policy years 1–10 only). Both cases.

   **RERUN divergences flagged (engine matches the system, not RERUN):**
   PW cease — RERUN stops the PW charge at attained age 60 (its benefit
   definition table); the engine honors the system's recorded BNF_CEA_DT
   (2038-07-14 = one year later) → 12 × 34.94 one-year window. Debug File
   AI is `vMTPwoPW` (MTP *without* the PW benefit) while the engine carries
   the full system MTP → the flat 402.72/yr (case 9) / 251.16/yr (case 12)
   "MTP" delta is a mapping artifact, not a calc difference.

   **Still needs the laptop:** benefit rates for 1U147500 — local
   Select_RATE_BENMTP/BENCTP/BENCOI have **no rows** for that plancode, so
   case-12's PWST/GIR charge deltas (−0.25/mo early, −60/mo late) cannot be
   classified until the benefit-rate rows are exported; plus the §5.4
   target-index rates, Select_RATE_SHDINT (§5.1), and 1U144600 (§5.2).

   Tooling: `run_engine_case.py` now takes `iul_wair`,
   `use_policy_ag49_regime`, `current_interest_rate`, `iul_declared_rate`,
   `iul_asset_charge_rate`, `allocations`, `swam`, `variable_loan_rate`;
   `compare_rerun_vs_app.py` auto-wires IUL inputs from the Saved Case (blend
   computed exactly like INPUT B52/E52) and takes `wair` (sIntCalcMethod=3
   override + engine flag), `overrides` (RERUN named ranges, incl. vector
   rows), `app_extra`, `tag`; `rerun_debug_map.py` J/K now map to
   `asset_charge_rate`/`asset_charge` (K previously pointed at the PoAV
   `av_charge`). New helpers: `dump_saved_case_summary.py`,
   `summarize_compare_workbook.py`, `dump_sheet_formulas.py`,
   `wait_for_file.py`.

---

## §6 — GLP forecast batch → management exhibit (NEEDS LIVE DB2) (2026-07-18)

The four-forecast GLP batch over `docs\Illustration_UL\GLP Limit Calc v2.xlsx`
(17,324 policies, only ~5 rows run so far) needs live DB2. On the laptop:

1. Run the batch (resumable via `--start-row` / sidecar replay):
   `venv\Scripts\python.exe tools/run_glp_forecast_batch.py "docs\Illustration_UL\GLP Limit Calc v2.xlsx"`
2. Build the management exhibit from the completed workbook:
   `venv\Scripts\python.exe tools/build_glp_forecast_report.py "docs\Illustration_UL\GLP Limit Calc v2.xlsx"`
   → writes `docs\Illustration_UL\GLP Funding Outlook.html` (self-contained,
   email/print-ready) and prints a JSON audit summary (tier counts, label
   vocabulary seen, bypass reasons, unclassified rows — should be 0).

The report classifies every row into five MUTUALLY EXCLUSIVE categories
(Robert's spec 2026-07-18): Sustained (cur-prem = Maturity) / Increase fixes
it (exc date = none) / Exceptions required (exc date is a date; the
"front-loading only" policies — abs-max run = Maturity — are a SUB-METRIC of
this category, not their own band) / No Solution / Not Classified (bypass).
Accepts current labels ("(none)") and legacy ones ("not needed"). Centerpiece
is an interactive by-form breakdown: click a category chip or funnel segment
→ forms ranked by that category (share-of-form bars); open with `#cat=D` to
preselect. Exhibit verified on the minipc against a 2,400-row synthetic
workbook (`tools/make_glp_report_demo_workbook.py`, form-correlated mix).
Sanity checks after the real run: `unclassified_count` = 0 and no unexpected
strings in `labels_seen`; exception-date rows with a blank abs-max column are
counted in `missing_abs_max` (not front-load-capable, conservative).

---

## Changelog
- **2026-07-17 (minipc)** — Guideline expense-basis fix (7702 rule: guaranteed
  COI + statutory interest + CURRENT expenses): `build_guideline_basis` now
  includes rider charge streams (CTR/spouse term, current COI — the same
  `rates.rider_rates` the deduction uses), excludes ADB (non-QAB), and gates
  base COI at PremiumCeaseAge / fee at MaturityAge (RERUN Guideline_Premiums
  COIR/Fee). `compute_target_premiums` gained rider targets (CTR hardcoded
  7.80/unit/yr per Rates_Control, term riders from their own plancode's
  MTP/CTP tables). U0356726-DBO before-change GLP/GSP now match RERUN to 12
  decimals; after-change within cents (residual = §5.4 PW target-index rate).
- **2026-06-22 (minipc, later)** — File Sources Phases 2a/2b/2c/3 built +
  screenshot-verified in-app on the minipc (§3c updated): the File Source editor
  (drag-drop member files), Manual SQL + Visual builder over a File Source via
  DuckDB, and a File Source browser + adhoc→FileDataSource migration tool.
  Committed on `feat/file-sources`. Remaining laptop work: run the migration with
  `apply=true` on real data, then delete the dead legacy adhoc code (§3c).
- **2026-06-22 (minipc)** — File Sources Phase 1 backbone (added §3c): flat
  files reworked into a first-class `FileDataSource` (peer of a DSN, each member
  file its own DuckDB table) queried by the existing Visual/Manual builders.
  New pure modules `file_source.py` / `file_source_store.py` /
  `file_query_runner.py`; `dynamic_query.py` gained a `DUCKDB` dialect.
  Design captured in `docs/FILE_SOURCES.md`. Tests: `test_file_source.py` 17
  green; `test_dynamic_query` + `test_forge_engine` 40 green (no regressions).
  Builder integration + editor rework + migration deferred to the app (§3c).
- **2026-06-15 (minipc)** — Audit query rename/copy fixes (added §1.11):
  atomic cross-store `query_object_store.rename_object()` (object + visual
  SavedQuery + stale qdef files) so renames stick; both forge-source rename paths
  now move a visual Source's design too; one `is_forge_owned()` predicate filters
  forge copies out of the "add a query" selector + Queries dialog (kills the
  phantom duplicate); removed dead `query_field_picker._list_query_sources`;
  consolidated `qdef_store.delete_qdef_files` / `saved_query_store.rename_query`
  /`delete_query_file`. Headless suite green (261 passed; remaining failures are
  the known live-DB2/illustration ones). Scoped the deferred forge-rename
  unification into `docs/FORGE_RENAME_UNIFICATION.md` (laptop task, §1.11).
- **2026-06-11 (minipc, evening)** — Query Browser reorganization + Append
  Tables backbone (added §1.10): QueryObject unique ids + id-keyed store with
  legacy migration; `query_organizer.py` (groups/forge refs/reconcile/seed/
  clone); browser tree rebuilt on it with build-mode colors, `[DSN]` tags,
  weight hierarchy, drag-drop and group/forge clone; build-mode selector
  colored; engine/canvas-model/pandas support for Append Tables with config
  persistence.
- **2026-06-12 (minipc)** — Append Table canvas view completed: brown
  AppendBox rendering, right-click Add/Rename/Delete, query-list and
  canvas-source drops, member removal, shared-field/error/type-warning states,
  AppendTable-to-Source joins, virtual `[Append]` Forge Assist entries for
  Display/Filter picking, case-insensitive exact shared-field matching, and
  row-preserving append semantics (`UNION ALL` / pandas `concat`). Focused
  suite: DataForge canvas + engine 51 passed. Interactive laptop click-test is
  still pending under §1.10.
- **2026-06-11 (minipc)** — DataForge Phase 3 Manual mode (added §1.9): the
  engine gained `run_manual_sql` (Sources registered under their user-facing
  names; compiled Visual SQL runs unchanged in Manual mode), the runtime gained
  `compile_saved_forge_sql` + manual-aware `run_saved_forge`/`validate_forge`,
  and the designer's SQL tab became the Forge (DuckDB) view + Manual-mode
  editor. `get_config` now stores engine-shaped `joins`/`outputs`/`limit`
  (closing the §1.5 config ask). Drive-by: `qdef_store.load_qdef`/`list_qdefs`
  no longer crash when the qdefinitions dir doesn't exist; the stale
  `FakePolicyInfo` in `test_glp_exception` was completed (missing
  `age_at_maturity`/TAMRA fields), un-breaking that test. Full suite on the
  minipc: 208 passed; remaining failures are the documented live-DB2 ones
  (4× db2_query_performance, 2× illustration_md_check).
- **2026-06-10 (minipc)** — Guideline calcs OWNED by the engine + Illustration UI
  overhaul. (a) New `monthly_guideline.py`: monthly accumulated-value endowment
  solve (linear in premium, exact, no compression, unlimited recalcs) —
  penny-matches the workbook's Guideline_Premiums calculator at issue AND at
  every captured policy-change before/after; all four U0688012 scenarios now
  `all_ok` with the engine computing its OWN GLP/GSP/7-pay recalcs (no injected
  values). Workbook intent decoded: 7-pay is a NET premium (no fees/EPU/loads);
  GSP + 7-pay always solve level-DB (only GLP honors the DBO); non-material
  changes re-solve 7-pay from the ORIGINAL period start (new
  `tamra_7pay_start_av` from SVPY_BEG_CSV_AMT); benefits cease at payup (gate
  added to monthly deduction too). (b) "Find GP/TAMRA by Search Routine"
  toggle (default off): engine premium-solve with guaranteed COI / statutory
  rate / current expenses — GLP within $1.56, GSP $46.68 of the formula on the
  face-increase check; 7-pay ~7% higher BY DESIGN (search includes expenses).
  (c) UI: Inputs tab reordered (Transactions first) + valuation/monthliversary/
  first-forecast banner + scheduled premium prefilled from billing; NEW Values
  "Overview" tab — KPI chips, hand-painted AV/SV/DB/premium chart (hover
  readout, click-year-to-jump, legend toggles; now on its OWN "Chart" sub-tab
  for full height), annual⇄monthly drill-down ledger with right-click Excel
  dump. All Values group grids restyled via the new opt-in
  `FilterTableView.apply_ledger_style()` (no grid/zebra/row numbers, 17px rows,
  11px text, tinted compact header — themable per sub-app, stock style
  untouched for other consumers) + `autofit_columns_to_data()`: columns size to
  the FORMATTED DATA (not headers) and long header names word-wrap onto 2-3
  lines (floor = longest header word so wraps never become letter stacks) —
  roughly doubles visible columns per screen. Long RERUN-derived column names
  got compact wrap-friendly display relabels (COMPACT_HEADER_LABELS in
  values_tab.py — display-only, DataFrame keys unchanged). NEW drill-down
  system on the Values tab: "☰ Find Value" navigator rail (search every column
  across all group tabs, click to jump + highlight), "Inspect Month" panel
  (select any row anywhere → that month's full premium→deduction→interest
  waterfall + guideline/TAMRA/target state), and Overview double-click
  drill-through (jumps to the owning detail tab at that month and opens the
  inspector). **Laptop follow-ups:** click-test the
  Overview interactions (hover/legend/expand/Excel dump) and the GP-search
  toggle in-app; re-validate vs live UL_Rates; remaining engine gaps in
  QUESTION_LOG §E (rider/CCV target premiums, TEFRA-binding scenario, B→A,
  mid-year AccumAdjust).
- **2026-06-09 (minipc)** — Illustration policy-change pipeline COMPLETE and
  validated EXACT (0.0 delta, all comparison groups, 40 months) vs RERUN on
  U0688012 for base + face increase + face decrease + DBO A→B; U0492070 and
  U0656998 base re-validated at 0.0. New `target_premium.py` computes vMTP/vCTP
  from rates (recomputed at policy changes — the Q6 PW residual is gone);
  guideline GLP/GSP recalc (attained-age delta, monthly-cent floor) + TAMRA
  7-pay recalc/period-restart wired into `_apply_policy_change`, with
  `metadata` injection of RERUN's values for mechanics-only validation. Engine
  fixes: leap-day ExactDays interest (Feb 29 never credits), cov-1 COI rate
  ROUND(.,5), per-coverage EPU ROUND(.,2), stale rates.coi alias after re-band,
  ending DB recomputed from EOM AV less debt (WB), TAMRA inforce fields loaded
  from LH_TAMRA_7_PY_PER/_YR. See QUESTION_LOG §E for the remaining gaps
  (own guideline-calc calibration, TEFRA/TAMRA-binding scenario, B→A).
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
- **2026-06-07** — Added §1.6: completed the Illustration 7702 guideline pipeline
  (GSP-floored force-out, premium capping with TEFRA/TAMRA toggles, in-engine GP
  exception premium, gain→preferred new-loan split) from the RERUN CalcEngine
  formulas. Pure logic unit-tested headless (32 green); live-rate penny
  validation, year-1-7 TAMRA, the PolView force-out ripple, and the UI toggle
  checkboxes are deferred here. Same branch `fix/dataforge-review`.
- **2026-06-07** — Added §1.7: GLP/GSP routines — commutation/PV method +
  Fackler reserves (`commutation.py`, headless-tested, 21 green) and an iterative
  account-value endowment-search method (`guideline_calc.py`, reuses CalcEngine
  via new `bonus_override`/`rates_override`). Iterative method needs live
  guaranteed-COI rates; commutation method needs a real mortality table to
  penny-validate against admin. Same branch `fix/dataforge-review`.
- **2026-06-07** — Added §0 (START HERE): minipc handoff on branch
  `minipc-handoff-2026-06-07`. DataForge engine aggregation (#9), pre-flight
  validation + Snapshot preview (#4), preview-window FramelessWindow chrome (#3),
  the friendly-field dictionary (#6, `core/field_dictionary.py`), the standards
  consolidation into `Agent.md` (+ deleted `docs/CLAUDE.md`, root `CLAUDE.md`
  pointer), and a `query_object` copy-timestamp fix — all headless-tested. Made
  the full pytest suite runnable (root `conftest.py` excludes standalone scripts
  + conditional `win32com` skip). Remaining intuitive-tooling items (#1 canvas
  unify, #5/#7/#8/#10 UI, #11 vocab) are UI-heavy → laptop. Also checkpointed the
  prior in-flight Illustration 7702/GLP work (§1.6–1.7) onto this branch.
