"""Details panel construction for the SuiteView File Explorer."""
from __future__ import annotations

import logging

from suiteview.file_nav.file_explorer_imports import *
from suiteview.file_nav.file_explorer_widgets import DropTreeView, FileSortProxyModel, NoFocusDelegate

logger = logging.getLogger(__name__)


_HEADER_STYLE = """
QWidget {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #1E5BA8, stop:0.5 #0D3A7A, stop:1 #082B5C);
    border: none;
}
"""

_DETAILS_SEARCH_STYLE = """
QLineEdit {
    padding: 3px 8px;
    border: 1px solid #D4A017;
    border-radius: 3px;
    background: white;
    color: #1A3A6E;
}
QLineEdit:focus {
    border: 2px solid #FFD700;
}
"""

_DEPTH_COMBO_STYLE = """
QComboBox {
    padding: 2px 4px;
    border: 1px solid #D4A017;
    border-radius: 3px;
    background: white;
    color: #1A3A6E;
    font-size: 9pt;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #1A3A6E;
    margin-right: 5px;
}
QComboBox QAbstractItemView {
    border: 2px solid #2563EB;
    background-color: white;
    selection-background-color: #C9DAFF;
    selection-color: #1A3A6E;
}
"""

_DEPTH_TOGGLE_STYLE = """
QPushButton {
    background-color: #E0ECFF;
    border: 1px solid #2563EB;
    border-radius: 3px;
    padding: 2px 6px;
    font-size: 9pt;
    color: #1A3A6E;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #C9DAFF;
}
"""

_DEPTH_HOME_STYLE = """
QPushButton {
    background-color: #FFA500;
    border: 1px solid #D4A017;
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 12pt;
}
QPushButton:hover {
    background-color: #FFB84D;
    border-color: #FFD700;
}
"""

