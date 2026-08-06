"""Build the authoritative Segment-01 screen JSON by merging two source docs:

* the **archive terminal template** (``Archive/Policy Record 01 - BKUP …``) --
  provides the *authentic* on-screen layout: exact line breaks, spacing, the
  segment length (``0292``), and a realistic sample value at every position; and
* the **Sample 6201 mapping** (``seg_01.json`` produced from
  ``Sample 6201 screen.htm``) -- provides the byte-ordered DB2/COBOL source for
  each field (the mapping guide).

Both walk the record in byte order, so the i-th terminal value-token corresponds
to the i-th non-reserved field_spec (validated 1:1, 111=111).  We annotate each
template value-token with its resolved field name + DB2 source, and mark
header/footer chrome with a ``role`` so the live builder can substitute the
policy number, current date, user id and region.

Output schema (``seg_01.json``):
    segment, title, source, template=True
    lines        -- the template, tokens annotated:
                      chrome  -> {text, field, role}
                      value   -> {text(sample), field(spec name), db2 or null}
                      spacing -> {text, field:null}
    fields       -- spec name -> [COBOL:/DB2: ...]  (for tooltips)
    field_specs  -- byte-ordered specs (kept)
    layout_html  -- the Sample 6201 Record Layout table (has DB2 mappings)

Usage:
    venv\\Scripts\\python.exe tools/policyrecord/build_seg01_json.py '{"archive": "...", "mapping": "...", "out": "..."}'
"""

import json
import os
import sys

_ROLES = {
    "Screen Name": "screen_name",
    "Policy Number": "policy",
    "Segment Identification": "seg_id",
    "Segment Length": "seg_len",
    "Current Date": "current_date",
    "Part of the user ID?": "user",
    "Region and Company": "region",
}


def _display_specs(specs):
    """field_specs minus structural id/length and Reserved filler -- the fields
    that actually appear, in byte order."""
    out = []
    for s in specs:
        name = s.get("name", "")
        if name in ("Segment Identification", "Segment Length"):
            continue
        if name.lower().startswith("reserved"):
            continue
        out.append(s)
    return out


def main():
    args = json.loads(sys.argv[1])
    with open(args["archive"], "r", encoding="utf-8") as fh:
        archive = json.load(fh)
    with open(args["mapping"], "r", encoding="utf-8") as fh:
        mapping = json.load(fh)
    out_path = args["out"]

    specs = _display_specs(mapping.get("field_specs", []))
    spec_i = 0
    unresolved = []
    seg = mapping.get("segment", "01")

    new_lines = []
    for line in archive.get("lines", []):
        new_line = []
        for run in line:
            field = run.get("field")
            if not field:
                new_line.append({"text": run["text"], "field": None})
                continue
            role = _ROLES.get(field)
            if role:
                # Canonicalise the two chrome tokens whose archive text is
                # policy-specific, so the (rare) sample fallback is correct too;
                # the live builder overrides every role anyway.
                text = run["text"]
                if role == "screen_name":
                    text = f"62{seg},"
                elif role == "policy":
                    text = text.split()[0] if text.split() else text
                new_line.append({"text": text, "field": field, "role": role})
                continue
            # A record value token: pair with the next byte-ordered spec.
            if spec_i < len(specs):
                spec = specs[spec_i]
                spec_i += 1
                new_line.append({
                    "text": run["text"],
                    "field": spec["name"],
                    "db2": spec.get("db2"),
                })
            else:
                unresolved.append(field)
                new_line.append({"text": run["text"], "field": field, "db2": None})
        new_lines.append(new_line)

    doc = {
        "segment": mapping.get("segment", "01"),
        "title": mapping.get("title", "Segment 01 - Basic Policy"),
        "source": archive.get("source", ""),
        "template": True,
        "lines": new_lines,
        "fields": mapping.get("fields", {}),
        "field_specs": mapping.get("field_specs", []),
        "layout_html": mapping.get("layout_html", ""),
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)

    print(json.dumps({
        "ok": True,
        "out": out_path,
        "lines": len(new_lines),
        "specs_used": spec_i,
        "specs_available": len(specs),
        "unresolved": unresolved,
    }))


if __name__ == "__main__":
    main()
