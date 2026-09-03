"""Check that a bookmark CategoryPopup uses the available screen height.

Builds a CategoryPopup with a synthetic item list, positions it at a few
y-offsets, and reports the resulting geometry plus whether the inner scroll
area would need a vertical scrollbar.

Usage:
    venv\\Scripts\\python.exe tools/app/test_category_popup_height.py [item_count]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QScrollArea

from suiteview.ui.widgets.bookmark_widgets import CategoryPopup


def main():
    item_count = int(sys.argv[1]) if len(sys.argv) > 1 else 30

    app = QApplication(sys.argv[:1])
    geo = app.primaryScreen().availableGeometry()

    items = [
        {'type': 'bookmark', 'name': f'Bookmark {i}', 'path': f'C:/tmp/file_{i}.txt'}
        for i in range(item_count)
    ]

    popup = CategoryPopup(
        category_name='__height_probe__',
        category_items=items,
        color='#A080C0',
    )

    results = []
    for y in (geo.top() + 40, geo.top() + geo.height() // 2, geo.bottom() - 120):
        pos = popup.fit_to_position(QPoint(geo.left() + 100, y))
        popup.move(pos)
        popup.show()
        app.processEvents()

        scroll = popup.findChild(QScrollArea)
        bar = scroll.verticalScrollBar()
        results.append({
            'requested_y': y,
            'actual_y': pos.y(),
            'height': popup.height(),
            'content_height': popup._content_height(),
            'bottom': pos.y() + popup.height(),
            'screen_bottom': geo.bottom(),
            'scrollbar_needed': bar.maximum() > bar.minimum(),
        })

    popup.hide()

    max_fit = geo.height() - 2 * CategoryPopup.POPUP_SCREEN_MARGIN
    ok = all(
        r['bottom'] <= r['screen_bottom']
        and (not r['scrollbar_needed'] or r['height'] >= max_fit - 2)
        for r in results
    )
    print(json.dumps({
        'item_count': item_count,
        'screen': {'top': geo.top(), 'bottom': geo.bottom(), 'height': geo.height()},
        'cases': results,
        'all_ok': ok,
    }, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
