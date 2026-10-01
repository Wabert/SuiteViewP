"""Summarize RERUN baseline JSON results for triage.

Usage:
``venv\\Scripts\\python.exe tools\\rerun\\baseline_summarize_results.py
--comparison <comparison_summary.json> --output <summary.json>``

The summary extracts month-0 variances, rollback basis counts, premium
reconciliation, material COI diagnostics and feature/full-replay coverage.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.rerun.baseline_common import json_dump, json_load  # noqa: E402


FEATURES = ("riders", "benefits", "substandard", "db-option-b", "db-option-other", "loan", "shadow", "multi-segment")


def summarize(comparison_path: Path) -> dict:
    comparison = json_load(comparison_path)
    results = comparison["results"]
    basis_counts = Counter(row.get("rollback_basis", "not run") for row in results)
    status_counts = Counter(row.get("status", "") for row in results)
    month0_nonzero = []
    coi = []
    premium_mismatches = []
    feature_full = Counter()
    feature_all = Counter()
    no_replay_by_plan = defaultdict(int)
    replay_by_plan = defaultdict(int)
    for row in results:
        for feature in row.get("feature_tags", []):
            if feature in FEATURES:
                feature_all[feature] += 1
                if row.get("status") == "compared":
                    feature_full[feature] += 1
        if row.get("status") == "compared":
            replay_by_plan[row.get("requested_plancode", "")] += 1
        else:
            no_replay_by_plan[row.get("requested_plancode", "")] += 1
        month0 = row.get("month0") or {}
        variance = month0.get("variance")
        if variance is not None and abs(float(variance)) > 0.01:
            month0_nonzero.append({
                "key": row.get("key"),
                "plancode": row.get("plancode"),
                "variance": variance,
                "system_md": month0.get("system_md"),
                "calculated_md": month0.get("calculated_md"),
                "system_coi": month0.get("system_coi"),
                "calculated_coi": month0.get("calculated_coi"),
                "system_other": month0.get("system_other"),
                "calculated_other": month0.get("calculated_other"),
            })
        recon = row.get("premium_reconciliation") or {}
        mismatch = recon.get("replay_vs_paid_delta")
        if mismatch is not None and abs(float(mismatch)) > 1.0:
            premium_mismatches.append({
                "key": row.get("key"),
                "plancode": row.get("plancode"),
                "replay_vs_paid_delta": mismatch,
                "codes": sorted((recon.get("code_summary") or {}).keys()),
            })
        for detail in row.get("coi_details", []):
            coi.append({
                "key": row.get("key"),
                "plancode": row.get("plancode"),
                "date": detail.get("date"),
                "coi_diff": detail.get("coi_diff"),
                "cyberlife_coi": detail.get("cyberlife_coi"),
                "rerun_coi": detail.get("rerun_coi"),
                "total_nar": detail.get("total_nar"),
                "implied_rate": detail.get("implied_aggregate_rate_per_1000"),
                "rerun_rate": detail.get("rerun_aggregate_rate_per_1000"),
                "rates_by_coverage": detail.get("rerun_rates_by_coverage"),
                "charges_by_coverage": detail.get("rerun_charges_by_coverage"),
                "coverage_basis": detail.get("coverage_basis"),
            })
    worst_coi = sorted(coi, key=lambda item: abs(float(item.get("coi_diff") or 0.0)), reverse=True)
    return {
        "comparison": str(comparison_path),
        "policy_count": len(results),
        "status_counts": dict(status_counts),
        "rollback_basis_counts": dict(basis_counts),
        "month0_nonzero_count": len(month0_nonzero),
        "month0_nonzero": month0_nonzero[:100],
        "premium_mismatch_count": len(premium_mismatches),
        "premium_mismatches": premium_mismatches[:100],
        "worst_coi": worst_coi[:100],
        "feature_all": dict(feature_all),
        "feature_full_replay": dict(feature_full),
        "replay_by_plancode": dict(sorted(replay_by_plan.items())),
        "not_replayed_by_plancode": dict(sorted(no_replay_by_plan.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    summary = summarize(Path(args.comparison))
    json_dump(Path(args.output), summary)
    print(json.dumps({
        "output": args.output,
        "policy_count": summary["policy_count"],
        "status_counts": summary["status_counts"],
        "month0_nonzero_count": summary["month0_nonzero_count"],
        "premium_mismatch_count": summary["premium_mismatch_count"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

