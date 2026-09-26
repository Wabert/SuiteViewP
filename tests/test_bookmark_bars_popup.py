"""Bookmark popup sizing without reading the user's saved bookmarks."""

from PyQt6.QtWidgets import QApplication, QScrollArea

from suiteview.taskbar_launcher.bookmark_bars_popup import BookmarkBarsPopup
from suiteview.ui.widgets import bookmark_data_manager


class _BookmarkManager:
    def __init__(self, item_count):
        self._items = [
            {
                "id": index,
                "type": "bookmark",
                "name": f"Link {index}",
                "path": f"https://example.com/{index}",
            }
            for index in range(item_count)
        ]

    def get_all_bar_ids(self):
        return [0]

    def get_bar_data(self, bar_id):
        return {"name": "Bookmark Bar 1", "items": self._items}


def test_bookmark_popup_expands_to_show_every_link(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        bookmark_data_manager,
        "get_bookmark_manager",
        lambda: _BookmarkManager(item_count=16),
    )

    popup = BookmarkBarsPopup(maximum_height=800)
    popup.show()
    app.processEvents()

    scroll = popup.findChild(QScrollArea)
    assert scroll is not None
    assert scroll.verticalScrollBar().maximum() == 0
    assert popup.height() == popup.sizeHint().height()

    popup.close()
