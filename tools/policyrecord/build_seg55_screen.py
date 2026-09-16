"""Generate corrected 6255 hover, record-layout and captured-reference metadata."""

import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.polview.models.policy_record_builder import _sep, _tok, _wrap_record_groups
from suiteview.polview.models.policy_record_fund_control import (
    COMMON_FIELDS, COMMON_TABLE, FIXED_FIELDS, FIXED_TABLE, FLAG_COLUMNS,
)


def main():
    specs = [
        {"name": "Segment Identification", "byte": "1-2", "cobol": "FIFIDENT-SEGMENT-ID", "kind": "header"},
        {"name": "Segment Length", "byte": "3-4", "cobol": "FIFLNGTH-SEGMENT-LENGTH", "kind": "header"},
        {"name": "Flag Byte A", "byte": "5", "cobol": "FIFFLAGA-FLAG-BYTE-A", "kind": "flag",
         "bits": [{"bit": bit, "db2": f"{COMMON_TABLE}.{column}"} for bit, column in enumerate(FLAG_COLUMNS)]},
        {"name": "Flag Byte B", "byte": "6", "cobol": "FIFFLAGB-FLAG-BYTE-B", "kind": "flag"},
        {"name": "Flag Byte U", "byte": "7", "cobol": "FIFFLAGU-USER-FLAG-BYTE", "kind": "flag"},
    ]
    for table, definitions in ((COMMON_TABLE, COMMON_FIELDS), (FIXED_TABLE, FIXED_FIELDS)):
        if table == FIXED_TABLE:
            specs.append({"name": "Reserved", "byte": "37-45", "cobol": "FIFRESV-RESERVED", "kind": "reserved"})
        specs.extend(
            {"name": name, "db2": f"{table}.{column}", "cobol": cobol,
             "byte": byte, "kind": kind, "width": width,
             "applies": "Common area" if table == COMMON_TABLE else "Fixed funds only"}
            for name, column, cobol, byte, kind, width in definitions
        )
    specs.extend([
        {"name": "Number of Interest Rate/Limit Pairs", "byte": "80-81",
         "cobol": "FIFTNENT-NUMBER-OF-TIERS", "db2": f"{FIXED_TABLE}.TIER_ITS_RT_NBR",
         "kind": "tier", "applies": "Tiered/duration portfolio only; rendering guarded pending live verification"},
        {"name": "Tier Interest Rate", "byte": "82-84 (+8 per entry, up to 8)",
         "cobol": "FIFTRATE-TIER-RATE",
         "db2": "LH_AMT_TIERED_ITS.TIER_ITS_RT / LH_DUR_TIERED_ITS.TIER_ITS_RT",
         "kind": "tier", "applies": "Method 1T / 1D respectively; rendering guarded"},
        {"name": "Tier Interest Rate Limit", "byte": "85-89 (+8 per entry, up to 8)",
         "cobol": "FIFTLIMT-TIER-LIMIT",
         "db2": "LH_AMT_TIERED_ITS.ITS_TIER_AMT / LH_DUR_TIERED_ITS.ITS_TIER_DUR",
         "kind": "tier", "applies": "Amount / duration redefine; rendering guarded"},
    ])
    fields = {}
    for spec in specs:
        descriptions = [f"Byte: {spec['byte']}", f"COBOL: {spec['cobol']}"]
        if spec.get("db2"):
            descriptions.append(f"DB2: {spec['db2']}")
        if spec.get("applies"):
            descriptions.append(spec["applies"])
        if spec["kind"] == "flag":
            descriptions.extend(
                f"Bit {bit['bit']}: {bit['db2']}" for bit in spec.get("bits", [])
            )
            if not spec.get("bits"):
                descriptions.append("Reserved; no DB2 mapping. Captured zeros are amber examples.")
        elif spec["kind"] == "rate":
            descriptions.append("Format: 3-byte packed, 2 whole digits and 3 decimals; e.g. 4.000, not .040.")
        elif spec["kind"] == "integer":
            descriptions.append(f"Format: {spec['width']} packed digits, no decimals.")
        elif spec["kind"] == "binary":
            descriptions.append(f"Format: {spec['width']}-byte unsigned binary; display as a decimal integer.")
        elif spec["kind"] == "date":
            descriptions.append("Format: 4-byte internal date; MM/DD/YYYY. High-date sentinel displays **/**/****.")
        elif spec["kind"] == "text":
            descriptions.append(f"Format: {spec['width']} character(s); stored blanks remain blank.")
        fields[spec["name"]] = descriptions
    fields["Segment Length"].append("Verified fixed non-tiered length 79 = 45-byte common area + 34-byte fixed area.")
    fields["High Phase"].append("Two bytes (D202 pp.75/600), not the stale one-byte HTML layout.")
    fields["Number of Interest Rate/Limit Pairs"].append(
        "D202 documents up to eight 8-byte rate/limit pairs, ascending by limit. "
        "SEG_IDX_NBR and live stored length/count semantics require verification."
    )
    for name in ("Screen Name", "Policy Number", "Current Date", "Part of the user ID?", "Region and Company"):
        fields[name] = []
    rows = []
    for spec in specs:
        details = "<br>".join(html.escape(value) for value in fields[spec["name"]])
        rows.append(f"<tr><td>{html.escape(spec['byte'])}</td><td><b>{html.escape(spec['name'])}</b><br>{details}</td></tr>")
    reference = [
        ["55", "0079", "00100001", "00000000", "00000000",
         "1", "GP", "F", "0", "00", "0", "0", "0", "0", "0", "0", "0", "1", "0", "00", "0", "0",
         "**/**/****", " ", ".000",
         "1", " ", "1", "1", ".000", "2", "999", "0", "0", "1", " " * 11, ".000", "**/**/****"],
        ["55", "0079", "00000001", "00000000", "00000000",
         "1", "U1", "F", "0", "00", "0", "0", "1", "0", "1", "1", "1", "1", "1", "00", "0", "0",
         "**/**/****", " ", ".000",
         "2", "3", "1", "1", "4.000", "0", "0", " ", "0", "0", "ANICO1983  ", "6.000", "12/14/2000"],
    ]
    display_specs = [spec for spec in specs if spec["kind"] not in ("reserved", "tier")]
    lines = [[_sep("  "), _tok("6255,", "Screen Name"), _sep(" "), _tok("UL045809", "Policy Number")]]
    for values in reference:
        if len(values) != len(display_specs):
            raise ValueError(f"Reference field count {len(values)} != {len(display_specs)}")
        lines.extend(_wrap_record_groups([[_tok(value, spec["name"])] for value, spec in zip(values, display_specs)]))
    while len(lines) < 18:
        lines.append([_sep(" ")])
    lines.extend([
        [_sep(" " * 68), _tok("09/16/26", "Current Date"), _sep(" "), _tok("B7Y02", "Part of the user ID?")],
        [_sep("  CK620 DISPLAY COMPLETE" + " " * 37), _tok("CKPR-ANICO", "Region and Company")],
    ])
    notes = (
        "The common 45-byte area is LH_COV_IVM_FND_CTL for both fixed and variable funds; "
        "fixed funds append 34 bytes from LH_COV_FXD_FND_CTL. Join by policy, company, system, "
        "coverage phase and fund ID. Non-tiered fixed records end at byte 79. "
        "Variable funds omit the fixed area; live rendering is guarded until a capture verifies that variant. "
        "Tiered amount (1T) and duration (1D) methods append the documented count and rate/limit area, "
        "but are guarded until real rows establish count, length and ordering. "
        "NULL slots are dim and annotated, distinct from stored zero or blanks. "
        "Flag A is live; reserved B/U bits are illustrative amber zeros."
    )
    document = {
        "segment": "55", "title": "Individual Fund Control (screen 6255)",
        "source": "UL045809 / 01 / CKPR capture 2026-09-16; D202 pp.63-77/600; COBOLDB2translation.xls",
        "lines": lines, "fields": fields, "field_specs": specs,
        "verification": {
            "live_policies": ["UL045809 / 01 / CKPR", "U0633187 / 01 / CKPR"],
            "verified_on": "2026-09-16", "limitations": notes,
            "archive_corrections": "6255 (not 6275); 8 Flag A bits; High Phase 60-61; key 62-72; initial rate 73-75; end date 76-79; tier count 80-81.",
        },
        "layout_html": (
            f"<p>{html.escape(notes)}</p>"
            '<table border="1" cellspacing="0" cellpadding="3">'
            '<tr bgcolor="#E6A0AA"><th>Byte</th><th>Field / source / applicability</th></tr>'
            + "".join(rows) + "</table>"
        ),
    }
    path = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_55.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "fields": len(fields)}))


if __name__ == "__main__":
    main()
