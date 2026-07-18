"""Dump cached values of one column range from an .xlsx/.xlsm, fast.

Usage:
    dump_xlsx_col.py <file> <sheet> <col_letter> <first_row> <last_row>

Prints "row | value" for non-empty cells only. Values-only (data_only) load.
"""
import sys
import json

try:
    import openpyxl
    from openpyxl.utils import column_index_from_string
except ImportError:
    print(json.dumps({"error": "openpyxl not installed"}))
    sys.exit(1)


def main():
    if len(sys.argv) < 6:
        print(json.dumps({"error": "Usage: dump_xlsx_col.py <file> <sheet> <col> <r0> <r1>"}))
        sys.exit(1)
    path, sheet, col = sys.argv[1], sys.argv[2], sys.argv[3]
    r0, r1 = int(sys.argv[4]), int(sys.argv[5])
    ci = column_index_from_string(col)

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    for row in ws.iter_rows(min_row=r0, max_row=r1, min_col=ci, max_col=ci):
        v = row[0].value
        if v is not None and v != "":
            print(f"{row[0].row} | {v}")
    wb.close()


if __name__ == "__main__":
    main()
