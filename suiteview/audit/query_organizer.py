"""
Query organizer — the user's free-form arrangement of Queries, Query Groups,
and DataForges shown by the Object Browser (DATAFORGE_DESIGN §8).

Modeled on the File Nav BookmarkDataManager: one JSON document holding an
ordered tree, persisted atomically. The organizer stores only *references*
(query ids, forge names) plus the user's grouping/order — query content lives
in query_object_store, forge content in dataforge_store.

Schema (~/.suiteview/query_organizer.json):

    {
      "next_group_id": 3,
      "items": [
        {"type": "query", "query_id": "ab12cd34…"},
        {"type": "group", "id": 1, "name": "Claims Work",
         "items": [{"type": "query", "query_id": "…"}]},
        {"type": "forge", "name": "ReinForge"}
      ]
    }

Rules:
- Root holds queries, groups, and forge refs. Groups hold queries only
  (one level — groups don't nest, mirroring bookmark categories).
- Reconcile keeps the document honest: refs to deleted queries/forges are
  pruned; unknown queries/forges on disk are appended (a query can never be
  lost by the organizer). Forge-owned query copies (config["dataforge"]) are
  NOT organized here — they render under their Forge.
- First run seeds groups named for the old build-type categories so the
  browser starts familiar.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from suiteview.core.json_store import read_json, write_json

from suiteview.audit import query_object_store
from suiteview.audit.query_object import (
    OBJECT_KIND_ADHOC_SOURCE,
    OBJECT_KIND_CYBERLIFE,
    OBJECT_KIND_EXECUTABLE,
    OBJECT_KIND_MANUAL_SQL,
    OBJECT_KIND_VISUAL,
    QueryObject,
)

logger = logging.getLogger(__name__)

ITEM_QUERY = "query"
ITEM_GROUP = "group"
ITEM_FORGE = "forge"
COMMONS_GROUP_ID = 0
COMMONS_GROUP_NAME = "Commons"
COMMONS_GROUP_COLOR = "#D8DEE8"
DEFAULT_GROUP_COLOR = "#CE93D8"

# Seed groups for first run — the old build-type categories, as groups the
# user is then free to rename/delete/reorganize.
_SEED_GROUPS = (
    (OBJECT_KIND_CYBERLIFE, "Cyberlife"),
    (OBJECT_KIND_VISUAL, "Visual Queries"),
    (OBJECT_KIND_MANUAL_SQL, "Manual SQL"),
    (OBJECT_KIND_ADHOC_SOURCE, "File Sources"),
    (OBJECT_KIND_EXECUTABLE, "Executable"),
)


def _organizer_path() -> Path:
    import os

    override = os.environ.get("SUITEVIEW_QUERY_ORGANIZER_FILE")
    if override:
        return Path(override)
    return Path.home() / ".suiteview" / "query_organizer.json"


def _is_forge_owned(obj: QueryObject) -> bool:
    """Forge-local Source copies are owned by their Forge, not the organizer."""
    return query_object_store.is_forge_owned(obj)


class QueryOrganizer:
    """Groups/order for the Object Browser. All query refs are by id."""

    def __init__(self, path: Path | None = None):
        self._path = path or _organizer_path()
        self._data: dict[str, Any] = {"next_group_id": 1, "items": []}
        self._loaded = False

    # ── Persistence ───────────────────────────────────────────────────

    def load(self) -> None:
        data = read_json(self._path, default=None)
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            self._data = data
            self._data.setdefault("next_group_id", 1)
        else:
            self._data = {"next_group_id": 1, "items": []}
        self._loaded = True

    def save(self) -> None:
        write_json(self._path, self._data)

    @property
    def exists_on_disk(self) -> bool:
        return self._path.exists()

    @property
    def items(self) -> list[dict]:
        """The ordered root items (mutable — call save() after edits)."""
        if not self._loaded:
            self.load()
        return self._data["items"]

    # ── Lookup ────────────────────────────────────────────────────────

    def find_group(self, group_id: int) -> dict | None:
        for item in self.items:
            if item.get("type") == ITEM_GROUP and item.get("id") == group_id:
                return item
        return None

    def commons_group(self) -> dict:
        self._ensure_commons()
        group = self.find_group(COMMONS_GROUP_ID)
        if group is None:
            raise RuntimeError("Commons group could not be created.")
        return group

    @staticmethod
    def is_commons_group(group: dict | None) -> bool:
        return bool(
            group
            and group.get("type") == ITEM_GROUP
            and group.get("id") == COMMONS_GROUP_ID
        )

    def group_names(self) -> list[str]:
        return [g["name"] for g in self.items if g.get("type") == ITEM_GROUP]

    def query_location(self, query_id: str) -> int | None:
        """The containing group id, or None when the query sits at root
        (or is not organized at all — check query_ref for that)."""
        for item in self.items:
            if item.get("type") == ITEM_GROUP:
                for child in item.get("items", []):
                    if child.get("query_id") == query_id:
                        if item.get("id") == COMMONS_GROUP_ID:
                            return None
                        return item["id"]
        return None

    def query_ref(self, query_id: str) -> dict | None:
        for item in self.items:
            if item.get("type") == ITEM_QUERY and item.get("query_id") == query_id:
                return item
            if item.get("type") == ITEM_GROUP:
                for child in item.get("items", []):
                    if child.get("query_id") == query_id:
                        return child
        return None

    def forge_ref(self, forge_name: str) -> dict | None:
        for item in self.items:
            if item.get("type") == ITEM_FORGE and item.get("name") == forge_name:
                return item
        return None

    # ── Groups ────────────────────────────────────────────────────────

    def create_group(self, name: str, index: int | None = None) -> dict:
        group = {"type": ITEM_GROUP, "id": self._data["next_group_id"],
                 "name": name.strip() or "New Group", "items": [],
                 "color": DEFAULT_GROUP_COLOR, "expanded": True}
        self._data["next_group_id"] += 1
        if index is None:
            self.items.append(group)
        else:
            self.items.insert(max(0, min(index, len(self.items))), group)
        return group

    def rename_group(self, group_id: int, new_name: str) -> bool:
        group = self.find_group(group_id)
        if self.is_commons_group(group):
            return False
        if group is None or not new_name.strip():
            return False
        group["name"] = new_name.strip()
        return True

    def set_group_color(self, group_id: int, color: str) -> bool:
        group = self.find_group(group_id)
        if group is None or self.is_commons_group(group):
            return False
        group["color"] = color or DEFAULT_GROUP_COLOR
        return True

    def set_group_expanded(self, group_id: int, expanded: bool) -> bool:
        group = self.find_group(group_id)
        if group is None:
            return False
        group["expanded"] = bool(expanded)
        return True

    def delete_group(self, group_id: int, *, keep_queries: bool = True) -> list[str]:
        """Remove a group. Returns the ids of the queries it contained.

        ``keep_queries=True`` moves the contained query refs to root (the
        queries themselves are untouched); ``False`` drops the refs — the
        caller is responsible for deleting the query objects too.
        """
        group = self.find_group(group_id)
        if self.is_commons_group(group):
            return []
        if group is None:
            return []
        contained = [c["query_id"] for c in group.get("items", [])
                     if c.get("type") == ITEM_QUERY]
        idx = self.items.index(group)
        self.items.pop(idx)
        if keep_queries:
            commons_items = self.commons_group().setdefault("items", [])
            for offset, query_id in enumerate(contained):
                commons_items.insert(offset, {"type": ITEM_QUERY, "query_id": query_id})
        return contained

    # ── Query refs ────────────────────────────────────────────────────

    def add_query(self, query_id: str, group_id: int | None = None,
                  index: int | None = None) -> dict:
        """Add a ref for a (new) query. Moves it if already organized."""
        self._ensure_commons()
        self.remove_query(query_id)
        ref = {"type": ITEM_QUERY, "query_id": query_id}
        target_group = self.find_group(group_id if group_id is not None else COMMONS_GROUP_ID)
        container = target_group.setdefault("items", []) if target_group is not None else self.commons_group()["items"]
        if index is None:
            container.append(ref)
        else:
            container.insert(max(0, min(index, len(container))), ref)
        return ref

    def remove_query(self, query_id: str) -> bool:
        for item in list(self.items):
            if item.get("type") == ITEM_QUERY and item.get("query_id") == query_id:
                self.items.remove(item)
                return True
            if item.get("type") == ITEM_GROUP:
                for child in list(item.get("items", [])):
                    if child.get("query_id") == query_id:
                        item["items"].remove(child)
                        return True
        return False

    def move_query(self, query_id: str, group_id: int | None = None,
                   index: int | None = None) -> None:
        """Move a query ref: root ⇄ group ⇄ group, with optional position."""
        self.add_query(query_id, group_id, index)

    def move_root_item(self, item: dict, index: int) -> None:
        """Reorder a root item (group/forge/loose query) to a new index."""
        if item in self.items:
            self.items.remove(item)
            target_index = max(0, min(index, len(self.items)))
            self.items.insert(target_index, item)

    # ── Forge refs ────────────────────────────────────────────────────

    def add_forge(self, forge_name: str, index: int | None = None) -> dict:
        existing = self.forge_ref(forge_name)
        if existing is not None:
            return existing
        ref = {"type": ITEM_FORGE, "name": forge_name, "expanded": True}
        if index is None:
            self.items.append(ref)
        else:
            self.items.insert(max(0, min(index, len(self.items))), ref)
        return ref

    def remove_forge(self, forge_name: str) -> bool:
        ref = self.forge_ref(forge_name)
        if ref is not None:
            self.items.remove(ref)
            return True
        return False

    def rename_forge(self, old_name: str, new_name: str) -> None:
        ref = self.forge_ref(old_name)
        if ref is not None:
            ref["name"] = new_name

    def set_forge_expanded(self, forge_name: str, expanded: bool) -> bool:
        ref = self.forge_ref(forge_name)
        if ref is None:
            return False
        ref["expanded"] = bool(expanded)
        return True

    # ── Reconcile (keep the document honest) ──────────────────────────

    def reconcile(self, objects: list[QueryObject],
                  forge_names: list[str]) -> bool:
        """Sync refs with reality. Returns True when anything changed.

        - Prunes refs whose query/forge no longer exists.
        - Appends queries/forges present on disk but not yet organized
          (forge-owned Source copies are skipped — they live under their
          Forge, fed by dataforge_store).
        - On very first run (no file yet), seeds build-type groups so the
          browser starts looking like the old kind-based view.
        """
        organizable = [o for o in objects if not _is_forge_owned(o)]
        known_ids = {o.id for o in organizable}
        forge_set = set(forge_names)
        changed = False

        first_run = not self._loaded and not self.exists_on_disk
        if not self._loaded:
            self.load()

        changed = self._ensure_commons() or changed

        if first_run and organizable:
            self._seed_from_kinds(organizable)
            self._data["seeded"] = True
            changed = True

        # Prune dead refs.
        for item in list(self.items):
            kind = item.get("type")
            if kind == ITEM_QUERY and item.get("query_id") not in known_ids:
                self.items.remove(item)
                changed = True
            elif kind == ITEM_FORGE and item.get("name") not in forge_set:
                self.items.remove(item)
                changed = True
            elif kind == ITEM_GROUP:
                for child in list(item.get("items", [])):
                    if child.get("query_id") not in known_ids:
                        item["items"].remove(child)
                        changed = True

        # Append anything on disk that isn't organized yet.
        organized = {ref.get("query_id") for ref in self._all_query_refs()}
        commons_items = self.commons_group().setdefault("items", [])
        for obj in organizable:
            if obj.id not in organized:
                commons_items.append({"type": ITEM_QUERY, "query_id": obj.id})
                changed = True
        listed_forges = {i.get("name") for i in self.items
                         if i.get("type") == ITEM_FORGE}
        for forge_name in forge_names:
            if forge_name not in listed_forges:
                self.items.append({"type": ITEM_FORGE, "name": forge_name, "expanded": True})
                changed = True

        return changed

    def _ensure_commons(self) -> bool:
        """Ensure the permanent Commons group exists and owns loose queries."""
        if not self._loaded:
            self.load()

        changed = False
        commons = None
        for item in self.items:
            if (item.get("type") == ITEM_GROUP
                    and (item.get("id") == COMMONS_GROUP_ID
                         or item.get("name") == COMMONS_GROUP_NAME
                         or item.get("system") == "commons")):
                commons = item
                break

        if commons is None:
            commons = {
                "type": ITEM_GROUP,
                "id": COMMONS_GROUP_ID,
                "name": COMMONS_GROUP_NAME,
                "system": "commons",
                "color": COMMONS_GROUP_COLOR,
                "expanded": True,
                "items": [],
            }
            self.items.insert(0, commons)
            changed = True
        else:
            expected = {
                "id": COMMONS_GROUP_ID,
                "name": COMMONS_GROUP_NAME,
                "system": "commons",
                "color": COMMONS_GROUP_COLOR,
            }
            for key, value in expected.items():
                if commons.get(key) != value:
                    commons[key] = value
                    changed = True
            if "items" not in commons:
                commons["items"] = []
                changed = True
            if "expanded" not in commons:
                commons["expanded"] = True
                changed = True

        loose_refs = [item for item in list(self.items)
                      if item.get("type") == ITEM_QUERY]
        if loose_refs:
            for ref in loose_refs:
                self.items.remove(ref)
                commons["items"].append(ref)
            changed = True

        for item in self.items:
            if item.get("type") == ITEM_GROUP and not self.is_commons_group(item):
                for key, value in {
                    "color": DEFAULT_GROUP_COLOR,
                    "expanded": True,
                    "items": [],
                }.items():
                    if key not in item:
                        item[key] = value
                        changed = True
            elif item.get("type") == ITEM_FORGE:
                if "expanded" not in item:
                    item["expanded"] = True
                    changed = True
        return changed

    def _all_query_refs(self) -> list[dict]:
        refs: list[dict] = []
        for item in self.items:
            if item.get("type") == ITEM_QUERY:
                refs.append(item)
            elif item.get("type") == ITEM_GROUP:
                refs.extend(c for c in item.get("items", [])
                            if c.get("type") == ITEM_QUERY)
        return refs

    def _seed_from_kinds(self, objects: list[QueryObject]) -> None:
        by_kind: dict[str, list[QueryObject]] = {}
        for obj in objects:
            by_kind.setdefault(obj.kind, []).append(obj)
        for kind, label in _SEED_GROUPS:
            members = by_kind.get(kind, [])
            if not members:
                continue
            group = self.create_group(label)
            group["items"] = [{"type": ITEM_QUERY, "query_id": o.id}
                              for o in sorted(members,
                                              key=lambda o: o.name.lower())]

    # ── Cross-store orchestration (browser actions) ───────────────────

    def copy_query(self, query_id: str, group_id: int | None = None,
                   index: int | None = None) -> QueryObject:
        """Copy a query (new id, name may repeat) into root or a group."""
        copied = query_object_store.copy_object_by_id(query_id)
        self.add_query(copied.id, group_id, index)
        return copied

    def clone_group(self, group_id: int) -> dict | None:
        """Clone a group AND deep-copy every query it contains (new ids)."""
        group = self.find_group(group_id)
        if group is None:
            return None
        clone = self.create_group(self._unique_group_name(group["name"]),
                                  index=self.items.index(group) + 1)
        for child in group.get("items", []):
            try:
                copied = query_object_store.copy_object_by_id(child["query_id"])
            except ValueError:
                logger.warning("Clone skipped a missing query: %s",
                               child.get("query_id"))
                continue
            clone["items"].append({"type": ITEM_QUERY, "query_id": copied.id})
        return clone

    def _unique_group_name(self, base: str) -> str:
        names = set(self.group_names())
        if base not in names:
            return base
        suffix = 2
        while f"{base} ({suffix})" in names:
            suffix += 1
        return f"{base} ({suffix})"

    # ── Forge membership (queries in/out of a DataForge) ──────────────

    def send_query_to_forge(self, query_id: str, forge_name: str,
                            *, move: bool = False) -> bool:
        """Copy (or move) a query into a Forge as an editable-copy Source.

        Copy keeps the standalone query; move removes it (Sources are
        self-contained copies, so nothing dangles — see DATAFORGE_DESIGN §2).
        """
        from suiteview.audit import qdef_store
        from suiteview.audit.query_object import qdefinition_from_query_object
        from suiteview.audit.dataforge import dataforge_store
        from suiteview.audit.dataforge.dataforge_model import DataForgeSource

        obj = query_object_store.load_object_by_id(query_id)
        forge = dataforge_store.load_forge(forge_name)
        if obj is None or forge is None:
            return False

        dataforge_config = (obj.config or {}).get("dataforge", {})
        if not isinstance(dataforge_config, dict):
            dataforge_config = {}
        original_name = (
            str(dataforge_config.get("source_name", "")).strip() or obj.name
        )
        copy_name = f"{original_name} [{forge.name}]"

        copied = query_object_store.load_object(copy_name)
        if copied is None:
            try:
                copied = query_object_store.copy_object_by_id(obj.id, copy_name)
            except ValueError:
                logger.exception(
                    "Failed to copy query object %s into DataForge %s",
                    obj.name,
                    forge.name,
                )
                return False

        copied.config = dict(copied.config or {})
        copied.config["dataforge"] = {
            "forge_name": forge.name,
            "source_name": original_name,
            "query_object_id": copied.id,
        }
        copied.config["query_object_id"] = copied.id
        copied.source_design = copied.source_design or original_name
        query_object_store.save_object(copied)

        qd = qdefinition_from_query_object(copied)
        qd.forge_name = forge.name
        qdef_store.save_qdef(qd)
        copied = query_object_store.load_object(copy_name) or copied

        forge.sources = [
            source for source in forge.sources
            if source.effective_alias() != copy_name
            and source.query_name != copy_name
        ]
        forge.sources.append(DataForgeSource(
            query_name=copy_name,
            query_object_id=copied.id,
            alias="",
            definition=copied.to_dict(),
        ))
        config = dict(forge.config or {})
        sources = [name for name in config.get("sources", []) if name != copy_name]
        sources.append(copy_name)
        config["sources"] = sources
        source_ids = [sid for sid in config.get("source_ids", []) if sid != copied.id]
        source_ids.append(copied.id)
        config["source_ids"] = source_ids
        forge.config = config
        dataforge_store.save_forge(forge)
        if move:
            query_object_store.delete_object_by_id(query_id)
            self.remove_query(query_id)
        return True

    def extract_query_from_forge(self, forge_name: str, alias: str,
                                 group_id: int | None = None,
                                 *, remove_source: bool = False) -> QueryObject | None:
        """Materialize a Forge Source as a standalone query (new id).

        Copies the Source's (Forge-local) definition out into the organizer;
        ``remove_source=True`` additionally removes the Source from the Forge
        (move semantics) along with its Snapshot.
        """
        from suiteview.audit.dataforge import dataforge_store

        forge = dataforge_store.load_forge(forge_name)
        if forge is None:
            return None
        source = forge.source_by_alias(alias)
        if source is None or not source.definition:
            return None
        obj = QueryObject.from_dict(dict(source.definition))
        from uuid import uuid4
        obj.id = uuid4().hex
        obj.config = {k: v for k, v in (obj.config or {}).items()
                      if k != "dataforge"}  # standalone now, not forge-owned
        query_object_store.save_object(obj, force_new=True)
        self.add_query(obj.id, group_id)
        if remove_source:
            forge.sources.remove(source)
            dataforge_store.save_forge(forge)
            dataforge_store.delete_source_snapshot(forge_name, alias)
        return obj

    def clone_forge(self, forge_name: str, new_name: str | None = None) -> str | None:
        """Clone a Forge: definition, every Source, and every Snapshot.

        The clone is immediately runnable (self-contained, like the original).
        Returns the clone's name, or None if the source Forge is missing.
        """
        from suiteview.audit.dataforge import dataforge_store
        from suiteview.audit.dataforge.dataforge_model import DataForge

        forge = dataforge_store.load_forge(forge_name)
        if forge is None:
            return None
        clone_name = (new_name or "").strip() or self._unique_forge_name(forge_name)
        clone = DataForge.from_dict(forge.to_dict())
        clone.name = clone_name
        if isinstance(clone.config, dict):
            clone.config["name"] = f"⚙ {clone_name}"
        dataforge_store.save_forge(clone)
        dataforge_store.copy_forge_snapshots(forge_name, clone_name)
        ref = self.forge_ref(forge_name)
        index = self.items.index(ref) + 1 if ref is not None else None
        self.add_forge(clone_name, index)
        return clone_name

    @staticmethod
    def _unique_forge_name(base: str) -> str:
        from suiteview.audit.dataforge import dataforge_store

        candidate = f"{base} (2)"
        suffix = 2
        while dataforge_store.forge_exists(candidate):
            suffix += 1
            candidate = f"{base} ({suffix})"
        return candidate


# ── Module singleton ──────────────────────────────────────────────────

_organizer: QueryOrganizer | None = None


def get_query_organizer() -> QueryOrganizer:
    global _organizer
    if _organizer is None:
        _organizer = QueryOrganizer()
    return _organizer
