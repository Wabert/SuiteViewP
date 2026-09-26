"""QueryObject Viewer NavigationMixin methods."""
from __future__ import annotations

from .common import *  # noqa: F401,F403 - private split module shares viewer globals.


class QueryObjectViewerNavigationMixin:
    def refresh(self):
        """Rebuild the tree from the organizer: groups, forges, loose queries.

        Weight tells structure (query < Group < Forge), color tells origin
        (build-mode chips/tints; DataForge orange) â€” design Â§8.
        """
        current_payload = _payload(self.tree.currentItem())
        search_text = self.edit_search.text() if hasattr(self, "edit_search") else ""
        search_active = bool(search_text.strip())
        self._loading_tree = True
        self.tree.clear()
        self.tree.setDragEnabled(not search_active)
        self.tree.setAcceptDrops(not search_active)
        self.tree.setDropIndicatorShown(not search_active)
        self._ensure_dataforge_query_objects()
        objects = query_object_store.list_objects()
        by_id = {o.id: o for o in objects}

        # Forge-owned Source copies render under their forge node.
        forge_children: dict[str, list[QueryObject]] = {}
        for obj in objects:
            info = _dataforge_info(obj)
            if info is not None:
                forge_children.setdefault(info[0], []).append(obj)

        forge_names = [f.name for f in dataforge_store.list_forges()]
        organizer = get_query_organizer()
        if organizer.reconcile(objects, forge_names):
            organizer.save()

        fallback_item = None
        selected_item = None

        def _track(item: QTreeWidgetItem, payload: dict):
            nonlocal fallback_item, selected_item
            if fallback_item is None and payload.get("type") == "query":
                fallback_item = item
            if current_payload and payload.get("type") == current_payload.get("type"):
                keys = {"query": ("id",), "group": ("group_id",),
                        "forge": ("name",)}.get(payload.get("type"), ())
                if keys and all(payload.get(k) == current_payload.get(k)
                                for k in keys):
                    selected_item = item

        def _add_query_item(parent, obj: QueryObject, forge_name: str = ""):
            style = mode_style(obj.kind)
            dsn = _display_dsn_for_object(obj) or "?"
            item = QTreeWidgetItem([obj.name])
            item.setFont(0, _FONT)
            item.setForeground(0, QColor(style.color))
            item.setBackground(0, QBrush(QColor(style.tint)))
            item.setToolTip(0, f"{style.label} â€” {dsn}")
            payload = {
                "type": "query",
                "id": obj.id,
                "name": obj.name,
                "badge": dsn,
                "badge_color": style.color,
                "badge_fill": style.color,
                "badge_text_color": "#FFFFFF",
            }
            if forge_name:
                payload["forge"] = forge_name
            item.setData(0, Qt.ItemDataRole.UserRole, payload)
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            _track(item, payload)
            return item

        def _add_forge_item(forge_name: str):
            children = sorted(forge_children.get(forge_name, []),
                              key=lambda o: o.name.lower())
            forge_matches = self._text_matches_search(
                search_text, ["DataForge", _dataforge_display_name(forge_name), forge_name])
            if search_text:
                children = [obj for obj in children
                            if self._object_matches_search(obj, search_text)]
            if search_text and not forge_matches and not children:
                return
            item = QTreeWidgetItem([f"âš™ {_dataforge_display_name(forge_name)} ({len(children)})"])
            item.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
            item.setForeground(0, QColor(FORGE_STYLE.color))
            item.setBackground(0, QBrush(QColor(FORGE_STYLE.tint)))
            item.setSizeHint(0, QSize(0, 30))
            payload = {"type": "forge", "name": forge_name}
            item.setData(0, Qt.ItemDataRole.UserRole, payload)
            self.tree.addTopLevelItem(item)
            for obj in children:
                _add_query_item(item, obj, forge_name=forge_name)
            item.setExpanded(self._expanded_for_item(payload, search_active))
            _track(item, payload)

        def _add_group_item(group: dict):
            children = []
            group_matches = self._text_matches_search(search_text, [group["name"]])
            for child in group.get("items", []):
                obj = by_id.get(child.get("query_id"))
                if obj is not None and (not search_text
                                        or self._object_matches_search(obj, search_text)):
                    children.append(obj)
            if search_text and not group_matches and not children:
                return
            prefix = "" if group.get("id") == COMMONS_GROUP_ID else "â–£ "
            item = QTreeWidgetItem([f"{prefix}{group['name']} ({len(children)})"])
            item.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))
            item.setForeground(0, QColor(GROUP_STYLE.color))
            item.setBackground(0, QBrush(QColor(GROUP_STYLE.tint)))
            item.setSizeHint(0, QSize(0, 30))
            payload = {"type": "group", "group_id": group["id"],
                       "name": group["name"],
                       "color": group.get("color"),
                       "expanded": group.get("expanded", True)}
            item.setData(0, Qt.ItemDataRole.UserRole, payload)
            self.tree.addTopLevelItem(item)
            for obj in children:
                _add_query_item(item, obj)
            item.setExpanded(self._expanded_for_item(payload, search_active))
            _track(item, payload)

        for entry in organizer.items:
            kind = entry.get("type")
            if kind == "query":
                obj = by_id.get(entry.get("query_id"))
                if obj is not None and self._object_matches_search(obj, search_text):
                    _add_query_item(None, obj)
            elif kind == "group":
                _add_group_item(entry)
            elif kind == "forge":
                _add_forge_item(entry.get("name", ""))

        item_to_select = selected_item or fallback_item
        if item_to_select is not None:
            self.tree.setCurrentItem(item_to_select)
        else:
            self._clear_detail()
        self._loading_tree = False
        if hasattr(self, "source_tree"):
            self._refresh_source_tree(objects)

    def _refresh_source_tree(self, objects: list[QueryObject] | None = None) -> None:
        if not hasattr(self, "source_tree"):
            return
        current_payload = _payload(self.source_tree.currentItem())
        search_text = self.edit_source_search.text() if hasattr(self, "edit_source_search") else ""
        search_active = bool(search_text.strip())
        self._loading_source_tree = True
        self.source_tree.clear()
        objects = objects if objects is not None else query_object_store.list_objects()
        index = self._build_data_source_index(objects)

        selected_item = None

        def _track(item: QTreeWidgetItem, payload: dict) -> None:
            nonlocal selected_item
            if not current_payload or payload.get("type") != current_payload.get("type"):
                return
            keys = {
                "odbc_source": ("dsn",),
                "registered_odbc": ("data_source_id",),
                "access_source": ("data_source_id",),
                "file_source": ("key",),
                "file_data_source": ("key",),
                "query": ("id", "source_key"),
                "source_query": ("id", "source_key"),
                "source_group": ("group",),
            }.get(payload.get("type"), ())
            if keys and all(payload.get(key) == current_payload.get(key) for key in keys):
                selected_item = item

        def _add_query_leaf(parent: QTreeWidgetItem, obj: QueryObject, source_key: str) -> None:
            style = mode_style(obj.kind)
            dsn = _display_dsn_for_object(obj) or obj.source_design or "?"
            item = QTreeWidgetItem([f"{obj.name}  [{dsn}]"])
            item.setFont(0, _FONT)
            item.setForeground(0, QColor("#000000"))
            item.setToolTip(0, f"{style.label} - {dsn}")
            payload = {
                "type": "query",
                "id": obj.id,
                "name": obj.name,
                "source_key": source_key,
                "source_tree": True,
                "badge": _QUERY_BADGES.get(obj.kind, "Q"),
                "badge_color": style.color,
                "badge_fill": style.color,
                "badge_text_color": "#FFFFFF",
            }
            item.setData(0, Qt.ItemDataRole.UserRole, payload)
            parent.addChild(item)
            _track(item, payload)

        def _filtered_source_objects(source: dict) -> list[QueryObject]:
            source_values = [
                source.get("label", ""), source.get("path", ""),
                source.get("source_type", ""), source.get("group", ""),
            ]
            source_matches = self._text_matches_search(search_text, source_values)
            if source_matches:
                return list(source.get("objects", []))
            return [
                obj for obj in source.get("objects", [])
                if self._object_matches_search(obj, search_text)
            ]

        def _add_group(group_key: str, title: str, sources: list[dict]) -> None:
            visible_sources: list[tuple[dict, list[QueryObject]]] = []
            for source in sources:
                children = _filtered_source_objects(source)
                source_matches = self._text_matches_search(search_text, [
                    source.get("label", ""), source.get("path", ""),
                    source.get("source_type", ""), title,
                ])
                if not search_active or source_matches or children:
                    visible_sources.append((source, children))
            if not visible_sources:
                return
            root = QTreeWidgetItem([f"{title} ({len(visible_sources)})"])
            root.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))
            root.setForeground(0, QColor("#000000"))
            root.setBackground(0, QBrush(QColor("#E8F0FB")))
            payload = {"type": "source_group", "group": group_key}
            root.setData(0, Qt.ItemDataRole.UserRole, payload)
            self.source_tree.addTopLevelItem(root)
            _track(root, payload)
            src_color = {"odbc": "#1E5BA8", "access": "#8B5E00",
                         "file_sources": "#4D7C0F"}.get(group_key, "#8B6914")
            src_type = {"odbc": "odbc_source", "access": "access_source",
                        "file_sources": "file_data_source"}.get(group_key, "file_source")
            for source, children in visible_sources:
                label = source.get("label", "")
                node_type = source.get("node_type") or src_type
                registered = bool(source.get("registered"))
                source_item = QTreeWidgetItem([label])
                source_item.setFont(0, _FONT_BOLD)
                source_item.setForeground(0, QColor("#000000"))
                tooltip = source.get("path") or source.get("dsn") or label
                if group_key == "file_sources":
                    tooltip = "Double-click to edit this File Source"
                elif registered:
                    tooltip = f"Registered ODBC source â€” DSN {source.get('dsn', '')}"
                source_item.setToolTip(0, tooltip)
                source_payload = {
                    "type": node_type,
                    "group": group_key,
                    "key": source.get("key", ""),
                    "dsn": source.get("dsn", ""),
                    "path": source.get("path", ""),
                    "label": label,
                    "registered": registered,
                    "source_type": source.get("source_type", ""),
                    "metadata": source.get("metadata", {}),
                    "file_source_id": source.get("file_source_id", ""),
                    "data_source_id": source.get("data_source_id", ""),
                    "object_ids": [obj.id for obj in source.get("objects", [])],
                }
                source_item.setData(0, Qt.ItemDataRole.UserRole, source_payload)
                root.addChild(source_item)
                _track(source_item, source_payload)
                if group_key == "file_sources":
                    for table_name, member_path in source.get("members", []):
                        member_item = QTreeWidgetItem([_filename_from_path(member_path)])
                        member_item.setFont(0, _FONT)
                        member_item.setForeground(0, QColor("#000000"))
                        member_item.setData(0, Qt.ItemDataRole.UserRole,
                                            {"type": "file_member", "label": table_name,
                                             "path": member_path})
                        source_item.addChild(member_item)
                source_item.setExpanded(search_active or group_key == "file_sources")
            root.setExpanded(True)

        _add_group("odbc", "ODBC", sorted(index["odbc"].values(), key=lambda item: item["label"].lower()))
        _add_group("access", "MS Access", sorted(index["access"].values(), key=lambda item: item["label"].lower()))
        _add_group("file_sources", "File Sources", sorted(index["file_sources"].values(), key=lambda item: item["label"].lower()))

        if selected_item is not None:
            self.source_tree.setCurrentItem(selected_item)
        self._loading_source_tree = False

    def _build_data_source_index(self, objects: list[QueryObject]) -> dict[str, dict[str, dict]]:

        index: dict[str, dict[str, dict]] = {
            "odbc": {}, "access": {}, "files": {}, "file_sources": {}}

        # Registered ODBC / Access sources are pinned â€” they show whether or not
        # a query targets them yet (the whole point of "Add Data Source").
        for ds in data_source_store.list_data_sources():
            if ds.kind == KIND_ODBC and ds.dsn.strip():
                index["odbc"][ds.dsn.strip().lower()] = {
                    "group": "odbc",
                    "key": ds.dsn.strip().lower(),
                    "label": f"{ds.name}  [{datasource_kind_label(ds)}]",
                    "dsn": ds.dsn.strip(),
                    "node_type": "registered_odbc",
                    "registered": True,
                    "data_source_id": ds.id,
                    "objects": [],
                }
            elif ds.kind == KIND_ACCESS and ds.path.strip():
                index["access"][ds.id] = {
                    "group": "access",
                    "key": ds.id,
                    "label": f"{ds.name}  [{datasource_kind_label(ds)}]",
                    "path": ds.path,
                    "node_type": "access_source",
                    "registered": True,
                    "data_source_id": ds.id,
                    "objects": [],
                }

        # Saved File Sources are their own store entity (peer of a DSN) â€” show
        # them whether or not a query targets them yet.
        for fds in file_source_store.list_file_sources():
            index["file_sources"][fds.id] = {
                "group": "file_sources",
                "key": fds.id,
                "label": f"{fds.name}  [{datasource_label(fds)}]",
                "file_source_id": fds.id,
                "members": [(m.resolved_table_name(), m.path) for m in fds.members],
                "objects": [],
            }

        for obj in objects:
            fs_id = self._file_source_id_for_object(obj)
            if fs_id and fs_id in index["file_sources"]:
                # A query that targets a File Source belongs under it, not ODBC.
                entry = index["file_sources"][fs_id]
                if all(existing.id != obj.id for existing in entry["objects"]):
                    entry["objects"].append(obj)
                continue
            for dsn in self._odbc_dsns_for_object(obj):
                entry = index["odbc"].setdefault(dsn.lower(), {
                    "group": "odbc",
                    "key": dsn.lower(),
                    "label": dsn,
                    "dsn": dsn,
                    "objects": [],
                })
                if all(existing.id != obj.id for existing in entry["objects"]):
                    entry["objects"].append(obj)

            for file_entry in self._file_sources_for_object(obj):
                key = file_entry["key"]
                entry = index["files"].setdefault(key, {
                    "group": "files",
                    "key": key,
                    "label": file_entry["label"],
                    "path": file_entry["path"],
                    "source_type": file_entry["source_type"],
                    "metadata": file_entry["metadata"],
                    "objects": [],
                })
                if all(existing.id != obj.id for existing in entry["objects"]):
                    entry["objects"].append(obj)

        for group in index.values():
            for entry in group.values():
                entry["objects"].sort(key=lambda item: item.name.lower())
        return index

    @staticmethod
    def _file_source_id_for_object(obj: QueryObject) -> str:
        """The FileDataSource id a query targets (``file:<id>`` dsn or config)."""
        dsn = (obj.dsn or "").strip()
        if dsn.startswith("file:"):
            return dsn[len("file:"):]
        return str((obj.config or {}).get("file_source_id", "")).strip()

    @staticmethod
    def _odbc_dsns_for_object(obj: QueryObject) -> list[str]:
        if obj.kind == OBJECT_KIND_ADHOC_SOURCE:
            return []
        if (obj.dsn or "").strip().startswith("file:"):
            return []  # file-backed query â€” listed under File Sources, not ODBC
        dsns: set[str] = set()
        if obj.dsn.strip():
            dsns.add(obj.dsn.strip())
        for source in obj.sources:
            dsn = source.dsn.strip()
            if dsn and not dsn.startswith(("file:", "list:")):
                dsns.add(dsn)
        return sorted(dsns, key=str.lower)

    @staticmethod
    def _file_sources_for_object(obj: QueryObject) -> list[dict]:
        entries: list[dict] = []
        for source in obj.sources:
            metadata = dict(source.metadata or {})
            path = str(metadata.get("path", "")).strip()
            source_type = (source.source_type or obj.source_design or "").strip().lower()
            if obj.kind != OBJECT_KIND_ADHOC_SOURCE and not path and source_type not in _FILE_SOURCE_TYPES:
                continue
            label = _filename_from_path(path or source.name or obj.name)
            entries.append({
                "key": _file_source_key(path, source.name or obj.name),
                "label": label,
                "path": path,
                "source_type": source_type or source.source_type or obj.source_design,
                "metadata": metadata,
                "source_name": source.name,
                "status": source.status,
            })
        if not entries and obj.kind == OBJECT_KIND_ADHOC_SOURCE:
            metadata = dict((obj.config or {}).get("source_metadata", {}) or {})
            path = str(metadata.get("path", "")).strip()
            entries.append({
                "key": _file_source_key(path, obj.name),
                "label": _filename_from_path(path or obj.name),
                "path": path,
                "source_type": obj.source_design,
                "metadata": metadata,
                "source_name": obj.name,
                "status": obj.metadata_status,
            })
        return entries

    def _on_source_tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        payload = _payload(item)
        if payload.get("type") == "source_group":
            item.setExpanded(not item.isExpanded())

    def _on_source_tree_selection(self, current, previous) -> None:
        if self._loading_source_tree:
            return
        self._offer_to_save_file_source_edits()
        self._route_source_selection(current)

    def _offer_to_save_file_source_edits(self) -> None:
        """If a File Source has unsaved edits, offer to Save before navigating away.

        Navigation guard â€” it never blocks navigation, it just asks whether to persist
        the draft first (Save) or drop it (Discard)."""
        dash = self._source_dashboard
        if self._current_source_kind != "file_data_source" or not dash.is_dirty():
            return
        if self._current_file_source is None or not self._current_file_source.members:
            return
        reply = QMessageBox.question(
            self, "Unsaved File Source",
            f'"{dash.editable_name() or "This File Source"}" has unsaved changes. '
            "Save them before leaving?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard,
            QMessageBox.StandardButton.Save)
        if reply == QMessageBox.StandardButton.Save:
            self._on_source_save()
        dash.set_dirty(False)

    def _route_source_selection(self, current) -> None:
        """Show a source node in the dashboard, a query node in the detail canvas."""
        payload = _payload(current)
        payload_type = payload.get("type")
        if payload_type in {"query", "source_query"}:
            obj = query_object_store.load_object_by_id(payload.get("id", ""))
            if obj is not None:
                self._browser_canvas_stack.setCurrentWidget(self._detail_canvas)
                self._show_detail(obj)
                return
        if payload_type in {"odbc_source", "registered_odbc", "access_source",
                            "file_data_source", "file_source"}:
            self._browser_canvas_stack.setCurrentWidget(self._source_dashboard)
            if payload_type == "registered_odbc":
                self._show_registered_odbc_detail(payload)
            elif payload_type == "access_source":
                self._show_access_source_detail(payload)
            elif payload_type == "odbc_source":
                self._show_odbc_source_detail(payload)
            elif payload_type == "file_data_source":
                self._show_file_data_source_detail(payload)
            else:
                self._show_file_source_detail(payload)
            return
        if payload_type == "file_member" and current is not None and current.parent() is not None:
            self._route_source_selection(current.parent())
            return
        # A group node or empty selection: nothing to inspect.
        self._browser_canvas_stack.setCurrentWidget(self._source_dashboard)
        self._reset_current_source()
        self._source_dashboard.show_empty("Select a data source")
        self._update_data_sources_canvas_title()

    def _reset_current_source(self) -> None:
        self._current_source_kind = ""
        self._current_source_payload = {}
        self._current_file_source = None
        self._current_data_source = None
        self._current_source_path = ""

    def _on_source_tree_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        payload = _payload(item)
        if payload.get("type") == "file_data_source":
            # The dashboard already IS the editor â€” single-click selects + shows it.
            self._route_source_selection(item)
            return
        if payload.get("type") not in {"query", "source_query"}:
            return
        obj = query_object_store.load_object_by_id(payload.get("id", ""))
        if obj is None:
            return
        self._show_detail(obj)
        if self._current is not None and self._can_open_in_builder(self._current):
            self._on_open_builder()

    def _on_source_tree_context_menu(self, pos) -> None:
        """Right-click a File Source node to delete it."""
        item = self.source_tree.itemAt(pos)
        if item is None:
            return
        payload = _payload(item)
        if payload.get("type") != "file_data_source":
            return
        menu = QMenu(self.source_tree)
        delete_action = menu.addAction("Delete File Source")
        chosen = menu.exec(self.source_tree.viewport().mapToGlobal(pos))
        if chosen is delete_action:
            self._delete_file_source_by_payload(payload)

    def _delete_file_source_by_payload(self, payload: dict) -> None:
        """Confirm and delete a File Source identified by a tree payload."""

        fs_id = str(payload.get("file_source_id") or payload.get("key", "")).strip()
        fds = file_source_store.load_file_source_by_id(fs_id)
        if fds is None:
            return
        objects = self._objects_from_payload(payload)
        extra = (f"\n\n{len(objects)} query object(s) target it and will stop "
                 "resolving.") if objects else ""
        reply = QMessageBox.question(
            self,
            "Delete File Source",
            f'Delete File Source "{fds.name}"?{extra}\n\n'
            "This removes the source definition, not the underlying files.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        file_source_store.delete_file_source_by_id(fds.id)
        self.refresh()
        self._reset_current_source()
        self._source_dashboard.show_empty("Select a data source")

    def _expanded_for_item(self, payload: dict, search_active: bool) -> bool:
        if search_active:
            return True
        if payload.get("type") == "group":
            return bool(payload.get("expanded", True))
        if payload.get("type") == "forge":
            organizer = get_query_organizer()
            ref = organizer.forge_ref(payload.get("name", ""))
            return bool((ref or {}).get("expanded", True))
        return False

    def _set_all_containers_expanded(self, expanded: bool) -> None:
        organizer = get_query_organizer()
        for entry in organizer.items:
            if entry.get("type") == "group":
                organizer.set_group_expanded(entry.get("id"), expanded)
            elif entry.get("type") == "forge":
                organizer.set_forge_expanded(entry.get("name", ""), expanded)
        organizer.save()
        self.refresh()

    def _on_tree_expansion_changed(self, item: QTreeWidgetItem, expanded: bool) -> None:
        if self._loading_tree:
            return
        payload = _payload(item)
        organizer = get_query_organizer()
        changed = False
        if payload.get("type") == "group":
            changed = organizer.set_group_expanded(payload.get("group_id"), expanded)
        elif payload.get("type") == "forge":
            changed = organizer.set_forge_expanded(payload.get("name", ""), expanded)
        if changed:
            organizer.save()

    def _on_tree_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        payload = _payload(item)
        if payload.get("type") in {"group", "forge"}:
            item.setExpanded(not item.isExpanded())

    @staticmethod
    def _load_left_panel_width() -> int:
        ui = load_ui_settings()
        width = ui.get("query_object_browser_left_width", _LEFT_PANEL_DEFAULT_WIDTH)
        if not isinstance(width, (int, float)):
            return _LEFT_PANEL_DEFAULT_WIDTH
        return max(_LEFT_PANEL_MIN_WIDTH, min(int(width), _LEFT_PANEL_MAX_WIDTH))

    def _save_left_panel_width(self) -> None:
        ui = load_ui_settings()
        ui["query_object_browser_left_width"] = self._left_panel_width
        save_ui_settings(ui)

    def _on_browser_splitter_moved(self, pos: int, index: int) -> None:
        if self._restoring_left_width:
            return
        handle = self._browser_splitter.handle(index)
        user_drag = bool(QApplication.mouseButtons() & Qt.MouseButton.LeftButton)
        if handle is None or not handle.underMouse() or not user_drag:
            QTimer.singleShot(0, self._apply_left_panel_width)
            return
        sizes = self._browser_splitter.sizes()
        if not sizes:
            return
        width = max(_LEFT_PANEL_MIN_WIDTH, min(int(sizes[0]), _LEFT_PANEL_MAX_WIDTH))
        self._left_panel_width = width
        self._save_left_panel_width()

    def _apply_left_panel_width(self) -> None:
        splitter = getattr(self, "_browser_splitter", None)
        if splitter is None:
            return
        sizes = splitter.sizes()
        total = sum(sizes) if sizes else 1120
        width = max(_LEFT_PANEL_MIN_WIDTH, min(self._left_panel_width, _LEFT_PANEL_MAX_WIDTH))
        self._restoring_left_width = True
        try:
            splitter.setSizes([width, max(_RIGHT_PANEL_MIN_WIDTH, total - width)])
        finally:
            self._restoring_left_width = False

    def _restore_left_panel_width(self) -> None:
        try:
            self._apply_left_panel_width()
        finally:
            self._restoring_left_width = False

    @staticmethod
    def _text_matches_search(search_text: str, values: list[object]) -> bool:
        terms = [term for term in search_text.lower().split() if term]
        if not terms:
            return True
        haystack = " ".join(str(value or "") for value in values).lower()
        return all(term in haystack for term in terms)

    @staticmethod
    def _object_matches_search(obj: QueryObject, search_text: str) -> bool:
        return QueryObjectViewerNavigationMixin._text_matches_search(search_text, [
            obj.name,
            _display_dsn_for_object(obj),
            _kind_label(obj.kind),
            obj.source_design,
            obj.description,
            " ".join(obj.tags),
        ])

    def _ensure_dataforge_query_objects(self) -> None:
        """Publish missing browser QueryObjects from saved DataForge definitions."""

        for forge in dataforge_store.list_forges():
            for source in forge.sources:
                definition = source.definition or {}
                copy_name = str(definition.get("name", "")).strip() or source.query_name
                if not copy_name:
                    continue
                source_label = self._definition_source_label(definition, source.query_name)
                existing = query_object_store.load_object(copy_name)
                if existing is not None and _dataforge_info(existing) is not None:
                    continue
                try:
                    if "kind" in definition:
                        obj = QueryObject.from_dict(definition)
                    else:
                        qd = QDefinition.from_dict(definition)
                        qd.forge_name = forge.name
                        obj = object_from_qdefinition(qd)
                except Exception:
                    logger.exception("Failed to repair DataForge QueryObject: %s", copy_name)
                    continue
                obj.name = copy_name
                obj.config = dict(obj.config or {})
                obj.config["dataforge"] = {
                    "forge_name": forge.name,
                    "source_name": source_label,
                }
                obj.source_design = obj.source_design or source_label
                query_object_store.save_object(obj)

    def select_object(self, name: str):
        """Refresh and select a Query Object by name if it exists."""
        self.refresh()

        def _select_under(item: QTreeWidgetItem) -> bool:
            payload = _payload(item)
            if payload.get("type") == "query" and payload.get("name") == name:
                self.tree.setCurrentItem(item)
                return True
            for index in range(item.childCount()):
                if _select_under(item.child(index)):
                    return True
            return False

        for i in range(self.tree.topLevelItemCount()):
            if _select_under(self.tree.topLevelItem(i)):
                return

    def _select_object(self, name: str):
        self.select_object(name)

    def _on_tree_selection(self, current, previous):
        self._update_group_action_buttons()
        saved_width = self._left_panel_width
        self._restoring_left_width = True
        payload = _payload(current)
        try:
            if payload.get("type") == "forge":
                self._clear_detail()
                return
            if payload.get("type") == "query":
                obj = query_object_store.load_object_by_id(payload.get("id", ""))
                if obj is not None:
                    self._show_detail(obj)
                    return
            self._clear_detail()
        finally:
            self._left_panel_width = saved_width
            QTimer.singleShot(0, self._restore_left_panel_width)
