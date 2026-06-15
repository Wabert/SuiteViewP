"""Create a Desktop shortcut that launches the SuiteView taskbar (mini-bar).

Single-purpose helper:
  1. Renders the branded SuiteView icon (blue square, gold trim, golden "S")
     at multiple sizes by REUSING the app's own icon code
     (``SuiteViewTaskbar._create_icon_pixmap`` — a pure function of size, it
     never touches ``self``), so the shortcut icon always matches the live app.
  2. Assembles those renders into a multi-resolution ``.ico`` written to
     ``~/.suiteview/suiteview.ico`` (app-owned, persistent, out of the repo).
  3. Creates ``SuiteView.lnk`` on the Desktop pointing at
     ``venv\\Scripts\\pythonw.exe scripts\\run_suiteview.py`` so double-clicking
     starts the taskbar with no console window.

Run:
    venv\\Scripts\\python.exe tools/create_taskbar_shortcut.py                  # live (default)
    venv\\Scripts\\python.exe tools/create_taskbar_shortcut.py '{"variant":"local"}'  # local-data, red ring

The "local" variant points at scripts/run_suiteview_local.py (SUITEVIEW_LOCAL_DATA=1)
and paints the icon border red so it can't be confused with the live launcher.
Outputs a JSON status line to stdout.
"""

import json
import os
import struct
import sys
from pathlib import Path

# Project root = parent of this tools/ directory.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _render_png_frames(border=None):
    """Return list of (size, png_bytes) using the app's own icon drawing code.

    ``border`` (e.g. "#C0392B") overpaints the gold border in that colour to mark
    a variant — used to make the LOCAL-DATA shortcut visually distinct without
    duplicating the icon art.
    """
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PyQt6.QtGui import QColor, QPainter, QPen
    from PyQt6.QtWidgets import QApplication

    # A QApplication is required for QPixmap rendering. No window is shown.
    app = QApplication.instance() or QApplication(sys.argv)

    from suiteview.taskbar_launcher.suiteview_taskbar import SuiteViewTaskbar

    frames = []
    for size in ICON_SIZES:
        # _create_icon_pixmap ignores self -> safe to call unbound with None.
        pixmap = SuiteViewTaskbar._create_icon_pixmap(None, size)
        if border:
            # Repaint the border ring over the original gold one (same geometry
            # as _create_icon_pixmap: margin/rect/border_width/corner).
            margin = max(1, size // 32)
            rect_size = size - margin * 2
            border_width = max(1, size // 20)
            corner = max(2, size // 8)
            p = QPainter(pixmap)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(border), border_width))
            p.drawRoundedRect(margin, margin, rect_size, rect_size, corner, corner)
            p.end()
        image = pixmap.toImage()

        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "PNG")
        buf.close()
        frames.append((size, bytes(ba)))

    del app  # keep linter happy; QApplication lifetime is fine for a one-shot
    return frames


def _write_ico(frames, ico_path):
    """Assemble a PNG-compressed multi-resolution .ico (Vista+ format)."""
    count = len(frames)
    header = struct.pack("<HHH", 0, 1, count)  # reserved=0, type=1 (icon), count

    offset = len(header) + count * 16  # entries are 16 bytes each
    entries = bytearray()
    payload = bytearray()
    for size, png in frames:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO spec
        entries += struct.pack(
            "<BBBBHHII",
            dim,          # width
            dim,          # height
            0,            # color count (0 = >=256 colors)
            0,            # reserved
            1,            # color planes
            32,           # bits per pixel
            len(png),     # size of image data
            offset,       # offset of image data
        )
        payload += png
        offset += len(png)

    ico_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ico_path, "wb") as fh:
        fh.write(header)
        fh.write(entries)
        fh.write(payload)


def _create_shortcut(lnk_path, target, arguments, workdir, icon_path, desc):
    """Create a Windows .lnk via WScript.Shell (pywin32)."""
    import win32com.client

    shell = win32com.client.Dispatch("WScript.Shell")
    sc = shell.CreateShortcut(str(lnk_path))
    sc.TargetPath = str(target)
    sc.Arguments = arguments
    sc.WorkingDirectory = str(workdir)
    sc.IconLocation = str(icon_path)
    sc.Description = desc
    sc.WindowStyle = 1  # normal
    sc.Save()


# Shortcut variants: the normal live-data launcher, and a red-bordered LOCAL-DATA
# launcher that runs the suite against the offline SQLite fixtures.
VARIANTS = {
    "live": {
        "script": "scripts/run_suiteview.py",
        "lnk": "SuiteView.lnk",
        "ico": "suiteview.ico",
        "border": None,
        "desc": "SuiteView - launch the taskbar mini-bar",
    },
    "local": {
        "script": "scripts/run_suiteview_local.py",
        "lnk": "SuiteView (Local Data).lnk",
        "ico": "suiteview_local.ico",
        "border": "#C0392B",  # red ring = offline SQLite fixtures, NOT live DB2
        "desc": "SuiteView (LOCAL DATA) - offline SQLite fixtures, not live DB2",
    },
}


def main():
    cmd = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    variant = cmd.get("variant", "live")
    if variant not in VARIANTS:
        print(json.dumps({"ok": False, "error": f"unknown variant: {variant}"}))
        return 1
    cfg = VARIANTS[variant]

    pythonw = ROOT / "venv" / "Scripts" / "pythonw.exe"
    run_script = ROOT / cfg["script"]
    ico_path = Path(os.path.expanduser("~")) / ".suiteview" / cfg["ico"]

    if not pythonw.exists():
        print(json.dumps({"ok": False, "error": f"pythonw.exe not found: {pythonw}"}))
        return 1
    if not run_script.exists():
        print(json.dumps({"ok": False, "error": f"launcher not found: {run_script}"}))
        return 1

    # 1 + 2: render the branded icon (recoloured border for variants) and write the .ico
    frames = _render_png_frames(border=cfg["border"])
    _write_ico(frames, ico_path)

    # 3: resolve the real Desktop (handles OneDrive redirection) and make the .lnk
    import win32com.client

    desktop = Path(win32com.client.Dispatch("WScript.Shell").SpecialFolders("Desktop"))
    lnk_path = desktop / cfg["lnk"]

    _create_shortcut(
        lnk_path=lnk_path,
        target=pythonw,
        arguments=f'"{run_script}"',
        workdir=ROOT,
        icon_path=ico_path,
        desc=cfg["desc"],
    )

    print(json.dumps({
        "ok": True,
        "variant": variant,
        "shortcut": str(lnk_path),
        "icon": str(ico_path),
        "target": str(pythonw),
        "arguments": f'"{run_script}"',
        "sizes": ICON_SIZES,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
