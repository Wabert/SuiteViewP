"""Build verified allocation metadata, correcting the archive's byte offsets."""

import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.policyrecord.extract_policy_record_screen import (
    _classify, _parse_layout, _repair_layout_html, _split_tables,
    _TerminalParser, _normalize_lines, _trim_trailing_blank_lines,
)
from suiteview.polview.models.policy_record_allocations import (
    ENTRY_TABLE, FLAG_COLUMNS, HEADER_TABLE, VALUE_FIELDS,
)


def main():
    source = ROOT / "docs" / "Policy Record" / "Sample 6257 screen.htm"
    tables = _split_tables(source.read_text(encoding="utf-8"))
    layout = next(_repair_layout_html(table) for table in tables if _classify(table) == "layout")
    fields, specs = _parse_layout(layout)
    parser = _TerminalParser()
    parser.feed(next(table for table in tables if _classify(table) == "terminal"))
    lines = _trim_trailing_blank_lines(_normalize_lines(parser._lines), keep=1)
    for line in lines:
        for run in line:
            if run.get("field") == "Screen Name":
                run["text"] = "6257,"
    for spec in specs:
        name = spec["name"]
        if name == "Number of Allocations":
            spec.update(byte="29-30", db2=None)
        elif name.startswith("Allocation ") or name == "Fund Allocation Units":
            if name not in ("Allocation Method",):
                bounds = [int(part) - 1 for part in spec["byte"].split("-")]
                spec["byte"] = "-".join(str(part) for part in bounds)
        if name == "Allocation Method":
            spec["cobol"] = "FALALLOM-ALLOCATION-METHOD"
        elif name == "Segment Type":
            spec["db2"] = f"{HEADER_TABLE}.FND_TRS_TYP_CD"
        elif name == "Last Allocation Change Date":
            spec["db2"] = (
                f"{HEADER_TABLE}.LST_ALC_CHG_DT / "
                f"{HEADER_TABLE}.CRG_DED_ALC_EFF_DT (C sets)"
            )
        fields[name] = [
            f"{label}: {spec[key]}" for key, label in (("cobol", "COBOL"), ("db2", "DB2"))
            if spec.get(key)
        ]
    fields["Segment Identification"] = ["COBOL: FALIDENT-SEGMENT-ID", "Constant: 57"]
    fields["Segment Length"] = [
        "COBOL: FALLNGTH-SEGMENT-LENGTH",
        "30 header bytes + 16 bytes per allocation (including the P/D/U redefines).",
    ]
    fields["Flag Byte A"] = [
        "COBOL: FALFLAGA-FLAG-BYTE-A",
        *[f"Bit {index}: {HEADER_TABLE}.{column}" for index, column in enumerate(FLAG_COLUMNS)],
        "Bits 3-6 reserved; bit 7 group-control generation has no verified DB2 source.",
        "Bit 0: internally generated. Bit 1: automated closed-fund processing.",
        "Bit 2 = 1 means monthliversary processing has NOT occurred since addition.",
    ]
    fields["Flag Byte U"] = [
        "COBOL: FALFLAGU-USER-FLAG-BYTE", "User-reserved byte; displayed as an example.",
    ]
    fields["Last Allocation Change Date"] = [
        "COBOL: FALLCGDT-LAST-CHANGE-DATE",
        f"DB2: {HEADER_TABLE}.LST_ALC_CHG_DT (non-C sets)",
        f"DB2: {HEADER_TABLE}.CRG_DED_ALC_EFF_DT (C charge-deduction sets)",
    ]
    fields["Type Sequence"].append(
        f"Join {HEADER_TABLE}.FND_ALC_SEQ_NBR to {ENTRY_TABLE}.FND_ALC_SEQ_NBR."
    )
    fields["Number of Allocations"] = [
        "COBOL: FALALNUM-NUMBER-OF-ALLOCATIONS",
        "Derived: count of LH_FND_ALC rows for this allocation type and set sequence.",
        "SEG_IDX_NBR orders the entries; the workbook swaps its description with FND_ALC_SEQ_NBR.",
    ]
    for value_type, (name, column, cobol, digits, decimals) in VALUE_FIELDS.items():
        fields[name] = [
            f"COBOL: {cobol}", f"DB2: {ENTRY_TABLE}.{column}",
            f"Type {value_type}: {digits} packed digits, {decimals} decimal places.",
        ]
    specs.extend([
        {"name": "Fund Allocation Dollars", "byte": "40-45",
         "db2": f"{ENTRY_TABLE}.FND_ALC_AMT", "cobol": VALUE_FIELDS["D"][2]},
        {"name": "Fund Allocation Percent", "byte": "40-42",
         "db2": f"{ENTRY_TABLE}.FND_ALC_PCT", "cobol": VALUE_FIELDS["P"][2]},
    ])
    for name in ("Screen Name", "Policy Number", "Current Date", "Part of the user ID?", "Region and Company"):
        fields[name] = []
    rows = []
    for spec in specs:
        mappings = "<br>".join(html.escape(value) for value in fields[spec["name"]])
        rows.append(
            f'<tr><td>{spec["byte"]}</td><td><b>{html.escape(spec["name"])}</b><br>{mappings}</td></tr>'
        )
    document = {
        "segment": "57", "title": "Fund Allocation (screen 6257)",
        "source": "Sample 6257 screen.htm; mappings verified with CyberDoc D202 pp.90-96/602 and live DB2",
        "lines": lines, "fields": fields, "field_specs": specs,
        "layout_html": (
            '<p>30-byte header; each allocation adds 16 bytes. Entry offsets below describe the first entry.</p>'
            '<table border="1" cellspacing="0" cellpadding="3">'
            '<tr bgcolor="#E6A0AA"><th>Byte</th><th>Field / source</th></tr>'
            + "".join(rows) + "</table>"
        ),
    }
    destination = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_57.json"
    destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(destination), "fields": len(fields)}))


if __name__ == "__main__":
    main()
