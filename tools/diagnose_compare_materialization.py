"""Diagnose the Compare-tab "two different cases, identical values" bug.

Reproduces exactly what ``IllustrationCompareTab._build_spec`` does for a saved
case — a throwaway ``IllustrationInputsTab``, ``load_data_from_policy`` +
``apply_case_inputs`` — but OFFLINE, using the policy snapshot embedded in each
case file as the policy (so no DB2 needed). Prints, per case, the applied
warnings and the exported future-inputs (scheduled/dated transactions and
policy-change events, esp. DB_OPTION), then reports whether the two cases'
exported input sets actually differ.

Usage:
    venv\\Scripts\\python.exe tools/diagnose_compare_materialization.py
    venv\\Scripts\\python.exe tools/diagnose_compare_materialization.py '{"cases": ["U0351626 Prem to Maturity - Opt A", "U0351626 Prem to Maturity - Opt B"]}'
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SUITEVIEW_LOCAL_DATA", "1")   # engine rates from local SQLite

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from suiteview.illustration.core.compare_runner import (  # noqa: E402
    ScenarioSpec, run_scenario,
)
from suiteview.illustration.core.scenario_builder import (  # noqa: E402
    build_illustration_scenario,
)
from suiteview.illustration.models import case_store  # noqa: E402


def _describe_input_set(input_set) -> dict:
    return {
        "scheduled": [
            (t.kind.name, t.policy_year, t.amount, t.mode)
            for t in input_set.scheduled_transactions
        ],
        "dated": [
            (t.kind.name, str(t.effective_date), t.amount, t.subtype)
            for t in input_set.dated_transactions
        ],
        "policy_changes": [
            (c.kind.name, str(c.effective_date), c.value)
            for c in input_set.policy_changes
        ],
    }


def _log(msg):
    print(msg, flush=True)


def _materialize(case):
    """Isolate the dbo/face apply->export leak at the DynamicInputsPanel level.

    The functional difference between the two cases lives entirely in
    ``inputs.dynamic`` (the dbo change row), which is applied via
    ``DynamicInputsPanel.apply_state`` and exported via ``collect_into`` — the
    same surface Run Values reads. Reproduce just that, offline, from the
    embedded snapshot."""
    from suiteview.illustration.models.input_set import IllustrationInputSet
    from suiteview.illustration.ui.inputs_dynamic import DynamicInputsPanel

    snapshot = case.policy_snapshot
    if snapshot is None:
        raise SystemExit(f"Case {case.name!r} has no policy_snapshot (v1).")

    _log("  constructing DynamicInputsPanel...")
    panel = DynamicInputsPanel()
    _log("  load_from_policy...")
    has_shadow = bool(getattr(snapshot, "has_shadow_account", False))
    panel.load_from_policy(snapshot, has_shadow=has_shadow, shadow_ceased=False)
    _log("  apply_state(dynamic)...")
    warnings = panel.apply_state(case.inputs.get("dynamic") or {})
    _log("  collect_into...")
    input_set = IllustrationInputSet()
    panel.collect_into(input_set)
    dbo_entries = [dict(e) for e in panel.dbo_section.entries()]
    scenario = build_illustration_scenario(snapshot, future_inputs=input_set)
    return {
        "warnings": warnings,
        "dbo_section_entries": dbo_entries,
        "future_inputs": _describe_input_set(input_set),
        "min_level": panel.min_level_request(),
        "db_option_base": getattr(scenario.projectable_policy, "db_option", None),
    }


def _full_spec_and_run(case) -> dict:
    """Faithful compare-tab reproduction: build a ScenarioSpec via the real
    IllustrationInputsTab, then run it through run_scenario (with the engine)."""
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    snapshot = case.policy_snapshot
    _log("  IllustrationInputsTab()...")
    tab = IllustrationInputsTab()
    try:
        has_shadow = bool(getattr(snapshot, "has_shadow_account", False))
        tab.load_data_from_policy(snapshot, has_shadow=has_shadow,
                                  shadow_ceased=False)
        tab.apply_case_inputs(case.inputs)
        scenario = build_illustration_scenario(
            snapshot,
            inforce_overrides=tab.export_inforce_overrides(),
            future_inputs=tab.export_input_set())
        spec = ScenarioSpec(
            label=case.name,
            scenario=scenario,
            months=tab.projection_months(scenario.projectable_policy),
            options=tab.export_options(),
            stop_on_lapse=tab.stop_on_lapse_enabled(),
            lumpsum_to_next=tab.lumpsum_to_next_enabled(),
            max_level=tab.max_level_request(),
            min_level=tab.min_level_request(),
            shadow_level=tab.shadow_level_request(),
            payoff_requests=tab.loan_payoff_requests(),
        )
    finally:
        tab.deleteLater()

    _log("  run_scenario()...")
    outcome = run_scenario(spec)
    final = outcome.results[-1]
    return {
        "solved": {k: (round(v, 2) if isinstance(v, (int, float)) else v)
                   for k, v in outcome.solved.items()},
        "final_year": final.policy_year,
        "final_av": round(final.av_end_of_month, 2),
        "final_sv": round(final.ending_sv, 2),
        "final_db": round(final.ending_db or final.gross_db, 2),
        "policy_changes": [
            (c.kind.name, str(c.effective_date), c.value)
            for c in spec.scenario.future_inputs.policy_changes],
    }


def _spec_via_tab(case, shared_policy_data):
    """Mirror compare_tab._build_spec + _spec_from_tab EXACTLY: a fresh tab, but
    the scenario built from the SHARED policy_data object (as _on_run does)."""
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    tab = IllustrationInputsTab()
    try:
        tab.load_data_from_policy(shared_policy_data)
        tab.apply_case_inputs(case.inputs)
        scenario = build_illustration_scenario(
            shared_policy_data,
            inforce_overrides=tab.export_inforce_overrides(),
            future_inputs=tab.export_input_set())
        return ScenarioSpec(
            label=case.name, scenario=scenario,
            months=tab.projection_months(scenario.projectable_policy),
            options=tab.export_options(),
            stop_on_lapse=tab.stop_on_lapse_enabled(),
            lumpsum_to_next=tab.lumpsum_to_next_enabled(),
            max_level=tab.max_level_request(),
            min_level=tab.min_level_request(),
            shadow_level=tab.shadow_level_request(),
            payoff_requests=tab.loan_payoff_requests())
    finally:
        tab.deleteLater()


def _reproduce_on_run(names):
    """Full _on_run reproduction: ONE shared policy_data object for both sides,
    both specs built (sequentially, fresh tabs), then run_comparison-style."""
    from suiteview.illustration.core.compare_runner import run_comparison

    case_a = case_store.load_case(names[0])
    case_b = case_store.load_case(names[1])
    # The app shares ONE build_illustration_data result across both sides.
    shared = case_a.policy_snapshot          # identical to case_b's; stand-in
    _log("build spec A (shared policy_data)...")
    spec_a = _spec_via_tab(case_a, shared)
    _log("build spec B (shared policy_data)...")
    spec_b = _spec_via_tab(case_b, shared)
    _log("run_comparison...")
    result = run_comparison([spec_a, spec_b])
    out_a, out_b = result.outcomes
    fa = out_a.results[-1]
    fb = out_b.results[-1]
    print("===== _on_run REPRODUCTION (shared policy_data) =====")
    print(f"  A solved={out_a.solved} final DB={round(fa.ending_db or fa.gross_db, 2)}")
    print(f"  B solved={out_b.solved} final DB={round(fb.ending_db or fb.gross_db, 2)}")
    da = round(fa.ending_db or fa.gross_db, 2)
    db = round(fb.ending_db or fb.gross_db, 2)
    print(f"  IDENTICAL: {da == db}")
    print()


def _reproduce_live(names):
    """The TRUE _on_run path: tab loaded from LIVE PolicyInformation, scenario
    from LIVE build_illustration_data — NOT the frozen snapshot. This is what
    the user actually ran."""
    from suiteview.core.policy_service import get_policy_info
    from suiteview.illustration.core.illustration_policy_service import (
        build_illustration_data,
    )
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    case_a = case_store.load_case(names[0])
    case_b = case_store.load_case(names[1])
    pn = case_a.policy_number
    region = case_a.region or "CKPR"
    company = case_a.company_code or "01"
    _log(f"build_illustration_data({pn}) [LIVE/local]...")
    policy_data = build_illustration_data(pn, region=region, company_code=company)
    live_policy = get_policy_info(pn, region, company)

    def run_case(case):
        tab = IllustrationInputsTab()
        try:
            tab.load_data_from_policy(live_policy)      # LIVE, as the app does
            tab.apply_case_inputs(case.inputs)
            scenario = build_illustration_scenario(
                policy_data,                            # LIVE, as the app does
                inforce_overrides=tab.export_inforce_overrides(),
                future_inputs=tab.export_input_set())
            spec = ScenarioSpec(
                label=case.name, scenario=scenario,
                months=tab.projection_months(scenario.projectable_policy),
                options=tab.export_options(),
                stop_on_lapse=tab.stop_on_lapse_enabled(),
                lumpsum_to_next=tab.lumpsum_to_next_enabled(),
                max_level=tab.max_level_request(),
                min_level=tab.min_level_request(),
                shadow_level=tab.shadow_level_request(),
                payoff_requests=tab.loan_payoff_requests())
            changes = [(c.kind.name, str(c.effective_date), c.value)
                       for c in scenario.future_inputs.policy_changes]
        finally:
            tab.deleteLater()
        outcome = run_scenario(spec)
        f = outcome.results[-1]
        return outcome.solved, round(f.ending_db or f.gross_db, 2), changes

    sa, dba, ca = run_case(case_a)
    sb, dbb, cb = run_case(case_b)
    print("===== TRUE LIVE _on_run REPRODUCTION =====")
    print(f"  A solved={sa} final DB={dba} changes={ca}")
    print(f"  B solved={sb} final DB={dbb} changes={cb}")
    print(f"  IDENTICAL: {dba == dbb}")
    print()


def _reproduce_real_build_spec(names):
    """Call the ACTUAL IllustrationCompareTab._build_spec for both sides with a
    mock window, exactly as _on_run does, and compare the two specs."""
    from types import SimpleNamespace

    from suiteview.core.policy_service import get_policy_info
    from suiteview.illustration.core.illustration_policy_service import (
        build_illustration_data,
    )
    from suiteview.illustration.ui.compare_tab import IllustrationCompareTab
    from suiteview.illustration.ui.inputs_tab import IllustrationInputsTab

    case_a = case_store.load_case(names[0])
    case_b = case_store.load_case(names[1])
    pn = case_a.policy_number
    region = case_a.region or "CKPR"
    company = case_a.company_code or "01"
    policy_data = build_illustration_data(pn, region=region, company_code=company)
    live_policy = get_policy_info(pn, region, company)

    live_inputs_tab = IllustrationInputsTab()
    live_inputs_tab.load_data_from_policy(live_policy)
    window = SimpleNamespace(
        _current_key=(pn, region, company),
        _policy=live_policy,
        _illustration_data=policy_data,
        inputs_tab=live_inputs_tab,
    )
    compare = IllustrationCompareTab(window=window)

    key = (pn, region, company)
    spec_a = compare._build_spec(case_a, key, side="A")
    spec_b = compare._build_spec(case_b, key, side="B")
    fa = _describe_input_set(spec_a.scenario.future_inputs)
    fb = _describe_input_set(spec_b.scenario.future_inputs)
    print("===== REAL _build_spec, window._policy = LIVE =====")
    print(f"  A future_inputs.policy_changes = {fa['policy_changes']}")
    print(f"  B future_inputs.policy_changes = {fb['policy_changes']}")
    print(f"  future_inputs IDENTICAL: {fa == fb}")
    print()

    # Snapshot mode / live-load failure: window._policy is None, so the
    # throwaway tab's context is degraded and change-row effective dates cannot
    # resolve -> the DBO change silently drops and both sides collapse.
    window2 = SimpleNamespace(
        _current_key=(pn, region, company), _policy=None,
        _illustration_data=policy_data, inputs_tab=live_inputs_tab)
    compare2 = IllustrationCompareTab(window=window2)
    try:
        sa2 = compare2._build_spec(case_a, key, side="A")
        sb2 = compare2._build_spec(case_b, key, side="B")
        fa2 = _describe_input_set(sa2.scenario.future_inputs)
        fb2 = _describe_input_set(sb2.scenario.future_inputs)
        print("===== REAL _build_spec, window._policy = None (snapshot mode) =====")
        print(f"  A future_inputs.policy_changes = {fa2['policy_changes']}")
        print(f"  B future_inputs.policy_changes = {fb2['policy_changes']}")
        print(f"  future_inputs IDENTICAL: {fa2 == fb2}")
        oa2, ob2 = run_scenario(sa2), run_scenario(sb2)
        fda = round(oa2.results[-1].ending_db or oa2.results[-1].gross_db, 2)
        fdb = round(ob2.results[-1].ending_db or ob2.results[-1].gross_db, 2)
        print(f"  full run final DB: A={fda}  B={fdb}  IDENTICAL={fda == fdb}")
    except Exception as exc:
        import traceback
        print(f"  window._policy=None RAISED: {exc}")
        traceback.print_exc()
    print()


def main() -> None:
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    names = cmd.get("cases") or [
        "U0351626 Prem to Maturity - Opt A",
        "U0351626 Prem to Maturity - Opt B",
    ]
    app = QApplication.instance() or QApplication(sys.argv)  # keep ref alive
    _ = app

    if len(names) == 2:
        try:
            _reproduce_real_build_spec(names)
        except Exception as exc:
            import traceback
            _log(f"[real _build_spec reproduction failed: {exc}]")
            traceback.print_exc()
        return

    summaries = {}
    runs = {}
    for name in names:
        _log(f"loading case {name!r}...")
        case = case_store.load_case(name)
        summary = _materialize(case)
        summaries[name] = summary
        print(f"===== {name} (panel export) =====")
        print(json.dumps(summary, indent=2, default=str))
        _log(f"full run for {name!r}...")
        runs[name] = _full_spec_and_run(case)
        print(f"===== {name} (full run_scenario) =====")
        print(json.dumps(runs[name], indent=2, default=str))
        print()

    if len(summaries) == 2:
        (na, sa), (nb, sb) = summaries.items()
        same_inputs = sa["future_inputs"] == sb["future_inputs"]
        ra, rb = runs[na], runs[nb]
        same_run = (ra["final_av"], ra["final_sv"], ra["final_db"]) == (
            rb["final_av"], rb["final_sv"], rb["final_db"])
        print("===== VERDICT =====")
        print(f"future_inputs identical: {same_inputs}")
        print(f"full run final AV/SV/DB identical: {same_run}")
        print(f"  A final AV/SV/DB = {ra['final_av']}/{ra['final_sv']}/{ra['final_db']}")
        print(f"  B final AV/SV/DB = {rb['final_av']}/{rb['final_sv']}/{rb['final_db']}")


if __name__ == "__main__":
    main()
