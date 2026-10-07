# Run Values flow

The Illustration window is the Qt boundary.  Widgets read and render drafts;
`suiteview.illustration.core.run_service` owns the deterministic run pipeline.

1. **Click** — `IllustrationWindow._on_run_values` checks for unapplied record
   edits, reads a plain `InputDraft`, builds a frozen `RunRequest`, disables the
   button and shows progress.
2. **Draft** — `IllustrationInputsTab.read_draft()` captures JSON-safe case
   input state plus compiled `IllustrationInputSet`, `IllustrationOptions`,
   inforce/issue/rollback basis overrides and solve requests.  `render_draft()`
   restores a draft into a fresh widget when policy sessions are revisited.
3. **Scenario** — `execute_run()` loads or copies the `PolicyBasis`, then
   `build_run_scenario()` applies inforce overrides, issue-mode assumptions and
   rollback assumptions through `scenario_builder`.  Rollback and from-issue
   scenarios retain dated transaction receipt dates so the engine can credit
   receipt-to-monthliversary interest; ordinary inforce forecasts still treat
   scheduled/modal cash flows as monthliversary transactions.
4. **Solves** — `resolve_solved_inputs()` preserves the UI's solve order:
   ABR Quote short-circuits; then lumpsum-to-next-premium, max level, minimum
   level to maturity, shadow maturity, target premium, duration and loan payoff.
   Each solve layers its result into a new input set and returns solved values
   for the widget to display.
5. **Engine** — `run_current_projection()` calls the public
   `suiteview.illustration.api.project_policy` façade.  The service does not
   rewire lower-level engine/rate loaders.
6. **Guaranteed** — `run_guaranteed_projection_safe()` replays locked current
   cash flows under guaranteed assumptions.  Failure is non-fatal for the run
   and is returned as a banner/status message, but it makes the formal
   illustration unprintable: `build_report_result()` records the error on the
   report (`IllustrationReport.guaranteed_error`) and the Report tab disables
   Print to PDF (`report_tab.print_blocked_reason`; `write_pdf` raises
   `ReportNotPrintableError`), because the guaranteed columns would print blank.
7. **Report** — `build_report_result()` calls the report builder with a pinned
   run date from the request and a `ReportRunContext`: the app build label
   (`suiteview.core.build_info.app_build_label()`, version plus git commit),
   the run timestamp (`RunControls.run_timestamp`, else the build moment), the
   user's selected options and stop-on-lapse control.  These identify the run
   in the support export only; the customer report carries no build/run footer
   on any page, so pages use the full `REPORT_PAGE_MAX_LINES`.  For in-force
   runs the cover also states, as of the valuation date (`POLICY STATUS`
   block): values older than `STALE_VALUATION_DAYS` (45) before the run date,
   a suspended policy (`IllustrationPolicyData.suspense_code == "2"`, from
   `LH_BAS_POL.SUS_CD`), an already-MEC policy (which is then never reported
   as *becoming* a MEC), and the shadow-account no-lapse guarantee status
   (`shadow_status_lines`, incl. nullified by debt on `ShadowLoanImpact:
   Nullify` plans).  Loan charge/credit rates print with the loan balance.
   User options that differ from the defaults are collected as
   `IllustrationReport.settings_lines` (`non_default_settings_lines`) for the
   support export; the customer cover does not print them.  Report
   specs/page specs are interpreters around the existing text builders.

**Export Case for Support** (☰ menu, `ui/support_export_controls.py` →
`core/support_export.py`) writes two files to a chosen folder (Documents by
default): `SUPPORT - <policy> - <plancode> - <yyyy-mm-dd hh-mm>.cases.json`, a
standard case bundle of the current inputs plus frozen policy data, and the
same stem `.support.json` with the app version/build, the last run's time,
messages, guaranteed failure, printed status/settings lines, load-time
warnings, the illustrated rate and a SHA-256 of the plancode configuration
(UL_Rates tables are read live and are not fingerprinted).
8. **Render** — the window applies solved inputs, renders Values, Guaranteed
   Values and Report/ABR pages, then re-enables the button.  Dialogs, cursors,
   tab selection and status-bar text stay in the UI layer.

Per-policy session state is `IllustrationSessionState`: plain `InputDraft`,
policy basis snapshot, values/report render snapshots, last scenario and status.
It deliberately does not store live input widgets.
