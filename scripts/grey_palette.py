"""Quick grey palette picker - run to see actual colors."""
import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt

GREYS = [
    (1, "#F8F8F8", "Near white"),
    (2, "#F0F0F0", "Default Windows bg"),
    (3, "#ECECEC", "Very light grey"),
    (4, "#E8E8E8", "Current setting"),
    (5, "#E4E4E4", "Previous setting"),
    (6, "#E0E0E0", "Light-medium"),
    (7, "#DCDCDC", "Gainsboro"),
    (8, "#D8D8D8", "Original dark"),
    (9, "#D0D0D0", "Medium grey"),
    (10, "#C8C8C8", "Silver-ish"),
    (11, "#C0C0C0", "Silver"),
    (12, "#B0B0B0", "Dark silver"),
]

app = QApplication(sys.argv)
win = QWidget()
win.setWindowTitle("Grey Palette Picker")
layout = QVBoxLayout(win)
layout.setSpacing(2)
layout.setContentsMargins(10, 10, 10, 10)

for num, hex_color, desc in GREYS:
    row = QHBoxLayout()
    row.setSpacing(8)

    swatch = QLabel()
    swatch.setFixedSize(200, 32)
    swatch.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #999;")

    label = QLabel(f"  {num:>2}.  {hex_color}  -  {desc}")
    label.setStyleSheet("font-size: 13px; font-family: Consolas;")
    label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    row.addWidget(swatch)
    row.addWidget(label, 1)
    layout.addLayout(row)

win.adjustSize()
win.show()
sys.exit(app.exec())
