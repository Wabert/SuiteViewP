"""List defined names in an .xlsx/.xlsm workbook with their refers-to targets.

Usage:
    list_defined_names.py <file> [<filter_substring>]

Emits one line per defined name: name | refers_to. Case-insensitive filter.
"""
import sys
import json

try:
    import openpyxl
except ImportError:
    print(json.dumps({"error": "openpyxl not installed"}))
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: list_defined_names.py <file> [<filter>]"}))
        sys.exit(1)
    path = sys.argv[1]
    flt = sys.argv[2].lower() if len(sys.argv) > 2 else None

    wb = openpyxl.load_workbook(path, read_only=True)
    for name, dn in sorted(wb.defined_names.items()):
        if flt and flt not in name.lower():
            continue
        print(f"{name} | {dn.attr_text}")
    wb.close()


if __name__ == "__main__":
    main()
