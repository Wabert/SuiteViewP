"""Extract text and embedded images from a ``.docx`` in document order.

Auditable helper for turning a Word document of CyberLife policy-record
screenshots (e.g. ``docs/Policy Record/Example screen shots.docx``) into plain
text + PNG/EMF images that can be viewed and cross-referenced when building out
new policy-record segments.

Walks the document body in order so each image is emitted with a sequence number
alongside the paragraphs around it, and writes an ``index.json`` describing the
run of text/image blocks.

Usage::

    venv\\Scripts\\python.exe tools/office/extract_docx.py '{"path": "docs/Policy Record/Example screen shots.docx"}'
    venv\\Scripts\\python.exe tools/office/extract_docx.py '{"path": "...", "out": "C:/tmp/docx"}'
    venv\\Scripts\\python.exe tools/office/extract_docx.py document.docx C:/tmp/docx

Config keys:
    path -- .docx path (required)
    out  -- output dir (default: <docxdir>/<docxstem>_extract)
"""

import json
import os
import sys
import zipfile
from xml.etree import ElementTree as ET

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
_V = "{urn:schemas-microsoft-com:vml}"


def _rels(zf) -> dict:
    """Map relationship id -> media target from document.xml.rels."""
    out = {}
    try:
        data = zf.read("word/_rels/document.xml.rels")
    except KeyError:
        return out
    root = ET.fromstring(data)
    for rel in root:
        rid = rel.get("Id")
        target = rel.get("Target")
        if rid and target:
            out[rid] = target
    return out


def _para_text(p) -> str:
    return "".join(t.text or "" for t in p.iter(f"{_W}t"))


def _embed_ids(el):
    """Yield relationship ids for modern DrawingML and legacy VML images."""
    for blip in el.iter(f"{_A}blip"):
        rid = blip.get(f"{_R}embed")
        if rid:
            yield rid
    for image in el.iter(f"{_V}imagedata"):
        rid = image.get(f"{_R}id")
        if rid:
            yield rid


def main():
    if len(sys.argv) > 1 and sys.argv[1].lstrip().startswith("{"):
        cfg = json.loads(sys.argv[1])
    elif len(sys.argv) > 1:
        cfg = {"path": sys.argv[1]}
        if len(sys.argv) > 2:
            cfg["out"] = sys.argv[2]
    else:
        cfg = {}
    path = cfg["path"]
    stem = os.path.splitext(os.path.basename(path))[0]
    out_dir = cfg.get("out") or os.path.join(os.path.dirname(path), stem + "_extract")
    os.makedirs(out_dir, exist_ok=True)

    zf = zipfile.ZipFile(path)
    rels = _rels(zf)
    doc = ET.fromstring(zf.read("word/document.xml"))
    body = doc.find(f"{_W}body")

    blocks = []
    img_seq = 0
    text_lines = []
    for el in body.iter():
        if el.tag == f"{_W}p":
            txt = _para_text(el).strip()
            ids = list(_embed_ids(el))
            for rid in ids:
                img_seq += 1
                target = rels.get(rid, "")
                src = "word/" + target.replace("../", "")
                ext = os.path.splitext(src)[1] or ".bin"
                name = f"img_{img_seq:03d}{ext}"
                try:
                    with open(os.path.join(out_dir, name), "wb") as fh:
                        fh.write(zf.read(src))
                    blocks.append({"seq": img_seq, "type": "image", "file": name, "src": src})
                    text_lines.append(f"[[IMAGE {img_seq}: {name}]]")
                except KeyError:
                    blocks.append({"seq": img_seq, "type": "image", "file": None, "src": src})
            if txt:
                blocks.append({"type": "text", "text": txt})
                text_lines.append(txt)

    with open(os.path.join(out_dir, "text.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(text_lines))
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(blocks, fh, indent=2)

    media = [n for n in zf.namelist() if n.startswith("word/media/")]
    print(json.dumps({
        "ok": True,
        "path": path,
        "out": out_dir,
        "images_in_order": img_seq,
        "media_files": media,
        "text_blocks": sum(1 for b in blocks if b.get("type") == "text"),
    }, indent=2))


if __name__ == "__main__":
    main()
