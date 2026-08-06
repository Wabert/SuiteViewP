"""Dump the live Segment 01 token stream for a policy with byte + DB2 + raw
value, so it can be compared field-by-field against a real CyberLife 6201 screen.

For every emitted value token it prints: line index, field name, the byte range
(from field_specs), the DB2 source, the raw live value read from DB2, the
formatted on-screen text, and whether it rendered as amber "example" data.

Usage (needs live DB2):
    venv\\Scripts\\python.exe tools/policyrecord/dump_seg01_live.py '{\"policy\": \"U0175443\", \"region\": \"CKPR\"}'
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.core.policy_service import get_policy_info, clear_cache
from suiteview.polview.ui.policy_record_viewer import load_screen
from suiteview.polview.models.policy_record_builder import build_segment_lines


def main():
    cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    policy = cfg.get("policy", "U0175443")
    region = cfg.get("region", "CKPR")

    screen = load_screen("01")
    byte_of = {s["name"]: s.get("byte", "") for s in screen.get("field_specs", [])}
    db2_of = {s["name"]: s.get("db2", "") for s in screen.get("field_specs", [])}

    clear_cache()
    pi = get_policy_info(policy, region, cfg.get("company") or None)
    print(f"policy={policy} exists={getattr(pi, 'exists', None)}")
    lines = build_segment_lines("01", pi, screen)
    if lines is None:
        print("build_segment_lines returned None")
        return 1

    def raw(db2):
        if not db2 or "." not in db2:
            return None
        tbl, col = db2.split(".", 1)
        try:
            return pi.data_item(tbl.strip(), col.strip())
        except Exception as exc:
            return f"<err {exc}>"

    for i, line in enumerate(lines):
        print(f"\n[{i:2d}] {''.join(r['text'] for r in line)!r}")
        for r in line:
            name = r.get("field")
            if not name:
                continue
            db2 = db2_of.get(name, "")
            mark = "EX" if r.get("example") else "  "
            print("   %s b=%-7s %-42s db2=%-34s raw=%-14r text=%r"
                  % (mark, byte_of.get(name, ""), name[:42], db2, raw(db2), r.get("text")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
