"""Render Segment 66 (Advanced Product) live via the real builder and print it so
the output can be diffed against the ground-truth screenshot (img_016, U0361148).

This drives the exact production code path -- ``build_segment_lines("66", pi)`` --
then prints, per line, the visible text (token texts joined, since separators
carry their own spacing) plus a token-level breakdown (text / field / example).
It also prints the captured-reference ``lines`` from ``seg_66.json`` (which match
the screenshot) so the two can be compared line-by-line before shipping.

Usage (needs live DB2):
    venv\\Scripts\\python.exe tools/policyrecord/probe_segment66.py '{\"policy\": \"U0361148\", \"region\": \"CKPR\"}'
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

_SEG_PATH = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_66.json"


def _visible(line):
    return "".join(str(run.get("text", "")) for run in line)


def _value_tokens(line):
    """Return only the hover-aware value tokens (skip pure spacing runs)."""
    return [run for run in line if run.get("field")]


def main():
    cfg = json.loads(sys.argv[1])
    policy = cfg["policy"]
    region = cfg.get("region", "CKPR")

    with open(_SEG_PATH, "r", encoding="utf-8") as fh:
        screen = json.load(fh)
    ref_lines = screen.get("lines", [])

    clear_cache()
    pi = get_policy_info(policy, region, cfg.get("company"))
    if pi is None or not getattr(pi, "exists", False):
        print(json.dumps({"found": False, "policy": policy}))
        return

    live = build_segment_lines("66", pi, screen)
    if live is None:
        print(f"policy={policy}: no LH_NON_TRD_POL row -> falls back to reference "
              f"(not an advanced product?)")
        return

    print(f"policy={policy} region={region}  live_lines={len(live)}  ref_lines={len(ref_lines)}")
    print("\n================= VISIBLE TEXT (live vs captured reference) =================")
    for i in range(max(len(live), len(ref_lines))):
        lv = _visible(live[i]) if i < len(live) else ""
        rf = _visible(ref_lines[i]) if i < len(ref_lines) else ""
        flag = "" if lv.rstrip() == rf.rstrip() else "   <-- DIFF"
        print(f"[{i:02d}] LIVE |{lv}|{flag}")
        print(f"     REF  |{rf}|")

    print("\n================= LIVE VALUE TOKENS =================")
    for i, line in enumerate(live):
        toks = _value_tokens(line)
        if not toks:
            continue
        print(f"\n--- line {i} ---")
        for run in toks:
            mark = "EX" if run.get("example") else "  "
            print("  %s %-46s = %r" % (mark, (run.get("field") or "")[:46], run.get("text")))


if __name__ == "__main__":
    main()
