"""Extract all VBA modules from an .xlsm/.xlsb workbook to a directory.

Usage:
    extract_workbook_vba.py <workbook> <out_dir>

Writes one <module>.bas file per VBA module (oletools/olevba) and prints a JSON
summary {module: line_count}.
"""
import sys
import json
from pathlib import Path

try:
    from oletools.olevba import VBA_Parser
except ImportError:
    print(json.dumps({"error": "oletools not installed. Run: venv\\Scripts\\python.exe -m pip install oletools"}))
    sys.exit(1)


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: extract_workbook_vba.py <workbook> <out_dir>"}))
        sys.exit(1)
    workbook, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    parser = VBA_Parser(workbook)
    summary = {}
    for (_fn, _stream, vba_filename, vba_code) in parser.extract_all_macros():
        name = Path(vba_filename).stem or vba_filename
        out = out_dir / f"{name}.bas"
        out.write_text(vba_code, encoding="utf-8", errors="replace")
        summary[name] = vba_code.count("\n") + 1
    parser.close()
    print(json.dumps({"out_dir": str(out_dir), "modules": summary}, indent=2))


if __name__ == "__main__":
    main()
