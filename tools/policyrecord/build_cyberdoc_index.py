"""Build a COBOL-name -> field-format index from the CyberLife policy-record docs.

The official CyberLife documentation (``Policy_Reference/CyberDoc_1201/*.pdf``
beside this repo, extracted to ``Policy_Reference/CyberDoc_1201/text/*.txt`` by
``extract_pdf_text.py``) documents every policy
record field as a block::

    Accounting Date                              <- human name (line before Format)
    Format: MMDDYY, 4 bytes packed               <- storage / display format
    AL: FBRPAYDT                                 <- 8-char assembler label
    PL4                                          <- assembler PIC
    COBOL: FBRPAYDT-ACCOUNTING-DATE              <- full COBOL name (the key)
    S9(7) COMP-3                                 <- COBOL PIC
    <prose description...>

This tool walks those blocks and emits a JSON map keyed by the **primary COBOL
name** (which matches the ``cobol`` field on each ``seg_<n>.json`` field spec)::

    {
      "FBRPAYDT-ACCOUNTING-DATE": {
        "name": "Accounting Date",
        "format": "MMDDYY, 4 bytes packed",
        "kind": "date_packed"
      },
      ...
    }

``kind`` is a normalised display class the policy-record builder can act on:

    date         - compound calendar date (Internal date / MOYR date / MOYR code)
                   -> rendered slashed MM/DD/YYYY on the mainframe
    date_packed  - single packed field explicitly documented "MMDDYY"
                   -> rendered as the packed integer MMDDYY (e.g. 71026)
    packed_num   - single packed whole-number field; if its DB2 value is a date
                   the mainframe shows it packed MMDDYY too (e.g. Billing Date)
    decimal:N    - packed/zoned number with N fractional digits
    int          - binary whole number
    flag         - a byte of flag bits
    char         - character / code field
    (absent)     - unclassified (group-level containers, etc.)

Usage::

    venv\\Scripts\\python.exe tools/policyrecord/build_cyberdoc_index.py
    venv\\Scripts\\python.exe tools/policyrecord/build_cyberdoc_index.py '{"sources": ["../Policy_Reference/CyberDoc_1201/text/D20.txt"], "out": "..."}'

Config keys (all optional):
    sources -- list of extracted .txt docs to parse, in *priority* order
               (earlier files win on COBOL-name conflicts).
               Default: D20.txt then D202.txt from Policy_Reference/CyberDoc_1201/text
               (found by searching upward from the repo; env CYBERDOC_TEXT_DIR overrides)
    out     -- output JSON path. Default:
               suiteview/polview/data/policy_record_screens/cyberdoc_field_formats.json
"""

import json
import os
import re
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cyberdoc_text_dir() -> str:
    """Locate the shared ``Policy_Reference/CyberDoc_1201/text`` corpus.

    Searched upward from the repo so checkouts under ``SuiteViewP.worktrees``
    resolve too; ``CYBERDOC_TEXT_DIR`` overrides.
    """
    override = os.environ.get("CYBERDOC_TEXT_DIR")
    if override:
        return override
    parent = _REPO
    while True:
        candidate = os.path.join(parent, "Policy_Reference", "CyberDoc_1201", "text")
        if os.path.isdir(candidate):
            return candidate
        up = os.path.dirname(parent)
        if up == parent:
            return os.path.join(os.path.dirname(_REPO), "Policy_Reference", "CyberDoc_1201", "text")
        parent = up


_DEFAULT_SOURCES = [
    os.path.join(_cyberdoc_text_dir(), "D20.txt"),
    os.path.join(_cyberdoc_text_dir(), "D202.txt"),
]
_DEFAULT_OUT = os.path.join(
    _REPO, "suiteview", "polview", "data", "policy_record_screens",
    "cyberdoc_field_formats.json",
)

_FORMAT_RE = re.compile(r"^Format:\s*(.+?)\s*$", re.IGNORECASE)
_COBOL_RE = re.compile(r"^COBOL:\s*(\S+)", re.IGNORECASE)
_DECIMAL_RE = re.compile(r"(\d+)\s+decimal")


def classify(fmt: str):
    """Map a CyberDoc ``Format:`` string to a normalised display ``kind``."""
    f = fmt.lower().strip()
    # Strip a leading "group level," qualifier before classifying the payload.
    f = re.sub(r"^group level,\s*", "", f)

    # Dates first -- their format strings also contain "packed".
    if "mmddyy" in f:
        return "date_packed"
    if "internal date" in f or "moyr" in f:
        return "date"

    m = _DECIMAL_RE.search(f)
    if m:
        return "decimal:%d" % int(m.group(1))

    if "flag bit" in f:
        return "flag"
    if "binary" in f:
        return "int"
    # A single packed whole-number field (no decimals). When its DB2 source is a
    # date column the mainframe renders it packed MMDDYY (e.g. Billing Date).
    if "packed" in f and "whole number" in f:
        return "packed_num"
    if "packed" in f:
        return "packed_num"
    if "char" in f:  # "N characters", "N bytes, character"
        return "char"
    return None


def parse_source(path: str) -> dict:
    """Parse one extracted doc into ``{cobol_name: {name, format, kind}}``."""
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    out = {}
    i = 0
    n = len(lines)
    while i < n:
        m = _FORMAT_RE.match(lines[i])
        if not m:
            i += 1
            continue
        fmt = m.group(1).strip()
        # The human field name is the nearest non-empty line above "Format:".
        name = ""
        j = i - 1
        while j >= 0:
            cand = lines[j].strip()
            if cand:
                name = cand
                break
            j -= 1
        # The primary COBOL name is the first "COBOL:" line below "Format:",
        # before the next "Format:" block starts.
        cobol = None
        k = i + 1
        while k < n and not _FORMAT_RE.match(lines[k]):
            cm = _COBOL_RE.match(lines[k])
            if cm:
                cobol = cm.group(1).rstrip(".").strip()
                break
            k += 1
        if cobol:
            out[cobol] = {
                "name": name,
                "format": fmt,
                "kind": classify(fmt),
            }
        i += 1
    return out


def main():
    cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    sources = cfg.get("sources") or _DEFAULT_SOURCES
    out_path = cfg.get("out") or _DEFAULT_OUT

    index = {}
    per_source = {}
    # Later sources fill only gaps -> earlier (higher priority) sources win.
    for src in sources:
        if not os.path.exists(src):
            per_source[src] = "missing"
            continue
        parsed = parse_source(src)
        per_source[src] = len(parsed)
        for cobol, meta in parsed.items():
            index.setdefault(cobol, meta)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    ordered = {k: index[k] for k in sorted(index)}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(ordered, fh, indent=2)
        fh.write("\n")

    kinds = {}
    for meta in index.values():
        kinds[meta["kind"]] = kinds.get(meta["kind"], 0) + 1

    print(json.dumps({
        "ok": True,
        "out": out_path,
        "sources": per_source,
        "total_fields": len(index),
        "kind_counts": kinds,
    }, indent=2))


if __name__ == "__main__":
    main()
