"""Read a sheet from an XLS file and output as JSON."""
import sys
import json

try:
    import xlrd
except ImportError:
    print(json.dumps({"error": "xlrd not installed. Run: pip install xlrd"}))
    sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: read_xls_sheet.py <file> [sheet_name] [max_rows]"}))
        sys.exit(1)

    file_path = sys.argv[1]
    sheet_name = sys.argv[2] if len(sys.argv) > 2 else None
    max_rows = int(sys.argv[3]) if len(sys.argv) > 3 else 100

    wb = xlrd.open_workbook(file_path)

    if sheet_name is None:
        # List all sheet names
        print(json.dumps({"sheets": wb.sheet_names()}))
        return

    sheet = wb.sheet_by_name(sheet_name)
    
    # Read header row
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    
    rows = []
    for r in range(1, min(sheet.nrows, max_rows + 1)):
        row_data = {}
        for c in range(sheet.ncols):
            val = sheet.cell_value(r, c)
            if isinstance(val, float) and val == int(val):
                val = int(val)
            row_data[headers[c]] = val
        rows.append(row_data)

    print(json.dumps({
        "sheet": sheet_name,
        "total_rows": sheet.nrows - 1,
        "showing": len(rows),
        "columns": headers,
        "rows": rows
    }, indent=2, default=str))

if __name__ == "__main__":
    main()
