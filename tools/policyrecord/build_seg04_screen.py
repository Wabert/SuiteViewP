"""Generate Benefits hover and record-layout metadata from the verified mapping."""

import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.polview.models.policy_record_benefits import (
    DENY_FIELD, EXTENSION_TABLE, FIELDS, FLAGS, FREQUENCY_FIELD, PPA_FIELD, TABLE,
)


def build_document():
    specs = [
        {"name": "Segment Identification", "byte": "1-2",
         "cobol": "FSBIDENT-SEGMENT-IDENT", "kind": "header"},
        {"name": "Segment Length", "byte": "3-4",
         "cobol": "FSBLNGTH-SEGMENT-LENGTH", "kind": "header"},
    ]
    for index, (name, bits) in enumerate(FLAGS.items()):
        specs.append({
            "name": name, "byte": str(5 + index), "kind": "flag",
            "cobol": f"FSBFLAG{'AB'[index]}-FLAG-BYTE-{'AB'[index]}",
            "bits": [
                {"bit": bit, "db2": f"{TABLE}.{column}", "meaning": meaning}
                for bit, (column, meaning) in enumerate(bits)
            ],
        })
    for table, definitions in (
        (TABLE, (*FIELDS, PPA_FIELD)), (EXTENSION_TABLE, (DENY_FIELD, FREQUENCY_FIELD)),
    ):
        specs.extend(
            {"name": name, "db2": f"{table}.{column}", "cobol": cobol,
             "byte": byte, "kind": kind, "width": width, "decimals": decimals}
            for name, column, cobol, byte, kind, width, decimals in definitions
        )
    fields = {}
    for spec in specs:
        details = [f"Byte: {spec['byte']}", f"COBOL: {spec['cobol']}"]
        if spec.get("db2"):
            details.append(f"DB2: {spec['db2']}")
        details.extend(f"Bit {bit['bit']}: {bit['db2']} - {bit['meaning']}"
                       for bit in spec.get("bits", []))
        if spec["kind"] == "number":
            details.append(f"Format: {spec['width']} packed digits, {spec['decimals']} decimals.")
        elif spec["kind"] == "text":
            details.append(f"Format: {spec['width']} character(s); retain stored blanks.")
        elif spec["kind"] == "date":
            details.append("Format: MM/DD/YYYY; sentinel dates display **/**/****.")
        fields[spec["name"]] = details
    fields["Segment Length"].append("81 bytes; D20 byte diagram p.374 includes reserved byte 75 and user bytes 76-81.")
    fields["Use Code"].append(
        "0 = ceased; 1 = active; 2/3 = special waiver/payor cases. "
        "For type U (COLA), DB2: LH_SPM_BNF.COL_ICE_FQY_CD supplies the increase frequency instead."
    )
    fields["Renewable Rate Indicator"].append("DB2 0 = X (not renewable); 1 = blank (renewable).")
    fields[PPA_FIELD[0]].append(
        "Type A (PPA) only; 4.50 in DB2 displays 4.500. Bytes 70-74 are shared "
        "with OPT_DT / IFT_PCT / CPI_ADJ_REJ_NBR variants, not additional fields."
    )
    fields[FREQUENCY_FIELD[0]].append(
        "Blank in verified captures and not printed. Nonblank frequency is guarded pending a matching capture."
    )
    fields[DENY_FIELD[0]].append(
        "Live value and display position verified; archived layouts disagree on bytes 76/77. "
        "Do not infer the physical byte position from a capture with blank frequency."
    )
    for name in ("Screen Name", "Policy Number", "Current Date", "Part of the user ID?", "Region and Company"):
        fields[name] = []
    notes = (
        "References: CyberDoc 1201 D20 pp.159-175 and byte diagram p.374; "
        "COBOLDB2translation.xls Translation; Policy Record html.xls sheets 04 / 04 - Supp Benefit. "
        "Verified read-only against U0566833 / 01 / CKPR and its September 17, 2026 capture. "
        "Join LH_SPM_BNF to TH_SPM_BNF by policy/company/system, phase, benefit type/subtype, "
        "person/sequence, status and issue date. Preserve source order within each phase. "
        "All 16 flag bits are live. NULL slots are dim and annotated, never stored zeros. "
        "Option/inflation/CPI variants, all-coverage requests, nonblank benefit frequency and "
        "ABR qualification user bytes require additional screen verification and report explicit errors. "
        "Missing TH rows show an unavailable rate-deny slot, never an assumed N. "
        "Reserved byte 75 and unknown user bytes 78-81 are not invented or displayed."
    )
    rows = [
        f"<tr><td>{html.escape(spec['byte'])}</td><td><b>{html.escape(spec['name'])}</b><br>"
        + "<br>".join(html.escape(detail) for detail in fields[spec["name"]])
        + "</td></tr>"
        for spec in specs
    ]
    return {
        "segment": "04", "title": "Benefits (screen 6204)",
        "source": "D20 pp.159-175/374; COBOLDB2translation.xls; U0566833 capture 2026-09-17",
        "lines": [], "fields": fields, "field_specs": specs,
        "layout_html": (
            f"<p>{html.escape(notes)}</p>"
            '<table border="1" cellspacing="0" cellpadding="3">'
            '<tr bgcolor="#E6A0AA"><th>Byte</th><th>Field / source / applicability</th></tr>'
            + "".join(rows) + "</table>"
        ),
    }


def main():
    path = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_04.json"
    document = build_document()
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "fields": len(document["fields"])}))


if __name__ == "__main__":
    main()
