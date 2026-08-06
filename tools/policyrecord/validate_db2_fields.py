"""
Validate DB2 field names used in the codebase against the authoritative
COBOL/DB2 translation workbook. Writes results to docs/field_validation_report.txt
"""
import xlrd
import re
import os
import glob
import sys

# Load authoritative field names from the translation workbook
wb = xlrd.open_workbook("docs/COBOLDB2translation.xls")
ws = wb.sheet_by_name("Translation")

# Build mapping: table -> set of valid field names
table_fields = {}
for r in range(1, ws.nrows):
    table = str(ws.cell_value(r, 3)).strip()
    field = str(ws.cell_value(r, 4)).strip()
    if table and field:
        if table not in table_fields:
            table_fields[table] = set()
        table_fields[table].add(field)

out = open("docs/field_validation_report.txt", "w")

def p(s=""):
    print(s)
    out.write(s + "\n")

p(f"Loaded {len(table_fields)} tables from workbook")
p(f"Total fields: {sum(len(v) for v in table_fields.values())}")
p()

# Find all Python files to scan
py_files = []
for root, dirs, files in os.walk("suiteview/polview"):
    for f in files:
        if f.endswith(".py"):
            py_files.append(os.path.join(root, f))

p(f"Scanning {len(py_files)} Python files...")
p()

# Patterns
field_in_data_item = re.compile(
    r'data_item\(\s*["\']([A-Z_]+)["\']\s*,\s*["\']([A-Z_0-9]+)["\']'
)

field_in_data_item_where = re.compile(
    r'data_item_where\(\s*["\']([A-Z_]+)["\']\s*,\s*["\']([A-Z_0-9]+)["\']\s*,\s*["\']([A-Z_0-9]+)["\']'
)

data_item_pattern = re.compile(
    r'(?:data_item|data_item_array|data_item_count|data_item_where|'
    r'data_item_where_multi|data_items_where|fetch_table|get_rows_where|'
    r'find_row_index|_ensure_table_loaded)\s*\(\s*["\']([A-Z_]+)["\']'
)

field_in_row_get = re.compile(
    r'row(?:\[\s*|\.\s*get\s*\(\s*)["\']([A-Z_][A-Z_0-9]+)["\']'
)

all_issues = []

for filepath in py_files:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check data_item("TABLE", "FIELD") calls
    for m in field_in_data_item.finditer(content):
        table, field = m.group(1), m.group(2)
        if table in table_fields and field not in table_fields[table]:
            pos = m.start()
            line_no = content[:pos].count("\n") + 1
            all_issues.append((filepath, line_no, table, field, "FIELD NOT IN TABLE"))
    
    # Check data_item_where("TABLE", "RETURN", "FILTER") calls
    for m in field_in_data_item_where.finditer(content):
        table, ret_field, filter_field = m.group(1), m.group(2), m.group(3)
        if table in table_fields:
            if ret_field not in table_fields[table]:
                pos = m.start()
                line_no = content[:pos].count("\n") + 1
                all_issues.append((filepath, line_no, table, ret_field, "RETURN FIELD NOT IN TABLE"))
            if filter_field not in table_fields[table]:
                pos = m.start()
                line_no = content[:pos].count("\n") + 1
                all_issues.append((filepath, line_no, table, filter_field, "FILTER FIELD NOT IN TABLE"))

# Deduplicate
seen = set()
unique_issues = []
for filepath, line_no, table, field, reason in all_issues:
    key = (filepath, table, field)
    if key not in seen:
        seen.add(key)
        unique_issues.append((filepath, line_no, table, field, reason))

p("=" * 80)
p("SECTION 1: INVALID FIELDS — Referenced in data_item() but NOT in workbook")
p("=" * 80)
for filepath, line_no, table, field, reason in sorted(unique_issues):
    short_path = filepath.replace("suiteview/polview/", "")
    p(f"  {short_path}:{line_no}  {table}.{field}  [{reason}]")

p(f"\nTotal unique field issues: {len(unique_issues)}")

# Check for unknown tables
p()
p("=" * 80)
p("SECTION 2: UNKNOWN TABLES — Referenced but NOT in the workbook")
p("=" * 80)
unknown_tables = set()
for filepath in py_files:
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    for m in data_item_pattern.finditer(content):
        table = m.group(1)
        if table not in table_fields:
            unknown_tables.add(table)

for t in sorted(unknown_tables):
    p(f"  {t}")
p(f"\nTotal unknown tables: {len(unknown_tables)}")

# Check CL_POLREC row.get() fields
p()
p("=" * 80)
p("SECTION 3: CL_POLREC row.get()/row[] fields NOT found in ANY DB2 table")
p("=" * 80)

cl_files = glob.glob("suiteview/polview/models/cl_polrec/CL_POLREC_*.py")
cl_files.append("suiteview/polview/models/policy_information.py")

for filepath in sorted(cl_files):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    row_fields = set(field_in_row_get.findall(content))
    short = os.path.basename(filepath)
    
    for field in sorted(row_fields):
        in_any = False
        for t, fields in table_fields.items():
            if field in fields:
                in_any = True
                break
        if not in_any:
            p(f"  {short}: field '{field}' not found in ANY DB2 table")

# For reference: print fields for key tables
p()
p("=" * 80)
p("SECTION 4: REFERENCE — Key table field lists from the workbook")
p("=" * 80)
key_tables = [
    "LH_BAS_POL", "TH_BAS_POL", "LH_COV_PHA", "TH_COV_PHA",
    "LH_NON_TRD_POL", "LH_SST_XTR_CRG", "LH_COV_INS_RNL_RT",
    "LH_SPM_BNF", "LH_POL_TOTALS", "LH_POL_YR_TOT",
    "LH_CSH_VAL_LOAN", "LH_FND_VAL_LOAN", "FH_FIXED",
]
for t in key_tables:
    if t in table_fields:
        fields = sorted(table_fields[t])
        p(f"\n  {t} ({len(fields)} fields):")
        for f in fields:
            p(f"    {f}")

out.close()
print("\nReport written to docs/field_validation_report.txt")
