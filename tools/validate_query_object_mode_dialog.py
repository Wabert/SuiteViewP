"""Render the New Query Object mode chooser for visual validation."""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from suiteview.audit.audit_window import QueryObjectModeDialog


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyle("Fusion")

    dialog = QueryObjectModeDialog()
    dialog.show()
    app.processEvents()

    output_dir = PROJECT_ROOT / "docs" / "audit" / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "query_object_mode_dialog.png"
    pixmap = dialog.grab()
    if pixmap.isNull():
        raise RuntimeError("Mode chooser screenshot was blank/null")
    pixmap.save(str(output_path))

    image = pixmap.toImage()
    width = image.width()
    height = image.height()
    sample_colors = []
    step_x = max(1, width // 12)
    step_y = max(1, height // 8)
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            sample_colors.append(image.pixelColor(x, y).rgb())

    unique_colors = len(set(sample_colors))
    nonwhite_samples = sum(
        1 for color in sample_colors if color != QColor("white").rgb()
    )
    if width < 500 or height < 220 or unique_colors < 4 or nonwhite_samples < 20:
        raise RuntimeError(
            "Mode chooser screenshot did not pass layout checks: "
            f"size={width}x{height}, unique={unique_colors}, nonwhite={nonwhite_samples}"
        )

    print(f"screenshot={output_path}")
    print(f"size={width}x{height}")
    print(f"unique_sample_colors={unique_colors}")
    print(f"nonwhite_samples={nonwhite_samples}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
