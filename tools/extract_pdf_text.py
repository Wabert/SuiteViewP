"""Extract text from a PDF into a UTF-8 ``.txt`` file (and print a summary).

Auditable helper for turning the official CyberLife policy-record documentation
(``docs/CyberDoc/*.pdf``) into plain text so field definitions / COBOL names /
redefines / formats can be searched and cross-referenced without a PDF viewer.

Uses PyMuPDF (``fitz``).  Pages are separated by a form-feed marker line so the
source page of any hit can be found.

Usage:
    venv\\Scripts\\python.exe tools/extract_pdf_text.py '{"pdf": "docs/CyberDoc/D10.pdf", "out": "docs/CyberDoc/text/D10.txt"}'
    venv\\Scripts\\python.exe tools/extract_pdf_text.py '{"pdf": "...", "first": 1, "last": 20}'

Config keys (all optional except ``pdf``):
    pdf    -- path to the source PDF (required)
    out    -- output .txt path (default: alongside the PDF under a text/ dir)
    first  -- 1-based first page (default: 1)
    last   -- 1-based last page inclusive (default: last page)
"""

import json
import os
import sys

import fitz  # PyMuPDF


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "{}"
    if arg.startswith("@"):
        with open(arg[1:], "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    else:
        cfg = json.loads(arg)
    pdf_path = cfg["pdf"]
    doc = fitz.open(pdf_path)

    first = int(cfg.get("first", 1))
    last = int(cfg.get("last", doc.page_count))
    first = max(1, first)
    last = min(doc.page_count, last)

    out_path = cfg.get("out")
    if not out_path:
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        out_dir = os.path.join(os.path.dirname(pdf_path), "text")
        out_path = os.path.join(out_dir, base + ".txt")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    chars = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for pno in range(first - 1, last):
            page = doc.load_page(pno)
            text = page.get_text("text")
            fh.write(f"\f===== PAGE {pno + 1} =====\n")
            fh.write(text)
            chars += len(text)

    print(json.dumps({
        "ok": True,
        "pdf": pdf_path,
        "out": out_path,
        "pages": doc.page_count,
        "extracted_pages": last - first + 1,
        "chars": chars,
    }))


if __name__ == "__main__":
    main()
