"""
Join-canvas model — the pure, Qt-free state behind the MS-Access-style join
canvas (Phase 2).

The visual layer (forge_canvas_view.py) renders and mutates an instance of
:class:`JoinCanvasModel`; keeping the state here means the join logic
(relationships, multi-key grouping, serialization, conversion to engine specs)
is unit-testable without a display.

Vocabulary (DATAFORGE_DESIGN.md): each **Source** box lists its fields; drawing
a field-to-field line creates a join **key**; all the lines between the same two
boxes form one **relationship** (a :class:`CanvasJoin`) whose join *type*
(inner/left/right/outer) is set per relationship, exactly like MS Access.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .forge_engine import AppendSpec, JoinSpec, shared_append_columns

# Allowed relationship types (match forge_engine._JOIN_SQL keys we expose in UI).
JOIN_TYPES = ("inner", "left", "right", "outer")


@dataclass
class CanvasField:
    """One field shown in a Source box."""
    name: str
    data_type: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "data_type": self.data_type}

    @staticmethod
    def from_dict(d: dict) -> CanvasField:
        return CanvasField(name=d["name"], data_type=d.get("data_type", ""))


@dataclass
class CanvasSource:
    """A Source box on the canvas: an alias, its fields and its position."""
    alias: str
    fields: list[CanvasField] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    width: float = 184.0
    collapsed: bool = False
    visible_rows: int = 12
    scroll_offset: int = 0

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def has_field(self, name: str) -> bool:
        return any(f.name == name for f in self.fields)

    def to_dict(self) -> dict:
        return {
            "alias": self.alias,
            "fields": [f.to_dict() for f in self.fields],
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "collapsed": self.collapsed,
            "visible_rows": self.visible_rows,
            "scroll_offset": self.scroll_offset,
        }

    @staticmethod
    def from_dict(d: dict) -> CanvasSource:
        return CanvasSource(
            alias=d["alias"],
            fields=[CanvasField.from_dict(f) for f in d.get("fields", [])],
            x=float(d.get("x", 0.0)),
            y=float(d.get("y", 0.0)),
            width=max(140.0, float(d.get("width", 184.0))),
            collapsed=bool(d.get("collapsed", False)),
            visible_rows=max(3, int(d.get("visible_rows", 12))),
            scroll_offset=max(0, int(d.get("scroll_offset", 0))),
        )


@dataclass
class CanvasAppend:
    """An Append Table group box (design §9): a named UNION of member Sources.

    ``members`` are Source aliases in stack order (first in = bottom of the
    stack = the member whose column order defines the shared fields). Member
    Sources stay in the model's ``sources`` list (their fields define the
    shared set) but leave the join graph — the view hides their boxes and
    renders just their header bars inside this group.
    """
    name: str
    members: list[str] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    width: float = 220.0
    collapsed: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "members": list(self.members),
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "collapsed": self.collapsed,
        }

    @staticmethod
    def from_dict(d: dict) -> CanvasAppend:
        return CanvasAppend(
            name=d["name"],
            members=list(d.get("members", [])),
            x=float(d.get("x", 0.0)),
            y=float(d.get("y", 0.0)),
            width=max(160.0, float(d.get("width", 220.0))),
            collapsed=bool(d.get("collapsed", False)),
        )


@dataclass
class JoinKey:
    """One field-to-field link (one drawn line) within a relationship."""
    left_field: str
    right_field: str

    def to_dict(self) -> dict:
        return {"left_field": self.left_field, "right_field": self.right_field}

    @staticmethod
    def from_dict(d: dict) -> JoinKey:
        return JoinKey(left_field=d["left_field"], right_field=d["right_field"])


@dataclass
class CanvasJoin:
    """A relationship between two Source boxes (1+ keys, one join type)."""
    left_source: str
    right_source: str
    keys: list[JoinKey] = field(default_factory=list)
    how: str = "inner"
    enabled: bool = True

    def complete_keys(self) -> list[JoinKey]:
        return [k for k in self.keys if k.left_field and k.right_field]

    def to_dict(self) -> dict:
        return {
            "left_source": self.left_source,
            "right_source": self.right_source,
            "keys": [k.to_dict() for k in self.keys],
            "how": self.how,
            "enabled": self.enabled,
        }

    @staticmethod
    def from_dict(d: dict) -> CanvasJoin:
        return CanvasJoin(
            left_source=d["left_source"],
            right_source=d["right_source"],
            keys=[JoinKey.from_dict(k) for k in d.get("keys", [])],
            how=d.get("how", "inner"),
            enabled=d.get("enabled", True),
        )


class JoinCanvasModel:
    """Holds Source boxes + relationships; converts to engine specs / legacy ops.

    Pure data + logic — no Qt. The view keeps this in sync with what's drawn.
    """

    def __init__(self):
        self.sources: list[CanvasSource] = []
        self.joins: list[CanvasJoin] = []
        self.appends: list[CanvasAppend] = []

    # ── Sources ─────────────────────────────────────────────────────────

    def get_source(self, alias: str) -> CanvasSource | None:
        for s in self.sources:
            if s.alias == alias:
                return s
        return None

    def set_sources(self, names: list[str],
                    columns: dict[str, list[str]] | None = None,
                    types: dict[str, dict[str, str]] | None = None,
                    add_missing: bool = True) -> None:
        """Reconcile the box set to ``names``, preserving surviving boxes.

        New Sources are appended with a default cascading position; removed
        Sources (and any relationships touching them) are dropped; surviving
        Sources keep their position but refresh their field list.
        """
        columns = columns or {}
        types = types or {}
        keep = set(names)

        # Drop gone sources; prune them out of Append Tables too.
        self.sources = [s for s in self.sources if s.alias in keep]
        for ap in self.appends:
            ap.members = [m for m in ap.members if m in keep]
        # Joins may legally reference Append Tables as endpoints.
        join_names = keep | {ap.name for ap in self.appends}
        self.joins = [
            j for j in self.joins
            if j.left_source in join_names and j.right_source in join_names
        ]

        existing = {s.alias for s in self.sources}
        for i, name in enumerate(names):
            cols = columns.get(name, [])
            ctypes = types.get(name, {})
            fields = [CanvasField(c, ctypes.get(c, "")) for c in cols]
            src = self.get_source(name)
            if src is None:
                if not add_missing:
                    continue
                # Cascade new boxes so they don't stack exactly.
                self.sources.append(CanvasSource(
                    alias=name, fields=fields,
                    x=40 + 60 * len(existing), y=40 + 40 * len(existing)))
                existing.add(name)
            else:
                src.fields = fields
                src.scroll_offset = min(src.scroll_offset,
                                        max(0, len(src.fields) - src.visible_rows))

    def remove_source(self, alias: str) -> None:
        self.sources = [s for s in self.sources if s.alias != alias]
        self.joins = [
            j for j in self.joins
            if j.left_source != alias and j.right_source != alias
        ]
        for ap in self.appends:
            if alias in ap.members:
                ap.members.remove(alias)

    # ── Append Tables (design §9) ────────────────────────────────────────

    def get_append(self, name: str) -> CanvasAppend | None:
        for ap in self.appends:
            if ap.name == name:
                return ap
        return None

    def member_of(self, alias: str) -> str | None:
        """The Append Table this Source belongs to, or None."""
        for ap in self.appends:
            if alias in ap.members:
                return ap.name
        return None

    def add_append(self, name: str, x: float = 60.0,
                   y: float = 60.0) -> CanvasAppend:
        """Create a named, empty Append Table on the canvas."""
        clean = name.strip()
        if not clean:
            raise ValueError("An Append Table needs a name.")
        if self.get_append(clean) is not None:
            raise ValueError(
                f"The Append Table name {clean!r} is already used.")
        ap = CanvasAppend(name=clean, x=x, y=y)
        self.appends.append(ap)
        return ap

    def remove_append(self, name: str) -> None:
        """Delete an Append Table; its members become plain Sources again."""
        ap = self.get_append(name)
        if ap is None:
            return
        self.appends.remove(ap)
        self.joins = [j for j in self.joins
                      if name not in (j.left_source, j.right_source)]

    def rename_append(self, old: str, new: str) -> None:
        ap = self.get_append(old)
        clean = new.strip()
        if ap is None or not clean or clean == old:
            return
        if self.get_append(clean) is not None:
            raise ValueError(
                f"The Append Table name {clean!r} is already used.")
        ap.name = clean
        for j in self.joins:
            if j.left_source == old:
                j.left_source = clean
            if j.right_source == old:
                j.right_source = clean

    def add_member(self, append_name: str, alias: str) -> None:
        """Drop a Source into an Append Table.

        The Source leaves the join graph (its relationships are removed —
        the Append Table joins in its place) and its box collapses to a
        header bar inside the group.
        """
        ap = self.get_append(append_name)
        if ap is None:
            raise ValueError(f"No Append Table named {append_name!r}.")
        if self.get_source(alias) is None:
            raise ValueError(f"No Source named {alias!r} on the canvas.")
        owner = self.member_of(alias)
        if owner is not None:
            raise ValueError(
                f"{alias!r} is already inside Append Table {owner!r}.")
        if any(alias in (j.left_source, j.right_source) for j in self.joins):
            raise ValueError(
                f"{alias!r} already has joins. Delete those joins before "
                f"adding it to an Append Table.")
        ap.members.append(alias)
        self._prune_append_field_joins(append_name)

    def remove_member(self, append_name: str, alias: str) -> None:
        """Remove a Source from an Append Table without restoring its box."""
        ap = self.get_append(append_name)
        if ap is not None and alias in ap.members:
            ap.members.remove(alias)
            self.sources = [s for s in self.sources if s.alias != alias]
            self.joins = [j for j in self.joins
                          if alias not in (j.left_source, j.right_source)]
            self._prune_append_field_joins(append_name)

    def _prune_append_field_joins(self, append_name: str) -> None:
        """Drop join keys that no longer exist in an Append Table schema."""
        shared = {field.lower(): field for field in self.shared_fields(append_name)}
        if not shared:
            self.joins = [j for j in self.joins
                          if append_name not in (j.left_source, j.right_source)]
            return
        kept: list[CanvasJoin] = []
        for join in self.joins:
            if join.left_source == append_name:
                valid_keys = []
                for key in join.keys:
                    canonical = shared.get(key.left_field.lower())
                    if canonical is not None:
                        key.left_field = canonical
                        valid_keys.append(key)
                join.keys = valid_keys
            elif join.right_source == append_name:
                valid_keys = []
                for key in join.keys:
                    canonical = shared.get(key.right_field.lower())
                    if canonical is not None:
                        key.right_field = canonical
                        valid_keys.append(key)
                join.keys = valid_keys
            if join.keys:
                kept.append(join)
        self.joins = kept

    def shared_fields(self, append_name: str) -> list[str]:
        """The Append Table's schema: ordered intersection of member columns."""
        ap = self.get_append(append_name)
        if ap is None:
            return []
        schemas = {s.alias: s.field_names() for s in self.sources}
        return shared_append_columns(schemas, ap.members)

    def append_type_conflicts(self, append_name: str) -> dict[str, list[tuple[str, str]]]:
        """Shared fields whose member column types differ.

        The append still runs; the engine/pandas path coerces to a common
        representation. This returns enough detail for the view to warn without
        blocking the drop.
        """
        ap = self.get_append(append_name)
        if ap is None:
            return {}
        source_map = {s.alias: s for s in self.sources}
        conflicts: dict[str, list[tuple[str, str]]] = {}
        for field_name in self.shared_fields(append_name):
            seen: dict[str, list[tuple[str, str]]] = {}
            for member in ap.members:
                src = source_map.get(member)
                if src is None:
                    continue
                match = next((f for f in src.fields
                              if f.name.lower() == field_name.lower()), None)
                data_type = (match.data_type if match is not None else "").strip()
                if not data_type:
                    continue
                seen.setdefault(data_type.lower(), []).append((member, data_type))
            if len(seen) > 1:
                conflicts[field_name] = [entry for entries in seen.values()
                                         for entry in entries]
        return conflicts

    def fields_of(self, name: str) -> list[str]:
        """Joinable fields of a Source box OR an Append Table."""
        src = self.get_source(name)
        if src is not None:
            return src.field_names()
        if self.get_append(name) is not None:
            return self.shared_fields(name)
        return []

    def to_append_specs(self) -> list[AppendSpec]:
        """Engine specs for every Append Table with at least one member."""
        return [AppendSpec(alias=ap.name, members=tuple(ap.members))
                for ap in self.appends if ap.members]

    def to_config_appends(self) -> list[dict]:
        """Append dicts for DataForge.config (forge_runtime reads these)."""
        return [{"alias": ap.name, "members": list(ap.members)}
                for ap in self.appends if ap.members]

    def get_append_ops(self) -> list[dict]:
        """Append ops for the live pandas run path (pd.concat on shared cols)."""
        return [{"name": ap.name, "members": list(ap.members),
                 "columns": self.shared_fields(ap.name)}
                for ap in self.appends if ap.members]

    # ── Relationships / keys ─────────────────────────────────────────────

    def find_join(self, a: str, b: str) -> CanvasJoin | None:
        """Find the relationship between two Sources (unordered)."""
        for j in self.joins:
            if {j.left_source, j.right_source} == {a, b}:
                return j
        return None

    def add_link(self, src_a: str, field_a: str,
                 src_b: str, field_b: str) -> CanvasJoin:
        """Add a field-to-field key between two Sources.

        Reuses the existing relationship for the pair if present (keeping its
        orientation), else creates one. Self-joins and duplicate keys are
        rejected. Returns the affected relationship.
        """
        if src_a == src_b:
            raise ValueError("Cannot join a Source to itself.")
        for name in (src_a, src_b):
            if self.get_source(name) is None and self.get_append(name) is None:
                raise ValueError("Both Sources must exist on the canvas.")
            owner = self.member_of(name)
            if owner is not None:
                raise ValueError(
                    f"{name!r} is inside Append Table {owner!r} — draw the "
                    f"join from the Append Table's shared fields instead.")

        join = self.find_join(src_a, src_b)
        if join is None:
            join = CanvasJoin(left_source=src_a, right_source=src_b, keys=[])
            self.joins.append(join)

        # Orient the new key to the relationship's stored left/right.
        if join.left_source == src_a:
            key = JoinKey(field_a, field_b)
        else:
            key = JoinKey(field_b, field_a)

        if any(k.left_field == key.left_field
               and k.right_field == key.right_field for k in join.keys):
            return join  # duplicate key, no-op
        join.keys.append(key)
        return join

    def remove_key(self, a: str, b: str, key: JoinKey) -> None:
        """Remove one key from a relationship; drop the relationship if empty."""
        join = self.find_join(a, b)
        if join is None:
            return
        join.keys = [
            k for k in join.keys
            if not (k.left_field == key.left_field
                    and k.right_field == key.right_field)
        ]
        if not join.keys:
            self.joins.remove(join)

    def remove_join(self, a: str, b: str) -> None:
        join = self.find_join(a, b)
        if join is not None:
            self.joins.remove(join)

    def set_how(self, a: str, b: str, how: str) -> None:
        if how not in JOIN_TYPES:
            raise ValueError(f"Unknown join type {how!r}.")
        join = self.find_join(a, b)
        if join is not None:
            join.how = how

    def set_enabled(self, a: str, b: str, enabled: bool) -> None:
        join = self.find_join(a, b)
        if join is not None:
            join.enabled = enabled

    # ── Conversions ──────────────────────────────────────────────────────

    def to_join_specs(self) -> list[JoinSpec]:
        """Engine specs for every enabled relationship with complete keys."""
        specs: list[JoinSpec] = []
        for j in self.joins:
            if not j.enabled:
                continue
            keys = j.complete_keys()
            if not keys:
                continue
            specs.append(JoinSpec(
                left_source=j.left_source,
                right_source=j.right_source,
                left_keys=tuple(k.left_field for k in keys),
                right_keys=tuple(k.right_field for k in keys),
                how=j.how,
            ))
        return specs

    def to_config_joins(self) -> list[dict]:
        """Explicit join dicts for DataForge.config (forge_runtime reads these)."""
        joins: list[dict] = []
        for j in self.joins:
            keys = j.complete_keys()
            if not (j.enabled and keys):
                continue
            joins.append({
                "left_source": j.left_source,
                "right_source": j.right_source,
                "left_keys": [k.left_field for k in keys],
                "right_keys": [k.right_field for k in keys],
                "how": j.how,
            })
        return joins

    def get_merge_ops(self) -> list[dict]:
        """Legacy pandas merge-op dicts (backward compatible with the old tab).

        Single-key joins collapse left_on/right_on to scalars, matching
        ForgeJoinsTab.get_merge_ops so the current pandas _run_forge keeps
        working during the transition.
        """
        ops: list[dict] = []
        for j in self.joins:
            if not j.enabled:
                continue
            keys = j.complete_keys()
            if not keys:
                continue
            left_on = [k.left_field for k in keys]
            right_on = [k.right_field for k in keys]
            if len(keys) == 1:
                left_on, right_on = left_on[0], right_on[0]
            ops.append({
                "left": j.left_source,
                "right": j.right_source,
                "left_on": left_on,
                "right_on": right_on,
                "how": j.how,
            })
        return ops

    # ── Validation ───────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return human-readable warnings about the current configuration."""
        warnings: list[str] = []
        for ap in self.appends:
            if len(ap.members) == 1:
                warnings.append(
                    f"Append Table {ap.name} has only one member — drop more "
                    f"queries in to append them.")
            if ap.members and not self.shared_fields(ap.name):
                warnings.append(
                    f"Append Table {ap.name}: its members share no columns.")
        for j in self.joins:
            left_known = (self.get_source(j.left_source) is not None
                          or self.get_append(j.left_source) is not None)
            right_known = (self.get_source(j.right_source) is not None
                           or self.get_append(j.right_source) is not None)
            left_fields = self.fields_of(j.left_source)
            right_fields = self.fields_of(j.right_source)
            for k in j.keys:
                if left_known and k.left_field and k.left_field not in left_fields:
                    warnings.append(
                        f"{j.left_source}.{k.left_field} is not a known field.")
                if right_known and k.right_field and k.right_field not in right_fields:
                    warnings.append(
                        f"{j.right_source}.{k.right_field} is not a known field.")
            if not j.complete_keys():
                warnings.append(
                    f"Relationship {j.left_source}–{j.right_source} has no "
                    f"complete key.")
        return warnings

    # ── State persistence ────────────────────────────────────────────────

    def to_state(self) -> dict:
        return {
            "sources": [s.to_dict() for s in self.sources],
            "joins": [j.to_dict() for j in self.joins],
            "appends": [ap.to_dict() for ap in self.appends],
        }

    def from_state(self, state: dict) -> None:
        self.sources = [CanvasSource.from_dict(s)
                        for s in state.get("sources", [])]
        self.joins = [CanvasJoin.from_dict(j) for j in state.get("joins", [])]
        self.appends = [CanvasAppend.from_dict(a)
                        for a in state.get("appends", [])]

    @staticmethod
    def from_legacy_merges(merges: list[dict]) -> "JoinCanvasModel":
        """Build a model from the old {left,right,left_on,right_on,how} ops."""
        model = JoinCanvasModel()
        aliases: dict[str, CanvasSource] = {}

        def ensure(name: str) -> CanvasSource:
            if name not in aliases:
                src = CanvasSource(alias=name,
                                   x=40 + 60 * len(aliases),
                                   y=40 + 40 * len(aliases))
                aliases[name] = src
                model.sources.append(src)
            return aliases[name]

        for m in merges:
            left, right = m.get("left", ""), m.get("right", "")
            if not left or not right:
                continue
            ensure(left)
            ensure(right)
            left_on = m.get("left_on", "")
            right_on = m.get("right_on", "")
            if isinstance(left_on, str):
                left_on = [left_on]
            if isinstance(right_on, str):
                right_on = [right_on]
            join = CanvasJoin(left_source=left, right_source=right,
                              keys=[], how=m.get("how", "inner"))
            for lo, ro in zip(left_on, right_on):
                if lo and ro:
                    join.keys.append(JoinKey(lo, ro))
            if join.keys:
                model.joins.append(join)
        return model

    @staticmethod
    def from_legacy_cards(cards: list[dict]) -> "JoinCanvasModel":
        """Build a model from the old ForgeJoinsTab card state.

        Each card had: left, right, how, on_pairs ([(l, r), ...]), enabled.
        Box positions were keyed by card id (not Source), so they can't be
        reused; boxes get a fresh cascade layout.
        """
        merges: list[dict] = []
        for c in cards:
            pairs = [(lf, rf) for lf, rf in c.get("on_pairs", []) if lf and rf]
            if not pairs:
                continue
            merges.append({
                "left": c.get("left", ""),
                "right": c.get("right", ""),
                "left_on": [p[0] for p in pairs],
                "right_on": [p[1] for p in pairs],
                "how": c.get("how", "inner"),
            })
        model = JoinCanvasModel.from_legacy_merges(merges)
        # Carry the per-card enabled flag onto the relationships.
        for c, j in zip([c for c in cards
                         if any(lf and rf for lf, rf in c.get("on_pairs", []))],
                        model.joins):
            j.enabled = c.get("enabled", True)
        return model
