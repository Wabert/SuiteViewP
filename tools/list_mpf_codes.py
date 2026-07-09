"""List the type-2 supplemental premium codes in an MPF print file.

Usage:
    venv\\Scripts\\python.exe tools/list_mpf_codes.py <mpf_file>
"""

import json
import sys

sys.path.insert(0, ".")

from suiteview.ratemanager.mpf_exporter import summarize  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: list_mpf_codes.py <mpf_file>"}))
        return 1
    rows = summarize(sys.argv[1])
    print(json.dumps(
        [{"premcode": pc, "benefit": ben, "combos": c, "rows": r}
         for pc, ben, c, r in rows], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
