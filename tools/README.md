# tools/ — auditable helper scripts

All AI-assisted execution goes through small, single-purpose scripts in this
directory (no inline `python -c`). Scripts take CLI args (prefer a single JSON
argument) and write JSON to stdout.

## Organization — one folder per pipeline

| Folder | Scope |
|---|---|
| `office/` | Generic workbook/CSV/doc/PDF utilities (`dump_xlsx_*`, `compare_workbook_*`, `read_xls`, `extract_docx`, `render_pdf_page`, …) — **check here before writing a new file utility** |
| `localdev/` | Local SQLite dev-data pipeline (`create_local_dev_data`, `export_local_*`, `check_local_*`, `query_local_sqlite`, …) — see `docs/LOCAL_DEV_DATA.md` |
| `rerun/` | RERUN workbook COM bridge + engine comparison (`rerun_com`, `compare_rerun_vs_app`, `compare_case`, saved-case dumps, `build_test_matrix`) — workbooks live in the work-laptop archive; ISWL live checks (`verify_iswl_rollforward`, `run_iswl_illustration`, `build_iswl_plancode_rows`, `find_iswl_policies`, `sample_iswl_receipts`, `probe_iswl_history`); par whole life (`verify_parwl_inforce`, `run_parwl_illustration`, `find_parwl_policies`, `build_cyberlife_mortality`); indeterminate premium term (`verify_term_inforce`, `run_term_illustration`, `find_term_policies`) |
| `engine/` | Illustration engine verification harnesses (`check_guideline_*`, `check_target_premium`, ratchet/benefit checks, `drive_illustration_app`) |
| `glp/` | The GLP forecast batch pipeline (policy list → fetch AV/debt → append columns → batch run → report) |
| `rates/` | UL_Rates / SV_INDEX / rate-workup tooling (`query_ul_rates`, `run_rate_workup`, `create_sv_index_*`, `verify_sv_index_*`, mortality loader) |
| `policyrecord/` | CyberDoc / policy-record segment screens (`build_seg*`, `probe_segment*`, `gen_seg02_fields`, `build_cyberdoc_index`) |
| `audit/` | Audit / File Sources / source-dashboard UI harnesses and data migrations |
| `app/` | App-level dev UX (`take_screenshot`, `sandbox_suiteview`, `check_imports`, `generate_testing_plan`, `create_taskbar_shortcut`; live window checks `verify_rerun_joint_window`, `verify_rerun_parwl_window`, `verify_rerun_term_window`) |

Intra-folder imports (e.g. `compare_case` ← `calc_compare_map`,
`rerun_*` ← `rerun_com`) rely on scripts living in the **same** folder — keep
pipeline families together when adding or moving scripts.

**Two invariants every script in a bucket folder must obey:**

1. Invoke from the repo root: `venv\Scripts\python.exe tools/<folder>/<name>.py`
   (some scripts also assume `cwd` = repo root for relative data paths).
2. The repo root from inside a bucket is **two levels up**:
   `ROOT = Path(__file__).resolve().parents[2]` (or a triple
   `os.path.dirname`). A `parents[1]` here points at `tools/` and silently
   breaks `import suiteview` — this exact bug bit all 9 folders once.

## Rules

1. **Reuse.** Before writing a new script, grep the relevant folder — the
   generic utilities in `office/` cover most workbook/CSV inspection needs.
2. **Single purpose, auditable.** Small scripts; input via CLI args (JSON
   preferred); output JSON to stdout.
3. **No inline execution.** Never `python -c` — create/extend a script here.
4. **Retirement policy.** One-shot diagnostics (a single policy, a single bug,
   a shipped UI change) are **deleted when the investigation closes** — git
   history is the archive. Durable pipeline stages stay.
5. **Naming.** `check_`/`verify_`/`validate_` = assert correctness;
   `dump_`/`inspect_`/`list_` = read and print; `probe_` = live-source schema
   discovery; `build_`/`create_`/`make_` = produce an artifact; `run_` = batch
   driver; `show_`/`preview_`/`screenshot_` = UI harness.
