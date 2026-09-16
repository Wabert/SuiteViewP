"""Build Segment 60 metadata from the HTML, corrected to CyberDoc 1201."""

from __future__ import annotations

import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.policyrecord.extract_policy_record_screen import (
    _classify, _parse_layout, _repair_layout_html, _split_tables,
)


def main() -> int:
    source = ROOT / "docs" / "Policy Record" / "Sample 6260 screen.htm"
    layout = next(
        _repair_layout_html(table) for table in _split_tables(source.read_text(encoding="utf-8"))
        if _classify(table) == "layout"
    )
    fields, specs = _parse_layout(layout)
    specs = [spec for spec in specs if spec["name"] not in (
        "RESERVED", "Used Accumulators", "Additional Payments by Month",
    )]
    specs.extend([
        {
            "name": "LTC Cost of Insurance Since Issue", "byte": "112-117",
            "cobol": "FUMLTCOI-TOTAL-LTC-COST-OF-INS",
            "db2": "LH_POL_TOTALS.TOT_LTC_CST_OF_INS",
        },
        {
            "name": "CyberLife Reserved", "byte": "118-129",
            "cobol": "FUMCLRSV-CL-RESERVED", "db2": None, "kind": "reserved",
        },
        {
            "name": "User Reserved", "byte": "130-138",
            "cobol": "FUMRESRV-RESERVED", "db2": None, "kind": "reserved",
        },
        {
            "name": "Used Accumulators", "byte": "139",
            "cobol": "FUMACCUM-USED-ACCUMS",
            "db2": "LH_POL_TOTALS.MO_ADD_PMT_QTY", "kind": "integer",
        },
        {
            "name": "Additional Payments by Month", "byte": "140-211",
            "cobol": "FUMADPAY-PAYMENTS-BY-MONTH",
            "db2": "LH_MO_ADD_PMT.MO_ADD_PRM_AMT", "kind": "monthly",
        },
    ])
    integer_fields = {"Total Number of Additional Payments", "Total Number of Withdrawals"}
    for spec in specs:
        name = spec["name"]
        if name in ("Flag Byte A", "User Flag Byte"):
            spec["kind"] = "flag"
            spec["cobol"] = (
                "FUMFLAGA-FLAG-BYTE-A" if name == "Flag Byte A" else "FUMFLAGU-FLAG-BYTE-U"
            )
        elif name in ("Segment Identification", "Segment Length"):
            spec["kind"] = "header"
            spec["cobol"] = (
                "FUMIDENT-SEGMENT-IDENT" if name == "Segment Identification"
                else "FUMLNGTH-SEGMENT-LENGTH"
            )
        elif name in integer_fields:
            spec["kind"] = "integer"
        elif "Date" in name:
            spec["kind"] = "date"
        else:
            spec.setdefault("kind", "amount")
        fields[name] = [
            f"{label}: {spec[key]}" for key, label in (("cobol", "COBOL"), ("db2", "DB2"))
            if spec.get(key)
        ]
        if spec["kind"] == "flag":
            fields[name].append("Reserved byte; no complete DB2 mapping. Displayed as an example.")
    fields.pop("RESERVED", None)
    fields["LTC Cost of Insurance Since Issue"].append(
        "CyberDoc D202 printed p.125; column verified live on UL045809."
    )
    fields["Used Accumulators"].append(
        "Zero/no monthly rows verified on UL045809. Nonzero monthly-array layout requires verification."
    )
    for name in ("Screen Name", "Policy Number", "Current Date", "Part of the user ID?", "Region and Company"):
        fields[name] = []
    rows = []
    for spec in specs:
        mappings = "<br>".join(html.escape(value) for value in fields[spec["name"]])
        rows.append(
            f'<tr><td>{spec["byte"]}</td><td><b>{html.escape(spec["name"])}</b><br>{mappings}</td></tr>'
        )
    reference_values = [
        "60", "0139", "00000000", "00000000", "46726.00", "1365.25", "3",
        "4458.28", "2316.00", ".00", ".00", ".00", "13987.30", ".00", "3",
        "34103.95", ".00", ".00", "**/**/****", "**/**/****", ".00", ".00",
        ".00", ".00", ".00", "0",
    ]
    display_specs = [s for s in specs if s["kind"] not in ("reserved", "monthly")]
    if len(display_specs) != len(reference_values):
        raise ValueError("Reference values and Segment 60 fields are misaligned")
    tokens = [
        {"text": value, "field": spec["name"]}
        for value, spec in zip(reference_values, display_specs)
    ]
    lines = [[{"text": "  6260, ", "field": None}, {"text": "UL045809", "field": "Policy Number"}]]
    for start, end in ((0, 12), (12, 24), (24, 26)):
        line = [{"text": "  " if start == 0 else " " * 10, "field": None}]
        for token in tokens[start:end]:
            if len(line) > 1:
                line.append({"text": " ", "field": None})
            line.append(token)
        lines.append(line)
    while len(lines) < 18:
        lines.append([{"text": " ", "field": None}])
    lines.extend([
        [
            {"text": " " * 68, "field": None},
            {"text": "09/15/26", "field": "Current Date"},
            {"text": "  ", "field": None},
            {"text": "B7Y02", "field": "Part of the user ID?"},
        ],
        [
            {"text": "  CK620 DISPLAY COMPLETE" + " " * 37, "field": None},
            {"text": "CKPR-ANICO", "field": "Region and Company"},
        ],
    ])
    document = {
        "segment": "60", "title": "Payment Accumulation (screen 6260)",
        "source": "UL045809 CyberLife capture 2026-09-15; CyberDoc D202 pp.120-126, 606",
        "lines": lines, "fields": fields, "field_specs": specs,
        "layout_html": (
            '<table border="1" cellspacing="0" cellpadding="3">'
            '<tr bgcolor="#E6A0AA"><th>Byte</th><th>Field / source</th></tr>'
            + "".join(rows) + "</table>"
        ),
    }
    destination = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_60.json"
    destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(destination), "fields": len(fields)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
