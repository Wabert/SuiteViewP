"""
QueryObject persistence — id-keyed.

Storage: ~/.suiteview/query_objects/<safe_name>__<id8>.json — readable AND
collision-free, because query **names are no longer unique** (the organizer
and browser reference queries by ``QueryObject.id``; see DATAFORGE_DESIGN §8).
Tests and tools can override the directory with SUITEVIEW_QUERY_OBJECTS_DIR.

Legacy ``<name>.json`` files (pre-id) are migrated in place on first load:
an id is stamped, the file is rewritten under the new filename, and the old
file is removed — so ids are stable from the first time an object is seen.

Name-based APIs (``load_object``/``delete_object``/``object_exists``) remain
as compatibility seams for subsystems that still key by name (DataForge
Re-sync, qdef_store, saved visual designs); they resolve to the **newest
updated** object with that name. New code should use the ``*_by_id`` forms.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from suiteview.audit.query_object import OBJECT_KIND_VISUAL, QueryObject

logger = logging.getLogger(__name__)

_ID_SUFFIX_RE = re.compile(r"__([0-9a-f]{8})$")


def _objects_dir() -> Path:
    override = os.environ.get("SUITEVIEW_QUERY_OBJECTS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".suiteview" / "query_objects"


def _ensure_dir() -> Path:
    directory = _objects_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def object_path(query_object: QueryObject) -> Path:
    """The canonical on-disk path for an object (name + id8)."""
    return (_objects_dir()
            / f"{_safe_filename(query_object.name)}__{query_object.id[:8]}.json")


def _is_legacy_path(path: Path) -> bool:
    return not _ID_SUFFIX_RE.search(path.stem)


def _load_path(path: Path) -> QueryObject | None:
    """Load one file, migrating legacy (id-less) files in place.

    Migration persists immediately so the stamped id is stable — loading the
    same legacy file twice must not mint two different ids.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        logger.exception("Failed to load query object: %s", path)
        return None

    needs_migration = "id" not in data or _is_legacy_path(path)
    obj = QueryObject.from_dict(data)  # stamps an id if missing
    if needs_migration:
        try:
            target = object_path(obj)
            with open(target, "w", encoding="utf-8") as handle:
                json.dump(obj.to_dict(), handle, indent=2)
            if target != path:
                path.unlink(missing_ok=True)
            logger.info("Migrated query object to id storage: %s", target.name)
        except Exception:
            logger.exception("Failed to migrate query object: %s", path)
    return obj


def list_objects() -> list[QueryObject]:
    """Return all query objects sorted newest first (migrating legacy files)."""
    _ensure_dir()
    objects: list[QueryObject] = []
    for path in sorted(_objects_dir().glob("*.json")):
        obj = _load_path(path)
        if obj is not None:
            objects.append(obj)
    objects.sort(key=lambda obj: obj.updated_at, reverse=True)
    return objects


def load_object_by_id(object_id: str) -> QueryObject | None:
    """Load one query object by its permanent id."""
    if not object_id:
        return None
    _ensure_dir()
    for path in _objects_dir().glob(f"*__{object_id[:8]}.json"):
        obj = _load_path(path)
        if obj is not None and obj.id == object_id:
            return obj
    # Legacy/renamed fallback: full scan (also migrates stragglers).
    for obj in list_objects():
        if obj.id == object_id:
            return obj
    return None


def _objects_named(name: str) -> list[QueryObject]:
    """All objects with this exact name, newest-updated first.

    Filename matching is plain string prefix — NOT glob — because query names
    legally contain glob metacharacters (e.g. ``Trad CV [Forge]``).
    """
    _ensure_dir()
    safe = _safe_filename(name)
    matches: list[QueryObject] = []
    seen_ids: set[str] = set()
    for path in _objects_dir().glob("*.json"):
        stem = path.stem
        if not (stem == safe or
                (stem.startswith(f"{safe}__") and _ID_SUFFIX_RE.search(stem))):
            continue
        obj = _load_path(path)
        if obj is not None and obj.name == name and obj.id not in seen_ids:
            matches.append(obj)
            seen_ids.add(obj.id)
    matches.sort(key=lambda obj: obj.updated_at, reverse=True)
    return matches


