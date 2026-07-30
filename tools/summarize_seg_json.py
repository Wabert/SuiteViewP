"""Summarize a policy-record segment JSON for quick human review.

Prints the terminal ``lines`` as reconstructed text (one row per line, with a
``|`` marking each hover-aware value run), followed by the ordered
``field_specs`` (name / byte / db2 / cobol) and the ``fields`` tooltip keys.

Usage:
    python tools/summarize_seg_json.py "{\"path\": \"C:/tmp/segjson/seg_67.json\"}"
"""

import json
import sys


def _line_text(line):
    parts = []
    for run in line:
        text = run.get("text", "")
        if run.get("field"):
            parts.append("|" + text + "|")
        else:
            parts.append(text)
    return "".join(parts)


def main():
    args = json.loads(sys.argv[1])
    with open(args["path"], "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    print("== segment", doc.get("segment"), "-", doc.get("title"), "==")
    print("source:", doc.get("source"))
    print("template:", doc.get("template", False))
    print()
    print("---- terminal lines (%d) ----" % len(doc.get("lines", [])))
    for i, line in enumerate(doc.get("lines", [])):
        print("%2d: %s" % (i, _line_text(line)))
    print()
    specs = doc.get("field_specs", []) or []
    print("---- field_specs (%d) ----" % len(specs))
    for s in specs:
        print("  byte %-8s %-40s db2=%-28s cobol=%s" % (
            s.get("byte"), s.get("name"), s.get("db2"), s.get("cobol")))
    print()
    fields = doc.get("fields", {}) or {}
    print("---- fields tooltip keys (%d) ----" % len(fields))
    for k in fields:
        print("  ", k, "->", fields[k])

    if args.get("pairs"):
        print()
        print("---- ordered (field: text) value runs ----")
        for i, line in enumerate(doc.get("lines", [])):
            for run in line:
                if run.get("field"):
                    print("  L%02d  %-40s = %r" % (
                        i, run.get("field"), run.get("text")))


if __name__ == "__main__":
    main()
