"""Read-only, page-numbered text search across local reference PDFs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import fitz


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("terms", nargs="+")
    parser.add_argument("--file", default="*.pdf")
    args = parser.parse_args()
    results = []
    for path in sorted(args.directory.glob(args.file)):
        with fitz.open(path) as document:
            for index, page in enumerate(document):
                lines = page.get_text().splitlines()
                for line_index, line in enumerate(lines):
                    if any(term.casefold() in line.casefold() for term in args.terms):
                        results.append({
                            "pdf": path.name,
                            "pdf_page": index + 1,
                            "context": lines[max(0, line_index - 2):line_index + 4],
                        })
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
