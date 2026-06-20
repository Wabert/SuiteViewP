"""Diagnose the FilterTableView freeze-pane alignment offscreen.

Builds a ledger-style FilterTableView with frozen columns and a wide DataFrame,
shows it at a fixed size, then reports the geometry that governs row alignment:
the two viewports' heights/positions, the main horizontal scrollbar, and the
reserved frozen bottom inset.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PyQt6.QtWidgets import QApplication


def main() -> None:
    app = QApplication.instance() or QApplication([])
    from suiteview.ui.widgets.filter_table_view import FilterTableView

    grid = FilterTableView()
    grid.apply_ledger_style()
    grid.set_search_visible(False)
    grid.set_sort_enabled(False)
    grid.set_filtering_enabled(False)
    grid.set_frozen_column_count(4)

    df = pd.DataFrame({f"Col{i:02d}": list(range(60)) for i in range(20)})
    grid.set_dataframe(df)
    grid.autofit_columns_to_data()
    grid.resize(700, 320)
    grid.show()
    app.processEvents()
    app.processEvents()

    main_v = grid.table_view
    frozen_v = grid.frozen_table_view
    h_sb = main_v.horizontalScrollBar()

    def vp(view):
        r = view.viewport().rect()
        gp = view.viewport().mapTo(grid, r.topLeft())
        bottom = view.viewport().mapTo(grid, r.bottomLeft())
        return {"height": r.height(), "top_y": gp.y(), "bottom_y": bottom.y()}

    report = {
        "main_viewport": vp(main_v),
        "frozen_viewport": vp(frozen_v),
        "main_view_height": main_v.height(),
        "frozen_view_height": frozen_v.height(),
        "main_hscroll_visible": h_sb.isVisible(),
        "main_hscroll_needed": h_sb.maximum() > h_sb.minimum(),
        "main_hscroll_sizehint_h": h_sb.sizeHint().height(),
        "frozen_bottom_inset": getattr(grid, "_frozen_bottom_inset", None),
        "main_scroll_mode": str(main_v.verticalScrollMode()),
        "frozen_scroll_mode": str(frozen_v.verticalScrollMode()),
        "row_height_main": main_v.rowHeight(0) if main_v.model() else None,
        "row_height_frozen": frozen_v.rowHeight(0) if frozen_v.model() else None,
        "viewport_bottoms_aligned": vp(main_v)["bottom_y"] == vp(frozen_v)["bottom_y"],
    }
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
