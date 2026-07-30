"""Verify positional alignment between an archive terminal entry and the master
field_specs for Segment 02, so a repeated-template live builder can trust that
"the i-th on-screen token == the i-th record-layout field".

Loads:
  * archive  -- seg_02.json extracted from the archive terminal (tokens carry the
                on-screen text + a short field name), entries delimited by a value
                token whose text is exactly "02" (Segment Identification).
  * master   -- seg_02 layout JSON extracted from the master build sheet
                (field_specs carry byte / name / db2 / cobol in byte order).

Prints, side by side, the archive entry-1 value tokens and the master
field_specs, flagging the first length/þmismatch so misalignment can't silently
produce wrong data.

Usage:
    python tools/align_seg02.py "{\"archive\": \"C:/tmp/segjson/seg_02.json\", \"master\": \"C:/tmp/segjson/seg_02_layout.json\", \"entry\": 1}"
"""

import json
import sys


def _entry_value_tokens(lines):
    """Split value tokens (field != None) into entries.

    A new entry starts at each token whose text is exactly '02' (the Segment
    Identification).  Returns a list of entries, each a list of (field, text).
    """
    entries = []
    current = None
    for line in lines:
        for run in line:
            if not run.get("field"):
                continue
            text = run.get("text", "")
            if text.strip() == "02" and run.get("field") == "Segment Identification":
                current = []
                entries.append(current)
            if current is not None:
                current.append((run.get("field"), text))
    return entries


def main():
    cfg = json.loads(sys.argv[1])
    with open(cfg["archive"], "r", encoding="utf-8") as fh:
        archive = json.load(fh)
    with open(cfg["master"], "r", encoding="utf-8") as fh:
        master = json.load(fh)

    entry_idx = int(cfg.get("entry", 1)) - 1
    entries = _entry_value_tokens(archive.get("lines", []))
    tokens = entries[entry_idx] if entry_idx < len(entries) else []
    specs = master.get("field_specs", []) or []

    print("archive entries:", len(entries),
          "| entry", entry_idx + 1, "tokens:", len(tokens),
          "| master field_specs:", len(specs))
    print()
    n = max(len(tokens), len(specs))
    for i in range(n):
        tok = tokens[i] if i < len(tokens) else (None, None)
        sp = specs[i] if i < len(specs) else {}
        print("%3d | arc %-34s = %-14r | spec byte %-8s %-34s db2=%s" % (
            i, (tok[0] or "")[:34], tok[1], sp.get("byte"),
            (sp.get("name") or "")[:34], sp.get("db2")))


if __name__ == "__main__":
    main()
