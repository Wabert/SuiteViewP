"""Read-only U0416030 screenshot setup and prior-table-drop isolation check."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--case", required=True)
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_hash = hashlib.sha256(args.bundle.read_bytes()).hexdigest()
    report = {"checks": {}}
    checks = report["checks"]
    with TemporaryDirectory(prefix="suiteview-rating-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        os.environ.setdefault("QT_QPA_PLATFORM", "windows" if args.screenshot else "offscreen")
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from suiteview.core.rates import owned_rate_connections
        from suiteview.illustration.core.compare_runner import run_scenario
        from suiteview.illustration.core.rate_loader import load_rates
        from suiteview.illustration.models.imported_case_store import load_imported_case
        from suiteview.illustration.models.input_set import PolicyChangeKind
        from suiteview.illustration.models.plancode_config import load_plancode
        from suiteview.illustration.ui.main_window import IllustrationWindow
        from suiteview.illustration.ui.saved_case_scenario import materialize_saved_case

        app = QApplication.instance() or QApplication([])
        source = load_imported_case(args.bundle, args.case)
        case = deepcopy(source)
        policy = case.policy_snapshot
        assert policy is not None and policy.policy_number == "U0416030"
        assert policy.base_segment.table_rating == 2 and policy.base_segment.flat_extra == 0
        dynamic = case.inputs["dynamic"]
        dynamic.update(illustrated_rate="3.000", lumpsum="", forecast_loan="",
                       forecast_withdrawal="", apply_prem_to_loan=False, tamra=True)
        sections = dynamic["sections"]
        sections["premiums"] = [
            {"type": "Billable Prem", "year": "25", "amount": "80.82", "mode": "M", "for_years": "37"},
        ]
        for name in ("loans", "withdrawals", "repayments", "dbo", "rateclass", "table"):
            sections[name] = []
        sections["face"] = [{"type": "Input", "year": "29", "amount": "95000"}]
        with owned_rate_connections():
            spec = materialize_saved_case(case, strict=True)
            checks["no_table_change_in_clean_inputs"] = all(
                change.kind != PolicyChangeKind.SUBSTANDARD
                for change in spec.scenario.future_inputs.policy_changes)
            clean = run_scenario(spec)
            assert clean.ok, clean.error
            dropped = deepcopy(case)
            dropped.inputs["dynamic"]["sections"]["table"] = [
                {"type": "Input", "year": "29", "value": "0"},
            ]
            drop_trial = run_scenario(materialize_saved_case(dropped, strict=True))
            assert drop_trial.ok, drop_trial.error
            rerun = run_scenario(materialize_saved_case(case, strict=True))
            assert rerun.ok, rerun.error
            checks["clean_run_unchanged_after_drop_trial"] = clean.results == rerun.results
            recalc = next(s.guideline_recalc for s in clean.results if s.guideline_recalc)
            pv = recalc["monthly_pv_recalc"]["before"]["glp"]
            config = load_plancode(policy.plancode)
            rates = load_rates(policy, config, coi_scale=0)
            schedule = rates.segment_coi[policy.base_segment.coverage_phase]
            drop_recalc = next(s.guideline_recalc for s in drop_trial.results if s.guideline_recalc)
            drop_row = drop_recalc["monthly_pv_recalc"]["after"]["glp"]["glp_rows"][0]
            drop_raw = float(schedule[drop_row["Age"] - policy.issue_age + 1]) / 1000
            checks["explicit_drop_still_removes_rating"] = (
                drop_row["q'x"] == round(drop_raw / (1 + drop_raw), 8))
            checked = []
            for row in pv["glp_rows"]:
                if row.get("_endowment"):
                    continue
                age = row["Age"]
                policy_year = age - policy.issue_age + 1
                raw = schedule[min(policy_year, len(schedule) - 1)]
                assert raw is not None
                adjusted = min(float(raw) * (1 + config.table_rating_factor * 2), 83.333) / 1000
                expected = round(adjusted / (1 + adjusted), 8)
                checked.append(row["q'x"] == expected)
            checks["every_glp_before_month_retains_table_two"] = all(checked)
            report.update(
                table_rating=policy.base_segment.table_rating,
                table_cease_date=policy.base_segment.table_cease_date,
                recalc_date=recalc["change_date"], glp_before=pv["glp_rollup"]["premium"],
                sample_rows=[row for row in pv["glp_rows"] if row["Policy Month"] in (61, 73)],
            )
            if args.screenshot:
                messages = []

                def message(_parent, title, text, *unused):
                    messages.append(f"{title}: {text}")
                    return QMessageBox.StandardButton.Ok

                window = IllustrationWindow()
                try:
                    with (patch.object(QMessageBox, "information", message),
                          patch.object(QMessageBox, "warning", message),
                          patch.object(QMessageBox, "critical", message)):
                        window._load_case_snapshot(case)
                        window._on_run_values()
                    assert window.values_tab._current_view is not None, messages
                    checks["native_matches_clean_run"] = window.values_tab._current_view[1] == clean.results
                    checks["no_native_errors"] = not messages
                    view = window.values_tab.recalc_view
                    window.values_tab.content_stack.setCurrentWidget(view)
                    view.show_date(0)
                    detail = view.detail_views[0]
                    glp_view = detail.pv_views[("glp", "before")]
                    detail.tabs.setCurrentWidget(glp_view)
                    window.show()
                    app.processEvents()
                    glp_view.grid.table_view.scrollTo(glp_view.grid.table_view.model().index(72, 0))
                    app.processEvents()
                    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    assert window.grab().save(str(args.screenshot))
                finally:
                    window.close()
                    window.deleteLater()
                    app.processEvents()
        checks["snapshot_unchanged"] = policy == source.policy_snapshot
    checks["saved_file_unchanged"] = hashlib.sha256(args.bundle.read_bytes()).hexdigest() == source_hash
    report["all_ok"] = all(checks.values())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
