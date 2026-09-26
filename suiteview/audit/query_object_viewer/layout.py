"""QueryObject Viewer LayoutMixin methods."""
from __future__ import annotations

from .common import *  # noqa: F401,F403 - private split module shares viewer globals.
from suiteview.audit.common_table_dialog import CommonTableDialog
from suiteview.audit.unique_value_registry_window import UniqueValueRegistryWindow
from .dashboard import _SourceDashboard
from .widgets import _CompactSourceDelegate, _OrganizerPillDelegate, _OrganizerTree


class QueryObjectViewerLayoutMixin:
    def build_content(self) -> QWidget:
        body = QWidget()
        body.setStyleSheet("QWidget { background-color: #F0F0F0; }")
        root = QVBoxLayout(body)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(4)

        splitter = self._make_browser_splitter()
        splitter.addWidget(self._build_left_panel())
        detail_panel = self._build_detail_panel()
        self._browser_canvas_stack = self._build_browser_canvas_stack(detail_panel)
        splitter.addWidget(self._build_canvas_shell())
        self._configure_browser_splitter(splitter)
        root.addWidget(splitter, 1)

        self.refresh()
        QTimer.singleShot(0, self._apply_left_panel_width)
        return body

    def _make_browser_splitter(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._browser_splitter = splitter
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)
        splitter.splitterMoved.connect(self._on_browser_splitter_moved)
        return splitter

    def _build_left_panel(self) -> QWidget:
        left = QWidget()
        left.setMinimumWidth(_LEFT_PANEL_MIN_WIDTH)
        left.setMaximumWidth(_LEFT_PANEL_MAX_WIDTH)
        left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        self.left_tabs = QTabWidget()
        self.left_tabs.setFont(_FONT_SMALL)
        self.left_tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #1E5BA8; background: white; }"
            "QTabBar::tab { background: #E8F0FB; color: #0D3A7A;"
            " border: 1px solid #A0C4E8; border-bottom: none;"
            " padding: 3px 5px; font-size: 8pt; }"
            "QTabBar::tab:selected { background: white; color: #1E5BA8; font-weight: bold; }"
        )
        self.left_tabs.addTab(self._build_query_nav_panel(), "Queries")
        self.left_tabs.addTab(self._build_data_source_panel(), "Data Sources")
        self._tables_left_host = self._make_embedded_host()
        self._registry_left_host = self._make_embedded_host()
        self.left_tabs.addTab(self._tables_left_host, "Common Tables")
        self.left_tabs.addTab(self._registry_left_host, "Registry")
        self.left_tabs.currentChanged.connect(self._on_left_tab_changed)
        left_lay.addWidget(self.left_tabs, 1)
        return left

    def _build_query_nav_panel(self) -> QWidget:
        queried_panel = QWidget()
        queried_lay = QVBoxLayout(queried_panel)
        queried_lay.setContentsMargins(3, 3, 3, 3)
        queried_lay.setSpacing(4)

        lbl_left = QLabel("Queries")
        lbl_left.setFont(_FONT_BOLD)
        lbl_left.setStyleSheet("color: #1E5BA8;")
        queried_lay.addWidget(lbl_left)

        search_row = QWidget()
        search_lay = QHBoxLayout(search_row)
        search_lay.setContentsMargins(0, 0, 0, 0)
        search_lay.setSpacing(4)
        self.edit_search = self._make_search_edit("Search query objects...")
        self.edit_search.textChanged.connect(lambda _text: self.refresh())
        search_lay.addWidget(self.edit_search, 1)
        queried_lay.addWidget(search_row)

        self.tree = _OrganizerTree(self)
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(210)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(14)
        self.tree.setUniformRowHeights(False)
        self.tree.setItemDelegate(_OrganizerPillDelegate(self.tree))
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tree.setFont(_FONT)
        self.tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #1E5BA8; background: white; }"
            "QTreeWidget::item { padding: 0px; border: none; background: transparent; }"
            "QTreeWidget::item:selected { background: transparent; color: black; }"
        )
        self.tree.itemClicked.connect(self._on_tree_clicked)
        self.tree.currentItemChanged.connect(self._on_tree_selection)
        self.tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        self.tree.itemExpanded.connect(lambda item: self._on_tree_expansion_changed(item, True))
        self.tree.itemCollapsed.connect(lambda item: self._on_tree_expansion_changed(item, False))
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        queried_lay.addWidget(self.tree, 1)
        return queried_panel

    def _build_detail_panel(self) -> QWidget:
        right = QWidget()
        right.setMinimumWidth(_RIGHT_PANEL_MIN_WIDTH)
        right.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(4)
        right_lay.addWidget(self._build_info_header())
        right_lay.addWidget(self._build_object_tabs(), 1)
        self._detail_canvas = right
        return right

    def _build_info_header(self) -> QWidget:
        info = QWidget()
        info_lay = QHBoxLayout(info)
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.setSpacing(10)

        self.lbl_name = QLabel("Select a QueryObject")
        self.lbl_name.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_name.setStyleSheet("color: #1E5BA8;")
        self.lbl_name.setFixedWidth(430)
        self.lbl_name.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        info_lay.addWidget(self.lbl_name)

        self.lbl_kind = QLabel("")
        self.lbl_kind.setFont(_FONT)
        self.lbl_kind.setStyleSheet("color: #666;")
        self.lbl_kind.setVisible(False)
        info_lay.addWidget(self.lbl_kind)

        self.lbl_status = QLabel("")
        self.lbl_status.setFont(_FONT)
        self.lbl_status.setStyleSheet("color: #666;")
        self.lbl_status.setVisible(False)
        info_lay.addWidget(self.lbl_status)
        info_lay.addStretch()

        self._add_header_button(info_lay, "btn_open_builder", "Open in Builder", 116,
                                self._on_open_builder,
                                "Open this object in its designer when available")
        self._add_header_button(info_lay, "btn_preview_file", "Preview Data", 98,
                                self._on_preview_file)
        self._add_header_button(info_lay, "btn_open_source_folder", "Open Folder", 98,
                                self._on_open_source_folder,
                                "Open this source file's folder in File Nav",
                                visible=False)
        self._add_promote_button(info_lay)
        self._add_header_button(info_lay, "btn_delete", "Delete", 80,
                                self._on_delete, style=_BTN_DANGER_STYLE)
        return info

    def _add_header_button(
        self,
        layout: QHBoxLayout,
        attr: str,
        text: str,
        width: int,
        callback,
        tooltip: str = "",
        *,
        style: str = _BTN_STYLE,
        visible: bool = True,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setFont(_FONT_BOLD)
        button.setFixedSize(width, 26)
        button.setStyleSheet(style)
        if tooltip:
            button.setToolTip(tooltip)
        button.clicked.connect(callback)
        button.setVisible(visible)
        setattr(self, attr, button)
        layout.addWidget(button)
        return button

    def _add_promote_button(self, layout: QHBoxLayout) -> None:
        self.btn_promote = QPushButton("Register Source")
        self.btn_promote.setFont(_FONT_BOLD)
        self.btn_promote.setFixedSize(112, 26)
        self.btn_promote.setStyleSheet(_BTN_STYLE)
        self.btn_promote.setToolTip("Mark a file source object as a registered, reusable source")
        self.btn_promote.clicked.connect(self._on_promote)
        self._promote_slot = QWidget()
        self._promote_slot.setFixedSize(112, 26)
        promote_lay = QHBoxLayout(self._promote_slot)
        promote_lay.setContentsMargins(0, 0, 0, 0)
        promote_lay.setSpacing(0)
        promote_lay.addWidget(self.btn_promote)
        layout.addWidget(self._promote_slot)

    def _build_object_editor(self) -> QWidget:
        editor = QWidget()
        editor.setStyleSheet(
            "QWidget { background: #FAFBFD; border: 1px solid #C9D8EA; }"
            "QLabel { border: none; background: transparent; color: #444; }"
            "QLineEdit { background: white; border: 1px solid #A0C4E8; padding: 2px 4px; }"
        )
        editor_lay = QGridLayout(editor)
        editor_lay.setContentsMargins(6, 5, 6, 5)
        editor_lay.setHorizontalSpacing(6)
        editor_lay.setVerticalSpacing(4)

        self.edit_name = self._make_line_edit(0)
        self.edit_origin = self._make_line_edit(0)
        self.edit_origin.setToolTip("Builder/source that created this object, such as Query Studio, Cyberlife, Manual SQL, or csv")
        self.edit_tags = self._make_line_edit(0)
        self.edit_tags.setToolTip("Optional comma-separated labels for grouping and finding objects later")
        self.edit_description = self._make_line_edit(0)

        self._add_editor_field(editor_lay, 0, 0, "Object", self.edit_name)
        self._add_editor_field(editor_lay, 0, 2, "Builder", self.edit_origin)
        self._add_editor_field(editor_lay, 1, 0, "Description", self.edit_description)
        self._add_editor_field(editor_lay, 1, 2, "Tags", self.edit_tags)

        self.btn_save = QPushButton("Save")
        self.btn_save.setFont(_FONT_BOLD)
        self.btn_save.setFixedSize(72, 24)
        self.btn_save.setStyleSheet(_BTN_STYLE)
        self.btn_save.clicked.connect(self._on_save_changes)
        editor_lay.addWidget(self.btn_save, 0, 4, 2, 1, Qt.AlignmentFlag.AlignTop)
        editor_lay.setColumnStretch(1, 3)
        editor_lay.setColumnStretch(3, 2)
        editor_lay.setRowStretch(0, 0)
        editor_lay.setRowStretch(1, 0)
        editor_lay.setRowStretch(2, 1)
        return editor

    def _build_object_tabs(self) -> QTabWidget:
        self.tabs = QTabWidget()
        self.tabs.setFont(_FONT)
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 2px solid #1E5BA8; background: white; }"
            "QTabBar::tab { padding: 4px 14px; font-size: 9pt;"
            " border: 1px solid #A0C4E8; border-bottom: none; margin-right: 1px; }"
            "QTabBar::tab:selected { background: white; color: #1E5BA8;"
            " font-weight: bold; }"
            "QTabBar::tab:!selected { background: #E8F0FB; color: #444; }"
        )
        self.tabs.addTab(self._build_object_editor(), "Object")
        self.tbl_sources = self._add_table_tab("Sources", ["Name", "Type", "DSN", "Status"])
        self.tbl_outputs = self._add_table_tab("Outputs", ["Field", "Type", "Display Name", "Source"])
        self.tbl_inputs = self._add_table_tab("Inputs", ["Field", "Type", "Display Name", "Source"])
        self.tbl_joins = self._add_table_tab("Joins", ["Field", "Type", "Display Name", "Source"])
        self.tbl_fields = self._add_table_tab(
            "All Fields", ["Field", "Type", "Role", "Display Name", "Source"])
        self.tbl_fields.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.txt_sql = self._add_text_tab("SQL", read_only=False)
        self.txt_config = self._add_text_tab("Config", read_only=True)
        return self.tabs

    def _add_table_tab(self, label: str, headers: list[str]) -> QTableWidget:
        table = self._make_table(headers)
        self.tabs.addTab(table, label)
        return table

    def _add_text_tab(self, label: str, *, read_only: bool) -> QTextEdit:
        text = QTextEdit()
        text.setFont(_FONT_MONO)
        text.setReadOnly(read_only)
        text.setStyleSheet("QTextEdit { background: white; border: none; }")
        self.tabs.addTab(text, label)
        return text

    def _build_browser_canvas_stack(self, detail_panel: QWidget) -> QStackedWidget:
        stack = QStackedWidget()
        stack.addWidget(detail_panel)
        self._tables_canvas_host = self._make_embedded_host()
        self._registry_canvas_host = self._make_embedded_host()
        stack.addWidget(self._tables_canvas_host)
        stack.addWidget(self._registry_canvas_host)
        self._source_dashboard = self._build_source_dashboard()
        stack.addWidget(self._source_dashboard)
        return stack

    def _build_source_dashboard(self) -> _SourceDashboard:
        dashboard = _SourceDashboard()
        dashboard.btn_test.clicked.connect(self._on_source_test)
        dashboard.btn_register.clicked.connect(self._on_source_register)
        dashboard.btn_edit.clicked.connect(self._on_source_edit_setup)
        dashboard.btn_edit_format.clicked.connect(self._on_edit_file_source_format)
        dashboard.btn_open_folder.clicked.connect(self._on_open_source_folder)
        dashboard.btn_delete.clicked.connect(self._on_source_delete)
        new_query_menu = QMenu(dashboard.btn_new_query)
        new_query_menu.addAction("Visual Query").triggered.connect(
            lambda: self._on_source_new_query("visual"))
        if not is_data_read_only():
            new_query_menu.addAction("Manual SQL").triggered.connect(
                lambda: self._on_source_new_query("manual"))
        dashboard.btn_new_query.setMenu(new_query_menu)
        dashboard.preview_requested.connect(self._on_dashboard_preview)
        dashboard.remove_table_requested.connect(self._on_dashboard_remove_table)
        dashboard.open_table_folder_requested.connect(self._open_path_folder)
        dashboard.save_requested.connect(self._on_source_save)
        dashboard.add_files_requested.connect(self._on_add_files_to_source)
        dashboard.pick_files_requested.connect(self._on_pick_files_for_source)
        dashboard.bulk_columns_requested.connect(self._on_bulk_edit_columns)
        return dashboard

    def _build_canvas_shell(self) -> QWidget:
        canvas_shell = QWidget()
        canvas_shell.setMinimumWidth(_RIGHT_PANEL_MIN_WIDTH)
        canvas_shell.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        canvas_lay = QVBoxLayout(canvas_shell)
        canvas_lay.setContentsMargins(0, 0, 0, 0)
        canvas_lay.setSpacing(4)

        self.lbl_canvas_title = QLabel("Object Browser")
        self.lbl_canvas_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.lbl_canvas_title.setMinimumHeight(28)
        self.lbl_canvas_title.setStyleSheet(
            "QLabel { background: #DADADA; color: black;"
            " border: 1px solid #B8B8B8; padding: 4px 8px; }"
        )
        self.lbl_canvas_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        canvas_lay.addWidget(self.lbl_canvas_title)
        canvas_lay.addWidget(self._browser_canvas_stack, 1)
        return canvas_shell

    def _configure_browser_splitter(self, splitter: QSplitter) -> None:
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([
            self._left_panel_width,
            max(_RIGHT_PANEL_MIN_WIDTH, 1120 - self._left_panel_width),
        ])

    @staticmethod
    def _make_line_edit(width: int) -> QLineEdit:
        edit = QLineEdit()
        edit.setFont(_FONT)
        edit.setFixedHeight(24)
        if width:
            edit.setFixedWidth(width)
        edit.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #A0C4E8;"
            " padding: 2px 4px; }"
        )
        return edit

    @staticmethod
    def _make_search_edit(placeholder: str) -> QLineEdit:
        edit = QLineEdit()
        edit.setFont(_FONT)
        edit.setFixedHeight(24)
        edit.setPlaceholderText(placeholder)
        edit.setClearButtonEnabled(True)
        edit.setStyleSheet(
            "QLineEdit { background: white; border: 1px solid #1E5BA8;"
            " border-radius: 3px; padding: 2px 6px; }"
        )
        return edit

    @staticmethod
    def _install_nav_search(panel: QWidget, search_edit: QLineEdit) -> None:
        layout = panel.layout()
        if layout is None:
            return
        layout.insertWidget(min(1, layout.count()), search_edit)

    def _set_canvas_title(self, title: str) -> None:
        if hasattr(self, "lbl_canvas_title"):
            self.lbl_canvas_title.setText(title or "Object Browser")

    def _make_embedded_host(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        return host

    @staticmethod
    def _replace_host_content(host: QWidget, child: QWidget) -> None:
        layout = host.layout()
        if layout is None:
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        child.setParent(host)
        child.setVisible(True)
        layout.addWidget(child, 1)

    def _on_left_tab_changed(self, index: int) -> None:
        label = self.left_tabs.tabText(index)
        if label == "Common Tables":
            self._ensure_tables_embedded()
            self._browser_canvas_stack.setCurrentWidget(self._tables_canvas_host)
            self._update_common_tables_canvas_title()
            return
        if label == "Registry":
            self._ensure_registry_embedded()
            self._browser_canvas_stack.setCurrentWidget(self._registry_canvas_host)
            self._update_registry_canvas_title()
            return
        if label == "Data Sources":
            self._refresh_source_tree()
            self._route_source_selection(self.source_tree.currentItem())
            self._update_data_sources_canvas_title()
        else:
            self._browser_canvas_stack.setCurrentWidget(self._detail_canvas)
            self._update_queried_canvas_title()

    def _ensure_tables_embedded(self) -> None:
        if self._embedded_common_tables is not None:
            return
        try:
            self._embedded_common_tables = CommonTableDialog(parent=self, embedded=True)
            self._replace_host_content(
                self._tables_left_host, self._embedded_common_tables._nav_panel)
            self._replace_host_content(
                self._tables_canvas_host, self._embedded_common_tables._canvas_panel)
            self.edit_table_search = self._make_search_edit("Search common tables...")
            self.edit_table_search.textChanged.connect(self._filter_common_table_list)
            self._install_nav_search(
                self._embedded_common_tables._nav_panel, self.edit_table_search)
            self._embedded_common_tables.lst_tables.currentTextChanged.connect(
                lambda _name: self._update_common_tables_canvas_title())
            self._filter_common_table_list(self.edit_table_search.text())
        except Exception as exc:
            logger.exception("Failed to embed Common Tables in Object Browser")
            QMessageBox.warning(self, "Common Tables Error", str(exc))

    def _ensure_registry_embedded(self) -> None:
        if self._embedded_registry is not None:
            return
        try:
            self._embedded_registry = UniqueValueRegistryWindow(parent=self)
            self._replace_host_content(
                self._registry_left_host, self._embedded_registry._nav_panel)
            self._replace_host_content(
                self._registry_canvas_host, self._embedded_registry._canvas_panel)
            self.edit_registry_search = self._make_search_edit("Search registry fields...")
            self.edit_registry_search.textChanged.connect(self._filter_registry_tree)
            self._install_nav_search(
                self._embedded_registry._nav_panel, self.edit_registry_search)
            self._embedded_registry.tree.currentItemChanged.connect(
                lambda current, _previous: self._update_registry_canvas_title(current))
            self._filter_registry_tree(self.edit_registry_search.text())
        except Exception as exc:
            logger.exception("Failed to embed Registry in Object Browser")
            QMessageBox.warning(self, "Registry Error", str(exc))

    def _select_left_tab(self, label: str) -> None:
        for index in range(self.left_tabs.count()):
            if self.left_tabs.tabText(index) == label:
                self.left_tabs.setCurrentIndex(index)
                return

    def _open_common_tables(self):
        self._select_left_tab("Common Tables")

    def _open_registry(self):
        self._select_left_tab("Registry")

    def _update_queried_canvas_title(self) -> None:
        self._set_canvas_title(self._query_canvas_title())

    def _update_data_sources_canvas_title(self) -> None:
        self._set_canvas_title(self._data_source_canvas_title())

    def _update_common_tables_canvas_title(self) -> None:
        table_name = ""
        if self._embedded_common_tables is not None:
            current = self._embedded_common_tables.lst_tables.currentItem()
            table_name = current.text() if current is not None else ""
        self._set_canvas_title(f"Common Tables: {table_name}" if table_name else "Common Tables")

    def _update_registry_canvas_title(self, item: QTreeWidgetItem | None = None) -> None:
        if self._embedded_registry is None:
            self._set_canvas_title("Registry")
            return
        current = item or self._embedded_registry.tree.currentItem()
        if current is None:
            self._set_canvas_title("Registry")
            return
        parent = current.parent()
        grandparent = parent.parent() if parent is not None else None
        if grandparent is not None:
            self._set_canvas_title(f"Registry: {parent.text(0)}.{current.text(0)}")
        else:
            self._set_canvas_title(f"Registry: {current.text(0)}")

    def _query_canvas_title(self) -> str:
        payload = _payload(self.tree.currentItem()) if hasattr(self, "tree") else {}
        payload_type = payload.get("type")
        if payload_type == "query":
            obj = query_object_store.load_object_by_id(payload.get("id", ""))
            if obj is not None:
                return f"{_kind_label(obj.kind)}: {obj.name}"
            name = str(payload.get("name", "")).strip()
            return f"Queries: {name}" if name else "Queries"
        if payload_type == "group":
            name = str(payload.get("name", "")).strip()
            return f"Query Groups: {name}" if name else "Query Groups"
        if payload_type == "forge":
            name = str(payload.get("name", "")).strip()
            display_name = _dataforge_display_name(name) if name else ""
            return f"DataForge: {display_name}" if display_name else "DataForge"
        return "Queries"

    def _data_source_canvas_title(self) -> str:
        payload = _payload(self.source_tree.currentItem()) if hasattr(self, "source_tree") else {}
        payload_type = payload.get("type")
        if payload_type in {"query", "source_query"}:
            obj = query_object_store.load_object_by_id(payload.get("id", ""))
            name = obj.name if obj is not None else str(payload.get("name", "")).strip()
            return f"Data Sources: {name}" if name else "Data Sources"
        if payload_type == "odbc_source":
            dsn = str(payload.get("dsn", "")).strip()
            return f"Data Sources: {dsn}" if dsn else "Data Sources"
        if payload_type == "file_source":
            label = str(payload.get("label", "")).strip()
            return f"Data Sources: {label}" if label else "Data Sources"
        if payload_type == "source_group":
            group = str(payload.get("group", "")).strip().title()
            return f"Data Sources: {group}" if group else "Data Sources"
        return "Data Sources"

    def _filter_common_table_list(self, search_text: str) -> None:
        if self._embedded_common_tables is None:
            return
        table_list = self._embedded_common_tables.lst_tables
        for row in range(table_list.count()):
            item = table_list.item(row)
            item.setHidden(not self._text_matches_search(search_text, [item.text()]))
        self._update_common_tables_canvas_title()

    def _filter_registry_tree(self, search_text: str) -> None:
        if self._embedded_registry is None:
            return
        tree = self._embedded_registry.tree
        search_active = bool(search_text.strip())

        def _matches(item: QTreeWidgetItem) -> bool:
            return self._text_matches_search(
                search_text, [item.text(column) for column in range(tree.columnCount())])

        def _filter_item(item: QTreeWidgetItem, ancestor_matches: bool = False) -> bool:
            own_matches = _matches(item)
            descendant_matches = False
            for child_index in range(item.childCount()):
                child = item.child(child_index)
                descendant_matches = _filter_item(child, ancestor_matches or own_matches) or descendant_matches
            visible = not search_active or ancestor_matches or own_matches or descendant_matches
            item.setHidden(not visible)
            if search_active and visible and item.childCount():
                item.setExpanded(True)
            return visible

        root = tree.invisibleRootItem()
        for index in range(root.childCount()):
            _filter_item(root.child(index))
        self._update_registry_canvas_title()

    def _build_data_source_panel(self) -> QWidget:
        panel = QWidget()
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(3, 3, 3, 3)
        panel_lay.setSpacing(4)

        lbl = QLabel("Data Sources")
        lbl.setFont(_FONT_BOLD)
        lbl.setStyleSheet("color: #1E5BA8;")
        panel_lay.addWidget(lbl)

        self.edit_source_search = self._make_search_edit("Search data sources...")
        self.edit_source_search.textChanged.connect(lambda _text: self._refresh_source_tree())
        panel_lay.addWidget(self.edit_source_search)

        # Defining a source is a data-source action, not a query build mode — so
        # the entry point lives here. A typed chooser: File Source + ODBC DSN
        # today; MS Access joins it next.
        self.btn_add_source = QPushButton("+ Add Data Source  ▾")
        self.btn_add_source.setFont(_FONT_BOLD)
        self.btn_add_source.setFixedHeight(24)
        self.btn_add_source.setStyleSheet(_BTN_STYLE)
        self.btn_add_source.setToolTip("Register a new data source to query against")
        add_menu = QMenu(self.btn_add_source)
        add_menu.addAction("File Source…").triggered.connect(self._on_add_file_source)
        add_menu.addAction("ODBC DSN…").triggered.connect(self._on_add_odbc_source)
        add_menu.addAction("MS Access…").triggered.connect(self._on_add_access_source)
        self.btn_add_source.setMenu(add_menu)
        panel_lay.addWidget(self.btn_add_source)

        self.source_tree = QTreeWidget()
        self.source_tree.setHeaderHidden(True)
        self.source_tree.setDragEnabled(False)
        self.source_tree.setAcceptDrops(False)
        self.source_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.source_tree.setRootIsDecorated(True)
        self.source_tree.setIndentation(12)
        self.source_tree.setUniformRowHeights(False)
        self.source_tree.setItemDelegate(_CompactSourceDelegate(self.source_tree))
        self.source_tree.setFont(_FONT)
        self.source_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.source_tree.setStyleSheet(
            "QTreeWidget { border: 1px solid #C9D8EA; border-radius: 3px;"
            " background: white; outline: 0; }"
            "QTreeWidget::item { padding: 0px 4px; border: none; }"
            "QTreeWidget::item:hover { background: #F2F7FD; }"
            "QTreeWidget::item:selected { background: #DCEAFB; color: #0D3A7A; }"
        )
        self.source_tree.itemClicked.connect(self._on_source_tree_clicked)
        self.source_tree.currentItemChanged.connect(self._on_source_tree_selection)
        self.source_tree.itemDoubleClicked.connect(self._on_source_tree_double_clicked)
        self.source_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.source_tree.customContextMenuRequested.connect(
            self._on_source_tree_context_menu)
        panel_lay.addWidget(self.source_tree, 1)
        return panel

    @staticmethod
    def _add_editor_field(layout: QGridLayout, row: int, col: int, label: str, widget: QLineEdit):
        lbl = QLabel(label)
        lbl.setFont(_FONT_SMALL)
        layout.addWidget(lbl, row, col)
        layout.addWidget(widget, row, col + 1)

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(18)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setFont(_FONT)
        table.setStyleSheet(
            "QTableWidget { border: none; background: white; gridline-color: #E0E0E0; }"
            "QHeaderView::section { background: #E8F0FB; font-weight: bold;"
            " font-size: 8pt; border: 1px solid #C0C0C0; padding: 1px 4px; }"
        )
        return table

    @staticmethod
    def _set_table_headers(table: QTableWidget, headers: list[str]) -> None:
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(0)

    @staticmethod
    def _set_table_rows(table: QTableWidget, rows: list[list[object]]) -> None:
        table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for col_index, value in enumerate(values):
                table.setItem(row_index, col_index, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def _configure_object_tables(self) -> None:
        self._set_tab_labels([
            "Object", "Sources", "Outputs", "Inputs",
            "Joins", "All Fields", "SQL", "Config",
        ])
        self._set_table_headers(self.tbl_sources, ["Name", "Type", "DSN", "Status"])
        self._set_table_headers(self.tbl_outputs, ["Field", "Type", "Display Name", "Source"])
        self._set_table_headers(self.tbl_inputs, ["Field", "Type", "Display Name", "Source"])
        self._set_table_headers(self.tbl_joins, ["Field", "Type", "Display Name", "Source"])
        self._set_table_headers(self.tbl_fields, ["Field", "Type", "Role", "Display Name", "Source"])

    def _configure_forge_tables(self) -> None:
        self._set_tab_labels([
            "Forge", "Sources", "Outputs", "Filters",
            "Joins", "All Fields", "SQL", "Config",
        ])
        self._set_table_headers(self.tbl_sources, ["Source", "Query Copy", "Kind", "DSN", "Columns", "Snapshot", "Rows"])
        self._set_table_headers(self.tbl_outputs, ["Field", "Display Name", "Source", "Type"])
        self._set_table_headers(self.tbl_inputs, ["Filter Tab", "Field", "Mode", "Value"])
        self._set_table_headers(self.tbl_joins, ["Left Source", "Left Field(s)", "Right Source", "Right Field(s)", "Type"])
        self._set_table_headers(self.tbl_fields, ["Field", "Type", "Role", "Source"])

    def _set_tab_labels(self, labels: list[str]) -> None:
        if not hasattr(self, "tabs"):
            return
        for index, label in enumerate(labels):
            if index >= self.tabs.count():
                break
            self.tabs.setTabText(index, label)
