"""Search for specific table's fields in the COBOL DB2 translation workbook."""
import sys
import json
import xlrd

def main():
    file_path = sys.argv[1]
    search_table = sys.argv[2] if len(sys.argv) > 2 else None

    wb = xlrd.open_workbook(file_path)
    sheet = wb.sheet_by_name("Translation")

    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]

    results = []
    for r in range(1, sheet.nrows):
        row_data = {}
        for c in range(sheet.ncols):
            val = sheet.cell_value(r, c)
            if isinstance(val, float) and val == int(val):
                val = int(val)
            row_data[headers[c]] = val

        table = str(row_data.get("Table", "")).strip()
        if search_table and search_table.upper() not in table.upper():
            continue

        results.append({
            "seg": row_data.get("SEG #", ""),
            "cobol": str(row_data.get("COBOL Name", "")).strip(),
            "table": table,
            "field": str(row_data.get("Field Name", "")).strip(),
            "translation": str(row_data.get("Translation", "")).strip(),
        })

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
