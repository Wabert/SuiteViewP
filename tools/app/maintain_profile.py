"""Preview profile restructuring; --apply moves data and --cleanup removes retired items."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from suiteview.core.profile_maintenance import maintain_profile, plan_profile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply; default is a read-only preview.")
    parser.add_argument("--cleanup", action="store_true", help="Include the reviewed retired data and previews.")
    args = parser.parse_args()
    try:
        operation = maintain_profile if args.apply else plan_profile
        result = operation(cleanup=args.cleanup)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, "applied": args.apply, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