def load_object(name: str) -> QueryObject | None:
    """Load one query object by name (compat seam).

    Names may be duplicated; this returns the newest-updated match so the
    name-based subsystems keep working. Prefer :func:`load_object_by_id`.
    """
    matches = _objects_named(name)
    return matches[0] if matches else None


def _find_path_by_id(object_id: str) -> Path | None:
    for path in _objects_dir().glob(f"*__{object_id[:8]}.json"):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                if json.load(handle).get("id") == object_id:
                    return path
        except Exception:
            continue
    return None


def save_object(query_object: QueryObject, *, force_new: bool = False) -> None:
    """Save or overwrite a query object (keyed by id; filename tracks name).

    Republish safety: factory functions mint a fresh id every time, and many
    flows rebuild an object from its design and save it again. Saving an
    object whose id is unknown on disk while its NAME already exists is a
    republish — it adopts the existing object's id and overwrites, exactly
    like the pre-id store did. Intentional duplicates (copy/clone, extract
    from a Forge) pass ``force_new=True`` to keep their fresh id.
    """
    _ensure_dir()
    if not query_object.id:
        query_object.id = uuid4().hex
    if not force_new and _find_path_by_id(query_object.id) is None:
        existing = _objects_named(query_object.name)
        if existing:
            query_object.id = existing[0].id
    target = object_path(query_object)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(query_object.to_dict(), handle, indent=2)

    # A rename moves the file: clear any other file carrying this id.
    for path in _objects_dir().glob(f"*__{query_object.id[:8]}.json"):
        if path == target:
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                stale = json.load(handle).get("id") == query_object.id
            if stale:
                path.unlink()
        except Exception:
            logger.exception("Failed to clean stale query object file: %s", path)
    # Pre-migration leftover for the same name (no id inside) is superseded.
    legacy = _objects_dir() / f"{_safe_filename(query_object.name)}.json"
    if legacy.exists():
        try:
            with open(legacy, "r", encoding="utf-8") as handle:
                legacy_without_id = "id" not in json.load(handle)
            if legacy_without_id:
                legacy.unlink()
        except Exception:
            logger.exception("Failed to clean legacy query object file: %s", legacy)


def copy_object_by_id(object_id: str, new_name: str | None = None) -> QueryObject:
    """Copy a query object; the copy gets its OWN id (and may keep the name).

    Duplicate names are legal — ids disambiguate. The one exception is a
    visual query: its designer snapshot (SavedQuery) is still name-keyed, so
    a visual copy auto-suffixes its name until that store migrates to ids.
    """
    source = load_object_by_id(object_id)
    if source is None:
        raise ValueError(f"Query object not found: id {object_id}")
    return _copy_from(source, new_name)


def copy_object(source_name: str, new_name: str) -> QueryObject:
    """Copy a query object by name (compat seam; newest match wins)."""
    source = load_object(source_name)
    if source is None:
        raise ValueError(f"Query object not found: {source_name}")
    clean = new_name.strip()
    if not clean:
        raise ValueError("New query object name cannot be blank.")
    return _copy_from(source, clean)


def _copy_from(source: QueryObject, new_name: str | None) -> QueryObject:
    copied = QueryObject.from_dict(source.to_dict())
    copied.id = uuid4().hex
    copied.name = (new_name or source.name).strip() or source.name
    if source.kind == OBJECT_KIND_VISUAL:
        # SavedQuery designs are name-keyed: a visual copy needs a free name.
        copied.name = _unique_visual_name(copied.name)
    # A copy gets its OWN creation time. Guard the back-to-back case where
    # datetime.now() lands in the same microsecond as the source's timestamp
    # (fast machine / immediate copy), so a copy is always strictly newer than
    # — and therefore distinguishable from — its original.
    copied.created_at = max(datetime.now(),
                            source.created_at + timedelta(microseconds=1))
    copied.updated_at = copied.created_at
    for source_ref in copied.sources:
        if source_ref.name == source.name:
            source_ref.name = copied.name
    for field in copied.fields:
        if field.source == source.name:
            field.source = copied.name
    _copy_saved_visual_design(source.name, copied.name, copied.created_at,
                              source.kind)
    # A copy is an intentional duplicate → force_new keeps its fresh id.
    # EXCEPT visual copies: copying the design above auto-published a twin
    # object under the (suffixed-unique) new name, so saving WITHOUT
    # force_new adopts that twin's id and overwrites it — one object, the
    # copy's content winning, exactly like the pre-id store.
    save_object(copied, force_new=(source.kind != OBJECT_KIND_VISUAL))
    return copied


