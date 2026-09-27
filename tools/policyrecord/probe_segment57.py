"""Read-only allocation-segment probe and UL045809 capture comparison."""

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.polview.services.policy_service import get_policy_info
from suiteview.polview.models.policy_record_builder import build_segment_lines
from suiteview.polview.ui.policy_record_viewer import load_screen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default="UL045809")
    parser.add_argument("--company", default="01")
    parser.add_argument("--region", default="CKPR")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expect-ul045809", action="store_true")
    args = parser.parse_args()
    if os.environ.get("SUITEVIEW_LOCAL_DATA") == "1":
        raise RuntimeError("Live verification requires local data disabled.")
    pi = get_policy_info(
        args.policy.strip().upper(), region=args.region.strip().upper(),
        company_code=args.company.strip().upper(),
    )
    if pi is None or not pi.identity.exists:
        raise RuntimeError(f"Policy {args.policy} was not found.")
    sources = {}
    for table in ("LH_FND_TRS_ALC_SET", "LH_FND_ALC"):
        sources[table] = pi.fetch_table(table)
        error = pi.table_error(table)
        if error:
            raise RuntimeError(f"{table}: {error}")
    lines = build_segment_lines("57", pi, load_screen("57"))
    text = ["".join(run["text"] for run in line) for line in lines or []]
    result = {"policy": pi.identity.policy_number, "sources": sources, "lines": lines, "text": text}
    if args.expect_ul045809:
        expected = "57 0046 10000000 00000000 P 1 12/15/1984 1 1 U1 P 100.00"
        body = []
        for line in (lines or [])[1:]:
            if not any(run.get("field") for run in line):
                break
            body.append(" ".join("".join(run["text"] for run in line).split()))
        if body != [expected]:
            raise AssertionError(f"Capture mismatch:\nExpected: {expected}\nActual: {body}")
        result["capture_match"] = True
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "lines"},
                     indent=2, default=str))


if __name__ == "__main__":
    main()
