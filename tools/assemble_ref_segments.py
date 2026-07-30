"""Assemble bundled ``seg_<n>.json`` policy-record *reference* screens from the
already-extracted source material, writing them into the app's data directory.

These are **captured reference** screens (real CyberLife screen data, labeled as
sample, not this-policy live data).  Every terminal value keeps its field-name
hover; where a trustworthy COBOL/DB2 mapping is available from the same source it
is added to the hover, and the authoritative byte/COBOL/DB2 record-layout table is
shown below the screen.

Segment 02 (Coverage): archive terminal (authored field-name tooltips) + the
master build-sheet record-layout HTML (byte/COBOL/DB2).  Green-screen tooltips are
kept name-only on purpose -- the master coverage sheet contains a documented
copy/paste mapping slip (e.g. "Agent Phase Code" -> NXT_CHG_DT), and the full,
byte-anchored mapping is presented in the record-layout table instead.

Segment 67 (Renewal Rates): the clean ``Sample 6267`` extraction, whose terminal
tooltips and ``field_specs`` come from one authored source, so COBOL/DB2 is safely
attached to each hovered value.

Usage:
    python tools/assemble_ref_segments.py "{\"segments\": [\"02\", \"67\"]}"
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "suiteview" / "polview" / "data" / "policy_record_screens"
TMP = Path("C:/tmp/segjson")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _mapping_strings(spec: dict) -> list:
    out = []
    cobol = (spec.get("cobol") or "").strip()
    if cobol:
        out.append(f"COBOL: {cobol}")
    db2 = (spec.get("db2") or "").strip()
    if db2:
        for part in db2.split(";"):
            part = part.strip()
            if part:
                out.append(f"DB2: {part}")
    return out


def _token_field_names(lines: list) -> list:
    names = []
    seen = set()
    for line in lines:
        for run in line:
            f = run.get("field")
            if f and f not in seen:
                seen.add(f)
                names.append(f)
    return names


def _fields_from_specs(token_names: list, specs: list) -> dict:
    """Map each terminal token field-name to COBOL/DB2 strings, matching the
    authored ``field_specs`` by exact-normalized name only (no fuzzy guessing)."""
    by_norm = {}
    for sp in specs:
        n = _norm(sp.get("name"))
        if n and n not in by_norm:
            by_norm[n] = sp
    fields = {}
    for name in token_names:
        sp = by_norm.get(_norm(name))
        fields[name] = _mapping_strings(sp) if sp else []
    return fields


def build_67() -> dict:
    src = json.loads((TMP / "seg_67.json").read_text(encoding="utf-8"))
    lines = src["lines"]
    fields = _fields_from_specs(_token_field_names(lines), src.get("field_specs", []))
    return {
        "segment": "67",
        "title": "Renewal Rates (screen 6267)",
        "source": "Sample 6267 screen.htm (captured reference)",
        "lines": lines,
        "fields": fields,
        "layout_html": src.get("layout_html", ""),
    }


def build_02() -> dict:
    arch = json.loads((TMP / "seg_02.json").read_text(encoding="utf-8"))
    master = json.loads((TMP / "seg_02_layout.json").read_text(encoding="utf-8"))
    lines = arch["lines"]
    # Name-only hovers on the green screen; the authoritative byte/COBOL/DB2 map
    # lives in the record-layout table (master build sheet) shown below.
    fields = {name: [] for name in _token_field_names(lines)}
    return {
        "segment": "02",
        "title": "Coverage (screen 6202)",
        "source": "Policy Record 02 archive + master build sheet (captured reference)",
        "lines": lines,
        "fields": fields,
        "layout_html": master.get("layout_html", ""),
    }


def _row(indent: int, *cells):
    """Build one terminal line: optional left indent, then value tokens separated
    by two-space runs.  Each cell is ``(text,)`` (plain) or ``(text, field)``."""
    line = []
    if indent:
        line.append({"text": " " * indent, "field": None})
    for i, cell in enumerate(cells):
        if i:
            line.append({"text": "  ", "field": None})
        text = cell[0]
        field = cell[1] if len(cell) > 1 else None
        line.append({"text": text, "field": field})
    return line


def build_66() -> dict:
    """Segment 66 (Advanced Product) captured from the U0361148 screenshot.

    The 6266 terminal has no authored per-value tooltips and its display tokens do
    not map 1:1 onto the byte layout, so only the reliably-identifiable header
    tokens (segment id/length + flag bytes + the two fixed control fields) carry
    field-name hovers.  The authoritative byte -> field reference is the Record
    Layout table below (from the master build sheet)."""
    layout_html = (TMP / "sample_6266.htm").read_text(encoding="utf-8")
    lines = [
        _row(0, ("  ",), ("6266,", "Screen Name"), ("  ",),
             ("U0361148 ;.", "Policy Number")),
        _row(0, ("66", "Segment Identification"), ("0247", "Segment Length"),
             ("00000000", "Flag Byte A"), ("00000000", "Flag Byte B"),
             ("00000000", "Flag Byte C"), ("00000000", "Flag Byte D"),
             ("00000000", "Flag Byte E"), ("00000000", "User Flag Byte"),
             ("2", "TEFRA/DEFRA"), ("1", "Plan Option"), ("12",), ("11",)),
        _row(8, ("08/15/2070",), ("0",), ("4.000",), ("4.000",), ("M",), ("1",),
             ("L0",), ("120",), ("1",), ("0",), ("0",), ("**/**/****",), ("1",),
             ("2",), ("08/15/2026",), ("1",), ("0",)),
        _row(8, ("0",), ("13",), ("300",), ("999",), ("Y",), ("10",),
             ("9999999",), ("0",), ("0",), ("M",), ("0",), ("**/**/****",),
             ("1",), ("A",), ("1",), ("0",), ("185.000",), ("25000",)),
        _row(8, ("91869.61",), (".00",), ("12",), ("0",), ("0N15601",), ("0",),
             ("0910",), ("100",), ("999",), ("0",), ("0",), ("0",), ("A",),
             ("0",), ("4.000",), ("002",), ("0",), ("0",), ("2",), ("0",),
             ("8",)),
        _row(8, ("6.000",), ("0",), ("6.000",), ("336",), ("61",), ("1",),
             (".000",), ("T",), ("**/**/****",), ("08/15/2025",), ("1",),
             ("**/**/****",), ("330",), ("0",)),
        _row(8, ("C",), ("87",), ("5",), ("08/15/2008",), ("0",),
             ("**/**/****",), ("0",), (".00",), ("0",), ("0",), ("0",), ("0",),
             ("0",), ("1",)),
        _row(0, (" ",)),
        _row(0, ("CK620 DISPLAY COMPLETE",)),
    ]
    fields = {name: [] for name in _token_field_names(lines)}
    return {
        "segment": "66",
        "title": "Advanced Product (screen 6266)",
        "source": "Example screen shots.docx img (U0361148) + master build sheet "
                  "(captured reference)",
        "lines": lines,
        "fields": fields,
        "layout_html": layout_html,
    }


BUILDERS = {"02": build_02, "66": build_66, "67": build_67}


def main():
    cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    segments = cfg.get("segments", list(BUILDERS))
    for seg in segments:
        builder = BUILDERS.get(seg)
        if builder is None:
            print(f"skip {seg}: no builder")
            continue
        screen = builder()
        out = DATA_DIR / f"seg_{seg}.json"
        out.write_text(json.dumps(screen, indent=2), encoding="utf-8")
        n_fields = sum(1 for v in screen["fields"].values() if v)
        print(f"wrote {out.name}: lines={len(screen['lines'])} "
              f"fields={len(screen['fields'])} (mapped={n_fields}) "
              f"layout_html={len(screen['layout_html'])}")


if __name__ == "__main__":
    main()
