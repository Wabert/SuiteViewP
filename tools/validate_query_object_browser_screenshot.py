"""Render the Query Object Browser and save a screenshot for visual validation."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from suiteview.audit.saved_query import SavedQuery
from suiteview.audit.query_object import (
    adhoc_source_object,
    cyberlife_query_object,
    object_from_saved_query,
)
from suiteview.audit.query_object_store import save_object
from suiteview.audit.query_object_viewer_window import QueryObjectViewerWindow


def main() -> int:
    store_dir = Path(tempfile.gettempdir()) / "suiteview_qobj_visual_validation"
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store_dir.mkdir(parents=True, exist_ok=True)
    os.environ["SUITEVIEW_QUERY_OBJECTS_DIR"] = str(store_dir)

    save_object(cyberlife_query_object(
        "Cyberlife Visual Validation",
        sql="SELECT TCH_POL_ID, CK_CMP_CD FROM DB2TAB.LH_BAS_POL",
        dsn="CKPR_DSN",
        region="CKPR",
        system_code="I",
        criteria={"status": "Active"},
        result_columns=["TCH_POL_ID", "CK_CMP_CD"],
        column_types={"TCH_POL_ID": "VARCHAR(20)", "CK_CMP_CD": "CHAR(2)"},
    ))
    save_object(adhoc_source_object(
        "Loose CSV Visual Validation",
        source_type="csv",
        metadata={"path": "C:/temp/loose.csv"},
        columns=["Policy", "Amount", "RunDate"],
        column_types={"Policy": "TEXT", "Amount": "DECIMAL", "RunDate": "DATE"},
    ))
    save_object(object_from_saved_query(SavedQuery(
        name="QDesigner Role Validation",
        source_group="Visual Validation",
        dsn="CKPR_DSN",
        tables=["DB2TAB.LH_BAS_POL", "DB2TAB.LH_COV_PHA"],
        sql="SELECT TCH_POL_ID FROM DB2TAB.LH_BAS_POL",
        config={
            "select_tab": {
                "display_all": False,
                "fields": [
                    {
                        "field_key": "DB2TAB.LH_BAS_POL.TCH_POL_ID",
                        "display_name": "Policy Number",
                    }
                ],
            },
            "tabs": [
                {
                    "grid": {
                        "fields": {
                            "DB2TAB.LH_BAS_POL.CK_CMP_CD": {
                                "label_text": "Company",
                                "mode": 0,
                            }
                        }
                    }
                }
            ],
            "joins_tab": {
                "cards": [
                    {
                        "card_id": "join-1",
                        "left_table": "DB2TAB.LH_BAS_POL",
                        "right_table": "DB2TAB.LH_COV_PHA",
                        "on_conditions": [{"left": "TCH_POL_ID", "right": "POL_ID"}],
                    }
                ]
            },
        },
    )))

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyle("Fusion")

    window = QueryObjectViewerWindow()
    window.resize(1120, 620)
    window.show()
    app.processEvents()
    window.refresh()
    app.processEvents()

    output_dir = PROJECT_ROOT / "docs" / "audit" / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    captures = []

    qdesigner_item = _find_tree_item(window, "QDesigner Role Validation")
    if qdesigner_item is None:
        raise RuntimeError("QDesigner validation object was not visible in the tree")
    window.tree.setCurrentItem(qdesigner_item)
    window.tabs.setCurrentIndex(0)
    app.processEvents()
    captures.append(_capture(window, output_dir / "query_object_browser_sources.png"))
    window.tabs.setCurrentIndex(1)
    app.processEvents()
    captures.append(_capture(window, output_dir / "query_object_browser_outputs.png"))
    window.tabs.setCurrentIndex(2)
    app.processEvents()
    captures.append(_capture(window, output_dir / "query_object_browser_inputs.png"))
    window.tabs.setCurrentIndex(3)
    app.processEvents()
    captures.append(_capture(window, output_dir / "query_object_browser_joins.png"))

    cyberlife_item = _find_tree_item(window, "Cyberlife Visual Validation")
    if cyberlife_item is None:
        raise RuntimeError("Cyberlife validation object was not visible in the tree")
    window.tree.setCurrentItem(cyberlife_item)
    window.tabs.setCurrentIndex(5)
    app.processEvents()
    captures.append(_capture(window, output_dir / "query_object_browser_cyberlife_sql.png"))

    for capture in captures:
        print(
            f"screenshot={capture['path']}; size={capture['width']}x{capture['height']}; "
            f"unique_sample_colors={capture['unique_colors']}; "
            f"nonwhite_samples={capture['nonwhite_samples']}"
        )
    print(f"store={store_dir}")
    return 0


def _capture(window: QueryObjectViewerWindow, output_path: Path) -> dict[str, object]:
    pixmap = window.grab()
    if pixmap.isNull():
        raise RuntimeError(f"Window screenshot was blank/null: {output_path}")
    pixmap.save(str(output_path))

    image = pixmap.toImage()
    width = image.width()
    height = image.height()
    sample_colors = []
    step_x = max(1, width // 16)
    step_y = max(1, height // 12)
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            sample_colors.append(image.pixelColor(x, y).rgb())

    unique_colors = len(set(sample_colors))
    nonwhite_samples = sum(
        1 for color in sample_colors if color != QColor("white").rgb()
    )
    if width < 700 or height < 400 or unique_colors < 4 or nonwhite_samples < 10:
        raise RuntimeError(
            "Screenshot did not pass nonblank layout checks: "
            f"path={output_path}, size={width}x{height}, "
            f"unique={unique_colors}, nonwhite={nonwhite_samples}"
        )
    return {
        "path": output_path,
        "width": width,
        "height": height,
        "unique_colors": unique_colors,
        "nonwhite_samples": nonwhite_samples,
    }


def _find_tree_item(window: QueryObjectViewerWindow, text: str):
    for group_index in range(window.tree.topLevelItemCount()):
        parent = window.tree.topLevelItem(group_index)
        for child_index in range(parent.childCount()):
            child = parent.child(child_index)
            if child.text(0) == text:
                return child
    return None


if __name__ == "__main__":
    raise SystemExit(main())