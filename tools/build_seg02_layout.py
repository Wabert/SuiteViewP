"""Build the Segment 02 (Coverage) field_specs mapping from authoritative sources.

Segment 02 repeats once per coverage phase (a row of ``LH_COV_PHA``).  To render
it live we need, in on-screen (byte) order, each field's DB2 source and display
format.  This tool assembles that mapping from three authorities and prints a
review so a human/agent can eyeball every field before it ships:

  1. ``seg_02.json`` -- the captured-reference screen.  Its ``lines`` give the
     authoritative on-screen *token order* (the "spine"); its ``layout_html``
     Record-Layout table gives, per byte range, the primary Field label + COBOL
     name + a (sometimes wrong / flagged) DB2 column.
  2. ``COBOLDB2translation.xls`` (Translation sheet) -- the authoritative
     COBOL-name -> DB2-column map.  Where the layout's DB2 disagrees with this,
     we trust this and flag it.
  3. ``cyberdoc_field_formats.json`` -- COBOL-name -> display ``kind``
     (``decimal:N`` / ``date`` / ``packed_num`` / ``int`` / code) from the
     official CyberLife documentation.

Alignment: the screen spine and the layout's primary rows are both in byte
order, so we zip them positionally.  Chrome rows (segment id/length, flag bytes)
carry no COBOL/DB2 and are emitted as chrome/example.

Output: writes ``field_specs`` JSON to ``out`` (default C:/tmp/seg02/seg_02_layout.json)
and prints an aligned review table + a DISCREPANCIES section to stdout.

Usage:
    venv\\Scripts\\python.exe tools/build_seg02_layout.py '{"out": "C:/tmp/seg02/seg_02_layout.json"}'
"""
from __future__ import annotations

import json
import os
import re
import sys
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SEG_JSON = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "seg_02.json"
CYBERDOC = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens" / "cyberdoc_field_formats.json"
XLS = ROOT / "docs" / "COBOLDB2translation.xls"

_TR = re.compile(r"<tr>(.*?)</tr>", re.S)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_COBOL = re.compile(r"COBOL:\s*([A-Za-z0-9\-]+)")
_DB2 = re.compile(r"DB2:\s*([A-Za-z0-9_]+\.[A-Za-z0-9_]+)")


def _cell_text(html: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", html)
    return unescape(txt).replace("\xa0", " ").strip()


def _label(cell_html: str) -> str:
    """The bold field label (text before COBOL:), cleaned."""
    txt = _cell_text(cell_html)
    txt = re.split(r"COBOL:", txt, 1)[0]
    return re.sub(r"\s+", " ", txt).strip()


def _parse_layout(html: str):
    """Return byte-ordered primary field rows: {byte, label, cobol, db2_layout, note}."""
    rows = []
    for tr in _TR.findall(html):
        tds = _TD.findall(tr)
        if len(tds) < 2:
            continue
        byte = _cell_text(tds[1])
        if byte.lower() == "byte":  # header row
            continue
        field_html = tds[2] if len(tds) > 2 else ""
        field_txt = _cell_text(field_html)
        cobol_m = _COBOL.search(field_txt)
        db2_m = _DB2.search(field_txt)
        note = ""
        if "???" in field_txt or "verify" in field_txt.lower():
            note = "layout flagged uncertain"
        rows.append({
            "byte": byte,
            "label": _label(field_html),
            "cobol": cobol_m.group(1) if cobol_m else None,
            "db2_layout": db2_m.group(1) if db2_m else None,
            "note": note,
        })
    return rows


def _spine(doc):
    """On-screen value-token field names for coverage block 1, in order."""
    lines = doc.get("lines", [])
    fields = []
    seen_seg_id = 0
    started = False
    for line in lines:
        for run in line:
            f = run.get("field")
            if not f:
                continue
            if f == "Segment Identification":
                seen_seg_id += 1
                if seen_seg_id == 1:
                    started = True
                elif seen_seg_id == 2:
                    return fields  # start of block 2
            if started:
                fields.append(f)
    return fields


def _translation_map():
    """COBOL-name -> DB2 column, from the Translation sheet (SEG 02 rows)."""
    import xlrd
    wb = xlrd.open_workbook(str(XLS))
    sheet = wb.sheet_by_name("Translation")
    headers = [str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols)]
    ci = {h: i for i, h in enumerate(headers)}
    out = {}
    for r in range(1, sheet.nrows):
        def cell(name):
            i = ci.get(name)
            return str(sheet.cell_value(r, i)).strip() if i is not None else ""
        cobol = cell("COBOL Name")
        table = cell("Table")
        field = cell("Field Name")
        if cobol and table and field:
            out.setdefault(cobol.upper(), f"{table}.{field}")
    return out


def _cyberdoc_kinds():
    with open(CYBERDOC, "r", encoding="utf-8") as fh:
        idx = json.load(fh)
    return {k.upper(): (v or {}).get("kind") for k, v in idx.items()}


def main():
    cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].strip().startswith("{") else {}
    out_path = Path(cfg.get("out", r"C:/tmp/seg02/seg_02_layout.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(SEG_JSON, "r", encoding="utf-8") as fh:
        doc = json.load(fh)

    spine = _spine(doc)
    layout = _parse_layout(doc["layout_html"])
    trans = _translation_map()
    kinds = _cyberdoc_kinds()

    print(f"spine fields: {len(spine)} | layout rows: {len(layout)}")
    print()

    specs = []
    discrepancies = []
    n = max(len(spine), len(layout))
    for i in range(n):
        name = spine[i] if i < len(spine) else None
        lay = layout[i] if i < len(layout) else {}
        cobol = lay.get("cobol")
        db2_layout = lay.get("db2_layout")
        db2_trans = trans.get((cobol or "").upper()) if cobol else None
        # Prefer the Translation-sheet DB2 when it exists; else the layout's.
        db2 = db2_trans or db2_layout
        kind = kinds.get((cobol or "").upper()) if cobol else None
        specs.append({
            "name": name,
            "byte": lay.get("byte"),
            "layout_label": lay.get("label"),
            "cobol": cobol,
            "db2": db2,
            "db2_layout": db2_layout,
            "db2_translation": db2_trans,
            "kind": kind,
            "note": lay.get("note", ""),
        })
        flag = ""
        if db2_layout and db2_trans and db2_layout.upper() != db2_trans.upper():
            flag = "DB2 MISMATCH"
            discrepancies.append((i, name, cobol, db2_layout, db2_trans))
        elif cobol and not db2_trans:
            flag = "no translation row"
        print("%3d | %-52s | byte %-7s | %-30s | lay=%-30s trn=%-30s kind=%-10s %s" % (
            i, (name or "<none>")[:52], lay.get("byte"), (cobol or "")[:30],
            (db2_layout or "")[:30], (db2_trans or "")[:30], kind or "", flag))

    print("\n===== DISCREPANCIES (layout DB2 != translation DB2) =====")
    for i, name, cobol, dl, dt in discrepancies:
        print(f"  [{i}] {name} ({cobol}): layout={dl}  translation={dt}")

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"segment": "02", "field_specs": specs}, fh, indent=2)
    print(f"\nwrote {out_path} ({len(specs)} specs)")


if __name__ == "__main__":
    main()
