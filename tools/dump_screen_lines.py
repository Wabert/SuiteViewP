"""Dump the terminal-screen lines of a policy-record JSON, showing each run's
text and (field) so the authentic on-screen field layout can be studied.

Usage:
    venv\\Scripts\\python.exe tools/dump_screen_lines.py '{"path": "PATH"}'
"""
import json
import sys


def main():
    args = (
        json.loads(sys.argv[1])
        if sys.argv[1].lstrip().startswith("{")
        else {"path": sys.argv[1]}
    )
    with open(args["path"], "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    lines = doc.get("lines", [])
    print(f"{len(lines)} lines")
    for i, line in enumerate(lines):
        text = "".join(r["text"] for r in line)
        print(f"\n[{i:2d}] {text!r}")
        for r in line:
            if r.get("field"):
                extra = []
                if r.get("db2"):
                    extra.append(f"db2={r['db2']}")
                if r.get("role"):
                    extra.append(f"role={r['role']}")
                if r.get("cobol"):
                    extra.append(f"cobol={r['cobol']}")
                print(f"      -> {r['text']!r:14} field={r['field']!r:42} "
                      + "  ".join(extra))


if __name__ == "__main__":
    main()
