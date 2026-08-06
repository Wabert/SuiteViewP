"""Build the shipped Segment 53 screen from the extracted HTML definition.

Usage:
    venv\\Scripts\\python.exe tools\\build_seg53_screen.py ^
        C:\\tmp\\seg53\\seg_53.json ^
        suiteview\\polview\\data\\policy_record_screens\\seg_53.json
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
            _tok("6253,", "Screen Name"),
            dict(SEP),
            _tok("UE142109", "Policy Number"),
            dict(SEP),
        ],
        _line(
            ("53", "Segment Identification"),
            ("0089", "Segment Length"),
            ("B", "Automatic Transaction Type"),
            ("1", "Automatic Transaction Sequence"),
            ("00000000", "Flag Byte A"),
            ("00000000", "Flag Byte B"),
            ("00000000", "Flag Byte C"),
            ("00000000", "Flag Byte D"),
            ("00000000", "Flag Byte E"),
            ("00000000", "Flag Byte U"),
            ("08/2021", "Start Date"),
        ),
        _line(
            ("00/1900", "Suspend Date"),
            ("00/1900", "Restart Date"),
            ("07/06/2113", "Cease Date"),
            ("07/2026", "Last Activity Date"),
            ("08/2026", "Next Scheduled Activity Date"),
            ("1", "Activity Day"),
            ("08/01/2021", "Previous Maintenance Date"),
            ("SWEEP   ", "Transaction Origin"),
            ("1", "Status Code"),
            indent=True,
        ),
        _line(
            ("     ", "Event Code"),
            ("  ", "Error Condition"),
            ("1", "Frequency"),
            ("1", "Charge Override"),
            (".00", "Charge Amount"),
            ("199.80", "Sweep Fund Minimum Balance"),
            ("M", "Sweep Frequency"),
            ("1", "Sweep Day"),
            ("0", "Sweep Month"),
            indent=True,
        ),
    ]
    while len(lines) < 18:
        lines.append([{"text": " ", "field": None}])
    lines.extend([
        [
            {"text": " " * 68, "field": None},
            _tok("07/30/26", "Current Date"),
            dict(SEP),
            _tok("B7Y02", "Part of the user ID?"),
        ],
        [
            {"text": "  CK620 DISPLAY COMPLETE".ljust(60), "field": None},
            _tok("CKPR-ANICO", "Region and Company"),
            dict(SEP),
        ],
        [{"text": " ", "field": None}],
    ])
    return lines


def main() -> int:
    source = Path(sys.argv[1])
    destination = Path(sys.argv[2])
    document = json.loads(source.read_text(encoding="utf-8"))

    document["title"] = "Segment 53 - Automatic Transaction Control"
    document["source"] = (
        "Sample 6253 screen.htm / attached UE142109 CyberLife capture"
    )
    document["lines"] = _reference_lines()

    fields = document["fields"]
    fields.pop("Fequency", None)
    fields.pop("Charge Overrider", None)
    fields.pop("Event Condition", None)
    fields.update({
        "Screen Name": [],
        "Policy Number": [],
        "Completion Message": [],
        "Current Date": [],
        "Part of the user ID?": [],
        "Region and Company": [],
        "Automatic Transaction Type": [
            "COBOL: FAUATTYP-AUTO-TRANS-TYPE",
            "DB2: LH_ATM_TRS_SCH.ATM_TRS_TYP_CD",
        ],
        "Automatic Transaction Sequence": [
            "COBOL: FAUATSQ-AUTO-TRANS-SEQ",
            "DB2: LH_ATM_TRS_SCH.ATM_TRS_SEQ_NBR",
        ],
        "Flag Byte A": [
            "COBOL: FAUATFBA-FLAG-BYTE-A",
            "DB2 exposes selected bits only: "
            "LH_ATM_TRS_SCH.DFL_STR_DT_ISS_IND",
        ],
        "Flag Byte B": [
            "COBOL: FAUATFBB-FLAG-BYTE-B",
            "DB2: none",
        ],
        "Flag Byte C": [
            "COBOL: FAUATFBC-FLAG-BYTE-C",
            "DB2: none",
        ],
        "Flag Byte D": [
            "COBOL: FAUATFBD-FLAG-BYTE-D",
            "DB2: none",
        ],
        "Flag Byte E": [
            "COBOL: FAUATFBE-FLAG-BYTE-E",
            "DB2: none",
        ],
        "Flag Byte U": [
            "COBOL: FAUATFBU-FLAG-BYTE-U",
            "DB2: none",
        ],
        "Previous Maintenance Date": [
            "COBOL: FAUATPMD-PREV-MAINT-DATE",
            "DB2: LH_ATM_TRS_SCH.ATM_TRS_PRE_MNT_DT",
        ],
        "Transaction Origin": [
            "COBOL: FAUATORG-ORIGIN",
            "DB2: LH_ATM_TRS_SCH.DPT_DESK_CD",
        ],
        "Status Code": [
            "COBOL: FAUATSTC-AT-STATUS-CODE",
            "DB2: LH_ATM_TRS_SCH.ATM_TRS_STA_CD",
        ],
        "Event Code": [
            "COBOL: FAUATSEV-SCRIBE-EVENT-CODE",
            "DB2: LH_ATM_TRS_SCH.COS_EVT_CD",
        ],
        "Error Condition": [
            "COBOL: FAUATSER-SCRIBE-ERROR-COND",
            "DB2: LH_ATM_TRS_SCH.COS_ERR_CD",
        ],
        "Frequency": [
            "COBOL: FAUATFRQ-FREQUENCY",
            "DB2: LH_ATM_TRS_SCH.ATM_TRS_FQY_PER",
        ],
        "Charge Override": [
            "COBOL: FAUATCGO-AT-CHG-OVERRIDE",
            "DB2: none",
        ],
        "Sweep Fund Minimum Balance": [
            "COBOL: FAUSWMNB-SWEEP-MIN-BALANCE",
            "DB2: LH_SWF_SCH.SWEEP_MIN_BALANCE",
        ],
        "Sweep Frequency": [
            "COBOL: FAUSWFRQ-SWEEP-FREQUENCY",
            "DB2: LH_SWF_SCH.SWEEP_FREQUENCY",
        ],
        "Sweep Day": [
            "COBOL: FAUSWDAY-SWEEP-DAY",
            "DB2: LH_SWF_SCH.SWEEP_DAY",
        ],
        "Sweep Month": [
            "COBOL: FUASWMTH-SWEEP-MONTH",
            "DB2: LH_SWF_SCH.SWEEP_MONTH",
        ],
    })

    spec_updates = {
        "Automatic Transaction Type": (
            "LH_ATM_TRS_SCH.ATM_TRS_TYP_CD",
            "FAUATTYP-AUTO-TRANS-TYPE",
        ),
        "Automatic Transaction Sequence": (
            "LH_ATM_TRS_SCH.ATM_TRS_SEQ_NBR",
            "FAUATSQ-AUTO-TRANS-SEQ",
        ),
        "Previous Maintenance Date": (
            "LH_ATM_TRS_SCH.ATM_TRS_PRE_MNT_DT",
            "FAUATPMD-PREV-MAINT-DATE",
        ),
        "Transaction Origin": (
            "LH_ATM_TRS_SCH.DPT_DESK_CD",
            "FAUATORG-ORIGIN",
        ),
        "Status Code": (
            "LH_ATM_TRS_SCH.ATM_TRS_STA_CD",
            "FAUATSTC-AT-STATUS-CODE",
        ),
        "Event Code": (
            "LH_ATM_TRS_SCH.COS_EVT_CD",
            "FAUATSEV-SCRIBE-EVENT-CODE",
        ),
        "Error Condition": (
            "LH_ATM_TRS_SCH.COS_ERR_CD",
            "FAUATSER-SCRIBE-ERROR-COND",
        ),
        "Fequency": (
            "LH_ATM_TRS_SCH.ATM_TRS_FQY_PER",
            "FAUATFRQ-FREQUENCY",
        ),
        "Charge Overrider": (None, "FAUATCGO-AT-CHG-OVERRIDE"),
        "Sweep Fund Minimum Balance": (
            "LH_SWF_SCH.SWEEP_MIN_BALANCE",
            "FAUSWMNB-SWEEP-MIN-BALANCE",
        ),
        "Sweep Frequency": (
            "LH_SWF_SCH.SWEEP_FREQUENCY",
            "FAUSWFRQ-SWEEP-FREQUENCY",
        ),
        "Sweep Day": (
            "LH_SWF_SCH.SWEEP_DAY",
            "FAUSWDAY-SWEEP-DAY",
        ),
        "Sweep Month": (
            "LH_SWF_SCH.SWEEP_MONTH",
            "FUASWMTH-SWEEP-MONTH",
        ),
    }
    for spec in document["field_specs"]:
        name = spec.get("name")
        if name not in spec_updates:
            continue
        db2, cobol = spec_updates[name]
        if name == "Fequency":
            spec["name"] = "Frequency"
        elif name == "Charge Overrider":
            spec["name"] = "Charge Override"
        spec["db2"] = db2
        spec["cobol"] = cobol

    replacements = {
        "Fequency": "Frequency",
        "Charge Overrider": "Charge Override",
        "FAUTXNTP-AUTO-TRANS-TYPE": "FAUATTYP-AUTO-TRANS-TYPE",
        "FAUATSEQ AUTO-TRANS-SEQ": "FAUATSQ-AUTO-TRANS-SEQ",
        "FAUPRFDT-PREV-REFRESH-DATE": "FAUATPMD-PREV-MAINT-DATE",
        "FAUORIGN-ORIGIN": "FAUATORG-ORIGIN",
        "FAUSTSCD-AWD-STATUS-CODE": "FAUATSTC-AT-STATUS-CODE",
        "FAUCYEVT-SCRIBE-EVENT-CODE": "FAUATSEV-SCRIBE-EVENT-CODE",
        "FAUCYERR-SCRIBE-ERROR-COND": "FAUATSER-SCRIBE-ERROR-COND",
        "COBOL: FAUSWMNB-SWEEP-MIN-BALANCE</br>"
        "&#160;&#160;&#160;&#160;DB2: ": (
            "COBOL: FAUSWMNB-SWEEP-MIN-BALANCE</br>"
            "&#160;&#160;&#160;&#160;DB2: LH_SWF_SCH.SWEEP_MIN_BALANCE"
        ),
        "COBOL: FAUSWFRQ-SWEEP-FREQUENCY</br>"
        "&#160;&#160;&#160;&#160;DB2: ": (
            "COBOL: FAUSWFRQ-SWEEP-FREQUENCY</br>"
            "&#160;&#160;&#160;&#160;DB2: LH_SWF_SCH.SWEEP_FREQUENCY"
        ),
        "COBOL: FAUSWDAY-SWEEP-DAY</br>"
        "&#160;&#160;&#160;&#160;DB2: ": (
            "COBOL: FAUSWDAY-SWEEP-DAY</br>"
            "&#160;&#160;&#160;&#160;DB2: LH_SWF_SCH.SWEEP_DAY"
        ),
        "COBOL: FUASWMTH-SWEEP-MONTH</br>"
        "&#160;&#160;&#160;&#160;DB2: ": (
            "COBOL: FUASWMTH-SWEEP-MONTH</br>"
            "&#160;&#160;&#160;&#160;DB2: LH_SWF_SCH.SWEEP_MONTH"
        ),
    }
    layout_html = document["layout_html"]
    for old, new in replacements.items():
        layout_html = layout_html.replace(old, new)
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
