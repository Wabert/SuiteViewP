"""Render one page of a PDF to a PNG for visual inspection (QtPdf).

Usage: venv\\Scripts\\python.exe tools/render_pdf_page.py <in.pdf> <out.png> [page]
Prints JSON {"ok": true, "out": path, "page_size": [w, h]} on success.
"""
from __future__ import annotations

import json
import sys

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication


def main() -> int:
    pdf_path, out_path = sys.argv[1], sys.argv[2]
    page = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    try:
        from PyQt6.QtPdf import QPdfDocument
    except ImportError:
        print(json.dumps({"ok": False, "error": "PyQt6.QtPdf not available"}))
        return 1
    document = QPdfDocument(None)
    document.load(pdf_path)
    if document.status() != QPdfDocument.Status.Ready:
        print(json.dumps({"ok": False, "error": f"load status {document.status()}"}))
        return 1
    size = document.pagePointSize(page)
    scale = 1.5  # ~108 dpi
    image = document.render(page, QSize(int(size.width() * scale), int(size.height() * scale)))
    image.save(out_path)
    print(json.dumps({"ok": True, "out": out_path,
                      "page_size": [size.width(), size.height()],
                      "page_count": document.pageCount()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
