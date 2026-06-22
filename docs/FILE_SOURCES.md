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
- **Phase 2c — Visual builder over a File Source (remaining):** let the Visual
  Query designer target a File Source (members as the Tables list, schema as the
  field list, compile via the `DUCKDB` dialect, Run → `file_query_runner`). More
  invasive — touches the Tables dialog (ODBC introspection) and
  `DynamicQuery._on_run_audit`.
- **Phase 3 — Browser/organizer + migration (app):** the "File Sources" group
  lists FileDataSources (not per-file query objects); the source-tree shows each
  source and its members. Migrate existing `adhoc_source` QueryObjects →
  FileDataSource (+ a default query), then delete the old `adhoc_source` kind
  cleanly (dev-only, no shims).

## 5. Constraints
- DuckDB + flat-file logic is fully testable on the minipc; interactive UI
  verification (builder integration, the editor, the browser) is deferred to the
  app on the work laptop (`WORK_LAPTOP_SPEC.md` §3c).

## Changelog
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
