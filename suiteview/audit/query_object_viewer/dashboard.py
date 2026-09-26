"""Data-source dashboard widget for QueryObject Viewer."""
from __future__ import annotations

from .common import *  # noqa: F401,F403 - private split module shares viewer globals.
from .widgets import _FileDropTable

class _SourceDashboard(QWidget):
    """Detail view AND editor for a Data Source — a source dashboard.

    A data source is a thing you *connect to* (a DSN, an Access file, a File
    Source), so this surfaces its identity, reachability (health), connection
    setup, the tables it exposes, their columns, and which Query Objects use it
    — never query-only tabs (outputs / joins / SQL).

    For **File Sources** this is also the single canonical screen used to add,
    edit, and view: the Setup name/description and the Columns (name + type) are
    editable in place, files can be dropped/added on the Tables tab, and a Save
    button persists the draft. ODBC / Access stay read-only here (they edit via a
    small registration dialog). The window owns all data extraction, the
    ``FileDataSource`` mutation, and persistence; this widget holds only the
    draft and emits intent (``save_requested`` / ``add_files_requested`` / …).
    """

    preview_requested = pyqtSignal(str, int)      # table name, row count
    remove_table_requested = pyqtSignal(str)      # table name
    open_table_folder_requested = pyqtSignal(str) # file path of that table
    save_requested = pyqtSignal()                 # persist the editable draft
    add_files_requested = pyqtSignal(list)        # member file paths to add
    pick_files_requested = pyqtSignal()           # open a file picker to add members
    bulk_columns_requested = pyqtSignal()         # open the multi-line column-spec box

    def __init__(self, parent=None):
        super().__init__(parent)
        self._editable = False     # File Source edit mode (vs read-only ODBC/Access)
        self._loading = False      # suppress dirty marking during programmatic fill
        self._dirty = False
        self._names_editable = True
        self.setStyleSheet("QWidget { background: #F0F0F0; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: #FAFBFD; border: 1px solid #C9D8EA; }"
            "QLabel { border: none; background: transparent; }")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(8, 6, 8, 6)
        hlay.setSpacing(8)

        self.lbl_name = QLabel("")
        self.lbl_name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_name.setStyleSheet("color: #1E5BA8; border: none; background: transparent;")
        hlay.addWidget(self.lbl_name)

        self.lbl_badge = QLabel("")
        self.lbl_badge.setFont(_FONT_SMALL)
        self.lbl_badge.setVisible(False)
        hlay.addWidget(self.lbl_badge)

        self.lbl_health = QLabel("")
        self.lbl_health.setFont(_FONT_SMALL)
        self.lbl_health.setVisible(False)
        hlay.addWidget(self.lbl_health)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT_SMALL)
        self.lbl_status.setStyleSheet("color: #6B7280; border: none; background: transparent;")
        hlay.addWidget(self.lbl_status)

        hlay.addStretch(1)

        self._add_header_actions(hlay)
        root.addWidget(header)

        # ── Overview tab: Setup and Columns side by side ───────────────────
        # Each side is a stack: read-only StyledInfoTableGroup (ODBC/Access) OR
        # an editable widget (File Source). set_editable() picks the page.
        self.grp_setup = StyledInfoTableGroup("Setup", show_info=False)
        self.grp_columns = StyledInfoTableGroup("Columns", show_info=False, filterable=True)
        self.grp_usedby = StyledInfoTableGroup("Used by", show_info=False)
        for grp in (self.grp_setup, self.grp_columns, self.grp_usedby):
            grp.setStyleSheet(_DASHBOARD_GROUP_STYLE)
            _reskin_info_table_blue(grp)

        self.setup_stack = QStackedWidget()
        self.setup_stack.addWidget(self.grp_setup)          # 0 read-only
        self.setup_stack.addWidget(self._build_setup_editor())  # 1 editable
        self.columns_stack = QStackedWidget()
        self.columns_stack.addWidget(self.grp_columns)      # 0 read-only
        self.columns_stack.addWidget(self._build_columns_editor())  # 1 editable

        overview = QSplitter(Qt.Orientation.Horizontal)
        overview.setChildrenCollapsible(False)
        overview.setHandleWidth(4)
        overview.addWidget(self.setup_stack)
        overview.addWidget(self.columns_stack)
        overview.setSizes([420, 420])

        self._panels = {
            "setup": self.grp_setup,
            "columns": self.grp_columns,
            "usedby": self.grp_usedby,
        }

        # ── Tables tab: table list (top) + a row-count preview (bottom) ──────
        self.tables_list = _FileDropTable(0, 3)
        self.tables_list.setHorizontalHeaderLabels(["Table", "Status", "File"])
        self.tables_list.verticalHeader().setVisible(False)
        self.tables_list.verticalHeader().setDefaultSectionSize(19)
        self.tables_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tables_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tables_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tables_list.setFont(_FONT)
        self.tables_list.horizontalHeader().setStretchLastSection(True)
        self.tables_list.setStyleSheet(
            "QTableWidget { background: white; border: none; gridline-color: #EEF2F7; }"
            "QTableWidget::item { padding: 0px 4px; }"
            "QTableWidget::item:selected { background: #DCEAFB; color: #0D3A7A; }"
            "QHeaderView::section { background: #E8F0FB; font-weight: bold;"
            " font-size: 8pt; border: 1px solid #C0C0C0; padding: 1px 4px; }")
        self.tables_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tables_list.customContextMenuRequested.connect(self._on_tables_context_menu)
        self.tables_list.itemDoubleClicked.connect(lambda *_: self._on_preview_clicked())
        self.tables_list.files_dropped.connect(self.add_files_requested.emit)

        tables_box = QGroupBox("Tables")
        tables_box.setStyleSheet(_DASHBOARD_GROUP_STYLE)
        tb_lay = QVBoxLayout(tables_box)
        tb_lay.setContentsMargins(6, 16, 6, 4)
        tb_lay.setSpacing(2)
        add_row = QHBoxLayout()
        self.btn_add_files = QPushButton("Add File(s)…")
        self.btn_add_files.setFont(_FONT_BOLD)
        self.btn_add_files.setFixedHeight(22)
        self.btn_add_files.setStyleSheet(_BTN_STYLE)
        self.btn_add_files.clicked.connect(self.pick_files_requested.emit)
        add_row.addWidget(self.btn_add_files)
        add_row.addStretch(1)
        self.btn_preview = QPushButton("Preview")
        self.btn_preview.setFont(_FONT_BOLD)
        self.btn_preview.setFixedHeight(22)
        self.btn_preview.setStyleSheet(_BTN_STYLE)
        self.btn_preview.clicked.connect(self._on_preview_clicked)
        add_row.addWidget(self.btn_preview)
        tb_lay.addLayout(add_row)
        tb_lay.addWidget(self.tables_list, 1)
        self.lbl_tables_footnote = QLabel(
            "Right-click a table to copy its path, open its folder, or remove it.")
        self.lbl_tables_footnote.setFont(_FONT_SMALL)
        self.lbl_tables_footnote.setStyleSheet(
            "color: #6B7280; font-style: italic; border: none; background: transparent;")
        tb_lay.addWidget(self.lbl_tables_footnote)

        used_by_page = QWidget()
        ub_lay = QVBoxLayout(used_by_page)
        ub_lay.setContentsMargins(2, 2, 2, 2)
        ub_lay.addWidget(self.grp_usedby)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #1E5BA8; background: #F0F0F0; }"
            "QTabBar::tab { background: #E8F0FB; color: #0D3A7A; border: 1px solid #A0C4E8;"
            " border-bottom: none; padding: 3px 12px; font-size: 8pt; }"
            "QTabBar::tab:selected { background: #F0F0F0; color: #1E5BA8; font-weight: bold; }")
        self.tabs.addTab(overview, "Overview")
        self.tabs.addTab(tables_box, "Tables")       # index 1 (toggled per source)
        self.tabs.addTab(used_by_page, "Used by")
        root.addWidget(self.tabs, 1)

        self._tables_rows: list[dict] = []
        self._tables_removable = False
        self._preview_dialog: "_TablePreviewDialog | None" = None
        self._preview_table_name = ""

    def _add_header_actions(self, layout: QHBoxLayout) -> None:
        self.btn_test = self._make_button("Test")
        self.btn_register = self._make_button("Register")
        self.btn_edit = self._make_button("Edit Setup")
        self.btn_edit_format = self._make_button("Edit Format")
        self.btn_edit_format.setToolTip(
            "Re-open the delimiter / fixed-width layout dialog and re-read the columns")
        self.btn_new_query = self._make_button("New Query")
        self.btn_open_folder = self._make_button("Open Folder")
        self.btn_save = self._make_button("Save")
        self.btn_save.setStyleSheet(
            _BTN_STYLE + "QPushButton:disabled { background-color: #A9BBD0;"
            " color: #E8EEF6; border-color: #93A7C0; }")
        self.btn_delete = self._make_button("Delete", danger=True)
        self.btn_save.clicked.connect(self.save_requested.emit)
        for button in (self.btn_test, self.btn_register, self.btn_edit,
                       self.btn_edit_format, self.btn_new_query, self.btn_open_folder,
                       self.btn_save, self.btn_delete):
            layout.addWidget(button)

    # ── Editable (File Source) widgets ──────────────────────────────────

    def _build_setup_editor(self) -> QWidget:
        """Editable Setup pane (File Source): Name + Description + read-only info."""
        box = QGroupBox("Setup")
        box.setStyleSheet(_DASHBOARD_GROUP_STYLE)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 16, 8, 8)
        lay.setSpacing(6)
        form = QFormLayout()
        form.setSpacing(4)
        edit_style = ("QLineEdit { background: white; border: 1px solid #A0C4E8;"
                      " padding: 3px 5px; }")
        self.edit_src_name = QLineEdit()
        self.edit_src_name.setStyleSheet(edit_style)
        self.edit_src_name.textEdited.connect(self._on_edit_changed)
        self.edit_src_desc = QLineEdit()
        self.edit_src_desc.setStyleSheet(edit_style)
        self.edit_src_desc.setPlaceholderText("Optional description")
        self.edit_src_desc.textEdited.connect(self._on_edit_changed)
        form.addRow("Name", self.edit_src_name)
        form.addRow("Description", self.edit_src_desc)
        lay.addLayout(form)
        self.lbl_setup_info = QLabel("")
        self.lbl_setup_info.setWordWrap(True)
        self.lbl_setup_info.setFont(_FONT_SMALL)
        self.lbl_setup_info.setStyleSheet(
            "color: #475569; border: none; background: transparent;")
        lay.addWidget(self.lbl_setup_info)
        lay.addStretch(1)
        return box

    def _build_columns_editor(self) -> QWidget:
        """Editable Columns pane (File Source): name cells + a Type combo per row."""
        box = QGroupBox("Columns")
        box.setStyleSheet(_DASHBOARD_GROUP_STYLE)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(8, 16, 8, 8)
        lay.setSpacing(4)
        hint = QLabel("Edit a column name or pick its Type, then Save.")
        hint.setFont(_FONT_SMALL)
        hint.setStyleSheet(
            "color: #6B7280; font-style: italic; border: none; background: transparent;")
        hint_row = QHBoxLayout()
        hint_row.setContentsMargins(0, 0, 0, 0)
        hint_row.setSpacing(6)
        hint_row.addWidget(hint)
        hint_row.addStretch(1)
        self.btn_bulk_columns = QPushButton("Enter Columns…")
        self.btn_bulk_columns.setFont(_FONT_SMALL)
        self.btn_bulk_columns.setFixedHeight(20)
        self.btn_bulk_columns.setToolTip(
            "Type or paste all columns at once — one name per line, or "
            "name,start,width for a fixed-width layout")
        self.btn_bulk_columns.setStyleSheet(
            "QPushButton { background: #F8FAFC; border: 1px solid #8AAED8;"
            " border-radius: 3px; color: #0D3A7A; padding: 1px 8px; }"
            "QPushButton:hover { background: #E8F0FB; border-color: #1E5BA8; }")
        self.btn_bulk_columns.clicked.connect(self.bulk_columns_requested.emit)
        hint_row.addWidget(self.btn_bulk_columns)
        lay.addLayout(hint_row)
        self.tbl_columns_edit = QTableWidget(0, 2)
        self.tbl_columns_edit.setHorizontalHeaderLabels(["Column", "Type"])
        self.tbl_columns_edit.verticalHeader().setVisible(False)
        self.tbl_columns_edit.verticalHeader().setDefaultSectionSize(20)
        self.tbl_columns_edit.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_columns_edit.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.tbl_columns_edit.setFont(_FONT)
        self.tbl_columns_edit.setStyleSheet(
            "QTableWidget { background: white; border: none; gridline-color: #EEF2F7; }"
            "QTableWidget::item:selected { background: #DCEAFB; color: #0D3A7A; }"
            "QHeaderView::section { background: #E8F0FB; font-weight: bold;"
            " font-size: 8pt; border: 1px solid #C0C0C0; padding: 1px 4px; }")
        hdr = self.tbl_columns_edit.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tbl_columns_edit.setColumnWidth(1, 110)
        self.tbl_columns_edit.itemChanged.connect(self._on_edit_changed)
        lay.addWidget(self.tbl_columns_edit, 1)
        return box

    def set_editable(self, editable: bool) -> None:
        """Switch Setup/Columns between read-only (ODBC/Access) and editable."""
        self._editable = editable
        page = 1 if editable else 0
        self.setup_stack.setCurrentIndex(page)
        self.columns_stack.setCurrentIndex(page)
        self.tables_list.setAcceptDrops(editable)
        self.tables_list.viewport().setAcceptDrops(editable)
        self.tables_list.setDragDropMode(
            QAbstractItemView.DragDropMode.DropOnly if editable
            else QAbstractItemView.DragDropMode.NoDragDrop)
        self.btn_add_files.setVisible(editable)
        self.lbl_tables_footnote.setText(
            "Drag files here to add, or use Add File(s)…. Right-click a table to "
            "copy its path, open its folder, or remove it." if editable
            else "Right-click a table to copy its path, open its folder, or remove it.")

    def set_editable_setup(self, name: str, description: str, info: str) -> None:
        self._loading = True
        self.edit_src_name.setText(name or "")
        self.edit_src_desc.setText(description or "")
        self.lbl_setup_info.setText(info or "")
        self._loading = False

    def set_editable_columns(self, columns: list[tuple], *,
                             names_editable: bool = True) -> None:
        """Fill the editable columns table. ``columns`` = (name, data_type)."""
        self._loading = True
        self._names_editable = names_editable
        tbl = self.tbl_columns_edit
        tbl.setRowCount(0)
        tbl.setRowCount(len(columns))
        for row, (name, data_type) in enumerate(columns):
            item = QTableWidgetItem(str(name))
            if not names_editable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tbl.setItem(row, 0, item)
            combo = QComboBox()
            combo.addItems(list(_FILE_DATA_TYPES))
            dt = (data_type or "TEXT").upper()
            if dt not in _FILE_DATA_TYPES:
                combo.addItem(dt)
            combo.setCurrentText(dt)
            combo.currentTextChanged.connect(self._on_edit_changed)
            tbl.setCellWidget(row, 1, combo)
        self._loading = False

    def editable_name(self) -> str:
        return self.edit_src_name.text().strip()

    def editable_description(self) -> str:
        return self.edit_src_desc.text().strip()

    def editable_columns(self) -> list[tuple]:
        """Read the draft columns back as (name, data_type) tuples."""
        out: list[tuple] = []
        tbl = self.tbl_columns_edit
        for row in range(tbl.rowCount()):
            item = tbl.item(row, 0)
            combo = tbl.cellWidget(row, 1)
            name = item.text().strip() if item else ""
            data_type = combo.currentText() if combo else "TEXT"
            out.append((name, data_type))
        return out

    @property
    def names_editable(self) -> bool:
        return self._names_editable

    def _on_edit_changed(self, *_args) -> None:
        if not self._loading:
            self.set_dirty(True)

    def set_dirty(self, dirty: bool) -> None:
        self._dirty = bool(dirty)
        if self._editable:
            self.btn_save.setEnabled(self._dirty)
            self.lbl_status.setText("Unsaved changes" if self._dirty else "")

    def is_dirty(self) -> bool:
        return self._editable and self._dirty

    @staticmethod
    def _make_button(text: str, *, danger: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setFont(_FONT_BOLD)
        btn.setFixedHeight(26)
        btn.setStyleSheet(_BTN_DANGER_STYLE if danger else _BTN_STYLE)
        return btn

    def set_title(self, text: str) -> None:
        self.lbl_name.setText(text or "")

    def set_badge(self, text: str, color: str) -> None:
        if not text:
            self.lbl_badge.setVisible(False)
            return
        self.lbl_badge.setText(text)
        self.lbl_badge.setStyleSheet(
            f"color: white; background: {color or '#475569'};"
            " border-radius: 8px; padding: 1px 9px;")
        self.lbl_badge.setVisible(True)

    def set_health(self, text: str, state: str | None) -> None:
        if not text or state is None:
            self.lbl_health.setVisible(False)
            return
        bg, fg, border = _HEALTH_PILL_COLORS.get(state, _HEALTH_PILL_COLORS["neutral"])
        self.lbl_health.setText(text)
        self.lbl_health.setStyleSheet(
            f"color: {fg}; background: {bg}; border: 1px solid {border};"
            " border-radius: 8px; padding: 1px 9px;")
        self.lbl_health.setVisible(True)

    def set_actions(self, *, test: bool, edit: bool, new_query: bool,
                    open_folder: bool, delete: bool, register: bool = False,
                    save: bool = False, edit_format: bool = False) -> None:
        self.btn_test.setVisible(test)
        self.btn_register.setVisible(register)
        self.btn_edit.setVisible(edit)
        self.btn_edit_format.setVisible(edit_format)
        self.btn_new_query.setVisible(new_query)
        self.btn_open_folder.setVisible(open_folder)
        self.btn_save.setVisible(save)
        self.btn_delete.setVisible(delete)

    def set_test_button(self, label: str, tooltip: str) -> None:
        """The top 'Test' action means different things per source type — name it."""
        self.btn_test.setText(label)
        self.btn_test.setToolTip(tooltip)

    def set_panel(self, key: str, columns: list[str], rows: list[list[object]],
                  visible: bool = True) -> None:
        grp = self._panels[key]
        if not visible:
            grp.setVisible(False)
            return
        grp.setVisible(True)
        grp.load_data(columns, [tuple(row) for row in rows])

    # ── Tables tab ────────────────────────────────────────────────────

    def set_tables(self, rows: list[tuple], *, removable: bool) -> None:
        """Fill the Tables list. ``rows`` = (table, status, path); ``removable``
        gates the right-click Remove (File Source members can be removed)."""
        self._tables_rows = [
            {"name": str(r[0]), "status": str(r[1]) if len(r) > 1 else "",
             "path": str(r[2]) if len(r) > 2 else ""}
            for r in rows
        ]
        self._tables_removable = removable
        self.tables_list.setRowCount(len(self._tables_rows))
        for row, info in enumerate(self._tables_rows):
            for col, value in enumerate((info["name"], info["status"], info["path"])):
                self.tables_list.setItem(row, col, QTableWidgetItem(value))
        self.tables_list.resizeColumnToContents(0)
        self.tables_list.resizeColumnToContents(1)
        if self._tables_rows:
            self.tables_list.selectRow(0)  # a default target for the Preview button
        self.clear_preview()

    def set_tables_tab_visible(self, visible: bool) -> None:
        self.tabs.setTabVisible(1, visible)
        if not visible and self.tabs.currentIndex() == 1:
            self.tabs.setCurrentIndex(0)

    def _ensure_preview_dialog(self) -> "_TablePreviewDialog":
        if self._preview_dialog is None:
            self._preview_dialog = _TablePreviewDialog(self)
            self._preview_dialog.reload_requested.connect(self._on_preview_reload)
        return self._preview_dialog

    def set_preview(self, dataframe) -> None:
        self._ensure_preview_dialog().set_dataframe(dataframe)

    def clear_preview(self) -> None:
        if self._preview_dialog is not None:
            self._preview_dialog.set_dataframe(pd.DataFrame())

    def _selected_table(self) -> dict | None:
        rows = self.tables_list.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        return self._tables_rows[index] if 0 <= index < len(self._tables_rows) else None

    def _on_preview_clicked(self) -> None:
        info = self._selected_table()
        if info is None and self._tables_rows:
            self.tables_list.selectRow(0)
            info = self._selected_table()
        if info is None:
            return
        self._preview_table_name = info["name"]
        dlg = self._ensure_preview_dialog()
        dlg.set_title(info["name"])
        rows = dlg.rows_value()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        self.preview_requested.emit(info["name"], rows)

    def _on_preview_reload(self, rows: int) -> None:
        if self._preview_table_name:
            self.preview_requested.emit(self._preview_table_name, max(1, rows))

    def _on_tables_context_menu(self, pos) -> None:
        item = self.tables_list.itemAt(pos)
        if item is None:
            return
        info = self._tables_rows[item.row()] if item.row() < len(self._tables_rows) else None
        if info is None:
            return
        menu = QMenu(self.tables_list)
        copy_path = menu.addAction("Copy path")
        copy_path.setEnabled(bool(info["path"]))
        open_folder = menu.addAction("Open containing folder")
        open_folder.setEnabled(bool(info["path"]))
        remove = menu.addAction("Remove table from source")
        remove.setEnabled(self._tables_removable)
        chosen = menu.exec(self.tables_list.viewport().mapToGlobal(pos))
        if chosen == copy_path and info["path"]:
            QApplication.clipboard().setText(info["path"])
        elif chosen == open_folder and info["path"]:
            self.open_table_folder_requested.emit(info["path"])
        elif chosen == remove:
            self.remove_table_requested.emit(info["name"])

    def show_empty(self, message: str) -> None:
        self.set_editable(False)
        self.set_dirty(False)
        self.lbl_status.setText("")
        self.set_title(message)
        self.set_badge("", "")
        self.set_health("", None)
        self.set_actions(test=False, edit=False, new_query=False,
                         open_folder=False, delete=False, save=False)
        for key in self._panels:
            self.set_panel(key, [], [], visible=False)
        self.set_tables([], removable=False)
        self.set_tables_tab_visible(False)