_EXPORT_BUTTON_STYLE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #2A8A2A, stop:1 #1A6A1A);
    border: 1px solid #D4A017;
    border-radius: 3px;
    font-size: 12pt;
    color: #FFFFFF;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #3A9A3A, stop:1 #2A7A2A);
    border-color: #FFD700;
}
"""

_DETAILS_VIEW_STYLE = """
QTreeView {
    outline: none;
    border: none;
    background-color: transparent;
}
QTreeView::item {
    padding: 2px 6px;
    margin: 0px;
    border: none;
    border-radius: 0px;
    background-color: transparent;
    min-height: 20px;
    outline: none;
}
QTreeView::item:hover {
    background-color: #C8DCF0;
    border: none;
    outline: none;
}
QTreeView::item:selected {
    background-color: #B0C8E8;
    color: #0A1E5E;
    border: none;
    outline: none;
}
QTreeView::item:selected:!active {
    background-color: #B0C8E8;
    color: #0A1E5E;
    border: none;
    outline: none;
}
QTreeView::item:focus {
    border: none;
    outline: none;
}
QTreeView:focus {
    border: none;
    outline: none;
}
"""

_DETAILS_HEADER_STYLE = """
QHeaderView {
    background-color: #E0E0E0;
}
QHeaderView::section {
    background-color: #E0E0E0;
    padding: 1px 6px;
    font-size: 11px;
    font-weight: 600;
    color: #333333;
    border: none;
    border-right: 1px solid #C0C0C0;
}
QHeaderView::section:last {
    border-right: none;
}
"""

_FOOTER_STYLE = """
QLabel {
    background-color: #E0E0E0;
    padding: 2px 8px;
    font-size: 9pt;
    color: #555555;
    border: none;
    border-top: 1px solid #A0B8D8;
}
"""


class FileExplorerDetailsPanelMixin:
    def create_details_panel(self):
        """Create the details view panel (right side) for folder contents."""
        widget = QWidget()
        widget.setStyleSheet("background-color: #CCE5F8;")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._create_details_header())
        self._create_details_view()
        layout.addWidget(self.details_view)
        self._create_details_footer(layout)
        return widget

    def _create_details_header(self):
        header_widget = QWidget()
        header_widget.setStyleSheet(_HEADER_STYLE)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 5, 8, 5)
        header_layout.setSpacing(8)

        header_layout.addWidget(self._create_details_search_box())
        header_layout.addWidget(self._create_depth_level_combo())
        header_layout.addWidget(self._create_depth_toggle_button())
        header_layout.addWidget(self._create_depth_home_button())
        header_layout.addWidget(self._create_details_header_label())
        header_layout.addStretch()
        header_layout.addWidget(self._create_export_button())
        return header_widget

    def _create_details_search_box(self):
        self.details_search = QLineEdit()
        self.details_search.setPlaceholderText("Search...")
        self.details_search.setClearButtonEnabled(True)
        self.details_search.setMaximumWidth(240)
        self.details_search.setMaximumHeight(24)
        self.details_search.setToolTip(
            "Search by name, or use length formulas:\n"
            "  =(len=9)   - exactly 9 characters\n"
            "  =(len>10)  - more than 10 characters\n"
            "  =(len<5)   - less than 5 characters\n"
            "  =(len>=8)  - 8 or more characters\n"
            "  =(len<=12) - 12 or fewer characters\n"
            "  =(len!=7)  - not 7 characters"
        )
        self.details_search.setStyleSheet(_DETAILS_SEARCH_STYLE)
        self.details_search.textChanged.connect(self.on_details_search_changed)
        return self.details_search

    def _create_depth_level_combo(self):
        self.depth_level_combo = QComboBox()
        self.depth_level_combo.addItems(["1", "2", "3", "4", "5", "6", "7", "8", "Max"])
        self.depth_level_combo.setCurrentText("1")
        self.depth_level_combo.setMaximumWidth(60)
        self.depth_level_combo.setMaximumHeight(24)
        self.depth_level_combo.setToolTip("Depth level for subfolder search")
        self.depth_level_combo.setStyleSheet(_DEPTH_COMBO_STYLE)
        self.depth_level_combo.currentTextChanged.connect(self.on_depth_level_changed)
        return self.depth_level_combo

    def _create_depth_toggle_button(self):
        self.depth_toggle_btn = QPushButton("Off")
        self.depth_toggle_btn.setCheckable(False)
        self.depth_toggle_btn.setMaximumWidth(50)
        self.depth_toggle_btn.setMaximumHeight(24)
        self.depth_toggle_btn.setToolTip("Depth search is off")
        self.depth_toggle_btn.setStyleSheet(_DEPTH_TOGGLE_STYLE)
        self.depth_toggle_btn.clicked.connect(self.toggle_depth_search)
        return self.depth_toggle_btn

    def _create_depth_home_button(self):
        self.depth_home_btn = QPushButton("🏠")
        self.depth_home_btn.setFixedSize(26, 24)
        self.depth_home_btn.setToolTip("Go to depth search root folder")
        self.depth_home_btn.setStyleSheet(_DEPTH_HOME_STYLE)
        self.depth_home_btn.clicked.connect(self.go_to_depth_search_home)
        self.depth_home_btn.hide()
        return self.depth_home_btn

    def _create_details_header_label(self):
        self.details_header = QLabel("Contents")
        self.details_header.setStyleSheet(
            """
            QLabel {
                font-weight: 600;
                font-size: 10pt;
                color: #D4A017;
                background: transparent;
            }
            """
        )
        return self.details_header

    def _create_export_button(self):
        self.export_btn = QPushButton()
        self.export_btn.setText("📊")
        self.export_btn.setToolTip("Export details view to Excel")
        self.export_btn.setFixedSize(26, 26)
        self.export_btn.setStyleSheet(_EXPORT_BUTTON_STYLE)
        self.export_btn.clicked.connect(self.export_details_to_excel)
        return self.export_btn

    def _create_details_view(self):
        self.details_view = DropTreeView()
        self.details_view.set_file_explorer(self)
        self.details_view.files_dropped.connect(self.handle_dropped_files)
        self.details_view.setAnimated(False)
        self.details_view.setRootIsDecorated(False)
        self.details_view.setIndentation(0)
        self.details_view.setHeaderHidden(False)
        self.details_view.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self.details_view.setSortingEnabled(True)
        self.details_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.details_view.setDragEnabled(True)
        self.details_view.setDragDropMode(QTreeView.DragDropMode.DragDrop)
        self.details_view.setStyleSheet(_DETAILS_VIEW_STYLE)
        self.details_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.details_view.setFrameShape(QFrame.Shape.NoFrame)
        self.details_view.setItemDelegate(NoFocusDelegate(self.details_view))
        self.details_view.installEventFilter(self)

        self._create_details_model()
        self._configure_details_header()
        self._connect_details_view_signals()

    def _create_details_model(self):
        self.details_model = QStandardItemModel()
        self.details_model.setHorizontalHeaderLabels(['Name', 'Size', 'Type', 'Date Modified', 'Date Accessed'])
        self.details_model.itemChanged.connect(self.on_item_renamed)

        self.details_sort_proxy = FileSortProxyModel()
        self.details_sort_proxy.setSourceModel(self.details_model)
        self.details_sort_proxy.setFilterKeyColumn(0)
        self.details_sort_proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.details_view.setModel(self.details_sort_proxy)

    def _configure_details_header(self):
        header_view = self.details_view.header()
        for column in range(5):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header_view.setMinimumSectionSize(60)
        header_view.setDefaultSectionSize(100)
        header_view.setFixedHeight(22)
        header_view.setStyleSheet(_DETAILS_HEADER_STYLE)
        self.details_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        default_widths = [350, 100, 120, 150, 150]
        for col, default_width in enumerate(default_widths):
            width = self.column_widths.get(f'col_{col}', default_width)
            self.details_view.setColumnWidth(col, width)
        header_view.sectionResized.connect(self.on_column_resized)

    def _connect_details_view_signals(self):
        self.details_view.doubleClicked.connect(self.on_details_item_double_clicked)
        self.details_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.details_view.customContextMenuRequested.connect(self.show_details_context_menu)

    def _create_details_footer(self, layout):
        footer = QLabel("")
        footer.setStyleSheet(_FOOTER_STYLE)
        footer.setFixedHeight(20)
        layout.addWidget(footer)
        self.details_footer = footer
        self.details_sort_proxy.rowsInserted.connect(self.update_details_footer)
        self.details_sort_proxy.rowsRemoved.connect(self.update_details_footer)
        self.details_sort_proxy.modelReset.connect(self.update_details_footer)
