"""Probe the production Segment 53 builder with live policy data.

Usage:
    venv\\Scripts\\python.exe tools\\probe_segment53.py UE142109 CKPR
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.core.policy_service import clear_cache, get_policy_info
from suiteview.polview.models.policy_record_builder import build_segment_lines
from suiteview.polview.ui.policy_record_viewer import load_screen


def main() -> int:
    policy = sys.argv[1] if len(sys.argv) > 1 else "UE142109"
    region = sys.argv[2] if len(sys.argv) > 2 else "CKPR"
    clear_cache()
    pi = get_policy_info(policy, region)
    screen = load_screen("53")
    lines = build_segment_lines("53", pi, screen)
    if not lines:
        print("No verified live Segment 53 Sweep Fund data")
        return 1

    sweep_error = pi.table_error("LH_SWF_SCH")
    if sweep_error:
        print(f"LH_SWF_SCH unavailable: {sweep_error}")

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
