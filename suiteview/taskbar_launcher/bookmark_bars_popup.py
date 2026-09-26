"""Bookmark bars popup used by the SuiteView compact bar."""

import logging

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from suiteview.ui.widgets.bookmark_data_manager import get_bookmark_manager
from suiteview.ui.widgets.bookmark_widgets import (
    CategoryButton,
    StandaloneBookmarkButton,
)

logger = logging.getLogger(__name__)

class BookmarkBarsPopup(QWidget):
    """
    Frameless popup that appears when the user right-clicks the SuiteView bar.
    Displays one vertical BookmarkContainer panel per configured bookmark bar,
    side-by-side, so every bar and its categories/bookmarks are visible at once.
    Closes when the user clicks outside the popup or activates a bookmark.
    """
    # Emitted with the path when a bookmark is clicked
    bookmark_activated = pyqtSignal(str)

    def __init__(self, parent_bar=None, maximum_height=None):
        super().__init__(parent=None)  # Top-level so it floats above everything
        self._parent_bar = parent_bar
        self._containers = []  # Keep refs so they don't get GC'd
        self._maximum_height = maximum_height

        # Use Tool | FramelessWindowHint | WindowStaysOnTopHint instead of
        # Qt.WindowType.Popup.  The Popup flag auto-closes but it also
        # re-delivers the dismissing click to whatever Qt widget is underneath,
        # which caused a CategoryButton on the SuiteView bar to open its
        # popup immediately after the bookmark popup closed.
        # Instead we use an application-level event filter (below) to close
        # the popup when the user clicks outside it.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self._build_ui()

        # Install an application-level event filter to detect outside clicks.
        # This is the same mechanism used by QMenu and QComboBox dropdowns
        # when NOT using the Popup window flag.
        QApplication.instance().installEventFilter(self)

    def _build_ui(self):
        """Build the popup UI: one panel per bar, populated with bookmark buttons.

        We intentionally do NOT create new BookmarkContainer instances here because
        doing so would:
        1. Overwrite the existing registry entries for each bar_id, breaking
           cross-bar drag-and-drop on the live containers.
        2. Mutate the stored orientation in the data manager for bar 0 (horizontal)
           since we want vertical orientation in the popup.

        Instead we read raw data from the BookmarkDataManager and build lightweight
        read-only panels using StandaloneBookmarkButton and CategoryButton directly.
        """

        manager = get_bookmark_manager()
        bar_ids = manager.get_all_bar_ids()

        # ── Outer styling ────────────────────────────────────────────────────
        self.setStyleSheet("""
            BookmarkBarsPopup {
                background: #0D3A7A;
                border: 2px solid #D4A017;
                border-radius: 6px;
            }
        """)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        outer_layout.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────────
        header = QLabel("📌  Bookmarks")
        header.setStyleSheet("""
            QLabel {
                color: #D4A017;
                font-size: 11pt;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
                background: transparent;
                padding: 4px 8px 6px 8px;
                border-bottom: 1px solid #D4A017;
            }
        """)
        outer_layout.addWidget(header)

        # ── Panel row ────────────────────────────────────────────────────────
        panels_frame = QFrame()
        panels_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        panels_layout = QHBoxLayout(panels_frame)
        panels_layout.setContentsMargins(4, 6, 4, 4)
        panels_layout.setSpacing(10)

        PANEL_WIDTH = 220
        _panels_built = 0
        panels = []
        desired_panel_height = 0

        for bar_id in bar_ids:
            bar_data = manager.get_bar_data(bar_id)
            items = bar_data.get('items', [])

            # Skip bars with no items
            if not items:
                continue

            bar_name = bar_data.get('name', f"Bookmark Bar {bar_id + 1}")

            # ── Per-bar outer panel ──────────────────────────────────────────
            panel = QFrame()
            panel.setFixedWidth(PANEL_WIDTH)
            panel.setStyleSheet("""
                QFrame {
                    background: #9EC8EE;
                    border: 1px solid #5A9FD8;
                    border-radius: 5px;
                }
            """)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(0)

            # Bar title
            title_lbl = QLabel(bar_name)
            title_lbl.setStyleSheet("""
                QLabel {
                    color: #FFD700;
                    font-size: 9pt;
                    font-weight: bold;
                    font-family: 'Segoe UI', sans-serif;
                    background: #0D3A7A;
                    padding: 4px 8px;
                    border-bottom: 1px solid #3A7DC8;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    border-bottom-left-radius: 0px;
                    border-bottom-right-radius: 0px;
                }
            """)
            panel_layout.addWidget(title_lbl)

            # Scroll area for items
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("""
                QScrollArea { background: transparent; border: none; }
                QScrollArea > QWidget > QWidget { background: transparent; }
                QScrollBar:vertical {
                    background: #0D3A7A;
                    width: 6px;
                    margin: 0;
                    border-radius: 3px;
                }
                QScrollBar::handle:vertical {
                    background: #D4A017;
                    border-radius: 3px;
                    min-height: 20px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            """)

            # Items container
            items_widget = QWidget()
            items_widget.setStyleSheet("background: transparent;")
            items_layout = QVBoxLayout(items_widget)
            items_layout.setContentsMargins(4, 4, 4, 4)
            items_layout.setSpacing(2)
            items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

            # ── Populate items ───────────────────────────────────────────────
            for idx, item_data in enumerate(items):
                item_type = item_data.get('type')

                if item_type == 'bookmark':
                    bm = {
                        'name': item_data.get('name', ''),
                        'path': item_data.get('path', ''),
                        'id': item_data.get('id'),
                    }
                    btn = StandaloneBookmarkButton(
                        bookmark_data=bm,
                        item_index=idx,
                        parent=items_widget,
                        container=None,
                        orientation='vertical'
                    )
                    btn.clicked_path.connect(self.bookmark_activated.emit)
                    # Also close the popup on ANY click (including URLs, which the
                    # button handles internally without emitting clicked_path).
                    btn.clicked.connect(self.close)
                    items_layout.addWidget(btn)

                elif item_type == 'category':
                    cat_items = []
                    subcats = []
                    for child in item_data.get('items', []):
                        if child.get('type') == 'bookmark':
                            cat_items.append({
                                'name': child.get('name', ''),
                                'path': child.get('path', ''),
                                'id': child.get('id'),
                            })
                        elif child.get('type') == 'category':
                            subcats.append(child.get('name', ''))

                    cat_btn = CategoryButton(
                        category_name=item_data.get('name', ''),
                        category_items=cat_items,
                        subcategories=subcats,
                        item_index=idx,
                        parent=items_widget,
                        data_manager=None,    # read-only popup — no editing
                        source_bar_id=bar_id,
                        orientation='vertical',
                        color=item_data.get('color'),
                        category_id=item_data.get('id'),
                    )
                    cat_btn.item_clicked.connect(self.bookmark_activated.emit)
                    items_layout.addWidget(cat_btn)

            items_layout.addStretch()
            scroll.setWidget(items_widget)
            panel_layout.addWidget(scroll)

            panels_layout.addWidget(panel)
            panels.append(panel)
            desired_panel_height = max(
                desired_panel_height,
                title_lbl.sizeHint().height()
                + items_layout.sizeHint().height()
                + (panel.frameWidth() * 2),
            )
            _panels_built += 1

        if panels:
            popup_chrome_height = (
                outer_layout.contentsMargins().top()
                + outer_layout.contentsMargins().bottom()
                + header.sizeHint().height()
                + panels_layout.contentsMargins().top()
                + panels_layout.contentsMargins().bottom()
            )
            available_panel_height = desired_panel_height
            if self._maximum_height is not None:
                available_panel_height = max(
                    120, self._maximum_height - popup_chrome_height
                )
            panel_height = min(desired_panel_height, available_panel_height)
            for panel in panels:
                panel.setFixedHeight(panel_height)

        outer_layout.addWidget(panels_frame)

        # ── Fallback: no bookmarks ───────────────────────────────────────────
        if _panels_built == 0:
            placeholder = QLabel("No bookmarks yet.\nRight-click a folder in SuiteView\nto add bookmarks.")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet("""
                QLabel {
                    color: #A0B8D8;
                    font-size: 10pt;
                    font-style: italic;
                    font-family: 'Segoe UI', sans-serif;
                    padding: 28px;
                }
            """)
            outer_layout.addWidget(placeholder)

        self.adjustSize()

    def eventFilter(self, obj, event):
        """Close the popup when the user clicks outside it and all its child popups."""
        if event.type() == QEvent.Type.MouseButtonPress:
            # Get global click position
            try:
                global_pos = event.globalPosition().toPoint()
            except AttributeError:
                global_pos = event.globalPos()

            # Click is inside our own window — keep open
            if self.geometry().contains(global_pos):
                return False

            # Click might be inside a CategoryPopup opened from one of our
            # CategoryButtons (those float as separate windows but have a parent
            # widget, so they appear in allWidgets(), not topLevelWidgets()).
            from suiteview.ui.widgets.bookmark_widgets import CategoryPopup
            for widget in QApplication.allWidgets():
                if isinstance(widget, CategoryPopup) and widget.isVisible():
                    if widget.geometry().contains(global_pos):
                        return False  # Click inside a child category popup — stay open

            # Genuinely outside — close
            QApplication.instance().removeEventFilter(self)
            self.close()
            if self._parent_bar is not None:
                try:
                    self._parent_bar._bookmark_popup = None
                except Exception:
                    logger.debug("Could not clear parent bookmark popup reference", exc_info=True)

        return False  # Never consume the event

    def closeEvent(self, event):
        """Remove event filter on close."""
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:
            logger.debug("Could not remove bookmark popup event filter", exc_info=True)
        super().closeEvent(event)

    def changeEvent(self, event):
        """Close when the app loses OS-level activation (click on desktop / taskbar / other app)."""
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            # Don't close if a CategoryPopup just took activation — the user
            # may be clicking a bookmark inside one of our category panels.
            from suiteview.ui.widgets.bookmark_widgets import CategoryPopup
            active_win = QApplication.activeWindow()
            if not isinstance(active_win, CategoryPopup):
                QApplication.instance().removeEventFilter(self)
                if self._parent_bar is not None:
                    try:
                        self._parent_bar._bookmark_popup = None
                    except Exception:
                        logger.debug("Could not clear parent bookmark popup reference", exc_info=True)
                self.close()
        super().changeEvent(event)

    def paintEvent(self, event):
        """Draw blue/gold border around the popup."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor("#D4A017"), 2))
        painter.setBrush(QColor("#0D3A7A"))
        painter.drawRoundedRect(r, 5, 5)
        painter.end()
