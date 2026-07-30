"""Build the shipped Segment 59 screen from the extracted workbook layout.

Usage:
    venv\\Scripts\\python.exe tools\\build_seg59_screen.py ^
        C:\\tmp\\seg59\\seg_59.json ^
        suiteview\\polview\\data\\policy_record_screens\\seg_59.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


SEP = {"text": "  ", "field": None}
INDENT = {"text": "            ", "field": None}


def _tok(text: str, field: str) -> dict:
    return {"text": text, "field": field}


def _line(*tokens: tuple[str, str], indent: bool = False) -> list[dict]:
    runs = [dict(INDENT)] if indent else [{"text": "  ", "field": None}]
    for index, (text, field) in enumerate(tokens):
        if index:
            runs.append(dict(SEP))
        runs.append(_tok(text, field))
    runs.append(dict(SEP))
    return runs


def _reference_lines() -> list[list[dict]]:
    lines = [
        [
            {"text": "  ", "field": None},
            _tok("6259,", "Screen Name"),
            dict(SEP),
            _tok("U0633187", "Policy Number"),
            {"text": "   ;    .", "field": None},
        ],
        _line(
            ("59", "Segment Identification"),
            ("0191", "Segment Length"),
            ("00010000", "Flag Byte A"),
            ("00000000", "Flag Byte B"),
            ("00000000", "Flag Byte U"),
            ("1", "Segment Type"),
            ("2", "MEC Indicator"),
            ("0", "Rated Rates Indicator"),
            ("**/**/****", "MEC Date"),
            ("06/10/2012", "7-Pay Period Start Date"),
            ("**/**/****", "7-Pay Next Change Date"),
        ),
        _line(
            ("3513.71", "7-Pay Level Premium"),
            (".00", "7-Pay Window Premiums"),
            (".000", "7-Pay Current Interest Rate"),
            ("0", "7-Pay Guaranteed Period"),
            ("100000.00", "7-Pay Beginning Specified or Face Amount"),
            (".00", "7-Pay Beginning Cash Value"),
            (".00", "Death Benefit as of June 20, 1988"),
            (".00", "Death Benefit as of October 20, 1988"),
            ("2889.00", "7-Pay Premiums Paid [1]"),
            (".00", "7-Pay Withdrawals [1]"),
            ("2782.00", "7-Pay Premiums Paid [2]"),
            (".00", "7-Pay Withdrawals [2]"),
            indent=True,
        ),
        _line(
            ("2782.00", "7-Pay Premiums Paid [3]"),
            (".00", "7-Pay Withdrawals [3]"),
            ("2568.00", "7-Pay Premiums Paid [4]"),
            (".00", "7-Pay Withdrawals [4]"),
            ("1177.00", "7-Pay Premiums Paid [5]"),
            (".00", "7-Pay Withdrawals [5]"),
            (".00", "7-Pay Premiums Paid [6]"),
            (".00", "7-Pay Withdrawals [6]"),
            (".00", "7-Pay Premiums Paid [7]"),
            (".00", "7-Pay Withdrawals [7]"),
            ("0", "1035 Exchange Information"),
            indent=True,
        ),
    ]
    while len(lines) < 18:
        lines.append([{"text": " ", "field": None}])
    lines.extend([
        [
            _tok("CK620 DISPLAY COMPLETE", "Completion Message"),
            {"text": " " * 62, "field": None},
            _tok("07/29/26", "Current Date"),
            dict(SEP),
            _tok("B7Y02", "Part of the user ID?"),
        ],
        [
            {"text": " " * 78, "field": None},
            _tok("CKPR-ANICO", "Region and Company"),
        ],
    ])
    return lines


def main() -> int:
    source = Path(sys.argv[1])
    destination = Path(sys.argv[2])
    document = json.loads(source.read_text(encoding="utf-8"))

    document["source"] = (
        "Policy Record html.xls / Policy Segments seg.doc (U0633187)"
    )
    document["lines"] = _reference_lines()

    fields = document["fields"]
    fields.update({
        "Screen Name": [],
        "Policy Number": [],
        "Completion Message": [],
        "Current Date": [],
        "Part of the user ID?": [],
        "Region and Company": [],
        "Flag Byte A": [
            "COBOL: FTMFLAGA-FLAG-BYTE-A",
            "DB2 bits 0-5: LH_TAMRA_7_PY_PER.GDF_SVPY_TES_IND, "
            "GDF_GDL_PRM_IND, MAT_CHG_IND, SVPY_PRM_CLC_IND, "
            "REVERSE_TO_ISS_IND, OVR_MEC_IND",
        ],
        "Flag Byte B": [
            "COBOL: FTMFLAGB-FLAG-BYTE-B",
            "DB2: none",
        ],
        "Flag Byte U": [
            "COBOL: FTMFLAGU-FLAG-BYTE-U",
            "DB2: none",
        ],
        "Segment Type": [
            "COBOL: FTMSGTYP-TAMRA-SEG-TYPE",
            "Derived: LH_TAMRA_7_PY_PER row = Type 1",
        ],
        "1035 Exchange Information": [
            "COBOL: FTM1035I-1035-EXCH-INFO",
            "DB2: LH_TAMRA_7_PY_PER.XCG_1035_PMT_QTY",
        ],
        "Number of Variable Entries": [
            "COBOL: FTMVRENT-VARIABLE-ENTRIES",
            "Derived: count of LH_TAMRA_MEC_PRM variable-phase rows",
        ],
    })

    for spec in document["field_specs"]:
        if spec.get("name") == "1035 Exchange Information":
            spec["db2"] = "LH_TAMRA_7_PY_PER.XCG_1035_PMT_QTY"
        elif spec.get("name") == "Number of Variable Entries":
            spec["db2"] = None

    layout_html = document["layout_html"].replace(
        "LH_TAMRA_7_PY_YR.XCG_1035_PMT_QTY",
        "LH_TAMRA_7_PY_PER.XCG_1035_PMT_QTY",
    ).replace(
        "DB2: LH_TAMRA_7_PY_YR.SVPY_YR_SEQ_NBR",
        "Derived: count of LH_TAMRA_MEC_PRM variable-phase rows",
    )
    document["layout_html"] = layout_html

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
