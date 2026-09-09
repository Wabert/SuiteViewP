"""Read-only live check of COLA coverage details and illustration surrender columns."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QDialog

from suiteview.core.policy_service import get_policy_info
from suiteview.illustration.core.calc_engine import IllustrationEngine
from suiteview.illustration.core.illustration_policy_service import build_illustration_data
from suiteview.illustration.models.case_store import decode_policy_snapshot, encode_policy_snapshot
from suiteview.illustration.models.plancode_config import load_plancode
from suiteview.illustration.ui.policy_tab import IllustrationPolicyTab
from suiteview.illustration.ui.values_tab import IllustrationValuesTab


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--company", required=True)
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--expected-coverages", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("This verification requires live data, not local fixtures.")
    app = QApplication.instance() or QApplication([])
    pi = get_policy_info(args.policy, args.region, args.company)
    policy = build_illustration_data(args.policy, args.region, args.company)
    assert len(policy.segments) == args.expected_coverages
    assert not pi.table_error("TH_COV_PHA")
    snapshot = decode_policy_snapshot(encode_policy_snapshot(policy))
    assert snapshot == policy
    config = load_plancode(policy.plancode)
    states = IllustrationEngine().project(policy, months=1, stop_on_lapse=False)

    policy_tab = IllustrationPolicyTab()
    coverage_rows = []
    for index, segment in enumerate(policy.segments, 1):
        coverage = next(c for c in pi.get_base_coverages() if c.cov_pha_nbr == segment.coverage_phase)
        indicator = dict(policy_tab._coverage_detail_rows(coverage))["Added by COLA:"]
        assert (indicator == "Yes") == segment.is_cola
        exempt = args.company == "26" and config.is_ffl and segment.is_cola
        if exempt:
            assert all(state.surrender_charges_by_coverage[f"cov{index}"] == 0 for state in states)
        coverage_rows.append({
            "phase": segment.coverage_phase, "cola": indicator, "exempt": exempt,
            "surrender_charge": states[0].surrender_charges_by_coverage[f"cov{index}"],
        })

    values_tab = IllustrationValuesTab()
    values_tab._render_projection(policy, states, months=1)
    grid = values_tab._tab_grids[values_tab.POLICY_VALUES_GROUP]
    frame = grid.model.get_display_data()
    expected = [f"SC Cov {i}" for i in range(1, args.expected_coverages + 1)]
    assert [name for name in frame.columns if name.startswith("SC Cov ")] == expected
    assert all(abs(sum(state.surrender_charges_by_coverage.values()) - state.surrender_charge) < 1e-8
               for state in states)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    values_tab.resize(1700, 650)
    values_tab.show()
    values_tab.content_stack.setCurrentWidget(grid)
    app.processEvents()
    grid.table_view.scrollTo(
        grid.table_view.model().index(0, list(frame.columns).index(expected[len(expected) // 2])),
        grid.table_view.ScrollHint.PositionAtCenter)
    app.processEvents()
    values_path = args.out_dir / "policy_values.png"
    assert values_tab.grab().save(str(values_path))

    cola_coverage = next(c for c in pi.get_base_coverages() if str(c.cola_indicator).strip() == "1")
    detail_path = args.out_dir / "cola_coverage_detail.png"

    def capture_detail():
        dialog = next(w for w in policy_tab.findChildren(QDialog) if w.isVisible())
        if not dialog.grab().save(str(detail_path)):
            raise RuntimeError(f"Could not save {detail_path}")
        dialog.accept()

    QTimer.singleShot(100, capture_detail)
    policy_tab._show_detail_dialog("coverage", cola_coverage)
    values_tab.close()
    print(json.dumps({
        "all_ok": True, "policy": args.policy, "company": policy.company_code,
        "plancode": policy.plancode, "is_ffl": config.is_ffl,
        "coverages": coverage_rows, "columns": expected,
        "screenshots": [str(values_path), str(detail_path)],
    }, indent=2))


if __name__ == "__main__":
    main()
