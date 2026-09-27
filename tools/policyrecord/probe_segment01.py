"""Build the live Segment 01 (or any fixed) policy-record screen and dump it as
plain text, so the byte-stream + token classification can be verified without a
screenshot.

Usage:
    venv\\Scripts\\python.exe tools/policyrecord/probe_segment01.py '{"policy": "U0633187", "region": "CKPR", "segment": "01"}'

Prints, per line, the concatenated visible text, then a summary of how many
tokens resolved to real DB2 values vs example/dim placeholders (with the field
names in each bucket).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.polview.services.policy_service import get_policy_info
from suiteview.polview.ui.policy_record_viewer import load_screen
from suiteview.polview.models.policy_record_builder import build_segment_lines


def main():
    cfg = {"policy": "U0633187", "region": "CKPR", "company": "", "segment": "01"}
    if len(sys.argv) > 1 and sys.argv[1].strip().startswith("{"):
        cfg.update(json.loads(sys.argv[1]))

    pi = get_policy_info(cfg["policy"], cfg["region"], cfg.get("company") or None)
    print(f"policy={cfg['policy']} exists={getattr(pi, 'exists', None)} "
          f"region={getattr(pi, 'region', None)} company={getattr(pi, 'company_name', None)}")

    base = load_screen(cfg["segment"])
    lines = build_segment_lines(cfg["segment"], pi, base)
    if lines is None:
        print("build_segment_lines returned None")
        return 1

    print(f"\n--- rendered {len(lines)} lines ---")
    for line in lines:
        print("|" + "".join(run["text"] for run in line))

    real, example, dim = [], [], []
    for line in lines:
        for run in line:
            if run.get("field") is None:
                continue
            if run.get("example"):
                example.append((run["field"], run["text"]))
            elif run.get("dim"):
                dim.append((run["field"], run["text"]))
            else:
                real.append((run["field"], run["text"]))

    print(f"\nreal={len(real)} example={len(example)} dim={len(dim)}")
    print("\nEXAMPLE tokens:")
    for name, text in example:
        print(f"  {name!r} = {text!r}")
    print("\nDIM tokens:")
    for name, text in dim:
        print(f"  {name!r} = {text!r}")
    print("\nREAL tokens (first 40):")
    for name, text in real[:40]:
        print(f"  {name!r} = {text!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
