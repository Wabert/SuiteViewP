"""Render AuditWindow and validate the simplified Query Object header."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from suiteview.audit.audit_window import AuditWindow


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyle("Fusion")

    window = AuditWindow(region="CKPR")
    window.resize(1215, 720)
    window.show()
    app.processEvents()

    expected = {
        "objects": "Objects",
        "new": "New Object",
        "cyberlife": "Cyberlife",
        "studio": "Query Studio",
        "dataforge": "DataForge",
    }
    actual = {
        "objects": window.btn_objects.text(),
        "new": window.btn_new_object.text(),
        "cyberlife": window.btn_cyberlife.text(),
        "studio": window.btn_workbench.text(),
        "dataforge": window.btn_dataforge.text(),
    }
    if actual != expected:
        raise RuntimeError(f"Unexpected header labels: {actual}")
    if window.btn_qdef.isVisible():
        raise RuntimeError("Advanced/QDef button is still visible in the normal header")

    output_dir = PROJECT_ROOT / "docs" / "audit" / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "audit_query_studio_header.png"
    pixmap = window.grab()
    if pixmap.isNull():
        raise RuntimeError("Audit header screenshot was blank/null")
    pixmap.save(str(output_path))

    image = pixmap.toImage()
    width = image.width()
    height = image.height()
    sample_colors = []
    step_x = max(1, width // 18)
    step_y = max(1, height // 12)
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            sample_colors.append(image.pixelColor(x, y).rgb())

    unique_colors = len(set(sample_colors))
    nonwhite_samples = sum(
        1 for color in sample_colors if color != QColor("white").rgb()
    )
    if width < 1000 or height < 600 or unique_colors < 5 or nonwhite_samples < 20:
        raise RuntimeError(
            "Header screenshot did not pass layout checks: "
            f"size={width}x{height}, unique={unique_colors}, "
            f"nonwhite={nonwhite_samples}"
        )

    print(f"screenshot={output_path}")
    print(f"labels={actual}")
    print(f"size={width}x{height}")
    print(f"unique_sample_colors={unique_colors}")
    print(f"nonwhite_samples={nonwhite_samples}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())