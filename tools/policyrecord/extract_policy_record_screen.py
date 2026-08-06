"""Extract a CyberLife Policy Record HTML sample screen into structured JSON.

The sample screens under ``docs/Policy Record`` document one policy-record
segment.  A file may contain up to two tables:

* a **terminal-screen** table -- the green-on-black mainframe display, where each
  on-screen value is an ``<a title="Field Name">value</a>`` anchor (present only
  for segments that shipped with a rendered sample, e.g. 6258); and
* a **record-layout** table -- ``Byte | Field | Redefines...`` rows mapping each
  field to its COBOL / DB2 source (``<a name="...">`` + ``<b>label</b>``).

This one-shot helper parses a file into a JSON document the native PolView
"Policy Record" viewer renders, so no HTML/browser is shipped with the app.

The tables are identified by **content**, not position, so it works whether a
file has both tables (6258) or only the layout table (6201):

* ``lines``       -- the terminal screen, as rows of ``{text, field}`` runs
                     (empty when the file has no terminal-screen table).
* ``fields``      -- ``field label -> ["COBOL: ...", "DB2: ...", ...]`` for every
                     documented field (primary and redefines), for tooltips.
* ``field_specs`` -- the ordered list of **primary** fields
                     ``{name, byte, db2, cobol}`` down the record, so a flat
                     fixed-layout segment can be rendered live from DB2.
* ``layout_html`` -- the raw record-layout table HTML (rendered via Qt rich text).

Usage:
    python tools/policyrecord/extract_policy_record_screen.py "{\"html\": \"docs/Policy Record/Sample 6201 screen.htm\", \"segment\": \"01\", \"title\": \"Segment 01 - Basic Policy\", \"out\": \"suiteview/polview/data/policy_record_screens/seg_01.json\"}"
"""

import html as _html
import json
import os
import re
import sys
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# Terminal-screen table -> lines
# ---------------------------------------------------------------------------

class _TerminalParser(HTMLParser):
    """Parse a single terminal-screen ``<table>`` into lines of runs.

    Each ``<tr>`` is a screen line; each ``<a title=...>`` is a hover-aware value
    run; surrounding text is inert spacing.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._in_td = False
        self._in_a = False
        self._a_title = None
        self._a_emitted = False
        self._lines = []
        self._current_line = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._current_line = []
        elif tag == "td":
            self._in_td = True
        elif tag == "a":
            self._in_a = True
            self._a_title = dict(attrs).get("title")
            self._a_emitted = False

    def handle_endtag(self, tag):
        if tag == "tr":
            if self._current_line is not None:
                self._lines.append(self._current_line)
            self._current_line = None
        elif tag == "td":
            self._in_td = False
        elif tag == "a":
            if (
                self._in_td
                and self._current_line is not None
                and self._a_title
                and not self._a_emitted
            ):
                self._current_line.append({"text": "", "field": self._a_title})
            self._in_a = False
            self._a_title = None
            self._a_emitted = False

    def handle_data(self, data):
        if self._in_td and self._current_line is not None and data:
            field = self._a_title if self._in_a else None
            # Keep raw text (incl. \xa0); whitespace is normalised later so the
            # native render matches how a browser collapses source formatting.
            self._current_line.append({"text": data, "field": field})
            if self._in_a:
                self._a_emitted = True


def _html_collapse(text):
    """Reproduce browser whitespace handling: keep each ``\xa0`` (&#160;) as a
    hard space, collapse every run of ASCII whitespace to a single space."""
    out = []
    prev_ws = False
    for ch in text:
        if ch == "\xa0":
            out.append(" ")
            prev_ws = False
        elif ch.isspace():
            if not prev_ws:
                out.append(" ")
                prev_ws = True
        else:
            out.append(ch)
            prev_ws = False
    return "".join(out)


def _normalize_lines(lines):
    """Collapse whitespace in every run and drop runs that become empty."""
    normalized = []
    for line in lines:
        runs = []
        for run in line:
            text = _html_collapse(run["text"])
            if text == "" and not run["field"]:
                continue
            runs.append({"text": text, "field": run["field"]})
        normalized.append(runs)
    return normalized


def _trim_trailing_blank_lines(lines, keep=1):
    """Collapse a long run of empty filler lines at the end to *keep* lines."""
    def is_blank(line):
        return all(not run["text"].strip() for run in line)

    end = len(lines)
    while end > 0 and is_blank(lines[end - 1]):
        end -= 1
    trailing = min(len(lines) - end, keep)
    return lines[: end + trailing]


# ---------------------------------------------------------------------------
# Table splitting / classification
# ---------------------------------------------------------------------------

def _split_tables(html):
    """Return the raw HTML of every top-level ``<table>...</table>`` block."""
    return re.findall(r"<table\b.*?</table>", html, flags=re.IGNORECASE | re.DOTALL)


def _classify(table_html):
    if re.search(r"title\s*=", table_html, flags=re.IGNORECASE):
        return "terminal"
    if re.search(r"<a\s+name=", table_html, flags=re.IGNORECASE) or ">Byte<" in table_html:
        return "layout"
    return "unknown"


def _repair_layout_html(snippet):
    """Repair a malformed header cell in the source where rowspan leaked into the
    style string (missing closing quote) -- keeps Qt's parser from dropping the
    first "Byte" header cell's styling."""
    return snippet.replace(
        'background-color: rgb(230,160,170); rowspan="1">',
        'background-color: rgb(230,160,170);" rowspan="1">',
    )


# ---------------------------------------------------------------------------
# Record-layout table -> fields + ordered field_specs
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"</?br\s*/?>", flags=re.IGNORECASE)
_BYTE_RE = re.compile(r"^\d+(?:-\d+)?$")


