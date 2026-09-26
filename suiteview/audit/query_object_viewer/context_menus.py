"""Organizer context-menu, create, rename, and drop methods."""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtWidgets import QAbstractItemView, QInputDialog, QMenu, QMessageBox

from suiteview.audit import qdef_store, query_object_store, saved_query_store
from suiteview.audit.dataforge import dataforge_store
from suiteview.audit.query_object import (
    OBJECT_KIND_VISUAL,
    QueryObject,
    qdefinition_from_query_object,
)
from suiteview.audit.query_object_viewer.common import _payload, logger
from suiteview.audit.query_organizer import COMMONS_GROUP_ID, get_query_organizer
from suiteview.ui.widgets.bookmark_widgets import ColorPickerPopup


class QueryObjectViewerOrganizerActionsMixin:
    """Requires BrowserState organizer/tree attributes; provides context actions."""

    def _selected_group_payload(self) -> dict:
        payload = _payload(self.tree.currentItem())
        return payload if payload.get("type") == "group" else {}

    def _selected_group_is_editable(self) -> bool:
        payload = self._selected_group_payload()
        return bool(payload and payload.get("group_id") != COMMONS_GROUP_ID)

    def _update_group_action_buttons(self) -> None:
        return

    def _on_rename_selected_group(self) -> None:
        payload = self._selected_group_payload()
        if not payload or payload.get("group_id") == COMMONS_GROUP_ID:
            return
        self._rename_group(payload)

    def _on_color_selected_group(self) -> None:
        payload = self._selected_group_payload()
        if not payload or payload.get("group_id") == COMMONS_GROUP_ID:
            return
        self._choose_group_color(payload)

    def _on_delete_selected_group(self) -> None:
        payload = self._selected_group_payload()
        if not payload or payload.get("group_id") == COMMONS_GROUP_ID:
            return
        self._delete_group_and_queries(payload)

    def _on_tree_double_clicked(self, item, column):
        payload = _payload(item)
        if payload.get("type") == "forge":
            self._open_dataforge_builder(payload.get("name", ""))
            return
        if payload.get("type") == "query":
            obj = query_object_store.load_object_by_id(payload.get("id", ""))
            if obj is not None and self._can_open_in_builder(obj):
                self._open_query_object_builder(obj.name)
            return
        if self._current is not None and self._can_open_in_builder(self._current):
            self._on_open_builder()

    def _show_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        payload = _payload(item)
        global_pos = self.tree.viewport().mapToGlobal(pos)

        # Background: organizer-level actions.
        if item is None or not payload:
            menu = QMenu(self)
            new_query, new_forge = self._add_creation_actions(menu)
            menu.addSeparator()
            new_group = menu.addAction("New Query Group...")
            chosen = menu.exec(global_pos)
            if self._handle_creation_action(chosen, new_query, new_forge):
                return
            if chosen == new_group:
                self._on_new_group()
            return

        self.tree.setCurrentItem(item)

        if payload["type"] == "group":
            self._group_context_menu(payload, global_pos)
        elif payload["type"] == "forge":
            self._forge_context_menu(payload, global_pos)
        elif payload.get("forge"):
            self._forge_query_context_menu(payload, global_pos)
        else:
            self._query_context_menu(payload, global_pos)

    def _group_context_menu(self, payload: dict, global_pos):
        group_id = payload["group_id"]
        menu = QMenu(self)
        is_commons = group_id == COMMONS_GROUP_ID
        rename = menu.addAction("Rename Group...")
        rename.setEnabled(not is_commons)
        color = menu.addAction("Group Color...")
        color.setEnabled(not is_commons)
        clone = menu.addAction("Clone Group (with queries)")
        clone.setEnabled(not is_commons)
        menu.addSeparator()
        new_query, new_forge = self._add_creation_actions(menu)
        new_group = menu.addAction("New Query Group...")
        menu.addSeparator()
        delete = menu.addAction("Delete Group and Queries")
        delete.setEnabled(not is_commons)

        chosen = menu.exec(global_pos)
        organizer = get_query_organizer()
        if chosen == rename:
            self._rename_group(payload)
        elif chosen == color:
            self._choose_group_color(payload)
        elif chosen == clone:
            organizer.clone_group(group_id)
            organizer.save()
            self.refresh()
        elif self._handle_creation_action(chosen, new_query, new_forge):
            return
        elif chosen == new_group:
            self._on_new_group()
        elif chosen == delete:
            self._delete_group_and_queries(payload)

    def _rename_group(self, payload: dict) -> None:
        group_id = payload.get("group_id")
        if group_id == COMMONS_GROUP_ID:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename Group", "Group name:", text=payload.get("name", ""))
        if ok and new_name.strip():
            organizer = get_query_organizer()
            organizer.rename_group(group_id, new_name)
            organizer.save()
            self.refresh()

    def _choose_group_color(self, payload: dict) -> None:
        group_id = payload.get("group_id")
        if group_id == COMMONS_GROUP_ID:
            return
        picker = ColorPickerPopup(self, payload.get("color"))
        picker.color_selected.connect(lambda color: self._set_group_color(group_id, color))
        picker.move(self.mapToGlobal(self.rect().center()))
        picker.show()

    def _set_group_color(self, group_id: int, color: str) -> None:
        organizer = get_query_organizer()
        if organizer.set_group_color(group_id, color):
            organizer.save()
            self.refresh()

    def _delete_group_and_queries(self, payload: dict) -> None:
        group_id = payload.get("group_id")
        if group_id == COMMONS_GROUP_ID:
            return
        organizer = get_query_organizer()
        group = organizer.find_group(group_id)
        if group is None:
            return
        query_ids = [child.get("query_id") for child in group.get("items", [])
                     if child.get("type") == "query" and child.get("query_id")]
        reply = QMessageBox.question(
            self,
            "Delete Query Group",
            f"Delete group \"{group.get('name', payload.get('name', ''))}\"?\n\n"
            f"All {len(query_ids)} query object(s) inside this group will be deleted. "
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for query_id in query_ids:
            query_object_store.delete_object_by_id(query_id)
        organizer.delete_group(group_id, keep_queries=False)
        organizer.save()
        self.refresh()
        self._clear_detail()

    def _forge_context_menu(self, payload: dict, global_pos):
        forge_name = payload["name"]
        menu = QMenu(self)
        open_forge = menu.addAction("Open DataForge in Builder")
        clone = menu.addAction("Clone DataForge (with Sources + Snapshots)")
        menu.addSeparator()
        delete_forge = menu.addAction("Delete DataForge")
        menu.addSeparator()
        new_query, new_forge = self._add_creation_actions(menu)

        chosen = menu.exec(global_pos)
        if chosen == open_forge:
            self._open_dataforge_builder(forge_name)
        elif chosen == clone:
            organizer = get_query_organizer()
            clone_name = organizer.clone_forge(forge_name)
            organizer.save()
            self._notify_forge_list_changed()
            self.refresh()
            if clone_name:
                QMessageBox.information(
                    self, "DataForge Cloned",
                    f"Created \"{clone_name}\" — Sources and Snapshots "
                    f"included, ready to run.")
        elif chosen == delete_forge:
            self._delete_dataforge(forge_name)
        elif self._handle_creation_action(chosen, new_query, new_forge):
            return

    def _query_context_menu(self, payload: dict, global_pos):
        obj = query_object_store.load_object_by_id(payload["id"])
        if obj is None:
            return
        organizer = get_query_organizer()

        menu = QMenu(self)
        open_new = menu.addAction("Open in New Window")
        open_new.setEnabled(self._can_open_in_builder(obj))
        menu.addSeparator()
        rename = menu.addAction("Rename")
        copy_here = menu.addAction("Copy")
        delete = menu.addAction("Delete")

        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen == open_new:
            self._open_query_object_in_new_builder(obj.name)
        elif chosen == rename:
            self._rename_query_object(obj)
        elif chosen == copy_here:
            organizer.copy_query(obj.id, organizer.query_location(obj.id))
            organizer.save()
            self.refresh()
        elif chosen == delete:
            self._delete_query_object(obj)

    def _rename_query_object(self, obj: QueryObject) -> None:
        new_name, ok = QInputDialog.getText(
            self, "Rename Query Object", "Object name:", text=obj.name)
        if not ok or not new_name.strip() or new_name.strip() == obj.name:
            return
        if obj.kind == OBJECT_KIND_VISUAL and query_object_store.object_exists(new_name.strip()):
            QMessageBox.warning(
                self,
                "Name Already Exists",
                f"A visual Query Object named \"{new_name.strip()}\" already exists.",
            )
            return
        query_object_store.rename_object(obj, new_name.strip())
        self.refresh()

    def _delete_query_object(self, obj: QueryObject) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Query Object",
            f"Delete query object \"{obj.name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        query_object_store.delete_object_by_id(obj.id)
        organizer = get_query_organizer()
        organizer.remove_query(obj.id)
        organizer.save()
        self.refresh()
        if self._current is not None and self._current.id == obj.id:
            self._clear_detail()

    def _forge_query_context_menu(self, payload: dict, global_pos):
        """Context menu for a Source copy inside a DataForge node."""
        forge_name = payload["forge"]
        obj = query_object_store.load_object_by_id(payload["id"])
        if obj is None:
            return
        menu = QMenu(self)
        rename = menu.addAction("Rename Source...")
        open_forge = menu.addAction("Open DataForge in Builder")
        open_new = menu.addAction("Open in New Window")
        open_new.setEnabled(self._can_open_in_builder(obj))
        menu.addSeparator()
        copy_out = menu.addAction("Copy out to Browser")
        move_out = menu.addAction("Move out to Browser")
        menu.addSeparator()
        remove = menu.addAction("Remove from DataForge")

        chosen = menu.exec(global_pos)
        organizer = get_query_organizer()
        if chosen == rename:
            self._rename_forge_query_object(forge_name, obj)
        elif chosen == open_forge:
            self._open_dataforge_builder(forge_name)
        elif chosen == open_new:
            self._open_query_object_in_new_builder(obj.name)
        elif chosen in (copy_out, move_out):
            out = organizer.extract_query_from_forge(
                forge_name, obj.name, remove_source=(chosen == move_out))
            if out is None:
                QMessageBox.warning(
                    self, "Extract Failed",
                    f"Could not find Source \"{obj.name}\" in "
                    f"\"{forge_name}\".")
                return
            if chosen == move_out:
                self._delete_forge_source_records(forge_name, obj)
            organizer.save()
            self.refresh()
        elif chosen == remove:
            reply = QMessageBox.question(
                self, "Remove from DataForge",
                f"Remove Source \"{obj.name}\" from \"{forge_name}\"?\n\n"
                "Its Snapshot and Forge-local copy are deleted.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._remove_source_from_forge(forge_name, obj)
                self.refresh()

    def _rename_forge_query_object(self, forge_name: str, obj: QueryObject) -> None:
        new_name, ok = QInputDialog.getText(
            self, "Rename DataForge Source", "Source name:", text=obj.name)
        new_name = new_name.strip()
        if not ok or not new_name or new_name == obj.name:
            return
        try:
            self._rename_forge_source_records(forge_name, obj, new_name)
        except ValueError as exc:
            QMessageBox.warning(self, "Rename Source Failed", str(exc))
            return
        self._notify_forge_list_changed()
        self.refresh()

    @staticmethod
    def _rename_forge_source_records(
            forge_name: str, obj: QueryObject, new_name: str) -> QueryObject:
        """Rename a Forge-local Source copy across the persisted stores."""
        new_name = new_name.strip()
        old_name = obj.name
        if not new_name:
            raise ValueError("Source name cannot be blank.")
        if new_name == old_name:
            return obj


        forge = dataforge_store.load_forge(forge_name)
        if forge is None:
            raise ValueError(f"DataForge \"{forge_name}\" was not found.")

        source = None
        for candidate in forge.sources:
            definition = candidate.definition or {}
            if (candidate.query_name == old_name
                    or candidate.effective_alias() == old_name
                    or definition.get("id") == obj.id):
                source = candidate
                break
        if source is None:
            raise ValueError(
                f"Source \"{old_name}\" was not found in \"{forge_name}\".")

        old_alias = source.effective_alias()
        new_alias = new_name if not source.alias or source.alias == old_name else source.alias
        for candidate in forge.sources:
            if candidate is source:
                continue
            if candidate.query_name == new_name or candidate.effective_alias() == new_alias:
                raise ValueError(
                    f"A Source named \"{new_name}\" already exists in \"{forge_name}\".")

        obj.name = new_name
        obj.updated_at = datetime.now()
        obj.config = dict(obj.config or {})
        dataforge_config = obj.config.get("dataforge", {})
        if not isinstance(dataforge_config, dict):
            dataforge_config = {}
        dataforge_config["forge_name"] = forge_name
        dataforge_config.setdefault("source_name", old_name)
        obj.config["dataforge"] = dataforge_config
        query_object_store.save_object(obj)
        # Move a visual Source's name-keyed design too (no-op if none).
        saved_query_store.rename_query(old_name, new_name)

        QueryObjectViewerOrganizerActionsMixin._delete_forge_qdef_file_only(forge_name, old_name)
        qd = qdefinition_from_query_object(obj)
        qd.forge_name = forge_name
        qdef_store.save_qdef(qd)

        source.query_name = new_name
        if source.alias == old_name:
            source.alias = new_name
        source.definition = obj.to_dict()

        mapping = {old_name: new_name}
        if old_alias != new_alias:
            mapping[old_alias] = new_alias
            QueryObjectViewerOrganizerActionsMixin._rename_forge_source_snapshot(
                forge_name, old_alias, new_alias)
        forge.config = QueryObjectViewerOrganizerActionsMixin._rename_forge_config_sources(
            dict(forge.config or {}), mapping)
        dataforge_store.save_forge(forge)
        return obj

    @staticmethod
    def _delete_forge_qdef_file_only(forge_name: str, qdef_name: str) -> None:

        qdef_store.delete_qdef_files(qdef_name, forge_name=forge_name)

    @staticmethod
    def _rename_forge_source_snapshot(forge_name: str, old_alias: str, new_alias: str) -> None:

        old_path = dataforge_store.source_snapshot_path(forge_name, old_alias)
        if not old_path.exists():
            return
        new_path = dataforge_store.source_snapshot_path(forge_name, new_alias)
        new_path.parent.mkdir(parents=True, exist_ok=True)
        if new_path.exists():
            raise ValueError(
                f"A Snapshot already exists for Source \"{new_alias}\".")
        old_path.replace(new_path)

    @staticmethod
    def _rename_forge_config_sources(value, mapping: dict[str, str]):
        if isinstance(value, dict):
            return {
                QueryObjectViewerOrganizerActionsMixin._rename_forge_config_sources(k, mapping):
                QueryObjectViewerOrganizerActionsMixin._rename_forge_config_sources(v, mapping)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [QueryObjectViewerOrganizerActionsMixin._rename_forge_config_sources(v, mapping)
                    for v in value]
        if isinstance(value, str):
            return QueryObjectViewerOrganizerActionsMixin._replace_forge_source_name(value, mapping)
        return value

    @staticmethod
    def _replace_forge_source_name(value: str, mapping: dict[str, str]) -> str:
        for old_name, new_name in sorted(mapping.items(), key=lambda pair: len(pair[0]), reverse=True):
            if value == old_name:
                return new_name
            if value.startswith(f"{old_name}."):
                return f"{new_name}{value[len(old_name):]}"
        return value

    # ── Organizer actions ─────────────────────────────────────────────

    def _container_targets(self, organizer) -> list[tuple[str, dict]]:
        """(label, target) pairs for the Move to / Copy to submenus."""

        targets: list[tuple[str, dict]] = [("Top level", {"root": True})]
        for entry in organizer.items:
            if entry.get("type") == "group":
                targets.append((f"Group: {entry['name']}",
                                {"group_id": entry["id"]}))
        for forge in dataforge_store.list_forges():
            targets.append((f"⚙ Forge: {forge.name}", {"forge": forge.name}))
        return targets

    def _send_query_to(self, obj: QueryObject, target: dict, *, move: bool):
        organizer = get_query_organizer()
        if target.get("forge"):
            ok = organizer.send_query_to_forge(obj.id, target["forge"],
                                               move=move)
            if not ok:
                QMessageBox.warning(self, "Add to DataForge Failed",
                                    f"Could not add \"{obj.name}\" to "
                                    f"\"{target['forge']}\".")
                return
            self._notify_forge_list_changed()
        elif move:
            organizer.move_query(obj.id, target.get("group_id"))
        else:
            organizer.copy_query(obj.id, target.get("group_id"))
        organizer.save()
        self.refresh()

    def _add_creation_actions(self, menu: QMenu):
        new_query = menu.addAction("New Query")
        new_forge = menu.addAction("New Forge")
        return new_query, new_forge

    def _handle_creation_action(self, chosen, new_query, new_forge) -> bool:
        if chosen == new_query:
            self._on_new_query()
            return True
        if chosen == new_forge:
            self._on_new_forge()
            return True
        return False

    def _on_new_query(self):
        parent = self._audit_window_for_builder()
        opener = getattr(parent, "_show_new_object_menu", None)
        if opener is None:
            QMessageBox.information(
                self,
                "Builder Unavailable",
                "Could not open the Query builder chooser.",
            )
            return
        opener()

    def _on_new_forge(self):
        self._open_dataforge_builder("")

    def _on_new_group(self):
        name, ok = QInputDialog.getText(self, "New Query Group", "Group name:")
        if not ok or not name.strip():
            return
        organizer = get_query_organizer()
        organizer.create_group(name)
        organizer.save()
        self.refresh()

    def _notify_forge_list_changed(self):
        parent = self._audit_parent or self.parent() or self._find_audit_window()
        refresher = getattr(parent, "_refresh_picker_forge_list", None)
        if callable(refresher):
            refresher()

    def _remove_source_from_forge(self, forge_name: str, obj: QueryObject):
        """Delete one Source (and its Snapshot + Forge-local copy records)."""

        forge = dataforge_store.load_forge(forge_name)
        if forge is not None:
            source = forge.source_by_alias(obj.name)
            if source is not None:
                forge.sources.remove(source)
                dataforge_store.save_forge(forge)
            dataforge_store.delete_source_snapshot(forge_name, obj.name)
        self._delete_forge_source_records(forge_name, obj)

    @staticmethod
    def _delete_forge_source_records(forge_name: str, obj: QueryObject):

        try:
            qdef_store.delete_qdef(obj.name, forge_name=forge_name)
        except Exception:
            logger.exception("Failed to delete DataForge QDefinition: %s",
                             obj.name)
        query_object_store.delete_object_by_id(obj.id)

    # ── Drag & drop (from _OrganizerTree) ─────────────────────────────

    def _handle_tree_drop(self, dragged, target, indicator):
        """Apply a tree drag-drop to the organizer, then rebuild."""
        src = _payload(dragged)
        dst = _payload(target)
        if not src or dragged is target:
            return
        on_item = indicator == QAbstractItemView.DropIndicatorPosition.OnItem
        organizer = get_query_organizer()

        if src["type"] == "query" and not src.get("forge"):
            self._handle_standalone_query_drop(
                src, dst, target, indicator, on_item, organizer)
            return

        if src["type"] == "query" and src.get("forge"):
            self._handle_forge_source_drop(src, dst, organizer)
            return

        if src["type"] in ("group", "forge"):
            self._handle_root_item_drop(src, target, indicator, organizer)

    def _handle_standalone_query_drop(
        self,
        src: dict,
        dst: dict,
        target,
        indicator,
        on_item: bool,
        organizer,
    ) -> None:
        obj = query_object_store.load_object_by_id(src["id"])
        if obj is None:
            return
        if on_item and dst.get("type") == "forge":
            self._drop_query_on_forge(obj, dst["name"])
        elif on_item and dst.get("type") == "group":
            organizer.move_query(obj.id, dst["group_id"])
            organizer.set_group_expanded(dst["group_id"], True)
        elif on_item and dst.get("type") == "query" and dst.get("forge"):
            self._drop_query_on_forge(obj, dst["forge"])
        else:
            group_id, index = self._drop_position(target, indicator)
            organizer.move_query(obj.id, group_id, index)
            if group_id is not None:
                organizer.set_group_expanded(group_id, True)
        organizer.save()
        self.refresh()

    def _handle_forge_source_drop(self, src: dict, dst: dict, organizer) -> None:
        obj = query_object_store.load_object_by_id(src["id"])
        if obj is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Out of DataForge")
        box.setText(f"Take \"{obj.name}\" out of \"{src['forge']}\"?")
        copy_btn = box.addButton("Copy out", QMessageBox.ButtonRole.AcceptRole)
        move_btn = box.addButton("Move out", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() not in (copy_btn, move_btn):
            return
        group_id = dst.get("group_id") if dst.get("type") == "group" else None
        out = organizer.extract_query_from_forge(
            src["forge"], obj.name, group_id,
            remove_source=(box.clickedButton() is move_btn))
        if out is not None and box.clickedButton() is move_btn:
            self._delete_forge_source_records(src["forge"], obj)
        if out is not None and group_id is not None:
            organizer.set_group_expanded(group_id, True)
        organizer.save()
        self.refresh()

    def _handle_root_item_drop(self, src: dict, target, indicator, organizer) -> None:
        entry = (organizer.find_group(src.get("group_id"))
                 if src["type"] == "group"
                 else organizer.forge_ref(src.get("name", "")))
        if entry is None:
            return
        _, index = self._drop_position(target, indicator, root_only=True)
        if src["type"] == "group":
            organizer.set_group_expanded(src.get("group_id"), False)
        else:
            organizer.set_forge_expanded(src.get("name", ""), False)
        organizer.move_root_item(entry, index)
        organizer.save()
        self.refresh()

    def _drop_query_on_forge(self, obj: QueryObject, forge_name: str):
        """A query dropped onto a Forge: ask whether to move or copy it in."""
        box = QMessageBox(self)
        box.setWindowTitle("Add to DataForge")
        box.setText(
            f"Add \"{obj.name}\" to DataForge \"{forge_name}\"?\n\n"
            "It becomes a Forge-local Source copy (Refresh it there to pull "
            "data). Move also removes the standalone query.")
        copy_btn = box.addButton("Copy in", QMessageBox.ButtonRole.AcceptRole)
        move_btn = box.addButton("Move in", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() not in (copy_btn, move_btn):
            return
        organizer = get_query_organizer()
        organizer.send_query_to_forge(obj.id, forge_name,
                                      move=box.clickedButton() is move_btn)
        organizer.set_forge_expanded(forge_name, True)
        self._notify_forge_list_changed()

    def _drop_position(self, target, indicator,
                       root_only: bool = False) -> tuple[int | None, int | None]:
        """Resolve a drop to (group_id or None=root, index or None=append)."""
        below = indicator == QAbstractItemView.DropIndicatorPosition.BelowItem
        if target is None:
            return None, None
        parent = target.parent()
        if parent is None:
            index = self.tree.indexOfTopLevelItem(target) + (1 if below else 0)
            dst = _payload(target)
            if (not root_only and indicator
                    == QAbstractItemView.DropIndicatorPosition.OnItem
                    and dst.get("type") == "group"):
                return dst["group_id"], None
            return None, index
        if root_only:
            return None, None
        parent_payload = _payload(parent)
        if parent_payload.get("type") == "group":
            index = parent.indexOfChild(target) + (1 if below else 0)
            return parent_payload["group_id"], index
        return None, None
