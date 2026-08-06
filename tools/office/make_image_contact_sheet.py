"""Create a labeled contact sheet for images in a directory.

Useful for quickly identifying a sequence of extracted policy-record
screenshots without opening each image individually.

Usage:
    venv\\Scripts\\python.exe tools/office/make_image_contact_sheet.py ^
        "C:\\tmp\\policy-segments" "C:\\tmp\\policy-segments\\contact.png"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtWidgets import QApplication


def main() -> int:
    source = Path(sys.argv[1]).resolve()
    destination = Path(sys.argv[2]).resolve()
    images = sorted(
        path for path in source.iterdir()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}
        and path.resolve() != destination
    )
    if not images:
        raise RuntimeError(f"No images found in {source}")

    app = QApplication.instance() or QApplication([])
    columns = 3
    cell_width = 420
    cell_height = 275
    label_height = 24
    rows = (len(images) + columns - 1) // columns
    sheet = QImage(
        columns * cell_width,
        rows * cell_height,
        QImage.Format.Format_RGB32,
    )
    sheet.fill(QColor("white"))

    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    for index, path in enumerate(images):
        row, column = divmod(index, columns)
        x = column * cell_width
        y = row * cell_height
        painter.setPen(QColor("#333333"))
        painter.drawText(
            QRect(x + 6, y, cell_width - 12, label_height),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            path.name,
        )

        image = QImage(str(path))
        bounds = QRect(
            x + 6,
            y + label_height,
            cell_width - 12,
            cell_height - label_height - 6,
        )
        scaled = image.scaled(
            bounds.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        image_x = bounds.x() + (bounds.width() - scaled.width()) // 2
        image_y = bounds.y() + (bounds.height() - scaled.height()) // 2
        painter.drawImage(image_x, image_y, scaled)
        painter.setPen(QColor("#BBBBBB"))
        painter.drawRect(bounds)
    painter.end()

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not sheet.save(str(destination)):
        raise RuntimeError(f"Could not save {destination}")
    app.processEvents()
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
