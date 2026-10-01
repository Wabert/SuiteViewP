"""Search CyberDoc PDFs for diagnostic terms.

Usage:
``venv\\Scripts\\python.exe tools\\rerun\\search_cyberdoc_pdf.py
C:\\Users\\ab7y02\\Dev\\Policy_Reference\\CyberDoc_1201 shadow XP CCV SWAM``

Read-only helper for RERUN baseline diagnostics.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _extract_with_pypdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_with_pymupdf(path: Path) -> str:
    import fitz

    doc = fitz.open(str(path))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def extract_text(path: Path) -> tuple[str, str]:
    errors = []
    for name, func in (("pypdf", _extract_with_pypdf), ("pymupdf", _extract_with_pymupdf)):
        try:
            return func(path), name
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    raise RuntimeError("PDF text extraction failed: " + " | ".join(errors))


def snippets(text: str, terms: list[str], context: int) -> list[dict[str, object]]:
    lowered = text.lower()
    found = []
    for term in terms:
        start = 0
        needle = term.lower()
        while True:
            idx = lowered.find(needle, start)
            if idx < 0:
                break
            left = max(0, idx - context)
            right = min(len(text), idx + len(term) + context)
            found.append({
                "term": term,
                "offset": idx,
                "snippet": " ".join(text[left:right].split()),
            })
            start = idx + len(term)
            if len(found) >= 200:
                return found
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder")
    parser.add_argument("terms", nargs="+")
    parser.add_argument("--context", type=int, default=220)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    folder = Path(args.folder)
    results = []
    extractor = ""
    for path in sorted(folder.glob("*.pdf")):
        try:
            text, extractor = extract_text(path)
            hits = snippets(text, args.terms, args.context)
        except Exception as exc:  # noqa: BLE001
            hits = [{"error": f"{type(exc).__name__}: {exc}"}]
        if hits:
            results.append({"file": str(path), "hits": hits[:50]})
    payload = {"folder": str(folder), "terms": args.terms, "extractor": extractor, "results": results}
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({
        "matches": len(results),
        "output": args.output,
        "files": [Path(row["file"]).name for row in results[:20]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
