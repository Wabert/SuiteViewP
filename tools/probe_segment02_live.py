"""Render Segment 02 (Coverage) live via the real builder and print it so the
output can be diffed against the ground-truth screenshot (img_002, U0361148).

Drives the production path -- ``build_segment_lines("02", pi)`` -- and prints,
per line, the visible text plus each hover-aware value token (text / field /
example).  Segment 02 repeats once per LH_COV_PHA coverage phase.

Usage (needs live DB2):
    venv\\Scripts\\python.exe tools/probe_segment02_live.py '{\"policy\": \"U0361148\", \"region\": \"CKPR\"}'
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.policy_service import get_policy_info, clear_cache
from suiteview.polview.models.policy_record_builder import build_segment_lines

_SEG_PATH = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_02.json"


def _visible(line):
    return "".join(str(run.get("text", "")) for run in line)


def _value_tokens(line):
    return [run for run in line if run.get("field")]


def main():
    cfg = json.loads(sys.argv[1])
    policy = cfg["policy"]
    region = cfg.get("region", "CKPR")

    with open(_SEG_PATH, "r", encoding="utf-8") as fh:
        screen = json.load(fh)

    clear_cache()
    pi = get_policy_info(policy, region, cfg.get("company"))
    if pi is None or not getattr(pi, "exists", False):
        print(json.dumps({"found": False, "policy": policy}))
        return

    live = build_segment_lines("02", pi, screen)
    if live is None:
        print(f"policy={policy}: no LH_COV_PHA rows -> falls back to reference")
        return

    print(f"policy={policy} region={region}  live_lines={len(live)}")
    print("\n================= VISIBLE TEXT (live) =================")
    for i, line in enumerate(live):
        print(f"[{i:02d}] |{_visible(line)}|")

    print("\n================= LIVE VALUE TOKENS =================")
    for i, line in enumerate(live):
        toks = _value_tokens(line)
        if not toks:
            continue
        print(f"\n--- line {i} ---")
        for run in toks:
            mark = "EX" if run.get("example") else "  "
            print("  %s %-48s = %r" % (mark, (run.get("field") or "")[:48], run.get("text")))

    fmap = screen.get("fields", {})
    missing = sorted({
        run.get("field") for line in live for run in _value_tokens(line)
        if run.get("field") not in fmap
    })
    print("\n================= HOVER COVERAGE =================")
    if missing:
        print("MISSING from fields map (no tooltip):")
        for m in missing:
            print(f"  - {m}")
    else:
        print("OK: every emitted field resolves to a fields-map key.")


if __name__ == "__main__":
    main()
