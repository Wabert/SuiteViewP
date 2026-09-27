"""Read-only verification of the live policy's Single/Joint display."""

import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="000321709")
    parser.add_argument("--company", default="26")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--expect", choices=("Single", "Joint First to Die", "Joint Second to Die"))
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live verification must not use local policy data")

    with TemporaryDirectory(prefix="suiteview-joint-insured-") as profile:
        os.environ["SUITEVIEW_PROFILE_DIR"] = profile
        from PyQt6.QtWidgets import QApplication
        from suiteview.polview.services.policy_prefetch import PolicyLoadSession
        from suiteview.polview.ui.tabs.coverages_tab import CoveragesTab

        app = QApplication.instance() or QApplication([])
        session = PolicyLoadSession(args.policy, args.region, args.company)
        try:
            prepared = session.load_initial()
        finally:
            session.close()
        if not prepared.available:
            raise RuntimeError(f"Policy {args.policy} / {args.company} was not found")
        policy = prepared.policy
        tab = CoveragesTab()
        with policy.cached_reads_only():
            tab.load_data_from_policy(policy)
        report = {
            "policy": policy.policy_number,
            "company": policy.company_code,
            "source": "LH_COV_PHA.NBR_OF_LIVES_CD (phase 1), FCVLIVES-LIVES",
            "number_of_lives_code": policy.coverages.number_of_lives_code,
            "is_joint_insured": policy.coverages.is_joint_insured,
            "display": tab.joint_label.text(),
        }
        tab.resize(1160, 620)
        tab.show()
        app.processEvents()
        label = tab.joint_label
        report["label_fits"] = (
            label.fontMetrics().horizontalAdvance(label.text()) <= label.contentsRect().width()
        )
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not tab.grab().save(str(args.screenshot)):
                raise RuntimeError("Failed to save native screenshot")
        tab.close()
        print(json.dumps(report, indent=2, default=str))
        if not report["label_fits"]:
            raise AssertionError("Single/Joint label is clipped")
        if args.expect and report["display"] != args.expect:
            raise AssertionError(f"Expected {args.expect}, got {report['display']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