def _strip_tags(html):
    return _TAG_RE.sub("", html)


def _parse_field_cell(cell_html):
    """Parse one ``<td>`` field cell into name + mapping lines.

    Returns ``None`` when the cell has no ``<b>`` label (i.e. it is not a field
    cell).  ``db2`` is the first real ``TABLE.COLUMN`` source (``None`` when the
    field has no DB2 source or it is documented as ``none``).
    """
    b = re.search(r"<b>(.*?)</b>", cell_html, flags=re.DOTALL)
    if b is None:
        return None
    name = _html_collapse(_html.unescape(_strip_tags(b.group(1)))).strip()

    body = _BR_RE.sub("\n", cell_html)
    body = _html.unescape(_strip_tags(body))
    mappings = []
    cobol = None
    db2 = None
    for raw in body.split("\n"):
        line = _html_collapse(raw).strip()
        if line.startswith("COBOL:"):
            mappings.append(line)
            if cobol is None:
                cobol = line[len("COBOL:"):].strip()
        elif line.startswith("DB2:"):
            mappings.append(line)
            value = line[len("DB2:"):].strip()
            if db2 is None and value and value.lower() != "none":
                db2 = value
        elif line.startswith("Modification:"):
            mappings.append(line)
    return {"name": name, "mappings": mappings, "cobol": cobol, "db2": db2}


def _parse_layout(layout_html):
    """Return ``(fields, field_specs)`` from a record-layout table.

    * ``fields``      -- ``name -> [mapping strings]`` for every field cell.
    * ``field_specs`` -- ordered ``{name, byte, db2, cobol}`` for the **primary**
                         (leftmost) field of each byte row (redefines excluded).
    """
    fields = {}
    specs = []

    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", layout_html,
                      flags=re.IGNORECASE | re.DOTALL)
    for row in rows:
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row,
                           flags=re.IGNORECASE | re.DOTALL)
        if not cells:
            continue

        byte = None
        row_fields = []
        for cell in cells:
            field = _parse_field_cell(cell)
            if field is not None:
                row_fields.append(field)
                continue
            text = _html_collapse(_html.unescape(_strip_tags(cell))).strip()
            if _BYTE_RE.match(text):
                byte = text

        # Register every field (primary + redefines) for tooltips.
        for field in row_fields:
            if not field["name"]:
                continue
            bucket = fields.setdefault(field["name"], [])
            for mapping in field["mappings"]:
                if mapping not in bucket:
                    bucket.append(mapping)

        # The leftmost field of a byte row is the primary displayed field.
        if byte is not None and row_fields:
            primary = row_fields[0]
            specs.append({
                "name": primary["name"],
                "byte": byte,
                "db2": primary["db2"],
                "cobol": primary["cobol"],
            })

    return fields, specs


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing JSON argument"}))
        return 2
    if sys.argv[1].lstrip().startswith("{"):
        args = json.loads(sys.argv[1])
    else:
        if len(sys.argv) < 5:
            print(json.dumps({
                "error": "positional usage: <html> <segment> <title> <out>",
            }))
            return 2
        args = {
            "html": sys.argv[1],
            "segment": sys.argv[2],
            "title": sys.argv[3],
            "out": sys.argv[4],
        }
    html_path = args["html"]
    segment = str(args["segment"])
    out_path = args["out"]
    title = args.get("title", f"Segment {segment}")

    with open(html_path, "r", encoding="utf-8", errors="replace") as fh:
        html = fh.read()

    terminal_html = ""
    layout_html = ""
    for block in _split_tables(html):
        kind = _classify(block)
        if kind == "terminal" and not terminal_html:
            terminal_html = block
        elif kind == "layout" and not layout_html:
            layout_html = _repair_layout_html(block)

    lines = []
    if terminal_html:
        parser = _TerminalParser()
        parser.feed(terminal_html)
        lines = _normalize_lines(parser._lines)
        lines = _trim_trailing_blank_lines(lines, keep=1)

    fields, field_specs = ({}, [])
    if layout_html:
        fields, field_specs = _parse_layout(layout_html)

    doc = {
        "segment": segment,
        "title": title,
        "source": os.path.basename(html_path),
        "lines": lines,
        "fields": fields,
        "field_specs": field_specs,
        "layout_html": layout_html,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)

    print(json.dumps({
        "ok": True,
        "out": out_path,
        "lines": len(lines),
        "fields": len(fields),
        "field_specs": len(field_specs),
        "layout_html_len": len(layout_html),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
