"""Enrich the two extracted annual screens with verified format/flag metadata."""

import html
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from suiteview.polview.models.policy_record_annual_totals import FIELDS_63, FIELDS_64, FLAG_COLUMNS, TABLES


def main():
    results = []
    for segment, fields in (("63", FIELDS_63), ("64", FIELDS_64)):
        path = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / f"seg_{segment}.json"
        screen = json.loads(path.read_text(encoding="utf-8"))
        lookup = {spec[0]: spec for spec in fields}
        prefix = "FUY" if segment == "63" else "FCY"
        offset = 7 if segment == "63" else 9
        for spec in screen["field_specs"]:
            name = spec["name"]
            if name in lookup:
                _, column, cobol, digits, decimals = lookup[name]
                spec.update(db2=f"{TABLES[segment]}.{column}", cobol=cobol,
                            kind="date" if decimals is None else ("integer" if decimals == 0 else "decimal"),
                            digits=digits, decimals=decimals)
                size = 4 if decimals is None else (
                    1 if column == "POL_YR_DUR" else (digits + 2) // 2
                )
                byte = str(offset) if size == 1 else f"{offset}-{offset + size - 1}"
                if byte != spec["byte"]:
                    screen["layout_html"] = screen["layout_html"].replace(spec["byte"], byte)
                spec["byte"] = byte
                offset += size
                screen["fields"][name] = [
                    f"COBOL: {cobol}", f"DB2: {spec['db2']}",
                    "Format: MM/DD/YYYY" if decimals is None else f"Format: {digits} digits, {decimals} decimal places",
                ]
            elif name == "Flag Byte A":
                spec.update(cobol=f"{prefix}FLAGA-FLAG-BYTE-A", kind="flag",
                            bits=[{"bit": index, "db2": f"{TABLES[segment]}.{column}"}
                                  for index, column in enumerate(FLAG_COLUMNS[segment])])
                screen["fields"][name] = [
                    f"COBOL: {spec['cobol']}",
                    *[f"Bit {bit['bit']}: {bit['db2']}" for bit in spec["bits"]],
                    "Remaining bits are reserved: illustrative amber zeros, not verified live data.",
                ]
            elif "Flag" in name:
                suffix = name[-1] if name[-1] in ("B", "C") else "U"
                spec.update(cobol=f"{prefix}FLAG{suffix}-FLAG-BYTE-{suffix}", kind="flag")
                screen["fields"][name] = [
                    f"COBOL: {spec['cobol']}",
                    "No DB2 source; all eight bits are illustrative amber zeros.",
                ]
            else:
                spec["kind"] = "header"
        screen["verification"] = {
            "references": ["COBOLDB2translation.xls", "D202.pdf printed pages 129-138, 608-609"],
            "live_policy": "UL045809 / 01 / CKPR",
            "verified_on": "2026-09-15",
            "null_slots": "Source NULL uses the captured numeric slot format, dimmed and explicitly annotated; it is not a stored zero.",
            "wrapping": "79 usable cells after the shared two-space inset; continuation inset 10.",
            "archive_corrections": (
                "Carry-forward percent occupies bytes 106-108, not the sample HTML's 106-111."
                if segment == "63" else
                "The final two six-byte amounts occupy 63-68 and 69-74, not the sample HTML's five-byte ranges."
            ),
        }
        for name in (
            "Screen Name", "Policy Number", "Current Date",
            "Part of the user ID?", "Region and Company",
        ):
            screen["fields"].setdefault(name, [])
        for spec in screen["field_specs"]:
            if spec["name"] not in lookup:
                continue
            label = f"<b>{html.escape(spec['name'])}</b>"
            def update_layout_row(match):
                row = match.group(0)
                if label not in row:
                    return row
                row = re.sub(r"DB2:\s*[^<]+", f"DB2: {spec['db2']}", row)
                return re.sub(r"COBOL:\s*[^<]+", f"COBOL: {spec['cobol']}", row)
            screen["layout_html"] = re.sub(
                r"<tr>.*?</tr>", update_layout_row, screen["layout_html"], flags=re.S,
            )
        assert offset - 1 == (108 if segment == "63" else 74)
        path.write_text(json.dumps(screen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        results.append({"segment": segment, "fields": len(screen["fields"])})
    print(json.dumps(results))


if __name__ == "__main__":
    main()
