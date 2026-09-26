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
   rollback assumptions through `scenario_builder`.
4. **Solves** — `resolve_solved_inputs()` preserves the UI's solve order:
   ABR Quote short-circuits; then lumpsum-to-next-premium, max level, minimum
   level to maturity, shadow maturity, target premium, duration and loan payoff.
   Each solve layers its result into a new input set and returns solved values
   for the widget to display.
5. **Engine** — `run_current_projection()` calls the public
   `suiteview.illustration.api.project_policy` façade.  The service does not
   rewire lower-level engine/rate loaders.
6. **Guaranteed** — `run_guaranteed_projection_safe()` replays locked current
   cash flows under guaranteed assumptions.  Failure is non-fatal and is
   returned as a banner/status message.
7. **Report** — `build_report_result()` calls the report builder with a pinned
   run date from the request.  Report specs/page specs are interpreters around
   the existing byte-identical text builders.
8. **Render** — the window applies solved inputs, renders Values, Guaranteed
   Values and Report/ABR pages, then re-enables the button.  Dialogs, cursors,
   tab selection and status-bar text stay in the UI layer.

Per-policy session state is `IllustrationSessionState`: plain `InputDraft`,
policy basis snapshot, values/report render snapshots, last scenario and status.
It deliberately does not store live input widgets.