def _unique_visual_name(base: str) -> str:
    from suiteview.audit import saved_query_store

    if not saved_query_store.query_exists(base) and not object_exists(base):
        return base
    suffix = 2
    while (saved_query_store.query_exists(f"{base} ({suffix})")
           or object_exists(f"{base} ({suffix})")):
        suffix += 1
    return f"{base} ({suffix})"


def _copy_saved_visual_design(source_name: str, new_name: str, created_at: datetime, kind: str) -> None:
    if kind != OBJECT_KIND_VISUAL:
        return
    try:
        from suiteview.audit import saved_query_store

        saved = saved_query_store.load_query(source_name)
        if saved is None:
            logger.warning("No saved visual design found while copying query object: %s", source_name)
            return
        if saved_query_store.query_exists(new_name):
            raise ValueError(f"A saved visual design named \"{new_name}\" already exists.")
        copied_saved = copy.deepcopy(saved)
        copied_saved.name = new_name
        copied_saved.created_at = created_at
        saved_query_store.save_query(copied_saved)
    except ValueError:
        raise
    except Exception:
        logger.exception("Failed to copy saved visual design for query object: %s", source_name)
        raise


def restore_saved_visual_design(query_object: QueryObject):
    """Restore a missing SavedQuery design from a visual QueryObject snapshot."""
    if query_object.kind != OBJECT_KIND_VISUAL or not query_object.config:
        return None
    try:
        from suiteview.audit import saved_query_store
        from suiteview.audit.saved_query import SavedQuery

        existing = saved_query_store.load_query(query_object.name)
        if existing is not None:
            return existing
        restored = SavedQuery(
            name=query_object.name,
            source_group=query_object.source_design,
            dsn=query_object.dsn,
            tables=[source.name for source in query_object.sources],
            config=query_object.config,
            sql=query_object.sql,
            result_columns=query_object.result_columns,
            column_types={field.name: field.data_type for field in query_object.fields if field.data_type},
            created_at=query_object.created_at,
        )
        saved_query_store.save_query(restored)
        save_object(query_object)
        return restored
    except Exception:
        logger.exception("Failed to restore saved visual design for query object: %s", query_object.name)
        raise


def delete_object_by_id(object_id: str) -> None:
    """Delete a query object by its permanent id."""
    obj = load_object_by_id(object_id)
    if obj is None:
        return
    path = object_path(obj)
    if path.exists():
        path.unlink()


def delete_object(name: str) -> None:
    """Delete a query object by name (compat seam).

    Acts on the same object :func:`load_object` would return (the newest
    match), so name-based load→delete flows stay symmetric. New code should
    use :func:`delete_object_by_id`.
    """
    obj = load_object(name)
    if obj is None:
        return
    path = object_path(obj)
    if path.exists():
        path.unlink()
    # Pre-migration file with this name, if any, is the same logical object.
    legacy = _objects_dir() / f"{_safe_filename(name)}.json"
    if legacy.exists():
        try:
            with open(legacy, "r", encoding="utf-8") as handle:
                if "id" not in json.load(handle):
                    legacy.unlink()
        except Exception:
            logger.exception("Failed to clean legacy query object file: %s", legacy)


def object_exists(name: str) -> bool:
    """Whether ANY query object has this name (names may be duplicated)."""
    return bool(_objects_named(name))
