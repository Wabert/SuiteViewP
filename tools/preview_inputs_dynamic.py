"""Render the dynamic Input tab's change sections to a PNG for visual checks.

Reproduces the add-row scenario: the Face Amount Change group gets a second
row (year 25 / 6000) so the − remove button's interaction with the New Face
field can be inspected.

Usage:
    venv\\Scripts\\python.exe tools/preview_inputs_dynamic.py [width]
Writes ~/.suiteview/inputs_dynamic_preview.png and prints the path.
"""
import json
import sys
from datetime import date
from pathlib import Path

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from suiteview.illustration.ui.inputs_dynamic import (  # noqa: E402
    DynamicInputsPanel, PolicyContext,
)
from suiteview.illustration.ui.styles import PURPLE_BG  # noqa: E402

OUT_PATH = Path.home() / ".suiteview" / "inputs_dynamic_preview.png"


def main():
    width = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
    app = QApplication(sys.argv)

    panel = DynamicInputsPanel()
    panel.setStyleSheet(f"background-color: {PURPLE_BG};")
    ctx = PolicyContext(
        issue_date=date(1996, 7, 15),
        issue_age=31,
        forecast_year=30,
        forecast_age=60,
        forecast_date=date(2026, 7, 15),
        maturity_age=95,
        default_mode="M",
        modal_premium=100.0,
    )
    panel._ctx = ctx
    for section in (panel.premium_section, panel.loan_section,
                    panel.withdrawal_section, panel.repayment_section,
                    panel.face_section, panel.dbo_section,
                    panel.rateclass_section, panel.table_section):
        section.set_context(ctx)

    # Mirror the screenshot: two face rows, second added via the ＋ path.
    face = panel.face_section
    first = face.rows()[0]
    first.year_edit.set_value(15)
    first.age_edit.set_value(45)
    first.amount_edit.set_value(45000, decimals=0)
    second = face.add_row()
    second.year_edit.set_value(25)
    second.age_edit.set_value(55)
    second.amount_edit.set_value(6000, decimals=0)

    squeeze = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    if squeeze:
        face.setFixedWidth(squeeze)
    panel.resize(width, 760)
    panel.show()
    app.processEvents()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    panel.grab().save(str(OUT_PATH))
    zoom = face.grab()
    zoom = zoom.scaled(zoom.width() * 3, zoom.height() * 3)
    zoom_path = OUT_PATH.with_name("inputs_dynamic_preview_face_zoom.png")
    zoom.save(str(zoom_path))
    geometry = {}
    for label, row in (("row1", first), ("row2", second)):
        geometry[label] = {
            "row": [row.x(), row.y(), row.width(), row.height()],
            "amount": [row.amount_edit.x(), row.amount_edit.width()],
            "remove": [row.remove_btn.x(), row.remove_btn.width(),
                       row.remove_btn.isVisible()],
        }
    print(json.dumps({"screenshot": str(OUT_PATH),
                      "size": [panel.width(), panel.height()],
                      "geometry": geometry}))
    app.quit()


if __name__ == "__main__":
    main()
