"""Probe the production Segment 59 builder with live policy data.

Usage:
    venv\\Scripts\\python.exe tools/policyrecord/probe_segment59.py U0633187 CKPR
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from suiteview.core.policy_service import clear_cache, get_policy_info
from suiteview.polview.models.policy_record_builder import build_segment_lines
from suiteview.polview.ui.policy_record_viewer import load_screen


def main() -> int:
    policy = sys.argv[1] if len(sys.argv) > 1 else "U0633187"
    region = sys.argv[2] if len(sys.argv) > 2 else "CKPR"
    clear_cache()
    pi = get_policy_info(policy, region)
    screen = load_screen("59")
    lines = build_segment_lines("59", pi, screen)
    if not lines:
        print("No live Segment 59 Type 1 data")
        return 1

    fields = screen.get("fields", {})
    for index, line in enumerate(lines):
        text = "".join(run.get("text", "") for run in line)
        print(f"[{index:02d}] {text!r}")
        for run in line:
            field = run.get("field")
            if not field:
                continue
            state = "EXAMPLE" if run.get("example") else "LIVE"
            mappings = " | ".join(fields.get(field, []))
            print(
                f"     {state:7} {field}: {run.get('text')!r}"
                f" [{mappings}]"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
