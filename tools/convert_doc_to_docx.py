"""Convert a legacy binary Word ``.doc`` to ``.docx`` using Word COM.

This is an auditable bridge for policy-record screenshot documents that predate
the Office Open XML format.  The resulting ``.docx`` can be processed by
``tools/extract_docx.py`` without requiring a separate document parser.

Usage:
    venv\\Scripts\\python.exe tools/convert_doc_to_docx.py ^
        "{\"path\":\"docs/Policy Record/Policy Segments seg.doc\"}"
    venv\\Scripts\\python.exe tools/convert_doc_to_docx.py ^
        "docs\\Policy Record\\Policy Segments seg.doc" "C:\\tmp\\segments.docx"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1].lstrip().startswith("{"):
        cfg = json.loads(sys.argv[1])
    elif len(sys.argv) > 1:
        cfg = {"path": sys.argv[1]}
        if len(sys.argv) > 2:
            cfg["out"] = sys.argv[2]
    else:
        cfg = {}
    source = Path(cfg["path"]).resolve()
    destination = Path(cfg.get("out") or source.with_suffix(".docx")).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)

    try:
        from win32com.client import dynamic
    except ImportError as exc:
        raise RuntimeError("win32com is required to convert legacy Word files") from exc

    word = dynamic.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    document = None
    try:
        document = word.Documents.Open(
            str(source),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        document.SaveAs2(str(destination), FileFormat=16)
    finally:
        if document is not None:
            document.Close(SaveChanges=False)
        word.Quit()

    print(json.dumps({
        "ok": True,
        "source": str(source),
        "out": str(destination),
        "size": destination.stat().st_size,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
