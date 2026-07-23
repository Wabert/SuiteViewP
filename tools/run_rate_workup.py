"""Run a Rate Workup headlessly from a JSON spec (verification harness).

Usage:
    venv\\Scripts\\python.exe tools/run_rate_workup.py '<json>'
    venv\\Scripts\\python.exe tools/run_rate_workup.py @path/to/spec.json

JSON keys mirror WorkupSpec: plancode, output_dir, fmt, maturity_age,
iaf_path, mpf_path, scr_path, epu_path, base_index, scr_plan, epu_plan,
epu_freq, epu_rule, benefits: [{code, renewable, cease_age, mpf_code}] —
cease_age is required for non-renewing benefits; mpf_code links a benefit's
charges to an MPF premium code ('' or omitted = IAF charges).

Prints the WorkupResult as JSON to stdout.
"""

import json
import sys

sys.path.insert(0, ".")

from suiteview.ratemanager.workup import (  # noqa: E402
    BenefitSelection, WorkupSpec, analyze, build,
)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: run_rate_workup.py '<json>'"}))
        return 1
    arg = sys.argv[1]
    if arg.startswith("@"):
        with open(arg[1:], "r", encoding="utf-8") as f:
            cfg = json.load(f)
    else:
        cfg = json.loads(arg)

    benefits = [BenefitSelection(**b) for b in cfg.pop("benefits", [])]
    spec = WorkupSpec(benefits=benefits, **cfg)

    ana = analyze(spec)
    if ana.error:
        print(json.dumps({"stage": "analyze", "error": ana.error}))
        return 1

    res = build(spec, ana)
    out = {
        "stage": "build",
        "output_path": res.output_path,
        "rate_space": ana.rate_space_summary(),
        "table_counts": dict(res.table_counts),
        "index_ranges": dict(res.index_ranges),
        "warnings": res.warnings,
        "error": res.error or None,
    }
    print(json.dumps(out, indent=2))
    return 1 if res.error else 0


if __name__ == "__main__":
    sys.exit(main())
