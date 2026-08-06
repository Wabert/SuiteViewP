"""Dump the field_specs of a policy-record JSON as a readable table.

Usage:
    python tools/policyrecord/show_field_specs.py '{"path": "PATH"}'
"""
import json
import sys


def main():
    args = json.loads(sys.argv[1])
    with open(args["path"], "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    specs = doc["field_specs"]
    print(f"{len(specs)} specs")
    for i, s in enumerate(specs):
        db2 = s["db2"] or "-"
        cobol = s["cobol"] or "-"
        print(f"{i:3d} | byte {s['byte']:>7} | {s['name'][:38]:38} | db2={db2:32} | cobol={cobol}")


if __name__ == "__main__":
    main()
