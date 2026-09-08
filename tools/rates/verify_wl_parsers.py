"""Exercise strict Whole Life parsers on complete local prints; no DB access."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.ratemanager.whole_life import parsers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for kind in ("cvf", "pui", "iaf", "nsp"):
        parser.add_argument("--" + kind, action="append", default=[])
    parser.add_argument("--user-code")
    args = parser.parse_args()
    if args.iaf and not args.user_code:
        parser.error("--user-code is required for IAF prints; it cannot be inferred.")
    failed = False
    for kind in ("cvf", "pui", "iaf", "nsp"):
        for filename in getattr(args, kind):
            start = time.monotonic()
            try:
                parse = getattr(parsers, "parse_" + kind)
                rows = parse(filename, args.user_code) if kind == "iaf" else parse(filename)
                keys = getattr(parsers, ("CV" if kind == "cvf" else kind.upper()) + "_KEYS")
                unique = len({tuple(row[key] for key in keys) for row in rows})
                result = {
                    "ok": True, "kind": kind, "file": filename,
                    "rows": len(rows), "unique_keys": unique, "identical_duplicates": len(rows) - unique,
                    "negative_rates": sum(row["RATE"] < 0 for row in rows),
                    "decimal_rates": all(isinstance(row["RATE"], Decimal) for row in rows),
                    "users": dict(Counter(row["USER_CODE"] for row in rows)),
                    "sha256": hashlib.sha256(Path(filename).read_bytes()).hexdigest(),
                }
                del rows
            except Exception as exc:
                failed = True
                result = {"ok": False, "kind": kind, "file": filename, "error": str(exc)}
            result["seconds"] = round(time.monotonic() - start, 2)
            print(json.dumps(result), flush=True)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
