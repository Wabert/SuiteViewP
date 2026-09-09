"""Read a typed ABR request and emit one JSON response; never send email."""
import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from suiteview.abrquote.automation import QuoteRequest, quote_abr


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true",
                        help="Validate request without imports that initiate data access")
    args = parser.parse_args(argv)
    try:
        request = QuoteRequest.from_dict(json.loads(args.request.read_text(encoding="utf-8-sig")))
        if args.validate_only:
            response = {"status": "valid", "live_access": False}
        else:
            # Legacy diagnostic prints must not contaminate the machine channel.
            with redirect_stdout(sys.stderr):
                response = quote_abr(request)
        print(json.dumps(response, allow_nan=False, ensure_ascii=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__,
                          "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
